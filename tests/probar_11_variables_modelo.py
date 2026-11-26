"""Prueba de scripts/variables_prevision.py y scripts/11_variables_modelo.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_variables/ una carpeta con la estructura del
caso (data/processed/, informes/particion.json y config/modelo/registro-transformaciones.md), ejecuta el
script sobre ella con --raiz y la borra al acabar. Importa el módulo variables_prevision.py y el script que prueba, que
tiene su trabajo bajo __main__.

Los casos que tienen que fallar si el código está mal, cada uno con su control que no debe disparar:
  1. un retardo que toma el día de su fila;
  2. una media que incluye el día de su fila;
  3. el primer día de una serie que toma un dato de otra;
  4. un hueco de fecha en una serie (y una fecha repetida): la función para;
  5. un producto que entra la semana anterior y cuenta sin tener precio cuatro semanas antes, con el código de semana
     que salta como al cambiar de año;
  6. un evento de event_name_2 que no marca su columna;
  7. la recursión: con una historia que acaba en días previstos, la función da los retardos de esos días previstos y
     deja igual los de los días reales;
  8. el script completo: base en OK con sus cifras, un hueco que lo para sin guardar, un precio medio vacío en la
     validación que lo para sin guardar, entradas sin cambiar y ninguna comprobación con su resultado puesto.
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

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "scripts" / "variables_prevision.py"
SCRIPT = RAIZ / "scripts" / "11_variables_modelo.py"
TMP = RAIZ / "tests" / "tmp_variables"
FALLOS = []

# Semanas de la prueba: el código salta de 11105 a 11201, como al cambiar de año
SEMANAS = [11101, 11102, 11103, 11104, 11105, 11201, 11202, 11203, 11204]
DIAS_ENTRENAMIENTO = 49
DIAS_VALIDACION = 14
SERIES = [("CA_1", "FOODS_1"), ("TX_1", "HOBBIES_2")]


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
def serie_simple(tienda, dept, dias, inicio="2011-01-29", base=100):
    """Una serie de un departamento en una tienda con unidades que crecen cada día (ningún valor se repite)."""
    fechas = pd.date_range(inicio, periods=dias, freq="D").astype("datetime64[us]")
    unidades = base + np.arange(dias) * 3
    return pd.DataFrame({"store_id": tienda, "dept_id": dept, "date": fechas,
                         "unidades": unidades.astype("int64"), "dolares": unidades * 2.5})


def calendario_pequeno():
    """El Calendario de la prueba: 63 días, semanas de sábado a viernes con el salto de código y su semana anterior."""
    dias = DIAS_ENTRENAMIENTO + DIAS_VALIDACION
    fechas = pd.date_range("2011-01-29", periods=dias, freq="D").astype("datetime64[us]")
    semana = [SEMANAS[i // 7] for i in range(dias)]
    anterior = [SEMANAS[i // 7 - 1] if i >= 7 else None for i in range(dias)]
    cal = pd.DataFrame({"d": [f"d_{i + 1}" for i in range(dias)], "date": fechas, "wm_yr_wk": semana,
                        "wm_yr_wk_anterior": pd.array(anterior, dtype="Int64")})
    cal["periodo"] = ["construccion" if i < DIAS_ENTRENAMIENTO else "validacion" for i in range(dias)]
    return cal


def precios_pequenos():
    """Precios por producto, tienda y semana. F3 entra en la semana 11104 (posición 3) y no tiene cuatro semanas de
    precio hasta la posición 7; X1 es de otro departamento de la misma tienda y nunca cuenta para FOODS_1."""
    filas = []
    for pos, w in enumerate(SEMANAS):
        filas += [("CA_1", "F1", w, 1.0), ("CA_1", "F2", w, 2.0), ("TX_1", "H1", w, 3.0), ("CA_1", "X1", w, 9.0)]
        if pos >= 3:
            filas.append(("CA_1", "F3", w, 4.0))
    precios = pd.DataFrame(filas, columns=["store_id", "item_id", "wm_yr_wk", "sell_price"])
    dim = pd.DataFrame({"item_id": ["F1", "F2", "F3", "H1", "X1"],
                        "dept_id": ["FOODS_1", "FOODS_1", "FOODS_1", "HOBBIES_2", "HOUSEHOLD_1"],
                        "cat_id": ["FOODS", "FOODS", "FOODS", "HOBBIES", "HOUSEHOLD"]})
    return precios, dim


def tablas_series():
    """Las dos partes de la tabla de series de la prueba, con las 26 columnas y las filas desordenadas."""
    cal = calendario_pequeno()
    filas = []
    for k, (tienda, dept) in enumerate(SERIES):
        for i, r in cal.iterrows():
            unidades = 100 + 3 * i if k == 0 else (i * 7) % 11
            ev1 = {39: "SuperBowl", 44: "Easter", 46: "Father's day", 55: "Easter"}.get(i)
            ev2 = {43: "Cinco De Mayo", 54: "Father's day"}.get(i)
            filas.append({
                "store_id": tienda, "dept_id": dept, "d": r["d"], "cat_id": dept.split("_")[0],
                "state_id": tienda.split("_")[0], "unidades": unidades, "dolares": round(unidades * 2.5, 2),
                "date": r["date"], "year": r["date"].year, "month": r["date"].month,
                "weekday": r["date"].day_name(), "wday": int(r["date"].dayofweek), "wm_yr_wk": r["wm_yr_wk"],
                "wm_yr_wk_anterior": r["wm_yr_wk_anterior"], "event_name_1": ev1,
                "event_type_1": "Cultural" if ev1 else None, "event_name_2": ev2,
                "event_type_2": "Cultural" if ev2 else None, "snap": i % 2, "periodo": r["periodo"],
                "mes_parcial": False, "semana_parcial": False, "cierre_tienda": False, "fuera_del_error": False,
                "clase_cero": None, "precio_medio_semana_anterior": None if i < 35 else 1.5 + k})
    df = pd.DataFrame(filas)
    for c in ["store_id", "dept_id", "d", "cat_id", "state_id", "weekday", "event_name_1", "event_type_1",
              "event_name_2", "event_type_2", "periodo", "clase_cero"]:
        df[c] = df[c].astype("str")
    df["wm_yr_wk_anterior"] = df["wm_yr_wk_anterior"].astype("Int64")
    df["precio_medio_semana_anterior"] = df["precio_medio_semana_anterior"].astype("float64")
    df = df.sample(frac=1.0, random_state=1).reset_index(drop=True)
    return df[df["periodo"] == "construccion"].copy(), df[df["periodo"] == "validacion"].copy(), cal


def montar(raiz, ent, val, cal, precios, dim):
    """Escribe la carpeta del caso de la prueba con sus tablas, particion.json y un registro pequeño."""
    if raiz.exists():
        shutil.rmtree(raiz)
    (raiz / "data" / "processed").mkdir(parents=True)
    (raiz / "informes").mkdir()
    (raiz / "config" / "modelo").mkdir(parents=True)
    pr = raiz / "data" / "processed"
    ent.to_parquet(pr / "hechos_series_entrenamiento.parquet", index=False)
    val.to_parquet(pr / "hechos_series_validacion.parquet", index=False)
    cal.to_parquet(pr / "calendario.parquet", index=False)
    precios.to_parquet(pr / "precios_corregido.parquet", index=False)
    dim.to_parquet(pr / "dim_producto.parquet", index=False)
    particion = {"fecha_datos": "2015-05-22", "resultado": {"estado": "OK"},
                 "partes": [{"parte": "entrenamiento", "sha256": huella(pr / "hechos_series_entrenamiento.parquet")},
                            {"parte": "validacion", "sha256": huella(pr / "hechos_series_validacion.parquet")}]}
    (raiz / "informes" / "particion.json").write_text(json.dumps(particion), encoding="utf-8")
    (raiz / "config" / "modelo" / "registro-transformaciones.md").write_text(
        "# Registro (prueba)\n\n### R-011 · ficha anterior de la prueba\n", encoding="utf-8")


def ejecutar(raiz):
    """Ejecuta el script con -W error sobre la carpeta de la prueba; devuelve código, JSON y salida."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)],
                          capture_output=True, text=True, encoding="utf-8", env=entorno)
    ruta = raiz / "informes" / "variables_modelo.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


