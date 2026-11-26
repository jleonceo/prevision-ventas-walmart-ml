"""Cuadro de mando del caso 69 para la Dirección de Operaciones de Tiendas.

Un solo HTML que se abre sin internet, con cinco pestañas (visión general, el pedido, dónde gana, festivos y próximos
días, en el orden del guion aprobado) y cuatro filtros que valen para todas, de lo general a lo concreto
(estado, tienda, categoría y departamento). Los gráficos son SVG dibujados por el JavaScript del propio HTML, porque
los filtros los redibujan.

Lee, sin cambiarlos:
- informes/prueba_final.json (scripts/20_prueba_final.py): las cifras del informe final que el cuadro repite, los
  orígenes, las vísperas de festivo, el mínimo de pruebas para ganar y la regla que se recomienda en cada departamento;
- data/processed/previsiones_prueba_final.parquet (scripts/20): una fila por prueba, combinación y día del último año
  guardado, con la venta real, el modelo y las tres reglas; solo la variante «reentrenado», el modelo en uso;
- data/processed/prueba_final/hechos_prueba_final.parquet (scripts/20): la venta real hasta el 22/05/2016, para la media
  de los últimos 28 días de HOBBIES_2 en los próximos días y para comprobar la venta por otro camino;
- data/processed/dim_tienda.parquet y dim_producto.parquet (scripts/05): el estado de cada tienda y la categoría de cada
  departamento;
- data/predicciones/desde_2016-05-22/previsiones_lote.parquet y resumen.json (produccion/lote_prueba_final.py con
  --origen 2016-05-22): la previsión de los 28 días siguientes al último dato;
- produccion/configuracion.json: el modelo en uso, para comprobar que el lote se hizo con él.

Deja informes/cuadro_mando.html, informes/cuadro_mando.json e informes/cuadro_mando_proximos_dias.csv (la lista de los
próximos días sin filtros).

Orden: cada entrada tiene que ser más nueva que el script que la crea (ver ENTRADAS).

Para sin escribir nada si: una entrada es más vieja que su script; una cifra que repite del informe no es la de
prueba_final.json; la venta en dólares no da lo mismo por otro camino; el lote de los próximos días no es el del modelo
en uso, no trae 70 combinaciones por 10 días en unidades y 28 en dólares o trae vacíos o negativos; la regla que se
recomienda no es la media de los últimos 28 días solo en HOBBIES_2; la huella de data/raw/ no es la de la prueba final;
sale una palabra que la hoja de vocabulario no usa; o una validación lleva su resultado escrito. Si cambia la huella de
data/ durante la ejecución, borra el HTML y el CSV y para.

Pruebas: tests/probar_21_cuadro_mando.py, tests/probar_21_cuadro_mando_pestanas.py y
tests/probar_21_cuadro_mando_navegador.py.

No importa ningún script numerado. Importa scripts/prevision_recursiva.py (módulo de funciones: las tres reglas y el
redondeo de las unidades).

Uso, desde cualquier carpeta:
    python -W error scripts/21_cuadro_mando.py
"""

# =====================================================================================================================
# CONFIGURACIÓN
# =====================================================================================================================

# datetime pone la fecha de ejecución
import datetime as dt
# hashlib calcula las huellas de data/
import hashlib
# json lee las entradas y escribe el JSON del cuadro
import json
# math redondea hacia arriba el mínimo de pruebas
import math
# re busca resultados escritos y palabras vetadas
import re
# sys añade scripts/ a la ruta de importación y comprueba el intérprete
import sys
# time mide lo que tarda cada apartado de principal()
import time
# Decimal redondea el CSV como Excel
from decimal import Decimal, ROUND_HALF_UP
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

import numpy as np
import pandas as pd

# Carpeta del caso, calculada desde el propio script para que funcione lo lance quien lo lance
RAIZ = Path(__file__).resolve().parents[1]
# El módulo de las reglas sencillas, desde scripts/
sys.path.insert(0, str(RAIZ / "scripts"))

import prevision_recursiva as pr  # noqa: E402

# Intérprete del caso
ENTORNO = "69_prevision_ventas_walmart"
SCRIPT = "scripts/21_cuadro_mando.py"
SALIDA_HTML = RAIZ / "informes" / "cuadro_mando.html"
SALIDA_JSON = RAIZ / "informes" / "cuadro_mando.json"
SALIDA_CSV = RAIZ / "informes" / "cuadro_mando_proximos_dias.csv"

# Entradas y el script que crea cada una (para comprobar el orden)
PRUEBA_FINAL = "informes/prueba_final.json"
PREVISIONES = "data/processed/previsiones_prueba_final.parquet"
HECHOS_PF = "data/processed/prueba_final/hechos_prueba_final.parquet"
DIM_TIENDA = "data/processed/dim_tienda.parquet"
DIM_PRODUCTO = "data/processed/dim_producto.parquet"
LOTE = "data/predicciones/desde_2016-05-22"
LOTE_PARQUET = f"{LOTE}/previsiones_lote.parquet"
LOTE_RESUMEN = f"{LOTE}/resumen.json"
CONFIGURACION = "produccion/configuracion.json"
ENTRADAS = [(PRUEBA_FINAL, "scripts/20_prueba_final.py"), (PREVISIONES, "scripts/20_prueba_final.py"),
            (HECHOS_PF, "scripts/20_prueba_final.py"), (DIM_TIENDA, "scripts/05_transformacion_datos.py"),
            (DIM_PRODUCTO, "scripts/05_transformacion_datos.py"), (LOTE_PARQUET, "produccion/lote_prueba_final.py"),
            (LOTE_RESUMEN, "produccion/lote_prueba_final.py")]

# La variante del modelo en uso y las fechas: el último dato y el día desde el que se prevé (guion §4)
VARIANTE = "reentrenado"
FECHA_DATOS = "2016-05-22"
ORIGEN_PROXIMOS = pd.Timestamp("2016-05-22")
# Las tres reglas sencillas, en su orden y con su nombre entero (reglas, apartado 7; hoja de vocabulario)
REGLAS = list(pr.REGLAS)
NOMBRES_REGLAS = {"repetir_semana_anterior": "repetir la semana anterior",
                  "media_28_dias": "la media de los últimos 28 días",
                  "media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores"}
# Los nombres del lector para los estados y las categorías (hoja de vocabulario, aprobada en una nota interna)
ESTADOS = {"CA": "California", "TX": "Texas", "WI": "Wisconsin"}
CATEGORIAS = {"FOODS": "alimentación", "HOBBIES": "ocio", "HOUSEHOLD": "hogar"}
# Parte mínima de pruebas que gana el modelo para decir que falla menos: el 75 %, redondeando hacia arriba (reglas, apartado 7)
PARTE_GANA = 0.75
# Tolerancia al comparar con el JSON, que guarda las cifras con toda su precisión
TOLERANCIA = 1e-9
# Palabras que la hoja de vocabulario dice que no se usan, en todo el HTML (también en el JavaScript)
PROHIBIDAS = [r"\bseries?\b", r"predicci", r"pron[oó]stico", r"\bWAPE\b", r"\bHGB\b", r"la mejor regla", r"\brival\b",
              r"benchmark", r"\bhorizonte\b", r"m[eé]todo actual", r"sucursal", r"Thanksgiving", r"Christmas",
              r"NewYear", r"\bimpagad", r"reposici[oó]n", r"aprovisionamiento", r"d[ií]a SNAP"]
# Las validaciones del JSON, que la prueba busca para que ninguna lleve su resultado escrito
VALIDACIONES = ["entradas_mas_nuevas", "fecha_datos_igual", "lote_del_modelo_en_uso", "lote_completo",
                "recomendado_del_json", "cifras_iguales_al_json", "venta_por_otro_camino", "raw_igual_que_la_prueba",
                "huella_data_igual", "sin_resultados_escritos", "sin_palabras_vetadas"]


def reloj():
    """Una función que imprime los segundos desde la llamada anterior y el total, con el nombre del apartado."""
    inicio = [time.perf_counter()] * 2

    def marca(apartado):
        """Imprime lo que tardó el apartado que acaba."""
        ahora = time.perf_counter()
        print(f"tiempo {apartado}: {ahora - inicio[1]:.1f} s (total {ahora - inicio[0]:.1f} s)", flush=True)
        inicio[1] = ahora
    return marca


class Parada(Exception):
    """El cuadro no se escribe: algo de lo que comprueba no cuadra."""


# =====================================================================================================================
# AYUDAS
# =====================================================================================================================

def exigir(condicion, mensaje):
    """Para con el mensaje si la condición no se cumple."""
    if not condicion:
        raise Parada(mensaje)


def sha256(ruta):
    """SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def huella_data(raiz):
    """Huella de toda la carpeta data/: una línea por fichero con su huella, y la huella de esas líneas."""
    base = Path(raiz) / "data"
    lineas = [f"{p.relative_to(raiz).as_posix()} {sha256(p)}" for p in sorted(base.rglob("*")) if p.is_file()]
    return {"ficheros": len(lineas), "sha256": hashlib.sha256("\n".join(lineas).encode("utf-8")).hexdigest()}


def leer_json(ruta):
    """Un JSON en UTF-8."""
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def comprobar_orden(pares):
    """Para si alguna entrada es más vieja que el script que la crea. `pares`: [(entrada, script)]."""
    viejas = [str(e) for e, s in pares if Path(e).stat().st_mtime < Path(s).stat().st_mtime]
    if viejas:
        raise Parada(f"orden: estas entradas son más viejas que el script que las crea; relánzalo: {viejas}")
    return True


def nativo(x):
    """Valores de numpy y pandas a tipos de Python; NaN a None (un JSON no lleva NaN)."""
    if isinstance(x, dict):
        return {str(k): nativo(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [nativo(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(float(x)) else float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if x is pd.NA or x is pd.NaT:
        return None
    return x


def iguales(a, b, tolerancia=TOLERANCIA):
    """Dos cifras iguales con tolerancia relativa; vacío solo con vacío."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tolerancia * max(1.0, abs(float(b)))


def buscar_resultados_escritos(texto):
    """Líneas del código con una validación puesta a True; la prueba pide que el script no tenga ninguna."""
    claves = "|".join(VALIDACIONES + ["cifras_iguales_al_json"])
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def sin_prohibidas(texto):
    """Las palabras o frases vetadas que lleve un texto."""
    return sorted({m.group(0) for p in PROHIBIDAS for m in re.finditer(p, texto, flags=re.I)})


def fecha_es(fecha):
    """Una fecha como 22/05/2016."""
    return pd.Timestamp(fecha).strftime("%d/%m/%Y")


# =====================================================================================================================
# LA MEDIDA (reglas, apartado 6 y §7), la misma cuenta que hace el JavaScript
# =====================================================================================================================

def error_sesgo(real, previsto):
    """Error y exceso por cada 100 vendidas: |previsto − real| y (previsto − real) sumados, entre lo real, por 100.

    Es la cuenta de prevision_recursiva.error_y_sesgo, que para si la venta suma cero; aquí da (None, None), porque una
    selección pequeña puede no tener venta. La prueba compara las dos.
    """
    total = float(np.sum(real))
    if not total > 0:
        return None, None
    d = np.asarray(previsto, dtype="float64") - np.asarray(real, dtype="float64")
    return float(100 * np.abs(d).sum() / total), float(100 * d.sum() / total)


def menor(valores):
    """La posición del menor valor; con empate, la primera (el orden de las reglas)."""
    k = 0
    for j in range(1, len(valores)):
        if valores[j] < valores[k]:
            k = j
    return k


def medidas(real, modelo, reglas):
    """Error y exceso del modelo y de cada regla con las mismas filas; None si no hay venta."""
    em, sm = error_sesgo(real, modelo)
    if em is None:
        return None
    er = [error_sesgo(real, r) for r in reglas]
    return {"modelo": em, "sesgo": sm, "reglas": [e for e, _ in er], "sesgos": [s for _, s in er]}


def minimo_gana(de, parte=PARTE_GANA):
    """Las pruebas que tiene que ganar el modelo para decir que falla menos: el 75 % redondeando hacia arriba."""
    return math.ceil(parte * de - 1e-9)


# =====================================================================================================================
# DATOS DEL HTML
# =====================================================================================================================

def _bloque(tabla, indice, origenes):
    """Una tabla de previsiones como columnas: combinación, prueba, día, hueco (prueba y día) y lo previsto.

    Las filas fuera del error (el 25 de diciembre, reglas, apartado 6) no entran: no cuentan en ninguna cifra ni en los gráficos.
    """
    t = tabla[~tabla["fuera_del_error"].to_numpy()].sort_values(["origen", "date", "store_id", "dept_id"],
                                                                kind="stable")
    fechas = sorted(t["date"].unique())
    pos_fecha = {f: i for i, f in enumerate(fechas)}
    huecos = list(dict.fromkeys(zip(t["origen"], t["date"])))
    pos_hueco = {k: i for i, k in enumerate(huecos)}
    pos_origen = {pd.Timestamp(o): i for i, o in enumerate(origenes)}
    return {"c": [indice[(s, d)] for s, d in zip(t["store_id"], t["dept_id"])],
            "o": [pos_origen[pd.Timestamp(o)] for o in t["origen"]],
            "t": [pos_fecha[f] for f in t["date"]],
            "s": [pos_hueco[k] for k in zip(t["origen"], t["date"])],
            "real": t["real"].astype(float).tolist(), "modelo": t["modelo"].astype(float).tolist(),
            "r": [t[r].astype(float).tolist() for r in REGLAS],
            "fechas": [pd.Timestamp(f).strftime("%Y-%m-%d") for f in fechas], "huecos": len(huecos)}


