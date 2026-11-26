"""Variables nuevas del modelo del caso 69: retardos, medias, productos con precio, eventos y día del mes.

Aplica la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 (config/modelo/
matriz_transformaciones.md, «Lo que aprobó el responsable del caso») con el método transformacion-datos. Une la historia de entrenamiento y
de validación, de modo que los primeros días de la validación tomen los últimos del entrenamiento, calcula con
scripts/variables_prevision.py las variables de los dos objetivos y las demás, quita del entrenamiento los primeros 35
días de cada serie (planteamientos §2, decisión 7) y guarda las dos tablas solo si pasan sus validaciones. Deja
informes/variables_modelo.json y una ficha por transformación nueva en el registro de transformaciones.

La tabla de validación lleva los retardos con la venta real: sirve para comprobar el preprocesador y nunca para medir el
modelo, que en la validación prevé de forma recursiva (planteamientos §2, decisión 2).

Depende de lo que dejan otros scripts (error 2): las dos partes de scripts/10_particion.py, cuya huella se comprueba
contra informes/particion.json; precios_corregido.parquet (scripts/03_correccion_datos.py); dim_producto.parquet
(scripts/05_transformacion_datos.py); calendario.parquet (scripts/04_modelado_datos.py).

Uso: python -W error scripts/11_variables_modelo.py [--raiz CARPETA]
  --raiz: carpeta con la estructura del caso. Por defecto, la del caso. La prueba la usa con datos pequeños.
Sale con 0 si el estado es OK o AVISO y con 1 si es PARADO o ERROR.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import inspect
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import variables_prevision as vp  # noqa: E402

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método transformacion-datos con que se escribió este script
SCRIPT_REL = "scripts/11_variables_modelo.py"

# Fecha de referencia de los datos (reglas, apartado 5, «Fechas»)
FECHA_DATOS = "2015-05-22"

# Planteamientos §2, decisión 7: salen los primeros 35 días de cada serie del entrenamiento (29 por los retardos y 6
# por el precio medio vacío en las cinco primeras semanas); la validación no pierde ninguna fila
DIAS_SIN_HISTORIA = 35

ENTRADAS = {"entrenamiento": "data/processed/hechos_series_entrenamiento.parquet",
            "validacion": "data/processed/hechos_series_validacion.parquet",
            "precios": "data/processed/precios_corregido.parquet",
            "dim_producto": "data/processed/dim_producto.parquet",
            "calendario": "data/processed/calendario.parquet"}
SALIDAS = {"entrenamiento": "data/processed/hechos_modelo_entrenamiento.parquet",
           "validacion": "data/processed/hechos_modelo_validacion.parquet"}
PARTICION_REL = "informes/particion.json"
JSON_REL = "informes/variables_modelo.json"
REGISTRO_REL = "config/modelo/registro-transformaciones.md"
MATRIZ_REL = "config/modelo/matriz_transformaciones.md"
RESULTADO = {True: "pasa", False: "falla"}


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


def entorno():
    """Versiones con que se ejecuta el script."""
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
            "pyarrow": pyarrow.__version__, "scikit-learn": sklearn.__version__, "ejecutable": sys.executable}


def version_metodo():
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def validacion(nombre, condicion, detalle):
    """Una validación con su resultado calculado de la condición, nunca escrito a mano (error 24)."""
    return {"validacion": nombre, "resultado": RESULTADO[bool(condicion)], "ok": bool(condicion), "detalle": detalle}


def suma(serie, decimales=2):
    """Suma de una columna redondeada para el JSON; None si tiene algún vacío (un vacío no es un cero, error 10)."""
    if serie.isna().any():
        return None
    return round(float(serie.astype("float64").sum()), decimales)


# ══ 3. Al empezar ═══════════════════════════════════════════════════════════════
def al_empezar(raiz):
    """Lee informes/particion.json: si está PARADO o en ERROR, o las partes tienen otra huella, no se empieza."""
    ruta = raiz / PARTICION_REL
    if not ruta.exists():
        return [f"falta {PARTICION_REL}"]
    particion = json.loads(ruta.read_text(encoding="utf-8"))
    paradas = []
    estado = particion.get("resultado", {}).get("estado")
    if estado in ("PARADO", "ERROR") or estado is None:
        paradas.append(f"la partición está en {estado}: no se empieza (resultado.md, «Al empezar»)")
    huellas = {p.get("parte"): p.get("sha256") for p in particion.get("partes", [])}
    for parte in ("entrenamiento", "validacion"):
        actual = huella(raiz / ENTRADAS[parte])
        if huellas.get(parte) != actual:
            paradas.append(f"la huella de {ENTRADAS[parte]} no es la de la partición")
    return paradas


# ══ 4. Variables nuevas ═════════════════════════════════════════════════════════
# ── 4.1 Historia unida y retardos y medias de los dos objetivos ──
def historia_unida(entrenamiento, validacion_):
    """Las dos partes en una sola historia por serie y fecha, para que la validación tome el final del entrenamiento."""
    historia = pd.concat([entrenamiento, validacion_], ignore_index=True)
    return historia.sort_values(vp.CLAVE_SERIE + [vp.COLUMNA_FECHA]).reset_index(drop=True)


def anadir_retardos_y_medias(historia):
    """Las 12 variables de cada objetivo, cada una con la historia de su propio objetivo."""
    salida = historia.copy()
    for objetivo in vp.OBJETIVOS:
        salida = salida.join(vp.crear_variables_objetivo(historia, objetivo))
    return salida


# ── 4.2 Los primeros días de cada serie, sin historia ──
def quitar_primeros_dias(entrenamiento, dias):
    """Separa los primeros `dias` días de cada serie del entrenamiento (planteamientos §2, decisión 7)."""
    puesto = entrenamiento.groupby(vp.CLAVE_SERIE)[vp.COLUMNA_FECHA].rank(method="first")
    quitar = puesto <= dias
    return entrenamiento[~quitar].reset_index(drop=True), entrenamiento[quitar].reset_index(drop=True)


# ══ 5. Registro de transformaciones ═════════════════════════════════════════════
REGLAS = {
    "retardos_unidades": ["crear_variables_objetivo", "comprobar_sin_huecos", "comprobar_retardos_y_medias"],
    "retardos_dolares": ["crear_variables_objetivo", "comprobar_sin_huecos", "comprobar_retardos_y_medias"],
    "productos_con_precio": ["contar_productos_que_cuentan", "anadir_productos_con_precio", "orden_de_semanas"],
    "eventos": ["lista_eventos", "anadir_eventos"],
    "dia_del_mes": ["anadir_dia_del_mes"],
    "primeros_dias": ["quitar_primeros_dias"],
}


def huella_regla(clave):
    """Huella corta del código de las funciones de una regla y de su constante: cambia si cambia la regla."""
    fuentes = []
    for nombre in REGLAS[clave]:
        funcion = getattr(vp, nombre, None) or globals()[nombre]
        fuentes.append(inspect.getsource(funcion))
    fuentes.append(f"{vp.RETARDOS}{vp.VENTANAS}{vp.SEMANAS_PREVIAS_CON_PRECIO}{DIAS_SIN_HISTORIA}")
    return hashlib.sha256("".join(fuentes).encode("utf-8")).hexdigest()[:12]


def fmt(n, decimales=0):
    """Número a la española: punto de miles y coma decimal."""
    if n is None:
        return "sin dato"
    texto = f"{n:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def contenido_fichas(r):
    """Las seis fichas, con sus cifras tomadas del diccionario de resultados de esta ejecución."""
    c = r["cifras_control"]
    q = r["filas_quitadas"]
    fecha = r["fecha_ejecucion"][:10]
    fecha_es = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
    permiso = (f"el agente analista-preparacion-modelo ejecuta `{SCRIPT_REL}` por la petición de la sesión principal "
               f"del {fecha_es} (variables nuevas, preprocesador y propuesta de preselección), con la matriz de "
               "transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).")
    tablas = "`hechos_modelo_entrenamiento` y `hechos_modelo_validacion`"
    fichas = []
    for objetivo, unidad in (("unidades", "unidades"), ("dolares", "dólares")):
        e, v = c["entrenamiento"], c["validacion"]
        dec = 0 if objetivo == "unidades" else 2
        fichas.append((f"retardos_{objetivo}", f"{tablas}: retardos y medias de {unidad}", [
            f"{tablas} (nuevas): `{objetivo}_lag_1` a `{objetivo}_lag_7`, `{objetivo}_lag_14`, `{objetivo}_lag_21`, "
            f"`{objetivo}_lag_28`, `{objetivo}_media_7` y `{objetivo}_media_28`.",
            f"la venta en {unidad} de cada día, sin su historia en la misma fila.",
            f"el modelo de {unidad} prevé con la venta hasta la víspera (reglas, apartado 5, «Lo que se sabe el día de prever»).",
            "la fijan los planteamientos (§2, decisión 7) con la matriz aprobada: dentro de cada serie ordenada por "
            "fecha, solo con días anteriores al de la fila. La misma función sirve para la previsión recursiva. Las dos partes se "
            "calculan sobre la historia unida, así que los primeros días de la validación toman los últimos del "
            "entrenamiento. Salen del objetivo: el modelo de dólares usa solo las de dólares y el de unidades, las suyas.",
            ["comprobar_sin_huecos(historia)   # para si una serie tiene un día que falta o repetido",
             f"grupo = historia.sort_values([\"store_id\", \"dept_id\", \"date\"]).groupby([\"store_id\", \"dept_id\"])[\"{objetivo}\"]",
             f"df[\"{objetivo}_lag_k\"] = grupo.shift(k)   # k = 1..7, 14, 21, 28",
             f"df[\"{objetivo}_media_w\"] = grupo.shift(1) agrupado por serie .rolling(w, min_periods=w).mean()   # w = 7, 28"],
            f"entrenamiento: `{objetivo}_lag_1` suma {fmt(e[f'{objetivo}_lag_1'], dec)}, `{objetivo}_lag_28` "
            f"{fmt(e[f'{objetivo}_lag_28'], dec)} y `{objetivo}_media_28` {fmt(e[f'{objetivo}_media_28'], 2)}; "
            f"validación: {fmt(v[f'{objetivo}_lag_1'], dec)}, {fmt(v[f'{objetivo}_lag_28'], dec)} y "
            f"{fmt(v[f'{objetivo}_media_28'], 2)}. 0 vacíos en las dos tablas. Rehechas por otro camino (unión por "
            f"serie y fecha t − k): {r['comprobacion_retardos'][objetivo]['filas_distintas']} filas distintas.",
            "12 columnas más en cada tabla.",
            f"quitar las columnas: `df = df.drop(columns=vp.nombres_variables(\"{objetivo}\"))`."]))
    fichas.append(("productos_con_precio", f"{tablas}: productos_con_precio_semana_anterior", [
        f"{tablas} (nueva): `productos_con_precio_semana_anterior`.",
        "el precio va por producto, tienda y semana; no había ninguna cifra de los productos que se venden en cada "
        "departamento.",
        "que el modelo vea la llegada de productos nuevos, que en una serie multiplica la venta por 7,2 (ficha; "
        "planteamientos §2, decisión 7).",
        "cuestión 001, resuelta por el responsable del caso el 24/11/2026: cuentan los productos del departamento con precio en la "
        "tienda la semana anterior que ya tenían precio cuatro semanas antes, la regla del precio medio (reglas, apartado 5, "
        "«El precio»). Las semanas se ordenan por sus fechas, porque el código salta al cambiar de año.",
        ["posicion = precios[\"wm_yr_wk\"].map(orden_de_las_semanas)   # por el orden de las fechas",
         "cuenta = posicion - posicion.groupby([store_id, item_id]).transform(\"min\") >= 4",
         "conteo = precios.assign(cuenta=cuenta).groupby([\"store_id\", \"dept_id\", \"wm_yr_wk\"])[\"cuenta\"].sum()",
         "df = df.merge(conteo, left_on=[..., \"wm_yr_wk_anterior\"], right_on=[..., \"wm_yr_wk\"], validate=\"many_to_one\")"],
        f"en el entrenamiento suma {fmt(c['entrenamiento']['productos_con_precio_semana_anterior'])}, de "
        f"{fmt(c['entrenamiento']['productos_min'])} a {fmt(c['entrenamiento']['productos_max'])} por fila. En la "
        f"validación suma {fmt(c['validacion']['productos_con_precio_semana_anterior'])}, de "
        f"{fmt(c['validacion']['productos_min'])} a {fmt(c['validacion']['productos_max'])}. 0 vacíos.",
        "una columna más en cada tabla.",
        "quitar la columna: `df = df.drop(columns=\"productos_con_precio_semana_anterior\")`."]))
    ev = r["eventos"]
    fichas.append(("eventos", f"{tablas}: evento_<nombre>", [
        f"{tablas} (nuevas): una columna `evento_<nombre>` por evento, {ev['numero']} en total.",
        "el evento de un día está en `event_name_1` o en `event_name_2`.",
        "«Father's day» cae en `event_name_2` en la validación y en el entrenamiento solo en `event_name_1`; con las "
        "dos columnas por separado, ese día sale sin evento (matriz, candidatas).",
        "matriz aprobada, respuesta 3: candidata al lado de `event_name_1` y `event_name_2`. La lista de eventos sale "
        "solo del entrenamiento. El nombre de la columna es el del evento tal cual, sin cambiarlo.",
        ["eventos = sorted(set(ent[\"event_name_1\"].dropna()) | set(ent[\"event_name_2\"].dropna()))",
         "df[f\"evento_{e}\"] = ((df[\"event_name_1\"] == e) | (df[\"event_name_2\"] == e)).astype(int)"],
        f"{ev['numero']} eventos en el entrenamiento; {len(ev['nuevos_en_validacion'])} nuevos en la validación. "
        f"Días de serie con algún evento: {fmt(ev['filas_con_evento']['entrenamiento'])} en el entrenamiento y "
        f"{fmt(ev['filas_con_evento']['validacion'])} en la validación.",
        f"{ev['numero']} columnas de 0 y 1 más en cada tabla.",
        "quitar las columnas que empiezan por `evento_`."]))
    fichas.append(("dia_del_mes", f"{tablas}: dia_del_mes", [
        f"{tablas} (nueva): `dia_del_mes`.",
        "la fecha entera, en `date`.",
        "los días SNAP caen siempre en los días 1 a 15 del mes: el día del mes da esa quincena aunque no haya SNAP "
        "(matriz, candidatas).",
        "matriz aprobada, respuesta 4: candidata.",
        ["df[\"dia_del_mes\"] = df[\"date\"].dt.day"],
        f"de {c['entrenamiento']['dia_del_mes_min']} a {c['entrenamiento']['dia_del_mes_max']} en el entrenamiento; "
        "0 vacíos en las dos tablas.",
        "una columna más en cada tabla.",
        "quitar la columna: `df = df.drop(columns=\"dia_del_mes\")`."]))
    fichas.append(("primeros_dias", "hechos_modelo_entrenamiento: salen los primeros 35 días de cada serie", [
        "`hechos_modelo_entrenamiento`: filas.",
        f"el entrenamiento tenía {fmt(q['filas_antes'])} filas, {q['series']} series con {fmt(q['dias_por_serie'])} "
        "días cada una.",
        "los primeros días de cada serie no tienen la historia que piden las variables: 29 por los retardos y 6 más "
        "porque el precio medio de la semana anterior está vacío en las cinco primeras semanas (reglas, apartado 7, «Población "
        "del análisis»).",
        "lo fijan los planteamientos (§2, decisión 7) con la respuesta 2 de la matriz aprobada (el responsable del caso, 24/11/2026, "
        "una nota interna): salen 35 días, no 29. La validación no pierde ninguna fila. No cambian ninguna respuesta: son días de la construcción de 2011, "
        "fuera de la validación donde se decide y se mide el modelo.",
        ["puesto = ent.groupby([\"store_id\", \"dept_id\"])[\"date\"].rank(method=\"first\")",
         "ent = ent[puesto > 35]"],
        f"salen {fmt(q['filas_quitadas'])} filas, del {q['desde']:%d/%m/%Y} al {q['hasta']:%d/%m/%Y}. Llevan "
        f"{fmt(q['unidades_quitadas'])} unidades y {fmt(q['dolares_quitados'], 2)} dólares. Quedan "
        f"{fmt(q['filas_despues'])} filas. Después, 0 vacíos en las variables nuevas y en el precio medio.",
        f"`hechos_modelo_entrenamiento.parquet` con {fmt(q['filas_despues'])} filas; las quitadas siguen en "
        "`hechos_series_entrenamiento.parquet`.",
        "volver a unir las filas quitadas desde `hechos_series_entrenamiento.parquet`; sus retardos y su precio "
        "medio salen vacíos, así que la validación de vacíos del script tendría que cambiar con ellas."]))
    return [(clave, titulo, campos, permiso) for clave, titulo, campos in fichas]


def escribir_fichas(raiz, r):
    """Añade al registro una ficha por regla nueva o cambiada; si la regla ya está con su huella, no la repite."""
    ruta = raiz / REGISTRO_REL
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else "# Registro de transformaciones\n"
    numeros = [int(n) for n in re.findall(r"^### R-(\d{3})", texto, flags=re.M)]
    siguiente = max(numeros, default=0) + 1
    nuevas = []
    escritas = []
    for clave, titulo, campos, permiso in contenido_fichas(r):
        marca = f"Regla: `{clave}` · huella `{huella_regla(clave)}`"
        if marca in texto:
            continue
        tabla, como, problema, decision, codigo, comprobacion, quedo, deshacer = campos
        bloque = [f"### R-{siguiente:03d} · {r['fecha_ejecucion'][8:10]}/{r['fecha_ejecucion'][5:7]}/"
                  f"{r['fecha_ejecucion'][:4]} · {titulo}", "",
                  f"1. **Tabla y columna:** {tabla}", "", f"2. **Cómo estaba:** {como}", "",
                  f"3. **Problema o finalidad:** {problema}", "", f"4. **Decisión:** {decision}", "",
                  "5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.", "",
                  "   ```python", *[f"   {linea}" for linea in codigo], "   ```", "",
                  f"6. **Quién y con qué permiso:** {permiso}", "", f"7. **Comprobación:** {comprobacion}", "",
                  f"8. **Cómo quedó:** {quedo}", "", f"9. **Cómo deshacer:** {deshacer}", "", marca, ""]
        nuevas.append("\n".join(bloque))
        escritas.append(f"R-{siguiente:03d}")
        siguiente += 1
    if nuevas:
        cabecera = "## Fichas de las variables del modelo (`scripts/11_variables_modelo.py`)"
        prefijo = "" if cabecera in texto else f"\n{cabecera}\n"
        ruta.write_text(texto.rstrip("\n") + "\n" + prefijo + "\n" + "\n".join(nuevas), encoding="utf-8")
    return escritas


# ══ 6. Ejecución ════════════════════════════════════════════════════════════════
def cifras_tabla(t, nuevas):
    """Sumas de control de una tabla de salida: cada variable nueva, sus vacíos y los rangos del conteo y del día."""
    cifras = {c: suma(t[c]) for c in nuevas}
    cifras["vacios_variables_nuevas"] = int(t[nuevas].isna().sum().sum())
    cifras["vacios_precio_medio"] = int(t["precio_medio_semana_anterior"].isna().sum())
    cifras["productos_min"] = int(t[vp.COLUMNA_PRODUCTOS].min())
    cifras["productos_max"] = int(t[vp.COLUMNA_PRODUCTOS].max())
    cifras["dia_del_mes_min"] = int(t["dia_del_mes"].min())
    cifras["dia_del_mes_max"] = int(t["dia_del_mes"].max())
    cifras["filas"] = len(t)
    cifras["unidades"] = int(t["unidades"].sum())
    cifras["dolares"] = suma(t["dolares"])
    return cifras


def principal(raiz):
    """Ejecuta el paso entero y devuelve el diccionario de resultados (el JSON)."""
    r = {"metodo": "transformacion-datos", "version_metodo": version_metodo(), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [], "resultado": {}, "pendientes": [],
         "uso_de_la_validacion": ("hechos_modelo_validacion lleva los retardos y las medias calculados con la venta "
                                  "real hasta la víspera de cada día. Sirve solo para comprobar el preprocesador. "
                                  "Nunca mide el modelo: en la validación el modelo prevé de forma recursiva desde "
                                  "cada origen, con lo previsto después del origen (planteamientos §2, decisión 2)."),
         "parametros": [{"nombre": "retardos", "valor": list(vp.RETARDOS), "origen": "planteamientos §2, decisión 7"},
                        {"nombre": "ventanas de las medias", "valor": list(vp.VENTANAS),
                         "origen": "planteamientos §2, decisión 7"},
                        {"nombre": "dias_sin_historia", "valor": DIAS_SIN_HISTORIA,
                         "origen": "planteamientos §2, decisión 7; matriz, respuesta 2"},
                        {"nombre": "semanas_previas_con_precio", "valor": vp.SEMANAS_PREVIAS_CON_PRECIO,
                         "origen": "reglas-negocio §5, «El precio»; cuestión 001"}],
         "validaciones": [], "salidas": []}

    # Huellas de las entradas antes de nada: tienen que salir iguales al final
    for nombre, rel in ENTRADAS.items():
        r["entradas"].append({"ruta": rel, "sha256": huella(raiz / rel)})
    paradas = al_empezar(raiz)
    if paradas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "; ".join(paradas),
                          "artefactos": [JSON_REL], "siguiente": "revisar la partición antes de crear variables"}
        return r

    ent = pd.read_parquet(raiz / ENTRADAS["entrenamiento"])
    val = pd.read_parquet(raiz / ENTRADAS["validacion"])
    precios = pd.read_parquet(raiz / ENTRADAS["precios"])
    dim_producto = pd.read_parquet(raiz / ENTRADAS["dim_producto"])
    calendario = pd.read_parquet(raiz / ENTRADAS["calendario"])
    for e, t in zip(r["entradas"], [ent, val, precios, dim_producto, calendario]):
        e["filas"], e["columnas"] = len(t), t.shape[1]
    columnas_entrada = list(ent.columns)

    # 4.1 Historia unida; si una serie tiene un hueco de fecha, se para sin guardar
    historia = historia_unida(ent, val)
    try:
        con_retardos = anadir_retardos_y_medias(historia)
        sin_huecos, detalle_huecos = True, "cada serie tiene una fila por día, sin huecos ni días repetidos"
    except vp.HuecoDeFecha as error:
        sin_huecos, detalle_huecos = False, str(error)
    r["validaciones"].append(validacion("sin huecos de fecha en ninguna serie", sin_huecos, detalle_huecos))
    if not sin_huecos:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": detalle_huecos,
                          "artefactos": [JSON_REL], "siguiente": "revisar la serie con el hueco"}
        return r

    # 4.2 Productos con precio la semana anterior, eventos del entrenamiento y día del mes
    orden = vp.orden_de_semanas(calendario)
    conteo = vp.contar_productos_que_cuentan(precios, dim_producto, orden)
    filas_antes = len(con_retardos)
    df = vp.anadir_productos_con_precio(con_retardos, conteo)
    eventos = vp.lista_eventos(ent)
    df = vp.anadir_dia_del_mes(vp.anadir_eventos(df, eventos))
    r["cruces"] = [{"cruce": "precios con dim_producto (departamento de cada producto)", "validate": "many_to_one",
                    "filas_antes": len(precios), "grupos_tienda_departamento_semana": len(conteo),
                    "nota": "la función para si algún precio no tiene departamento o su semana no está en el Calendario"},
                   {"cruce": "historia con el conteo por tienda, departamento y semana anterior",
                    "validate": "many_to_one", "filas_antes": filas_antes, "filas_despues": len(df)}]
    nuevas = [c for c in df.columns if c not in columnas_entrada]

    # La comprobación de retardos y medias, por otro camino, sobre la historia entera (las dos partes)
    r["comprobacion_retardos"] = {o: vp.comprobar_retardos_y_medias(df, o) for o in vp.OBJETIVOS}

    # 4.3 De vuelta a las dos partes y salida de los primeros días del entrenamiento
    ent_v = df[df["periodo"] == "construccion"].reset_index(drop=True)
    val_v = df[df["periodo"] == "validacion"].reset_index(drop=True)
    series = ent_v.groupby(vp.CLAVE_SERIE).ngroups
    dias_por_serie = ent_v.groupby(vp.CLAVE_SERIE).size()
    ent_m, quitadas = quitar_primeros_dias(ent_v, DIAS_SIN_HISTORIA)
    r["filas_quitadas"] = {"filas_antes": len(ent_v), "series": series,
                           "dias_por_serie": int(dias_por_serie.min()) if dias_por_serie.nunique() == 1 else None,
                           "filas_quitadas": len(quitadas), "filas_despues": len(ent_m),
                           "desde": quitadas[vp.COLUMNA_FECHA].min(), "hasta": quitadas[vp.COLUMNA_FECHA].max(),
                           "unidades_quitadas": int(quitadas["unidades"].sum()),
                           "dolares_quitados": suma(quitadas["dolares"])}

    # 4.4 Validaciones, que paran sin guardar
    esperadas_ent = len(ent) - series * DIAS_SIN_HISTORIA
    v = r["validaciones"]
    v.append(validacion("filas del entrenamiento: las de entrada menos 35 días de cada serie",
                        len(ent_m) == esperadas_ent and bool((dias_por_serie > DIAS_SIN_HISTORIA).all()),
                        {"filas": len(ent_m), "esperadas": esperadas_ent}))
    v.append(validacion("filas de la validación: las de entrada, sin perder ninguna",
                        len(val_v) == len(val) and set(val_v["d"] + val_v["store_id"] + val_v["dept_id"])
                        == set(val["d"] + val["store_id"] + val["dept_id"]),
                        {"filas": len(val_v), "esperadas": len(val)}))
    for nombre_parte, t in (("entrenamiento", ent_m), ("validacion", val_v)):
        vacias = {c: int(t[c].isna().sum()) for c in nuevas if t[c].isna().any()}
        v.append(validacion(f"ninguna variable nueva vacía en {nombre_parte}", not vacias, vacias))
    for objetivo in vp.OBJETIVOS:
        comp = r["comprobacion_retardos"][objetivo]
        v.append(validacion(f"retardos y medias de {objetivo}: ninguno usa el día de su fila ni días de otra serie",
                            comp["filas_distintas"] == 0, comp))
    for nombre_parte, t in (("entrenamiento", ent_m), ("validacion", val_v)):
        n = int(t["precio_medio_semana_anterior"].isna().sum())
        v.append(validacion(f"precio medio de la semana anterior sin vacíos en {nombre_parte}", n == 0,
                            {"vacios": n}))
    sumas_ok = (int(ent_m["unidades"].sum()) + int(quitadas["unidades"].sum()) == int(ent["unidades"].sum())
                and int(val_v["unidades"].sum()) == int(val["unidades"].sum()))
    v.append(validacion("las unidades de entrada se conservan: entrenamiento más quitadas y validación", sumas_ok,
                        {"entrenamiento_entrada": int(ent["unidades"].sum()),
                         "validacion_entrada": int(val["unidades"].sum())}))

    # Eventos: la lista sale solo del entrenamiento; los nuevos en la validación se cuentan
    en_val = vp.lista_eventos(val)
    columnas_evento = [f"{vp.PREFIJO_EVENTO}{e}" for e in eventos]
    r["eventos"] = {"numero": len(eventos), "lista": eventos,
                    "nuevos_en_validacion": [e for e in en_val if e not in eventos],
                    "filas_con_evento": {"entrenamiento": int((ent_m[columnas_evento].sum(axis=1) > 0).sum()),
                                         "validacion": int((val_v[columnas_evento].sum(axis=1) > 0).sum())},
                    "columnas": columnas_evento}

    r["cifras_control"] = {"entrenamiento": cifras_tabla(ent_m, nuevas), "validacion": cifras_tabla(val_v, nuevas)}
    r["variables_generadas"] = (
        [{"columna": f"{o}_lag_{k}", "formula": f"{o} de la misma serie el día t - {k}", "columnas_origen": [o, "date"],
          "unidad": "unidades" if o == "unidades" else "dólares", "informacion_posterior": False,
          "sale_del_objetivo": True, "suma_de_otras": False} for o in vp.OBJETIVOS for k in vp.RETARDOS]
        + [{"columna": f"{o}_media_{w}", "formula": f"media de {o} de la misma serie de t - {w} a t - 1",
            "columnas_origen": [o, "date"], "unidad": "unidades" if o == "unidades" else "dólares",
            "informacion_posterior": False, "sale_del_objetivo": True, "suma_de_otras": False,
            "nota": f"es la media de los retardos 1 a {w}: con lag_1 a lag_7 dentro, media_7 es su combinación lineal"}
           for o in vp.OBJETIVOS for w in vp.VENTANAS]
        + [{"columna": vp.COLUMNA_PRODUCTOS, "formula": "productos del departamento con precio en la tienda la semana "
            "anterior que ya tenían precio cuatro semanas antes", "columnas_origen": ["sell_price", "wm_yr_wk",
            "wm_yr_wk_anterior", "dept_id"], "unidad": "productos", "informacion_posterior": False,
            "sale_del_objetivo": False, "suma_de_otras": False},
           {"columna": "evento_<nombre>", "formula": "1 si event_name_1 o event_name_2 es ese evento",
            "columnas_origen": ["event_name_1", "event_name_2"], "unidad": None, "informacion_posterior": False,
            "sale_del_objetivo": False, "suma_de_otras": False},
           {"columna": "dia_del_mes", "formula": "date.dt.day", "columnas_origen": ["date"], "unidad": "día",
            "informacion_posterior": False, "sale_del_objetivo": False, "suma_de_otras": False}])
    r["transformaciones"] = [
        {"id": "T-01", "transformacion": "retardos y medias de unidades", "columnas": vp.nombres_variables("unidades"),
         "regla": "planteamientos §2, decisión 7"},
        {"id": "T-02", "transformacion": "retardos y medias de dólares", "columnas": vp.nombres_variables("dolares"),
         "regla": "planteamientos §2, decisión 7"},
        {"id": "T-03", "transformacion": "productos con precio la semana anterior", "columnas": [vp.COLUMNA_PRODUCTOS],
         "regla": "reglas-negocio §5, «El precio»; cuestión 001"},
        {"id": "T-04", "transformacion": "una columna por evento", "columnas": columnas_evento,
         "regla": "matriz aprobada, respuesta 3"},
        {"id": "T-05", "transformacion": "día del mes", "columnas": ["dia_del_mes"], "regla": "matriz, respuesta 4"},
        {"id": "T-06", "transformacion": "salen los primeros 35 días de cada serie del entrenamiento", "columnas": [],
         "regla": "planteamientos §2, decisión 7; matriz, respuesta 2"}]
    r["particion"] = {"columna_fecha": "date",
                      "desarrollo": {"desde": ent_m["date"].min(), "hasta": ent_m["date"].max()},
                      "validacion": {"desde": val_v["date"].min(), "hasta": val_v["date"].max()},
                      "fuente": "reglas-negocio §5, «Fechas»; informes/particion.json"}

    fallidas = [x["validacion"] for x in v if not x["ok"]]
    if fallidas:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto",
                          "resumen": f"{len(fallidas)} validaciones no pasan; no se guarda ninguna tabla",
                          "artefactos": [JSON_REL], "siguiente": "revisar: " + "; ".join(fallidas)}
        return r

    # 4.5 Guardar, solo con todas las validaciones en verde (error 15), ordenadas por serie y fecha
    orden_filas = vp.CLAVE_SERIE + [vp.COLUMNA_FECHA]
    for parte, t in (("entrenamiento", ent_m), ("validacion", val_v)):
        t = t.sort_values(orden_filas).reset_index(drop=True)
        # Sin vacíos (validado), el conteo pasa de entero con vacíos a entero simple
        t[vp.COLUMNA_PRODUCTOS] = t[vp.COLUMNA_PRODUCTOS].astype("int64")
        t.to_parquet(raiz / SALIDAS[parte], index=False)
        r["salidas"].append({"tabla": Path(SALIDAS[parte]).stem, "ruta": SALIDAS[parte],
                             "sha256": huella(raiz / SALIDAS[parte]), "filas": len(t), "columnas": t.shape[1],
                             "que_es_una_fila": "un departamento en una tienda un día",
                             "uso": "ajustar y elegir con validación cruzada" if parte == "entrenamiento"
                             else "solo comprobar el preprocesador; no mide el modelo"})
    r["entradas_despues_iguales"] = all(huella(raiz / e["ruta"]) == e["sha256"] for e in r["entradas"])
    r["resultado"] = {"estado": "OK" if r["entradas_despues_iguales"] else "ERROR",
                      "riesgo": "bajo" if r["entradas_despues_iguales"] else "alto",
                      "resumen": f"{len(nuevas)} variables nuevas; entrenamiento con {len(ent_m)} filas tras quitar "
                                 f"{len(quitadas)} y validación con {len(val_v)}; {len(v)} validaciones en verde.",
                      "artefactos": [JSON_REL, *SALIDAS.values(), REGISTRO_REL],
                      "siguiente": "preparacion-modelo §4 a §6: scripts/12_preparacion.py"}
    r["fichas"] = escribir_fichas(raiz, r)
    return r


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", type=Path, default=CASO)
    raiz = argumentos.parse_args().raiz.resolve()
    try:
        resultado = principal(raiz)
    except Exception:
        resultado = {"metodo": "transformacion-datos", "script": SCRIPT_REL, "fecha_datos": FECHA_DATOS,
                     "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "entorno": entorno(),
                     "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": traceback.format_exc()[-1500:],
                                   "artefactos": [JSON_REL], "siguiente": "corregir el fallo técnico"},
                     "pendientes": []}
    for clave in ("validaciones",):
        for x in resultado.get(clave, []):
            x.pop("ok", None)
    (raiz / JSON_REL).write_text(json.dumps(a_json_limpio(resultado), ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["resultado"]["estado"], "·", resultado["resultado"]["resumen"])
    sys.exit(0 if resultado["resultado"]["estado"] in ("OK", "AVISO") else 1)
