"""Prueba de produccion/lote_prueba_final.py, con datos pequeños escritos aquí.

No lee ningún dato del caso: cada caso se monta con tablas de juguete y una copia de juguete de la parte «que_se_mide» de
informes/prueba_final.json, escrita aquí (programacion-del-caso, error 31).

Los casos, los de quien quiere romperlo incluidos (programacion-del-caso, error 35):
  1. los orígenes salen de que_se_mide: los ordinarios y las vísperas de festivo, en ese orden; sin ese apartado, para;
  2. la venta de cada origen se corta en él: ningún día posterior, aunque las columnas lleguen desordenadas;
  3. los precios llegan hasta la semana anterior al último día del horizonte más largo, por el orden de las fechas del
     calendario (el código de la semana salta al cambiar de año), y no más;
  4. la comparación con la referencia: igual da que coincide; una previsión estropeada en 1e-6, una fila que falta en el
     lote o una clave repetida dan que no; las filas del lote que la referencia no mide se cuentan aparte, sin fallar;
  5. la comparación con el lote guardado, fila a fila con la previsión sin redondear: igual coincide, estropeada no;
  6. un destino que ya tiene algo para sin escribir;
  7. ninguna comprobación del script se escribe con su resultado puesto (error 24);
  8. --origen sustituye los orígenes de que_se_mide por uno dado (petición 32): un origen cuyo horizonte más largo cabe
     justo en el calendario pasa y da una sola prueba; uno que se pasa un día del último día del calendario para; uno
     al que no llega la venta para, aunque el calendario sí llegue; una venta con las columnas desordenadas no engaña.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "produccion" / "lote_prueba_final.py"
TMP = RAIZ / "tests" / "tmp_lote_prueba_final"
FALLOS = []
CLAVES = ["prueba", "objetivo", "origen", "store_id", "dept_id", "date"]


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar(ruta, nombre):
    """Importa un fichero .py sin ejecutar su __main__."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def para(funcion, *argumentos, **nombrados):
    """El mensaje si la función para con Parada; None si no para."""
    try:
        funcion(*argumentos, **nombrados)
    except Exception as error:  # se mira el nombre de la clase: la del módulo que se prueba
        return str(error) if type(error).__name__ == "Parada" else f"otra excepción: {type(error).__name__}: {error}"
    return None


def calendario_pequeno():
    """Un calendario de 60 días desde el 20/12/2014, con semanas de Walmart que saltan al cambiar de año."""
    fechas = pd.date_range("2014-12-20", periods=60, freq="D")
    semanas, codigo, anio = [], 11446, 2014
    for i, f in enumerate(fechas):
        if i and f.weekday() == 5:   # la semana de Walmart empieza el sábado
            codigo += 1
            if f.year != anio:
                anio, codigo = f.year, 11501
        semanas.append(codigo)
    return pd.DataFrame({"d": [f"d_{i + 1}" for i in range(60)], "date": fechas.strftime("%Y-%m-%d"),
                         "wm_yr_wk": semanas})


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_origenes(m):
    """Caso 1: los orígenes salen de que_se_mide."""
    que = {"que_se_mide": {"origenes": ["2015-05-22", "2015-06-19"], "horizontes": {"unidades": 10, "dolares": 28},
                           "festivos": {"Navidad": "2015-12-24"}}}
    pruebas = m.pruebas_de_la_prueba_final(que)
    comprobar(pruebas == [("ordinaria", pd.Timestamp("2015-05-22")), ("ordinaria", pd.Timestamp("2015-06-19")),
                          ("festivo", pd.Timestamp("2015-12-24"))], f"orígenes: de que_se_mide, en orden ({pruebas})")
    mensaje = para(m.pruebas_de_la_prueba_final, {"resultado": {}})
    comprobar(mensaje is not None and "que_se_mide" in mensaje, f"orígenes: sin que_se_mide para ({mensaje})")


