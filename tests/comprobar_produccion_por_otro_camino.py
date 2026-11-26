"""Prueba por otro camino de las previsiones de producción del caso 69 (método preproduccion, apartado 2.4).

Rehace cada previsión de un fichero de producción sin cargar el modelo guardado y sin importar el código de producción
(ni produccion/ ni scripts/produccion_prevision.py, ni los módulos que este reutiliza para prever,
variables_prevision.py y prevision_recursiva.py). Lo que cambia frente a producción:
  - el Pipeline se reconstruye desde la receta de la búsqueda (informes/busqueda.json, «ganador»: columnas e
    hiperparámetros) con el preprocesador del desarrollo, scripts/preparacion_prevision.py, el que usaron la búsqueda y
    la validación: con las ramas de event_name_1 y event_name_2 y con las columnas evento_<nombre> que ya trae la tabla.
    Producción no lleva esas ramas y calcula los eventos con su lista aprendida;
  - la previsión día a día se escribe aquí: cada serie es una fila de una matriz con sus 28 últimos días, tomados por
    fecha; cada día se calculan los retardos y las medias con NumPy, se prevé, se acota en cero y la previsión pasa a
    ser el último día de la matriz. Los retardos y las ventanas se leen de informes/variables_modelo.json.
Compara fila a fila, uniendo por objetivo, origen, serie y fecha, la previsión sin redondear con la de producción, con la
tolerancia de produccion/configuracion.json (1e-12, preproduccion/parametros.md).

Con --estropear cambia a propósito una previsión de producción (le suma 1e-6, mil veces la tolerancia): la prueba tiene
que salir en rojo; sin ese caso el verde no prueba nada.

Aquí se ejecuta con los 13 orígenes de la validación sobre lo que dejó el primer reentreno; con el año guardado lo
ejecuta la petición 28, con el fichero de producción y la tabla de historia que se le pasen. El reentrenado (petición
29) se entrena con una tabla sin las columnas evento_<nombre> (produccion_prevision.tabla_con_variables): aquí se
calculan con pandas de event_name_1 y event_name_2, con la lista de su entrenamiento (columnas_de_evento).

Uso: python -W error tests/comprobar_produccion_por_otro_camino.py --produccion PARQUET [--entrenamiento PARQUET]
     [--historia PARQUET ...] [--resultado JSON] [--estropear]
Sale con 0 si todas las filas coinciden y con 1 si no.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
from preparacion_prevision import columnas_entrada, construir_preprocesador  # noqa: E402  los del desarrollo

CONFIGURACION = CASO / "produccion" / "configuracion.json"
BUSQUEDA = CASO / "informes" / "busqueda.json"
VARIABLES = CASO / "informes" / "variables_modelo.json"
VALIDACION_POR_DEFECTO = CASO / "data" / "processed" / "hechos_modelo_validacion.parquet"
CLAVE_SERIE = ["store_id", "dept_id"]
CLAVES = CLAVE_SERIE + ["date"]
ESTROPEO = 1e-6


# ══ 2. La receta y el ajuste, sin el código de producción ═══════════════════════
def parametro(variables, nombre):
    """Un parámetro de informes/variables_modelo.json."""
    return next(p["valor"] for p in variables["parametros"] if p["nombre"] == nombre)


def modelo_desde_la_receta(ganador, objetivo, columnas_evento):
    """El Pipeline de la búsqueda: el preprocesador del desarrollo, las columnas del ganador y su boosting."""
    seleccion = ColumnTransformer([("columnas", "passthrough", list(ganador["columnas"]))], remainder="drop",
                                  verbose_feature_names_out=False).set_output(transform="pandas")
    return Pipeline([("preprocesador", construir_preprocesador(objetivo, columnas_evento)),
                     ("columnas", seleccion), ("modelo", HistGradientBoostingRegressor(**ganador["hiperparametros"]))])


def columnas_de_evento(entrenamiento, tabla):
    """Las columnas evento_<nombre> del entrenamiento y de la tabla de historia, y su lista.

    La tabla de la validación ya las trae (scripts/11_variables_modelo.py): se usan tal cual. La del reentrenado
    (produccion_prevision.tabla_con_variables) solo trae event_name_1 y event_name_2: aquí se calculan con pandas, sin
    el código de producción. La lista son los eventos que aparecen en los dos campos del entrenamiento, ordenados (la
    lista aprende del entrenamiento, R-015); cada columna vale 1 el día que trae el evento en cualquiera de los dos. Si
    la tabla de historia ya trae una columna de la lista, tiene que coincidir con la calculada: si no, para.
    Devuelve copias del entrenamiento y de la tabla con las columnas, y la lista de columnas.
    """
    ya = [c for c in entrenamiento.columns if c.startswith("evento_")]
    if ya:
        return entrenamiento, tabla, ya
    nombres = sorted(str(n) for n in pd.concat([entrenamiento["event_name_1"], entrenamiento["event_name_2"]])
                     .dropna().unique())
    columnas = [f"evento_{n}" for n in nombres]
    salidas = []
    for t in (entrenamiento, tabla):
        nueva = t.copy()
        for nombre, columna in zip(nombres, columnas):
            calculada = ((t["event_name_1"] == nombre).fillna(False).to_numpy()
                         | (t["event_name_2"] == nombre).fillna(False).to_numpy()).astype("int64")
            if columna in t.columns:
                traida = t[columna].to_numpy(dtype="float64")
                hay = ~np.isnan(traida)
                if (traida[hay] != calculada[hay]).any():
                    raise ValueError(f"{columna}: la tabla de historia trae otros valores que los calculados con "
                                     "event_name_1 y event_name_2")
            nueva[columna] = calculada
        salidas.append(nueva)
    return salidas[0], salidas[1], columnas


# ══ 3. La previsión día a día, escrita aquí ═════════════════════════════════════
def prever_por_otro_camino(modelo, historia, futuro, objetivo, origen, horizonte, retardos, ventanas):
    """Prevé desde un origen con una matriz por serie de los últimos días, tomados por fecha.

    historia: la venta real (store_id, dept_id, date y el objetivo). futuro: lo que se sabe de antemano de cada serie y
    día del horizonte. Devuelve store_id, dept_id, date y prevision_otro_camino.
    """
    largo = max(max(retardos), max(ventanas))
    dias = [origen - pd.Timedelta(largo - 1 - i, "D") for i in range(largo)]
    tramo = historia[historia["date"].isin(dias).to_numpy()]
    matriz = tramo.pivot(index=CLAVE_SERIE, columns="date", values=objetivo).reindex(columns=dias)
    if matriz.isna().any().any():
        raise ValueError(f"series sin los {largo} días que acaban en el origen {origen:%Y-%m-%d}")
    series = matriz.index.to_frame(index=False)
    valores = matriz.to_numpy(dtype="float64")
    salida = []
    for h in range(1, horizonte + 1):
        dia = origen + pd.Timedelta(h, "D")
        del_dia = futuro[(futuro["date"] == dia).to_numpy()]
        del_dia = del_dia.drop(columns=[c for c in del_dia.columns if c.startswith(("unidades", "dolares"))])
        x = series.merge(del_dia, on=CLAVE_SERIE, how="left", validate="one_to_one")
        if x["date"].isna().any():
            raise ValueError(f"al futuro le faltan series el {dia:%Y-%m-%d}")
        for k in retardos:
            x[f"{objetivo}_lag_{k}"] = valores[:, -k]
        for w in ventanas:
            x[f"{objetivo}_media_{w}"] = valores[:, -w:].mean(axis=1)
        previsto = np.clip(np.asarray(modelo.predict(x), dtype="float64"), 0.0, None)
        salida.append(series.assign(date=dia, prevision_otro_camino=previsto))
        valores = np.column_stack([valores, previsto])
    return pd.concat(salida, ignore_index=True)


# ══ 4. Principal ════════════════════════════════════════════════════════════════
def principal(args):
    """Rehace las previsiones, las compara fila a fila y devuelve el resultado."""
    configuracion = json.loads(CONFIGURACION.read_text(encoding="utf-8"))
    tolerancia = float(configuracion["tolerancia"])
    busqueda = json.loads(BUSQUEDA.read_text(encoding="utf-8"))
    variables = json.loads(VARIABLES.read_text(encoding="utf-8"))
    retardos, ventanas = parametro(variables, "retardos"), parametro(variables, "ventanas de las medias")
    entrenamiento_ruta = Path(args.entrenamiento or CASO / configuracion["rutas"]["tabla_de_la_particion"])
    entrenamiento = pd.read_parquet(entrenamiento_ruta)
    historias = [entrenamiento] + [pd.read_parquet(Path(p)) for p in (args.historia or [VALIDACION_POR_DEFECTO])]
    tabla = pd.concat(historias, ignore_index=True)
    produccion = pd.read_parquet(Path(args.produccion))
    columna = "prevision_sin_redondear" if "prevision_sin_redondear" in produccion.columns else "prevision"
    produccion["origen"] = pd.to_datetime(produccion["origen"])
    if args.estropear:
        produccion.loc[produccion.index[0], columna] = produccion.loc[produccion.index[0], columna] + ESTROPEO

    # El ajuste, con las filas que tienen toda su historia, en el orden de fecha y serie de la búsqueda
    historia_cols = [c for c in entrenamiento.columns if c.startswith(("unidades_", "dolares_"))] + [
        "precio_medio_semana_anterior"]
    ajuste = entrenamiento.dropna(subset=historia_cols).sort_values(["date"] + CLAVE_SERIE, kind="stable")
    ajuste = ajuste.reset_index(drop=True)
    # Las columnas de evento: las que trae la tabla o, en la del reentrenado, calculadas aquí con su lista
    ajuste, tabla, columnas_evento = columnas_de_evento(ajuste, tabla)
    por_objetivo, partes = {}, []
    for objetivo in sorted(produccion["objetivo"].unique()):
        ganador = busqueda["ganador"][objetivo]
        modelo = modelo_desde_la_receta(ganador, objetivo, columnas_evento)
        entrada = columnas_entrada(objetivo, columnas_evento)
        modelo.fit(ajuste[entrada], ajuste[objetivo])
        de = produccion[produccion["objetivo"] == objetivo]
        for origen in sorted(de["origen"].unique()):
            origen = pd.Timestamp(origen)
            horizonte = int(de.loc[de["origen"] == origen, "date"].nunique())
            dias = [origen + pd.Timedelta(h, "D") for h in range(1, horizonte + 1)]
            futuro = tabla[tabla["date"].isin(dias).to_numpy()]
            p = prever_por_otro_camino(modelo, tabla[CLAVES + [objetivo]], futuro, objetivo, origen, horizonte,
                                       retardos, ventanas)
            partes.append(p.assign(objetivo=objetivo, origen=origen))
    aqui = pd.concat(partes, ignore_index=True)

    # Fila a fila, uniendo por objetivo, origen, serie y fecha
    claves = ["objetivo", "origen"] + CLAVES
    unido = produccion[claves + [columna]].merge(aqui, on=claves, how="outer", validate="one_to_one", indicator=True)
    for objetivo in sorted(unido["objetivo"].unique()):
        de = unido[unido["objetivo"] == objetivo]
        ambos = de[de["_merge"] == "both"]
        dif = np.abs(ambos[columna].to_numpy(dtype="float64") - ambos["prevision_otro_camino"].to_numpy(dtype="float64"))
        por_objetivo[objetivo] = {"filas": int(len(ambos)), "solo_en_produccion": int((de["_merge"] == "left_only").sum()),
                                  "solo_por_otro_camino": int((de["_merge"] == "right_only").sum()),
                                  "diferencia_maxima": float(dif.max()) if len(dif) else None,
                                  "filas_por_encima_de_la_tolerancia": int((dif > tolerancia).sum())}
    coincide = all(x["solo_en_produccion"] == 0 and x["solo_por_otro_camino"] == 0
                   and x["filas_por_encima_de_la_tolerancia"] == 0 and x["filas"] > 0 for x in por_objetivo.values())
    return {"coincide": bool(coincide), "estropeada": bool(args.estropear), "tolerancia": tolerancia,
            "origenes": int(produccion["origen"].nunique()), "produccion": str(args.produccion),
            "columna_comparada": columna, "entrenamiento": str(entrenamiento_ruta),
            "historia": [str(p) for p in (args.historia or [VALIDACION_POR_DEFECTO])], "por_objetivo": por_objetivo,
            "como": "Pipeline reconstruido desde informes/busqueda.json con el preprocesador del desarrollo; "
                    "previsión día a día escrita aquí con NumPy; sin cargar el modelo ni importar producción"}


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Prueba por otro camino de las previsiones de producción")
    argumentos.add_argument("--produccion", required=True, help="previsiones de producción (Parquet)")
    argumentos.add_argument("--entrenamiento", default=None, help="tabla con la que se reajusta la receta")
    argumentos.add_argument("--historia", nargs="*", default=None, help="tablas con la venta real y el futuro")
    argumentos.add_argument("--resultado", default=None, help="JSON donde se escribe el resultado")
    argumentos.add_argument("--estropear", action="store_true", help="cambia a propósito una previsión de producción")
    args = argumentos.parse_args()
    print("intérprete:", sys.executable)
    resultado = principal(args)
    if args.resultado:
        Path(args.resultado).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    for o, x in resultado["por_objetivo"].items():
        print(f"{o}: {x['filas']} filas, diferencia máxima {x['diferencia_maxima']}, por encima de la tolerancia "
              f"{x['filas_por_encima_de_la_tolerancia']}, solo en producción {x['solo_en_produccion']}, solo aquí "
              f"{x['solo_por_otro_camino']}")
    print("RESULTADO:", "COINCIDE" if resultado["coincide"] else "NO COINCIDE",
          "(salida estropeada a propósito)" if args.estropear else "")
    sys.exit(0 if resultado["coincide"] else 1)