def preparar_datos(prev, dim_tienda, dim_producto, lote, regla_prox, festivos, origenes, recomendado, minimo):
    """Todo lo que el navegador necesita para filtrar sin volver a Python, como listas (sin NaN).

    prev: previsiones_prueba_final.parquet; lote: el de los próximos días; regla_prox: la media de los últimos 28 días
    de cada combinación y día de los próximos días; festivos: [{nombre, origen}]; origenes: los 13 días de partida;
    recomendado: departamento → «modelo» o la regla que se recomienda; minimo: pruebas que hay que ganar.
    """
    prev = prev[(prev["variante"] == VARIANTE).to_numpy()]
    exigir(len(prev) > 0, f"previsiones_prueba_final no trae la variante {VARIANTE}")
    est_de = dict(zip(dim_tienda["store_id"], dim_tienda["state_id"]))
    cat_de = dict(zip(dim_producto["dept_id"], dim_producto["cat_id"]))
    exigir(set(est_de.values()) <= set(ESTADOS) and set(cat_de.values()) <= set(CATEGORIAS),
           f"un estado o una categoría sin nombre del lector: {set(est_de.values())}, {set(cat_de.values())}")
    # Combinaciones de lo general a lo concreto: estado, tienda, categoría y departamento (D8)
    tiendas = sorted(set(prev["store_id"]), key=lambda s: (list(ESTADOS).index(est_de[s]), s))
    deps = sorted(set(prev["dept_id"]), key=lambda d: (list(CATEGORIAS).index(cat_de[d]), d))
    combos = [(t, d) for t in tiendas for d in deps]
    indice = {k: i for i, k in enumerate(combos)}
    pos_t, pos_d = {t: i for i, t in enumerate(tiendas)}, {d: i for i, d in enumerate(deps)}
    ordinaria = (prev["prueba"] == "ordinaria").to_numpy()
    u = _bloque(prev[ordinaria & (prev["objetivo"] == "unidades").to_numpy()], indice, origenes)
    d = _bloque(prev[ordinaria & (prev["objetivo"] == "dolares").to_numpy()], indice, origenes)
    f = _bloque(prev[(prev["prueba"] == "festivo").to_numpy() & (prev["objetivo"] == "unidades").to_numpy()], indice,
                [x["origen"] for x in festivos])
    exigir(len(set(u["o"])) == len(origenes) and len(set(d["o"])) == len(origenes) and len(set(f["o"])) == len(festivos),
           "faltan pruebas en previsiones_prueba_final")
    # Los próximos días: el modelo, salvo donde se recomienda una regla (HOBBIES_2, la media de los últimos 28 días)
    exigir(set(lote["prueba"]) == {"proximos_dias"}, f"el lote no es el de los próximos días: {set(lote['prueba'])}")
    exigir(not lote["prevision"].isna().any(), f"el lote trae {int(lote['prevision'].isna().sum())} previsiones vacías")
    exigir(bool((lote["prevision"] >= 0).all()), "el lote trae previsiones negativas")
    exigir(set(zip(lote["store_id"], lote["dept_id"])) == set(combos), "el lote no trae las mismas combinaciones")
    fechas_p = sorted(lote.loc[(lote["objetivo"] == "dolares").to_numpy(), "date"].unique())
    dias_u = int(lote.loc[(lote["objetivo"] == "unidades").to_numpy(), "date"].nunique())
    regla = regla_prox.set_index(["store_id", "dept_id", "date"])
    ldol = lote[(lote["objetivo"] == "dolares").to_numpy()].set_index(["store_id", "dept_id", "date"])["prevision"]
    luni = lote[(lote["objetivo"] == "unidades").to_numpy()].set_index(["store_id", "dept_id", "date"])["prevision"]
    exigir(not ldol.index.duplicated().any() and not luni.index.duplicated().any(), "el lote trae claves repetidas")
    prox = {"c": [], "t": [], "unidades": [], "dolares": [], "regla": []}
    for (s, dep) in combos:
        con = recomendado.get(dep, "modelo")
        for i, fe in enumerate(fechas_p):
            k = (s, dep, fe)
            if con == "modelo":
                uu = float(luni[k]) if k in luni.index else None
                dd = float(ldol[k])
            else:
                uu = float(regla.loc[k, "unidades"]) if k in luni.index else None
                dd = float(regla.loc[k, "dolares"])
            prox["c"].append(indice[(s, dep)])
            prox["t"].append(i)
            prox["unidades"].append(uu)
            prox["dolares"].append(dd)
            prox["regla"].append(0 if con == "modelo" else 1)
    return nativo({
        "fecha_datos": FECHA_DATOS, "origen_proximos": ORIGEN_PROXIMOS.strftime("%Y-%m-%d"), "minimo_gana": minimo,
        "reglas": REGLAS, "nombres_reglas": NOMBRES_REGLAS,
        "estados": [{"id": e, "nombre": ESTADOS[e]} for e in ESTADOS if e in set(est_de[t] for t in tiendas)],
        "tiendas": [{"id": t, "estado": est_de[t]} for t in tiendas],
        "categorias": [{"id": c, "nombre": CATEGORIAS[c]} for c in CATEGORIAS if c in set(cat_de[x] for x in deps)],
        "departamentos": [{"id": x, "categoria": cat_de[x]} for x in deps],
        "combos": {"tienda": [pos_t[t] for t, _ in combos], "departamento": [pos_d[x] for _, x in combos]},
        "origenes": [pd.Timestamp(o).strftime("%Y-%m-%d") for o in origenes], "festivos": festivos,
        "recomendado": recomendado, "u": u, "d": d, "f": f,
        "proximos": prox, "fechas_proximos": [pd.Timestamp(x).strftime("%Y-%m-%d") for x in fechas_p],
        "dias_unidades": dias_u})


def recomendado_de(pf):
    """Departamento → «modelo» o la regla que se recomienda, del JSON (reglas, apartado 7), igual en los dos objetivos.

    El guion aprobado y la petición 32 dicen HOBBIES_2 con la media de los últimos 28 días: si el JSON dice otra cosa,
    para.
    """
    nombre_a_clave = {v: k for k, v in NOMBRES_REGLAS.items()}
    salida = {}
    for objetivo in ("unidades", "dolares"):
        uno = {}
        for x in pf[VARIANTE][objetivo]["recomendacion_por_departamento"]:
            uno[x["departamento"]] = "modelo" if x["se_recomienda"] == "el modelo" else nombre_a_clave.get(x["se_recomienda"])
        exigir(None not in uno.values(), f"una recomendación sin regla conocida en {objetivo}: {uno}")
        if salida:
            exigir(uno == salida, f"la recomendación cambia entre unidades y dólares: {salida} y {uno}")
        salida = uno
    con_regla = {k: v for k, v in salida.items() if v != "modelo"}
    exigir(con_regla == {"HOBBIES_2": "media_28_dias"},
           f"la regla que se recomienda no es la media de los últimos 28 días solo en HOBBIES_2: {con_regla}")
    return salida


def reglas_para_proximos(hechos, origen, plazos):
    """La media de los últimos 28 días desde el origen para cada combinación y día de los próximos días.

    Usa prevision_recursiva.reglas_sencillas (la misma función que midió las reglas), con la venta real hasta el
    origen. Las unidades, acotadas en cero y redondeadas como se miden; vacías pasado su plazo. plazos: {unidades,
    dolares} en días.
    """
    partes = []
    for objetivo in ("unidades", "dolares"):
        try:
            r = pr.reglas_sencillas(hechos[["store_id", "dept_id", "date", objetivo]], objetivo, origen,
                                    int(plazos["dolares"]))
        except ValueError as error:
            raise Parada(f"la media de los últimos 28 días no se puede calcular en {objetivo}: {error}") from error
        valor = np.clip(r["media_28_dias"].to_numpy(dtype="float64"), 0, None)
        if objetivo == "unidades":
            valor = pr.redondear_unidades(valor)
            valor = np.where(r["h"].to_numpy() <= int(plazos["unidades"]), valor, np.nan)
        partes.append(r[["store_id", "dept_id", "date"]].assign(**{objetivo: valor}))
    return partes[0].merge(partes[1], on=["store_id", "dept_id", "date"], how="outer", validate="one_to_one")


# =====================================================================================================================
# RESUMEN EN PYTHON: LAS CIFRAS DE ARRIBA PARA CUALQUIER FILTRO (lo que compara la prueba del navegador)
# =====================================================================================================================

def normalizar(datos, f):
    """Los filtros válidos, con el estado de la tienda y la categoría del departamento; lo que no existe se quita."""
    est = {t["id"]: t["estado"] for t in datos["tiendas"]}
    cat = {x["id"]: x["categoria"] for x in datos["departamentos"]}
    salida = {}
    estado = f.get("estado") if f.get("estado") in {e["id"] for e in datos["estados"]} else None
    tienda = f.get("tienda") if f.get("tienda") in est else None
    categoria = f.get("categoria") if f.get("categoria") in {c["id"] for c in datos["categorias"]} else None
    dep = f.get("departamento") if f.get("departamento") in cat else None
    if tienda is not None:
        estado = est[tienda]
    if dep is not None:
        categoria = cat[dep]
    for k, v in (("estado", estado), ("tienda", tienda), ("categoria", categoria), ("departamento", dep)):
        if v is not None:
            salida[k] = v
    return salida


def seleccion(datos, f):
    """Las combinaciones que pasan los filtros, como lista de verdadero o falso."""
    f = normalizar(datos, f)
    salida = []
    for it, idp in zip(datos["combos"]["tienda"], datos["combos"]["departamento"]):
        t, x = datos["tiendas"][it], datos["departamentos"][idp]
        salida.append((f.get("estado") in (None, t["estado"])) and (f.get("tienda") in (None, t["id"]))
                      and (f.get("categoria") in (None, x["categoria"])) and (f.get("departamento") in (None, x["id"])))
    return np.array(salida, dtype=bool)


def _arr(datos, b):
    """Las columnas de un bloque como arrays de numpy, guardadas en los datos para no rehacerlas."""
    clave = "_np_" + b
    if clave not in datos:
        x = datos[b]
        datos[clave] = {"c": np.asarray(x["c"], dtype=np.int64), "o": np.asarray(x["o"], dtype=np.int64),
                        "t": np.asarray(x["t"], dtype=np.int64), "s": np.asarray(x["s"], dtype=np.int64),
                        "real": np.asarray(x["real"], dtype=float), "modelo": np.asarray(x["modelo"], dtype=float),
                        "r": [np.asarray(v, dtype=float) for v in x["r"]], "huecos": int(x["huecos"])}
    return datos[clave]


def medidas_de(datos, b, filas):
    """Error y exceso del modelo y de las reglas en las filas marcadas de un bloque."""
    a = _arr(datos, b)
    return medidas(a["real"][filas], a["modelo"][filas], [r[filas] for r in a["r"]])


def por_prueba(datos, b, sel, n):
    """Las medidas de cada prueba (día de partida) en la selección."""
    a = _arr(datos, b)
    en = sel[a["c"]]
    return [medidas_de(datos, b, en & (a["o"] == k)) for k in range(n)]


def gana(pruebas):
    """Pruebas en que el modelo falla menos que la regla que menos falla en esa prueba, y pruebas con venta."""
    con = [p for p in pruebas if p is not None]
    return sum(p["modelo"] < min(p["reglas"]) for p in con), len(con)


def error_sumado(datos, b, sel, solo_prueba=None, combos=None):
    """El error de la previsión sumada: se suman las combinaciones en cada prueba y día y se mide con esas sumas.

    Es la previsión sumada de abajo arriba del informe (reglas, apartado 4). combos: si se da, solo esas combinaciones.
    """
    a = _arr(datos, b)
    en = sel[a["c"]]
    if combos is not None:
        en = en & combos[a["c"]]
    if solo_prueba is not None:
        en = en & (a["o"] == solo_prueba)
    n = a["huecos"]

    def suma(v):
        """La suma de cada hueco (prueba y día) con las filas marcadas."""
        return np.bincount(a["s"][en], weights=v[en], minlength=n)
    return medidas(suma(a["real"]), suma(a["modelo"]), [suma(r) for r in a["r"]])


