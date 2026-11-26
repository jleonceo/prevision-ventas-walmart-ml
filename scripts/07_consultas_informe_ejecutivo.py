"""Consultas del informe ejecutivo del caso 69 (patrón assets/07_patron_informe_ejecutivo.md, §5).

Deja en informes/consultas-informe-ejecutivo.json, como una lista de cifras con su nombre, todo número que escribe el
informe ejecutivo y que no es un dato fijo de las reglas:
  - la venta de 2013 (el último año natural completo de la construcción), su media al día y las partes por categoría,
    sobre data/processed/hechos_series.parquet, solo con las filas de la construcción;
  - la parte de productos de tienda sin ningún cambio de precio en las semanas de la construcción, sobre
    data/processed/precios_corregido.parquet;
  - las cifras del exploratorio que usa el informe, leídas de informes/analisis-exploratorio__hechos_series.json.

Depende de scripts/06_analisis_exploratorio.py: lee su JSON y para si su estado no es OK.

Uso: python -W error scripts/07_consultas_informe_ejecutivo.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/07_consultas_informe_ejecutivo.py"
EXPLORATORIO = "informes/analisis-exploratorio__hechos_series.json"
HECHOS = "data/processed/hechos_series.parquet"
PRECIOS = "data/processed/precios_corregido.parquet"
SALIDA = "informes/consultas-informe-ejecutivo.json"
# El último año natural completo de la construcción (29/01/2011 a 22/05/2014); la cifra de dinero (el responsable del caso, 24/11/2026)
ANO = 2013
FIN_DE_SEMANA = ("Saturday", "Sunday")


class Parada(Exception):
    """Condición que impide dejar las consultas; el mensaje dice cuál."""


# =================================================================================================================
# 3. Consultas sobre las tablas
# =================================================================================================================
def solo_construccion(t):
    """Las filas de la construcción: la validación no entra en ninguna consulta (reglas, apartado 7, población)."""
    return t.loc[t["periodo"].eq("construccion")]


def venta_del_ano(hechos, ano):
    """Unidades y dólares del año en la construcción, su media de dólares al día y la parte de cada categoría."""
    t = solo_construccion(hechos)
    t = t.loc[t["date"].dt.year.eq(ano)]
    unidades, dolares = int(t["unidades"].sum()), float(t["dolares"].sum())
    por_cat = t.groupby("cat_id")[["unidades", "dolares"]].sum().sort_index()
    partes = {c: {"unidades_pct": float(r["unidades"]) / unidades * 100 if unidades else None,
                  "dolares_pct": float(r["dolares"]) / dolares * 100 if dolares else None}
              for c, r in por_cat.iterrows()}
    dias = int(t["date"].nunique())
    return {"unidades": unidades, "dolares": dolares, "dias": dias,
            "dolares_al_dia": dolares / dias if dias else None, "partes": partes}


def sin_cambio_de_precio(precios, semanas):
    """Parte de productos de tienda con un solo precio en las semanas dadas (las de la construcción)."""
    p = precios.loc[precios["wm_yr_wk"].isin(semanas)]
    distintos = p.groupby(["store_id", "item_id"])["sell_price"].nunique()
    return {"productos_tienda": int(len(distintos)),
            "pct": float((distintos == 1).mean() * 100) if len(distintos) else None}


# =================================================================================================================
# 4. Cifras del exploratorio
# =================================================================================================================
def es_alimentacion(departamento):
    """Cierto si el departamento es de alimentación (FOODS_1 a FOODS_3)."""
    return departamento.startswith("FOODS")


def cifras_del_exploratorio(j):
    """Las cifras del exploratorio que escribe el informe, con los grupos y sentidos que sus frases afirman."""
    p4 = j["pregunta_4"]
    c = {"departamentos_de_tienda_80_unidades": j["pareto"]["series_unidades"]["elementos_para_el_80"],
         "departamentos_de_tienda_80_dolares": j["pareto"]["series_dolares"]["elementos_para_el_80"],
         "departamentos_de_tienda": j["pareto"]["series_unidades"]["elementos"]}
    dep = {x["nombre"]: x for x in j["reparto"]["departamento"]}
    if "FOODS_3" in dep:
        c["parte_unidades_foods_3_pct"] = dep["FOODS_3"]["parte_unidades_pct"]
    # Festivos: la bajada se escribe sin signo, de la menor a la mayor; las frases dicen que todas son bajadas
    for evento, clave in [("Thanksgiving", "accion_gracias"), ("NewYear", "ano_nuevo")]:
        v = [e["cambio_pct"] for e in p4["eventos"] if e["evento"] == evento and e["cambio_pct"] is not None]
        c[f"{clave}_bajada_min_pct"] = -max(v) if v else None
        c[f"{clave}_bajada_max_pct"] = -min(v) if v else None
        c[f"{clave}_negativos"] = sum(x < 0 for x in v)
    # SNAP: alimentación por un lado y hogar y ocio por otro
    alim = [v["cambio_pct"] for d, v in p4["snap"].items() if es_alimentacion(d) and v["cambio_pct"] is not None]
    resto = [v["cambio_pct"] for d, v in p4["snap"].items() if not es_alimentacion(d) and v["cambio_pct"] is not None]
    c.update({"snap_alimentacion_min_pct": min(alim) if alim else None,
              "snap_alimentacion_max_pct": max(alim) if alim else None,
              "snap_resto_min_pct": min(resto) if resto else None, "snap_resto_max_pct": max(resto) if resto else None})
    # Día de la semana y meses
    cocientes = [v["cociente"] for v in p4["dia_semana"].values() if v["cociente"] is not None]
    c.update({"dia_cociente_min": min(cocientes) if cocientes else None,
              "dia_cociente_max": max(cocientes) if cocientes else None,
              "departamentos": len(p4["dia_semana"]),
              "dias_fuertes_fin_de_semana": sum(v["dia_fuerte"] in FIN_DE_SEMANA for v in p4["dia_semana"].values())})
    desvios = [abs(v["cambio_pct"]) for x in p4["mes"].values() for v in x["meses"].values()
               if v["cambio_pct"] is not None]
    c["mes_mayor_desvio_pct"] = max(desvios) if desvios else None
    # Cambios de nivel: cuántos, cuántas bajadas, cuántos de HOBBIES_2 y el mayor grupo de una tienda el mismo día
    con = [s for s in j["saltos"] if s["salto"]]
    grupos = {}
    for s in con:
        grupos.setdefault((s["tienda"], s["fecha"]), []).append(s["departamento"])
    (tienda, fecha), deps = max(grupos.items(), key=lambda kv: (len(kv[1]), kv[0][1] or "")) if grupos else ((None, None), [])
    c.update({"cambios_de_nivel": len(con), "cambios_de_nivel_bajadas": sum(s["razon"] < 1 for s in con),
              "cambios_de_nivel_hobbies_2": sum(s["departamento"] == "HOBBIES_2" for s in con),
              "cambios_mismo_dia_mayor": len(deps), "cambios_mismo_dia_tienda": tienda,
              "cambios_mismo_dia_fecha": fecha})
    # Días sin ventas
    pc = j["ceros"]["por_clase"]
    c.update({"dias_cierre": pc.get("cierre"), "dias_25_diciembre": pc.get("25_diciembre"),
              "dias_hobbies_2_a_cero": pc.get("demanda_intermitente"),
              "departamentos_de_tienda_hobbies_2": len(j["ceros"]["series_intermitentes"]),
              "dias_analizados": j["poblacion"]["construccion"]["dias"]})
    return c


# =================================================================================================================
# 5. Ejecución
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def principal(raiz):
    """Lee las tablas y el exploratorio, calcula las cifras y escribe el JSON."""
    ruta_j = raiz / EXPLORATORIO
    if not ruta_j.exists():
        raise Parada(f"falta {EXPLORATORIO}: se crea con scripts/06_analisis_exploratorio.py")
    j = json.loads(ruta_j.read_text(encoding="utf-8"))
    if j.get("resultado", {}).get("estado") != "OK":
        raise Parada(f"{EXPLORATORIO} no está en OK: el informe ejecutivo espera a que se contesten sus pendientes")
    antes = {r: sha256(raiz / r) for r in (HECHOS, PRECIOS)}
    hechos = pd.read_parquet(raiz / HECHOS, columns=["date", "periodo", "cat_id", "unidades", "dolares", "wm_yr_wk"])
    precios = pd.read_parquet(raiz / PRECIOS)

    # Cifras de las tablas y del exploratorio
    v = venta_del_ano(hechos, ANO)
    semanas = set(solo_construccion(hechos)["wm_yr_wk"])
    pr = sin_cambio_de_precio(precios, semanas)
    cifras = {"dolares_2013": v["dolares"], "dolares_2013_millones": v["dolares"] / 1e6, "unidades_2013": v["unidades"],
              "dias_2013": v["dias"], "dolares_al_dia_2013": v["dolares_al_dia"],
              "productos_tienda_construccion": pr["productos_tienda"], "sin_cambio_precio_pct": pr["pct"]}
    for cat, nombre in [("FOODS", "alimentacion"), ("HOUSEHOLD", "hogar"), ("HOBBIES", "ocio")]:
        cifras[f"parte_unidades_{nombre}_2013_pct"] = v["partes"].get(cat, {}).get("unidades_pct")
        cifras[f"parte_dolares_{nombre}_2013_pct"] = v["partes"].get(cat, {}).get("dolares_pct")
    cifras.update(cifras_del_exploratorio(j))

    # Las tablas no cambian; ninguna cifra queda sin calcular
    despues = {r: sha256(raiz / r) for r in (HECHOS, PRECIOS)}
    vacias = sorted(k for k, x in cifras.items() if x is None)
    cambiadas = [r for r in antes if antes[r] != despues[r]]
    estado = "OK" if not vacias and not cambiadas else "ERROR"
    salida = {"script": SCRIPT, "fecha_datos": j.get("fecha_datos"),
              "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "estado": estado,
              "errores": [f"sin calcular: {k}" for k in vacias] + [f"cambió la tabla {r}" for r in cambiadas],
              "entradas": {r: antes[r] for r in antes} | {EXPLORATORIO: sha256(ruta_j)},
              "cifras": [{"nombre": k, "valor": x} for k, x in cifras.items()]}
    (raiz / SALIDA).write_text(json.dumps(salida, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
    if estado != "OK":
        raise Parada("; ".join(salida["errores"]))
    print(f"OK: {SALIDA}, {len(cifras)} cifras; 2013: {v['dolares']:.2f} dólares, {v['unidades']} unidades")


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
