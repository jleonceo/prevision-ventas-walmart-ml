"""Prueba de scripts/16_validacion.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_validacion/ una carpeta con la estructura del
caso (las cuatro tablas, busqueda.json con una receta pequeña, preseleccion.json, preparacion.json, particion.json, los
planteamientos con la aprobación escrita en la copia, la ficha y la pieza de evaluación), ejecuta el script sobre ella
con --raiz y la borra al acabar. Importa los módulos del caso y el script que prueba, que tiene su trabajo bajo __main__.

Los casos que tienen que fallar si el código está mal:
  1. la validación cargada antes de leer la receta;
  2. una previsión medida a un día y no en recursivo;
  3. un origen con su horizonte fuera de la validación;
  4. una regla comparada con otros días que el modelo;
  5. el intervalo remuestreando filas y no series;
  6. la ventaja calculada con una sola regla para todos los orígenes;
  7. el 25 de diciembre dentro del error;
  8. un mes parcial comparado;
  9. un suavizado ajustado con días después del origen;
 10. una validación escrita con su resultado puesto (error 24);
 11. el aporte de las series que no suma la ventaja, o calculado con otra regla que la de cada origen;
 12. la ventaja sin una tienda calculada con la regla elegida con todas;
 13. el intervalo por tienda que remuestrea series;
 14. un evento contado como cubierto por caer en un día fuera del error o fuera del horizonte;
 15. un departamento con dos categorías (o una tienda con dos estados);
 16. una suma de unidades sin redondear cada serie antes;
 17. el error del grupo calculado como media de los errores de sus series;
 18. un grupo con días de otro origen mezclados;
 19. la cadena que no da el error de las series sumadas.
Y el control que no debe disparar: el script entero sobre tablas limpias para en la puerta del responsable del caso, con todas las
validaciones en verde, los 13 orígenes, los días previstos de cada serie, las cuatro salidas y los bloques «robustez»
y «niveles».
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
from sklearn.ensemble import HistGradientBoostingRegressor

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
SCRIPT = SCRIPTS / "16_validacion.py"
PIEZA = RAIZ / "assets" / "evaluacion_continua.py"
TMP = RAIZ / "tests" / "tmp_validacion"
FALLOS = []
SERIES = [("T_0", "D_0"), ("T_0", "D_1"), ("T_1", "D_0"), ("T_1", "D_1")]
EVENTOS = ["Ev_A", "Ev_B"]
# Con este inicio, el entrenamiento tiene los doce meses, como en el caso: el codificador los conoce todos
INICIO = "2013-03-01"
FIN_CONSTRUCCION = pd.Timestamp("2014-05-22")
FIN_VALIDACION = pd.Timestamp("2015-05-22")
APROBACION = "**Ganador (el responsable del caso, 25/11/2026, «Apruebo el ganador»):** receta de la prueba."


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
def tablas(vp):
    """Cuatro series diarias del 01/03/2013 al 22/05/2015 con ritmo semanal, eventos, SNAP, precio y un 25 de
    diciembre cerrado. Devuelve la tabla de series entera y la de modelo, con los retardos del módulo de variables y sin
    los 35 primeros días de cada serie, como en el caso."""
    rng = np.random.default_rng(11)
    fechas = pd.date_range(INICIO, FIN_VALIDACION, freq="D").astype("datetime64[us]")
    partes = []
    for k, (tienda, dept) in enumerate(SERIES):
        fin_de_semana = (fechas.dayofweek >= 5).astype(int)
        unidades = np.maximum(0, 30 + 12 * k + 10 * fin_de_semana + rng.integers(-6, 7, len(fechas)))
        navidad = (fechas.month == 12) & (fechas.day == 25)
        unidades = np.where(navidad, 0, unidades)
        evento = [EVENTOS[(i // 20) % 2] if i % 20 == 3 else None for i in range(len(fechas))]
        evento_2 = ["Ev_B" if i % 20 == 13 else None for i in range(len(fechas))]
        precio = 2.0 + k * 0.5
        partes.append(pd.DataFrame({
            "store_id": tienda, "dept_id": dept, "d": [f"d_{i + 1}" for i in range(len(fechas))], "date": fechas,
            "weekday": fechas.day_name(), "month": fechas.month.astype("int64"), "event_name_1": evento,
            "event_name_2": evento_2, "snap": ((fechas.day <= 10) & (k % 2 == 0)).astype("int64"),
            "precio_medio_semana_anterior": precio, "productos_con_precio_semana_anterior": 10 + k,
            "dia_del_mes": fechas.day.astype("int64"), "fuera_del_error": navidad,
            "unidades": unidades.astype("int64"), "dolares": np.round(unidades * precio, 2)}))
    t = pd.concat(partes, ignore_index=True)
    for c in ["store_id", "dept_id", "d", "weekday", "event_name_1", "event_name_2"]:
        t[c] = t[c].astype("str")
    t.loc[t["event_name_1"] == "None", "event_name_1"] = None
    t.loc[t["event_name_2"] == "None", "event_name_2"] = None
    for e in EVENTOS:
        t[f"evento_{e}"] = ((t["event_name_1"] == e).fillna(False) | (t["event_name_2"] == e).fillna(False)).astype(
            "int64")
    series = t[["store_id", "dept_id", "date", "unidades", "dolares", "fuera_del_error"]].copy()
    modelo = t.copy()
    for objetivo in ("unidades", "dolares"):
        modelo = modelo.join(vp.crear_variables_objetivo(modelo, objetivo))
    primer = modelo.groupby(["store_id", "dept_id"])["date"].transform("min")
    modelo = modelo[modelo["date"] >= primer + pd.Timedelta(35, "D")].reset_index(drop=True)
    return series, modelo


def columnas_salida(pp, tabla, objetivo):
    """Los nombres que da el preprocesador del caso con esta tabla."""
    eventos = [c for c in tabla.columns if c.startswith("evento_")]
    pipe = pp.construir_preprocesador(objetivo, eventos).fit(tabla)
    return list(pipe.transform(tabla.head(3)).columns)


def receta_de_prueba():
    """Los hiperparámetros enteros de un boosting pequeño, como los escribe la búsqueda (get_params)."""
    return HistGradientBoostingRegressor(early_stopping=False, max_iter=15, min_samples_leaf=20, learning_rate=0.2,
                                         random_state=42).get_params()


def montar(raiz, series, modelo, pp, m, receta_rota=False):
    """Escribe la carpeta del caso de la prueba. Con receta_rota, la receta no tiene ganador y la validación de modelo
    es un texto: si el script la abriera antes de leer la receta, se rompería."""
    if raiz.exists():
        shutil.rmtree(raiz)
    procesados = raiz / "data" / "processed"
    procesados.mkdir(parents=True)
    (raiz / "informes").mkdir()
    (raiz / "config" / "metodo").mkdir(parents=True)
    ficha = raiz / "assets" / "fichas_de_algoritmos" / "histgradientboosting"
    ficha.mkdir(parents=True)
    (ficha / "01_ficha.md").write_text("# ficha de la prueba\n", encoding="utf-8")
    shutil.copyfile(PIEZA, raiz / "assets" / "evaluacion_continua.py")
    (raiz / "config" / "metodo" / "04_planteamientos.md").write_text(
        f"# Planteamientos de la prueba\n\n{APROBACION}\n", encoding="utf-8")

    rutas = {"me": "data/processed/hechos_modelo_entrenamiento.parquet",
             "mv": "data/processed/hechos_modelo_validacion.parquet",
             "se": "data/processed/hechos_series_entrenamiento.parquet",
             "sv": "data/processed/hechos_series_validacion.parquet"}
    modelo[modelo["date"] <= FIN_CONSTRUCCION].to_parquet(raiz / rutas["me"], index=False)
    series[series["date"] <= FIN_CONSTRUCCION].to_parquet(raiz / rutas["se"], index=False)
    series[series["date"] > FIN_CONSTRUCCION].to_parquet(raiz / rutas["sv"], index=False)
    if receta_rota:
        (raiz / rutas["mv"]).write_text("no se abre", encoding="utf-8")
    else:
        modelo[modelo["date"] > FIN_CONSTRUCCION].to_parquet(raiz / rutas["mv"], index=False)
    h = {k: huella(raiz / v) for k, v in rutas.items()}
    # El calendario, un día por fila, con los eventos de las tablas (como data/processed/calendario_corregido.parquet)
    calendario = modelo[["date", "event_name_1", "event_name_2"]].drop_duplicates("date").reset_index(drop=True)
    calendario.to_parquet(procesados / "calendario_corregido.parquet", index=False)
    # Las dimensiones, como data/processed/dim_producto.parquet y dim_tienda.parquet: un producto por fila, varios por
    # departamento; cada departamento en su categoría y cada tienda en su estado
    pd.DataFrame({"item_id": ["I_1", "I_2", "I_3", "I_4"], "dept_id": ["D_0", "D_0", "D_1", "D_1"],
                  "cat_id": ["CAT_A", "CAT_A", "CAT_B", "CAT_B"]}).to_parquet(procesados / "dim_producto.parquet",
                                                                              index=False)
    pd.DataFrame({"store_id": ["T_0", "T_1"], "state_id": ["ST_A", "ST_B"]}).to_parquet(
        procesados / "dim_tienda.parquet", index=False)

    entrenamiento = modelo[modelo["date"] <= FIN_CONSTRUCCION]
    eventos = [c for c in modelo.columns if c.startswith("evento_")]
    objetivos, ganador = {}, {}
    for objetivo in ("unidades", "dolares"):
        salida = columnas_salida(pp, entrenamiento, objetivo)
        objetivos[objetivo] = {"columnas_finales": {"HistGradientBoosting": salida}}
        columnas = [c for c in salida if not c.startswith(("event_name_1_ohe_", "event_name_2_ohe_"))]
        hiper = receta_de_prueba()
        # La cifra de entrenamiento del reajuste, como la escribe la búsqueda: a un día, sin los 25 de diciembre
        orden = entrenamiento.sort_values(["date", "store_id", "dept_id"], kind="stable").reset_index(drop=True)
        final = m.construir_modelo(objetivo, eventos, columnas, hiper)
        final.fit(orden[m.entrada_de(objetivo, eventos)], orden[objetivo])
        medidas = orden[~orden["fuera_del_error"].to_numpy()]
        error = m.pr.error_y_sesgo(medidas[objetivo], m.previsto_medible(
            final.predict(medidas[m.entrada_de(objetivo, eventos)]), objetivo))[0]
        ganador[objetivo] = {"algoritmo": "HistGradientBoosting", "clase": "HistGradientBoostingRegressor",
                             "ficha": "assets/fichas_de_algoritmos/histgradientboosting/01_ficha.md",
                             "hiperparametros": hiper, "semilla": 42, "columnas": columnas,
                             "n_columnas": len(columnas), "aprobado_por": "",
                             "reajuste": {"filas_ajuste": len(orden), "entrenamiento": {
                                 "error": error, "filas": "entrenamiento: prueba"}}}
    busqueda = {"fecha_datos": "2015-05-22", "resultado": {"estado": "PARADO"}, "puerta_de_juan": True,
                "entradas": [{"ruta": rutas["me"], "sha256": h["me"], "filas": len(entrenamiento)}],
                "tabla": {"filas": len(entrenamiento)}}
    if not receta_rota:
        busqueda["ganador"] = ganador
    pres = {"resultado": {"estado": "AVISO"}, "objetivos": objetivos}
    prep = {"resultado": {"estado": "OK"},
            "entradas": [{"ruta": rutas["me"], "sha256": h["me"]}, {"ruta": rutas["mv"], "sha256": h["mv"]}],
            "fuera": [{"variable": v, "motivo": "prueba"} for v in
                      ("d", "unidades", "dolares", "periodo", "cierre_tienda", "fuera_del_error", "clase_cero")]}
    validacion = series[series["date"] > FIN_CONSTRUCCION]
    part = {"resultado": {"estado": "OK"}, "partes": [
        {"parte": "entrenamiento", "ruta": rutas["se"], "sha256": h["se"]},
        {"parte": "validacion", "ruta": rutas["sv"], "sha256": h["sv"], "filas": len(validacion),
         "fecha_min": f"{validacion['date'].min():%Y-%m-%d}", "fecha_max": f"{validacion['date'].max():%Y-%m-%d}",
         "dias": int(validacion["date"].nunique()), "combinaciones": len(SERIES)}]}
    for nombre, datos in (("busqueda", busqueda), ("preseleccion", pres), ("preparacion", prep),
                          ("particion", part)):
        (raiz / "informes" / f"{nombre}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return huella(raiz / "informes" / "busqueda.json")


def ejecutar(raiz, huella_receta, *extra):
    """Ejecuta el script con -W error sobre la carpeta de la prueba; devuelve código, JSON y salida."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz),
                           "--huella-receta", huella_receta, *extra],
                          capture_output=True, text=True, encoding="utf-8", env=entorno)
    ruta = raiz / "informes" / "validacion.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


