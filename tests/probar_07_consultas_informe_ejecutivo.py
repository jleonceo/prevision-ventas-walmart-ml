"""Prueba de scripts/07_consultas_informe_ejecutivo.py, con tablas pequeñas escritas aquí.

No lee ningún dato ni informe del caso. Importa solo el script que prueba, que tiene su trabajo bajo __main__. Cada
caso lleva su rojo: un mutante del script con la pieza que evita el error cambiada, que tiene que fallar (error 24).

Los casos:
  1. la venta de 2013 suma solo los días de 2013 de la construcción; ni la validación ni otro año entran;
  2. las partes por categoría y la venta media al día, calculadas a mano;
  3. los productos sin cambio de precio se cuentan solo en las semanas de la construcción;
  4. las cifras del exploratorio: Acción de Gracias, SNAP separado entre alimentación y el resto, día de la semana,
     meses y cambios de nivel, con un caso a mano;
  5. el script no escribe ninguna comprobación con su resultado puesto.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "07_consultas_informe_ejecutivo.py"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cerca(a, b, tolerancia=1e-9):
    """Cierto si los dos números existen y se diferencian en menos de la tolerancia."""
    return a is not None and b is not None and abs(float(a) - float(b)) < tolerancia


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    spec = importlib.util.spec_from_file_location("consultas_07", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Tablas pequeñas ─────────────────────────────────────────────────────────
def tabla_venta():
    """Dos días de 2013 y uno de 2012 en construcción, uno de 2013 en validación, dos categorías.

    2013 en construcción: FOODS vende 30 unidades y 60 dólares; HOBBIES, 10 y 40. Total 40 unidades y 100 dólares en
    dos días: 50 dólares al día. Las partes: FOODS 75 % de las unidades y 60 % de los dólares. La trampa de la
    validación trae 1.000 unidades en 2013 y la de 2012, 500.
    """
    filas = [
        ("2013-03-01", "construccion", "FOODS", 20, 40.0), ("2013-03-01", "construccion", "HOBBIES", 5, 20.0),
        ("2013-03-02", "construccion", "FOODS", 10, 20.0), ("2013-03-02", "construccion", "HOBBIES", 5, 20.0),
        ("2012-03-02", "construccion", "FOODS", 500, 1000.0),
        ("2013-12-31", "validacion", "FOODS", 1000, 2000.0),
    ]
    t = pd.DataFrame(filas, columns=["date", "periodo", "cat_id", "unidades", "dolares"])
    t["date"] = pd.to_datetime(t["date"]).astype("datetime64[us]")
    t["periodo"] = t["periodo"].astype("str")
    t["cat_id"] = t["cat_id"].astype("str")
    return t


def tabla_precios():
    """Tres productos de tienda: P1 sin cambio en la construcción, P2 con cambio, P3 cambia solo en la validación."""
    filas = [("S", "P1", 1, 1.0), ("S", "P1", 2, 1.0), ("S", "P2", 1, 1.0), ("S", "P2", 2, 2.0),
             ("S", "P3", 1, 3.0), ("S", "P3", 2, 3.0), ("S", "P3", 3, 9.0)]
    return pd.DataFrame(filas, columns=["store_id", "item_id", "wm_yr_wk", "sell_price"])


def exploratorio():
    """Un JSON de exploratorio mínimo con las piezas que se leen."""
    return {
        "pareto": {"series_unidades": {"elementos": 4, "elementos_para_el_80": 2},
                   "series_dolares": {"elementos": 4, "elementos_para_el_80": 3}},
        "reparto": {"departamento": [{"nombre": "FOODS_1", "parte_unidades_pct": 60.0},
                                     {"nombre": "HOBBIES_1", "parte_unidades_pct": 40.0}]},
        "pregunta_4": {
            "eventos": [{"evento": "Thanksgiving", "departamento": "FOODS_1", "cambio_pct": -10.0},
                        {"evento": "Thanksgiving", "departamento": "HOBBIES_1", "cambio_pct": -50.0},
                        {"evento": "NewYear", "departamento": "FOODS_1", "cambio_pct": -20.0},
                        {"evento": "NewYear", "departamento": "HOBBIES_1", "cambio_pct": -30.0}],
            "snap": {"FOODS_1": {"cambio_pct": 12.0}, "FOODS_2": {"cambio_pct": 4.0},
                     "HOBBIES_1": {"cambio_pct": -2.0}},
            "dia_semana": {"FOODS_1": {"cociente": 1.3, "dia_fuerte": "Saturday"},
                           "HOBBIES_1": {"cociente": 1.2, "dia_fuerte": "Wednesday"}},
            "mes": {"FOODS": {"meses": {"1": {"cambio_pct": -3.0}, "2": {"cambio_pct": 5.5}}}}},
        "saltos": [{"tienda": "S1", "departamento": "FOODS_1", "fecha": "2012-10-26", "razon": 2.0, "salto": True},
                   {"tienda": "S1", "departamento": "HOBBIES_2", "fecha": "2012-10-26", "razon": 0.5, "salto": True},
                   {"tienda": "S2", "departamento": "HOBBIES_2", "fecha": "2013-01-01", "razon": 1.6, "salto": True},
                   {"tienda": "S2", "departamento": "FOODS_1", "fecha": None, "razon": 1.1, "salto": False}],
        "ceros": {"por_clase": {"cierre": 3, "25_diciembre": 1, "demanda_intermitente": 9, "resto": 2},
                  "series_intermitentes": ["S1 HOBBIES_2", "S2 HOBBIES_2"]},
        "poblacion": {"construccion": {"filas": 100, "dias": 50}},
    }


# ── 3. Casos ───────────────────────────────────────────────────────────────────
def probar_ventas(m):
    """Casos 1 y 2: la venta de 2013, solo construcción y solo 2013, con partes y media al día."""
    r = m.venta_del_ano(tabla_venta(), 2013)
    comprobar(r["unidades"] == 40 and cerca(r["dolares"], 100.0), f"2013: 40 unidades y 100 dólares ({r})")
    comprobar(cerca(r["dolares_al_dia"], 50.0) and r["dias"] == 2, f"2013: 50 dólares al día en 2 días ({r})")
    comprobar(cerca(r["partes"]["FOODS"]["unidades_pct"], 75.0) and cerca(r["partes"]["FOODS"]["dolares_pct"], 60.0),
              f"2013: FOODS 75 % de las unidades y 60 % de los dólares ({r['partes']})")
    original = m.solo_construccion
    m.solo_construccion = lambda t: t
    try:
        mut = m.venta_del_ano(tabla_venta(), 2013)
    finally:
        m.solo_construccion = original
    comprobar(mut["unidades"] != 40, f"rojo · sin quitar la validación cambia la venta de 2013 ({mut['unidades']})")


def probar_precios(m):
    """Caso 3: productos de tienda sin cambio de precio, solo en las semanas de la construcción."""
    r = m.sin_cambio_de_precio(tabla_precios(), {1, 2})
    comprobar(r["productos_tienda"] == 3 and cerca(r["pct"], 200 / 3),
              f"construcción: 2 de 3 sin cambio, 66,7 % ({r})")
    mut = m.sin_cambio_de_precio(tabla_precios(), {1, 2, 3})
    comprobar(not cerca(mut["pct"], 200 / 3), f"rojo · con la semana de la validación cambia la cifra ({mut})")


def probar_exploratorio(m):
    """Caso 4: las cifras que se toman del exploratorio, con un caso a mano."""
    c = m.cifras_del_exploratorio(exploratorio())
    comprobar(cerca(c["accion_gracias_bajada_min_pct"], 10.0) and cerca(c["accion_gracias_bajada_max_pct"], 50.0)
              and c["accion_gracias_negativos"] == 2, f"Acción de Gracias: de 10 % a 50 %, 2 de 2 negativos ({c})")
    comprobar(cerca(c["snap_alimentacion_min_pct"], 4.0) and cerca(c["snap_alimentacion_max_pct"], 12.0)
              and cerca(c["snap_resto_min_pct"], -2.0), "SNAP: alimentación de 4 % a 12 %; el resto, −2 %")
    comprobar(c["dias_fuertes_fin_de_semana"] == 1 and c["departamentos"] == 2,
              "día de la semana: 1 de 2 departamentos con el día fuerte en fin de semana")
    comprobar(cerca(c["mes_mayor_desvio_pct"], 5.5), "meses: el mayor desvío sin signo, 5,5 %")
    comprobar(c["cambios_de_nivel"] == 3 and c["cambios_de_nivel_bajadas"] == 1
              and c["cambios_de_nivel_hobbies_2"] == 2, "cambios de nivel: 3, 1 bajada, 2 de HOBBIES_2")
    comprobar(c["cambios_mismo_dia_mayor"] == 2 and c["cambios_mismo_dia_tienda"] == "S1"
              and c["cambios_mismo_dia_fecha"] == "2012-10-26", "el mayor grupo del mismo día: S1, 2 el 26/10/2012")
    comprobar(c["departamentos_de_tienda_80_unidades"] == 2 and c["departamentos_de_tienda_80_dolares"] == 3,
              "Pareto: 2 en unidades y 3 en dólares")
    original = m.es_alimentacion
    m.es_alimentacion = lambda d: True
    try:
        mut = m.cifras_del_exploratorio(exploratorio())
    finally:
        m.es_alimentacion = original
    comprobar(not cerca(mut["snap_alimentacion_min_pct"], 4.0), "rojo · sin separar alimentación cambia el mínimo")


def probar_sin_veredictos_escritos():
    """Caso 5, error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    patron = r"[\"'](coincide|pasa|cumple|iguales|ok|correcto)[\"']\s*:\s*(True|False)\b"
    comprobar(re.findall(patron, codigo) == [], "el script no escribe ninguna comprobación con su resultado puesto")
    comprobar(re.findall(patron, "x = {\"coincide\": True}") != [], "rojo · la búsqueda ve un veredicto escrito")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_ventas(modulo)
            probar_precios(modulo)
            probar_exploratorio(modulo)
            probar_sin_veredictos_escritos()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
