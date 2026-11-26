# Modelado de datos · caso 69

Diseño: `config/modelo/modelo-datos.md`. Estado: **OK**. Riesgo: bajo.

## Fuente

- Script: `scripts/04_modelado_datos.py`, ejecutado el 2026-11-24T11:04:42.
- Fecha de los datos: 2015-05-22.
- `data/processed/venta_corregido.parquet`: 5.000 filas y 1.581 columnas; huella `8d54b88b01a9`.
- `data/processed/precios_corregido.parquet`: 854.573 filas y 4 columnas; huella `d9ac5467e59d`.
- `data/processed/calendario_corregido.parquet`: 1.969 filas y 14 columnas; huella `1754b2bb702d`.

## Resumen

Diseño comprobado sobre las tres tablas corregidas: 0 contradicciones con los datos. Cuatro tablas de entrega (la de series, dos dimensiones y el Calendario) y 7 cruces en el plan, todos muchos a uno.

Aprobado por el responsable del caso el 2026-11-24.
Siguiente: las reglas de transformación y transformacion-datos, con el plan de cruces.

## Tablas y grano

| Tabla | Tipo | Grano | Clave del grano | Clave única | Filas repetidas |
|---|---|---|---|---|---|
| venta | hechos | una fila por producto y tienda, con las unidades de cada día en 1.575 columnas (d_1 a d_1575); el hecho es producto, tienda y día, que la transformación pasa a filas | item_id, store_id | sí | 0 |
| precios | hechos | una fila por producto, tienda y semana de Walmart, con su precio | store_id, item_id, wm_yr_wk | sí | 0 |
| calendario | dimension | una fila por día | d | sí | 0 |
| dim_producto | dimension | una fila por producto | item_id | se comprueba al construirla | sin dato |
| dim_tienda | dimension | una fila por tienda | store_id | se comprueba al construirla | sin dato |
| Calendario | dimension | una fila por día | d | sí | 0 |
| hechos_series | hechos | una fila por serie (departamento en una tienda) y día | store_id, dept_id, d | se comprueba al construirla | sin dato |

## Relaciones

| Desde | Hacia | Clave | Maestro | Cardinalidad | Procedencia | Mismo tipo |
|---|---|---|---|---|---|---|
| venta en filas | Calendario | d → d | Calendario | N:1 | guía del concurso (d_1 … d_n son los días, d_1 el 29/01/2011); reglas, apartado 5 (cada venta es del día natural de la tienda) | sí |
| venta en filas | precios | item_id, store_id, wm_yr_wk → item_id, store_id, wm_yr_wk | precios | N:1 | reglas, apartado 5 (el precio es el de un producto en una tienda durante una semana de Walmart y vale para sus siete días; la venta en dólares multiplica las unidades de cada día por ese precio); guía del concurso | sí |
| venta en filas | dim_producto | item_id → item_id | dim_producto | N:1 | reglas, apartado 3 (dos productos son distintos por su código) y §4 (producto, departamento y categoría); guía del concurso | sí |
| precios | dim_producto | item_id → item_id | dim_producto | N:1 | reglas, apartado 4 (cada producto pertenece a un departamento); ficha, pregunta 4 (precio medio del departamento por semana) | sí |
| hechos_series | dim_tienda | store_id → store_id | dim_tienda | N:1 | reglas, apartado 3 (dos tiendas son distintas por su código y pertenecen a un estado) y §4 | sí |
| hechos_series | Calendario | d → d | Calendario | N:1 | reglas, apartado 3 (la serie es la venta diaria de un departamento en una tienda) y §5 | sí |
| hechos_series | precio medio del departamento por semana | store_id, dept_id, wm_yr_wk_anterior → store_id, dept_id, wm_yr_wk | precio medio del departamento por semana | N:1 | reglas, apartado 5, D9 (el precio que entra en la previsión de un día es el de la semana anterior); ficha, pregunta 4 | sí |

## Calendario

Por días, del 2011-01-29 al 2016-06-19, con 0 días que faltan. Construido en `data/processed/calendario.parquet` con 1.969 días: 1.210 de construcción, 365 de validación y 394 sin periodo. Huella `a8478ae161ca`.

- construcción (2011-01-29 a 2014-05-22, 1.210 días): meses parciales 2011-01, 2014-05; semanas parciales 11416.
- validación (2014-05-23 a 2015-05-22, 365 días): meses parciales 2014-05, 2015-05; semanas parciales 11416.
- sin periodo (2015-05-23 a 2016-06-19, 394 días): meses parciales 2015-05, 2016-06; semanas parciales 11621.
- La semana 11416 cruza los dos periodos: 6 días en la construcción y 1 en la validación.
- Saltos de código entre una semana y la siguiente: 5. La semana anterior se toma por orden de fechas, nunca restando 1 al código.

## Plan de cruces

