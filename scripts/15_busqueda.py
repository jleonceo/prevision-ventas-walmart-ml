"""Búsqueda del modelo del caso 69: HistGradientBoosting y Ridge en los dos objetivos, medidos en recursivo.

Aplica el método aprendizaje-automatico, apartado 5 a §7 con lo que el responsable del caso aprobó el 24/11/2026 (informes/modelado_propuesta.md;
config/metodo/04_planteamientos.md §2, «Algoritmos y búsqueda»). Lo que hace:
  1. una búsqueda por algoritmo y objetivo (§5): HistGradientBoostingRegressor con 15 candidatos al azar de su rejilla
     (ParameterSampler con semilla 42, early_stopping=False) y Ridge con su rejilla entera (ParameterGrid); las
     rejillas, las de informes/modelo_minimo.json («coste»); las columnas, las columnas_finales de
     informes/preseleccion.json sin las de event_name_1 y event_name_2; el preprocesador de
     scripts/preparacion_prevision.py, ajustado dentro de cada corte;
  2. los mismos 5 cortes por fecha que el modelo mínimo (prevision_recursiva.pliegues_por_dia), comprobados contra los
     orígenes de informes/modelo_minimo.json;
  3. cada candidato se ajusta con los días del corte, 25 de diciembre incluido, y se mide con la previsión recursiva
     desde su origen (prevision_recursiva.prever_recursivo), con el error y el sesgo de reglas, apartado 6 sin los 25 de
     diciembre; al lado, su medida en las filas del ajuste, rotulada como entrenamiento;
  4. el borde y el rango plano (§5): si el mejor valor de un hiperparámetro cae en el borde de su rejilla, o la medida no
     cambia a lo largo de su rango, la rejilla se amplía por ese lado una vez y se repite solo ese algoritmo;
  5. el ranking (§6), con el trivial y las tres reglas en los mismos cortes, y la comparación pliegue a pliegue;
  6. el ganador de cada objetivo (§7): reajustado con todo el entrenamiento, la importancia por permutación sobre las
     filas fuera de pliegue por variable de origen, la distancia entre entrenamiento y validación cruzada, la regla
     simple con sus dos variables de más peso y el canario de las fugas (validación 11).

No abre la validación (validación 3) y no mide el suavizado exponencial. Para en la puerta del responsable del caso: el ganador se aprueba
antes de abrir la validación (resultado.md: con aprobado_por vacío, el estado es PARADO).

Depende de los scripts 12 a 14 (error 2): lee la tabla de entrenamiento, cuya huella se comprueba contra
informes/preseleccion.json e informes/modelo_minimo.json, que tienen que estar en OK o AVISO.

Deja informes/busqueda.json, informes/modelado_busqueda.csv e informes/busqueda_propuesta.md, este generado del JSON.

Uso: python -W error scripts/15_busqueda.py [--raiz CARPETA]
     python -W error scripts/15_busqueda.py --medir FRACCION [--candidatos N] [--objetivos unidades dolares]
Con --medir ejecuta todo sobre la fracción más reciente de los días, con N candidatos por algoritmo y sin ampliar
rejillas; imprime el tiempo y la estimación para la búsqueda entera y no escribe nada. Sale con 0 si el estado es OK,
AVISO o PARADO en la puerta del responsable del caso, y con 1 si para por otro motivo o hay ERROR.
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import ParameterGrid, ParameterSampler
from sklearn.pipeline import Pipeline
from sklearn.utils import check_random_state

# Los módulos del caso, que no ejecutan nada al importarse (error 1)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preparacion_prevision import columnas_entrada, construir_preprocesador  # noqa: E402
import prevision_recursiva as pr  # noqa: E402

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método aprendizaje-automatico con que se escribió este script
SCRIPT_REL = "scripts/15_busqueda.py"
FECHA_DATOS = "2015-05-22"
ENTRENAMIENTO_REL = "data/processed/hechos_modelo_entrenamiento.parquet"
PRESELECCION_REL = "informes/preseleccion.json"
PREPARACION_REL = "informes/preparacion.json"
MODELO_MINIMO_REL = "informes/modelo_minimo.json"
JSON_REL = "informes/busqueda.json"
CSV_REL = "informes/modelado_busqueda.csv"
MD_REL = "informes/busqueda_propuesta.md"
FICHAS = {"HistGradientBoosting": "assets/fichas_de_algoritmos/histgradientboosting/01_ficha.md",
          "Ridge": "assets/fichas_de_algoritmos/regresion_lineal_y_regularizadas/01_ficha.md"}
COLUMNA_FECHA = "date"
CLAVE_SERIE = ["store_id", "dept_id"]
COLUMNA_FUERA = "fuera_del_error"
COLUMNA_FUGA = "fuga_canario"
# Lo que nunca se abre: la validación, la prueba final y un lote de producción (método, apartado 9, validación 3)
NO_SE_ABRE = re.compile(r"validacion|prueba|produccion")

# Reglas, apartado 5 y planteamientos §2: el horizonte de cada objetivo
HORIZONTE = {"unidades": 10, "dolares": 28}
OBJETIVOS = tuple(HORIZONTE)
# El responsable del caso, 24/11/2026 (reglas, apartado 7, «Preselección de variables»): fuera event_name_1 y event_name_2
FUERA_PREFIJOS = ("event_name_1_ohe_", "event_name_2_ohe_")
# Planteamientos §2, «Algoritmos y búsqueda»: 15 candidatos al azar en HistGradientBoosting; Ridge, rejilla entera
ALGORITMOS = ("HistGradientBoosting", "Ridge")
CANDIDATOS = {"HistGradientBoosting": 15, "Ridge": None}
NOMBRE_ALGORITMO = {"HistGradientBoosting": "HistGradientBoostingRegressor", "Ridge": "Ridge"}
# Parámetros del método (parametros.md), con el valor del caso
SEMILLA = 42
PLIEGUES = 5
REPETICIONES = 10
# Manual 3.6: con datos de una muestra la desviación típica divide por n − 1; cinco cortes son una muestra
DDOF = 1
# Reglas, apartado 7, «Lo esperable»: un error de menos de 5 por cada 100 apunta a que la previsión usa el futuro
LIMITE_FUGA = 5.0
# Lo que valida scikit-learn 1.9 en cada hiperparámetro que se puede ampliar: mínimo y si el mínimo vale
LIMITES = {"learning_rate": (0.0, False), "l2_regularization": (0.0, True), "max_depth": (1, True),
           "max_iter": (1, True), "min_samples_leaf": (1, True), "alpha": (0.0, False)}
ENTEROS = ("max_depth", "max_iter", "min_samples_leaf")
NOMBRE_REGLA = {"repetir_semana_anterior": "repetir la semana anterior",
                "media_28_dias": "la media de los últimos 28 días",
                "media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores"}
# Los nombres de las validaciones: la prueba y el propio script buscan que ninguna se escriba con su resultado puesto
NOMBRES_VALIDACION = ("sin_filas_de_ajuste", "semillas", "validacion_sin_abrir", "columnas_de_preseleccion",
                      "citas_existen", "reproducible", "sin_identificadores_ni_posteriores", "sin_resultados_escritos",
                      "objetivo_conocido_al_entrenar", "pliegues_por_fecha", "mismos_cortes", "medido_en_recursiva",
                      "recursiva_completa_sin_negativas", "recursiva_a_un_dia_igual", "bordes_ampliados",
                      "rotulos_de_filas", "empate_pliegue_a_pliegue", "canario_objetivo_barajado",
                      "entrada_sin_cambiar", "con_probabilidad", "recalibrado_si_hace_falta",
                      "probabilidad_media_cerca_de_la_tasa", "intervalo_por_entidad")

TEORIA = [{"apartado": "32.4", "por_que": "los hiperparámetros se prueban con validación cruzada dentro del "
                                          "entrenamiento"},
          {"apartado": "32.6", "por_que": "si gana un valor del borde, se amplía hacia ese lado; si la medida no "
                                          "cambia en el rango, también; una segunda búsqueda contesta solo eso"},
          {"apartado": "32.7", "por_que": "búsqueda aleatoria cuando las combinaciones se disparan (72 en el boosting)"},
          {"apartado": "32.8", "por_que": "el candidato es el Pipeline entero, ajustado dentro de cada corte"},
          {"apartado": "31.6", "por_que": "validación cruzada temporal, ventana creciente, test_size igual al horizonte"},
          {"apartado": "31.7", "por_que": "previsión recursiva: cada candidato se mide como se usará, con el error que "
                                          "crece con el horizonte"},
          {"apartado": "31.9", "por_que": "WAPE con el sesgo aparte, la referencia ingenua y el error en entrenamiento "
                                          "al lado"},
          {"apartado": "19.3", "por_que": "la distancia entre entrenamiento y validación cruzada se compara entre "
                                          "modelos del mismo problema, sin vara fija"},
          {"apartado": "3.6", "por_que": "la desviación de cinco cortes, como muestra, divide por n − 1"}]


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


def validacion_sin_abrir(abiertas):
    """Verdadero si ninguna tabla abierta es de validación, prueba final o producción (validación 3)."""
    return not any(NO_SE_ABRE.search(Path(a).stem) for a in abiertas)


def rotulos_de_filas(nodo, camino=""):
    """Las cifras del JSON con el rótulo de filas mal puesto (resultado.md; validación 1).

    Una cifra es un diccionario con «error» o «cv_media». Bajo la clave «entrenamiento» tiene que decir que sus filas son
    de entrenamiento; en cualquier otro sitio, que son fuera de pliegue. Sin «filas», también está mal.
    """
    malas = []
    if isinstance(nodo, dict):
        if "error" in nodo or "cv_media" in nodo:
            filas = str(nodo.get("filas", ""))
            de_entrenamiento = camino.rsplit("/", 1)[-1] == "entrenamiento"
            if de_entrenamiento and not filas.startswith("entrenamiento"):
                malas.append(camino)
            elif not de_entrenamiento and not filas.startswith("fuera de pliegue"):
                malas.append(camino)
        for k, v in nodo.items():
            malas += rotulos_de_filas(v, f"{camino}/{k}")
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            malas += rotulos_de_filas(v, f"{camino}[{i}]")
    return malas


def sin_filas_de_ajuste(indices_ajuste, indices_medida):
    """Verdadero si ninguna fila medida es una fila del ajuste (validación 1)."""
    return len(np.intersect1d(np.asarray(indices_ajuste), np.asarray(indices_medida))) == 0


def redondo(x):
    """Redondea al entero, la mitad hacia arriba (error 9)."""
    return int(math.floor(x + 0.5))


# ══ 3. Al empezar ═══════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Lee preseleccion.json, preparacion.json y modelo_minimo.json: si alguno falta, no está en OK o AVISO o la tabla
    tiene otra huella, no se empieza (resultado.md, «Al empezar»)."""
    paradas = []
    leidos = {}
    for rel in (PRESELECCION_REL, PREPARACION_REL, MODELO_MINIMO_REL):
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
    for rel in (PRESELECCION_REL, MODELO_MINIMO_REL):
        huellas = {e.get("ruta"): e.get("sha256") for e in leidos.get(rel, {}).get("entradas", [])}
        if rel in leidos and huellas.get(ENTRENAMIENTO_REL) != actual:
            paradas.append(f"la huella de {ENTRENAMIENTO_REL} no es la de {rel}")
    return paradas, leidos


