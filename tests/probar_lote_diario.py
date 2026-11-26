"""Prueba de produccion/lote_diario.py, con datos pequeños escritos aquí.

No lee ningún dato del caso. Toma los datos de juguete de tests/probar_produccion_prevision.py (venta, precios y
calendario con la forma de data/raw/, dos tiendas y dos departamentos), monta en tests/tmp_lote_diario/ una carpeta con
la estructura del caso, reentrena en ella un modelo pequeño con produccion/reentrenar.py, lo pone como modelo en uso en
su configuración y lanza el lote como proceso aparte con -W error, sin argumentos salvo la carpeta del caso.

Los casos, los de quien quiere romperlo incluidos (programacion-del-caso, error 35):
  1. el origen es el último día con venta, por el calendario y no por el orden de las columnas; un último día con un
     producto vacío (la venta de ayer no llegó entera) o un día que no está en el calendario paran;
  2. el registro: la última ejecución buena se lee de él; sin fichero no hay ninguna; una línea rota para;
  3. la venta tiene que avanzar: con la misma venta que la última ejecución buena, o con una anterior, para; con
     --repetir se deja repetir a propósito;
  4. el origen no puede caer dentro del entrenamiento del modelo en uso (los días a prever estarían en él);
  5. los precios de varias fuentes se juntan; una semana de un producto repetida en dos fuentes para;
  6. el intérprete tiene que ser el de la configuración; la configuración sin su apartado del lote para;
  7. de principio a fin: sin argumentos prevé con el modelo en uso, deja data/predicciones/AAAA-MM-DD/ con su resumen,
     apunta la ejecución en el registro y sale con 0; con la misma venta otra vez, para con 1 y no escribe previsiones;
     con el día siguiente, prevé desde un día después y la primera salida del mismo día queda en _archivo/;
  8. con una venta que no llega hasta el día que se pide (--origen), para con 1 y un mensaje claro;
  9. ninguna comprobación del script se escribe con su resultado puesto (error 24).
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "produccion" / "lote_diario.py"
REENTRENAR = RAIZ / "produccion" / "reentrenar.py"
TMP = RAIZ / "tests" / "tmp_lote_diario"
sys.path.insert(0, str(RAIZ / "scripts"))
FALLOS = []
HORIZONTES = {"unidades": 3, "dolares": 5}
DIA_ORIGEN = 120      # el último día de la venta de juguete con que se entrena y se prevé la primera vez
FECHA = "2026-11-25"  # la carpeta de la ejecución


def comprobar(condicion, caso):
    """Apunta el caso si la condición no se cumple."""
    if not condicion:
        FALLOS.append(caso)
        print("FALLA:", caso)
    else:
        print("pasa: ", caso)


def cargar(ruta, nombre):
    """Importa un fichero .py sin ejecutar su __main__."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


JUGUETE = cargar(RAIZ / "tests" / "probar_produccion_prevision.py", "juguete_lote")


def para(funcion, *argumentos, **nombrados):
    """El mensaje si la función para con Parada del lote; None si no para."""
    try:
        funcion(*argumentos, **nombrados)
    except Exception as error:  # se mira el nombre de la clase: la del módulo que se prueba
        return str(error) if type(error).__name__ == "Parada" else f"otra excepción: {type(error).__name__}: {error}"
    return None


def venta_pequena():
    """Una venta de dos productos y cinco días, con el calendario de esos días; d_4 va detrás de d_5."""
    calendario = pd.DataFrame({"d": [f"d_{i}" for i in range(1, 6)],
                               "date": pd.date_range("2015-05-18", periods=5, freq="D")})
    venta = pd.DataFrame({"id": ["A", "B"], "item_id": ["A", "B"], "dept_id": ["D", "D"], "cat_id": ["C", "C"],
                          "store_id": ["S", "S"], "state_id": ["CA", "CA"],
                          "d_1": [1, 2], "d_2": [0, 1], "d_3": [3, 0], "d_5": [2, 2], "d_4": [1, 1]})
    return venta, calendario


