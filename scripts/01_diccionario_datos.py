"""Diccionario de datos del origen del caso 69 (método diccionario-datos).

Lee las tres fuentes de data/raw/ sin alterarlas, perfila cada columna, revisa una a una las 1.575 columnas de días de
la venta y las describe como un bloque, compara los datos con la guía de participantes del concurso M5 y escribe:
  - config/fuentes/diccionario-datos-origen.json, para calidad-datos;
  - config/fuentes/diccionario-datos-origen.md, generado de ese JSON en la misma ejecución.

Se ejecuta sin intervención manual:
  PYTHONUTF8=1 <python del entorno 69_prevision_ventas_walmart> -W error scripts/01_diccionario_datos.py

No escribe en data/raw/, no corrige, no renombra ni cruza tablas.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import csv
import hashlib
import json
import math
import platform
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
SALIDA_JSON = RAIZ / "config" / "fuentes" / "diccionario-datos-origen.json"
SALIDA_MD = RAIZ / "config" / "fuentes" / "diccionario-datos-origen.md"
VERSION_METODO = "20/11/2026"  # versión del método diccionario-datos con que se escribió este script
GUIA = "config/fuentes/M5_guia_de_participantes_2020.docx"
PROTECCION = RAIZ / "config" / "fuentes" / "proteccion-datos.json"

# Fecha de referencia de los datos (reglas, apartado 5): último día que se mira antes de la prueba final.
FECHA_DATOS = "2015-05-22"

# Los dos periodos de trabajo (reglas, apartado 5). La prueba final está fuera de data/raw/.
PERIODOS = {
    "construccion": ("2011-01-29", "2014-05-22"),
    "validacion": ("2014-05-23", "2015-05-22"),
}

# Las tres fuentes, con el nombre que les da el caso.
FUENTES = {
    "venta": "sales_train_evaluation.csv",
    "precios": "sell_prices.csv",
    "calendario": "calendar.csv",
}

# Parámetros del método (parametros.md), con el valor de esta ejecución y de dónde sale.
CODIFICACIONES = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
MAX_LISTA = 15
RARA_PCT = 2.5
RARA_MIN = 5
RARA_TEXTO = f"menos del {str(RARA_PCT).replace('.', ',')} % de las filas o menos de {RARA_MIN} apariciones"
PARAMETROS = [
    {"nombre": "orden de codificaciones", "valor": ", ".join(CODIFICACIONES), "origen": "por defecto"},
    {"nombre": "filas donde buscar la cabecera de un Excel", "valor": None, "origen": "no aplica: no hay Excel"},
    {"nombre": "lista completa de valores de un texto", "valor": MAX_LISTA, "origen": "por defecto"},
    {"nombre": "categoría rara", "valor": RARA_TEXTO, "origen": "por defecto"},
    {"nombre": "apertura de bases de datos", "valor": None, "origen": "no aplica: no hay bases de datos"},
    {"nombre": "ficheros de un ZIP que no se abren", "valor": None, "origen": "no aplica: no hay ZIP"},
]

# Rango del precio de la tabla «Lo esperable» (reglas, apartado 7), solo para contarlo: no decide nada.
PRECIO_ESPERABLE = (0.5, 50.0)

# ── 1.1 Lo que dice la guía del concurso (diccionario de la organización, apartado «The dataset») ──
# Columnas documentadas por fichero. Los días de la venta se documentan como d_1 a d_1941.
GUIA_FICHEROS = {"venta": "sales_train.csv", "precios": "sell_prices.csv", "calendario": "calendar.csv"}
GUIA_COLUMNAS = {
    "venta": ["item_id", "dept_id", "cat_id", "store_id", "state_id"],
    "precios": ["store_id", "item_id", "wm_yr_wk", "sell_price"],
    "calendario": ["date", "wm_yr_wk", "weekday", "wday", "month", "year", "event_name_1", "event_type_1",
                   "event_name_2", "event_type_2", "snap_CA", "snap_TX", "snap_WI"],
}
GUIA_DIAS_VENTA = 1941
GUIA_PRODUCTOS = 3049
GUIA_RANGO_CALENDARIO = ("2011-01-29", "2016-06-19")
GUIA_JERARQUIA = {"cat_id": 3, "dept_id": 7, "store_id": 10, "state_id": 3}
DIAS_SEMANA = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# ── 1.2 Descripciones y procedencias, separadas del cálculo (diccionario-datos §4) ──
# Cada columna: rol, significado, procedencia, clase documental y, en las magnitudes, el cero y la fila que falta.
G = "declarado (guía del concurso, «The dataset»)"
DESCRIPCIONES = {
    "venta": {
        "id": dict(rol="identificador", procedencia="medido; el sufijo, sin_confirmar",
                   significado="identificador de la fila: el producto, la tienda y un sufijo fijo, unidos por guion "
                               "bajo. La guía no lo documenta; el significado del sufijo se deduce del nombre del "
                               "fichero y no se usa"),
        "item_id": dict(rol="clave", procedencia=G,
                        significado="código del producto. Junto con store_id apunta a los precios (relación supuesta: "
                                    "la guía no la declara)"),
        "dept_id": dict(rol="categorica", procedencia=G + "; reglas de negocio §4",
                        significado="departamento al que pertenece el producto"),
        "cat_id": dict(rol="categorica", procedencia=G + "; reglas de negocio §4",
                       significado="categoría a la que pertenece el producto: alimentación, ocio u hogar"),
        "store_id": dict(rol="clave", procedencia=G + "; reglas de negocio §4",
                         significado="código de la tienda donde se vende el producto. Junto con item_id apunta a "
                                     "los precios (relación supuesta)"),
        "state_id": dict(rol="categorica", procedencia=G + "; reglas de negocio §4",
                         significado="estado donde está la tienda"),
    },
    "bloque_dias": dict(
        rol="magnitud", procedencia=G + "; reglas de negocio §5",
        significado="unidades vendidas del producto en la tienda el día i, contado desde el 29/01/2011",
        significado_cero="un día con cero unidades es un dato válido, no un vacío; no distingue falta de demanda de "
                         "falta de producto (reglas de negocio §5)",
        significado_sin_fila="no falta ninguna fila: cada producto está en cada tienda (medido). Antes de su primera "
                             "venta un producto suma cero a su departamento (reglas de negocio §3)"),
    "precios": {
        "store_id": dict(rol="clave", procedencia=G, significado="código de la tienda"),
        "item_id": dict(rol="clave", procedencia=G, significado="código del producto"),
        "wm_yr_wk": dict(rol="codigo", procedencia=G + "; reglas de negocio §5",
                         significado="código de la semana de Walmart, de sábado a viernes. Apunta a la semana del "
                                     "calendario (relación supuesta)"),
        "sell_price": dict(rol="magnitud", procedencia=G + "; reglas de negocio §5 y §6",
                           significado="precio de venta del producto en la tienda esa semana, en dólares: la media de "
                                       "los siete días, que vale para los siete",
                           significado_cero="no hay ceros (medido); un precio cero hace sospechar (reglas de negocio "
                                            "§7, «Lo esperable»)",
                           significado_sin_fila="una semana sin fila es una semana en que el producto no se vendió en "
                                                "esa tienda (guía del concurso; reglas de negocio §5)"),
    },
    "calendario": {
        "date": dict(rol="fecha", procedencia=G, significado="fecha del día, en formato año-mes-día", tipo_declarado="fecha y-m-d"),
        "wm_yr_wk": dict(rol="codigo", procedencia=G, significado="código de la semana de Walmart a la que pertenece el día"),
        "weekday": dict(rol="categorica", procedencia=G, significado="nombre del día de la semana, en inglés"),
        "wday": dict(rol="codigo", procedencia=G, significado="número del día de la semana, empezando por el sábado"),
        "month": dict(rol="codigo", procedencia=G, significado="mes de la fecha"),
        "year": dict(rol="codigo", procedencia=G, significado="año de la fecha"),
        "d": dict(rol="clave", procedencia="medido; sin documentar en la guía",
                  significado="código del día, de d_1 en adelante, que coincide con el nombre de las columnas de días "
                              "de la venta (relación supuesta, medida)"),
        "event_name_1": dict(rol="categorica", procedencia=G + "; reglas de negocio §5",
                             significado="nombre del evento del día; vacío quiere decir «sin evento»"),
        "event_type_1": dict(rol="categorica", procedencia=G + "; reglas de negocio §5",
                             significado="tipo del evento del día; vacío quiere decir «sin evento»"),
        "event_name_2": dict(rol="categorica", procedencia=G + "; reglas de negocio §5",
                             significado="nombre del segundo evento del día; vacío quiere decir «sin segundo evento»"),
        "event_type_2": dict(rol="categorica", procedencia=G + "; reglas de negocio §5",
                             significado="tipo del segundo evento del día; vacío quiere decir «sin segundo evento»"),
        "snap_CA": dict(rol="booleana", procedencia=G, tipo_declarado="binaria 0 o 1",
                        significado="1 si las tiendas de California aceptan compras con SNAP ese día; 0 si no"),
        "snap_TX": dict(rol="booleana", procedencia=G, tipo_declarado="binaria 0 o 1",
                        significado="1 si las tiendas de Texas aceptan compras con SNAP ese día; 0 si no"),
        "snap_WI": dict(rol="booleana", procedencia=G, tipo_declarado="binaria 0 o 1",
                        significado="1 si las tiendas de Wisconsin aceptan compras con SNAP ese día; 0 si no"),
    },
}

# Lecturas posibles de las columnas que el cálculo lleve a decisión de negocio. Si una columna llega sin texto aquí,
# se usan las lecturas generales de su motivo.
LECTURAS = {
    "categoria_rara": ["cada categoría se lee por sí sola, aunque aparezca pocas veces",
                       "las categorías raras se leen juntas, o por la columna que las agrupa si existe"],
    "cero_sin_significado": ["el cero es un dato válido", "el cero es un vacío o un código"],
}
LECTURAS_COLUMNA = {
    ("calendario", "event_name_1"): ["cada evento se lee por su nombre, aunque aparezca una vez al año",
                                     "los eventos se leen por su tipo (event_type_1), juntando los nombres"],
    ("calendario", "event_type_1"): ["cada tipo de evento se lee por sí solo, aunque alguno tenga pocos días",
                                     "los tipos con pocos días se leen juntos, o todos los tipos como un solo «día con evento»"],
    ("calendario", "event_name_2"): ["cada segundo evento se lee por su nombre",
                                     "los segundos eventos se leen por su tipo (event_type_2), juntando los nombres"],
    ("calendario", "event_type_2"): ["cada tipo del segundo evento se lee por sí solo",
                                     "el segundo evento se lee junto con el primero, como un día con evento"],
}

# Lo que ninguna fuente disponible dice (diccionario-datos §5, «no se puede saber»), con su procedencia.
NO_SE_PUEDE_SABER = [
    {"que": "si el precio lleva impuestos de venta", "procedencia": "reglas de negocio §6"},
    {"que": "cuándo fija la tienda el precio dentro de la semana", "procedencia": "reglas de negocio §5"},
    {"que": "si un día con cero unidades tenía producto en el estante: no hay existencias", "procedencia": "reglas de negocio §5"},
    {"que": "qué quiere decir el sufijo fijo de id", "procedencia": "la guía no documenta la columna id"},
]


# ══ 2. Lectura de la fuente (diccionario-datos §2) ══════════════════════════════
def huella(ruta):
    """SHA-256 del fichero, para comprobar que data/raw/ no cambia."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def detectar_codificacion(ruta):
    """Prueba utf-8, utf-8-sig, cp1252 y latin-1 en ese orden; con BOM usa utf-8-sig. Devuelve (codificación, avisos)."""
    datos = Path(ruta).read_bytes()
    if datos.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", []
    for cod in CODIFICACIONES:
        try:
            datos.decode(cod)
        except UnicodeDecodeError:
            continue
        avisos = [] if cod == "utf-8" else [f"no se pudo leer como utf-8; se leyó como {cod}"]
        return cod, avisos
    raise ValueError(f"{ruta}: ninguna codificación de la lista lo lee")