# ══ 4. Columnas, modelos y candidatos ═══════════════════════════════════════════
def columnas_modelo(preseleccion, objetivo, algoritmo):
    """Las columnas finales de la preselección sin las de event_name_1 y event_name_2 (reglas, apartado 7)."""
    finales = preseleccion["objetivos"][objetivo]["columnas_finales"][algoritmo]
    return [c for c in finales if not c.startswith(FUERA_PREFIJOS)]


def construir_modelo(objetivo, columnas_evento, columnas, estimador, extra=()):
    """El Pipeline entero: el preprocesador del caso, sin ajustar, las columnas de la preselección y el algoritmo.

    Es el de scripts/14_modelo_minimo.py, que no se importa (error 1). extra: columnas que pasan tal cual junto al
    preprocesador; solo las usa el canario de la fuga.
    """
    preparacion = construir_preprocesador(objetivo, columnas_evento)
    if extra:
        preparacion = ColumnTransformer(
            [("preparacion", preparacion, columnas_entrada(objetivo, columnas_evento)),
             ("extra", "passthrough", list(extra))],
            remainder="drop", verbose_feature_names_out=False).set_output(transform="pandas")
    seleccion = ColumnTransformer([("columnas", "passthrough", list(columnas) + list(extra))], remainder="drop",
                                  verbose_feature_names_out=False).set_output(transform="pandas")
    return Pipeline([("preprocesador", preparacion), ("columnas", seleccion), ("modelo", estimador)])


def estimador(algoritmo, hiperparametros):
    """El algoritmo con sus hiperparámetros y la semilla; el boosting sin parada temprana (con fecha, método, apartado 5)."""
    if algoritmo == "HistGradientBoosting":
        return HistGradientBoostingRegressor(early_stopping=False, random_state=SEMILLA, **hiperparametros)
    if algoritmo == "Ridge":
        return Ridge(random_state=SEMILLA, **hiperparametros)
    raise ValueError(f"algoritmo desconocido: {algoritmo}")


def combinaciones(rejilla):
    """Cuántas combinaciones tiene una rejilla."""
    return len(ParameterGrid(rejilla))


def candidatos(rejilla, n, semilla):
    """Los candidatos de la búsqueda: n al azar con semilla, o la rejilla entera si n es None o no es menor que ella.

    RandomizedSearchCV no prevé desde un origen, así que el bucle es propio y los candidatos salen de ParameterSampler
    o ParameterGrid (petición de la búsqueda, punto 3).
    """
    total = combinaciones(rejilla)
    if n is None or n >= total:
        return [dict(c) for c in ParameterGrid(rejilla)], "rejilla"
    return [dict(c) for c in ParameterSampler(rejilla, n_iter=n, random_state=semilla)], "aleatoria"


def grupo_de(columna):
    """La variable de origen de una columna de salida del preprocesador."""
    for prefijo in ("store_id", "dept_id", "weekday", "month", "event_name_1", "event_name_2"):
        if columna.startswith(f"{prefijo}_ohe_"):
            return prefijo
    for sufijo in ("_rs", "_ss"):
        if columna.endswith(sufijo):
            return columna[: -len(sufijo)]
    return columna


# ══ 5. Medir un candidato en un corte ═══════════════════════════════════════════
def previsto_medible(valores, objetivo):
    """Acota en cero y, en unidades, redondea al entero (método, apartado 8; reglas, apartado 6)."""
    v = np.clip(np.asarray(valores, dtype="float64"), 0.0, None)
    return pr.redondear_unidades(v) if objetivo == "unidades" else v


def medir(real, previsto, filas):
    """Error y sesgo de reglas, apartado 6 con las filas sobre las que se calcularon."""
    error, sesgo = pr.error_y_sesgo(real, previsto)
    return {"error": error, "sesgo": sesgo, "filas": filas}


def comprobar_recursiva(prevision, n_series, origen, horizonte):
    """Verdadero si la previsión es la recursiva entera desde el origen: cada serie con un día por cada h de 1 al
    horizonte, cada día igual al origen más h. Una previsión a un día no pasa."""
    if not {"h", COLUMNA_FECHA}.issubset(prevision.columns) or len(prevision) != n_series * horizonte:
        return False
    if sorted(prevision["h"].unique().tolist()) != list(range(1, horizonte + 1)):
        return False
    por_serie = prevision.groupby(CLAVE_SERIE)["h"].nunique()
    fechas = pd.to_datetime(prevision[COLUMNA_FECHA])
    esperadas = pd.Timestamp(origen) + pd.to_timedelta(prevision["h"], unit="D")
    return bool(len(por_serie) == n_series and (por_serie == horizonte).all() and (fechas == esperadas).all())