# ── 2. Casos con funciones ─────────────────────────────────────────────────────
def probar_origen(m):
    """Caso 1: el origen es el último día con venta; un último día incompleto o fuera del calendario para."""
    venta, calendario = venta_pequena()
    origen = m.origen_de_la_venta(venta, calendario)
    comprobar(origen == pd.Timestamp("2015-05-22"), f"origen: el último día por el calendario ({origen})")
    incompleta = venta.copy()
    incompleta.loc[1, "d_5"] = float("nan")
    mensaje = para(m.origen_de_la_venta, incompleta, calendario)
    comprobar(mensaje is not None and "no ha llegado entera" in mensaje,
              f"origen: el último día con un producto vacío para ({mensaje})")
    fuera = venta.rename(columns={"d_5": "d_9"})
    mensaje = para(m.origen_de_la_venta, fuera, calendario)
    comprobar(mensaje is not None and "calendario" in mensaje, f"origen: un día fuera del calendario para ({mensaje})")


def probar_registro(m):
    """Caso 2: la última ejecución buena, del registro."""
    carpeta = TMP / "registro"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "registro.jsonl"
    comprobar(m.ultima_ejecucion_buena(ruta) is None, "registro: sin fichero no hay ninguna ejecución buena")
    lineas = [{"estado": "OK", "origen": "2015-05-21", "fecha": "2026-11-24"},
              {"estado": "OK", "origen": "2015-05-22", "fecha": "2026-11-25"},
              {"estado": "PARA", "origen": "2015-05-22", "fecha": "2026-11-26"}]
    ruta.write_text("\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    ultima = m.ultima_ejecucion_buena(ruta)
    comprobar(ultima is not None and ultima["origen"] == "2015-05-22" and ultima["fecha"] == "2026-11-25",
              f"registro: la última buena, no la última línea ({ultima})")
    ruta.write_text(ruta.read_text(encoding="utf-8") + "{esto no es JSON\n", encoding="utf-8")
    mensaje = para(m.ultima_ejecucion_buena, ruta)
    comprobar(mensaje is not None and "registro" in mensaje, f"registro: una línea rota para ({mensaje})")


def probar_avanza(m):
    """Caso 3: la venta tiene que avanzar respecto de la última ejecución buena."""
    previa = {"estado": "OK", "origen": "2015-05-22", "fecha": "2026-11-25"}
    misma = para(m.comprobar_que_avanza, pd.Timestamp("2015-05-22"), previa, False)
    comprobar(misma is not None and "no llega hasta ayer" in misma, f"avanza: la misma venta para ({misma})")
    anterior = para(m.comprobar_que_avanza, pd.Timestamp("2015-05-20"), previa, False)
    comprobar(anterior is not None, f"avanza: una venta anterior para ({anterior})")
    comprobar(para(m.comprobar_que_avanza, pd.Timestamp("2015-05-22"), previa, True) is None,
              "avanza: con --repetir se deja repetir")
    comprobar(para(m.comprobar_que_avanza, pd.Timestamp("2015-05-23"), previa, False) is None,
              "avanza: un día después pasa")
    comprobar(para(m.comprobar_que_avanza, pd.Timestamp("2015-05-23"), None, False) is None,
              "avanza: sin ejecución anterior pasa")


def probar_entrenamiento(m):
    """Caso 4: el origen no cae dentro del entrenamiento del modelo en uso."""
    fichas = {"unidades": {"fecha_datos": "2015-05-22"}, "dolares": {"fecha_datos": "2015-05-22"}}
    mensaje = para(m.comprobar_fuera_del_entrenamiento, pd.Timestamp("2015-05-21"), fichas)
    comprobar(mensaje is not None and "entrenamiento" in mensaje, f"entrenamiento: un origen anterior para ({mensaje})")
    comprobar(para(m.comprobar_fuera_del_entrenamiento, pd.Timestamp("2015-05-22"), fichas) is None,
              "entrenamiento: el último día del entrenamiento como origen pasa")
    sin = para(m.comprobar_fuera_del_entrenamiento, pd.Timestamp("2015-05-22"), {"unidades": {}, "dolares": {}})
    comprobar(sin is not None, f"entrenamiento: una ficha sin fecha de los datos para ({sin})")


def probar_precios(m):
    """Caso 5: los precios de varias fuentes se juntan; una semana repetida para."""
    carpeta = TMP / "precios"
    carpeta.mkdir(parents=True, exist_ok=True)
    a = pd.DataFrame({"store_id": ["S", "S"], "item_id": ["A", "B"], "wm_yr_wk": [11101, 11101], "sell_price": [1.0, 2.0]})
    b = pd.DataFrame({"store_id": ["S"], "item_id": ["A"], "wm_yr_wk": [11102], "sell_price": [1.5]})
    a.to_csv(carpeta / "a.csv", index=False, encoding="utf-8")
    b.to_csv(carpeta / "b.csv", index=False, encoding="utf-8")
    ruta = m.juntar_precios([carpeta / "a.csv", carpeta / "b.csv"], carpeta / "juntos")
    juntos = pd.read_csv(ruta, encoding="utf-8")
    comprobar(len(juntos) == 3 and set(juntos["wm_yr_wk"]) == {11101, 11102}, f"precios: se juntan ({len(juntos)} filas)")
    comprobar(m.juntar_precios([carpeta / "a.csv"], carpeta / "solo") == carpeta / "a.csv",
              "precios: con una sola fuente se usa tal cual")
    a.to_csv(carpeta / "c.csv", index=False, encoding="utf-8")
    mensaje = para(m.juntar_precios, [carpeta / "a.csv", carpeta / "c.csv"], carpeta / "repetidos")
    comprobar(mensaje is not None and "repetid" in mensaje, f"precios: una semana repetida para ({mensaje})")


def probar_interprete_y_configuracion(m):
    """Caso 6: el intérprete de la configuración y su apartado del lote."""
    comprobar(para(m.comprobar_interprete, Path(sys.executable), Path(sys.executable.upper())) is None,
              "intérprete: el mismo, escrito con otras mayúsculas, pasa")
    mensaje = para(m.comprobar_interprete, Path(sys.executable), Path("otro/python.exe"))
    comprobar(mensaje is not None and "intérprete" in mensaje, f"intérprete: otro para ({mensaje})")
    carpeta = TMP / "sin_apartado" / "produccion"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "configuracion.json").write_text(json.dumps({"rutas": {}}), encoding="utf-8")
    mensaje = para(m.leer_configuracion, carpeta.parent)
    comprobar(mensaje is not None and "lote_diario" in mensaje, f"configuración: sin su apartado para ({mensaje})")


