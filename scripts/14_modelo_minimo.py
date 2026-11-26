"""Modelo mínimo del caso 69 y tabla de coste de la búsqueda, solo con el entrenamiento.

Aplica el método aprendizaje-automatico desde su §1 hasta la puerta de la lista de algoritmos y el nivel (§5, «El coste a
la vista antes de lanzar»). Lo que hace:
  1. el modelo mínimo (§1): HistGradientBoostingRegressor con sus valores por defecto, early_stopping=False y semilla
     42, uno por objetivo, con las columnas de HistGradientBoosting de informes/preseleccion.json sin las de
     event_name_1 y event_name_2 (el responsable del caso, 24/11/2026, reglas, apartado 7: «un día es festivo y punto», P-01);
  2. la validación cruzada por fecha (§3): TimeSeriesSplit(5) sobre los días, test_size igual al horizonte (10 días en
     unidades y 28 en dólares), sin barajar; cada pliegue entrena con lo anterior;
  3. en cada pliegue, con las mismas filas, el error y el sesgo de reglas, apartado 6 a un día (retardos reales de la tabla) y
     con la previsión recursiva desde el último día del ajuste (scripts/prevision_recursiva.py), al lado del trivial
     (DummyRegressor con la mediana, §6) y de las tres reglas sencillas (reglas, apartado 7);
  4. las variables que mandan, por permutación sobre las filas de prueba de los pliegues (§7), por variable de origen;
  5. la tabla de coste (§5): el tiempo de un ajuste de cada candidato con la tabla entera y, por nivel, los modelos y
     el tiempo estimado, a un día y con la recursiva, con la parte del espacio que prueba cada nivel.

No hace la búsqueda, no elige ganador y no abre la validación (validación 3 del método). Depende de los scripts 11 a 13
(error 2): lee la tabla de entrenamiento, cuya huella se comprueba contra informes/preparacion.json y preseleccion.json,
que tienen que estar en OK o AVISO.

Deja informes/modelo_minimo.json, con la estructura de resultado.md en lo que aplica y cada cifra con sus filas.

Uso: python -W error scripts/14_modelo_minimo.py [--raiz CARPETA] [--medir FRACCION]
Con --medir, ejecuta todo sobre la fracción más reciente de los días, imprime el tiempo y la estimación lineal para la
tabla entera y no escribe nada. Sale con 0 si el estado es OK o AVISO y con 1 si es PARADO o ERROR.
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
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.utils import check_random_state

# Los módulos del caso, que no ejecutan nada al importarse (error 1)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preparacion_prevision import columnas_entrada, construir_preprocesador  # noqa: E402
import prevision_recursiva as pr  # noqa: E402

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método aprendizaje-automatico con que se escribió este script
SCRIPT_REL = "scripts/14_modelo_minimo.py"
FECHA_DATOS = "2015-05-22"
ENTRENAMIENTO_REL = "data/processed/hechos_modelo_entrenamiento.parquet"
PRESELECCION_REL = "informes/preseleccion.json"
PREPARACION_REL = "informes/preparacion.json"
PARTICION_REL = "informes/particion.json"
JSON_REL = "informes/modelo_minimo.json"
FICHAS = {"HistGradientBoosting": "assets/fichas_de_algoritmos/histgradientboosting/01_ficha.md",
          "Ridge": "assets/fichas_de_algoritmos/regresion_lineal_y_regularizadas/01_ficha.md",
          "bosque": "assets/fichas_de_algoritmos/bosque_aleatorio/01_ficha.md"}
COLUMNA_FECHA = "date"
CLAVE_SERIE = ["store_id", "dept_id"]
COLUMNA_FUERA = "fuera_del_error"
# Lo que nunca se abre: la validación, la prueba final y un lote de producción (método, apartado 9, validación 3)
NO_SE_ABRE = re.compile(r"validacion|prueba|produccion")

# Reglas, apartado 5 y planteamientos §2: el horizonte de cada objetivo
HORIZONTE = {"unidades": 10, "dolares": 28}
OBJETIVOS = tuple(HORIZONTE)
# El responsable del caso, 24/11/2026 (reglas, apartado 7, «Preselección de variables»; P-01): fuera event_name_1 y event_name_2
FUERA_PREFIJOS = ("event_name_1_ohe_", "event_name_2_ohe_")
# Parámetros del método (parametros.md), con el valor del caso
SEMILLA = 42
PLIEGUES = 5
REPETICIONES = 10
NIVELES = {"rapido": {"candidatos": 5, "pliegues": 3}, "equilibrado": {"candidatos": 15, "pliegues": 5},
           "exhaustivo": {"candidatos": 40, "pliegues": 5}}
# Los nombres de las validaciones: la prueba y el propio script buscan que ninguna se escriba con su resultado puesto
NOMBRES_VALIDACION = ("sin_filas_de_ajuste", "semillas", "validacion_sin_abrir", "columnas_de_preseleccion",
                      "citas_existen", "reproducible", "sin_identificadores_ni_posteriores", "sin_resultados_escritos",
                      "objetivo_conocido_al_entrenar", "pliegues_por_fecha", "recursiva_completa_sin_negativas",
                      "recursiva_a_un_dia_igual", "entrada_sin_cambiar", "con_probabilidad",
                      "recalibrado_si_hace_falta", "canario_objetivo_barajado", "probabilidad_media_cerca_de_la_tasa",
                      "intervalo_por_entidad")

TEORIA = [{"apartado": "32.13", "por_que": "los pasos de todo modelo supervisado: aquí llegan hasta el 7, sin buscar"},
          {"apartado": "31.6", "por_que": "validación cruzada temporal, ventana creciente y test_size igual al horizonte"},
          {"apartado": "20.3", "por_que": "TimeSeriesSplit sobre los días ordenados; cada bloque se lee con el trivial y "
                                          "la referencia al lado"},
          {"apartado": "31.7", "por_que": "previsión recursiva: el error crece con el horizonte y se mide aparte; "
                                          "nunca por debajo de cero"},
          {"apartado": "31.9", "por_que": "WAPE con el sesgo aparte, la referencia ingenua en los mismos días y el error "
                                          "en entrenamiento al lado para ver el sobreajuste"},
          {"apartado": "32.7", "por_que": "búsqueda aleatoria: el coste lo mandan candidatos por pliegues"}]


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
    if isinstance(obj, (list, tuple)):
        return [a_json_limpio(v) for v in obj]
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
        return obj.date().isoformat() if obj == obj.normalize() else obj.isoformat()
    return obj


def entorno():
    """Versiones con que se ejecuta el script."""
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
            "pyarrow": pyarrow.__version__, "scikit-learn": sklearn.__version__, "ejecutable": sys.executable}


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def buscar_resultados_escritos(texto):
    """Las validaciones escritas con su resultado puesto (True o False) en un texto de código (error 24)."""
    nombres = "|".join(NOMBRES_VALIDACION)
    patron = rf"[\"']({nombres})[\"']\s*(?:\]\s*=|:)\s*\(?\s*(?:True|False)\b"
    return re.findall(patron, texto)


def sin_filas_de_ajuste(indices_ajuste, indices_medida):
    """Verdadero si ninguna fila medida es una fila del ajuste (validación 1)."""
    return len(np.intersect1d(np.asarray(indices_ajuste), np.asarray(indices_medida))) == 0


# ══ 3. Al empezar ═══════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Lee preseleccion.json, preparacion.json y particion.json: si alguno falta, no está en OK o AVISO o la tabla
    tiene otra huella, no se empieza (resultado.md, «Al empezar»)."""
    paradas = []
    leidos = {}
    for rel in (PRESELECCION_REL, PREPARACION_REL, PARTICION_REL):
        ruta = raiz / rel
        if not ruta.exists():
            paradas.append(f"falta {rel}")
            continue
        leidos[rel] = json.loads(ruta.read_text(encoding="utf-8"))
        estado = leidos[rel].get("resultado", {}).get("estado")
        if estado not in ("OK", "AVISO"):
            paradas.append(f"{rel} está en {estado}: no se empieza")
    ruta_tabla = raiz / ENTRENAMIENTO_REL
    actual = huella(ruta_tabla) if ruta_tabla.exists() else None
    for rel in (PRESELECCION_REL, PREPARACION_REL):
        huellas = {e.get("ruta"): e.get("sha256") for e in leidos.get(rel, {}).get("entradas", [])}
        if rel in leidos and huellas.get(ENTRENAMIENTO_REL) != actual:
            paradas.append(f"la huella de {ENTRENAMIENTO_REL} no es la de {rel}")
    return paradas, leidos


