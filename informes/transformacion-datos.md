# Informe de transformación de datos

## Fuente

- Entrada: `data/processed/venta_corregido.parquet`, 5.000 filas y 1.581 columnas; huella `8d54b88b01a9f00c53461cc40dde91d48cb2c97bffaf2c9c569c1449e18304cd`.
- Entrada: `data/processed/precios_corregido.parquet`, 854.573 filas y 4 columnas; huella `d9ac5467e59d7f099a0e3ae0358417ef17be8e3c76d6fb59726fa6c70f99c1fa`.
- Entrada: `data/processed/calendario.parquet`, 1.969 filas y 18 columnas; huella `a8478ae161ca3e4c99e5f8fa7530ba2a4f73f7e954bf785decefa975c32fbeda`.
- Salida: `data/processed/hechos_series.parquet`.
- Salida: `data/processed/dim_producto.parquet`.
- Salida: `data/processed/dim_tienda.parquet`.
- Contexto: `config/negocio/reglas-transformacion.md`, el plan de cruces de `informes/modelado-datos.json` y el estado de `informes/correccion-datos.json`.
- Ejecución: 2026-11-24T11:04:45, con Python 3.13.15 y pandas 3.0.6. Fecha de los datos: 2015-05-22.

## Objetivo

Estado **OK**, riesgo bajo. Tabla de series con 110.250 filas de 70 series, 9.327.191 unidades y 24.982.728,54 dólares, los de la venta en filas; dim_producto con 500 productos y dim_tienda con 10 tiendas. Los 7 cruces del plan sin filas de más y 24 validaciones en verde.

La venta se prepara en una fila por departamento en una tienda y día, en unidades y en dólares, con el calendario, el SNAP de su estado, las marcas de cierre y de los ceros y el precio medio del departamento de la semana anterior. Es la base de la exploración y de las variables del paso 5.

## Transformaciones aplicadas

- T-01 · tabla de series con la venta en dólares, cruces 1 a 5: 110.250 filas con 9.327.191 unidades y 24.982.728,54 dólares, los de la venta en filas. Columnas: store_id, dept_id, d, cat_id, state_id, unidades, dolares, snap, columnas del Calendario. Ficha R-004.
- T-02 · marcas de cierre, del error y de los ceros: cierre_tienda en 175 y 56 días de serie de construcción y validación. Columnas: cierre_tienda, fuera_del_error, clase_cero. Ficha R-005.
- T-03 · precio medio del departamento de la semana anterior, cruces 6 y 7: 15.750 grupos con precio; 2.450 filas vacías, sin semana anterior o sin ningún producto con cuatro semanas de precio. Columnas: precio_medio_semana_anterior. Ficha R-009.
- T-04 · dimensión de producto: 500 productos con la clave sin repetir. Columnas: item_id, dept_id, cat_id. Ficha R-007.
- T-05 · dimensión de tienda: 10 tiendas con la clave sin repetir. Columnas: store_id, state_id. Ficha R-008.

## Variables generadas

| Columna | Fórmula | Sale de | Unidad | Posterior al día | Sale del objetivo | Suma de otras |
|---|---|---|---|---|---|---|
| unidades | suma de las unidades de los productos del departamento en la tienda ese día | d_1 a d_n de la venta | unidades | sí | sí | no |
| dolares | suma de unidades × sell_price de su semana, producto a producto, en céntimos | unidades, sell_price, wm_yr_wk | dólares | sí | sí | no |
| snap | snap_ca, snap_tx o snap_wi según state_id | state_id, snap_ca, snap_tx, snap_wi | - | no | no | no |
| cierre_tienda | todas las series de la tienda venden cero ese día | unidades, store_id, d | - | sí | sí | no |
| fuera_del_error | 25 de diciembre o cierre_tienda | date, cierre_tienda | - | sí | sí | no |
| clase_cero | en los ceros: cierre, 25_diciembre, demanda_intermitente (media del periodo sin cierres < 10) o resto | unidades, cierre_tienda, date, periodo | - | sí | sí | no |
| precio_medio_semana_anterior | media simple de sell_price de los productos del departamento con precio en la tienda la semana wm_yr_wk_anterior que ya lo tenían cuatro semanas antes | sell_price, dept_id, wm_yr_wk_anterior | dólares por unidad | no | no | no |

