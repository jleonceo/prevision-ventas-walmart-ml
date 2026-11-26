"""Prueba de scripts/10_particion.py, con tablas pequeñas escritas aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_particion/ una carpeta con la estructura del
caso (data/processed/hechos_series.parquet e informes/transformacion-datos.json), ejecuta el script sobre ella con
--raiz y la borra al acabar. Importa solo el script que prueba, que tiene su trabajo bajo __main__.

Los casos:
  1. base: dos series con cuatro días de construcción y dos de validación, con las filas desordenadas. Es el control
     que no debe disparar: estado OK, todas las comprobaciones en verde, cada parte son exactamente las filas de su
     periodo, la entrada no cambia y el JSON trae fecha_datos y las versiones;
  2. una fila de validación que cae también en entrenamiento: sin_filas_compartidas en rojo;
  3. una fila que se pierde: suman_la_entrada en rojo;
  4. la fecha máxima de entrenamiento igual o posterior a la mínima de validación: fechas_sin_solape en rojo, y el
     script para sin escribir ninguna parte;
  5. una parte que no coincide con su periodo: parte_igual_a_su_periodo en rojo;
  6. los tramos del paso 2 distintos de las fechas de las partes: tramos_del_paso_2 en rojo;
  7. al empezar: el JSON del paso 2 en PARADO o con otra huella de la tabla, el script para sin partir;
  8. el script no escribe ninguna comprobación con su resultado puesto (error 24).
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "10_particion.py"
TMP = RAIZ / "tests" / "tmp_particion"
FALLOS = []

TRAMOS = {"columna_fecha": "date",
          "desarrollo": {"desde": "2011-01-29", "hasta": "2011-02-01"},
          "validacion": {"desde": "2011-02-02", "hasta": "2011-02-03"}}


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


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    spec = importlib.util.spec_from_file_location("particion_10", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def tabla_pequena():
    """Dos series (CA_1 FOODS_1 y TX_1 HOBBIES_2) en seis días: cuatro de construcción y dos de validación."""
    fechas = pd.date_range("2011-01-29", periods=6, freq="D")
    filas = []
    for tienda, dept in (("CA_1", "FOODS_1"), ("TX_1", "HOBBIES_2")):
        for i, fecha in enumerate(fechas):
            filas.append({"store_id": tienda, "dept_id": dept, "d": f"d_{i + 1}", "unidades": 10 * (i + 1),
                          "dolares": round(2.5 * (i + 1), 2), "date": fecha,
                          "periodo": "construccion" if i < 4 else "validacion",
                          "precio_medio_semana_anterior": None if i < 2 else 1.5})
    tabla = pd.DataFrame(filas)
    tabla["date"] = tabla["date"].astype("datetime64[us]")
    tabla["precio_medio_semana_anterior"] = tabla["precio_medio_semana_anterior"].astype("float64")
    return tabla


def montar(nombre, tabla, estado="OK", huella_distinta=False, tramos=None):
    """Carpeta de prueba con la tabla y el JSON del paso 2; devuelve su raíz."""
    raiz = TMP / nombre
    (raiz / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (raiz / "informes").mkdir(parents=True, exist_ok=True)
    ruta = raiz / "data" / "processed" / "hechos_series.parquet"
    tabla.to_parquet(ruta, index=False)
    sha = "0" * 64 if huella_distinta else huella(ruta)
    transformacion = {"fecha_datos": "2015-05-22", "resultado": {"estado": estado},
                      "salidas": [{"tabla": "hechos_series", "ruta": "data/processed/hechos_series.parquet",
                                   "sha256": sha, "filas": int(len(tabla))}],
                      "particion": tramos or TRAMOS}
    (raiz / "informes" / "transformacion-datos.json").write_text(json.dumps(transformacion), encoding="utf-8")
    return raiz


def ejecutar(raiz):
    """Ejecuta el script sobre la carpeta de prueba, como proceso aparte y con -W error."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)], capture_output=True,
                          text=True, encoding="utf-8", env=entorno, timeout=300)
    ruta = raiz / "informes" / "particion.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


def claves(df):
    """Las claves de fila (tienda, departamento, día) como conjunto."""
    return set(zip(df["store_id"], df["dept_id"], df["d"]))


