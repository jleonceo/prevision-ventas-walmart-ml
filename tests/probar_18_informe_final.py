"""Prueba de scripts/18_informe_final.py: el informe final del caso 69.

No lee ningún informe ni documento vivo del caso. Escribe JSON pequeños, con la forma de los de informes/, en
tests/tmp_informe_final/, los lee con el script y borra la carpeta al acabar. Desde la versión 4 del texto
las cifras principales salen de prueba_final.json (variante reentrenado, el modelo en uso; tal_como_esta, el del año
de comprobación); de validacion.json quedan la página 4 y el exceso del año de comprobación. Comprueba:
1. que el script existe y se importa sin ejecutar nada;
2. el control que no debe disparar: con JSON buenos monta quince páginas antes del anexo, en el orden del texto, con
   las cifras leídas y las dos proporciones calculadas (la ventaja entre el error de la regla);
3. que para con un JSON de otra fecha_datos o con una prueba final que no acaba el 22/05/2016;
4. que para si HOBBIES_2 deja de ser el único departamento con regla, en cualquiera de los dos objetivos;
5. que para si una frase del texto aprobado ha cambiado (y no para con la frase igual);
6. que para si en el texto hay una cifra escrita a mano, que no se leyó de ningún JSON (y no con una leída);
7. que para con un término que prohíbe la hoja de vocabulario o con un nombre interno (y no con «mejoras supuestas»);
8. que para con un título que lleva un código suelto (y no con el código y su nombre);
9. que para con más de 15 páginas sin el anexo;
10. que con JSON buenos salen las frases de la versión 4, con sus cifras leídas y las páginas que citan;
11. que para si el modelo en uso no gana en unidades o en dólares (pruebas o intervalo);
12. que para si el modelo del año de comprobación no se queda en unidades a una prueba de las que pide la regla, o si
    en dólares no gana;
13. que para si en dólares la tienda que no gana no es solo CA_4 o si su diferencia no es un empate que se ve;
14. que para si los supuestos sin fuente del business case no son 4;
15. que para si los años de cada festivo no salen enteros;
16. que lee particion.json y para si trae otra fecha_datos o su año de comprobación no es el de la validación;
17. que para si el modelo en uso no falla menos que la regla en un estado o una categoría;
18. que para si en el año de comprobación otra previsión se pasa más que el modelo;
19. que para si el exceso del modelo en uso llega a 0,5 en valor absoluto, en cualquiera de los dos objetivos;
20. que para si en unidades la regla no falla menos justo en CA_2 y CA_4;
21. que para si el modelo no falla menos que la regla en las tres vísperas de festivo, a 10 días y una vez cada una;
22. que para si la cadena no se queda corta en dólares;
23. que para si el escenario alto no es el más favorable;
24. que para si el modelo en uso de la configuración no es el reentrenado de la prueba final, ajustado hasta la fecha
    de los datos;
25. que para si WI_2 no es la tienda donde más gana en dólares;
26. que para si las páginas que cita el texto no son las del panel (y no para con las del informe);
27. que para si en unidades el modelo en uso no se pasa lo mismo que la regla, a un decimal;
28. que para si el exceso del modelo en uso no bajó frente al del año de comprobación;
29. que para si la regla del veredicto y la media del mismo día no se leen igual a un decimal (y no para si se leen
    igual aunque no sean la misma cifra, como en el último año en unidades);
30. que con JSON buenos salen las frases de la versión 5 (propuesta_informe_final_v5.md §2) y ya no las de la 4,
    que ninguna página pasa de 650 px y que el resumen no pasa de 150 palabras;
31. que para si Wisconsin no es el estado con más diferencia en unidades o California el de menos;
32. que para si la regla que menos falla por tienda no es la media del mismo día en todas salvo WI_2 en unidades;
33. que para si la de los otros cuatro departamentos no es la media del mismo día en todos salvo FOODS_1 en dólares;
34. que para si en alguno de los otros cuatro departamentos el modelo no falla menos;
35. que para si HOBBIES_2, a un decimal, se lee igual en el modelo y en la regla (tabla de la página 10);
36. que para si el modelo en uso no le gana al suavizado en las pruebas que pide la regla;
37. que para si el modelo del año de comprobación no falló más que el modelo en uso (las barras son del de uso);
38. que las quince páginas del panel se comprueban (las 3 a 15 que cita el resumen, cambio 5);
39. que salen las frases de la tercera pasada (§2 bis: 4b, 7b, 15b, 20b y del 29 al 38) y ya no las que cambian;
40. que para si la regla que menos falla en la víspera no es la de los 28 días en Acción de Gracias y la del mismo día
    en Navidad y en Año Nuevo;
41. que para si en dólares la media del mismo día no se queda corta (página 11);
42. que para si en dólares la regla de WI_2 no es la media del mismo día (página 9);
43. que paginas() escribe tres páginas y para si una no se comprueba con el panel;
44. que salen las frases de la cuarta pasada (§2 ter: 38b, 39, 40, 41 y 42) y ya no las que cambian;
45. que para si Año Nuevo no tiene la misma regla que Navidad o si el 25 de diciembre no queda fuera del error;
46. que salen las frases de la quinta pasada (§2 quater: 43, 44 y 45) y ya no las que cambian;
47. que para si en la víspera de Navidad no falta solo el 25 de diciembre («sin contar el día de cierre»);
48. que para si en dólares alguna tienda no tiene la media del mismo día como regla (página 2, respuesta 3).

Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_18_informe_final.py
"""

# copy duplica las entradas para estropearlas sin tocar las buenas
import copy
# importlib carga el script por su ruta sin ejecutar su main
import importlib.util
# json escribe las entradas pequeñas
import json
# shutil borra la carpeta temporal
import shutil
# sys da el código de salida
import sys
# date y timedelta escriben los días de partida, cada 28 días
from datetime import date, timedelta
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

# =====================================================================================================================
# CONFIGURACIÓN
# =====================================================================================================================

# Carpeta del caso, desde la prueba
RAIZ = Path(__file__).resolve().parents[1]
# Script que se prueba
SCRIPT = RAIZ / "scripts" / "18_informe_final.py"
# Carpeta temporal de la prueba: se crea y se borra
TMP = RAIZ / "tests" / "tmp_informe_final"
# Fecha de datos de las entradas buenas
FECHA = "2015-05-22"
# El modelo en uso de las entradas buenas: el reentrenado con la venta hasta la fecha de los datos
EN_USO = "modelos/reentrenos/2015-05-22"
# Casos que fallan
FALLOS = []


# =====================================================================================================================
# AYUDAS
# =====================================================================================================================

def caso(nombre, condicion):
    """Apunta un caso y dice si pasa."""
    print(("PASA " if condicion else "FALLA ") + nombre)
    if not condicion:
        FALLOS.append(nombre)


def para(funcion, *args):
    """True si la función para con ValueError."""
    try:
        funcion(*args)
    except ValueError as error:
        print(f"      (para: {str(error)[:150]})")
        return True
    # Otro error no es parar con motivo: se dice y cuenta como que no para
    except Exception as error:  # noqa: BLE001
        print(f"      (otro error, no para con motivo: {type(error).__name__}: {str(error)[:150]})")
        return False
    return False


