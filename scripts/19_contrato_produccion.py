"""Contrato de producción del caso 69: la parte 1 del método preproduccion.

Lee el ganador de cada objetivo (informes/busqueda.json), comprueba que es el que la validación dio por bueno
(informes/validacion.json y el veredicto aprobado en config/metodo/04_planteamientos.md), saca de la matriz
aprobada (informes/preparacion.json, «matriz») de qué finalista sale cada columna, tira del hilo en el registro de
transformaciones y separa cada paso en sus cuatro clases (método, apartado 1.3). Deja config/modelo/contrato_produccion.md
e informes/preproduccion.json. No escribe código de producción: el contrato lo aprueba el responsable del caso antes.

Para con ERROR si una columna del ganador no sale de ninguna finalista, si una finalista no tiene cadena completa en el
registro, si un paso que aprende se ajustó antes de la partición o con más filas que el entrenamiento, o si queda un
campo vacío en el contrato. El contrato solo se escribe con las cuatro validaciones en verde (error 15).

Depende de lo que dejan otros scripts (error 2): informes/busqueda.json (15), informes/validacion.json (16),
informes/preparacion.json (12), informes/preseleccion.json (13) e informes/variables_modelo.json (11). La huella de
busqueda.json tiene que ser la que registró la validación. No abre ningún dato: solo JSON y documentos.

La aprobación del responsable del caso se lee del registro de transformaciones: la ficha del contrato aprobado («contrato de producción
aprobado», con «el responsable del caso, DD/MM/AAAA: «...» (referencia de la decisión)»). Con ella, el contrato y el JSON dicen quién lo aprobó y cuándo.

La parte 2 (petición 27): con el contrato aprobado y las carpetas que se le pasan, rellena codigo, reentreno, lote,
prueba_por_otro_camino y las validaciones de la parte 2 con lo que dejaron produccion/reentrenar.py (reentreno.json),
tests/comprobar_produccion_por_otro_camino.py (prueba_por_otro_camino.json y su versión con la salida estropeada, en la
carpeta del reentreno) y el ensayo de produccion/ejecutar.py (resumen.json). Lee además el código de
produccion/ejecutar.py para comprobar que no llama a ningún paso que quita filas.

El lote (petición 28): con --lote (data/processed/prueba_final), rellena lote con el resumen del lote del candidato
(tal_como_esta/resumen.json) y prueba_por_otro_camino.lote con la prueba sobre él y su versión estropeada; con
--reentrenado, el reentreno trae la comparacion_con_el_en_uso de la ficha del reentrenado. Deja además
informes/preproduccion.md, generado del JSON (resultado.md, «El informe para la persona»).

El modelo en uso (petición 29): si produccion/configuracion.json nombra el modelo en uso con la aprobación del responsable del caso
(modelo_en_uso_aprobado_por), la pregunta P-02 pasa a decisiones como resuelta, sin borrarse, y el estado es OK; el
modelo en uso tiene que ser uno de los medidos (validación modelo_en_uso_medido). Con --lote y --reentrenado, si está
la prueba por otro camino sobre el lote del reentrenado (reentrenado/prueba_por_otro_camino.json y su versión
estropeada), entra con su validación otro_camino_lote_reentrenado.

Uso: python -W error scripts/19_contrato_produccion.py [--raiz CARPETA] [--reentreno CARPETA --ensayo CARPETA]
     [--lote CARPETA] [--reentrenado CARPETA]
  --raiz: carpeta con la estructura del caso. Por defecto, la del caso. La prueba la usa con documentos pequeños.
  --reentreno: carpeta del primer reentreno (modelos/reentrenos/AAAA-MM-DD); --ensayo: carpeta del ensayo de la
  ejecución (data/predicciones/AAAA-MM-DD). Sin las dos, la parte 2 queda vacía.
Sale con 0 si el contrato queda escrito esperando al responsable del caso (PARADO con puerta_de_juan) o con la parte 2 en AVISO, y con 1
si para antes o con ERROR.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import json
import platform
import re
import sys
import traceback
from datetime import datetime
from importlib import metadata
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
VERSION_METODO = "20/11/2026"  # versión del método preproduccion con que se escribió este script
SCRIPT_REL = "scripts/19_contrato_produccion.py"
JSON_REL = "informes/preproduccion.json"
CONTRATO_REL = "config/modelo/contrato_produccion.md"
BUSQUEDA_REL = "informes/busqueda.json"
VALIDACION_REL = "informes/validacion.json"
PREPARACION_REL = "informes/preparacion.json"
PRESELECCION_REL = "informes/preseleccion.json"
VARIABLES_REL = "informes/variables_modelo.json"
REGISTRO_REL = "config/modelo/registro-transformaciones.md"
PLANTEAMIENTOS_REL = "config/metodo/04_planteamientos.md"
PROTECCION_REL = "config/fuentes/proteccion-datos.json"
ASIGNACION_REL = "informes/modelado_asignacion.json"
# La parte 2: el código que deja la petición 27 y lo que lee de sus ejecuciones
CODIGO_PARTE_2 = {"modulo": "scripts/produccion_prevision.py", "reentrenar": "produccion/reentrenar.py",
                  "ejecutar": "produccion/ejecutar.py", "prueba": "tests/comprobar_produccion_por_otro_camino.py",
                  "configuracion": "produccion/configuracion.json"}
REENTRENO_JSON = "reentreno.json"
PRUEBA_JSON = "prueba_por_otro_camino.json"
PRUEBA_ESTROPEADA_JSON = "prueba_por_otro_camino_estropeada.json"
ENSAYO_JSON = "resumen.json"
# El lote de la prueba final (petición 28): el del candidato, tal como está, y la prueba por otro camino sobre él
LOTE_VARIANTE = "tal_como_esta"
# El lote del reentrenado, con su prueba por otro camino (petición 29)
LOTE_REENTRENADO = "reentrenado"
MD_REL = "informes/preproduccion.md"
# La ficha del contrato aprobado en el registro y la frase con la aprobación del responsable del caso
TITULO_APROBACION = "contrato de producción aprobado"
PATRON_APROBACION = re.compile(r"[Ee]l responsable del caso, (\d{2})/(\d{2})/(\d{4}): («[^»]+»)")
# Piezas que ya existen en disco y que la parte 2 tiene que revisar contra el contrato antes de escribir nada
PIEZAS_EXISTENTES = ["scripts/variables_prevision.py", "scripts/preparacion_prevision.py",
                     "scripts/prevision_recursiva.py"]

OBJETIVOS = ("unidades", "dolares")
NOMBRE = {"unidades": "Unidades", "dolares": "Dólares"}
# La clave de una fila de la tabla de series: departamento, tienda y día (registro R-004, «la clave sin repetir»)
IDENTIFICADOR = ["store_id", "dept_id", "date"]
CLASES = ("quita filas", "no aprende", "necesita otras filas", "aprende")
# Orden de las etapas del hilo (método, apartado 1.2): lo de antes de la partición no puede aprender
ETAPAS = ("origen", "correccion", "integracion", "transformacion", "particion", "variables", "filas",
          "preprocesador", "seleccion", "modelo")
ETAPAS_OBLIGATORIAS = ("particion", "preprocesador", "seleccion", "modelo")

# Dónde va cada clase (método, apartado 1.3), con el caso de la previsión recursiva en la tercera
DONDE_VA = {
    "quita filas": "solo en el reentreno, antes del Pipeline y contado; nunca en la ejecución diaria",
    "no aprende": ("en el módulo .py como función, dentro del Pipeline con FunctionTransformer o antes con pandas, "
                   "igual al reentrenar que al ejecutar"),
    "necesita otras filas": ("con las filas anteriores a cada día, nunca con las posteriores ni con el propio día: al "
                             "reentrenar, con la propia tabla de entrenamiento; al prever, con la tabla de historia que "
                             "ya lleva lo previsto (previsión recursiva, reglas, apartado 5)"),
    "aprende": "dentro del Pipeline, con fit en el entrenamiento",
}

# El catálogo de pasos, leído del registro de transformaciones. `cita` es una frase literal de la ficha: si el registro
# deja de decirla, la cadena no está completa. `esperado` es la clase que daba la petición 26 (tarea 3); None si el
# petición no nombraba el paso.
SIN_FICHA_MODELO = "sin ficha en el registro"
PASOS = {
    "recorte": {"ficha": "T-001", "etapa": "origen", "clase": "no aprende", "esperado": None,
                "paso": "las series suman los 500 productos del recorte de M5 en las 10 tiendas",
                "cita": "500 productos al azar"},
    "fecha": {"ficha": "R-001", "etapa": "correccion", "clase": "no aprende", "esperado": "no aprende",
              "paso": "la fecha del calendario se lee como fecha con el formato año-mes-día",
              "cita": "se lee con el formato explícito"},
    "snap_nombres": {"ficha": "R-002", "etapa": "correccion", "clase": "no aprende", "esperado": "no aprende",
                     "paso": "las columnas SNAP de cada estado pasan a minúsculas",
                     "cita": "`snap_CA` pasa a `snap_ca`"},
    "semana_anterior": {"ficha": "T-003", "etapa": "integracion", "clase": "no aprende", "esperado": "no aprende",
                        "paso": "el Calendario añade a cada día su semana anterior, por el orden de las fechas",
                        "cita": "más la semana anterior por el orden de las fechas"},
    "dim_producto": {"ficha": "R-007", "etapa": "integracion", "clase": "no aprende", "esperado": None,
                     "paso": "una fila por producto con su departamento",
                     "cita": "una fila por producto con su departamento y su categoría"},
    "dim_tienda": {"ficha": "R-008", "etapa": "integracion", "clase": "no aprende", "esperado": None,
                   "paso": "una fila por tienda con su estado", "cita": "una fila por tienda con su estado"},
    "series": {"ficha": "R-004", "etapa": "integracion", "clase": "no aprende", "esperado": None,
               "paso": ("la venta de cada producto se une con el calendario, el precio, el producto y la tienda; se suma "
                        "por departamento, tienda y día en unidades y en céntimos; snap es el del estado de la tienda"),
               "cita": "se suma por serie y día en céntimos enteros"},
    "precio_medio": {"ficha": "R-009", "etapa": "transformacion", "clase": "necesita otras filas",
                     "esperado": "necesita otras filas",
                     "paso": ("media simple del precio de la semana anterior de los productos del departamento que ya "
                              "tenían precio cuatro semanas antes"),
                     "cita": "que ya lo tenían cuatro semanas antes"},
    "particion": {"ficha": "R-010", "etapa": "particion", "clase": "quita filas", "esperado": None,
                  "paso": ("el entrenamiento son las filas de la construcción, hasta el {fin_entrenamiento}; al "
                           "reentrenar, la tabla que se pasa marca el corte"),
                  "cita": "partición por fecha"},
    "retardos_unidades": {"ficha": "R-012", "etapa": "variables", "clase": "necesita otras filas",
                          "esperado": "necesita otras filas",
                          "paso": "retardos de 1 a 7, 14, 21 y 28 días y medias de 7 y 28 días de las unidades de la serie",
                          "cita": "comprobar_sin_huecos(historia)"},
    "retardos_dolares": {"ficha": "R-013", "etapa": "variables", "clase": "necesita otras filas",
                         "esperado": "necesita otras filas",
                         "paso": "retardos de 1 a 7, 14, 21 y 28 días y medias de 7 y 28 días de los dólares de la serie",
                         "cita": "comprobar_sin_huecos(historia)"},
    "productos": {"ficha": "R-014", "etapa": "variables", "clase": "necesita otras filas",
                  "esperado": "necesita otras filas",
                  "paso": ("cuántos productos del departamento tenían precio la semana anterior y ya lo tenían cuatro "
                           "semanas antes"),
                  "cita": ("cuentan los productos del departamento con precio en la tienda la semana anterior que ya "
                           "tenían precio cuatro semanas antes")},
    "eventos_lista": {"ficha": "R-015", "etapa": "variables", "clase": "aprende", "esperado": "no aprende",
                      "paso": "la lista de eventos se saca de los días de entrenamiento",
                      "cita": "La lista de eventos sale solo del entrenamiento"},
    "eventos_columnas": {"ficha": "R-015", "etapa": "variables", "clase": "no aprende", "esperado": "no aprende",
                         "paso": ("una columna de 0 y 1 por evento de la lista, a 1 si el día lo trae en event_name_1 o "
                                  "en event_name_2"),
                         "cita": "una columna `evento_<nombre>` por evento"},
    "dia_del_mes": {"ficha": "R-016", "etapa": "variables", "clase": "no aprende", "esperado": "no aprende",
                    "paso": "el día del mes, de 1 a 31, sacado de la fecha",
                    "cita": 'df["dia_del_mes"] = df["date"].dt.day'},
    "primeros_dias": {"ficha": "R-017", "etapa": "filas", "clase": "quita filas", "esperado": "quita filas",
                      "paso": "salen del entrenamiento los primeros 35 días de cada serie, que no tienen la historia que "
                              "piden las variables",
                      "cita": "salen 35 días, no 29"},
    "seleccion": {"ficha": "R-018", "etapa": "seleccion", "clase": "no aprende", "esperado": None,
                  "paso": ("el modelo toma por su nombre las columnas del ganador; las de event_name_1 y event_name_2 "
                           "no entran (reglas, apartado 7)"),
                  "cita": "preselección de variables: listas de columnas y escenario"},
    # Desde el 25/11/2026 el modelo tiene su ficha en el registro, la R-020
    "modelo": {"ficha": "R-020", "etapa": "modelo", "clase": "aprende", "esperado": "aprende",
               "paso": "el ganador se ajusta con las filas del entrenamiento, con la receta fija",
               "cita": "el modelo ganador de cada objetivo"},
}
# La ficha del preprocesador es la de la matriz aprobada; cada finalista tiene su rama, leída de preparacion.json
CITA_PREPROCESADOR = "El responsable del caso aprobó la matriz el 24/11/2026"
FICHA_PREPROCESADOR = "R-011"

# La ficha que crea cada finalista y la frase que lo dice. Los retardos y las medias los crea la ficha de su objetivo.
CITAS_DE_CREACION = {
    "store_id": ("R-004", "`store_id`"),
    "dept_id": ("R-004", "`dept_id`"),
    "weekday": ("R-004", "las columnas del Calendario"),
    "month": ("R-004", "las columnas del Calendario"),
    "snap": ("R-004", "snap = snap_ca, snap_tx o snap_wi según state_id"),
    "evento_<nombre>": ("R-015", "una columna `evento_<nombre>` por evento"),
    "precio_medio_semana_anterior": ("R-009", "`precio_medio_semana_anterior` (nueva)"),
    "productos_con_precio_semana_anterior": ("R-014", "(nueva): `productos_con_precio_semana_anterior`"),
    "dia_del_mes": ("R-016", "(nueva): `dia_del_mes`"),
}
# El hilo de cada finalista hasta la partición incluida y lo que viene después, antes del preprocesador.
# Las claves con <obj> valen para los dos objetivos.
HILO = {
    "store_id": ["recorte", "series", "particion", "primeros_dias"],
    "dept_id": ["recorte", "dim_producto", "series", "particion", "primeros_dias"],
    "weekday": ["semana_anterior", "series", "particion", "primeros_dias"],
    "month": ["semana_anterior", "series", "particion", "primeros_dias"],
    "snap": ["snap_nombres", "dim_tienda", "series", "particion", "primeros_dias"],
    "evento_<nombre>": ["semana_anterior", "series", "particion", "eventos_lista", "eventos_columnas",
                        "primeros_dias"],
    "precio_medio_semana_anterior": ["recorte", "fecha", "semana_anterior", "dim_producto", "series", "precio_medio",
                                     "particion", "primeros_dias"],
    "productos_con_precio_semana_anterior": ["recorte", "fecha", "semana_anterior", "dim_producto", "series",
                                             "particion", "productos", "primeros_dias"],
    "dia_del_mes": ["fecha", "series", "particion", "dia_del_mes", "primeros_dias"],
    "<obj>_retardo": ["recorte", "fecha", "dim_producto", "series", "particion", "retardos_<obj>", "primeros_dias"],
}
PATRON_RETARDO = re.compile(r"^(unidades|dolares)_(lag|media)_\d+$")


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_json(ruta):
    """Un JSON en UTF-8 (error 21)."""
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def version_metodo(raiz=None):
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def version(paquete):
    """La versión instalada de un paquete, sin importarlo."""
    try:
        return metadata.version(paquete)
    except metadata.PackageNotFoundError:
        return None


def parametro(variables, nombre):
    """El valor de un parámetro de informes/variables_modelo.json, o None si no está."""
    return next((p.get("valor") for p in variables.get("parametros", []) if p.get("nombre") == nombre), None)


def miles(n):
    """Un entero con el punto de los miles, como se escribe en los documentos del caso."""
    return f"{n:,}".replace(",", ".")


# ══ 3. El registro y las finalistas ═════════════════════════════════════════════
def leer_registro(texto):
    """Las fichas del registro: {id: texto}. Las R-xxx van de su encabezado al siguiente; las T-xxx, en su fila."""
    fichas = {}
    actual = None
    for linea in texto.splitlines():
        cabecera = re.match(r"^###\s+(R-\d{3})\b", linea)
        fila = re.match(r"^\|\s*(T-\d{3})\s*\|", linea)
        if cabecera:
            actual = cabecera.group(1)
            fichas[actual] = linea + "\n"
        elif fila:
            fichas[fila.group(1)] = linea
            actual = None
        elif linea.startswith("## "):
            actual = None
        elif actual:
            fichas[actual] += linea + "\n"
    return fichas


def patron_de_salida(salida, objetivo):
    """Una salida de la matriz como expresión: <obj> es el objetivo; cualquier otro <...> es una o más letras."""
    partes = re.split(r"(<[^>]+>)", salida.replace("<obj>", objetivo))
    return re.compile("^" + "".join(".+" if p.startswith("<") else re.escape(p) for p in partes) + "$")


def finalistas_del_ganador(columnas, variables_matriz, objetivo):
    """De qué variable de la matriz sale cada columna del ganador; devuelve (finalistas en orden, columnas sin finalista).

    Una columna sale de la primera variable de la matriz cuya salida la describe; con una salida literal manda la
    igualdad (así `<obj>_lag_1_rs` no se confunde con `<obj>_lag_14_rs`).
    """
    por_variable = {}
    sin_finalista = []
    for columna in columnas:
        origen = None
        for v in variables_matriz:
            if not v.get("entra"):
                continue
            if any(patron_de_salida(s, objetivo).match(columna) for s in v.get("salida", [])):
                origen = v
                break
        if origen is None:
            sin_finalista.append(columna)
            continue
        nombre = origen["variable"].replace("<obj>", objetivo)
        por_variable.setdefault(nombre, {"variable_matriz": origen, "columnas": []})["columnas"].append(columna)
    orden = [v["variable"].replace("<obj>", objetivo) for v in variables_matriz]
    finalistas = [(n, por_variable[n]) for n in orden if n in por_variable]
    return finalistas, sin_finalista


def paso_del_preprocesador(variable, v_matriz):
    """El paso del preprocesador de una finalista, con su clase sacada de su rama y su escalado en la matriz."""
    rama, escalado = v_matriz.get("rama") or "", v_matriz.get("escalado") or ""
    if "una columna por categoría" in rama:
        clase, texto = "aprende", f"OneHotEncoder aprende las categorías de {variable} en el entrenamiento"
    elif escalado and escalado != "ninguno":
        clase, texto = "aprende", f"{escalado} aprende la escala de {variable} en el entrenamiento"
    else:
        clase, texto = "no aprende", f"{variable} pasa tal cual"
    return {"clave": f"preprocesador_{clase.replace(' ', '_')}", "ficha": FICHA_PREPROCESADOR,
            "etapa": "preprocesador", "clase": clase, "esperado": None, "paso": texto, "cita": CITA_PREPROCESADOR,
            "fuente": "config/modelo/matriz_transformaciones.md; informes/preparacion.json"}


def construir_cadena(variable, generica, objetivo, v_matriz, fin_entrenamiento="sin fecha"):
    """La cadena de una finalista: su hilo del catálogo, el preprocesador, la selección y el modelo; None si no hay hilo.

    fin_entrenamiento: el último día del entrenamiento, leído de informes/variables_modelo.json (error 16).
    """
    clave_hilo = "<obj>_retardo" if PATRON_RETARDO.match(variable) else generica
    if clave_hilo not in HILO:
        return None
    pasos = []
    for clave in HILO[clave_hilo] + ["preprocesador", "seleccion", "modelo"]:
        if clave == "preprocesador":
            pasos.append(paso_del_preprocesador(variable, v_matriz))
            continue
        clave = clave.replace("<obj>", objetivo)
        paso = {"clave": clave, **PASOS[clave]}
        paso["paso"] = paso["paso"].replace("{fin_entrenamiento}", fin_entrenamiento)
        pasos.append(paso)
    return pasos


def creacion(variable, objetivo):
    """La ficha que crea una finalista y la frase que tiene que traer."""
    if PATRON_RETARDO.match(variable):
        # Las fichas R-012 y R-013 nombran los retardos de 1 a 7 como un tramo; los demás, uno a uno
        k = int(variable.rsplit("_", 1)[1])
        if "_lag_" in variable and 1 <= k <= 7:
            return PASOS[f"retardos_{objetivo}"]["ficha"], f"`{objetivo}_lag_1` a `{objetivo}_lag_7`"
        return PASOS[f"retardos_{objetivo}"]["ficha"], variable
    return CITAS_DE_CREACION.get(variable.replace(objetivo, "<obj>"), CITAS_DE_CREACION.get(variable, (None, None)))


# ══ 4. Las validaciones de la parte 1 ═══════════════════════════════════════════
def huecos_de_cadena(cadenas, registro, objetivo):
    """Las finalistas sin cadena completa: sin hilo, sin una etapa obligatoria, sin su ficha de creación o con una
    ficha que el registro no tiene o que ya no dice lo que se cita."""
    huecos = []
    for variable, cadena in cadenas.items():
        if cadena is None:
            huecos.append({"variable": variable, "motivo": "no tiene hilo en el catálogo del contrato"})
            continue
        etapas = {p["etapa"] for p in cadena}
        for etapa in ETAPAS_OBLIGATORIAS:
            if etapa not in etapas:
                huecos.append({"variable": variable, "motivo": f"le falta la etapa {etapa}"})
        for p in cadena:
            if not re.match(r"^[RT]-\d{3}$", p["ficha"]):
                continue
            if p["ficha"] not in registro:
                huecos.append({"variable": variable, "motivo": f"el registro no tiene la ficha {p['ficha']}"})
            elif p["cita"] not in registro[p["ficha"]]:
                huecos.append({"variable": variable, "motivo": f"{p['ficha']} no dice «{p['cita']}»"})
        ficha, cita = creacion(variable, objetivo)
        if ficha is None:
            huecos.append({"variable": variable, "motivo": "no tiene ficha de creación"})
        elif ficha not in registro or cita not in registro[ficha]:
            huecos.append({"variable": variable, "motivo": f"la ficha que la crea, {ficha}, no dice «{cita}»"})
    return huecos


def aprende_antes_de_la_particion(cadenas):
    """Los pasos que aprenden y van antes de la partición en su cadena (método, apartado 1.4)."""
    malos = []
    for variable, cadena in cadenas.items():
        if not cadena:
            continue
        posiciones = [i for i, p in enumerate(cadena) if p["etapa"] == "particion"]
        corte = posiciones[0] if posiciones else len(cadena)
        malos += [{"variable": variable, "paso": p.get("clave"), "ficha": p["ficha"]}
                  for p in cadena[:corte] if p["clase"] == "aprende"]
    return malos


def campos_vacios(obj, ruta=""):
    """Las rutas de los campos vacíos: None, texto vacío, lista vacía o diccionario vacío. El cero y False no lo son."""
    if obj is None or (isinstance(obj, (str, list, dict)) and len(obj) == 0):
        return [ruta]
    vacios = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            vacios += campos_vacios(v, f"{ruta}.{k}" if ruta else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            vacios += campos_vacios(v, f"{ruta}[{i}]")
    return vacios


def distinto_de_lo_esperado(objetivos):
    """Los pasos de las cadenas cuya clase no es la que daba la petición, y los que no nombraba y no son «no aprende»."""
    vistos = {}
    for o in objetivos.values():
        for f in o["finalistas"]:
            for p in f["cadena"]:
                clave = p["clave"]
                if clave in vistos:
                    vistos[clave]["finalistas"].add(f["variable"])
                    continue
                if p["esperado"] is not None and p["esperado"] != p["clase"]:
                    tipo = f"la petición esperaba «{p['esperado']}»"
                elif p["esperado"] is None and p["clase"] != "no aprende":
                    tipo = "la petición no lo nombraba"
                else:
                    continue
                vistos[clave] = {"paso": clave, "ficha": p["ficha"], "clase": p["clase"], "tipo": tipo,
                                 "texto": p["paso"], "finalistas": {f["variable"]}}
    return [{**v, "finalistas": sorted(v["finalistas"])} for v in vistos.values()]


# ══ 5. El contrato por objetivo ═════════════════════════════════════════════════
def contrato_objetivo(objetivo, ganador, matriz, registro, validacion, variables, preparacion):
    """Finalistas, cadenas, receta y previsión de un objetivo; devuelve (contrato, detalle de las validaciones)."""
    finalistas, sin_finalista = finalistas_del_ganador(ganador.get("columnas", []), matriz, objetivo)
    hasta = ((variables.get("particion") or {}).get("desarrollo") or {}).get("hasta")
    fin = datetime.strptime(hasta, "%Y-%m-%d").strftime("%d/%m/%Y") if hasta else "sin fecha en variables_modelo.json"
    cadenas = {n: construir_cadena(n, info["variable_matriz"]["variable"], objetivo, info["variable_matriz"], fin)
               for n, info in finalistas}
    huecos = huecos_de_cadena(cadenas, registro, objetivo)
    antes = aprende_antes_de_la_particion(cadenas)

    # Los pasos que aprenden se ajustaron con las filas del entrenamiento: las que quedan tras quitar los 35 días
    filas_ent = (variables.get("filas_quitadas") or {}).get("filas_despues")
    filas_pre = ((preparacion.get("preprocesadores") or {}).get(objetivo) or {}).get("ajustado_con_filas")
    filas_mod = (ganador.get("reajuste") or {}).get("filas_ajuste")
    ajustes = {"filas_entrenamiento": filas_ent, "preprocesador": filas_pre, "modelo": filas_mod}
    if filas_ent is None or filas_pre != filas_ent or filas_mod != filas_ent:
        antes.append({"variable": "todas", "paso": "preprocesador y modelo",
                      "ficha": f"{PREPARACION_REL}; {BUSQUEDA_REL}",
                      "motivo": f"ajustados con {filas_pre} y {filas_mod} filas; el entrenamiento tiene {filas_ent}"})

    horizonte = ((validacion.get("validacion") or {}).get(objetivo) or {}).get("horizonte")
    retardos, ventanas = parametro(variables, "retardos") or [], parametro(variables, "ventanas de las medias") or []
    historia = max(retardos + ventanas) if retardos + ventanas else None
    semanas_precio = parametro(variables, "semanas_previas_con_precio")
    contrato = {
        "objetivo": objetivo,
        "finalistas": [{"variable": n, "columnas_del_modelo": info["columnas"],
                        "cadena": [{k: p[k] for k in ("clave", "ficha", "etapa", "clase", "esperado", "paso")}
                                   | {"donde_va": DONDE_VA.get(p["clase"])}
                                   for p in (cadenas[n] or [])]}
                       for n, info in finalistas],
        "receta": {"algoritmo": ganador.get("algoritmo"), "clase": ganador.get("clase"),
                   "hiperparametros": ganador.get("hiperparametros"), "buscados": ganador.get("buscados"),
                   "semilla": ganador.get("semilla"), "columnas": ganador.get("columnas"),
                   "n_columnas": len(ganador.get("columnas", [])), "filas_ajuste": filas_mod,
                   "corte": {"como": "sin corte", "valores": ["no aplica: se prevé una cantidad"], "grupo": "no aplica"},
                   "fuente": BUSQUEDA_REL,
                   "aprobado_por": ((validacion.get("receta") or {}).get("ganador") or {}).get(objetivo, {})
                   .get("aprobado_por")},
        "prevision": {
            "horizonte_dias": horizonte,
            "historia_minima_dias": historia,
            "historia_minima": (f"la venta en {objetivo} de cada serie en los {historia} días que acaban en el origen: "
                                f"el retardo y la media más largos piden {historia} días antes del primer día previsto"),
            "historia_de_precios": (f"los precios de cada producto desde {semanas_precio} semanas antes de la semana "
                                    "anterior al primer día previsto hasta la semana anterior al último; con menos, un "
                                    "producto que ya se vendía contaría como nuevo (reglas, apartado 5, «El precio»)"),
            "calendario": ("los días a prever con su día de la semana, mes, fecha, eventos, días SNAP de cada estado y "
                           "semana de Walmart, más la semana anterior a la del primer día"),
            "objetivo_a_prever": "vacío, nunca cero: un cero de relleno no se distingue de una venta de cero",
            "como_se_preve": (f"día a día, desde el día siguiente al origen hasta el día {horizonte}; los retardos y las "
                              "medias de cada día se calculan con la tabla de historia que ya lleva lo previsto"),
            "union": ("cada previsión se escribe en la historia uniendo por store_id, dept_id y fecha, nunca por "
                      "posición; se comprueba que ningún día a prever queda sin previsión"),
            "acotar": "en cero, antes de escribir la previsión en la historia (reglas, apartado 6)",
            "redondeo": ("al entero, con la mitad hacia arriba, solo al medir y en la salida; la historia guarda lo "
                         "previsto sin redondear" if objetivo == "unidades" else
                         "ninguno: los dólares no se redondean"),
            "modelos": "uno para las 70 combinaciones de departamento y tienda, no uno por serie (planteamientos §2, "
                       "decisión 6)",
            "navidad": ("entra en la historia con lo previsto, como cualquier día (matriz); al "
                        "reentrenar entra en el ajuste"),
            "sin_historia": (f"una serie sin {historia} días de historia sale con la previsión vacía y su motivo; no se "
                             "quita"),
            "columna_de_prevision": f"con un nombre distinto de «{objetivo}»",
            "fuentes": ("reglas, apartado 5 («El horizonte», «El precio», «Lo que se sabe el día de prever») y §6; matriz, "
                        "«Cómo se calculan en la previsión recursiva»; informes/validacion.json; "
                        "scripts/prevision_recursiva.py (prever_recursivo y redondear_unidades), leído para el redondeo"),
        },
    }
    detalle = {"sin_finalista": sin_finalista, "huecos": huecos, "aprende_antes": antes, "ajustes": ajustes}
    return contrato, detalle


# ══ 5b. La aprobación y la parte 2 ══════════════════════════════════════════════
def aprobacion_del_contrato(registro):
    """La aprobación del responsable del caso, leída de la ficha del contrato aprobado del registro; None si no está.

    Devuelve aprobado_por, fecha en ISO, el texto de la aprobación, el estado tal como lo dicen el contrato y el JSON
    y la ficha.
    """
    for ficha, texto in registro.items():
        cabecera = texto.splitlines()[0] if texto else ""
        if not ficha.startswith("R-") or TITULO_APROBACION not in cabecera:
            continue
        m = PATRON_APROBACION.search(texto)
        if not m:
            continue
        dia, mes, anio, palabras = m.groups()
        return {"aprobado_por": "el responsable del caso", "fecha": f"{anio}-{mes}-{dia}", "palabras": palabras,
                "ficha": ficha, "estado": f"aprobado por el responsable del caso el {dia}/{mes}/{anio}, {palabras}"}
    return None


def parte_2(raiz, dir_reentreno, dir_ensayo, dir_lote=None, dir_reentrenado=None):
    """Lo que la parte 2 deja en el JSON, leído de lo que dejaron sus ejecuciones; devuelve (campos, validaciones,
    faltan).

    Cada validación se calcula con lo leído (error 24): el reentreno da las columnas del contrato, el bit a bit y si
    cambia con datos nuevos; la prueba por otro camino coincide y sale en rojo con la salida estropeada; el ensayo da
    las filas, la ficha, el periodo y la previsión completa; el código de produccion/ejecutar.py no llama a ningún
    paso que quita filas.
    """
    rutas = {"reentreno": dir_reentreno / REENTRENO_JSON, "prueba": dir_reentreno / PRUEBA_JSON,
             "estropeada": dir_reentreno / PRUEBA_ESTROPEADA_JSON, "ensayo": dir_ensayo / ENSAYO_JSON,
             "ejecutar": raiz / CODIGO_PARTE_2["ejecutar"]}
    if dir_lote is not None:
        rutas |= {"lote": dir_lote / LOTE_VARIANTE / ENSAYO_JSON, "prueba_lote": dir_lote / PRUEBA_JSON,
                  "estropeada_lote": dir_lote / PRUEBA_ESTROPEADA_JSON}
    if dir_reentrenado is not None:
        rutas["reentrenado"] = dir_reentrenado / REENTRENO_JSON
    faltan = [str(r) for r in rutas.values() if not r.exists()]
    if faltan:
        return None, None, faltan
    re_, prueba = leer_json(rutas["reentreno"]), leer_json(rutas["prueba"])
    estropeada, ensayo = leer_json(rutas["estropeada"]), leer_json(rutas["ensayo"])
    codigo_ejecutar = rutas["ejecutar"].read_text(encoding="utf-8")
    llamadas = [p for p in re_.get("pasos_que_quitan_filas", []) if re.search(rf"\b{re.escape(p)}\s*\(", codigo_ejecutar)]
    val_re, val_en = re_.get("validaciones") or {}, ensayo.get("validaciones") or {}
    comprobacion = re_.get("comprobacion") or {}

    def relativa(ruta):
        """La ruta desde la carpeta del caso, si cuelga de ella."""
        try:
            return Path(ruta).resolve().relative_to(raiz.resolve()).as_posix()
        except ValueError:
            return str(ruta)

    campos = {
        "codigo": dict(CODIGO_PARTE_2),
        "reentreno": {"tabla": (re_.get("tabla") or {}).get("ruta"), "huella_tabla": (re_.get("tabla") or {}).get("sha256"),
                      "fecha_corte": (re_.get("tabla") or {}).get("fecha_corte"),
                      "filas_entrada": re_.get("filas_entrada"), "filas_quitadas": re_.get("filas_quitadas"),
                      "filas_ajuste": re_.get("filas_ajuste"), "modelo_en_uso": re_.get("modelo_en_uso"),
                      "igual_bit_a_bit": val_re.get("bit_a_bit"), "ruta": relativa(dir_reentreno),
                      "primer_reentreno": {"origenes": comprobacion.get("origenes"),
                                           "tolerancia": comprobacion.get("tolerancia"),
                                           "por_objetivo": comprobacion.get("por_objetivo"),
                                           "referencia": comprobacion.get("referencia")},
                      "cambia_con_datos_nuevos": re_.get("cambia_con_datos_nuevos"),
                      "ramas_event_name": re_.get("ramas_event_name"),
                      "comparacion_con_el_en_uso": re_.get("comparacion_con_el_en_uso")},
        "lote": {"ruta": None, "filas_entrada": None, "filas_salida": None, "sin_puntuar": None,
                 "historial": {"ruta": None, "filas": None},
                 "estado": "pendiente: la petición 28 ejecuta el lote con el año guardado"},
        "prueba_por_otro_camino": {"coincide": prueba.get("coincide"), "tolerancia": prueba.get("tolerancia"),
                                   "rojo_con_estropeada": estropeada.get("coincide") is False,
                                   "sobre": f"los {prueba.get('origenes')} orígenes de la validación",
                                   "por_objetivo": prueba.get("por_objetivo"),
                                   "lote": "pendiente de la petición 28"},
        "ensayo_ejecucion": {"ruta": relativa(dir_ensayo), "origen": ensayo.get("origen"), "ensayo": ensayo.get("ensayo"),
                             "filas": ensayo.get("filas"), "modelo": ensayo.get("modelo")},
    }
    validaciones = {
        "columnas_del_contrato": val_re.get("columnas_del_contrato") is True,
        "filas_ejecucion": val_en.get("filas_ejecucion") is True,
        "bit_a_bit": val_re.get("bit_a_bit") is True,
        "otro_camino": prueba.get("coincide") is True and estropeada.get("coincide") is False,
        "sin_quitar_filas_al_ejecutar": not llamadas and bool(re_.get("pasos_que_quitan_filas")),
        "ficha_cuadra": val_en.get("ficha_cuadra") is True,
        "cambia_con_datos_nuevos": val_re.get("cambia_con_datos_nuevos") is True,
        "periodo_que_toca": val_en.get("periodo_que_toca") is True,
        "prevision_completa": val_en.get("sin_vacias_sin_motivo") is True and val_en.get("sin_negativas") is True,
    }
    campos["detalle_parte_2"] = {"llamadas_que_quitan_filas_en_ejecutar": llamadas}

    # El lote de la prueba final y la prueba por otro camino sobre él (petición 28; método, apartado 2.4)
    if dir_lote is not None:
        lote, prueba_l = leer_json(rutas["lote"]), leer_json(rutas["prueba_lote"])
        estropeada_l = leer_json(rutas["estropeada_lote"])
        entrada = lote.get("filas_entrada") or {}
        campos["lote"] = {
            "ruta": relativa(dir_lote / LOTE_VARIANTE), "modelos": lote.get("modelos"),
            "filas_entrada": entrada.get("filas_a_prever"), "filas_salida": lote.get("filas_salida"),
            "ejecuciones": entrada.get("ejecuciones"), "origenes": len(lote.get("origenes") or []),
            "sin_puntuar": [{"motivo": k, "filas": v} for k, v in (lote.get("sin_prevision") or {}).items()],
            "historial": {"ruta": ("data/raw/sales_train_evaluation.csv y data/raw/reserva/sales_train_evaluation.csv, "
                                   "cortadas en cada origen"),
                          "filas": entrada.get("venta_productos_tienda_por_origen")},
            "estado": "hecho en la petición 28: el año guardado, con el candidato"}
        campos["prueba_por_otro_camino"]["lote"] = {
            "ruta": relativa(rutas["prueba_lote"]), "coincide": prueba_l.get("coincide"),
            "rojo_con_estropeada": estropeada_l.get("coincide") is False, "tolerancia": prueba_l.get("tolerancia"),
            "origenes": prueba_l.get("origenes"), "por_objetivo": prueba_l.get("por_objetivo")}
        validaciones["otro_camino_lote"] = prueba_l.get("coincide") is True and estropeada_l.get("coincide") is False
        validaciones["filas_lote"] = (entrada.get("filas_a_prever") is not None
                                      and lote.get("filas_salida") == entrada.get("filas_a_prever"))
    # El reentrenado con un año más: su comparación con el candidato, de su ficha
    if dir_reentrenado is not None:
        ficha = leer_json(rutas["reentrenado"])
        campos["reentreno"]["comparacion_con_el_en_uso"] = ficha.get("comparacion_con_el_en_uso")
        campos["reentreno"]["reentrenado"] = {"ruta": relativa(dir_reentrenado),
                                              "filas_ajuste": ficha.get("filas_ajuste"),
                                              "fecha_datos": ficha.get("fecha_datos")}
    # La prueba por otro camino sobre el lote del reentrenado (petición 29), si está: con su versión estropeada
    if dir_lote is not None and dir_reentrenado is not None:
        prueba_r = dir_lote / LOTE_REENTRENADO / PRUEBA_JSON
        estropeada_r = dir_lote / LOTE_REENTRENADO / PRUEBA_ESTROPEADA_JSON
        if prueba_r.exists() and estropeada_r.exists():
            p, e = leer_json(prueba_r), leer_json(estropeada_r)
            campos["prueba_por_otro_camino"]["lote_reentrenado"] = {
                "ruta": relativa(prueba_r), "coincide": p.get("coincide"),
                "rojo_con_estropeada": e.get("coincide") is False, "tolerancia": p.get("tolerancia"),
                "origenes": p.get("origenes"), "por_objetivo": p.get("por_objetivo")}
            validaciones["otro_camino_lote_reentrenado"] = p.get("coincide") is True and e.get("coincide") is False
    return campos, validaciones, []


def modelo_en_uso_aprobado(raiz):
    """El modelo en uso de produccion/configuracion.json y quién lo aprobó; None si no hay o si no está aprobado.

    Lo decide el responsable del caso (R-022): sin su aprobación escrita en la configuración, la pregunta P-02 sigue pendiente.
    """
    ruta = raiz / CODIGO_PARTE_2["configuracion"]
    if not ruta.exists():
        return None
    configuracion = leer_json(ruta)
    carpeta, aprobado = configuracion.get("modelo_en_uso"), configuracion.get("modelo_en_uso_aprobado_por")
    if not carpeta or not aprobado:
        return None
    return {"carpeta": Path(carpeta).as_posix(), "aprobado_por": aprobado, "fuente": CODIGO_PARTE_2["configuracion"]}


# ══ 6. El texto del contrato ════════════════════════════════════════════════════
def texto_contrato(r):
    """El contrato para el responsable del caso, generado del mismo diccionario que el JSON (resultado.md, regla 1)."""
    obj = r["objetivos"]
    u, d = obj["unidades"], obj["dolares"]
    fecha = r["fecha_ejecucion"][:10]
    n_fin = {o: len(obj[o]["finalistas"]) for o in obj}
    n_col = {o: obj[o]["receta"]["n_columnas"] for o in obj}
    distintos = r["distinto_de_lo_esperado"]
    aprobado = r["contrato"].get("estado")
    estado = aprobado if aprobado else (f"propuesto el {fecha}, pendiente de la aprobación del responsable del caso; sin ella no se "
                                        "escribe código de producción")
    lineas = ["---",
              "titulo: Contrato de producción del caso 69 · cómo se construye cada columna de los dos modelos de "
              "previsión",
              f"estado: {estado}",
              f"fecha_documento: {fecha}",
              "dueno: el responsable del caso (decide) · el equipo de análisis (propone)",
              f"fuentes: `{BUSQUEDA_REL}`, `{VALIDACION_REL}`, `{PREPARACION_REL}`, `{PRESELECCION_REL}`, "
              f"`{VARIABLES_REL}`, `registro-transformaciones.md`, `matriz_transformaciones.md`, "
              "`../metodo/04_planteamientos.md` §2 y `../negocio/reglas-negocio.md` §5 a §7",
              f"generado_por: `{SCRIPT_REL}`; no se edita a mano",
              "---", "",
              "# Contrato de producción · caso 69", ""]

    # ── Lo que se pide aprobar (o lo que se aprobó) ──
    lineas += ["## Lo que aprobó el responsable del caso" if aprobado else "## Lo que se pide aprobar", "",
               f"Los dos modelos que la validación dio por buenos son {u['receta']['algoritmo']} en unidades y "
               f"{d['receta']['algoritmo']} en dólares. El de unidades usa {n_col['unidades']} columnas, que salen de "
               f"{n_fin['unidades']} finalistas; el de dólares, {n_col['dolares']} columnas de {n_fin['dolares']} "
               "finalistas. Cada finalista tiene su cadena completa en el registro de transformaciones y cada paso de "
               "la cadena tiene una de las cuatro clases.",
               "",
               "Con este contrato aprobado se escriben el Pipeline, el reentreno y la ejecución diaria. "
               + ("El responsable del caso aprobó estas tres cosas:" if aprobado else "El responsable del caso aprueba o cambia tres cosas:"), "",
               "- las cadenas y la clase de cada paso;",
               f"- los {len(distintos)} pasos en que el registro dice algo distinto de lo que esperaba la petición;",
               "- lo que el registro no recoge, que va en «Límites».", ""]

    # ── Los dos modelos ──
    lineas += ["## Los dos modelos", "",
               f"Cada fila es una serie en un día: su identificador es {', '.join(r['identificador'])}. Cada modelo "
               "prevé las 70 combinaciones de departamento y tienda a la vez. Ninguno tiene corte, porque los dos "
               "prevén una cantidad.", ""]
    for o in OBJETIVOS:
        rec, prev = obj[o]["receta"], obj[o]["prevision"]
        buscados = ", ".join(f"{k} {'sin límite' if v is None else v}" for k, v in rec["buscados"].items())
        lineas.append(f"- **{NOMBRE[o]}.** Prevé a {prev['horizonte_dias']} días con {rec['algoritmo']} "
                      f"({buscados}; semilla {rec['semilla']}). Se ajustó con {miles(rec['filas_ajuste'])} filas. "
                      f"Lo aprobó {rec['aprobado_por']}.")
    lineas += ["", f"Los demás hiperparámetros son los de la librería, con la parada temprana apagada; la lista entera "
               f"está en `{JSON_REL}` y en `{BUSQUEDA_REL}`. El veredicto de la validación lo aprobó "
               f"{r['veredicto_aprobado']}.", ""]

    # ── Las finalistas ──
    lineas += ["## Las finalistas", "",
               "Una finalista es la variable de la que salen columnas del modelo. La tabla va del todo a la unidad: "
               "la serie, el calendario, el precio y la historia de la venta. Los retardos y las medias salen del "
               "objetivo de cada modelo, así que cambian de nombre de uno a otro.", "",
               "| Finalista | Columnas en unidades | Columnas en dólares |", "|---|---|---|"]
    cols = {o: {f["variable"].replace(o, "<obj>"): len(f["columnas_del_modelo"]) for f in obj[o]["finalistas"]}
            for o in OBJETIVOS}
    for nombre in dict.fromkeys(list(cols["unidades"]) + list(cols["dolares"])):
        lineas.append(f"| `{nombre}` | {cols['unidades'].get(nombre, 0)} | {cols['dolares'].get(nombre, 0)} |")
    lineas.append("")

    # ── Los pasos por clase ──
    lineas += ["## Los pasos por clase", "",
               "Cada paso va a un sitio según su clase. Las fichas son las del registro de transformaciones; el "
               "preprocesador sigue la matriz aprobada (R-011) y el modelo, la R-020.", ""]
    pasos = {}
    for o in OBJETIVOS:
        for f in obj[o]["finalistas"]:
            for p in f["cadena"]:
                clave = p["clave"].replace(o, "<obj>")
                pasos.setdefault(clave, {"p": p, "finalistas": set()})["finalistas"].add(f["variable"].replace(o, "<obj>"))
    # Los pasos de cada clase, en el orden del hilo; las finalistas que los usan, en el orden de la tabla de arriba
    orden_finalistas = list(dict.fromkeys(list(cols["unidades"]) + list(cols["dolares"])))
    for clase in CLASES:
        de_la_clase = sorted((v for v in pasos.values() if v["p"]["clase"] == clase),
                             key=lambda v: ETAPAS.index(v["p"]["etapa"]))
        lineas += [f"### {clase.capitalize()}", "", f"Van {DONDE_VA[clase]}.", ""]
        for v in de_la_clase:
            p = v["p"]
            usan = "todas las finalistas" if len(v["finalistas"]) >= max(len(orden_finalistas), 1) else \
                ", ".join(f"`{x}`" for x in orden_finalistas if x in v["finalistas"])
            texto, ficha = p["paso"], p["ficha"]
            if p["clave"].startswith("retardos_"):
                ficha = " y ".join(PASOS[f"retardos_{o}"]["ficha"] for o in OBJETIVOS)
                texto = ("retardos de 1 a 7, 14, 21 y 28 días y medias de 7 y 28 días del objetivo de la serie, "
                         "unidades o dólares según el modelo")
            if p["etapa"] == "preprocesador":
                texto = "el preprocesador " + ("codifica o escala la finalista" if clase == "aprende"
                                               else "la deja pasar tal cual")
            if ficha == SIN_FICHA_MODELO:
                ficha = "Modelo, sin ficha"
            lineas.append(f"- {ficha} · {texto}. Lo usan: {usan}.")
        lineas.append("")

    # ── La cadena de cada finalista ──
    lineas += ["## La cadena de cada finalista", "",
               "Cada cadena va en el orden en que se aplica, del origen al modelo. Entre paréntesis, la clase de cada "
               "paso: Q quita filas, N no aprende, H necesita otras filas y A aprende. Las cadenas de dólares son "
               "iguales con la ficha R-013 en lugar de R-012.", "",
               "| Finalista | Cadena |", "|---|---|"]
    letra = {"quita filas": "Q", "no aprende": "N", "necesita otras filas": "H", "aprende": "A"}
    for f in u["finalistas"]:
        cadena = " · ".join(f"{'modelo' if p['ficha'] == SIN_FICHA_MODELO else p['ficha']} ({letra[p['clase']]})"
                            for p in f["cadena"])
        lineas.append(f"| `{f['variable'].replace('unidades', '<obj>')}` | {cadena} |")
    lineas.append("")

    # ── La previsión día a día ──
    lineas += ["## La previsión día a día", "",
               f"Las unidades se prevén a {u['prevision']['horizonte_dias']} días y los dólares a "
               f"{d['prevision']['horizonte_dias']}, siempre desde el último día con venta conocida. Cada día del "
               "horizonte se prevé con lo previsto para los anteriores.", ""]
    pu = u["prevision"]
    lineas += [f"- **Historia mínima.** Cada previsión necesita la venta de la serie en su objetivo durante los "
               f"{pu['historia_minima_dias']} días que acaban en el origen, porque el retardo y la media más largos "
               f"miran {pu['historia_minima_dias']} días atrás.",
               f"- **Precios.** Hacen falta {pu['historia_de_precios']}.",
               f"- **Calendario.** Hacen falta {pu['calendario']}.",
               f"- **Lo que se prevé.** El objetivo de los días a prever llega {pu['objetivo_a_prever']}.",
               "- **Cómo se prevé.** Se prevé día a día, desde el día siguiente al origen hasta el último del "
               "horizonte. Los retardos y las medias de cada día se calculan con la tabla de historia que ya lleva lo "
               "previsto.",
               f"- **Unión.** {pu['union'][0].upper() + pu['union'][1:]}.",
               f"- **Acotar.** La previsión se acota {pu['acotar']}.",
               f"- **Redondeo.** En unidades, {pu['redondeo']}. Los dólares no se redondean.",
               f"- **Un modelo.** Hay {pu['modelos']}.",
               f"- **El 25 de diciembre.** {pu['navidad'][0].upper() + pu['navidad'][1:]}.",
               f"- **Series sin historia.** {pu['sin_historia'][0].upper() + pu['sin_historia'][1:]}.",
               "- **Nombre de la previsión.** La columna de la previsión no se llama como el objetivo.", ""]

    # ── Lo que el registro dice distinto ──
    lineas += ["## Lo que el registro dice distinto de lo esperado", "",
               "La petición esperaba que solo aprendiera el modelo y que solo quitaran filas los primeros 35 días. El "
               "registro dice otra cosa en estos pasos. Manda el registro:", ""]
    for x in distintos:
        texto = ("el preprocesador codifica y escala las finalistas con lo que aprende del entrenamiento"
                 if x["paso"].startswith("preprocesador_") else x["texto"])
        lineas.append(f"- {x['ficha']} · {texto}: es «{x['clase']}»; {x['tipo']}.")
    lineas.append("")

    # ── Lo que ya existe ──
    lineas += ["## Lo que ya existe para la parte 2", "",
               "Estos módulos ya están en disco. La parte 2 los revisa contra este contrato antes de escribir nada "
               "nuevo:", ""]
    lineas += [f"- `{x}`;" for x in r["piezas_existentes"][:-1]] + [f"- `{r['piezas_existentes'][-1]}`."] \
        if r["piezas_existentes"] else ["- ninguno."]
    lineas.append("")

    # ── Datos personales ──
    lineas += ["## Datos personales", ""]
    if r["datos_personales"]["proteccion_datos_json"]:
        lineas.append(f"La protección de los datos está descrita en `{PROTECCION_REL}`.")
    else:
        lineas.append(f"No existe `{PROTECCION_REL}`: los datos no pasaron por la protección. Las tablas son ventas por "
                      "departamento y tienda. El contrato no usa ninguna columna sobre personas.")
    lineas.append("")

    # ── Límites ──
    ramas = (r.get("reentreno") or {}).get("ramas_event_name") or {}
    # El límite de las ramas se escribe aquí con la tolerancia leída del reentreno; el motivo de reentreno.json es
    # técnico y no se copia
    tolerancia = ((r.get("reentreno") or {}).get("primer_reentreno") or {}).get("tolerancia")
    if ramas:
        texto_ramas = ("- El preprocesador del desarrollo se ajustó con las ramas de event_name_1 y event_name_2, cuyas "
                       "columnas después no entran en el modelo. El código de producción "
                       + ("las conserva" if ramas.get("van") else
                          "no las lleva: sin ellas, el primer reentreno da las previsiones de la validación fila a fila, "
                          f"con la tolerancia de {tolerancia}. Cada rama aprende solo de su columna")
                       + ".")
    else:
        texto_ramas = ("- El preprocesador se ajustó con las ramas de event_name_1 y event_name_2, cuyas columnas después "
                       "no entran en el modelo. Cada rama aprende solo de su columna, así que quitarlas no debería "
                       "cambiar las columnas que entran. Es una interpretación: lo comprueba el reentreno bit a bit de "
                       "la parte 2.")
    lineas += ["## Límites", "",
               "- La ficha R-018 sigue diciendo que la cuestión de los eventos está abierta, porque una ficha no se "
               "reescribe. El responsable del caso la resolvió el 24/11/2026 (reglas, apartado 7): lo recoge la ficha R-019 y el "
               "ganador no usa event_name_1 ni event_name_2.",
               texto_ramas,
               "- El precio de los días a prever se da por conocido, también dentro del horizonte (reglas, apartado 5, D9; "
               "supuesto).",
               "- La historia de precios de cuatro semanas vale porque un producto no tiene huecos de precio (reglas "
               "§5). Si llegara uno con huecos, la cuenta cambiaría.",
               ("- El lote de producción es el año guardado, que se abrió después de aprobar este contrato (petición "
                "28). Lo que se vio en él no cambia el contrato." if "hecho" in str((r.get("lote") or {}).get("estado"))
                else "- No hay lote de producción dentro del caso: la prueba final está apartada y este contrato no la "
                "abre."),
               (f"- La ficha del contrato está en el registro: {r['contrato'].get('ficha')}." if aprobado else
                "- La ficha del contrato entra en el registro cuando el responsable del caso lo apruebe."), ""]

    # ── Lo que el responsable del caso puede decidir, o su aprobación ──
    if aprobado:
        lineas += ["## La aprobación", "",
                   f"El responsable del caso aprobó el contrato el {r['contrato']['fecha'][8:10]}/{r['contrato']['fecha'][5:7]}/"
                   f"{r['contrato']['fecha'][:4]} con las palabras {r['contrato']['palabras']}. "
                   f"Su ficha es la {r['contrato']['ficha']} del registro de "
                   "transformaciones. Con ella empieza la parte 2: el Pipeline, el reentreno y la ejecución diaria.",
                   ""]
    else:
        lineas += ["## Lo que el responsable del caso puede decidir", "",
                   "- Aprobar el contrato como está. Entonces su ficha entra en el registro y empieza la parte 2: el "
                   "Pipeline, el reentreno y la ejecución diaria.",
                   "- Cambiar la cadena o la clase de un paso antes de aprobarlo.", ""]
    return "\n".join(lineas)


# ══ 6b. El informe para la persona ══════════════════════════════════════════════
def cifra(x, decimales=2):
    """Una cifra con coma decimal, como se escribe en español; «sin cifra» si no la hay."""
    return "sin cifra" if x is None else f"{x:.{decimales}f}".replace(".", ",")


def entero(x):
    """Un entero con punto de miles; «sin cifra» si no lo hay."""
    return "sin cifra" if x is None else miles(int(x))


def fecha_es(iso):
    """Una fecha ISO como DD/MM/AAAA."""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "sin fecha"


QUE_HACE = {
    "modulo": "las piezas del Pipeline, los pasos que no aprenden y los que necesitan otras filas, sin ejecutar nada al "
              "importarse",
    "reentrenar": "rehace los dos modelos con la receta fija del contrato, quita contadas las filas sin historia y los "
                  "guarda con su ficha en una carpeta nueva; si la carpeta ya existe, para sin tocarla",
    "ejecutar": "prevé cada serie desde el último día con venta, día a día, sin quitar ninguna fila; la que no se puede "
                "prever sale vacía con su motivo",
    "prueba": "rehace las previsiones sin cargar el modelo guardado ni importar el código de producción y las compara "
              "fila a fila",
    "configuracion": "las rutas, los horizontes, la semilla, la tolerancia y el modelo en uso, que decide el responsable del caso"}
NOMBRE_VALIDACION = {
    "columnas_con_finalista": "cada columna del modelo sale de una finalista",
    "cadenas_completas": "cada finalista tiene su cadena completa en el registro",
    "aprende_despues_de_la_particion": "nada aprende antes de la partición",
    "sin_campos_vacios": "el contrato no tiene campos vacíos",
    "columnas_del_contrato": "el modelo recibe exactamente las columnas del contrato",
    "filas_ejecucion": "la ejecución saca una fila por serie y día",
    "bit_a_bit": "el primer reentreno da las previsiones de la validación",
    "otro_camino": "la prueba por otro camino coincide en la validación y sale en rojo con la previsión estropeada",
    "sin_quitar_filas_al_ejecutar": "la ejecución no quita filas",
    "ficha_cuadra": "el modelo solo se carga si cuadra su ficha",
    "cambia_con_datos_nuevos": "con otra tabla el reentreno sale distinto",
    "periodo_que_toca": "la ejecución para con la venta de otro día",
    "prevision_completa": "ninguna previsión sale vacía sin motivo ni negativa",
    "otro_camino_lote": "la prueba por otro camino coincide en el lote y sale en rojo con la previsión estropeada",
    "filas_lote": "el lote saca tantas filas como había que prever",
    "otro_camino_lote_reentrenado": ("la prueba por otro camino coincide en el lote del reentrenado y sale en rojo con "
                                     "la previsión estropeada"),
    "modelo_en_uso_medido": "el modelo en uso es uno de los medidos"}


def texto_informe(r):
    """informes/preproduccion.md para el responsable del caso, generado del mismo diccionario que el JSON (resultado.md, regla 1).

    Sigue los apartados de resultado.md, «El informe para la persona», en su orden, y cierra con lo que puede decidir
    el responsable del caso. Solo lleva cifras del diccionario.
    """
    obj = r.get("objetivos") or {}
    re_ = r.get("reentreno") or {}
    lote = r.get("lote") or {}
    prueba = r.get("prueba_por_otro_camino") or {}
    val = r.get("validaciones") or {}
    hecho_lote = "hecho" in str(lote.get("estado"))
    en_uso = r.get("modelo_en_uso") or {}
    lineas = ["# La preproducción del caso 69", "",
              f"Fecha de los datos: {r.get('fecha_datos')}. Sale de `{JSON_REL}`, generado por `{SCRIPT_REL}` el "
              f"{fecha_es(r['fecha_ejecucion'][:10])}. Estado: {r['resultado'].get('estado', 'sin estado')}.", ""]
    verdes = [k for k, v in val.items() if v is True]
    rojas = [k for k, v in val.items() if v is False]
    if rojas:
        lineas += [f"Hay {len(rojas)} comprobaciones en rojo: el código de producción no está listo.", ""]
    elif r.get("parte") == 2:
        lineas += [f"El código de producción está escrito y sus {len(verdes)} comprobaciones salen en verde. "
                   + ("También pasó el lote, que es el año guardado. " if hecho_lote else "El lote está pendiente. ")
                   + (f"El modelo en uso es `{en_uso['carpeta']}`: lo aprobó {en_uso['aprobado_por']}." if en_uso
                      else "Falta que el responsable del caso decida qué modelo pasa a uso."), ""]
    else:
        lineas += ["El contrato está escrito. El código de producción todavía no se ha medido aquí.", ""]

    # ── Las finalistas y su cadena ──
    lineas += ["## Las finalistas y su cadena", ""]
    for o in OBJETIVOS:
        if o not in obj:
            continue
        nombres = ", ".join(f"`{f['variable']}`" for f in obj[o]["finalistas"][:4])
        lineas.append(f"- **{NOMBRE[o]}.** El modelo usa {obj[o]['receta']['n_columnas']} columnas, que salen de "
                      f"{len(obj[o]['finalistas'])} finalistas; las primeras son {nombres}.")
    lineas += ["", "Cada finalista tiene su cadena completa en el registro de transformaciones, desde el origen hasta el "
               f"modelo, con la clase de cada paso. Las cadenas están en `{CONTRATO_REL}`.", ""]

    # ── El contrato ──
    c = r.get("contrato") or {}
    lineas += ["## El contrato", ""]
    if c.get("aprobado_por"):
        lineas.append(f"El responsable del caso aprobó el contrato el {fecha_es(c.get('fecha'))} con las palabras {c.get('palabras')}; "
                      f"su ficha es la {c.get('ficha')} del registro.")
    else:
        lineas.append("El contrato espera la aprobación del responsable del caso.")
    u = obj.get("unidades", {}).get("receta", {})
    lineas += [f"Los dos modelos son {u.get('algoritmo')} con la receta fija de la búsqueda, semilla {u.get('semilla')}. "
               f"En {len(r.get('distinto_de_lo_esperado') or [])} pasos el registro dice algo distinto de lo que "
               "esperaba la petición; manda el registro.", ""]

    # ── Qué hace cada script ──
    lineas += ["## Qué hace cada script", ""]
    codigo = r.get("codigo") or {}
    if codigo:
        lineas += [f"- `{codigo[k]}`: {QUE_HACE[k]}." for k in ("modulo", "reentrenar", "ejecutar", "prueba",
                                                               "configuracion") if k in codigo]
    else:
        lineas.append("El código de producción se escribe cuando el responsable del caso apruebe el contrato.")
    lineas.append("")

    # ── El reentreno ──
    lineas += ["## El reentreno", ""]
    if re_:
        primer = re_.get("primer_reentreno") or {}
        lineas.append(f"El primer reentreno está en `{re_.get('ruta')}`. Se ajustó con {entero(re_.get('filas_ajuste'))} "
                      "filas de la construcción, las mismas que el modelado.")
        lineas.append(("Da fila a fila las previsiones de la validación" if re_.get("igual_bit_a_bit") else
                       "No da las previsiones de la validación")
                      + f" en sus {primer.get('origenes')} orígenes, con la tolerancia de {primer.get('tolerancia')}.")
        rn = re_.get("reentrenado") or {}
        comp = re_.get("comparacion_con_el_en_uso") or {}
        if rn:
            lineas += ["", f"El reentrenado con un año más está en `{rn.get('ruta')}`: se ajustó con "
                       f"{entero(rn.get('filas_ajuste'))} filas, construcción y validación juntas."]
        if comp.get("reentrenado"):
            lineas += ["", "Los dos se midieron en la prueba final, con las mismas reglas que la validación. "
                       + ("Cuando se midieron no había modelo en uso: el primer reentreno hizo su papel en la "
                          "comparación." if en_uso else "No hay modelo en uso: el primer reentreno hace su papel en "
                                                         "la comparación."), "",
                       "| Objetivo | Modelo | Veredicto | Orígenes que gana | Ventaja | Error del modelo | Sesgo |",
                       "|---|---|---|---|---|---|---|"]
            for o in OBJETIVOS:
                for lado, nombre in (("en_uso", "primer reentreno"), ("reentrenado", "reentrenado")):
                    x = (comp.get(lado) or {}).get(o) or {}
                    if not x:
                        continue
                    ganados = (f"{x.get('origenes_que_gana')} de {x.get('de')}" if x.get("origenes_que_gana") is not None
                               else "sin cifra")
                    lineas.append(f"| {NOMBRE[o]} | {nombre} | {x.get('veredicto', 'sin cifra')} | {ganados} | "
                                  f"{cifra(x.get('ventaja'))} | {cifra(x.get('error_modelo'))} | "
                                  f"{cifra(x.get('sesgo_modelo'))} |")
            lineas += ["", "La ventaja son los puntos de error que el modelo falla menos que la regla que menos falla "
                       "en cada origen; el error y el sesgo van por cada 100 vendidos. Las cifras enteras están en "
                       f"`{comp.get('fuente', 'informes/prueba_final.json')}`."]
    else:
        lineas.append("El reentreno se hace en la parte 2.")
    lineas.append("")

    # ── El lote ──
    lineas += ["## El lote", ""]
    if hecho_lote:
        sin = lote.get("sin_puntuar") or []
        lineas.append(f"El lote es el año guardado. La ejecución diaria se lanzó {lote.get('ejecuciones')} veces con el "
                      f"primer reentreno, una por origen, con la venta cortada en cada uno.")
        lineas.append(f"Había que prever {entero(lote.get('filas_entrada'))} filas de serie y día y salieron "
                      f"{entero(lote.get('filas_salida'))}. "
                      + ("Ninguna quedó sin previsión." if not sin else
                         "Quedaron sin previsión: " + "; ".join(f"{x['motivo']}, {entero(x['filas'])}" for x in sin) + "."))
        lineas.append(f"Las salidas están en `{lote.get('ruta')}`.")
    else:
        lineas.append("El lote está pendiente: lo ejecuta la petición 28 con el año guardado.")
    lineas.append("")

    # ── La prueba por otro camino ──
    lineas += ["## La prueba por otro camino", ""]
    if prueba:
        lineas.append(f"Sobre {prueba.get('sobre', 'los orígenes de la validación')}, la prueba "
                      + ("coincide" if prueba.get("coincide") else "no coincide")
                      + f" con la tolerancia de {prueba.get('tolerancia')}"
                      + ("; sale en rojo con una previsión estropeada a propósito." if prueba.get("rojo_con_estropeada")
                         else "; no sale en rojo con la previsión estropeada."))
        pl = prueba.get("lote") if isinstance(prueba.get("lote"), dict) else None
        if pl:
            filas = sum((x or {}).get("filas", 0) for x in (pl.get("por_objetivo") or {}).values())
            lineas.append(f"En el lote, {entero(filas)} filas de {pl.get('origenes')} orígenes: "
                          + ("coinciden todas" if pl.get("coincide") else "no coinciden todas")
                          + ("; la previsión estropeada sale en rojo." if pl.get("rojo_con_estropeada")
                             else "; la previsión estropeada no sale en rojo."))
        else:
            lineas.append("En el lote está pendiente de la petición 28.")
        plr = prueba.get("lote_reentrenado") if isinstance(prueba.get("lote_reentrenado"), dict) else None
        if plr:
            filas = sum((x or {}).get("filas", 0) for x in (plr.get("por_objetivo") or {}).values())
            lineas.append(f"En el lote del reentrenado, {entero(filas)} filas de {plr.get('origenes')} orígenes: "
                          + ("coinciden todas" if plr.get("coincide") else "no coinciden todas")
                          + ("; la previsión estropeada sale en rojo." if plr.get("rojo_con_estropeada")
                             else "; la previsión estropeada no sale en rojo."))
    else:
        lineas.append("La prueba se hace en la parte 2.")
    lineas.append("")

    # ── Validaciones ──
    lineas += ["## Validaciones", ""]
    for k, v in val.items():
        estado = {True: "en verde", False: "en rojo"}.get(v, "pendiente")
        lineas.append(f"- {NOMBRE_VALIDACION.get(k, k).capitalize()}: {estado}.")
    lineas.append("")

    # ── Parámetros usados ──
    lineas += ["## Parámetros usados", ""]
    for x in r.get("parametros") or []:
        valor = ", ".join(str(v) for v in x["valor"]) if isinstance(x.get("valor"), list) else x.get("valor")
        lineas.append(f"- {x['nombre'].replace('_', ' ').capitalize()}: {valor} (`{x['origen']}`).")
    if prueba.get("tolerancia") is not None:
        lineas.append(f"- Tolerancia de la prueba por otro camino: {prueba.get('tolerancia')} "
                      "(los parámetros del método preproduccion).")
    lineas.append("")

    # ── Datos personales ──
    lineas += ["## Datos personales", ""]
    if (r.get("datos_personales") or {}).get("proteccion_datos_json"):
        lineas.append(f"La protección de los datos está descrita en `{PROTECCION_REL}`.")
    else:
        lineas.append(f"No existe `{PROTECCION_REL}`: los datos no pasaron por la protección. Las tablas son ventas por "
                      "departamento y tienda. Ni el contrato ni el código de producción usan columnas sobre personas.")
    lineas.append("")

    # ── Límites ──
    lineas += ["## Límites", "",
               "- El precio de los días a prever se da por conocido, también dentro del horizonte (reglas, apartado 5, D9). Es "
               "un supuesto.",
               "- Los modelos guardados ejecutan código al abrirse: solo se cargan si cuadra su ficha."]
    if hecho_lote:
        lineas += ["- Las entradas de cada origen del lote se armaron fuera del caso y no se guardan; sus huellas están "
                   f"en el resumen del lote (`{lote.get('ruta')}/resumen.json`).",
                   ("- La prueba por otro camino se hizo sobre el lote de los dos modelos."
                    if prueba.get("lote_reentrenado") else
                    "- La prueba por otro camino se hizo sobre el lote del primer reentreno. El del reentrenado se "
                    "midió sin ella.")]
    lineas.append("")

    # ── Lo que puede decidir el responsable del caso ──
    if r.get("pendientes"):
        lineas += ["## Lo que puede decidir el responsable del caso", ""]
        for x in r["pendientes"]:
            lineas.append(f"- {x['pregunta']} Opciones: {'; '.join(x['opciones'])}.")
        lineas.append("")
    return "\n".join(lineas)


# ══ 7. Ejecución principal ══════════════════════════════════════════════════════
def principal(raiz, dir_reentreno=None, dir_ensayo=None, dir_lote=None, dir_reentrenado=None):
    """Comprueba al empezar, arma el contrato, lo valida y lo escribe; el JSON se escribe siempre.

    Con el contrato aprobado en el registro y las dos carpetas de la parte 2, rellena además la parte 2.
    """
    r = {"metodo": "preproduccion", "version_metodo": version_metodo(raiz), "script": SCRIPT_REL, "fecha_datos": None,
         "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": {"python": platform.python_version(), "scikit-learn": version("scikit-learn"),
                     "pandas": version("pandas"), "ejecutable": sys.executable},
         "entradas": [], "resultado": {}, "pendientes": [], "puerta_de_juan": False, "parte": 1,
         "contrato": {"ruta": CONTRATO_REL, "aprobado_por": "", "fecha": ""},
         "identificador": IDENTIFICADOR,
         "objetivo": "unidades y dolares, un modelo cada uno",
         "objetivos": {},
         "codigo": None, "reentreno": None, "lote": None, "prueba_por_otro_camino": None,
         "parte_2": "pendiente: empieza cuando el responsable del caso apruebe el contrato",
         "validaciones": {}, "detalle_validaciones": {}, "distinto_de_lo_esperado": [],
         "piezas_existentes": [], "datos_personales": {}, "paradas": [],
         "parametros": [], "teoria_aplicada": ["39.1 Las tres fases", "39.2 La preproducción: dos tareas"]}

    def terminar(estado, riesgo, resumen, siguiente, artefactos):
        """Escribe el JSON con su estado (resultado.md, regla 5) y devuelve el estado."""
        r["resultado"] = {"estado": estado, "riesgo": riesgo, "resumen": resumen, "artefactos": artefactos,
                          "siguiente": siguiente}
        (raiz / "informes").mkdir(parents=True, exist_ok=True)
        (raiz / JSON_REL).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        # El informe para la persona, del mismo diccionario, solo cuando ya hay contrato (resultado.md, regla 1)
        if r["objetivos"]:
            (raiz / MD_REL).write_text(texto_informe(r), encoding="utf-8")
        return estado

    # ── 7.1 Al empezar (resultado.md, «Al empezar») ──
    rutas = {n: raiz / n for n in (BUSQUEDA_REL, VALIDACION_REL, PREPARACION_REL, PRESELECCION_REL, VARIABLES_REL,
                                   REGISTRO_REL, PLANTEAMIENTOS_REL)}
    faltan = [n for n, ruta in rutas.items() if not ruta.exists()]
    if faltan:
        r["paradas"].append({"codigo": "falta_entrada", "motivo": f"faltan {', '.join(faltan)}"})
        return terminar("PARADO", "alto", f"Faltan entradas: {', '.join(faltan)}.", "ejecutar antes los scripts 11 a 16",
                        [JSON_REL])
    for n, ruta in rutas.items():
        r["entradas"].append({"ruta": n, "sha256": huella(ruta)})
    busqueda, validacion = leer_json(rutas[BUSQUEDA_REL]), leer_json(rutas[VALIDACION_REL])
    preparacion, preseleccion = leer_json(rutas[PREPARACION_REL]), leer_json(rutas[PRESELECCION_REL])
    variables = leer_json(rutas[VARIABLES_REL])
    registro = leer_registro(rutas[REGISTRO_REL].read_text(encoding="utf-8"))
    # La aprobación del responsable del caso, si su ficha está en el registro; sin ella el contrato sigue propuesto
    aprobacion = aprobacion_del_contrato(registro)
    if aprobacion:
        r["contrato"] = {"ruta": CONTRATO_REL, **aprobacion}
    planteamientos = rutas[PLANTEAMIENTOS_REL].read_text(encoding="utf-8")
    r["fecha_datos"] = busqueda.get("fecha_datos")

    if (raiz / ASIGNACION_REL).exists():
        r["paradas"].append({"codigo": "modelo_por_clase", "motivo": "el método aún no admite un modelo por clase"})
    esperada = ((validacion.get("receta") or {}).get("huella") or {}).get("esperada")
    if esperada != huella(rutas[BUSQUEDA_REL]):
        r["paradas"].append({"codigo": "otra_busqueda",
                             "motivo": "busqueda.json no es el que validó la validación (huella distinta)"})
    for o in OBJETIVOS:
        veredicto = (((validacion.get("validacion") or {}).get(o) or {}).get("veredicto") or {}).get("veredicto")
        if veredicto != "gana":
            r["paradas"].append({"codigo": "sin_veredicto", "motivo": f"{o}: la validación dice «{veredicto}»"})
        aprobado = (((validacion.get("receta") or {}).get("ganador") or {}).get(o) or {}).get("aprobado_por")
        if not aprobado:
            r["paradas"].append({"codigo": "ganador_sin_aprobar", "motivo": f"{o}: el ganador no está aprobado"})
    m = re.search(r"\*\*Veredicto de la validación \(([^)]*)\)", planteamientos)
    r["veredicto_aprobado"] = m.group(1) if m else None
    if not m:
        r["paradas"].append({"codigo": "veredicto_sin_aprobar",
                             "motivo": "los planteamientos no traen el veredicto aprobado por el responsable del caso"})
    if r["paradas"]:
        return terminar("PARADO", "alto", "El modelo no está validado y aprobado: no se escribe el contrato.",
                        "aprobar el ganador y el veredicto de la validación", [JSON_REL])

    # ── 7.2 El contrato de cada objetivo y sus validaciones ──
    matriz = (preparacion.get("matriz") or {}).get("variables") or []
    detalles = {}
    for o in OBJETIVOS:
        ganador = (busqueda.get("ganador") or {}).get(o) or {}
        r["objetivos"][o], detalles[o] = contrato_objetivo(o, ganador, matriz, registro, validacion, variables,
                                                           preparacion)
    r["distinto_de_lo_esperado"] = distinto_de_lo_esperado(r["objetivos"])
    r["piezas_existentes"] = [x for x in PIEZAS_EXISTENTES if (raiz / x).exists()]
    r["datos_personales"] = {"proteccion_datos_json": (raiz / PROTECCION_REL).exists(),
                             "columnas_de_personas_usadas": []}
    r["parametros"] = [{"nombre": "retardos", "valor": parametro(variables, "retardos"), "origen": VARIABLES_REL},
                       {"nombre": "ventanas de las medias", "valor": parametro(variables, "ventanas de las medias"),
                        "origen": VARIABLES_REL},
                       {"nombre": "semanas_previas_con_precio", "valor": parametro(variables,
                                                                                   "semanas_previas_con_precio"),
                        "origen": VARIABLES_REL},
                       {"nombre": "ficha de la preselección", "valor": preseleccion.get("ficha_registro"),
                        "origen": PRESELECCION_REL}]

    # Los campos del contrato que se comprueban vacíos: lo que fija la parte 1 (sin el estado de aprobación)
    contrato_comprobado = {"identificador": r["identificador"], "objetivo": r["objetivo"], "objetivos": r["objetivos"],
                           "veredicto_aprobado": r["veredicto_aprobado"]}
    # «esperado» es None a propósito cuando la petición no nombraba el paso: no es un campo del contrato
    sin_esperado = json.loads(json.dumps(contrato_comprobado))
    for o in sin_esperado["objetivos"].values():
        # Un hiperparámetro a None es un valor de la librería (sin límite), no un hueco del contrato
        for clave in ("hiperparametros", "buscados"):
            if isinstance(o["receta"].get(clave), dict):
                o["receta"][clave] = {k: "None" if v is None else v for k, v in o["receta"][clave].items()}
        for f in o["finalistas"]:
            for p in f["cadena"]:
                p.pop("esperado", None)
    vacios = campos_vacios(sin_esperado)
    r["detalle_validaciones"] = {o: detalles[o] for o in OBJETIVOS} | {"campos_vacios": vacios}
    r["validaciones"] = {
        "columnas_con_finalista": all(not detalles[o]["sin_finalista"] for o in OBJETIVOS),
        "cadenas_completas": all(not detalles[o]["huecos"] for o in OBJETIVOS)
                             and all(r["objetivos"][o]["finalistas"] for o in OBJETIVOS),
        "aprende_despues_de_la_particion": all(not detalles[o]["aprende_antes"] for o in OBJETIVOS),
        "sin_campos_vacios": not vacios,
        "columnas_del_contrato": None, "filas_ejecucion": None, "bit_a_bit": None, "otro_camino": None,
        "sin_quitar_filas_al_ejecutar": None, "ficha_cuadra": None, "cambia_con_datos_nuevos": None,
        "periodo_que_toca": None, "prevision_completa": None,
    }
    fallidas = [k for k, v in r["validaciones"].items() if v is False]
    if fallidas:
        return terminar("ERROR", "alto", f"Validaciones en rojo: {', '.join(fallidas)}. No se escribe el contrato.",
                        "revisar el detalle de las validaciones en el JSON", [JSON_REL])

    # ── 7.3 La parte 2, solo con el contrato aprobado y las dos carpetas (resultado.md: sin aprobar, no empieza) ──
    faltan_parte_2 = []
    if aprobacion and dir_reentreno is not None and dir_ensayo is not None:
        campos, val2, faltan_parte_2 = parte_2(raiz, Path(dir_reentreno), Path(dir_ensayo),
                                               dir_lote and Path(dir_lote), dir_reentrenado and Path(dir_reentrenado))
        if campos is not None:
            r.update({k: v for k, v in campos.items()})
            r["validaciones"].update(val2)
            r["parte"] = 2
            r["parte_2"] = ("hecha: Pipeline, reentreno y ejecución; el lote, con el año guardado (petición 28)"
                            if dir_lote else "hecha: Pipeline, reentreno y ejecución; el lote queda para la petición 28")

    # ── 7.4 Escribir el contrato, solo con las validaciones de la parte 1 en verde (error 15) ──
    ruta_contrato = raiz / CONTRATO_REL
    ruta_contrato.parent.mkdir(parents=True, exist_ok=True)
    ruta_contrato.write_text(texto_contrato(r), encoding="utf-8")
    n = {o: (len(r["objetivos"][o]["finalistas"]), r["objetivos"][o]["receta"]["n_columnas"]) for o in OBJETIVOS}
    resumen = (f"unidades: {n['unidades'][1]} columnas de {n['unidades'][0]} finalistas; dolares: {n['dolares'][1]} "
               f"columnas de {n['dolares'][0]} finalistas; cadenas completas y validaciones de la parte 1 en verde")
    artefactos = [JSON_REL, CONTRATO_REL]
    if faltan_parte_2:
        r["paradas"].append({"codigo": "falta_parte_2", "motivo": f"faltan {', '.join(faltan_parte_2)}"})
        return terminar("ERROR", "alto", f"{resumen}; la parte 2 no se puede rellenar: faltan {faltan_parte_2}",
                        "ejecutar reentrenar.py, la prueba por otro camino y el ensayo de ejecutar.py", [JSON_REL])
    if r["parte"] == 2:
        # El modelo en uso, si el responsable del caso lo aprobó en la configuración: tiene que ser uno de los modelos medidos
        reentrenado = (r["reentreno"].get("reentrenado") or {}).get("ruta")
        medidos = [r["reentreno"]["ruta"]] + ([reentrenado] if reentrenado else [])
        en_uso = modelo_en_uso_aprobado(raiz)
        if en_uso:
            r["modelo_en_uso"] = en_uso
            r["validaciones"]["modelo_en_uso_medido"] = en_uso["carpeta"] in medidos
        fallidas = [k for k, v in r["validaciones"].items() if v is not True]
        if fallidas:
            return terminar("ERROR", "alto", f"{resumen}; validaciones de la parte 2 en rojo: {', '.join(fallidas)}",
                            "revisar el detalle de la parte 2 en el JSON", artefactos)
        r["puerta_de_juan"] = True
        if reentrenado:
            p02 = {"id": "P-02", "tabla": "modelo en uso", "columna": "los dos modelos",
                   "pregunta": (f"¿Qué modelo pasa a uso: el primer reentreno ({r['reentreno']['ruta']}) o "
                                f"el reentrenado con un año más ({reentrenado})?"),
                   "opciones": [f"el primer reentreno ({r['reentreno']['ruta']})",
                                f"el reentrenado ({reentrenado})", "ninguno todavía"]}
        else:
            p02 = {"id": "P-02", "tabla": "modelo en uso", "columna": "los dos modelos",
                   "pregunta": f"¿Apruebas el primer reentreno ({r['reentreno']['ruta']}) como modelo en uso?",
                   "opciones": ["aprobarlo como modelo en uso", "no usarlo todavía"]}
        r["pendientes"] = [p02]
        # P-02 resuelta: no se borra, pasa a decisiones con lo decidido y dónde quedó
        if en_uso:
            r["pendientes"], r["puerta_de_juan"] = [], False
            r["decisiones"] = [p02 | {"estado": "resuelta", "decision": f"{en_uso['carpeta']}: {en_uso['aprobado_por']}",
                                      "donde": f"{en_uso['fuente']}, modelo_en_uso"}]
            return terminar("OK", "bajo", f"{resumen}; contrato {r['contrato']['estado']}; parte 2 y lote con sus "
                            f"validaciones en verde; modelo en uso {en_uso['carpeta']}, {en_uso['aprobado_por']}",
                            "el despliegue (paso 7): el lote diario con el modelo en uso", artefactos + [MD_REL])
        if dir_lote:
            return terminar("AVISO", "medio", f"{resumen}; contrato {r['contrato']['estado']}; parte 2 y lote con "
                            "sus validaciones en verde", "El responsable del caso decide el modelo en uso (puerta 4)",
                            artefactos + [MD_REL])
        return terminar("AVISO", "medio", f"{resumen}; contrato {r['contrato']['estado']}; parte 2 con sus "
                        "validaciones en verde; el lote queda para la petición 28",
                        "la petición 28 ejecuta el lote con el año guardado; el responsable del caso decide el modelo en uso", artefactos)
    if aprobacion:
        return terminar("AVISO", "medio", f"{resumen}; contrato {r['contrato']['estado']}; falta la parte 2",
                        "la parte 2: el Pipeline, el reentreno y la ejecución (petición 27)", artefactos)
    r["puerta_de_juan"] = True
    r["pendientes"] = [{"id": "P-01", "tabla": "contrato de producción", "columna": "todas las finalistas",
                        "pregunta": "¿Apruebas el contrato de producción antes de escribir el código de la parte 2?",
                        "opciones": ["aprobar el contrato", "cambiar una cadena o la clase de un paso"]}]
    return terminar("PARADO", "medio", f"{resumen}; el contrato espera al responsable del caso", "El responsable del caso aprueba el contrato; después, la "
                    "parte 2 (Pipeline, reentrenar y ejecutar)", artefactos)


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Contrato de producción del caso 69")
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta con la estructura del caso")
    argumentos.add_argument("--reentreno", default=None, help="carpeta del primer reentreno (parte 2)")
    argumentos.add_argument("--ensayo", default=None, help="carpeta del ensayo de la ejecución (parte 2)")
    argumentos.add_argument("--lote", default=None, help="carpeta del lote de la prueba final (petición 28)")
    argumentos.add_argument("--reentrenado", default=None, help="carpeta del reentrenado con un año más")
    args = argumentos.parse_args()
    raiz_de_trabajo = Path(args.raiz).resolve()
    print("intérprete:", sys.executable)
    salida_json = raiz_de_trabajo / JSON_REL
    try:
        estado_final = principal(raiz_de_trabajo, args.reentreno and Path(args.reentreno).resolve(),
                                 args.ensayo and Path(args.ensayo).resolve(), args.lote and Path(args.lote).resolve(),
                                 args.reentrenado and Path(args.reentrenado).resolve())
        puerta = json.loads(salida_json.read_text(encoding="utf-8")).get("puerta_de_juan")
    except Exception as fallo:  # un fallo técnico deja el JSON en ERROR (resultado.md, regla 5) y sale con 1
        traceback.print_exc()
        error = {"metodo": "preproduccion", "script": SCRIPT_REL, "fecha_datos": None,
                 "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
                 "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(fallo).__name__}: {fallo}",
                               "artefactos": [JSON_REL], "siguiente": "revisar el fallo"},
                 "pendientes": [], "puerta_de_juan": False, "validaciones": {}, "paradas": []}
        salida_json.parent.mkdir(parents=True, exist_ok=True)
        salida_json.write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding="utf-8")
        estado_final, puerta = "ERROR", False
    print("estado:", estado_final)
    sys.exit(0 if estado_final in ("OK", "AVISO") or puerta else 1)
