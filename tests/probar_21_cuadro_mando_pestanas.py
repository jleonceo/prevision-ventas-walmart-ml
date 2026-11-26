"""Prueba de las pestañas de informes/cuadro_mando.html, abierto en Edge sin ventana.

Edge abre una página de prueba en tests/tmp_cuadro/ con el cuadro dentro de un marco de 1366 × 650. Esa página pone
cada combinación de filtros y cada pestaña con la función del propio cuadro que lee la dirección (CUADRO.irA) y mide la
pestaña montada: cuántas cifras tiene arriba y su ancho, cuántos gráficos, cuántas palabras, sus títulos y si la página
se sale a lo ancho. Edge deja el resultado en el DOM y la prueba lo lee con --dump-dom.

Combinaciones (petición 32): todas las de estado y categoría (4 × 4, con «Todos»); con la tienda de muestra WI_2, cada
categoría; con el departamento de muestra FOODS_3, cada estado; y WI_2 con FOODS_3. Son 25.

En cada pestaña y combinación comprueba: de 3 a 4 cifras arriba, todas del mismo ancho; como mucho 2 gráficos; como
mucho LIMITE_PALABRAS palabras (unas 60; no cuentan el número grande, la etiqueta de las cifras, lo que va dentro de
los gráficos y las tablas, los mandos ni lo que sale al pasar el ratón); ningún título con coma o dos puntos; ningún
título que diga «falla menos» sin marcarlo y sin 10 de 13 pruebas ganadas en la selección; ninguna palabra que la hoja
de vocabulario del caso dice que no se usa; nada más ancho que 1366 px; nada que se salga por abajo sin su barra; la
fuente al pie con la fecha de los datos; el orden de las pestañas, de los filtros, de las columnas de las tablas y de la
línea «Viendo»; HOBBIES_2 marcado con la regla que se recomienda. Y que las cifras sin filtros son las de
tests/cifras_cuadro_mando.json.

La carpeta tests/tmp_cuadro/ se crea y se borra siempre. Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_21_cuadro_mando_pestanas.py
"""

# html deshace los escapes del resultado que deja Edge
import html
# json lee los datos del cuadro, el resultado de Edge y las cifras de referencia
import json

import os
# re busca el resultado en el DOM y las palabras de los títulos
import re
# shutil borra la carpeta temporal
import shutil
# subprocess lanza Edge
import subprocess
# sys da el código de salida
import sys
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HTML = RAIZ / "informes" / "cuadro_mando.html"
REFERENCIA = RAIZ / "tests" / "cifras_cuadro_mando.json"
TMP = RAIZ / "tests" / "tmp_cuadro"
EDGE = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
# El orden de las pestañas del guion aprobado (§3) y el de los filtros, de lo general a lo concreto (D8)
PESTANAS = ["vision", "pedido", "donde", "festivos", "proximos"]
ORDEN_FILTROS = ["f-estado", "f-tienda", "f-categoria", "f-departamento"]
COLUMNAS = {"p-pedido": ["Departamento", "Unidades: modelo", "Unidades: regla que menos falla",
                         "Regla que menos falla", "Se pide con"],
            "p-proximos": ["Tienda", "Departamento", "Día", "Unidades previstas", "Dólares previstos", "Se prevé con"]}
