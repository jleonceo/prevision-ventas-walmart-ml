"""Prueba de scripts/08_informe_ejecutivo.py, sin imprimir ningún PDF.

Prueba las guardias que paran el informe antes de escribirlo, con cifras escritas aquí: cada una con su caso que tiene
que parar y el texto aprobado con las cifras buenas, que no debe parar (control). No lee ningún informe del caso salvo
con --datos, que pasa las guardias con el JSON real de consultas.

Los casos:
  1. una cifra del texto que no es la del JSON, o que falta en él, para; un número sin marcar que no es fijo, también;
  2. un apartado que pasa de su tope de palabras para;
  3. una palabra vetada para, salvo dentro de un nombre de fichero entre comillas invertidas;
  4. cada frase con sentido para si sus cifras ya no la sostienen;
  5. el anexo que no empieza en página propia, lo anterior en más de dos páginas o más de tres en total, paran.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "08_informe_ejecutivo.py"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    spec = importlib.util.spec_from_file_location("ejecutivo_08", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def cifras_del_texto(m):
    """Las cifras tal como las escribe el texto aprobado, sacadas de sus marcas: el control que no debe parar."""
    cifras = {}
    for _, _, t in m.textos(m.BLOQUES):
        for nombre, como in m.MARCA.findall(t):
            if nombre == "fecha_datos":
                cifras[nombre] = "2015-05-22"
            else:
                cifras[nombre] = float(como.replace(".", "").replace(",", "."))
    # Las cifras que solo usan las frases con sentido
    cifras.update({"departamentos": 7, "dias_fuertes_fin_de_semana": 7, "accion_gracias_negativos": 7,
                   "snap_resto_min_pct": -4.7, "snap_resto_max_pct": 1.6, "mes_mayor_desvio_pct": 8.9,
                   "dia_cociente_min": 1.22, "cambios_de_nivel_hobbies_2": 10, "cambios_mismo_dia_tienda": "WI_1",
                   "cambios_mismo_dia_fecha": "2012-10-26"})
    return cifras


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_cifras(m):
    """Caso 1: cifras contra el JSON."""
    c = cifras_del_texto(m)
    comprobar(m.comprobar_cifras(c) == [], f"control · el texto con sus propias cifras no para ({m.comprobar_cifras(c)[:2]})")
    otra = dict(c, dolares_2013=6094768.0)
    comprobar(any("dolares_2013" in e for e in m.comprobar_cifras(otra)), "rojo · un dólar de más en 2013 para")
    falta = {k: v for k, v in c.items() if k != "cambios_de_nivel"}
    comprobar(any("cambios_de_nivel" in e for e in m.comprobar_cifras(falta)), "rojo · una cifra que falta en el JSON para")
    bloque = [["resumen", "p", "Se vendieron 123 cajas."]]
    comprobar(any("123" in e for e in m.comprobar_cifras(c, bloque)), "rojo · un número sin marcar y no fijo para")


def probar_topes(m):
    """Caso 2: topes de palabras."""
    c = cifras_del_texto(m)
    comprobar(m.comprobar_topes(m.contar_palabras(m.BLOQUES, c)) == [], "control · el texto aprobado cabe en sus topes")
    largo = m.BLOQUES + [["limites", "p", "palabra " * 120]]
    comprobar(any("limites" in e for e in m.comprobar_topes(m.contar_palabras(largo, c))),
              "rojo · 120 palabras más en los límites paran")


def probar_jerga(m):
    """Caso 3: palabras vetadas."""
    c = cifras_del_texto(m)
    comprobar(m.sin_jerga(m.texto_plano(m.BLOQUES, c)) == [], "control · el texto aprobado no lleva palabras vetadas")
    comprobar(m.sin_jerga("Cada serie se mide en la validación.") != [], "rojo · «serie» y «validación» paran")
    comprobar(m.sin_jerga("Sale de `informes/serie.json`.") == [], "control · dentro de un nombre de fichero no para")


def probar_exigir(m):
    """Caso 4: frases con sentido."""
    c = cifras_del_texto(m)
    comprobar(m.exigir(c) == [], f"control · las frases con sentido se cumplen ({m.exigir(c)})")
    for clave, valor, frase in [("dias_fuertes_fin_de_semana", 6, "sábado o domingo"),
                                ("accion_gracias_negativos", 6, "Acción de Gracias"),
                                ("snap_resto_max_pct", 6.0, "apenas mueve"),
                                ("mes_mayor_desvio_pct", 9.5, "Ningún mes"),
                                ("mes_mayor_desvio_pct", 30.0, "pesa menos")]:
        errores = m.exigir(dict(c, **{clave: valor}))
        comprobar(any(frase in e for e in errores), f"rojo · con {clave} = {valor} para la frase «{frase}»")


def probar_paginas(m):
    """Caso 5: paginación."""
    a = m.TITULO_ANEXO
    comprobar(m.comprobar_paginas(["uno", "dos", f"{a} tres"]) == [], "control · dos páginas y el anexo en la tercera")
    comprobar(m.comprobar_paginas(["uno", f"dos {a}"]) != [], "rojo · el anexo detrás de otro texto para")
    comprobar(m.comprobar_paginas(["uno", "dos", "tres", f"{a}"]) != [], "rojo · lo anterior en tres páginas para")
    comprobar(m.comprobar_paginas(["uno", f"{a}", "x", "y"]) != [], "rojo · cuatro páginas paran")


def probar_con_datos(m):
    """Con --datos: las guardias con el JSON real de consultas."""
    ruta = RAIZ / m.CONSULTAS
    if not ruta.exists():
        comprobar(False, f"existe {m.CONSULTAS}")
        return
    c = m.cargar_cifras(json.loads(ruta.read_text(encoding="utf-8")))
    errores = (m.comprobar_cifras(c) + m.comprobar_topes(m.contar_palabras(m.BLOQUES, c))
               + m.sin_jerga(m.texto_plano(m.BLOQUES, c)) + m.exigir(c))
    comprobar(errores == [], f"con el JSON real, ninguna guardia para ({errores[:3]})")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_cifras(modulo)
            probar_topes(modulo)
            probar_jerga(modulo)
            probar_exigir(modulo)
            probar_paginas(modulo)
            if "--datos" in sys.argv:
                probar_con_datos(modulo)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
