"""Prueba de scripts/15_busqueda.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_busqueda/ una carpeta con la estructura del
caso (la tabla de entrenamiento, una tabla de validación rota a propósito, preseleccion.json, preparacion.json,
modelo_minimo.json y las dos fichas), ejecuta el script sobre ella con --raiz y la borra al acabar. Importa los módulos
del caso y el script que prueba, que tiene su trabajo bajo __main__.

Los casos que tienen que fallar si el código está mal:
  1. un candidato medido a un día y no en recursivo;
  2. dos algoritmos comparados con cortes distintos;
  3. un empate decidido con la desviación de cada algoritmo y no pliegue a pliegue;
  4. un mejor valor en el borde de su rejilla sin ampliar;
  5. el script que abre la validación;
  6. una cifra de entrenamiento rotulada como fuera de pliegue;
  7. una validación escrita con su resultado puesto (error 24).
Y el control que no debe disparar: el script entero sobre tablas limpias para en la puerta del responsable del caso, con todas las
validaciones en verde, los cortes del modelo mínimo, la tabla de lo probado, la propuesta y cada cifra con sus filas.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
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
SCRIPTS = RAIZ / "scripts"
SCRIPT = SCRIPTS / "15_busqueda.py"
TMP = RAIZ / "tests" / "tmp_busqueda"
FALLOS = []
SERIES = [("T_0", "D_0"), ("T_0", "D_1"), ("T_1", "D_0"), ("T_1", "D_1")]
EVENTOS = ["Ev_A", "Ev_B"]
# Rejillas pequeñas de la prueba: cada una con un hiperparámetro de dos valores para que haya borde
REJILLAS = {"HistGradientBoosting": {"learning_rate": [0.3], "max_depth": [3], "max_iter": [30, 60],
                                     "min_samples_leaf": [20], "l2_regularization": [0]},
            "Ridge": {"alpha": [1.0, 10.0, 100.0]}}


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def huella(ruta):
    """SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def cargar(ruta, nombre):
    """Importa un fichero de Python por su ruta."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Datos pequeños ──────────────────────────────────────────────────────────
def tabla_entrenamiento(vp, dias=560):
    """Cuatro series con calendario, eventos, precio y los retardos de los dos objetivos calculados con el módulo de
    variables; salen los 35 primeros días de cada serie, como en el caso. Incluye un 25 de diciembre. Con 560 días, el
    ajuste del primer corte de dólares ya tiene los doce meses, como en el caso."""
    rng = np.random.default_rng(7)
    fechas = pd.date_range("2013-03-01", periods=dias + 35, freq="D").astype("datetime64[us]")
    partes = []
    for k, (tienda, dept) in enumerate(SERIES):
        fin_de_semana = (fechas.dayofweek >= 5).astype(int)
        unidades = np.maximum(0, 40 + 15 * k + 12 * fin_de_semana + rng.integers(-5, 6, len(fechas)))
        evento = [EVENTOS[(i // 20) % 2] if i % 20 == 3 else None for i in range(len(fechas))]
        evento_2 = ["Ev_B" if i % 20 == 13 else None for i in range(len(fechas))]
        partes.append(pd.DataFrame({
            "store_id": tienda, "dept_id": dept, "d": [f"d_{i + 1}" for i in range(len(fechas))], "date": fechas,
            "weekday": fechas.day_name(), "month": fechas.month.astype("int64"), "event_name_1": evento,
            "event_name_2": evento_2, "snap": (fechas.day <= 10).astype("int64"),
            "precio_medio_semana_anterior": 2.0 + k * 0.5, "productos_con_precio_semana_anterior": 10 + k,
            "dia_del_mes": fechas.day.astype("int64"),
            "fuera_del_error": (fechas.month == 12) & (fechas.day == 25),
            "unidades": unidades.astype("int64"), "dolares": np.round(unidades * (2.0 + k * 0.5), 2)}))
    t = pd.concat(partes, ignore_index=True)
    for c in ["store_id", "dept_id", "d", "weekday", "event_name_1", "event_name_2"]:
        t[c] = t[c].astype("str")
    for e in EVENTOS:
        t[f"evento_{e}"] = ((t["event_name_1"] == e).fillna(False) | (t["event_name_2"] == e).fillna(False)).astype(
            "int64")
    for objetivo in ("unidades", "dolares"):
        t = t.join(vp.crear_variables_objetivo(t, objetivo))
    primer = t.groupby(["store_id", "dept_id"])["date"].transform("min")
    t = t[t["date"] >= primer + pd.Timedelta(35, "D")].reset_index(drop=True)
    return t.sample(frac=1.0, random_state=3).reset_index(drop=True)


def columnas_salida(pp, tabla, objetivo):
    """Los nombres que da el preprocesador del caso con esta tabla."""
    eventos = [c for c in tabla.columns if c.startswith("evento_")]
    pipe = pp.construir_preprocesador(objetivo, eventos).fit(tabla)
    return list(pipe.transform(tabla.head(3)).columns)


def montar(raiz, tabla, pp, pr, estado="AVISO", desplazar_cortes=False):
    """Escribe la carpeta del caso de la prueba: la tabla, una validación rota, los tres JSON previos y las fichas."""
    if raiz.exists():
        shutil.rmtree(raiz)
    procesados = raiz / "data" / "processed"
    procesados.mkdir(parents=True)
    (raiz / "informes").mkdir()
    for carpeta in ("histgradientboosting", "regresion_lineal_y_regularizadas"):
        ficha = raiz / "assets" / "fichas_de_algoritmos" / carpeta
        ficha.mkdir(parents=True)
        (ficha / "01_ficha.md").write_text("# ficha de la prueba\n", encoding="utf-8")
    tabla.to_parquet(procesados / "hechos_modelo_entrenamiento.parquet", index=False)
    # Caso 5: una validación que no es Parquet; si el script la abriera, se rompería
    (procesados / "hechos_modelo_validacion.parquet").write_text("no se abre", encoding="utf-8")
    sha = huella(procesados / "hechos_modelo_entrenamiento.parquet")
    entrada = [{"ruta": "data/processed/hechos_modelo_entrenamiento.parquet", "sha256": sha}]
    objetivos, minimo = {}, {}
    for objetivo, h in (("unidades", 10), ("dolares", 28)):
        salida = columnas_salida(pp, tabla, objetivo)
        ridge = [c for c in salida if c not in (f"{objetivo}_lag_2_rs", f"{objetivo}_lag_3_rs")]
        objetivos[objetivo] = {"columnas_finales": {"Ridge": ridge, "HistGradientBoosting": list(salida)}}
        origenes = [p["origen"] for p in pr.pliegues_por_dia(tabla["date"], 5, h)]
        if desplazar_cortes:
            origenes = [o - pd.Timedelta(1, "D") for o in origenes]
        minimo[objetivo] = {"pliegues": [{"origen": f"{o:%Y-%m-%d}"} for o in origenes]}
    pres = {"fecha_datos": "2015-05-22", "resultado": {"estado": estado}, "entradas": entrada, "objetivos": objetivos}
    prep = {"fecha_datos": "2015-05-22", "resultado": {"estado": "OK"}, "entradas": entrada,
            "fuera": [{"variable": v, "motivo": "prueba"} for v in
                      ("d", "unidades", "dolares", "periodo", "cierre_tienda", "fuera_del_error", "clase_cero")]}
    mm = {"fecha_datos": "2015-05-22", "resultado": {"estado": "AVISO"}, "entradas": entrada,
          "coste": {"rejillas": REJILLAS}, "modelo_minimo": minimo}
    for nombre, datos in (("preseleccion", pres), ("preparacion", prep), ("modelo_minimo", mm)):
        (raiz / "informes" / f"{nombre}.json").write_text(json.dumps(datos), encoding="utf-8")


def ejecutar(raiz, *extra):
    """Ejecuta el script con -W error sobre la carpeta de la prueba; devuelve código, JSON y salida."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz), *extra],
                          capture_output=True, text=True, encoding="utf-8", env=entorno)
    ruta = raiz / "informes" / "busqueda.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


