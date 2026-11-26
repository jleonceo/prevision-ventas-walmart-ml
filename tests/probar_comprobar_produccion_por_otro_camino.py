"""Prueba de tests/comprobar_produccion_por_otro_camino.py en lo que cambia para el reentrenado, con datos pequeños.

La prueba por otro camino rehace las previsiones con el preprocesador del desarrollo, que pide las columnas
evento_<nombre>. La tabla del reentrenado (produccion_prevision.tabla_con_variables) no las lleva: solo trae
event_name_1 y event_name_2. Aquí se prueba la función que las calcula en ese caso, sin importar el código de
producción. No lee ningún dato del caso.

Los casos:
  1. una tabla de entrenamiento sin evento_<nombre>: la lista sale de los eventos de su event_name_1 y event_name_2,
     ordenada; cada columna vale 1 el día que trae el evento en cualquiera de los dos campos y 0 si no, también en la
     tabla de historia; un evento que solo aparece en la historia no crea columna (la lista aprende del entrenamiento);
  2. una tabla de entrenamiento que ya las trae (la de la validación): no se tocan y la lista es la suya;
  3. una tabla de historia que ya trae una columna con otro valor que el calculado: para, no la pisa;
  4. el fichero sigue sin importar el código de producción (preproduccion §2.4).
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "tests" / "comprobar_produccion_por_otro_camino.py"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar():
    """Importa la prueba por otro camino sin ejecutar su __main__."""
    spec = importlib.util.spec_from_file_location("otro_camino", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def tablas():
    """Un entrenamiento sin columnas de evento y una historia con un evento que el entrenamiento no tiene."""
    entrenamiento = pd.DataFrame({"date": pd.date_range("2015-02-01", periods=4, freq="D"),
                                  "event_name_1": ["SuperBowl", None, "Easter", None],
                                  "event_name_2": [None, None, None, "Easter"], "unidades": [1.0, 2.0, 3.0, 4.0]})
    historia = pd.DataFrame({"date": pd.date_range("2015-02-05", periods=3, freq="D"),
                             "event_name_1": ["Easter", "NewYear", None], "event_name_2": [None, None, "SuperBowl"],
                             "unidades": [5.0, 6.0, 7.0]})
    return entrenamiento, historia


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_sin_columnas(m):
    """Caso 1: se calculan de event_name_1 y event_name_2, con la lista del entrenamiento."""
    entrenamiento, historia = tablas()
    e, h, columnas = m.columnas_de_evento(entrenamiento, historia)
    comprobar(columnas == ["evento_Easter", "evento_SuperBowl"], f"sin columnas: la lista del entrenamiento ({columnas})")
    comprobar(e["evento_Easter"].tolist() == [0, 0, 1, 1] and e["evento_SuperBowl"].tolist() == [1, 0, 0, 0],
              "sin columnas: 1 el día que trae el evento en cualquiera de los dos campos")
    comprobar(h["evento_Easter"].tolist() == [1, 0, 0] and h["evento_SuperBowl"].tolist() == [0, 0, 1]
              and "evento_NewYear" not in h.columns, "sin columnas: la historia con la misma lista, sin eventos nuevos")
    comprobar("evento_Easter" not in entrenamiento.columns, "sin columnas: no cambia las tablas que recibe")


def probar_con_columnas(m):
    """Caso 2: un entrenamiento que ya las trae no se toca."""
    entrenamiento, historia = tablas()
    entrenamiento["evento_Otro"] = [0, 1, 0, 0]
    e, h, columnas = m.columnas_de_evento(entrenamiento, historia)
    comprobar(columnas == ["evento_Otro"] and e.equals(entrenamiento) and h.equals(historia),
              f"con columnas: no se tocan ({columnas})")


def probar_choca(m):
    """Caso 3: una historia con una columna que no coincide con la calculada para."""
    entrenamiento, historia = tablas()
    historia["evento_Easter"] = [0, 0, 0]
    try:
        m.columnas_de_evento(entrenamiento, historia)
        resultado = None
    except ValueError as error:
        resultado = str(error)
    comprobar(resultado is not None and "evento_Easter" in resultado, f"choca: para sin pisarla ({resultado})")


def probar_sin_produccion():
    """Caso 4: no importa el código de producción."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    importa = re.findall(r"^\s*(?:from|import)\s+(produccion_prevision|variables_prevision|prevision_recursiva|"
                         r"produccion)\b", codigo, flags=re.MULTILINE)
    comprobar(not importa, f"sin importar producción ({importa})")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    try:
        modulo = cargar()
        if not hasattr(modulo, "columnas_de_evento"):
            comprobar(False, "existe la función columnas_de_evento")
        else:
            probar_sin_columnas(modulo)
            probar_con_columnas(modulo)
            probar_choca(modulo)
        probar_sin_produccion()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