# ── 2. Casos con el script entero ──────────────────────────────────────────────
def probar_base():
    """Caso 1: el control que no debe disparar, con las filas desordenadas."""
    tabla = tabla_pequena().sample(frac=1, random_state=7).reset_index(drop=True)
    raiz = montar("base", tabla)
    antes = huella(raiz / "data" / "processed" / "hechos_series.parquet")
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "OK",
              f"base: el script acaba en OK ({codigo}; {salida[-400:] if codigo else ''})")
    if d is None:
        return
    comp = d.get("comprobaciones", {})
    for nombre in ("sin_filas_compartidas", "suman_la_entrada", "fechas_sin_solape", "parte_igual_a_su_periodo",
                   "tramos_del_paso_2", "mismas_columnas", "todas_las_series_en_cada_parte"):
        comprobar(comp.get(nombre) is True, f"base: {nombre} en verde ({comp.get(nombre)})")
    comprobar(comp.get("tasa_dentro_de_tolerancia") is None and comp.get("sin_entidades_compartidas") is None,
              "base: las comprobaciones que no aplican a una cantidad partida por fecha salen null")
    ent = pd.read_parquet(raiz / "data" / "processed" / "hechos_series_entrenamiento.parquet")
    val = pd.read_parquet(raiz / "data" / "processed" / "hechos_series_validacion.parquet")
    comprobar(claves(ent) == claves(tabla[tabla["periodo"] == "construccion"]),
              "base: entrenamiento son exactamente las filas de construcción")
    comprobar(claves(val) == claves(tabla[tabla["periodo"] == "validacion"]),
              "base: validación son exactamente las filas de validación")
    comprobar(list(ent.columns) == list(tabla.columns) and list(val.columns) == list(tabla.columns),
              "base: cada parte conserva las columnas de la entrada en su orden")
    comprobar(huella(raiz / "data" / "processed" / "hechos_series.parquet") == antes
              and d["entradas"][0]["sha256"] == antes and d.get("huella_entrada_despues") == antes,
              "base: la entrada no cambia y su huella va en el JSON")
    partes = {p["parte"]: p for p in d["partes"]}
    comprobar(partes["entrenamiento"]["filas"] == 8 and partes["validacion"]["filas"] == 4,
              f"base: 8 y 4 filas ({partes['entrenamiento']['filas']}, {partes['validacion']['filas']})")
    comprobar(partes["entrenamiento"]["unidades"] == 200 and partes["validacion"]["unidades"] == 220,
              f"base: unidades 200 y 220 ({partes['entrenamiento']['unidades']}, {partes['validacion']['unidades']})")
    comprobar(abs(partes["entrenamiento"]["dolares"] - 50.0) < 1e-9 and abs(partes["validacion"]["dolares"] - 55.0) < 1e-9,
              f"base: dólares 50 y 55 ({partes['entrenamiento']['dolares']}, {partes['validacion']['dolares']})")
    comprobar(partes["entrenamiento"]["fecha_min"] == "2011-01-29" and partes["entrenamiento"]["fecha_max"] == "2011-02-01"
              and partes["validacion"]["fecha_min"] == "2011-02-02" and partes["validacion"]["fecha_max"] == "2011-02-03",
              "base: fechas mínima y máxima de cada parte")
    comprobar(partes["entrenamiento"]["combinaciones"] == 2 and partes["validacion"]["dias"] == 2,
              "base: combinaciones de departamento y tienda y días por parte")
    comprobar(partes["entrenamiento"]["sha256"] == huella(raiz / "data" / "processed" / "hechos_series_entrenamiento.parquet"),
              "base: la huella de la parte de entrenamiento es la del fichero")
    comprobar(partes["lote_produccion"]["ruta"] is None and partes["lote_produccion"]["filas"] is None,
              "base: no hay lote de producción y sale null")
    comprobar(d["fecha_datos"] == "2015-05-22" and d["estrategia"] == "fecha" and d["columna_fecha"] == "date",
              "base: fecha_datos del paso 2, estrategia por fecha y su columna")
    comprobar(all(d["entorno"].get(k) for k in ("python", "pandas", "numpy", "pyarrow", "scikit-learn", "ejecutable")),
              f"base: el JSON trae las versiones ({d.get('entorno')})")
    comprobar(d["resultado"]["artefactos"] == ["informes/particion.json",
                                                "data/processed/hechos_series_entrenamiento.parquet",
                                                "data/processed/hechos_series_validacion.parquet"],
              "base: los artefactos son el JSON y las dos partes")


def probar_solape_en_el_script():
    """Caso 4 con el script entero: una fecha de construcción posterior a una de validación para sin escribir partes."""
    tabla = tabla_pequena()
    tabla.loc[(tabla["store_id"] == "CA_1") & (tabla["d"] == "d_4"), "date"] = pd.Timestamp("2011-02-05")
    raiz = montar("solape", tabla)
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["comprobaciones"].get("fechas_sin_solape") is False,
              f"solape: el script acaba en ERROR con fechas_sin_solape en rojo ({codigo})")
    comprobar(not (raiz / "data" / "processed" / "hechos_series_entrenamiento.parquet").exists()
              and not (raiz / "data" / "processed" / "hechos_series_validacion.parquet").exists(),
              "solape: no escribe ninguna parte")