def cargar():
    """Carga el script como módulo, sin ejecutar su main."""
    spec = importlib.util.spec_from_file_location("informe_final_69", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# =====================================================================================================================
# ENTRADAS PEQUEÑAS, CON LA FORMA DE LAS DE informes/
# =====================================================================================================================

def fila(prevision, error, sesgo):
    """Una fila de errores, como en validacion.json."""
    return {"grupo": None, "prevision": prevision, "error": error, "sesgo": sesgo}


def grupo(nombre, error_modelo, error_regla, sesgo_modelo, series, regla="media_mismo_dia_4_semanas"):
    """Un grupo de la previsión sumada (niveles), como en validacion.json."""
    return {"grupo": nombre, "series": series, "error_modelo": error_modelo, "sesgo_modelo": sesgo_modelo,
            "regla_que_menos_falla": regla, "error_regla": error_regla,
            "modelo_falla_menos": error_modelo < error_regla}


def departamento(nombre, error_modelo, error_regla, regla, se_recomienda):
    """La recomendación de un departamento, como en validacion.json."""
    nombres = {"media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores",
               "media_28_dias": "la media de los últimos 28 días"}
    return {"departamento": nombre, "error_modelo": error_modelo, "error_regla": error_regla,
            "regla_que_menos_falla": regla, "regla_que_menos_falla_nombre": nombres[regla],
            "se_recomienda": se_recomienda}


def objetivo(o):
    """Un objetivo de validacion.json con lo que lee el informe; `o` es «unidades» o «dolares»."""
    u = o == "unidades"
    # Trece días de partida, uno cada 28 días
    origenes = [(date(2014, 5, 22) + timedelta(days=28 * i)).isoformat() for i in range(13)]
    # Errores y sesgos de las seis previsiones
    todas = ([fila("modelo", 15.6436, 3.2465), fila("repetir_semana_anterior", 22.1984, -1.64),
              fila("media_28_dias", 21.6389, -3.58), fila("media_mismo_dia_4_semanas", 17.9283, 0.2846),
              fila("trivial", 72.51, -45.9), fila("suavizado", 17.3976, -0.93)] if u else
             [fila("modelo", 17.3733, 2.12), fila("repetir_semana_anterior", 23.9204, -2.42),
              fila("media_28_dias", 22.2781, -0.99), fila("media_mismo_dia_4_semanas", 19.4362, -0.94),
              fila("trivial", 69.47, -43.1), fila("suavizado", 19.2872, -2.04)])
    evento = ([fila("modelo", 17.78, 6.51), fila("repetir_semana_anterior", 21.98, 1.6),
               fila("media_28_dias", 20.86, -0.7), fila("media_mismo_dia_4_semanas", 18.81, 2.4),
               fila("suavizado", 18.71, -1.2)] if u else
              [fila("modelo", 18.49, 2.51), fila("repetir_semana_anterior", 25.08, -0.5),
               fila("media_28_dias", 23.86, -1.2), fila("media_mismo_dia_4_semanas", 20.88, 0.3),
               fila("suavizado", 21.27, -2.7)])
    tiendas = ["CA_1", "CA_2", "CA_3", "CA_4", "TX_1", "TX_2", "TX_3", "WI_1", "WI_2", "WI_3"]
    # En dólares, CA_2 es la única tienda en que la regla falla menos, y la que más se pasa
    grupos_tienda = [grupo(t, 8.0, 9.5, 2.0, 7) for t in tiendas]
    # WI_2 es la tienda donde más gana el modelo, en los dos objetivos («sigue siendo», página 4)
    grupos_tienda[8] = grupo("WI_2", 9.3, 18.6, 2.0, 7)
    if not u:
        grupos_tienda[1] = grupo("CA_2", 11.7, 10.0, 7.5, 7)
    deps = ([departamento("FOODS_1", 20.33, 23.07, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("FOODS_2", 18.47, 24.64, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("FOODS_3", 12.53, 14.71, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_1", 22.21, 23.98, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_2", 52.17, 51.2, "media_28_dias", "la media de los últimos 28 días"),
             departamento("HOUSEHOLD_1", 13.37, 13.6, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOUSEHOLD_2", 22.28, 23.07, "media_mismo_dia_4_semanas", "el modelo")] if u else
            [departamento("FOODS_1", 23.4, 26.83, "media_28_dias", "el modelo"),
             departamento("FOODS_2", 18.3, 23.91, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("FOODS_3", 14.33, 15.88, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_1", 20.64, 22.31, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_2", 62.44, 57.97, "media_28_dias", "la media de los últimos 28 días"),
             departamento("HOUSEHOLD_1", 15.21, 16.45, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOUSEHOLD_2", 24.9649, 24.9475, "media_mismo_dia_4_semanas",
                          "la media del mismo día de las 4 semanas anteriores")])
    sin_cubrir = (["Thanksgiving", "Christmas", "NewYear", "Halloween"] if u else ["Christmas"])
    return {
        "horizonte": 10 if u else 28,
        "origenes": origenes,
        # Días previstos por combinación: 13 pruebas de 10 días en unidades; en dólares, 364 (el 25/12 fuera)
        "dias_previstos_por_serie": 130 if u else 364,
        "dias_fuera_del_error": [] if u else ["2014-12-25"],
        "errores": {"todas": todas, "dias_con_evento": evento},
        "veredicto": {"origenes_que_gana": 12, "de": 13, "minimo": 10,
                      "ventaja": 2.2847 if u else 2.0629,
                      "error_modelo": todas[0]["error"], "error_rival": todas[3]["error"],
                      "rival_por_origen": ["media_mismo_dia_4_semanas"] * 13,
                      "intervalo": {"bajo": 1.2318 if u else 1.0184, "alto": 3.4945 if u else 3.3213,
                                    "percentiles": [2.5, 97.5]},
                      "veredicto": "gana"},
        "suavizado": {"error_rival": todas[5]["error"], "lectura": "gana", "origenes_que_gana": 10 if u else 13,
                      "de": 13, "minimo": 10, "ventaja": 1.7540 if u else 1.9139,
                      "intervalo": {"bajo": 0.5116 if u else 0.3039, "alto": 3.2822 if u else 3.9229,
                                    "percentiles": [2.5, 97.5]}},
        "robustez": {
            "aporte_por_serie": {"series": [
                {"store_id": "WI_2", "dept_id": "FOODS_3", "aporte": 0.5},
                {"store_id": "WI_2", "dept_id": "FOODS_2", "aporte": 0.4},
                {"store_id": "WI_3", "dept_id": "FOODS_3", "aporte": 0.2},
                {"store_id": "CA_3", "dept_id": "FOODS_3", "aporte": 0.1}]},
            "ventaja_sin": {"juntas": {"quitar": ["WI_2", "WI_3"], "ventaja": 1.2004 if u else 0.99}},
            "intervalo_por_tienda": {"bajo": 1.0809 if u else 0.7852, "alto": 3.7695 if u else 3.8049},
            "series_con_alguna_regla_mejor": {"cuantas": 16 if u else 19, "de": 70},
            "eventos": {"cuantos": 30, "cubiertos": 8 if u else 29,
                        "sin_cubrir": [{"nombre": n} for n in sin_cubrir],
                        "desde": "2014-05-23", "hasta": FECHA}},
        "niveles": {
            "padres": {"estado": {t: t[:2] for t in tiendas}},
            "cadena": {"grupos": [dict(grupo("cadena", 4.88 if u else 4.91, 7.15 if u else 7.62, todas[0]["sesgo"], 70),
                                       errores=[fila("modelo", 4.88 if u else 4.91, todas[0]["sesgo"])])],
                       "origenes": {"origenes_que_gana": 9 if u else 12, "de": 13}},
            "estado": {"grupos": [grupo("CA", 5.59, 7.3, 3.9, 28), grupo("TX", 6.28, 7.53, 3.5, 21),
                                  grupo("WI", 6.87, 12.63, 2.1, 21)] if u else
                       [grupo("CA", 5.87, 7.45, 3.1, 28), grupo("TX", 6.56, 8.54, 1.7, 21),
                        grupo("WI", 7.22, 13.11, 1.0, 21)]},
            "categoria": {"grupos": [grupo("FOODS", 5.52, 8.92, 3.3, 30), grupo("HOBBIES", 9.21, 10.29, 0.3, 20),
                                     grupo("HOUSEHOLD", 6.39, 6.91, 4.4, 20)] if u else
                          [grupo("FOODS", 6.57, 10.0, 3.7, 30), grupo("HOBBIES", 7.7, 9.79, -1.2, 20),
                           grupo("HOUSEHOLD", 6.57, 8.45, 0.1, 20)]},
            "tienda": {"grupos": grupos_tienda}},
        "recomendacion_por_departamento": deps,
    }


def entradas_buenas():
    """Los cuatro JSON pequeños, con su nombre de fichero y la misma fecha de datos."""
    deps = ["FOODS_1", "FOODS_2", "FOODS_3", "HOBBIES_1", "HOBBIES_2", "HOUSEHOLD_1", "HOUSEHOLD_2"]
    validacion = {"script": "scripts/16_validacion.py", "fecha_datos": FECHA,
                  "receta": {"ganador": {"unidades": {"algoritmo": "HistGradientBoosting"},
                                         "dolares": {"algoritmo": "HistGradientBoosting"}}},
                  "validacion": {"unidades": objetivo("unidades"), "dolares": objetivo("dolares")}}
    # Acción de Gracias y Año Nuevo bajan la venta en los siete; Navidad, sin cifra (la tienda cierra)
    eventos = []
    # dias_serie: 30 días de cada festivo por departamento, 3 años en 10 tiendas; Navidad, 0 (la tienda cierra)
    for d in deps:
        eventos.append({"evento": "Thanksgiving", "departamento": d, "dias_serie": 30,
                        "cambio_pct": -72.2222 if d == "HOBBIES_2" else -30.0})
        eventos.append({"evento": "NewYear", "departamento": d, "dias_serie": 30,
                        "cambio_pct": -77.8027 if d == "HOBBIES_2" else -25.0})
        eventos.append({"evento": "Christmas", "departamento": d, "dias_serie": 0, "cambio_pct": None})
    snap = {d: {"cambio_pct": {"FOODS_2": 24.0359, "FOODS_3": 12.0101}.get(d, 1.0)} for d in deps}
    dia = {d: {"cociente": {"HOUSEHOLD_1": 1.5142, "HOBBIES_2": 1.2187}.get(d, 1.4),
               "dia_fuerte": "Sunday" if d.startswith("FOODS") else "Saturday"} for d in deps}
    exploratorio = {
        "script": "scripts/06_analisis_exploratorio.py", "fecha_datos": FECHA,
        "productos_por_departamento": {"FOODS_1": 43, "FOODS_2": 61, "FOODS_3": 129, "HOBBIES_1": 73,
                                       "HOBBIES_2": 27, "HOUSEHOLD_1": 93, "HOUSEHOLD_2": 74},
        "alertas": [{"id": "A-41", "texto": "El recorte tiene 500 de los 3.049 productos: un total del caso no es "
                                            "un total de Walmart"}],
        "poblacion": {"construccion": {"desde": "2011-01-29", "hasta": "2014-05-22"}},
        "ceros": {"series_intermitentes": [f"{t} HOBBIES_2" for t in
                                           ["CA_1", "CA_2", "CA_3", "CA_4", "TX_1", "TX_2", "TX_3", "WI_1", "WI_2",
                                            "WI_3"]]},
        "saltos": [{"tienda": "WI_2", "departamento": "FOODS_2", "fecha": "2012-05-15", "razon": 3.01, "salto": True},
                   {"tienda": "WI_2", "departamento": "FOODS_3", "fecha": "2012-06-02", "razon": 1.63, "salto": True},
                   {"tienda": "WI_3", "departamento": "FOODS_3", "fecha": "2012-08-04", "razon": 0.73,
                    "salto": False}],
        "reparto": {"departamento": [{"nombre": d, "unidades": 3000000 if d == "FOODS_3" else 500000}
                                     for d in deps]},
        "pregunta_4": {
            "eventos": eventos, "snap": snap, "dia_semana": dia,
            "mes": {c: {"meses": {str(m): {"cambio_pct": -8.9 if m == 5 else 2.0} for m in range(1, 13)}}
                    for c in ("FOODS", "HOBBIES", "HOUSEHOLD")},
            "precio": {"por_departamento": {d: {"mediana_spearman": -0.38 if d == "FOODS_2" else 0.2}
                                            for d in deps}}}}
    escenario = {
        "bajo": (5.0, -94839.9, 112000.0, None), "central": (10.0, -6230.74, 56000.0, None),
        "alto": (15.0, 62517.71, 28000.0, 10)}
    # Ocho supuestos: cuatro con fuente pública y cuatro sin fuente
    supuestos = ([{"nombre": f"con fuente {i}", "origen": "fuente pública"} for i in range(4)]
                 + [{"nombre": f"sin fuente {i}", "origen": "decidido por el equipo de análisis a petición del responsable del caso, 24/11/2026"}
                    for i in range(4)])
    business = {"script": "scripts/09_business_case.py", "fecha_datos": FECHA, "supuestos": supuestos,
                "linea_de_hoy": {"venta_2013": 6094766.85, "venta_mes": 507897.2375},
                "escenarios": {k: {"parametros": {"mejora_pct": m}, "por_anio": [{}, {}, {}],
                                   "total": {"beneficio": b, "coste": c}, "mes_recupera_inversion": r}
                               for k, (m, b, c, r) in escenario.items()}}
    busqueda = {"script": "scripts/15_busqueda.py", "fecha_datos": FECHA,
                "tabla": {"desde": "2011-03-05", "hasta": "2014-05-22"}}
    # La partición: el año de comprobación, con sus días
    particion = {"script": "scripts/10_particion.py", "fecha_datos": FECHA,
                 "partes": [{"parte": "entrenamiento", "fecha_min": "2011-01-29", "fecha_max": "2014-05-22",
                             "dias": 1210},
                            {"parte": "validacion", "fecha_min": "2014-05-23", "fecha_max": FECHA, "dias": 365}]}
    return {"validacion.json": validacion, "analisis-exploratorio__hechos_series.json": exploratorio,
            "business_case.json": business, "busqueda.json": busqueda, "particion.json": particion,
            "prueba_final.json": prueba_final()}


# ---------------------------------------------------------------------------------------------------------------------
# La prueba final, con la forma de prueba_final.json
# ---------------------------------------------------------------------------------------------------------------------

def veredicto(gana, ventaja, bajo, alto, modelo, rival, lectura):
    """Un veredicto de prueba_final.json."""
    return {"origenes_que_gana": gana, "de": 13, "minimo": 10, "ventaja": ventaja, "error_modelo": modelo,
            "error_rival": rival, "intervalo": {"bajo": bajo, "alto": alto, "percentiles": [2.5, 97.5]},
            "veredicto": lectura}


def objetivo_pf(o):
    """Un objetivo de la variante reentrenado (el modelo en uso) de prueba_final.json."""
    u = o == "unidades"
    origenes = [(date(2015, 5, 22) + timedelta(days=28 * i)).isoformat() for i in range(13)]
    todas = ([fila("modelo", 14.4995, 0.2663), fila("repetir_semana_anterior", 21.701, -0.2812),
              fila("media_28_dias", 21.0606, -3.3446), fila("media_mismo_dia_4_semanas", 16.9025, 0.2624),
              fila("suavizado", 16.1111, -0.0444)] if u else
             [fila("modelo", 16.2055, -0.4995), fila("repetir_semana_anterior", 23.0839, -1.7569),
              fila("media_28_dias", 21.2867, -1.455), fila("media_mismo_dia_4_semanas", 18.6106, -1.4407),
              fila("suavizado", 18.0358, -1.6723)])
    tiendas = (["CA_1", 8.0973, 8.7267], ["CA_2", 9.2988, 8.1717], ["CA_3", 7.1702, 8.3046], ["CA_4", 7.9771, 7.9172],
               ["TX_1", 7.7804, 9.6618], ["TX_2", 6.7769, 8.3607], ["TX_3", 7.9299, 8.8608], ["WI_1", 7.538, 8.9323],
               ["WI_2", 9.1628, 18.1645], ["WI_3", 7.4443, 11.6325]) if u else (
               ["CA_1", 8.2776, 8.9831], ["CA_2", 10.3055, 10.8069], ["CA_3", 7.1559, 8.7608],
               ["CA_4", 9.2401, 9.2085], ["TX_1", 8.6035, 10.5441], ["TX_2", 8.8953, 10.7303],
               ["TX_3", 9.3136, 11.004], ["WI_1", 8.6341, 10.8032], ["WI_2", 9.5476, 17.8192], ["WI_3", 8.8658, 12.319])
    deps = ([departamento("FOODS_1", 20.4735, 21.7144, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("FOODS_2", 17.5993, 23.4104, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("FOODS_3", 10.8537, 13.4757, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_1", 20.8418, 22.1107, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_2", 50.2006, 50.1128, "media_28_dias", "la media de los últimos 28 días"),
             departamento("HOUSEHOLD_1", 12.0854, 13.0276, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOUSEHOLD_2", 20.1535, 21.0737, "media_mismo_dia_4_semanas", "el modelo")] if u else
            [departamento("FOODS_1", 21.5563, 24.1864, "media_28_dias", "el modelo"),
             departamento("FOODS_2", 16.8544, 22.5701, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("FOODS_3", 13.1516, 15.1226, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_1", 19.249, 21.1417, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOBBIES_2", 60.4866, 59.7538, "media_28_dias", "la media de los últimos 28 días"),
             departamento("HOUSEHOLD_1", 14.5115, 15.8966, "media_mismo_dia_4_semanas", "el modelo"),
             departamento("HOUSEHOLD_2", 22.3439, 24.1147, "media_mismo_dia_4_semanas", "el modelo")])
    cadena = grupo("cadena", 4.2442 if u else 4.8463, 5.8738 if u else 7.1524, todas[0]["sesgo"], 70)
    cadena["errores"] = [fila("modelo", cadena["error_modelo"], todas[0]["sesgo"])]
    x = {
        "horizonte": 10 if u else 28,
        "origenes": origenes,
        "dias_fuera_del_error": [] if u else ["2015-12-25"],
        "errores": {"todas": todas},
        "veredicto": (veredicto(12, 16.9025 - 14.4995, 1.4144, 3.5428, 14.4995, 16.9025, "gana") if u else
                      veredicto(13, 18.6106 - 16.2055, 1.4606, 3.5533, 16.2055, 18.6106, "gana")),
        "suavizado": {"error_rival": todas[4]["error"], "lectura": "gana", "origenes_que_gana": 11 if u else 12,
                      "de": 13, "minimo": 10},
        "exceso": {"valores": {f["prevision"]: f["sesgo"] for f in todas}},
        "niveles": {
            "padres": {"estado": {t[0]: t[0][:2] for t in tiendas}},
            "cadena": {"grupos": [cadena], "origenes": {"origenes_que_gana": 10 if u else 12, "de": 13}},
            "estado": {"grupos": [grupo("CA", 5.515, 5.669, -0.4, 28), grupo("TX", 5.68, 7.354, 1.1, 21),
                                  grupo("WI", 5.878, 11.284, 0.5, 21)] if u else
                       [grupo("CA", 5.707, 6.833, -1.2, 28), grupo("TX", 7.272, 9.01, 0.4, 21),
                        grupo("WI", 6.936, 12.028, -0.2, 21)]},
            "categoria": {"grupos": [grupo("FOODS", 5.091, 7.487, 0.8, 30), grupo("HOBBIES", 7.561, 8.228, -0.5, 20),
                                     grupo("HOUSEHOLD", 4.727, 6.275, -0.9, 20)] if u else
                          [grupo("FOODS", 6.095, 9.284, 1.3, 30), grupo("HOBBIES", 6.812, 7.977, -2.0, 20),
                           grupo("HOUSEHOLD", 6.509, 8.352, -3.5, 20)]},
            # En unidades, en WI_2 la regla que menos falla es la media de los últimos 28 días (como en el JSON real)
            "tienda": {"grupos": [grupo(t, m, r, 0.5, 7, regla="media_28_dias" if u and t == "WI_2"
                                        else "media_mismo_dia_4_semanas") for t, m, r in tiendas]}},
        "recomendacion_por_departamento": deps,
    }
    if u:
        # Las tres vísperas de festivo, a 10 días, una vez cada una
        festivos = [("Acción de Gracias", "2015-11-25", 18.7695, 5.1134, "media_28_dias", 25.5146, 11.8306),
                    ("Navidad", "2015-12-24", 18.412, 1.408, "media_mismo_dia_4_semanas", 21.234, 4.348),
                    ("Año Nuevo", "2015-12-31", 14.024, 0.236, "media_mismo_dia_4_semanas", 20.536, -8.898)]
        x["festivos"] = {"por_origen": [
            {"festivo": n, "origen": org,
             # Los 10 días siguientes a la víspera, sin el 25 de diciembre (fuera del error): en Navidad son 9
             "dias": [x for x in ((date.fromisoformat(org) + timedelta(days=i + 1)).isoformat() for i in range(10))
                      if x[5:] != "12-25"],
             "errores": [fila("modelo", em, sm), fila(regla, er, sr)], "error_modelo": em, "sesgo_modelo": sm,
             "regla_que_menos_falla": regla, "error_regla": er, "modelo_falla_menos": em < er}
            for n, org, em, sm, regla, er, sr in festivos]}
    return x


def prueba_final():
    """prueba_final.json pequeño: las dos variantes, con el modelo en uso y el del año de comprobación."""
    tal = {"unidades": {"veredicto": veredicto(9, 1.6081, 0.6331, 2.7422, 15.2943, 16.9025, "no gana")},
           "dolares": {"veredicto": veredicto(12, 1.1545, 0.0196, 2.4637, 17.4561, 18.6106, "gana")}}
    return {"script": "scripts/20_prueba_final.py", "fecha_datos": FECHA, "fin_prueba_final": "2016-05-22",
            "modelos": {"tal_como_esta": {"carpeta": "modelos/reentrenos/2026-11-25"},
                        "reentrenado": {"carpeta": EN_USO}},
            "tal_como_esta": tal,
            "reentrenado": {"unidades": objetivo_pf("unidades"), "dolares": objetivo_pf("dolares")}}


def roto(entradas, cambio):
    """Una copia de las entradas con `cambio` aplicado a prueba_final.json."""
    copia = copy.deepcopy(entradas)
    # Un script que no lee la prueba final no la trae en sus entradas: se añade para que el caso pueda dar rojo
    copia.setdefault("prueba_final.json", prueba_final())
    cambio(copia["prueba_final.json"])
    return copia


def de_lista(lista, campo, valor):
    """La fila de una lista con ese valor en ese campo."""
    return next(f for f in lista if f[campo] == valor)


def escribir(entradas):
    """Escribe las entradas en la carpeta temporal, en UTF-8."""
    TMP.mkdir(parents=True, exist_ok=True)
    for nombre, datos in entradas.items():
        (TMP / nombre).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


# =====================================================================================================================
# CASOS
# =====================================================================================================================

def casos(m):
    """Lanza los casos sobre el módulo cargado."""
    # 2. Control que no debe disparar: con las entradas buenas, el informe se monta entero
    escribir(entradas_buenas())
    entradas = m.leer_entradas(TMP)
    caso("2. lee las seis entradas de la carpeta que se le da, con la prueba final", len(entradas) == 6
         and "prueba_final.json" in entradas)
    try:
        texto, filas, inf = m.construir(entradas, None, EN_USO)
        monta = True
    except Exception as error:  # noqa: BLE001
        print(f"      (para: {type(error).__name__}: {str(error)[:300]})")
        monta = False
    caso("2. con JSON buenos monta el informe sin parar", monta)
    if monta:
        antes = [p for p in inf.paginas if p.tipo != "anexo"]
        caso("2. quince páginas antes del anexo: las once del texto, con el resumen y la página 2 en dos y la 3 en tres",
             len(antes) == 15)
        caso("2. orden: resumen, doce de resultado, límites y decisiones",
             [p.tipo for p in antes] == ["resumen"] + ["resultado"] * 12 + ["limites", "decision"])
        caso("2. cada página partida lleva el mismo título en sus dos partes",
             antes[0].titulo == antes[1].titulo and antes[3].titulo == antes[4].titulo
             and antes[5].titulo == antes[6].titulo == antes[7].titulo)
        caso("2. hay anexo", any(p.tipo == "anexo" for p in inf.paginas))
        # Las dos proporciones salen de las cifras del veredicto: 2,403 / 16,9025 y 2,4051 / 18,6106
        caso("2. el 14,2 % sale de las cifras del veredicto del modelo en uso en unidades", "14,2 %" in texto)
        caso("2. el 12,9 % sale de las cifras del veredicto del modelo en uso en dólares", "12,9 %" in texto)
        for cifra in ("14,5", "16,9", "−94.840 $", "+62.518 $", "Mes 10", "1,20", "16 de 70", "−77,8 %",
                      "05/03/2011", "3.049", "22/05/2016", "23/05/2015"):
            caso(f"2. la cifra «{cifra}» se lee de su JSON y está en el informe", cifra in texto)
        caso("2. el CSV de los gráficos lleva cifras", len(filas) >= 10)
        caso("2. el anexo dice cómo se calculan las dos proporciones",
             "1 menos el error del modelo entre el de la regla que menos falla" in texto)

    # 3. Un JSON con otra fecha_datos, y la prueba final que no acaba el 22/05/2016
    otra = copy.deepcopy(entradas)
    otra["business_case.json"]["fecha_datos"] = "2015-05-21"
    caso("3. para con un JSON de otra fecha_datos", para(m.comprobar_fechas, otra))
    caso("3. construir también para con esa fecha", para(m.construir, otra))
    otra = roto(entradas, lambda p: p.update(fecha_datos="2016-05-22"))
    caso("3. para si prueba_final.json trae otra fecha_datos", para(m.construir, otra))
    otra = roto(entradas, lambda p: p.update(fin_prueba_final="2016-05-21"))
    caso("3. para si la prueba final no acaba el 22/05/2016", para(m.construir, otra))

    # 4. HOBBIES_2, el único departamento con regla en los dos objetivos
    def h2_gana(p):
        """El modelo por delante de la regla en HOBBIES_2, en unidades."""
        d = de_lista(p["reentrenado"]["unidades"]["recomendacion_por_departamento"], "departamento", "HOBBIES_2")
        d["error_modelo"], d["se_recomienda"] = 40.0, "el modelo"
    caso("4. para si en HOBBIES_2 en unidades se recomienda el modelo", para(m.construir, roto(entradas, h2_gana)))

    def f1_regla(p):
        """FOODS_1 con la regla en dólares: HOBBIES_2 ya no es el único."""
        d = de_lista(p["reentrenado"]["dolares"]["recomendacion_por_departamento"], "departamento", "FOODS_1")
        d["error_modelo"], d["se_recomienda"] = 25.0, "la media de los últimos 28 días"
    caso("4. para si en dólares otro departamento lleva la regla", para(m.construir, roto(entradas, f1_regla)))

    # 5. Una frase del texto aprobado cambiada
    aprobado = ("---\n\n# Notas para el responsable del caso antes del texto\n\n- Esto no va al informe.\n\n---\n\n"
                "# El título del informe\n\n## Página 1 · Qué se prevé\n### Un título de página\n\n"
                "**Análisis ejecutivo.** Al sumar, los errores se compensan y el error baja. Falla 4,9.\n\n"
                "| Grupo | Cifra |\n|---|---|\n| California | 5,6 |\n")
    bueno = ("<nav><p class=\"informe-titulo\">El título del informe</p><button>2. Qué se prevé</button></nav>"
             "<section id=\"p1\"><h1>Un título de página</h1><h2>Análisis ejecutivo</h2>"
             "<p>Al sumar, los errores se compensan y el error baja. Falla 4,9.</p>"
             "<table><tr><th>Grupo</th><th>Cifra</th></tr><tr><td>California</td><td>5,6</td></tr></table></section>")
    caso("5. no para con el texto igual al aprobado", not para(m.comprobar_texto, bueno, aprobado))
    caso("5. para si una frase aprobada ha cambiado",
         para(m.comprobar_texto, bueno.replace("se compensan y", "se compensan del todo y"), aprobado))
    caso("5. las notas para el responsable del caso no se buscan en el informe", "Esto no va" not in bueno
         and not para(m.comprobar_texto, bueno, aprobado))

    # 6. Una cifra escrita a mano en vez de leída
    pagina = "<section id=\"p1\"><h1>Título</h1><p>Falla 15,6 por cada 100 vendidas, a 10 días.</p></section>"
    caso("6. no para con cifras leídas", not para(m.cifras_leidas, pagina, {"15,6", "10"}))
    caso("6. para con una cifra que no se leyó de ningún JSON",
         para(m.cifras_leidas, pagina.replace("15,6", "15,7"), {"15,6", "10"}))

    # 7. Términos que prohíbe la hoja de vocabulario y nombres internos
    def seccion(frase):
        """Una página con una frase."""
        return f"<section id=\"p2\"><h1>Título</h1><p>{frase}</p></section>"
    caso("7. para con «pronóstico» (la hoja dice «la previsión»)",
         para(m.sin_sinonimos, seccion("El pronóstico se pasa de media.")))
    caso("7. para con «serie» (la hoja dice «combinación»)",
         para(m.sin_sinonimos, seccion("Cada serie se prevé aparte.")))
    caso("7. para con «WAPE» fuera del anexo", para(m.sin_jerga, seccion("El WAPE baja."), set()))
    caso("7. para con «rival» fuera del anexo", para(m.sin_jerga, seccion("El rival falla más."), set()))
    caso("7. para con «validación» fuera del anexo (la hoja dice «el año de comprobación»)",
         para(m.sin_jerga, seccion("El modelo de la validación."), set()))
    caso("7. no para con «mejoras supuestas» (los escenarios del dinero)",
         not para(m.sin_sinonimos, seccion("Con mejoras supuestas, el resultado cambia.")))
    caso("7. no para con «Horizonte de la previsión»",
         not para(m.sin_jerga, seccion("Horizonte de la previsión en unidades."), set()))

    # 8. Un título con un código suelto
    caso("8. para con un código suelto en un título",
         para(m.titulos_claros, ["En HOBBIES_2 la media de los últimos 28 días falla menos que el modelo"]))
    caso("8. para con una letra suelta en un título", para(m.titulos_claros, ["En B la regla falla menos"]))
    caso("8. no para con el código y su nombre",
         not para(m.titulos_claros,
                  ["En el departamento de ocio HOBBIES_2 la media de los últimos 28 días falla menos que el modelo",
                   "Sin dos tiendas de Wisconsin la ventaja del año de comprobación se quedaba en la mitad"]))

    # 9. Más de 15 páginas sin el anexo
    largo = m.Informe("Informe de prueba", "datos de prueba")
    largo.pagina("Resumen de prueba", "resumen", panel="Resumen")
    for i in range(15):
        largo.pagina(f"Página de prueba número {i}", "resultado", panel=f"Página {i}")
    caso("9. para con 16 páginas sin el anexo", para(largo.html))

    # 10. Las frases de la versión 4, con sus cifras leídas de las entradas buenas
    if monta:
        for frase in ("Pedir con la previsión del modelo en seis de los siete departamentos",
                      "comprobada en dos años seguidos, del 23/05/2014 al 22/05/2016.",
                      "Se comprobó en el último año guardado, con 13 pruebas, una cada 28 días.",
                      "El modelo en uso falla menos que la regla en 12 de 13 pruebas en unidades y en 13 de 13 en "
                      "dólares.",
                      "Tal como salió de ese año, en unidades ganó en 9 de 13 pruebas,",
                      "el modelo falla 2,40 unidades menos por cada 100, un 14,2 % menos. En dólares falla 2,41 menos, "
                      "un 12,9 % menos.",
                      "la ventaja va de 1,41 a 3,54 unidades por cada 100 y de 1,46 a 3,55 dólares.",
                      "falló 15,3 unidades por cada 100 en este año y ganó en 9 de las 13 pruebas.",
                      # Las frases de la versión 4 que cambia la tercera pasada se comprueban en su forma nueva (39)
                      "así que en unidades no se confirmó. En dólares sí, con 12 de 13.",
                      "le gana en 11 de 13 pruebas en unidades y en 12 de 13 en dólares.",
                      "En la cadena la previsión se pasa +0,3 unidades y se queda corta 0,5 dólares por cada 100.",
                      "En dólares, CA_4 empata: la regla falla menos por 0,03.",
                      "En unidades, la regla falla menos en CA_2, con 8,2 frente a 9,3. En CA_4 también, por 0,06.",
                      "WI_2 sigue siendo la tienda donde más gana: 9,5 dólares por cada 100 frente a 17,8",
                      "En unidades la regla falla menos por solo 0,09; en dólares, por 0,73.",
                      "En el año de comprobación, el modelo anterior se pasaba +3,2",
                      "Unidades de más en los 10 días tras la víspera de Acción de Gracias",
                      "En Acción de Gracias, 18,8 unidades por cada 100 frente a 25,5",
                      "en el último año, la previsión falla un 14,2 % menos en unidades.",
                      "Cada festivo grande se comprobó una sola vez, desde su víspera y a 10 días",
                      "la venta de 2011 a 2016",
                      "Se pide a la Dirección que apruebe cuatro decisiones",
                      "Falla menos en 12 de 13 pruebas",
                      "Sumada, falla menos que la regla en 9 de 10 tiendas; en CA_4 empatan (págs. 6 a 8)",
                      "Aprueba las cuatro decisiones de la página 15",
                      "13 días de partida en cada año, uno cada 28 días.",
                      "ajustada con la venta hasta el 22/05/2015. Se comprobó del 23/05/2015 al 22/05/2016.",
                      "4 de 8", "con 3 años de cada festivo",
                      "La previsión del modelo falla menos que las reglas sencillas en casi todas las tiendas"):
            caso(f"10. el informe dice «{frase}»", frase in texto)
        caso("10. ya no dice «cuando el último año guardado la confirme» (versión 3)",
             "cuando el último año guardado la confirme" not in texto)
        # La tabla de la página 2: la fila del modelo en uso y la del suavizado, con su exceso o defecto
        tabla_p2 = texto.split("Se pasa (+) o se queda corta (−), dólares por cada 100", 1)
        caso("10. la tabla de la página 2 lleva las dos columnas de exceso", len(tabla_p2) == 2)
        if len(tabla_p2) == 2:
            filas_p2 = tabla_p2[1].split("</tbody>", 1)[0]
            caso("10. fila del modelo con 14,5, 16,2, 0,3 y −0,5",
                 "<td>Modelo</td><td class=\"num\">14,5</td><td class=\"num\">16,2</td>"
                 "<td class=\"num\">0,3</td><td class=\"num\">−0,5</td>" in filas_p2)
            caso("10. fila del suavizado con 0,0 y −1,7",
                 "<td class=\"num\">0,0</td><td class=\"num\">−1,7</td></tr>" in filas_p2)
    caso("10. para con «La mejora, la venta perdida…»: en la versión 3 ya no es excepción",
         para(m.sin_sinonimos, seccion("La mejora, la venta perdida, el coste del proyecto y su calendario")))

    # 11. El modelo en uso gana en los dos objetivos
    caso("11. para si en dólares el modelo en uso gana solo en 9 de 13",
         para(m.construir, roto(entradas, lambda p: p["reentrenado"]["dolares"]["veredicto"].update(
             origenes_que_gana=9, veredicto="no gana"))))
    caso("11. para si en unidades el intervalo de la ventaja no queda por encima de cero",
         para(m.construir, roto(entradas, lambda p: p["reentrenado"]["unidades"]["veredicto"]["intervalo"].update(
             bajo=-0.1))))

    # 12. El modelo del año de comprobación: en unidades, una prueba menos de las que pide la regla; en dólares, gana
    caso("12. para si el modelo del año de comprobación gana en unidades (10 de 13)",
         para(m.construir, roto(entradas, lambda p: p["tal_como_esta"]["unidades"]["veredicto"].update(
             origenes_que_gana=10, veredicto="gana"))))
    caso("12. para si en unidades se queda en 8 de 13: ya no es «una menos»",
         para(m.construir, roto(entradas, lambda p: p["tal_como_esta"]["unidades"]["veredicto"].update(
             origenes_que_gana=8))))
    caso("12. para si en dólares no gana",
         para(m.construir, roto(entradas, lambda p: p["tal_como_esta"]["dolares"]["veredicto"].update(
             origenes_que_gana=9, veredicto="no gana"))))

    # 13. En dólares, 9 de 10 tiendas y la que no es CA_4, con una diferencia de menos de 0,05 que se ve
    def tienda_d(nombre, error_modelo):
        """Cambia el error del modelo de una tienda en dólares."""
        def cambio(p):
            g = de_lista(p["reentrenado"]["dolares"]["niveles"]["tienda"]["grupos"], "grupo", nombre)
            g["error_modelo"], g["modelo_falla_menos"] = error_modelo, error_modelo < g["error_regla"]
        return cambio
    caso("13. para si en dólares la regla gana también en TX_1",
         para(m.construir, roto(entradas, tienda_d("TX_1", 10.9))))
    caso("13. para si en CA_4 la regla falla menos por 0,06 (ya no empatan)",
         para(m.construir, roto(entradas, tienda_d("CA_4", 9.2685))))
    caso("13. para si en CA_4 la diferencia es 0,004, que a dos decimales se escribe 0,00",
         para(m.construir, roto(entradas, tienda_d("CA_4", 9.2125))))
    caso("13. para si en dólares el modelo gana en las 10 tiendas",
         para(m.construir, roto(entradas, tienda_d("CA_4", 9.1))))

    # 14. Los supuestos sin fuente del business case
    rota = copy.deepcopy(entradas)
    rota["business_case.json"]["supuestos"][0]["origen"] = "decidido por el equipo de análisis a petición del responsable del caso, 24/11/2026"
    caso("14. para si los supuestos sin fuente son 5", para(m.construir, rota))

    # 15. Los años de cada festivo
    rota = copy.deepcopy(entradas)
    for r in rota["analisis-exploratorio__hechos_series.json"]["pregunta_4"]["eventos"]:
        if r["evento"] == "Thanksgiving" and r["departamento"] == "FOODS_1":
            r["dias_serie"] = 31
    caso("15. para si los días de un festivo no son un número entero de años en las 10 tiendas",
         para(m.construir, rota))

    # 16. La partición
    caso("16. lee particion.json", "particion.json" in entradas)
    if "particion.json" in entradas:
        rota = copy.deepcopy(entradas)
        rota["particion.json"]["fecha_datos"] = "2015-05-21"
        caso("16. para si particion.json trae otra fecha_datos", para(m.construir, rota))
        rota = copy.deepcopy(entradas)
        rota["particion.json"]["partes"][1]["fecha_min"] = "2014-05-24"
        caso("16. para si el año de comprobación de la partición no es el de la validación", para(m.construir, rota))

    # 17. El modelo en uso falla menos que la regla en todos los estados y categorías
    def grupo_pf(o, nivel, nombre, **cambios):
        """Cambia un grupo de un nivel del modelo en uso."""
        def cambio(p):
            de_lista(p["reentrenado"][o]["niveles"][nivel]["grupos"], "grupo", nombre).update(**cambios)
        return cambio
    caso("17. para si en Texas, en unidades, la regla falla menos",
         para(m.construir, roto(entradas, grupo_pf("unidades", "estado", "TX", error_modelo=7.5,
                                                   modelo_falla_menos=False))))
    caso("17. para si en ocio, en dólares, la regla que menos falla es otra",
         para(m.construir, roto(entradas, grupo_pf("dolares", "categoria", "HOBBIES",
                                                   regla_que_menos_falla="media_28_dias"))))

    # 18. En el año de comprobación el modelo se pasaba más que todas las reglas
    rota = copy.deepcopy(entradas)
    de_lista(rota["validacion.json"]["validacion"]["unidades"]["errores"]["todas"], "prevision",
             "repetir_semana_anterior")["sesgo"] = 3.5
    caso("18. para si en el año de comprobación otra previsión se pasa más que el modelo", para(m.construir, rota))

    # 19. El exceso del modelo en uso, por debajo de 0,5 en valor absoluto
    def sesgo_pf(o, valor):
        """Cambia el exceso del modelo en uso en un objetivo."""
        def cambio(p):
            x = p["reentrenado"][o]
            de_lista(x["errores"]["todas"], "prevision", "modelo")["sesgo"] = valor
            x["exceso"]["valores"]["modelo"] = valor
        return cambio
    caso("19. para si en dólares el modelo en uso se queda corto −0,6",
         para(m.construir, roto(entradas, sesgo_pf("dolares", -0.6))))
    caso("19. para si en unidades el modelo en uso se pasa +0,55",
         para(m.construir, roto(entradas, sesgo_pf("unidades", 0.55))))

    # 20. En unidades la regla falla menos justo en CA_2 y CA_4
    def tienda_u(nombre, error_modelo):
        """Cambia el error del modelo de una tienda en unidades."""
        def cambio(p):
            g = de_lista(p["reentrenado"]["unidades"]["niveles"]["tienda"]["grupos"], "grupo", nombre)
            g["error_modelo"], g["modelo_falla_menos"] = error_modelo, error_modelo < g["error_regla"]
        return cambio
    caso("20. para si en unidades el modelo gana en CA_4", para(m.construir, roto(entradas, tienda_u("CA_4", 7.8))))
    caso("20. para si en unidades la regla gana también en TX_1",
         para(m.construir, roto(entradas, tienda_u("TX_1", 9.9))))

    # 21. Las tres vísperas de festivo
    def navidad_pierde(p):
        """En Navidad el modelo falla más que la regla."""
        f = de_lista(p["reentrenado"]["unidades"]["festivos"]["por_origen"], "festivo", "Navidad")
        f["error_modelo"], f["modelo_falla_menos"] = 22.0, False
    caso("21. para si en Navidad el modelo falla más que la regla", para(m.construir, roto(entradas, navidad_pierde)))
    caso("21. para si solo hay dos vísperas", para(m.construir, roto(
        entradas, lambda p: p["reentrenado"]["unidades"]["festivos"]["por_origen"].pop())))
    caso("21. para si una víspera no se mide a 10 días", para(m.construir, roto(
        entradas, lambda p: p["reentrenado"]["unidades"]["festivos"]["por_origen"][0]["dias"].pop())))

    # 22. La cadena se queda corta en dólares
    def cadena_d(p):
        """La cadena se pasa también en dólares."""
        de_lista(p["reentrenado"]["dolares"]["niveles"]["cadena"]["grupos"][0]["errores"], "prevision",
                 "modelo")["sesgo"] = 0.4
    caso("22. para si en dólares la cadena se pasa", para(m.construir, roto(entradas, cadena_d)))

    # 23. El escenario más favorable es el alto
    rota = copy.deepcopy(entradas)
    rota["business_case.json"]["escenarios"]["central"]["total"]["beneficio"] = 70000.0
    caso("23. para si el escenario central sale mejor que el alto", para(m.construir, rota))

    # 24. El modelo en uso de la configuración es el reentrenado de la prueba final, ajustado hasta la fecha de los datos
    caso("24. para si la configuración usa el modelo del año de comprobación",
         para(m.construir, entradas, None, "modelos/reentrenos/2026-11-25"))
    caso("24. para si la carpeta del reentrenado no es la de la fecha de los datos",
         para(m.construir, roto(entradas, lambda p: p["modelos"]["reentrenado"].update(
             carpeta="modelos/reentrenos/2015-06-01")), None, "modelos/reentrenos/2015-06-01"))

    # 25. WI_2, la tienda donde más gana en dólares, en el último año y en el año de comprobación («sigue siendo»)
    caso("25. para si en dólares WI_3 gana más que WI_2",
         para(m.construir, roto(entradas, grupo_pf("dolares", "tienda", "WI_3", error_regla=25.0))))
    rota = copy.deepcopy(entradas)
    de_lista(rota["validacion.json"]["validacion"]["dolares"]["niveles"]["tienda"]["grupos"], "grupo",
             "TX_1")["error_regla"] = 30.0
    caso("25. para si en el año de comprobación WI_2 no era la tienda donde más ganaba", para(m.construir, rota))

    # 26. Las páginas que cita el texto son las del panel
    if monta:
        paneles = [p.panel for p in inf.paginas]
        caso("26. no para con los paneles del informe", not para(m.comprobar_referencias, paneles))
        caso("26. para si una página se parte y las de detrás se corren",
             para(m.comprobar_referencias, paneles[:4] + ["Otra parte"] + paneles[4:]))
    else:
        caso("26. comprueba las páginas citadas (el informe no se montó)", False)

    # 27. En unidades el modelo en uso se pasa lo mismo que la regla, a un decimal
    def regla_u(p):
        """La regla se pasa +0,45 en unidades: a un decimal, +0,5 frente a +0,3."""
        x = p["reentrenado"]["unidades"]
        de_lista(x["errores"]["todas"], "prevision", "media_mismo_dia_4_semanas")["sesgo"] = 0.45
        x["exceso"]["valores"]["media_mismo_dia_4_semanas"] = 0.45
    caso("27. para si en unidades la regla se pasa +0,5 y el modelo +0,3", para(m.construir, roto(entradas, regla_u)))

    # 28. «Por qué bajó el exceso»: el modelo en uso se pasa menos que el del año de comprobación
    rota = roto(entradas, sesgo_pf("unidades", 0.4))
    de_lista(rota["validacion.json"]["validacion"]["unidades"]["errores"]["todas"], "prevision", "modelo")["sesgo"] = 0.35
    caso("28. para si el exceso del modelo en uso no bajó frente al del año de comprobación", para(m.construir, rota))

    # 29. La regla que menos falla prueba a prueba (la del veredicto) puede fallar algo menos que la media del mismo
    # día con todas juntas, como en el último año en unidades, pero las dos se leen igual a un decimal
    def rival_u(error_rival):
        """Pone el error de la regla del veredicto en unidades, con su ventaja."""
        def cambio(p):
            ver = p["reentrenado"]["unidades"]["veredicto"]
            ver["error_rival"], ver["ventaja"] = error_rival, error_rival - ver["error_modelo"]
        return cambio
    caso("29. no para si la regla del veredicto falla 16,90 y la media del mismo día 16,9025",
         not para(m.construir, roto(entradas, rival_u(16.9002))))
    caso("29. para si la regla del veredicto falla 16,80: el texto diría 16,9 y la ventaja saldría de 16,8",
         para(m.construir, roto(entradas, rival_u(16.80))))

    # 30. Las frases de la versión 5, con sus cifras leídas de las entradas buenas
    if monta:
        for frase in ("Un 14,2 % menos que la media del mismo día de las 4 semanas anteriores, que falla 16,9",
                      "Un 12,9 % menos que la misma regla, que falla 18,6",
                      "Unidades que falla la previsión por cada 100 vendidas, a 10 días, el plazo del pedido",
                      "Dólares que falla por cada 100 vendidos, a 28 días, el mes de finanzas",
                      "Sí, en 12 de 13 pruebas en unidades y en 13 de 13 en dólares. En HOBBIES_2, de venta "
                      "intermitente, falla menos la media de los últimos 28 días",
                      "Fuente: venta diaria de las 70 combinaciones, del 23/05/2014 al 22/05/2016; el detalle, en las "
                      "páginas 3 a 15",
                      "Tres de alimentación, dos de ocio y dos de hogar, en 10 tiendas de California, Texas y Wisconsin",
                      "La previsión del modelo falla menos que las tres reglas y el suavizado en el último año guardado",
                      "Al suavizado exponencial, que no es una de las tres reglas, el modelo en uso le gana en 11 de 13 "
                      "pruebas",
                      "Las barras son del modelo en uso. Tal como salió del año de comprobación, sin el año más de "
                      "datos, el modelo falló 15,3 unidades por cada 100 en este año y ganó en 9 de las 13 pruebas.",
                      ">En unidades, a 10 días<", ">En dólares, a 28 días<",
                      "Un 27,7 % menos que la media del mismo día de las 4 semanas anteriores, que falla 5,9",
                      "Un 32,2 % menos que la misma regla, que falla 7,2",
                      # Cambio 32 de la tercera pasada
                      "Por estados, la diferencia es mayor en Wisconsin, con 5,9 frente a 11,3 unidades. En California, "
                      "en unidades, casi empatan: 5,5 frente a 5,7.",
                      "<th>Estado o categoría</th>",
                      # Cambio 34 de la tercera pasada
                      "<th>Departamento</th><th class=\"num\">Unidades: modelo</th><th class=\"num\">Unidades: regla "
                      "que menos falla</th><th class=\"num\">Dólares: modelo</th><th class=\"num\">Dólares: regla que "
                      "menos falla</th><th>Se recomienda</th>",
                      "<td>HOBBIES_2, ocio</td><td class=\"num\">50,2</td><td class=\"num\">50,1</td>",
                      "Los otros cuatro (FOODS_1, FOODS_2, HOBBIES_1 y HOUSEHOLD_1), en el anexo: el modelo falla "
                      "menos en todos.",
                      "Pedir con la previsión del modelo, también en los festivos grandes; en HOBBIES_2, con la media "
                      "de los últimos 28 días",
                      "la regla es la que menos falla en cada tienda: la media del mismo día de las 4 semanas "
                      "anteriores en todas, salvo WI_2 en unidades, donde es la media de los últimos 28 días",
                      "la regla es la que menos falla en cada departamento: la media del mismo día de las 4 semanas "
                      "anteriores en todos, salvo FOODS_1 en dólares, donde es la media de los últimos 28 días",
                      "Con ellas, 2,28, en el año de comprobación", "Con ellas, 2,06, en el año de comprobación",
                      "Dólares que se queda corta por cada 100 vendidos",
                      "El 27,7 % y el 32,2 % de la cadena se calculan igual."):
            caso(f"30. el informe dice «{frase}»", frase in texto)
        for vieja in ("Unidades: modelo y regla que menos falla", "Los otros cuatro, en el anexo",
                      "<th>Grupo</th>", "Con ellas, 2,28<"):
            caso(f"30. ya no dice «{vieja}» (versión 4)", vieja not in texto)
        caso("30. ninguna página pasa de 650 px", all(p.alto() <= 650 for p in inf.paginas))
        caso("30. el resumen no pasa de 150 palabras (T2)", m.palabras(inf.paginas[0]) <= 150)

    # 39. La tercera pasada (propuesta_informe_final_v5.md §2 bis): 4b, 7b, 15b, 20b y del 29 al 38
    if monta:
        for frase in ("en 13 de 13 en dólares. En HOBBIES_2, de venta intermitente, falla menos la media de los "
                      "últimos 28 días.",
                      "volver a medir. Qué parte de la venta de Walmart suman no se puede saber</td>",
                      "Dólares que falla cada tienda por cada 100 vendidos, a 28 días, del 23/05/2015 al 22/05/2016. "
                      "En naranja, CA_4, donde empatan.",
                      "en unidades ganó en 9 de 13 pruebas, una menos de las 10 que hacían falta.",
                      "Hacían falta 10, así que en unidades no se confirmó.",
                      "Ese mínimo se fijó antes de medir.",
                      "En el año de comprobación, las tres combinaciones que más aportan son de alimentación en WI_2 y "
                      "WI_3.",
                      "Combinaciones en que una regla falla menos que el modelo en el año de comprobación, en unidades",
                      "9,5 dólares por cada 100 frente a 17,8 de la media del mismo día de las 4 semanas anteriores.",
                      "<p class=\"numero\">0,5</p><p class=\"etiqueta\">Dólares que se queda corta por cada 100 "
                      "vendidos</p><p class=\"contexto\">La media del mismo día de las 4 semanas anteriores, 1,4</p>",
                      "La media de los últimos 28 días, +11,8"):
            caso(f"39. el informe dice «{frase}»", frase in texto)
        for vieja in ("una menos de las que pide la regla", "La regla pide 10", "La regla se fijó antes de medir",
                      "En California casi empatan", "Unidades, regla", "de 17,8 de la regla", "frente a 17,8 de la regla",
                      "en todas las tiendas, con CA_4 empatada", "La regla que menos falla, −1,4",
                      "La regla que menos falla, +11,8", "van aquí", "su año:",
                      "En naranja, la tienda en que la regla falla menos", "Falló menos que la regla en los tres"):
            caso(f"39. ya no dice «{vieja}»", vieja not in texto)

    # 44. La cuarta pasada (propuesta_informe_final_v5.md §2 ter): 38b, 39, 40, 41 y 42
    if monta:
        for frase in ("Tabla de cifras. Cada cifra con su fichero de informes. Las tablas largas van en las dos páginas "
                      "siguientes.",
                      "<th>Cifra</th><th>Fichero de informes</th></tr>",
                      "se pasa lo mismo que la media del mismo día de las 4 semanas anteriores en unidades",
                      "En Acción de Gracias, 18,8 unidades por cada 100 frente a 25,5 de la media de los últimos 28 "
                      "días.",
                      "En Año Nuevo, 14,0 frente a 20,5 de esa misma regla.",
                      "en las tres vísperas falló menos que la regla que menos falla en cada una"):
            caso(f"44. el informe dice «{frase}»", frase in texto)
        for vieja in ("Fecha de los datos", "periodo de sus datos", "(págs. 4, 10 y 12)",
                      "se pasa lo mismo que la regla en unidades", "en cada una: en Acción de Gracias"):
            caso(f"44. ya no dice «{vieja}»", vieja not in texto)

    # 40. Las reglas de los festivos: Acción de Gracias, los últimos 28 días; Navidad y Año Nuevo, la del mismo día
    def regla_festivo(nombre, regla):
        """Cambia la regla que menos falla en la víspera de un festivo, con su fila de errores."""
        def cambio(p):
            f = de_lista(p["reentrenado"]["unidades"]["festivos"]["por_origen"], "festivo", nombre)
            f["errores"][1]["prevision"], f["regla_que_menos_falla"] = regla, regla
        return cambio
    caso("40. para si en Acción de Gracias la regla que menos falla es la del mismo día",
         para(m.construir, roto(entradas, regla_festivo("Acción de Gracias", "media_mismo_dia_4_semanas"))))
    caso("40. para si en Navidad la regla que menos falla es la de los últimos 28 días",
         para(m.construir, roto(entradas, regla_festivo("Navidad", "media_28_dias"))))
    caso("40. para si en Año Nuevo la regla que menos falla es la de los últimos 28 días",
         para(m.construir, roto(entradas, regla_festivo("Año Nuevo", "media_28_dias"))))

    # 41. El exceso en dólares de la página 11: la media del mismo día también se queda corta
    def regla_d_se_pasa(p):
        """En dólares, la media del mismo día se pasa +0,4."""
        x = p["reentrenado"]["dolares"]
        de_lista(x["errores"]["todas"], "prevision", "media_mismo_dia_4_semanas")["sesgo"] = 0.4
        x["exceso"]["valores"]["media_mismo_dia_4_semanas"] = 0.4
    caso("41. para si en dólares la media del mismo día se pasa en vez de quedarse corta",
         para(m.construir, roto(entradas, regla_d_se_pasa)))

    # 42. «frente a 17,8 de la media del mismo día…»: en dólares, en WI_2 la regla que menos falla es esa
    caso("42. para si en dólares WI_2 tiene la media de los últimos 28 días",
         para(m.construir, roto(entradas, grupo_pf("dolares", "tienda", "WI_2", regla_que_menos_falla="media_28_dias"))))

    # 43. paginas() con tres páginas, todas entre las que se comprueban con el panel
    caso("43. paginas(4, 10, 12) escribe «(págs. 4, 10 y 12)»",
         not para(m.paginas, 4, 10, 12) and m.paginas(4, 10, 12) == "(págs. 4, 10 y 12)")
    caso("43. paginas() para si una de las tres no se comprueba con el panel", para(m.paginas, 4, 10, 16))

    # 45. «de esa misma regla»: Año Nuevo tiene la misma regla que Navidad. Con la de los 28 días en Año Nuevo, para
    caso("45. para si en Año Nuevo la regla que menos falla no es la misma que en Navidad",
         para(m.construir, roto(entradas, regla_festivo("Año Nuevo", "media_28_dias"))))
    # El 25 de diciembre, el día de cierre, queda fuera del error
    caso("45. para si el 25 de diciembre no queda fuera del error",
         para(m.construir, roto(entradas, lambda p: p["reentrenado"]["dolares"].update(dias_fuera_del_error=[]))))

    # 46. La quinta pasada (propuesta_informe_final_v5.md §2 quater): 43, 44 y 45
    if monta:
        for frase in ("<p>Estas cifras son de 2011 a mayo de 2014, con 3 años de cada festivo. El mes pesa poco y el "
                      "precio casi no cambia.</p><p>En el último año",
                      "En Navidad, 18,4 frente a 21,2 de la media del mismo día de las 4 semanas anteriores, sin contar "
                      "el día de cierre.",
                      "Al sumar, falla 4,2 unidades por cada 100 en la cadena; en dólares falla menos que la media del "
                      "mismo día de las 4 semanas anteriores en 9 de 10 tiendas y en CA_4 empatan",
                      "Falla menos en 12 de 13 pruebas en unidades y en las tres vísperas de festivo (págs. 1, 10 y 12)"):
            caso(f"46. el informe dice «{frase}»", frase in texto)
        for vieja in ("En Navidad la tienda cierra", "pruebas del último año guardado y en las tres vísperas",
                      "en dólares falla menos que la regla en 9 de 10 tiendas"):
            caso(f"46. ya no dice «{vieja}»", vieja not in texto)

    # 47. «sin contar el día de cierre»: en la víspera de Navidad se miden 9 días y falta solo el 25 de diciembre
    def navidad_con_25(p):
        """La víspera de Navidad mide también el 25 de diciembre: los 10 días."""
        f = de_lista(p["reentrenado"]["unidades"]["festivos"]["por_origen"], "festivo", "Navidad")
        f["dias"] = sorted(f["dias"] + ["2015-12-25"])
    caso("47. para si en la víspera de Navidad se mide también el 25 de diciembre",
         para(m.construir, roto(entradas, navidad_con_25)))

    # 48. En dólares, en todas las tiendas la regla es la media del mismo día (página 2, respuesta 3)
    caso("48. para si en dólares TX_2 tiene la media de los últimos 28 días",
         para(m.construir, roto(entradas, grupo_pf("dolares", "tienda", "TX_2", regla_que_menos_falla="media_28_dias"))))

    # 30, sigue: el plazo en las notas, la página del informe ejecutivo y las tablas largas del anexo
    if monta:
        # El plazo, en la nota de las tablas de las páginas 6 y 10 y de las dos tablas del anexo (la 4, si cabe)
        caso("30. «Unidades a 10 días; dólares a 28.» en al menos cuatro notas de tabla",
             texto.count("Unidades a 10 días; dólares a 28.") >= 4)
        # La nota del informe ejecutivo vuelve al anexo, a su página
        por_panel = {p.panel: t for p, (_, t) in zip(inf.paginas, m.paginas_visibles(texto))}
        caso("30. la nota del informe ejecutivo ya no está en las decisiones",
             "La primera desarrolla" not in por_panel.get("Decisiones propuestas", "La primera desarrolla"))
        caso("30. la nota del informe ejecutivo está en su página del anexo",
             "La primera desarrolla las acciones 1 y 2"
             in por_panel.get("Las decisiones y el informe ejecutivo", ""))
        # Las tablas largas van en las dos páginas que siguen a la tabla de cifras
        anexo = [p.panel for p in inf.paginas if p.tipo == "anexo"]
        caso("30. las dos páginas que siguen a la tabla de cifras son las tablas largas",
             "Tabla de cifras" in anexo and anexo[anexo.index("Tabla de cifras") + 1:anexo.index("Tabla de cifras") + 3]
             == ["Los otros cuatro departamentos", "Las diez tiendas"])
        caso("30. quince páginas antes del anexo también en la versión 5",
             sum(1 for p in inf.paginas if p.tipo != "anexo") == 15)

    # 31. Wisconsin, el estado con más diferencia en unidades; California, el de menos
    caso("31. para si en unidades Texas tiene más diferencia que Wisconsin",
         para(m.construir, roto(entradas, grupo_pf("unidades", "estado", "TX", error_regla=12.0))))
    caso("31. para si en unidades Texas tiene menos diferencia que California",
         # 7,354 − 7,30 = 0,05, menos que los 0,15 de California
         para(m.construir, roto(entradas, grupo_pf("unidades", "estado", "TX", error_modelo=7.30))))

    # 32. La regla que menos falla en cada tienda: la media del mismo día en todas, salvo WI_2 en unidades
    caso("32. para si en unidades WI_2 tiene también la media del mismo día",
         para(m.construir, roto(entradas, grupo_pf("unidades", "tienda", "WI_2",
                                                   regla_que_menos_falla="media_mismo_dia_4_semanas"))))
    caso("32. para si en dólares CA_1 tiene la media de los últimos 28 días",
         para(m.construir, roto(entradas, grupo_pf("dolares", "tienda", "CA_1", regla_que_menos_falla="media_28_dias"))))

    # 33. La regla que menos falla en los otros cuatro departamentos: la media del mismo día, salvo FOODS_1 en dólares
    def regla_dep(o, nombre, regla):
        """Cambia la regla que menos falla de un departamento del modelo en uso."""
        nombres = {"media_mismo_dia_4_semanas": "la media del mismo día de las 4 semanas anteriores",
                   "media_28_dias": "la media de los últimos 28 días"}

        def cambio(p):
            d = de_lista(p["reentrenado"][o]["recomendacion_por_departamento"], "departamento", nombre)
            d["regla_que_menos_falla"], d["regla_que_menos_falla_nombre"] = regla, nombres[regla]
        return cambio
    caso("33. para si en dólares FOODS_1 tiene la media del mismo día",
         para(m.construir, roto(entradas, regla_dep("dolares", "FOODS_1", "media_mismo_dia_4_semanas"))))
    caso("33. para si en unidades HOBBIES_1 tiene la media de los últimos 28 días",
         para(m.construir, roto(entradas, regla_dep("unidades", "HOBBIES_1", "media_28_dias"))))

    # 34. Los otros cuatro departamentos: el modelo falla menos en todos
    def dep_pierde(o, nombre):
        """El modelo falla más que la regla en un departamento, que sigue recomendando el modelo."""
        def cambio(p):
            d = de_lista(p["reentrenado"][o]["recomendacion_por_departamento"], "departamento", nombre)
            d["error_modelo"] = d["error_regla"] + 1.0
        return cambio
    caso("34. para si en dólares el modelo falla más en HOUSEHOLD_1",
         para(m.construir, roto(entradas, dep_pierde("dolares", "HOUSEHOLD_1"))))
    caso("34. para si en unidades la regla falla menos también en FOODS_1 (HOBBIES_2 ya no es el único)",
         para(m.construir, roto(entradas, dep_pierde("unidades", "FOODS_1"))))

    # 35. HOBBIES_2 en la tabla de la página 10, a un decimal: el modelo y la regla tienen que leerse distintos
    def h2_igual(p):
        """En unidades, 50,13 frente a 50,11: a un decimal, 50,1 y 50,1."""
        de_lista(p["reentrenado"]["unidades"]["recomendacion_por_departamento"], "departamento",
                 "HOBBIES_2")["error_modelo"] = 50.1328
    caso("35. para si HOBBIES_2 a un decimal se lee igual en el modelo y en la regla",
         para(m.construir, roto(entradas, h2_igual)))

    # 36. El modelo en uso le gana al suavizado en las pruebas que pide la regla
    caso("36. para si en unidades le gana al suavizado solo en 9 de 13",
         para(m.construir, roto(entradas, lambda p: p["reentrenado"]["unidades"]["suavizado"].update(
             origenes_que_gana=9))))

    # 37. «Las barras son del modelo en uso»: el del año de comprobación falló más que el que está en las barras
    caso("37. para si el modelo del año de comprobación falló menos que el modelo en uso",
         para(m.construir, roto(entradas, lambda p: p["tal_como_esta"]["unidades"]["veredicto"].update(
             error_modelo=14.0))))

    # 38. Las quince páginas del panel se comprueban, también las que solo cita «el detalle, en las páginas 3 a 15»
    if monta:
        paneles = [p.panel for p in inf.paginas]
        caso("38. para si la página 11 del panel deja de ser «El exceso»",
             para(m.comprobar_referencias, paneles[:10] + ["Otra"] + paneles[11:]))
        caso("38. para si la página 3 del panel deja de ser «Qué se prevé»",
             para(m.comprobar_referencias, paneles[:2] + ["Otra"] + paneles[3:]))


def main():
    """Carga el script, lanza los casos y borra la carpeta temporal."""
    caso("1. el script existe", SCRIPT.is_file())
    if not SCRIPT.is_file():
        print(f"{len(FALLOS)} FALLA")
        sys.exit(1)
    m = cargar()
    caso("1. se importa sin ejecutar nada (tiene main y construir)", hasattr(m, "main") and hasattr(m, "construir"))
    try:
        casos(m)
    finally:
        # La carpeta temporal no se queda en el caso
        shutil.rmtree(TMP, ignore_errors=True)
    caso("la carpeta temporal se ha borrado", not TMP.exists())
    print(f"{len(FALLOS)} FALLA" if FALLOS else "Todo en verde")
    sys.exit(1 if FALLOS else 0)


if __name__ == "__main__":
    main()
