"""Corrección de las tres tablas del caso 69 (método correccion-datos), con la petición 07 del 23/11/2026.

Lee las tres tablas de data/raw/ (venta, precios y calendario) sin alterarlas y aplica solo las dos correcciones con
criterio: la fecha del calendario pasa de texto a fecha (C-04) y snap_CA, snap_TX y snap_WI pasan a minúsculas (C-03).
No quita filas, no cambia valores ni rellena vacíos: el caso entrena un modelo. Clasifica además los días a cero de las
70 series de departamento y tienda, sin cambiar ningún dato. Escribe:
  - data/processed/venta_corregido.parquet, precios_corregido.parquet y calendario_corregido.parquet;
  - informes/correccion-datos.json, para los métodos siguientes;
  - informes/correccion-datos.md, generado de ese JSON en la misma ejecución;
  - las fichas de la corrección en config/modelo/registro-transformaciones.md, debajo de lo que hay y una
    sola vez.

Depende de informes/calidad-datos.json (scripts/02_calidad_datos.py) y del diccionario del origen
(scripts/01_diccionario_datos.py): si la huella de su entrada no es la de data/raw/, para (resultado.md, regla 7). Las
decisiones de la persona responsable y los motivos de lo que no se cambia se leen del fichero de decisiones del
proyecto, config/modelo/decisiones-correccion.json (correccion-datos §3), que los copia literales de la petición
07, donde el responsable del caso los decidió.

Se ejecuta sin intervención manual:
  PYTHONUTF8=1 <python del entorno 69_prevision_ventas_walmart> -W error scripts/03_correccion_datos.py
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import hashlib
import json
import math
import platform
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import pyarrow.compute as pc
import pyarrow.parquet as pq

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
PROCESADOS = RAIZ / "data" / "processed"
CALIDAD = RAIZ / "informes" / "calidad-datos.json"
DICCIONARIO = RAIZ / "config" / "fuentes" / "diccionario-datos-origen.json"
PROTECCION = RAIZ / "config" / "fuentes" / "proteccion-datos.json"
REGISTRO = RAIZ / "config" / "modelo" / "registro-transformaciones.md"
VERSION_METODO = "20/11/2026"  # versión del método correccion-datos con que se escribió este script
SALIDA_JSON = RAIZ / "informes" / "correccion-datos.json"
SALIDA_MD = RAIZ / "informes" / "correccion-datos.md"
SCRIPT_REL = "scripts/03_correccion_datos.py"

# ── 1.1 Lo que fijan las reglas del caso y la petición ──
# El fichero de decisiones del proyecto (correccion-datos §3): la opción elegida en cada cuestión de la calidad, literal,
# y el motivo de cada problema que no se cambia. Las decisiones no viven en el código ni en un prompt.
DECISIONES_REL = "config/modelo/decisiones-correccion.json"
DECISIONES = RAIZ / DECISIONES_REL
PERMISO = ("el agente analista-preparacion-datos ejecuta `scripts/03_correccion_datos.py` por la petición "
           "petición 07, lanzado con el sí del responsable del caso («Sí, lánzalo») el 23/11/2026")
# Fecha de referencia y periodos (reglas, apartado 5). El calendario sigue 394 días más, que no son de ningún periodo.
FECHA_DATOS = "2015-05-22"
PERIODOS = {"construccion": ("2011-01-29", "2014-05-22"), "validacion": ("2014-05-23", "2015-05-22")}
FUENTES = {"venta": "sales_train_evaluation.csv", "precios": "sell_prices.csv", "calendario": "calendar.csv"}
SALIDAS = {"venta": "venta_corregido.parquet", "precios": "precios_corregido.parquet",
           "calendario": "calendario_corregido.parquet"}
# La fecha del calendario: tipo declarado «fecha y-m-d» en el diccionario; la calidad (C-04) lo demuestra.
COLUMNA_FECHA = ("calendario", "date")
FORMATO_FECHA = "%Y-%m-%d"
# El caso entrena un modelo: ningún vacío se rellena aquí (parametros.md; petición 07).
VA_A_MODELO = True
# Tabla de clases de los ceros (petición 07, con la guía de forecasting §3): media diaria por debajo de este valor.
UMBRAL_INTERMITENTE = 10
CLASES_CERO = ["cierre", "25_diciembre", "demanda_intermitente", "resto"]
SNAP = {"CA": "snap_CA", "TX": "snap_TX", "WI": "snap_WI"}
ETIQUETA_PERIODO = {"total": "total", "construccion": "construcción", "validacion": "validación"}
# Las fichas que esta corrección deja en el registro: número, contenido y título del bloque.
FICHAS = {"fecha": "R-001", "nombres": "R-002", "sin_cambios": "R-003"}
TITULO_FICHAS = "## Fichas de la corrección de datos (`scripts/03_correccion_datos.py`)"
# Del rol del diccionario al tipo con que se lee (petición 07): identificadores y nombres como texto; códigos, enteros.
ROL_A_TIPO = {"identificador": "texto", "clave": "texto", "categorica": "texto", "codigo": "entero",
              "booleana": "entero", "fecha": "fecha"}
TIPO_A_DTYPE = {"texto": "str", "entero": "int64", "decimal": "float64", "fecha": "str"}

# ── 1.2 Parámetros (parametros.md del método y del caso) ──
PARAMETROS = [
    {"nombre": "forma de los nombres de columna", "valor": "minúsculas, sin tildes ni eñes, guion bajo",
     "origen": "por defecto (criterios.md §5)"},
    {"nombre": "etiqueta del vacío en una categórica", "valor": "sin dato",
     "origen": "por defecto; no se usa: ningún vacío se rellena"},
    {"nombre": "marca de lo imputado", "valor": "<campo>_faltante, 0 y 1", "origen": "por defecto; no se usa: nada se imputa"},
    {"nombre": "si los datos van a un modelo", "valor": "no se imputa aquí",
     "origen": "por defecto; el caso entrena un modelo (petición 07)"},
    {"nombre": "formato de la tabla corregida", "valor": "Parquet", "origen": "por defecto"},
    {"nombre": "formato de la fecha", "valor": FORMATO_FECHA,
     "origen": "diccionario (tipo declarado «fecha y-m-d») y petición 07"},
    {"nombre": "umbral de la demanda intermitente", "valor": UMBRAL_INTERMITENTE,
     "origen": "petición 07, tabla de clases de los ceros (guía de forecasting §3)"},
    {"nombre": "periodos", "valor": {k: list(v) for k, v in PERIODOS.items()}, "origen": "reglas de negocio §5"},
]

TEORIA = [
    {"apartado": "8.1", "por_que": "cada corrección responde a un problema diagnosticado; la limpieza solo hace reglas "
                                   "que no aprenden nada de los datos, porque los datos van a un modelo"},
    {"apartado": "8.2", "por_que": "nombres en minúsculas, sin tildes y con guion bajo; el mapeo se guarda"},
    {"apartado": "8.3", "por_que": "la fecha se convierte con su formato explícito y se cuentan los valores que no se "
                                   "leen antes de darla por buena"},
    {"apartado": "8.10", "por_que": "el cierre: recuentos y sumas de antes y después, el registro junto al dato y lo "
                                    "pendiente con su motivo"},
]

LIMITES = [
    "La corrección mira una tabla cada vez. Una clave huérfana o repetida al otro lado de un cruce no se ve ni se "
    "corrige aquí.",
    "El diagnóstico completo de la calidad no se vuelve a pasar sobre las tablas corregidas (manual 8.10, paso 1). Se "
    "comparan filas, columnas, valores, tipos y sumas de antes y después.",
    "Los pesos que dan los motivos de C-12 a C-15 (porcentajes de dólares y unidades) vienen de la petición 07, copiados "
    "en el fichero de decisiones; este script no los recalcula.",
    "La regla de no tener dos decisiones sobre el mismo campo se aplica por cuestión: PC-03 y PC-04 son de la misma "
    "columna de la venta, igual que PC-05 y PC-06, porque cada una contesta una pregunta distinta.",
    "El script lista los días del resto de los ceros con su serie y su fecha. Qué son lo decide la cascada de D8.",
    "Los días del calendario posteriores a la fecha de referencia se corrigen igual que los demás. No son de ningún "
    "periodo y no entran en la clasificación de los ceros.",
]

PATRONES_PERSONALES = {
    "correo": r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}",
    "documento de identidad": r"\b(?:\d{8}|[XYZ]\d{7})[A-Za-z]\b",
    "teléfono": r"(?:\+\d{2,3}\s?)?\b[6789]\d{8}\b",
    "cuenta bancaria": r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){4,7}\b",
}


# ══ 2. Utilidades generales ══════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 del fichero, para comprobar que data/raw/ no cambia."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_json_limpio(obj):
    """Convierte tipos de numpy a Python y NaN o infinito a None, para un JSON válido (error 22)."""
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


def escribir_json(ruta, d):
    """Escribe el JSON en UTF-8, sin NaN."""
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(a_json_limpio(d), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def pasa_o_falla(condicion):
    """El veredicto de una comprobación, calculado con lo que se ejecutó (error 24)."""
    return "pasa" if condicion else "falla"


def es_dia(columna):
    """Una columna de días de la venta: d_1 a d_1575."""
    return re.fullmatch(r"d_\d+", columna) is not None


# ══ 3. Las reglas de corrección ══════════════════════════════════════════════════
# ── 3.1 Nombres de columna (criterios.md §5) ──
def normalizar_nombre(nombre):
    """Nombre normalizado de una columna: minúsculas, sin tildes y con guion bajo (manual 8.2)."""
    sin_tildes = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")


def mapeo_nombres(columnas):
    """Los nombres que cambian y las colisiones: dos columnas que acabarían con el mismo nombre."""
    nuevos = {}
    for c in columnas:
        nuevos.setdefault(normalizar_nombre(c), []).append(c)
    colisiones = [{"nombre": n, "columnas": cs} for n, cs in nuevos.items() if len(cs) > 1]
    mapeo = {c: normalizar_nombre(c) for c in columnas if normalizar_nombre(c) != c}
    return mapeo, colisiones


# ── 3.2 Tipos (manual 8.3) ──
def convertir_fecha(serie, formato):
    """Lee la fecha con su formato explícito; cuenta lo que no se lee antes de dar la conversión por buena."""
    convertida = pd.to_datetime(serie, format=formato, errors="coerce")
    no_convierten = int((convertida.isna() & serie.notna()).sum())
    return {"serie": convertida, "no_convierten": no_convierten, "vacias": int(serie.isna().sum())}


def tipo_logico(serie):
    """El tipo de una columna en las palabras de la petición: texto, entero, decimal o fecha."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return "fecha"
    if pd.api.types.is_bool_dtype(serie):
        return "booleano"
    if pd.api.types.is_integer_dtype(serie):
        return "entero"
    if pd.api.types.is_float_dtype(serie):
        return "decimal"
    if pd.api.types.is_string_dtype(serie):
        return "texto"
    return str(serie.dtype)