TIENDA_MUESTRA, DEPARTAMENTO_MUESTRA = "WI_2", "FOODS_3"
ESTADOS = {"CA": "California", "TX": "Texas", "WI": "Wisconsin"}
CATEGORIAS = {"FOODS": "alimentación", "HOBBIES": "ocio", "HOUSEHOLD": "hogar"}
LIMITE_PALABRAS = 66
# La paleta de las reglas de salida (E2): azul, lo real o el modelo; el segundo color, la previsión o la regla con que
# se compara (G3: el naranja es solo lo peor o la alerta). El segundo color, elegido con las pruebas de color del 25/11
AZUL, NARANJA = "#2a78d6", "#eb6834"
SEGUNDA = "#eda100"
MINIMO_GANA = 10
DE_PRUEBAS = 13
FECHA = "22/05/2016"
REGLA_HOBBIES = "la media de los últimos 28 días"
# Lo que la hoja de vocabulario del lector dice que no se usa (config/metodo/vocabulario_del_lector.md)
VETADAS = re.compile(r"\bseries?\b|predicci|pron[oó]stico|\bWAPE\b|\bHGB\b|la mejor regla|\brival\b|benchmark|"
                     r"\bhorizonte\b|m[eé]todo actual|sucursal|Thanksgiving|Christmas|NewYear|\bIA\b|algoritmo|"
                     r"reposici[oó]n|aprovisionamiento|d[ií]a SNAP", re.I)
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso y dice si pasa."""
    if not condicion:
        print(f"FALLA {nombre} ({detalle})")
        FALLOS.append(nombre)
    return condicion


def datos_del_html():
    """Los datos que el cuadro lleva dentro, en su bloque JSON."""
    texto = HTML.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="datos">(.*?)</script>', texto, flags=re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def combinaciones():
    """Las 25 combinaciones de la cabecera, como diccionarios en el orden de los filtros."""
    combos = []
    for estado in [None, *ESTADOS]:
        for categoria in [None, *CATEGORIAS]:
            combos.append({k: v for k, v in (("estado", estado), ("categoria", categoria)) if v is not None})
    for categoria in [None, *CATEGORIAS]:
        combos.append({k: v for k, v in (("estado", "WI"), ("tienda", TIENDA_MUESTRA), ("categoria", categoria))
                       if v is not None})
    for estado in [None, *ESTADOS]:
        combos.append({k: v for k, v in (("estado", estado), ("categoria", "FOODS"),
                                         ("departamento", DEPARTAMENTO_MUESTRA)) if v is not None})
    combos.append({"estado": "WI", "tienda": TIENDA_MUESTRA, "categoria": "FOODS", "departamento": DEPARTAMENTO_MUESTRA})
    return combos


def direccion(pestana, filtros):
    """La dirección de la página para una pestaña y unos filtros, como la escribe el cuadro."""
    return "#" + "&".join([f"pestana={pestana}"] + [f"{k}={v}" for k, v in filtros.items()])


PAGINA = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<iframe id="cuadro" src="__SRC__" style="width:1366px;height:650px;border:0"></iframe>
<pre id="resultado"></pre>
<script>
const PRUEBAS = __PRUEBAS__;
const marco = document.getElementById('cuadro');
function palabras(sec) {
  const copia = sec.cloneNode(true);
  copia.querySelectorAll('svg, table, .num, .etq, button, select, label').forEach(e => e.remove());
  const texto = copia.textContent.replace(/\\s+/g, ' ');
  return texto.split(' ').filter(p => /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(p)).length;
}
marco.addEventListener('load', () => {
  const salida = [];
  try {
    const win = marco.contentWindow, doc = marco.contentDocument;
    for (const p of PRUEBAS) {
      win.CUADRO.irA(p.hash);
      const sec = doc.querySelector('section.pestana:not([hidden])');
      const cifras = [...sec.querySelectorAll('.cifra')];
      const titulos = [...sec.querySelectorAll('[data-titulo]')].map(t => ({texto: t.textContent.trim(),
        concluye: t.dataset.concluye, gana: t.dataset.gana, de: t.dataset.de}));
      const ids = [...doc.querySelectorAll('[id]')].map(e => e.id);
      const cortes = [...sec.querySelectorAll('.cifra > div')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent);
      const tablas = [...sec.querySelectorAll('.tabla')].map(t => ({alto: t.scrollHeight, visible: t.clientHeight, barra: getComputedStyle(t).overflowY}));
      salida.push({hash: p.hash, pestana: sec.id, cifras: cifras.length,
        filtros: [...doc.querySelectorAll('.filtros select')].map(s => s.id),
        pestanas: [...doc.querySelectorAll('[role=tab]')].map(b => b.dataset.p),
        columnas: [...sec.querySelectorAll('thead th')].map(th => th.textContent),
        filas_hobbies: [...sec.querySelectorAll('tbody tr')].filter(tr => tr.textContent.includes('HOBBIES_2')).map(tr => tr.lastElementChild.textContent),
        filas_otras: [...sec.querySelectorAll('tbody tr')].filter(tr => !tr.textContent.includes('HOBBIES_2')).map(tr => tr.lastElementChild.textContent),
        viendo: doc.getElementById('viendo').textContent, cortes: cortes, tablas: tablas,
        ids_repetidos: ids.filter((x, i) => ids.indexOf(x) !== i), pie: (sec.querySelector('.pie') || {}).textContent || '',
        selects_vacios: [...doc.querySelectorAll('select')].filter(s => s.options.length === 0).map(s => s.id),
        anchos: cifras.map(c => Math.round(c.getBoundingClientRect().width * 10) / 10),
        valores: cifras.map(c => ({id: c.dataset.id, valor: c.dataset.valor})),
        graficos: sec.querySelectorAll('.grafico').length, palabras: palabras(sec), titulos: titulos,
        ancho: doc.documentElement.scrollWidth, alto: doc.documentElement.scrollHeight, texto: sec.innerText,
        contextos: Object.fromEntries(cifras.map(c => [c.dataset.id, (c.querySelector('.ctx') || {}).textContent || ''])),
        lineas: [...sec.querySelectorAll('.grafico svg path')].map(p => ({color: p.getAttribute('stroke'), raya: p.getAttribute('stroke-dasharray') || ''})),
        leyenda_raya: [...sec.querySelectorAll('.grafico svg line[stroke-dasharray]')].map(l => l.getAttribute('stroke')),
        barras: [...new Set([...sec.querySelectorAll('.grafico svg g[data-tip] rect')].map(x => x.getAttribute('fill')).filter(c => c && c !== 'transparent' && !c.startsWith('url')))],
        leyenda: [...sec.querySelectorAll('.grafico')].map(g => {
          const t = g.querySelector('.gtit'), l = t ? t.nextElementSibling : null;
          if (!l || !l.classList.contains('gley')) return {debajo: false};
          const a = t.getBoundingClientRect(), b = l.getBoundingClientRect();
          return {debajo: true, izquierda: Math.abs(a.left - b.left), hueco: b.top - a.bottom, textos: l.textContent.trim()};
        }),
        semanas: sec.id === 'p-vision' ? {titulo: sec.querySelector('.gtit').textContent, sub: sec.querySelector('.gsub').textContent,
          puntos: sec.querySelectorAll('.grafico > svg g[data-tip]').length,
          navidad: [...sec.querySelectorAll('.grafico > svg g[data-tip]')].filter(g => g.dataset.tip.includes('sin el 25 de diciembre')).map(g => g.dataset.tip),
          primera: (sec.querySelector('.grafico > svg g[data-tip]') || {dataset: {}}).dataset.tip || ''} : null,
        leyendas_dentro:[...sec.querySelectorAll('.grafico > svg line[stroke-dasharray], .grafico > svg text')].filter(e => /Venta|Modelo|Previsión del modelo|regla que menos falla/.test(e.textContent || '') && e.tagName === 'text').length});
    }
  } catch (e) { salida.push({error: String(e) + ' ' + (e.stack || '')}); }
  try {
    // La dirección que escribe el cuadro al cambiar un filtro, con los cuatro puestos
    const win = marco.contentWindow, doc = marco.contentDocument;
    win.CUADRO.irA('#pestana=vision&departamento=FOODS_3&tienda=WI_2');
    const s = doc.getElementById('f-categoria'); s.value = 'FOODS'; s.dispatchEvent(new Event('change'));
    salida.push({direccion: win.location.hash});
  } catch (e) { salida.push({error: String(e)}); }
  document.getElementById('resultado').textContent = JSON.stringify(salida);
});
</script></body></html>"""


