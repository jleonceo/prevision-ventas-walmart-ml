"""Módulo de producción del caso 69: el Pipeline de cada modelo, los pasos que no aprenden y los que necesitan otras filas.

Módulo de funciones, sin nada que se ejecute al importarlo (programacion-del-caso, error 1). Lo usan
produccion/reentrenar.py y produccion/ejecutar.py. El modelo guardado con joblib lleva una referencia a la clase
EventosDelEntrenamiento de este módulo: para cargarlo, scripts/ tiene que estar en la ruta de importación (manual 39.7).

Sigue el contrato de producción aprobado por el responsable del caso el 25/11/2026 («Apruebo el contrato»; registro R-021;
config/modelo/contrato_produccion.md e informes/preproduccion.json) con el método preproduccion, apartado 2.1 y
pipelines.md. Lo que hace cada paso lo dicen las fichas del registro de transformaciones:
  - no aprende: R-001 (la fecha), R-002 (los SNAP en minúsculas), T-003 (la semana anterior), R-007 y R-008 (las
    dimensiones), R-004 (la venta por serie en céntimos), R-016 (el día del mes), R-015 (una columna por evento) y R-018
    (el modelo toma sus columnas por nombre);
  - necesita otras filas: R-009 (precio medio), R-014 (productos con precio), R-012 y R-013 (retardos y medias), con la
    historia que ya lleva lo previsto;
  - aprende, dentro del Pipeline: R-015 (la lista de eventos), R-011 (codificar y escalar) y el modelo.
Los pasos que quitan filas (R-010 y R-017) no están aquí: van solo en produccion/reentrenar.py.

Reutiliza sin cambiarlos scripts/variables_prevision.py (retardos y medias, productos con precio, eventos, día del mes),
scripts/preparacion_prevision.py (el nombre de las columnas codificadas) y scripts/prevision_recursiva.py (la previsión
día a día, la misma que usó la validación). Ninguno ejecuta nada al importarse: solo definen constantes y funciones.

Las ramas de event_name_1 y event_name_2 del preprocesador del desarrollo no están: sus columnas no entran en el modelo
(reglas, apartado 7) y el primer reentreno comprobó que sin ellas la previsión sale igual (petición 27, punto 2).
"""

# ══ 1. Configuración ════════════════════════════════════════════════════════════
import hashlib
import json
import platform
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler, StandardScaler
from sklearn.utils.validation import check_is_fitted

import prevision_recursiva as pr
import variables_prevision as vp
from preparacion_prevision import combinar_categoria

CLAVE_SERIE = vp.CLAVE_SERIE
COLUMNA_FECHA = vp.COLUMNA_FECHA
OBJETIVOS = vp.OBJETIVOS
# R-015: los eventos de un día vienen en estos dos campos del calendario
COLUMNAS_EVENTO = ["event_name_1", "event_name_2"]
# R-002 y R-004: el SNAP de cada estado, con su nombre ya en minúsculas
SNAP_DE_ESTADO = {"CA": "snap_ca", "TX": "snap_tx", "WI": "snap_wi"}
# Las columnas de las tres entradas, con la forma de data/raw/ (diccionario de datos del origen)
COLUMNAS_VENTA = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
COLUMNAS_PRECIOS = ["store_id", "item_id", "wm_yr_wk", "sell_price"]
COLUMNAS_CALENDARIO = ["date", "wm_yr_wk", "weekday", "wday", "month", "year", "d", "event_name_1", "event_type_1",
                       "event_name_2", "event_type_2", "snap_CA", "snap_TX", "snap_WI"]
NUMERICAS_CALENDARIO = ["wm_yr_wk", "wday", "month", "year", "snap_CA", "snap_TX", "snap_WI"]
NUMERICAS_PRECIOS = ["wm_yr_wk", "sell_price"]
PREFIJO_DIA = "d_"
FORMATO_FECHA = "%Y-%m-%d"   # R-001: la fecha del calendario se lee con su formato explícito
# Las columnas que salen de la historia: si una falta en una fila, esa fila no tiene la historia que piden
COLUMNAS_DE_HISTORIA = ["precio_medio_semana_anterior"] + [n for o in OBJETIVOS for n in vp.nombres_variables(o)]
# El paso del preprocesador de cada finalista, tal como lo escribe el contrato, y la rama a la que va
RAMA_DEL_PASO = {"OneHotEncoder": "ohe", "StandardScaler": "ss", "RobustScaler": "rs"}
ORDEN_RAMAS = ("ohe", "eventos", "pasa", "ss", "rs")
SUFIJO_RAMA = {"ss": "_ss", "rs": "_rs"}