def comprobar_tipos(df, esperados):
    """Las columnas cuyo tipo no es el de su rol."""
    return [{"columna": c, "esperado": e, "leido": tipo_logico(df[c])} for c, e in esperados.items()
            if tipo_logico(df[c]) != e]


def tipos_esperados(diccionario):
    """El tipo de cada columna según su rol en el diccionario; una magnitud, entero o decimal según cómo llega."""
    esperados = {}
    for t in diccionario["tablas"]:
        tipos = {}
        for c in t["campos"]:
            if c["rol"] == "magnitud":
                tipos[c["columna"]] = "entero" if c["tipo_leido"].startswith("int") else "decimal"
            else:
                tipos[c["columna"]] = ROL_A_TIPO[c["rol"]]
        if t.get("bloque_dias"):
            tipo_dias = "entero" if set(t["bloque_dias"]["tipos"]) == {"int64"} else "decimal"
            tipos["__dias__"] = tipo_dias
        esperados[t["tabla"]] = tipos
    return esperados


# ── 3.3 Ningún valor cambia (criterio de éxito de la petición) ──
def valores_iguales(antes, despues, mapeos, fechas):
    """Deshace el nombre nuevo y la fecha y compara columna a columna; devuelve las diferencias."""
    diferencias = []
    for tabla, a in antes.items():
        b = despues[tabla]
        if len(a) != len(b):
            diferencias.append({"tabla": tabla, "columna": "filas", "antes": len(a), "despues": len(b)})
            continue
        b = b.rename(columns={v: k for k, v in mapeos.get(tabla, {}).items()})
        if list(a.columns) != list(b.columns):
            diferencias.append({"tabla": tabla, "columna": "columnas", "antes": len(a.columns), "despues": len(b.columns)})
            continue
        col_fecha, formato = fechas.get(tabla, (None, None))
        for c in a.columns:
            x, y = a[c], b[c]
            if c == col_fecha and pd.api.types.is_datetime64_any_dtype(y):
                y = y.dt.strftime(formato)
            iguales = (x.isna() == y.isna()) & ((x == y) | x.isna())
            distintas = int((~iguales.to_numpy(dtype=bool)).sum())
            if distintas:
                diferencias.append({"tabla": tabla, "columna": c, "filas": distintas})
    return diferencias


def cobertura(problemas, corregidos, sin_cambios):
    """Cada problema de la calidad, una sola vez en correcciones o en sin cambios."""
    vistos = list(corregidos) + [p for s in sin_cambios for p in s["problemas"]]
    return {"faltan": sorted(set(problemas) - set(vistos)),
            "repetidos": sorted({p for p in vistos if vistos.count(p) > 1}),
            "sobran": sorted(set(vistos) - set(problemas))}


# ── 3.4 Datos personales (correccion-datos §1) ──
def datos_personales(tablas):
    """Columnas de texto con valores con forma de dato personal: tabla, columna, tipo y filas, nunca el valor."""
    hallados = []
    for tabla, df in tablas.items():
        for c in df.columns:
            if not pd.api.types.is_string_dtype(df[c]) or pd.api.types.is_datetime64_any_dtype(df[c]):
                continue
            cuenta = df[c].dropna().value_counts()
            valores = pd.Series(cuenta.index.astype(str))
            filas, tipos = 0, []
            for nombre, patron in PATRONES_PERSONALES.items():
                casan = valores.str.contains(patron, regex=True).to_numpy()
                if casan.any():
                    tipos.append(nombre)
            if tipos:
                patron_junto = "|".join(f"(?:{PATRONES_PERSONALES[t]})" for t in tipos)
                filas = int(cuenta.to_numpy()[valores.str.contains(patron_junto, regex=True).to_numpy()].sum())
                hallados.append({"tabla": tabla, "columna": c, "tipos": tipos, "filas": filas})
    return hallados


