"""Informe del modelado del caso 69: reúne lo medido en el paso 5 y lo escribe para la persona, sin medir nada.

Aplica el método aprendizaje-automatico, apartado 10 y su resultado.md («El informe para la persona») con el veredicto que el responsable del caso
aprobó el 25/11/2026 («Sí, apruebo el veredicto»; config/metodo/04_planteamientos.md §2). Lo que
hace, en este orden:
  1. lee los siete JSON del paso 5 (partición, preparación, variables, preselección, modelo mínimo, búsqueda y
     validación), comprueba que ninguno está en ERROR y que todos tienen la misma fecha de los datos, y guarda su huella;
  2. reúne en un diccionario cada valor que cita el informe, con su fichero y su camino dentro del JSON; no calcula
     ninguna cifra nueva: solo cuenta y ordena lo que ya traen los JSON;
  3. dibuja las dos figuras de assets/evaluacion_continua.py por objetivo, sin cambiarla, sobre
     data/processed/previsiones_validacion.parquet sin los días fuera del error;
  4. con ese mismo diccionario escribe informes/modelado.json e informes/modelado.md en la misma ejecución.
Lleva además el bloque «robustez» de validacion.json (el responsable del caso, 25/11/2026, «Sí, amplíalo»): «Lo que matiza la
ventaja», dentro de «La validación», y en «Límites» los eventos que la validación no cubre y la concentración de la
ventaja, citados como las demás cifras.
Lleva también el bloque «niveles» (el responsable del caso, 25/11/2026, «Apruebo el guion»; ficha, pregunta 3): «La previsión
sumada por tienda, categoría, estado y cadena», dentro de «La validación», citada como las demás cifras.
No abre las tablas de hechos de data/processed, no reajusta, no prevé y no cambia ningún JSON de los pasos anteriores.

Depende de los scripts 10 a 16 (error 2): lee lo que dejaron y para si falta alguno o si alguno está en ERROR.

Uso: python -W error scripts/17_informe_modelado.py [--raiz CARPETA]
Sale con 0 si todas las validaciones quedan en verde y con 1 si no.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import argparse
import hashlib
import json
import math
import platform
import re
import sys
import time
import traceback
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Sin pantalla: las figuras van a fichero
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow  # noqa: E402

# La pieza común de evaluación, que no ejecuta nada al importarse (error 1)
CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
import evaluacion_continua as ec  # noqa: E402

SCRIPT_REL = "scripts/17_informe_modelado.py"
FECHA_DATOS = "2015-05-22"
PARTICION_REL = "informes/particion.json"
PREPARACION_REL = "informes/preparacion.json"
VARIABLES_REL = "informes/variables_modelo.json"
PRESELECCION_REL = "informes/preseleccion.json"
MINIMO_REL = "informes/modelo_minimo.json"
BUSQUEDA_REL = "informes/busqueda.json"
VALIDACION_REL = "informes/validacion.json"
ENTRADAS_JSON = (PARTICION_REL, PREPARACION_REL, VARIABLES_REL, PRESELECCION_REL, MINIMO_REL, BUSQUEDA_REL,
                 VALIDACION_REL)
PREVISIONES_REL = "data/processed/previsiones_validacion.parquet"
PLANTEAMIENTOS_REL = "config/metodo/04_planteamientos.md"
REGLAS_REL = "config/negocio/reglas-negocio.md"
PROTECCION_REL = "config/fuentes/proteccion-datos.json"
VERSION_METODO = "20/11/2026"  # versión del método aprendizaje-automatico con que se escribió este script
JSON_REL = "informes/modelado.json"
MD_REL = "informes/modelado.md"
FIGURAS_REL = "informes/figuras_modelado"

# Planteamientos §2, «Veredicto de la validación»: la aprobación del responsable del caso, que el script busca escrita
APROBACION_VEREDICTO = "el responsable del caso, 25/11/2026, «Sí, apruebo el veredicto»"
SECCION_VEREDICTO = "§2, «Veredicto de la validación»"
# Planteamientos §2, decisión 6: por qué no se probó un modelo por serie
MODELO_POR_SERIE = "Uno por serie multiplicaría por 70 el coste"
# Reglas, apartado 6, «Lo que no se puede calcular»: los datos que harían falta (vía 3 del método, apartado 8)
SECCION_NO_SE_PUEDE = "§6, «Lo que no se puede calcular»"
INFORMACION_NUEVA = [
    {"dato": "coste y margen de cada producto",
     "para_que": "calcular el dinero que ahorra la previsión",
     "frase": "El dinero que ahorra la previsión: los datos no traen coste, margen ni existencias."},
    {"dato": "existencias de cada producto en cada tienda y día",
     "para_que": "calcular el dinero que ahorra la previsión y saber si un día a cero fue falta de demanda o estante "
                 "vacío, es decir, las ventas perdidas",
     "frase": "Las ventas perdidas por estante vacío: un cero no dice si había producto."}]

OBJETIVOS = ("unidades", "dolares")
OBJETIVO_TEXTO = {"unidades": "unidades", "dolares": "dólares"}
UNIDAD = {"unidades": "unidades por cada 100 vendidas", "dolares": "dólares por cada 100 vendidos"}
REGLAS = ("repetir_semana_anterior", "media_28_dias", "media_mismo_dia_4_semanas")
PREDICTORES = ("modelo",) + REGLAS + ("trivial", "suavizado")
# La previsión sumada, de lo general a lo concreto (transmision-conocimiento §3; reglas, apartado 4)
NIVELES = ("cadena", "estado", "tienda", "categoria")
NIVEL_TEXTO = {"cadena": "cadena", "estado": "estado", "tienda": "tienda", "categoria": "categoría"}
# Los nombres que no trae ningún JSON; los de las reglas con cifras en el nombre se citan de validacion.json
NOMBRE = {"modelo": "el modelo", "repetir_semana_anterior": "repetir la semana anterior",
          "media_28_dias": "la media de los últimos 28 días",
          "media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores",
          "trivial": "el trivial (la mediana)", "trivial_mediana": "el trivial (la mediana)",
          "suavizado": "el suavizado exponencial"}
DIAS = {"dias_con_evento": "con algún evento", "dias_sin_evento": "sin evento",
        "dias_snap": "SNAP del estado de la tienda", "dias_sin_snap": "sin SNAP"}

# Los parámetros propios de este script, con su origen; van al JSON y al informe
PARAMETROS = {
    "decimales de errores, sesgos y ventajas": {"valor": 2, "origen": "informes/validacion_resultado.md, el formato "
                                                                      "del paso anterior"},
    "decimales del R²": {"valor": 3, "origen": "decisión de este informe: con dos, los R² del modelo y de las reglas "
                                               "se leen casi iguales"},
    "redondeo": {"valor": "la mitad, hacia arriba (Decimal, ROUND_HALF_UP)", "origen": "programacion-del-caso, "
                                                                                     "error 9"},
    "importancias que se enseñan": {"valor": 5, "origen": "como informes/busqueda_propuesta.md"},
    "filas de las figuras": {"valor": "las de la validación sin los días fuera del error",
                             "origen": "petición del informe; reglas, apartado 6"},
    "formato de las figuras": {"valor": "PNG a 100 puntos por pulgada", "origen": "decisión de este informe"},
}
DPI = PARAMETROS["formato de las figuras"]["valor"].split()[2]

APARTADOS = ["Lo aprobado antes de entrenar", "Qué se probó y cuánto costó", "El desequilibrio", "Ranking",
             "El ganador y por qué", "Qué variables pesan", "La validación", "El corte", "¿Se da por bueno?",
             "Las tres vías de mejora", "Validaciones", "Parámetros usados", "Datos personales", "Límites"]
NOMBRES_VALIDACION = (
    "entradas_sin_error", "fechas_datos_iguales", "veredicto_aprobado_escrito", "citas_con_origen", "citas_existen",
    "redondeo_igual", "numeros_en_el_json", "apartados_en_orden", "no_aplica_explicado", "datos_personales_bien",
    "sin_tablas_hechos", "sin_resultados_escritos", "figuras_con_las_filas_medidas", "figuras_escritas",
    "sin_coma_y", "limites_nombran_eventos", "entradas_sin_cambiar", "informe_estable")
DESCRIPCION_VALIDACION = {
    "entradas_sin_error": "ningún JSON de entrada en ERROR",
    "fechas_datos_iguales": "la misma fecha de los datos en los siete JSON",
    "veredicto_aprobado_escrito": "la aprobación del veredicto, escrita en los planteamientos",
    "citas_con_origen": "cada valor citado con su fichero y su camino",
    "citas_existen": "cada valor citado es el que hay en su fichero",
    "redondeo_igual": "cada cifra escrita con el redondeo que guarda el JSON",
    "numeros_en_el_json": "cada número del informe está en modelado.json",
    "apartados_en_orden": "los catorce apartados, en el orden de resultado.md",
    "no_aplica_explicado": "el desequilibrio y el corte, explicados con su motivo",
    "datos_personales_bien": "el apartado de datos personales dice si existe la protección",
    "sin_tablas_hechos": "el script no abre ninguna tabla de hechos",
    "sin_resultados_escritos": "ninguna validación escrita con su resultado puesto (programacion-del-caso, error 24)",
    "figuras_con_las_filas_medidas": "las figuras usan las filas que midió la validación",
    "figuras_escritas": "las cuatro figuras están en disco",
    "sin_coma_y": "ningún «, y» en el texto",
    "limites_nombran_eventos": "«Límites» nombra cada evento que la validación no cubre",
    "entradas_sin_cambiar": "las entradas, iguales antes y después",
    "informe_estable": "el informe final pasa las mismas comprobaciones que el borrador"}

# Lo que no cuenta como número del informe: código, enlaces, apartados, identificadores y la numeración de una lista
EXENTOS = [r"`[^`]*`", r"\]\([^)]*\)", r"§\s?\d+(?:\.\d+)*", r"\b[A-Z][A-Za-z]*_\d+\b", r"\bR\d+-\d+\b",
           r"\b(?:CP|WF|P)-\d+\b", r"decisión \d+", r"apartado \d+(?:\.\d+)*", r"cuestión \d+", r"caso \d+", r"programacion-del-caso, error \d+", r"(?m)^\s*\d+\.\s"]
TOKEN = re.compile(r"\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d+(?:[.,]\d+)*")
# Una ruta entre comillas a una tabla de hechos de data/processed (programacion-del-caso: el script no la abre)
PATRON_HECHOS = re.compile(r"[\"'][^\"'\n]*hechos_\w*\.parquet")
_LEER = object()


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
    if obj is None:
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
            "pyarrow": pyarrow.__version__, "matplotlib": matplotlib.__version__, "ejecutable": sys.executable}


def version_metodo(raiz=None):
    """La versión del método con que se escribió este script."""
    return VERSION_METODO


def partes_del_camino(camino):
    """Los pasos de un camino como «validacion.unidades.errores.todas[0].error»: claves y posiciones."""
    return [int(i) if i else k for k, i in re.findall(r"([^.\[\]]+)|\[(\d+)\]", camino)]


def obtener(d, camino):
    """El valor de un camino dentro de un JSON; KeyError o IndexError si no está."""
    nodo = d
    for paso in partes_del_camino(camino):
        nodo = nodo[paso]
    return nodo


def filas_del_camino(d, camino):
    """El rótulo «filas» más cercano por encima del valor, como lo dejó el paso que lo calculó (resultado.md)."""
    nodo, filas = d, None
    for paso in partes_del_camino(camino):
        if isinstance(nodo, dict) and isinstance(nodo.get("filas"), str):
            filas = nodo["filas"]
        nodo = nodo[paso]
    if isinstance(nodo, dict) and isinstance(nodo.get("filas"), str):
        filas = nodo["filas"]
    return filas


def redondear(valor, decimales):
    """Un número redondeado a la mitad hacia arriba, como Excel (programacion-del-caso, error 9)."""
    return Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def numero_es(d, decimales, signo):
    """Un Decimal escrito en español: punto de millar y coma decimal; con signo si se pide."""
    texto = f"{abs(d):,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    prefijo = "-" if d < 0 else ("+" if signo else "")
    return prefijo + texto


def escribir(valor, decimales=None, signo=False, tipo=None):
    """Un valor como se escribe en el informe. Devuelve (texto, redondeado)."""
    if tipo == "fecha":
        return (pd.Timestamp(valor).strftime("%d/%m/%Y"), None) if valor else ("sin cifra", None)
    if valor is None:
        return "sin cifra", None
    if isinstance(valor, bool):
        return ("sí" if valor else "no"), None
    if isinstance(valor, str):
        return valor, None
    if isinstance(valor, dict):
        return "; ".join(f"{k}: {escribir(v)[0]}" for k, v in valor.items()), None
    if isinstance(valor, (list, tuple)):
        return ("; ".join(escribir(v, decimales, signo)[0] for v in valor) if valor else "ninguna"), None
    if decimales is not None:
        d = redondear(valor, decimales)
        return numero_es(d, decimales, signo), float(d)
    if isinstance(valor, int):
        return numero_es(Decimal(valor), 0, signo), valor
    texto = f"{valor:g}".replace(".", ",")
    return (("+" if signo and valor >= 0 else "") + texto), valor


def tokens(texto):
    """Los números de un texto: fechas enteras y números con sus separadores."""
    return TOKEN.findall(texto)


def seccion(md, titulo):
    """El cuerpo de un apartado «## titulo», hasta el siguiente apartado; cadena vacía si no está."""
    m = re.search(rf"(?m)^## {re.escape(titulo)}\s*$", md)
    if not m:
        return ""
    siguiente = re.search(r"(?m)^## ", md[m.end():])
    return md[m.end(): m.end() + siguiente.start()] if siguiente else md[m.end():]


