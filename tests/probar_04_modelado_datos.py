"""Prueba de scripts/04_modelado_datos.py.

Sin argumentos usa solo datos pequeños escritos aquí; lo que necesita escribir va a tests/tmp_modelado/, que se crea y se
borra. Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla.

Con --datos compara además informes/modelado-datos.json con la clave "modelado" de tests/cifras_de_referencia.json
(programacion-del-caso §6) y hace una segunda vía sobre los Parquet de data/processed/:
  - vía 1: el script cuenta con numpy sobre la venta ancha, busca el precio de cada día por índice de semana y suma en
    céntimos enteros;
  - vía 2: esta prueba pasa la venta a filas con pandas (melt), une la semana del calendario y el precio con merge y
    validate="m:1", y suma con Decimal. No guarda nada.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import re
import shutil
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "04_modelado_datos.py"
TMP = RAIZ / "tests" / "tmp_modelado"
FALLOS = []

APARTADOS = ["Fuente", "Resumen", "Tablas y grano", "Relaciones", "Calendario", "Plan de cruces",
             "Registro de exclusiones", "Precio medio del departamento", "Comprobaciones", "Decisiones pendientes",
             "Datos personales", "Límites"]


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script sin ejecutar su __main__ (su nombre empieza por cifra, así que va por importlib)."""
    spec = importlib.util.spec_from_file_location("modelado_datos", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ── 2. Casos con datos pequeños ────────────────────────────────────────────────
def probar_clave(m):
    """La clave del grano: única pasa; una clave repetida TIENE que salir con sus filas repetidas."""
    df = pd.DataFrame({"item_id": ["A", "A", "B"], "store_id": ["T1", "T2", "T1"], "w": [1, 1, 1]})
    r = m.clave_del_grano(df, ["item_id", "store_id"])
    comprobar(r == {"clave_unica": True, "filas_repetidas": 0, "claves_repetidas": 0}, "(A,T1), (A,T2), (B,T1): clave única")
    df = pd.DataFrame({"item_id": ["A", "A", "A", "B"], "store_id": ["T1", "T1", "T1", "T1"], "w": [1, 2, 3, 1]})
    r = m.clave_del_grano(df, ["item_id", "store_id"])
    comprobar(r["clave_unica"] is False and r["filas_repetidas"] == 3 and r["claves_repetidas"] == 1,
              "(A,T1) tres veces: clave repetida, 3 filas y 1 clave (el caso que tiene que fallar)")
    r = m.clave_del_grano(df, ["item_id", "store_id", "w"])
    comprobar(r["clave_unica"] is True, "con la semana en la clave, las mismas filas son únicas")


def probar_calendario(m):
    """Días seguidos sin hueco; un día que falta se detecta."""
    fechas = pd.Series(pd.to_datetime(["2011-01-29", "2011-01-30", "2011-01-31"], format="%Y-%m-%d"))
    r = m.dias_seguidos(fechas)
    comprobar(r["desde"] == "2011-01-29" and r["hasta"] == "2011-01-31" and r["dias_que_faltan"] == 0, "tres días seguidos")
    fechas = pd.Series(pd.to_datetime(["2011-01-29", "2011-01-31", "2011-02-03"], format="%Y-%m-%d"))
    comprobar(m.dias_seguidos(fechas)["dias_que_faltan"] == 3, "faltan el 30/01, el 01/02 y el 02/02 (el caso que falla)")


def probar_semanas(m):
    """Días por semana y orden de las semanas: el paso de año salta de código y la semana anterior se toma por orden."""
    cal = pd.DataFrame({"date": pd.date_range("2011-12-24", periods=21, freq="D"),
                        "wm_yr_wk": [11148] * 7 + [11201] * 7 + [11202] * 7})
    r = m.semanas(cal)
    comprobar(r["dias_por_semana"] == {11148: 7, 11201: 7, 11202: 7} and r["semanas_incompletas"] == {},
              "tres semanas de siete días")
    comprobar(r["anterior"] == {11201: 11148, 11202: 11201} and r["saltos_de_codigo"] == [[11148, 11201]],
              "la anterior de 11201 es 11148, no 11200 (el caso que falla si se resta 1)")
    comprobar(r["orden_por_codigo_igual_que_por_fecha"] is True, "el orden por código es el de las fechas")
    corta = cal.iloc[:-1]
    comprobar(m.semanas(corta)["semanas_incompletas"] == {11202: 6}, "una semana con seis días se detecta")


def probar_parciales(m):
    """Meses y semanas que no tienen todos sus días dentro de un periodo."""
    cal = pd.DataFrame({"date": pd.date_range("2014-05-10", "2014-06-06", freq="D")})
    cal["wm_yr_wk"] = [11415] * 7 + [11416] * 7 + [11417] * 7 + [11418] * 7
    periodos = {"uno": ("2014-05-10", "2014-05-22"), "dos": ("2014-05-23", "2014-06-06")}
    r = m.parciales(cal, periodos)
    comprobar(r["uno"]["meses_parciales"] == ["2014-05"] and r["uno"]["semanas_parciales"] == [11416],
              "en el primer periodo, mayo y la semana 11416 quedan partidos")
    comprobar(r["dos"]["meses_parciales"] == ["2014-05", "2014-06"] and r["dos"]["semanas_parciales"] == [11416],
              "en el segundo, mayo, junio y la 11416; la 11417 y la 11418 están enteras")


def probar_jerarquia(m):
    """Cada producto con un departamento y una categoría; cada tienda con un estado; productos por departamento."""
    v = pd.DataFrame({"item_id": ["F1", "F2", "H1", "F1", "F2", "H1"], "dept_id": ["F", "F", "H", "F", "F", "H"],
                      "cat_id": ["FO", "FO", "HO", "FO", "FO", "HO"], "store_id": ["A", "A", "A", "B", "B", "B"],
                      "state_id": ["X", "X", "X", "Y", "Y", "Y"]})
    r = m.jerarquia(v)
    comprobar(r["productos_con_mas_de_un_departamento"] == 0 and r["productos_con_mas_de_una_categoria"] == 0
              and r["departamentos_con_mas_de_una_categoria"] == 0 and r["tiendas_con_mas_de_un_estado"] == 0,
              "una jerarquía limpia no da ningún fallo")
    comprobar(r["productos_por_departamento_en_cada_tienda"] == {"A": {"F": 2, "H": 1}, "B": {"F": 2, "H": 1}}
              and r["series"] == 4, "dos productos de F y uno de H en cada tienda; 4 series")
    v.loc[3, "dept_id"] = "H"
    v.loc[4, "state_id"] = "Z"
    r = m.jerarquia(v)
    comprobar(r["productos_con_mas_de_un_departamento"] == 1 and r["tiendas_con_mas_de_un_estado"] == 1,
              "un producto en dos departamentos y una tienda en dos estados se detectan (el caso que falla)")


def probar_dolares(m):
    """Unidades por el precio de su semana, en céntimos enteros; un día con venta y sin precio se cuenta."""
    U = np.array([[1, 0, 2, 0], [0, 0, 0, 3]], dtype=np.int64)
    P = np.array([[199, 250], [np.nan, 100]])           # céntimos por producto-tienda y semana
    semana_de_dia = np.array([0, 0, 1, 1])
    r = m.dolares(U, P, semana_de_dia)
    comprobar(r["centimos"] == 1 * 199 + 2 * 250 + 3 * 100 and r["dias_sin_precio"] == 2
              and r["dias_con_venta_y_sin_precio"] == 0, "999 céntimos; los dos días de la semana sin precio no venden")
    U[1, 1] = 4
    r = m.dolares(U, P, semana_de_dia)
    comprobar(r["dias_con_venta_y_sin_precio"] == 1, "un día con venta y sin precio se cuenta (el caso que tiene que saltar)")
    comprobar(m.a_centimos(pd.Series([0.01, 2.97, 34.18, 0.285])) is None,
              "un precio con más de dos decimales no pasa a céntimos")
    comprobar(m.dolares_redondeados(123456789) == 1234567.89, "céntimos enteros a dólares sin pérdida")


def probar_precio_medio(m):
    """Media simple y ponderada por unidades del departamento en una semana, calculadas a mano."""
    precios = pd.DataFrame({"store_id": ["A", "A", "A"], "dept_id": ["F", "F", "F"], "item_id": ["1", "2", "3"],
                            "wm_yr_wk": [1, 1, 1], "sell_price": [1.0, 3.0, 8.0], "unidades": [3, 1, 0]})
    r = m.precio_medio_departamento(precios)
    fila = r["tabla"].iloc[0]
    comprobar(abs(fila["simple"] - 4.0) < 1e-12 and abs(fila["ponderada"] - 1.5) < 1e-12,
              "simple (1+3+8)/3 = 4; ponderada (3·1+1·3)/4 = 1,5")
    comprobar(abs(r["resumen"]["diferencia_relativa_media_pct"] - 62.5) < 1e-9, "la diferencia relativa sin signo es 62,5 %")
    precios["unidades"] = 0
    r = m.precio_medio_departamento(precios)
    comprobar(r["resumen"]["sin_ponderada"] == 1 and r["resumen"]["comparables"] == 0,
              "sin unidades en la semana la ponderada no existe y no se compara")


def probar_exclusiones(m):
    """El 25 de diciembre por periodo y el cierre de una tienda fuera del 25 de diciembre."""
    fechas = np.array(["2011-12-24", "2011-12-25", "2011-12-26", "2012-12-25"])
    # tienda A: dos series; tienda B: una serie
    S = np.array([[3, 0, 0, 1], [2, 0, 0, 5], [4, 1, 6, 0]])
    tiendas = np.array(["A", "A", "B"])
    periodos = {"p1": ("2011-12-24", "2011-12-26"), "p2": ("2012-12-25", "2012-12-25")}
    r = m.dias_fuera_del_error(S, tiendas, fechas, periodos)
    comprobar(r["25_diciembre"] == {"p1": 3, "p2": 3}, "el 25 de diciembre: 3 días de serie en cada periodo")
    comprobar(r["cierres_fuera_del_25"] == [{"tienda": "A", "fecha": "2011-12-26", "periodo": "p1", "dias_serie": 2}],
              "A entera a cero el 26/12 es un cierre fuera del 25; B a cero el 25/12 no lo es")


def probar_aprobacion(m):
    """La aprobación solo con la línea fija; cualquier otra forma deja aprobado en false."""
    TMP.mkdir(parents=True, exist_ok=True)
    ruta = TMP / "modelo-datos.md"
    base = "# Modelo\n\n## 9. Decisiones de modelado\n\n- una decisión\n\n## 10. Observaciones y pendientes\n"
    ruta.write_text(base, encoding="utf-8")
    comprobar(m.leer_aprobacion(ruta) == {"aprobado": False, "fecha": None, "quien": None}, "sin la línea: no aprobado")
    ruta.write_text(base.replace("- una decisión\n", "- una decisión\n\nAprobado: sí · el responsable del caso · 2026-11-25\n"), encoding="utf-8")
    comprobar(m.leer_aprobacion(ruta) == {"aprobado": True, "fecha": "2026-11-25", "quien": "el responsable del caso"}, "con la línea: aprobado")
    ruta.write_text(base.replace("- una decisión\n", "- una decisión\n\nAprobado: pendiente · el responsable del caso\n"), encoding="utf-8")
    comprobar(m.leer_aprobacion(ruta)["aprobado"] is False, "«Aprobado: pendiente» no aprueba (el caso que tiene que fallar)")
    ruta.write_text(base + "\nAprobado: sí · el responsable del caso · 2026-11-25\n", encoding="utf-8")
    comprobar(m.leer_aprobacion(ruta)["aprobado"] is False, "la línea fuera de «Decisiones de modelado» no aprueba")
    comprobar(m.estado_y_riesgo({"aprobado": False}, [])[0] == "PARADO", "sin aprobar: PARADO")
    comprobar(m.estado_y_riesgo({"aprobado": True}, [])[0] == "OK", "aprobado y sin contradicciones: OK")
    comprobar(m.estado_y_riesgo({"aprobado": True}, [{"que": "x"}]) == ("PARADO", "alto"),
              "aprobado pero con una contradicción con el diseño: PARADO y riesgo alto (el diseño se revisa)")


def calendario_pequeno():
    """Cinco semanas, del sábado 28/01/2012 al viernes 02/03/2012, con un salto de código tras la primera."""
    fechas = pd.date_range("2012-01-28", "2012-03-02", freq="D")
    semana = np.repeat([11148, 11201, 11202, 11203, 11204], 7)
    return pd.DataFrame({
        "date": fechas, "wm_yr_wk": semana, "weekday": fechas.day_name(), "wday": (fechas.dayofweek + 2) % 7 + 1,
        "month": fechas.month, "year": fechas.year, "d": [f"d_{i}" for i in range(1, len(fechas) + 1)],
        "event_name_1": None, "event_type_1": None, "event_name_2": None, "event_type_2": None,
        "snap_ca": 0, "snap_tx": 0, "snap_wi": 0})


def probar_construir_calendario(m):
    """El Calendario: semana anterior por orden, periodo de cada día y marcas de mes y semana parciales."""
    if not hasattr(m, "construir_calendario") or not hasattr(m, "validar_calendario"):
        comprobar(False, "el script tiene construir_calendario y validar_calendario")
        return
    cal = calendario_pequeno()
    periodos = {"p1": ("2012-01-28", "2012-02-29"), "p2": ("2012-03-01", "2012-03-01")}
    # Las filas llegan desordenadas: el resultado no puede depender del orden (error 7)
    out = m.construir_calendario(cal.sample(frac=1, random_state=69), periodos)
    comprobar(list(out.columns) == m.COLUMNAS_CALENDARIO, "las columnas del Calendario son las del diseño, en su orden")
    comprobar(list(out["date"]) == list(cal["date"]), "las filas salen ordenadas por fecha")
    ant = out.groupby("wm_yr_wk")["wm_yr_wk_anterior"].first()
    comprobar(pd.isna(ant[11148]) and ant[11201] == 11148 and ant[11202] == 11201 and ant[11204] == 11203,
              "la anterior de 11201 es 11148, no 11200; la primera semana no tiene anterior (el caso que falla si se resta 1)")
    comprobar(out["periodo"].value_counts().to_dict() == {"p1": 33, "p2": 1, "sin_periodo": 1},
              "33 días en p1, 1 en p2 y el 02/03 sin periodo")
    mes = out["date"].dt.strftime("%Y-%m")
    comprobar(out.loc[mes == "2012-01", "mes_parcial"].all() and not out.loc[mes == "2012-02", "mes_parcial"].any()
              and out.loc[mes == "2012-03", "mes_parcial"].all(),
              "enero y marzo quedan partidos; febrero entero en p1 no (el caso que distingue)")
    ult = out["wm_yr_wk"] == 11204
    comprobar(out.loc[ult, "semana_parcial"].all() and not out.loc[~ult, "semana_parcial"].any(),
              "solo la semana 11204, repartida en tres periodos, queda partida")
    con_resto = dict(periodos) | {"sin_periodo": ("2012-03-02", "2012-03-02")}
    par = m.parciales(cal, con_resto)
    comprobar(m.validar_calendario(out, cal, par) == [], "un Calendario bien construido pasa la validación")
    sin_un_dia = m.construir_calendario(cal.drop(index=10), periodos)
    comprobar(len(m.validar_calendario(sin_un_dia, cal, par)) > 0,
              "un Calendario con un día de menos no pasa la validación (el caso que tiene que fallar)")
    cambiado = out.copy()
    cambiado.loc[3, "snap_ca"] = 1
    comprobar(len(m.validar_calendario(cambiado, cal, par)) > 0,
              "una columna copiada que cambia no pasa la validación (el caso que tiene que fallar)")


def probar_configuracion(m):
    """El bloque de configuración: cada cardinalidad con su procedencia, que nunca son solo los datos; el plan en orden."""
    for r in m.RELACIONES:
        comprobar(r["procedencia"] and "datos" not in r["procedencia"].split(";")[0].lower(),
                  f"la relación {r['desde']} → {r['hacia']} tiene procedencia que no son los datos")
    ordenes = [c["orden"] for c in m.PLAN_CRUCES]
    comprobar(ordenes == list(range(1, len(ordenes) + 1)), "el plan de cruces va numerado en orden")
    comprobar(all(c["tipo_cruce"] == "left" and c["cardinalidad"] == "N:1" for c in m.PLAN_CRUCES),
              "todos los cruces, por la izquierda y muchos a uno")
    comprobar(all("unidades" in c["magnitudes_control"] for c in m.PLAN_CRUCES if c["partida"] != "precios"),
              "cada cruce desde la venta o las series controla las unidades")
    # El precio medio del departamento quedó fijado como media simple (planteamientos; el responsable del caso, 24/11/2026)
    cruce7 = next(c for c in m.PLAN_CRUCES if c["se_une"] == "precio medio del departamento por semana")
    medida = json.dumps(cruce7["agregar_antes"], ensure_ascii=False)
    comprobar("media simple" in medida and "por fijar" not in medida and "ponderada" not in medida,
              "el cruce 7 dice media simple, sin «por fijar» ni la ponderada (el caso que falla con el plan de antes)")
    # Solo cuentan los productos con precio desde cuatro semanas antes (reglas, apartado 5; el responsable del caso, 24/11/2026)
    comprobar("cuatro semanas antes" in medida,
              "el cruce 7 dice que solo cuentan los productos con precio cuatro semanas antes (falla con el plan de antes)")
    if not hasattr(m, "pendientes_del_diseno"):
        comprobar(False, "las decisiones pendientes salen de pendientes_del_diseno")
        return
    sin_aprobar = [p["id"] for p in m.pendientes_del_diseno({"aprobado": False})]
    aprobado = [p["id"] for p in m.pendientes_del_diseno({"aprobado": True})]
    comprobar("precio_medio_del_departamento" not in sin_aprobar + aprobado,
              "la elección del precio medio ya no es una decisión pendiente")
    comprobar("aprobacion_del_diseno" in sin_aprobar and "aprobacion_del_diseno" not in aprobado,
              "la aprobación sale como pendiente sin aprobar y deja de salir aprobado (el caso que distingue)")


def probar_salidas(m):
    """El JSON sale sin NaN y el Markdown tiene sus apartados en su orden."""
    limpio = m.a_json_limpio({"x": float("nan"), "y": [1.5, float("inf")], "z": np.int64(2)})
    comprobar(limpio["x"] is None and limpio["y"][1] is None and limpio["z"] == 2, "NaN e infinito pasan a null")
    texto = m.generar_md(m.resultado_minimo_de_prueba())
    comprobar(re.findall(r"^## (.+)$", texto, flags=re.M) == APARTADOS, "el informe de prueba tiene sus apartados en orden")
    comprobar(", y " not in texto, "el informe de prueba no une dos partes con «, y»")


def probar_sin_veredictos_escritos():
    """Error 24: ninguna comprobación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](clave_unica|coincide|mismo_tipo|aprobado|completo|ok|pasa|primer_periodo_completo|"
                         r"ultimo_periodo_completo)[\"']\s*:\s*(True|False)", codigo)
    comprobar(puestos == [], f"el script no escribe ninguna comprobación con su resultado puesto ({puestos})")


# ── 3. Con los datos reales (solo con --datos) ─────────────────────────────────
def cifras_de_referencia(d):
    """Las cifras de control de la petición (clave "modelado" de tests/cifras_de_referencia.json) salen iguales."""
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    if "modelado" not in ref:
        comprobar(False, "tests/cifras_de_referencia.json tiene la clave modelado")
        return
    medido = d["cifras_de_control"]
    for clave, valor in ref["modelado"]["cifras"].items():
        comprobar(medido.get(clave) == valor, f"cifra de control {clave}: esperado {valor} · JSON {medido.get(clave)}")
    huellas = {e["ruta"].split("/")[-1]: e["sha256"] for e in d["entradas"]}
    comprobar(huellas == ref["modelado"]["huellas"], "las huellas de entrada son las de la petición")
    comprobar({k.split("/")[-1]: v for k, v in d["huellas_despues"].items()} == ref["modelado"]["huellas"],
              "las huellas de data/processed/ después del script son las de la petición")


def segunda_via(d):
    """Rehace con pandas en filas (melt y merge validado) las unidades, los días sin precio y los dólares."""
    proc = RAIZ / "data" / "processed"
    c = d["cifras_de_control"]
    venta = pd.read_parquet(proc / "venta_corregido.parquet")
    dias = [x for x in venta.columns if x.startswith("d_")]
    larga = venta.melt(id_vars=["item_id", "store_id"], value_vars=dias, var_name="d", value_name="unidades")
    cal = pd.read_parquet(proc / "calendario_corregido.parquet", columns=["d", "wm_yr_wk"])
    larga = larga.merge(cal, on="d", how="left", validate="m:1")
    precios = pd.read_parquet(proc / "precios_corregido.parquet")
    larga = larga.merge(precios, on=["store_id", "item_id", "wm_yr_wk"], how="left", validate="m:1", indicator=True)
    sin_precio = larga["_merge"] == "left_only"
    con_precio = larga.loc[~sin_precio]
    centimos = sum(int(u) * int(Decimal(str(p)) * 100) for u, p in
                   con_precio.loc[con_precio["unidades"] > 0, ["unidades", "sell_price"]].itertuples(index=False))
    dolares = float((Decimal(centimos) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    medido = {"filas": len(larga), "unidades": int(larga["unidades"].sum()), "dias_sin_precio": int(sin_precio.sum()),
              "dias_con_venta_y_sin_precio": int((sin_precio & (larga["unidades"] > 0)).sum()), "dolares": dolares}
    print("segunda vía (melt y merge):", medido)
    comprobar(medido["filas"] == 7875000, "la venta en filas son 7.875.000")
    comprobar(medido["unidades"] == c["unidades"], "las unidades coinciden por las dos vías")
    comprobar(medido["dias_sin_precio"] == c["dias_sin_precio"], "los días sin precio coinciden por las dos vías")
    comprobar(medido["dias_con_venta_y_sin_precio"] == c["dias_con_venta_y_sin_precio"],
              "los días con venta y sin precio coinciden por las dos vías")
    comprobar(medido["dolares"] == c["dolares"], "los dólares coinciden al céntimo por las dos vías")


def informe(d, m):
    """El informe real: sus apartados en orden, sin «, y», y su aprobación y estado iguales a lo que dice hoy el diseño.

    No fija si está aprobado, porque eso cambia cuando el responsable del caso aprueba (error 31): lo lee del diseño vivo y exige que el
    JSON diga lo mismo. Las reglas de la línea de aprobación se prueban sobre copias en probar_aprobacion.
    """
    texto = (RAIZ / "informes" / "modelado-datos.md").read_text(encoding="utf-8")
    comprobar(re.findall(r"^## (.+)$", texto, flags=re.M) == APARTADOS, "el informe real tiene sus apartados en orden")
    comprobar(", y " not in texto, "el informe real no une dos partes con «, y»")
    esperada = m.leer_aprobacion(m.DISENO)
    estado_esperado = m.estado_y_riesgo(esperada, d["contradicciones"])[0]
    comprobar(d["aprobado"] == esperada and d["resultado"]["estado"] == estado_esperado,
              f"el JSON dice lo mismo que el diseño: aprobado {esperada['aprobado']}, estado {estado_esperado}")
    comprobar(d["fecha_datos"] == "2015-05-22", "fecha_datos 2015-05-22")


def calendario_real(d):
    """El Calendario guardado, rehecho por otra vía desde data/raw/calendar.csv con el módulo csv, sin pandas.

    Vía 1: el script, con pandas sobre calendario_corregido.parquet. Vía 2: esta prueba lee el CSV en bruto, ordena
    por fecha, toma la semana anterior por orden de aparición y cuenta los días de cada mes y semana dentro del periodo.
    """
    import calendar as cal_std
    import csv
    ruta = RAIZ / "data" / "processed" / "calendario.parquet"
    if not d["aprobado"]["aprobado"]:
        comprobar(d["calendario"]["fichero"] is None, "sin aprobar, el JSON no apunta a ningún Calendario")
        return
    comprobar(ruta.exists() and d["calendario"]["fichero"] == "data/processed/calendario.parquet",
              "con el diseño aprobado, el Calendario está en data/processed/calendario.parquet")
    if not ruta.exists():
        return
    guardado = pd.read_parquet(ruta)
    with open(RAIZ / "data" / "raw" / "calendar.csv", encoding="utf-8", newline="") as f:
        filas = sorted(csv.DictReader(f), key=lambda x: x["date"])
    periodos = {"construccion": ("2011-01-29", "2014-05-22"), "validacion": ("2014-05-23", "2015-05-22")}
    orden, anterior = [], {}
    for x in filas:
        w = int(x["wm_yr_wk"])
        if not orden or orden[-1] != w:
            anterior[w] = orden[-1] if orden else None
            orden.append(w)
    for x in filas:
        x["periodo"] = next((n for n, (a, b) in periodos.items() if a <= x["date"] <= b), "sin_periodo")
    por_mes, por_semana = {}, {}
    for x in filas:
        por_mes[(x["periodo"], x["date"][:7])] = por_mes.get((x["periodo"], x["date"][:7]), 0) + 1
        por_semana[(x["periodo"], x["wm_yr_wk"])] = por_semana.get((x["periodo"], x["wm_yr_wk"]), 0) + 1
    via2 = [(x["d"], x["date"], int(x["wm_yr_wk"]), anterior[int(x["wm_yr_wk"])], x["periodo"],
             por_mes[(x["periodo"], x["date"][:7])] != cal_std.monthrange(int(x["date"][:4]), int(x["date"][5:7]))[1],
             por_semana[(x["periodo"], x["wm_yr_wk"])] != 7) for x in filas]
    via1 = [(r.d, r.date.strftime("%Y-%m-%d"), int(r.wm_yr_wk), None if pd.isna(r.wm_yr_wk_anterior)
             else int(r.wm_yr_wk_anterior), r.periodo, bool(r.mes_parcial), bool(r.semana_parcial))
            for r in guardado.itertuples(index=False)]
    distintas = sum(a != b for a, b in zip(via1, via2))
    print(f"Calendario: {len(via1)} filas en el Parquet y {len(via2)} en el CSV en bruto; {distintas} distintas")
    comprobar(len(via1) == len(via2) == 1969 and distintas == 0,
              "el Calendario coincide fila a fila con el rehecho desde el CSV en bruto (d, fecha, semana, anterior, "
              "periodo y marcas)")
    cuenta = guardado["periodo"].value_counts().to_dict()
    comprobar(cuenta == {"construccion": 1210, "validacion": 365, "sin_periodo": 394},
              f"1.210 días de construcción, 365 de validación y 394 sin periodo ({cuenta})")
    comprobar(d["calendario"].get("sha256") == huella_fichero(ruta), "la huella del JSON es la del Parquet guardado")


def huella_fichero(ruta):
    """SHA-256 de un fichero."""
    import hashlib
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_clave(modulo)
            probar_calendario(modulo)
            probar_semanas(modulo)
            probar_parciales(modulo)
            probar_jerarquia(modulo)
            probar_dolares(modulo)
            probar_precio_medio(modulo)
            probar_exclusiones(modulo)
            probar_aprobacion(modulo)
            probar_construir_calendario(modulo)
            probar_configuracion(modulo)
            probar_salidas(modulo)
            probar_sin_veredictos_escritos()
            if "--datos" in sys.argv:
                datos = json.loads((RAIZ / "informes" / "modelado-datos.json").read_text(encoding="utf-8"))
                cifras_de_referencia(datos)
                segunda_via(datos)
                informe(datos, modulo)
                calendario_real(datos)
    except Exception as error:  # un fallo del script es un fallo de la prueba, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_modelado borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
