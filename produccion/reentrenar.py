"""Reentreno de los dos modelos de previsión del caso 69 con la receta fija del contrato (método preproduccion, apartado 2.2).

Rehace el modelo de unidades y el de dólares con la receta del contrato aprobado por el responsable del caso el 25/11/2026 («Apruebo el
contrato»; informes/preproduccion.json): las mismas finalistas, el mismo preprocesador y el mismo
HistGradientBoosting con sus hiperparámetros y su semilla. No vuelve a buscar algoritmo ni hiperparámetros: eso es una
modelización nueva. No sustituye al modelo en uso: lo decide el responsable del caso.

Lo que hace, en este orden:
  1. lee la tabla de entrenamiento que se le pasa (--tabla, sin valor por defecto), con la forma de
     data/processed/hechos_modelo_entrenamiento.parquet o de produccion_prevision.tabla_con_variables. Con la tabla de
     la partición solo se ejecuta en modo de comprobación (--comprobacion); si no, ERROR;
  2. quita, contadas, las filas que quitan filas en el contrato: las que tienen el objetivo vacío (R-010: la tabla que
     se pasa marca el corte y el objetivo se sabe al momento) y las que no tienen la historia que piden las variables
     (R-017: en una tabla completa son los 35 primeros días de cada serie). Para si una fila sin historia cae a mitad
     de una serie: sería un hueco, no un primer día;
  3. ordena por fecha y serie (error 7), construye el Pipeline de cada objetivo, lo guarda sin ajustar (la receta,
     antes del fit), lo ajusta, comprueba que el modelo recibe exactamente las columnas del contrato y lo guarda con
     joblib y su ficha en modelos/reentrenos/AAAA-MM-DD/. Si esa carpeta ya existe, para sin tocarla;
  4. si hay modelo en uso: con la misma tabla tiene que salir igual bit a bit; con otra, distinto. Si no lo hay, el
     reentreno sin los últimos días de la tabla tiene que salir distinto (validación 8);
  5. en modo de comprobación (el primer reentreno): prevé en recursivo desde los orígenes de la referencia que se le
     pasa (--referencia, las previsiones de la validación) con la tabla de validación (--validacion), como
     scripts/16_validacion.py, y compara fila a fila con la tolerancia de la configuración. Si no coincide, para.
Deja en la carpeta del reentreno <objetivo>_receta.joblib, <objetivo>.joblib, sus fichas <nombre>_versiones.json,
reentreno.json y, en modo de comprobación, previsiones_comprobacion.parquet.

Uso: python -W error produccion/reentrenar.py --tabla TABLA [--comprobacion --validacion TABLA --referencia TABLA]
     [--raiz CARPETA] [--fecha AAAA-MM-DD]
Sale con 0 si el reentreno queda guardado con sus validaciones en verde y con 1 si para o alguna sale en rojo.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import importlib
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
CONFIGURACION_REL = "produccion/configuracion.json"
SCRIPT_REL = "produccion/reentrenar.py"
CLAVE_SERIE = ["store_id", "dept_id"]
COLUMNA_FECHA = "date"
CLAVES = CLAVE_SERIE + [COLUMNA_FECHA]
OBJETIVOS = ("unidades", "dolares")
# Los pasos que quitan filas: solo existen aquí; ejecutar.py no puede llamar a ninguno (validación 6)
PASOS_QUE_QUITAN_FILAS = ["quitar_sin_objetivo", "quitar_sin_historia"]
COLUMNAS_REFERENCIA = ["objetivo", "origen", "store_id", "dept_id", "date", "modelo"]


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def leer_configuracion(raiz):
    """La configuración de producción, en UTF-8 (error 21)."""
    return json.loads((raiz / CONFIGURACION_REL).read_text(encoding="utf-8"))


def ruta_de(raiz, ruta):
    """Una ruta de la configuración, desde la carpeta del caso si no es absoluta (error 23)."""
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else raiz / ruta


def importar_modulo(raiz, configuracion):
    """Importa scripts/produccion_prevision.py con su nombre, que es el que guarda joblib en el modelo."""
    carpeta = str(ruta_de(raiz, configuracion["rutas"]["modulo"]))
    if carpeta not in sys.path:
        sys.path.insert(0, carpeta)
    return importlib.import_module("produccion_prevision")


def a_json(obj):
    """Un objeto como JSON válido: fechas en ISO, números de NumPy como números y vacíos como null (error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()[:10] if getattr(obj, "hour", 0) == 0 and getattr(obj, "minute", 0) == 0 else \
            obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ══ 3. Los pasos que quitan filas (solo aquí, contados) ══════════════════════════
def quitar_sin_objetivo(tabla):
    """R-010: la tabla que se pasa marca el corte; quita las filas cuyo objetivo aún no se conoce (vacío).

    En este caso el objetivo se sabe al momento: en una tabla de entrenamiento bien hecha salen 0. Devuelve la tabla y
    las filas quitadas.
    """
    vacio = tabla[list(OBJETIVOS)].isna().any(axis=1).to_numpy()
    return tabla[~vacio].reset_index(drop=True), int(vacio.sum())


def quitar_sin_historia(tabla, columnas_de_historia):
    """R-017: quita las filas sin la historia que piden las variables; para si una cae a mitad de su serie.

    Una fila sin historia tiene vacía alguna de las columnas que salen de días anteriores. En una tabla completa son
    los 35 primeros días de cada serie: 28 por los retardos y la media más larga y las cinco primeras semanas del
    precio medio. Si una fila vacía va detrás de una completa en su serie es un hueco y no un primer día: para.
    Devuelve la tabla y las filas quitadas.
    """
    orden = tabla.sort_values(CLAVES, kind="stable")
    vacia = orden[columnas_de_historia].isna().any(axis=1)
    completa_antes = (~vacia).astype("int64").groupby([orden[c] for c in CLAVE_SERIE], sort=False).cummax()
    huecos = orden.loc[(vacia & (completa_antes == 1)).to_numpy(), CLAVES]
    if len(huecos):
        primeros = "; ".join(f"{x.store_id} {x.dept_id} {x.date:%Y-%m-%d}" for x in huecos.head(3).itertuples())
        raise ValueError(f"{len(huecos)} filas sin historia a mitad de su serie (un hueco, no un primer día): {primeros}")
    quitar = vacia.reindex(tabla.index).to_numpy()
    return tabla[~quitar].reset_index(drop=True), int(quitar.sum())


# ══ 4. Ajustar, guardar y comparar ══════════════════════════════════════════════
def ajustar_y_guardar(pp, receta, ajuste, carpeta, objetivo, datos_ficha):
    """Construye el Pipeline, guarda la receta antes del fit, ajusta, comprueba las columnas y guarda con su ficha."""
    entrada = pp.columnas_de_entrada(receta)
    pipe = pp.construir_pipeline(receta)
    pp.guardar_modelo(pipe, carpeta / f"{objetivo}_receta.joblib", objetivo=objetivo, ajustado=False,
                      que_es="la receta: el Pipeline sin ajustar, guardado antes del fit")
    pipe.fit(ajuste[entrada], ajuste[objetivo])
    salen = pp.comprobar_columnas_de_salida(pipe, receta["columnas"])
    ficha = pp.guardar_modelo(pipe, carpeta / f"{objetivo}.joblib", objetivo=objetivo, ajustado=True,
                              semilla=receta["hiperparametros"].get("random_state"), filas=len(ajuste),
                              columnas_entrada=entrada, columnas_salida=list(pipe.named_steps["modelo"].feature_names_in_),
                              inspeccion=pp.inspeccion(pipe),
                              lleva_filas_de_entrenamiento=pp.lleva_filas_de_entrenamiento(pipe, len(ajuste)),
                              **datos_ficha)
    return pipe, ficha, salen


def prever_origenes(pp, modelos, historia, validacion, referencia, horizontes):
    """Prevé en recursivo cada objetivo desde los orígenes de la referencia, como scripts/16_validacion.py.

    La historia es la venta real de la tabla de entrenamiento y de la validación; cada previsión la corta en su origen.
    El futuro son las filas de validación de los días del horizonte. Devuelve una fila por objetivo, origen, serie y día.
    """
    partes = []
    for objetivo, modelo in modelos.items():
        h = horizontes[objetivo]
        origenes = sorted(pd.to_datetime(referencia.loc[referencia["objetivo"] == objetivo, "origen"]).unique())
        for origen in origenes:
            origen = pd.Timestamp(origen)
            dias = [origen + pd.Timedelta(k, "D") for k in range(1, h + 1)]
            futuro = validacion[validacion[COLUMNA_FECHA].isin(dias).to_numpy()]
            p = pp.prever(modelo, historia[CLAVES + [objetivo]], futuro, objetivo, h, origen)
            partes.append(p.assign(objetivo=objetivo, origen=origen,
                                   prevision=pp.redondear_salida(p["prevision_sin_redondear"], objetivo)))
    return pd.concat(partes, ignore_index=True)[["objetivo", "origen"] + CLAVES +
                                                ["h", "prevision_sin_redondear", "prevision"]]


def comparar_con_referencia(previsto, referencia, tolerancia):
    """Une por objetivo, origen, serie y fecha y mide la diferencia máxima con la previsión de la referencia.

    Las unidades se comparan redondeadas, como las guardó la validación; los dólares, acotados y sin redondear. Para un
    objetivo coincide si están las mismas filas en los dos lados y ninguna se separa más que la tolerancia.
    """
    claves = ["objetivo", "origen"] + CLAVES
    ref = referencia[COLUMNAS_REFERENCIA].copy()
    ref["origen"] = pd.to_datetime(ref["origen"])
    unido = previsto.merge(ref, on=claves, how="outer", validate="one_to_one", indicator=True)
    resultado = {}
    for objetivo in sorted(unido["objetivo"].unique()):
        de = unido[unido["objetivo"] == objetivo]
        ambos = de[de["_merge"] == "both"]
        diferencia = np.abs(ambos["prevision"].to_numpy(dtype="float64") - ambos["modelo"].to_numpy(dtype="float64"))
        maxima = float(diferencia.max()) if len(diferencia) else None
        resultado[objetivo] = {"filas": int(len(ambos)), "solo_en_produccion": int((de["_merge"] == "left_only").sum()),
                               "solo_en_la_referencia": int((de["_merge"] == "right_only").sum()),
                               "diferencia_maxima": maxima,
                               "filas_por_encima_de_la_tolerancia": int((diferencia > tolerancia).sum()),
                               "coincide": bool(len(ambos) == len(de) and maxima is not None and maxima <= tolerancia)}
    return resultado


# ══ 5. Principal ════════════════════════════════════════════════════════════════
def principal(args):
    """Reentrena con la receta fija, compara y escribe reentreno.json; devuelve el código de salida."""
    raiz = Path(args.raiz).resolve()
    configuracion = leer_configuracion(raiz)
    pp = importar_modulo(raiz, configuracion)
    tolerancia = float(configuracion["tolerancia"])

    # 5.1 El contrato tiene que estar aprobado (resultado.md: sin aprobar, la parte 2 no empieza)
    contrato = json.loads(ruta_de(raiz, configuracion["rutas"]["contrato"]).read_text(encoding="utf-8"))
    if not (contrato.get("contrato") or {}).get("aprobado_por"):
        print("PARADO · el contrato de producción no está aprobado: no se reentrena")
        return 1

    # 5.2 La tabla: con la de la partición, solo en modo de comprobación
    ruta_tabla = Path(args.tabla).resolve()
    huella_tabla = pp.huella(ruta_tabla)
    particion = ruta_de(raiz, configuracion["rutas"]["tabla_de_la_particion"])
    es_la_particion = particion.exists() and pp.huella(particion) == huella_tabla
    if es_la_particion and not args.comprobacion:
        print("ERROR · con la tabla de la partición solo se reentrena en modo de comprobación (--comprobacion)")
        return 1
    if args.comprobacion and (args.validacion is None or args.referencia is None):
        print("ERROR · el modo de comprobación necesita --validacion y --referencia")
        return 1
    recetas = {o: pp.receta_del_contrato(contrato, o) for o in OBJETIVOS}
    for o, receta in recetas.items():
        if receta["hiperparametros"].get("random_state") != configuracion["semilla"]:
            print(f"ERROR · la receta de {o} no lleva la semilla de la configuración")
            return 1
    tabla = pd.read_parquet(ruta_tabla)
    entradas = sorted({c for receta in recetas.values() for c in pp.columnas_de_entrada(receta)})
    pp.comprobar_columnas(tabla, CLAVES + list(OBJETIVOS) + entradas, "la tabla de entrenamiento")
    numericas = [c for receta in recetas.values() for r in ("pasa", "ss", "rs") for c in receta["ramas"].get(r, [])]
    pp.comprobar_numericas(tabla, list(OBJETIVOS) + numericas, "la tabla de entrenamiento")

    # 5.3 Los pasos que quitan filas, contados (R-010 y R-017)
    fecha_corte = pd.Timestamp(tabla[COLUMNA_FECHA].max())
    sin_objetivo, n_sin_objetivo = quitar_sin_objetivo(tabla)
    con_historia, n_sin_historia = quitar_sin_historia(sin_objetivo, pp.COLUMNAS_DE_HISTORIA)
    ajuste = con_historia.sort_values([COLUMNA_FECHA] + CLAVE_SERIE, kind="stable").reset_index(drop=True)
    filas_quitadas = [{"motivo": "objetivo sin conocer", "ficha": "R-010", "fecha": fecha_corte,
                       "filas": n_sin_objetivo, "casos_del_evento": None},
                      {"motivo": "sin la historia que piden las variables", "ficha": "R-017", "filas": n_sin_historia}]

    # 5.4 La carpeta del reentreno: si ya existe, para sin tocarla. Puede ser un candidato que espera al responsable del caso o el modelo
    # en uso; moverla dejaría su ruta con otro modelo dentro (petición 28, tarea 4). Cada reentreno va a su carpeta
    carpeta = ruta_de(raiz, configuracion["rutas"]["reentrenos"]) / args.fecha
    if carpeta.exists():
        print(f"ERROR · la carpeta del reentreno {carpeta} ya existe: no se toca; pasa otra fecha con --fecha")
        return 1
    carpeta.mkdir(parents=True)
    try:
        tabla_rel = ruta_tabla.relative_to(raiz).as_posix()
    except ValueError:
        tabla_rel = str(ruta_tabla)

    # 5.5 Ajustar y guardar cada objetivo con su ficha
    datos_ficha = {"tabla": tabla_rel, "huella_tabla": huella_tabla, "fecha_datos": f"{fecha_corte:%Y-%m-%d}",
                   "contrato": {k: contrato["contrato"].get(k) for k in ("aprobado_por", "fecha", "estado")}}
    modelos, fichas, columnas_ok = {}, {}, {}
    for o in OBJETIVOS:
        try:
            modelos[o], fichas[o], _ = ajustar_y_guardar(pp, recetas[o], ajuste, carpeta, o, datos_ficha)
            columnas_ok[o] = True
        except ValueError as error:
            print(f"ERROR · {o}: {error}")
            columnas_ok[o] = False
    validaciones = {"columnas_del_contrato": all(columnas_ok.values()), "bit_a_bit": None,
                    "cambia_con_datos_nuevos": None}
    r = {"script": SCRIPT_REL, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "fecha_datos": f"{fecha_corte:%Y-%m-%d}", "modo": "comprobacion" if args.comprobacion else "reentreno",
         "tabla": {"ruta": tabla_rel, "sha256": huella_tabla, "filas": len(tabla), "fecha_corte": fecha_corte,
                   "es_la_de_la_particion": es_la_particion},
         "filas_entrada": len(tabla), "filas_quitadas": filas_quitadas, "filas_ajuste": len(ajuste),
         "ruta": carpeta.relative_to(raiz).as_posix() if carpeta.is_relative_to(raiz) else str(carpeta),
         "modelos": {o: {"receta": f"{o}_receta.joblib", "modelo": f"{o}.joblib", "ficha": f"{o}_versiones.json",
                         "huella": fichas[o]["huella"] if o in fichas else None,
                         "columnas": len(recetas[o]["columnas"])} for o in OBJETIVOS},
         "pasos_que_quitan_filas": PASOS_QUE_QUITAN_FILAS, "versiones": pp.versiones()}
    if not validaciones["columnas_del_contrato"]:
        return escribir(carpeta, r, validaciones)
    entrada = {o: pp.columnas_de_entrada(recetas[o]) for o in OBJETIVOS}

    # 5.6 Frente al modelo en uso; si no lo hay, frente al reentreno sin los últimos días (validaciones 4 y 8)
    en_uso = configuracion.get("modelo_en_uso")
    r["comparacion_con_el_en_uso"] = {"periodo": None, "filas": None, "medida": None, "en_uso": None,
                                      "reentrenado": None}
    if en_uso:
        carpeta_en_uso = ruta_de(raiz, en_uso)
        misma, iguales = {}, {}
        for o in OBJETIVOS:
            viejo, ficha_vieja = pp.cargar_modelo(carpeta_en_uso / f"{o}.joblib")
            x = ajuste[entrada[o]]
            iguales[o] = bool(np.array_equal(viejo.predict(x), modelos[o].predict(x)))
            misma[o] = ficha_vieja.get("huella_tabla") == huella_tabla
        r["modelo_en_uso"] = {"existia": True, "de_donde": en_uso, "misma_tabla": misma, "sale_igual": iguales}
        if all(misma.values()):
            validaciones["bit_a_bit"] = all(iguales.values())
        else:
            validaciones["cambia_con_datos_nuevos"] = not any(iguales.values())
    else:
        r["modelo_en_uso"] = {"existia": False, "de_donde": "ninguno: el responsable del caso aún no ha aprobado un modelo en uso; el "
                                                            "primer reentreno se compara con la validación"}
        dias_menos = int(configuracion["dias_menos_para_comprobar_que_cambia"])
        corte = ajuste[COLUMNA_FECHA].max() - pd.Timedelta(dias_menos, "D")
        menos = ajuste[(ajuste[COLUMNA_FECHA] <= corte).to_numpy()].reset_index(drop=True)
        cambia = {}
        for o in OBJETIVOS:
            otro = pp.construir_pipeline(recetas[o]).fit(menos[entrada[o]], menos[o])
            x = ajuste[entrada[o]]
            dif = np.abs(otro.predict(x) - modelos[o].predict(x))
            cambia[o] = {"diferencia_maxima": float(dif.max()), "cambia": bool(dif.max() > 0)}
        r["cambia_con_datos_nuevos"] = {"tabla": f"la misma sin sus últimos {dias_menos} días ({len(menos)} filas)",
                                        "por_objetivo": cambia}
        validaciones["cambia_con_datos_nuevos"] = all(x["cambia"] for x in cambia.values())

    # 5.7 El primer reentreno frente a la validación, fila a fila (modo de comprobación)
    if args.comprobacion:
        validacion = pd.read_parquet(Path(args.validacion).resolve())
        referencia = pd.read_parquet(Path(args.referencia).resolve())
        pp.comprobar_columnas(referencia, COLUMNAS_REFERENCIA, "la referencia")
        historia = pd.concat([tabla, validacion], ignore_index=True)
        previsto = prever_origenes(pp, modelos, historia, validacion, referencia, configuracion["horizontes"])
        previsto.to_parquet(carpeta / "previsiones_comprobacion.parquet", index=False)
        por_objetivo = comparar_con_referencia(previsto, referencia, tolerancia)
        r["comprobacion"] = {"origenes": int(referencia["origen"].nunique()), "tolerancia": tolerancia,
                             "referencia": str(args.referencia), "validacion": str(args.validacion),
                             "huella_referencia": pp.huella(Path(args.referencia)),
                             "previsiones": "previsiones_comprobacion.parquet", "por_objetivo": por_objetivo,
                             "como": "unidades redondeadas al entero con la mitad hacia arriba, como las guardó la "
                                     "validación; dólares acotados en cero, sin redondear"}
        validaciones["bit_a_bit"] = all(x["coincide"] for x in por_objetivo.values())
        diferencias = ", ".join(f"{o} {x['diferencia_maxima']}" for o, x in por_objetivo.items())
        r["ramas_event_name"] = {
            "van": False,
            "motivo": (f"sin ellas el primer reentreno da las previsiones de la validación fila a fila (diferencia "
                       f"máxima {diferencias}; tolerancia {tolerancia:g}): cada rama aprende solo de su columna y sus "
                       "columnas no entran en el modelo") if validaciones["bit_a_bit"] else
                      "no se puede decidir: el primer reentreno no da las previsiones de la validación"}
    return escribir(carpeta, r, validaciones)


def escribir(carpeta, r, validaciones):
    """Escribe reentreno.json con su estado, calculado de las validaciones; devuelve el código de salida."""
    r["validaciones"] = validaciones
    if any(v is False for v in validaciones.values()):
        r["estado"] = "ERROR"
    elif any(v is None for v in validaciones.values()):
        r["estado"] = "AVISO"
    else:
        r["estado"] = "OK"
    (carpeta / "reentreno.json").write_text(json.dumps(a_json(r), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{r['estado']} · {r['filas_ajuste']} filas de ajuste; validaciones {validaciones}")
    for o, x in (r.get("comprobacion") or {}).get("por_objetivo", {}).items():
        print(f"  {o}: {x['filas']} filas comparadas, diferencia máxima {x['diferencia_maxima']}, coincide "
              f"{x['coincide']}")
    return 0 if r["estado"] in ("OK", "AVISO") else 1


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Reentreno de los dos modelos con la receta fija del contrato")
    argumentos.add_argument("--tabla", required=True, help="tabla de entrenamiento (Parquet); sin valor por defecto")
    argumentos.add_argument("--comprobacion", action="store_true", help="modo de comprobación del primer reentreno")
    argumentos.add_argument("--validacion", default=None, help="tabla de validación (solo en modo de comprobación)")
    argumentos.add_argument("--referencia", default=None, help="previsiones de la validación (modo de comprobación)")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    argumentos.add_argument("--fecha", default=datetime.now().strftime("%Y-%m-%d"), help="carpeta del reentreno")
    print("intérprete:", sys.executable)
    try:
        codigo = principal(argumentos.parse_args())
    except Exception:  # un fallo técnico para con su motivo y sale con 1
        traceback.print_exc()
        codigo = 1
    sys.exit(codigo)