class ModeloRetardo:
    """Modelo de prueba: prevé el retardo de un día más 3; fit no aprende nada."""

    def fit(self, x, y):
        """No aprende: devuelve el propio modelo."""
        return self

    def predict(self, x):
        """El retardo de un día más 3."""
        return x["unidades_lag_1"].to_numpy(dtype="float64") + 3.0


# ── 3. Caso 1: medido en recursivo ─────────────────────────────────────────────
def casos_recursivo(m, pr, pp, tabla):
    """Un candidato medido a un día no pasa; la medida del script es la recursiva hecha a mano."""
    t = tabla.sort_values(["date", "store_id", "dept_id"]).reset_index(drop=True)
    pliegue = pr.pliegues_por_dia(t["date"], 5, 10)[0]
    origen = pliegue["origen"]
    eventos = [c for c in t.columns if c.startswith("evento_")]
    entrada = pp.columnas_entrada("unidades", eventos)
    cifras, control, _ = m.medir_candidato(t, "unidades", entrada, ModeloRetardo(), pliegue, 1)
    # A mano: la recursiva del módulo y el error de reglas, apartado 6, sin los 25 de diciembre
    ajuste = t[t["date"] <= origen]
    prueba = t[t["date"].isin(pliegue["dias_prueba"])]
    rec = pr.prever_recursivo(ModeloRetardo(), ajuste[["store_id", "dept_id", "date", "unidades"]], prueba,
                              "unidades", 10, origen=origen)
    junto = prueba.merge(rec, on=["store_id", "dept_id", "date"], how="left", validate="one_to_one")
    junto = junto[~junto["fuera_del_error"].to_numpy()]
    esperado = pr.error_y_sesgo(junto["unidades"], pr.redondear_unidades(junto["prevision"]))[0]
    un_dia = pr.error_y_sesgo(junto["unidades"], pr.redondear_unidades(junto["unidades_lag_1"] + 3.0))[0]
    comprobar(abs(un_dia - esperado) > 0.5, "control: con este modelo, a un día y en recursivo dan cifras distintas")
    comprobar(np.isclose(cifras["recursiva"]["error"], esperado),
              "1 · el candidato se mide en recursivo desde el origen, no a un día")
    comprobar(control["medido_en_recursiva"] and control["recursiva_a_un_dia_igual"],
              "control: la medida pasa su comprobación de recursiva")
    # Una tabla de previsión a un día (solo h = 1) no pasa la comprobación de recursiva
    a_un_dia = rec[rec["h"] == 1]
    comprobar(not m.comprobar_recursiva(a_un_dia, 4, origen, 10),
              "1 · una previsión a un día sale en rojo en la comprobación de recursiva")
    comprobar(m.comprobar_recursiva(rec, 4, origen, 10), "control: la recursiva entera pasa su comprobación")
    sin_h = rec.drop(columns="h").assign(h=1)
    comprobar(not m.comprobar_recursiva(sin_h, 4, origen, 10), "1 · todos los días con h = 1 salen en rojo")
    comprobar(cifras["entrenamiento"]["filas"].startswith("entrenamiento") and
              cifras["recursiva"]["filas"].startswith("fuera de pliegue"), "control: cada cifra del corte con sus filas")


