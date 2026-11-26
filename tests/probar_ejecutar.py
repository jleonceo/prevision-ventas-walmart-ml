"""Prueba de produccion/ejecutar.py, con datos pequeños escritos aquí.

No lee ningún dato del caso. Toma los datos de juguete de tests/probar_produccion_prevision.py (venta, precios y
calendario con la forma de data/raw/, dos tiendas y dos departamentos, 140 días), monta en tests/tmp_ejecutar/ una
carpeta con la estructura del caso, reentrena en ella un modelo pequeño con produccion/reentrenar.py y lanza
produccion/ejecutar.py como proceso aparte con -W error, con la venta hasta el origen en CSV.

Los casos, los de quien quiere romperlo incluidos (programacion-del-caso, error 35):
  1. base: una fila por serie y día a prever (horizonte de cada objetivo), ninguna vacía sin motivo ni negativa,
     unidades enteras en la salida, la previsión sin redondear al lado, resumen con sus validaciones y la ficha que
     cuadra; la previsión no se llama como el objetivo;
  2. falta una columna (sell_price en los precios): para con un mensaje claro;
  3. un número llega como texto (un día de la venta): para;
  4. la historia no llega hasta el día de origen que se pide (la entrada del día anterior): para; y una venta que llega
     más allá del origen pedido, también;
  5. una combinación nueva sin 28 días de historia sale con la previsión vacía y su motivo; las demás, previstas;
  6. las series llegan en otro orden: cada una recibe la suya;
  7. una ficha que no cuadra: no carga el modelo y para;
  8. sin modelo en uso y sin modelo a mano: para;
  9. una segunda ejecución el mismo día copia antes la primera a _archivo/;
 10. ejecutar.py no llama a ningún paso que quita filas (validación 6), leído en su código.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "produccion" / "ejecutar.py"
REENTRENAR = RAIZ / "produccion" / "reentrenar.py"
TMP = RAIZ / "tests" / "tmp_ejecutar"
sys.path.insert(0, str(RAIZ / "scripts"))
FALLOS = []
ORIGEN = "2011-05-28"   # el día 120 de los datos de juguete
HORIZONTES = {"unidades": 3, "dolares": 5}


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


JUGUETE = cargar(RAIZ / "tests" / "probar_produccion_prevision.py", "juguete")


def montar():
    """La carpeta de prueba con un modelo pequeño reentrenado hasta el origen; devuelve raíz y datos crudos."""
    import produccion_prevision as pp
    raiz = TMP / "caso"
    for carpeta in ("informes", "produccion", "data/processed", "data/entrada", "modelos/reentrenos"):
        (raiz / carpeta).mkdir(parents=True, exist_ok=True)
    contrato = {"contrato": {"aprobado_por": "el responsable del caso", "fecha": "2026-11-25"}, "objetivos": {}}
    for o in ("unidades", "dolares"):
        contrato["objetivos"].update(JUGUETE.contrato_pequeno(o, JUGUETE.columnas_pequenas(o))["objetivos"])
    (raiz / "informes" / "preproduccion.json").write_text(json.dumps(contrato, ensure_ascii=False), encoding="utf-8")
    configuracion = json.loads((RAIZ / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    configuracion["horizontes"] = HORIZONTES
    configuracion["dias_menos_para_comprobar_que_cambia"] = 14
    configuracion["modelo_en_uso"] = None
    configuracion["rutas"]["modulo"] = str(RAIZ / "scripts")
    (raiz / "produccion" / "configuracion.json").write_text(json.dumps(configuracion, ensure_ascii=False),
                                                            encoding="utf-8")
    crudo = JUGUETE.calendario_crudo(140)
    precios = JUGUETE.precios_crudos(crudo)
    venta = JUGUETE.venta_cruda(crudo, precios)
    dias_hasta_origen = [f"d_{i}" for i in range(1, 121)]
    venta_origen = venta[[c for c in venta.columns if not c.startswith("d_")] + dias_hasta_origen]
    tabla = pp.tabla_con_variables(venta_origen, precios, crudo)
    tabla.to_parquet(raiz / "data" / "processed" / "entrenamiento.parquet", index=False)
    tabla.head(10).to_parquet(raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet", index=False)
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(REENTRENAR), "--raiz", str(raiz), "--fecha", "2026-11-25",
                           "--tabla", str(raiz / "data" / "processed" / "entrenamiento.parquet")],
                          capture_output=True, text=True, encoding="utf-8", env=entorno, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"el reentreno de juguete no salió: {proc.stdout[-500:]} {proc.stderr[-800:]}")
    rutas = escribir_entrada(raiz, "base", venta_origen, precios, crudo)
    return raiz, venta_origen, precios, crudo, rutas


def escribir_entrada(raiz, nombre, venta, precios, calendario):
    """Escribe las tres entradas en CSV, con la forma de data/raw/; devuelve sus rutas."""
    carpeta = raiz / "data" / "entrada" / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = {"venta": carpeta / "venta.csv", "precios": carpeta / "precios.csv", "calendario": carpeta / "calendario.csv"}
    venta.to_csv(rutas["venta"], index=False, encoding="utf-8")
    precios.to_csv(rutas["precios"], index=False, encoding="utf-8")
    calendario.to_csv(rutas["calendario"], index=False, encoding="utf-8")
    return rutas


def ejecutar(raiz, rutas, origen=ORIGEN, modelos="modelos/reentrenos/2026-11-25", fecha="2026-11-25"):
    """Lanza ejecutar.py; devuelve (código, salida en Parquet o None, resumen o None, texto)."""
    argumentos = [sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz), "--fecha", fecha,
                  "--venta", str(rutas["venta"]), "--precios", str(rutas["precios"]),
                  "--calendario", str(rutas["calendario"]), "--origen", origen, "--ensayo"]
    if modelos:
        argumentos += ["--modelos", str(raiz / modelos)]
    proc = subprocess.run(argumentos, capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONUTF8="1"), timeout=600)
    carpeta = raiz / "data" / "predicciones" / fecha
    salida = pd.read_parquet(carpeta / "previsiones.parquet") if proc.returncode == 0 else None
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8")) if proc.returncode == 0 else None
    return proc.returncode, salida, resumen, proc.stdout + proc.stderr


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_base(raiz, rutas):
    """Caso 1: la ejecución de base."""
    codigo, s, resumen, texto = ejecutar(raiz, rutas)
    comprobar(codigo == 0 and s is not None, f"base: sale con 0 ({codigo}; {texto[-800:] if codigo else ''})")
    if s is None:
        return None
    for o, h in HORIZONTES.items():
        de = s[s["objetivo"] == o]
        comprobar(len(de) == 4 * h and sorted(de["h"].unique()) == list(range(1, h + 1)),
                  f"base: {o}, una fila por serie y día a prever ({len(de)} de {4 * h})")
    comprobar(s["prevision"].notna().all() and (s["prevision"] >= 0).all() and s["motivo"].isna().all(),
              "base: ninguna fila vacía ni negativa")
    u = s[s["objetivo"] == "unidades"]
    comprobar(np.array_equal(u["prevision"], np.floor(u["prevision_sin_redondear"] + 0.5)),
              "base: las unidades salen al entero con la mitad hacia arriba y la previsión sin redondear al lado")
    comprobar("unidades" not in s.columns and "dolares" not in s.columns, "base: la previsión no se llama como el objetivo")
    v = resumen["validaciones"]
    comprobar(all(v.get(k) is True for k in ("filas_ejecucion", "ficha_cuadra", "periodo_que_toca",
                                              "sin_vacias_sin_motivo", "sin_negativas", "sin_pasos_que_quitan_filas")),
              f"base: el resumen trae sus validaciones en verde ({v})")
    comprobar(resumen["ensayo"] is True and resumen["modelo"]["en_uso"] is False and resumen["origen"] == ORIGEN,
              "base: el resumen dice que es un ensayo con un modelo que no está en uso")
    return s


def probar_falta_columna(raiz, venta, precios, crudo):
    """Caso 2: falta una columna."""
    rutas = escribir_entrada(raiz, "falta", venta, precios.drop(columns="sell_price"), crudo)
    codigo, _, _, texto = ejecutar(raiz, rutas)
    comprobar(codigo == 1 and "sell_price" in texto, f"falta sell_price: para con un mensaje claro ({codigo})")


def probar_texto(raiz, venta, precios, crudo):
    """Caso 3: un número llega como texto."""
    rota = venta.astype({"d_110": "object"})
    rota.loc[2, "d_110"] = "siete"
    rutas = escribir_entrada(raiz, "texto", rota, precios, crudo)
    codigo, _, _, texto = ejecutar(raiz, rutas)
    comprobar(codigo == 1 and "texto" in texto and "d_110" in texto, f"un número como texto: para ({codigo})")


def probar_historia_corta(raiz, venta, precios, crudo):
    """Caso 4: la historia no llega hasta el origen pedido, o lo pasa."""
    ayer = venta.drop(columns="d_120")
    rutas = escribir_entrada(raiz, "ayer", ayer, precios, crudo)
    codigo, _, _, texto = ejecutar(raiz, rutas)
    comprobar(codigo == 1 and "no llega" in texto, f"la entrada del día anterior: para ({codigo})")
    rutas = escribir_entrada(raiz, "base_otra", venta, precios, crudo)
    codigo, _, _, texto = ejecutar(raiz, rutas, origen="2011-05-27")
    comprobar(codigo == 1 and "después del origen" in texto, f"una venta más allá del origen pedido: para ({codigo})")


def probar_combinacion_nueva(raiz, venta, precios, crudo):
    """Caso 5: una combinación nueva sin 28 días de historia sale vacía con su motivo."""
    nueva = venta[venta["store_id"] == "CA_1"].copy()
    nueva["store_id"] = "WI_1"
    nueva["state_id"] = "WI"
    nueva["id"] = nueva["item_id"] + "_WI_1_evaluation"
    dias = [c for c in nueva.columns if c.startswith("d_")]
    nueva[dias] = nueva[dias].astype("float64")
    nueva.loc[:, dias[:-10]] = np.nan
    precios_wi = precios[precios["store_id"] == "CA_1"].assign(store_id="WI_1")
    rutas = escribir_entrada(raiz, "nueva", pd.concat([venta, nueva], ignore_index=True),
                             pd.concat([precios, precios_wi], ignore_index=True), crudo)
    codigo, s, _, texto = ejecutar(raiz, rutas)
    comprobar(codigo == 0 and s is not None, f"combinación nueva: sale con 0 ({codigo}; {texto[-600:] if codigo else ''})")
    if s is None:
        return
    wi = s[s["store_id"] == "WI_1"]
    otras = s[s["store_id"] != "WI_1"]
    comprobar(len(wi) == 2 * sum(HORIZONTES.values()) and wi["prevision"].isna().all() and wi["motivo"].notna().all()
              and wi["motivo"].str.contains("28 días").all(),
              "combinación nueva: sus filas salen con la previsión vacía y su motivo")
    comprobar(otras["prevision"].notna().all() and len(otras) == 4 * sum(HORIZONTES.values()),
              "combinación nueva: las demás series salen previstas")


def probar_otro_orden(raiz, venta, precios, crudo, base):
    """Caso 6: con las series en otro orden cada una recibe la suya."""
    rutas = escribir_entrada(raiz, "orden", venta.sample(frac=1, random_state=3), precios.sample(frac=1, random_state=4),
                             crudo.sample(frac=1, random_state=5))
    codigo, s, _, _ = ejecutar(raiz, rutas, fecha="2026-11-26")
    if s is None or base is None:
        comprobar(False, f"otro orden: sale con 0 ({codigo})")
        return
    unido = base.merge(s, on=["objetivo", "store_id", "dept_id", "date"], suffixes=("", "_b"), validate="one_to_one")
    comprobar(len(unido) == len(base) and np.array_equal(unido["prevision_sin_redondear"],
                                                         unido["prevision_sin_redondear_b"]),
              "otro orden: cada serie recibe la suya")


def probar_ficha(raiz, rutas):
    """Caso 7: una ficha que no cuadra no carga."""
    ficha = raiz / "modelos" / "reentrenos" / "2026-11-25" / "dolares_versiones.json"
    original = ficha.read_text(encoding="utf-8")
    datos = json.loads(original)
    datos["huella"] = "0" * 64
    ficha.write_text(json.dumps(datos), encoding="utf-8")
    codigo, _, _, texto = ejecutar(raiz, rutas, fecha="2026-11-27")
    ficha.write_text(original, encoding="utf-8")
    comprobar(codigo == 1 and "huella" in texto, f"ficha que no cuadra: no carga y para ({codigo})")


def probar_sin_modelo(raiz, rutas):
    """Caso 8: sin modelo en uso ni modelo a mano, para."""
    codigo, _, _, texto = ejecutar(raiz, rutas, modelos=None, fecha="2026-11-28")
    comprobar(codigo == 1 and "modelo en uso" in texto, f"sin modelo en uso: para ({codigo})")


def probar_archivo(raiz, rutas):
    """Caso 9: una segunda ejecución el mismo día copia antes la primera a _archivo."""
    codigo, _, _, _ = ejecutar(raiz, rutas)
    archivo = raiz / "data" / "predicciones" / "_archivo"
    copias = list(archivo.glob("2026-11-25_*")) if archivo.exists() else []
    comprobar(codigo == 0 and copias and (copias[0] / "previsiones.parquet").exists(),
              f"la segunda ejecución del día copia la primera a _archivo ({len(copias)})")


def probar_sin_pasos_que_quitan():
    """Caso 10: ejecutar.py no llama a ningún paso que quita filas."""
    reentrenar = cargar(REENTRENAR, "reentrenar_prueba")
    codigo = SCRIPT.read_text(encoding="utf-8")
    llamadas = [p for p in reentrenar.PASOS_QUE_QUITAN_FILAS if re.search(rf"\b{p}\s*\(", codigo)]
    comprobar(not llamadas and reentrenar.PASOS_QUE_QUITAN_FILAS, f"ejecutar.py no quita filas ({llamadas})")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            raiz_caso, venta_c, precios_c, crudo_c, rutas_c = montar()
            salida_base = probar_base(raiz_caso, rutas_c)
            probar_falta_columna(raiz_caso, venta_c, precios_c, crudo_c)
            probar_texto(raiz_caso, venta_c, precios_c, crudo_c)
            probar_historia_corta(raiz_caso, venta_c, precios_c, crudo_c)
            probar_combinacion_nueva(raiz_caso, venta_c, precios_c, crudo_c)
            probar_otro_orden(raiz_caso, venta_c, precios_c, crudo_c, salida_base)
            probar_ficha(raiz_caso, rutas_c)
            probar_sin_modelo(raiz_caso, rutas_c)
            probar_archivo(raiz_caso, rutas_c)
            probar_sin_pasos_que_quitan()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_ejecutar borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
