"""El lote de la prueba final del caso 69: produccion/ejecutar.py lanzado en cada origen del año guardado.

Rehace dentro del caso el lanzamiento que la petición 28 hizo con un fichero de trabajo de fuera (petición 29, hueco 1).
No es la ejecución diaria (produccion/lote_diario.py) ni mide nada: deja las previsiones que lee
scripts/20_prueba_final.py. No copia la lógica de la previsión: llama a ejecutar.py como función, una vez por origen.

Lo que hace, en este orden:
  1. lee los orígenes de informes/prueba_final.json («que_se_mide»: los 13 ordinarios y las 3 vísperas de festivo, fijados
     en el guion del paso 7 antes de abrir el año) y los horizontes de produccion/configuracion.json. Con --origen, en
     lugar de esos, solo el día que se da (prueba «proximos_dias», petición 32): para si ese día más el horizonte más
     largo pasa del último día del calendario o si la venta no llega hasta él;
  2. para si el destino ya tiene algo: no mezcla un lote con otro ni pisa uno guardado;
  3. por cada origen arma tres CSV con la forma de data/raw/, en <destino>/_entradas/, que se borran al acabar el origen
     (sus huellas quedan en el resumen): la venta de data/raw/ y data/raw/reserva/ unidas por producto y cortadas en el
     origen, de modo que ejecutar.py no ve ningún día posterior; los precios de las dos carpetas hasta la semana anterior
     al último día del horizonte más largo, por el orden de las fechas (el precio de los días a prever se da por
     conocido, reglas, apartado 5, D9); el calendario de data/raw/, entero;
  4. lanza ejecutar.py con los modelos que se le pasan, como ensayo, con una configuración de trabajo en <destino>/_raiz/
     igual a la del caso salvo la carpeta de las predicciones, que es el destino. data/raw/ solo se lee;
  5. junta las salidas en <destino>/previsiones_lote.parquet y escribe <destino>/resumen.json con la forma del lote del
     petición 28, la que lee scripts/20_prueba_final.py;
  6. con --referencia (data/processed/previsiones_prueba_final.parquet) compara, fila a fila y para la variante que se
     dice, la previsión del lote con la que midió la prueba final; con --lote-de-referencia, la previsión sin redondear
     con la de un lote guardado. Deja <destino>/comparacion.json. No cambia ninguna referencia.

Uso: python -W error produccion/lote_prueba_final.py --modelos CARPETA --destino CARPETA [--variante NOMBRE]
     [--referencia PARQUET] [--lote-de-referencia PARQUET] [--raiz CARPETA] [--origen AAAA-MM-DD]
Sale con 0 si el lote queda guardado y lo que se compara coincide, y con 1 si para o no coincide.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
CONFIGURACION_REL = "produccion/configuracion.json"
PRUEBA_FINAL_REL = "informes/prueba_final.json"
EJECUTAR = Path(__file__).with_name("ejecutar.py")
RAW = {"venta": "data/raw/sales_train_evaluation.csv", "precios": "data/raw/sell_prices.csv",
       "calendario": "data/raw/calendar.csv", "venta_reserva": "data/raw/reserva/sales_train_evaluation.csv",
       "precios_reserva": "data/raw/reserva/sell_prices.csv"}
CLAVES = ["prueba", "objetivo", "origen", "store_id", "dept_id", "date"]
RUTAS_ABSOLUTAS = ("contrato", "modulo", "tabla_de_la_particion", "reentrenos")


class Parada(Exception):
    """El lote para con un mensaje claro."""


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def ruta_de(raiz, ruta):
    """Una ruta de la configuración, desde la carpeta del caso si no es absoluta (error 23)."""
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else raiz / ruta


def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_fecha(serie):
    """Fechas con la misma unidad en todas las tablas, para que las uniones casen."""
    return pd.to_datetime(serie).astype("datetime64[us]")


def cargar_ejecutar():
    """produccion/ejecutar.py como módulo: su trabajo está bajo __main__ y al importarlo solo define funciones."""
    spec = importlib.util.spec_from_file_location("ejecutar_produccion", EJECUTAR)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ══ 3. Los orígenes y las entradas de cada uno ═══════════════════════════════════
def pruebas_de_la_prueba_final(prueba_final):
    """Los orígenes de informes/prueba_final.json («que_se_mide»): primero los ordinarios, después las vísperas."""
    que = prueba_final.get("que_se_mide")
    if not que or not que.get("origenes"):
        raise Parada("informes/prueba_final.json no trae que_se_mide con sus orígenes")
    return ([("ordinaria", pd.Timestamp(o)) for o in que["origenes"]]
            + [("festivo", pd.Timestamp(f)) for f in (que.get("festivos") or {}).values()])


def pruebas_con_origen(origen, calendario, venta, horizonte_mayor):
    """El origen dado con --origen en lugar de los de que_se_mide (petición 32): una sola prueba, «proximos_dias».

    Para si el origen más el horizonte más largo pasa del último día del calendario (no se puede prever un día que no
    está) o si la venta no llega hasta el origen (la historia acabaría antes del día del que se prevé).
    """
    fechas = pd.to_datetime(calendario["date"], format="%Y-%m-%d")
    ultimo_calendario = fechas.max()
    if origen + pd.Timedelta(horizonte_mayor, "D") > ultimo_calendario:
        raise Parada(f"el origen {origen:%Y-%m-%d} más {horizonte_mayor} días pasa del último día del calendario "
                     f"({ultimo_calendario:%Y-%m-%d})")
    fecha_de = dict(zip(calendario["d"], fechas))
    dias = [fecha_de[c] for c in venta.columns if str(c).startswith("d_") and c in fecha_de]
    if not dias or max(dias) < origen:
        hasta = f"{max(dias):%Y-%m-%d}" if dias else "ningún día"
        raise Parada(f"la venta no llega hasta el origen {origen:%Y-%m-%d}: acaba en {hasta}")
    return [("proximos_dias", origen)]


def comprobar_destino(destino):
    """Para si el destino ya tiene algo: ni se mezcla un lote con otro ni se pisa uno guardado."""
    if destino.exists() and any(destino.iterdir()):
        raise Parada(f"el destino {destino} ya tiene algo dentro: elige una carpeta vacía o que no exista")


def armar_entradas(origen, venta, precios, calendario, horizonte_mayor, carpeta):
    """Los CSV de venta y precios de un origen; devuelve sus rutas.

    La venta, cortada en el origen: solo los días hasta él, por las fechas del calendario. Los precios, hasta la semana
    anterior a la del último día del horizonte más largo, con las semanas en el orden de sus fechas (el código salta al
    cambiar de año). Para si un precio es de una semana que no está en el calendario.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    fechas = pd.to_datetime(calendario["date"], format="%Y-%m-%d")
    fecha_de = dict(zip(calendario["d"], fechas))
    ids = [c for c in venta.columns if not str(c).startswith("d_")]
    dias = [c for c in venta.columns if str(c).startswith("d_") and fecha_de[c] <= origen]
    rutas = {"venta": carpeta / "venta.csv", "precios": carpeta / "precios.csv"}
    venta[ids + dias].to_csv(rutas["venta"], index=False, encoding="utf-8")
    cal = calendario.assign(_fecha=fechas).sort_values("_fecha", kind="stable")
    orden = list(dict.fromkeys(int(w) for w in cal["wm_yr_wk"]))
    posicion = {w: i for i, w in enumerate(orden)}
    ultimo = origen + pd.Timedelta(horizonte_mayor, "D")
    semana = int(cal.loc[(cal["_fecha"] == ultimo).to_numpy(), "wm_yr_wk"].iloc[0])
    anterior = orden[posicion[semana] - 1]
    pos = precios["wm_yr_wk"].map(posicion)
    if pos.isna().any():
        raise Parada(f"{int(pos.isna().sum())} precios de semanas que no están en el calendario")
    precios[(pos <= posicion[anterior]).to_numpy()].to_csv(rutas["precios"], index=False, encoding="utf-8")
    return rutas


