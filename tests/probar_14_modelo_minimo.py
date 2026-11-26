"""Prueba de scripts/prevision_recursiva.py y scripts/14_modelo_minimo.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_modelo_minimo/ una carpeta con la estructura
del caso (la tabla de entrenamiento, preseleccion.json, preparacion.json, particion.json y las dos fichas), ejecuta el
script sobre ella con --raiz y la borra al acabar. Importa el módulo prevision_recursiva.py, el de variables y el
script que prueba, que tiene su trabajo bajo __main__.

Los casos que tienen que fallar si el código está mal:
  1. la recursión usa la venta real de un día ya previsto;
  2. un retardo toma un día de otra serie;
  3. una previsión negativa pasa sin acotar (o entra sin acotar en la historia);
  4. un pliegue cuyo entrenamiento incluye un día de su prueba;
  5. una regla sencilla que usa un día posterior al origen;
  6. una cifra calculada sobre las filas del ajuste;
  7. una validación escrita con su resultado puesto (error 24).
Y el control que no debe disparar: el script entero sobre tablas limpias deja el JSON en AVISO, con todas las
validaciones en verde, la recursión a un día igual a la previsión con retardos reales y cada cifra con sus filas.
Además: las reglas a mano, el redondeo, el error contra la pieza común (error 30) y la permutación por grupos contra la
de scikit-learn (error 30).
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import make_scorer

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
MODULO = SCRIPTS / "prevision_recursiva.py"
SCRIPT = SCRIPTS / "14_modelo_minimo.py"
TMP = RAIZ / "tests" / "tmp_modelo_minimo"
FALLOS = []
SERIES = [("T_0", "D_0"), ("T_0", "D_1"), ("T_1", "D_0"), ("T_1", "D_1")]
EVENTOS = ["Ev_A", "Ev_B"]


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
def historia_simple(niveles, dias=40, inicio="2014-01-01"):
    """Una historia por serie con un nivel propio y un valor distinto cada día: store_id, dept_id, date, unidades."""
    fechas = pd.date_range(inicio, periods=dias, freq="D").astype("datetime64[us]")
    partes = []
    for (tienda, dept), nivel in niveles.items():
        partes.append(pd.DataFrame({"store_id": tienda, "dept_id": dept, "date": fechas,
                                    "unidades": (nivel + np.arange(dias)).astype("float64")}))
    return pd.concat(partes, ignore_index=True)


def futuro_simple(series, origen, dias, valor_real=99999.0):
    """Las filas de los días que se prevén, con un objetivo real y unos retardos falsos que no se pueden usar."""
    fechas = pd.date_range(origen + pd.Timedelta(1, "D"), periods=dias, freq="D").astype("datetime64[us]")
    filas = [{"store_id": t, "dept_id": d, "date": f, "unidades": valor_real, "unidades_lag_1": -1.0,
              "dolares": valor_real, "precio": 1.0} for t, d in series for f in fechas]
    return pd.DataFrame(filas)


class ModeloRetardo:
    """Modelo de prueba: prevé el retardo de un día más un desplazamiento, o una cuenta que puede salir negativa."""

    def __init__(self, desplazamiento=0.0, invertir=False):
        self.desplazamiento = desplazamiento
        self.invertir = invertir

    def predict(self, x):
        """La previsión: el retardo de un día (más el desplazamiento), o 10 menos el retardo si se invierte."""
        lag = x["unidades_lag_1"].to_numpy(dtype="float64")
        return 10.0 - lag if self.invertir else lag + self.desplazamiento


def tabla_entrenamiento(vp, dias=560):
    """La tabla de entrenamiento de la prueba: cuatro series, con calendario, eventos, precio y los retardos de los
    dos objetivos calculados con el módulo de variables; salen los 35 primeros días de cada serie, como en el caso."""
    rng = np.random.default_rng(7)
    fechas = pd.date_range("2013-01-05", periods=dias + 35, freq="D").astype("datetime64[us]")
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


def montar(raiz, tabla, pp, estado="AVISO", huella_falsa=False):
    """Escribe la carpeta del caso de la prueba con la tabla, los tres JSON previos y las dos fichas."""
    if raiz.exists():
        shutil.rmtree(raiz)
    pr = raiz / "data" / "processed"
    pr.mkdir(parents=True)
    (raiz / "informes").mkdir()
    for carpeta in ("histgradientboosting", "regresion_lineal_y_regularizadas"):
        ficha = raiz / "assets" / "fichas_de_algoritmos" / carpeta
        ficha.mkdir(parents=True)
        (ficha / "01_ficha.md").write_text("# ficha de la prueba\n", encoding="utf-8")
    tabla.to_parquet(pr / "hechos_modelo_entrenamiento.parquet", index=False)
    sha = "0" * 64 if huella_falsa else huella(pr / "hechos_modelo_entrenamiento.parquet")
    objetivos = {}
    for objetivo in ("unidades", "dolares"):
        salida = columnas_salida(pp, tabla, objetivo)
        hgb = list(salida)
        # Ridge sin dos retardos, como si la votación los hubiera quitado; event_name_* sigue en las dos listas
        ridge = [c for c in salida if c not in (f"{objetivo}_lag_2_rs", f"{objetivo}_lag_3_rs")]
        objetivos[objetivo] = {"columnas_finales": {"Ridge": ridge, "HistGradientBoosting": hgb}}
    pres = {"fecha_datos": "2015-05-22", "resultado": {"estado": estado},
            "entradas": [{"ruta": "data/processed/hechos_modelo_entrenamiento.parquet", "sha256": sha}],
            "objetivos": objetivos}
    prep = {"fecha_datos": "2015-05-22", "resultado": {"estado": "OK"}, "matriz": {"aprobada_por": "el responsable del caso"},
            "entradas": [{"ruta": "data/processed/hechos_modelo_entrenamiento.parquet", "sha256": sha}],
            "fuera": [{"variable": v, "motivo": "prueba"} for v in
                      ("d", "unidades", "dolares", "periodo", "cierre_tienda", "fuera_del_error", "clase_cero")]}
    part = {"fecha_datos": "2015-05-22", "resultado": {"estado": "OK"}}
    for nombre, datos in (("preseleccion", pres), ("preparacion", prep), ("particion", part)):
        (raiz / "informes" / f"{nombre}.json").write_text(json.dumps(datos), encoding="utf-8")


def ejecutar(raiz):
    """Ejecuta el script con -W error sobre la carpeta de la prueba; devuelve código, JSON y salida."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)],
                          capture_output=True, text=True, encoding="utf-8", env=entorno)
    ruta = raiz / "informes" / "modelo_minimo.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


