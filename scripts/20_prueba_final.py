"""Prueba final del caso 69: los dos modelos de previsión medidos una vez en el año guardado, frente a las tres reglas.

Aplica el guion del paso 7, apartado 2 («Lo que se mide», fijado antes de abrir el año), con las medidas de reglas, apartado 6
y la regla de ganar de reglas, apartado 7, las mismas que scripts/16_validacion.py. Lee las previsiones que dejó
produccion/ejecutar.py en data/processed/prueba_final/<variante>/<origen>/ (el lote, petición 28, tarea 1; se rehace
desde el caso con produccion/lote_prueba_final.py, petición 29) y la venta real de data/raw/ y data/raw/reserva/, que no
cambia. Lo que hace, en este orden:
  1. la venta real de cada serie y día, sumada aquí desde los productos (unidades, y céntimos por el precio de su
     semana), con el 25 de diciembre y los cierres de tienda fuera del error; se comprueba contra las tablas del
     desarrollo en los días que ellas tienen;
  2. lo que se sabe de antemano de cada día del año guardado (calendario, SNAP, eventos de la lista del
     entrenamiento, precio medio y productos de la semana anterior, día del mes), con la forma de
     data/processed/hechos_modelo_validacion.parquet: es la tabla de historia de la prueba por otro camino
     (tests/comprobar_produccion_por_otro_camino.py). Se comprueba contra esa tabla en los días de la validación;
  3. lee el lote de cada variante y para si una previsión usa un día posterior a su origen, si falta un origen, una
     serie o un día, si una fila llega sin previsión o negativa, o si no casa por serie y fecha con la venta real;
  4. desde cada origen, las tres reglas y el suavizado exponencial con la venta real hasta el origen
     (prevision_recursiva.reglas_sencillas y la función del script 16), unidos a la previsión por serie y fecha;
  5. en los 13 orígenes ordinarios (unidades a 10 días, dólares a 28), el veredicto de reglas, apartado 7 con las funciones del
     script 16: orígenes que gana frente a la regla que menos falla en cada uno (10 de 13) e intervalo del 95 % de la
     ventaja remuestreando las 70 series enteras 1.000 veces con semilla 42; al lado, el sesgo, el suavizado, el error
     por departamento y por tienda con la recomendación de cada departamento y la previsión sumada;
  6. en las tres vísperas de festivo, solo unidades, el error del modelo y de las reglas, al lado;
  7. la medida rehecha sobre data/processed/previsiones_validacion.parquet tiene que dar las cifras de
     informes/validacion.json: así se comprueba que se mide igual que en la validación;
  8. el reentrenado (--reentrenado), medido igual; sus cifras van al lado y a la ficha del reentreno
     (reentreno.json, comparacion_con_el_en_uso).
Con lo que se ve en el año guardado no se ajusta nada: el modelo no se toca. Para en la puerta del responsable del caso: él decide si
el modelo se confirma y cuál pasa a uso.

Importa scripts/16_validacion.py para usar sus funciones: su trabajo está bajo __main__ y al importarlo solo define
constantes y funciones (error 1). Depende de lo que dejan ejecutar.py (el lote) y reentrenar.py (error 2).

Deja informes/prueba_final.json, data/processed/previsiones_prueba_final.parquet y
data/processed/prueba_final/hechos_prueba_final.parquet.

Uso: python -W error scripts/20_prueba_final.py [--reentrenado CARPETA] [--raiz CARPETA]
Sale con 0 si para en la puerta del responsable del caso con todas las comprobaciones en verde y con 1 si no.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import importlib.util
import json
import math
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
sys.path.insert(0, str(CASO / "assets"))
import prevision_recursiva as pr  # noqa: E402


def _importar_validacion():
    """scripts/16_validacion.py como módulo: solo define constantes y funciones al importarse."""
    spec = importlib.util.spec_from_file_location("validacion_16", CASO / "scripts" / "16_validacion.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


V16 = _importar_validacion()

SCRIPT_REL = "scripts/20_prueba_final.py"
VERSION_METODO = "20/11/2026"  # versión del método preproduccion con que se escribió este script
# La fecha de referencia de los datos (reglas, apartado 5): la misma clave en todos los JSON del caso
FECHA_DATOS = "2015-05-22"
FIN_PRUEBA_FINAL = "2016-05-22"
JSON_REL = "informes/prueba_final.json"
PARQUET_REL = "data/processed/previsiones_prueba_final.parquet"
LOTE_REL = "data/processed/prueba_final"
HECHOS_PF_REL = "data/processed/prueba_final/hechos_prueba_final.parquet"
VALIDACION_JSON_REL = "informes/validacion.json"
PREV_VALIDACION_REL = "data/processed/previsiones_validacion.parquet"
SERIES_ENT_REL = "data/processed/hechos_series_entrenamiento.parquet"
SERIES_VAL_REL = "data/processed/hechos_series_validacion.parquet"
MODELO_VAL_REL = "data/processed/hechos_modelo_validacion.parquet"
MODELO_ENT_REL = "data/processed/hechos_modelo_entrenamiento.parquet"
DIM_PRODUCTO_REL = "data/processed/dim_producto.parquet"
DIM_TIENDA_REL = "data/processed/dim_tienda.parquet"
RAW = {"venta": "data/raw/sales_train_evaluation.csv", "precios": "data/raw/sell_prices.csv",
       "calendario": "data/raw/calendar.csv", "venta_reserva": "data/raw/reserva/sales_train_evaluation.csv",
       "precios_reserva": "data/raw/reserva/sell_prices.csv"}
CANDIDATO_REL = "modelos/reentrenos/2026-11-25"

COLUMNA_FECHA = "date"
CLAVE_SERIE = ["store_id", "dept_id"]
CLAVES = CLAVE_SERIE + [COLUMNA_FECHA]
REGLAS = pr.REGLAS
OBJETIVOS = ("unidades", "dolares")
# Guion del paso 7, apartado 2: 13 orígenes cada 28 días desde el 22/05/2015 y tres vísperas de festivo en unidades
HORIZONTES = {"unidades": 10, "dolares": 28}
PRIMER_ORIGEN = pd.Timestamp("2015-05-22")
N_ORIGENES = 13
PASO_ORIGENES = 28
FESTIVOS = {"Acción de Gracias": pd.Timestamp("2015-11-25"), "Navidad": pd.Timestamp("2015-12-24"),
            "Año Nuevo": pd.Timestamp("2015-12-31")}
# Reglas, apartado 5: un producto cuenta en el precio medio si ya tenía precio cuatro semanas antes
SEMANAS_PREVIAS_CON_PRECIO = 4
SNAP_DE_ESTADO = {"CA": "snap_CA", "TX": "snap_TX", "WI": "snap_WI"}
# Tolerancia de las comparaciones con las cifras ya guardadas
TOLERANCIA = 1e-9
# Las columnas de la tabla de historia que se comprueban contra la del desarrollo
COLUMNAS_COMPROBADAS = ["unidades", "dolares", "fuera_del_error", "cierre_tienda", "snap", "weekday", "month",
                        "event_name_1", "event_name_2", "wm_yr_wk_anterior", "precio_medio_semana_anterior",
                        "productos_con_precio_semana_anterior", "dia_del_mes"]
NOMBRE = V16.NOMBRE


class Parada(Exception):
    """La prueba final para: el lote o la venta real no permiten medir sin engañarse."""


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_fecha(serie):
    """Fechas con la misma unidad en todas las tablas, para que las uniones casen."""
    return pd.to_datetime(serie).astype("datetime64[us]")


def rotular(obj, de="validacion:", a="prueba_final:"):
    """Cambia el rótulo de filas de las funciones del script 16 («validacion: N filas») por el de la prueba final."""
    if isinstance(obj, dict):
        return {k: rotular(v, de, a) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rotular(v, de, a) for v in obj]
    if isinstance(obj, str) and obj.startswith(de):
        return a + obj[len(de):]
    return obj


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def origenes_ordinarios():
    """Los 13 orígenes de la prueba final, cada 28 días desde el 22/05/2015."""
    return [PRIMER_ORIGEN + pd.Timedelta(PASO_ORIGENES * i, "D") for i in range(N_ORIGENES)]


# ══ 3. La venta real y lo que se sabe de antemano ════════════════════════════════
def preparar_calendario(calendario):
    """El calendario por orden de fechas, con la fecha leída con su formato y la semana anterior por ese orden."""
    cal = calendario.copy()
    cal[COLUMNA_FECHA] = a_fecha(pd.to_datetime(cal[COLUMNA_FECHA], format="%Y-%m-%d"))
    cal = cal.sort_values(COLUMNA_FECHA, kind="stable").reset_index(drop=True)
    orden = list(dict.fromkeys(int(w) for w in cal["wm_yr_wk"]))
    anterior = dict(zip(orden[1:], orden[:-1]))
    cal["wm_yr_wk_anterior"] = cal["wm_yr_wk"].map(anterior).astype("Int64")
    return cal, orden


def venta_real_por_serie(venta, precios, calendario):
    """La venta real de cada serie y día, sumada desde los productos de una venta con la forma de data/raw/.

    Unidades: la suma de las del departamento en la tienda. Dólares: la suma de unidades por el precio de su semana en
    céntimos enteros, pasada a dólares con dos decimales (reglas, apartado 5). Un día con venta y sin precio para. Marca
    cierre_tienda (toda la tienda a cero ese día) y fuera_del_error (el 25 de diciembre o un cierre, reglas, apartado 6).
    Devuelve store_id, dept_id, date, unidades, dolares, cierre_tienda y fuera_del_error, ordenada por la clave.
    """
    cal, orden = preparar_calendario(calendario)
    fecha_de = dict(zip(cal["d"], cal[COLUMNA_FECHA]))
    semana_de = dict(zip(cal["d"], cal["wm_yr_wk"]))
    dias = [c for c in venta.columns if str(c).startswith("d_")]
    fuera_cal = [d for d in dias if d not in fecha_de]
    if fuera_cal:
        raise Parada(f"días de la venta que no están en el calendario: {fuera_cal[:3]}")
    unidades = venta[dias].to_numpy(dtype="float64")
    if np.isnan(unidades).any() or (unidades < 0).any():
        raise Parada("la venta trae días vacíos o negativos: el trabajo para (reglas, apartado 5)")
    # El precio de cada producto y tienda en la semana de cada día, en una matriz producto × semana
    fila_de = {k: i for i, k in enumerate(zip(venta["store_id"], venta["item_id"]))}
    semana_pos = {w: i for i, w in enumerate(orden)}
    matriz = np.full((len(venta), len(orden)), np.nan)
    filas = [fila_de.get(k) for k in zip(precios["store_id"], precios["item_id"])]
    dentro = np.array([f is not None for f in filas])
    semanas = precios["wm_yr_wk"].map(semana_pos).to_numpy()
    matriz[np.array([f for f in filas if f is not None], dtype=int), semanas[dentro].astype(int)] = \
        precios["sell_price"].to_numpy(dtype="float64")[dentro]
    precio_dia = matriz[:, [semana_pos[semana_de[d]] for d in dias]]
    sin_precio = np.isnan(precio_dia)
    if (sin_precio & (unidades > 0)).any():
        raise Parada(f"{int((sin_precio & (unidades > 0)).sum())} días con venta y sin precio: el trabajo para "
                     "(reglas, apartado 5)")
    centimos = unidades * np.where(sin_precio, 0.0, np.rint(np.nan_to_num(precio_dia) * 100))
    # De producto a serie: la suma de cada departamento en cada tienda y día
    grupos = [venta["store_id"].to_numpy(), venta["dept_id"].to_numpy()]
    suma_u = pd.DataFrame(unidades, columns=dias).groupby(grupos, sort=True).sum()
    suma_c = pd.DataFrame(centimos, columns=dias).groupby(grupos, sort=True).sum()
    largo = suma_u.stack().rename("unidades").to_frame().join(suma_c.stack().rename("centimos"))
    largo.index.names = ["store_id", "dept_id", "d"]
    t = largo.reset_index()
    t[COLUMNA_FECHA] = a_fecha(t["d"].map(fecha_de))
    t["dolares"] = np.round(t["centimos"].to_numpy() / 100, 2)
    t["cierre_tienda"] = t.groupby(["store_id", COLUMNA_FECHA])["unidades"].transform("sum").to_numpy() == 0
    navidad = (t[COLUMNA_FECHA].dt.month == 12).to_numpy() & (t[COLUMNA_FECHA].dt.day == 25).to_numpy()
    t["fuera_del_error"] = navidad | t["cierre_tienda"].to_numpy()
    t = t.sort_values(CLAVES, kind="stable").reset_index(drop=True)
    return t[CLAVES + ["unidades", "dolares", "cierre_tienda", "fuera_del_error"]]


def precio_y_productos(venta, precios, orden):
    """Por tienda, departamento y semana: el precio medio simple y cuántos productos cuentan (reglas, apartado 5).

    Cuenta un producto con precio esa semana si ya lo tenía cuatro semanas antes, con las semanas en el orden de sus
    fechas; la primera semana de cada producto en su tienda se toma de todos los precios que llegan.
    """
    dept = venta[["item_id", "dept_id"]].drop_duplicates()
    con = precios.merge(dept, on="item_id", how="inner", validate="many_to_one")
    pos = con["wm_yr_wk"].map({w: i for i, w in enumerate(orden)})
    primera = pos.groupby([con["store_id"], con["item_id"]], sort=False).transform("min")
    cuenta = (pos - primera) >= SEMANAS_PREVIAS_CON_PRECIO
    return (con.assign(_precio=con["sell_price"].where(cuenta), _cuenta=cuenta.astype("int64"))
            .groupby(["store_id", "dept_id", "wm_yr_wk"], sort=True)
            .agg(precio_medio_semana_anterior=("_precio", "mean"),
                 productos_con_precio_semana_anterior=("_cuenta", "sum")).reset_index())


def lo_que_se_sabe(real, venta, precios, calendario, eventos, desde, hasta):
    """La venta real de los días entre desde y hasta con lo que se sabe de antemano de cada uno.

    Tiene la forma de data/processed/hechos_modelo_validacion.parquet sin los retardos: calendario, SNAP del estado de
    la tienda, una columna evento_<nombre> por evento de la lista del entrenamiento, precio medio y productos de la
    semana anterior y día del mes. Es la tabla de historia de la prueba por otro camino.
    """
    cal, orden = preparar_calendario(calendario)
    dias = real[(real[COLUMNA_FECHA] >= desde).to_numpy() & (real[COLUMNA_FECHA] <= hasta).to_numpy()]
    columnas_cal = ["d", COLUMNA_FECHA, "wm_yr_wk", "wm_yr_wk_anterior", "weekday", "wday", "month", "year",
                    "event_name_1", "event_type_1", "event_name_2", "event_type_2"] + list(SNAP_DE_ESTADO.values())
    t = dias.merge(cal[columnas_cal], on=COLUMNA_FECHA, how="left", validate="many_to_one")
    tiendas = venta[["store_id", "state_id"]].drop_duplicates()
    depts = venta[["dept_id", "cat_id"]].drop_duplicates()
    t = t.merge(tiendas, on="store_id", how="left", validate="many_to_one")
    t = t.merge(depts, on="dept_id", how="left", validate="many_to_one")
    t["snap"] = np.select([t["state_id"].to_numpy() == e for e in SNAP_DE_ESTADO],
                          [t[c].to_numpy() for c in SNAP_DE_ESTADO.values()], default=-1).astype("int64")
    t = t.drop(columns=list(SNAP_DE_ESTADO.values()))
    semana = precio_y_productos(venta, precios, orden).rename(columns={"wm_yr_wk": "wm_yr_wk_anterior"})
    semana["wm_yr_wk_anterior"] = semana["wm_yr_wk_anterior"].astype("Int64")
    t = t.merge(semana, on=["store_id", "dept_id", "wm_yr_wk_anterior"], how="left", validate="many_to_one")
    sin = t["productos_con_precio_semana_anterior"].isna().to_numpy()
    t.loc[sin, "productos_con_precio_semana_anterior"] = 0
    t["productos_con_precio_semana_anterior"] = t["productos_con_precio_semana_anterior"].astype("int64")
    for nombre in eventos:
        t[f"evento_{nombre}"] = ((t["event_name_1"] == nombre).fillna(False).to_numpy()
                                 | (t["event_name_2"] == nombre).fillna(False).to_numpy()).astype("int64")
    t["dia_del_mes"] = t[COLUMNA_FECHA].dt.day.astype("int64")
    return t.sort_values(CLAVES, kind="stable").reset_index(drop=True)


def comparar_tablas(mia, otra, columnas):
    """Las columnas que no coinciden entre dos tablas con las mismas claves: números con la tolerancia, el resto
    igual, los vacíos con los vacíos. Devuelve las filas comunes, las que faltan a un lado y las columnas distintas."""
    a = mia[CLAVES + columnas].copy()
    b = otra[CLAVES + columnas].copy()
    b[COLUMNA_FECHA] = a_fecha(b[COLUMNA_FECHA])
    unido = a.merge(b, on=CLAVES, how="outer", suffixes=("", "_otra"), validate="one_to_one", indicator=True)
    distintas = []
    ambos = unido[(unido["_merge"] == "both").to_numpy()]
    for c in columnas:
        x, y = ambos[c], ambos[f"{c}_otra"]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y) and not pd.api.types.is_bool_dtype(x):
            xv, yv = x.astype("float64").to_numpy(), y.astype("float64").to_numpy()
            bien = (np.isnan(xv) & np.isnan(yv)) | (np.abs(xv - yv) <= TOLERANCIA)
        else:
            bien = (x.isna().to_numpy() & y.isna().to_numpy()) | (x.astype("object") == y.astype("object")).to_numpy()
        if not bien.all():
            distintas.append({"columna": c, "filas": int((~bien).sum())})
    return {"filas_comunes": int(len(ambos)), "solo_aqui": int((unido["_merge"] == "left_only").sum()),
            "solo_en_desarrollo": int((unido["_merge"] == "right_only").sum()), "columnas_distintas": distintas,
            "igual": len(distintas) == 0 and len(ambos) == len(otra)}


# ══ 4. El lote ══════════════════════════════════════════════════════════════════
def leer_lote(carpeta, pruebas, horizontes, series):
    """Las previsiones del lote de cada origen, comprobadas antes de medir; para con Parada si algo no cuadra.

    carpeta: data/processed/prueba_final/<variante>, con una subcarpeta AAAA-MM-DD por origen (previsiones.parquet y
    resumen.json de ejecutar.py). pruebas: [{"prueba", "origen", "objetivos"}]. Para si falta un origen, si la venta
    que vio ejecutar.py llega más allá del origen, si un día previsto no va detrás de su origen, si falta o sobra una
    serie o un día, si hay claves repetidas o si una fila llega sin previsión o negativa. Devuelve prueba, objetivo,
    origen, store_id, dept_id, date, h y modelo (la previsión sin redondear).
    """
    carpeta = Path(carpeta)
    partes = []
    for p in pruebas:
        origen = pd.Timestamp(p["origen"])
        sub = carpeta / f"{origen:%Y-%m-%d}"
        if not (sub / "previsiones.parquet").exists() or not (sub / "resumen.json").exists():
            raise Parada(f"falta el origen {origen:%Y-%m-%d} en {carpeta.name}: no está su previsión o su resumen")
        resumen = json.loads((sub / "resumen.json").read_text(encoding="utf-8"))
        vio = pd.Timestamp(resumen.get("fecha_datos"))
        if vio > origen:
            raise Parada(f"la previsión del origen {origen:%Y-%m-%d} se hizo con la venta hasta el {vio:%Y-%m-%d}, "
                         "posterior a su origen")
        if vio < origen:
            raise Parada(f"la previsión del origen {origen:%Y-%m-%d} se hizo con la venta hasta el {vio:%Y-%m-%d}: "
                         "no llega a su origen")
        tabla = pd.read_parquet(sub / "previsiones.parquet")
        tabla[COLUMNA_FECHA] = a_fecha(tabla[COLUMNA_FECHA])
        tabla["origen"] = a_fecha(tabla["origen"])
        if (tabla["origen"] != origen).any():
            raise Parada(f"la carpeta del origen {origen:%Y-%m-%d} trae previsiones de otro origen")
        for objetivo in p["objetivos"]:
            h = horizontes[objetivo]
            de = tabla[(tabla["objetivo"] == objetivo).to_numpy()]
            if (de[COLUMNA_FECHA] <= origen).any():
                raise Parada(f"{objetivo}, origen {origen:%Y-%m-%d}: un día previsto no va detrás de su origen")
            if de[CLAVES].duplicated().any():
                raise Parada(f"{objetivo}, origen {origen:%Y-%m-%d}: claves de serie y fecha repetidas")
            esperadas = {(s[0], s[1], origen + pd.Timedelta(k, "D")) for s in series for k in range(1, h + 1)}
            llegan = set(zip(de["store_id"], de["dept_id"], de[COLUMNA_FECHA]))
            if llegan != esperadas:
                raise Parada(f"{objetivo}, origen {origen:%Y-%m-%d}: el lote no trae todas las series y días del "
                             f"horizonte (faltan {len(esperadas - llegan)}, sobran {len(llegan - esperadas)})")
            valores = de["prevision_sin_redondear"].to_numpy(dtype="float64")
            if np.isnan(valores).any():
                raise Parada(f"{objetivo}, origen {origen:%Y-%m-%d}: {int(np.isnan(valores).sum())} filas sin previsión")
            if (valores < 0).any():
                raise Parada(f"{objetivo}, origen {origen:%Y-%m-%d}: {int((valores < 0).sum())} previsiones negativas")
            partes.append(de[CLAVES + ["h"]].assign(prueba=p["prueba"], objetivo=objetivo, origen=origen,
                                                     modelo=valores))
    return pd.concat(partes, ignore_index=True)


# ══ 5. Las reglas, el suavizado y la tabla que se mide ═══════════════════════════
def armar_objetivo(lote, real, objetivo, origenes, horizonte, prueba, con_suavizado=True, cache=None):
    """Por cada origen: la venta real del horizonte, la previsión del lote, las tres reglas y el suavizado, unidos por
    serie y fecha; las previsiones, acotadas en cero y, en unidades, redondeadas, como se miden.

    Las reglas y el suavizado usan solo la venta real hasta el origen (las funciones la cortan ahí). Para si la
    previsión no casa por serie y fecha con la venta real. cache: un diccionario para no repetir el suavizado de un
    origen entre dos variantes.
    """
    cache = {} if cache is None else cache
    historia = real[CLAVES + [objetivo]]
    partes = []
    for numero, origen in enumerate(origenes, start=1):
        origen = pd.Timestamp(origen)
        dias = [origen + pd.Timedelta(k, "D") for k in range(1, horizonte + 1)]
        base = real[real[COLUMNA_FECHA].isin(dias).to_numpy()][CLAVES + [objetivo, "fuera_del_error"]]
        del_lote = lote[((lote["objetivo"] == objetivo) & (lote["origen"] == origen)
                         & (lote["prueba"] == prueba)).to_numpy()][CLAVES + ["modelo"]]
        clave = (objetivo, origen, horizonte)
        if clave not in cache:
            reglas = pr.reglas_sencillas(historia, objetivo, origen, horizonte).drop(columns="h")
            reglas[COLUMNA_FECHA] = a_fecha(reglas[COLUMNA_FECHA])
            suav, bien = None, None
            if con_suavizado:
                suav, registro = V16.prever_suavizado(historia, objetivo, origen, horizonte)
                suav[COLUMNA_FECHA] = a_fecha(suav[COLUMNA_FECHA])
                suav = suav.drop(columns="h")
                bien = V16.suavizado_sin_futuro(registro, origen)
            cache[clave] = (reglas, suav, bien)
        reglas, suav, bien = cache[clave]
        previsiones = {"modelo": del_lote, "reglas": reglas}
        if suav is not None:
            previsiones["suavizado"] = suav
        try:
            tabla = V16.unir_previsiones(base, previsiones)
        except ValueError as error:
            raise Parada(f"{objetivo}, origen {origen:%Y-%m-%d}: la previsión no casa por serie y fecha con la venta "
                         f"real ({error})") from error
        partes.append(tabla.assign(origen=origen, numero_origen=numero, prueba=prueba,
                                   h=(tabla[COLUMNA_FECHA] - origen).dt.days.astype("int64"),
                                   suavizado_sin_futuro=bien))
    tabla = pd.concat(partes, ignore_index=True)
    for p in ["modelo", *REGLAS] + (["suavizado"] if con_suavizado else []):
        tabla[p] = V16.previsto_medible(tabla[p], objetivo)
    return tabla


# ══ 6. La medida (reglas, apartado 6 y §7, con las funciones del script 16) ═══════════════
def predictores_de(tabla):
    """Las previsiones que trae la tabla: el modelo, las tres reglas y, si está, el suavizado."""
    return ["modelo", *REGLAS] + (["suavizado"] if "suavizado" in tabla.columns else [])


def medir_ordinaria(tabla, objetivo, origenes, series, padres):
    """El veredicto de reglas, apartado 7 y lo que va al lado, sobre los días medidos (sin el 25 de diciembre ni los cierres)."""
    medidas = V16.filas_medidas(tabla)
    pred = predictores_de(tabla)
    errores = {"todas": V16.errores_por_grupo(medidas, objetivo, pred),
               "por_origen": V16.errores_por_grupo(medidas, objetivo, pred, "origen"),
               "por_departamento": V16.errores_por_grupo(medidas, objetivo, pred, "dept_id"),
               "por_tienda": V16.errores_por_grupo(medidas, objetivo, pred, "store_id")}
    sumas = V16.sumas_por_serie_y_origen(medidas, objetivo, pred, series, list(origenes))
    frente = V16.prueba_de_ganar(sumas, list(REGLAS), len(origenes), series)
    pesos = frente.pop("_pesos")
    otro = V16.ventaja_por_otro_camino(medidas, objetivo, REGLAS)
    resultado = {
        "horizonte": int(tabla["h"].max()), "origenes": [pd.Timestamp(o) for o in origenes],
        "filas_previstas": len(tabla), "filas_medidas": len(medidas),
        "filas_fuera_del_error": int(tabla["fuera_del_error"].sum()),
        "dias_fuera_del_error": sorted({f"{d:%Y-%m-%d}" for d in tabla.loc[tabla["fuera_del_error"].to_numpy(dtype=bool),
                                                                         COLUMNA_FECHA]}),
        "errores": errores, "veredicto": frente,
        "exceso": {"que_es": "el sesgo de reglas, apartado 6: positivo si la previsión se pasa, en cada 100 vendidos",
                   "valores": {e["prevision"]: e["sesgo"] for e in errores["todas"]}},
        "ventaja_por_otro_camino": otro,
        "recomendacion_por_departamento": V16.recomendacion_por_departamento(medidas, objetivo),
        "suavizado": None, "niveles": None}
    if "suavizado" in tabla.columns:
        suav = V16.prueba_de_ganar(sumas, ["suavizado"], len(origenes), series)
        suav.pop("_pesos")
        suav["lectura"] = suav.pop("veredicto")
        resultado["suavizado"] = suav
        resultado["niveles"] = V16.previsiones_sumadas(medidas, objetivo, padres)
    resultado["control"] = {
        "ventaja_otro_camino": bool(np.isclose(otro, frente["ventaja"], rtol=0, atol=TOLERANCIA)),
        "intervalo_por_entidad": V16.remuestreo_por_entidad(pesos, len(series)),
        "sin_dias_fuera": V16.sin_dias_fuera_del_error(medidas),
        "completa": bool(tabla[pred].notna().all().all()),
        "suavizado_sin_futuro": (None if "suavizado_sin_futuro" not in tabla.columns
                                 or tabla["suavizado_sin_futuro"].isna().all()
                                 else bool(tabla["suavizado_sin_futuro"].astype(bool).all()))}
    return resultado


def medir_festivos(tabla, objetivo, nombres):
    """En cada víspera de festivo, el error y el sesgo del modelo y de las reglas, y la regla que menos falla."""
    medidas = V16.filas_medidas(tabla)
    pred = predictores_de(tabla)
    por_origen = []
    for origen, g in medidas.groupby("origen", sort=True):
        errores = V16.errores_por_grupo(g, objetivo, pred)
        por = {e["prevision"]: e for e in errores}
        mejor = min(REGLAS, key=lambda r: (por[r]["error"], r))
        por_origen.append({"festivo": nombres.get(pd.Timestamp(origen)), "origen": origen,
                           "dias": [f"{d:%Y-%m-%d}" for d in sorted(g[COLUMNA_FECHA].unique())],
                           "errores": errores, "error_modelo": por["modelo"]["error"],
                           "sesgo_modelo": por["modelo"]["sesgo"], "regla_que_menos_falla": mejor,
                           "regla_que_menos_falla_nombre": NOMBRE[mejor], "error_regla": por[mejor]["error"],
                           "modelo_falla_menos": bool(por["modelo"]["error"] < por[mejor]["error"])})
    return {"que_es": "las tres vísperas de festivo, solo unidades, a 10 días; se miran al lado, sin decidir con ellas",
            "filas_previstas": len(tabla), "filas_medidas": len(medidas),
            "dias_fuera_del_error": sorted({f"{d:%Y-%m-%d}" for d in tabla.loc[
                tabla["fuera_del_error"].to_numpy(dtype=bool), COLUMNA_FECHA]}),
            "todas": V16.errores_por_grupo(medidas, objetivo, pred), "por_origen": por_origen}


def resumen_veredicto(bloque):
    """Las cifras del veredicto que se ponen al lado: orígenes, ventaja, intervalo, errores y sesgo."""
    v = bloque["veredicto"]
    sesgos = {e["prevision"]: e["sesgo"] for e in bloque["errores"]["todas"]}
    return {"veredicto": v["veredicto"], "origenes_que_gana": v["origenes_que_gana"], "de": v["de"],
            "minimo": v["minimo"], "ventaja": v["ventaja"], "intervalo_bajo": v["intervalo"]["bajo"],
            "intervalo_alto": v["intervalo"]["alto"], "error_modelo": v["error_modelo"],
            "error_regla_que_menos_falla": v["error_rival"], "sesgo_modelo": sesgos.get("modelo"),
            "sesgo_reglas": {r: sesgos.get(r) for r in REGLAS}}


# ══ 7. Medir igual que la validación ═════════════════════════════════════════════
def medida_de_la_validacion(prev_validacion, validacion, padres):
    """La medida de este script sobre las previsiones guardadas de la validación, frente a informes/validacion.json.

    Si sale igual en los dos objetivos (orígenes que gana, ventaja, intervalo, errores y el suavizado), este script
    mide como el 16. Devuelve las diferencias y si coincide.
    """
    salida, iguales = {}, []
    for objetivo in OBJETIVOS:
        t = prev_validacion[(prev_validacion["objetivo"] == objetivo).to_numpy()].rename(columns={"real": objetivo})
        t[COLUMNA_FECHA] = a_fecha(t[COLUMNA_FECHA])
        t["origen"] = a_fecha(t["origen"])
        origenes = sorted(t["origen"].unique())
        series = sorted(map(tuple, t[CLAVE_SERIE].drop_duplicates().to_numpy().tolist()))
        r = medir_ordinaria(t, objetivo, [pd.Timestamp(o) for o in origenes], series, padres)
        g = validacion["validacion"][objetivo]
        pares = {"origenes_que_gana": (r["veredicto"]["origenes_que_gana"], g["veredicto"]["origenes_que_gana"]),
                 "ventaja": (r["veredicto"]["ventaja"], g["veredicto"]["ventaja"]),
                 "intervalo_bajo": (r["veredicto"]["intervalo"]["bajo"], g["veredicto"]["intervalo"]["bajo"]),
                 "intervalo_alto": (r["veredicto"]["intervalo"]["alto"], g["veredicto"]["intervalo"]["alto"]),
                 "error_modelo": (r["veredicto"]["error_modelo"], g["veredicto"]["error_modelo"]),
                 "suavizado_ventaja": (r["suavizado"]["ventaja"], g["suavizado"]["ventaja"]),
                 "suavizado_intervalo_bajo": (r["suavizado"]["intervalo"]["bajo"], g["suavizado"]["intervalo"]["bajo"])}
        diferencias = {k: abs(float(a) - float(b)) for k, (a, b) in pares.items()}
        iguales.append(all(d <= TOLERANCIA for d in diferencias.values())
                       and r["veredicto"]["veredicto"] == g["veredicto"]["veredicto"])
        salida[objetivo] = {"diferencia_maxima": max(diferencias.values()), "diferencias": diferencias}
    return {"por_objetivo": salida, "coincide": all(iguales),
            "como": f"medir_ordinaria sobre {PREV_VALIDACION_REL} frente a {VALIDACION_JSON_REL}, tolerancia {TOLERANCIA:g}"}


def cifras_de_la_validacion(validacion):
    """Las cifras de la validación que van al lado de las de la prueba final, leídas de informes/validacion.json."""
    salida = {}
    for objetivo in OBJETIVOS:
        g = validacion["validacion"][objetivo]
        salida[objetivo] = resumen_veredicto(g) | {
            "suavizado": {"origenes_que_gana": g["suavizado"]["origenes_que_gana"], "ventaja": g["suavizado"]["ventaja"],
                          "lectura": g["suavizado"]["lectura"]},
            "periodo": f"{g['primer_dia_previsto'][:10]} a {g['ultimo_dia_previsto'][:10]}"}
    return salida


# ══ 8. Principal ════════════════════════════════════════════════════════════════
def medir_variante(nombre, carpeta_lote, real, series, padres, cache):
    """Lee el lote de una variante y mide los dos objetivos en los orígenes ordinarios y las unidades en los
    festivos; devuelve el bloque del JSON y las filas medidas para el Parquet."""
    ordinarios = origenes_ordinarios()
    pruebas = [{"prueba": "ordinaria", "origen": o, "objetivos": list(OBJETIVOS)} for o in ordinarios]
    pruebas += [{"prueba": "festivo", "origen": o, "objetivos": ["unidades"]} for o in FESTIVOS.values()]
    lote = leer_lote(carpeta_lote, pruebas, HORIZONTES, series)
    bloque, filas = {}, []
    for objetivo in OBJETIVOS:
        tabla = armar_objetivo(lote, real, objetivo, ordinarios, HORIZONTES[objetivo], "ordinaria", cache=cache)
        bloque[objetivo] = medir_ordinaria(tabla, objetivo, ordinarios, series, padres)
        filas.append(tabla.assign(objetivo=objetivo, real=tabla[objetivo]))
    festivos = armar_objetivo(lote, real, "unidades", list(FESTIVOS.values()), HORIZONTES["unidades"], "festivo",
                              cache=cache)
    bloque["unidades"]["festivos"] = medir_festivos(festivos, "unidades", {v: k for k, v in FESTIVOS.items()})
    filas.append(festivos.assign(objetivo="unidades", real=festivos["unidades"]))
    juntas = pd.concat(filas, ignore_index=True).assign(variante=nombre)
    juntas = juntas[["variante", "prueba", "objetivo", "origen"] + CLAVES + ["h", "real", "modelo", *REGLAS,
                                                                            "suavizado", "fuera_del_error"]]
    resumen_lote = json.loads((Path(carpeta_lote) / "resumen.json").read_text(encoding="utf-8")) \
        if (Path(carpeta_lote) / "resumen.json").exists() else {}
    return bloque, juntas, resumen_lote


def huellas_del_modelo(carpeta):
    """La huella de los dos modelos de una carpeta de reentreno."""
    return {o: huella(carpeta / f"{o}.joblib") for o in OBJETIVOS if (carpeta / f"{o}.joblib").exists()}


def principal(raiz, reentrenado_rel):
    """Mide, compara y devuelve el diccionario del JSON y la tabla de previsiones."""
    r = {"metodo": "preproduccion", "version_metodo": version_metodo(), "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
         "fin_prueba_final": FIN_PRUEBA_FINAL, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__,
                     "ejecutable": sys.executable},
         "entradas": [], "resultado": {}, "pendientes": [], "puerta_de_juan": False}
    huellas_raw = {rel: huella(raiz / rel) for rel in RAW.values()}

    # 1. La venta real, sumada aquí de data/raw/ y data/raw/reserva/, y su comprobación contra el desarrollo
    venta_a = pd.read_csv(raiz / RAW["venta"], encoding="utf-8")
    venta_b = pd.read_csv(raiz / RAW["venta_reserva"], encoding="utf-8")
    if not (venta_a["id"].to_numpy() == venta_b["id"].to_numpy()).all():
        raise Parada("la venta y su reserva no traen los mismos productos en el mismo orden")
    venta = pd.concat([venta_a, venta_b[[c for c in venta_b.columns if str(c).startswith("d_")]]], axis=1)
    precios = pd.concat([pd.read_csv(raiz / RAW["precios"], encoding="utf-8"),
                         pd.read_csv(raiz / RAW["precios_reserva"], encoding="utf-8")], ignore_index=True)
    calendario = pd.read_csv(raiz / RAW["calendario"], encoding="utf-8")
    real = venta_real_por_serie(venta, precios, calendario)
    desarrollo = pd.concat([pd.read_parquet(raiz / SERIES_ENT_REL), pd.read_parquet(raiz / SERIES_VAL_REL)],
                           ignore_index=True)
    hasta_desarrollo = real[(real[COLUMNA_FECHA] <= pd.Timestamp(FECHA_DATOS)).to_numpy()]
    venta_igual = comparar_tablas(hasta_desarrollo, desarrollo,
                                  ["unidades", "dolares", "fuera_del_error", "cierre_tienda"])

    # 2. Lo que se sabe de antemano: la tabla de historia de la prueba por otro camino, comprobada en la validación
    eventos = [c[len("evento_"):] for c in pq.read_schema(raiz / MODELO_ENT_REL).names if c.startswith("evento_")]
    modelo_val = pd.read_parquet(raiz / MODELO_VAL_REL)
    dias_val = a_fecha(modelo_val[COLUMNA_FECHA])
    sabido_val = lo_que_se_sabe(real, venta, precios, calendario, eventos, dias_val.min(), dias_val.max())
    columnas_evento = [f"evento_{e}" for e in eventos]
    sabido_igual = comparar_tablas(sabido_val, modelo_val, COLUMNAS_COMPROBADAS + columnas_evento)
    inicio_pf = pd.Timestamp(FECHA_DATOS) + pd.Timedelta(1, "D")
    sabido_pf = lo_que_se_sabe(real, venta, precios, calendario, eventos, inicio_pf, pd.Timestamp(FIN_PRUEBA_FINAL))

    # 3 a 6. Cada variante: el lote, las reglas, el suavizado y la medida
    series = sorted(map(tuple, real[CLAVE_SERIE].drop_duplicates().to_numpy().tolist()))
    padres = V16.padres_de_las_series(pd.read_parquet(raiz / DIM_PRODUCTO_REL), pd.read_parquet(raiz / DIM_TIENDA_REL),
                                      series)
    cache, tablas = {}, []
    variantes = {"tal_como_esta": CANDIDATO_REL}
    if reentrenado_rel:
        variantes["reentrenado"] = reentrenado_rel
    r["modelos"], r["lote"] = {}, {}
    for nombre, carpeta_modelo in variantes.items():
        bloque, juntas, resumen_lote = medir_variante(nombre, raiz / LOTE_REL / nombre, real, series, padres, cache)
        r[nombre] = rotular(bloque)
        tablas.append(juntas)
        esperadas = huellas_del_modelo(raiz / carpeta_modelo)
        usadas = [o.get("modelo", {}).get("huellas") for o in resumen_lote.get("origenes", [])]
        r["modelos"][nombre] = {"carpeta": carpeta_modelo, "huellas": esperadas,
                                "lote_con_este_modelo": bool(usadas) and all(u == esperadas for u in usadas)}
        r["lote"][nombre] = {"ruta": f"{LOTE_REL}/{nombre}", "filas_salida": resumen_lote.get("filas_salida"),
                             "filas_entrada": resumen_lote.get("filas_entrada"),
                             "sin_prevision": resumen_lote.get("sin_prevision")}

    # 7. Se mide igual que la validación y sus cifras van al lado
    validacion = json.loads((raiz / VALIDACION_JSON_REL).read_text(encoding="utf-8"))
    prev_val = pd.read_parquet(raiz / PREV_VALIDACION_REL)
    igual_que_validacion = medida_de_la_validacion(prev_val, validacion, padres)
    r["validacion_al_lado"] = cifras_de_la_validacion(validacion)
    r["comparacion"] = {o: {"validacion": r["validacion_al_lado"][o]} | {
        n: resumen_veredicto(r[n][o]) for n in variantes} for o in OBJETIVOS}

    # Las comprobaciones, calculadas con lo ejecutado
    controles = [(n, o, r[n][o]["control"]) for n in variantes for o in OBJETIVOS]
    huellas_despues = {rel: huella(raiz / rel) for rel in RAW.values()}
    candidato = json.loads((raiz / CANDIDATO_REL / "reentreno.json").read_text(encoding="utf-8"))
    r["comprobaciones"] = {
        "venta_real_igual_que_el_desarrollo": venta_igual["igual"],
        "lo_que_se_sabe_igual_que_el_desarrollo": sabido_igual["igual"],
        "medida_igual_que_la_validacion": igual_que_validacion["coincide"],
        "ventaja_por_otro_camino": all(c["ventaja_otro_camino"] for _, _, c in controles),
        "intervalo_por_series_enteras": all(c["intervalo_por_entidad"] for _, _, c in controles),
        "sin_dias_fuera_del_error_en_la_medida": all(c["sin_dias_fuera"] for _, _, c in controles),
        "previsiones_completas": all(c["completa"] for _, _, c in controles),
        "suavizado_sin_futuro": all(c["suavizado_sin_futuro"] for _, _, c in controles),
        "lote_con_el_modelo_que_se_dice": all(m["lote_con_este_modelo"] for m in r["modelos"].values()),
        "candidato_sin_tocar": huellas_del_modelo(raiz / CANDIDATO_REL) == {
            o: candidato["modelos"][o]["huella"] for o in OBJETIVOS},
        "entradas_sin_cambiar": huellas_despues == huellas_raw}
    r["detalle_comprobaciones"] = {"venta_real": venta_igual, "lo_que_se_sabe": sabido_igual,
                                   "medida_de_la_validacion": igual_que_validacion}
    r["entradas"] = [{"ruta": rel, "sha256": h} for rel, h in huellas_raw.items()] + [
        {"ruta": rel, "sha256": huella(raiz / rel)} for rel in (VALIDACION_JSON_REL, PREV_VALIDACION_REL)]
    r["huellas_despues"] = huellas_despues
    r["que_se_mide"] = {
        "fuente": "guion del paso 7, apartado 2, fijado antes de abrir el año (petición 28)",
        "origenes": [f"{o:%Y-%m-%d}" for o in origenes_ordinarios()], "horizontes": HORIZONTES,
        "festivos": {k: f"{v:%Y-%m-%d}" for k, v in FESTIVOS.items()},
        "regla_de_ganar": (f"reglas, apartado 7: falla menos que la regla que menos falla en al menos "
                           f"{math.ceil(V16.PROPORCION_ORIGENES * N_ORIGENES)} de {N_ORIGENES} orígenes y el intervalo "
                           f"del 95 % de la ventaja ({V16.REMUESTREOS} remuestreos de las series enteras, semilla "
                           f"{V16.SEMILLA}) queda por encima de cero"),
        "fuera_del_error": "el 25 de diciembre y los días con la tienda entera a cero (reglas, apartado 5 y §6)",
        "no_se_ajusta_nada": "con lo que se ve en el año guardado no se cambia el modelo"}
    r["tabla_de_historia"] = {"ruta": HECHOS_PF_REL, "filas": len(sabido_pf),
                              "para_que": "la historia de tests/comprobar_produccion_por_otro_camino.py en el lote"}
    r["previsiones"] = {"ruta": PARQUET_REL, "valores": "acotados en cero y, en unidades, redondeados: como se miden"}
    r["datos_personales"] = {"proteccion_datos_json": (raiz / "config/fuentes/proteccion-datos.json").exists(),
                             "columnas_de_personas_usadas": []}
    tabla = pd.concat(tablas, ignore_index=True).sort_values(
        ["variante", "prueba", "objetivo", "origen"] + CLAVES).reset_index(drop=True)
    r["previsiones"]["filas"] = len(tabla)
    rojas = [k for k, v in r["comprobaciones"].items() if v is not True]
    resumen = "; ".join(f"{n}, {o}: {r['comparacion'][o][n]['veredicto']} ({r['comparacion'][o][n]['origenes_que_gana']} "
                        f"de {N_ORIGENES}, ventaja {r['comparacion'][o][n]['ventaja']:.2f}, intervalo "
                        f"{r['comparacion'][o][n]['intervalo_bajo']:.2f} a {r['comparacion'][o][n]['intervalo_alto']:.2f})"
                        for o in OBJETIVOS for n in variantes)
    if rojas:
        r["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{resumen}; comprobaciones en rojo: {rojas}",
                          "artefactos": [JSON_REL], "siguiente": "revisar las comprobaciones en rojo"}
        return r, None, None
    # 8. La ficha del reentrenado: su comparación con el candidato, que hace de modelo en uso (no hay ninguno); se
    # escribe solo con las comprobaciones en verde (error 15)
    if "reentrenado" in variantes:
        ficha = raiz / variantes["reentrenado"] / "reentreno.json"
        datos = json.loads(ficha.read_text(encoding="utf-8"))
        datos["comparacion_con_el_en_uso"] = {
            "periodo": f"{inicio_pf:%Y-%m-%d} a {FIN_PRUEBA_FINAL}: los 13 orígenes de la prueba final y las 3 vísperas "
                       "de festivo, que ninguno de los dos modelos vio",
            "filas": {o: r["reentrenado"][o]["filas_medidas"] for o in OBJETIVOS},
            "medida": "error de reglas, apartado 6 por cada 100 vendidos y veredicto de reglas, apartado 7, como la validación",
            "en_uso": {"carpeta": CANDIDATO_REL, "nota": "no hay modelo en uso: es el candidato que reproduce la "
                                                         "validación"} | {o: r["comparacion"][o]["tal_como_esta"]
                                                                           for o in OBJETIVOS},
            "reentrenado": {o: r["comparacion"][o]["reentrenado"] for o in OBJETIVOS},
            "fuente": JSON_REL, "escrito_por": SCRIPT_REL}
        ficha.write_text(json.dumps(V16.a_json_limpio(datos), ensure_ascii=False, indent=2), encoding="utf-8")
        r["reentrenado_ficha"] = f"{variantes['reentrenado']}/reentreno.json"

    r["puerta_de_juan"] = True
    r["pendientes"] = [
        {"id": "P-01", "tabla": "prueba final", "columna": "veredicto de cada objetivo",
         "pregunta": "¿Se confirma el veredicto de la validación con la prueba final en cada objetivo?",
         "opciones": ["se confirma", "no se confirma: se dice así"]},
        {"id": "P-02", "tabla": "modelo en uso", "columna": "los dos modelos",
         "pregunta": "¿Qué modelo pasa a uso (puerta 4)?",
         "opciones": [CANDIDATO_REL] + ([variantes["reentrenado"]] if "reentrenado" in variantes else [])
         + ["ninguno todavía"]}]
    r["resultado"] = {"estado": "PARADO", "riesgo": "medio", "resumen": f"{resumen}; comprobaciones en verde; el responsable del caso "
                      "decide si se confirma y qué modelo pasa a uso",
                      "artefactos": [JSON_REL, PARQUET_REL, HECHOS_PF_REL],
                      "siguiente": "El responsable del caso decide (puerta 4); después, el informe de la preproducción y el informe final"}
    return r, tabla, sabido_pf


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", type=Path, default=CASO)
    argumentos.add_argument("--reentrenado", default=None, help="carpeta del reentrenado, desde la del caso")
    args = argumentos.parse_args()
    raiz_caso = args.raiz.resolve()
    print("intérprete:", sys.executable)
    tabla_prev = sabido = None
    try:
        resultado, tabla_prev, sabido = principal(raiz_caso, args.reentrenado)
    except Exception as fallo:  # una parada o un fallo técnico dejan el JSON con su estado y salen con 1
        traceback.print_exc()
        resultado = {"metodo": "preproduccion", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                     "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "puerta_de_juan": False,
                     "resultado": {"estado": "PARADO" if isinstance(fallo, Parada) else "ERROR", "riesgo": "alto",
                                   "resumen": f"{type(fallo).__name__}: {fallo}", "artefactos": [JSON_REL],
                                   "siguiente": "revisar el motivo"}, "pendientes": []}
    # Se valida antes de guardar (error 15): las tablas solo se escriben con las comprobaciones en verde
    if tabla_prev is not None:
        tabla_prev.to_parquet(raiz_caso / PARQUET_REL, index=False)
        sabido.to_parquet(raiz_caso / HECHOS_PF_REL, index=False)
    (raiz_caso / JSON_REL).write_text(json.dumps(V16.a_json_limpio(resultado), ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado.get("puerta_de_juan") else 1)