# ── 3. Casos de la función de variables ────────────────────────────────────────
def casos_funcion(vp):
    """Casos 1 a 4 y 7: retardos, medias, series separadas, huecos y recursión."""
    a = serie_simple("CA_1", "FOODS_1", 40, base=100)
    b = serie_simple("TX_1", "HOBBIES_2", 40, base=5000)
    historia = pd.concat([a, b], ignore_index=True).sample(frac=1.0, random_state=3)
    v = vp.crear_variables_objetivo(historia, "unidades")
    comprobar(list(v.index) == list(historia.index), "función: devuelve las filas en el índice de la entrada")
    comprobar(set(v.columns) == set(vp.nombres_variables("unidades")) and len(v.columns) == 12,
              "función: las 12 variables de unidades")
    juntos = historia.join(v)
    sa = juntos[juntos["store_id"] == "CA_1"].sort_values("date").reset_index(drop=True)
    sb = juntos[juntos["store_id"] == "TX_1"].sort_values("date").reset_index(drop=True)
    y = sa["unidades"].to_numpy()

    # 1 · el retardo toma el día anterior, nunca el de su fila
    comprobar(sa.loc[20, "unidades_lag_1"] == y[19] and sa.loc[20, "unidades_lag_1"] != y[20],
              "1 · lag_1 es el día anterior y no el de la fila")
    comprobar(sa.loc[30, "unidades_lag_28"] == y[2] and sa.loc[30, "unidades_lag_7"] == y[23],
              "1 · lag_28 y lag_7 en su día")
    # 2 · la media acaba el día anterior
    comprobar(np.isclose(sa.loc[30, "unidades_media_7"], y[23:30].mean()), "2 · media_7 de t-7 a t-1")
    comprobar(np.isclose(sa.loc[30, "unidades_media_28"], y[2:30].mean()), "2 · media_28 de t-28 a t-1")
    comprobar(pd.isna(sa.loc[27, "unidades_media_28"]) and not pd.isna(sa.loc[28, "unidades_media_28"]),
              "2 · media_28 vacía hasta tener 28 días anteriores")
    # 3 · el primer día de una serie no toma nada de otra
    comprobar(pd.isna(sb.loc[0, "unidades_lag_1"]) and pd.isna(sb.loc[0, "unidades_media_7"]),
              "3 · el primer día de la segunda serie queda vacío")
    comprobar(sb.loc[1, "unidades_lag_1"] == sb.loc[0, "unidades"], "3 · el segundo día toma el primero de su serie")

    # La comprobación del script: el control limpio no dispara y cada error inyectado sí
    limpio = vp.comprobar_retardos_y_medias(juntos, "unidades")
    comprobar(limpio["filas_distintas"] == 0, "control limpio: la comprobación de retardos no dispara")
    malo = juntos.copy()
    malo["unidades_lag_1"] = malo["unidades"]
    comprobar(vp.comprobar_retardos_y_medias(malo, "unidades")["filas_distintas"] > 0,
              "1 · la comprobación caza un retardo que toma el día de su fila")
    malo = juntos.sort_values(["store_id", "dept_id", "date"]).copy()
    malo["unidades_media_7"] = (malo.groupby(["store_id", "dept_id"])["unidades"]
                                .transform(lambda s: s.rolling(7).mean()))
    comprobar(vp.comprobar_retardos_y_medias(malo, "unidades")["filas_distintas"] > 0,
              "2 · la comprobación caza una media que incluye el día de su fila")
    malo = juntos.sort_values(["store_id", "dept_id", "date"]).copy()
    malo["unidades_lag_1"] = malo["unidades"].shift(1)
    comprobar(vp.comprobar_retardos_y_medias(malo, "unidades")["filas_distintas"] > 0,
              "3 · la comprobación caza el primer día de una serie que toma el último de otra")

    # 4 · huecos y fechas repetidas: la función para
    con_hueco = historia[historia["date"] != a["date"].iloc[15]]
    try:
        vp.crear_variables_objetivo(con_hueco, "unidades")
        comprobar(False, "4 · un hueco de fecha para la función")
    except vp.HuecoDeFecha as e:
        comprobar("CA_1" in str(e), "4 · un hueco de fecha para la función y dice la serie")
    repetida = pd.concat([historia, a.iloc[[10]]])
    try:
        vp.crear_variables_objetivo(repetida, "unidades")
        comprobar(False, "4 · una fecha repetida para la función")
    except vp.HuecoDeFecha:
        comprobar(True, "4 · una fecha repetida para la función")
    try:
        vp.crear_variables_objetivo(historia, "margen")
        comprobar(False, "función: un objetivo que no es unidades ni dólares para")
    except ValueError:
        comprobar(True, "función: un objetivo que no es unidades ni dólares para")

    # 7 · recursión: historia real hasta el origen, tres días previstos y el día que se prevé, sin valor
    real = serie_simple("CA_1", "FOODS_1", 30, base=100)
    previstos = serie_simple("CA_1", "FOODS_1", 34, base=100).iloc[30:].copy()
    previstos["dolares"] = [999.0, 998.0, 997.0, np.nan]
    historia_rec = pd.concat([real, previstos]).reset_index(drop=True)
    vr = vp.crear_variables_objetivo(historia_rec, "dolares")
    ultimo = vr.iloc[33]
    comprobar(ultimo["dolares_lag_1"] == 997.0 and ultimo["dolares_lag_3"] == 999.0,
              "7 · recursión: lag_1 y lag_3 del día previsto son los días previstos")
    comprobar(ultimo["dolares_lag_4"] == real["dolares"].iloc[29], "7 · recursión: lag_4 es el último día real")
    esperada = np.mean(list(real["dolares"].iloc[26:30]) + [999.0, 998.0, 997.0])
    comprobar(np.isclose(ultimo["dolares_media_7"], esperada), "7 · recursión: media_7 mezcla reales y previstos")
    solo_real = vp.crear_variables_objetivo(real, "dolares")
    comprobar(vr.iloc[:30].equals(solo_real), "7 · los días reales dan lo mismo con o sin días previstos detrás")


