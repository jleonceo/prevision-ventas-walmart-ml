# Informe de corrección de datos · caso 69

Informe generado por `scripts/03_correccion_datos.py` a partir de `informes/correccion-datos.json`. Estado **OK**, riesgo bajo. Fecha de los datos: 2015-05-22.

La fecha del calendario pasa de texto a fecha y 3 nombres de columna pasan a minúsculas. Ninguna fila ni valor cambia (0 diferencias); 6 cuestiones de la calidad quedan decididas por la petición 07 y los 2.687 días de serie a cero de los dos periodos quedan clasificados.

## Fuente

- Entrada `data/raw/sales_train_evaluation.csv`: 5.000 filas y 1.581 columnas; huella `fcbeed85b09a49d3b1b0625a721053388f26e19490bf42e480e97ad6e177b7b2`.
- Entrada `data/raw/sell_prices.csv`: 854.573 filas y 4 columnas; huella `3a3124852028006f94b6eb2c6b0a313df689ca2c75a6b8aaac0e67447f593a7f`.
- Entrada `data/raw/calendar.csv`: 1.969 filas y 14 columnas; huella `d12b5914ef03e66649adf5dd9e996e6602251c22b7a6af8f1f7e3aa12f8860f5`.
- Diagnóstico de partida: `informes/calidad-datos.json`, en estado AVISO, con 29 problemas y 6 cuestiones.
- Salida `data/processed/venta_corregido.parquet`: 5.000 filas y 1.581 columnas; huella `8d54b88b01a9f00c53461cc40dde91d48cb2c97bffaf2c9c569c1449e18304cd`.
- Salida `data/processed/precios_corregido.parquet`: 854.573 filas y 4 columnas; huella `d9ac5467e59d7f099a0e3ae0358417ef17be8e3c76d6fb59726fa6c70f99c1fa`.
- Salida `data/processed/calendario_corregido.parquet`: 1.969 filas y 14 columnas; huella `1754b2bb702dc7193b81f638906027dccbbbd16a647a2d65cfd3dcb296581d27`.
- Ejecución del 2026-11-24T08:37:57 con Python 3.13.15, pandas 3.0.6 y pyarrow 24.0.0. Duró 2,62 segundos.
- Teoría del manual aplicada: 8.1, cada corrección responde a un problema diagnosticado; la limpieza solo hace reglas que no aprenden nada de los datos, porque los datos van a un modelo; 8.2, nombres en minúsculas, sin tildes y con guion bajo; el mapeo se guarda; 8.3, la fecha se convierte con su formato explícito y se cuentan los valores que no se leen antes de darla por buena; 8.10, el cierre: recuentos y sumas de antes y después, el registro junto al dato y lo pendiente con su motivo.

## Correcciones aplicadas

- **C-04, la fecha del calendario.** `calendario.date` pasa de texto a fecha con el formato %Y-%m-%d. Es una corrección técnicamente inequívoca: 0 fechas no se leen con ese formato. Antes era texto y ahora es fecha (datetime64[us]) en las 1.969 filas, con 0 vacías. Ficha R-001.
- **C-03, los nombres de columna.** En `calendario`: `snap_CA` pasa a `snap_ca`; `snap_TX` pasa a `snap_tx`; `snap_WI` pasa a `snap_wi`. Es una corrección técnicamente inequívoca (criterios.md §5) con 0 colisiones. Ninguna otra columna cambia de nombre. Ficha R-002.
- Tipos comprobados sin cambio: 24 columnas o bloques ya traían el tipo de su rol (texto, entero o decimal). Un tipo que ya está bien no es una corrección.

## Decisiones del responsable

Las cuestiones de la calidad quedan decididas por el responsable del caso en la petición 07, con fecha 2026-11-23. El script las lee del fichero de decisiones `config/modelo/decisiones-correccion.json`. Ninguna cambia un dato.

- **PC-01** (C-12): «son precios reales de productos baratos y se usan como están». Motivo: los 9.438 precios bajo 0,5 dólares pesan el 0,41 % de los dólares de la construcción y el 0,31 % de la validación; en una serie, como mucho el 3,3 %. Quitarlos dejaría semanas con venta y sin precio, que paran el trabajo (reglas, apartado 5).
- **PC-02** (C-13): «son cambios reales de precio y se usan como están». Motivo: las 350 subidas de más del doble pesan el 0,03 % de los dólares de cada periodo.
- **PC-03** (C-14): «es un cierre real de la tienda y se trata como el 25 de diciembre». En la corrección no cambia ningún dato; ningún error se mide ese día. Motivo: WI_1 el 2011-02-02 es un cierre por la definición de las reglas, apartado 5, en el quinto día de los datos.
- **PC-04** (C-15): «se dejan como vendidas». Motivo: 22 de 9.327.191 unidades; el 25 de diciembre queda fuera del error (reglas, apartado 6).
- **PC-05** (C-16): «son cambios reales de la venta y la serie se usa entera». Cómo pesa en el modelo la historia anterior al salto lo fijan los planteamientos, no los datos. Motivo: los saltos son cambios reales de la venta; cómo entra la historia anterior al salto lo fijan los planteamientos.
- **PC-06** (C-17): «son cambios reales de la venta y la serie se usa entera». Cómo pesa en el modelo la historia anterior al salto lo fijan los planteamientos, no los datos. Motivo: los saltos son cambios reales de la venta; cómo entra la historia anterior al salto lo fijan los planteamientos.

