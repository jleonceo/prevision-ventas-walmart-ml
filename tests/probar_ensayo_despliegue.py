"""Prueba de produccion/ensayo_despliegue.py en sus piezas, con datos pequeños escritos aquí.

El ensayo entero lanza el lote con los modelos y los datos del caso y tarda minutos: se ejecuta aparte, con su carpeta de
trabajo. Aquí se prueban las piezas que deciden si el ensayo dice la verdad, sin leer ningún dato del caso.

Los casos:
  1. el día siguiente: la venta de trabajo lleva un día más, sacado de la reserva por su columna y con los productos en
     el mismo orden; si la reserva no trae ese día o los productos no casan, para; apartar ese día deja la venta como
     estaba;
  2. comparar dos previsiones fila a fila: iguales coinciden con diferencia 0; una estropeada en 1e-6 no; una fila de
     menos no; las filas se unen por objetivo, origen, serie y fecha, no por posición;
  3. la configuración de trabajo: todas las rutas que no se copian apuntan a la carpeta del caso por ruta absoluta y
     las entradas del lote a la carpeta de trabajo; la configuración del caso no se toca;
  4. ninguna comprobación del script se escribe con su resultado puesto (error 24).
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
SCRIPT = RAIZ / "produccion" / "ensayo_despliegue.py"
TMP = RAIZ / "tests" / "tmp_ensayo_despliegue"
FALLOS = []


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


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_dia_siguiente(m):
    """Caso 1: añadir el día siguiente de la reserva y apartarlo."""
    venta = pd.DataFrame({"id": ["A", "B"], "item_id": ["A", "B"], "d_1": [1, 2], "d_2": [3, 4]})
    reserva = pd.DataFrame({"id": ["A", "B"], "item_id": ["A", "B"], "d_3": [5, 6], "d_4": [7, 8]})
    con = m.anadir_dia(venta, reserva, "d_3")
    comprobar(list(con.columns) == ["id", "item_id", "d_1", "d_2", "d_3"] and con["d_3"].tolist() == [5, 6],
              f"día siguiente: se añade la columna de la reserva ({list(con.columns)})")
    comprobar(m.apartar_dia(con, "d_3").equals(venta), "día siguiente: apartarlo deja la venta como estaba")
    mensaje = para(m.anadir_dia, venta, reserva, "d_9")
    comprobar(mensaje is not None and "d_9" in mensaje, f"día siguiente: un día que la reserva no trae para ({mensaje})")
    desordenada = reserva.iloc[::-1].reset_index(drop=True)
    mensaje = para(m.anadir_dia, venta, desordenada, "d_3")
    comprobar(mensaje is not None and "orden" in mensaje, f"día siguiente: productos en otro orden paran ({mensaje})")


def probar_comparar(m):
    """Caso 2: dos previsiones fila a fila."""
    a = pd.DataFrame({"objetivo": "unidades", "origen": pd.Timestamp("2015-05-22"), "store_id": "S",
                      "dept_id": ["D1", "D2"], "date": pd.Timestamp("2015-05-23"),
                      "prevision_sin_redondear": [1.25, 2.5]})
    r = m.comparar_previsiones(a, a.iloc[::-1].reset_index(drop=True), 1e-12)
    comprobar(r["coincide"] is True and r["diferencia_maxima"] == 0.0 and r["filas"] == 2,
              f"comparar: iguales en otro orden coinciden ({r})")
    b = a.copy()
    b.loc[1, "prevision_sin_redondear"] += 1e-6
    r = m.comparar_previsiones(a, b, 1e-12)
    comprobar(r["coincide"] is False, f"comparar: estropeada no coincide ({r})")
    r = m.comparar_previsiones(a, a.iloc[:1], 1e-12)
    comprobar(r["coincide"] is False and r["solo_en_una"] == 1, f"comparar: una fila de menos no coincide ({r})")


def probar_configuracion(m):
    """Caso 3: la configuración de trabajo."""
    configuracion = json.loads((RAIZ / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    antes = (RAIZ / "produccion" / "configuracion.json").read_bytes()
    trabajo = TMP / "trabajo"
    nueva = m.configuracion_de_trabajo(configuracion, RAIZ, trabajo)
    rutas = nueva["rutas"]
    comprobar(all(Path(rutas[k]).is_absolute() and Path(rutas[k]).is_relative_to(RAIZ)
                  for k in ("contrato", "modulo", "tabla_de_la_particion")),
              f"configuración: lo que no se copia apunta al caso por ruta absoluta ({rutas})")
    comprobar(rutas["reentrenos"] == configuracion["rutas"]["reentrenos"]
              and rutas["predicciones"] == configuracion["rutas"]["predicciones"],
              "configuración: los modelos y las predicciones, dentro de la carpeta de trabajo")
    entradas = nueva["lote_diario"]["entradas"]
    comprobar(Path(entradas["venta"]).is_relative_to(trabajo) and Path(entradas["calendario"]).is_absolute(),
              f"configuración: la venta del lote es la de trabajo ({entradas})")
    comprobar((RAIZ / "produccion" / "configuracion.json").read_bytes() == antes and configuracion != nueva,
              "configuración: la del caso no se toca")


def probar_sin_validaciones_escritas():
    """Caso 4: ninguna comprobación se escribe con su resultado puesto (error 24)."""
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
            modulo = cargar(SCRIPT, "ensayo_despliegue_prueba")
            probar_dia_siguiente(modulo)
            probar_comparar(modulo)
            probar_configuracion(modulo)
            probar_sin_validaciones_escritas()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_ensayo_despliegue borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
