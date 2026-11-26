"""Preselección de variables de los dos modelos de previsión del caso 69, solo con el entrenamiento.

Aplica el método preseleccion-variables con lo que aprobó el responsable del caso el 24/11/2026 (reglas-negocio.md §7, «Preselección de
variables»): en los dos objetivos por separado; en Ridge, todos los pasos; en HistGradientBoosting, solo quitar
lo que no puede entrar (§2) y una variante por variable (§5); modo comparativo (eliminación recursiva con validación
cruzada, información mutua e importancia por permutación); consenso amplio; las variables obligatorias, sin votar.

La tabla que entra a los métodos sale del preprocesador de scripts/preparacion_prevision.py ajustado con el
entrenamiento. El script no abre la validación ni la prueba final (validación 1 del método, apartado 8). Los pliegues van por
fecha y la reserva de la permutación es el 20 % más reciente del entrenamiento. Los modelos auxiliares van con valores
fijos y semilla, sin búsqueda: sus cifras solo ordenan.

Depende de scripts/11_variables_modelo.py y de scripts/12_preparacion.py (error 2): lee la tabla de entrenamiento, cuya
huella se comprueba contra informes/variables_modelo.json, e informes/preparacion.json, que tiene que estar en OK.

Deja informes/preseleccion.json (estructura de resultado.md, con las dos listas de cada objetivo y la tabla de
decisiones) y una ficha en config/modelo/registro-transformaciones.md.

Uso: python -W error scripts/13_preseleccion.py [--raiz CARPETA] [--medir FRACCION]
Con --medir, ejecuta todo sobre la fracción más reciente de días del entrenamiento, imprime el tiempo y la estimación
para la tabla entera y no escribe nada. Sale con 0 si el estado es OK o AVISO y con 1 si es PARADO o ERROR.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import json
import math
import platform
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import sklearn
from scipy.stats import chi2_contingency
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.feature_selection import RFECV, mutual_info_regression
from sklearn.inspection import permutation_importance
from sklearn.model_selection import TimeSeriesSplit

# El preprocesador vive en un módulo que no ejecuta nada al importarse (error 1)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preparacion_prevision import (OBJETIVOS, columnas_entrada, construir_preprocesador,  # noqa: E402
                                   nombre_salida)

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método preseleccion-variables con que se escribió este script
SCRIPT_REL = "scripts/13_preseleccion.py"
FECHA_DATOS = "2015-05-22"
ENTRENAMIENTO_REL = "data/processed/hechos_modelo_entrenamiento.parquet"
PREPARACION_REL = "informes/preparacion.json"
VARIABLES_REL = "informes/variables_modelo.json"
MATRIZ_REL = "config/modelo/matriz_transformaciones.md"
REGISTRO_REL = "config/modelo/registro-transformaciones.md"
JSON_REL = "informes/preseleccion.json"
COLUMNA_FECHA = "date"
CLAVE_SERIE = ["store_id", "dept_id"]
# Lo que nunca se abre: la validación, la prueba final y un lote de producción (método, apartado 8, validación 1)
NO_SE_ABRE = re.compile(r"validacion|prueba|produccion")

# Parámetros del método (parametros.md), con el valor del caso
SEMILLA = 42                         # la de preparacion-modelo
PLIEGUES = 3                         # TimeSeriesSplit(3) sobre los días, sin barajar
METRICA = "neg_mean_absolute_error"  # objetivo continuo
REPETICIONES = 10                    # permutación
FRACCION_RESERVA = 0.2               # el 20 % más reciente del entrenamiento
LIMITE_MUESTREO = 100_000            # por debajo, sin muestra
UMBRAL_SPEARMAN = 0.5
UMBRAL_CRAMER = 0.5
ARBOLES_RFECV = 100
PROFUNDIDAD_RFECV = 5
ESCENARIO = "consenso amplio"        # reglas, apartado 7
VOTOS_MINIMOS = {"consenso fuerte": 3, "consenso amplio": 2, "todas las candidatas": 1}
MODO = "comparativo"                 # reglas, apartado 7

# Los dos algoritmos y los pasos del método que se aplican a cada uno (reglas, apartado 7)
ALGORITMOS = {"Ridge": "todos los pasos del método (§2 a §7)",
              "HistGradientBoosting": "solo §2 (fuera lo que no puede entrar) y §5 (una variante por variable)"}

# El origen de las 30 columnas evento_<nombre>: la matriz las trata como una sola variable (respuesta 3)
ORIGEN_EVENTO = "evento_<nombre>"
# Las variables que se quedan sin votar, con su motivo (reglas, apartado 7, «Preselección de variables»). «Los festivos» son las
# tres familias de eventos (petición de la preselección)
MOTIVO_SERIE = "un modelo para las 70 combinaciones con la tienda y el departamento como variables (planteamientos §2, decisión 6)"
MOTIVO_EFECTOS = "la pregunta 4 de la ficha pide sus efectos «como variables del modelo»"
OBLIGATORIAS = {"store_id": MOTIVO_SERIE, "dept_id": MOTIVO_SERIE,
                "event_name_1": f"festivos: {MOTIVO_EFECTOS}", "event_name_2": f"festivos: {MOTIVO_EFECTOS}",
                ORIGEN_EVENTO: f"festivos: {MOTIVO_EFECTOS}", "snap": f"días SNAP: {MOTIVO_EFECTOS}",
                "weekday": f"día de la semana: {MOTIVO_EFECTOS}", "month": f"mes: {MOTIVO_EFECTOS}",
                "precio_medio_semana_anterior": f"precio medio de la semana anterior: {MOTIVO_EFECTOS}"}
# Dos codificaciones del mismo evento: si las dos quedan en la lista, es un grupo ambiguo (método, apartado 5) que decide el responsable del caso
EVENTOS_POR_COLUMNA = ["event_name_1", "event_name_2"]
EVENTOS_UNA_POR_EVENTO = [ORIGEN_EVENTO]

# Los apartados del manual que se aplican (teoria.md del método)
TEORIA = [{"apartado": "36.2", "por_que": "la selección solo con el entrenamiento, con pliegues hacia delante"},
          {"apartado": "36.5", "por_que": "información mutua con semilla y máscara de discretas"},
          {"apartado": "36.6", "por_que": "RFECV con un bosque de valores fijos y pliegues por fecha"},
          {"apartado": "36.7", "por_que": "permutación sobre la reserva interna que el modelo auxiliar no vio"},
          {"apartado": "36.8", "por_que": "la votación de los tres métodos y el corte por salto natural"},
          {"apartado": "36.9", "por_que": "pares parecidos de distinto origen, Spearman y V de Cramér"}]


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_json_limpio(obj):
    """Tipos de numpy y pandas a Python; NaN e infinito a null (programacion-del-caso, error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json_limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [a_json_limpio(v) for v in (sorted(obj) if isinstance(obj, set) else obj)]
    if obj is None or obj is pd.NA:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        valor = float(obj)
        return None if math.isnan(valor) or math.isinf(valor) else valor
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def entorno():
    """Versiones con que se ejecuta el script."""
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
            "pyarrow": pyarrow.__version__, "scikit-learn": sklearn.__version__, "ejecutable": sys.executable}


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def leer_tabla(raiz, rel, abiertas):
    """Lee un Parquet del caso y apunta su ruta: la validación 1 comprueba que ninguna es la validación."""
    abiertas.append(rel)
    return pd.read_parquet(raiz / rel)


