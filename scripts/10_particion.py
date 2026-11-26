"""Partición del caso 69: entrenamiento y validación de la tabla de series, tal como las apartó el paso 2.

Aplica el método preparacion-modelo, apartado 1. La partición ya existe: es la columna `periodo` de
data/processed/hechos_series.parquet, puesta en el paso 2 por fecha (reglas-negocio §5, «Fechas»). Este script no
vuelve a partir: separa las filas de cada periodo, comprueba en código que cada parte son exactamente esas filas y que
sus fechas son los tramos del paso 2, y guarda las dos partes en data/processed/ solo si pasan sus comprobaciones. No
hay lote de producción: la prueba final está fuera del caso (reglas, apartado 5). Deja informes/particion.json.

Depende de lo que deja otro script (error 2): data/processed/hechos_series.parquet e informes/transformacion-datos.json
(scripts/05_transformacion_datos.py). Antes de empezar comprueba el estado de ese JSON y que la huella de la tabla es la
que él registró.

Uso: python -W error scripts/10_particion.py [--raiz CARPETA]
  --raiz: carpeta con la estructura del caso (data/processed/ e informes/). Por defecto, la del caso. La prueba la usa
  para ejecutar el script sobre tablas pequeñas.
Sale con 0 si el estado es OK o AVISO y con 1 si es PARADO o ERROR.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import json
import math
import platform
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import sklearn

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método preparacion-modelo con que se escribió este script
SCRIPT_REL = "scripts/10_particion.py"
ENTRADA_REL = "data/processed/hechos_series.parquet"
TRANSFORMACION_REL = "informes/transformacion-datos.json"
JSON_REL = "informes/particion.json"
SALIDAS = {"entrenamiento": "data/processed/hechos_series_entrenamiento.parquet",
           "validacion": "data/processed/hechos_series_validacion.parquet"}

# Cada parte es el periodo que apartó el paso 2, y su tramo de fechas es el que registró ese paso en su JSON
PERIODO_DE_PARTE = {"entrenamiento": "construccion", "validacion": "validacion"}
TRAMO_DE_PARTE = {"entrenamiento": "desarrollo", "validacion": "validacion"}
CLAVE = ["store_id", "dept_id", "d"]
SERIE = ["store_id", "dept_id"]
COLUMNA_FECHA = "date"
COLUMNA_PERIODO = "periodo"

# No hay azar en esta partición; la semilla se escribe porque el método la pide en el JSON (parametros.md)
SEMILLA = 42


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_json_limpio(obj):
    """Tipos de numpy y pandas a Python; NaN, infinito y NA a null (programacion-del-caso, error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json_limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json_limpio(v) for v in obj]
    if obj is None or obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        valor = float(obj)
        return None if math.isnan(valor) or math.isinf(valor) else valor
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def claves(df):
    """Las claves de fila (tienda, departamento, día) como lista de tuplas."""
    return list(zip(df["store_id"], df["dept_id"], df["d"]))


def centimos(df):
    """Suma de los dólares en céntimos enteros, para comparar sumas sin error de coma flotante."""
    return int(np.rint(df["dolares"].to_numpy(dtype="float64") * 100).sum())


def fecha_iso(valor):
    """Una fecha a texto ISO, o None si no hay."""
    return None if pd.isna(valor) else pd.Timestamp(valor).strftime("%Y-%m-%d")


# ══ 3. Partir y comprobar ═══════════════════════════════════════════════════════
def partir(tabla):
    """Separa las filas de cada periodo del paso 2, ordenadas por la clave; no reparte nada de nuevo."""
    partes = {}
    for parte, periodo in PERIODO_DE_PARTE.items():
        # La máscara booleana, no etiquetas: con un índice repetido, .loc[etiquetas] traería de más (error 8c)
        trozo = tabla[tabla[COLUMNA_PERIODO] == periodo]
        partes[parte] = trozo.sort_values(CLAVE, kind="mergesort").reset_index(drop=True)
    return partes


