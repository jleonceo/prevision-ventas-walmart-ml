"""Prueba de produccion/vuelta_atras.py, con datos pequeños escritos aquí.

No lee ningún dato ni modelo del caso. Monta en tests/tmp_vuelta_atras/ una carpeta con la estructura del caso: una
configuración de producción con su modelo en uso, dos carpetas de modelos de juguete (un fichero cualquiera con su ficha,
huella y versiones del entorno) y la salida de dos días en data/predicciones/. Lanza el script como proceso aparte con
-W error.

Los casos, los de quien quiere romperlo incluidos (programacion-del-caso, error 35):
  1. volver al modelo anterior: la configuración pasa a nombrarlo, guarda quién lo decide y una copia de la configuración
     de antes en produccion/_archivo/; el resto de la configuración no cambia;
  2. dos vueltas atrás seguidas (A a B y B a A): la configuración vuelve a nombrar el primero y quedan dos copias;
  3. volver al modelo que ya está en uso, a una carpeta que no existe, a una sin ficha o a una cuyo fichero no es el de
     su ficha: para con 1 y la configuración no cambia;
  4. sin decir quién lo decide: para;
  5. deshacer la salida de un día: la carpeta del día pasa a data/predicciones/_archivo/ (no se borra nada) y el día queda
     sin salida; dos veces seguidas: la segunda para, porque ya no hay nada que deshacer;
  6. restaurar una ejecución archivada de ese día: la carpeta del día vuelve a ser esa, y la que había pasa antes a
     _archivo/; una versión que no existe o de otro día para sin mover nada.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "produccion" / "vuelta_atras.py"
TMP = RAIZ / "tests" / "tmp_vuelta_atras"
FALLOS = []
EN_USO = "modelos/reentrenos/2015-05-22"
ANTERIOR = "modelos/reentrenos/2026-11-25"


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def huella(ruta):
    """SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def modelo_de_juguete(carpeta, contenido):
    """Dos ficheros de modelo cualquiera con su ficha: la huella y las versiones del entorno."""
    carpeta.mkdir(parents=True, exist_ok=True)
    versiones = {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                 "numpy": np.__version__, "joblib": joblib.__version__}
    for o in ("unidades", "dolares"):
        ruta = carpeta / f"{o}.joblib"
        ruta.write_bytes(f"{contenido} {o}".encode("utf-8"))
        ficha = {"fichero": ruta.name, "huella": huella(ruta), "versiones": versiones, "fecha_datos": "2015-05-22"}
        (carpeta / f"{o}_versiones.json").write_text(json.dumps(ficha), encoding="utf-8")


def montar(nombre):
    """La carpeta de prueba: configuración, dos modelos y la salida de dos días; devuelve la raíz."""
    raiz = TMP / nombre
    (raiz / "produccion").mkdir(parents=True, exist_ok=True)
    configuracion = {"que_es": "configuración de juguete", "rutas": {"reentrenos": "modelos/reentrenos",
                                                                    "predicciones": "data/predicciones",
                                                                    "modulo": str(RAIZ / "scripts")},
                     "horizontes": {"unidades": 10, "dolares": 28}, "modelo_en_uso": EN_USO,
                     "modelo_en_uso_lo_decide": "el responsable del caso", "modelo_en_uso_aprobado_por": "el responsable del caso, 25/11/2026: «sí»"}
    (raiz / "produccion" / "configuracion.json").write_text(json.dumps(configuracion, ensure_ascii=False, indent=2),
                                                            encoding="utf-8")
    modelo_de_juguete(raiz / EN_USO, "reentrenado")
    modelo_de_juguete(raiz / ANTERIOR, "primer reentreno")
    for dia, origen in (("2026-11-24", "2015-05-21"), ("2026-11-25", "2015-05-22")):
        carpeta = raiz / "data" / "predicciones" / dia
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "resumen.json").write_text(json.dumps({"origen": origen, "estado": "OK"}), encoding="utf-8")
    vieja = raiz / "data" / "predicciones" / "_archivo" / "2026-11-25_080000000000"
    vieja.mkdir(parents=True, exist_ok=True)
    (vieja / "resumen.json").write_text(json.dumps({"origen": "2015-05-21", "estado": "OK"}), encoding="utf-8")
    return raiz


def configuracion(raiz):
    """La configuración de la carpeta de prueba."""
    return json.loads((raiz / "produccion" / "configuracion.json").read_text(encoding="utf-8"))


def lanzar(raiz, *argumentos):
    """Lanza el script como proceso aparte, con -W error; devuelve (código, texto)."""
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), *map(str, argumentos), "--raiz", str(raiz)],
                          capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"),
                          timeout=300)
    return proc.returncode, proc.stdout + proc.stderr


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_modelo():
    """Casos 1 y 2: volver al modelo anterior y volver otra vez."""
    raiz = montar("modelo")
    antes = configuracion(raiz)
    codigo, texto = lanzar(raiz, "modelo", "--a", ANTERIOR, "--decide", "el responsable del caso, ensayo de la prueba")
    despues = configuracion(raiz)
    copias = sorted((raiz / "produccion" / "_archivo").glob("configuracion_*.json")) \
        if (raiz / "produccion" / "_archivo").exists() else []
    comprobar(codigo == 0 and despues["modelo_en_uso"] == ANTERIOR
              and "ensayo de la prueba" in despues["modelo_en_uso_aprobado_por"],
              f"modelo: la configuración nombra el anterior y quién lo decide ({codigo}; {texto[-400:]})")
    comprobar(len(copias) == 1 and json.loads(copias[0].read_text(encoding="utf-8")) == antes,
              f"modelo: guarda la configuración de antes ({len(copias)})")
    iguales = {k: v for k, v in despues.items() if k not in ("modelo_en_uso", "modelo_en_uso_aprobado_por",
                                                             "vuelta_atras")}
    comprobar(iguales == {k: v for k, v in antes.items() if k not in ("modelo_en_uso", "modelo_en_uso_aprobado_por")},
              "modelo: el resto de la configuración no cambia")
    comprobar((despues.get("vuelta_atras") or {}).get("desde") == EN_USO,
              f"modelo: apunta desde qué modelo se volvió ({despues.get('vuelta_atras')})")
    codigo, texto = lanzar(raiz, "modelo", "--a", EN_USO, "--decide", "el responsable del caso, vuelta de la prueba")
    otra = configuracion(raiz)
    copias = sorted((raiz / "produccion" / "_archivo").glob("configuracion_*.json"))
    comprobar(codigo == 0 and otra["modelo_en_uso"] == EN_USO and len(copias) == 2,
              f"modelo: dos vueltas atrás seguidas vuelven al primero con dos copias ({codigo}; {len(copias)})")