# ══ 3. La matriz y el origen de cada columna (método, apartado 5) ═════════════════════════
def expandir_celda(celda):
    """Los nombres de variable de la primera celda de una fila de la matriz.

    Entiende las tres formas de la matriz: un nombre suelto, un rango («`<obj>_lag_1` a `<obj>_lag_7`») y una lista
    con sufijos («`<obj>_lag_14`, `_lag_21`, `_lag_28`»).
    """
    rango = re.fullmatch(r"`(.+_lag_)(\d+)` a `\1(\d+)`", celda.strip())
    if rango:
        return {f"{rango.group(1)}{k}" for k in range(int(rango.group(2)), int(rango.group(3)) + 1)}
    tokens = re.findall(r"`([^`]+)`", celda) or [celda.strip()]
    nombres = set()
    prefijo = re.match(r"(.*?)_(lag|media)_", tokens[0])
    for t in tokens:
        nombres.add(f"{prefijo.group(1)}{t}" if t.startswith("_") and prefijo else t)
    return nombres


def variables_matriz(texto, objetivo):
    """Las variables de las filas de la matriz que entran («sí» en la columna entra), con <obj> = objetivo."""
    nombres = set()
    cabecera = None
    for linea in texto.splitlines():
        if not linea.startswith("|"):
            cabecera = None
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if cabecera is None:
            cabecera = celdas
            continue
        if set(linea.strip()) <= set("|-: ") or "variable" not in cabecera or "entra" not in cabecera:
            continue
        if len(celdas) != len(cabecera) or not celdas[cabecera.index("entra")].lower().startswith("sí"):
            continue
        nombres |= expandir_celda(celdas[cabecera.index("variable")])
    return {n.replace("<obj>", objetivo) for n in nombres}


def origenes(ct, columnas_salida, columnas_evento):
    """Columna de salida → variable de origen, leído de las ramas del ColumnTransformer ajustado."""
    origen = {}
    for nombre, _, cols in ct.transformers_:
        if nombre == "remainder":
            continue
        for c in cols:
            if nombre.startswith("ohe"):
                origen.update({s: c for s in columnas_salida if s.startswith(f"{c}_ohe_")})
            elif nombre == "pasa":
                origen[c] = ORIGEN_EVENTO if c in columnas_evento else c
            else:
                origen[nombre_salida(nombre, c)] = c
    return origen


def familias_de(origen):
    """Las variables de origen con más de una columna: una codificación o las evento_<nombre> (método, apartado 5, familia)."""
    grupos = {}
    for columna, o in origen.items():
        grupos.setdefault(o, []).append(columna)
    return {o: cols for o, cols in grupos.items() if len(cols) > 1}


# ══ 4. Pliegues y reserva por fecha (método, apartado 4; aprendizaje-automatico §3) ═══════
def pliegues_por_fecha(fechas, n):
    """TimeSeriesSplit(n) sobre los días, sin barajar, pasado a filas: un día entero cae en un solo lado."""
    fechas = pd.Series(fechas).reset_index(drop=True)
    dias = np.array(sorted(fechas.unique()))
    pliegues = []
    for tr, te in TimeSeriesSplit(n).split(dias):
        pliegues.append((np.flatnonzero(fechas.isin(dias[tr]).to_numpy()),
                         np.flatnonzero(fechas.isin(dias[te]).to_numpy())))
    return pliegues


def c_pliegues_por_fecha(fechas, pliegues):
    """Control: en cada pliegue todo el entrenamiento es anterior a la prueba y cada día de la prueba va entero."""
    fechas = pd.Series(fechas).reset_index(drop=True)
    detalle = []
    ok = bool(pliegues)
    for tr, te in pliegues:
        f_tr, f_te = fechas.iloc[tr], fechas.iloc[te]
        completo = int(fechas.isin(f_te.unique()).sum()) == len(te)
        bien = len(tr) > 0 and len(te) > 0 and f_tr.max() < f_te.min() and completo
        detalle.append({"filas_ajuste": len(tr), "filas_prueba": len(te), "hasta": f_tr.max(), "desde": f_te.min(),
                        "dias_enteros": completo, "bien": bool(bien)})
        ok = ok and bool(bien)
    return ok, detalle


def dias_de_reserva(n_dias, fraccion):
    """Cuántos días van a la reserva: la fracción de los días hacia arriba (error 14), sin el ruido de la coma."""
    return math.ceil(round(fraccion * n_dias, 9))


def reserva_reciente(fechas, fraccion):
    """Máscara de las filas de los días más recientes: la fracción de los días, hacia arriba."""
    fechas = pd.Series(fechas).reset_index(drop=True)
    dias = sorted(fechas.unique())
    return fechas >= dias[-dias_de_reserva(len(dias), fraccion)]


def c_reserva_reciente(fechas, mascara, fraccion):
    """Control: la reserva son exactamente los días más recientes, en la fracción fijada."""
    fechas = pd.Series(fechas).reset_index(drop=True)
    mascara = pd.Series(mascara).reset_index(drop=True).astype(bool)
    reserva, resto = fechas[mascara], fechas[~mascara]
    esperados = dias_de_reserva(fechas.nunique(), fraccion)
    ok = len(reserva) > 0 and len(resto) > 0 and reserva.min() > resto.max() and reserva.nunique() == esperados
    return bool(ok), {"dias_reserva": int(reserva.nunique()), "dias_esperados": esperados, "filas_reserva": len(reserva),
                      "desde": reserva.min() if len(reserva) else None, "hasta_el_resto": resto.max() if len(resto) else None}


