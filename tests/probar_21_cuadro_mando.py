"""Prueba de las piezas de Python de scripts/21_cuadro_mando.py, con datos pequeños escritos aquí.

No lee ningún dato del caso: monta tablas de juguete con la forma de previsiones_prueba_final.parquet, del lote de los
próximos días y de las dimensiones, y llama a las funciones del script.

Casos:
1. el script existe y se importa sin ejecutar nada (no escribe el cuadro);
2. el error y el exceso por cada 100 vendidas: 10 y 10 vendidas con 12 y 7 previstas fallan 25 y se quedan cortas 5,
   lo mismo que scripts/prevision_recursiva.error_y_sesgo (otro cálculo); sin venta, vacío;
3. la regla que menos falla: con un empate, la primera en el orden de las reglas;
4. el título concluye «falla menos» solo con 10 de 13 pruebas: con 9 de 13 describe, con 10 de 13 concluye;
5. una fila fuera del error (el 25 de diciembre) no cambia el error de su víspera;
6. sumando las combinaciones, dos errores que se compensan dan error cero, y sin sumar no;
7. los filtros: la tienda pone su estado y el departamento su categoría; un valor que no existe se quita;
8. los próximos días: HOBBIES_2 va con la media de los últimos 28 días y las unidades solo llegan a su plazo;
9. una previsión vacía en el lote de los próximos días para; un lote que no es de próximos días, también;
10. la regla que se recomienda sale del JSON: si no es solo HOBBIES_2 con la media de los últimos 28 días, para;
11. la media de los últimos 28 días para los próximos días, de una venta de juguete: la media y redondeada en unidades;
12. el CSV: su nombre con los filtros y la fecha; punto y coma, coma decimal y la selección en la primera línea;
13. una entrada más vieja que su script para, y una más nueva pasa;
14. el buscador de validaciones con su resultado escrito caza una y no encuentra ninguna en el script.

La carpeta tests/tmp_cuadro_piezas/ se crea y se borra siempre. Sale con 0 si todo pasa y con 1 si algo falla.

Uso: python -W error tests/probar_21_cuadro_mando.py
"""

# importlib carga el script y el módulo de las reglas por su ruta sin ejecutar su principal
import importlib.util
# os cambia la fecha de modificación de los ficheros de prueba
import os
# shutil borra la carpeta temporal
import shutil
# sys da el código de salida y la ruta de importación
import sys
# traceback enseña el fallo de una excepción
import traceback
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "21_cuadro_mando.py"
SALIDA = RAIZ / "informes" / "cuadro_mando.html"
TMP = RAIZ / "tests" / "tmp_cuadro_piezas"
REGLAS = ["repetir_semana_anterior", "media_28_dias", "media_mismo_dia_4_semanas"]
ORIGENES = [pd.Timestamp("2015-05-22") + pd.Timedelta(28 * k, "D") for k in range(13)]
FESTIVOS = [{"nombre": "Acción de Gracias", "origen": "2015-11-25"}, {"nombre": "Navidad", "origen": "2015-12-24"},
            {"nombre": "Año Nuevo", "origen": "2015-12-31"}]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso y dice si pasa."""
    print(("PASA  " if condicion else "FALLA ") + nombre + ("" if condicion else f" ({detalle})"))
    if not condicion:
        FALLOS.append(nombre)


def cargar(ruta, nombre):
    """Carga un fichero de Python como módulo, sin ejecutar su principal."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def para(m, funcion, *args):
    """Cierto si la función para con la Parada del script."""
    try:
        funcion(*args)
    except m.Parada:
        return True
    return False


# ── Datos de juguete ──────────────────────────────────────────────────────────
def dimensiones():
    """Dos tiendas de dos estados y dos departamentos de dos categorías."""
    tiendas = pd.DataFrame({"store_id": ["CA_1", "WI_2"], "state_id": ["CA", "WI"]})
    productos = pd.DataFrame({"item_id": ["FOODS_3_001", "HOBBIES_2_001"], "dept_id": ["FOODS_3", "HOBBIES_2"],
                              "cat_id": ["FOODS", "HOBBIES"]})
    return tiendas, productos


