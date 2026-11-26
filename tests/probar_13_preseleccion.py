"""Prueba de scripts/13_preseleccion.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_preseleccion/ una carpeta con la estructura
del caso (la tabla de entrenamiento, informes/preparacion.json, informes/variables_modelo.json, una copia corta de la
matriz aprobada y un registro de transformaciones), ejecuta el script sobre ella con --raiz y la borra al acabar. La
tabla de validación que se deja en la carpeta es basura a propósito: si el script la abriera, fallaría. Importa solo el
script que prueba, que tiene su trabajo bajo __main__, y el módulo del preprocesador a través de él.

Los casos:
  0. control que no debe disparar: el script entero sobre tablas limpias deja preseleccion.json en AVISO (el grupo de
     los eventos queda para el responsable del caso), con las seis validaciones en verde en los dos objetivos y los dos algoritmos, las
     obligatorias dentro, los pliegues y la reserva por fecha, y su ficha en el registro;
  1 a 6. cada una de las seis validaciones del método, apartado 8, con un caso que tiene que salir en rojo;
  7. una variable obligatoria que la votación dejaría fuera entra igual;
  8. un pliegue que mezcla fechas sale en rojo;
  9. una reserva que no es la parte más reciente sale en rojo;
  10. al empezar: preparacion.json en PARADO, el script para; y ninguna validación escrita con su resultado puesto
      (error 24).
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
from sklearn.model_selection import TimeSeriesSplit

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "13_preseleccion.py"
TMP = RAIZ / "tests" / "tmp_preseleccion"
FALLOS = []
TIENDAS = ["T_A", "T_B"]
DEPARTAMENTOS = ["D_A", "D_B"]
EVENTOS = ["Ev_1", "Ev_2", "Ev_3"]
RETARDOS = (1, 2, 3, 4, 5, 6, 7, 14, 21, 28)
PROHIBIDAS = ["d", "unidades", "dolares", "periodo", "cierre_tienda", "fuera_del_error", "clase_cero", "cat_id",
              "state_id", "wday", "event_type_1", "event_type_2", "year", "date", "wm_yr_wk", "wm_yr_wk_anterior",
              "mes_parcial", "semana_parcial"]

# Copia corta de la matriz aprobada, con las mismas formas de fila que la real; su estado se escribe aquí (error 31)
MATRIZ = """---
estado: aprobada por el responsable del caso (copia de prueba)
---
# Matriz de prueba

## Las columnas de la tabla de series que entran

| variable | tipo | rama | escalado | relleno | salida | entra | porqué | desde cuándo se conoce |
|---|---|---|---|---|---|---|---|---|
| store_id | nominal | ohe | ninguno | no | `store_id_ohe_<tienda>` | sí | prueba | de antemano |
| dept_id | nominal | ohe | ninguno | no | `dept_id_ohe_<departamento>` | sí | prueba | de antemano |
| weekday | nominal | ohe | ninguno | no | `weekday_ohe_<día>` | sí | prueba | de antemano |
| month | nominal | ohe | ninguno | no | `month_ohe_<mes>` | sí | prueba | de antemano |
| event_name_1 | nominal | ohe | ninguno | sin evento | `event_name_1_ohe_<evento>` | sí | prueba | de antemano |
| event_name_2 | nominal | ohe | ninguno | sin evento | `event_name_2_ohe_<evento>` | sí | prueba | de antemano |
| snap | binaria | tal cual | ninguno | no | `snap` | sí | prueba | de antemano |
| precio_medio_semana_anterior | continua | tal cual | ss | no | `precio_medio_semana_anterior_ss` | sí | prueba | de antemano |

## Las columnas de la tabla de series que no entran

| variable | entra | porqué | desde cuándo se conoce |
|---|---|---|---|
| d | no | identificador | de antemano |
| cierre_tienda | no | posterior | al cerrar el día |

## Las variables nuevas candidatas

