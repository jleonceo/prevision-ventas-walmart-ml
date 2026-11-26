"""Prueba de scripts/19_contrato_produccion.py, con datos pequeños escritos aquí.

No lee ningún dato, informe ni documento vivo del caso: monta en tests/tmp_contrato/ una carpeta con la estructura del
caso (los cinco JSON que lee el script, los planteamientos y un registro de transformaciones de juguete), ejecuta el
script sobre ella con --raiz y la borra al acabar. El registro de juguete se escribe con las fichas y las frases que el
script cita, sacadas de su propio catálogo; el estado de cada documento (aprobado, veredicto) se escribe aquí y no se
hereda de los reales (programacion-del-caso, error 31).

Los casos:
  1. base: un ganador pequeño por objetivo, con una columna de cada clase de finalista. Es el control que no debe
     disparar: el script acaba esperando al responsable del caso (PARADO con puerta_de_juan), sale con 0, deja el contrato y el JSON,
     todas las validaciones de la parte 1 en verde, cada columna con su finalista y cada cadena con sus clases;
  2. una columna del ganador que no sale de ninguna finalista de la matriz: ERROR, sin contrato;
  3. una finalista sin cadena completa: falta en el registro una ficha de su cadena, o la matriz trae una variable sin
     cadena en el catálogo: ERROR, sin contrato;
  4. un paso que aprende ajustado antes de la partición: con el preprocesador ajustado con más filas que el
     entrenamiento (script entero) y con una cadena que pone un paso que aprende delante de la partición (función):
     ERROR;
  5. un campo vacío en el contrato: el algoritmo del ganador vacío (script entero) y un campo vacío suelto (función):
     ERROR;
  6. al empezar: el veredicto no es «gana», la huella de la búsqueda no es la que validó la validación o el ganador
     no está aprobado: PARADO sin puerta, sale con 1 y no escribe contrato;
  7. el script no escribe ninguna validación con su resultado puesto (error 24);
  8. la aprobación del responsable del caso: con la ficha del contrato aprobado en el registro, el contrato y el JSON dicen «aprobado por
     el responsable del caso el 25/11/2026, «Apruebo el contrato»»; sin ella, siguen sin aprobar (el caso 1);
  9. la parte 2 (petición 27): con el contrato aprobado y lo que dejan el reentreno, la prueba por otro camino y el
     ensayo de la ejecución, el JSON trae codigo, reentreno, prueba_por_otro_camino y las validaciones de la parte 2
     calculadas, con el lote pendiente; una validación de la parte 2 en rojo da ERROR; sin la aprobación, la parte 2 no
     se rellena aunque se le pasen los ficheros;
 11. el lote (petición 28): con --lote, el JSON trae el lote (ruta, filas que entran y salen, sin puntuar por motivo,
     historial) y la prueba por otro camino sobre él, con las validaciones otro_camino_lote y filas_lote calculadas;
     la prueba del lote que no sale en rojo con la salida estropeada, o un lote con filas de menos, da ERROR; con
     --reentrenado, el reentreno trae comparacion_con_el_en_uso y la pregunta del modelo en uso nombra los dos; el
     contrato ya no dice que no hay lote; y queda informes/preproduccion.md, generado del JSON, con los apartados de
     resultado.md en su orden y sin «, y» ni rayas;
 12. el modelo en uso (petición 29): con la configuración de producción que nombra el reentrenado y la aprobación de
     el responsable del caso, P-02 pasa a decisiones como resuelta, sin pendientes, y el estado es OK; el JSON y el informe dicen el
     modelo en uso; la prueba por otro camino sobre el lote del reentrenado entra con su rojo. Sin la aprobación, P-02
     sigue pendiente; un modelo en uso que no es ninguno de los medidos, o la prueba del reentrenado que no sale en
     rojo con la previsión estropeada, dan ERROR.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "19_contrato_produccion.py"
TMP = RAIZ / "tests" / "tmp_contrato"
FALLOS = []
CONTRATO_REL = Path("config") / "modelo" / "contrato_produccion.md"
JSON_REL = Path("informes") / "preproduccion.json"

# Un ganador pequeño: una columna de cada clase de finalista (codificada, tal cual, evento, escalada y retardo)
COLUMNAS_BASE = ["store_id_ohe_CA_1", "store_id_ohe_TX_1", "snap", "evento_Christmas",
                 "precio_medio_semana_anterior_ss", "<obj>_lag_1_rs", "<obj>_media_7_rs"]
FILAS_ENTRENAMIENTO = 82250


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar_script():
    """Importa el script que se prueba (su trabajo está bajo __main__)."""
    spec = importlib.util.spec_from_file_location("contrato_19", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def matriz():
    """Las variables de la matriz que usa el ganador pequeño, con la forma de informes/preparacion.json."""
    return [
        {"variable": "store_id", "rama": "una columna por categoría, sin drop", "escalado": "ninguno",
         "salida": ["store_id_ohe_<categoría>"], "entra": True},
        {"variable": "snap", "rama": "tal cual", "escalado": "ninguno", "salida": ["snap"], "entra": True},
        {"variable": "evento_<nombre>", "rama": "tal cual", "escalado": "ninguno",
         "salida": ["evento_Christmas", "evento_Easter"], "entra": True},
        {"variable": "precio_medio_semana_anterior", "rama": "tal cual", "escalado": "StandardScaler",
         "salida": ["precio_medio_semana_anterior_ss"], "entra": True},
        {"variable": "<obj>_lag_1", "rama": "tal cual", "escalado": "RobustScaler", "salida": ["<obj>_lag_1_rs"],
         "entra": True},
        {"variable": "<obj>_media_7", "rama": "tal cual", "escalado": "RobustScaler", "salida": ["<obj>_media_7_rs"],
         "entra": True},
    ]


APROBACION = ("### R-021 · 25/11/2026 · contrato de producción aprobado\n\n"
              "4. **Decisión:** El responsable del caso, 25/11/2026: «Apruebo el contrato». Con él, las tres diferencias.\n")
TEXTO_APROBADO = "aprobado por el responsable del caso el 25/11/2026, «Apruebo el contrato»"


def registro(m, quitar=()):
    """Un registro de juguete con las fichas y las frases que cita el catálogo del script, menos las de `quitar`."""
    citas = {}
    for paso in m.PASOS.values():
        citas.setdefault(paso["ficha"], []).append(paso["cita"])
    for cita in m.CITAS_DE_CREACION.values():
        citas.setdefault(cita[0], []).append(cita[1])
    citas.setdefault("R-011", []).append(m.CITA_PREPROCESADOR)
    for obj in ("unidades", "dolares"):
        ficha = m.PASOS[f"retardos_{obj}"]["ficha"]
        # Como el registro real: los retardos de 1 a 7 van como tramo; los de 14, 21 y 28, uno a uno
        citas[ficha] += [f"`{obj}_lag_1` a `{obj}_lag_7`"] + [f"{obj}_lag_{k}" for k in (14, 21, 28)]
        citas[ficha] += [f"{obj}_media_{w}" for w in (7, 28)]
    lineas = ["# Registro de transformaciones · juguete", "", "| Nº | Qué |", "|---|---|"]
    for ficha in sorted(c for c in citas if c.startswith("T-") and c not in quitar):
        lineas.append(f"| {ficha} | {' · '.join(citas[ficha])} |")
    for ficha in sorted(c for c in citas if c.startswith("R-") and c not in quitar):
        lineas += ["", f"### {ficha} · 24/11/2026 · ficha de juguete", "", " · ".join(citas[ficha])]
    return "\n".join(lineas) + "\n"


def ganador(objetivo, columnas, algoritmo="HistGradientBoosting"):
    """El ganador de un objetivo con la forma de informes/busqueda.json."""
    return {"algoritmo": algoritmo, "clase": "HistGradientBoostingRegressor",
            "hiperparametros": {"learning_rate": 0.1, "max_iter": 500, "min_samples_leaf": 205, "max_depth": None,
                                "l2_regularization": 0, "random_state": 42, "early_stopping": False},
            "buscados": {"learning_rate": 0.1, "max_iter": 500, "min_samples_leaf": 205, "max_depth": None,
                         "l2_regularization": 0},
            "semilla": 42, "columnas": [c.replace("<obj>", objetivo) for c in columnas],
            "n_columnas": len(columnas), "preprocesador": "scripts/preparacion_prevision.py",
            "reajuste": {"filas_ajuste": FILAS_ENTRENAMIENTO}}


def montar(nombre, m, columnas=None, quitar=(), filas_preprocesador=FILAS_ENTRENAMIENTO, veredicto="gana",
           huella_distinta=False, aprobado="el responsable del caso, 25/11/2026, «Apruebo el ganador»", algoritmo="HistGradientBoosting",
           variables_matriz=None, aprobado_contrato=False):
    """Carpeta de prueba con los cinco JSON, los planteamientos y el registro; devuelve su raíz.

    aprobado_contrato: añade al registro la ficha del contrato aprobado; el estado se escribe aquí (error 31).
    """
    raiz = TMP / nombre
    for carpeta in ("informes", "config/modelo", "config/metodo"):
        (raiz / carpeta).mkdir(parents=True, exist_ok=True)
    columnas = columnas or COLUMNAS_BASE
    busqueda = {"fecha_datos": "2015-05-22", "resultado": {"estado": "PARADO"},
                "ganador": {o: ganador(o, columnas, algoritmo) for o in ("unidades", "dolares")}}
    ruta_b = raiz / "informes" / "busqueda.json"
    ruta_b.write_text(json.dumps(busqueda, ensure_ascii=False), encoding="utf-8")
    sha = "0" * 64 if huella_distinta else hashlib.sha256(ruta_b.read_bytes()).hexdigest()
    validacion = {"fecha_datos": "2015-05-22", "resultado": {"estado": "PARADO"},
                  "receta": {"ruta": "informes/busqueda.json", "huella": {"esperada": sha},
                             "ganador": {o: {"aprobado_por": aprobado} for o in ("unidades", "dolares")}},
                  "validacion": {o: {"horizonte": h, "veredicto": {"veredicto": veredicto}}
                                 for o, h in (("unidades", 10), ("dolares", 28))}}
    (raiz / "informes" / "validacion.json").write_text(json.dumps(validacion, ensure_ascii=False), encoding="utf-8")
    preparacion = {"fecha_datos": "2015-05-22",
                   "matriz": {"ruta": "config/modelo/matriz_transformaciones.md", "aprobada_por": "el responsable del caso",
                              "fecha": "2026-11-24", "variables": variables_matriz or matriz()},
                   "preprocesadores": {o: {"remainder": "drop", "ajustado_con_filas": filas_preprocesador}
                                       for o in ("unidades", "dolares")}}
    (raiz / "informes" / "preparacion.json").write_text(json.dumps(preparacion, ensure_ascii=False), encoding="utf-8")
    preseleccion = {"fecha_datos": "2015-05-22", "ficha_registro": "R-018"}
    (raiz / "informes" / "preseleccion.json").write_text(json.dumps(preseleccion), encoding="utf-8")
    variables = {"fecha_datos": "2015-05-22",
                 "filas_quitadas": {"filas_antes": 84700, "filas_quitadas": 2450,
                                    "filas_despues": FILAS_ENTRENAMIENTO},
                 "parametros": [{"nombre": "retardos", "valor": [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]},
                                {"nombre": "ventanas de las medias", "valor": [7, 28]},
                                {"nombre": "dias_sin_historia", "valor": 35},
                                {"nombre": "semanas_previas_con_precio", "valor": 4}],
                 "eventos": {"numero": 2, "lista": ["Christmas", "Easter"]},
                 "particion": {"desarrollo": {"desde": "2011-03-05", "hasta": "2014-05-22"}}}
    (raiz / "informes" / "variables_modelo.json").write_text(json.dumps(variables), encoding="utf-8")
    planteamientos = ("# Planteamientos de juguete\n\n**Veredicto de la validación (el responsable del caso, 25/11/2026, «Sí, apruebo el "
                      "veredicto»):** el modelo gana en los dos objetivos.\n")
    (raiz / "config" / "metodo" / "04_planteamientos.md").write_text(planteamientos, encoding="utf-8")
    texto_registro = registro(m, quitar) + ("\n" + APROBACION if aprobado_contrato else "")
    (raiz / "config" / "modelo" / "registro-transformaciones.md").write_text(texto_registro,
                                                                                       encoding="utf-8")
    return raiz


def montar_parte_2(raiz, bit_a_bit=True, estropeada_coincide=False, ejecutar_quita=False):
    """Lo que dejan el reentreno, la prueba por otro camino y el ensayo, de juguete; devuelve (reentreno, ensayo).

    bit_a_bit: el reentreno coincide con la validación. estropeada_coincide: la prueba con la salida estropeada sale en
    verde (no debería). ejecutar_quita: produccion/ejecutar.py llama a un paso que quita filas.
    """
    reentreno = raiz / "modelos" / "reentrenos" / "2026-11-25"
    ensayo = raiz / "data" / "predicciones" / "2026-11-25"
    reentreno.mkdir(parents=True, exist_ok=True)
    ensayo.mkdir(parents=True, exist_ok=True)
    (raiz / "produccion").mkdir(parents=True, exist_ok=True)
    datos_reentreno = {
        "script": "produccion/reentrenar.py", "estado": "OK", "modo": "comprobacion",
        "tabla": {"ruta": "data/processed/hechos_modelo_entrenamiento.parquet", "sha256": "a" * 64, "filas": 82250,
                  "fecha_corte": "2014-05-22"},
        "filas_entrada": 82250,
        "filas_quitadas": [{"motivo": "objetivo sin conocer", "ficha": "R-010", "fecha": "2014-05-22", "filas": 0,
                            "casos_del_evento": None},
                           {"motivo": "sin la historia que piden las variables", "ficha": "R-017", "filas": 0}],
        "filas_ajuste": 82250, "ruta": "modelos/reentrenos/2026-11-25",
        "modelo_en_uso": {"existia": False, "de_donde": "ninguno: el primer reentreno se compara con la validación"},
        "comparacion_con_el_en_uso": {"periodo": None, "filas": None, "medida": None, "en_uso": None,
                                      "reentrenado": None},
        "comprobacion": {"origenes": 13, "tolerancia": 1e-12,
                         "por_objetivo": {o: {"filas": 9100 if o == "unidades" else 25480,
                                              "diferencia_maxima": 0.0 if bit_a_bit else 3.0,
                                              "coincide": bit_a_bit} for o in ("unidades", "dolares")}},
        "cambia_con_datos_nuevos": {"por_objetivo": {o: {"cambia": True, "diferencia_maxima": 1.5}
                                                     for o in ("unidades", "dolares")}},
        "ramas_event_name": {"van": False, "motivo": "sin ellas la previsión sale igual"},
        "pasos_que_quitan_filas": ["quitar_sin_objetivo", "quitar_sin_historia"],
        "validaciones": {"columnas_del_contrato": True, "bit_a_bit": bit_a_bit, "cambia_con_datos_nuevos": True}}
    (reentreno / "reentreno.json").write_text(json.dumps(datos_reentreno, ensure_ascii=False), encoding="utf-8")
    for nombre, coincide in (("prueba_por_otro_camino.json", True),
                             ("prueba_por_otro_camino_estropeada.json", estropeada_coincide)):
        (reentreno / nombre).write_text(json.dumps({"coincide": coincide, "tolerancia": 1e-12, "origenes": 13}),
                                        encoding="utf-8")
    resumen = {"script": "produccion/ejecutar.py", "estado": "OK", "ensayo": True, "origen": "2014-05-22",
               "validaciones": {"filas_ejecucion": True, "ficha_cuadra": True, "periodo_que_toca": True,
                                "sin_vacias_sin_motivo": True, "sin_negativas": True}}
    (ensayo / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False), encoding="utf-8")
    codigo = "def principal():\n    return 1\n" + ("    quitar_sin_historia(tabla)\n" if ejecutar_quita else "")
    (raiz / "produccion" / "ejecutar.py").write_text(codigo, encoding="utf-8")
    return reentreno, ensayo


def montar_lote(raiz, estropeada_coincide=False, filas_salida=42560):
    """Lo que dejan el lote de la prueba final y su prueba por otro camino, de juguete; devuelve la carpeta."""
    lote = raiz / "data" / "processed" / "prueba_final"
    (lote / "tal_como_esta").mkdir(parents=True, exist_ok=True)
    resumen = {"variante": "tal_como_esta", "modelos": "modelos/reentrenos/2026-11-25",
               "origenes": [{"origen": "2015-05-22", "prueba": "ordinaria"}, {"origen": "2015-11-25", "prueba": "festivo"}],
               "filas_entrada": {"venta_productos_tienda_por_origen": 5000, "ejecuciones": 16, "filas_a_prever": 42560},
               "filas_salida": filas_salida, "sin_prevision": {}}
    (lote / "tal_como_esta" / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False), encoding="utf-8")
    for nombre, coincide in (("prueba_por_otro_camino.json", True),
                             ("prueba_por_otro_camino_estropeada.json", estropeada_coincide)):
        (lote / nombre).write_text(json.dumps({"coincide": coincide, "tolerancia": 1e-12, "origenes": 16,
                                               "por_objetivo": {"unidades": {"filas": 11200},
                                                                "dolares": {"filas": 31360}}}), encoding="utf-8")
    return lote


def montar_reentrenado(raiz):
    """La ficha de un reentrenado de juguete con su comparación con el candidato; devuelve la carpeta."""
    carpeta = raiz / "modelos" / "reentrenos" / "2015-05-22"
    carpeta.mkdir(parents=True, exist_ok=True)
    ficha = {"script": "produccion/reentrenar.py", "estado": "AVISO", "filas_ajuste": 107800,
             "comparacion_con_el_en_uso": {"periodo": "2015-05-23 a 2016-05-22", "filas": {"unidades": 9100},
                                           "medida": "error de reglas, apartado 6", "en_uso": {"unidades": {"error_modelo": 15.3}},
                                           "reentrenado": {"unidades": {"error_modelo": 14.5}}}}
    (carpeta / "reentreno.json").write_text(json.dumps(ficha, ensure_ascii=False), encoding="utf-8")
    return carpeta


def ejecutar(raiz, extra=()):
    """Ejecuta el script sobre la carpeta de prueba, como proceso aparte y con -W error."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz), *map(str, extra)],
                          capture_output=True, text=True, encoding="utf-8", env=entorno, timeout=300)
    ruta = raiz / JSON_REL
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


