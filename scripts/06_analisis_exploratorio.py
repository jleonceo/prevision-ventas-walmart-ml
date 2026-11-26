"""Análisis exploratorio de la tabla de series del caso 69 (método analisis-exploratorio).

Lee data/processed/hechos_series.parquet (una fila por departamento en una tienda y día) con sus dos dimensiones y el
Calendario, solo para leer, y deja informes/analisis-exploratorio__hechos_series.json y .html. El HTML sale entero del
JSON: ninguna cifra del informe se calcula al escribirlo.

Población: solo las filas con periodo «construccion». De la validación salen solo sus filas, unidades y dólares. Los
días con fuera_del_error salen de los efectos de la pregunta 4, de las medias y del bloque frente al objetivo.

Depende de lo que deja scripts/05_transformacion_datos.py: lee informes/transformacion-datos.json (estado y columnas
posteriores al día) y las tablas cuya huella está en sus salidas. Si su estado es PARADO o ERROR, no analiza.

Uso: python -W error scripts/06_analisis_exploratorio.py [--raiz CARPETA]
  --raiz: carpeta con la estructura del caso (data/processed/ e informes/). Por defecto, la del propio script.
"""

# =====================================================================================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN
# =====================================================================================================================

# argparse lee la carpeta del caso, para que la prueba use una copia pequeña
import argparse
# hashlib da la huella de cada tabla antes y después
import hashlib
# html escapa los textos del informe
import html
# json escribe el resultado
import json
# math comprueba los valores que no son números
import math
# sys da la versión de Python y la ruta de las piezas comunes
import sys
# time mide cuánto tarda
import time
# datetime da la fecha de ejecución
from datetime import datetime
# Path calcula las rutas desde la carpeta del caso (error 23)
from pathlib import Path

# matplotlib, numpy, pandas, pyarrow y scipy hacen las cuentas y los gráficos
import matplotlib
import numpy as np
import pandas as pd
import pyarrow
import scipy
from scipy import stats

# Las piezas comunes se usan desde assets/, sin copiarlas
CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
import graficos  # noqa: E402

# Versión del método: la última línea de versión de su ficha del método
VERSION_METODO = "24/11/2026"
SCRIPT = "scripts/06_analisis_exploratorio.py"
TABLA = "hechos_series"
TABLAS = ["hechos_series", "dim_producto", "dim_tienda", "calendario"]

# Los siete grupos de columnas de la petición del paso 4
GRUPOS = {
    "identificación y fecha": ["store_id", "dept_id", "d", "date", "wm_yr_wk", "wm_yr_wk_anterior"],
    "dimensiones": ["cat_id", "state_id"],
    "objetivo": ["unidades", "dolares"],
    "calendario conocido de antemano": ["year", "month", "weekday", "wday", "event_name_1", "event_type_1",
                                        "event_name_2", "event_type_2", "snap"],
    "periodo y marcas de parcial": ["periodo", "mes_parcial", "semana_parcial"],
    "posteriores al día": ["cierre_tienda", "fuera_del_error", "clase_cero"],
    "precio": ["precio_medio_semana_anterior"],
}
# Las columnas que se cruzan con el objetivo: calendario, dimensiones y precio. Nunca una posterior al día.
VARIABLES_FRENTE_OBJETIVO = ["cat_id", "state_id", "year", "month", "weekday", "wday", "event_name_1", "event_type_1",
                             "event_name_2", "event_type_2", "snap", "precio_medio_semana_anterior"]

# Parámetros fijados antes de calcular (parametros.md del método y petición del paso 4)
FILAS_MINIMAS = 30                 # parametros.md: filas mínimas para comparar una categoría frente al objetivo
MINIMO_DIAS_EVENTO = 30            # planteamientos: mínimo de días de serie por evento y departamento
DIA_MAXIMO_SNAP = 15               # planteamientos: SNAP se compara dentro de los días 1 a 15 del mes
SEMANAS_DIA_NORMAL = 4             # planteamientos: el día normal, el mismo día de las cuatro semanas anteriores
RETARDOS_ACF = [1, 7, 14, 28]      # petición: autocorrelación a 1, 7, 14 y 28 días
VENTANA_SALTO, MINIMO_VENTANA, UMBRAL_SALTO = 91, 80, 1.5   # celda del salto de nivel del reconocimiento (D1)
PARETO_A, PARETO_B = 80, 95        # comprobación 2: A hasta el 80 %, B hasta el 95 %
CONCENTRACION_A = 20               # elegido antes de calcular: «casi todo» si la clase A tiene el 20 % o menos
UMBRAL_DIFERENCIA = 0.20           # elegido antes de calcular: una variable muestra diferencia desde el 20 %
UMBRAL_FUGA = 0.90                 # elegido antes de calcular: separa casi del todo con eta² o |rho| de 0,9
SENAL_MEDIA_MEDIANA = 0.25         # elegido antes de calcular: media lejos de la mediana si se aparta un 25 %
SENAL_ORDENES = 1000               # elegido antes de calcular: máximo mil veces el mínimo positivo
DIAS_SEMANA = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
NOMBRE_DIA = dict(zip(DIAS_SEMANA, ["sábado", "domingo", "lunes", "martes", "miércoles", "jueves", "viernes"]))
NOMBRE_MES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
              9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
CORTO_MES = {k: v[:3] for k, v in NOMBRE_MES.items()}


# =====================================================================================================================
# 2. PIEZAS PEQUEÑAS
# =====================================================================================================================