| variable | tipo | rama | escalado | relleno | salida | entra | porqué | desde cuándo se conoce |
|---|---|---|---|---|---|---|---|---|
| `<obj>_lag_1` a `<obj>_lag_7` | continua | tal cual | rs | ninguno | `<obj>_lag_k_rs` | sí | prueba | t−k |
| `<obj>_lag_14`, `_lag_21`, `_lag_28` | continua | tal cual | rs | ninguno | `<obj>_lag_k_rs` | sí | prueba | t−k |
| `<obj>_media_7` | continua | tal cual | rs | ninguno | `<obj>_media_7_rs` | sí | prueba | t−1 |
| `<obj>_media_28` | continua | tal cual | rs | ninguno | `<obj>_media_28_rs` | sí | prueba | t−1 |
| `productos_con_precio_semana_anterior` | discreta | tal cual | ss | ninguno | `productos_con_precio_semana_anterior_ss` | sí, candidata | prueba | de antemano |

## Candidatas que no estaban en los planteamientos

| variable | tipo | rama | escalado | relleno | salida | entra | porqué | desde cuándo se conoce |
|---|---|---|---|---|---|---|---|---|
| `evento_<nombre>` | binaria | una por evento | ninguno | 0 | `evento_<nombre>` | sí, candidata | prueba | de antemano |
| `dia_del_mes` | discreta | tal cual | ss | no | `dia_del_mes_ss` | sí, candidata | prueba | de antemano |
"""


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
    spec = importlib.util.spec_from_file_location("preseleccion_13", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["preseleccion_13"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Datos pequeños ──────────────────────────────────────────────────────────
def tabla(dias=400, semilla=1):
    """Una tabla con las columnas de hechos_modelo: 2 tiendas, 2 departamentos y `dias` días por serie.

    Las unidades y los dólares dependen del retardo de 7 días y del día de la semana, para que los métodos tengan algo
    que encontrar; las filas salen desordenadas a propósito: el script tiene que ordenarlas por fecha.
    """
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range("2011-03-05", periods=dias, freq="D").astype("datetime64[us]")
    filas = []
    for t in TIENDAS:
        for d in DEPARTAMENTOS:
            base = rng.uniform(20, 80)
            filas.append(pd.DataFrame({"store_id": t, "dept_id": d, "date": fechas}))
            filas[-1]["base"] = base
    x = pd.concat(filas, ignore_index=True)
    n = len(x)
    x["weekday"] = x["date"].dt.day_name().astype("str")
    x["month"] = x["date"].dt.month.astype("int64")
    x["dia_del_mes"] = x["date"].dt.day.astype("int64")
    x["snap"] = (x["date"].dt.day <= 10).astype("int64")
    x["precio_medio_semana_anterior"] = rng.uniform(1, 9, n)
    x["productos_con_precio_semana_anterior"] = rng.integers(3, 60, n)
    ev1 = pd.Series([None] * n, dtype="str")
    ev2 = pd.Series([None] * n, dtype="str")
    dia = (x["date"] - x["date"].min()).dt.days
    # Cada evento en 10 fechas, 40 filas: por encima del mínimo de 30 para no agrupar una categoría
    for i, e in enumerate(EVENTOS):
        ev1[(dia % 30 == i * 7) & (dia < 300)] = e
    ev2[(dia % 30 == 25) & (dia < 300)] = "Ev_1"
    x["event_name_1"] = ev1
    x["event_name_2"] = ev2
    for e in EVENTOS:
        x[f"evento_{e}"] = ((x["event_name_1"] == e).fillna(False) | (x["event_name_2"] == e).fillna(False)).astype("int64")
    finde = x["weekday"].isin(["Saturday", "Sunday"]).to_numpy()
    for o, escala in (("unidades", 1.0), ("dolares", 2.5)):
        serie = x["base"].to_numpy() * escala * (1 + 0.4 * finde) + rng.normal(0, 3, n)
        x[o] = np.clip(serie, 0, None)
        for k in RETARDOS:
            x[f"{o}_lag_{k}"] = np.clip(serie + rng.normal(0, 1 + k, n), 0, None)
        x[f"{o}_media_7"] = x[f"{o}_lag_1"] * 0.5 + x[f"{o}_lag_7"] * 0.5
        x[f"{o}_media_28"] = x[[f"{o}_lag_{k}" for k in (7, 14, 21, 28)]].mean(axis=1)
    for c in PROHIBIDAS:
        if c not in x.columns:
            x[c] = 0
    x = x.drop(columns="base")
    return x.sample(frac=1, random_state=3).reset_index(drop=True)


def montar(raiz, ent, estado_prep="OK"):
    """Escribe la carpeta del caso de la prueba."""
    if raiz.exists():
        shutil.rmtree(raiz)
    pr = raiz / "data" / "processed"
    pr.mkdir(parents=True)
    (raiz / "informes").mkdir()
    (raiz / "config" / "modelo").mkdir(parents=True)
    ent.to_parquet(pr / "hechos_modelo_entrenamiento.parquet", index=False)
    (pr / "hechos_modelo_validacion.parquet").write_bytes(b"no es un parquet: si el script lo abre, falla")
    salidas = [{"ruta": "data/processed/hechos_modelo_entrenamiento.parquet",
                "sha256": huella(pr / "hechos_modelo_entrenamiento.parquet")}]
    previo = {"fecha_datos": "2015-05-22", "resultado": {"estado": "OK"}, "salidas": salidas,
              "eventos": {"lista": EVENTOS, "columnas": [f"evento_{e}" for e in EVENTOS]}}
    (raiz / "informes" / "variables_modelo.json").write_text(json.dumps(previo), encoding="utf-8")
    prep = {"fecha_datos": "2015-05-22", "resultado": {"estado": estado_prep},
            "algoritmo_previsto": "HistGradientBoosting y Ridge, con un solo preprocesador por objetivo",
            "matriz": {"aprobada_por": "el responsable del caso", "fecha": "2026-11-24"},
            "fuera": [{"variable": v, "motivo": "prueba"} for v in PROHIBIDAS]}
    (raiz / "informes" / "preparacion.json").write_text(json.dumps(prep), encoding="utf-8")
    (raiz / "config" / "modelo" / "matriz_transformaciones.md").write_text(MATRIZ, encoding="utf-8")
    (raiz / "config" / "modelo" / "registro-transformaciones.md").write_text(
        "# Registro de transformaciones · prueba\n\n### R-007 · ficha anterior\n\ntexto\n", encoding="utf-8")


def ejecutar(raiz, *extra):
    """Ejecuta el script con -W error; devuelve código, JSON y salida."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz), *extra],
                          capture_output=True, text=True, encoding="utf-8", env=entorno)
    ruta = raiz / "informes" / "preseleccion.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