# ── 2. Casos con el script entero ──────────────────────────────────────────────
def probar_base(m):
    """Caso 1: el control que no debe disparar."""
    raiz = montar("base", m)
    codigo, d, salida = ejecutar(raiz)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "PARADO" and d.get("puerta_de_juan") is True,
              f"base: espera al responsable del caso con PARADO y puerta, sale con 0 ({codigo}; {salida[-600:] if codigo else ''})")
    if d is None:
        return
    val = d.get("validaciones", {})
    for nombre in ("columnas_con_finalista", "cadenas_completas", "aprende_despues_de_la_particion",
                   "sin_campos_vacios"):
        comprobar(val.get(nombre) is True, f"base: {nombre} en verde ({val.get(nombre)})")
    comprobar((raiz / CONTRATO_REL).exists(), "base: deja el contrato")
    comprobar(d["contrato"]["aprobado_por"] == "" and d["contrato"]["ruta"] == CONTRATO_REL.as_posix(),
              "base: el contrato sale sin aprobar, con su ruta")
    for obj in ("unidades", "dolares"):
        o = d["objetivos"][obj]
        cols = [c for f in o["finalistas"] for c in f["columnas_del_modelo"]]
        comprobar(sorted(cols) == sorted(c.replace("<obj>", obj) for c in COLUMNAS_BASE),
                  f"{obj}: cada columna del ganador sale de una finalista ({len(cols)})")
        nombres = [f["variable"] for f in o["finalistas"]]
        comprobar(nombres == ["store_id", "snap", "evento_<nombre>", "precio_medio_semana_anterior",
                              f"{obj}_lag_1", f"{obj}_media_7"],
                  f"{obj}: seis finalistas, en el orden de la matriz ({nombres})")
        por_variable = {f["variable"]: f for f in o["finalistas"]}
        clases = [p["clase"] for p in por_variable[f"{obj}_lag_1"]["cadena"]]
        comprobar("quita filas" in clases and "necesita otras filas" in clases and clases[-1] == "aprende",
                  f"{obj}: el retardo de 1 día quita filas, necesita otras filas y acaba en el modelo ({clases})")
        fichas = [p["ficha"] for p in por_variable[f"{obj}_lag_1"]["cadena"]]
        comprobar(m.PASOS[f"retardos_{obj}"]["ficha"] in fichas and "R-017" in fichas and "R-010" in fichas,
                  f"{obj}: la cadena del retardo trae su ficha, la de los 35 días y la de la partición ({fichas})")
        evento = por_variable["evento_<nombre>"]["cadena"]
        lista = [p for p in evento if p["ficha"] == "R-015"]
        comprobar([p["clase"] for p in lista] == ["aprende", "no aprende"],
                  f"{obj}: la lista de eventos aprende y la columna de cada evento no ({[p['clase'] for p in lista]})")
        pre = [p for p in por_variable["snap"]["cadena"] if p["etapa"] == "preprocesador"]
        comprobar([p["clase"] for p in pre] == ["no aprende"], f"{obj}: snap pasa tal cual por el preprocesador")
        pre = [p for p in por_variable["store_id"]["cadena"] if p["etapa"] == "preprocesador"]
        comprobar([p["clase"] for p in pre] == ["aprende"], f"{obj}: la tienda se codifica y eso aprende")
        comprobar(o["receta"]["algoritmo"] == "HistGradientBoosting" and o["receta"]["semilla"] == 42,
                  f"{obj}: la receta trae el algoritmo y la semilla del ganador")
        comprobar(o["prevision"]["horizonte_dias"] == (10 if obj == "unidades" else 28)
                  and o["prevision"]["historia_minima_dias"] == 28,
                  f"{obj}: horizonte y historia mínima leídos de los JSON ({o['prevision'].get('horizonte_dias')})")
    distintos = {x["paso"] for x in d["distinto_de_lo_esperado"]}
    comprobar("eventos_lista" in distintos and "particion" in distintos,
              f"base: la lista de eventos y la partición salen como distintas de lo esperado ({sorted(distintos)})")
    comprobar(d["fecha_datos"] == "2015-05-22" and d["entorno"].get("scikit-learn"),
              "base: fecha_datos y versiones en el JSON")
    texto = (raiz / CONTRATO_REL).read_text(encoding="utf-8")
    comprobar(", y " not in texto and "—" not in texto and "–" not in texto,
              "base: el contrato no trae «, y» ni rayas")
    for apartado in ("## Lo que se pide aprobar", "## Los dos modelos", "## Las finalistas",
                     "## Los pasos por clase", "## La cadena de cada finalista", "## La previsión día a día",
                     "## Datos personales", "## Límites"):
        comprobar(apartado in texto, f"base: el contrato tiene el apartado «{apartado}»")