def medir_en_edge(pruebas):
    """Abre la página de prueba en Edge sin ventana y devuelve lo que midió."""
    pagina = TMP / "pagina_de_prueba.html"
    pagina.write_text(PAGINA.replace("__SRC__", HTML.resolve().as_uri())
                      .replace("__PRUEBAS__", json.dumps(pruebas, ensure_ascii=False)), encoding="utf-8")
    orden = [str(EDGE), "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--window-size=1400,800",
             "--virtual-time-budget=120000", f"--user-data-dir={TMP / 'perfil_edge'}", "--dump-dom",
             pagina.resolve().as_uri()]
    salida = subprocess.run(orden, capture_output=True, timeout=300).stdout.decode("utf-8", errors="replace")
    m = re.search(r'<pre id="resultado">(.*?)</pre>', salida, flags=re.S)
    if not m or not m.group(1).strip():
        raise RuntimeError("Edge no dejó el resultado de la página de prueba")
    return json.loads(html.unescape(m.group(1)))


def orden_viendo(hash_):
    """Lo que la línea «Viendo» tiene que nombrar, en el orden de los filtros."""
    partes = dict(x.split("=", 1) for x in hash_.lstrip("#").split("&"))
    orden = []
    if "estado" in partes:
        orden.append(ESTADOS[partes["estado"]])
    if "tienda" in partes:
        orden.append(partes["tienda"])
    if "categoria" in partes:
        orden.append(CATEGORIAS[partes["categoria"]])
    if "departamento" in partes:
        orden.append(partes["departamento"])
    return orden