def probar_entradas(m):
    """Casos 2 y 3: la venta cortada en el origen y los precios hasta la semana que toca."""
    calendario = calendario_pequeno()
    dias = [f"d_{i}" for i in range(1, 61)]
    venta = pd.DataFrame({"id": ["A"], "item_id": ["A"], "store_id": ["S"]} | {d: [1] for d in reversed(dias)})
    semanas = sorted(calendario["wm_yr_wk"].unique(), key=lambda w: calendario.loc[calendario["wm_yr_wk"] == w].index[0])
    precios = pd.DataFrame({"store_id": "S", "item_id": "A", "wm_yr_wk": semanas, "sell_price": 1.0})
    carpeta = TMP / "entradas"
    origen = pd.Timestamp("2014-12-27")
    rutas = m.armar_entradas(origen, venta, precios, calendario, 10, carpeta)
    cortada = pd.read_csv(rutas["venta"], encoding="utf-8")
    fecha_de = dict(zip(calendario["d"], pd.to_datetime(calendario["date"])))
    ultimos = [fecha_de[c] for c in cortada.columns if c.startswith("d_")]
    comprobar(max(ultimos) == origen and len(ultimos) == 8, f"entradas: la venta acaba en el origen ({max(ultimos)}, "
                                                            f"{len(ultimos)} días)")
    llegan = pd.read_csv(rutas["precios"], encoding="utf-8")
    ultimo_dia = origen + pd.Timedelta(10, "D")                       # 06/01/2015, semana 11501
    semana_ultimo = int(calendario.loc[pd.to_datetime(calendario["date"]) == ultimo_dia, "wm_yr_wk"].iloc[0])
    anterior = semanas[semanas.index(semana_ultimo) - 1]
    comprobar(semana_ultimo == 11501 and anterior == 11447, f"entradas: el calendario de juguete salta de año "
                                                            f"({semana_ultimo}, {anterior})")
    comprobar(llegan["wm_yr_wk"].tolist() == semanas[:semanas.index(anterior) + 1],
              f"entradas: los precios llegan hasta la semana anterior al último día, por las fechas "
              f"({llegan['wm_yr_wk'].tolist()})")


def lote_y_referencia():
    """Un lote de juguete (con un objetivo que la referencia no mide) y su referencia."""
    base = pd.DataFrame({"prueba": "ordinaria", "objetivo": "unidades", "origen": pd.Timestamp("2015-05-22"),
                         "store_id": "S", "dept_id": ["D1", "D2"], "date": pd.Timestamp("2015-05-23"),
                         "prevision": [3.0, 4.0], "prevision_sin_redondear": [3.2, 3.7]})
    sobra = base.assign(prueba="festivo", objetivo="dolares", prevision=[10.5, 11.5],
                        prevision_sin_redondear=[10.5, 11.5])
    lote = pd.concat([base, sobra], ignore_index=True)
    referencia = base[CLAVES].assign(variante="reentrenado", modelo=[3.0, 4.0])
    otra = referencia.assign(variante="tal_como_esta", modelo=[9.0, 9.0])
    return lote, pd.concat([referencia, otra], ignore_index=True)


def probar_comparar(m):
    """Casos 4 y 5: la comparación con la referencia y con el lote guardado."""
    lote, referencia = lote_y_referencia()
    r = m.comparar_con_referencia(lote, referencia, "reentrenado", 1e-12)
    comprobar(r["coincide"] is True and r["filas"] == 2 and r["solo_en_el_lote"] == 2 and r["diferencia_maxima"] == 0.0,
              f"referencia: igual coincide y cuenta aparte lo que no mide ({r})")
    estropeado = lote.copy()
    estropeado.loc[0, "prevision"] += 1e-6
    r = m.comparar_con_referencia(estropeado, referencia, "reentrenado", 1e-12)
    comprobar(r["coincide"] is False and r["filas_por_encima_de_la_tolerancia"] == 1,
              f"referencia: una previsión estropeada no coincide ({r})")
    r = m.comparar_con_referencia(lote.drop(index=1), referencia, "reentrenado", 1e-12)
    comprobar(r["coincide"] is False and r["solo_en_la_referencia"] == 1, f"referencia: falta una fila ({r})")
    repetido = pd.concat([lote, lote.iloc[[0]]], ignore_index=True)
    mensaje = para(m.comparar_con_referencia, repetido, referencia, "reentrenado", 1e-12)
    comprobar(mensaje is not None, f"referencia: una clave repetida para ({mensaje})")
    r = m.comparar_con_lote(lote, lote.copy(), 1e-12)
    comprobar(r["coincide"] is True and r["filas"] == 4, f"lote guardado: igual coincide ({r})")
    otro = lote.copy()
    otro.loc[3, "prevision_sin_redondear"] += 1e-6
    r = m.comparar_con_lote(lote, otro, 1e-12)
    comprobar(r["coincide"] is False, f"lote guardado: estropeado no coincide ({r})")


