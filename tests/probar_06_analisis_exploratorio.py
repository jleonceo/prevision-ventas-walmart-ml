"""Prueba de scripts/06_analisis_exploratorio.py.

Sin argumentos usa solo tablas pequeñas escritas aquí, en tests/tmp_exploratorio/, que se crea y se borra. No lee
ningún informe ni documento vivo del caso: el JSON de la transformación que necesita el script se escribe aquí con el
estado que se prueba (error 31). Importa solo el script que prueba, que tiene su trabajo dentro de
`if __name__ == "__main__":`, y además lo ejecuta como proceso aparte con --raiz y -W error.

Cada caso lleva su rojo: la misma comprobación se pasa a un «mutante», el script con la pieza que evita el error
cambiada aquí dentro, y tiene que fallar. Así cada verde puede dar rojo (error 24).

Los casos:
  1. una fila de la validación no entra en ningún cálculo, salvo los tres totales;
  2. un día SNAP después del día 15 no entra en el efecto de SNAP;
  3. un evento con menos de 30 días de serie en un departamento no da efecto; con 30 justos, sí (control que no debe
     disparar);
  4. el día normal no usa una semana con evento ni un día fuera del error;
  5. ninguna columna posterior al día se cruza con el objetivo como variable (se busca en el código);
  6. el día más fuerte entre el más flojo, con un caso calculado a mano (14 / 10 = 1,4);
  7. el script no escribe ninguna comprobación con su resultado puesto (error 24);
  8. el script entero, como proceso aparte con -W error, deja su JSON y su HTML y no cambia sus tablas de entrada;
  9. las observaciones de la persona escritas en el JSON se conservan al volver a ejecutar, y cada pendiente de zona
     gris que contestan pasa a contestada; con una sin contestar el estado sigue en AVISO (control).

Con --datos rehace además por otro camino, numpy sobre la matriz de series por días y sin groupby de pandas, el efecto de
SNAP y el de Acción de Gracias de cada departamento, y los compara con informes/analisis-exploratorio__hechos_series.json
(programacion-del-caso §6). La vía 1 es el script: groupby de pandas sobre la tabla larga. La vía 2 parte de
hechos_series.parquet, la coloca en una matriz de 70 series por 1.575 días con índices y recorre los días a mano.
Comprueba también los totales contra tests/cifras_de_referencia.json y las huellas de las cuatro tablas contra las del
petición.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "06_analisis_exploratorio.py"
TMP = RAIZ / "tests" / "tmp_exploratorio"
FALLOS = []
BASE = pd.Timestamp("2013-01-05")  # un sábado: wday 1, como en el Calendario de Walmart
POSTERIORES = {"cierre_tienda", "fuera_del_error", "clase_cero"}
APARTADOS = ["Resumen ejecutivo", "Contexto", "Visión general", "Variables numéricas", "Variables categóricas",
             "Análisis temporal", "Frente al objetivo", "Hallazgos principales", "Alertas y limitaciones",
             "Hipótesis y preguntas abiertas", "Observaciones de la persona", "Comprobaciones aplicadas",
             "Parámetros usados", "Datos personales", "Siguiente paso"]
# Huellas de las cuatro tablas, copiadas de la petición del paso 4 (prompt del exploratorio, CRITERIO DE ÉXITO)
HUELLAS_PETICION = {
    "hechos_series.parquet": "31a6a1fbac4f87437ebdd70ca6ab06f55c189fcc87e8150c5d5d319056abf165",
    "dim_producto.parquet": "5aa2ad7d0fc32f190175caa7ce67f64aaafd407c6105618ead65bb86b336c1e7",
    "dim_tienda.parquet": "744be76903218a6be24190f316231c569387936f0212b43068aed1715ef3571c",
    "calendario.parquet": "a8478ae161ca3e4c99e5f8fa7530ba2a4f73f7e954bf785decefa975c32fbeda",
}


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def huella(ruta):
    """SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__, así que importarlo no lo ejecuta)."""
    spec = importlib.util.spec_from_file_location("exploratorio_06", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def cerca(a, b, tolerancia=1e-9):
    """Cierto si los dos números existen y se diferencian en menos de la tolerancia."""
    return a is not None and b is not None and abs(float(a) - float(b)) < tolerancia


# ── 2. Tablas pequeñas ─────────────────────────────────────────────────────────
def serie(tienda, dept, unidades, desde=0, periodo=None, snap=None, evento=None, fuera=None, cat="C1", estado="CA",
          inicio=BASE):
    """Una serie con sus 26 columnas, día a día desde `inicio` + `desde` días.

    `periodo`, `snap`, `evento` y `fuera` son diccionarios {posición: valor}; lo que no está vale construcción, 0,
    sin evento y falso.
    """
    n = len(unidades)
    periodo, snap, evento, fuera = periodo or {}, snap or {}, evento or {}, fuera or {}
    fechas = pd.DatetimeIndex([inicio + pd.Timedelta(days=desde + i) for i in range(n)])
    dias = (fechas - BASE).days.to_numpy()
    u = np.asarray(unidades, dtype="int64")
    ev = [evento.get(i) for i in range(n)]
    fu = np.array([bool(fuera.get(i, False)) for i in range(n)])
    clase = [None if u[i] > 0 else ("cierre" if fu[i] else "resto") for i in range(n)]
    return pd.DataFrame({
        "store_id": pd.Series([tienda] * n, dtype="str"),
        "dept_id": pd.Series([dept] * n, dtype="str"),
        "d": pd.Series([f"d_{x + 1}" for x in dias], dtype="str"),
        "cat_id": pd.Series([cat] * n, dtype="str"),
        "state_id": pd.Series([estado] * n, dtype="str"),
        "unidades": u,
        "dolares": u * 2.0,
        "date": fechas.astype("datetime64[us]"),
        "year": pd.Series(fechas.year, dtype="int64"),
        "month": pd.Series(fechas.month, dtype="int64"),
        "weekday": pd.Series(fechas.day_name(), dtype="str"),
        "wday": pd.Series((fechas.dayofweek - 5) % 7 + 1, dtype="int64"),
        "wm_yr_wk": pd.Series(11300 + dias // 7, dtype="int64"),
        "wm_yr_wk_anterior": pd.Series(11299 + dias // 7, dtype="Int64"),
        "event_name_1": pd.Series(ev, dtype="str"),
        "event_type_1": pd.Series([None if e is None else "Cultural" for e in ev], dtype="str"),
        "event_name_2": pd.Series([None] * n, dtype="str"),
        "event_type_2": pd.Series([None] * n, dtype="str"),
        "snap": pd.Series([int(snap.get(i, 0)) for i in range(n)], dtype="int64"),
        "periodo": pd.Series([periodo.get(i, "construccion") for i in range(n)], dtype="str"),
        "mes_parcial": pd.Series([False] * n, dtype="bool"),
        "semana_parcial": pd.Series([False] * n, dtype="bool"),
        "cierre_tienda": pd.Series(fu, dtype="bool"),
        "fuera_del_error": pd.Series(fu, dtype="bool"),
        "clase_cero": pd.Series(clase, dtype="str"),
        "precio_medio_semana_anterior": pd.Series([2.0 + 0.01 * (x // 7) for x in dias], dtype="float64"),
    })


def tabla_snap():
    """Una serie en febrero (construcción) y diez días de marzo (validación).

    - días 1 a 10 y 15, SNAP, 12 unidades; días 11 a 14, sin SNAP, 10 unidades: el efecto es 12 / 10 - 1 = 20 %;
    - días 16 a 28, SNAP, 100 unidades: la trampa del día SNAP después del 15;
    - 1 a 10 de marzo, validación, SNAP, 1.000 unidades: la trampa de la validación.
    """
    u, snap, periodo = [], {}, {}
    for i, dia in enumerate(range(1, 29)):
        con_snap = dia <= 10 or dia >= 15
        snap[i] = int(con_snap)
        u.append(12 if dia <= 15 and con_snap else (10 if dia <= 15 else 100))
    for j in range(10):
        snap[28 + j], periodo[28 + j] = 1, "validacion"
        u.append(1000)
    return serie("S1", "D1", u, periodo=periodo, snap=snap, inicio=pd.Timestamp("2013-02-01"))


def tabla_eventos(dias=200, validacion=28):
    """Diez tiendas de un departamento, 200 días de construcción y 28 de validación, 10 unidades cada día normal.

    - E30, los días 35, 63 y 91 (sábados), 15 unidades: 30 días de serie y efecto 15 / 10 - 1 = 50 %;
    - EX, el día 21, 50 unidades; el día 14, fuera del error con 0: las dos trampas del día normal del día 35;
    - E20, los días 100 y 107, 30 unidades: 20 días de serie, no da efecto;
    - E30 otra vez el día 203, en la validación, con 1.000 unidades: la trampa de la validación.
    """
    n = dias + validacion
    u = [10] * n
    evento, fuera, periodo = {}, {14: True}, {i: "validacion" for i in range(dias, n)}
    for t in (35, 63, 91):
        evento[t], u[t] = "E30", 15
    evento[21], u[21], u[14] = "EX", 50, 0
    for t in (100, 107):
        evento[t], u[t] = "E20", 30
    evento[203], u[203] = "E30", 1000
    return pd.concat([serie(f"S{k}", "D1", u, periodo=periodo, evento=evento, fuera=fuera) for k in range(10)],
                     ignore_index=True)


def tabla_semana():
    """Una serie de tres semanas de construcción y una de validación, de sábado a viernes.

    Ritmo: sábado 14, domingo 12, lunes 10, martes 10, miércoles 11, jueves 11 y viernes 12. El martes de la tercera
    semana está fuera del error con 0 unidades. A mano: el día más fuerte (sábado, 14) entre el más flojo (lunes o
    martes, 10) da 1,4. Con el día fuera del error dentro, el martes bajaría a 6,67 y saldría 2,1. La validación trae
    un sábado de 1.000 unidades.
    """
    ritmo = [14, 12, 10, 10, 11, 11, 12]
    u = ritmo * 3 + [1000] + ritmo[1:]
    u[17] = 0
    periodo = {i: "validacion" for i in range(21, 28)}
    return serie("S1", "D1", u, periodo=periodo, fuera={17: True})


# ── 3. Casos sobre las funciones ───────────────────────────────────────────────
def probar_snap(m):
    """Caso 2 (y 1): el efecto de SNAP solo con los días 1 a 15 y solo con la construcción."""
    t = tabla_snap()
    bueno = m.efecto_snap(m.poblacion(t))["D1"]["cambio_pct"]
    comprobar(cerca(bueno, 20.0), f"SNAP: 12 / 10 - 1 = 20 % (sale {bueno})")
    # Rojo: el mutante deja entrar los días después del 15
    original = m.en_quincena
    m.en_quincena = lambda dia: np.ones(len(dia), dtype=bool)
    try:
        mutante = m.efecto_snap(m.poblacion(t))["D1"]["cambio_pct"]
    finally:
        m.en_quincena = original
    comprobar(not cerca(mutante, 20.0), f"rojo · un día SNAP después del 15 cambia el efecto (mutante {mutante})")
    # Rojo: el mutante no quita la validación
    mutante_val = m.efecto_snap(t)["D1"]["cambio_pct"]
    comprobar(not cerca(mutante_val, 20.0), f"rojo · la validación cambia el efecto de SNAP (mutante {mutante_val})")


def efecto_de(lista, evento, dept="D1"):
    """La fila de un evento y un departamento en la lista de efectos."""
    filas = [e for e in lista if e["evento"] == evento and e["departamento"] == dept]
    return filas[0] if len(filas) == 1 else None


def probar_eventos(m):
    """Casos 3 y 4 (y 1): mínimo de 30 días de serie, día normal sin eventos ni días fuera del error."""
    t = tabla_eventos()
    ef = m.efecto_eventos(m.poblacion(t))
    e30, e20, ex = efecto_de(ef, "E30"), efecto_de(ef, "E20"), efecto_de(ef, "EX")
    comprobar(e30 is not None and e30["dias_serie"] == 30 and cerca(e30["cambio_pct"], 50.0),
              f"control que no debe disparar · E30 con 30 días justos da su efecto, 50 % ({e30})")
    comprobar(e20 is not None and e20["dias_serie"] == 20 and e20["cambio_pct"] is None,
              f"E20 con 20 días de serie no da efecto y dice cuántos tiene ({e20})")
    comprobar(ex is not None and ex["dias_serie"] == 10 and ex["cambio_pct"] is None,
              f"EX con 10 días de serie no da efecto ({ex})")
    # Rojo del mínimo: con el mínimo a cero, E20 daría efecto
    original_min = m.MINIMO_DIAS_EVENTO
    m.MINIMO_DIAS_EVENTO = 0
    try:
        mut = efecto_de(m.efecto_eventos(m.poblacion(t)), "E20")
    finally:
        m.MINIMO_DIAS_EVENTO = original_min
    comprobar(mut is not None and mut["cambio_pct"] is not None,
              f"rojo · sin el mínimo de 30 días, E20 da efecto (mutante {mut and mut['cambio_pct']})")
    # Rojo del día normal: con las semanas de evento dentro, y con los días fuera del error dentro
    original = m.semana_vale_para_normal
    for nombre, mutante in [("una semana con evento", lambda e, f: ~f),
                            ("un día fuera del error", lambda e, f: ~e)]:
        m.semana_vale_para_normal = mutante
        try:
            mut = efecto_de(m.efecto_eventos(m.poblacion(t)), "E30")
        finally:
            m.semana_vale_para_normal = original
        comprobar(mut is not None and not cerca(mut["cambio_pct"], 50.0),
                  f"rojo · un día normal que incluye {nombre} cambia el efecto de E30 (mutante {mut and mut['cambio_pct']})")
    # Rojo de la validación: sin quitarla, E30 tiene 40 días y otro efecto
    mut = efecto_de(m.efecto_eventos(t), "E30")
    comprobar(mut is not None and mut["dias_serie"] == 40 and not cerca(mut["cambio_pct"], 50.0),
              f"rojo · la validación cambia el efecto de E30 (mutante {mut})")


def probar_dia_semana(m):
    """Caso 6 (y 1): el día más fuerte entre el más flojo, calculado a mano."""
    t = tabla_semana()
    r = m.efecto_dia_semana(m.poblacion(t))["D1"]
    comprobar(cerca(r["cociente"], 1.4) and r["dia_fuerte"] == "Saturday" and r["dia_flojo"] == "Monday",
              f"día de la semana: 14 / 10 = 1,4, sábado entre lunes ({r})")
    original = m.sin_fuera
    m.sin_fuera = lambda df: df
    try:
        mut = m.efecto_dia_semana(m.poblacion(t))["D1"]["cociente"]
    finally:
        m.sin_fuera = original
    comprobar(not cerca(mut, 1.4), f"rojo · con el día fuera del error dentro el cociente cambia (mutante {mut})")
    mut_val = m.efecto_dia_semana(t)["D1"]["cociente"]
    comprobar(not cerca(mut_val, 1.4), f"rojo · con la validación dentro el cociente cambia (mutante {mut_val})")


def variables_cruzadas_en(codigo):
    """La lista literal VARIABLES_FRENTE_OBJETIVO del código, leída con ast."""
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Assign) and any(getattr(x, "id", None) == "VARIABLES_FRENTE_OBJETIVO"
                                                for x in nodo.targets):
            return [ast.literal_eval(e) for e in nodo.value.elts]
    return None


def probar_posteriores(m):
    """Caso 5: ninguna columna posterior al día se cruza con el objetivo como variable (en el código)."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    lista = variables_cruzadas_en(codigo)
    comprobar(lista is not None and not (set(lista) & POSTERIORES),
              f"el código no cruza ninguna columna posterior con el objetivo ({lista})")
    # Rojo: el mismo código con cierre_tienda añadido a la lista
    mutante = codigo.replace("VARIABLES_FRENTE_OBJETIVO = [", "VARIABLES_FRENTE_OBJETIVO = [\"cierre_tienda\", ", 1)
    lista_mut = variables_cruzadas_en(mutante)
    comprobar(lista_mut is not None and bool(set(lista_mut) & POSTERIORES),
              "rojo · la búsqueda en el código ve una columna posterior añadida a la lista")
    # La guarda del script para si se le pasa una columna posterior
    try:
        m.comprobar_sin_posteriores(list(m.VARIABLES_FRENTE_OBJETIVO) + ["clase_cero"], POSTERIORES)
        paro = False
    except ValueError:
        paro = True
    comprobar(paro, "rojo · la guarda del script para con una columna posterior en la lista")
    try:
        m.comprobar_sin_posteriores(list(m.VARIABLES_FRENTE_OBJETIVO), POSTERIORES)
        sigue = True
    except ValueError:
        sigue = False
    comprobar(sigue, "control que no debe disparar · la guarda deja pasar la lista del script")