def previsiones(gana, compensa=False):
    """Una tabla con la forma de previsiones_prueba_final.parquet: 13 pruebas de 2 días en unidades y en dólares.

    En las `gana` primeras pruebas el modelo falla 1 de cada 10 y las tres reglas 2; en las demás, el modelo 3. Con
    `compensa`, en la primera prueba CA_1 se pasa 2 y WI_2 se queda corta 2 en FOODS_3 (sumadas, se compensan).
    """
    filas = []
    for objetivo in ("unidades", "dolares"):
        for k, origen in enumerate(ORIGENES):
            for tienda in ("CA_1", "WI_2"):
                for dep in ("FOODS_3", "HOBBIES_2"):
                    for h in (1, 2):
                        e = 1.0 if k < gana else 3.0
                        if compensa and k == 0 and dep == "FOODS_3":
                            e = 2.0 if tienda == "CA_1" else -2.0
                        filas.append({"variante": "reentrenado", "prueba": "ordinaria", "objetivo": objetivo,
                                      "origen": origen, "store_id": tienda, "dept_id": dep,
                                      "date": origen + pd.Timedelta(h, "D"), "h": h, "real": 10.0, "modelo": 10.0 + e,
                                      "repetir_semana_anterior": 12.0, "media_28_dias": 12.0,
                                      "media_mismo_dia_4_semanas": 12.0, "suavizado": 12.0, "fuera_del_error": False})
    for f in FESTIVOS:
        origen = pd.Timestamp(f["origen"])
        for tienda in ("CA_1", "WI_2"):
            for dep in ("FOODS_3", "HOBBIES_2"):
                for h in (1, 2):
                    fuera = f["nombre"] == "Navidad" and h == 1
                    filas.append({"variante": "reentrenado", "prueba": "festivo", "objetivo": "unidades",
                                  "origen": origen, "store_id": tienda, "dept_id": dep,
                                  "date": origen + pd.Timedelta(h, "D"), "h": h, "real": 0.0 if fuera else 10.0,
                                  "modelo": 500.0 if fuera else 11.0, "repetir_semana_anterior": 14.0,
                                  "media_28_dias": 13.0, "media_mismo_dia_4_semanas": 15.0, "suavizado": 12.0,
                                  "fuera_del_error": fuera})
    tabla = pd.DataFrame(filas)
    otra = tabla.assign(variante="tal_como_esta", modelo=99.0)
    return pd.concat([tabla, otra], ignore_index=True)


def lote(dias_u=2, dias_d=3, vacia=False, prueba="proximos_dias"):
    """Un lote de próximos días de juguete: unidades a dias_u días y dólares a dias_d desde el 22/05/2016."""
    filas = []
    origen = pd.Timestamp("2016-05-22")
    for objetivo, dias in (("unidades", dias_u), ("dolares", dias_d)):
        for tienda in ("CA_1", "WI_2"):
            for dep in ("FOODS_3", "HOBBIES_2"):
                for h in range(1, dias + 1):
                    filas.append({"objetivo": objetivo, "origen": origen, "store_id": tienda, "dept_id": dep,
                                  "date": origen + pd.Timedelta(h, "D"), "h": h, "prevision": 7.0,
                                  "prevision_sin_redondear": 7.2, "motivo": None, "aviso": None, "prueba": prueba})
    t = pd.DataFrame(filas)
    if vacia:
        t.loc[0, "prevision"] = np.nan
    return t


def regla_proximos(dias_d=3):
    """La media de los últimos 28 días de juguete: 3 unidades y 4,5 dólares al día en cada combinación."""
    filas = []
    origen = pd.Timestamp("2016-05-22")
    for tienda in ("CA_1", "WI_2"):
        for dep in ("FOODS_3", "HOBBIES_2"):
            for h in range(1, dias_d + 1):
                filas.append({"store_id": tienda, "dept_id": dep, "date": origen + pd.Timedelta(h, "D"),
                              "unidades": 3.0, "dolares": 4.5})
    return pd.DataFrame(filas)


RECOMENDADO = {"FOODS_3": "modelo", "HOBBIES_2": "media_28_dias"}


def datos_de(m, gana=9, compensa=False):
    """Los datos del HTML con las tablas de juguete."""
    tiendas, productos = dimensiones()
    return m.preparar_datos(previsiones(gana, compensa), tiendas, productos, lote(), regla_proximos(), FESTIVOS,
                            [f"{o:%Y-%m-%d}" for o in ORIGENES], RECOMENDADO, 10)


