"""Medidas, tablas y gráficos técnicos para evaluar un modelo supervisado que predice una cantidad.

Guía de uso: `01_guia_evaluacion.md`, en esta misma carpeta. Banco: `probar_evaluacion_continua.py`.

Solo vale para modelos supervisados con un objetivo numérico (un importe, unas unidades, unos días). No vale para
modelos de sí o no (`../evaluacion_modelo_binario/`), agrupación ni supervivencia. La previsión de una serie usa las
mismas medidas, pero su partición y su referencia las pone la guía, §9.

Todas las funciones reciben el valor real y el previsto, sobre filas que el modelo no ha visto. Paran con un
ValueError que dice qué falla si les llegan longitudes distintas, vacíos, infinitos, una tabla en lugar de una
columna, ninguna fila o un objetivo constante (con él, el R² no existe).

- medidas: el error en las unidades del objetivo (MAE, RMSE, mediana), el R², el sesgo, el WAPE y el MAPE solo
  cuando tiene sentido;
- referencia_media: la predicción más sencilla, la media de desarrollo, que todo modelo tiene que superar;
- comparar_modelos: las medidas de varios modelos sobre las mismas filas, con la mejora sobre la última, que es la
  referencia;
- error_por_tramo: dónde falla el modelo, por tramos del valor real;
- desarrollo_frente_a_validacion: el error en las filas del ajuste y en las nuevas, para ver el sobreajuste;
- intervalo e intervalo_diferencia: el intervalo del 95 % de una medida, o de la diferencia entre dos modelos, por
  remuestreo de filas;
- figura_real_frente_a_prevision y figura_residuos: gráficos técnicos en matplotlib, para el informe interno de
  auditoría del modelo.
"""

# matplotlib dibuja los gráficos técnicos
import matplotlib.pyplot as plt
# numpy hace las cuentas
import numpy as np
# pandas devuelve las tablas
import pandas as pd
# Las medidas de referencia de scikit-learn
from sklearn.metrics import (mean_absolute_error, mean_absolute_percentage_error, mean_squared_error,
                             median_absolute_error, r2_score, root_mean_squared_error)

# Las medidas que admiten intervalo, con la función que las calcula
MEDIDAS_INTERVALO = {
    "mae": mean_absolute_error,
    "rmse": root_mean_squared_error,
    "r2": r2_score,
}


def _comprobar(real, previsto):
    """Devuelve real y previsto como arrays de números, o para con un ValueError que dice qué falla."""
    # Las dos entradas como arrays de números
    real = np.asarray(real, dtype=float)
    previsto = np.asarray(previsto, dtype=float)
    # Una columna cada una, con el mismo número de filas
    if real.ndim != 1 or previsto.ndim != 1:
        # Se para
        raise ValueError(f"real y previsto tienen que ser una columna cada uno, y llegan con forma {real.shape} "
                         f"y {previsto.shape}")
    if real.shape != previsto.shape:
        # Se para
        raise ValueError(f"real y previsto con longitudes distintas: {len(real)} y {len(previsto)}")
    # Al menos dos filas
    if len(real) < 2:
        # Se para
        raise ValueError("hacen falta al menos dos filas para medir el error")
    # Sin vacíos ni infinitos
    if not (np.isfinite(real).all() and np.isfinite(previsto).all()):
        # Se para
        raise ValueError("hay vacíos o infinitos en el real o en el previsto: se quitan antes, y se dice cuántos")
    # Un objetivo constante no tiene varianza que explicar
    if np.all(real == real[0]):
        # Se para
        raise ValueError("el valor real es el mismo en todas las filas: el R² no existe con estas filas")
    # Todo en orden
    return real, previsto


def _mape(real, previsto):
    """El MAPE y su motivo: vacío si algún real es cero o si el objetivo cruza el cero, porque entonces explota."""
    # Un real igual a cero divide por cero
    if np.any(real == 0):
        return float("nan"), "algún valor real es cero: el MAPE divide por él"
    # Con reales de los dos signos, los cercanos a cero inflan el porcentaje
    if real.min() < 0 < real.max():
        return float("nan"), "el objetivo cruza el cero: los valores cercanos a cero inflan el MAPE; se usa el WAPE"
    # Con el objetivo de un solo signo, el MAPE de scikit-learn
    return float(mean_absolute_percentage_error(real, previsto)), None