# ══ 4. Decisiones y motivos, leídos del fichero de decisiones ════════════════════
def leer_fichero_decisiones(ruta):
    """Las decisiones (pendiente, opción literal y nota) y los motivos de lo que no se cambia (problemas, cuestiones y
    motivo) del fichero de decisiones del proyecto. Un campo que falta para la lectura con ValueError: sin él no se
    puede comprobar la decisión ni dar el motivo."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    faltan = [c for c in ("fecha", "decisiones", "sin_cambios") if c not in datos]
    faltan += [f"decisiones[{i}].{c}" for i, x in enumerate(datos.get("decisiones", []))
               for c in ("pendiente", "decision", "nota") if c not in x]
    faltan += [f"sin_cambios[{i}].{c}" for i, x in enumerate(datos.get("sin_cambios", []))
               for c in ("problemas", "pendientes", "motivo") if c not in x]
    if faltan:
        raise ValueError(f"al fichero de decisiones {ruta} le faltan: {', '.join(faltan)}")
    decisiones = [dict(x, fecha=datos["fecha"]) for x in datos["decisiones"]]
    return decisiones, datos["sin_cambios"]


def comprobar_decisiones(decisiones, pendientes):
    """Las cuatro comprobaciones de correccion-datos §2 antes de aplicar las respuestas de la persona responsable."""
    fallos = []
    opciones = {p["id"]: p["opciones"] for p in pendientes}
    ids = [x["pendiente"] for x in decisiones]
    for repetido in sorted({i for i in ids if ids.count(i) > 1}):
        fallos.append(f"{repetido} tiene dos decisiones")
    for x in decisiones:
        if x["pendiente"] not in opciones:
            fallos.append(f"{x['pendiente']} no es un pendiente de la calidad")
        elif x["decision"] not in opciones[x["pendiente"]]:
            fallos.append(f"{x['pendiente']}: la decisión no es una de las opciones ofrecidas")
    for falta in sorted(set(opciones) - set(ids)):
        fallos.append(f"{falta} se queda sin respuesta")
    return fallos


# ══ 5. Los días a cero de las 70 series ══════════════════════════════════════════
def clasificar_ceros(S, tienda, nombres, fechas, umbral):
    """Clase de cada día a cero de cada serie, en la primera que cumple: cierre, 25 de diciembre, intermitente, resto.

    S tiene una fila por serie (departamento en una tienda) y una columna por día del periodo.
    """
    S = np.asarray(S)
    tienda = np.asarray(tienda)
    fechas = np.asarray(fechas)
    cero = S == 0
    # Un cierre es la tienda con todos sus departamentos a cero ese día (reglas, apartado 5).
    cerrada = {t: cero[tienda == t].all(axis=0) for t in sorted(set(tienda.tolist()))}
    cierre_serie = np.vstack([cerrada[t] for t in tienda])
    navidad = np.array([f[5:] == "12-25" for f in fechas])
    medias = np.array([S[i, ~cierre_serie[i]].mean() if (~cierre_serie[i]).any() else np.nan for i in range(len(S))])
    intermitente = np.nan_to_num(medias, nan=np.inf) < umbral
    mascaras = {"cierre": cero & cierre_serie}
    mascaras["25_diciembre"] = cero & ~cierre_serie & navidad[None, :]
    mascaras["demanda_intermitente"] = cero & ~cierre_serie & ~navidad[None, :] & intermitente[:, None]
    mascaras["resto"] = cero & ~(mascaras["cierre"] | mascaras["25_diciembre"] | mascaras["demanda_intermitente"])
    orden = sorted(range(len(nombres)), key=lambda i: nombres[i])

    def dias_de(clase):
        """Los días de serie de una clase, ordenados por serie y fecha."""
        return [{"serie": nombres[i], "fecha": str(fechas[k])} for i in orden for k in np.nonzero(mascaras[clase][i])[0]]

    clases = {c: {"dias_serie": int(m.sum()), "series": int(m.any(axis=1).sum())} for c, m in mascaras.items()}
    clases["cierre"]["dias_de_tienda"] = int(sum(v.sum() for v in cerrada.values()))
    clases["cierre"]["tiendas_y_fechas"] = [{"tienda": t, "fecha": str(fechas[k])} for t in cerrada
                                            for k in np.nonzero(cerrada[t])[0]]
    clases["25_diciembre"]["lista"] = dias_de("25_diciembre")
    clases["demanda_intermitente"]["umbral"] = umbral
    clases["demanda_intermitente"]["series_bajo_el_umbral"] = int(intermitente.sum())
    clases["demanda_intermitente"]["lista"] = [
        {"serie": nombres[i], "media": round(float(medias[i]), 2), "dias_a_cero": int(mascaras["demanda_intermitente"][i].sum())}
        for i in orden if intermitente[i]]
    clases["resto"]["lista"] = dias_de("resto")
    demas = [i for i in orden if not intermitente[i] and not np.isnan(medias[i])]
    mas_baja = min(demas, key=lambda i: medias[i]) if demas else None
    total = int(cero.sum())
    return {
        "dias": int(S.shape[1]), "series": int(S.shape[0]), "dias_serie_a_cero": total, "clases": clases,
        "partes_suman_el_total": sum(c["dias_serie"] for c in clases.values()) == total,
        "media_mas_baja_de_las_demas": None if mas_baja is None else {"serie": nombres[mas_baja],
                                                                       "media": round(float(medias[mas_baja]), 2)},
        "medias": [{"serie": nombres[i], "media": round(float(medias[i]), 2)} for i in orden],
    }


def resto_por_serie(clase_resto):
    """El resto agrupado por serie: cuántos días y entre qué fechas."""
    grupos = {}
    for x in clase_resto["lista"]:
        grupos.setdefault(x["serie"], []).append(x["fecha"])
    return [{"serie": s, "dias": len(f), "desde": min(f), "hasta": max(f)} for s, f in sorted(grupos.items())]


# ══ 6. Sumas de control ══════════════════════════════════════════════════════════
def sumas_desde_pandas(venta, precios, calendario, periodos, snap):
    """Vía 1, antes: las sumas sobre las tablas leídas de data/raw/ con pandas."""
    fecha_de = dict(zip(calendario["d"], calendario["date"].astype(str).str[:10]))
    dias = [c for c in venta.columns if es_dia(c)]
    unidades = {"total": int(venta[dias].to_numpy().sum())}
    for p, (desde, hasta) in periodos.items():
        cols = [c for c in dias if desde <= fecha_de[c] <= hasta]
        unidades[p] = int(venta[cols].to_numpy().sum())
    return {"filas": {"venta": len(venta), "precios": len(precios), "calendario": len(calendario)},
            "columnas": {"venta": venta.shape[1], "precios": precios.shape[1], "calendario": calendario.shape[1]},
            "unidades": unidades, "suma_sell_price": round(float(precios["sell_price"].sum()), 2),
            "dias_snap": {e: int(calendario[c].sum()) for e, c in snap.items()}}


def sumas_desde_parquet(rutas, periodos, snap):
    """Vía 2, después: relee los Parquet con pyarrow, sin pandas, y suma con pyarrow.compute."""
    venta = pq.read_table(rutas["venta"])
    precios = pq.read_table(rutas["precios"])
    cal = pq.read_table(rutas["calendario"])
    fecha_de = dict(zip(cal.column("d").to_pylist(), [x.strftime("%Y-%m-%d") for x in cal.column("date").to_pylist()]))
    dias = [c for c in venta.column_names if es_dia(c)]
    por_dia = {c: int(pc.sum(venta.column(c)).as_py() or 0) for c in dias}
    unidades = {"total": sum(por_dia.values())}
    for p, (desde, hasta) in periodos.items():
        unidades[p] = sum(v for c, v in por_dia.items() if desde <= fecha_de[c] <= hasta)
    return {"filas": {"venta": venta.num_rows, "precios": precios.num_rows, "calendario": cal.num_rows},
            "columnas": {"venta": venta.num_columns, "precios": precios.num_columns, "calendario": cal.num_columns},
            "unidades": unidades, "suma_sell_price": round(float(pc.sum(precios.column("sell_price")).as_py()), 2),
            "dias_snap": {e: int(pc.sum(cal.column(c)).as_py()) for e, c in snap.items()}}


def sumas_control(antes, despues):
    """Cada magnitud que no debía cambiar, antes y después, con su coincidencia calculada."""
    filas = []

    def una(columna, a, b):
        """Una suma de control."""
        filas.append({"columna": columna, "antes": a, "despues": b, "coincide": a == b,
                      "via_antes": "pandas sobre data/raw/", "via_despues": "pyarrow sobre data/processed/"})
    for t in antes["filas"]:
        una(f"filas de {t}", antes["filas"][t], despues["filas"][t])
        una(f"columnas de {t}", antes["columnas"][t], despues["columnas"][t])
    for p in antes["unidades"]:
        una(f"unidades ({ETIQUETA_PERIODO[p]})", antes["unidades"][p], despues["unidades"][p])
    una("suma de sell_price", antes["suma_sell_price"], despues["suma_sell_price"])
    for e in antes["dias_snap"]:
        una(f"días SNAP de {e}", antes["dias_snap"][e], despues["dias_snap"][e])
    return filas


# ══ 7. Validación y estado ═══════════════════════════════════════════════════════
def validar(d):
    """Comprobaciones que paran con ERROR: huellas, sumas, cobertura de los problemas, valores y clases de ceros."""
    fallos = []
    cambiadas = [e["ruta"] for e in d["entradas"] if d["huellas_despues"].get(e["ruta"]) != e["sha256"]]
    if cambiadas:
        fallos.append({"comprobacion": "data/raw/ intacto", "detalle": cambiadas})
    distintas = [s["columna"] for s in d["sumas_control"] if s["antes"] != s["despues"]]
    if distintas:
        fallos.append({"comprobacion": "sumas de control iguales antes y después", "detalle": distintas})
    if any(d["cobertura"][k] for k in ("faltan", "repetidos", "sobran")):
        fallos.append({"comprobacion": "cada problema de la calidad una sola vez", "detalle": d["cobertura"]})
    if d["diferencias_de_valores"]:
        fallos.append({"comprobacion": "ningún valor cambiado", "detalle": d["diferencias_de_valores"]})
    malas = [p for p, c in d["clases_de_ceros"].items() if not c["partes_suman_el_total"]]
    if malas:
        fallos.append({"comprobacion": "las clases de ceros suman el total", "detalle": malas})
    return fallos


def estado_y_riesgo(fallos, paradas, pendientes):
    """ERROR si la validación falla; PARADO si una regla para; AVISO con pendientes; OK si no."""
    if fallos:
        return "ERROR", "alto"
    if paradas:
        return "PARADO", "alto"
    if pendientes:
        return "AVISO", "medio"
    return "OK", "bajo"


# ══ 8. Lectura ═══════════════════════════════════════════════════════════════════
def leer_tablas(esperados):
    """Lee las tres tablas con el tipo de su rol fijado al leer; la fecha llega como texto y se convierte después."""
    comun = dict(encoding="utf-8", sep=",", keep_default_na=False, na_values=[""])
    tablas = {}
    for tabla, fichero in FUENTES.items():
        cabecera = pd.read_csv(RAW / fichero, nrows=0, **comun).columns
        tipos = {c: TIPO_A_DTYPE[esperados[tabla]["__dias__"] if es_dia(c) and "__dias__" in esperados[tabla]
                                 else esperados[tabla][c]] for c in cabecera}
        tablas[tabla] = pd.read_csv(RAW / fichero, dtype=tipos, **comun)
    return tablas


def esperados_por_columna(df, esperados_tabla):
    """El tipo esperado de cada columna de la tabla, con el bloque de días desplegado."""
    return {c: (esperados_tabla["__dias__"] if es_dia(c) and "__dias__" in esperados_tabla else esperados_tabla[c])
            for c in df.columns}


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


# ══ 9. Construcción ══════════════════════════════════════════════════════════════
def esqueleto():
    """Todas las claves del JSON, vacías; construir() las llena y la prueba arma con él un resultado mínimo."""
    return {
        "metodo": "correccion-datos", "version_metodo": None, "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": None, "entorno": {}, "entradas": [], "huellas_despues": {},
        "resultado": {"estado": None, "riesgo": None, "resumen": "",
                      "artefactos": ["informes/correccion-datos.json", "informes/correccion-datos.md"]
                      + [f"data/processed/{s}" for s in SALIDAS.values()],
                      "siguiente": "la sesión principal rehace las cifras; después, la cascada de las reglas, apartado 5 y el "
                                   "diseño del modelo de datos (modelado-datos)"},
        "pendientes": [], "calidad": {}, "salidas": [], "correcciones": [], "sin_cambios": [], "decisiones_usuario": [],
        "sumas_control": [], "comprobaciones": {}, "nombres": [], "tipos_comprobados": [], "va_a_modelo": VA_A_MODELO,
        "parametros": PARAMETROS, "clases_de_ceros": {}, "cobertura": {"faltan": [], "repetidos": [], "sobran": []},
        "diferencias_de_valores": [], "datos_personales": [], "datos_personales_nota": "", "periodos": {},
        "teoria_aplicada": TEORIA, "limites": LIMITES, "cifras_de_control": {}, "paradas": [],
        "validacion": {}, "duracion_segundos": None, "duracion_por_parte": {},
    }


def comprobar_calidad(calidad, huellas):
    """La entrada de este método (resultado.md, «Al empezar»): el JSON de calidad existe, no paró y es de estos datos."""
    if calidad is None:
        return ["no existe informes/calidad-datos.json"]
    paradas = []
    if calidad["resultado"]["estado"] in ("PARADO", "ERROR"):
        paradas.append(f"el JSON de calidad está en {calidad['resultado']['estado']}")
    distintas = [e["ruta"] for e in calidad["entradas"] if huellas.get(e["ruta"]) != e["sha256"]]
    if distintas:
        paradas.append(f"la huella de la entrada de la calidad no es la de data/raw/: {distintas}")
    return paradas


def construir():
    """Lee, corrige, valida, guarda y mide; devuelve el diccionario del JSON."""
    inicio = time.time()
    partes = {}
    d = esqueleto()
    d["fecha_ejecucion"] = datetime.now().isoformat(timespec="seconds")
    d["version_metodo"] = version_metodo()
    d["entorno"] = {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                    "pyarrow": pyarrow.__version__, "ejecutable": sys.executable}
    d["periodos"] = {k: {"desde": v[0], "hasta": v[1]} for k, v in PERIODOS.items()}

    # ── 9.1 Huellas de entrada y la puerta del JSON de calidad ──
    huellas = {f"data/raw/{f}": huella(RAW / f) for f in FUENTES.values()}
    calidad = json.loads(CALIDAD.read_text(encoding="utf-8")) if CALIDAD.exists() else None
    d["paradas"] = [{"motivo": m} for m in comprobar_calidad(calidad, huellas)]
    if d["paradas"]:
        d["entradas"] = [{"ruta": r, "sha256": h} for r, h in huellas.items()]
        return d
    d["calidad"] = {"ruta": "informes/calidad-datos.json", "estado": calidad["resultado"]["estado"],
                    "fecha_ejecucion": calidad["fecha_ejecucion"], "problemas": len(calidad["problemas"]),
                    "pendientes": len(calidad["pendientes"])}

    # ── 9.2 Lectura con el tipo de cada rol ──
    t0 = time.time()
    diccionario = json.loads(DICCIONARIO.read_text(encoding="utf-8"))
    esperados = tipos_esperados(diccionario)
    antes = leer_tablas(esperados)
    partes["lectura"] = round(time.time() - t0, 2)
    d["entradas"] = [{"ruta": f"data/raw/{FUENTES[t]}", "sha256": huellas[f"data/raw/{FUENTES[t]}"], "filas": len(df),
                      "columnas": df.shape[1]} for t, df in antes.items()]

    # ── 9.3 Datos personales: si hay uno en claro, para sin corregir ──
    d["datos_personales"] = datos_personales(antes)
    d["datos_personales_nota"] = (
        "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas "
        "de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada de personas. "
        f"Esta ejecución buscó correos, documentos de identidad, teléfonos y cuentas bancarias en las columnas de texto "
        f"de las tres tablas y los encontró en {len(d['datos_personales'])} columnas. Este método no usa ni deja ninguna "
        "columna de datos personales.") if not PROTECCION.exists() else "Existe proteccion-datos.json: revisarlo."
    if d["datos_personales"]:
        d["paradas"] = [{"motivo": "dato personal en claro", "detalle": d["datos_personales"]}]
        return d

    # ── 9.4 Decisiones de la persona responsable y motivos de lo que no se cambia, del fichero de decisiones ──
    decisiones, motivos = leer_fichero_decisiones(DECISIONES)
    fallos_decision = comprobar_decisiones(decisiones, calidad["pendientes"])
    if fallos_decision:
        # Si falla una comprobación, no se aplica ninguna decisión y las cuestiones siguen pendientes (§2).
        d["pendientes"] = [dict(p, nota="; ".join(fallos_decision)) for p in calidad["pendientes"]]
    else:
        motivo_de = {pc_: m["motivo"] for m in motivos for pc_ in m["pendientes"]}
        problema_de = {p["id"]: p.get("problema") for p in calidad["pendientes"]}
        d["decisiones_usuario"] = [{"pendiente": x["pendiente"], "problema_calidad": problema_de[x["pendiente"]],
                                    "decision": x["decision"], "nota": x["nota"] or None,
                                    "motivo": motivo_de.get(x["pendiente"]), "fecha": x["fecha"],
                                    "fuente": DECISIONES_REL}
                                   for x in decisiones]

    # ── 9.5 Correcciones: la fecha (C-04) y los nombres (C-03) ──
    t0 = time.time()
    despues = {t: df.copy() for t, df in antes.items()}
    tabla_f, col_f = COLUMNA_FECHA
    fecha_conv = convertir_fecha(antes[tabla_f][col_f], FORMATO_FECHA)
    problema_fecha = next(p["id"] for p in calidad["problemas"] if p["tabla"] == tabla_f and p["columna"] == col_f)
    if fecha_conv["no_convierten"] == 0:
        despues[tabla_f][col_f] = fecha_conv["serie"]
    else:
        d["pendientes"].append({"id": "P-01", "tabla": tabla_f, "columna": col_f, "pregunta": (
            f"{fecha_conv['no_convierten']} fechas no se leen con {FORMATO_FECHA}. ¿Cómo se leen?"),
            "opciones": ["se deja como texto hasta saber su formato"]})
    mapeos, colisiones = {}, []
    for t, df in antes.items():
        mapeo, col = mapeo_nombres(list(df.columns))
        colisiones += [dict(c, tabla=t) for c in col]
        if mapeo and not col:
            mapeos[t] = mapeo
            despues[t] = despues[t].rename(columns=mapeo)
    if colisiones:
        d["pendientes"].append({"id": "P-02", "tabla": "varias", "columna": "nombres", "pregunta": (
            f"{len(colisiones)} colisiones al normalizar los nombres. ¿Qué nombre lleva cada columna?"), "opciones": [],
            "detalle": colisiones})
    cambiados = [(t, a, b) for t, m in mapeos.items() for a, b in m.items()]
    problema_nombres = next(p["id"] for p in calidad["problemas"]
                            if p["columna"] == ", ".join(a for _, a, _ in cambiados)) if cambiados else None
    partes["correccion"] = round(time.time() - t0, 2)

    # ── 9.6 Validar antes de guardar (error 15): ninguna fila ni valor cambia y cada tipo es el de su rol ──
    t0 = time.time()
    d["diferencias_de_valores"] = valores_iguales(antes, despues, mapeos, {tabla_f: (col_f, FORMATO_FECHA)})
    for t, df in despues.items():
        inverso = {v: k for k, v in mapeos.get(t, {}).items()}
        esperado = esperados_por_columna(df.rename(columns=inverso), esperados[t])
        esperado = {mapeos.get(t, {}).get(c, c): e for c, e in esperado.items()}
        malos = comprobar_tipos(df, esperado)
        dias = [c for c in df.columns if es_dia(c)]
        leidos_antes = {c: tipo_logico(antes[t][c]) for c in antes[t].columns}
        for c in [c for c in df.columns if not es_dia(c)]:
            origen = inverso.get(c, c)
            d["tipos_comprobados"].append({"tabla": t, "columna": c, "esperado": esperado[c], "antes": leidos_antes[origen],
                                           "despues": tipo_logico(df[c]), "cambia": leidos_antes[origen] != tipo_logico(df[c])})
        if dias:
            tipos_dias = sorted({tipo_logico(df[c]) for c in dias})
            d["tipos_comprobados"].append({"tabla": t, "columna": f"{dias[0]} a {dias[-1]}", "columnas": len(dias),
                                           "esperado": esperados[t]["__dias__"], "antes": ", ".join(tipos_dias),
                                           "despues": ", ".join(tipos_dias), "cambia": False})
        if malos:
            d["pendientes"].append({"id": f"P-T-{t}", "tabla": t, "columna": ", ".join(m["columna"] for m in malos),
                                    "pregunta": "columnas sin el tipo de su rol", "opciones": [], "detalle": malos})
    partes["validacion_antes_de_guardar"] = round(time.time() - t0, 2)

    # ── 9.7 Guardar los Parquet, solo si nada cambió ──
    t0 = time.time()
    rutas = {t: PROCESADOS / s for t, s in SALIDAS.items()}
    if not d["diferencias_de_valores"]:
        PROCESADOS.mkdir(parents=True, exist_ok=True)
        for t, df in despues.items():
            df.to_parquet(rutas[t], index=False)
    partes["escritura"] = round(time.time() - t0, 2)

    # ── 9.8 Sumas de control por dos vías: pandas sobre data/raw/ y pyarrow sobre los Parquet ──
    t0 = time.time()
    snap_despues = {e: mapeos.get("calendario", {}).get(c, c) for e, c in SNAP.items()}
    s_antes = sumas_desde_pandas(antes["venta"], antes["precios"], antes["calendario"], PERIODOS, SNAP)
    s_despues = sumas_desde_parquet(rutas, PERIODOS, snap_despues)
    d["sumas_control"] = sumas_control(s_antes, s_despues)
    partes["comprobacion_parquet"] = round(time.time() - t0, 2)

    # ── 9.9 Clases de los días a cero de las 70 series, en cada periodo ──
    t0 = time.time()
    venta, cal = despues["venta"], despues["calendario"]
    dias = [c for c in venta.columns if es_dia(c)]
    series = venta.groupby(["store_id", "dept_id"], sort=True)[dias].sum()
    nombres = [f"{t} {dp}" for t, dp in series.index]
    tienda_de = np.array([t for t, _ in series.index])
    fecha_de = dict(zip(cal["d"], cal["date"].dt.strftime("%Y-%m-%d")))
    for p, (desde, hasta) in PERIODOS.items():
        cols = [c for c in dias if desde <= fecha_de[c] <= hasta]
        d["clases_de_ceros"][p] = clasificar_ceros(series[cols].to_numpy(), tienda_de, nombres,
                                                   [fecha_de[c] for c in cols], UMBRAL_INTERMITENTE)
    partes["ceros"] = round(time.time() - t0, 2)

    # ── 9.10 Correcciones, sin cambios, nombres y salidas, todo calculado ──
    if fecha_conv["no_convierten"] == 0:
        d["correcciones"].append({
            "id": "K-01", "problema_calidad": problema_fecha, "tabla": tabla_f, "columna": col_f,
            "correccion": f"de texto a fecha con el formato {FORMATO_FECHA}", "criterio": "tecnicamente_inequivoca",
            "ficha": FICHAS["fecha"], "antes": tipo_logico(antes[tabla_f][col_f]), "despues": tipo_logico(despues[tabla_f][col_f]),
            "dtype_despues": str(despues[tabla_f][col_f].dtype), "filas_afectadas": len(antes[tabla_f]),
            "no_convierten": fecha_conv["no_convierten"], "vacias_antes": fecha_conv["vacias"],
            "vacias_despues": int(despues[tabla_f][col_f].isna().sum())})
    if cambiados:
        d["correcciones"].append({
            "id": "K-02", "problema_calidad": problema_nombres, "tabla": ", ".join(sorted({t for t, _, _ in cambiados})),
            "columna": ", ".join(a for _, a, _ in cambiados), "correccion": "nombre en minúsculas (criterios.md §5)",
            "criterio": "tecnicamente_inequivoca", "ficha": FICHAS["nombres"], "antes": [a for _, a, _ in cambiados],
            "despues": [b for _, _, b in cambiados], "columnas_afectadas": len(cambiados)})
    d["nombres"] = [{"tabla": t, "antes": a, "despues": b, "ficha": FICHAS["nombres"]} for t, a, b in cambiados]
    d["sin_cambios"] = [{"problema_calidad": p, "pendientes": m["pendientes"], "motivo": m["motivo"],
                         "ficha": FICHAS["sin_cambios"]} for m in motivos for p in m["problemas"]]
    d["sin_cambios"].sort(key=lambda x: x["problema_calidad"])
    d["cobertura"] = cobertura([p["id"] for p in calidad["problemas"]], [c["problema_calidad"] for c in d["correcciones"]],
                               motivos)
    for t, ruta in rutas.items():
        df = despues[t]
        ficha_de = {col_f: FICHAS["fecha"]} if t == tabla_f else {}
        ficha_de.update({b: FICHAS["nombres"] for tt, _, b in cambiados if tt == t})
        campos = [{"columna": c, "tipo": str(df[c].dtype), "nulos": int(df[c].isna().sum()), "distintos": int(df[c].nunique()),
                   "regla_aplicada": ficha_de.get(c)} for c in df.columns if not es_dia(c)]
        dias_t = [c for c in df.columns if es_dia(c)]
        if dias_t:
            bloque = df[dias_t].to_numpy()
            campos.append({"columna": f"{dias_t[0]} a {dias_t[-1]}", "columnas": len(dias_t),
                           "tipo": ", ".join(sorted({str(df[c].dtype) for c in dias_t})), "nulos": int(df[dias_t].isna().sum().sum()),
                           "distintos": int(np.unique(bloque).size), "regla_aplicada": None})
        d["salidas"].append({"tabla": t, "ruta": f"data/processed/{SALIDAS[t]}",
                             "sha256": huella(ruta) if ruta.exists() else None, "filas": len(df), "columnas": df.shape[1],
                             "campos_salida": campos})

    # ── 9.11 Las cuatro comprobaciones del dataset procesado (§4.4) ──
    filas_iguales = all(s["coincide"] for s in d["sumas_control"] if s["columna"].startswith(("filas", "columnas")))
    tipos_bien = all(x["despues"] == x["esperado"] for x in d["tipos_comprobados"])
    con_fecha = all(c in fecha_de for c in dias)
    d["comprobaciones"] = {
        "completitud": pasa_o_falla(filas_iguales),
        "consistencia": pasa_o_falla(tipos_bien and not d["diferencias_de_valores"]),
        "utilidad": pasa_o_falla(len(nombres) == 70 and con_fecha and all(len(c["medias"]) == 70 for c in d["clases_de_ceros"].values())),
        "datos_personales": pasa_o_falla(not d["datos_personales"]),
    }
    d["comprobaciones_detalle"] = {
        "completitud": "filas y columnas de las tres tablas, iguales antes y después",
        "consistencia": "cada columna con el tipo de su rol y ningún valor distinto al deshacer la corrección",
        "utilidad": "el análisis del caso, la previsión de las 70 series de departamento y tienda, sigue siendo posible: "
                    "las 70 series se forman y cada día de la venta tiene su fecha en el calendario",
        "datos_personales": "ninguna columna de texto con forma de dato personal",
    }

    # ── 9.12 Cifras de control (las de la petición, medidas en esta ejecución) ──
    cc = {}
    for t in FUENTES:
        cc[f"filas_{t}_antes"], cc[f"filas_{t}_despues"] = s_antes["filas"][t], s_despues["filas"][t]
        cc[f"columnas_{t}_antes"], cc[f"columnas_{t}_despues"] = s_antes["columnas"][t], s_despues["columnas"][t]
    for p in s_antes["unidades"]:
        cc[f"unidades_{p}_antes"], cc[f"unidades_{p}_despues"] = s_antes["unidades"][p], s_despues["unidades"][p]
    cc["suma_sell_price_antes"], cc["suma_sell_price_despues"] = s_antes["suma_sell_price"], s_despues["suma_sell_price"]
    cc["dias_snap_antes"], cc["dias_snap_despues"] = s_antes["dias_snap"], s_despues["dias_snap"]
    cc["nombres_cambiados"], cc["colisiones"] = len(cambiados), len(colisiones)
    fechas_leidas = despues[tabla_f][col_f]
    cc["fechas_leidas"] = int(fechas_leidas.notna().sum()) if fecha_conv["no_convierten"] == 0 else 0
    cc["fechas_vacias"] = int(fechas_leidas.isna().sum())
    cc["fecha_minima"] = str(pd.to_datetime(fechas_leidas).min().date())
    cc["fecha_maxima"] = str(pd.to_datetime(fechas_leidas).max().date())
    cc["clases_de_ceros"] = {p: {k: c["clases"][k]["dias_serie"] for k in CLASES_CERO} for p, c in d["clases_de_ceros"].items()}
    cc["dias_de_tienda_cerrada"] = {p: c["clases"]["cierre"]["dias_de_tienda"] for p, c in d["clases_de_ceros"].items()}
    cc["series_intermitentes"] = {p: [x["serie"] for x in c["clases"]["demanda_intermitente"]["lista"]]
                                  for p, c in d["clases_de_ceros"].items()}
    cc["resto_por_serie"] = {p: resto_por_serie(c["clases"]["resto"]) for p, c in d["clases_de_ceros"].items()}
    d["cifras_de_control"] = cc

    # ── 9.13 Huella final, validación y estado ──
    d["huellas_despues"] = {f"data/raw/{f}": huella(RAW / f) for f in FUENTES.values()}
    fallos = validar(d)
    d["validacion"] = {"comprobaciones": ["data/raw/ intacto", "sumas de control iguales antes y después",
                                          "cada problema de la calidad una sola vez", "ningún valor cambiado",
                                          "las clases de ceros suman el total"], "fallos": fallos}
    estado, riesgo = estado_y_riesgo(fallos, d["paradas"], d["pendientes"])
    total_ceros = sum(c["dias_serie_a_cero"] for c in d["clases_de_ceros"].values())
    d["resultado"].update(estado=estado, riesgo=riesgo, resumen=(
        f"La fecha del calendario pasa de texto a fecha y {len(cambiados)} nombres de columna pasan a minúsculas. "
        f"Ninguna fila ni valor cambia ({len(d['diferencias_de_valores'])} diferencias); "
        f"{len(d['decisiones_usuario'])} cuestiones de la calidad quedan decididas por la petición 07 "
        f"y los {fmt(total_ceros)} días de serie a cero de los dos periodos quedan clasificados."))
    d["duracion_por_parte"] = partes
    d["duracion_segundos"] = round(time.time() - inicio, 2)
    return a_json_limpio(d)


# ══ 10. Textos para la persona: informe y fichas del registro ════════════════════
def fmt(x, codigo=False):
    """Número con punto de miles y coma decimal; un código (semana, año) sin punto de miles."""
    if isinstance(x, bool) or x is None:
        return {True: "sí", False: "no", None: "sin dato"}[x]
    if isinstance(x, int) and codigo:
        return str(x)
    if isinstance(x, int):
        return f"{x:,}".replace(",", ".")
    if isinstance(x, float):
        if x == int(x) and abs(x) < 1e15:
            return fmt(int(x))
        texto = f"{x:,.4f}".rstrip("0").rstrip(".")
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return str(x)


def frase(texto):
    """Primera letra en mayúscula, sin tocar las demás (SNAP, CA)."""
    return texto[:1].upper() + texto[1:] if texto else texto


def lista_y(valores):
    """Une una lista en texto: «a, b y c»."""
    valores = [str(v) for v in valores]
    if len(valores) <= 1:
        return "".join(valores)
    return ", ".join(valores[:-1]) + " y " + valores[-1]


PERIODO_TXT = {"construccion": "construcción", "validacion": "validación"}
CLASE_TXT = {"cierre": "cierre de la tienda", "25_diciembre": "25 de diciembre",
             "demanda_intermitente": "demanda intermitente", "resto": "resto"}


def fecha_es(iso):
    """De AAAA-MM-DD a DD/MM/AAAA, como las fichas que ya hay en el registro."""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def suma(d, columna):
    """Una suma de control del JSON por su nombre."""
    return next((s for s in d["sumas_control"] if s["columna"] == columna), {"antes": None, "despues": None})


def texto_ceros(d):
    """Las clases de los ceros, por periodo: de lo general (el total) a lo concreto (cada día del resto)."""
    L = []
    for p, c in d["clases_de_ceros"].items():
        cl = c["clases"]
        L.append(f"  - {PERIODO_TXT[p].capitalize()}: {fmt(c['dias_serie_a_cero'])} días de serie a cero en "
                 f"{fmt(c['series'])} series.")
        for k in CLASES_CERO:
            extra = (f", {fmt(cl[k]['dias_de_tienda'])} días de tienda cerrada" if k == "cierre" else "")
            L.append(f"    - {CLASE_TXT[k].capitalize()}: {fmt(cl[k]['dias_serie'])} días de serie en "
                     f"{fmt(cl[k]['series'])} series{extra}.")
        inter = cl["demanda_intermitente"]["lista"]
        if inter:
            L.append(f"    - Series con media de menos de {fmt(cl['demanda_intermitente']['umbral'])} unidades al día, "
                     f"{fmt(cl['demanda_intermitente']['series_bajo_el_umbral'])} en total: "
                     + "; ".join(f"{x['serie']} ({fmt(x['media'])})" for x in inter) + ".")
        if c["media_mas_baja_de_las_demas"]:
            m = c["media_mas_baja_de_las_demas"]
            L.append(f"    - La serie que menos vende de las demás es {m['serie']}, con {fmt(m['media'])} de media.")
        for r in resto_por_serie(cl["resto"]):
            L.append(f"    - Resto en {r['serie']}: {fmt(r['dias'])} días entre el {r['desde']} y el {r['hasta']}.")
    return L


def generar_md(d):
    """Informe para la persona a partir del diccionario que se guardó como JSON, con la estructura de la plantilla."""
    L = []
    a = L.append
    res = d["resultado"]
    a("# Informe de corrección de datos · caso 69\n")
    a(f"Informe generado por `{d['script']}` a partir de `informes/correccion-datos.json`. Estado **{res['estado']}**, "
      f"riesgo {res['riesgo']}. Fecha de los datos: {d['fecha_datos']}.\n")
    a(res["resumen"] + "\n")

    a("## Fuente\n")
    for e in d["entradas"]:
        a(f"- Entrada `{e['ruta']}`: {fmt(e.get('filas'))} filas y {fmt(e.get('columnas'))} columnas; huella `{e['sha256']}`.")
    if d["calidad"]:
        q = d["calidad"]
        a(f"- Diagnóstico de partida: `{q['ruta']}`, en estado {q['estado']}, con {fmt(q['problemas'])} problemas "
          f"y {fmt(q['pendientes'])} cuestiones.")
    for s in d["salidas"]:
        a(f"- Salida `{s['ruta']}`: {fmt(s['filas'])} filas y {fmt(s['columnas'])} columnas; huella `{s['sha256']}`.")
    en = d["entorno"]
    a(f"- Ejecución del {d['fecha_ejecucion']} con Python {en.get('python')}, pandas {en.get('pandas')} y pyarrow "
      f"{en.get('pyarrow')}. Duró {fmt(d['duracion_segundos'])} segundos.")
    a("- Teoría del manual aplicada: " + "; ".join(f"{t['apartado']}, {t['por_que']}" for t in d["teoria_aplicada"]) + ".")
    a("")

    a("## Correcciones aplicadas\n")
    if not d["correcciones"]:
        a("Ninguna corrección cambió algo en esta ejecución.")
    for c in d["correcciones"]:
        if c["id"] == "K-01":
            a(f"- **{c['problema_calidad']}, la fecha del calendario.** `{c['tabla']}.{c['columna']}` pasa {c['correccion']}. "
              f"Es una corrección técnicamente inequívoca: {fmt(c['no_convierten'])} fechas no se leen con ese formato. "
              f"Antes era {c['antes']} y ahora es {c['despues']} ({c['dtype_despues']}) en las {fmt(c['filas_afectadas'])} filas, "
              f"con {fmt(c['vacias_despues'])} vacías. Ficha {c['ficha']}.")
        else:
            pares = "; ".join(f"`{x}` pasa a `{y}`" for x, y in zip(c["antes"], c["despues"]))
            a(f"- **{c['problema_calidad']}, los nombres de columna.** En `{c['tabla']}`: {pares}. Es una corrección "
              f"técnicamente inequívoca (criterios.md §5) con {fmt(d['cifras_de_control'].get('colisiones'))} colisiones. "
              f"Ninguna otra columna cambia de nombre. Ficha {c['ficha']}.")
    bien = [x for x in d["tipos_comprobados"] if not x["cambia"]]
    if bien:
        a(f"- Tipos comprobados sin cambio: {fmt(len(bien))} columnas o bloques ya traían el tipo de su rol "
          f"(texto, entero o decimal). Un tipo que ya está bien no es una corrección.")
    a("")

    a("## Decisiones del responsable\n")
    if not d["decisiones_usuario"]:
        a("No hay decisiones de la persona responsable aplicadas en esta ejecución.")
    else:
        a(f"Las cuestiones de la calidad quedan decididas por el responsable del caso en la petición 07, con fecha "
          f"{d['decisiones_usuario'][0]['fecha']}. El script las lee del fichero de decisiones "
          f"`{d['decisiones_usuario'][0]['fuente']}`. Ninguna cambia un dato.\n")
        for x in d["decisiones_usuario"]:
            nota = f" {x['nota']}." if x.get("nota") else ""
            a(f"- **{x['pendiente']}** ({x['problema_calidad']}): «{x['decision']}».{nota} Motivo: {x['motivo']}")
    a("")

    a("## Elementos mantenidos sin cambios\n")
    a(f"{fmt(len(d['sin_cambios']))} problemas de la calidad se dejan como están, cada uno con su motivo. Todos van "
      f"en la ficha {FICHAS['sin_cambios']} del registro.\n")
    for s in d["sin_cambios"]:
        cuestion = f" ({lista_y(s['pendientes'])})" if s["pendientes"] else ""
        a(f"- **{s['problema_calidad']}**{cuestion}: {s['motivo']}")
        if s["problema_calidad"] == "C-18" and d["clases_de_ceros"]:
            a("  - Clases de los días a cero de las 70 series de departamento y tienda. Cada cero va a la primera clase "
              "que cumple, en este orden: cierre de la tienda, 25 de diciembre, demanda intermitente y resto.")
            L.extend(texto_ceros(d))
    a("")

    a("## Decisiones pendientes\n")
    if not d["pendientes"]:
        a("No queda ninguna. Las seis cuestiones de la calidad están en «Decisiones del responsable».")
    for p in d["pendientes"]:
        a(f"- **{p.get('id')}** ({p.get('tabla')}, {p.get('columna')}): {p.get('pregunta')} Opciones: "
          + "; ".join(p.get("opciones") or ["sin opciones cerradas todavía"]) + ".")
    a("")

    a("## Validación\n")
    for t in ("venta", "precios", "calendario"):
        f_, c_ = suma(d, f"filas de {t}"), suma(d, f"columnas de {t}")
        a(f"- {t.capitalize()}: {fmt(f_['antes'])} filas antes y {fmt(f_['despues'])} después; "
          f"{fmt(c_['antes'])} columnas antes y {fmt(c_['despues'])} después.")
    for s in d["sumas_control"]:
        if not s["columna"].startswith(("filas", "columnas")):
            a(f"- {frase(s['columna'])}: {fmt(s['antes'])} antes y {fmt(s['despues'])} después; coincide: "
              f"{fmt(s['coincide'])}.")
    a("- Las dos vías: antes, pandas sobre `data/raw/`; después, pyarrow sobre los Parquet de `data/processed/`.")
    a(f"- Valores distintos al deshacer la corrección: {fmt(len(d['diferencias_de_valores']))}.")
    for k, v in d["comprobaciones"].items():
        a(f"- Comprobación de {k.replace('_', ' ')}: {v}. {frase(d.get('comprobaciones_detalle', {}).get(k, ''))}.")
    fallos = d["validacion"].get("fallos") if d["validacion"] else None
    a(f"- Validaciones que paran el trabajo: {fmt(len(fallos)) if fallos is not None else 'no se llegó a validar'} fallos.")
    iguales = all(d["huellas_despues"].get(e["ruta"]) == e["sha256"] for e in d["entradas"])
    a(f"- Huella de `data/raw/` igual antes y después: {fmt(iguales)}.")
    a(f"- Estado final: {res['estado']}. Tablas generadas: " + "; ".join(f"`{s['ruta']}`" for s in d["salidas"]) + ".")
    a("")

    a("## Datos personales\n")
    a(d["datos_personales_nota"] or "Sin nota.")
    a("")

    a("## Límites\n")
    for x in d["limites"]:
        a(f"- {x}")
    a("")
    return "\n".join(L)


def fichas_registro(d):
    """Las tres fichas de nueve campos del registro de transformaciones (correccion-datos §5), con cifras del JSON."""
    fecha = fecha_es((d["fecha_ejecucion"] or "")[:10])
    cc = d["cifras_de_control"]
    k1 = next((c for c in d["correcciones"] if c["id"] == "K-01"), None)
    k2 = next((c for c in d["correcciones"] if c["id"] == "K-02"), None)
    fichas = []
    filas_cal = suma(d, "filas de calendario")
    if k1:
        fichas.append((FICHAS["fecha"], "\n".join([
            f"### {FICHAS['fecha']} · {fecha} · {k1['tabla']}.{k1['columna']}, de texto a fecha", "",
            f"1. **Tabla y columna:** {k1['tabla']}, `{k1['columna']}` (`data/raw/calendar.csv`).",
            f"2. **Cómo estaba:** texto con el formato año-mes-día en {fmt(k1['filas_afectadas'])} filas, "
            f"con {fmt(k1['vacias_antes'])} vacías.",
            f"3. **Problema:** {k1['problema_calidad']} de la calidad: la fecha llega como texto.",
            f"4. **Decisión:** corrección técnicamente inequívoca (`criterios.md` §1), porque {fmt(k1['no_convierten'])} "
            f"fechas no se leen con el formato `{FORMATO_FECHA}`. La pide la petición 07.",
            "5. **Qué se hizo:** se lee con el formato explícito, sin inferirlo. Antes de dar la conversión por buena se "
            "cuentan las fechas que no se leen.",
            "",
            "   ```python",
            f'   convertida = pd.to_datetime(calendario["date"], format="{FORMATO_FECHA}", errors="coerce")',
            '   no_convierten = int((convertida.isna() & calendario["date"].notna()).sum())   # tiene que ser 0',
            '   calendario["date"] = convertida',
            "   ```",
            "",
            f"6. **Quién y con qué permiso:** {PERMISO}.",
            f"7. **Comprobación:** {fmt(cc.get('fechas_leidas'))} fechas leídas con {fmt(cc.get('fechas_vacias'))} vacías, "
            f"del {cc.get('fecha_minima')} al {cc.get('fecha_maxima')}. Al volver a texto dicen el mismo día que el origen "
            f"en todas las filas ({fmt(len(d['diferencias_de_valores']))} diferencias). Filas: {fmt(filas_cal['antes'])} "
            f"antes y {fmt(filas_cal['despues'])} después.",
            f"8. **Cómo quedó:** `{k1['columna']}` con tipo fecha ({k1['dtype_despues']}) en "
            "`data/processed/calendario_corregido.parquet`.",
            f'9. **Cómo deshacer:** `calendario["date"] = calendario["date"].dt.strftime("{FORMATO_FECHA}")`. El origen, '
            "`data/raw/calendar.csv`, no cambia.",
            ""])))
    if k2:
        mapeo = "; ".join(f"`{x}` pasa a `{y}`" for x, y in zip(k2["antes"], k2["despues"]))
        inverso = ", ".join(f'"{y}": "{x}"' for x, y in zip(k2["antes"], k2["despues"]))
        snap_a, snap_d = cc.get("dias_snap_antes") or {}, cc.get("dias_snap_despues") or {}
        fichas.append((FICHAS["nombres"], "\n".join([
            f"### {FICHAS['nombres']} · {fecha} · nombres de columna de {k2['tabla']}", "",
            f"1. **Tabla y columna:** {k2['tabla']}, {lista_y(f'`{x}`' for x in k2['antes'])}.",
            f"2. **Cómo estaba:** {fmt(k2['columnas_afectadas'])} nombres con mayúsculas. Las demás columnas de las tres "
            "tablas ya seguían la forma normalizada.",
            f"3. **Problema:** {k2['problema_calidad']} de la calidad: nombres que no siguen la forma normalizada.",
            f"4. **Decisión:** corrección técnicamente inequívoca (`criterios.md` §5), con {fmt(cc.get('colisiones'))} "
            "colisiones. El diccionario y las reglas nombran las columnas por su nombre de origen, así que el mapeo "
            f"entero va aquí: {mapeo}.",
            "5. **Qué se hizo:** cada nombre pasa a minúsculas, sin tildes y con guion bajo. El mapeo se calcula con esa "
            "regla sobre todas las columnas de las tres tablas, sin escribir ningún nombre a mano.",
            "",
            "   ```python",
            "   mapeo = {c: normalizar_nombre(c) for c in calendario.columns if normalizar_nombre(c) != c}",
            "   calendario = calendario.rename(columns=mapeo)",
            "   ```",
            "",
            f"6. **Quién y con qué permiso:** {PERMISO}.",
            f"7. **Comprobación:** {fmt(cc.get('nombres_cambiados'))} nombres cambiados. Los días SNAP de cada estado no "
            "cambian: " + "; ".join(f"{e}, {fmt(snap_a.get(e))} antes y {fmt(snap_d.get(e))} después" for e in snap_a) + ".",
            "8. **Cómo quedó:** `data/processed/calendario_corregido.parquet` con "
            f"{lista_y(f'`{x}`' for x in k2['despues'])}. La venta y los precios no cambian ningún nombre.",
            f"9. **Cómo deshacer:** `calendario = calendario.rename(columns={{{inverso}}})`.",
            ""])))
    ids = [s["problema_calidad"] for s in d["sin_cambios"]]
    ceros = "; ".join(f"{PERIODO_TXT.get(p, p)}: " + ", ".join(f"{CLASE_TXT[k]} {fmt(v)}" for k, v in c.items())
                      for p, c in (cc.get("clases_de_ceros") or {}).items())
    unidades = "; ".join(f"{ETIQUETA_PERIODO[p]}, {fmt(suma(d, f'unidades ({ETIQUETA_PERIODO[p]})')['antes'])} antes y "
                         f"{fmt(suma(d, f'unidades ({ETIQUETA_PERIODO[p]})')['despues'])} después"
                         for p in ("total", "construccion", "validacion"))
    precio = suma(d, "suma de sell_price")
    decisiones = [f"   - {x['pendiente']} ({x['problema_calidad']}): «{x['decision']}»." for x in d["decisiones_usuario"]]
    fichas.append((FICHAS["sin_cambios"], "\n".join([
        f"### {FICHAS['sin_cambios']} · {fecha} · lo que se deja sin cambios, con PC-01 a PC-06", "",
        f"1. **Tabla y columna:** venta, precios y calendario. Son {fmt(len(ids))} problemas de la calidad: "
        f"{lista_y(ids)}.",
        "2. **Cómo estaba:** como llega de `data/raw/`; cada problema está descrito en `informes/calidad-datos.json`.",
        "3. **Problema:** los problemas de la calidad que no tienen corrección y sus cuestiones abiertas, PC-01 a PC-06.",
        "4. **Decisión:** se usan los datos como están. Las cuestiones quedan decididas por la petición 07 con la opción "
        "que ofreció la calidad, copiada literal:",
        *decisiones,
        "   El motivo de cada problema está en `informes/correccion-datos.json` (`sin_cambios`). Ninguno cambia una "
        "respuesta del caso: la petición lo midió antes de lanzarse.",
        "5. **Qué se hizo:** ningún cambio. Se comprueba que ninguna fila ni valor cambia al deshacer el nombre nuevo y "
        "la fecha. Los días a cero de las 70 series se clasifican sin tocar ningún dato (`clases_de_ceros` del JSON).",
        "",
        "   ```python",
        '   diferencias = valores_iguales(antes, despues, mapeos, {"calendario": ("date", "%Y-%m-%d")})   # tiene que ser []',
        "   ```",
        "",
        f"6. **Quién y con qué permiso:** decide el responsable del caso con el sí a la petición 07; {PERMISO}.",
        f"7. **Comprobación:** {fmt(len(d['diferencias_de_valores']))} valores distintos. Unidades: {unidades}. Suma de "
        f"`sell_price`: {fmt(precio['antes'])} antes y {fmt(precio['despues'])} después. Días de serie a cero por clase: "
        f"{ceros}.",
        "8. **Cómo quedó:** las tres tablas de `data/processed/` con los mismos valores que `data/raw/`.",
        "9. **Cómo deshacer:** no hay nada que deshacer. Si una decisión cambia, se añade una ficha nueva que lo diga.",
        ""])))
    return fichas


def anadir_fichas(ruta, fichas, titulo):
    """Añade debajo de lo que hay las fichas que aún no están, sin tocar nada; devuelve las que añadió."""
    texto = Path(ruta).read_text(encoding="utf-8") if Path(ruta).exists() else "# Registro de transformaciones\n"
    nuevas = [(i, f) for i, f in fichas if not re.search(rf"^### {re.escape(i)} ", texto, flags=re.M)]
    if not nuevas:
        return []
    añadido = "" if texto.endswith("\n") else "\n"
    if titulo not in texto:
        añadido += f"\n{titulo}\n"
    for _, f in nuevas:
        añadido += "\n" + f
    Path(ruta).write_text(texto + añadido, encoding="utf-8")
    return [i for i, _ in nuevas]


def resultado_minimo_de_prueba():
    """Un resultado mínimo, con todas las claves llenas, para probar la validación, el informe y las fichas."""
    d = esqueleto()
    d.update(fecha_ejecucion="2026-01-01T00:00:00", entorno={"python": "x", "pandas": "y", "pyarrow": "z"},
             duracion_segundos=1.0)
    d["resultado"].update(estado="OK", riesgo="bajo", resumen="Prueba.")
    d["entradas"] = [{"ruta": "data/raw/a.csv", "sha256": "h1", "filas": 2, "columnas": 2}]
    d["huellas_despues"] = {"data/raw/a.csv": "h1"}
    d["sumas_control"] = [{"columna": "filas de calendario", "antes": 2, "despues": 2, "coincide": None},
                          {"columna": "unidades (total)", "antes": 5, "despues": 5, "coincide": None},
                          {"columna": "suma de sell_price", "antes": 1.5, "despues": 1.5, "coincide": None}]
    d["correcciones"] = [
        {"id": "K-01", "problema_calidad": "C-04", "tabla": "calendario", "columna": "date", "correccion": "de texto a fecha",
         "criterio": "tecnicamente_inequivoca", "ficha": "R-001", "antes": "texto", "despues": "fecha",
         "dtype_despues": "datetime64[us]", "filas_afectadas": 2, "no_convierten": 0, "vacias_antes": 0, "vacias_despues": 0},
        {"id": "K-02", "problema_calidad": "C-03", "tabla": "calendario", "columna": "snap_CA",
         "correccion": "nombre en minúsculas", "criterio": "tecnicamente_inequivoca", "ficha": "R-002", "antes": ["snap_CA"],
         "despues": ["snap_ca"], "columnas_afectadas": 1}]
    d["sin_cambios"] = [{"problema_calidad": "C-01", "pendientes": ["PC-01"], "motivo": "motivo.", "ficha": "R-003"}]
    d["decisiones_usuario"] = [{"pendiente": "PC-01", "problema_calidad": "C-01", "decision": "se usan", "nota": None,
                                "motivo": "motivo.", "fecha": "2026-01-01", "fuente": DECISIONES_REL}]
    d["cifras_de_control"] = {"fechas_leidas": 2, "fechas_vacias": 0, "fecha_minima": "2011-01-29",
                              "fecha_maxima": "2011-01-30", "colisiones": 0, "nombres_cambiados": 1,
                              "dias_snap_antes": {"CA": 1}, "dias_snap_despues": {"CA": 1},
                              "clases_de_ceros": {"construccion": {"cierre": 1}}}
    d["comprobaciones"] = {"completitud": pasa_o_falla(1 == 1)}
    d["validacion"] = {"fallos": []}
    return d


# ══ 11. Ejecución ════════════════════════════════════════════════════════════════
def main():
    """Construye la corrección, escribe el JSON y el Markdown y añade las fichas; si algo falla, deja el JSON con ERROR."""
    print("intérprete:", sys.executable)
    try:
        d = construir()
    except Exception as error:
        d = esqueleto()
        d["fecha_ejecucion"] = datetime.now().isoformat(timespec="seconds")
        d["resultado"].update(estado="ERROR", riesgo="alto", resumen=f"{type(error).__name__}: {error}",
                              artefactos=["informes/correccion-datos.json"], siguiente="arreglar el fallo")
        escribir_json(SALIDA_JSON, d)
        raise
    texto_json = json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False)
    texto_md = generar_md(json.loads(texto_json))
    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.write_text(texto_json, encoding="utf-8")
    SALIDA_MD.write_text(texto_md, encoding="utf-8")
    # Las fichas se escriben en el momento del cambio y solo si la corrección vale; una reejecución no las repite.
    if d["resultado"]["estado"] in ("OK", "AVISO"):
        print("fichas añadidas al registro:", anadir_fichas(REGISTRO, fichas_registro(d), TITULO_FICHAS) or "ninguna")
    print("estado:", d["resultado"]["estado"], "· riesgo:", d["resultado"]["riesgo"])
    print("resumen:", d["resultado"]["resumen"])
    print("validación:", d["validacion"].get("fallos") if d.get("validacion") else "no se llegó a validar")
    print("segundos por parte:", d["duracion_por_parte"], "· total:", d["duracion_segundos"])
    return 0 if d["resultado"]["estado"] in ("OK", "AVISO") else 1


if __name__ == "__main__":
    sys.exit(main())
