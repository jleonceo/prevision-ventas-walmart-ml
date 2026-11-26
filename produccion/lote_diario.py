"""Lote diario de la previsión del caso 69 (método despliegue, parte 1): lo lanza el envoltorio lote_diario.ps1.

Prevé cada día, sin nadie delante, con el modelo en uso de produccion/configuracion.json. No copia nada de la lógica de
la previsión: llama a produccion/ejecutar.py como función, con el origen que toca y las entradas de la configuración
(apartado lote_diario). Lo que hace, en este orden:
  1. lee la configuración, comprueba su apartado lote_diario y que el intérprete es el del entorno del caso (error 3);
  2. toma como origen el día de ayer según los datos: el último día con venta, por el calendario. Para si ese día no ha
     llegado entero (un producto sin dato) o si no está en el calendario. Con --origen, ese día tiene que ser el que se
     pide: si la venta no llega hasta él, para;
  3. comprueba que la venta avanza: si la última ejecución buena del registro ya prevé desde ese día o desde uno
     posterior, la venta nueva no ha llegado y para (con --repetir se repite a propósito). Comprueba también que el
     origen no cae antes del último día con que se entrenó el modelo en uso: los días a prever estarían en su
     entrenamiento (la entrada no puede ser la tabla con la que se entrenó; despliegue, parte 1);
  4. junta los precios si llegan en varios ficheros (data/raw/ y data/raw/reserva/: el precio de los días a prever se da
     por conocido, reglas, apartado 5, D9), en una carpeta de trabajo que se borra al acabar;
  5. llama a ejecutar.py, que prevé, comprueba sus filas y guarda data/predicciones/AAAA-MM-DD/ con previsiones.parquet y
     resumen.json; si ese día ya había una salida, ejecutar.py la copia antes a data/predicciones/_archivo/;
  6. comprueba lo que quedó: la carpeta del día con su resumen en OK, el origen pedido, tantas filas como se esperaban y
     el modelo en uso;
  7. apunta la ejecución en el registro (una línea JSON por ejecución, sin datos de personas): inicio, fin, duración,
     estado, código, origen, carpeta, modelo y mensaje.

Uso: python -W error produccion/lote_diario.py [--origen AAAA-MM-DD] [--repetir] [--fecha AAAA-MM-DD] [--raiz CARPETA]
Sale con 0 si la previsión del día queda guardada con sus comprobaciones en verde, con 1 si para (la entrada o una
comprobación no lo permiten) y con 2 si hay un fallo técnico.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
CONFIGURACION_REL = "produccion/configuracion.json"
EJECUTAR = Path(__file__).with_name("ejecutar.py")
SCRIPT_REL = "produccion/lote_diario.py"
CLAVES_DEL_LOTE = ("python", "entradas", "registro", "registros_del_envoltorio", "trabajo")
ENTRADAS = ("venta", "precios", "calendario")
CLAVE_PRECIO = ["store_id", "item_id", "wm_yr_wk"]
OBJETIVOS = ("unidades", "dolares")
CODIGO_PARA, CODIGO_FALLO = 1, 2


class Parada(Exception):
    """El lote para con un mensaje claro: no se escribe ninguna previsión."""


# ══ 2. Configuración y entradas ═════════════════════════════════════════════════
def ruta_de(raiz, ruta):
    """Una ruta de la configuración, desde la carpeta del caso si no es absoluta (error 23)."""
    ruta = Path(os.path.expandvars(str(ruta)))
    return ruta if ruta.is_absolute() else raiz / ruta


def leer_configuracion(raiz):
    """La configuración de producción y su apartado lote_diario; para si falta el apartado o una de sus claves."""
    ruta = raiz / CONFIGURACION_REL
    if not ruta.exists():
        raise Parada(f"no existe la configuración {ruta}")
    configuracion = json.loads(ruta.read_text(encoding="utf-8"))
    lote = configuracion.get("lote_diario")
    if not isinstance(lote, dict):
        raise Parada("la configuración no tiene su apartado lote_diario")
    faltan = [k for k in CLAVES_DEL_LOTE if not lote.get(k)] + [f"entradas.{k}" for k in ENTRADAS
                                                                if not (lote.get("entradas") or {}).get(k)]
    if faltan:
        raise Parada(f"al apartado lote_diario de la configuración le faltan: {faltan}")
    return configuracion, lote


def comprobar_interprete(esperado, actual):
    """Para si el intérprete que ejecuta no es el de la configuración (error 3); Windows no distingue mayúsculas."""
    if os.path.normcase(os.path.abspath(esperado)) != os.path.normcase(os.path.abspath(actual)):
        raise Parada(f"el intérprete no es el del entorno del caso: se ejecuta con {actual} y la configuración pide "
                     f"{esperado}")


def rutas_de_entrada(raiz, lote):
    """Las rutas de la venta, los precios (una o varias) y el calendario; para si alguna no existe."""
    entradas = lote["entradas"]
    precios = entradas["precios"] if isinstance(entradas["precios"], list) else [entradas["precios"]]
    rutas = {"venta": ruta_de(raiz, entradas["venta"]), "precios": [ruta_de(raiz, p) for p in precios],
             "calendario": ruta_de(raiz, entradas["calendario"])}
    faltan = [str(r) for r in [rutas["venta"], rutas["calendario"], *rutas["precios"]] if not r.exists()]
    if faltan:
        raise Parada(f"no existen las entradas: {faltan}")
    return rutas


def origen_de_la_venta(venta, calendario):
    """El día de ayer según los datos: el último día con venta, por las fechas del calendario y no por el orden de las
    columnas. Para si un día de la venta no está en el calendario o si el último no ha llegado entero."""
    fecha_de = dict(zip(calendario["d"], pd.to_datetime(calendario["date"], format="%Y-%m-%d")))
    dias = [c for c in venta.columns if str(c).startswith("d_")]
    if not dias:
        raise Parada("la venta no trae ninguna columna de día (d_1, d_2…)")
    fuera = [d for d in dias if d not in fecha_de]
    if fuera:
        raise Parada(f"días de la venta que no están en el calendario: {fuera[:5]}")
    ultimo = max(dias, key=lambda d: fecha_de[d])
    vacios = int(pd.to_numeric(venta[ultimo], errors="coerce").isna().sum())
    if vacios:
        raise Parada(f"la venta de ayer ({fecha_de[ultimo]:%Y-%m-%d}, {ultimo}) no ha llegado entera: {vacios} de "
                     f"{len(venta)} productos sin dato")
    return pd.Timestamp(fecha_de[ultimo])


# ══ 3. El registro y las comprobaciones antes de prever ══════════════════════════
def ultima_ejecucion_buena(ruta):
    """La última línea del registro con estado OK; None si no hay registro o ninguna buena. Para si una línea está rota."""
    if not ruta.exists():
        return None
    ultima = None
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            datos = json.loads(linea)
        except json.JSONDecodeError as error:
            raise Parada(f"el registro {ruta} tiene la línea {numero} rota ({error}): revísalo antes de seguir") from error
        if datos.get("estado") == "OK":
            ultima = datos
    return ultima


def comprobar_que_avanza(origen, previa, repetir):
    """Para si la venta no avanza respecto de la última ejecución buena, salvo que se repita a propósito."""
    if previa is None or repetir:
        return
    anterior = pd.Timestamp(previa["origen"])
    if origen <= anterior:
        raise Parada(f"la venta no llega hasta ayer: acaba el {origen:%Y-%m-%d} y la última ejecución buena (la del "
                     f"{previa.get('fecha')}) ya prevé desde el {anterior:%Y-%m-%d}. ¿Ha llegado la venta nueva? Para "
                     "repetirla a propósito, lanza el lote con --repetir")


def comprobar_fuera_del_entrenamiento(origen, fichas):
    """Para si el origen cae antes del último día con que se entrenó algún modelo: preveríamos días que vio al
    entrenar. Lee fecha_datos de la ficha de cada modelo; para si una ficha no la trae."""
    for objetivo, ficha in fichas.items():
        if not ficha.get("fecha_datos"):
            raise Parada(f"la ficha del modelo de {objetivo} no dice hasta qué día se entrenó (fecha_datos)")
        hasta = pd.Timestamp(ficha["fecha_datos"])
        if origen < hasta:
            raise Parada(f"el origen {origen:%Y-%m-%d} es anterior al último día del entrenamiento del modelo de "
                         f"{objetivo} ({hasta:%Y-%m-%d}): los días a prever estarían en su entrenamiento")


def fichas_del_modelo(carpeta):
    """Las fichas (<objetivo>_versiones.json) de los dos modelos de una carpeta; para si falta alguna."""
    fichas = {}
    for o in OBJETIVOS:
        ruta = carpeta / f"{o}_versiones.json"
        if not ruta.exists():
            raise Parada(f"falta la ficha {ruta}")
        fichas[o] = json.loads(ruta.read_text(encoding="utf-8"))
    return fichas


def juntar_precios(rutas, carpeta):
    """Una sola ruta de precios: la de la única fuente o un CSV con todas juntas, escrito en la carpeta de trabajo.

    Para si una semana de un producto en una tienda llega repetida: no se sabe cuál de los dos precios vale.
    """
    if len(rutas) == 1:
        return rutas[0]
    juntos = pd.concat([pd.read_csv(r, encoding="utf-8") for r in rutas], ignore_index=True)
    repetidas = int(juntos.duplicated(CLAVE_PRECIO).sum())
    if repetidas:
        raise Parada(f"{repetidas} precios repetidos (la misma semana de un producto en una tienda) entre {rutas}")
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = carpeta / "precios.csv"
    juntos.to_csv(salida, index=False, encoding="utf-8")
    return salida


def apuntar(ruta, linea):
    """Añade la línea de esta ejecución al registro, en UTF-8 (error 21)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def cargar_ejecutar():
    """produccion/ejecutar.py como módulo: su trabajo está bajo __main__ y al importarlo solo define funciones."""
    spec = importlib.util.spec_from_file_location("ejecutar_produccion", EJECUTAR)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ══ 4. Principal ════════════════════════════════════════════════════════════════