# ══ 3. El registro de lo citado ═════════════════════════════════════════════════
class Citas:
    """Cada valor que cita el informe, con su fichero, su camino, su redondeo y cómo se escribe."""

    def __init__(self, fuentes, docs):
        """`fuentes` es {fichero: JSON leído}; `docs`, {fichero: texto} de los documentos que se citan."""
        self.fuentes = fuentes
        self.docs = docs
        self.lista = []
        self._indice = {}

    def cita(self, fichero, camino, decimales=None, signo=False, tipo=None, operacion=None, valor=_LEER):
        """Registra un valor y devuelve cómo se escribe. Sin `valor`, lo lee del JSON por su camino."""
        dado = valor is not _LEER
        if not dado:
            valor = obtener(self.fuentes[fichero], camino)
        # Un valor dado (un recuento o una frase de un documento) entra en la clave: dos frases del mismo apartado
        # son dos citas
        clave = (fichero, camino, decimales, signo, tipo, operacion, json.dumps(valor, ensure_ascii=False) if dado
                 else None)
        if clave in self._indice:
            return self._indice[clave]["escrito"]
        escrito, redondeado = escribir(valor, decimales, signo, tipo)
        filas = None
        if fichero in self.fuentes and operacion is None:
            filas = filas_del_camino(self.fuentes[fichero], camino)
        es_cifra = isinstance(valor, (int, float)) and not isinstance(valor, bool)
        entrada = {"id": f"C-{len(self.lista) + 1:04d}", "fichero": fichero, "camino": camino,
                   "operacion": operacion, "valor": valor, "decimales": decimales, "signo": signo, "tipo": tipo,
                   "redondeado": redondeado, "escrito": escrito,
                   "filas": filas if filas or not es_cifra else "no aplica: no se mide sobre filas"}
        self.lista.append(entrada)
        self._indice[clave] = entrada
        return escrito

    def contar(self, fichero, camino, valor, que):
        """Registra un recuento de una lista del JSON (lo único que se calcula, con ordenar)."""
        return self.cita(fichero, camino, operacion=f"contar: {que}", valor=valor)


# ══ 4. Las comprobaciones (validaciones del script) ═══════════════════════════════
def entradas_en_error(fuentes):
    """Los JSON de entrada cuyo estado es ERROR."""
    return [rel for rel, d in fuentes.items() if (d.get("resultado") or {}).get("estado") == "ERROR"]


def citas_sin_origen(cifras):
    """Las citas sin fichero o sin camino."""
    return [c.get("id") for c in cifras if not c.get("fichero") or not c.get("camino")]


def normalizar(texto):
    """Un texto con los espacios y saltos de línea seguidos como un solo espacio."""
    return re.sub(r"\s+", " ", texto)


def citas_que_no_existen(cifras, fuentes, docs):
    """Las citas cuyo valor no es el que hay en su fichero (método, apartado 9, validación 7)."""
    malas = []
    for c in cifras:
        fichero, camino, valor = c.get("fichero"), c.get("camino"), c.get("valor")
        try:
            if fichero in fuentes:
                leido = obtener(fuentes[fichero], camino)
                operacion = c.get("operacion") or ""
                if operacion.startswith("contar"):
                    bien = isinstance(leido, (list, dict)) and isinstance(valor, int) and 0 <= valor <= len(leido)
                else:
                    bien = leido == valor
            elif fichero == SCRIPT_REL:
                bien = PARAMETROS.get(camino.removeprefix("PARAMETROS."), {}).get("valor") == valor
            elif fichero in docs:
                bien = normalizar(str(valor)) in normalizar(docs[fichero])
            else:
                bien = False
        except (KeyError, IndexError, TypeError):
            bien = False
        if not bien:
            malas.append(c.get("id"))
    return malas


def redondeo_distinto(cifras):
    """Las cifras cuyo texto no es el de su valor con el redondeo que guarda el JSON."""
    malas = []
    for c in cifras:
        if c.get("decimales") is None or not isinstance(c.get("valor"), (int, float)):
            continue
        texto, redondeado = escribir(c["valor"], c["decimales"], c.get("signo", False))
        if texto != c.get("escrito") or redondeado != c.get("redondeado"):
            malas.append(c.get("id"))
    return malas


def numeros_fuera_del_json(md, cifras):
    """Los números del informe que no están escritos así en ninguna cita de modelado.json."""
    permitidos = {t for c in cifras for t in tokens(str(c.get("escrito", "")))}
    limpio = md
    for patron in EXENTOS:
        limpio = re.sub(patron, " ", limpio)
    return [t for t in tokens(limpio) if t not in permitidos]


def apartados_en_orden(md):
    """Si los apartados «## » del informe son los catorce de resultado.md, en su orden."""
    return re.findall(r"(?m)^## (.+?)\s*$", md) == APARTADOS


def no_aplica_explicado(md, r):
    """Los apartados que no aplican y no lo explican: el desequilibrio y el corte tienen que estar, decir «no aplica»
    y llevar el motivo que dejaron los JSON."""
    fallos = []
    motivos = {"El desequilibrio": (r.get("desequilibrio") or {}).get("por_que"),
               "El corte": (r.get("corte") or {}).get("por_que")}
    for titulo, motivo in motivos.items():
        cuerpo = seccion(md, titulo)
        if not cuerpo.strip() or "no aplica" not in cuerpo.lower() or not motivo or motivo not in cuerpo:
            fallos.append(titulo)
    return fallos


def datos_personales_bien(md, existe):
    """Si el apartado de datos personales dice que falta la protección cuando falta (resultado.md, regla 6)."""
    cuerpo = seccion(md, "Datos personales")
    if existe:
        return f"`{PROTECCION_REL}`" in cuerpo
    return f"No existe `{PROTECCION_REL}`" in cuerpo and "no pasaron por la protección" in cuerpo


def abre_tablas_hechos(texto):
    """Las rutas a una tabla de hechos escritas en un código."""
    return PATRON_HECHOS.findall(texto)


def buscar_resultados_escritos(texto):
    """Las validaciones escritas con su resultado puesto (True o False) en un código (error 24)."""
    nombres = "|".join(NOMBRES_VALIDACION)
    patron = rf"[\"']({nombres})[\"']\s*(?:\]\s*=|:)\s*\(?\s*(?:True|False)\b"
    return re.findall(patron, texto)


def sin_coma_y(md):
    """Si el texto no une dos partes con «, y» (transmision-conocimiento §4)."""
    return ", y " not in md


def entradas_cambiadas(raiz, entradas):
    """Las entradas cuya huella ya no es la que tenían al leerlas."""
    return [e["ruta"] for e in entradas if not (raiz / e["ruta"]).exists() or huella(raiz / e["ruta"]) != e["sha256"]]


def figuras_completas(rutas):
    """Si están en disco las dos figuras de cada objetivo."""
    return len(rutas) == 2 * len(OBJETIVOS) and all(Path(p).exists() for p in rutas)


def eventos_sin_nombrar(md, r):
    """Los eventos que la validación no cubre (bloque «robustez») y que «Límites» no nombra."""
    limites = seccion(md, "Límites")
    nombres = [e["nombre"] for o in OBJETIVOS
               for e in r["informe"]["validacion"][o]["robustez"]["eventos"]["sin_cubrir"]]
    return [n for n in dict.fromkeys(nombres) if n not in limites]


def comprobar_md(md, r, existe_proteccion):
    """Las comprobaciones que se hacen sobre el texto del informe."""
    return {"numeros_en_el_json": not numeros_fuera_del_json(md, r["cifras"]),
            "apartados_en_orden": apartados_en_orden(md),
            "no_aplica_explicado": not no_aplica_explicado(md, r),
            "datos_personales_bien": datos_personales_bien(md, existe_proteccion),
            "sin_coma_y": sin_coma_y(md),
            "limites_nombran_eventos": not eventos_sin_nombrar(md, r)}


# ══ 5. Lectura ══════════════════════════════════════════════════════════════════
def leer_entradas(raiz):
    """Los siete JSON del paso 5 con su huella. Devuelve (fuentes, entradas, paradas)."""
    fuentes, entradas, paradas = {}, [], []
    for rel in ENTRADAS_JSON:
        ruta = raiz / rel
        if not ruta.exists():
            paradas.append(f"falta {rel}")
            continue
        fuentes[rel] = json.loads(ruta.read_text(encoding="utf-8"))
        entradas.append({"ruta": rel, "sha256": huella(ruta),
                         "estado": (fuentes[rel].get("resultado") or {}).get("estado"),
                         "fecha_datos": fuentes[rel].get("fecha_datos")})
    for rel in entradas_en_error(fuentes):
        paradas.append(f"{rel} está en ERROR: no se empieza")
    # El bloque «robustez» lo deja el script 16 desde el 25/11/2026: sin él, el informe no puede citarlo
    # El bloque «niveles», desde el 25/11/2026: sin él, el informe no puede citar la previsión sumada
    for bloque in ("robustez", "niveles"):
        sin_bloque = [o for o in OBJETIVOS if VALIDACION_REL in fuentes
                      and bloque not in ((fuentes[VALIDACION_REL].get("validacion") or {}).get(o) or {})]
        if sin_bloque:
            paradas.append(f"{VALIDACION_REL} no trae el bloque {bloque} de {', '.join(sin_bloque)}: ejecutar antes "
                           f"scripts/16_validacion.py")
    distintas = [e["ruta"] for e in entradas if e["fecha_datos"] != FECHA_DATOS]
    if distintas:
        paradas.append(f"fecha_datos distinta de {FECHA_DATOS} en {', '.join(distintas)}")
    return fuentes, entradas, paradas


def leer_documentos(raiz):
    """Los documentos que cita el informe: los planteamientos y las reglas de negocio."""
    docs = {}
    for rel in (PLANTEAMIENTOS_REL, REGLAS_REL):
        ruta = raiz / rel
        docs[rel] = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    return docs


def leer_previsiones(raiz):
    """La tabla de previsiones de la validación, solo con las columnas de las figuras."""
    columnas = ["objetivo", "real", "modelo", "fuera_del_error"]
    tabla = pd.read_parquet(raiz / PREVISIONES_REL, columns=columnas)
    tabla["fuera_del_error"] = tabla["fuera_del_error"].astype(bool)
    return tabla


def filas_de_figura(tabla, objetivo):
    """Las filas de un objetivo sin los días fuera del error, las mismas que midió la validación."""
    return tabla[(tabla["objetivo"] == objetivo) & ~tabla["fuera_del_error"]].reset_index(drop=True)


# ══ 6. Reunir lo que cita el informe ════════════════════════════════════════════
def indice(lista, **filtro):
    """La posición del primer elemento de una lista de diccionarios que cumple el filtro, o None."""
    return next((i for i, e in enumerate(lista) if all(e.get(k) == v for k, v in filtro.items())), None)


def la_que_menos_falla(lista, previsiones):
    """La posición de la previsión con menos error de una lista de errores, entre las dadas (ordenar)."""
    candidatas = [(e["error"], i) for i, e in enumerate(lista) if e["prevision"] in previsiones and e["error"] is not None]
    return min(candidatas)[1] if candidatas else None


def reunir_aprobado(C, cs, f):
    """Lo aprobado antes de entrenar."""
    mm, ps, va, pa = f[MINIMO_REL], f[PRESELECCION_REL], f[VARIABLES_REL], f[PARTICION_REL]
    partes = {}
    for nombre in ("entrenamiento", "validacion"):
        i = indice(pa["partes"], parte=nombre)
        base = f"partes[{i}]"
        partes[nombre] = {"filas": C(PARTICION_REL, f"{base}.filas"),
                          "desde": C(PARTICION_REL, f"{base}.fecha_min", tipo="fecha"),
                          "hasta": C(PARTICION_REL, f"{base}.fecha_max", tipo="fecha"),
                          "dias": C(PARTICION_REL, f"{base}.dias")}
    return {
        "hace_falta": C(MINIMO_REL, "hace_falta_modelar.respuesta"),
        "contestable": C(MINIMO_REL, "puerta_contestable.aplica"),
        "contestable_por_que": C(MINIMO_REL, "puerta_contestable.por_que"),
        "medida": C(MINIMO_REL, "aprobado_antes.medida_principal"),
        "medida_por_que": C(MINIMO_REL, "aprobado_antes.por_que"),
        "referencias": [C(MINIMO_REL, f"aprobado_antes.referencias[{i}]")
                        for i in range(len(mm["aprobado_antes"]["referencias"]))],
        "se_da_por_bueno": C(MINIMO_REL, "aprobado_antes.se_da_por_bueno"),
        "algoritmos": C(BUSQUEDA_REL, "aprobado_antes.algoritmos_y_busqueda"),
        "algoritmos_aprobado_por": C(BUSQUEDA_REL, "aprobado_antes.aprobado_por"),
        "ganador_aprobado_por": sorted({C(VALIDACION_REL, f"receta.ganador.{o}.aprobado_por") for o in OBJETIVOS}),
        "partes": partes,
        "quitadas": {k: C(VARIABLES_REL, f"filas_quitadas.{k}", tipo="fecha" if k in ("desde", "hasta") else None)
                     for k in ("filas_quitadas", "filas_despues", "desde", "hasta")},
        "preseleccion": {k: C(PRESELECCION_REL, k) for k in ("modo", "escenario", "escenario_fijado_en")},
        "variables_generadas": cs.contar(VARIABLES_REL, "variables_generadas", len(va["variables_generadas"]),
                                         "entradas de variables_generadas"),
        "variables_lista": [C(VARIABLES_REL, f"variables_generadas[{i}].columna")
                            for i in range(len(va["variables_generadas"]))],
        "ajuste_desde": C(BUSQUEDA_REL, "tabla.desde", tipo="fecha"),
        "ajuste_hasta": C(BUSQUEDA_REL, "tabla.hasta", tipo="fecha"),
        "ajuste_filas": C(BUSQUEDA_REL, "tabla.filas")}