class ModeloRetardo:
    """Modelo de prueba: prevé el retardo de un día más 3; no aprende nada."""

    def predict(self, x):
        """El retardo de un día más 3."""
        return x["unidades_lag_1"].to_numpy(dtype="float64") + 3.0


# ── 3. Caso 1: la validación, después de la receta ─────────────────────────────
def casos_orden(m):
    """El registro de lecturas: la receta primero y cada tabla de validación una sola vez."""
    bien = [{"paso": "receta", "ruta": "informes/busqueda.json"},
            {"paso": "validacion", "ruta": "data/processed/hechos_modelo_validacion.parquet"},
            {"paso": "validacion", "ruta": "data/processed/hechos_series_validacion.parquet"}]
    comprobar(m.orden_de_lectura_bien(bien), "control: la receta y después cada validación una vez pasa")
    comprobar(not m.orden_de_lectura_bien([bien[1], bien[0], bien[2]]),
              "1 · la validación cargada antes de leer la receta sale en rojo")
    comprobar(not m.orden_de_lectura_bien(bien + [bien[1]]), "1 · una validación cargada dos veces sale en rojo")
    comprobar(not m.orden_de_lectura_bien(bien[1:]), "1 · una validación cargada sin receta sale en rojo")


# ── 4. Caso 2: en recursivo ────────────────────────────────────────────────────
def casos_recursivo(m, pr, modelo):
    """La medida del modelo es la recursiva entera desde el origen; una previsión a un día no pasa."""
    t = modelo.sort_values(["date", "store_id", "dept_id"]).reset_index(drop=True)
    origen = FIN_CONSTRUCCION
    historia = t[["store_id", "dept_id", "date", "unidades"]]
    futuro = t[(t["date"] > origen) & (t["date"] <= origen + pd.Timedelta(10, "D"))]
    rec = m.prever_modelo(ModeloRetardo(), historia, futuro, "unidades", origen, 10)
    a_mano = pr.prever_recursivo(ModeloRetardo(), historia, futuro, "unidades", 10, origen=origen)
    junto = futuro.merge(a_mano, on=["store_id", "dept_id", "date"])
    un_dia = junto["unidades_lag_1"] + 3.0
    comprobar(float(np.abs(un_dia - junto["prevision"]).max()) > 0.5,
              "control: con este modelo, a un día y en recursivo dan cifras distintas")
    unido = rec.merge(a_mano, on=["store_id", "dept_id", "date", "h"], suffixes=("", "_a_mano"))
    comprobar(len(unido) == 40 and np.allclose(unido["modelo"], unido["prevision"]),
              "2 · el modelo se prevé con prever_recursivo desde el origen, no a un día")
    comprobar(m.comprobar_recursiva(a_mano, 4, origen, 10), "control: la recursiva entera pasa su comprobación")
    comprobar(not m.comprobar_recursiva(a_mano[a_mano["h"] == 1], 4, origen, 10),
              "2 · una previsión a un día sale en rojo en la comprobación de recursiva")
    comprobar(not m.comprobar_recursiva(a_mano.assign(h=1), 4, origen, 10),
              "2 · todos los días con h = 1 salen en rojo")