## Transformaciones pendientes

No hay ninguna: todas las transformaciones tienen su regla en las reglas de transformación.

## Cambios estructurales

- De «un producto en una tienda, con un día por columna» a «un producto en una tienda y día»: unidades 9.327.191 antes y 9.327.191 después (coincide).
- De «un producto en una tienda y día» a «un departamento en una tienda un día»: unidades 9.327.191 antes y 9.327.191 después (coincide); dólares (en céntimos) 2.498.272.854 antes y 2.498.272.854 después (coincide).
- De «un producto en una tienda y semana, con su precio» a «un departamento en una tienda y semana, con la media simple de sus precios con cuatro semanas de precio»: precios que entran en la media 854.573 antes y 854.573 después (coincide).

| Cruce | Partida | Se une | Filas antes | Filas después | Sin pareja en la partida | Cardinalidad | Hecho |
|---|---|---|---|---|---|---|---|
| 1 | venta en filas | Calendario | 7.875.000 | 7.875.000 | 0 | N:1 | sí |
| 2 | venta en filas | precios | 7.875.000 | 7.875.000 | 1.892.989 | N:1 | sí |
| 3 | venta en filas | dim_producto | 7.875.000 | 7.875.000 | 0 | N:1 | sí |
| 4 | hechos_series | dim_tienda | 110.250 | 110.250 | 0 | N:1 | sí |
| 5 | hechos_series | Calendario | 110.250 | 110.250 | 0 | N:1 | sí |
| 6 | precios | dim_producto | 854.573 | 854.573 | 0 | N:1 | sí |
| 7 | hechos_series | precio medio del departamento por semana | 110.250 | 110.250 | 490 | N:1 | sí |

Las filas sin pareja del cruce 2 son días sin precio, que suman cero dólares. Las del cruce 7 son los días de la semana sin anterior, con el precio medio vacío.

## Validación

- columnas de la tabla de series: **pasa**. 26 columnas; sobran []; faltan [].
- clave (store_id, dept_id, d) sin repetir: **pasa**. 0 filas repetidas.
- filas igual a series por días: **pasa**. 110.250 filas; 70 series por 1.575 días.
- unidades iguales a las de la venta en filas: **pasa**. 9.327.191 y 9.327.191.
- dólares iguales a los de la venta en filas: **pasa**. 24.982.728,54 y 24.982.728,54.
- los dólares guardados son los céntimos exactos: **pasa**. 0 filas cuyo importe con dos decimales no vuelve a sus céntimos.
- cada serie con una sola categoría: **pasa**. 0 series con más de una.
- todos los días de la tabla tienen periodo: **pasa**. 0 filas sin él.
- date es fecha, sin zona horaria y sin huecos: **pasa**. tipo datetime64[us]; 0 días que faltan entre el primero y el último.
- wm_yr_wk_anterior es la semana anterior por orden de fechas: **pasa**. 0 días del Calendario con otra semana anterior.
- snap es el del estado de la tienda: **pasa**. 0 filas con otro SNAP.
- clase_cero en todos los ceros y solo en ellos: **pasa**. 0 ceros sin regla; 0 ceros sin clase; 0 días con venta con clase.
- las series con ceros de demanda intermitente tienen media por debajo del umbral: **pasa**. media rehecha como suma entre días abiertos de cada serie en su periodo.
- clase_cero igual a clases_de_ceros de correccion-datos.json: **pasa**. aquí {'construccion': {'cierre': 175, '25_diciembre': 35, 'demanda_intermitente': 2171, 'resto': 35}, 'validacion': {'cierre': 56, '25_diciembre': 12, 'demanda_intermitente': 201, 'resto': 2}}; en la corrección {'construccion': {'cierre': 175, '25_diciembre': 35, 'demanda_intermitente': 2171, 'resto': 35}, 'validacion': {'cierre': 56, '25_diciembre': 12, 'demanda_intermitente': 201, 'resto': 2}}.
- fuera_del_error es el 25 de diciembre o el cierre: **pasa**. 287 filas marcadas.
- el precio medio está vacío en los días sin semana anterior: **pasa**. 2450 filas vacías; 490 sin semana anterior.
- el precio medio está vacío en los días cuya semana anterior no tiene ningún producto con cuatro semanas de precio: **pasa**. 1960 filas con la semana anterior sin ningún producto que cuente.
- dim_producto con la clave sin repetir: **pasa**. 500 filas.
- dim_tienda con la clave sin repetir: **pasa**. 10 filas.
- sumas de control de «un producto en una tienda, con un día por columna» a «un producto en una tienda y día»: **pasa**. antes y después.
- sumas de control de «un producto en una tienda y día» a «un departamento en una tienda un día»: **pasa**. antes y después.
- sumas de control de «un producto en una tienda y semana, con su precio» a «un departamento en una tienda y semana, con la media simple de sus precios con cuatro semanas de precio»: **pasa**. antes y después.
- productos-tienda sin precio igual al cruce venta-precios de calidad-datos.json: **pasa**. aquí 53; en la calidad 53.
- las tablas de entrada no cambian: **pasa**. cambiadas: [].