## Elementos mantenidos sin cambios

27 problemas de la calidad se dejan como están, cada uno con su motivo. Todos van en la ficha R-003 del registro.

- **C-01**: pasar la venta a una fila por día es reestructurar; lo hace la transformación.
- **C-02**: la clave es item_id con store_id; id no se usa como variable.
- **C-05**: D2, cerrada el 21/11/2026; el vacío es «sin evento» (reglas, apartado 5). Los cinco días con segundo evento traen dos fiestas distintas; ninguno repite ni contradice al primero.
- **C-06**: D2, cerrada el 21/11/2026; el vacío es «sin evento» (reglas, apartado 5). Los cinco días con segundo evento traen dos fiestas distintas; ninguno repite ni contradice al primero.
- **C-07**: D2, cerrada el 21/11/2026; el vacío es «sin evento» (reglas, apartado 5). Los cinco días con segundo evento traen dos fiestas distintas; ninguno repite ni contradice al primero.
- **C-08**: D2, cerrada el 21/11/2026; el vacío es «sin evento» (reglas, apartado 5). Los cinco días con segundo evento traen dos fiestas distintas; ninguno repite ni contradice al primero.
- **C-09**: una semana sin precio es una semana sin venta (reglas, apartado 5).
- **C-10**: un día con cero unidades es un dato válido (reglas, apartado 5).
- **C-11**: un día con cero unidades es un dato válido (reglas, apartado 5).
- **C-12** (PC-01): los 9.438 precios bajo 0,5 dólares pesan el 0,41 % de los dólares de la construcción y el 0,31 % de la validación; en una serie, como mucho el 3,3 %. Quitarlos dejaría semanas con venta y sin precio, que paran el trabajo (reglas, apartado 5).
- **C-13** (PC-02): las 350 subidas de más del doble pesan el 0,03 % de los dólares de cada periodo.
- **C-14** (PC-03): WI_1 el 2011-02-02 es un cierre por la definición de las reglas, apartado 5, en el quinto día de los datos.
- **C-15** (PC-04): 22 de 9.327.191 unidades; el 25 de diciembre queda fuera del error (reglas, apartado 6).
- **C-16** (PC-05 y PC-06): los saltos son cambios reales de la venta; cómo entra la historia anterior al salto lo fijan los planteamientos.
- **C-17** (PC-05 y PC-06): los saltos son cambios reales de la venta; cómo entra la historia anterior al salto lo fijan los planteamientos.
- **C-18**: los ceros son datos válidos; su clase está en clases_de_ceros.
  - Clases de los días a cero de las 70 series de departamento y tienda. Cada cero va a la primera clase que cumple, en este orden: cierre de la tienda, 25 de diciembre, demanda intermitente y resto.
  - Construcción: 2.416 días de serie a cero en 70 series.
    - Cierre de la tienda: 175 días de serie en 63 series, 25 días de tienda cerrada.
    - 25 de diciembre: 35 días de serie en 18 series.
    - Demanda intermitente: 2.171 días de serie en 10 series.
    - Resto: 35 días de serie en 3 series.
    - Series con media de menos de 10 unidades al día, 10 en total: CA_1 HOBBIES_2 (2,58); CA_2 HOBBIES_2 (3,68); CA_3 HOBBIES_2 (3,65); CA_4 HOBBIES_2 (1,23); TX_1 HOBBIES_2 (2,22); TX_2 HOBBIES_2 (4,73); TX_3 HOBBIES_2 (3,61); WI_1 HOBBIES_2 (2,43); WI_2 HOBBIES_2 (2,4); WI_3 HOBBIES_2 (2,19).
    - La serie que menos vende de las demás es WI_2 HOUSEHOLD_2, con 14,01 de media.
    - Resto en WI_1 FOODS_2: 14 días entre el 2011-11-24 y el 2012-10-25.
    - Resto en WI_1 HOUSEHOLD_2: 18 días entre el 2012-09-29 y el 2012-10-25.
    - Resto en WI_2 FOODS_2: 3 días entre el 2012-04-30 y el 2012-05-02.
  - Validación: 271 días de serie a cero en 70 series.
    - Cierre de la tienda: 56 días de serie en 56 series, 8 días de tienda cerrada.
    - 25 de diciembre: 12 días de serie en 12 series.
    - Demanda intermitente: 201 días de serie en 9 series.
    - Resto: 2 días de serie en 1 series.
    - Series con media de menos de 10 unidades al día, 10 en total: CA_1 HOBBIES_2 (7,54); CA_2 HOBBIES_2 (5,28); CA_3 HOBBIES_2 (8,68); CA_4 HOBBIES_2 (2,34); TX_1 HOBBIES_2 (3,97); TX_2 HOBBIES_2 (7,91); TX_3 HOBBIES_2 (7,6); WI_1 HOBBIES_2 (5,33); WI_2 HOBBIES_2 (3,94); WI_3 HOBBIES_2 (3,68).
    - La serie que menos vende de las demás es CA_2 FOODS_2, con 15,64 de media.
    - Resto en CA_2 FOODS_2: 2 días entre el 2014-10-08 y el 2014-10-09.
