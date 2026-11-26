"""Prueba de scripts/09_business_case.py, con cifras pequeñas escritas aquí.

No lee ningún dato ni informe del caso salvo con --datos, que comprueba el JSON y el Excel que deja el script con un
cálculo por otro camino. Importa solo el script que prueba, que tiene su trabajo bajo __main__.

Los casos:
  1. las cuentas de un mes, calculadas a mano: ahorro, margen de la venta recuperada, coste y beneficio;
  2. el mes en que se recupera la inversión sale del beneficio acumulado y no es el primer mes con beneficio (regla 3);
  3. la rampa tiene 36 meses y empieza en cero (regla 5);
  4. las guardias paran: una mejora de 1 o más (regla 4), un supuesto sin fuente (regla 6), una rampa corta (regla 5);
  5. el script no escribe ninguna comprobación con su resultado puesto (error 24);
  6. con --datos: el resultado de cada escenario rehecho con una fórmula cerrada, y el Excel con lo mismo que el JSON.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "09_business_case.py"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cerca(a, b, tolerancia=1e-6):
    """Cierto si los dos números existen y se diferencian en menos de la tolerancia."""
    return a is not None and b is not None and abs(float(a) - float(b)) < tolerancia


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    spec = importlib.util.spec_from_file_location("business_case_09", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def escenario_a_mano():
    """Un escenario pequeño: ahorro de base 1.000 al mes, venta perdida de base 2.000, margen del 25 %.

    Mejora del 10 %. Con la palanca entera, cada mes ahorra 100 y recupera 200 de venta, que dejan 50 de margen: 150.
    Puesta en marcha 900 en tres meses (300 al mes) y 20 al mes de coste fijo.
    """
    return {"base_ahorro": 1000.0, "base_venta_perdida": 2000.0, "margen_pct": 25.0, "mejora_pct": 10.0,
            "puesta_en_marcha": 900.0, "meses_puesta_en_marcha": 3, "coste_mes": 20.0}


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_cuentas(m):
    """Caso 1: las cuentas de un mes, a mano."""
    e = escenario_a_mano()
    rampa = [1.0] * 36
    meses = m.cuentas(e, rampa)
    primero = meses[0]
    comprobar(len(meses) == 36, f"36 meses ({len(meses)})")
    comprobar(cerca(primero["ahorro"], 100.0) and cerca(primero["venta_recuperada"], 200.0)
              and cerca(primero["margen_venta"], 50.0), f"mes 1: ahorro 100, venta 200, margen 50 ({primero})")
    comprobar(cerca(primero["coste"], 320.0) and cerca(primero["beneficio"], -170.0),
              f"mes 1: coste 320 y beneficio −170 ({primero})")
    comprobar(cerca(meses[3]["coste"], 20.0) and cerca(meses[3]["beneficio"], 130.0),
              f"mes 4: coste 20 y beneficio 130 ({meses[3]})")
    # Rojo: sin margen, la venta recuperada contaría entera como beneficio
    mut = m.cuentas(dict(e, margen_pct=100.0), rampa)
    comprobar(not cerca(mut[0]["beneficio"], -170.0), "rojo · con margen del 100 % cambia el beneficio")


def probar_recuperacion(m):
    """Caso 2: el mes de recuperación sale del acumulado (regla 3)."""
    e = escenario_a_mano()
    r = m.resumen(m.cuentas(e, [1.0] * 36))
    # Meses 1 a 3: −170 cada uno (acumulado −510). Desde el 4, +130: el acumulado pasa de cero en el mes 7 (−510 + 4×130)
    comprobar(r["primer_mes_con_beneficio"] == 4, f"primer mes con beneficio, el 4 ({r['primer_mes_con_beneficio']})")
    comprobar(r["mes_recupera_inversion"] == 7, f"recupera la inversión en el mes 7 ({r['mes_recupera_inversion']})")
    comprobar(cerca(r["total"]["coste"], 900.0 + 20.0 * 36), f"coste de tres años, 1.620 ({r['total']['coste']})")
    comprobar(cerca(r["total"]["beneficio"], 150.0 * 36 - 1620.0), f"beneficio de tres años ({r['total']['beneficio']})")
    comprobar(cerca(r["total"]["roi_pct"], (150.0 * 36 - 1620.0) / 1620.0 * 100),
              f"retorno = beneficio / coste ({r['total']['roi_pct']})")
    comprobar(len(r["por_anio"]) == 3, "tres años")


def probar_rampa(m):
    """Caso 3: la rampa del caso, 36 meses y nada al empezar."""
    r = m.rampa()
    comprobar(len(r) == 36 and r[0] == 0 and r[-1] == 1, f"rampa de 36 meses de 0 a 1 ({r[:7]})")
    comprobar(all(0 <= x <= 1 for x in r), "rampa entre 0 y 1")


def probar_guardias(m):
    """Caso 4: las guardias de las seis reglas paran lo que tienen que parar."""
    e = escenario_a_mano()
    supuestos = [{"nombre": "x", "valor": 1, "origen": "fuente pública", "fuente": "un sitio"}]
    comprobar(m.validar({"central": e}, supuestos, m.rampa()) == [], "control · un escenario correcto no para")
    comprobar(any("mejora" in x for x in m.validar({"central": dict(e, mejora_pct=100.0)}, supuestos, m.rampa())),
              "rojo · una mejora del 100 % (factor 0) para")
    sin_fuente = [{"nombre": "x", "valor": 1, "origen": "fuente pública", "fuente": ""}]
    comprobar(any("fuente" in x for x in m.validar({"central": e}, sin_fuente, m.rampa())),
              "rojo · un supuesto sin fuente para")
    comprobar(any("rampa" in x for x in m.validar({"central": e}, supuestos, [1.0] * 12)),
              "rojo · una rampa de 12 meses para")
    comprobar(any("base" in x for x in m.validar({"central": dict(e, base_ahorro=-5.0)}, supuestos, m.rampa())),
              "rojo · una base negativa para")


def probar_sin_veredictos_escritos():
    """Caso 5, error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    patron = r"[\"'](coincide|pasa|cumple|iguales|ok|correcto)[\"']\s*:\s*(True|False)\b"
    comprobar(re.findall(patron, codigo) == [], "el script no escribe ninguna comprobación con su resultado puesto")
    comprobar(re.findall(patron, "x = {\"cumple\": True}") != [], "rojo · la búsqueda ve un veredicto escrito")


