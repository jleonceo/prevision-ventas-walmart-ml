"""Informe final del caso 69 para la Dirección de Operaciones de Tiendas: un HTML por resultados y el CSV de sus
gráficos.

Lee (y no cambia) seis JSON de informes/, que tienen que existir, traer la misma fecha de datos (2015-05-22) y ser
más nuevos que el script que los crea:
- prueba_final.json (scripts/20_prueba_final.py): el último año guardado, del 23/05/2015 al 22/05/2016
  (fin_prueba_final), con el modelo en uso (variante reentrenado, el de produccion/configuracion.json) y el del año de
  comprobación (variante tal_como_esta). De aquí salen las cifras principales desde la versión 4 del texto;
- validacion.json (scripts/16_validacion.py): el año de comprobación, del 23/05/2014 al 22/05/2015. Quedan de él la
  página 4 (la ventaja sin WI_2 y WI_3), el exceso del modelo de ese año y el periodo de la portada;
- analisis-exploratorio__hechos_series.json (scripts/06_analisis_exploratorio.py): la pregunta 4, los ceros, los saltos
  de nivel, los productos y el periodo de la construcción;
- business_case.json (scripts/09_business_case.py): la venta de 2013, los tres escenarios a tres años y los supuestos
  del cálculo, con su origen;
- busqueda.json (scripts/15_busqueda.py): las fechas de la venta con que se ajustó el modelo del año de comprobación;
- particion.json (scripts/10_particion.py): los días del año de comprobación (la parte de validación).
Lee también produccion/configuracion.json, solo para comprobar que el modelo en uso es el reentrenado de la prueba
final.

Deja informes/informe_final.html e informes/informe_final_graficos.csv. No deja PDF: informe.py no lo hace.

El texto es el de config/metodo/borrador_informe_final.md, versión 5: la versión 4 (propuesta_informe_final_v4.md
§3, «Apruebo los nueve», con las correcciones de su §5) con los cambios de propuesta_informe_final_v5.md §2
y §2 bis (la tercera pasada), que el responsable del caso mandó montar el 25/11/2026 («revisar todo otra vez y actualizar»); los que no
caben en la pantalla o pasan de 150 palabras lo dicen en un comentario donde irían. Desde el título del informe hasta el
anexo; las notas para el responsable del caso no van. No se cambia ninguna frase: el script compara al final cada frase del borrador con
el texto visible del HTML y para si alguna no está. Lo único que se añade es lo que piden las reglas de salida y el
petición: la fuente bajo cada tabla, los subtítulos y fuentes de los gráficos, las páginas que cita cada «Por qué» de
las decisiones y la columna de página de la tabla de cifras del anexo (las dos, comprobadas contra el panel).

No calcula ninguna cifra salvo cuatro proporciones (el 14,2 % y el 12,9 %: la ventaja entre el error de la regla que
menos falla, que es 1 menos el error del modelo entre el de la regla, con las cifras del veredicto; el 27,7 % y el
32,2 % de la cadena: 1 menos el error del modelo entre el de la regla, con las cifras sin redondear), las diferencias
que se escriben a dos
decimales (las cifras leídas, restadas), los supuestos sin fuente (contados), los años de cada festivo (sus días
entre las tiendas) y el primer día del último año (el día siguiente al primer día de partida). Cada cifra se lee de su
JSON y se escribe a la española, con el redondeo del texto; cada frase que nombra un grupo, un sentido o un «todos»
lleva delante un exigir() que para si los datos ya no la sostienen. Al montar comprueba además que las páginas que
cita el texto son las del panel. No importa ningún script del caso: solo las piezas comunes de assets/ (informe.py y
graficos.py), que no ejecutan nada al importarse.

Uso, desde cualquier carpeta:
    python -W error scripts/18_informe_final.py
"""

# csv escribe las cifras de los gráficos
import csv
# html limpia el texto visible para las guardias
import html
# json lee las entradas
import json
# re busca la jerga, los sinónimos, las cifras y las frases
import re
# sys añade assets/ a la ruta de importación y comprueba el intérprete
import sys
# date y timedelta cuentan los días entre dos fechas y dan el día siguiente
from datetime import date, timedelta
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

# =====================================================================================================================
# CONFIGURACIÓN
# =====================================================================================================================

# Carpeta del caso, calculada desde el propio script para que funcione lo lance quien lo lance
RAIZ = Path(__file__).resolve().parents[1]
# Las piezas comunes se usan desde assets/, sin copiarlas
sys.path.insert(0, str(RAIZ / "assets"))

# Piezas comunes: el informe y los gráficos
from informe import Informe  # noqa: E402
from graficos import numero, barras_ordenadas, ANCHO_FILA  # noqa: E402

# Intérprete del caso
ENTORNO = "69_prevision_ventas_walmart"
# Carpeta de los informes y salidas
INFORMES = RAIZ / "informes"
SALIDA_HTML = INFORMES / "informe_final.html"
SALIDA_CSV = INFORMES / "informe_final_graficos.csv"
# Texto aprobado, con el que se compara el HTML al terminar
BORRADOR = RAIZ / "config" / "metodo" / "borrador_informe_final.md"
# Configuración de producción: dice cuál es el modelo en uso
CONFIGURACION = RAIZ / "produccion" / "configuracion.json"

# Los JSON que lee el informe; todos con la misma fecha de datos (programacion-del-caso, SC-65)
FECHA_DATOS = "2015-05-22"
VALIDACION = "validacion.json"
EXPLORATORIO = "analisis-exploratorio__hechos_series.json"
NEGOCIO = "business_case.json"
BUSQUEDA = "busqueda.json"
PARTICION = "particion.json"
PRUEBA_FINAL = "prueba_final.json"
ENTRADAS = [VALIDACION, EXPLORATORIO, NEGOCIO, BUSQUEDA, PARTICION, PRUEBA_FINAL]
# El último día del último año guardado: con esta fecha se rotulan sus cifras (fin_prueba_final de prueba_final.json)
FIN_PRUEBA_FINAL = "2016-05-22"
# Las dos variantes de la prueba final: el modelo en uso y el del año de comprobación, tal como salió de ese año
EN_USO = "reentrenado"
ANTERIOR = "tal_como_esta"
# Los dos objetivos de la previsión, y cómo se escriben en el texto
OBJETIVOS = ("unidades", "dolares")
OBJETIVO_TEXTO = {"unidades": "unidades", "dolares": "dólares"}

# Las tres reglas sencillas con su nombre entero (reglas, apartado 7 y hoja de vocabulario del lector)
REGLAS = {"repetir_semana_anterior": "repetir la semana anterior",
          "media_28_dias": "la media de los últimos 28 días",
          "media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores"}
# La regla que menos falla en el veredicto y en los grupos de la página 3
REGLA_PRINCIPAL = "media_mismo_dia_4_semanas"
# Festivos con su nombre en español (hoja de vocabulario); prueba_final.json ya los trae en español
FESTIVOS = {"Thanksgiving": "Acción de Gracias", "Christmas": "Navidad", "NewYear": "Año Nuevo"}
# Estados y categorías con su nombre para el lector, en el orden de la tabla de la página 3
ESTADOS = {"CA": "California", "TX": "Texas", "WI": "Wisconsin"}
CATEGORIAS = {"FOODS": "Alimentación", "HOBBIES": "Ocio", "HOUSEHOLD": "Hogar"}
# Departamentos de la tabla de la página 5, con su categoría la primera vez
DEPARTAMENTOS_PAGINA_5 = {"FOODS_3": "FOODS_3, alimentación", "HOBBIES_2": "HOBBIES_2, ocio",
                          "HOUSEHOLD_2": "HOUSEHOLD_2, hogar"}
# Meses en español, para «mayo de 2014»
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

# Título del informe (versión A)
TITULO = "La previsión del modelo falla menos que las reglas sencillas en casi todas las tiendas y departamentos"
# Los recuentos que el texto escribe con letra («seis de los siete departamentos», «cuatro decisiones»)
EN_LETRA = {1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho", 9: "nueve",
            10: "diez"}
# «Casi no se pasa» y «ya no se pasa de media»: el exceso del modelo en uso, por debajo de 0,5 por cada 100 en valor
# absoluto (petición 30, como el «casi en cero» de la petición 25)
CASI_CERO = 0.5
# «Empatan»: modelo y regla se separan menos de 0,05, la mitad del decimal con que el informe da los errores
EMPATE = 0.05
# Fuentes de tablas y gráficos en palabras del lector (F1)
FUENTE_PAGINAS = "páginas de este informe"
# Las páginas que cita el texto, con el rótulo que tienen en el panel: el resumen manda a la 15 y a las 3 a 15
# (cambio 5 de la versión 5) y cada «Por qué» de las decisiones a las suyas. Van las quince, para que el panel entero
# quede comprobado. Si una página se parte, las de detrás se corren y el script para
REFERENCIAS = {1: "Resumen", 2: "Resumen, las cuatro preguntas", 3: "Qué se prevé", 4: "El modelo frente a las reglas",
               5: "El modelo frente a las reglas, gráfico", 6: "La previsión sumada", 7: "La previsión sumada, gráfico",
               8: "La previsión sumada, análisis", 9: "Dónde gana y dónde no", 10: "Qué usar en cada departamento",
               11: "El exceso", 12: "Los días que cambian", 13: "El dinero", 14: "Límites",
               15: "Decisiones propuestas"}
# Los otros cuatro departamentos, los del anexo (cambio 17): los que no van en la tabla de la página 10
OTROS_CUATRO = ["FOODS_1", "FOODS_2", "HOBBIES_1", "HOUSEHOLD_1"]
# La única excepción a la media del mismo día como regla que menos falla: por tienda (cambio 22) y en los otros cuatro
# departamentos (cambio 27), con su objetivo
EXCEPCION_TIENDA = ("WI_2", "unidades")
EXCEPCION_DEPARTAMENTO = ("FOODS_1", "dolares")
# El plazo de cada objetivo en la nota de las tablas (cambio 28)
NOTA_PLAZO = "Unidades a {u} días; dólares a {d}."

# Jerga que no puede salir fuera del anexo: los nombres internos del análisis y los de código y fichero. Cada patrón
# lleva sus banderas: los códigos de tienda y departamento (WI_2, FOODS_3) sí se usan, así que el de nombres de
# columna distingue mayúsculas
JERGA = [(r"\borígen(?:es)?\b|\borigen(?:es)?\b", re.I), (r"\bvalidaci[oó]n\b", re.I),
         (r"\bconstrucci[oó]n\b", re.I), (r"\bseries?\b", re.I), (r"\bsesgos?\b", re.I), (r"\bwape\b", re.I),
         (r"\brival(?:es)?\b", re.I), (r"\bhorizonte\b(?! de la previsión)", re.I), (r"\bd[ií]as? SNAP\b", 0),
         (r"HistGradientBoosting", re.I), (r"\b[a-z0-9]+_[a-z0-9_]+\b", 0),
         (r"\.(?:json|csv|py|parquet|md|html)\b", re.I)]
# Términos internos que nunca van en un título (patrón §4, guardia de títulos), además de los de la jerga
INTERNOS_TITULO = [r"\bregla corregida\b", r"\bpuntos\b", r"\bbanco\b", r"\breceta\b"]

# Guardia de sinónimos: cada término fijado en la hoja de vocabulario del lector con lo que «No se usa». Vale en todo
# el informe, anexo incluido
SINONIMOS = {
    "combinación de departamento y tienda": [r"\bseries?\b", r"\bdepartamentos? de tienda\b"],
    "el código del departamento": [r"\bdepartamento \d\b"],
    "alimentación, ocio y hogar": [r"\bfamilias?\b", r"\bsecci[oó]n(?:es)?\b"],
    "tienda": [r"\bsucursal(?:es)?\b", r"\blocal(?:es)?\b"],
    "la previsión": [r"\bpredicci[oó]n(?:es)?\b", r"\bpron[oó]sticos?\b", r"\bestimaci[oó]n(?:es)?\b"],
    "el modelo de previsión": [r"\bel algoritmo\b", r"\bla IA\b", r"\bHGB\b"],
    "las tres reglas con su nombre entero": [r"\bla mejor regla\b", r"\bel método actual\b"],
    "la regla que menos falla": [r"\bel rival\b", r"\bbenchmark\b", r"\bla referencia\b"],
    "el error": [r"\bWAPE\b", r"\bporcentaje de error\b", r"\bprecisi[oó]n\b"],
    "la ventaja": [r"\bmejoras?\b", r"\bganancias?\b", r"\blift\b"],
    "el día desde el que se prevé": [r"\borigen(?:es)?\b", r"\bcortes?\b"],
    "el año de comprobación": [r"\btest\b", r"\bconjunto de validaci[oó]n\b"],
    "el último año, guardado para confirmar": [r"\bhold-out\b"],
    "día de cobro de la ayuda alimentaria (SNAP)": [r"\bd[ií]as? SNAP\b"],
    "festivo con su nombre en español": [r"\bThanksgiving\b", r"\bChristmas\b", r"\bNewYear\b"],
    "día en que la tienda cierra": [r"\bd[ií]as? sin ventas\b"],
    "el pedido": [r"\breposici[oó]n\b", r"\baprovisionamiento\b"],
    "se prevé día a día": [r"\brecursiv[oa]s?\b", r"\bautorregresiv[oa]s?\b"],
    "se compara con lo que se vendió": [r"\bse evalúa\b", r"\bse valida\b"],
}
# Las frases aprobadas en que «mejora» no es la ventaja sino el supuesto de los escenarios del dinero (business case):
# no son el sinónimo vetado y se dejan fuera de la búsqueda. «mejoras supuestas» es de la versión 1 y se queda: no
# estorba y la prueba la usa. La cifra clave «La mejora, la venta perdida…» de la versión 2 ya no está (versión 3)
EXCEPCIONES_SINONIMOS = ["mejoras supuestas", "suponen la mejora"]
# Origen de un supuesto del business case que tiene fuente; los demás no la tienen
CON_FUENTE = "fuente pública"

# Lo que la guardia de cifras no tiene que encontrar en un JSON porque no es una cifra de los datos: los nombres de las
# reglas, los códigos, las referencias a páginas y acciones, la unidad «por cada 100», los números de las preguntas
# del resumen, el nombre del concurso y la cuenta de las proporciones del anexo
NO_SON_CIFRAS = ([re.escape(n) for n in REGLAS.values()] + [re.escape(n[:1].upper() + n[1:]) for n in REGLAS.values()]
                 + [r"\b[A-Z]+_\d+\b", r"\bM5\b", r"\bpágs?\. \d+(?:(?:, | y | a )\d+)*", r"\bpágina \d+\b",
                    r"\bpáginas \d+ a \d+\b",
                    r"\bacciones \d+ y \d+\b", r"\bacción \d+\b", r"\bcada 100\b", r"\bpor 100\b",
                    r"(?<![\d.,])\b\d\. (?=[A-ZÁÉÍÓÚ])", r"\b1 menos el error\b"])


