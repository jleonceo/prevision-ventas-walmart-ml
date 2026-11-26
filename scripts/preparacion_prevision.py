"""El preprocesador de los dos modelos de previsión del caso 69, sin ajustar.

Módulo de funciones, sin nada que se ejecute al importarlo (programacion-del-caso, error 1). Lo usan
scripts/12_preparacion.py, que lo comprueba con sus nueve validaciones, y scripts/13_preseleccion.py, que lo ajusta con
el entrenamiento para preseleccionar; después lo usará aprendizaje-automatico. Pasó aquí desde scripts/12_preparacion.py
sin cambiar su comportamiento.

Construye con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 (config/modelo/
matriz_transformaciones.md) un ColumnTransformer dentro de un Pipeline (método preparacion-modelo, apartado 4). Es un solo
preprocesador para HistGradientBoosting y Ridge; las variables de los dos objetivos van por separado: el modelo de
unidades usa las de unidades y el de dólares las de dólares, las demás las dos.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler, StandardScaler

# Los dos objetivos (matriz, «Lo que ya estaba fijado»)
OBJETIVOS = ("unidades", "dolares")

# Las ramas de la matriz aprobada, columna a columna (la lista de entrada se escribe a mano, preparacion-modelo §4)
OHE_COLUMNAS = ["store_id", "dept_id", "weekday", "month"]
EVENTO_COLUMNAS = ["event_name_1", "event_name_2"]
RELLENO_EVENTO = "sin evento"   # el vacío significa «día sin evento» (reglas, apartado 5); no existe con otro significado
SS_COLUMNAS = ["precio_medio_semana_anterior", "productos_con_precio_semana_anterior", "dia_del_mes"]
PASA_FIJAS = ["snap"]           # binaria, tal cual; las evento_<nombre> se añaden con su lista
DROP_MATRIZ = None              # sin drop: k columnas por categórica
MIN_FRECUENCIA = 30             # preparacion-modelo/parametros.md, «mínimo para no agrupar una categoría»
RETARDOS = (1, 2, 3, 4, 5, 6, 7, 14, 21, 28)
VENTANAS = (7, 28)


# ══ 2. Nombres de las columnas ══════════════════════════════════════════════════
def nombres_rs(objetivo):
    """Las 12 variables de la historia del objetivo, que llevan RobustScaler (matriz: colas sin tratar)."""
    return [f"{objetivo}_lag_{k}" for k in RETARDOS] + [f"{objetivo}_media_{w}" for w in VENTANAS]


def combinar_categoria(columna, categoria):
    """Nombre de una columna de una codificación: <variable>_ohe_<categoría> (catálogo, sufijos)."""
    return f"{columna}_ohe_{categoria}"


def nombre_salida(transformador, columna):
    """Nombre de salida con el sufijo de su rama: _rs, _ss; las codificaciones y lo que pasa tal cual, sin sufijo."""
    if transformador.startswith("ohe") or transformador == "pasa":
        return columna
    return f"{columna}_{transformador}"


def columnas_entrada(objetivo, columnas_evento):
    """Las columnas que entran al preprocesador de un objetivo, escritas por nombre."""
    return OHE_COLUMNAS + EVENTO_COLUMNAS + PASA_FIJAS + list(columnas_evento) + SS_COLUMNAS + nombres_rs(objetivo)


# ══ 3. El preprocesador (preparacion-modelo §4) ═════════════════════════════════
def construir_preprocesador(objetivo, columnas_evento):
    """El ColumnTransformer de la matriz aprobada dentro de un Pipeline, sin ajustar.

    objetivo: «unidades» o «dolares»; decide qué historia entra. columnas_evento: las evento_<nombre> de la lista del
    entrenamiento (informes/variables_modelo.json). Cada llamada crea objetos nuevos (manual 39.5).
    """
    if objetivo not in OBJETIVOS:
        raise ValueError(f"objetivo desconocido: {objetivo}")
    eventos = Pipeline([("vacio", SimpleImputer(strategy="constant", fill_value=RELLENO_EVENTO)),
                        ("columnas", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=MIN_FRECUENCIA,
                                                   sparse_output=False, drop=DROP_MATRIZ,
                                                   feature_name_combiner=combinar_categoria))])
    preparacion = ColumnTransformer(
        [("ohe", OneHotEncoder(sparse_output=False, drop=DROP_MATRIZ, feature_name_combiner=combinar_categoria),
          OHE_COLUMNAS),
         ("ohe_eventos", eventos, EVENTO_COLUMNAS),
         ("pasa", "passthrough", PASA_FIJAS + list(columnas_evento)),
         ("ss", StandardScaler(), SS_COLUMNAS),
         ("rs", RobustScaler(), nombres_rs(objetivo))],
        remainder="drop", verbose_feature_names_out=nombre_salida).set_output(transform="pandas")
    return Pipeline([("preparacion", preparacion)])
