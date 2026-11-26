"""Prueba de scripts/02_calidad_datos.py.

Sin argumentos usa solo datos pequeños escritos aquí; lo que necesita escribir va a tests/tmp_calidad/, que se crea y se
borra. Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla.

Con --datos compara además informes/calidad-datos.json con la clave "calidad" de tests/cifras_de_referencia.json
(programacion-del-caso §6) y hace una segunda vía:
  - vía 1: el script, con pandas, escribe sus cifras en informes/calidad-datos.json;
  - vía 2: esta prueba recorre data/raw/ en bruto con el módulo csv, sin pandas, y cuenta los precios por debajo de
    0,5 dólares hasta la semana 11416 y después, y las unidades de cada 25 de diciembre sumando las celdas de la venta.
También comprueba que el informe Markdown tiene los 19 apartados de la plantilla en su orden y que cada cifra suya está
en el JSON.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import csv
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "02_calidad_datos.py"
TMP = RAIZ / "tests" / "tmp_calidad"
FALLOS = []

APARTADOS = ["Fuente analizada", "Resumen", "Inspección general", "Estructura", "Tipos y formatos", "Valores ausentes",
             "Duplicados", "Claves y granularidad", "Categóricas y texto", "Numéricas y outliers", "Fechas",
             "Reglas lógicas e integridad", "Cruces entre tablas", "Reglas candidatas para aprobar",
             "Resumen de problemas detectados", "Posibles acciones", "Parámetros usados", "Datos personales",
             "Límites de esta revisión"]


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script sin ejecutar su __main__ (su nombre empieza por cifra, así que va por importlib)."""
    spec = importlib.util.spec_from_file_location("calidad_datos", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Casos con datos pequeños ────────────────────────────────────────────────
def probar_saltos_de_nivel(m):
    """La medida D1: ventanas de 91 días, 80 con dato, el 25 de diciembre sin dato, razón 1,5."""
    serie = np.r_[np.full(200, 10.0), np.full(200, 20.0)]
    plana = np.full(400, 10.0)
    r = m.mayor_salto_nivel(np.vstack([serie, plana]), np.zeros(400, dtype=bool))
    comprobar(int(r.loc[0, "dia"]) == 201 and abs(r.loc[0, "razon"] - 2.0) < 1e-9 and bool(r.loc[0, "salto"]),
              "una serie que pasa de 10 a 20 el día 201 sale con salto de razón 2 ese día")
    comprobar(not bool(r.loc[1, "salto"]), "una serie plana no sale con salto")
    bajada = np.r_[np.full(200, 30.0), np.full(200, 18.0)]
    r = m.mayor_salto_nivel(bajada[None, :], np.zeros(400, dtype=bool))
    comprobar(bool(r.loc[0, "salto"]) and r.loc[0, "razon"] <= 1 / 1.5, "una bajada a 0,6 veces es salto")
    # Con más de 11 días sin dato en cada ventana no hay 80 con dato: no se puede medir y no sale salto.
    sin_dato = np.zeros(400, dtype=bool)
    sin_dato[np.arange(0, 400, 7)] = True
    sin_dato[np.arange(3, 400, 7)] = True
    r = m.mayor_salto_nivel(serie[None, :], sin_dato)
    comprobar(not bool(r.loc[0, "salto"]) and r.loc[0, "razon"] is None,
              "sin 80 días con dato en las ventanas no hay medida")
    # Ninguna ventana toma días del otro periodo: un cambio justo en la frontera no se ve en ninguno de los dos.
    frontera = np.r_[np.full(150, 10.0), np.full(150, 30.0)]
    mascaras = {"a": np.r_[np.ones(150, bool), np.zeros(150, bool)], "b": np.r_[np.zeros(150, bool), np.ones(150, bool)]}
    por = m.saltos_por_periodo(frontera[None, :], np.zeros(300, dtype=bool), mascaras)
    comprobar(not bool(por["a"].loc[0, "salto"]) and not bool(por["b"].loc[0, "salto"]),
              "un cambio en la frontera entre periodos no se mide con días de los dos")
    juntos = m.mayor_salto_nivel(frontera[None, :], np.zeros(300, dtype=bool))
    comprobar(bool(juntos.loc[0, "salto"]), "el mismo cambio sí se ve si los dos periodos van juntos (control del caso anterior)")


def probar_cierres_y_rachas(m):
    """Un cierre es la tienda entera a cero; la racha más larga de ceros cuenta días seguidos."""
    tienda = np.array([[5, 0, 3, 0], [2, 0, 0, 1]])        # dos departamentos de una tienda, cuatro días
    comprobar(m.cierres_de_tienda(tienda.sum(axis=0)[None, :]).tolist() == [[False, True, False, False]],
              "solo el día con los dos departamentos a cero es cierre")
    comprobar(m.racha_mas_larga(np.array([0, 1, 1, 0, 1, 1, 1, 0], bool)) == 3, "la racha más larga es de 3")
    comprobar(m.racha_mas_larga(np.zeros(5, bool)) == 0, "sin ceros la racha es 0")


def probar_precios(m):
    """Semana con venta y sin precio, huecos del precio y subidas de más del doble."""
    venta_semana = np.array([[0, 3, 2, 0], [1, 0, 0, 0]])
    precio = np.array([[np.nan, 1.0, 1.0, 2.5], [np.nan, 4.0, np.nan, 4.0]])
    comprobar(m.semanas_con_venta_sin_precio(venta_semana, precio).sum() == 1,
              "la semana con 1 unidad y sin precio se cuenta (el caso que para el trabajo)")
    h = m.huecos_de_precio(precio)
    comprobar(h["semanas_que_faltan"] == 1 and h["con_precio"] == 2 and h["no_llegan_al_final"] == 0,
              "un hueco entre la primera y la última semana con precio se cuenta")
    comprobar(int(m.subidas_de_precio(precio, 2.0).sum()) == 1, "pasar de 1,0 a 2,5 es más del doble; 2,0 no lo sería")
    comprobar(int(m.subidas_de_precio(np.array([[1.0, 2.0]]), 2.0).sum()) == 0, "pasar justo al doble no cuenta")


def probar_atipicos_y_colas(m):
    """Rango intercuartílico y z robusto, contrastados con un caso calculado a mano; colas y escala."""
    x = np.array([1, 2, 2, 3, 3, 3, 4, 4, 5, 40], dtype=float)
    # A mano: Q1 2,25, Q3 4, IQR 1,75, límite alto 6,625: solo el 40. Mediana 3, MAD 1: z del 40 = 0,6745·37 = 24,96.
    a = m.atipicos(x, 1.5, 3.5, 0.6745)
    comprobar(a["iqr"] == 1 and a["z_robusto"] == 1 and a["los_dos"] == 1, "el 40 lo marcan los dos métodos")
    comprobar(abs(a["q1"] - 2.25) < 1e-9 and abs(a["mad"] - 1.0) < 1e-9, "Q1 y MAD salen como a mano")
    z = m.atipicos(np.array([0, 0, 0, 0, 0, 0, 0, 9], float), 1.5, 3.5, 0.6745)
    comprobar(z["z_robusto"] is None and z["iqr"] is None and z["dispersion_cero"] == ["iqr", "z_robusto"],
              "con dispersión cero no se marca ningún atípico y se registra")
    c = m.colas(np.array([1, 1, 2, 9, 50]), 2)
    comprobar(c["bajos"] == [{"valor": 1, "filas": 2}, {"valor": 2, "filas": 1}] and c["altos"][0] == {"valor": 50, "filas": 1}
              and c["mayor_salto"] == {"desde": 9, "hasta": 50}, "las colas y el mayor salto salen bien")
    e = m.escala(np.array([1.0, 3.0, 4500.0, 3900.0]))
    comprobar(e["salto"] is True and e["cifras"] == {"1": 2, "4": 2}, "cifras 1 y 4 sin 2 ni 3: salto de escala")
    e = m.escala(np.array([0.5, 12.0, 340.0]))
    comprobar(e["salto"] is False, "cifras 1, 2 y 3 seguidas no son salto")


def probar_reparto(m):
    """Los cuatro veredictos del reparto de vacíos por segmento."""
    nulo = np.r_[np.ones(20, bool), np.zeros(80, bool), np.zeros(100, bool)]
    seg = np.r_[np.full(100, "A"), np.full(100, "B")]
    r = m.reparto(nulo, {"g": seg})
    comprobar(r["veredicto"] == "concentrados" and r["global_pct"] == 10.0, "20 % en A frente a 10 % global: concentrados")
    nulo = np.r_[np.ones(10, bool), np.zeros(90, bool), np.ones(10, bool), np.zeros(90, bool)]
    comprobar(m.reparto(nulo, {"g": seg})["veredicto"] == "repartidos", "10 % en los dos: repartidos")
    comprobar(m.reparto(np.zeros(200, bool), {"g": seg})["veredicto"] == "sin_nulos", "sin vacíos: sin_nulos")
    comprobar(m.reparto(np.r_[True, np.zeros(19, bool)], {"g": np.array(["A"] * 10 + ["B"] * 10)})["veredicto"]
              == "no_se_puede_saber", "segmentos de menos de 30 filas: no se puede saber")


def probar_reglas(m):
    """SNAP por día del mes, nombres de evento con más de un tipo y nombres normalizados."""
    dia = np.array([1, 2, 1, 2, 1, 2])
    comprobar(m.snap_que_cambia(dia, np.array([1, 0, 1, 0, 1, 0])) == 0, "un SNAP fijo por día del mes no incumple")
    comprobar(m.snap_que_cambia(dia, np.array([1, 0, 1, 0, 0, 0])) == 1, "un día del mes que cambia una vez incumple")
    pares = pd.DataFrame({"nombre": ["X", "X", "Y"], "tipo": ["A", "B", "A"]})
    comprobar(m.nombres_con_mas_de_un_tipo(pares) == ["X"], "un nombre con dos tipos se detecta")
    comprobar(m.normalizar_nombre("snap_CA") == "snap_ca" and m.normalizar_nombre("Año fiscal") == "ano_fiscal",
              "el nombre normalizado va en minúsculas, sin tildes y con guion bajo")


def probar_validacion(m):
    """Las comprobaciones 6, 7, 9 y 10 paran con ERROR; el caso roto TIENE que saltar."""
    bueno = {
        "entradas": [{"ruta": "data/raw/a.csv", "sha256": "h1"}],
        "huellas_despues": {"data/raw/a.csv": "h1"},
        "columnas_con_vacios": [{"tabla": "t", "columna": "c"}],
        "nulos_por_segmento": [{"tabla": "t", "columna": "c", "veredicto": "repartidos"}],
        "cruces": [{"izquierda": "t", "derecha": "u", "sin_pareja_izquierda": 0, "sin_pareja_derecha": 3}],
        "magnitudes": [{"tabla": "t", "columna": "m", "grupos": 2}],
        "escala": [{"tabla": "t", "columna": "m"}, {"tabla": "t", "columna": "m"}],
        "colas": [{"tabla": "t", "columna": "m"}, {"tabla": "t", "columna": "m"}],
        "parametros": [{"nombre": n, "valor": 1, "origen": "por defecto"} for n in m.PARAMETROS_DE_LA_METODO],
    }
    comprobar(m.validar(bueno) == [], "un resultado completo pasa las cuatro comprobaciones")
    roto = json.loads(json.dumps(bueno))
    roto["nulos_por_segmento"] = []
    roto["huellas_despues"]["data/raw/a.csv"] = "otra"
    roto["cruces"][0]["sin_pareja_derecha"] = None
    roto["colas"] = roto["colas"][:1]
    roto["parametros"] = roto["parametros"][1:]
    fallos = m.validar(roto)
    comprobar(len(fallos) == 4 and all(any(f["comprobacion"].startswith(n) for f in fallos) for n in ("6", "7", "9", "10")),
              "un resultado roto hace saltar las comprobaciones 6, 7, 9 y 10")
    d = {"resultado": {"estado": "AVISO", "riesgo": "medio", "resumen": "x"}, **roto}
    m.aplicar_validacion(d)
    comprobar(d["resultado"]["estado"] == "ERROR" and d["validacion"], "si la validación falla, el estado pasa a ERROR")


def probar_paradas(m):
    """Una venta negativa o una semana con venta y sin precio paran el trabajo (reglas, apartado 5)."""
    comprobar(m.estado_y_riesgo([], [], []) == ("OK", "bajo"), "sin pendientes ni paradas: OK")
    comprobar(m.estado_y_riesgo([], [], [{"id": "PC-01"}]) == ("AVISO", "medio"), "con pendientes: AVISO")
    comprobar(m.estado_y_riesgo([], m.paradas(1, 0), [])[0] == "PARADO", "una venta negativa para el trabajo")
    comprobar(m.estado_y_riesgo([], m.paradas(0, 2), [])[0] == "PARADO", "una semana con venta y sin precio para el trabajo")
    comprobar(m.estado_y_riesgo([{"comprobacion": "9"}], [], [])[0] == "ERROR", "una validación que falla es ERROR")


def probar_textos_navidad(m):
    """El 25 de diciembre se describe con lo que miden los datos, no con una copia de las reglas (24/11/2026)."""
    t = m.textos_navidad({"2011": 6, "2012": 4}, 15, 10)
    comprobar("15 de los 20 días de tienda" in t["observacion"] and "otros 5 días de tienda" in t["observacion"],
              "la observación da los días de tienda cerrados y los abiertos, calculados (10 tiendas en 2 años)")
    comprobar("10 unidades en 2 años" in t["pregunta"] and "5 de los 20 días de tienda" in t["pregunta"]
              and "otros 15" in t["pregunta"], "la pregunta da las unidades, los años y los días de tienda, calculados")
    comprobar(all("10 tiendas en 2 años" in x for x in t.values()), "los dos textos dicen de dónde salen los días de tienda")
    comprobar(all("es cero" not in x for x in t.values()), "ninguno de los dos textos dice que la venta es cero")
    codigo = SCRIPT.read_text(encoding="utf-8")
    comprobar("dicen que el 25 de diciembre la venta es cero" not in codigo and "dicen que es cero" not in codigo,
              "el script no copia la regla del 25 de diciembre de las reglas, apartado 5 (cambió el 24/11/2026)")


def probar_salidas(m):
    """El JSON sale válido sin NaN y el Markdown tiene los 19 apartados en su orden; se escribe en tmp_calidad."""
    limpio = m.a_json_limpio({"x": float("nan"), "y": [1.5, float("inf")], "z": np.int64(2)})
    comprobar(limpio["x"] is None and limpio["y"][1] is None and limpio["z"] == 2, "NaN e infinito pasan a null")
    texto = m.generar_md(m.resultado_minimo_de_prueba())
    titulos = re.findall(r"^## (.+)$", texto, flags=re.M)
    comprobar(titulos == APARTADOS, "el informe de prueba tiene los 19 apartados de la plantilla en su orden")
    ruta = TMP / "x.json"
    m.escribir_json(ruta, {"a": 1})
    comprobar(json.loads(ruta.read_text(encoding="utf-8")) == {"a": 1}, "el JSON se escribe en UTF-8 y se relee igual")


def probar_cifras_del_informe():
    """La comprobación «cada cifra del informe está en el JSON» tiene que poder dar rojo."""
    del_json = numeros_del_json({"a": 1234, "b": "vale 5,6 dólares", "c": 0.123456}, set())
    comprobar(numeros("hay 1.234 y 5,6") <= del_json, "1.234 y 5,6 se reconocen como cifras del JSON")
    comprobar(not numeros("hay 1.235") <= del_json, "una cifra que no está en el JSON se detecta (el caso que tiene que fallar)")
    comprobar(numeros("0,12") <= del_json, "una cifra redondeada a dos decimales se reconoce")


def probar_sin_veredictos_escritos():
    """Error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](ok|cumple|pasa|coincide|igual|valida|aprobada_por_datos)[\"']\s*:\s*(True|False)\b", codigo)
    comprobar(puestos == [], "el script no escribe ninguna comprobación con True o False puesto")


# ── 3. Con los datos reales (solo con --datos) ─────────────────────────────────
def numeros(texto):
    """Números de un texto escrito a la española (punto de miles, coma decimal), como floats."""
    salida = set()
    for t in re.findall(r"\d+(?:\.\d{3})*(?:,\d+)?", texto):
        salida.add(float(t.replace(".", "").replace(",", ".")))
    return salida


def numeros_del_json(obj, acumulado):
    """Todos los números del JSON: los valores numéricos y los que van escritos dentro de los textos."""
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
    """Las cifras de control de la petición (clave "calidad" de tests/cifras_de_referencia.json) salen iguales."""
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    if "calidad" not in ref:
        comprobar(False, "tests/cifras_de_referencia.json tiene la clave calidad")
        return
    esperado = ref["calidad"]["cifras"]
    medido = d["cifras_de_control"]
    for clave, valor in esperado.items():
        comprobar(medido.get(clave) == valor, f"cifra de control {clave}: esperado {valor} · JSON {medido.get(clave)}")
    huellas = {e["ruta"].split("/")[-1]: e["sha256"] for e in d["entradas"]}
    comprobar(huellas == ref["huellas"], "las huellas de entrada son las de la petición")
    comprobar({k.split("/")[-1]: v for k, v in d["huellas_despues"].items()} == ref["huellas"],
              "las huellas de data/raw/ después del script son las de la petición")


def segunda_via(d):
    """Rehace con el módulo csv, sin pandas, los precios bajos por periodo y las unidades de cada 25 de diciembre."""
    raw = RAIZ / "data" / "raw"
    bajos_hasta = bajos_despues = 0
    with open(raw / "sell_prices.csv", encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            if float(fila["sell_price"]) < 0.5:
                if int(fila["wm_yr_wk"]) <= 11416:
                    bajos_hasta += 1
                else:
                    bajos_despues += 1
    with open(raw / "calendar.csv", encoding="utf-8", newline="") as f:
        navidad = {fila["d"]: fila["date"][:4] for fila in csv.DictReader(f) if fila["date"][5:] == "12-25"}
    unidades = {}
    with open(raw / "sales_train_evaluation.csv", encoding="utf-8", newline="") as f:
        lector = csv.reader(f)
        cabecera = next(lector)
        posiciones = {i: navidad[c] for i, c in enumerate(cabecera) if c in navidad}
        for fila in lector:
            for i, ano in posiciones.items():
                unidades[ano] = unidades.get(ano, 0) + int(fila[i])
    c = d["cifras_de_control"]
    print("segunda vía · precios bajo 0,5 hasta la 11416: csv", bajos_hasta, "· JSON", c["precio_bajo_0_5_hasta_11416"])
    print("segunda vía · precios bajo 0,5 después: csv", bajos_despues, "· JSON", c["precio_bajo_0_5_despues"])
    print("segunda vía · unidades del 25 de diciembre: csv", dict(sorted(unidades.items())), "· JSON", c["unidades_25_diciembre"])
    comprobar(bajos_hasta == c["precio_bajo_0_5_hasta_11416"] and bajos_despues == c["precio_bajo_0_5_despues"],
              "los precios por debajo de 0,5 coinciden por las dos vías")
    comprobar(dict(sorted(unidades.items())) == c["unidades_25_diciembre"], "las unidades del 25 de diciembre coinciden por las dos vías")


def informe_md(d):
    """El informe tiene los 19 apartados en su orden, ninguna cifra fuera del JSON y ninguna «, y»."""
    texto = (RAIZ / "informes" / "calidad-datos.md").read_text(encoding="utf-8")
    titulos = re.findall(r"^## (.+)$", texto, flags=re.M)
    comprobar(titulos == APARTADOS, "el informe real tiene los 19 apartados de la plantilla en su orden")
    del_json = numeros_del_json(d, set())
    fuera = sorted(n for n in numeros(texto) if n not in del_json)
    comprobar(fuera == [], f"cada cifra del informe está en el JSON (fuera: {fuera[:10]})")
    comprobar(", y " not in texto, "el informe no une dos partes con «, y»")
    comprobar("|---" not in texto, "el informe no usa tablas Markdown")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_saltos_de_nivel(modulo)
            probar_cierres_y_rachas(modulo)
            probar_precios(modulo)
            probar_atipicos_y_colas(modulo)
            probar_reparto(modulo)
            probar_reglas(modulo)
            probar_validacion(modulo)
            probar_paradas(modulo)
            probar_textos_navidad(modulo)
            probar_salidas(modulo)
            probar_sin_veredictos_escritos()
            probar_cifras_del_informe()
            if "--datos" in sys.argv:
                datos = json.loads((RAIZ / "informes" / "calidad-datos.json").read_text(encoding="utf-8"))
                cifras_de_referencia(datos)
                segunda_via(datos)
                informe_md(datos)
    except Exception as error:  # un fallo del script es un fallo de la prueba, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_calidad borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