# ══ 4. Comparar con lo guardado ══════════════════════════════════════════════════
def unir(a, b, columnas_a, columnas_b, claves):
    """Une dos tablas por sus claves, con las fechas en la misma unidad; para si una clave se repite."""
    a, b = a[claves + columnas_a].copy(), b[claves + columnas_b].copy()
    for t in (a, b):
        for c in ("origen", "date"):
            t[c] = a_fecha(t[c])
        if t.duplicated(claves).any():
            raise Parada(f"claves repetidas al comparar: {int(t.duplicated(claves).sum())}")
    return a.merge(b, on=claves, how="outer", indicator=True, suffixes=("", "_ref"))


def comparar_con_referencia(lote, referencia, variante, tolerancia):
    """La previsión del lote frente a la que midió la prueba final («modelo» de previsiones_prueba_final.parquet).

    Las dos están acotadas en cero y, en unidades, redondeadas al entero. Coincide si cada fila de la referencia está
    en el lote y ninguna se separa más que la tolerancia. Las filas del lote que la prueba final no mide (los dólares de
    las vísperas de festivo) se cuentan aparte.
    """
    ref = referencia[(referencia["variante"] == variante).to_numpy()]
    unido = unir(lote, ref, ["prevision"], ["modelo"], CLAVES)
    ambos = unido[(unido["_merge"] == "both").to_numpy()]
    dif = np.abs(ambos["prevision"].to_numpy(dtype="float64") - ambos["modelo"].to_numpy(dtype="float64"))
    solo_ref = int((unido["_merge"] == "right_only").sum())
    por_encima = int((~(dif <= tolerancia)).sum())
    return {"variante": variante, "filas": int(len(ambos)), "solo_en_el_lote": int((unido["_merge"] == "left_only").sum()),
            "solo_en_la_referencia": solo_ref, "diferencia_maxima": float(dif.max()) if len(dif) else None,
            "filas_por_encima_de_la_tolerancia": por_encima,
            "coincide": bool(len(ambos) > 0 and solo_ref == 0 and por_encima == 0)}