def probar_modelo_que_para():
    """Casos 3 y 4: lo que tiene que parar sin tocar la configuración."""
    raiz = montar("modelo_para")
    sin_ficha = raiz / "modelos" / "reentrenos" / "sin_ficha"
    modelo_de_juguete(sin_ficha, "x")
    (sin_ficha / "dolares_versiones.json").unlink()
    cambiado = raiz / "modelos" / "reentrenos" / "cambiado"
    modelo_de_juguete(cambiado, "y")
    (cambiado / "unidades.joblib").write_bytes(b"otro fichero")
    antes = huella(raiz / "produccion" / "configuracion.json")
    for nombre, argumentos in (("el que ya está en uso", ["--a", EN_USO, "--decide", "el responsable del caso"]),
                               ("una carpeta que no existe", ["--a", "modelos/reentrenos/no_existe", "--decide", "el responsable del caso"]),
                               ("una carpeta sin ficha", ["--a", "modelos/reentrenos/sin_ficha", "--decide", "el responsable del caso"]),
                               ("un fichero que no es el de su ficha", ["--a", "modelos/reentrenos/cambiado",
                                                                        "--decide", "el responsable del caso"]),
                               ("sin decir quién lo decide", ["--a", ANTERIOR, "--decide", " "])):
        codigo, texto = lanzar(raiz, "modelo", *argumentos)
        comprobar(codigo == 1 and "PARA" in texto and huella(raiz / "produccion" / "configuracion.json") == antes,
                  f"modelo: {nombre} para sin tocar la configuración ({codigo}; {texto[-300:]})")


def probar_salida():
    """Casos 5 y 6: deshacer y restaurar la salida de un día."""
    raiz = montar("salida")
    predicciones = raiz / "data" / "predicciones"
    archivo = predicciones / "_archivo"
    antes = set(p.name for p in archivo.iterdir())
    codigo, texto = lanzar(raiz, "salida", "--fecha", "2026-11-25")
    nuevas = [p for p in archivo.iterdir() if p.name not in antes]
    comprobar(codigo == 0 and not (predicciones / "2026-11-25").exists() and len(nuevas) == 1
              and json.loads((nuevas[0] / "resumen.json").read_text(encoding="utf-8"))["origen"] == "2015-05-22",
              f"salida: la carpeta del día pasa a _archivo y el día queda sin salida ({codigo}; {texto[-300:]})")
    comprobar((predicciones / "2026-11-24").exists(), "salida: los demás días no se tocan")
    codigo, texto = lanzar(raiz, "salida", "--fecha", "2026-11-25")
    comprobar(codigo == 1 and "PARA" in texto, f"salida: deshacer dos veces seguidas para la segunda ({codigo})")
    # Restaurar la ejecución archivada de antes
    codigo, texto = lanzar(raiz, "salida", "--fecha", "2026-11-25", "--restaurar", "2026-11-25_080000000000")
    restaurada = predicciones / "2026-11-25" / "resumen.json"
    comprobar(codigo == 0 and restaurada.exists()
              and json.loads(restaurada.read_text(encoding="utf-8"))["origen"] == "2015-05-21"
              and (archivo / "2026-11-25_080000000000").exists(),
              f"salida: restaura la ejecución archivada y la deja también en _archivo ({codigo}; {texto[-300:]})")
    # Restaurar con el día ocupado: la que había pasa antes a _archivo
    antes = set(p.name for p in archivo.iterdir())
    codigo, texto = lanzar(raiz, "salida", "--fecha", "2026-11-25", "--restaurar", nuevas[0].name if nuevas else "x")
    nuevas2 = [p for p in archivo.iterdir() if p.name not in antes]
    comprobar(codigo == 0 and len(nuevas2) == 1
              and json.loads((predicciones / "2026-11-25" / "resumen.json").read_text(encoding="utf-8"))["origen"]
              == "2015-05-22",
              f"salida: con el día ocupado, la que había pasa antes a _archivo ({codigo}; {len(nuevas2)})")
    # Lo que tiene que parar sin mover nada
    for nombre, version in (("una versión que no existe", "2026-11-25_no_existe"),
                            ("una versión de otro día", "2026-11-24_x")):
        (archivo / "2026-11-24_x").mkdir(exist_ok=True)
        listado = sorted(p.name for p in predicciones.rglob("*"))
        codigo, texto = lanzar(raiz, "salida", "--fecha", "2026-11-25", "--restaurar", version)
        comprobar(codigo == 1 and "PARA" in texto and sorted(p.name for p in predicciones.rglob("*")) == listado,
                  f"salida: {nombre} para sin mover nada ({codigo}; {texto[-300:]})")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            probar_modelo()
            probar_modelo_que_para()
            probar_salida()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_vuelta_atras borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