# ── 4. Casos 2 y 3: la comparación ─────────────────────────────────────────────
def casos_comparacion(m):
    """Cortes distintos paran; el empate se decide pliegue a pliegue y, si empatan, el más estable frente al trivial."""
    origenes = ["2014-01-01", "2014-01-11", "2014-01-21", "2014-01-31", "2014-02-10"]
    a = {"origenes": origenes, "errores": [10.0, 20.0, 30.0, 40.0, 50.0]}
    b = {"origenes": origenes, "errores": [11.0, 21.0, 31.0, 41.0, 51.0]}
    otro = {"origenes": origenes[:4] + ["2014-02-11"], "errores": b["errores"]}
    try:
        m.comparar_pliegue_a_pliegue(a, otro)
        comprobar(False, "2 · dos algoritmos con cortes distintos no se comparan")
    except ValueError:
        comprobar(True, "2 · dos algoritmos con cortes distintos no se comparan")
    trivial = {"origenes": origenes, "errores": [70.0, 70.0, 70.0, 70.0, 70.0]}
    try:
        m.elegir_ganador({"HistGradientBoosting": a, "Ridge": otro}, trivial)
        comprobar(False, "2 · el ganador no se elige con cortes distintos")
    except ValueError:
        comprobar(True, "2 · el ganador no se elige con cortes distintos")
    # La desviación de cada algoritmo (15,8) tapa la diferencia; pliegue a pliegue, a gana en los cinco
    comp = m.comparar_pliegue_a_pliegue(a, b)
    comprobar(not comp["empate"] and comp["mejor"] == "a" and np.isclose(comp["media"], -1.0),
              "3 · pliegue a pliegue, el que gana en los cinco cortes no empata")
    eleccion = m.elegir_ganador({"HistGradientBoosting": a, "Ridge": b}, trivial)
    comprobar(eleccion["algoritmo"] == "HistGradientBoosting" and not eleccion["empate"],
              "3 · el ganador no sale de la desviación de cada algoritmo")
    # Empate de verdad: diferencias de signo cambiante; gana el que mejora al trivial por un margen más parecido
    c = {"origenes": origenes, "errores": [20.0, 18.0, 21.0, 19.0, 20.0]}
    d = {"origenes": origenes, "errores": [19.0, 19.5, 20.0, 19.5, 20.5]}
    trivial_v = {"origenes": origenes, "errores": [60.0, 61.0, 62.0, 59.0, 60.0]}
    eleccion = m.elegir_ganador({"HistGradientBoosting": c, "Ridge": d}, trivial_v)
    desv_c = np.std(np.array(c["errores"]) - np.array(trivial_v["errores"]), ddof=1)
    desv_d = np.std(np.array(d["errores"]) - np.array(trivial_v["errores"]), ddof=1)
    esperado = "HistGradientBoosting" if desv_c < desv_d else "Ridge"
    comprobar(eleccion["empate"] and eleccion["algoritmo"] == esperado and eleccion["criterio"] == "estabilidad",
              "3 · con empate gana el más estable frente al trivial, medido pliegue a pliegue")


