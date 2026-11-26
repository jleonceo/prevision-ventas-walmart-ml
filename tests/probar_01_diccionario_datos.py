"""Prueba de scripts/01_diccionario_datos.py.

Sin argumentos usa solo datos pequeños escritos aquí, en tests/tmp_diccionario/, que se crea y se borra.
Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla.

Con --datos compara además el JSON con tests/cifras_de_referencia.json (programacion-del-caso §6) y hace la segunda vía (programacion-del-caso §6; diccionario-datos §9.4): rehace dos cifras del
diccionario leyendo data/raw/ con el módulo csv, sin pandas, y las compara con el JSON que dejó el script:
  - vía 1: el script, con pandas, escribe filas y nulos en config/fuentes/diccionario-datos-origen.json;
  - vía 2: esta prueba cuenta las filas de sell_prices.csv y las celdas vacías de event_name_1 en calendar.csv
    recorriendo los ficheros en bruto línea a línea.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import csv
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "01_diccionario_datos.py"
TMP = RAIZ / "tests" / "tmp_diccionario"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script sin ejecutar su __main__ (su nombre empieza por cifra, así que va por importlib)."""
    spec = importlib.util.spec_from_file_location("diccionario_datos", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Casos con datos pequeños ────────────────────────────────────────────────
def probar_lectura(m):
    """La codificación sigue el orden del método y el separador se detecta."""
    (TMP / "bom.csv").write_bytes("﻿a,b\n1,2\n".encode("utf-8"))
    (TMP / "plano.csv").write_bytes("a,b\n1,2\n".encode("utf-8"))
    (TMP / "cp1252.csv").write_bytes("a;b\nespa\xf1a;2\n".encode("latin-1"))
    cod, avisos = m.detectar_codificacion(TMP / "bom.csv")
    comprobar(cod == "utf-8-sig", "un fichero con BOM se lee como utf-8-sig")
    cod, avisos = m.detectar_codificacion(TMP / "plano.csv")
    comprobar(cod == "utf-8" and avisos == [], "un fichero utf-8 sin BOM se lee como utf-8, sin aviso")
    cod, avisos = m.detectar_codificacion(TMP / "cp1252.csv")
    comprobar(cod == "cp1252" and len(avisos) == 1, "un fichero cp1252 sale de utf-8 y deja un aviso")
    comprobar(m.detectar_separador(TMP / "cp1252.csv", "cp1252") == ";", "el separador ; se detecta")
    comprobar(m.detectar_separador(TMP / "plano.csv", "utf-8") == ",", "el separador , se detecta")


def probar_bloque_dias(m):
    """Cada columna de días se mira una a una; la que no cumple lo del bloque sale con ficha propia."""
    bueno = pd.DataFrame({"d_1": [0, 1, 2], "d_2": [3, 0, 1], "d_3": [0, 0, 5]})
    r = m.revisar_bloque_dias(bueno, ["d_1", "d_2", "d_3"])
    comprobar(r["fuera_del_bloque"] == [] and r["nombres_seguidos"] is True and r["columnas"] == 3,
              "tres columnas de días limpias forman un bloque sin excepciones")
    comprobar(r["columnas_revisadas"] == 3, "el bloque dice cuántas columnas revisó una a una")

    # El caso que TIENE que salir mal: un negativo, un vacío, un decimal, una constante y un hueco en los nombres.
    malo = pd.DataFrame({"d_1": [0, 1, 2], "d_2": [3, -1, 1], "d_3": [0, None, 5],
                         "d_4": [0.5, 1.0, 2.0], "d_6": [0, 0, 0]})
    r = m.revisar_bloque_dias(malo, ["d_1", "d_2", "d_3", "d_4", "d_6"])
    fuera = {f["columna"]: f["motivos"] for f in r["fuera_del_bloque"]}
    comprobar("d_2" in fuera and any("negativ" in x for x in fuera["d_2"]), "una venta negativa saca su columna del bloque")
    comprobar("d_3" in fuera and any("vac" in x for x in fuera["d_3"]), "un vacío saca su columna del bloque")
    comprobar("d_4" in fuera and any("entero" in x for x in fuera["d_4"]), "un decimal saca su columna del bloque")
    comprobar("d_6" in fuera and any("constante" in x for x in fuera["d_6"]), "una columna constante sale del bloque")
    comprobar("d_1" not in fuera, "la columna limpia se queda en el bloque")
    comprobar(r["nombres_seguidos"] is False, "un hueco en la numeración de los días se detecta")


def probar_categorias_raras(m):
    """Rara: menos del 2,5 % de las filas o menos de cinco apariciones."""
    s = pd.Series(["A"] * 196 + ["B"] * 4)
    raras = {x["categoria"] for x in m.categorias_raras(s, 2.5, 5)}
    comprobar(raras == {"B"}, "una categoría con 4 de 200 filas es rara y la de 196 no")
    s = pd.Series(["A"] * 50 + ["B"] * 50)
    comprobar(m.categorias_raras(s, 2.5, 5) == [], "dos categorías iguales no son raras")


def probar_clase(m):
    """La clase la manda lo peor que tenga la columna."""
    base = {"rol": "categorica", "nulos": 0, "filas": 10, "categorias_raras": [], "significado_cero": None,
            "clase_documental": "resuelto"}
    comprobar(m.clase_del_campo(base) == "resuelto", "una categórica sin nada raro es resuelto")
    comprobar(m.clase_del_campo({**base, "nulos": 10}) == "no_se_puede_saber", "una columna entera vacía no se puede saber")
    comprobar(m.clase_del_campo({**base, "categorias_raras": [{"categoria": "x"}]}) == "decision_de_negocio",
              "una categoría rara lleva la columna a decisión de negocio")
    comprobar(m.clase_del_campo({**base, "rol": "magnitud"}) == "decision_de_negocio",
              "una magnitud sin significado del cero va a decisión de negocio")
    comprobar(m.clase_del_campo({**base, "rol": "magnitud", "significado_cero": "dato válido"}) == "resuelto",
              "una magnitud con su cero documentado es resuelto")
    comprobar(m.clase_del_campo({**base, "clase_documental": "no_se_puede_saber"}) == "no_se_puede_saber",
              "la clase del texto de configuración también cuenta")


def probar_guia(m):
    """Columnas documentadas que no llegan y columnas que llegan sin documentar."""
    c = m.comparar_columnas_con_guia("t", ["a", "b", "d"], ["a", "b", "c"])
    textos = json.dumps(c, ensure_ascii=False)
    comprobar(len(c) == 2 and '"columna": "d"' in textos and '"columna": "c"' in textos,
              "sale una contradicción por la columna sin documentar y otra por la que no llega")
    comprobar(m.comparar_columnas_con_guia("t", ["a"], ["a"]) == [], "sin diferencias no hay contradicción")


def probar_json(m):
    """Un JSON no lleva NaN ni infinito: van como null."""
    limpio = m.a_json_limpio({"x": float("nan"), "y": [1.5, float("inf")], "z": 2})
    texto = json.dumps(limpio, allow_nan=False)
    comprobar(limpio["x"] is None and limpio["y"][1] is None and limpio["z"] == 2, "NaN e infinito pasan a null")
    comprobar("NaN" not in texto, "el JSON sale válido")


def probar_sin_veredictos_escritos():
    """Error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](ok|cumple|pasa|coincide|igual|valida)[\"']\s*:\s*(True|False)\b", codigo)
    comprobar(puestos == [], "el script no escribe ninguna comprobación con True o False puesto")


# ── 3. Segunda vía sobre los datos reales (solo con --datos) ────────────────────
def segunda_via():
    """Rehace filas de precios y vacíos de event_name_1 con el módulo csv y las compara con el JSON del script."""
    dic = json.loads((RAIZ / "config" / "fuentes" / "diccionario-datos-origen.json").read_text(encoding="utf-8"))
    tablas = {t["tabla"]: t for t in dic["tablas"]}
    with open(RAIZ / "data" / "raw" / "sell_prices.csv", encoding="utf-8", newline="") as f:
        filas_precios = sum(1 for _ in csv.reader(f)) - 1
    with open(RAIZ / "data" / "raw" / "calendar.csv", encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        vacios_evento = sum(1 for fila in lector if fila["event_name_1"] == "")
    nulos_json = next(c["nulos"] for c in tablas["calendario"]["campos"] if c["columna"] == "event_name_1")
    print("segunda vía · filas de precios: csv", filas_precios, "· JSON", tablas["precios"]["filas"])
    print("segunda vía · vacíos de event_name_1: csv", vacios_evento, "· JSON", nulos_json)
    comprobar(filas_precios == tablas["precios"]["filas"], "las filas de precios coinciden por las dos vías")
    comprobar(vacios_evento == nulos_json, "los vacíos de event_name_1 coinciden por las dos vías")


def cifras_de_referencia():
    """Las cifras de control de la petición (tests/cifras_de_referencia.json) salen iguales en el JSON del diccionario."""
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    dic = json.loads((RAIZ / "config" / "fuentes" / "diccionario-datos-origen.json").read_text(encoding="utf-8"))
    t = {x["tabla"]: x for x in dic["tablas"]}
    v, p, c = t["venta"], t["precios"], t["calendario"]
    campo = {(x["tabla"], f["columna"]): f for x in dic["tablas"] for f in x["campos"]}
    b, rv, rp = v["bloque_dias"], v["relaciones_medidas"], p["relaciones_medidas"]
    medido = {
        "venta.filas": v["filas"], "venta.columnas": v["columnas"],
        "venta.id_distintos": campo[("venta", "id")]["distintos"], "venta.productos": rv["productos_distintos"],
        "venta.tiendas": campo[("venta", "store_id")]["distintos"], "venta.columnas_de_dias": b["columnas_revisadas"],
        "venta.vacios_en_dias": b["nulos"], "venta.negativos_en_dias": b["negativos"],
        "venta.tipo_de_los_dias": list(b["tipos"]) == ["int64"], "venta.filas_por_departamento": rv["filas_por_departamento"],
        "precios.filas": p["filas"], "precios.columnas": p["columnas"],
        "precios.vacios": sum(f["nulos"] for f in p["campos"]), "precios.clave_unica": p["clave_unica"],
        "precios.semana_minima": campo[("precios", "wm_yr_wk")]["minimo"],
        "precios.semana_maxima": campo[("precios", "wm_yr_wk")]["maximo"],
        "precios.filas_hasta_la_semana_11416": p["por_periodo"]["hasta_la_ultima_semana_de_construccion"]["filas"],
        "precios.filas_despues_de_la_semana_11416": p["por_periodo"]["despues"]["filas"],
        "precios.productos_tienda_con_algun_precio": rp["productos_tienda_con_algun_precio"],
        "calendario.filas": c["filas"], "calendario.columnas": c["columnas"],
        "calendario.fecha_minima": campo[("calendario", "date")]["minimo"],
        "calendario.fecha_maxima": campo[("calendario", "date")]["maximo"], "calendario.d_unico": c["clave_unica"],
        "calendario.vacios": {k: f["nulos"] for (tb, k), f in campo.items() if tb == "calendario" and f["nulos"]},
        "huellas": {e["ruta"].split("/")[-1]: e["sha256"] for e in dic["entradas"]},
    }
    esperado = {f"{tabla}.{k}": val for tabla in ("venta", "precios", "calendario") for k, val in ref[tabla].items()}
    esperado["venta.tipo_de_los_dias"] = True
    esperado["huellas"] = ref["huellas"]
    for clave, valor in esperado.items():
        comprobar(medido[clave] == valor, f"cifra de control {clave}: esperado {valor} · JSON {medido[clave]}")
    comprobar(dic["huellas_despues"] == {"venta": ref["huellas"]["sales_train_evaluation.csv"],
                                         "precios": ref["huellas"]["sell_prices.csv"],
                                         "calendario": ref["huellas"]["calendar.csv"]},
              "las huellas de data/raw/ después del script son las de la petición")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_lectura(modulo)
            probar_bloque_dias(modulo)
            probar_categorias_raras(modulo)
            probar_clase(modulo)
            probar_guia(modulo)
            probar_json(modulo)
            probar_sin_veredictos_escritos()
            if "--datos" in sys.argv:
                segunda_via()
                cifras_de_referencia()
    except Exception as error:  # un fallo del script es un fallo de la prueba, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_diccionario borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
