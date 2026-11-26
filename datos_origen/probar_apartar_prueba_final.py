"""Prueba de apartar_prueba_final.py con datos pequeños escritos aquí, nunca los del caso. Sale con 0 si pasa."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apartar_prueba_final as a  # noqa: E402

fallos = []
hechas = [0]


def comprobar(nombre, obtenido, esperado):
    """Apunta un fallo si lo obtenido no es lo esperado y cuenta la comprobación."""
    hechas[0] += 1
    if obtenido != esperado:
        fallos.append(f"{nombre}: esperaba {esperado!r}, salió {obtenido!r}")


# Calendario de cuatro días en dos semanas; el corte, el segundo día.
calendario = [
    "date,wm_yr_wk,weekday,wday,month,year,d,event_name_1\n",
    "2015-05-21,11516,Thursday,6,5,2015,d_1,\n",
    "2015-05-22,11516,Friday,7,5,2015,d_2,\n",
    "2015-05-23,11517,Saturday,1,5,2015,d_3,\n",
    "2015-05-24,11517,Sunday,2,5,2015,d_4,\n",
]
comprobar("corte", a.dia_y_semana_de_corte(calendario, "2015-05-22"), (2, "11516"))

# Una fecha que no está en el calendario tiene que parar el trabajo.
hechas[0] += 1
try:
    a.dia_y_semana_de_corte(calendario, "2099-01-01")
    fallos.append("fecha ausente: no paró")
except ValueError:
    pass

ventas = ["id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2,d_3,d_4\n",
          "X_CA_1,X,F_1,F,CA_1,CA,1,0,5,7\n"]
guardadas, apartadas = a.partir_ventas(ventas, 2)
comprobar("ventas guardadas", guardadas, ["id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2\n",
                                          "X_CA_1,X,F_1,F,CA_1,CA,1,0\n"])
comprobar("ventas apartadas", apartadas, ["id,item_id,dept_id,cat_id,store_id,state_id,d_3,d_4\n",
                                          "X_CA_1,X,F_1,F,CA_1,CA,5,7\n"])

# Una cabecera sin columnas d_ seguidas desde d_1 tiene que parar.
hechas[0] += 1
try:
    a.partir_ventas(["id,item_id,dept_id,cat_id,store_id,state_id,d_2,d_1\n"], 1)
    fallos.append("cabecera desordenada: no paró")
except ValueError:
    pass

precios = ["store_id,item_id,wm_yr_wk,sell_price\n",
           "CA_1,X,11516,2.97\n", "CA_1,X,11517,3.10\n", "CA_1,Y,11515,1.00\n"]
guardadas, apartadas = a.partir_precios(precios, "11516")
comprobar("precios guardados", guardadas, ["store_id,item_id,wm_yr_wk,sell_price\n",
                                           "CA_1,X,11516,2.97\n", "CA_1,Y,11515,1.00\n"])
comprobar("precios apartados", apartadas, ["store_id,item_id,wm_yr_wk,sell_price\n", "CA_1,X,11517,3.10\n"])

# Los ficheros reales acaban las líneas en \r\n: se parten igual y conservan su final de línea.
ventas_crlf = ["id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2,d_3\r\n", "X_CA_1,X,F_1,F,CA_1,CA,1,0,5\r\n"]
guardadas, apartadas = a.partir_ventas(ventas_crlf, 2)
comprobar("ventas \\r\\n guardadas", guardadas, ["id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2\r\n",
                                               "X_CA_1,X,F_1,F,CA_1,CA,1,0\r\n"])
comprobar("ventas \\r\\n apartadas", apartadas, ["id,item_id,dept_id,cat_id,store_id,state_id,d_3\r\n",
                                               "X_CA_1,X,F_1,F,CA_1,CA,5\r\n"])
calendario_crlf = ["date,wm_yr_wk,d\r\n", "2015-05-22,11516,d_7\r\n"]
comprobar("corte \\r\\n", a.dia_y_semana_de_corte(calendario_crlf, "2015-05-22"), (7, "11516"))
precios_crlf = ["store_id,item_id,wm_yr_wk\r\n", "CA_1,X,11516\r\n", "CA_1,X,11517\r\n"]
comprobar("precios \\r\\n", a.partir_precios(precios_crlf, "11516"),
          (["store_id,item_id,wm_yr_wk\r\n", "CA_1,X,11516\r\n"], ["store_id,item_id,wm_yr_wk\r\n", "CA_1,X,11517\r\n"]))

if fallos:
    print("FALLA:")
    for f in fallos:
        print(" -", f)
    sys.exit(1)
print(f"PASA: {hechas[0]} comprobaciones")
sys.exit(0)
