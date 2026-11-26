"""Prueba de scripts/12_preparacion.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_preparacion/ una carpeta con la estructura
del caso (data/processed/hechos_modelo_*.parquet e informes/variables_modelo.json), ejecuta el script sobre ella con
--raiz y la borra al acabar. Importa solo el script que prueba, que tiene su trabajo bajo __main__.

Los casos:
  0. control que no debe disparar: el script entero sobre tablas limpias deja preparacion.json en OK, con las nueve
     validaciones en verde en los dos objetivos; el preprocesador sale sin ajustar de su función; el de unidades no
     lleva ninguna variable de dólares ni al revés; un evento de event_name_2 que el entrenamiento no tiene en esa
     columna sale con sus columnas a cero sin avisar;
  1 a 9. cada una de las nueve validaciones del §5, con un caso que tiene que salir en rojo;
  10. al empezar: variables_modelo.json en PARADO o con otra huella, el script para;
  11. el script no escribe ninguna validación con su resultado puesto (error 24);
  12. el preprocesador vive en scripts/preparacion_prevision.py: el módulo se importa sin ejecutar nada, el script lo
      importa sin guardar una copia y da el mismo preprocesador.
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
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, StandardScaler

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "12_preparacion.py"
TMP = RAIZ / "tests" / "tmp_preparacion"
FALLOS = []
EVENTOS = [f"Evento {i:02d}" for i in range(29)] + ["Father's day"]
EVENTOS_2 = ["Evento 03", "Evento 07", "Evento 11"]
RETARDOS = (1, 2, 3, 4, 5, 6, 7, 14, 21, 28)


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


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("preparacion_12", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["preparacion_12"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Datos pequeños ──────────────────────────────────────────────────────────
def tabla(filas, inicio, semilla, validacion=False):
    """Una tabla con las columnas de hechos_modelo: 10 tiendas, 7 departamentos, los 7 días y los 12 meses."""
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range(inicio, periods=filas, freq="D").astype("datetime64[us]")
    t = pd.DataFrame({"store_id": [f"T_{i % 10}" for i in range(filas)],
                      "dept_id": [f"D_{i % 7}" for i in range(filas)], "date": fechas,
                      "weekday": fechas.day_name(), "month": fechas.month.astype("int64"),
                      "snap": rng.integers(0, 2, filas), "dia_del_mes": fechas.day.astype("int64"),
                      "precio_medio_semana_anterior": rng.uniform(1, 9, filas),
                      "productos_con_precio_semana_anterior": rng.integers(3, 120, filas),
                      "unidades": rng.integers(0, 900, filas), "dolares": rng.uniform(0, 3000, filas)})
    t["weekday"] = t["weekday"].astype("str")
    ev1 = [None] * filas
    ev2 = [None] * filas
    if not validacion:
        # Cada evento con más de 30 filas, el mínimo para no agrupar una categoría (parametros.md)
        for i in range(0, filas, 2):
            ev1[i] = EVENTOS[(i // 2) % len(EVENTOS)]
        for i in range(1, filas, 10):
            ev2[i] = EVENTOS_2[(i // 10) % len(EVENTOS_2)]
    else:
        ev1[3] = "Evento 05"
        ev2[8] = "Father's day"   # en el entrenamiento solo está en event_name_1
    t["event_name_1"] = pd.Series(ev1, dtype="str")
    t["event_name_2"] = pd.Series(ev2, dtype="str")
    for e in EVENTOS:
        t[f"evento_{e}"] = ((t["event_name_1"] == e).fillna(False) | (t["event_name_2"] == e).fillna(False)).astype("int64")
    for o in ("unidades", "dolares"):
        for k in RETARDOS:
            t[f"{o}_lag_{k}"] = rng.uniform(0, 1000, filas)
        for w in (7, 28):
            t[f"{o}_media_{w}"] = rng.uniform(0, 1000, filas)
    return t


def montar(raiz, ent, val, estado="OK", huella_falsa=False):
    """Escribe la carpeta del caso de la prueba con las dos tablas y el JSON del paso anterior."""
    if raiz.exists():
        shutil.rmtree(raiz)
    (raiz / "data" / "processed").mkdir(parents=True)
    (raiz / "informes").mkdir()
    pr = raiz / "data" / "processed"
    ent.to_parquet(pr / "hechos_modelo_entrenamiento.parquet", index=False)
    val.to_parquet(pr / "hechos_modelo_validacion.parquet", index=False)
    salidas = [{"ruta": "data/processed/hechos_modelo_entrenamiento.parquet",
                "sha256": "0" * 64 if huella_falsa else huella(pr / "hechos_modelo_entrenamiento.parquet")},
               {"ruta": "data/processed/hechos_modelo_validacion.parquet",
                "sha256": huella(pr / "hechos_modelo_validacion.parquet")}]
    previo = {"fecha_datos": "2015-05-22", "resultado": {"estado": estado}, "salidas": salidas,
              "eventos": {"lista": EVENTOS, "columnas": [f"evento_{e}" for e in EVENTOS]}}
    (raiz / "informes" / "variables_modelo.json").write_text(json.dumps(previo), encoding="utf-8")


def ejecutar(raiz):
    """Ejecuta el script con -W error; devuelve código, JSON y salida."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)],
                          capture_output=True, text=True, encoding="utf-8", env=entorno)
    ruta = raiz / "informes" / "preparacion.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