# ══ 4. Columnas y modelos ═══════════════════════════════════════════════════════
def columnas_modelo(preseleccion, objetivo, algoritmo):
    """Las columnas finales de la preselección sin las de event_name_1 y event_name_2 (reglas, apartado 7, P-01)."""
    finales = preseleccion["objetivos"][objetivo]["columnas_finales"][algoritmo]
    return [c for c in finales if not c.startswith(FUERA_PREFIJOS)]


def construir_modelo(objetivo, columnas_evento, columnas, estimador):
    """El Pipeline entero: el preprocesador del caso, sin ajustar, las columnas de la preselección y el algoritmo.

    El preprocesador se ajusta dentro de cada pliegue, con el fit del Pipeline (método, apartado 5).
    """
    seleccion = ColumnTransformer([("columnas", "passthrough", list(columnas))], remainder="drop",
                                  verbose_feature_names_out=False).set_output(transform="pandas")
    return Pipeline([("preprocesador", construir_preprocesador(objetivo, columnas_evento)),
                     ("columnas", seleccion), ("modelo", estimador)])


def modelo_minimo():
    """HistGradientBoostingRegressor por defecto, sin parada temprana (con fecha, método, apartado 5) y con semilla."""
    return HistGradientBoostingRegressor(early_stopping=False, random_state=SEMILLA)


def grupo_de(columna):
    """La variable de origen de una columna de salida del preprocesador."""
    for prefijo in ("store_id", "dept_id", "weekday", "month", "event_name_1", "event_name_2"):
        if columna.startswith(f"{prefijo}_ohe_"):
            return prefijo
    for sufijo in ("_rs", "_ss"):
        if columna.endswith(sufijo):
            return columna[: -len(sufijo)]
    return columna


