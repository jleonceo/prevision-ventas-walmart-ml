"""Prueba de scripts/05_transformacion_datos.py.

Sin argumentos usa solo datos pequeños escritos aquí. Cada caso monta en tests/tmp_transformacion/<caso>/ una copia
mínima de la estructura del caso (data/processed/, informes/ y el registro de transformaciones, con el estado que se
prueba escrito aquí) y ejecuta el script como proceso aparte con --raiz, con -W error. No importa ningún script del
caso: importarlo lo ejecutaría. La carpeta se crea y se borra. Sale con 0 si todo pasa y con 1 si algo falla, e imprime
qué caso falla.

Con --datos compara además informes/transformacion-datos.json con la clave "transformacion" de
tests/cifras_de_referencia.json y hace una segunda vía (programacion-del-caso §6):
  - vía 1: el script pasa la venta a filas (melt), une Calendario, precios y dimensiones con merge validado, suma por
    serie y día con groupby y guarda data/processed/hechos_series.parquet;
  - vía 2: esta prueba parte de la venta ANCHA de data/processed/venta_corregido.parquet, busca el precio de cada día
    por índice de semana en una matriz de precios, suma por serie con numpy (np.add.at) y rehace las unidades y los
    dólares por serie y periodo, los recuentos de cierre_tienda y clase_cero y el precio medio de la semana anterior,
    sin melt ni merge. Compara con hechos_series.parquet.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
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
SCRIPT = RAIZ / "scripts" / "05_transformacion_datos.py"
TMP = RAIZ / "tests" / "tmp_transformacion"
FALLOS = []

COLUMNAS = ["store_id", "dept_id", "d", "cat_id", "state_id", "unidades", "dolares", "date", "year", "month", "weekday",
            "wday", "wm_yr_wk", "wm_yr_wk_anterior", "event_name_1", "event_type_1", "event_name_2", "event_type_2",
            "snap", "periodo", "mes_parcial", "semana_parcial", "cierre_tienda", "fuera_del_error", "clase_cero",
            "precio_medio_semana_anterior"]
APARTADOS = ["Fuente", "Objetivo", "Transformaciones aplicadas", "Variables generadas", "Transformaciones pendientes",
             "Cambios estructurales", "Validación", "Dataset generado", "Registro de exclusiones", "Datos personales",
             "Pendiente para el modelo", "Teoría aplicada"]
SALIDAS = ["hechos_series.parquet", "dim_producto.parquet", "dim_tienda.parquet"]

# El plan de cruces aprobado, escrito aquí con su estado (error 31): no se hereda del modelado-datos.json vivo.
PLAN = [
    {"orden": 1, "partida": "venta en filas", "se_une": "Calendario", "clave_partida": ["d"], "clave_une": ["d"],
     "cardinalidad": "N:1", "tipo_cruce": "left"},
    {"orden": 2, "partida": "venta en filas", "se_une": "precios", "clave_partida": ["item_id", "store_id", "wm_yr_wk"],
     "clave_une": ["item_id", "store_id", "wm_yr_wk"], "cardinalidad": "N:1", "tipo_cruce": "left"},
    {"orden": 3, "partida": "venta en filas", "se_une": "dim_producto", "clave_partida": ["item_id"],
     "clave_une": ["item_id"], "cardinalidad": "N:1", "tipo_cruce": "left"},
    {"orden": 4, "partida": "hechos_series", "se_une": "dim_tienda", "clave_partida": ["store_id"],
     "clave_une": ["store_id"], "cardinalidad": "N:1", "tipo_cruce": "left"},
    {"orden": 5, "partida": "hechos_series", "se_une": "Calendario", "clave_partida": ["d"], "clave_une": ["d"],
     "cardinalidad": "N:1", "tipo_cruce": "left"},
    {"orden": 6, "partida": "precios", "se_une": "dim_producto", "clave_partida": ["item_id"], "clave_une": ["item_id"],
     "cardinalidad": "N:1", "tipo_cruce": "left"},
    {"orden": 7, "partida": "hechos_series", "se_une": "precio medio del departamento por semana",
     "clave_partida": ["store_id", "dept_id", "wm_yr_wk_anterior"], "clave_une": ["store_id", "dept_id", "wm_yr_wk"],
     "cardinalidad": "N:1", "tipo_cruce": "left"},
]

REGISTRO_PRUEBA = """# Registro de transformaciones · copia de prueba

## Fichas de la corrección de datos (prueba)

### R-001 · 23/11/2026 · prueba uno

1. **Tabla y columna:** prueba.

### R-003 · 23/11/2026 · prueba tres

1. **Tabla y columna:** prueba.
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


