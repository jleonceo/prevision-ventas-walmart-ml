"""Ejecución diaria de la previsión del caso 69: unidades a 10 días y dólares a 28 (método preproduccion, apartado 2.3).

Prevé cada serie de departamento y tienda desde el último día con venta conocida, día a día, con los dos modelos que
deja produccion/reentrenar.py. Sigue el contrato aprobado por el responsable del caso el 25/11/2026 («Apruebo el contrato»),
«La previsión día a día». Al ejecutar no se tira ninguna fila: sale una por serie y día a prever; la que no se puede
prever sale con la previsión vacía y su motivo.

Lo que hace, en este orden:
  1. carga cada modelo solo si cuadra su ficha (versiones de scikit-learn y pandas, huella del fichero). El modelo es el
     de la configuración (modelo_en_uso, que aprueba el responsable del caso) o, como ensayo, el que se le pasa con --modelos;
  2. lee la venta, los precios y el calendario con la misma forma que data/raw/ (la venta por producto y tienda, un día
     por columna) y para con un mensaje claro si falta una columna o si un número llega como texto;
  3. comprueba que la venta es la del día que toca: su último día tiene que ser el origen que se pide (--origen). Si la
     historia no llega hasta él (la entrada del día anterior) o pasa de él, para;
  4. arma la historia de los 28 días que acaban en el origen (R-004) y lo que se sabe de antemano de los días a prever
     (calendario, snap, precio y productos de la semana anterior, día del mes) con scripts/produccion_prevision.py;
     comprueba que los precios llegan desde cuatro semanas antes de la semana anterior al primer día previsto hasta la
     semana anterior al último;
  5. una serie sin los 28 días de historia, o sin el precio de la semana anterior en algún día a prever, sale con la
     previsión vacía y su motivo; las demás se prevén día a día con la tabla que ya lleva lo previsto, uniendo por serie
     y fecha y acotando en cero; una categoría que el modelo no conoce se prevé (handle_unknown) y se marca;
  6. redondea las unidades al entero, con la mitad hacia arriba, solo en la salida; los dólares no;
  7. comprueba una fila por serie y día, ninguna vacía sin motivo ni negativa, y guarda en data/predicciones/AAAA-MM-DD/
     previsiones.parquet y resumen.json. Si ese día ya había una ejecución, la copia antes a data/predicciones/_archivo/.
Ningún paso que quita filas está aquí: esos solo van en produccion/reentrenar.py.

Uso: python -W error produccion/ejecutar.py --venta CSV --precios CSV --calendario CSV --origen AAAA-MM-DD
     [--modelos CARPETA] [--ensayo] [--raiz CARPETA] [--fecha AAAA-MM-DD]
Sale con 0 si la previsión queda guardada con sus comprobaciones en verde y con 1 si para.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import importlib
import importlib.util
import json
import re
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
CONFIGURACION_REL = "produccion/configuracion.json"
SCRIPT_REL = "produccion/ejecutar.py"
CLAVE_SERIE = ["store_id", "dept_id"]
COLUMNA_FECHA = "date"
CLAVES = CLAVE_SERIE + [COLUMNA_FECHA]
OBJETIVOS = ("unidades", "dolares")
COLUMNAS_SALIDA = ["objetivo", "origen", "store_id", "dept_id", "date", "h", "prevision", "prevision_sin_redondear",
                   "motivo", "aviso"]


class Parada(Exception):
    """La ejecución para con un mensaje claro: no se escribe ninguna previsión."""


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
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


def pasos_que_quitan_filas_aqui():
    """Los pasos que quitan filas (los de reentrenar.py) que este script llama en su código; tiene que ser ninguno."""
    spec = importlib.util.spec_from_file_location("reentrenar_pasos", Path(__file__).with_name("reentrenar.py"))
    reentrenar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reentrenar)
    codigo = Path(__file__).read_text(encoding="utf-8")
    return reentrenar.PASOS_QUE_QUITAN_FILAS, [p for p in reentrenar.PASOS_QUE_QUITAN_FILAS
                                               if re.search(rf"\b{re.escape(p)}\s*\(", codigo)]


def a_json(obj):
    """Un objeto como JSON válido: fechas en ISO, números de NumPy como números y vacíos como null (error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return f"{obj:%Y-%m-%d}"
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ══ 3. Las entradas ═════════════════════════════════════════════════════════════
def leer_entradas(pp, rutas):
    """Lee las tres entradas en UTF-8 y comprueba sus columnas y sus números; devuelve venta, precios y calendario."""
    venta = pd.read_csv(rutas["venta"], encoding="utf-8")
    precios = pd.read_csv(rutas["precios"], encoding="utf-8")
    calendario_crudo = pd.read_csv(rutas["calendario"], encoding="utf-8")
    pp.comprobar_columnas(venta, pp.COLUMNAS_VENTA, "la venta")
    if not pp.columnas_de_dias(venta):
        raise pp.EntradaNoValida("la venta no trae ninguna columna de día (d_1, d_2…)")
    pp.comprobar_columnas(precios, pp.COLUMNAS_PRECIOS, "los precios")
    pp.comprobar_numericas(venta, pp.columnas_de_dias(venta), "la venta")
    pp.comprobar_numericas(precios, pp.NUMERICAS_PRECIOS, "los precios")
    return venta, precios, pp.preparar_calendario(calendario_crudo)


def dias_de_la_historia(pp, venta, calendario, origen, historia_minima):
    """Comprueba que la venta es la del día que toca y devuelve las columnas de los días de historia, en orden.

    El último día con venta tiene que ser el origen: si es anterior, la historia no llega (la entrada del día anterior);
    si es posterior, no es la entrada de ese día. Faltan días de historia: para.
    """
    fecha_de = dict(zip(calendario["d"], calendario[COLUMNA_FECHA]))
    columnas = pp.columnas_de_dias(venta)
    desconocidas = [c for c in columnas if c not in fecha_de]
    if desconocidas:
        raise Parada(f"días de la venta que no están en el calendario: {desconocidas[:5]}")
    ultimo = max(fecha_de[c] for c in columnas)
    if ultimo < origen:
        raise Parada(f"la historia no llega hasta el día de origen pedido: la venta acaba el {ultimo:%Y-%m-%d} y el "
                     f"origen es el {origen:%Y-%m-%d} (¿es la entrada de un día anterior?)")
    if ultimo > origen:
        raise Parada(f"la venta llega hasta el {ultimo:%Y-%m-%d}, después del origen pedido ({origen:%Y-%m-%d}): no "
                     "es la entrada de ese día")
    columna_de = {fecha_de[c]: c for c in columnas}
    dias = [origen - pd.Timedelta(historia_minima - 1 - i, "D") for i in range(historia_minima)]
    faltan = [f"{d:%Y-%m-%d}" for d in dias if d not in columna_de]
    if faltan:
        raise Parada(f"la venta no trae los {historia_minima} días que acaban en el origen: faltan {faltan[:5]}")
    return [columna_de[d] for d in dias], ultimo


def comprobar_precios(pp, precios, calendario, dias_futuro):
    """Para si los precios no llegan desde cuatro semanas antes de la semana anterior al primer día previsto hasta la
    semana anterior al último (contrato, «Precios»)."""
    orden = pp.vp.orden_de_semanas(calendario)
    posicion = {int(w): i for i, w in enumerate(orden)}
    anterior = dict(zip(calendario[COLUMNA_FECHA], calendario["wm_yr_wk_anterior"]))
    primera, ultima = anterior[dias_futuro[0]], anterior[dias_futuro[-1]]
    if pd.isna(primera) or pd.isna(ultima):
        raise Parada("algún día a prever no tiene semana anterior en el calendario")
    desde = posicion[int(primera)] - pp.vp.SEMANAS_PREVIAS_CON_PRECIO
    hasta = posicion[int(ultima)]
    hay = precios["wm_yr_wk"].map(posicion)
    if hay.isna().any():
        raise Parada(f"{int(hay.isna().sum())} precios de semanas que no están en el calendario")
    if hay.min() > desde or hay.max() < hasta:
        raise Parada(f"los precios van de la semana {orden[int(hay.min())]} a la {orden[int(hay.max())]}; hacen falta "
                     f"de la {orden[max(desde, 0)]} a la {orden[hasta]}")


# ══ 4. La previsión de un objetivo ══════════════════════════════════════════════
def avisos_de_categoria(modelo, futuro):
    """Por serie, las categorías que el codificador del modelo no conoce: se prevén (handle_unknown) y se marcan."""
    ohe = modelo.named_steps["preprocesador"].named_transformers_["ohe"]
    avisos = {}
    for columna, conocidas in zip(ohe.feature_names_in_, ohe.categories_):
        nuevas = futuro.loc[~futuro[columna].isin(list(conocidas)).to_numpy(), CLAVE_SERIE + [columna]]
        for fila in nuevas.drop_duplicates().itertuples(index=False):
            clave = (fila[0], fila[1])
            avisos[clave] = (avisos.get(clave, "") + f"categoría nueva en {columna}: {fila[2]}; ").strip()
    return avisos


def prever_objetivo(pp, modelo, objetivo, horizonte, origen, series, historia, futuro, motivos):
    """Una fila por serie y día del horizonte: prevista o con la previsión vacía y su motivo, nunca quitada."""
    dias = [origen + pd.Timedelta(h, "D") for h in range(1, horizonte + 1)]
    rejilla = series.merge(pd.DataFrame({COLUMNA_FECHA: dias, "h": range(1, horizonte + 1)}), how="cross")
    motivo_obj = motivos[objetivo]
    validas = series[[(s, d) not in motivo_obj for s, d in zip(series["store_id"], series["dept_id"])]]
    del_horizonte = futuro[futuro[COLUMNA_FECHA].isin(dias).to_numpy()]
    avisos = {}
    if len(validas):
        dentro = pd.MultiIndex.from_frame(historia[CLAVE_SERIE]).isin(pd.MultiIndex.from_frame(validas))
        dentro_f = pd.MultiIndex.from_frame(del_horizonte[CLAVE_SERIE]).isin(pd.MultiIndex.from_frame(validas))
        previsto = pp.prever(modelo, historia[dentro][CLAVES + [objetivo]], del_horizonte[dentro_f], objetivo,
                             horizonte, origen)
        avisos = avisos_de_categoria(modelo, del_horizonte[dentro_f])
        salida = rejilla.merge(previsto[CLAVES + ["prevision_sin_redondear"]], on=CLAVES, how="left",
                               validate="one_to_one")
    else:
        salida = rejilla.assign(prevision_sin_redondear=np.nan)
    claves = list(zip(salida["store_id"], salida["dept_id"]))
    salida["motivo"] = pd.Series([motivo_obj.get(k) for k in claves], index=salida.index, dtype="object")
    salida["aviso"] = pd.Series([avisos.get(k) for k in claves], index=salida.index, dtype="object")
    salida["prevision"] = pp.redondear_salida(salida["prevision_sin_redondear"], objetivo)
    return salida.assign(objetivo=objetivo, origen=origen)[COLUMNAS_SALIDA]


# ══ 5. Principal ════════════════════════════════════════════════════════════════
def principal(args):
    """Carga, comprueba, prevé y guarda; devuelve el código de salida."""
    raiz = Path(args.raiz).resolve()
    configuracion = json.loads((raiz / CONFIGURACION_REL).read_text(encoding="utf-8"))
    pp = importar_modulo(raiz, configuracion)
    origen = pd.Timestamp(args.origen)
    horizontes = {o: int(configuracion["horizontes"][o]) for o in OBJETIVOS}
    historia_minima = int(configuracion["historia_minima_dias"])

    # 5.1 El modelo: el que está en uso o, como ensayo, el que se pasa a mano; solo si cuadra su ficha
    en_uso = configuracion.get("modelo_en_uso")
    carpeta_modelos = ruta_de(raiz, args.modelos) if args.modelos else (ruta_de(raiz, en_uso) if en_uso else None)
    if carpeta_modelos is None:
        raise Parada("no hay modelo en uso: lo aprueba el responsable del caso en produccion/configuracion.json; para un ensayo, pásalo "
                     "con --modelos")
    modelos, fichas = {}, {}
    for o in OBJETIVOS:
        modelos[o], fichas[o] = pp.cargar_modelo(carpeta_modelos / f"{o}.joblib")

    # 5.2 Las entradas, la del día que toca, la historia y lo que se sabe de antemano
    rutas = {"venta": Path(args.venta), "precios": Path(args.precios), "calendario": Path(args.calendario)}
    venta, precios, calendario = leer_entradas(pp, rutas)
    columnas_historia, ultimo = dias_de_la_historia(pp, venta, calendario, origen, historia_minima)
    dias_futuro = [origen + pd.Timedelta(h, "D") for h in range(1, max(horizontes.values()) + 1)]
    faltan = [f"{d:%Y-%m-%d}" for d in dias_futuro if d not in set(calendario[COLUMNA_FECHA])]
    if faltan:
        raise Parada(f"el calendario no llega a los días a prever: faltan {faltan[:5]}")
    comprobar_precios(pp, precios, calendario, dias_futuro)
    dim_producto, dim_tienda = pp.dimensiones(venta)
    historia = pp.venta_por_serie(venta, precios, calendario, dim_producto, columnas_historia)
    series = venta[CLAVE_SERIE].drop_duplicates().reset_index(drop=True)
    por_semana = pp.precio_y_productos_por_semana(precios, dim_producto, calendario)
    futuro = pp.tabla_del_futuro(series, dias_futuro, calendario, dim_tienda, por_semana)

    # 5.3 Las series que no se pueden prever, con su motivo (no se quitan: salen vacías)
    incompletas = historia.groupby(CLAVE_SERIE)["unidades"].apply(lambda s: bool(s.isna().any() or
                                                                                 len(s) != historia_minima))
    motivos = {}
    for o, h in horizontes.items():
        motivos[o] = {k: f"sin los {historia_minima} días de historia que acaban en el origen"
                      for k, mala in incompletas.items() if mala}
        del_h = futuro[futuro[COLUMNA_FECHA].isin(dias_futuro[:h]).to_numpy()]
        sin_precio = del_h.loc[del_h["precio_medio_semana_anterior"].isna().to_numpy(), CLAVE_SERIE].drop_duplicates()
        for k in map(tuple, sin_precio.to_numpy().tolist()):
            motivos[o].setdefault(k, "sin el precio medio de la semana anterior en algún día a prever")

    # 5.4 Prever cada objetivo
    partes = [prever_objetivo(pp, modelos[o], o, horizontes[o], origen, series, historia, futuro, motivos)
              for o in OBJETIVOS]
    salida = pd.concat(partes, ignore_index=True)

    # 5.5 Comprobaciones, calculadas con lo ejecutado
    esperadas = {o: len(series) * horizontes[o] for o in OBJETIVOS}
    filas = {o: int((salida["objetivo"] == o).sum()) for o in OBJETIVOS}
    vacias = salida["prevision"].isna()
    pasos, llamadas = pasos_que_quitan_filas_aqui()
    validaciones = {
        "filas_ejecucion": all(filas[o] == esperadas[o] for o in OBJETIVOS)
                           and not salida.duplicated(["objetivo"] + CLAVES).any(),
        "ficha_cuadra": all(f.get("huella") == pp.huella(carpeta_modelos / f"{o}.joblib") for o, f in fichas.items()),
        "periodo_que_toca": bool(ultimo == origen),
        "sin_vacias_sin_motivo": bool((salida.loc[vacias.to_numpy(), "motivo"].notna()).all()),
        "sin_negativas": bool((salida.loc[(~vacias).to_numpy(), "prevision"] >= 0).all()),
        "sin_pasos_que_quitan_filas": bool(pasos) and not llamadas}
    if not all(validaciones.values()):
        raise Parada(f"comprobaciones en rojo: {[k for k, v in validaciones.items() if not v]}")

    # 5.6 Guardar: si ese día ya había una ejecución, se copia antes a _archivo
    carpeta = ruta_de(raiz, configuracion["rutas"]["predicciones"]) / args.fecha
    if carpeta.exists():
        archivo = carpeta.parent / "_archivo" / f"{args.fecha}_{datetime.now():%H%M%S%f}"
        shutil.copytree(carpeta, archivo)
    carpeta.mkdir(parents=True, exist_ok=True)
    salida.to_parquet(carpeta / "previsiones.parquet", index=False)
    en_uso_ruta = ruta_de(raiz, en_uso).resolve() if en_uso else None
    resumen = {
        "script": SCRIPT_REL, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "ensayo": bool(args.ensayo), "origen": origen, "fecha_datos": ultimo,
        "modelo": {"carpeta": str(carpeta_modelos), "en_uso": en_uso_ruta == carpeta_modelos.resolve(),
                   "huellas": {o: f["huella"] for o, f in fichas.items()},
                   "contrato": fichas["unidades"].get("contrato")},
        "entradas": [{"ruta": str(r), "sha256": pp.huella(r)} for r in rutas.values()],
        "filas": {o: {"series": len(series), "horizonte": horizontes[o], "esperadas": esperadas[o], "salida": filas[o],
                      "con_prevision": int(((salida["objetivo"] == o) & ~vacias).sum()),
                      "sin_prevision": salida.loc[(salida["objetivo"] == o).to_numpy() & vacias.to_numpy(), "motivo"]
                      .value_counts().to_dict(),
                      "con_aviso": int(((salida["objetivo"] == o) & salida["aviso"].notna()).sum())}
                  for o in OBJETIVOS},
        "validaciones": validaciones, "pasos_que_quitan_filas_llamados": llamadas,
        "salida": "previsiones.parquet", "estado": "OK"}
    (carpeta / "resumen.json").write_text(json.dumps(a_json(resumen), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK · origen {origen:%Y-%m-%d}; " + "; ".join(
        f"{o}: {filas[o]} filas ({resumen['filas'][o]['con_prevision']} con previsión)" for o in OBJETIVOS)
        + f"; guardado en {carpeta}")
    return 0


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Ejecución diaria de la previsión")
    argumentos.add_argument("--venta", required=True, help="venta por producto y tienda, un día por columna (CSV)")
    argumentos.add_argument("--precios", required=True, help="precios por producto, tienda y semana (CSV)")
    argumentos.add_argument("--calendario", required=True, help="calendario con la forma de data/raw/ (CSV)")
    argumentos.add_argument("--origen", required=True, help="último día con venta conocida, AAAA-MM-DD")
    argumentos.add_argument("--modelos", default=None, help="carpeta de los modelos; por defecto, el modelo en uso")
    argumentos.add_argument("--ensayo", action="store_true", help="marca la ejecución como ensayo en el resumen")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    argumentos.add_argument("--fecha", default=datetime.now().strftime("%Y-%m-%d"), help="carpeta de la ejecución")
    print("intérprete:", sys.executable)
    try:
        codigo = principal(argumentos.parse_args())
    except (Parada, ValueError, RuntimeError) as parada:  # para con un mensaje claro y sin escribir previsiones
        print(f"PARA · {parada}")
        codigo = 1
    except Exception:  # un fallo técnico, con su traza
        traceback.print_exc()
        codigo = 1
    sys.exit(codigo)