def probar_al_empezar():
    """Caso 7: el JSON del paso 2 en PARADO o con otra huella de la tabla para el script antes de partir."""
    for nombre, kwargs in (("parado", {"estado": "PARADO"}), ("otra_huella", {"huella_distinta": True})):
        raiz = montar(nombre, tabla_pequena(), **kwargs)
        codigo, d, salida = ejecutar(raiz)
        comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO",
                  f"{nombre}: el script para ({codigo}; {d and d['resultado']['estado']})")
        comprobar(not (raiz / "data" / "processed" / "hechos_series_entrenamiento.parquet").exists(),
                  f"{nombre}: no escribe ninguna parte")


# ── 3. Casos sobre las comprobaciones, con partes estropeadas a propósito ─────
def probar_comprobaciones(m):
    """Casos 2, 3, 5 y 6: cada comprobación da rojo con su fallo y verde sin él."""
    tabla = tabla_pequena()
    buenas = m.partir(tabla)
    comp, _ = m.comprobar_particion(tabla, buenas, TRAMOS)
    comprobar(all(comp[k] is True for k in ("sin_filas_compartidas", "suman_la_entrada", "fechas_sin_solape",
                                             "parte_igual_a_su_periodo", "tramos_del_paso_2")),
              "comprobaciones: con las partes bien, todas en verde")

    # 2. una fila de validación que cae también en entrenamiento
    copia = {k: v.copy() for k, v in buenas.items()}
    copia["entrenamiento"] = pd.concat([copia["entrenamiento"], copia["validacion"].iloc[[0]]], ignore_index=True)
    comp, _ = m.comprobar_particion(tabla, copia, TRAMOS)
    comprobar(comp["sin_filas_compartidas"] is False, "fila de validación en entrenamiento: sin_filas_compartidas en rojo")

    # 3. una fila que se pierde
    copia = {k: v.copy() for k, v in buenas.items()}
    copia["validacion"] = copia["validacion"].iloc[1:]
    comp, _ = m.comprobar_particion(tabla, copia, TRAMOS)
    comprobar(comp["suman_la_entrada"] is False, "fila perdida: suman_la_entrada en rojo")

    # 3b. una fila perdida tapada por una repetida: el número de filas cuadra y la comprobación tiene que ver el hueco
    copia = {k: v.copy() for k, v in buenas.items()}
    copia["validacion"] = pd.concat([copia["validacion"].iloc[1:], copia["validacion"].iloc[[1]]], ignore_index=True)
    comp, _ = m.comprobar_particion(tabla, copia, TRAMOS)
    comprobar(comp["suman_la_entrada"] is False, "fila perdida tapada por una repetida: suman_la_entrada en rojo")

    # 4. la fecha máxima de entrenamiento igual a la mínima de validación
    pisada = tabla.copy()
    pisada.loc[(pisada["periodo"] == "construccion") & (pisada["d"] == "d_4"), "date"] = pd.Timestamp("2011-02-02")
    comp, _ = m.comprobar_particion(pisada, m.partir(pisada), TRAMOS)
    comprobar(comp["fechas_sin_solape"] is False, "fecha máxima de entrenamiento igual a la mínima de validación: en rojo")

    # 5. una parte que no coincide con su periodo: una fila de validación pasa a entrenamiento
    copia = {k: v.copy() for k, v in buenas.items()}
    movida = copia["validacion"].iloc[[0]]
    copia["entrenamiento"] = pd.concat([copia["entrenamiento"], movida], ignore_index=True)
    copia["validacion"] = copia["validacion"].iloc[1:]
    comp, _ = m.comprobar_particion(tabla, copia, TRAMOS)
    comprobar(comp["parte_igual_a_su_periodo"] is False, "parte distinta de su periodo: parte_igual_a_su_periodo en rojo")
    comprobar(comp["sin_filas_compartidas"] is True and comp["suman_la_entrada"] is True,
              "parte distinta de su periodo: las filas no se repiten ni se pierden, así que solo esa comprobación lo ve")

    # 6. los tramos del paso 2 no son los de las partes
    otros = {"columna_fecha": "date", "desarrollo": {"desde": "2011-01-29", "hasta": "2011-02-02"},
             "validacion": {"desde": "2011-02-03", "hasta": "2011-02-03"}}
    comp, _ = m.comprobar_particion(tabla, buenas, otros)
    comprobar(comp["tramos_del_paso_2"] is False, "tramos del paso 2 distintos: tramos_del_paso_2 en rojo")


def probar_sin_veredictos_escritos():
    """Caso 8, error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](sin_filas_compartidas|suman_la_entrada|fechas_sin_solape|parte_igual_a_su_periodo|"
                         r"tramos_del_paso_2|mismas_columnas|todas_las_series_en_cada_parte)[\"']\s*:\s*(True|False)\b",
                         codigo)
    comprobar(puestos == [], f"el script no escribe ninguna comprobación con su resultado puesto ({puestos})")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            probar_base()
            probar_solape_en_el_script()
            probar_al_empezar()
            probar_comprobaciones(cargar_script())
            probar_sin_veredictos_escritos()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_particion borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