# ── 3. Control que no debe disparar ────────────────────────────────────────────
def caso_base(m, ent, val):
    """El script entero sobre tablas limpias y el preprocesador recién construido."""
    columnas_evento = [f"evento_{e}" for e in EVENTOS]
    pipe = m.construir_preprocesador("unidades", columnas_evento)
    comprobar(isinstance(pipe, Pipeline) and not hasattr(pipe.named_steps["preparacion"], "transformers_"),
              "0 · el preprocesador sale de su función dentro de un Pipeline y sin ajustar")
    ct = pipe.named_steps["preparacion"]
    comprobar(ct.remainder == "drop", "0 · remainder drop")
    entrada_u = m.columnas_entrada("unidades", columnas_evento)
    entrada_d = m.columnas_entrada("dolares", columnas_evento)
    comprobar(not any(c.startswith("dolares") for c in entrada_u) and not any(c.startswith("unidades") for c in entrada_d)
              and len(entrada_u) == len(entrada_d) == 4 + 2 + 1 + 30 + 3 + 12,
              "0 · cada modelo usa las variables de su objetivo y comparte las demás")

    raiz = TMP / "base"
    montar(raiz, ent, val)
    huellas = {p.name: huella(p) for p in (raiz / "data" / "processed").glob("*.parquet")}
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "OK",
              f"0 · base: estado OK ({salida[-800:] if codigo else ''})")
    if d is None or codigo != 0:
        return
    comprobar(all(huella(raiz / "data" / "processed" / n) == h for n, h in huellas.items()),
              "0 · base: las tablas de entrada no cambian")
    for objetivo in ("unidades", "dolares"):
        val_o = d["preprocesadores"][objetivo]["validaciones"]
        comprobar(len(val_o) == 9 and all(val_o.values()), f"0 · base: nueve validaciones en verde en {objetivo}")
        salidas = d["preprocesadores"][objetivo]["columnas_salida"]
        comprobar(len(salidas) == 10 + 7 + 7 + 12 + 31 + 4 + 1 + 30 + 3 + 12,
                  f"0 · base: 117 columnas de salida en {objetivo}")
    comprobar(all(d["validaciones"].values()) and len(d["validaciones"]) == 9, "0 · base: las nueve, juntas")
    comprobar(d["fecha_datos"] == "2015-05-22" and "pyarrow" in d["entorno"] and "scikit-learn" in d["entorno"],
              "0 · base: fecha_datos y versiones")
    comprobar(d["matriz"]["aprobada_por"] == "el responsable del caso" and d["desequilibrio"] is None,
              "0 · base: matriz aprobada y sin desequilibrio (objetivo continuo)")
    comprobar(d["preprocesadores"]["unidades"]["ajustado_con_filas"] == len(ent),
              "0 · base: el preprocesador se ajusta solo con las filas de entrenamiento")
    fd = d["preprocesadores"]["unidades"]["comprobacion_evento_nuevo"]
    comprobar(fd["filas"] == 1 and fd["todas_a_cero"], "0 · base: Father's day en event_name_2 sale a cero sin avisar")