def prever(args, raiz, configuracion, lote, registro):
    """Las comprobaciones de antes, la previsión con ejecutar.py y las de después; devuelve lo que va al registro."""
    rutas = rutas_de_entrada(raiz, lote)
    venta = pd.read_csv(rutas["venta"], encoding="utf-8")
    calendario = pd.read_csv(rutas["calendario"], encoding="utf-8")
    origen = origen_de_la_venta(venta, calendario)
    registro["origen"] = f"{origen:%Y-%m-%d}"
    if args.origen and pd.Timestamp(args.origen) != origen:
        raise Parada(f"la venta no llega hasta el día que se pide ({args.origen}): su último día es el "
                     f"{origen:%Y-%m-%d}")
    comprobar_que_avanza(origen, ultima_ejecucion_buena(ruta_de(raiz, lote["registro"])), args.repetir)
    if not configuracion.get("modelo_en_uso"):
        raise Parada("no hay modelo en uso en la configuración: lo aprueba el responsable del caso")
    carpeta_modelo = ruta_de(raiz, configuracion["modelo_en_uso"])
    registro["modelo"] = configuracion["modelo_en_uso"]
    comprobar_fuera_del_entrenamiento(origen, fichas_del_modelo(carpeta_modelo))

    # La previsión: ejecutar.py como función, con la carpeta de trabajo que se borra siempre al acabar
    trabajo = ruta_de(raiz, lote["trabajo"]) / f"{datetime.now():%Y%m%d_%H%M%S_%f}"
    try:
        precios = juntar_precios(rutas["precios"], trabajo)
        ejecutar = cargar_ejecutar()
        argumentos = argparse.Namespace(venta=str(rutas["venta"]), precios=str(precios),
                                        calendario=str(rutas["calendario"]), origen=f"{origen:%Y-%m-%d}", modelos=None,
                                        ensayo=False, raiz=str(raiz), fecha=args.fecha)
        try:
            codigo = ejecutar.principal(argumentos)
        except (ejecutar.Parada, ValueError, RuntimeError) as parada:
            raise Parada(f"ejecutar.py para: {parada}") from parada
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
    if codigo != 0:
        raise Parada(f"ejecutar.py sale con {codigo}")

    # Lo que quedó, comprobado con lo leído del disco
    carpeta = ruta_de(raiz, configuracion["rutas"]["predicciones"]) / args.fecha
    ruta_resumen = carpeta / "resumen.json"
    resumen = json.loads(ruta_resumen.read_text(encoding="utf-8")) if ruta_resumen.exists() else {}
    filas = resumen.get("filas") or {}
    comprobaciones = {
        "carpeta_del_dia_con_resumen": ruta_resumen.exists() and (carpeta / "previsiones.parquet").exists(),
        "resumen_en_ok": resumen.get("estado") == "OK",
        "origen_pedido": resumen.get("origen") == f"{origen:%Y-%m-%d}",
        "filas_esperadas": bool(filas) and all((filas.get(o) or {}).get("salida") == (filas.get(o) or {}).get("esperadas")
                                               for o in OBJETIVOS),
        "modelo_en_uso": (resumen.get("modelo") or {}).get("en_uso") is True}
    registro.update({"carpeta": str(carpeta), "comprobaciones": comprobaciones,
                     "filas": {o: (filas.get(o) or {}).get("salida") for o in OBJETIVOS},
                     "huellas_modelo": (resumen.get("modelo") or {}).get("huellas")})
    rojas = [k for k, v in comprobaciones.items() if not v]
    if rojas:
        raise Parada(f"comprobaciones de la salida en rojo: {rojas}")
    return registro


