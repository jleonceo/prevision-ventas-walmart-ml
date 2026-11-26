"""Informe ejecutivo del caso 69 (patrón assets/07_patron_informe_ejecutivo.md), en HTML A4 y en PDF.

El texto es el de config/metodo/borrador_informe_ejecutivo.md, versión 3, desde el título hasta el final,
copiado tal cual en BLOQUES. Cada cifra va marcada como [[nombre|cifra]]: «nombre» es la cifra de
informes/consultas-informe-ejecutivo.json y «cifra», cómo la escribe el texto. El HTML lleva la cifra del JSON escrita
con numero() de assets/graficos.py, con tantos decimales como la del texto; si no sale igual, para.

Antes de escribir el HTML para con ERROR si:
  - una cifra del texto no es la de su JSON, redondeada como la escribe el texto, o hay un número sin marcar que no es
    una fecha, un año, un código de departamento o tienda ni un dato fijo (de las reglas o de la prueba rápida);
  - un apartado pasa de su tope de palabras (§1 del patrón);
  - aparece una palabra vetada, salvo dentro de un nombre de fichero entre comillas invertidas;
  - deja de cumplirse una frase con sentido (exigir()).
Después imprime el PDF con Edge sin ventana, espera a que exista y deje de crecer, y para con ERROR si el anexo no
empieza en una página solo suya, si lo anterior no cabe en dos páginas o si pasa de tres.

Cómo se cuentan las palabras: en el texto visible, una palabra es un trozo entre espacios con al menos una letra o
una cifra. Cada apartado cuenta su texto sin su encabezado H2 o H3; el primero cuenta el título, el subtítulo y el
resumen.

Depende de scripts/07_consultas_informe_ejecutivo.py: lee su JSON. No usa assets/informe.py.

Uso: python -W error scripts/08_informe_ejecutivo.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pypdf import PdfReader

CASO = Path(__file__).resolve().parents[1]
# Las piezas comunes se usan desde assets/, sin copiarlas (programacion-del-caso §1)
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/08_informe_ejecutivo.py"
CONSULTAS = "informes/consultas-informe-ejecutivo.json"
HTML = "informes/informe_ejecutivo.html"
PDF = "informes/informe_ejecutivo.pdf"
RESUMEN = "informes/informe_ejecutivo.json"
FECHA_DATOS = "2015-05-22"
EDGE = str(Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
# Espera al PDF: Edge puede devolver el control antes de terminar de escribirlo (patrón §6)
ESPERA_MAXIMA_S = 120
INTERVALO_S = 0.5

# Topes de palabras de cada apartado (patrón §1)
TOPES = {"resumen": 300, "encontrado": 400, "limites": 100, "recomendaciones": 200, "anexo": 500}
# Palabras del método que no salen en el informe (borrador, «Términos fijados»)
VETADAS = ["serie", "series", "construcción", "validación", "corte", "cortes", "origen", "suceso", "entidad",
           "intermitente", "autocorrelación", "zona gris", "departamento de tienda", "departamentos de tienda"]
# Números que el texto escribe sin sacarlos del JSON:
#   - años, días y meses de las fechas, y la de emisión;
#   - los números de los códigos FOODS_3, HOBBIES_2 y WI_1, del nombre del concurso M5, la regla, apartado 9 y el 25 de
#     diciembre;
#   - datos fijos de las reglas: 70 combinaciones de departamento y tienda, 7 departamentos, 10 tiendas, 500 de 3.049 productos, horizontes de 10 y
#     28 días, las 4 semanas de la regla sencilla, el 80 % del Pareto, la razón 1,5 del cambio de nivel, la primera
#     quincena (15) y el 9 % que la frase de los meses no pasa;
#   - la prueba rápida de la ficha: 16,2 y 17,8 de cada 100, 10 de 12 fechas.
SIN_JSON = {"2011", "2012", "2013", "2014", "2015", "2020", "2026", "29", "01", "22", "05", "24", "26", "10", "11",
            "1", "2", "3", "4", "5", "9", "12", "15", "25", "28", "70", "80", "100", "500", "3", "049", "1,5", "16,2", "17,8"}
TITULO_ANEXO = "Anexo: trabajo realizado"

MARCA = re.compile(r"\[\[(\w+)\|([^\]]+)\]\]")
CODIGO = re.compile(r"`[^`]*`")


class Parada(Exception):
    """Condición que impide dar el informe por bueno; el mensaje dice cuál."""


# =================================================================================================================
# 3. El texto del borrador, versión 3
# =================================================================================================================
# Cada bloque: [apartado, tipo, contenido]. Tipos: h1, h2, h3, p, ul (una viñeta es un texto o [texto, [viñetas]]) y
# ol. Las cifras, [[nombre|como la escribe el texto]].
BLOQUES = [
    # -------------------------------------------------------------------------------------------------------------
    # 3.1 Título, subtítulo y resumen
    # -------------------------------------------------------------------------------------------------------------
    ["resumen", "h1", "La venta de [[dolares_2013_millones|6,1]] millones de dólares de 2013 cambia con el calendario "
                      "de forma distinta en cada departamento"],
    ["resumen", "p", "Informe para la Dirección de Operaciones de Tiendas"],
    ["resumen", "p", "Periodo analizado: 29 de enero de 2011 al 22 de mayo de 2014 | Datos disponibles hasta: "
                     "[[fecha_datos|22/05/2015]] | Emisión: 24/11/2026"],
    ["resumen", "h2", "Resumen ejecutivo"],
    ["resumen", "ul", [
        "En 2013, las combinaciones de departamento y tienda analizadas vendieron **[[dolares_2013|6.094.767]] "
        "dólares**, con [[unidades_2013|2.312.182]] unidades. Son 70: [[departamentos|7]] departamentos en 10 tiendas, con 500 de los "
        "3.049 productos de Walmart. No es la venta de la cadena entera.",
        "La venta está repartida: el 80 % de las unidades lo reúnen **[[departamentos_de_tienda_80_unidades|31]] "
        "combinaciones de departamento y tienda**.",
        "El calendario cambia la venta de cada departamento de forma distinta. Acción de Gracias la baja entre un "
        "**[[accion_gracias_bajada_min_pct|9,1]] % y un [[accion_gracias_bajada_max_pct|72,2]] %**. Los días en que se "
        "cobra la ayuda alimentaria pública (SNAP) suben la alimentación hasta un **[[snap_alimentacion_max_pct|24,0]] "
        "%**.",
        "El fin de semana manda: el día más fuerte vende entre **[[dia_cociente_min|1,22]] y "
        "[[dia_cociente_max|1,51]] veces** el más flojo. La época del año pesa menos.",
        "**[[cambios_de_nivel|28]] combinaciones de departamento y tienda** cambiaron de nivel de golpe y lo mantuvieron durante "
        "meses.",
        "En una prueba rápida, una primera previsión a 10 días falla **16,2 unidades de cada 100** vendidas. Gana a la "
        "regla sencilla que menos falla en 10 de 12 pruebas.",
    ]],
    ["resumen", "p", "Se pide al equipo directivo que apruebe tres acciones:"],
    ["resumen", "ol", [
        "**Construir y medir la previsión diaria de las 70 combinaciones de departamento y tienda.**",
        "**Decidir en cada departamento si se usa la previsión o una regla sencilla.**",
        "**Averiguar con los jefes de tienda qué explica los [[cambios_de_nivel|28]] cambios de nivel.**",
    ]],
    ["resumen", "p", "**La primera acción activa las otras dos:** sin la previsión medida no hay con qué comparar cada "
                     "departamento."],
    # -------------------------------------------------------------------------------------------------------------
    # 3.2 Conclusiones: lo que hemos encontrado
    # -------------------------------------------------------------------------------------------------------------
    ["conclusiones", "h2", "Conclusiones y recomendaciones"],
    ["encontrado", "h3", "Lo que hemos encontrado"],
    ["encontrado", "ul", [
        "**[[dolares_2013|6.094.767]] dólares en 2013.** Es la suma de los [[dias_2013|365]] días del año, producto a "
        "producto, con el precio de cada semana. La alimentación hace el [[parte_unidades_alimentacion_2013_pct|70,8]] "
        "% de las unidades y el [[parte_dolares_alimentacion_2013_pct|58,8]] % de los dólares.",
        "**[[departamentos_de_tienda_80_unidades|31]] para el 80 %.** Las [[departamentos_de_tienda|70]] combinaciones "
        "de departamento y tienda, ordenadas de mayor a menor venta en unidades entre el 29/01/2011 y el 22/05/2014. En dólares hacen "
        "falta [[departamentos_de_tienda_80_dolares|34]]. El departamento de alimentación FOODS_3 reúne el "
        "[[parte_unidades_foods_3_pct|48,7]] % de las unidades.",
        "**Del [[accion_gracias_bajada_min_pct|9,1]] % al [[accion_gracias_bajada_max_pct|72,2]] % en Acción de "
        "Gracias.** Cada día de fiesta se compara con el mismo día de la semana de las cuatro semanas anteriores, en "
        "cada departamento. Año Nuevo baja la venta entre un [[ano_nuevo_bajada_min_pct|20,0]] % y un "
        "[[ano_nuevo_bajada_max_pct|77,8]] %. SNAP se compara dentro de la primera quincena de cada mes, entre días con "
        "y sin la ayuda. Sube la alimentación del [[snap_alimentacion_min_pct|4,3]] % al "
        "[[snap_alimentacion_max_pct|24,0]] % y apenas mueve hogar y ocio.",
        "**De [[dia_cociente_min|1,22]] a [[dia_cociente_max|1,51]] veces.** Es la venta media del día más fuerte "
        "entre la del más flojo, en cada departamento; en los [[departamentos|7]] el más fuerte es sábado o domingo. "
        "Ningún mes completo se aparta más de un 9 % de la media.",
        "**[[cambios_de_nivel|28]] cambios de nivel.** Un cambio de nivel es una venta media de las trece semanas "
        "siguientes al menos 1,5 veces mayor o menor que la de las trece anteriores. De los [[cambios_de_nivel|28]], "
        "[[cambios_de_nivel_bajadas|7]] son bajadas. Diez son de un departamento de ocio, HOBBIES_2, que vende muy poco "
        "y a días sueltos. En la tienda WI_1 cambian [[cambios_mismo_dia_mayor|4]] departamentos el mismo día, el "
        "26/10/2012.",
        "**16,2 de cada 100.** Prueba rápida con una previsión para las 70 combinaciones de departamento y tienda a la vez, en 12 "
        "fechas del último año analizado. En dólares falla 17,8 de cada 100 a 28 días. Gana a la regla sencilla que "
        "menos falla en las 12 fechas. Las tres reglas sencillas son repetir la semana anterior, la media de los "
        "últimos 28 días y la media del mismo día de las 4 semanas anteriores.",
    ]],
    # -------------------------------------------------------------------------------------------------------------
    # 3.3 Límites
    # -------------------------------------------------------------------------------------------------------------
    ["limites", "h3", "Límites"],
    ["limites", "p", "Las cifras son de 500 de los 3.049 productos y no son la venta de Walmart. Los datos no traen "
                     "coste, margen ni existencias: no dicen cuánto dinero ahorraría una previsión ni si un día sin "
                     "ventas fue falta de producto. Los efectos del calendario describen diferencias; no prueban su "
                     "causa. La prueba rápida orienta. El veredicto lo da la medición con un año entero que el trabajo "
                     "no ha usado."],
    # -------------------------------------------------------------------------------------------------------------
    # 3.4 Recomendaciones
    # -------------------------------------------------------------------------------------------------------------
    ["recomendaciones", "h3", "Recomendaciones"],
    ["recomendaciones", "ol", [
        "**Construir y medir la previsión diaria de las 70 combinaciones de departamento y tienda.** Dos previsiones de cada una, en "
        "unidades a 10 días y en dólares a 28 días, medidas contra las tres reglas sencillas con un año que no se ha "
        "usado. **Quién:** el equipo de análisis, con la aprobación de la Dirección de Operaciones de Tiendas; **para "
        "cuándo:** pendiente. **Sale de:** la prueba rápida, que falla 16,2 unidades de cada 100.",
        "**Decidir en cada departamento si se usa la previsión o una regla sencilla.** Donde la previsión falle de "
        "media más que la regla sencilla que menos falla, se usa esa regla. **Quién:** la Dirección de Operaciones de "
        "Tiendas, con compras; **para cuándo:** al terminar la medición. **Sale de:** las "
        "[[departamentos_de_tienda_hobbies_2|10]] combinaciones de departamento y tienda de HOBBIES_2, que venden a días sueltos.",
        "**Averiguar con los jefes de tienda qué explica los [[cambios_de_nivel|28]] cambios de nivel.** Una reforma, "
        "un cambio de surtido o un error de carga. **Quién:** los jefes de las tiendas afectadas; **para cuándo:** "
        "pendiente. **Sale de:** los [[cambios_de_nivel|28]] cambios, [[cambios_mismo_dia_mayor|4]] de ellos en WI_1 "
        "el mismo día.",
    ]],
    # -------------------------------------------------------------------------------------------------------------
    # 3.5 Anexo, en página nueva
    # -------------------------------------------------------------------------------------------------------------
    ["anexo", "h2", TITULO_ANEXO],
    ["anexo", "p", "**Tablas y periodo.** La venta diaria de 500 productos en 10 tiendas de California, Texas y "
                   "Wisconsin, sus precios por semana y el calendario con los festivos y los días SNAP de cada estado. "
                   "Se analiza del 29/01/2011 al 22/05/2014, [[dias_analizados|1.210]] días. El año siguiente se "
                   "reserva para medir la previsión y el último año de los datos, para la prueba final."],
    ["anexo", "p", "**Pasos.** Se describió cada columna, se revisó la calidad y se corrigió lo necesario sin cambiar "
                   "ninguna venta. Después se montó una tabla con una fila por departamento, tienda y día, con la "
                   "venta en unidades y en dólares. Por último se exploró. Cada cifra se comprobó por un segundo "
                   "cálculo."],
    ["anexo", "p", "**Consultas.**"],
    ["anexo", "ul", [
        "¿Cuánto se vendió en 2013? [[dolares_2013|6.094.767]] dólares y [[unidades_2013|2.312.182]] unidades. De "
        "media, [[dolares_al_dia_2013|16.698]] dólares al día.",
        ["¿Qué parte vende cada categoría en 2013, en unidades y en dólares?", [
            "alimentación, el [[parte_unidades_alimentacion_2013_pct|70,8]] % y el "
            "[[parte_dolares_alimentacion_2013_pct|58,8]] %;",
            "hogar, el [[parte_unidades_hogar_2013_pct|20,1]] % y el [[parte_dolares_hogar_2013_pct|29,3]] %;",
            "ocio, el [[parte_unidades_ocio_2013_pct|9,1]] % y el [[parte_dolares_ocio_2013_pct|11,9]] %."]],
        "¿Cuántos días se queda una combinación de departamento y tienda sin ventas? Hay [[dias_cierre|175]] días de cierre de tienda "
        "y [[dias_25_diciembre|35]] de 25 de diciembre sin cierre. Otros [[dias_hobbies_2_a_cero|2.171]] son de "
        "HOBBIES_2, que vende a días sueltos.",
        "¿Qué días cambian la venta? Festivos, días SNAP y día de la semana, por departamento. El precio casi no "
        "cambia: en el periodo analizado, el [[sin_cambio_precio_pct|41,1]] % de los productos de cada tienda no "
        "cambió nunca de precio. No hay promociones.",
    ]],
    ["anexo", "p", "**Datos personales.** No hay: los datos son de productos, tiendas, precios y calendario (reglas de "
                   "negocio §9)."],
    ["anexo", "p", "**De dónde sale cada cifra.** Casi todas, de `informes/analisis-exploratorio__hechos_series.json`. "
                   "Las de 2013 salen del script de consultas de este informe; las de la prueba rápida, del reconocimiento "
                   "de reconocimiento de los datos."],
    ["anexo", "p", "**Fuentes externas.** [1] Concurso M5 Forecasting de Walmart en Kaggle y su guía de participantes "
                   "(2020)."],
]


# =================================================================================================================
# 4. Cifras: del JSON al texto
# =================================================================================================================
def cargar_cifras(datos):
    """Diccionario nombre -> valor de las cifras del JSON de consultas, con su fecha_datos."""
    cifras = {c["nombre"]: c["valor"] for c in datos["cifras"]}
    cifras["fecha_datos"] = datos.get("fecha_datos")
    return cifras


def escribir(nombre, valor, como_texto):
    """La cifra del JSON escrita como la escribe el texto: con sus decimales, coma decimal y punto de miles."""
    if nombre == "fecha_datos":
        return dt.date.fromisoformat(valor).strftime("%d/%m/%Y")
    decimales = len(como_texto.split(",")[1]) if "," in como_texto else 0
    return numero(valor, decimales)


def textos(bloques):
    """Todos los textos de los bloques, con su apartado y su tipo, viñetas anidadas incluidas."""
    for apartado, tipo, contenido in bloques:
        if tipo in ("ul", "ol"):
            for item in contenido:
                if isinstance(item, list):
                    yield apartado, tipo, item[0]
                    for sub in item[1]:
                        yield apartado, tipo, sub
                else:
                    yield apartado, tipo, item
        else:
            yield apartado, tipo, contenido


def con_json(texto, cifras):
    """El texto con cada cifra marcada sustituida por la del JSON (o por la del texto, si falta en el JSON)."""
    return MARCA.sub(lambda m: escribir(m[1], cifras[m[1]], m[2]) if m[1] in cifras else m[2], texto)


def comprobar_cifras(cifras, bloques=BLOQUES):
    """Errores de cifras: una que no sale como la escribe el texto, una que falta en el JSON o un número sin marcar."""
    errores = []
    for apartado, _, texto in textos(bloques):
        for m in MARCA.finditer(texto):
            if m[1] not in cifras:
                errores.append(f"{apartado}: la cifra {m[1]} ({m[2]}) no está en {CONSULTAS}")
                continue
            sale = escribir(m[1], cifras[m[1]], m[2])
            if sale != m[2]:
                errores.append(f"{apartado}: {m[1]} sale {sale} del JSON y el texto escribe {m[2]}")
        # Un número que no viene del JSON solo puede ser uno de SIN_JSON
        resto = CODIGO.sub(" ", MARCA.sub(" ", texto))
        for n in re.findall(r"\d+(?:,\d+)?", resto):
            if n not in SIN_JSON:
                errores.append(f"{apartado}: el número {n} no sale del JSON ni es un dato fijo")
    return errores


# =================================================================================================================
# 5. Palabras: topes y vetadas
# =================================================================================================================
def plano(texto, cifras):
    """Texto visible: las cifras del JSON, sin marcas de negrita; las comillas invertidas se quedan."""
    return con_json(texto, cifras).replace("**", "")


def texto_plano(bloques, cifras):
    """Todo el texto visible del informe en una cadena."""
    return "\n".join(plano(t, cifras) for _, _, t in textos(bloques))


def contar_palabras(bloques, cifras):
    """Palabras de cada apartado, sin sus encabezados H2 y H3: trozos entre espacios con una letra o una cifra."""
    cuenta = {a: 0 for a in TOPES}
    for apartado, tipo, texto in textos(bloques):
        if tipo in ("h2", "h3") or apartado not in cuenta:
            continue
        cuenta[apartado] += sum(1 for w in plano(texto, cifras).replace("`", "").split() if re.search(r"\w", w))
    return cuenta


def comprobar_topes(palabras):
    """Errores de los apartados que pasan de su tope."""
    return [f"el apartado {a} tiene {n} palabras y su tope es {TOPES[a]}" for a, n in palabras.items()
            if n > TOPES[a]]


def sin_jerga(texto):
    """Errores por cada palabra vetada fuera de un nombre de fichero entre comillas invertidas."""
    fuera = CODIGO.sub(" ", texto)
    patron = re.compile(r"\b(" + "|".join(VETADAS) + r")\b", re.IGNORECASE)
    return [f"palabra vetada: «{m[0]}»" for m in patron.finditer(fuera)]


# =================================================================================================================
# 6. Frases con sentido
# =================================================================================================================
def exigir(c, bloques=BLOQUES):
    """Errores de las frases que dicen un sentido o un grupo y que las cifras ya no sostienen."""
    aprobado = " ".join(MARCA.sub(lambda m: m[2], t) for _, _, t in textos(bloques)).replace("**", "")
    errores = []

    def frase(texto, condicion):
        """Apunta un error si la frase no está en el texto o si su condición no se cumple."""
        try:
            cumple = bool(condicion())
        except (KeyError, TypeError, ZeroDivisionError) as e:
            cumple = False
            texto = f"{texto} (falta {e})"
        if texto.split(" (falta")[0] not in aprobado:
            errores.append(f"exigir: la frase «{texto}» ya no está en el texto")
        elif not cumple:
            errores.append(f"exigir: «{texto}» no se cumple con las cifras del JSON")

    # El día más fuerte cae en sábado o domingo en todos los departamentos
    frase("el más fuerte es sábado o domingo", lambda: c["dias_fuertes_fin_de_semana"] == c["departamentos"])
    # Acción de Gracias baja la venta en todos los departamentos
    frase("Acción de Gracias la baja", lambda: c["accion_gracias_negativos"] == c["departamentos"])
    # SNAP apenas mueve hogar y ocio: menos de 5 puntos sin signo en cada uno (umbral fijado antes de medir)
    frase("apenas mueve hogar y ocio", lambda: max(abs(c["snap_resto_min_pct"]), abs(c["snap_resto_max_pct"])) < 5)
    # Ningún mes completo se aparta un 9 % o más de la media
    frase("Ningún mes completo se aparta más de un 9 %", lambda: c["mes_mayor_desvio_pct"] < 9)
    # La época del año pesa menos que el día de la semana: el mayor desvío de un mes, por debajo del menor efecto del día
    frase("La época del año pesa menos", lambda: c["mes_mayor_desvio_pct"] < (c["dia_cociente_min"] - 1) * 100)
    # Diez cambios de nivel son de HOBBIES_2
    frase("Diez son de un departamento de ocio", lambda: c["cambios_de_nivel_hobbies_2"] == 10)
    # El mayor grupo de cambios del mismo día es el de WI_1 el 26/10/2012
    frase("En la tienda WI_1 cambian", lambda: c["cambios_mismo_dia_tienda"] == "WI_1"
          and c["cambios_mismo_dia_fecha"] == "2012-10-26")
    return errores


# =================================================================================================================
# 7. HTML
# =================================================================================================================
ESTILO = """
@page { size: A4; margin: 20mm; }
html, body { background: #ffffff; color: #0b0b0b; }
body { margin: 0; font-family: "Segoe UI", sans-serif; font-size: 11pt; line-height: 1.4; }
h1, h2, h3 { font-weight: bold; color: #0b0b0b; line-height: 1.25; }
h1 { font-size: 18pt; margin: 0 0 6pt; }
h2 { font-size: 14pt; margin: 14pt 0 4pt; }
h3 { font-size: 12pt; margin: 10pt 0 4pt; }
p { margin: 0 0 6pt; }
ul { list-style: disc; margin: 0 0 6pt; padding-left: 18pt; }
ul ul { list-style: circle; margin: 3pt 0 0; }
ol { list-style: decimal; margin: 0 0 6pt; padding-left: 18pt; }
li { margin: 0 0 3pt; }
strong { font-weight: bold; }
code { font-family: Consolas, "Courier New", monospace; }
* { text-decoration: none; box-shadow: none; }
section.anexo { break-before: page; }
"""


def en_linea(texto, cifras):
    """Un texto en HTML: cifras del JSON, negrita y nombres de fichero en letra de código."""
    t = html.escape(con_json(texto, cifras), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)


def lista(tipo, items, cifras):
    """Una lista con viñetas o numerada; una viñeta [texto, [viñetas]] lleva su lista anidada."""
    partes = []
    for item in items:
        if isinstance(item, list):
            partes.append(f"<li>{en_linea(item[0], cifras)}{lista('ul', item[1], cifras)}</li>")
        else:
            partes.append(f"<li>{en_linea(item, cifras)}</li>")
    return f"<{tipo}>" + "".join(partes) + f"</{tipo}>"


def montar_html(cifras, bloques=BLOQUES):
    """El documento entero; el anexo va en su sección, que empieza en página nueva."""
    cuerpo, en_anexo = [], False
    for apartado, tipo, contenido in bloques:
        if apartado == "anexo" and not en_anexo:
            cuerpo.append('<section class="anexo">')
            en_anexo = True
        if tipo in ("h1", "h2", "h3", "p"):
            cuerpo.append(f"<{tipo}>{en_linea(contenido, cifras)}</{tipo}>")
        elif tipo in ("ul", "ol"):
            cuerpo.append(lista(tipo, contenido, cifras))
    if en_anexo:
        cuerpo.append("</section>")
    return ("<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<title>Informe ejecutivo · previsión de ventas de Walmart</title>\n"
            f"<style>{ESTILO}</style>\n</head>\n<body>\n" + "\n".join(cuerpo) + "\n</body>\n</html>\n")


# =================================================================================================================
# 8. PDF y páginas
# =================================================================================================================
def imprimir_pdf(ruta_html, ruta_pdf):
    """Imprime el HTML a PDF con Edge sin ventana y espera a que el PDF exista y deje de crecer."""
    if ruta_pdf.exists():
        ruta_pdf.unlink()
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={ruta_pdf}", ruta_html.resolve().as_uri()],
                   capture_output=True, timeout=ESPERA_MAXIMA_S)
    limite, anterior = time.monotonic() + ESPERA_MAXIMA_S, -1
    while time.monotonic() < limite:
        tam = ruta_pdf.stat().st_size if ruta_pdf.exists() else -1
        if tam > 0 and tam == anterior:
            return
        anterior = tam
        time.sleep(INTERVALO_S)
    raise Parada(f"Edge no dejó un PDF terminado en {ESPERA_MAXIMA_S} s")


def comprobar_paginas(paginas):
    """Errores de paginación: el anexo en página solo suya, lo anterior en dos páginas y tres como mucho en total."""
    errores = []
    if len(paginas) > 3:
        errores.append(f"el PDF tiene {len(paginas)} páginas y el tope es 3")
    normal = [" ".join(p.split()) for p in paginas]
    donde = [i for i, p in enumerate(normal) if TITULO_ANEXO in p]
    if not donde:
        return errores + ["el PDF no tiene el anexo"]
    i = donde[0]
    if not normal[i].startswith(TITULO_ANEXO):
        errores.append(f"el anexo empieza en la página {i + 1} detrás de otro texto: no tiene la página para él")
    if i > 2:
        errores.append(f"lo anterior al anexo ocupa {i} páginas y tiene que caber en dos")
    return errores


# =================================================================================================================
# 9. Ejecución
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def principal(raiz):
    """Comprueba el texto contra el JSON, escribe el HTML, imprime el PDF y comprueba sus páginas."""
    ruta_consultas = raiz / CONSULTAS
    if not ruta_consultas.exists():
        raise Parada(f"falta {CONSULTAS}: se crea con scripts/07_consultas_informe_ejecutivo.py")
    datos = json.loads(ruta_consultas.read_text(encoding="utf-8"))
    if datos.get("estado") != "OK" or datos.get("fecha_datos") != FECHA_DATOS:
        raise Parada(f"{CONSULTAS} no está en OK o su fecha_datos no es {FECHA_DATOS}")
    cifras = cargar_cifras(datos)

    # Las cuatro comprobaciones del texto, todas antes de escribir nada
    palabras = contar_palabras(BLOQUES, cifras)
    errores = (comprobar_cifras(cifras) + comprobar_topes(palabras) + sin_jerga(texto_plano(BLOQUES, cifras))
               + exigir(cifras))
    if errores:
        raise Parada("\nERROR: ".join(errores))

    # HTML y PDF
    ruta_html, ruta_pdf = raiz / HTML, raiz / PDF
    ruta_html.write_text(montar_html(cifras), encoding="utf-8")
    imprimir_pdf(ruta_html, ruta_pdf)
    paginas = [p.extract_text() or "" for p in PdfReader(ruta_pdf).pages]
    errores_pdf = comprobar_paginas(paginas)
    anexo = next((i + 1 for i, p in enumerate(paginas) if TITULO_ANEXO in " ".join(p.split())), None)

    # Resumen del informe, con su estado calculado
    estado = "ERROR" if errores_pdf else "OK"
    resumen = {
        "script": SCRIPT,
        "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
        "estado": estado,
        "errores": errores_pdf,
        "palabras": {a: {"palabras": n, "tope": TOPES[a]} for a, n in palabras.items()},
        "regla_de_palabras": "texto visible sin los encabezados H2 y H3 del apartado; palabra = trozo entre espacios "
                             "con una letra o una cifra; el resumen cuenta el título y el subtítulo",
        "paginas": {"total": len(paginas), "anexo_empieza_en": anexo},
        "huellas": {CONSULTAS: sha256(ruta_consultas), HTML: sha256(ruta_html), PDF: sha256(ruta_pdf)},
    }
    (raiz / RESUMEN).write_text(json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                encoding="utf-8")
    if errores_pdf:
        raise Parada("\nERROR: ".join(errores_pdf))
    print(f"OK: {HTML}, {PDF} ({len(paginas)} páginas, anexo en la {anexo}) y {RESUMEN}; palabras {palabras}")


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso")
    raiz = Path(argumentos.parse_args().raiz).resolve()
    print(f"Python: {sys.executable}")
    try:
        principal(raiz)
    except Parada as e:
        print(f"ERROR: {e}")
        sys.exit(1)