def probar_sin_validaciones_escritas():
    """Caso 9: ninguna comprobación se escribe con su resultado puesto (error 24)."""
    codigo = SCRIPT.read_text(encoding="utf-8")
    escritas = re.findall(r'"[a-z_]+":\s*(?:True|False)\b', codigo)
    comprobar(not escritas, f"sin comprobaciones escritas con su resultado ({escritas})")


# ── 3. De principio a fin, con un modelo de juguete ─────────────────────────────
def montar():
    """La carpeta de prueba con un modelo pequeño reentrenado hasta el día 120 y puesto en uso; devuelve la raíz y los
    datos crudos."""
    import produccion_prevision as pp
    raiz = TMP / "caso"
    for carpeta in ("informes", "produccion", "data/processed", "data/entrada", "modelos/reentrenos"):
        (raiz / carpeta).mkdir(parents=True, exist_ok=True)
    contrato = {"contrato": {"aprobado_por": "el responsable del caso", "fecha": "2026-11-25"}, "objetivos": {}}
    for o in ("unidades", "dolares"):
        contrato["objetivos"].update(JUGUETE.contrato_pequeno(o, JUGUETE.columnas_pequenas(o))["objetivos"])
    (raiz / "informes" / "preproduccion.json").write_text(json.dumps(contrato, ensure_ascii=False), encoding="utf-8")
    crudo = JUGUETE.calendario_crudo(140)
    precios = JUGUETE.precios_crudos(crudo)
    venta = JUGUETE.venta_cruda(crudo, precios)
    ids = [c for c in venta.columns if not c.startswith("d_")]
    venta_origen = venta[ids + [f"d_{i}" for i in range(1, DIA_ORIGEN + 1)]]
    tabla = pp.tabla_con_variables(venta_origen, precios, crudo)
    tabla.to_parquet(raiz / "data" / "processed" / "entrenamiento.parquet", index=False)
    tabla.head(10).to_parquet(raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet", index=False)
    configuracion = json.loads((RAIZ / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    configuracion["horizontes"] = HORIZONTES
    configuracion["dias_menos_para_comprobar_que_cambia"] = 14
    configuracion["modelo_en_uso"] = None
    configuracion["rutas"]["modulo"] = str(RAIZ / "scripts")
    escribir_configuracion(raiz, configuracion)
    proc = subprocess.run([sys.executable, "-W", "error", str(REENTRENAR), "--raiz", str(raiz), "--fecha", "2011-05-28",
                           "--tabla", str(raiz / "data" / "processed" / "entrenamiento.parquet")],
                          capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"),
                          timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"el reentreno de juguete no salió: {proc.stdout[-500:]} {proc.stderr[-800:]}")
    # El modelo en uso y el apartado del lote: las entradas, el registro y el intérprete, escritos aquí
    configuracion["modelo_en_uso"] = "modelos/reentrenos/2011-05-28"
    configuracion["lote_diario"] = {
        "python": sys.executable,
        "entradas": {"venta": "data/entrada/venta.csv", "precios": ["data/entrada/precios_a.csv",
                                                                    "data/entrada/precios_b.csv"],
                     "calendario": "data/entrada/calendario.csv"},
        "registro": "data/predicciones/registro_lote_diario.jsonl",
        "registros_del_envoltorio": "data/predicciones/_registros",
        "trabajo": "data/predicciones/_trabajo"}
    escribir_configuracion(raiz, configuracion)
    # Los precios llegan en dos ficheros, partidos por semanas, como data/raw/ y data/raw/reserva/
    corte = sorted(precios["wm_yr_wk"].unique())[len(precios["wm_yr_wk"].unique()) // 2]
    precios[precios["wm_yr_wk"] <= corte].to_csv(raiz / "data" / "entrada" / "precios_a.csv", index=False,
                                                encoding="utf-8")
    precios[precios["wm_yr_wk"] > corte].to_csv(raiz / "data" / "entrada" / "precios_b.csv", index=False,
                                               encoding="utf-8")
    crudo.to_csv(raiz / "data" / "entrada" / "calendario.csv", index=False, encoding="utf-8")
    return raiz, venta, ids


def escribir_configuracion(raiz, configuracion):
    """Escribe la configuración de la carpeta de prueba."""
    (raiz / "produccion" / "configuracion.json").write_text(json.dumps(configuracion, ensure_ascii=False, indent=2),
                                                            encoding="utf-8")


def escribir_venta(raiz, venta, ids, ultimo_dia):
    """La venta de entrada hasta el día que se pide, con la forma de data/raw/."""
    venta[ids + [f"d_{i}" for i in range(1, ultimo_dia + 1)]].to_csv(raiz / "data" / "entrada" / "venta.csv",
                                                                     index=False, encoding="utf-8")


def lanzar(raiz, *extra):
    """Lanza el lote como proceso aparte, con -W error; devuelve (código, texto)."""
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz), "--fecha", FECHA,
                           *map(str, extra)], capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONUTF8="1"), timeout=600)
    return proc.returncode, proc.stdout + proc.stderr