def calcular(datos, f):
    """Todo lo que enseñan las pestañas para unos filtros: cifras, contextos y lo que piden los títulos."""
    f = normalizar(datos, f)
    sel = seleccion(datos, f)
    n_o, n_f = len(datos["origenes"]), len(datos["festivos"])
    au, ad = _arr(datos, "u"), _arr(datos, "d")
    eu, ed = medidas_de(datos, "u", sel[au["c"]]), medidas_de(datos, "d", sel[ad["c"]])
    pu, pd_ = por_prueba(datos, "u", sel, n_o), por_prueba(datos, "d", sel, n_o)
    gu, de_u = gana(pu)
    gd, de_d = gana(pd_)
    r = {"sel": sel, "eu": eu, "ed": ed, "porprueba_u": pu, "porprueba_d": pd_, "gana_u": gu, "de_u": de_u,
         "gana_d": gd, "de_d": de_d, "venta": float(ad["real"][sel[ad["c"]]].sum())}
    r["regla_u"] = menor(eu["reglas"]) if eu else None
    r["regla_d"] = menor(ed["reglas"]) if ed else None
    # Dónde gana: cada tienda sumando sus departamentos; cada departamento sin sumar; todo en dólares
    tiendas, deps = [], []
    ct = np.asarray(datos["combos"]["tienda"])
    cd = np.asarray(datos["combos"]["departamento"])
    for i, t in enumerate(datos["tiendas"]):
        if not (sel & (ct == i)).any():
            continue
        m = error_sumado(datos, "d", sel, combos=(ct == i))
        if m is not None:
            tiendas.append({"id": t["id"], "modelo": m["modelo"], "regla": menor(m["reglas"]),
                            "error_regla": min(m["reglas"])})
    for i, x in enumerate(datos["departamentos"]):
        en = sel & (cd == i)
        if not en.any():
            continue
        m = medidas_de(datos, "d", en[ad["c"]])
        if m is not None:
            deps.append({"id": x["id"], "modelo": m["modelo"], "regla": menor(m["reglas"]),
                         "error_regla": min(m["reglas"])})
    r["tiendas"], r["deps"] = tiendas, deps
    r["sumado_d"], r["sumado_u"] = error_sumado(datos, "d", sel), error_sumado(datos, "u", sel)
    # Festivos: el modelo y la regla que menos falla en cada víspera
    af = _arr(datos, "f")
    r["festivos"] = []
    for k in range(n_f):
        m = medidas_de(datos, "f", sel[af["c"]] & (af["o"] == k))
        r["festivos"].append(None if m is None else {"modelo": m["modelo"], "regla": menor(m["reglas"]),
                                                     "error_regla": min(m["reglas"])})
    # Próximos días
    p = datos["proximos"]
    en = sel[np.asarray(p["c"], dtype=np.int64)]
    uni = np.array([np.nan if v is None else v for v in p["unidades"]], dtype=float)
    dol = np.asarray(p["dolares"], dtype=float)
    t = np.asarray(p["t"], dtype=np.int64)
    r["unidades_10"] = float(np.nansum(uni[en]))
    r["dolares_10"] = float(dol[en & (t < datos["dias_unidades"])].sum())
    r["dolares_28"] = float(dol[en].sum())
    con_regla = {c for c, g in zip(p["c"], p["regla"]) if g == 1 and sel[c]}
    r["con_regla"] = len(con_regla)
    r["combos_sel"] = int(sel.sum())
    return r


def resumen(datos, f):
    """Las cifras de arriba de las cinco pestañas para unos filtros, calculadas en Python: {pestaña: [{id, valor}]}."""
    r = calcular(datos, f)
    eu, ed = r["eu"], r["ed"]

    def regla_de(e, k):
        """El error de la regla k, o vacío."""
        return None if e is None or k is None else e["reglas"][k]
    return {
        "vision": [{"id": "venta", "valor": r["venta"]},
                   {"id": "error_modelo", "valor": None if ed is None else ed["modelo"]},
                   {"id": "error_regla", "valor": regla_de(ed, r["regla_d"])},
                   {"id": "pruebas_gana", "valor": r["gana_d"]}],
        "pedido": [{"id": "error_modelo", "valor": None if eu is None else eu["modelo"]},
                   {"id": "error_regla", "valor": regla_de(eu, r["regla_u"])},
                   {"id": "pruebas_gana", "valor": r["gana_u"]},
                   {"id": "exceso", "valor": None if eu is None else eu["sesgo"]}],
        "donde": [{"id": "tiendas_gana", "valor": sum(x["modelo"] < x["error_regla"] for x in r["tiendas"])},
                  {"id": "departamentos_gana", "valor": sum(x["modelo"] < x["error_regla"] for x in r["deps"])},
                  {"id": "sumado_dolares", "valor": None if r["sumado_d"] is None else r["sumado_d"]["modelo"]},
                  {"id": "sumado_unidades", "valor": None if r["sumado_u"] is None else r["sumado_u"]["modelo"]}],
        "festivos": [{"id": f"festivo_{k}", "valor": None if x is None else x["modelo"]}
                     for k, x in enumerate(r["festivos"])],
        "proximos": [{"id": "unidades_10", "valor": r["unidades_10"]}, {"id": "dolares_10", "valor": r["dolares_10"]},
                     {"id": "dolares_28", "valor": r["dolares_28"]}, {"id": "con_regla", "valor": r["con_regla"]}]}


def titulos(datos, f):
    """El título de cada pestaña: concluye «falla menos» solo con 10 de 13 pruebas ganadas en la selección (petición 32).

    Devuelve {pestaña: {texto, concluye, gana, de}}. El JavaScript escribe los mismos.
    """
    r = calcular(datos, f)
    minimo = datos["minimo_gana"]
    sale = {}
    ok_d = r["de_d"] == len(datos["origenes"]) and r["gana_d"] >= minimo
    ok_u = r["de_u"] == len(datos["origenes"]) and r["gana_u"] >= minimo
    sale["vision"] = {"texto": "La previsión del modelo falla menos que la regla en dólares" if ok_d
                      else "La venta y la previsión del modelo en dólares de esta selección",
                      "concluye": ok_d, "gana": r["gana_d"], "de": r["de_d"]}
    sale["pedido"] = {"texto": "La previsión del pedido falla menos que la regla en unidades" if ok_u
                      else "Lo que falla la previsión del pedido y la regla en esta selección",
                      "concluye": ok_u, "gana": r["gana_u"], "de": r["de_u"]}
    nt, ganan_t = len(r["tiendas"]), sum(x["modelo"] < x["error_regla"] for x in r["tiendas"])
    nd, ganan_d = len(r["deps"]), sum(x["modelo"] < x["error_regla"] for x in r["deps"])
    if ok_d and ganan_t == nt and ganan_d == nd:
        texto, concl = "La previsión falla menos que la regla en todas las tiendas y departamentos de la selección", True
    elif ok_d and 2 * ganan_t > nt and 2 * ganan_d > nd:
        texto, concl = "La previsión falla menos que la regla en la mayoría de tiendas y departamentos", True
    else:
        texto, concl = "Lo que falla la previsión y la regla en cada tienda y departamento", False
    sale["donde"] = {"texto": texto, "concluye": concl, "gana": r["gana_d"], "de": r["de_d"]}
    sale["festivos"] = {"texto": "La venta y la previsión tras cada víspera de festivo",
                        "concluye": False, "gana": None, "de": None}
    sale["proximos"] = {"texto": "Lo que se prevé vender en los próximos 28 días", "concluye": False, "gana": None,
                        "de": None}
    return sale


# =====================================================================================================================
# LOS PRÓXIMOS DÍAS Y SU CSV
# =====================================================================================================================

def filas_proximos(datos, f):
    """La lista de los próximos días en la selección: una fila por combinación y día, de lo general a lo concreto."""
    sel = seleccion(datos, f)
    p = datos["proximos"]
    salida = []
    for c, t, uu, dd, g in zip(p["c"], p["t"], p["unidades"], p["dolares"], p["regla"]):
        if not sel[c]:
            continue
        tienda = datos["tiendas"][datos["combos"]["tienda"][c]]
        dep = datos["departamentos"][datos["combos"]["departamento"][c]]
        salida.append({"estado": tienda["estado"], "tienda": tienda["id"], "categoria": dep["categoria"],
                       "departamento": dep["id"], "fecha": datos["fechas_proximos"][t], "unidades": uu, "dolares": dd,
                       "con": datos["recomendado"].get(dep["id"], "modelo") if g else "modelo"})
    return salida


def decimal_csv(x, decimales):
    """Un número con coma decimal y sin punto de miles, redondeado como Excel sobre su texto."""
    paso = Decimal(1).scaleb(-decimales)
    return str(Decimal(repr(float(x))).quantize(paso, rounding=ROUND_HALF_UP)).replace(".", ",")


def _seleccion_texto(datos, f):
    """Los filtros puestos, en palabras, en el orden de los filtros."""
    nombres_e = {e["id"]: e["nombre"] for e in datos["estados"]}
    nombres_c = {c["id"]: c["nombre"] for c in datos["categorias"]}
    partes = []
    if f.get("estado"):
        partes.append(nombres_e[f["estado"]])
    if f.get("tienda"):
        partes.append(f["tienda"])
    if f.get("categoria"):
        partes.append(nombres_c[f["categoria"]])
    if f.get("departamento"):
        partes.append(f["departamento"])
    return partes


def nombre_csv(datos, f):
    """El nombre del CSV: proximos_dias_wi_wi_2_foods_foods_3_datos-2016-05-22.csv, con los filtros que haya."""
    f = normalizar(datos, f)
    partes = ["proximos_dias"] + [str(f[k]).lower() for k in ("estado", "tienda", "categoria", "departamento") if k in f]
    return "_".join(partes) + f"_datos-{datos['fecha_datos']}.csv"


# Columnas de lo general a lo concreto (estado, tienda, categoría, departamento y día); lo previsto y con qué, al final
CABECERA_CSV = ["Estado", "Tienda", "Categoría", "Departamento", "Día", "Unidades previstas", "Dólares previstos",
                "Se prevé con"]


def texto_csv(datos, f):
    """El CSV de la lista: la selección en la primera línea, punto y coma, coma decimal y las unidades enteras."""
    f = normalizar(datos, f)
    nombres_e = {e["id"]: e["nombre"] for e in datos["estados"]}
    nombres_c = {c["id"]: c["nombre"] for c in datos["categorias"]}
    lineas = [" · ".join(["Próximos días"] + _seleccion_texto(datos, f)
                         + [f"previsión hecha con la venta hasta el {fecha_es(datos['origen_proximos'])}"]),
              ";".join(CABECERA_CSV)]
    for x in filas_proximos(datos, f):
        lineas.append(";".join([nombres_e[x["estado"]], x["tienda"], nombres_c[x["categoria"]], x["departamento"],
                                fecha_es(x["fecha"]), "" if x["unidades"] is None else decimal_csv(x["unidades"], 0),
                                decimal_csv(x["dolares"], 2),
                                "el modelo" if x["con"] == "modelo" else NOMBRES_REGLAS[x["con"]]]))
    return "\r\n".join(lineas) + "\r\n"


# =====================================================================================================================
# COMPROBACIONES
# =====================================================================================================================

def _filtro_de_grupo(nivel, grupo):
    """Los filtros que dan un grupo de los niveles del JSON (cadena, estado, tienda o categoría)."""
    return {} if nivel == "cadena" else {nivel: grupo}


def comparar_con_json(datos, pf):
    """Cada cifra que el cuadro repite, sin filtros, frente a informes/prueba_final.json (variante del modelo en uso).

    Devuelve una lista de {nombre, cuadro, json, coinciden}.
    """
    salida = []

    def anadir(nombre, cuadro, del_json):
        """Una comparación: cifras con tolerancia; textos y listas, iguales."""
        if isinstance(del_json, (str, list)) or isinstance(cuadro, (str, list)):
            ok = cuadro == del_json
        else:
            ok = iguales(cuadro, del_json)
        salida.append({"nombre": nombre, "cuadro": cuadro, "json": del_json, "coinciden": bool(ok)})

    r = calcular(datos, {})
    js = pf[VARIANTE]
    deps = [x["id"] for x in datos["departamentos"]]
    for b, objetivo, e, porp, gn, de in (("u", "unidades", r["eu"], r["porprueba_u"], r["gana_u"], r["de_u"]),
                                         ("d", "dolares", r["ed"], r["porprueba_d"], r["gana_d"], r["de_d"])):
        todas = {x["prevision"]: x for x in js[objetivo]["errores"]["todas"]}
        anadir(f"{objetivo}.modelo.error", e["modelo"], todas["modelo"]["error"])
        anadir(f"{objetivo}.modelo.exceso", e["sesgo"], todas["modelo"]["sesgo"])
        for k, regla in enumerate(REGLAS):
            anadir(f"{objetivo}.{regla}.error", e["reglas"][k], todas[regla]["error"])
            anadir(f"{objetivo}.{regla}.exceso", e["sesgos"][k], todas[regla]["sesgo"])
        anadir(f"{objetivo}.regla_que_menos_falla", REGLAS[menor(e["reglas"])],
               min(REGLAS, key=lambda x: (todas[x]["error"], REGLAS.index(x))))
        anadir(f"{objetivo}.pruebas_que_gana", gn, js[objetivo]["veredicto"]["origenes_que_gana"])
        anadir(f"{objetivo}.pruebas", de, js[objetivo]["veredicto"]["de"])
        anadir(f"{objetivo}.minimo", datos["minimo_gana"], js[objetivo]["veredicto"]["minimo"])
        por = {(x["grupo"], x["prevision"]): x["error"] for x in js[objetivo]["errores"]["por_origen"]}
        for k, origen in enumerate(datos["origenes"]):
            anadir(f"{objetivo}.prueba_{origen}.modelo", porp[k]["modelo"], por[(origen, "modelo")])
            for j, regla in enumerate(REGLAS):
                anadir(f"{objetivo}.prueba_{origen}.{regla}", porp[k]["reglas"][j], por[(origen, regla)])
        anadir(f"{objetivo}.regla_de_cada_prueba", [REGLAS[menor(p["reglas"])] for p in porp],
               js[objetivo]["veredicto"]["rival_por_origen"])
        for x in js[objetivo]["recomendacion_por_departamento"]:
            en = seleccion(datos, {"departamento": x["departamento"]})
            m = medidas_de(datos, b, en[_arr(datos, b)["c"]])
            anadir(f"{objetivo}.{x['departamento']}.modelo", m["modelo"], x["error_modelo"])
            anadir(f"{objetivo}.{x['departamento']}.regla", REGLAS[menor(m["reglas"])], x["regla_que_menos_falla"])
            anadir(f"{objetivo}.{x['departamento']}.error_regla", min(m["reglas"]), x["error_regla"])
        anadir(f"{objetivo}.departamentos", sorted(deps),
               sorted(x["departamento"] for x in js[objetivo]["recomendacion_por_departamento"]))
        for nivel in ("cadena", "estado", "tienda", "categoria"):
            for g in js[objetivo]["niveles"][nivel]["grupos"]:
                m = error_sumado(datos, b, seleccion(datos, _filtro_de_grupo(nivel, g["grupo"])))
                anadir(f"{objetivo}.sumado.{g['grupo']}.modelo", m["modelo"], g["error_modelo"])
                anadir(f"{objetivo}.sumado.{g['grupo']}.regla", REGLAS[menor(m["reglas"])], g["regla_que_menos_falla"])
                anadir(f"{objetivo}.sumado.{g['grupo']}.error_regla", min(m["reglas"]), g["error_regla"])
    anadir("dolares.tiendas_que_gana", sum(x["modelo"] < x["error_regla"] for x in r["tiendas"]),
           sum(bool(g["modelo_falla_menos"]) for g in js["dolares"]["niveles"]["tienda"]["grupos"]))
    for k, x in enumerate(js["unidades"]["festivos"]["por_origen"]):
        anadir(f"festivo_{k}.nombre", datos["festivos"][k]["nombre"], x["festivo"])
        anadir(f"festivo_{k}.origen", datos["festivos"][k]["origen"], x["origen"])
        anadir(f"festivo_{k}.modelo", r["festivos"][k]["modelo"], x["error_modelo"])
        anadir(f"festivo_{k}.regla", REGLAS[r["festivos"][k]["regla"]], x["regla_que_menos_falla"])
        anadir(f"festivo_{k}.error_regla", r["festivos"][k]["error_regla"], x["error_regla"])
    return salida