# ── Casos ─────────────────────────────────────────────────────────────────────
def probar(m, pr):
    """Los casos 2 a 14."""
    # 2. error y exceso, contra la función del caso
    e, s = m.error_sesgo(np.array([10.0, 10.0]), np.array([12.0, 7.0]))
    e2, s2 = pr.error_y_sesgo([10.0, 10.0], [12.0, 7.0])
    caso("error y exceso: 25 y −5", abs(e - 25) < 1e-12 and abs(s + 5) < 1e-12, (e, s))
    caso("error y exceso: iguales que prevision_recursiva", abs(e - e2) < 1e-12 and abs(s - s2) < 1e-12, (e2, s2))
    caso("error sin venta: vacío", m.error_sesgo(np.array([0.0]), np.array([3.0])) == (None, None))
    # 3. la regla que menos falla, con empate
    caso("regla que menos falla: la menor", m.menor([3.0, 1.0, 2.0]) == 1)
    caso("regla que menos falla: con empate, la primera", m.menor([2.0, 1.0, 1.0]) == 1)
    # 4. el título concluye solo con 10 de 13
    d9, d10 = datos_de(m, 9), datos_de(m, 10)
    r9, r10 = m.calcular(d9, {}), m.calcular(d10, {})
    caso("9 de 13: el modelo gana 9 pruebas en dólares", r9["gana_d"] == 9 and r9["de_d"] == 13, (r9["gana_d"], r9["de_d"]))
    t9, t10 = m.titulos(d9, {}), m.titulos(d10, {})
    for p in ("vision", "pedido", "donde"):
        caso(f"9 de 13: el título de {p} no concluye", not t9[p]["concluye"] and "falla menos" not in t9[p]["texto"],
             t9[p])
        caso(f"10 de 13: el título de {p} concluye", t10[p]["concluye"] and "falla menos" in t10[p]["texto"], t10[p])
    caso("festivos y próximos días: el título nunca concluye",
         not any(t[p]["concluye"] or "falla menos" in t[p]["texto"] for t in (t9, t10) for p in ("festivos", "proximos")))
    # 5. la fila fuera del error no cuenta: la víspera de Navidad falla 10 de cada 100 (11 frente a 10)
    caso("fuera del error: el 25 de diciembre no cuenta", abs(r9["festivos"][1]["modelo"] - 10.0) < 1e-12,
         r9["festivos"][1])
    # 6. sumando se compensan
    dc = datos_de(m, 13, compensa=True)
    sel = m.normalizar(dc, {"departamento": "FOODS_3"})
    rc = m.calcular(dc, sel)
    caso("sumadas, la primera prueba de FOODS_3 se compensa", rc["porprueba_u"][0]["modelo"] > 0 and
         abs(m.error_sumado(dc, "u", m.seleccion(dc, sel), solo_prueba=0)["modelo"]) < 1e-12,
         (rc["porprueba_u"][0], m.error_sumado(dc, "u", m.seleccion(dc, sel), solo_prueba=0)))
    # 7. los filtros
    caso("filtros: la tienda pone su estado", m.normalizar(d9, {"estado": "CA", "tienda": "WI_2"}) ==
         {"estado": "WI", "tienda": "WI_2"}, m.normalizar(d9, {"estado": "CA", "tienda": "WI_2"}))
    caso("filtros: el departamento pone su categoría", m.normalizar(d9, {"departamento": "HOBBIES_2"}) ==
         {"categoria": "HOBBIES", "departamento": "HOBBIES_2"}, m.normalizar(d9, {"departamento": "HOBBIES_2"}))
    caso("filtros: un valor que no existe se quita", m.normalizar(d9, {"tienda": "TX_9", "estado": "XX"}) == {},
         m.normalizar(d9, {"tienda": "TX_9", "estado": "XX"}))
    # 8. los próximos días
    filas = m.filas_proximos(d9, {})
    hob = [x for x in filas if x["departamento"] == "HOBBIES_2"]
    foo = [x for x in filas if x["departamento"] == "FOODS_3"]
    caso("próximos días: HOBBIES_2 con la media de los últimos 28 días",
         all(x["con"] == "media_28_dias" and x["dolares"] == 4.5 for x in hob)
         and all(x["unidades"] in (3.0, None) for x in hob), hob[:2])
    caso("próximos días: el resto con el modelo", all(x["con"] == "modelo" and x["dolares"] == 7.0 for x in foo), foo[:2])
    caso("próximos días: las unidades solo en su plazo", [x["unidades"] is not None for x in foo[:3]] ==
         [True, True, False], [x["unidades"] for x in foo[:3]])
    r = m.calcular(d9, {})
    caso("próximos días: 2 días de unidades y 3 de dólares", r["unidades_10"] == 2 * (7 + 7 + 3 + 3)
         and abs(r["dolares_28"] - 3 * (7 + 7 + 4.5 + 4.5)) < 1e-9, (r["unidades_10"], r["dolares_28"]))
    # 9. el lote de los próximos días
    tiendas, productos = dimensiones()
    origenes = [f"{o:%Y-%m-%d}" for o in ORIGENES]
    caso("lote con una previsión vacía: para", para(m, m.preparar_datos, previsiones(9), tiendas, productos,
                                                    lote(vacia=True), regla_proximos(), FESTIVOS, origenes,
                                                    RECOMENDADO, 10))
    caso("lote que no es de próximos días: para", para(m, m.preparar_datos, previsiones(9), tiendas, productos,
                                                      lote(prueba="ordinaria"), regla_proximos(), FESTIVOS, origenes,
                                                      RECOMENDADO, 10))
    # 10. la regla que se recomienda, del JSON
    def json_con(hob_u, hob_d):
        """Una copia de juguete de prueba_final.json con la recomendación de HOBBIES_2 que se dice."""
        rec = {"unidades": hob_u, "dolares": hob_d}
        return {"reentrenado": {o: {"recomendacion_por_departamento": [
            {"departamento": "FOODS_3", "se_recomienda": "el modelo", "regla_que_menos_falla": "media_28_dias"},
            {"departamento": "HOBBIES_2", "se_recomienda": v, "regla_que_menos_falla": "media_28_dias"}]}
            for o, v in rec.items()}}
    regla = "la media de los últimos 28 días"
    caso("recomendado: HOBBIES_2 con la media de los últimos 28 días",
         m.recomendado_de(json_con(regla, regla)) == RECOMENDADO, m.recomendado_de(json_con(regla, regla)))
    caso("recomendado: si en dólares es el modelo, para", para(m, m.recomendado_de, json_con(regla, "el modelo")))
    # 11. la media de los últimos 28 días para los próximos días
    fechas = pd.date_range(end="2016-05-22", periods=40, freq="D")
    hechos = pd.DataFrame({"store_id": "CA_1", "dept_id": "HOBBIES_2", "date": fechas,
                           "unidades": [100.0] * 12 + [2.0, 3.0] * 14, "dolares": [1.0] * 12 + [1.25] * 28})
    rp = m.reglas_para_proximos(hechos, pd.Timestamp("2016-05-22"), {"unidades": 2, "dolares": 3})
    caso("media de los últimos 28 días: 2,5 al día redondeado a 3 unidades; 1,25 dólares",
         list(rp["unidades"].dropna()) == [3.0, 3.0] and list(rp["dolares"]) == [1.25, 1.25, 1.25], rp)
    # 12. el CSV
    f = m.normalizar(d9, {"tienda": "WI_2", "departamento": "FOODS_3"})
    nombre = m.nombre_csv(d9, f)
    caso("CSV: nombre con los filtros y la fecha", nombre == "proximos_dias_wi_wi_2_foods_foods_3_datos-2016-05-22.csv",
         nombre)
    texto = m.texto_csv(d9, f)
    lineas = texto.split("\r\n")
    caso("CSV: la selección en la primera línea", lineas[0] == "Próximos días · Wisconsin · WI_2 · alimentación · "
         "FOODS_3 · previsión hecha con la venta hasta el 22/05/2016", lineas[0])
    caso("CSV: cabecera de lo general a lo concreto", lineas[1] == "Estado;Tienda;Categoría;Departamento;Día;"
         "Unidades previstas;Dólares previstos;Se prevé con", lineas[1])
    caso("CSV: punto y coma y coma decimal", lineas[2] == "Wisconsin;WI_2;alimentación;FOODS_3;23/05/2016;7;7,00;"
         "el modelo" and lineas[4] == "Wisconsin;WI_2;alimentación;FOODS_3;25/05/2016;;7,00;el modelo", lineas[2:5])
    (TMP / nombre).write_text(texto, encoding="utf-8-sig", newline="")
    leido = (TMP / nombre).read_text(encoding="utf-8-sig")
    caso("CSV: se escribe y se lee igual", leido == texto.replace("\r\n", "\n") or leido == texto)
    # 13. el orden
    viejo, script = TMP / "entrada.json", TMP / "script.py"
    viejo.write_text("{}", encoding="utf-8")
    script.write_text("#", encoding="utf-8")
    os.utime(viejo, (1_000_000, 1_000_000))
    caso("orden: una entrada más vieja que su script para", para(m, m.comprobar_orden, [(viejo, script)]))
    os.utime(viejo, None)
    os.utime(script, (1_000_000, 1_000_000))
    caso("orden: una entrada más nueva pasa", m.comprobar_orden([(viejo, script)]) is True)
    # 14. validaciones escritas
    caso("buscador: caza una validación escrita", m.buscar_resultados_escritos('v["cifras_iguales_al_json"] = True'))
    caso("buscador: el script no tiene ninguna", m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8")) == [],
         m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8")))


def main():
    """Lanza los casos."""
    print("intérprete:", sys.executable)
    if not SCRIPT.is_file():
        caso("existe el script scripts/21_cuadro_mando.py", False)
        print(f"{len(FALLOS)} FALLA")
        return 1
    antes = SALIDA.stat().st_mtime if SALIDA.exists() else None
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True)
    try:
        m = cargar(SCRIPT, "cuadro_mando_69")
        despues = SALIDA.stat().st_mtime if SALIDA.exists() else None
        caso("importar el script no escribe el cuadro", antes == despues, (antes, despues))
        pr = cargar(RAIZ / "scripts" / "prevision_recursiva.py", "prevision_recursiva_prueba") \
            if "prevision_recursiva" not in sys.modules else sys.modules["prevision_recursiva"]
        probar(m, pr)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        traceback.print_exc()
        caso("la prueba se ejecuta sin excepción", False, f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