# ── 5. Caso 3: los orígenes ────────────────────────────────────────────────────
def casos_origenes(m):
    """13 orígenes cada 28 días, del 22/05/2014 al 23/04/2015; un horizonte fuera de la validación sale en rojo."""
    origenes = m.generar_origenes(pd.Timestamp("2014-05-22"), 13, 28)
    comprobar(len(origenes) == 13 and origenes[-1] == pd.Timestamp("2015-04-23"),
              "control: los 13 orígenes acaban el 23/04/2015")
    dias = pd.date_range("2014-05-23", "2015-05-22", freq="D")
    bien = m.comprobar_origenes(origenes, {"unidades": 10, "dolares": 28}, dias)
    comprobar(bien["bien"], "control: los 13 orígenes con sus horizontes dentro de la validación pasan")
    fuera = origenes[:-1] + [pd.Timestamp("2015-05-10")]
    comprobar(not m.comprobar_origenes(fuera, {"unidades": 10, "dolares": 28}, dias)["bien"],
              "3 · un origen con su horizonte fuera de la validación sale en rojo")
    antes = [pd.Timestamp("2014-05-10")] + origenes[1:]
    comprobar(not m.comprobar_origenes(antes, {"unidades": 10, "dolares": 28}, dias)["bien"],
              "3 · un origen con su horizonte dentro de la construcción sale en rojo")
    comprobar(m.sin_prueba_final(dias, pd.Timestamp("2015-05-22")) and
              not m.sin_prueba_final(dias.append(pd.DatetimeIndex(["2015-05-23"])), pd.Timestamp("2015-05-22")),
              "control: un día de la prueba final en la validación sale en rojo")


# ── 6. Caso 4: los mismos días ─────────────────────────────────────────────────
def casos_mismas_filas(m):
    """Una regla con otros días que el modelo no se une; las mismas filas, sí."""
    fechas = pd.date_range("2014-05-23", periods=3, freq="D")
    base = pd.DataFrame({"store_id": "T_0", "dept_id": "D_0", "date": fechas, "unidades": [5, 6, 7]})
    modelo = base[["store_id", "dept_id", "date"]].assign(h=[1, 2, 3], modelo=[5.0, 5.0, 5.0])
    regla = base[["store_id", "dept_id", "date"]].assign(regla=[4.0, 4.0, 4.0])
    unido = m.unir_previsiones(base, {"modelo": modelo, "regla": regla})
    comprobar(len(unido) == 3 and unido[["modelo", "regla"]].notna().all().all(),
              "control: el modelo y la regla con los mismos días se unen")
    corrida = regla.assign(date=regla["date"] + pd.Timedelta(1, "D"))
    try:
        m.unir_previsiones(base, {"modelo": modelo, "regla": corrida})
        comprobar(False, "4 · una regla comparada con otros días que el modelo sale en rojo")
    except ValueError:
        comprobar(True, "4 · una regla comparada con otros días que el modelo sale en rojo")
    try:
        m.unir_previsiones(base, {"modelo": modelo, "regla": regla.iloc[:2]})
        comprobar(False, "4 · una regla con un día de menos sale en rojo")
    except ValueError:
        comprobar(True, "4 · una regla con un día de menos sale en rojo")