class EntradaNoValida(ValueError):
    """Una entrada sin una columna que pide el contrato, con un número escrito como texto o con un dato imposible."""


class FichaQueNoCuadra(RuntimeError):
    """El modelo guardado no casa con su ficha: otras versiones o un fichero distinto del que se guardó."""


# ══ 2. La receta, leída del contrato ════════════════════════════════════════════
def receta_del_contrato(contrato, objetivo):
    """La receta de un objetivo con las ramas del preprocesador, leída de informes/preproduccion.json.

    Cada finalista va a su rama por el paso del preprocesador que trae su cadena: OneHotEncoder, StandardScaler,
    RobustScaler o «pasa tal cual»; evento_<nombre> va a la rama de los eventos, que aprende su lista (R-015). Las
    columnas del modelo y los hiperparámetros son los de la receta del contrato. Para si alguna columna del modelo no
    sale de ninguna finalista o si una finalista no tiene paso del preprocesador.
    """
    datos = contrato["objetivos"][objetivo]
    ramas = {r: [] for r in ORDEN_RAMAS}
    de_finalistas = []
    for f in datos["finalistas"]:
        variable = f["variable"]
        paso = next((p["paso"] for p in f["cadena"] if p.get("etapa") == "preprocesador"), None)
        if paso is None:
            raise ValueError(f"la finalista {variable} no tiene paso del preprocesador en el contrato")
        if variable == "evento_<nombre>":
            ramas["eventos"] = list(COLUMNAS_EVENTO)
        elif paso.endswith("pasa tal cual"):
            ramas["pasa"].append(variable)
        else:
            rama = RAMA_DEL_PASO.get(paso.split(" ", 1)[0])
            if rama is None:
                raise ValueError(f"el paso del preprocesador de {variable} no es de ninguna rama conocida: {paso}")
            ramas[rama].append(variable)
        de_finalistas += f["columnas_del_modelo"]
    receta = datos["receta"]
    columnas = list(receta["columnas"])
    sin_finalista = sorted(set(columnas) - set(de_finalistas))
    if sin_finalista or len(columnas) != len(set(columnas)):
        raise ValueError(f"columnas del modelo sin finalista o repetidas: {sin_finalista}")
    return {"objetivo": objetivo, "algoritmo": receta["algoritmo"], "semilla": receta["semilla"],
            "hiperparametros": dict(receta["hiperparametros"]), "columnas": columnas,
            "ramas": {r: v for r, v in ramas.items() if v}}


def columnas_de_entrada(receta):
    """Las columnas que entran al Pipeline de una receta, por nombre y en el orden de sus ramas."""
    return [c for r in ORDEN_RAMAS for c in receta["ramas"].get(r, [])]


# ══ 3. Las entradas con la forma de data/raw/ ════════════════════════════════════
def comprobar_columnas(tabla, columnas, nombre):
    """Para con un mensaje claro si a la tabla le falta alguna de las columnas que pide el contrato."""
    faltan = [c for c in columnas if c not in tabla.columns]
    if faltan:
        raise EntradaNoValida(f"a {nombre} le faltan columnas: {faltan}")


def comprobar_numericas(tabla, columnas, nombre):
    """Para con un mensaje claro si una columna numérica llega como texto (error 5)."""
    texto = [c for c in columnas if not pd.api.types.is_numeric_dtype(tabla[c])]
    if texto:
        raise EntradaNoValida(f"en {nombre} llegan como texto columnas que son números: {texto[:5]}")


