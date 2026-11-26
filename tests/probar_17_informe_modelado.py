"""Prueba de scripts/17_informe_modelado.py, con JSON pequeños escritos aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_informe_modelado/ una carpeta con la
estructura del caso (los siete JSON del paso 5 en pequeño, una tabla de previsiones de cuatro series, los planteamientos
y las reglas con lo que el script cita escrito en la copia), ejecuta el script sobre ella con --raiz y la borra al
acabar. Importa el script que prueba, que tiene su trabajo bajo __main__.

Los casos que tienen que fallar si el código está mal:
  1. un JSON de entrada en ERROR;
  2. un apartado que falta o fuera de orden;
  3. un número del informe que no está en modelado.json;
  4. una cifra sin clave de origen;
  5. el desequilibrio o el corte quitados en vez de explicados;
  6. el apartado de datos personales que no dice que falta proteccion-datos.json;
  7. el script que abre una tabla de hechos;
  8. una validación escrita con su resultado puesto (error 24);
  9. el informe que no nombra en «Límites» un evento sin cubrir;
 10. una cifra de robustez que no está en modelado.json;
 11. validacion.json sin el bloque «robustez»;
 12. una cifra de la previsión sumada (bloque «niveles») que no está en modelado.json;
 13. validacion.json sin el bloque «niveles».
Y los de las demás validaciones del script: una cita que no está en su fichero, un redondeo distinto del escrito, una
fecha de los datos distinta, el veredicto sin su aprobación escrita, unas figuras con otras filas que las medidas y un
texto con «, y».
El control que no debe disparar: el script entero sobre la carpeta limpia termina en OK, con todas las validaciones en
verde, los catorce apartados en su orden, las cuatro figuras y cada cifra con su origen.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "17_informe_modelado.py"
TMP = RAIZ / "tests" / "tmp_informe_modelado"
FALLOS = []
FECHA = "2015-05-22"
HORIZONTE = {"unidades": 2, "dolares": 3}
ORIGENES = ["2014-05-22", "2014-06-19"]
TIENDAS = ["T_0", "T_1"]
DEPARTAMENTOS = ["D_A", "D_B"]
REGLAS = ["repetir_semana_anterior", "media_28_dias", "media_mismo_dia_4_semanas"]
PREDICTORES = ["modelo"] + REGLAS + ["trivial", "suavizado"]
NOMBRE_REGLA = {"media_28_dias": "la media de los últimos 28 días",
                "media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores"}
APROBACION = ("**Veredicto de la validación (el responsable del caso, 25/11/2026, «Sí, apruebo el veredicto»):** el modelo gana "
              "en la prueba.")
PLANTEAMIENTOS = (f"# Planteamientos de la prueba\n\n6. **Un modelo para las 70 combinaciones.** Uno por serie "
                  f"multiplicaría por 70 el coste de\n   la búsqueda.\n\n{APROBACION}\n")
REGLAS_MD = ("# Reglas de la prueba\n\n### Lo que no se puede calcular\n\n- El dinero que ahorra la previsión: los datos "
             "no traen coste, margen ni existencias.\n- Las ventas perdidas por estante vacío: un cero no dice si había "
             "producto.\n")


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar(ruta, nombre):
    """Importa un fichero de Python por su ruta."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Datos pequeños ──────────────────────────────────────────────────────────
def previsiones():
    """La tabla de previsiones de la validación: cuatro series, dos orígenes, 2 días en unidades y 3 en dólares; en
    dólares, el 25 de diciembre de cada serie queda fuera del error."""
    rng = np.random.default_rng(7)
    filas = []
    for objetivo, h_max in HORIZONTE.items():
        for k, origen in enumerate(ORIGENES):
            for tienda in TIENDAS:
                for dept in DEPARTAMENTOS:
                    for h in range(1, h_max + 1):
                        fecha = pd.Timestamp(origen) + pd.Timedelta(h, "D")
                        fuera = objetivo == "dolares" and k == 1 and h == 3
                        real = float(rng.integers(5, 90))
                        filas.append({"objetivo": objetivo, "origen": pd.Timestamp(origen), "store_id": tienda,
                                      "dept_id": dept, "date": fecha, "h": h, "real": real,
                                      "modelo": real + float(rng.integers(-5, 6)), "fuera_del_error": fuera})
    t = pd.DataFrame(filas)
    t["origen"] = t["origen"].astype("datetime64[us]")
    t["date"] = t["date"].astype("datetime64[us]")
    return t


def entrada(rng, grupo, prevision, filas):
    """Una fila de una lista de errores, como la escribe la validación."""
    return {"grupo": grupo, "prevision": prevision, "filas": filas, "error": float(rng.uniform(10, 30)),
            "sesgo": float(rng.uniform(-3, 3))}