# ── 7. Casos 5 y 6: el intervalo y la ventaja ──────────────────────────────────
def casos_ventaja(m):
    """La ventaja usa la regla que menos falla en cada origen; el intervalo remuestrea series enteras."""
    # Dos series, dos orígenes, dos reglas; 10 vendidas por serie y origen
    real = np.full((2, 2), 10.0)
    modelo = np.array([[2.0, 3.0], [2.0, 3.0]])           # 4 y 6 por origen
    reglas = np.array([[[1.0, 4.0], [1.0, 4.0]],           # regla 0: 2 y 8
                       [[3.0, 1.5], [3.0, 1.5]]])          # regla 1: 6 y 3
    v = m.ventaja_por_origen(modelo, reglas, real)
    # Por origen: la regla 0 en el primero (2) y la 1 en el segundo (3): (2 + 3) / 40 = 12,5; el modelo, 25
    comprobar(np.isclose(v["error_combinacion"][0], 12.5) and np.isclose(v["error_modelo"][0], 25.0) and
              np.isclose(v["ventaja"][0], -12.5),
              "6 · la ventaja se calcula con la regla que menos falla en cada origen")
    comprobar(not np.isclose(v["ventaja"][0], -2.5), "6 · no con la regla que menos falla en todos los orígenes")
    comprobar(v["regla_por_origen"][0].tolist() == [0, 1] and int(v["origenes_que_gana"][0]) == 0,
              "control: la regla de cada origen y los orígenes que gana el modelo")
    pesos = m.pesos_por_series(70, 1000, 42)
    comprobar(pesos.shape == (1000, 70) and m.remuestreo_por_entidad(pesos, 70),
              "control: 1.000 remuestreos de las 70 series enteras pasan")
    por_filas = m.pesos_por_series(70 * 130, 1000, 42)
    comprobar(not m.remuestreo_por_entidad(por_filas, 70), "5 · el intervalo remuestreando filas y no series sale "
                                                           "en rojo")
    comprobar(np.array_equal(pesos, m.pesos_por_series(70, 1000, 42)), "control: la misma semilla, los mismos "
                                                                       "remuestreos")
    comprobar(m.veredicto(10, 13, 0.1) == "gana" and m.veredicto(10, 13, -0.1) == "mejor de media pero no demostrado"
              and m.veredicto(9, 13, 0.1) == "no gana", "control: el veredicto con sus dos condiciones (10 de 13)")


# ── 8. Casos 7 y 8: el 25 de diciembre y los meses ─────────────────────────────
def casos_dias(m):
    """El 25 de diciembre sale del error; los meses parciales no se comparan."""
    t = pd.DataFrame({"date": pd.to_datetime(["2014-12-24", "2014-12-25", "2014-12-26"]),
                      "fuera_del_error": [False, True, False], "unidades": [3, 0, 4]})
    medidas = m.filas_medidas(t)
    comprobar(len(medidas) == 2 and m.sin_dias_fuera_del_error(medidas), "7 · el 25 de diciembre sale de lo medido")
    comprobar(not m.sin_dias_fuera_del_error(t), "7 · el 25 de diciembre dentro del error sale en rojo")
    meses = m.meses_completos(pd.date_range("2014-05-23", "2015-05-21", freq="D"))
    comprobar("2014-05" not in meses and "2015-05" not in meses and "2014-06" in meses and len(meses) == 11,
              "8 · mayo de 2014 y mayo de 2015 son parciales y no se comparan")
    tabla = pd.DataFrame({"date": pd.to_datetime(["2014-05-30", "2014-06-10", "2015-05-02"]),
                          "unidades": [10.0, 10.0, 10.0], "modelo": [8.0, 9.0, 1.0]})
    por_mes = m.errores_por_mes(tabla, "unidades", ["modelo"], meses)
    comprobar({e["grupo"] for e in por_mes} == {"2014-06"}, "8 · un mes parcial comparado sale de la tabla de meses")
    comprobar(not m.sin_meses_parciales([{"grupo": "2014-05"}], meses), "8 · un mes parcial en la tabla sale en rojo")


# ── 9. Caso 9: el suavizado ────────────────────────────────────────────────────
def casos_suavizado(m, series):
    """El suavizado solo usa la venta hasta el origen; un ajuste con días posteriores sale en rojo."""
    origen = FIN_CONSTRUCCION
    una = series[(series["store_id"] == "T_0") & (series["dept_id"] == "D_0")]
    hasta = una[una["date"] <= origen]
    con_futuro, registro = m.prever_suavizado(una, "unidades", origen, 10)
    solo_pasado, _ = m.prever_suavizado(hasta, "unidades", origen, 10)
    comprobar(np.allclose(con_futuro["suavizado"], solo_pasado["suavizado"]),
              "9 · el suavizado prevé igual con la historia cortada en el origen")
    comprobar(m.suavizado_sin_futuro(registro, origen) and registro[0]["primer_dia"] == pd.Timestamp(INICIO),
              "control: el registro del ajuste acaba en el origen y empieza en el primer día de la serie")
    malo = [dict(registro[0], ultimo_dia=origen + pd.Timedelta(1, "D"))]
    comprobar(not m.suavizado_sin_futuro(malo, origen), "9 · un suavizado ajustado con días después del origen sale "
                                                        "en rojo")
    comprobar((con_futuro["suavizado"] >= 0).all() and con_futuro["h"].tolist() == list(range(1, 11)),
              "control: el suavizado, acotado en cero, del día 1 al 10")


# ── 10. Caso 10 ────────────────────────────────────────────────────────────────
def casos_escritos(m):
    """Ninguna validación con su resultado puesto (error 24)."""
    escrito = 'v = {"reproducible": True, "validacion_una_vez": (False)}\nv["intervalo_por_entidad"] = True\n'
    comprobar(len(m.buscar_resultados_escritos(escrito)) == 3, "10 · una validación con su resultado puesto se "
                                                               "encuentra")
    comprobar(m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8")) == [],
              "10 · el script no escribe ninguna validación con su resultado puesto")
    comprobar("tests/cifras_de_referencia" not in SCRIPT.read_text(encoding="utf-8"),
              "control: el script no escribe en las cifras de referencia")