def reunir_probado(C, cs, f):
    """Qué se probó y cuánto costó."""
    b = f[BUSQUEDA_REL]
    bq = b["busqueda"]
    espacio = [{k: C(BUSQUEDA_REL, f"busqueda.espacio[{i}].{k}") for k in
                ("objetivo", "algoritmo", "combinaciones", "probadas", "tipo")} for i in range(len(bq["espacio"]))]
    segundas = [{"objetivo": C(BUSQUEDA_REL, f"busqueda.segundas_busquedas[{i}].objetivo"),
                 "algoritmo": C(BUSQUEDA_REL, f"busqueda.segundas_busquedas[{i}].algoritmo"),
                 "mejora": C(BUSQUEDA_REL, f"busqueda.segundas_busquedas[{i}].mejora", 2, True),
                 "desviacion": C(BUSQUEDA_REL, f"busqueda.segundas_busquedas[{i}].desviacion", 2),
                 "se_sostiene": C(BUSQUEDA_REL, f"busqueda.segundas_busquedas[{i}].se_sostiene")}
                for i in range(len(bq["segundas_busquedas"]))]
    return {
        "minimo": {o: {"a_un_dia": C(MINIMO_REL, f"modelo_minimo.{o}.resumen.a_un_dia.error", 2),
                       "recursiva": C(MINIMO_REL, f"modelo_minimo.{o}.resumen.recursiva.error", 2)}
                   for o in OBJETIVOS},
        "cv_tipo": C(BUSQUEDA_REL, "validacion_cruzada.tipo"),
        "pliegues": C(BUSQUEDA_REL, "validacion_cruzada.pliegues"),
        "test_size": {o: C(BUSQUEDA_REL, f"validacion_cruzada.test_size.{o}") for o in OBJETIVOS},
        "origenes": {o: [C(BUSQUEDA_REL, f"validacion_cruzada.origenes.{o}[{i}]", tipo="fecha")
                         for i in range(len(b["validacion_cruzada"]["origenes"][o]))] for o in OBJETIVOS},
        "nivel": C(BUSQUEDA_REL, "busqueda.nivel"),
        "medida": C(BUSQUEDA_REL, "busqueda.medida"),
        "espacio": espacio,
        "modelos": C(BUSQUEDA_REL, "busqueda.modelos_de_la_busqueda"),
        "modelos_por": [(k, C(BUSQUEDA_REL, f"busqueda.modelos_por_objetivo_y_algoritmo.{k}"))
                        for k in bq["modelos_por_objetivo_y_algoritmo"]],
        "extra": [(k, C(BUSQUEDA_REL, f"busqueda.modelos_extra.{k}")) for k in bq["modelos_extra"]],
        "segundos_busqueda": C(BUSQUEDA_REL, "busqueda.segundos", 0),
        "segundos_validacion": C(VALIDACION_REL, "segundos", 0),
        "ampliadas": cs.contar(BUSQUEDA_REL, "busqueda.rejillas_ampliadas", len(bq["rejillas_ampliadas"]),
                               "todas las ampliaciones"),
        "ampliadas_medidas": cs.contar(BUSQUEDA_REL, "busqueda.rejillas_ampliadas",
                                       sum(1 for x in bq["rejillas_ampliadas"] if x.get("medido")),
                                       "ampliaciones con medido = true"),
        "segundas": segundas}


def reunir_ranking(C, f, nombre):
    """El ranking de cada objetivo con sus referencias y la comparación pliegue a pliegue."""
    b = f[BUSQUEDA_REL]
    salida = {}
    for o in OBJETIVOS:
        algoritmos = []
        for i, x in enumerate(b["ranking"]):
            if x["objetivo"] != o:
                continue
            base = f"ranking[{i}]"
            algoritmos.append({"algoritmo": C(BUSQUEDA_REL, f"{base}.algoritmo"),
                               "error": C(BUSQUEDA_REL, f"{base}.cv_media", 2),
                               "desviacion": C(BUSQUEDA_REL, f"{base}.cv_desviacion", 2),
                               "sesgo": C(BUSQUEDA_REL, f"{base}.sesgo_media", 2, True),
                               "entrenamiento": C(BUSQUEDA_REL, f"{base}.entrenamiento.error", 2),
                               "gana": C(BUSQUEDA_REL, f"{base}.cortes_que_gana_a_la_regla_que_menos_falla"),
                               "filas": C(BUSQUEDA_REL, f"{base}.filas"),
                               "filas_entrenamiento": C(BUSQUEDA_REL, f"{base}.entrenamiento.filas")})
        referencias = []
        for i, x in enumerate(b["referencias_cv"]):
            if x["objetivo"] != o:
                continue
            base = f"referencias_cv[{i}]"
            referencias.append({"nombre": nombre(x["nombre"]), "error": C(BUSQUEDA_REL, f"{base}.cv_media", 2),
                                "sesgo": C(BUSQUEDA_REL, f"{base}.sesgo_media", 2, True)})
        comp = f"comparacion.{o}"
        salida[o] = {"algoritmos": algoritmos, "referencias": referencias,
                     "comparacion": {"media": C(BUSQUEDA_REL, f"{comp}.media", 2, True),
                                     "desviacion": C(BUSQUEDA_REL, f"{comp}.desviacion", 2),
                                     "empate": C(BUSQUEDA_REL, f"{comp}.empate")}}
    return salida


def reunir_ganador(C, f, n_importancias):
    """El ganador, la regla simple, el canario y las importancias de cada objetivo."""
    b = f[BUSQUEDA_REL]
    ganador, importancias = {}, {}
    for o in OBJETIVOS:
        g = f"ganador.{o}"
        rs = f"regla_simple.{o}"
        ganador[o] = {
            "algoritmo": C(BUSQUEDA_REL, f"{g}.algoritmo"),
            "buscados": [(k, C(BUSQUEDA_REL, f"{g}.buscados.{k}")) for k in b["ganador"][o]["buscados"]],
            "semilla": C(BUSQUEDA_REL, f"{g}.semilla"),
            "columnas": C(BUSQUEDA_REL, f"{g}.n_columnas"),
            "por_que": C(BUSQUEDA_REL, f"{g}.por_que"),
            "ficha": C(BUSQUEDA_REL, f"{g}.ficha"),
            "reajuste": C(BUSQUEDA_REL, f"{g}.reajuste.filas_ajuste"),
            "regla_simple": {"variables": [C(BUSQUEDA_REL, f"{rs}.variables[{i}]")
                                           for i in range(len(b["regla_simple"][o]["variables"]))],
                             "error": C(BUSQUEDA_REL, f"{rs}.recursiva.error", 2),
                             "media": C(BUSQUEDA_REL, f"{rs}.comparacion_con_el_ganador.media", 2, True),
                             "desviacion": C(BUSQUEDA_REL, f"{rs}.comparacion_con_el_ganador.desviacion", 2),
                             "supera": C(BUSQUEDA_REL, f"{rs}.el_ganador_la_supera")},
            "canario": {"barajado": C(BUSQUEDA_REL, f"canario.{o}.barajado.error", 2),
                        "fuga": C(BUSQUEDA_REL, f"canario.{o}.fuga.error", 2),
                        "limite": C(BUSQUEDA_REL, f"canario.{o}.limite_fuga")}}
        imp = b["importancias"][o]
        orden = sorted(range(len(imp["valores"])), key=lambda i: -imp["valores"][i]["importancia"])
        base = f"importancias.{o}"
        importancias[o] = {
            "metodo": C(BUSQUEDA_REL, f"{base}.metodo"), "filas": C(BUSQUEDA_REL, f"{base}.filas"),
            "puntuacion": C(BUSQUEDA_REL, f"{base}.puntuacion"),
            "peso_dos": C(BUSQUEDA_REL, f"{base}.peso_de_las_dos_primeras", 2),
            "total": C(BUSQUEDA_REL, f"{base}.valores", operacion="contar: variables de origen medidas",
                       valor=len(imp["valores"])),
            "primeras": [{"columna": C(BUSQUEDA_REL, f"{base}.valores[{i}].columna"),
                          "importancia": C(BUSQUEDA_REL, f"{base}.valores[{i}].importancia", 2),
                          "desviacion": C(BUSQUEDA_REL, f"{base}.valores[{i}].desviacion", 2)}
                         for i in orden[:n_importancias]]}
    return ganador, importancias


def reunir_lista_errores(C, lista, base, nombre):
    """Una lista de errores de validacion.json: el modelo y la regla que menos falla en esas filas (ordenar)."""
    im = indice(lista, prevision="modelo")
    ir = la_que_menos_falla(lista, REGLAS)
    return {"modelo_error": C(VALIDACION_REL, f"{base}[{im}].error", 2),
            "modelo_sesgo": C(VALIDACION_REL, f"{base}[{im}].sesgo", 2, True),
            "filas": C(VALIDACION_REL, f"{base}[{im}].filas"),
            "regla": nombre(lista[ir]["prevision"]),
            "regla_error": C(VALIDACION_REL, f"{base}[{ir}].error", 2)}


def reunir_robustez(C, cs, f, o):
    """Lo que matiza la ventaja de un objetivo, citado del bloque «robustez» de validacion.json; no calcula nada."""
    x = f[VALIDACION_REL]["validacion"][o]["robustez"]
    rb = f"validacion.{o}.robustez"
    ap, vs, it = f"{rb}.aporte_por_serie", f"{rb}.ventaja_sin", f"{rb}.intervalo_por_tienda"
    me, ev, di = f"{rb}.series_con_alguna_regla_mejor", f"{rb}.eventos", f"{rb}.filas_por_dia_de_la_semana"

    def serie(camino):
        """Una serie escrita como «tienda departamento», con sus dos claves citadas."""
        return f"{C(VALIDACION_REL, f'{camino}.store_id')} {C(VALIDACION_REL, f'{camino}.dept_id')}"

    def sin(camino, nodo):
        """La ventaja sin unas tiendas, o el motivo por el que no se calculó."""
        return {"quitar": [C(VALIDACION_REL, f"{camino}.quitar[{i}]") for i in range(len(nodo["quitar"]))],
                "ventaja": C(VALIDACION_REL, f"{camino}.ventaja", 2), "valor": nodo["ventaja"],
                "motivo": C(VALIDACION_REL, f"{camino}.motivo") if nodo.get("motivo") else None}

    a = x["aporte_por_serie"]
    return {
        "n_primeras": cs.contar(VALIDACION_REL, f"{ap}.cinco_primeras", len(a["cinco_primeras"]), "series"),
        "primeras": [{"serie": serie(f"{ap}.cinco_primeras[{i}]"),
                      "aporte": C(VALIDACION_REL, f"{ap}.cinco_primeras[{i}].aporte", 2)}
                     for i in range(len(a["cinco_primeras"]))],
        "aporte_primeras": C(VALIDACION_REL, f"{ap}.aporte_cinco_primeras", 2),
        "ventaja": C(VALIDACION_REL, f"{ap}.ventaja", 2), "ventaja_valor": a["ventaja"],
        "n_series": cs.contar(VALIDACION_REL, f"{ap}.series", len(a["series"]), "series"),
        "cada_tienda": [sin(f"{vs}.cada_tienda[{i}]", t) for i, t in enumerate(x["ventaja_sin"]["cada_tienda"])],
        "juntas": sin(f"{vs}.juntas", x["ventaja_sin"]["juntas"]),
        "intervalo": {k: C(VALIDACION_REL, f"{it}.{k}", 2) for k in ("bajo", "alto")}
        | {k: C(VALIDACION_REL, f"{it}.{k}") for k in ("remuestreos", "unidades", "semilla", "que_se_remuestrea")},
        "mejores": {"cuantas": C(VALIDACION_REL, f"{me}.cuantas"), "de": C(VALIDACION_REL, f"{me}.de"),
                    "series": [serie(f"{me}.series[{i}]") for i in range(len(x["series_con_alguna_regla_mejor"]
                                                                              ["series"]))]},
        "eventos": {"cuantos": C(VALIDACION_REL, f"{ev}.cuantos"), "cubiertos": C(VALIDACION_REL, f"{ev}.cubiertos"),
                    "desde": C(VALIDACION_REL, f"{ev}.desde", tipo="fecha"),
                    "hasta": C(VALIDACION_REL, f"{ev}.hasta", tipo="fecha"),
                    "sin_cubrir": [{"nombre": C(VALIDACION_REL, f"{ev}.sin_cubrir[{i}].nombre"),
                                    "motivo": C(VALIDACION_REL, f"{ev}.sin_cubrir[{i}].motivo")}
                                   for i in range(len(x["eventos"]["sin_cubrir"]))]},
        "dias": [{"dia": C(VALIDACION_REL, f"{di}.dias[{i}].dia"), "filas": C(VALIDACION_REL, f"{di}.dias[{i}].filas")}
                 for i in range(len(x["filas_por_dia_de_la_semana"]["dias"]))]}


def reunir_niveles(C, cs, f, o, nombre):
    """La previsión sumada de un objetivo, citada del bloque «niveles» de validacion.json; no calcula nada. Los niveles,
    de lo general a lo concreto: cadena, estado, tienda y categoría."""
    x = f[VALIDACION_REL]["validacion"][o]["niveles"]
    nv = f"validacion.{o}.niveles"
    salida = {}
    for nivel in NIVELES:
        grupos = []
        for i, g in enumerate(x[nivel]["grupos"]):
            gb = f"{nv}.{nivel}.grupos[{i}]"
            grupos.append({
                "grupo": C(VALIDACION_REL, f"{gb}.grupo"), "series": C(VALIDACION_REL, f"{gb}.series"),
                "filas_sumadas": C(VALIDACION_REL, f"{gb}.filas_sumadas"),
                "error_modelo": C(VALIDACION_REL, f"{gb}.error_modelo", 2),
                "sesgo_modelo": C(VALIDACION_REL, f"{gb}.sesgo_modelo", 2, True),
                "regla": C(VALIDACION_REL, f"{gb}.regla_que_menos_falla_nombre"),
                "error_regla": C(VALIDACION_REL, f"{gb}.error_regla", 2),
                "modelo_falla_menos": C(VALIDACION_REL, f"{gb}.modelo_falla_menos"),
                "errores": [{"nombre": nombre(e["prevision"]),
                             "error": C(VALIDACION_REL, f"{gb}.errores[{j}].error", 2),
                             "sesgo": C(VALIDACION_REL, f"{gb}.errores[{j}].sesgo", 2, True)}
                            for j, e in enumerate(g["errores"])]})
        salida[nivel] = {"grupos": grupos,
                         "cuantos": cs.contar(VALIDACION_REL, f"{nv}.{nivel}.grupos", len(x[nivel]["grupos"]), "grupos")}
    co = f"{nv}.cadena.origenes"
    salida["origenes"] = {"gana": C(VALIDACION_REL, f"{co}.origenes_que_gana"), "de": C(VALIDACION_REL, f"{co}.de")}
    return salida