def preparar_calendario(calendario):
    """R-001, R-002 y T-003: la fecha con su formato, los SNAP en minúsculas y la semana anterior por las fechas.

    La semana anterior se toma por el orden de las fechas, porque el código de la semana salta al cambiar de año. Para
    si una fecha no se lee con el formato año-mes-día.
    """
    comprobar_columnas(calendario, COLUMNAS_CALENDARIO, "el calendario")
    comprobar_numericas(calendario, NUMERICAS_CALENDARIO, "el calendario")
    salida = calendario.copy()
    fecha = pd.to_datetime(salida["date"], format=FORMATO_FECHA, errors="coerce")
    no_se_leen = int((fecha.isna() & salida["date"].notna()).sum())
    if no_se_leen or fecha.isna().any():
        raise EntradaNoValida(f"{no_se_leen} fechas del calendario no se leen con el formato {FORMATO_FECHA}")
    salida["date"] = fecha
    salida = salida.rename(columns={c: c.lower() for c in salida.columns if c.startswith("snap_")})
    salida = salida.sort_values(COLUMNA_FECHA, kind="stable").reset_index(drop=True)
    orden = vp.orden_de_semanas(salida)
    anterior = dict(zip(orden[1:], orden[:-1]))
    salida["wm_yr_wk_anterior"] = salida["wm_yr_wk"].map(anterior).astype("Int64")
    return salida


def dimensiones(venta):
    """R-007 y R-008: una fila por producto con su departamento y su categoría, y una por tienda con su estado.

    Para si un producto aparece con dos departamentos o una tienda con dos estados.
    """
    dim_producto = venta[["item_id", "dept_id", "cat_id"]].drop_duplicates().sort_values("item_id", kind="stable")
    dim_tienda = venta[["store_id", "state_id"]].drop_duplicates().sort_values("store_id", kind="stable")
    if dim_producto["item_id"].duplicated().any() or dim_tienda["store_id"].duplicated().any():
        raise EntradaNoValida("un producto con dos departamentos o una tienda con dos estados en la venta")
    return dim_producto.reset_index(drop=True), dim_tienda.reset_index(drop=True)


def columnas_de_dias(venta):
    """Las columnas de día de la venta (d_1, d_2…), en el orden de la tabla."""
    return [c for c in venta.columns if str(c).startswith(PREFIJO_DIA)]


def venta_por_serie(venta, precios, calendario, dim_producto, dias):
    """R-004: la venta de cada producto de los días pedidos, unida al calendario y al precio y sumada por serie y día.

    Los dólares se suman en céntimos enteros (unidades por el precio de su semana en céntimos) y pasan a dólares con dos
    decimales, como scripts/05_transformacion_datos.py. Un día sin precio suma cero dólares; un día con venta y sin
    precio para (reglas, apartado 5). Un producto con la venta vacía deja vacío el día de su serie: no se sabe cuánto vendió y un
    cero de relleno no se distingue de una venta de cero. Devuelve store_id, dept_id, date, unidades y dolares.
    """
    larga = venta.melt(id_vars=["item_id", "store_id"], value_vars=list(dias), var_name="d", value_name="unidades")
    larga = larga.merge(calendario[["d", "date", "wm_yr_wk"]], on="d", how="left", validate="many_to_one")
    if larga["date"].isna().any():
        raise EntradaNoValida(f"días de la venta que no están en el calendario: {sorted(larga.loc[larga['date'].isna(), 'd'].unique())[:5]}")
    larga = larga.merge(precios[COLUMNAS_PRECIOS], on=["item_id", "store_id", "wm_yr_wk"], how="left",
                        validate="many_to_one")
    unidades = larga["unidades"].to_numpy(dtype="float64")
    if (unidades < 0).any():
        raise EntradaNoValida(f"{int((unidades < 0).sum())} ventas negativas: el trabajo para (reglas, apartado 5)")
    sin_precio = larga["sell_price"].isna().to_numpy()
    con_venta_sin_precio = int((sin_precio & (unidades > 0)).sum())
    if con_venta_sin_precio:
        raise EntradaNoValida(f"{con_venta_sin_precio} días con venta y sin precio: el trabajo para (reglas, apartado 5)")
    centimos_precio = np.where(sin_precio, 0, np.rint(larga["sell_price"].fillna(0).to_numpy() * 100))
    larga["centimos"] = unidades * centimos_precio
    larga["vacio"] = np.isnan(unidades)
    larga = larga.merge(dim_producto[["item_id", "dept_id"]], on="item_id", how="left", validate="many_to_one")
    series = (larga.groupby(["store_id", "dept_id", "date"], sort=True)
              .agg(unidades=("unidades", "sum"), centimos=("centimos", "sum"), vacios=("vacio", "sum"))
              .reset_index())
    vacia = series["vacios"].to_numpy() > 0
    series["dolares"] = np.round(series["centimos"].to_numpy(dtype="float64") / 100, 2)
    series.loc[vacia, ["unidades", "dolares"]] = np.nan
    return series[CLAVE_SERIE + [COLUMNA_FECHA, "unidades", "dolares"]]