def detectar_separador(ruta, codificacion):
    """Detecta el separador mirando la cabecera."""
    with open(ruta, encoding=codificacion, newline="") as f:
        cabecera = f.readline()
    return csv.Sniffer().sniff(cabecera, delimiters=",;\t|").delimiter


def leer_fuente(nombre):
    """Lee una fuente entera. Solo el campo vacío es nulo: un texto como «NA» se queda como texto para verlo."""
    ruta = RAW / FUENTES[nombre]
    cod, avisos = detectar_codificacion(ruta)
    sep = detectar_separador(ruta, cod)
    df = pd.read_csv(ruta, sep=sep, encoding=cod, keep_default_na=False, na_values=[""], decimal=".")
    texto_numerico = [c for c in df.columns if pd.api.types.is_string_dtype(df[c])
                      and df[c].dropna().astype(str).str.fullmatch(r"-?\d+([.,]\d+)?").all() and df[c].notna().any()]
    for c in texto_numerico:
        avisos.append(f"la columna {c} es numérica y se leyó como texto")
    lectura = {"codificacion": cod, "separador": sep, "decimal": ".", "hoja": None, "fila_cabecera": 0,
               "solo_vacio_es_nulo": True, "avisos": avisos}
    return df, lectura


# ══ 3. Perfil por columna (diccionario-datos §3) ════════════════════════════════
def a_json_limpio(obj):
    """Convierte tipos de numpy a Python y NaN o infinito a None, para un JSON válido."""
    if isinstance(obj, dict):
        return {str(k): a_json_limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json_limpio(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        valor = float(obj)
        return None if (math.isnan(valor) or math.isinf(valor)) else valor
    if isinstance(obj, pd.Timestamp):
        return obj.date().isoformat()
    return obj


def categorias_raras(serie, pct_limite, min_apariciones):
    """Categorías con menos del pct_limite % de las filas o menos de min_apariciones apariciones."""
    filas = len(serie)
    cuenta = serie.dropna().value_counts()
    raras = []
    for categoria, n in cuenta.items():
        pct = 100 * n / filas
        if pct < pct_limite or n < min_apariciones:
            raras.append({"categoria": categoria, "filas": int(n), "pct": round(pct, 2)})
    return raras


def clase_del_campo(campo):
    """Clase de la columna: la manda lo peor entre la clase documental y lo que miden los datos (diccionario-datos §5)."""
    orden = ["resuelto", "decision_de_negocio", "no_se_puede_saber"]
    candidatas = [campo.get("clase_documental") or "resuelto"]
    if campo["filas"] > 0 and campo["nulos"] == campo["filas"]:
        candidatas.append("no_se_puede_saber")
    if campo["rol"] == "categorica" and campo["categorias_raras"]:
        candidatas.append("decision_de_negocio")
    if campo["rol"] == "magnitud" and not campo.get("significado_cero"):
        candidatas.append("decision_de_negocio")
    return max(candidatas, key=orden.index)


def perfil_columna(df, columna, descripcion):
    """Ficha de una columna: tipo, rol, nulos, vacíos, espacios, distintos, rango o lista, clase y procedencia."""
    s = df[columna]
    filas = len(s)
    rol = descripcion["rol"]
    es_texto = pd.api.types.is_string_dtype(s)
    texto = s.dropna().astype(str) if es_texto else pd.Series([], dtype=str)
    campo = {
        "columna": columna,
        "tipo_leido": str(s.dtype),
        "tipo_declarado": descripcion.get("tipo_declarado"),
        "rol": rol,
        "nulos": int(s.isna().sum()),
        "nulos_pct": round(100 * s.isna().mean(), 2),
        "vacios": int((texto.str.strip() == "").sum()),
        "espacios": int((texto != texto.str.strip()).sum()),
        "distintos": int(s.nunique(dropna=True)),
        "minimo": None,
        "maximo": None,
        "valores": None,
    }
    if rol in ("magnitud", "fecha", "codigo") and not es_texto:
        campo["minimo"], campo["maximo"] = s.min(), s.max()
    elif rol == "fecha":
        campo["minimo"], campo["maximo"] = s.min(), s.max()
    if es_texto and campo["distintos"] <= MAX_LISTA:
        cuenta = s.value_counts(dropna=True)
        campo["valores"] = [{"valor": v, "frecuencia": int(n)} for v, n in cuenta.items()]
    campo["categorias_raras"] = categorias_raras(s, RARA_PCT, RARA_MIN) if rol == "categorica" else []
    campo["filas"] = filas
    campo["clase_documental"] = descripcion.get("clase_documental", "resuelto")
    campo["significado_cero"] = descripcion.get("significado_cero")
    campo["significado_sin_fila"] = descripcion.get("significado_sin_fila")
    campo["clase"] = clase_del_campo(campo)
    campo["significado"] = descripcion["significado"]
    campo["procedencia"] = descripcion["procedencia"]
    campo["proteccion"] = None
    return campo


def revisar_bloque_dias(df, columnas):
    """Revisa una a una las columnas de días (tipo entero, vacíos, negativos, constante) y resume el bloque.

    La columna que no cumple lo mismo que las demás sale en fuera_del_bloque con sus motivos.
    """
    fuera, minimos, maximos, revisadas = [], [], [], 0
    for c in columnas:
        s = df[c]
        revisadas += 1
        motivos = []
        nulos = int(s.isna().sum())
        if not pd.api.types.is_integer_dtype(s):
            motivos.append(f"no es entero: tipo {s.dtype}")
        if nulos:
            motivos.append(f"{nulos} vacíos")
        negativos = int((s < 0).sum())
        if negativos:
            motivos.append(f"{negativos} negativos")
        if s.nunique(dropna=True) <= 1:
            motivos.append("constante en todas las filas")
        minimos.append(s.min())
        maximos.append(s.max())
        if motivos:
            fuera.append({"columna": c, "motivos": motivos, "minimo": s.min(), "maximo": s.max(), "nulos": nulos})
    numeros = [int(m.group(1)) for c in columnas if (m := re.fullmatch(r"d_(\d+)", c))]
    seguidos = len(numeros) == len(columnas) and numeros == list(range(1, len(columnas) + 1))
    sub = df[columnas]
    return {
        "columnas": len(columnas),
        "columnas_revisadas": revisadas,
        "primera": columnas[0] if columnas else None,
        "ultima": columnas[-1] if columnas else None,
        "nombres_seguidos": seguidos,
        "tipos": {str(k): int(v) for k, v in sub.dtypes.astype(str).value_counts().items()},
        "nulos": int(sub.isna().sum().sum()),
        "negativos": int((sub < 0).sum().sum()),
        "minimo": min(minimos) if minimos else None,
        "maximo": max(maximos) if maximos else None,
        "columnas_con_minimo_cero": int(sum(1 for m in minimos if m == 0)),
        "maximo_mas_bajo_de_una_columna": min(maximos) if maximos else None,
        "fuera_del_bloque": fuera,
    }


# ══ 4. Comparación con la guía del concurso (diccionario-datos §1) ═════════════
def comparar_columnas_con_guia(tabla, columnas_fuente, documentadas):
    """Columnas documentadas que no llegan y columnas que llegan sin documentar."""
    salida = []
    for c in documentadas:
        if c not in columnas_fuente:
            salida.append({"tabla": tabla, "columna": c, "que_dice_el_documento": f"documenta la columna {c}",
                           "que_dicen_los_datos": "la columna no está en el fichero"})
    for c in columnas_fuente:
        if c not in documentadas:
            salida.append({"tabla": tabla, "columna": c, "que_dice_el_documento": "no la documenta",
                           "que_dicen_los_datos": f"la columna {c} está en el fichero"})
    return salida


def comprobacion(tabla, columna, documento, datos, contradice):
    """Una afirmación de la guía puesta frente a lo medido; contradice sale del cálculo."""
    return {"tabla": tabla, "columna": columna, "que_dice_el_documento": documento, "que_dicen_los_datos": datos,
            "contradice": bool(contradice)}


# ══ 5. Cálculo por tabla ═════════════════════════════════════════════════════════
def pct(a, b):
    """Porcentaje con dos decimales; None si el denominador es cero."""
    return round(100 * a / b, 2) if b else None


def describir_venta(venta, calendario):
    """Ficha de la venta: identidad, bloque de días, relaciones medidas y cifras por periodo."""
    identidad = list(DESCRIPCIONES["venta"].keys())
    dias = [c for c in venta.columns if c not in identidad]
    campos = [perfil_columna(venta, c, DESCRIPCIONES["venta"][c]) for c in identidad if c in venta.columns]
    bloque = revisar_bloque_dias(venta, dias)

    # Relaciones dentro de la tabla que dan el significado de las columnas de identidad (medido).
    prefijo = venta["item_id"] + "_" + venta["store_id"] + "_"
    empieza = pd.Series([i.startswith(p) for i, p in zip(venta["id"], prefijo)])
    sufijos = sorted({i[len(p):] for i, p in zip(venta["id"], prefijo) if i.startswith(p)})
    relaciones = {
        "filas_donde_id_es_producto_tienda_y_sufijo": int(empieza.sum()),
        "sufijos_distintos_de_id": len(sufijos),
        "sufijo_de_id": sufijos[0] if len(sufijos) == 1 else None,
        "productos_cuyo_codigo_no_empieza_por_su_departamento": int((venta["item_id"].str.rsplit("_", n=1).str[0] != venta["dept_id"]).sum()),
        "departamentos_cuyo_codigo_no_empieza_por_su_categoria": int((venta["dept_id"].str.rsplit("_", n=1).str[0] != venta["cat_id"]).sum()),
        "tiendas_cuyo_codigo_no_empieza_por_su_estado": int((venta["store_id"].str.split("_").str[0] != venta["state_id"]).sum()),
        "productos_con_mas_de_un_departamento": int((venta.groupby("item_id")["dept_id"].nunique() > 1).sum()),
        "departamentos_con_mas_de_una_categoria": int((venta.groupby("dept_id")["cat_id"].nunique() > 1).sum()),
        "tiendas_con_mas_de_un_estado": int((venta.groupby("store_id")["state_id"].nunique() > 1).sum()),
        "productos_que_no_estan_en_todas_las_tiendas": int((venta.groupby("item_id")["store_id"].nunique() != venta["store_id"].nunique()).sum()),
        "pares_producto_tienda_repetidos": int(venta.duplicated(["item_id", "store_id"]).sum()),
        "productos_distintos": int(venta["item_id"].nunique()),
        "filas_por_departamento": {k: int(v) for k, v in venta["dept_id"].value_counts().sort_index().items()},
        "productos_por_departamento": {k: int(v) for k, v in venta.groupby("dept_id")["item_id"].nunique().sort_index().items()},
        "filas_por_tienda": {k: int(v) for k, v in venta["store_id"].value_counts().sort_index().items()},
    }

    # Cifras de cada periodo: el día i de la venta es la fila d_i del calendario.
    fecha_de = dict(zip(calendario["d"], pd.to_datetime(calendario["date"], format="%Y-%m-%d")))
    por_periodo = {}
    for nombre, (ini, fin) in PERIODOS.items():
        cols = [c for c in dias if c in fecha_de and pd.Timestamp(ini) <= fecha_de[c] <= pd.Timestamp(fin)]
        sub = venta[cols].to_numpy()
        por_periodo[nombre] = {
            "desde": ini, "hasta": fin, "primera_columna": cols[0] if cols else None,
            "ultima_columna": cols[-1] if cols else None, "dias": len(cols), "celdas": int(sub.size),
            "celdas_a_cero": int((sub == 0).sum()), "celdas_a_cero_pct": pct(int((sub == 0).sum()), sub.size),
            "unidades": int(sub.sum()), "maximo_de_una_celda": int(sub.max()) if sub.size else None,
            "productos_tienda_sin_ninguna_venta": int((sub.sum(axis=1) == 0).sum()),
        }
    cubiertos = sum(p["dias"] for p in por_periodo.values())

    tabla = {
        "tabla": "venta", "fichero": f"data/raw/{FUENTES['venta']}",
        "que_es_una_fila": "un producto en una tienda, con una columna por día",
        "filas": len(venta), "columnas": venta.shape[1],
        "clave": ["id"], "clave_unica": bool(venta["id"].is_unique),
        "clave_alternativa": ["item_id", "store_id"],
        "clave_alternativa_unica": bool(not venta.duplicated(["item_id", "store_id"]).any()),
        "claves_hacia_otras_tablas": [
            {"columnas": ["item_id", "store_id"], "tabla": "precios", "supuesta": True},
            {"columnas": ["nombre de cada columna de días"], "tabla": "calendario (columna d)", "supuesta": True},
        ],
        "campos": campos,
        "bloque_dias": {**DESCRIPCIONES["bloque_dias"], **bloque,
                        "clase": clase_del_campo({"rol": "magnitud", "nulos": bloque["nulos"],
                                                  "filas": len(venta) * len(dias), "categorias_raras": [],
                                                  "significado_cero": DESCRIPCIONES["bloque_dias"]["significado_cero"],
                                                  "clase_documental": "resuelto"}),
                        "dias_en_los_dos_periodos": cubiertos},
        "relaciones_medidas": relaciones,
        "por_periodo": por_periodo,
    }
    return tabla


def describir_precios(precios, calendario):
    """Ficha de los precios, con sus cifras por periodo, separadas por la última semana de la construcción."""
    campos = [perfil_columna(precios, c, DESCRIPCIONES["precios"][c]) for c in precios.columns if c in DESCRIPCIONES["precios"]]
    fechas = pd.to_datetime(calendario["date"], format="%Y-%m-%d")
    ultima_semana_construccion = int(calendario.loc[fechas == pd.Timestamp(PERIODOS["construccion"][1]), "wm_yr_wk"].iloc[0])
    primera_semana_validacion = int(calendario.loc[fechas == pd.Timestamp(PERIODOS["validacion"][0]), "wm_yr_wk"].iloc[0])
    precio = precios["sell_price"]
    centimos = (precio * 100 - (precio * 100).round()).abs() > 1e-6
    hasta = precios["wm_yr_wk"] <= ultima_semana_construccion
    por_periodo = {}
    for nombre, mascara in [("hasta_la_ultima_semana_de_construccion", hasta), ("despues", ~hasta)]:
        sub = precios[mascara]
        por_periodo[nombre] = {
            "filas": int(mascara.sum()),
            "semana_minima": int(sub["wm_yr_wk"].min()) if len(sub) else None,
            "semana_maxima": int(sub["wm_yr_wk"].max()) if len(sub) else None,
            "productos_tienda_con_precio": int(sub[["item_id", "store_id"]].drop_duplicates().shape[0]),
            "precio_minimo": float(sub["sell_price"].min()) if len(sub) else None,
            "precio_maximo": float(sub["sell_price"].max()) if len(sub) else None,
        }
    tabla = {
        "tabla": "precios", "fichero": f"data/raw/{FUENTES['precios']}",
        "que_es_una_fila": "un producto en una tienda en una semana de Walmart, con su precio",
        "filas": len(precios), "columnas": precios.shape[1],
        "clave": ["store_id", "item_id", "wm_yr_wk"],
        "clave_unica": bool(not precios.duplicated(["store_id", "item_id", "wm_yr_wk"]).any()),
        "claves_hacia_otras_tablas": [
            {"columnas": ["item_id", "store_id"], "tabla": "venta", "supuesta": True},
            {"columnas": ["wm_yr_wk"], "tabla": "calendario", "supuesta": True},
        ],
        "campos": campos,
        "relaciones_medidas": {
            "productos_distintos": int(precios["item_id"].nunique()),
            "tiendas_distintas": int(precios["store_id"].nunique()),
            "semanas_distintas": int(precios["wm_yr_wk"].nunique()),
            "productos_tienda_con_algun_precio": int(precios[["item_id", "store_id"]].drop_duplicates().shape[0]),
            "precios_con_mas_de_dos_decimales": int(centimos.sum()),
            "precios_por_debajo_del_rango_esperable": int((precio < PRECIO_ESPERABLE[0]).sum()),
            "precios_por_encima_del_rango_esperable": int((precio > PRECIO_ESPERABLE[1]).sum()),
            "rango_esperable": list(PRECIO_ESPERABLE),
            "precios_cero_o_negativos": int((precio <= 0).sum()),
        },
        "ultima_semana_de_construccion": ultima_semana_construccion,
        "primera_semana_de_validacion": primera_semana_validacion,
        "por_periodo": por_periodo,
    }
    return tabla


def describir_calendario(calendario):
    """Ficha del calendario, con sus relaciones internas y sus cifras por periodo."""
    campos = [perfil_columna(calendario, c, DESCRIPCIONES["calendario"][c]) for c in calendario.columns if c in DESCRIPCIONES["calendario"]]
    fechas = pd.to_datetime(calendario["date"], format="%Y-%m-%d", errors="coerce")
    esperado_wday = calendario["weekday"].map({d: i + 1 for i, d in enumerate(DIAS_SEMANA)})
    numeros_d = calendario["d"].str.extract(r"^d_(\d+)$")[0].astype(float)
    dias_por_semana = calendario.groupby("wm_yr_wk").size()
    primer_dia_semana = calendario.groupby("wm_yr_wk")["weekday"].first()
    eventos = {}
    for k in ("1", "2"):
        n, t = calendario[f"event_name_{k}"], calendario[f"event_type_{k}"]
        eventos[k] = int((n.isna() != t.isna()).sum())
    relaciones = {
        "fechas_que_no_se_leen_como_ano_mes_dia": int(fechas.isna().sum()),
        "dias_seguidos_sin_hueco": bool((fechas.diff().dropna() == pd.Timedelta(days=1)).all()),
        "d_numerado_de_1_en_adelante_sin_hueco": bool((numeros_d == np.arange(1, len(calendario) + 1)).all()),
        "fecha_de_d1": fechas[calendario["d"] == "d_1"].iloc[0] if (calendario["d"] == "d_1").any() else None,
        "filas_con_wday_distinto_del_que_toca_a_weekday": int((esperado_wday != calendario["wday"]).sum()),
        "filas_con_month_distinto_del_mes_de_date": int((fechas.dt.month != calendario["month"]).sum()),
        "filas_con_year_distinto_del_ano_de_date": int((fechas.dt.year != calendario["year"]).sum()),
        "semanas": int(len(dias_por_semana)),
        "semanas_con_siete_dias": int((dias_por_semana == 7).sum()),
        "semanas_incompletas": {str(k): int(v) for k, v in dias_por_semana[dias_por_semana != 7].items()},
        "semanas_que_no_empiezan_en_sabado": int((primer_dia_semana.iloc[1:] != "Saturday").sum()),
        "filas_con_nombre_y_tipo_del_evento_1_descuadrados": eventos["1"],
        "filas_con_nombre_y_tipo_del_evento_2_descuadrados": eventos["2"],
        "dias_con_segundo_evento_sin_primero": int((calendario["event_name_2"].notna() & calendario["event_name_1"].isna()).sum()),
    }
    por_periodo = {}
    tramos = dict(PERIODOS)
    tramos["despues_de_la_fecha_de_referencia"] = (
        (pd.Timestamp(FECHA_DATOS) + pd.Timedelta(days=1)).date().isoformat(), fechas.max().date().isoformat())
    for nombre, (ini, fin) in tramos.items():
        m = (fechas >= pd.Timestamp(ini)) & (fechas <= pd.Timestamp(fin))
        sub = calendario[m]
        por_periodo[nombre] = {
            "desde": ini, "hasta": fin, "filas": int(m.sum()),
            "dias_con_evento": int(sub["event_name_1"].notna().sum()),
            "dias_con_dos_eventos": int(sub["event_name_2"].notna().sum()),
            "dias_snap": {s: int(sub[s].sum()) for s in ("snap_CA", "snap_TX", "snap_WI")},
            "semana_minima": int(sub["wm_yr_wk"].min()) if len(sub) else None,
            "semana_maxima": int(sub["wm_yr_wk"].max()) if len(sub) else None,
        }
    tabla = {
        "tabla": "calendario", "fichero": f"data/raw/{FUENTES['calendario']}",
        "que_es_una_fila": "un día",
        "filas": len(calendario), "columnas": calendario.shape[1],
        "clave": ["d"], "clave_unica": bool(calendario["d"].is_unique),
        "clave_alternativa": ["date"], "clave_alternativa_unica": bool(calendario["date"].is_unique),
        "claves_hacia_otras_tablas": [
            {"columnas": ["d"], "tabla": "venta (nombre de cada columna de días)", "supuesta": True},
            {"columnas": ["wm_yr_wk"], "tabla": "precios", "supuesta": True},
        ],
        "campos": campos,
        "relaciones_medidas": relaciones,
        "por_periodo": por_periodo,
    }
    return tabla


def comprobar_guia(venta, precios, calendario, t_venta, t_cal):
    """Pone cada afirmación de la guía frente a lo medido. Devuelve todas las comprobaciones y las diferencias por recorte."""
    comps = []
    ident = list(DESCRIPCIONES["venta"].keys())
    for c in comparar_columnas_con_guia("venta", ident, GUIA_COLUMNAS["venta"]):
        comps.append({**c, "contradice": True})
    for c in comparar_columnas_con_guia("precios", list(precios.columns), GUIA_COLUMNAS["precios"]):
        comps.append({**c, "contradice": True})
    for c in comparar_columnas_con_guia("calendario", list(calendario.columns), GUIA_COLUMNAS["calendario"]):
        comps.append({**c, "contradice": True})
    for tabla, fichero in GUIA_FICHEROS.items():
        comps.append(comprobacion(tabla, None, f"el fichero se llama {fichero}",
                                  f"el fichero se llama {FUENTES[tabla]}", fichero != FUENTES[tabla]))
    b = t_venta["bloque_dias"]
    comps.append(comprobacion("venta", "d_1 … d_n", "las unidades vendidas el día i: un número entero de unidades",
                              f"{b['columnas']} columnas; " + "; ".join(f"{k} en {v}" for k, v in b["tipos"].items())
                              + f"; {b['nulos']} vacíos; {b['negativos']} negativos",
                              bool(b["nulos"] or b["negativos"] or set(b["tipos"]) - {"int64"})))
    r = t_cal["relaciones_medidas"]
    comps.append(comprobacion("calendario", "d", "el día d_1 es el 2011-01-29",
                              f"d_1 es el {a_json_limpio(r['fecha_de_d1'])}",
                              a_json_limpio(r["fecha_de_d1"]) != "2011-01-29"))
    fechas = pd.to_datetime(calendario["date"], format="%Y-%m-%d")
    rango = (fechas.min().date().isoformat(), fechas.max().date().isoformat())
    comps.append(comprobacion("calendario", "date", f"los datos van del {GUIA_RANGO_CALENDARIO[0]} al {GUIA_RANGO_CALENDARIO[1]}",
                              f"el calendario va del {rango[0]} al {rango[1]}", rango != GUIA_RANGO_CALENDARIO))
    comps.append(comprobacion("calendario", "date", "formato año-mes-día",
                              f"{r['fechas_que_no_se_leen_como_ano_mes_dia']} fechas no se leen con ese formato",
                              r["fechas_que_no_se_leen_como_ano_mes_dia"] > 0))
    fuera_semana = sorted(set(calendario["weekday"].dropna()) - set(DIAS_SEMANA))
    comps.append(comprobacion("calendario", "weekday", "el día de la semana, de sábado a viernes",
                              f"valores fuera de los siete días: {', '.join(fuera_semana) or 'ninguno'}", bool(fuera_semana)))
    comps.append(comprobacion("calendario", "wday", "número del día de la semana, empezando por el sábado",
                              f"{r['filas_con_wday_distinto_del_que_toca_a_weekday']} filas no casan con weekday",
                              r["filas_con_wday_distinto_del_que_toca_a_weekday"] > 0))
    comps.append(comprobacion("calendario", "month", "el mes de la fecha",
                              f"{r['filas_con_month_distinto_del_mes_de_date']} filas no casan con date",
                              r["filas_con_month_distinto_del_mes_de_date"] > 0))
    comps.append(comprobacion("calendario", "year", "el año de la fecha",
                              f"{r['filas_con_year_distinto_del_ano_de_date']} filas no casan con date",
                              r["filas_con_year_distinto_del_ano_de_date"] > 0))
    for k in ("1", "2"):
        n = r[f"filas_con_nombre_y_tipo_del_evento_{k}_descuadrados"]
        comps.append(comprobacion("calendario", f"event_name_{k} y event_type_{k}",
                                  "si el día tiene evento, su nombre y su tipo",
                                  f"{n} filas con nombre sin tipo o tipo sin nombre", n > 0))
    for s in ("snap_CA", "snap_TX", "snap_WI"):
        valores = sorted(int(v) for v in calendario[s].dropna().unique())
        comps.append(comprobacion("calendario", s, "binaria, 0 o 1",
                                  f"valores {', '.join(map(str, valores))}; {int(calendario[s].isna().sum())} vacíos",
                                  bool(set(valores) - {0, 1}) or calendario[s].isna().any()))
    rel = t_venta["relaciones_medidas"]
    comps.append(comprobacion("venta", "state_id", "el estado donde está la tienda",
                              f"{rel['tiendas_con_mas_de_un_estado']} tiendas con más de un estado; "
                              f"{rel['tiendas_cuyo_codigo_no_empieza_por_su_estado']} filas cuyo código de tienda no empieza por su estado",
                              rel["tiendas_con_mas_de_un_estado"] > 0))
    comps.append(comprobacion("venta", "dept_id", "los departamentos desagregan las categorías",
                              f"{rel['departamentos_con_mas_de_una_categoria']} departamentos en más de una categoría",
                              rel["departamentos_con_mas_de_una_categoria"] > 0))
    comps.append(comprobacion("venta", "item_id", "cada producto pertenece a un departamento",
                              f"{rel['productos_con_mas_de_un_departamento']} productos en más de un departamento",
                              rel["productos_con_mas_de_un_departamento"] > 0))
    for col, n_guia in GUIA_JERARQUIA.items():
        n = int(venta[col].nunique())
        comps.append(comprobacion("venta", col, f"{n_guia} valores distintos", f"{n} valores distintos", n != n_guia))
    comps.append(comprobacion("precios", "sell_price", "una semana sin precio es una semana en que el producto no se vendió",
                              "no se comprueba aquí: hace falta cruzar con la venta y el calendario (calidad-datos, bloque 3.11)",
                              False))

    # Lo que difiere porque el caso es un recorte (reglas, apartado 3 y §5): no es una contradicción.
    recorte = [
        {"tabla": "venta", "columna": "item_id", "guia": f"{GUIA_PRODUCTOS} productos",
         "datos": f"{rel['productos_distintos']} productos", "motivo": "recorte de 500 productos (reglas de negocio §3)"},
        {"tabla": "venta", "columna": "d_1 … d_n", "guia": f"d_1 a d_{GUIA_DIAS_VENTA}",
         "datos": f"{b['primera']} a {b['ultima']}", "motivo": "la prueba final está apartada fuera del caso (reglas de negocio §5)"},
        {"tabla": "precios", "columna": "wm_yr_wk", "guia": "precios hasta la última semana del concurso",
         "datos": f"semanas {int(precios['wm_yr_wk'].min())} a {int(precios['wm_yr_wk'].max())}",
         "motivo": "la prueba final está apartada fuera del caso (reglas de negocio §5)"},
    ]
    return comps, recorte


# ══ 6. Datos personales (diccionario-datos §3) ═════════════════════════════════
PATRONES_PERSONALES = {
    "correo": r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}",
    "telefono": r"(?<!\d)\+?\d{9,12}(?!\d)",
    "documento": r"(?<![A-Z0-9])\d{8}[A-Z](?![A-Z0-9])",
    "cuenta": r"(?<![A-Z])[A-Z]{2}\d{2}[A-Z0-9]{12,30}",
}


def buscar_datos_personales(nombre, df):
    """Busca en cada columna de texto valores con forma de dato personal; devuelve las columnas que los tienen."""
    hallados = []
    for c in df.columns:
        if not pd.api.types.is_string_dtype(df[c]):
            continue
        valores = pd.Series(df[c].dropna().unique()).astype(str)
        for tipo, patron in PATRONES_PERSONALES.items():
            n = int(valores.str.contains(patron, regex=True).sum())
            if n:
                hallados.append({"tabla": nombre, "columna": c, "tipo": tipo, "valores_distintos": n})
    return hallados


# ══ 7. Informe Markdown, generado del JSON ═════════════════════════════════════
def fmt(x, codigo=False):
    """Número con punto de miles y coma decimal; un código (año, semana) sin punto de miles; el resto, tal cual."""
    if isinstance(x, bool) or x is None:
        return {True: "sí", False: "no", None: "—"}[x]
    if isinstance(x, int) and codigo:
        return str(x)
    if isinstance(x, int):
        return f"{x:,}".replace(",", ".")
    if isinstance(x, float):
        texto = f"{x:,.2f}".rstrip("0").rstrip(".") if x != int(x) else f"{int(x):,}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return str(x)


TILDES = {"codigo": "código", "categoria": "categoría", "mas": "más", "estan": "están", "ano": "año", "dia": "día", "dias": "días",
          "sabado": "sábado", "minima": "mínima", "maxima": "máxima", "ultima": "última", "algun": "algún",
          "minimo": "mínimo", "maximo": "máximo", "construccion": "construcción", "validacion": "validación",
          "pct": "%", "despues": "después", "maximo_de": "máximo de"}


def etiqueta(clave):
    """Convierte una clave del JSON en texto para la persona, con sus tildes."""
    return " ".join(TILDES.get(p, p) for p in clave.split("_"))


CLASES = {"resuelto": "resuelto", "no_se_puede_saber": "no se puede saber", "decision_de_negocio": "decisión de negocio"}


def generar_md(d):
    """Escribe el diccionario para la persona a partir del diccionario d que se guardó como JSON."""
    L = []
    a = L.append
    a("# Diccionario de datos del origen · caso 69\n")
    a(f"Generado por `{d['script']}` el {d['fecha_ejecucion'][:10]}, a partir de `diccionario-datos-origen.json`. "
      f"Fecha de los datos: {d['fecha_datos']}. Estado: **{d['resultado']['estado']}**, riesgo {d['resultado']['riesgo']}.\n")
    a(f"{d['resultado']['resumen']}\n")

    a("## 1. Cabecera\n")
    a(f"- Comprobado el {d['fecha_ejecucion'][:10]} con Python {d['entorno']['python']} y pandas {d['entorno']['pandas']}.")
    for e in d["entradas"]:
        a(f"- `{e['ruta']}`: {fmt(e['bytes'])} bytes; {fmt(e['filas'])} filas; {fmt(e['columnas'])} columnas; huella `{e['sha256']}`.")
    a(f"- Diccionario de la organización: `{d['diccionario_organizacion']}`.")
    a(f"- Contexto usado: {'; '.join(d['contexto_usado'])}.\n")

    a("## 2. Lectura\n")
    a("| Tabla | Codificación | Separador | Decimal | Solo el campo vacío es nulo | Avisos |")
    a("|---|---|---|---|---|---|")
    for t in d["tablas"]:
        lec = t["lectura"]
        a(f"| {t['tabla']} | {lec['codificacion']} | `{lec['separador']}` | `{lec['decimal']}` | {fmt(lec['solo_vacio_es_nulo'])} | "
          f"{'; '.join(lec['avisos']) or 'ninguno'} |")
    a("")

    a("## 3. Resumen\n")
    a("| Tabla | Qué es una fila | Filas | Columnas | Clave | Clave única |")
    a("|---|---|---|---|---|---|")
    for t in d["tablas"]:
        a(f"| {t['tabla']} | {t['que_es_una_fila']} | {fmt(t['filas'])} | {fmt(t['columnas'])} | {', '.join(t['clave'])} | {fmt(t['clave_unica'])} |")
    a("")

    a("## 4. Las tablas\n")
    for t in d["tablas"]:
        a(f"### {t['tabla']} · `{t['fichero']}`\n")
        linea = f"Una fila es {t['que_es_una_fila']}. Clave: {', '.join(t['clave'])} (única: {fmt(t['clave_unica'])})."
        if t.get("clave_alternativa"):
            linea += f" Clave alternativa: {', '.join(t['clave_alternativa'])} (única: {fmt(t['clave_alternativa_unica'])})."
        a(linea)
        a("\nClaves que parecen apuntar a otra tabla, todas supuestas porque la guía no declara relaciones:\n")
        for k in t["claves_hacia_otras_tablas"]:
            a(f"- {', '.join(k['columnas'])} → {k['tabla']}")
        a("\n| Columna | Tipo leído | Rol | Nulos | % nulos | Vacíos | Espacios | Distintos | Mínimo | Máximo | Clase | Significado | Procedencia |")
        a("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c in t["campos"]:
            a(f"| {c['columna']} | {c['tipo_leido']} | {c['rol']} | {fmt(c['nulos'])} | {fmt(c['nulos_pct'])} | {fmt(c['vacios'])} | "
              f"{fmt(c['espacios'])} | {fmt(c['distintos'])} | {fmt(c['minimo'], c['rol'] == 'codigo')} | {fmt(c['maximo'], c['rol'] == 'codigo')} | {CLASES[c['clase']]} | "
              f"{c['significado']} | {c['procedencia']} |")
        a("")
        listas = [c for c in t["campos"] if c["valores"]]
        if listas:
            a("Valores de las columnas de texto con 15 distintos o menos:\n")
            for c in listas:
                a(f"- **{c['columna']}**: " + "; ".join(f"{v['valor']} {fmt(v['frecuencia'])}" for v in c["valores"]))
            a("")
        raras = [c for c in t["campos"] if c["categorias_raras"]]
        if raras:
            a("Categorías raras (menos del 2,5 % de las filas o menos de cinco apariciones):\n")
            for c in raras:
                a(f"- **{c['columna']}**: {len(c['categorias_raras'])} de {fmt(c['distintos'])} categorías.")
            a("")
        magn = [c for c in t["campos"] if c["rol"] == "magnitud"]
        for c in magn:
            a(f"El cero de {c['columna']}: {c['significado_cero']}. La fila que falta: {c['significado_sin_fila']}.\n")
        if "bloque_dias" in t:
            b = t["bloque_dias"]
            a("#### El bloque de columnas de días\n")
            a(f"Las {fmt(b['columnas'])} columnas de días, de {b['primera']} a {b['ultima']}, se revisaron una a una "
              f"({fmt(b['columnas_revisadas'])} revisadas). Numeración seguida desde d_1: {fmt(b['nombres_seguidos'])}.\n")
            a("| Rasgo | Valor |")
            a("|---|---|")
            a(f"| tipos leídos | {', '.join(f'{k}: {fmt(v)} columnas' for k, v in b['tipos'].items())} |")
            a(f"| vacíos en el bloque | {fmt(b['nulos'])} |")
            a(f"| negativos en el bloque | {fmt(b['negativos'])} |")
            a(f"| mínimo y máximo de una celda | {fmt(b['minimo'])} y {fmt(b['maximo'])} |")
            a(f"| columnas con algún cero | {fmt(b['columnas_con_minimo_cero'])} |")
            a(f"| máximo más bajo de una columna | {fmt(b['maximo_mas_bajo_de_una_columna'])} |")
            a(f"| rol | {b['rol']} |")
            a(f"| clase | {CLASES[b['clase']]} |")
            a(f"| significado | {b['significado']} |")
            a(f"| el cero | {b['significado_cero']} |")
            a(f"| la fila que falta | {b['significado_sin_fila']} |")
            a(f"| procedencia | {b['procedencia']} |")
            a("")
            if b["fuera_del_bloque"]:
                a("Columnas que se salen del bloque, cada una con su ficha:\n")
                a("| Columna | Motivos | Mínimo | Máximo | Vacíos |")
                a("|---|---|---|---|---|")
                for f in b["fuera_del_bloque"]:
                    a(f"| {f['columna']} | {'; '.join(f['motivos'])} | {fmt(f['minimo'])} | {fmt(f['maximo'])} | {fmt(f['nulos'])} |")
                a("")
            else:
                a("Ninguna columna se sale del bloque.\n")
        if t.get("relaciones_medidas"):
            a("#### Relaciones medidas dentro de la tabla\n")
            for k, v in t["relaciones_medidas"].items():
                if isinstance(v, dict):
                    v = "; ".join(f"{kk}: {fmt(vv)}" for kk, vv in v.items()) or "ninguna"
                elif isinstance(v, list):
                    v = " a ".join(fmt(x) for x in v)
                else:
                    v = fmt(v)
                a(f"- {etiqueta(k)}: {v}")
            a("")
        if t.get("por_periodo"):
            a("#### Cifras por periodo\n")
            claves = list(next(iter(t["por_periodo"].values())).keys())
            a("| Periodo | " + " | ".join(etiqueta(k) for k in claves) + " |")
            a("|---|" + "---|" * len(claves))
            for p, vals in t["por_periodo"].items():
                celdas = []
                for k in claves:
                    v = vals[k]
                    celdas.append("; ".join(f"{kk} {fmt(vv)}" for kk, vv in v.items()) if isinstance(v, dict)
                                  else fmt(v, "semana" in k))
                a(f"| {etiqueta(p)} | " + " | ".join(celdas) + " |")
            a("")

    a("## 5. Contradicciones con el diccionario de la organización\n")
    a(f"El diccionario de la organización es la guía de participantes del concurso (`{d['diccionario_organizacion']}`), "
      f"apartado «The dataset». Se pusieron {len(d['comprobaciones_guia'])} afirmaciones suyas frente a los datos. "
      f"Mandan los datos.\n")
    if d["contradicciones"]:
        a("| Tabla | Columna | Qué dice la guía | Qué dicen los datos |")
        a("|---|---|---|---|")
        for c in d["contradicciones"]:
            a(f"| {c['tabla']} | {c['columna'] or '(fichero)'} | {c['que_dice_el_documento']} | {c['que_dicen_los_datos']} |")
    else:
        a("Ninguna afirmación de la guía choca con los datos.")
    a("\nLo que difiere porque el caso es un recorte, que no es una contradicción:\n")
    for r in d["diferencias_por_recorte"]:
        a(f"- {r['tabla']}, {r['columna']}: la guía dice {r['guia']}; los datos traen {r['datos']}. Motivo: {r['motivo']}.")
    a("\nLas afirmaciones de la guía que los datos cumplen:\n")
    for c in d["comprobaciones_guia"]:
        if not c["contradice"]:
            a(f"- {c['tabla']}, {c['columna'] or '(fichero)'}: {c['que_dice_el_documento']}. Datos: {c['que_dicen_los_datos']}.")
    a("")

    a("## 6. Columnas que no llegan al análisis\n")
    a(d["columnas_que_no_llegan_nota"] + "\n")

    a("## 7. Filtros de negocio\n")
    for f in d["filtros_de_negocio"]:
        a(f"- {f['regla']}: {fmt(f['filas_afectadas'])} {f['unidad']}.")
    a("")

    a("## 8. Decisiones de negocio pendientes\n")
    if d["pendientes"]:
        for p in d["pendientes"]:
            a(f"- **{p['id']} · {p['tabla']}, {p['columna']}.** {p['pregunta']} Lecturas posibles: "
              + "; ".join(f"({i + 1}) {o}" for i, o in enumerate(p["opciones"])) + ".")
    else:
        a("Ninguna.")
    a("")

    a("## 9. Lo que no se puede saber\n")
    for n in d["no_se_puede_saber"]:
        a(f"- {n['que']} ({n['procedencia']}).")
    a("")

    a("## 10. Datos personales\n")
    a(d["datos_personales_nota"] + "\n")

    a("## 11. Límites\n")
    for lim in d["limites"]:
        a(f"- {lim}")
    a("")

    a("## Validación de esta ejecución\n")
    for v in d["validacion"]:
        a(f"- {v['comprobacion']}: {fmt(v['resultado'])}.")
    a("")
    a("## Parámetros\n")
    for p in d["parametros"]:
        a(f"- {p['nombre']}: {fmt(p['valor'])} ({p['origen']}).")
    a("")
    return "\n".join(L)


# ══ 8. Ejecución ════════════════════════════════════════════════════════════════
def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def construir():
    """Lee las tres fuentes, las describe, valida y devuelve el diccionario de resultados."""
    inicio = time.time()
    huellas_antes = {n: huella(RAW / f) for n, f in FUENTES.items()}
    proteccion = json.loads(PROTECCION.read_text(encoding="utf-8")) if PROTECCION.exists() else None

    # Lectura de las tres fuentes enteras.
    leidas = {n: leer_fuente(n) for n in FUENTES}
    venta, precios, calendario = (leidas[n][0] for n in ("venta", "precios", "calendario"))

    # Perfil de cada tabla.
    t_venta = describir_venta(venta, calendario)
    t_precios = describir_precios(precios, calendario)
    t_cal = describir_calendario(calendario)
    tablas = [t_venta, t_precios, t_cal]
    for t in tablas:
        t["lectura"] = leidas[t["tabla"]][1]

    # Comparación con la guía.
    comprobaciones_guia, recorte = comprobar_guia(venta, precios, calendario, t_venta, t_cal)
    contradicciones = [{k: c[k] for k in ("tabla", "columna", "que_dice_el_documento", "que_dicen_los_datos")}
                       for c in comprobaciones_guia if c["contradice"]]

    # Datos personales y texto libre.
    personales = [h for n in FUENTES for h in buscar_datos_personales(n, leidas[n][0])]

    # Decisiones de negocio pendientes, sacadas de la clase calculada.
    pendientes = []
    for t in tablas:
        for c in t["campos"]:
            if c["clase"] != "decision_de_negocio":
                continue
            motivo = "categoria_rara" if c["categorias_raras"] else "cero_sin_significado"
            opciones = LECTURAS_COLUMNA.get((t["tabla"], c["columna"]), LECTURAS[motivo])
            if motivo == "categoria_rara":
                pregunta = (f"{len(c['categorias_raras'])} de sus {c['distintos']} categorías son raras "
                            f"({RARA_TEXTO}, contando los días sin evento). ¿Cómo se leen?")
            else:
                pregunta = "Su cero no tiene significado documentado. ¿Qué es un cero?"
            pendientes.append({"id": f"P-{len(pendientes) + 1:02d}", "tabla": t["tabla"], "columna": c["columna"],
                               "pregunta": pregunta, "opciones": opciones})

    # Filtros de negocio: lo que las reglas apartan o reservan, con cuántas filas afecta.
    filtros = [
        {"regla": "reglas de negocio §5: la prueba final (del 23/05/2015 al 22/05/2016) está fuera de data/raw/; "
                  "la venta llega hasta el 22/05/2015", "filas_afectadas": 0, "unidad": "filas de data/raw/ afectadas"},
        {"regla": "reglas de negocio §5: el calendario llega a propósito hasta el 19/06/2016; los días después de la "
                  "fecha de referencia no tienen venta en el caso",
         "filas_afectadas": t_cal["por_periodo"]["despues_de_la_fecha_de_referencia"]["filas"], "unidad": "filas del calendario"},
        {"regla": "reglas de negocio §7, «Población del análisis»: el reconocimiento y la exploración usan solo la "
                  "construcción; la validación se mira al medir el modelo",
         "filas_afectadas": t_venta["por_periodo"]["validacion"]["dias"], "unidad": "columnas de días de la venta en la validación"},
        {"regla": "precios después de la última semana de la construcción, que entran en la validación",
         "filas_afectadas": t_precios["por_periodo"]["despues"]["filas"], "unidad": "filas de precios"},
    ]

    huellas_despues = {n: huella(RAW / f) for n, f in FUENTES.items()}

    # Validación (diccionario-datos §9): cada resultado se calcula con lo que se ejecutó.
    con_ficha = {c["columna"] for c in t_venta["campos"]}
    dias = [c for c in venta.columns if c not in con_ficha]
    venta_cubierta = set(venta.columns) == con_ficha | set(dias) and t_venta["bloque_dias"]["columnas_revisadas"] == len(dias)
    precios_cubierta = {c["columna"] for c in t_precios["campos"]} == set(precios.columns)
    cal_cubierta = {c["columna"] for c in t_cal["campos"]} == set(calendario.columns)
    todos = [c for t in tablas for c in t["campos"]] + [t_venta["bloque_dias"]]
    validacion = [
        {"comprobacion": "todas las columnas de las tres fuentes tienen ficha o están en el bloque de días",
         "resultado": bool(venta_cubierta and precios_cubierta and cal_cubierta)},
        {"comprobacion": "cada significado tiene procedencia",
         "resultado": all(bool(c.get("procedencia")) and bool(c.get("significado")) for c in todos)},
        {"comprobacion": "ninguna columna con dato personal muestra valores",
         "resultado": not any(c["rol"] == "dato_personal" and c["valores"] for t in tablas for c in t["campos"])},
        {"comprobacion": "columnas con valores de forma de dato personal", "resultado": len(personales)},
        {"comprobacion": "las huellas de data/raw/ son iguales antes y después",
         "resultado": huellas_antes == huellas_despues},
        {"comprobacion": "las 1.575 columnas de días revisadas una a una",
         "resultado": t_venta["bloque_dias"]["columnas_revisadas"]},
    ]
    fallos = [v for v in validacion if v["resultado"] is False]

    if fallos:
        estado, riesgo = "ERROR", "alto"
    elif personales:
        estado, riesgo = "PARADO", "alto"
    elif pendientes or contradicciones or any(t["lectura"]["avisos"] for t in tablas):
        estado, riesgo = "AVISO", "bajo"
    else:
        estado, riesgo = "OK", "bajo"
    resumen = (f"Tres fuentes descritas: venta {fmt(t_venta['filas'])} filas, precios {fmt(t_precios['filas'])} filas y "
               f"calendario {fmt(t_cal['filas'])} filas; las {fmt(t_venta['bloque_dias']['columnas'])} columnas de días revisadas "
               f"una a una, con {len(t_venta['bloque_dias']['fuera_del_bloque'])} fuera del bloque. "
               f"{len(contradicciones)} contradicciones con la guía del concurso y {len(pendientes)} decisiones de negocio "
               f"pendientes. No hubo paso de protección de datos: proteccion-datos.json no existe y las reglas, apartado 9 dicen "
               f"que no hay datos personales.") if proteccion is None else "Hubo paso de protección de datos."

    d = {
        "metodo": "diccionario-datos",
        "version_metodo": version_metodo(),
        "script": "scripts/01_diccionario_datos.py",
        "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "entorno": {"python": platform.python_version(), "pandas": pd.__version__, "ejecutable": sys.executable},
        "entradas": [{"ruta": f"data/raw/{FUENTES[t['tabla']]}", "sha256": huellas_antes[t["tabla"]],
                      "bytes": (RAW / FUENTES[t["tabla"]]).stat().st_size, "filas": t["filas"], "columnas": t["columnas"]}
                     for t in tablas],
        "huellas_despues": huellas_despues,
        "resultado": {"estado": estado, "riesgo": riesgo, "resumen": resumen,
                      "artefactos": ["config/fuentes/diccionario-datos-origen.json",
                                     "config/fuentes/diccionario-datos-origen.md"],
                      "siguiente": "calidad-datos, con su plan aprobado por la persona responsable"},
        "pendientes": pendientes,
        "parametros": PARAMETROS,
        "periodos": {k: {"desde": v[0], "hasta": v[1]} for k, v in PERIODOS.items()},
        "diccionario_organizacion": GUIA,
        "contexto_usado": ["EQUIPO.md", "config/negocio/reglas-negocio.md",
                           "config/negocio/01_ficha_del_caso.md", "config/metodo/04_planteamientos.md",
                           GUIA],
        "tablas": tablas,
        "contradicciones": contradicciones,
        "comprobaciones_guia": comprobaciones_guia,
        "diferencias_por_recorte": recorte,
        "columnas_que_no_llegan": [],
        "columnas_que_no_llegan_nota": "No hay código de carga todavía: scripts/ no tenía ningún script antes de este. "
                                       "Ninguna columna se descarta en la lectura.",
        "filtros_de_negocio": filtros,
        "no_se_puede_saber": NO_SE_PUEDE_SABER,
        "datos_personales": personales,
        "datos_personales_nota": (
            "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las "
            "reglas de negocio §9 dicen que no hay datos de personas y el paso 2a no se hizo. Esta ejecución buscó en "
            f"cada columna de texto valores con forma de correo, teléfono, documento o cuenta y encontró {len(personales)} "
            "columnas con ellos. Este método no usa ni deja ninguna columna de datos personales."
            if proteccion is None else "Hay proteccion-datos.json: revisar su contenido."),
        "texto_libre": "ninguna columna es texto libre; no se buscaron órdenes dentro de las celdas",
        "limites": [
            "el diccionario describe una tabla cada vez; las claves huérfanas o repetidas entre tablas se ven primero "
            "en el apartado «Cruces entre tablas» de calidad-datos y se controlan al cruzarlas con integracion-datos",
            "la detección de datos personales mira columnas enteras; un nombre dentro de texto libre no lo caza",
            "las descripciones «sin confirmar» son deducciones y no se usan como regla",
            "el reparto de los vacíos por segmento no se mide aquí: lo mide calidad-datos en el bloque 3.4",
            "la afirmación de la guía sobre la semana sin precio necesita cruzar tablas y se comprueba en calidad-datos",
        ],
        "validacion": validacion,
        "duracion_segundos": None,
    }
    d["duracion_segundos"] = round(time.time() - inicio, 1)
    return a_json_limpio(d)


def main():
    """Construye el diccionario, escribe el JSON y genera de él el Markdown; si algo falla, deja el JSON con ERROR."""
    print("intérprete:", sys.executable)
    try:
        d = construir()
    except Exception as error:
        d = {"metodo": "diccionario-datos", "script": "scripts/01_diccionario_datos.py", "fecha_datos": FECHA_DATOS,
             "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
             "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(error).__name__}: {error}",
                           "artefactos": [], "siguiente": "arreglar el fallo"}, "pendientes": []}
        SALIDA_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        raise
    texto_json = json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False)
    texto_md = generar_md(json.loads(texto_json))
    SALIDA_JSON.write_text(texto_json, encoding="utf-8")
    SALIDA_MD.write_text(texto_md, encoding="utf-8")
    print("estado:", d["resultado"]["estado"], "· riesgo:", d["resultado"]["riesgo"])
    print("resumen:", d["resultado"]["resumen"])
    print("segundos:", d["duracion_segundos"])
    return 0 if d["resultado"]["estado"] in ("OK", "AVISO") else 1


if __name__ == "__main__":
    sys.exit(main())