def reunir_validacion(C, cs, f, nombre):
    """La validación de cada objetivo: veredicto, errores, recomendación, días, horizonte, MASE, tramos y distancia."""
    v = f[VALIDACION_REL]
    salida = {}
    for o in OBJETIVOS:
        x = v["validacion"][o]
        base = f"validacion.{o}"
        ve, iv = f"{base}.veredicto", f"{base}.veredicto.intervalo"
        su = f"{base}.suavizado"
        veredicto = {k: C(VALIDACION_REL, f"{ve}.{k}") for k in ("origenes_que_gana", "de", "minimo", "veredicto")}
        veredicto.update({"ventaja": C(VALIDACION_REL, f"{ve}.ventaja", 2, True),
                          "error_modelo": C(VALIDACION_REL, f"{ve}.error_modelo", 2),
                          "error_rival": C(VALIDACION_REL, f"{ve}.error_rival", 2),
                          "bajo": C(VALIDACION_REL, f"{iv}.bajo", 2, True),
                          "alto": C(VALIDACION_REL, f"{iv}.alto", 2, True),
                          "remuestreos": C(VALIDACION_REL, f"{iv}.remuestreos"),
                          "unidades": C(VALIDACION_REL, f"{iv}.unidades"),
                          "semilla": C(VALIDACION_REL, f"{iv}.semilla"),
                          "que_se_remuestrea": C(VALIDACION_REL, f"{iv}.que_se_remuestrea"),
                          "medida": C(VALIDACION_REL, f"{iv}.medida"),
                          "cumple_origenes": x["veredicto"]["origenes_que_gana"] >= x["veredicto"]["minimo"],
                          "cumple_intervalo": x["veredicto"]["intervalo"]["bajo"] > 0})
        todas = [{"nombre": nombre(e["prevision"]), "error": C(VALIDACION_REL, f"{base}.errores.todas[{i}].error", 2),
                  "sesgo": C(VALIDACION_REL, f"{base}.errores.todas[{i}].sesgo", 2, True)}
                 for i, e in enumerate(x["errores"]["todas"])]
        suavizado = {k: C(VALIDACION_REL, f"{su}.{k}") for k in ("origenes_que_gana", "de", "lectura")}
        suavizado.update({"ventaja": C(VALIDACION_REL, f"{su}.ventaja", 2, True),
                          "bajo": C(VALIDACION_REL, f"{su}.intervalo.bajo", 2, True),
                          "alto": C(VALIDACION_REL, f"{su}.intervalo.alto", 2, True)})
        recomendacion = []
        for i, d in enumerate(x["recomendacion_por_departamento"]):
            rb = f"{base}.recomendacion_por_departamento[{i}]"
            recomendacion.append({"departamento": C(VALIDACION_REL, f"{rb}.departamento"),
                                  "modelo": C(VALIDACION_REL, f"{rb}.error_modelo", 2),
                                  "regla": C(VALIDACION_REL, f"{rb}.regla_que_menos_falla_nombre"),
                                  "regla_error": C(VALIDACION_REL, f"{rb}.error_regla", 2),
                                  "se_recomienda": C(VALIDACION_REL, f"{rb}.se_recomienda")})
        n_modelo = cs.contar(VALIDACION_REL, f"{base}.recomendacion_por_departamento",
                             sum(1 for d in x["recomendacion_por_departamento"] if d["se_recomienda"] == "el modelo"),
                             "departamentos con se_recomienda = el modelo")
        n_dep = cs.contar(VALIDACION_REL, f"{base}.recomendacion_por_departamento",
                          len(x["recomendacion_por_departamento"]), "departamentos")
        dias = {}
        for clave in DIAS:
            dias[clave] = reunir_lista_errores(C, x["errores"][clave], f"{base}.errores.{clave}", nombre)
        por_h = []
        for h in sorted({e["grupo"] for e in x["errores"]["por_h"]}):
            lista = [e for e in x["errores"]["por_h"] if e["grupo"] == h]
            posiciones = [i for i, e in enumerate(x["errores"]["por_h"]) if e["grupo"] == h]
            im = posiciones[indice(lista, prevision="modelo")]
            ir = posiciones[la_que_menos_falla(lista, REGLAS)]
            lb = f"{base}.errores.por_h"
            por_h.append({"h": C(VALIDACION_REL, f"{lb}[{im}].grupo"),
                          "modelo_error": C(VALIDACION_REL, f"{lb}[{im}].error", 2),
                          "modelo_sesgo": C(VALIDACION_REL, f"{lb}[{im}].sesgo", 2, True),
                          "regla": nombre(x["errores"]["por_h"][ir]["prevision"]),
                          "regla_error": C(VALIDACION_REL, f"{lb}[{ir}].error", 2)})
        por_tienda = []
        for t in sorted({e["grupo"] for e in x["errores"]["por_tienda"]}):
            posiciones = [i for i, e in enumerate(x["errores"]["por_tienda"]) if e["grupo"] == t]
            lista = [x["errores"]["por_tienda"][i] for i in posiciones]
            im = posiciones[indice(lista, prevision="modelo")]
            ir = posiciones[la_que_menos_falla(lista, REGLAS)]
            lb = f"{base}.errores.por_tienda"
            por_tienda.append({"tienda": C(VALIDACION_REL, f"{lb}[{im}].grupo"),
                               "modelo_error": C(VALIDACION_REL, f"{lb}[{im}].error", 2),
                               "regla": nombre(x["errores"]["por_tienda"][ir]["prevision"]),
                               "regla_error": C(VALIDACION_REL, f"{lb}[{ir}].error", 2)})
        mase = [{"nombre": nombre(p), "valor": C(VALIDACION_REL, f"{base}.mase.valores.{p}", 2)}
                for p in x["mase"]["valores"]]
        tramos = [{"tramo": C(VALIDACION_REL, f"{base}.error_por_tramo.tabla[{i}].tramo"),
                   "filas": C(VALIDACION_REL, f"{base}.error_por_tramo.tabla[{i}].filas"),
                   "real_medio": C(VALIDACION_REL, f"{base}.error_por_tramo.tabla[{i}].real_medio", 2),
                   "previsto_medio": C(VALIDACION_REL, f"{base}.error_por_tramo.tabla[{i}].previsto_medio", 2),
                   "mae": C(VALIDACION_REL, f"{base}.error_por_tramo.tabla[{i}].mae", 2),
                   "sesgo": C(VALIDACION_REL, f"{base}.error_por_tramo.tabla[{i}].sesgo", 2, True)}
                  for i in range(len(x["error_por_tramo"]["tabla"]))]
        pieza = [{"lado": e["lado"], "mae": C(VALIDACION_REL, f"{base}.desarrollo_frente_a_validacion.pieza[{i}].mae", 2),
                  "rmse": C(VALIDACION_REL, f"{base}.desarrollo_frente_a_validacion.pieza[{i}].rmse", 2),
                  "r2": C(VALIDACION_REL, f"{base}.desarrollo_frente_a_validacion.pieza[{i}].r2", 3)}
                 for i, e in enumerate(x["desarrollo_frente_a_validacion"]["pieza"])]
        dv = f"{base}.desarrollo_frente_a_validacion"
        di = f"distancia.{o}"
        medidas = [{"nombre": nombre(e["prevision"]),
                    "mae": C(VALIDACION_REL, f"{base}.medidas_pieza.tabla[{i}].mae", 2),
                    "rmse": C(VALIDACION_REL, f"{base}.medidas_pieza.tabla[{i}].rmse", 2),
                    "r2": C(VALIDACION_REL, f"{base}.medidas_pieza.tabla[{i}].r2", 3)}
                   for i, e in enumerate(x["medidas_pieza"]["tabla"])]
        ic = indice(x["sesgo_dias_cero"], prevision="modelo")
        salida[o] = {
            "horizonte": C(VALIDACION_REL, f"{base}.horizonte"), "horizonte_valor": x["horizonte"],
            "origenes": cs.contar(VALIDACION_REL, f"{base}.origenes", len(x["origenes"]), "orígenes"),
            "filas_medidas": C(VALIDACION_REL, f"{base}.filas_medidas"),
            "filas_fuera": C(VALIDACION_REL, f"{base}.filas_fuera_del_error"),
            "dias_fuera": [C(VALIDACION_REL, f"{base}.dias_fuera_del_error[{i}]", tipo="fecha")
                           for i in range(len(x["dias_fuera_del_error"]))],
            "dias_por_serie": C(VALIDACION_REL, f"{base}.dias_previstos_por_serie"),
            "primer_dia": C(VALIDACION_REL, f"{base}.primer_dia_previsto", tipo="fecha"),
            "ultimo_dia": C(VALIDACION_REL, f"{base}.ultimo_dia_previsto", tipo="fecha"),
            "filas_todas": C(VALIDACION_REL, f"{base}.errores.todas[0].filas"),
            "trivial_como": C(VALIDACION_REL, f"{base}.trivial.como"),
            "veredicto": veredicto, "todas": todas, "suavizado": suavizado,
            "recomendacion": recomendacion, "n_modelo": n_modelo, "n_departamentos": n_dep,
            "dias": dias, "por_h": por_h, "por_tienda": por_tienda,
            "mase": mase, "mase_escala": C(VALIDACION_REL, f"{base}.mase.escala"),
            "tramos": tramos, "tramos_filas": C(VALIDACION_REL, f"{base}.error_por_tramo.filas"),
            "medidas": medidas,
            "desarrollo": {"entrenamiento": C(VALIDACION_REL, f"{dv}.entrenamiento.error", 2),
                           "entrenamiento_filas": C(VALIDACION_REL, f"{dv}.entrenamiento.filas"),
                           "validacion": C(VALIDACION_REL, f"{dv}.validacion.error", 2),
                           "pieza": pieza, "pieza_filas": C(VALIDACION_REL, f"{dv}.pieza_filas"),
                           "cv_entrenamiento": C(BUSQUEDA_REL, f"{di}.entrenamiento.error", 2),
                           "cv_a_un_dia": C(BUSQUEDA_REL, f"{di}.a_un_dia.error", 2),
                           "cv_recursiva": C(BUSQUEDA_REL, f"{di}.recursiva.error", 2),
                           "lectura": C(BUSQUEDA_REL, f"{di}.lectura")},
            "dias_cero": {"sesgo": C(VALIDACION_REL, f"{base}.sesgo_dias_cero[{ic}].sesgo_medio_por_fila", 2, True),
                          "unidad": C(VALIDACION_REL, f"{base}.sesgo_dias_cero[{ic}].unidad"),
                          "filas": C(VALIDACION_REL, f"{base}.sesgo_dias_cero[{ic}].filas")},
            "canario": {"barajado": C(VALIDACION_REL, f"{base}.canario.barajado.error", 2),
                        "fuga": C(VALIDACION_REL, f"{base}.canario.fuga.error", 2),
                        "limite": C(VALIDACION_REL, f"{base}.canario.limite_fuga")},
            "reajuste": C(VALIDACION_REL, f"{base}.reajuste.filas"),
            "robustez": reunir_robustez(C, cs, f, o), "niveles": reunir_niveles(C, cs, f, o, nombre)}
    # Las lecturas que el script 16 dejó en «parametros»: umbrales para leer, que no deciden nada
    lecturas = {}
    for clave, texto in (("fuga", "límite de la sospecha de fuga"), ("ventaja", "ventaja que se revisa"),
                         ("dias_cero", "sesgo en los días a cero")):
        i = indice(v["parametros"], nombre=texto)
        if i is not None:
            lecturas[clave] = {"nombre": C(VALIDACION_REL, f"parametros[{i}].nombre"),
                               "valor": C(VALIDACION_REL, f"parametros[{i}].valor"),
                               "origen": C(VALIDACION_REL, f"parametros[{i}].origen"),
                               "numero": v["parametros"][i]["valor"]}
    if "ventaja" in lecturas:
        for o in OBJETIVOS:
            salida[o]["ventaja_por_debajo_de_revisar"] = (
                v["validacion"][o]["veredicto"]["ventaja"] < lecturas["ventaja"]["numero"])
    if "fuga" in lecturas:
        for o in OBJETIVOS:
            salida[o]["error_por_encima_de_fuga"] = (
                v["validacion"][o]["veredicto"]["error_modelo"] > lecturas["fuga"]["numero"])
    salida["lecturas"] = {k: {kk: vv for kk, vv in x.items() if kk != "numero"} for k, x in lecturas.items()}
    salida["series"] = C(VALIDACION_REL, "series.cuantas")
    salida["muestra"] = C(VALIDACION_REL, "series.muestra")
    salida["valores_previsiones"] = C(VALIDACION_REL, "previsiones.valores")
    salida["sospechas"] = cs.contar(VALIDACION_REL, "sospechas", len(v["sospechas"]), "sospechas apuntadas")
    return salida


def candidatas_sin_crear(variables):
    """Las candidatas de los planteamientos §2, decisión 7, que no están en variables_modelo.json: un retardo y una
    media por cada valor de sus «parametros», en los dos objetivos, y la llegada de productos nuevos (cuestión 001)."""
    parametros = {p["nombre"]: p["valor"] for p in variables.get("parametros", [])}
    esperadas = [f"{o}_lag_{x}" for o in OBJETIVOS for x in parametros.get("retardos", [])]
    esperadas += [f"{o}_media_{x}" for o in OBJETIVOS for x in parametros.get("ventanas de las medias", [])]
    esperadas.append("productos_con_precio_semana_anterior")
    creadas = {v["columna"] for v in variables.get("variables_generadas", [])}
    return [x for x in esperadas if x not in creadas]