def comprobar_particion(tabla, partes, tramos):
    """Comprobaciones del método, apartado 1, cada una calculada con lo que se ejecutó (error 24); devuelve (comprobaciones, detalle).

    tramos: la partición registrada por el paso 2 (informes/transformacion-datos.json, «particion»).
    """
    ent, val = partes["entrenamiento"], partes["validacion"]
    claves_ent, claves_val, claves_tabla = claves(ent), claves(val), claves(tabla)
    detalle = {}

    # Ninguna fila está en las dos partes
    compartidas = set(claves_ent) & set(claves_val)
    detalle["filas_compartidas"] = len(compartidas)

    # Las partes suman la entrada: mismo número de filas, ninguna repetida, ninguna perdida y las mismas sumas
    repetidas = (len(claves_ent) - len(set(claves_ent))) + (len(claves_val) - len(set(claves_val)))
    perdidas = set(claves_tabla) - (set(claves_ent) | set(claves_val))
    sobrantes = (set(claves_ent) | set(claves_val)) - set(claves_tabla)
    filas_iguales = len(ent) + len(val) == len(tabla)
    unidades_iguales = int(ent["unidades"].sum()) + int(val["unidades"].sum()) == int(tabla["unidades"].sum())
    dolares_iguales = centimos(ent) + centimos(val) == centimos(tabla)
    detalle.update({"filas_entrada": len(tabla), "filas_partes": len(ent) + len(val), "filas_repetidas": repetidas,
                    "filas_perdidas": len(perdidas), "filas_sobrantes": len(sobrantes)})

    # Con partición por fecha: el último día de entrenamiento va antes del primero de validación
    max_ent, min_val = ent[COLUMNA_FECHA].max(), val[COLUMNA_FECHA].min()
    detalle.update({"fecha_max_entrenamiento": fecha_iso(max_ent), "fecha_min_validacion": fecha_iso(min_val)})

    # Cada parte son exactamente las filas de su periodo en la entrada, y todas sus filas llevan ese periodo
    iguales_al_periodo = []
    for parte, periodo in PERIODO_DE_PARTE.items():
        esperadas = set(claves(tabla[tabla[COLUMNA_PERIODO] == periodo]))
        propias = partes[parte]
        iguales_al_periodo.append(set(claves(propias)) == esperadas and len(propias) == len(esperadas)
                                  and bool((propias[COLUMNA_PERIODO] == periodo).all()))
    detalle["partes_iguales_a_su_periodo"] = dict(zip(PERIODO_DE_PARTE, iguales_al_periodo))

    # Las fechas de cada parte son el tramo que registró el paso 2
    tramos_iguales = []
    for parte, tramo in TRAMO_DE_PARTE.items():
        t = tramos.get(tramo) or {}
        propias = partes[parte][COLUMNA_FECHA]
        tramos_iguales.append(fecha_iso(propias.min()) == t.get("desde") and fecha_iso(propias.max()) == t.get("hasta"))
    detalle["columna_fecha_del_paso_2"] = tramos.get("columna_fecha")

    # Cada parte tiene todas las series en todos sus días: series por días es igual a filas
    completas = []
    for parte in PERIODO_DE_PARTE:
        p = partes[parte]
        completas.append(len(p) == p[SERIE].drop_duplicates().shape[0] * p[COLUMNA_FECHA].nunique())

    comprobaciones = {
        "sin_filas_compartidas": len(compartidas) == 0,
        "sin_entidades_compartidas": None,
        "suman_la_entrada": filas_iguales and repetidas == 0 and not perdidas and not sobrantes
                            and unidades_iguales and dolares_iguales,
        "tasa_dentro_de_tolerancia": None,
        "fechas_sin_solape": bool(pd.notna(max_ent) and pd.notna(min_val) and max_ent < min_val),
        "parte_igual_a_su_periodo": all(iguales_al_periodo),
        "tramos_del_paso_2": all(tramos_iguales) and tramos.get("columna_fecha") == COLUMNA_FECHA,
        "mismas_columnas": all(list(p.columns) == list(tabla.columns) for p in partes.values()),
        "todas_las_series_en_cada_parte": all(completas),
    }
    return comprobaciones, detalle