def medidas(real, previsto):
    """Las medidas del error de un modelo, sobre filas que no ha visto.

    - mae: el error medio, en las unidades del objetivo; es la que se lee primero;
    - rmse y mse: el error que pesa más los fallos grandes; el RMSE está en las unidades del objetivo y el MSE, al
      cuadrado. Si el RMSE es mucho mayor que el MAE, hay pocos fallos muy grandes;
    - mediana_error_absoluto: el error de la fila típica, que no mueven los fallos extremos;
    - r2: cuánto mejora el modelo sobre predecir la media de estas filas; en datos nuevos puede ser negativo;
    - sesgo: el error medio con signo, previsto menos real; positivo es que el modelo se pasa;
    - wape: el error absoluto total entre el valor real total, en tanto por uno; sirve aunque haya ceros;
    - mape y mape_motivo: el error porcentual medio, solo si ningún real es cero ni el objetivo cruza el cero;
    - filas, media_real y desviacion_real: con qué se compara todo lo anterior.
    """
    # Entradas comprobadas
    real, previsto = _comprobar(real, previsto)
    # Error de cada fila, previsto menos real
    error = previsto - real
    # El MAPE solo cuando tiene sentido
    mape, motivo = _mape(real, previsto)
    # Diccionario de medidas
    return {
        "filas": int(len(real)),
        "media_real": float(real.mean()),
        "desviacion_real": float(real.std(ddof=1)),
        "mae": float(mean_absolute_error(real, previsto)),
        "rmse": float(root_mean_squared_error(real, previsto)),
        "mse": float(mean_squared_error(real, previsto)),
        "mediana_error_absoluto": float(median_absolute_error(real, previsto)),
        "r2": float(r2_score(real, previsto)),
        "sesgo": float(error.mean()),
        "wape": float(np.abs(error).sum() / np.abs(real).sum()),
        "mape": mape,
        "mape_motivo": motivo,
    }


def referencia_media(real_desarrollo, n):
    """La predicción más sencilla: la media del objetivo en desarrollo, repetida para las n filas de validación."""
    # La media se calcula solo con desarrollo, como cualquier otro modelo
    media = float(np.mean(np.asarray(real_desarrollo, dtype=float)))
    return np.full(n, media)


def comparar_modelos(real, previstos):
    """medidas de cada modelo sobre las mismas filas. `previstos` es {nombre: previsto}.

    El ÚLTIMO de la lista es la referencia: la columna mejora_mae dice cuánto baja cada modelo su MAE, en tanto por uno
    (0,30 es un 30 % menos de error). Un modelo no es bueno por sí mismo, sino si supera a algo más simple.
    """
    # Una fila por modelo, en el orden recibido
    tabla = pd.DataFrame({nombre: medidas(real, p) for nombre, p in previstos.items()}).T
    # La referencia es la última
    mae_ref = float(tabla["mae"].iloc[-1])
    # Mejora del MAE sobre la referencia
    tabla["mejora_mae"] = 1 - tabla["mae"].astype(float) / mae_ref
    return tabla


def error_por_tramo(real, previsto, n_tramos=5):
    """El error por tramos del valor real, con el mismo número de filas en cada uno.

    Dice dónde falla el modelo: es frecuente que acierte en el centro y se quede corto en los extremos (sesgo
    negativo en los valores altos). Con pocos casos, cada tramo necesita bastantes filas: el caso fija el mínimo.
    """
    # Entradas comprobadas
    real, previsto = _comprobar(real, previsto)
    # Tramos por cuantiles del valor real, sin tramos repetidos
    tramo = pd.qcut(real, n_tramos, duplicates="drop")
    d = pd.DataFrame({"real": real, "previsto": previsto, "error": previsto - real, "tramo": tramo})
    d["error_absoluto"] = d["error"].abs()
    # Recuento y medidas por tramo
    return d.groupby("tramo", observed=True).agg(filas=("real", "size"), real_medio=("real", "mean"),
                                                 previsto_medio=("previsto", "mean"), mae=("error_absoluto", "mean"),
                                                 sesgo=("error", "mean"))