| Orden | Partida | Se une | Clave | Cardinalidad | Tipo | Control | Agregar antes |
|---|---|---|---|---|---|---|---|
| 1 | venta en filas | Calendario | d → d | N:1 | left | unidades | no |
| 2 | venta en filas | precios | item_id, store_id, wm_yr_wk → item_id, store_id, wm_yr_wk | N:1 | left | unidades | no |
| 3 | venta en filas | dim_producto | item_id → item_id | N:1 | left | unidades, dolares | no |
| 4 | hechos_series | dim_tienda | store_id → store_id | N:1 | left | unidades, dolares | a store_id, dept_id, d |
| 5 | hechos_series | Calendario | d → d | N:1 | left | unidades, dolares | no |
| 6 | precios | dim_producto | item_id → item_id | N:1 | left | filas, sell_price | no |
| 7 | hechos_series | precio medio del departamento por semana | store_id, dept_id, wm_yr_wk_anterior → store_id, dept_id, wm_yr_wk | N:1 | left | unidades, dolares | a store_id, dept_id, wm_yr_wk |

## Registro de exclusiones

| Qué sale | De qué cálculo | Recuento | Se puede recuperar |
|---|---|---|---|
| los días de serie del 25 de diciembre | el error, el sesgo y la ventaja del modelo y de las tres reglas (reglas, apartado 6) | 210 días de serie en construcción; 70 días de serie en validación | sí: se quedan en la tabla |
| el cierre de toda una tienda fuera del 25 de diciembre | el error, como un 25 de diciembre (reglas, apartado 5; PC-03) | WI_1 el 2011-02-02, 7 días de serie en construcción | sí: se queda en la tabla |
| nada: suman cero a su departamento | ninguno; la venta en dólares les da cero | 53 productos-tienda con 0 unidades | no hace falta: no salen |
| los días del calendario posteriores a la fecha de referencia | la tabla de series: no tienen venta en el caso | 394 días | con la prueba final, copiada por la persona responsable |
| los primeros días de cada serie sin la historia que piden las variables | la previsión y la comparación con las reglas (reglas, apartado 7, «Población del análisis») | pendiente del paso 5, cuando se fijen las variables | no: no hay datos antes del 29/01/2011 |

## Precio medio del departamento

Medido en la construcción sobre 12.110 semanas de departamento en tienda; 12.108 tienen las dos medias.

- Diferencia relativa sin signo: media 28,52 %; mediana 28,04 %.
- Percentil 95: 51,97 %. Máxima: 93,39 %.
- La ponderada queda por debajo de la simple en el 95,02 % de las semanas.
- FOODS_1: 25,24 % de media.
- FOODS_2: 36,90 % de media.
- FOODS_3: 30,81 % de media.
- HOBBIES_1: 43,23 % de media.
- HOBBIES_2: 20,11 % de media.
- HOUSEHOLD_1: 22,19 % de media.
- HOUSEHOLD_2: 21,11 % de media.

Elegida la media simple, porque la ponderada necesita unidades que dentro del horizonte todavía no se conocen (planteamientos; el responsable del caso, 24/11/2026).

## Comprobaciones

- filas de venta, precios y calendario: 5.000, 854.573 y 1.969.
- claves del grano repetidas en venta, precios y calendario: 0, 0 y 0 filas.
- productos, tiendas y series: 500, 10 y 70.
- productos por departamento iguales en las diez tiendas: sí.
- días de la venta: d_1 es el sábado 2011-01-29; d_1575 es el viernes 2015-05-22.
- semanas de la venta: 225, de la 11101 a la 11516; incompletas 0.
- semanas de los precios iguales a las de la venta: sí.
- último día de la construcción: jueves 2014-05-22, semana 11416.
- productos-tienda sin precio y precios sin producto-tienda: 53 y 0.
- semanas del calendario sin precio y días del calendario sin venta: 57 y 394.
- unidades: 9.327.191.
- días con venta y sin precio; días sin precio: 0; 1.892.989.
- dólares con el precio de su semana: 24.982.728,54.

Ningún dato contradice el diseño.

## Decisiones pendientes

- ¿Cuántos días de cada evento hacen falta para dar su efecto en la pregunta 4? Es de método y va a los planteamientos con la fórmula de cada efecto. Opciones: un mínimo fijado en los planteamientos / dar todos los efectos marcando los de pocos días.

## Datos personales

No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario y no traen nada de personas. Este método no usa ni deja ninguna columna de datos personales.

## Límites

- El script comprueba el grano y los tipos de las claves. Si las claves casan entre tablas lo mide integracion-datos, salvo los recuentos que pide el registro de exclusiones.
- En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar. El diccionario y la corrección cuentan cero vacíos en las claves de las tres tablas; si apareciera uno, el cruce para antes de unir.
- Un maestro que cambia con el tiempo se modela con la versión que hay. Aquí no cambia: el departamento de un producto y el estado de una tienda son fijos en los datos.
- Los dólares se calculan solo para contar y sumar, con el precio buscado por índice de semana. La única tabla que se guarda es el Calendario.
- La diferencia entre la media simple y la ponderada del precio del departamento se mide en la construcción. La semana 11416 entra con sus días de la construcción.