# ══ 5. Cada variable sola y los métodos (método, apartado 3 y §4; manual 36.5 a 36.7) ═════
def ranking_mi(x, y, semilla=SEMILLA):
    """Información mutua de cada columna con el objetivo, con su puesto desde 1 (manual 36.5).

    Máscara de discretas: las columnas con 10 valores o menos (las 0 y 1), como el manual. Empates por el nombre.
    """
    discretas = (x.nunique() <= 10).to_numpy()
    valor = mutual_info_regression(x, y, discrete_features=discretas, random_state=semilla)
    r = pd.DataFrame({"columna": x.columns, "mi": valor}).sort_values(["mi", "columna"], ascending=[False, True])
    r["ranking_mi"] = np.arange(1, len(r) + 1)
    return r.reset_index(drop=True)


def ranking_rfecv(x, y, pliegues, semilla=SEMILLA):
    """Eliminación recursiva con validación cruzada por fecha (manual 36.6); las de puesto 1 son las elegidas.

    Bosque con valores fijos y semilla, sin búsqueda (parametros.md, «modelos auxiliares»). n_jobs solo reparte los
    árboles entre núcleos: con la semilla fija el bosque sale igual.
    """
    estimador = RandomForestRegressor(n_estimators=ARBOLES_RFECV, max_depth=PROFUNDIDAD_RFECV, random_state=semilla,
                                      n_jobs=-1)
    r = RFECV(estimador, cv=pliegues, scoring=METRICA).fit(x, y)
    return (pd.DataFrame({"columna": x.columns, "ranking_rfe": r.ranking_}).sort_values(["ranking_rfe", "columna"])
            .reset_index(drop=True)), int(r.n_features_)


def ranking_per(x, y, reserva, semilla=SEMILLA):
    """Importancia por permutación sobre la reserva interna (manual 36.7), con el modelo auxiliar ajustado sin ella."""
    auxiliar = HistGradientBoostingRegressor(random_state=semilla).fit(x[~reserva.to_numpy()], y[~reserva.to_numpy()])
    p = permutation_importance(auxiliar, x[reserva.to_numpy()], y[reserva.to_numpy()], scoring=METRICA,
                               n_repeats=REPETICIONES, random_state=semilla, n_jobs=1)
    r = pd.DataFrame({"columna": x.columns, "permutacion": p.importances_mean, "desviacion": p.importances_std})
    r = r.sort_values(["permutacion", "columna"], ascending=[False, True])
    r["ranking_per"] = np.arange(1, len(r) + 1)
    return r.reset_index(drop=True)


def corte_salto(valores):
    """El corte por salto natural (metodos.md, «El corte»): la mayor caída entre dos valores seguidos, de mayor a
    menor. Marca las que quedan por encima de la caída; devuelve el último valor marcado y el conjunto."""
    s = valores.sort_index().sort_values(ascending=False, kind="stable")
    if len(s) < 2:
        return (float(s.iloc[0]) if len(s) else None), set(s.index)
    caidas = s.to_numpy()[:-1] - s.to_numpy()[1:]
    k = int(np.argmax(caidas))
    return float(s.iloc[k]), set(s.index[:k + 1])


def tabla_votos(r_mi, r_rfe, r_per):
    """Une los tres rankings y cuenta los votos de cada columna: ranking 1 en RFECV y por encima del corte en los otros."""
    corte_mi, marca_mi = corte_salto(r_mi.set_index("columna")["mi"])
    corte_per, marca_per = corte_salto(r_per.set_index("columna")["permutacion"])
    t = (r_mi.merge(r_rfe, on="columna", how="outer", validate="1:1")
         .merge(r_per[["columna", "permutacion", "ranking_per"]], on="columna", how="outer", validate="1:1"))
    t["voto_mi"] = t["columna"].isin(marca_mi)
    t["voto_rfe"] = t["ranking_rfe"] == 1
    t["voto_per"] = t["columna"].isin(marca_per)
    t["votos"] = t[["voto_mi", "voto_rfe", "voto_per"]].sum(axis=1).astype("int64")
    cortes = {"mi": {"valor": corte_mi, "como": "salto: la mayor caída entre dos valores seguidos"},
              "permutacion": {"valor": corte_per, "como": "salto: la mayor caída entre dos valores seguidos"}}
    return t.sort_values("ranking_mi").reset_index(drop=True), cortes


def decidir_por_votos(votos, origen, obligatorias, escenario):
    """Decisión de la votación para cada columna: las obligatorias entran sin votar; las demás, con los votos que pide
    el escenario (método, apartado 4)."""
    minimo = VOTOS_MINIMOS[escenario]
    decision = {}
    for fila in votos.itertuples():
        o = origen.get(fila.columna)
        if o in obligatorias:
            decision[fila.columna] = {"entra": True, "motivo": f"obligatoria, sin votar: {obligatorias[o]}"}
        else:
            entra = int(fila.votos) >= minimo
            decision[fila.columna] = {"entra": entra, "motivo": f"{int(fila.votos)} votos de 3; {escenario} pide "
                                                                 f"{minimo}"}
    return decision


# ══ 6. Lo que no puede entrar y las variables del momento (método, apartado 2) ════════════
def fuera_de_entrada(entrada, x, origen, prohibidas, obligatorias, familias):
    """Las columnas que no pueden entrar: una prohibida o el objetivo entre las de entrada, y las constantes.

    Una constante que pertenece a una familia o a una obligatoria no se quita sola: se dice y queda para el responsable del caso.
    """
    fuera = [{"columna": c, "motivo": "prohibida"} for c in entrada if c in prohibidas]
    avisos = []
    for c in x.columns[(x.nunique(dropna=False) <= 1).to_numpy()]:
        if origen[c] in familias or origen[c] in obligatorias:
            avisos.append({"columna": c, "aviso": "constante en entrenamiento, dentro de una familia u obligatoria"})
        else:
            fuera.append({"columna": c, "motivo": "constante"})
    return fuera, avisos


def variables_del_momento(ent, entrada, columnas_evento):
    """Las variables de entrada con el mismo valor en todas las filas de cada fecha (método, apartado 2)."""
    distintos = ent.groupby(COLUMNA_FECHA)[entrada].nunique(dropna=False).max()
    momento = {c for c in entrada if distintos[c] <= 1}
    origen_momento = {ORIGEN_EVENTO if c in columnas_evento else c for c in momento}
    if not all(c in momento for c in columnas_evento):
        origen_momento.discard(ORIGEN_EVENTO)
    return origen_momento