# ── 2. Datos pequeños ──────────────────────────────────────────────────────────
def datos_base():
    """Tres tiendas (CA, TX, WI), dos departamentos de dos productos cada uno y 14 días.

    - Semanas 11148 (d_1 a d_7, sin anterior) y 11201 (d_8 a d_14), seguidas: la anterior de la 11201 es la 11148.
    - d_7 es el 25/12/2013. S_TX cierra entera el d_3 y el d_7; el d_4 vende solo D2.
    - S_CA D1, d_8: P1 vende 1 a 1,50 y P2 vende 3 a 3,50 = 12,00 dólares. Con dos semanas ningún producto lleva
      cuatro semanas de precio, así que el precio medio queda vacío en todos los días (reglas, apartado 5).
    - S_WI D1 en la construcción (d_1 a d_10): 99 unidades sin días de cierre, media 9,9, cero el d_1. S_WI D2: 100
      unidades, media 10,0, cero el d_2. En la validación (d_11 a d_14) S_WI D1 tiene media 15 y un cero el d_11.
    - S_WI P4 no tiene ningún precio (y no vende); S_WI P2 no tiene precio la 11201 (y no vende).
    """
    fechas = pd.date_range("2013-12-19", periods=14, freq="D")
    cal = pd.DataFrame({
        "d": pd.Series([f"d_{i}" for i in range(1, 15)], dtype="str"),
        "date": fechas.astype("datetime64[us]"),
        "year": fechas.year.astype("int64"), "month": fechas.month.astype("int64"),
        "weekday": pd.Series(fechas.day_name(), dtype="str"),
        "wday": pd.Series([(i % 7) + 1 for i in range(14)], dtype="int64"),
        "wm_yr_wk": pd.Series([11148] * 7 + [11201] * 7, dtype="int64"),
        "wm_yr_wk_anterior": pd.Series([pd.NA] * 7 + [11148] * 7, dtype="Int64"),
        "event_name_1": pd.Series([None] * 6 + ["Christmas"] + [None] * 7, dtype="str"),
        "event_type_1": pd.Series([None] * 6 + ["National"] + [None] * 7, dtype="str"),
        "event_name_2": pd.Series([None] * 14, dtype="str"),
        "event_type_2": pd.Series([None] * 14, dtype="str"),
        "snap_ca": pd.Series([0, 1] + [0] * 12, dtype="int64"),
        "snap_tx": pd.Series([0, 0, 1] + [0] * 5 + [1] + [0] * 5, dtype="int64"),
        "snap_wi": pd.Series([0, 0, 0, 1] + [0] * 10, dtype="int64"),
        "periodo": pd.Series(["construccion"] * 10 + ["validacion"] * 4, dtype="str"),
        "mes_parcial": pd.Series([True] * 14, dtype="bool"),
        "semana_parcial": pd.Series([False] * 14, dtype="bool"),
    })
    ceros = [0] * 14
    unidades = {
        ("S_CA", "P1"): [1] * 14, ("S_CA", "P2"): [3] * 14,
        ("S_CA", "P3"): [20] * 6 + [0] + [20] * 7, ("S_CA", "P4"): ceros,
        ("S_TX", "P1"): [20, 20, 0, 0, 20, 20, 0] + [20] * 7, ("S_TX", "P2"): ceros,
        ("S_TX", "P3"): [20, 20, 0, 20, 20, 20, 0] + [20] * 7, ("S_TX", "P4"): ceros,
        ("S_WI", "P1"): [0] + [11] * 9 + [0, 20, 20, 20], ("S_WI", "P2"): ceros,
        ("S_WI", "P3"): [12, 0, 12, 12, 12, 12, 10, 10, 10, 10, 20, 20, 20, 20], ("S_WI", "P4"): ceros,
    }
    estado = {"S_CA": "CA", "S_TX": "TX", "S_WI": "WI"}
    dept = {"P1": ("D1", "C1"), "P2": ("D1", "C1"), "P3": ("D2", "C2"), "P4": ("D2", "C2")}
    filas = []
    for (tienda, item), u in unidades.items():
        fila = {"id": f"{item}_{tienda}", "item_id": item, "dept_id": dept[item][0], "cat_id": dept[item][1],
                "store_id": tienda, "state_id": estado[tienda]}
        fila.update({f"d_{i + 1}": int(x) for i, x in enumerate(u)})
        filas.append(fila)
    venta = pd.DataFrame(filas)
    for c in ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]:
        venta[c] = venta[c].astype("str")
    for c in [f"d_{i}" for i in range(1, 15)]:
        venta[c] = venta[c].astype("int64")
    precio = {"P1": (1.00, 1.50), "P2": (3.00, 3.50), "P3": (2.00, 2.00), "P4": (5.00, 5.00)}
    filas = []
    for tienda in ["S_CA", "S_TX", "S_WI"]:
        for item, (p1, p2) in precio.items():
            for semana, p in ((11148, p1), (11201, p2)):
                if tienda == "S_WI" and (item == "P4" or (item == "P2" and semana == 11201)):
                    continue
                filas.append({"store_id": tienda, "item_id": item, "wm_yr_wk": semana, "sell_price": p})
    precios = pd.DataFrame(filas).astype({"store_id": "str", "item_id": "str", "wm_yr_wk": "int64",
                                          "sell_price": "float64"})
    return venta, precios, cal


CLASES_BASE = {"construccion": {"cierre": 4, "25_diciembre": 1, "demanda_intermitente": 1, "resto": 2},
               "validacion": {"cierre": 0, "25_diciembre": 0, "demanda_intermitente": 0, "resto": 1}}