def precio_y_productos_por_semana(precios, dim_producto, calendario):
    """R-009 y R-014: por tienda, departamento y semana, el precio medio y cuántos productos cuentan.

    Solo cuentan los productos con precio esa semana que ya lo tenían cuatro semanas antes, con las semanas en el orden
    de sus fechas (reglas, apartado 5, «El precio»). La media es simple y no se redondea; queda vacía si no cuenta ninguno. Es la
    regla de scripts/05_transformacion_datos.py (precio_medio_semana) y de variables_prevision.contar_productos_que_cuentan.
    """
    orden = vp.orden_de_semanas(calendario)
    posicion = {int(w): i for i, w in enumerate(orden)}
    con_dept = precios[COLUMNAS_PRECIOS].merge(dim_producto[["item_id", "dept_id"]], on="item_id", how="left",
                                               validate="many_to_one")
    if con_dept["dept_id"].isna().any():
        raise EntradaNoValida(f"{int(con_dept['dept_id'].isna().sum())} precios de productos que no están en la venta")
    pos = con_dept["wm_yr_wk"].map(posicion)
    if pos.isna().any():
        raise EntradaNoValida(f"{int(pos.isna().sum())} precios de semanas que no están en el calendario")
    primera = pos.groupby([con_dept["store_id"], con_dept["item_id"]], sort=False).transform("min")
    cuenta = (pos - primera) >= vp.SEMANAS_PREVIAS_CON_PRECIO
    medio = (con_dept.assign(precio_que_cuenta=con_dept["sell_price"].where(cuenta))
             .groupby(["store_id", "dept_id", "wm_yr_wk"], sort=True)
             .agg(precio_medio_semana_anterior=("precio_que_cuenta", "mean")).reset_index())
    conteo = vp.contar_productos_que_cuentan(precios[COLUMNAS_PRECIOS], dim_producto, orden)
    return medio.merge(conteo, on=["store_id", "dept_id", "wm_yr_wk"], how="outer", validate="one_to_one")


def tabla_del_futuro(series, dias, calendario, dim_tienda, por_semana):
    """Lo que se sabe de antemano de cada serie y día: calendario, snap, precio de la semana anterior y día del mes.

    Es lo que entra al Pipeline sin el objetivo: R-004 (las columnas del calendario y el snap del estado de la tienda),
    R-009 y R-014 (unidos por la semana anterior del día) y R-016. El objetivo no está: al prever llega vacío, nunca
    a cero. Para si un día no está en el calendario o una tienda es de un estado sin columna de SNAP.
    """
    rejilla = series[CLAVE_SERIE].drop_duplicates().merge(pd.DataFrame({COLUMNA_FECHA: pd.to_datetime(list(dias))}),
                                                           how="cross")
    columnas_cal = ["date", "d", "year", "month", "weekday", "wday", "wm_yr_wk", "wm_yr_wk_anterior"] + \
        COLUMNAS_EVENTO + list(SNAP_DE_ESTADO.values())
    tabla = rejilla.merge(calendario[columnas_cal], on=COLUMNA_FECHA, how="left", validate="many_to_one",
                          indicator=True)
    if (tabla["_merge"] != "both").any():
        raise EntradaNoValida("días a prever que no están en el calendario")
    tabla = tabla.drop(columns="_merge").merge(dim_tienda, on="store_id", how="left", validate="many_to_one")
    desconocidos = sorted(set(tabla["state_id"].dropna()) - set(SNAP_DE_ESTADO))
    if desconocidos or tabla["state_id"].isna().any():
        raise EntradaNoValida(f"tiendas de un estado sin columna de SNAP: {desconocidos or ['vacío']}")
    tabla["snap"] = np.select([tabla["state_id"] == e for e in SNAP_DE_ESTADO],
                              [tabla[c] for c in SNAP_DE_ESTADO.values()], default=-1).astype("int64")
    tabla = tabla.drop(columns=list(SNAP_DE_ESTADO.values()))
    precio = por_semana[["store_id", "dept_id", "wm_yr_wk", "precio_medio_semana_anterior"]].rename(
        columns={"wm_yr_wk": "wm_yr_wk_anterior"})
    precio["wm_yr_wk_anterior"] = precio["wm_yr_wk_anterior"].astype("Int64")
    tabla = tabla.merge(precio, on=["store_id", "dept_id", "wm_yr_wk_anterior"], how="left", validate="many_to_one")
    conteo = por_semana[["store_id", "dept_id", "wm_yr_wk", vp.COLUMNA_PRODUCTOS]].dropna(
        subset=[vp.COLUMNA_PRODUCTOS])
    tabla = vp.anadir_productos_con_precio(tabla, conteo)
    return vp.anadir_dia_del_mes(tabla)