# ══ 7. Las que dicen lo mismo (método, apartado 6; manual 36.9) ═══════════════════════════
def pares_spearman(x, origen, umbral):
    """Cada par de numéricas de distinto origen con Spearman absoluto igual o mayor que el umbral, una vez."""
    if x.shape[1] < 2:
        return []
    c = x.corr(method="spearman").abs()
    i, j = np.triu_indices_from(c, k=1)
    t = pd.DataFrame({"columna_1": c.index[i], "columna_2": c.columns[j], "valor": c.to_numpy()[i, j]})
    t = t[(t["columna_1"].map(origen) != t["columna_2"].map(origen)) & (t["valor"] >= umbral)]
    t = t.sort_values(["valor", "columna_1", "columna_2"], ascending=[False, True, True])
    return [{"columna_1": r.columna_1, "columna_2": r.columna_2, "medida": "spearman", "valor": float(r.valor)}
            for r in t.itertuples()]


def cramer_v(a, b):
    """V de Cramér entre dos categóricas, sin la corrección de Yates."""
    tabla = pd.crosstab(a, b)
    if min(tabla.shape) < 2:
        return 0.0
    chi2 = chi2_contingency(tabla, correction=False)[0]
    return float(math.sqrt(chi2 / (tabla.to_numpy().sum() * (min(tabla.shape) - 1))))


def categorica_de_origen(ent, origen_nombre, columnas_evento):
    """La variable categórica de un origen, antes de codificar: las evento_<nombre> como el evento o eventos del día."""
    if origen_nombre == ORIGEN_EVENTO:
        nombres = np.array([c.removeprefix("evento_") for c in columnas_evento], dtype=object)
        marcas = ent[columnas_evento].to_numpy() == 1
        return pd.Series(["+".join(nombres[f]) or "sin evento" for f in marcas], index=ent.index)
    return ent[origen_nombre].astype("str").fillna("sin evento")


def pares_cramer(ent, origenes_categoricos, columnas_evento, umbral):
    """Cada par de categóricas de distinto origen con V de Cramér igual o mayor que el umbral, una vez."""
    series = {o: categorica_de_origen(ent, o, columnas_evento) for o in sorted(origenes_categoricos)}
    pares = []
    nombres = list(series)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1:]:
            v = cramer_v(series[a], series[b])
            if v >= umbral:
                pares.append({"columna_1": a, "columna_2": b, "medida": "cramer", "valor": v})
    return sorted(pares, key=lambda p: (-p["valor"], p["columna_1"], p["columna_2"]))


def resolver_pares(pares, valor, es_obligatoria):
    """De cada par, del más fuerte al más flojo, sale la de menos valor; una obligatoria gana el par.

    Si una del par ya salió, el par queda resuelto. Si las dos son obligatorias, no sale ninguna.
    """
    quitadas = set()
    for p in pares:
        a, b = p["columna_1"], p["columna_2"]
        if a in quitadas or b in quitadas:
            p["sale"] = "ninguna: el par ya quedó resuelto"
            continue
        if es_obligatoria(a) and es_obligatoria(b):
            p["sale"] = "ninguna: las dos son obligatorias"
            continue
        if es_obligatoria(a) or es_obligatoria(b):
            sale = b if es_obligatoria(a) else a
            p["sale"] = f"{sale} (la otra es obligatoria)"
        else:
            sale = b if valor[a] >= valor[b] else a
            p["sale"] = sale
        quitadas.add(sale)
    return quitadas


def apariciones(pares):
    """En cuántos pares sale cada variable, mirando las dos columnas del par."""
    cuenta = {}
    for p in pares:
        for c in (p["columna_1"], p["columna_2"]):
            cuenta[c] = cuenta.get(c, 0) + 1
    return dict(sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0])))


# ══ 8. Las seis validaciones (método, apartado 8) y los controles de la petición ═════════════
def v_sin_validacion(abiertas):
    """1. Nada se ajustó con la validación ni con un lote de producción: no se abrió ninguna."""
    malas = [a for a in abiertas if NO_SE_ABRE.search(Path(a).name)]
    return bool(abiertas) and not malas, {"abiertas": list(abiertas), "prohibidas_abiertas": malas}


def v_origen_en_matriz(finales, origen, vars_matriz):
    """2. Cada columna final tiene su variable de origen entre las que entran en la matriz."""
    faltan = [c for c in finales if origen.get(c) not in vars_matriz]
    return not faltan, {"sin_origen_en_matriz": faltan}


def v_familias_enteras(finales, familias):
    """3. Ninguna familia quedó a medias."""
    puestas = set(finales)
    a_medias = sorted(o for o, cols in familias.items() if 0 < sum(c in puestas for c in cols) < len(cols))
    return not a_medias, {"a_medias": a_medias}


def v_tope(tope, n):
    """4. En los lineales, el número de columnas no pasa del tope, si el tope aplica."""
    ok = (not tope["aplica"]) or (tope["maximo_columnas"] is not None and n <= tope["maximo_columnas"])
    return bool(ok), {"aplica": tope["aplica"], "maximo": tope["maximo_columnas"], "columnas": n}


def v_sin_prohibidas(finales, origen, prohibidas):
    """5. Ningún identificador, objetivo ni prohibida en la lista, ni como columna ni como origen."""
    malas = [c for c in finales if c in prohibidas or origen.get(c) in prohibidas]
    return not malas, {"prohibidas": malas}


def v_lista_valida(finales):
    """6. La lista no está vacía y no tiene nombres repetidos."""
    repetidos = sorted({c for c in finales if list(finales).count(c) > 1})
    return bool(finales) and not repetidos, {"columnas": len(finales), "repetidos": repetidos}


def c_obligatorias_dentro(finales, origen, obligatorias):
    """Control: todas las columnas de cada variable obligatoria están en la lista, y cada obligatoria tiene columnas."""
    columnas = {o: [c for c, oc in origen.items() if oc == o] for o in obligatorias}
    sin_columnas = sorted(o for o, cols in columnas.items() if not cols)
    faltan = sorted(c for cols in columnas.values() for c in cols if c not in set(finales))
    return not sin_columnas and not faltan, {"obligatorias_sin_columnas": sin_columnas, "faltan": faltan}


def validaciones(finales, origen, vars_matriz, familias, tope, prohibidas, abiertas):
    """Las seis, con su resultado calculado (error 24): {nombre: (resultado, detalle)}."""
    return {"sin_validacion": v_sin_validacion(abiertas),
            "origen_en_matriz": v_origen_en_matriz(finales, origen, vars_matriz),
            "familias_enteras": v_familias_enteras(finales, familias),
            "tope": v_tope(tope, len(finales)),
            "sin_prohibidas": v_sin_prohibidas(finales, origen, prohibidas),
            "lista_valida": v_lista_valida(finales)}