## Dataset generado

- `data/processed/hechos_series.parquet`: 110.250 filas y 26 columnas; una fila es un departamento en una tienda un día. Huella `31a6a1fbac4f87437ebdd70ca6ab06f55c189fcc87e8150c5d5d319056abf165`.
- `data/processed/dim_producto.parquet`: 500 filas y 3 columnas; una fila es un producto. Huella `5aa2ad7d0fc32f190175caa7ce67f64aaafd407c6105618ead65bb86b336c1e7`.
- `data/processed/dim_tienda.parquet`: 10 filas y 2 columnas; una fila es una tienda. Huella `744be76903218a6be24190f316231c569387936f0212b43068aed1715ef3571c`.

## Registro de exclusiones

| Clase | Qué sale | Columna | De qué cálculo | Recuento | Se puede recuperar |
|---|---|---|---|---|---|
| 25 de diciembre | los días de serie del 25 de diciembre | fuera_del_error | el error, el sesgo y la ventaja | construcción: 210 días de serie, 19 unidades y 36,17 dólares; validación: 70 días de serie, 3 unidades y 6,04 dólares | sí: siguen en la tabla de series con su venta |
| cierre fuera del 25 de diciembre | el cierre de una tienda entera fuera del 25 de diciembre | fuera_del_error | el error, el sesgo y la ventaja, como un 25 de diciembre | construcción: 7 días de serie, 0 unidades y 0,00 dólares; validación: 0 días de serie, 0 unidades y 0,00 dólares | sí: siguen en la tabla de series a cero |
| sin precio medio de la semana anterior | los días sin semana anterior o cuya semana anterior no tiene ningún producto con precio cuatro semanas antes (reglas, apartado 5) | precio_medio_semana_anterior | lo que use el precio medio de la semana anterior | construcción: 2.450 días de serie, 157.519 unidades y 394.448,77 dólares; validación: 0 días de serie, 0 unidades y 0,00 dólares | sí: siguen en la tabla de series con el precio vacío |
| productos-tienda sin ningún precio | nada: no venden ningún día y suman cero a su departamento | - | ninguno | 53 productos-tienda con 0 unidades | no hace falta: siguen en la venta corregida |
| días del calendario sin venta | los días del Calendario posteriores a la fecha de referencia | - | la tabla de series: no tienen venta en el caso | 394 días, del 2015-05-23 al 2016-06-19 | sí: siguen en el Calendario para producción |
| primeros días sin historia | los primeros días de cada serie sin la historia que piden las variables | - | la previsión y la comparación con las reglas (reglas, apartado 7) | se cuentan en el paso 5, cuando se fijen las variables | no: no hay datos antes del 29/01/2011 |