def tabla_con_variables(venta, precios, calendario_crudo):
    """La tabla de series con todas sus variables, de una venta, unos precios y un calendario con la forma de data/raw/.

    Une R-004 de todos los días de la venta con lo que se sabe de antemano (tabla_del_futuro) y añade los retardos y
    las medias de los dos objetivos (R-012 y R-013), cada uno con días anteriores de su serie. Es la forma de la tabla
    de entrenamiento que recibe produccion/reentrenar.py; no quita ninguna fila: los primeros días, sin historia,
    quedan con sus variables vacías y los quita el reentreno (R-017).
    """
    comprobar_columnas(venta, COLUMNAS_VENTA, "la venta")
    comprobar_columnas(precios, COLUMNAS_PRECIOS, "los precios")
    comprobar_numericas(venta, columnas_de_dias(venta), "la venta")
    comprobar_numericas(precios, NUMERICAS_PRECIOS, "los precios")
    calendario = preparar_calendario(calendario_crudo)
    dim_producto, dim_tienda = dimensiones(venta)
    series = venta_por_serie(venta, precios, calendario, dim_producto, columnas_de_dias(venta))
    por_semana = precio_y_productos_por_semana(precios, dim_producto, calendario)
    conocidas = tabla_del_futuro(series, sorted(series[COLUMNA_FECHA].unique()), calendario, dim_tienda, por_semana)
    tabla = conocidas.merge(series, on=CLAVE_SERIE + [COLUMNA_FECHA], how="left", validate="one_to_one")
    tabla = tabla.sort_values(CLAVE_SERIE + [COLUMNA_FECHA], kind="stable").reset_index(drop=True)
    for objetivo in OBJETIVOS:
        tabla = tabla.join(vp.crear_variables_objetivo(tabla, objetivo))
    return tabla


# ══ 4. Los eventos: la lista aprende, la columna no (R-015) ═════════════════════
class EventosDelEntrenamiento(TransformerMixin, BaseEstimator):
    """Una columna evento_<nombre> de 0 y 1 por evento de la lista, a 1 si el día lo trae en cualquiera de los dos
    campos.

    La lista se aprende en el fit, con los días de entrenamiento (R-015, «aprende»); un evento que solo aparece al prever
    no crea columna. Usa variables_prevision.lista_eventos y anadir_eventos, las de scripts/11_variables_modelo.py.
    """

    def fit(self, X, y=None):
        """Aprende la lista de eventos de event_name_1 y event_name_2 del entrenamiento."""
        comprobar_columnas(X, COLUMNAS_EVENTO, "la entrada de los eventos")
        self.eventos_ = vp.lista_eventos(X)
        return self

    def transform(self, X):
        """Las columnas evento_<nombre> de la lista aprendida, con el mismo índice que la entrada."""
        check_is_fitted(self, "eventos_")
        comprobar_columnas(X, COLUMNAS_EVENTO, "la entrada de los eventos")
        salida = vp.anadir_eventos(X[COLUMNAS_EVENTO], self.eventos_)
        return salida[[f"{vp.PREFIJO_EVENTO}{e}" for e in self.eventos_]]

    def get_feature_names_out(self, input_features=None):
        """Los nombres de las columnas que saca: evento_<nombre>, en el orden de la lista."""
        check_is_fitted(self, "eventos_")
        return np.asarray([f"{vp.PREFIJO_EVENTO}{e}" for e in self.eventos_], dtype=object)