# ── 3. La previsión recursiva ──────────────────────────────────────────────────
def casos_recursion(pr):
    """Casos 1, 2 y 3, con un modelo de prueba que prevé el retardo de un día."""
    niveles = {("T_0", "D_0"): 100.0, ("T_1", "D_1"): 5000.0}
    historia = historia_simple(niveles)
    origen = historia["date"].max()
    futuro = futuro_simple(niveles, origen, 5)
    previsto = pr.prever_recursivo(ModeloRetardo(), historia, futuro, "unidades", 5)
    comprobar(len(previsto) == 2 * 5 and set(previsto["h"]) == {1, 2, 3, 4, 5},
              "recursión: una fila por serie y día del horizonte")
    a = previsto[previsto["store_id"] == "T_0"].sort_values("h")["prevision"].to_numpy()
    b = previsto[previsto["store_id"] == "T_1"].sort_values("h")["prevision"].to_numpy()
    ultimo_a = 100.0 + 39
    ultimo_b = 5000.0 + 39
    # 1 · con el retardo de un día, cada día previsto repite el anterior previsto: el último real del origen
    comprobar(np.allclose(a, ultimo_a), "1 · la recursión usa lo previsto y nunca la venta real del día ya previsto")
    otro = futuro_simple(niveles, origen, 5, valor_real=-7.0)
    comprobar(pr.prever_recursivo(ModeloRetardo(), historia, otro, "unidades", 5).equals(previsto),
              "1 · cambiar la venta real y los retardos del futuro no cambia nada")
    # La historia posterior al origen tampoco entra
    con_futuro_real = pd.concat([historia, futuro_simple(niveles, origen, 3)[["store_id", "dept_id", "date",
                                                                                "unidades"]]])
    comprobar(pr.prever_recursivo(ModeloRetardo(), con_futuro_real, futuro, "unidades", 5, origen=origen)
              .equals(previsto), "1 · una historia con días posteriores al origen se corta en el origen")
    # 2 · cada serie toma sus propios días
    comprobar(np.allclose(b, ultimo_b) and not np.allclose(a, b), "2 · ningún retardo toma un día de otra serie")
    # Control: con un desplazamiento, el día h vale el último real más h veces el desplazamiento
    sube = pr.prever_recursivo(ModeloRetardo(desplazamiento=2.0), historia, futuro, "unidades", 5)
    s = sube[sube["store_id"] == "T_0"].sort_values("h")["prevision"].to_numpy()
    comprobar(np.allclose(s, ultimo_a + 2.0 * np.arange(1, 6)), "control: cada día suma sobre lo ya previsto")
    # 3 · una previsión negativa se acota en cero y entra acotada en la historia: 10 − 139 < 0 → 0; después 10 − 0
    neg = pr.prever_recursivo(ModeloRetardo(invertir=True), historia, futuro, "unidades", 3)
    n = neg[neg["store_id"] == "T_0"].sort_values("h")["prevision"].to_numpy()
    comprobar((neg["prevision"] >= 0).all(), "3 · ninguna previsión negativa")
    comprobar(np.allclose(n, [0.0, 10.0, 0.0]), "3 · lo acotado en cero es lo que entra en la historia")
    # Una historia con un día que falta antes del origen: para
    corta = historia[~((historia["store_id"] == "T_0") & (historia["date"] == origen - pd.Timedelta(3, "D")))]
    try:
        pr.prever_recursivo(ModeloRetardo(), corta, futuro, "unidades", 5)
        comprobar(False, "una historia con un hueco en los 28 días anteriores al origen para")
    except ValueError:
        comprobar(True, "una historia con un hueco en los 28 días anteriores al origen para")
    # Un futuro al que le falta un día de una serie: para
    try:
        pr.prever_recursivo(ModeloRetardo(), historia, futuro.iloc[1:], "unidades", 5)
        comprobar(False, "un futuro sin una fila de una serie y un día para")
    except ValueError:
        comprobar(True, "un futuro sin una fila de una serie y un día para")