def comprobar_pestana(r):
    """Los casos de una pestaña en una combinación."""
    nombre = r["hash"]
    caso(f"{nombre}: de 3 a 4 cifras", 3 <= r["cifras"] <= 4, r["cifras"])
    caso(f"{nombre}: cifras del mismo ancho", r["anchos"] and max(r["anchos"]) - min(r["anchos"]) <= 1, r["anchos"])
    caso(f"{nombre}: ninguna cifra cortada", not r["cortes"], r["cortes"])
    caso(f"{nombre}: como mucho 2 gráficos", r["graficos"] <= 2, r["graficos"])
    caso(f"{nombre}: unas 60 palabras", r["palabras"] <= LIMITE_PALABRAS, r["palabras"])
    caso(f"{nombre}: nada más ancho que la pantalla", r["ancho"] <= 1366, r["ancho"])
    caso(f"{nombre}: nada más alto que la pantalla", r["alto"] <= 650, r["alto"])
    for t in r["tablas"]:
        caso(f"{nombre}: la tabla larga lleva su barra", t["alto"] <= t["visible"] + 1 or t["barra"] in ("auto", "scroll"), t)
    caso(f"{nombre}: ninguna palabra vetada", not VETADAS.search(r["texto"]), VETADAS.search(r["texto"]))
    caso(f"{nombre}: tiene título", len(r["titulos"]) >= 1, r["titulos"])
    caso(f"{nombre}: ningún id repetido en la página", not r["ids_repetidos"], r["ids_repetidos"])
    caso(f"{nombre}: los filtros, de lo general a lo concreto", r["filtros"] == ORDEN_FILTROS, r["filtros"])
    caso(f"{nombre}: las pestañas, en su orden", r["pestanas"] == PESTANAS, r["pestanas"])
    caso(f"{nombre}: ningún selector sin opciones", not r["selects_vacios"], r["selects_vacios"])
    caso(f"{nombre}: el pie dice la fuente y la fecha", "Fuente" in r["pie"] and FECHA in r["pie"], r["pie"])
    if r["pestana"] in COLUMNAS:
        caso(f"{nombre}: las columnas de la tabla, en su orden", r["columnas"] == COLUMNAS[r["pestana"]], r["columnas"])
        caso(f"{nombre}: HOBBIES_2 con la regla que se recomienda, marcada",
             all(REGLA_HOBBIES in x and "se recomienda" in x for x in r["filas_hobbies"]), r["filas_hobbies"][:2])
        caso(f"{nombre}: el resto, con el modelo", all(x.startswith("el modelo") for x in r["filas_otras"]),
             sorted(set(r["filas_otras"]))[:3])
    if r["pestana"] == "p-proximos":
        # El responsable del caso, tras la petición 32: sin HOBBIES_2 en la selección, la cifra de la regla no habla de HOBBIES_2
        partes = dict(x.split("=", 1) for x in r["hash"].lstrip("#").split("&"))
        con_hobbies = partes.get("categoria") in (None, "HOBBIES") and partes.get("departamento") in (None, "HOBBIES_2")
        ctx = r["contextos"].get("con_regla", "")
        if con_hobbies:
            caso(f"{nombre}: con HOBBIES_2, la cifra de la regla lo dice", ctx == "HOBBIES_2, la regla que se recomienda", ctx)
        else:
            caso(f"{nombre}: sin HOBBIES_2, la cifra de la regla dice que todo va con el modelo",
                 "HOBBIES_2" not in ctx and "previsión del modelo" in ctx, ctx)
    if r["pestana"] in ("p-vision", "p-festivos"):
        # La venta en azul y continua; la previsión en el segundo color y discontinua (el responsable del caso, tras la petición 32)
        continuas = sorted(set(x["color"] for x in r["lineas"] if not x["raya"]))
        rayadas = sorted(set(x["color"] for x in r["lineas"] if x["raya"]))
        caso(f"{nombre}: la venta, en azul y continua", continuas == [AZUL], continuas)
        caso(f"{nombre}: la previsión, en el segundo color y discontinua", rayadas == [SEGUNDA], rayadas)
        caso(f"{nombre}: la leyenda de la previsión, en el segundo color", r["leyenda_raya"] == [SEGUNDA], r["leyenda_raya"])
    if r["pestana"] == "p-vision":
        # El gráfico de la visión general va por semana de Walmart: 52 semanas enteras del 23/05/2015 al 20/05/2016;
        # la del 25 de diciembre, con 6 días y dicho en su etiqueta
        s = r["semanas"]
        caso(f"{nombre}: el gráfico dice «por semana» en el título y el subtítulo",
             "por semana" in s["titulo"] and "por semana" in s["sub"], s)
        caso(f"{nombre}: 52 semanas", s["puntos"] == 52, s["puntos"])
        caso(f"{nombre}: la primera semana va del 23/05/2015 al 29/05/2015",
             s["primera"].startswith("Semana del 23/05/2015 al 29/05/2015"), s["primera"])
        caso(f"{nombre}: la semana del 25 de diciembre dice que tiene 6 días", len(s["navidad"]) == 1
             and "19/12/2015 al 25/12/2015" in s["navidad"][0] and "6 días" in s["navidad"][0], s["navidad"])
    if r["pestana"] in ("p-vision", "p-pedido", "p-donde", "p-festivos"):
        # La leyenda, justo debajo del título del gráfico, a la izquierda y pegada a él; no suelta dentro del dibujo
        caso(f"{nombre}: la leyenda va justo debajo del título del gráfico",
             r["leyenda"] and all(x["debajo"] and x["izquierda"] <= 2 and 0 <= x["hueco"] <= 6 for x in r["leyenda"]),
             r["leyenda"])
        caso(f"{nombre}: ninguna leyenda suelta dentro del dibujo", r["leyendas_dentro"] == 0, r["leyendas_dentro"])
    if r["pestana"] in ("p-pedido", "p-donde"):
        # El modelo en azul (naranja donde falla más, G3) y la regla en el segundo color
        caso(f"{nombre}: la regla, en el segundo color", SEGUNDA in r["barras"]
             and set(r["barras"]) <= {AZUL, SEGUNDA, NARANJA}, r["barras"])
    puestos = [r["viendo"].find(x) for x in orden_viendo(r["hash"])]
    caso(f"{nombre}: la línea «Viendo» nombra los filtros en su orden", puestos == sorted(puestos) and -1 not in puestos,
         (r["viendo"], orden_viendo(r["hash"])))
    for t in r["titulos"]:
        caso(f"{nombre}: título sin coma ni dos puntos «{t['texto']}»", "," not in t["texto"] and ":" not in t["texto"])
        if "falla menos" in t["texto"]:
            caso(f"{nombre}: el título que concluye está marcado «{t['texto']}»", t["concluye"] == "si", t)
            gana = int(t["gana"]) if t["gana"] not in (None, "") else -1
            de = int(t["de"]) if t["de"] not in (None, "") else -1
            caso(f"{nombre}: el título concluye con 10 de 13 pruebas o más «{t['texto']}»",
                 gana >= MINIMO_GANA and de == DE_PRUEBAS, t)


