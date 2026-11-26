"""Preprocesador de los dos modelos de previsión del caso 69, sin ajustar, y sus nueve validaciones.

Construye con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 (config/modelo/
matriz_transformaciones.md) un ColumnTransformer dentro de un Pipeline (método preparacion-modelo, apartado 4). Es un solo
preprocesador para HistGradientBoosting y Ridge; las variables de los dos objetivos van por separado: el modelo de
unidades usa las de unidades y el de dólares las de dólares, las demás las dos. El preprocesador sale sin ajustar de
construir_preprocesador(), que vive en scripts/preparacion_prevision.py: lo ajusta aprendizaje-automatico,
con el entrenamiento, junto al modelo.

Para comprobarlo (§5), este script lo ajusta una sola vez con el entrenamiento y aplica transform a la validación con
retardos reales, que solo sirve para esto. No guarda ningún conjunto transformado ni el preprocesador ajustado. Deja
informes/preparacion.json con la estructura del método (resultado.md).

Depende de scripts/11_variables_modelo.py (error 2): data/processed/hechos_modelo_entrenamiento.parquet y
hechos_modelo_validacion.parquet, cuya huella se comprueba contra informes/variables_modelo.json.

Uso: python -W error scripts/12_preparacion.py [--raiz CARPETA]
Sale con 0 si el estado es OK y con 1 si es PARADO o ERROR.
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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, RobustScaler, StandardScaler

# El preprocesador vive en un módulo que no ejecuta nada al importarse (error 1): lo usan este script y el 13
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preparacion_prevision import (DROP_MATRIZ, EVENTO_COLUMNAS, MIN_FRECUENCIA, OBJETIVOS,  # noqa: E402
                                   OHE_COLUMNAS, PASA_FIJAS, RELLENO_EVENTO, RETARDOS, SS_COLUMNAS, VENTANAS,
                                   columnas_entrada,
                                   combinar_categoria, construir_preprocesador, nombre_salida, nombres_rs)

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método preparacion-modelo con que se escribió este script
SCRIPT_REL = "scripts/12_preparacion.py"
FECHA_DATOS = "2015-05-22"
ENTRADAS = {"entrenamiento": "data/processed/hechos_modelo_entrenamiento.parquet",
            "validacion": "data/processed/hechos_modelo_validacion.parquet"}
PREVIO_REL = "informes/variables_modelo.json"
JSON_REL = "informes/preparacion.json"
MATRIZ_REL = "config/modelo/matriz_transformaciones.md"

# Los dos algoritmos que compiten (matriz, «Lo que ya estaba fijado»); los objetivos vienen del módulo
ALGORITMOS = ["HistGradientBoosting", "Ridge"]
# Admiten las k columnas de una codificación sin quitar una: los árboles cortan por columna y Ridge está regularizado
# (catálogo, categóricas; ficha de Ridge §6)
ADMITEN_COLINEALIDAD = {"HistGradientBoosting": "árboles", "Ridge": "regresión regularizada"}

# Columnas de salida por codificación que dice la matriz (31 = 30 eventos más «sin evento»; 4 = 3 más «sin evento»)
COLUMNAS_OHE_MATRIZ = {"store_id": 10, "dept_id": 7, "weekday": 7, "month": 12, "event_name_1": 31, "event_name_2": 4}


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_json_limpio(obj):
    """Tipos de numpy y pandas a Python; NaN e infinito a null (programacion-del-caso, error 22)."""
    if isinstance(obj, dict):
        return {str(k): a_json_limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [a_json_limpio(v) for v in obj]
    if obj is None or obj is pd.NA:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        valor = float(obj)
        return None if math.isnan(valor) or math.isinf(valor) else valor
    return obj


def entorno():
    """Versiones con que se ejecuta el script."""
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
            "pyarrow": pyarrow.__version__, "scikit-learn": sklearn.__version__, "ejecutable": sys.executable}


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


# ══ 3. El preprocesador ═══ está en scripts/preparacion_prevision.py (construir_preprocesador)


# ══ 4. Las nueve validaciones (preparacion-modelo §5) ═══════════════════════════
def pasos(transformador):
    """Los pasos de una rama: el transformador solo, o cada paso si es un Pipeline."""
    if isinstance(transformador, Pipeline):
        return [p for _, p in transformador.steps]
    return [transformador]


def ramas(ct):
    """Las ramas ajustadas de un ColumnTransformer, sin el sobrante."""
    return [(n, t, list(c)) for n, t, c in ct.transformers_ if n != "remainder"]


def tal_cual(ct):
    """Los nombres de las ramas que pasan tal cual, leídos de la definición: al ajustar, scikit-learn cambia
    «passthrough» por un FunctionTransformer en transformers_."""
    return {n for n, t, _ in ct.transformers if isinstance(t, str) and t == "passthrough"}


def columnas_esperadas(entrenamiento, objetivo, columnas_evento):
    """Las columnas de salida que la matriz espera, con las categorías que hay en el entrenamiento."""
    esperadas = []
    for c in OHE_COLUMNAS:
        esperadas += [combinar_categoria(c, v) for v in sorted(entrenamiento[c].dropna().unique())]
    for c in EVENTO_COLUMNAS:
        cats = sorted(set(entrenamiento[c].dropna().astype("str")) | {RELLENO_EVENTO})
        esperadas += [combinar_categoria(c, v) for v in cats]
    esperadas += PASA_FIJAS + list(columnas_evento)
    esperadas += [f"{c}_ss" for c in SS_COLUMNAS] + [f"{c}_rs" for c in nombres_rs(objetivo)]
    return esperadas


def v_filas(ent, s_tr, val, s_va):
    """1. Las filas de entrada y de salida coinciden en cada parte."""
    detalle = {"entrenamiento": [len(ent), len(s_tr)], "validacion": [len(val), len(s_va)]}
    return len(ent) == len(s_tr) and len(val) == len(s_va), detalle


def v_sin_objetivo(ct, salida):
    """2. Ningún objetivo entra al preprocesador ni sale de él."""
    entradas = {c for _, _, cols in ramas(ct) for c in cols}
    dentro = sorted(entradas & set(OBJETIVOS))
    fuera = [c for c in salida.columns if c in OBJETIVOS or any(c == nombre_salida(n, o) for n in ("ss", "rs")
                                                                for o in OBJETIVOS)]
    return not dentro and not fuera, {"objetivo_en_entrada": dentro, "objetivo_en_salida": fuera}


def v_sin_intermedias(ct, salida):
    """3. No quedan columnas intermedias (prefijo de un paso) ni la original de una variable transformada."""
    transformadas = {c for n, t, cols in ramas(ct) if n not in tal_cual(ct) for c in cols}
    originales = sorted(set(salida.columns) & transformadas)
    intermedias = [c for c in salida.columns if "__" in c]
    return not originales and not intermedias, {"originales": originales, "intermedias": intermedias}


def v_sin_vacios(s_tr, s_va):
    """4. Sin vacíos en la salida: Ridge no los admite y la matriz no deja ninguno."""
    n = {"entrenamiento": int(s_tr.isna().sum().sum()), "validacion": int(s_va.isna().sum().sum())}
    return sum(n.values()) == 0, n


def v_nombres_unicos(salida):
    """5. Los nombres de salida son únicos."""
    repetidos = sorted(set(salida.columns[salida.columns.duplicated()]))
    return not repetidos, {"repetidos": repetidos}


def v_nombres_unicos_partes(s_tr, s_va):
    """5, en las dos partes: nombres únicos en cada una y las mismas columnas, en el mismo orden."""
    ok_tr, d_tr = v_nombres_unicos(s_tr)
    ok_va, d_va = v_nombres_unicos(s_va)
    iguales = list(s_tr.columns) == list(s_va.columns)
    return ok_tr and ok_va and iguales, {"entrenamiento": d_tr, "validacion": d_va, "mismas_columnas": iguales}


def v_sin_redundancia(ct, s_tr, algoritmos):
    """6. Una codificación con sus k columnas (suman 1 en cada fila) solo si todos los algoritmos lo admiten, y con
    el drop que dice la matriz."""
    detalle = {}
    ok = True
    admiten = all(a in ADMITEN_COLINEALIDAD for a in algoritmos)
    for _, t, cols in ramas(ct):
        for paso in pasos(t):
            if not isinstance(paso, OneHotEncoder):
                continue
            for c in cols:
                familia = [s for s in s_tr.columns if s.startswith(f"{c}_ohe_")]
                suma_uno = bool(len(familia)) and bool((s_tr[familia].sum(axis=1) == 1).all())
                drop_ok = paso.drop is DROP_MATRIZ or paso.drop == DROP_MATRIZ
                bien = drop_ok and (not suma_uno or admiten)
                detalle[c] = {"columnas": len(familia), "suman_1": suma_uno, "drop": paso.drop,
                              "drop_de_la_matriz": DROP_MATRIZ, "algoritmos_lo_admiten": admiten}
                ok = ok and bien
    return ok and bool(detalle), detalle


def v_columnas_esperadas(salida, esperadas, entrenamiento):
    """7. Las columnas de salida son exactamente las que la matriz espera, en número y en nombre."""
    sobran = sorted(set(salida.columns) - set(esperadas))
    faltan = sorted(set(esperadas) - set(salida.columns))
    por_familia = {c: sum(1 for s in esperadas if s.startswith(f"{c}_ohe_")) for c in COLUMNAS_OHE_MATRIZ}
    familias_ok = por_familia == COLUMNAS_OHE_MATRIZ
    ok = not sobran and not faltan and len(salida.columns) == len(esperadas) and familias_ok
    return ok, {"salida": len(salida.columns), "esperadas": len(esperadas), "sobran": sobran, "faltan": faltan,
                "por_codificacion": por_familia, "matriz": COLUMNAS_OHE_MATRIZ}


def v_relleno_sin_choque(entrenamiento):
    """8. El relleno fijo «sin evento» no aparece ya en el entrenamiento con otro significado."""
    choques = {c: int((entrenamiento[c] == RELLENO_EVENTO).fillna(False).sum()) for c in EVENTO_COLUMNAS}
    return sum(choques.values()) == 0, {"relleno": RELLENO_EVENTO, "filas_con_ese_valor": choques}


def v_escalado_segun_matriz(ct, s_tr, s_va):
    """9. El escalado cumple la matriz y sus trampas: las columnas de 0 y 1 salen en 0 y 1; cada numérica con su
    escalador; ninguna salida dispersa; un MinMaxScaler, con clip."""
    binarias = [nombre_salida(n, c) for n, t, cols in ramas(ct) if n == "pasa" for c in cols]
    binarias += [s for s in s_tr.columns if "_ohe_" in s]
    fuera_01 = sorted({c for s in (s_tr, s_va) for c in binarias if c in s.columns
                       and not s[c].isin([0, 1]).all()})
    esperado = {c: RobustScaler for o in OBJETIVOS for c in nombres_rs(o)}
    esperado.update({c: StandardScaler for c in SS_COLUMNAS})
    mal_escalador, sin_clip, dispersas = [], [], []
    for n, t, cols in ramas(ct):
        for paso in pasos(t):
            if isinstance(paso, OneHotEncoder) and paso.sparse_output:
                dispersas.append(n)
            if isinstance(paso, MinMaxScaler) and not paso.clip:
                sin_clip.append(n)
            if isinstance(paso, (StandardScaler, RobustScaler, MinMaxScaler)):
                mal_escalador += [c for c in cols if c in esperado and not isinstance(paso, esperado[c])]
        # Una numérica que la matriz escala y pasa tal cual también incumple
        if n in tal_cual(ct):
            mal_escalador += [c for c in cols if c in esperado]
    ok = not fuera_01 and not mal_escalador and not sin_clip and not dispersas
    return ok, {"binarias_fuera_de_0_y_1": fuera_01, "escalador_distinto_de_la_matriz": mal_escalador,
                "minmax_sin_clip": sin_clip, "salida_dispersa": dispersas, "binarias": len(binarias)}


def validaciones(ct, ent, s_tr, val, s_va, esperadas, algoritmos):
    """Las nueve, con su resultado calculado (error 24): {nombre: (resultado, detalle)}."""
    return {"filas": v_filas(ent, s_tr, val, s_va),
            "sin_objetivo": v_sin_objetivo(ct, s_tr),
            "sin_intermedias": v_sin_intermedias(ct, s_tr),
            "sin_vacios": v_sin_vacios(s_tr, s_va),
            "nombres_unicos": v_nombres_unicos_partes(s_tr, s_va),
            "sin_redundancia": v_sin_redundancia(ct, s_tr, algoritmos),
            "columnas_esperadas": v_columnas_esperadas(s_tr, esperadas, ent),
            "relleno_sin_choque": v_relleno_sin_choque(ent),
            "escalado_segun_matriz": v_escalado_segun_matriz(ct, s_tr, s_va)}


# ══ 5. Lo que se escribe en el JSON ═════════════════════════════════════════════
def filas_matriz(columnas_evento):
    """Las filas de la matriz aprobada que monta el preprocesador, para el JSON."""
    filas = [{"variable": c, "tipo": "nominal", "rama": "una columna por categoría, sin drop", "escalado": "ninguno",
              "relleno": "no tiene vacíos", "significado_relleno": None, "salida": [f"{c}_ohe_<categoría>"],
              "entra": True, "porque": "matriz aprobada; planteamientos §2, decisión 6 (tienda y departamento)"}
             for c in OHE_COLUMNAS]
    filas += [{"variable": c, "tipo": "nominal", "rama": "una columna por categoría, handle_unknown="
               "infrequent_if_exist", "escalado": "ninguno", "relleno": f"constante «{RELLENO_EVENTO}», sin marca",
               "significado_relleno": "día sin evento (reglas, apartado 5)", "salida": [f"{c}_ohe_<evento>"], "entra": True,
               "porque": "matriz aprobada: eventos del calendario, conocidos de antemano"} for c in EVENTO_COLUMNAS]
    filas.append({"variable": "snap", "tipo": "binaria", "rama": "tal cual", "escalado": "ninguno",
                  "relleno": "no tiene vacíos", "significado_relleno": None, "salida": ["snap"], "entra": True,
                  "porque": "matriz aprobada: SNAP sube la alimentación (exploratorio, H-04)"})
    filas.append({"variable": "evento_<nombre>", "tipo": "binaria", "rama": "tal cual", "escalado": "ninguno",
                  "relleno": "0 en los días sin ese evento", "significado_relleno": "sin ese evento",
                  "salida": list(columnas_evento), "entra": True, "porque": "matriz aprobada, respuesta 3"})
    filas += [{"variable": c, "tipo": "continua" if c.startswith("precio") else "discreta", "rama": "tal cual",
               "escalado": "StandardScaler", "relleno": "ninguno: no quedan vacíos", "significado_relleno": None,
               "salida": [f"{c}_ss"], "entra": True, "porque": "matriz aprobada, escalado pregunta 4"}
              for c in SS_COLUMNAS]
    filas += [{"variable": f"<obj>_{s}", "tipo": "continua", "rama": "tal cual", "escalado": "RobustScaler",
               "relleno": "ninguno: salen los 35 primeros días", "significado_relleno": None,
               "salida": [f"<obj>_{s}_rs"], "entra": True,
               "porque": "matriz aprobada, escalado pregunta 3 (colas sin tratar); <obj> es el objetivo del modelo"}
              for s in [f"lag_{k}" for k in RETARDOS] + [f"media_{w}" for w in VENTANAS]]
    return filas


FUERA = [("d", "identificador del día"), ("unidades", "objetivo del modelo de unidades; venta del mismo día en el otro"),
         ("dolares", "objetivo del modelo de dólares; venta del mismo día en el otro"),
         ("periodo", "marca de la partición"), ("cierre_tienda", "posterior a la decisión: se conoce al cerrar el día"),
         ("fuera_del_error", "posterior a la decisión: se conoce al cerrar el día"),
         ("clase_cero", "posterior a la decisión: usa la media del periodo entero"),
         ("cat_id", "copia de dept_id"), ("state_id", "copia de store_id"), ("wday", "copia de weekday"),
         ("event_type_1", "copia agrupada de event_name_1"), ("event_type_2", "copia agrupada de event_name_2"),
         ("year", "en la validación toma un valor que el entrenamiento no tiene"),
         ("date", "sus componentes ya entran"), ("wm_yr_wk", "identificador de la semana"),
         ("wm_yr_wk_anterior", "identificador de la semana anterior"), ("mes_parcial", "marca para no comparar"),
         ("semana_parcial", "marca para no comparar")]


# ══ 6. Ejecución ════════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Lee el JSON de las variables: si está PARADO o en ERROR, o las tablas tienen otra huella, no se empieza."""
    ruta = raiz / PREVIO_REL
    if not ruta.exists():
        return [f"falta {PREVIO_REL}"], None
    previo = json.loads(ruta.read_text(encoding="utf-8"))
    paradas = []
    estado = previo.get("resultado", {}).get("estado")
    if estado not in ("OK", "AVISO"):
        paradas.append(f"{PREVIO_REL} está en {estado}: no se empieza")
    huellas = {s.get("ruta"): s.get("sha256") for s in previo.get("salidas", [])}
    for rel in ENTRADAS.values():
        if not (raiz / rel).exists() or huellas.get(rel) != huella(raiz / rel):
            paradas.append(f"la huella de {rel} no es la de {PREVIO_REL}")
    return paradas, previo