# ══ 5. El Pipeline ══════════════════════════════════════════════════════════════
def nombre_de_salida(transformador, columna):
    """El nombre de una columna de salida: _ss y _rs en las escaladas; las demás, tal cual (catálogo de sufijos)."""
    return f"{columna}{SUFIJO_RAMA.get(transformador, '')}"


def construir_pipeline(receta):
    """El Pipeline de una receta, nuevo en cada llamada (pipelines.md, regla 14), sin ajustar.

    preprocesador: un ColumnTransformer con una rama por grupo, por nombre (R-011 y R-015), remainder fijado a drop y
    handle_unknown en el codificador; columnas: el modelo toma por su nombre las columnas del ganador en su orden
    (R-018); modelo: HistGradientBoosting con los hiperparámetros de la receta.
    """
    ramas = receta["ramas"]
    piezas = {"ohe": lambda: OneHotEncoder(handle_unknown="ignore", sparse_output=False, drop=None,
                                           feature_name_combiner=combinar_categoria),
              "eventos": EventosDelEntrenamiento, "pasa": lambda: "passthrough",
              "ss": StandardScaler, "rs": RobustScaler}
    transformadores = [(r, piezas[r](), list(ramas[r])) for r in ORDEN_RAMAS if ramas.get(r)]
    preprocesador = ColumnTransformer(transformadores, remainder="drop",
                                      verbose_feature_names_out=nombre_de_salida).set_output(transform="pandas")
    seleccion = ColumnTransformer([("columnas", "passthrough", list(receta["columnas"]))], remainder="drop",
                                  verbose_feature_names_out=False).set_output(transform="pandas")
    if receta.get("algoritmo", "HistGradientBoosting") != "HistGradientBoosting":
        raise ValueError(f"algoritmo que el contrato no prevé: {receta.get('algoritmo')}")
    modelo = HistGradientBoostingRegressor(**receta["hiperparametros"])
    return Pipeline([("preprocesador", preprocesador), ("columnas", seleccion), ("modelo", modelo)])


def comprobar_columnas_de_salida(pipe, esperadas):
    """Para si el preprocesador ajustado no saca exactamente las columnas esperadas (remainder="drop" tira en silencio)
    o si el modelo no las recibe en el orden de la receta; devuelve las de salida, ordenadas."""
    salen = list(pipe.named_steps["preprocesador"].get_feature_names_out())
    faltan = [c for c in esperadas if c not in salen]
    sobran = [c for c in salen if c not in esperadas]
    if faltan or sobran:
        raise ValueError(f"columnas de salida distintas de las del contrato; faltan {faltan}, sobran {sobran}")
    al_modelo = list(getattr(pipe.named_steps["modelo"], "feature_names_in_", []))
    if al_modelo != list(esperadas):
        raise ValueError("el modelo no recibe las columnas del contrato en su orden")
    return sorted(salen)


def _valor_json(v):
    """Un parámetro como valor de JSON: los objetos, por su nombre."""
    return v if isinstance(v, (str, int, float, bool, type(None))) else repr(v)


def inspeccion(pipe):
    """La inspección del Pipeline ajustado: pasos, ramas con sus columnas, remainder, columnas de salida, parámetros
    del modelo, iteraciones y la lista de eventos aprendida (manual 39.6)."""
    pre = pipe.named_steps["preprocesador"]
    modelo = pipe.named_steps["modelo"]
    ramas = [{"nombre": n, "transformador": t if isinstance(t, str) else type(t).__name__, "columnas": list(c)}
             for n, t, c in pre.transformers_ if n != "remainder"]
    eventos = next((list(t.eventos_) for n, t, _ in pre.transformers_ if n == "eventos"), [])
    return {"pasos": list(pipe.named_steps), "ramas": ramas, "remainder": pre.remainder,
            "columnas_salida_preprocesador": list(pre.get_feature_names_out()),
            "columnas_modelo": list(modelo.feature_names_in_),
            "modelo": {"clase": type(modelo).__name__,
                       "parametros": {k: _valor_json(v) for k, v in modelo.get_params().items()},
                       "n_iter": int(modelo.n_iter_)},
            "eventos_aprendidos": eventos}