def escribir_caso(nombre, venta, precios, cal, estado_correccion="OK", huella_venta=None, clases=None):
    """Monta la carpeta de un caso de prueba y devuelve su ruta."""
    raiz = TMP / nombre
    proc = raiz / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    (raiz / "informes").mkdir(parents=True, exist_ok=True)
    (raiz / "config" / "modelo").mkdir(parents=True, exist_ok=True)
    venta.to_parquet(proc / "venta_corregido.parquet", index=False)
    precios.to_parquet(proc / "precios_corregido.parquet", index=False)
    cal.to_parquet(proc / "calendario.parquet", index=False)
    clases = CLASES_BASE if clases is None else clases
    correccion = {
        "fecha_datos": "2015-05-22", "resultado": {"estado": estado_correccion},
        "salidas": [{"tabla": "venta", "sha256": huella_venta or huella(proc / "venta_corregido.parquet")},
                    {"tabla": "precios", "sha256": huella(proc / "precios_corregido.parquet")}],
        "clases_de_ceros": {p: {"clases": {k: {"dias_serie": v} for k, v in c.items()}} for p, c in clases.items()},
    }
    modelado = {"fecha_datos": "2015-05-22", "resultado": {"estado": "OK"}, "aprobado": {"aprobado": True},
                "calendario": {"sha256": huella(proc / "calendario.parquet")}, "plan_cruces": PLAN}
    (raiz / "informes" / "correccion-datos.json").write_text(json.dumps(correccion), encoding="utf-8")
    (raiz / "informes" / "modelado-datos.json").write_text(json.dumps(modelado), encoding="utf-8")
    (raiz / "config" / "modelo" / "registro-transformaciones.md").write_text(REGISTRO_PRUEBA,
                                                                                         encoding="utf-8")
    return raiz


