"""Validación del ganador del caso 69: medido una vez, en recursivo desde 13 orígenes, frente a las tres reglas.

Aplica el método aprendizaje-automatico, apartado 8 a §10 con el ganador que el responsable del caso aprobó el 25/11/2026 («Apruebo el ganador»; config/metodo/04_planteamientos.md §2, «Ganador»). Lo que hace, en este orden:
  1. lee la receta de cada objetivo de informes/busqueda.json («ganador»), con su huella comprobada contra la que tenía
     al empezar este paso, y la aprobación escrita en los planteamientos;
  2. ajusta cada ganador una vez con las filas de data/processed/hechos_modelo_entrenamiento.parquet, con el
     preprocesador de scripts/preparacion_prevision.py, como scripts/15_busqueda.py; no se reajusta con la validación
     (planteamientos §2, decisión 2). Solo después carga las tablas de validación (validación 3);
  3. desde 13 orígenes, cada 28 días del 22/05/2014 al 23/04/2015 (decisión 1), prevé con
     prevision_recursiva.prever_recursivo: unidades a 10 días y dólares a 28; la historia es la venta real hasta el
     origen, de entrenamiento y de validación; el futuro, las filas de validación del horizonte;
  4. en las mismas series, días y orígenes: las tres reglas (prevision_recursiva.reglas_sencillas), el trivial (la
     mediana del ajuste, como en la búsqueda) y el suavizado exponencial de la decisión 8 (statsmodels,
     ExponentialSmoothing aditivo semanal sin tendencia, ajustado en cada serie con toda su venta hasta el origen);
  5. el error y el sesgo de reglas, apartado 6 (unidades redondeadas al medir; el 25 de diciembre fuera) por origen,
     departamento, tienda, día del horizonte, mes completo, días con evento y días SNAP, y el sesgo en los días a cero;
  6. el veredicto de reglas, apartado 7: orígenes que gana frente a la regla que menos falla en cada uno (10 de 13) y el
     intervalo del 95 % de la ventaja remuestreando las 70 series enteras (decisión 3); el suavizado, al lado y con
     las mismas pruebas, como lectura; la recomendación de cada departamento; y lo que matiza la ventaja (el responsable del caso,
     25/11/2026, «Sí, amplíalo»), con las mismas sumas y filas medidas: el aporte de cada serie, la ventaja
     sin cada tienda y sin WI_2 y WI_3, el intervalo por tiendas enteras, las series en que alguna regla falla menos,
     los eventos del calendario que caen en días medidos y las filas de cada día de la semana;
  6.2 la previsión sumada (el responsable del caso, 25/11/2026, «Apruebo el guion»; ficha, pregunta 3): con las mismas filas
     medidas, la suma de abajo arriba por cadena, estado, tienda y categoría (data/processed/dim_producto.parquet y
     dim_tienda.parquet), con el error y el sesgo de cada nivel frente a las tres reglas y el suavizado;
  7. lo demás del §8 con assets/evaluacion_continua.py sin cambiarla: medidas en las mismas filas, error por tramos,
     desarrollo frente a validación y el MASE; las validaciones del §9.
Para en la puerta del responsable del caso: el veredicto se aprueba antes del informe.

No abre nada de la prueba final (después del 22/05/2015) ni escribe en tests/ ni en config/.

Depende de los scripts 10 a 15 (error 2): las huellas de las tablas se comprueban contra informes/preparacion.json,
informes/particion.json e informes/busqueda.json.

Deja informes/validacion.json, informes/validacion_por_origen.csv, data/processed/previsiones_validacion.parquet e
informes/validacion_resultado.md, este generado del JSON.

Uso: python -W error scripts/16_validacion.py [--raiz CARPETA] [--huella-receta SHA256]
     python -W error scripts/16_validacion.py --muestra-origenes 2 --muestra-series 7
Con --muestra-* ejecuta todo con los primeros orígenes y las primeras series, imprime el tiempo y la estimación para la
ejecución entera y no escribe nada. Sale con 0 si para en la puerta del responsable del caso con todo en verde y con 1 si no.
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
import statsmodels
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# Los módulos del caso, que no ejecutan nada al importarse (error 1), y la pieza común de evaluación
CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
sys.path.insert(0, str(CASO / "assets"))
from preparacion_prevision import columnas_entrada, construir_preprocesador  # noqa: E402
import prevision_recursiva as pr  # noqa: E402
import variables_prevision as vp  # noqa: E402
import evaluacion_continua as ec  # noqa: E402

VERSION_METODO = "20/11/2026"  # versión del método aprendizaje-automatico con que se escribió este script
PIEZA_CASO = CASO / "assets" / "evaluacion_continua.py"
PIEZA_COMUN = CASO / "assets" / "evaluacion_continua.py"
SCRIPT_REL = "scripts/16_validacion.py"
FECHA_DATOS = "2015-05-22"
BUSQUEDA_REL = "informes/busqueda.json"
PRESELECCION_REL = "informes/preseleccion.json"
PREPARACION_REL = "informes/preparacion.json"
PARTICION_REL = "informes/particion.json"
PLANTEAMIENTOS_REL = "config/metodo/04_planteamientos.md"
PIEZA_REL = "assets/evaluacion_continua.py"
MODELO_ENT_REL = "data/processed/hechos_modelo_entrenamiento.parquet"
MODELO_VAL_REL = "data/processed/hechos_modelo_validacion.parquet"
SERIES_ENT_REL = "data/processed/hechos_series_entrenamiento.parquet"
SERIES_VAL_REL = "data/processed/hechos_series_validacion.parquet"
JSON_REL = "informes/validacion.json"
CSV_REL = "informes/validacion_por_origen.csv"
PARQUET_REL = "data/processed/previsiones_validacion.parquet"
MD_REL = "informes/validacion_resultado.md"
PROTECCION_REL = "config/fuentes/proteccion-datos.json"
CALENDARIO_REL = "data/processed/calendario_corregido.parquet"

# La huella de informes/busqueda.json al empezar este paso (25/11/2026), contra la que se comprueba la receta
HUELLA_RECETA = "91b008c091be5060fdf8c78ab453360e86a4303718a9e14428e0da8c80fe47f5"
# Planteamientos §2, «Ganador»: la aprobación del responsable del caso, que el script busca escrita en los planteamientos
APROBADO_POR = "el responsable del caso, 25/11/2026, «Apruebo el ganador»"
TEXTO_APROBACION = ("«Apruebo el ganador»",)

COLUMNA_FECHA = "date"
CLAVE_SERIE = ["store_id", "dept_id"]
CLAVES = CLAVE_SERIE + [COLUMNA_FECHA]
COLUMNA_FUERA = "fuera_del_error"
COLUMNA_FUGA = "fuga_canario"
# Reglas, apartado 5 y planteamientos §2: el horizonte de cada objetivo
HORIZONTE = {"unidades": 10, "dolares": 28}
OBJETIVOS = tuple(HORIZONTE)
# Planteamientos §2, decisión 1: 13 orígenes cada 28 días, el primero el último día de la construcción
PRIMER_ORIGEN = pd.Timestamp("2014-05-22")
N_ORIGENES = 13
PASO_ORIGENES = 28
# Reglas, apartado 7, «Qué cuenta como mejora»: el 75 % de los orígenes, hacia arriba
PROPORCION_ORIGENES = 0.75
# Planteamientos §2, decisión 3: remuestreos, semilla y percentiles del intervalo
REMUESTREOS = 1000
SEMILLA = 42
PERCENTILES = (2.5, 97.5)
# Reglas, apartado 7, «Lo esperable»: un error de menos de 5 apunta a que la previsión usa el futuro; una ventaja de más de 15
# se revisa
LIMITE_FUGA = 5.0
LIMITE_VENTAJA = 15.0
# Guía de evaluación continua §7: el error por tramos del valor real
TRAMOS = 5
# El responsable del caso, 24/11/2026 (reglas, apartado 7, «Preselección de variables»): fuera event_name_1 y event_name_2
FUERA_PREFIJOS = ("event_name_1_ohe_", "event_name_2_ohe_")
NO_SE_ABRE = re.compile(r"prueba|produccion")
PREDICTORES = ("modelo",) + pr.REGLAS + ("trivial", "suavizado")
NOMBRE = {"modelo": "el modelo", "repetir_semana_anterior": "repetir la semana anterior",
          "media_28_dias": "la media de los últimos 28 días",
          "media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores",
          "trivial": "el trivial (la mediana)", "suavizado": "el suavizado exponencial"}
NOMBRES_VALIDACION = (
    "sin_filas_de_ajuste", "semillas", "validacion_una_vez", "con_probabilidad", "columnas_de_preseleccion",
    "recalibrado_si_hace_falta", "citas_existen", "reproducible", "sin_identificadores_ni_posteriores",
    "sin_resultados_escritos", "canario_objetivo_barajado", "probabilidad_media_cerca_de_la_tasa",
    "objetivo_conocido_al_entrenar", "recursiva_completa_sin_negativas", "intervalo_por_entidad",
    "origenes_bien", "sin_prueba_final", "mismas_filas", "ventaja_con_la_regla_de_cada_origen",
    "sin_dias_fuera_del_error", "sin_meses_parciales", "suavizado_sin_futuro", "dias_previstos_por_serie",
    "reglas_primer_origen_a_mano", "historia_igual_en_las_dos_tablas", "receta_reproducida",
    "pieza_igual_a_la_comun", "tablas_como_la_particion", "rotulos_de_filas", "entradas_sin_cambiar")
# Lo que matiza la ventaja (el responsable del caso, 25/11/2026, «Sí, amplíalo»; auditor del cierre del modelado): son
# lecturas sobre las mismas previsiones y filas que el veredicto, que no cambian
SERIES_QUE_MAS_APORTAN = 5
# Las tiendas que se quitan juntas, las que señaló el auditor; cada tienda sola se quita también
QUITAR_JUNTAS = ("WI_2", "WI_3")
DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
NOMBRES_COMPROBACION_ROBUSTEZ = ("aporte_suma_la_ventaja", "intervalo_por_tienda_entera",
                                 "eventos_solo_en_dias_medidos", "dias_de_la_semana_suman_las_filas")
# La previsión sumada (pregunta 3 de la ficha; el responsable del caso, 25/11/2026, «Apruebo el guion»): reglas, apartado 4, «Cómo cuadran
# los niveles», de abajo arriba. Los niveles, de lo general a lo concreto; las previsiones que se suman y se miden
DIM_PRODUCTO_REL = "data/processed/dim_producto.parquet"
DIM_TIENDA_REL = "data/processed/dim_tienda.parquet"
NIVELES = ("cadena", "estado", "tienda", "categoria")
PREDICTORES_NIVELES = ("modelo",) + pr.REGLAS + ("suavizado",)
NOMBRES_COMPROBACION_NIVELES = ("un_padre_por_hijo", "grupos_completos", "sumas_cuadran",
                                "cadena_igual_a_las_series_sumadas")

TEORIA = [
    {"apartado": "31.7", "por_que": "previsión de varios periodos: se mide recursiva, como se usará, al horizonte "
                                    "entero"},
    {"apartado": "31.9", "por_que": "WAPE con el sesgo aparte, la referencia ingenua, el error por horizonte y "
                                    "entrenamiento frente a validación"},
    {"apartado": "18.3", "por_que": "la cifra se lee contra las referencias, en las mismas filas"},
    {"apartado": "19.3", "por_que": "desarrollo frente a validación, sin vara fija"},
    {"apartado": "4.6", "por_que": "el intervalo del 95 % de la ventaja"},
    {"apartado": "5.3", "por_que": "bootstrap por grupos y pareado: se remuestrean las series enteras y la ventaja "
                                   "se calcula en cada remuestreo con las mismas series para el modelo y las reglas"},
    {"apartado": "5.1", "por_que": "las tres vías de mejora, si el modelo no gana"}]
# La teoría de la previsión sumada va dentro de su bloque, para no cambiar nada de lo que ya estaba en el JSON
TEORIA_NIVELES = [{"apartado": "31.8", "por_que": "la previsión sumada se reconcilia de abajo arriba: se suman las "
                                                  "series y cada nivel se mide con sus filas sumadas"},
                  {"apartado": "31.9", "por_que": "el error de cada nivel con su sesgo aparte, frente a las reglas"}]


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
    if isinstance(obj, np.ndarray):
        return [a_json_limpio(v) for v in obj.tolist()]
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
            "pyarrow": pyarrow.__version__, "scikit-learn": sklearn.__version__,
            "statsmodels": statsmodels.__version__, "ejecutable": sys.executable}


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def buscar_resultados_escritos(texto):
    """Las validaciones escritas con su resultado puesto (True o False) en un texto de código (error 24)."""
    nombres = "|".join(NOMBRES_VALIDACION + NOMBRES_COMPROBACION_ROBUSTEZ + NOMBRES_COMPROBACION_NIVELES)
    patron = rf"[\"']({nombres})[\"']\s*(?:\]\s*=|:)\s*\(?\s*(?:True|False)\b"
    return re.findall(patron, texto)


def leer_json(raiz, rel):
    """Un JSON del caso, o None si no existe."""
    ruta = raiz / rel
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def rotulos_de_filas(nodo, camino=""):
    """Las cifras del JSON con el rótulo de filas mal puesto (resultado.md; validación 1).

    Una cifra es un diccionario con «error». Bajo una clave «entrenamiento» tiene que decir que sus filas son de
    entrenamiento; en cualquier otro sitio, que son de validación. Sin «filas», también está mal.
    """
    malas = []
    if isinstance(nodo, dict):
        if "error" in nodo:
            filas = str(nodo.get("filas", ""))
            de_entrenamiento = "entrenamiento" in camino.rsplit("/", 1)[-1]
            if de_entrenamiento and not filas.startswith("entrenamiento"):
                malas.append(camino)
            elif not de_entrenamiento and not filas.startswith("validacion"):
                malas.append(camino)
        for k, v in nodo.items():
            malas += rotulos_de_filas(v, f"{camino}/{k}")
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            malas += rotulos_de_filas(v, f"{camino}[{i}]")
    return malas


def miles(n):
    """Un entero con punto de millar, como se escribe en español."""
    return f"{int(n):,}".replace(",", ".")


def num(x, decimales=1, signo=False):
    """Una cifra con coma decimal, como se escribe en español; con signo si se pide."""
    if x is None:
        return "sin cifra"
    texto = f"{x:+.{decimales}f}" if signo else f"{x:.{decimales}f}"
    return texto.replace(".", ",")


# ══ 3. La receta y el orden de lectura (validación 3) ════════════════════════════
def leer_receta(raiz, huella_esperada):
    """La receta del ganador de cada objetivo, con su huella comprobada y la aprobación escrita en los planteamientos.

    Devuelve (receta, paradas, huellas). Para si la huella no es la esperada, si falta el ganador de un objetivo o
    alguna pieza de su receta, o si la aprobación no está escrita.
    """
    ruta = raiz / BUSQUEDA_REL
    if not ruta.exists():
        return None, [f"falta {BUSQUEDA_REL}"], {"esperada": huella_esperada, "calculada": None}
    calculada = huella(ruta)
    huellas = {"esperada": huella_esperada, "calculada": calculada}
    if calculada != huella_esperada:
        return None, [f"la huella de {BUSQUEDA_REL} no es la esperada: la receta cambió"], huellas
    d = json.loads(ruta.read_text(encoding="utf-8"))
    paradas, receta = [], {}
    for objetivo in OBJETIVOS:
        g = (d.get("ganador") or {}).get(objetivo)
        if not g:
            paradas.append(f"la receta no tiene ganador de {objetivo}")
            continue
        hiper = g.get("hiperparametros") or {}
        if g.get("algoritmo") != "HistGradientBoosting" or not g.get("columnas") or not hiper:
            paradas.append(f"la receta de {objetivo} está incompleta")
        elif hiper.get("random_state") != g.get("semilla") or hiper.get("early_stopping") is not False:
            paradas.append(f"la receta de {objetivo} no lleva su semilla o lleva parada temprana")
        receta[objetivo] = g
    plant = raiz / PLANTEAMIENTOS_REL
    texto = plant.read_text(encoding="utf-8") if plant.exists() else ""
    if not all(t in texto for t in TEXTO_APROBACION):
        paradas.append(f"la aprobación del ganador no está escrita en {PLANTEAMIENTOS_REL}")
    return {"json": d, "ganador": receta}, paradas, huellas


def orden_de_lectura_bien(registro):
    """Verdadero si la receta se leyó antes de cargar ninguna tabla de validación y cada una se cargó una sola vez."""
    pasos = [x["paso"] for x in registro]
    if "receta" not in pasos:
        return False
    primera = pasos.index("receta")
    validaciones = [(i, x["ruta"]) for i, x in enumerate(registro) if x["paso"] == "validacion"]
    rutas = [r for _, r in validaciones]
    return bool(validaciones) and all(i > primera for i, _ in validaciones) and len(rutas) == len(set(rutas))


def cargar(raiz, rel, registro, paso):
    """Lee una tabla Parquet y apunta la lectura en el registro."""
    registro.append({"paso": paso, "ruta": rel})
    return pd.read_parquet(raiz / rel)


# ══ 4. Orígenes, modelo y previsiones ════════════════════════════════════════════
def generar_origenes(primero, n, paso):
    """Los orígenes de la validación: n, cada paso días, desde el primero."""
    return [pd.Timestamp(primero) + pd.Timedelta(paso * i, "D") for i in range(n)]


def comprobar_origenes(origenes, horizontes, dias_validacion):
    """Cada día del horizonte de cada origen está en la validación, y ninguno antes del primero.

    Devuelve bien y, por objetivo, los días que caen fuera.
    """
    validos = set(pd.DatetimeIndex(dias_validacion))
    fuera = {}
    for objetivo, h in horizontes.items():
        dias = [o + pd.Timedelta(k, "D") for o in origenes for k in range(1, h + 1)]
        fuera[objetivo] = [d for d in dias if d not in validos]
    return {"bien": all(not v for v in fuera.values()) and len(origenes) > 0, "dias_fuera": fuera}


def sin_prueba_final(fechas, fecha_datos):
    """Verdadero si ninguna fecha pasa de la fecha de los datos: la prueba final no se abre."""
    return bool(pd.DatetimeIndex(fechas).max() <= pd.Timestamp(fecha_datos))


def entrada_de(objetivo, columnas_evento):
    """Las columnas que entran al preprocesador de un objetivo."""
    return columnas_entrada(objetivo, columnas_evento)


def construir_modelo(objetivo, columnas_evento, columnas, hiperparametros, extra=()):
    """El Pipeline del ganador: el preprocesador del caso, sin ajustar, las columnas de la receta y el boosting con sus
    hiperparámetros. Es el de scripts/15_busqueda.py, que no se importa (error 1). extra: columnas que pasan tal cual;
    solo las usa el canario de la fuga."""
    preparacion = construir_preprocesador(objetivo, columnas_evento)
    if extra:
        preparacion = ColumnTransformer(
            [("preparacion", preparacion, columnas_entrada(objetivo, columnas_evento)),
             ("extra", "passthrough", list(extra))],
            remainder="drop", verbose_feature_names_out=False).set_output(transform="pandas")
    seleccion = ColumnTransformer([("columnas", "passthrough", list(columnas) + list(extra))], remainder="drop",
                                  verbose_feature_names_out=False).set_output(transform="pandas")
    return Pipeline([("preprocesador", preparacion), ("columnas", seleccion),
                     ("modelo", HistGradientBoostingRegressor(**hiperparametros))])


def previsto_medible(valores, objetivo):
    """Acota en cero y, en unidades, redondea al entero (método, apartado 8; reglas, apartado 6)."""
    v = np.clip(np.asarray(valores, dtype="float64"), 0.0, None)
    return pr.redondear_unidades(v) if objetivo == "unidades" else v


def comprobar_recursiva(prevision, n_series, origen, horizonte):
    """Verdadero si la previsión es la recursiva entera desde el origen: cada serie con un día por cada h de 1 al
    horizonte, cada día igual al origen más h. Una previsión a un día no pasa (validación 14)."""
    if not {"h", COLUMNA_FECHA}.issubset(prevision.columns) or len(prevision) != n_series * horizonte:
        return False
    if sorted(prevision["h"].unique().tolist()) != list(range(1, horizonte + 1)):
        return False
    por_serie = prevision.groupby(CLAVE_SERIE)["h"].nunique()
    fechas = pd.to_datetime(prevision[COLUMNA_FECHA])
    esperadas = pd.Timestamp(origen) + pd.to_timedelta(prevision["h"], unit="D")
    return bool(len(por_serie) == n_series and (por_serie == horizonte).all() and (fechas == esperadas).all())


def prever_modelo(modelo, historia, futuro, objetivo, origen, horizonte):
    """El modelo desde un origen con prevision_recursiva.prever_recursivo, la misma función que la ejecución.

    La función corta la historia en el origen y quita del futuro la venta y sus retardos. Devuelve las claves, h y la
    columna modelo, sin redondear.
    """
    rec = pr.prever_recursivo(modelo, historia, futuro, objetivo, horizonte, origen=origen)
    return rec.rename(columns={"prevision": "modelo"})


def prever_suavizado(historia, objetivo, origen, horizonte):
    """El suavizado exponencial de la decisión 8 en cada serie, con toda su venta hasta el origen incluido.

    ExponentialSmoothing con estacionalidad semanal aditiva y sin tendencia; acotado en cero. Corta la historia en el
    origen y para si una serie no llega a él o tiene un día que falta. Devuelve la previsión (claves, h, suavizado) y
    el registro de cada ajuste: primer y último día usados y cuántos.
    """
    origen = pd.Timestamp(origen)
    antes = historia[(historia[COLUMNA_FECHA] <= origen).to_numpy()]
    vp.comprobar_sin_huecos(antes)
    salida, registro = [], []
    for clave, grupo in antes.groupby(CLAVE_SERIE, sort=True):
        grupo = grupo.sort_values(COLUMNA_FECHA)
        if grupo[COLUMNA_FECHA].max() != origen:
            raise ValueError(f"la serie {clave} no llega al origen {origen:%Y-%m-%d}")
        y = grupo[objetivo].to_numpy(dtype="float64")
        ajuste = ExponentialSmoothing(y, trend=None, damped_trend=False, seasonal="add", seasonal_periods=7,
                                      initialization_method="estimated", use_boxcox=False).fit()
        previsto = np.clip(np.asarray(ajuste.forecast(horizonte), dtype="float64"), 0.0, None)
        dias = [origen + pd.Timedelta(h, "D") for h in range(1, horizonte + 1)]
        salida.append(pd.DataFrame({CLAVE_SERIE[0]: clave[0], CLAVE_SERIE[1]: clave[1], COLUMNA_FECHA: dias,
                                    "h": range(1, horizonte + 1), "suavizado": previsto}))
        registro.append({"store_id": clave[0], "dept_id": clave[1], "primer_dia": grupo[COLUMNA_FECHA].min(),
                         "ultimo_dia": grupo[COLUMNA_FECHA].max(), "dias": len(y)})
    tabla = pd.concat(salida, ignore_index=True)
    tabla[COLUMNA_FECHA] = tabla[COLUMNA_FECHA].astype(historia[COLUMNA_FECHA].dtype)
    return tabla, registro


def suavizado_sin_futuro(registro, origen):
    """Verdadero si cada ajuste del suavizado acaba en el origen y usa todos los días desde el primero."""
    origen = pd.Timestamp(origen)
    return bool(registro) and all(
        pd.Timestamp(x["ultimo_dia"]) == origen
        and x["dias"] == (pd.Timestamp(x["ultimo_dia"]) - pd.Timestamp(x["primer_dia"])).days + 1 for x in registro)


def unir_previsiones(base, previsiones):
    """Une a las filas del horizonte cada previsión, que tiene que traer exactamente las mismas series y días.

    base: las filas de validación del horizonte, con las claves. previsiones: {nombre: tabla con las claves}. Para si
    una previsión tiene otros días, alguno de menos o repetido: una regla solo se compara en los días del modelo.
    """
    if base[CLAVES].duplicated().any():
        raise ValueError("las filas del horizonte tienen claves repetidas")
    salida = base.copy()
    for nombre, tabla in previsiones.items():
        if tabla[CLAVES].duplicated().any():
            raise ValueError(f"{nombre} tiene días repetidos")
        comunes = base[CLAVES].merge(tabla[CLAVES], on=CLAVES, how="inner")
        if len(tabla) != len(base) or len(comunes) != len(base):
            raise ValueError(f"{nombre} no trae las mismas series y días que el horizonte: {len(tabla)} filas, "
                             f"{len(comunes)} en común de {len(base)}")
        salida = salida.merge(tabla, on=CLAVES, how="left", validate="one_to_one")
    return salida


# ══ 5. El error del caso por grupos (reglas, apartado 6) ═════════════════════════════════
def filas_medidas(tabla):
    """Las filas que entran al error: sin los días fuera del error (el 25 de diciembre, reglas, apartado 6)."""
    return tabla[~tabla[COLUMNA_FUERA].to_numpy(dtype=bool)]


def sin_dias_fuera_del_error(medidas):
    """Verdadero si ninguna fila medida es un día fuera del error."""
    return not bool(medidas[COLUMNA_FUERA].to_numpy(dtype=bool).any())


def rotulo(tabla):
    """Sobre qué filas se calculó una cifra de validación: cuántas y de cuántos orígenes."""
    texto = f"validacion: {len(tabla)} filas"
    if "origen" in tabla.columns:
        texto += f" de {tabla['origen'].nunique()} orígenes"
    return texto


def errores_por_grupo(tabla, objetivo, predictores, columna=None):
    """El error y el sesgo de cada previsión, en todas las filas o por cada valor de una columna."""
    grupos = [(None, tabla)] if columna is None else list(tabla.groupby(columna, sort=True))
    salida = []
    for valor, grupo in grupos:
        real = grupo[objetivo].to_numpy(dtype="float64")
        for nombre in predictores:
            fila = {"grupo": valor, "prevision": nombre, "filas": rotulo(grupo)}
            if real.sum() > 0:
                fila["error"], fila["sesgo"] = pr.error_y_sesgo(real, grupo[nombre].to_numpy(dtype="float64"))
            else:
                fila.update(error=None, sesgo=None, motivo="la venta real suma cero: el error por cada 100 no existe")
            salida.append(fila)
    return salida


def meses_completos(fechas):
    """Los meses naturales con todos sus días entre el primer y el último día previsto (reglas, apartado 5: un mes sin todos
    sus días es parcial y no se compara)."""
    fechas = pd.DatetimeIndex(fechas)
    desde, hasta = fechas.min(), fechas.max()
    salida = []
    for mes in sorted(fechas.to_period("M").unique()):
        if mes.start_time.normalize() >= desde.normalize() and mes.end_time.normalize() <= hasta.normalize():
            salida.append(str(mes))
    return salida


def errores_por_mes(tabla, objetivo, predictores, meses):
    """El error de cada mes natural completo; cada día previsto cuenta en su mes (decisión 5)."""
    con_mes = tabla.assign(mes=tabla[COLUMNA_FECHA].dt.strftime("%Y-%m"))
    con_mes = con_mes[con_mes["mes"].isin(meses).to_numpy()]
    return errores_por_grupo(con_mes, objetivo, predictores, "mes")


def sin_meses_parciales(por_mes, meses):
    """Verdadero si la tabla de meses solo trae meses completos."""
    return all(e["grupo"] in meses for e in por_mes)


def sesgo_dias_cero(medidas, objetivo, predictores):
    """El sesgo en los días con venta real cero: el error medio con signo por fila, en la unidad del objetivo.

    La cifra por cada 100 divide por la venta, que aquí es cero; se usa el sesgo de la pieza común (error medio con
    signo, ec.medidas).
    """
    ceros = medidas[medidas[objetivo].to_numpy(dtype="float64") == 0]
    salida = []
    for nombre in predictores:
        salida.append({"prevision": nombre, "sesgo_medio_por_fila": float(ceros[nombre].mean()) if len(ceros) else None,
                       "unidad": "unidades" if objetivo == "unidades" else "dólares", "filas": rotulo(ceros)})
    return salida


# ══ 6. Ventaja, intervalo y veredicto (reglas, apartado 7; decisiones 1 y 3) ═══════════════
def sumas_por_serie_y_origen(medidas, objetivo, predictores, series, origenes):
    """Por serie y origen, la suma del error sin signo de cada previsión, la del error con signo y la de lo real."""
    indice = pd.MultiIndex.from_tuples(series, names=CLAVE_SERIE)

    def tabla(valores):
        """Suma por serie y origen, en el orden de series y orígenes; para si falta alguna combinación."""
        t = (medidas.assign(_v=valores).pivot_table(index=CLAVE_SERIE, columns="origen", values="_v", aggfunc="sum")
             .reindex(index=indice, columns=origenes))
        if t.isna().any().any():
            raise ValueError("alguna serie no tiene filas medidas en algún origen")
        return t.to_numpy(dtype="float64")

    real = medidas[objetivo].to_numpy(dtype="float64")
    return {"real": tabla(real),
            "abs": {p: tabla(np.abs(medidas[p].to_numpy(dtype="float64") - real)) for p in predictores},
            "con_signo": {p: tabla(medidas[p].to_numpy(dtype="float64") - real) for p in predictores}}


def ventaja_por_origen(abs_modelo, abs_reglas, real, pesos=None):
    """La ventaja de reglas, apartado 7 con la regla que menos falla en cada origen.

    abs_modelo y real: (series, orígenes); abs_reglas: (reglas, series, orígenes); pesos: (remuestreos, series), cuántas
    veces entra cada serie (sin pesos, una vez cada una). En cada remuestreo y origen se elige la regla que menos falla
    en lo remuestreado; la ventaja es el error de esa combinación menos el del modelo, sobre todos los orígenes juntos.
    """
    pesos = np.ones((1, real.shape[0])) if pesos is None else np.asarray(pesos, dtype="float64")
    den = pesos @ real
    if (den <= 0).any():
        raise ValueError("un remuestreo con la venta real a cero en algún origen")
    num_reglas = np.einsum("bs,kso->kbo", pesos, np.asarray(abs_reglas, dtype="float64"))
    regla = num_reglas.argmin(axis=0)
    num_comb = np.take_along_axis(num_reglas, regla[None], axis=0)[0]
    num_mod = pesos @ abs_modelo
    error_comb = 100 * num_comb.sum(axis=1) / den.sum(axis=1)
    error_mod = 100 * num_mod.sum(axis=1) / den.sum(axis=1)
    return {"error_combinacion": error_comb, "error_modelo": error_mod, "ventaja": error_comb - error_mod,
            "regla_por_origen": regla, "origenes_que_gana": (num_mod < num_comb).sum(axis=1),
            "error_modelo_por_origen": 100 * num_mod / den, "error_regla_por_origen": 100 * num_comb / den}


def pesos_por_series(n_unidades, n, semilla):
    """n remuestreos con reposición de las unidades: cuántas veces entra cada una en cada remuestreo."""
    rng = np.random.default_rng(semilla)
    sorteo = rng.integers(0, n_unidades, size=(n, n_unidades))
    return np.stack([np.bincount(fila, minlength=n_unidades) for fila in sorteo])


def remuestreo_por_entidad(pesos, n_series):
    """Verdadero si cada remuestreo sortea las series enteras: una columna por serie y n_series sorteadas (validación
    15). Un remuestreo de filas tiene una columna por fila y no pasa."""
    pesos = np.asarray(pesos)
    return bool(pesos.ndim == 2 and pesos.shape[1] == n_series and (pesos.sum(axis=1) == n_series).all()
                and (pesos >= 0).all())


def veredicto(origenes_que_gana, n_origenes, bajo):
    """El veredicto de reglas, apartado 7: gana, mejor de media pero no demostrado, o no gana."""
    minimo = math.ceil(PROPORCION_ORIGENES * n_origenes)
    primera = origenes_que_gana >= minimo
    segunda = bajo is not None and bajo > 0
    if primera and segunda:
        return "gana"
    if primera:
        return "mejor de media pero no demostrado"
    return "no gana"


def ventaja_por_otro_camino(medidas, objetivo, reglas):
    """La ventaja rehecha origen a origen con la tabla de filas: la regla que menos falla en cada uno y la suma de los
    errores sin signo de todos los orígenes (segunda vía de la ventaja vectorizada)."""
    num_comb = num_mod = den = 0.0
    for _, grupo in medidas.groupby("origen", sort=True):
        real = grupo[objetivo].to_numpy(dtype="float64")
        errores = {r: np.abs(grupo[r].to_numpy(dtype="float64") - real).sum() for r in reglas}
        num_comb += min(errores.values())
        num_mod += np.abs(grupo["modelo"].to_numpy(dtype="float64") - real).sum()
        den += real.sum()
    return 100 * (num_comb - num_mod) / den


def prueba_de_ganar(sumas, rivales, n_origenes, series):
    """Las dos pruebas de reglas, apartado 7 del modelo frente a una lista de rivales: los orígenes que gana y el intervalo de
    la ventaja con las series remuestreadas enteras."""
    abs_rivales = np.stack([sumas["abs"][r] for r in rivales])
    punto = ventaja_por_origen(sumas["abs"]["modelo"], abs_rivales, sumas["real"])
    pesos = pesos_por_series(len(series), REMUESTREOS, SEMILLA)
    remuestreo = ventaja_por_origen(sumas["abs"]["modelo"], abs_rivales, sumas["real"], pesos)
    bajo, alto = (float(np.percentile(remuestreo["ventaja"], p)) for p in PERCENTILES)
    ganados = int(punto["origenes_que_gana"][0])
    return {"origenes_que_gana": ganados, "de": n_origenes, "minimo": math.ceil(PROPORCION_ORIGENES * n_origenes),
            "ventaja": float(punto["ventaja"][0]), "error_modelo": float(punto["error_modelo"][0]),
            "error_rival": float(punto["error_combinacion"][0]),
            "rival_por_origen": [rivales[i] for i in punto["regla_por_origen"][0]],
            "intervalo": {"bajo": bajo, "alto": alto, "remuestreos": REMUESTREOS, "semilla": SEMILLA,
                          "percentiles": list(PERCENTILES), "medida": "ventaja en puntos de error por cada 100",
                          "unidad": "serie", "unidades": len(series),
                          "que_se_remuestrea": "las combinaciones de departamento y tienda enteras, con todos sus días "
                                               "y orígenes"},
            "veredicto": veredicto(ganados, n_origenes, bajo), "_pesos": pesos}


# ── 6.1 Lo que matiza la ventaja: lecturas que no cambian el veredicto ──
def aporte_por_serie(sumas, rivales, rival_por_origen, series):
    """Lo que aporta cada serie a la ventaja, con la regla que menos falla en cada origen (la de rival_por_origen).

    Aporte de una serie = (suma de errores sin signo de esa regla en la serie, origen a origen, menos la del modelo)
    entre la venta real total, por 100. La suma de las series es la ventaja. Devuelve las series de la que más aporta a
    la que menos (empates, por la clave de la serie), las cinco primeras y las sumas.
    """
    regla = [rivales.index(r) for r in rival_por_origen]
    abs_reglas = np.stack([sumas["abs"][r] for r in rivales])
    abs_rival = np.stack([abs_reglas[k, :, o] for o, k in enumerate(regla)], axis=1)
    total = float(sumas["real"].sum())
    aportes = 100 * (abs_rival.sum(axis=1) - sumas["abs"]["modelo"].sum(axis=1)) / total
    lista = sorted(({"store_id": s[0], "dept_id": s[1], "aporte": float(a)} for s, a in zip(series, aportes)),
                   key=lambda x: (-x["aporte"], x["store_id"], x["dept_id"]))
    primeras = lista[:SERIES_QUE_MAS_APORTAN]
    return {"series": lista, "cinco_primeras": primeras,
            "aporte_cinco_primeras": float(sum(x["aporte"] for x in primeras)),
            "suma_de_todas": float(sum(x["aporte"] for x in lista))}


def aporte_suma_la_ventaja(lista, ventaja):
    """Verdadero si el aporte de todas las series suma la ventaja del veredicto."""
    return bool(np.isclose(sum(x["aporte"] for x in lista), ventaja, rtol=0, atol=1e-9))


def ventaja_sin_tiendas(sumas, rivales, series, quitar):
    """La ventaja sin las series de unas tiendas, con la misma definición del veredicto: la regla que menos falla en
    cada origen se elige otra vez en lo que queda. Null con su motivo si alguna tienda no está o no queda ninguna."""
    tiendas = {s[0] for s in series}
    faltan = [t for t in quitar if t not in tiendas]
    dentro = np.array([s[0] not in quitar for s in series], dtype="float64")
    salida = {"quitar": list(quitar), "series": int(dentro.sum()), "de": len(series)}
    if faltan:
        return dict(salida, ventaja=None, motivo=f"no están en las series medidas: {', '.join(faltan)}")
    if dentro.sum() == 0:
        return dict(salida, ventaja=None, motivo="no queda ninguna serie")
    abs_reglas = np.stack([sumas["abs"][r] for r in rivales])
    v = ventaja_por_origen(sumas["abs"]["modelo"], abs_reglas, sumas["real"], dentro[None, :])
    return dict(salida, ventaja=float(v["ventaja"][0]),
                rival_por_origen=[rivales[i] for i in v["regla_por_origen"][0]])


def pesos_por_tienda(series, n, semilla):
    """n remuestreos con reposición de las tiendas enteras: cuántas veces entra cada serie, que es cuántas veces entra
    su tienda. Devuelve los pesos (remuestreos, series) y la tienda de cada serie."""
    tienda_de_serie = [s[0] for s in series]
    tiendas = sorted(set(tienda_de_serie))
    por_tienda = pesos_por_series(len(tiendas), n, semilla)
    columna = [tiendas.index(t) for t in tienda_de_serie]
    return por_tienda[:, columna], tienda_de_serie


def remuestreo_por_tienda(pesos, tienda_de_serie):
    """Verdadero si cada remuestreo sortea tiendas enteras: todas las series de una tienda entran las mismas veces y
    se sortean tantas tiendas como hay. Un remuestreo de series no pasa."""
    pesos = np.asarray(pesos)
    tiendas = sorted(set(tienda_de_serie))
    if pesos.ndim != 2 or pesos.shape[1] != len(tienda_de_serie) or (pesos < 0).any():
        return False
    por_tienda = []
    for t in tiendas:
        columnas = pesos[:, [i for i, x in enumerate(tienda_de_serie) if x == t]]
        if not (columnas == columnas[:, :1]).all():
            return False
        por_tienda.append(columnas[:, 0])
    return bool((np.stack(por_tienda, axis=1).sum(axis=1) == len(tiendas)).all())


def intervalo_por_tienda(sumas, rivales, series):
    """El intervalo del 95 % de la ventaja remuestreando tiendas enteras, con todas sus series, días y orígenes, con
    la misma definición del veredicto. Es una lectura: el del veredicto es el de series (decisión 3)."""
    pesos, tienda_de_serie = pesos_por_tienda(series, REMUESTREOS, SEMILLA)
    abs_reglas = np.stack([sumas["abs"][r] for r in rivales])
    remuestreo = ventaja_por_origen(sumas["abs"]["modelo"], abs_reglas, sumas["real"], pesos)
    bajo, alto = (float(np.percentile(remuestreo["ventaja"], p)) for p in PERCENTILES)
    return {"bajo": bajo, "alto": alto, "remuestreos": REMUESTREOS, "semilla": SEMILLA,
            "percentiles": list(PERCENTILES), "unidad": "tienda", "unidades": len(set(tienda_de_serie)),
            "que_se_remuestrea": "las tiendas enteras, con todas sus series, días y orígenes",
            "_bien": remuestreo_por_tienda(pesos, tienda_de_serie)}


def series_con_alguna_regla_mejor(sumas, rivales, series):
    """Las series en que alguna regla falla menos que el modelo, con todos los orígenes juntos: la suma de errores sin
    signo de la regla en la serie, menor que la del modelo."""
    modelo = sumas["abs"]["modelo"].sum(axis=1)
    reglas = np.stack([sumas["abs"][r].sum(axis=1) for r in rivales])
    real = sumas["real"].sum(axis=1)
    lista = []
    for i, s in enumerate(series):
        k = int(reglas[:, i].argmin())
        if reglas[k, i] < modelo[i]:
            lista.append({"store_id": s[0], "dept_id": s[1], "regla": rivales[k], "regla_nombre": NOMBRE[rivales[k]],
                          "error_de_la_regla": float(100 * reglas[k, i] / real[i]),
                          "error_del_modelo": float(100 * modelo[i] / real[i])})
    return {"cuantas": len(lista), "de": len(series), "series": lista}


def eventos_del_periodo(calendario, desde, hasta):
    """Los eventos del calendario entre dos días, los dos incluidos: una fila por evento y día, venga en
    event_name_1 o en event_name_2."""
    dias = pd.to_datetime(calendario[COLUMNA_FECHA])
    dentro = calendario[((dias >= pd.Timestamp(desde)) & (dias <= pd.Timestamp(hasta))).to_numpy()]
    partes = []
    for campo in ("event_name_1", "event_name_2"):
        con = dentro[dentro[campo].notna().to_numpy()]
        partes.append(pd.DataFrame({"nombre": con[campo].astype(str).to_numpy(),
                                    "fecha": pd.to_datetime(con[COLUMNA_FECHA]).to_numpy(), "campo": campo}))
    return pd.concat(partes, ignore_index=True).sort_values(["fecha", "nombre"], kind="stable").reset_index(drop=True)


def eventos_cubiertos(eventos, previsto, medidas):
    """Cuántos eventos caen en días medidos y en cuántas filas medidas cae cada uno. Un evento cuyo día está previsto
    pero fuera del error, o que no está en ningún horizonte, no cuenta como cubierto: se dice por qué."""
    medidos = pd.to_datetime(medidas[COLUMNA_FECHA]).value_counts()
    previstos = set(pd.to_datetime(previsto[COLUMNA_FECHA]))
    por_evento, sin_cubrir = [], []
    for e in eventos.itertuples(index=False):
        filas = int(medidos.get(e.fecha, 0))
        por_evento.append({"nombre": e.nombre, "fecha": e.fecha, "filas_medidas": filas})
        if filas == 0:
            motivo = "fuera del error" if e.fecha in previstos else "fuera del horizonte"
            sin_cubrir.append({"nombre": e.nombre, "fecha": e.fecha, "motivo": motivo})
    return {"cuantos": len(por_evento), "cubiertos": len(por_evento) - len(sin_cubrir), "sin_cubrir": sin_cubrir,
            "por_evento": por_evento}


def eventos_solo_en_dias_medidos(ev, medidas):
    """Verdadero si cada evento cubierto cae en un día medido y ninguno sin cubrir cae en uno."""
    dias = set(pd.to_datetime(medidas[COLUMNA_FECHA]))
    sin = {(x["nombre"], x["fecha"]) for x in ev["sin_cubrir"]}
    return all(((x["nombre"], x["fecha"]) in sin) != (x["fecha"] in dias) for x in ev["por_evento"])


def filas_por_dia_de_la_semana(medidas):
    """Las filas medidas de cada día de la semana, de lunes a domingo."""
    cuenta = pd.to_datetime(medidas[COLUMNA_FECHA]).dt.dayofweek.value_counts()
    dias = [{"dia": d, "filas": int(cuenta.get(i, 0))} for i, d in enumerate(DIAS_SEMANA)]
    return {"dias": dias, "total": int(sum(x["filas"] for x in dias))}


def robustez(sumas, frente_reglas, medidas, previsto, eventos, series, periodo):
    """El bloque «robustez» de un objetivo: las seis lecturas de la petición, con las mismas previsiones y filas medidas
    que el veredicto, sin ajustar, prever ni elegir nada nuevo. Cada cifra dice qué es y sobre qué filas."""
    rivales = list(pr.REGLAS)
    filas = rotulo(medidas)
    ap = aporte_por_serie(sumas, rivales, frente_reglas["rival_por_origen"], series)
    tiendas = sorted({s[0] for s in series})
    sin_cada = [dict(ventaja_sin_tiendas(sumas, rivales, series, [t]), filas=filas) for t in tiendas]
    juntas = dict(ventaja_sin_tiendas(sumas, rivales, series, list(QUITAR_JUNTAS)), filas=filas)
    intervalo = intervalo_por_tienda(sumas, rivales, series)
    bien_intervalo = intervalo.pop("_bien")
    mejores = series_con_alguna_regla_mejor(sumas, rivales, series)
    ev = eventos_cubiertos(eventos, previsto, medidas)
    dias = filas_por_dia_de_la_semana(medidas)
    comprobaciones = {
        "aporte_suma_la_ventaja": aporte_suma_la_ventaja(ap["series"], frente_reglas["ventaja"]),
        "intervalo_por_tienda_entera": bien_intervalo,
        "eventos_solo_en_dias_medidos": eventos_solo_en_dias_medidos(ev, medidas),
        "dias_de_la_semana_suman_las_filas": dias["total"] == len(medidas)}
    return {
        "que_es": "lo que matiza la ventaja: lecturas con las mismas previsiones y filas medidas "
                  "que el veredicto; no lo cambian",
        "filas": filas,
        "aporte_por_serie": dict(ap, ventaja=frente_reglas["ventaja"], filas=filas, que_es=(
            "puntos de la ventaja que aporta cada serie: (errores sin signo de la regla que menos falla en cada "
            "origen, la de rival_por_origen, menos los del modelo, en la serie) entre la venta real total, por 100; la "
            "suma de las series es la ventaja")),
        "ventaja_sin": {"cada_tienda": sin_cada, "juntas": juntas, "que_es": (
            "la ventaja sin las series de una tienda o de varias juntas, con la regla que menos falla en cada origen "
            "elegida otra vez en lo que queda"), "juntas_origen": "las tiendas que señaló el auditor"},
        "intervalo_por_tienda": dict(intervalo, filas=filas, que_es=(
            "intervalo del 95 % de la ventaja remuestreando tiendas enteras; es una lectura: el intervalo del "
            "veredicto es el de series (planteamientos §2, decisión 3)")),
        "series_con_alguna_regla_mejor": dict(mejores, filas=filas, que_es=(
            "series en que alguna de las tres reglas falla menos que el modelo, con todos los orígenes juntos")),
        "eventos": dict(ev, desde=periodo[0], hasta=periodo[1], filas=filas, que_es=(
            "eventos del calendario (event_name_1 y event_name_2) de la validación, uno por evento y día; cubierto si "
            "cae en alguna fila medida; sin cubrir, fuera del error (previsto y fuera de la medida) o fuera del "
            "horizonte (ningún origen lo prevé)")),
        "filas_por_dia_de_la_semana": dict(dias, filas=filas, que_es="filas medidas de cada día de la semana"),
        "comprobaciones": comprobaciones}


# ── 6.2 La previsión sumada (pregunta 3): lectura que no cambia el veredicto ──
def un_padre_por_hijo(dim_producto, dim_tienda):
    """Verdadero si cada departamento tiene una sola categoría y cada tienda un solo estado, sin vacíos."""
    pares = [tabla[[hijo, padre]].drop_duplicates() for tabla, hijo, padre in
             ((dim_producto, "dept_id", "cat_id"), (dim_tienda, "store_id", "state_id"))]
    return bool(all(not p.iloc[:, 1].isna().any() and not p.iloc[:, 0].duplicated().any() for p in pares))


def padres_de_las_series(dim_producto, dim_tienda, series):
    """La categoría de cada departamento y el estado de cada tienda de las series medidas.

    Sale de data/processed/dim_producto.parquet (cat_id de cada dept_id) y dim_tienda.parquet (state_id de cada
    store_id). Para si un departamento tiene dos categorías, una tienda dos estados o una serie queda sin alguno.
    """
    if not un_padre_por_hijo(dim_producto, dim_tienda):
        raise ValueError("algún departamento con más de una categoría o alguna tienda con más de un estado")
    categoria = dict(dim_producto[["dept_id", "cat_id"]].drop_duplicates().itertuples(index=False, name=None))
    estado = dict(dim_tienda[["store_id", "state_id"]].drop_duplicates().itertuples(index=False, name=None))
    sin_padre = [s for s in series if s[1] not in categoria or s[0] not in estado]
    if sin_padre:
        raise ValueError(f"{len(sin_padre)} series sin categoría o sin estado: {sin_padre[:3]}")
    return {"categoria": {d: categoria[d] for d in sorted({s[1] for s in series})},
            "estado": {t: estado[t] for t in sorted({s[0] for s in series})}}


def grupo_de_cada_fila(tabla, nivel, padres):
    """El grupo de cada fila en un nivel: la cadena entera, el estado de su tienda, su tienda o la categoría de su
    departamento."""
    if nivel == "cadena":
        return pd.Series("cadena", index=tabla.index)
    if nivel == "estado":
        return tabla["store_id"].map(padres["estado"])
    if nivel == "tienda":
        return tabla["store_id"]
    if nivel == "categoria":
        return tabla["dept_id"].map(padres["categoria"])
    raise ValueError(f"nivel desconocido: {nivel}")


def sumar_por_grupo(medidas, objetivo, nivel, padres, predictores=PREDICTORES_NIVELES):
    """La previsión de cada grupo, cada origen y cada día: la suma de las de sus series tal como se miden.

    Cada previsión de cada serie se acota en cero y, en unidades, se redondea (previsto_medible) antes de sumar, como
    se suman los pedidos de cada departamento; la venta real se suma tal cual. Se suma por grupo, origen y día: dos
    orígenes que prevén el mismo día no se mezclan. Devuelve grupo, origen, date, la venta real, cada previsión sumada y
    cuántas series suma cada fila.
    """
    t = medidas[["origen", COLUMNA_FECHA] + CLAVE_SERIE + [objetivo] + list(predictores)].copy()
    for p in predictores:
        t[p] = previsto_medible(t[p], objetivo)
    t["grupo"] = grupo_de_cada_fila(t, nivel, padres).to_numpy()
    if t["grupo"].isna().any():
        raise ValueError(f"filas sin grupo en el nivel {nivel}")
    columnas = [objetivo] + list(predictores)
    agregado = {c: (c, "sum") for c in columnas} | {"series": (objetivo, "size")}
    return t.groupby(["grupo", "origen", COLUMNA_FECHA], sort=True).agg(**agregado).reset_index()


def grupos_completos(sumas, medidas, nivel, padres):
    """Verdadero si cada fila sumada lleva todas las series de su grupo: ningún día de un origen con series de menos,
    que haría que el grupo midiera días distintos que sus series."""
    series = medidas[CLAVE_SERIE].drop_duplicates()
    esperadas = series.assign(grupo=grupo_de_cada_fila(series, nivel, padres).to_numpy()).groupby("grupo").size()
    return bool((sumas["series"].to_numpy() == sumas["grupo"].map(esperadas).to_numpy()).all())


def sumas_cuadran(sumas, medidas, objetivo, predictores=PREDICTORES_NIVELES):
    """Verdadero si lo sumado en el nivel suma lo mismo que las filas medidas: la venta real y cada previsión, esta
    acotada y, en unidades, redondeada en cada serie."""
    bien = np.isclose(sumas[objetivo].sum(), medidas[objetivo].astype("float64").sum(), rtol=1e-12, atol=1e-6)
    for p in predictores:
        bien = bien and np.isclose(sumas[p].sum(), previsto_medible(medidas[p], objetivo).sum(), rtol=1e-12,
                                   atol=1e-6)
    return bool(bien and sumas["series"].sum() == len(medidas))


def rotulo_sumado(tabla):
    """Sobre qué filas se calculó una cifra de la previsión sumada: cuántas filas de grupo, origen y día, de cuántos
    orígenes y cuántas series suma cada una."""
    series = int(tabla["series"].max()) if len(tabla) else 0
    return (f"validacion: {len(tabla)} filas sumadas (grupo, origen y día) de {tabla['origen'].nunique()} orígenes, "
            f"cada una con {series} series")


def errores_del_nivel(sumas, objetivo, predictores=PREDICTORES_NIVELES):
    """Por cada grupo, con todos los orígenes juntos: el error y el sesgo de reglas, apartado 6 de cada previsión sobre las
    filas sumadas, la regla que menos falla en él (con empate, por su nombre) y si el modelo falla menos que ella."""
    salida = []
    for grupo, g in sumas.groupby("grupo", sort=True):
        filas = rotulo_sumado(g)
        real = g[objetivo].to_numpy(dtype="float64")
        errores = []
        for p in predictores:
            fila = {"prevision": p, "filas": filas}
            if real.sum() > 0:
                fila["error"], fila["sesgo"] = pr.error_y_sesgo(real, g[p].to_numpy(dtype="float64"))
            else:
                fila.update(error=None, sesgo=None, motivo="la venta real suma cero: el error por cada 100 no existe")
            errores.append(fila)
        por = {e["prevision"]: e for e in errores}
        reglas = [r for r in pr.REGLAS if por[r]["error"] is not None]
        mejor = min(reglas, key=lambda r: (por[r]["error"], r)) if reglas else None
        modelo = por["modelo"]
        salida.append({
            "grupo": grupo, "series": int(g["series"].max()), "filas_sumadas": len(g), "origenes": int(g["origen"].nunique()),
            "errores": errores, "error_modelo": modelo["error"], "sesgo_modelo": modelo["sesgo"],
            "regla_que_menos_falla": mejor, "regla_que_menos_falla_nombre": NOMBRE.get(mejor),
            "error_regla": por[mejor]["error"] if mejor else None, "sesgo_regla": por[mejor]["sesgo"] if mejor else None,
            "modelo_falla_menos": (bool(modelo["error"] < por[mejor]["error"]) if mejor and modelo["error"] is not None
                                   else None),
            "filas": filas})
    return salida


def origenes_de_la_cadena(sumas_cadena, objetivo):
    """En cada origen, el error del modelo y el de la regla que menos falla en ese origen sobre las filas sumadas de
    la cadena; cuántos orígenes falla menos el modelo."""
    por_origen = []
    for origen, g in sumas_cadena.groupby("origen", sort=True):
        real = g[objetivo].to_numpy(dtype="float64")
        errores = {p: pr.error_y_sesgo(real, g[p].to_numpy(dtype="float64"))[0] for p in ("modelo",) + pr.REGLAS}
        mejor = min(pr.REGLAS, key=lambda r: (errores[r], r))
        por_origen.append({"origen": origen, "error_modelo": errores["modelo"], "regla_que_menos_falla": mejor,
                           "regla_que_menos_falla_nombre": NOMBRE[mejor], "error_regla": errores[mejor],
                           "modelo_falla_menos": bool(errores["modelo"] < errores[mejor]), "filas": rotulo_sumado(g)})
    return {"origenes_que_gana": sum(x["modelo_falla_menos"] for x in por_origen), "de": len(por_origen),
            "por_origen": por_origen, "filas": rotulo_sumado(sumas_cadena), "que_es": (
                "orígenes en que el modelo falla menos que la regla que menos falla en ese origen, sobre las filas "
                "sumadas de la cadena; es una lectura: el veredicto se mide con las series (reglas, apartado 7)")}


def cadena_cuadra(grupo_cadena, medidas, objetivo):
    """Verdadero si la cadena suma todas las series medidas y da su error: la segunda vía suma las filas medidas por
    origen y día, sin pasar por los grupos, y mide el modelo y cada regla sobre esas sumas."""
    t = medidas.assign(**{p: previsto_medible(medidas[p], objetivo) for p in ("modelo",) + pr.REGLAS})
    sumado = t.groupby(["origen", COLUMNA_FECHA], sort=True)[[objetivo, "modelo", *pr.REGLAS]].sum()
    real = sumado[objetivo].to_numpy(dtype="float64")
    por = {e["prevision"]: e for e in grupo_cadena.get("errores", [])}
    bien = grupo_cadena.get("series") == len(medidas[CLAVE_SERIE].drop_duplicates())
    bien = bien and grupo_cadena.get("filas_sumadas") == len(sumado)
    for p in ("modelo",) + pr.REGLAS:
        error = pr.error_y_sesgo(real, sumado[p].to_numpy(dtype="float64"))[0]
        dado = grupo_cadena.get("error_modelo") if p == "modelo" else (por.get(p) or {}).get("error")
        bien = bien and dado is not None and bool(np.isclose(dado, error, rtol=0, atol=1e-9))
    return bool(bien)


def previsiones_sumadas(medidas, objetivo, padres):
    """El bloque «niveles» de un objetivo: la cadena, los estados, las tiendas y las categorías, cada uno con la suma
    de sus series en las mismas filas medidas que el veredicto, sin ajustar, prever ni elegir nada nuevo."""
    bloque = {"que_es": ("la previsión sumada de abajo arriba (reglas, apartado 4, «Cómo cuadran los niveles»; ficha, "
                         "pregunta 3): una lectura con las mismas previsiones y filas medidas que el veredicto; no lo "
                         "cambia"),
              "como_se_suma": ("en cada grupo, origen y día, la suma de las previsiones de sus series tal como se "
                               "miden: acotadas en cero y, en unidades, redondeadas al entero antes de sumar; la "
                               "venta real, sumada igual; el error y el sesgo de reglas, apartado 6, sobre las filas sumadas de "
                               "todos los orígenes juntos"),
              "filas": rotulo(medidas), "padres": padres,
              "fuente_padres": f"{DIM_PRODUCTO_REL} (cat_id de cada dept_id); {DIM_TIENDA_REL} (state_id de cada "
                               "store_id)", "teoria": TEORIA_NIVELES}
    completos, cuadran = [], []
    for nivel in NIVELES:
        sumas = sumar_por_grupo(medidas, objetivo, nivel, padres)
        completos.append(grupos_completos(sumas, medidas, nivel, padres))
        cuadran.append(sumas_cuadran(sumas, medidas, objetivo))
        bloque[nivel] = {"grupos": errores_del_nivel(sumas, objetivo), "cuantos": int(sumas["grupo"].nunique()),
                         "filas": rotulo_sumado(sumas)}
        if nivel == "cadena":
            bloque[nivel]["origenes"] = origenes_de_la_cadena(sumas, objetivo)
    bloque["comprobaciones"] = {
        "un_padre_por_hijo": all(medidas["dept_id"].map(padres["categoria"]).notna())
        and all(medidas["store_id"].map(padres["estado"]).notna()),
        "grupos_completos": all(completos), "sumas_cuadran": all(cuadran),
        "cadena_igual_a_las_series_sumadas": cadena_cuadra(bloque["cadena"]["grupos"][0], medidas, objetivo)}
    return bloque


# ══ 7. MASE y recomendación por departamento ══════════════════════════════════════
def escala_mase(series_construccion, objetivo):
    """La escala de cada serie: el error medio de repetir la semana anterior a un día en la construcción, sin los días
    fuera del error como día previsto."""
    t = series_construccion.sort_values(CLAVES).reset_index(drop=True)
    vp.comprobar_sin_huecos(t)
    previo = t.groupby(CLAVE_SERIE, sort=False)[objetivo].shift(7).astype("float64")
    error = (t[objetivo].astype("float64") - previo).abs()
    validos = (previo.notna() & ~t[COLUMNA_FUERA].astype(bool)).to_numpy()
    escala = error[validos].groupby([t.loc[validos, c] for c in CLAVE_SERIE]).mean()
    if (escala <= 0).any():
        raise ValueError("una serie con escala cero: el MASE no existe")
    return escala


def mase(medidas, objetivo, predictores, escala):
    """El MASE de cada previsión: el error sin signo de cada fila entre la escala de su serie, de media. Cada serie
    tiene las mismas filas medidas, así que es también la media del MASE de cada serie."""
    s = pd.MultiIndex.from_frame(medidas[CLAVE_SERIE])
    divisor = escala.reindex(s).to_numpy(dtype="float64")
    if np.isnan(divisor).any():
        raise ValueError("una serie medida sin escala")
    real = medidas[objetivo].to_numpy(dtype="float64")
    return {p: float(np.mean(np.abs(medidas[p].to_numpy(dtype="float64") - real) / divisor)) for p in predictores}


def recomendacion_por_departamento(medidas, objetivo):
    """En cada departamento, el error de media del modelo y de cada regla en todos los orígenes; si el modelo falla más
    que la regla que menos falla en él, se recomienda esa regla (reglas, apartado 7)."""
    salida = []
    for dept, grupo in medidas.groupby("dept_id", sort=True):
        real = grupo[objetivo].to_numpy(dtype="float64")
        errores = {p: pr.error_y_sesgo(real, grupo[p].to_numpy(dtype="float64")) for p in ("modelo",) + pr.REGLAS}
        mejor = min(pr.REGLAS, key=lambda r: (errores[r][0], r))
        recomendar = errores["modelo"][0] > errores[mejor][0]
        salida.append({"departamento": dept, "error_modelo": errores["modelo"][0], "sesgo_modelo": errores["modelo"][1],
                       "errores_reglas": {r: errores[r][0] for r in pr.REGLAS}, "regla_que_menos_falla": mejor,
                       "regla_que_menos_falla_nombre": NOMBRE[mejor], "error_regla": errores[mejor][0],
                       "sesgo_regla": errores[mejor][1], "se_recomienda": NOMBRE[mejor] if recomendar else "el modelo",
                       "filas": rotulo(grupo)})
    return salida


# ══ 8. Un objetivo ══════════════════════════════════════════════════════════════
def validar_objetivo(objetivo, receta, tablas, origenes, columnas_evento, series):
    """Ajusta el ganador, prevé desde cada origen con el modelo y sus referencias y mide todo lo del §8."""
    h = HORIZONTE[objetivo]
    ent, val, ent_s, val_s = tablas["me"], tablas["mv"], tablas["se"], tablas["sv"]
    hiper, columnas = receta["hiperparametros"], receta["columnas"]
    entrada = entrada_de(objetivo, columnas_evento)
    tiempos = {}

    # El ajuste, una vez, con todo el entrenamiento: el objetivo se sabe al momento (método, apartado 7)
    inicio = time.perf_counter()
    modelo = construir_modelo(objetivo, columnas_evento, columnas, hiper)
    modelo.fit(tablas["me_ajuste"][entrada], tablas["me_ajuste"][objetivo])
    tiempos["ajuste"] = time.perf_counter() - inicio
    des = filas_medidas(tablas["me_ajuste"])
    previsto_des = previsto_medible(modelo.predict(des[entrada]), objetivo)
    error_des = pr.error_y_sesgo(des[objetivo], previsto_des)
    esperado = ((receta.get("reajuste") or {}).get("entrenamiento") or {}).get("error")
    mediana = float(np.median(tablas["me_ajuste"][objetivo].to_numpy(dtype="float64")))

    # La historia real de las dos tablas, hasta donde llegue; cada función la corta en el origen
    historia = pd.concat([ent, val], ignore_index=True)[CLAVES + [objetivo]]
    historia_s = pd.concat([ent_s, val_s], ignore_index=True)[CLAVES + [objetivo, COLUMNA_FUERA]]

    # Desde cada origen: el modelo en recursivo, las tres reglas, el suavizado y el trivial, en las mismas filas
    partes, controles, registro_suav, crudas = [], [], [], {}
    tiempos.update(recursion=0.0, reglas=0.0, suavizado=0.0)
    for numero, origen in enumerate(origenes, start=1):
        dias = [origen + pd.Timedelta(k, "D") for k in range(1, h + 1)]
        futuro = val[val[COLUMNA_FECHA].isin(dias).to_numpy()]
        inicio = time.perf_counter()
        rec = prever_modelo(modelo, historia, futuro, objetivo, origen, h)
        tiempos["recursion"] += time.perf_counter() - inicio
        inicio = time.perf_counter()
        reglas = pr.reglas_sencillas(historia, objetivo, origen, h).drop(columns="h")
        tiempos["reglas"] += time.perf_counter() - inicio
        inicio = time.perf_counter()
        suav, reg = prever_suavizado(historia_s[CLAVES + [objetivo]], objetivo, origen, h)
        tiempos["suavizado"] += time.perf_counter() - inicio
        registro_suav.append({"origen": origen, "bien": suavizado_sin_futuro(reg, origen),
                              "primer_dia": min(x["primer_dia"] for x in reg),
                              "ultimo_dia": max(x["ultimo_dia"] for x in reg)})
        base = futuro[CLAVES + [objetivo, COLUMNA_FUERA, "snap", "event_name_1", "event_name_2"]]
        tabla = unir_previsiones(base, {"modelo": rec, "reglas": reglas, "suavizado": suav.drop(columns="h")})
        tabla = tabla.assign(trivial=mediana, origen=origen, numero_origen=numero)
        if numero == 1:
            crudas["modelo"] = rec.sort_values(CLAVES)["modelo"].to_numpy()
            crudas["suavizado"] = suav.sort_values(CLAVES)["suavizado"].to_numpy()
        controles.append({"origen": origen, "recursiva": comprobar_recursiva(rec.rename(columns={"modelo": "x"}),
                                                                           len(series), origen, h),
                          "completa": bool(tabla[list(PREDICTORES)].notna().all().all()
                                           and len(tabla) == len(series) * h),
                          "sin_negativas": bool((tabla[list(PREDICTORES)] >= 0).all().all())})
        partes.append(tabla)
    previsto = pd.concat(partes, ignore_index=True)
    for p in PREDICTORES:
        previsto[p] = previsto_medible(previsto[p], objetivo)
    medidas = filas_medidas(previsto)

    # Las tres reglas desde el primer origen, llamadas a mano con la historia hasta el 22/05/2014 (control de la petición)
    primero = medidas[medidas["numero_origen"] == 1]
    a_mano = pr.reglas_sencillas(ent[CLAVES + [objetivo]], objetivo, origenes[0], h).drop(columns="h")
    a_mano = primero[CLAVES + [objetivo]].merge(a_mano, on=CLAVES, how="left", validate="one_to_one")
    reglas_a_mano = all(np.isclose(pr.error_y_sesgo(primero[objetivo], primero[r])[0],
                                   pr.error_y_sesgo(a_mano[objetivo], previsto_medible(a_mano[r], objetivo))[0],
                                   rtol=0, atol=1e-9) for r in pr.REGLAS)

    # 5. El error y el sesgo por grupos
    meses = meses_completos(previsto[COLUMNA_FECHA])
    con_evento = medidas["event_name_1"].notna() | medidas["event_name_2"].notna()
    errores = {
        "todas": errores_por_grupo(medidas, objetivo, PREDICTORES),
        "por_origen": errores_por_grupo(medidas, objetivo, PREDICTORES, "origen"),
        "por_departamento": errores_por_grupo(medidas, objetivo, PREDICTORES, "dept_id"),
        "por_tienda": errores_por_grupo(medidas, objetivo, PREDICTORES, "store_id"),
        "por_h": errores_por_grupo(medidas, objetivo, PREDICTORES, "h"),
        "por_mes": errores_por_mes(medidas, objetivo, PREDICTORES, meses),
        "dias_con_evento": errores_por_grupo(medidas[con_evento.to_numpy()], objetivo, PREDICTORES),
        "dias_sin_evento": errores_por_grupo(medidas[(~con_evento).to_numpy()], objetivo, PREDICTORES),
        "dias_snap": errores_por_grupo(medidas[medidas["snap"].to_numpy() == 1], objetivo, PREDICTORES),
        "dias_sin_snap": errores_por_grupo(medidas[medidas["snap"].to_numpy() == 0], objetivo, PREDICTORES)}

    # 6. El veredicto frente a las tres reglas y, como lectura, frente al suavizado
    sumas = sumas_por_serie_y_origen(medidas, objetivo, PREDICTORES, series, origenes)
    frente_reglas = prueba_de_ganar(sumas, list(pr.REGLAS), len(origenes), series)
    frente_suavizado = prueba_de_ganar(sumas, ["suavizado"], len(origenes), series)
    otro_camino = ventaja_por_otro_camino(medidas, objetivo, pr.REGLAS)
    pesos = frente_reglas.pop("_pesos")
    frente_suavizado.pop("_pesos")
    frente_suavizado["lectura"] = frente_suavizado.pop("veredicto")

    # 6.1 Lo que matiza la ventaja, con las mismas sumas y filas que el veredicto
    inicio = time.perf_counter()
    matiza = robustez(sumas, frente_reglas, medidas, previsto, tablas["eventos"], series, tablas["periodo"])
    tiempos["robustez"] = time.perf_counter() - inicio

    # 6.2 La previsión sumada por niveles, con las mismas filas medidas que el veredicto (pregunta 3)
    inicio = time.perf_counter()
    niveles = previsiones_sumadas(medidas, objetivo, tablas["padres"])
    tiempos["niveles"] = time.perf_counter() - inicio

    # 8. Lo demás del §8 con la pieza común, en las mismas filas
    real = medidas[objetivo].to_numpy(dtype="float64")
    orden = ["modelo"] + list(pr.REGLAS) + ["suavizado", "trivial"]
    comparacion = ec.comparar_modelos(real, {p: medidas[p].to_numpy(dtype="float64") for p in orden})
    tramos = ec.error_por_tramo(real, medidas["modelo"].to_numpy(dtype="float64"), n_tramos=TRAMOS)
    des_val = ec.desarrollo_frente_a_validacion(des[objetivo].to_numpy(dtype="float64"), previsto_des, real,
                                                medidas["modelo"].to_numpy(dtype="float64"))
    escala = escala_mase(ent_s, objetivo)
    mase_valores = mase(medidas, objetivo, PREDICTORES, escala)

    # Validación 11: el canario en el primer origen, con el objetivo barajado y con la venta real como variable
    canario = canario_del_primer_origen(objetivo, receta, tablas, origenes[0], columnas_evento, historia,
                                        errores["por_origen"])
    # Validación 8: dos ejecuciones seguidas dan lo mismo
    otro = construir_modelo(objetivo, columnas_evento, columnas, hiper)
    otro.fit(tablas["me_ajuste"][entrada], tablas["me_ajuste"][objetivo])
    dias1 = [origenes[0] + pd.Timedelta(k, "D") for k in range(1, h + 1)]
    futuro1 = val[val[COLUMNA_FECHA].isin(dias1).to_numpy()]
    repetida = prever_modelo(otro, historia, futuro1, objetivo, origenes[0], h).sort_values(CLAVES)["modelo"]
    suav2, _ = prever_suavizado(historia_s[CLAVES + [objetivo]], objetivo, origenes[0], h)
    reproducible = bool(np.array_equal(repetida.to_numpy(), crudas["modelo"])
                        and np.array_equal(suav2.sort_values(CLAVES)["suavizado"].to_numpy(), crudas["suavizado"]))

    # Lo que piden las validaciones, calculado con lo ejecutado
    claves_ajuste = tablas["me_ajuste"][CLAVES]
    control = {
        "sin_filas_de_ajuste": len(medidas[CLAVES].merge(claves_ajuste, on=CLAVES, how="inner")) == 0,
        "objetivo_conocido_al_entrenar": int((tablas["me_ajuste"][COLUMNA_FECHA]
                                              >= previsto[COLUMNA_FECHA].min()).sum()) == 0,
        "recursiva": all(c["recursiva"] and c["completa"] and c["sin_negativas"] for c in controles),
        "mismas_filas": bool(previsto[list(PREDICTORES)].notna().all().all()),
        "ventaja_otro_camino": bool(np.isclose(otro_camino, frente_reglas["ventaja"], rtol=0, atol=1e-9)),
        "sin_dias_fuera": sin_dias_fuera_del_error(medidas),
        "sin_meses_parciales": sin_meses_parciales(errores["por_mes"], meses),
        "suavizado_sin_futuro": all(x["bien"] for x in registro_suav),
        "intervalo_por_entidad": remuestreo_por_entidad(pesos, len(series)),
        "reglas_a_mano": bool(reglas_a_mano), "reproducible": reproducible,
        "receta_reproducida": None if esperado is None else bool(np.isclose(error_des[0], esperado, rtol=1e-9,
                                                                            atol=1e-9)),
        "semilla": modelo[-1].get_params().get("random_state")}
    dias_por_serie = previsto.groupby(CLAVE_SERIE)[COLUMNA_FECHA].agg(["size", "nunique"])

    resultado = {
        "horizonte": h, "origenes": origenes, "filas_previstas": len(previsto), "filas_medidas": len(medidas),
        "filas_fuera_del_error": int(previsto[COLUMNA_FUERA].sum()),
        "dias_fuera_del_error": sorted({f"{d:%Y-%m-%d}" for d in previsto.loc[previsto[COLUMNA_FUERA].to_numpy(dtype=bool),
                                                                            COLUMNA_FECHA]}),
        "dias_previstos_por_serie": int(dias_por_serie["size"].iloc[0]) if dias_por_serie["size"].nunique() == 1 else None,
        "dias_distintos_por_serie": int(dias_por_serie["nunique"].min()),
        "primer_dia_previsto": previsto[COLUMNA_FECHA].min(), "ultimo_dia_previsto": previsto[COLUMNA_FECHA].max(),
        "meses_completos": meses, "trivial": {"valor": mediana, "como": "la mediana de las filas del ajuste, como en "
                                                                        "scripts/15_busqueda.py"},
        "errores": errores, "veredicto": frente_reglas, "suavizado": frente_suavizado,
        "ventaja_por_otro_camino": otro_camino, "robustez": matiza, "niveles": niveles,
        "recomendacion_por_departamento": recomendacion_por_departamento(medidas, objetivo),
        "sesgo_dias_cero": sesgo_dias_cero(medidas, objetivo, PREDICTORES),
        "medidas_pieza": {"filas": rotulo(medidas), "tabla": comparacion.reset_index(names="prevision")
                          .to_dict(orient="records"), "referencia_de_mejora_mae": "trivial"},
        "error_por_tramo": {"filas": rotulo(medidas), "prevision": "modelo",
                            "tabla": tramos.reset_index().assign(tramo=lambda t: t["tramo"].astype(str))
                            .to_dict(orient="records")},
        "desarrollo_frente_a_validacion": {
            "entrenamiento": {"error": error_des[0], "sesgo": error_des[1],
                              "filas": f"entrenamiento: {len(des)} filas del ajuste sin los días fuera del error, "
                                       f"a un día"},
            "validacion": next(e for e in errores["todas"] if e["prevision"] == "modelo"),
            "pieza": des_val.reset_index(names="lado").to_dict(orient="records"),
            "pieza_filas": "desarrollo: filas del ajuste a un día (entrenamiento); validación: recursiva desde los "
                           "orígenes"},
        "mase": {"valores": mase_valores, "escala": "error medio de repetir la semana anterior a un día en la "
                                                    "construcción, por serie, sin los días fuera del error",
                 "filas": rotulo(medidas)},
        "canario": canario, "reajuste": {"filas": len(tablas["me_ajuste"]), "error_entrenamiento": error_des[0],
                                          "error_de_la_busqueda": esperado},
        "tiempos": tiempos, "control": control, "sumas": sumas}
    return resultado, previsto


def canario_del_primer_origen(objetivo, receta, tablas, origen, columnas_evento, historia, por_origen):
    """El canario de la validación 11 en el primer origen, con la receta del ganador ajustada otra vez.

    Con el objetivo barajado en el ajuste, el modelo deja de ganar a la regla que menos falla en ese origen; con la
    venta real puesta como variable, el error cae por debajo de LIMITE_FUGA (reglas, apartado 7, «Lo esperable»).
    """
    h = HORIZONTE[objetivo]
    hiper, columnas = receta["hiperparametros"], receta["columnas"]
    entrada = entrada_de(objetivo, columnas_evento)
    ajuste, val = tablas["me_ajuste"], tablas["mv"]
    dias = [origen + pd.Timedelta(k, "D") for k in range(1, h + 1)]
    futuro = val[val[COLUMNA_FECHA].isin(dias).to_numpy()]
    medidas = filas_medidas(futuro)

    def medir(prevision):
        """El error de reglas, apartado 6 en las filas medidas del primer origen."""
        junto = medidas[CLAVES + [objetivo]].merge(prevision, on=CLAVES, how="left", validate="one_to_one")
        return pr.error_y_sesgo(junto[objetivo], previsto_medible(junto["modelo"], objetivo))[0]

    barajado = np.random.default_rng(SEMILLA).permutation(ajuste[objetivo].to_numpy())
    modelo = construir_modelo(objetivo, columnas_evento, columnas, hiper).fit(ajuste[entrada], barajado)
    error_barajado = medir(prever_modelo(modelo, historia, futuro, objetivo, origen, h))
    con_fuga = ajuste.assign(**{COLUMNA_FUGA: ajuste[objetivo].astype("float64")})
    modelo = construir_modelo(objetivo, columnas_evento, columnas, hiper, extra=(COLUMNA_FUGA,))
    modelo.fit(con_fuga[entrada + [COLUMNA_FUGA]], con_fuga[objetivo])
    futuro_fuga = futuro.assign(**{COLUMNA_FUGA: futuro[objetivo].astype("float64")})
    error_fuga = medir(prever_modelo(modelo, historia, futuro_fuga, objetivo, origen, h))
    filas = f"validacion: {len(medidas)} filas del primer origen, recursiva"
    del_origen = [e for e in por_origen if e["grupo"] == origen and e["prevision"] in pr.REGLAS]
    mejor = min(del_origen, key=lambda e: e["error"])
    return {"origen": origen, "barajado": {"error": error_barajado, "filas": filas},
            "fuga": {"error": error_fuga, "filas": filas},
            "regla_que_menos_falla": {"nombre": mejor["prevision"], "error": mejor["error"], "filas": mejor["filas"]},
            "barajado_pierde_la_senal": bool(error_barajado > mejor["error"]),
            "fuga_se_ve": bool(error_fuga < LIMITE_FUGA), "limite_fuga": LIMITE_FUGA}


# ══ 9. Las tres vías de mejora (método, apartado 8) ═════════════════════════════════════════
def vias_de_mejora(busqueda, preparacion, raiz):
    """Lo probado y lo que queda en cada vía, de la más barata a la más cara, con lo que dicen los JSON y los
    documentos del caso."""
    probados = sorted({f["algoritmo"] for f in busqueda.get("ranking", [])})
    fichas = sorted(p.name for p in (raiz / "assets" / "fichas_de_algoritmos").iterdir() if p.is_dir()) \
        if (raiz / "assets" / "fichas_de_algoritmos").exists() else []
    variables = [{"variable": v.get("variable"), "probada": v.get("entra"), "motivo": v.get("porque")}
                 for v in ((preparacion or {}).get("matriz") or {}).get("variables", [])]
    return {
        "mejor_modelo": {"probado": {"algoritmos": probados, "espacio": (busqueda.get("busqueda") or {}).get("espacio"),
                                     "segundas_busquedas": len((busqueda.get("busqueda") or {})
                                                               .get("segundas_busquedas", []))},
                         "fichas_en_el_caso": fichas,
                         "queda": "un modelo por serie, descartado en los planteamientos §2, decisión 6, por coste; "
                                  "cualquier búsqueda nueva se mide solo con filas que nadie ha visto (método, apartado 8)",
                         "fuente": f"{BUSQUEDA_REL}; {PLANTEAMIENTOS_REL} §2"},
        "variables_nuevas": variables,
        "informacion_nueva": [
            {"dato": "existencias por producto y tienda", "para_que": "distinguir un día sin demanda de un estante "
                                                                      "vacío", "quien_lo_tiene": "no consta"},
            {"dato": "promociones", "para_que": "medir el efecto del precio, que con precios casi fijos no se puede "
                                                "estudiar", "quien_lo_tiene": "no consta"},
            {"dato": "los 3.049 productos y no el recorte de 500", "para_que": "la venta entera de cada departamento",
             "quien_lo_tiene": "no consta"}],
        "fuente_informacion": "config/negocio/01_ficha_del_caso.md, «Lo que condiciona las respuestas»"}


# ══ 10. El resultado para el responsable del caso, generado del JSON ════════════════════════════════
NOMBRE_OBJETIVO = {"unidades": "Unidades, a 10 días", "dolares": "Dólares, a 28 días"}
UNIDAD = {"unidades": "unidades por cada 100 vendidas", "dolares": "dólares por cada 100 vendidos"}


def cifra(lista, prevision, grupo=None):
    """La entrada de una lista de errores para una previsión y un grupo."""
    return next((e for e in lista if e["prevision"] == prevision and e["grupo"] == grupo), None)


def md_matiza(r):
    """El apartado «Lo que matiza la ventaja» de validacion_resultado.md, con el bloque «robustez» del JSON."""
    lineas = ["", "## Lo que matiza la ventaja", "",
              "Son lecturas con las mismas previsiones y las mismas filas medidas que el veredicto. No lo cambian.", ""]
    for objetivo in OBJETIVOS:
        rob = r["validacion"][objetivo].get("robustez")
        if not rob:
            continue
        ap, vs, it = rob["aporte_por_serie"], rob["ventaja_sin"], rob["intervalo_por_tienda"]
        me, ev, di = rob["series_con_alguna_regla_mejor"], rob["eventos"], rob["filas_por_dia_de_la_semana"]
        juntas = vs["juntas"]
        nombre_juntas = " y ".join(juntas["quitar"])
        sin_juntas = (f"Sin {nombre_juntas} juntas, la ventaja es de {num(juntas['ventaja'], 2, True)} puntos."
                      if juntas["ventaja"] is not None else f"Sin {nombre_juntas} no se calcula: {juntas['motivo']}.")
        cada = "; ".join(f"sin {x['quitar'][0]}, {num(x['ventaja'], 2, True)}" if x["ventaja"] is not None
                         else f"sin {x['quitar'][0]}, sin cifra ({x['motivo']})" for x in vs["cada_tienda"])
        sin_cubrir = "; ".join(f"{x['nombre']} ({pd.Timestamp(x['fecha']):%d/%m/%Y}, {x['motivo']})"
                               for x in ev["sin_cubrir"]) or "ninguno"
        lineas += [f"### {NOMBRE_OBJETIVO[objetivo]}", "",
                   f"- **La ventaja se concentra.** Las {len(ap['cinco_primeras'])} series que más aportan suman "
                   f"{num(ap['aporte_cinco_primeras'], 2, True)} de los {num(ap['ventaja'], 2, True)} puntos: "
                   + "; ".join(f"{x['store_id']} {x['dept_id']} ({num(x['aporte'], 2, True)})"
                               for x in ap["cinco_primeras"]) + ".",
                   f"- **Sin algunas tiendas.** {sin_juntas} Sin cada tienda: {cada}.",
                   f"- **Remuestreando tiendas enteras**, el intervalo del 95 % de la ventaja va de "
                   f"{num(it['bajo'], 2, True)} a {num(it['alto'], 2, True)} ({it['unidades']} tiendas, "
                   f"{miles(it['remuestreos'])} remuestreos). El veredicto usa el de series.",
                   f"- **Series en que alguna regla falla menos que el modelo:** {me['cuantas']} de {me['de']}"
                   + (": " + "; ".join(f"{x['store_id']} {x['dept_id']}" for x in me["series"]) + "." if me["series"]
                      else "."),
                   f"- **Eventos del calendario** del {pd.Timestamp(ev['desde']):%d/%m/%Y} al "
                   f"{pd.Timestamp(ev['hasta']):%d/%m/%Y}: {ev['cubiertos']} de {ev['cuantos']} caen en días medidos. "
                   f"Sin cubrir: {sin_cubrir}.",
                   "- **Filas medidas por día de la semana:** "
                   + "; ".join(f"{x['dia']}, {miles(x['filas'])}" for x in di["dias"]) + ".", ""]
    return lineas


NIVEL_TEXTO = {"cadena": "cadena", "estado": "estado", "tienda": "tienda", "categoria": "categoría"}


def md_niveles(r):
    """El apartado «La previsión sumada» de validacion_resultado.md, con el bloque «niveles» del JSON."""
    lineas = ["", "## La previsión sumada", "",
              "La previsión de la cadena, de cada estado, de cada tienda y de cada categoría es la suma de las de sus "
              "series tal como se miden: acotadas en cero y, en unidades, redondeadas antes de sumar. El error y el "
              "sesgo salen de las filas sumadas de todos los orígenes juntos. Es una lectura: el veredicto no cambia.",
              ""]
    for objetivo in OBJETIVOS:
        niv = r["validacion"][objetivo].get("niveles")
        if not niv:
            continue
        cad = niv["cadena"]["origenes"]
        lineas += [f"### {NOMBRE_OBJETIVO[objetivo]}", "",
                   f"En la cadena, el modelo falla menos que la regla que menos falla en cada origen en "
                   f"{cad['origenes_que_gana']} de los {cad['de']} orígenes.", "",
                   "| Nivel | Grupo | Filas sumadas | Error del modelo | Sesgo del modelo | Regla que menos falla | "
                   "Error de la regla | El modelo falla menos |", "|---|---|---|---|---|---|---|---|"]
        for nivel in NIVELES:
            for g in niv[nivel]["grupos"]:
                grupo = f"las {g['series']} series" if nivel == "cadena" else g["grupo"]
                menos = {True: "sí", False: "no"}.get(g["modelo_falla_menos"], "sin cifra")
                lineas.append(f"| {NIVEL_TEXTO[nivel]} | {grupo} | {miles(g['filas_sumadas'])} | "
                              f"{num(g['error_modelo'], 2)} | {num(g['sesgo_modelo'], 2, True)} | "
                              f"{g['regla_que_menos_falla_nombre'] or 'sin cifra'} | {num(g['error_regla'], 2)} | "
                              f"{menos} |")
        lineas.append("")
    return lineas


def resultado_md(r):
    """El texto de informes/validacion_resultado.md, solo con cifras del diccionario del JSON."""
    lineas = ["# La validación del modelo · caso 69", "",
              f"Fecha de los datos: {r['fecha_datos']}. Sale de `{JSON_REL}`, generado por `{SCRIPT_REL}` el "
              f"{r['fecha_ejecucion'][:10]}. Estado: {r['resultado']['estado']}.", ""]
    if "validacion" not in r:
        lineas += ["La validación no llegó a medirse.", "", f"Motivo: {r['resultado']['resumen']}", ""]
        return "\n".join(lineas)
    lineas += ["## El veredicto", ""]
    for objetivo in OBJETIVOS:
        v = r["validacion"][objetivo]["veredicto"]
        i = v["intervalo"]
        lineas.append(f"- **{NOMBRE_OBJETIVO[objetivo]}: {v['veredicto']}.** El modelo falla menos que la regla que "
                      f"menos falla en {v['origenes_que_gana']} de los {v['de']} orígenes; hacían falta "
                      f"{v['minimo']}. Su ventaja es de {num(v['ventaja'], 2, True)} puntos, con un intervalo del 95 % "
                      f"de {num(i['bajo'], 2, True)} a {num(i['alto'], 2, True)}.")
    v0 = r["validacion"][OBJETIVOS[0]]["veredicto"]
    i0 = v0["intervalo"]
    lineas += ["", f"Gana si cumple las dos condiciones de las reglas: al menos {v0['minimo']} orígenes de {v0['de']} "
               f"con el intervalo entero por encima de cero. El intervalo sale de remuestrear {miles(i0['remuestreos'])} veces "
               f"las {i0['unidades']} series enteras, con semilla {i0['semilla']}.", "",
               "## El error frente a las reglas", "",
               f"Error y sesgo por cada 100 vendidos, con las {i0['unidades']} series juntas en los {v0['de']} "
               "orígenes y sin el 25 de diciembre.", "", "| Objetivo | Previsión | Error | Sesgo |", "|---|---|---|---|"]
    for objetivo in OBJETIVOS:
        for e in r["validacion"][objetivo]["errores"]["todas"]:
            lineas.append(f"| {objetivo} | {NOMBRE[e['prevision']]} | {num(e['error'], 2)} | "
                          f"{num(e['sesgo'], 2, True)} |")
    lineas += ["", "## El suavizado exponencial al lado", ""]
    for objetivo in OBJETIVOS:
        s = r["validacion"][objetivo]["suavizado"]
        lineas.append(f"- **{NOMBRE_OBJETIVO[objetivo]}:** el modelo falla menos que el suavizado en "
                      f"{s['origenes_que_gana']} de {s['de']} orígenes. La diferencia es de "
                      f"{num(s['ventaja'], 2, True)} puntos, con un intervalo de {num(s['intervalo']['bajo'], 2, True)} "
                      f"a {num(s['intervalo']['alto'], 2, True)}. Con las mismas pruebas, la lectura es «{s['lectura']}».")
    lineas += ["", "Es una lectura: el veredicto se mide solo frente a las tres reglas.", "",
               "## La recomendación de cada departamento", "",
               "Si el modelo falla de media más que la regla que menos falla en un departamento, se recomienda esa "
               "regla en él. El veredicto principal no cambia.", "",
               "| Objetivo | Departamento | Error del modelo | Regla que menos falla | Error de la regla | Se recomienda |",
               "|---|---|---|---|---|---|"]
    for objetivo in OBJETIVOS:
        for d in r["validacion"][objetivo]["recomendacion_por_departamento"]:
            lineas.append(f"| {objetivo} | {d['departamento']} | {num(d['error_modelo'], 2)} | "
                          f"{d['regla_que_menos_falla_nombre']} | {num(d['error_regla'], 2)} | {d['se_recomienda']} |")
    lineas += ["", "## Los días de evento y los días SNAP", "", "| Objetivo | Días | Error del modelo | Sesgo del modelo |"
               " Error de la regla que menos falla en ellos |", "|---|---|---|---|---|"]
    for objetivo in OBJETIVOS:
        for clave, texto in (("dias_con_evento", "con algún evento"), ("dias_snap", "SNAP del estado de la tienda")):
            lista = r["validacion"][objetivo]["errores"][clave]
            m = cifra(lista, "modelo")
            reglas = [e for e in lista if e["prevision"] in pr.REGLAS and e["error"] is not None]
            mejor = min(reglas, key=lambda e: e["error"]) if reglas else None
            lineas.append(f"| {objetivo} | {texto} | {num(m['error'], 2) if m else 'sin cifra'} | "
                          f"{num(m['sesgo'], 2, True) if m else 'sin cifra'} | "
                          f"{(NOMBRE[mejor['prevision']] + ': ' + num(mejor['error'], 2)) if mejor else 'sin cifra'} |")
    lineas += md_matiza(r)
    lineas += md_niveles(r)
    vias = r.get("vias_de_mejora")
    if vias:
        sin_ganar = [NOMBRE_OBJETIVO[o] for o in OBJETIVOS if r["validacion"][o]["veredicto"]["veredicto"] != "gana"]
        probadas = [x["variable"] for x in vias["variables_nuevas"] if x["probada"]]
        sin_probar = [x["variable"] for x in vias["variables_nuevas"] if x["probada"] is False]
        algoritmos = ", ".join(vias["mejor_modelo"]["probado"]["algoritmos"]) or "los algoritmos de la búsqueda"
        lineas += ["", "## Las tres vías de mejora", "",
                   f"El modelo no gana en: {'; '.join(sin_ganar)}. Las vías van de la más barata a la más cara.", "",
                   f"1. **Mejor modelo.** Se probaron {algoritmos}. Queda {vias['mejor_modelo']['queda']}.",
                   f"2. **Variables nuevas con los datos que ya hay.** Entraron {len(probadas)} variables de la matriz; "
                   f"quedaron fuera {len(sin_probar)}" + (f": {', '.join(sin_probar)}." if sin_probar else "."),
                   "3. **Más información.** "
                   + " ".join(f"{x['dato'].capitalize()}, para {x['para_que']}; quién lo tiene: {x['quien_lo_tiene']}."
                              for x in vias["informacion_nueva"])]
    lineas += ["", "## Datos personales", ""]
    if r["datos_personales"]["proteccion_datos_json"]:
        lineas.append(f"La protección de los datos está descrita en `{PROTECCION_REL}`.")
    else:
        lineas.append(f"No existe `{PROTECCION_REL}`: los datos no pasaron por la protección. Las tablas son ventas por "
                      "departamento y tienda y esta validación no usa ninguna columna sobre personas.")
    largo = r["validacion"][max(OBJETIVOS, key=lambda o: HORIZONTE[o])]
    desde, hasta = (pd.Timestamp(largo[k]) for k in ("primer_dia_previsto", "ultimo_dia_previsto"))
    lineas += ["", "## Límites", "",
               f"- Los días previstos van del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}. La prueba final lo confirma una "
               "sola vez.",
               "- El modelo se ajustó una vez con la construcción y no se reajusta en la validación. En la ejecución "
               "diaria se reajustaría.",
               "- Las cifras miden lo vendido. Los datos no traen existencias, así que un día a cero no dice si había "
               "producto.",
               "- El modelo detecta asociaciones con el calendario y con la venta pasada. No dice qué causa la venta.",
               "- Si cambia la forma de vender, el error sube y hay que volver a medir.", "",
               "## Lo que puede decidir el responsable del caso", "",
               "- Aprobar el veredicto de cada objetivo y la recomendación por departamento, para pasar al informe.",
               "- Pedir otra cosa antes del informe.", ""]
    return "\n".join(lineas)


# ══ 11. Principal ═══════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Lee preseleccion.json, preparacion.json y particion.json y compara las huellas de las cuatro tablas con las que
    dejaron los pasos anteriores, sin cargarlas."""
    paradas, leidos = [], {}
    for rel in (PRESELECCION_REL, PREPARACION_REL, PARTICION_REL):
        d = leer_json(raiz, rel)
        if d is None:
            paradas.append(f"falta {rel}")
            continue
        leidos[rel] = d
        if d.get("resultado", {}).get("estado") not in ("OK", "AVISO"):
            paradas.append(f"{rel} está en {d.get('resultado', {}).get('estado')}: no se empieza")
    esperadas = {}
    for e in leidos.get(PREPARACION_REL, {}).get("entradas", []):
        esperadas[e.get("ruta")] = e.get("sha256")
    for p in leidos.get(PARTICION_REL, {}).get("partes", []):
        if p.get("ruta"):
            esperadas[p["ruta"]] = p.get("sha256")
    huellas = {}
    for rel in (MODELO_ENT_REL, MODELO_VAL_REL, SERIES_ENT_REL, SERIES_VAL_REL):
        ruta = raiz / rel
        huellas[rel] = huella(ruta) if ruta.exists() else None
        if huellas[rel] is None or huellas[rel] != esperadas.get(rel):
            paradas.append(f"la huella de {rel} no es la de los pasos anteriores")
    return paradas, leidos, huellas