def probar_columna_sin_finalista(m):
    """Caso 2: una columna del ganador que no sale de ninguna finalista para con ERROR."""
    raiz = montar("sin_finalista", m, columnas=COLUMNAS_BASE + ["columna_rara_ss"])
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["validaciones"].get("columnas_con_finalista") is False,
              f"columna sin finalista: ERROR con columnas_con_finalista en rojo ({codigo})")
    comprobar(not (raiz / CONTRATO_REL).exists(), "columna sin finalista: no escribe el contrato")


def probar_sin_cadena(m):
    """Caso 3: una finalista sin cadena completa para con ERROR."""
    raiz = montar("sin_ficha", m, quitar=("R-012",))
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["validaciones"].get("cadenas_completas") is False,
              f"falta R-012 en el registro: ERROR con cadenas_completas en rojo ({codigo})")
    comprobar(not (raiz / CONTRATO_REL).exists(), "falta R-012: no escribe el contrato")
    variables = matriz() + [{"variable": "year", "rama": "tal cual", "escalado": "StandardScaler",
                             "salida": ["year_ss"], "entra": True}]
    raiz = montar("sin_catalogo", m, columnas=COLUMNAS_BASE + ["year_ss"], variables_matriz=variables)
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["validaciones"].get("cadenas_completas") is False,
              f"finalista sin cadena en el catálogo: ERROR con cadenas_completas en rojo ({codigo})")