# ── 3. Control que no debe disparar ────────────────────────────────────────────
def caso_base(ent):
    """El script entero sobre tablas limpias."""
    raiz = TMP / "base"
    montar(raiz, ent)
    antes = huella(raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet")
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "AVISO",
              f"0 · base: estado AVISO, por el grupo de eventos ({salida[-1500:] if codigo else ''})")
    if d is None or codigo != 0:
        return
    comprobar(huella(raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet") == antes,
              "0 · base: la tabla de entrenamiento no cambia")
    comprobar(d["fecha_datos"] == "2015-05-22" and all(k in d["entorno"] for k in
                                                        ("python", "pandas", "numpy", "pyarrow", "scikit-learn")),
              "0 · base: fecha_datos y versiones")
    comprobar(d["escenario"] == "consenso amplio" and d["modo"] == "comparativo" and d["se_preselecciona"] is True,
              "0 · base: modo comparativo y consenso amplio")
    comprobar(all(not re.search(r"validacion|prueba|produccion", Path(a).name) for a in d["tablas_abiertas"])
              and d["tablas_abiertas"] == ["data/processed/hechos_modelo_entrenamiento.parquet"],
              "0 · base: solo se abre la tabla de entrenamiento")
    for o in ("unidades", "dolares"):
        obj = d["objetivos"][o]
        for alg in ("Ridge", "HistGradientBoosting"):
            v = obj["validaciones"][alg]
            comprobar(len(v) == 6 and all(v.values()), f"0 · base: seis validaciones en verde en {o}, {alg}")
        comprobar(all(obj["controles"].values()), f"0 · base: controles en verde en {o}")
        finales = obj["columnas_finales"]
        obligatorias = [f for f in obj["tabla_decisiones"] if f["obligatoria"]]
        comprobar(obligatorias and all(f["columna"] in finales["Ridge"] and f["columna"] in finales["HistGradientBoosting"]
                                       for f in obligatorias), f"0 · base: las obligatorias entran en {o}")
        comprobar(len(finales["HistGradientBoosting"]) == len(obj["tabla_decisiones"]),
                  f"0 · base: HistGradientBoosting conserva todas las columnas sin constantes en {o}")
        comprobar(any(g["clase"] == "ambiguo" for g in obj["una_variante_por_variable"]),
                  f"0 · base: los eventos con dos codificaciones quedan como grupo ambiguo en {o}")
        comprobar(any(f["del_momento"] for f in obj["tabla_decisiones"] if f["origen"] == "weekday"),
                  f"0 · base: el día de la semana sale marcado como del momento en {o}")
    comprobar(len(d["pendientes"]) == 1 and len(d["pendientes"][0]["opciones"]) == 2,
              "0 · base: un pendiente para el responsable del caso con dos opciones")
    registro = (raiz / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    comprobar("### R-008 · " in registro and "consenso amplio" in registro, "0 · base: ficha R-008 en el registro")


# ── 4. Las seis validaciones y los tres controles, en rojo ─────────────────────
def casos_rojos(m):
    """Cada validación y cada control con un caso que tiene que fallar, y su caso bueno al lado."""
    # 1 · nada se ajustó con la validación
    comprobar(m.v_sin_validacion(["data/processed/hechos_modelo_entrenamiento.parquet"])[0]
              and not m.v_sin_validacion(["data/processed/hechos_modelo_entrenamiento.parquet",
                                          "data/processed/hechos_modelo_validacion.parquet"])[0],
              "1 · abrir la validación sale en rojo")
    # 2 · origen en la matriz
    vars_matriz = m.variables_matriz(MATRIZ, "unidades")
    comprobar({"store_id", "unidades_lag_3", "unidades_lag_21", "unidades_media_28", "evento_<nombre>",
               "dia_del_mes"} <= vars_matriz and "d" not in vars_matriz and "dolares_lag_1" not in vars_matriz,
              "2 · la matriz se lee con sus rangos y solo con las filas que entran")
    origen = {"store_id_ohe_T_A": "store_id", "unidades_lag_1_rs": "unidades_lag_1", "rara": "inventada"}
    comprobar(m.v_origen_en_matriz(["store_id_ohe_T_A", "unidades_lag_1_rs"], origen, vars_matriz)[0]
              and not m.v_origen_en_matriz(["store_id_ohe_T_A", "rara"], origen, vars_matriz)[0]
              and not m.v_origen_en_matriz(["sin_origen"], origen, vars_matriz)[0],
              "2 · una columna sin origen en la matriz sale en rojo")
    # 3 · familias enteras
    familias = {"store_id": ["store_id_ohe_T_A", "store_id_ohe_T_B"]}
    comprobar(m.v_familias_enteras(["store_id_ohe_T_A", "store_id_ohe_T_B"], familias)[0]
              and not m.v_familias_enteras(["store_id_ohe_T_A"], familias)[0],
              "3 · una familia a medias sale en rojo")
    # 4 · tope
    comprobar(m.v_tope({"aplica": False, "maximo_columnas": None}, 500)[0]
              and m.v_tope({"aplica": True, "maximo_columnas": 10}, 10)[0]
              and not m.v_tope({"aplica": True, "maximo_columnas": 10}, 11)[0],
              "4 · pasar del tope cuando aplica sale en rojo")
    # 5 · prohibidas
    comprobar(m.v_sin_prohibidas(["snap"], {"snap": "snap"}, PROHIBIDAS)[0]
              and not m.v_sin_prohibidas(["snap", "cierre_tienda"], {"snap": "snap", "cierre_tienda": "cierre_tienda"},
                                         PROHIBIDAS)[0]
              and not m.v_sin_prohibidas(["unidades_ss"], {"unidades_ss": "unidades"}, PROHIBIDAS)[0],
              "5 · una prohibida o el objetivo en la lista sale en rojo")
    # 6 · lista válida
    comprobar(m.v_lista_valida(["a", "b"])[0] and not m.v_lista_valida([])[0] and not m.v_lista_valida(["a", "a"])[0],
              "6 · una lista vacía o con repetidos sale en rojo")

    # 7 · una obligatoria que la votación dejaría fuera entra igual
    votos = pd.DataFrame({"columna": ["snap", "x_lag_1_rs", "x_lag_2_rs"], "votos": [0, 3, 1]})
    origen = {"snap": "snap", "x_lag_1_rs": "x_lag_1", "x_lag_2_rs": "x_lag_2"}
    decision = m.decidir_por_votos(votos, origen, {"snap": "prueba"}, "consenso amplio")
    sin_regla = m.decidir_por_votos(votos, origen, {}, "consenso amplio")
    comprobar(decision["snap"]["entra"] and decision["snap"]["motivo"].startswith("obligatoria")
              and not sin_regla["snap"]["entra"] and decision["x_lag_1_rs"]["entra"]
              and not decision["x_lag_2_rs"]["entra"],
              "7 · la obligatoria con 0 votos entra; sin la regla saldría")
    comprobar(m.c_obligatorias_dentro(["snap", "x_lag_1_rs"], origen, {"snap": "prueba"})[0]
              and not m.c_obligatorias_dentro(["x_lag_1_rs"], origen, {"snap": "prueba"})[0],
              "7 · el control de las obligatorias sale en rojo si falta una")

    # 8 · un pliegue que mezcla fechas
    fechas = pd.Series(pd.date_range("2012-01-01", periods=50, freq="D").repeat(7))
    buenos = m.pliegues_por_fecha(fechas, 3)
    por_filas = list(TimeSeriesSplit(3).split(np.zeros(len(fechas))))
    comprobar(m.c_pliegues_por_fecha(fechas, buenos)[0] and not m.c_pliegues_por_fecha(fechas, por_filas)[0],
              "8 · un pliegue que corta una fecha por la mitad sale en rojo")
    desordenadas = fechas.sample(frac=1, random_state=4).reset_index(drop=True)
    comprobar(not m.c_pliegues_por_fecha(desordenadas, por_filas)[0],
              "8 · pliegues sobre filas sin ordenar por fecha salen en rojo")

    # 9 · la reserva de la permutación no es la parte más reciente
    reciente = m.reserva_reciente(fechas, 0.2)
    al_azar = pd.Series(np.random.default_rng(5).random(len(fechas)) < 0.2)
    antigua = fechas <= fechas.sort_values().iloc[int(len(fechas) * 0.2)]
    comprobar(m.c_reserva_reciente(fechas, reciente, 0.2)[0] and not m.c_reserva_reciente(fechas, al_azar, 0.2)[0]
              and not m.c_reserva_reciente(fechas, antigua, 0.2)[0],
              "9 · una reserva al azar o la más antigua sale en rojo")

    # El corte por salto natural: la mayor caída entre dos valores seguidos
    valor, marcadas = m.corte_salto(pd.Series({"a": 0.9, "b": 0.8, "c": 0.1, "d": 0.05}))
    comprobar(marcadas == {"a", "b"} and valor == 0.8, "corte: el salto natural separa a y b de c y d")


# ── 5. Al empezar y error 24 ───────────────────────────────────────────────────
def casos_al_empezar(ent):
    """preparacion.json en PARADO: el script para; el código no lleva validaciones con su resultado puesto."""
    raiz = TMP / "parado"
    montar(raiz, ent.head(200), estado_prep="PARADO")
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO",
              "10 · con preparacion.json en PARADO no empieza")
    texto = SCRIPT.read_text(encoding="utf-8")
    nombres = ("sin_validacion|origen_en_matriz|familias_enteras|tope|sin_prohibidas|lista_valida|"
               "obligatorias_dentro|pliegues_por_fecha|reserva_reciente")
    comprobar(not re.search(rf"[\"']({nombres})[\"']\s*:\s*\(?\s*(True|False)\b", texto),
              "10 · ninguna validación escrita con su resultado puesto")
    comprobar("hechos_modelo_validacion" not in texto, "10 · el script no nombra la tabla de validación")


# ── 6. Ejecución ───────────────────────────────────────────────────────────────
def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/13_preseleccion.py")
        else:
            m = cargar_script()
            ent = tabla()
            casos_rojos(m)
            casos_al_empezar(ent)
            caso_base(ent)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