def principal(raiz, huella_receta, max_origenes=None, max_series=None):
    """Lee la receta, ajusta, abre la validación una vez, mide y devuelve el JSON, la tabla por origen y las
    previsiones."""
    muestra = max_origenes is not None or max_series is not None
    r = {"metodo": "aprendizaje-automatico", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [], "resultado": {}, "pendientes": [], "puerta_de_juan": False,
         "rama": "prevision"}
    registro = []
    r["tablas_abiertas"] = registro
    artefactos = [JSON_REL, CSV_REL, PARQUET_REL, MD_REL]

    # 1. La receta, antes de cargar nada de la validación
    receta, paradas, huellas_receta = leer_receta(raiz, huella_receta)
    r["receta"] = {"ruta": BUSQUEDA_REL, "huella": huellas_receta}
    if not paradas:
        registro.append({"paso": "receta", "ruta": BUSQUEDA_REL})
        paradas_inicio, leidos, huellas = al_empezar(raiz)
        paradas += paradas_inicio
    if paradas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "; ".join(paradas),
                          "artefactos": [JSON_REL, MD_REL], "siguiente": "revisar la receta y los pasos anteriores"}
        return r, None, None
    r["receta"]["ganador"] = {o: {**{k: g.get(k) for k in ("algoritmo", "clase", "ficha", "hiperparametros", "semilla",
                                                          "columnas", "n_columnas", "preprocesador")},
                                  "aprobado_por": APROBADO_POR,
                                  "aprobado_por_fuente": f"{PLANTEAMIENTOS_REL} §2, «Ganador»"}
                              for o, g in receta["ganador"].items()}
    preseleccion, preparacion, particion = leidos[PRESELECCION_REL], leidos[PREPARACION_REL], leidos[PARTICION_REL]

    # 2. El entrenamiento y el ajuste: la validación todavía no se ha cargado
    tablas = {"me": cargar(raiz, MODELO_ENT_REL, registro, "entrenamiento"),
              "se": cargar(raiz, SERIES_ENT_REL, registro, "entrenamiento")}
    filas_busqueda = (receta["json"].get("tabla") or {}).get("filas")
    # Orden por fecha y serie (error 7), el mismo con que la búsqueda ajustó
    tablas["me_ajuste"] = tablas["me"].sort_values([COLUMNA_FECHA] + CLAVE_SERIE, kind="stable").reset_index(drop=True)
    columnas_evento = [c for c in tablas["me"].columns if c.startswith("evento_")]

    # 3. La validación, una vez
    tablas["mv"] = cargar(raiz, MODELO_VAL_REL, registro, "validacion")
    tablas["sv"] = cargar(raiz, SERIES_VAL_REL, registro, "validacion")
    parte_val = next((p for p in particion.get("partes", []) if p.get("parte") == "validacion"), {})
    dias_val = pd.DatetimeIndex(sorted(tablas["mv"][COLUMNA_FECHA].unique()))
    tablas_como_la_particion = bool(
        len(tablas["mv"]) == parte_val.get("filas") and len(tablas["sv"]) == parte_val.get("filas")
        and len(dias_val) == parte_val.get("dias") and f"{dias_val.min():%Y-%m-%d}" == parte_val.get("fecha_min")
        and f"{dias_val.max():%Y-%m-%d}" == parte_val.get("fecha_max")
        and tablas["mv"][CLAVE_SERIE].drop_duplicates().shape[0] == parte_val.get("combinaciones")
        and (filas_busqueda is None or len(tablas["me"]) == filas_busqueda))
    for clave, rel in (("me", MODELO_ENT_REL), ("mv", MODELO_VAL_REL), ("se", SERIES_ENT_REL),
                       ("sv", SERIES_VAL_REL)):
        r["entradas"].append({"ruta": rel, "sha256": huellas[rel], "filas": len(tablas[clave]),
                              "columnas": tablas[clave].shape[1]})
    for rel in (BUSQUEDA_REL, PRESELECCION_REL, PREPARACION_REL, PARTICION_REL):
        r["entradas"].append({"ruta": rel, "sha256": huella(raiz / rel)})

    # El calendario, solo para contar los eventos de la validación (lo que matiza la ventaja); se conoce de
    # antemano (reglas, apartado 5) y se corta en el periodo de la validación nada más leerlo
    calendario = cargar(raiz, CALENDARIO_REL, registro, "calendario")
    r["entradas"].append({"ruta": CALENDARIO_REL, "sha256": huella(raiz / CALENDARIO_REL), "filas": len(calendario),
                          "columnas": calendario.shape[1]})
    tablas["periodo"] = (dias_val.min(), dias_val.max())
    tablas["eventos"] = eventos_del_periodo(calendario, *tablas["periodo"])
    del calendario

    # Las dos dimensiones, solo para saber la categoría de cada departamento y el estado de cada tienda (la previsión
    # sumada); no traen ventas
    dimensiones = {}
    for rel in (DIM_PRODUCTO_REL, DIM_TIENDA_REL):
        dimensiones[rel] = cargar(raiz, rel, registro, "dimension")
        r["entradas"].append({"ruta": rel, "sha256": huella(raiz / rel), "filas": len(dimensiones[rel]),
                              "columnas": dimensiones[rel].shape[1]})

    # La historia de las dos tablas tiene que decir la misma venta los mismos días (segunda vía de la historia)
    modelo_todo = pd.concat([tablas["me"], tablas["mv"]], ignore_index=True)[CLAVES + list(OBJETIVOS)]
    series_todo = pd.concat([tablas["se"], tablas["sv"]], ignore_index=True)[CLAVES + list(OBJETIVOS)]
    cruce = modelo_todo.merge(series_todo, on=CLAVES, how="left", suffixes=("", "_s"), validate="one_to_one")
    historia_igual = bool(cruce[[f"{o}_s" for o in OBJETIVOS]].notna().all().all() and all(
        np.allclose(cruce[o].to_numpy(dtype="float64"), cruce[f"{o}_s"].to_numpy(dtype="float64"), rtol=0, atol=1e-9)
        for o in OBJETIVOS))

    # Los orígenes y las series
    origenes = generar_origenes(PRIMER_ORIGEN, N_ORIGENES, PASO_ORIGENES)
    estado_origenes = comprobar_origenes(origenes, HORIZONTE, dias_val)
    series = sorted(map(tuple, tablas["mv"][CLAVE_SERIE].drop_duplicates().to_numpy().tolist()))
    if muestra:
        origenes = origenes[: max_origenes or len(origenes)]
        series = series[: max_series or len(series)]
        # El ajuste sigue con todo el entrenamiento (la receta); la muestra solo recorta lo que se prevé
        for clave in ("me", "se", "mv", "sv"):
            dentro = pd.MultiIndex.from_frame(tablas[clave][CLAVE_SERIE]).isin(series)
            tablas[clave] = tablas[clave][dentro].reset_index(drop=True)
    if not estado_origenes["bien"]:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto",
                          "resumen": f"algún horizonte cae fuera de la validación: {estado_origenes['dias_fuera']}",
                          "artefactos": [JSON_REL, MD_REL], "siguiente": "revisar los orígenes"}
        return r, None, None
    # Cada serie medida con su categoría y su estado; para si un departamento tiene dos categorías o una tienda dos
    # estados, porque la suma no sabría a qué grupo va
    try:
        tablas["padres"] = padres_de_las_series(dimensiones[DIM_PRODUCTO_REL], dimensiones[DIM_TIENDA_REL], series)
    except ValueError as e:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"la previsión sumada no se puede montar: {e}",
                          "artefactos": [JSON_REL, MD_REL], "siguiente": "revisar las dimensiones de producto y tienda"}
        return r, None, None

    # 4 a 8. Cada objetivo
    r["validacion"], previsiones, inicio = {}, [], time.perf_counter()
    for objetivo in OBJETIVOS:
        res, prev = validar_objetivo(objetivo, receta["ganador"][objetivo], tablas, origenes, columnas_evento, series)
        r["validacion"][objetivo] = res
        previsiones.append(prev.assign(objetivo=objetivo))
    segundos = time.perf_counter() - inicio

    # Las validaciones del §9 y las propias de este paso, calculadas con lo ejecutado
    texto_propio = Path(__file__).read_text(encoding="utf-8")
    fuera = {f["variable"] for f in preparacion.get("fuera", [])}
    entradas_modelo = {c for o in OBJETIVOS for c in entrada_de(o, columnas_evento)}
    controles = {o: r["validacion"][o]["control"] for o in OBJETIVOS}
    citas = [BUSQUEDA_REL, PLANTEAMIENTOS_REL, PRESELECCION_REL, PREPARACION_REL, PARTICION_REL, PIEZA_REL] + \
        [g.get("ficha") for g in receta["ganador"].values()]
    texto_plant = (raiz / PLANTEAMIENTOS_REL).read_text(encoding="utf-8")
    huellas_despues = {rel: huella(raiz / rel) for rel in huellas}
    v = {}
    v["sin_filas_de_ajuste"] = all(c["sin_filas_de_ajuste"] for c in controles.values())
    v["semillas"] = all(c["semilla"] == SEMILLA for c in controles.values()) and all(
        g.get("semilla") == SEMILLA for g in receta["ganador"].values())
    v["validacion_una_vez"] = orden_de_lectura_bien(registro)
    v["columnas_de_preseleccion"] = all(
        g["columnas"] == [c for c in preseleccion["objetivos"][o]["columnas_finales"]["HistGradientBoosting"]
                          if not c.startswith(FUERA_PREFIJOS)] for o, g in receta["ganador"].items())
    v["citas_existen"] = all(c and (raiz / c).exists() for c in citas) and all(t in texto_plant
                                                                              for t in TEXTO_APROBACION)
    v["reproducible"] = all(c["reproducible"] for c in controles.values())
    v["sin_identificadores_ni_posteriores"] = not (entradas_modelo & fuera)
    v["sin_resultados_escritos"] = buscar_resultados_escritos(texto_propio) == []
    v["canario_objetivo_barajado"] = all(r["validacion"][o]["canario"]["barajado_pierde_la_senal"]
                                         and r["validacion"][o]["canario"]["fuga_se_ve"] for o in OBJETIVOS)
    v["objetivo_conocido_al_entrenar"] = all(c["objetivo_conocido_al_entrenar"] for c in controles.values())
    v["recursiva_completa_sin_negativas"] = all(c["recursiva"] for c in controles.values())
    v["intervalo_por_entidad"] = all(c["intervalo_por_entidad"] for c in controles.values())
    v["origenes_bien"] = estado_origenes["bien"]
    v["sin_prueba_final"] = sin_prueba_final(dias_val, FECHA_DATOS) and sin_prueba_final(
        tablas["sv"][COLUMNA_FECHA], FECHA_DATOS) and not any(NO_SE_ABRE.search(Path(x["ruta"]).stem) for x in registro)
    v["mismas_filas"] = all(c["mismas_filas"] for c in controles.values())
    v["ventaja_con_la_regla_de_cada_origen"] = all(c["ventaja_otro_camino"] for c in controles.values())
    v["sin_dias_fuera_del_error"] = all(c["sin_dias_fuera"] for c in controles.values())
    v["sin_meses_parciales"] = all(c["sin_meses_parciales"] for c in controles.values())
    v["suavizado_sin_futuro"] = all(c["suavizado_sin_futuro"] for c in controles.values())
    v["dias_previstos_por_serie"] = all(
        r["validacion"][o]["dias_previstos_por_serie"] == len(origenes) * HORIZONTE[o]
        and r["validacion"][o]["dias_distintos_por_serie"] == len(origenes) * HORIZONTE[o] for o in OBJETIVOS)
    v["reglas_primer_origen_a_mano"] = all(c["reglas_a_mano"] for c in controles.values())
    v["historia_igual_en_las_dos_tablas"] = historia_igual
    v["receta_reproducida"] = None if any(c["receta_reproducida"] is None for c in controles.values()) else all(
        c["receta_reproducida"] for c in controles.values())
    v["pieza_igual_a_la_comun"] = PIEZA_COMUN.exists() and huella(PIEZA_CASO) == huella(PIEZA_COMUN)
    v["tablas_como_la_particion"] = tablas_como_la_particion
    v["entradas_sin_cambiar"] = huellas_despues == huellas and huella(raiz / BUSQUEDA_REL) == huella_receta
    for nombre in ("con_probabilidad", "recalibrado_si_hace_falta", "probabilidad_media_cerca_de_la_tasa"):
        v[nombre] = None
    # Las sumas por serie solo sirven para el intervalo; no van al JSON
    for o in OBJETIVOS:
        r["validacion"][o].pop("sumas")
        r["validacion"][o].pop("control")
    v["rotulos_de_filas"] = rotulos_de_filas(r["validacion"]) == []
    r["validaciones"] = v
    r["validaciones_nulas"] = {
        "con_probabilidad": "no aplica: objetivo de cantidad", "recalibrado_si_hace_falta": "no aplica: sin equilibrar",
        "probabilidad_media_cerca_de_la_tasa": "no aplica: objetivo de cantidad",
        "receta_reproducida": None if v["receta_reproducida"] is not None else
        "busqueda.json no trae la cifra de entrenamiento del reajuste"}
    r["controles"] = {o: c for o, c in controles.items()}
    r["origenes"] = {"valores": origenes, "estado": estado_origenes["bien"], "primero": PRIMER_ORIGEN,
                     "cada": PASO_ORIGENES, "fuente": f"{PLANTEAMIENTOS_REL} §2, decisión 1"}
    r["series"] = {"cuantas": len(series), "muestra": muestra}
    r["datos_personales"] = {"proteccion_datos_json": (raiz / PROTECCION_REL).exists(),
                             "columnas_de_personas_usadas": []}
    r["teoria_aplicada"] = TEORIA
    r["huellas_despues"] = huellas_despues
    r["segundos"] = segundos
    r["parametros"] = [
        {"nombre": "orígenes", "valor": f"{N_ORIGENES}, cada {PASO_ORIGENES} días desde {PRIMER_ORIGEN:%Y-%m-%d}",
         "origen": "planteamientos §2, decisión 1"},
        {"nombre": "orígenes que hay que ganar", "valor": f"{PROPORCION_ORIGENES:.0%} hacia arriba",
         "origen": "reglas, apartado 7, «Qué cuenta como mejora»"},
        {"nombre": "remuestreos del intervalo", "valor": REMUESTREOS, "origen": "planteamientos §2, decisión 3"},
        {"nombre": "semilla", "valor": SEMILLA, "origen": "planteamientos §2, decisión 3; la receta"},
        {"nombre": "percentiles", "valor": list(PERCENTILES), "origen": "planteamientos §2, decisión 3"},
        {"nombre": "tramos del valor real", "valor": TRAMOS, "origen": "guía de evaluación continua §7"},
        {"nombre": "límite de la sospecha de fuga", "valor": LIMITE_FUGA, "origen": "reglas, apartado 7, «Lo esperable»"},
        {"nombre": "ventaja que se revisa", "valor": LIMITE_VENTAJA, "origen": "reglas, apartado 7, «Lo esperable»"},
        {"nombre": "suavizado", "valor": "ExponentialSmoothing(trend=None, seasonal='add', seasonal_periods=7)",
         "origen": "planteamientos §2, decisión 8"},
        {"nombre": "meses que se comparan", "valor": "los que tienen todos sus días entre el primer y el último día "
                                                     "previsto de cada objetivo",
         "origen": "planteamientos §2, decisión 5; reglas, apartado 5"},
        {"nombre": "sesgo en los días a cero", "valor": "error medio con signo por fila",
         "origen": "la cifra por cada 100 divide por cero; sesgo de ec.medidas"}]

    # Lo que haría sospechar, con las vallas de «Lo esperable»
    sospechas = []
    for o in OBJETIVOS:
        e = r["validacion"][o]["veredicto"]
        if e["error_modelo"] < LIMITE_FUGA:
            sospechas.append(f"{o}: el modelo falla menos de {LIMITE_FUGA:.0f}, se trata como fuga hasta descartarla")
        if e["ventaja"] > LIMITE_VENTAJA:
            sospechas.append(f"{o}: ventaja de más de {LIMITE_VENTAJA:.0f} puntos, se revisa si usa el futuro")
    r["sospechas"] = sospechas
    if any(r["validacion"][o]["veredicto"]["veredicto"] != "gana" for o in OBJETIVOS):
        r["vias_de_mejora"] = vias_de_mejora(receta["json"], preparacion, raiz)

    # La tabla por origen y las previsiones
    filas_csv = []
    for o in OBJETIVOS:
        for e in r["validacion"][o]["errores"]["por_origen"]:
            filas_csv.append({"objetivo": o, "origen": e["grupo"], "prevision": e["prevision"], "error": e["error"],
                              "sesgo": e["sesgo"], "filas": e["filas"]})
    tabla_csv = pd.DataFrame(filas_csv)
    todas = pd.concat(previsiones, ignore_index=True)
    todas = todas.rename(columns={"unidades": "real_unidades", "dolares": "real_dolares"})
    todas["real"] = np.where(todas["objetivo"] == "unidades", todas.get("real_unidades"), todas.get("real_dolares"))
    tabla_prev = todas[["objetivo", "origen", "store_id", "dept_id", "date", "h", "real", "modelo"] + list(pr.REGLAS)
                       + ["suavizado", COLUMNA_FUERA]].sort_values(["objetivo", "origen", "store_id", "dept_id",
                                                                     "date"]).reset_index(drop=True)
    r["previsiones"] = {"ruta": PARQUET_REL, "filas": len(tabla_prev),
                        "valores": "acotados en cero y, en unidades, redondeados: como se miden"}

    # Las comprobaciones de lo que matiza la ventaja y de la previsión sumada: no son validaciones del §9, pero una en
    # rojo para igual
    rojas_robustez = [f"{o}.{bloque}.{k}" for o in OBJETIVOS for bloque in ("robustez", "niveles")
                      for k, x in r["validacion"][o][bloque]["comprobaciones"].items() if x is not True]
    bien = all(x for x in v.values() if x is not None) and not rojas_robustez
    resumen = "; ".join(f"{o}: {r['validacion'][o]['veredicto']['veredicto']} ("
                        f"{r['validacion'][o]['veredicto']['origenes_que_gana']} de {len(origenes)} orígenes, "
                        f"intervalo de la ventaja {r['validacion'][o]['veredicto']['intervalo']['bajo']:.2f} a "
                        f"{r['validacion'][o]['veredicto']['intervalo']['alto']:.2f})" for o in OBJETIVOS)
    if bien:
        r["puerta_de_juan"] = True
        r["pendientes"] = [{"id": "P-01", "tabla": "validacion", "columna": "veredicto de cada objetivo",
                            "pregunta": "¿Apruebas el veredicto de cada objetivo y la recomendación por departamento "
                                        "antes del informe? Puerta del responsable del caso", "opciones": ["aprobar", "otra decisión"]}]
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto" if sospechas else "medio",
                          "resumen": f"{resumen}; validaciones en verde; el veredicto espera al responsable del caso"
                                     + (f"; sospechas: {sospechas}" if sospechas else ""),
                          "artefactos": artefactos, "siguiente": "El responsable del caso aprueba el veredicto; después, el informe"}
    else:
        falsas = [k for k, x in v.items() if x is False] + rojas_robustez
        r["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{resumen}; validaciones en rojo: {falsas}",
                          "artefactos": [JSON_REL, MD_REL], "siguiente": "revisar las validaciones en rojo"}
        tabla_csv = tabla_prev = None
    return r, tabla_csv, tabla_prev


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", type=Path, default=CASO)
    argumentos.add_argument("--huella-receta", default=HUELLA_RECETA)
    argumentos.add_argument("--muestra-origenes", type=int, default=None)
    argumentos.add_argument("--muestra-series", type=int, default=None)
    args = argumentos.parse_args()
    raiz = args.raiz.resolve()
    if args.muestra_origenes is not None or args.muestra_series is not None:
        inicio = time.perf_counter()
        medido, _, _ = principal(raiz, args.huella_receta, args.muestra_origenes, args.muestra_series)
        total = time.perf_counter() - inicio
        print(f"MUESTRA · {medido['resultado']['estado']} · {args.muestra_origenes} orígenes, "
              f"{args.muestra_series} series, en {total:.1f} s")
        print(f"validaciones en rojo: {[k for k, x in medido.get('validaciones', {}).items() if x is False]}")
        for o, val in medido.get("validacion", {}).items():
            print(f"{o}: robustez en {val['tiempos']['robustez']:.2f} s; comprobaciones "
                  f"{val['robustez']['comprobaciones']}")
            print(f"{o}: niveles en {val['tiempos']['niveles']:.2f} s; grupos "
                  f"{ {n: val['niveles'][n]['cuantos'] for n in NIVELES} }; filas sumadas por grupo "
                  f"{sorted({g['filas_sumadas'] for n in NIVELES for g in val['niveles'][n]['grupos']})}; "
                  f"comprobaciones {val['niveles']['comprobaciones']}")
        estimado = 0.0
        n_o = len(medido.get("origenes", {}).get("valores", [])) or 1
        n_s = medido.get("series", {}).get("cuantas") or 1
        for o, val in medido.get("validacion", {}).items():
            t = val["tiempos"]
            # El ajuste no depende de la muestra; la recursión y las reglas crecen con los orígenes; el suavizado,
            # con los orígenes y las series
            parte = (t["ajuste"] * 4 + (t["recursion"] + t["reglas"]) * N_ORIGENES / n_o * 1.2
                     + t["suavizado"] * N_ORIGENES / n_o * 70 / n_s)
            estimado += parte
            print(f"{o}: ajuste {t['ajuste']:.1f} s, recursión {t['recursion']:.1f} s, reglas {t['reglas']:.1f} s, "
                  f"suavizado {t['suavizado']:.1f} s; estimado para la ejecución entera {parte / 60:.1f} min")
        print(f"estimado total: {estimado / 60:.1f} min")
        sys.exit(0 if medido.get("puerta_de_juan") else 1)
    tabla_csv = tabla_prev = None
    try:
        resultado, tabla_csv, tabla_prev = principal(raiz, args.huella_receta)
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
        tabla_prev.to_parquet(raiz / PARQUET_REL, index=False)
    (raiz / MD_REL).write_text(resultado_md(limpio), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado.get("puerta_de_juan") else 1)