# ── 11. Casos 11 a 14: lo que matiza la ventaja ────────────────────────────────
def casos_robustez(m):
    """El aporte de cada serie, la ventaja sin tiendas, el intervalo por tienda, los eventos y los días de la semana."""
    # Dos series, dos orígenes, dos reglas, 10 vendidas por serie y origen. Origen 0: r0 (1) frente a r1 (8);
    # origen 1: r1 (2) frente a r0 (10). La combinación falla 3 y el modelo 7: ventaja 100 · (3 - 7) / 40 = -10
    real = np.full((2, 2), 10.0)
    sumas = {"real": real, "abs": {"modelo": np.array([[2.0, 3.0], [1.0, 1.0]]),
                                   "r0": np.array([[1.0, 4.0], [0.0, 6.0]]),
                                   "r1": np.array([[3.0, 1.5], [5.0, 0.5]])}}
    series = [("T_0", "D_0"), ("T_1", "D_0")]
    v = m.ventaja_por_origen(sumas["abs"]["modelo"], np.stack([sumas["abs"][r] for r in ("r0", "r1")]), real)
    rival = [["r0", "r1"][i] for i in v["regla_por_origen"][0]]
    ap = m.aporte_por_serie(sumas, ["r0", "r1"], rival, series)
    por_serie = {(x["store_id"], x["dept_id"]): x["aporte"] for x in ap["series"]}
    # Serie 0: (1 + 1,5 - 5) / 40 · 100 = -6,25; serie 1: (0 + 0,5 - 2) / 40 · 100 = -3,75
    comprobar(np.isclose(por_serie[("T_0", "D_0")], -6.25) and np.isclose(por_serie[("T_1", "D_0")], -3.75),
              "11 · el aporte de cada serie usa la regla de cada origen (rival_por_origen)")
    comprobar(not np.isclose(por_serie[("T_0", "D_0")], -1.25),
              "11 · no la regla que menos falla en la serie con todos los orígenes juntos")
    comprobar(np.isclose(ap["suma_de_todas"], v["ventaja"][0]) and np.isclose(ap["suma_de_todas"], -10.0)
              and m.aporte_suma_la_ventaja(ap["series"], -10.0), "control: el aporte de las series suma la ventaja")
    tocado = [dict(x, aporte=x["aporte"] + 0.5) for x in ap["series"]]
    comprobar(not m.aporte_suma_la_ventaja(tocado, -10.0), "11 · un aporte de las series que no suma la ventaja "
                                                          "sale en rojo")
    comprobar([(x["store_id"], x["dept_id"]) for x in ap["series"]] == [("T_1", "D_0"), ("T_0", "D_0")],
              "control: las series, de la que más aporta a la que menos")

    # Un origen y tres series: con todas, la regla A (6 frente a 8); sin la tienda T_1, la B (2 frente a 6)
    sumas3 = {"real": np.full((3, 1), 10.0), "abs": {"modelo": np.full((3, 1), 2.0),
                                                     "A": np.array([[3.0], [3.0], [0.0]]),
                                                     "B": np.array([[1.0], [1.0], [6.0]])}}
    series3 = [("T_0", "D_0"), ("T_0", "D_1"), ("T_1", "D_0")]
    sin = m.ventaja_sin_tiendas(sumas3, ["A", "B"], series3, ["T_1"])
    comprobar(sin["series"] == 2 and np.isclose(sin["ventaja"], -10.0),
              "12 · la ventaja sin una tienda elige otra vez la regla en lo que queda")
    comprobar(not np.isclose(sin["ventaja"], 10.0), "12 · no con la regla elegida con todas las tiendas")
    nada = m.ventaja_sin_tiendas(sumas3, ["A", "B"], series3, ["WI_2"])
    vacio = m.ventaja_sin_tiendas(sumas3, ["A", "B"], series3, ["T_0", "T_1"])
    comprobar(nada["ventaja"] is None and nada.get("motivo") and vacio["ventaja"] is None and vacio.get("motivo"),
              "control: una tienda que no está o quitarlas todas da null con su motivo")

    # El intervalo por tienda: cada remuestreo sortea tiendas enteras, con todas sus series
    series4 = [("T_0", "D_0"), ("T_0", "D_1"), ("T_1", "D_0"), ("T_1", "D_1")]
    pesos, tienda_de_serie = m.pesos_por_tienda(series4, 1000, 42)
    comprobar(pesos.shape == (1000, 4) and m.remuestreo_por_tienda(pesos, tienda_de_serie),
              "control: 1.000 remuestreos de las tiendas enteras pasan")
    comprobar(not m.remuestreo_por_tienda(m.pesos_por_series(4, 1000, 42), tienda_de_serie),
              "13 · el intervalo por tienda que remuestrea series sale en rojo")
    sumas4 = {"real": np.full((4, 2), 10.0), "abs": {"modelo": np.full((4, 2), 2.0),
                                                     "A": np.full((4, 2), 3.0), "B": np.full((4, 2), 4.0)}}
    it = m.intervalo_por_tienda(sumas4, ["A", "B"], series4)
    comprobar(it["unidad"] == "tienda" and it["unidades"] == 2 and np.isclose(it["bajo"], 10.0)
              and np.isclose(it["alto"], 10.0) and it["semilla"] == 42 and it["remuestreos"] == 1000,
              "control: el intervalo por tienda, con 2 tiendas, semilla 42 y 1.000 remuestreos")

    # Los eventos: uno en un día medido, uno en un 25 de diciembre fuera del error, uno sin prever, dos el mismo día
    cal = pd.DataFrame({"date": pd.to_datetime(["2014-05-20", "2014-06-01", "2014-12-25", "2015-02-01",
                                                "2014-06-15"]).astype("datetime64[us]"),
                        "event_name_1": ["Antes", "Medido", "Christmas", "SinPrever", "Doble1"],
                        "event_name_2": [None, None, None, None, "Doble2"]})
    eventos = m.eventos_del_periodo(cal, pd.Timestamp("2014-05-23"), pd.Timestamp("2015-05-22"))
    comprobar(len(eventos) == 5 and "Antes" not in set(eventos["nombre"]),
              "control: los eventos del periodo, con los dos campos, sin los de antes")
    previsto = pd.DataFrame({"date": pd.to_datetime(["2014-06-01", "2014-06-01", "2014-12-25", "2014-06-15"]),
                             "fuera_del_error": [False, False, True, False]})
    medidas = m.filas_medidas(previsto)
    ev = m.eventos_cubiertos(eventos, previsto, medidas)
    motivos = {x["nombre"]: x["motivo"] for x in ev["sin_cubrir"]}
    filas = {x["nombre"]: x["filas_medidas"] for x in ev["por_evento"]}
    comprobar(ev["cuantos"] == 5 and ev["cubiertos"] == 3 and filas == {"Medido": 2, "Christmas": 0, "SinPrever": 0,
                                                                         "Doble1": 1, "Doble2": 1},
              "14 · solo cuentan como cubiertos los eventos de días medidos, con sus filas")
    comprobar(motivos.get("Christmas") == "fuera del error" and motivos.get("SinPrever") == "fuera del horizonte",
              "14 · un evento en un día fuera del error o fuera del horizonte no cuenta como cubierto")

    # Las filas de cada día de la semana, de lunes a domingo
    dias = m.filas_por_dia_de_la_semana(pd.DataFrame({"date": pd.to_datetime(
        ["2014-06-02", "2014-06-06", "2014-06-06", "2014-06-08"])}))
    comprobar([(x["dia"], x["filas"]) for x in dias["dias"]] == [
        ("lunes", 1), ("martes", 0), ("miércoles", 0), ("jueves", 0), ("viernes", 2), ("sábado", 0), ("domingo", 1)]
              and dias["total"] == 4, "control: las filas de cada día de la semana, de lunes a domingo")


