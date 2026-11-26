"""Prueba de que el navegador dice lo mismo que Python en informes/cuadro_mando.html.

1. En Edge sin ventana, en las combinaciones de la prueba de las pestañas, las cifras de arriba de cada pestaña
   (data-valor) son las que calcula resumen() del script con los datos que lleva el cuadro; los títulos, los que da
   titulos(); y el nombre y el texto del CSV de los próximos días, los de nombre_csv() y texto_csv().
2. En Python, resumen() en todas las combinaciones válidas de los cuatro filtros (cada tienda con su estado y cada
   departamento con su categoría: 14 × 11 = 154): cada pestaña con 3 a 4 cifras; la venta y lo previsto de cada estado
   suman lo de «Todos» con los demás filtros iguales, y lo de cada tienda suma lo de su estado; lo mismo con las
   categorías y los departamentos; las pruebas que gana nunca pasan de 13.

La carpeta tests/tmp_cuadro/ se crea y se borra siempre. Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_21_cuadro_mando_navegador.py
"""

# html deshace los escapes del resultado que deja Edge
import html
# importlib carga el script y la prueba de las pestañas por su ruta
import importlib.util
# itertools recorre las combinaciones
import itertools
# json lee el resultado de Edge
import json

import os
# re busca el resultado en el DOM
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
SCRIPT = RAIZ / "scripts" / "21_cuadro_mando.py"
PESTANAS_PY = RAIZ / "tests" / "probar_21_cuadro_mando_pestanas.py"
HTML = RAIZ / "informes" / "cuadro_mando.html"
TMP = RAIZ / "tests" / "tmp_cuadro"
EDGE = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
PESTANAS = ["vision", "pedido", "donde", "festivos", "proximos"]
TOLERANCIA = 1e-9
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso y dice si pasa."""
    if not condicion:
        print(f"FALLA {nombre} ({detalle})")
        FALLOS.append(nombre)
    return condicion


def cargar(ruta, nombre):
    """Carga un fichero de Python como módulo, sin ejecutar su principal."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


PAGINA = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<iframe id="cuadro" src="__SRC__" style="width:1366px;height:650px;border:0"></iframe>
<pre id="resultado"></pre>
<script>
const PRUEBAS = __PRUEBAS__;
const marco = document.getElementById('cuadro');
marco.addEventListener('load', () => {
  const salida = [];
  try {
    const win = marco.contentWindow, doc = marco.contentDocument;
    for (const p of PRUEBAS) {
      win.CUADRO.irA(p.hash);
      const sec = doc.querySelector('section.pestana:not([hidden])');
      const t = sec.querySelector('h2');
      const r = {hash: p.hash, valores: [...sec.querySelectorAll('.cifra')].map(c => ({id: c.dataset.id, valor: c.dataset.valor})),
        titulo: {texto: t.textContent, concluye: t.dataset.concluye}};
      if (sec.id === 'p-proximos') { r.nombre = win.CUADRO.nombreCsv(); r.csv = win.CUADRO.textoCsv(); }
      salida.push(r);
    }
  } catch (e) { salida.push({error: String(e) + ' ' + (e.stack || '')}); }
  document.getElementById('resultado').textContent = JSON.stringify(salida);
});
</script></body></html>"""


def medir_en_edge(pruebas):
    """Abre la página de prueba en Edge sin ventana y devuelve lo que leyó."""
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


def iguales(a, b):
    """Dos cifras iguales con la tolerancia de la prueba; vacío con vacío."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOLERANCIA * max(1.0, abs(float(b)))


def filtros_de(hash_):
    """La pestaña y los filtros de una dirección de la página."""
    partes = dict(p.split("=", 1) for p in hash_.lstrip("#").split("&"))
    return partes.pop("pestana"), partes