def comparar_con_lote(lote, guardado, tolerancia):
    """La previsión sin redondear del lote frente a la de un lote guardado, fila a fila; dos vacíos son iguales."""
    unido = unir(lote, guardado, ["prevision_sin_redondear"], ["prevision_sin_redondear"], CLAVES)
    ambos = unido[(unido["_merge"] == "both").to_numpy()]
    x = ambos["prevision_sin_redondear"].to_numpy(dtype="float64")
    y = ambos["prevision_sin_redondear_ref"].to_numpy(dtype="float64")
    vacios = np.isnan(x) & np.isnan(y)
    dif = np.where(vacios, 0.0, np.abs(x - y))
    solo = int((unido["_merge"] != "both").sum())
    por_encima = int((~(dif <= tolerancia)).sum())
    return {"filas": int(len(ambos)), "solo_en_uno": solo, "diferencia_maxima": float(dif.max()) if len(dif) else None,
            "filas_por_encima_de_la_tolerancia": por_encima,
            "coincide": bool(len(ambos) > 0 and solo == 0 and por_encima == 0)}


# ══ 5. Principal ════════════════════════════════════════════════════════════════
def leer_datos(raiz):
    """La venta de data/raw/ y su reserva unidas por producto, los precios de las dos y el calendario."""
    venta_a = pd.read_csv(raiz / RAW["venta"], encoding="utf-8")
    venta_b = pd.read_csv(raiz / RAW["venta_reserva"], encoding="utf-8")
    if not (venta_a["id"].to_numpy() == venta_b["id"].to_numpy()).all():
        raise Parada("la venta y su reserva no traen los mismos productos en el mismo orden")
    venta = pd.concat([venta_a, venta_b[[c for c in venta_b.columns if str(c).startswith("d_")]]], axis=1)
    precios = pd.concat([pd.read_csv(raiz / RAW["precios"], encoding="utf-8"),
                         pd.read_csv(raiz / RAW["precios_reserva"], encoding="utf-8")], ignore_index=True)
    return venta, precios, pd.read_csv(raiz / RAW["calendario"], encoding="utf-8")


def configuracion_de_trabajo(configuracion, raiz, destino):
    """La configuración del caso con las rutas absolutas y las predicciones en el destino."""
    nueva = json.loads(json.dumps(configuracion))
    for clave in RUTAS_ABSOLUTAS:
        nueva["rutas"][clave] = str(ruta_de(raiz, configuracion["rutas"][clave]))
    nueva["rutas"]["predicciones"] = str(destino)
    if configuracion.get("modelo_en_uso"):
        nueva["modelo_en_uso"] = str(ruta_de(raiz, configuracion["modelo_en_uso"]))
    return nueva