def probar_con_datos(m):
    """Con --datos: el JSON rehecho con una fórmula cerrada y el Excel contra el JSON."""
    ruta = RAIZ / m.SALIDA_JSON
    if not ruta.exists():
        comprobar(False, f"existe {m.SALIDA_JSON}")
        return
    j = json.loads(ruta.read_text(encoding="utf-8"))
    comprobar(j["estado"] == "OK", f"el JSON está en OK ({j['estado']})")
    # Otra vía: con la rampa de 3 meses a 0, 3 a la mitad y 30 enteros, el efecto suma 31,5 meses de palanca entera
    for nombre, esc in j["escenarios"].items():
        p = esc["parametros"]
        mensual = p["base_ahorro"] * p["mejora_pct"] / 100 + p["base_venta_perdida"] * p["mejora_pct"] / 100 * p["margen_pct"] / 100
        resultado = mensual * 31.5
        coste = p["puesta_en_marcha"] + p["coste_mes"] * 36
        comprobar(abs(esc["total"]["resultado"] - resultado) < 0.01 and abs(esc["total"]["coste"] - coste) < 0.01,
                  f"{nombre}: resultado y coste rehechos con la fórmula cerrada")
    # Otra vía para la base: la venta de 2013 del JSON de consultas, entre 12
    c = {x["nombre"]: x["valor"] for x in json.loads((RAIZ / m.CONSULTAS).read_text(encoding="utf-8"))["cifras"]}
    comprobar(abs(j["linea_de_hoy"]["venta_mes"] - c["dolares_2013"] / 12) < 0.01, "la venta al mes es la de 2013 entre 12")
    # El Excel lleva en cada escenario las bases y los porcentajes del JSON
    import openpyxl
    wb = openpyxl.load_workbook(RAIZ / m.SALIDA_XLSX)
    for nombre, esc in j["escenarios"].items():
        hoja = wb[f"Escenario {nombre}"]
        p = esc["parametros"]
        comprobar(abs(hoja["C25"].value - p["base_ahorro"]) < 0.01 and abs(hoja["C12"].value - p["base_venta_perdida"]) < 0.01
                  and hoja["C39"].value == p["margen_pct"], f"Excel, {nombre}: bases y margen como en el JSON")
        comprobar(hoja["C27"].value == 0 and hoja["AN27"].value == p["mejora_pct"], f"Excel, {nombre}: la rampa en los porcentajes")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_cuentas(modulo)
            probar_recuperacion(modulo)
            probar_rampa(modulo)
            probar_guardias(modulo)
            probar_sin_veredictos_escritos()
            if "--datos" in sys.argv:
                probar_con_datos(modulo)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