def reunir_vias(C, cs, f):
    """Las tres vías de mejora, como mejoras posibles: el modelo se da por bueno (método, apartado 8, último párrafo)."""
    b, ps, pr, va = f[BUSQUEDA_REL], f[PRESELECCION_REL], f[PREPARACION_REL], f[VARIABLES_REL]
    bq = b["busqueda"]
    sin_probar = [{"objetivo": C(BUSQUEDA_REL, f"busqueda.espacio[{i}].objetivo"),
                   "algoritmo": C(BUSQUEDA_REL, f"busqueda.espacio[{i}].algoritmo"),
                   "probadas": C(BUSQUEDA_REL, f"busqueda.espacio[{i}].probadas"),
                   "combinaciones": C(BUSQUEDA_REL, f"busqueda.espacio[{i}].combinaciones")}
                  for i, e in enumerate(bq["espacio"]) if e["probadas"] < e["combinaciones"]]
    imposibles = [{"objetivo": C(BUSQUEDA_REL, f"busqueda.rejillas_ampliadas[{i}].objetivo"),
                   "hiperparametro": C(BUSQUEDA_REL, f"busqueda.rejillas_ampliadas[{i}].hiperparametro"),
                   "lado": C(BUSQUEDA_REL, f"busqueda.rejillas_ampliadas[{i}].lado"),
                   "motivo": C(BUSQUEDA_REL, f"busqueda.rejillas_ampliadas[{i}].imposible")}
                  for i, e in enumerate(bq["rejillas_ampliadas"]) if e.get("imposible")]
    algoritmos_con_rejilla = [k for k in bq.get("rejillas", {}) if k not in {x["algoritmo"] for x in b["ranking"]}]
    no_sostenidas = cs.contar(BUSQUEDA_REL, "busqueda.segundas_busquedas",
                              sum(1 for x in bq["segundas_busquedas"] if not x.get("se_sostiene")),
                              "segundas búsquedas con se_sostiene = false")
    # La llegada de productos nuevos (cuestión 001): creada, y en cada objetivo qué pasó con ella
    llegada = {}
    for o in OBJETIVOS:
        tabla = ps["objetivos"][o]["tabla_decisiones"]
        i = indice(tabla, origen="productos_con_precio_semana_anterior")
        j = indice(b["importancias"][o]["valores"], columna="productos_con_precio_semana_anterior")
        llegada[o] = {"ridge": C(PRESELECCION_REL, f"objetivos.{o}.tabla_decisiones[{i}].Ridge") if i is not None
                      else None,
                      "hgb": C(PRESELECCION_REL, f"objetivos.{o}.tabla_decisiones[{i}].HistGradientBoosting")
                      if i is not None else None,
                      "importancia": C(BUSQUEDA_REL, f"importancias.{o}.valores[{j}].importancia", 2)
                      if j is not None else None}
    k = indice(va["variables_generadas"], columna="productos_con_precio_semana_anterior")
    llegada["formula"] = C(VARIABLES_REL, f"variables_generadas[{k}].formula") if k is not None else None
    opciones = ps.get("pendientes", [{}])[0].get("opciones", []) if ps.get("pendientes") else []
    io = next((i for i, x in enumerate(opciones) if x.startswith("evento_<nombre>")), None)
    eventos = C(PRESELECCION_REL, f"pendientes[0].opciones[{io}]") if io is not None else None
    fuera = [{"variable": C(PREPARACION_REL, f"fuera[{i}].variable"),
              "motivo": C(PREPARACION_REL, f"fuera[{i}].motivo")} for i in range(len(pr["fuera"]))]
    informacion = [{"dato": x["dato"], "para_que": x["para_que"],
                    "frase": C(REGLAS_REL, SECCION_NO_SE_PUEDE, valor=x["frase"]),
                    "quien_lo_tiene": "no se puede saber con las fuentes del caso"}
                   for x in INFORMACION_NUEVA]
    return {"sin_probar": sin_probar, "imposibles": imposibles, "con_rejilla_sin_entrar": algoritmos_con_rejilla,
            "sin_crear": candidatas_sin_crear(va),
            "algoritmos": C(BUSQUEDA_REL, "aprobado_antes.algoritmos_y_busqueda"),
            "no_sostenidas": no_sostenidas,
            "n_segundas": cs.contar(BUSQUEDA_REL, "busqueda.segundas_busquedas", len(bq["segundas_busquedas"]),
                                    "segundas búsquedas"),
            "modelo_por_serie": C(PLANTEAMIENTOS_REL, "§2, decisión 6", valor=MODELO_POR_SERIE),
            "llegada": llegada, "eventos": eventos, "fuera": fuera, "informacion": informacion}


def reunir(fuentes, docs, existe_proteccion, figuras):
    """El diccionario de todo lo que cita el informe, con cada valor registrado con su origen."""
    cs = Citas(fuentes, docs)
    C = cs.cita
    v = fuentes[VALIDACION_REL]
    # Los nombres de las reglas con cifras en el nombre se citan del JSON que los trae
    nombres = {}
    for o in OBJETIVOS:
        for i, d in enumerate(v["validacion"][o]["recomendacion_por_departamento"]):
            nombres[d["regla_que_menos_falla"]] = C(
                VALIDACION_REL, f"validacion.{o}.recomendacion_por_departamento[{i}].regla_que_menos_falla_nombre")

    def nombre(p):
        """El nombre de una previsión, citado si lo trae el JSON."""
        return nombres.get(p, NOMBRE.get(p, p))

    n_importancias = PARAMETROS["importancias que se enseñan"]["valor"]
    informe = {"cabecera": {"fecha_datos": C(VALIDACION_REL, "fecha_datos", tipo="fecha"),
                            "aprobacion": C(PLANTEAMIENTOS_REL, SECCION_VEREDICTO, valor=APROBACION_VEREDICTO)},
               "aprobado": reunir_aprobado(C, cs, fuentes),
               "probado": reunir_probado(C, cs, fuentes),
               "desequilibrio": {"busqueda": C(BUSQUEDA_REL, "desequilibrio.por_que"),
                                 "particion": C(PARTICION_REL, "objetivo.nota"),
                                 "recalibrado": C(VALIDACION_REL, "validaciones_nulas.recalibrado_si_hace_falta")},
               "ranking": reunir_ranking(C, fuentes, nombre),
               "pliegues": C(BUSQUEDA_REL, "validacion_cruzada.pliegues")}
    informe["ganador"], informe["importancias"] = reunir_ganador(C, fuentes, n_importancias)
    informe["validacion"] = reunir_validacion(C, cs, fuentes, nombre)
    informe["corte"] = {"motivo": C(VALIDACION_REL, "validaciones_nulas.con_probabilidad"),
                        "probabilidad": C(VALIDACION_REL, "validaciones_nulas.probabilidad_media_cerca_de_la_tasa")}
    informe["vias"] = reunir_vias(C, cs, fuentes)
    # Las validaciones de los pasos 15 y 16, contadas
    pasos = {}
    for rel in (BUSQUEDA_REL, VALIDACION_REL):
        val = fuentes[rel].get("validaciones", {})
        nulas = fuentes[rel].get("validaciones_nulas", {})
        pasos[rel] = {"en_verde": cs.contar(rel, "validaciones", sum(1 for x in val.values() if x is True),
                                            "validaciones a true"),
                      "comprobadas": cs.contar(rel, "validaciones", sum(1 for x in val.values() if x is not None),
                                               "validaciones que no son null"),
                      "nulas": [(k, C(rel, f"validaciones_nulas.{k}")) for k, x in nulas.items()
                                if val.get(k) is None and isinstance(x, str)]}
    informe["pasos"] = pasos
    # Los parámetros: los de este script y los que dejaron la búsqueda y la validación
    propios = [{"nombre": k, "valor": C(SCRIPT_REL, f"PARAMETROS.{k}", valor=x["valor"]), "origen": x["origen"]}
               for k, x in PARAMETROS.items()]
    heredados = []
    for rel in (BUSQUEDA_REL, VALIDACION_REL):
        for i in range(len(fuentes[rel].get("parametros", []))):
            heredados.append({"paso": rel, "nombre": C(rel, f"parametros[{i}].nombre"),
                              "valor": C(rel, f"parametros[{i}].valor"), "origen": C(rel, f"parametros[{i}].origen")})
    informe["parametros"] = {"propios": propios, "heredados": heredados}
    informe["datos_personales"] = {"existe": existe_proteccion,
                                   "columnas": C(VALIDACION_REL, "datos_personales.columnas_de_personas_usadas")}
    informe["figuras"] = [dict(x, filas_escrito=C(VALIDACION_REL, f"validacion.{x['objetivo']}.filas_medidas"))
                          for x in figuras]
    return cs, informe


# ══ 7. Lo propio de modelado.json (resultado.md) ══════════════════════════════════
def lo_propio(f, informe):
    """Las claves de resultado.md, copiadas de los JSON de origen con su fuente; nada se recalcula."""
    mm, b, v, pa = f[MINIMO_REL], f[BUSQUEDA_REL], f[VALIDACION_REL], f[PARTICION_REL]
    validacion = {}
    for o in OBJETIVOS:
        x = v["validacion"][o]
        validacion[o] = {"fuente": f"{VALIDACION_REL}, validacion.{o}", "abierta_una_vez":
                         v.get("validaciones", {}).get("validacion_una_vez"), "pieza": "assets/evaluacion_continua.py",
                         "filas": x["filas_medidas"], "veredicto": x["veredicto"], "errores": x["errores"]["todas"],
                         "suavizado": x["suavizado"], "recomendacion_por_departamento": x["recomendacion_por_departamento"],
                         "desarrollo_frente_a_validacion": x["desarrollo_frente_a_validacion"],
                         "intervalo": x["veredicto"]["intervalo"], "robustez": x["robustez"],
                         "niveles": x["niveles"],
                         "se_da_por_bueno": x["veredicto"]["veredicto"] == "gana",
                         "frente_al_trivial": "supera" if x["veredicto"]["veredicto"] == "gana" else
                         x["veredicto"]["veredicto"],
                         "errores_por_segmento": {"por_departamento": "recomendacion_por_departamento",
                                                  "por_tramo": x["error_por_tramo"]}}
    return {
        "rama": v.get("rama"),
        "hace_falta_modelar": dict(mm["hace_falta_modelar"], fuente=MINIMO_REL),
        "puerta_contestable": dict(mm["puerta_contestable"], fuente=MINIMO_REL),
        "aprobado_antes": dict(mm["aprobado_antes"], fuente_json=MINIMO_REL),
        "validacion_cruzada": dict(b["validacion_cruzada"], fuente=BUSQUEDA_REL),
        "desequilibrio": dict(b["desequilibrio"], fuente=BUSQUEDA_REL, metodo=None, recalibracion=None),
        "busqueda": dict(b["busqueda"], fuente=BUSQUEDA_REL),
        "ranking": b["ranking"], "referencias_cv": b["referencias_cv"],
        "ganador": {o: dict(b["ganador"][o], aprobado_por=v["receta"]["ganador"][o].get("aprobado_por"),
                            fuente=f"{BUSQUEDA_REL}; aprobado_por de {VALIDACION_REL}") for o in OBJETIVOS},
        "importancias": dict(b["importancias"], fuente=BUSQUEDA_REL),
        "validacion": validacion,
        "corte": {"aplica": False, "por_que": v["validaciones_nulas"].get("con_probabilidad"),
                  "nota": pa.get("objetivo", {}).get("nota"), "fuente": f"{VALIDACION_REL}, validaciones_nulas; "
                                                                        f"{PARTICION_REL}, objetivo.nota"},
        "vias_de_mejora": informe["vias"]}


# ══ 8. Las figuras de la pieza común ══════════════════════════════════════════════
def dibujar(raiz, tablas):
    """Las dos figuras de la pieza común por objetivo, sin cambiarla. Devuelve las rutas escritas."""
    carpeta = raiz / FIGURAS_REL
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for o, t in tablas.items():
        # Real frente a previsto, con la diagonal del acierto perfecto
        fig = ec.figura_real_frente_a_prevision(t["real"].to_numpy(), {"el modelo": t["modelo"].to_numpy()})
        fig.axes[0].set_title(f"Validación en {OBJETIVO_TEXTO[o]}: real frente a previsto")
        ruta = carpeta / f"{o}_real_frente_a_prevision.png"
        fig.savefig(ruta, dpi=int(DPI))
        plt.close(fig)
        rutas.append(ruta)
        # El error de cada fila frente a lo previsto
        fig = ec.figura_residuos(t["real"].to_numpy(), t["modelo"].to_numpy())
        fig.axes[0].set_title(f"Validación en {OBJETIVO_TEXTO[o]}: error frente a lo previsto")
        ruta = carpeta / f"{o}_residuos.png"
        fig.savefig(ruta, dpi=int(DPI))
        plt.close(fig)
        rutas.append(ruta)
    return rutas


# ══ 9. El informe para la persona, generado del diccionario ════════════════════
def tabla_md(cabecera, filas):
    """Una tabla de Markdown: las columnas de cifras a la derecha y las de texto a la izquierda (reglas de salida,
    TB2). En la columna de texto, el nombre del objetivo con su tilde."""
    filas = [[OBJETIVO_TEXTO.get(c, c) if isinstance(c, str) else c for c in fila] for fila in filas]
    cifra = re.compile(r"^[+-]?[\d.,]+$")
    alineacion = ["---:" if filas and all(cifra.match(str(f[i])) for f in filas) else "---"
                  for i in range(len(cabecera))]
    lineas = ["| " + " | ".join(cabecera) + " |", "|" + "|".join(alineacion) + "|"]
    lineas += ["| " + " | ".join(str(c) for c in fila) + " |" for fila in filas]
    return lineas


def primera_mayuscula(texto):
    """El texto con la primera letra en mayúscula, sin tocar el resto."""
    return texto[:1].upper() + texto[1:]


def titulo_objetivo(inf, o):
    """«Unidades, a 10 días», con el horizonte citado del JSON."""
    return f"{OBJETIVO_TEXTO[o].capitalize()}, a {inf['validacion'][o]['horizonte']} días"


def md_aprobado(inf):
    """Lo aprobado antes de entrenar."""
    a = inf["aprobado"]
    p, q = a["partes"], a["quitadas"]
    return ["## Lo aprobado antes de entrenar", "",
            "Todo lo de este apartado se aprobó antes de entrenar; este informe no lo cambia.", "",
            f"- **Hace falta modelar: {a['hace_falta']}.** La ficha pide una previsión diaria de cada departamento en "
            "cada tienda; el exploratorio no la contesta.",
            f"- **Decide sobre personas: {a['contestable']}.** {primera_mayuscula(a['contestable_por_que'])}.",
            f"- **Medida principal:** {a['medida']}. Por qué: {a['medida_por_que']}.",
            f"- **Referencias:** {'; '.join(a['referencias'])}.",
            f"- **Lo que se da por bueno:** {a['se_da_por_bueno']}.",
            f"- **Algoritmos y búsqueda:** {a['algoritmos']}. Lo aprobó {a['algoritmos_aprobado_por']}.",
            f"- **El ganador, aprobado antes de abrir la validación:** {'; '.join(a['ganador_aprobado_por'])}.",
            f"- **Partición por fecha:** entrenamiento con {p['entrenamiento']['filas']} filas, del "
            f"{p['entrenamiento']['desde']} al {p['entrenamiento']['hasta']} ({p['entrenamiento']['dias']} días); "
            f"validación con {p['validacion']['filas']} filas, del {p['validacion']['desde']} al "
            f"{p['validacion']['hasta']} ({p['validacion']['dias']} días).",
            f"- **Historia que piden las variables:** salen del entrenamiento {q['filas_quitadas']} filas, del "
            f"{q['desde']} al {q['hasta']}; quedan {q['filas_despues']} para ajustar.",
            f"- **Preselección:** modo {a['preseleccion']['modo']}, escenario {a['preseleccion']['escenario']}; "
            f"fijado en {a['preseleccion']['escenario_fijado_en']}.", ""]