def desarrollo_frente_a_validacion(real_des, previsto_des, real_val, previsto_val):
    """MAE, RMSE y R² en desarrollo y en validación, y validación entre desarrollo, para ver el sobreajuste.

    En desarrollo se mide con el modelo ya ajustado a esas filas; en validación, con filas que no ha visto. Si el error
    de validación es mucho mayor que el de desarrollo, el modelo memoriza en lugar de aprender (sobreajuste): se
    corrige con un modelo más sencillo o más regularizado. Si los dos son altos y parecidos, se queda corto (infra
    ajuste). Cuánto es «mucho» no tiene vara fija: se compara entre modelos del mismo caso.
    """
    # Medidas de cada lado
    des = medidas(real_des, previsto_des)
    val = medidas(real_val, previsto_val)
    claves = ["mae", "rmse", "r2"]
    tabla = pd.DataFrame({"desarrollo": {k: des[k] for k in claves}, "validacion": {k: val[k] for k in claves}}).T
    # Cuántas veces es el de validación el de desarrollo
    tabla.loc["validacion_entre_desarrollo"] = tabla.loc["validacion"] / tabla.loc["desarrollo"]
    return tabla


def _medida(nombre):
    """La función de una medida que admite intervalo, o para si no la hay."""
    if nombre not in MEDIDAS_INTERVALO:
        # Se para
        raise ValueError(f"medida sin intervalo: {nombre}; las que hay son {sorted(MEDIDAS_INTERVALO)}")
    return MEDIDAS_INTERVALO[nombre]


def intervalo(real, previsto, medida="mae", n=1000, semilla=42):
    """El intervalo del 95 % de una medida, por percentiles de n remuestreos de las filas con semilla fija."""
    # Entradas comprobadas y medida elegida
    real, previsto = _comprobar(real, previsto)
    f = _medida(medida)
    # Remuestreos con reposición, siempre los mismos con la misma semilla
    rng = np.random.default_rng(semilla)
    valores = []
    for _ in range(n):
        i = rng.integers(0, len(real), len(real))
        valores.append(f(real[i], previsto[i]))
    # Percentiles 2,5 y 97,5
    return float(np.percentile(valores, 2.5)), float(np.percentile(valores, 97.5))


def intervalo_diferencia(real, previsto_a, previsto_b, medida="mae", n=1000, semilla=42):
    """El intervalo del 95 % de la medida de A menos la de B, con los mismos remuestreos para los dos (emparejados).

    Si no incluye el cero, la diferencia no se explica por el azar de las filas. Con el MAE, un intervalo por debajo
    de cero dice que A se equivoca menos que B.
    """
    # Entradas comprobadas y medida elegida
    real, previsto_a = _comprobar(real, previsto_a)
    _, previsto_b = _comprobar(real, previsto_b)
    f = _medida(medida)
    # Las mismas filas para los dos modelos en cada remuestreo
    rng = np.random.default_rng(semilla)
    valores = []
    for _ in range(n):
        i = rng.integers(0, len(real), len(real))
        valores.append(f(real[i], previsto_a[i]) - f(real[i], previsto_b[i]))
    # Percentiles 2,5 y 97,5
    return float(np.percentile(valores, 2.5)), float(np.percentile(valores, 97.5))


def figura_real_frente_a_prevision(real, previstos):
    """Real frente a previsto de uno o varios modelos, con la diagonal del acierto perfecto. Para lectores técnicos."""
    # Figura y ejes
    fig, ax = plt.subplots(figsize=(6, 5))
    # Una nube por modelo
    for nombre, p in previstos.items():
        r_, p_ = _comprobar(real, p)
        ax.scatter(r_, p_, s=8, alpha=0.6, label=nombre)
    # Diagonal entre el mínimo y el máximo del real
    r_ = np.asarray(real, dtype=float)
    ax.plot([r_.min(), r_.max()], [r_.min(), r_.max()], linestyle="--", color="grey", label="acierto perfecto")
    # Rótulos en castellano
    ax.set_xlabel("Valor real")
    ax.set_ylabel("Valor previsto")
    ax.legend()
    return fig


def figura_residuos(real, previsto):
    """El error de cada fila frente a lo previsto, con la línea del cero. Una nube sin forma es buena señal."""
    # Entradas comprobadas
    real, previsto = _comprobar(real, previsto)
    # Figura y ejes
    fig, ax = plt.subplots(figsize=(6, 5))
    # Error con signo, previsto menos real
    ax.scatter(previsto, previsto - real, s=8, alpha=0.6)
    ax.axhline(0, linestyle="--", color="grey")
    # Rótulos en castellano
    ax.set_xlabel("Valor previsto")
    ax.set_ylabel("Error (previsto menos real)")
    return fig
