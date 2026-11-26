"""Prueba de scripts/20_prueba_final.py, con datos pequeños escritos aquí.

No lee ningún dato del caso: monta en tests/tmp_prueba_final/ un lote de juguete con la forma que deja
produccion/ejecutar.py (una carpeta por origen con previsiones.parquet y resumen.json) y una venta real de juguete de
cuatro series (dos tiendas y dos departamentos), y llama a las funciones del script. Lo único del caso que mira es la
huella de informes/validacion.json, para comprobar que importar el script no ejecuta nada.

Los casos, uno que tiene que fallar por cada parada y un control que no debe disparar (programacion-del-caso, §2):
  1. control: el lote limpio se mide sin parar, con el veredicto de reglas, apartado 7 (orígenes que gana, ventaja, intervalo),
     y el mismo lote con las filas en otro orden da exactamente lo mismo;
  2. una previsión que usa un día posterior a su origen (el resumen dice que la venta llegaba hasta el día siguiente):
     para; y un día previsto que no va detrás del origen, también;
  3. falta un origen entero o falta un día de una serie: para;
  4. una fila sin previsión o con la previsión negativa: para;
  5. la previsión que no casa por serie y fecha con la venta real (una tienda con otro nombre, que una unión por
     posición dejaría pasar): para;
  6. la medida cambia si se cambia la venta real de un día;
  7. la venta real por serie, de una venta y unos precios con la forma de data/raw/: suma unidades y céntimos, marca
     fuera del error el 25 de diciembre y el cierre de una tienda;
  8. el script no escribe ninguna comprobación con su resultado puesto (error 24) e importarlo no ejecuta nada.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "20_prueba_final.py"
TMP = RAIZ / "tests" / "tmp_prueba_final"
FALLOS = []
SERIES = [("CA_1", "FOODS_1"), ("CA_1", "HOBBIES_1"), ("TX_1", "FOODS_1"), ("TX_1", "HOBBIES_1")]
ORIGENES = [pd.Timestamp("2015-05-01"), pd.Timestamp("2015-05-08"), pd.Timestamp("2015-05-15")]
HORIZONTES = {"unidades": 3, "dolares": 5}
PADRES = {"categoria": {"FOODS_1": "FOODS", "HOBBIES_1": "HOBBIES"}, "estado": {"CA_1": "CA", "TX_1": "TX"}}


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    spec = importlib.util.spec_from_file_location("prueba_final_20", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def venta_real():
    """La venta real de juguete: cuatro series de 92 días con su ritmo semanal y un ruido fijo."""
    rng = np.random.default_rng(7)
    dias = pd.date_range("2015-03-01", "2015-05-31", freq="D")
    filas = []
    for i, (tienda, dept) in enumerate(SERIES):
        base = 40 + 15 * i
        ritmo = np.array([1.0, 0.9, 0.85, 0.9, 1.1, 1.3, 1.25])
        unidades = np.rint(base * ritmo[dias.dayofweek] + rng.normal(0, 3, len(dias))).clip(0)
        filas.append(pd.DataFrame({"store_id": tienda, "dept_id": dept, "date": dias, "unidades": unidades,
                                   "dolares": np.round(unidades * 2.5, 2), "fuera_del_error": False}))
    return pd.concat(filas, ignore_index=True)


def lote(real, carpeta, desviacion=0.01):
    """El lote de juguete: una carpeta por origen con la forma de ejecutar.py; la previsión es lo real con un error
    pequeño, para que gane a las reglas."""
    rng = np.random.default_rng(11)
    for origen in ORIGENES:
        partes = []
        for objetivo, h in HORIZONTES.items():
            dias = [origen + pd.Timedelta(k, "D") for k in range(1, h + 1)]
            de = real[real["date"].isin(dias)].copy()
            previsto = de[objetivo].to_numpy() * (1 + rng.normal(0, desviacion, len(de)))
            partes.append(pd.DataFrame({
                "objetivo": objetivo, "origen": origen, "store_id": de["store_id"].to_numpy(),
                "dept_id": de["dept_id"].to_numpy(), "date": de["date"].to_numpy(),
                "h": (de["date"] - origen).dt.days.to_numpy(), "prevision": np.round(previsto),
                "prevision_sin_redondear": previsto, "motivo": None, "aviso": None}))
        sub = carpeta / f"{origen:%Y-%m-%d}"
        sub.mkdir(parents=True, exist_ok=True)
        pd.concat(partes, ignore_index=True).to_parquet(sub / "previsiones.parquet", index=False)
        (sub / "resumen.json").write_text(json.dumps({"origen": f"{origen:%Y-%m-%d}",
                                                      "fecha_datos": f"{origen:%Y-%m-%d}"}), encoding="utf-8")
    return carpeta


def medir(m, carpeta, real):
    """Lee el lote y mide las unidades en los orígenes ordinarios, sin suavizado; devuelve el bloque del objetivo."""
    pruebas = [{"prueba": "ordinaria", "origen": o, "objetivos": list(HORIZONTES)} for o in ORIGENES]
    leido = m.leer_lote(carpeta, pruebas, HORIZONTES, SERIES)
    tabla = m.armar_objetivo(leido, real, "unidades", ORIGENES, HORIZONTES["unidades"], "ordinaria",
                             con_suavizado=False)
    return m.medir_ordinaria(tabla, "unidades", ORIGENES, SERIES, PADRES)


def para(m, carpeta, real, texto):
    """Verdadero si medir el lote para con Parada y el mensaje trae el texto."""
    try:
        medir(m, carpeta, real)
    except m.Parada as parada:
        return texto in str(parada), str(parada)
    return False, "no paró"


def copia(nombre):
    """Una carpeta de lote nueva, limpia."""
    carpeta = TMP / nombre
    shutil.rmtree(carpeta, ignore_errors=True)
    return lote(venta_real(), carpeta)


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_control(m):
    """Caso 1: el lote limpio se mide sin parar; con otro orden, lo mismo."""
    real = venta_real()
    carpeta = copia("control")
    r = medir(m, carpeta, real)
    v = r["veredicto"]
    comprobar(v["de"] == 3 and v["minimo"] == 3 and isinstance(v["origenes_que_gana"], int)
              and v["intervalo"]["bajo"] <= v["ventaja"] <= v["intervalo"]["alto"] and v["veredicto"] == "gana",
              f"control: mide sin parar y el modelo casi perfecto gana ({v['origenes_que_gana']}, {v['ventaja']:.2f})")
    comprobar(r["control"]["ventaja_otro_camino"] is True and r["control"]["intervalo_por_entidad"] is True,
              "control: la ventaja coincide por otro camino y el intervalo remuestrea series enteras")
    # El mismo lote con las filas barajadas: la unión va por serie y fecha, no por posición
    for sub in carpeta.iterdir():
        p = pd.read_parquet(sub / "previsiones.parquet")
        p.sample(frac=1.0, random_state=3).to_parquet(sub / "previsiones.parquet", index=False)
    r2 = medir(m, carpeta, real)
    comprobar(r2["veredicto"]["ventaja"] == v["ventaja"] and r2["errores"]["todas"] == r["errores"]["todas"],
              "control: con las filas del lote en otro orden sale exactamente lo mismo")


def probar_posterior(m):
    """Caso 2: una previsión que usa un día posterior a su origen para."""
    real = venta_real()
    carpeta = copia("posterior")
    sub = carpeta / f"{ORIGENES[1]:%Y-%m-%d}"
    resumen = json.loads((sub / "resumen.json").read_text(encoding="utf-8"))
    resumen["fecha_datos"] = f"{ORIGENES[1] + pd.Timedelta(1, 'D'):%Y-%m-%d}"
    (sub / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
    bien, texto = para(m, carpeta, real, "posterior a su origen")
    comprobar(bien, f"la venta llega más allá del origen: para ({texto})")
    carpeta = copia("dia_antes")
    sub = carpeta / f"{ORIGENES[0]:%Y-%m-%d}"
    p = pd.read_parquet(sub / "previsiones.parquet")
    p.loc[0, "date"] = ORIGENES[0]
    p.to_parquet(sub / "previsiones.parquet", index=False)
    bien, texto = para(m, carpeta, real, "no va detrás de su origen")
    comprobar(bien, f"un día previsto que no va detrás del origen: para ({texto})")


def probar_falta(m):
    """Caso 3: falta un origen o un día."""
    real = venta_real()
    carpeta = copia("falta_origen")
    shutil.rmtree(carpeta / f"{ORIGENES[2]:%Y-%m-%d}")
    bien, texto = para(m, carpeta, real, "falta el origen")
    comprobar(bien, f"falta un origen: para ({texto})")
    carpeta = copia("falta_dia")
    sub = carpeta / f"{ORIGENES[1]:%Y-%m-%d}"
    p = pd.read_parquet(sub / "previsiones.parquet")
    p.drop(index=p.index[(p["objetivo"] == "unidades")][4]).to_parquet(sub / "previsiones.parquet", index=False)
    bien, texto = para(m, carpeta, real, "no trae")
    comprobar(bien, f"falta un día de una serie: para ({texto})")


def probar_vacia_o_negativa(m):
    """Caso 4: una fila sin previsión o negativa."""
    real = venta_real()
    for nombre, valor, texto_esperado in (("vacia", np.nan, "sin previsión"), ("negativa", -2.0, "negativa")):
        carpeta = copia(nombre)
        sub = carpeta / f"{ORIGENES[0]:%Y-%m-%d}"
        p = pd.read_parquet(sub / "previsiones.parquet")
        p.loc[3, "prevision_sin_redondear"] = valor
        p.to_parquet(sub / "previsiones.parquet", index=False)
        bien, texto = para(m, carpeta, real, texto_esperado)
        comprobar(bien, f"una fila {nombre}: para ({texto})")


def probar_no_casa(m):
    """Caso 5: la previsión que no casa por serie y fecha con la venta real para."""
    real = venta_real()
    carpeta = copia("no_casa")
    otra = real.copy()
    otra["store_id"] = otra["store_id"].replace({"TX_1": "TX_9"})
    bien, texto = para(m, carpeta, otra, "serie y fecha")
    comprobar(bien, f"una tienda con otro nombre en la venta real: para, no se une por posición ({texto})")


def probar_cambia_con_la_venta(m):
    """Caso 6: la medida sale distinta si cambia la venta real de un día."""
    real = venta_real()
    carpeta = copia("cambia")
    antes = medir(m, carpeta, real)
    otra = real.copy()
    fila = otra.index[(otra["store_id"] == "CA_1") & (otra["dept_id"] == "FOODS_1")
                      & (otra["date"] == ORIGENES[0] + pd.Timedelta(2, "D"))][0]
    otra.loc[fila, "unidades"] = otra.loc[fila, "unidades"] + 30
    despues = medir(m, carpeta, otra)
    comprobar(antes["veredicto"]["error_modelo"] != despues["veredicto"]["error_modelo"],
              f"cambiar la venta real de un día cambia la medida ({antes['veredicto']['error_modelo']:.4f} y "
              f"{despues['veredicto']['error_modelo']:.4f})")


def probar_venta_real(m):
    """Caso 7: la venta real por serie de una venta con la forma de data/raw/."""
    calendario = pd.DataFrame({"date": ["2015-12-24", "2015-12-25", "2015-12-26"], "wm_yr_wk": [11547, 11547, 11548],
                               "d": ["d_1", "d_2", "d_3"]})
    venta = pd.DataFrame({"id": ["a", "b", "c"], "item_id": ["FOODS_1_001", "FOODS_1_002", "HOBBIES_1_001"],
                          "dept_id": ["FOODS_1", "FOODS_1", "HOBBIES_1"], "cat_id": ["FOODS", "FOODS", "HOBBIES"],
                          "store_id": ["CA_1", "CA_1", "CA_1"], "state_id": ["CA", "CA", "CA"],
                          "d_1": [2, 1, 3], "d_2": [0, 0, 1], "d_3": [0, 0, 0]})
    precios = pd.DataFrame({"store_id": ["CA_1"] * 4, "item_id": ["FOODS_1_001", "FOODS_1_002", "HOBBIES_1_001",
                                                                  "FOODS_1_001"],
                            "wm_yr_wk": [11547, 11547, 11547, 11548], "sell_price": [1.25, 2.10, 3.33, 1.25]})
    t = m.venta_real_por_serie(venta, precios, calendario).set_index(["dept_id", "date"])
    f1 = t.loc[("FOODS_1", pd.Timestamp("2015-12-24"))]
    comprobar(f1["unidades"] == 3 and abs(f1["dolares"] - 4.60) < 1e-9,
              f"venta real: suma unidades y céntimos por serie ({f1['unidades']}, {f1['dolares']})")
    comprobar(bool(t.loc[("HOBBIES_1", pd.Timestamp("2015-12-25")), "fuera_del_error"])
              and not bool(t.loc[("FOODS_1", pd.Timestamp("2015-12-24")), "fuera_del_error"]),
              "venta real: el 25 de diciembre queda fuera del error aunque la tienda venda")
    comprobar(bool(t.loc[("FOODS_1", pd.Timestamp("2015-12-26")), "fuera_del_error"])
              and bool(t.loc[("FOODS_1", pd.Timestamp("2015-12-26")), "cierre_tienda"]),
              "venta real: el día con la tienda entera a cero es un cierre y queda fuera del error")
    venta.loc[0, "d_3"] = 4
    precios = precios.iloc[:3]
    try:
        m.venta_real_por_serie(venta, precios, calendario)
        comprobar(False, "venta real: un día con venta y sin precio para")
    except m.Parada:
        comprobar(True, "venta real: un día con venta y sin precio para")


def probar_codigo(huella_antes):
    """Caso 8: sin comprobaciones escritas con su resultado y sin ejecutar nada al importar."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    # puerta_de_juan es el estado de la salida, que empieza en False, no una comprobación
    puestos = [x for x in re.findall(r"[\"']([a-z_]+)[\"']\s*:\s*(?:True|False)\b", codigo) if x != "puerta_de_juan"]
    comprobar(puestos == [], f"el script no escribe ninguna comprobación con su resultado puesto ({puestos})")
    ruta = RAIZ / "informes" / "validacion.json"
    comprobar(hashlib.sha256(ruta.read_bytes()).hexdigest() == huella_antes and "if __name__ == \"__main__\":" in codigo,
              "importar el script no ejecuta nada: informes/validacion.json no cambia")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            huella = hashlib.sha256((RAIZ / "informes" / "validacion.json").read_bytes()).hexdigest()
            modulo = cargar_script()
            probar_control(modulo)
            probar_posterior(modulo)
            probar_falta(modulo)
            probar_vacia_o_negativa(modulo)
            probar_no_casa(modulo)
            probar_cambia_con_la_venta(modulo)
            probar_venta_real(modulo)
            probar_codigo(huella)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_prueba_final borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