def principal(raiz):
    """Construye, comprueba y describe los dos preprocesadores; devuelve el diccionario del JSON."""
    r = {"metodo": "preparacion-modelo", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [], "resultado": {}, "pendientes": []}
    paradas, previo = al_empezar(raiz)
    if paradas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "; ".join(paradas),
                          "artefactos": [JSON_REL], "siguiente": "volver a ejecutar scripts/11_variables_modelo.py"}
        return r
    ent = pd.read_parquet(raiz / ENTRADAS["entrenamiento"])
    val = pd.read_parquet(raiz / ENTRADAS["validacion"])
    for rel, t in zip(ENTRADAS.values(), (ent, val)):
        r["entradas"].append({"ruta": rel, "sha256": huella(raiz / rel), "filas": len(t), "columnas": t.shape[1]})
    columnas_evento = list(previo["eventos"]["columnas"])

    r["objetivo"] = {"columna": list(OBJETIVOS), "tipo": "cantidad", "clase_positiva": None,
                     "nota": "dos modelos: unidades a 10 días y dólares a 28 (reglas, apartado 5, «El horizonte»)"}
    r["desequilibrio"] = None
    r["algoritmo_previsto"] = " y ".join(ALGORITMOS) + ", con un solo preprocesador por objetivo"
    r["matriz"] = {"ruta": MATRIZ_REL, "aprobada_por": "el responsable del caso", "fecha": "2026-11-24",
                   "variables": filas_matriz(columnas_evento)}
    r["preprocesadores"] = {}
    todas = {}
    for objetivo in OBJETIVOS:
        entrada = columnas_entrada(objetivo, columnas_evento)
        faltan = [c for c in entrada if c not in ent.columns or c not in val.columns]
        if faltan:
            raise KeyError(f"faltan columnas de entrada: {faltan}")
        # Ajuste con el entrenamiento, una sola vez y solo para comprobar; la validación solo se transforma
        pipe = construir_preprocesador(objetivo, columnas_evento)
        s_tr = pipe.fit(ent).transform(ent)
        s_va = pipe.transform(val)
        ct = pipe.named_steps["preparacion"]
        esperadas = columnas_esperadas(ent, objetivo, columnas_evento)
        vals = validaciones(ct, ent, s_tr, val, s_va, esperadas, ALGORITMOS)
        # Un evento de event_name_2 que el entrenamiento no tiene en esa columna sale con todas sus columnas a cero
        conocidas = set(ent["event_name_2"].dropna())
        nuevas = val["event_name_2"].notna() & ~val["event_name_2"].isin(conocidas)
        familia = [s for s in s_va.columns if s.startswith("event_name_2_ohe_")]
        otro = "dolares" if objetivo == "unidades" else "unidades"
        r["preprocesadores"][objetivo] = {
            "script": SCRIPT_REL, "funcion": "construir_preprocesador", "columnas_entrada": entrada,
            "columnas_salida": list(s_tr.columns), "remainder": ct.remainder,
            "ajustado_con_filas": int(ct.named_transformers_["ss"].n_samples_seen_),
            "validaciones": {k: v[0] for k, v in vals.items()},
            "detalle_validaciones": {k: v[1] for k, v in vals.items()},
            "sin_variables_del_otro_objetivo": not any(c.startswith(f"{otro}_") for c in entrada),
            "comprobacion_evento_nuevo": {"eventos": sorted(val.loc[nuevas, "event_name_2"].unique()),
                                          "filas": int(nuevas.sum()),
                                          "todas_a_cero": bool((s_va.loc[nuevas.to_numpy(), familia] == 0).all().all())}}
        todas[objetivo] = vals
    r["validaciones"] = {k: all(todas[o][k][0] for o in OBJETIVOS) for k in todas[OBJETIVOS[0]]}
    r["fuera"] = [{"variable": v, "motivo": m} for v, m in FUERA]
    r["preprocesador"] = {"script": SCRIPT_REL, "funcion": "construir_preprocesador(objetivo, columnas_evento)",
                          "columnas_entrada": {o: r["preprocesadores"][o]["columnas_entrada"] for o in OBJETIVOS},
                          "columnas_salida": {o: r["preprocesadores"][o]["columnas_salida"] for o in OBJETIVOS},
                          "remainder": "drop", "ajustado": "no: lo ajusta aprendizaje-automatico con el entrenamiento"}
    r["parametros"] = [{"nombre": "sobrante del ColumnTransformer", "valor": "drop", "origen": "parametros.md"},
                       {"nombre": "mínimo para no agrupar una categoría", "valor": MIN_FRECUENCIA,
                        "origen": "parametros.md; ninguna categoría de eventos queda por debajo en el entrenamiento"},
                       {"nombre": "relleno categórico", "valor": RELLENO_EVENTO,
                        "origen": "matriz aprobada (en lugar de «sin dato»: el vacío es un día sin evento)"},
                       {"nombre": "semilla", "valor": 42, "origen": "parametros.md; ningún paso usa azar"},
                       {"nombre": "drop de las codificaciones", "valor": None, "origen": "matriz aprobada"}]
    r["validacion_usada"] = ("la validación con retardos reales de hechos_modelo_validacion solo se transforma para "
                             "comprobar; no mide el modelo (planteamientos §2, decisión 2)")
    bien = all(r["validaciones"].values())
    r["resultado"] = {"estado": "OK" if bien else "ERROR", "riesgo": "bajo" if bien else "alto",
                      "resumen": (f"preprocesador de la matriz aprobada, uno por objetivo con "
                                  f"{len(r['preprocesadores']['unidades']['columnas_salida'])} columnas de salida; "
                                  f"{sum(r['validaciones'].values())} de 9 validaciones en verde en los dos"),
                      "artefactos": [JSON_REL],
                      "siguiente": "preseleccion-variables §1: propuesta al responsable del caso (informes/preseleccion_propuesta.md)"}
    return r


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", type=Path, default=CASO)
    raiz = argumentos.parse_args().raiz.resolve()
    try:
        resultado = principal(raiz)
    except Exception:
        resultado = {"metodo": "preparacion-modelo", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                     "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "entorno": entorno(),
                     "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": traceback.format_exc()[-1500:],
                                   "artefactos": [JSON_REL], "siguiente": "corregir el fallo técnico"},
                     "pendientes": []}
    (raiz / JSON_REL).write_text(json.dumps(a_json_limpio(resultado), ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado["resultado"]["estado"] in ("OK", "AVISO") else 1)