def huella(ruta):
    """SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def limpio(x):
    """Pasa a tipos de JSON: numpy a Python, fechas a ISO y lo que no es número a null (error 22)."""
    if isinstance(x, dict):
        return {str(k): limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [limpio(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(x).date().isoformat()
    if x is pd.NA:
        return None
    return x


def pct(a, b):
    """a / b - 1 en porcentaje; None si no se puede calcular."""
    if a is None or b is None or not math.isfinite(a) or not math.isfinite(b) or b == 0:
        return None
    return (a / b - 1) * 100


def n(x, dec=0, unidad="", con_signo=False):
    """Número a la española para el texto del informe; «no se puede calcular» si falta."""
    return "no se puede calcular" if x is None else graficos.numero(x, dec, unidad, con_signo)


# =====================================================================================================================
# 3. POBLACIÓN Y FILTROS QUE EVITAN LOS ERRORES DEL PETICIÓN
# =====================================================================================================================

def poblacion(df):
    """Las filas de la construcción: la validación solo da sus totales (reglas, apartado 7, «Población del análisis»)."""
    return df.loc[df["periodo"].eq("construccion")].copy()


def sin_fuera(df):
    """Quita los días fuera del error: el 25 de diciembre y el cierre de WI_1 (reglas, apartado 6)."""
    return df.loc[~df["fuera_del_error"].astype(bool)]


def en_quincena(dia):
    """Cierto en los días 1 a 15 del mes, los únicos con que se compara SNAP (planteamientos)."""
    return np.asarray(dia) <= DIA_MAXIMO_SNAP


def semana_vale_para_normal(evento, fuera):
    """Un día anterior sirve para el día normal si no tiene evento y no está fuera del error (planteamientos)."""
    return ~evento & ~fuera


def comprobar_sin_posteriores(variables, posteriores):
    """Para si alguna columna posterior al día iba a cruzarse con el objetivo como variable."""
    cruzadas = sorted(set(variables) & set(posteriores))
    if cruzadas:
        raise ValueError(f"columnas posteriores al día cruzadas con el objetivo: {cruzadas}")


def matriz(pob, columnas):
    """Coloca columnas de la tabla larga en matrices de series (tienda y departamento) por días, ordenadas."""
    claves = pob[["store_id", "dept_id"]].drop_duplicates().sort_values(["store_id", "dept_id"], ignore_index=True)
    fechas = np.sort(pob["date"].unique())
    codigo = {(a, b): i for i, (a, b) in enumerate(zip(claves["store_id"], claves["dept_id"]))}
    fila = np.array([codigo[k] for k in zip(pob["store_id"], pob["dept_id"])])
    col = np.searchsorted(fechas, pob["date"].to_numpy())
    salida = {}
    for c in columnas:
        if c == "event_name_1":
            m = np.full((len(claves), len(fechas)), "", dtype=object)
            m[fila, col] = pob[c].fillna("").to_numpy(dtype=object)
        elif c in ("fuera_del_error",):
            m = np.ones((len(claves), len(fechas)), dtype=bool)
            m[fila, col] = pob[c].to_numpy(dtype=bool)
        else:
            m = np.full((len(claves), len(fechas)), np.nan)
            m[fila, col] = pob[c].to_numpy(dtype="float64")
        salida[c] = m
    return claves, pd.DatetimeIndex(fechas), salida


# =====================================================================================================================
# 4. BLOQUE 4 · LA PREGUNTA 4 (planteamientos, «ya fijado», 24/11/2026)
# =====================================================================================================================

def efecto_snap(pob):
    """Cambio de la venta en días SNAP frente a días sin SNAP de los días 1 a 15, por departamento, en %."""
    t = sin_fuera(pob)
    t = t.loc[en_quincena(t["date"].dt.day.to_numpy())]
    salida = {}
    for dept in sorted(t["dept_id"].unique()):
        u = t.loc[t["dept_id"].eq(dept)]
        con, sin = u.loc[u["snap"].eq(1), "unidades"], u.loc[u["snap"].eq(0), "unidades"]
        media_con = float(con.mean()) if len(con) else None
        media_sin = float(sin.mean()) if len(sin) else None
        salida[dept] = {"cambio_pct": pct(media_con, media_sin), "media_snap": media_con, "media_sin_snap": media_sin,
                        "dias_serie_snap": int(len(con)), "dias_serie_sin_snap": int(len(sin))}
    return salida


def efecto_snap_por_estado(pob):
    """El mismo cambio de SNAP por departamento y estado, para ver si se invierte al segmentar (§5 del método)."""
    salida = {}
    for estado in sorted(pob["state_id"].unique()):
        for dept, r in efecto_snap(pob.loc[pob["state_id"].eq(estado)]).items():
            salida.setdefault(dept, {})[estado] = r["cambio_pct"]
    return salida


def efecto_eventos(pob):
    """Cambio de la venta en cada evento frente a su día normal, por departamento, en %.

    Día de evento: event_name_1 lleno y dentro del error. Día normal de cada serie y día de evento: la media del mismo
    día de la semana en las cuatro semanas anteriores, sin las que tienen evento ni las fuera del error. El efecto es la
    media de los días de evento entre la media de sus días normales, menos 1, con MINIMO_DIAS_EVENTO días o más.
    """
    claves, fechas, m = matriz(pob, ["unidades", "fuera_del_error", "event_name_1"])
    tipo = pob.dropna(subset=["event_name_1"]).groupby("event_name_1")["event_type_1"].first().to_dict()
    U, F, N = m["unidades"], m["fuera_del_error"], m["event_name_1"]
    E = N != ""
    valida = semana_vale_para_normal(E, F) & ~np.isnan(U)
    suma, cuenta = np.zeros(U.shape), np.zeros(U.shape)
    # Para cada día, suma las semanas anteriores que valen, de una en una
    for k in range(1, SEMANAS_DIA_NORMAL + 1):
        s = 7 * k
        if s < U.shape[1]:
            suma[:, s:] += np.where(valida[:, :-s], np.nan_to_num(U[:, :-s]), 0.0)
            cuenta[:, s:] += valida[:, :-s]
    normal = np.divide(suma, cuenta, out=np.full(U.shape, np.nan), where=cuenta > 0)
    celdas = E & ~F & ~np.isnan(U)
    dept = claves["dept_id"].to_numpy()
    salida = []
    for evento in sorted(set(N[E])):
        for d in sorted(set(dept)):
            de = (N == evento) & celdas & (dept == d)[:, None]
            con = de & (cuenta > 0)
            dias = int(con.sum())
            media_ev = float(U[con].mean()) if dias else None
            media_no = float(normal[con].mean()) if dias else None
            salida.append({"evento": evento, "tipo": tipo.get(evento), "departamento": d, "dias_serie": dias,
                           "dias_sin_dia_normal": int((de & (cuenta == 0)).sum()),
                           "dias_con_menos_de_4_semanas": int((con & (cuenta < SEMANAS_DIA_NORMAL)).sum()),
                           "media_evento": media_ev, "media_dia_normal": media_no,
                           "cambio_pct": pct(media_ev, media_no) if dias >= MINIMO_DIAS_EVENTO and dias > 0 else None})
    return salida


def efecto_dia_semana(pob):
    """La venta media del día más fuerte entre la del más flojo, por departamento, sin los días fuera del error."""
    t = sin_fuera(pob)
    medias = t.groupby(["dept_id", "weekday"])["unidades"].mean()
    salida = {}
    for dept in sorted(t["dept_id"].unique()):
        serie = {d: float(medias[(dept, d)]) for d in DIAS_SEMANA if (dept, d) in medias.index}
        fuerte = max(serie, key=lambda d: (serie[d], -DIAS_SEMANA.index(d)))
        flojo = min(serie, key=lambda d: (serie[d], DIAS_SEMANA.index(d)))
        salida[dept] = {"cociente": serie[fuerte] / serie[flojo] if serie[flojo] > 0 else None,
                        "dia_fuerte": fuerte, "dia_flojo": flojo, "medias": serie,
                        "filas": int(t["dept_id"].eq(dept).sum())}
    return salida


def dia_fuerte_por_serie(pob):
    """El día de la semana más fuerte de cada serie, para ver si cambia de tienda a tienda."""
    t = sin_fuera(pob)
    medias = t.groupby(["store_id", "dept_id", "weekday"])["unidades"].mean()
    salida = {}
    for (tienda, dept), g in medias.groupby(level=["store_id", "dept_id"]):
        valores = {k[2]: float(v) for k, v in g.items()}
        salida.setdefault(dept, {})[tienda] = max(valores, key=lambda d: (valores[d], -DIAS_SEMANA.index(d)))
    return salida


def efecto_mes(pob):
    """Venta media de cada mes completo entre la media de los meses completos, por categoría, en %."""
    t = sin_fuera(pob)
    t = t.loc[~t["mes_parcial"].astype(bool)]
    salida = {}
    for cat in sorted(t["cat_id"].unique()):
        u = t.loc[t["cat_id"].eq(cat)]
        media = float(u["unidades"].mean())
        por_mes = u.groupby("month")["unidades"].agg(["mean", "size"])
        salida[cat] = {"media_meses_completos": media, "filas": int(len(u)),
                       "meses": {int(k): {"cambio_pct": pct(float(r["mean"]), media), "filas": int(r["size"])}
                                 for k, r in por_mes.iterrows()}}
    return salida


def precio_spearman(pob):
    """Spearman entre el precio medio de la semana anterior y las unidades de la semana, por serie y su mediana.

    Solo semanas completas (reglas, apartado 5: una semana parcial no se compara) con precio; las unidades de la semana suman
    sus días dentro del error.
    """
    t = sin_fuera(pob)
    t = t.loc[~t["semana_parcial"].astype(bool) & t["precio_medio_semana_anterior"].notna()]
    semanas = (t.groupby(["store_id", "dept_id", "wm_yr_wk"])
               .agg(unidades=("unidades", "sum"), precio=("precio_medio_semana_anterior", "first")).reset_index())
    series = []
    for (tienda, dept), g in semanas.groupby(["store_id", "dept_id"]):
        if g["precio"].nunique() < 2 or g["unidades"].nunique() < 2:
            rho = None
        else:
            rho = float(stats.spearmanr(g["precio"], g["unidades"]).statistic)
        series.append({"tienda": tienda, "departamento": dept, "semanas": int(len(g)), "spearman": rho,
                       "cambios_de_precio": int((g["precio"].diff().fillna(0) != 0).sum())})
    por_dept = {}
    for dept in sorted({s["departamento"] for s in series}):
        valores = [s["spearman"] for s in series if s["departamento"] == dept and s["spearman"] is not None]
        por_dept[dept] = {"mediana_spearman": float(np.median(valores)) if valores else None, "series": len(valores)}
    return {"series": series, "por_departamento": por_dept}


# =====================================================================================================================
# 5. BLOQUES 1 A 3 · REPARTO, RITMO, SALTOS Y CEROS
# =====================================================================================================================

def reparto(pob):
    """Unidades y dólares por estado, tienda, categoría y departamento, con su parte del total (todos los días)."""
    total_u, total_d = float(pob["unidades"].sum()), float(pob["dolares"].sum())
    salida = {}
    for nombre, col in [("estado", "state_id"), ("tienda", "store_id"), ("categoria", "cat_id"),
                        ("departamento", "dept_id")]:
        g = pob.groupby(col)[["unidades", "dolares"]].sum().sort_index()
        salida[nombre] = [{"nombre": k, "unidades": int(r["unidades"]), "dolares": round(float(r["dolares"]), 2),
                           "parte_unidades_pct": float(r["unidades"]) / total_u * 100 if total_u else None,
                           "parte_dolares_pct": float(r["dolares"]) / total_d * 100 if total_d else None}
                          for k, r in g.iterrows()]
    return salida


def pareto(valores):
    """Pareto y ABC de una pareja elemento y magnitud: cuántos elementos suman el 80 % y cada clase (comprobación 2)."""
    orden = sorted(valores.items(), key=lambda kv: (-kv[1], kv[0]))
    total = sum(v for _, v in orden)
    filas, previo = [], 0.0
    for nombre, v in orden:
        clase = "A" if previo < PARETO_A else ("B" if previo < PARETO_B else "C")
        previo += v / total * 100 if total else 0
        filas.append({"nombre": nombre, "valor": v, "acumulado_pct": previo, "clase": clase})
    k80 = next((i + 1 for i, f in enumerate(filas) if f["acumulado_pct"] >= PARETO_A - 1e-9), len(filas))
    clases = {c: {"elementos": sum(f["clase"] == c for f in filas),
                  "parte_pct": sum(f["valor"] for f in filas if f["clase"] == c) / total * 100 if total else None}
              for c in "ABC"}
    return {"elementos": len(filas), "elementos_para_el_80": k80,
            "elementos_para_el_80_pct": k80 / len(filas) * 100 if filas else None,
            "clases": clases, "ranking": filas}


def ritmo(pob):
    """Venta media por día de serie por día de la semana y por mes, por departamento (sin meses parciales)."""
    t = sin_fuera(pob)
    semana = t.groupby(["dept_id", "weekday"])[["unidades", "dolares"]].mean()
    tm = t.loc[~t["mes_parcial"].astype(bool)]
    mes = tm.groupby(["dept_id", "month"])[["unidades", "dolares"]].mean()
    salida = {"dia_semana": {}, "mes": {}}
    for dept in sorted(t["dept_id"].unique()):
        salida["dia_semana"][dept] = {d: {"unidades": float(semana.loc[(dept, d), "unidades"]),
                                          "dolares": float(semana.loc[(dept, d), "dolares"])}
                                      for d in DIAS_SEMANA if (dept, d) in semana.index}
        salida["mes"][dept] = {int(m_): {"unidades": float(r["unidades"]), "dolares": float(r["dolares"])}
                               for (d_, m_), r in mes.iterrows() if d_ == dept}
    parciales = (pob.loc[pob["mes_parcial"].astype(bool)].groupby(["year", "month"])["date"]
                 .agg(["min", "max"]).reset_index())
    salida["meses_parciales"] = [{"anio": int(r["year"]), "mes": int(r["month"]), "desde": r["min"], "hasta": r["max"]}
                                 for _, r in parciales.iterrows()]
    return salida


def autocorrelacion(pob):
    """Autocorrelación de las unidades de cada serie a 1, 7, 14 y 28 días, y su mediana por departamento.

    Es la autocorrelación muestral de manual: covarianza con el retardo entre la varianza, con la media de la serie
    entera. Usa todos los días de la construcción en su orden, sin huecos.
    """
    claves, _, m = matriz(pob, ["unidades"])
    series = []
    for i, x in enumerate(m["unidades"]):
        x = x[~np.isnan(x)]
        z = x - x.mean()
        den = float((z ** 2).sum())
        acf = {str(k): (float((z[k:] * z[:-k]).sum()) / den if den > 0 and k < len(z) else None) for k in RETARDOS_ACF}
        series.append({"tienda": claves.at[i, "store_id"], "departamento": claves.at[i, "dept_id"], "acf": acf})
    mediana = {}
    for dept in sorted(claves["dept_id"].unique()):
        mediana[dept] = {str(k): float(np.median([s["acf"][str(k)] for s in series if s["departamento"] == dept
                                                  and s["acf"][str(k)] is not None])) for k in RETARDOS_ACF}
    return {"series": series, "mediana_por_departamento": mediana}


def saltos(pob):
    """Salto de nivel de cada serie con la medida del reconocimiento (celda del salto, D1).

    Para cada día, la media de los 91 días siguientes (el del día incluido) frente a la de los 91 anteriores, sin el
    25 de diciembre y con al menos 80 días con dato en cada ventana; el mayor cambio de log((después + 1) / (antes + 1))
    de la serie es salto si la razón es 1,5 o más, o 1 / 1,5 o menos.
    """
    claves, fechas, m = matriz(pob, ["unidades"])
    navidad = (fechas.month == 12) & (fechas.day == 25)
    X = pd.DataFrame(np.where(navidad[None, :], np.nan, m["unidades"]).T)
    antes = X.rolling(VENTANA_SALTO, min_periods=MINIMO_VENTANA).mean().shift(1)
    despues = X.iloc[::-1].rolling(VENTANA_SALTO, min_periods=MINIMO_VENTANA).mean().iloc[::-1]
    A, D = antes.to_numpy(), despues.to_numpy()
    lr = np.log((D + 1) / (A + 1))
    salida = []
    for j in range(X.shape[1]):
        columna = np.abs(lr[:, j])
        if not np.isfinite(columna).any():
            salida.append({"tienda": claves.at[j, "store_id"], "departamento": claves.at[j, "dept_id"], "fecha": None,
                           "antes": None, "despues": None, "razon": None, "salto": None})
            continue
        i = int(np.nanargmax(columna))
        razon = D[i, j] / A[i, j] if A[i, j] > 0 else None
        es = razon is not None and (razon >= UMBRAL_SALTO or razon <= 1 / UMBRAL_SALTO)
        salida.append({"tienda": claves.at[j, "store_id"], "departamento": claves.at[j, "dept_id"],
                       "fecha": fechas[i].date().isoformat(), "antes": float(A[i, j]), "despues": float(D[i, j]), "razon": razon,
                       "salto": es})
    return salida


def ceros(pob):
    """Los días a cero por clase_cero y por serie, y las series de demanda intermitente (columna posterior)."""
    z = pob.loc[pob["unidades"].eq(0)]
    por_clase = {c: int(v) for c, v in z["clase_cero"].value_counts().sort_index().items()}
    por_serie = []
    for (tienda, dept), g in z.groupby(["store_id", "dept_id"]):
        por_serie.append({"tienda": tienda, "departamento": dept, "dias_cero": int(len(g)),
                          "por_clase": {c: int(v) for c, v in g["clase_cero"].value_counts().sort_index().items()}})
    intermitentes = sorted({f"{a} {b}" for a, b in zip(z.loc[z["clase_cero"].eq("demanda_intermitente"), "store_id"],
                                                        z.loc[z["clase_cero"].eq("demanda_intermitente"), "dept_id"])})
    return {"por_clase": por_clase, "por_serie": por_serie, "series_intermitentes": intermitentes,
            "dias_serie_a_cero": int(len(z))}


def series_de_negocio(pob):
    """Comprobación 11 sobre el total: media de unidades y dólares por día de serie de cada mes completo."""
    t = sin_fuera(pob)
    t = t.loc[~t["mes_parcial"].astype(bool)]
    mensual = t.groupby(["year", "month"])[["unidades", "dolares"]].mean().reset_index()
    salida = {"meses": [{"anio": int(r["year"]), "mes": int(r["month"]), "unidades": float(r["unidades"]),
                         "dolares": float(r["dolares"])} for _, r in mensual.iterrows()]}
    for mag in ("unidades", "dolares"):
        v = mensual[mag].to_numpy(dtype=float)
        r = {"media_movil_3": [None if np.isnan(x) else float(x) for x in pd.Series(v).rolling(3).mean()]}
        r["variacion_ultimo_mes_pct"] = pct(v[-1], v[-2]) if len(v) >= 2 else None
        if len(v) >= 13:
            ultimo = mensual.iloc[-1]
            previo = mensual.loc[(mensual["year"] == ultimo["year"] - 1) & (mensual["month"] == ultimo["month"]), mag]
            r["variacion_interanual_ultimo_mes_pct"] = pct(v[-1], float(previo.iloc[0])) if len(previo) else None
        else:
            r["variacion_interanual_ultimo_mes_pct"] = None
        x = np.arange(len(v), dtype=float)
        if len(v) >= 3:
            b, a = np.polyfit(x, v, 1)
            r2 = 1 - ((v - (a + b * x)) ** 2).sum() / ((v - v.mean()) ** 2).sum()
            be, ae = np.polyfit(x, np.log(v), 1)
            ve = np.exp(ae + be * x)
            r2e = 1 - ((v - ve) ** 2).sum() / ((v - v.mean()) ** 2).sum()
            r.update({"tendencia_lineal_por_mes": float(b), "r2_lineal": float(r2),
                      "tendencia_exponencial_pct_mes": float((np.exp(be) - 1) * 100), "r2_exponencial": float(r2e)})
        completos = mensual.groupby("year").size()
        anios = sorted(int(y) for y, k in completos.items() if k == 12)
        if len(anios) >= 2:
            ini = float(t.loc[t["year"].eq(anios[0]), mag].mean())
            fin = float(t.loc[t["year"].eq(anios[-1]), mag].mean())
            r["cagr"] = {"desde": anios[0], "hasta": anios[-1],
                         "pct": ((fin / ini) ** (1 / (anios[-1] - anios[0])) - 1) * 100 if ini > 0 else None}
        else:
            r["cagr"] = {"desde": None, "hasta": None, "pct": None, "motivo": "menos de dos años completos"}
        salida[mag] = r
    # Segunda granularidad: semanas completas (comprobación 1)
    sem = sin_fuera(pob).loc[lambda x: ~x["semana_parcial"].astype(bool)].groupby("wm_yr_wk").agg(
        unidades=("unidades", "mean"), desde=("date", "min"))
    salida["semanas"] = [{"semana": int(k), "desde": r["desde"], "unidades": float(r["unidades"])}
                         for k, r in sem.iterrows()]
    return salida


# =====================================================================================================================
# 6. TIPIFICACIÓN, NUMÉRICAS Y CATEGÓRICAS
# =====================================================================================================================

def tipificar(pob):
    """Tipo y grupo de cada columna (comprobación 13 para discreta o continua)."""
    limite = min(20, int(0.05 * len(pob)))
    tipos = {"store_id": "identificador", "dept_id": "identificador", "d": "identificador", "date": "fecha",
             "wm_yr_wk": "identificador", "wm_yr_wk_anterior": "identificador", "cat_id": "categorica",
             "state_id": "categorica", "year": "codigo", "month": "codigo", "weekday": "categorica", "wday": "codigo",
             "event_name_1": "categorica", "event_type_1": "categorica", "event_name_2": "categorica",
             "event_type_2": "categorica", "snap": "booleana", "periodo": "categorica", "mes_parcial": "booleana",
             "semana_parcial": "booleana", "cierre_tienda": "booleana", "fuera_del_error": "booleana",
             "clase_cero": "categorica"}
    salida = []
    for grupo, columnas in GRUPOS.items():
        for c in columnas:
            if c in tipos:
                tipo = tipos[c]
            else:
                v = pob[c].dropna()
                entera = bool(np.all(np.equal(np.mod(v.to_numpy(dtype=float), 1), 0)))
                tipo = "discreta" if entera and v.nunique() <= limite else "continua"
            salida.append({"columna": c, "grupo": grupo, "tipo": tipo, "distintos": int(pob[c].nunique()),
                           "vacios": int(pob[c].isna().sum())})
    return {"limite_discreta": limite, "columnas": salida}


def numericas(pob):
    """Estadísticos de las tres magnitudes, sin los días fuera del error, con las cuatro señales (comprobación 17)."""
    t = sin_fuera(pob)
    salida = []
    for c in ["unidades", "dolares", "precio_medio_semana_anterior"]:
        v = t[c].dropna().astype(float)
        q = v.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        media, mediana = float(v.mean()), float(q[0.5])
        positivos = v[v > 0]
        senales = []
        if mediana > 0 and abs(media - mediana) / mediana > SENAL_MEDIA_MEDIANA:
            senales.append("media lejos de la mediana")
        if q[0.25] == q[0.5] == q[0.75] or q[0.5] == v.max():
            senales.append("cuartiles iguales a un mismo valor")
        if len(positivos) and v.max() / positivos.min() >= SENAL_ORDENES:
            senales.append("mínimo y máximo de órdenes de magnitud distintos")
        if v.nunique() == 2:
            senales.append("variable binaria entre las continuas")
        salida.append({"columna": c, "validos": int(len(v)), "vacios": int(t[c].isna().sum()), "media": media,
                       "mediana": mediana, "desviacion": float(v.std()), "minimo": float(v.min()),
                       "maximo": float(v.max()), "percentiles": {str(int(k * 100)): float(x) for k, x in q.items()},
                       "senales": senales, "valores": v.to_numpy()})
    return salida


def categoricas(pob):
    """Frecuencias de cada categórica en su unidad: días, días de estado, series o filas (§2 del método)."""
    dias = pob.drop_duplicates("d")
    salida = []
    for c in ["event_name_1", "event_type_1", "event_name_2", "event_type_2", "weekday"]:
        f = dias[c].fillna("sin evento").value_counts()
        salida.append({"columna": c, "unidad": "días", "total": int(len(dias)), "distintos": int(dias[c].nunique()),
                       "frecuencias": {k: int(v) for k, v in f.items()}})
    estado_dia = pob.drop_duplicates(["state_id", "d"])
    f = estado_dia.groupby("state_id")["snap"].sum()
    salida.append({"columna": "snap", "unidad": "días de estado", "total": int(len(estado_dia)), "distintos": 2,
                   "frecuencias": {f"{k} con SNAP": int(v) for k, v in f.items()}})
    serie = pob.drop_duplicates(["store_id", "dept_id"])
    for c in ["cat_id", "state_id"]:
        f = serie[c].value_counts().sort_index()
        salida.append({"columna": c, "unidad": "series", "total": int(len(serie)), "distintos": int(serie[c].nunique()),
                       "frecuencias": {k: int(v) for k, v in f.items()}})
    for c in ["periodo", "mes_parcial", "semana_parcial"]:
        f = dias[c].astype(str).value_counts()
        salida.append({"columna": c, "unidad": "días", "total": int(len(dias)), "distintos": int(dias[c].nunique()),
                       "frecuencias": {k: int(v) for k, v in f.items()}})
    tienda_dia = pob.drop_duplicates(["store_id", "d"])
    for c in ["cierre_tienda", "fuera_del_error"]:
        salida.append({"columna": c, "unidad": "días de tienda", "total": int(len(tienda_dia)), "distintos": 2,
                       "frecuencias": {"verdadero": int(tienda_dia[c].sum())},
                       "dias_serie_verdadero": int(pob[c].sum())})
    f = pob["clase_cero"].fillna("con venta").value_counts()
    salida.append({"columna": "clase_cero", "unidad": "días de serie", "total": int(len(pob)),
                   "distintos": int(pob["clase_cero"].nunique()), "frecuencias": {k: int(v) for k, v in f.items()}})
    return salida


# =====================================================================================================================
# 7. FRENTE AL OBJETIVO (comprobación 12)
# =====================================================================================================================

def frente_al_objetivo(pob, posteriores):
    """Mediana del objetivo por categoría con sus filas; Pearson y Spearman con el precio. Solo construcción."""
    comprobar_sin_posteriores(VARIABLES_FRENTE_OBJETIVO, posteriores)
    t = sin_fuera(pob)
    salida = {"objetivo": ["unidades", "dolares"], "tipo": "cantidad", "filas_usadas": "construccion",
              "n_filas": int(len(t)), "filas_fuera_del_error_quitadas": int(len(pob) - len(t)), "variables": []}
    for objetivo in ["unidades", "dolares"]:
        y = t[objetivo].astype(float)
        mediana_global = float(y.median())
        for c in VARIABLES_FRENTE_OBJETIVO:
            if c == "precio_medio_semana_anterior":
                ok = t[c].notna()
                x, yy = t.loc[ok, c].astype(float), y[ok]
                pe, sp = float(stats.pearsonr(x, yy).statistic), float(stats.spearmanr(x, yy).statistic)
                salida["variables"].append({"columna": c, "objetivo": objetivo, "tipo": "magnitud",
                                            "filas": int(ok.sum()), "pearson": pe, "spearman": sp,
                                            "diferencia": abs(sp), "posible_fuga": abs(sp) >= UMBRAL_FUGA})
                continue
            grupo = t[c].astype(str).where(t[c].notna(), "sin evento") if t[c].dtype != bool else t[c].astype(str)
            g = y.groupby(grupo).agg(["median", "mean", "size"])
            categorias = [{"valor": k, "mediana": float(r["median"]), "filas": int(r["size"]),
                           "se_compara": bool(r["size"] >= FILAS_MINIMAS)} for k, r in g.iterrows()]
            comparables = [x for x in categorias if x["se_compara"]]
            dif = ((max(x["mediana"] for x in comparables) - min(x["mediana"] for x in comparables)) / mediana_global
                   if len(comparables) >= 2 and mediana_global > 0 else None)
            total_ss = float(((y - y.mean()) ** 2).sum())
            entre = float((g["size"] * (g["mean"] - y.mean()) ** 2).sum())
            eta2 = entre / total_ss if total_ss > 0 else None
            salida["variables"].append({"columna": c, "objetivo": objetivo, "tipo": "categorica",
                                        "mediana_global": mediana_global, "categorias": categorias,
                                        "diferencia": dif, "eta2": eta2,
                                        "muestra_diferencia": dif is not None and dif >= UMBRAL_DIFERENCIA,
                                        "posible_fuga": eta2 is not None and eta2 >= UMBRAL_FUGA})
    salida["variables"].sort(key=lambda v: (v["objetivo"], -(v["diferencia"] or 0)))
    return salida


# =====================================================================================================================
# 8. LO ESPERABLE (comprobación 18, reglas, apartado 7)
# =====================================================================================================================

def lo_esperable(pob, r):
    """Mide las filas de «Lo esperable» que se pueden medir con esta tabla y marca la zona gris."""
    filas = []
    t = sin_fuera(pob)
    por_serie = t.groupby(["store_id", "dept_id"])
    med_u = por_serie["unidades"].median()
    med_d = por_serie["dolares"].median()
    # Venta diaria en unidades: entera, no negativa, de decenas a pocos miles (lectura: de 10 a 5.000)
    neg = int((pob["unidades"] < 0).sum())
    dec = int((pob["unidades"] % 1 != 0).sum())
    bajo = sorted(f"{a} {b}" for (a, b), v in med_u.items() if v < 10)
    n_saltos = sum(1 for s in r["saltos"] if s["salto"])
    zona = []
    if bajo:
        zona.append(f"{len(bajo)} series con una mediana diaria por debajo de 10 unidades")
    if int(pob["unidades"].max()) > 5000:
        zona.append("algún día pasa de 5.000 unidades")
    if n_saltos:
        zona.append(f"{n_saltos} series con un salto de nivel duradero")
    filas.append({"fila": "Venta diaria de un departamento en una tienda, en unidades",
                  "rango": "entera y no negativa; de decenas a pocos miles al día (leído como de 10 a 5.000)",
                  "cifras": {"negativos": neg, "con_decimales": dec, "mediana_menor_serie": float(med_u.min()),
                             "mediana_mayor_serie": float(med_u.max()), "maximo_dia": int(pob["unidades"].max()),
                             "series_mediana_bajo_10": bajo, "series_con_salto": n_saltos},
                  "dentro": not zona and neg == 0 and dec == 0, "zona_gris": zona})
    # Venta diaria en dólares: positiva, de cientos a decenas de miles (lectura: de 100 a 99.999)
    d0u = int(((pob["dolares"] > 0) & (pob["unidades"] == 0)).sum())
    u0d = int(((pob["dolares"] == 0) & (pob["unidades"] > 0)).sum())
    con_u = t.loc[t["unidades"] > 0]
    pu = con_u["dolares"] / con_u["unidades"]
    bajo_d = sorted(f"{a} {b}" for (a, b), v in med_d.items() if v < 100)
    zona = []
    if bajo_d:
        zona.append(f"{len(bajo_d)} series con una mediana diaria por debajo de 100 dólares")
    if d0u or u0d:
        zona.append("dólares sin unidades o unidades sin dólares")
    if int((pu < 1).sum()) or int((pu >= 100).sum()):
        zona.append("días con un precio medio por unidad de céntimos o de cientos de dólares")
    filas.append({"fila": "Venta diaria de un departamento en una tienda, en dólares",
                  "rango": "positiva; de cientos a decenas de miles al día (leído como de 100 a 99.999); precio medio "
                           "por unidad entre 1 y 100 dólares",
                  "cifras": {"dolares_sin_unidades": d0u, "unidades_sin_dolares": u0d,
                             "mediana_menor_serie": float(med_d.min()), "mediana_mayor_serie": float(med_d.max()),
                             "series_mediana_bajo_100": bajo_d, "precio_unidad_minimo": float(pu.min()),
                             "precio_unidad_maximo": float(pu.max()), "dias_precio_unidad_bajo_1": int((pu < 1).sum()),
                             "dias_precio_unidad_100_o_mas": int((pu >= 100).sum())},
                  "dentro": not zona, "zona_gris": zona})
    # Días sin ventas: pocos en los grandes; días seguidos a cero en alimentación; pequeño casi siempre a cero
    abiertos = pob.loc[~pob["cierre_tienda"].astype(bool)]
    parte = (abiertos["unidades"].eq(0).groupby(abiertos["dept_id"]).mean() * 100).to_dict()
    claves, _, m = matriz(abiertos.assign(cero=abiertos["unidades"].eq(0).astype(float)), ["cero"])
    rachas = {}
    for i, fila_ in enumerate(m["cero"]):
        mayor, actual = 0, 0
        for v in fila_:
            actual = actual + 1 if v == 1 else 0
            mayor = max(mayor, actual)
        dept = claves.at[i, "dept_id"]
        rachas[dept] = max(rachas.get(dept, 0), mayor)
    zona = [f"{d}: racha de {k} días seguidos a cero" for d, k in sorted(rachas.items()) if d.startswith("FOODS")
            and k >= 2]
    zona += [f"{d}: {graficos.numero(p, 1)} % de días a cero" for d, p in sorted(parte.items()) if p > 50]
    productos = r["productos_por_departamento"]
    comunes = [d for d in parte if d in productos]
    rho = (float(stats.spearmanr([productos[d] for d in comunes], [parte[d] for d in comunes]).statistic)
           if len(comunes) >= 3 else None)
    filas.append({"fila": "Días sin ventas de un departamento",
                  "rango": "pocos o ninguno en los grandes; más en los pequeños; más productos, menos ceros",
                  "cifras": {"parte_dias_a_cero_pct": parte, "racha_mayor_a_cero": rachas,
                             "spearman_productos_y_ceros": rho},
                  "dentro": not zona and (rho is None or rho < 0), "zona_gris": zona})
    # Cierres de tienda: pocos al año; el 25 de diciembre la venta es cero
    tienda_dia = pob.groupby(["store_id", "date"]).agg(cierre=("cierre_tienda", "first"), u=("unidades", "sum"),
                                                       evento=("event_name_1", "first")).reset_index()
    navidad = (tienda_dia["date"].dt.month == 12) & (tienda_dia["date"].dt.day == 25)
    fuera25 = tienda_dia.loc[tienda_dia["cierre"].astype(bool) & ~navidad]
    por_anio = fuera25.groupby(fuera25["date"].dt.year).size().to_dict()
    nav_venta = tienda_dia.loc[navidad & (tienda_dia["u"] > 0)]
    zona = [f"cierre de {a} el {b.date().isoformat()} sin evento en el calendario"
            for a, b, e in zip(fuera25["store_id"], fuera25["date"], fuera25["evento"]) if pd.isna(e)]
    zona += [f"{k} cierres fuera del 25 de diciembre en {y}" for y, k in por_anio.items() if k > 2]
    if len(nav_venta):
        zona.append(f"{len(nav_venta)} días de tienda del 25 de diciembre con venta ({int(nav_venta['u'].sum())} "
                    f"unidades)")
    filas.append({"fila": "Cierres de tienda",
                  "rango": "muy pocos al año; el 25 de diciembre la venta es cero",
                  "cifras": {"cierres_fuera_del_25_por_anio": {int(k): int(v) for k, v in por_anio.items()},
                             "dias_tienda_25_diciembre": int(navidad.sum()),
                             "dias_tienda_25_diciembre_con_venta": int(len(nav_venta)),
                             "unidades_25_diciembre": int(nav_venta["u"].sum())},
                  "dentro": not zona, "zona_gris": zona})
    # Festivos y eventos: de -20 % a +20 %; más de un 50 % hace sospechar
    con = [e for e in r["pregunta_4"]["eventos"] if e["cambio_pct"] is not None]
    fuera_r = [e for e in con if abs(e["cambio_pct"]) > 20]
    sospecha = [e for e in con if abs(e["cambio_pct"]) > 50]
    signos = {np.sign(e["cambio_pct"]) for e in con}
    zona = [f"{len(fuera_r)} de {len(con)} pares de evento y departamento fuera de ±20 %"] if fuera_r else []
    zona += [f"{e['evento']} en {e['departamento']}: {graficos.numero(e['cambio_pct'], 1, ' %', True)}"
             for e in sorted(sospecha, key=lambda e: e["cambio_pct"])]
    if len(signos) == 1 and con:
        zona.append("todos los eventos con el mismo signo")
    filas.append({"fila": "Cambio de la venta en festivos",
                  "rango": "de un 20 % menos a un 20 % más que un día normal; el 25 de diciembre aparte",
                  "cifras": {"pares_con_efecto": len(con), "pares_fuera_de_20": len(fuera_r),
                             "pares_mas_de_50": len(sospecha)},
                  "dentro": not zona, "zona_gris": zona})
    # SNAP: de 0 a +10 %, sobre todo en alimentación; negativo en alimentación o más de un 20 % hace sospechar
    snap = r["pregunta_4"]["snap"]
    zona = []
    for d, v in snap.items():
        c = v["cambio_pct"]
        if c is None:
            continue
        if c > 20:
            zona.append(f"{d}: {graficos.numero(c, 1, ' %', True)}, más de un 20 %")
        elif c < 0 and d.startswith("FOODS"):
            zona.append(f"{d}: {graficos.numero(c, 1, ' %', True)}, negativo en alimentación")
        elif c < 0 or c > 10:
            zona.append(f"{d}: {graficos.numero(c, 1, ' %', True)}, fuera de 0 a 10 %")
    filas.append({"fila": "Cambio de la venta en días SNAP",
                  "rango": "de 0 a un 10 % más, sobre todo en alimentación; poco o nada en ocio y hogar",
                  "cifras": {d: v["cambio_pct"] for d, v in snap.items()},
                  "dentro": not zona, "zona_gris": zona})
    # Día de la semana: de 1,1 a 1,5; más del doble hace sospechar; el fin de semana, por encima
    ds = r["pregunta_4"]["dia_semana"]
    zona = [f"{d}: {graficos.numero(v['cociente'], 2)}, fuera de 1,1 a 1,5" for d, v in ds.items()
            if v["cociente"] is not None and not 1.1 <= v["cociente"] <= 1.5]
    zona += [f"{d}: el día más fuerte es el {NOMBRE_DIA[v['dia_fuerte']]}" for d, v in ds.items()
             if v["dia_fuerte"] not in ("Saturday", "Sunday")]
    distintos = {d: sorted(set(v.values())) for d, v in r["dia_fuerte_por_serie"].items()}
    zona += [f"{d}: el día más fuerte cambia de tienda a tienda ({', '.join(NOMBRE_DIA[x] for x in v)})"
             for d, v in distintos.items() if len(v) > 2]
    filas.append({"fila": "Cambio de la venta según el día de la semana",
                  "rango": "el día más fuerte vende de 1,1 a 1,5 veces el más flojo; el fin de semana, por encima",
                  "cifras": {d: {"cociente": v["cociente"], "dia_fuerte": v["dia_fuerte"],
                                 "dias_fuertes_por_tienda": distintos.get(d)} for d, v in ds.items()},
                  "dentro": not zona, "zona_gris": zona})
    # Totales de tienda y de categoría: suma exacta de sus departamentos; alimentación por encima en unidades
    tienda = {x["nombre"]: x["unidades"] for x in r["reparto"]["tienda"]}
    suma_series = pob.groupby("store_id")["unidades"].sum().to_dict()
    no_cuadran = [k for k in tienda if tienda[k] != int(suma_series.get(k, -1))]
    filas.append({"fila": "Totales de tienda",
                  "rango": "la suma exacta de sus 7 departamentos, en unidades y en dólares",
                  "cifras": {"tiendas_que_no_cuadran": no_cuadran},
                  "dentro": not no_cuadran, "zona_gris": [f"{k} no cuadra" for k in no_cuadran]})
    cat = {x["nombre"]: x["unidades"] for x in r["reparto"]["categoria"]}
    orden = sorted(cat, key=lambda k: -cat[k])
    zona = [] if not cat or orden[0] == "FOODS" else [f"{orden[0]} vende más unidades que alimentación"]
    if sum(cat.values()) != sum(tienda.values()):
        zona.append("la suma de las categorías no es la de las tiendas")
    filas.append({"fila": "Totales de categoría",
                  "rango": "alimentación por encima de hogar y de ocio en unidades; suman lo mismo que las tiendas",
                  "cifras": {"orden_unidades": orden, "suma_categorias": sum(cat.values()),
                             "suma_tiendas": sum(tienda.values())},
                  "dentro": not zona, "zona_gris": zona})
    for f in filas:
        f["criterio_propio"] = True
    no_medidas = ["Precio (es columna de origen: la compara calidad-datos, C-12 y C-13)", "Error de la previsión, en "
                  "unidades", "Error en dólares", "Sesgo", "Ventaja frente a las reglas",
                  "Error de repetir la semana anterior", "Error de la media de los últimos 28 días",
                  "Error de la media del mismo día de las 4 semanas anteriores"]
    return {"filas": filas, "no_se_miden_aqui": no_medidas}


# =====================================================================================================================
# 9. EL ANÁLISIS ENTERO, SIN ESCRIBIR NADA
# =====================================================================================================================

def analizar(tablas, transformacion, calidad, correccion, observaciones=None):
    """Todo el análisis en un diccionario. No escribe ficheros ni lee fechas: lo mismo entra, lo mismo sale.

    `observaciones` son las de la persona, leídas del JSON de la ejecución anterior (comprobación 16).
    """
    df = tablas["hechos_series"]
    posteriores = sorted(v["columna"] for v in transformacion.get("variables_generadas", [])
                         if v.get("informacion_posterior") and v["columna"] not in GRUPOS["objetivo"])
    comprobar_sin_posteriores(VARIABLES_FRENTE_OBJETIVO, posteriores)
    pob = poblacion(df).sort_values(["store_id", "dept_id", "date"], ignore_index=True)
    val = df.loc[df["periodo"].eq("validacion")]
    r = {"fecha_datos": transformacion.get("fecha_datos")}
    # Población: la construcción entera y, de la validación, sus tres totales
    r["poblacion"] = {
        "construccion": {"filas": int(len(pob)), "unidades": int(pob["unidades"].sum()),
                         "dolares": round(float(pob["dolares"].sum()), 2), "desde": pob["date"].min(),
                         "hasta": pob["date"].max(), "dias": int(pob["date"].nunique()),
                         "series": int(len(pob[["store_id", "dept_id"]].drop_duplicates())),
                         "dias_serie_fuera_del_error": int(pob["fuera_del_error"].sum()),
                         "filas_sin_fuera_del_error": int((~pob["fuera_del_error"].astype(bool)).sum())},
        "validacion": {"filas": int(len(val)), "unidades": int(val["unidades"].sum()),
                       "dolares": round(float(val["dolares"].sum()), 2)},
    }
    r["grupos_de_columnas"] = GRUPOS
    r["posteriores_al_dia"] = posteriores
    r["productos_por_departamento"] = {k: int(v) for k, v in
                                      tablas["dim_producto"]["dept_id"].value_counts().sort_index().items()}
    r["tipificacion"] = tipificar(pob)
    r["numericas"] = numericas(pob)
    r["categoricas"] = categoricas(pob)
    # Bloque 1, el reparto y el Pareto
    r["reparto"] = reparto(pob)
    serie_u = {f"{a} {b}": int(v) for (a, b), v in pob.groupby(["store_id", "dept_id"])["unidades"].sum().items()}
    serie_d = {f"{a} {b}": float(v) for (a, b), v in pob.groupby(["store_id", "dept_id"])["dolares"].sum().items()}
    r["pareto"] = {"series_unidades": pareto(serie_u), "series_dolares": pareto(serie_d)}
    for nombre in ("tienda", "departamento"):
        r["pareto"][f"{nombre}_unidades"] = pareto({x["nombre"]: x["unidades"] for x in r["reparto"][nombre]})
        r["pareto"][f"{nombre}_dolares"] = pareto({x["nombre"]: x["dolares"] for x in r["reparto"][nombre]})
    # Bloque 2, el ritmo y la autocorrelación
    r["ritmo"] = ritmo(pob)
    r["autocorrelacion"] = autocorrelacion(pob)
    r["series_de_negocio"] = series_de_negocio(pob)
    # Bloque 3, saltos y ceros
    r["saltos"] = saltos(pob)
    r["ceros"] = ceros(pob)
    # Bloque 4, la pregunta 4
    r["pregunta_4"] = {"snap": efecto_snap(pob), "snap_por_estado": efecto_snap_por_estado(pob),
                       "eventos": efecto_eventos(pob), "dia_semana": efecto_dia_semana(pob),
                       "mes": efecto_mes(pob), "precio": precio_spearman(pob)}
    r["dia_fuerte_por_serie"] = dia_fuerte_por_serie(pob)
    r["frente_al_objetivo"] = frente_al_objetivo(pob, posteriores)
    r["lo_esperable"] = lo_esperable(pob, r)
    interpretar(r, calidad, correccion, observaciones or [])
    return limpio(r)


# =====================================================================================================================
# 10. HALLAZGOS, ALERTAS, HIPÓTESIS Y COMPROBACIONES (salen de las cifras calculadas)
# =====================================================================================================================

def interpretar(r, calidad, correccion, observaciones):
    """Escribe hallazgos, alertas, hipótesis, comprobaciones, parámetros, pendientes y lo que esperan los pasos
    siguientes, todo a partir de las cifras ya calculadas en r y de las observaciones de la persona."""
    p4 = r["pregunta_4"]
    dep = {x["nombre"]: x for x in r["reparto"]["departamento"]}
    mayor = max(dep.values(), key=lambda x: x["unidades"]) if dep else None
    pu = r["pareto"]["series_unidades"]
    ds = p4["dia_semana"]
    snap = p4["snap"]
    con_ef = [e for e in p4["eventos"] if e["cambio_pct"] is not None]
    sin_ef = [e for e in p4["eventos"] if e["cambio_pct"] is None]
    con_salto = [s for s in r["saltos"] if s["salto"]]
    acf7 = r["autocorrelacion"]["mediana_por_departamento"]
    hall = []
    if mayor:
        hall.append({"id": "H-01", "grafico": "g-reparto", "texto": (
            f"{mayor['nombre']} es el departamento que más vende: {n(mayor['parte_unidades_pct'], 1, ' %')} de las "
            f"unidades y {n(mayor['parte_dolares_pct'], 1, ' %')} de los dólares de la construcción"),
            "dimensiones_comprobadas": ["departamento", "tienda", "categoría", "estado"],
            "respaldo": f"{r['poblacion']['construccion']['filas']} días de serie; columnas unidades y dolares"})
    hall.append({"id": "H-02", "grafico": "g-pareto", "texto": (
        f"{pu['elementos_para_el_80']} de las {pu['elementos']} series ({n(pu['elementos_para_el_80_pct'], 1, ' %')}) "
        f"suman el 80 % de las unidades: la venta no se concentra en unas pocas"),
        "dimensiones_comprobadas": ["serie, en unidades y en dólares"],
        "respaldo": f"{pu['elementos']} series; columna unidades"})
    if ds:
        coc = [v["cociente"] for v in ds.values() if v["cociente"] is not None]
        fines = sum(v["dia_fuerte"] in ("Saturday", "Sunday") for v in ds.values())
        hall.append({"id": "H-03", "grafico": "g-dia-semana", "texto": (
            f"El día más fuerte vende de {n(min(coc), 2)} a {n(max(coc), 2)} veces el más flojo según el departamento; "
            f"en {fines} de los {len(ds)} departamentos el más fuerte cae en fin de semana"),
            "dimensiones_comprobadas": ["departamento", "serie (día más fuerte por tienda)"],
            "respaldo": f"{r['poblacion']['construccion']['filas_sin_fuera_del_error']} días de serie; columnas "
                        f"unidades y weekday"})
    if snap:
        alim = {d: v["cambio_pct"] for d, v in snap.items() if d.startswith("FOODS") and v["cambio_pct"] is not None}
        otros = {d: v["cambio_pct"] for d, v in snap.items() if not d.startswith("FOODS") and v["cambio_pct"] is not None}
        if alim and otros:
            hall.append({"id": "H-04", "grafico": "g-snap", "texto": (
                f"Los días SNAP suben la venta de alimentación de {n(min(alim.values()), 1, ' %')} a "
                f"{n(max(alim.values()), 1, ' %')} frente a los días sin SNAP de la misma quincena; en ocio y hogar el "
                f"cambio va de {n(min(otros.values()), 1, ' %')} a {n(max(otros.values()), 1, ' %')}"),
                "dimensiones_comprobadas": ["departamento", "estado"],
                "respaldo": "días 1 a 15 de la construcción; columnas unidades y snap"})
    if con_ef:
        baja = min(con_ef, key=lambda e: e["cambio_pct"])
        sube = max(con_ef, key=lambda e: e["cambio_pct"])
        tg = [e["cambio_pct"] for e in con_ef if e["evento"] == "Thanksgiving"]
        texto = (f"{len(con_ef)} pares de evento y departamento tienen 30 días de serie o más. La mayor bajada es "
                 f"{baja['evento']} en {baja['departamento']} ({n(baja['cambio_pct'], 1, ' %', True)}) y la mayor "
                 f"subida, {sube['evento']} en {sube['departamento']} ({n(sube['cambio_pct'], 1, ' %', True)})")
        if tg:
            texto += f"; Acción de Gracias baja todos los departamentos, de {n(max(tg), 1, ' %')} a {n(min(tg), 1, ' %')}"
        hall.append({"id": "H-05", "grafico": "g-accion-gracias", "texto": texto,
                     "dimensiones_comprobadas": ["departamento", "evento"],
                     "respaldo": "días de evento con su día normal; columnas unidades y event_name_1"})
    if r["saltos"]:
        por_dept = {}
        for s in con_salto:
            por_dept[s["departamento"]] = por_dept.get(s["departamento"], 0) + 1
        hall.append({"id": "H-06", "grafico": "g-saltos", "texto": (
            f"{len(con_salto)} de las {len(r['saltos'])} series tienen un salto de nivel en la construcción; "
            f"{sum(s['razon'] < 1 for s in con_salto)} son bajadas. Por departamento: "
            + "; ".join(f"{k} {v}" for k, v in sorted(por_dept.items()))),
            "dimensiones_comprobadas": ["serie", "departamento"],
            "respaldo": "media de 91 días después frente a 91 antes; columna unidades"})
    if acf7:
        a7 = {d: v["7"] for d, v in acf7.items() if v.get("7") is not None}
        a1 = {d: v["1"] for d, v in acf7.items() if v.get("1") is not None}
        if a7:
            hall.append({"id": "H-07", "grafico": None, "texto": (
                f"La autocorrelación a 7 días va de {n(min(a7.values()), 2)} a {n(max(a7.values()), 2)} en mediana por "
                f"departamento, frente a {n(min(a1.values()), 2)} a {n(max(a1.values()), 2)} a 1 día"),
                "dimensiones_comprobadas": ["serie", "departamento"],
                "respaldo": f"{len(r['autocorrelacion']['series'])} series; columna unidades"})
    mes = p4["mes"]
    if mes:
        extremo = min(((c, m_, v["cambio_pct"]) for c, x in mes.items() for m_, v in x["meses"].items()
                       if v["cambio_pct"] is not None), key=lambda z: z[2], default=None)
        if extremo:
            hall.append({"id": "H-08", "grafico": "g-mes", "texto": (
                f"El mes que menos vende frente a la media de los meses completos es {NOMBRE_MES[int(extremo[1])]} "
                f"en {extremo[0]} ({n(extremo[2], 1, ' %', True)})"),
                "dimensiones_comprobadas": ["categoría", "mes"],
                "respaldo": "meses completos de la construcción; columnas unidades y month"})
    pr = p4["precio"]["por_departamento"]
    if pr:
        vals = [v["mediana_spearman"] for v in pr.values() if v["mediana_spearman"] is not None]
        if vals:
            hall.append({"id": "H-09", "grafico": "g-precio", "texto": (
                f"La correlación de Spearman entre el precio de la semana anterior y las unidades de la semana va de "
                f"{n(min(vals), 2)} a {n(max(vals), 2)} en mediana por departamento: describe, no mide un efecto"),
                "dimensiones_comprobadas": ["serie", "departamento"],
                "respaldo": "semanas completas con precio; columnas precio_medio_semana_anterior y unidades"})
    r["hallazgos"] = hall

    # Alertas: las de este análisis, la zona gris y las heredadas de calidad y corrección
    al = []
    pc = r["poblacion"]["construccion"]
    al.append({"texto": (f"Los meses parciales ({', '.join(f'{NOMBRE_MES[x['mes']]} de {x['anio']}' for x in r['ritmo']['meses_parciales'])}) "
                         f"no entran en ninguna media por mes ni en las series de negocio"), "origen": None})
    al.append({"texto": (f"{pc['dias_serie_fuera_del_error']} días de serie fuera del error salen de los efectos, de "
                         f"las medias y del bloque frente al objetivo; los totales los incluyen"), "origen": None})
    for f in r["lo_esperable"]["filas"]:
        for z in f["zona_gris"]:
            al.append({"texto": f"Zona gris en «{f['fila']}» (criterio propio): {z}", "origen": "reglas-negocio §7"})
    sin_dias = sorted({e["evento"] for e in sin_ef if e["dias_serie"] == 0})
    if sin_dias:
        al.append({"texto": f"Sin días de serie dentro del error: {', '.join(sin_dias)}; no dan efecto", "origen": None})
    pocos = [e for e in sin_ef if e["dias_serie"] > 0]
    if pocos:
        al.append({"texto": "Eventos con menos de 30 días de serie, sin efecto: " + "; ".join(
            f"{e['evento']} en {e['departamento']}, {e['dias_serie']} días" for e in pocos), "origen": None})
    inter = r["ceros"]["series_intermitentes"]
    if inter:
        al.append({"texto": (f"{len(inter)} series de demanda intermitente ({', '.join(inter)}): un cambio de una o dos "
                             f"unidades mueve mucho sus porcentajes"), "origen": "correccion-datos, clases_de_ceros"})
    for v in r["frente_al_objetivo"]["variables"]:
        if v["posible_fuga"]:
            al.append({"texto": f"Posible fuga: {v['columna']} separa casi del todo {v['objetivo']}", "origen": None,
                       "tipo": "posible_fuga"})
    for c in r["posteriores_al_dia"]:
        al.append({"texto": (f"Posible fuga si se usara como variable: {c} se conoce al cerrar el día y sale de las "
                             f"unidades; aquí solo se describe"), "origen": "transformacion-datos, variables_generadas",
                   "tipo": "posible_fuga"})
    al.append({"texto": ("Posible fuga si se usara como variable: unidades y dólares del mismo día son los dos "
                         "objetivos; los dólares salen de las unidades por el precio"), "origen": None,
               "tipo": "posible_fuga"})
    for prob in (calidad or {}).get("problemas", []):
        if prob.get("id") in ("C-12", "C-13", "C-14", "C-15", "C-16", "C-19", "C-22"):
            al.append({"texto": f"{prob['resultado']}", "origen": f"calidad-datos {prob['id']}"})
    for dec in (correccion or {}).get("decisiones_usuario", []):
        al.append({"texto": f"{dec['pendiente']} decidida el {dec['fecha']}: {dec['decision']}",
                   "origen": f"correccion-datos {dec['problema_calidad']}"})
    resto = (correccion or {}).get("cifras_de_control", {}).get("resto_por_serie", {}).get("construccion", [])
    if resto:
        salto_de = {f"{s['tienda']} {s['departamento']}": s["fecha"] for s in con_salto}
        # Cuenta las series cuyos ceros de la clase resto caen en la ventana anterior a su salto (91 días)
        antes_del_salto = [x for x in resto if x["serie"] in salto_de and x["hasta"] < salto_de[x["serie"]]
                           and (pd.Timestamp(salto_de[x["serie"]]) - pd.Timestamp(x["hasta"])).days <= VENTANA_SALTO]
        al.append({"texto": (f"Anomalía concentrada: los días a cero de la clase resto caen en {len(resto)} series; "
                             f"{len(antes_del_salto)} de ellas los tienen en los {VENTANA_SALTO} días anteriores a su "
                             f"salto de nivel ("
                             + "; ".join(f"{x['serie']}, {x['dias']} días hasta el {x['hasta']}" for x in antes_del_salto)
                             + "). Afecta a series que se prevén y coincide con otra señal: el salto"),
                   "origen": "correccion-datos, resto_por_serie"})
    al.append({"texto": "El recorte tiene 500 de los 3.049 productos: un total del caso no es un total de Walmart",
               "origen": "reglas-negocio §3"})
    for i, a in enumerate(al, 1):
        a["id"] = f"A-{i:02d}"
    r["alertas"] = al

    # Hipótesis, con lo que haría falta y las cinco explicaciones alternativas (comprobación 8)
    hip = []
    if con_salto:
        fechas = {}
        for s in con_salto:
            fechas.setdefault((s["tienda"], s["fecha"]), []).append(s["departamento"])
        juntos = [(k, v) for k, v in fechas.items() if len(v) >= 2]
        if juntos:
            (tienda, fecha), deps = max(juntos, key=lambda kv: len(kv[1]))
            hip.append({"id": "Hi-01", "texto": (
                f"En {tienda} saltan a la vez {len(deps)} departamentos el {fecha} ({', '.join(deps)}): puede ser un "
                f"cambio de la tienda o productos que empiezan a venderse; también un error de carga"),
                "que_haria_falta": "la primera venta de cada producto en esa tienda, que está en venta_corregido; "
                                   "un dato de la tienda que no está en la tabla",
                "alternativas": "tamaño del grupo: no; calendario: no cae en un evento; regresión a la media: no, dura "
                                "meses; causa al revés: no aplica; variable que no está: la reforma o el surtido"})
    if snap:
        top = max(snap.items(), key=lambda kv: kv[1]["cambio_pct"] if kv[1]["cambio_pct"] is not None else -1e9)
        hip.append({"id": "Hi-02", "texto": (
            f"La subida de {top[0]} en días SNAP ({n(top[1]['cambio_pct'], 1, ' %', True)}) puede deberse a la ayuda "
            f"alimentaria o a algo que coincide con los días SNAP dentro de la quincena"),
            "que_haria_falta": "el mismo cociente por estado con días de calendario parecidos; el gasto con la ayuda, "
                               "que no está en los datos",
            "alternativas": "tamaño del grupo: miles de días de serie; calendario: SNAP cae en días fijos de cada "
                            "estado; regresión a la media: no; causa al revés: no; variable que no está: la nómina"})
    hip.append({"id": "Hi-03", "texto": ("La correlación entre precio y unidades no dice que el precio mueva la venta: "
                                         "los precios casi no cambian y el precio medio cambia también cuando entra un "
                                         "producto"),
                "que_haria_falta": "cambios de precio de un mismo producto con la venta de ese producto",
                "alternativas": "una variable que no está: la entrada de productos mueve a la vez precio y unidades"})
    r["hipotesis"] = hip

    # Comprobaciones de comprobaciones.md con su estado, calculado de lo que hay
    zona_gris = sum(len(f["zona_gris"]) for f in r["lo_esperable"]["filas"])
    sen = [s for x in r["numericas"] for s in x["senales"]]
    concentrado = pu["clases"]["A"]["elementos"] / pu["elementos"] * 100 <= CONCENTRACION_A if pu["elementos"] else False
    comp = [
        ("1 Tiempo", "aplicada_con_resultado" if r["ritmo"]["meses_parciales"] else "aplicada_sin_nada_relevante",
         "meses parciales marcados; serie semanal y mensual"),
        ("2 Pareto y ABC", "aplicada_con_resultado",
         "series, tiendas y departamentos, en unidades y dólares" + ("; concentrado" if concentrado else
                                                                     "; la clase A no es un grupo pequeño")),
        ("3 Respaldo de cada cifra", "aplicada_con_resultado", "cada hallazgo con filas y columnas"),
        ("4 Datos personales", "no_aplica", "no hay columnas de personas (reglas, apartado 9)"),
        ("5 Códigos sin etiqueta", "aplicada_sin_nada_relevante",
         "wday, wm_yr_wk, snap y los tipos de evento están documentados; las magnitudes tienen unidad"),
        ("6 Reproducibilidad", "aplicada_con_resultado", "versiones, fecha y huellas en Contexto"),
        ("7 Correlaciones", "aplicada_con_resultado", "Pearson y Spearman del precio con los dos objetivos"),
        ("8 Forma de las hipótesis", "aplicada_con_resultado", f"{len(hip)} hipótesis con lo que haría falta"),
        ("9 Variables asimétricas", "aplicada_con_resultado", "medianas en el bloque frente al objetivo"),
        ("10 Gráficos", "aplicada_con_resultado", "un eje, títulos calculados y sin gráficos repetidos"),
        ("11 Series de negocio", "aplicada_con_resultado", "media móvil, variaciones, tendencias y CAGR"),
        ("12 Frente al objetivo", "aplicada_con_resultado", f"{graficos.numero(r['frente_al_objetivo']['n_filas'])} filas de construcción"),
        ("13 Discreta o continua", "aplicada_con_resultado",
         f"límite min(20, 5 % de las filas) = {r['tipificacion']['limite_discreta']}"),
        ("14 Texto", "no_aplica", "no hay texto libre: los nombres de evento son categorías"),
        ("15 Alta cardinalidad", "aplicada_sin_nada_relevante",
         "ninguna categórica pasa de 50 valores; d y wm_yr_wk son identificadores"),
        ("16 Observaciones de la persona", "aplicada_con_resultado" if observaciones else "aplicada_sin_nada_relevante",
         f"{len(observaciones)} observaciones de la persona" if observaciones else
         "apartado vacío, a la espera de la persona"),
        ("17 Tabla de estadísticos", "aplicada_con_resultado" if sen else "aplicada_sin_nada_relevante",
         "; ".join(f"{x['columna']}: {', '.join(x['senales'])}" for x in r["numericas"] if x["senales"]) or "sin señales"),
        ("18 Lo esperable", "aplicada_con_resultado" if zona_gris else "aplicada_sin_nada_relevante",
         f"{zona_gris} puntos de zona gris"),
    ]
    r["comprobaciones"] = [{"comprobacion": a, "estado": b, "detalle": c} for a, b, c in comp]
    # Las observaciones de la persona se conservan tal como las escribió (comprobación 16)
    r["observaciones"] = list(observaciones)
    r["parametros"] = [
        {"nombre": "numérica discreta", "valor": f"entera y con como mucho {r['tipificacion']['limite_discreta']} "
                                                 f"valores distintos", "origen": "por defecto (parametros.md)"},
        {"nombre": "filas mínimas frente al objetivo", "valor": FILAS_MINIMAS, "origen": "por defecto y petición"},
        {"nombre": "alta cardinalidad", "valor": "más de 50 valores distintos", "origen": "por defecto"},
        {"nombre": "las más frecuentes en alta cardinalidad", "valor": 10, "origen": "por defecto"},
        {"nombre": "texto muy corto", "valor": "menos de 3 caracteres", "origen": "por defecto"},
        {"nombre": "diagrama de caja", "valor": "no se dibuja: miles de filas", "origen": "por defecto"},
        {"nombre": "parte con que se cruza el objetivo", "valor": "construcción", "origen": "por defecto"},
        {"nombre": "mínimo de días de serie por evento", "valor": MINIMO_DIAS_EVENTO, "origen": "planteamientos"},
        {"nombre": "días del mes con que se compara SNAP", "valor": f"1 a {DIA_MAXIMO_SNAP}", "origen": "planteamientos"},
        {"nombre": "semanas del día normal", "valor": SEMANAS_DIA_NORMAL, "origen": "planteamientos"},
        {"nombre": "retardos de la autocorrelación", "valor": RETARDOS_ACF, "origen": "petición"},
        {"nombre": "salto de nivel", "valor": f"ventanas de {VENTANA_SALTO} días, {MINIMO_VENTANA} con dato, razón "
                                              f"{UMBRAL_SALTO}", "origen": "reconocimiento (D1)"},
        {"nombre": "clases ABC", "valor": f"A hasta el {PARETO_A} %, B hasta el {PARETO_B} %; el elemento que cruza "
                                          f"el corte va en la clase de antes", "origen": "comprobación 2"},
        {"nombre": "grupo pequeño que acumula casi todo", "valor": f"clase A con el {CONCENTRACION_A} % de los "
                                                                   f"elementos o menos", "origen": "elegido antes de calcular"},
        {"nombre": "variable que muestra diferencia", "valor": f"(mayor mediana - menor mediana) / mediana de todo, "
                                                               f"{UMBRAL_DIFERENCIA}", "origen": "elegido antes de calcular"},
        {"nombre": "posible fuga", "valor": f"eta² o |Spearman| de {UMBRAL_FUGA} o más", "origen": "elegido antes de calcular"},
        {"nombre": "señales de la tabla de estadísticos", "valor": f"media a más del {int(SENAL_MEDIA_MEDIANA * 100)} % "
                                                                   f"de la mediana; máximo {SENAL_ORDENES} veces el "
                                                                   f"mínimo positivo", "origen": "elegido antes de calcular"},
        {"nombre": "lectura de los rangos de «Lo esperable»", "valor": "decenas a pocos miles = 10 a 5.000 unidades; "
                                                                       "cientos a decenas de miles = 100 a 99.999 dólares; "
                                                                       "precio por unidad de 1 a 100 dólares",
         "origen": "elegido antes de calcular"},
    ]
    # Pendientes: cada fila de «Lo esperable» con zona gris se pregunta, no se corrige. La contesta la observación de
    # la persona cuyo «responde_a» es el nombre de la fila; sin ella, la pendiente sigue abierta
    respuestas = {o.get("responde_a"): o for o in observaciones if o.get("responde_a")}
    r["pendientes"] = [{"id": f"PE-{i:02d}", "tabla": TABLA, "columna": "unidades", "fila": f["fila"],
                        "pregunta": f"«{f['fila']}» cae en zona gris: {'; '.join(f['zona_gris'])}. ¿Se revisa el dato o "
                                    f"el rango, que es de criterio propio?",
                        "opciones": ["el dato es real y el rango de criterio propio se revisa",
                                     "se mira el dato antes de seguir"],
                        "respuesta": ({"texto": respuestas[f["fila"]].get("texto"),
                                       "fecha": respuestas[f["fila"]].get("fecha")} if f["fila"] in respuestas else None)}
                       for i, f in enumerate([f for f in r["lo_esperable"]["filas"] if f["zona_gris"]], 1)]
    r["premisa"] = {"afirmacion": None, "la_sostienen_los_datos": None}
    r["siguiente_paso"] = "hace_falta_modelar"
    # Lo que los pasos siguientes esperan, en cifras
    r["para_los_pasos_siguientes"] = {
        "reparto_por_departamento": r["reparto"]["departamento"],
        "efectos_por_departamento": {
            "snap_pct": {d: v["cambio_pct"] for d, v in snap.items()},
            "eventos_pct": [{"evento": e["evento"], "departamento": e["departamento"], "dias_serie": e["dias_serie"],
                             "cambio_pct": e["cambio_pct"]} for e in p4["eventos"]],
            "dia_semana_cociente": {d: v["cociente"] for d, v in ds.items()},
            "mes_por_categoria_pct": {c: {m_: v["cambio_pct"] for m_, v in x["meses"].items()} for c, x in mes.items()},
            "precio_mediana_spearman": {d: v["mediana_spearman"] for d, v in pr.items()}},
        "autocorrelacion_por_serie": r["autocorrelacion"]["series"],
        "series_con_salto": [{"serie": f"{s['tienda']} {s['departamento']}", "fecha": s["fecha"], "razon": s["razon"]}
                             for s in con_salto],
        "series_demanda_intermitente": inter,
        "alertas_posible_fuga": [a["texto"] for a in al if a.get("tipo") == "posible_fuga"],
    }
    r["teoria_aplicada"] = [
        {"apartado": "34.2", "por_que": "tipificar por papel: identificadores y códigos del calendario no son magnitudes"},
        {"apartado": "34.4 y 3.5", "por_que": "media junto a mediana y las cuatro señales de la tabla"},
        {"apartado": "34.6", "por_que": "histograma para las continuas; sin caja con miles de filas"},
        {"apartado": "34.7", "por_que": "cruce con el objetivo solo con la construcción; describe, no elige"},
        {"apartado": "3.7", "por_que": "Pearson y Spearman a la vez con el precio; Spearman por serie porque el precio "
                                       "casi no cambia y la relación puede no ser lineal"},
        {"apartado": "34.8 y 3.8", "por_que": "separar hallazgo, alerta, anomalía e hipótesis; sin causas"},
        {"apartado": "34.9 y 34.10", "por_que": "tiempo, Pareto y ABC, series de negocio"},
        {"apartado": "14.12", "por_que": "media móvil, variación interanual, estacionalidad y CAGR"},
        {"apartado": "31.2", "por_que": "autocorrelación como relación de la serie con su pasado, a 1, 7, 14 y 28 días"},
    ]


# =====================================================================================================================
# 11. EL INFORME HTML (sale entero del diccionario)
# =====================================================================================================================

def e(texto):
    """Escapa un texto para el HTML."""
    return html.escape(str(texto))


def tabla_html(cabecera, filas, numericas_=()):
    """Una tabla con las columnas numéricas a la derecha."""
    th = "".join(f"<th class=\"num\">{e(c)}</th>" if i in numericas_ else f"<th>{e(c)}</th>"
                 for i, c in enumerate(cabecera))
    cuerpo = "".join("<tr>" + "".join(f"<td class=\"num\">{e(v)}</td>" if i in numericas_ else f"<td>{e(v)}</td>"
                                      for i, v in enumerate(f)) + "</tr>" for f in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{cuerpo}</tbody></table>"


def bloque(id_, titulo, subtitulo, svg, fuente="Fuente: tabla de series, construcción."):
    """Un gráfico con su título, su subtítulo y su fuente debajo."""
    return (f"<div class=\"grafico\" id=\"{id_}\"><p class=\"g-titulo\">{e(titulo)}</p>"
            f"<p class=\"g-subtitulo\">{e(subtitulo)}</p>{svg}<p class=\"g-fuente\">{e(fuente)}</p></div>")


def informe_html(d, css):
    """Monta el HTML con la estructura de plantilla_informe.md, solo con cifras del diccionario d."""
    p4, pc, pv = d["pregunta_4"], d["poblacion"]["construccion"], d["poblacion"]["validacion"]
    s = []
    s.append(f"<h1>Análisis exploratorio de la tabla de series</h1><p>{e(pc['series'])} series, del {e(pc['desde'])} "
             f"al {e(pc['hasta'])}. Fecha de los datos: {e(d['fecha_datos'])}.</p>")
    # Resumen ejecutivo: de los hallazgos, las alertas y el siguiente paso
    s.append("<h2>Resumen ejecutivo</h2><ul>")
    for h in d["hallazgos"][:4]:
        s.append(f"<li>{e(h['texto'])}.</li>")
    zg = sum(len(f["zona_gris"]) for f in d["lo_esperable"]["filas"])
    s.append(f"<li>Lo esperable deja {zg} puntos en zona gris, todos con rangos de criterio propio: se preguntan, no se "
             f"corrigen. El siguiente paso es modelar.</li></ul>")
    # Contexto
    s.append("<h2>Contexto</h2>")
    s.append(f"<p>Cada fila es la venta de un departamento en una tienda un día, en unidades y en dólares. La clave es "
             f"tienda, departamento y día. El análisis usa solo la construcción: {graficos.numero(pc['filas'])} días de "
             f"serie con {graficos.numero(pc['unidades'])} unidades y {graficos.numero(pc['dolares'], 2)} dólares. De "
             f"la validación solo se dan sus totales: {graficos.numero(pv['filas'])} días de serie, "
             f"{graficos.numero(pv['unidades'])} unidades y {graficos.numero(pv['dolares'], 2)} dólares.</p>")
    s.append(f"<p>Los {pc['dias_serie_fuera_del_error']} días de serie fuera del error (el 25 de diciembre y los cierres de tienda "
             f"de otros días) cuentan en los totales y en el reparto. Salen de las medias, de los efectos y del bloque frente "
             f"al objetivo. Columnas posteriores al día, que solo se describen: {e(', '.join(d['posteriores_al_dia']))}.</p>")
    ent = d.get("entorno", {})
    s.append(tabla_html(["Tabla", "Filas", "Columnas", "Huella"], [[x["ruta"], graficos.numero(x["filas"]),
                                                                    x["columnas"], x["sha256"][:16] + "…"]
                                                                   for x in d.get("entradas", [])], (1, 2)))
    s.append(f"<p class=\"fuente\">Fuente: data/processed. Ejecutado el {e(d.get('fecha_ejecucion'))} con Python "
             f"{e(ent.get('python'))}, pandas {e(ent.get('pandas'))}, numpy {e(ent.get('numpy'))}, pyarrow "
             f"{e(ent.get('pyarrow'))}, matplotlib {e(ent.get('matplotlib'))} y scipy {e(ent.get('scipy'))}.</p>")
    # Visión general: grupos de columnas, tipificación y reparto
    s.append("<h2>Visión general</h2>")
    s.append(tabla_html(["Grupo", "Columnas"], [[g, ", ".join(c)] for g, c in d["grupos_de_columnas"].items()]))
    s.append("<p class=\"fuente\">Fuente: petición del paso 4 y reglas de transformación §1.</p>")
    filas_rep = []
    for nivel in ("estado", "tienda", "categoria", "departamento"):
        for x in d["reparto"][nivel]:
            filas_rep.append([nivel, x["nombre"], graficos.numero(x["unidades"]),
                              graficos.numero(x["parte_unidades_pct"], 1, " %"), graficos.numero(x["dolares"]),
                              graficos.numero(x["parte_dolares_pct"], 1, " %")])
    s.append(tabla_html(["Nivel", "Nombre", "Unidades", "Parte", "Dólares", "Parte"], filas_rep, (2, 3, 4, 5)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción, todos los días. Partes sobre el total de "
             "cada magnitud.</p>")
    dep = d["reparto"]["departamento"]
    s.append(bloque("g-reparto", "Parte de cada departamento en unidades y en dólares",
                    "Porcentaje del total de la construcción",
                    graficos.barras_ordenadas([x["nombre"] for x in dep],
                                              {"unidades": [x["parte_unidades_pct"] for x in dep],
                                               "dólares": [x["parte_dolares_pct"] for x in dep]},
                                              decimales=1, unidad=" %", medida="parte del total")))
    filas_p = []
    for nombre, p in d["pareto"].items():
        filas_p.append([nombre.replace("_", " "), p["elementos"], p["elementos_para_el_80"],
                        graficos.numero(p["elementos_para_el_80_pct"], 1, " %"),
                        *[f"{p['clases'][c]['elementos']} ({graficos.numero(p['clases'][c]['parte_pct'] or 0, 1, ' %')})"
                          for c in "ABC"]])
    s.append(tabla_html(["Pareja", "Elementos", "Para el 80 %", "Parte de elementos", "A", "B", "C"], filas_p, (1, 2, 3)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción. Con 7 o 10 elementos el Pareto dice poco.</p>")
    pu = d["pareto"]["series_unidades"]
    s.append(bloque("g-pareto", f"{pu['elementos_para_el_80']} de {pu['elementos']} series suman el 80 % de las unidades",
                    "Parte acumulada de las unidades, series de mayor a menor",
                    graficos.curva_acumulada([x["valor"] for x in pu["ranking"]], marcas=(20, 50))))
    # Variables numéricas
    s.append("<h2>Variables numéricas</h2>")
    s.append(tabla_html(["Columna", "Válidos", "Media", "Mediana", "Desviación", "Mínimo", "P99", "Máximo", "Señales"],
                        [[x["columna"], graficos.numero(x["validos"]), graficos.numero(x["media"], 2),
                          graficos.numero(x["mediana"], 2), graficos.numero(x["desviacion"], 2),
                          graficos.numero(x["minimo"], 2), graficos.numero(x["percentiles"]["99"], 2),
                          graficos.numero(x["maximo"], 2), ", ".join(x["senales"]) or "ninguna"]
                         for x in d["numericas"]], (1, 2, 3, 4, 5, 6, 7)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción sin días fuera del error. La media lejos de la "
             "mediana en unidades y dólares mezcla departamentos de tamaño muy distinto: dos grupos, no una escala "
             "rota.</p>")
    hist = d["_histogramas"]
    # Un histograma por magnitud, a todo el ancho: con miles de filas las cuentas de cada tramo no caben en media fila
    for c, unidad in [("unidades", ""), ("dolares", " $"), ("precio_medio_semana_anterior", " $")]:
        s.append(bloque(f"g-hist-{c}", f"Distribución de {c}", "Días de serie por tramo",
                        graficos.histograma(hist[c], intervalos=12, decimales=2 if c.startswith("precio") else 0,
                                            unidad=unidad, ancho=1000, medida="días de serie")))
    # Variables categóricas, con los ceros de clase_cero
    s.append("<h2>Variables categóricas</h2>")
    s.append(tabla_html(["Columna", "Unidad", "Total", "Distintos", "Más frecuente"],
                        [[x["columna"], x["unidad"], graficos.numero(x["total"]), x["distintos"],
                          max(x["frecuencias"].items(), key=lambda kv: kv[1])[0]] for x in d["categoricas"]], (2, 3)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción. Cada columna se cuenta en su unidad: el "
             "calendario por días, SNAP por días de estado, las dimensiones por series.</p>")
    ev = next(x for x in d["categoricas"] if x["columna"] == "event_name_1")
    evs = {k: v for k, v in ev["frecuencias"].items() if k != "sin evento"}
    if evs:
        s.append(bloque("g-eventos", "Días de cada evento en la construcción",
                        f"{ev['frecuencias'].get('sin evento', 0)} de {ev['total']} días no tienen evento",
                        graficos.barras_ordenadas(list(evs), list(evs.values()), medida="días")))
    cz = d["ceros"]["por_clase"]
    if cz:
        s.append(bloque("g-ceros", f"{graficos.numero(d['ceros']['dias_serie_a_cero'])} días de serie a cero, por clase",
                        "Días de serie de la construcción; clase_cero es posterior al día y solo se describe",
                        graficos.barras_ordenadas(list(cz), list(cz.values()), medida="días de serie")))
    filas_c = [[f"{x['tienda']} {x['departamento']}", x["dias_cero"],
                ", ".join(f"{k} {v}" for k, v in x["por_clase"].items())]
               for x in sorted(d["ceros"]["por_serie"], key=lambda x: -x["dias_cero"]) if x["dias_cero"] > 3]
    s.append(tabla_html(["Serie", "Días a cero", "Por clase"], filas_c, (1,)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción; solo las series con más de 3 días a cero.</p>")
    # Análisis temporal: series de negocio, ritmo, saltos y la pregunta 4
    s.append("<h2>Análisis temporal</h2>")
    sn = d["series_de_negocio"]
    meses = [f"{CORTO_MES[x['mes']]} {x['anio']}" for x in sn["meses"]]
    if meses:
        mm = sn["unidades"]["media_movil_3"]
        inicio = next((i for i, v in enumerate(mm) if v is not None), len(mm))
        series_l = {"media del mes": [x["unidades"] for x in sn["meses"]][inicio:]}
        if inicio < len(mm):
            series_l["media móvil de 3 meses"] = mm[inicio:]
        s.append(bloque("g-mensual", "Unidades por día de serie en cada mes completo",
                        f"Media por día de serie de las {pc['series']} series, sin meses parciales ni días fuera del error",
                        graficos.linea_tiempo(meses[inicio:], series_l, decimales=1, ancho=1000, medida="unidades")))
        u = sn["unidades"]
        s.append(f"<p>Tendencia lineal: {n(u.get('tendencia_lineal_por_mes'), 2)} unidades por día de serie cada mes, "
                 f"con R² de {n(u.get('r2_lineal'), 2)}. La exponencial da {n(u.get('tendencia_exponencial_pct_mes'), 2, ' %')} "
                 f"al mes, con R² de {n(u.get('r2_exponencial'), 2)}. Último mes frente al anterior: "
                 f"{n(u['variacion_ultimo_mes_pct'], 1, ' %', True)}; frente al mismo mes del año anterior: "
                 f"{n(u['variacion_interanual_ultimo_mes_pct'], 1, ' %', True)}. CAGR de {e(u['cagr']['desde'])} a "
                 f"{e(u['cagr']['hasta'])}: {n(u['cagr']['pct'], 1, ' %')} en unidades y "
                 f"{n(sn['dolares']['cagr']['pct'], 1, ' %')} en dólares. Una tendencia describe, no prevé.</p>")
    if sn["semanas"]:
        # En la escala del día de serie la marca más baja del eje cae sobre la primera fecha; a escala de todas las
        # series juntas (la media por el número de series) se lee igual y las marcas no se pisan
        s.append(bloque("g-semanal", f"Unidades al día de las {pc['series']} series juntas en cada semana completa",
                        "Segunda granularidad: las semanas de Walmart, de sábado a viernes; media por día de serie "
                        f"por {pc['series']}",
                        graficos.linea_tiempo([f"{x['desde'][8:10]}/{x['desde'][5:7]}/{x['desde'][2:4]}"
                                               for x in sn["semanas"]],
                                              {"": [x["unidades"] * pc["series"] for x in sn["semanas"]]}, decimales=0,
                                              ancho=1000,
                                              medida="unidades")))
    rd = d["ritmo"]["dia_semana"]
    s.append(tabla_html(["Departamento"] + [NOMBRE_DIA[x] for x in DIAS_SEMANA],
                        [[k] + [graficos.numero(v[x]["unidades"], 1) if x in v else "" for x in DIAS_SEMANA]
                         for k, v in rd.items()], tuple(range(1, 8))))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción sin días fuera del error; unidades por día de "
             "serie.</p>")
    rm = d["ritmo"]["mes"]
    s.append(tabla_html(["Departamento"] + [CORTO_MES[m_] for m_ in range(1, 13)],
                        [[k] + [graficos.numero(v[str(m_)]["unidades"], 1) if str(m_) in v else "" for m_ in range(1, 13)]
                         for k, v in rm.items()], tuple(range(1, 13))))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción sin meses parciales ni días fuera del error; "
             "unidades por día de serie.</p>")
    ac = d["autocorrelacion"]["mediana_por_departamento"]
    s.append(tabla_html(["Departamento"] + [f"{k} días" for k in RETARDOS_ACF],
                        [[k] + [graficos.numero(v[str(x)], 2) for x in RETARDOS_ACF] for k, v in ac.items()],
                        tuple(range(1, 5))))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción. Mediana por departamento de la "
             "autocorrelación de cada serie; la de cada serie está en el JSON.</p>")
    cs = [x for x in d["saltos"] if x["salto"]]
    if cs:
        cs = sorted(cs, key=lambda x: -x["razon"])
        s.append(bloque("g-saltos", f"{len(cs)} series con salto de nivel, con su razón",
                        "Media de los 91 días después entre la de los 91 antes, en el día del mayor cambio",
                        graficos.barra_divergente([f"{x['tienda']} {x['departamento']} {x['fecha']}" for x in cs],
                                                  [x["razon"] for x in cs], referencia=1, rotulo_referencia="sin cambio",
                                                  decimales=2, medida="razón")))
    s.append("<h3>Los días que cambian la venta (pregunta 4)</h3>")
    s.append(f"<p>Cada efecto es un cociente de medias de unidades por día de serie, menos 1. Sin los "
             f"{pc['dias_serie_fuera_del_error']} días de serie fuera del error.</p>")
    ds = p4["dia_semana"]
    s.append(bloque("g-dia-semana", "El día más fuerte entre el más flojo, por departamento",
                    "Venta media del día de la semana más fuerte entre la del más flojo",
                    graficos.barras_ordenadas(list(ds), [v["cociente"] for v in ds.values()], decimales=2,
                                              medida="cociente")))
    sp = p4["snap"]
    s.append(bloque("g-snap", "Cambio de la venta en días SNAP, por departamento",
                    "Días SNAP frente a días sin SNAP, solo los días 1 a 15 del mes, en %",
                    graficos.barra_divergente(list(sp), [v["cambio_pct"] or 0 for v in sp.values()], decimales=1,
                                              unidad=" %", medida="cambio de la venta")))
    est = p4["snap_por_estado"]
    s.append(tabla_html(["Departamento"] + sorted({k for v in est.values() for k in v}),
                        [[k] + [n(v.get(x), 1, " %") for x in sorted({k2 for v2 in est.values() for k2 in v2})]
                         for k, v in est.items()], (1, 2, 3)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción; el mismo cociente de SNAP por estado.</p>")
    tg = [x for x in p4["eventos"] if x["evento"] == "Thanksgiving" and x["cambio_pct"] is not None]
    if tg:
        s.append(bloque("g-accion-gracias", "Acción de Gracias baja la venta en todos los departamentos",
                        "Cambio de la venta frente al día normal, en %",
                        graficos.barra_divergente([x["departamento"] for x in tg], [x["cambio_pct"] for x in tg],
                                                  decimales=1, unidad=" %", n=[x["dias_serie"] for x in tg],
                                                  medida="cambio de la venta")))
    deps = sorted({x["departamento"] for x in p4["eventos"]})
    evn = sorted({x["evento"] for x in p4["eventos"]})
    idx = {(x["evento"], x["departamento"]): x for x in p4["eventos"]}
    s.append(tabla_html(["Evento"] + deps,
                        [[ev_] + [(n(idx[(ev_, dp)]["cambio_pct"], 1, " %") if idx[(ev_, dp)]["cambio_pct"] is not None
                                   else f"{idx[(ev_, dp)]['dias_serie']} días") for dp in deps] for ev_ in evn],
                        tuple(range(1, len(deps) + 1))))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción. Sin efecto, los días de serie que tiene.</p>")
    me = p4["mes"]
    if me:
        s.append(bloque("g-mes", "Cambio de la venta de cada mes frente a la media de los meses completos",
                        "Por categoría, en %",
                        graficos.linea_tiempo([CORTO_MES[m_] for m_ in range(1, 13)],
                                              {c: [x["meses"].get(str(m_), {}).get("cambio_pct") or 0
                                                   for m_ in range(1, 13)] for c, x in me.items()},
                                              decimales=1, unidad=" %", ancho=1000, medida="cambio")))
    pr = p4["precio"]["por_departamento"]
    s.append(bloque("g-precio", "Spearman del precio de la semana anterior con las unidades de la semana",
                    "Mediana de las series de cada departamento; solo describe",
                    graficos.barra_divergente(list(pr), [v["mediana_spearman"] or 0 for v in pr.values()],
                                              decimales=2, medida="Spearman")))
    # Frente al objetivo
    fo = d["frente_al_objetivo"]
    s.append("<h2>Frente al objetivo</h2>")
    s.append(f"<p>Con las filas de la construcción sin días fuera del error: {graficos.numero(fo['n_filas'])}. "
             f"Los objetivos son cantidades, unidades y dólares. Una categoría con menos de {FILAS_MINIMAS} filas no se "
             f"compara. Describe; no elige variables.</p>")
    filas_f = []
    for v in fo["variables"]:
        if v["tipo"] == "magnitud":
            filas_f.append([v["objetivo"], v["columna"], f"Pearson {n(v['pearson'], 3)}; Spearman {n(v['spearman'], 3)}",
                            n(v["diferencia"], 2), "sí" if v["posible_fuga"] else "no"])
        else:
            cats = sorted(v["categorias"], key=lambda c: -c["mediana"])
            filas_f.append([v["objetivo"], v["columna"],
                            "; ".join(f"{c['valor']} {graficos.numero(c['mediana'], 1)} (n = {graficos.numero(c['filas'])})"
                                      for c in cats[:4]) + ("…" if len(cats) > 4 else ""),
                            n(v["diferencia"], 2), "sí" if v["posible_fuga"] else "no"])
    s.append(tabla_html(["Objetivo", "Variable", "Medianas o correlación", "Diferencia", "Posible fuga"], filas_f, (3,)))
    s.append("<p class=\"fuente\">Fuente: tabla de series, construcción. Diferencia: mayor mediana menos menor, entre la "
             "mediana de todo; en el precio, |Spearman|.</p>")
    top = [v for v in fo["variables"] if v["objetivo"] == "unidades" and v["tipo"] == "categorica"
           and v.get("muestra_diferencia")][:2]
    for v in top:
        cats = [c for c in sorted(v["categorias"], key=lambda c: -c["mediana"]) if c["se_compara"]][:12]
        s.append(bloque(f"g-obj-{v['columna']}", f"Mediana de unidades por {v['columna']}",
                        "Unidades por día de serie; entre paréntesis, las filas",
                        graficos.barras_ordenadas([c["valor"] for c in cats], [c["mediana"] for c in cats],
                                                  decimales=1, n=[c["filas"] for c in cats], medida="mediana")))
    fugas = d["para_los_pasos_siguientes"]["alertas_posible_fuga"]
    s.append("<ul>" + "".join(f"<li>{e(x)}.</li>" for x in fugas) + "</ul>")
    # Hallazgos, alertas, hipótesis, observaciones
    s.append("<h2>Hallazgos principales</h2><ul>")
    for h in d["hallazgos"]:
        ref = f" Gráfico: <a href=\"#{h['grafico']}\">ver</a>." if h["grafico"] else ""
        s.append(f"<li>{e(h['texto'])}. Dimensiones comprobadas: {e(', '.join(h['dimensiones_comprobadas']))}. "
                 f"Respaldo: {e(h['respaldo'])}.{ref}</li>")
    s.append("</ul><h2>Alertas y limitaciones</h2><ul>")
    for a in d["alertas"]:
        s.append(f"<li>{e(a['id'])}. {e(a['texto'])}." + (f" Origen: {e(a['origen'])}." if a["origen"] else "") + "</li>")
    s.append("</ul><h2>Hipótesis y preguntas abiertas</h2><ul>")
    for h in d["hipotesis"]:
        s.append(f"<li>{e(h['texto'])}. Haría falta: {e(h['que_haria_falta'])}. Otras explicaciones repasadas: "
                 f"{e(h['alternativas'])}.</li>")
    for p in d["pendientes"]:
        contesta = (f" Contestada el {e(p['respuesta']['fecha'])}: {e(p['respuesta']['texto'])}"
                    if p.get("respuesta") else " Sin contestar.")
        s.append(f"<li>{e(p['id'])}. {e(p['pregunta'])}{contesta}</li>")
    s.append("</ul><h2>Observaciones de la persona</h2>")
    s.append("<p>Todavía no hay observaciones. La persona responsable las escribe y se vuelve a ejecutar el "
             "análisis.</p>" if not d["observaciones"] else
             "<ul>" + "".join(f"<li>{e(o['bloque'])}, {e(o['tipo'])}: {e(o['texto'])} ({e(o['fecha'])})</li>"
                              for o in d["observaciones"]) + "</ul>")
    s.append("<h2>Comprobaciones aplicadas</h2>")
    s.append(tabla_html(["Comprobación", "Estado", "Lo calculado"],
                        [[c["comprobacion"], c["estado"].replace("_", " "), c["detalle"]] for c in d["comprobaciones"]]))
    s.append("<p class=\"fuente\">Fuente: comprobaciones.md del método.</p>")
    lf = d["lo_esperable"]
    s.append(tabla_html(["Fila de «Lo esperable»", "Rango", "Dentro", "Zona gris"],
                        [[f["fila"], f["rango"], "sí" if f["dentro"] else "no", "; ".join(f["zona_gris"]) or "ninguna"]
                         for f in lf["filas"]]))
    s.append(f"<p class=\"fuente\">Fuente: reglas de negocio §7; todos los rangos son de criterio propio. No se miden "
             f"aquí: {e('; '.join(lf['no_se_miden_aqui']))}.</p>")
    s.append("<h2>Parámetros usados</h2>")
    s.append(tabla_html(["Parámetro", "Valor", "De dónde sale"], [[p["nombre"], p["valor"], p["origen"]]
                                                                  for p in d["parametros"]]))
    s.append("<p class=\"fuente\">Fuente: parametros.md del método, planteamientos y petición del paso 4.</p>")
    s.append("<h2>Datos personales</h2>")
    s.append(f"<p>{e(d['datos_personales_nota'])}</p>")
    s.append("<h2>Siguiente paso</h2>")
    abiertas = [p for p in d["pendientes"] if not p.get("respuesta")]
    s.append(f"<p>{e(d['siguiente_paso'].replace('_', ' '))}: la tabla está lista para preparar el modelo."
             + (f" Antes, la persona responsable contesta las {len(abiertas)} preguntas de zona gris que siguen "
                f"abiertas.</p>" if abiertas else " La persona responsable ya contestó la zona gris.</p>"))
    cuerpo = "\n".join(s)
    return (f"<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\"><title>Análisis exploratorio · "
            f"{TABLA}</title><style>{css}\nmain {{ margin-left: 0; }}\nh3 {{ font-size: 16px; }}</style></head>"
            f"<body><main><div class=\"pagina\">{cuerpo}</div></main></body></html>")


# =====================================================================================================================
# 12. EJECUCIÓN
# =====================================================================================================================

def leer_json(ruta):
    """Lee un JSON si existe; si no, un diccionario vacío."""
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def main(raiz):
    """Lee, analiza, comprueba las huellas y escribe el JSON y el HTML."""
    t0 = time.time()
    proc, inf = raiz / "data" / "processed", raiz / "informes"
    ruta_j = inf / f"analisis-exploratorio__{TABLA}.json"
    ruta_h = inf / f"analisis-exploratorio__{TABLA}.html"
    base = {"metodo": "analisis-exploratorio", "version_metodo": VERSION_METODO, "script": SCRIPT,
            "fecha_datos": None, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
            "entorno": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__,
                        "pyarrow": pyarrow.__version__, "matplotlib": matplotlib.__version__,
                        "scipy": scipy.__version__, "ejecutable": sys.executable}}
    # Las observaciones que la persona escribió en el JSON anterior se conservan, también si esta ejecución falla
    previas = leer_json(ruta_j).get("observaciones") or []
    base["observaciones"] = previas
    try:
        # Al empezar: la transformación tiene que estar bien
        transformacion = leer_json(inf / "transformacion-datos.json")
        base["fecha_datos"] = transformacion.get("fecha_datos")
        estado = transformacion.get("resultado", {}).get("estado")
        if estado in (None, "PARADO", "ERROR"):
            raise RuntimeError(f"transformacion-datos.json con estado {estado}: no se analiza")
        antes = {t: huella(proc / f"{t}.parquet") for t in TABLAS}
        tablas = {t: pd.read_parquet(proc / f"{t}.parquet") for t in TABLAS}
        d = analizar(tablas, transformacion, leer_json(inf / "calidad-datos.json"),
                     leer_json(inf / "correccion-datos.json"), previas)
        despues = {t: huella(proc / f"{t}.parquet") for t in TABLAS}
        cambiadas = [t for t in TABLAS if antes[t] != despues[t]]
        if cambiadas:
            raise RuntimeError(f"las tablas de entrada cambiaron: {cambiadas}")
        histos = {x["columna"]: x.pop("valores") for x in d["numericas"]}
        d.update(base)
        d["entradas"] = [{"ruta": f"data/processed/{t}.parquet", "sha256": antes[t], "filas": int(len(tablas[t])),
                          "columnas": int(tablas[t].shape[1])} for t in TABLAS]
        d["huellas_despues"] = {f"data/processed/{t}.parquet": despues[t] for t in TABLAS}
        d["dataset"] = {"ruta": f"data/processed/{TABLA}.parquet", "sha256": antes[TABLA]}
        d["datos_personales"] = []
        d["datos_personales_nota"] = (
            "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las "
            "reglas de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada "
            "de personas. Este análisis no usa ni deja ninguna columna de datos personales.")
        # AVISO mientras quede alguna pendiente sin contestar por la persona
        abiertas = [p for p in d["pendientes"] if not p.get("respuesta")]
        estado = "AVISO" if abiertas else "OK"
        riesgo = "medio" if abiertas else "bajo"
        pc = d["poblacion"]["construccion"]
        d["resultado"] = {"estado": estado, "riesgo": riesgo,
                          "resumen": (f"Exploratorio de {pc['series']} series en {graficos.numero(pc['filas'])} días de serie de la "
                                      f"construcción; {len(d['hallazgos'])} hallazgos, {len(d['alertas'])} alertas y "
                                      f"{len(d['pendientes'])} filas de «Lo esperable» en zona gris, "
                                      f"{len(d['pendientes']) - len(abiertas)} contestadas por la persona."),
                          "artefactos": [f"informes/{ruta_j.name}", f"informes/{ruta_h.name}"],
                          "siguiente": "la sesión principal rehace las cifras; después, las observaciones de la "
                                       "persona y otra ejecución"}
        d["duracion_segundos"] = round(time.time() - t0, 2)
        orden = ["metodo", "version_metodo", "script", "fecha_datos", "fecha_ejecucion", "entorno", "entradas",
                 "huellas_despues", "resultado", "pendientes", "dataset"]
        d = {**{k: d[k] for k in orden}, **{k: v for k, v in d.items() if k not in orden}}
        # El HTML se monta del mismo diccionario; los valores de los histogramas no van al JSON
        css = (CASO / "assets" / "estilo.css").read_text(encoding="utf-8")
        pagina = informe_html({**d, "_histogramas": histos}, css)
        inf.mkdir(parents=True, exist_ok=True)
        ruta_j.write_text(json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        ruta_h.write_text(pagina, encoding="utf-8")
        print(f"estado {estado}; {len(d['hallazgos'])} hallazgos; {len(d['alertas'])} alertas; "
              f"{d['duracion_segundos']} s")
        return 0
    except Exception as error:
        # Regla 5: el JSON se escribe también cuando falla, con su estado
        base["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(error).__name__}: {error}",
                             "artefactos": [f"informes/{ruta_j.name}"], "siguiente": "arreglar el fallo"}
        inf.mkdir(parents=True, exist_ok=True)
        ruta_j.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        raise


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Análisis exploratorio del caso 69")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta con la estructura del caso")
    sys.exit(main(Path(argumentos.parse_args().raiz)))