def robustez_json(objetivo, filas, f):
    """El bloque «robustez» de un objetivo, como lo escribe la validación, con cifras distintas de las demás."""
    aportes = [("T_0", "D_A", 0.875), ("T_1", "D_A", 0.625), ("T_0", "D_B", 0.5), ("T_1", "D_B", 0.25)]
    series = [{"store_id": s, "dept_id": d, "aporte": a} for s, d, a in aportes]
    if objetivo == "unidades":
        sin_cubrir = [{"nombre": "Thanksgiving", "fecha": "2014-11-27", "motivo": "fuera del horizonte"},
                      {"nombre": "Christmas", "fecha": "2014-12-25", "motivo": "fuera del horizonte"},
                      {"nombre": "NewYear", "fecha": "2015-01-01", "motivo": "fuera del horizonte"}]
        dias = [8, 0, 0, 0, 4, 4, 0]
    else:
        sin_cubrir = [{"nombre": "Christmas", "fecha": "2014-12-25", "motivo": "fuera del error"}]
        dias = [4, 0, 0, 4, 4, 4, 4]
    eventos = [("MemorialDay", "2014-05-26"), ("Thanksgiving", "2014-11-27"), ("Christmas", "2014-12-25"),
               ("NewYear", "2015-01-01")]
    fuera = {x["nombre"] for x in sin_cubrir}
    return {
        "que_es": "lo que matiza la ventaja", "filas": f,
        "aporte_por_serie": {"series": series, "cinco_primeras": series, "aporte_cinco_primeras": 2.25,
                             "suma_de_todas": 2.25, "ventaja": 2.25, "filas": f, "que_es": "aporte de cada serie"},
        "ventaja_sin": {"cada_tienda": [{"quitar": ["T_0"], "series": 2, "de": 4, "ventaja": 1.125, "filas": f},
                                        {"quitar": ["T_1"], "series": 2, "de": 4, "ventaja": 0.6875, "filas": f}],
                        "juntas": {"quitar": ["T_1"], "series": 2, "de": 4, "ventaja": 0.6875, "filas": f},
                        "que_es": "la ventaja sin tiendas", "juntas_origen": "las que señaló el auditor"},
        "intervalo_por_tienda": {"bajo": 0.4375, "alto": 4.125, "remuestreos": 1000, "semilla": 42,
                                 "percentiles": [2.5, 97.5], "unidad": "tienda", "unidades": 2,
                                 "que_se_remuestrea": "las tiendas enteras", "filas": f, "que_es": "intervalo"},
        "series_con_alguna_regla_mejor": {"cuantas": 1, "de": 4, "filas": f, "que_es": "series", "series": [
            {"store_id": "T_1", "dept_id": "D_B", "regla": "media_28_dias",
             "regla_nombre": "la media de los últimos 28 días", "error_de_la_regla": 12.5, "error_del_modelo": 13.5}]},
        "eventos": {"cuantos": 4, "cubiertos": 4 - len(sin_cubrir), "sin_cubrir": sin_cubrir,
                    "por_evento": [{"nombre": n, "fecha": d, "filas_medidas": 0 if n in fuera else 4}
                                   for n, d in eventos],
                    "desde": "2014-05-23", "hasta": "2015-05-22", "filas": f, "que_es": "eventos"},
        "filas_por_dia_de_la_semana": {"dias": [{"dia": d, "filas": n} for d, n in zip(
            ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"), dias)],
            "total": filas, "filas": f, "que_es": "filas por día"},
        "comprobaciones": {"aporte_suma_la_ventaja": True, "intervalo_por_tienda_entera": True,
                           "eventos_solo_en_dias_medidos": True, "dias_de_la_semana_suman_las_filas": True}}


def niveles_json(objetivo, f):
    """El bloque «niveles» de un objetivo, como lo escribe la validación, con cifras distintas de las demás."""
    filas_sumadas = 2 * HORIZONTE[objetivo] - (1 if objetivo == "dolares" else 0)
    fs = f"validacion: {filas_sumadas} filas sumadas (grupo, origen y día) de 2 orígenes"

    def grupo(nombre, series, base):
        """Un grupo con el error y el sesgo de sus cinco previsiones; base mueve las cifras de un grupo a otro."""
        errores = [{"prevision": p, "error": base + 1.5 * i, "sesgo": -0.375 - 0.25 * i, "filas": fs}
                   for i, p in enumerate(["modelo"] + REGLAS + ["suavizado"])]
        return {"grupo": nombre, "series": series, "filas_sumadas": filas_sumadas, "origenes": 2, "errores": errores,
                "error_modelo": base, "sesgo_modelo": -0.375, "regla_que_menos_falla": "repetir_semana_anterior",
                "regla_que_menos_falla_nombre": "repetir la semana anterior", "error_regla": base + 1.5,
                "sesgo_regla": -0.625, "modelo_falla_menos": True, "filas": fs}

    return {
        "que_es": "la previsión sumada", "como_se_suma": "de abajo arriba", "filas": f,
        "padres": {"categoria": {"D_A": "CAT_A", "D_B": "CAT_B"}, "estado": {"T_0": "ST_A", "T_1": "ST_A"}},
        "cadena": {"grupos": [grupo("cadena", 4, 6.4375)], "cuantos": 1, "filas": fs,
                   "origenes": {"origenes_que_gana": 2, "de": 2, "filas": fs, "que_es": "orígenes", "por_origen": []}},
        "estado": {"grupos": [grupo("ST_A", 4, 6.4375)], "cuantos": 1, "filas": fs},
        "tienda": {"grupos": [grupo("T_0", 2, 8.0625), grupo("T_1", 2, 9.3125)], "cuantos": 2, "filas": fs},
        "categoria": {"grupos": [grupo("CAT_A", 2, 10.5625), grupo("CAT_B", 2, 31.0625)], "cuantos": 2, "filas": fs},
        "comprobaciones": {"un_padre_por_hijo": True, "grupos_completos": True, "sumas_cuadran": True,
                           "cadena_igual_a_las_series_sumadas": True}}


def validacion_json(tabla):
    """validacion.json en pequeño, con las claves que cita el informe."""
    rng = np.random.default_rng(3)
    v = {"metodo": "aprendizaje-automatico", "script": "scripts/16_validacion.py", "fecha_datos": FECHA,
         "resultado": {"estado": "PARADO"},
         "receta": {"ganador": {o: {"aprobado_por": "el responsable del caso, 25/11/2026, «Apruebo el ganador»"}
                                for o in HORIZONTE}},
         "validacion": {},
         "validaciones": {"sin_filas_de_ajuste": True, "semillas": True, "con_probabilidad": None},
         "validaciones_nulas": {"con_probabilidad": "no aplica: objetivo de cantidad",
                                "recalibrado_si_hace_falta": "no aplica: sin equilibrar",
                                "probabilidad_media_cerca_de_la_tasa": "no aplica: objetivo de cantidad"},
         "series": {"cuantas": 4, "muestra": False},
         "datos_personales": {"proteccion_datos_json": False, "columnas_de_personas_usadas": []},
         "parametros": [{"nombre": "límite de la sospecha de fuga", "valor": 5.0, "origen": "reglas, apartado 7"},
                        {"nombre": "ventaja que se revisa", "valor": 15.0, "origen": "reglas, apartado 7"},
                        {"nombre": "sesgo en los días a cero", "valor": "error medio con signo por fila",
                         "origen": "la cifra por cada 100 divide por cero"}],
         "segundos": 12.3, "sospechas": [],
         "previsiones": {"ruta": "data/processed/previsiones_validacion.parquet", "filas": len(tabla),
                         "valores": "acotados en cero y, en unidades, redondeados: como se miden"}}
    for o, h_max in HORIZONTE.items():
        t = tabla[tabla["objetivo"] == o]
        medidas = int((~t["fuera_del_error"]).sum())
        f = f"validacion: {medidas} filas de 2 orígenes"
        recomendacion = []
        for i, d in enumerate(DEPARTAMENTOS):
            regla = REGLAS[1 + i]
            recomendacion.append({"departamento": d, "error_modelo": 20.0 + i, "sesgo_modelo": 1.0,
                                  "regla_que_menos_falla": regla, "regla_que_menos_falla_nombre": NOMBRE_REGLA[regla],
                                  "error_regla": 21.0 - 2 * i, "se_recomienda": "el modelo" if i == 0 else
                                  NOMBRE_REGLA[regla], "filas": f})
        v["validacion"][o] = {
            "horizonte": h_max, "origenes": ORIGENES, "filas_previstas": len(t), "filas_medidas": medidas,
            "filas_fuera_del_error": len(t) - medidas, "dias_fuera_del_error": ["2014-12-25"] if o == "dolares" else [],
            "dias_previstos_por_serie": 2 * h_max, "primer_dia_previsto": "2014-05-23",
            "ultimo_dia_previsto": "2014-06-22",
            "trivial": {"valor": 51.0, "como": "la mediana de las filas del ajuste"},
            "errores": {"todas": [entrada(rng, None, p, f) for p in PREDICTORES],
                        "por_tienda": [entrada(rng, t_, p, f) for t_ in TIENDAS for p in PREDICTORES],
                        "por_h": [entrada(rng, h, p, f) for h in range(1, h_max + 1) for p in PREDICTORES],
                        "dias_con_evento": [entrada(rng, None, p, f) for p in PREDICTORES],
                        "dias_sin_evento": [entrada(rng, None, p, f) for p in PREDICTORES],
                        "dias_snap": [entrada(rng, None, p, f) for p in PREDICTORES],
                        "dias_sin_snap": [entrada(rng, None, p, f) for p in PREDICTORES]},
            "veredicto": {"origenes_que_gana": 2, "de": 2, "minimo": 2, "ventaja": 2.25, "error_modelo": 15.5,
                          "error_rival": 17.75, "veredicto": "gana",
                          "intervalo": {"bajo": 1.125, "alto": 3.5, "remuestreos": 1000, "semilla": 42,
                                        "percentiles": [2.5, 97.5], "medida": "ventaja en puntos de error por cada 100",
                                        "unidad": "serie", "unidades": 4,
                                        "que_se_remuestrea": "las combinaciones de departamento y tienda enteras"}},
            "suavizado": {"origenes_que_gana": 1, "de": 2, "minimo": 2, "ventaja": 0.5, "lectura": "no se puede afirmar",
                          "intervalo": {"bajo": -0.25, "alto": 1.5}},
            "recomendacion_por_departamento": recomendacion,
            "sesgo_dias_cero": [{"prevision": p, "sesgo_medio_por_fila": 3.0, "unidad": "unidades", "filas": f}
                                for p in PREDICTORES],
            "medidas_pieza": {"filas": f, "tabla": [{"prevision": p, "mae": 14.5, "rmse": 24.25, "r2": 0.954,
                                                     "mejora_mae": 0.78} for p in PREDICTORES]},
            "error_por_tramo": {"filas": f, "tabla": [
                {"tramo": "(-0.001, 20.0]", "filas": 5, "real_medio": 8.5, "previsto_medio": 10.25, "mae": 4.0,
                 "sesgo": 2.0},
                {"tramo": "(20.0, 90.0]", "filas": 5, "real_medio": 50.5, "previsto_medio": 49.25, "mae": 9.0,
                 "sesgo": -1.0}]},
            "desarrollo_frente_a_validacion": {
                "entrenamiento": {"error": 13.5, "sesgo": 0.0, "filas": "entrenamiento: 100 filas del ajuste"},
                "validacion": {"error": 15.5, "sesgo": 3.0, "filas": f},
                "pieza": [{"lado": "desarrollo", "mae": 11.25, "rmse": 17.75, "r2": 0.97},
                          {"lado": "validacion", "mae": 14.5, "rmse": 24.25, "r2": 0.954},
                          {"lado": "validacion_entre_desarrollo", "mae": 1.3, "rmse": 1.38, "r2": 0.98}],
                "pieza_filas": "desarrollo: filas del ajuste a un día; validación: recursiva"},
            "mase": {"valores": {p: 0.84 + 0.01 * i for i, p in enumerate(PREDICTORES)},
                     "escala": "error medio de repetir la semana anterior a un día", "filas": f},
            "canario": {"barajado": {"error": 73.0, "filas": f}, "fuga": {"error": 0.98, "filas": f},
                        "limite_fuga": 5.0},
            "reajuste": {"filas": 100}, "robustez": robustez_json(o, medidas, f), "niveles": niveles_json(o, f)}
    return v


def busqueda_json():
    """busqueda.json en pequeño."""
    ranking, referencias = [], []
    for o in HORIZONTE:
        for alg, e in (("HistGradientBoosting", 15.5), ("Ridge", 21.0)):
            ranking.append({"objetivo": o, "algoritmo": alg, "cv_media": e, "cv_desviacion": 0.75, "sesgo_media": 0.5,
                            "filas": "fuera de pliegue: los 2 cortes",
                            "entrenamiento": {"error": e - 2, "filas": "entrenamiento: las filas del ajuste"},
                            "cortes_que_gana_a_la_regla_que_menos_falla": 1})
        for nombre, e in zip(["trivial_mediana"] + REGLAS, (73.5, 22.5, 21.0, 18.0)):
            referencias.append({"objetivo": o, "nombre": nombre, "cv_media": e, "sesgo_media": -0.5,
                                "filas": "fuera de pliegue: los 2 cortes"})
    imp = [{"columna": c, "importancia": x, "desviacion": 0.5} for c, x in
           (("ventas_media_7", 28.0), ("ventas_lag_1", 13.5), ("weekday", 3.0),
            ("productos_con_precio_semana_anterior", 0.84), ("snap", 1.0), ("month", -0.01))]
    return {
        "metodo": "aprendizaje-automatico", "fecha_datos": FECHA, "resultado": {"estado": "PARADO"},
        "tabla": {"desde": "2011-03-05", "hasta": "2014-05-22", "filas": 100},
        "aprobado_antes": {"algoritmos_y_busqueda": "HistGradientBoosting y Ridge; nivel equilibrado",
                           "aprobado_por": "el responsable del caso, 24/11/2026, «Sí, tal cual»"},
        "validacion_cruzada": {"tipo": "TimeSeriesSplit sobre los días, sin barajar", "pliegues": 2,
                               "test_size": dict(HORIZONTE),
                               "origenes": {o: ["2014-04-02", "2014-04-12"] for o in HORIZONTE}},
        "desequilibrio": {"regla": None, "por_que": "no aplica: los dos objetivos son cantidades"},
        "ranking": ranking, "referencias_cv": referencias,
        "comparacion": {o: {"media": -5.5, "desviacion": 1.25, "empate": False} for o in HORIZONTE},
        "ganador": {o: {"algoritmo": "HistGradientBoosting", "semilla": 42, "n_columnas": 82,
                        "buscados": {"min_samples_leaf": 205, "max_iter": 500, "max_depth": None,
                                     "learning_rate": 0.1, "l2_regularization": 0},
                        "por_que": "gana pliegue a pliegue: la media de las diferencias pasa de su desviación",
                        "ficha": "assets/fichas_de_algoritmos/histgradientboosting/01_ficha.md",
                        "reajuste": {"filas_ajuste": 100}} for o in HORIZONTE},
        "importancias": {o: {"metodo": "permutacion por variable de origen", "filas": "fuera de pliegue: 40 filas",
                             "puntuacion": "menos el error", "valores": imp, "peso_de_las_dos_primeras": 0.66}
                         for o in HORIZONTE},
        "distancia": {o: {"entrenamiento": {"error": 13.5, "filas": "entrenamiento: las filas del ajuste"},
                          "a_un_dia": {"error": 14.25, "filas": "fuera de pliegue: a un día"},
                          "recursiva": {"error": 15.5, "filas": "fuera de pliegue: recursiva"},
                          "lectura": "manual 19.3: sin vara fija"} for o in HORIZONTE},
        "regla_simple": {o: {"variables": ["ventas_media_7", "ventas_lag_1"],
                             "recursiva": {"error": 21.75, "filas": "fuera de pliegue: recursiva"},
                             "comparacion_con_el_ganador": {"media": -6.25, "desviacion": 1.5},
                             "el_ganador_la_supera": True} for o in HORIZONTE},
        "canario": {o: {"barajado": {"error": 81.0, "filas": "fuera de pliegue: corte 2"},
                        "fuga": {"error": 0.9, "filas": "fuera de pliegue: corte 2"}, "limite_fuga": 5.0}
                    for o in HORIZONTE},
        "busqueda": {"nivel": "equilibrado", "medida": "error de reglas, apartado 6 en recursivo",
                     "rejillas": {"HistGradientBoosting": {"max_iter": [100, 500]}, "bosque": {"max_depth": [5, 10]}},
                     "espacio": [{"objetivo": o, "algoritmo": a, "combinaciones": c, "probadas": p, "tipo": t}
                                 for o in HORIZONTE for a, c, p, t in (("HistGradientBoosting", 72, 15, "aleatoria"),
                                                                       ("Ridge", 13, 13, "rejilla"))],
                     "rejillas_ampliadas": [
                         {"objetivo": "unidades", "algoritmo": "HistGradientBoosting", "hiperparametro": "max_iter",
                          "lado": "alto", "motivo": "borde", "medido": True, "imposible": None},
                         {"objetivo": "unidades", "algoritmo": "HistGradientBoosting",
                          "hiperparametro": "l2_regularization", "lado": "bajo", "motivo": "borde", "medido": False,
                          "imposible": "-1 queda por debajo del mínimo válido (0.0)"}],
                     "segundas_busquedas": [{"objetivo": "unidades", "algoritmo": "HistGradientBoosting",
                                             "mejora": -0.06, "desviacion": 0.32, "se_sostiene": False}],
                     "modelos_de_la_busqueda": 40,
                     "modelos_por_objetivo_y_algoritmo": {"unidades/HistGradientBoosting": 10, "unidades/Ridge": 10,
                                                          "dolares/HistGradientBoosting": 10, "dolares/Ridge": 10},
                     "modelos_extra": {"canario": 4}, "segundos": 100.4},
        "validaciones": {"sin_filas_de_ajuste": True, "semillas": True, "con_probabilidad": None},
        "validaciones_nulas": {"con_probabilidad": "no aplica: objetivo de cantidad"},
        "parametros": [{"nombre": "semilla", "valor": 42, "origen": "parametros.md"},
                       {"nombre": "candidatos", "valor": {"HistGradientBoosting": 15, "Ridge": None},
                        "origen": "planteamientos §2"}]}


def resto_json():
    """Los otros cinco JSON en pequeño."""
    base = {"fecha_datos": FECHA, "resultado": {"estado": "OK"}}
    particion = dict(base, partes=[
        {"parte": "entrenamiento", "filas": 120, "fecha_min": "2011-01-29", "fecha_max": "2014-05-22", "dias": 30},
        {"parte": "validacion", "filas": 60, "fecha_min": "2014-05-23", "fecha_max": "2015-05-22", "dias": 15},
        {"parte": "lote_produccion", "filas": None}],
        objetivo={"nota": "objetivo continuo: no hay tasa ni desequilibrio de clases"})
    preparacion = dict(base, fuera=[{"variable": "year", "motivo": "en la validación toma un valor que el "
                                                                  "entrenamiento no tiene"},
                                    {"variable": "clase_cero", "motivo": "posterior a la decisión"}])
    variables = dict(base, variables_generadas=[{"columna": "ventas_lag_1", "formula": "la venta del día anterior"},
                                                {"columna": "productos_con_precio_semana_anterior",
                                                 "formula": "productos con precio la semana anterior"}],
                     filas_quitadas={"filas_quitadas": 20, "filas_despues": 100, "desde": "2011-01-29",
                                     "hasta": "2011-03-04"})
    preseleccion = dict(base, modo="comparativo", escenario="consenso amplio",
                        escenario_fijado_en="negocio/reglas-negocio.md §7",
                        pendientes=[{"opciones": ["event_name_1 y event_name_2: salen las evento_<nombre>",
                                                  "evento_<nombre>: salen event_name_1 y event_name_2"]}],
                        objetivos={o: {"tabla_decisiones": [
                            {"columna": "productos_con_precio_semana_anterior_ss",
                             "origen": "productos_con_precio_semana_anterior", "votos": 1,
                             "Ridge": "sale: 1 votos de 3; consenso amplio pide 2",
                             "HistGradientBoosting": "entra: §2 y §5"}]} for o in HORIZONTE})
    minimo = dict(base, hace_falta_modelar={"respuesta": True, "por_que": "es una previsión"},
                  puerta_contestable={"aplica": False, "por_que": "no decide sobre personas"},
                  aprobado_antes={"medida_principal": "error por cada 100 vendidas, sin el 25 de diciembre",
                                  "por_que": "el error de las juntas decide",
                                  "referencias": ["las tres reglas sencillas", "el trivial"],
                                  "se_da_por_bueno": "al menos el 75 % de los orígenes y el intervalo del 95 % "
                                                     "por encima de cero"},
                  desequilibrio={"regla": None, "por_que": "no aplica: los dos objetivos son cantidades"},
                  modelo_minimo={o: {"resumen": {"a_un_dia": {"error": 14.25, "filas": "fuera de pliegue"},
                                                 "recursiva": {"error": 16.25, "filas": "fuera de pliegue"}}}
                                 for o in HORIZONTE})
    return {"informes/particion.json": particion, "informes/preparacion.json": preparacion,
            "informes/variables_modelo.json": variables, "informes/preseleccion.json": preseleccion,
            "informes/modelo_minimo.json": minimo}


def montar(raiz, cambios=None, planteamientos=PLANTEAMIENTOS):
    """Escribe la carpeta del caso de la prueba. `cambios` es {fichero: función que cambia su JSON}."""
    if raiz.exists():
        shutil.rmtree(raiz)
    (raiz / "data" / "processed").mkdir(parents=True)
    (raiz / "informes").mkdir()
    (raiz / "config" / "metodo").mkdir(parents=True)
    (raiz / "config" / "negocio").mkdir(parents=True)
    tabla = previsiones()
    tabla.to_parquet(raiz / "data" / "processed" / "previsiones_validacion.parquet", index=False)
    jsons = resto_json()
    jsons["informes/busqueda.json"] = busqueda_json()
    jsons["informes/validacion.json"] = validacion_json(tabla)
    for rel, d in jsons.items():
        if cambios and rel in cambios:
            cambios[rel](d)
        (raiz / rel).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    (raiz / "config" / "metodo" / "04_planteamientos.md").write_text(planteamientos, encoding="utf-8")
    (raiz / "config" / "negocio" / "reglas-negocio.md").write_text(REGLAS_MD, encoding="utf-8")


def ejecutar(raiz):
    """Ejecuta el script sobre la carpeta de la prueba con -W error. Devuelve (código, JSON, salida)."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    p = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)], capture_output=True,
                       text=True, encoding="utf-8", env=entorno, timeout=170)
    ruta = raiz / "informes" / "modelado.json"
    d = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return p.returncode, d, p.stdout + p.stderr


# ── 3. El control: la carpeta limpia ──────────────────────────────────────────
def control(m):
    """El script entero sobre la carpeta limpia. Devuelve el md y el JSON para los demás casos."""
    raiz = TMP / "limpia"
    montar(raiz)
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "OK",
              f"control: la carpeta limpia termina en OK ({salida[-1500:]})")
    if d is None:
        return None, None
    md = (raiz / "informes" / "modelado.md").read_text(encoding="utf-8")
    malas = [k for k, x in d["validaciones"].items() if x is not True]
    comprobar(not malas, f"control: todas las validaciones en verde ({malas})")
    comprobar(m.apartados_en_orden(md), "control: los catorce apartados en su orden")
    figuras = sorted(p.name for p in (raiz / "informes" / "figuras_modelado").glob("*.png"))
    comprobar(len(figuras) == 4 and all(f"figuras_modelado/{f}" in md for f in figuras),
              f"control: cuatro figuras, enlazadas en el informe ({figuras})")
    comprobar(d["cifras"] and all(c.get("fichero") and c.get("camino") for c in d["cifras"]),
              "control: cada cifra con su fichero y su camino")
    comprobar({"python", "pandas", "numpy", "pyarrow", "matplotlib"} <= set(d["entorno"]),
              "control: las versiones de Python, pandas, numpy, pyarrow y matplotlib")
    comprobar(len(d["entradas"]) == 8 and all(e.get("sha256") for e in d["entradas"]),
              "control: las siete entradas JSON y la tabla de previsiones, con su huella")
    filas = {f["objetivo"]: f["filas"] for f in d["figuras"]}
    comprobar(filas == {"unidades": 16, "dolares": 20}, f"control: las figuras sin los días fuera del error ({filas})")
    comprobar(", y " not in md and "No existe `config/fuentes/proteccion-datos.json`" in md,
              "control: sin «, y» y con la protección de datos dicha")
    comprobar("los datos no traen coste, margen ni existencias" in md and "un cero no dice si había producto" in md,
              "control: la vía 3 cita las dos frases de las reglas, cada una en su viñeta")
    variables = {"parametros": [{"nombre": "retardos", "valor": [1]}, {"nombre": "ventanas de las medias",
                                                                       "valor": [7]}],
                 "variables_generadas": [{"columna": c} for c in ("unidades_lag_1", "dolares_lag_1", "unidades_media_7",
                                                                  "dolares_media_7")]}
    comprobar(m.candidatas_sin_crear(variables) == ["productos_con_precio_semana_anterior"],
              "una candidata de los planteamientos sin crear")
    return md, d


# ── 4. Casos 1 a 8 ─────────────────────────────────────────────────────────────
def casos_entrada(m):
    """Caso 1: un JSON de entrada en ERROR."""
    comprobar(m.entradas_en_error({"a.json": {"resultado": {"estado": "ERROR"}},
                                   "b.json": {"resultado": {"estado": "OK"}}}) == ["a.json"],
              "1 · la función ve el JSON en ERROR")
    raiz = TMP / "error"
    montar(raiz, {"informes/validacion.json": lambda d: d["resultado"].update(estado="ERROR")})
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO" and
              not (raiz / "informes" / "figuras_modelado").exists(),
              f"1 · con validacion.json en ERROR para sin dibujar ({salida[-600:]})")


def casos_apartados(m, md):
    """Caso 2: un apartado que falta o fuera de orden."""
    sin_corte = md.replace("## El corte", "## Otra cosa")
    trozos = md.split("## Ranking")
    cambiado = md.replace("## El desequilibrio", "## TEMP").replace("## Ranking", "## El desequilibrio").replace(
        "## TEMP", "## Ranking")
    comprobar(not m.apartados_en_orden(sin_corte), "2 · falta un apartado")
    comprobar(len(trozos) == 2 and not m.apartados_en_orden(cambiado), "2 · dos apartados fuera de orden")


def casos_numeros(m, md, d):
    """Caso 3: un número del informe que no está en modelado.json."""
    comprobar(m.numeros_fuera_del_json(md, d["cifras"]) == [], "3 · control: todos los números del informe están")
    comprobar("99,99" in m.numeros_fuera_del_json(md + "\nEl error fue 99,99.\n", d["cifras"]),
              "3 · un número que no está en el JSON")


def casos_origen(m, d):
    """Caso 4: una cifra sin clave de origen."""
    cifras = copy.deepcopy(d["cifras"])
    cifras[0]["fichero"] = ""
    comprobar(m.citas_sin_origen(d["cifras"]) == [] and m.citas_sin_origen(cifras),
              "4 · una cifra sin fichero de origen")
    cifras = copy.deepcopy(d["cifras"])
    cifras[1]["camino"] = None
    comprobar(m.citas_sin_origen(cifras), "4 · una cifra sin camino")


def casos_no_aplica(m, md, d):
    """Caso 5: el desequilibrio o el corte quitados en vez de explicados."""
    comprobar(m.no_aplica_explicado(md, d) == [], "5 · control: los dos explicados")
    cuerpo = m.seccion(md, "El desequilibrio")
    comprobar(m.no_aplica_explicado(md.replace(cuerpo, "\n"), d), "5 · el desequilibrio sin su explicación")
    corte = m.seccion(md, "El corte")
    comprobar(m.no_aplica_explicado(md.replace(corte, "\nNo aplica.\n"), d), "5 · el corte sin su motivo")


def casos_datos_personales(m, md):
    """Caso 6: el apartado de datos personales que no dice que falta proteccion-datos.json."""
    comprobar(m.datos_personales_bien(md, False), "6 · control: lo dice")
    roto = md.replace("No existe `config/fuentes/proteccion-datos.json`", "Los datos están bien")
    comprobar(not m.datos_personales_bien(roto, False), "6 · no dice que falta proteccion-datos.json")


def casos_codigo(m):
    """Casos 7 y 8: el script que abre una tabla de hechos y una validación escrita con su resultado puesto."""
    propio = SCRIPT.read_text(encoding="utf-8")
    comprobar(m.abre_tablas_hechos(propio) == [], "7 · control: el script no abre ninguna tabla de hechos")
    comprobar(m.abre_tablas_hechos('t = pd.read_parquet("data/processed/hechos_modelo_validacion.parquet")'),
              "7 · una tabla de hechos abierta")
    comprobar(m.buscar_resultados_escritos(propio) == [], "8 · control: ninguna validación con su resultado puesto")
    comprobar(m.buscar_resultados_escritos('v["citas_existen"] = True'), "8 · una validación escrita como True")
    comprobar(m.buscar_resultados_escritos('{"apartados_en_orden": False}'), "8 · una validación escrita como False")


# ── 5. Las demás validaciones ──────────────────────────────────────────────────
def casos_demas(m, md, d):
    """Una cita que no está en su fichero, un redondeo distinto, la fecha, la aprobación, las filas y «, y»."""
    raiz = TMP / "limpia"
    fuentes = {rel: json.loads((raiz / rel).read_text(encoding="utf-8")) for rel in m.ENTRADAS_JSON}
    docs = m.leer_documentos(raiz)
    comprobar(m.citas_que_no_existen(d["cifras"], fuentes, docs) == [], "control: cada cita está en su fichero")
    cifras = copy.deepcopy(d["cifras"])
    numerica = next(i for i, c in enumerate(cifras) if isinstance(c["valor"], float) and c["fichero"].endswith("json"))
    cifras[numerica]["valor"] = cifras[numerica]["valor"] + 1
    comprobar(m.citas_que_no_existen(cifras, fuentes, docs), "una cita con otro valor que su fichero")
    cifras = copy.deepcopy(d["cifras"])
    con_decimales = next(i for i, c in enumerate(cifras) if c.get("decimales"))
    comprobar(m.redondeo_distinto(d["cifras"]) == [], "control: cada cifra escrita con su redondeo")
    cifras[con_decimales]["escrito"] = "123,45"
    comprobar(m.redondeo_distinto(cifras), "una cifra escrita con otro redondeo")
    comprobar(m.sin_coma_y(md) and not m.sin_coma_y(md + "\nUna cosa, y otra.\n"), "un texto con «, y»")
    comprobar(m.entradas_cambiadas(raiz, d["entradas"]) == [], "control: las entradas, iguales")
    cambiadas = copy.deepcopy(d["entradas"])
    cambiadas[0]["sha256"] = "0" * 64
    comprobar(m.entradas_cambiadas(raiz, cambiadas) == [cambiadas[0]["ruta"]], "una entrada que cambió")
    figuras = sorted((raiz / "informes" / "figuras_modelado").glob("*.png"))
    comprobar(m.figuras_completas(figuras) and not m.figuras_completas(figuras[:3]),
              "una figura que falta")
    estable = m.comprobar_md(md, d, False)
    comprobar(all(estable.values()) and m.comprobar_md(md + "\nCifra 99,99.\n", d, False) != estable,
              "un informe final que no pasa lo que pasó el borrador")

    raiz = TMP / "fecha"
    montar(raiz, {"informes/preseleccion.json": lambda x: x.update(fecha_datos="2015-05-23")})
    codigo, x, _ = ejecutar(raiz)
    comprobar(codigo == 1 and x is not None and x["resultado"]["estado"] == "PARADO", "otra fecha de los datos para")
    raiz = TMP / "sin_aprobacion"
    montar(raiz, planteamientos=PLANTEAMIENTOS.replace(APROBACION, "Sin veredicto."))
    codigo, x, _ = ejecutar(raiz)
    comprobar(codigo == 1 and x is not None and x["resultado"]["estado"] == "PARADO",
              "sin la aprobación del veredicto escrita, para")
    raiz = TMP / "filas"
    montar(raiz, {"informes/validacion.json": lambda x: x["validacion"]["dolares"].update(filas_medidas=24)})
    codigo, x, _ = ejecutar(raiz)
    comprobar(codigo == 1 and x is not None and x["validaciones"].get("figuras_con_las_filas_medidas") is False,
              "unas figuras con otras filas que las medidas")


# ── 6. Casos 9 a 11: lo que matiza la ventaja ──────────────────────────────────
def casos_robustez(m, md, d):
    """El subapartado de la validación, los eventos sin cubrir en «Límites» y las cifras de robustez citadas."""
    validacion = m.seccion(md, "La validación")
    limites = m.seccion(md, "Límites")
    comprobar("### Lo que matiza la ventaja" in validacion,
              "control: «Lo que matiza la ventaja» es un subapartado de «La validación»")
    comprobar(all(n in limites for n in ("Thanksgiving", "Christmas", "NewYear")),
              "9 · control: «Límites» nombra los eventos sin cubrir")
    de_robustez = [c for c in d["cifras"] if ".robustez." in str(c.get("camino"))]
    comprobar(len(de_robustez) >= 10 and all(c.get("filas") for c in de_robustez if isinstance(c["valor"], (int, float))),
              "10 · control: las cifras de robustez están citadas en modelado.json con sus filas")
    sin_ellas = [c for c in d["cifras"] if ".robustez." not in str(c.get("camino"))]
    faltan = m.numeros_fuera_del_json(md, sin_ellas)
    comprobar(bool(faltan) and "0,69" in faltan and "4,13" in faltan,
              f"10 · una cifra de robustez que no está en modelado.json sale en rojo ({faltan[:6]})")

    raiz = TMP / "sin_robustez"
    montar(raiz, {"informes/validacion.json": lambda x: x["validacion"]["unidades"].pop("robustez")})
    codigo, x, _ = ejecutar(raiz)
    comprobar(codigo == 1 and x is not None and x["resultado"]["estado"] == "PARADO" and
              "robustez" in x["resultado"]["resumen"], "11 · validacion.json sin el bloque robustez, para")

    comprobar(d["validaciones"].get("limites_nombran_eventos") is True and m.eventos_sin_nombrar(md, d) == [],
              "9 · control: la validación de los eventos en «Límites», en verde")
    roto = md.replace(limites, limites.replace("Thanksgiving", "un festivo"))
    comprobar(m.eventos_sin_nombrar(roto, d) == ["Thanksgiving"],
              "9 · un evento sin cubrir que «Límites» no nombra sale en rojo")
    solo_arriba = md.replace(limites, limites.replace("NewYear", "otro"))
    comprobar("NewYear" in solo_arriba and m.eventos_sin_nombrar(solo_arriba, d) == ["NewYear"],
              "9 · nombrarlo solo fuera de «Límites» no basta")


# ── 7. Casos 12 y 13: la previsión sumada ──────────────────────────────────────
def casos_niveles(m, md, d):
    """El subapartado de la previsión sumada dentro de «La validación» y sus cifras citadas en modelado.json."""
    titulo = "### La previsión sumada por tienda, categoría, estado y cadena"
    validacion = m.seccion(md, "La validación")
    comprobar(titulo in validacion, "control: «La previsión sumada…» es un subapartado de «La validación»")
    sub = validacion.split(titulo, 1)[-1].split("\n### ", 1)[0]
    comprobar(all(x in sub for x in ("6,44", "31,06", "CAT_B", "T_1", "ST_A", "las 4 series", "repetir la semana "
                                                                                              "anterior")),
              "control: el subapartado trae las cifras y los grupos de los cuatro niveles")
    de_niveles = [c for c in d["cifras"] if ".niveles." in str(c.get("camino"))]
    # Las cifras medidas llevan las filas de la validación; los recuentos de grupos dicen que no se miden sobre filas
    medidas = [c for c in de_niveles if isinstance(c["valor"], (int, float)) and not isinstance(c["valor"], bool)
               and not c.get("operacion")]
    recuentos = [c for c in de_niveles if str(c.get("operacion") or "").startswith("contar")]
    comprobar(len(medidas) >= 20 and all(str(c.get("filas", "")).startswith("validacion") for c in medidas)
              and len(recuentos) == 2 * 4 and all(c.get("filas") for c in recuentos),
              "12 · control: las cifras de niveles están citadas en modelado.json con sus filas")
    sin_ellas = [c for c in d["cifras"] if ".niveles." not in str(c.get("camino"))]
    faltan = m.numeros_fuera_del_json(md, sin_ellas)
    comprobar("6,44" in faltan and "31,06" in faltan,
              f"12 · una cifra de niveles que no está en modelado.json sale en rojo ({faltan[:6]})")
    comprobar(all("niveles" in d["validacion"][o] for o in HORIZONTE),
              "control: modelado.json lleva el bloque niveles de cada objetivo")

    raiz = TMP / "sin_niveles"
    montar(raiz, {"informes/validacion.json": lambda x: x["validacion"]["dolares"].pop("niveles")})
    codigo, x, _ = ejecutar(raiz)
    comprobar(codigo == 1 and x is not None and x["resultado"]["estado"] == "PARADO" and
              "niveles" in x["resultado"]["resumen"], "13 · validacion.json sin el bloque niveles, para")


# ── 8. Ejecución ───────────────────────────────────────────────────────────────
def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/17_informe_modelado.py")
        else:
            m = cargar(SCRIPT, "informe_modelado_17")
            md, d = control(m)
            casos_entrada(m)
            casos_codigo(m)
            if md is not None:
                casos_apartados(m, md)
                casos_numeros(m, md, d)
                casos_origen(m, d)
                casos_no_aplica(m, md, d)
                casos_datos_personales(m, md)
                casos_demas(m, md, d)
                try:
                    casos_robustez(m, md, d)
                except AttributeError as e:
                    comprobar(False, f"9 a 11 · el script tiene las funciones de robustez ({e})")
                casos_niveles(m, md, d)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