## Datos personales

No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada de personas. Esta transformación no usa ni deja ninguna columna de datos personales.

## Pendiente para el modelo

| Columna | Tipo | Valores | Orden real | Unidad | Mínimo | Máximo |
|---|---|---|---|---|---|---|
| store_id | categorica | 10 | no | - | - | - |
| dept_id | categorica | 7 | no | - | - | - |
| cat_id | categorica | 3 | no | - | - | - |
| state_id | categorica | 3 | no | - | - | - |
| weekday | categorica | 7 | sí | - | - | - |
| event_name_1 | categorica | 30 | no | - | - | - |
| event_type_1 | categorica | 4 | no | - | - | - |
| event_name_2 | categorica | 4 | no | - | - | - |
| event_type_2 | categorica | 2 | no | - | - | - |
| periodo | categorica | 2 | no | - | - | - |
| clase_cero | categorica | 4 | no | - | - | - |
| d | codigo numerico, es categoria | 1.575 | sí | - | - | - |
| year | codigo numerico, es categoria | 5 | sí | - | - | - |
| month | codigo numerico, es categoria | 12 | sí | - | - | - |
| wday | codigo numerico, es categoria | 7 | sí | - | - | - |
| wm_yr_wk | codigo numerico, es categoria | 225 | sí | - | - | - |
| wm_yr_wk_anterior | codigo numerico, es categoria | 224 | sí | - | - | - |
| snap | codigo numerico, es categoria | 2 | no | - | - | - |
| mes_parcial | marca verdadero o falso | 2 | no | - | - | - |
| semana_parcial | marca verdadero o falso | 2 | no | - | - | - |
| cierre_tienda | marca verdadero o falso | 2 | no | - | - | - |
| fuera_del_error | marca verdadero o falso | 2 | no | - | - | - |
| unidades | magnitud | 797 | sí | unidades | 0 | 1.059 |
| dolares | magnitud | 47.221 | sí | dólares | 0 | 3.014,14 |
| precio_medio_semana_anterior | magnitud | 6.087 | sí | dólares por unidad | 1,47 | 6,88 |
| date | fecha | 1.575 | sí | - | 2011-01-29 | 2015-05-22 |

Partición por `date` (reglas-negocio §5, «Fechas»): desarrollo del 2011-01-29 al 2014-05-22; validación del 2014-05-23 al 2015-05-22. Los dos días de cada tramo entran en él. Filas fuera de los dos tramos: 0.

## Teoría aplicada

- Manual 12.3: la venta llega en ancho, un día por columna; melt la pasa a una fila por producto, tienda y día para unirle la semana y el precio.
- Manual 12.5 y 12.6: al subir de producto a departamento las unidades y los dólares son flujos y se suman con su cuadre antes y después; el precio es un nivel y no se suma.
- Manual 3.5: el precio medio del departamento es la media simple de sus productos con precio desde cuatro semanas antes, fijada por el responsable del caso el 24/11/2026; la ponderada necesitaría unidades que en el horizonte no se conocen.
- Manual 12.7: no se suma un nivel: el precio medio nunca se suma entre filas ni entre series.

Límites:

- Los cruces comparan claves exactas: una clave que existe pero apunta a otra entidad no se detecta.
- El mismo producto o la misma tienda con dos códigos no se vería como repetido.
- El departamento de un producto y el estado de una tienda se toman como fijos: así están en los datos.
- Las sumas de control cubren las unidades, los dólares y el precio en céntimos de cada cruce.
- clase_cero usa la media de la serie en su periodo entero: sirve para describir y nunca entra como variable del modelo.
- Los primeros días de cada serie sin la historia que piden las variables se cuentan en el paso 5.