# ── 4. Casos de productos con precio y eventos ─────────────────────────────────
def casos_productos_y_eventos(vp):
    """Casos 5 y 6."""
    precios, dim = precios_pequenos()
    cal = calendario_pequeno()
    orden = vp.orden_de_semanas(cal)
    comprobar(orden == SEMANAS, "5 · las semanas, por el orden de sus fechas")
    conteo = vp.contar_productos_que_cuentan(precios, dim, orden)
    c = conteo.set_index(["store_id", "dept_id", "wm_yr_wk"])["productos_con_precio_semana_anterior"]
    comprobar(c[("CA_1", "FOODS_1", 11201)] == 2,
              "5 · F3 entra en 11104 y en 11201 (dos semanas después por fecha) no cuenta, aunque el código salte 97")
    comprobar(c[("CA_1", "FOODS_1", 11203)] == 3, "5 · F3 cuenta en 11203, cuatro semanas después de entrar")
    comprobar(c[("CA_1", "FOODS_1", 11104)] == 0, "5 · nadie cuenta antes de cuatro semanas de precio")
    comprobar(("CA_1", "HOUSEHOLD_1", 11203) in c.index and c[("CA_1", "FOODS_1", 11105)] == 2,
              "control: X1 es de otro departamento y FOODS_1 cuenta solo F1 y F2 en 11105")

    # Unión por la semana anterior: un día de 11202 toma el conteo de 11201
    dias = cal.assign(store_id="CA_1", dept_id="FOODS_1")
    con = vp.anadir_productos_con_precio(dias, conteo)
    fila = con[con["wm_yr_wk"] == 11202].iloc[0]
    comprobar(fila["productos_con_precio_semana_anterior"] == 2, "5 · el día toma el conteo de su semana anterior")
    comprobar(pd.isna(con.iloc[0]["productos_con_precio_semana_anterior"]),
              "5 · sin semana anterior, el conteo queda vacío")

    # 6 · eventos de las dos columnas
    ent, val, _ = tablas_series()
    eventos = vp.lista_eventos(ent)
    comprobar(eventos == sorted(["SuperBowl", "Easter", "Father's day", "Cinco De Mayo"]),
              "6 · la lista de eventos sale de event_name_1 y event_name_2 del entrenamiento")
    marcado = vp.anadir_eventos(val, eventos)
    fd = marcado[marcado["event_name_2"] == "Father's day"]
    comprobar(len(fd) == 2 and (fd["evento_Father's day"] == 1).all(),
              "6 · un evento de event_name_2 marca su columna")
    comprobar(int(marcado["evento_Easter"].sum()) == 2 and int(marcado["evento_SuperBowl"].sum()) == 0,
              "control: Easter en event_name_1 marca 2 días y SuperBowl ninguno en la validación")
    comprobar(set(marcado.loc[marcado["event_name_1"].isna() & marcado["event_name_2"].isna(),
                              [f"evento_{e}" for e in eventos]].stack().unique()) == {0},
              "control: un día sin evento deja todas las columnas a 0")
    dm = vp.anadir_dia_del_mes(val)
    comprobar((dm["dia_del_mes"] == dm["date"].dt.day).all(), "dia_del_mes es el día del mes de date")