def venta_por_otro_camino(datos, hechos):
    """La venta en dólares del último año guardado sumada desde hechos_prueba_final (otra tabla), en los mismos días y
    sin los días fuera del error, frente a la del cuadro."""
    fechas = pd.to_datetime(pd.Series(datos["d"]["fechas"])).astype("datetime64[us]")
    en = hechos["date"].isin(fechas).to_numpy() & ~hechos["fuera_del_error"].to_numpy()
    return {"cuadro": calcular(datos, {})["venta"], "hechos_prueba_final": float(hechos.loc[en, "dolares"].sum()),
            "dias": len(fechas)}


# =====================================================================================================================
# HTML: estilos, esqueleto y JavaScript
# =====================================================================================================================

CSS = """
html, body { margin: 0; background: #ffffff; color: #0b0b0b; }
body { font-family: "Segoe UI", system-ui, sans-serif; font-size: 15px; line-height: 1.4; font-variant-numeric: tabular-nums; }
* { box-sizing: border-box; }
.barra { display: flex; align-items: baseline; gap: 28px; padding: 8px 40px 6px; border-bottom: 1px solid #e1e0d9; }
.barra .nombre { font-weight: 700; font-size: 16px; white-space: nowrap; }
.barra [role=tablist] { display: flex; gap: 22px; }
.barra [role=tab] { font: 15px "Segoe UI", system-ui, sans-serif; background: #ffffff; color: #0b0b0b; border: 0; padding: 2px 0; cursor: pointer; }
.barra [role=tab][aria-selected=true] { font-weight: 700; text-decoration: underline; }
.filtros { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; padding: 6px 40px 0; font-size: 14px; }
.filtros label { color: #52514e; }
.filtros select { font: 14px "Segoe UI", system-ui, sans-serif; margin-left: 4px; padding: 1px 2px; }
.filtros button { font: 14px "Segoe UI", system-ui, sans-serif; background: #ffffff; border: 1px solid #898781; border-radius: 3px; padding: 1px 8px; cursor: pointer; }
.filtros button:disabled { color: #898781; border-color: #e1e0d9; cursor: default; }
.viendo { margin: 3px 40px 0; font-size: 13px; color: #52514e; }
main { padding: 4px 40px 0; }
.pestana h2 { font-size: 28px; font-weight: 700; line-height: 1.2; margin: 0 0 6px; }
.cifras { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px; margin: 0 0 8px; }
.cifra { min-width: 0; outline-offset: 2px; }
.cifra .num { font-size: 28px; font-weight: 700; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cifra .etq { font-size: 14px; line-height: 1.3; }
.cifra .ctx { font-size: 13px; color: #52514e; line-height: 1.3; }
.grafico .gtit { font-size: 20px; font-weight: 700; line-height: 1.25; }
.grafico .gsub { font-size: 13px; color: #52514e; }
.grafico .gley { line-height: 0; margin-top: 1px; }
.grafico svg { display: block; margin-top: 2px; }
.grafico svg text { font-family: "Segoe UI", system-ui, sans-serif; }
.texto { margin: 6px 0 0; max-width: 110ch; }
.pie { margin: 4px 0 0; font-size: 13px; color: #52514e; max-width: 160ch; }
.tabla { overflow-y: auto; border-bottom: 1px solid #e1e0d9; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { position: sticky; top: 0; background: #ffffff; text-align: left; font-weight: 600; border-bottom: 1px solid #0b0b0b; padding: 2px 6px; vertical-align: bottom; }
td { padding: 1px 6px; white-space: nowrap; }
th.n, td.n { text-align: right; }
.mandos { display: flex; align-items: center; gap: 18px; margin: 4px 0 0; font-size: 14px; }
.mandos .nota { font-size: 13px; color: #52514e; }
.mandos button { font: 14px "Segoe UI", system-ui, sans-serif; background: #ffffff; border: 1px solid #898781; border-radius: 3px; padding: 1px 8px; cursor: pointer; }
#tip { position: fixed; z-index: 10; max-width: 380px; background: #ffffff; color: #0b0b0b; border: 1px solid #898781; border-radius: 3px; padding: 6px 8px; font-size: 13px; line-height: 1.35; pointer-events: none; }
[data-tip]:focus { outline: 2px solid #2a78d6; }
"""

CUERPO = """
<div class="barra">
  <span class="nombre">Previsión de la venta</span>
  <div role="tablist" aria-label="Pestañas">
    <button role="tab" id="b-vision" data-p="vision">Visión general</button>
    <button role="tab" id="b-pedido" data-p="pedido">El pedido</button>
    <button role="tab" id="b-donde" data-p="donde">Dónde gana</button>
    <button role="tab" id="b-festivos" data-p="festivos">Festivos</button>
    <button role="tab" id="b-proximos" data-p="proximos">Próximos días</button>
  </div>
</div>
<div class="filtros">
  <label>Estado<select id="f-estado"></select></label>
  <label>Tienda<select id="f-tienda"></select></label>
  <label>Categoría<select id="f-categoria"></select></label>
  <label>Departamento<select id="f-departamento"></select></label>
  <button id="quitar" type="button">Quitar filtros</button>
</div>
<p class="viendo" id="viendo"></p>
<main>
  <section class="pestana" id="p-vision" role="tabpanel" hidden>
    <h2 data-titulo id="t-vision"></h2><div class="cifras" id="c-vision"></div>
    <div class="grafico" id="g-vision"></div><p class="texto" id="x-vision"></p><p class="pie" id="pie-vision"></p>
  </section>
  <section class="pestana" id="p-pedido" role="tabpanel" hidden>
    <h2 data-titulo id="t-pedido"></h2><div class="cifras" id="c-pedido"></div>
    <div class="grafico" id="g-pedido"></div><div class="tabla" id="d-pedido" style="max-height:178px"></div>
    <p class="pie" id="pie-pedido"></p>
  </section>
  <section class="pestana" id="p-donde" role="tabpanel" hidden>
    <h2 data-titulo id="t-donde"></h2><div class="cifras" id="c-donde"></div>
    <div class="grafico" id="g-donde"></div><p class="pie" id="pie-donde"></p>
  </section>
  <section class="pestana" id="p-festivos" role="tabpanel" hidden>
    <h2 data-titulo id="t-festivos"></h2><div class="cifras" id="c-festivos"></div>
    <div class="grafico" id="g-festivos"></div><p class="texto" id="x-festivos"></p><p class="pie" id="pie-festivos"></p>
  </section>
  <section class="pestana" id="p-proximos" role="tabpanel" hidden>
    <h2 data-titulo id="t-proximos"></h2><div class="cifras" id="c-proximos"></div>
    <div class="grafico" id="g-proximos"></div>
    <div class="mandos"><button id="descargar" type="button">Descargar CSV</button><span class="nota" id="x-proximos"></span></div>
    <div class="tabla" id="d-proximos" style="max-height:190px"></div><p class="pie" id="pie-proximos"></p>
  </section>
</main>
<div id="tip" role="tooltip" hidden></div>
"""

