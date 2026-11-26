"""Prueba de produccion/reentrenar.py, con datos pequeños escritos aquí.

No lee ningún dato del caso. Toma los datos de juguete de tests/probar_produccion_prevision.py (una venta, unos precios
y un calendario con la forma de data/raw/, dos tiendas y dos departamentos), monta en tests/tmp_reentrenar/ una carpeta
con la estructura del caso (contrato aprobado de juguete, configuración y tablas) y lanza el script como proceso aparte
con -W error. El estado del contrato (aprobado o no) se escribe aquí (error 31).

Los casos, los de quien quiere romperlo incluidos (programacion-del-caso, error 35):
  1. sin --tabla no arranca: la tabla no tiene valor por defecto;
  2. con la tabla de la partición sin --comprobacion, ERROR;
  3. con el contrato sin aprobar, PARADO: no reentrena;
  4. el reentreno de base: quita contadas las filas sin la historia que piden las variables (R-017, los 35 primeros
     días de cada serie), guarda la receta antes del fit y el modelo ajustado con su ficha, las columnas del modelo son
     las del contrato y la ficha dice que el modelo no guarda filas;
  5. un hueco a mitad de la historia (un retardo vacío después de días completos) para: no es un primer día;
  6. con un modelo en uso: con la misma tabla sale igual bit a bit; con una tabla distinta no sale igual;
  7. el modo de comprobación: con la referencia que dejó otra ejecución de la misma receta, coincide fila a fila; con
     una previsión de la referencia cambiada, no coincide y sale con ERROR; la tabla sin sus últimos días cambia el
     modelo;
  8. la carpeta del reentreno de ese día ya existe (el candidato que espera al responsable del caso): para con 1 sin tocarla, ni
     moverla ni escribir dentro, y sin crear _archivo (petición 28, tarea 4). Cada reentreno va a su carpeta.
Los casos que reentrenan dos veces usan una fecha distinta en cada una, porque el script ya no reutiliza una carpeta.
"""

# ── 1. Preparación ─────────────────────────────────────────────────────────────
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "produccion" / "reentrenar.py"
TMP = RAIZ / "tests" / "tmp_reentrenar"
sys.path.insert(0, str(RAIZ / "scripts"))
FALLOS = []


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


# Los datos de juguete y el contrato de juguete son los de la prueba del módulo: una sola definición
JUGUETE = cargar(RAIZ / "tests" / "probar_produccion_prevision.py", "juguete")


def contrato_aprobado(aprobado=True):
    """El contrato de juguete de los dos objetivos, con la forma de informes/preproduccion.json."""
    contrato = {"contrato": {"aprobado_por": "el responsable del caso" if aprobado else "", "fecha": "2026-11-25" if aprobado else ""},
                "objetivos": {}}
    for o in ("unidades", "dolares"):
        contrato["objetivos"].update(JUGUETE.contrato_pequeno(o, JUGUETE.columnas_pequenas(o))["objetivos"])
    return contrato


def montar(nombre, aprobado=True, modelo_en_uso=None, dias=140):
    """Carpeta de prueba con la estructura del caso; devuelve su raíz y la tabla completa con variables."""
    import produccion_prevision as pp
    raiz = TMP / nombre
    for carpeta in ("informes", "produccion", "data/processed", "modelos/reentrenos"):
        (raiz / carpeta).mkdir(parents=True, exist_ok=True)
    (raiz / "informes" / "preproduccion.json").write_text(json.dumps(contrato_aprobado(aprobado), ensure_ascii=False),
                                                          encoding="utf-8")
    configuracion = json.loads((RAIZ / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    configuracion["horizontes"] = {"unidades": 3, "dolares": 5}
    configuracion["dias_menos_para_comprobar_que_cambia"] = 14
    configuracion["modelo_en_uso"] = modelo_en_uso
    configuracion["rutas"]["modulo"] = str(RAIZ / "scripts")
    (raiz / "produccion" / "configuracion.json").write_text(json.dumps(configuracion, ensure_ascii=False),
                                                            encoding="utf-8")
    crudo = JUGUETE.calendario_crudo(dias)
    precios = JUGUETE.precios_crudos(crudo)
    venta = JUGUETE.venta_cruda(crudo, precios)
    tabla = pp.tabla_con_variables(venta, precios, crudo)
    # La tabla de la partición es otra: sin el último día. El script la reconoce por su contenido, no por su nombre
    particion = tabla[tabla["date"] < tabla["date"].max()]
    particion.to_parquet(raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet", index=False)
    return raiz, tabla


def ejecutar(raiz, *argumentos, fecha="2026-11-25"):
    """Lanza el script sobre la carpeta de prueba; devuelve (código, reentreno.json de esa fecha o None, salida)."""
    entorno = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz), "--fecha", fecha,
                           *map(str, argumentos)], capture_output=True, text=True, encoding="utf-8", env=entorno,
                          timeout=600)
    ruta = raiz / "modelos" / "reentrenos" / fecha / "reentreno.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return proc.returncode, datos, proc.stdout + proc.stderr