# ══ 9. La preselección de un objetivo ═══════════════════════════════════════════
def grupos_una_variante(finales, familias, decision_por_origen):
    """La tabla de grupos del §5: cada familia entera o fuera; y el grupo ambiguo si quedan dos codificaciones del
    mismo evento. No hay alternativas: cada variable tiene una sola rama en la matriz."""
    puestas = set(finales)
    grupos = [{"origen": o, "clase": "familia", "columnas": cols, "se_queda": [c for c in cols if c in puestas],
               "decidio": decision_por_origen.get(o, "regla")} for o, cols in sorted(familias.items())]
    por_columna = [o for o in EVENTOS_POR_COLUMNA if any(c in puestas for c in familias.get(o, []))]
    una_por_evento = [o for o in EVENTOS_UNA_POR_EVENTO if any(c in puestas for c in familias.get(o, []))]
    ambiguo = bool(por_columna and una_por_evento)
    if ambiguo:
        columnas = [c for o in por_columna + una_por_evento for c in familias[o]]
        grupos.append({"origen": " y ".join(por_columna) + " frente a " + " y ".join(una_por_evento),
                       "clase": "ambiguo", "columnas": columnas, "se_queda": [c for c in columnas if c in puestas],
                       "decidio": "persona: pendiente P-01; mientras, se quedan las dos codificaciones"})
    return grupos, ambiguo


def preseleccionar_objetivo(ent, objetivo, columnas_evento, prohibidas, texto_matriz, abiertas):
    """Ajusta el preprocesador con el entrenamiento, ordena las columnas con los tres métodos, vota y deja la lista de
    Ridge y la de HistGradientBoosting con sus validaciones y controles."""
    inicio = time.perf_counter()
    entrada = columnas_entrada(objetivo, columnas_evento)
    faltan = [c for c in entrada if c not in ent.columns]
    if faltan:
        raise KeyError(f"faltan columnas de entrada: {faltan}")
    pipe = construir_preprocesador(objetivo, columnas_evento)
    x = pipe.fit_transform(ent)
    y = ent[objetivo].to_numpy(dtype="float64")
    ct = pipe.named_steps["preparacion"]
    origen = origenes(ct, list(x.columns), columnas_evento)
    familias = familias_de(origen)
    vars_matriz = variables_matriz(texto_matriz, objetivo)
    obligatorias = {o: m for o, m in OBLIGATORIAS.items() if o in set(origen.values())}
    otro = [o for o in OBJETIVOS if o != objetivo][0]
    prohibidas_obj = set(prohibidas) | set(OBJETIVOS) | {c for c in ent.columns if c.startswith(f"{otro}_")}

    # §2: fuera lo que no puede entrar y las variables del momento
    fuera, avisos_constantes = fuera_de_entrada(entrada, x, origen, prohibidas_obj, obligatorias, familias)
    fuera_cols = {f["columna"] for f in fuera}
    momento = variables_del_momento(ent, entrada, columnas_evento)
    candidatas = x.drop(columns=[c for c in fuera_cols if c in x.columns])

    # §3 y §4: los tres métodos, sobre todas las columnas que pueden entrar; pliegues y reserva por fecha
    fechas = ent[COLUMNA_FECHA].reset_index(drop=True)
    pliegues = pliegues_por_fecha(fechas, PLIEGUES)
    reserva = reserva_reciente(fechas, FRACCION_RESERVA)
    r_mi = ranking_mi(candidatas, y)
    r_rfe, n_rfe = ranking_rfecv(candidatas, y, pliegues)
    r_per = ranking_per(candidatas, y, reserva)
    votos, cortes = tabla_votos(r_mi, r_rfe, r_per)
    decision = decidir_por_votos(votos, origen, obligatorias, ESCENARIO)

    # §5: una familia que no es obligatoria entra entera si la votación la deja entera; si queda partida, es ambigua
    partidas = sorted(o for o, cols in familias.items() if o not in obligatorias
                      and len({decision[c]["entra"] for c in cols if c in decision}) > 1)
    for o in partidas:
        for c in familias[o]:
            if c in decision:
                decision[c] = {"entra": True, "motivo": "familia partida por la votación: queda entera, pendiente"}
    tras_voto = [c for c in candidatas.columns if decision[c]["entra"]]

    # §6 (Ridge): pares parecidos de distinto origen entre las que pasaron 4 y 5
    numericas = [c for c in tras_voto if origen[c] not in familias and x[c].nunique() > 2]
    categoricas = sorted({origen[c] for c in tras_voto if c not in numericas})
    pares = pares_spearman(x[numericas], origen, UMBRAL_SPEARMAN)
    pares_cat = pares_cramer(ent, categoricas, columnas_evento, UMBRAL_CRAMER)
    valor_mi = r_mi.set_index("columna")["mi"]
    quitadas = resolver_pares(pares, valor_mi, lambda c: origen[c] in obligatorias)
    resolver_pares(pares_cat, {o: 0.0 for o in categoricas}, lambda o: o in obligatorias)
    # §7: el tope del método se cuenta por casos de la clase pequeña; con un objetivo continuo no hay clases
    tope = {"aplica": False, "casos_clase_pequena": None, "maximo_columnas": None,
            "motivo": "objetivo continuo: el método define el tope solo por casos de la clase pequeña"}

    finales = {"Ridge": [c for c in tras_voto if c not in quitadas],
               "HistGradientBoosting": list(candidatas.columns)}
    tope["columnas_finales"] = len(finales["Ridge"])
    grupos = {}
    ambiguos = {}
    for alg, lista in finales.items():
        grupos[alg], ambiguos[alg] = grupos_una_variante(lista, familias, {o: "regla" for o in familias})
    vals = {alg: validaciones(lista, origen, vars_matriz, familias,
                              tope if alg == "Ridge" else {"aplica": False, "maximo_columnas": None},
                              prohibidas_obj, abiertas)
            for alg, lista in finales.items()}
    controles = {"obligatorias_dentro": {alg: c_obligatorias_dentro(lista, origen, obligatorias)
                                         for alg, lista in finales.items()},
                 "pliegues_por_fecha": c_pliegues_por_fecha(fechas, pliegues),
                 "reserva_reciente": c_reserva_reciente(fechas, reserva, FRACCION_RESERVA)}
    ok_controles = {"obligatorias_dentro": all(v[0] for v in controles["obligatorias_dentro"].values()),
                    "pliegues_por_fecha": controles["pliegues_por_fecha"][0],
                    "reserva_reciente": controles["reserva_reciente"][0]}

    # La tabla de decisiones: una fila por columna de salida del preprocesador
    por_col = votos.set_index("columna")
    filas = []
    for c in x.columns:
        f = por_col.loc[c] if c in por_col.index else None
        if c in fuera_cols:
            ridge = hgb = "sale: " + next(d["motivo"] for d in fuera if d["columna"] == c)
        else:
            hgb = "entra: §2 y §5" + (", obligatoria" if origen[c] in obligatorias else "")
            if c in quitadas:
                par = next(p for p in pares if c in (p["columna_1"], p["columna_2"]) and p["sale"].split(" ")[0] == c)
                otra = par["columna_2"] if par["columna_1"] == c else par["columna_1"]
                ridge = f"sale: dice lo mismo que {otra} (Spearman {par['valor']:.3f}) y tiene menos información mutua"
            else:
                ridge = ("entra: " if decision[c]["entra"] else "sale: ") + decision[c]["motivo"]
        filas.append({"columna": c, "origen": origen[c], "obligatoria": origen[c] in obligatorias,
                      "del_momento": origen[c] in momento,
                      "mi": None if f is None else float(f["mi"]),
                      "ranking_mi": None if f is None else int(f["ranking_mi"]),
                      "ranking_rfe": None if f is None else int(f["ranking_rfe"]),
                      "permutacion": None if f is None else float(f["permutacion"]),
                      "ranking_per": None if f is None else int(f["ranking_per"]),
                      "votos": None if f is None else int(f["votos"]), "Ridge": ridge, "HistGradientBoosting": hgb})
    rankings = [{"columna": r["columna"], "origen": r["origen"], "mi": r["mi"], "ranking_mi": r["ranking_mi"],
                 "ranking_rfe": r["ranking_rfe"], "permutacion": r["permutacion"], "ranking_per": r["ranking_per"],
                 "valor_informativo": None, "votos": r["votos"]} for r in filas if r["votos"] is not None]
    cabeza = {"mi": r_mi["columna"].iloc[0], "permutacion": r_per["columna"].iloc[0]}
    return {"filas_entrenamiento": len(ent), "columnas_salida_preprocesador": x.shape[1],
            "fuera_de_entrada": fuera, "avisos_constantes": avisos_constantes,
            "alarmas_de_fuga": [],
            "variables_del_momento": {
                "origenes": sorted(momento),
                "encabezan_un_ranking": sorted({origen[c] for c in cabeza.values() if origen[c] in momento}),
                "tratamiento": ("calendario conocido de antemano que se repite cada año: no se tratan como coyuntura; "
                                "la regla del responsable del caso (reglas, apartado 7) conserva las obligatorias")},
            "cortes": cortes, "rfecv_columnas_elegidas": n_rfe, "rankings": rankings,
            "familias_partidas_por_la_votacion": partidas,
            "una_variante_por_variable": grupos["Ridge"],
            "una_variante_por_variable_hgb": grupos["HistGradientBoosting"],
            "grupo_ambiguo_de_eventos": ambiguos,
            "pares_parecidos": pares + pares_cat,
            "apariciones_en_pares": apariciones(pares + pares_cat),
            "tope": tope, "columnas_finales": finales, "tabla_decisiones": filas,
            "validaciones": {alg: {k: v[0] for k, v in vs.items()} for alg, vs in vals.items()},
            "detalle_validaciones": {alg: {k: v[1] for k, v in vs.items()} for alg, vs in vals.items()},
            "controles": ok_controles,
            "detalle_controles": {"obligatorias_dentro": {a: v[1] for a, v in controles["obligatorias_dentro"].items()},
                                  "pliegues_por_fecha": controles["pliegues_por_fecha"][1],
                                  "reserva_reciente": controles["reserva_reciente"][1]},
            "segundos": round(time.perf_counter() - inicio, 1)}


