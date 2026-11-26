"""Previsión recursiva del caso 69, las tres reglas sencillas, el error del caso y los pliegues por día.

Módulo de funciones, sin nada que se ejecute al importarlo (programacion-del-caso, error 1). Lo usan
scripts/14_modelo_minimo.py y, después, la búsqueda, la validación y la producción: la misma función prevé desde
cualquier origen, para todas las combinaciones de departamento y tienda a la vez.

Las reglas salen de config/negocio/reglas-negocio.md: §5, «El horizonte» y «Lo que se sabe el día de prever»
(la previsión de un día usa la venta hasta la víspera, y desde el origen, lo ya previsto); §6, las métricas (el error
y el sesgo por cada 100 vendidas, una previsión nunca negativa); §7, las tres reglas sencillas, con el día del origen
dentro de su ventana. Y de config/metodo/04_planteamientos.md §2, decisión 2.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

import variables_prevision as vp

CLAVE_SERIE = vp.CLAVE_SERIE
COLUMNA_FECHA = vp.COLUMNA_FECHA
# El retardo más largo y la media más larga piden 28 días de historia antes de cada día previsto (decisión 7)
HISTORIA_NECESARIA = max(max(vp.RETARDOS), max(vp.VENTANAS))
# Reglas, apartado 7: las tres reglas, con su nombre entero
REGLAS = ("repetir_semana_anterior", "media_28_dias", "media_mismo_dia_4_semanas")
UN_DIA = pd.Timedelta(1, "D")


# ══ 2. Utilidades ═══════════════════════════════════════════════════════════════
def _columnas_de_objetivo(columnas):
    """Las columnas que dicen la venta de un día (los objetivos) o salen de ella (retardos y medias)."""
    prefijos = tuple(f"{o}_" for o in vp.OBJETIVOS)
    return [c for c in columnas if c in vp.OBJETIVOS or str(c).startswith(prefijos)]


def ventana_hasta_el_origen(historia, objetivo, origen):
    """Los 28 días de cada serie que acaban en el origen, con el día del origen, comprobados.

    Corta la historia en el origen: lo que haya después no se usa. Para si una serie no tiene los 28 días seguidos o
    tiene la venta vacía en alguno.
    """
    faltan = [c for c in CLAVE_SERIE + [COLUMNA_FECHA, objetivo] if c not in historia.columns]
    if faltan:
        raise ValueError(f"a la historia le faltan columnas: {faltan}")
    desde = origen - pd.Timedelta(HISTORIA_NECESARIA - 1, "D")
    mascara = ((historia[COLUMNA_FECHA] >= desde) & (historia[COLUMNA_FECHA] <= origen)).to_numpy()
    ventana = historia.loc[mascara, CLAVE_SERIE + [COLUMNA_FECHA, objetivo]].copy()
    ventana[objetivo] = ventana[objetivo].astype("float64")
    if ventana.empty:
        raise ValueError(f"la historia no tiene ningún día entre {desde:%Y-%m-%d} y el origen {origen:%Y-%m-%d}")
    if ventana[objetivo].isna().any():
        raise ValueError(f"{int(ventana[objetivo].isna().sum())} días de la historia con la venta vacía")
    dias = ventana.groupby(CLAVE_SERIE)[COLUMNA_FECHA].nunique()
    filas = ventana.groupby(CLAVE_SERIE).size()
    incompletas = dias[(dias != HISTORIA_NECESARIA) | (filas != HISTORIA_NECESARIA)]
    if len(incompletas):
        raise ValueError(f"{len(incompletas)} series sin los {HISTORIA_NECESARIA} días seguidos que acaban en el "
                         f"origen {origen:%Y-%m-%d}: {list(incompletas.index[:3])}")
    return ventana.sort_values(CLAVE_SERIE + [COLUMNA_FECHA]).reset_index(drop=True)


# ══ 3. La previsión recursiva ═══════════════════════════════════════════════════
def prever_recursivo(modelo, historia, futuro, objetivo, horizonte, origen=None):
    """Prevé desde un origen, día a día hasta el horizonte, todas las series de la historia a la vez.

    modelo: cualquier objeto con predict(x), que recibe una tabla con las columnas del futuro y los retardos y medias
    del objetivo (el Pipeline entero del caso). historia: store_id, dept_id, date y el objetivo, con la venta real; se
    corta en el origen (por defecto, su último día). futuro: una fila por serie y día del horizonte con lo que se conoce
    de antemano (calendario, eventos, precio de la semana anterior: reglas, apartado 5, D9); si trae la venta real o retardos de
    alguno de los dos objetivos, se quitan antes de prever.

    Cada día calcula sus retardos y medias con variables_prevision.crear_variables_objetivo sobre la historia, que
    llega hasta el origen con la venta real y sigue con lo ya previsto. Acota la previsión en cero y la añade a la
    historia antes del día siguiente. No redondea: las unidades se redondean solo al medir (redondear_unidades).
    Devuelve store_id, dept_id, date, h y prevision.
    """
    if objetivo not in vp.OBJETIVOS:
        raise ValueError(f"objetivo desconocido: {objetivo}")
    if horizonte < 1:
        raise ValueError("el horizonte es de un día o más")
    origen = pd.Timestamp(historia[COLUMNA_FECHA].max() if origen is None else origen)
    acumulada = ventana_hasta_el_origen(historia, objetivo, origen)
    series = acumulada[CLAVE_SERIE].drop_duplicates()
    dias = [origen + UN_DIA * h for h in range(1, horizonte + 1)]

    # Lo que se sabe de antemano de cada día previsto; fuera la venta real y lo que sale de ella
    exogenas = futuro.drop(columns=_columnas_de_objetivo(futuro.columns))
    exogenas = exogenas.loc[exogenas[COLUMNA_FECHA].isin(dias).to_numpy()]
    rejilla = series.merge(pd.DataFrame({COLUMNA_FECHA: dias}), how="cross")
    cruce = rejilla.merge(exogenas, on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one",
                          indicator=True)
    sin_fila = int((cruce["_merge"] != "both").sum())
    if sin_fila:
        raise ValueError(f"al futuro le faltan {sin_fila} filas de serie y día del horizonte")
    exogenas = cruce.drop(columns="_merge")

    nombres = vp.nombres_variables(objetivo)
    salida = []
    for h, dia in enumerate(dias, start=1):
        # La fila del día que se prevé entra a la historia con la venta vacía: la función nunca mira su propia fila
        del_dia = exogenas[exogenas[COLUMNA_FECHA] == dia]
        nuevo = del_dia[CLAVE_SERIE + [COLUMNA_FECHA]].assign(**{objetivo: np.nan})
        tramo = pd.concat([acumulada, nuevo], ignore_index=True)
        variables = vp.crear_variables_objetivo(tramo, objetivo)
        filas = (tramo[COLUMNA_FECHA] == dia).to_numpy()
        del_tramo = pd.concat([tramo.loc[filas, CLAVE_SERIE + [COLUMNA_FECHA]], variables.loc[filas]], axis=1)
        x = del_dia.merge(del_tramo, on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one")
        if x[nombres].isna().any().any():
            raise ValueError(f"retardos o medias vacíos el {dia:%Y-%m-%d}: falta historia")
        # Una previsión no puede ser negativa (reglas, apartado 6): se acota en cero antes de entrar en la historia
        previsto = np.clip(np.asarray(modelo.predict(x), dtype="float64"), 0.0, None)
        resultado = x[CLAVE_SERIE + [COLUMNA_FECHA]].assign(h=h, prevision=previsto)
        salida.append(resultado)
        acumulada = pd.concat([acumulada, resultado[CLAVE_SERIE + [COLUMNA_FECHA]].assign(**{objetivo: previsto})],
                              ignore_index=True)
        # Solo hacen falta los 28 días anteriores al día siguiente
        acumulada = acumulada[(acumulada[COLUMNA_FECHA] > dia - pd.Timedelta(HISTORIA_NECESARIA, "D")).to_numpy()]
    return pd.concat(salida, ignore_index=True)


# ══ 4. Las tres reglas sencillas (reglas, apartado 7) ═════════════════════════════════════
def reglas_sencillas(historia, objetivo, origen, horizonte):
    """Las tres reglas desde un origen, solo con la venta hasta el origen incluido.

    - repetir la semana anterior: los 7 últimos días, el del origen incluido, repetidos semana a semana;
    - media de los últimos 28 días, el del origen incluido, la misma para todo el horizonte;
    - media del mismo día de la semana en las cuatro semanas que acaban en el origen.
    Devuelve store_id, dept_id, date, h y una columna por regla.
    """
    origen = pd.Timestamp(origen)
    ventana = ventana_hasta_el_origen(historia, objetivo, origen)
    salida = []
    for clave, grupo in ventana.groupby(CLAVE_SERIE, sort=True):
        # v[27] es el origen y v[0], 27 días antes
        v = grupo.sort_values(COLUMNA_FECHA)[objetivo].to_numpy(dtype="float64")
        for h in range(1, horizonte + 1):
            mismo_dia = [v[i] for i in range(HISTORIA_NECESARIA) if (i - (HISTORIA_NECESARIA - 1 + h)) % 7 == 0]
            salida.append({CLAVE_SERIE[0]: clave[0], CLAVE_SERIE[1]: clave[1], COLUMNA_FECHA: origen + UN_DIA * h,
                           "h": h, REGLAS[0]: v[HISTORIA_NECESARIA - 7 + (h - 1) % 7], REGLAS[1]: v.mean(),
                           REGLAS[2]: float(np.mean(mismo_dia))})
    tabla = pd.DataFrame(salida)
    tabla[COLUMNA_FECHA] = tabla[COLUMNA_FECHA].astype(historia[COLUMNA_FECHA].dtype)
    return tabla


# ══ 5. El error del caso (reglas, apartado 6) ════════════════════════════════════════════
def redondear_unidades(valores):
    """Redondea unidades previstas al entero, la mitad hacia arriba (programacion-del-caso, error 9); para si llega
    una previsión negativa, que tendría que venir ya acotada."""
    v = np.asarray(valores, dtype="float64")
    if (v < 0).any():
        raise ValueError(f"{int((v < 0).sum())} previsiones negativas: se acotan en cero antes de redondear")
    return np.floor(v + 0.5)


def error_y_sesgo(real, previsto):
    """El error (suma de las diferencias sin signo entre la suma de lo real, por 100) y el sesgo (lo mismo con signo,
    positivo si la previsión se pasa), sobre todas las filas juntas."""
    r = np.asarray(real, dtype="float64")
    p = np.asarray(previsto, dtype="float64")
    if r.shape != p.shape or r.ndim != 1:
        raise ValueError(f"real y previsto con formas distintas: {r.shape} y {p.shape}")
    if not (np.isfinite(r).all() and np.isfinite(p).all()):
        raise ValueError("vacíos o infinitos en el real o en lo previsto")
    total = r.sum()
    if total <= 0:
        raise ValueError("la venta real suma cero: el error por cada 100 vendidas no existe")
    return float(100 * np.abs(p - r).sum() / total), float(100 * (p - r).sum() / total)


# ══ 6. Pliegues por día ═════════════════════════════════════════════════════════
def pliegues_por_dia(fechas, n_pliegues, horizonte):
    """TimeSeriesSplit sobre los días, sin barajar, con test_size igual al horizonte (aprendizaje-automatico §3).

    Cada pliegue entrena con todos los días anteriores. Devuelve, por pliegue, los días del ajuste, los de la prueba y
    el origen (el último día del ajuste), como fechas.
    """
    dias = np.array(sorted(pd.Series(fechas).unique()))
    pliegues = []
    for ajuste, prueba in TimeSeriesSplit(n_splits=n_pliegues, test_size=horizonte).split(dias):
        pliegues.append({"dias_ajuste": pd.DatetimeIndex(dias[ajuste]), "dias_prueba": pd.DatetimeIndex(dias[prueba]),
                         "origen": pd.Timestamp(dias[ajuste].max())})
    return pliegues


def comprobar_pliegue(dias_ajuste, dias_prueba, horizonte):
    """Comprueba un pliegue: todo el ajuste antes de la prueba, sin días compartidos, y la prueba con los días del
    horizonte seguidos desde el día siguiente al origen."""
    ajuste = pd.DatetimeIndex(dias_ajuste)
    prueba = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dias_prueba).unique()))
    compartidos = int(ajuste.isin(prueba).sum())
    seguidos = len(prueba) > 0 and bool((prueba[1:] - prueba[:-1] == UN_DIA).all())
    bien = (len(ajuste) > 0 and len(prueba) == horizonte and compartidos == 0 and seguidos
            and ajuste.max() < prueba.min() and prueba.min() == ajuste.max() + UN_DIA)
    return {"bien": bool(bien), "dias_ajuste": len(ajuste), "dias_prueba": len(prueba),
            "dias_compartidos": compartidos, "prueba_seguida": seguidos,
            "ajuste_hasta": ajuste.max() if len(ajuste) else None, "prueba_desde": prueba.min() if len(prueba) else None,
            "prueba_hasta": prueba.max() if len(prueba) else None}