# ── 4. Las nueve validaciones, en rojo ─────────────────────────────────────────
def casos_rojos(m, ent, val):
    """Cada validación con un caso que tiene que fallar."""
    columnas_evento = [f"evento_{e}" for e in EVENTOS]
    pipe = m.construir_preprocesador("unidades", columnas_evento).fit(ent)
    ct = pipe.named_steps["preparacion"]
    s_tr, s_va = pipe.transform(ent), pipe.transform(val)
    esperadas = m.columnas_esperadas(ent, "unidades", columnas_evento)
    ok = m.validaciones(ct, ent, s_tr, val, s_va, esperadas, m.ALGORITMOS)
    comprobar(all(v[0] for v in ok.values()), "control: las nueve en verde con el preprocesador bueno")

    # 1 · filas
    comprobar(not m.v_filas(ent, s_tr.iloc[1:], val, s_va)[0], "1 · una fila perdida sale en rojo")
    # 2 · objetivo entre las salidas
    malo = ColumnTransformer([("ss", StandardScaler(), ["unidades", "precio_medio_semana_anterior"])],
                             remainder="drop", verbose_feature_names_out=m.nombre_salida).set_output(transform="pandas")
    malo.fit(ent)
    comprobar(not m.v_sin_objetivo(malo, malo.transform(ent))[0], "2 · el objetivo entre las salidas sale en rojo")
    # 3 · columnas intermedias u originales
    comprobar(not m.v_sin_intermedias(ct, s_tr.assign(store_id=1))[0], "3 · la original de una codificada sale en rojo")
    comprobar(not m.v_sin_intermedias(ct, s_tr.assign(**{"ohe__store_id_ohe_T_0": 1}))[0],
              "3 · una columna con el prefijo de un paso intermedio sale en rojo")
    # 4 · vacíos
    con_vacio = s_va.copy()
    con_vacio.iloc[0, 0] = np.nan
    comprobar(not m.v_sin_vacios(s_tr, con_vacio)[0], "4 · un vacío en la salida de validación sale en rojo")
    # 5 · nombres únicos
    repetida = pd.concat([s_tr, s_tr[["snap"]]], axis=1)
    comprobar(not m.v_nombres_unicos(repetida)[0], "5 · un nombre repetido sale en rojo")
    # 6 · redundancia: un algoritmo que no admite las k columnas, o un drop distinto del de la matriz
    comprobar(not m.v_sin_redundancia(ct, s_tr, ["Ridge", "LinearRegression"])[0],
              "6 · las k columnas con una lineal sin regularizar salen en rojo")
    con_drop = m.construir_preprocesador("unidades", columnas_evento)
    con_drop.named_steps["preparacion"].transformers[0][1].set_params(drop="first")
    con_drop.fit(ent)
    comprobar(not m.v_sin_redundancia(con_drop.named_steps["preparacion"], con_drop.transform(ent), m.ALGORITMOS)[0],
              "6 · un drop que la matriz no dice sale en rojo")
    # 7 · columnas esperadas
    comprobar(not m.v_columnas_esperadas(s_tr.drop(columns=["snap"]), esperadas, ent)[0],
              "7 · una columna que falta sale en rojo")
    nueve = ent[ent["store_id"] != "T_9"]
    comprobar(not m.v_columnas_esperadas(s_tr, m.columnas_esperadas(nueve, "unidades", columnas_evento), nueve)[0],
              "7 · nueve tiendas cuando la matriz dice diez sale en rojo")
    # 8 · el relleno choca con un valor que ya existe
    con_relleno = ent.copy()
    con_relleno.loc[con_relleno.index[1], "event_name_1"] = m.RELLENO_EVENTO
    comprobar(not m.v_relleno_sin_choque(con_relleno)[0], "8 · «sin evento» ya presente en entrenamiento sale en rojo")
    # 9 · escalado
    comprobar(not m.v_escalado_segun_matriz(ct, s_tr.assign(snap=s_tr["snap"] * 2), s_va)[0],
              "9 · una columna de 0 y 1 que sale con un 2 sale en rojo")
    otro = Pipeline([("preparacion", ColumnTransformer(
        [("ss", StandardScaler(), m.nombres_rs("unidades"))], remainder="drop",
        verbose_feature_names_out=m.nombre_salida).set_output(transform="pandas"))]).fit(ent)
    comprobar(not m.v_escalado_segun_matriz(otro.named_steps["preparacion"], otro.transform(ent), otro.transform(val))[0],
              "9 · los retardos con StandardScaler en vez de RobustScaler salen en rojo")
    mm = Pipeline([("preparacion", ColumnTransformer(
        [("ss", MinMaxScaler(), ["precio_medio_semana_anterior"])], remainder="drop",
        verbose_feature_names_out=m.nombre_salida).set_output(transform="pandas"))]).fit(ent)
    comprobar(not m.v_escalado_segun_matriz(mm.named_steps["preparacion"], mm.transform(ent), mm.transform(val))[0],
              "9 · un MinMaxScaler sin clip sale en rojo")
    disperso = ColumnTransformer([("ohe", OneHotEncoder(), ["store_id"])], remainder="drop")
    disperso.fit(ent)
    comprobar(not m.v_escalado_segun_matriz(disperso, s_tr, s_va)[0], "9 · una codificación con salida dispersa sale en rojo")