def md_probado(inf):
    """Qué se probó y cuánto costó."""
    pr = inf["probado"]
    lineas = ["## Qué se probó y cuánto costó", "",
              "Primero un modelo mínimo, sin búsqueda, para ver dónde estaba el listón. Después, la búsqueda "
              "aprobada.", ""]
    for o in OBJETIVOS:
        m = pr["minimo"][o]
        lineas.append(f"- **Modelo mínimo en {OBJETIVO_TEXTO[o]}:** falla {m['recursiva']} en recursivo y "
                      f"{m['a_un_dia']} a un día.")
    lineas += ["", f"La validación cruzada: «{pr['cv_tipo']}». Fueron {pr['pliegues']} cortes. Cada corte prevé "
               f"{pr['test_size']['unidades']} días en unidades y {pr['test_size']['dolares']} en dólares, desde estos "
               "orígenes:", ""]
    for o in OBJETIVOS:
        lineas.append(f"- {OBJETIVO_TEXTO[o]}: {', '.join(pr['origenes'][o])}.")
    lineas += ["", f"La búsqueda fue de nivel {pr['nivel']}. Su medida: {pr['medida']}. Qué parte del espacio se "
               "probó:", ""]
    lineas += tabla_md(["Objetivo", "Algoritmo", "Tipo", "Combinaciones probadas", "Combinaciones posibles"],
                       [[e["objetivo"], e["algoritmo"], e["tipo"], e["probadas"], e["combinaciones"]]
                        for e in pr["espacio"]])
    lineas += ["", f"La búsqueda ajustó {pr['modelos']} modelos ("
               + "; ".join(f"{k}: {x}" for k, x in pr["modelos_por"]) + "), más los de control ("
               + "; ".join(f"{k}: {x}" for k, x in pr["extra"]) + f"). Tardó {pr['segundos_busqueda']} segundos; la "
               f"validación, {pr['segundos_validacion']}.", "",
               f"Se ampliaron las rejillas {pr['ampliadas']} veces por un borde o un rango plano; "
               f"{pr['ampliadas_medidas']} de esas ampliaciones se midieron y las demás no eran posibles. Las segundas "
               "búsquedas que contestaban esas ampliaciones fueron estas:", ""]
    lineas += tabla_md(["Objetivo", "Algoritmo", "Mejora media", "Desviación", "Se sostiene"],
                       [[s["objetivo"], s["algoritmo"], s["mejora"], s["desviacion"], s["se_sostiene"]]
                        for s in pr["segundas"]])
    return lineas + [""]


def md_desequilibrio(inf):
    """El desequilibrio, que no aplica a una cantidad: se dice con su motivo."""
    d = inf["desequilibrio"]
    return ["## El desequilibrio", "",
            "No aplica a esta previsión. El desequilibrio del método es el de un objetivo de sí o no con una clase "
            "mucho más rara que la otra; aquí los dos objetivos son cantidades.", "",
            f"- Motivo que dejó la búsqueda: «{d['busqueda']}».",
            f"- Lo que dice la partición: «{d['particion']}».",
            f"- Por eso no se equilibró nada ni hubo que recalibrar: «{d['recalibrado']}».", ""]


def md_ranking(inf):
    """El ranking de cada objetivo con las referencias al lado."""
    lineas = ["## Ranking", "",
              "El error es el de los cortes de la validación cruzada, previendo en recursivo; el de entrenamiento se "
              "mide a un día en las filas del ajuste. La distancia entre los dos es el sobreajuste.", ""]
    for o in OBJETIVOS:
        r = inf["ranking"][o]
        lineas += [f"### {titulo_objetivo(inf, o)}", ""]
        lineas += tabla_md(["Algoritmo", "Error medio", "Desviación entre cortes", "Sesgo", "Error en entrenamiento",
                            f"Cortes que gana, de {inf['pliegues']}"],
                           [[a["algoritmo"], a["error"], a["desviacion"], a["sesgo"], a["entrenamiento"], a["gana"]]
                            for a in r["algoritmos"]])
        lineas += [""]
        lineas += tabla_md(["Referencia", "Error medio", "Sesgo"],
                           [[x["nombre"], x["error"], x["sesgo"]] for x in r["referencias"]])
        c = r["comparacion"]
        # scripts/15_busqueda.py, comparar_pliegue_a_pliegue: «a» es HistGradientBoosting y «b», Ridge
        lineas += ["", f"Pliegue a pliegue, HistGradientBoosting menos Ridge da {c['media']} puntos de media, con una "
                   f"desviación de {c['desviacion']}. Empate: {c['empate']}.", ""]
    return lineas


def md_ganador(inf):
    """El ganador y por qué."""
    lineas = ["## El ganador y por qué", ""]
    for o in OBJETIVOS:
        g = inf["ganador"][o]
        rs, ca = g["regla_simple"], g["canario"]
        hiper = "; ".join(f"`{k}` = {'sin límite' if x == 'sin cifra' else x}" for k, x in g["buscados"])
        lineas += [f"### {titulo_objetivo(inf, o)}", "",
                   f"Gana {g['algoritmo']}, con {g['columnas']} columnas y semilla {g['semilla']}. Se reajustó con "
                   f"{g['reajuste']} filas de la construcción. Por qué: {g['por_que']}. Su ficha está en "
                   f"`{g['ficha']}`.", "",
                   f"- **Hiperparámetros elegidos:** {hiper}.",
                   f"- **Frente a la regla simple:** con solo las dos variables que más pesan "
                   f"({', '.join(f'`{x}`' for x in rs['variables'])}), una regresión lineal falla {rs['error']}. El "
                   f"ganador la supera pliegue a pliegue: {rs['supera']} (diferencia media de {rs['media']}, "
                   f"desviación de {rs['desviacion']}).",
                   f"- **Canario:** con el objetivo barajado falla {ca['barajado']}; con la venta real puesta como "
                   f"variable, {ca['fuga']}. Un error por debajo de {ca['limite']} apuntaría a que la previsión usa el "
                   "futuro: la comprobación ve una fuga cuando la hay.", ""]
    return lineas


def md_importancias(inf):
    """Qué variables pesan."""
    lineas = ["## Qué variables pesan", "",
              "La importancia es lo que empeora el error al barajar cada variable de origen. Dice que el modelo usa "
              "esa variable para acertar. No dice que cause la venta.", ""]
    for o in OBJETIVOS:
        imp = inf["importancias"][o]
        lineas += [f"### {titulo_objetivo(inf, o)}", ""]
        lineas += tabla_md(["Variable", "Importancia", "Desviación"],
                           [[f"`{x['columna']}`", x["importancia"], x["desviacion"]] for x in imp["primeras"]])
        lineas += ["", f"Son las primeras de {imp['total']} variables de origen. Las dos primeras llevan {imp['peso_dos']} "
                   f"de la importancia positiva, en tanto por uno. Método: {imp['metodo']}; filas: {imp['filas']}; "
                   f"puntuación: {imp['puntuacion']}.", ""]
    return lineas


def md_validacion(inf):
    """La validación, con las referencias al lado."""
    va = inf["validacion"]
    lec = va["lecturas"]
    lineas = ["## La validación", "",
              f"El ganador se midió una sola vez en la validación, en recursivo y con las {va['series']} series "
              f"enteras (muestra: {va['muestra']}). Cómo van las previsiones: «{va['valores_previsiones']}».", ""]
    for o in OBJETIVOS:
        x = va[o]
        ve, su = x["veredicto"], x["suavizado"]
        dias_fuera = f", sin {', '.join(x['dias_fuera'])}" if x["dias_fuera"] else ""
        lineas += [f"### {titulo_objetivo(inf, o)}: {ve['veredicto']}", "",
                   f"Se midió desde {x['origenes']} orígenes, del {x['primer_dia']} al {x['ultimo_dia']}, con "
                   f"{x['filas_medidas']} filas{dias_fuera}. Cada serie tiene {x['dias_por_serie']} días previstos.",
                   "", "**El veredicto y sus dos condiciones** (reglas, apartado 7, «Qué cuenta como mejora»):", "",
                   f"- Falla menos que la regla que menos falla en {ve['origenes_que_gana']} de {ve['de']} orígenes; "
                   f"hacían falta {ve['minimo']}. Se cumple: {'sí' if ve['cumple_origenes'] else 'no'}.",
                   f"- La ventaja es de {ve['ventaja']} puntos ({ve['medida']}), con un intervalo de {ve['bajo']} a "
                   f"{ve['alto']}. Entero por encima de cero: {'sí' if ve['cumple_intervalo'] else 'no'}.",
                   f"- El intervalo sale de remuestrear {ve['remuestreos']} veces {ve['que_se_remuestrea']}, "
                   f"{ve['unidades']} series, con semilla {ve['semilla']}.", "",
                   f"**El error y el sesgo**, en {UNIDAD[o]}. Filas: «{x['filas_todas']}». El trivial es "
                   f"{x['trivial_como']}.", ""]
        lineas += tabla_md(["Previsión", "Error", "Sesgo"], [[e["nombre"], e["error"], e["sesgo"]] for e in x["todas"]])
        lineas += ["", f"**El suavizado exponencial, como lectura.** El modelo falla menos que él en "
                   f"{su['origenes_que_gana']} de {su['de']} orígenes. La diferencia es de {su['ventaja']} puntos, con "
                   f"un intervalo de {su['bajo']} a {su['alto']}. Lectura: {su['lectura']}. El veredicto se mide solo "
                   "frente a las tres reglas.", "",
                   f"**La recomendación de cada departamento.** Se recomienda el modelo en {x['n_modelo']} de "
                   f"{x['n_departamentos']} departamentos. Donde el modelo falla de media más que la regla que menos "
                   "falla, se recomienda esa regla; el veredicto principal no cambia.", ""]
        lineas += tabla_md(["Departamento", "Error del modelo", "Regla que menos falla", "Error de la regla",
                            "Se recomienda"],
                           [[d["departamento"], d["modelo"], d["regla"], d["regla_error"], d["se_recomienda"]]
                            for d in x["recomendacion"]])
        lineas += ["", "**Los días de evento y los días SNAP.**", ""]
        lineas += tabla_md(["Días", "Error del modelo", "Sesgo del modelo", "Regla que menos falla en ellos",
                            "Su error"],
                           [[DIAS[k], d["modelo_error"], d["modelo_sesgo"], d["regla"], d["regla_error"]]
                            for k, d in x["dias"].items()])
        lineas += ["", "**El error por día del horizonte.**", ""]
        lineas += tabla_md(["Día", "Error del modelo", "Sesgo del modelo", "Regla que menos falla ese día",
                            "Su error"],
                           [[h["h"], h["modelo_error"], h["modelo_sesgo"], h["regla"], h["regla_error"]]
                            for h in x["por_h"]])
        lineas += ["", f"**El MASE**: el error de cada previsión entre la escala, que es {x['mase_escala']}. Por "
                   "debajo de 1, falla menos que esa referencia ingenua.", ""]
        lineas += tabla_md(["Previsión", "MASE"], [[m["nombre"], m["valor"]] for m in x["mase"]])
        lineas += ["", f"**El error por tramos del valor real**, del modelo. Filas: «{x['tramos_filas']}».", ""]
        lineas += tabla_md(["Tramo", "Filas", "Real medio", "Previsto medio", "Error medio", "Sesgo"],
                           [[t["tramo"], t["filas"], t["real_medio"], t["previsto_medio"], t["mae"], t["sesgo"]]
                            for t in x["tramos"]])
        lineas += ["", "**Las medidas de la pieza común** en las mismas filas, en las unidades del objetivo.", ""]
        lineas += tabla_md(["Previsión", "Error medio absoluto", "Raíz del error cuadrático", "R²"],
                           [[m["nombre"], m["mae"], m["rmse"], m["r2"]] for m in x["medidas"]])
        lineas += ["", "**Cada tienda, para leer.**", ""]
        lineas += tabla_md(["Tienda", "Error del modelo", "Regla que menos falla", "Su error"],
                           [[t["tienda"], t["modelo_error"], t["regla"], t["regla_error"]] for t in x["por_tienda"]])
        dv = x["desarrollo"]
        lado = {"desarrollo": "desarrollo", "validacion": "validación",
                "validacion_entre_desarrollo": "validación entre desarrollo"}
        lineas += ["", f"**Desarrollo frente a validación.** En el entrenamiento, a un día, el modelo falla "
                   f"{dv['entrenamiento']} ({dv['entrenamiento_filas']}); en la validación, en recursivo, "
                   f"{dv['validacion']}. En los cortes de la búsqueda fallaba {dv['cv_entrenamiento']} en "
                   f"entrenamiento, {dv['cv_a_un_dia']} a un día y {dv['cv_recursiva']} en recursivo. Lectura: "
                   f"{dv['lectura']}. Con la pieza común ({dv['pieza_filas']}):", ""]
        lineas += tabla_md(["Lado", "Error medio absoluto", "Raíz del error cuadrático", "R²"],
                           [[lado.get(p["lado"], p["lado"]), p["mae"], p["rmse"], p["r2"]] for p in dv["pieza"]])
        dc, ca = x["dias_cero"], x["canario"]
        lineas += ["", f"**Los días a cero.** En ellos el modelo se pasa {dc['sesgo']} {dc['unidad']} por fila de "
                   f"media ({dc['filas']}).", "",
                   f"**El canario de la validación.** Con el objetivo barajado el modelo falla {ca['barajado']}; con "
                   f"la venta real como variable, {ca['fuga']}.", ""]
        if "fuga" in lec and "ventaja" in lec:
            lineas += [f"**Lecturas del paso anterior.** Son umbrales para leer, sin poder de decisión "
                       f"({lec['fuga']['origen']}). Un error por debajo de {lec['fuga']['valor']} apuntaría a que la "
                       f"previsión usa el futuro: el del modelo queda {'por encima' if x['error_por_encima_de_fuga'] else 'por debajo'}. "
                       f"Una ventaja de más de {lec['ventaja']['valor']} puntos se revisaría: esta queda "
                       f"{'por debajo' if x['ventaja_por_debajo_de_revisar'] else 'por encima'}.", ""]
    if "dias_cero" in lec:
        lineas += [f"El sesgo de los días a cero se da como {lec['dias_cero']['valor']}, porque "
                   f"{lec['dias_cero']['origen']}.", ""]
    lineas += md_matiza(inf)
    lineas += md_niveles(inf)
    lineas += ["### Las figuras de la pieza común", "",
               "La primera de cada objetivo pone lo real frente a lo previsto, con la diagonal del acierto perfecto. "
               "La segunda pone el error de cada fila frente a lo previsto, con la línea del cero: una nube sin forma "
               "es buena señal. Son las filas de la validación sin los días fuera del error.", ""]
    for x in inf["figuras"]:
        o = x["objetivo"]
        lineas += [f"![{OBJETIVO_TEXTO[o].capitalize()}: real frente a previsto, {x['filas_escrito']} filas]"
                   f"(figuras_modelado/{o}_real_frente_a_prevision.png)", "",
                   f"![{OBJETIVO_TEXTO[o].capitalize()}: error frente a lo previsto, {x['filas_escrito']} filas]"
                   f"(figuras_modelado/{o}_residuos.png)", ""]
    return lineas