def parte_navegador(m, pe, datos):
    """Las cifras, los títulos y el CSV del navegador frente a los de Python."""
    combos = pe.combinaciones()
    pruebas = [{"hash": pe.direccion(p, c)} for c in combos for p in PESTANAS]
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    try:
        resultado = medir_en_edge(pruebas)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    errores = [r for r in resultado if "error" in r]
    caso("la página de prueba no da error", not errores, errores[:1])
    comparadas = 0
    for r in [x for x in resultado if "error" not in x]:
        pestana, f = filtros_de(r["hash"])
        esperado = {c["id"]: c["valor"] for c in m.resumen(datos, f)[pestana]}
        sale = {v["id"]: (None if v["valor"] in (None, "") else float(v["valor"])) for v in r["valores"]}
        caso(f"{r['hash']}: las mismas cifras", set(sale) == set(esperado), (set(sale), set(esperado)))
        for k in esperado:
            comparadas += 1
            caso(f"{r['hash']}: {k}", iguales(sale.get(k), esperado[k]), f"navegador {sale.get(k)}, Python {esperado[k]}")
        t = m.titulos(datos, f)[pestana]
        caso(f"{r['hash']}: el mismo título", r["titulo"]["texto"] == t["texto"]
             and r["titulo"]["concluye"] == ("si" if t["concluye"] else "no"), (r["titulo"], t))
        if pestana == "proximos":
            fn = m.normalizar(datos, f)
            caso(f"{r['hash']}: nombre del CSV", r["nombre"] == m.nombre_csv(datos, fn), (r["nombre"], m.nombre_csv(datos, fn)))
            texto = m.texto_csv(datos, fn)
            caso(f"{r['hash']}: texto del CSV", r["csv"] == texto, (r["csv"][:300], texto[:300]))
    print(f"navegador: {comparadas} cifras comparadas en {len(resultado)} pestañas")


def parte_python(m, datos):
    """resumen() en todas las combinaciones válidas de los cuatro filtros."""
    est_de = {t["id"]: t["estado"] for t in datos["tiendas"]}
    cat_de = {d["id"]: d["categoria"] for d in datos["departamentos"]}
    lugares = [(None, None)] + [(e["id"], None) for e in datos["estados"]] + [(est_de[t], t) for t in est_de]
    grupos = [(None, None)] + [(c["id"], None) for c in datos["categorias"]] + [(cat_de[d], d) for d in cat_de]
    res = {}
    for (estado, tienda), (categoria, dep) in itertools.product(lugares, grupos):
        f = {k: v for k, v in (("estado", estado), ("tienda", tienda), ("categoria", categoria),
                               ("departamento", dep)) if v is not None}
        r = m.resumen(datos, f)
        clave = (estado, tienda, categoria, dep)
        res[clave] = {p: {c["id"]: c["valor"] for c in r[p]} for p in PESTANAS}
        for p in PESTANAS:
            caso(f"{clave} {p}: de 3 a 4 cifras", 3 <= len(r[p]) <= 4, len(r[p]))
        for p, ident in (("vision", "pruebas_gana"), ("pedido", "pruebas_gana")):
            caso(f"{clave}: {p} {ident} entre 0 y 13", 0 <= res[clave][p][ident] <= 13, res[clave][p][ident])
    caso("son 154 combinaciones", len(res) == 154, len(res))
    sumas = 0
    aditivas = [("vision", "venta"), ("proximos", "unidades_10"), ("proximos", "dolares_10"), ("proximos", "dolares_28"),
                ("proximos", "con_regla")]
    for (estado, tienda, categoria, dep), r in res.items():
        # Las partes de un lugar: los estados de «Todos» o las tiendas de un estado; lo mismo con los grupos
        if estado is None:
            partes_l = [(e["id"], None) for e in datos["estados"]]
        elif tienda is None:
            partes_l = [(estado, t) for t in est_de if est_de[t] == estado]
        else:
            partes_l = []
        if categoria is None:
            partes_g = [(c["id"], None) for c in datos["categorias"]]
        elif dep is None:
            partes_g = [(categoria, d) for d in cat_de if cat_de[d] == categoria]
        else:
            partes_g = []
        for partes, como in ((partes_l, "lugar"), (partes_g, "grupo")):
            if not partes:
                continue
            for p, ident in aditivas:
                if como == "lugar":
                    suma = sum(res[(a, b, categoria, dep)][p][ident] for a, b in partes)
                else:
                    suma = sum(res[(estado, tienda, a, b)][p][ident] for a, b in partes)
                sumas += 1
                caso(f"{(estado, tienda, categoria, dep)} {ident}: las partes ({como}) suman el total",
                     abs(suma - r[p][ident]) <= 1e-6 * max(1.0, abs(r[p][ident])), (suma, r[p][ident]))
    print(f"python: 154 combinaciones y {sumas} sumas de partes comprobadas")


def main():
    """Lanza las dos partes."""
    if not caso("existe informes/cuadro_mando.html", HTML.is_file(), "lanza antes scripts/21_cuadro_mando.py"):
        print(f"{len(FALLOS)} FALLA")
        return 1
    m = cargar(SCRIPT, "cuadro_mando_69")
    pe = cargar(PESTANAS_PY, "probar_pestanas_69")
    datos = pe.datos_del_html()
    parte_navegador(m, pe, datos)
    parte_python(m, datos)
    print(f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