JS = r"""
'use strict';
const D = JSON.parse(document.getElementById('datos').textContent);
const AZUL = '#2a78d6', NARANJA = '#eb6834', VERDE = '#1baf7a', GRIS = '#898781', REJILLA = '#e1e0d9', TEXTO2 = '#52514e', NEGRO = '#0b0b0b';
// El segundo color: la previsión frente a lo vendido y la regla frente al modelo, en los cuatro gráficos que comparan dos
// cosas. Elegido con las pruebas de color del 25/11/2026 (el responsable del caso: «no se distinguen, cambia de color, haz pruebas»)
// La visión general va por semana de Walmart, de sábado a viernes: por día, el ritmo de la semana tapaba dónde se separa
// la previsión de la venta (comparadas las dos el 25/11/2026)
const SEGUNDA = '#eda100', SEMANAL = true;
const PESTANAS = ['vision', 'pedido', 'donde', 'festivos', 'proximos'];
const FILTROS = ['estado', 'tienda', 'categoria', 'departamento'];
const E = {pestana: 'vision', estado: null, tienda: null, categoria: null, departamento: null};
const NR = D.reglas.map(r => D.nombres_reglas[r]);
const NOMBRE_E = Object.fromEntries(D.estados.map(e => [e.id, e.nombre]));
const NOMBRE_C = Object.fromEntries(D.categorias.map(c => [c.id, c.nombre]));
const EST_DE = Object.fromEntries(D.tiendas.map(t => [t.id, t.estado]));
const CAT_DE = Object.fromEntries(D.departamentos.map(x => [x.id, x.categoria]));
const CT = D.combos.tienda, CD = D.combos.departamento, NC = CT.length;
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

// ---------------------------------------------------------------- números y textos a la española
function redondeo(x, d) {
  // Como Excel y como decimal_csv de Python: el medio se aleja del cero, sobre el texto del número
  let s = String(Math.abs(x));
  if (s.includes('e')) s = Math.abs(x).toFixed(20);
  let [ent, dec = ''] = s.split('.');
  dec = dec.padEnd(d + 1, '0');
  let base = BigInt(ent + dec.slice(0, d));
  if (Number(dec[d]) >= 5) base += 1n;
  const t = base.toString().padStart(d + 1, '0');
  return [x < 0 && base !== 0n, d > 0 ? t.slice(0, t.length - d) : t, d > 0 ? t.slice(t.length - d) : ''];
}
function num(x, d = 0) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const [neg, e, f] = redondeo(x, d);
  return (neg ? '−' : '') + e.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (d > 0 ? ',' + f : '');
}
function decCsv(x, d) { const [neg, e, f] = redondeo(x, d); return (neg ? '-' : '') + e + (d > 0 ? ',' + f : ''); }
function signo(x, d = 1) {
  if (x === null) return '—';
  const t = num(Math.abs(x), d);
  return /^0(,0*)?$/.test(t) ? t : (x > 0 ? '+' : '−') + t;
}
function usd(x) { return num(x) + ' $'; }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function fechaEs(s) { const [a, m, d] = s.split('-'); return d + '/' + m + '/' + a; }
function diaMes(s) { const [a, m, d] = s.split('-'); return d + '/' + m; }
function mayus(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function listaY(xs) { return xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join(', ') + ' y ' + xs[xs.length - 1]; }
function sumarDias(s, n) { const f = new Date(s + 'T00:00:00Z'); f.setUTCDate(f.getUTCDate() + n); return f.toISOString().slice(0, 10); }
const FUENTE = 'Fuente: venta diaria de las 70 combinaciones, datos a ' + fechaEs(D.fecha_datos);

// ---------------------------------------------------------------- la selección
function normalizar() {
  if (E.tienda !== null) E.estado = EST_DE[E.tienda];
  if (E.departamento !== null) E.categoria = CAT_DE[E.departamento];
}
function seleccion() {
  const s = new Array(NC);
  for (let i = 0; i < NC; i++) {
    const t = D.tiendas[CT[i]], x = D.departamentos[CD[i]];
    s[i] = (E.estado === null || t.estado === E.estado) && (E.tienda === null || t.id === E.tienda)
      && (E.categoria === null || x.categoria === E.categoria) && (E.departamento === null || x.id === E.departamento);
  }
  return s;
}
function hayFiltro() { return FILTROS.some(k => E[k] !== null); }
function seleccionPartes() {
  const p = [];
  if (E.estado !== null) p.push(NOMBRE_E[E.estado]);
  if (E.tienda !== null) p.push(E.tienda);
  if (E.categoria !== null) p.push(NOMBRE_C[E.categoria]);
  if (E.departamento !== null) p.push(E.departamento);
  return p;
}
function seleccionTexto() { return seleccionPartes().join(' · ') || 'las 70 combinaciones'; }

// ---------------------------------------------------------------- la medida (la misma cuenta que calcular() en Python)
function nuevaSuma() { return {real: 0, am: 0, sm: 0, ar: [0, 0, 0], sr: [0, 0, 0]}; }
function sumar(s, B, i) {
  const re = B.real[i], dm = B.modelo[i] - re;
  s.real += re; s.am += Math.abs(dm); s.sm += dm;
  for (let k = 0; k < 3; k++) { const dr = B.r[k][i] - re; s.ar[k] += Math.abs(dr); s.sr[k] += dr; }
}
function medidas(s) {
  if (!(s.real > 0)) return null;
  return {modelo: 100 * s.am / s.real, sesgo: 100 * s.sm / s.real, reglas: s.ar.map(a => 100 * a / s.real), sesgos: s.sr.map(a => 100 * a / s.real)};
}
function menor(xs) { let k = 0; for (let j = 1; j < xs.length; j++) if (xs[j] < xs[k]) k = j; return k; }
function medir(B, ok) { const s = nuevaSuma(); for (let i = 0; i < B.c.length; i++) if (ok(i)) sumar(s, B, i); return medidas(s); }
function porPrueba(B, sel, n) {
  const ss = Array.from({length: n}, nuevaSuma);
  for (let i = 0; i < B.c.length; i++) if (sel[B.c[i]]) sumar(ss[B.o[i]], B, i);
  return ss.map(medidas);
}
function gana(pp) { let g = 0, de = 0; for (const p of pp) { if (!p) continue; de++; if (p.modelo < Math.min(...p.reglas)) g++; } return [g, de]; }
function sumado(B, ok) {
  // La previsión sumada: las combinaciones de cada prueba y día se suman y se mide con esas sumas
  const n = B.huecos, re = new Float64Array(n), m = new Float64Array(n), r = [new Float64Array(n), new Float64Array(n), new Float64Array(n)];
  for (let i = 0; i < B.c.length; i++) {
    if (!ok(i)) continue;
    const h = B.s[i]; re[h] += B.real[i]; m[h] += B.modelo[i];
    for (let k = 0; k < 3; k++) r[k][h] += B.r[k][i];
  }
  const s = nuevaSuma();
  for (let h = 0; h < n; h++) {
    const dm = m[h] - re[h]; s.real += re[h]; s.am += Math.abs(dm); s.sm += dm;
    for (let k = 0; k < 3; k++) { const dr = r[k][h] - re[h]; s.ar[k] += Math.abs(dr); s.sr[k] += dr; }
  }
  return medidas(s);
}
function calcular() {
  const sel = seleccion(), no = D.origenes.length, U = D.u, B = D.d, F = D.f;
  const eu = medir(U, i => sel[U.c[i]]), ed = medir(B, i => sel[B.c[i]]);
  const pu = porPrueba(U, sel, no), pd = porPrueba(B, sel, no);
  const [gu, deu] = gana(pu), [gd, ded] = gana(pd);
  let venta = 0; for (let i = 0; i < B.c.length; i++) if (sel[B.c[i]]) venta += B.real[i];
  const tiendas = [], deps = [];
  D.tiendas.forEach((t, j) => {
    if (!sel.some((v, i) => v && CT[i] === j)) return;
    const m = sumado(B, i => sel[B.c[i]] && CT[B.c[i]] === j);
    if (m) tiendas.push({id: t.id, modelo: m.modelo, regla: menor(m.reglas), error_regla: Math.min(...m.reglas)});
  });
  D.departamentos.forEach((x, j) => {
    if (!sel.some((v, i) => v && CD[i] === j)) return;
    const m = medir(B, i => sel[B.c[i]] && CD[B.c[i]] === j);
    if (m) deps.push({id: x.id, modelo: m.modelo, regla: menor(m.reglas), error_regla: Math.min(...m.reglas)});
  });
  const festivos = D.festivos.map((f, k) => {
    const m = medir(F, i => sel[F.c[i]] && F.o[i] === k);
    return m === null ? null : {modelo: m.modelo, regla: menor(m.reglas), error_regla: Math.min(...m.reglas)};
  });
  const P = D.proximos; let u10 = 0, d10 = 0, d28 = 0; const conRegla = new Set();
  for (let i = 0; i < P.c.length; i++) {
    if (!sel[P.c[i]]) continue;
    if (P.unidades[i] !== null) u10 += P.unidades[i];
    d28 += P.dolares[i];
    if (P.t[i] < D.dias_unidades) d10 += P.dolares[i];
    if (P.regla[i] === 1) conRegla.add(P.c[i]);
  }
  return {sel, eu, ed, pu, pd, gu, deu, gd, ded, venta, ru: eu ? menor(eu.reglas) : null, rd: ed ? menor(ed.reglas) : null,
    tiendas, deps, sumadoD: sumado(B, i => sel[B.c[i]]), sumadoU: sumado(U, i => sel[U.c[i]]), festivos,
    u10, d10, d28, conRegla: conRegla.size, nsel: sel.filter(Boolean).length};
}
function titulos(r) {
  // Concluye «falla menos» solo con 10 de 13 pruebas ganadas en la selección (la misma regla que titulos() en Python)
  const min = D.minimo_gana, no = D.origenes.length;
  const okD = r.ded === no && r.gd >= min, okU = r.deu === no && r.gu >= min;
  const s = {};
  s.vision = {texto: okD ? 'La previsión del modelo falla menos que la regla en dólares' : 'La venta y la previsión del modelo en dólares de esta selección', concluye: okD, gana: r.gd, de: r.ded};
  s.pedido = {texto: okU ? 'La previsión del pedido falla menos que la regla en unidades' : 'Lo que falla la previsión del pedido y la regla en esta selección', concluye: okU, gana: r.gu, de: r.deu};
  const nt = r.tiendas.length, gt = r.tiendas.filter(x => x.modelo < x.error_regla).length;
  const nd = r.deps.length, gdp = r.deps.filter(x => x.modelo < x.error_regla).length;
  let texto = 'Lo que falla la previsión y la regla en cada tienda y departamento', concl = false;
  if (okD && gt === nt && gdp === nd) { texto = 'La previsión falla menos que la regla en todas las tiendas y departamentos de la selección'; concl = true; }
  else if (okD && 2 * gt > nt && 2 * gdp > nd) { texto = 'La previsión falla menos que la regla en la mayoría de tiendas y departamentos'; concl = true; }
  s.donde = {texto, concluye: concl, gana: r.gd, de: r.ded};
  s.festivos = {texto: 'La venta y la previsión tras cada víspera de festivo', concluye: false, gana: null, de: null};
  s.proximos = {texto: 'Lo que se prevé vender en los próximos 28 días', concluye: false, gana: null, de: null};
  return s;
}

// ---------------------------------------------------------------- piezas: cifras, títulos, leyendas, escala
function cifra(id, valor, numero, etiqueta, contexto, tip) {
  return `<div class="cifra" tabindex="0" data-id="${id}" data-valor="${valor === null ? '' : String(valor)}" data-tip="${esc(tip)}">`
    + `<div class="num">${esc(numero)}</div><div class="etq">${esc(etiqueta)}</div><div class="ctx">${esc(contexto)}</div></div>`;
}
function titulo(el, t) {
  el.textContent = t.texto;
  el.dataset.concluye = t.concluye ? 'si' : 'no';
  if (t.gana !== null) { el.dataset.gana = String(t.gana); el.dataset.de = String(t.de); } else { delete el.dataset.gana; delete el.dataset.de; }
}
function grafico(id, texto, sub, svg, ley = null) {
  // El título; justo debajo, pegada a él y a la izquierda, la leyenda si el gráfico compara dos cosas; el subtítulo
  const g = document.getElementById(id);
  g.innerHTML = `<div class="gtit" data-titulo data-concluye="no"></div>` + (ley ? leyendaArriba(ley) : '') + `<div class="gsub"></div>` + svg;
  g.querySelector('.gtit').textContent = texto;
  g.querySelector('.gsub').textContent = sub;
}
function leyendaArriba(items) {
  // items: [[color, texto, discontinua]]; el ancho de cada texto se estima por sus letras, a 12 px
  let x = 0, s = '';
  for (const [color, texto, raya] of items) { s += leyenda(x, 12, color, texto, !!raya); x += (raya ? 24 : 15) + texto.length * 6.6 + 22; }
  return `<div class="gley"><svg width="${Math.ceil(x)}" height="16" viewBox="0 0 ${Math.ceil(x)} 16" role="img" aria-label="Leyenda">${s}</svg></div>`;
}
function ventaPorPeriodo(sel, semanal) {
  // La venta y la previsión del modelo en dólares, sumadas por día o por semana de Walmart (de sábado a viernes);
  // los días fuera del error (el 25 de diciembre) no están en los datos, así que su semana cuenta 6 días
  const B = D.d, clave = B.fechas.map(f => semanal ? sumarDias(f, -((new Date(f + 'T00:00:00Z').getUTCDay() + 1) % 7)) : f);
  const orden = [...new Set(clave)], pos = Object.fromEntries(orden.map((k, j) => [k, j]));
  const re = new Float64Array(orden.length), pm = new Float64Array(orden.length);
  const periodos = orden.map(k => ({desde: k, hasta: semanal ? sumarDias(k, 6) : k, dias: 0}));
  clave.forEach(k => { periodos[pos[k]].dias += 1; });
  for (let i = 0; i < B.c.length; i++) if (sel[B.c[i]]) { const j = pos[clave[B.t[i]]]; re[j] += B.real[i]; pm[j] += B.modelo[i]; }
  return {periodos, re, pm};
}
function escala(max) {
  let p = 1;
  if (max > 0) { const e = Math.pow(10, Math.floor(Math.log10(max / 4))); p = [1, 2, 2.5, 5].map(x => x * e).find(x => max / x <= 5) || 10 * e; }
  return {paso: p, tope: Math.max(p, Math.ceil(max / p) * p)};
}
function leyenda(x, y, color, texto, raya = false) {
  const m = raya ? `<line x1="${x}" x2="${x + 18}" y1="${y - 4}" y2="${y - 4}" stroke="${color}" stroke-width="2" stroke-dasharray="5 3"/>`
    : `<rect x="${x}" y="${y - 9}" width="10" height="10" fill="${color}"/>`;
  return m + `<text x="${x + (raya ? 24 : 15)}" y="${y}" font-size="12" fill="${TEXTO2}">${esc(texto)}</text>`;
}
function conDe(rec) { return rec === 'modelo' ? 'el modelo' : NR[D.reglas.indexOf(rec)] + ', la regla que se recomienda'; }

// ---------------------------------------------------------------- pestaña 1: visión general
function dibujarVision(r, t) {
  titulo(document.getElementById('t-vision'), t.vision);
  const ed = r.ed, rd = r.rd, sel = seleccionTexto();
  const f0 = D.d.fechas[0], f1 = D.d.fechas[D.d.fechas.length - 1];
  document.getElementById('c-vision').innerHTML = [
    cifra('venta', r.venta, usd(r.venta), 'Dólares vendidos en el último año guardado', `Del ${fechaEs(f0)} al ${fechaEs(f1)}`,
      `Venta en dólares de ${sel} del ${fechaEs(f0)} al ${fechaEs(f1)}, los días que mide la previsión a 28 días, sin el 25 de diciembre: ${usd(r.venta)}.`),
    cifra('error_modelo', ed ? ed.modelo : null, ed ? num(ed.modelo, 1) : '—', 'Dólares que falla la previsión por cada 100', 'A 28 días, el mes de finanzas',
      ed ? `La previsión del modelo en ${sel} falla ${num(ed.modelo, 2)} dólares por cada 100 vendidos, a 28 días desde cada día de partida. Es la suma de lo que se desvía cada día, sin signo, entre lo vendido.` : 'Sin venta en esta selección.'),
    cifra('error_regla', ed ? ed.reglas[rd] : null, ed ? num(ed.reglas[rd], 1) : '—', 'Dólares que falla la regla que menos falla', ed ? mayus(NR[rd]) : '—',
      ed ? `De las tres reglas sencillas, la que menos falla en ${sel} es ${NR[rd]}: ${num(ed.reglas[rd], 2)} dólares por cada 100 vendidos, a 28 días.` : 'Sin venta en esta selección.'),
    cifra('pruebas_gana', r.gd, `${r.gd} de ${r.ded}`, 'Pruebas en dólares en que el modelo falla menos', `Hacen falta ${D.minimo_gana} para concluir`,
      `En ${r.gd} de las ${r.ded} pruebas en dólares, una cada 28 días, el modelo falla menos que la regla que menos falla en esa prueba. La regla fijada antes de medir pide al menos ${D.minimo_gana}.`)
  ].join('');
  // Gráfico: la venta y la previsión del modelo, sumadas en la selección, por día o por semana de Walmart (SEMANAL)
  const P = ventaPorPeriodo(r.sel, SEMANAL), n = P.re.length, re = P.re, pm = P.pm;
  const W = 1286, H = 196, ml = 62, mr = 20, mt = 8, mb = 22;
  const {paso, tope} = escala(Math.max(...re, ...pm));
  const X = j => ml + j * (W - ml - mr) / (n - 1), Y = v => mt + (H - mt - mb) * (1 - v / tope);
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Venta y previsión ${SEMANAL ? 'por semana' : 'de cada día'}">`;
  for (let y = 0; y <= tope + 1e-9; y += paso) svg += `<line x1="${ml}" x2="${W - mr}" y1="${Y(y)}" y2="${Y(y)}" stroke="${REJILLA}"/><text x="${ml - 6}" y="${Y(y) + 4}" font-size="12" text-anchor="end" fill="${TEXTO2}">${num(y)}</text>`;
  // El mes, en el primer punto de cada mes
  P.periodos.forEach((p, j) => { if (j > 0 && p.desde.slice(5, 7) !== P.periodos[j - 1].desde.slice(5, 7)) svg += `<text x="${X(j)}" y="${H - 6}" font-size="12" text-anchor="middle" fill="${TEXTO2}">${MESES[Number(p.desde.slice(5, 7)) - 1]} ${p.desde.slice(2, 4)}</text>`; });
  const camino = v => Array.from(v, (y, j) => (j ? 'L' : 'M') + X(j).toFixed(1) + ' ' + Y(y).toFixed(1)).join('');
  svg += `<path d="${camino(re)}" fill="none" stroke="${AZUL}" stroke-width="1.8"/>`;
  // La previsión, en el segundo color y discontinua: en el mismo azul que la venta no se distinguían (el responsable del caso)
  svg += `<path d="${camino(pm)}" fill="none" stroke="${SEGUNDA}" stroke-width="1.8" stroke-dasharray="5 3"/>`;
  const ancho = (W - ml - mr) / n;
  for (let j = 0; j < n; j++) {
    const p = P.periodos[j];
    const cuando = SEMANAL ? `Semana del ${fechaEs(p.desde)} al ${fechaEs(p.hasta)}` + (p.dias < 7 ? ` (${p.dias} días: sin el 25 de diciembre)` : '') : fechaEs(p.desde);
    svg += `<g tabindex="0" data-tip="${esc(cuando + ': venta de ' + usd(re[j]) + '; previsión del modelo, ' + usd(pm[j]) + '.')}">`
      + (SEMANAL ? `<circle cx="${X(j)}" cy="${Y(re[j])}" r="2.5" fill="${AZUL}"/>` : '')
      + `<rect x="${(X(j) - ancho / 2).toFixed(1)}" y="${mt}" width="${ancho.toFixed(2)}" height="${H - mt - mb}" fill="transparent"/></g>`;
  }
  svg += '</svg>';
  grafico('g-vision', SEMANAL ? 'Venta y previsión por semana' : 'Venta y previsión de cada día', SEMANAL ? 'Dólares por semana' : 'Dólares al día', svg,
    [[AZUL, 'Venta'], [SEGUNDA, 'Previsión del modelo, a 28 días', true]]);
  document.getElementById('x-vision').textContent = 'Vigila HOBBIES_2, que se pide con la media de los últimos 28 días. Los festivos grandes solo se comprobaron una vez.';
  document.getElementById('pie-vision').textContent = FUENTE;
}

// ---------------------------------------------------------------- pestaña 2: el pedido
function dibujarPedido(r, t) {
  titulo(document.getElementById('t-pedido'), t.pedido);
  const eu = r.eu, ru = r.ru, sel = seleccionTexto();
  document.getElementById('c-pedido').innerHTML = [
    cifra('error_modelo', eu ? eu.modelo : null, eu ? num(eu.modelo, 1) : '—', 'Unidades que falla la previsión por cada 100', 'A 10 días, el plazo del pedido',
      eu ? `La previsión del modelo en ${sel} falla ${num(eu.modelo, 2)} unidades por cada 100 vendidas, a 10 días desde cada día de partida.` : 'Sin venta en esta selección.'),
    cifra('error_regla', eu ? eu.reglas[ru] : null, eu ? num(eu.reglas[ru], 1) : '—', 'Unidades que falla la regla que menos falla', eu ? mayus(NR[ru]) : '—',
      eu ? `De las tres reglas sencillas, la que menos falla en ${sel} es ${NR[ru]}: ${num(eu.reglas[ru], 2)} unidades por cada 100 vendidas, a 10 días.` : 'Sin venta en esta selección.'),
    cifra('pruebas_gana', r.gu, `${r.gu} de ${r.deu}`, 'Pruebas en unidades en que el modelo falla menos', `Hacen falta ${D.minimo_gana} para concluir`,
      `En ${r.gu} de las ${r.deu} pruebas en unidades el modelo falla menos que la regla que menos falla en esa prueba. La regla fijada antes de medir pide al menos ${D.minimo_gana}.`),
    cifra('exceso', eu ? eu.sesgo : null, eu ? signo(eu.sesgo) : '—', 'Unidades que se pasa (+) o se queda corta (−) por cada 100', eu ? 'La regla que menos falla, ' + signo(eu.sesgos[ru]) : '—',
      eu ? `La previsión del modelo en ${sel} se pasa ${signo(eu.sesgo, 2)} unidades por cada 100 vendidas; si es negativo, se queda corta. ${mayus(NR[ru])}, ${signo(eu.sesgos[ru], 2)}.` : 'Sin venta en esta selección.')
  ].join('');
  // Gráfico: el error de cada prueba, el modelo frente a la regla que menos falla en esa prueba
  const W = 1286, H = 150, ml = 10, mt = 16, mb = 20, n = D.origenes.length, gw = (W - ml) / n, bw = Math.min(30, gw * 0.32);
  const vals = r.pu.filter(p => p).flatMap(p => [p.modelo, Math.min(...p.reglas)]);
  const tope = Math.max(1, ...vals) * 1.12, Y = v => mt + (H - mt - mb) * (1 - v / tope);
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Error de cada prueba">`;
  svg += `<line x1="${ml}" x2="${W}" y1="${Y(0)}" y2="${Y(0)}" stroke="${GRIS}"/>`;
  r.pu.forEach((p, k) => {
    const x0 = ml + k * gw + gw / 2, o = D.origenes[k];
    svg += `<text x="${x0}" y="${H - 5}" font-size="12" text-anchor="middle" fill="${TEXTO2}">${fechaEs(o)}</text>`;
    if (!p) return;
    const kr = menor(p.reglas), er = p.reglas[kr], falla = !(p.modelo < er);
    const barras = [[p.modelo, falla ? NARANJA : AZUL, x0 - bw - 2, `Prueba desde el ${fechaEs(o)}: el modelo falla ${num(p.modelo, 2)} unidades por cada 100 vendidas, a 10 días.`],
      [er, SEGUNDA, x0 + 2, `Prueba desde el ${fechaEs(o)}: ${NR[kr]}, la regla que menos falla en esa prueba, ${num(er, 2)} unidades por cada 100.`]];
    for (const [v, c, x, tip] of barras) svg += `<g tabindex="0" data-tip="${esc(tip)}"><rect x="${x}" y="${Y(v)}" width="${bw}" height="${Y(0) - Y(v)}" fill="${c}"/><text x="${x + bw / 2}" y="${Y(v) - 3}" font-size="11" text-anchor="middle" fill="${NEGRO}">${num(v, 1)}</text></g>`;
  });
  svg += '</svg>';
  grafico('g-pedido', 'Lo que falla cada prueba', 'Unidades por cada 100 vendidas, a 10 días', svg,
    [[AZUL, 'Modelo'], [SEGUNDA, 'La regla que menos falla en esa prueba'], [NARANJA, 'Modelo, en las pruebas en que falla más']]);
  // Tabla por departamento, en el orden de las categorías; con qué se pide, de la decisión del informe
  let h = '<table><thead><tr><th>Departamento</th><th class="n">Unidades: modelo</th><th class="n">Unidades: regla que menos falla</th><th>Regla que menos falla</th><th>Se pide con</th></tr></thead><tbody>';
  D.departamentos.forEach((x, j) => {
    const m = medir(D.u, i => r.sel[D.u.c[i]] && CD[D.u.c[i]] === j);
    if (!m) return;
    const k = menor(m.reglas);
    h += `<tr><td>${esc(x.id)} (${esc(NOMBRE_C[x.categoria])})</td><td class="n">${num(m.modelo, 1)}</td><td class="n">${num(m.reglas[k], 1)}</td><td>${esc(NR[k])}</td><td>${esc(conDe(D.recomendado[x.id] || 'modelo'))}</td></tr>`;
  });
  document.getElementById('d-pedido').innerHTML = h + '</tbody></table>';
  document.getElementById('pie-pedido').textContent = FUENTE + '; 13 pruebas de 10 días, una cada 28 días';
}

// ---------------------------------------------------------------- pestaña 3: dónde gana
function textoPierden(xs, tiendas) {
  const pierden = xs.filter(x => !(x.modelo < x.error_regla));
  if (!pierden.length) return tiendas ? 'En todas las tiendas de la selección' : 'En todos los departamentos de la selección';
  if (pierden.length === 1) {
    const x = pierden[0];
    return tiendas ? `En ${x.id} la regla falla menos por ${num(x.modelo - x.error_regla, 2)}` : `En ${x.id} falla menos ${NR[x.regla]}`;
  }
  return 'La regla falla menos en ' + listaY(pierden.map(x => x.id));
}
function dibujarDonde(r, t) {
  titulo(document.getElementById('t-donde'), t.donde);
  const sel = seleccionTexto();
  const gt = r.tiendas.filter(x => x.modelo < x.error_regla).length, gdp = r.deps.filter(x => x.modelo < x.error_regla).length;
  const sd = r.sumadoD, su = r.sumadoU, kd = sd ? menor(sd.reglas) : null, ku = su ? menor(su.reglas) : null;
  document.getElementById('c-donde').innerHTML = [
    cifra('tiendas_gana', gt, `${gt} de ${r.tiendas.length}`, 'Tiendas en que la previsión sumada falla menos', textoPierden(r.tiendas, true),
      `Tiendas de ${sel} en que la previsión en dólares, sumando sus departamentos, falla menos que la regla que menos falla en esa tienda, a 28 días: ${gt} de ${r.tiendas.length}.`),
    cifra('departamentos_gana', gdp, `${gdp} de ${r.deps.length}`, 'Departamentos en que el modelo falla menos', textoPierden(r.deps, false),
      `Departamentos de ${sel} en que el modelo falla menos en dólares que la regla que menos falla en ese departamento, a 28 días: ${gdp} de ${r.deps.length}.`),
    cifra('sumado_dolares', sd ? sd.modelo : null, sd ? num(sd.modelo, 1) : '—', 'Dólares que falla la previsión sumada por cada 100', sd ? `${mayus(NR[kd])}, ${num(sd.reglas[kd], 1)}` : '—',
      sd ? `Sumando cada día las combinaciones de ${sel}, la previsión falla ${num(sd.modelo, 2)} dólares por cada 100 vendidos, a 28 días. ${mayus(NR[kd])}, sumada igual, ${num(sd.reglas[kd], 2)}.` : 'Sin venta en esta selección.'),
    cifra('sumado_unidades', su ? su.modelo : null, su ? num(su.modelo, 1) : '—', 'Unidades que falla la previsión sumada por cada 100', su ? (ku === kd ? `La misma regla, ${num(su.reglas[ku], 1)}, a 10 días` : `${mayus(NR[ku])}, ${num(su.reglas[ku], 1)}, a 10 días`) : '—',
      su ? `Sumando cada día las combinaciones de ${sel}, la previsión falla ${num(su.modelo, 2)} unidades por cada 100 vendidas, a 10 días. ${mayus(NR[ku])}, sumada igual, ${num(su.reglas[ku], 2)}.` : 'Sin venta en esta selección.')
  ].join('');
  // Dos paneles con la misma escala: cada tienda sumando sus departamentos y cada departamento sin sumar
  const W = 1286, pw = 610, gap = 66, fila = 23, mt = 20, lab = 92;
  const filas = Math.max(r.tiendas.length, r.deps.length), H = mt + filas * fila + 6;
  const max = Math.max(1, ...r.tiendas.concat(r.deps).flatMap(x => [x.modelo, x.error_regla])) * 1.15;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Error de cada tienda y departamento">`;
  const panel = (x0, xs, cabecera, que) => {
    let s = `<text x="${x0}" y="${mt - 6}" font-size="13" font-weight="600" fill="${NEGRO}">${cabecera}</text>`;
    const X = v => x0 + lab + (pw - lab - 40) * v / max;
    xs.forEach((x, j) => {
      const y = mt + j * fila, falla = !(x.modelo < x.error_regla);
      s += `<text x="${x0 + lab - 8}" y="${y + 14}" font-size="12" text-anchor="end" fill="${NEGRO}">${esc(x.id)}</text>`;
      const barras = [[x.modelo, falla ? NARANJA : AZUL, y + 2, `${x.id}${que}: el modelo falla ${num(x.modelo, 2)} dólares por cada 100 vendidos, a 28 días.`],
        [x.error_regla, SEGUNDA, y + 11, `${x.id}${que}: ${NR[x.regla]}, la regla que menos falla aquí, ${num(x.error_regla, 2)} dólares por cada 100.`]];
      for (const [v, c, yy, tip] of barras) s += `<g tabindex="0" data-tip="${esc(tip)}"><rect x="${X(0)}" y="${yy}" width="${X(v) - X(0)}" height="8" fill="${c}"/><text x="${X(v) + 4}" y="${yy + 8}" font-size="11" fill="${NEGRO}">${num(v, 1)}</text></g>`;
    });
    return s;
  };
  svg += panel(0, r.tiendas, 'Cada tienda, sumando sus departamentos', ', sumando sus departamentos') + panel(pw + gap, r.deps, 'Cada departamento, sin sumar', '');
  svg += '</svg>';
  grafico('g-donde', 'Cada tienda y cada departamento', 'Dólares que falla por cada 100 vendidos, a 28 días', svg,
    [[AZUL, 'Modelo'], [SEGUNDA, 'La regla que menos falla en ese grupo'], [NARANJA, 'Modelo, donde falla más']]);
  document.getElementById('pie-donde').textContent = FUENTE;
}

// ---------------------------------------------------------------- pestaña 4: festivos
function dibujarFestivos(r, t) {
  titulo(document.getElementById('t-festivos'), t.festivos);
  const sel = seleccionTexto();
  document.getElementById('c-festivos').innerHTML = D.festivos.map((f, k) => {
    const x = r.festivos[k];
    return cifra('festivo_' + k, x ? x.modelo : null, x ? num(x.modelo, 1) : '—', `${f.nombre}, unidades que falla por cada 100`, x ? `${mayus(NR[x.regla])}, ${num(x.error_regla, 1)}` : '—',
      x ? `Desde la víspera de ${f.nombre} (${fechaEs(f.origen)}), a 10 días, la previsión del modelo en ${sel} falla ${num(x.modelo, 2)} unidades por cada 100 vendidas. La regla que menos falla esa vez es ${NR[x.regla]}, con ${num(x.error_regla, 2)}.` : 'Sin venta en esta selección.');
  }).join('');
  // Tres paneles: la venta y la previsión de cada día tras la víspera, sumadas en la selección
  const F = D.f, W = 1286, H = 196, pw = 400, gap = 43, ml = 50, mt = 8, mb = 22;
  const porDia = D.festivos.map(() => ({re: new Float64Array(11), pm: new Float64Array(11), hay: new Array(11).fill(false)}));
  for (let i = 0; i < F.c.length; i++) if (r.sel[F.c[i]]) {
    const s = porDia[F.o[i]], h = Math.round((Date.parse(F.fechas[F.t[i]]) - Date.parse(D.festivos[F.o[i]].origen)) / 864e5);
    s.re[h] += F.real[i]; s.pm[h] += F.modelo[i]; s.hay[h] = true;
  }
  const {paso, tope} = escala(Math.max(1, ...porDia.flatMap(s => [...s.re, ...s.pm])));
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Venta y previsión tras cada víspera">`;
  D.festivos.forEach((f, k) => {
    const x0 = k * (pw + gap), s = porDia[k], X = h => x0 + ml + (h - 1) * (pw - ml - 30) / 9, Y = v => mt + 14 + (H - mt - 14 - mb) * (1 - v / tope);
    svg += `<text x="${x0 + ml}" y="${mt + 6}" font-size="13" font-weight="600" fill="${NEGRO}">${esc(f.nombre)}</text>`;
    for (let y = 0; y <= tope + 1e-9; y += paso) svg += `<line x1="${x0 + ml}" x2="${x0 + pw - 20}" y1="${Y(y)}" y2="${Y(y)}" stroke="${REJILLA}"/><text x="${x0 + ml - 6}" y="${Y(y) + 4}" font-size="11" text-anchor="end" fill="${TEXTO2}">${num(y)}</text>`;
    const hs = []; for (let h = 1; h <= 10; h++) if (s.hay[h]) hs.push(h);
    const camino = v => hs.map((h, j) => (j ? 'L' : 'M') + X(h).toFixed(1) + ' ' + Y(v[h]).toFixed(1)).join('');
    svg += `<path d="${camino(s.re)}" fill="none" stroke="${AZUL}" stroke-width="1.8"/><path d="${camino(s.pm)}" fill="none" stroke="${SEGUNDA}" stroke-width="1.8" stroke-dasharray="5 3"/>`;
    for (const h of hs) {
      const dia = sumarDias(f.origen, h);
      if (h === hs[0] || h === hs[hs.length - 1] || h === 5) svg += `<text x="${X(h)}" y="${H - 5}" font-size="11" text-anchor="middle" fill="${TEXTO2}">${diaMes(dia)}</text>`;
      svg += `<g tabindex="0" data-tip="${esc(fechaEs(dia) + ', tras la víspera de ' + f.nombre + ': venta de ' + num(s.re[h]) + ' unidades; previsión del modelo, ' + num(s.pm[h]) + '.')}"><circle cx="${X(h)}" cy="${Y(s.re[h])}" r="3" fill="${AZUL}"/><rect x="${X(h) - 15}" y="${mt}" width="30" height="${H - mt - mb}" fill="transparent"/></g>`;
    }
  });
  svg += '</svg>';
  grafico('g-festivos', 'Cada víspera', 'Unidades al día; la previsión, a 10 días; Navidad sin el día de cierre', svg,
    [[AZUL, 'Venta'], [SEGUNDA, 'Previsión del modelo, a 10 días', true]]);
  document.getElementById('x-festivos').textContent = 'Cada festivo se comprobó una sola vez.';
  document.getElementById('pie-festivos').textContent = FUENTE;
}

// ---------------------------------------------------------------- pestaña 5: próximos días
function filasProximos(sel) {
  const P = D.proximos, out = [];
  for (let i = 0; i < P.c.length; i++) {
    if (!sel[P.c[i]]) continue;
    const tienda = D.tiendas[CT[P.c[i]]], dep = D.departamentos[CD[P.c[i]]];
    out.push({estado: tienda.estado, tienda: tienda.id, categoria: dep.categoria, departamento: dep.id, fecha: D.fechas_proximos[P.t[i]],
      unidades: P.unidades[i], dolares: P.dolares[i], con: P.regla[i] ? (D.recomendado[dep.id] || 'modelo') : 'modelo'});
  }
  return out;
}
function dibujarProximos(r, t) {
  titulo(document.getElementById('t-proximos'), t.proximos);
  const sel = seleccionTexto(), fp = D.fechas_proximos, du = D.dias_unidades;
  document.getElementById('c-proximos').innerHTML = [
    cifra('unidades_10', r.u10, num(r.u10), `Unidades previstas del ${diaMes(fp[0])} al ${fechaEs(fp[du - 1])}`, 'A 10 días, el plazo del pedido',
      `Unidades previstas de ${sel} del ${fechaEs(fp[0])} al ${fechaEs(fp[du - 1])}: ${num(r.u10)}. Es la suma de la previsión de cada día; en HOBBIES_2, la media de los últimos 28 días.`),
    cifra('dolares_10', r.d10, usd(r.d10), `Dólares previstos del ${diaMes(fp[0])} al ${fechaEs(fp[du - 1])}`, 'Los mismos 10 días',
      `Dólares previstos de ${sel} en los 10 primeros días: ${usd(r.d10)}.`),
    cifra('dolares_28', r.d28, usd(r.d28), `Dólares previstos del ${diaMes(fp[0])} al ${fechaEs(fp[fp.length - 1])}`, 'A 28 días, el mes de finanzas',
      `Dólares previstos de ${sel} del ${fechaEs(fp[0])} al ${fechaEs(fp[fp.length - 1])}: ${usd(r.d28)}.`),
    // Sin HOBBIES_2 en la selección, ninguna combinación va con una regla: se dice así, sin nombrar HOBBIES_2
    r.conRegla > 0
      ? cifra('con_regla', r.conRegla, num(r.conRegla), 'Combinaciones que se piden con una regla', 'HOBBIES_2, la regla que se recomienda',
        `Combinaciones de ${sel} que se prevén con la media de los últimos 28 días, la regla que se recomienda en HOBBIES_2: ${num(r.conRegla)} de ${r.nsel}.`)
      : cifra('con_regla', r.conRegla, num(r.conRegla), 'Combinaciones que se piden con una regla', 'Todo se pide con la previsión del modelo',
        `Ninguna combinación de ${sel} se prevé con una regla: todo se pide con la previsión del modelo.`)
  ].join('');
  // Gráfico: los dólares previstos de cada día, rayados porque son una previsión (G19)
  const n = fp.length, por = new Float64Array(n), filas = filasProximos(r.sel);
  for (const x of filas) por[fp.indexOf(x.fecha)] += x.dolares;
  const W = 1286, H = 132, ml = 4, mt = 14, mb = 18, cw = (W - ml) / n, Y0 = H - mb, tope = Math.max(1, ...por) * 1.05;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Dólares previstos cada día">`;
  svg += `<defs><pattern id="rayado-proximos" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#ffffff"/><line x1="0" y1="0" x2="0" y2="6" stroke="${AZUL}" stroke-width="3"/></pattern></defs>`;
  for (let j = 0; j < n; j++) {
    const x = ml + j * cw + 3, h = (Y0 - mt) * por[j] / tope;
    svg += `<g tabindex="0" data-tip="${esc(fechaEs(fp[j]) + ': ' + usd(por[j]) + ' previstos en ' + sel + '.')}"><rect x="${x}" y="${Y0 - h}" width="${cw - 6}" height="${h}" fill="url(#rayado-proximos)" stroke="${AZUL}"/><text x="${x + (cw - 6) / 2}" y="${Y0 - h - 3}" font-size="10" text-anchor="middle" fill="${NEGRO}">${num(por[j])}</text></g>`;
    svg += `<text x="${x + (cw - 6) / 2}" y="${H - 5}" font-size="10" text-anchor="middle" fill="${TEXTO2}">${diaMes(fp[j])}</text>`;
  }
  svg += '</svg>';
  grafico('g-proximos', 'Dólares previstos cada día', `Del ${fechaEs(fp[0])} al ${fechaEs(fp[n - 1])}`, svg);
  // La lista, de lo general a lo concreto: tienda, departamento y día; lo previsto y con qué, al final
  let h = '<table><thead><tr><th>Tienda</th><th>Departamento</th><th>Día</th><th class="n">Unidades previstas</th><th class="n">Dólares previstos</th><th>Se prevé con</th></tr></thead><tbody>';
  for (const x of filas) h += `<tr><td>${esc(x.tienda)}</td><td>${esc(x.departamento)}</td><td>${fechaEs(x.fecha)}</td><td class="n">${x.unidades === null ? '' : num(x.unidades)}</td><td class="n">${num(x.dolares)}</td><td>${esc(conDe(x.con))}</td></tr>`;
  document.getElementById('d-proximos').innerHTML = h + '</tbody></table>';
  document.getElementById('x-proximos').textContent = `${num(filas.length)} filas; las unidades, solo los 10 primeros días.`;
  document.getElementById('pie-proximos').textContent = `Fuente: previsión del modelo en uso hecha con la venta hasta el ${fechaEs(D.origen_proximos)}. Aún no hay venta real con que compararla.`;
}

// ---------------------------------------------------------------- CSV
function nombreCsv() {
  return ['proximos_dias', ...FILTROS.filter(k => E[k] !== null).map(k => E[k].toLowerCase())].join('_') + '_datos-' + D.fecha_datos + '.csv';
}
function textoCsv() {
  const lineas = [['Próximos días', ...seleccionPartes(), 'previsión hecha con la venta hasta el ' + fechaEs(D.origen_proximos)].join(' · '),
    'Estado;Tienda;Categoría;Departamento;Día;Unidades previstas;Dólares previstos;Se prevé con'];
  for (const x of filasProximos(seleccion())) lineas.push([NOMBRE_E[x.estado], x.tienda, NOMBRE_C[x.categoria], x.departamento, fechaEs(x.fecha),
    x.unidades === null ? '' : decCsv(x.unidades, 0), decCsv(x.dolares, 2), x.con === 'modelo' ? 'el modelo' : NR[D.reglas.indexOf(x.con)]].join(';'));
  return lineas.join('\r\n') + '\r\n';
}
function descargar() {
  const url = URL.createObjectURL(new Blob(['﻿' + textoCsv()], {type: 'text/csv;charset=utf-8'}));
  const a = document.createElement('a'); a.href = url; a.download = nombreCsv(); document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------- dirección de la página, filtros y pestañas
function leerDireccion(hash) {
  const p = new URLSearchParams(String(hash || '').replace(/^#/, ''));
  E.pestana = PESTANAS.includes(p.get('pestana')) ? p.get('pestana') : 'vision';
  E.estado = NOMBRE_E[p.get('estado')] ? p.get('estado') : null;
  E.tienda = EST_DE[p.get('tienda')] ? p.get('tienda') : null;
  E.categoria = NOMBRE_C[p.get('categoria')] ? p.get('categoria') : null;
  E.departamento = CAT_DE[p.get('departamento')] ? p.get('departamento') : null;
  normalizar();
}
function escribirDireccion() {
  const p = ['pestana=' + E.pestana];
  for (const k of FILTROS) if (E[k] !== null) p.push(k + '=' + encodeURIComponent(E[k]));
  history.replaceState(null, '', '#' + p.join('&'));
}
function opciones(id, valores, valor) {
  const el = document.getElementById(id);
  el.innerHTML = '<option value="">Todos</option>' + valores.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
  el.value = valor === null ? '' : valor;
}
function dibujar() {
  for (const p of PESTANAS) {
    document.getElementById('p-' + p).hidden = p !== E.pestana;
    const b = document.getElementById('b-' + p); b.setAttribute('aria-selected', String(p === E.pestana)); b.tabIndex = p === E.pestana ? 0 : -1;
  }
  opciones('f-estado', D.estados.map(e => [e.id, e.nombre]), E.estado);
  opciones('f-tienda', D.tiendas.filter(t => E.estado === null || t.estado === E.estado).map(t => [t.id, t.id]), E.tienda);
  opciones('f-categoria', D.categorias.map(c => [c.id, c.nombre]), E.categoria);
  opciones('f-departamento', D.departamentos.filter(x => E.categoria === null || x.categoria === E.categoria).map(x => [x.id, x.id]), E.departamento);
  document.getElementById('quitar').disabled = !hayFiltro();
  const r = calcular(), t = titulos(r), partes = seleccionPartes();
  document.getElementById('viendo').textContent = 'Viendo: ' + (partes.length ? partes.join(' · ') + ' · ' + r.nsel + ' de ' + NC : 'las ' + NC) + ' combinaciones de departamento y tienda';
  ({vision: dibujarVision, pedido: dibujarPedido, donde: dibujarDonde, festivos: dibujarFestivos, proximos: dibujarProximos})[E.pestana](r, t);
  ocultarTip();
}
function cambiar() { normalizar(); escribirDireccion(); dibujar(); }

// ---------------------------------------------------------------- etiquetas al pasar el ratón y con el tabulador
const TIP = document.getElementById('tip');
function mostrarTip(el) {
  TIP.textContent = el.dataset.tip; TIP.hidden = false;
  const r = el.getBoundingClientRect(), w = TIP.offsetWidth, h = TIP.offsetHeight;
  let x = r.left + r.width / 2 - w / 2, y = r.bottom + 8;
  if (y + h > window.innerHeight) y = r.top - h - 8;
  x = Math.max(8, Math.min(x, window.innerWidth - w - 8)); y = Math.max(8, y);
  TIP.style.left = x + 'px'; TIP.style.top = y + 'px';
}
function ocultarTip() { TIP.hidden = true; }
document.addEventListener('mouseover', ev => { const el = ev.target.closest('[data-tip]'); if (el) mostrarTip(el); else ocultarTip(); });
document.addEventListener('focusin', ev => { const el = ev.target.closest('[data-tip]'); if (el) mostrarTip(el); });
document.addEventListener('focusout', ocultarTip);
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') ocultarTip(); });
document.addEventListener('mouseleave', ocultarTip);

// ---------------------------------------------------------------- arranque
document.getElementById('f-estado').addEventListener('change', ev => { E.estado = ev.target.value || null; if (E.tienda !== null && EST_DE[E.tienda] !== E.estado) E.tienda = null; cambiar(); });
document.getElementById('f-tienda').addEventListener('change', ev => { E.tienda = ev.target.value || null; cambiar(); });
document.getElementById('f-categoria').addEventListener('change', ev => { E.categoria = ev.target.value || null; if (E.departamento !== null && CAT_DE[E.departamento] !== E.categoria) E.departamento = null; cambiar(); });
document.getElementById('f-departamento').addEventListener('change', ev => { E.departamento = ev.target.value || null; cambiar(); });
document.getElementById('quitar').addEventListener('click', () => { for (const k of FILTROS) E[k] = null; cambiar(); });
document.getElementById('descargar').addEventListener('click', descargar);
document.querySelectorAll('[role=tab]').forEach(b => {
  b.addEventListener('click', () => { E.pestana = b.dataset.p; cambiar(); });
  b.addEventListener('keydown', ev => {
    const i = PESTANAS.indexOf(E.pestana), d = ev.key === 'ArrowRight' ? 1 : ev.key === 'ArrowLeft' ? -1 : 0;
    if (!d) return;
    E.pestana = PESTANAS[(i + d + PESTANAS.length) % PESTANAS.length]; cambiar(); document.getElementById('b-' + E.pestana).focus();
  });
});
window.addEventListener('hashchange', () => { leerDireccion(location.hash); dibujar(); });
window.CUADRO = {irA: h => { leerDireccion(h); dibujar(); }, nombreCsv, textoCsv};
leerDireccion(location.hash); dibujar();
"""