def probar_aprende_antes(m):
    """Caso 4: un paso que aprende ajustado antes de la partición para con ERROR."""
    raiz = montar("ajuste_con_todo", m, filas_preprocesador=110250)
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["validaciones"].get("aprende_despues_de_la_particion") is False,
              f"preprocesador ajustado con más filas que el entrenamiento: ERROR ({codigo})")
    comprobar(not (raiz / CONTRATO_REL).exists(), "preprocesador con todo: no escribe el contrato")
    # Función: una cadena con un paso que aprende delante de la partición
    cadena = [dict(m.PASOS["series"]), dict(m.PASOS["eventos_lista"]), dict(m.PASOS["particion"]),
              dict(m.PASOS["modelo"])]
    malos = m.aprende_antes_de_la_particion({"evento_<nombre>": cadena})
    comprobar(malos and malos[0]["variable"] == "evento_<nombre>",
              f"función: la lista de eventos delante de la partición sale como fallo ({malos})")
    cadena = [dict(m.PASOS["series"]), dict(m.PASOS["particion"]), dict(m.PASOS["eventos_lista"]),
              dict(m.PASOS["modelo"])]
    comprobar(m.aprende_antes_de_la_particion({"evento_<nombre>": cadena}) == [],
              "función: con la lista detrás de la partición no sale ningún fallo")