# =====================================================================================================================
# AYUDAS
# =====================================================================================================================

# Cifras escritas en el informe, tal como se escriben y sin signo: la guardia de cifras busca aquí cada número del
# texto visible. Se vacía al empezar cada informe
LEIDAS = set()


def exigir(condicion, frase):
    """Para si los datos ya no sostienen la frase que se va a escribir."""
    # Una frase falsa no se escribe
    if not condicion:
        raise ValueError(f"exigir: los datos ya no sostienen «{frase}»")


def leer_entradas(carpeta):
    """Lee los JSON de entrada de `carpeta`, en UTF-8, y los devuelve por nombre."""
    # Cada uno tiene que existir
    faltan = [n for n in ENTRADAS if not (Path(carpeta) / n).is_file()]
    if faltan:
        raise ValueError(f"faltan entradas en {carpeta}: {faltan}")
    # Se leen todos
    return {n: json.loads((Path(carpeta) / n).read_text(encoding="utf-8")) for n in ENTRADAS}


def comprobar_fechas(entradas):
    """Para si algún JSON no trae la fecha de datos del caso (SC-65) o la prueba final no acaba en su día."""
    # Los que traen otra fecha o ninguna
    distintas = {n: d.get("fecha_datos") for n, d in entradas.items() if d.get("fecha_datos") != FECHA_DATOS}
    if distintas:
        raise ValueError(f"fecha_datos distinta de {FECHA_DATOS} o ausente: {distintas}")
    # El último año guardado acaba en fin_prueba_final: con esa fecha se rotulan sus cifras
    fin = entradas.get(PRUEBA_FINAL, {}).get("fin_prueba_final")
    if fin != FIN_PRUEBA_FINAL:
        raise ValueError(f"fin_prueba_final de {PRUEBA_FINAL} distinto de {FIN_PRUEBA_FINAL} o ausente: {fin}")


def comprobar_orden(entradas):
    """Para si algún JSON es más viejo que el script que lo crea (errores 2 y 28 de programacion-del-caso)."""
    # El JSON tiene que ser posterior a su script
    viejos = [n for n, d in entradas.items()
              if (INFORMES / n).stat().st_mtime < (RAIZ / d["script"]).stat().st_mtime]
    if viejos:
        raise ValueError(f"orden: estos JSON son más viejos que el script que los crea; relánzalo: {viejos}")


# ---------------------------------------------------------------------------------------------------------------------
# Cifras a la española, apuntadas para la guardia de cifras
# ---------------------------------------------------------------------------------------------------------------------

def apunta(texto):
    """Apunta una cifra escrita, sin su signo, y la devuelve tal cual."""
    LEIDAS.add(texto.lstrip("+−-"))
    return texto


def num(x, decimales=1, signo=False):
    """Un número leído de un JSON, a la española, con su redondeo (Excel: los empates se alejan del cero)."""
    return apunta(numero(x, decimales, con_signo=signo))


def ent(x):
    """Un entero leído de un JSON: 3049 -> «3.049»."""
    return num(x, 0)


def pct(x, decimales=1, signo=False):
    """Un porcentaje ya en tanto por cien: 12,74 -> «12,7 %»."""
    return num(x, decimales, signo) + " %"


def usd(x, signo=False):
    """Dólares sin decimales: −94839,9 -> «−94.840 $»."""
    return num(x, 0, signo) + " $"


def fecha(iso):
    """Una fecha AAAA-MM-DD como la lee la Dirección: «23/05/2014»."""
    a, m, d = iso[:10].split("-")
    return apunta(f"{d}/{m}/{a}")


def anio(iso):
    """El año de una fecha AAAA-MM-DD: «2012»."""
    return apunta(iso[:4])


def mes_y_anio(iso):
    """El mes y el año de una fecha: «mayo de 2014»."""
    return f"{MESES[int(iso[5:7]) - 1]} de {anio(iso)}"


def dia_y_mes(iso):
    """El día y el mes de una fecha: «25 de diciembre»."""
    return f"{apunta(str(int(iso[8:10])))} de {MESES[int(iso[5:7]) - 1]}"


def en_tabla(x, decimales=1):
    """Un número que va a una celda de tabla: informe.py lo escribe; aquí se apunta cómo saldrá."""
    num(x, decimales)
    return x


def paginas(*numeros, seguidas=False):
    """«(pág. 9)», «(págs. 4 y 10)», «(págs. 4, 10 y 12)» o, con `seguidas` y dos, «(págs. 6 a 8)»: las páginas que
    cita un «Por qué». Cada una tiene que estar en REFERENCIAS, que comprobar_referencias() contrasta con el panel."""
    numeros = list(numeros)
    exigir(numeros and all(n in REFERENCIAS for n in numeros),
           f"las páginas {numeros} están entre las que se comprueban")
    exigir(not seguidas or len(numeros) == 2, "«a» solo une dos páginas")
    if len(numeros) == 1:
        return f"(pág. {numeros[0]})"
    if seguidas:
        return f"(págs. {numeros[0]} a {numeros[1]})"
    return "(págs. " + ", ".join(str(n) for n in numeros[:-1]) + f" y {numeros[-1]})"


def nota_plazo(c):
    """«Unidades a 10 días; dólares a 28.»: el plazo de cada objetivo, en la nota de una tabla (cambio 28)."""
    return NOTA_PLAZO.format(u=ent(c["unidades"]["horizonte"]), d=ent(c["dolares"]["horizonte"]))


# ---------------------------------------------------------------------------------------------------------------------
# Cifras de los gráficos (F3)
# ---------------------------------------------------------------------------------------------------------------------

def apuntar(filas, pagina, grafico, grupo, medida, cifra, unidad):
    """Apunta una cifra de un gráfico para el CSV (F3)."""
    filas.append({"pagina": pagina, "grafico": grafico, "grupo": grupo, "medida": medida, "cifra": cifra,
                  "unidad": unidad})


def escribir_csv(ruta, filas):
    """CSV de las cifras de los gráficos: punto y coma, coma decimal y UTF-8 con marca (patrón §6)."""
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(["pagina", "grafico", "grupo", "medida", "cifra", "unidad"])
        # Cada cifra con coma decimal, hasta cuatro decimales y sin ceros de más
        for fila in filas:
            cifra = f"{float(fila['cifra']):.4f}".rstrip("0").rstrip(".").replace(".", ",")
            escritor.writerow([fila["pagina"], fila["grafico"], fila["grupo"], fila["medida"], cifra, fila["unidad"]])


# =====================================================================================================================
# GUARDIAS
# =====================================================================================================================

def _sin_codigo(texto_html):
    """El HTML sin estilos, scripts, comentarios, dibujos SVG ni el <title> de la cabecera."""
    limpio = re.sub(r"<(script|style|svg|title)\b.*?</\1>", " ", texto_html, flags=re.S)
    return re.sub(r"<!--.*?-->", " ", limpio, flags=re.S)