# ── 12. Casos 15 a 19: la previsión sumada por niveles ─────────────────────────
def filas_de_niveles(valores, origenes=None, fechas=None):
    """Filas medidas pequeñas: una por (tienda, departamento, unidades, modelo); todas las reglas y el suavizado
    iguales a la venta real salvo que se diga. Cada fila en su origen y su día."""
    n = len(valores)
    origenes = origenes or ["2014-05-22"] * n
    fechas = fechas or ["2014-05-23"] * n
    t = pd.DataFrame({"origen": pd.to_datetime(origenes), "date": pd.to_datetime(fechas),
                      "store_id": [v[0] for v in valores], "dept_id": [v[1] for v in valores],
                      "unidades": [float(v[2]) for v in valores], "modelo": [float(v[3]) for v in valores]})
    for p in ("repetir_semana_anterior", "media_28_dias", "media_mismo_dia_4_semanas", "suavizado"):
        t[p] = t["unidades"]
    return t


def casos_niveles(m):
    """La previsión sumada: un padre por hijo, redondear cada serie antes de sumar, el error de las filas sumadas, cada
    origen por su lado y la cadena igual a las series sumadas."""
    productos = pd.DataFrame({"item_id": ["I_1", "I_2", "I_3"], "dept_id": ["D_0", "D_0", "D_1"],
                              "cat_id": ["CAT_A", "CAT_A", "CAT_B"]})
    tiendas = pd.DataFrame({"store_id": ["T_0", "T_1"], "state_id": ["ST_A", "ST_A"]})
    series = [("T_0", "D_0"), ("T_0", "D_1"), ("T_1", "D_0"), ("T_1", "D_1")]
    padres = m.padres_de_las_series(productos, tiendas, series)
    comprobar(padres == {"categoria": {"D_0": "CAT_A", "D_1": "CAT_B"}, "estado": {"T_0": "ST_A", "T_1": "ST_A"}}
              and m.un_padre_por_hijo(productos, tiendas),
              "control: cada departamento con su categoría y cada tienda con su estado")
    dos_categorias = pd.concat([productos, pd.DataFrame({"item_id": ["I_4"], "dept_id": ["D_1"], "cat_id": ["CAT_C"]})])
    dos_estados = pd.concat([tiendas, pd.DataFrame({"store_id": ["T_1"], "state_id": ["ST_B"]})])
    for nombre, (p, t) in (("un departamento con dos categorías", (dos_categorias, tiendas)),
                           ("una tienda con dos estados", (productos, dos_estados))):
        try:
            m.padres_de_las_series(p, t, series)
            para = False
        except ValueError:
            para = True
        comprobar(para and not m.un_padre_por_hijo(p, t), f"15 · {nombre} para y sale en rojo")
    try:
        m.padres_de_las_series(productos, tiendas, series + [("T_9", "D_0")])
        comprobar(False, "15 · una serie sin estado para")
    except ValueError:
        comprobar(True, "15 · una serie sin estado para")

    # 16: tres series de la misma categoría con 0,4 unidades previstas cada una: cada serie se redondea a 0 antes de
    # sumar, así que la categoría prevé 0; sumando antes, 1,2 o 1
    t = filas_de_niveles([("T_0", "D_0", 1, 0.4), ("T_1", "D_0", 1, 0.4)])
    sumas = m.sumar_por_grupo(t, "unidades", "categoria", padres)
    comprobar(len(sumas) == 1 and float(sumas["modelo"].iloc[0]) == 0.0 and int(sumas["series"].iloc[0]) == 2,
              "16 · las unidades de cada serie se redondean antes de sumar (0 + 0, no 0,8 ni 1)")
    t2 = filas_de_niveles([("T_0", "D_0", 1, 0.6), ("T_1", "D_0", 1, 0.6)])
    comprobar(float(m.sumar_por_grupo(t2, "unidades", "categoria", padres)["modelo"].iloc[0]) == 2.0,
              "16 · con 0,6 cada serie redondea a 1 y la suma es 2, no 1,2")
    dolares = t2.rename(columns={"unidades": "dolares"})
    comprobar(np.isclose(float(m.sumar_por_grupo(dolares, "dolares", "categoria", padres)["modelo"].iloc[0]), 1.2),
              "control: en dólares no se redondea")

    # 17: el error del grupo sale de las filas sumadas: 100 y 10 vendidas, 90 y 15 previstas; 5 de 110 = 4,55, no la
    # media de 10 y 50 ni la suma de errores sin sumar antes (15 de 110 = 13,6)
    t = filas_de_niveles([("T_0", "D_0", 100, 90), ("T_1", "D_0", 10, 15)])
    grupos = m.errores_del_nivel(m.sumar_por_grupo(t, "unidades", "estado", padres), "unidades")
    modelo = next(e for e in grupos[0]["errores"] if e["prevision"] == "modelo")
    comprobar(len(grupos) == 1 and np.isclose(modelo["error"], 100 * 5 / 110) and np.isclose(modelo["sesgo"],
                                                                                              -100 * 5 / 110),
              "17 · el error del grupo es el de las filas sumadas (4,55)")
    comprobar(not np.isclose(modelo["error"], 30.0) and not np.isclose(modelo["error"], 100 * 15 / 110),
              "17 · no la media de los errores de sus series (30) ni sus errores sin sumar (13,6)")
    comprobar(grupos[0]["regla_que_menos_falla"] == "media_28_dias" and grupos[0]["modelo_falla_menos"] is False
              and str(grupos[0]["filas"]).startswith("validacion"),
              "control: la regla que menos falla (empate a cero, por su nombre) y si el modelo falla menos que ella")

    # 18: dos orígenes que prevén el mismo día: cada uno suma por su lado; mezclados, el 24/05 sumaría los dos
    t = filas_de_niveles([("T_0", "D_0", 10, 12), ("T_0", "D_0", 10, 11), ("T_0", "D_0", 10, 30),
                          ("T_0", "D_0", 10, 9)],
                         origenes=["2014-05-22", "2014-05-22", "2014-05-23", "2014-05-23"],
                         fechas=["2014-05-23", "2014-05-24", "2014-05-24", "2014-05-25"])
    sumas = m.sumar_por_grupo(t, "unidades", "cadena", padres)
    dia = sumas[sumas["date"] == pd.Timestamp("2014-05-24")].sort_values("origen")
    comprobar(len(sumas) == 4 and dia["modelo"].tolist() == [11.0, 30.0] and dia["unidades"].tolist() == [10.0, 10.0],
              "18 · cada origen suma sus días por su lado: el 24/05 no mezcla los dos orígenes")
    cad = m.origenes_de_la_cadena(sumas, "unidades")
    comprobar(cad["de"] == 2 and cad["origenes_que_gana"] == 0 and len(cad["por_origen"]) == 2,
              "control: los orígenes de la cadena, uno por origen")

    # 19: la cadena tiene que dar el error de todas las series sumadas
    t = filas_de_niveles([("T_0", "D_0", 100, 90), ("T_1", "D_0", 10, 15), ("T_0", "D_1", 50, 52),
                          ("T_1", "D_1", 40, 30)])
    bloque = m.previsiones_sumadas(t, "unidades", padres)
    cadena = bloque["cadena"]["grupos"][0]
    comprobar(m.cadena_cuadra(cadena, t, "unidades") and np.isclose(cadena["error_modelo"], 100 * 13 / 200),
              "control: la cadena da el error de las cuatro series sumadas (13 de 200, 6,5)")
    media = dict(cadena, error_modelo=float(np.mean([10, 50, 4, 25])))
    comprobar(not m.cadena_cuadra(media, t, "unidades"), "19 · una cadena con la media de los errores sale en rojo")
    sin_una = m.errores_del_nivel(m.sumar_por_grupo(t.iloc[:3], "unidades", "cadena", padres), "unidades")[0]
    comprobar(not m.cadena_cuadra(sin_una, t, "unidades"), "19 · una cadena a la que le falta una serie sale en rojo")
    comprobar([len(bloque[n]["grupos"]) for n in ("cadena", "estado", "tienda", "categoria")] == [1, 1, 2, 2]
              and all(x is True for x in bloque["comprobaciones"].values()) and len(bloque["comprobaciones"]) >= 4
              and bloque["cadena"]["origenes"]["de"] == 1,
              "control: el bloque con sus cuatro niveles y sus comprobaciones en verde")
    malo = t.copy()
    malo.loc[3, "origen"] = pd.Timestamp("2014-05-21")
    comprobar(not m.grupos_completos(m.sumar_por_grupo(malo, "unidades", "cadena", padres), malo, "cadena", padres),
              "18 · un grupo con un día al que le faltan series de su origen sale en rojo")