def probar_campo_vacio(m):
    """Caso 5: un campo vacío en el contrato para con ERROR."""
    raiz = montar("algoritmo_vacio", m, algoritmo="")
    codigo, d, _ = ejecutar(raiz)
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["validaciones"].get("sin_campos_vacios") is False,
              f"algoritmo vacío: ERROR con sin_campos_vacios en rojo ({codigo})")
    comprobar(not (raiz / CONTRATO_REL).exists(), "algoritmo vacío: no escribe el contrato")
    comprobar(m.campos_vacios({"a": {"b": [1, {"c": ""}]}, "d": 0}) == ["a.b[1].c"],
              "función: encuentra el texto vacío anidado y no toma el cero por vacío")
    comprobar(m.campos_vacios({"a": None, "b": [], "c": {}}) == ["a", "b", "c"],
              "función: null, lista vacía y diccionario vacío son campos vacíos")
    comprobar(m.campos_vacios({"a": 1, "b": [2], "c": {"d": False}}) == [],
              "función: sin vacíos no encuentra ninguno")


def probar_al_empezar(m):
    """Caso 6: sin veredicto «gana», con otra búsqueda o sin aprobación, el script para sin contrato."""
    for nombre, kwargs in (("no_gana", {"veredicto": "no gana"}), ("otra_busqueda", {"huella_distinta": True}),
                           ("sin_aprobar", {"aprobado": ""})):
        raiz = montar(nombre, m, **kwargs)
        codigo, d, _ = ejecutar(raiz)
        comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "PARADO"
                  and not d.get("puerta_de_juan"),
                  f"{nombre}: para al empezar, sin puerta y con 1 ({codigo}; {d and d['resultado']['estado']})")
        comprobar(not (raiz / CONTRATO_REL).exists(), f"{nombre}: no escribe el contrato")