def main():
    """Lanza los casos."""
    if not caso("existe informes/cuadro_mando.html", HTML.is_file(), "lanza antes scripts/21_cuadro_mando.py"):
        print(f"{len(FALLOS)} FALLA")
        return 1
    combos = combinaciones()
    caso("son 25 combinaciones", len(combos) == 25, len(combos))
    pruebas = [{"hash": direccion(p, c)} for c in combos for p in PESTANAS]
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    try:
        resultado = medir_en_edge(pruebas)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    direcciones = [r["direccion"] for r in resultado if "direccion" in r]
    caso("la dirección pone los filtros de lo general a lo concreto",
         direcciones == ["#pestana=vision&estado=WI&tienda=WI_2&categoria=FOODS&departamento=FOODS_3"], direcciones)
    resultado = [r for r in resultado if "direccion" not in r]
    errores = [r for r in resultado if "error" in r]
    caso("la página de prueba no da error", not errores, errores[:1])
    medidas = [r for r in resultado if "error" not in r]
    caso("se midieron todas las pestañas", len(medidas) == len(pruebas), (len(medidas), len(pruebas)))
    for r in medidas:
        comprobar_pestana(r)
    print("palabras como mucho por pestaña:",
          {p: max((r["palabras"] for r in medidas if r["pestana"] == f"p-{p}"), default=None) for p in PESTANAS})
    # Las cifras sin filtros, contra las de referencia
    ref = json.loads(REFERENCIA.read_text(encoding="utf-8")).get("cifras", {}) if REFERENCIA.is_file() else {}
    caso("hay cifras del cuadro de referencia", bool(ref), f"falta {REFERENCIA.name} o su clave cifras")
    sin_filtros = {f"{r['pestana'][2:]}.{v['id']}": v["valor"] for r in medidas if r["hash"].count("&") == 0
                   for v in r["valores"]}
    for clave, esperado in ref.items():
        sale = sin_filtros.get(clave)
        igual = (sale not in (None, "") and abs(float(sale) - esperado) <= 1e-9 * max(1.0, abs(esperado)))
        caso(f"referencia {clave}", igual, f"sale {sale}, referencia {esperado}")
    caso("toda cifra sin filtros tiene referencia", set(sin_filtros) == set(ref), set(sin_filtros) ^ set(ref))
    print(f"{len(medidas)} pestañas medidas; " + (f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA"))
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