# ── 4. Las reglas, las cifras y los pliegues ───────────────────────────────────
def casos_reglas(pr):
    """Caso 5 y las reglas calculadas a mano."""
    historia = historia_simple({("T_0", "D_0"): 0.0}, dias=40)
    origen = historia["date"].max()
    r = pr.reglas_sencillas(historia, "unidades", origen, 10).sort_values("h").reset_index(drop=True)
    y = historia["unidades"].to_numpy()          # y[39] es el origen
    comprobar(list(r["h"]) == list(range(1, 11)), "reglas: una fila por día del horizonte")
    # Repetir la semana anterior: el día h toma y[origen − 6 + (h − 1) mod 7]
    esperado = [y[33 + (h - 1) % 7] for h in range(1, 11)]
    comprobar(np.allclose(r["repetir_semana_anterior"], esperado), "reglas: repetir la semana anterior, a mano")
    comprobar(np.allclose(r["media_28_dias"], y[12:40].mean()), "reglas: media de los 28 días con el origen")
    mismo = [np.mean([y[i] for i in range(12, 40) if (i - (39 + h)) % 7 == 0]) for h in range(1, 11)]
    comprobar(np.allclose(r["media_mismo_dia_4_semanas"], mismo), "reglas: media del mismo día de 4 semanas, a mano")
    # 5 · días posteriores al origen con valores enormes: las reglas no cambian
    despues = historia_simple({("T_0", "D_0"): 1e6}, dias=10, inicio=str((origen + pd.Timedelta(1, "D")).date()))
    con_despues = pd.concat([historia, despues], ignore_index=True)
    r2 = pr.reglas_sencillas(con_despues, "unidades", origen, 10).sort_values("h").reset_index(drop=True)
    comprobar(r2.equals(r), "5 · ninguna regla usa un día posterior al origen")


def casos_cifras(pr):
    """El error y el sesgo contra la pieza común (error 30) y el redondeo."""
    sys.path.insert(0, str(RAIZ / "assets"))
    ec = cargar(RAIZ / "assets" / "evaluacion_continua.py", "evaluacion_continua")
    real = np.array([10.0, 0.0, 5.0, 20.0, 7.0])
    prev = np.array([12.0, 1.0, 3.0, 15.0, 7.0])
    error, sesgo = pr.error_y_sesgo(real, prev)
    m = ec.medidas(real, prev)
    comprobar(np.isclose(error, 100 * m["wape"]), "error: 100 × WAPE de la pieza común")
    comprobar(np.isclose(sesgo, 100 * m["sesgo"] / m["media_real"]), "sesgo: con signo, por cada 100 vendidas")
    comprobar(np.isclose(error, 100 * 10 / 42) and np.isclose(sesgo, 100 * -4 / 42), "error y sesgo, a mano")
    comprobar(list(pr.redondear_unidades([0.49, 0.5, 2.5, 3.4999, 7.0])) == [0.0, 1.0, 3.0, 3.0, 7.0],
              "redondeo de unidades: mitad hacia arriba, sin cortar decimales")
    try:
        pr.redondear_unidades([-0.2])
        comprobar(False, "redondear una previsión negativa para")
    except ValueError:
        comprobar(True, "redondear una previsión negativa para")


