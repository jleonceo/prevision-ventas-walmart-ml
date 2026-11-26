"""Comprobación del diseño del modelo de datos del caso 69 (método modelado-datos), con la petición 08 del 24/11/2026.

Lee las tres tablas corregidas de data/processed/ (venta, precios y calendario) sin alterarlas y comprueba lo que el
diseño de config/modelo/modelo-datos.md afirma sobre ellas: el grano y su clave, la jerarquía de producto y
tienda, el calendario sin huecos, las semanas de Walmart, las claves sin pareja que el diseño da por esperadas, los
dólares de la venta con el precio de su semana y los recuentos del registro de exclusiones. Mide además lo que separa
la media simple de la ponderada por unidades en el precio medio del departamento; la elegida es la simple
(planteamientos; el responsable del caso, 24/11/2026).

No cruza tablas: el precio de cada día se busca por índice de semana solo para contar y sumar. El único dataset que
guarda es el Calendario, y solo con el diseño aprobado por el responsable del caso y sin contradicciones (método, apartado 9). Escribe:
  - data/processed/calendario.parquet, el Calendario del modelo (modelo-datos.md §6), cuando se cumple lo anterior;
  - informes/modelado-datos.json, para integracion-datos y transformacion-datos;
  - informes/modelado-datos.md, generado de ese JSON en la misma ejecución.

Depende de informes/correccion-datos.json (scripts/03_correccion_datos.py): si su estado no es OK o la huella de una
tabla corregida no es la de su entrada en `salidas`, para (resultado.md, «Al empezar»).

Se ejecuta sin intervención manual:
  PYTHONUTF8=1 <python del entorno 69_prevision_ventas_walmart> -W error scripts/04_modelado_datos.py
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import hashlib
import json
import math
import platform
import re
import sys
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import pyarrow.parquet as pq

RAIZ = Path(__file__).resolve().parents[1]
PROCESADOS = RAIZ / "data" / "processed"
CORRECCION = RAIZ / "informes" / "correccion-datos.json"
CALIDAD = RAIZ / "informes" / "calidad-datos.json"
PROTECCION = RAIZ / "config" / "fuentes" / "proteccion-datos.json"
DISENO_REL = "config/modelo/modelo-datos.md"
DISENO = RAIZ / DISENO_REL
VERSION_METODO = "20/11/2026"  # versión del método modelado-datos con que se escribió este script
SALIDA_JSON = RAIZ / "informes" / "modelado-datos.json"
SALIDA_MD = RAIZ / "informes" / "modelado-datos.md"
CALENDARIO_REL = "data/processed/calendario.parquet"
SALIDA_CALENDARIO = RAIZ / CALENDARIO_REL
SCRIPT_REL = "scripts/04_modelado_datos.py"

# ── 1.1 Lo que fijan las reglas del caso ──
# Fecha de referencia y periodos (reglas, apartado 5). Los días del calendario posteriores no son de ningún periodo.
FECHA_DATOS = "2015-05-22"
PERIODOS = {"construccion": ("2011-01-29", "2014-05-22"), "validacion": ("2014-05-23", "2015-05-22")}
ENTRADAS = {"venta": "venta_corregido.parquet", "precios": "precios_corregido.parquet",
            "calendario": "calendario_corregido.parquet"}
SERIE = ["store_id", "dept_id"]
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
ETIQUETA = {"construccion": "construcción", "validacion": "validación", "sin_periodo": "sin periodo"}

# ── 1.2 Tablas de entrada: grano y clave, copiados del diseño (modelo-datos.md §3) ──
TABLAS = [
    {"tabla": "venta", "grano": "una fila por producto y tienda, con las unidades de cada día en 1.575 columnas "
                                "(d_1 a d_1575); el hecho es producto, tienda y día, que la transformación pasa a filas",
     "clave_grano": ["item_id", "store_id"], "clave_alternativa": ["id"], "tipo": "hechos",
     "columnas": ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]},
    {"tabla": "precios", "grano": "una fila por producto, tienda y semana de Walmart, con su precio",
     "clave_grano": ["store_id", "item_id", "wm_yr_wk"], "clave_alternativa": None, "tipo": "hechos",
     "columnas": ["store_id", "item_id", "wm_yr_wk", "sell_price"]},
    {"tabla": "calendario", "grano": "una fila por día", "clave_grano": ["d"], "clave_alternativa": ["date"],
     "tipo": "dimension",
     "columnas": ["date", "wm_yr_wk", "weekday", "wday", "month", "year", "d", "event_name_1", "event_type_1",
                  "event_name_2", "event_type_2", "snap_ca", "snap_tx", "snap_wi"]},
]

# ── 1.3 Tablas del modelo que construirá la transformación (modelo-datos.md §3) ──
TABLAS_DISENO = [
    {"tabla": "dim_producto", "grano": "una fila por producto", "clave_grano": ["item_id"], "tipo": "dimension",
     "atributos": {"dept_id": "venta.dept_id", "cat_id": "venta.cat_id"}},
    {"tabla": "dim_tienda", "grano": "una fila por tienda", "clave_grano": ["store_id"], "tipo": "dimension",
     "atributos": {"state_id": "venta.state_id"}},
    {"tabla": "Calendario", "grano": "una fila por día", "clave_grano": ["d"], "tipo": "dimension",
     "atributos": {"date": "calendario.date", "year": "calendario.year", "month": "calendario.month",
                   "weekday": "calendario.weekday", "wday": "calendario.wday", "wm_yr_wk": "calendario.wm_yr_wk",
                   "wm_yr_wk_anterior": "orden de las semanas del calendario",
                   "event_name_1": "calendario.event_name_1", "event_type_1": "calendario.event_type_1",
                   "event_name_2": "calendario.event_name_2", "event_type_2": "calendario.event_type_2",
                   "snap_ca": "calendario.snap_ca", "snap_tx": "calendario.snap_tx", "snap_wi": "calendario.snap_wi",
                   "periodo": "reglas, apartado 5", "mes_parcial": "reglas, apartado 5", "semana_parcial": "reglas, apartado 5"}},
    {"tabla": "hechos_series", "grano": "una fila por serie (departamento en una tienda) y día",
     "clave_grano": ["store_id", "dept_id", "d"], "tipo": "hechos",
     "atributos": {"cat_id": "dim_producto.cat_id", "unidades": "reglas, apartado 5, venta en unidades",
                   "dolares": "reglas, apartado 5, venta en dólares"}},
]

# Columnas del Calendario y su orden, copiadas de modelo-datos.md §6.
COLUMNAS_CALENDARIO = ["d", "date", "year", "month", "weekday", "wday", "wm_yr_wk", "wm_yr_wk_anterior",
                       "event_name_1", "event_type_1", "event_name_2", "event_type_2", "snap_ca", "snap_tx", "snap_wi",
                       "periodo", "mes_parcial", "semana_parcial"]

# ── 1.4 Relaciones con su clave, su maestro y su cardinalidad (modelo-datos.md §4) ──
# La cardinalidad sale de las reglas y de la guía del concurso, nunca solo de los datos. «tipos_desde» y «tipos_hacia»
# dicen de qué columna de entrada sale cada clave, para medir si tienen el mismo tipo a los dos lados.
NOMBRES_DE_DIAS = ("venta", "<nombres de las columnas de días>")
RELACIONES = [
    {"desde": "venta en filas", "hacia": "Calendario", "clave_desde": ["d"], "clave_hacia": ["d"],
     "maestro": "Calendario", "cardinalidad": "N:1",
     "procedencia": "guía del concurso (d_1 … d_n son los días, d_1 el 29/01/2011); reglas, apartado 5 (cada venta es del día "
                    "natural de la tienda)",
     "sin_pareja": "ningún día de la venta queda sin fecha; los días del calendario sin venta no son de ningún "
                   "periodo (reglas, apartado 5)",
     "tipos_desde": [NOMBRES_DE_DIAS], "tipos_hacia": [("calendario", "d")]},
    {"desde": "venta en filas", "hacia": "precios", "clave_desde": ["item_id", "store_id", "wm_yr_wk"],
     "clave_hacia": ["item_id", "store_id", "wm_yr_wk"], "maestro": "precios", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 5 (el precio es el de un producto en una tienda durante una semana de Walmart y vale "
                    "para sus siete días; la venta en dólares multiplica las unidades de cada día por ese precio); "
                    "guía del concurso",
     "sin_pareja": "una semana sin precio es una semana sin venta (reglas, apartado 5): esos días suman cero dólares; un día "
                   "con venta y sin precio para el trabajo (reglas, apartado 5)",
     "tipos_desde": [("venta", "item_id"), ("venta", "store_id"), ("calendario", "wm_yr_wk")],
     "tipos_hacia": [("precios", "item_id"), ("precios", "store_id"), ("precios", "wm_yr_wk")]},
    {"desde": "venta en filas", "hacia": "dim_producto", "clave_desde": ["item_id"], "clave_hacia": ["item_id"],
     "maestro": "dim_producto", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 3 (dos productos son distintos por su código) y §4 (producto, departamento y categoría); "
                    "guía del concurso",
     "sin_pareja": "no puede haberla: dim_producto sale de la propia venta",
     "tipos_desde": [("venta", "item_id")], "tipos_hacia": [("venta", "item_id")]},
    {"desde": "precios", "hacia": "dim_producto", "clave_desde": ["item_id"], "clave_hacia": ["item_id"],
     "maestro": "dim_producto", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 4 (cada producto pertenece a un departamento); ficha, pregunta 4 (precio medio del "
                    "departamento por semana)",
     "sin_pareja": "pendiente: si apareciera, se cuenta y se para",
     "tipos_desde": [("precios", "item_id")], "tipos_hacia": [("venta", "item_id")]},
    {"desde": "hechos_series", "hacia": "dim_tienda", "clave_desde": ["store_id"], "clave_hacia": ["store_id"],
     "maestro": "dim_tienda", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 3 (dos tiendas son distintas por su código y pertenecen a un estado) y §4",
     "sin_pareja": "no puede haberla: dim_tienda sale de la propia venta",
     "tipos_desde": [("venta", "store_id")], "tipos_hacia": [("venta", "store_id")]},
    {"desde": "hechos_series", "hacia": "Calendario", "clave_desde": ["d"], "clave_hacia": ["d"],
     "maestro": "Calendario", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 3 (la serie es la venta diaria de un departamento en una tienda) y §5",
     "sin_pareja": "ningún día de la serie queda sin fecha",
     "tipos_desde": [NOMBRES_DE_DIAS], "tipos_hacia": [("calendario", "d")]},
    {"desde": "hechos_series", "hacia": "precio medio del departamento por semana",
     "clave_desde": ["store_id", "dept_id", "wm_yr_wk_anterior"], "clave_hacia": ["store_id", "dept_id", "wm_yr_wk"],
     "maestro": "precio medio del departamento por semana", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 5, D9 (el precio que entra en la previsión de un día es el de la semana anterior); ficha, "
                    "pregunta 4",
     "sin_pareja": "la primera semana no tiene anterior: sus días son de los primeros sin historia (reglas, apartado 7)",
     "tipos_desde": [("venta", "store_id"), ("venta", "dept_id"), ("calendario", "wm_yr_wk")],
     "tipos_hacia": [("precios", "store_id"), ("venta", "dept_id"), ("precios", "wm_yr_wk")]},
]

# ── 1.5 Plan de cruces que lee integracion-datos (modelo-datos.md §8) ──
PLAN_CRUCES = [
    {"orden": 1, "partida": "venta en filas", "se_une": "Calendario", "clave_partida": ["d"], "clave_une": ["d"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["unidades"], "agregar_antes": None,
     "aporta": ["date", "wm_yr_wk"]},
    {"orden": 2, "partida": "venta en filas", "se_une": "precios", "clave_partida": ["item_id", "store_id", "wm_yr_wk"],
     "clave_une": ["item_id", "store_id", "wm_yr_wk"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["unidades"], "agregar_antes": None, "aporta": ["sell_price"],
     "nota": "las filas sin precio tienen que tener cero unidades; después del cruce, dólares = unidades × sell_price, "
             "con cero dólares en las filas sin precio"},
    {"orden": 3, "partida": "venta en filas", "se_une": "dim_producto", "clave_partida": ["item_id"],
     "clave_une": ["item_id"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["unidades", "dolares"], "agregar_antes": None, "aporta": ["dept_id", "cat_id"]},
    {"orden": 4, "partida": "hechos_series", "se_une": "dim_tienda", "clave_partida": ["store_id"],
     "clave_une": ["store_id"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["unidades", "dolares"],
     "agregar_antes": {"desde": "venta en filas", "grano": ["store_id", "dept_id", "d"], "arrastra": ["cat_id"],
                       "medidas": {"unidades": "suma", "dolares": "suma"}},
     "aporta": ["state_id"]},
    {"orden": 5, "partida": "hechos_series", "se_une": "Calendario", "clave_partida": ["d"], "clave_une": ["d"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["unidades", "dolares"],
     "agregar_antes": None,
     "aporta": ["date", "year", "month", "weekday", "wday", "wm_yr_wk", "wm_yr_wk_anterior", "event_name_1",
                "event_type_1", "event_name_2", "event_type_2", "snap del estado de la tienda", "periodo",
                "mes_parcial", "semana_parcial"]},
    {"orden": 6, "partida": "precios", "se_une": "dim_producto", "clave_partida": ["item_id"], "clave_une": ["item_id"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["filas", "sell_price"], "agregar_antes": None,
     "aporta": ["dept_id"]},
    {"orden": 7, "partida": "hechos_series", "se_une": "precio medio del departamento por semana",
     "clave_partida": ["store_id", "dept_id", "wm_yr_wk_anterior"], "clave_une": ["store_id", "dept_id", "wm_yr_wk"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["unidades", "dolares"],
     "agregar_antes": {"desde": "precios con su departamento (cruce 6)", "grano": ["store_id", "dept_id", "wm_yr_wk"],
                       "medidas": {"precio_medio": "media simple de los precios de los productos con precio esa "
                                                   "semana que ya lo tenían cuatro semanas antes (planteamientos; "
                                                   "reglas, apartado 5; el responsable del caso, 24/11/2026)"},
                       "nota": "no necesita las unidades de la venta: dentro del horizonte las de la semana anterior "
                               "todavía no se conocen"},
     "aporta": ["precio medio del departamento de la semana anterior"]},
]

TEORIA = [
    {"apartado": "12.5 y 12.6", "por_que": "el grano de cada tabla y el paso de producto a serie: las unidades y los "
                                          "dólares son flujos y se suman; el precio es un nivel y no se suma"},
    {"apartado": "9.5", "por_que": "cada relación con su fila, su clave, su maestro y su cardinalidad sacada de las "
                                   "reglas y de la guía; dos hechos de grano distinto no se unen fila a fila"},
    {"apartado": "14.9", "por_que": "la serie diaria es un flujo: un día sin venta es un cero válido (reglas, apartado 5) y "
                                    "el precio, un nivel que vale para los siete días de su semana"},
]

LIMITES = [
    "El script comprueba el grano y los tipos de las claves. Si las claves casan entre tablas lo mide "
    "integracion-datos, salvo los recuentos que pide el registro de exclusiones.",
    "En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar. El diccionario y la corrección "
    "cuentan cero vacíos en las claves de las tres tablas; si apareciera uno, el cruce para antes de unir.",
    "Un maestro que cambia con el tiempo se modela con la versión que hay. Aquí no cambia: el departamento de un "
    "producto y el estado de una tienda son fijos en los datos.",
    "Los dólares se calculan solo para contar y sumar, con el precio buscado por índice de semana. La única tabla que "
    "se guarda es el Calendario.",
    "La diferencia entre la media simple y la ponderada del precio del departamento se mide en la construcción. La "
    "semana 11416 entra con sus días de la construcción.",
]


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_json_limpio(obj):
    """Convierte tipos de numpy a Python y NaN o infinito a null (programacion-del-caso, error 22)."""
    if isinstance(obj, dict):
        return {str(a_json_limpio(k)) if not isinstance(k, str) else k: a_json_limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json_limpio(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        valor = float(obj)
        return None if math.isnan(valor) or math.isinf(valor) else valor
    return obj


def fmt(n, decimales=0):
    """Número a la española: punto de miles y coma decimal."""
    if n is None:
        return "sin dato"
    texto = f"{n:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


# ══ 3. Comprobaciones del diseño ════════════════════════════════════════════════
# ── 3.1 Grano ──
def clave_del_grano(df, columnas):
    """Si la clave del grano es única: filas que repiten clave y cuántas claves se repiten."""
    repetida = df.duplicated(columnas, keep=False)
    filas = int(repetida.sum())
    claves = int(df.loc[repetida, columnas].drop_duplicates().shape[0])
    return {"clave_unica": filas == 0, "filas_repetidas": filas, "claves_repetidas": claves}


def jerarquia(venta):
    """Producto → departamento → categoría y tienda → estado (reglas, apartado 4), con los productos de cada serie."""
    por_item = venta.groupby("item_id")[["dept_id", "cat_id"]].nunique()
    por_dept = venta.groupby("dept_id")["cat_id"].nunique()
    por_tienda = venta.groupby("store_id")["state_id"].nunique()
    conteo = venta.groupby(SERIE)["item_id"].nunique()
    productos = {}
    for (tienda, dept), n in conteo.items():
        productos.setdefault(str(tienda), {})[str(dept)] = int(n)
    return {"productos": int(venta["item_id"].nunique()), "tiendas": int(venta["store_id"].nunique()),
            "series": int(len(conteo)),
            "productos_con_mas_de_un_departamento": int((por_item["dept_id"] > 1).sum()),
            "productos_con_mas_de_una_categoria": int((por_item["cat_id"] > 1).sum()),
            "departamentos_con_mas_de_una_categoria": int((por_dept > 1).sum()),
            "tiendas_con_mas_de_un_estado": int((por_tienda > 1).sum()),
            "productos_por_departamento_en_cada_tienda": productos}


def tipos_de_relacion(relacion, tablas):
    """El tipo de cada columna de la clave a los dos lados, leído de la tabla de entrada de la que sale."""
    def tipo(origen):
        if origen == NOMBRES_DE_DIAS:
            return "str"
        tabla, columna = origen
        return str(tablas[tabla][columna].dtype)
    desde = [tipo(o) for o in relacion["tipos_desde"]]
    hacia = [tipo(o) for o in relacion["tipos_hacia"]]
    return desde, hacia


# ── 3.2 Fechas ──
def dias_seguidos(fechas):
    """Rango de fechas y días que faltan entre el primero y el último."""
    unicas = pd.Series(fechas).drop_duplicates().sort_values()
    desde, hasta = unicas.iloc[0], unicas.iloc[-1]
    esperados = (hasta - desde).days + 1
    return {"desde": desde.strftime("%Y-%m-%d"), "hasta": hasta.strftime("%Y-%m-%d"), "dias": int(len(unicas)),
            "dias_que_faltan": int(esperados - len(unicas))}


def semanas(cal):
    """Días de cada semana de Walmart, su orden por fecha y la semana anterior de cada una, tomada por orden."""
    por_semana = cal.groupby("wm_yr_wk")["date"].agg(["count", "min"])
    dias = {int(w): int(n) for w, n in por_semana["count"].items()}
    orden = [int(w) for w in por_semana.sort_values("min").index]
    saltos = [[a, b] for a, b in zip(orden, orden[1:]) if b - a != 1]
    return {"dias_por_semana": dias, "semanas_incompletas": {w: n for w, n in dias.items() if n != 7},
            "anterior": {b: a for a, b in zip(orden, orden[1:])}, "saltos_de_codigo": saltos,
            "orden_por_codigo_igual_que_por_fecha": orden == sorted(orden)}


def parciales(cal, periodos):
    """Meses y semanas que no tienen todos sus días dentro de cada periodo (reglas, apartado 5, «parcial»)."""
    resultado = {}
    for nombre, (desde, hasta) in periodos.items():
        dentro = cal[(cal["date"] >= pd.Timestamp(desde)) & (cal["date"] <= pd.Timestamp(hasta))]
        mes = dentro["date"].dt.strftime("%Y-%m")
        dias_mes = dentro.groupby(mes)["date"].agg(["count", "max"])
        meses = [m for m, fila in dias_mes.iterrows() if fila["count"] != fila["max"].days_in_month]
        dias_semana = dentro.groupby("wm_yr_wk")["date"].count()
        resultado[nombre] = {"desde": desde, "hasta": hasta, "dias": int(len(dentro)), "meses_parciales": meses,
                             "semanas_parciales": [int(w) for w, n in dias_semana.items() if n != 7]}
    return resultado


# ── 3.3 Dólares con el precio de su semana ──
def a_centimos(precios):
    """Precio en céntimos enteros; None si algún precio tiene más de dos decimales."""
    x = np.asarray(precios, dtype="float64") * 100
    redondeado = np.round(x)
    if np.any(np.abs(x - redondeado) > 1e-6):
        return None
    return redondeado.astype(np.int64)


def dolares(U, P, semana_de_dia):
    """Unidades de cada día por el precio de su semana, en céntimos enteros, sin unir tablas.

    U: unidades, una fila por producto-tienda y una columna por día. P: céntimos, una fila por producto-tienda y una
    columna por semana, con NaN donde no hay precio. semana_de_dia: la columna de P que corresponde a cada día.
    """
    precio_dia = P[:, semana_de_dia]
    sin_precio = np.isnan(precio_dia)
    centimos = np.where(sin_precio, 0, precio_dia).astype(np.int64)
    return {"dias_sin_precio": int(sin_precio.sum()),
            "dias_con_venta_y_sin_precio": int((sin_precio & (U > 0)).sum()),
            "centimos": int((U.astype(np.int64) * centimos).sum())}


def dolares_redondeados(centimos):
    """Céntimos enteros a dólares, sin pérdida."""
    return float((Decimal(int(centimos)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ── 3.4 Precio medio del departamento por semana ──
def precio_medio_departamento(df):
    """Media simple y ponderada por unidades del precio de cada departamento, tienda y semana, y lo que las separa.

    df: una fila por producto, tienda y semana con precio, con store_id, dept_id, wm_yr_wk, sell_price y unidades.
    """
    df = df.assign(importe=df["sell_price"] * df["unidades"])
    tabla = (df.groupby(["store_id", "dept_id", "wm_yr_wk"])
             .agg(simple=("sell_price", "mean"), importe=("importe", "sum"), unidades=("unidades", "sum"))
             .reset_index())
    con_unidades = tabla["unidades"] > 0
    tabla["ponderada"] = np.where(con_unidades, tabla["importe"] / tabla["unidades"].where(con_unidades, 1), np.nan)
    comparables = tabla[con_unidades].copy()
    comparables["dif"] = comparables["ponderada"] - comparables["simple"]
    comparables["dif_rel"] = comparables["dif"].abs() / comparables["simple"] * 100
    resumen = {"grupos": int(len(tabla)), "sin_ponderada": int((~con_unidades).sum()),
               "comparables": int(len(comparables))}
    if len(comparables):
        resumen.update({
            "diferencia_media_dolares": round(float(comparables["dif"].abs().mean()), 4),
            "diferencia_relativa_media_pct": float(comparables["dif_rel"].mean()),
            "diferencia_relativa_mediana_pct": float(comparables["dif_rel"].median()),
            "diferencia_relativa_p95_pct": float(comparables["dif_rel"].quantile(0.95)),
            "diferencia_relativa_maxima_pct": float(comparables["dif_rel"].max()),
            "ponderada_por_debajo_pct": float((comparables["dif"] < 0).mean() * 100),
            "por_departamento_media_pct": {str(k): float(v) for k, v in
                                           comparables.groupby("dept_id")["dif_rel"].mean().items()}})
    return {"tabla": tabla, "resumen": resumen}


# ── 3.5 Registro de exclusiones ──
def dias_fuera_del_error(S, tiendas, fechas, periodos):
    """Días de serie del 25 de diciembre por periodo y cierres de una tienda entera fuera del 25 de diciembre.

    S: unidades por serie (filas) y día (columnas); tiendas: la tienda de cada serie; fechas: AAAA-MM-DD de cada día.
    """
    fechas = np.asarray(fechas)
    es_25 = np.array([f[5:] == "12-25" for f in fechas])
    resultado = {"25_diciembre": {}, "cierres_fuera_del_25": []}
    for nombre, (desde, hasta) in periodos.items():
        dentro = (fechas >= desde) & (fechas <= hasta)
        resultado["25_diciembre"][nombre] = int((dentro & es_25).sum() * S.shape[0])
    for tienda in sorted(set(tiendas)):
        filas = S[np.asarray(tiendas) == tienda]
        cerrada = (filas.sum(axis=0) == 0) & ~es_25
        for k in np.flatnonzero(cerrada):
            periodo = next((n for n, (a, b) in periodos.items() if a <= fechas[k] <= b), None)
            resultado["cierres_fuera_del_25"].append({"tienda": str(tienda), "fecha": str(fechas[k]),
                                                      "periodo": periodo, "dias_serie": int(filas.shape[0])})
    return resultado


# ── 3.6 Construcción del Calendario (modelo-datos.md §6; método, apartado 9) ──
def construir_calendario(cal, periodos):
    """El Calendario del modelo: las columnas del calendario corregido, la semana anterior, el periodo y las marcas.

    La semana anterior se toma por el orden de las fechas, porque el código salta al cambiar de año. Los días que no
    caen en ningún periodo llevan «sin_periodo» (reglas, apartado 5). Un mes o una semana es parcial cuando no tiene todos sus
    días dentro del periodo del día.
    """
    # Se ordena por fecha antes de nada, para que nada dependa del orden de las filas (error 7)
    out = cal.sort_values("date", kind="stable").reset_index(drop=True)
    out["wm_yr_wk_anterior"] = out["wm_yr_wk"].map(semanas(out)["anterior"]).astype("Int64")
    # Cada día recibe su periodo; lo que queda fuera de los dos es «sin_periodo»
    out["periodo"] = "sin_periodo"
    for nombre, (desde, hasta) in periodos.items():
        dentro = (out["date"] >= pd.Timestamp(desde)) & (out["date"] <= pd.Timestamp(hasta))
        out.loc[dentro, "periodo"] = nombre
    # Las marcas cuentan los días del mes y de la semana dentro del periodo del día
    mes = out["date"].dt.strftime("%Y-%m")
    out["mes_parcial"] = out.groupby([out["periodo"], mes])["date"].transform("count") != out["date"].dt.days_in_month
    out["semana_parcial"] = out.groupby(["periodo", "wm_yr_wk"])["date"].transform("count") != 7
    return out[COLUMNAS_CALENDARIO]


def validar_calendario(out, entrada, par):
    """Lo que el Calendario tiene que cumplir antes de guardarse (error 15); devuelve la lista de problemas.

    entrada: el calendario corregido del que sale. par: los meses y semanas parciales de cada periodo medidos con
    parciales(), que es otra cuenta distinta de la de construir_calendario().
    """
    problemas = []
    if list(out.columns) != COLUMNAS_CALENDARIO:
        problemas.append("las columnas no son las del diseño")
    if len(out) != len(entrada):
        problemas.append(f"{len(out)} filas frente a {len(entrada)} del calendario corregido")
    if out["d"].duplicated().any():
        problemas.append("la clave d se repite")
    if dias_seguidos(out["date"])["dias_que_faltan"]:
        problemas.append("faltan días entre el primero y el último")
    primera = out.loc[out["date"].idxmin(), "wm_yr_wk"]
    if set(out.loc[out["wm_yr_wk_anterior"].isna(), "wm_yr_wk"]) != {primera}:
        problemas.append("hay semanas sin anterior que no son la primera")
    # Las columnas copiadas tienen que llegar iguales al calendario corregido, fila a fila
    comunes = [c for c in entrada.columns if c in out.columns]
    esperado = entrada.sort_values("date", kind="stable").reset_index(drop=True)[comunes]
    if len(out) == len(entrada) and not out[comunes].reset_index(drop=True).equals(esperado):
        problemas.append("alguna columna copiada del calendario corregido ha cambiado")
    # Las marcas, contra las de parciales()
    for nombre, p in par.items():
        dentro = out[out["periodo"] == nombre]
        meses = sorted(dentro.loc[dentro["mes_parcial"], "date"].dt.strftime("%Y-%m").unique())
        semanas_p = sorted(int(w) for w in dentro.loc[dentro["semana_parcial"], "wm_yr_wk"].unique())
        if len(dentro) != p["dias"] or meses != sorted(p["meses_parciales"]) or semanas_p != sorted(p["semanas_parciales"]):
            problemas.append(f"el periodo {nombre} no tiene los días o las marcas que mide parciales()")
    return problemas


# ── 3.7 Aprobación y estado ──
def leer_aprobacion(ruta):
    """Busca la línea fija de aprobación dentro de «Decisiones de modelado»; sin ella, no aprobado."""
    encontrada = None
    lineas = Path(ruta).read_text(encoding="utf-8").splitlines() if Path(ruta).exists() else []
    dentro = False
    for linea in lineas:
        if linea.startswith("## "):
            dentro = "Decisiones de modelado" in linea
            continue
        m = re.match(r"^Aprobado: sí · (.+?) · (\d{4}-\d{2}-\d{2})\s*$", linea)
        if dentro and m:
            encontrada = m
    return {"aprobado": encontrada is not None, "fecha": encontrada.group(2) if encontrada else None,
            "quien": encontrada.group(1) if encontrada else None}


def pendientes_del_diseno(aprobacion):
    """Las decisiones que el diseño deja abiertas; la aprobación, solo mientras falte.

    El precio medio del departamento ya no está: quedó fijado como media simple en los planteamientos (el responsable del caso, 24/11/2026).
    """
    aprobar = [] if aprobacion["aprobado"] else [
        {"id": "aprobacion_del_diseno", "tabla": None, "columna": None,
         "pregunta": "¿Se aprueba el diseño del modelo de datos?",
         "opciones": ["sí, con la línea fija en «Decisiones de modelado»", "no, con lo que hay que cambiar"]}]
    return aprobar + [
        {"id": "minimo_de_la_pregunta_4", "tabla": None, "columna": None,
         "pregunta": "¿Cuántos días de cada evento hacen falta para dar su efecto en la pregunta 4? Es de método y "
                     "va a los planteamientos con la fórmula de cada efecto.",
         "opciones": ["un mínimo fijado en los planteamientos", "dar todos los efectos marcando los de pocos días"]},
    ]


def estado_y_riesgo(aprobacion, contradicciones):
    """PARADO hasta que el responsable del caso apruebe o mientras los datos contradigan el diseño; OK solo con las dos cosas."""
    if not aprobacion["aprobado"]:
        return "PARADO", "medio" if contradicciones else "bajo"
    if contradicciones:
        return "PARADO", "alto"
    return "OK", "bajo"


# ══ 4. Informe para la persona ══════════════════════════════════════════════════
def resultado_minimo_de_prueba():
    """Un resultado con todas las claves que usa el informe, para la prueba."""
    return {
        "fecha_ejecucion": "2026-11-24T10:00:00", "fecha_datos": FECHA_DATOS, "script": SCRIPT_REL,
        "entradas": [{"ruta": "data/processed/a.parquet", "sha256": "x", "filas": 1, "columnas": 1}],
        "resultado": {"estado": "PARADO", "riesgo": "bajo", "resumen": "prueba", "siguiente": "aprobación"},
        "aprobado": leer_aprobacion(Path("no-existe.md")),
        "tablas": [{"tabla": "a", "grano": "una fila", "clave_grano": ["k"], "tipo": "hechos", "clave_unica": None,
                    "filas_repetidas": None, "fichero": None}],
        "relaciones": [{"desde": "a", "hacia": "b", "clave_desde": ["k"], "clave_hacia": ["k"], "maestro": "b",
                        "cardinalidad": "N:1", "procedencia": "reglas", "mismo_tipo": None}],
        "calendario": {"periodo": "día", "desde": "2011-01-29", "hasta": "2011-01-30", "dias_que_faltan": 0,
                       "parciales": {}, "semana_que_cruza": None, "saltos_de_codigo": [],
                       "primer_periodo_completo": None, "ultimo_periodo_completo": None, "fichero": None},
        "forma_entrega": "tablas_separadas", "plan_cruces": [], "exclusiones": [],
        "precio_medio_departamento": {"resumen": {"grupos": 0, "sin_ponderada": 0, "comparables": 0}},
        "comprobaciones": [], "contradicciones": [], "pendientes": [], "datos_personales_nota": "sin datos",
        "limites": ["uno"],
    }


def generar_md(r):
    """Informe para la persona, generado del mismo diccionario que el JSON (resultado.md, regla 1)."""
    L = [f"# Modelado de datos · caso 69", "",
         f"Diseño: `{DISENO_REL}`. Estado: **{r['resultado']['estado']}**. Riesgo: {r['resultado']['riesgo']}.", ""]
    L += ["## Fuente", "", f"- Script: `{r['script']}`, ejecutado el {r['fecha_ejecucion']}.",
          f"- Fecha de los datos: {r['fecha_datos']}."]
    for e in r["entradas"]:
        L.append(f"- `{e['ruta']}`: {fmt(e['filas'])} filas y {fmt(e['columnas'])} columnas; huella `{e['sha256'][:12]}`.")
    aprob = r["aprobado"]
    L += ["", "## Resumen", "", r["resultado"]["resumen"], "",
          (f"Aprobado por {aprob['quien']} el {aprob['fecha']}." if aprob["aprobado"]
           else "El diseño no está aprobado: falta la línea del responsable del caso en «Decisiones de modelado»."),
          f"Siguiente: {r['resultado']['siguiente']}", ""]
    L += ["## Tablas y grano", "", "| Tabla | Tipo | Grano | Clave del grano | Clave única | Filas repetidas |",
          "|---|---|---|---|---|---|"]
    for t in r["tablas"]:
        unica = {True: "sí", False: "no", None: "se comprueba al construirla"}[t["clave_unica"]]
        rep = "sin dato" if t["filas_repetidas"] is None else fmt(t["filas_repetidas"])
        L.append(f"| {t['tabla']} | {t['tipo']} | {t['grano']} | {', '.join(t['clave_grano'])} | {unica} | {rep} |")
    L += ["", "## Relaciones", "", "| Desde | Hacia | Clave | Maestro | Cardinalidad | Procedencia | Mismo tipo |",
          "|---|---|---|---|---|---|---|"]
    for x in r["relaciones"]:
        clave = f"{', '.join(x['clave_desde'])} → {', '.join(x['clave_hacia'])}"
        L.append(f"| {x['desde']} | {x['hacia']} | {clave} | {x['maestro']} | {x['cardinalidad']} | {x['procedencia']} "
                 f"| {({True: 'sí', False: 'no'}).get(x['mismo_tipo'], 'sin dato')} |")
    c = r["calendario"]
    if c.get("fichero"):
        por = c["dias_por_periodo"]
        construido = (f"Construido en `{c['fichero']}` con {fmt(c['filas'])} días: {fmt(por.get('construccion', 0))} "
                      f"de construcción, {fmt(por.get('validacion', 0))} de validación y "
                      f"{fmt(por.get('sin_periodo', 0))} sin periodo. Huella `{c['sha256'][:12]}`.")
    else:
        construido = "No se construye hasta que el responsable del caso apruebe el diseño."
    L += ["", "## Calendario", "",
          f"Por días, del {c['desde']} al {c['hasta']}, con {fmt(c['dias_que_faltan'])} días que faltan. {construido}",
          ""]
    for nombre, p in c["parciales"].items():
        meses = ", ".join(p["meses_parciales"]) or "ninguno"
        sem = ", ".join(str(w) for w in p["semanas_parciales"]) or "ninguna"
        L.append(f"- {ETIQUETA.get(nombre, nombre)} ({p['desde']} a {p['hasta']}, {fmt(p['dias'])} días): meses "
                 f"parciales {meses}; semanas parciales {sem}.")
    if c["semana_que_cruza"]:
        s = c["semana_que_cruza"]
        L.append(f"- La semana {s['semana']} cruza los dos periodos: {fmt(s['dias_construccion'])} días en la "
                 f"construcción y {fmt(s['dias_validacion'])} en la validación.")
    L.append(f"- Saltos de código entre una semana y la siguiente: {fmt(len(c['saltos_de_codigo']))}. La semana "
             f"anterior se toma por orden de fechas, nunca restando 1 al código.")
    L += ["", "## Plan de cruces", "", "| Orden | Partida | Se une | Clave | Cardinalidad | Tipo | Control | Agregar antes |",
          "|---|---|---|---|---|---|---|---|"]
    for x in r["plan_cruces"]:
        agregar = "no" if not x["agregar_antes"] else f"a {', '.join(x['agregar_antes']['grano'])}"
        L.append(f"| {x['orden']} | {x['partida']} | {x['se_une']} | {', '.join(x['clave_partida'])} → "
                 f"{', '.join(x['clave_une'])} | {x['cardinalidad']} | {x['tipo_cruce']} | "
                 f"{', '.join(x['magnitudes_control'])} | {agregar} |")
    L += ["", "## Registro de exclusiones", "", "| Qué sale | De qué cálculo | Recuento | Se puede recuperar |",
          "|---|---|---|---|"]
    for x in r["exclusiones"]:
        L.append(f"| {x['que_sale']} | {x['de_que_calculo']} | {x['recuento_texto']} | {x['recuperable']} |")
    pm = r["precio_medio_departamento"]["resumen"]
    L += ["", "## Precio medio del departamento", "",
          f"Medido en la construcción sobre {fmt(pm['grupos'])} semanas de departamento en tienda; "
          f"{fmt(pm['comparables'])} tienen las dos medias.", ""]
    if pm.get("comparables"):
        L += [f"- Diferencia relativa sin signo: media {fmt(pm['diferencia_relativa_media_pct'], 2)} %; mediana "
              f"{fmt(pm['diferencia_relativa_mediana_pct'], 2)} %.",
              f"- Percentil 95: {fmt(pm['diferencia_relativa_p95_pct'], 2)} %. Máxima: "
              f"{fmt(pm['diferencia_relativa_maxima_pct'], 2)} %.",
              f"- La ponderada queda por debajo de la simple en el {fmt(pm['ponderada_por_debajo_pct'], 2)} % de las "
              f"semanas."]
        for dept, v in pm["por_departamento_media_pct"].items():
            L.append(f"- {dept}: {fmt(v, 2)} % de media.")
    L += ["", "Elegida la media simple, porque la ponderada necesita unidades que dentro del horizonte todavía no se "
              "conocen (planteamientos; el responsable del caso, 24/11/2026).", ""]
    L += ["## Comprobaciones", ""]
    for x in r["comprobaciones"]:
        L.append(f"- {x['que']}: {x['resultado']}.")
    if r["contradicciones"]:
        L += ["", "Contradicciones con el diseño:"] + [f"- {x['que']}" for x in r["contradicciones"]]
    else:
        L += ["", "Ningún dato contradice el diseño."]
    L += ["", "## Decisiones pendientes", ""]
    L += [f"- {p['pregunta']} Opciones: {' / '.join(p['opciones'])}." for p in r["pendientes"]] or ["- Ninguna."]
    L += ["", "## Datos personales", "", r["datos_personales_nota"], "", "## Límites", ""]
    L += [f"- {x}" for x in r["limites"]]
    return "\n".join(L) + "\n"


# ══ 5. Ejecución ════════════════════════════════════════════════════════════════
def principal():
    """Lee, comprueba, mide y escribe el JSON y el informe; el JSON se escribe también si algo falla."""
    inicio = time.perf_counter()
    partes = {}
    r = {"metodo": "modelado-datos", "version_metodo": version_metodo(), "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
         "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                     "pyarrow": pyarrow.__version__, "ejecutable": sys.executable},
         "diseno": DISENO_REL}
    try:
        # ── 5.1 Al empezar: la corrección tiene que estar en OK y con las huellas de sus salidas ──
        t = time.perf_counter()
        corr = json.loads(CORRECCION.read_text(encoding="utf-8"))
        rutas = {k: PROCESADOS / v for k, v in ENTRADAS.items()}
        huellas = {k: huella(p) for k, p in rutas.items()}
        de_correccion = {s["tabla"]: s["sha256"] for s in corr["salidas"]}
        paradas = []
        if corr["resultado"]["estado"] != "OK":
            paradas.append(f"correccion-datos.json está en {corr['resultado']['estado']}")
        paradas += [f"la huella de {k} no es la de correccion-datos.json" for k in rutas if huellas[k] != de_correccion.get(k)]

        # ── 5.2 Lectura: de cada tabla, solo las columnas que nombra el diseño ──
        esquemas = {k: pq.read_schema(p).names for k, p in rutas.items()}
        dias = [c for c in esquemas["venta"] if c.startswith("d_")]
        venta = pd.read_parquet(rutas["venta"], columns=TABLAS[0]["columnas"] + dias)
        precios = pd.read_parquet(rutas["precios"], columns=TABLAS[1]["columnas"])
        cal = pd.read_parquet(rutas["calendario"], columns=TABLAS[2]["columnas"])
        tablas_df = {"venta": venta, "precios": precios, "calendario": cal}
        r["entradas"] = [{"ruta": f"data/processed/{ENTRADAS[k]}", "sha256": huellas[k], "filas": int(len(df)),
                          "columnas": int(len(esquemas[k]))} for k, df in tablas_df.items()]
        partes["lectura"] = round(time.perf_counter() - t, 2)

        # ── 5.3 Grano, columnas y jerarquía ──
        t = time.perf_counter()
        comprobaciones, contradicciones = [], []
        r["tablas"] = []
        for cfg in TABLAS:
            df = tablas_df[cfg["tabla"]]
            faltan = [c for c in cfg["columnas"] if c not in esquemas[cfg["tabla"]]]
            grano = clave_del_grano(df, cfg["clave_grano"])
            alternativa = clave_del_grano(df, cfg["clave_alternativa"]) if cfg["clave_alternativa"] else None
            r["tablas"].append({"tabla": cfg["tabla"], "fichero": f"data/processed/{ENTRADAS[cfg['tabla']]}",
                                "grano": cfg["grano"], "clave_grano": cfg["clave_grano"], "tipo": cfg["tipo"],
                                "clave_unica": grano["clave_unica"], "filas_repetidas": grano["filas_repetidas"],
                                "claves_repetidas": grano["claves_repetidas"], "columnas_que_faltan": faltan,
                                "clave_alternativa": cfg["clave_alternativa"],
                                "clave_alternativa_unica": alternativa["clave_unica"] if alternativa else None})
            if faltan:
                contradicciones.append({"que": f"a {cfg['tabla']} le faltan columnas del diseño: {faltan}"})
            if not grano["clave_unica"]:
                contradicciones.append({"que": f"la clave del grano de {cfg['tabla']} se repite en "
                                               f"{grano['filas_repetidas']} filas"})
            if alternativa and not alternativa["clave_unica"]:
                contradicciones.append({"que": f"{cfg['clave_alternativa']} de {cfg['tabla']} se repite"})
        for cfg in TABLAS_DISENO:
            r["tablas"].append({"tabla": cfg["tabla"], "fichero": None, "grano": cfg["grano"],
                                "clave_grano": cfg["clave_grano"], "tipo": cfg["tipo"], "clave_unica": None,
                                "filas_repetidas": None, "atributos": cfg["atributos"],
                                "nota": "no existe todavía: la construye la transformación con el diseño aprobado"})
        jer = jerarquia(venta)
        for clave in ("productos_con_mas_de_un_departamento", "productos_con_mas_de_una_categoria",
                      "departamentos_con_mas_de_una_categoria", "tiendas_con_mas_de_un_estado"):
            if jer[clave]:
                contradicciones.append({"que": f"{clave}: {jer[clave]}"})
        por_tienda = list(jer["productos_por_departamento_en_cada_tienda"].values())
        mismos_en_todas = all(x == por_tienda[0] for x in por_tienda)
        r["jerarquia"] = jer
        r["relaciones"] = []
        for rel in RELACIONES:
            desde, hacia = tipos_de_relacion(rel, tablas_df)
            r["relaciones"].append({k: v for k, v in rel.items() if not k.startswith("tipos_")}
                                   | {"tipos_desde": desde, "tipos_hacia": hacia, "mismo_tipo": desde == hacia})
            if desde != hacia:
                contradicciones.append({"que": f"la clave de {rel['desde']} → {rel['hacia']} tiene tipos distintos"})
        partes["grano_y_relaciones"] = round(time.perf_counter() - t, 2)

        # ── 5.4 Calendario y semanas ──
        t = time.perf_counter()
        rango = dias_seguidos(cal["date"])
        fecha_de = dict(zip(cal["d"], cal["date"]))
        semana_de = dict(zip(cal["d"], cal["wm_yr_wk"]))
        sin_fecha = [d for d in dias if d not in fecha_de]
        cal_venta = cal[cal["d"].isin(dias)]
        sem_venta = semanas(cal_venta)
        sem_todas = semanas(cal)
        sem_precios = sorted(int(w) for w in precios["wm_yr_wk"].unique())
        sem_v = sorted(sem_venta["dias_por_semana"])
        hasta_c = pd.Timestamp(PERIODOS["construccion"][1])
        fila_fin = cal[cal["date"] == hasta_c].iloc[0]
        semana_cruza = int(fila_fin["wm_yr_wk"])
        dias_cruza = cal[cal["wm_yr_wk"] == semana_cruza]["date"]
        ultimo_cal = cal["date"].max().strftime("%Y-%m-%d")
        siguiente = (pd.Timestamp(PERIODOS["validacion"][1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        con_resto = dict(PERIODOS) | ({"sin_periodo": (siguiente, ultimo_cal)} if siguiente <= ultimo_cal else {})
        par = parciales(cal, con_resto)
        primero, ultimo = fecha_de[dias[0]], fecha_de[dias[-1]]
        r["calendario"] = {
            "periodo": "día", "desde": rango["desde"], "hasta": rango["hasta"], "dias": rango["dias"],
            "dias_que_faltan": rango["dias_que_faltan"], "fichero": None,
            "primer_periodo_completo": not par["construccion"]["meses_parciales"][:1] == [primero.strftime("%Y-%m")],
            "ultimo_periodo_completo": not par["validacion"]["meses_parciales"][-1:] == [ultimo.strftime("%Y-%m")],
            "parciales": par,
            "semana_que_cruza": {"semana": semana_cruza,
                                 "dias_construccion": int((dias_cruza <= hasta_c).sum()),
                                 "dias_validacion": int((dias_cruza > hasta_c).sum())},
            "saltos_de_codigo": sem_todas["saltos_de_codigo"],
            "orden_por_codigo_igual_que_por_fecha": sem_todas["orden_por_codigo_igual_que_por_fecha"],
            "semanas_del_calendario_incompletas": sem_todas["semanas_incompletas"],
            "union_de_cada_hecho": {"venta": "d", "precios": "wm_yr_wk, con la semana del día sacada del Calendario"},
            "construccion": "al aprobarse el diseño, desde las 1.969 filas de calendario_corregido.parquet, sin "
                            "fechas fijas en el código"}
        if rango["dias_que_faltan"] or sin_fecha:
            contradicciones.append({"que": f"faltan {rango['dias_que_faltan']} días en el calendario; "
                                           f"{len(sin_fecha)} días de la venta sin fecha"})
        if sem_venta["semanas_incompletas"]:
            contradicciones.append({"que": f"semanas de la venta incompletas: {sem_venta['semanas_incompletas']}"})
        if sem_precios != sem_v:
            contradicciones.append({"que": "las semanas de los precios no son las de la venta"})
        if not sem_todas["orden_por_codigo_igual_que_por_fecha"]:
            contradicciones.append({"que": "el orden de los códigos de semana no es el de las fechas"})
        partes["calendario"] = round(time.perf_counter() - t, 2)

        # ── 5.5 Claves sin pareja que el diseño da por esperadas y dólares con el precio de su semana ──
        t = time.perf_counter()
        pares = pd.MultiIndex.from_frame(venta[["item_id", "store_id"]])
        pares_precio = pd.MultiIndex.from_frame(precios[["item_id", "store_id"]].drop_duplicates())
        sin_precio_pares = ~pares.isin(pares_precio)
        precios_sin_par = int((~pares_precio.isin(pares)).sum())
        semanas_cal = sorted(int(w) for w in cal["wm_yr_wk"].unique())
        U = venta[dias].to_numpy(dtype=np.int64)
        col_semana = {w: i for i, w in enumerate(sem_v)}
        semana_de_dia = np.array([col_semana[int(semana_de[d])] for d in dias])
        centimos = a_centimos(precios["sell_price"])
        if centimos is None:
            contradicciones.append({"que": "hay precios con más de dos decimales: los dólares no se suman en céntimos"})
        P = np.full((len(venta), len(sem_v)), np.nan)
        fila = pares.get_indexer(pd.MultiIndex.from_frame(precios[["item_id", "store_id"]]))
        columna = precios["wm_yr_wk"].map(col_semana).to_numpy()
        valido = (fila >= 0) & ~pd.isna(columna)
        P[fila[valido], columna[valido].astype(int)] = centimos[valido] if centimos is not None else np.nan
        dol = dolares(U, P, semana_de_dia)
        if dol["dias_con_venta_y_sin_precio"]:
            contradicciones.append({"que": f"{dol['dias_con_venta_y_sin_precio']} días con venta y sin precio: "
                                           f"las reglas, apartado 5 paran antes de calcular dólares"})
        partes["dolares"] = round(time.perf_counter() - t, 2)

        # ── 5.6 Registro de exclusiones ──
        t = time.perf_counter()
        series = venta.groupby(SERIE)[dias].sum()
        S = series.to_numpy(dtype=np.int64)
        tiendas_serie = series.index.get_level_values("store_id").to_numpy()
        fechas = np.array([fecha_de[d].strftime("%Y-%m-%d") for d in dias])
        fuera = dias_fuera_del_error(S, tiendas_serie, fechas, PERIODOS)
        unidades_sin_precio = int(U[sin_precio_pares].sum())
        dias_cal_sin_venta = int((~cal["d"].isin(dias)).sum())
        cierres_txt = "; ".join(f"{x['tienda']} el {x['fecha']}, {x['dias_serie']} días de serie en "
                                f"{ETIQUETA.get(x['periodo'], x['periodo'])}" for x in fuera["cierres_fuera_del_25"])
        r["exclusiones"] = [
            {"clase": "25 de diciembre", "que_sale": "los días de serie del 25 de diciembre",
             "de_que_calculo": "el error, el sesgo y la ventaja del modelo y de las tres reglas (reglas, apartado 6)",
             "como_se_trata": "se quedan en la tabla de series con su venta; no entran en el error",
             "por_que": "se sabe de antemano que la tienda cierra (reglas, apartado 6)", "recuperable": "sí: se quedan en la tabla",
             "recuento": fuera["25_diciembre"],
             "recuento_texto": "; ".join(f"{fmt(v)} días de serie en {ETIQUETA[k]}" for k, v in fuera["25_diciembre"].items())},
            {"clase": "cierre fuera del 25 de diciembre", "que_sale": "el cierre de toda una tienda fuera del 25 de diciembre",
             "de_que_calculo": "el error, como un 25 de diciembre (reglas, apartado 5; PC-03)",
             "como_se_trata": "se queda en la tabla de series a cero; no entra en el error",
             "por_que": "es un cierre real de la tienda y se trata como el 25 de diciembre (reglas, apartado 5)",
             "recuperable": "sí: se queda en la tabla", "recuento": fuera["cierres_fuera_del_25"],
             "recuento_texto": cierres_txt or "ninguno"},
            {"clase": "productos-tienda sin ningún precio", "que_sale": "nada: suman cero a su departamento",
             "de_que_calculo": "ninguno; la venta en dólares les da cero",
             "como_se_trata": "se quedan en la venta en filas con cero unidades",
             "por_que": "un producto que no se vendía suma cero a su departamento (reglas, apartado 3)",
             "recuperable": "no hace falta: no salen",
             "recuento": {"productos_tienda": int(sin_precio_pares.sum()), "unidades": unidades_sin_precio},
             "recuento_texto": f"{fmt(int(sin_precio_pares.sum()))} productos-tienda con {fmt(unidades_sin_precio)} unidades"},
            {"clase": "días del calendario sin venta", "que_sale": "los días del calendario posteriores a la fecha de referencia",
             "de_que_calculo": "la tabla de series: no tienen venta en el caso",
             "como_se_trata": "se quedan en el Calendario sin periodo; la previsión en producción los necesita",
             "por_que": "no son de ningún periodo (reglas, apartado 5); la prueba final está apartada fuera del caso",
             "recuperable": "con la prueba final, copiada por la persona responsable",
             "recuento": {"dias": dias_cal_sin_venta}, "recuento_texto": f"{fmt(dias_cal_sin_venta)} días"},
            {"clase": "primeros días sin historia",
             "que_sale": "los primeros días de cada serie sin la historia que piden las variables",
             "de_que_calculo": "la previsión y la comparación con las reglas (reglas, apartado 7, «Población del análisis»)",
             "como_se_trata": "se cuentan en el registro de transformaciones",
             "por_que": "las variables de la previsión necesitan días anteriores",
             "recuperable": "no: no hay datos antes del 29/01/2011", "recuento": None,
             "recuento_texto": "pendiente del paso 5, cuando se fijen las variables"},
        ]
        partes["exclusiones"] = round(time.perf_counter() - t, 2)

        # ── 5.7 Precio medio del departamento por semana, en la construcción ──
        t = time.perf_counter()
        en_construccion = np.array([f <= PERIODOS["construccion"][1] for f in fechas])
        sem_c = sorted({int(semana_de[d]) for d, dentro in zip(dias, en_construccion) if dentro})
        uno = np.zeros((int(en_construccion.sum()), len(sem_c)), dtype=np.int64)
        idx_c = {w: i for i, w in enumerate(sem_c)}
        dias_c = [d for d, dentro in zip(dias, en_construccion) if dentro]
        uno[np.arange(len(dias_c)), [idx_c[int(semana_de[d])] for d in dias_c]] = 1
        unidades_semana = U[:, en_construccion] @ uno
        pc = precios[precios["wm_yr_wk"].isin(sem_c)]
        fila_pc = pares.get_indexer(pd.MultiIndex.from_frame(pc[["item_id", "store_id"]]))
        df_pm = pd.DataFrame({"store_id": pc["store_id"].to_numpy(), "dept_id": venta["dept_id"].to_numpy()[fila_pc],
                              "wm_yr_wk": pc["wm_yr_wk"].to_numpy(), "sell_price": pc["sell_price"].to_numpy(),
                              "unidades": unidades_semana[fila_pc, pc["wm_yr_wk"].map(idx_c).to_numpy()]})
        pm = precio_medio_departamento(df_pm)
        r["precio_medio_departamento"] = {
            "de_que_tablas_sale": "precios (sell_price de cada producto, tienda y semana) con dim_producto (su "
                                  "departamento); la ponderada necesita además las unidades de la venta en filas, "
                                  "sumadas por producto, tienda y semana con la semana del Calendario",
            "periodo_medido": "construcción", "semanas_medidas": len(sem_c), "resumen": pm["resumen"]}
        partes["precio_medio"] = round(time.perf_counter() - t, 2)

        # ── 5.8 Cifras de control, comprobaciones y pendientes ──
        comun = por_tienda[0] if mismos_en_todas else None
        cc = {
            "filas_venta": int(len(venta)), "columnas_venta": len(esquemas["venta"]), "filas_precios": int(len(precios)),
            "filas_calendario": int(len(cal)),
            "clave_venta_filas_repetidas": r["tablas"][0]["filas_repetidas"],
            "id_unico": r["tablas"][0]["clave_alternativa_unica"],
            "clave_precios_filas_repetidas": r["tablas"][1]["filas_repetidas"],
            "clave_calendario_filas_repetidas": r["tablas"][2]["filas_repetidas"],
            "date_unica": r["tablas"][2]["clave_alternativa_unica"],
            "productos": jer["productos"], "tiendas": jer["tiendas"], "series": jer["series"],
            "productos_con_mas_de_un_departamento": jer["productos_con_mas_de_un_departamento"],
            "productos_con_mas_de_una_categoria": jer["productos_con_mas_de_una_categoria"],
            "tiendas_con_mas_de_un_estado": jer["tiendas_con_mas_de_un_estado"],
            "productos_por_departamento_igual_en_todas_las_tiendas": mismos_en_todas,
            "productos_por_departamento": comun,
            "calendario_desde": rango["desde"], "calendario_hasta": rango["hasta"],
            "calendario_dias_que_faltan": rango["dias_que_faltan"],
            "primer_dia_venta": {"d": dias[0], "fecha": primero.strftime("%Y-%m-%d"), "dia": DIAS_ES[primero.dayofweek]},
            "ultimo_dia_venta": {"d": dias[-1], "fecha": ultimo.strftime("%Y-%m-%d"), "dia": DIAS_ES[ultimo.dayofweek]},
            "semanas_venta": len(sem_v), "semana_minima": sem_v[0], "semana_maxima": sem_v[-1],
            "semanas_venta_incompletas": len(sem_venta["semanas_incompletas"]),
            "semanas_precios": len(sem_precios), "semanas_precios_iguales_a_venta": sem_precios == sem_v,
            "fin_construccion": {"fecha": hasta_c.strftime("%Y-%m-%d"), "dia": DIAS_ES[hasta_c.dayofweek],
                                 "semana": semana_cruza},
            "productos_tienda_sin_precio": int(sin_precio_pares.sum()), "precios_sin_producto_tienda": precios_sin_par,
            "semanas_calendario_sin_precio": len(set(semanas_cal) - set(sem_precios)),
            "dias_calendario_sin_venta": dias_cal_sin_venta,
            "unidades": int(U.sum()), "dias_con_venta_y_sin_precio": dol["dias_con_venta_y_sin_precio"],
            "dias_sin_precio": dol["dias_sin_precio"], "dolares": dolares_redondeados(dol["centimos"]),
        }
        r["cifras_de_control"] = cc
        comprobaciones = [
            {"que": "filas de venta, precios y calendario",
             "resultado": f"{fmt(cc['filas_venta'])}, {fmt(cc['filas_precios'])} y {fmt(cc['filas_calendario'])}"},
            {"que": "claves del grano repetidas en venta, precios y calendario",
             "resultado": f"{fmt(cc['clave_venta_filas_repetidas'])}, {fmt(cc['clave_precios_filas_repetidas'])} y "
                          f"{fmt(cc['clave_calendario_filas_repetidas'])} filas"},
            {"que": "productos, tiendas y series", "resultado": f"{fmt(cc['productos'])}, {fmt(cc['tiendas'])} y "
                                                                f"{fmt(cc['series'])}"},
            {"que": "productos por departamento iguales en las diez tiendas",
             "resultado": "sí" if mismos_en_todas else "no"},
            {"que": "días de la venta", "resultado": f"{cc['primer_dia_venta']['d']} es el {cc['primer_dia_venta']['dia']} "
                                                    f"{cc['primer_dia_venta']['fecha']}; {cc['ultimo_dia_venta']['d']} es "
                                                    f"el {cc['ultimo_dia_venta']['dia']} {cc['ultimo_dia_venta']['fecha']}"},
            {"que": "semanas de la venta", "resultado": f"{fmt(cc['semanas_venta'])}, de la {cc['semana_minima']} a la "
                                                       f"{cc['semana_maxima']}; incompletas {fmt(cc['semanas_venta_incompletas'])}"},
            {"que": "semanas de los precios iguales a las de la venta",
             "resultado": "sí" if cc["semanas_precios_iguales_a_venta"] else "no"},
            {"que": "último día de la construcción", "resultado": f"{cc['fin_construccion']['dia']} "
                                                                f"{cc['fin_construccion']['fecha']}, semana "
                                                                f"{cc['fin_construccion']['semana']}"},
            {"que": "productos-tienda sin precio y precios sin producto-tienda",
             "resultado": f"{fmt(cc['productos_tienda_sin_precio'])} y {fmt(cc['precios_sin_producto_tienda'])}"},
            {"que": "semanas del calendario sin precio y días del calendario sin venta",
             "resultado": f"{fmt(cc['semanas_calendario_sin_precio'])} y {fmt(cc['dias_calendario_sin_venta'])}"},
            {"que": "unidades", "resultado": fmt(cc["unidades"])},
            {"que": "días con venta y sin precio; días sin precio",
             "resultado": f"{fmt(cc['dias_con_venta_y_sin_precio'])}; {fmt(cc['dias_sin_precio'])}"},
            {"que": "dólares con el precio de su semana", "resultado": fmt(cc["dolares"], 2)},
        ]
        r["comprobaciones"] = comprobaciones
        r["contradicciones"] = contradicciones
        r["forma_entrega"] = "tablas_separadas"
        r["entrega"] = ["hechos_series", "dim_producto", "dim_tienda", "Calendario"]
        r["plan_cruces"] = PLAN_CRUCES
        r["quien_cruza"] = ("la transformación, con los controles de integracion-datos en cada cruce: todos parten "
                            "de la venta en filas o de la tabla de series, que solo existen después de reestructurar "
                            "la venta (C-01)")
        calidad = json.loads(CALIDAD.read_text(encoding="utf-8"))
        r["cruces_de_calidad"] = [{k: x[k] for k in ("izquierda", "derecha", "clave", "sin_pareja_izquierda",
                                                      "sin_pareja_derecha")} for x in calidad["cruces"]]
        r["aprobado"] = leer_aprobacion(DISENO)
        r["pendientes"] = pendientes_del_diseno(r["aprobado"])
        r["teoria_aplicada"] = TEORIA
        r["datos_personales"] = []
        r["datos_personales_nota"] = (
            "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las "
            "reglas de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada "
            "de personas. Este método no usa ni deja ninguna columna de datos personales.")
        r["limites"] = LIMITES
        if paradas:
            contradicciones.extend({"que": p} for p in paradas)

        # ── 5.9 El Calendario, solo con el diseño aprobado y sin contradicciones (método, apartado 9) ──
        # Se valida antes de guardar (error 15): con un problema no se escribe y el estado pasa a PARADO.
        artefactos_extra = []
        if r["aprobado"]["aprobado"] and not contradicciones:
            t = time.perf_counter()
            calendario = construir_calendario(cal, PERIODOS)
            problemas = validar_calendario(calendario, cal, par)
            contradicciones.extend({"que": f"Calendario: {p}"} for p in problemas)
            if not problemas:
                calendario.to_parquet(SALIDA_CALENDARIO, index=False)
                dias_periodo = {str(k): int(v) for k, v in calendario["periodo"].value_counts().items()}
                r["calendario"].update({
                    "fichero": CALENDARIO_REL, "sha256": huella(SALIDA_CALENDARIO), "filas": int(len(calendario)),
                    "columnas": COLUMNAS_CALENDARIO, "dias_por_periodo": dias_periodo,
                    "semanas_sin_anterior": sorted(int(w) for w in
                                                   calendario.loc[calendario["wm_yr_wk_anterior"].isna(), "wm_yr_wk"].unique()),
                    "construccion": f"construido el {r['fecha_ejecucion'][:10]} con el diseño aprobado por "
                                    f"{r['aprobado']['quien']} el {r['aprobado']['fecha']}"})
                for x in r["tablas"]:
                    if x["tabla"] == "Calendario":
                        unico = clave_del_grano(calendario, ["d"])
                        x.update({"fichero": CALENDARIO_REL, "clave_unica": unico["clave_unica"],
                                  "filas_repetidas": unico["filas_repetidas"],
                                  "nota": "construido por este script; las demás tablas las construye la transformación"})
                artefactos_extra.append(CALENDARIO_REL)
            partes["calendario_construido"] = round(time.perf_counter() - t, 2)
        estado, riesgo = estado_y_riesgo(r["aprobado"], contradicciones)
        falta = "la aprobación del responsable del caso del diseño" if not r["aprobado"]["aprobado"] else "revisar el diseño"
        r["resultado"] = {
            "estado": estado, "riesgo": riesgo,
            "resumen": (f"Diseño comprobado sobre las tres tablas corregidas: {fmt(len(contradicciones))} "
                        f"contradicciones con los datos. Cuatro tablas de entrega (la de series, dos dimensiones y "
                        f"el Calendario) y {fmt(len(PLAN_CRUCES))} cruces en el plan, todos muchos a uno."),
            "artefactos": ["informes/modelado-datos.json", "informes/modelado-datos.md"] + artefactos_extra,
            "siguiente": (f"falta {falta}. Con ella, este script se amplía con su prueba para construir el Calendario "
                          f"(método, apartado 9) y se escriben las reglas de transformación." if estado == "PARADO"
                          else "las reglas de transformación y transformacion-datos, con el plan de cruces."),
        }
        r["huellas_despues"] = {f"data/processed/{ENTRADAS[k]}": huella(p) for k, p in rutas.items()}
        cambiadas = [k for k, v in r["huellas_despues"].items() if v != huellas[k.split("/")[-1].split("_")[0]]]
        r["validacion"] = {"huellas_iguales_antes_y_despues": not cambiadas, "tablas_cambiadas": cambiadas}
    except Exception as error:  # el JSON se escribe también cuando falla (resultado.md, regla 5)
        r["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(error).__name__}: {error}",
                          "artefactos": ["informes/modelado-datos.json"], "siguiente": "arreglar el fallo y repetir"}
        r.setdefault("pendientes", [])
        partes["total"] = round(time.perf_counter() - inicio, 2)
        r["duracion_por_parte"] = partes
        SALIDA_JSON.write_text(json.dumps(a_json_limpio(r), ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    t = time.perf_counter()
    r["duracion_por_parte"] = partes
    r["duracion_segundos"] = round(time.perf_counter() - inicio, 2)
    limpio = a_json_limpio(r)
    SALIDA_JSON.write_text(json.dumps(limpio, ensure_ascii=False, indent=2), encoding="utf-8")
    SALIDA_MD.write_text(generar_md(limpio), encoding="utf-8")
    print(f"estado {limpio['resultado']['estado']} · {limpio['duracion_segundos']} s · "
          f"escritura {round(time.perf_counter() - t, 2)} s")
    return limpio


if __name__ == "__main__":
    print("intérprete:", sys.executable)
    principal()