def probar_sin_veredictos_escritos():
    """Caso 7, error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    patron = r"[\"'](coincide|pasa|cumple|iguales|dentro|posible_fuga|salto|hecho)[\"']\s*:\s*(True|False)\b"
    puestos = re.findall(patron, codigo)
    puestos += re.findall(r"[\"']resultado[\"']\s*:\s*[\"'](pasa|falla)[\"']\s*[,}]", codigo)
    comprobar(puestos == [], f"el script no escribe ninguna comprobación con su resultado puesto ({puestos})")
    comprobar(re.findall(patron, "x = {\"coincide\": True}") != [], "rojo · la búsqueda ve un veredicto escrito")


# ── 4. Caso 1 sobre el análisis entero y el script como proceso aparte ────────
def tablas_prueba():
    """Las cuatro tablas del caso de prueba: la de eventos con una segunda serie de semana y sus dimensiones."""
    h = pd.concat([tabla_eventos(), serie("S0", "D2", ([14, 12, 10, 10, 11, 11, 12] * 33)[:228], cat="C2",
                                          periodo={i: "validacion" for i in range(200, 228)})], ignore_index=True)
    h = h.sort_values(["store_id", "dept_id", "date"], ignore_index=True)
    dim_p = pd.DataFrame({"item_id": pd.Series(["P1", "P2", "P3"], dtype="str"),
                          "dept_id": pd.Series(["D1", "D1", "D2"], dtype="str"),
                          "cat_id": pd.Series(["C1", "C1", "C2"], dtype="str")})
    dim_t = pd.DataFrame({"store_id": pd.Series([f"S{k}" for k in range(10)], dtype="str"),
                          "state_id": pd.Series(["CA"] * 10, dtype="str")})
    dias = h[["d", "date"]].drop_duplicates().sort_values("date", ignore_index=True)
    cal = pd.DataFrame({"d": dias["d"], "date": dias["date"]})
    return {"hechos_series": h, "dim_producto": dim_p, "dim_tienda": dim_t, "calendario": cal}


TRANSFORMACION_PRUEBA = {
    "fecha_datos": "2015-05-22",
    "resultado": {"estado": "OK"},
    "variables_generadas": [
        {"columna": "unidades", "informacion_posterior": True, "sale_del_objetivo": True},
        {"columna": "dolares", "informacion_posterior": True, "sale_del_objetivo": True},
        {"columna": "snap", "informacion_posterior": False, "sale_del_objetivo": False},
        {"columna": "cierre_tienda", "informacion_posterior": True, "sale_del_objetivo": True},
        {"columna": "fuera_del_error", "informacion_posterior": True, "sale_del_objetivo": True},
        {"columna": "clase_cero", "informacion_posterior": True, "sale_del_objetivo": True},
        {"columna": "precio_medio_semana_anterior", "informacion_posterior": False, "sale_del_objetivo": False},
    ],
}


def sin_validacion(d):
    """El resultado sin lo que puede cambiar con la validación sin que sea un error: sus totales y las fechas."""
    d = json.loads(json.dumps(d, default=str))
    d["poblacion"].pop("validacion", None)
    for clave in ("fecha_ejecucion", "duracion_segundos", "entradas", "huellas_despues", "dataset"):
        d.pop(clave, None)
    return d


def probar_validacion_entera(m):
    """Caso 1: con la validación cambiada, todo el análisis sale igual salvo sus tres totales."""
    tablas = tablas_prueba()
    otra = {k: v.copy() for k, v in tablas.items()}
    val = otra["hechos_series"]["periodo"].eq("validacion")
    otra["hechos_series"].loc[val, "unidades"] = otra["hechos_series"].loc[val, "unidades"] * 3 + 7
    otra["hechos_series"].loc[val, "dolares"] = otra["hechos_series"].loc[val, "unidades"] * 2.0
    a = m.analizar(tablas, TRANSFORMACION_PRUEBA, {}, {})
    b = m.analizar(otra, TRANSFORMACION_PRUEBA, {}, {})
    comprobar(sin_validacion(a) == sin_validacion(b), "la validación solo cambia sus tres totales")
    comprobar(a["poblacion"]["validacion"] != b["poblacion"]["validacion"]
              and set(a["poblacion"]["validacion"]) == {"filas", "unidades", "dolares"},
              f"de la validación salen solo filas, unidades y dólares ({a['poblacion']['validacion']})")
    original = m.poblacion
    m.poblacion = lambda df: df
    try:
        ma = m.analizar(tablas, TRANSFORMACION_PRUEBA, {}, {})
        mb = m.analizar(otra, TRANSFORMACION_PRUEBA, {}, {})
    finally:
        m.poblacion = original
    comprobar(sin_validacion(ma) != sin_validacion(mb), "rojo · sin quitar la validación, el análisis cambia con ella")


def probar_script_entero():
    """Caso 8: el script como proceso aparte, con -W error, sobre una copia mínima de la estructura del caso."""
    raiz = TMP / "caso"
    proc_dir = raiz / "data" / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (raiz / "informes").mkdir(parents=True, exist_ok=True)
    for nombre, t in tablas_prueba().items():
        t.to_parquet(proc_dir / f"{nombre}.parquet", index=False)
    (raiz / "informes" / "transformacion-datos.json").write_text(json.dumps(TRANSFORMACION_PRUEBA), encoding="utf-8")
    antes = {p.name: huella(p) for p in proc_dir.glob("*.parquet")}
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)], capture_output=True,
                          text=True, encoding="utf-8", env=entorno, timeout=600)
    comprobar(proc.returncode == 0, f"el script sale con 0 con -W error ({proc.returncode}: {proc.stderr[-1500:]})")
    ruta_j = raiz / "informes" / "analisis-exploratorio__hechos_series.json"
    ruta_h = raiz / "informes" / "analisis-exploratorio__hechos_series.html"
    comprobar(ruta_j.exists() and ruta_h.exists(), "deja el JSON y el HTML con el nombre de la tabla")
    comprobar({p.name: huella(p) for p in proc_dir.glob("*.parquet")} == antes, "las tablas de entrada no cambian")
    if not (ruta_j.exists() and ruta_h.exists()):
        return
    d = json.loads(ruta_j.read_text(encoding="utf-8"))
    comprobar("NaN" not in ruta_j.read_text(encoding="utf-8") and "Infinity" not in ruta_j.read_text(encoding="utf-8"),
              "el JSON no lleva NaN ni Infinity")
    comprobar(d["fecha_datos"] == "2015-05-22" and d["resultado"]["estado"] in ("OK", "AVISO"),
              f"fecha_datos leída de la transformación y estado válido ({d['fecha_datos']}, {d['resultado']['estado']})")
    comprobar(len(d["comprobaciones"]) == 18, f"las 18 comprobaciones con su estado ({len(d['comprobaciones'])})")
    comprobar(d["observaciones"] == [] and d["siguiente_paso"] in ("con_esto_basta", "hace_falta_modelar",
                                                                   "volver_a_limpiar", "falta_un_dato"),
              "observaciones vacías y un siguiente paso de la lista")
    fo = d["frente_al_objetivo"]
    comprobar(fo["filas_usadas"] == "construccion" and not (set(v["columna"] for v in fo["variables"]) & POSTERIORES),
              "el bloque frente al objetivo usa la construcción y ninguna columna posterior")
    html = ruta_h.read_text(encoding="utf-8")
    titulos = re.findall(r"<h2[^>]*>(.*?)</h2>", html)
    comprobar([t for t in titulos if t in APARTADOS] == APARTADOS, f"el HTML tiene los apartados de la plantilla en orden")
    texto = re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", html, flags=re.S))
    comprobar(", y " not in texto, "el texto del HTML (sin la hoja de estilo común) no une dos partes con «, y»")
    nombres = {p["nombre"] for p in d["parametros"]}
    comprobar(len(nombres) >= 7, f"los parámetros llevan al menos las siete filas de parametros.md ({len(nombres)})")
    probar_observaciones(raiz, ruta_j, entorno)


def probar_observaciones(raiz, ruta_j, entorno):
    """Caso 9, comprobación 16: las observaciones escritas en el JSON sobreviven a la siguiente ejecución.

    Cada pendiente de zona gris con una observación que la contesta (`responde_a` con el nombre de su fila) pasa a
    contestada, con la respuesta al lado. El estado es OK solo si no queda ninguna abierta. Primero se contestan todas
    menos una (control: sigue en AVISO) y después todas.
    """
    d = json.loads(ruta_j.read_text(encoding="utf-8"))
    filas = [p.get("fila") for p in d["pendientes"]]
    comprobar(len(filas) >= 1 and all(filas), f"cada pendiente nombra su fila de «Lo esperable» ({filas})")
    if not filas or not all(filas):
        return

    def ejecutar_con(respuestas):
        d_ = json.loads(ruta_j.read_text(encoding="utf-8"))
        d_["observaciones"] = [{"bloque": "Lo esperable", "tipo": "decisión", "columnas": ["unidades"],
                                "texto": f"Normal: {f}", "fecha": "2026-11-24", "responde_a": f} for f in respuestas]
        ruta_j.write_text(json.dumps(d_, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)], capture_output=True,
                              text=True, encoding="utf-8", env=entorno, timeout=600)
        comprobar(proc.returncode == 0, f"con observaciones, el script sale con 0 ({proc.returncode}: {proc.stderr[-800:]})")
        return json.loads(ruta_j.read_text(encoding="utf-8"))

    parcial = ejecutar_con(filas[1:])
    comprobar(len(parcial["observaciones"]) == len(filas) - 1,
              f"las observaciones escritas se conservan al volver a ejecutar ({len(parcial['observaciones'])})")
    abiertas = [p.get("fila") for p in parcial["pendientes"] if p.get("respuesta") is None]
    comprobar(abiertas == filas[:1] and parcial["resultado"]["estado"] == "AVISO",
              f"control · con una fila sin contestar sigue en AVISO ({abiertas}, {parcial['resultado']['estado']})")
    todas = ejecutar_con(filas)
    contestadas = [p for p in todas["pendientes"] if p.get("respuesta") is not None]
    comprobar(len(contestadas) == len(filas) and todas["resultado"]["estado"] == "OK",
              f"con todas contestadas, cada pendiente lleva su respuesta y el estado es OK "
              f"({len(contestadas)} de {len(filas)}, {todas['resultado']['estado']})")
    html = (raiz / "informes" / "analisis-exploratorio__hechos_series.html").read_text(encoding="utf-8")
    comprobar(f"Normal: {filas[0]}" in html, "el HTML enseña las observaciones de la persona")


# ── 5. Con los datos reales (solo con --datos) ─────────────────────────────────
def segunda_via():
    """Rehace con numpy sobre la matriz de series por días, sin groupby de pandas, SNAP y Acción de Gracias."""
    ruta = RAIZ / "informes" / "analisis-exploratorio__hechos_series.json"
    if not ruta.exists():
        comprobar(False, "existe informes/analisis-exploratorio__hechos_series.json")
        return
    d = json.loads(ruta.read_text(encoding="utf-8"))
    proc = RAIZ / "data" / "processed"
    for nombre, valor in HUELLAS_PETICION.items():
        comprobar(huella(proc / nombre) == valor, f"la huella de {nombre} es la de la petición")
    h = pd.read_parquet(proc / "hechos_series.parquet")
    # La matriz: una fila por serie (tienda y departamento) y una columna por día, colocada con índices
    clave = (h["store_id"] + "|" + h["dept_id"]).to_numpy()
    series, fila = np.unique(clave, return_inverse=True)
    col = np.array([int(x[2:]) - 1 for x in h["d"].to_numpy()])
    n_s, n_d = len(series), col.max() + 1
    U = np.zeros((n_s, n_d))
    U[fila, col] = h["unidades"].to_numpy()
    F = np.zeros((n_s, n_d), dtype=bool)
    F[fila, col] = h["fuera_del_error"].to_numpy()
    S = np.zeros((n_s, n_d), dtype=bool)
    S[fila, col] = h["snap"].to_numpy() == 1
    dia_mes = np.zeros(n_d, dtype=int)
    dia_mes[col] = h["date"].dt.day.to_numpy()
    construccion = np.zeros(n_d, dtype=bool)
    construccion[col] = h["periodo"].to_numpy() == "construccion"
    evento = np.full(n_d, "", dtype=object)
    evento[col] = h["event_name_1"].fillna("").to_numpy()
    dept_serie = np.array([s.split("|")[1] for s in series])
    # SNAP: días 1 a 15 de la construcción, sin los días fuera del error
    q = construccion & (dia_mes <= 15)
    for dept in sorted(set(dept_serie)):
        m = (dept_serie == dept)[:, None] & q[None, :] & ~F
        via2 = (U[m & S].mean() / U[m & ~S].mean() - 1) * 100
        via1 = d["pregunta_4"]["snap"][dept]["cambio_pct"]
        comprobar(cerca(via1, via2, 1e-6), f"SNAP de {dept} por las dos vías: {via1} y {via2}")
    # Acción de Gracias: cada día de evento frente a su día normal, recorrido a mano
    dias_ev = [j for j in range(n_d) if construccion[j] and evento[j] == "Thanksgiving"]
    for dept in sorted(set(dept_serie)):
        reales, normales = [], []
        for s in np.flatnonzero(dept_serie == dept):
            for j in dias_ev:
                if F[s, j]:
                    continue
                prev = [U[s, j - 7 * k] for k in range(1, 5)
                        if j - 7 * k >= 0 and construccion[j - 7 * k] and evento[j - 7 * k] == "" and not F[s, j - 7 * k]]
                if prev:
                    reales.append(U[s, j])
                    normales.append(sum(prev) / len(prev))
        via2 = (sum(reales) / len(reales)) / (sum(normales) / len(normales)) * 100 - 100
        fila_j = [e for e in d["pregunta_4"]["eventos"] if e["evento"] == "Thanksgiving" and e["departamento"] == dept]
        via1 = fila_j[0]["cambio_pct"] if fila_j else None
        comprobar(cerca(via1, via2, 1e-6) and fila_j[0]["dias_serie"] == len(reales),
                  f"Acción de Gracias de {dept} por las dos vías: {via1} y {via2} ({len(reales)} días)")
    # Los totales, contra las cifras de referencia de la transformación
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))["transformacion"]
    cifras = ref["cifras"]
    for p in ("construccion", "validacion"):
        comprobar(d["poblacion"][p]["filas"] == cifras["filas_por_periodo"][p]
                  and d["poblacion"][p]["unidades"] == cifras["unidades_por_periodo"][p]
                  and cerca(d["poblacion"][p]["dolares"], cifras["dolares_por_periodo"][p], 0.005),
                  f"totales de {p} iguales a las cifras de referencia")
    comprobar({e["ruta"].split("/")[-1]: e["sha256"] for e in d["entradas"] if e["ruta"].endswith(".parquet")}
              == HUELLAS_PETICION, "las huellas de entrada del JSON son las de la petición")


# ── 6. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_snap(modulo)
            probar_eventos(modulo)
            probar_dia_semana(modulo)
            probar_posteriores(modulo)
            probar_sin_veredictos_escritos()
            probar_validacion_entera(modulo)
            probar_script_entero()
        if "--datos" in sys.argv:
            segunda_via()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_exploratorio borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