def medir_candidato(tabla, objetivo, entrada, modelo, pliegue, numero, objetivo_ajuste=None):
    """Ajusta un modelo con los días del ajuste de un corte y lo mide con la previsión recursiva desde su origen.

    tabla: ordenada por fecha y serie. modelo: sin ajustar, con fit y predict. objetivo_ajuste: otro objetivo para el
    ajuste (el canario barajado); la historia de la recursión es siempre la real. Los 25 de diciembre entran en el
    ajuste y salen de la medida (reglas, apartado 6). Devuelve las cifras, lo que piden las validaciones y el modelo ajustado.
    """
    h = HORIZONTE[objetivo]
    en_ajuste = tabla[COLUMNA_FECHA].isin(pliegue["dias_ajuste"]).to_numpy()
    en_prueba = tabla[COLUMNA_FECHA].isin(pliegue["dias_prueba"]).to_numpy()
    ajuste, prueba = tabla[en_ajuste], tabla[en_prueba]
    y = ajuste[objetivo] if objetivo_ajuste is None else objetivo_ajuste

    # El ajuste, solo con el pasado del corte
    inicio = time.perf_counter()
    modelo.fit(ajuste[entrada], y)
    segundos_ajuste = time.perf_counter() - inicio

    # La previsión recursiva desde el origen, como se usará; la historia es la venta real hasta el origen
    inicio = time.perf_counter()
    recursiva = pr.prever_recursivo(modelo, ajuste[CLAVE_SERIE + [COLUMNA_FECHA, objetivo]], prueba, objetivo, h,
                                    origen=pliegue["origen"])
    segundos_recursion = time.perf_counter() - inicio
    n_series = len(ajuste[CLAVE_SERIE].drop_duplicates())
    junto = prueba[CLAVE_SERIE + [COLUMNA_FECHA, objetivo, COLUMNA_FUERA]].merge(
        recursiva, on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one")

    # La cifra del corte, sin los días fuera del error, con la previsión acotada y en unidades redondeada
    medidas = junto[~junto[COLUMNA_FUERA].to_numpy()]
    filas = (f"fuera de pliegue: {len(medidas)} filas de prueba del corte {numero}, recursiva desde el origen "
             f"{pliegue['origen']:%Y-%m-%d}")
    recursivo = medir(medidas[objetivo].to_numpy(dtype="float64"), previsto_medible(medidas["prevision"], objetivo),
                      filas)

    # En las filas del ajuste, a un día con los retardos reales: es la cifra de entrenamiento, rotulada como tal
    inicio = time.perf_counter()
    aj = ajuste[~ajuste[COLUMNA_FUERA].to_numpy()]
    entrenamiento = medir(aj[objetivo].to_numpy(dtype="float64"), previsto_medible(modelo.predict(aj[entrada]), objetivo),
                          f"entrenamiento: {len(aj)} filas del ajuste del corte {numero}, a un día")
    segundos_entrenamiento = time.perf_counter() - inicio

    # El primer día del horizonte tiene que dar lo mismo en recursivo que a un día con los retardos reales
    primero = prueba[(prueba[COLUMNA_FECHA] == pliegue["origen"] + pr.UN_DIA).to_numpy()]
    uno = primero[CLAVE_SERIE + [COLUMNA_FECHA]].assign(a_un_dia=np.clip(modelo.predict(primero[entrada]), 0.0, None))
    uno = uno.merge(recursiva, on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one")
    diferencia = float(np.abs(uno["prevision"] - uno["a_un_dia"]).max()) if len(uno) else float("inf")

    cifras = {"corte": numero, "origen": pliegue["origen"], "recursiva": recursivo, "entrenamiento": entrenamiento,
              "segundos": {"ajuste": segundos_ajuste, "recursion": segundos_recursion,
                           "entrenamiento": segundos_entrenamiento}}
    control = {"comprobacion": pr.comprobar_pliegue(pliegue["dias_ajuste"], pliegue["dias_prueba"], h),
               "sin_filas_de_ajuste": sin_filas_de_ajuste(np.flatnonzero(en_ajuste), np.flatnonzero(en_prueba)),
               "filas_ajuste_sin_conocer": int((ajuste[COLUMNA_FECHA] >= pliegue["dias_prueba"].min()).sum()),
               "medido_en_recursiva": comprobar_recursiva(recursiva, n_series, pliegue["origen"], h),
               "recursiva_completa": bool(junto["prevision"].notna().all() and len(recursiva) == len(prueba)),
               "recursiva_sin_negativas": bool((recursiva["prevision"] >= 0).all()),
               "recursiva_a_un_dia_igual": bool(diferencia <= 1e-6 * (1 + float(uno["a_un_dia"].abs().max()))),
               "prevision": junto["prevision"].to_numpy(), "filas_ajuste": int(en_ajuste.sum())}
    return cifras, control, modelo


# ══ 6. La comparación pliegue a pliegue (método, apartado 6, «Empate») ═════════════════════
def comparar_pliegue_a_pliegue(a, b):
    """Compara dos series de errores por corte, a menos b en los mismos cortes.

    a, b: {"origenes": [...], "errores": [...]}. Para si los cortes no son los mismos. Empatan si la media de las
    diferencias no pasa de su desviación típica (n − 1); si la pasa, gana el de menos error («a» o «b»).
    """
    if [str(x) for x in a["origenes"]] != [str(x) for x in b["origenes"]]:
        raise ValueError("cortes distintos: dos medidas solo se comparan en los mismos cortes")
    d = np.asarray(a["errores"], dtype="float64") - np.asarray(b["errores"], dtype="float64")
    if len(d) < 2:
        raise ValueError("hacen falta al menos dos cortes para comparar pliegue a pliegue")
    media, desviacion = float(d.mean()), float(d.std(ddof=DDOF))
    empate = abs(media) <= desviacion
    return {"diferencias": d.tolist(), "media": media, "desviacion": desviacion, "empate": bool(empate),
            "mejor": None if empate else ("a" if media < 0 else "b"), "metodo": "pliegue a pliegue"}


def elegir_ganador(por_algoritmo, trivial):
    """El ganador entre HistGradientBoosting y Ridge (método, apartado 6).

    Sin empate pliegue a pliegue, gana el de menos error aunque sea el menos estable. Con empate, como el modelo solo
    predice, gana el más estable frente al trivial: la menor desviación, corte a corte, de su error menos el del
    trivial. Si siguen igualados, el más sencillo, Ridge.
    """
    hgb, ridge = por_algoritmo["HistGradientBoosting"], por_algoritmo["Ridge"]
    comp = comparar_pliegue_a_pliegue(hgb, ridge)
    estabilidad = {nombre: comparar_pliegue_a_pliegue(serie, trivial)["desviacion"]
                   for nombre, serie in por_algoritmo.items()}
    if not comp["empate"]:
        algoritmo = "HistGradientBoosting" if comp["mejor"] == "a" else "Ridge"
        criterio = "pliegue a pliegue"
    elif estabilidad["HistGradientBoosting"] != estabilidad["Ridge"]:
        algoritmo = min(estabilidad, key=estabilidad.get)
        criterio = "estabilidad"
    else:
        algoritmo, criterio = "Ridge", "sencillez"
    return {"algoritmo": algoritmo, "empate": comp["empate"], "criterio": criterio, "comparacion": comp,
            "estabilidad_frente_al_trivial": estabilidad}


# ══ 7. El borde y el rango plano (método, apartado 5) ═════════════════════════════════════
def _ordenados(valores):
    """Los valores de un hiperparámetro de menor a mayor, con «sin límite» (None) al final."""
    numericos = sorted(v for v in valores if v is not None)
    return numericos + ([None] if None in valores else [])


def detectar_bordes(rejilla, mejor):
    """Los hiperparámetros cuyo mejor valor cae en un borde de su rejilla, con el lado («bajo» o «alto»).

    Solo cuentan los que se buscan, los de dos valores o más; «sin límite» es el borde alto.
    """
    bordes = []
    for nombre, valores in rejilla.items():
        orden = _ordenados(list(valores))
        if len(orden) < 2 or nombre not in mejor:
            continue
        if mejor[nombre] == orden[0]:
            bordes.append((nombre, "bajo"))
        elif mejor[nombre] == orden[-1]:
            bordes.append((nombre, "alto"))
    return bordes


def detectar_planos(rejilla, resultados):
    """Los hiperparámetros en que la medida no cambia a lo largo de su rango.

    Para cada valor probado, el error medio por corte de los candidatos con ese valor; el mejor valor y el peor se
    comparan pliegue a pliegue (§6, «Empate»). Si empatan, el rango no separa nada.
    """
    planos = []
    for nombre, valores in rejilla.items():
        if len(valores) < 2:
            continue
        por_valor = {}
        for r in resultados:
            por_valor.setdefault(repr(r["hiperparametros"].get(nombre)), []).append(r)
        if len(por_valor) < 2:
            continue
        medias = {k: {"origenes": v[0]["origenes"], "errores": np.mean([x["errores"] for x in v], axis=0)}
                  for k, v in por_valor.items()}
        mejor = min(medias, key=lambda k: float(np.mean(medias[k]["errores"])))
        peor = max(medias, key=lambda k: float(np.mean(medias[k]["errores"])))
        if comparar_pliegue_a_pliegue(medias[mejor], medias[peor])["empate"]:
            planos.append(nombre)
    return planos


def ampliar_valor(valores, lado, nombre):
    """El valor siguiente de la rejilla por un lado: un paso más de su progresión.

    Con los dos valores más cercanos al borde: si los dos son positivos, la misma proporción; si no, la misma
    diferencia. Los enteros se redondean. Devuelve (valor, None) o (None, motivo) si no admite ampliación.
    """
    orden = _ordenados(list(valores))
    if len(orden) < 2:
        return None, "un solo valor: no hay progresión que seguir"
    if lado == "alto" and orden[-1] is None:
        return None, "«sin límite» ya es el valor más alto"
    numericos = [v for v in orden if v is not None]
    if len(numericos) < 2:
        return None, "un solo valor con límite: no hay progresión que seguir"
    borde, interior = (numericos[-1], numericos[-2]) if lado == "alto" else (numericos[0], numericos[1])
    nuevo = borde * borde / interior if borde > 0 and interior > 0 else borde + (borde - interior)
    if nombre in ENTEROS:
        nuevo = redondo(nuevo)
    minimo, incluido = LIMITES.get(nombre, (None, True))
    if minimo is not None and (nuevo < minimo or (nuevo == minimo and not incluido)):
        return None, f"{nuevo} queda por debajo del mínimo válido ({minimo})"
    if nuevo == borde:
        return None, "el paso siguiente repite el borde"
    return (float(nuevo) if nombre not in ENTEROS else int(nuevo)), None


def bordes_ampliados(bordes, ampliaciones):
    """Verdadero si cada borde tiene su ampliación medida o el motivo por el que no se puede ampliar."""
    for nombre, lado in bordes:
        hecha = [a for a in ampliaciones if a["hiperparametro"] == nombre and a["lado"] == lado]
        if not any((a["valor_nuevo"] is not None and a["medido"]) or (a["valor_nuevo"] is None and a["imposible"])
                   for a in hecha):
            return False
    return True


# ══ 8. Una búsqueda ═════════════════════════════════════════════════════════════
def medir_lista(tabla, objetivo, algoritmo, lista, columnas, columnas_evento, pliegues, busqueda, primero):
    """Mide una lista de candidatos en los cortes; devuelve sus resultados, sus controles y los modelos del mejor."""
    entrada = columnas_entrada(objetivo, columnas_evento)
    resultados, controles = [], []
    mejor_modelos, mejor_error = None, None
    for k, hiper in enumerate(lista):
        cortes, modelos = [], []
        for numero, pliegue in enumerate(pliegues, start=1):
            modelo = construir_modelo(objetivo, columnas_evento, columnas, estimador(algoritmo, hiper))
            c, control, ajustado = medir_candidato(tabla, objetivo, entrada, modelo, pliegue, numero)
            cortes.append(c)
            control["semilla"] = ajustado[-1].get_params().get("random_state")
            controles.append(control)
            modelos.append(ajustado)
        errores = [c["recursiva"]["error"] for c in cortes]
        r = {"objetivo": objetivo, "algoritmo": algoritmo, "busqueda": busqueda, "candidato": primero + k,
             "hiperparametros": hiper, "origenes": [c["origen"] for c in cortes], "errores": errores,
             "sesgos": [c["recursiva"]["sesgo"] for c in cortes],
             "entrenamiento_errores": [c["entrenamiento"]["error"] for c in cortes],
             "por_corte": cortes, "previsiones": [ctl["prevision"] for ctl in controles[-len(pliegues):]]}
        r["cv_media"] = float(np.mean(errores))
        resultados.append(r)
        # Se guardan solo los modelos del mejor hasta ahora, para la importancia y la distancia del ganador
        if mejor_error is None or r["cv_media"] < mejor_error:
            mejor_error, mejor_modelos = r["cv_media"], modelos
    return resultados, controles, mejor_modelos


def mejor_de(resultados):
    """El candidato de menos error medio; con empate exacto, el primero probado (error 7)."""
    return min(resultados, key=lambda r: (r["cv_media"], r["candidato"]))


# ══ 9. Las referencias de cada corte ════════════════════════════════════════════
def referencias_del_corte(tabla, objetivo, pliegue, numero):
    """El trivial (DummyRegressor con la mediana, método, apartado 6) y las tres reglas (reglas, apartado 7) en las filas medidas del
    corte, las mismas que los candidatos."""
    h = HORIZONTE[objetivo]
    en_ajuste = tabla[COLUMNA_FECHA].isin(pliegue["dias_ajuste"]).to_numpy()
    en_prueba = tabla[COLUMNA_FECHA].isin(pliegue["dias_prueba"]).to_numpy()
    ajuste, prueba = tabla[en_ajuste], tabla[en_prueba]
    reglas = pr.reglas_sencillas(ajuste, objetivo, pliegue["origen"], h)
    junto = prueba[CLAVE_SERIE + [COLUMNA_FECHA, objetivo, COLUMNA_FUERA]].merge(
        reglas.drop(columns="h"), on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one")
    trivial = DummyRegressor(strategy="median").fit(np.zeros((len(ajuste), 1)), ajuste[objetivo])
    junto["trivial_mediana"] = trivial.predict(np.zeros((len(junto), 1)))
    medidas = junto[~junto[COLUMNA_FUERA].to_numpy()]
    real = medidas[objetivo].to_numpy(dtype="float64")
    filas = f"fuera de pliegue: {len(medidas)} filas de prueba del corte {numero}"
    return {nombre: medir(real, previsto_medible(medidas[nombre], objetivo), filas)
            for nombre in ("trivial_mediana",) + pr.REGLAS}


# ══ 10. Importancia, regla simple y canario del ganador (método, apartado 7) ════════════════
def importancia_por_grupos(modelo, x, y, grupos, puntuar, repeticiones, semilla):
    """Importancia por permutación de grupos de columnas, con el reparto de azar de permutation_importance.

    Es la de scripts/14_modelo_minimo.py, comprobada allí contra scikit-learn (error 30). Cada grupo (las columnas de
    una misma variable de origen) se baraja junto. La importancia es la puntuación sin barajar menos la barajada.
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


def filas_medidas_del_corte(tabla, pliegue):
    """Las filas de prueba del corte sin los días fuera del error."""
    en_prueba = tabla[COLUMNA_FECHA].isin(pliegue["dias_prueba"]).to_numpy()
    prueba = tabla[en_prueba]
    return prueba[~prueba[COLUMNA_FUERA].to_numpy()]


def importancias_del_ganador(tabla, objetivo, columnas, columnas_evento, pliegues, modelos):
    """Permutación por variable de origen sobre las filas de prueba de los cortes, con el modelo de cada corte, a un
    día con los retardos reales (la recursión genera sus retardos y no se pueden barajar)."""
    entrada = columnas_entrada(objetivo, columnas_evento)
    grupos = {}
    for c in columnas:
        grupos.setdefault(grupo_de(c), []).append(c)

    def puntuar(r, previsto):
        """Menos el error del caso: mayor es mejor."""
        return -pr.error_y_sesgo(r, previsto_medible(previsto, objetivo))[0]

    por_corte, a_un_dia = [], []
    for pliegue, modelo in zip(pliegues, modelos):
        medidas = filas_medidas_del_corte(tabla, pliegue)
        real = medidas[objetivo].to_numpy(dtype="float64")
        x = modelo[:1].transform(medidas[entrada])
        por_corte.append(importancia_por_grupos(modelo[1:], x, real, grupos, puntuar, REPETICIONES, SEMILLA))
        a_un_dia.append(pr.error_y_sesgo(real, previsto_medible(modelo.predict(medidas[entrada]), objetivo)))
    valores = []
    for grupo in por_corte[0]:
        medias = [imp[grupo]["media"] for imp in por_corte]
        valores.append({"columna": grupo, "importancia": float(np.mean(medias)),
                        "desviacion": float(np.std(medias, ddof=DDOF)), "por_corte": medias})
    valores.sort(key=lambda v: (-v["importancia"], v["columna"]))
    positivas = sum(max(v["importancia"], 0.0) for v in valores)
    filas = sum(len(filas_medidas_del_corte(tabla, p)) for p in pliegues)
    return {"metodo": "permutacion por variable de origen", "repeticiones": REPETICIONES, "semilla": SEMILLA,
            "puntuacion": "menos el error de reglas, apartado 6, con la previsión acotada"
                          + (" y redondeada" if objetivo == "unidades" else ""),
            "filas": f"fuera de pliegue: {filas} filas de prueba de los {len(pliegues)} cortes, a un día con los "
                     f"retardos reales",
            "valores": valores,
            "peso_de_las_dos_primeras": (sum(max(v["importancia"], 0.0) for v in valores[:2]) / positivas
                                         if positivas > 0 else None)}, a_un_dia


def regla_simple(tabla, objetivo, columnas, columnas_evento, pliegues, variables, ganador):
    """La regla simple hecha solo con las dos variables de más peso (método, apartado 7): una regresión lineal con sus columnas,
    medida en recursivo en los mismos cortes y comparada pliegue a pliegue con el ganador."""
    entrada = columnas_entrada(objetivo, columnas_evento)
    cols = [c for c in columnas if grupo_de(c) in variables]
    cortes = []
    for numero, pliegue in enumerate(pliegues, start=1):
        modelo = construir_modelo(objetivo, columnas_evento, cols, LinearRegression())
        c, _, _ = medir_candidato(tabla, objetivo, entrada, modelo, pliegue, numero)
        cortes.append(c)
    serie = {"origenes": [c["origen"] for c in cortes], "errores": [c["recursiva"]["error"] for c in cortes]}
    comp = comparar_pliegue_a_pliegue({"origenes": ganador["origenes"], "errores": ganador["errores"]}, serie)
    return {"variables": list(variables), "columnas": cols, "modelo": "LinearRegression",
            "recursiva": {"error": float(np.mean(serie["errores"])),
                          "sesgo": float(np.mean([c["recursiva"]["sesgo"] for c in cortes])),
                          "filas": f"fuera de pliegue: los {len(pliegues)} cortes, recursiva desde cada origen"},
            "por_corte": [c["recursiva"] for c in cortes], "comparacion_con_el_ganador": comp,
            "el_ganador_la_supera": bool(comp["mejor"] == "a")}


def canario(tabla, objetivo, algoritmo, hiper, columnas, columnas_evento, pliegue, numero, referencias):
    """El canario de la validación 11 en el último corte, con la receta del ganador.

    Con el objetivo barajado en el ajuste, el modelo pierde la señal y deja de ganar a las tres reglas. Con la venta
    real puesta como variable, el error cae por debajo de LIMITE_FUGA, el que reglas, apartado 7 da como señal de usar el futuro.
    """
    entrada = columnas_entrada(objetivo, columnas_evento)
    en_ajuste = tabla[COLUMNA_FECHA].isin(pliegue["dias_ajuste"]).to_numpy()
    y = tabla.loc[en_ajuste, objetivo].to_numpy()
    barajado = np.random.default_rng(SEMILLA).permutation(y)
    modelo = construir_modelo(objetivo, columnas_evento, columnas, estimador(algoritmo, hiper))
    con_barajado, _, _ = medir_candidato(tabla, objetivo, entrada, modelo, pliegue, numero, objetivo_ajuste=barajado)
    con_fuga = tabla.assign(**{COLUMNA_FUGA: tabla[objetivo].astype("float64")})
    modelo = construir_modelo(objetivo, columnas_evento, columnas, estimador(algoritmo, hiper), extra=(COLUMNA_FUGA,))
    con_columna, _, _ = medir_candidato(con_fuga, objetivo, entrada + [COLUMNA_FUGA], modelo, pliegue, numero)
    mejor_regla = min(pr.REGLAS, key=lambda r: referencias[r]["error"])
    return {"corte": numero, "barajado": con_barajado["recursiva"], "fuga": con_columna["recursiva"],
            "regla_que_menos_falla": {"nombre": mejor_regla, **referencias[mejor_regla]},
            "barajado_pierde_la_senal": bool(con_barajado["recursiva"]["error"] > referencias[mejor_regla]["error"]),
            "fuga_se_ve": bool(con_columna["recursiva"]["error"] < LIMITE_FUGA), "limite_fuga": LIMITE_FUGA}


# ══ 11. Un objetivo ═════════════════════════════════════════════════════════════
def resumen_de(r, filas_cv):
    """La fila del ranking de un candidato: media y desviación entre cortes, sesgo y entrenamiento con sus filas."""
    return {"cv_media": r["cv_media"], "cv_desviacion": float(np.std(r["errores"], ddof=DDOF)),
            "sesgo_media": float(np.mean(r["sesgos"])), "filas": filas_cv,
            "entrenamiento": {"error": float(np.mean(r["entrenamiento_errores"])),
                              "desviacion": float(np.std(r["entrenamiento_errores"], ddof=DDOF)),
                              "filas": "entrenamiento: las filas del ajuste de cada corte, a un día"}}


def buscar_objetivo(tabla, objetivo, preseleccion, rejillas, columnas_evento, pliegues, limite, ampliar):
    """Las dos búsquedas de un objetivo, sus ampliaciones, el ranking, el ganador y lo que pide el §7."""
    referencias = [referencias_del_corte(tabla, objetivo, p, i) for i, p in enumerate(pliegues, start=1)]
    origenes = [p["origen"] for p in pliegues]
    salida = {"resultados": [], "controles": [], "ampliaciones": [], "segundas": [], "espacio": [], "finales": {},
              "modelos": {}, "bordes": {}}
    for algoritmo in ALGORITMOS:
        columnas = columnas_modelo(preseleccion, objetivo, algoritmo)
        rejilla = rejillas[algoritmo]
        lista, tipo = candidatos(rejilla, CANDIDATOS[algoritmo], SEMILLA)
        if limite is not None:
            lista = lista[:limite]
        resultados, controles, modelos = medir_lista(tabla, objetivo, algoritmo, lista, columnas, columnas_evento,
                                                     pliegues, "primera", 1)
        mejor = mejor_de(resultados)
        salida["espacio"].append({"objetivo": objetivo, "algoritmo": algoritmo, "combinaciones": combinaciones(rejilla),
                                  "probadas": len(lista), "tipo": tipo})

        # El borde y el rango plano: se amplía una vez, por ese lado, y se repite solo este algoritmo
        bordes = detectar_bordes(rejilla, mejor["hiperparametros"])
        planos = detectar_planos(rejilla, resultados)
        lados = {(n, l): "borde" for n, l in bordes}
        for n in planos:
            for lado in ("bajo", "alto"):
                lados[(n, lado)] = "borde y rango plano" if (n, lado) in lados else "rango plano"
        salida["bordes"][algoritmo] = bordes
        nuevos, registros = [], []
        for (nombre, lado), motivo in sorted(lados.items()):
            valor, imposible = ampliar_valor(rejilla[nombre], lado, nombre)
            registro = {"objetivo": objetivo, "algoritmo": algoritmo, "hiperparametro": nombre, "lado": lado,
                        "motivo": motivo, "valor_mejor": mejor["hiperparametros"].get(nombre), "valor_nuevo": valor,
                        "imposible": imposible, "medido": False, "candidato": None}
            if valor is not None and ampliar:
                candidato = dict(mejor["hiperparametros"], **{nombre: valor})
                if candidato not in nuevos and candidato not in [r["hiperparametros"] for r in resultados]:
                    nuevos.append(candidato)
                registro["candidato"] = candidato
            registros.append(registro)
        if nuevos:
            segundos, ctl2, modelos2 = medir_lista(tabla, objetivo, algoritmo, nuevos, columnas, columnas_evento,
                                                   pliegues, "ampliacion", len(resultados) + 1)
            controles += ctl2
            for registro in registros:
                registro["medido"] = registro["candidato"] is not None
            mejor2 = mejor_de(segundos)
            comp = comparar_pliegue_a_pliegue(mejor, mejor2)
            adoptado = comp["mejor"] == "b"
            salida["segundas"].append({
                "objetivo": objetivo, "algoritmo": algoritmo,
                "que_contesta": [f"{r['hiperparametro']} ({r['motivo']}, lado {r['lado']})" for r in registros
                                 if r["candidato"] is not None],
                "candidatos": len(nuevos), "mejor_nuevo": mejor2["hiperparametros"],
                "mejora": -comp["media"], "desviacion": comp["desviacion"], "se_sostiene": adoptado,
                "adoptado": adoptado,
                "queda_en_el_borde": [n for n, _ in detectar_bordes(
                    {k: sorted(set(_ordenados(rejilla[k]) + [c[k] for c in nuevos]), key=lambda v: (v is None, v or 0))
                     for k in rejilla}, mejor2["hiperparametros"]) if adoptado]})
            resultados += segundos
            if adoptado:
                mejor, modelos = mejor2, modelos2
        salida["ampliaciones"] += registros
        salida["resultados"] += resultados
        salida["controles"] += controles
        salida["finales"][algoritmo] = mejor
        salida["modelos"][algoritmo] = modelos

    # El ranking: una fila por algoritmo, con las referencias de los mismos cortes al lado
    filas_cv = f"fuera de pliegue: los {len(pliegues)} cortes, recursiva desde cada origen"
    ranking = []
    for algoritmo, mejor in salida["finales"].items():
        fila = {"objetivo": objetivo, "algoritmo": algoritmo, "candidato": mejor["candidato"],
                "hiperparametros": mejor["hiperparametros"], "origenes": mejor["origenes"],
                "por_corte": mejor["errores"], **resumen_de(mejor, filas_cv)}
        reglas_corte = [min(ref[r]["error"] for r in pr.REGLAS) for ref in referencias]
        fila["cortes_que_gana_a_la_regla_que_menos_falla"] = int(sum(e < m for e, m in zip(mejor["errores"],
                                                                                           reglas_corte)))
        ranking.append(fila)
    trivial = {"origenes": origenes, "errores": [ref["trivial_mediana"]["error"] for ref in referencias]}
    resumen_refs = [{"objetivo": objetivo, "nombre": nombre,
                     "cv_media": float(np.mean([ref[nombre]["error"] for ref in referencias])),
                     "cv_desviacion": float(np.std([ref[nombre]["error"] for ref in referencias], ddof=DDOF)),
                     "sesgo_media": float(np.mean([ref[nombre]["sesgo"] for ref in referencias])),
                     "por_corte": [ref[nombre]["error"] for ref in referencias], "filas": filas_cv.replace(
                         ", recursiva desde cada origen", ", desde cada origen")}
                    for nombre in ("trivial_mediana",) + pr.REGLAS]
    eleccion = elegir_ganador({a: {"origenes": m["origenes"], "errores": m["errores"]}
                               for a, m in salida["finales"].items()}, trivial)
    salida.update({"referencias": referencias, "ranking": ranking, "referencias_cv": resumen_refs,
                   "eleccion": eleccion, "trivial": trivial})
    return salida


def ganador_objetivo(tabla, objetivo, preseleccion, columnas_evento, pliegues, busqueda):
    """Lo que pide el §7 del ganador de un objetivo: reajuste, importancias, distancia, regla simple y canario."""
    algoritmo = busqueda["eleccion"]["algoritmo"]
    mejor = busqueda["finales"][algoritmo]
    columnas = columnas_modelo(preseleccion, objetivo, algoritmo)
    entrada = columnas_entrada(objetivo, columnas_evento)

    # Reajuste con todo el entrenamiento: el objetivo se sabe al momento, así que entran todas las filas (§7)
    inicio = time.perf_counter()
    final = construir_modelo(objetivo, columnas_evento, columnas, estimador(algoritmo, mejor["hiperparametros"]))
    final.fit(tabla[entrada], tabla[objetivo])
    segundos = time.perf_counter() - inicio
    medidas = tabla[~tabla[COLUMNA_FUERA].to_numpy()]
    reajuste = {"filas_ajuste": len(tabla), "segundos": segundos,
                "n_iter": getattr(final[-1], "n_iter_", None),
                "entrenamiento": medir(medidas[objetivo].to_numpy(dtype="float64"),
                                       previsto_medible(final.predict(medidas[entrada]), objetivo),
                                       f"entrenamiento: {len(medidas)} filas, todo el entrenamiento sin los 25 de "
                                       f"diciembre, a un día")}

    # Importancia por permutación con los modelos de cada corte, sobre filas que no vieron
    importancias, a_un_dia = importancias_del_ganador(tabla, objetivo, columnas, columnas_evento, pliegues,
                                                      busqueda["modelos"][algoritmo])

    # La distancia entre entrenamiento y validación cruzada, también a un día para separar la recursión
    fila = next(f for f in busqueda["ranking"] if f["algoritmo"] == algoritmo)
    cv_un_dia = float(np.mean([e for e, _ in a_un_dia]))
    distancia = {"entrenamiento": fila["entrenamiento"],
                 "a_un_dia": {"error": cv_un_dia, "filas": "fuera de pliegue: los cortes, a un día con los retardos "
                                                           "reales; solo para leer la distancia, no decide nada"},
                 "recursiva": {"error": fila["cv_media"], "filas": fila["filas"]},
                 "distancia_a_un_dia": cv_un_dia - fila["entrenamiento"]["error"],
                 "distancia_recursiva": fila["cv_media"] - fila["entrenamiento"]["error"],
                 "lectura": "manual 19.3: sin vara fija; se compara con la del otro algoritmo del ranking"}

    # Si una o dos variables llevan casi todo el peso: la regla simple con esas dos, siempre medida (§7)
    positivas = [v["columna"] for v in importancias["valores"] if v["importancia"] > 0][:2]
    simple = (regla_simple(tabla, objetivo, columnas, columnas_evento, pliegues, positivas, mejor)
              if positivas else None)

    # El canario de las fugas, en el último corte (validación 11)
    numero = len(pliegues)
    pajaro = canario(tabla, objetivo, algoritmo, mejor["hiperparametros"], columnas, columnas_evento,
                     pliegues[-1], numero, busqueda["referencias"][-1])

    # Dos ejecuciones seguidas dan la misma cifra (validación 8): se repite el primer corte del ganador
    modelo = construir_modelo(objetivo, columnas_evento, columnas, estimador(algoritmo, mejor["hiperparametros"]))
    _, otra, _ = medir_candidato(tabla, objetivo, entrada, modelo, pliegues[0], 1)
    reproducible = bool(np.array_equal(otra["prevision"], mejor["previsiones"][0]))

    eleccion = busqueda["eleccion"]
    if eleccion["criterio"] == "pliegue a pliegue":
        por_que = "gana pliegue a pliegue: la media de las diferencias pasa de su desviación"
    elif eleccion["criterio"] == "estabilidad":
        por_que = "empate pliegue a pliegue; gana el más estable frente al trivial, porque el modelo solo predice"
    else:
        por_que = "empate pliegue a pliegue y la misma estabilidad; gana el más sencillo"
    ganador = {"algoritmo": algoritmo, "clase": NOMBRE_ALGORITMO[algoritmo], "ficha": FICHAS[algoritmo],
               "hiperparametros": final[-1].get_params(), "buscados": mejor["hiperparametros"],
               "semilla": SEMILLA, "columnas": columnas, "n_columnas": len(columnas),
               "preprocesador": "scripts/preparacion_prevision.py, ajustado con las filas del ajuste",
               "por_que": por_que, "criterio": eleccion["criterio"], "aprobado_por": "", "reajuste": reajuste}
    return ganador, importancias, distancia, simple, pajaro, reproducible


# ══ 12. La tabla de lo probado y la estimación ═══════════════════════════════════
def tabla_probada(resultados):
    """Una fila por candidato con sus hiperparámetros, su medida por corte y su posición dentro de su algoritmo."""
    filas = []
    for r in resultados:
        fila = {"objetivo": r["objetivo"], "algoritmo": r["algoritmo"], "busqueda": r["busqueda"],
                "candidato": r["candidato"], "hiperparametros": json.dumps(r["hiperparametros"]),
                **{f"param_{k}": v for k, v in r["hiperparametros"].items()},
                "cv_media": r["cv_media"], "cv_desviacion": float(np.std(r["errores"], ddof=DDOF)),
                "sesgo_media": float(np.mean(r["sesgos"])),
                "cv_filas": "fuera de pliegue: recursiva desde el origen de cada corte",
                "entrenamiento_media": float(np.mean(r["entrenamiento_errores"])),
                "entrenamiento_filas": "entrenamiento: filas del ajuste de cada corte, a un día",
                "segundos": float(sum(c["segundos"]["ajuste"] + c["segundos"]["recursion"]
                                      + c["segundos"]["entrenamiento"] for c in r["por_corte"]))}
        for i, e in enumerate(r["errores"], start=1):
            fila[f"error_corte_{i}"] = e
        filas.append(fila)
    t = pd.DataFrame(filas)
    t["posicion"] = (t.groupby(["objetivo", "algoritmo"])["cv_media"].rank(method="first").astype("int64"))
    return t.sort_values(["objetivo", "algoritmo", "posicion"]).reset_index(drop=True)


def estimar(resultados, fraccion, rejillas):
    """La estimación de la búsqueda entera con los tiempos de la muestra: el ajuste y la predicción en entrenamiento
    crecen con las filas (lineal, por arriba); la recursión no depende de las filas."""
    estimacion = []
    for objetivo in OBJETIVOS:
        for algoritmo in ALGORITMOS:
            cortes = [c for r in resultados if r["objetivo"] == objetivo and r["algoritmo"] == algoritmo
                      for c in r["por_corte"]]
            if not cortes:
                continue
            ajuste = np.mean([c["segundos"]["ajuste"] + c["segundos"]["entrenamiento"] for c in cortes]) / fraccion
            recursion = np.mean([c["segundos"]["recursion"] for c in cortes])
            n = min(CANDIDATOS[algoritmo] or combinaciones(rejillas[algoritmo]), combinaciones(rejillas[algoritmo]))
            estimacion.append({"objetivo": objetivo, "algoritmo": algoritmo, "candidatos": n,
                               "segundos_por_corte": float(ajuste + recursion),
                               "segundos": float(n * PLIEGUES * (ajuste + recursion))})
    return estimacion


# ══ 13. La propuesta para el responsable del caso, generada del JSON ════════════════════════════════
NOMBRE_OBJETIVO = {"unidades": "Unidades", "dolares": "Dólares"}


def nombre_regla(nombre):
    """El nombre entero de una referencia."""
    return "el trivial (la mediana)" if nombre == "trivial_mediana" else NOMBRE_REGLA[nombre]


def num(x, decimales=1, signo=False):
    """Una cifra con coma decimal, como se escribe en español; con signo si se pide."""
    texto = f"{x:+.{decimales}f}" if signo else f"{x:.{decimales}f}"
    return texto.replace(".", ",")


def propuesta_md(r):
    """El texto de informes/busqueda_propuesta.md, solo con cifras del diccionario del JSON."""
    lineas = ["# Propuesta del ganador de la búsqueda · caso 69", "",
              f"Fecha de los datos: {r['fecha_datos']}. Sale de `{JSON_REL}`, generado por `{SCRIPT_REL}` el "
              f"{r['fecha_ejecucion'][:10]}. Estado: {r['resultado']['estado']}.", ""]
    if "ganador" not in r:
        lineas += ["La búsqueda no llegó a proponer un ganador.", "", f"Motivo: {r['resultado']['resumen']}", ""]
        return "\n".join(lineas)
    lineas += ["## Qué se propone", ""]
    for objetivo in OBJETIVOS:
        g = r["ganador"][objetivo]
        fila = next(f for f in r["ranking"] if f["objetivo"] == objetivo and f["algoritmo"] == g["algoritmo"])
        refs = [x for x in r["referencias_cv"] if x["objetivo"] == objetivo and x["nombre"] != "trivial_mediana"]
        regla = min(refs, key=lambda x: x["cv_media"])
        unidad = "unidades por cada 100 vendidas" if objetivo == "unidades" else "dólares por cada 100 vendidos"
        lineas.append(f"- **{NOMBRE_OBJETIVO[objetivo]}, a {HORIZONTE[objetivo]} días:** {g['algoritmo']}. Falla "
                      f"{num(fila['cv_media'])} {unidad} de media en los cortes, previendo en recursivo. La regla que "
                      f"menos falla de media es {nombre_regla(regla['nombre'])}: falla {num(regla['cv_media'])}.")
    lineas += ["", "Cada propuesta espera la aprobación del responsable del caso. Hasta entonces la validación sigue cerrada. El "
               "estado del JSON es PARADO porque el ganador está en su puerta.", "",
               "## La receta", "",
               "| Objetivo | Algoritmo | Hiperparámetros buscados | Semilla | Columnas |", "|---|---|---|---|---|"]
    for objetivo in OBJETIVOS:
        g = r["ganador"][objetivo]
        hiper = "; ".join(f"{k} = {v}" for k, v in sorted(g["buscados"].items()))
        lineas.append(f"| {objetivo} | {g['clase']} | {hiper} | {g['semilla']} | {g['n_columnas']} |")
    lineas += ["", "Las columnas son las de la preselección sin las de event_name_1 ni event_name_2. El preprocesador "
               "se ajusta con las filas de cada ajuste. La lista entera está en el JSON.", "",
               "## Por qué ese algoritmo", ""]
    for objetivo in OBJETIVOS:
        c = r["comparacion"][objetivo]
        g = r["ganador"][objetivo]
        lineas.append(f"- **{NOMBRE_OBJETIVO[objetivo]}:** HistGradientBoosting menos Ridge da "
                      f"{num(c['media'], 2, True)} puntos de media corte a corte, con una desviación de "
                      f"{num(c['desviacion'], 2)}. "
                      + ("La media pasa de la desviación, así que gana el de menos error." if not c["empate"] else
                         "La media no pasa de la desviación: empatan. Gana el más estable frente al trivial.")
                      + f" Queda {g['algoritmo']}.")
    lineas += ["", "## Ranking", "",
               "Error por cada 100 vendidos, media de los cortes en recursivo. El entrenamiento se mide a un día en "
               "las filas del ajuste de cada corte.", "",
               "| Objetivo | Algoritmo | Error | Desviación entre cortes | Sesgo | Entrenamiento | Cortes que gana |",
               "|---|---|---|---|---|---|---|"]
    for f in r["ranking"]:
        lineas.append(f"| {f['objetivo']} | {f['algoritmo']} | {num(f['cv_media'], 2)} | {num(f['cv_desviacion'], 2)} | "
                      f"{num(f['sesgo_media'], 2, True)} | {num(f['entrenamiento']['error'], 2)} | "
                      f"{f['cortes_que_gana_a_la_regla_que_menos_falla']} de {len(f['por_corte'])} |")
    lineas += ["", "«Cortes que gana» cuenta los cortes en que falla menos que la regla que menos falla en ese corte.",
               "", "| Objetivo | Referencia | Error | Sesgo |", "|---|---|---|---|"]
    for x in r["referencias_cv"]:
        lineas.append(f"| {x['objetivo']} | {nombre_regla(x['nombre'])} | {num(x['cv_media'], 2)} | "
                      f"{num(x['sesgo_media'], 2, True)} |")
    lineas += ["", "## Rejillas ampliadas", ""]
    for a in r["busqueda"]["rejillas_ampliadas"]:
        if a["valor_nuevo"] is not None:
            lineas.append(f"- {a['objetivo']}, {a['algoritmo']}, {a['hiperparametro']} ({a['motivo']}, lado "
                          f"{a['lado']}): se probó {a['valor_nuevo']}.")
        else:
            lineas.append(f"- {a['objetivo']}, {a['algoritmo']}, {a['hiperparametro']} ({a['motivo']}, lado "
                          f"{a['lado']}): no se amplía porque {a['imposible']}.")
    for s in r["busqueda"]["segundas_busquedas"]:
        lineas.append(f"- Segunda búsqueda de {s['algoritmo']} en {s['objetivo']}: mejora {num(s['mejora'], 2, True)} "
                      f"de media con una desviación de {num(s['desviacion'], 2)}. "
                      + ("Se sostiene pliegue a pliegue: se adopta." if s["adoptado"] else
                         "No se sostiene pliegue a pliegue: se queda el de la primera."))
    if not r["busqueda"]["rejillas_ampliadas"]:
        lineas.append("- Ninguna.")
    lineas += ["", "## Qué variables pesan", "",
               "Puntos de error que se pierden al barajar cada variable de origen, media de los cortes. Las cinco "
               "primeras de cada ganador:", "", "| Objetivo | Variable | Importancia |", "|---|---|---|"]
    for objetivo in OBJETIVOS:
        for v in r["importancias"][objetivo]["valores"][:5]:
            lineas.append(f"| {objetivo} | {v['columna']} | {num(v['importancia'], 2)} |")
    lineas.append("")
    for objetivo in OBJETIVOS:
        imp = r["importancias"][objetivo]
        partes = [f"- **{NOMBRE_OBJETIVO[objetivo]}:**"]
        if imp["peso_de_las_dos_primeras"] is not None:
            partes.append(f"las dos primeras llevan el {num(100 * imp['peso_de_las_dos_primeras'], 0)} % de la "
                          f"importancia positiva.")
        s = r["regla_simple"][objetivo]
        if s is not None:
            partes.append(f"Una regresión lineal con solo esas dos falla {num(s['recursiva']['error'])} de media.")
            partes.append("El ganador la supera pliegue a pliegue." if s["el_ganador_la_supera"] else
                          "El ganador no la supera pliegue a pliegue: no aporta sobre ella.")
        c = r["canario"][objetivo]
        partes.append(f"En el último corte, con el objetivo barajado falla {num(c['barajado']['error'])}.")
        partes.append(f"Con la venta real puesta como variable falla {num(c['fuga']['error'])}.")
        partes.append("Las dos cifras dicen que la comprobación ve una fuga cuando la hay."
                      if c["barajado_pierde_la_senal"] and c["fuga_se_ve"] else
                      "El canario no se comporta como debe: no se puede descartar una fuga.")
        lineas.append(" ".join(partes))
    lineas += ["", "## Entrenamiento frente a validación cruzada", ""]
    for objetivo in OBJETIVOS:
        d = r["distancia"][objetivo]
        lineas.append(f"- **{NOMBRE_OBJETIVO[objetivo]}:** {num(d['entrenamiento']['error'], 2)} en entrenamiento "
                      f"frente a {num(d['recursiva']['error'], 2)} en recursivo. A un día con los retardos reales, "
                      f"{num(d['a_un_dia']['error'], 2)}.")
    lineas.append("")
    lineas.append("La distancia no tiene una vara fija (manual 19.3): se lee al lado de la del otro algoritmo, que "
                  "está en el ranking.")
    lineas += ["", "## Límites", "",
               "- Ninguna cifra mira la validación. Todas salen del entrenamiento, con los cortes del modelo mínimo.",
               "- La importancia se mide a un día con los retardos reales: en la recursión los retardos salen de lo "
               "previsto y no se pueden barajar.",
               "- Cuánto se amplía una rejilla no está escrito en el método. Se toma un paso más de su progresión y se "
               "prueba con el resto de la receta del mejor candidato.",
               "- La desviación entre cortes divide por n − 1 (manual 3.6). El modelo mínimo dividía por n.",
               "- El suavizado exponencial no se mide aquí: va con la validación.", "",
               "## Lo que puede decidir el responsable del caso", "",
               "- Aprobar el ganador de cada objetivo con su receta, para abrir la validación una vez.",
               "- Pedir otra cosa antes de abrirla.", ""]
    return "\n".join(lineas)


# ══ 14. Principal ═══════════════════════════════════════════════════════════════
def principal(raiz, fraccion_medida=None, limite=None, objetivos=OBJETIVOS):
    """Prepara, busca en los objetivos pedidos, propone el ganador y devuelve el diccionario del JSON y la tabla."""
    medir_solo = fraccion_medida is not None
    r = {"metodo": "aprendizaje-automatico", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [], "resultado": {}, "pendientes": [], "puerta_de_juan": False}
    artefactos = [JSON_REL, CSV_REL, MD_REL]
    paradas, leidos = al_empezar(raiz)
    if paradas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "; ".join(paradas),
                          "artefactos": [JSON_REL, MD_REL], "siguiente": "volver a ejecutar los scripts 12 a 14"}
        return r, None
    preseleccion, preparacion, minimo = leidos[PRESELECCION_REL], leidos[PREPARACION_REL], leidos[MODELO_MINIMO_REL]
    rejillas = minimo["coste"]["rejillas"]
    abiertas = [ENTRENAMIENTO_REL]
    huella_antes = huella(raiz / ENTRENAMIENTO_REL)
    tabla = pd.read_parquet(raiz / ENTRENAMIENTO_REL)
    r["entradas"].append({"ruta": ENTRENAMIENTO_REL, "sha256": huella_antes, "filas": len(tabla),
                          "columnas": tabla.shape[1]})
    for rel in (PRESELECCION_REL, PREPARACION_REL, MODELO_MINIMO_REL):
        r["entradas"].append({"ruta": rel, "sha256": huella(raiz / rel)})
    # Orden por fecha y serie (error 7): el resultado no depende del orden en que llegan las filas
    tabla = tabla.sort_values([COLUMNA_FECHA] + CLAVE_SERIE, kind="stable").reset_index(drop=True)
    if medir_solo:
        dias = sorted(tabla[COLUMNA_FECHA].unique())
        desde = dias[-max(1, math.ceil(len(dias) * fraccion_medida))]
        tabla = tabla[tabla[COLUMNA_FECHA] >= desde].reset_index(drop=True)
    columnas_evento = [c for c in tabla.columns if c.startswith("evento_")]
    por_serie = tabla.groupby(CLAVE_SERIE)[COLUMNA_FECHA].agg(["size", "min", "max"])
    r["tabla"] = {"filas": len(tabla), "series": len(por_serie), "dias_por_serie_min": int(por_serie["size"].min()),
                  "dias_por_serie_max": int(por_serie["size"].max()), "desde": tabla[COLUMNA_FECHA].min(),
                  "hasta": tabla[COLUMNA_FECHA].max(), "filas_fuera_del_error": int(tabla[COLUMNA_FUERA].sum())}

    # Los cortes: los de pliegues_por_dia, que tienen que ser los del modelo mínimo (petición, punto 2)
    pliegues, origenes_minimo = {}, {}
    for objetivo in objetivos:
        pliegues[objetivo] = pr.pliegues_por_dia(tabla[COLUMNA_FECHA], PLIEGUES, HORIZONTE[objetivo])
        origenes_minimo[objetivo] = [p["origen"] for p in minimo["modelo_minimo"][objetivo]["pliegues"]]
        propios = [f"{p['origen']:%Y-%m-%d}" for p in pliegues[objetivo]]
        if not medir_solo and propios != [str(o)[:10] for o in origenes_minimo[objetivo]]:
            r["resultado"] = {"estado": "PARADO", "riesgo": "alto",
                              "resumen": f"los cortes de {objetivo} no son los del modelo mínimo: {propios} frente a "
                                         f"{origenes_minimo[objetivo]}",
                              "artefactos": [JSON_REL, MD_REL], "siguiente": "revisar la tabla de entrenamiento"}
            return r, None

    r["rama"] = "prevision"
    r["aprobado_antes"] = {
        "medida_principal": "error de la previsión: unidades (o dólares) que falla por cada 100 vendidas, de las 70 "
                            "series juntas y todos los días del corte, sin el 25 de diciembre, con el sesgo al lado",
        "algoritmos_y_busqueda": "HistGradientBoosting y Ridge; nivel equilibrado; 15 candidatos al azar en "
                                 "HistGradientBoosting y la rejilla entera de Ridge; 5 cortes por fecha; medida en "
                                 "recursivo; los 25 de diciembre entran en el ajuste y salen de la medida",
        "aprobado_por": "el responsable del caso, 24/11/2026, «Sí, tal cual»",
        "fuente": "config/metodo/04_planteamientos.md §2; informes/modelado_propuesta.md; "
                  "config/negocio/reglas-negocio.md §6 y §7"}
    r["validacion_cruzada"] = {
        "tipo": "TimeSeriesSplit sobre los días, sin barajar, ventana creciente; los cortes del modelo mínimo",
        "pliegues": PLIEGUES, "semilla": SEMILLA, "grupo": None,
        "test_size": {o: HORIZONTE[o] for o in objetivos}, "gap": None,
        "origenes": {o: [p["origen"] for p in pliegues[o]] for o in objetivos}, "objetivo_sin_conocer": []}
    r["desequilibrio"] = {"regla": None, "por_que": "no aplica: los dos objetivos son cantidades"}
    r["teoria_aplicada"] = TEORIA

    # Las búsquedas y el ganador de cada objetivo
    todos_resultados, todos_controles, busquedas = [], [], {}
    r["ranking"], r["referencias_cv"] = [], []
    r["comparacion"], r["eleccion"], r["ganador"], r["importancias"] = {}, {}, {}, {}
    r["distancia"], r["regla_simple"], r["canario"] = {}, {}, {}
    reproducibles = []
    inicio = time.perf_counter()
    for objetivo in objetivos:
        b = buscar_objetivo(tabla, objetivo, preseleccion, rejillas, columnas_evento, pliegues[objetivo], limite,
                            ampliar=not medir_solo)
        busquedas[objetivo] = b
        todos_resultados += b["resultados"]
        todos_controles += b["controles"]
        r["ranking"] += b["ranking"]
        r["referencias_cv"] += b["referencias_cv"]
        r["comparacion"][objetivo] = b["eleccion"]["comparacion"]
        r["eleccion"][objetivo] = {k: v for k, v in b["eleccion"].items() if k != "comparacion"}
        g, imp, dist, simple, pajaro, repro = ganador_objetivo(tabla, objetivo, preseleccion, columnas_evento,
                                                               pliegues[objetivo], b)
        r["ganador"][objetivo], r["importancias"][objetivo], r["distancia"][objetivo] = g, imp, dist
        r["regla_simple"][objetivo], r["canario"][objetivo] = simple, pajaro
        reproducibles.append(repro)
        for p in pliegues[objetivo]:
            r["validacion_cruzada"]["objetivo_sin_conocer"].append(
                {"objetivo": objetivo, "entrenamiento": f"corte que mide desde {p['dias_prueba'].min():%Y-%m-%d}",
                 "conocido_desde": p["dias_prueba"].min(), "filas_quitadas": int(
                     sum(c["filas_ajuste_sin_conocer"] for c in b["controles"] if c["comprobacion"]["prueba_desde"]
                         == p["dias_prueba"].min())), "eventos_quitados": None})
        r["validacion_cruzada"]["objetivo_sin_conocer"].append(
            {"objetivo": objetivo, "entrenamiento": "ajuste final", "conocido_desde": None, "filas_quitadas": 0,
             "eventos_quitados": None})
    segundos_busqueda = time.perf_counter() - inicio

    # La búsqueda, con su espacio, lo que se amplió y lo que costó
    ampliaciones = [a for o in objetivos for a in busquedas[o]["ampliaciones"]]
    modelos_busqueda = sum(len(x["por_corte"]) for x in todos_resultados)
    r["busqueda"] = {
        "nivel": "equilibrado", "tipo": {a: CANDIDATOS[a] and "aleatoria" or "rejilla" for a in ALGORITMOS},
        "candidatos": CANDIDATOS, "semilla_del_muestreo": SEMILLA,
        "medida": "error de reglas, apartado 6 en recursivo desde el origen de cada corte; gana la menor media",
        "tabla": CSV_REL, "rejillas": rejillas, "espacio": [e for o in objetivos for e in busquedas[o]["espacio"]],
        "rejillas_ampliadas": ampliaciones,
        "segundas_busquedas": [s for o in objetivos for s in busquedas[o]["segundas"]],
        "regla_de_ampliacion": "un paso más de la progresión de la rejilla por el lado del borde (con dos valores "
                               "positivos, la misma proporción; si no, la misma diferencia; los enteros, redondeados), "
                               "probado con el resto de la receta del mejor candidato; un rango plano se amplía por los "
                               "dos lados; una sola vez (método, apartado 5; manual 32.5 y 32.6, que no fijan cuánto)",
        "rango_plano": "el mejor valor y el peor, con el error medio por corte de sus candidatos, empatan pliegue a "
                       "pliegue (§6)",
        "modelos_de_la_busqueda": modelos_busqueda,
        "modelos_por_objetivo_y_algoritmo": {f"{o}/{a}": sum(len(x["por_corte"]) for x in todos_resultados
                                                             if x["objetivo"] == o and x["algoritmo"] == a)
                                             for o in objetivos for a in ALGORITMOS},
        "modelos_extra": {"reajuste_del_ganador": len(objetivos), "regla_simple": PLIEGUES * len(objetivos),
                          "canario": 2 * len(objetivos), "reproducible": len(objetivos)},
        "segundos": segundos_busqueda}

    # Las validaciones del §9 que aplican, calculadas con lo ejecutado
    fuera = {f["variable"] for f in preparacion.get("fuera", [])}
    entradas = {c for o in objetivos for c in columnas_entrada(o, columnas_evento)}
    citas = [PRESELECCION_REL, PREPARACION_REL, MODELO_MINIMO_REL] + list(FICHAS.values())
    huella_despues = huella(raiz / ENTRENAMIENTO_REL)
    bordes_por = [(busquedas[o]["bordes"][a], [x for x in ampliaciones if x["objetivo"] == o and x["algoritmo"] == a])
                  for o in objetivos for a in ALGORITMOS]
    mismos = all(f["origenes"] == [p["origen"] for p in pliegues[f["objetivo"]]] for f in r["ranking"]) and all(
        x["origenes"] == [p["origen"] for p in pliegues[x["objetivo"]]] for x in todos_resultados)
    del_minimo = None if medir_solo else all(
        [f"{p['origen']:%Y-%m-%d}" for p in pliegues[o]] == [str(x)[:10] for x in origenes_minimo[o]]
        for o in objetivos)
    v = {}
    v["sin_filas_de_ajuste"] = all(c["sin_filas_de_ajuste"] for c in todos_controles)
    v["semillas"] = all(c["semilla"] == SEMILLA for c in todos_controles) and all(
        g["semilla"] == SEMILLA and g["hiperparametros"].get("random_state") == SEMILLA for g in r["ganador"].values())
    v["validacion_sin_abrir"] = validacion_sin_abrir(abiertas)
    v["columnas_de_preseleccion"] = all(
        g["columnas"] == columnas_modelo(preseleccion, o, g["algoritmo"]) and len(g["columnas"]) > 0
        for o, g in r["ganador"].items())
    v["citas_existen"] = all((raiz / c).exists() for c in citas)
    v["reproducible"] = all(reproducibles)
    v["sin_identificadores_ni_posteriores"] = not (entradas & fuera) and not any(
        grupo_de(c) in fuera for g in r["ganador"].values() for c in g["columnas"])
    v["sin_resultados_escritos"] = buscar_resultados_escritos(Path(__file__).read_text(encoding="utf-8")) == []
    v["objetivo_conocido_al_entrenar"] = all(c["filas_ajuste_sin_conocer"] == 0 for c in todos_controles)
    v["pliegues_por_fecha"] = all(c["comprobacion"]["bien"] for c in todos_controles)
    v["mismos_cortes"] = mismos and del_minimo is not False
    v["medido_en_recursiva"] = all(c["medido_en_recursiva"] for c in todos_controles)
    v["recursiva_completa_sin_negativas"] = all(c["recursiva_completa"] and c["recursiva_sin_negativas"]
                                                for c in todos_controles)
    v["recursiva_a_un_dia_igual"] = all(c["recursiva_a_un_dia_igual"] for c in todos_controles)
    v["bordes_ampliados"] = None if medir_solo else all(bordes_ampliados(b, a) for b, a in bordes_por)
    v["empate_pliegue_a_pliegue"] = all(len(c["diferencias"]) == PLIEGUES and c["metodo"] == "pliegue a pliegue"
                                        for c in r["comparacion"].values())
    v["canario_objetivo_barajado"] = all(c["barajado_pierde_la_senal"] and c["fuga_se_ve"]
                                         for c in r["canario"].values())
    v["entrada_sin_cambiar"] = huella_despues == huella_antes
    for nombre in ("con_probabilidad", "recalibrado_si_hace_falta", "probabilidad_media_cerca_de_la_tasa",
                   "intervalo_por_entidad"):
        v[nombre] = None
    v["rotulos_de_filas"] = rotulos_de_filas(r) == []
    r["validaciones"] = v
    r["validaciones_nulas"] = {
        "con_probabilidad": "no aplica: objetivo de cantidad", "recalibrado_si_hace_falta": "no aplica: sin equilibrar",
        "probabilidad_media_cerca_de_la_tasa": "no aplica: objetivo de cantidad",
        "intervalo_por_entidad": "va con la validación (planteamientos §2, decisión 3)",
        "bordes_ampliados": "solo en la medida de tiempo, que no amplía" if medir_solo else None}
    r["cortes_del_modelo_minimo"] = {"iguales": del_minimo, "origenes": origenes_minimo}
    r["tablas_abiertas"] = abiertas
    r["huella_entrada_despues"] = huella_despues
    r["fichas"] = {a: {"ruta": ruta, "existe": (raiz / ruta).exists()} for a, ruta in FICHAS.items()}
    r["parametros"] = [
        {"nombre": "semilla", "valor": SEMILLA, "origen": "preparacion-modelo; parametros.md; petición"},
        {"nombre": "pliegues", "valor": f"TimeSeriesSplit({PLIEGUES}) sobre los días, test_size 10 y 28",
         "origen": "parametros.md; método, apartado 3; los cortes del modelo mínimo"},
        {"nombre": "candidatos", "valor": CANDIDATOS, "origen": "planteamientos §2, nivel equilibrado"},
        {"nombre": "parada temprana", "valor": False, "origen": "método, apartado 5: con fecha, early_stopping=False"},
        {"nombre": "repeticiones de la permutación", "valor": REPETICIONES, "origen": "parametros.md"},
        {"nombre": "desviación entre cortes", "valor": f"ddof={DDOF}", "origen": "manual 3.6"},
        {"nombre": "límite del canario de la fuga", "valor": LIMITE_FUGA, "origen": "reglas, apartado 7, «Lo esperable»"},
        {"nombre": "días fuera del error", "valor": "dentro del ajuste; fuera de la medida",
         "origen": "reglas, apartado 6; planteamientos §2, «Algoritmos y búsqueda»"}]

    bien = all(x for x in v.values() if x is not None)
    if medir_solo:
        r["estimacion"] = estimar(todos_resultados, fraccion_medida, rejillas)
    t = tabla_probada(todos_resultados)
    resumen = "; ".join(f"{o}: {r['ganador'][o]['algoritmo']} con {next(f['cv_media'] for f in r['ranking'] if f['objetivo'] == o and f['algoritmo'] == r['ganador'][o]['algoritmo']):.2f} en recursivo"
                        for o in objetivos)
    contadas = sum(x is not None for x in v.values())
    if bien:
        r["puerta_de_juan"] = True
        r["pendientes"] = [{"id": "P-01", "tabla": "modelado", "columna": "ganador de cada objetivo",
                            "pregunta": "¿Apruebas el ganador de cada objetivo con su receta antes de abrir la "
                                        "validación? Puerta del responsable del caso (método, apartado 7 y §8)",
                            "opciones": ["aprobar la propuesta de informes/busqueda_propuesta.md", "otra decisión"]}]
        r["resultado"] = {"estado": "PARADO", "riesgo": "medio",
                          "resumen": f"{resumen}; {contadas} de {contadas} validaciones en verde; el ganador espera "
                                     f"al responsable del caso", "artefactos": artefactos,
                          "siguiente": "El responsable del caso aprueba el ganador de cada objetivo; después, la validación una vez"}
    else:
        falsas = [k for k, x in v.items() if x is False]
        r["resultado"] = {"estado": "ERROR", "riesgo": "alto",
                          "resumen": f"{resumen}; validaciones en rojo: {falsas}", "artefactos": artefactos,
                          "siguiente": "revisar las validaciones en rojo antes de proponer nada"}
    return r, t


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", type=Path, default=CASO)
    argumentos.add_argument("--medir", type=float, default=None,
                            help="fracción más reciente de los días con que se mide el tiempo; no escribe nada")
    argumentos.add_argument("--candidatos", type=int, default=1, help="con --medir, candidatos por algoritmo")
    argumentos.add_argument("--objetivos", nargs="+", choices=OBJETIVOS, default=list(OBJETIVOS),
                            help="con --medir, qué objetivos se miden")
    args = argumentos.parse_args()
    raiz = args.raiz.resolve()
    if args.medir is not None:
        inicio = time.perf_counter()
        medido, _ = principal(raiz, fraccion_medida=args.medir, limite=args.candidatos,
                              objetivos=tuple(args.objetivos))
        segundos = time.perf_counter() - inicio
        print(f"MEDIDA · {medido['resultado']['estado']} · {medido.get('tabla', {}).get('filas')} filas, "
              f"{args.candidatos} candidato(s) por algoritmo, objetivos {args.objetivos}, en {segundos:.1f} s")
        print(f"validaciones en rojo: {[k for k, x in medido.get('validaciones', {}).items() if x is False]}")
        total = 0.0
        for e in medido.get("estimacion", []):
            total += e["segundos"]
            print(f"estimación · {e['objetivo']} · {e['algoritmo']}: {e['candidatos']} candidatos × {PLIEGUES} cortes "
                  f"× {e['segundos_por_corte']:.1f} s = {e['segundos'] / 60:.1f} min")
        print(f"estimación de la búsqueda de estos objetivos sin ampliaciones ni extras: {total / 60:.1f} min")
        sys.exit(0 if medido["resultado"]["estado"] in ("OK", "AVISO") or medido.get("puerta_de_juan") else 1)
    tabla_csv = None
    try:
        resultado, tabla_csv = principal(raiz)
    except Exception:
        resultado = {"metodo": "aprendizaje-automatico", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                     "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "entorno": entorno(),
                     "puerta_de_juan": False,
                     "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": traceback.format_exc()[-1500:],
                                   "artefactos": [JSON_REL], "siguiente": "corregir el fallo técnico"},
                     "pendientes": []}
    limpio = a_json_limpio(resultado)
    (raiz / JSON_REL).write_text(json.dumps(limpio, ensure_ascii=False, indent=2), encoding="utf-8")
    if tabla_csv is not None:
        tabla_csv.to_csv(raiz / CSV_REL, index=False, encoding="utf-8")
    (raiz / MD_REL).write_text(propuesta_md(limpio), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado["resultado"]["estado"] in ("OK", "AVISO") or resultado.get("puerta_de_juan") else 1)