def principal(args):
    """Lanza el lote y apunta la ejecución en el registro; devuelve el código de salida."""
    inicio = time.perf_counter()
    raiz = Path(args.raiz).resolve()
    registro = {"script": SCRIPT_REL, "inicio": datetime.now().isoformat(timespec="seconds"), "fecha": args.fecha,
                "origen": None, "modelo": None, "repetir": bool(args.repetir), "interprete": sys.executable}
    ruta_registro = None
    try:
        configuracion, lote = leer_configuracion(raiz)
        ruta_registro = ruta_de(raiz, lote["registro"])
        comprobar_interprete(ruta_de(raiz, lote["python"]), Path(sys.executable))
        prever(args, raiz, configuracion, lote, registro)
        registro.update({"estado": "OK", "codigo": 0, "mensaje": "previsión del día guardada"})
    except Parada as parada:
        registro.update({"estado": "PARA", "codigo": CODIGO_PARA, "mensaje": str(parada)})
    except Exception as fallo:  # un fallo técnico: se apunta con su tipo y sale con su código
        traceback.print_exc()
        registro.update({"estado": "ERROR", "codigo": CODIGO_FALLO, "mensaje": f"{type(fallo).__name__}: {fallo}"})
    registro["fin"] = datetime.now().isoformat(timespec="seconds")
    registro["duracion_s"] = round(time.perf_counter() - inicio, 1)
    if ruta_registro is not None:
        apuntar(ruta_registro, registro)
    print(f"{registro['estado']} · lote diario · origen {registro['origen']} · {registro['mensaje']} · "
          f"{registro['duracion_s']} s")
    return registro["codigo"]


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Lote diario de la previsión del caso 69")
    argumentos.add_argument("--origen", default=None, help="el día de ayer que se espera, AAAA-MM-DD (opcional)")
    argumentos.add_argument("--repetir", action="store_true", help="repite a propósito un origen ya previsto")
    argumentos.add_argument("--fecha", default=datetime.now().strftime("%Y-%m-%d"),
                            help="carpeta de la ejecución; por defecto, hoy")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    print("intérprete:", sys.executable)
    sys.exit(principal(argumentos.parse_args()))