# ── 13. El script entero ───────────────────────────────────────────────────────
def casos_script(m, pp, series, modelo):
    """El control que no debe disparar y la parada con la receta rota sin abrir la validación."""
    raiz = TMP / "base"
    sha = montar(raiz, series, modelo, pp, m)
    antes = {p.name: huella(p) for p in (raiz / "data" / "processed").glob("*.parquet")}
    codigo, d, salida = ejecutar(raiz, sha)
    falsas = [k for k, x in (d or {}).get("validaciones", {}).items() if x is False]
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "PARADO" and d.get("puerta_de_juan"),
              f"control: el script entero para en la puerta del responsable del caso ({salida[-2500:] if codigo else ''} {falsas})")
    if d is None or codigo != 0:
        return
    comprobar({p.name: huella(p) for p in (raiz / "data" / "processed").glob("*.parquet")
               if p.name in antes} == antes, "control: las tablas de entrada no cambian")
    comprobar(all(v is True for v in d["validaciones"].values() if v is not None) and
              sum(v is True for v in d["validaciones"].values()) >= 15, "control: las validaciones, en verde")
    comprobar(d["fecha_datos"] == "2015-05-22" and all(k in d["entorno"] for k in (
        "python", "pandas", "numpy", "pyarrow", "scikit-learn", "statsmodels")), "control: fecha_datos y las versiones")
    comprobar(d["receta"]["huella"]["calculada"] == sha and d["receta"]["huella"]["esperada"] == sha,
              "control: la huella de la receta, comprobada y escrita")
    comprobar([x["paso"] for x in d["tablas_abiertas"]][0] == "receta",
              "1 · la receta se lee antes de cargar ninguna validación")
    for objetivo, h in (("unidades", 10), ("dolares", 28)):
        g = d["receta"]["ganador"][objetivo]
        comprobar(g["aprobado_por"].startswith("el responsable del caso, 25/11/2026"), f"control: aprobado_por del ganador de {objetivo}")
        val = d["validacion"][objetivo]
        comprobar(len(val["origenes"]) == 13 and val["dias_previstos_por_serie"] == 13 * h,
                  f"control: 13 orígenes y {13 * h} días previstos por serie en {objetivo}")
        comprobar(val["veredicto"]["veredicto"] in ("gana", "mejor de media pero no demostrado", "no gana") and
                  val["veredicto"]["intervalo"]["unidad"] == "serie" and
                  val["veredicto"]["intervalo"]["unidades"] == 4, f"control: el veredicto de {objetivo}, por series")
        comprobar(all(e["filas"].startswith("validacion") for e in val["errores"]["por_mes"]) and
                  {e["grupo"] for e in val["errores"]["por_mes"]} <= set(val["meses_completos"]),
                  f"8 · solo meses completos en {objetivo}")
        comprobar(len(val["recomendacion_por_departamento"]) == 2, f"control: una recomendación por departamento en "
                                                                     f"{objetivo}")
        rob = val.get("robustez") or {}
        ap = rob.get("aporte_por_serie") or {}
        comprobar(rob and np.isclose(ap.get("suma_de_todas", np.nan), val["veredicto"]["ventaja"])
                  and len(ap.get("series", [])) == 4 and len(ap.get("cinco_primeras", [])) == 4
                  and all(x is True for x in rob.get("comprobaciones", {}).values())
                  and len(rob.get("comprobaciones", {})) >= 4,
                  f"11 · el bloque robustez de {objetivo}: el aporte de las series suma la ventaja")
        if not rob:
            continue
        tiendas = {tuple(x["quitar"]): x for x in rob["ventaja_sin"]["cada_tienda"]}
        comprobar(set(tiendas) == {("T_0",), ("T_1",)} and all(x["ventaja"] is not None for x in tiendas.values())
                  and rob["ventaja_sin"]["juntas"]["ventaja"] is None,
                  f"12 · la ventaja sin cada tienda de {objetivo}; WI_2 y WI_3, que no están, con null")
        comprobar(rob["intervalo_por_tienda"]["unidad"] == "tienda" and rob["intervalo_por_tienda"]["unidades"] == 2
                  and rob["intervalo_por_tienda"]["bajo"] <= rob["intervalo_por_tienda"]["alto"],
                  f"13 · el intervalo de {objetivo}, por tiendas enteras")
        ev, dias = rob["eventos"], rob["filas_por_dia_de_la_semana"]
        comprobar(ev["cuantos"] == ev["cubiertos"] + len(ev["sin_cubrir"]) and ev["desde"] == "2014-05-23"
                  and ev["hasta"] == "2015-05-22" and dias["total"] == val["filas_medidas"],
                  f"14 · los eventos y los días de la semana de {objetivo}, con las filas medidas")
        comprobar(all(isinstance(x.get("que_es"), str) and str(x.get("filas", "")).startswith("validacion")
                      for x in (ap, rob["intervalo_por_tienda"], rob["series_con_alguna_regla_mejor"], ev, dias)),
                  f"control: cada cifra de robustez de {objetivo} dice qué es y sobre qué filas")
        # La previsión sumada: 13 orígenes por el horizonte, sin el 25 de diciembre (todas las series a la vez)
        niv = val.get("niveles") or {}
        dias_grupo = 13 * h - len(val["dias_fuera_del_error"])
        cuantos = {n: len((niv.get(n) or {}).get("grupos", [])) for n in ("cadena", "estado", "tienda", "categoria")}
        comprobar(cuantos == {"cadena": 1, "estado": 2, "tienda": 2, "categoria": 2}
                  and all(g["filas_sumadas"] == dias_grupo for n in cuantos for g in niv[n]["grupos"])
                  and all(x is True for x in niv.get("comprobaciones", {}).values())
                  and len(niv.get("comprobaciones", {})) >= 4,
                  f"15 a 19 · el bloque niveles de {objetivo}: 1, 2, 2 y 2 grupos con {dias_grupo} filas sumadas cada uno")
        if not niv:
            continue
        cadena = niv["cadena"]["grupos"][0]
        comprobar(cadena["series"] == 4 and niv["cadena"]["origenes"]["de"] == 13
                  and 0 <= niv["cadena"]["origenes"]["origenes_que_gana"] <= 13
                  and all(str(g["filas"]).startswith("validacion") and all(str(e["filas"]).startswith("validacion")
                                                                          for e in g["errores"])
                          for n in cuantos for g in niv[n]["grupos"]),
                  f"control: la cadena de {objetivo} suma las 4 series y cada cifra dice sobre qué filas")
    previsiones = pd.read_parquet(raiz / "data" / "processed" / "previsiones_validacion.parquet")
    comprobar(len(previsiones) == 4 * 13 * (10 + 28) and {
        "objetivo", "origen", "store_id", "dept_id", "date", "h", "real", "modelo", "repetir_semana_anterior",
        "media_28_dias", "media_mismo_dia_4_semanas", "suavizado"} <= set(previsiones.columns),
              "control: una fila por objetivo, origen, serie y día previsto")
    dolares = previsiones[previsiones["objetivo"] == "dolares"]
    comprobar(dolares.groupby(["store_id", "dept_id"])["date"].nunique().eq(364).all() and
              not dolares.duplicated(["store_id", "dept_id", "date"]).any(),
              "control: en dólares, cada día de la validación una vez, 364 por serie")
    por_origen = pd.read_csv(raiz / "informes" / "validacion_por_origen.csv")
    comprobar(len(por_origen) == 2 * 13 * 6 and {"objetivo", "origen", "prevision", "error", "sesgo"} <=
              set(por_origen.columns), "control: la tabla por origen, seis previsiones en cada uno")
    texto = (raiz / "informes" / "validacion_resultado.md").read_text(encoding="utf-8")
    comprobar("el responsable del caso" in texto and ", y " not in texto and "Límites" in texto, "control: el resultado para el responsable del caso, "
                                                                                 "sin «, y»")
    comprobar("## Lo que matiza la ventaja" in texto, "control: el resultado trae «Lo que matiza la ventaja»")
    comprobar("## La previsión sumada" in texto, "control: el resultado trae «La previsión sumada»")
    comprobar(any(x["ruta"] == "data/processed/dim_producto.parquet" for x in d["entradas"])
              and any(x["ruta"] == "data/processed/dim_tienda.parquet" for x in d["entradas"]),
              "control: las dos dimensiones, entre las entradas con su huella")

    # La receta rota: para sin abrir la validación (que es un texto y rompería el Parquet)
    raiz = TMP / "rota"
    sha = montar(raiz, series, modelo, pp, m, receta_rota=True)
    codigo, d, salida = ejecutar(raiz, sha)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO" and
              not any(x["paso"] == "validacion" for x in d["tablas_abiertas"]),
              f"1 · con la receta sin ganador para sin abrir la validación ({salida[-800:]})")
    # Otra huella de receta: para antes de abrir nada
    codigo, d, _ = ejecutar(TMP / "base", "0" * 64)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO" and
              "huella" in d["resultado"]["resumen"], "control: con otra huella de la receta no empieza")


# ── 12. Ejecución ──────────────────────────────────────────────────────────────
def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/16_validacion.py")
        else:
            sys.path.insert(0, str(SCRIPTS))
            vp = cargar(SCRIPTS / "variables_prevision.py", "variables_prevision")
            pp = cargar(SCRIPTS / "preparacion_prevision.py", "preparacion_prevision")
            pr = cargar(SCRIPTS / "prevision_recursiva.py", "prevision_recursiva")
            m = cargar(SCRIPT, "validacion_16")
            series, modelo = tablas(vp)
            casos_orden(m)
            casos_recursivo(m, pr, modelo)
            casos_origenes(m)
            casos_mismas_filas(m)
            casos_ventaja(m)
            casos_dias(m)
            casos_suavizado(m, series)
            casos_escritos(m)
            try:
                casos_robustez(m)
            except AttributeError as e:
                comprobar(False, f"11 a 14 · el script tiene las funciones de robustez ({e})")
            try:
                casos_niveles(m)
            except AttributeError as e:
                comprobar(False, f"15 a 19 · el script tiene las funciones de la previsión sumada ({e})")
            casos_script(m, pp, series, modelo)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