def principal(args):
    """Lanza ejecutar.py en cada origen, junta el lote, lo compara si se pide; devuelve el código de salida."""
    raiz = Path(args.raiz).resolve()
    configuracion = json.loads((raiz / CONFIGURACION_REL).read_text(encoding="utf-8"))
    tolerancia = float(configuracion["tolerancia"])
    horizonte_mayor = max(int(h) for h in configuracion["horizontes"].values())
    destino = Path(args.destino).resolve()
    comprobar_destino(destino)
    modelos = ruta_de(raiz, args.modelos).resolve()
    huellas_raw = {rel: huella(raiz / rel) for rel in RAW.values()}
    venta, precios, calendario = leer_datos(raiz)
    # Los orígenes: los de que_se_mide o, con --origen, solo el que se da (petición 32)
    if getattr(args, "origen", None):
        pruebas = pruebas_con_origen(pd.Timestamp(args.origen), calendario, venta, horizonte_mayor)
    else:
        pruebas = pruebas_de_la_prueba_final(json.loads((raiz / PRUEBA_FINAL_REL).read_text(encoding="utf-8")))

    # La configuración de trabajo: la del caso con las predicciones en el destino
    trabajo = destino / "_raiz"
    (trabajo / "produccion").mkdir(parents=True, exist_ok=True)
    (trabajo / CONFIGURACION_REL).write_text(json.dumps(configuracion_de_trabajo(configuracion, raiz, destino),
                                                        ensure_ascii=False, indent=2), encoding="utf-8")
    ejecutar = cargar_ejecutar()
    partes, por_origen = [], []
    try:
        for prueba, origen in pruebas:
            inicio = time.perf_counter()
            rutas = armar_entradas(origen, venta, precios, calendario, horizonte_mayor,
                                   destino / "_entradas" / f"{origen:%Y-%m-%d}")
            with open(rutas["precios"], encoding="utf-8") as f:
                filas_precios = sum(1 for _ in f) - 1
            argumentos = argparse.Namespace(venta=str(rutas["venta"]), precios=str(rutas["precios"]),
                                            calendario=str(raiz / RAW["calendario"]), origen=f"{origen:%Y-%m-%d}",
                                            modelos=str(modelos), ensayo=True, raiz=str(trabajo),
                                            fecha=f"{origen:%Y-%m-%d}")
            try:
                codigo = ejecutar.principal(argumentos)
            except (ejecutar.Parada, ValueError, RuntimeError) as parada:
                raise Parada(f"{prueba} {origen:%Y-%m-%d}: ejecutar.py para: {parada}") from parada
            if codigo != 0:
                raise Parada(f"{prueba} {origen:%Y-%m-%d}: ejecutar.py sale con {codigo}")
            shutil.rmtree(destino / "_entradas" / f"{origen:%Y-%m-%d}")
            carpeta = destino / f"{origen:%Y-%m-%d}"
            r = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
            partes.append(pd.read_parquet(carpeta / "previsiones.parquet").assign(prueba=prueba))
            por_origen.append({"prueba": prueba, "origen": f"{origen:%Y-%m-%d}", "carpeta": f"{origen:%Y-%m-%d}",
                               "fecha_datos": r["fecha_datos"], "filas": r["filas"], "validaciones": r["validaciones"],
                               "entradas": [{"que": k, "sha256": e["sha256"]} for k, e in
                                            zip(("venta", "precios", "calendario"), r["entradas"])],
                               "modelo": {"carpeta": modelos.relative_to(raiz).as_posix()
                                          if modelos.is_relative_to(raiz) else str(modelos),
                                          "huellas": r["modelo"]["huellas"]},
                               "venta_filas": len(venta), "precios_filas": filas_precios,
                               "segundos": round(time.perf_counter() - inicio, 1)})
    finally:
        shutil.rmtree(destino / "_entradas", ignore_errors=True)
        shutil.rmtree(trabajo, ignore_errors=True)

    # El lote junto y su resumen, con la forma que lee scripts/20_prueba_final.py
    lote = pd.concat(partes, ignore_index=True)
    lote.to_parquet(destino / "previsiones_lote.parquet", index=False)
    sin = lote.loc[lote["prevision"].isna().to_numpy(), "motivo"].value_counts().to_dict()
    resumen = {
        "que_es": ("el lote de la prueba final del caso 69: produccion/ejecutar.py lanzado en los orígenes de "
                   f"{PRUEBA_FINAL_REL} (que_se_mide), o en el que se da con --origen, con los modelos de la carpeta "
                   "que se nombra; no es la ejecución diaria"),
        "script": "produccion/lote_prueba_final.py", "variante": args.variante,
        "origen_dado": getattr(args, "origen", None),
        "modelos": modelos.relative_to(raiz).as_posix() if modelos.is_relative_to(raiz) else str(modelos),
        "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "como_se_armo_la_entrada": {
            "venta": f"{RAW['venta']} y {RAW['venta_reserva']} unidas por producto y cortadas en el origen: "
                     "ejecutar.py no ve ningún día posterior",
            "precios": f"{RAW['precios']} y {RAW['precios_reserva']} hasta la semana anterior al último día del "
                       f"horizonte de {horizonte_mayor} días (reglas, apartado 5, D9: el precio se da por conocido)",
            "calendario": f"{RAW['calendario']} entero (se conoce de antemano)",
            "donde": "en <destino>/_entradas/, borradas al acabar cada origen; sus huellas, en cada origen",
            "huellas_origen": huellas_raw},
        "origenes": por_origen,
        "filas_entrada": {"venta_productos_tienda_por_origen": len(venta), "ejecuciones": len(por_origen),
                          "filas_a_prever": int(sum(o["filas"][k]["esperadas"] for o in por_origen for k in o["filas"]))},
        "filas_salida": int(len(lote)), "sin_prevision": {str(k): int(v) for k, v in sin.items()},
        "previsiones_lote": "previsiones_lote.parquet",
        "entradas_sin_cambiar": {rel: huella(raiz / rel) for rel in RAW.values()} == huellas_raw}
    (destino / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"lote: {len(lote)} filas en {len(por_origen)} orígenes; sin previsión: {sin}")

    # La comparación con lo guardado, si se pide
    comparacion = {"tolerancia": tolerancia}
    if args.referencia:
        comparacion["referencia"] = {"ruta": str(args.referencia), "sha256": huella(Path(args.referencia))} | \
            comparar_con_referencia(lote, pd.read_parquet(args.referencia), args.variante, tolerancia)
    if args.lote_de_referencia:
        comparacion["lote_de_referencia"] = {"ruta": str(args.lote_de_referencia),
                                             "sha256": huella(Path(args.lote_de_referencia))} | \
            comparar_con_lote(lote, pd.read_parquet(args.lote_de_referencia), tolerancia)
    comparadas = [v["coincide"] for k, v in comparacion.items() if isinstance(v, dict)]
    comparacion["coincide"] = all(comparadas) if comparadas else None
    (destino / "comparacion.json").write_text(json.dumps(comparacion, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in comparacion.items():
        if isinstance(v, dict):
            print(f"{k}: {v['filas']} filas, diferencia máxima {v['diferencia_maxima']}, coincide {v['coincide']}")
    return 0 if resumen["entradas_sin_cambiar"] and comparacion["coincide"] is not False else 1


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="El lote de la prueba final del caso 69")
    argumentos.add_argument("--modelos", required=True, help="carpeta de los modelos, desde la del caso")
    argumentos.add_argument("--destino", required=True, help="carpeta vacía donde se deja el lote")
    argumentos.add_argument("--variante", default="reentrenado", help="nombre de la variante en la referencia")
    argumentos.add_argument("--referencia", default=None, help="previsiones_prueba_final.parquet para comparar")
    argumentos.add_argument("--lote-de-referencia", default=None, help="previsiones_lote.parquet guardado para comparar")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    argumentos.add_argument("--origen", default=None,
                            help="AAAA-MM-DD: prevé solo desde ese día, en lugar de los orígenes de que_se_mide")
    print("intérprete:", sys.executable)
    try:
        sys.exit(principal(argumentos.parse_args()))
    except Parada as parada:
        print(f"PARA · {parada}")
        sys.exit(1)
    except Exception:  # un fallo técnico, con su traza
        traceback.print_exc()
        sys.exit(1)
