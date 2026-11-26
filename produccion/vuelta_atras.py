"""Vuelta atrás de la producción del caso 69 (método despliegue, «lo común»): el modelo en uso y la salida de un día.

Dos órdenes, cada una con su comprobación antes de tocar nada. Ninguna borra: lo que se aparta pasa a un archivo.
  - modelo: pone en produccion/configuracion.json otro modelo en uso (el anterior, o el que se diga), con quién lo
    decide. Antes comprueba que la carpeta trae los dos modelos con su ficha, que cada fichero es el de su ficha (huella)
    y que las versiones de scikit-learn y pandas son las del entorno: sin abrir el joblib, que ejecuta código al
    cargarse. Guarda antes una copia de la configuración en produccion/_archivo/. Cambiar el modelo en uso lo decide
    el responsable del caso (R-022, «Cómo deshacer»);
  - salida: deshace la salida de un día. La carpeta data/predicciones/AAAA-MM-DD/ pasa a data/predicciones/_archivo/;
    con --restaurar, la ejecución archivada que se nombra vuelve a ser la del día (se copia y sigue en el archivo).
    Para sin mover nada si no hay nada que deshacer o si la versión no existe o es de otro día.

Uso: python -W error produccion/vuelta_atras.py modelo --a CARPETA --decide TEXTO [--raiz CARPETA]
     python -W error produccion/vuelta_atras.py salida --fecha AAAA-MM-DD [--restaurar NOMBRE] [--raiz CARPETA]
Sale con 0 si la vuelta atrás queda hecha y con 1 si para.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import importlib
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
CONFIGURACION_REL = "produccion/configuracion.json"
ARCHIVO_CONFIGURACION_REL = "produccion/_archivo"
OBJETIVOS = ("unidades", "dolares")
VERSIONES_QUE_DECIDEN = ("scikit-learn", "pandas")


class Parada(Exception):
    """La vuelta atrás para con un mensaje claro sin tocar nada."""


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def ruta_de(raiz, ruta):
    """Una ruta de la configuración, desde la carpeta del caso si no es absoluta (error 23)."""
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else raiz / ruta


def leer_configuracion(raiz):
    """La configuración de producción, en UTF-8 (error 21)."""
    return json.loads((raiz / CONFIGURACION_REL).read_text(encoding="utf-8"))


def importar_modulo(raiz, configuracion):
    """scripts/produccion_prevision.py, para la huella y las versiones: las mismas que comprueba la carga del modelo."""
    carpeta = str(ruta_de(raiz, configuracion["rutas"]["modulo"]))
    if carpeta not in sys.path:
        sys.path.insert(0, carpeta)
    return importlib.import_module("produccion_prevision")


def marca():
    """Una marca de tiempo para el nombre de lo que se archiva: no se repite entre dos órdenes seguidas."""
    return f"{datetime.now():%Y%m%d_%H%M%S_%f}"


# ══ 3. El modelo en uso ═════════════════════════════════════════════════════════
def comprobar_modelos(pp, carpeta):
    """Para si a la carpeta le falta un modelo o su ficha, si un fichero no es el de su ficha o si las versiones que
    deciden la carga no son las del entorno. No abre ningún joblib."""
    if not carpeta.is_dir():
        raise Parada(f"no existe la carpeta del modelo {carpeta}")
    actuales = pp.versiones()
    for o in OBJETIVOS:
        modelo, ficha = carpeta / f"{o}.joblib", carpeta / f"{o}_versiones.json"
        if not modelo.exists() or not ficha.exists():
            raise Parada(f"a {carpeta} le falta el modelo de {o} o su ficha")
        datos = json.loads(ficha.read_text(encoding="utf-8"))
        if pp.huella(modelo) != datos.get("huella"):
            raise Parada(f"{modelo.name} de {carpeta} no es el fichero que dice su ficha (huella distinta)")
        distintas = {k: (datos.get("versiones", {}).get(k), actuales[k]) for k in VERSIONES_QUE_DECIDEN
                     if datos.get("versiones", {}).get(k) != actuales[k]}
        if distintas:
            raise Parada(f"el modelo de {o} se guardó con otras versiones (guardado, actual): {distintas}")


def volver_al_modelo(raiz, destino, decide):
    """Pone otro modelo en uso en la configuración, con quién lo decide, tras guardar una copia de la de antes."""
    if not decide or not decide.strip():
        raise Parada("hay que decir quién decide la vuelta atrás (--decide)")
    configuracion = leer_configuracion(raiz)
    pp = importar_modulo(raiz, configuracion)
    actual = configuracion.get("modelo_en_uso")
    destino_rel = Path(destino).as_posix()
    if actual and ruta_de(raiz, actual).resolve() == ruta_de(raiz, destino_rel).resolve():
        raise Parada(f"{destino_rel} ya es el modelo en uso: no hay nada que cambiar")
    comprobar_modelos(pp, ruta_de(raiz, destino_rel))
    # La copia de la configuración de antes, en su archivo, antes de escribir la nueva
    archivo = raiz / ARCHIVO_CONFIGURACION_REL
    archivo.mkdir(parents=True, exist_ok=True)
    copia = archivo / f"configuracion_{marca()}.json"
    shutil.copy2(raiz / CONFIGURACION_REL, copia)
    nueva = dict(configuracion)
    nueva["modelo_en_uso"] = destino_rel
    nueva["modelo_en_uso_aprobado_por"] = decide.strip()
    nueva["vuelta_atras"] = {"desde": actual, "a": destino_rel, "fecha": datetime.now().isoformat(timespec="seconds"),
                             "copia_de_antes": copia.relative_to(raiz).as_posix(), "decide": decide.strip()}
    (raiz / CONFIGURACION_REL).write_text(json.dumps(nueva, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK · modelo en uso: {actual} → {destino_rel}; copia de la configuración de antes en "
          f"{copia.relative_to(raiz).as_posix()}")


# ══ 4. La salida de un día ══════════════════════════════════════════════════════
def deshacer_salida(raiz, fecha, restaurar=None):
    """Aparta la salida de un día a _archivo y, si se pide, restaura una ejecución archivada de ese mismo día."""
    configuracion = leer_configuracion(raiz)
    predicciones = ruta_de(raiz, configuracion["rutas"]["predicciones"])
    dia = predicciones / fecha
    archivo = predicciones / "_archivo"
    # Todo se comprueba antes de mover nada
    origen_restaurado = None
    if restaurar is not None:
        origen_restaurado = archivo / restaurar
        if not restaurar.startswith(f"{fecha}_") or Path(restaurar).name != restaurar:
            raise Parada(f"{restaurar} no es una ejecución archivada del día {fecha}")
        if not (origen_restaurado / "resumen.json").exists():
            raise Parada(f"no existe la ejecución archivada {origen_restaurado} (o no trae su resumen)")
    elif not dia.exists():
        raise Parada(f"no hay salida del día {fecha} que deshacer en {predicciones}")
    if dia.exists():
        apartada = archivo / f"{fecha}_{marca()}_deshecha"
        archivo.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dia), str(apartada))
        print(f"OK · la salida del {fecha} pasa a {apartada.relative_to(predicciones).as_posix()}")
    if origen_restaurado is not None:
        shutil.copytree(origen_restaurado, dia)
        print(f"OK · la salida del {fecha} vuelve a ser {restaurar} (sigue también en el archivo)")


# ══ 5. Principal ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Vuelta atrás de la producción del caso 69")
    ordenes = argumentos.add_subparsers(dest="orden", required=True)
    modelo = ordenes.add_parser("modelo", help="pone otro modelo en uso en la configuración")
    modelo.add_argument("--a", required=True, help="carpeta del modelo, desde la del caso")
    modelo.add_argument("--decide", required=True, help="quién lo decide, con sus palabras y su código")
    salida = ordenes.add_parser("salida", help="deshace la salida de un día")
    salida.add_argument("--fecha", required=True, help="carpeta del día, AAAA-MM-DD")
    salida.add_argument("--restaurar", default=None, help="ejecución archivada de ese día que vuelve a ser la suya")
    for sub in (modelo, salida):
        sub.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    args = argumentos.parse_args()
    print("intérprete:", sys.executable)
    try:
        raiz_caso = Path(args.raiz).resolve()
        if args.orden == "modelo":
            volver_al_modelo(raiz_caso, args.a, args.decide)
        else:
            deshacer_salida(raiz_caso, args.fecha, args.restaurar)
        codigo = 0
    except Parada as parada:
        print(f"PARA · {parada}")
        codigo = 1
    except Exception:  # un fallo técnico, con su traza
        traceback.print_exc()
        codigo = 1
    sys.exit(codigo)