def leer_registro(raiz):
    """Las líneas del registro de ejecuciones."""
    ruta = raiz / "data" / "predicciones" / "registro_lote_diario.jsonl"
    if not ruta.exists():
        return []
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def probar_de_principio_a_fin():
    """Casos 7 y 8: sin argumentos, la misma venta otra vez, el día siguiente y una venta que no llega."""
    raiz, venta, ids = montar()
    carpeta = raiz / "data" / "predicciones" / FECHA
    escribir_venta(raiz, venta, ids, DIA_ORIGEN)
    codigo, texto = lanzar(raiz)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8")) if (carpeta / "resumen.json").exists() \
        else None
    comprobar(codigo == 0 and resumen is not None, f"de principio a fin: sale con 0 y deja el resumen ({codigo}; "
                                                   f"{texto[-1200:] if codigo else ''})")
    if resumen is None:
        return
    comprobar(resumen["origen"] == "2011-05-28" and resumen["modelo"]["en_uso"] is True and resumen["ensayo"] is False,
              f"de principio a fin: prevé desde el último día con el modelo en uso ({resumen['origen']}, "
              f"{resumen['modelo']['en_uso']})")
    registro = leer_registro(raiz)
    comprobar(len(registro) == 1 and registro[0]["estado"] == "OK" and registro[0]["origen"] == "2011-05-28"
              and registro[0]["codigo"] == 0 and registro[0].get("duracion_s") is not None,
              f"de principio a fin: el registro apunta la ejecución ({registro})")
    comprobar(not (raiz / "data" / "predicciones" / "_trabajo").exists()
              or not any((raiz / "data" / "predicciones" / "_trabajo").iterdir()),
              "de principio a fin: no deja ficheros de trabajo")
    primera = pd.read_parquet(carpeta / "previsiones.parquet")

    # La misma venta otra vez: no llega hasta ayer
    codigo, texto = lanzar(raiz)
    registro = leer_registro(raiz)
    archivo = raiz / "data" / "predicciones" / "_archivo"
    comprobar(codigo == 1 and "no llega hasta ayer" in texto and registro[-1]["estado"] == "PARA"
              and not archivo.exists(),
              f"la misma venta: para con 1 sin tocar las previsiones ({codigo}; {texto[-400:]})")

    # El día siguiente: el origen avanza un día y la primera salida del mismo día queda en _archivo
    escribir_venta(raiz, venta, ids, DIA_ORIGEN + 1)
    codigo, texto = lanzar(raiz)
    segunda = pd.read_parquet(carpeta / "previsiones.parquet") if codigo == 0 else None
    copias = sorted(archivo.glob(f"{FECHA}_*")) if archivo.exists() else []
    comprobar(codigo == 0 and segunda is not None and (pd.to_datetime(segunda["origen"]) == "2011-05-29").all()
              and len(copias) == 1,
              f"el día siguiente: prevé desde un día después y archiva la primera ({codigo}; {len(copias)}; "
              f"{texto[-800:] if codigo else ''})")
    if copias:
        archivada = pd.read_parquet(copias[0] / "previsiones.parquet")
        comprobar(archivada.equals(primera), "el día siguiente: la salida archivada es la primera")
    if segunda is not None:
        comprobar(pd.to_datetime(segunda["date"]).min() == pd.to_datetime(primera["date"]).min() + pd.Timedelta(1, "D"),
                  "el día siguiente: los días previstos se corren un día")

    # Una venta que no llega hasta el día que se pide
    codigo, texto = lanzar(raiz, "--origen", "2011-05-31")
    comprobar(codigo == 1 and "no llega" in texto, f"--origen: una venta que no llega para con 1 ({codigo}; "
                                                   f"{texto[-400:]})")


# ── 4. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            modulo = cargar(SCRIPT, "lote_diario_prueba")
            probar_origen(modulo)
            probar_registro(modulo)
            probar_avanza(modulo)
            probar_entrenamiento(modulo)
            probar_precios(modulo)
            probar_interprete_y_configuracion(modulo)
            probar_sin_validaciones_escritas()
            probar_de_principio_a_fin()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_lote_diario borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