def nombre_tiendas(lista):
    """Varias tiendas escritas como «WI_2 y WI_3»."""
    return " y ".join(lista) if len(lista) < 3 else ", ".join(lista[:-1]) + " y " + lista[-1]


def eventos_por_motivo(sin_cubrir):
    """Los eventos sin cubrir agrupados por su motivo: «Fuera del horizonte: A, B. Fuera del error: C.»"""
    grupos = {}
    for e in sin_cubrir:
        grupos.setdefault(e["motivo"], []).append(e["nombre"])
    return " ".join(f"{motivo[:1].upper()}{motivo[1:]}: {', '.join(nombres)}." for motivo, nombres in grupos.items())


def md_matiza(inf):
    """Lo que matiza la ventaja, subapartado de «La validación», con el bloque «robustez» citado."""
    va = inf["validacion"]
    lineas = ["### Lo que matiza la ventaja", "",
              "Son lecturas sobre las mismas previsiones y las mismas filas medidas que el veredicto. No lo cambian: "
              "dicen dónde se gana la ventaja y qué días no llegó a medir la validación.", ""]
    for o in OBJETIVOS:
        rb = va[o]["robustez"]
        j, it, me, ev = rb["juntas"], rb["intervalo"], rb["mejores"], rb["eventos"]
        juntas = (f"Sin {nombre_tiendas(j['quitar'])} juntas, la ventaja queda en {j['ventaja']} puntos."
                  if j["valor"] is not None else
                  f"Sin {nombre_tiendas(j['quitar'])} juntas no se calculó: {j['motivo']}.")
        sin_cubrir = (f"Los demás quedan sin cubrir. {eventos_por_motivo(ev['sin_cubrir'])}" if ev["sin_cubrir"]
                      else "Ninguno queda sin cubrir.")
        lineas += [f"**{titulo_objetivo(inf, o)}.**", "",
                   f"- **La ventaja se concentra en pocas series.** Las {rb['n_primeras']} de las {rb['n_series']} que "
                   f"más aportan suman {rb['aporte_primeras']} puntos. La ventaja entera es de {rb['ventaja']}. "
                   "Son, con su aporte: " + "; ".join(f"{x['serie']} ({x['aporte']})" for x in rb["primeras"]) + ".",
                   f"- **Sin algunas tiendas.** {juntas} La tabla de abajo da la ventaja sin cada tienda.",
                   f"- **Remuestreando tiendas enteras.** Con las {it['unidades']} tiendas sorteadas {it['remuestreos']} "
                   f"veces (semilla {it['semilla']}), el intervalo de la ventaja va de {it['bajo']} a "
                   f"{it['alto']}. Es una lectura: el veredicto se mide con el intervalo de series.",
                   f"- **Series en que alguna regla falla menos que el modelo:** {me['cuantas']} de {me['de']}, con "
                   "todos los orígenes juntos."
                   + (" Son " + "; ".join(me["series"]) + "." if me["series"] else ""),
                   f"- **Eventos del calendario.** Del {ev['desde']} al {ev['hasta']} hay {ev['cuantos']}. De ellos, "
                   f"{ev['cubiertos']} caen en días medidos. {sin_cubrir}",
                   "- **Filas medidas por día de la semana:** "
                   + "; ".join(f"{d['dia']}, {d['filas']}" for d in rb["dias"]) + ".", ""]
    # La ventaja sin cada tienda, de los dos objetivos en una tabla, por el nombre de la tienda
    por_tienda = {}
    for o in OBJETIVOS:
        for t in va[o]["robustez"]["cada_tienda"]:
            por_tienda.setdefault(t["quitar"][0], {})[o] = t["ventaja"]
    lineas += tabla_md(["Tienda que se quita"] + [f"Ventaja en {OBJETIVO_TEXTO[o]}" for o in OBJETIVOS],
                       [[t] + [x.get(o, "sin cifra") for o in OBJETIVOS] for t, x in sorted(por_tienda.items())])
    return lineas + [""]


def md_niveles(inf):
    """La previsión sumada por tienda, categoría, estado y cadena, subapartado de «La validación», con el bloque
    «niveles» citado; responde a la pregunta 3 de la ficha."""
    va = inf["validacion"]
    lineas = ["### La previsión sumada por tienda, categoría, estado y cadena", "",
              "La previsión de la cadena, la de cada estado, la de cada tienda y la de cada categoría salen de sumar "
              "las previsiones de sus series de departamento y tienda tal como se miden: acotadas en cero y, en "
              "unidades, redondeadas antes de sumar. El error y el sesgo de cada grupo salen de sus filas sumadas, "
              "con todos los orígenes juntos. Es una lectura sobre las mismas filas medidas que el veredicto, que no "
              "cambia.", ""]
    for o in OBJETIVOS:
        nv = va[o]["niveles"]
        cadena = nv["cadena"]["grupos"][0]
        lineas += [f"**{titulo_objetivo(inf, o)}.** En la cadena, que suma las {cadena['series']} series, el modelo "
                   f"falla {cadena['error_modelo']} {UNIDAD[o]}. La regla que menos falla en ella es "
                   f"{cadena['regla']}, con {cadena['error_regla']}. Origen a origen, el modelo falla menos que la "
                   f"regla que menos falla en ese origen en {nv['origenes']['gana']} de {nv['origenes']['de']}.", ""]
        lineas += tabla_md(["Previsión de la cadena", "Error", "Sesgo"],
                           [[e["nombre"], e["error"], e["sesgo"]] for e in cadena["errores"]])
        lineas += [""]
        filas = []
        for nivel in NIVELES:
            for g in nv[nivel]["grupos"]:
                grupo = f"las {g['series']} series" if nivel == "cadena" else g["grupo"]
                filas.append([NIVEL_TEXTO[nivel], grupo, g["filas_sumadas"], g["error_modelo"], g["sesgo_modelo"],
                              g["regla"], g["error_regla"], g["modelo_falla_menos"]])
        lineas += tabla_md(["Nivel", "Grupo", "Filas sumadas", "Error del modelo", "Sesgo del modelo",
                            "Regla que menos falla", "Su error", "El modelo falla menos"], filas)
        lineas += [""]
    return lineas


def md_corte(inf):
    """El corte, que no aplica a una cantidad: se dice con su motivo."""
    c = inf["corte"]
    return ["## El corte", "",
            "No aplica a esta previsión. El corte convierte una probabilidad en un sí o un no; aquí no hay "
            f"probabilidad. Motivo que dejó la validación: «{c['motivo']}».", "",
            f"La previsión se usa como cantidad, tal cual sale: «{inf['validacion']['valores_previsiones']}». Sin "
            "probabilidad no hay umbral que fijar, ni tabla de cortes, ni matriz de impacto, ni escenarios.", ""]


def md_bueno(inf):
    """¿Se da por bueno?"""
    va = inf["validacion"]
    lineas = ["## ¿Se da por bueno?", ""]
    todos = all(va[o]["veredicto"]["veredicto"] == "gana" for o in OBJETIVOS)
    lineas += [f"**{'Sí, en los dos objetivos.' if todos else 'No en los dos objetivos.'}** Veredicto aprobado: "
               f"{inf['cabecera']['aprobacion']}. La regla con que se decide, escrita antes de medir: "
               f"{inf['aprobado']['se_da_por_bueno']}.", ""]
    for o in OBJETIVOS:
        ve = va[o]["veredicto"]
        lineas.append(f"- **{titulo_objetivo(inf, o)}: {ve['veredicto']}.** Falla menos que la regla que menos falla "
                      f"en {ve['origenes_que_gana']} de {ve['de']} orígenes, con una ventaja de {ve['ventaja']} puntos "
                      f"y un intervalo de {ve['bajo']} a {ve['alto']}.")
    lineas += ["", "Hace falta el modelo y no basta el suavizado: el modelo también le gana en las lecturas de los dos "
               "objetivos." if all(va[o]["suavizado"]["lectura"] == "gana" for o in OBJETIVOS) else
               "Frente al suavizado, el modelo no gana en las lecturas de los dos objetivos: a la empresa podría "
               "bastarle el método sencillo (planteamientos §1).", "",
               "La recomendación por departamento no cambia el veredicto principal: en los departamentos donde una "
               "regla falla menos, se recomienda esa regla (apartado «La validación»).", ""]
    return lineas


def md_vias(inf):
    """Las tres vías de mejora, como mejoras posibles."""
    vi = inf["vias"]
    ll = vi["llegada"]
    lineas = ["## Las tres vías de mejora", "",
              "El modelo se da por bueno, así que las vías van como mejoras posibles, de la más barata a la más cara "
              "(método, apartado 8). Una búsqueda nueva, después de haber visto la validación, solo se mediría con filas que "
              "nadie ha visto: la prueba final o un periodo nuevo.", "",
              "1. **Mejor modelo.** Lo que quedó sin probar en la búsqueda:", ""]
    for s in vi["sin_probar"]:
        lineas.append(f"   - {s['algoritmo']} en {OBJETIVO_TEXTO.get(s['objetivo'], s['objetivo'])}: se probaron "
                      f"{s['probadas']} de {s['combinaciones']} combinaciones de su rejilla.")
    for s in vi["imposibles"]:
        lineas.append(f"   - `{s['hiperparametro']}` en {OBJETIVO_TEXTO.get(s['objetivo'], s['objetivo'])}, por el "
                      f"lado {s['lado']}: no se amplió porque {s['motivo']}.")
    if vi["con_rejilla_sin_entrar"]:
        lineas.append(f"   - Sin probar, con su rejilla preparada en la búsqueda: "
                      f"{', '.join(f'«{x}»' for x in vi['con_rejilla_sin_entrar'])}. No estaba en la lista aprobada: "
                      f"{vi['algoritmos']}.")
    lineas += [f"   - De {vi['n_segundas']} segundas búsquedas, {vi['no_sostenidas']} no mejoraron de forma que se "
               "sostuviera pliegue a pliegue.",
               f"   - Un modelo por serie quedó descartado por su coste: «{vi['modelo_por_serie']}» (planteamientos §2, "
               "decisión 6).", "",
               "2. **Variables nuevas con los datos que ya hay.** "
               + (f"Las candidatas de los planteamientos §2, decisión 7, se crearon todas: hay "
                  f"{inf['aprobado']['variables_generadas']} entradas en las variables del modelo."
                  if not vi["sin_crear"] else
                  f"Candidatas de los planteamientos §2, decisión 7, sin crear: "
                  f"{', '.join(f'`{x}`' for x in vi['sin_crear'])}."), ""]
    if ll.get("formula"):
        lineas.append(f"   - La llegada de productos nuevos (cuestión 001) se creó como {ll['formula']}.")
        for o in OBJETIVOS:
            x = ll[o]
            lineas.append(f"     En {OBJETIVO_TEXTO[o]}, en HistGradientBoosting: «{x['hgb']}»; en Ridge: «{x['ridge']}». "
                          f"En el ganador pesa {x['importancia']} puntos de error.")
    if vi["eventos"]:
        lineas.append(f"   - Los campos `event_name_1` y `event_name_2` no entraron en el ganador: el responsable del caso eligió una "
                      f"columna por festivo (reglas, apartado 7), la opción «{vi['eventos']}».")
    lineas += ["   - Las variables que no se probaron, con su motivo:", ""]
    lineas += ["   " + x for x in tabla_md(["Variable", "Motivo"], [[f"`{x['variable']}`", x["motivo"]]
                                                                      for x in vi["fuera"]])]
    lineas += ["", "3. **Más información.** Los datos que harían falta están en las reglas, «Lo que no se puede "
               "calcular»:", ""]
    for x in vi["informacion"]:
        lineas.append(f"   - **{x['dato'].capitalize()}**, para {x['para_que']}. Lo dicen las reglas: «{x['frase']}» "
                      f"Quién lo tiene: {x['quien_lo_tiene']}.")
    return lineas + [""]


def md_validaciones(r):
    """Las validaciones de este script y las de los pasos 15 y 16, contadas."""
    lineas = ["## Validaciones", "", "Las de este informe, calculadas en esta ejecución:", ""]
    texto = {True: "pasa", False: "falla", None: "sin comprobar"}
    lineas += tabla_md(["Validación", "Resultado"],
                       [[DESCRIPCION_VALIDACION[k], texto[r["validaciones"].get(k)]] for k in NOMBRES_VALIDACION])
    lineas += ["", "Las de los pasos anteriores, tal como quedaron en sus JSON:", ""]
    for rel, p in r["informe"]["pasos"].items():
        lineas.append(f"- `{rel}`: {p['en_verde']} en verde de {p['comprobadas']} comprobadas.")
        for k, motivo in p["nulas"]:
            lineas.append(f"  - `{k}`: {motivo}.")
    return lineas + [""]


def md_parametros(inf):
    """Los parámetros usados: los de este informe y los que dejaron la búsqueda y la validación."""
    pa = inf["parametros"]
    lineas = ["## Parámetros usados", "", "Los de este informe:", ""]
    lineas += tabla_md(["Parámetro", "Valor", "Origen"], [[x["nombre"], x["valor"], x["origen"]] for x in pa["propios"]])
    lineas += ["", "Los de la búsqueda y la validación, con los que se midió todo lo citado:", ""]
    lineas += tabla_md(["Paso", "Parámetro", "Valor", "Origen"],
                       [[f"`{x['paso']}`", x["nombre"], x["valor"], x["origen"]] for x in pa["heredados"]])
    return lineas + [""]


def md_datos_personales(inf):
    """Datos personales (resultado.md, regla 6)."""
    dp = inf["datos_personales"]
    if dp["existe"]:
        cuerpo = [f"La protección de los datos está descrita en `{PROTECCION_REL}`."]
    else:
        cuerpo = [f"No existe `{PROTECCION_REL}`: los datos no pasaron por la protección. Las reglas del caso (§9) "
                  "dicen que los datos son de productos, tiendas, precios y calendario. No traen nada de personas."]
    return ["## Datos personales", ""] + cuerpo + [
        "", f"Columnas de datos personales que usa o deja este informe: {dp['columnas']}.", ""]


