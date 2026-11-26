"""Diagnóstico de calidad de las tres tablas del caso 69 (método calidad-datos), con el plan aprobado el 21/11/2026.

Lee las tres tablas de data/raw/ (venta, precios y calendario) sin alterarlas, parte del diccionario del origen y aplica
los once bloques del método en la construcción y la validación por separado. Escribe:
  - informes/calidad-datos.json, para los métodos siguientes;
  - informes/calidad-datos.md, generado de ese JSON en la misma ejecución.

Depende de config/fuentes/diccionario-datos-origen.json, que deja scripts/01_diccionario_datos.py: si su huella
de entrada no es la de data/raw/, para (resultado.md, regla 7).

Se ejecuta sin intervención manual:
  PYTHONUTF8=1 <python del entorno 69_prevision_ventas_walmart> -W error scripts/02_calidad_datos.py

Diagnostica: no corrige, no quita, no junta ni transforma datos. No guarda ninguna tabla cruzada.
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

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
DICCIONARIO = RAIZ / "config" / "fuentes" / "diccionario-datos-origen.json"
PROTECCION = RAIZ / "config" / "fuentes" / "proteccion-datos.json"
VERSION_METODO = "20/11/2026"  # versión del método calidad-datos con que se escribió este script
SALIDA_JSON = RAIZ / "informes" / "calidad-datos.json"
SALIDA_MD = RAIZ / "informes" / "calidad-datos.md"
SCRIPT_REL = "scripts/02_calidad_datos.py"

# ── 1.1 Lo que fijan las reglas del caso y el plan aprobado ──
# Fecha de referencia de los datos (reglas, apartado 5): último día que se mira antes de la prueba final.
FECHA_DATOS = "2015-05-22"
# Los dos periodos de trabajo (reglas, apartado 5). El calendario sigue hasta el 19/06/2016 a propósito.
PERIODOS = {"construccion": ("2011-01-29", "2014-05-22"), "validacion": ("2014-05-23", "2015-05-22")}
FIN_CALENDARIO = "2016-06-19"
PLAN_APROBADO = {"por": "el responsable del caso", "fecha": "2026-11-21"}
# D3 (21/11/2026): las reglas candidatas del plan son comprobaciones aprobadas con él. Es una decisión, no un cálculo.
REGLAS_CANDIDATAS_APROBADAS = True
FUENTES = {"venta": "sales_train_evaluation.csv", "precios": "sell_prices.csv", "calendario": "calendar.csv"}
IDENTIDAD_VENTA = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
# Códigos documentados en las reglas, apartado 4: departamentos, categorías, tiendas y estados.
DEPARTAMENTOS = ["FOODS_1", "FOODS_2", "FOODS_3", "HOBBIES_1", "HOBBIES_2", "HOUSEHOLD_1", "HOUSEHOLD_2"]
CATEGORIAS = ["FOODS", "HOBBIES", "HOUSEHOLD"]
TIENDAS = ["CA_1", "CA_2", "CA_3", "CA_4", "TX_1", "TX_2", "TX_3", "WI_1", "WI_2", "WI_3"]
ESTADOS = ["CA", "TX", "WI"]
DIAS_SEMANA = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
COLUMNAS_EVENTO = ["event_name_1", "event_type_1", "event_name_2", "event_type_2"]

# ── 1.2 Parámetros (parametros.md del método, con el valor del plan aprobado) ──
LIM_IQR = 1.5
LIM_Z = 3.5
K_Z = 0.6745
SEGMENTO_MINIMO = 30
FACTOR_CONCENTRACION = 2.0
RARA_PCT = 2.5
RARA_MIN = 5
CODIGO_PCT = 5.0
N_COLAS = 10
EXCEL = (20000, 60000)
RANGO_PRECIO = (0.5, 50.0)
SUBIDA_PRECIO = 2.0
VENTANA_SALTO = 91
MINIMO_SALTO = 80
UMBRAL_SALTO = 1.5
DIMENSIONES_REPARTO = ["periodo", "tienda", "estado", "departamento", "categoria"]

PARAMETROS_DE_LA_METODO = [
    "límite del rango intercuartílico", "límite del z robusto", "segmento mínimo para el reparto de nulos",
    "concentración de nulos en un segmento", "categoría rara", "código de ausencia numérico candidato",
    "colas de cada magnitud", "fecha de Excel candidata", "horizonte de fechas futuras",
]
PARAMETROS = [
    {"nombre": "límite del rango intercuartílico", "valor": LIM_IQR, "origen": "por defecto"},
    {"nombre": "límite del z robusto", "valor": LIM_Z, "origen": "por defecto"},
    {"nombre": "segmento mínimo para el reparto de nulos", "valor": SEGMENTO_MINIMO, "origen": "por defecto"},
    {"nombre": "concentración de nulos en un segmento", "valor": FACTOR_CONCENTRACION,
     "origen": "por defecto: el doble del porcentaje global"},
    {"nombre": "categoría rara", "valor": f"menos del {str(RARA_PCT).replace('.', ',')} % de las filas o menos de {RARA_MIN} apariciones",
     "origen": "por defecto, el mismo del diccionario"},
    {"nombre": "código de ausencia numérico candidato", "valor": CODIGO_PCT,
     "origen": "por defecto: un valor en un extremo del rango con ese porcentaje de las filas o más"},
    {"nombre": "colas de cada magnitud", "valor": N_COLAS,
     "origen": "por defecto; por departamento y periodo, a petición de la petición"},
    {"nombre": "fecha de Excel candidata", "valor": list(EXCEL), "origen": "por defecto; no aplica en este caso"},
    {"nombre": "horizonte de fechas futuras", "valor": FECHA_DATOS,
     "origen": "reglas de negocio §5, fecha de referencia, para la venta y los precios"},
    {"nombre": "horizonte del calendario", "valor": FIN_CALENDARIO,
     "origen": "reglas de negocio §5: llega hasta ahí a propósito; sus días posteriores no se marcan como futuros"},
    {"nombre": "dimensiones del reparto", "valor": DIMENSIONES_REPARTO, "origen": "plan aprobado, apartado 3"},
    {"nombre": "rango del precio", "valor": list(RANGO_PRECIO), "origen": "reglas de negocio §7, «Lo esperable»"},
    {"nombre": "subida de precio sospechosa", "valor": SUBIDA_PRECIO,
     "origen": "reglas de negocio §7, «Lo esperable»: un salto de más del doble de una semana a otra"},
    {"nombre": "constante del z robusto", "valor": K_Z,
     "origen": "convención del z robusto modificado de Iglewicz y Hoaglin; el método fija solo el límite"},
    {"nombre": "ventana de los saltos de nivel", "valor": VENTANA_SALTO,
     "origen": "D1, cerrada como criterio técnico el 21/11/2026: la del reconocimiento, celda 57"},
    {"nombre": "días con dato en cada ventana", "valor": MINIMO_SALTO, "origen": "D1, cerrada el 21/11/2026"},
    {"nombre": "razón de un salto de nivel", "valor": UMBRAL_SALTO,
     "origen": "D1, cerrada el 21/11/2026: después entre antes de 1,5 o más, o de 1 entre 1,5 o menos"},
]

DECISIONES_CERRADAS = [
    {"id": "D1", "fecha": "2026-11-21", "que": "la medida de los saltos de nivel",
     "cerrado": "la del reconocimiento (celda 57): media de los 91 días siguientes, el del día incluido, frente a la de "
                "los 91 anteriores, sin él; al menos 80 días con dato en cada ventana; el 25 de diciembre cuenta como "
                "día sin dato; se comparan como log((después + 1) / (antes + 1)); el salto de la serie es el día de mayor "
                "valor absoluto; es salto si después / antes es de 1,5 o más, o de 1 / 1,5 o menos. Se mide en las 70 "
                "series y en las 10 tiendas, en cada periodo por separado"},
    {"id": "D2", "fecha": "2026-11-21", "que": "los nombres y los tipos de evento con pocos días (P-01 a P-04 del diccionario)",
     "cerrado": "se dejan como están; que un evento sea raro no cambia el diagnóstico; cómo se leen se decide en las "
                "reglas de transformación"},
    {"id": "D3", "fecha": "2026-11-21", "que": "las reglas candidatas del apartado 7 del plan",
     "cerrado": "son comprobaciones aprobadas con el plan: se cuenta cada regla por separado sin cambiar ni quitar "
                "ninguna; pasarlas a las reglas de negocio va por la cascada"},
]

TEORIA = [
    {"apartado": "7.1, 7.2 y 33.1", "por_que": "el orden del diagnóstico: muestra, visión global, nulos, duplicados, "
                                               "valores únicos y estadísticos"},
    {"apartado": "7.3", "por_que": "nulos por columna, por fila y códigos de ausencia, con su reparto"},
    {"apartado": "7.4", "por_que": "duplicados exactos, sin identificadores y casi duplicados"},
    {"apartado": "7.5 y 33.10", "por_que": "valores únicos y categorías raras, solo como diagnóstico"},
    {"apartado": "7.6, 33.9 y 33.11", "por_que": "escala, colas, rango intercuartílico y z robusto con la mediana y la "
                                                  "desviación absoluta mediana; un atípico no es un error"},
    {"apartado": "14.13 y 14.15", "por_que": "fechas leídas con su formato y días que faltan en la serie"},
    {"apartado": "7.8 y 7.9", "por_que": "lo que el diagnóstico automático no ve: tiempo, cruces y negocio"},
]

# Textos que se buscan como posibles códigos de ausencia (bloque 3.4 y comprobaciones.md §4).
CODIGOS_TEXTO = ["none", "null", "n/a", "na", "nan", "-", "pendiente", "unknown", "desconocido", "sin dato", "sin_dato",
                 "?", "0000-00-00", "1900-01-01"]
CODIGOS_NUMERO = [-1, 999, 9999, 99999]


# ══ 2. Utilidades generales de la metodología ═══════════════════════════════════
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


def pct(a, b, decimales=2):
    """Porcentaje redondeado; None si el denominador es cero."""
    return round(100 * a / b, decimales) if b else None


def normalizar_nombre(nombre):
    """Nombre normalizado de una columna: minúsculas, sin tildes y con guion bajo (comprobaciones.md §9)."""
    sin_tildes = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")


def atipicos(x, lim_iqr, lim_z, k):
    """Atípicos por rango intercuartílico y por z robusto; con dispersión cero el método no marca nada y se registra."""
    x = np.asarray(x, dtype=float)
    q1, q3 = np.percentile(x, [25, 75])
    rango = q3 - q1
    mediana = float(np.median(x))
    mad = float(np.median(np.abs(x - mediana)))
    cero = []
    marca_iqr = marca_z = None
    if rango > 0:
        marca_iqr = (x < q1 - lim_iqr * rango) | (x > q3 + lim_iqr * rango)
    else:
        cero.append("iqr")
    if mad > 0:
        marca_z = np.abs(k * (x - mediana) / mad) > lim_z
    else:
        cero.append("z_robusto")
    return {
        "valores": int(x.size), "q1": float(q1), "q3": float(q3), "mediana": mediana, "mad": mad,
        "iqr": int(marca_iqr.sum()) if marca_iqr is not None else None,
        "z_robusto": int(marca_z.sum()) if marca_z is not None else None,
        "los_dos": int((marca_iqr & marca_z).sum()) if marca_iqr is not None and marca_z is not None else None,
        "limite_iqr": lim_iqr, "limite_z": lim_z, "dispersion_cero": cero,
    }


def colas(x, n):
    """Los n valores distintos más bajos y más altos, con su recuento, y el mayor salto entre dos valores seguidos."""
    valores, cuenta = np.unique(np.asarray(x), return_counts=True)
    def fila(v, c):
        """Un valor de la cola con su recuento."""
        v = round(float(v), 2) if isinstance(v, (float, np.floating)) else int(v)
        return {"valor": v, "filas": int(c)}
    bajos = [fila(v, c) for v, c in zip(valores[:n], cuenta[:n])]
    altos = [fila(v, c) for v, c in zip(valores[::-1][:n], cuenta[::-1][:n])]
    salto = None
    if len(valores) > 1:
        i = int(np.argmax(np.diff(valores)))
        salto = {"desde": fila(valores[i], 0)["valor"], "hasta": fila(valores[i + 1], 0)["valor"]}
    return {"bajos": bajos, "altos": altos, "mayor_salto": salto, "distintos": int(len(valores))}


def escala(x):
    """Cuántos valores tienen 1, 2, 3… cifras enteras; salto si falta un número de cifras entre el menor y el mayor."""
    enteros = np.floor(np.abs(np.asarray(x, dtype=float)))
    cifras = np.ones(enteros.shape, dtype=int)
    for potencia in range(1, 13):
        cifras += enteros >= 10 ** potencia
    numeros, cuenta = np.unique(cifras, return_counts=True)
    presentes = [int(v) for v in numeros]
    huecos = [c for c in range(min(presentes), max(presentes) + 1) if c not in presentes] if presentes else []
    salto = bool(huecos)
    factor = None
    if salto:
        bajo = np.median(np.asarray(x, float)[cifras == min(presentes)])
        alto = np.median(np.asarray(x, float)[cifras == max(presentes)])
        factor = round(float(alto / bajo), 2) if bajo else None
    return {"cifras": {str(int(v)): int(c) for v, c in zip(numeros, cuenta)}, "salto": salto, "factor": factor,
            "factor_uniforme": False if salto else None}


def reparto(es_nulo, dimensiones, minimo=SEGMENTO_MINIMO, factor=FACTOR_CONCENTRACION):
    """Porcentaje de vacíos global y por segmento de cada dimensión, con el veredicto del método (bloque 3.4)."""
    es_nulo = np.asarray(es_nulo, dtype=bool).ravel()
    global_pct = round(100 * es_nulo.mean(), 2) if es_nulo.size else None
    segmentos, evaluables, concentrado = [], 0, False
    for dim, etiquetas in dimensiones.items():
        tabla = pd.DataFrame({"seg": np.asarray(etiquetas).ravel(), "nulo": es_nulo}).groupby("seg")["nulo"].agg(["sum", "size"])
        for seg, fila in tabla.iterrows():
            filas, nulos = int(fila["size"]), int(fila["sum"])
            p = round(100 * nulos / filas, 2)
            concentra = bool(filas >= minimo and global_pct and p >= factor * global_pct)
            evaluables += filas >= minimo
            concentrado |= concentra
            segmentos.append({"dimension": dim, "segmento": str(seg), "filas": filas, "nulos": nulos, "pct": p,
                              "concentra": concentra})
    if not es_nulo.any():
        veredicto = "sin_nulos"
    elif evaluables == 0:
        veredicto = "no_se_puede_saber"
    elif concentrado:
        veredicto = "concentrados"
    else:
        veredicto = "repartidos"
    return {"global_pct": global_pct, "nulos": int(es_nulo.sum()), "filas": int(es_nulo.size),
            "dimensiones": list(dimensiones), "veredicto": veredicto,
            "doble_alcanzable": bool(global_pct is not None and factor * global_pct <= 100), "segmentos": segmentos}


def racha_mas_larga(mascara):
    """Número de días seguidos más largo en que la máscara es verdadera."""
    mejor = actual = 0
    for v in np.asarray(mascara, dtype=bool):
        actual = actual + 1 if v else 0
        mejor = max(mejor, actual)
    return mejor


# ══ 3. Comprobaciones propias del caso ═══════════════════════════════════════════
def mayor_salto_nivel(M, sin_dato, ventana=VENTANA_SALTO, minimo=MINIMO_SALTO, umbral=UMBRAL_SALTO):
    """Medida D1 (reconocimiento, celda 57): día y tamaño del mayor cambio de nivel de cada fila de M (series x días).

    Antes: media de los `ventana` días anteriores, sin el día. Después: media de los `ventana` siguientes, con él. Cada
    ventana pide `minimo` días con dato; los días de `sin_dato` (el 25 de diciembre) cuentan como sin dato.
    """
    X = pd.DataFrame(np.where(np.asarray(sin_dato, bool)[None, :], np.nan, np.asarray(M, float)).T)
    antes = X.rolling(ventana, min_periods=minimo).mean().shift(1)
    despues = X[::-1].rolling(ventana, min_periods=minimo).mean()[::-1]
    lr = np.log((despues + 1) / (antes + 1)).abs()
    filas = []
    for s in range(X.shape[1]):
        col = lr.iloc[:, s].to_numpy()
        if not np.isnan(col).all():
            t = int(np.nanargmax(col))
            a, b = float(antes.iat[t, s]), float(despues.iat[t, s])
            razon = b / a if a > 0 else None
            salto = bool(razon is not None and (razon >= umbral or razon <= 1 / umbral))
            filas.append({"dia": t + 1, "antes": a, "despues": b, "razon": razon, "salto": salto})
        else:
            filas.append({"dia": None, "antes": None, "despues": None, "razon": None, "salto": False})
    return pd.DataFrame(filas, dtype=object)


def saltos_por_periodo(M, sin_dato, mascaras):
    """La medida D1 en cada periodo por separado: ninguna ventana toma días del otro periodo."""
    return {nombre: mayor_salto_nivel(np.asarray(M)[:, m], np.asarray(sin_dato)[m]) for nombre, m in mascaras.items()}


def cierres_de_tienda(S):
    """Cierre: la tienda vende cero ese día en sus siete departamentos (reglas, apartado 5). S es tiendas x días."""
    return np.asarray(S) == 0


def semanas_con_venta_sin_precio(W, P):
    """Máscara de las semanas producto-tienda con unidades vendidas y sin fila de precio (reglas, apartado 5: para el trabajo)."""
    return (np.asarray(W) > 0) & np.isnan(np.asarray(P, float))


def huecos_de_precio(P):
    """Semanas sin precio entre la primera y la última con precio de cada producto-tienda, y si llega al final."""
    tiene = ~np.isnan(np.asarray(P, float))
    con = tiene.any(axis=1)
    n = tiene.shape[1]
    primera = np.where(con, tiene.argmax(axis=1), -1)
    ultima = np.where(con, n - 1 - tiene[:, ::-1].argmax(axis=1), -1)
    faltan = int(sum((ultima[i] - primera[i] + 1) - tiene[i].sum() for i in np.flatnonzero(con)))
    return {"con_precio": int(con.sum()), "semanas_que_faltan": faltan,
            "no_llegan_al_final": int((con & (ultima != n - 1)).sum()), "primera": primera, "ultima": ultima}


def subidas_de_precio(P, factor):
    """Máscara (productos-tienda x semanas) de los precios que pasan de más de `factor` veces el de la semana anterior."""
    P = np.asarray(P, float)
    salida = np.zeros(P.shape, dtype=bool)
    ambos = ~np.isnan(P[:, 1:]) & ~np.isnan(P[:, :-1])
    razon = np.ones(ambos.shape)
    razon[ambos] = P[:, 1:][ambos] / P[:, :-1][ambos]
    salida[:, 1:] = ambos & (razon > factor)
    return salida


def snap_que_cambia(dia_del_mes, snap):
    """Días del calendario cuyo SNAP no es el valor más frecuente de su día del mes (regla candidata)."""
    t = pd.DataFrame({"dia": dia_del_mes, "snap": snap})
    moda = t.groupby("dia")["snap"].agg(lambda s: s.value_counts().index[0])
    return int((t["snap"].to_numpy() != t["dia"].map(moda).to_numpy()).sum())


def nombres_con_mas_de_un_tipo(pares):
    """Nombres de evento que aparecen con más de un tipo."""
    n = pares.dropna().groupby("nombre")["tipo"].nunique()
    return sorted(n[n > 1].index.tolist())


def paradas(negativos, semanas_sin_precio):
    """Las reglas, apartado 5 que paran el trabajo: una venta negativa o una semana con venta y sin precio."""
    salida = []
    if negativos:
        salida.append({"regla": "reglas, apartado 5: una venta negativa sería imposible", "filas": int(negativos)})
    if semanas_sin_precio:
        salida.append({"regla": "reglas, apartado 5: una semana con venta y sin precio es un error de los datos",
                       "filas": int(semanas_sin_precio)})
    return salida


def textos_navidad(unidades_por_ano, cerrados, tiendas):
    """Observación y pregunta del 25 de diciembre, con lo que miden los datos.

    No copian el texto de las reglas, apartado 5, que cambió el 24/11/2026: una copia se queda vieja sin avisar
    (error 16). `cerrados` son los días de tienda del 25 de diciembre con la tienda entera a cero; un día de tienda es
    una tienda en un 25 de diciembre, así que hay `tiendas` por cada año.
    """
    anos = len(unidades_por_ano)
    dias = tiendas * anos
    abiertos = dias - cerrados
    cuenta = f"{fmt(tiendas)} tiendas en {fmt(anos)} años"
    observacion = (f"en {fmt(cerrados)} de los {fmt(dias)} días de tienda del 25 de diciembre ({cuenta}) la tienda entera "
                   f"vende cero, que es un cierre según las reglas, apartado 5. Las unidades se venden en los otros "
                   f"{fmt(abiertos)} días de tienda")
    pregunta = (f"El 25 de diciembre suma {fmt(sum(unidades_por_ano.values()))} unidades en {fmt(anos)} años. Esas "
                f"unidades se venden en {fmt(abiertos)} de los {fmt(dias)} días de tienda de esa fecha ({cuenta}); en los "
                f"otros {fmt(cerrados)}, la tienda entera vende cero. ¿Cómo se leen las unidades del 25 de diciembre?")
    return {"observacion": observacion, "pregunta": pregunta}


def estado_y_riesgo(fallos, paros, pendientes):
    """Estado del bloque común: ERROR si falla la validación, PARADO por las reglas, AVISO con pendientes."""
    if fallos:
        return "ERROR", "alto"
    if paros:
        return "PARADO", "alto"
    if pendientes:
        return "AVISO", "medio"
    return "OK", "bajo"


# ══ 4. Validación en código (método, apartado 6: comprobaciones 6, 7, 9 y 10) ══════════════
def validar(d):
    """Devuelve las comprobaciones que fallan. Cada una se calcula con lo que se ejecutó."""
    fallos = []
    con_veredicto = {(n["tabla"], n["columna"]) for n in d.get("nulos_por_segmento", [])
                     if n.get("veredicto") in ("sin_nulos", "repartidos", "concentrados", "no_se_puede_saber")}
    sin = [f"{c['tabla']}.{c['columna']}" for c in d.get("columnas_con_vacios", []) if (c["tabla"], c["columna"]) not in con_veredicto]
    if sin:
        fallos.append({"comprobacion": "6 · cada variable con ausencias tiene su veredicto de reparto", "detalle": sin})
    rotos = [f"{c['izquierda']}-{c['derecha']}" for c in d.get("cruces", [])
             if not isinstance(c.get("sin_pareja_izquierda"), int) or not isinstance(c.get("sin_pareja_derecha"), int)]
    if rotos or not d.get("cruces"):
        fallos.append({"comprobacion": "7 · cada relación tiene sus claves sin pareja en los dos lados", "detalle": rotos})
    distintas = [e["ruta"] for e in d.get("entradas", []) if d.get("huellas_despues", {}).get(e["ruta"]) != e["sha256"]]
    if distintas or not d.get("entradas"):
        fallos.append({"comprobacion": "9 · data/raw/ intacto: la huella es igual antes y después", "detalle": distintas})
    faltan = []
    for mg in d.get("magnitudes", []):
        for clave in ("escala", "colas"):
            n = sum(1 for e in d.get(clave, []) if e["tabla"] == mg["tabla"] and e["columna"] == mg["columna"])
            if n < mg["grupos"]:
                faltan.append(f"{clave} de {mg['tabla']}.{mg['columna']}: {n} de {mg['grupos']}")
    nombres = {p["nombre"] for p in d.get("parametros", [])}
    faltan += [f"parámetro {p}" for p in PARAMETROS_DE_LA_METODO if p not in nombres]
    if faltan or not d.get("magnitudes"):
        fallos.append({"comprobacion": "10 · cada magnitud tiene su escala y sus colas; el JSON lleva los parámetros",
                       "detalle": faltan})
    return fallos


def aplicar_validacion(d):
    """Escribe en d el resultado de la validación y, si algo falla, pone el estado en ERROR."""
    fallos = validar(d)
    d["validacion"] = {
        "comprobaciones": ["6 · cada variable con ausencias tiene su veredicto de reparto",
                           "7 · cada relación tiene sus claves sin pareja en los dos lados",
                           "9 · data/raw/ intacto: la huella es igual antes y después",
                           "10 · cada magnitud tiene su escala y sus colas; el JSON lleva los parámetros"],
        "fallos": fallos,
    }
    if fallos:
        d["resultado"]["estado"], d["resultado"]["riesgo"] = "ERROR", "alto"
        d["resultado"]["resumen"] = "La validación del script falló: " + "; ".join(f["comprobacion"] for f in fallos) + "."
    return fallos


# ══ 5. Lectura ═══════════════════════════════════════════════════════════════════
def leer_tablas():
    """Lee las tres tablas enteras como dice el diccionario: utf-8, coma, solo el campo vacío es nulo; tipos fijados."""
    comun = dict(encoding="utf-8", sep=",", keep_default_na=False, na_values=[""])
    cabecera = pd.read_csv(RAW / FUENTES["venta"], nrows=0, **comun).columns
    tipos = {c: ("str" if c in IDENTIDAD_VENTA else "int64") for c in cabecera}
    venta = pd.read_csv(RAW / FUENTES["venta"], dtype=tipos, **comun)
    precios = pd.read_csv(RAW / FUENTES["precios"], dtype={"store_id": "str", "item_id": "str", "wm_yr_wk": "int64",
                                                            "sell_price": "float64"}, **comun)
    calendario = pd.read_csv(RAW / FUENTES["calendario"], dtype={
        "date": "str", "wm_yr_wk": "int64", "weekday": "str", "wday": "int64", "month": "int64", "year": "int64",
        "d": "str", "event_name_1": "str", "event_type_1": "str", "event_name_2": "str", "event_type_2": "str",
        "snap_CA": "int64", "snap_TX": "int64", "snap_WI": "int64"}, **comun)
    return venta, precios, calendario


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def esqueleto():
    """Todas las claves del JSON, vacías; construir() las llena y la prueba genera con él un informe mínimo."""
    return {
        "metodo": "calidad-datos", "version_metodo": None, "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": None, "entorno": {}, "entradas": [], "huellas_despues": {},
        "resultado": {"estado": None, "riesgo": None, "resumen": "", "artefactos": ["informes/calidad-datos.json",
                                                                                     "informes/calidad-datos.md"],
                      "siguiente": "correccion-datos, con otra petición, después de que la sesión principal revise este JSON"},
        "pendientes": [], "con_diccionario": False, "diccionario": {}, "plan_aprobado": PLAN_APROBADO,
        "decisiones_cerradas": DECISIONES_CERRADAS, "periodos": {}, "teoria_aplicada": TEORIA,
        "inspeccion": {}, "estructura": {}, "tipos": [], "escala": [], "escala_precio_bajo": {},
        "codigos_buscados": [], "codigos_de_ausencia": [], "vacios_por_fila": [], "columnas_con_vacios": [],
        "nulos_por_segmento": [], "semana_sin_precio": {}, "duplicados": [], "claves_y_granularidad": [],
        "categorias": {}, "categorias_raras": [], "nombres": [], "magnitudes": [], "outliers": [], "colas": [],
        "fechas": [], "comprobaciones_reglas": [], "reconocimiento": [], "saltos_de_nivel": {}, "reglas_candidatas": [],
        "cruces": [], "riesgos_modelo": [], "problemas": [], "instrucciones_en_texto": [], "datos_personales": [],
        "datos_personales_nota": "", "no_aplicado": [], "limites": [], "parametros": PARAMETROS,
        "cifras_de_control": {}, "validacion": {}, "duracion_segundos": None,
    }


# ══ 6. Construcción del diagnóstico ══════════════════════════════════════════════
def construir():
    """Lee las tres tablas, aplica los once bloques y devuelve el diccionario de resultados, ya validado."""
    inicio = time.time()
    d = esqueleto()
    d["fecha_ejecucion"] = datetime.now().isoformat(timespec="seconds")
    d["version_metodo"] = version_metodo()
    d["entorno"] = {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                    "ejecutable": sys.executable}
    d["periodos"] = {k: {"desde": v[0], "hasta": v[1]} for k, v in PERIODOS.items()}
    huellas_antes = {f"data/raw/{f}": huella(RAW / f) for f in FUENTES.values()}

    # ── 6.1 Al empezar: el diccionario del origen (resultado.md) ──
    # Si para o describe otra fuente, este script no empieza: la cadena se repite desde diccionario-datos.
    dic = json.loads(DICCIONARIO.read_text(encoding="utf-8"))
    huellas_dic = {e["ruta"]: e["sha256"] for e in dic["entradas"]}
    d["diccionario"] = {"ruta": "config/fuentes/diccionario-datos-origen.json",
                        "estado": dic["resultado"]["estado"], "fecha_ejecucion": dic["fecha_ejecucion"],
                        "misma_huella": huellas_dic == huellas_antes}
    if dic["resultado"]["estado"] in ("PARADO", "ERROR") or huellas_dic != huellas_antes:
        d["resultado"].update(estado="PARADO", riesgo="alto",
                              resumen="El diccionario del origen paró o describe otra fuente: se repite la cadena desde diccionario-datos.",
                              siguiente="ejecutar scripts/01_diccionario_datos.py y después este script")
        d["entradas"] = [{"ruta": r, "sha256": h} for r, h in huellas_antes.items()]
        d["huellas_despues"] = huellas_antes
        return d
    d["con_diccionario"] = True
    tdic = {t["tabla"]: t for t in dic["tablas"]}
    campo_dic = {(t["tabla"], c["columna"]): c for t in dic["tablas"] for c in t["campos"]}

    # ── 6.2 Lectura y piezas comunes ──
    venta, precios, cal = leer_tablas()
    d["entradas"] = [{"ruta": f"data/raw/{FUENTES[n]}", "sha256": huellas_antes[f"data/raw/{FUENTES[n]}"],
                      "bytes": (RAW / FUENTES[n]).stat().st_size, "filas": int(df.shape[0]), "columnas": int(df.shape[1])}
                     for n, df in (("venta", venta), ("precios", precios), ("calendario", cal))]
    dias = [c for c in venta.columns if c not in IDENTIDAD_VENTA]
    Y = venta[dias].to_numpy(np.int64)
    fechas_cal = pd.to_datetime(cal["date"], format="%Y-%m-%d")
    fecha_de_d = dict(zip(cal["d"], fechas_cal))
    semana_de_d = dict(zip(cal["d"], cal["wm_yr_wk"]))
    fecha_dia = pd.DatetimeIndex([fecha_de_d[c] for c in dias])
    sem_dia = np.array([semana_de_d[c] for c in dias])
    ini_c, fin_c = (pd.Timestamp(x) for x in PERIODOS["construccion"])
    ini_v, fin_v = (pd.Timestamp(x) for x in PERIODOS["validacion"])
    m_periodo = {"construccion": np.asarray((fecha_dia >= ini_c) & (fecha_dia <= fin_c)),
                 "validacion": np.asarray((fecha_dia >= ini_v) & (fecha_dia <= fin_v))}
    navidad = np.asarray((fecha_dia.month == 12) & (fecha_dia.day == 25))
    ultima_sem_c = int(cal.loc[fechas_cal == fin_c, "wm_yr_wk"].iloc[0])
    # Semanas de la venta, en el orden de los días; cada una es un bloque de días seguidos.
    cambios = np.r_[0, np.flatnonzero(np.diff(sem_dia)) + 1]
    semanas = sem_dia[cambios]
    W = np.add.reduceat(Y, cambios, axis=1)
    hasta = semanas <= ultima_sem_c
    ETQ_HASTA, ETQ_DESPUES = f"hasta la semana {ultima_sem_c}", f"después de la semana {ultima_sem_c}"
    etiqueta_semana = np.where(hasta, ETQ_HASTA, ETQ_DESPUES)
    clave_venta = pd.MultiIndex.from_frame(venta[["item_id", "store_id"]])
    P = (precios.pivot(index=["item_id", "store_id"], columns="wm_yr_wk", values="sell_price")
         .reindex(index=clave_venta, columns=semanas).to_numpy())
    dept_fila, cat_fila = venta["dept_id"].to_numpy(), venta["cat_id"].to_numpy()
    tienda_fila, estado_fila = venta["store_id"].to_numpy(), venta["state_id"].to_numpy()
    # Venta de cada tienda (suma de sus siete departamentos) y de cada una de las 70 series.
    S_df = pd.DataFrame(Y).groupby(tienda_fila).sum()
    S, tiendas = S_df.to_numpy(), list(S_df.index)
    clave_serie = ["state_id", "store_id", "cat_id", "dept_id"]
    U_df = pd.DataFrame(Y).groupby([venta[c].to_numpy() for c in clave_serie]).sum()
    U = U_df.to_numpy()
    series = [f"{i[1]} {i[3]}" for i in U_df.index]
    tienda_serie = np.array([tiendas.index(i[1]) for i in U_df.index])
    dept_serie = np.array([i[3] for i in U_df.index])
    cierre = cierres_de_tienda(S)

    # ── 6.3 Bloque 3.1 · Inspección general: lo que el diccionario no trae ──
    def muestra(s):
        """Tres valores de muestra: primera fila, fila del medio y última (ninguno es dato personal, reglas, apartado 9)."""
        n = len(s)
        return [a_json_limpio(s.iloc[i]) for i in (0, n // 2, n - 1)]
    muestras = {"venta": {c: muestra(venta[c]) for c in IDENTIDAD_VENTA},
                "precios": {c: muestra(precios[c]) for c in precios.columns},
                "calendario": {c: muestra(cal[c]) for c in cal.columns}}
    muestras["venta"]["d_1 a d_1575"] = [int(Y[0, 0]), int(Y[len(Y) // 2, Y.shape[1] // 2]), int(Y[-1, -1])]
    tramo_cal = np.where(fechas_cal <= fin_c, "construccion", np.where(fechas_cal <= fin_v, "validacion", "despues"))
    cobertura = {
        "venta": {p: {"desde": fecha_dia[m].min().date().isoformat(), "hasta": fecha_dia[m].max().date().isoformat(),
                      "dias": int(m.sum()), "primera_columna": dias[int(np.flatnonzero(m)[0])],
                      "ultima_columna": dias[int(np.flatnonzero(m)[-1])]} for p, m in m_periodo.items()},
        "precios": {lab: {"semana_minima": int(semanas[hasta == h].min()), "semana_maxima": int(semanas[hasta == h].max()),
                          "semanas": int((hasta == h).sum()),
                          "filas": int(((precios["wm_yr_wk"] <= ultima_sem_c) == h).sum())}
                    for lab, h in ((ETQ_HASTA, True), (ETQ_DESPUES, False))},
        "calendario": {t: {"desde": fechas_cal[tramo_cal == t].min().date().isoformat(),
                           "hasta": fechas_cal[tramo_cal == t].max().date().isoformat(), "dias": int((tramo_cal == t).sum())}
                       for t in ("construccion", "validacion", "despues")},
    }
    dias_sem_ultima = int((sem_dia == ultima_sem_c).sum())
    dias_sem_ultima_c = int(((sem_dia == ultima_sem_c) & m_periodo["construccion"]).sum())
    d["inspeccion"] = {
        "del_diccionario": {t: {"filas": tdic[t]["filas"], "columnas": tdic[t]["columnas"], "clave": tdic[t]["clave"],
                                "clave_unica": tdic[t]["clave_unica"]} for t in tdic},
        "muestras": muestras, "cobertura": cobertura,
        "semana_que_cruza": {"semana": ultima_sem_c, "dias_en_construccion": dias_sem_ultima_c,
                             "dias_en_validacion": dias_sem_ultima - dias_sem_ultima_c},
    }

    # ── 6.4 Bloque 3.2 · Estructura: forma de la tabla y nombres de columna ──
    prefijo = venta["item_id"] + "_" + venta["store_id"] + "_"
    id_doble = int(sum(i.startswith(p) for i, p in zip(venta["id"], prefijo)))
    anidadas = {f"{t}.{c}": int(df[c].dropna().astype(str).str.match(r"^\s*[\[{]").sum())
                for t, df in (("venta", venta[IDENTIDAD_VENTA]), ("precios", precios), ("calendario", cal))
                for c in df.columns if pd.api.types.is_string_dtype(df[c])}
    vacias = [f"{t}.{c['columna']}" for t in tdic for c in tdic[t]["campos"] if c["nulos"] == c["filas"]]
    constantes = [f"{t}.{c['columna']}" for t in tdic for c in tdic[t]["campos"] if c["distintos"] <= 1]
    d["estructura"] = {
        "forma": [
            {"tabla": "venta", "rasgo": "periodos repartidos en columnas", "resultado": len(dias),
             "detalle": f"una columna por día, de {dias[0]} a {dias[-1]}"},
            {"tabla": "venta", "rasgo": "columna doble", "columna": "id", "filas": id_doble, "pct": pct(id_doble, len(venta)),
             "detalle": "id es item_id, store_id y un sufijo, unidos por guion bajo",
             "sufijo": tdic["venta"]["relaciones_medidas"]["sufijo_de_id"]},
            {"tabla": "todas", "rasgo": "celdas que empiezan como una lista o un JSON", "resultado": int(sum(anidadas.values()))},
        ],
        "columnas_vacias": vacias, "columnas_constantes": constantes,
        "columnas_de_dias_fuera_del_bloque": len(tdic["venta"]["bloque_dias"]["fuera_del_bloque"]),
        "avisos_de_lectura": {t: tdic[t]["lectura"]["avisos"] for t in tdic},
    }
    todas_columnas = [("venta", c) for c in venta.columns] + [("precios", c) for c in precios.columns] + \
                     [("calendario", c) for c in cal.columns]
    normal = {}
    for t, c in todas_columnas:
        normal.setdefault((t, normalizar_nombre(c)), []).append(c)
    nombres = []
    for t, c in todas_columnas:
        raro = c != normalizar_nombre(c)
        choca = [x for x in normal[(t, normalizar_nombre(c))] if x != c]
        if raro or choca:
            nombres.append({"tabla": t, "columna": c, "normalizado": normalizar_nombre(c),
                            "motivo": "mayúsculas, tildes, espacios o símbolos" if raro else "",
                            "colision_con": ", ".join(choca)})
    d["nombres"] = nombres

    # ── 6.5 Bloque 3.3 · Tipos y formatos ──
    fechas_no = int(pd.to_datetime(cal["date"], format="%Y-%m-%d", errors="coerce").isna().sum())
    d_no = int((~cal["d"].str.fullmatch(r"d_\d+")).sum())
    tipos = []
    for c in IDENTIDAD_VENTA:
        tipos.append({"tabla": "venta", "columna": c, "leido": campo_dic[("venta", c)]["tipo_leido"],
                      "rol": campo_dic[("venta", c)]["rol"], "toca": "texto", "pct_no_convierte": 0.0,
                      "muestra": muestras["venta"][c], "aviso": None})
    tipos.append({"tabla": "venta", "columna": "d_1 a d_1575", "leido": "int64", "rol": "magnitud", "toca": "entero",
                  "pct_no_convierte": 0.0, "muestra": muestras["venta"]["d_1 a d_1575"], "aviso": None})
    for c in precios.columns:
        rol = campo_dic[("precios", c)]["rol"]
        tipos.append({"tabla": "precios", "columna": c, "leido": campo_dic[("precios", c)]["tipo_leido"], "rol": rol,
                      "toca": {"magnitud": "decimal", "codigo": "código (semana)"}.get(rol, "texto"),
                      "pct_no_convierte": 0.0, "muestra": muestras["precios"][c],
                      "aviso": "codigo_numerico" if rol == "codigo" else None})
    for c in cal.columns:
        rol = campo_dic[("calendario", c)]["rol"]
        toca = {"fecha": "fecha", "codigo": "código", "booleana": "booleano"}.get(rol, "texto")
        no_conv = {"date": pct(fechas_no, len(cal)), "d": pct(d_no, len(cal))}.get(c, 0.0)
        if rol == "booleana":
            no_conv = pct(int((~cal[c].isin([0, 1])).sum()), len(cal))
        aviso = {"fecha": "fecha_como_texto", "codigo": "codigo_numerico", "booleana": "booleano_enmascarado"}.get(rol)
        if c == "d":
            aviso = "texto_con_numero"
        tipos.append({"tabla": "calendario", "columna": c, "leido": campo_dic[("calendario", c)]["tipo_leido"], "rol": rol,
                      "toca": toca, "pct_no_convierte": no_conv, "muestra": muestras["calendario"][c], "aviso": aviso})
    d["tipos"] = tipos

    # Escala, colas y atípicos de las dos magnitudes, por departamento y periodo, y en total (bloques 3.3 y 3.8).
    precio = precios["sell_price"].to_numpy()
    dept_de_item = dict(zip(venta["item_id"], venta["dept_id"]))
    dept_precio = precios["item_id"].map(dept_de_item).to_numpy()
    hasta_precio = (precios["wm_yr_wk"] <= ultima_sem_c).to_numpy()
    grupos = ["total"] + DEPARTAMENTOS
    escalas, colas_l, outl = [], [], []
    for g in grupos:
        filas_g = np.ones(len(venta), bool) if g == "total" else dept_fila == g
        for p, m in m_periodo.items():
            x = Y[np.ix_(filas_g, m)].ravel()
            base = {"tabla": "venta", "columna": "unidades (d_1 a d_1575)", "grupo": g, "periodo": p}
            escalas.append({**base, **escala(x)})
            colas_l.append({**base, **colas(x, N_COLAS)})
            outl.append({**base, **atipicos(x, LIM_IQR, LIM_Z, K_Z)})
        filas_p = np.ones(len(precios), bool) if g == "total" else dept_precio == g
        for lab, hh in ((ETQ_HASTA, True), (ETQ_DESPUES, False)):
            x = precio[filas_p & (hasta_precio == hh)]
            base = {"tabla": "precios", "columna": "sell_price", "grupo": g, "periodo": lab}
            escalas.append({**base, **escala(x)})
            colas_l.append({**base, **colas(x, N_COLAS)})
            outl.append({**base, **atipicos(x, LIM_IQR, LIM_Z, K_Z)})
    d["escala"], d["colas"], d["outliers"] = escalas, colas_l, outl
    d["magnitudes"] = [{"tabla": "venta", "columna": "unidades (d_1 a d_1575)", "grupos": len(grupos) * 2},
                       {"tabla": "precios", "columna": "sell_price", "grupos": len(grupos) * 2}]

    # Precio por debajo de 0,5: ¿escala perdida? Se compara cada precio bajo con la mediana de su producto-tienda.
    bajo = precio < RANGO_PRECIO[0]
    clave_p = precios["item_id"] + "|" + precios["store_id"]
    mediana_pt = precios.groupby(clave_p.to_numpy())["sell_price"].transform("median").to_numpy()
    todos_bajos = pd.Series(bajo).groupby(clave_p.to_numpy()).transform("all").to_numpy()
    razon_bajo = mediana_pt[bajo] / precio[bajo]
    pt_bajo = clave_p[bajo].nunique()
    d["escala_precio_bajo"] = {
        "filas": int(bajo.sum()), "productos_tienda": int(pt_bajo),
        "filas_en_productos_tienda_siempre_por_debajo": int((bajo & todos_bajos).sum()),
        "productos_tienda_siempre_por_debajo": int(clave_p[bajo & todos_bajos].nunique()),
        "filas_en_productos_tienda_con_otros_precios": int((bajo & ~todos_bajos).sum()),
        "razon_mediana_entre_precio": {"minima": round(float(razon_bajo.min()), 2),
                                       "mediana": round(float(np.median(razon_bajo)), 2),
                                       "maxima": round(float(razon_bajo.max()), 2)},
        "filas_con_razon_cerca_de_10_o_100": int(((np.abs(razon_bajo - 10) <= 1) | (np.abs(razon_bajo - 100) <= 10)).sum()),
        "por_departamento": {g: int((bajo & (dept_precio == g)).sum()) for g in DEPARTAMENTOS},
        "por_periodo": {ETQ_HASTA: int((bajo & hasta_precio).sum()), ETQ_DESPUES: int((bajo & ~hasta_precio).sum())},
    }

    # ── 6.6 Bloque 3.4 · Valores ausentes ──
    # Textos y números que podrían ser códigos de ausencia, en todas las columnas de las tres tablas.
    buscados = []
    for t, df in (("venta", venta[IDENTIDAD_VENTA]), ("precios", precios), ("calendario", cal)):
        for c in df.columns:
            if pd.api.types.is_string_dtype(df[c]):
                s = df[c].dropna().astype(str)
                bajo_t = s.str.strip().str.lower()
                for cod in CODIGOS_TEXTO:
                    n = int((bajo_t == cod).sum())
                    if n:
                        buscados.append({"tabla": t, "columna": c, "codigo": cod, "filas": n})
                n = int((s.str.strip() == "").sum())
                if n:
                    buscados.append({"tabla": t, "columna": c, "codigo": "cadena de espacios", "filas": n})
    for t, c, x in (("venta", "unidades (d_1 a d_1575)", Y.ravel()), ("precios", "sell_price", precio)):
        for cod in CODIGOS_NUMERO:
            n = int((x == cod).sum())
            if n:
                buscados.append({"tabla": t, "columna": c, "codigo": str(cod), "filas": n})
    d["codigos_buscados"] = {"textos": CODIGOS_TEXTO, "numeros": CODIGOS_NUMERO, "hallados": buscados}

    codigos = []
    for k in ("1", "2"):
        for c in (f"event_name_{k}", f"event_type_{k}"):
            n = campo_dic[("calendario", c)]["nulos"]
            otra = f"event_type_{k}" if "name" in c else f"event_name_{k}"
            descuadre = tdic["calendario"]["relaciones_medidas"][f"filas_con_nombre_y_tipo_del_evento_{k}_descuadrados"]
            codigos.append({"tabla": "calendario", "columna": c, "codigo": "vacío", "tipo": "texto", "filas": n,
                            "pct_filas": campo_dic[("calendario", c)]["nulos_pct"], "documentado": True,
                            "coincide_con": "sin evento (reglas, apartado 5)",
                            "mismas_filas_que": [otra] if descuadre == 0 else [], "periodo": "todo el calendario"})
    # El cero de la venta: extremo del rango con más del 5 % de las celdas; documentado como dato válido (reglas, apartado 5).
    sin_precio_dia = np.isnan(P)[:, np.searchsorted(semanas, sem_dia)]
    for p, m in m_periodo.items():
        bp = tdic["venta"]["por_periodo"][p]
        ceros = Y[:, m] == 0
        en_sin_precio = int((ceros & sin_precio_dia[:, m]).sum())
        codigos.append({"tabla": "venta", "columna": "unidades (d_1 a d_1575)", "codigo": "0", "tipo": "numerico",
                        "filas": bp["celdas_a_cero"], "pct_filas": bp["celdas_a_cero_pct"], "documentado": True,
                        "coincide_con": f"{fmt(en_sin_precio)} de esas celdas caen en una semana sin fila de precio "
                                        f"({fmt(pct(en_sin_precio, bp['celdas_a_cero']))} %)",
                        "celdas_en_semana_sin_precio": en_sin_precio, "mismas_filas_que": [], "periodo": p})
    candidatos = []
    for e in colas_l:
        if e["grupo"] != "total":
            continue
        total = next(o["valores"] for o in outl if o["tabla"] == e["tabla"] and o["grupo"] == "total"
                     and o["periodo"] == e["periodo"])
        for lado, v in (("mínimo", e["bajos"][0]), ("máximo", e["altos"][0])):
            candidatos.append({"tabla": e["tabla"], "columna": e["columna"], "periodo": e["periodo"], "extremo": lado,
                               "valor": v["valor"], "filas": v["filas"], "pct": pct(v["filas"], total),
                               "candidato": bool(pct(v["filas"], total) >= CODIGO_PCT)})
    d["codigos_de_ausencia"] = codigos
    d["codigos_numericos_candidatos"] = candidatos

    # Vacíos por fila (comprobaciones.md §8); sin las columnas de evento, cuyo vacío es «sin evento» (reglas, apartado 5).
    vac_cal = cal.isna().sum(axis=1).value_counts().sort_index()
    vac_cal_sin = cal.drop(columns=COLUMNAS_EVENTO).isna().sum(axis=1).value_counts().sort_index()
    d["vacios_por_fila"] = [
        {"tabla": "venta", "con_todas": {"0": len(venta)}, "sin_casi_vacias": {"0": len(venta)}, "excluidas": [],
         "fuente": "diccionario: 0 vacíos en las 1.581 columnas"},
        {"tabla": "precios", "con_todas": {"0": len(precios)}, "sin_casi_vacias": {"0": len(precios)}, "excluidas": [],
         "fuente": "diccionario: 0 vacíos en las 4 columnas"},
        {"tabla": "calendario", "con_todas": {str(k): int(v) for k, v in vac_cal.items()},
         "sin_casi_vacias": {str(k): int(v) for k, v in vac_cal_sin.items()}, "excluidas": COLUMNAS_EVENTO,
         "fuente": "calculado; las cuatro columnas de evento se excluyen por las reglas, apartado 5"},
    ]

    # Reparto de los vacíos: los cuatro de evento por periodo; la semana sin precio por las cinco dimensiones del plan.
    nps, con_vacios = [], []
    for c in COLUMNAS_EVENTO:
        r = reparto(cal[c].isna().to_numpy(), {"periodo": tramo_cal})
        nps.append({"tabla": "calendario", "columna": c, **r})
        con_vacios.append({"tabla": "calendario", "columna": c})
    falta = np.isnan(P)
    filas_r = np.repeat(np.arange(len(venta)), len(semanas))
    rep_precio = reparto(falta.ravel(), {"periodo": np.tile(etiqueta_semana, len(venta)), "tienda": tienda_fila[filas_r],
                                "estado": estado_fila[filas_r], "departamento": dept_fila[filas_r],
                                "categoria": cat_fila[filas_r]})
    nps.append({"tabla": "precios", "columna": "sell_price (semana sin fila)", **rep_precio})
    con_vacios.append({"tabla": "precios", "columna": "sell_price (semana sin fila)"})
    d["nulos_por_segmento"], d["columnas_con_vacios"] = nps, con_vacios
    h = huecos_de_precio(P)
    sin_ninguno = ~(~falta).any(axis=1)
    antes_primero = int(sum(h["primera"][i] for i in range(len(venta)) if h["primera"][i] > 0))
    d["semana_sin_precio"] = {
        "celdas": int(falta.size), "sin_precio": int(falta.sum()), "pct": pct(int(falta.sum()), falta.size),
        "antes_del_primer_precio": antes_primero, "huecos_entre_primera_y_ultima": h["semanas_que_faltan"],
        "despues_del_ultimo_precio": int(sum(len(semanas) - 1 - h["ultima"][i] for i in range(len(venta)) if h["ultima"][i] >= 0)),
        "en_productos_tienda_sin_ningun_precio": int(falta[sin_ninguno].sum()),
        "productos_tienda_sin_ningun_precio": int(sin_ninguno.sum()),
        "por_periodo": {lab: {"celdas": int(falta[:, hasta == hh].size), "sin_precio": int(falta[:, hasta == hh].sum()),
                              "pct": pct(int(falta[:, hasta == hh].sum()), falta[:, hasta == hh].size)}
                        for lab, hh in ((ETQ_HASTA, True), (ETQ_DESPUES, False))},
    }

    # Cada semana sin precio se cuenta una vez (error 11): las cuatro partes suman el total.
    ssp = d["semana_sin_precio"]
    ssp["partes_suman_el_total"] = (ssp["antes_del_primer_precio"] + ssp["huecos_entre_primera_y_ultima"]
                                    + ssp["despues_del_ultimo_precio"] + ssp["en_productos_tienda_sin_ningun_precio"]
                                    == ssp["sin_precio"])

    # ── 6.7 Bloque 3.5 · Duplicados ──
    dup = []
    solo_dias = {p: pd.DataFrame(Y[:, m]).duplicated(keep=False) for p, m in m_periodo.items()}
    ceros_dias = {p: int(((Y[:, m].sum(axis=1) == 0) & solo_dias[p].to_numpy()).sum()) for p, m in m_periodo.items()}
    dup.append({"tabla": "venta", "exactos": int(venta.duplicated().sum()),
                "exactos_sin_identificadores": int(venta.drop(columns=["id", "item_id", "store_id"]).duplicated().sum()),
                "identificadores_quitados": ["id", "item_id", "store_id"], "clave_unica": tdic["venta"]["clave_unica"],
                "por_clave": int(venta.duplicated(["item_id", "store_id"]).sum()), "casi_duplicados": 0, "logicos": 0,
                "filas_con_los_mismos_dias_que_otra": {p: int(s.sum()) for p, s in solo_dias.items()},
                "de_ellas_sin_ninguna_venta": ceros_dias,
                "nota_casi_duplicados": "la clave item_id y store_id es única: no hay dos filas con la misma clave"})
    dup.append({"tabla": "precios", "exactos": int(precios.duplicated().sum()),
                "exactos_sin_identificadores": int(precios.duplicated().sum()), "identificadores_quitados": [],
                "clave_unica": tdic["precios"]["clave_unica"],
                "por_clave": int(precios.duplicated(["store_id", "item_id", "wm_yr_wk"]).sum()), "casi_duplicados": 0,
                "logicos": 0, "nota_casi_duplicados": "la clave tienda, producto y semana es única"})
    dup.append({"tabla": "calendario", "exactos": int(cal.duplicated().sum()),
                "exactos_sin_identificadores": int(cal.drop(columns=["d", "date"]).duplicated().sum()),
                "identificadores_quitados": ["d", "date"], "clave_unica": tdic["calendario"]["clave_unica"],
                "por_clave": int(cal.duplicated(["d"]).sum()), "casi_duplicados": 0, "logicos": 0,
                "nota_casi_duplicados": "la clave d es única y date también"})
    # Duplicados lógicos: la misma entidad escrita de dos formas (códigos y nombres de evento).
    logicos = {}
    for etiqueta, valores in (("item_id", venta["item_id"]), ("store_id", venta["store_id"]), ("dept_id", venta["dept_id"]),
                              ("nombre de evento", pd.concat([cal["event_name_1"], cal["event_name_2"]])),
                              ("tipo de evento", pd.concat([cal["event_type_1"], cal["event_type_2"]]))):
        distintos = pd.Series(valores.dropna().unique())
        grupos_n = distintos.groupby(distintos.map(lambda v: re.sub(r"[^a-z0-9]", "", v.lower()))).size()
        logicos[etiqueta] = {"distintos": int(len(distintos)), "formas_que_se_juntan": int((grupos_n > 1).sum())}
    for e in dup:
        if e["tabla"] == "venta":
            e["logicos"] = sum(logicos[k]["formas_que_se_juntan"] for k in ("item_id", "store_id", "dept_id"))
        if e["tabla"] == "calendario":
            e["logicos"] = sum(logicos[k]["formas_que_se_juntan"] for k in ("nombre de evento", "tipo de evento"))
    d["duplicados"] = dup
    d["duplicados_logicos"] = logicos

    # ── 6.8 Bloque 3.6 · Claves y granularidad ──
    d["claves_y_granularidad"] = [
        {"tabla": "venta", "documentada": "un producto en una tienda, con las unidades de cada día en columnas (guía)",
         "observada": tdic["venta"]["que_es_una_fila"], "clave": tdic["venta"]["clave"],
         "clave_unica": tdic["venta"]["clave_unica"], "clave_alternativa_unica": tdic["venta"]["clave_alternativa_unica"],
         "entidades": {"productos": tdic["venta"]["relaciones_medidas"]["productos_distintos"], "tiendas": len(tiendas),
                       "productos_tienda": len(venta), "dias": len(dias)},
         "discrepancia": "ninguna en la clave; la granularidad producto-tienda-día está en forma ancha"},
        {"tabla": "precios", "documentada": "precio medio de un producto en una tienda en una semana (guía)",
         "observada": tdic["precios"]["que_es_una_fila"], "clave": tdic["precios"]["clave"],
         "clave_unica": tdic["precios"]["clave_unica"],
         "entidades": {"productos_tienda": tdic["precios"]["relaciones_medidas"]["productos_tienda_con_algun_precio"],
                       "semanas": tdic["precios"]["relaciones_medidas"]["semanas_distintas"]},
         "discrepancia": "ninguna"},
        {"tabla": "calendario", "documentada": "un día (guía)", "observada": tdic["calendario"]["que_es_una_fila"],
         "clave": tdic["calendario"]["clave"], "clave_unica": tdic["calendario"]["clave_unica"],
         "entidades": {"dias": len(cal), "semanas": tdic["calendario"]["relaciones_medidas"]["semanas"]},
         "discrepancia": "ninguna"},
    ]

    # ── 6.9 Bloque 3.7 · Categóricas y texto ──
    no_doc = {c: sorted(set(venta[c]) - set(doc)) for c, doc in (("dept_id", DEPARTAMENTOS), ("cat_id", CATEGORIAS),
                                                                  ("store_id", TIENDAS), ("state_id", ESTADOS))}
    nombres_ev = pd.Series(pd.concat([cal["event_name_1"], cal["event_name_2"]]).dropna().unique())
    d["categorias"] = {
        "codigos_no_documentados": {c: v for c, v in no_doc.items()},
        "espacios_externos": {f"{t}.{c['columna']}": c["espacios"] for t in tdic for c in tdic[t]["campos"]
                              if c["tipo_leido"] == "str"},
        "variantes_de_mayusculas": {f"{t}.{c}": int(df[c].dropna().nunique() - df[c].dropna().str.lower().nunique())
                                    for t, df in (("venta", venta[IDENTIDAD_VENTA]), ("precios", precios), ("calendario", cal))
                                    for c in df.columns if pd.api.types.is_string_dtype(df[c])},
        "estilo_de_los_nombres_de_evento": {
            "nombres": int(len(nombres_ev)),
            "con_espacios": int(nombres_ev.str.contains(" ").sum()),
            "con_apostrofo": int(nombres_ev.str.contains("'").sum()),
            "con_guion": int(nombres_ev.str.contains("-").sum()),
            "pegados_con_mayusculas": int(nombres_ev.str.fullmatch(r"([A-Z][a-z]+){2,}").sum()),
        },
    }
    d["categorias_raras"] = [{"tabla": t, "columna": c["columna"], "categoria": r["categoria"], "filas": r["filas"],
                              "pct": r["pct"], "de_diccionario": True}
                             for t in tdic for c in tdic[t]["campos"] for r in c["categorias_raras"]]

    # ── 6.10 Bloque 3.9 · Fechas ──
    dia_mayor_12 = int((cal["date"].str[8:10].astype(int) > 12).sum())
    rel = tdic["calendario"]["relaciones_medidas"]
    fecha_venta_max = fecha_dia.max().date().isoformat()
    sem_fin_datos = int(cal.loc[fechas_cal == pd.Timestamp(FECHA_DATOS), "wm_yr_wk"].iloc[0])
    sem_no_monotona = int((np.diff(cal["wm_yr_wk"].to_numpy()) < 0).sum())
    d["fechas"] = [{
        "tabla": "calendario", "columna": "date", "minimo": campo_dic[("calendario", "date")]["minimo"],
        "maximo": campo_dic[("calendario", "date")]["maximo"], "convencion": "año-mes-día",
        "demostrada": bool(dia_mayor_12 > 0 and fechas_no == 0), "fechas_con_dia_mayor_que_12": dia_mayor_12,
        "fechas_invalidas": fechas_no, "dias_seguidos_sin_hueco": rel["dias_seguidos_sin_hueco"],
        "semanas_que_no_empiezan_en_sabado": rel["semanas_que_no_empiezan_en_sabado"],
        "semanas_incompletas": rel["semanas_incompletas"], "dias_con_semana_anterior_a_la_del_dia_previo": sem_no_monotona,
        "dias_despues_de_la_fecha_de_referencia": cobertura["calendario"]["despues"]["dias"],
        "dias_despues_del_horizonte_del_calendario": int((fechas_cal > pd.Timestamp(FIN_CALENDARIO)).sum()),
        "nota": "los días posteriores a la fecha de referencia no son de ningún periodo; se describen aparte y no se marcan "
                "como futuros (reglas, apartado 5)"},
        {"tabla": "venta", "columna": "d_1 a d_1575 (por su fecha en el calendario)", "minimo": fecha_dia.min().date().isoformat(),
         "maximo": fecha_venta_max, "convencion": "la del calendario", "demostrada": None,
         "dias_despues_del_horizonte": int((fecha_dia > pd.Timestamp(FECHA_DATOS)).sum()),
         "columnas_sin_hueco": tdic["venta"]["bloque_dias"]["nombres_seguidos"]},
        {"tabla": "precios", "columna": "wm_yr_wk", "minimo": int(precios["wm_yr_wk"].min()),
         "maximo": int(precios["wm_yr_wk"].max()), "convencion": "código de semana de Walmart", "demostrada": None,
         "semana_de_la_fecha_de_referencia": sem_fin_datos,
         "filas_despues_del_horizonte": int((precios["wm_yr_wk"] > sem_fin_datos).sum())},
    ]

    # ── 6.11 Bloque 3.10 · Las siete reglas del plan (§5 de las reglas de negocio) ──
    ceros_por = {}
    for p, m in m_periodo.items():
        z = Y[:, m] == 0
        ceros_por[p] = {
            "celdas": int(z.size), "a_cero": int(z.sum()), "pct": pct(int(z.sum()), z.size),
            "por_tienda": {t: pct(int(z[tienda_fila == t].sum()), z[tienda_fila == t].size) for t in TIENDAS},
            "por_departamento": {g: pct(int(z[dept_fila == g].sum()), z[dept_fila == g].size) for g in DEPARTAMENTOS},
        }
    lista_cierres = []
    for i, t in enumerate(tiendas):
        for j in np.flatnonzero(cierre[i]):
            ev = cal.loc[cal["d"] == dias[j], "event_name_1"].iloc[0]
            lista_cierres.append({"tienda": t, "fecha": fecha_dia[j].date().isoformat(), "evento": ev if pd.notna(ev) else None,
                                  "navidad": bool(navidad[j]),
                                  "periodo": "construccion" if m_periodo["construccion"][j] else "validacion"})
    lista_cierres.sort(key=lambda x: (x["fecha"], x["tienda"]))
    cierres_p = {p: {"cierres": sum(1 for c in lista_cierres if c["periodo"] == p),
                     "en_navidad": sum(1 for c in lista_cierres if c["periodo"] == p and c["navidad"]),
                     "fuera_de_navidad": [c for c in lista_cierres if c["periodo"] == p and not c["navidad"]]}
                 for p in m_periodo}
    vsp = semanas_con_venta_sin_precio(W, P)
    psv = (W == 0) & ~np.isnan(P)
    negativos = {p: int((Y[:, m] < 0).sum()) for p, m in m_periodo.items()}
    bajo_hasta, bajo_despues = int((bajo & hasta_precio).sum()), int((bajo & ~hasta_precio).sum())
    reglas = [
        {"id": "R-1", "regla": "un día con cero unidades es un dato válido, no un vacío (§5)",
         "resultado": {p: {k: v for k, v in c.items()} for p, c in ceros_por.items()}},
        {"id": "R-2", "regla": "un cierre es la tienda entera a cero (§5)", "resultado": {
            "total": len(lista_cierres), "por_periodo": cierres_p, "lista": lista_cierres}},
        {"id": "R-3", "regla": "una semana sin precio es una semana sin venta (§5)", "resultado": {
            "semanas_con_venta_sin_precio": {ETQ_HASTA: int(vsp[:, hasta].sum()), ETQ_DESPUES: int(vsp[:, ~hasta].sum())},
            "semanas_con_precio_sin_venta": {ETQ_HASTA: int(psv[:, hasta].sum()), ETQ_DESPUES: int(psv[:, ~hasta].sum())},
            "nota": f"la semana {ultima_sem_c} suma sus siete días: {dias_sem_ultima_c} de la construcción y "
                    f"{dias_sem_ultima - dias_sem_ultima_c} de la validación. Se cuenta en «{ETQ_HASTA}»"}},
        {"id": "R-4", "regla": "el precio vale para los siete días de su semana: un precio por producto-tienda y semana (§5)",
         "resultado": {"filas_con_la_clave_repetida": int(precios.duplicated(["store_id", "item_id", "wm_yr_wk"]).sum()),
                       "fuente": "recontado; el diccionario da la clave única"}},
        {"id": "R-5", "regla": "una venta negativa sería imposible; si aparece, el trabajo para (§5)",
         "resultado": {"negativos": negativos}},
        {"id": "R-6", "regla": "un día sin evento es un día normal (§5)", "resultado": {
            "dias_con_evento": {t: tdic["calendario"]["por_periodo"][k]["dias_con_evento"] for t, k in
                                (("construccion", "construccion"), ("validacion", "validacion"),
                                 ("despues", "despues_de_la_fecha_de_referencia"))},
            "nota": "el vacío de los eventos no entra como ausencia ni en los vacíos por fila; cifras del diccionario"}},
        {"id": "R-7", "regla": "el precio va de 0,5 a 50 dólares en casi todos los productos (§7, «Lo esperable»)",
         "resultado": {"por_debajo": int(bajo.sum()), "por_periodo": {ETQ_HASTA: bajo_hasta, ETQ_DESPUES: bajo_despues},
                       "minimo": round(float(precio.min()), 2), "por_encima": int((precio > RANGO_PRECIO[1]).sum()),
                       "por_departamento": d["escala_precio_bajo"]["por_departamento"]}},
    ]
    d["comprobaciones_reglas"] = reglas

    # ── 6.12 Lo que dejó el reconocimiento: las siete cuestiones, en cada periodo ──
    saltos = saltos_por_periodo(U, navidad, m_periodo)
    saltos_t = saltos_por_periodo(S, navidad, m_periodo)
    sn = {}
    for p, m in m_periodo.items():
        fechas_p = fecha_dia[m]
        def filas_salto(r, nombres):
            """Filas del resultado D1 con su nombre y su fecha."""
            out = []
            for k, fila in r.iterrows():
                medida = fila["razon"] is not None and not pd.isna(fila["razon"])
                out.append({"nombre": nombres[k],
                            "fecha": fechas_p[int(fila["dia"]) - 1].date().isoformat() if medida else None,
                            "antes": round(float(fila["antes"]), 2) if medida else None,
                            "despues": round(float(fila["despues"]), 2) if medida else None,
                            "razon": round(float(fila["razon"]), 2) if medida else None,
                            "salto": bool(fila["salto"])})
            return out
        fs, ft = filas_salto(saltos[p], series), filas_salto(saltos_t[p], tiendas)
        con = [x for x in fs if x["salto"]]
        sn[p] = {"series_con_salto": len(con), "series": len(fs), "bajadas": sum(1 for x in con if x["razon"] < 1),
                 "mayor": max(con, key=lambda x: x["razon"]) if con else None,
                 "menor": min(con, key=lambda x: x["razon"]) if con else None,
                 "saltos": sorted(con, key=lambda x: -x["razon"]),
                 "por_departamento": {g: sum(1 for x in con if x["nombre"].endswith(g)) for g in DEPARTAMENTOS},
                 "tiendas_con_salto": [x for x in ft if x["salto"]], "tiendas": ft}
    d["saltos_de_nivel"] = {"medida": DECISIONES_CERRADAS[0]["cerrado"], "decision": "D1", "fecha_decision": "2026-11-21",
                            "por_periodo": sn}

    primera = np.where((Y > 0).any(axis=1), (Y > 0).argmax(axis=1), Y.shape[1])
    n_c = int(m_periodo["construccion"].sum())
    antes_venta = {"construccion": np.minimum(primera, n_c), "validacion": np.clip(primera - n_c, 0, Y.shape[1] - n_c)}
    # Lo que suman los productos-tienda que venden en el periodo, separado de los que no venden en él ningún día:
    # el reconocimiento contó solo los primeros (1.470.682 en la construcción).
    vende_en = {"construccion": primera < n_c, "validacion": (primera >= n_c) & (primera < Y.shape[1])}
    no_vende_aun = {"construccion": primera >= n_c, "validacion": primera >= Y.shape[1]}
    nuevos_val = (primera >= n_c) & (primera < Y.shape[1])
    z_fuera = (U == 0) & ~cierre[tienda_serie]
    ceros_serie = {}
    for p, m in m_periodo.items():
        zf = z_fuera[:, m]
        rachas = [racha_mas_larga(zf[i]) for i in range(len(series))]
        larga = int(np.argmax(rachas))
        ceros_serie[p] = {"dias_serie_a_cero": int((U[:, m] == 0).sum()), "fuera_de_cierres": int(zf.sum()),
                          "por_departamento": {g: int(zf[dept_serie == g].sum()) for g in DEPARTAMENTOS},
                          "racha_mas_larga": {"serie": series[larga], "dias": rachas[larga]},
                          "por_serie": {series[i]: {"dias": int(zf[i].sum()), "racha": rachas[i]} for i in range(len(series))}}
    nav_idx = np.flatnonzero(navidad)
    unidades_nav = {str(fecha_dia[j].year): int(S[:, j].sum()) for j in nav_idx}
    nav_tienda = {str(fecha_dia[j].year): {t: int(S[i, j]) for i, t in enumerate(tiendas) if S[i, j] > 0} for j in nav_idx}
    sin_venta = {p: (Y[:, m].sum(axis=1) == 0) for p, m in m_periodo.items()}
    nunca = sin_venta["construccion"] & sin_venta["validacion"]
    sin_precio_hasta = np.isnan(P[:, hasta]).all(axis=1)
    sin_precio_todo = np.isnan(P).all(axis=1)
    primera_sem = h["primera"]
    con_ambos = (primera < Y.shape[1]) & (primera_sem >= 0)
    dia_primer_precio = np.where(primera_sem >= 0, cambios[np.clip(primera_sem, 0, None)], -1)
    dif = (primera - dia_primer_precio)[con_ambos]
    llega_despues = con_ambos & (primera_sem > 0)
    dif_n = (primera - dia_primer_precio)[llega_despues]
    # La población del reconocimiento (celda 50): con precio y venta, y primera venta después del primer día.
    nuevo = con_ambos & (primera > 0)
    dif_r = (primera - dia_primer_precio)[nuevo]
    per_r = np.where(primera[nuevo] < n_c, "construccion", "validacion")
    rec = [
        {"id": "Q-1", "cuestion": "los saltos de nivel (medida D1)", "resultado": {
            p: {"series_con_salto": sn[p]["series_con_salto"], "bajadas": sn[p]["bajadas"],
                "tiendas_con_salto": [x["nombre"] for x in sn[p]["tiendas_con_salto"]]} for p in sn},
         "detalle": "saltos_de_nivel"},
        {"id": "Q-2", "cuestion": "los días anteriores a la primera venta de cada producto-tienda", "resultado": {
            p: {"dias_producto_tienda": int(a.sum()),
                "de_productos_tienda_que_empiezan_a_vender_en_el_periodo": int(a[vende_en[p]].sum()),
                "de_productos_tienda_que_aun_no_venden_al_acabar_el_periodo": int(a[no_vende_aun[p]].sum()),
                "productos_tienda_que_aun_no_venden_al_acabar_el_periodo": int(no_vende_aun[p].sum()),
                "por_tienda": {t: int(a[tienda_fila == t].sum()) for t in TIENDAS},
                "por_departamento": {g: int(a[dept_fila == g].sum()) for g in DEPARTAMENTOS}} for p, a in antes_venta.items()}
            | {"productos_tienda_que_venden_por_primera_vez_en_la_validacion": int(nuevos_val.sum()),
               "nota": "la primera venta se busca en los dos periodos; en la validación cuentan los días antes de esa primera venta"}},
        {"id": "Q-3", "cuestion": "los días de serie a cero fuera de los cierres",
         "resultado": {p: {k: v for k, v in c.items() if k != "por_serie"} for p, c in ceros_serie.items()},
         "detalle": "la racha cuenta días seguidos a cero fuera de un cierre; un cierre corta la racha"},
        {"id": "Q-4", "cuestion": "el cierre de WI_1 del 02/02/2011 sin evento",
         "resultado": {"cierres_fuera_de_navidad": [c for c in lista_cierres if not c["navidad"]]}},
        {"id": "Q-5", "cuestion": "las unidades del 25 de diciembre", "resultado": {
            "por_ano": unidades_nav, "por_tienda_y_ano": nav_tienda,
            "construccion": int(sum(S[:, j].sum() for j in nav_idx if m_periodo["construccion"][j])),
            "validacion": int(sum(S[:, j].sum() for j in nav_idx if m_periodo["validacion"][j]))}},
        {"id": "Q-6", "cuestion": "los productos-tienda que no venden nunca", "resultado": {
            "construccion": int(sin_venta["construccion"].sum()), "validacion": int(sin_venta["validacion"].sum()),
            "en_ninguno_de_los_dos": int(nunca.sum()), "en_ninguno_sin_ningun_precio": int((nunca & sin_precio_todo).sum()),
            "construccion_sin_precio_hasta_la_semana": int((sin_venta["construccion"] & sin_precio_hasta).sum()),
            "por_departamento_en_ninguno": {g: int((nunca & (dept_fila == g)).sum()) for g in DEPARTAMENTOS}}},
        {"id": "Q-7", "cuestion": "el precio que llega antes de la primera venta", "resultado": {
            "productos_tienda_con_precio_y_venta": int(con_ambos.sum()),
            "dias_entre_primer_precio_y_primera_venta": {
                "antes_del_precio": int((dif < 0).sum()), "de_0_a_6": int(((dif >= 0) & (dif <= 6)).sum()),
                "de_7_a_27": int(((dif >= 7) & (dif <= 27)).sum()), "28_o_mas": int((dif >= 28).sum())},
            "con_el_primer_precio_despues_de_la_primera_semana": int(llega_despues.sum()),
            "de_ellos_de_0_a_6_dias": int(((dif_n >= 0) & (dif_n <= 6)).sum()),
            "primera_venta_por_periodo": {"construccion": int((con_ambos & (primera < n_c)).sum()),
                                          "validacion": int((con_ambos & (primera >= n_c)).sum())},
            "como_el_reconocimiento": {p: {"empiezan_a_vender_despues_del_primer_dia": int((per_r == p).sum()),
                                           "precio_de_0_a_6_dias_antes": int(((dif_r >= 0) & (dif_r <= 6) & (per_r == p)).sum()),
                                           "precio_mas_de_6_dias_antes": int(((dif_r > 6) & (per_r == p)).sum()),
                                           "precio_despues": int(((dif_r < 0) & (per_r == p)).sum())}
                                       for p in m_periodo},
            "nota": "el primer precio cuenta desde el sábado de su semana"}},
    ]
    d["reconocimiento"] = rec
    d["ceros_por_serie"] = {p: c["por_serie"] for p, c in ceros_serie.items()}

    # ── 6.13 Reglas candidatas (D3): cada regla de las nueve viñetas, por separado ──
    rv = tdic["venta"]["relaciones_medidas"]
    dias_sem = cal.groupby("wm_yr_wk").size()
    filas_semana_corta = int(cal["wm_yr_wk"].map(dias_sem).ne(7).sum())
    pares = pd.concat([cal[["event_name_1", "event_type_1"]].set_axis(["nombre", "tipo"], axis=1),
                       cal[["event_name_2", "event_type_2"]].set_axis(["nombre", "tipo"], axis=1)])
    varios_tipos = nombres_con_mas_de_un_tipo(pares)
    filas_varios = int(pares["nombre"].isin(varios_tipos).sum())
    dia_mes = fechas_cal.dt.day.to_numpy()
    snap_cambia = {e: snap_que_cambia(dia_mes, cal[f"snap_{e}"].to_numpy()) for e in ESTADOS}
    snap_dias = {e: sorted(int(x) for x in np.unique(dia_mes[cal[f"snap_{e}"].to_numpy() == 1])) for e in ESTADOS}
    sub = subidas_de_precio(P, SUBIDA_PRECIO)
    bajadas_mitad = int(subidas_de_precio(1 / P, SUBIDA_PRECIO).sum())
    primer_dia_sem = cal.groupby("wm_yr_wk")["weekday"].first()
    rc = [
        ("RC-01", "venta", ["dept_id", "cat_id"], "dept_id empieza por cat_id",
         rv["departamentos_cuyo_codigo_no_empieza_por_su_categoria"], "filas", "diccionario"),
        ("RC-02", "venta", ["item_id", "dept_id"], "item_id empieza por dept_id",
         rv["productos_cuyo_codigo_no_empieza_por_su_departamento"], "filas", "diccionario"),
        ("RC-03", "venta", ["store_id", "state_id"], "store_id empieza por state_id",
         rv["tiendas_cuyo_codigo_no_empieza_por_su_estado"], "filas", "diccionario"),
        ("RC-04", "venta", ["id", "item_id", "store_id"], "id es item_id, store_id y el sufijo evaluation, unidos por guion bajo",
         len(venta) - id_doble + (0 if rv["sufijos_distintos_de_id"] == 1 else len(venta)), "filas", "calculado"),
        ("RC-05", "calendario", ["wday", "weekday"], "wday casa con weekday",
         rel["filas_con_wday_distinto_del_que_toca_a_weekday"], "días", "diccionario"),
        ("RC-06", "calendario", ["month", "date"], "month casa con date", rel["filas_con_month_distinto_del_mes_de_date"],
         "días", "diccionario"),
        ("RC-07", "calendario", ["year", "date"], "year casa con date", rel["filas_con_year_distinto_del_ano_de_date"],
         "días", "diccionario"),
        ("RC-08", "calendario", ["event_name_1", "event_type_1"], "event_type_1 está vacío si y solo si lo está event_name_1",
         rel["filas_con_nombre_y_tipo_del_evento_1_descuadrados"], "días", "diccionario"),
        ("RC-09", "calendario", ["event_name_2", "event_type_2"], "event_type_2 está vacío si y solo si lo está event_name_2",
         rel["filas_con_nombre_y_tipo_del_evento_2_descuadrados"], "días", "diccionario"),
        ("RC-10", "calendario", ["event_name_1", "event_name_2"], "no hay segundo evento sin primero",
         rel["dias_con_segundo_evento_sin_primero"], "días", "diccionario"),
        ("RC-11", "calendario", ["wm_yr_wk"], "la semana de Walmart tiene siete días", filas_semana_corta, "días",
         "calculado"),
        ("RC-12", "calendario", ["wm_yr_wk", "weekday"], "la semana de Walmart empieza en sábado",
         int((primer_dia_sem.iloc[1:] != "Saturday").sum()), "semanas", "calculado"),
        ("RC-13", "calendario", ["event_name_1", "event_type_1", "event_name_2", "event_type_2"],
         "cada nombre de evento tiene siempre el mismo tipo", filas_varios, "apariciones de evento", "calculado"),
        ("RC-14", "precios", ["item_id", "store_id", "wm_yr_wk"],
         "un producto-tienda con precio lo tiene todas las semanas entre la primera y la última, sin huecos",
         h["semanas_que_faltan"], "semanas que faltan", "calculado"),
        ("RC-15", "precios", ["item_id", "store_id", "wm_yr_wk"],
         f"un producto-tienda con precio lo tiene hasta la última semana, la {int(semanas[-1])}", h["no_llegan_al_final"],
         "productos-tienda", "calculado"),
        ("RC-16", "precios", ["sell_price", "wm_yr_wk"],
         "el precio de un producto-tienda no pasa de más del doble de una semana a la siguiente", int(sub.sum()),
         "semanas", "calculado"),
        ("RC-17", "calendario", ["snap_CA", "snap_TX", "snap_WI", "date"],
         "el SNAP sigue una regla fija por día del mes en cada estado", int(sum(snap_cambia.values())), "días", "calculado"),
    ]
    d["reglas_candidatas"] = [{"id": i, "tabla": t, "columnas": cs, "regla": r, "filas_que_incumplen": int(n), "unidad": u,
                               "fuente": f, "aprobada": REGLAS_CANDIDATAS_APROBADAS,
                               "aprobacion": "D3: comprobación aprobada con el plan el 21/11/2026; pasarla a las reglas de "
                                             "negocio va por la cascada"} for i, t, cs, r, n, u, f in rc]
    extra = {
        "RC-11": {"semanas_incompletas": rel["semanas_incompletas"]},
        "RC-13": {"nombres": int(pares["nombre"].dropna().nunique()), "nombres_con_mas_de_un_tipo": len(varios_tipos)},
        "RC-14": {"productos_tienda_con_precio": h["con_precio"]},
        "RC-15": {"productos_tienda_con_precio": h["con_precio"],
                  "productos_tienda_que_llegan": h["con_precio"] - h["no_llegan_al_final"]},
        "RC-16": {"productos_tienda_con_subida": int(sub.any(axis=1).sum()),
                  "por_periodo": {ETQ_HASTA: int(sub[:, hasta].sum()), ETQ_DESPUES: int(sub[:, ~hasta].sum())},
                  "bajadas_a_menos_de_la_mitad": bajadas_mitad},
        "RC-17": {"dias_que_cambian_por_estado": snap_cambia, "dias_del_mes_con_snap": snap_dias},
    }
    for r in d["reglas_candidatas"]:
        r.update(extra.get(r["id"], {}))

    # ── 6.14 Bloque 3.11 · Cruces entre tablas ──
    dias_set = set(dias)
    pt_venta = set(zip(venta["item_id"], venta["store_id"]))
    pt_precio = set(zip(precios["item_id"], precios["store_id"]))
    sem_cal = set(cal["wm_yr_wk"])
    sem_precio = set(precios["wm_yr_wk"])
    sin_pareja_pt = {lab: int(np.isnan(P[:, hasta == hh]).all(axis=1).sum()) for lab, hh in
                     ((ETQ_HASTA, True), (ETQ_DESPUES, False))}
    unidades_sin_precio = {lab: int(Y[np.isnan(P[:, hasta == hh]).all(axis=1)][:, np.isin(sem_dia, semanas[hasta == hh])].sum())
                           for lab, hh in ((ETQ_HASTA, True), (ETQ_DESPUES, False))}
    formato = lambda s: bool((s.str.strip() != s).any() or (s.str.upper() != s).any())
    sem_cal_por = {t: set(cal.loc[tramo_cal == t, "wm_yr_wk"]) for t in ("construccion", "validacion", "despues")}
    d["cruces"] = [
        {"izquierda": "venta", "derecha": "precios", "clave": ["item_id", "store_id"], "cardinalidad_esperada": "1:N",
         "supuesta": True, "sin_pareja_izquierda": len(pt_venta - pt_precio), "sin_pareja_derecha": len(pt_precio - pt_venta),
         "pct_sin_pareja_izquierda": pct(len(pt_venta - pt_precio), len(pt_venta)),
         "pct_sin_pareja_derecha": pct(len(pt_precio - pt_venta), len(pt_precio)),
         "sin_pareja_izquierda_por_periodo": sin_pareja_pt, "unidades_de_los_sin_pareja": unidades_sin_precio,
         "formato_distinto": bool(formato(venta["item_id"]) != formato(precios["item_id"]) or
                                  str(venta["item_id"].dtype) != str(precios["item_id"].dtype)),
         "tipos": [str(venta["item_id"].dtype), str(precios["item_id"].dtype)],
         "unica_en_maestro": bool(not venta.duplicated(["item_id", "store_id"]).any())},
        {"izquierda": "precios", "derecha": "calendario", "clave": ["wm_yr_wk"], "cardinalidad_esperada": "N:1 frente a las semanas del calendario",
         "supuesta": True, "sin_pareja_izquierda": len(sem_precio - sem_cal), "sin_pareja_derecha": len(sem_cal - sem_precio),
         "pct_sin_pareja_izquierda": pct(len(sem_precio - sem_cal), len(sem_precio)),
         "pct_sin_pareja_derecha": pct(len(sem_cal - sem_precio), len(sem_cal)),
         "semanas_del_calendario_sin_precio_por_tramo": {t: len(s - sem_precio) for t, s in sem_cal_por.items()},
         "semanas_del_calendario_por_tramo": {t: len(s) for t, s in sem_cal_por.items()},
         "formato_distinto": str(precios["wm_yr_wk"].dtype) != str(cal["wm_yr_wk"].dtype),
         "tipos": [str(precios["wm_yr_wk"].dtype), str(cal["wm_yr_wk"].dtype)],
         "unica_en_maestro": bool(cal["wm_yr_wk"].is_unique),
         "nota": "el calendario tiene una fila por día: la semana se repite siete veces y es única entre sus semanas distintas"},
        {"izquierda": "venta (columnas de días)", "derecha": "calendario", "clave": ["d"], "cardinalidad_esperada": "1:1",
         "supuesta": True, "sin_pareja_izquierda": len(set(dias) - set(cal["d"])),
         "sin_pareja_derecha": len(set(cal["d"]) - set(dias)),
         "pct_sin_pareja_izquierda": pct(len(set(dias) - set(cal["d"])), len(dias)),
         "pct_sin_pareja_derecha": pct(len(set(cal["d"]) - set(dias)), len(cal)),
         "sin_pareja_derecha_dentro_de_los_periodos": int(sum(1 for x, t in zip(cal["d"], tramo_cal) if t != "despues" and x not in dias_set)),
         "formato_distinto": False, "tipos": ["nombre de columna", str(cal["d"].dtype)],
         "unica_en_maestro": tdic["calendario"]["clave_unica"],
         "nota": "los días del calendario posteriores a la fecha de referencia no tienen columna a propósito (reglas, apartado 5)"},
    ]

    # ── 6.15 Riesgos para un modelo (comprobaciones.md §2) ──
    d["riesgos_modelo"] = [
        {"tabla": "precios", "columna": "sell_price", "riesgo": "el precio de la semana prevista dice si hubo venta: una "
         f"semana sin precio es una semana sin venta ({fmt(int(vsp.sum()))} semanas con venta y sin precio). Los "
         "planteamientos fijan el precio de la semana anterior"},
        {"tabla": "venta", "columna": "unidades", "riesgo": "el objetivo es continuo y el desequilibrio de clases no aplica; los "
         f"ceros pesan más en HOBBIES_2, con el {fmt(ceros_por['construccion']['por_departamento']['HOBBIES_2'])} % de sus "
         "celdas a cero en la construcción"},
        {"tabla": "venta", "columna": "item_id", "riesgo": f"categórica con {fmt(int(venta['item_id'].nunique()))} valores"},
        {"tabla": "venta", "columna": "id", "riesgo": f"categórica con {fmt(int(venta['id'].nunique()))} valores, uno por fila"},
        {"tabla": "calendario", "columna": "event_name_1",
         "riesgo": f"categórica con {fmt(int(cal['event_name_1'].nunique()))} valores"},
        {"tabla": "venta", "columna": "id, cat_id, state_id", "riesgo": "columnas que salen de otras: id del producto y la "
         "tienda; cat_id del departamento; state_id de la tienda"},
        {"tabla": "calendario", "columna": "weekday, wday, month, year, d", "riesgo": "columnas que salen de la fecha"},
        {"tabla": "precios", "columna": "wm_yr_wk", "riesgo": f"la semana {ultima_sem_c} cruza de la construcción a la "
         "validación: su precio vale para días de los dos periodos"},
    ]

    # ── 6.16 Datos personales, texto libre y lo que no se aplicó ──
    d["datos_personales"] = []
    d["datos_personales_nota"] = (
        "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas de "
        "negocio §9 dicen que los datos son de productos, tiendas, precios y calendario; no traen nada de personas. El "
        f"diccionario buscó valores con forma de dato personal en cada columna de texto y los encontró en "
        f"{fmt(len(dic['datos_personales']))} columnas. Este método no usa ni deja ninguna columna de datos personales."
        if not PROTECCION.exists() else "Hay proteccion-datos.json: revisar su contenido.")
    sin_mad = [f"{o['tabla']} {o['grupo']} {PERIODO_TXT.get(o['periodo'], o['periodo'])}" for o in outl
               if "z_robusto" in o["dispersion_cero"]]
    sin_iqr = [f"{o['tabla']} {o['grupo']} {PERIODO_TXT.get(o['periodo'], o['periodo'])}" for o in outl
               if "iqr" in o["dispersion_cero"]]
    d["no_aplicado"] = [
        {"control": "la búsqueda de fechas de Excel (comprobaciones.md §6)", "motivo": "ninguna columna de fecha está guardada como número"},
        {"control": "la búsqueda de instrucciones dentro del texto (bloque 3.7)", "motivo": "ninguna columna es texto libre"},
        {"control": "el control de clases desbalanceadas (comprobaciones.md §2)", "motivo": "el objetivo es continuo"},
        {"control": "el z robusto donde la desviación absoluta mediana es cero",
         "motivo": f"dispersión cero en {fmt(len(sin_mad))} grupos ({lista(sin_mad)})" if sin_mad else "ningún grupo"},
        {"control": "el rango intercuartílico donde Q1 y Q3 son iguales",
         "motivo": f"dispersión cero en {fmt(len(sin_iqr))} grupos ({lista(sin_iqr)})" if sin_iqr else "ningún grupo"},
        {"control": "el factor de una escala perdida", "motivo": "ninguna magnitud tiene un hueco en su número de cifras"
         if not any(e["salto"] for e in escalas) else "hay grupos con salto: ver escala"},
        {"control": "nada de la prueba final", "motivo": "no está en el caso (reglas, apartado 5)"},
    ]
    d["instrucciones_en_texto"] = []

    # ── 6.17 Problemas y pendientes (lo que el plan no preveía va con su cifra, comprobaciones.md §12) ──
    problemas, pendientes = [], []
    nota_corr = "la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»)"

    def problema(bloque, tabla, columna, resultado, filas, total, observacion, accion, negocio=False):
        """Añade un problema con su id correlativo."""
        problemas.append({"id": f"C-{len(problemas) + 1:02d}", "bloque": bloque, "tabla": tabla, "columna": columna,
                          "resultado": resultado, "filas_afectadas": filas, "pct_filas": pct(filas, total) if total else None,
                          "observacion": observacion, "posible_accion": accion, "decision_de_negocio": negocio})
        return problemas[-1]["id"]

    def pendiente(tabla, columna, pregunta, opciones, problema_id):
        """Añade una cuestión pendiente, sin elegir ninguna opción."""
        pendientes.append({"id": f"PC-{len(pendientes) + 1:02d}", "tabla": tabla, "columna": columna, "pregunta": pregunta,
                           "opciones": opciones, "problema": problema_id, "nota": nota_corr})

    problema("3.2", "venta", "d_1 a d_1575", f"{fmt(len(dias))} columnas, una por día", len(venta), len(venta),
             "forma no tabular: los días están repartidos en columnas", "pasar a una fila por producto-tienda-día al transformar")
    problema("3.2", "venta", "id", f"{fmt(id_doble)} de {fmt(len(venta))} filas son item_id, store_id y el sufijo "
             f"{tdic['venta']['relaciones_medidas']['sufijo_de_id']}", id_doble, len(venta),
             "columna doble: repite el producto y la tienda", "no usarla como variable; la clave es item_id con store_id")
    colisiones = sum(1 for n in nombres if n["colision_con"])
    problema("3.2", "calendario", ", ".join(n["columna"] for n in nombres),
             f"{fmt(len(nombres))} nombres con mayúsculas; {fmt(colisiones)} colisiones al normalizar", len(nombres), None,
             "nombres que no siguen la forma normalizada", "normalizar el nombre en la corrección")
    problema("3.3", "calendario", "date", f"texto en año-mes-día; {fmt(fechas_no)} fechas no se leen con ese formato", len(cal),
             len(cal), "la fecha llega como texto", "leerla como fecha con su formato")
    for c in COLUMNAS_EVENTO:
        cd = campo_dic[("calendario", c)]
        problema("3.4", "calendario", c, f"{fmt(cd['nulos'])} vacíos de {fmt(cd['filas'])} días ({fmt(cd['nulos_pct'])} %); "
                 f"{fmt(len(cd['categorias_raras']))} categorías raras", cd["nulos"], cd["filas"],
                 "el vacío es «sin evento» (reglas, apartado 5); las categorías raras quedan como están por D2, cerrada el 21/11/2026",
                 "cómo se leen se decide en las reglas de transformación (D2)", negocio=True)
    ssp = d["semana_sin_precio"]
    problema("3.4", "precios", "sell_price (semana sin fila)",
             f"{fmt(ssp['sin_precio'])} de {fmt(ssp['celdas'])} semanas producto-tienda sin precio ({fmt(ssp['pct'])} %): "
             f"{fmt(ssp['antes_del_primer_precio'])} antes del primer precio, {fmt(ssp['huecos_entre_primera_y_ultima'])} en "
             f"huecos y {fmt(ssp['en_productos_tienda_sin_ningun_precio'])} en los "
             f"{fmt(ssp['productos_tienda_sin_ningun_precio'])} productos-tienda sin ningún precio", ssp["sin_precio"], ssp["celdas"],
             f"veredicto del reparto: {rep_precio['veredicto']}; la guía y las reglas, apartado 5 la documentan como semana sin venta",
             "ninguna en la calidad; el dólar se calcula solo donde hay precio")
    for p in m_periodo:
        cp = ceros_por[p]
        problema("3.4", "venta", "unidades", f"{fmt(cp['a_cero'])} de {fmt(cp['celdas'])} celdas a cero ({fmt(cp['pct'])} %) en la "
                 f"{PERIODO_TXT[p]}", cp["a_cero"], cp["celdas"],
                 "dato válido (reglas, apartado 5); por su peso en el extremo del rango sería un código numérico candidato",
                 "ninguna: no es un vacío")
    id_bajo = problema("3.10", "precios", "sell_price", f"{fmt(int(bajo.sum()))} precios por debajo de 0,5 dólares: "
                       f"{fmt(bajo_hasta)} hasta la semana {ultima_sem_c} y {fmt(bajo_despues)} después; mínimo "
                       f"{fmt(round(float(precio.min()), 2))}", int(bajo.sum()), len(precios),
                       "fuera del rango de «Lo esperable» (reglas, apartado 7); "
                       f"{fmt(d['escala_precio_bajo']['productos_tienda_siempre_por_debajo'])} productos-tienda los tienen en "
                       "todas sus semanas", "preguntar, nunca quitar")
    pendiente("precios", "sell_price", f"{fmt(int(bajo.sum()))} precios quedan por debajo de 0,5 dólares, fuera de «Lo "
              "esperable». ¿Cómo se leen?",
              ["son precios reales de productos baratos y se usan como están",
               "son errores del dato y no se usan para calcular dólares"], id_bajo)
    id_sub = problema("3.10", "precios", "sell_price", f"{fmt(int(sub.sum()))} subidas de más del doble de una semana a la "
                      f"siguiente, en {fmt(int(sub.any(axis=1).sum()))} productos-tienda", int(sub.sum()), len(precios),
                      "«Lo esperable» (reglas, apartado 7) lo señala como sospechoso", "preguntar, nunca quitar")
    pendiente("precios", "sell_price", f"En {fmt(int(sub.sum()))} semanas el precio pasa a más del doble que la semana "
              "anterior. ¿Cómo se leen?",
              ["son cambios reales de precio y se usan como están",
               "son errores del dato y esas semanas no se usan para calcular dólares"], id_sub)
    fuera_nav = [c for c in lista_cierres if not c["navidad"]]
    id_cierre = problema("3.10", "venta", "unidades", f"{fmt(len(lista_cierres))} cierres: "
                         f"{fmt(cierres_p['construccion']['cierres'])} en la construcción y "
                         f"{fmt(cierres_p['validacion']['cierres'])} en la validación; fuera del 25 de diciembre, "
                         + lista([f"{c['tienda']} el {c['fecha']}" + ("" if c["evento"] else " sin evento") for c in fuera_nav],
                                 "ninguno"), len(fuera_nav), None,
                         "«Lo esperable» (reglas, apartado 7): un cierre en una sola tienda sin causa hace sospechar", "preguntar")
    if fuera_nav:
        pendiente("venta", "unidades", f"Fuera del 25 de diciembre hay {fmt(len(fuera_nav))} "
                  + ("cierre de tienda" if len(fuera_nav) == 1 else "cierres de tienda") + ": "
                  + lista([f"{c['tienda']} el {c['fecha']}" + ("" if c["evento"] else ", sin evento") for c in fuera_nav])
                  + ". ¿Cómo se lee?",
                  ["es un cierre real de la tienda y se trata como el 25 de diciembre",
                   "es un día sin dato y se trata como vacío"], id_cierre)
    # El 25 de diciembre se describe con los cierres medidos, sin copiar las reglas, apartado 5.
    nav = textos_navidad(unidades_nav, sum(c["navidad"] for c in lista_cierres), len(tiendas))
    id_nav = problema("3.10", "venta", "unidades", "unidades del 25 de diciembre, las 5.000 series sumadas: "
                      + "; ".join(f"{a}, {fmt(u)}" for a, u in unidades_nav.items()), sum(unidades_nav.values()), None,
                      nav["observacion"], "preguntar; el 25 de diciembre ya queda fuera del error (reglas, apartado 6)")
    pendiente("venta", "unidades", nav["pregunta"],
              ["se dejan como vendidas", "se leen como cierre, con la venta a cero"], id_nav)
    for p in m_periodo:
        s = sn[p]
        if s["mayor"] is None:
            continue
        id_s = problema("3.10", "venta", "unidades por serie", f"{fmt(s['series_con_salto'])} de {fmt(s['series'])} series con "
                        f"salto de nivel en la {PERIODO_TXT[p]}, {fmt(s['bajadas'])} de ellos bajadas; el mayor, "
                        f"{s['mayor']['nombre']}, {fmt(s['mayor']['razon'])} veces el {s['mayor']['fecha']}; tiendas con salto: "
                        + lista([f"{x['nombre']} ({fmt(x['razon'])} veces el {x['fecha']})" for x in s["tiendas_con_salto"]],
                                "ninguna"), s["series_con_salto"], s["series"],
                        "medido con D1, cerrada el 21/11/2026; «Lo esperable» (reglas, apartado 7) señala un salto duradero sin "
                        "festivo, que puede ser un producto que empieza a venderse",
                        "medir en la corrección si cambia alguna respuesta")
        pendiente("venta", "unidades por serie", f"En la {PERIODO_TXT[p]}, {fmt(s['series_con_salto'])} series tienen un salto "
                  "de nivel. ¿Cómo se leen?",
                  ["son cambios reales de la venta y la serie se usa entera",
                   "la historia anterior al salto no representa la serie y se marca"], id_s)
    cs_c = ceros_serie["construccion"]
    problema("3.10", "venta", "unidades por serie", "días de serie a cero fuera de los cierres: " + "; ".join(
             f"{PERIODO_TXT[p]} {fmt(c['fuera_de_cierres'])}, con la racha más larga de {fmt(c['racha_mas_larga']['dias'])} "
             f"días en {c['racha_mas_larga']['serie']}" for p, c in ceros_serie.items()), cs_c["fuera_de_cierres"], None,
             f"HOBBIES_2 tiene {fmt(cs_c['por_departamento']['HOBBIES_2'])} de los de la construcción",
             "clasificarlos en la limpieza con la tabla de clases (reglas, apartado 5)")
    problema("3.10", "venta", "unidades", "días producto-tienda a cero antes de la primera venta: " + "; ".join(
             f"{PERIODO_TXT[p]} {fmt(int(a[vende_en[p]].sum()))} de los que empiezan a vender en ella, más "
             f"{fmt(int(a[no_vende_aun[p]].sum()))} de los {fmt(int(no_vende_aun[p].sum()))} que aún no venden al acabarla"
             for p, a in antes_venta.items()) + f"; {fmt(int(nuevos_val.sum()))} productos-tienda venden por primera vez en "
             "la validación", int(antes_venta["construccion"].sum()), None,
             "suman cero a su departamento sin que cambie la demanda (reglas, apartado 3)",
             "medir en la corrección si cambia alguna respuesta")
    problema("3.10", "venta", "unidades", f"productos-tienda sin ninguna venta: {fmt(int(sin_venta['construccion'].sum()))} en "
             f"la construcción; {fmt(int(sin_venta['validacion'].sum()))} en la validación; {fmt(int(nunca.sum()))} en "
             f"ninguno de los dos, {fmt(int((nunca & sin_precio_todo).sum()))} de ellos sin ningún precio", int(nunca.sum()),
             len(venta), "suman cero a su departamento", "medir si quitarlos cambia alguna respuesta")
    problema("3.10", "precios", "sell_price", f"{fmt(int(psv.sum()))} semanas producto-tienda con precio y sin venta",
             int(psv.sum()), int((~np.isnan(P)).sum()), "descripción: el precio no dice que hubo venta", "ninguna")
    problema("3.9", "calendario", "wm_yr_wk", f"la semana {ultima_sem_c} tiene {fmt(dias_sem_ultima_c)} días en la "
             f"construcción y {fmt(dias_sem_ultima - dias_sem_ultima_c)} en la validación", dias_sem_ultima, None,
             "su precio vale para días de los dos periodos", "tenerlo en cuenta al cortar por periodo")
    problema("3.9", "calendario", "date", f"{fmt(cobertura['calendario']['despues']['dias'])} días después de la fecha de "
             "referencia", cobertura["calendario"]["despues"]["dias"], len(cal),
             "a propósito (reglas, apartado 5); no son de ningún periodo", "ninguna")
    problema("3.10", "calendario", "wm_yr_wk", "semanas incompletas: " + lista(
             [f"la {k}, con {fmt(v)} días" for k, v in rel["semanas_incompletas"].items()]), filas_semana_corta, len(cal),
             "la última semana del calendario acaba con el fichero", "ninguna")
    for o in outl:
        if o["grupo"] == "total":
            problema("3.8", o["tabla"], o["columna"], f"{PERIODO_TXT.get(o['periodo'], o['periodo'])}: "
                     + texto_atipicos(o), o["iqr"] or 0, o["valores"],
                     "un atípico no es un error; los límites solo detectan", "ninguna en la calidad")
    problema("3.11", "venta", "item_id, store_id", f"{fmt(len(pt_venta - pt_precio))} productos-tienda de la venta sin ningún "
             f"precio; {fmt(len(pt_precio - pt_venta))} pares de los precios sin venta", len(pt_venta - pt_precio), len(pt_venta),
             f"arrastran {fmt(sum(unidades_sin_precio.values()))} unidades", "ninguna: no venden")
    d["problemas"], d["pendientes"] = problemas, pendientes

    # ── 6.18 Cifras de control de la petición, leídas del propio resultado ──
    q6 = rec[5]["resultado"]
    sc, sv = sn["construccion"], sn["validacion"]
    d["cifras_de_control"] = {
        "filas_venta": len(venta), "filas_precios": len(precios), "filas_calendario": len(cal),
        "precio_bajo_0_5": int(bajo.sum()), "precio_bajo_0_5_hasta_11416": bajo_hasta, "precio_bajo_0_5_despues": bajo_despues,
        "precio_minimo": round(float(precio.min()), 2), "precio_por_encima_de_50": int((precio > RANGO_PRECIO[1]).sum()),
        "cierres": len(lista_cierres), "cierres_construccion": cierres_p["construccion"]["cierres"],
        "cierres_construccion_navidad": cierres_p["construccion"]["en_navidad"],
        "cierres_construccion_fuera_de_navidad": [{"tienda": c["tienda"], "fecha": c["fecha"], "evento": c["evento"]}
                                                  for c in cierres_p["construccion"]["fuera_de_navidad"]],
        "cierres_validacion": cierres_p["validacion"]["cierres"], "cierres_validacion_navidad": cierres_p["validacion"]["en_navidad"],
        "unidades_25_diciembre": unidades_nav, "semanas_con_venta_sin_precio": int(vsp.sum()),
        "productos_tienda_sin_venta_construccion": q6["construccion"], "productos_tienda_sin_venta_validacion": q6["validacion"],
        "productos_tienda_sin_venta_en_ninguno": q6["en_ninguno_de_los_dos"],
        "productos_tienda_sin_venta_en_ninguno_sin_precio": q6["en_ninguno_sin_ningun_precio"],
        "nombres_de_evento": int(pares["nombre"].dropna().nunique()), "nombres_de_evento_con_mas_de_un_tipo": len(varios_tipos),
        "snap_dias_que_cambian": snap_cambia, "snap_dias_del_mes": snap_dias,
        "precio_semanas_que_faltan": h["semanas_que_faltan"], "productos_tienda_con_precio": h["con_precio"],
        "productos_tienda_con_precio_hasta_la_ultima_semana": h["con_precio"] - h["no_llegan_al_final"],
        "ultima_semana_de_precio": int(semanas[-1]),
        "subidas_de_precio_mas_del_doble": int(sub.sum()), "productos_tienda_con_subida": int(sub.any(axis=1).sum()),
        "saltos_construccion_series": sc["series_con_salto"], "saltos_construccion_bajadas": sc["bajadas"],
        "saltos_construccion_mayor": {k: sc["mayor"][k] for k in ("nombre", "razon", "fecha")} if sc["mayor"] else None,
        "saltos_construccion_tiendas": [{k: x[k] for k in ("nombre", "razon", "fecha")} for x in sc["tiendas_con_salto"]],
        "saltos_construccion_wi_3": {k: next(x for x in sc["tiendas"] if x["nombre"] == "WI_3")[k] for k in ("razon", "fecha", "salto")},
        "saltos_validacion_series": sv["series_con_salto"], "saltos_validacion_bajadas": sv["bajadas"],
        "saltos_validacion_mayor": {k: sv["mayor"][k] for k in ("nombre", "razon", "fecha")} if sv["mayor"] else None,
        "saltos_validacion_tiendas": [{k: x[k] for k in ("nombre", "razon", "fecha")} for x in sv["tiendas_con_salto"]],
    }

    # ── 6.19 Límites, estado y validación ──
    d["limites"] = [
        "Se revisaron tres relaciones: venta y precios por producto y tienda; precios y calendario por la semana; venta y "
        "calendario por el día.",
        "Los vacíos de los eventos se segmentaron solo por periodo, la única dimensión del calendario. La semana sin precio se "
        "segmentó por periodo, tienda, estado, departamento y categoría. Un segmento no revisado puede esconder una concentración.",
        "En los eventos el doble del porcentaje global pasa del 100 %: ningún segmento puede llegar a él y el veredicto "
        "«repartidos» sale por construcción.",
        "Las cifras de la validación describen y no se cruzan con el precio, los eventos ni el SNAP, salvo las comprobaciones "
        "de las reglas que lo piden.",
        "Las cifras del diccionario no se recalculan: filas, columnas, tipos, vacíos, distintos, categorías raras y relaciones "
        "dentro de cada tabla.",
        "La prueba final no está en el caso y nada de este diagnóstico la mira.",
    ]
    paros = paradas(sum(negativos.values()), int(vsp.sum()))
    d["paradas"] = paros
    d["huellas_despues"] = {f"data/raw/{f}": huella(RAW / f) for f in FUENTES.values()}
    estado, riesgo = estado_y_riesgo([], paros, pendientes)
    d["resultado"].update(estado=estado, riesgo=riesgo, resumen=(
        f"Diagnóstico de las tres tablas con el plan aprobado: {fmt(len(problemas))} problemas y {fmt(len(pendientes))} "
        f"cuestiones pendientes. Las reglas que paran el trabajo no saltan: {fmt(sum(negativos.values()))} ventas negativas "
        f"y {fmt(int(vsp.sum()))} semanas con venta y sin precio. Lo que más pesa son {fmt(int(bajo.sum()))} precios por "
        f"debajo de 0,5 dólares y los saltos de nivel de {fmt(sc['series_con_salto'])} series en la construcción.")
        if not paros else
        "El trabajo para por una regla de negocio: " + "; ".join(f"{x['regla']} ({fmt(x['filas'])})" for x in paros) + ".")
    aplicar_validacion(d)
    d["duracion_segundos"] = round(time.time() - inicio, 1)
    return a_json_limpio(d)


# ══ 7. Informe Markdown, generado del JSON ═════════════════════════════════════
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


def lista(valores, vacio="ninguno"):
    """Lista en texto: «a; b; c»; `vacio` si no hay ninguno."""
    return "; ".join(str(v) for v in valores) if valores else vacio


def texto_atipicos(o):
    """Recuento de los dos métodos de atípicos; con dispersión cero, el método no se aplica y se dice."""
    def uno(n):
        """Un recuento, o el motivo de no tenerlo."""
        return fmt(n) if n is not None else "no se aplica, dispersión cero"
    return (f"rango intercuartílico {uno(o['iqr'])}; z robusto {uno(o['z_robusto'])}; los dos {uno(o['los_dos'])}; "
            f"de {fmt(o['valores'])} valores")


def frase(texto):
    """Primera letra en mayúscula, para empezar una frase con un texto del JSON."""
    return texto[:1].upper() + texto[1:] if texto else texto


PERIODO_TXT = {"construccion": "construcción", "validacion": "validación", "despues": "después de la fecha de referencia"}
CIFRAS_TXT = {"1": "1 cifra"}


def generar_md(d):
    """Escribe el informe para la persona a partir del diccionario d que se guardó como JSON; mismos apartados que la plantilla."""
    L = []
    a = L.append
    res = d["resultado"]
    a("# Calidad de los datos · caso 69\n")
    a(f"Informe generado por `{d['script']}` a partir de `informes/calidad-datos.json`. Estado **{res['estado']}**, "
      f"riesgo {res['riesgo']}. Fecha de los datos: {d['fecha_datos']}.\n")

    a("## Fuente analizada\n")
    for e in d["entradas"]:
        a(f"- `{e['ruta']}`: {fmt(e.get('bytes'))} bytes; {fmt(e.get('filas'))} filas; {fmt(e.get('columnas'))} columnas; "
          f"huella `{e['sha256']}`.")
    a(f"- Ejecutado el {str(d['fecha_ejecucion'])[:10]} con Python {d['entorno'].get('python')} y pandas "
      f"{d['entorno'].get('pandas')}, en {fmt(d.get('duracion_segundos'))} segundos.")
    dic = d.get("diccionario", {})
    a(f"- Partió del diccionario del origen: {fmt(d['con_diccionario'])} (estado {dic.get('estado')}, misma huella: "
      f"{fmt(dic.get('misma_huella'))}).")
    a(f"- Plan aprobado por {d['plan_aprobado']['por']} el {d['plan_aprobado']['fecha']}.\n")

    a("## Resumen\n")
    a(res["resumen"] + "\n")
    if d["pendientes"]:
        a("Lo que la persona responsable tiene que leer antes de corregir:\n")
        for p in d["pendientes"]:
            a(f"- **{p['id']}.** {p['pregunta']}")
        a("")

    a("## Inspección general\n")
    for t, v in d["inspeccion"].get("del_diccionario", {}).items():
        a(f"- {t}: {fmt(v['filas'])} filas y {fmt(v['columnas'])} columnas, según el diccionario; clave {', '.join(v['clave'])}.")
    cob = d["inspeccion"].get("cobertura", {})
    for p, v in cob.get("venta", {}).items():
        a(f"- Venta en la {PERIODO_TXT[p]}: del {v['desde']} al {v['hasta']}, {fmt(v['dias'])} días ({v['primera_columna']} "
          f"a {v['ultima_columna']}).")
    for p, v in cob.get("precios", {}).items():
        a(f"- Precios {p}: semanas {fmt(v['semana_minima'], True)} a {fmt(v['semana_maxima'], True)}, {fmt(v['filas'])} filas.")
    for p, v in cob.get("calendario", {}).items():
        a(f"- Calendario, {PERIODO_TXT[p]}: del {v['desde']} al {v['hasta']}, {fmt(v['dias'])} días.")
    sc = d["inspeccion"].get("semana_que_cruza")
    if sc:
        a(f"- La semana {fmt(sc['semana'], True)} tiene {fmt(sc['dias_en_construccion'])} días en la construcción y "
          f"{fmt(sc['dias_en_validacion'])} en la validación: lo que se reparte por semana se da hasta ella y después.")
    a("")

    a("## Estructura\n")
    for f in d["estructura"].get("forma", []):
        a(f"- {f['tabla']}, {f['rasgo']}: {f.get('detalle', fmt(f.get('resultado')))}"
          + (f" ({fmt(f['pct'])} % de las filas)." if f.get("pct") is not None else "."))
    a(f"- Columnas vacías: {lista(d['estructura'].get('columnas_vacias'), 'ninguna')}. Columnas constantes: "
      f"{lista(d['estructura'].get('columnas_constantes'), 'ninguna')}.")
    for n in d["nombres"]:
        a(f"- Nombre `{n['columna']}` de {n['tabla']}: normalizado `{n['normalizado']}`; colisión: {n['colision_con'] or 'ninguna'}.")
    a("")

    a("## Tipos y formatos\n")
    for t in d["tipos"]:
        if t["aviso"]:
            a(f"- {t['tabla']}.{t['columna']}: leído como {t['leido']}, toca {t['toca']} ({t['aviso']}); no se convierte el "
              f"{fmt(t['pct_no_convierte'])} %.")
    a("- Las demás columnas tienen el tipo que toca por su rol.")
    for e in d["escala"]:
        if e["grupo"] == "total":
            a(f"- Escala de {e['tabla']}.{e['columna']} en {PERIODO_TXT.get(e['periodo'], e['periodo'])}: "
              + "; ".join(f"{fmt(n)} valores de {CIFRAS_TXT.get(k, k + ' cifras')}" for k, n in e["cifras"].items())
              + f". Salto de escala: {fmt(e['salto'])}.")
    sal = [e for e in d["escala"] if e["salto"]]
    a(f"- Grupos por departamento y periodo con un hueco en el número de cifras: {len(sal)}.")
    epb = d.get("escala_precio_bajo") or {}
    if epb:
        a(f"- Los {fmt(epb['filas'])} precios por debajo de 0,5 dólares son de {fmt(epb['productos_tienda'])} productos-tienda; "
          f"{fmt(epb['productos_tienda_siempre_por_debajo'])} los tienen en todas sus semanas. En los demás, la mediana del "
          f"producto-tienda entre el precio bajo va de {fmt(epb['razon_mediana_entre_precio']['minima'])} a "
          f"{fmt(epb['razon_mediana_entre_precio']['maxima'])} veces: no es un factor uniforme.")
    a("")

    a("## Valores ausentes\n")
    for n in d["nulos_por_segmento"]:
        top = sorted(n["segmentos"], key=lambda s: -s["pct"])[:3]
        a(f"- {n['tabla']}.{n['columna']}: {fmt(n['global_pct'])} % global; veredicto **{n['veredicto']}**; segmentos con más: "
          + "; ".join(f"{s['dimension']} {PERIODO_TXT.get(s['segmento'], s['segmento'])} {fmt(s['pct'])} %" for s in top) + ".")
    ssp = d.get("semana_sin_precio") or {}
    if ssp:
        a(f"- Semanas producto-tienda sin precio: {fmt(ssp['sin_precio'])}, de ellas {fmt(ssp['antes_del_primer_precio'])} antes "
          f"del primer precio y {fmt(ssp['huecos_entre_primera_y_ultima'])} en huecos.")
    for c in d["codigos_de_ausencia"]:
        a(f"- Código «{c['codigo']}» en {c['tabla']}.{c['columna']} ({PERIODO_TXT.get(c['periodo'], c['periodo'])}): "
          f"{fmt(c['filas'])} ({fmt(c['pct_filas'])} %); documentado: {fmt(c['documentado'])}; {c['coincide_con']}.")
    hall = d["codigos_buscados"].get("hallados", []) if d.get("codigos_buscados") else []
    a(f"- Textos y números buscados como posibles códigos de ausencia en las tres tablas: {len(hall)} hallados.")
    for v in d["vacios_por_fila"]:
        a(f"- Vacíos por fila en {v['tabla']}: " + "; ".join(f"{fmt(n)} filas con {k}" for k, n in v["con_todas"].items())
          + ". Sin las columnas excluidas: " + "; ".join(f"{fmt(n)} filas con {k}" for k, n in v["sin_casi_vacias"].items()) + ".")
    a("")

    a("## Duplicados\n")
    for e in d["duplicados"]:
        a(f"- {e['tabla']}: {fmt(e['exactos'])} filas idénticas; {fmt(e['exactos_sin_identificadores'])} sin "
          f"{', '.join(e['identificadores_quitados']) or 'identificadores'}; {fmt(e['por_clave'])} claves repetidas; "
          f"{fmt(e['logicos'])} duplicados lógicos.")
        if "filas_con_los_mismos_dias_que_otra" in e:
            a("- Filas de la venta con los mismos días que otra: " + "; ".join(
                f"{PERIODO_TXT[p]} {fmt(n)}, de ellas {fmt(e['de_ellas_sin_ninguna_venta'][p])} sin ninguna venta"
                for p, n in e["filas_con_los_mismos_dias_que_otra"].items()) + ". Es evidencia, no un error.")
    a("")

    a("## Claves y granularidad\n")
    for g in d["claves_y_granularidad"]:
        a(f"- {g['tabla']}: una fila es {g['observada']}; clave {', '.join(g['clave'])}, única: {fmt(g['clave_unica'])}. "
          f"Discrepancia con la guía: {g['discrepancia']}.")
    a("")

    a("## Categóricas y texto\n")
    cat = d.get("categorias") or {}
    if cat:
        a("- Códigos fuera de las reglas, apartado 4: " + "; ".join(f"{c} {len(v)}" for c, v in cat["codigos_no_documentados"].items()) + ".")
        a(f"- Valores con espacios por fuera: {fmt(sum(cat['espacios_externos'].values()))}. Variantes de mayúsculas: "
          f"{fmt(sum(cat['variantes_de_mayusculas'].values()))}.")
        es = cat["estilo_de_los_nombres_de_evento"]
        a(f"- Los {fmt(es['nombres'])} nombres de evento mezclan estilos: {fmt(es['con_espacios'])} con espacios, "
          f"{fmt(es['con_apostrofo'])} con apóstrofo, {fmt(es['con_guion'])} con guion y {fmt(es['pegados_con_mayusculas'])} "
          "pegados con mayúsculas. Al normalizarlos no se junta ninguno."
          if sum(v["formas_que_se_juntan"] for v in d["duplicados_logicos"].values()) == 0 else
          f"- Los {fmt(es['nombres'])} nombres de evento mezclan estilos y alguno se junta al normalizar.")
    raras = {}
    for r in d["categorias_raras"]:
        raras.setdefault(f"{r['tabla']}.{r['columna']}", []).append(r)
    for c, rs in raras.items():
        a(f"- Categorías raras de {c}, del diccionario: {len(rs)}. Quedan como están por D2, cerrada el 21/11/2026.")
    a("")

    a("## Numéricas y outliers\n")
    a("Los límites solo detectan: un atípico no es un error.\n")
    for o in d["outliers"]:
        if o["grupo"] == "total":
            a(f"- {o['tabla']}, {PERIODO_TXT.get(o['periodo'], o['periodo'])}: Q1 {fmt(round(o['q1'], 2))}, Q3 "
              f"{fmt(round(o['q3'], 2))} y mediana {fmt(round(o['mediana'], 2))}; {texto_atipicos(o)}.")
    for c in d["colas"]:
        if c["grupo"] == "total":
            a(f"- Colas de {c['tabla']} en {PERIODO_TXT.get(c['periodo'], c['periodo'])}: los más bajos "
              + ", ".join(fmt(v["valor"]) for v in c["bajos"]) + "; los más altos " + ", ".join(fmt(v["valor"]) for v in c["altos"])
              + (f"; mayor salto de {fmt(c['mayor_salto']['desde'])} a {fmt(c['mayor_salto']['hasta'])}." if c["mayor_salto"] else "."))
    a("- Las colas, la escala y los atípicos de cada departamento están en el JSON, en `colas`, `escala` y `outliers`.\n")

    a("## Fechas\n")
    for f in d["fechas"]:
        a(f"- {f['tabla']}.{f['columna']}: del {f['minimo']} al {f['maximo']}; convención {f['convencion']}"
          + (f", demostrada con {fmt(f['fechas_con_dia_mayor_que_12'])} fechas de día mayor que 12" if f.get("demostrada") else "") + ".")
    cal = next((f for f in d["fechas"] if f["tabla"] == "calendario"), None)
    if cal:
        a(f"- El calendario sigue {fmt(cal['dias_despues_de_la_fecha_de_referencia'])} días después de la fecha de referencia. "
          "No son de ningún periodo: se describen aparte y no se marcan como futuros.")
    a("")

    a("## Reglas lógicas e integridad\n")
    for r in d["comprobaciones_reglas"]:
        a(f"- **{r['id']}**, {r['regla']}: " + resumen_regla(r) + ".")
    a("")
    a("Lo que dejó el reconocimiento, medido en cada periodo:\n")
    for q in d["reconocimiento"]:
        a(f"- **{q['id']}**, {q['cuestion']}: " + resumen_cuestion(q, d) + ".")
    a("")
    a("Riesgos para un modelo, solo señalados:\n")
    for r in d["riesgos_modelo"]:
        a(f"- {r['tabla']}.{r['columna']}: {r['riesgo']}.")
    a("")

    a("## Cruces entre tablas\n")
    for c in d["cruces"]:
        a(f"- {c['izquierda']} con {c['derecha']} por {', '.join(c['clave'])} ({c['cardinalidad_esperada']}, relación supuesta): "
          f"{fmt(c['sin_pareja_izquierda'])} claves de la izquierda sin pareja y {fmt(c['sin_pareja_derecha'])} de la derecha; "
          f"formato distinto: {fmt(c['formato_distinto'])}.")
    a("")

    a("## Reglas candidatas para aprobar\n")
    a(f"Las nueve viñetas del plan dan {fmt(len(d['reglas_candidatas']))} reglas, cada una contada por separado. Son comprobaciones aprobadas con el plan "
      "(D3, 21/11/2026); pasarlas a las reglas de negocio va por la cascada.\n")
    for r in d["reglas_candidatas"]:
        a(f"- **{r['id']}** ({r['tabla']}: {', '.join(r['columnas'])}). {frase(r['regla'])}. La incumplen "
          f"{fmt(r['filas_que_incumplen'])} {r['unidad']}.")
    a("")

    a("## Resumen de problemas detectados\n")
    for p in d["problemas"]:
        a(f"- **{p['id']}** ({p['bloque']}, {p['tabla']}.{p['columna']}): {p['resultado']}. {frase(p['observacion'])}.")
    a("")

    a("## Posibles acciones\n")
    a("Ninguna se ejecuta en esta fase.\n")
    for p in d["problemas"]:
        if p["posible_accion"] and p["posible_accion"] != "ninguna":
            a(f"- {p['id']}: {p['posible_accion']}.")
    for p in d["pendientes"]:
        a(f"- {p['id']}, para la persona responsable: {p['pregunta']} Lecturas: "
          + "; ".join(f"({i + 1}) {o}" for i, o in enumerate(p["opciones"])) + f". Después, {p['nota']}.")
    a("")
    a("Las cuestiones pendientes no eligen ninguna lectura: las decide la persona responsable.")
    a("")

    a("## Parámetros usados\n")
    for p in d["parametros"]:
        valor = ", ".join(fmt(v) for v in p["valor"]) if isinstance(p["valor"], list) else fmt(p["valor"])
        a(f"- {p['nombre']}: {valor} ({p['origen']}).")
    for dc in d["decisiones_cerradas"]:
        a(f"- {dc['id']}, {dc['que']}: cerrada el {dc['fecha']}.")
    a("- Teoría del manual aplicada: " + "; ".join(f"{t['apartado']}, {t['por_que']}" for t in d["teoria_aplicada"]) + ".\n")

    a("## Datos personales\n")
    a(d["datos_personales_nota"] + "\n")

    a("## Límites de esta revisión\n")
    for lim in d["limites"]:
        a(f"- {lim}")
    for n in d["no_aplicado"]:
        a(f"- No se aplicó {n['control']}: {n['motivo']}.")
    a("")
    return "\n".join(L)


def resumen_regla(r):
    """Una línea con la cifra de cada una de las siete reglas del plan."""
    v = r["resultado"]
    if r["id"] == "R-1":
        return "; ".join(f"{PERIODO_TXT[p]} {fmt(c['a_cero'])} celdas a cero ({fmt(c['pct'])} %)" for p, c in v.items())
    if r["id"] == "R-2":
        return f"{fmt(v['total'])} cierres; " + "; ".join(
            f"{PERIODO_TXT[p]} {fmt(c['cierres'])}, {fmt(c['en_navidad'])} en Navidad" for p, c in v["por_periodo"].items())
    if r["id"] == "R-3":
        return ("semanas con venta y sin precio " + "; ".join(f"{k} {fmt(n)}" for k, n in v["semanas_con_venta_sin_precio"].items())
                + "; con precio y sin venta " + "; ".join(f"{k} {fmt(n)}" for k, n in v["semanas_con_precio_sin_venta"].items()))
    if r["id"] == "R-4":
        return f"{fmt(v['filas_con_la_clave_repetida'])} claves repetidas"
    if r["id"] == "R-5":
        return "; ".join(f"{PERIODO_TXT[p]} {fmt(n)} negativos" for p, n in v["negativos"].items())
    if r["id"] == "R-6":
        return "días con evento: " + "; ".join(f"{PERIODO_TXT[p]} {fmt(n)}" for p, n in v["dias_con_evento"].items())
    if r["id"] == "R-7":
        return (f"{fmt(v['por_debajo'])} por debajo de 0,5 (" + "; ".join(f"{k} {fmt(n)}" for k, n in v["por_periodo"].items())
                + f"); mínimo {fmt(v['minimo'])}; {fmt(v['por_encima'])} por encima de 50")
    return ""


def resumen_cuestion(q, d):
    """Una línea con la cifra de cada cuestión del reconocimiento."""
    v = q["resultado"]
    if q["id"] == "Q-1":
        partes = []
        for p, c in v.items():
            m = d["saltos_de_nivel"]["por_periodo"][p]["mayor"]
            partes.append(f"{PERIODO_TXT[p]} {fmt(c['series_con_salto'])} series ({fmt(c['bajadas'])} bajadas)"
                          + (f", la mayor {m['nombre']} con {fmt(m['razon'])} el {m['fecha']}" if m else "")
                          + f"; tiendas con salto: {lista(c['tiendas_con_salto'], 'ninguna')}")
        return "; ".join(partes)
    if q["id"] == "Q-2":
        return ("; ".join(f"{PERIODO_TXT[p]} {fmt(v[p]['de_productos_tienda_que_empiezan_a_vender_en_el_periodo'])} días de "
                          f"productos-tienda que empiezan a vender en ella, más {fmt(v[p]['de_productos_tienda_que_aun_no_venden_al_acabar_el_periodo'])} "
                          f"de {fmt(v[p]['productos_tienda_que_aun_no_venden_al_acabar_el_periodo'])} que aún no venden al acabarla"
                          for p in ("construccion", "validacion"))
                + f"; {fmt(v['productos_tienda_que_venden_por_primera_vez_en_la_validacion'])} productos-tienda venden por "
                  "primera vez en la validación")
    if q["id"] == "Q-3":
        return "; ".join(f"{PERIODO_TXT[p]} {fmt(c['fuera_de_cierres'])} días, racha más larga de {fmt(c['racha_mas_larga']['dias'])} "
                         f"en {c['racha_mas_larga']['serie']}" for p, c in v.items())
    if q["id"] == "Q-4":
        return lista([f"{c['tienda']} el {c['fecha']}, evento: {c['evento'] or 'ninguno'}" for c in v["cierres_fuera_de_navidad"]])
    if q["id"] == "Q-5":
        return "; ".join(f"{a} {fmt(n)} unidades" for a, n in v["por_ano"].items())
    if q["id"] == "Q-6":
        return (f"construcción {fmt(v['construccion'])}; validación {fmt(v['validacion'])}; en ninguno de los dos "
                f"{fmt(v['en_ninguno_de_los_dos'])}, de ellos {fmt(v['en_ninguno_sin_ningun_precio'])} sin ningún precio")
    if q["id"] == "Q-7":
        x = v["dias_entre_primer_precio_y_primera_venta"]
        r = v["como_el_reconocimiento"]
        return (f"de {fmt(v['productos_tienda_con_precio_y_venta'])} productos-tienda con precio y venta, {fmt(x['de_0_a_6'])} "
                f"venden de 0 a 6 días después del primer precio y {fmt(x['antes_del_precio'])} antes. De los que empiezan a "
                "vender después del primer día, tienen el precio de 0 a 6 días antes " + "; ".join(
                    f"{fmt(c['precio_de_0_a_6_dias_antes'])} de {fmt(c['empiezan_a_vender_despues_del_primer_dia'])} en la "
                    f"{PERIODO_TXT[p]}" for p, c in r.items()))
    return ""


def resultado_minimo_de_prueba():
    """Un resultado mínimo, con todas las claves, para probar que el informe tiene sus 19 apartados."""
    d = esqueleto()
    d.update(fecha_ejecucion="2026-01-01T00:00:00", entorno={"python": "x", "pandas": "y"})
    d["resultado"].update(estado="OK", riesgo="bajo", resumen="Prueba.")
    d["codigos_buscados"] = {"hallados": []}
    return d


# ══ 8. Ejecución ════════════════════════════════════════════════════════════════
def main():
    """Construye el diagnóstico, escribe el JSON y genera de él el Markdown; si algo falla, deja el JSON con ERROR."""
    print("intérprete:", sys.executable)
    try:
        d = construir()
    except Exception as error:
        d = esqueleto()
        d["fecha_ejecucion"] = datetime.now().isoformat(timespec="seconds")
        d["resultado"].update(estado="ERROR", riesgo="alto", resumen=f"{type(error).__name__}: {error}",
                              artefactos=["informes/calidad-datos.json"], siguiente="arreglar el fallo")
        escribir_json(SALIDA_JSON, d)
        raise
    texto_json = json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False)
    texto_md = generar_md(json.loads(texto_json))
    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.write_text(texto_json, encoding="utf-8")
    SALIDA_MD.write_text(texto_md, encoding="utf-8")
    print("estado:", d["resultado"]["estado"], "· riesgo:", d["resultado"]["riesgo"])
    print("resumen:", d["resultado"]["resumen"])
    print("validación:", d["validacion"].get("fallos") if d.get("validacion") else "no se llegó a validar")
    print("segundos:", d["duracion_segundos"])
    return 0 if d["resultado"]["estado"] in ("OK", "AVISO") else 1


if __name__ == "__main__":
    sys.exit(main())
