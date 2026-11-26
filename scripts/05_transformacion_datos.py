"""Transformación de datos del caso 69: la tabla de series, dim_producto y dim_tienda.

Aplica config/negocio/reglas-transformacion.md (aprobado por el responsable del caso el 24/11/2026) con el método
transformacion-datos. Pasa la venta a filas, hace los cruces 1 a 7 del plan aprobado de informes/modelado-datos.json
con los controles de integracion-datos, agrega a una fila por departamento en una tienda y día, añade las marcas y el
precio medio de la semana anterior y guarda las tres tablas en data/processed/ solo si pasan sus validaciones. Deja
informes/transformacion-datos.json, el informe Markdown generado de él y una ficha por transformación nueva en el
registro de transformaciones.

Depende de lo que dejan otros scripts (error 2): data/processed/venta_corregido.parquet y precios_corregido.parquet
(scripts/03_correccion_datos.py) y data/processed/calendario.parquet (scripts/04_modelado_datos.py). Antes de empezar
comprueba sus huellas contra informes/correccion-datos.json e informes/modelado-datos.json.

Uso: python -W error scripts/05_transformacion_datos.py [--raiz CARPETA]
  --raiz: carpeta con la estructura del caso (data/processed/, informes/ y config/modelo/). Por defecto, la
  del caso. La prueba la usa para ejecutar el script sobre datos pequeños.
Sale con 0 si el estado es OK o AVISO y con 1 si es PARADO o ERROR.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import inspect
import json
import math
import platform
import re
import sys
import time
import traceback
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método transformacion-datos con que se escribió este script
SCRIPT_REL = "scripts/05_transformacion_datos.py"
PETICION_REL = "petición 09"
REGLAS_REL = "config/negocio/reglas-transformacion.md"

# Fecha de referencia de los datos (reglas, apartado 5, «Fechas»)
FECHA_DATOS = "2015-05-22"

ENTRADAS = {"venta": "data/processed/venta_corregido.parquet",
            "precios": "data/processed/precios_corregido.parquet",
            "calendario": "data/processed/calendario.parquet"}
SALIDAS = {"hechos_series": "data/processed/hechos_series.parquet",
           "dim_producto": "data/processed/dim_producto.parquet",
           "dim_tienda": "data/processed/dim_tienda.parquet"}
QUE_ES_UNA_FILA = {"hechos_series": "un departamento en una tienda un día",
                   "dim_producto": "un producto",
                   "dim_tienda": "una tienda"}
CORRECCION_REL = "informes/correccion-datos.json"
MODELADO_REL = "informes/modelado-datos.json"
CALIDAD_REL = "informes/calidad-datos.json"
PROTECCION_REL = "config/fuentes/proteccion-datos.json"
JSON_REL = "informes/transformacion-datos.json"
MD_REL = "informes/transformacion-datos.md"
REGISTRO_REL = "config/modelo/registro-transformaciones.md"

# Partición de las reglas, apartado 5, «Fechas»: los dos días de cada tramo entran en él
PARTICION = {"columna_fecha": "date",
             "desarrollo": {"desde": "2011-01-29", "hasta": "2014-05-22"},
             "validacion": {"desde": "2014-05-23", "hasta": "2015-05-22"},
             "fuente": "reglas-negocio §5, «Fechas»"}
PERIODOS = ["construccion", "validacion"]

# Umbral de la demanda intermitente: menos de 10 unidades de media al día (reglas, apartado 5, D8)
UMBRAL_INTERMITENTE = 10
CLASES_CERO = ["cierre", "25_diciembre", "demanda_intermitente", "resto"]
SNAP_DE_ESTADO = {"CA": "snap_ca", "TX": "snap_tx", "WI": "snap_wi"}

# En el precio medio solo cuentan los productos con precio desde cuatro semanas antes: con 28 días de horizonte, todo
# producto que cuenta ya se vendía antes del origen (reglas, apartado 5, «El precio»; el responsable del caso, 24/11/2026)
SEMANAS_PREVIAS_CON_PRECIO = 4

# Las 26 columnas de la tabla de series, en su orden (reglas de transformación, apartado 1)
COLUMNAS_SERIES = ["store_id", "dept_id", "d", "cat_id", "state_id", "unidades", "dolares", "date", "year", "month",
                   "weekday", "wday", "wm_yr_wk", "wm_yr_wk_anterior", "event_name_1", "event_type_1",
                   "event_name_2", "event_type_2", "snap", "periodo", "mes_parcial", "semana_parcial",
                   "cierre_tienda", "fuera_del_error", "clase_cero", "precio_medio_semana_anterior"]
COLUMNAS_DIM_PRODUCTO = ["item_id", "dept_id", "cat_id"]
COLUMNAS_DIM_TIENDA = ["store_id", "state_id"]
CLAVE_SERIES = ["store_id", "dept_id", "d"]

# Los cruces que hace este script. Tienen que ser los del plan aprobado, en su orden (método, apartado 2, «Integración»).
CRUCES = [
    {"orden": 1, "partida": "venta en filas", "se_une": "Calendario", "clave_partida": ["d"], "clave_une": ["d"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes": ["unidades"]},
    {"orden": 2, "partida": "venta en filas", "se_une": "precios", "clave_partida": ["item_id", "store_id", "wm_yr_wk"],
     "clave_une": ["item_id", "store_id", "wm_yr_wk"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes": ["unidades"]},
    {"orden": 3, "partida": "venta en filas", "se_une": "dim_producto", "clave_partida": ["item_id"],
     "clave_une": ["item_id"], "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes": ["unidades", "centimos"]},
    {"orden": 4, "partida": "hechos_series", "se_une": "dim_tienda", "clave_partida": ["store_id"],
     "clave_une": ["store_id"], "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes": ["unidades", "centimos"]},
    {"orden": 5, "partida": "hechos_series", "se_une": "Calendario", "clave_partida": ["d"], "clave_une": ["d"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes": ["unidades", "centimos"]},
    {"orden": 6, "partida": "precios", "se_une": "dim_producto", "clave_partida": ["item_id"], "clave_une": ["item_id"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes": ["centimos_precio"]},
    {"orden": 7, "partida": "hechos_series", "se_une": "precio medio del departamento por semana",
     "clave_partida": ["store_id", "dept_id", "wm_yr_wk_anterior"], "clave_une": ["store_id", "dept_id", "wm_yr_wk"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes": ["unidades", "centimos"]},
]
CAMPOS_DEL_PLAN = ["orden", "partida", "se_une", "clave_partida", "clave_une", "cardinalidad", "tipo_cruce"]
NOMBRE_MAGNITUD = {"unidades": "unidades", "centimos": "dólares (en céntimos)",
                   "centimos_precio": "sell_price (en céntimos)"}

TEORIA = [
    {"apartado": "12.3", "por_que": "la venta llega en ancho, un día por columna; melt la pasa a una fila por producto, "
                                    "tienda y día para unirle la semana y el precio"},
    {"apartado": "12.5 y 12.6", "por_que": "al subir de producto a departamento las unidades y los dólares son flujos y "
                                           "se suman con su cuadre antes y después; el precio es un nivel y no se suma"},
    {"apartado": "3.5", "por_que": "el precio medio del departamento es la media simple de sus productos con precio "
                                   "desde cuatro semanas antes, fijada por el responsable del caso el 24/11/2026; la ponderada "
                                   "necesitaría unidades que en el horizonte no se conocen"},
    {"apartado": "12.7", "por_que": "no se suma un nivel: el precio medio nunca se suma entre filas ni entre series"},
]

LIMITES = [
    "Los cruces comparan claves exactas: una clave que existe pero apunta a otra entidad no se detecta.",
    "El mismo producto o la misma tienda con dos códigos no se vería como repetido.",
    "El departamento de un producto y el estado de una tienda se toman como fijos: así están en los datos.",
    "Las sumas de control cubren las unidades, los dólares y el precio en céntimos de cada cruce.",
    "clase_cero usa la media de la serie en su periodo entero: sirve para describir y nunca entra como variable del "
    "modelo.",
    "Los primeros días de cada serie sin la historia que piden las variables se cuentan en el paso 5.",
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
    """Tipos de numpy y pandas a Python; NaN, infinito y NA a null (programacion-del-caso, error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json_limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json_limpio(v) for v in obj]
    if obj is None or obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        valor = float(obj)
        return None if math.isnan(valor) or math.isinf(valor) else valor
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def fmt(n, decimales=0):
    """Número a la española: punto de miles y coma decimal."""
    if n is None:
        return "sin dato"
    texto = f"{n:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def dolares(centimos):
    """Céntimos enteros a dólares con dos decimales, sin pérdida."""
    return float((Decimal(int(centimos)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def a_centimos(precio):
    """Precio en céntimos enteros; None si algún precio falta o tiene más de dos decimales."""
    x = np.asarray(precio, dtype="float64") * 100
    redondeado = np.rint(x)
    if not np.all(np.isfinite(x)) or np.any(np.abs(x - redondeado) > 1e-6):
        return None
    return redondeado.astype(np.int64)


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def tipo_de_clave(serie):
    """Familia del tipo de una columna de clave: entero, texto u otro (formato de la clave, integracion-datos §3)."""
    if pd.api.types.is_integer_dtype(serie.dtype):
        return "entero"
    if pd.api.types.is_string_dtype(serie.dtype):
        return "texto"
    return str(serie.dtype)


def parada(codigo, donde, motivo):
    """Una parada del script: su código, el paso en que para y el motivo."""
    return {"codigo": codigo, "donde": donde, "motivo": motivo}


# ══ 3. Al empezar ═══════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Estado de los JSON anteriores, huellas de las entradas y plan de cruces (resultado.md, «Al empezar»)."""
    paradas = []
    leidos = {}
    for nombre, rel in (("correccion", CORRECCION_REL), ("modelado", MODELADO_REL)):
        ruta = raiz / rel
        if not ruta.exists():
            paradas.append(parada("entrada_no_ok", "al empezar", f"falta {rel}"))
            continue
        leidos[nombre] = json.loads(ruta.read_text(encoding="utf-8"))
        estado = leidos[nombre].get("resultado", {}).get("estado")
        if estado != "OK":
            paradas.append(parada("entrada_no_ok", "al empezar", f"{rel} está en {estado}, no en OK"))
    if "modelado" in leidos and not (leidos["modelado"].get("aprobado") or {}).get("aprobado"):
        paradas.append(parada("entrada_no_ok", "al empezar", "el diseño de modelado-datos.json no está aprobado"))
    # Huellas: la venta y los precios, contra salidas de la corrección; el Calendario, contra el modelado
    esperadas = {}
    if "correccion" in leidos:
        por_tabla = {s.get("tabla"): s.get("sha256") for s in leidos["correccion"].get("salidas", [])}
        esperadas["venta"] = por_tabla.get("venta")
        esperadas["precios"] = por_tabla.get("precios")
    if "modelado" in leidos:
        esperadas["calendario"] = (leidos["modelado"].get("calendario") or {}).get("sha256")
    huellas = {}
    for nombre, rel in ENTRADAS.items():
        ruta = raiz / rel
        if not ruta.exists():
            paradas.append(parada("huella_distinta", "al empezar", f"falta {rel}"))
            continue
        huellas[nombre] = huella(ruta)
        if nombre in esperadas and huellas[nombre] != esperadas[nombre]:
            paradas.append(parada("huella_distinta", "al empezar",
                                  f"la huella de {rel} no es la de su JSON ({huellas[nombre][:12]} frente a "
                                  f"{str(esperadas[nombre])[:12]})"))
    # El plan: los cruces de este script tienen que ser los del plan aprobado, en su orden
    if "modelado" in leidos:
        plan = [{c: x.get(c) for c in CAMPOS_DEL_PLAN} for x in leidos["modelado"].get("plan_cruces", [])]
        propios = [{c: x[c] for c in CAMPOS_DEL_PLAN} for x in CRUCES]
        if plan != propios:
            distintos = [p["orden"] for p in propios if p not in plan]
            paradas.append(parada("cruce_fuera_del_plan", "al empezar",
                                  f"los cruces {distintos} no están así en el plan aprobado de modelado-datos.json"))
    return leidos, huellas, paradas


# ══ 4. Cruces con los controles de integracion-datos ════════════════════════════
def cruzar(cfg, izq, der):
    """Un cruce por la izquierda, muchos a uno, con la auditoría previa y el control posterior de integracion-datos.

    Renombra la clave del maestro a los nombres de la partida y une con merge(validate, indicator). Devuelve el
    resultado (None si para), el informe del cruce y la parada si la hay.
    """
    ci, cd, mags = cfg["clave_partida"], cfg["clave_une"], cfg["magnitudes"]
    der = der.rename(columns=dict(zip(cd, ci)))
    info = {"orden": cfg["orden"], "partida": cfg["partida"], "se_une": cfg["se_une"],
            "clave": {"partida": ci, "se_une": cd}, "tipo_cruce": cfg["tipo_cruce"],
            "cardinalidad_esperada": cfg["cardinalidad"]}
    # ── Auditoría previa: repetidas en el maestro, nulas, formato y huérfanas por conjuntos de claves ──
    repetida = der.duplicated(ci, keep=False)
    info["repetidas_maestro"] = {"claves": int(der.loc[repetida, ci].drop_duplicates().shape[0]),
                                 "filas": int(repetida.sum())}
    info["claves_nulas"] = {"partida": int(izq[ci].isna().any(axis=1).sum()),
                            "se_une": int(der[ci].isna().any(axis=1).sum())}
    tipos_i = [tipo_de_clave(izq[c]) for c in ci]
    tipos_d = [tipo_de_clave(der[c]) for c in ci]
    distintos = [t[c].dropna().drop_duplicates() for t in (izq, der) for c in ci if tipo_de_clave(t[c]) == "texto"]
    espacios = sum(int((s != s.str.strip()).sum()) for s in distintos)
    info["tipos"] = {"partida": tipos_i, "se_une": tipos_d}
    info["espacios_en_la_clave"] = espacios
    info["formato_igual"] = tipos_i == tipos_d and espacios == 0
    agregado = {"filas": (ci[0], "size")} | {m: (m, "sum") for m in mags}
    por_clave = izq.groupby(ci, dropna=False, sort=False).agg(**agregado)
    claves_der = (pd.Index(der[ci[0]].drop_duplicates()) if len(ci) == 1
                  else pd.MultiIndex.from_frame(der[ci].drop_duplicates()))
    con_pareja = por_clave.index.isin(claves_der)
    huerfanas = por_clave.loc[~con_pareja]
    info["huerfanas_partida"] = {
        "claves": int(len(huerfanas)), "filas": int(huerfanas["filas"].sum()),
        "peso": [{"magnitud": NOMBRE_MAGNITUD[m],
                  "pct": None if por_clave[m].sum() == 0 else float(huerfanas[m].sum() / por_clave[m].sum() * 100)}
                 for m in mags]}
    info["huerfanas_maestro"] = {"claves": int((~claves_der.isin(por_clave.index)).sum())}
    partida_repite = bool((por_clave["filas"] > 1).any())
    maestro_repite = info["repetidas_maestro"]["filas"] > 0
    info["cardinalidad_observada"] = {(True, False): "N:1", (False, False): "1:1", (True, True): "N:N",
                                      (False, True): "1:N"}[(partida_repite, maestro_repite)]
    info["filas_antes"] = int(len(izq))
    sumas_antes = {m: int(izq[m].sum()) for m in mags}

    def cerrar(motivo, df=None):
        """Cierra el cruce: hecho solo si hay resultado y ningún motivo de parada."""
        info["motivo_parada"] = motivo
        info["hecho"] = motivo is None and df is not None
        if info["hecho"]:
            return df.drop(columns="_merge"), info, None
        return None, info, parada(f"cruce_{cfg['orden']}", f"cruce {cfg['orden']}", motivo)

    if not info["formato_igual"]:
        info["filas_despues"] = None
        return cerrar("la clave tiene formato distinto a cada lado")
    # ── Cruce validando la cardinalidad; si validate falla, se mide sin validar y no se guarda ──
    der = der.astype({c: izq[c].dtype for c in ci})
    try:
        df = izq.merge(der, on=ci, how="left", validate="many_to_one", indicator=True, suffixes=("", "_maestro"))
    except pd.errors.MergeError as error:
        medido = len(izq.merge(der, on=ci, how="left"))
        info.update({"error_validate": str(error), "filas_despues": int(medido),
                     "filas_de_mas": int(medido - len(izq))})
        return cerrar(f"el maestro repite {info['repetidas_maestro']['claves']} claves en "
                      f"{info['repetidas_maestro']['filas']} filas: el cruce N:1 daría {medido - len(izq)} filas de más")
    # ── Control posterior: filas, columnas, indicator, nulos nuevos y sumas ──
    origen = df["_merge"].value_counts()
    info["resultado_indicator"] = {"con_pareja": int(origen.get("both", 0)),
                                   "solo_partida": int(origen.get("left_only", 0)),
                                   "solo_maestro": int(origen.get("right_only", 0))}
    info["filas_despues"] = int(len(df))
    info["columnas_antes"] = int(izq.shape[1])
    info["columnas_despues"] = int(df.shape[1] - 1)
    aportadas = [c for c in der.columns if c not in ci]
    sin_pareja = df["_merge"] == "left_only"
    info["nulos_nuevos"] = [{"columna": c, "de_huerfanas": int(df.loc[sin_pareja, c].isna().sum()),
                             "vacios_del_maestro": int(df.loc[~sin_pareja, c].isna().sum())} for c in aportadas]
    info["huerfanas_cuadran"] = info["huerfanas_partida"]["filas"] == info["resultado_indicator"]["solo_partida"]
    info["sumas_control"] = [{"magnitud": NOMBRE_MAGNITUD[m], "antes": sumas_antes[m], "despues": int(df[m].sum()),
                              "coincide": sumas_antes[m] == int(df[m].sum())} for m in mags]
    crece = info["filas_despues"] != info["filas_antes"]
    sumas_mal = not all(s["coincide"] for s in info["sumas_control"])
    motivo = ("las filas cambian" if crece else "las sumas de control no coinciden" if sumas_mal
              else "las huérfanas contadas antes no son las left_only del cruce" if not info["huerfanas_cuadran"]
              else None)
    return cerrar(motivo, df)


# ══ 5. Transformaciones ═════════════════════════════════════════════════════════
# ── 5.1 Dimensiones (reglas de transformación, apartados 2 y 3) ──
def construir_dim_producto(venta):
    """Una fila por producto con su departamento y su categoría, de la venta (reglas, apartado 4)."""
    return (venta[COLUMNAS_DIM_PRODUCTO].drop_duplicates().sort_values("item_id", kind="stable")
            .reset_index(drop=True))


def construir_dim_tienda(venta):
    """Una fila por tienda con su estado, de la venta (reglas, apartado 4)."""
    return (venta[COLUMNAS_DIM_TIENDA].drop_duplicates().sort_values("store_id", kind="stable")
            .reset_index(drop=True))


# ── 5.2 La venta en filas y los dólares (cruces 1 a 3) ──
def venta_en_filas(venta, dias):
    """De una fila por producto y tienda con un día por columna a una fila por producto, tienda y día (manual 12.3)."""
    return venta.melt(id_vars=["item_id", "store_id"], value_vars=dias, var_name="d", value_name="unidades")


def centimos_del_dia(df):
    """Céntimos de cada fila: unidades por el precio de su semana; cero en los días sin precio (reglas, apartado 5)."""
    sin_precio = df["sell_price"].isna().to_numpy()
    precio = np.where(sin_precio, 0, np.rint(df["sell_price"].fillna(0).to_numpy() * 100)).astype(np.int64)
    return df["unidades"].to_numpy(np.int64) * precio


# ── 5.3 De producto a serie (cambio de granularidad) ──
def agregar_a_series(df):
    """Suma las unidades y los céntimos de los productos de cada departamento en cada tienda y día (manual 12.6).

    La categoría entra en la clave del grupo: si un departamento tuviera dos, saldrían dos filas con la misma clave de
    serie y la validación de la clave lo pararía.
    """
    return (df.groupby(["store_id", "dept_id", "cat_id", "d"], sort=False, observed=True)
            .agg(unidades=("unidades", "sum"), centimos=("centimos", "sum")).reset_index())


def snap_del_estado(df):
    """El SNAP del estado de la tienda, de snap_ca, snap_tx o snap_wi; las otras dos columnas no se quedan."""
    condiciones = [df["state_id"] == e for e in SNAP_DE_ESTADO]
    valores = [df[c] for c in SNAP_DE_ESTADO.values()]
    df["snap"] = np.select(condiciones, valores, default=-1).astype(np.int64)
    return df.drop(columns=list(SNAP_DE_ESTADO.values()))


# ── 5.4 Marcas para medir el error y describir los ceros (reglas, apartado 5, D8) ──
def marcas(df):
    """cierre_tienda, fuera_del_error y clase_cero, con la regla de clasificar_ceros de la corrección.

    La media de cada serie se calcula en su periodo, sin contar sus días de cierre. clase_cero va en este orden:
    cierre, 25_diciembre, demanda_intermitente y resto; vacía en los días con venta.
    """
    cero = df["unidades"] == 0
    df["cierre_tienda"] = df.groupby(["store_id", "d"], sort=False)["unidades"].transform("sum") == 0
    navidad = (df["date"].dt.month == 12) & (df["date"].dt.day == 25)
    df["fuera_del_error"] = navidad | df["cierre_tienda"]
    abierto = df["unidades"].where(~df["cierre_tienda"])
    media = abierto.groupby([df["store_id"], df["dept_id"], df["periodo"]], sort=False).transform("mean")
    intermitente = media < UMBRAL_INTERMITENTE
    cierre = df["cierre_tienda"]
    condiciones = [cero & cierre, cero & ~cierre & navidad, cero & ~cierre & ~navidad & intermitente, cero]
    clase = np.select([c.to_numpy() for c in condiciones], CLASES_CERO, default="SIN_REGLA")
    df["clase_cero"] = pd.Series(clase, index=df.index, dtype="str").where(cero)
    return df


def series_intermitentes(df):
    """Media de cada serie en su periodo sin sus días de cierre, por otro cálculo (sumas entre recuentos)."""
    abiertos = df.loc[~df["cierre_tienda"]]
    g = abiertos.groupby(["periodo", "store_id", "dept_id"]).agg(suma=("unidades", "sum"), dias=("unidades", "size"))
    g["media"] = g["suma"] / g["dias"]
    resultado = {}
    for p in PERIODOS:
        x = g.loc[g.index.get_level_values("periodo") == p]
        bajo = x[x["media"] < UMBRAL_INTERMITENTE]
        resultado[p] = {"series": int(len(bajo)),
                        "departamentos": sorted({str(k[2]) for k in bajo.index}),
                        "lista": [{"serie": f"{k[1]} {k[2]}", "media": round(float(v), 2)}
                                  for k, v in bajo["media"].sort_index().items()]}
    return resultado


# ── 5.5 Precio medio del departamento de la semana anterior (cruces 6 y 7; reglas, apartado 5, D9) ──
def precio_medio_semana(precios_dept, orden_semanas):
    """Media simple de sell_price de los productos del departamento con precio en esa tienda esa semana que ya lo
    tenían SEMANAS_PREVIAS_CON_PRECIO semanas antes (reglas, apartado 5, «El precio»).

    Un producto entra la semana de su primera venta y no vuelve a quedarse sin precio: contado desde que entra, la
    media de una semana dentro del horizonte avisaría de esa venta. La posición de cada semana sale del orden de las
    fechas, porque el código salta al cambiar de año. No se pondera por unidades ni se redondea (el responsable del caso, 24/11/2026). Es
    un nivel: nunca se suma. Devuelve todos los grupos con algún precio; la media queda vacía en los que no tienen
    ningún producto que cuente.
    """
    posicion = {int(w): i for i, w in enumerate(orden_semanas)}
    pos = precios_dept["wm_yr_wk"].map(posicion)
    primera = pos.groupby([precios_dept["store_id"], precios_dept["item_id"]], sort=False).transform("min")
    cuenta = (pos - primera) >= SEMANAS_PREVIAS_CON_PRECIO
    con_cuenta = precios_dept.assign(cuenta=cuenta, precio_que_cuenta=precios_dept["sell_price"].where(cuenta))
    return (con_cuenta.groupby(["store_id", "dept_id", "wm_yr_wk"], sort=True)
            .agg(precio_medio_semana_anterior=("precio_que_cuenta", "mean"), productos_con_precio=("item_id", "size"),
                 productos_que_cuentan=("cuenta", "sum"))
            .reset_index())


def semanas_por_orden(cal):
    """Las semanas del Calendario en el orden de sus fechas."""
    return [int(w) for w in cal.groupby("wm_yr_wk")["date"].min().sort_values().index]


def anterior_por_orden(cal):
    """La semana anterior de cada semana del Calendario, tomada por el orden de las fechas."""
    orden = semanas_por_orden(cal)
    return {b: a for a, b in zip(orden, orden[1:])}


# ══ 6. Registro de exclusiones y lo pendiente para el modelo ═══════════════════
def exclusiones(df, cal, pt_sin_precio, dias_venta):
    """La tabla del registro de exclusiones (reglas de transformación, apartado 4), con sus cifras del código."""
    navidad = (df["date"].dt.month == 12) & (df["date"].dt.day == 25)

    def resumen(mascara):
        """Días de serie, unidades y dólares de unas filas, por periodo."""
        return {p: {"dias_serie": int((mascara & (df["periodo"] == p)).sum()),
                    "unidades": int(df.loc[mascara & (df["periodo"] == p), "unidades"].sum()),
                    "dolares": dolares(df.loc[mascara & (df["periodo"] == p), "centimos"].sum())} for p in PERIODOS}

    fuera_25 = df["cierre_tienda"] & ~navidad
    cierres = (df.loc[fuera_25].groupby(["store_id", "d", "date", "periodo"]).size().reset_index(name="dias_serie"))
    sin_precio_medio = df["precio_medio_semana_anterior"].isna()
    cal_sin_venta = cal.loc[~cal["d"].isin(dias_venta)]
    return [
        {"clase": "25 de diciembre", "columna": "fuera_del_error",
         "que_sale": "los días de serie del 25 de diciembre", "de_que_calculo": "el error, el sesgo y la ventaja",
         "recuento": resumen(navidad), "se_puede_recuperar": "sí: siguen en la tabla de series con su venta"},
        {"clase": "cierre fuera del 25 de diciembre", "columna": "fuera_del_error",
         "que_sale": "el cierre de una tienda entera fuera del 25 de diciembre",
         "de_que_calculo": "el error, el sesgo y la ventaja, como un 25 de diciembre",
         "recuento": resumen(fuera_25),
         "detalle": [{"tienda": str(r.store_id), "fecha": r.date.strftime("%Y-%m-%d"), "d": str(r.d),
                      "periodo": str(r.periodo), "dias_serie": int(r.dias_serie)} for r in cierres.itertuples()],
         "se_puede_recuperar": "sí: siguen en la tabla de series a cero"},
        {"clase": "sin precio medio de la semana anterior", "columna": "precio_medio_semana_anterior",
         "que_sale": "los días sin semana anterior o cuya semana anterior no tiene ningún producto con precio cuatro "
                     "semanas antes (reglas, apartado 5)",
         "de_que_calculo": "lo que use el precio medio de la semana anterior",
         "recuento": resumen(sin_precio_medio),
         "semanas": sorted(int(w) for w in df.loc[sin_precio_medio, "wm_yr_wk"].unique()),
         "dias": int(df.loc[sin_precio_medio, "d"].nunique()),
         "se_puede_recuperar": "sí: siguen en la tabla de series con el precio vacío"},
        {"clase": "productos-tienda sin ningún precio", "columna": None,
         "que_sale": "nada: no venden ningún día y suman cero a su departamento", "de_que_calculo": "ninguno",
         "recuento": {"productos_tienda": int(pt_sin_precio["n"]), "unidades": int(pt_sin_precio["unidades"]),
                      "dolares": 0.0},
         "se_puede_recuperar": "no hace falta: siguen en la venta corregida"},
        {"clase": "días del calendario sin venta", "columna": None,
         "que_sale": "los días del Calendario posteriores a la fecha de referencia",
         "de_que_calculo": "la tabla de series: no tienen venta en el caso",
         "recuento": {"dias": int(len(cal_sin_venta)),
                      "desde": None if cal_sin_venta.empty else cal_sin_venta["date"].min().strftime("%Y-%m-%d"),
                      "hasta": None if cal_sin_venta.empty else cal_sin_venta["date"].max().strftime("%Y-%m-%d")},
         "se_puede_recuperar": "sí: siguen en el Calendario para producción"},
        {"clase": "primeros días sin historia", "columna": None,
         "que_sale": "los primeros días de cada serie sin la historia que piden las variables",
         "de_que_calculo": "la previsión y la comparación con las reglas (reglas, apartado 7)", "recuento": None,
         "nota": "se cuentan en el paso 5, cuando se fijen las variables",
         "se_puede_recuperar": "no: no hay datos antes del 29/01/2011"},
    ]


def pendiente_modelo(df):
    """Cada columna de la tabla de series con su tipo, sus valores o su rango, sin modificar ningún dato."""
    categoricas = {"store_id": False, "dept_id": False, "cat_id": False, "state_id": False, "weekday": True,
                   "event_name_1": False, "event_type_1": False, "event_name_2": False, "event_type_2": False,
                   "periodo": False, "clase_cero": False}
    codigos = {"d": True, "year": True, "month": True, "wday": True, "wm_yr_wk": True, "wm_yr_wk_anterior": True,
               "snap": False}
    marcas_ = ["mes_parcial", "semana_parcial", "cierre_tienda", "fuera_del_error"]
    magnitudes = {"unidades": "unidades", "dolares": "dólares", "precio_medio_semana_anterior": "dólares por unidad"}
    lista = []
    for c, orden in categoricas.items():
        lista.append({"columna": c, "tipo": "categorica", "valores": int(df[c].nunique()), "orden_real": orden,
                      "unidad": None, "minimo": None, "maximo": None})
    for c, orden in codigos.items():
        lista.append({"columna": c, "tipo": "codigo numerico, es categoria", "valores": int(df[c].nunique()),
                      "orden_real": orden, "unidad": None, "minimo": None, "maximo": None})
    for c in marcas_:
        lista.append({"columna": c, "tipo": "marca verdadero o falso", "valores": int(df[c].nunique()),
                      "orden_real": False, "unidad": None, "minimo": None, "maximo": None})
    for c, unidad in magnitudes.items():
        lista.append({"columna": c, "tipo": "magnitud", "valores": int(df[c].nunique()), "orden_real": True,
                      "unidad": unidad, "minimo": float(df[c].min()), "maximo": float(df[c].max())})
    lista.append({"columna": "date", "tipo": "fecha", "valores": int(df["date"].nunique()), "orden_real": True,
                  "unidad": None, "minimo": df["date"].min().strftime("%Y-%m-%d"),
                  "maximo": df["date"].max().strftime("%Y-%m-%d")})
    return lista


# ══ 7. Registro de transformaciones ═════════════════════════════════════════════
CODIGO_FICHA = {
    "series_y_dolares": """larga = venta.melt(id_vars=["item_id", "store_id"], value_vars=dias, var_name="d", value_name="unidades")
larga = larga.merge(calendario[["d", "date", "wm_yr_wk"]], on="d", how="left", validate="many_to_one", indicator=True)   # cruce 1
larga = larga.merge(precios, on=["item_id", "store_id", "wm_yr_wk"], how="left", validate="many_to_one", indicator=True)   # cruce 2
# un día con venta y sin precio para antes de calcular; los días sin precio suman 0 céntimos
larga["centimos"] = larga["unidades"] * round(larga["sell_price"] * 100)
larga = larga.merge(dim_producto, on="item_id", how="left", validate="many_to_one", indicator=True)   # cruce 3
series = larga.groupby(["store_id", "dept_id", "cat_id", "d"]).agg(unidades=("unidades", "sum"), centimos=("centimos", "sum"))
series = series.merge(dim_tienda, ...)   # cruce 4
series = series.merge(calendario, ...)   # cruce 5; snap = snap_ca, snap_tx o snap_wi según state_id
series["dolares"] = series["centimos"] / 100""",
    "marcas": """df["cierre_tienda"] = df.groupby(["store_id", "d"])["unidades"].transform("sum") == 0
df["fuera_del_error"] = navidad | df["cierre_tienda"]
media = df["unidades"].where(~df["cierre_tienda"]).groupby([store_id, dept_id, periodo]).transform("mean")
clase = np.select([cero & cierre, cero & ~cierre & navidad, cero & ~cierre & ~navidad & (media < 10), cero],
                  ["cierre", "25_diciembre", "demanda_intermitente", "resto"])   # vacía en los días con venta""",
    "precio_medio": """precios = precios.merge(dim_producto[["item_id", "dept_id"]], on="item_id", how="left", validate="many_to_one")   # cruce 6
posicion = precios["wm_yr_wk"].map(orden_de_las_semanas)   # por el orden de las fechas
cuenta = posicion - posicion.groupby([precios["store_id"], precios["item_id"]]).transform("min") >= 4
medio = (precios.assign(precio=precios["sell_price"].where(cuenta))
         .groupby(["store_id", "dept_id", "wm_yr_wk"]).agg(precio_medio_semana_anterior=("precio", "mean")))
series = series.merge(medio.rename(columns={"wm_yr_wk": "wm_yr_wk_anterior"}),
                      on=["store_id", "dept_id", "wm_yr_wk_anterior"], how="left", validate="many_to_one")   # cruce 7""",
    "dim_producto": """dim_producto = venta[["item_id", "dept_id", "cat_id"]].drop_duplicates().sort_values("item_id")""",
    "dim_tienda": """dim_tienda = venta[["store_id", "state_id"]].drop_duplicates().sort_values("store_id")""",
}
FUNCIONES_DE_REGLA = {
    "series_y_dolares": ["venta_en_filas", "centimos_del_dia", "agregar_a_series", "snap_del_estado", "cruzar"],
    "marcas": ["marcas"],
    "precio_medio": ["precio_medio_semana", "semanas_por_orden", "cruzar"],
    "dim_producto": ["construir_dim_producto"],
    "dim_tienda": ["construir_dim_tienda"],
}


def huella_regla(clave):
    """Huella corta del código que aplica una regla: si no cambia, una reejecución no añade ficha (método, apartado 6)."""
    modulo = sys.modules[__name__]
    texto = "".join(inspect.getsource(getattr(modulo, f)) for f in FUNCIONES_DE_REGLA[clave]) + CODIGO_FICHA[clave]
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def contenido_fichas(r):
    """Las cinco fichas de esta transformación, con sus nueve campos y las cifras de esta ejecución."""
    c = r["cifras_de_control"]
    quien = (f"el agente analista-preparacion-datos ejecuta `{SCRIPT_REL}` por la petición `{PETICION_REL}`, con las "
             f"reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`{REGLAS_REL}`) y el diseño aprobado por "
             f"El responsable del caso el 24/11/2026.")
    up, dp, fp = c["unidades_por_periodo"], c["dolares_por_periodo"], c["filas_por_periodo"]
    cc, cl = c["clase_cero"], c["cierre_tienda"]
    fe = c["fuera_del_error"]
    return [
        ("series_y_dolares", "hechos_series: la tabla de series con la venta en dólares (cruces 1 a 5)", [
            "`data/processed/hechos_series.parquet` (nueva): `store_id`, `dept_id`, `d`, `cat_id`, `state_id`, "
            "`unidades`, `dolares`, las columnas del Calendario y `snap`.",
            f"la venta llega con una fila por producto y tienda ({fmt(r['entradas'][0]['filas'])} filas) y un día "
            f"por columna ({fmt(c['series_dias'])} días); el precio, por producto, tienda y semana; el Calendario, "
            f"por día.",
            "las preguntas 1, 2 y 4 se miden en una fila por departamento en una tienda y día (reglas, apartado 3 y §5; diseño "
            "§3 y §8).",
            "reglas de transformación, apartado 1; diseño aprobado, cruces 1 a 5. Un día sin precio suma cero dólares; "
            "un día con venta y sin precio para el script (reglas, apartado 5).",
            "la venta pasa a filas, se une con la semana del Calendario, el precio y el departamento con los controles "
            "de integracion-datos y se suma por serie y día en céntimos enteros.\n\n   ```python\n   "
            + CODIGO_FICHA["series_y_dolares"].replace("\n", "\n   ") + "\n   ```",
            quien,
            f"venta en filas: {fmt(c['venta_filas'])} filas, {fmt(c['venta_unidades'])} unidades y "
            f"{fmt(c['venta_dolares'], 2)} dólares; {fmt(c['dias_con_venta_y_sin_precio'])} días con venta y sin "
            f"precio; {fmt(c['dias_sin_precio'])} días sin precio. Tabla de series: {fmt(c['series_filas'])} filas "
            f"con la clave sin repetir; construcción {fmt(fp['construccion'])} filas, {fmt(up['construccion'])} "
            f"unidades y {fmt(dp['construccion'], 2)} dólares; validación {fmt(fp['validacion'])} filas, "
            f"{fmt(up['validacion'])} unidades y {fmt(dp['validacion'], 2)} dólares. Las sumas de los 5 cruces "
            f"coinciden antes y después.",
            f"{fmt(c['series_filas'])} filas y {c['series_columnas']} columnas en `data/processed/hechos_series.parquet`.",
            "borrar `data/processed/hechos_series.parquet`. Las tablas de entrada no cambian.",
        ]),
        ("marcas", "hechos_series: cierre_tienda, fuera_del_error y clase_cero", [
            "`hechos_series`: `cierre_tienda`, `fuera_del_error` y `clase_cero` (nuevas).",
            "los ceros de las series no decían si eran un cierre, un 25 de diciembre o una demanda baja.",
            "medir el error sin los días que se saben de antemano y describir los ceros (reglas, apartado 5, D8; reglas, apartado 6).",
            "reglas de transformación, apartado 1. Las tres se conocen después del día; clase_cero usa la media del "
            "periodo entero y nunca entra como variable del modelo.",
            "se marcan con la regla de `clasificar_ceros` de la corrección, sin importarla.\n\n   ```python\n   "
            + CODIGO_FICHA["marcas"].replace("\n", "\n   ") + "\n   ```",
            quien,
            f"cierre_tienda: {cl['construccion']} y {cl['validacion']} días de serie en construcción y validación; "
            f"fuera_del_error: {fe['construccion']} y {fe['validacion']}. clase_cero en la construcción: cierre "
            f"{cc['construccion']['cierre']}, 25 de diciembre {cc['construccion']['25_diciembre']}, demanda "
            f"intermitente {fmt(cc['construccion']['demanda_intermitente'])} y resto {cc['construccion']['resto']}; en "
            f"la validación: {cc['validacion']['cierre']}, {cc['validacion']['25_diciembre']}, "
            f"{cc['validacion']['demanda_intermitente']} y {cc['validacion']['resto']}.",
            "tres columnas más en `data/processed/hechos_series.parquet`; los datos de venta no cambian.",
            "quitar las tres columnas: `df = df.drop(columns=[\"cierre_tienda\", \"fuera_del_error\", \"clase_cero\"])`.",
        ]),
        ("precio_medio", "hechos_series: precio_medio_semana_anterior (cruces 6 y 7)", [
            "`hechos_series`: `precio_medio_semana_anterior` (nueva).",
            "el precio va por producto, tienda y semana; la serie va por departamento y día.",
            "el precio que entra en la previsión de un día es el de la semana anterior (reglas, apartado 5, D9; ficha, "
            "pregunta 4).",
            "media simple de los productos del departamento con precio en la tienda esa semana que ya lo tenían "
            "cuatro semanas antes, unida por `wm_yr_wk_anterior` del Calendario (el responsable del caso, 24/11/2026; reglas, apartado 5). Un "
            "producto entra la semana de su primera venta: contado desde entonces, avisaría de esa venta dentro del "
            "horizonte. Es un nivel: nunca se suma ni se redondea.",
            "se une el departamento a cada precio, se hace la media por tienda, departamento y semana y se une a cada "
            "día por su semana anterior.\n\n   ```python\n   "
            + CODIGO_FICHA["precio_medio"].replace("\n", "\n   ") + "\n   ```",
            quien,
            f"{fmt(c['precio_medio_grupos'])} grupos de tienda, departamento y semana con algún precio; "
            f"{c['precio_medio_grupos_sin_precio']} sin ninguno. En {fmt(c['precio_medio_grupos_sin_productos_que_cuentan'])} "
            f"no cuenta ningún producto; quedan fuera {fmt(c['precio_medio_precios_que_no_cuentan'])} precios de "
            f"productos con menos de cuatro semanas de precio. Quedan vacías {fmt(c['precio_medio_filas_vacias'])} "
            f"filas, las de las semanas {', '.join(str(w) for w in c['precio_medio_semanas_vacias'])}: sin anterior o "
            f"sin ningún producto que cuente.",
            "una columna más en `data/processed/hechos_series.parquet`.",
            "quitar la columna: `df = df.drop(columns=\"precio_medio_semana_anterior\")`.",
        ]),
        ("dim_producto", "dim_producto: una fila por producto", [
            "`data/processed/dim_producto.parquet` (nueva): `item_id`, `dept_id` y `cat_id`.",
            "el departamento y la categoría de cada producto venían repetidos en cada fila de la venta.",
            "dimensión de producto del diseño (§3); la usan los cruces 3 y 6.",
            "reglas de transformación, apartado 2.",
            "una fila por producto con su departamento y su categoría.\n\n   ```python\n   "
            + CODIGO_FICHA["dim_producto"] + "\n   ```",
            quien,
            f"{c['dim_producto_filas']} filas, {c['dim_producto_clave_filas_repetidas']} filas con la clave repetida. "
            "Por departamento: " + ", ".join(f"{k} {v}" for k, v in c["dim_producto_por_departamento"].items()) + ".",
            f"{c['dim_producto_filas']} filas y 3 columnas en `data/processed/dim_producto.parquet`.",
            "borrar `data/processed/dim_producto.parquet`.",
        ]),
        ("dim_tienda", "dim_tienda: una fila por tienda", [
            "`data/processed/dim_tienda.parquet` (nueva): `store_id` y `state_id`.",
            "el estado de cada tienda venía repetido en cada fila de la venta.",
            "dimensión de tienda del diseño (§3); la usa el cruce 4 y la suma de la pregunta 3.",
            "reglas de transformación, apartado 3.",
            "una fila por tienda con su estado.\n\n   ```python\n   " + CODIGO_FICHA["dim_tienda"] + "\n   ```",
            quien,
            f"{c['dim_tienda_filas']} filas, {c['dim_tienda_clave_filas_repetidas']} filas con la clave repetida. Por "
            "estado: " + ", ".join(f"{k} {v}" for k, v in c["dim_tienda_por_estado"].items()) + ".",
            f"{c['dim_tienda_filas']} filas y 2 columnas en `data/processed/dim_tienda.parquet`.",
            "borrar `data/processed/dim_tienda.parquet`.",
        ]),
    ]


def fichas_por_regla(texto):
    """La última ficha de cada regla del registro, leyendo ficha a ficha: el número y su línea «Regla:»."""
    ficha_de = {}
    for bloque in re.split(r"^(?=### R-\d{3} · )", texto, flags=re.M):
        numero = re.match(r"### (R-\d{3}) · ", bloque)
        regla = re.search(r"^Regla: `([a-z_]+)`", bloque, flags=re.M)
        if numero and regla:
            ficha_de[regla.group(1)] = numero.group(1)
    return ficha_de


def escribir_fichas(raiz, r):
    """Añade al registro una ficha por regla nueva o cambiada; si la regla y su código no cambian, no añade nada."""
    ruta = raiz / REGISTRO_REL
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else "# Registro de transformaciones\n"
    hechas = dict(re.findall(r"^Regla: `([a-z_]+)` · huella `([0-9a-f]{12})`", texto, flags=re.M))
    numeros = [int(n) for n in re.findall(r"^### R-(\d{3}) · ", texto, flags=re.M)]
    siguiente = max(numeros, default=0) + 1
    nombres = ["Tabla y columna", "Cómo estaba", "Problema o finalidad", "Decisión", "Qué se hizo",
               "Quién y con qué permiso", "Comprobación", "Cómo quedó", "Cómo deshacer"]
    fecha = datetime.now().strftime("%d/%m/%Y")
    nuevas, bloques = [], []
    for clave, titulo, campos in contenido_fichas(r):
        huella_actual = huella_regla(clave)
        if hechas.get(clave) == huella_actual:
            continue
        numero = f"R-{siguiente:03d}"
        siguiente += 1
        if clave in hechas:
            campos = list(campos)
            campos[3] = campos[3] + f" Cambia la regla `{clave}`, que tenía la huella `{hechas[clave]}`."
        lineas = [f"### {numero} · {fecha} · {titulo}", ""]
        for i, (nombre, valor) in enumerate(zip(nombres, campos), 1):
            lineas += [f"{i}. **{nombre}:** {valor}", ""]
        lineas += [f"Regla: `{clave}` · huella `{huella_actual}`", ""]
        bloques.append("\n".join(lineas))
        nuevas.append(numero)
    if bloques:
        cabecera = f"## Fichas de la transformación de datos (`{SCRIPT_REL}`)"
        if cabecera not in texto:
            texto = texto.rstrip("\n") + "\n\n" + cabecera + "\n"
        texto = texto.rstrip("\n") + "\n\n" + "\n".join(bloques)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
    return nuevas


# ══ 8. Informe para la persona ══════════════════════════════════════════════════
def generar_md(r):
    """El informe Markdown, generado del mismo diccionario que el JSON (resultado.md, regla 1)."""
    res = r["resultado"]
    c = r.get("cifras_de_control") or {}
    L = ["# Informe de transformación de datos", ""]
    L += ["## Fuente", ""]
    for e in r.get("entradas", []):
        L.append(f"- Entrada: `{e['ruta']}`, {fmt(e.get('filas'))} filas y {fmt(e.get('columnas'))} columnas; huella "
                 f"`{e['sha256']}`.")
    for s in r.get("salidas", []):
        L.append(f"- Salida: `{s['ruta']}`.")
    L.append(f"- Contexto: `{REGLAS_REL}`, el plan de cruces de `{MODELADO_REL}` y el estado de `{CORRECCION_REL}`.")
    L.append(f"- Ejecución: {r['fecha_ejecucion']}, con Python {r['entorno']['python']} y pandas "
             f"{r['entorno']['pandas']}. Fecha de los datos: {r['fecha_datos']}.")
    L += ["", "## Objetivo", ""]
    L.append(f"Estado **{res['estado']}**, riesgo {res['riesgo']}. {res['resumen']}")
    L.append("")
    L.append("La venta se prepara en una fila por departamento en una tienda y día, en unidades y en dólares, con el "
             "calendario, el SNAP de su estado, las marcas de cierre y de los ceros y el precio medio del departamento "
             "de la semana anterior. Es la base de la exploración y de las variables del paso 5.")
    for p in r.get("paradas", []):
        L.append(f"- Parada en {p['donde']} ({p['codigo']}): {p['motivo']}.")
    L += ["", "## Transformaciones aplicadas", ""]
    if not r.get("transformaciones"):
        L.append("Ninguna: el script paró antes de guardar.")
    for t in r.get("transformaciones", []):
        L.append(f"- {t['id']} · {t['transformacion']}: {t['resultado']} Columnas: {', '.join(t['columnas'])}. "
                 f"Ficha {t['ficha'] or 'sin ficha nueva en esta ejecución'}.")
    L += ["", "## Variables generadas", ""]
    if r.get("variables_generadas"):
        L += ["| Columna | Fórmula | Sale de | Unidad | Posterior al día | Sale del objetivo | Suma de otras |",
              "|---|---|---|---|---|---|---|"]
        for v in r["variables_generadas"]:
            L.append(f"| {v['columna']} | {v['formula']} | {', '.join(v['columnas_origen'])} | {v['unidad'] or '-'} | "
                     f"{'sí' if v['informacion_posterior'] else 'no'} | {'sí' if v['sale_del_objetivo'] else 'no'} | "
                     f"{'sí' if v['suma_de_otras'] else 'no'} |")
    else:
        L.append("Ninguna en esta ejecución.")
    L += ["", "## Transformaciones pendientes", ""]
    if r.get("pendientes"):
        for p in r["pendientes"]:
            L.append(f"- {p['id']} ({p['tabla']}, {p['columna']}): {p['pregunta']}")
    else:
        L.append("No hay ninguna: todas las transformaciones tienen su regla en las reglas de transformación.")
    L += ["", "## Cambios estructurales", ""]
    for g in r.get("cambios_granularidad", []):
        L.append(f"- De «{g['antes']}» a «{g['despues']}»: " + "; ".join(
            f"{s['magnitud']} {fmt(s['antes'])} antes y {fmt(s['despues'])} después"
            f" ({'coincide' if s['coincide'] else 'no coincide'})" for s in g["sumas_control"]) + ".")
    if r.get("cruces"):
        L += ["", "| Cruce | Partida | Se une | Filas antes | Filas después | Sin pareja en la partida | "
                  "Cardinalidad | Hecho |", "|---|---|---|---|---|---|---|---|"]
        for x in r["cruces"]:
            L.append(f"| {x['orden']} | {x['partida']} | {x['se_une']} | {fmt(x['filas_antes'])} | "
                     f"{fmt(x.get('filas_despues'))} | {fmt(x['huerfanas_partida']['filas'])} | "
                     f"{x['cardinalidad_observada']} | {'sí' if x['hecho'] else 'no'} |")
        L.append("")
        L.append("Las filas sin pareja del cruce 2 son días sin precio, que suman cero dólares. Las del cruce 7 son los "
                 "días de la semana sin anterior, con el precio medio vacío.")
    L += ["", "## Validación", ""]
    for v in r.get("validaciones", []):
        L.append(f"- {v['validacion']}: **{v['resultado']}**. {v['detalle']}")
    L += ["", "## Dataset generado", ""]
    if r.get("salidas"):
        for s in r["salidas"]:
            L.append(f"- `{s['ruta']}`: {fmt(s['filas'])} filas y {s['columnas']} columnas; una fila es "
                     f"{s['que_es_una_fila']}. Huella `{s['sha256']}`.")
    else:
        L.append("No se guardó ninguna tabla: el script paró antes de guardar.")
    L += ["", "## Registro de exclusiones", ""]
    if r.get("exclusiones"):
        L += ["| Clase | Qué sale | Columna | De qué cálculo | Recuento | Se puede recuperar |",
              "|---|---|---|---|---|---|"]
        for e in r["exclusiones"]:
            L.append(f"| {e['clase']} | {e['que_sale']} | {e['columna'] or '-'} | {e['de_que_calculo']} | "
                     f"{texto_recuento(e)} | {e['se_puede_recuperar']} |")
    else:
        L.append("Sin calcular: el script paró antes.")
    L += ["", "## Datos personales", ""]
    L.append(r.get("datos_personales_nota", ""))
    L += ["", "## Pendiente para el modelo", ""]
    pm = r.get("pendiente_modelo") or []
    if pm:
        L += ["| Columna | Tipo | Valores | Orden real | Unidad | Mínimo | Máximo |", "|---|---|---|---|---|---|---|"]
        for x in pm:
            L.append(f"| {x['columna']} | {x['tipo']} | {fmt(x['valores'])} | {'sí' if x['orden_real'] else 'no'} | "
                     f"{x['unidad'] or '-'} | {texto_valor(x['minimo'])} | {texto_valor(x['maximo'])} |")
        pa = r["particion"]
        L.append("")
        L.append(f"Partición por `{pa['columna_fecha']}` ({pa['fuente']}): desarrollo del {pa['desarrollo']['desde']} "
                 f"al {pa['desarrollo']['hasta']}; validación del {pa['validacion']['desde']} al "
                 f"{pa['validacion']['hasta']}. Los dos días de cada tramo entran en él. Filas fuera de los dos "
                 f"tramos: {fmt(pa.get('filas_sin_tramo'))}.")
    else:
        L.append("Sin calcular: el script paró antes.")
    L += ["", "## Teoría aplicada", ""]
    for t in r.get("teoria_aplicada", []):
        L.append(f"- Manual {t['apartado']}: {t['por_que']}.")
    L += ["", "Límites:", ""] + [f"- {x}" for x in r.get("limites", [])]
    return "\n".join(L) + "\n"


def texto_recuento(e):
    """El recuento de una clase del registro de exclusiones, en una frase."""
    rc = e["recuento"]
    if rc is None:
        return e.get("nota", "sin dato")
    if "construccion" in rc:
        return "; ".join(f"{'construcción' if p == 'construccion' else 'validación'}: {fmt(v['dias_serie'])} días de "
                         f"serie, {fmt(v['unidades'])} unidades y {fmt(v['dolares'], 2)} dólares"
                         for p, v in rc.items())
    if "productos_tienda" in rc:
        return f"{fmt(rc['productos_tienda'])} productos-tienda con {fmt(rc['unidades'])} unidades"
    return f"{fmt(rc['dias'])} días, del {rc['desde']} al {rc['hasta']}"


def texto_valor(v):
    """Un mínimo o un máximo para la tabla del informe."""
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    return fmt(v, 0 if float(v).is_integer() else 2)


# ══ 9. Ejecución ════════════════════════════════════════════════════════════════
def nueva_validacion(lista, nombre, condicion, detalle):
    """Apunta una validación con su resultado calculado de la condición."""
    lista.append({"validacion": nombre, "resultado": "pasa" if bool(condicion) else "falla", "detalle": detalle})


def principal(raiz):
    """Lee, comprueba, cruza, transforma, valida, guarda y escribe el JSON, el informe y las fichas."""
    inicio = time.time()
    partes = {}
    r = {"metodo": "transformacion-datos", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                     "ejecutable": sys.executable},
         "entradas": [], "resultado": {}, "pendientes": [], "salidas": [], "transformaciones": [],
         "variables_generadas": [], "cambios_granularidad": [], "cruces": [], "validaciones": [],
         "pendiente_modelo": [], "particion": None, "exclusiones": [], "paradas": [],
         "parametros": [{"nombre": "umbral de la demanda intermitente", "valor": UMBRAL_INTERMITENTE,
                         "unidad": "unidades de media al día", "fuente": "reglas-negocio §5, D8"}],
         "teoria_aplicada": TEORIA, "limites": LIMITES, "datos_personales": []}
    proteccion = raiz / PROTECCION_REL
    r["datos_personales_nota"] = (
        "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas "
        "de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada de personas. "
        "Esta transformación no usa ni deja ninguna columna de datos personales." if not proteccion.exists() else
        "Existe config/fuentes/proteccion-datos.json: hay que leerlo antes de usar estas tablas.")

    def terminar(estado, riesgo, resumen, siguiente):
        """Escribe el JSON y el informe, también cuando el script para (resultado.md, regla 5)."""
        r["resultado"] = {"estado": estado, "riesgo": riesgo, "resumen": resumen,
                          "artefactos": [JSON_REL, MD_REL] + [s["ruta"] for s in r["salidas"]],
                          "siguiente": siguiente}
        r["duracion_por_parte"] = partes
        r["duracion_segundos"] = round(time.time() - inicio, 2)
        (raiz / "informes").mkdir(parents=True, exist_ok=True)
        limpio = a_json_limpio(r)
        (raiz / JSON_REL).write_text(json.dumps(limpio, ensure_ascii=False, indent=2), encoding="utf-8")
        (raiz / MD_REL).write_text(generar_md(limpio), encoding="utf-8")
        return estado

    def parar(motivos):
        """Para el script sin guardar ninguna tabla."""
        r["paradas"] += motivos
        r["salidas"] = []
        return terminar("PARADO", "alto", "El script paró sin guardar ninguna tabla: "
                        + "; ".join(p["motivo"] for p in r["paradas"]) + ".",
                        "revisar la parada; la exploración no empieza")

    # ── 9.1 Al empezar: JSON anteriores, huellas y plan ──
    t0 = time.time()
    leidos, huellas_antes, paradas = al_empezar(raiz)
    partes["al_empezar"] = round(time.time() - t0, 2)
    if paradas:
        return parar(paradas)

    # ── 9.2 Lectura ──
    t0 = time.time()
    venta = pd.read_parquet(raiz / ENTRADAS["venta"])
    precios = pd.read_parquet(raiz / ENTRADAS["precios"])
    cal = pd.read_parquet(raiz / ENTRADAS["calendario"])
    for nombre, tabla in (("venta", venta), ("precios", precios), ("calendario", cal)):
        r["entradas"].append({"ruta": ENTRADAS[nombre], "sha256": huellas_antes[nombre], "filas": int(len(tabla)),
                              "columnas": int(tabla.shape[1])})
    dias = sorted([c for c in venta.columns if re.fullmatch(r"d_\d+", c)], key=lambda c: int(c[2:]))
    partes["lectura"] = round(time.time() - t0, 2)

    # ── 9.3 Reglas que paran antes de calcular: venta negativa y precios que no pasan a céntimos ──
    negativas = int((venta[dias].to_numpy() < 0).sum())
    if negativas:
        return parar([parada("venta_negativa", "lectura", f"{negativas} días de producto-tienda con venta negativa "
                                                          f"(reglas, apartado 5)")])
    centimos_precio = a_centimos(precios["sell_price"])
    if centimos_precio is None:
        return parar([parada("precio_decimales", "lectura",
                             "algún precio falta o tiene más de dos decimales: no pasa a céntimos enteros")])
    precios = precios.assign(centimos_precio=centimos_precio)

    # ── 9.4 Dimensiones: una fila por producto y por tienda ──
    t0 = time.time()
    dim_producto = construir_dim_producto(venta)
    dim_tienda = construir_dim_tienda(venta)
    partes["dimensiones"] = round(time.time() - t0, 2)

    # ── 9.5 La venta en filas y los cruces 1 a 3 ──
    t0 = time.time()
    larga = venta_en_filas(venta, dias)
    filas_venta_larga = int(len(larga))
    partes["venta_en_filas"] = round(time.time() - t0, 2)
    t0 = time.time()
    larga, info, p = cruzar(CRUCES[0], larga, cal[["d", "date", "wm_yr_wk"]])
    r["cruces"].append(info)
    if p:
        return parar([p])
    larga, info, p = cruzar(CRUCES[1], larga, precios[["item_id", "store_id", "wm_yr_wk", "sell_price"]])
    r["cruces"].append(info)
    if p:
        return parar([p])
    # Un día con venta y sin precio para antes de calcular los dólares (reglas, apartado 5)
    sin_precio = larga["sell_price"].isna()
    con_venta_sin_precio = int((sin_precio & (larga["unidades"] > 0)).sum())
    dias_sin_precio = int(sin_precio.sum())
    if con_venta_sin_precio:
        return parar([parada("venta_sin_precio", "cruce 2",
                             f"{con_venta_sin_precio} días con venta y sin precio (reglas, apartado 5)")])
    larga["centimos"] = centimos_del_dia(larga)
    pt = larga.groupby(["item_id", "store_id"], sort=False).agg(con_precio=("sell_price", "count"),
                                                                 unidades=("unidades", "sum"))
    pt_sin = pt[pt["con_precio"] == 0]
    pt_sin_precio = {"n": int(len(pt_sin)), "unidades": int(pt_sin["unidades"].sum())}
    larga, info, p = cruzar(CRUCES[2], larga, dim_producto)
    r["cruces"].append(info)
    if p:
        return parar([p])
    venta_unidades = int(larga["unidades"].sum())
    venta_centimos = int(larga["centimos"].sum())
    partes["cruces_1_a_3"] = round(time.time() - t0, 2)

    # ── 9.6 De producto a serie: suma por departamento, tienda y día ──
    t0 = time.time()
    df = agregar_a_series(larga)
    del larga
    r["cambios_granularidad"].append({
        "antes": "un producto en una tienda, con un día por columna", "despues": "un producto en una tienda y día",
        "sumas_control": [{"magnitud": "unidades", "antes": int(venta[dias].to_numpy().sum()),
                           "despues": venta_unidades,
                           "coincide": int(venta[dias].to_numpy().sum()) == venta_unidades}]})
    r["cambios_granularidad"].append({
        "antes": "un producto en una tienda y día", "despues": QUE_ES_UNA_FILA["hechos_series"],
        "sumas_control": [{"magnitud": "unidades", "antes": venta_unidades, "despues": int(df["unidades"].sum()),
                           "coincide": venta_unidades == int(df["unidades"].sum())},
                          {"magnitud": "dólares (en céntimos)", "antes": venta_centimos,
                           "despues": int(df["centimos"].sum()), "coincide": venta_centimos == int(df["centimos"].sum())}]})
    partes["agregacion"] = round(time.time() - t0, 2)

    # ── 9.7 Cruces 4 y 5: estado de la tienda y Calendario; SNAP del estado ──
    t0 = time.time()
    df, info, p = cruzar(CRUCES[3], df, dim_tienda)
    r["cruces"].append(info)
    if p:
        return parar([p])
    df, info, p = cruzar(CRUCES[4], df, cal)
    r["cruces"].append(info)
    if p:
        return parar([p])
    desconocidos = sorted(set(df["state_id"].dropna().unique()) - set(SNAP_DE_ESTADO))
    if desconocidos or df["state_id"].isna().any():
        return parar([parada("estado_desconocido", "SNAP del estado",
                             f"estados sin columna de SNAP: {desconocidos or ['vacío']} (solo CA, TX y WI)")])
    df = snap_del_estado(df)
    partes["cruces_4_y_5"] = round(time.time() - t0, 2)

    # ── 9.8 Marcas ──
    t0 = time.time()
    df = marcas(df)
    intermitentes = series_intermitentes(df)
    partes["marcas"] = round(time.time() - t0, 2)

    # ── 9.9 Cruces 6 y 7: precio medio del departamento de la semana anterior ──
    t0 = time.time()
    precios_dept, info, p = cruzar(CRUCES[5], precios, dim_producto[["item_id", "dept_id"]])
    r["cruces"].append(info)
    if p:
        return parar([p])
    orden_semanas = semanas_por_orden(cal)
    semanas_fuera = sorted(set(int(w) for w in precios_dept["wm_yr_wk"].unique()) - set(orden_semanas))
    if semanas_fuera:
        return parar([parada("semana_sin_orden", "precio medio",
                             f"semanas de precio que no están en el Calendario: {semanas_fuera[:5]}")])
    medio = precio_medio_semana(precios_dept, orden_semanas)
    r["cambios_granularidad"].append({
        "antes": "un producto en una tienda y semana, con su precio",
        "despues": "un departamento en una tienda y semana, con la media simple de sus precios con cuatro semanas de "
                   "precio",
        "sumas_control": [{"magnitud": "precios que entran en la media", "antes": int(len(precios_dept)),
                           "despues": int(medio["productos_con_precio"].sum()),
                           "coincide": int(len(precios_dept)) == int(medio["productos_con_precio"].sum())}]})
    df, info, p = cruzar(CRUCES[6], df, medio[["store_id", "dept_id", "wm_yr_wk", "precio_medio_semana_anterior"]])
    r["cruces"].append(info)
    if p:
        return parar([p])
    partes["cruces_6_y_7"] = round(time.time() - t0, 2)

    # ── 9.10 Columnas en su orden; los céntimos pasan a dólares ──
    t0 = time.time()
    df = df.sort_values(["store_id", "dept_id", "date"], kind="stable").reset_index(drop=True)
    df["dolares"] = np.round(df["centimos"].to_numpy() / 100, 2)
    centimos_series = df["centimos"].to_numpy(np.int64).copy()
    df = df.drop(columns="centimos")
    df = df[[c for c in COLUMNAS_SERIES if c in df.columns] + [c for c in df.columns if c not in COLUMNAS_SERIES]]

    # ── 9.11 Validaciones, todas calculadas con lo ejecutado ──
    v = r["validaciones"]
    columnas = list(df.columns)
    nueva_validacion(v, "columnas de la tabla de series", columnas == COLUMNAS_SERIES,
                     f"{len(columnas)} columnas; sobran {[c for c in columnas if c not in COLUMNAS_SERIES]}; faltan "
                     f"{[c for c in COLUMNAS_SERIES if c not in columnas]}.")
    if columnas != COLUMNAS_SERIES:
        r["paradas"].append(parada("columnas_series", "validación",
                                   "la tabla de series no tiene exactamente sus 26 columnas en su orden"))
    repetidas = int(df.duplicated(CLAVE_SERIES, keep=False).sum())
    nueva_validacion(v, "clave (store_id, dept_id, d) sin repetir", repetidas == 0, f"{repetidas} filas repetidas.")
    n_series = int(df[["store_id", "dept_id"]].drop_duplicates().shape[0])
    nueva_validacion(v, "filas igual a series por días", len(df) == n_series * len(dias),
                     f"{fmt(len(df))} filas; {n_series} series por {fmt(len(dias))} días.")
    nueva_validacion(v, "unidades iguales a las de la venta en filas", int(df["unidades"].sum()) == venta_unidades,
                     f"{fmt(int(df['unidades'].sum()))} y {fmt(venta_unidades)}.")
    centimos_de_dolares = np.rint(df["dolares"].to_numpy() * 100).astype(np.int64)
    nueva_validacion(v, "dólares iguales a los de la venta en filas", int(centimos_de_dolares.sum()) == venta_centimos,
                     f"{fmt(dolares(centimos_de_dolares.sum()), 2)} y {fmt(dolares(venta_centimos), 2)}.")
    distintos_centimos = int((centimos_de_dolares != centimos_series).sum())
    nueva_validacion(v, "los dólares guardados son los céntimos exactos",
                     distintos_centimos == 0 and int((df["dolares"] < 0).sum()) == 0,
                     f"{distintos_centimos} filas cuyo importe con dos decimales no vuelve a sus céntimos.")
    categorias = df.groupby(["store_id", "dept_id"])["cat_id"].nunique()
    nueva_validacion(v, "cada serie con una sola categoría", int((categorias > 1).sum()) == 0,
                     f"{int((categorias > 1).sum())} series con más de una.")
    sin_periodo = int((~df["periodo"].isin(PERIODOS)).sum())
    nueva_validacion(v, "todos los días de la tabla tienen periodo", sin_periodo == 0, f"{sin_periodo} filas sin él.")
    fechas = df["date"].drop_duplicates().sort_values()
    huecos = int((fechas.iloc[-1] - fechas.iloc[0]).days + 1 - len(fechas)) if len(fechas) else None
    nueva_validacion(v, "date es fecha, sin zona horaria y sin huecos",
                     pd.api.types.is_datetime64_any_dtype(df["date"]) and df["date"].dt.tz is None and huecos == 0,
                     f"tipo {df['date'].dtype}; {huecos} días que faltan entre el primero y el último.")
    por_orden = anterior_por_orden(cal)
    distintas = int(sum(1 for w, a in zip(cal["wm_yr_wk"], cal["wm_yr_wk_anterior"])
                        if (None if pd.isna(a) else int(a)) != por_orden.get(int(w))))
    nueva_validacion(v, "wm_yr_wk_anterior es la semana anterior por orden de fechas", distintas == 0,
                     f"{distintas} días del Calendario con otra semana anterior.")
    snap_mal = int(sum(((df["state_id"] == e) & (df["snap"] != cal.set_index("d").loc[df["d"], col].to_numpy())).sum()
                       for e, col in SNAP_DE_ESTADO.items()))
    nueva_validacion(v, "snap es el del estado de la tienda", snap_mal == 0, f"{snap_mal} filas con otro SNAP.")
    cero = df["unidades"] == 0
    sin_regla = int((df["clase_cero"] == "SIN_REGLA").sum())
    ceros_sin_clase = int((cero & df["clase_cero"].isna()).sum())
    venta_con_clase = int((~cero & df["clase_cero"].notna()).sum())
    nueva_validacion(v, "clase_cero en todos los ceros y solo en ellos",
                     sin_regla == 0 and ceros_sin_clase == 0 and venta_con_clase == 0,
                     f"{sin_regla} ceros sin regla; {ceros_sin_clase} ceros sin clase; {venta_con_clase} días con "
                     f"venta con clase.")
    # La media de cada serie, por otro cálculo: el conjunto de intermitentes tiene que ser el que usó la clase
    usadas = {p: sorted({f"{t} {dp}" for t, dp in df.loc[(df["clase_cero"] == "demanda_intermitente")
                                                          & (df["periodo"] == p), ["store_id", "dept_id"]]
                         .itertuples(index=False)}) for p in PERIODOS}
    rehechas = {p: [x["serie"] for x in intermitentes[p]["lista"]] for p in PERIODOS}
    nueva_validacion(v, "las series con ceros de demanda intermitente tienen media por debajo del umbral",
                     all(set(usadas[p]) <= set(rehechas[p]) for p in PERIODOS),
                     "media rehecha como suma entre días abiertos de cada serie en su periodo.")
    clases = {p: {k: int(((df["periodo"] == p) & (df["clase_cero"] == k)).sum()) for k in CLASES_CERO}
              for p in PERIODOS}
    ref = leidos["correccion"].get("clases_de_ceros") or {}
    ref_clases = {p: {k: (ref.get(p, {}).get("clases", {}).get(k) or {}).get("dias_serie") for k in CLASES_CERO}
                  for p in PERIODOS} if ref else None
    if ref_clases is not None:
        nueva_validacion(v, "clase_cero igual a clases_de_ceros de correccion-datos.json", clases == ref_clases,
                         f"aquí {clases}; en la corrección {ref_clases}.")
    navidad = (df["date"].dt.month == 12) & (df["date"].dt.day == 25)
    nueva_validacion(v, "fuera_del_error es el 25 de diciembre o el cierre",
                     bool((df["fuera_del_error"] == (navidad | df["cierre_tienda"])).all()),
                     f"{int(df['fuera_del_error'].sum())} filas marcadas.")
    vacio = df["precio_medio_semana_anterior"].isna()
    sin_anterior = df["wm_yr_wk_anterior"].isna()
    # Grupos de tienda, departamento y semana de la tabla con algún precio, comparando conjuntos de claves
    semanas_serie = pd.MultiIndex.from_frame(df[["store_id", "dept_id", "wm_yr_wk"]].drop_duplicates())
    con_precio_grupo = semanas_serie.isin(pd.MultiIndex.from_frame(medio[["store_id", "dept_id", "wm_yr_wk"]]))
    grupos_con_precio = int(con_precio_grupo.sum())
    grupos_sin_precio = int((~con_precio_grupo).sum())
    # Los días cuya semana anterior tiene precios y ninguno de un producto con cuatro semanas: vacíos por la regla
    sin_cuatro = medio.loc[medio["productos_que_cuentan"] == 0, ["store_id", "dept_id", "wm_yr_wk"]]
    claves_anterior = pd.MultiIndex.from_frame(
        df[["store_id", "dept_id", "wm_yr_wk_anterior"]].astype({"wm_yr_wk_anterior": "float64"}))
    sin_cuatro_dia = claves_anterior.isin(pd.MultiIndex.from_frame(sin_cuatro.astype({"wm_yr_wk": "float64"})))
    vacio_de_mas = int((vacio & ~sin_anterior & ~sin_cuatro_dia).sum())
    nueva_validacion(v, "el precio medio está vacío en los días sin semana anterior",
                     int((sin_anterior & ~vacio).sum()) == 0,
                     f"{int(vacio.sum())} filas vacías; {int(sin_anterior.sum())} sin semana anterior.")
    nueva_validacion(v, "el precio medio está vacío en los días cuya semana anterior no tiene ningún producto con "
                        "cuatro semanas de precio", int((sin_cuatro_dia & ~vacio).sum()) == 0,
                     f"{int(sin_cuatro_dia.sum())} filas con la semana anterior sin ningún producto que cuente.")
    if vacio_de_mas:
        r["pendientes"].append({
            "id": "P-01", "tabla": "hechos_series", "columna": "precio_medio_semana_anterior",
            "pregunta": f"{vacio_de_mas} filas quedan sin precio medio porque su departamento no tuvo ningún producto "
                        f"con precio la semana anterior: ¿qué valor llevan? Las reglas de transformación no lo fijan.",
            "opciones": ["dejarlo vacío", "otra regla que fije el responsable del caso"]})
    nueva_validacion(v, "dim_producto con la clave sin repetir", dim_producto["item_id"].is_unique,
                     f"{len(dim_producto)} filas.")
    nueva_validacion(v, "dim_tienda con la clave sin repetir", dim_tienda["store_id"].is_unique,
                     f"{len(dim_tienda)} filas.")
    for g in r["cambios_granularidad"]:
        nueva_validacion(v, f"sumas de control de «{g['antes']}» a «{g['despues']}»",
                         all(s["coincide"] for s in g["sumas_control"]), "antes y después.")
    if not dim_producto["item_id"].is_unique:
        r["paradas"].append(parada("dim_producto_clave", "validación", "un producto con más de un departamento"))
    if not dim_tienda["store_id"].is_unique:
        r["paradas"].append(parada("dim_tienda_clave", "validación", "una tienda con más de un estado"))
    falladas = [x["validacion"] for x in v if x["resultado"] == "falla"]
    if falladas and not any(p["codigo"] == "validaciones" for p in r["paradas"]):
        r["paradas"].append(parada("validaciones", "validación", "fallan: " + "; ".join(falladas)))
    partes["validacion"] = round(time.time() - t0, 2)

    # ── 9.12 Cifras de control, exclusiones, variables y partición ──
    df_c = df.assign(centimos=centimos_de_dolares)
    por = {p: df_c[df_c["periodo"] == p] for p in PERIODOS}
    fuera_25 = df["cierre_tienda"] & ~navidad
    cierres = (df.loc[fuera_25].groupby(["store_id", "d", "date"]).size().reset_index(name="n"))
    r["cifras_de_control"] = {
        "venta_filas": filas_venta_larga, "venta_unidades": venta_unidades, "venta_dolares": dolares(venta_centimos),
        "dias_con_venta_y_sin_precio": con_venta_sin_precio, "dias_sin_precio": dias_sin_precio,
        "series_filas": int(len(df)), "series_columnas": int(df.shape[1]), "series_clave_filas_repetidas": repetidas,
        "series_dias": len(dias),
        "filas_por_periodo": {p: int(len(x)) for p, x in por.items()},
        "unidades_por_periodo": {p: int(x["unidades"].sum()) for p, x in por.items()},
        "dolares_por_periodo": {p: dolares(x["centimos"].sum()) for p, x in por.items()},
        "series_con_mas_de_una_categoria": int((categorias > 1).sum()),
        "filas_snap": int((df["snap"] == 1).sum()),
        "cierre_tienda": {p: int(x["cierre_tienda"].sum()) for p, x in por.items()},
        "fuera_del_error": {p: int(x["fuera_del_error"].sum()) for p, x in por.items()},
        "fuera_del_error_25_diciembre": {p: int((navidad & (df["periodo"] == p)).sum()) for p in PERIODOS},
        "cierres_fuera_del_25": [{"tienda": str(x.store_id), "fecha": x.date.strftime("%Y-%m-%d"), "d": str(x.d),
                                  "dias_serie": int(x.n)} for x in cierres.itertuples()],
        "clase_cero": clases,
        "series_intermitentes": {p: {"series": intermitentes[p]["series"],
                                     "departamentos": intermitentes[p]["departamentos"]} for p in PERIODOS},
        "precio_medio_grupos": grupos_con_precio, "precio_medio_grupos_sin_precio": grupos_sin_precio,
        "precio_medio_grupos_sin_productos_que_cuentan": int((medio["productos_que_cuentan"] == 0).sum()),
        "precio_medio_precios_que_no_cuentan": int((medio["productos_con_precio"]
                                                    - medio["productos_que_cuentan"]).sum()),
        "precio_medio_filas_vacias": int(vacio.sum()),
        "precio_medio_semanas_vacias": sorted(int(w) for w in df.loc[vacio, "wm_yr_wk"].unique()),
        "dim_producto_filas": int(len(dim_producto)),
        "dim_producto_clave_filas_repetidas": int(dim_producto.duplicated("item_id", keep=False).sum()),
        "dim_producto_por_departamento": {str(k): int(n) for k, n in
                                          dim_producto.groupby("dept_id")["item_id"].nunique().items()},
        "dim_tienda_filas": int(len(dim_tienda)),
        "dim_tienda_clave_filas_repetidas": int(dim_tienda.duplicated("store_id", keep=False).sum()),
        "dim_tienda_por_estado": {str(k): int(n) for k, n in dim_tienda.groupby("state_id")["store_id"].nunique().items()},
    }
    r["series_intermitentes"] = intermitentes
    r["exclusiones"] = exclusiones(df_c, cal, pt_sin_precio, dias)
    calidad = raiz / CALIDAD_REL
    if calidad.exists():
        cruces_calidad = json.loads(calidad.read_text(encoding="utf-8")).get("cruces", [])
        vp = next((x for x in cruces_calidad if x.get("izquierda") == "venta" and x.get("derecha") == "precios"), None)
        if vp is not None:
            nueva_validacion(v, "productos-tienda sin precio igual al cruce venta-precios de calidad-datos.json",
                             vp.get("sin_pareja_izquierda") == pt_sin_precio["n"],
                             f"aquí {pt_sin_precio['n']}; en la calidad {vp.get('sin_pareja_izquierda')}.")
            if v[-1]["resultado"] == "falla":
                r["paradas"].append(parada("validaciones", "validación", "productos-tienda sin precio distintos de calidad"))
    r["variables_generadas"] = [
        {"columna": "unidades", "formula": "suma de las unidades de los productos del departamento en la tienda ese día",
         "columnas_origen": ["d_1 a d_n de la venta"], "unidad": "unidades", "informacion_posterior": True,
         "sale_del_objetivo": True, "suma_de_otras": False, "nota": "es el objetivo en unidades"},
        {"columna": "dolares", "formula": "suma de unidades × sell_price de su semana, producto a producto, en céntimos",
         "columnas_origen": ["unidades", "sell_price", "wm_yr_wk"], "unidad": "dólares",
         "informacion_posterior": True, "sale_del_objetivo": True, "suma_de_otras": False,
         "nota": "es el objetivo en dólares"},
        {"columna": "snap", "formula": "snap_ca, snap_tx o snap_wi según state_id",
         "columnas_origen": ["state_id", "snap_ca", "snap_tx", "snap_wi"], "unidad": None,
         "informacion_posterior": False, "sale_del_objetivo": False, "suma_de_otras": False},
        {"columna": "cierre_tienda", "formula": "todas las series de la tienda venden cero ese día",
         "columnas_origen": ["unidades", "store_id", "d"], "unidad": None, "informacion_posterior": True,
         "sale_del_objetivo": True, "suma_de_otras": False},
        {"columna": "fuera_del_error", "formula": "25 de diciembre o cierre_tienda",
         "columnas_origen": ["date", "cierre_tienda"], "unidad": None, "informacion_posterior": True,
         "sale_del_objetivo": True, "suma_de_otras": False,
         "nota": "sale de cierre_tienda, que sale de las unidades"},
        {"columna": "clase_cero", "formula": "en los ceros: cierre, 25_diciembre, demanda_intermitente (media del "
                                             "periodo sin cierres < 10) o resto",
         "columnas_origen": ["unidades", "cierre_tienda", "date", "periodo"], "unidad": None,
         "informacion_posterior": True, "sale_del_objetivo": True, "suma_de_otras": False,
         "nota": "usa la media del periodo entero: solo para describir"},
        {"columna": "precio_medio_semana_anterior",
         "formula": "media simple de sell_price de los productos del departamento con precio en la tienda la semana "
                    "wm_yr_wk_anterior que ya lo tenían cuatro semanas antes",
         "columnas_origen": ["sell_price", "dept_id", "wm_yr_wk_anterior"], "unidad": "dólares por unidad",
         "informacion_posterior": False, "sale_del_objetivo": False, "suma_de_otras": False},
    ]
    r["pendiente_modelo"] = pendiente_modelo(df)
    desde, hasta = PARTICION["desarrollo"]["desde"], PARTICION["validacion"]["hasta"]
    fuera_tramo = (df["date"] < pd.Timestamp(desde)) | (df["date"] > pd.Timestamp(hasta))
    tramo = np.where(df["date"] <= pd.Timestamp(PARTICION["desarrollo"]["hasta"]), "construccion", "validacion")
    r["particion"] = dict(PARTICION, filas_sin_tramo=int(fuera_tramo.sum()),
                          fechas_sin_tramo=sorted(df.loc[fuera_tramo, "date"].dt.strftime("%Y-%m-%d").unique().tolist()),
                          filas_con_periodo_distinto_del_tramo=int((~fuera_tramo & (df["periodo"] != tramo)).sum()))

    # ── 9.13 Sin validaciones falladas, se guardan las tablas (error 15); si no, se para sin guardar ──
    if r["paradas"]:
        return parar([])
    t0 = time.time()
    proc = raiz / "data" / "processed"
    tablas = {"hechos_series": df, "dim_producto": dim_producto, "dim_tienda": dim_tienda}
    for nombre, tabla in tablas.items():
        tabla.to_parquet(raiz / SALIDAS[nombre], index=False)
        r["salidas"].append({"tabla": nombre, "ruta": SALIDAS[nombre], "sha256": huella(raiz / SALIDAS[nombre]),
                             "filas": int(len(tabla)), "columnas": int(tabla.shape[1]),
                             "que_es_una_fila": QUE_ES_UNA_FILA[nombre]})
    r["huellas_despues"] = {rel: huella(raiz / rel) for rel in ENTRADAS.values()}
    cambiadas = [rel for nombre, rel in ENTRADAS.items() if r["huellas_despues"][rel] != huellas_antes[nombre]]
    nueva_validacion(v, "las tablas de entrada no cambian", cambiadas == [], f"cambiadas: {cambiadas}.")
    partes["escritura"] = round(time.time() - t0, 2)

    # ── 9.14 Transformaciones y fichas del registro ──
    nuevas = escribir_fichas(raiz, r)
    ficha_de = fichas_por_regla((raiz / REGISTRO_REL).read_text(encoding="utf-8"))
    r["fichas_nuevas"] = nuevas
    c = r["cifras_de_control"]
    r["transformaciones"] = [
        {"id": "T-01", "transformacion": "tabla de series con la venta en dólares, cruces 1 a 5",
         "columnas": ["store_id", "dept_id", "d", "cat_id", "state_id", "unidades", "dolares", "snap",
                      "columnas del Calendario"], "regla": "reglas-transformacion §1", "ficha": ficha_de.get("series_y_dolares"),
         "resultado": f"{fmt(c['series_filas'])} filas con {fmt(c['venta_unidades'])} unidades y "
                      f"{fmt(c['venta_dolares'], 2)} dólares, los de la venta en filas."},
        {"id": "T-02", "transformacion": "marcas de cierre, del error y de los ceros",
         "columnas": ["cierre_tienda", "fuera_del_error", "clase_cero"], "regla": "reglas-transformacion §1",
         "ficha": ficha_de.get("marcas"),
         "resultado": f"cierre_tienda en {c['cierre_tienda']['construccion']} y {c['cierre_tienda']['validacion']} "
                      f"días de serie de construcción y validación."},
        {"id": "T-03", "transformacion": "precio medio del departamento de la semana anterior, cruces 6 y 7",
         "columnas": ["precio_medio_semana_anterior"], "regla": "reglas-transformacion §1",
         "ficha": ficha_de.get("precio_medio"),
         "resultado": f"{fmt(c['precio_medio_grupos'])} grupos con precio; {fmt(c['precio_medio_filas_vacias'])} "
                      f"filas vacías, sin semana anterior o sin ningún producto con cuatro semanas de precio."},
        {"id": "T-04", "transformacion": "dimensión de producto", "columnas": COLUMNAS_DIM_PRODUCTO,
         "regla": "reglas-transformacion §2", "ficha": ficha_de.get("dim_producto"),
         "resultado": f"{c['dim_producto_filas']} productos con la clave sin repetir."},
        {"id": "T-05", "transformacion": "dimensión de tienda", "columnas": COLUMNAS_DIM_TIENDA,
         "regla": "reglas-transformacion §3", "ficha": ficha_de.get("dim_tienda"),
         "resultado": f"{c['dim_tienda_filas']} tiendas con la clave sin repetir."},
    ]
    if r["validaciones"][-1]["resultado"] == "falla":
        return terminar("ERROR", "alto", "Las tablas de entrada cambiaron durante la ejecución.", "revisar la ejecución")
    estado = "AVISO" if r["pendientes"] else "OK"
    resumen = (f"Tabla de series con {fmt(c['series_filas'])} filas de {n_series} series, {fmt(c['venta_unidades'])} "
               f"unidades y {fmt(c['venta_dolares'], 2)} dólares, los de la venta en filas; dim_producto con "
               f"{c['dim_producto_filas']} productos y dim_tienda con {c['dim_tienda_filas']} tiendas. Los 7 cruces "
               f"del plan sin filas de más y {len(r['validaciones'])} validaciones en verde.")
    return terminar(estado, "bajo" if estado == "OK" else "medio", resumen,
                    "la sesión principal rehace las cifras; después, el auditor del paso 3 y analisis-exploratorio")


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Transformación de datos del caso 69")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta con la estructura del caso")
    raiz_de_trabajo = Path(argumentos.parse_args().raiz).resolve()
    print("intérprete:", sys.executable)
    try:
        estado_final = principal(raiz_de_trabajo)
    except Exception as fallo:  # un fallo técnico deja el JSON en ERROR (resultado.md, regla 5) y sale con 1
        traceback.print_exc()
        error = {"metodo": "transformacion-datos", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                 "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
                 "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(fallo).__name__}: {fallo}",
                               "artefactos": [JSON_REL], "siguiente": "revisar el fallo"},
                 "pendientes": [], "salidas": [], "paradas": []}
        (raiz_de_trabajo / "informes").mkdir(parents=True, exist_ok=True)
        (raiz_de_trabajo / JSON_REL).write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding="utf-8")
        estado_final = "ERROR"
    print("estado:", estado_final)
    sys.exit(0 if estado_final in ("OK", "AVISO") else 1)