# ── 5. Caso 4: el borde ────────────────────────────────────────────────────────
def casos_borde(m):
    """El borde se detecta, se amplía un paso de la rejilla y un borde sin ampliar sale en rojo."""
    rejilla = {"alpha": [1.0, 10.0, 100.0], "max_depth": [3, 5, None], "l2_regularization": [0, 1],
               "learning_rate": [0.1]}
    bordes = m.detectar_bordes(rejilla, {"alpha": 100.0, "max_depth": 5, "l2_regularization": 0,
                                         "learning_rate": 0.1})
    comprobar(("alpha", "alto") in bordes and ("l2_regularization", "bajo") in bordes and len(bordes) == 2,
              "4 · el borde se detecta (y un valor del medio o una rejilla de un solo valor, no)")
    comprobar(m.detectar_bordes(rejilla, {"alpha": 1.0, "max_depth": None, "l2_regularization": 1,
                                          "learning_rate": 0.1}) ==
              [("alpha", "bajo"), ("max_depth", "alto"), ("l2_regularization", "alto")] or
              set(m.detectar_bordes(rejilla, {"alpha": 1.0, "max_depth": None, "l2_regularization": 1,
                                              "learning_rate": 0.1})) ==
              {("alpha", "bajo"), ("max_depth", "alto"), ("l2_regularization", "alto")},
              "4 · «sin límite» es el borde alto de la profundidad")
    comprobar(np.isclose(m.ampliar_valor([1.0, 10.0, 100.0], "alto", "alpha")[0], 1000.0) and
              np.isclose(m.ampliar_valor([0.05, 0.1], "bajo", "learning_rate")[0], 0.025),
              "4 · se amplía un paso de la progresión de la rejilla")
    comprobar(m.ampliar_valor([0, 1], "bajo", "l2_regularization")[0] is None and
              m.ampliar_valor([3, 5, None], "alto", "max_depth")[0] is None and
              m.ampliar_valor([100, 200, 500], "alto", "max_iter")[0] == 1250,
              "4 · lo que no admite ampliación lo dice; los enteros quedan enteros")
    sin = m.bordes_ampliados([("alpha", "alto")], [])
    comprobar(not sin, "4 · un mejor valor en el borde sin ampliar sale en rojo")
    con = m.bordes_ampliados([("alpha", "alto")], [{"hiperparametro": "alpha", "lado": "alto",
                                                     "valor_nuevo": 1000.0, "medido": True, "imposible": None}])
    sin_medir = m.bordes_ampliados([("alpha", "alto")], [{"hiperparametro": "alpha", "lado": "alto",
                                                          "valor_nuevo": 1000.0, "medido": False,
                                                          "imposible": None}])
    imposible = m.bordes_ampliados([("l2_regularization", "bajo")],
                                   [{"hiperparametro": "l2_regularization", "lado": "bajo", "valor_nuevo": None,
                                     "medido": False, "imposible": "por debajo de 0 no es válido"}])
    comprobar(con and imposible and not sin_medir,
              "4 · ampliado y medido, o imposible con su motivo, pasa; ampliado sin medir, no")