def montar_html(datos):
    """El HTML entero, con los datos dentro de un bloque JSON (los «</» escapados para no cerrar el script)."""
    publicos = {k: v for k, v in datos.items() if not k.startswith("_")}
    js_datos = json.dumps(publicos, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    return ("<!doctype html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>Previsión de la venta</title>\n<style>" + CSS + "</style>\n</head>\n<body>\n" + CUERPO
            + "\n<script type=\"application/json\" id=\"datos\">" + js_datos + "</script>\n<script>" + JS
            + "</script>\n</body>\n</html>\n")


# =====================================================================================================================
# PRINCIPAL
# =====================================================================================================================

def principal(raiz=RAIZ):
    """Comprueba, calcula, comprueba otra vez y escribe el HTML, el CSV y el JSON del cuadro."""
    raiz = Path(raiz)
    if Path(sys.executable).resolve() != PYTHON_CASO.resolve():
        raise Parada(f"este no es el intérprete del caso: {sys.executable}")
    marca = reloj()
    huella_antes = huella_data(raiz)
    marca("huella de data/ al empezar")
    validaciones = {}
    # Entradas: existen y son más nuevas que su script
    pares = [(raiz / e, raiz / s) for e, s in ENTRADAS]
    faltan = [str(e) for e, _ in pares if not e.is_file()]
    exigir(not faltan, f"faltan entradas: {faltan}")
    validaciones["entradas_mas_nuevas"] = comprobar_orden(pares)
    pf = leer_json(raiz / PRUEBA_FINAL)
    resumen_lote = leer_json(raiz / LOTE_RESUMEN)
    conf = leer_json(raiz / CONFIGURACION)
    # La fecha de los datos: la prueba final acaba el 22/05/2016 y el lote prevé desde ese día
    validaciones["fecha_datos_igual"] = (pf["fin_prueba_final"] == FECHA_DATOS
                                         and resumen_lote.get("origen_dado") == FECHA_DATOS
                                         and [o["fecha_datos"] for o in resumen_lote["origenes"]] == [FECHA_DATOS])
    # El lote se hizo con el modelo en uso, el mismo que midió la prueba final en su variante reentrenado
    validaciones["lote_del_modelo_en_uso"] = (resumen_lote["modelos"] == conf["modelo_en_uso"]
                                              and resumen_lote["origenes"][0]["modelo"]["huellas"]
                                              == pf["modelos"][VARIANTE]["huellas"]
                                              and resumen_lote["entradas_sin_cambiar"] is True)
    # La huella de data/raw/ es la que dejó la prueba final
    raw = {r: sha256(raiz / r) for r in pf["huellas_despues"]}
    validaciones["raw_igual_que_la_prueba"] = raw == pf["huellas_despues"]
    marca("entradas, orden, fechas y huellas")
    # Lectura de las tablas
    prev = pd.read_parquet(raiz / PREVISIONES)
    hechos = pd.read_parquet(raiz / HECHOS_PF)
    dim_tienda, dim_producto = pd.read_parquet(raiz / DIM_TIENDA), pd.read_parquet(raiz / DIM_PRODUCTO)
    lote = pd.read_parquet(raiz / LOTE_PARQUET)
    plazos = {o: int(h) for o, h in pf["que_se_mide"]["horizontes"].items()}
    # El lote completo: 70 combinaciones por 10 días en unidades y 28 en dólares, desde el día siguiente al último dato
    combinaciones = len(set(zip(prev["store_id"], prev["dept_id"])))
    completo = not lote["prevision"].isna().any() and bool((lote["prevision"] >= 0).all())
    for o, h in plazos.items():
        parte = lote[(lote["objetivo"] == o).to_numpy()]
        esperadas = set(pd.date_range(ORIGEN_PROXIMOS + pd.Timedelta(1, "D"), periods=h, freq="D"))
        completo = completo and len(parte) == combinaciones * h and set(pd.to_datetime(parte["date"])) == esperadas
    validaciones["lote_completo"] = completo
    recomendado = recomendado_de(pf)
    validaciones["recomendado_del_json"] = recomendado.get("HOBBIES_2") == "media_28_dias"
    festivos = [{"nombre": n, "origen": o} for n, o in pf["que_se_mide"]["festivos"].items()]
    origenes = pf["que_se_mide"]["origenes"]
    minimo = minimo_gana(len(origenes))
    regla_prox = reglas_para_proximos(hechos, ORIGEN_PROXIMOS, plazos)
    marca("tablas y media de los últimos 28 días")
    datos = preparar_datos(prev, dim_tienda, dim_producto, lote, regla_prox, festivos, origenes, recomendado, minimo)
    marca("datos del HTML")
    comparadas = comparar_con_json(datos, pf)
    validaciones["cifras_iguales_al_json"] = all(c["coinciden"] for c in comparadas)
    otra = venta_por_otro_camino(datos, hechos)
    validaciones["venta_por_otro_camino"] = iguales(otra["cuadro"], otra["hechos_prueba_final"], 1e-12)
    marca("comparación con el JSON")
    validaciones["sin_resultados_escritos"] = buscar_resultados_escritos(Path(__file__).read_text(encoding="utf-8")) == []
    html_texto = montar_html(datos)
    vetadas = sin_prohibidas(html_texto)
    validaciones["sin_palabras_vetadas"] = vetadas == []
    fallan = [k for k, v in validaciones.items() if v is not True]
    if fallan:
        malas = [c for c in comparadas if not c["coinciden"]][:10]
        raise Parada(f"no pasan estas comprobaciones: {fallan}; cifras distintas: {malas}; vetadas: {vetadas}")
    # Se escribe el HTML y el CSV; después se mira que data/ no ha cambiado
    SALIDA_HTML.write_text(html_texto, encoding="utf-8")
    SALIDA_CSV.write_text(texto_csv(datos, {}), encoding="utf-8-sig", newline="")
    huella_despues = huella_data(raiz)
    marca("HTML, CSV y huella de data/ al acabar")
    validaciones["huella_data_igual"] = huella_antes == huella_despues
    if not validaciones["huella_data_igual"]:
        SALIDA_HTML.unlink(missing_ok=True)
        SALIDA_CSV.unlink(missing_ok=True)
        raise Parada("la huella de data/ cambió entre el principio y el final: se borran el HTML y el CSV")
    js = {"script": SCRIPT, "fecha_datos": FECHA_DATOS, "origen_proximos": ORIGEN_PROXIMOS.strftime("%Y-%m-%d"),
          "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
          "variante": VARIANTE, "modelo_en_uso": conf["modelo_en_uso"],
          "entradas": [{"ruta": Path(e).relative_to(raiz).as_posix(), "script": Path(s).relative_to(raiz).as_posix(),
                        "sha256": sha256(e)} for e, s in pares],
          "cifras_sin_filtros": resumen(datos, {}),
          "titulos_sin_filtros": titulos(datos, {}),
          "comparadas_con_el_json": comparadas,
          "venta_por_otro_camino": otra,
          "recomendado": recomendado,
          "proximos_dias": {"filas": len(filas_proximos(datos, {})), "desde": datos["fechas_proximos"][0],
                            "hasta": datos["fechas_proximos"][-1], "dias_unidades": datos["dias_unidades"],
                            "csv": SALIDA_CSV.relative_to(raiz).as_posix()},
          "huella_data": {"antes": huella_antes, "despues": huella_despues},
          "validaciones": validaciones,
          "decisiones": [
              "Las cifras de la visión general, el pedido y dónde gana son del modelo en uso (variante reentrenado) en "
              "el último año guardado; sin el 25 de diciembre, con la previsión acotada en cero y, en unidades, "
              "redondeada, como las midió la prueba final.",
              "La regla que menos falla es la de la selección: la de menor error de las tres con las mismas filas; en "
              "cada prueba, la de menor error en esa prueba (como el veredicto de reglas, apartado 7).",
              "Un título dice «falla menos» solo si el modelo gana al menos 10 de las 13 pruebas en la selección "
              "(reglas, apartado 7, sin intervalo: con un filtro estrecho no hay combinaciones bastantes para remuestrear).",
              "Dónde gana va en dólares a 28 días: cada tienda con la previsión sumada de sus departamentos y cada "
              "departamento sin sumar, como el informe final.",
              "En los próximos días, HOBBIES_2 va con la media de los últimos 28 días hasta el 22/05/2016, calculada "
              "con prevision_recursiva.reglas_sencillas sobre hechos_prueba_final; en unidades, redondeada.",
              "La etiqueta y el contexto de las cifras pueden partirse en dos líneas para que el nombre entero de la "
              "regla quepa sin cortarse; el número grande no se parte."]}
    SALIDA_JSON.write_text(json.dumps(nativo(js), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    marca("JSON del cuadro")
    return js


if __name__ == "__main__":
    try:
        r = principal()
    except Parada as e:
        print(f"PARADO: {e}")
        sys.exit(1)
    print("OK: informes/cuadro_mando.html, informes/cuadro_mando.json e informes/cuadro_mando_proximos_dias.csv")
    for p, cs in r["cifras_sin_filtros"].items():
        print(p, {c["id"]: c["valor"] for c in cs})
    print("comparadas con el JSON:", len(r["comparadas_con_el_json"]), "; venta por otro camino:",
          r["venta_por_otro_camino"])