def probar_sin_veredictos_escritos():
    """Caso 7, error 24: ninguna validación se escribe con su resultado puesto."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestos = re.findall(r"[\"'](columnas_con_finalista|cadenas_completas|aprende_despues_de_la_particion|"
                         r"sin_campos_vacios|columnas_del_contrato|filas_ejecucion|bit_a_bit|otro_camino|"
                         r"sin_quitar_filas_al_ejecutar|ficha_cuadra|cambia_con_datos_nuevos|periodo_que_toca|"
                         r"prevision_completa)[\"']\s*:\s*(True|False)\b", codigo)
    comprobar(puestos == [], f"el script no escribe ninguna validación con su resultado puesto ({puestos})")


def probar_aprobacion(m):
    """Caso 8: con la ficha del contrato aprobado en el registro, el contrato y el JSON lo dicen."""
    raiz = montar("aprobado", m, aprobado_contrato=True)
    codigo, d, salida = ejecutar(raiz)
    comprobar(d is not None and d["contrato"].get("aprobado_por") == "el responsable del caso" and d["contrato"].get("fecha") == "2026-11-25"
              and d["contrato"].get("estado") == TEXTO_APROBADO,
              f"aprobado: el JSON dice quién, cuándo y con qué palabras ({d and d.get('contrato')}; {salida[-400:]})")
    texto = (raiz / CONTRATO_REL).read_text(encoding="utf-8") if (raiz / CONTRATO_REL).exists() else ""
    comprobar(f"estado: {TEXTO_APROBADO}" in texto, "aprobado: la cabecera del contrato dice que está aprobado")
    comprobar("pendiente de la aprobación del responsable del caso" not in texto and "R-021" in texto,
              "aprobado: el contrato ya no dice que está pendiente y nombra su ficha del registro")
    comprobar(", y " not in texto and "—" not in texto, "aprobado: el contrato no trae «, y» ni rayas")
    comprobar(codigo == 0 and d is not None and d.get("parte") == 1 and d.get("codigo") is None,
              f"aprobado sin la parte 2: sale con 0 y la parte 2 queda vacía ({codigo})")
    # Caso 10: el modelo tiene su ficha (R-020) y los festivos la suya (R-019); los límites ya no dicen lo
    # contrario
    comprobar("no tiene ficha" not in texto and "el registro no lo recoge" not in texto and "R-020 (A)" in texto
              and "R-019" in texto,
              "aprobado: el modelo va con su ficha R-020 y los límites nombran R-019, sin decir que faltan")


def probar_parte_2(m):
    """Caso 9: la parte 2 se rellena con lo que dejan el reentreno, la prueba y el ensayo; en rojo, ERROR."""
    raiz = montar("parte_2", m, aprobado_contrato=True)
    reentreno, ensayo = montar_parte_2(raiz)
    codigo, d, salida = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo])
    comprobar(codigo == 0 and d is not None and d.get("parte") == 2 and d["resultado"]["estado"] == "AVISO",
              f"parte 2: sale con 0, parte 2 y AVISO por lo pendiente ({codigo}; {d and d['resultado']}; "
              f"{salida[-500:] if codigo else ''})")
    if d is None:
        return
    for clave in ("modulo", "reentrenar", "ejecutar", "prueba", "configuracion"):
        comprobar(bool((d.get("codigo") or {}).get(clave)), f"parte 2: codigo.{clave} relleno")
    re_ = d.get("reentreno") or {}
    comprobar(re_.get("igual_bit_a_bit") is True and re_.get("filas_entrada") == 82250
              and re_.get("modelo_en_uso", {}).get("existia") is False and re_.get("ruta"),
              f"parte 2: el reentreno trae filas, modelo en uso y bit a bit ({re_})")
    prueba = d.get("prueba_por_otro_camino") or {}
    comprobar(prueba.get("coincide") is True and prueba.get("rojo_con_estropeada") is True
              and prueba.get("tolerancia") == 1e-12, f"parte 2: la prueba por otro camino, con su rojo ({prueba})")
    comprobar("pendiente" in str((d.get("lote") or {}).get("estado", "")), "parte 2: el lote queda pendiente")
    val = d.get("validaciones", {})
    for nombre in ("columnas_del_contrato", "filas_ejecucion", "bit_a_bit", "otro_camino",
                   "sin_quitar_filas_al_ejecutar", "ficha_cuadra", "cambia_con_datos_nuevos", "periodo_que_toca",
                   "prevision_completa"):
        comprobar(val.get(nombre) is True, f"parte 2: {nombre} en verde ({val.get(nombre)})")
    comprobar(d.get("puerta_de_juan") is True and any("modelo en uso" in p.get("pregunta", "")
                                                       for p in d.get("pendientes", [])),
              "parte 2: el modelo en uso queda para el responsable del caso")
    # Caso 10: el límite de las ramas de event_name se escribe con sus palabras y la tolerancia, sin copiar
    # el motivo técnico del reentreno
    texto = (raiz / CONTRATO_REL).read_text(encoding="utf-8")
    comprobar("sin ellas la previsión sale igual" not in texto and "con la tolerancia de 1e-12" in texto,
              "parte 2: el límite de las ramas de event_name no copia el motivo del reentreno")

    # Los rojos: bit a bit, la estropeada que no sale en rojo y un paso que quita filas en ejecutar.py
    for nombre, kwargs, validacion in (("bit_a_bit_rojo", {"bit_a_bit": False}, "bit_a_bit"),
                                       ("estropeada_verde", {"estropeada_coincide": True}, "otro_camino"),
                                       ("ejecutar_quita", {"ejecutar_quita": True}, "sin_quitar_filas_al_ejecutar")):
        raiz = montar(nombre, m, aprobado_contrato=True)
        reentreno, ensayo = montar_parte_2(raiz, **kwargs)
        codigo, d, _ = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo])
        comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
                  and d["validaciones"].get(validacion) is False,
                  f"{nombre}: ERROR con {validacion} en rojo ({codigo}; {d and d['validaciones'].get(validacion)})")

    # Sin la aprobación, la parte 2 no se rellena
    raiz = montar("sin_aprobar_parte_2", m)
    reentreno, ensayo = montar_parte_2(raiz)
    codigo, d, _ = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo])
    comprobar(d is not None and d.get("codigo") is None and d.get("parte") == 1 and d["contrato"]["aprobado_por"] == "",
              f"sin aprobar: la parte 2 no se rellena ({d and d.get('parte')})")


def probar_lote(m):
    """Caso 11: el lote de la prueba final, su prueba por otro camino y el informe en Markdown."""
    raiz = montar("lote", m, aprobado_contrato=True)
    reentreno, ensayo = montar_parte_2(raiz)
    lote = montar_lote(raiz)
    reentrenado = montar_reentrenado(raiz)
    codigo, d, salida = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo, "--lote", lote,
                                        "--reentrenado", reentrenado])
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "AVISO",
              f"lote: sale con 0 y AVISO ({codigo}; {d and d['resultado']}; {salida[-500:] if codigo else ''})")
    if d is None:
        return
    lt = d.get("lote") or {}
    comprobar(lt.get("filas_entrada") == 42560 and lt.get("filas_salida") == 42560 and lt.get("sin_puntuar") == []
              and lt.get("ruta") and (lt.get("historial") or {}).get("ruta") and "pendiente" not in str(lt.get("estado")),
              f"lote: trae ruta, filas, sin puntuar e historial ({lt})")
    pl = (d.get("prueba_por_otro_camino") or {}).get("lote") or {}
    comprobar(isinstance(pl, dict) and pl.get("coincide") is True and pl.get("rojo_con_estropeada") is True,
              f"lote: la prueba por otro camino sobre el lote, con su rojo ({pl})")
    val = d.get("validaciones", {})
    comprobar(val.get("otro_camino_lote") is True and val.get("filas_lote") is True,
              f"lote: otro_camino_lote y filas_lote en verde ({val.get('otro_camino_lote')}, {val.get('filas_lote')})")
    comp = (d.get("reentreno") or {}).get("comparacion_con_el_en_uso") or {}
    comprobar(comp.get("reentrenado") and comp.get("en_uso"), f"lote: el reentreno trae la comparación ({comp})")
    pregunta = " ".join(json.dumps(p, ensure_ascii=False) for p in d.get("pendientes", []))
    comprobar("2015-05-22" in pregunta and "2026-11-25" in pregunta,
              "lote: la pregunta del modelo en uso nombra el candidato y el reentrenado")
    contrato = (raiz / CONTRATO_REL).read_text(encoding="utf-8")
    comprobar("No hay lote de producción dentro del caso" not in contrato,
              "lote: el contrato ya no dice que no hay lote")
    md = raiz / "informes" / "preproduccion.md"
    texto = md.read_text(encoding="utf-8") if md.exists() else ""
    apartados = ["## Las finalistas y su cadena", "## El contrato", "## Qué hace cada script", "## El reentreno",
                 "## El lote", "## La prueba por otro camino", "## Validaciones", "## Parámetros usados",
                 "## Datos personales", "## Límites"]
    posiciones = [texto.find(a) for a in apartados]
    comprobar(texto and all(x >= 0 for x in posiciones) and posiciones == sorted(posiciones),
              f"lote: informes/preproduccion.md con los apartados de resultado.md en su orden ({posiciones})")
    comprobar(", y " not in texto and "—" not in texto and "–" not in texto and "42.560" in texto,
              "lote: el informe no trae «, y» ni rayas y da las filas del lote leídas del JSON")
    # Los rojos: la prueba del lote que no sale en rojo y un lote con filas de menos
    for nombre, kwargs, validacion in (("lote_estropeada_verde", {"estropeada_coincide": True}, "otro_camino_lote"),
                                       ("lote_filas_de_menos", {"filas_salida": 42559}, "filas_lote")):
        raiz = montar(nombre, m, aprobado_contrato=True)
        reentreno, ensayo = montar_parte_2(raiz)
        lote = montar_lote(raiz, **kwargs)
        codigo, d, _ = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo, "--lote", lote])
        comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
                  and d["validaciones"].get(validacion) is False,
                  f"{nombre}: ERROR con {validacion} en rojo ({codigo}; {d and d['validaciones'].get(validacion)})")


def montar_en_uso(raiz, carpeta, aprobado):
    """La configuración de producción de juguete con su modelo en uso; el estado se escribe aquí (error 31)."""
    (raiz / "produccion").mkdir(parents=True, exist_ok=True)
    configuracion = {"modelo_en_uso": carpeta, "modelo_en_uso_lo_decide": "el responsable del caso", "modelo_en_uso_aprobado_por": aprobado}
    (raiz / "produccion" / "configuracion.json").write_text(json.dumps(configuracion, ensure_ascii=False),
                                                            encoding="utf-8")


def montar_otro_camino_reentrenado(lote, estropeada_coincide=False):
    """La prueba por otro camino sobre el lote del reentrenado y su versión estropeada, de juguete."""
    (lote / "reentrenado").mkdir(parents=True, exist_ok=True)
    for nombre, coincide in (("prueba_por_otro_camino.json", True),
                             ("prueba_por_otro_camino_estropeada.json", estropeada_coincide)):
        (lote / "reentrenado" / nombre).write_text(json.dumps({"coincide": coincide, "tolerancia": 1e-12, "origenes": 16,
                                                               "por_objetivo": {"unidades": {"filas": 11200},
                                                                                "dolares": {"filas": 31360}}}),
                                                   encoding="utf-8")


def probar_modelo_en_uso(m):
    """Caso 12: el modelo en uso aprobado por el responsable del caso resuelve P-02; la prueba por otro camino del reentrenado."""
    aprobado = "el responsable del caso, 25/11/2026: «Sí, apruebo el reentrenado»"
    raiz = montar("en_uso", m, aprobado_contrato=True)
    reentreno, ensayo = montar_parte_2(raiz)
    lote = montar_lote(raiz)
    montar_otro_camino_reentrenado(lote)
    reentrenado = montar_reentrenado(raiz)
    montar_en_uso(raiz, "modelos/reentrenos/2015-05-22", aprobado)
    argumentos = ["--reentreno", reentreno, "--ensayo", ensayo, "--lote", lote, "--reentrenado", reentrenado]
    codigo, d, salida = ejecutar(raiz, argumentos)
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "OK" and d.get("pendientes") == [],
              f"en uso: sale con 0, OK y sin pendientes ({codigo}; {d and d['resultado']}; {d and d.get('pendientes')}; "
              f"{salida[-500:] if codigo else ''})")
    if d is None:
        return
    en_uso = d.get("modelo_en_uso") or {}
    comprobar(en_uso.get("carpeta") == "modelos/reentrenos/2015-05-22" and en_uso.get("aprobado_por") == aprobado,
              f"en uso: el JSON dice el modelo en uso y quién lo aprobó ({en_uso})")
    resueltas = [x for x in d.get("decisiones") or [] if x.get("id") == "P-02"]
    comprobar(resueltas and resueltas[0].get("estado") == "resuelta" and aprobado in resueltas[0].get("decision", "")
              and resueltas[0].get("pregunta"),
              f"en uso: P-02 queda resuelta, con su pregunta y lo decidido ({resueltas})")
    pl = (d.get("prueba_por_otro_camino") or {}).get("lote_reentrenado") or {}
    comprobar(pl.get("coincide") is True and pl.get("rojo_con_estropeada") is True
              and d["validaciones"].get("otro_camino_lote_reentrenado") is True,
              f"en uso: la prueba por otro camino del reentrenado, con su rojo ({pl})")
    texto = (raiz / "informes" / "preproduccion.md").read_text(encoding="utf-8")
    comprobar("Falta que el responsable del caso decida" not in texto and "«Sí, apruebo el reentrenado»" in texto and "se midió sin ella" not in texto
              and "## Lo que puede decidir el responsable del caso" not in texto,
              "en uso: el informe dice el modelo en uso y la prueba del reentrenado, sin la pregunta ya resuelta")
    comprobar(", y " not in texto and "—" not in texto and "–" not in texto, "en uso: el informe sin «, y» ni rayas")
    # Los rojos: sin aprobación sigue pendiente; un modelo en uso que no es ninguno de los dos; la prueba del
    # reentrenado que no sale en rojo con la previsión estropeada
    raiz = montar("en_uso_sin_aprobar", m, aprobado_contrato=True)
    reentreno, ensayo = montar_parte_2(raiz)
    lote = montar_lote(raiz)
    reentrenado = montar_reentrenado(raiz)
    montar_en_uso(raiz, "modelos/reentrenos/2015-05-22", "")
    codigo, d, _ = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo, "--lote", lote,
                                   "--reentrenado", reentrenado])
    comprobar(codigo == 0 and d is not None and d["resultado"]["estado"] == "AVISO"
              and [x["id"] for x in d.get("pendientes", [])] == ["P-02"],
              f"en uso sin aprobar: P-02 sigue pendiente ({codigo}; {d and d.get('pendientes')})")
    raiz = montar("en_uso_otro", m, aprobado_contrato=True)
    reentreno, ensayo = montar_parte_2(raiz)
    lote = montar_lote(raiz)
    reentrenado = montar_reentrenado(raiz)
    montar_en_uso(raiz, "modelos/reentrenos/2099-01-01", aprobado)
    codigo, d, _ = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo, "--lote", lote,
                                   "--reentrenado", reentrenado])
    comprobar(codigo == 1 and d is not None and d["resultado"]["estado"] == "ERROR"
              and d["validaciones"].get("modelo_en_uso_medido") is False,
              f"en uso: un modelo que no es ninguno de los medidos da ERROR ({codigo}; {d and d['resultado']})")
    raiz = montar("en_uso_estropeada_verde", m, aprobado_contrato=True)
    reentreno, ensayo = montar_parte_2(raiz)
    lote = montar_lote(raiz)
    montar_otro_camino_reentrenado(lote, estropeada_coincide=True)
    reentrenado = montar_reentrenado(raiz)
    montar_en_uso(raiz, "modelos/reentrenos/2015-05-22", aprobado)
    codigo, d, _ = ejecutar(raiz, ["--reentreno", reentreno, "--ensayo", ensayo, "--lote", lote,
                                   "--reentrenado", reentrenado])
    comprobar(codigo == 1 and d is not None and d["validaciones"].get("otro_camino_lote_reentrenado") is False,
              f"en uso: la prueba del reentrenado que no sale en rojo da ERROR ({codigo})")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar_script()
            probar_base(modulo)
            probar_columna_sin_finalista(modulo)
            probar_sin_cadena(modulo)
            probar_aprende_antes(modulo)
            probar_campo_vacio(modulo)
            probar_al_empezar(modulo)
            probar_sin_veredictos_escritos()
            probar_aprobacion(modulo)
            probar_parte_2(modulo)
            probar_lote(modulo)
            probar_modelo_en_uso(modulo)
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_contrato borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