def importancia_por_grupos(modelo, x, y, grupos, puntuar, repeticiones, semilla):
    """Importancia por permutación de grupos de columnas, con el reparto de azar de permutation_importance.

    Cada grupo (las columnas que salen de una misma variable) se baraja junto, que es lo mismo que barajar la variable
    de origen antes del preprocesador. Con grupos de una columna da lo mismo que scikit-learn 1.9 (la prueba lo
    compara, error 30). La importancia es la puntuación sin barajar menos la puntuación barajada.
    """
    base = puntuar(y, modelo.predict(x))
    semilla_grupo = check_random_state(semilla).randint(np.iinfo(np.int32).max + 1)
    salida = {}
    for nombre, columnas in grupos.items():
        azar = check_random_state(semilla_grupo)
        barajada = x.copy()
        indices = np.arange(len(x))
        puntos = []
        for _ in range(repeticiones):
            azar.shuffle(indices)
            barajada[columnas] = barajada[columnas].iloc[indices].to_numpy()
            puntos.append(puntuar(y, modelo.predict(barajada)))
        caidas = base - np.array(puntos)
        salida[nombre] = {"media": float(caidas.mean()), "desviacion": float(caidas.std())}
    return salida


# ══ 5. Un pliegue ═══════════════════════════════════════════════════════════════
def previsto_medible(valores, objetivo):
    """Acota en cero y, en unidades, redondea al entero (método, apartado 8; reglas, apartado 6)."""
    v = np.clip(np.asarray(valores, dtype="float64"), 0.0, None)
    return pr.redondear_unidades(v) if objetivo == "unidades" else v


def medir(real, previsto, filas):
    """Error y sesgo de reglas, apartado 6 con las filas sobre las que se calcularon."""
    error, sesgo = pr.error_y_sesgo(real, previsto)
    return {"error": error, "sesgo": sesgo, "filas": filas}