def _texto(fragmento_html):
    """Texto visible de un trozo de HTML, con los espacios juntados."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento_html)).split())


def visible(texto_html):
    """Todo el texto que se ve: panel y páginas, sin los dibujos."""
    return _texto(_sin_codigo(texto_html))


def paginas_visibles(texto_html):
    """[(id, texto visible)] de cada página del HTML."""
    return [(ident, _texto(cuerpo)) for ident, cuerpo in
            re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>', _sin_codigo(texto_html), flags=re.S)]


def sin_jerga(texto_html, excluir):
    """Para si el texto visible fuera del anexo lleva un nombre interno o de código. `excluir`: ids del anexo."""
    encontrados = []
    # Cada página, por su id; el anexo queda fuera
    for ident, texto in paginas_visibles(texto_html):
        if ident in excluir:
            continue
        for patron, banderas in JERGA:
            encontrados += [f"{ident}: «{m.group(0)}»" for m in re.finditer(patron, texto, flags=banderas)]
    if encontrados:
        raise ValueError("jerga fuera del anexo: " + "; ".join(sorted(set(encontrados))))


def sin_sinonimos(texto_html):
    """Para si alguna página, anexo incluido, usa lo que la hoja de vocabulario dice que no se usa."""
    encontrados = []
    for ident, texto in paginas_visibles(texto_html):
        # Las dos frases aprobadas en que «mejora» es el supuesto de los escenarios
        for excepcion in EXCEPCIONES_SINONIMOS:
            texto = texto.replace(excepcion, " ")
        for termino, patrones in SINONIMOS.items():
            for patron in patrones:
                # «la IA» y los nombres en inglés distinguen mayúsculas; el resto, no
                banderas = 0 if patron in (r"\bla IA\b", r"\bHGB\b") else re.I
                encontrados += [f"{ident}: «{m.group(0)}» (se dice «{termino}»)"
                                for m in re.finditer(patron, texto, flags=banderas)]
    if encontrados:
        raise ValueError("sinónimo vetado por la hoja de vocabulario: " + "; ".join(sorted(set(encontrados))))


def titulos_claros(titulos):
    """Para si un título lleva dos puntos, un código o una letra suelta sin su nombre, o un término interno."""
    malos = []
    for t in titulos:
        # Dos puntos parten el título (T1)
        if ":" in t:
            malos.append(f"«{t}» lleva dos puntos")
        # Un código de departamento o de tienda va detrás de su nombre: «el departamento de ocio HOBBIES_2»
        for m in re.finditer(r"\b[A-Z]+_\d+\b", t):
            antes = t[:m.start()].lower()
            if not re.search(r"(departamento de (?:alimentación|ocio|hogar)|tienda) $", antes):
                malos.append(f"«{t}» lleva el código {m.group(0)} sin su nombre")
        # Una letra suelta en lugar del nombre («En B…»)
        for m in re.finditer(r"(?<![\wÁÉÍÓÚÑáéíóúñ])[A-Z](?![\wÁÉÍÓÚÑáéíóúñ])", t):
            malos.append(f"«{t}» lleva la letra suelta {m.group(0)}")
        # Un término interno del análisis
        for patron, banderas in JERGA + [(x, re.I) for x in INTERNOS_TITULO]:
            if re.search(patron, t, flags=banderas):
                malos.append(f"«{t}» lleva un término interno ({patron})")
    if malos:
        raise ValueError("título que no se entiende solo: " + "; ".join(malos))


def cifras_leidas(texto_html, leidas):
    """Para si en el texto visible de una página hay una cifra que no se leyó de ningún JSON. `leidas`: las escritas.

    Los dibujos quedan fuera: sus cifras las escribe graficos.py con los valores que se le pasan, que salen de los
    JSON. Lo que no es una cifra de los datos (NO_SON_CIFRAS) se quita antes de buscar.
    """
    malas = []
    for ident, texto in paginas_visibles(texto_html):
        for patron in NO_SON_CIFRAS:
            texto = re.sub(patron, " ", texto)
        # Las fechas, enteras; después, los números con punto de miles y coma decimal
        for m in re.finditer(r"\b\d{2}/\d{2}/\d{4}\b", texto):
            if m.group(0) not in leidas:
                malas.append(f"{ident}: «{m.group(0)}»")
        texto = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", " ", texto)
        for m in re.finditer(r"\d+(?:\.\d{3})*(?:,\d+)?", texto):
            if m.group(0) not in leidas:
                malas.append(f"{ident}: «{m.group(0)}»")
    if malas:
        raise ValueError("cifra que no se leyó de ningún JSON: " + "; ".join(sorted(set(malas))))


def frases_aprobadas(aprobado_md):
    """Las frases del texto aprobado, desde el título del informe hasta el anexo, sin las notas para el responsable del caso.

    Quita lo que no es texto del lector (las líneas «Gráfico:», los rótulos «Métricas clave», las rayas y las marcas de
    Markdown) y parte cada bloque en frases, para buscarlas una a una en el HTML.
    """
    lineas = aprobado_md.splitlines()
    # Empieza en el título del informe: el primer título de nivel 1 que no es el de las notas
    inicio = next(i for i, l in enumerate(lineas) if l.startswith("# ") and not l.startswith("# Notas para el responsable del caso"))
    bloques, actual = [], []
    for linea in lineas[inicio:] + [""]:
        limpia = linea.strip()
        # Un bloque acaba en una línea vacía, una raya o una fila de tabla
        if not limpia or limpia == "---" or limpia.startswith("|") or limpia.startswith("#") or limpia.startswith("- "):
            if actual:
                bloques.append(" ".join(actual))
                actual = []
        if not limpia or limpia == "---" or re.fullmatch(r"\|[-| ]+\|", limpia):
            continue
        # Las filas de tabla, celda a celda
        if limpia.startswith("|"):
            bloques += [c.strip() for c in limpia.strip("|").split("|") if c.strip()]
            continue
        # Los títulos: el de una página dice su rótulo detrás de «·»
        if limpia.startswith("#"):
            titulo = limpia.lstrip("#").strip()
            bloques.append(titulo.split(" · ", 1)[1] if " · " in titulo else titulo)
            continue
        actual.append(limpia[2:] if limpia.startswith("- ") else limpia)
    frases = []
    for bloque in bloques:
        # La descripción del gráfico y el rótulo «Métricas clave» no son texto del lector
        if bloque.startswith("**Gráfico:**") or bloque == "**Métricas clave**":
            continue
        # Los rótulos de apartado se escriben sin el punto
        bloque = bloque.replace("**Análisis ejecutivo.**", "Análisis ejecutivo").replace("**Próximo paso.**",
                                                                                          "Próximo paso")
        # Sin marcas de Markdown
        bloque = " ".join(bloque.replace("**", "").replace("`", "").replace("*", "").split())
        # Una frase por trozo
        frases += [f for f in re.split(r"(?<=[.;:])\s+", bloque) if f]
    return frases


def comprobar_texto(texto_html, aprobado_md):
    """Para si alguna frase del texto aprobado no está, letra a letra, en el texto visible del HTML."""
    texto = visible(texto_html)
    faltan = [f for f in frases_aprobadas(aprobado_md) if f not in texto]
    if faltan:
        raise ValueError("frases del texto aprobado que no están en el informe: " + " | ".join(faltan))


def comprobar_referencias(paneles):
    """Para si una página que cita el texto («página 15», los «Por qué») no es la del panel. `paneles`: los rótulos
    del panel, en orden."""
    malas = [f"{n}: «{paneles[n - 1] if n <= len(paneles) else '—'}» y no «{rotulo}»"
             for n, rotulo in REFERENCIAS.items() if n > len(paneles) or paneles[n - 1] != rotulo]
    if malas:
        raise ValueError("páginas citadas que no son las del panel: " + "; ".join(malas))


# =====================================================================================================================
# CIFRAS
# =====================================================================================================================

def fila_de(lista, campo, valor):
    """La única fila de una lista de un JSON con ese valor en ese campo."""
    encontradas = [f for f in lista if f.get(campo) == valor]
    exigir(len(encontradas) == 1, f"el JSON trae una fila con {campo}={valor}")
    return encontradas[0]


def leer_objetivo(x, o):
    """Lo que usa el informe de un objetivo, con la forma común de validacion.json y prueba_final.json."""
    k = {"x": x}
    todas = {f["prevision"]: f for f in x["errores"]["todas"]}
    ver = x["veredicto"]
    k["error_modelo"], k["error_regla"] = ver["error_modelo"], ver["error_rival"]
    # La regla que menos falla, con todas las pruebas juntas, es la media del mismo día de las 4 semanas anteriores.
    # El veredicto compara en cada prueba con la regla que menos falla en ella (en el último año, en unidades, alguna
    # vez es repetir la semana anterior), así que su error puede ser algo menor: 16,902 frente a 16,921. El texto da
    # las dos con un decimal («La media del mismo día… falla 16,9» y la ventaja frente a la regla que menos falla), y
    # tienen que leerse igual
    exigir(todas[REGLA_PRINCIPAL]["error"] == min(todas[r]["error"] for r in REGLAS)
           and ver["error_rival"] <= todas[REGLA_PRINCIPAL]["error"] + 1e-9
           and numero(ver["error_rival"], 1) == numero(todas[REGLA_PRINCIPAL]["error"], 1),
           f"la media del mismo día de las 4 semanas anteriores es la regla que menos falla ({o})")
    exigir(abs(todas["modelo"]["error"] - ver["error_modelo"]) < 1e-9, f"el error del modelo es el del veredicto ({o})")
    k["reglas"] = {r: todas[r]["error"] for r in REGLAS}
    k["suavizado"] = x["suavizado"]["error_rival"]
    exigir(abs(todas["suavizado"]["error"] - k["suavizado"]) < 1e-9, f"el suavizado es el de la tabla de errores ({o})")
    k["sesgos"] = {nombre: f["sesgo"] for nombre, f in todas.items()}
    k["sesgo_modelo"], k["sesgo_regla"] = k["sesgos"]["modelo"], k["sesgos"][REGLA_PRINCIPAL]
    k["gana"], k["de"], k["minimo"] = ver["origenes_que_gana"], ver["de"], ver["minimo"]
    k["ventaja"], k["intervalo"] = ver["ventaja"], ver["intervalo"]
    # La ventaja es el error de la regla menos el del modelo: así la proporción es la ventaja entre el error de la
    # regla, que es lo mismo que 1 menos el error del modelo entre el de la regla
    exigir(abs(k["ventaja"] - (k["error_regla"] - k["error_modelo"])) < 1e-6,
           f"la ventaja es el error de la regla menos el del modelo ({o})")
    k["proporcion"] = k["ventaja"] / k["error_regla"] * 100
    k["horizonte"] = x["horizonte"]
    k["origenes"] = x["origenes"]
    k["suavizado_x"] = x["suavizado"]
    k["niveles"] = x["niveles"]
    k["departamentos"] = {d["departamento"]: d for d in x["recomendacion_por_departamento"]}
    k["tienda"] = {g["grupo"]: g for g in x["niveles"]["tienda"]["grupos"]}
    k["fuera"] = x.get("dias_fuera_del_error", [])
    return k


def _gana_regla(g):
    """Ventaja de un grupo: el error de la regla menos el del modelo (positiva si el modelo falla menos)."""
    return g["error_regla"] - g["error_modelo"]


def leer_comprobacion(entradas, c):
    """El año de comprobación (validacion.json): la portada, la página 4 y el exceso de ese año en la página 6."""
    v, pa = entradas[VALIDACION], entradas[PARTICION]
    c["v"] = {o: leer_objetivo(v["validacion"][o], o) for o in OBJETIVOS}
    vu, vd = c["v"]["unidades"], c["v"]["dolares"]
    c["algoritmo"] = v["receta"]["ganador"]["unidades"]["algoritmo"]
    exigir(v["receta"]["ganador"]["dolares"]["algoritmo"] == c["algoritmo"], "el mismo tipo de modelo en los dos")

    # Periodo comprobado y combinaciones
    ev_u = vu["x"]["robustez"]["eventos"]
    c["desde"], c["hasta"] = ev_u["desde"], ev_u["hasta"]
    exigir(c["hasta"] == FECHA_DATOS, "el año de comprobación acaba en la fecha de los datos")
    cadena = vu["niveles"]["cadena"]["grupos"][0]
    c["combinaciones"] = cadena["series"]
    c["tiendas"] = vu["niveles"]["padres"]["estado"]
    c["n_departamentos"] = len(vu["departamentos"])
    exigir(set(c["tiendas"].values()) == set(ESTADOS), "las tiendas son de California, Texas y Wisconsin")
    exigir(c["combinaciones"] == c["n_departamentos"] * len(c["tiendas"]),
           "las combinaciones son los departamentos por las tiendas")

    # Días de partida: trece, a intervalos iguales, los mismos en los dos objetivos
    exigir(vu["origenes"] == vd["origenes"] and len(vu["origenes"]) == vu["de"] == vd["de"],
           "los mismos días de partida en los dos objetivos del año de comprobación")
    pasos = {(_dia(b2) - _dia(a)) for a, b2 in zip(vu["origenes"], vu["origenes"][1:])}
    exigir(len(pasos) == 1, "los días de partida van a intervalos iguales")
    c["paso"] = pasos.pop()

    # El año de comprobación de la partición es el de la validación
    validacion_parte = fila_de(pa["partes"], "parte", "validacion")
    exigir((validacion_parte["fecha_min"], validacion_parte["fecha_max"]) == (c["desde"], c["hasta"]),
           "el año de comprobación de la partición es el de la validación")
    exigir(validacion_parte["dias"] == _dia(c["hasta"]) - _dia(c["desde"]) + 1,
           "los días del año de comprobación son los de sus fechas")

    # Página 4: sin las dos tiendas de Wisconsin la ventaja se quedaba en la mitad
    for o in OBJETIVOS:
        k = c["v"][o]
        rob = k["x"]["robustez"]
        juntas = rob["ventaja_sin"]["juntas"]
        exigir(juntas["quitar"] == ["WI_2", "WI_3"] and all(c["tiendas"][t] == "WI" for t in juntas["quitar"]),
               f"las dos tiendas que se quitan son WI_2 y WI_3, de Wisconsin ({o})")
        exigir(0 < juntas["ventaja"] < k["ventaja"] and 0.4 <= juntas["ventaja"] / k["ventaja"] <= 0.6,
               f"sin esas dos tiendas la ventaja se quedaba en la mitad y el modelo seguía ganando ({o})")
        tres = sorted(rob["aporte_por_serie"]["series"], key=lambda s: -s["aporte"])[:3]
        exigir(all(s["store_id"] in ("WI_2", "WI_3") and s["dept_id"].startswith("FOODS") for s in tres),
               f"las tres combinaciones que más aportan son de alimentación en WI_2 y WI_3 ({o})")
        exigir(rob["intervalo_por_tienda"]["bajo"] > 0, f"sorteando tiendas la ventaja sigue por encima de cero ({o})")
        k["sin_wi"], k["intervalo_tienda"] = juntas["ventaja"], rob["intervalo_por_tienda"]
        k["con_regla_mejor"] = rob["series_con_alguna_regla_mejor"]
        exigir(k["con_regla_mejor"]["de"] == c["combinaciones"], "las combinaciones con alguna regla mejor, de 70")
    # «WI_2 sigue siendo la tienda donde más gana» en dólares: también lo era en el año de comprobación
    exigir(max(vd["tienda"], key=lambda t: _gana_regla(vd["tienda"][t])) == "WI_2",
           "en el año de comprobación WI_2 era la tienda donde más ganaba el modelo en dólares")

    # Página 6: «El modelo del año de comprobación se pasaba más que todas las reglas»
    for o in OBJETIVOS:
        s = c["v"][o]["sesgos"]
        exigir(s["modelo"] > 0 and all(s["modelo"] > s[r] for r in s if r != "modelo"),
               f"el modelo del año de comprobación se pasaba más que todas las reglas ({o})")


def leer_ultimo_anio(entradas, c, modelo_en_uso):
    """El último año guardado (prueba_final.json): las cifras principales, con el modelo en uso y el anterior."""
    pf = entradas[PRUEBA_FINAL]
    vu = c["v"]["unidades"]
    c["unidades"], c["dolares"] = (leer_objetivo(pf[EN_USO][o], o) for o in OBJETIVOS)
    u, d = c["unidades"], c["dolares"]

    # El modelo en uso: el reentrenado de la prueba final, ajustado con la venta hasta la fecha de los datos, y el
    # mismo que dice la configuración de producción
    carpeta = pf["modelos"][EN_USO]["carpeta"]
    exigir(Path(carpeta).name == pf["fecha_datos"], "el modelo en uso se ajustó con la venta hasta la fecha de los datos")
    if modelo_en_uso is not None:
        exigir(modelo_en_uso == carpeta, "el modelo en uso de la configuración es el reentrenado de la prueba final")
    c["ajuste_en_uso"] = pf["fecha_datos"]

    # El periodo: empieza el día siguiente al primer día de partida y acaba en fin_prueba_final; «dos años seguidos»
    exigir(u["origenes"] == d["origenes"] and u["origenes"][0] == pf["fecha_datos"],
           "los días de partida del último año empiezan en la fecha de los datos, los mismos en los dos objetivos")
    c["p_desde"] = (date.fromisoformat(u["origenes"][0]) + timedelta(days=1)).isoformat()
    c["p_hasta"] = pf["fin_prueba_final"]
    exigir(_dia(c["p_desde"]) == _dia(c["hasta"]) + 1, "el último año empieza el día siguiente al año de comprobación")
    # «13 días de partida en cada año, uno cada 28 días»
    pasos = {(_dia(b2) - _dia(a)) for a, b2 in zip(u["origenes"], u["origenes"][1:])}
    exigir(len(u["origenes"]) == u["de"] == d["de"] == vu["de"] and pasos == {c["paso"]},
           "trece días de partida en cada año, uno cada 28 días")
    exigir(all(c[o]["horizonte"] == c["v"][o]["horizonte"] for o in OBJETIVOS),
           "los mismos días previstos en los dos años")
    # «ajustado con un año más de datos»
    exigir(int(c["ajuste_en_uso"][:4]) == int(c["construccion"]["hasta"][:4]) + 1
           and c["ajuste_en_uso"][4:] == c["construccion"]["hasta"][4:],
           "el modelo en uso se ajustó con un año más de datos que el del año de comprobación")

    # El modelo en uso gana en los dos objetivos (12 de 13 y 13 de 13) y falla menos que las tres reglas
    for o in OBJETIVOS:
        k = c[o]
        exigir(k["x"]["veredicto"]["veredicto"] == "gana" and k["gana"] >= k["minimo"] and k["intervalo"]["bajo"] > 0,
               f"el modelo en uso gana en el último año ({o})")
        exigir(k["error_modelo"] < min(k["reglas"].values()), f"el modelo en uso falla menos que las tres reglas ({o})")
        exigir(k["suavizado_x"]["lectura"] == "gana" and k["error_modelo"] < k["suavizado"],
               f"el modelo en uso le gana al suavizado exponencial ({o})")
        # «le gana en 11 de 13 pruebas» (cambio 9): gana en las pruebas que pide la regla, no solo con todas juntas
        exigir(k["suavizado_x"]["minimo"] <= k["suavizado_x"]["origenes_que_gana"] <= k["suavizado_x"]["de"],
               f"el modelo en uso le gana al suavizado en las pruebas que pide la regla ({o})")
    # «que no es una de las tres reglas» (cambio 9)
    exigir("suavizado" not in REGLAS, "el suavizado exponencial no es una de las tres reglas")
    exigir(u["intervalo"]["percentiles"] == d["intervalo"]["percentiles"], "el mismo intervalo en los dos")
    c["confianza"] = u["intervalo"]["percentiles"][1] - u["intervalo"]["percentiles"][0]

    # El modelo del año de comprobación, tal como salió de ese año: en unidades, una prueba menos de las que pide la
    # regla; en dólares, gana
    tu, td = (pf[ANTERIOR][o]["veredicto"] for o in OBJETIVOS)
    exigir(tu["veredicto"] == "no gana" and tu["origenes_que_gana"] == tu["minimo"] - 1,
           "el modelo del año de comprobación ganó en unidades en una prueba menos de las que pide la regla")
    exigir(td["veredicto"] == "gana" and td["origenes_que_gana"] >= td["minimo"],
           "en dólares el modelo del año de comprobación sí gana")
    # «Las barras son del modelo en uso» y el del año de comprobación falló más (cambio 10): su 15,3 no es una barra
    exigir(tu["error_modelo"] > u["error_modelo"] and numero(tu["error_modelo"], 1) != numero(u["error_modelo"], 1),
           "el modelo del año de comprobación falló más en unidades que el modelo en uso de las barras")
    c["anterior"] = {"unidades": tu, "dolares": td}

    # El exceso: casi no se pasa; en unidades, lo mismo que la regla; en dólares, algo corto; bajó frente al del año
    # de comprobación
    for o in OBJETIVOS:
        k = c[o]
        exigir(abs(k["sesgo_modelo"]) < abs(c["v"][o]["sesgo_modelo"]),
               f"el exceso del modelo en uso bajó frente al del año de comprobación ({o})")
        exigir(abs(k["sesgo_modelo"]) < CASI_CERO, f"el modelo en uso casi no se pasa ({o})")
    exigir(u["sesgo_modelo"] > 0 and numero(u["sesgo_modelo"], 1) == numero(u["sesgo_regla"], 1),
           "en unidades el modelo en uso se pasa lo mismo que la regla")
    exigir(d["sesgo_modelo"] < 0, "en dólares el modelo en uso se queda algo corto")

    # La previsión sumada: cadena, estados y categorías, con la media del mismo día como regla en todos
    for o in OBJETIVOS:
        k = c[o]
        cad = k["niveles"]["cadena"]["grupos"][0]
        exigir(cad["regla_que_menos_falla"] == REGLA_PRINCIPAL and cad["error_modelo"] < cad["error_regla"],
               f"en la cadena el modelo falla menos que la media del mismo día ({o})")
        exigir(cad["error_modelo"] < k["error_modelo"], f"al sumar, el error baja ({o})")
        k["cadena"] = cad
        k["cadena_sesgo"] = fila_de(cad["errores"], "prevision", "modelo")["sesgo"]
        for nivel in ("estado", "categoria"):
            for g in k["niveles"][nivel]["grupos"]:
                exigir(g["regla_que_menos_falla"] == REGLA_PRINCIPAL,
                       f"la regla que menos falla es la media del mismo día en {g['grupo']} ({o})")
                exigir(g["error_modelo"] < g["error_regla"], f"el modelo en uso falla menos en {g['grupo']} ({o})")
        k["estado"] = {g["grupo"]: g for g in k["niveles"]["estado"]["grupos"]}
        k["categoria"] = {g["grupo"]: g for g in k["niveles"]["categoria"]["grupos"]}
        exigir(set(k["estado"]) == set(ESTADOS) and set(k["categoria"]) == set(CATEGORIAS),
               f"los grupos de la página 3 son los tres estados y las tres categorías ({o})")
        # «Un 27,7 % menos que la media del mismo día…» (cambio 12): 1 menos el error del modelo entre el de la
        # regla, con las cifras sin redondear, como el 14,2 %
        k["cadena_proporcion"] = (1 - cad["error_modelo"] / cad["error_regla"]) * 100
    exigir(u["cadena_sesgo"] > 0 and d["cadena_sesgo"] < 0,
           "en la cadena la previsión se pasa en unidades y se queda corta en dólares")
    # «Por estados, la diferencia es mayor en Wisconsin… En California casi empatan» (cambio 13), en unidades
    diferencia = {e: _gana_regla(g) for e, g in u["estado"].items()}
    exigir(max(diferencia, key=diferencia.get) == "WI" and min(diferencia, key=diferencia.get) == "CA"
           and len(set(diferencia.values())) == len(diferencia),
           "en unidades Wisconsin es el estado con más diferencia entre el modelo y la regla y California el de menos")

    # Las tiendas en dólares: 9 de 10, y la que no es CA_4, empatada (menos de 0,05, visible a dos decimales)
    pierde_d = sorted(t for t, g in d["tienda"].items() if not g["error_modelo"] < g["error_regla"])
    exigir(pierde_d == ["CA_4"] and len(d["tienda"]) == len(c["tiendas"]),
           "en dólares la previsión sumada falla menos que la regla en todas las tiendas menos CA_4")
    c["tiendas_gana_dolares"] = len(d["tienda"]) - len(pierde_d)
    c["ca4_dolares"] = -_gana_regla(d["tienda"]["CA_4"])
    exigir(0 < c["ca4_dolares"] < EMPATE and numero(c["ca4_dolares"], 2) != numero(0, 2),
           "en CA_4 en dólares la regla falla menos por menos de 0,05, visible a dos decimales: empatan")
    # Las tiendas en unidades: la regla falla menos en CA_2 y en CA_4
    pierde_u = sorted(t for t, g in u["tienda"].items() if not g["error_modelo"] < g["error_regla"])
    exigir(pierde_u == ["CA_2", "CA_4"], "en unidades la regla falla menos justo en CA_2 y en CA_4")
    c["ca4_unidades"] = -_gana_regla(u["tienda"]["CA_4"])
    exigir(numero(c["ca4_unidades"], 2) != numero(0, 2), "la diferencia de CA_4 en unidades se ve a dos decimales")
    # «WI_2 sigue siendo la tienda donde más gana», en dólares
    exigir(max(d["tienda"], key=lambda t: _gana_regla(d["tienda"][t])) == "WI_2",
           "en el último año WI_2 es la tienda donde más gana el modelo en dólares")
    # «la regla es la que menos falla en cada tienda: la media del mismo día… en todas, salvo WI_2 en unidades, donde
    # es la media de los últimos 28 días» (cambio 22). Vale también para el gráfico de la página 7, en dólares
    otra_regla = {(t, o): g["regla_que_menos_falla"] for o in OBJETIVOS for t, g in c[o]["tienda"].items()
                  if g["regla_que_menos_falla"] != REGLA_PRINCIPAL}
    exigir(list(otra_regla) == [EXCEPCION_TIENDA] and set(otra_regla.values()) <= set(REGLAS),
           "la regla que menos falla es la media del mismo día en todas las tiendas, salvo WI_2 en unidades")
    c["regla_excepcion_tienda"] = otra_regla[EXCEPCION_TIENDA]

    # Qué usar en cada departamento: HOBBIES_2 es el único con regla, en los dos objetivos
    for o in OBJETIVOS:
        deps = c[o]["departamentos"]
        con_regla = {x for x, k2 in deps.items() if k2["se_recomienda"] != "el modelo"}
        exigir(con_regla == {"HOBBIES_2"}, f"HOBBIES_2 es el único departamento con regla ({o})")
        h2 = deps["HOBBIES_2"]
        exigir(h2["error_regla"] < h2["error_modelo"] and h2["regla_que_menos_falla"] == "media_28_dias"
               and h2["se_recomienda"] == REGLAS["media_28_dias"],
               f"en HOBBIES_2 la media de los últimos 28 días falla menos que el modelo ({o})")
        exigir(numero(h2["error_modelo"] - h2["error_regla"], 2) != numero(0, 2),
               f"la diferencia de HOBBIES_2 se ve a dos decimales ({o})")
        exigir(max(deps, key=lambda x: deps[x]["error_modelo"]) == "HOBBIES_2",
               f"HOBBIES_2 es donde más falla el modelo ({o})")
        exigir(all(deps[x]["error_modelo"] < deps[x]["error_regla"] for x in deps if x != "HOBBIES_2"),
               f"en los otros seis departamentos el modelo falla menos, también en FOODS_3 y HOUSEHOLD_2 ({o})")
        for x in deps.values():
            exigir(x["regla_que_menos_falla_nombre"] == REGLAS[x["regla_que_menos_falla"]],
                   "el nombre de la regla del JSON es el de la hoja de vocabulario")
        # La tabla de la página 10 va a un decimal (cambio 16): en HOBBIES_2 el modelo y la regla se leen distintos
        exigir(numero(h2["error_modelo"], 1) != numero(h2["error_regla"], 1),
               f"en HOBBIES_2 el modelo y la regla se leen distintos a un decimal ({o})")
    c["deps_modelo"] = len(u["departamentos"]) - 1
    exigir(len(u["departamentos"]) == c["n_departamentos"], "los siete departamentos en los dos años")
    # «Los otros cuatro (FOODS_1, FOODS_2, HOBBIES_1 y HOUSEHOLD_1), en el anexo: el modelo falla menos en todos»
    # (cambio 17)
    otros = sorted(x for x in u["departamentos"] if x not in DEPARTAMENTOS_PAGINA_5)
    exigir(otros == OTROS_CUATRO and sorted(x for x in d["departamentos"] if x not in DEPARTAMENTOS_PAGINA_5) == otros
           and all(c[o]["departamentos"][x]["error_modelo"] < c[o]["departamentos"][x]["error_regla"]
                   for o in OBJETIVOS for x in otros),
           "los otros cuatro departamentos son FOODS_1, FOODS_2, HOBBIES_1 y HOUSEHOLD_1 y el modelo falla menos en todos")
    c["otros_cuatro"] = otros
    # «la regla es la que menos falla en cada departamento: la media del mismo día… en todos, salvo FOODS_1 en dólares,
    # donde es la media de los últimos 28 días» (cambio 27)
    otra_regla = {(x, o): c[o]["departamentos"][x]["regla_que_menos_falla"] for o in OBJETIVOS for x in otros
                  if c[o]["departamentos"][x]["regla_que_menos_falla"] != REGLA_PRINCIPAL}
    exigir(list(otra_regla) == [EXCEPCION_DEPARTAMENTO],
           "la regla que menos falla es la media del mismo día en los otros cuatro departamentos, salvo FOODS_1 en "
           "dólares")
    c["regla_excepcion_departamento"] = otra_regla[EXCEPCION_DEPARTAMENTO]
    # «Tres de alimentación, dos de ocio y dos de hogar» (cambio 6): los departamentos de cada categoría, por su código
    c["deps_por_categoria"] = {cat: sum(1 for x in u["departamentos"] if x.split("_")[0] == cat) for cat in CATEGORIAS}
    exigir(sum(c["deps_por_categoria"].values()) == c["n_departamentos"]
           and all(n in EN_LETRA for n in c["deps_por_categoria"].values()),
           "cada departamento es de una de las tres categorías")
    c["h2"] = {o: c[o]["departamentos"]["HOBBIES_2"]["error_modelo"] - c[o]["departamentos"]["HOBBIES_2"]["error_regla"]
               for o in OBJETIVOS}

    # Las tres vísperas de festivo, en unidades: una vez cada una, a 10 días, y el modelo falla menos que la regla
    vispera = u["x"]["festivos"]["por_origen"]
    exigir(len(vispera) == 3 and {f["festivo"] for f in vispera} == set(FESTIVOS.values()),
           "las tres vísperas de festivo, una vez cada una")
    # «a 10 días»: los días medidos son los 10 siguientes a la víspera, salvo el 25 de diciembre, que queda fuera del
    # error (en Navidad se miden 9)
    for f in vispera:
        previstos = {(date.fromisoformat(f["origen"]) + timedelta(days=i + 1)).isoformat() for i in range(u["horizonte"])}
        exigir(set(f["dias"]) <= previstos and all(x[5:] == "12-25" for x in previstos - set(f["dias"])),
               f"la víspera de {f['festivo']} se mide a 10 días, sin más hueco que el 25 de diciembre")
    gracias = next(f for f in vispera if f["festivo"] == FESTIVOS["Thanksgiving"])
    exigir(len(gracias["dias"]) == u["horizonte"], "tras la víspera de Acción de Gracias se miden los 10 días")
    # «sin contar el día de cierre» (cambio 43): en la víspera de Navidad se miden 9 días y falta solo el 25 de
    # diciembre; en las otras dos no falta ninguno
    faltan = {f["festivo"]: {(date.fromisoformat(f["origen"]) + timedelta(days=i + 1)).isoformat()
                             for i in range(u["horizonte"])} - set(f["dias"]) for f in vispera}
    con_cierre = [x for x, dias in faltan.items() if dias]
    exigir(con_cierre == [FESTIVOS["Christmas"]] and len(faltan[FESTIVOS["Christmas"]]) == 1
           and all(x[5:] == "12-25" for x in faltan[FESTIVOS["Christmas"]]),
           "en la víspera de Navidad falta solo el 25 de diciembre, el día de cierre, y en las otras dos no falta ninguno")
    c["vispera_con_cierre"] = con_cierre
    exigir(all(f["error_modelo"] < f["error_regla"] and f["modelo_falla_menos"] for f in vispera),
           "el modelo falla menos que la regla en las tres vísperas de festivo")
    c["festivos_pf"] = {f["festivo"]: f for f in vispera}
    gracias = c["festivos_pf"][FESTIVOS["Thanksgiving"]]
    c["gracias_sesgo_regla"] = fila_de(gracias["errores"], "prevision", gracias["regla_que_menos_falla"])["sesgo"]
    # «la regla que menos falla en cada una» (cambios 35 y 36 de la tercera pasada): en Acción de Gracias, la media de
    # los últimos 28 días; en Navidad y en Año Nuevo, la media del mismo día de las 4 semanas anteriores
    exigir(gracias["regla_que_menos_falla"] == "media_28_dias"
           and all(c["festivos_pf"][FESTIVOS[x]]["regla_que_menos_falla"] == REGLA_PRINCIPAL
                   for x in ("Christmas", "NewYear")),
           "en la víspera de Acción de Gracias la regla que menos falla es la media de los últimos 28 días y en las de "
           "Navidad y Año Nuevo, la media del mismo día")
    # Los tres festivos se escriben en el orden del calendario (cambio 36): el de su víspera
    c["festivos_en_orden"] = [f["festivo"] for f in sorted(vispera, key=lambda f: f["origen"])]
    # «0,5 Dólares que se queda corta… La media del mismo día de las 4 semanas anteriores, 1,4» (cambio 35): en dólares
    # la regla que menos falla es la media del mismo día (lo comprueba leer_objetivo()) y también se queda corta
    exigir(d["sesgo_modelo"] < 0 and d["sesgo_regla"] < 0 and d["sesgos"][REGLA_PRINCIPAL] == d["sesgo_regla"],
           "en dólares el modelo en uso y la media del mismo día de las 4 semanas anteriores se quedan cortos")

    # El 25 de diciembre queda fuera del error: la tienda cierra
    exigir(d["fuera"] and all(x[5:] == "12-25" for x in d["fuera"]) and all(x[5:] == "12-25" for x in u["fuera"]),
           "el único día fuera del error es el 25 de diciembre")
    c["fuera"] = d["fuera"][0]


def leer_cifras(entradas, modelo_en_uso=None):
    """Saca de los JSON las cifras que usan las páginas y comprueba cada frase que nombra un grupo o un sentido."""
    e, bc, b = entradas[EXPLORATORIO], entradas[NEGOCIO], entradas[BUSQUEDA]
    c = {"construccion": e["poblacion"]["construccion"]}
    leer_comprobacion(entradas, c)
    leer_ultimo_anio(entradas, c, modelo_en_uso)

    # Subió de nivel en 2012: los saltos al alza de la alimentación de WI_2
    saltos = [s for s in e["saltos"] if s["tienda"] == "WI_2" and s["departamento"] in ("FOODS_2", "FOODS_3")]
    exigir(len(saltos) == 2 and all(s["salto"] and s["razon"] > 1 for s in saltos)
           and len({s["fecha"][:4] for s in saltos}) == 1, "la alimentación de WI_2 subió de nivel en un mismo año")
    c["anio_salto"] = saltos[0]["fecha"]
    # Las diez combinaciones de HOBBIES_2 son las únicas de venta intermitente; FOODS_3 es el que más vende
    intermitentes = e["ceros"]["series_intermitentes"]
    exigir(len(intermitentes) == len(c["tiendas"]) == 10 and all(s.endswith(" HOBBIES_2") for s in intermitentes),
           "las diez combinaciones de HOBBIES_2 son las únicas de venta intermitente")
    reparto = {r["nombre"]: r["unidades"] for r in e["reparto"]["departamento"]}
    exigir(max(reparto, key=reparto.get) == "FOODS_3", "FOODS_3 es el departamento que más vende")

    # Pregunta 4: los días que cambian (exploratorio, construcción)
    p4 = e["pregunta_4"]
    eventos = {}
    for r in p4["eventos"]:
        eventos.setdefault(r["evento"], {})[r["departamento"]] = r["cambio_pct"]
    for ev in ("Thanksgiving", "NewYear"):
        exigir(len(eventos[ev]) == c["n_departamentos"] and all(x is not None and x < 0 for x in eventos[ev].values()),
               f"en {FESTIVOS[ev]} la venta baja en los siete departamentos")
    c["eventos"] = eventos
    # «con 3 años de cada festivo»: los días de Acción de Gracias y Año Nuevo por departamento, entre las tiendas
    dias_festivo = {r["dias_serie"] for r in p4["eventos"] if r["evento"] in ("Thanksgiving", "NewYear")}
    exigir(len(dias_festivo) == 1 and next(iter(dias_festivo)) % len(c["tiendas"]) == 0
           and next(iter(dias_festivo)) > 0,
           "cada festivo tiene los mismos días en todos los departamentos, un número entero de años por tienda")
    c["anios_festivo"] = next(iter(dias_festivo)) // len(c["tiendas"])
    c["snap"] = {k2: x["cambio_pct"] for k2, x in p4["snap"].items()}
    c["dia_semana"] = p4["dia_semana"]
    exigir(len(c["dia_semana"]) == c["n_departamentos"]
           and all(x["dia_fuerte"] in ("Saturday", "Sunday") for x in c["dia_semana"].values()),
           "el día más fuerte es sábado o domingo en los siete departamentos")
    # «El mes pesa poco»: ningún mes se aparta más de un 9 % (borrador de hallazgos); «el precio casi no cambia»: la
    # mediana de la correlación por departamento queda entre −0,38 y 0,24 (borrador de hallazgos)
    exigir(all(abs(m["cambio_pct"]) < 9 for x in p4["mes"].values() for m in x["meses"].values()),
           "el mes pesa poco: ningún mes se aparta más de un 9 %")
    exigir(all(abs(x["mediana_spearman"]) < 0.4 for x in p4["precio"]["por_departamento"].values()),
           "el precio casi no cambia la venta")

    # Los productos: 500 de los 3.049
    alerta = fila_de(e["alertas"], "id", "A-41")["texto"]
    m = re.search(r"(\d+) de los ([\d.]+) productos", alerta)
    exigir(m is not None, "el exploratorio dice de cuántos productos sale el recorte")
    c["productos"] = sum(e["productos_por_departamento"].values())
    exigir(int(m.group(1)) == c["productos"], "el recorte tiene los productos de sus departamentos")
    c["productos_m5"] = int(m.group(2).replace(".", ""))

    # El dinero
    esc = bc["escenarios"]
    c["dinero"] = esc
    exigir(esc["alto"]["mes_recupera_inversion"] is not None and esc["bajo"]["mes_recupera_inversion"] is None
           and esc["central"]["mes_recupera_inversion"] is None,
           "el escenario alto recupera la inversión y los otros dos no")
    exigir(all(len(x["por_anio"]) == 3 for x in esc.values()), "los escenarios son a tres años")
    exigir(max(esc, key=lambda k2: esc[k2]["total"]["beneficio"]) == "alto",
           "el escenario alto es el más favorable")
    exigir(esc["bajo"]["total"]["beneficio"] < 0 < esc["alto"]["total"]["beneficio"],
           "con estos datos no se puede saber si el proyecto sale a cuenta: el signo cambia de un escenario a otro")
    # «4 de 8 supuestos sin fuente»: los que no son de fuente pública
    c["supuestos_total"] = len(bc["supuestos"])
    c["supuestos_sin_fuente"] = sum(1 for s in bc["supuestos"] if s["origen"] != CON_FUENTE)
    exigir(c["supuestos_sin_fuente"] == 4, "los supuestos sin fuente son 4: la mejora, la venta perdida, el coste del "
                                           "proyecto y su calendario")
    exigir(esc["alto"]["total"]["coste"] < esc["central"]["total"]["coste"] < esc["bajo"]["total"]["coste"],
           "el coste va del escenario alto al bajo")
    ventas = [k2 for k2 in bc["linea_de_hoy"] if re.fullmatch(r"venta_\d{4}", k2)]
    exigir(len(ventas) == 1, "el business case trae la venta de un año")
    c["anio_venta"], c["venta_anio"] = ventas[0][-4:], bc["linea_de_hoy"][ventas[0]]
    c["venta_mes"] = bc["linea_de_hoy"]["venta_mes"]
    # El ajuste del modelo del año de comprobación, con la venta de busqueda.json
    c["ajuste"] = b["tabla"]
    exigir(c["ajuste"]["hasta"] == c["construccion"]["hasta"], "el modelo se ajustó hasta el final de la construcción")
    return c


def _dia(iso):
    """Número de día de una fecha AAAA-MM-DD, para contar los días entre dos."""
    return date.fromisoformat(iso[:10]).toordinal()


# =====================================================================================================================
# PÁGINAS
# =====================================================================================================================

def nombre_regla(clave):
    """El nombre entero de una regla, empezando por mayúscula, para una celda o una línea suelta."""
    n = REGLAS[clave]
    return n[:1].upper() + n[1:]


def periodo(c):
    """El último año guardado: «del 23/05/2015 al 22/05/2016»."""
    return f"del {fecha(c['p_desde'])} al {fecha(c['p_hasta'])}"


def titulo_resumen(c):
    """Título del resumen, que va en sus dos partes: «seis de los siete departamentos», leído y escrito con letra."""
    return (f"Pedir con la previsión del modelo en {EN_LETRA[c['deps_modelo']]} de los "
            f"{EN_LETRA[c['n_departamentos']]} departamentos")


def frase_hobbies_2_cierta(c):
    """«En HOBBIES_2, de venta intermitente, falla menos la media de los últimos 28 días» (cambio 3): en unidades,
    HOBBIES_2 es el único departamento en que la regla falla menos que el modelo, y esa regla es la de los 28 días. Lo
    de «venta intermitente» lo comprueba leer_cifras() con el exploratorio."""
    deps = c["unidades"]["departamentos"]
    pierde = [x for x, k in deps.items() if not k["error_modelo"] < k["error_regla"]]
    return pierde == ["HOBBIES_2"] and deps["HOBBIES_2"]["regla_que_menos_falla"] == "media_28_dias"


def pagina_resumen(inf, c, filas):
    """Resumen: la recomendación, sus cifras clave y el análisis. La tabla de preguntas y el próximo paso van en la
    página siguiente: juntos no caben en la pantalla (S3); la frase aprobada no se recorta."""
    u, d, esc, tu = c["unidades"], c["dolares"], c["dinero"], c["anterior"]["unidades"]
    p = inf.pagina(titulo_resumen(c), "resumen", panel="Resumen", columnas=False)
    # El porcentaje, calculado, y el porqué de cada plazo (cambios 1 y 2)
    p.cifra_clave(num(u["error_modelo"]),
                  f"Unidades que falla la previsión por cada 100 vendidas, a {ent(u['horizonte'])} días, el plazo del "
                  "pedido",
                  f"Un {pct(u['proporcion'])} menos que {REGLAS[REGLA_PRINCIPAL]}, que falla "
                  f"{num(u['reglas'][REGLA_PRINCIPAL])}")
    p.cifra_clave(num(d["error_modelo"]),
                  f"Dólares que falla por cada 100 vendidos, a {ent(d['horizonte'])} días, el mes de finanzas",
                  f"Un {pct(d['proporcion'])} menos que la misma regla, que falla {num(d['reglas'][REGLA_PRINCIPAL])}")
    p.cifra_clave(num(u["sesgo_modelo"], signo=True), "Unidades de más que prevé por cada 100 vendidas",
                  f"La regla, también {num(u['sesgo_regla'], signo=True)}")
    # HOBBIES_2 en la primera página, en la forma corta (cambio 4b de la tercera pasada; el 4 pasaba de 150 palabras):
    # es el único departamento en que la regla falla menos en unidades, y esa regla
    h2 = u["departamentos"]["HOBBIES_2"]
    exigir(frase_hobbies_2_cierta(c), "HOBBIES_2 es el único departamento en que la regla falla menos en unidades, con "
                                      "la media de los últimos 28 días")
    # «la regla» queda para las reglas sencillas: el mínimo de pruebas se dice con su cifra (cambio 30)
    p.apartado("Análisis ejecutivo",
               "Pedir con la previsión del modelo reduce el error frente a la regla sencilla de hoy. Se comprobó en el "
               f"último año guardado, con {ent(u['de'])} pruebas, una cada {ent(c['paso'])} días. El modelo en uso "
               f"falla menos que la regla en {ent(u['gana'])} de {ent(u['de'])} pruebas en unidades y en "
               f"{ent(d['gana'])} de {ent(d['de'])} en dólares. En HOBBIES_2, de venta intermitente, falla menos "
               f"{REGLAS[h2['regla_que_menos_falla']]}.",
               "Es el modelo del año de comprobación, ajustado con un año más de datos. Tal como salió de ese año, en "
               f"unidades ganó en {ent(tu['origenes_que_gana'])} de {ent(tu['de'])} pruebas, una menos de las "
               f"{ent(tu['minimo'])} que hacían falta. Con el año más, la previsión casi no se pasa.",
               "El dinero no está medido: depende de cuánto bajen la mercancía parada y la venta perdida al pedir con "
               "el modelo. Con supuestos sin fuente, el resultado a tres años va de "
               f"{usd(esc['bajo']['total']['beneficio'])} a {usd(esc['alto']['total']['beneficio'], signo=True)}.")


def pagina_resumen_preguntas(inf, c, filas):
    """Resumen, sigue: la tabla de las cuatro preguntas y el próximo paso."""
    u, d = c["unidades"], c["dolares"]
    h2 = u["departamentos"]["HOBBIES_2"]
    p = inf.pagina(titulo_resumen(c), "resultado", panel="Resumen, las cuatro preguntas", columnas=False)
    # La excepción de la respuesta a la pregunta 2 (cambio 3)
    exigir(frase_hobbies_2_cierta(c), "HOBBIES_2 es el único departamento en que la regla falla menos en unidades, con "
                                      "la media de los últimos 28 días")
    # «el detalle, en las páginas 3 a 15» (cambio 5): las dos se comprueban con el panel
    exigir(3 in REFERENCIAS and max(REFERENCIAS) == 15, "las páginas 3 a 15 son las del detalle")
    p.tabla(["Pregunta", "Respuesta", "Qué se recomienda"], [
        ["1. Cuánto venderá cada combinación cada día",
         f"Una previsión diaria, a {ent(u['horizonte'])} días en unidades y a {ent(d['horizonte'])} en dólares",
         "Pedir con la previsión del modelo"],
        ["2. Si se equivoca menos que las reglas",
         f"Sí, en {ent(u['gana'])} de {ent(u['de'])} pruebas en unidades y en {ent(d['gana'])} de {ent(d['de'])} en "
         f"dólares. En HOBBIES_2, de venta intermitente, falla menos {REGLAS[h2['regla_que_menos_falla']]}",
         f"Pedir el departamento de ocio HOBBIES_2 con {REGLAS['media_28_dias']}"],
        ["3. Cuánto venderá cada tienda y categoría",
         # El «todas» con su excepción (cambio 29): leer_ultimo_anio() comprueba 9 de 10 y el empate de CA_4
         # La regla, por su nombre (cambio 44): en dólares es la de todas las tiendas, lo comprueba leer_ultimo_anio()
         f"Al sumar, falla {num(u['cadena']['error_modelo'])} unidades por cada 100 en la cadena; en dólares falla "
         f"menos que {REGLAS[REGLA_PRINCIPAL]} en {ent(c['tiendas_gana_dolares'])} de {ent(len(d['tienda']))} "
         "tiendas y en CA_4 empatan",
         "Planificar el mes de finanzas con la suma en dólares"],
        ["4. Qué días cambia la venta", "Festivos, días de cobro de la ayuda alimentaria (SNAP) y fin de semana",
         # Cada víspera frente a su regla (cambio 42): leer_ultimo_anio() comprueba que el modelo falla menos que la
         # regla que menos falla en cada una
         f"Pedir también los festivos grandes con la previsión: en las {EN_LETRA[len(c['festivos_pf'])]} vísperas "
         "falló menos que la regla que menos falla en cada una"]],
        fuente=f"venta diaria de las {ent(c['combinaciones'])} combinaciones, del {fecha(c['desde'])} al "
               f"{fecha(c['p_hasta'])}; el detalle, en las páginas 3 a {max(REFERENCIAS)}",
        texto=True)
    p.apartado("Próximo paso", f"Aprueba las {EN_LETRA[len(decisiones(c))]} decisiones de la página "
                               f"{max(REFERENCIAS)}, empezando por pedir con la previsión del modelo.")


def pagina_1(inf, c, filas):
    """Página 1: qué se prevé."""
    u, d = c["unidades"], c["dolares"]
    p = inf.pagina("Cada tienda pide con lo que espera vender cada departamento en los próximos días", "resultado",
                   panel="Qué se prevé")
    estados = ", ".join(ESTADOS[s] for s in ("CA", "TX")) + f" y {ESTADOS['WI']}"
    # Los siete departamentos por categoría, con letra (cambio 6): «Tres de alimentación, dos de ocio y dos de hogar»
    por_cat = [f"{EN_LETRA[c['deps_por_categoria'][k]]} de {CATEGORIAS[k].lower()}" for k in CATEGORIAS]
    reparto = ", ".join(por_cat[:-1]) + f" y {por_cat[-1]}"
    p.cifra_clave(ent(c["combinaciones"]), "Combinaciones de departamento y tienda",
                  f"{reparto[:1].upper()}{reparto[1:]}, en {ent(len(c['tiendas']))} tiendas de {estados}")
    p.cifra_clave(f"{ent(u['horizonte'])} días", "Horizonte de la previsión en unidades",
                  "El pedido semanal y lo que tarda en llegar")
    p.cifra_clave(f"{ent(d['horizonte'])} días", "Horizonte de la previsión en dólares", "El mes de finanzas")
    p.apartado("Análisis ejecutivo",
               f"El caso usa {ent(c['productos'])} de los {ent(c['productos_m5'])} productos del concurso público de "
               "Walmart (M5), elegidos al azar y sumados por departamento en cada tienda. Cada día se prevé la venta "
               "de los días "
               "siguientes con lo vendido hasta ayer, el calendario y el precio de la semana anterior. Si la previsión "
               "se queda corta, el estante se vacía; si se pasa, la mercancía queda parada en el almacén.")
    p.apartado("Próximo paso", f"Confirma con compras que {ent(u['horizonte'])} días cubren el pedido semanal y lo que "
                               "tarda en llegar: es un supuesto del caso.")


def titulo_pagina_2():
    """Título de la página 2, que va en sus dos partes: cuenta las cuatro previsiones de la tabla (cambio 8). Que el
    modelo en uso falla menos que las tres reglas y que el suavizado lo comprueba leer_ultimo_anio()."""
    return "La previsión del modelo falla menos que las tres reglas y el suavizado en el último año guardado"


def pagina_2(inf, c, filas):
    """Página 2: el modelo frente a las reglas. La tabla y el primer párrafo del análisis; el gráfico, el segundo
    párrafo y el próximo paso, en la siguiente (S3, como en la versión 3)."""
    u, d = c["unidades"], c["dolares"]
    su, sd = u["suavizado_x"], d["suavizado_x"]
    p = inf.pagina(titulo_pagina_2(), "resultado", panel="El modelo frente a las reglas", columnas=False)
    p.apartado("Métricas clave")
    orden = [REGLA_PRINCIPAL, "media_28_dias", "repetir_semana_anterior"]
    # Cada previsión con su error y su exceso (+) o defecto (−), en unidades y en dólares
    claves = ["modelo"] + orden + ["suavizado"]
    nombres = ["Modelo"] + [nombre_regla(r) for r in orden] + ["Suavizado exponencial (método estadístico sencillo)"]
    error = {o: {**c[o]["reglas"], "modelo": c[o]["error_modelo"], "suavizado": c[o]["suavizado"]} for o in OBJETIVOS}
    p.tabla(["Previsión", "Unidades, por cada 100", "Dólares, por cada 100",
             "Se pasa (+) o se queda corta (−), unidades por cada 100",
             "Se pasa (+) o se queda corta (−), dólares por cada 100"],
            [[n, en_tabla(error["unidades"][x]), en_tabla(error["dolares"][x]), en_tabla(u["sesgos"][x]),
              en_tabla(d["sesgos"][x])] for x, n in zip(claves, nombres)],
            # El plazo, en la nota (cambio 28), solo si la página cabe
            fuente=f"venta diaria de las {ent(c['combinaciones'])} combinaciones, {periodo(c)}, {ent(u['de'])} "
                   f"pruebas cada {ent(c['paso'])} días. {nota_plazo(c)}", decimales=[0, 1, 1, 1, 1])
    p.apartado("Análisis ejecutivo",
               f"Cada prueba prevé desde un día de partida, uno cada {ent(c['paso'])} días: los {ent(u['horizonte'])} "
               f"días siguientes en unidades y los {ent(d['horizonte'])} siguientes en dólares. "
               f"Frente a la regla que menos falla, el modelo falla {num(u['ventaja'], 2)} unidades menos por cada "
               f"100, un {pct(u['proporcion'])} menos. En dólares falla {num(d['ventaja'], 2)} menos, un "
               f"{pct(d['proporcion'])} menos. Con un {ent(c['confianza'])} % de confianza, la ventaja va de "
               f"{num(u['intervalo']['bajo'], 2)} a {num(u['intervalo']['alto'], 2)} unidades por cada 100 y de "
               f"{num(d['intervalo']['bajo'], 2)} a {num(d['intervalo']['alto'], 2)} dólares. "
               # La frase del suavizado cierra el segundo párrafo del texto aprobado; va aquí porque con ella la
               # segunda parte medía 661 px en el navegador (S3). Así, 645 y 638 px, sin partir la página. Desde la
               # versión 5 dice que el suavizado no es una de las tres reglas (cambio 9)
               "Al suavizado exponencial, que no es una de las tres reglas, el modelo en uso le gana en "
               f"{ent(su['origenes_que_gana'])} de "
               f"{ent(su['de'])} pruebas en unidades y en {ent(sd['origenes_que_gana'])} de {ent(sd['de'])} en "
               "dólares.")


def pagina_2_grafico(inf, c, filas):
    """Página 2, sigue: el error de cada previsión, en unidades y en dólares, en fila y con la misma escala; debajo, el
    segundo párrafo del análisis (el modelo del año de comprobación) y el próximo paso. La frase del suavizado va en
    la primera parte: aquí no cabía (S3)."""
    p = inf.pagina(titulo_pagina_2(), "resultado", panel="El modelo frente a las reglas, gráfico")
    # Cada barra con el nombre entero de su previsión, el de la tabla, partido en líneas para caber a la izquierda
    nombres = ["Modelo", "La media del mismo día\nde las 4 semanas\nanteriores", "La media de los\núltimos 28 días",
               "Repetir la\nsemana anterior", "Suavizado\nexponencial"]
    claves = ["modelo", REGLA_PRINCIPAL, "media_28_dias", "repetir_semana_anterior", "suavizado"]
    valores = {}
    for o in OBJETIVOS:
        k = c[o]
        valores[o] = [k["error_modelo"] if x == "modelo" else k["suavizado"] if x == "suavizado" else k["reglas"][x]
                      for x in claves]
    tope = max(valores["unidades"] + valores["dolares"])
    svgs = {}
    for o, unidad in (("unidades", "unidades"), ("dolares", "dólares")):
        for nombre, valor in zip(nombres, valores[o]):
            apuntar(filas, len(inf.paginas), f"error de cada previsión en {unidad}", nombre.replace("\n", " "),
                    f"{unidad} que falla por cada 100 vendidos", valor, unidad)
        svgs[o] = barras_ordenadas(nombres, valores[o], decimales=1, ancho=ANCHO_FILA, maximo=tope,
                                   medida=f"{unidad} que falla por cada 100 vendidos")
    subtitulo = (f"Unidades o dólares que falla cada previsión por cada 100 vendidos, {periodo(c)}. Fuente: venta "
                 f"diaria de las {ent(c['combinaciones'])} combinaciones")
    # El plazo en el rótulo de cada gráfico (cambio 11)
    p.fila(svgs["unidades"], f"En unidades, a {ent(c['unidades']['horizonte'])} días", subtitulo, svgs["dolares"],
           f"En dólares, a {ent(c['dolares']['horizonte'])} días", subtitulo)
    tu, td = c["anterior"]["unidades"], c["anterior"]["dolares"]
    # Las barras son del modelo en uso; el 15,3 es del modelo del año de comprobación (cambio 10), que falló más: lo
    # comprueba leer_ultimo_anio()
    p.texto("Las barras son del modelo en uso. Tal como salió del año de comprobación, sin el año más de datos, el "
            f"modelo falló {num(tu['error_modelo'])} unidades por cada 100 "
            f"en este año y ganó en {ent(tu['origenes_que_gana'])} de las {ent(tu['de'])} pruebas. Hacían falta "
            f"{ent(tu['minimo'])}, así que en unidades no se confirmó. En dólares sí, con "
            f"{ent(td['origenes_que_gana'])} de {ent(td['de'])}.")
    p.apartado("Próximo paso", f"Pide con la previsión del modelo en lugar de con {REGLAS[REGLA_PRINCIPAL]}.")


def titulo_pagina_3():
    """Título de la página 3, que va en sus tres partes."""
    return "Sumada por estado, categoría o cadena, la previsión falla menos que la regla en todos los grupos"


def pagina_3(inf, c, filas):
    """Página 3: la previsión sumada, en tres partes y en el orden del texto. Aquí, las cifras y la tabla; después, el
    gráfico y, al final, el análisis y el próximo paso (S3 y D3, como en la versión 3)."""
    u, d = c["unidades"], c["dolares"]
    p = inf.pagina(titulo_pagina_3(), "resultado", panel="La previsión sumada", columnas=False)
    # El porcentaje, calculado con las cifras sin redondear (cambio 12)
    p.cifra_clave(num(u["cadena"]["error_modelo"]),
                  f"Unidades que falla por cada 100 en la cadena, sumando las {ent(c['combinaciones'])} combinaciones",
                  f"Un {pct(u['cadena_proporcion'])} menos que {REGLAS[REGLA_PRINCIPAL]}, que falla "
                  f"{num(u['cadena']['error_regla'])}")
    p.cifra_clave(num(d["cadena"]["error_modelo"]), "Dólares que falla por cada 100 en la cadena",
                  f"Un {pct(d['cadena_proporcion'])} menos que la misma regla, que falla "
                  f"{num(d['cadena']['error_regla'])}")
    p.cifra_clave(f"{ent(c['tiendas_gana_dolares'])} de {ent(len(d['tienda']))}",
                  "Tiendas en que la suma en dólares falla menos que la regla", "En CA_4 empatan")
    tabla = []
    for nivel, nombres in (("estado", ESTADOS), ("categoria", CATEGORIAS)):
        for clave, nombre in nombres.items():
            gu, gd = u[nivel][clave], d[nivel][clave]
            tabla.append([nombre, en_tabla(gu["error_modelo"]), en_tabla(gu["error_regla"]),
                          en_tabla(gd["error_modelo"]), en_tabla(gd["error_regla"])])
    # La nota de la tabla empieza por la fuente (F1); detrás, sus dos frases aprobadas y el plazo (cambio 28). La
    # primera columna dice qué grupos son (cambio 14)
    p.tabla(["Estado o categoría", "Unidades: modelo", "Unidades: regla", "Dólares: modelo", "Dólares: regla"], tabla,
            fuente=f"venta diaria de las {ent(c['combinaciones'])} combinaciones, sumada por grupo, {periodo(c)}. "
                   f"Error por cada 100 vendidos. La regla es {REGLAS[REGLA_PRINCIPAL]}, la que menos falla en todos "
                   f"los grupos. {nota_plazo(c)}", decimales=[0, 1, 1, 1, 1])


def pagina_3_grafico(inf, c, filas):
    """Página 3, sigue: el error de cada tienda en dólares, del modelo y de la regla, con CA_4 destacada."""
    d = c["dolares"]
    p = inf.pagina(titulo_pagina_3(), "resultado", panel="La previsión sumada, gráfico")
    tiendas = sorted(d["tienda"])
    modelo = [d["tienda"][t]["error_modelo"] for t in tiendas]
    regla = [d["tienda"][t]["error_regla"] for t in tiendas]
    tope = max(modelo + regla)
    # Cada cifra de los dos gráficos, con el número de la página en el panel
    for t, a, b2 in zip(tiendas, modelo, regla):
        apuntar(filas, len(inf.paginas), "error de cada tienda en dólares, modelo", t,
                "dólares que falla por cada 100 vendidos", a, "dólares")
        apuntar(filas, len(inf.paginas), "error de cada tienda en dólares, regla", t,
                "dólares que falla por cada 100 vendidos", b2, "dólares")
    # Naranja solo para la tienda en que el modelo falla más que la regla (G3); el mismo orden y la misma escala en
    # los dos (G8)
    svg_modelo = barras_ordenadas(tiendas, modelo, decimales=1, ancho=ANCHO_FILA, maximo=tope, ordenar=False,
                                  destacar=[t for t in tiendas if not d["tienda"][t]["error_modelo"]
                                            < d["tienda"][t]["error_regla"]], medida="dólares que falla el modelo por cada 100 vendidos")
    svg_regla = barras_ordenadas(tiendas, regla, decimales=1, ancho=ANCHO_FILA, maximo=tope, ordenar=False,
                                 medida="dólares que falla la regla por cada 100 vendidos")
    # El rótulo dice el plazo y que en CA_4 empatan, en la forma corta (cambio 15b de la tercera pasada; el 15 acababa
    # a 656 px en el navegador): CA_4 es la única tienda en naranja, la única en que la regla falla menos en dólares,
    # y por menos de 0,05
    pierde = [t for t, g in d["tienda"].items() if not g["error_modelo"] < g["error_regla"]]
    exigir(pierde == ["CA_4"] and 0 < c["ca4_dolares"] < EMPATE,
           "CA_4 es la única tienda en que la regla falla menos en dólares, por menos de 0,05: empatan")
    subtitulo = (f"Dólares que falla cada tienda por cada 100 vendidos, a {ent(d['horizonte'])} días, {periodo(c)}. "
                 f"En naranja, {pierde[0]}, donde empatan. Fuente: venta diaria de las {ent(c['combinaciones'])} "
                 "combinaciones, sumada por tienda")
    p.fila(svg_modelo, "El modelo", subtitulo, svg_regla, nombre_regla(REGLA_PRINCIPAL), subtitulo)


def pagina_3_analisis(inf, c, filas):
    """Página 3, tercera parte: el análisis y el próximo paso."""
    u, d = c["unidades"], c["dolares"]
    p = inf.pagina(titulo_pagina_3(), "resultado", panel="La previsión sumada, análisis")
    ca2 = u["tienda"]["CA_2"]
    wi, ca = u["estado"]["WI"], u["estado"]["CA"]
    # Dónde cambia la diferencia entre estados (cambio 13): Wisconsin, la mayor; California, la menor
    diferencia = {e: _gana_regla(g) for e, g in u["estado"].items()}
    exigir(max(diferencia, key=diferencia.get) == "WI" and min(diferencia, key=diferencia.get) == "CA",
           "en unidades Wisconsin es el estado con más diferencia y California el de menos")
    # Dos párrafos: la cadena y los estados; después, las tiendas (de lo general a lo concreto)
    p.apartado("Análisis ejecutivo",
               "Al sumar, los errores de los departamentos se compensan y el error baja. En la cadena la previsión se "
               f"pasa {num(u['cadena_sesgo'], signo=True)} unidades y se queda corta {num(abs(d['cadena_sesgo']))} "
               f"dólares por cada 100. Por estados, la diferencia es mayor en {ESTADOS['WI']}, con "
               # California, con su magnitud (cambio 32)
               f"{num(wi['error_modelo'])} frente a {num(wi['error_regla'])} unidades. En {ESTADOS['CA']}, en "
               f"unidades, casi empatan: {num(ca['error_modelo'])} frente a {num(ca['error_regla'])}.",
               "En dólares, CA_4 empata: la regla falla menos por "
               f"{num(c['ca4_dolares'], 2)}. En unidades, la regla falla menos en CA_2, con {num(ca2['error_regla'])} "
               f"frente a {num(ca2['error_modelo'])}. En CA_4 también, por {num(c['ca4_unidades'], 2)}.")
    p.apartado("Próximo paso", "Planifica el mes de finanzas con la previsión sumada en dólares.")


def pagina_4(inf, c, filas):
    """Página 4: dónde gana y dónde no, con las cifras del año de comprobación y una frase del último año."""
    vu, vd, d = c["v"]["unidades"], c["v"]["dolares"], c["dolares"]
    p = inf.pagina("Sin dos tiendas de Wisconsin la ventaja del año de comprobación se quedaba en la mitad",
                   "resultado", panel="Dónde gana y dónde no")
    # Las cifras «con ellas» dicen su año: el informe da otras del último año (cambio 23)
    p.cifra_clave(num(vu["sin_wi"], 2), "Ventaja en unidades por cada 100 sin las tiendas WI_2 y WI_3",
                  f"Con ellas, {num(vu['ventaja'], 2)}, en el año de comprobación")
    p.cifra_clave(num(vd["sin_wi"], 2), "Ventaja en dólares por cada 100 sin esas dos tiendas",
                  f"Con ellas, {num(vd['ventaja'], 2)}, en el año de comprobación")
    p.cifra_clave(f"{ent(vu['con_regla_mejor']['cuantas'])} de {ent(vu['con_regla_mejor']['de'])}",
                  # El año de la cifra (cambio 33)
                  "Combinaciones en que una regla falla menos que el modelo en el año de comprobación, en unidades",
                  f"En dólares, {ent(vd['con_regla_mejor']['cuantas'])} de {ent(vd['con_regla_mejor']['de'])}")
    iu, idl, wi2 = vu["intervalo_tienda"], vd["intervalo_tienda"], d["tienda"]["WI_2"]
    # «frente a 17,8 de la media del mismo día…» (cambio 33): en dólares, la regla de WI_2 es esa
    exigir(wi2["regla_que_menos_falla"] == REGLA_PRINCIPAL,
           "en dólares la regla que menos falla en WI_2 es la media del mismo día de las 4 semanas anteriores")
    # El análisis empieza diciendo su año (cambio 33)
    p.apartado("Análisis ejecutivo",
               "En el año de comprobación, las tres combinaciones que más aportan son de alimentación en WI_2 y WI_3. "
               "Aun sorteando tiendas "
               f"enteras, la ventaja sigue por encima de cero: de {num(iu['bajo'], 2)} a {num(iu['alto'], 2)} "
               f"unidades por cada 100 y de {num(idl['bajo'], 2)} a {num(idl['alto'], 2)} dólares. En el resto de "
               "tiendas el modelo gana, pero menos. En el último año, WI_2 sigue siendo la tienda donde más gana: "
               f"{num(wi2['error_modelo'])} dólares por cada 100 frente a {num(wi2['error_regla'])} de "
               f"{REGLAS[wi2['regla_que_menos_falla']]}.")
    p.apartado("Próximo paso", "Pregunta a los jefes de WI_2 y WI_3 qué explica su venta de alimentación. En WI_2 "
                               f"subió de nivel en {anio(c['anio_salto'])}.")


def pagina_5(inf, c, filas):
    """Página 5: qué usar en cada departamento."""
    u, d = c["unidades"], c["dolares"]
    p = inf.pagina("En el departamento de ocio HOBBIES_2 la media de los últimos 28 días falla menos que el modelo",
                   "resultado", panel="Qué usar en cada departamento", columnas=False)
    p.apartado("Métricas clave")
    # Lo que se recomienda en cada departamento, comprobado contra el JSON en los dos objetivos
    recomendado = {"FOODS_3": "el modelo", "HOBBIES_2": REGLAS["media_28_dias"], "HOUSEHOLD_2": "el modelo"}
    for k2, rec in recomendado.items():
        exigir(u["departamentos"][k2]["se_recomienda"] == d["departamentos"][k2]["se_recomienda"] == rec,
               f"en {k2} se recomienda {rec}")
    # Una cifra por celda, todas a un decimal (cambio 16): en HOBBIES_2, 50,2 y 50,1; leer_ultimo_anio() comprueba que a
    # un decimal se leen distintos. El 0,09 lo da el análisis
    filas_tabla = [[nombre, en_tabla(u["departamentos"][k2]["error_modelo"]),
                    en_tabla(u["departamentos"][k2]["error_regla"]), en_tabla(d["departamentos"][k2]["error_modelo"]),
                    en_tabla(d["departamentos"][k2]["error_regla"]), recomendado[k2]]
                   for k2, nombre in DEPARTAMENTOS_PAGINA_5.items()]
    # Los otros cuatro, con nombre (cambio 17): leer_ultimo_anio() comprueba que son esos y que el modelo falla menos
    otros = c["otros_cuatro"]
    nombres_otros = ", ".join(otros[:-1]) + f" y {otros[-1]}"
    # Cabeceras como en la página 6 y el anexo, diciendo qué regla es (cambio 34)
    p.tabla(["Departamento", "Unidades: modelo", "Unidades: regla que menos falla", "Dólares: modelo",
             "Dólares: regla que menos falla", "Se recomienda"], filas_tabla,
            fuente=f"venta diaria de cada departamento en las {ent(len(c['tiendas']))} tiendas, {periodo(c)}. Los otros "
                   f"{EN_LETRA[len(otros)]} ({nombres_otros}), en el anexo: el modelo falla menos en todos. "
                   f"{nota_plazo(c)}",
            # A 13 px (texto=False, como permite informe.py), como en la versión 3: a 15 px no cabía (S3)
            decimales=[0, 1, 1, 1, 1, 0], texto=False)
    p.apartado("Análisis ejecutivo",
               "Las diez combinaciones de HOBBIES_2 son las únicas de venta intermitente, con días sin venta entre días "
               "con venta. Es donde más falla el modelo. En unidades la regla falla menos por solo "
               f"{num(c['h2']['unidades'], 2)}; en dólares, por {num(c['h2']['dolares'], 2)}. En HOUSEHOLD_2 el modelo "
               "ya gana en los dos objetivos. En FOODS_3, el departamento que más vende, también.")
    p.apartado("Próximo paso", f"Pide HOBBIES_2 con {REGLAS['media_28_dias']}; el resto, con la previsión del modelo.")


def pagina_6(inf, c, filas):
    """Página 6: el exceso."""
    u, d, vu = c["unidades"], c["dolares"], c["v"]["unidades"]
    gracias = c["festivos_pf"][FESTIVOS["Thanksgiving"]]
    p = inf.pagina("Con un año más de datos, la previsión casi no se pasa", "resultado", panel="El exceso")
    p.cifra_clave(num(u["sesgo_modelo"], signo=True), "Unidades de más que prevé por cada 100 vendidas",
                  f"En el año de comprobación, el modelo anterior se pasaba {num(vu['sesgo_modelo'], signo=True)}")
    # El rótulo dice qué mide (cambio 25) y la cifra va sin signo, con la regla por su nombre (cambio 35): en dólares
    # el modelo en uso y la media del mismo día se quedan cortos, lo comprueba leer_ultimo_anio()
    exigir(d["sesgo_modelo"] < 0 and d["sesgo_regla"] < 0,
           "en dólares el modelo en uso y la media del mismo día se quedan cortos")
    p.cifra_clave(num(abs(d["sesgo_modelo"])), "Dólares que se queda corta por cada 100 vendidos",
                  f"{nombre_regla(REGLA_PRINCIPAL)}, {num(abs(d['sesgo_regla']))}")
    # La regla de Acción de Gracias, por su nombre (cambio 35): la de los últimos 28 días, lo comprueba
    # leer_ultimo_anio()
    p.cifra_clave(num(gracias["sesgo_modelo"], signo=True),
                  f"Unidades de más en los {ent(u['horizonte'])} días tras la víspera de "
                  f"{FESTIVOS['Thanksgiving']}",
                  f"{nombre_regla(gracias['regla_que_menos_falla'])}, {num(c['gracias_sesgo_regla'], signo=True)}")
    p.apartado("Análisis ejecutivo",
               "Prever de más deja mercancía parada en el almacén. El modelo del año de comprobación se pasaba más que "
               # La regla, por su nombre (cambio 40): la del +0,3, que leer_ultimo_anio() comprueba a un decimal
               "todas las reglas. Con la misma receta y un año más de datos, se pasa lo mismo que "
               f"{REGLAS[REGLA_PRINCIPAL]} en unidades y en dólares se queda algo corto. Por qué bajó el exceso no se puede saber con lo medido.")
    p.apartado("Próximo paso", "Pide con la previsión sin corregirla: con el modelo en uso ya no se pasa de media.")


def pagina_7(inf, c, filas):
    """Página 7: los días que cambian. Las cifras clave son del exploratorio; el análisis, del último año."""
    u, ev, fe = c["unidades"], c["eventos"], c["festivos_pf"]
    gracias, nuevo, navidad = fe[FESTIVOS["Thanksgiving"]], fe[FESTIVOS["NewYear"]], fe[FESTIVOS["Christmas"]]
    # «En Navidad, 18,4 frente a 21,2» (cambio 24): en Navidad el modelo falla menos que la regla
    exigir(navidad["error_modelo"] < navidad["error_regla"] and navidad["modelo_falla_menos"],
           "en la víspera de Navidad el modelo falla menos que la regla")
    p = inf.pagina(f"En {FESTIVOS['Thanksgiving']} y {FESTIVOS['NewYear']} la venta cae en todos los departamentos",
                   "resultado", panel="Los días que cambian")
    p.cifra_clave(pct(ev["NewYear"]["HOBBIES_2"], signo=True),
                  f"Venta de HOBBIES_2 en {FESTIVOS['NewYear']} frente a un día normal",
                  f"En {FESTIVOS['Thanksgiving']}, {pct(ev['Thanksgiving']['HOBBIES_2'], signo=True)}")
    p.cifra_clave(pct(c["snap"]["FOODS_2"], signo=True),
                  "Venta de FOODS_2, alimentación, en los días de cobro de la ayuda alimentaria (SNAP)",
                  f"FOODS_3, {pct(c['snap']['FOODS_3'], signo=True)}")
    p.cifra_clave(num(c["dia_semana"]["HOUSEHOLD_1"]["cociente"], 2),
                  "Veces que vende el día más fuerte frente al más flojo en HOUSEHOLD_1, hogar",
                  f"En HOBBIES_2, {num(c['dia_semana']['HOBBIES_2']['cociente'], 2)}; siempre es sábado o domingo")
    con = c["construccion"]
    tres = EN_LETRA[len(fe)]
    # Dos párrafos (cambio 43): las cifras de efecto, de la construcción; después, las vísperas del último año
    p.apartado("Análisis ejecutivo",
               f"Estas cifras son de {anio(con['desde'])} a {mes_y_anio(con['hasta'])}, con {ent(c['anios_festivo'])} "
               "años de cada festivo. El mes pesa poco y el precio casi no cambia.",
               "En el último año se midió la previsión en unidades desde la víspera de los "
               f"{tres} festivos grandes, a {ent(u['horizonte'])} días. "
               # Cada festivo frente a su regla, en el orden del calendario (cambio 36): las reglas las comprueba
               # leer_ultimo_anio()
               + frases_festivos(c, tres))
    p.apartado("Próximo paso", "Pide los festivos grandes con la previsión, sabiendo que cada uno se comprobó una sola "
                               "vez.")


def frases_festivos(c, tres):
    """«En las tres falló menos que la regla que menos falla en cada una. En Acción de Gracias, 18,8 unidades por cada
    100 frente a 25,5 de la media de los últimos 28 días. En Navidad, 18,4 frente a 21,2 de la media del mismo día de
    las 4 semanas anteriores. En Año Nuevo, 14,0 frente a 20,5 de esa misma regla.»: en el orden del calendario, cada
    regla con el nombre que trae el JSON de su víspera (cambio 41)."""
    fe = c["festivos_pf"]
    exigir(all(fe[x]["error_modelo"] < fe[x]["error_regla"] for x in fe),
           "en las tres vísperas el modelo falla menos que la regla que menos falla en cada una")
    partes = [f"En las {tres} falló menos que la regla que menos falla en cada una."]
    anterior = None
    for i, nombre in enumerate(c["festivos_en_orden"]):
        f = fe[nombre]
        exigir(f["regla_que_menos_falla"] in REGLAS, f"la regla de la víspera de {nombre} es una de las tres")
        # «de esa misma regla» solo si es la misma que la víspera anterior; si no, su nombre entero
        regla = ("esa misma regla" if f["regla_que_menos_falla"] == anterior
                 else REGLAS[f["regla_que_menos_falla"]])
        unidades = " unidades por cada 100" if i == 0 else ""
        # «sin contar el día de cierre» (cambio 43) donde falta un día de los medidos: leer_ultimo_anio() comprueba que
        # solo falta en Navidad y que es el 25 de diciembre
        cierre = ", sin contar el día de cierre" if nombre in c["vispera_con_cierre"] else ""
        partes.append(f"En {nombre}, {num(f['error_modelo'])}{unidades} frente a {num(f['error_regla'])} de "
                      f"{regla}{cierre}.")
        anterior = f["regla_que_menos_falla"]
    return " ".join(partes)


def pagina_8(inf, c, filas):
    """Página 8: el dinero."""
    esc = c["dinero"]
    p = inf.pagina("El retorno depende de supuestos sin fuente y no está medido", "resultado", panel="El dinero")
    p.cifra_clave(usd(c["venta_mes"]),
                  f"Venta media al mes de las {ent(c['combinaciones'])} combinaciones en {apunta(c['anio_venta'])}",
                  f"{usd(c['venta_anio'])} en el año")
    p.cifra_clave(f"{ent(c['supuestos_sin_fuente'])} de {ent(c['supuestos_total'])}", "Supuestos del cálculo sin fuente",
                  "Cuánto bajan la mercancía parada y la venta perdida, qué parte de la venta se pierde, el coste y el "
                  "calendario")
    p.cifra_clave(f"Mes {ent(esc['alto']['mes_recupera_inversion'])}",
                  "Cuándo recupera la inversión el escenario más favorable", "Los otros dos no la recuperan en tres años")
    mejora = [esc[k]["parametros"]["mejora_pct"] for k in ("bajo", "central", "alto")]
    p.apartado("Análisis ejecutivo",
               f"El cálculo supone que la mercancía parada y la venta perdida bajan un {pct(mejora[0], 0)}, un "
               f"{pct(mejora[1], 0)} o un {pct(mejora[2], 0)}, y que el proyecto cuesta de "
               f"{usd(esc['alto']['total']['coste'])} a {usd(esc['bajo']['total']['coste'])} en tres años. Lo medido "
               f"es otra cosa: en el último año, la previsión falla un {pct(c['unidades']['proporcion'])} menos en "
               f"unidades. La base es pequeña porque el caso usa {ent(c['productos'])} de los "
               f"{ent(c['productos_m5'])} productos: con estos datos no se puede saber si el proyecto sale a cuenta.")
    p.apartado("Próximo paso", "Pide a finanzas el coste, el margen y las existencias de estos productos para calcular "
                               "el ahorro real.")


def pagina_limites(inf, c, filas):
    """Página 9: los límites que cambian una decisión."""
    tu, u = c["anterior"]["unidades"], c["unidades"]
    p = inf.pagina("Lo que puede cambiar estas conclusiones", "limites", panel="Límites")
    p.tabla(["Decisión a la que afecta", "Límite"], [
        ["Pedir con la previsión", "El modelo del año de comprobación no se confirmó en unidades en el último año "
                                   f"guardado: ganó en {ent(tu['origenes_que_gana'])} de {ent(tu['de'])} pruebas. El "
                                   "que queda en uso se eligió después de ver los dos en ese mismo año, lo que lo "
                                   "favorece algo. No hay otro año con venta para confirmarlo. Parte de ese año se miró "
                                   "antes de empezar"],
        ["Pedir con la previsión", "El caso no estudia promociones: en estos datos los precios casi no cambian. Con "
                                   "promociones, la previsión no está comprobada"],
        ["Pedir en los festivos", "Cada festivo grande se comprobó una sola vez, desde su víspera y a "
                                  f"{ent(u['horizonte'])} días"],
        ["Cuánto se gana en cada tienda", "En el año de comprobación, la mitad de la ventaja salía de WI_2 y WI_3. En "
                                          "el último año no se midió sin ellas"],
        ["El dinero", "Sin coste, margen ni existencias, el ahorro no se puede calcular. Los escenarios suponen la "
                      "mejora, la venta perdida y el coste del proyecto, sin fuente"],
        ["Todas", f"Son {ent(c['productos'])} de los {ent(c['productos_m5'])} productos de Walmart y la venta de "
                  f"{anio(c['construccion']['desde'])} a {anio(c['p_hasta'])}. Antes de pedir de verdad, la previsión "
                  "se hace y se comprueba con todos los productos. Si cambia la forma de vender, el error sube y hay que "
                  # Lo que no se puede saber, en la forma corta (cambio 7b de la tercera pasada; el 7 medía 673 px)
                  "volver a medir. Qué parte de la venta de Walmart suman no se puede saber"]],
        fuente=FUENTE_PAGINAS, texto=True)


def decisiones(c):
    """Las cuatro decisiones propuestas, en el orden del texto, con las páginas que cita cada «Por qué»: las usan la
    página de decisiones y el resumen."""
    u, d = c["unidades"], c["dolares"]
    # «también en los festivos grandes» (cambio 18): en las tres vísperas el modelo falló menos que la regla
    exigir(all(f["error_modelo"] < f["error_regla"] for f in c["festivos_pf"].values()),
           "en las tres vísperas de festivo el modelo falla menos que la regla")
    return [
        [f"Pedir con la previsión del modelo, también en los festivos grandes; en HOBBIES_2, con "
         f"{REGLAS['media_28_dias']}",
         "Aprueba la Dirección de Operaciones; lo aplican compras y jefes de tienda", "Primero",
         # Con las vísperas, que justifican «también en los festivos grandes» (cambio 37); el 12 de 13 del modelo
         # frente a la regla está en el resumen, la página 1 (cambio 39)
         # Con su magnitud (cambio 45)
         f"Falla menos en {ent(u['gana'])} de {ent(u['de'])} pruebas en unidades y en las "
         f"{EN_LETRA[len(c['festivos_pf'])]} vísperas de festivo {paginas(1, 10, 12)}"],
        ["Planificar el mes de finanzas con la previsión del modelo en dólares, sumada por tienda",
         "Aprueba la Dirección de Operaciones; lo aplica finanzas", "Primero",
         f"Sumada, falla menos que la regla en {ent(c['tiendas_gana_dolares'])} de {ent(len(d['tienda']))} tiendas; en "
         f"CA_4 empatan {paginas(6, 8, seguidas=True)}"],
        ["Preguntar a los jefes de WI_2 y WI_3 qué explica su venta de alimentación", "Operaciones de tiendas",
         "Pendiente de la Dirección",
         f"En el año de comprobación, sin esas dos tiendas la ventaja se quedaba en la mitad {paginas(9)}"],
        ["Pedir el coste, el margen y las existencias de estos productos", "Finanzas", "Pendiente de la Dirección",
         f"Sin ellos el ahorro no se calcula {paginas(13)}"]]


def pagina_decision(inf, c, filas):
    """Página 10: las cuatro decisiones propuestas y, debajo, a qué acciones del informe ejecutivo responden."""
    lista = decisiones(c)
    p = inf.pagina(f"Se pide a la Dirección que apruebe {EN_LETRA[len(lista)]} decisiones", "decision",
                   panel="Decisiones propuestas")
    p.tabla(["Decisión", "Quién", "Plazo", "Por qué"], lista, fuente=FUENTE_PAGINAS, texto=True)


def paginas_anexo(inf, c, filas):
    """Anexo: la nota del informe ejecutivo, método, fuentes y datos, con las tablas largas (D6)."""
    u, d = c["unidades"], c["dolares"]
    # La nota sobre el informe ejecutivo vuelve al anexo, a su página (cambio 19): la primera, justo detrás de las
    # decisiones, para que las dos tablas largas sigan a la tabla de cifras (cambio 20)
    a = inf.pagina("Las decisiones y el informe ejecutivo", "anexo", panel="Las decisiones y el informe ejecutivo")
    a.texto("La primera desarrolla las acciones 1 y 2 del informe ejecutivo (construir y medir la previsión; decidir "
            "previsión o regla en cada departamento). La tercera es la acción 3 (averiguar los cambios de nivel).")
    a = inf.pagina("Método, fuentes y datos", "anexo", panel="Método, fuentes y datos")
    a.texto(f"Cómo se mide el error. Lo que falla la previsión, sumado sin signo, entre lo vendido, por 100, con las "
            f"{ent(c['combinaciones'])} combinaciones y todos los días juntos. El exceso es la misma cuenta con signo. "
            f"El {dia_y_mes(c['fuera'])} queda fuera: la tienda cierra.",
            f"Cómo se prevé. Desde cada día de partida, día a día, con lo previsto los días anteriores, como se usaría "
            f"en la tienda. {ent(u['de'])} días de partida en cada año, uno cada {ent(c['paso'])} días.",
            f"Cuándo gana. Si falla menos que la regla que menos falla en al menos {ent(u['minimo'])} de las "
            f"{ent(u['de'])} pruebas y el intervalo del {ent(c['confianza'])} % de la ventaja queda por encima de cero. "
            # «la regla» queda para las reglas sencillas (cambio 30)
            "Ese mínimo se fijó antes de medir.")
    # El modelo y las dos proporciones, en su página: con lo anterior pasa de 150 palabras (T2)
    a = inf.pagina("El modelo", "anexo", panel="El modelo")
    a.texto(f"El modelo. Un modelo de árboles de decisión por boosting ({c['algoritmo']}), uno para unidades y otro "
            f"para dólares. El del año de comprobación se ajustó con la venta del {fecha(c['ajuste']['desde'])} al "
            f"{fecha(c['ajuste']['hasta'])}. El que queda en uso tiene la misma receta, ajustada con la venta hasta el "
            f"{fecha(c['ajuste_en_uso'])}. Se comprobó {periodo(c)}.",
            # Lo pide la petición: las dos proporciones son la única cifra que calcula el informe
            f"Cómo se calcula cuánto menos falla. El {pct(u['proporcion'])} y el {pct(d['proporcion'])} que la "
            "previsión falla menos que la regla son 1 menos el error del modelo entre el de la regla que menos falla, "
            # Las dos de la cadena, con la misma cuenta (cambio 26)
            f"en unidades y en dólares. El {pct(u['cadena_proporcion'])} y el {pct(d['cadena_proporcion'])} de la "
            "cadena se calculan igual.")
    f = inf.pagina("Tabla de cifras", "anexo", panel="Tabla de cifras")
    # La frase de arriba (cambio 38b de la cuarta pasada): las tablas largas van en las dos páginas siguientes, que es
    # donde las pone esta función. El periodo de cada cifra lo da su página: la columna de fecha sale (el 38, con el
    # periodo de cada fichero, medía 722 px en el navegador, y el 21, la columna de página, salió del todo)
    f.texto("Tabla de cifras. Cada cifra con su fichero de informes. Las tablas largas van en las dos páginas "
            "siguientes.")
    f.tabla(["Cifra", "Fichero de informes"], [
        # Con una fila por bloque la página no cabe en la pantalla (S3): las del último año van en tres
        ["Error, exceso y ventaja del modelo en uso, del modelo del año de comprobación y de las reglas; cuánto menos "
         "falla, calculado con las dos cifras del veredicto", PRUEBA_FINAL],
        ["Previsión sumada por tienda, estado, categoría y cadena; qué usar en cada departamento", PRUEBA_FINAL],
        ["Las tres vísperas de festivo", PRUEBA_FINAL],
        ["Lo que matiza la ventaja: las dos tiendas de Wisconsin; el exceso del año de comprobación", VALIDACION],
        ["Días que cambian la venta, venta intermitente, cambios de nivel y productos", EXPLORATORIO],
        ["Fechas de la venta con que se ajustó el modelo del año de comprobación", BUSQUEDA],
        ["Días del año de comprobación", PARTICION],
        ["Venta del año, escenarios a tres años y supuestos sin fuente", NEGOCIO],
        ["Cifras de los gráficos", SALIDA_CSV.name]],
        fuente="carpeta de informes del caso", texto=True)
    t = inf.pagina("Los otros cuatro departamentos", "anexo", panel="Los otros cuatro departamentos")
    otros = c["otros_cuatro"]
    # Qué regla es, con su excepción (cambio 27), y el plazo (cambio 28); los comprueba leer_ultimo_anio()
    dep_x, obj_x = EXCEPCION_DEPARTAMENTO
    t.tabla(["Departamento", "Unidades: modelo", "Unidades: regla", "Dólares: modelo", "Dólares: regla"],
            [[k, en_tabla(u["departamentos"][k]["error_modelo"]), en_tabla(u["departamentos"][k]["error_regla"]),
              en_tabla(d["departamentos"][k]["error_modelo"]), en_tabla(d["departamentos"][k]["error_regla"])]
             for k in otros],
            fuente=f"venta diaria de cada departamento en las {ent(len(c['tiendas']))} tiendas, {periodo(c)}. Error "
                   f"por cada 100 vendidos; la regla es la que menos falla en cada departamento: "
                   f"{REGLAS[REGLA_PRINCIPAL]} en todos, salvo {dep_x} en {OBJETIVO_TEXTO[obj_x]}, donde es "
                   f"{REGLAS[c['regla_excepcion_departamento']]}. {nota_plazo(c)}", decimales=[0, 1, 1, 1, 1])
    # Las tiendas, en su página: con los departamentos no cabe en la pantalla (S3)
    t = inf.pagina(f"Las {EN_LETRA[len(c['tiendas'])]} tiendas", "anexo",
                   panel=f"Las {EN_LETRA[len(c['tiendas'])]} tiendas")
    # Qué regla es, con su excepción (cambio 22), y el plazo (cambio 28); los comprueba leer_ultimo_anio()
    tienda_x, obj_x = EXCEPCION_TIENDA
    t.tabla(["Tienda", "Unidades: modelo", "Unidades: regla", "Dólares: modelo", "Dólares: regla"],
            [[k, en_tabla(u["tienda"][k]["error_modelo"]), en_tabla(u["tienda"][k]["error_regla"]),
              en_tabla(d["tienda"][k]["error_modelo"]), en_tabla(d["tienda"][k]["error_regla"])]
             for k in sorted(u["tienda"])],
            fuente=f"venta diaria de las {ent(c['combinaciones'])} combinaciones, sumada por tienda, {periodo(c)}. "
                   f"Error por cada 100 vendidos; la regla es la que menos falla en cada tienda: "
                   f"{REGLAS[REGLA_PRINCIPAL]} en todas, salvo {tienda_x} en {OBJETIVO_TEXTO[obj_x]}, donde es "
                   f"{REGLAS[c['regla_excepcion_tienda']]}. {nota_plazo(c)}", decimales=[0, 1, 1, 1, 1])
    # Datos personales, con su apartado propio al final del anexo (patrón §4)
    g = inf.pagina("Datos personales", "anexo", panel="Datos personales")
    g.texto("Datos personales. El caso no trae datos de personas: son ventas por producto y tienda. No pasaron por la "
            "protección de datos porque no hacía falta.")


# =====================================================================================================================
# MONTAJE
# =====================================================================================================================

def construir(entradas, aprobado=None, modelo_en_uso=None):
    """Comprueba las fechas, monta el informe y pasa las guardias: devuelve (HTML, filas del CSV, informe).

    Con `aprobado` (el texto del borrador), compara además cada frase aprobada con el HTML. Con `modelo_en_uso` (la
    carpeta que dice produccion/configuracion.json), comprueba que es el reentrenado de la prueba final.
    """
    LEIDAS.clear()
    comprobar_fechas(entradas)
    c = leer_cifras(entradas, modelo_en_uso)
    lector = (f"Para la Dirección de Operaciones de Tiendas. Venta diaria de {ent(c['combinaciones'])} combinaciones "
              f"de departamento y tienda de Walmart, comprobada en dos años seguidos, del {fecha(c['desde'])} al "
              f"{fecha(c['p_hasta'])}.")
    inf = Informe(TITULO, lector)
    filas = []
    for funcion in (pagina_resumen, pagina_resumen_preguntas, pagina_1, pagina_2, pagina_2_grafico, pagina_3,
                    pagina_3_grafico, pagina_3_analisis, pagina_4, pagina_5, pagina_6, pagina_7, pagina_8,
                    pagina_limites, pagina_decision, paginas_anexo):
        funcion(inf, c, filas)
    texto = inf.html()
    anexo = {p.id for p in inf.paginas if p.tipo == "anexo"}
    sin_jerga(texto, anexo)
    sin_sinonimos(texto)
    titulos_claros([TITULO] + [p.titulo for p in inf.paginas if p.tipo != "anexo"])
    cifras_leidas(texto, LEIDAS)
    comprobar_referencias([p.panel for p in inf.paginas])
    if aprobado is not None:
        comprobar_texto(texto, aprobado)
    return texto, filas, inf


def palabras(pagina):
    """Palabras del texto de una página: párrafos y apartados, sin rótulos, tablas, gráficos ni cifras clave."""
    texto = " ".join(b["html"] for b in pagina.bloques if b["clase"] in ("parrafo", "apartado"))
    texto = re.sub(r"<h2>.*?</h2>", " ", texto)
    return len(html.unescape(re.sub(r"<[^>]+>", " ", texto)).split())


def main():
    """Comprueba el intérprete y el orden, monta el informe, lo compara con el texto aprobado y lo escribe."""
    if Path(sys.prefix).name != ENTORNO:
        raise SystemExit(f"Lanza dentro del entorno {ENTORNO} (conda activate {ENTORNO}); este es {sys.prefix}")
    entradas = leer_entradas(INFORMES)
    comprobar_orden(entradas)
    modelo_en_uso = json.loads(CONFIGURACION.read_text(encoding="utf-8"))["modelo_en_uso"]
    texto, filas, inf = construir(entradas, BORRADOR.read_text(encoding="utf-8"), modelo_en_uso)
    SALIDA_HTML.write_text(texto, encoding="utf-8")
    escribir_csv(SALIDA_CSV, filas)
    for i, p in enumerate(inf.paginas, 1):
        print(f"{i:>2}. {p.tipo:<9} {p.alto():>4} px {palabras(p):>4} palabras  {p.titulo}")
    print(f"Escrito {SALIDA_HTML.relative_to(RAIZ)} y {SALIDA_CSV.relative_to(RAIZ)} ({len(filas)} cifras)")


if __name__ == "__main__":
    main()