- **C-19**: suman cero a su departamento (reglas, apartado 3) y no están mal.
- **C-20**: suman cero a su departamento (reglas, apartado 3) y no están mal.
- **C-21**: describen; no son errores.
- **C-22**: describen; no son errores.
- **C-23**: describen; no son errores.
- **C-24**: describen; no son errores.
- **C-25**: un atípico no es un error; son ventas y precios reales.
- **C-26**: un atípico no es un error; son ventas y precios reales.
- **C-27**: un atípico no es un error; son ventas y precios reales.
- **C-28**: un atípico no es un error; son ventas y precios reales.
- **C-29**: suman cero a su departamento (reglas, apartado 3) y no están mal.

## Decisiones pendientes

No queda ninguna. Las seis cuestiones de la calidad están en «Decisiones del responsable».

## Validación

- Venta: 5.000 filas antes y 5.000 después; 1.581 columnas antes y 1.581 después.
- Precios: 854.573 filas antes y 854.573 después; 4 columnas antes y 4 después.
- Calendario: 1.969 filas antes y 1.969 después; 14 columnas antes y 14 después.
- Unidades (total): 9.327.191 antes y 9.327.191 después; coincide: sí.
- Unidades (construcción): 7.003.244 antes y 7.003.244 después; coincide: sí.
- Unidades (validación): 2.323.947 antes y 2.323.947 después; coincide: sí.
- Suma de sell_price: 3.750.011,81 antes y 3.750.011,81 después; coincide: sí.
- Días SNAP de CA: 650 antes y 650 después; coincide: sí.
- Días SNAP de TX: 650 antes y 650 después; coincide: sí.
- Días SNAP de WI: 650 antes y 650 después; coincide: sí.
- Las dos vías: antes, pandas sobre `data/raw/`; después, pyarrow sobre los Parquet de `data/processed/`.
- Valores distintos al deshacer la corrección: 0.
- Comprobación de completitud: pasa. Filas y columnas de las tres tablas, iguales antes y después.
- Comprobación de consistencia: pasa. Cada columna con el tipo de su rol y ningún valor distinto al deshacer la corrección.
- Comprobación de utilidad: pasa. El análisis del caso, la previsión de las 70 series de departamento y tienda, sigue siendo posible: las 70 series se forman y cada día de la venta tiene su fecha en el calendario.
- Comprobación de datos personales: pasa. Ninguna columna de texto con forma de dato personal.
- Validaciones que paran el trabajo: 0 fallos.
- Huella de `data/raw/` igual antes y después: sí.
- Estado final: OK. Tablas generadas: `data/processed/venta_corregido.parquet`; `data/processed/precios_corregido.parquet`; `data/processed/calendario_corregido.parquet`.

## Datos personales

No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada de personas. Esta ejecución buscó correos, documentos de identidad, teléfonos y cuentas bancarias en las columnas de texto de las tres tablas y los encontró en 0 columnas. Este método no usa ni deja ninguna columna de datos personales.

## Límites

- La corrección mira una tabla cada vez. Una clave huérfana o repetida al otro lado de un cruce no se ve ni se corrige aquí.
- El diagnóstico completo de la calidad no se vuelve a pasar sobre las tablas corregidas (manual 8.10, paso 1). Se comparan filas, columnas, valores, tipos y sumas de antes y después.
- Los pesos que dan los motivos de C-12 a C-15 (porcentajes de dólares y unidades) vienen de la petición 07, copiados en el fichero de decisiones; este script no los recalcula.
- La regla de no tener dos decisiones sobre el mismo campo se aplica por cuestión: PC-03 y PC-04 son de la misma columna de la venta, igual que PC-05 y PC-06, porque cada una contesta una pregunta distinta.
- El script lista los días del resto de los ceros con su serie y su fecha. Qué son lo decide la cascada de D8.
- Los días del calendario posteriores a la fecha de referencia se corrigen igual que los demás. No son de ningún periodo y no entran en la clasificación de los ceros.