def md_limites_matiza(inf):
    """Las dos viñetas de «Límites» que salen del bloque «robustez»: los eventos sin probar y la concentración."""
    va = inf["validacion"]
    eventos = []
    for o in OBJETIVOS:
        ev = va[o]["robustez"]["eventos"]
        if not ev["sin_cubrir"]:
            continue
        eventos.append(f"En {OBJETIVO_TEXTO[o]}, la validación cubre {ev['cubiertos']} de los {ev['cuantos']} eventos "
                       f"del año. El modelo no está probado en los demás. {eventos_por_motivo(ev['sin_cubrir'])}")
    concentra = []
    for o in OBJETIVOS:
        rb = va[o]["robustez"]
        j = rb["juntas"]
        texto = (f"En {OBJETIVO_TEXTO[o]}, las {rb['n_primeras']} series que más aportan suman {rb['aporte_primeras']} "
                 f"puntos. La primera es {rb['primeras'][0]['serie']}." if rb["primeras"] else "")
        if j["valor"] is not None:
            texto += (f" Sin {nombre_tiendas(j['quitar'])}, la ventaja queda en {j['ventaja']} frente a "
                      f"{rb['ventaja']}")
            texto += (": en las series de las demás tiendas es más pequeña." if j["valor"] < rb["ventaja_valor"]
                      else ".")
        concentra.append(texto.strip())
    lineas = []
    if eventos:
        lineas.append("- **Eventos que la validación no cubre.** " + " ".join(eventos))
    lineas.append("- **La ventaja se concentra en pocas series.** " + " ".join(x for x in concentra if x))
    return lineas


def md_limites(inf):
    """Los límites del modelo (método, apartado 10) con los de la validación."""
    va, a = inf["validacion"], inf["aprobado"]
    largo = max(OBJETIVOS, key=lambda o: va[o]["horizonte_valor"])
    corto = min(OBJETIVOS, key=lambda o: va[o]["horizonte_valor"])
    lineas = ["## Límites", "",
              f"- **A qué datos y periodos aplica.** A las {va['series']} series de departamento y tienda del recorte "
              f"de productos del caso. Se ajustó con la construcción, del {a['ajuste_desde']} al {a['ajuste_hasta']}, "
              f"con {a['ajuste_filas']} filas. Se midió en la validación, del {va[largo]['primer_dia']} al "
              f"{va[largo]['ultimo_dia']}. Un total del caso no es un total de Walmart.",
              f"- **Qué días mide cada objetivo.** En {OBJETIVO_TEXTO[corto]} cada serie tiene "
              f"{va[corto]['dias_por_serie']} días previstos; en {OBJETIVO_TEXTO[largo]}, "
              f"{va[largo]['dias_por_serie']}. La prueba final no se ha abierto: la confirmará una sola vez.",
              "- **Asociaciones, no causas.** El modelo aprende de la venta pasada y del calendario. No dice qué causa "
              "la venta.",
              f"- **Deriva.** El modelo se ajustó una vez, con {va[OBJETIVOS[0]]['reajuste']} filas. No se reajustó "
              "con la validación. Si cambia la forma de vender, el error sube: el intervalo de la ventaja es la "
              "referencia para ver cuándo se aleja.",
              "- **Confianza.** "
              + " ".join(f"En {OBJETIVO_TEXTO[o]}, la ventaja va de {va[o]['veredicto']['bajo']} a "
                         f"{va[o]['veredicto']['alto']} puntos; la del suavizado, de {va[o]['suavizado']['bajo']} a "
                         f"{va[o]['suavizado']['alto']}." for o in OBJETIVOS),
              "- **Se pasa de media.** "
              + " ".join(f"En {OBJETIVO_TEXTO[o]} el sesgo del modelo es de "
                         f"{next(e['sesgo'] for e in va[o]['todas'] if e['nombre'] == 'el modelo')} por cada 100; en "
                         f"los días con algún evento, de {va[o]['dias']['dias_con_evento']['modelo_sesgo']}."
                         for o in OBJETIVOS)
              + " Pasarse deja mercancía parada.",
              "- **Departamentos donde no se recomienda.** "
              + " ".join(f"En {OBJETIVO_TEXTO[o]}: "
                         + (", ".join(f"{d['departamento']} ({d['se_recomienda']})" for d in va[o]["recomendacion"]
                                      if d["se_recomienda"] != "el modelo") or "ninguno") + "."
                         for o in OBJETIVOS),
              *md_limites_matiza(inf),
              "- **Lo que no puede decir.** Las cifras miden lo vendido. Sin existencias, un día a cero no dice si "
              "había producto. Sin coste ni margen, no se puede calcular el dinero que ahorra la previsión.",
              f"- **Sospechas apuntadas por la validación:** {va['sospechas']}.", ""]
    return lineas


def generar_md(r):
    """El texto de informes/modelado.md, solo con lo que hay en el diccionario."""
    inf = r["informe"]
    lineas = ["# El modelado · caso 69", "",
              f"Fecha de los datos: {inf['cabecera']['fecha_datos']}. Informe interno de auditoría del modelo, "
              f"generado de `{JSON_REL}` por `{SCRIPT_REL}`. Estado: {r['resultado']['estado']}. No mide nada nuevo: "
              "cita lo que dejaron los pasos del modelado.", ""]
    va = inf["validacion"]
    lineas += ["**El modelo gana a las tres reglas en los dos objetivos y se da por bueno.** "
               + " ".join(f"En {OBJETIVO_TEXTO[o]} falla {va[o]['veredicto']['error_modelo']} frente a "
                          f"{va[o]['veredicto']['error_rival']} de la regla que menos falla."
                          for o in OBJETIVOS)
               + f" Veredicto aprobado: {inf['cabecera']['aprobacion']}.", ""] if all(
        va[o]["veredicto"]["veredicto"] == "gana" for o in OBJETIVOS) else []
    lineas += md_aprobado(inf) + md_probado(inf) + md_desequilibrio(inf) + md_ranking(inf) + md_ganador(inf)
    lineas += md_importancias(inf) + md_validacion(inf) + md_corte(inf) + md_bueno(inf) + md_vias(inf)
    lineas += md_validaciones(r) + md_parametros(inf) + md_datos_personales(inf) + md_limites(inf)
    return "\n".join(lineas)


def md_parado(r):
    """El informe cuando el script para antes de reunir nada."""
    return "\n".join(["# El modelado · caso 69", "", f"Estado: {r['resultado']['estado']}.", "",
                      f"El informe no se generó. Motivo: {r['resultado']['resumen']}", ""])


# ══ 10. Principal ═══════════════════════════════════════════════════════════════
def escribir_salidas(raiz, r, md):
    """Escribe el JSON y el informe, en UTF-8 y sin NaN (errores 21 y 22)."""
    (raiz / "informes").mkdir(parents=True, exist_ok=True)
    texto = json.dumps(a_json_limpio(r), ensure_ascii=False, indent=2, allow_nan=False)
    (raiz / JSON_REL).write_text(texto + "\n", encoding="utf-8")
    (raiz / MD_REL).write_text(md, encoding="utf-8")


def principal(raiz):
    """Lee, reúne, comprueba, dibuja y escribe. Devuelve 0 si todo queda en verde y 1 si no."""
    inicio = time.perf_counter()
    r = {"metodo": "aprendizaje-automatico", "version_metodo": version_metodo(raiz), "script": SCRIPT_REL,
         "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
         "entorno": entorno(), "entradas": [],
         "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": "", "artefactos": [JSON_REL, MD_REL],
                       "siguiente": "revisar el fallo y volver a ejecutar"},
         "pendientes": [], "validaciones": {k: None for k in NOMBRES_VALIDACION}, "tablas_abiertas": []}
    try:
        # Lectura de las entradas: si alguna falta, está en ERROR o tiene otra fecha, se para sin dibujar
        fuentes, entradas, paradas = leer_entradas(raiz)
        r["entradas"] = entradas
        r["validaciones"]["entradas_sin_error"] = not entradas_en_error(fuentes)
        r["validaciones"]["fechas_datos_iguales"] = all(e["fecha_datos"] == FECHA_DATOS for e in entradas)
        docs = leer_documentos(raiz)
        aprobado = normalizar(APROBACION_VEREDICTO) in normalizar(docs[PLANTEAMIENTOS_REL])
        r["validaciones"]["veredicto_aprobado_escrito"] = aprobado
        if not aprobado:
            paradas.append(f"la aprobación del veredicto no está escrita en {PLANTEAMIENTOS_REL} {SECCION_VEREDICTO}")
        if paradas:
            r["resultado"].update(estado="PARADO", resumen="; ".join(paradas),
                                  siguiente="resolver lo que dice el resumen y volver a ejecutar")
            escribir_salidas(raiz, r, md_parado(r))
            print("PARADO:", r["resultado"]["resumen"])
            return 1

        # La tabla de previsiones, solo para las figuras, con las filas que midió la validación
        ruta_prev = raiz / PREVISIONES_REL
        huella_prev = huella(ruta_prev)
        previsiones = leer_previsiones(raiz)
        r["tablas_abiertas"].append(PREVISIONES_REL)
        r["entradas"].append({"ruta": PREVISIONES_REL, "sha256": huella_prev, "filas": int(len(previsiones)),
                              "columnas": int(previsiones.shape[1])})
        tablas = {o: filas_de_figura(previsiones, o) for o in OBJETIVOS}
        medidas = {o: fuentes[VALIDACION_REL]["validacion"][o]["filas_medidas"] for o in OBJETIVOS}
        r["validaciones"]["figuras_con_las_filas_medidas"] = all(len(tablas[o]) == medidas[o] for o in OBJETIVOS)
        figuras = [{"objetivo": o, "filas": int(len(tablas[o])), "filas_medidas_validacion": medidas[o],
                    "ficheros": [f"{FIGURAS_REL}/{o}_real_frente_a_prevision.png", f"{FIGURAS_REL}/{o}_residuos.png"]}
                   for o in OBJETIVOS]

        # El diccionario: cada valor citado con su origen, y lo propio de resultado.md
        existe_proteccion = (raiz / PROTECCION_REL).exists()
        cs, informe = reunir(fuentes, docs, existe_proteccion, figuras)
        r.update(lo_propio(fuentes, informe))
        r["informe"] = informe
        r["cifras"] = cs.lista
        r["figuras"] = figuras
        r["parametros"] = [{"nombre": k, "valor": x["valor"], "origen": x["origen"]} for k, x in PARAMETROS.items()]
        r["datos_personales"] = {"proteccion_datos_json": existe_proteccion, "columnas_de_personas_usadas": []}

        # Las comprobaciones de las citas y del código, antes de escribir nada (error 15)
        codigo = Path(__file__).read_text(encoding="utf-8")
        r["validaciones"]["citas_con_origen"] = not citas_sin_origen(r["cifras"])
        r["validaciones"]["citas_existen"] = not citas_que_no_existen(r["cifras"], fuentes, docs)
        r["validaciones"]["redondeo_igual"] = not redondeo_distinto(r["cifras"])
        r["validaciones"]["sin_tablas_hechos"] = (not abre_tablas_hechos(codigo) and
                                                  not any("hechos_" in t for t in r["tablas_abiertas"]))
        r["validaciones"]["sin_resultados_escritos"] = not buscar_resultados_escritos(codigo)
        borrador = generar_md(r)
        en_borrador = comprobar_md(borrador, r, existe_proteccion)
        r["validaciones"].update(en_borrador)

        # Las figuras, solo si todo lo anterior está en verde
        listas = all(x is True for k, x in r["validaciones"].items()
                     if k not in ("figuras_escritas", "entradas_sin_cambiar", "informe_estable"))
        rutas = dibujar(raiz, tablas) if listas else []
        r["validaciones"]["figuras_escritas"] = figuras_completas(rutas)
        if rutas:
            r["resultado"]["artefactos"] = [JSON_REL, MD_REL] + [str(p.relative_to(raiz).as_posix()) for p in rutas]
        r["validaciones"]["entradas_sin_cambiar"] = not entradas_cambiadas(raiz, r["entradas"])

        # El estado y el informe final, que tiene que pasar las mismas comprobaciones que el borrador
        def cerrar():
            """Pone el estado según las validaciones."""
            todo = all(x is True for x in r["validaciones"].values() if x is not None) and \
                r["validaciones"]["informe_estable"] is not False
            if todo:
                vered = "; ".join(f"{o}: {fuentes[VALIDACION_REL]['validacion'][o]['veredicto']['veredicto']}"
                                  for o in OBJETIVOS)
                r["resultado"].update(estado="OK", riesgo="bajo", resumen=(
                    f"Informe del modelado con {len(APARTADOS)} apartados y {len(r['cifras'])} valores citados, cada "
                    f"uno con su fichero y su camino; cuatro figuras de la pieza común; veredicto aprobado ({vered})."),
                    siguiente="El responsable del caso lee el informe; al cerrar el modelado, el auditor sin memoria (método, apartado 10), con su "
                              "sí; después, preproduccion")
            else:
                malas = [k for k, x in r["validaciones"].items() if x is False]
                r["resultado"].update(estado="ERROR", riesgo="alto", resumen=f"validaciones en rojo: {', '.join(malas)}")
        r["validaciones"]["informe_estable"] = None
        cerrar()
        md = generar_md(r)
        r["validaciones"]["informe_estable"] = comprobar_md(md, r, existe_proteccion) == en_borrador
        cerrar()
        md = generar_md(r)
        r["segundos"] = round(time.perf_counter() - inicio, 1)
        escribir_salidas(raiz, r, md)
        print(f"{r['resultado']['estado']}: {r['resultado']['resumen']} ({r['segundos']} s)")
        return 0 if r["resultado"]["estado"] == "OK" else 1
    except Exception:
        # Fallo técnico: el JSON se escribe igual, con su estado (resultado.md, regla 5)
        r["resultado"].update(estado="ERROR", resumen=traceback.format_exc(limit=3)[-900:])
        escribir_salidas(raiz, r, md_parado(r))
        print(r["resultado"]["resumen"])
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=CASO, help="carpeta del caso (por defecto, la de este script)")
    args = parser.parse_args()
    sys.exit(principal(args.raiz.resolve()))