# ── 6. Casos 5, 6 y 7 ──────────────────────────────────────────────────────────
def casos_controles(m):
    """La validación sin abrir, los rótulos de filas y las validaciones escritas a mano."""
    comprobar(not m.validacion_sin_abrir(["data/processed/hechos_modelo_entrenamiento.parquet",
                                          "data/processed/hechos_modelo_validacion.parquet"]),
              "5 · abrir la tabla de validación sale en rojo")
    comprobar(m.validacion_sin_abrir(["data/processed/hechos_modelo_entrenamiento.parquet"]),
              "control: abrir solo el entrenamiento pasa")
    texto = SCRIPT.read_text(encoding="utf-8")
    comprobar("hechos_modelo_validacion" not in texto, "5 · el script no nombra la tabla de validación")
    malo = {"ranking": [{"cv_media": 15.0, "filas": "fuera de pliegue: 5 cortes",
                         "entrenamiento": {"error": 14.0, "filas": "fuera de pliegue: 5 cortes"}}]}
    comprobar(len(m.rotulos_de_filas(malo)) == 1, "6 · una cifra de entrenamiento rotulada como fuera de pliegue "
                                                  "sale en rojo")
    malo2 = {"x": {"error": 1.0, "filas": "entrenamiento"}, "y": {"error": 2.0}}
    comprobar(len(m.rotulos_de_filas(malo2)) == 2, "6 · una cifra fuera de pliegue rotulada como entrenamiento, o "
                                                   "sin filas, sale en rojo")
    bueno = {"ranking": [{"cv_media": 15.0, "filas": "fuera de pliegue: 5 cortes",
                          "entrenamiento": {"error": 14.0, "filas": "entrenamiento: filas del ajuste"}}]}
    comprobar(m.rotulos_de_filas(bueno) == [], "control: los rótulos buenos pasan")
    escrito = 'v = {"reproducible": True, "mismos_cortes": (False)}\nvalidaciones["bordes_ampliados"] = True\n'
    comprobar(len(m.buscar_resultados_escritos(escrito)) == 3, "7 · una validación con su resultado puesto se "
                                                               "encuentra")
    comprobar(m.buscar_resultados_escritos(texto) == [], "7 · el script no escribe ninguna validación con su "
                                                         "resultado puesto")