def casos_pliegues(pr):
    """Caso 4: los pliegues por día y su comprobación."""
    fechas = pd.Series(np.repeat(pd.date_range("2014-01-01", periods=100, freq="D").astype("datetime64[us]"), 3))
    pliegues = pr.pliegues_por_dia(fechas, 5, 10)
    comprobar(len(pliegues) == 5, "pliegues: cinco")
    comprobar(all(len(p["dias_prueba"]) == 10 for p in pliegues), "pliegues: diez días de prueba en cada uno")
    comprobar(pliegues[-1]["dias_prueba"][-1] == fechas.max() and pliegues[0]["dias_prueba"][0]
              == fechas.max() - pd.Timedelta(49, "D"), "pliegues: los 50 últimos días, sin barajar")
    comprobar(all(pr.comprobar_pliegue(p["dias_ajuste"], p["dias_prueba"], 10)["bien"] for p in pliegues),
              "control: los pliegues buenos pasan su comprobación")
    comprobar(all(p["origen"] == p["dias_ajuste"].max() for p in pliegues), "pliegues: el origen es el último día "
                                                                             "del ajuste")
    malo = pliegues[2]
    con_prueba = np.append(malo["dias_ajuste"], malo["dias_prueba"][4])
    comprobar(not pr.comprobar_pliegue(con_prueba, malo["dias_prueba"], 10)["bien"],
              "4 · un pliegue cuyo entrenamiento incluye un día de su prueba sale en rojo")
    comprobar(not pr.comprobar_pliegue(malo["dias_ajuste"], malo["dias_prueba"][:9], 10)["bien"],
              "4 · un pliegue con menos días de prueba que el horizonte sale en rojo")


# ── 5. Las funciones del script ────────────────────────────────────────────────
def casos_funciones_script(m):
    """Casos 6 y 7 y la permutación por grupos contra la de scikit-learn."""
    comprobar(m.sin_filas_de_ajuste(np.array([1, 2, 3]), np.array([4, 5])), "control: filas distintas pasan")
    comprobar(not m.sin_filas_de_ajuste(np.array([1, 2, 3]), np.array([3, 4])),
              "6 · una cifra medida sobre una fila del ajuste sale en rojo")
    malo = 'v = {"reproducible": True, "pliegues_por_fecha": (False)}\nvalidaciones["sin_filas_de_ajuste"] = True\n'
    comprobar(len(m.buscar_resultados_escritos(malo)) == 3, "7 · una validación con su resultado puesto se encuentra")
    comprobar(m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8")) == [],
              "7 · el script no escribe ninguna validación con su resultado puesto")
    # Permutación por grupos de una columna = permutation_importance de scikit-learn, con la misma semilla
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.normal(size=(80, 3)), columns=["a", "b", "c"])
    y = 3 * x["a"] - x["b"] + rng.normal(scale=0.1, size=80) + 10
    modelo = LinearRegression().fit(x, y)

    def puntuar(real, previsto):
        return -float(np.abs(np.asarray(previsto) - np.asarray(real)).sum())

    propia = m.importancia_por_grupos(modelo, x, y, {"a": ["a"], "b": ["b"], "c": ["c"]}, puntuar, 5, 42)
    ref = permutation_importance(modelo, x, y, n_repeats=5, random_state=42,
                                 scoring=make_scorer(lambda r, p: puntuar(r, p)))
    comprobar(np.allclose([propia[k]["media"] for k in "abc"], ref.importances_mean)
              and np.allclose([propia[k]["desviacion"] for k in "abc"], ref.importances_std),
              "permutación por grupos de una columna igual a la de scikit-learn (error 30)")
    juntas = m.importancia_por_grupos(modelo, x, y, {"ab": ["a", "b"], "c": ["c"]}, puntuar, 5, 42)
    comprobar(juntas["ab"]["media"] > propia["a"]["media"] > 0 and abs(juntas["c"]["media"]) < propia["b"]["media"],
              "permutación: un grupo se permuta junto y una columna sin peso queda cerca de cero")


# ── 6. El script entero ────────────────────────────────────────────────────────
def todas_las_cifras(nodo, camino=""):
    """Los diccionarios del JSON con «error» o «sesgo» y su camino."""
    salida = []
    if isinstance(nodo, dict):
        if "error" in nodo or "sesgo" in nodo:
            salida.append((camino, nodo))
        for k, v in nodo.items():
            salida += todas_las_cifras(v, f"{camino}/{k}")
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            salida += todas_las_cifras(v, f"{camino}[{i}]")
    return salida