# ══ 10. Al empezar ══════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Lee preparacion.json y variables_modelo.json: si alguno no está en OK o AVISO, la matriz no está aprobada o la
    tabla tiene otra huella, no se empieza (resultado.md, «Al empezar»)."""
    paradas = []
    leidos = {}
    for rel in (PREPARACION_REL, VARIABLES_REL):
        ruta = raiz / rel
        if not ruta.exists():
            paradas.append(f"falta {rel}")
            continue
        leidos[rel] = json.loads(ruta.read_text(encoding="utf-8"))
        estado = leidos[rel].get("resultado", {}).get("estado")
        if estado not in ("OK", "AVISO"):
            paradas.append(f"{rel} está en {estado}: no se empieza")
    prep = leidos.get(PREPARACION_REL, {})
    if prep and prep.get("matriz", {}).get("aprobada_por") != "el responsable del caso":
        paradas.append("la matriz de transformaciones no consta como aprobada en preparacion.json")
    previo = leidos.get(VARIABLES_REL, {})
    huellas = {s.get("ruta"): s.get("sha256") for s in previo.get("salidas", [])}
    if previo and (not (raiz / ENTRENAMIENTO_REL).exists()
                   or huellas.get(ENTRENAMIENTO_REL) != huella(raiz / ENTRENAMIENTO_REL)):
        paradas.append(f"la huella de {ENTRENAMIENTO_REL} no es la de {VARIABLES_REL}")
    if not (raiz / MATRIZ_REL).exists():
        paradas.append(f"falta {MATRIZ_REL}")
    return paradas, prep, previo


# ══ 11. La ficha del registro ═══════════════════════════════════════════════════
def fmt(n):
    """Entero con punto de miles."""
    return f"{n:,}".replace(",", ".")


def resumir_lista(lista, origen):
    """Una lista de columnas, agrupada por su variable de origen con el número de columnas."""
    cuenta = {}
    for c in lista:
        cuenta[origen[c]] = cuenta.get(origen[c], 0) + 1
    return "; ".join(f"`{o}`" + (f" ({n} columnas)" if n > 1 else "") for o, n in cuenta.items())


def escribir_ficha(raiz, r):
    """Añade al registro la ficha de la preselección, con las listas y el escenario; si ya está con su huella, no."""
    ruta = raiz / REGISTRO_REL
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else "# Registro de transformaciones\n"
    listas = {o: r["objetivos"][o]["columnas_finales"] for o in OBJETIVOS}
    marca_huella = hashlib.sha256(json.dumps([listas, r["escenario"], r["modo"]], ensure_ascii=False,
                                             sort_keys=True).encode("utf-8")).hexdigest()[:12]
    marca = f"Regla: `preseleccion` · huella `{marca_huella}`"
    if marca in texto:
        return None
    numero = max([int(n) for n in re.findall(r"^### R-(\d{3})", texto, flags=re.M)], default=0) + 1
    fecha = r["fecha_ejecucion"]
    fecha_es = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
    lineas = []
    for o in OBJETIVOS:
        obj = r["objetivos"][o]
        origen = {f["columna"]: f["origen"] for f in obj["tabla_decisiones"]}
        ridge = obj["columnas_finales"]["Ridge"]
        hgb = obj["columnas_finales"]["HistGradientBoosting"]
        lineas.append(f"   - **{o}, Ridge:** {len(ridge)} columnas de {obj['columnas_salida_preprocesador']}: "
                      f"{resumir_lista(ridge, origen)}.")
        lineas.append(f"   - **{o}, HistGradientBoosting:** {len(hgb)} columnas, las de salida del preprocesador "
                      f"que pueden entrar.")
    pendiente = ("El grupo de los eventos (dos codificaciones del mismo evento) queda para el responsable del caso como P-01, con sus dos "
                 "opciones; mientras, las dos codificaciones siguen en las dos listas." if r["pendientes"] else
                 "Sin grupos ambiguos.")
    bloque = [f"### R-{numero:03d} · {fecha_es} · preselección de variables: listas de columnas y escenario", "",
              "1. **Tabla y columna:** las columnas de salida del preprocesador de cada objetivo "
              "(`scripts/preparacion_prevision.py`), ajustado con `hechos_modelo_entrenamiento`.", "",
              "2. **Cómo estaba:** las dos listas tenían todas las columnas de salida del preprocesador.", "",
              "3. **Problema o finalidad:** Ridge es lineal y el método pide preseleccionar siempre; a "
              "HistGradientBoosting solo se le quita lo que no puede entrar y se deja una variante por variable.", "",
              f"4. **Decisión:** reglas, apartado 7, «Preselección de variables» (el responsable del caso, 24/11/2026): modo {r['modo']}, "
              f"escenario «{r['escenario']}»; las obligatorias entran sin votar. No se usó la validación.", "",
              f"5. **Qué se hizo:** `{SCRIPT_REL}`. La lista se aplica después del preprocesador; no cambia la tabla.",
              "", "   ```python",
              "   x = construir_preprocesador(objetivo, columnas_evento).fit_transform(entrenamiento)",
              "   votos = mi_por_encima_del_salto + (rfecv.ranking_ == 1) + permutacion_por_encima_del_salto",
              "   ridge = obligatorias + votadas_con_2_o_mas - las_de_menos_mi_en_cada_par_spearman_0_5",
              "   ```", "",
              f"6. **Quién y con qué permiso:** el agente analista-preparacion-modelo deja `{SCRIPT_REL}` por la petición "
              f"de la sesión principal del {fecha_es}, con lo aprobado por el responsable del caso en las reglas, apartado 7 («Sí, apruébalo», "
              "una nota interna).", "",
              "7. **Comprobación:** las seis validaciones del método, apartado 8 y los controles de obligatorias, pliegues por "
              f"fecha y reserva reciente, en `{JSON_REL}`. {pendiente}", "",
              "8. **Cómo quedó:**", *lineas, "",
              "9. **Cómo deshacer:** usar la lista completa de salida del preprocesador "
              f"(`{PREPARACION_REL}`, `columnas_salida`).", "", marca, ""]
    cabecera = f"## Fichas de la preselección de variables (`{SCRIPT_REL}`)"
    prefijo = "" if cabecera in texto else f"\n{cabecera}\n"
    ruta.write_text(texto.rstrip("\n") + "\n" + prefijo + "\n" + "\n".join(bloque), encoding="utf-8")
    return f"R-{numero:03d}"


# ══ 12. Ejecución ═══════════════════════════════════════════════════════════════
def pendiente_eventos():
    """El grupo ambiguo de los eventos, para el responsable del caso, con sus dos opciones (método, apartado 5)."""
    return {"id": "P-01", "tabla": "columnas de salida del preprocesador",
            "columna": "event_name_1, event_name_2 y evento_<nombre>",
            "pregunta": ("Los festivos entran sin votar y con ellos dos codificaciones del mismo evento. ¿Cuál se "
                         "queda en las listas de los dos objetivos?"),
            "opciones": ["event_name_1 y event_name_2 (35 columnas): salen las evento_<nombre>; «Father's day» en "
                         "event_name_2 de la validación sale con todas sus columnas a cero",
                         "evento_<nombre> (30 columnas): salen event_name_1 y event_name_2; cada evento cuenta igual "
                         "caiga en la columna que caiga"]}


def principal(raiz, fraccion_medida=None):
    """Prepara, preselecciona los dos objetivos y devuelve el diccionario del JSON."""
    r = {"metodo": "preseleccion-variables", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [], "resultado": {}, "pendientes": []}
    paradas, prep, previo = al_empezar(raiz)
    if paradas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "; ".join(paradas),
                          "artefactos": [JSON_REL], "siguiente": "volver a ejecutar los scripts 11 y 12"}
        return r
    abiertas = []
    ent = leer_tabla(raiz, ENTRENAMIENTO_REL, abiertas)
    r["entradas"].append({"ruta": ENTRENAMIENTO_REL, "sha256": huella(raiz / ENTRENAMIENTO_REL), "filas": len(ent),
                          "columnas": ent.shape[1]})
    # Orden por fecha y serie (error 7): los pliegues y la reserva van por fecha
    ent = ent.sort_values([COLUMNA_FECHA] + CLAVE_SERIE, kind="stable").reset_index(drop=True)
    if fraccion_medida is not None:
        dias = sorted(ent[COLUMNA_FECHA].unique())
        ent = ent[ent[COLUMNA_FECHA] >= dias[-dias_de_reserva(len(dias), fraccion_medida)]].reset_index(drop=True)
    columnas_evento = list(previo["eventos"]["columnas"])
    prohibidas = [f["variable"] for f in prep.get("fuera", [])]
    texto_matriz = (raiz / MATRIZ_REL).read_text(encoding="utf-8")
    muestra = len(ent) > LIMITE_MUESTREO
    if muestra:
        raise ValueError(f"{len(ent)} filas: por encima de {LIMITE_MUESTREO} el método pide muestra, que este script "
                         "no hace")

    r["se_preselecciona"] = True
    r["por_que"] = ("compiten Ridge, lineal, y HistGradientBoosting; el responsable del caso aprobó preseleccionar en los dos objetivos: "
                    "en Ridge todos los pasos y en HistGradientBoosting solo §2 y §5 (reglas, apartado 7)")
    r["algoritmo_previsto"] = prep.get("algoritmo_previsto")
    r["pasos_por_algoritmo"] = ALGORITMOS
    r["muestra"] = {"usada": muestra, "filas": len(ent)}
    r["modo"] = MODO
    r["escenario"] = ESCENARIO
    r["escenario_fijado_en"] = "negocio/reglas-negocio.md §7, «Preselección de variables» (el responsable del caso, 24/11/2026)"
    r["obligatorias"] = [{"origen": o, "motivo": m} for o, m in OBLIGATORIAS.items()]
    r["teoria_aplicada"] = TEORIA
    r["objetivos"] = {o: preseleccionar_objetivo(ent, o, columnas_evento, prohibidas, texto_matriz, abiertas)
                      for o in OBJETIVOS}
    r["tablas_abiertas"] = abiertas
    r["entradas_despues_iguales"] = all(huella(raiz / e["ruta"]) == e["sha256"] for e in r["entradas"])
    r["parametros"] = [
        {"nombre": "semilla", "valor": SEMILLA, "origen": "preparacion-modelo; parametros.md"},
        {"nombre": "pliegues de RFECV", "valor": f"TimeSeriesSplit({PLIEGUES}) sobre los días, sin barajar",
         "origen": "parametros.md, con fecha y partición por fecha"},
        {"nombre": "métrica", "valor": METRICA, "origen": "parametros.md, objetivo continuo"},
        {"nombre": "repeticiones de la permutación", "valor": REPETICIONES, "origen": "parametros.md"},
        {"nombre": "reserva interna", "valor": f"{FRACCION_RESERVA:.0%} más reciente de los días, hacia arriba",
         "origen": "parametros.md, con fecha"},
        {"nombre": "escenario de votación", "valor": ESCENARIO, "origen": "reglas, apartado 7"},
        {"nombre": "umbral Spearman", "valor": UMBRAL_SPEARMAN, "origen": "parametros.md"},
        {"nombre": "umbral V de Cramér", "valor": UMBRAL_CRAMER, "origen": "parametros.md"},
        {"nombre": "tope en lineales", "valor": None, "origen": "parametros.md: por casos de la clase pequeña; no "
                                                               "aplica a un objetivo continuo"},
        {"nombre": "filas para muestrear", "valor": LIMITE_MUESTREO,
         "origen": "parametros.md: sin muestra por debajo; la segunda muestra no aplica"},
        {"nombre": "modelo auxiliar de RFECV", "valor": f"RandomForestRegressor({ARBOLES_RFECV} árboles, "
                                                        f"profundidad {PROFUNDIDAD_RFECV}, semilla {SEMILLA})",
         "origen": "parametros.md; sin búsqueda"},
        {"nombre": "modelo auxiliar de la permutación", "valor": f"HistGradientBoostingRegressor por defecto, "
                                                                 f"semilla {SEMILLA}",
         "origen": "parametros.md; sin búsqueda"},
        {"nombre": "paso de RFECV", "valor": 1, "origen": "valor por defecto de scikit-learn; el método no lo fija"},
        {"nombre": "corte de información mutua y permutación", "valor": "salto natural",
         "origen": "metodos.md, «El corte»: la mayor caída entre dos valores seguidos"},
        {"nombre": "máscara de discretas", "valor": "columnas con 10 valores o menos", "origen": "manual 36.5"}]

    todas = [v for o in OBJETIVOS for alg in ALGORITMOS for v in r["objetivos"][o]["validaciones"][alg].values()]
    todas += [v for o in OBJETIVOS for v in r["objetivos"][o]["controles"].values()]
    r["validaciones"] = {k: all(r["objetivos"][o]["validaciones"][alg][k] for o in OBJETIVOS for alg in ALGORITMOS)
                         for k in r["objetivos"][OBJETIVOS[0]]["validaciones"]["Ridge"]}
    ambiguo = any(any(r["objetivos"][o]["grupo_ambiguo_de_eventos"].values()) for o in OBJETIVOS)
    partidas = any(r["objetivos"][o]["familias_partidas_por_la_votacion"] for o in OBJETIVOS)
    if ambiguo:
        r["pendientes"].append(pendiente_eventos())
    if partidas:
        r["pendientes"].append({"id": "P-02", "tabla": "columnas de salida del preprocesador",
                                "columna": "familias partidas por la votación",
                                "pregunta": "Una familia que no es obligatoria quedó partida: ¿entra entera o sale?",
                                "opciones": ["entra entera", "sale entera"]})
    bien = all(todas) and r["entradas_despues_iguales"]
    estado = "ERROR" if not bien else ("AVISO" if r["pendientes"] else "OK")
    resumen = "; ".join(f"{o}: Ridge {len(r['objetivos'][o]['columnas_finales']['Ridge'])} columnas y "
                        f"HistGradientBoosting {len(r['objetivos'][o]['columnas_finales']['HistGradientBoosting'])}"
                        for o in OBJETIVOS)
    r["resultado"] = {"estado": estado, "riesgo": "bajo" if estado == "OK" else ("medio" if bien else "alto"),
                      "resumen": f"{resumen}, de {r['objetivos']['unidades']['columnas_salida_preprocesador']}; "
                                 f"{sum(todas)} de {len(todas)} validaciones y controles en verde"
                                 + ("; el grupo de los eventos queda para el responsable del caso (P-01)" if ambiguo else ""),
                      "artefactos": [JSON_REL, REGISTRO_REL],
                      "siguiente": "aprendizaje-automatico, con las listas de columnas_finales"
                                   + (", después de que el responsable del caso resuelva P-01" if ambiguo else "")}
    return r


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", type=Path, default=CASO)
    argumentos.add_argument("--medir", type=float, default=None,
                            help="fracción más reciente de los días con que se mide el tiempo; no escribe nada")
    args = argumentos.parse_args()
    raiz = args.raiz.resolve()
    if args.medir is not None:
        inicio = time.perf_counter()
        medido = principal(raiz, fraccion_medida=args.medir)
        segundos = time.perf_counter() - inicio
        print(f"MEDIDA · {medido['resultado']['estado']} · {medido.get('muestra', {}).get('filas')} filas en "
              f"{segundos:.1f} s; estimación lineal para la tabla entera: {segundos / args.medir:.0f} s")
        sys.exit(0 if medido["resultado"]["estado"] in ("OK", "AVISO") else 1)
    try:
        resultado = principal(raiz)
    except Exception:
        resultado = {"metodo": "preseleccion-variables", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                     "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "entorno": entorno(),
                     "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": traceback.format_exc()[-1500:],
                                   "artefactos": [JSON_REL], "siguiente": "corregir el fallo técnico"},
                     "pendientes": []}
    # Se valida antes de guardar (error 15): la ficha solo se escribe si el estado es OK o AVISO
    if resultado["resultado"]["estado"] in ("OK", "AVISO"):
        resultado["ficha_registro"] = escribir_ficha(raiz, resultado)
    (raiz / JSON_REL).write_text(json.dumps(a_json_limpio(resultado), ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado["resultado"]["estado"] in ("OK", "AVISO") else 1)