def probar_destino(m):
    """Caso 6: un destino con algo dentro para."""
    destino = TMP / "destino"
    (destino / "2015-05-22").mkdir(parents=True, exist_ok=True)
    mensaje = para(m.comprobar_destino, destino)
    comprobar(mensaje is not None and "destino" in mensaje, f"destino: con algo dentro para ({mensaje})")
    comprobar(para(m.comprobar_destino, TMP / "vacio_que_no_existe") is None, "destino: uno que no existe pasa")


def probar_origen_dado(m):
    """Caso 8: el origen dado con --origen, con el calendario de juguete (del 20/12/2014 al 17/02/2015)."""
    calendario = calendario_pequeno()
    hasta_40 = [f"d_{i}" for i in range(1, 41)]                     # la venta llega al 28/01/2015
    venta = pd.DataFrame({"id": ["A"], "item_id": ["A"], "store_id": ["S"]} | {d: [1] for d in reversed(hasta_40)})
    venta_entera = pd.DataFrame({"id": ["A"], "item_id": ["A"], "store_id": ["S"]}
                                | {f"d_{i}": [1] for i in range(60, 0, -1)})
    justo = pd.Timestamp("2015-02-07")                               # 07/02 + 10 días = 17/02, el último del calendario
    pruebas = None
    mensaje = para(m.pruebas_con_origen, justo, calendario, venta_entera, 10)
    if mensaje is None:
        pruebas = m.pruebas_con_origen(justo, calendario, venta_entera, 10)
    comprobar(mensaje is None and pruebas == [("proximos_dias", justo)],
              f"origen dado: cabe justo en el calendario y da una sola prueba ({mensaje}, {pruebas})")
    mensaje = para(m.pruebas_con_origen, justo + pd.Timedelta(1, "D"), calendario, venta_entera, 10)
    comprobar(mensaje is not None and "calendario" in mensaje,
              f"origen dado: un día más allá del calendario para ({mensaje})")
    mensaje = para(m.pruebas_con_origen, pd.Timestamp("2015-01-29"), calendario, venta, 10)
    comprobar(mensaje is not None and "venta" in mensaje, f"origen dado: la venta no llega hasta él y para ({mensaje})")
    mensaje = para(m.pruebas_con_origen, pd.Timestamp("2015-01-28"), calendario, venta, 10)
    comprobar(mensaje is None, f"origen dado: la venta llega justo hasta él y pasa ({mensaje})")


def probar_sin_validaciones_escritas():
    """Caso 7: ninguna comprobación se escribe con su resultado puesto (error 24)."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    escritas = re.findall(r'"[a-z_]+":\s*(?:True|False)\b', codigo)
    comprobar(not escritas, f"sin comprobaciones escritas con su resultado ({escritas})")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar(SCRIPT, "lote_prueba_final_prueba")
            probar_origenes(modulo)
            probar_entradas(modulo)
            probar_comparar(modulo)
            probar_destino(modulo)
            probar_origen_dado(modulo)
            probar_sin_validaciones_escritas()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_lote_prueba_final borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
