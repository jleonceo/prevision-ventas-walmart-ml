"""Prueba de scripts/03_correccion_datos.py.

Sin argumentos usa solo datos pequeños escritos aquí; lo que necesita escribir va a tests/tmp_correccion/, que se crea y
se borra. Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla.

Con --datos compara además informes/correccion-datos.json con la clave "correccion" de tests/cifras_de_referencia.json
(programacion-del-caso §6) y hace una segunda vía:
  - vía 1: el script lee data/raw/ con pandas (antes) y relee con pyarrow los Parquet que deja (después);
  - vía 2: esta prueba recorre data/raw/ en bruto con el módulo csv, sin pandas: unidades por periodo, suma de precios
    con Decimal, días SNAP y la clase de cada día a cero de las 70 series, con bucles de Python; y relee los Parquet
    con pandas para contar filas, columnas, nombres y tipos.
También comprueba que el informe Markdown tiene los 8 apartados de la plantilla en su orden, que cada cifra suya está en
el JSON y que el registro de transformaciones conserva T-001 y T-002 y tiene una sola vez cada ficha de la corrección.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import csv
import importlib.util
import json
import re
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "03_correccion_datos.py"
TMP = RAIZ / "tests" / "tmp_correccion"
FALLOS = []

APARTADOS = ["Fuente", "Correcciones aplicadas", "Decisiones del responsable", "Elementos mantenidos sin cambios",
             "Decisiones pendientes", "Validación", "Datos personales", "Límites"]

# Copia pequeña del fichero de decisiones del proyecto (correccion-datos §3). Lleva escrito el estado que se prueba:
# las cuestiones decididas (programacion-del-caso §2 y error 31).
DECISIONES_DE_PRUEBA = {
    "origen": "petición 07", "decidido_por": "el responsable del caso", "fecha": "2026-11-23",
    "decisiones": [
        {"pendiente": "PC-01", "decision": "son precios reales y se usan como están", "nota": None},
        {"pendiente": "PC-05", "decision": "son cambios reales y la serie se usa entera",
         "nota": "Lo demás lo fijan los planteamientos"},
        {"pendiente": "PC-06", "decision": "son cambios reales y la serie se usa entera",
         "nota": "Lo demás lo fijan los planteamientos"}],
    "sin_cambios": [
        {"problemas": ["C-01"], "pendientes": [], "motivo": "pasar la venta a filas es reestructurar."},
        {"problemas": ["C-05", "C-06", "C-07"], "pendientes": [], "motivo": "el vacío es «sin evento»."},
        {"problemas": ["C-12"], "pendientes": ["PC-01"], "motivo": "los precios bajos pesan poco."},
        {"problemas": ["C-16", "C-17"], "pendientes": ["PC-05", "PC-06"], "motivo": "los saltos son cambios reales."}],
}

PENDIENTES_DE_PRUEBA = [
    {"id": "PC-01", "tabla": "precios", "columna": "sell_price",
     "opciones": ["son precios reales y se usan como están", "son errores"], "problema": "C-12"},
    {"id": "PC-05", "tabla": "venta", "columna": "unidades por serie",
     "opciones": ["son cambios reales y la serie se usa entera", "se marca"], "problema": "C-16"},
    {"id": "PC-06", "tabla": "venta", "columna": "unidades por serie",
     "opciones": ["son cambios reales y la serie se usa entera", "se marca"], "problema": "C-17"},
]


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script sin ejecutar su __main__ (su nombre empieza por cifra, así que va por importlib)."""
    spec = importlib.util.spec_from_file_location("correccion_datos", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Casos con datos pequeños ────────────────────────────────────────────────
def probar_nombres(m):
    """Solo cambian los nombres que no siguen la forma; dos que acaban igual son una colisión."""
    mapeo, colisiones = m.mapeo_nombres(["date", "snap_CA", "snap_TX", "d_1", "wm_yr_wk"])
    comprobar(mapeo == {"snap_CA": "snap_ca", "snap_TX": "snap_tx"} and colisiones == [],
              "cambian solo snap_CA y snap_TX; date, d_1 y wm_yr_wk se quedan")
    mapeo, colisiones = m.mapeo_nombres(["Snap CA", "snap_ca", "x"])
    comprobar(len(colisiones) == 1 and colisiones[0]["nombre"] == "snap_ca",
              "«Snap CA» y «snap_ca» acaban igual: es una colisión (el caso que tiene que saltar)")


def probar_fecha(m):
    """La fecha se lee con su formato; lo que no se lee se cuenta y la conversión no se da por buena."""
    r = m.convertir_fecha(pd.Series(["2011-01-29", "2012-02-29", "2016-06-19"], dtype="str"), "%Y-%m-%d")
    comprobar(r["no_convierten"] == 0 and r["vacias"] == 0 and str(r["serie"].dt.strftime("%Y-%m-%d").tolist())
              == "['2011-01-29', '2012-02-29', '2016-06-19']", "tres fechas año-mes-día se leen y dicen el mismo día")
    r = m.convertir_fecha(pd.Series(["2011-01-29", "29/01/2011", "2013-02-30"], dtype="str"), "%Y-%m-%d")
    comprobar(r["no_convierten"] == 2, "un día-mes-año y un 30 de febrero no se leen y se cuentan (el caso que falla)")


def probar_tipos(m):
    """Cada columna, con el tipo de su rol; un tipo distinto se detecta."""
    df = pd.DataFrame({"id": pd.Series(["a", "b"], dtype="str"), "n": [1, 2], "p": [1.5, 2.0],
                       "f": pd.to_datetime(["2011-01-01", "2011-01-02"], format="%Y-%m-%d")})
    esperados = {"id": "texto", "n": "entero", "p": "decimal", "f": "fecha"}
    comprobar(m.comprobar_tipos(df, esperados) == [], "texto, entero, decimal y fecha se reconocen")
    df["n"] = df["n"].astype("float64")
    malos = m.comprobar_tipos(df, esperados)
    comprobar(len(malos) == 1 and malos[0]["columna"] == "n" and malos[0]["leido"] == "decimal",
              "un entero leído como decimal se detecta (el caso que tiene que saltar)")


def probar_valores_iguales(m):
    """Ninguna fila ni valor cambia: el nombre nuevo y la fecha se deshacen y se compara todo."""
    antes = {"cal": pd.DataFrame({"date": pd.Series(["2011-01-29", "2011-01-30"], dtype="str"), "snap_CA": [0, 1],
                                  "ev": pd.Series([None, "X"], dtype="str")})}
    despues = {"cal": antes["cal"].rename(columns={"snap_CA": "snap_ca"})}
    despues["cal"]["date"] = pd.to_datetime(despues["cal"]["date"], format="%Y-%m-%d")
    fechas = {"cal": ("date", "%Y-%m-%d")}
    comprobar(m.valores_iguales(antes, despues, {"cal": {"snap_CA": "snap_ca"}}, fechas) == [],
              "cambiar el nombre y pasar la fecha a fecha no cambia ningún valor")
    roto = {"cal": despues["cal"].copy()}
    roto["cal"].loc[1, "snap_ca"] = 0
    roto["cal"].loc[0, "date"] = pd.Timestamp("2011-01-28")
    diferencias = m.valores_iguales(antes, roto, {"cal": {"snap_CA": "snap_ca"}}, fechas)
    comprobar(sorted(x["columna"] for x in diferencias) == ["date", "snap_CA"],
              "un valor cambiado y una fecha que dice otro día se detectan (el caso que tiene que saltar)")
    corto = {"cal": despues["cal"].iloc[:1]}
    comprobar(any(x["columna"] == "filas" for x in m.valores_iguales(antes, corto, {"cal": {"snap_CA": "snap_ca"}}, fechas)),
              "una fila perdida se detecta")


def probar_ceros(m):
    """La precedencia de las cuatro clases y el umbral de la demanda intermitente, con un caso calculado a mano."""
    fechas = np.array(["2012-12-24", "2012-12-25", "2012-12-26", "2012-12-27", "2012-12-28"])
    S = np.array([[5, 0, 0, 20, 20],     # A1: media sin el cierre 11,25; el 12-26 a cero es resto
                  [13, 0, 12, 0, 15],    # A2: media sin el cierre 10,0, justo en el umbral; el 12-27 es resto
                  [0, 0, 1, 0, 2],       # B1: media 0,6, intermitente; su 25 de diciembre va a esa clase
                  [30, 4, 40, 50, 0]])   # B2: media 24,8; el 12-28 a cero es resto
    r = m.clasificar_ceros(S, np.array(["A", "A", "B", "B"]), ["A 1", "A 2", "B 1", "B 2"], fechas, 10)
    c = r["clases"]
    comprobar(c["cierre"]["dias_serie"] == 2 and c["cierre"]["dias_de_tienda"] == 1,
              "la tienda A entera a cero el 25 de diciembre es cierre, no 25 de diciembre (precedencia)")
    comprobar(c["25_diciembre"]["dias_serie"] == 1 and c["25_diciembre"]["lista"] == [{"serie": "B 1", "fecha": "2012-12-25"}],
              "el 25 de diciembre de B 1 sin cierre de su tienda va a su clase antes que a la intermitente")
    comprobar(c["demanda_intermitente"]["dias_serie"] == 2 and c["demanda_intermitente"]["series"] == 1
              and [x["serie"] for x in c["demanda_intermitente"]["lista"]] == ["B 1"],
              "solo B 1 es intermitente: A 2, con media de 10 justos, no lo es")
    comprobar(c["resto"]["dias_serie"] == 3 and c["resto"]["lista"] == [
        {"serie": "A 1", "fecha": "2012-12-26"}, {"serie": "A 2", "fecha": "2012-12-27"}, {"serie": "B 2", "fecha": "2012-12-28"}],
        "el resto sale con su serie y su fecha")
    comprobar(r["dias_serie_a_cero"] == 8 and r["partes_suman_el_total"] is True, "las cuatro clases suman los 8 ceros")
    medias = {x["serie"]: x["media"] for x in r["medias"]}
    comprobar(medias == {"A 1": 11.25, "A 2": 10.0, "B 1": 0.6, "B 2": 24.8}, "la media no cuenta los días de cierre")


def probar_decisiones(m):
    """Las decisiones y los motivos se leen del fichero de decisiones del proyecto, no de un prompt; una opción que no
    se ofreció hace saltar la comprobación."""
    comprobar(getattr(m, "DECISIONES", None) == RAIZ / "config" / "modelo" / "decisiones-correccion.json",
              "el script lee las decisiones de config/modelo/decisiones-correccion.json")
    codigo = SCRIPT.read_text(encoding="utf-8")
    comprobar("PETICIÓN" not in codigo and not hasattr(m, "leer_sin_cambios"),
              "el script ya no lee ni interpreta el texto de la petición (el caso que salía mal)")
    TMP.mkdir(parents=True, exist_ok=True)
    ruta = TMP / "decisiones.json"
    ruta.write_text(json.dumps(DECISIONES_DE_PRUEBA, ensure_ascii=False), encoding="utf-8")
    decisiones, motivos = m.leer_fichero_decisiones(ruta)
    roto = json.loads(json.dumps(DECISIONES_DE_PRUEBA))
    del roto["decisiones"][0]["decision"]
    ruta.write_text(json.dumps(roto, ensure_ascii=False), encoding="utf-8")
    try:
        m.leer_fichero_decisiones(ruta)
        salta = False
    except ValueError:
        salta = True
    comprobar(salta, "una decisión sin su opción en el fichero para la lectura (el caso que tiene que saltar)")
    comprobar([(x["pendiente"], x["decision"]) for x in decisiones] == [
        ("PC-01", "son precios reales y se usan como están"),
        ("PC-05", "son cambios reales y la serie se usa entera"),
        ("PC-06", "son cambios reales y la serie se usa entera")], "se leen las tres decisiones, literales")
    comprobar(decisiones[1]["nota"] == "Lo demás lo fijan los planteamientos", "la frase que sigue a la decisión va a su nota")
    comprobar(m.comprobar_decisiones(decisiones, PENDIENTES_DE_PRUEBA) == [], "las tres casan con las opciones ofrecidas")
    mala = json.loads(json.dumps(decisiones))
    mala[0]["decision"] = "son precios reales"
    comprobar(len(m.comprobar_decisiones(mala, PENDIENTES_DE_PRUEBA)) == 1,
              "una decisión que no copia la opción literal se rechaza (el caso que tiene que saltar)")
    comprobar(len(m.comprobar_decisiones(decisiones[:2], PENDIENTES_DE_PRUEBA)) == 1, "un pendiente sin respuesta se detecta")
    comprobar(len(m.comprobar_decisiones(decisiones + decisiones[:1], PENDIENTES_DE_PRUEBA)) == 1,
              "dos decisiones sobre el mismo pendiente se detectan")
    comprobar([x["problemas"] for x in motivos] == [["C-01"], ["C-05", "C-06", "C-07"], ["C-12"], ["C-16", "C-17"]]
              and motivos[3]["pendientes"] == ["PC-05", "PC-06"] and motivos[0]["motivo"] == "pasar la venta a filas es reestructurar.",
              "los motivos se leen con sus problemas y sus cuestiones")


def probar_cobertura(m):
    """Cada problema de la calidad va una sola vez a correcciones o a sin cambios."""
    problemas = ["C-01", "C-02", "C-03"]
    comprobar(m.cobertura(problemas, ["C-03"], [{"problemas": ["C-01", "C-02"]}]) == {"faltan": [], "repetidos": [], "sobran": []},
              "tres problemas, uno corregido y dos sin cambios: cobertura completa")
    r = m.cobertura(problemas, ["C-03"], [{"problemas": ["C-01", "C-03", "C-09"]}])
    comprobar(r == {"faltan": ["C-02"], "repetidos": ["C-03"], "sobran": ["C-09"]},
              "un problema sin motivo, uno repetido y uno que no existe se detectan (el caso que tiene que saltar)")


def probar_datos_personales(m):
    """Un correo o un documento en claro en una columna de texto se detecta, sin mostrar el valor."""
    limpio = {"t": pd.DataFrame({"a": pd.Series(["HOBBIES_1_003", "CA_1", "NBAFinalsEnd"], dtype="str")})}
    comprobar(m.datos_personales(limpio) == [], "códigos de producto, tienda y evento no son datos personales")
    sucio = {"t": pd.DataFrame({"a": pd.Series(["x", "ana@correo.es", "12345678Z"], dtype="str")})}
    r = m.datos_personales(sucio)
    comprobar(len(r) == 1 and r[0]["filas"] == 2 and "valor" not in r[0], "un correo y un DNI se cuentan sin mostrarlos")


def probar_validacion(m):
    """Las comprobaciones paran con ERROR; un resultado roto TIENE que saltar."""
    bueno = m.resultado_minimo_de_prueba()
    comprobar(m.validar(bueno) == [], "un resultado completo pasa la validación")
    roto = json.loads(json.dumps(bueno))
    roto["huellas_despues"]["data/raw/a.csv"] = "otra"
    roto["sumas_control"][0]["despues"] = 1.0
    roto["cobertura"]["faltan"] = ["C-02"]
    roto["diferencias_de_valores"] = [{"tabla": "t", "columna": "c"}]
    fallos = m.validar(roto)
    comprobar(len(fallos) == 4, f"una huella, una suma, un problema y un valor rotos dan cuatro fallos ({len(fallos)})")
    comprobar(m.estado_y_riesgo([], [], []) == ("OK", "bajo"), "sin fallos ni paradas ni pendientes: OK")
    comprobar(m.estado_y_riesgo([], [], [{"id": "P-01"}]) == ("AVISO", "medio"), "con pendientes: AVISO")
    comprobar(m.estado_y_riesgo([], [{"motivo": "x"}], [])[0] == "PARADO", "una parada es PARADO")
    comprobar(m.estado_y_riesgo([{"comprobacion": "x"}], [], [])[0] == "ERROR", "una validación que falla es ERROR")


def probar_sumas_parquet(m):
    """La segunda vía del script relee los Parquet con pyarrow y suma unidades por periodo, precios y SNAP."""
    TMP.mkdir(parents=True, exist_ok=True)
    venta = pd.DataFrame({"id": pd.Series(["a", "b"], dtype="str"), "d_1": [1, 2], "d_2": [3, 0], "d_3": [5, 7]})
    precios = pd.DataFrame({"sell_price": [0.1, 0.2, 2.97]})
    cal = pd.DataFrame({"date": pd.to_datetime(["2011-01-01", "2011-01-02", "2011-01-03"], format="%Y-%m-%d"),
                        "d": pd.Series(["d_1", "d_2", "d_3"], dtype="str"), "snap_ca": [1, 0, 1], "snap_tx": [0, 0, 0],
                        "snap_wi": [1, 1, 1]})
    rutas = {"venta": TMP / "v.parquet", "precios": TMP / "p.parquet", "calendario": TMP / "c.parquet"}
    venta.to_parquet(rutas["venta"], index=False)
    precios.to_parquet(rutas["precios"], index=False)
    cal.to_parquet(rutas["calendario"], index=False)
    r = m.sumas_desde_parquet(rutas, {"uno": ("2011-01-01", "2011-01-02"), "dos": ("2011-01-03", "2011-01-03")},
                              {"CA": "snap_ca", "TX": "snap_tx", "WI": "snap_wi"})
    comprobar(r["unidades"] == {"total": 18, "uno": 6, "dos": 12}, "unidades por periodo: 18, 6 y 12")
    comprobar(r["suma_sell_price"] == 3.27 and r["dias_snap"] == {"CA": 2, "TX": 0, "WI": 3},
              "la suma de precios al céntimo, 3,27, y los días SNAP por estado")
    comprobar(r["filas"] == {"venta": 2, "precios": 3, "calendario": 3} and r["columnas"]["venta"] == 4,
              "filas y columnas leídas del Parquet")


def probar_registro(m):
    """Las fichas se añaden debajo de lo que hay, sin tocarlo, y una segunda ejecución no las repite."""
    TMP.mkdir(parents=True, exist_ok=True)
    ruta = TMP / "registro.md"
    original = "# Registro\n\n| Nº | Qué |\n|---|---|\n| T-001 | algo |\n"
    ruta.write_text(original, encoding="utf-8")
    fichas = [("R-001", "### R-001 · uno\n\n1. **Tabla y columna:** t.\n"), ("R-002", "### R-002 · dos\n\n1. x\n")]
    comprobar(m.anadir_fichas(ruta, fichas, "## Fichas") == ["R-001", "R-002"], "se añaden las dos fichas")
    texto = ruta.read_text(encoding="utf-8")
    comprobar(texto.startswith(original) and texto.count("### R-001 ") == 1, "lo que había queda igual y la ficha va debajo")
    comprobar(m.anadir_fichas(ruta, fichas, "## Fichas") == [] and ruta.read_text(encoding="utf-8") == texto,
              "una segunda ejecución no repite ninguna ficha")


def probar_salidas(m):
    """El JSON sale sin NaN y el Markdown tiene los 8 apartados de la plantilla en su orden."""
    limpio = m.a_json_limpio({"x": float("nan"), "y": [1.5, float("inf")], "z": np.int64(2)})
    comprobar(limpio["x"] is None and limpio["y"][1] is None and limpio["z"] == 2, "NaN e infinito pasan a null")
    texto = m.generar_md(m.resultado_minimo_de_prueba())
    comprobar(re.findall(r"^## (.+)$", texto, flags=re.M) == APARTADOS, "el informe de prueba tiene los 8 apartados en su orden")
    for _, ficha in m.fichas_registro(m.resultado_minimo_de_prueba()):
        comprobar(len(re.findall(r"^\d\. \*\*", ficha, flags=re.M)) == 9, f"la ficha {ficha.splitlines()[0][:12]} tiene nueve campos")


def probar_sin_veredictos_escritos():
    """Error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](ok|cumple|pasa|coincide|igual|valida|completitud|consistencia|utilidad|datos_personales|"
                         r"partes_suman_el_total|huella_igual)[\"']\s*:\s*(True|False|[\"']pasa[\"'])", codigo)
    comprobar(puestos == [], f"el script no escribe ninguna comprobación con su resultado puesto ({puestos})")


def probar_cifras_del_informe():
    """La comprobación «cada cifra del informe está en el JSON» tiene que poder dar rojo."""
    del_json = numeros_del_json({"a": 1234, "b": "vale 5,6 dólares", "c": 0.123456}, set())
    comprobar(numeros("hay 1.234 y 5,6") <= del_json, "1.234 y 5,6 se reconocen como cifras del JSON")
    comprobar(not numeros("hay 1.235") <= del_json, "una cifra que no está en el JSON se detecta (el caso que tiene que fallar)")


def probar_bloque_del_registro():
    """Error 31: el control del registro mira solo las fichas de la corrección, no las que añaden los pasos siguientes.

    El registro de prueba lleva escrito el estado que se comprueba: las tres fichas de la corrección y, debajo, una
    sección de otro paso con una «, y» y campos de más, como la que escribe la transformación.
    """
    if "bloque_de_la_correccion" not in globals():
        comprobar(False, "existe bloque_de_la_correccion para acotar el control del registro")
        return
    fichas = "".join(f"### {n} · x\n\n1. **a:** b.\n2. **c:** d.\n" for n in ("R-001", "R-002", "R-003"))
    otro_paso = "\n## Fichas de la transformación de datos\n\n### R-004 · y\n\n1. **a:** uno, y dos.\n2. **c:** d.\n"
    registro = "# Registro\n\n## Fichas de la corrección\n\n" + fichas + otro_paso
    bloque = bloque_de_la_correccion(registro)
    comprobar("R-004" not in bloque and ", y " not in bloque and len(re.findall(r"^\d\. \*\*", bloque, flags=re.M)) == 6,
              "la sección de otro paso queda fuera del control de la corrección")
    con_coma = registro.replace("### R-002 · x\n\n1. **a:** b.", "### R-002 · x\n\n1. **a:** uno, y dos.")
    comprobar(", y " in bloque_de_la_correccion(con_coma),
              "una «, y» dentro de una ficha de la corrección se sigue viendo (el caso que tiene que fallar)")
    comprobar(bloque_de_la_correccion(fichas).count("### R-") == 3, "sin sección después, el bloque llega al final")


# ── 3. Con los datos reales (solo con --datos) ─────────────────────────────────
def numeros(texto):
    """Números de un texto escrito a la española (punto de miles, coma decimal), como floats."""
    return {float(t.replace(".", "").replace(",", ".")) for t in re.findall(r"\d+(?:\.\d{3})*(?:,\d+)?", texto)}


def numeros_del_json(obj, acumulado):
    """Todos los números del JSON: los valores numéricos y los que van escritos dentro de los textos y las claves."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            numeros_del_json(k, acumulado)
            numeros_del_json(v, acumulado)
    elif isinstance(obj, list):
        for v in obj:
            numeros_del_json(v, acumulado)
    elif isinstance(obj, bool) or obj is None:
        return acumulado
    elif isinstance(obj, (int, float)):
        acumulado.add(float(obj))
        acumulado.add(float(round(obj, 2)))
    elif isinstance(obj, str):
        acumulado |= numeros(obj)
        acumulado |= {float(x) for x in re.findall(r"\d+\.\d+", obj)}
    return acumulado


def cifras_de_referencia(d):
    """Las cifras de control de la petición (clave "correccion" de tests/cifras_de_referencia.json) salen iguales."""
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    if "correccion" not in ref:
        comprobar(False, "tests/cifras_de_referencia.json tiene la clave correccion")
        return
    medido = d["cifras_de_control"]
    for clave, valor in ref["correccion"]["cifras"].items():
        comprobar(medido.get(clave) == valor, f"cifra de control {clave}: esperado {valor} · JSON {medido.get(clave)}")
    huellas = {e["ruta"].split("/")[-1]: e["sha256"] for e in d["entradas"]}
    comprobar(huellas == ref["huellas"], "las huellas de entrada son las de la petición")
    comprobar({k.split("/")[-1]: v for k, v in d["huellas_despues"].items()} == ref["huellas"],
              "las huellas de data/raw/ después del script son las de la petición")


def contenido_del_json(d):
    """Los 29 problemas, cada uno una vez; las seis cuestiones decididas; el estado y las sumas de control."""
    calidad = json.loads((RAIZ / "informes" / "calidad-datos.json").read_text(encoding="utf-8"))
    ids = [p["id"] for p in calidad["problemas"]]
    vistos = [c["problema_calidad"] for c in d["correcciones"]] + [s["problema_calidad"] for s in d["sin_cambios"]]
    comprobar(sorted(vistos) == sorted(ids) and len(vistos) == len(set(vistos)) == 29,
              f"los 29 problemas de la calidad, cada uno una vez ({len(vistos)})")
    comprobar(sorted(c["problema_calidad"] for c in d["correcciones"]) == ["C-03", "C-04"], "las correcciones son C-03 y C-04")
    pcs = sorted(x["pendiente"] for x in d["decisiones_usuario"])
    comprobar(pcs == [f"PC-0{i}" for i in range(1, 7)], "PC-01 a PC-06 están en decisiones_usuario")
    opciones = {p["id"]: p["opciones"] for p in calidad["pendientes"]}
    comprobar(all(x["decision"] in opciones[x["pendiente"]]
                  and x["fuente"] == "config/modelo/decisiones-correccion.json"
                  for x in d["decisiones_usuario"]), "cada decisión es una opción ofrecida, con su fuente")
    fichero = json.loads((RAIZ / "config" / "modelo" / "decisiones-correccion.json").read_text(encoding="utf-8"))
    comprobar([(x["pendiente"], x["decision"]) for x in d["decisiones_usuario"]]
              == [(x["pendiente"], x["decision"]) for x in fichero["decisiones"]]
              and sorted(s["problema_calidad"] for s in d["sin_cambios"])
              == sorted(p for x in fichero["sin_cambios"] for p in x["problemas"]),
              "el JSON de la corrección dice lo mismo que el fichero de decisiones")
    comprobar(not any(p.get("id", "").startswith("PC-") for p in d["pendientes"]), "ninguna PC queda en pendientes")
    comprobar(all(s["coincide"] is True for s in d["sumas_control"]), "todas las sumas de control coinciden")
    comprobar(d["resultado"]["estado"] == "OK" and d["fecha_datos"] == "2015-05-22", "estado OK y fecha_datos 2015-05-22")
    comprobar(d["va_a_modelo"] is True and d["diferencias_de_valores"] == [], "va_a_modelo y ningún valor cambiado")
    comprobar([(n["antes"], n["despues"]) for n in d["nombres"]] == [("snap_CA", "snap_ca"), ("snap_TX", "snap_tx"),
                                                                       ("snap_WI", "snap_wi")], "el mapeo de nombres, entero")


def segunda_via(d):
    """Rehace con el módulo csv, sin pandas, las unidades, los precios, el SNAP y las clases de los ceros."""
    raw = RAIZ / "data" / "raw"
    c = d["cifras_de_control"]
    with open(raw / "calendar.csv", encoding="utf-8", newline="") as f:
        calendario = list(csv.DictReader(f))
    fecha_de = {fila["d"]: fila["date"] for fila in calendario}
    snap = {e: sum(int(fila[f"snap_{e}"]) for fila in calendario) for e in ("CA", "TX", "WI")}
    total_precio = Decimal("0")
    with open(raw / "sell_prices.csv", encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            total_precio += Decimal(fila["sell_price"])
    series = {}
    with open(raw / "sales_train_evaluation.csv", encoding="utf-8", newline="") as f:
        lector = csv.reader(f)
        cabecera = next(lector)
        i_dept, i_tienda = cabecera.index("dept_id"), cabecera.index("store_id")
        dias = [i for i, nombre in enumerate(cabecera) if nombre.startswith("d_")]
        fechas = [fecha_de[cabecera[i]] for i in dias]
        for fila in lector:
            clave = (fila[i_tienda], fila[i_dept])
            acumulado = series.setdefault(clave, [0] * len(dias))
            for k, i in enumerate(dias):
                acumulado[k] += int(fila[i])
    periodos = {p: (v["desde"], v["hasta"]) for p, v in d["periodos"].items()}
    unidades = {"total": sum(sum(v) for v in series.values())}
    clases = {}
    for p, (desde, hasta) in periodos.items():
        idx = [k for k, f in enumerate(fechas) if desde <= f <= hasta]
        unidades[p] = sum(v[k] for v in series.values() for k in idx)
        tiendas = sorted({t for t, _ in series})
        cerrada = {(t, k) for t in tiendas for k in idx if all(series[(t, dp)][k] == 0 for (tt, dp) in series if tt == t)}
        cuenta = {"cierre": 0, "25_diciembre": 0, "demanda_intermitente": 0, "resto": 0}
        for (t, dp), v in sorted(series.items()):
            abiertos = [v[k] for k in idx if (t, k) not in cerrada]
            intermitente = sum(abiertos) / len(abiertos) < 10
            for k in idx:
                if v[k] != 0:
                    continue
                if (t, k) in cerrada:
                    cuenta["cierre"] += 1
                elif fechas[k][5:] == "12-25":
                    cuenta["25_diciembre"] += 1
                elif intermitente:
                    cuenta["demanda_intermitente"] += 1
                else:
                    cuenta["resto"] += 1
        clases[p] = cuenta
    print("segunda vía · unidades: csv", unidades, "· JSON", {k: c[f"unidades_{k}_despues"] for k in unidades})
    print("segunda vía · suma de precios: Decimal", total_precio, "· JSON", c["suma_sell_price_despues"])
    print("segunda vía · días SNAP: csv", snap, "· JSON", c["dias_snap_despues"])
    print("segunda vía · clases de ceros: csv", clases, "· JSON", c["clases_de_ceros"])
    comprobar(all(unidades[k] == c[f"unidades_{k}_despues"] == c[f"unidades_{k}_antes"] for k in unidades),
              "las unidades coinciden por las dos vías, antes y después")
    comprobar(Decimal(str(c["suma_sell_price_despues"])) == total_precio.quantize(Decimal("0.01"))
              and c["suma_sell_price_antes"] == c["suma_sell_price_despues"], "la suma de precios coincide al céntimo por las dos vías")
    comprobar(snap == c["dias_snap_despues"] == c["dias_snap_antes"], "los días SNAP coinciden por las dos vías")
    comprobar(clases == c["clases_de_ceros"], "las clases de los ceros coinciden por las dos vías")


def parquet_con_pandas():
    """Los Parquet, releídos con pandas: filas y columnas del origen, tres nombres nuevos y la fecha como fecha."""
    raw = RAIZ / "data" / "raw"
    proc = RAIZ / "data" / "processed"
    pares = {"venta_corregido.parquet": "sales_train_evaluation.csv", "precios_corregido.parquet": "sell_prices.csv",
             "calendario_corregido.parquet": "calendar.csv"}
    for salida, entrada in pares.items():
        with open(raw / entrada, encoding="utf-8", newline="") as f:
            lector = csv.reader(f)
            cabecera = next(lector)
            filas = sum(1 for _ in lector)
        df = pd.read_parquet(proc / salida)
        cambiados = [(a, b) for a, b in zip(cabecera, df.columns) if a != b]
        comprobar(df.shape == (filas, len(cabecera)), f"{salida}: {df.shape} igual a {entrada}: ({filas}, {len(cabecera)})")
        esperado = [("snap_CA", "snap_ca"), ("snap_TX", "snap_tx"), ("snap_WI", "snap_wi")] if entrada == "calendar.csv" else []
        comprobar(cambiados == esperado, f"{salida}: solo cambian los nombres esperados ({cambiados})")
        if entrada == "calendar.csv":
            comprobar(pd.api.types.is_datetime64_any_dtype(df["date"]) and df["date"].isna().sum() == 0,
                      "la fecha del calendario es fecha y no tiene vacíos")


def bloque_de_la_correccion(registro):
    """Las fichas de la corrección: desde «### R-001» hasta el siguiente título de sección «## », o hasta el final.

    Las fichas que escriben los pasos siguientes van en su propia sección y no son de esta prueba (error 31).
    """
    inicio = registro.find("### R-001 ")
    fin = registro.find("\n## ", inicio)
    return registro[inicio:] if fin == -1 else registro[inicio:fin]


def informe_y_registro(d):
    """El informe: 8 apartados, cifras del JSON, sin «, y». El registro: T-001 y T-002 intactas, cada ficha una vez."""
    texto = (RAIZ / "informes" / "correccion-datos.md").read_text(encoding="utf-8")
    comprobar(re.findall(r"^## (.+)$", texto, flags=re.M) == APARTADOS, "el informe real tiene los 8 apartados en su orden")
    fuera = sorted(n for n in numeros(texto) if n not in numeros_del_json(d, set()))
    comprobar(fuera == [], f"cada cifra del informe está en el JSON (fuera: {fuera[:10]})")
    comprobar(", y " not in texto, "el informe no une dos partes con «, y»")
    registro = (RAIZ / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    comprobar(registro.startswith("# Registro de transformaciones · caso 69") and registro.count("| T-001 |") == 1
              and registro.count("| T-002 |") == 1, "el registro conserva T-001 y T-002 arriba")
    for ficha in ("R-001", "R-002", "R-003"):
        comprobar(registro.count(f"### {ficha} ") == 1, f"la ficha {ficha} está una sola vez")
    bloque = bloque_de_la_correccion(registro)
    comprobar(", y " not in bloque and len(re.findall(r"^\d\. \*\*", bloque, flags=re.M)) == 27,
              "las tres fichas tienen sus nueve campos y ninguna «, y»")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_nombres(modulo)
            probar_fecha(modulo)
            probar_tipos(modulo)
            probar_valores_iguales(modulo)
            probar_ceros(modulo)
            probar_decisiones(modulo)
            probar_cobertura(modulo)
            probar_datos_personales(modulo)
            probar_validacion(modulo)
            probar_sumas_parquet(modulo)
            probar_registro(modulo)
            probar_salidas(modulo)
            probar_sin_veredictos_escritos()
            probar_cifras_del_informe()
            probar_bloque_del_registro()
            if "--datos" in sys.argv:
                datos = json.loads((RAIZ / "informes" / "correccion-datos.json").read_text(encoding="utf-8"))
                cifras_de_referencia(datos)
                contenido_del_json(datos)
                segunda_via(datos)
                parquet_con_pandas()
                informe_y_registro(datos)
    except Exception as error:  # un fallo del script es un fallo de la prueba, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_correccion borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
