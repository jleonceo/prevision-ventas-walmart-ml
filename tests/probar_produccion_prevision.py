"""Prueba de scripts/produccion_prevision.py, el módulo del Pipeline de producción, con datos pequeños escritos aquí.

No lee ningún dato del caso. Monta en memoria una venta, unos precios y un calendario con la forma de data/raw/ (dos
tiendas, dos departamentos, cuatro productos, 140 días) y un contrato de juguete con la forma de informes/preproduccion.json.

Los casos:
  1. importar el módulo no ejecuta nada ni escribe ningún fichero (programacion-del-caso, error 1);
  2. la receta sale del contrato: las ramas por nombre, leídas del paso del preprocesador de cada finalista; para si
     una columna del modelo no sale de ninguna finalista;
  3. el calendario: la fecha con su formato (R-001), los SNAP en minúsculas (R-002) y la semana anterior por el orden
     de las fechas, también al saltar el código de año (T-003); para si una fecha no se lee;
  4. la venta por serie (R-004): unidades y dólares sumados en céntimos; un producto con la venta vacía deja vacío el
     día de su serie, nunca cero; un día con venta y sin precio para;
  5. el precio medio y los productos de la semana anterior (R-009 y R-014): solo cuentan los productos con precio
     desde cuatro semanas antes;
  6. la tabla del futuro: snap del estado de cada tienda, día del mes (R-016), el precio de la semana anterior;
  7. los eventos aprenden su lista en el fit (R-015): un evento que solo llega al prever no crea columna;
  8. el Pipeline: columnas de salida iguales a las de la receta, en su orden; una tienda nueva no rompe la ejecución
     (handle_unknown); la comprobación de columnas para si sobra o falta una;
  9. cada llamada construye objetos nuevos (pipelines.md, regla 14);
 10. guardar y cargar: con la ficha que cuadra carga; con otra versión de scikit-learn o con el fichero cambiado, no;
 11. la previsión recursiva del módulo da una fila por serie y día, sin negativas, y cada serie recibe la suya aunque
     lleguen en otro orden.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "scripts" / "produccion_prevision.py"
TMP = RAIZ / "tests" / "tmp_produccion_prevision"
sys.path.insert(0, str(RAIZ / "scripts"))
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


# ── 2. Datos pequeños con la forma de data/raw/ ───────────────────────────────
TIENDAS = {"CA_1": "CA", "TX_1": "TX"}
PRODUCTOS = {"FOODS_1_001": "FOODS_1", "FOODS_1_002": "FOODS_1", "HOBBIES_1_001": "HOBBIES_1",
             "HOBBIES_1_002": "HOBBIES_1"}
EVENTOS = {7: ("SuperBowl", None), 16: ("ValentinesDay", None), 100: ("SuperBowl", "Easter")}
# Un producto que empieza a venderse tarde en TX_1: su primera semana con precio es la sexta
PRODUCTO_TARDIO = ("HOBBIES_1_002", "TX_1", 11106)


def calendario_crudo(dias=140):
    """Un calendario con las columnas de data/raw/calendar.csv; semanas de sábado a viernes desde 11101."""
    fechas = pd.date_range("2011-01-29", periods=dias, freq="D")
    n = np.arange(dias)
    cal = pd.DataFrame({"date": fechas.strftime("%Y-%m-%d"), "wm_yr_wk": 11101 + n // 7,
                        "weekday": fechas.day_name(), "wday": n % 7 + 1, "month": fechas.month,
                        "year": fechas.year, "d": [f"d_{i + 1}" for i in n]})
    cal["event_name_1"] = pd.Series([EVENTOS.get(i, (None, None))[0] for i in n], dtype="object")
    cal["event_type_1"] = pd.Series(["Sporting" if i in EVENTOS else None for i in n], dtype="object")
    cal["event_name_2"] = pd.Series([EVENTOS.get(i, (None, None))[1] for i in n], dtype="object")
    cal["event_type_2"] = pd.Series(["Cultural" if EVENTOS.get(i, (None, None))[1] else None for i in n],
                                    dtype="object")
    cal["snap_CA"] = (fechas.day <= 10).astype("int64")
    cal["snap_TX"] = ((fechas.day >= 3) & (fechas.day <= 12)).astype("int64")
    cal["snap_WI"] = 0
    return cal


def precios_crudos(cal):
    """Precio de cada producto y tienda cada semana; el producto tardío solo desde su semana."""
    filas = []
    for tienda in TIENDAS:
        for item in PRODUCTOS:
            for semana in sorted(cal["wm_yr_wk"].unique()):
                if (item, tienda) == PRODUCTO_TARDIO[:2] and semana < PRODUCTO_TARDIO[2]:
                    continue
                base = 2.5 if item.startswith("FOODS") else 7.0
                filas.append({"store_id": tienda, "item_id": item, "wm_yr_wk": int(semana),
                              "sell_price": round(base + 0.01 * (int(semana) % 3), 2)})
    return pd.DataFrame(filas)


def venta_cruda(cal, precios, semilla=7):
    """La venta con la forma de data/raw/sales_train_evaluation.csv: una fila por producto y tienda, un día por columna.

    Cero en las semanas sin precio: una semana sin precio es una semana sin venta (reglas, apartado 5).
    """
    rng = np.random.default_rng(semilla)
    dias = cal["d"].tolist()
    con_precio = set(zip(precios["item_id"], precios["store_id"], precios["wm_yr_wk"]))
    filas = []
    for tienda, estado in TIENDAS.items():
        for item, dept in PRODUCTOS.items():
            fila = {"id": f"{item}_{tienda}_evaluation", "item_id": item, "dept_id": dept,
                    "cat_id": dept.split("_")[0], "store_id": tienda, "state_id": estado}
            lam = 6.0 if dept.startswith("FOODS") else 2.0
            valores = rng.poisson(lam, size=len(dias))
            for i, (d, semana) in enumerate(zip(dias, cal["wm_yr_wk"])):
                fin_de_semana = cal["weekday"].iloc[i] in ("Saturday", "Sunday")
                v = int(valores[i] + (3 if fin_de_semana else 0))
                fila[d] = v if (item, tienda, int(semana)) in con_precio else 0
            filas.append(fila)
    return pd.DataFrame(filas)


def contrato_pequeno(objetivo, columnas):
    """Un contrato de juguete con la forma de informes/preproduccion.json para un objetivo."""
    def paso(texto):
        return {"ficha": "R-011", "etapa": "preprocesador", "clase": "aprende", "paso": texto}

    finalistas = []
    for v in ("store_id", "dept_id", "weekday"):
        finalistas.append({"variable": v, "columnas_del_modelo": [c for c in columnas if c.startswith(f"{v}_ohe_")],
                           "cadena": [paso(f"OneHotEncoder aprende las categorías de {v} en el entrenamiento")]})
    finalistas.append({"variable": "snap", "columnas_del_modelo": ["snap"],
                       "cadena": [{"ficha": "R-011", "etapa": "preprocesador", "clase": "no aprende",
                                   "paso": "snap pasa tal cual"}]})
    finalistas.append({"variable": "evento_<nombre>", "columnas_del_modelo": [c for c in columnas
                                                                              if c.startswith("evento_")],
                       "cadena": [{"ficha": "R-015", "etapa": "variables", "clase": "aprende",
                                   "paso": "la lista de eventos se saca de los días de entrenamiento"},
                                  {"ficha": "R-011", "etapa": "preprocesador", "clase": "no aprende",
                                   "paso": "evento_<nombre> pasa tal cual"}]})
    for v in ("precio_medio_semana_anterior", "productos_con_precio_semana_anterior", "dia_del_mes"):
        finalistas.append({"variable": v, "columnas_del_modelo": [f"{v}_ss"],
                           "cadena": [paso(f"StandardScaler aprende la escala de {v} en el entrenamiento")]})
    for k in (1, 2, 3, 4, 5, 6, 7, 14, 21, 28):
        finalistas.append({"variable": f"{objetivo}_lag_{k}", "columnas_del_modelo": [f"{objetivo}_lag_{k}_rs"],
                           "cadena": [paso(f"RobustScaler aprende la escala de {objetivo}_lag_{k} en el entrenamiento")]})
    for w in (7, 28):
        finalistas.append({"variable": f"{objetivo}_media_{w}", "columnas_del_modelo": [f"{objetivo}_media_{w}_rs"],
                           "cadena": [paso(f"RobustScaler aprende la escala de {objetivo}_media_{w} en el "
                                           "entrenamiento")]})
    receta = {"algoritmo": "HistGradientBoosting", "semilla": 42, "columnas": columnas,
              "hiperparametros": {"max_iter": 15, "min_samples_leaf": 5, "random_state": 42, "early_stopping": False}}
    return {"contrato": {"aprobado_por": "el responsable del caso", "fecha": "2026-11-25"},
            "objetivos": {objetivo: {"finalistas": finalistas, "receta": receta}}}


def columnas_pequenas(objetivo, eventos=("Easter", "SuperBowl")):
    """Las columnas del modelo de juguete, en el orden en que las pide la receta.

    ValentinesDay cae en los primeros días, sin historia: no está en el entrenamiento y no sale columna (R-015).
    """
    dias = sorted(["Friday", "Monday", "Saturday", "Sunday", "Thursday", "Tuesday", "Wednesday"])
    return ([f"store_id_ohe_{t}" for t in TIENDAS] + ["dept_id_ohe_FOODS_1", "dept_id_ohe_HOBBIES_1"]
            + [f"weekday_ohe_{d}" for d in dias] + ["snap"] + [f"evento_{e}" for e in eventos]
            + [f"{v}_ss" for v in ("precio_medio_semana_anterior", "productos_con_precio_semana_anterior",
                                   "dia_del_mes")]
            + [f"{objetivo}_lag_{k}_rs" for k in (1, 2, 3, 4, 5, 6, 7, 14, 21, 28)]
            + [f"{objetivo}_media_{w}_rs" for w in (7, 28)])


# ── 3. Casos ───────────────────────────────────────────────────────────────────
def probar_importar():
    """Caso 1: importar el módulo en un proceso aparte no escribe nada en la carpeta de trabajo."""
    TMP.mkdir(parents=True, exist_ok=True)
    antes = sorted(p.name for p in TMP.iterdir())
    proc = subprocess.run([sys.executable, "-W", "error", "-c",
                           f"import sys; sys.path.insert(0, r'{RAIZ / 'scripts'}'); import produccion_prevision"],
                          capture_output=True, text=True, cwd=TMP, env=dict(os.environ, PYTHONUTF8="1"), timeout=120)
    despues = sorted(p.name for p in TMP.iterdir())
    comprobar(proc.returncode == 0 and antes == despues and proc.stdout == "",
              f"importar el módulo no ejecuta nada ({proc.returncode}; {proc.stderr[-300:]})")


def probar_receta(pp):
    """Caso 2: la receta sale del contrato, por nombre; una columna sin finalista para."""
    cols = columnas_pequenas("unidades")
    receta = pp.receta_del_contrato(contrato_pequeno("unidades", cols), "unidades")
    comprobar(receta["ramas"]["ohe"] == ["store_id", "dept_id", "weekday"]
              and receta["ramas"]["eventos"] == ["event_name_1", "event_name_2"] and receta["ramas"]["pasa"] == ["snap"]
              and receta["ramas"]["ss"][0] == "precio_medio_semana_anterior" and len(receta["ramas"]["rs"]) == 12,
              f"receta: ramas leídas del paso del preprocesador ({receta['ramas']})")
    comprobar(receta["columnas"] == cols and receta["hiperparametros"]["max_iter"] == 15,
              "receta: columnas e hiperparámetros del contrato")
    malo = contrato_pequeno("unidades", cols + ["columna_rara_ss"])
    try:
        pp.receta_del_contrato(malo, "unidades")
        comprobar(False, "receta: una columna sin finalista para")
    except ValueError:
        comprobar(True, "receta: una columna sin finalista para")


def probar_calendario(pp):
    """Caso 3: R-001, R-002 y T-003, con el salto del código de año."""
    cal = calendario_crudo(10)
    cal.loc[:6, "wm_yr_wk"] = 11152
    cal.loc[7:, "wm_yr_wk"] = 11201
    listo = pp.preparar_calendario(cal)
    comprobar(pd.api.types.is_datetime64_any_dtype(listo["date"]) and "snap_ca" in listo.columns
              and "snap_CA" not in listo.columns, "calendario: fecha como fecha y SNAP en minúsculas")
    anterior = dict(zip(listo["wm_yr_wk"], listo["wm_yr_wk_anterior"]))
    comprobar(anterior[11201] == 11152 and pd.isna(anterior[11152]),
              f"calendario: la semana anterior de 11201 es 11152, por el orden de las fechas ({anterior})")
    roto = calendario_crudo(10)
    roto.loc[3, "date"] = "03/02/2011"
    try:
        pp.preparar_calendario(roto)
        comprobar(False, "calendario: una fecha que no se lee con año-mes-día para")
    except ValueError:
        comprobar(True, "calendario: una fecha que no se lee con año-mes-día para")


def probar_venta(pp):
    """Caso 4: R-004 con céntimos, el vacío que no es cero y la venta sin precio que para."""
    cal = pp.preparar_calendario(calendario_crudo(21))
    precios = precios_crudos(calendario_crudo(21))
    venta = venta_cruda(calendario_crudo(21), precios)
    dim_producto, dim_tienda = pp.dimensiones(venta)
    dias = [f"d_{i}" for i in range(15, 22)]
    serie = pp.venta_por_serie(venta, precios, cal, dim_producto, dias)
    esperado = venta[(venta["store_id"] == "CA_1") & (venta["dept_id"] == "FOODS_1")][dias].to_numpy().sum(axis=0)
    real = serie[(serie["store_id"] == "CA_1") & (serie["dept_id"] == "FOODS_1")].sort_values("date")["unidades"]
    comprobar(len(serie) == 4 * 7 and np.array_equal(real.to_numpy(), esperado),
              f"venta: una fila por serie y día con las unidades sumadas ({len(serie)})")
    # Dólares por otro camino: unidades por el precio de su semana, producto a producto
    larga = venta.melt(id_vars=["item_id", "store_id"], value_vars=dias, var_name="d", value_name="u")
    larga = larga.merge(cal[["d", "wm_yr_wk"]], on="d").merge(precios, on=["item_id", "store_id", "wm_yr_wk"],
                                                               how="left")
    total = float((larga["u"] * larga["sell_price"].fillna(0)).sum())
    comprobar(abs(float(serie["dolares"].sum()) - total) < 1e-6,
              f"venta: los dólares son unidades por precio ({serie['dolares'].sum():.2f} y {total:.2f})")
    con_vacio = venta.astype({"d_17": "float64"})
    con_vacio.loc[0, "d_17"] = np.nan
    s2 = pp.venta_por_serie(con_vacio, precios, cal, dim_producto, dias)
    fila = s2[(s2["store_id"] == venta.loc[0, "store_id"]) & (s2["dept_id"] == venta.loc[0, "dept_id"])
              & (s2["date"] == pd.Timestamp("2011-02-14"))]
    comprobar(len(fila) == 1 and fila["unidades"].isna().all() and fila["dolares"].isna().all(),
              "venta: un producto con la venta vacía deja vacío el día de su serie, no cero")
    sin_precio = venta.copy()
    item, tienda, _ = PRODUCTO_TARDIO
    sin_precio.loc[(sin_precio["item_id"] == item) & (sin_precio["store_id"] == tienda), "d_15"] = 4
    try:
        pp.venta_por_serie(sin_precio, precios, cal, dim_producto, dias)
        comprobar(False, "venta: un día con venta y sin precio para")
    except ValueError:
        comprobar(True, "venta: un día con venta y sin precio para")


def probar_precio(pp):
    """Caso 5: R-009 y R-014 con la regla de las cuatro semanas."""
    crudo = calendario_crudo(70)
    cal = pp.preparar_calendario(crudo)
    precios = precios_crudos(crudo)
    venta = venta_cruda(crudo, precios)
    dim_producto, _ = pp.dimensiones(venta)
    por_semana = pp.precio_y_productos_por_semana(precios, dim_producto, cal)
    tx = por_semana[(por_semana["store_id"] == "TX_1") & (por_semana["dept_id"] == "HOBBIES_1")].set_index("wm_yr_wk")
    # El producto tardío empieza en 11106: cuenta desde 11110; antes solo cuenta el otro producto de HOBBIES_1
    comprobar(int(tx.loc[11109, "productos_con_precio_semana_anterior"]) == 1
              and int(tx.loc[11110, "productos_con_precio_semana_anterior"]) == 2,
              "precio: el producto nuevo cuenta desde cuatro semanas después de su primer precio")
    otro = precios[(precios["store_id"] == "TX_1") & (precios["item_id"] == "HOBBIES_1_001")].set_index("wm_yr_wk")
    comprobar(abs(tx.loc[11109, "precio_medio_semana_anterior"] - otro.loc[11109, "sell_price"]) < 1e-12,
              "precio: la media de 11109 es la del único producto que cuenta")
    comprobar(pd.isna(tx.loc[11101, "precio_medio_semana_anterior"]),
              "precio: la primera semana no tiene ningún producto que cuente y queda vacía")


def probar_futuro(pp):
    """Caso 6: la tabla del futuro, con snap del estado, día del mes y precio de la semana anterior."""
    crudo = calendario_crudo(70)
    cal = pp.preparar_calendario(crudo)
    precios = precios_crudos(crudo)
    venta = venta_cruda(crudo, precios)
    dim_producto, dim_tienda = pp.dimensiones(venta)
    por_semana = pp.precio_y_productos_por_semana(precios, dim_producto, cal)
    series = venta[["store_id", "dept_id"]].drop_duplicates()
    dias = list(pd.date_range("2011-03-20", periods=5, freq="D"))
    futuro = pp.tabla_del_futuro(series, dias, cal, dim_tienda, por_semana)
    comprobar(len(futuro) == len(series) * 5, f"futuro: una fila por serie y día ({len(futuro)})")
    fila = futuro[(futuro["store_id"] == "TX_1") & (futuro["date"] == pd.Timestamp("2011-03-20"))].iloc[0]
    comprobar(int(fila["snap"]) == int(crudo.set_index("date").loc["2011-03-20", "snap_TX"])
              and int(fila["dia_del_mes"]) == 20, "futuro: snap del estado de la tienda y día del mes")
    semana = int(cal.set_index("date").loc[pd.Timestamp("2011-03-20"), "wm_yr_wk_anterior"])
    esperado = por_semana.set_index(["store_id", "dept_id", "wm_yr_wk"]).loc[
        ("TX_1", fila["dept_id"], semana), "precio_medio_semana_anterior"]
    comprobar(abs(fila["precio_medio_semana_anterior"] - esperado) < 1e-12,
              "futuro: el precio es el de la semana anterior")
    comprobar(not any(c in futuro.columns for c in ("unidades", "dolares")),
              "futuro: no trae el objetivo (llega vacío al prever, nunca a cero)")


def tabla_pequena(pp, dias=140):
    """La tabla con variables de los datos pequeños, sin los días sin historia."""
    crudo = calendario_crudo(dias)
    precios = precios_crudos(crudo)
    venta = venta_cruda(crudo, precios)
    tabla = pp.tabla_con_variables(venta, precios, crudo)
    necesarias = [c for c in tabla.columns if c.startswith(("unidades_", "dolares_"))] + [
        "precio_medio_semana_anterior"]
    return tabla[tabla[necesarias].notna().all(axis=1).to_numpy()].reset_index(drop=True), venta, precios, crudo


def probar_eventos(pp):
    """Caso 7: la lista de eventos se aprende en el fit."""
    x = pd.DataFrame({"event_name_1": pd.Series(["SuperBowl", None, "NewYear"], dtype="object"),
                      "event_name_2": pd.Series([None, "Easter", None], dtype="object")})
    t = pp.EventosDelEntrenamiento().fit(x.iloc[:2])
    salida = t.transform(x)
    comprobar(list(salida.columns) == ["evento_Easter", "evento_SuperBowl"]
              and salida.to_numpy().tolist() == [[0, 1], [1, 0], [0, 0]],
              f"eventos: la lista sale del fit y un evento nuevo no crea columna ({list(salida.columns)})")


def probar_pipeline(pp):
    """Casos 8 y 9: columnas de salida, handle_unknown, comprobación de columnas y objetos nuevos."""
    tabla, *_ = tabla_pequena(pp)
    cols = columnas_pequenas("unidades")
    receta = pp.receta_del_contrato(contrato_pequeno("unidades", cols), "unidades")
    entrada = pp.columnas_de_entrada(receta)
    pipe = pp.construir_pipeline(receta)
    pipe.fit(tabla[entrada], tabla["unidades"])
    salen = list(pipe.named_steps["modelo"].feature_names_in_)
    comprobar(salen == cols, f"pipeline: el modelo recibe las columnas de la receta, en su orden ({len(salen)})")
    comprobar(pp.comprobar_columnas_de_salida(pipe, cols) == sorted(cols),
              "pipeline: la comprobación de columnas pasa con las de la receta")
    try:
        pp.comprobar_columnas_de_salida(pipe, cols + ["otra_ss"])
        comprobar(False, "pipeline: la comprobación de columnas para si falta una")
    except ValueError:
        comprobar(True, "pipeline: la comprobación de columnas para si falta una")
    nueva = tabla.head(3).copy()
    nueva["store_id"] = "WI_9"
    previsto = pipe.predict(nueva[entrada])
    comprobar(len(previsto) == 3 and np.isfinite(previsto).all(), "pipeline: una tienda nueva no rompe la ejecución")
    otro = pp.construir_pipeline(receta)
    comprobar(otro is not pipe and otro.named_steps["modelo"] is not pipe.named_steps["modelo"]
              and not hasattr(otro.named_steps["modelo"], "n_iter_"), "pipeline: cada llamada crea objetos nuevos")
    radio = pp.inspeccion(pipe)
    comprobar(radio["remainder"] == "drop" and radio["columnas_modelo"] == cols and radio["eventos_aprendidos"]
              and set(r["nombre"] for r in radio["ramas"]) == {"ohe", "eventos", "pasa", "ss", "rs"},
              "pipeline: la inspección trae ramas, remainder, columnas y eventos")
    filas = pp.lleva_filas_de_entrenamiento(pipe, len(tabla))
    comprobar(filas["lleva"] is False, f"pipeline: el boosting no guarda filas de entrenamiento ({filas})")


def probar_guardar_cargar(pp):
    """Caso 10: la ficha cuadra o no carga."""
    tabla, *_ = tabla_pequena(pp)
    cols = columnas_pequenas("unidades")
    receta = pp.receta_del_contrato(contrato_pequeno("unidades", cols), "unidades")
    pipe = pp.construir_pipeline(receta).fit(tabla[pp.columnas_de_entrada(receta)], tabla["unidades"])
    ruta = TMP / "modelo" / "unidades.joblib"
    pp.guardar_modelo(pipe, ruta, semilla=42)
    cargado, ficha = pp.cargar_modelo(ruta)
    x = tabla[pp.columnas_de_entrada(receta)]
    comprobar(np.array_equal(cargado.predict(x), pipe.predict(x)) and ficha["semilla"] == 42,
              "guardar: con la ficha que cuadra, carga y prevé igual")
    ruta_ficha = ruta.with_name("unidades_versiones.json")
    original = ruta_ficha.read_text(encoding="utf-8")
    datos = json.loads(original)
    datos["versiones"]["scikit-learn"] = "0.0.1"
    ruta_ficha.write_text(json.dumps(datos), encoding="utf-8")
    try:
        pp.cargar_modelo(ruta)
        comprobar(False, "cargar: con otra versión de scikit-learn en la ficha no carga")
    except pp.FichaQueNoCuadra:
        comprobar(True, "cargar: con otra versión de scikit-learn en la ficha no carga")
    ruta_ficha.write_text(original, encoding="utf-8")
    with open(ruta, "ab") as f:
        f.write(b"0")
    try:
        pp.cargar_modelo(ruta)
        comprobar(False, "cargar: con el fichero cambiado no carga")
    except pp.FichaQueNoCuadra:
        comprobar(True, "cargar: con el fichero cambiado no carga")


def probar_prever(pp):
    """Caso 11: la previsión recursiva del módulo, completa, sin negativas y sin depender del orden de las series."""
    tabla, venta, precios, crudo = tabla_pequena(pp)
    cols = columnas_pequenas("dolares")
    receta = pp.receta_del_contrato(contrato_pequeno("dolares", cols), "dolares")
    origen = pd.Timestamp("2011-06-10")   # el ajuste llega al 13/05 y trae el día 100, con sus dos eventos
    ajuste = tabla[tabla["date"] <= origen - pd.Timedelta(28, "D")]
    pipe = pp.construir_pipeline(receta).fit(ajuste[pp.columnas_de_entrada(receta)], ajuste["dolares"])
    historia = tabla[tabla["date"] <= origen][["store_id", "dept_id", "date", "dolares"]]
    futuro = tabla[(tabla["date"] > origen) & (tabla["date"] <= origen + pd.Timedelta(7, "D"))]
    futuro = futuro.drop(columns=[c for c in futuro.columns if c.startswith(("unidades", "dolares"))])
    a = pp.prever(pipe, historia, futuro, "dolares", 7, origen)
    b = pp.prever(pipe, historia.sample(frac=1, random_state=1), futuro.sample(frac=1, random_state=2), "dolares", 7,
                  origen)
    comprobar(len(a) == 4 * 7 and a["prevision_sin_redondear"].notna().all()
              and (a["prevision_sin_redondear"] >= 0).all(), f"prever: una fila por serie y día, sin negativas ({len(a)})")
    unidas = a.merge(b, on=["store_id", "dept_id", "date"], suffixes=("", "_b"))
    comprobar(len(unidas) == len(a) and np.array_equal(unidas["prevision_sin_redondear"].to_numpy(),
                                                       unidas["prevision_sin_redondear_b"].to_numpy()),
              "prever: con las series en otro orden cada una recibe la suya")
    comprobar(np.array_equal(pp.redondear_salida(np.array([0.5, 1.49, 2.5]), "unidades"), np.array([1.0, 1.0, 3.0]))
              and np.array_equal(pp.redondear_salida(np.array([0.5, 1.49]), "dolares"), np.array([0.5, 1.49])),
              "prever: las unidades se redondean con la mitad hacia arriba y los dólares no")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not MODULO.exists():
            comprobar(False, f"existe el módulo {MODULO.relative_to(RAIZ)}")
        else:
            probar_importar()
            import produccion_prevision as modulo
            probar_receta(modulo)
            probar_calendario(modulo)
            probar_venta(modulo)
            probar_precio(modulo)
            probar_futuro(modulo)
            probar_eventos(modulo)
            probar_pipeline(modulo)
            probar_guardar_cargar(modulo)
            probar_prever(modulo)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_produccion_prevision borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