def lleva_filas_de_entrenamiento(pipe, n_filas):
    """Mira en el objeto, y no por el nombre del algoritmo, si guarda filas de entrenamiento (método, apartado 2.2, paso 5).

    Busca en los atributos de cada pieza cualquier matriz o tabla con tantas filas como el entrenamiento.
    """
    piezas = [(n, p) for n, p in pipe.named_steps.items()]
    for n, p in list(piezas):
        for nombre, t, _ in getattr(p, "transformers_", []):
            if not isinstance(t, str):
                piezas.append((f"{n}.{nombre}", t))
    sospechosos = []
    for n, p in piezas:
        for atributo, valor in vars(p).items():
            # Solo las matrices y tablas de verdad: una clase guardada como atributo también tiene «shape»
            forma = getattr(valor, "shape", None) if not isinstance(valor, type) else None
            if isinstance(forma, tuple) and len(forma) >= 1 and forma[0] == n_filas:
                sospechosos.append(f"{n}.{atributo}")
    return {"lleva": bool(sospechosos), "atributos": sospechosos, "filas_entrenamiento": int(n_filas)}


# ══ 6. Guardar y cargar con su ficha (manual 39.7 y 39.11) ══════════════════════
def huella(ruta):
    """SHA-256 de un fichero, leído por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def versiones():
    """Las versiones que deciden si un modelo guardado se puede cargar aquí."""
    return {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
            "numpy": np.__version__, "joblib": joblib.__version__}


def guardar_modelo(pipe, ruta, **datos):
    """Guarda el pipe con joblib y, al lado, su ficha <nombre>_versiones.json con versiones, huella y fecha."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, ruta)
    ficha = {"fecha": datetime.now().isoformat(timespec="seconds"), "fichero": ruta.name, "huella": huella(ruta),
             "versiones": versiones()} | datos
    ruta.with_name(f"{ruta.stem}_versiones.json").write_text(json.dumps(ficha, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
    return ficha


def cargar_modelo(ruta):
    """Carga el pipe solo si su ficha cuadra: mismas versiones de scikit-learn y pandas, y el mismo fichero.

    Un joblib ejecuta código al abrirse: la ficha se lee antes y se para si algo no cuadra.
    """
    ruta_ficha = ruta.with_name(f"{ruta.stem}_versiones.json")
    if not ruta.exists() or not ruta_ficha.exists():
        raise FichaQueNoCuadra(f"falta el modelo {ruta.name} o su ficha {ruta_ficha.name}")
    ficha = json.loads(ruta_ficha.read_text(encoding="utf-8"))
    actuales = versiones()
    distintas = {k: (ficha["versiones"].get(k), actuales[k]) for k in ("scikit-learn", "pandas")
                 if ficha["versiones"].get(k) != actuales[k]}
    if distintas:
        raise FichaQueNoCuadra(f"el modelo se guardó con otras versiones (guardado, actual): {distintas}")
    if huella(ruta) != ficha["huella"]:
        raise FichaQueNoCuadra(f"{ruta.name} no es el fichero que se guardó: su huella no coincide con la de la ficha")
    return joblib.load(ruta), ficha


# ══ 7. Prever ═══════════════════════════════════════════════════════════════════
def prever(modelo, historia, futuro, objetivo, horizonte, origen):
    """La previsión recursiva desde el origen, día a día, con prevision_recursiva.prever_recursivo.

    Es la función que usó la validación: corta la historia en el origen, calcula los retardos y las medias de cada día
    con la historia que ya lleva lo previsto, une por serie y fecha, acota en cero antes de escribir la previsión en la
    historia y no redondea. Devuelve store_id, dept_id, date, h y prevision_sin_redondear.
    """
    resultado = pr.prever_recursivo(modelo, historia, futuro, objetivo, horizonte, origen=origen)
    return resultado.rename(columns={"prevision": "prevision_sin_redondear"})


def redondear_salida(valores, objetivo):
    """La previsión de la salida: las unidades, al entero con la mitad hacia arriba; los dólares, sin redondear."""
    v = np.asarray(valores, dtype="float64")
    if objetivo == "unidades":
        salida = np.full_like(v, np.nan)
        hay = ~np.isnan(v)
        salida[hay] = pr.redondear_unidades(v[hay])
        return salida
    return v