# ── 7. El script entero ────────────────────────────────────────────────────────
def casos_script(vp, pp, pr, tabla):
    """El control que no debe disparar, la medida de tiempo y las paradas al empezar."""
    raiz = TMP / "base"
    montar(raiz, tabla, pp, pr)
    ruta_tabla = raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet"
    antes = huella(ruta_tabla)
    codigo, d, salida = ejecutar(raiz)
    falsas = [k for k, x in (d or {}).get("validaciones", {}).items() if x is False]
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "PARADO" and d.get("puerta_de_juan"),
              f"control: el script entero para en la puerta del responsable del caso ({salida[-1500:] if codigo else ''} {falsas})")
    if d is None or codigo != 0:
        return
    comprobar(huella(ruta_tabla) == antes, "control: la tabla de entrenamiento no cambia")
    comprobar(d["tablas_abiertas"] == ["data/processed/hechos_modelo_entrenamiento.parquet"],
              "5 · el script solo abre la tabla de entrenamiento")
    comprobar(d["fecha_datos"] == "2015-05-22" and all(k in d["entorno"] for k in
                                                       ("python", "pandas", "numpy", "pyarrow", "scikit-learn")),
              "control: fecha_datos y las cinco versiones")
    comprobar(all(v is True for v in d["validaciones"].values() if v is not None) and
              sum(v is True for v in d["validaciones"].values()) >= 15, "control: las validaciones calculadas, en verde")
    comprobar(m_rotulos(d) == [], "6 · cada cifra del JSON con sus filas, las de entrenamiento rotuladas como tal")
    for objetivo in ("unidades", "dolares"):
        filas = [f for f in d["ranking"] if f["objetivo"] == objetivo]
        comprobar({f["algoritmo"] for f in filas} == {"HistGradientBoosting", "Ridge"},
                  f"control: una fila por algoritmo en {objetivo}")
        origenes = {tuple(f["origenes"]) for f in filas}
        minimo = json.loads((raiz / "informes" / "modelo_minimo.json").read_text(encoding="utf-8"))
        esperados = tuple(p["origen"] for p in minimo["modelo_minimo"][objetivo]["pliegues"])
        comprobar(origenes == {esperados}, f"2 · los dos algoritmos con los cortes del modelo mínimo en {objetivo}")
        comp = d["comparacion"][objetivo]
        comprobar(len(comp["diferencias"]) == 5 and comp["metodo"] == "pliegue a pliegue",
                  f"3 · la comparación de {objetivo}, pliegue a pliegue")
        g = d["ganador"][objetivo]
        comprobar(g["algoritmo"] in ("HistGradientBoosting", "Ridge") and g["semilla"] == 42 and g["columnas"]
                  and g["hiperparametros"] and g["aprobado_por"] == "", f"control: la receta del ganador de {objetivo}")
        comprobar(g["reajuste"]["filas_ajuste"] == len(tabla), f"control: el ganador de {objetivo}, reajustado con "
                                                               f"todo el entrenamiento")
        comprobar(d["importancias"][objetivo]["filas"].startswith("fuera de pliegue"),
                  f"control: importancias sobre filas fuera de pliegue en {objetivo}")
    ampliadas = d["busqueda"]["rejillas_ampliadas"]
    comprobar(any(a["hiperparametro"] == "max_iter" and a["medido"] for a in ampliadas) and
              any(a["hiperparametro"] == "alpha" for a in ampliadas),
              "4 · los bordes de la prueba se amplían y se dicen en el JSON")
    tabla_probada = pd.read_csv(raiz / "informes" / "modelado_busqueda.csv")
    comprobar(len(tabla_probada) >= 2 * (2 + 3) and {"objetivo", "algoritmo", "cv_media", "cv_desviacion",
                                                     "entrenamiento_media", "posicion"} <= set(tabla_probada.columns),
              "control: la tabla de lo probado, una fila por candidato")
    propuesta = (raiz / "informes" / "busqueda_propuesta.md").read_text(encoding="utf-8")
    comprobar("el responsable del caso" in propuesta and ", y " not in propuesta, "control: la propuesta escrita, sin «, y»")

    # La medida de tiempo con una muestra: no escribe nada
    raiz = TMP / "medir"
    montar(raiz, tabla, pp, pr)
    codigo, d, salida = ejecutar(raiz, "--medir", "0.9", "--candidatos", "1", "--objetivos", "unidades")
    comprobar(codigo == 0 and d is None and "estimación" in salida, f"control: --medir no escribe y estima "
                                                                    f"({salida[-800:] if codigo else ''})")

    # Al empezar: la preselección en PARADO, o cortes distintos de los del modelo mínimo, para sin medir
    raiz = TMP / "parado"
    montar(raiz, tabla, pp, pr, estado="PARADO")
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO" and not d.get("puerta_de_juan"),
              "con preseleccion.json en PARADO no empieza")
    raiz = TMP / "cortes"
    montar(raiz, tabla, pp, pr, desplazar_cortes=True)
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO" and
              "cortes" in d["resultado"]["resumen"], "2 · con cortes distintos de los del modelo mínimo no empieza")


def m_rotulos(d):
    """Los rótulos de filas del JSON, con la función del script (se carga en principal)."""
    return MODULO_SCRIPT.rotulos_de_filas(d)


# ── 8. Ejecución ───────────────────────────────────────────────────────────────
MODULO_SCRIPT = None


def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    global MODULO_SCRIPT
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/15_busqueda.py")
        else:
            sys.path.insert(0, str(SCRIPTS))
            vp = cargar(SCRIPTS / "variables_prevision.py", "variables_prevision")
            pp = cargar(SCRIPTS / "preparacion_prevision.py", "preparacion_prevision")
            pr = cargar(SCRIPTS / "prevision_recursiva.py", "prevision_recursiva")
            MODULO_SCRIPT = cargar(SCRIPT, "busqueda_15")
            tabla = tabla_entrenamiento(vp)
            casos_recursivo(MODULO_SCRIPT, pr, pp, tabla)
            casos_comparacion(MODULO_SCRIPT)
            casos_borde(MODULO_SCRIPT)
            casos_controles(MODULO_SCRIPT)
            casos_script(vp, pp, pr, tabla)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