# ── 5. Casos del script completo ───────────────────────────────────────────────
def casos_script():
    """Caso 8: el script entero sobre la carpeta de la prueba."""
    ent, val, cal = tablas_series()
    precios, dim = precios_pequenos()
    raiz = TMP / "base"
    montar(raiz, ent, val, cal, precios, dim)
    pr = raiz / "data" / "processed"
    huellas = {p.name: huella(p) for p in pr.glob("*.parquet")}
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "OK",
              f"8 · base: estado OK ({salida[-600:] if codigo else ''})")
    if d is None or codigo != 0:
        return
    comprobar(all(huella(pr / n) == h for n, h in huellas.items()), "8 · base: las entradas no cambian")
    comprobar(d["fecha_datos"] == "2015-05-22" and "scikit-learn" in d["entorno"] and "pyarrow" in d["entorno"],
              "8 · base: fecha_datos y versiones en el JSON")
    comprobar("uso_de_la_validacion" in d and "recursiv" in d["uso_de_la_validacion"],
              "8 · base: el JSON dice que la validación con retardos reales no mide el modelo")
    me = pd.read_parquet(pr / "hechos_modelo_entrenamiento.parquet")
    mv = pd.read_parquet(pr / "hechos_modelo_validacion.parquet")
    comprobar(len(me) == 2 * (DIAS_ENTRENAMIENTO - 35) and len(mv) == 2 * DIAS_VALIDACION,
              "8 · base: salen 35 días por serie del entrenamiento y ninguno de la validación")
    nuevas = [c for c in me.columns if c not in ent.columns]
    comprobar(len(nuevas) == 12 + 12 + 1 + 4 + 1, "8 · base: 30 columnas nuevas con 4 eventos")
    comprobar(not me[nuevas].isna().any().any() and not mv[nuevas].isna().any().any(),
              "8 · base: ninguna variable nueva vacía")

    # Cifras calculadas aquí, a mano, por fecha
    a = pd.concat([ent, val])
    a = a[a["store_id"] == "CA_1"].sort_values("date").reset_index(drop=True)
    y = a["unidades"].to_numpy()
    f40 = me[(me["store_id"] == "CA_1") & (me["d"] == "d_40")].iloc[0]
    comprobar(f40["unidades_lag_1"] == y[38] and f40["unidades_lag_28"] == y[11]
              and np.isclose(f40["unidades_media_7"], y[32:39].mean()), "8 · base: retardos y media del día 40")
    v50 = mv[(mv["store_id"] == "CA_1") & (mv["d"] == "d_50")].iloc[0]
    comprobar(v50["unidades_lag_1"] == y[48] and np.isclose(v50["dolares_media_28"], a["dolares"].iloc[21:49].mean()),
              "8 · base: el primer día de la validación toma los últimos del entrenamiento")
    d42 = me[(me["store_id"] == "CA_1") & (me["d"] == "d_42")].iloc[0]
    d43 = me[(me["store_id"] == "CA_1") & (me["d"] == "d_43")].iloc[0]
    comprobar(d42["productos_con_precio_semana_anterior"] == 2 and d43["productos_con_precio_semana_anterior"] == 2,
              "8 · base: productos con precio en 11201 y 11202 (F3 aún no cuenta)")
    v57 = mv[(mv["store_id"] == "CA_1") & (mv["d"] == "d_57")].iloc[0]
    comprobar(v57["productos_con_precio_semana_anterior"] == 3, "8 · base: F3 cuenta en 11204")
    comprobar(d["eventos"]["numero"] == 4 and d["eventos"]["nuevos_en_validacion"] == [],
              "8 · base: 4 eventos y ninguno nuevo en la validación")
    validaciones = {v["validacion"]: v["resultado"] for v in d["validaciones"]}
    comprobar(validaciones and all(r == "pasa" for r in validaciones.values()), "8 · base: todas las validaciones pasan")
    registro = (raiz / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    fichas = re.findall(r"^### (R-\d{3})", registro, flags=re.M)
    comprobar(fichas == ["R-011", "R-012", "R-013", "R-014", "R-015", "R-016", "R-017"],
              "8 · base: seis fichas nuevas, de R-012 a R-017")
    codigo2, _, _ = ejecutar(raiz)
    registro2 = (raiz / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    comprobar(codigo2 == 0 and registro2 == registro, "8 · base: reejecutar no añade fichas")

    # Un hueco de fecha en una serie: para sin guardar
    raiz = TMP / "hueco"
    montar(raiz, ent[ent["d"] != "d_20"], val, cal, precios, dim)
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO"
              and not (raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet").exists(),
              "8 · un hueco de fecha para el script sin guardar")

    # Un precio medio vacío en la validación: para sin guardar
    raiz = TMP / "precio"
    val2 = val.copy()
    val2.loc[val2.index[0], "precio_medio_semana_anterior"] = np.nan
    montar(raiz, ent, val2, cal, precios, dim)
    codigo, d, _ = ejecutar(raiz)
    falla = [v["validacion"] for v in (d or {}).get("validaciones", []) if v["resultado"] == "falla"]
    comprobar(codigo == 1 and d["resultado"]["estado"] == "PARADO" and any("precio" in f for f in falla)
              and not (raiz / "data" / "processed" / "hechos_modelo_validacion.parquet").exists(),
              "8 · un precio medio vacío en la validación para el script sin guardar")

    # La partición en PARADO: no empieza
    raiz = TMP / "parado"
    montar(raiz, ent, val, cal, precios, dim)
    ruta = raiz / "informes" / "particion.json"
    p = json.loads(ruta.read_text(encoding="utf-8"))
    p["resultado"]["estado"] = "PARADO"
    ruta.write_text(json.dumps(p), encoding="utf-8")
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d["resultado"]["estado"] == "PARADO", "8 · con la partición en PARADO no empieza")

    # Error 24: ninguna validación con su resultado escrito a mano
    texto = SCRIPT.read_text(encoding="utf-8")
    comprobar(len(re.findall(r"[\"']pasa[\"']", texto)) == 1 and len(re.findall(r"[\"']falla[\"']", texto)) == 1,
              "8 · el script calcula cada validación (pasa y falla aparecen solo en su función)")


# ── 6. Ejecución ───────────────────────────────────────────────────────────────
def principal():
    """Ejecuta los casos, borra la carpeta temporal y sale con 0 o 1."""
    try:
        if not MODULO.exists() or not SCRIPT.exists():
            comprobar(False, "existen scripts/variables_prevision.py y scripts/11_variables_modelo.py")
        else:
            sys.path.insert(0, str(MODULO.parent))
            vp = cargar(MODULO, "variables_prevision")
            cargar(SCRIPT, "variables_modelo_11")
            casos_funcion(vp)
            casos_productos_y_eventos(vp)
            casos_script()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