def casos_script(vp, pp):
    """El control que no debe disparar y las paradas al empezar."""
    tabla = tabla_entrenamiento(vp)
    raiz = TMP / "base"
    montar(raiz, tabla, pp)
    ruta_tabla = raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet"
    antes = huella(ruta_tabla)
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "AVISO",
              f"control: el script entero en AVISO, con la puerta del responsable del caso ({salida[-900:] if codigo else ''} "
              f"{[k for k, x in (d or {}).get('validaciones', {}).items() if x is False]})")
    if d is None or codigo != 0:
        return
    comprobar(huella(ruta_tabla) == antes, "control: la tabla de entrenamiento no cambia")
    comprobar(d["fecha_datos"] == "2015-05-22" and all(k in d["entorno"] for k in
                                                       ("python", "pandas", "numpy", "pyarrow", "scikit-learn")),
              "control: fecha_datos y las cinco versiones")
    comprobar(all(v is True for v in d["validaciones"].values() if v is not None) and
              sum(v is True for v in d["validaciones"].values()) >= 10, "control: las validaciones calculadas, en verde")
    for objetivo, h in (("unidades", 10), ("dolares", 28)):
        mm = d["modelo_minimo"][objetivo]
        comprobar(len(mm["pliegues"]) == 5 and all(p["dias_prueba"]["dias"] == h for p in mm["pliegues"]),
                  f"control: cinco pliegues de {h} días en {objetivo}")
        cols = mm["receta"]["columnas"]
        comprobar(not any(c.startswith(("event_name_1", "event_name_2")) for c in cols)
                  and len(cols) == len(columnas_salida(pp, tabla, objetivo)) - sum(
                      c.startswith(("event_name_1", "event_name_2")) for c in columnas_salida(pp, tabla, objetivo)),
                  f"control: las columnas de HistGradientBoosting sin event_name_1 ni event_name_2 en {objetivo}")
        comprobar(all(p["recursiva_a_un_dia_igual"] for p in mm["pliegues"]),
                  f"control: la recursión a un día da lo mismo que los retardos reales en {objetivo}")
        comprobar(all(p["recursiva"]["modelo"]["error"] >= 0 for p in mm["pliegues"]),
                  f"control: errores calculados en {objetivo}")
        comprobar(mm["importancias"]["valores"] and mm["importancias"]["filas"].startswith("fuera de pliegue"),
                  f"control: importancias por permutación sobre filas fuera de pliegue en {objetivo}")
    cifras = todas_las_cifras(d)
    comprobar(cifras and all("filas" in c for _, c in cifras), "6 · cada cifra del JSON dice sobre qué filas se calculó")
    comprobar(all(c["filas"] == "entrenamiento" for k, c in cifras if k.endswith("/entrenamiento")) and
              all(c["filas"].startswith("fuera de pliegue") for k, c in cifras if not k.endswith("/entrenamiento")),
              "6 · solo las cifras de entrenamiento llevan filas de entrenamiento")
    coste = d["coste"]
    comprobar({c["algoritmo"] for c in coste["algoritmos"]} == {"HistGradientBoosting", "bosque", "Ridge"} and
              all(c["segundos_ajuste"] > 0 for c in coste["algoritmos"]), "control: tiempos medidos de los tres")
    comprobar({n["nivel"] for n in coste["niveles"]} == {"rapido", "equilibrado", "exhaustivo"}, "control: tres niveles")

    # Al empezar: la preselección en PARADO, o la tabla con otra huella, para sin medir
    raiz = TMP / "parado"
    montar(raiz, tabla, pp, estado="PARADO")
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO",
              "con preseleccion.json en PARADO no empieza")
    raiz = TMP / "huella"
    montar(raiz, tabla, pp, huella_falsa=True)
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO",
              "con otra huella de la tabla no empieza")


# ── 7. Ejecución ───────────────────────────────────────────────────────────────
def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    try:
        if not MODULO.exists() or not SCRIPT.exists():
            comprobar(False, "existen scripts/prevision_recursiva.py y scripts/14_modelo_minimo.py")
        else:
            sys.path.insert(0, str(SCRIPTS))
            vp = cargar(SCRIPTS / "variables_prevision.py", "variables_prevision")
            pp = cargar(SCRIPTS / "preparacion_prevision.py", "preparacion_prevision")
            pr = cargar(MODULO, "prevision_recursiva")
            m = cargar(SCRIPT, "modelo_minimo_14")
            casos_recursion(pr)
            casos_reglas(pr)
            casos_cifras(pr)
            casos_pliegues(pr)
            casos_funciones_script(m)
            casos_script(vp, pp)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