def medir_pliegue(tabla, objetivo, columnas, columnas_evento, pliegue, numero):
    """Ajusta el modelo mínimo con los días del ajuste y lo mide en los de prueba, a un día y en recursivo, con el
    trivial y las tres reglas en las mismas filas. Devuelve las cifras, el modelo y lo que piden las validaciones."""
    h = HORIZONTE[objetivo]
    comprobacion = pr.comprobar_pliegue(pliegue["dias_ajuste"], pliegue["dias_prueba"], h)
    en_ajuste = tabla[COLUMNA_FECHA].isin(pliegue["dias_ajuste"]).to_numpy()
    en_prueba = tabla[COLUMNA_FECHA].isin(pliegue["dias_prueba"]).to_numpy()
    ajuste, prueba = tabla[en_ajuste], tabla[en_prueba]
    entrada = columnas_entrada(objetivo, columnas_evento)

    # El modelo mínimo, ajustado solo con el pasado del pliegue
    inicio = time.perf_counter()
    modelo = construir_modelo(objetivo, columnas_evento, columnas, modelo_minimo()).fit(ajuste[entrada],
                                                                                         ajuste[objetivo])
    segundos_ajuste = time.perf_counter() - inicio

    # A un día, con los retardos reales de la tabla
    un_dia = prueba[CLAVE_SERIE + [COLUMNA_FECHA, objetivo, COLUMNA_FUERA]].assign(
        a_un_dia=np.clip(modelo.predict(prueba[entrada]), 0.0, None))
    # Recursiva desde el último día del ajuste: la historia es la del ajuste y el futuro, lo conocido de antemano
    inicio = time.perf_counter()
    recursiva = pr.prever_recursivo(modelo, ajuste[CLAVE_SERIE + [COLUMNA_FECHA, objetivo]], prueba, objetivo, h,
                                    origen=pliegue["origen"])
    segundos_recursion = time.perf_counter() - inicio
    reglas = pr.reglas_sencillas(ajuste, objetivo, pliegue["origen"], h)
    trivial = DummyRegressor(strategy="median").fit(np.zeros((len(ajuste), 1)), ajuste[objetivo])
    junto = (un_dia.merge(recursiva.rename(columns={"prevision": "recursiva"}), on=CLAVE_SERIE + [COLUMNA_FECHA],
                          how="left", validate="one_to_one")
             .merge(reglas.drop(columns="h"), on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one"))
    junto["trivial_mediana"] = trivial.predict(np.zeros((len(junto), 1)))

    # Las cifras, sin los días fuera del error (reglas, apartado 6), con la previsión acotada y en unidades redondeada
    medidas = junto[~junto[COLUMNA_FUERA].to_numpy()]
    real = medidas[objetivo].to_numpy(dtype="float64")
    filas = f"fuera de pliegue: {len(medidas)} filas de prueba del pliegue {numero}"
    referencias = {nombre: medir(real, previsto_medible(medidas[nombre], objetivo), filas)
                   for nombre in ("trivial_mediana",) + pr.REGLAS}
    mejor = min(pr.REGLAS, key=lambda r: referencias[r]["error"])
    recursivo = medir(real, previsto_medible(medidas["recursiva"], objetivo), filas + ", recursiva desde el origen")
    aj_medido = ajuste[~ajuste[COLUMNA_FUERA].to_numpy()]
    entrenamiento = medir(aj_medido[objetivo].to_numpy(dtype="float64"),
                          previsto_medible(modelo.predict(aj_medido[entrada]), objetivo), "entrenamiento")
    h1 = junto[junto[COLUMNA_FECHA] == pliegue["origen"] + pd.Timedelta(1, "D")]
    diferencia_h1 = float(np.abs(h1["recursiva"] - h1["a_un_dia"]).max())
    cifras = {
        "pliegue": numero, "origen": pliegue["origen"],
        "dias_prueba": {"desde": comprobacion["prueba_desde"], "hasta": comprobacion["prueba_hasta"],
                        "dias": comprobacion["dias_prueba"]},
        "filas_ajuste": int(en_ajuste.sum()), "filas_prueba": int(en_prueba.sum()), "filas_medidas": len(medidas),
        "filas_fuera_del_error": int(junto[COLUMNA_FUERA].sum()),
        "a_un_dia": {"modelo": medir(real, previsto_medible(medidas["a_un_dia"], objetivo),
                                     filas + ", a un día con los retardos reales"),
                     "entrenamiento": entrenamiento},
        "recursiva": {"modelo": recursivo},
        "referencias": referencias,
        "regla_que_menos_falla": mejor,
        "ventaja_recursiva_frente_a_esa_regla": referencias[mejor]["error"] - recursivo["error"],
        "recursiva_gana_a_esa_regla": bool(recursivo["error"] < referencias[mejor]["error"]),
        "recursiva_a_un_dia_igual": bool(diferencia_h1 <= 1e-6 * (1 + float(h1["a_un_dia"].abs().max()))),
        "diferencia_maxima_dia_1": diferencia_h1,
        "segundos": {"ajuste": segundos_ajuste, "recursion": segundos_recursion}}
    control = {"comprobacion": comprobacion,
               "sin_filas_de_ajuste": sin_filas_de_ajuste(np.flatnonzero(en_ajuste), np.flatnonzero(en_prueba)),
               "filas_ajuste_sin_conocer": int((ajuste[COLUMNA_FECHA] >= pliegue["dias_prueba"].min()).sum()),
               "recursiva_completa": bool(junto["recursiva"].notna().all() and len(recursiva) == len(prueba)),
               "recursiva_sin_negativas": bool((recursiva["prevision"] >= 0).all()),
               "un_dia_previsto": junto["a_un_dia"].to_numpy()}
    # Las filas de prueba que se miden, con sus columnas de entrada, para la permutación
    prueba_medida = prueba[~prueba[COLUMNA_FUERA].to_numpy()]
    return cifras, control, modelo, prueba_medida, entrada


def importancias_del_pliegue(modelo, medidas, entrada, objetivo, columnas):
    """Permutación por variable de origen sobre las filas de prueba del pliegue, a un día (método, apartado 7)."""
    x = modelo[:1].transform(medidas[entrada])
    resto = modelo[1:]
    grupos = {}
    for c in columnas:
        grupos.setdefault(grupo_de(c), []).append(c)
    real = medidas[objetivo].to_numpy(dtype="float64")

    def puntuar(r, previsto):
        """Menos el error del caso: mayor es mejor."""
        return -pr.error_y_sesgo(r, previsto_medible(previsto, objetivo))[0]

    return importancia_por_grupos(resto, x, real, grupos, puntuar, REPETICIONES, SEMILLA)


# ══ 6. Un objetivo ══════════════════════════════════════════════════════════════
def resumir(pliegues, camino):
    """Media y desviación entre pliegues de una cifra, con las filas de los pliegues."""
    valores = {"error": [], "sesgo": []}
    for p in pliegues:
        nodo = p
        for paso in camino:
            nodo = nodo[paso]
        for k in valores:
            valores[k].append(nodo[k])
    etiqueta = "entrenamiento" if camino[-1] == "entrenamiento" else "fuera de pliegue: los 5 pliegues"
    return {"error": float(np.mean(valores["error"])), "error_desviacion": float(np.std(valores["error"])),
            "sesgo": float(np.mean(valores["sesgo"])), "sesgo_desviacion": float(np.std(valores["sesgo"])),
            "filas": etiqueta}


def modelo_minimo_objetivo(tabla, objetivo, preseleccion, columnas_evento):
    """El modelo mínimo de un objetivo en sus cinco pliegues, con sus referencias y las importancias."""
    h = HORIZONTE[objetivo]
    columnas = columnas_modelo(preseleccion, objetivo, "HistGradientBoosting")
    pliegues = pr.pliegues_por_dia(tabla[COLUMNA_FECHA], PLIEGUES, h)
    cifras, controles, importancias = [], [], []
    for numero, pliegue in enumerate(pliegues, start=1):
        c, control, modelo, medidas, entrada = medir_pliegue(tabla, objetivo, columnas, columnas_evento, pliegue,
                                                             numero)
        cifras.append(c)
        controles.append(control)
        importancias.append(importancias_del_pliegue(modelo, medidas, entrada, objetivo, columnas))
    # Importancias: media de los pliegues y desviación entre pliegues, de mayor a menor
    valores = []
    for grupo in importancias[0]:
        medias = [imp[grupo]["media"] for imp in importancias]
        valores.append({"columna": grupo, "importancia": float(np.mean(medias)),
                        "desviacion": float(np.std(medias)), "por_pliegue": medias})
    valores.sort(key=lambda v: -v["importancia"])
    positivas = sum(max(v["importancia"], 0.0) for v in valores)
    resumen = {nombre: resumir(cifras, camino) for nombre, camino in
               (("a_un_dia", ("a_un_dia", "modelo")), ("recursiva", ("recursiva", "modelo")),
                ("entrenamiento", ("a_un_dia", "entrenamiento")))}
    for regla in ("trivial_mediana",) + pr.REGLAS:
        resumen[regla] = resumir(cifras, ("referencias", regla))
    return {
        "horizonte": h, "receta": {"algoritmo": "HistGradientBoostingRegressor",
                                   "hiperparametros": modelo_minimo().get_params(), "semilla": SEMILLA,
                                   "columnas": columnas, "n_columnas": len(columnas),
                                   "preprocesador": "scripts/preparacion_prevision.py, ajustado dentro de cada pliegue"},
        "pliegues": cifras, "resumen": resumen,
        "pliegues_que_gana_la_recursiva": int(sum(c["recursiva_gana_a_esa_regla"] for c in cifras)),
        "importancias": {"metodo": "permutacion por variable de origen", "repeticiones": REPETICIONES,
                         "puntuacion": "menos el error de reglas, apartado 6, con la previsión acotada"
                                       + (" y redondeada" if objetivo == "unidades" else ""),
                         "filas": "fuera de pliegue: las filas de prueba de los 5 pliegues, a un día",
                         "valores": valores,
                         "peso_de_las_dos_primeras": (sum(max(v["importancia"], 0.0) for v in valores[:2]) / positivas
                                                      if positivas > 0 else None)},
    }, controles, pliegues


# ══ 7. La tabla de coste ════════════════════════════════════════════════════════
def espacio(filas):
    """Las rejillas de algoritmos.md (cantidad), con el montaje del boosting para fecha: early_stopping=False y
    max_iter en 100, 200 y 500; la hoja, max(20, 1 % de las filas)."""
    hoja = max(20, int(0.01 * filas))
    return hoja, {
        "HistGradientBoosting": {"learning_rate": [0.05, 0.1], "max_depth": [3, 5, None], "max_iter": [100, 200, 500],
                                 "min_samples_leaf": [hoja // 4, hoja], "l2_regularization": [0, 1]},
        "bosque": {"max_depth": [5, 10, 15], "n_estimators": [100, 300, 500],
                   "min_samples_leaf": [hoja // 4, hoja], "max_features": [0.3, 0.5, 1.0]},
        "Ridge": {"alpha": list(filas * np.logspace(-3, 3, 13))}}


def candidato_central(algoritmo, hoja, filas):
    """El candidato del centro de cada rejilla, con el que se mide el tiempo de un ajuste."""
    if algoritmo == "HistGradientBoosting":
        return HistGradientBoostingRegressor(early_stopping=False, learning_rate=0.1, max_depth=5, max_iter=200,
                                             min_samples_leaf=hoja, l2_regularization=0, random_state=SEMILLA)
    if algoritmo == "bosque":
        return RandomForestRegressor(n_estimators=300, max_depth=10, min_samples_leaf=hoja, max_features=0.5,
                                     n_jobs=-1, random_state=SEMILLA)
    return Ridge(alpha=float(filas), random_state=SEMILLA)


def tabla_de_coste(tabla, preseleccion, columnas_evento, pliegues_por_objetivo):
    """El tiempo de un ajuste del candidato central de cada algoritmo con la tabla entera y de su previsión recursiva
    desde el origen del último pliegue (solo tiempo), y por nivel los modelos y el tiempo estimado."""
    filas = len(tabla)
    hoja, rejillas = espacio(filas)
    medidos = []
    for objetivo in OBJETIVOS:
        entrada = columnas_entrada(objetivo, columnas_evento)
        ultimo = pliegues_por_objetivo[objetivo][-1]
        prueba = tabla[tabla[COLUMNA_FECHA].isin(ultimo["dias_prueba"]).to_numpy()]
        historia = tabla.loc[(tabla[COLUMNA_FECHA] <= ultimo["origen"]).to_numpy(),
                             CLAVE_SERIE + [COLUMNA_FECHA, objetivo]]
        for algoritmo in ("HistGradientBoosting", "bosque", "Ridge"):
            lista = "Ridge" if algoritmo == "Ridge" else "HistGradientBoosting"
            columnas = columnas_modelo(preseleccion, objetivo, lista)
            modelo = construir_modelo(objetivo, columnas_evento, columnas, candidato_central(algoritmo, hoja, filas))
            inicio = time.perf_counter()
            modelo.fit(tabla[entrada], tabla[objetivo])
            segundos_ajuste = time.perf_counter() - inicio
            inicio = time.perf_counter()
            pr.prever_recursivo(modelo, historia, prueba, objetivo, HORIZONTE[objetivo], origen=ultimo["origen"])
            segundos_recursion = time.perf_counter() - inicio
            medidos.append({"objetivo": objetivo, "algoritmo": algoritmo, "columnas": lista,
                            "n_columnas": len(columnas), "candidato": modelo[-1].get_params(),
                            "filas_ajuste": filas, "segundos_ajuste": segundos_ajuste,
                            "segundos_recursion": segundos_recursion, "horizonte": HORIZONTE[objetivo]})
    combinaciones = {a: int(np.prod([len(v) for v in r.values()])) for a, r in rejillas.items()}
    niveles = []
    for nivel, conf in NIVELES.items():
        por_algoritmo = []
        for algoritmo, total in combinaciones.items():
            candidatos = min(conf["candidatos"], total)
            for m in (x for x in medidos if x["algoritmo"] == algoritmo):
                ajustes = candidatos * conf["pliegues"]
                por_algoritmo.append({
                    "algoritmo": algoritmo, "objetivo": m["objetivo"], "combinaciones": total,
                    "candidatos": candidatos, "parte_del_espacio": candidatos / total,
                    "tipo": "rejilla" if candidatos == total else "aleatoria", "pliegues": conf["pliegues"],
                    "modelos": ajustes + 1,
                    "segundos_a_un_dia": (ajustes + 1) * m["segundos_ajuste"],
                    "segundos_recursiva": (ajustes + 1) * m["segundos_ajuste"] + ajustes * m["segundos_recursion"]})
        totales = {}
        for nombre, algoritmos in (("los_tres", ("HistGradientBoosting", "bosque", "Ridge")),
                                   ("sin_bosque", ("HistGradientBoosting", "Ridge"))):
            sel = [p for p in por_algoritmo if p["algoritmo"] in algoritmos]
            totales[nombre] = {"modelos": sum(p["modelos"] for p in sel),
                               "minutos_a_un_dia": sum(p["segundos_a_un_dia"] for p in sel) / 60,
                               "minutos_recursiva": sum(p["segundos_recursiva"] for p in sel) / 60}
        niveles.append({"nivel": nivel, **conf, "por_algoritmo": por_algoritmo, "totales": totales})
    return {"hoja": hoja, "filas": filas, "rejillas": rejillas, "combinaciones": combinaciones,
            "algoritmos": medidos, "niveles": niveles,
            "como_se_estima": "modelos = candidatos × pliegues + 1 reajuste, por algoritmo y objetivo; el tiempo, "
                              "modelos por el ajuste medido del candidato central, y en la recursiva además una "
                              "previsión recursiva por cada ajuste de pliegue",
            "limites": ["el ajuste del candidato central no es la media de la rejilla: un candidato con max_iter o "
                        "n_estimators de 500 tarda más y uno de 100 menos",
                        "cada pliegue entrena con menos filas que la tabla entera: la estimación queda por arriba",
                        "en el exhaustivo, repetir TimeSeriesSplit da los mismos pliegues: se cuentan 5",
                        "la previsión recursiva del tiempo usa un modelo ajustado con la tabla entera: solo mide "
                        "tiempo, ninguna cifra de error sale de ahí",
                        "Ridge con 13 combinaciones va en rejilla entera cuando el nivel pide más candidatos que "
                        "combinaciones: RandomizedSearchCV avisa y con -W error se para"]}


# ══ 8. Principal ════════════════════════════════════════════════════════════════
def principal(raiz, fraccion_medida=None):
    """Prepara, mide el modelo mínimo de los dos objetivos y el coste, y devuelve el diccionario del JSON."""
    r = {"metodo": "aprendizaje-automatico", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [], "resultado": {}, "pendientes": []}
    paradas, leidos = al_empezar(raiz)
    if paradas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "; ".join(paradas),
                          "artefactos": [JSON_REL], "siguiente": "volver a ejecutar los scripts 11 a 13"}
        return r
    preseleccion, preparacion = leidos[PRESELECCION_REL], leidos[PREPARACION_REL]
    abiertas = [ENTRENAMIENTO_REL]
    huella_antes = huella(raiz / ENTRENAMIENTO_REL)
    tabla = pd.read_parquet(raiz / ENTRENAMIENTO_REL)
    r["entradas"].append({"ruta": ENTRENAMIENTO_REL, "sha256": huella_antes, "filas": len(tabla),
                          "columnas": tabla.shape[1]})
    # Orden por fecha y serie (error 7): el resultado no depende del orden en que llegan las filas
    tabla = tabla.sort_values([COLUMNA_FECHA] + CLAVE_SERIE, kind="stable").reset_index(drop=True)
    if fraccion_medida is not None:
        dias = sorted(tabla[COLUMNA_FECHA].unique())
        desde = dias[-max(1, math.ceil(len(dias) * fraccion_medida))]
        tabla = tabla[tabla[COLUMNA_FECHA] >= desde].reset_index(drop=True)
    columnas_evento = [c for c in tabla.columns if c.startswith("evento_")]
    por_serie = tabla.groupby(CLAVE_SERIE)[COLUMNA_FECHA].agg(["size", "min", "max"])
    r["tabla"] = {"filas": len(tabla), "series": len(por_serie), "dias_por_serie_min": int(por_serie["size"].min()),
                  "dias_por_serie_max": int(por_serie["size"].max()), "desde": tabla[COLUMNA_FECHA].min(),
                  "hasta": tabla[COLUMNA_FECHA].max()}

    r["rama"] = "prevision"
    r["hace_falta_modelar"] = {
        "respuesta": True,
        "por_que": "las preguntas 1 y 2 de la ficha piden cuántas unidades y dólares venderá cada departamento en cada "
                   "tienda cada día y si la previsión se equivoca menos que las tres reglas: es una previsión, no una "
                   "pregunta descriptiva, y el exploratorio no la contesta. La ficha da las dos por contestables con "
                   "la construcción (prueba rápida con un modelo para las 70 series), y los planteamientos §1 "
                   "y §2 fijan el modelo y su referencia de suavizado exponencial"}
    r["puerta_contestable"] = {"aplica": False, "por_que": "la previsión informa y decide una persona; no decide sobre "
                                                           "personas (ficha, «Las seis comprobaciones»)"}
    r["aprobado_antes"] = {
        "medida_principal": "error de la previsión: unidades (o dólares) que falla por cada 100 vendidas, de las 70 "
                            "series juntas y todos los días del periodo, sin el 25 de diciembre, con el sesgo al lado",
        "por_que": "reglas, apartado 6: el error de las 70 juntas decide; el sesgo, porque el error puede bajar mientras la "
                   "previsión se queda corta",
        "referencias": ["las tres reglas sencillas (reglas, apartado 7)", "el trivial, DummyRegressor con la mediana (método, apartado 6)",
                        "el suavizado exponencial (planteamientos §1), que se mide con la validación"],
        "se_da_por_bueno": "reglas, apartado 7, «Qué cuenta como mejora»: menos error que la regla que menos falla en al menos "
                           "el 75 % de los orígenes y el intervalo del 95 % de la ventaja por encima de cero; se decide "
                           "en la validación",
        "minimo_de_casos": None,
        "fuente": "config/negocio/reglas-negocio.md §6 y §7; config/metodo/04_planteamientos.md"}
    r["validacion_cruzada"] = {
        "tipo": "TimeSeriesSplit sobre los días, sin barajar, ventana creciente", "pliegues": PLIEGUES,
        "semilla": SEMILLA, "grupo": None, "test_size": dict(HORIZONTE), "gap": None,
        "gap_por_que": "la venta de la víspera se conoce al prever (reglas, apartado 5)", "objetivo_sin_conocer": []}
    r["desequilibrio"] = {"regla": None, "por_que": "no aplica: los dos objetivos son cantidades"}
    r["busqueda"] = None
    r["teoria_aplicada"] = TEORIA

    # El modelo mínimo de cada objetivo
    inicio = time.perf_counter()
    r["modelo_minimo"], controles, pliegues = {}, {}, {}
    for objetivo in OBJETIVOS:
        r["modelo_minimo"][objetivo], controles[objetivo], pliegues[objetivo] = modelo_minimo_objetivo(
            tabla, objetivo, preseleccion, columnas_evento)
        for c in controles[objetivo]:
            r["validacion_cruzada"]["objetivo_sin_conocer"].append(
                {"objetivo": objetivo, "entrenamiento": f"pliegue que mide desde {c['comprobacion']['prueba_desde']:%Y-%m-%d}",
                 "conocido_desde": c["comprobacion"]["prueba_desde"], "filas_quitadas": c["filas_ajuste_sin_conocer"],
                 "eventos_quitados": None})
    segundos_minimo = time.perf_counter() - inicio

    # Dos ejecuciones seguidas dan la misma cifra (validación 8): se repite el primer pliegue de unidades
    primero = pliegues["unidades"][0]
    columnas_u = columnas_modelo(preseleccion, "unidades", "HistGradientBoosting")
    _, otra, _, _, _ = medir_pliegue(tabla, "unidades", columnas_u, columnas_evento, primero, 1)
    reproducible = bool(np.array_equal(otra["un_dia_previsto"], controles["unidades"][0]["un_dia_previsto"]))

    # La tabla de coste
    inicio = time.perf_counter()
    r["coste"] = tabla_de_coste(tabla, preseleccion, columnas_evento, pliegues)
    r["coste"]["segundos_modelo_minimo_dos_objetivos"] = segundos_minimo
    segundos_coste = time.perf_counter() - inicio
    r["coste"]["segundos_tabla_de_coste"] = segundos_coste

    # Las validaciones del §9 que aplican, calculadas con lo ejecutado
    todos = [c for o in OBJETIVOS for c in controles[o]]
    fuera = {f["variable"] for f in preparacion.get("fuera", [])}
    entradas = {c for o in OBJETIVOS for c in columnas_entrada(o, columnas_evento)}
    citas = [PRESELECCION_REL, PREPARACION_REL, PARTICION_REL, FICHAS["HistGradientBoosting"], FICHAS["Ridge"]]
    huella_despues = huella(raiz / ENTRENAMIENTO_REL)
    finales = {o: preseleccion["objetivos"][o]["columnas_finales"]["HistGradientBoosting"] for o in OBJETIVOS}
    v = {}
    v["sin_filas_de_ajuste"] = all(c["sin_filas_de_ajuste"] for c in todos)
    v["semillas"] = all(r["modelo_minimo"][o]["receta"]["hiperparametros"]["random_state"] == SEMILLA
                        for o in OBJETIVOS) and all(m["candidato"].get("random_state", SEMILLA) == SEMILLA
                                                    for m in r["coste"]["algoritmos"])
    v["validacion_sin_abrir"] = not any(NO_SE_ABRE.search(Path(a).stem) for a in abiertas)
    v["columnas_de_preseleccion"] = all(
        r["modelo_minimo"][o]["receta"]["columnas"] == [c for c in finales[o] if not c.startswith(FUERA_PREFIJOS)]
        and len(r["modelo_minimo"][o]["receta"]["columnas"]) > 0 for o in OBJETIVOS)
    v["citas_existen"] = all((raiz / c).exists() for c in citas)
    v["reproducible"] = reproducible
    v["sin_identificadores_ni_posteriores"] = not (entradas & fuera) and not any(
        grupo_de(c) in fuera for o in OBJETIVOS for c in r["modelo_minimo"][o]["receta"]["columnas"])
    v["sin_resultados_escritos"] = buscar_resultados_escritos(Path(__file__).read_text(encoding="utf-8")) == []
    v["objetivo_conocido_al_entrenar"] = all(c["filas_ajuste_sin_conocer"] == 0 for c in todos)
    v["pliegues_por_fecha"] = all(c["comprobacion"]["bien"] for c in todos)
    v["recursiva_completa_sin_negativas"] = all(c["recursiva_completa"] and c["recursiva_sin_negativas"] for c in todos)
    v["recursiva_a_un_dia_igual"] = all(p["recursiva_a_un_dia_igual"] for o in OBJETIVOS
                                        for p in r["modelo_minimo"][o]["pliegues"])
    v["entrada_sin_cambiar"] = huella_despues == huella_antes
    for nombre in ("con_probabilidad", "recalibrado_si_hace_falta", "canario_objetivo_barajado",
                   "probabilidad_media_cerca_de_la_tasa", "intervalo_por_entidad"):
        v[nombre] = None
    r["validaciones"] = v
    r["validaciones_nulas"] = {
        "con_probabilidad": "no aplica: objetivo de cantidad", "recalibrado_si_hace_falta": "no aplica: sin equilibrar",
        "canario_objetivo_barajado": "va con la búsqueda y el ganador", "probabilidad_media_cerca_de_la_tasa":
            "no aplica: objetivo de cantidad", "intervalo_por_entidad": "va con la validación (planteamientos §2, 3)"}
    r["detalle_pliegues"] = {o: [c["comprobacion"] for c in controles[o]] for o in OBJETIVOS}
    r["tablas_abiertas"] = abiertas
    r["huella_entrada_despues"] = huella_despues
    r["fichas"] = {a: {"ruta": ruta, "existe": (raiz / ruta).exists()} for a, ruta in FICHAS.items()}
    r["parametros"] = [
        {"nombre": "semilla", "valor": SEMILLA, "origen": "preparacion-modelo; parametros.md"},
        {"nombre": "pliegues", "valor": f"TimeSeriesSplit({PLIEGUES}) sobre los días, test_size 10 y 28",
         "origen": "parametros.md; método, apartado 3, previsión"},
        {"nombre": "repeticiones de la permutación", "valor": REPETICIONES, "origen": "parametros.md"},
        {"nombre": "parada temprana", "valor": False, "origen": "método, apartado 5: con fecha, early_stopping=False"},
        {"nombre": "hoja mínima de la rejilla", "valor": r["coste"]["hoja"],
         "origen": "algoritmos.md: max(20, 1 % de las filas de entrenamiento)"},
        {"nombre": "niveles de la búsqueda", "valor": NIVELES, "origen": "algoritmos.md, «El coste»"},
        {"nombre": "días fuera del error", "valor": "fuera de las cifras; dentro del ajuste",
         "origen": "reglas, apartado 6 para las cifras; el ajuste con la tabla entera, como pide la petición; para la búsqueda no está fijado (matriz, «Límites y preguntas abiertas»)"}]

    bien = all(x for x in v.values() if x is not None)
    r["pendientes"] = [{"id": "P-01", "tabla": "modelado", "columna": "lista de algoritmos y nivel de búsqueda",
                        "pregunta": "¿Qué algoritmos entran en la búsqueda y con qué nivel? Puerta del responsable del caso (método, apartado 5)",
                        "opciones": ["la propuesta de informes/modelado_propuesta.md", "otra lista o nivel"]}]
    estado = "AVISO" if bien else "ERROR"
    u, d = r["modelo_minimo"]["unidades"]["resumen"], r["modelo_minimo"]["dolares"]["resumen"]
    r["resultado"] = {
        "estado": estado, "riesgo": "medio" if bien else "alto",
        "resumen": (f"modelo mínimo en 5 pliegues: unidades {u['a_un_dia']['error']:.1f} a un día y "
                    f"{u['recursiva']['error']:.1f} en recursiva; dólares {d['a_un_dia']['error']:.1f} y "
                    f"{d['recursiva']['error']:.1f}; {sum(bool(x) for x in v.values() if x is not None)} de "
                    f"{sum(x is not None for x in v.values())} validaciones en verde; la búsqueda espera al responsable del caso"),
        "artefactos": [JSON_REL],
        "siguiente": "El responsable del caso aprueba la lista de algoritmos y el nivel (informes/modelado_propuesta.md); después, la "
                     "búsqueda"}
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
        print(f"MEDIDA · {medido['resultado']['estado']} · {medido.get('tabla', {}).get('filas')} filas en "
              f"{segundos:.1f} s; estimación lineal para la tabla entera: {segundos / args.medir:.0f} s")
        sys.exit(0 if medido["resultado"]["estado"] in ("OK", "AVISO") else 1)
    try:
        resultado = principal(raiz)
    except Exception:
        resultado = {"metodo": "aprendizaje-automatico", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                     "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "entorno": entorno(),
                     "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": traceback.format_exc()[-1500:],
                                   "artefactos": [JSON_REL], "siguiente": "corregir el fallo técnico"},
                     "pendientes": []}
    (raiz / JSON_REL).write_text(json.dumps(a_json_limpio(resultado), ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado["resultado"]["estado"] in ("OK", "AVISO") else 1)