# ── 2. Casos ───────────────────────────────────────────────────────────────────
def probar_sin_tabla():
    """Caso 1: sin --tabla no arranca."""
    raiz, _ = montar("sin_tabla")
    codigo, _, salida = ejecutar(raiz)
    comprobar(codigo != 0 and "--tabla" in salida, f"sin --tabla no arranca ({codigo})")


def probar_tabla_de_la_particion():
    """Caso 2: la tabla de la partición solo en modo de comprobación."""
    raiz, _ = montar("particion")
    codigo, d, salida = ejecutar(raiz, "--tabla", raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet")
    comprobar(codigo == 1 and "comprobación" in salida and not (raiz / "modelos" / "reentrenos" / "2026-11-25" /
                                                                "unidades.joblib").exists(),
              f"tabla de la partición sin --comprobacion: ERROR y sin modelo ({codigo}; {salida[-300:]})")


def probar_sin_aprobar():
    """Caso 3: con el contrato sin aprobar no reentrena."""
    raiz, tabla = montar("sin_aprobar", aprobado=False)
    otra = raiz / "data" / "processed" / "otra.parquet"
    tabla.to_parquet(otra, index=False)
    codigo, _, salida = ejecutar(raiz, "--tabla", otra)
    comprobar(codigo == 1 and "aprobado" in salida, f"contrato sin aprobar: para sin reentrenar ({codigo})")


def probar_base():
    """Caso 4: el reentreno de base."""
    import joblib
    raiz, tabla = montar("base")
    otra = raiz / "data" / "processed" / "otra.parquet"
    tabla.to_parquet(otra, index=False)
    codigo, d, salida = ejecutar(raiz, "--tabla", otra)
    comprobar(codigo == 0 and d is not None and d["estado"] in ("OK", "AVISO"),
              f"base: sale con 0 ({codigo}; {salida[-800:] if codigo else ''})")
    if d is None:
        return
    quitadas = {x["ficha"]: x["filas"] for x in d["filas_quitadas"]}
    comprobar(quitadas.get("R-017") == 4 * 35 and quitadas.get("R-010") == 0 and d["filas_ajuste"] == len(tabla) - 140,
              f"base: quita contadas las 35 primeras filas de cada serie y ninguna sin objetivo ({quitadas})")
    carpeta = raiz / "modelos" / "reentrenos" / "2026-11-25"
    for o in ("unidades", "dolares"):
        receta = joblib.load(carpeta / f"{o}_receta.joblib")
        comprobar(not hasattr(receta.named_steps["modelo"], "n_iter_"),
                  f"{o}: la receta se guardó antes del fit, sin ajustar")
        ficha = json.loads((carpeta / f"{o}_versiones.json").read_text(encoding="utf-8"))
        comprobar(ficha["columnas_salida"] == JUGUETE.columnas_pequenas(o) and ficha["filas"] == len(tabla) - 140
                  and ficha["huella_tabla"] and ficha["lleva_filas_de_entrenamiento"]["lleva"] is False
                  and ficha["inspeccion"]["remainder"] == "drop" and ficha["semilla"] == 42,
                  f"{o}: la ficha trae columnas, filas, huella, inspección y si guarda filas")
    comprobar(d["validaciones"]["columnas_del_contrato"] is True and d["modelo_en_uso"]["existia"] is False,
              "base: columnas del contrato en verde y sin modelo en uso")


def probar_hueco():
    """Caso 5: un retardo vacío a mitad de la historia para."""
    raiz, tabla = montar("hueco")
    rota = tabla.copy()
    fila = rota.index[(rota["store_id"] == "CA_1") & (rota["date"] == pd.Timestamp("2011-05-01"))][0]
    rota.loc[fila, "unidades_lag_3"] = np.nan
    ruta = raiz / "data" / "processed" / "rota.parquet"
    rota.to_parquet(ruta, index=False)
    codigo, _, salida = ejecutar(raiz, "--tabla", ruta)
    comprobar(codigo == 1 and "hueco" in salida, f"un retardo vacío a mitad de la historia para ({codigo})")


def probar_modelo_en_uso():
    """Caso 6: con un modelo en uso, la misma tabla sale igual y una distinta no."""
    raiz, tabla = montar("primero")
    otra = raiz / "data" / "processed" / "otra.parquet"
    tabla.to_parquet(otra, index=False)
    codigo, d, _ = ejecutar(raiz, "--tabla", otra)
    en_uso = raiz / "modelos" / "en_uso"
    shutil.copytree(raiz / "modelos" / "reentrenos" / "2026-11-25", en_uso)
    configuracion = json.loads((raiz / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    configuracion["modelo_en_uso"] = "modelos/en_uso"
    (raiz / "produccion" / "configuracion.json").write_text(json.dumps(configuracion), encoding="utf-8")
    codigo, d, salida = ejecutar(raiz, "--tabla", otra, fecha="2026-11-26")
    comprobar(codigo == 0 and d is not None and d["validaciones"].get("bit_a_bit") is True
              and d["modelo_en_uso"]["existia"] is True,
              f"misma tabla que el modelo en uso: sale igual bit a bit ({codigo}; {salida[-500:] if codigo else ''})")
    distinta = tabla.copy()
    distinta["unidades"] = distinta["unidades"] * 2
    distinta["dolares"] = distinta["dolares"] * 2
    ruta = raiz / "data" / "processed" / "distinta.parquet"
    distinta.to_parquet(ruta, index=False)
    codigo, d, salida = ejecutar(raiz, "--tabla", ruta, fecha="2026-11-27")
    comprobar(codigo == 0 and d is not None and d["validaciones"].get("cambia_con_datos_nuevos") is True,
              f"tabla distinta: el reentrenado no sale igual ({codigo}; {d and d['validaciones']})")


def probar_comprobacion():
    """Caso 7: el modo de comprobación contra una referencia, en verde y en rojo."""
    import produccion_prevision as pp
    raiz, tabla = montar("comprobacion", dias=140)
    corte = pd.Timestamp("2011-05-27")
    entrenamiento = tabla[tabla["date"] <= corte].reset_index(drop=True)
    validacion = tabla[tabla["date"] > corte].reset_index(drop=True)
    entrenamiento.to_parquet(raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet", index=False)
    validacion.to_parquet(raiz / "data" / "processed" / "validacion.parquet", index=False)
    # La referencia: la misma receta ajustada aquí con el módulo, desde dos orígenes, como la dejaría la validación
    contrato = contrato_aprobado()
    sin_historia = entrenamiento[pp.COLUMNAS_DE_HISTORIA].isna().any(axis=1).to_numpy()
    ajuste = entrenamiento[~sin_historia].sort_values(["date", "store_id", "dept_id"]).reset_index(drop=True)
    filas = []
    for o, h in (("unidades", 3), ("dolares", 5)):
        receta = pp.receta_del_contrato(contrato, o)
        pipe = pp.construir_pipeline(receta).fit(ajuste[pp.columnas_de_entrada(receta)], ajuste[o])
        historia = pd.concat([entrenamiento, validacion], ignore_index=True)[["store_id", "dept_id", "date", o]]
        for origen in (corte, corte + pd.Timedelta(7, "D")):
            dias = [origen + pd.Timedelta(k, "D") for k in range(1, h + 1)]
            futuro = validacion[validacion["date"].isin(dias)]
            p = pp.prever(pipe, historia, futuro, o, h, origen)
            filas.append(p.assign(objetivo=o, origen=origen,
                                  modelo=pp.redondear_salida(p["prevision_sin_redondear"], o)))
    referencia = pd.concat(filas, ignore_index=True).drop(columns="prevision_sin_redondear")
    ruta_ref = raiz / "data" / "processed" / "referencia.parquet"
    referencia.to_parquet(ruta_ref, index=False)
    particion = raiz / "data" / "processed" / "hechos_modelo_entrenamiento.parquet"
    codigo, d, salida = ejecutar(raiz, "--tabla", particion, "--comprobacion", "--validacion",
                                 raiz / "data" / "processed" / "validacion.parquet", "--referencia", ruta_ref)
    comprobar(codigo == 0 and d is not None and d["validaciones"].get("bit_a_bit") is True
              and all(x["diferencia_maxima"] == 0 for x in d["comprobacion"]["por_objetivo"].values())
              and d["validaciones"].get("cambia_con_datos_nuevos") is True,
              f"comprobación: coincide con la referencia y cambia sin los últimos días ({codigo}; "
              f"{d and d.get('comprobacion')}; {salida[-600:] if codigo else ''})")
    comprobar((raiz / "modelos" / "reentrenos" / "2026-11-25" / "previsiones_comprobacion.parquet").exists(),
              "comprobación: deja sus previsiones para la prueba por otro camino")
    estropeada = referencia.copy()
    estropeada.loc[0, "modelo"] = estropeada.loc[0, "modelo"] + 1
    estropeada.to_parquet(ruta_ref, index=False)
    codigo, d, salida = ejecutar(raiz, "--tabla", particion, "--comprobacion", "--validacion",
                                 raiz / "data" / "processed" / "validacion.parquet", "--referencia", ruta_ref,
                                 fecha="2026-11-26")
    comprobar(codigo == 1 and d is not None and d["validaciones"].get("bit_a_bit") is False,
              f"comprobación: con una previsión de la referencia cambiada, ERROR ({codigo})")


def probar_carpeta_que_ya_existe():
    """Caso 8: con la carpeta del día ya existente, para sin tocarla."""
    import hashlib
    raiz, tabla = montar("ya_existe")
    otra = raiz / "data" / "processed" / "otra.parquet"
    tabla.to_parquet(otra, index=False)
    codigo, primero, _ = ejecutar(raiz, "--tabla", otra)
    carpeta = raiz / "modelos" / "reentrenos" / "2026-11-25"

    def huellas():
        """La huella de cada fichero de la carpeta del primer reentreno."""
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(carpeta.iterdir())}             if carpeta.exists() else {}

    antes = huellas()
    distinta = tabla.copy()
    distinta["unidades"] = distinta["unidades"] * 2
    ruta = raiz / "data" / "processed" / "distinta.parquet"
    distinta.to_parquet(ruta, index=False)
    codigo, _, salida = ejecutar(raiz, "--tabla", ruta)
    comprobar(primero is not None and antes and codigo == 1 and "ya existe" in salida,
              f"carpeta que ya existe: para con 1 y lo dice ({codigo}; {salida[-300:]})")
    comprobar(huellas() == antes, "carpeta que ya existe: sus ficheros quedan como estaban")
    comprobar(not (carpeta.parent / "_archivo").exists(), "carpeta que ya existe: no la mueve a _archivo")


# ── 3. Ejecución ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe el script {SCRIPT.relative_to(RAIZ)}")
        else:
            probar_sin_tabla()
            probar_tabla_de_la_particion()
            probar_sin_aprobar()
            probar_base()
            probar_hueco()
            probar_modelo_en_uso()
            probar_comprobacion()
            probar_carpeta_que_ya_existe()
    except Exception as error:  # un fallo de la prueba es un fallo, con su motivo
        import traceback
        traceback.print_exc()
        comprobar(False, f"la prueba se ejecuta sin excepción ({type(error).__name__}: {error})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp_reentrenar borrada:", not TMP.exists())
    print("RESULTADO:", "VERDE" if not FALLOS else f"ROJO, {len(FALLOS)} caso(s)")
    sys.exit(1 if FALLOS else 0)
