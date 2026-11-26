"""Variables de previsión del caso 69: retardos, medias, productos con precio, eventos y día del mes.

Módulo de funciones, sin nada que se ejecute al importarlo (programacion-del-caso, error 1). Lo usan
scripts/11_variables_modelo.py para entrenar y, después, la previsión recursiva: la misma función de retardos y medias
recibe la historia de una serie, que puede acabar en días previstos, y para cada fila mira solo los días anteriores.

Las reglas salen de config/metodo/04_planteamientos.md §2, decisión 7, de reglas-negocio.md §5 («El
precio», cuestión 001) y de config/modelo/matriz_transformaciones.md, aprobada por el responsable del caso el 24/11/2026.
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import numpy as np
import pandas as pd

# Planteamientos §2, decisión 7: retardos de 1 a 7, 14, 21 y 28 días y medias de 7 y 28 días
RETARDOS = (1, 2, 3, 4, 5, 6, 7, 14, 21, 28)
VENTANAS = (7, 28)
OBJETIVOS = ("unidades", "dolares")
CLAVE_SERIE = ["store_id", "dept_id"]
COLUMNA_FECHA = "date"

# Reglas, apartado 5, «El precio» y cuestión 001: solo cuentan los productos con precio desde cuatro semanas antes
SEMANAS_PREVIAS_CON_PRECIO = 4
COLUMNA_PRODUCTOS = "productos_con_precio_semana_anterior"
PREFIJO_EVENTO = "evento_"


class HuecoDeFecha(ValueError):
    """Una serie con un día que falta o repetido: los retardos por filas dejarían de ser días."""


# ══ 2. Retardos y medias de un objetivo ═════════════════════════════════════════
def nombres_variables(objetivo):
    """Los nombres de las 12 variables de un objetivo, en su orden."""
    return [f"{objetivo}_lag_{k}" for k in RETARDOS] + [f"{objetivo}_media_{w}" for w in VENTANAS]


def comprobar_sin_huecos(historia):
    """Para si alguna serie tiene un día que falta o uno repetido.

    Los retardos y las medias se calculan por filas (shift y rolling): solo son días si cada serie tiene una fila por
    día, sin huecos (transformacion-datos, «Ventanas móviles»; manual 14.16).
    """
    orden = historia.sort_values(CLAVE_SERIE + [COLUMNA_FECHA])
    paso = orden.groupby(CLAVE_SERIE, sort=False)[COLUMNA_FECHA].diff()
    # Máscara por posición, no por etiqueta: con un índice repetido, loc devolvería filas de más (error 8c)
    mascara = (paso.notna() & (paso != pd.Timedelta(1, "D"))).to_numpy()
    malos = orden.loc[mascara, CLAVE_SERIE + [COLUMNA_FECHA]]
    if len(malos):
        primeros = "; ".join(f"{r.store_id} {r.dept_id} {r.date:%Y-%m-%d}" for r in malos.head(5).itertuples())
        raise HuecoDeFecha(f"{len(malos)} días de serie con un hueco o repetidos antes de ellos: {primeros}")


def crear_variables_objetivo(historia, objetivo):
    """Retardos y medias de un objetivo, dentro de cada serie y solo con días anteriores al de la fila.

    historia: una fila por departamento, tienda y día, con store_id, dept_id, date y el objetivo. Puede acabar en días
    previstos (la previsión recursiva) y la fila del día que se prevé puede llevar el objetivo vacío: nunca se mira el
    valor de la propia fila. Devuelve una tabla con el mismo índice que la entrada y las 12 columnas de
    nombres_variables(objetivo); los días sin historia suficiente quedan vacíos.
    """
    if objetivo not in OBJETIVOS:
        raise ValueError(f"objetivo desconocido: {objetivo}; tiene que ser uno de {OBJETIVOS}")
    comprobar_sin_huecos(historia)
    if not historia.index.is_unique:
        raise ValueError("la historia tiene el índice repetido: el resultado no se podría devolver fila a fila")
    # Se ordena por serie y fecha y se calcula dentro de cada serie (manual 11.9): el primer día de una serie no
    # puede tomar el último de la anterior
    orden = historia.sort_values(CLAVE_SERIE + [COLUMNA_FECHA])
    grupo = orden.groupby(CLAVE_SERIE, sort=False)[objetivo]
    salida = pd.DataFrame(index=orden.index)
    for k in RETARDOS:
        salida[f"{objetivo}_lag_{k}"] = grupo.shift(k).astype("float64")
    # La media acaba el día anterior: shift(1) antes de la ventana (manual 14.10), que pide los w días completos
    anterior = grupo.shift(1).astype("float64")
    for w in VENTANAS:
        salida[f"{objetivo}_media_{w}"] = (anterior.groupby([orden[c] for c in CLAVE_SERIE], sort=False)
                                           .transform(lambda s, w=w: s.rolling(w, min_periods=w).mean()))
    return salida.loc[historia.index]


def comprobar_retardos_y_medias(tabla, objetivo):
    """Rehace cada retardo y cada media por otro camino y cuenta las filas que no coinciden.

    En vez de desplazar filas, une a cada fila el valor de su misma serie en la fecha t - k (merge por serie y fecha).
    Así un retardo que toma el día de su fila, una media que lo incluye o un primer día que toma un dato de otra serie
    salen distintos. Dos vacíos cuentan como iguales.
    """
    base = tabla[CLAVE_SERIE + [COLUMNA_FECHA, objetivo]]
    valores = base.rename(columns={COLUMNA_FECHA: "_fecha", objetivo: "_valor"})
    hasta = max(max(RETARDOS), max(VENTANAS))
    previos = {}
    for k in range(1, hasta + 1):
        clave = base[CLAVE_SERIE].assign(_fecha=base[COLUMNA_FECHA] - pd.Timedelta(k, "D"))
        unido = clave.merge(valores, on=CLAVE_SERIE + ["_fecha"], how="left", validate="many_to_one")
        previos[k] = unido["_valor"].to_numpy(dtype="float64")
    distintas = np.zeros(len(tabla), dtype=bool)
    detalle = {}
    esperadas = {f"{objetivo}_lag_{k}": previos[k] for k in RETARDOS}
    for w in VENTANAS:
        # La media es vacía si falta alguno de sus w días
        esperadas[f"{objetivo}_media_{w}"] = np.vstack([previos[k] for k in range(1, w + 1)]).mean(axis=0)
    for nombre, esperado in esperadas.items():
        actual = tabla[nombre].to_numpy(dtype="float64")
        iguales = np.isclose(actual, esperado, rtol=0, atol=1e-9) | (np.isnan(actual) & np.isnan(esperado))
        detalle[nombre] = int((~iguales).sum())
        distintas |= ~iguales
    return {"filas_distintas": int(distintas.sum()), "por_variable": detalle}


# ══ 3. Productos del departamento con precio la semana anterior ═══════════════════
def orden_de_semanas(calendario):
    """Las semanas de Walmart en el orden de sus fechas: el código salta al cambiar de año."""
    return [int(w) for w in calendario.groupby("wm_yr_wk")[COLUMNA_FECHA].min().sort_values().index]


def contar_productos_que_cuentan(precios, dim_producto, orden_semanas):
    """Por tienda, departamento y semana, cuántos productos tienen precio esa semana y ya lo tenían
    SEMANAS_PREVIAS_CON_PRECIO semanas antes.

    Es la regla del precio medio (reglas, apartado 5, «El precio»; cuestión 001), la misma que precio_medio_semana de
    scripts/05_transformacion_datos.py §5.5: un producto entra la semana de su primera venta y no vuelve a quedarse sin
    precio, así que cuenta si su semana está a cuatro o más posiciones de su primera semana con precio en esa tienda.
    La posición sale del orden de las fechas, no del código.
    """
    posicion = {int(w): i for i, w in enumerate(orden_semanas)}
    con_dept = precios.merge(dim_producto[["item_id", "dept_id"]], on="item_id", how="left",
                             validate="many_to_one", indicator=True)
    sin_dept = int((con_dept["_merge"] != "both").sum())
    if sin_dept:
        raise ValueError(f"{sin_dept} precios de productos sin departamento en dim_producto")
    pos = con_dept["wm_yr_wk"].map(posicion)
    if pos.isna().any():
        raise ValueError(f"{int(pos.isna().sum())} precios de semanas que no están en el Calendario")
    primera = pos.groupby([con_dept["store_id"], con_dept["item_id"]], sort=False).transform("min")
    cuenta = ((pos - primera) >= SEMANAS_PREVIAS_CON_PRECIO).astype("int64")
    return (con_dept.assign(_cuenta=cuenta)
            .groupby(["store_id", "dept_id", "wm_yr_wk"], sort=True)
            .agg(**{COLUMNA_PRODUCTOS: ("_cuenta", "sum")})
            .reset_index())


def anadir_productos_con_precio(tabla, conteo):
    """Une a cada día el conteo de su semana anterior (wm_yr_wk_anterior), por tienda y departamento.

    Una semana anterior sin ningún precio del departamento vale 0 productos; un día sin semana anterior queda vacío.
    """
    derecha = conteo.rename(columns={"wm_yr_wk": "wm_yr_wk_anterior"})
    derecha["wm_yr_wk_anterior"] = derecha["wm_yr_wk_anterior"].astype("Int64")
    izquierda = tabla.copy()
    izquierda["wm_yr_wk_anterior"] = izquierda["wm_yr_wk_anterior"].astype("Int64")
    unido = izquierda.merge(derecha, on=["store_id", "dept_id", "wm_yr_wk_anterior"], how="left",
                            validate="many_to_one")
    unido.index = tabla.index
    sin_cuenta = unido[COLUMNA_PRODUCTOS].isna() & unido["wm_yr_wk_anterior"].notna()
    unido.loc[sin_cuenta, COLUMNA_PRODUCTOS] = 0
    unido[COLUMNA_PRODUCTOS] = unido[COLUMNA_PRODUCTOS].astype("Int64")
    return unido


# ══ 4. Eventos y día del mes ═══════════════════════════════════════════════════
def lista_eventos(entrenamiento):
    """Los eventos que aparecen en event_name_1 o event_name_2 del entrenamiento, ordenados."""
    nombres = pd.concat([entrenamiento["event_name_1"], entrenamiento["event_name_2"]]).dropna().unique()
    return sorted(str(n) for n in nombres)


def anadir_eventos(tabla, eventos):
    """Una columna evento_<nombre> por evento de la lista, a 1 si el día lo tiene en cualquiera de las dos columnas."""
    salida = tabla.copy()
    for nombre in eventos:
        salida[f"{PREFIJO_EVENTO}{nombre}"] = ((tabla["event_name_1"] == nombre).fillna(False)
                                               | (tabla["event_name_2"] == nombre).fillna(False)).astype("int64")
    return salida


def anadir_dia_del_mes(tabla):
    """El día del mes de date, de 1 a 31."""
    salida = tabla.copy()
    salida["dia_del_mes"] = tabla[COLUMNA_FECHA].dt.day.astype("int64")
    return salida