# ── 5. Al empezar y error 24 ───────────────────────────────────────────────────
def casos_al_empezar(ent, val):
    """El JSON del paso anterior en PARADO o con otra huella: el script para."""
    raiz = TMP / "parado"
    montar(raiz, ent, val, estado="PARADO")
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO",
              "10 · con variables_modelo.json en PARADO no empieza")
    raiz = TMP / "huella"
    montar(raiz, ent, val, huella_falsa=True)
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO",
              "10 · con otra huella de la tabla no empieza")
    texto = SCRIPT.read_text(encoding="utf-8")
    nombres = ("filas|sin_objetivo|sin_intermedias|sin_vacios|nombres_unicos|sin_redundancia|columnas_esperadas|"
               "relleno_sin_choque|escalado_segun_matriz")
    comprobar(not re.search(rf"[\"']({nombres})[\"']\s*:\s*\(?\s*(True|False)\b", texto),
              "11 · ninguna validación escrita con su resultado puesto")


# ── 5b. El preprocesador en su módulo ──────────────────────────────────────────
def caso_modulo(m, ent, val):
    """12 · scripts/preparacion_prevision.py existe, se importa sin ejecutar nada y da el mismo preprocesador.

    Se importa en un proceso aparte, con la carpeta de trabajo vacía: no imprime nada ni deja ningún fichero. El script
    12 usa la función del módulo, sin una copia propia, y el preprocesador del módulo transforma igual las dos tablas.
    """
    ruta = SCRIPT.parent / "preparacion_prevision.py"
    comprobar(ruta.exists(), "12 · existe scripts/preparacion_prevision.py")
    if not ruta.exists():
        return
    vacia = TMP / "importar"
    vacia.mkdir(parents=True, exist_ok=True)
    orden = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location('pp', sys.argv[1]); "
             "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)")
    proc = subprocess.run([sys.executable, "-W", "error", "-c", orden, str(ruta)], capture_output=True, text=True,
                          encoding="utf-8", cwd=vacia, env=dict(os.environ, PYTHONUTF8="1"))
    comprobar(proc.returncode == 0 and not proc.stdout and not proc.stderr and not any(vacia.iterdir()),
              f"12 · el módulo se importa sin imprimir ni escribir nada ({proc.stderr[-300:]})")
    spec = importlib.util.spec_from_file_location("preparacion_prevision_prueba", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    texto = SCRIPT.read_text(encoding="utf-8")
    comprobar(not re.search(r"^def (construir_preprocesador|columnas_entrada|nombres_rs|nombre_salida|"
                            r"combinar_categoria)\(", texto, flags=re.M)
              and re.search(r"^from preparacion_prevision import", texto, flags=re.M) is not None,
              "12 · el script 12 importa el preprocesador del módulo y no guarda una copia")
    columnas_evento = [f"evento_{e}" for e in EVENTOS]
    for objetivo in ("unidades", "dolares"):
        del_modulo = modulo.construir_preprocesador(objetivo, columnas_evento).fit(ent)
        del_script = m.construir_preprocesador(objetivo, columnas_evento).fit(ent)
        iguales = all(del_modulo.transform(t).equals(del_script.transform(t)) for t in (ent, val))
        comprobar(iguales and modulo.columnas_entrada(objetivo, columnas_evento)
                  == m.columnas_entrada(objetivo, columnas_evento),
                  f"12 · el módulo da el mismo preprocesador que el script en {objetivo}")


# ── 6. Ejecución ───────────────────────────────────────────────────────────────
def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/12_preparacion.py")
        else:
            m = cargar_script()
            ent = tabla(2000, "2010-01-01", 1)
            val = tabla(60, "2013-03-01", 2, validacion=True)
            caso_base(m, ent, val)
            casos_rojos(m, ent, val)
            casos_al_empezar(ent, val)
            caso_modulo(m, ent, val)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