def resumen_parte(parte, df, ruta, sha):
    """Filas, sumas, fechas y combinaciones de una parte, para el JSON."""
    return {"parte": parte, "periodo": PERIODO_DE_PARTE[parte], "ruta": ruta, "sha256": sha, "filas": int(len(df)),
            "columnas": int(df.shape[1]), "tasa_objetivo": None, "unidades": int(df["unidades"].sum()),
            "dolares": centimos(df) / 100, "fecha_min": fecha_iso(df[COLUMNA_FECHA].min()),
            "fecha_max": fecha_iso(df[COLUMNA_FECHA].max()), "dias": int(df[COLUMNA_FECHA].nunique()),
            "combinaciones": int(df[SERIE].drop_duplicates().shape[0])}


# ══ 4. Ejecución principal ══════════════════════════════════════════════════════
def principal(raiz):
    """Lee, comprueba al empezar, separa, comprueba, guarda las partes y escribe el JSON."""
    r = {"metodo": "preparacion-modelo", "version_metodo": version_metodo(), "script": SCRIPT_REL, "fecha_datos": None,
         "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                     "pyarrow": pyarrow.__version__, "scikit-learn": sklearn.__version__,
                     "ejecutable": sys.executable},
         "entradas": [], "resultado": {}, "pendientes": [],
         "estrategia": "fecha",
         "por_que": ("la partición la apartó el paso 2 por fecha, en la columna periodo (reglas-negocio §5, «Fechas»): "
                     "el modelo se usa hacia adelante y la validación es el año más reciente; aquí no se vuelve a partir"),
         "semilla": SEMILLA, "semilla_nota": "la partición no usa azar: sigue la columna periodo",
         "columna_fecha": COLUMNA_FECHA, "columna_periodo": COLUMNA_PERIODO, "columna_grupo": None,
         "objetivo": {"columnas": ["unidades", "dolares"], "tipo": "cantidad",
                      "nota": "objetivo continuo: no hay tasa ni desequilibrio de clases"},
         "partes": [], "comprobaciones": {}, "detalle_comprobaciones": {},
         "comprobaciones_nulas": {"sin_entidades_compartidas": "no aplica: partición por fecha; las 70 series están en "
                                                               "las dos partes a propósito",
                                  "tasa_dentro_de_tolerancia": "no aplica: el objetivo es una cantidad"},
         "huella_entrada_despues": None, "paradas": []}

    def terminar(estado, riesgo, resumen, siguiente, artefactos):
        """Escribe el JSON con su estado (resultado.md, regla 5) y devuelve el estado."""
        r["resultado"] = {"estado": estado, "riesgo": riesgo, "resumen": resumen, "artefactos": artefactos,
                          "siguiente": siguiente}
        (raiz / "informes").mkdir(parents=True, exist_ok=True)
        (raiz / JSON_REL).write_text(json.dumps(a_json_limpio(r), ensure_ascii=False, indent=2), encoding="utf-8")
        return estado

    # ── 4.1 Al empezar: el JSON del paso 2 y la huella de la tabla (resultado.md, «Al empezar») ──
    ruta_tr = raiz / TRANSFORMACION_REL
    ruta_entrada = raiz / ENTRADA_REL
    if not ruta_tr.exists() or not ruta_entrada.exists():
        r["paradas"].append({"codigo": "falta_entrada", "motivo": "falta la tabla de series o el JSON del paso 2"})
        return terminar("PARADO", "alto", "Falta la tabla de series o informes/transformacion-datos.json.",
                        "ejecutar antes scripts/05_transformacion_datos.py", [JSON_REL])
    transformacion = json.loads(ruta_tr.read_text(encoding="utf-8"))
    r["fecha_datos"] = transformacion.get("fecha_datos")
    estado_tr = (transformacion.get("resultado") or {}).get("estado")
    huella_antes = huella(ruta_entrada)
    registrada = next((s.get("sha256") for s in transformacion.get("salidas", []) if s.get("ruta") == ENTRADA_REL), None)
    if estado_tr not in ("OK", "AVISO"):
        r["paradas"].append({"codigo": "paso_2_no_valido", "motivo": f"el JSON del paso 2 está en {estado_tr}"})
    if registrada != huella_antes:
        r["paradas"].append({"codigo": "huella_distinta",
                             "motivo": f"la tabla tiene la huella {huella_antes} y el paso 2 registró {registrada}"})
    if r["paradas"]:
        return terminar("PARADO", "alto", "El paso 2 no está en OK o la tabla no es la que él dejó: no se parte.",
                        "revisar la transformación", [JSON_REL])

    # ── 4.2 Leer, separar y comprobar ──
    tabla = pd.read_parquet(ruta_entrada)
    r["entradas"].append({"ruta": ENTRADA_REL, "sha256": huella_antes, "filas": int(len(tabla)),
                          "columnas": int(tabla.shape[1])})
    tramos = transformacion.get("particion") or {}
    r["tramos_del_paso_2"] = {"fuente": f"{TRANSFORMACION_REL}, «particion»", "tramos": tramos}
    partes = partir(tabla)
    comprobaciones, detalle = comprobar_particion(tabla, partes, tramos)
    r["comprobaciones"], r["detalle_comprobaciones"] = comprobaciones, detalle
    fallidas = [k for k, v in comprobaciones.items() if v is False]
    if fallidas:
        r["partes"] = [resumen_parte(p, df, None, None) for p, df in partes.items()]
        return terminar("ERROR", "alto", f"Comprobaciones en rojo: {', '.join(fallidas)}. No se escribe ninguna parte.",
                        "revisar la columna periodo y las fechas del paso 2", [JSON_REL])

    # ── 4.3 Guardar las partes, solo con las comprobaciones en verde (error 15), y releerlas ──
    releidas_iguales = []
    for parte, df in partes.items():
        ruta = raiz / SALIDAS[parte]
        df.to_parquet(ruta, index=False)
        releida = pd.read_parquet(ruta)
        releidas_iguales.append(releida.equals(df))
        r["partes"].append(resumen_parte(parte, df, SALIDAS[parte], huella(ruta)))
    r["partes"].append({"parte": "lote_produccion", "periodo": None, "ruta": None, "sha256": None, "filas": None,
                        "tasa_objetivo": None, "fecha_min": None, "fecha_max": None,
                        "nota": "no hay lote de producción: la prueba final está fuera del caso (reglas-negocio §5)"})
    r["comprobaciones"]["partes_releidas_iguales"] = all(releidas_iguales)
    r["huella_entrada_despues"] = huella(ruta_entrada)
    artefactos = [JSON_REL] + list(SALIDAS.values())
    if not all(releidas_iguales) or r["huella_entrada_despues"] != huella_antes:
        return terminar("ERROR", "alto", "Una parte guardada no es igual a la separada o la entrada cambió.",
                        "revisar la ejecución", artefactos)

    ent, val = r["partes"][0], r["partes"][1]
    resumen = (f"Entrenamiento con {ent['filas']} filas del {ent['fecha_min']} al {ent['fecha_max']} y validación con "
               f"{val['filas']} filas del {val['fecha_min']} al {val['fecha_max']}, exactamente las de cada periodo del "
               f"paso 2; {sum(v is True for v in r['comprobaciones'].values())} comprobaciones en verde.")
    return terminar("OK", "bajo", resumen,
                    "preparacion-modelo §2 y §3: diagnóstico y matriz propuesta, que aprueba el responsable del caso", artefactos)


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Partición del caso 69")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta con la estructura del caso")
    raiz_de_trabajo = Path(argumentos.parse_args().raiz).resolve()
    print("intérprete:", sys.executable)
    try:
        estado_final = principal(raiz_de_trabajo)
    except Exception as fallo:  # un fallo técnico deja el JSON en ERROR (resultado.md, regla 5) y sale con 1
        traceback.print_exc()
        error = {"metodo": "preparacion-modelo", "script": SCRIPT_REL, "fecha_datos": None,
                 "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
                 "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(fallo).__name__}: {fallo}",
                               "artefactos": [JSON_REL], "siguiente": "revisar el fallo"},
                 "pendientes": [], "partes": [], "paradas": []}
        (raiz_de_trabajo / "informes").mkdir(parents=True, exist_ok=True)
        (raiz_de_trabajo / JSON_REL).write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding="utf-8")
        estado_final = "ERROR"
    print("estado:", estado_final)
    sys.exit(0 if estado_final in ("OK", "AVISO") else 1)