def ejecutar(raiz):
    """Ejecuta el script sobre la carpeta de prueba, como proceso aparte y con -W error."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)], capture_output=True,
                          text=True, encoding="utf-8", env=entorno, timeout=300)
    ruta = raiz / "informes" / "transformacion-datos.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


def fichas_nuevas(raiz):
    """Los números de ficha del registro de la prueba que no estaban en la copia."""
    texto = (raiz / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    return [n for n in re.findall(r"^### (R-\d{3}) · ", texto, flags=re.M) if n not in ("R-001", "R-003")]


# ── 3. Casos con datos pequeños ────────────────────────────────────────────────
def fila(h, tienda, dept, d):
    """La fila de una serie y un día."""
    x = h[(h["store_id"] == tienda) & (h["dept_id"] == dept) & (h["d"] == d)]
    return x.iloc[0] if len(x) == 1 else None


def probar_base():
    """El caso que tiene que salir bien: cada regla con el dato que la distingue de su error típico."""
    venta, precios, cal = datos_base()
    raiz = escribir_caso("base", venta, precios, cal)
    rc, d, salida = ejecutar(raiz)
    comprobar(rc == 0 and d is not None and d["resultado"]["estado"] == "OK",
              f"base: el script termina en OK (código {rc}){'' if rc == 0 else ' · ' + salida[-1500:]}")
    if d is None or rc != 0:
        return
    h = pd.read_parquet(raiz / "data" / "processed" / "hechos_series.parquet")
    comprobar(list(h.columns) == COLUMNAS, "base: hechos_series tiene las 26 columnas en su orden")
    comprobar(len(h) == 3 * 2 * 14 and not h.duplicated(["store_id", "dept_id", "d"]).any(),
              f"base: 84 filas (3 tiendas × 2 departamentos × 14 días) y clave sin repetir ({len(h)})")
    # Sumas: las unidades de la venta ancha y los dólares producto a producto por su precio, contados aquí aparte
    dias = [f"d_{i}" for i in range(1, 15)]
    semana = dict(zip(cal["d"], cal["wm_yr_wk"]))
    precio = {(r.store_id, r.item_id, r.wm_yr_wk): r.sell_price for r in precios.itertuples()}
    centimos = sum(int(r[c]) * round(precio[(r["store_id"], r["item_id"], semana[c])] * 100)
                   for _, r in venta.iterrows() for c in dias if r[c] > 0)
    comprobar(int(h["unidades"].sum()) == int(venta[dias].to_numpy().sum()), "base: las unidades cuadran")
    comprobar(int(round(h["dolares"].sum() * 100)) == centimos, "base: los dólares cuadran al céntimo")
    # Dólares de cada producto por su precio, no unidades de la serie por un precio medio
    x = fila(h, "S_CA", "D1", "d_8")
    comprobar(x is not None and x["unidades"] == 4 and abs(x["dolares"] - 12.00) < 1e-9,
              f"base: S_CA D1 d_8 vale 12,00 dólares (1 × 1,50 + 3 × 3,50), no 4 × 2,5 = 10 ({None if x is None else x['dolares']})")
    # Con dos semanas ningún producto lleva cuatro semanas de precio: el precio medio queda vacío en todos los días
    # (reglas, apartado 5; la media simple y las cuatro semanas se prueban en probar_cuatro_semanas)
    vacios = h["precio_medio_semana_anterior"].isna()
    comprobar(int(vacios.sum()) == 84,
              f"base: precio medio vacío en los 84 días de serie, sin anterior o sin cuatro semanas de precio "
              f"({int(vacios.sum())})")
    # Cierre de la tienda
    tx = h[h["store_id"] == "S_TX"]
    comprobar(tx.loc[tx["d"] == "d_3", "cierre_tienda"].tolist() == [True, True],
              "base: S_TX con sus dos series a cero el d_3 da cierre_tienda verdadero en las dos")
    comprobar(tx.loc[tx["d"] == "d_4", "cierre_tienda"].tolist() == [False, False],
              "base: S_TX el d_4, con una serie que vende, da cierre_tienda falso en las dos")
    comprobar(int(h["cierre_tienda"].sum()) == 4, f"base: 4 días de serie de cierre ({int(h['cierre_tienda'].sum())})")
    # El 25 de diciembre
    comprobar(tx.loc[tx["d"] == "d_7", "clase_cero"].tolist() == ["cierre", "cierre"],
              "base: el 25 de diciembre con la tienda cerrada va a la clase cierre")
    x = fila(h, "S_CA", "D2", "d_7")
    comprobar(x is not None and x["clase_cero"] == "25_diciembre",
              "base: el 25 de diciembre con la tienda abierta y la serie a cero va a 25_diciembre")
    comprobar(bool(h.loc[h["d"] == "d_7", "fuera_del_error"].all()) and int(h["fuera_del_error"].sum()) == 8,
              f"base: fuera_del_error en los 6 días de serie del 25 de diciembre y los 2 del cierre del d_3 "
              f"({int(h['fuera_del_error'].sum())})")
    # Demanda intermitente, con la media de su periodo
    x = fila(h, "S_WI", "D1", "d_1")
    comprobar(x is not None and x["clase_cero"] == "demanda_intermitente",
              "base: la serie con 9,9 unidades de media en la construcción es demanda_intermitente")
    x = fila(h, "S_WI", "D2", "d_2")
    comprobar(x is not None and x["clase_cero"] == "resto", "base: la serie con 10 unidades de media no lo es: resto")
    x = fila(h, "S_WI", "D1", "d_11")
    comprobar(x is not None and x["clase_cero"] == "resto",
              "base: en la validación la misma serie tiene su propia media (15): resto")
    comprobar(int((h["unidades"] > 0).sum()) == int(h["clase_cero"].isna().sum()),
              "base: clase_cero vacía en todos los días con venta y solo en ellos")
    # SNAP del estado de la tienda
    snap_de = {"S_CA": "snap_ca", "S_TX": "snap_tx", "S_WI": "snap_wi"}
    esperado = [int(cal.loc[cal["d"] == r.d, snap_de[r.store_id]].iloc[0]) for r in h.itertuples()]
    comprobar(h["snap"].tolist() == esperado, "base: snap es el del estado de cada tienda")
    # Dimensiones
    dp = pd.read_parquet(raiz / "data" / "processed" / "dim_producto.parquet")
    dt = pd.read_parquet(raiz / "data" / "processed" / "dim_tienda.parquet")
    comprobar(list(dp.columns) == ["item_id", "dept_id", "cat_id"] and len(dp) == 4 and dp["item_id"].is_unique,
              "base: dim_producto con 4 productos y clave sin repetir")
    comprobar(list(dt.columns) == ["store_id", "state_id"] and len(dt) == 3 and dt["store_id"].is_unique,
              "base: dim_tienda con 3 tiendas y clave sin repetir")
    # JSON
    c = d["cifras_de_control"]
    comprobar(c["dias_sin_precio"] == 21 and c["dias_con_venta_y_sin_precio"] == 0,
              f"base: 21 días sin precio y 0 con venta y sin precio ({c['dias_sin_precio']}, {c['dias_con_venta_y_sin_precio']})")
    exc = {e["clase"]: e for e in d["exclusiones"]}
    comprobar(exc.get("productos-tienda sin ningún precio", {}).get("recuento", {}).get("productos_tienda") == 1,
              "base: 1 producto-tienda sin ningún precio en el registro de exclusiones")
    comprobar(d["fecha_datos"] == "2015-05-22", "base: fecha_datos 2015-05-22")
    particion = {k: (d.get("particion") or {}).get(k) for k in ("columna_fecha", "desarrollo", "validacion", "fuente")}
    comprobar(particion == {"columna_fecha": "date", "desarrollo": {"desde": "2011-01-29", "hasta": "2014-05-22"},
                            "validacion": {"desde": "2014-05-23", "hasta": "2015-05-22"},
                            "fuente": "reglas-negocio §5, «Fechas»"}, "base: la partición es la de las reglas, apartado 5")
    marcas = {v["columna"]: (v["informacion_posterior"], v["sale_del_objetivo"]) for v in d["variables_generadas"]}
    comprobar(marcas.get("cierre_tienda") == (True, True) and marcas.get("clase_cero") == (True, True)
              and marcas.get("fuera_del_error", (False,))[0] is True,
              f"base: cierre_tienda, clase_cero y fuera_del_error marcadas como posteriores al día ({marcas})")
    comprobar(len(d["cruces"]) == 7 and all(x["hecho"] for x in d["cruces"]), "base: los 7 cruces hechos")
    comprobar([x["filas_antes"] == x["filas_despues"] for x in d["cruces"]] == [True] * 7,
              "base: ningún cruce cambia las filas")
    comprobar(all(v["resultado"] == "pasa" for v in d["validaciones"]), "base: todas las validaciones pasan")
    # Registro: cinco fichas la primera vez, ninguna al repetir
    nuevas = fichas_nuevas(raiz)
    comprobar(nuevas == ["R-004", "R-005", "R-006", "R-007", "R-008"], f"base: el script escribe R-004 a R-008 ({nuevas})")
    registro = (raiz / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    bloque = registro[registro.find("### R-004 "):]
    comprobar(", y " not in bloque and len(re.findall(r"^\d\. \*\*", bloque, flags=re.M)) == 45,
              "base: las cinco fichas tienen sus nueve campos y ninguna «, y»")
    rc2, d2, _ = ejecutar(raiz)
    comprobar(rc2 == 0 and fichas_nuevas(raiz) == nuevas, "base: al repetir sin cambiar ninguna regla no añade fichas")
    # Informe
    texto = (raiz / "informes" / "transformacion-datos.md").read_text(encoding="utf-8")
    comprobar(re.findall(r"^## (.+)$", texto, flags=re.M) == APARTADOS,
              f"base: el informe tiene sus apartados en orden ({re.findall(r'^## (.+)$', texto, flags=re.M)})")
    comprobar(", y " not in texto, "base: el informe no une dos partes con «, y»")


def datos_cuatro_semanas():
    """Una tienda, un departamento con cuatro productos y seis semanas seguidas, con el salto de año en el código.

    - Semanas por orden: 11150, 11151, 11152, 11201, 11202 y 11203 (d_1 a d_42). La anterior de la 11201 es la 11152.
    - P1 tiene precio desde la 11150: 1,00 hasta la 11201 y 2,00 desde la 11202. Vende 5 al día.
    - P2 tiene precio desde la 11150, a 3,00. Vende 1 al día.
    - P3 entra la 11151, a 10,00: en la 11202 lleva tres semanas de precio antes, no cuatro. Vende 1 al día desde ella.
    - P4 entra la 11202, a 50,00: es la semana anterior de la 11203. Vende 1 al día desde ella.
    - La 11203 toma la 11202: cuentan P1 y P2, media simple (2 + 3) / 2 = 2,5. Con todos los productos con precio
      saldría (2 + 3 + 10 + 50) / 4 = 16,25; ponderada por unidades, (2 × 5 + 3 × 1) / 6 = 2,17.
    - Las semanas 11150 a 11202 quedan vacías: la primera no tiene anterior y en las otras ningún producto lleva cuatro
      semanas de precio en su semana anterior.
    """
    semanas = [11150, 11151, 11152, 11201, 11202, 11203]
    fechas = pd.date_range("2012-03-03", periods=42, freq="D")
    semana_dia = [w for w in semanas for _ in range(7)]
    anterior = {b: a for a, b in zip(semanas, semanas[1:])}
    vacio = pd.Series([None] * 42, dtype="str")
    cal = pd.DataFrame({
        "d": pd.Series([f"d_{i}" for i in range(1, 43)], dtype="str"),
        "date": fechas.astype("datetime64[us]"),
        "year": fechas.year.astype("int64"), "month": fechas.month.astype("int64"),
        "weekday": pd.Series(fechas.day_name(), dtype="str"),
        "wday": pd.Series([(i % 7) + 1 for i in range(42)], dtype="int64"),
        "wm_yr_wk": pd.Series(semana_dia, dtype="int64"),
        "wm_yr_wk_anterior": pd.Series([anterior.get(w, pd.NA) for w in semana_dia], dtype="Int64"),
        "event_name_1": vacio.copy(), "event_type_1": vacio.copy(),
        "event_name_2": vacio.copy(), "event_type_2": vacio.copy(),
        "snap_ca": pd.Series([0] * 42, dtype="int64"), "snap_tx": pd.Series([0] * 42, dtype="int64"),
        "snap_wi": pd.Series([0] * 42, dtype="int64"),
        "periodo": pd.Series(["construccion"] * 42, dtype="str"),
        "mes_parcial": pd.Series([True] * 42, dtype="bool"), "semana_parcial": pd.Series([False] * 42, dtype="bool"),
    })
    entra = {"P1": 0, "P2": 0, "P3": 1, "P4": 4}
    vende = {"P1": 5, "P2": 1, "P3": 1, "P4": 1}
    filas = []
    for item in ["P1", "P2", "P3", "P4"]:
        fila = {"id": f"{item}_S_CA", "item_id": item, "dept_id": "D1", "cat_id": "C1", "store_id": "S_CA",
                "state_id": "CA"}
        fila.update({f"d_{i + 1}": (vende[item] if i // 7 >= entra[item] else 0) for i in range(42)})
        filas.append(fila)
    venta = pd.DataFrame(filas)
    for c in ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]:
        venta[c] = venta[c].astype("str")
    for c in [f"d_{i}" for i in range(1, 43)]:
        venta[c] = venta[c].astype("int64")
    precio = {"P1": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0], "P2": [3.0] * 6, "P3": [10.0] * 6, "P4": [50.0] * 6}
    filas = [{"store_id": "S_CA", "item_id": item, "wm_yr_wk": w, "sell_price": precio[item][i]}
             for item in precio for i, w in enumerate(semanas) if i >= entra[item]]
    precios = pd.DataFrame(filas).astype({"store_id": "str", "item_id": "str", "wm_yr_wk": "int64",
                                          "sell_price": "float64"})
    return venta, precios, cal


def probar_cuatro_semanas():
    """En el precio medio solo cuentan los productos con precio desde cuatro semanas antes (reglas, apartado 5)."""
    venta, precios, cal = datos_cuatro_semanas()
    ceros = {p: {k: 0 for k in CLASES_BASE["construccion"]} for p in ("construccion", "validacion")}
    raiz = escribir_caso("cuatro_semanas", venta, precios, cal, clases=ceros)
    rc, d, salida = ejecutar(raiz)
    comprobar(rc == 0 and d is not None and d["resultado"]["estado"] == "OK",
              f"cuatro semanas: el script termina en OK, sin pendientes (código {rc})"
              f"{'' if rc == 0 else ' · ' + salida[-1500:]}")
    if d is None or rc != 0:
        return
    h = pd.read_parquet(raiz / "data" / "processed" / "hechos_series.parquet")
    ultima = h.loc[h["wm_yr_wk"] == 11203, "precio_medio_semana_anterior"]
    comprobar(len(ultima) == 7 and bool((ultima - 2.5).abs().lt(1e-12).all()),
              f"cuatro semanas: la 11203 toma la media simple de P1 y P2 en la 11202, 2,5; ni 16,25 con los cuatro "
              f"productos ni 2,17 ponderada ({sorted(set(ultima.round(4)))})")
    vacios = h["precio_medio_semana_anterior"].isna()
    comprobar(int(vacios.sum()) == 35 and set(h.loc[vacios, "wm_yr_wk"]) == {11150, 11151, 11152, 11201, 11202},
              f"cuatro semanas: vacío en los 35 días de las semanas 11150 a 11202 ({int(vacios.sum())})")
    exc = {e["clase"]: e for e in d["exclusiones"]}
    sin = exc.get("sin precio medio de la semana anterior", {}).get("recuento") or {}
    comprobar((sin.get("construccion") or {}).get("dias_serie") == 35,
              f"cuatro semanas: el registro de exclusiones cuenta los 35 días sin precio medio ({sin})")
    comprobar(all(v["resultado"] == "pasa" for v in d["validaciones"]), "cuatro semanas: todas las validaciones pasan")


def probar_paradas():
    """Cada regla con condición tiene un caso que TIENE que parar el script, sin guardar nada ni escribir fichas."""
    casos = []
    venta, precios, cal = datos_base()
    sin = precios[~((precios["store_id"] == "S_CA") & (precios["item_id"] == "P1") & (precios["wm_yr_wk"] == 11148))]
    casos.append(("venta_sin_precio", venta, sin.reset_index(drop=True), cal, {}, "venta_sin_precio",
                  "un día con venta y sin precio para el script"))
    venta, precios, cal = datos_base()
    repetido = pd.concat([precios, precios.iloc[[0]]], ignore_index=True)
    casos.append(("precio_repetido", venta, repetido, cal, {}, "cruce_2",
                  "un precio con la clave repetida hace crecer las filas del cruce 2 y el script para"))
    venta, precios, cal = datos_base()
    cal = cal.assign(extra=np.int64(0))
    casos.append(("columna_de_mas", venta, precios, cal, {}, "columnas_series",
                  "una columna de más en la tabla de series para el script"))
    venta, precios, cal = datos_base()
    venta.loc[venta["store_id"] == "S_TX", "state_id"] = "NY"
    casos.append(("estado_desconocido", venta, precios, cal, {}, "estado_desconocido",
                  "una tienda de un estado que no es CA, TX ni WI para el script"))
    venta, precios, cal = datos_base()
    venta.loc[0, "d_2"] = -1
    casos.append(("venta_negativa", venta, precios, cal, {}, "venta_negativa", "una venta negativa para el script"))
    venta, precios, cal = datos_base()
    precios.loc[0, "sell_price"] = 1.005
    casos.append(("precio_tres_decimales", venta, precios, cal, {}, "precio_decimales",
                  "un precio con más de dos decimales para el script antes de pasarlo a céntimos"))
    venta, precios, cal = datos_base()
    casos.append(("correccion_no_ok", venta, precios, cal, {"estado_correccion": "AVISO"}, "entrada_no_ok",
                  "con correccion-datos.json fuera de OK el script no empieza"))
    venta, precios, cal = datos_base()
    casos.append(("huella_distinta", venta, precios, cal, {"huella_venta": "0" * 64}, "huella_distinta",
                  "con la huella de la venta distinta de la de su JSON el script no empieza"))
    for nombre, venta, precios, cal, extra, codigo, texto in casos:
        raiz = escribir_caso(nombre, venta, precios, cal, **extra)
        rc, d, salida = ejecutar(raiz)
        codigos = [p["codigo"] for p in (d or {}).get("paradas", [])]
        guardadas = [s for s in SALIDAS if (raiz / "data" / "processed" / s).exists()]
        comprobar(rc != 0 and d is not None and d["resultado"]["estado"] == "PARADO" and codigo in codigos
                  and d["salidas"] == [] and guardadas == [] and fichas_nuevas(raiz) == [],
                  f"{texto} (código {rc}, paradas {codigos}, guardadas {guardadas})"
                  + ("" if d is not None else " · " + salida[-800:]))
        if nombre == "precio_repetido" and d is not None:
            c2 = next((x for x in d["cruces"] if x["orden"] == 2), None)
            comprobar(c2 is not None and not c2["hecho"] and c2["filas_despues"] > c2["filas_antes"],
                      f"precio repetido: el cruce 2 mide las filas de más y no se hace ({c2 and (c2['filas_antes'], c2['filas_despues'])})")


def probar_sin_veredictos_escritos():
    """Error 24: ninguna comprobación se escribe con su resultado puesto."""
    if not SCRIPT.exists():
        comprobar(False, "existe el script para buscar veredictos escritos")
        return
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](clave_unica|coincide|formato_igual|hecho|pasa|huerfanas_cuadran|iguales)[\"']\s*:\s*"
                         r"(True|False)\b", codigo)
    puestos += re.findall(r"[\"']resultado[\"']\s*:\s*[\"'](pasa|falla)[\"']\s*[,}]", codigo)
    comprobar(puestos == [], f"el script no escribe ninguna comprobación con su resultado puesto ({puestos})")


# ── 4. Con los datos reales (solo con --datos) ─────────────────────────────────
def cifras_de_referencia(d):
    """Las cifras de CONTROLES de la petición (clave "transformacion") salen iguales en el JSON."""
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    if "transformacion" not in ref:
        comprobar(False, "tests/cifras_de_referencia.json tiene la clave transformacion")
        return
    medido = d.get("cifras_de_control", {})
    for clave, valor in ref["transformacion"]["cifras"].items():
        comprobar(medido.get(clave) == valor, f"cifra de control {clave}: esperado {valor} · JSON {medido.get(clave)}")
    huellas = {e["ruta"].split("/")[-1]: e["sha256"] for e in d["entradas"]}
    comprobar(huellas == ref["transformacion"]["huellas"], "las huellas de entrada son las de la petición")
    comprobar({k.split("/")[-1]: v for k, v in d["huellas_despues"].items()} == ref["transformacion"]["huellas"],
              "las huellas de las entradas después del script son las de la petición")
    for s in d["salidas"]:
        comprobar(huella(RAIZ / s["ruta"]) == s["sha256"], f"la huella de {s['ruta']} es la del JSON")


def segunda_via(d):
    """Rehace desde la venta ancha, con numpy y sin melt ni merge, lo que el script calculó en filas."""
    proc = RAIZ / "data" / "processed"
    venta = pd.read_parquet(proc / "venta_corregido.parquet")
    dias = sorted([c for c in venta.columns if re.fullmatch(r"d_\d+", c)], key=lambda c: int(c[2:]))
    cal = pd.read_parquet(proc / "calendario.parquet").set_index("d").loc[dias]
    U = venta[dias].to_numpy(np.int64)
    # Precio de cada producto-tienda por semana en una matriz; cada día toma la columna de su semana
    precios = pd.read_parquet(proc / "precios_corregido.parquet")
    semanas = sorted(int(w) for w in precios["wm_yr_wk"].unique())
    col = {w: i for i, w in enumerate(semanas)}
    ancho = precios.pivot(index=["store_id", "item_id"], columns="wm_yr_wk", values="sell_price")
    ancho = ancho.reindex(pd.MultiIndex.from_arrays([venta["store_id"], venta["item_id"]]))[semanas]
    P = ancho.to_numpy(dtype="float64")
    sem_dia = np.array([col[int(w)] for w in cal["wm_yr_wk"]])
    Pd = np.rint(P[:, sem_dia] * 100)
    C = np.where(np.isnan(Pd), 0, Pd).astype(np.int64) * U
    # Suma por serie (tienda y departamento) con np.add.at, en el orden de las claves
    claves = sorted(set(zip(venta["store_id"], venta["dept_id"])))
    codigo = {k: i for i, k in enumerate(claves)}
    fila_serie = np.array([codigo[k] for k in zip(venta["store_id"], venta["dept_id"])])
    SU = np.zeros((len(claves), len(dias)), dtype=np.int64)
    SC = np.zeros_like(SU)
    np.add.at(SU, fila_serie, U)
    np.add.at(SC, fila_serie, C)
    periodo = cal["periodo"].to_numpy()
    navidad = (cal["date"].dt.month.to_numpy() == 12) & (cal["date"].dt.day.to_numpy() == 25)
    tienda = np.array([t for t, _ in claves])
    cerrada = {t: (SU[tienda == t].sum(axis=0) == 0) for t in set(tienda)}
    cierre = np.vstack([cerrada[t] for t in tienda])
    via2 = {"unidades": {}, "centimos": {}, "cierre": {}, "clase": {}}
    for p in ("construccion", "validacion"):
        m = periodo == p
        via2["unidades"].update({(k[0], k[1], p): int(SU[i, m].sum()) for i, k in enumerate(claves)})
        via2["centimos"].update({(k[0], k[1], p): int(SC[i, m].sum()) for i, k in enumerate(claves)})
        via2["cierre"][p] = int((cierre[:, m]).sum())
        cuenta = {"cierre": 0, "25_diciembre": 0, "demanda_intermitente": 0, "resto": 0}
        for i in range(len(claves)):
            abiertos = m & ~cierre[i]
            media = SU[i, abiertos].sum() / abiertos.sum() if abiertos.any() else np.inf
            cero = (SU[i] == 0) & m
            c1 = cero & cierre[i]
            c2 = cero & ~cierre[i] & navidad
            c3 = cero & ~cierre[i] & ~navidad & (media < 10)
            cuenta["cierre"] += int(c1.sum())
            cuenta["25_diciembre"] += int(c2.sum())
            cuenta["demanda_intermitente"] += int(c3.sum())
            cuenta["resto"] += int((cero & ~c1 & ~c2 & ~c3).sum())
        via2["clase"][p] = cuenta
    # Precio medio simple por serie y semana, sin dividir por cero; cada día toma el de su semana anterior. Solo cuentan
    # los precios de un producto-tienda desde cuatro semanas después de su primera semana con precio (reglas, apartado 5)
    j = np.arange(len(semanas))[None, :]
    con_precio = ~np.isnan(P)
    primera = np.where(con_precio.any(axis=1), con_precio.argmax(axis=1), len(semanas))[:, None]
    P = np.where(j >= primera + 4, P, np.nan)
    M = np.full((len(claves), len(semanas)), np.nan)
    for i in range(len(claves)):
        bloque = P[fila_serie == i]
        n = (~np.isnan(bloque)).sum(axis=0)
        s = np.nansum(bloque, axis=0)
        np.divide(s, n, out=M[i], where=n > 0)
    anterior = cal["wm_yr_wk_anterior"]
    idx_ant = np.array([-1 if pd.isna(w) else col[int(w)] for w in anterior])
    PM = np.where(idx_ant[None, :] >= 0, M[:, np.maximum(idx_ant, 0)], np.nan)
    print("segunda vía (venta ancha y numpy):", {"unidades": int(SU.sum()), "centimos": int(SC.sum()),
                                                 "cierre": via2["cierre"], "clase": via2["clase"]})
    # Vía 1: la tabla guardada por el script
    h = pd.read_parquet(proc / "hechos_series.parquet").sort_values(["store_id", "dept_id", "date"])
    h["centimos"] = np.rint(h["dolares"].to_numpy() * 100).astype(np.int64)
    g = h.groupby(["store_id", "dept_id", "periodo"])[["unidades", "centimos"]].sum()
    via1_u = {k: int(v) for k, v in g["unidades"].items()}
    via1_c = {k: int(v) for k, v in g["centimos"].items()}
    comprobar(via1_u == via2["unidades"], "las unidades por serie y periodo coinciden por las dos vías")
    comprobar(via1_c == via2["centimos"], "los dólares por serie y periodo coinciden al céntimo por las dos vías")
    via1_cierre = {p: int(x) for p, x in h.groupby("periodo")["cierre_tienda"].sum().items()}
    comprobar(via1_cierre == via2["cierre"], f"cierre_tienda por periodo coincide ({via1_cierre} · {via2['cierre']})")
    via1_clase = {p: {c: int(((h["periodo"] == p) & (h["clase_cero"] == c)).sum()) for c in via2["clase"][p]}
                  for p in via2["clase"]}
    comprobar(via1_clase == via2["clase"], f"clase_cero por periodo coincide ({via1_clase})")
    claves_h = list(zip(h["store_id"], h["dept_id"], h["d"]))
    claves_v2 = [(k[0], k[1], dd) for k in claves for dd in dias]
    comprobar(claves_h == claves_v2, "la tabla guardada tiene las series y los días en el orden de la segunda vía")
    if claves_h == claves_v2:
        v1 = h["precio_medio_semana_anterior"].to_numpy(dtype="float64")
        v2 = PM.reshape(-1)
        mismos_vacios = bool((np.isnan(v1) == np.isnan(v2)).all())
        dif = float(np.nanmax(np.abs(v1 - v2))) if mismos_vacios else None
        comprobar(mismos_vacios and dif is not None and dif < 1e-9,
                  f"el precio medio de la semana anterior coincide por las dos vías (vacíos iguales, diferencia {dif})")


def informe_real(d):
    """El informe real: sus apartados en orden y sin «, y»."""
    texto = (RAIZ / "informes" / "transformacion-datos.md").read_text(encoding="utf-8")
    comprobar(re.findall(r"^## (.+)$", texto, flags=re.M) == APARTADOS, "el informe real tiene sus apartados en orden")
    comprobar(", y " not in texto, "el informe real no une dos partes con «, y»")
    comprobar(d["fecha_datos"] == "2015-05-22" and d["resultado"]["estado"] == "OK", "el JSON real: fecha y estado OK")


# ── 5. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            probar_base()
            probar_cuatro_semanas()
            probar_paradas()
        probar_sin_veredictos_escritos()
        if "--datos" in sys.argv:
            ruta = RAIZ / "informes" / "transformacion-datos.json"
            if not ruta.exists():
                comprobar(False, "existe informes/transformacion-datos.json")
            else:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                cifras_de_referencia(datos)
                segunda_via(datos)
                informe_real(datos)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_transformacion borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
