"""Business case del caso 69 (paso 4b): lo que valdría ajustar el pedido de cada departamento a la previsión.

Rellena la plantilla común del business case con tres escenarios (bajo, central y alto) y rehace las cuentas en Python,
mes a mes durante tres años, para que los resultados no dependan de que Excel recalcule:
  - la línea de hoy sale de los datos: la venta de 2013 del recorte, leída de informes/consultas-informe-ejecutivo.json;
  - el resto de importes son supuestos, cada uno con su origen: una fuente pública o la decisión del equipo de análisis por petición
    del responsable del caso (24/11/2026, «No tengo ni idea, decide tú»).

Dos palancas, de la palanca principal de la ficha («Ajustar el pedido de cada departamento a la previsión»):
  - ahorro: el coste de mantener la mercancía en el almacén baja con la mejora;
  - ingresos: se recupera parte de la venta que hoy se pierde por estante vacío; cuenta solo su margen.
Sus bases no se solapan (una es coste de mercancía guardada, la otra venta que no se hizo), así que se suman.

Deja informes/business_case.json e informes/business_case.xlsx. Depende de scripts/07_consultas_informe_ejecutivo.py.

Uso: python -W error scripts/09_business_case.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

import openpyxl

CASO = Path(__file__).resolve().parents[1]

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/09_business_case.py"
CONSULTAS = "informes/consultas-informe-ejecutivo.json"
# La plantilla común, la misma que la del workflow (comprobado con cmp el 24/11/2026)
PLANTILLA = "assets/plantilla_business_case.xlsx"
SALIDA_JSON = "informes/business_case.json"
SALIDA_XLSX = "informes/business_case.xlsx"
MESES = 36
# Columnas de los 36 meses en la plantilla: tres bloques de doce, cada uno seguido de su total del año
COLUMNAS = list(range(3, 15)) + list(range(16, 28)) + list(range(29, 41))
COMBINACION = ("Las dos palancas se suman: el coste de mantener la mercancía y la venta perdida por estante vacío "
               "no comparten base.")
EQUIPO = "decidido por el equipo de análisis a petición del responsable del caso, 24/11/2026"

# Supuestos comunes a los tres escenarios, cada uno con su origen y su fuente
MARGEN_PCT = 24.3
FALTAN_PCT = 8.0
SUPUESTOS = [
    {"nombre": "margen bruto sobre ventas", "valor": MARGEN_PCT, "origen": "fuente pública",
     "fuente": "Walmart, informe anual 10-K del año fiscal 2014 (SEC): 24,3 % de las ventas netas"},
    {"nombre": "productos que faltan en el estante", "valor": FALTAN_PCT, "origen": "fuente pública",
     "fuente": "Corsten y Gruen, estudio mundial de roturas de estante (2002): alrededor del 8 %"},
    {"nombre": "días de inventario", "valor": "40 y 45", "origen": "fuente pública",
     "fuente": "unos 45 días en 2013 (Spiceland, Intermediate Accounting); mediana de 42,8 (GuruFocus)"},
    {"nombre": "coste anual de mantener la mercancía", "valor": "20, 25 y 30 %", "origen": "fuente pública",
     "fuente": "regla general del sector, entre el 20 % y el 30 % del valor de la mercancía (Shopify, NetSuite)"},
    {"nombre": "parte de la venta del estante vacío que se pierde", "valor": "25, 40 y 50 %", "origen": EQUIPO,
     "fuente": "(supuesto) sin cifra comprobada; el estudio de Corsten y Gruen describe las reacciones del cliente"},
    {"nombre": "mejora de las dos palancas", "valor": "5, 10 y 15 %", "origen": EQUIPO, "fuente": "(supuesto)"},
    {"nombre": "puesta en marcha y coste mensual", "valor": "40.000/2.000, 20.000/1.000 y 10.000/500 dólares",
     "origen": EQUIPO, "fuente": "(supuesto)"},
    {"nombre": "rampa y horizonte", "valor": "3 años", "origen": EQUIPO,
     "fuente": "(supuesto) guía del business case: nada los meses 1 a 3, la mitad del 4 al 6, entera desde el 7"},
]
ESCENARIOS = {
    "bajo": {"dias_inventario": 40, "mantener_pct": 20.0, "perdida_pct": 25.0, "mejora_pct": 5.0,
             "puesta_en_marcha": 40000.0, "coste_mes": 2000.0},
    "central": {"dias_inventario": 45, "mantener_pct": 25.0, "perdida_pct": 40.0, "mejora_pct": 10.0,
                "puesta_en_marcha": 20000.0, "coste_mes": 1000.0},
    "alto": {"dias_inventario": 45, "mantener_pct": 30.0, "perdida_pct": 50.0, "mejora_pct": 15.0,
             "puesta_en_marcha": 10000.0, "coste_mes": 500.0},
}
MESES_PUESTA_EN_MARCHA = 3


class Parada(Exception):
    """Condición que impide dejar el business case; el mensaje dice cuál."""


# =================================================================================================================
# 3. Cuentas
# =================================================================================================================
def rampa():
    """Parte de la palanca que actúa cada mes: nada los meses 1 a 3, la mitad del 4 al 6, entera desde el 7."""
    return [0.0] * 3 + [0.5] * 3 + [1.0] * (MESES - 6)


def parametros(venta_mes, e):
    """Las bases de las dos palancas de un escenario, con lo demás que piden las cuentas.

    Mercancía en almacén = venta a coste del año × días de inventario / 365; su coste de mantenerla, al mes.
    Venta perdida hoy = venta del mes × productos que faltan × parte que se pierde.
    """
    venta_a_coste_ano = venta_mes * 12 * (1 - MARGEN_PCT / 100)
    almacen = venta_a_coste_ano * e["dias_inventario"] / 365
    return {"venta_mes": venta_mes, "dias_inventario": e["dias_inventario"], "mantener_pct": e["mantener_pct"],
            "perdida_pct": e["perdida_pct"], "mercancia_en_almacen": almacen,
            "base_ahorro": almacen * e["mantener_pct"] / 100 / 12,
            "base_venta_perdida": venta_mes * FALTAN_PCT / 100 * e["perdida_pct"] / 100,
            "margen_pct": MARGEN_PCT, "mejora_pct": e["mejora_pct"], "puesta_en_marcha": e["puesta_en_marcha"],
            "meses_puesta_en_marcha": MESES_PUESTA_EN_MARCHA, "coste_mes": e["coste_mes"]}


def cuentas(p, parte):
    """Las cuentas de cada mes: ahorro, venta recuperada y su margen, coste y beneficio."""
    meses = []
    for i, f in enumerate(parte):
        ahorro = p["base_ahorro"] * p["mejora_pct"] / 100 * f
        venta = p["base_venta_perdida"] * p["mejora_pct"] / 100 * f
        margen_venta = venta * p["margen_pct"] / 100
        coste = p["coste_mes"] + (p["puesta_en_marcha"] / p["meses_puesta_en_marcha"]
                                  if i < p["meses_puesta_en_marcha"] else 0.0)
        meses.append({"mes": i + 1, "ahorro": ahorro, "venta_recuperada": venta, "margen_venta": margen_venta,
                      "resultado": ahorro + margen_venta, "coste": coste, "beneficio": ahorro + margen_venta - coste})
    return meses


def resumen(meses):
    """Totales por año y de los tres años, retorno, primer mes con beneficio y mes de recuperación (regla 3)."""
    claves = ("ahorro", "venta_recuperada", "margen_venta", "resultado", "coste", "beneficio")
    por_anio = [{"anio": a + 1, **{k: sum(m[k] for m in meses[a * 12:(a + 1) * 12]) for k in claves}}
                for a in range(len(meses) // 12)]
    total = {k: sum(m[k] for m in meses) for k in claves}
    total["roi_pct"] = total["beneficio"] / total["coste"] * 100 if total["coste"] else None
    primero = next((m["mes"] for m in meses if m["beneficio"] > 0), None)
    acumulado, recupera = 0.0, None
    for m in meses:
        acumulado += m["beneficio"]
        if recupera is None and acumulado >= 0:
            recupera = m["mes"]
    return {"por_anio": por_anio, "total": total, "primer_mes_con_beneficio": primero,
            "mes_recupera_inversion": recupera}


# =================================================================================================================
# 4. Comprobaciones de las seis reglas
# =================================================================================================================
def validar(escenarios, supuestos, parte):
    """Errores que impiden dejar el business case; vacío si las reglas se cumplen."""
    errores = []
    # Regla 5: tres años, mes a mes, con la rampa entre 0 y 1
    if len(parte) != MESES or not all(0 <= f <= 1 for f in parte):
        errores.append(f"la rampa tiene que tener {MESES} meses entre 0 y 1")
    for nombre, p in escenarios.items():
        # Regla 4: la mejora deja un factor menor que 1 y mayor que 0
        if not 0 < p["mejora_pct"] < 100:
            errores.append(f"{nombre}: la mejora tiene que dejar un factor entre 0 y 1")
        # Regla 1: cada palanca, con su propia base, que no puede ser negativa
        if p["base_ahorro"] < 0 or p["base_venta_perdida"] < 0:
            errores.append(f"{nombre}: una base negativa")
        if not 0 < p["margen_pct"] < 100:
            errores.append(f"{nombre}: el margen tiene que estar entre 0 y 100")
    # Regla 6: cada supuesto con su origen y su fuente
    for s in supuestos:
        if not s.get("fuente") or not s.get("origen"):
            errores.append(f"supuesto sin fuente u origen: {s.get('nombre')}")
    return errores


# =================================================================================================================
# 5. Excel
# =================================================================================================================
def rellenar_hoja(hoja, nombre, p, parte):
    """Escribe un escenario en una hoja de la plantilla: nombres, bases, porcentajes por mes, margen y costes."""
    hoja.title = f"Escenario {nombre}"
    hoja["B6"] = (f"Caso 69 · escenario {nombre}: la línea de hoy, de la venta de 2013 del recorte; "
                  "los demás importes, supuestos de la hoja ASUNCIONES")
    for fila, texto in {11: "Palanca 1: venta que hoy se pierde por estante vacío, recuperada",
                        15: "Palanca 2: no usada", 19: "Palanca 3: no usada",
                        24: "Palanca 1: coste de mantener la mercancía en el almacén",
                        28: "Palanca 2: no usada", 32: "Palanca 3: no usada", 46: "Puesta en marcha"}.items():
        hoja.cell(fila, 2, texto)
    for i, col in enumerate(COLUMNAS):
        hoja.cell(12, col, round(p["base_venta_perdida"], 2))
        hoja.cell(14, col, round(p["mejora_pct"] * parte[i], 4))
        hoja.cell(25, col, round(p["base_ahorro"], 2))
        hoja.cell(27, col, round(p["mejora_pct"] * parte[i], 4))
        hoja.cell(39, col, p["margen_pct"])
        hoja.cell(45, col, p["coste_mes"])
        hoja.cell(46, col, p["puesta_en_marcha"] / p["meses_puesta_en_marcha"]
                  if i < p["meses_puesta_en_marcha"] else 0)


def escribir_excel(raiz, escenarios, parte):
    """Copia la plantilla, deja una hoja por escenario y la hoja de supuestos."""
    destino = raiz / SALIDA_XLSX
    shutil.copy(raiz / PLANTILLA, destino)
    wb = openpyxl.load_workbook(destino)
    base = wb["Business case"]
    nombres = list(escenarios)
    hojas = [base] + [wb.copy_worksheet(base) for _ in nombres[1:]]
    for hoja, nombre in zip(hojas, nombres):
        rellenar_hoja(hoja, nombre, escenarios[nombre], parte)
    asu = wb["ASUNCIONES"]
    asu["A4"], asu["B4"], asu["C4"], asu["D4"] = (
        "Palanca 1 de ahorro", "Coste de mantener la mercancía en el almacén",
        " / ".join(f"x {1 - p['mejora_pct'] / 100:.2f} ({n})" for n, p in escenarios.items()),
        "La previsión ajusta el pedido y baja la mercancía parada. " + COMBINACION)
    asu["A5"], asu["B5"], asu["C5"], asu["D5"] = (
        "Palanca 1 de ingresos", "Venta que hoy se pierde por estante vacío",
        " / ".join(f"+{p['mejora_pct']:.0f} % ({n})" for n, p in escenarios.items()),
        "Se recupera parte de la venta perdida; cuenta solo su margen.")
    asu["A6"], asu["B6"], asu["C6"], asu["D6"] = ("Palanca 2 y 3", "no usadas", "", "")
    asu["A8"], asu["B8"], asu["C8"], asu["D8"] = ("SUPUESTO", "VALOR", "ORIGEN", "FUENTE")
    for i, s in enumerate(SUPUESTOS, start=9):
        asu.cell(i, 1, s["nombre"]); asu.cell(i, 2, str(s["valor"])); asu.cell(i, 3, s["origen"])
        asu.cell(i, 4, s["fuente"])
    wb.save(destino)


# =================================================================================================================
# 6. Ejecución
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def principal(raiz):
    """Lee la venta de 2013, calcula los tres escenarios, los comprueba y escribe el JSON y el Excel."""
    ruta_c = raiz / CONSULTAS
    if not ruta_c.exists():
        raise Parada(f"falta {CONSULTAS}: se crea con scripts/07_consultas_informe_ejecutivo.py")
    consultas = json.loads(ruta_c.read_text(encoding="utf-8"))
    if consultas.get("estado") != "OK":
        raise Parada(f"{CONSULTAS} no está en OK")
    cifras = {x["nombre"]: x["valor"] for x in consultas["cifras"]}
    venta_mes = cifras["dolares_2013"] / 12

    # Los tres escenarios, comprobados antes de escribir nada
    parte = rampa()
    escenarios = {n: parametros(venta_mes, e) for n, e in ESCENARIOS.items()}
    errores = validar(escenarios, SUPUESTOS, parte)
    if errores:
        raise Parada("; ".join(errores))
    resultados = {n: {"parametros": p, **resumen(cuentas(p, parte))} for n, p in escenarios.items()}

    salida = {"script": SCRIPT, "fecha_datos": consultas.get("fecha_datos"),
              "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "estado": "OK",
              "entradas": {CONSULTAS: sha256(ruta_c), PLANTILLA: sha256(raiz / PLANTILLA)},
              "linea_de_hoy": {"venta_2013": cifras["dolares_2013"], "venta_mes": venta_mes,
                               "origen": "datos: venta de 2013 del recorte, 500 productos en 10 tiendas"},
              "combinacion": COMBINACION, "rampa": parte, "supuestos": SUPUESTOS, "escenarios": resultados}
    escribir_excel(raiz, escenarios, parte)
    (raiz / SALIDA_JSON).write_text(json.dumps(salida, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                    encoding="utf-8")
    for n, r in resultados.items():
        t = r["total"]
        print(f"{n}: resultado {t['resultado']:.0f}, coste {t['coste']:.0f}, beneficio {t['beneficio']:.0f}, "
              f"retorno {t['roi_pct']:.1f} %, recupera en el mes {r['mes_recupera_inversion']}")
    print(f"OK: {SALIDA_JSON} y {SALIDA_XLSX}")


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    raiz = Path(argumentos.parse_args().raiz).resolve()
    print(f"Python: {sys.executable}")
    try:
        principal(raiz)
    except Parada as e:
        print(f"ERROR: {e}")
        sys.exit(1)
