"""Saca el dataset del caso 69 a partir de los CSV de M5 Forecasting - Accuracy (Kaggle).

Recorte del caso: 500 productos elegidos al azar con semilla, en las 10 tiendas, con todos los
dias de `sales_train_evaluation.csv` (d_1 a d_1941). Se guardan tres ficheros con el formato del original:

- sales_train_evaluation.csv: solo las filas de los 500 productos (5.000 series);
- sell_prices.csv: solo los precios de esos productos;
- calendar.csv: entero (es pequeño y lo necesita cualquier serie).

`sales_train_validation.csv` no se guarda: es el mismo historico con 28 dias menos. `sample_submission.csv` tampoco: es
el formato de envio a la competicion.

Uso:  python recortar_m5.py <carpeta_con_los_csv_de_m5> <carpeta_de_salida>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SEMILLA = 69
N_PRODUCTOS = 500
TIENDAS_ESPERADAS = 10


def main(origen: Path, destino: Path) -> None:
    ventas = pd.read_csv(origen / "sales_train_evaluation.csv")
    tiendas_por_producto = ventas.groupby("item_id")["store_id"].nunique()
    if ventas["store_id"].nunique() != TIENDAS_ESPERADAS or (tiendas_por_producto != TIENDAS_ESPERADAS).any():
        raise SystemExit("ALTO: no todos los productos estan en las 10 tiendas; el recorte no daria 10 series por producto")

    productos = np.sort(ventas["item_id"].unique())
    elegidos = np.random.default_rng(SEMILLA).choice(productos, size=N_PRODUCTOS, replace=False)
    recorte = ventas[ventas["item_id"].isin(elegidos)]

    precios = pd.read_csv(origen / "sell_prices.csv")
    precios = precios[precios["item_id"].isin(elegidos)]

    destino.mkdir(parents=True, exist_ok=True)
    recorte.to_csv(destino / "sales_train_evaluation.csv", index=False)
    precios.to_csv(destino / "sell_prices.csv", index=False)
    (destino / "calendar.csv").write_bytes((origen / "calendar.csv").read_bytes())

    print(f"original: {len(ventas)} series, {len(productos)} productos")
    print(f"recorte: {len(recorte)} series, {recorte['item_id'].nunique()} productos, "
          f"{recorte['store_id'].nunique()} tiendas, {sum(c.startswith('d_') for c in recorte.columns)} dias")
    print(f"precios: {len(precios)} filas")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
