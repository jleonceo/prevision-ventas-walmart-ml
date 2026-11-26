"""Prueba de principio a fin del lote diario del caso 69, antes de activar nada (método despliegue, parte 1, pasos 5 y 6).

Ensaya el lote tal como lo lanzaría la tarea programada (el envoltorio lote_diario.ps1, que llama a lote_diario.py) y la
vuelta atrás, siempre sobre una copia de trabajo: la configuración del caso, data/raw/ y data/raw/reserva/ solo se
leen, y se comprueba con sus huellas que no cambian. Deja informes/despliegue.json con la forma que fija el método.

Lo que hace, en este orden:
  1. monta la carpeta de trabajo (--trabajo, vacía): la configuración del caso con las rutas que no se copian por ruta
     absoluta, una copia de las carpetas del modelo en uso y del anterior, y la venta de trabajo;
  2. el día siguiente simulado: la venta de trabajo es la de data/raw/ con el primer día de la reserva añadido. Se aparta
     ese día y se lanza el lote: prevé desde el último día de data/raw/ y sale fila a fila igual que las previsiones
     que ese modelo dejó guardadas para ese origen (--guardadas-en-uso). Se devuelve el día y se vuelve a lanzar: el
     origen avanza un día, los días previstos se corren uno y la salida del primero queda en _archivo/ porque se repite
     la fecha. Con la misma venta otra vez, el lote para (la venta no llega hasta ayer) sin tocar la salida; con un
     --origen al que la venta no llega, también;
  3. la vuelta atrás del modelo, dos veces seguidas: produccion/vuelta_atras.py pone el anterior (--anterior), el lote
     (con --repetir) da fila a fila sus previsiones guardadas (--guardadas-anterior); otra vez al modelo en uso, la
     configuración vuelve a ser la de antes y el lote da otra vez las del modelo en uso;
  4. la vuelta atrás de la salida de un día: la carpeta del día pasa a _archivo/ y se restaura la del día siguiente
     simulado, que vuelve a ser la del día;
  5. las huellas de la configuración del caso, de data/raw/ y de data/predicciones/ del caso, iguales antes y después;
  6. escribe informes/despliegue.json, con lo comprobado calculado de lo ejecutado (error 24).

Uso: python -W error produccion/ensayo_despliegue.py --trabajo CARPETA --anterior CARPETA --guardadas-en-uso PARQUET
     --guardadas-anterior PARQUET [--repeticion-prueba-final CARPETA] [--informe JSON] [--fecha AAAA-MM-DD]
Sale con 0 si todo lo comprobado sale en verde y con 1 si no.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
PRODUCCION = Path(__file__).resolve().parent
CONFIGURACION_REL = "produccion/configuracion.json"
VERSION_METODO = "20/11/2026"  # versión del método despliegue con que se escribió este script
SCRIPT_REL = "produccion/ensayo_despliegue.py"
INFORME_REL = "informes/despliegue.json"
RAW = ["data/raw/sales_train_evaluation.csv", "data/raw/sell_prices.csv", "data/raw/calendar.csv",
       "data/raw/reserva/sales_train_evaluation.csv", "data/raw/reserva/sell_prices.csv"]
VENTA_RESERVA_REL = "data/raw/reserva/sales_train_evaluation.csv"
CLAVES = ["objetivo", "origen", "store_id", "dept_id", "date"]
RUTAS_DEL_CASO = ("contrato", "modulo", "tabla_de_la_particion")
OBJETIVOS = ("unidades", "dolares")


class Parada(Exception):
    """El ensayo para con un mensaje claro."""


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def huella_de_carpeta(carpeta):
    """Una huella de todo lo que hay en una carpeta: ruta y huella de cada fichero, en orden."""
    if not carpeta.exists():
        return None
    h = hashlib.sha256()
    for ruta in sorted(p for p in carpeta.rglob("*") if p.is_file()):
        h.update(ruta.relative_to(carpeta).as_posix().encode("utf-8"))
        h.update(huella(ruta).encode("utf-8"))
    return h.hexdigest()


def ruta_de(raiz, ruta):
    """Una ruta de la configuración, desde la carpeta del caso si no es absoluta (error 23)."""
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else raiz / ruta


def cargar_lote_diario():
    """produccion/lote_diario.py como módulo, para leer el día de ayer de la venta con su misma regla."""
    spec = importlib.util.spec_from_file_location("lote_diario_ensayo", PRODUCCION / "lote_diario.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def a_json(obj):
    """Un objeto como JSON válido: fechas en ISO, números de NumPy como números y vacíos como null (error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return f"{obj:%Y-%m-%d}"
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ══ 3. Las piezas del ensayo ════════════════════════════════════════════════════
def anadir_dia(venta, reserva, columna):
    """La venta con un día más, la columna de la reserva que se nombra; para si no está o si los productos no casan."""
    if columna not in reserva.columns:
        raise Parada(f"la reserva no trae el día {columna}")
    if len(venta) != len(reserva) or not (venta["id"].to_numpy() == reserva["id"].to_numpy()).all():
        raise Parada("la venta y la reserva no traen los mismos productos en el mismo orden")
    return pd.concat([venta, reserva[[columna]]], axis=1)


def apartar_dia(venta, columna):
    """La venta sin el día que se nombra."""
    return venta.drop(columns=[columna])


def comparar_previsiones(a, b, tolerancia):
    """Dos previsiones fila a fila, unidas por objetivo, origen, serie y fecha, con la previsión sin redondear."""
    x, y = a[CLAVES + ["prevision_sin_redondear"]].copy(), b[CLAVES + ["prevision_sin_redondear"]].copy()
    for t in (x, y):
        for c in ("origen", "date"):
            t[c] = pd.to_datetime(t[c]).astype("datetime64[us]")
    unido = x.merge(y, on=CLAVES, how="outer", indicator=True, suffixes=("", "_otra"), validate="one_to_one")
    ambos = unido[(unido["_merge"] == "both").to_numpy()]
    p = ambos["prevision_sin_redondear"].to_numpy(dtype="float64")
    q = ambos["prevision_sin_redondear_otra"].to_numpy(dtype="float64")
    dif = np.where(np.isnan(p) & np.isnan(q), 0.0, np.abs(p - q))
    solo = int((unido["_merge"] != "both").sum())
    return {"filas": int(len(ambos)), "solo_en_una": solo, "diferencia_maxima": float(dif.max()) if len(dif) else None,
            "coincide": bool(len(ambos) > 0 and solo == 0 and (dif <= tolerancia).all())}


def configuracion_de_trabajo(configuracion, raiz, trabajo):
    """La configuración del caso para la carpeta de trabajo: lo que no se copia, por ruta absoluta al caso; los modelos
    y las predicciones, dentro de la carpeta de trabajo; la venta del lote, la de trabajo; precios y calendario, los del
    caso, que solo se leen."""
    nueva = json.loads(json.dumps(configuracion))
    for clave in RUTAS_DEL_CASO:
        nueva["rutas"][clave] = str(ruta_de(raiz, configuracion["rutas"][clave]))
    entradas = nueva["lote_diario"]["entradas"]
    entradas["venta"] = str(trabajo / "entradas" / "venta.csv")
    precios = entradas["precios"] if isinstance(entradas["precios"], list) else [entradas["precios"]]
    entradas["precios"] = [str(ruta_de(raiz, p)) for p in precios]
    entradas["calendario"] = str(ruta_de(raiz, entradas["calendario"]))
    return nueva


def lanzar_envoltorio(trabajo, *extra):
    """Lanza el lote como lo haría la tarea programada: powershell con el envoltorio; devuelve (código, texto)."""
    orden = ["powershell.exe", "-NoProfile", "-File", str(PRODUCCION / "lote_diario.ps1"), "-Raiz", str(trabajo),
             *map(str, extra)]
    proc = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    return proc.returncode, proc.stdout + proc.stderr


def volver(trabajo, *argumentos):
    """Lanza produccion/vuelta_atras.py sobre la carpeta de trabajo; devuelve (código, texto)."""
    proc = subprocess.run([sys.executable, "-W", "error", str(PRODUCCION / "vuelta_atras.py"), *map(str, argumentos),
                           "--raiz", str(trabajo)], capture_output=True, text=True, encoding="utf-8", timeout=600,
                          env={**os.environ, "PYTHONUTF8": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def leer_dia(trabajo, fecha):
    """La salida de un día en la carpeta de trabajo: previsiones y resumen, o (None, None)."""
    carpeta = trabajo / "data" / "predicciones" / fecha
    if not (carpeta / "resumen.json").exists():
        return None, None
    return (pd.read_parquet(carpeta / "previsiones.parquet"),
            json.loads((carpeta / "resumen.json").read_text(encoding="utf-8")))


def archivadas(trabajo, fecha):
    """Las ejecuciones de un día que hay en _archivo, ordenadas por nombre."""
    archivo = trabajo / "data" / "predicciones" / "_archivo"
    return sorted(archivo.glob(f"{fecha}_*")) if archivo.exists() else []


# ══ 4. Principal ════════════════════════════════════════════════════════════════
def ensayar(args, r):
    """Monta la carpeta de trabajo y ensaya el lote y la vuelta atrás; deja en r lo medido."""
    raiz = CASO
    configuracion = json.loads((raiz / CONFIGURACION_REL).read_text(encoding="utf-8"))
    tolerancia = float(configuracion["tolerancia"])
    en_uso = configuracion["modelo_en_uso"]
    anterior = Path(args.anterior).as_posix()
    trabajo = Path(args.trabajo).resolve()
    if trabajo.exists() and any(trabajo.iterdir()):
        raise Parada(f"la carpeta de trabajo {trabajo} ya tiene algo dentro")
    fecha = args.fecha

    # 4.1 La carpeta de trabajo: configuración, copia de los dos modelos y venta de trabajo
    (trabajo / "produccion").mkdir(parents=True, exist_ok=True)
    (trabajo / "entradas").mkdir(parents=True, exist_ok=True)
    (trabajo / CONFIGURACION_REL).write_text(json.dumps(configuracion_de_trabajo(configuracion, raiz, trabajo),
                                                        ensure_ascii=False, indent=2), encoding="utf-8")
    for carpeta in (en_uso, anterior):
        shutil.copytree(ruta_de(raiz, carpeta), trabajo / carpeta)
    lote = cargar_lote_diario()
    entradas = configuracion["lote_diario"]["entradas"]
    venta = pd.read_csv(ruta_de(raiz, entradas["venta"]), encoding="utf-8")
    reserva = pd.read_csv(raiz / VENTA_RESERVA_REL, encoding="utf-8")
    calendario = pd.read_csv(ruta_de(raiz, entradas["calendario"]), encoding="utf-8")
    ayer = lote.origen_de_la_venta(venta, calendario)
    fecha_de = dict(zip(calendario["d"], pd.to_datetime(calendario["date"], format="%Y-%m-%d")))
    dias_reserva = sorted((c for c in reserva.columns if str(c).startswith("d_")), key=lambda d: fecha_de[d])
    siguiente = dias_reserva[0]
    con_dia = anadir_dia(venta, reserva, siguiente)
    ruta_venta = trabajo / "entradas" / "venta.csv"
    r["fecha_datos"] = ayer

    # 4.2 El día siguiente simulado: se aparta el día, se lanza; se devuelve, se vuelve a lanzar
    apartar_dia(con_dia, siguiente).to_csv(ruta_venta, index=False, encoding="utf-8")
    codigo_a, texto_a = lanzar_envoltorio(trabajo, "--fecha", fecha)
    prev_a, res_a = leer_dia(trabajo, fecha)
    guardadas_en_uso = pd.read_parquet(args.guardadas_en_uso)
    igual_a = comparar_previsiones(prev_a, guardadas_en_uso, tolerancia) if prev_a is not None else None
    con_dia.to_csv(ruta_venta, index=False, encoding="utf-8")
    codigo_b, texto_b = lanzar_envoltorio(trabajo, "--fecha", fecha)
    prev_b, res_b = leer_dia(trabajo, fecha)
    copias = archivadas(trabajo, fecha)
    prev_archivada = pd.read_parquet(copias[0] / "previsiones.parquet") if len(copias) == 1 else None
    huella_dia = huella_de_carpeta(trabajo / "data" / "predicciones" / fecha)
    codigo_c, texto_c = lanzar_envoltorio(trabajo, "--fecha", fecha)
    codigo_d, texto_d = lanzar_envoltorio(trabajo, "--fecha", fecha, "--origen",
                                          f"{fecha_de[siguiente] + pd.Timedelta(1, 'D'):%Y-%m-%d}")
    sin_tocar = (huella_de_carpeta(trabajo / "data" / "predicciones" / fecha) == huella_dia
                 and len(archivadas(trabajo, fecha)) == len(copias))
    origen_b = pd.Timestamp(res_b["origen"]) if res_b else None
    r["prueba_de_principio_a_fin"] = {
        "como": ("el envoltorio lote_diario.ps1, como lo lanzaría la tarea programada, sobre una carpeta de trabajo con "
                 "la configuración del caso; la venta de trabajo es la de data/raw/ con el primer día de la reserva "
                 f"({siguiente}) añadido, que se aparta y se devuelve"),
        "dia_apartado": {"columna": siguiente, "fecha": fecha_de[siguiente]},
        "primera": {"codigo": codigo_a, "origen": res_a and res_a.get("origen"),
                    "modelo": res_a and res_a["modelo"].get("huellas"), "filas": res_a and res_a.get("filas"),
                    "igual_que_las_guardadas": igual_a, "guardadas": str(args.guardadas_en_uso)},
        "con_el_dia_devuelto": {"codigo": codigo_b, "origen": res_b and res_b.get("origen"),
                                "archivadas_del_dia": [c.name for c in copias],
                                "la_archivada_es_la_primera": bool(prev_archivada is not None and prev_a is not None
                                                                   and prev_archivada.equals(prev_a))},
        "misma_venta_otra_vez": {"codigo": codigo_c, "mensaje": [x for x in texto_c.splitlines() if "PARA" in x][-1:]},
        "origen_al_que_no_llega": {"codigo": codigo_d, "mensaje": [x for x in texto_d.splitlines() if "PARA" in x][-1:]},
        "registro_del_envoltorio": sorted(p.name for p in (trabajo / "data" / "predicciones" / "_registros").glob("*.log"))}
    validaciones = {
        "primera_sale_bien": codigo_a == 0 and res_a is not None and res_a.get("origen") == f"{ayer:%Y-%m-%d}",
        "primera_igual_que_las_guardadas": bool(igual_a and igual_a["coincide"]),
        "con_el_dia_devuelto_avanza_un_dia": codigo_b == 0 and origen_b == ayer + pd.Timedelta(1, "D"),
        "dias_previstos_corridos_un_dia": bool(prev_a is not None and prev_b is not None
                                               and pd.to_datetime(prev_b["date"]).min()
                                               == pd.to_datetime(prev_a["date"]).min() + pd.Timedelta(1, "D")),
        "la_primera_queda_en_archivo": r["prueba_de_principio_a_fin"]["con_el_dia_devuelto"]["la_archivada_es_la_primera"],
        "misma_venta_para_sin_tocar": codigo_c == 1 and "no llega hasta ayer" in texto_c and sin_tocar,
        "origen_al_que_no_llega_para": codigo_d == 1 and "no llega" in texto_d}

    # 4.3 La vuelta atrás del modelo, dos veces seguidas, con sus previsiones guardadas
    con_dia.pipe(apartar_dia, siguiente).to_csv(ruta_venta, index=False, encoding="utf-8")
    config_antes = json.loads((trabajo / CONFIGURACION_REL).read_text(encoding="utf-8"))
    decide = "ensayo de la vuelta atrás de la petición 29 sobre una copia de trabajo; en el caso lo decide el responsable del caso"
    codigo_v1, texto_v1 = volver(trabajo, "modelo", "--a", anterior, "--decide", decide)
    codigo_e, _ = lanzar_envoltorio(trabajo, "--fecha", fecha, "--repetir")
    prev_e, res_e = leer_dia(trabajo, fecha)
    igual_e = comparar_previsiones(prev_e, pd.read_parquet(args.guardadas_anterior), tolerancia) \
        if prev_e is not None else None
    codigo_v2, texto_v2 = volver(trabajo, "modelo", "--a", en_uso, "--decide", decide)
    config_despues = json.loads((trabajo / CONFIGURACION_REL).read_text(encoding="utf-8"))
    codigo_g, _ = lanzar_envoltorio(trabajo, "--fecha", fecha, "--repetir")
    prev_g, res_g = leer_dia(trabajo, fecha)
    igual_g = comparar_previsiones(prev_g, guardadas_en_uso, tolerancia) if prev_g is not None else None
    r["vuelta_atras"]["ensayo_modelo"] = {
        "a_el_anterior": {"codigo": codigo_v1, "texto": texto_v1.strip().splitlines()[-1:], "lote": codigo_e,
                          "modelo": res_e and res_e["modelo"].get("huellas"), "igual_que_sus_guardadas": igual_e,
                          "guardadas": str(args.guardadas_anterior)},
        "otra_vez_a_el_en_uso": {"codigo": codigo_v2, "texto": texto_v2.strip().splitlines()[-1:], "lote": codigo_g,
                                 "igual_que_sus_guardadas": igual_g},
        "copias_de_la_configuracion": sorted(p.name for p in (trabajo / "produccion" / "_archivo").glob("*.json"))}
    sin_marcas = {k: v for k, v in config_despues.items() if k not in ("modelo_en_uso_aprobado_por", "vuelta_atras")}
    validaciones |= {
        "vuelta_al_anterior_da_sus_previsiones": codigo_v1 == 0 and codigo_e == 0 and bool(igual_e and igual_e["coincide"]),
        "vuelta_otra_vez_da_las_del_en_uso": codigo_v2 == 0 and codigo_g == 0 and bool(igual_g and igual_g["coincide"]),
        "configuracion_vuelve_a_la_de_antes": sin_marcas == {k: v for k, v in config_antes.items()
                                                             if k != "modelo_en_uso_aprobado_por"}}

    # 4.4 La vuelta atrás de la salida de un día: se aparta y se restaura la del día siguiente simulado
    del_siguiente = [c for c in archivadas(trabajo, fecha)
                     if json.loads((c / "resumen.json").read_text(encoding="utf-8")).get("origen")
                     == f"{fecha_de[siguiente]:%Y-%m-%d}"]
    codigo_s1, texto_s1 = volver(trabajo, "salida", "--fecha", fecha)
    apartada = not (trabajo / "data" / "predicciones" / fecha).exists()
    codigo_s2, texto_s2 = volver(trabajo, "salida", "--fecha", fecha, "--restaurar", del_siguiente[0].name) \
        if del_siguiente else (None, "no hay ejecución archivada del día siguiente")
    prev_s, _ = leer_dia(trabajo, fecha)
    r["vuelta_atras"]["ensayo_salida"] = {
        "deshacer": {"codigo": codigo_s1, "texto": texto_s1.strip().splitlines()[-1:], "el_dia_queda_sin_salida": apartada},
        "restaurar": {"codigo": codigo_s2, "version": del_siguiente[0].name if del_siguiente else None,
                      "texto": texto_s2.strip().splitlines()[-1:]}}
    validaciones |= {
        "deshacer_la_salida_la_aparta": codigo_s1 == 0 and apartada,
        "restaurar_devuelve_la_del_dia_siguiente": codigo_s2 == 0 and prev_s is not None and prev_b is not None
                                                   and prev_s.equals(prev_b)}
    return validaciones


def principal(args):
    """Mide las huellas, ensaya, comprueba que nada del caso cambió y escribe informes/despliegue.json."""
    raiz = CASO
    configuracion = json.loads((raiz / CONFIGURACION_REL).read_text(encoding="utf-8"))
    lote = configuracion["lote_diario"]
    antes = {"configuracion": huella(raiz / CONFIGURACION_REL), "raw": {rel: huella(raiz / rel) for rel in RAW},
             "predicciones_del_caso": huella_de_carpeta(ruta_de(raiz, configuracion["rutas"]["predicciones"]))}
    r = {"metodo": "despliegue", "version_metodo": version_metodo(), "script": SCRIPT_REL, "fecha_datos": None,
         "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": {"python": sys.version.split()[0], "pandas": pd.__version__, "ejecutable": sys.executable},
         "entradas": [{"ruta": rel, "sha256": h} for rel, h in antes["raw"].items()]
         + [{"ruta": CONFIGURACION_REL, "sha256": antes["configuracion"]}],
         "resultado": {}, "pendientes": [],
         "forma": {"tipo": "lotes", "por_que": ("la previsión es diaria y la usa quien hace el pedido: un lote que deja "
                                                "cada día su salida (planteamientos del caso, paso 1)"),
                   "servidor": ("una carpeta del caso, con solo lo que el servidor necesitaría: es una simplificación, "
                                "no lo ideal (método despliegue, apartado 2)")},
         "configuracion": {"ruta": CONFIGURACION_REL, "modelo_en_uso": configuracion.get("modelo_en_uso"),
                           "modelo_en_uso_aprobado_por": configuracion.get("modelo_en_uso_aprobado_por"),
                           "lote_diario": lote, "salida": configuracion["rutas"]["predicciones"] + "/AAAA-MM-DD/"},
         "lote": {"script": "produccion/lote_diario.py", "envoltorio": "produccion/lote_diario.ps1",
                  "llama_a": "produccion/ejecutar.py, como función (no copia su lógica)",
                  "como_se_lanza": "powershell.exe -NoProfile -File <caso>\\produccion\\lote_diario.ps1",
                  "argumentos": {"--repetir": "repite a propósito un origen ya previsto",
                                 "--origen AAAA-MM-DD": "el día de ayer que se espera; si la venta no llega, para",
                                 "--fecha AAAA-MM-DD": "carpeta de la ejecución; por defecto, hoy"},
                  "codigos_de_salida": {"0": "previsión del día guardada", "1": "para: la entrada o una comprobación no "
                                        "lo permiten", "2": "fallo técnico"},
                  "deja": {"salida": "data/predicciones/AAAA-MM-DD/previsiones.parquet y resumen.json",
                           "archivo": "data/predicciones/_archivo/: la salida anterior del mismo día, antes de pisarla",
                           "registro": lote["registro"],
                           "registro_del_envoltorio": lote["registros_del_envoltorio"] + "/lote_diario_AAAAMMDD_HHMMSS.log"}},
         "programacion": {"estado": "sin crear ni activar: lo decide el responsable del caso (puerta 6)",
                          "como": ("el Programador de tareas de Windows llama solo al envoltorio, sin /WD ni privilegios "
                                   "altos, con dos opciones que el asistente básico no marca: que se ejecute aunque "
                                   "nadie haya iniciado sesión (la contraseña la escribe la persona) y que se "
                                   "ejecute en cuanto se pueda si se perdió un inicio"),
                          "hora": None, "zona": "hora local del equipo (el Programador de tareas usa la hora local)",
                          "probada": ("solo a mano: «Ejecutar» o el envoltorio desde la consola prueban la acción, no el "
                                      "desencadenador")},
         "vuelta_atras": {
             "modelo": {"que_se_restaura": "el modelo en uso de la configuración; el código no cambia",
                        "comando": ("python -W error produccion/vuelta_atras.py modelo --a modelos/reentrenos/<carpeta> "
                                    "--decide \"el responsable del caso, DD/MM/AAAA: «…» (referencia de la decisión)\""),
                        "anterior": Path(args.anterior).as_posix(),
                        "deja": "una copia de la configuración de antes en produccion/_archivo/"},
             "salida_de_un_dia": {"comando": ("python -W error produccion/vuelta_atras.py salida --fecha AAAA-MM-DD "
                                              "[--restaurar AAAA-MM-DD_<hora>]"),
                                  "deja": "la carpeta del día en data/predicciones/_archivo/; no se borra nada"}},
         "avisos": {"por_error": ("el código de salida del envoltorio (1 para, 2 fallo técnico), la línea del registro "
                                  "con su estado y su mensaje y el registro del envoltorio con lo que imprimió"),
                    "por_ausencia": ("sin montar: cuántas ejecuciones se esperan por ventana y quién se entera si "
                                     "faltan se fija con la cadencia (puerta 6)"),
                    "quien_los_lee": None},
         "teoria_aplicada": ["40.3 Ejecución por lotes: configuración como única fuente, envoltorio, cada lote aparte, "
                             "registro de cada ejecución, alertas por fallo y por ausencia, probar con un periodo nuevo "
                             "simulado antes de activar"],
         "datos_personales": {"proteccion_datos_json": (raiz / "config/fuentes/proteccion-datos.json").exists(),
                              "columnas_de_personas_usadas": [],
                              "nota": "ventas por departamento y tienda; el registro no lleva datos de personas"}}
    validaciones = ensayar(args, r)

    # La ejecución real más reciente del caso, si la hay, leída de su registro
    ruta_registro = ruta_de(raiz, lote["registro"])
    lineas = [json.loads(x) for x in ruta_registro.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if ruta_registro.exists() else []
    r["ejecuciones_en_el_caso"] = lineas
    # La repetición del lote de la prueba final, si se pasa su carpeta (petición 29, hueco 1)
    if args.repeticion_prueba_final:
        carpeta = Path(args.repeticion_prueba_final)
        r["repeticion_prueba_final"] = {"carpeta": str(carpeta), "script": "produccion/lote_prueba_final.py",
                                        "comparacion": json.loads((carpeta / "comparacion.json").read_text(encoding="utf-8"))}
        validaciones["prueba_final_se_repite_igual"] = r["repeticion_prueba_final"]["comparacion"].get("coincide") is True

    # Nada del caso cambió
    despues = {"configuracion": huella(raiz / CONFIGURACION_REL), "raw": {rel: huella(raiz / rel) for rel in RAW},
               "predicciones_del_caso": huella_de_carpeta(ruta_de(raiz, configuracion["rutas"]["predicciones"]))}
    validaciones |= {"configuracion_del_caso_sin_tocar": despues["configuracion"] == antes["configuracion"],
                     "raw_sin_tocar": despues["raw"] == antes["raw"],
                     "predicciones_del_caso_sin_tocar": despues["predicciones_del_caso"] == antes["predicciones_del_caso"]}
    r["huellas"] = {"antes": antes, "despues": despues}
    r["validaciones"] = validaciones
    rojas = [k for k, v in validaciones.items() if v is not True]
    r["pendientes"] = [
        {"id": "P-01", "tabla": "tarea programada", "columna": "programación",
         "pregunta": "¿Se crea la tarea diaria en el Programador de tareas y a qué hora (puerta 6)?",
         "opciones": ["crearla a la hora que diga el responsable del caso, con las dos opciones de programacion.md",
                      "no crearla todavía"]},
        {"id": "P-02", "tabla": "avisos", "columna": "por error y por ausencia",
         "pregunta": "¿Quién lee los avisos y cuántas ejecuciones se esperan por semana?",
         "opciones": ["el responsable del caso, con una ejecución por día", "otra persona o cadencia"]}]
    if rojas:
        r["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"comprobaciones en rojo: {rojas}",
                          "artefactos": [INFORME_REL], "siguiente": "revisar las comprobaciones en rojo"}
    else:
        r["resultado"] = {"estado": "AVISO", "riesgo": "medio",
                          "resumen": (f"el lote diario y su vuelta atrás salen bien de principio a fin en una copia de "
                                      f"trabajo ({len(validaciones)} comprobaciones en verde); la tarea programada y "
                                      "los avisos esperan al responsable del caso (puerta 6)"),
                          "artefactos": [INFORME_REL, "produccion/lote_diario.md"],
                          "siguiente": "El responsable del caso decide la programación y quién lee los avisos (puerta 6)"}
    return r


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Prueba de principio a fin del lote diario del caso 69")
    argumentos.add_argument("--trabajo", required=True, help="carpeta de trabajo vacía, fuera de los datos del caso")
    argumentos.add_argument("--anterior", required=True, help="carpeta del modelo al que se vuelve en el ensayo")
    argumentos.add_argument("--guardadas-en-uso", required=True, help="previsiones guardadas del modelo en uso")
    argumentos.add_argument("--guardadas-anterior", required=True, help="previsiones guardadas del modelo anterior")
    argumentos.add_argument("--repeticion-prueba-final", default=None, help="carpeta de lote_prueba_final.py")
    argumentos.add_argument("--informe", default=str(CASO / INFORME_REL), help="dónde se escribe despliegue.json")
    argumentos.add_argument("--fecha", default=datetime.now().strftime("%Y-%m-%d"), help="carpeta de la ejecución")
    args = argumentos.parse_args()
    print("intérprete:", sys.executable)
    try:
        resultado = principal(args)
    except Exception as fallo:  # una parada o un fallo técnico dejan el JSON con su estado
        traceback.print_exc()
        resultado = {"metodo": "despliegue", "script": SCRIPT_REL, "fecha_ejecucion": datetime.now().isoformat(
            timespec="seconds"), "resultado": {"estado": "PARADO" if isinstance(fallo, Parada) else "ERROR",
                                               "riesgo": "alto", "resumen": f"{type(fallo).__name__}: {fallo}",
                                               "artefactos": [INFORME_REL], "siguiente": "revisar el motivo"},
                     "pendientes": []}
    Path(args.informe).write_text(json.dumps(a_json(resultado), ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    for k, v in (resultado.get("validaciones") or {}).items():
        print(f"  {k}: {v}")
    sys.exit(0 if resultado["resultado"]["estado"] in ("OK", "AVISO") else 1)
