"""Aparta la prueba final del caso 69 antes del reconocimiento (paso 2).

Lee los tres ficheros enteros que deja `recortar_m5.py` y escribe:
- en `data/raw/` del caso, la venta y los precios hasta la fecha de corte; el calendario no se toca;
- en `data/raw/reserva/`, la venta y los precios posteriores, que no se abren hasta la prueba final.

Trabaja con el texto de cada línea, sin convertir números, para que lo que queda sea byte a byte lo que había.
No imprime ninguna cifra de venta de la prueba final: solo recuentos de días y de filas.
Uso: python apartar_prueba_final.py <carpeta_del_recorte> data/raw data/raw/reserva
"""
import sys
from pathlib import Path

# ---------------------------------------------------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------------------------------------------------

# Último día que se mira antes de la prueba final (reglas de negocio del caso, apartado 5, «Fechas»).
FECHA_CORTE = "2015-05-22"

# Las seis columnas que identifican cada fila de ventas, antes de los días.
COLUMNAS_ID = 6


# ---------------------------------------------------------------------------------------------------------------------
# Partir una línea sin perder su final
# ---------------------------------------------------------------------------------------------------------------------

def campos(linea):
    """Devuelve los campos de una línea CSV sin su final de línea, sea \\n o \\r\\n."""
    return linea.rstrip("\r\n").split(",")


def fin(linea):
    """Devuelve el final de línea tal como viene, para escribirlo igual."""
    return linea[len(linea.rstrip("\r\n")):]


# ---------------------------------------------------------------------------------------------------------------------
# Cálculo del corte
# ---------------------------------------------------------------------------------------------------------------------

def dia_y_semana_de_corte(lineas_calendario, fecha):
    """Devuelve el número de día (d_N) y la semana de Walmart de la fecha de corte; para si la fecha no está."""
    cabecera = campos(lineas_calendario[0])
    i_fecha, i_semana, i_dia = cabecera.index("date"), cabecera.index("wm_yr_wk"), cabecera.index("d")
    for linea in lineas_calendario[1:]:
        c = campos(linea)
        if c[i_fecha] == fecha:
            return int(c[i_dia].removeprefix("d_")), c[i_semana]
    raise ValueError(f"La fecha de corte {fecha} no está en el calendario")


def partir_ventas(lineas, n_dia):
    """Separa cada fila de ventas en sus columnas hasta d_n_dia y las posteriores, con las columnas de identidad.

    Para si las columnas de días no van seguidas desde d_1, porque entonces cortar por posición cortaría mal.
    """
    dias = campos(lineas[0])[COLUMNAS_ID:]
    if dias != [f"d_{i}" for i in range(1, len(dias) + 1)]:
        raise ValueError("Las columnas de días no van seguidas desde d_1")
    corte = COLUMNAS_ID + n_dia
    guardadas, apartadas = [], []
    for linea in lineas:
        c = campos(linea)
        guardadas.append(",".join(c[:corte]) + fin(linea))
        apartadas.append(",".join(c[:COLUMNAS_ID] + c[corte:]) + fin(linea))
    return guardadas, apartadas


def partir_precios(lineas, semana):
    """Separa las filas de precios de las semanas hasta la de corte de las posteriores; la cabecera va en las dos."""
    i_semana = campos(lineas[0]).index("wm_yr_wk")
    guardadas, apartadas = [lineas[0]], [lineas[0]]
    for linea in lineas[1:]:
        semana_fila = campos(linea)[i_semana]
        (guardadas if int(semana_fila) <= int(semana) else apartadas).append(linea)
    return guardadas, apartadas


# ---------------------------------------------------------------------------------------------------------------------
# Lectura, controles y escritura
# ---------------------------------------------------------------------------------------------------------------------

def leer(ruta):
    """Lee un CSV como lista de líneas, sin cambiar los finales de línea."""
    with open(ruta, encoding="utf-8", newline="") as f:
        return f.readlines()


def escribir(ruta, lineas):
    """Escribe las líneas tal cual, en UTF-8."""
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.writelines(lineas)


def controlar(ventas, v_guard, v_apart, precios, p_guard, p_apart, n_dia, semana):
    """Comprueba antes de escribir que las dos partes rehacen el original; para si no."""
    for orig, g, ap in zip(ventas, v_guard, v_apart):
        if campos(g) + campos(ap)[COLUMNAS_ID:] != campos(orig) or fin(g) != fin(orig):
            raise ValueError("Una fila de ventas no se rehace con sus dos partes")
    if len(campos(v_guard[0])) != COLUMNAS_ID + n_dia:
        raise ValueError("Las ventas guardadas no acaban en el día de corte")
    if len(p_guard) + len(p_apart) - 2 != len(precios) - 1:
        raise ValueError("Las filas de precios no suman las del original")
    i_sem = campos(precios[0]).index("wm_yr_wk")
    if any(int(campos(l)[i_sem]) > int(semana) for l in p_guard[1:]):
        raise ValueError("Hay precios guardados después de la semana de corte")
    if any(int(campos(l)[i_sem]) <= int(semana) for l in p_apart[1:]):
        raise ValueError("Hay precios apartados de la semana de corte o anteriores")


if __name__ == "__main__":
    completo, raw, reserva = (Path(p) for p in sys.argv[1:4])
    reserva.mkdir(parents=True, exist_ok=True)

    n_dia, semana = dia_y_semana_de_corte(leer(completo / "calendar.csv"), FECHA_CORTE)
    ventas = leer(completo / "sales_train_evaluation.csv")
    precios = leer(completo / "sell_prices.csv")
    v_guard, v_apart = partir_ventas(ventas, n_dia)
    p_guard, p_apart = partir_precios(precios, semana)
    controlar(ventas, v_guard, v_apart, precios, p_guard, p_apart, n_dia, semana)

    escribir(raw / "sales_train_evaluation.csv", v_guard)
    escribir(raw / "sell_prices.csv", p_guard)
    escribir(reserva / "sales_train_evaluation.csv", v_apart)
    escribir(reserva / "sell_prices.csv", p_apart)

    total_dias = len(campos(ventas[0])) - COLUMNAS_ID
    print(f"Corte: {FECHA_CORTE} = d_{n_dia}, semana {semana}")
    print(f"Ventas: {len(ventas) - 1} filas; días guardados {n_dia}, apartados {total_dias - n_dia}")
    print(f"Precios: filas guardadas {len(p_guard) - 1}, apartadas {len(p_apart) - 1}, original {len(precios) - 1}")
