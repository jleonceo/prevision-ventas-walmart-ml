# Diccionario de datos del origen · caso 69

Generado por `scripts/01_diccionario_datos.py` el 2026-11-21, a partir de `diccionario-datos-origen.json`. Fecha de los datos: 2015-05-22. Estado: **AVISO**, riesgo bajo.

Tres fuentes descritas: venta 5.000 filas, precios 854.573 filas y calendario 1.969 filas; las 1.575 columnas de días revisadas una a una, con 0 fuera del bloque. 3 contradicciones con la guía del concurso y 4 decisiones de negocio pendientes. No hubo paso de protección de datos: proteccion-datos.json no existe y las reglas, apartado 9 dicen que no hay datos personales.

## 1. Cabecera

- Comprobado el 2026-11-21 con Python 3.13.15 y pandas 3.0.6.
- `data/raw/sales_train_evaluation.csv`: 16.286.352 bytes; 5.000 filas; 1.581 columnas; huella `fcbeed85b09a49d3b1b0625a721053388f26e19490bf42e480e97ad6e177b7b2`.
- `data/raw/sell_prices.csv`: 26.245.223 bytes; 854.573 filas; 4 columnas; huella `3a3124852028006f94b6eb2c6b0a313df689ca2c75a6b8aaac0e67447f593a7f`.
- `data/raw/calendar.csv`: 103.469 bytes; 1.969 filas; 14 columnas; huella `d12b5914ef03e66649adf5dd9e996e6602251c22b7a6af8f1f7e3aa12f8860f5`.
- Diccionario de la organización: `config/fuentes/M5_guia_de_participantes_2020.docx`.
- Contexto usado: EQUIPO.md; config/negocio/reglas-negocio.md; config/negocio/01_ficha_del_caso.md; config/metodo/04_planteamientos.md; config/fuentes/M5_guia_de_participantes_2020.docx.

## 2. Lectura

| Tabla | Codificación | Separador | Decimal | Solo el campo vacío es nulo | Avisos |
|---|---|---|---|---|---|
| venta | utf-8 | `,` | `.` | sí | ninguno |
| precios | utf-8 | `,` | `.` | sí | ninguno |
| calendario | utf-8 | `,` | `.` | sí | ninguno |

## 3. Resumen

| Tabla | Qué es una fila | Filas | Columnas | Clave | Clave única |
|---|---|---|---|---|---|
| venta | un producto en una tienda, con una columna por día | 5.000 | 1.581 | id | sí |
| precios | un producto en una tienda en una semana de Walmart, con su precio | 854.573 | 4 | store_id, item_id, wm_yr_wk | sí |
| calendario | un día | 1.969 | 14 | d | sí |

## 4. Las tablas

### venta · `data/raw/sales_train_evaluation.csv`

Una fila es un producto en una tienda, con una columna por día. Clave: id (única: sí). Clave alternativa: item_id, store_id (única: sí).

Claves que parecen apuntar a otra tabla, todas supuestas porque la guía no declara relaciones:

- item_id, store_id → precios
- nombre de cada columna de días → calendario (columna d)

| Columna | Tipo leído | Rol | Nulos | % nulos | Vacíos | Espacios | Distintos | Mínimo | Máximo | Clase | Significado | Procedencia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| id | str | identificador | 0 | 0 | 0 | 0 | 5.000 | — | — | resuelto | identificador de la fila: el producto, la tienda y un sufijo fijo, unidos por guion bajo. La guía no lo documenta; el significado del sufijo se deduce del nombre del fichero y no se usa | medido; el sufijo, sin_confirmar |
| item_id | str | clave | 0 | 0 | 0 | 0 | 500 | — | — | resuelto | código del producto. Junto con store_id apunta a los precios (relación supuesta: la guía no la declara) | declarado (guía del concurso, «The dataset») |
| dept_id | str | categorica | 0 | 0 | 0 | 0 | 7 | — | — | resuelto | departamento al que pertenece el producto | declarado (guía del concurso, «The dataset»); reglas de negocio §4 |
| cat_id | str | categorica | 0 | 0 | 0 | 0 | 3 | — | — | resuelto | categoría a la que pertenece el producto: alimentación, ocio u hogar | declarado (guía del concurso, «The dataset»); reglas de negocio §4 |
| store_id | str | clave | 0 | 0 | 0 | 0 | 10 | — | — | resuelto | código de la tienda donde se vende el producto. Junto con item_id apunta a los precios (relación supuesta) | declarado (guía del concurso, «The dataset»); reglas de negocio §4 |
| state_id | str | categorica | 0 | 0 | 0 | 0 | 3 | — | — | resuelto | estado donde está la tienda | declarado (guía del concurso, «The dataset»); reglas de negocio §4 |

Valores de las columnas de texto con 15 distintos o menos:

- **dept_id**: FOODS_3 1.290; HOUSEHOLD_1 930; HOUSEHOLD_2 740; HOBBIES_1 730; FOODS_2 610; FOODS_1 430; HOBBIES_2 270
- **cat_id**: FOODS 2.330; HOUSEHOLD 1.670; HOBBIES 1.000
- **store_id**: CA_1 500; CA_2 500; CA_3 500; CA_4 500; TX_1 500; TX_2 500; TX_3 500; WI_1 500; WI_2 500; WI_3 500
- **state_id**: CA 2.000; TX 1.500; WI 1.500

#### El bloque de columnas de días

Las 1.575 columnas de días, de d_1 a d_1575, se revisaron una a una (1.575 revisadas). Numeración seguida desde d_1: sí.

| Rasgo | Valor |
|---|---|
| tipos leídos | int64: 1.575 columnas |
| vacíos en el bloque | 0 |
| negativos en el bloque | 0 |
| mínimo y máximo de una celda | 0 y 648 |
| columnas con algún cero | 1.575 |
| máximo más bajo de una columna | 1 |
| rol | magnitud |
| clase | resuelto |
| significado | unidades vendidas del producto en la tienda el día i, contado desde el 29/01/2011 |
| el cero | un día con cero unidades es un dato válido, no un vacío; no distingue falta de demanda de falta de producto (reglas de negocio §5) |
| la fila que falta | no falta ninguna fila: cada producto está en cada tienda (medido). Antes de su primera venta un producto suma cero a su departamento (reglas de negocio §3) |
| procedencia | declarado (guía del concurso, «The dataset»); reglas de negocio §5 |

Ninguna columna se sale del bloque.

#### Relaciones medidas dentro de la tabla

- filas donde id es producto tienda y sufijo: 5.000
- sufijos distintos de id: 1
- sufijo de id: evaluation
- productos cuyo código no empieza por su departamento: 0
- departamentos cuyo código no empieza por su categoría: 0
- tiendas cuyo código no empieza por su estado: 0
- productos con más de un departamento: 0
- departamentos con más de una categoría: 0
- tiendas con más de un estado: 0
- productos que no están en todas las tiendas: 0
- pares producto tienda repetidos: 0
- productos distintos: 500
- filas por departamento: FOODS_1: 430; FOODS_2: 610; FOODS_3: 1.290; HOBBIES_1: 730; HOBBIES_2: 270; HOUSEHOLD_1: 930; HOUSEHOLD_2: 740
- productos por departamento: FOODS_1: 43; FOODS_2: 61; FOODS_3: 129; HOBBIES_1: 73; HOBBIES_2: 27; HOUSEHOLD_1: 93; HOUSEHOLD_2: 74
- filas por tienda: CA_1: 500; CA_2: 500; CA_3: 500; CA_4: 500; TX_1: 500; TX_2: 500; TX_3: 500; WI_1: 500; WI_2: 500; WI_3: 500

#### Cifras por periodo

| Periodo | desde | hasta | primera columna | última columna | días | celdas | celdas a cero | celdas a cero % | unidades | máximo de una celda | productos tienda sin ninguna venta |
|---|---|---|---|---|---|---|---|---|---|---|---|
| construcción | 2011-01-29 | 2014-05-22 | d_1 | d_1210 | 1.210 | 6.050.000 | 4.278.752 | 70,72 | 7.003.244 | 648 | 306 |
| validación | 2014-05-23 | 2015-05-22 | d_1211 | d_1575 | 365 | 1.825.000 | 1.135.227 | 62,2 | 2.323.947 | 300 | 87 |

### precios · `data/raw/sell_prices.csv`

Una fila es un producto en una tienda en una semana de Walmart, con su precio. Clave: store_id, item_id, wm_yr_wk (única: sí).

Claves que parecen apuntar a otra tabla, todas supuestas porque la guía no declara relaciones:

- item_id, store_id → venta
- wm_yr_wk → calendario

| Columna | Tipo leído | Rol | Nulos | % nulos | Vacíos | Espacios | Distintos | Mínimo | Máximo | Clase | Significado | Procedencia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| store_id | str | clave | 0 | 0 | 0 | 0 | 10 | — | — | resuelto | código de la tienda | declarado (guía del concurso, «The dataset») |
| item_id | str | clave | 0 | 0 | 0 | 0 | 500 | — | — | resuelto | código del producto | declarado (guía del concurso, «The dataset») |
| wm_yr_wk | int64 | codigo | 0 | 0 | 0 | 0 | 225 | 11101 | 11516 | resuelto | código de la semana de Walmart, de sábado a viernes. Apunta a la semana del calendario (relación supuesta) | declarado (guía del concurso, «The dataset»); reglas de negocio §5 |
| sell_price | float64 | magnitud | 0 | 0 | 0 | 0 | 572 | 0,01 | 34,18 | resuelto | precio de venta del producto en la tienda esa semana, en dólares: la media de los siete días, que vale para los siete | declarado (guía del concurso, «The dataset»); reglas de negocio §5 y §6 |

Valores de las columnas de texto con 15 distintos o menos:

- **store_id**: TX_2 88.368; TX_1 87.676; CA_1 87.510; WI_3 87.358; CA_3 86.670; TX_3 86.504; WI_2 84.927; CA_4 84.126; WI_1 82.211; CA_2 79.223

El cero de sell_price: no hay ceros (medido); un precio cero hace sospechar (reglas de negocio §7, «Lo esperable»). La fila que falta: una semana sin fila es una semana en que el producto no se vendió en esa tienda (guía del concurso; reglas de negocio §5).

#### Relaciones medidas dentro de la tabla

- productos distintos: 500
- tiendas distintas: 10
- semanas distintas: 225
- productos tienda con algún precio: 4.947
- precios con más de dos decimales: 0
- precios por debajo del rango esperable: 9.438
- precios por encima del rango esperable: 0
- rango esperable: 0,5 a 50
- precios cero o negativos: 0

#### Cifras por periodo

| Periodo | filas | semana mínima | semana máxima | productos tienda con precio | precio mínimo | precio máximo |
|---|---|---|---|---|---|---|
| hasta la última semana de construcción | 603.600 | 11101 | 11416 | 4.700 | 0,05 | 29,97 |
| después | 250.973 | 11417 | 11516 | 4.947 | 0,01 | 34,18 |

### calendario · `data/raw/calendar.csv`

Una fila es un día. Clave: d (única: sí). Clave alternativa: date (única: sí).

Claves que parecen apuntar a otra tabla, todas supuestas porque la guía no declara relaciones:

- d → venta (nombre de cada columna de días)
- wm_yr_wk → precios

| Columna | Tipo leído | Rol | Nulos | % nulos | Vacíos | Espacios | Distintos | Mínimo | Máximo | Clase | Significado | Procedencia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| date | str | fecha | 0 | 0 | 0 | 0 | 1.969 | 2011-01-29 | 2016-06-19 | resuelto | fecha del día, en formato año-mes-día | declarado (guía del concurso, «The dataset») |
| wm_yr_wk | int64 | codigo | 0 | 0 | 0 | 0 | 282 | 11101 | 11621 | resuelto | código de la semana de Walmart a la que pertenece el día | declarado (guía del concurso, «The dataset») |
| weekday | str | categorica | 0 | 0 | 0 | 0 | 7 | — | — | resuelto | nombre del día de la semana, en inglés | declarado (guía del concurso, «The dataset») |
| wday | int64 | codigo | 0 | 0 | 0 | 0 | 7 | 1 | 7 | resuelto | número del día de la semana, empezando por el sábado | declarado (guía del concurso, «The dataset») |
| month | int64 | codigo | 0 | 0 | 0 | 0 | 12 | 1 | 12 | resuelto | mes de la fecha | declarado (guía del concurso, «The dataset») |
| year | int64 | codigo | 0 | 0 | 0 | 0 | 6 | 2011 | 2016 | resuelto | año de la fecha | declarado (guía del concurso, «The dataset») |
| d | str | clave | 0 | 0 | 0 | 0 | 1.969 | — | — | resuelto | código del día, de d_1 en adelante, que coincide con el nombre de las columnas de días de la venta (relación supuesta, medida) | medido; sin documentar en la guía |
| event_name_1 | str | categorica | 1.807 | 91,77 | 0 | 0 | 30 | — | — | decisión de negocio | nombre del evento del día; vacío quiere decir «sin evento» | declarado (guía del concurso, «The dataset»); reglas de negocio §5 |
| event_type_1 | str | categorica | 1.807 | 91,77 | 0 | 0 | 4 | — | — | decisión de negocio | tipo del evento del día; vacío quiere decir «sin evento» | declarado (guía del concurso, «The dataset»); reglas de negocio §5 |
| event_name_2 | str | categorica | 1.964 | 99,75 | 0 | 0 | 4 | — | — | decisión de negocio | nombre del segundo evento del día; vacío quiere decir «sin segundo evento» | declarado (guía del concurso, «The dataset»); reglas de negocio §5 |
| event_type_2 | str | categorica | 1.964 | 99,75 | 0 | 0 | 2 | — | — | decisión de negocio | tipo del segundo evento del día; vacío quiere decir «sin segundo evento» | declarado (guía del concurso, «The dataset»); reglas de negocio §5 |
| snap_CA | int64 | booleana | 0 | 0 | 0 | 0 | 2 | — | — | resuelto | 1 si las tiendas de California aceptan compras con SNAP ese día; 0 si no | declarado (guía del concurso, «The dataset») |
| snap_TX | int64 | booleana | 0 | 0 | 0 | 0 | 2 | — | — | resuelto | 1 si las tiendas de Texas aceptan compras con SNAP ese día; 0 si no | declarado (guía del concurso, «The dataset») |
| snap_WI | int64 | booleana | 0 | 0 | 0 | 0 | 2 | — | — | resuelto | 1 si las tiendas de Wisconsin aceptan compras con SNAP ese día; 0 si no | declarado (guía del concurso, «The dataset») |

Valores de las columnas de texto con 15 distintos o menos:

- **weekday**: Saturday 282; Sunday 282; Monday 281; Tuesday 281; Wednesday 281; Thursday 281; Friday 281
- **event_type_1**: Religious 55; National 52; Cultural 37; Sporting 18
- **event_name_2**: Father's day 2; Easter 1; Cinco De Mayo 1; OrthodoxEaster 1
- **event_type_2**: Cultural 4; Religious 1

Categorías raras (menos del 2,5 % de las filas o menos de cinco apariciones):

- **event_name_1**: 30 de 30 categorías.
- **event_type_1**: 2 de 4 categorías.
- **event_name_2**: 4 de 4 categorías.
- **event_type_2**: 2 de 2 categorías.

#### Relaciones medidas dentro de la tabla

- fechas que no se leen como año mes día: 0
- días seguidos sin hueco: sí
- d numerado de 1 en adelante sin hueco: sí
- fecha de d1: 2011-01-29
- filas con wday distinto del que toca a weekday: 0
- filas con month distinto del mes de date: 0
- filas con year distinto del año de date: 0
- semanas: 282
- semanas con siete días: 281
- semanas incompletas: 11621: 2
- semanas que no empiezan en sábado: 0
- filas con nombre y tipo del evento 1 descuadrados: 0
- filas con nombre y tipo del evento 2 descuadrados: 0
- días con segundo evento sin primero: 0

#### Cifras por periodo

| Periodo | desde | hasta | filas | días con evento | días con dos eventos | días snap | semana mínima | semana máxima |
|---|---|---|---|---|---|---|---|---|
| construcción | 2011-01-29 | 2014-05-22 | 1.210 | 99 | 3 | snap_CA 400; snap_TX 400; snap_WI 400 | 11101 | 11416 |
| validación | 2014-05-23 | 2015-05-22 | 365 | 29 | 1 | snap_CA 120; snap_TX 120; snap_WI 120 | 11416 | 11516 |
| después de la fecha de referencia | 2015-05-23 | 2016-06-19 | 394 | 34 | 1 | snap_CA 130; snap_TX 130; snap_WI 130 | 11517 | 11621 |

## 5. Contradicciones con el diccionario de la organización

El diccionario de la organización es la guía de participantes del concurso (`config/fuentes/M5_guia_de_participantes_2020.docx`), apartado «The dataset». Se pusieron 26 afirmaciones suyas frente a los datos. Mandan los datos.

| Tabla | Columna | Qué dice la guía | Qué dicen los datos |
|---|---|---|---|
| venta | id | no la documenta | la columna id está en el fichero |
| calendario | d | no la documenta | la columna d está en el fichero |
| venta | (fichero) | el fichero se llama sales_train.csv | el fichero se llama sales_train_evaluation.csv |

Lo que difiere porque el caso es un recorte, que no es una contradicción:

- venta, item_id: la guía dice 3049 productos; los datos traen 500 productos. Motivo: recorte de 500 productos (reglas de negocio §3).
- venta, d_1 … d_n: la guía dice d_1 a d_1941; los datos traen d_1 a d_1575. Motivo: la prueba final está apartada fuera del caso (reglas de negocio §5).
- precios, wm_yr_wk: la guía dice precios hasta la última semana del concurso; los datos traen semanas 11101 a 11516. Motivo: la prueba final está apartada fuera del caso (reglas de negocio §5).

Las afirmaciones de la guía que los datos cumplen:

- precios, (fichero): el fichero se llama sell_prices.csv. Datos: el fichero se llama sell_prices.csv.
- calendario, (fichero): el fichero se llama calendar.csv. Datos: el fichero se llama calendar.csv.
- venta, d_1 … d_n: las unidades vendidas el día i: un número entero de unidades. Datos: 1575 columnas; int64 en 1575; 0 vacíos; 0 negativos.
- calendario, d: el día d_1 es el 2011-01-29. Datos: d_1 es el 2011-01-29.
- calendario, date: los datos van del 2011-01-29 al 2016-06-19. Datos: el calendario va del 2011-01-29 al 2016-06-19.
- calendario, date: formato año-mes-día. Datos: 0 fechas no se leen con ese formato.
- calendario, weekday: el día de la semana, de sábado a viernes. Datos: valores fuera de los siete días: ninguno.
- calendario, wday: número del día de la semana, empezando por el sábado. Datos: 0 filas no casan con weekday.
- calendario, month: el mes de la fecha. Datos: 0 filas no casan con date.
- calendario, year: el año de la fecha. Datos: 0 filas no casan con date.
- calendario, event_name_1 y event_type_1: si el día tiene evento, su nombre y su tipo. Datos: 0 filas con nombre sin tipo o tipo sin nombre.
- calendario, event_name_2 y event_type_2: si el día tiene evento, su nombre y su tipo. Datos: 0 filas con nombre sin tipo o tipo sin nombre.
- calendario, snap_CA: binaria, 0 o 1. Datos: valores 0, 1; 0 vacíos.
- calendario, snap_TX: binaria, 0 o 1. Datos: valores 0, 1; 0 vacíos.
- calendario, snap_WI: binaria, 0 o 1. Datos: valores 0, 1; 0 vacíos.
- venta, state_id: el estado donde está la tienda. Datos: 0 tiendas con más de un estado; 0 filas cuyo código de tienda no empieza por su estado.
- venta, dept_id: los departamentos desagregan las categorías. Datos: 0 departamentos en más de una categoría.
- venta, item_id: cada producto pertenece a un departamento. Datos: 0 productos en más de un departamento.
- venta, cat_id: 3 valores distintos. Datos: 3 valores distintos.
- venta, dept_id: 7 valores distintos. Datos: 7 valores distintos.
- venta, store_id: 10 valores distintos. Datos: 10 valores distintos.
- venta, state_id: 3 valores distintos. Datos: 3 valores distintos.
- precios, sell_price: una semana sin precio es una semana en que el producto no se vendió. Datos: no se comprueba aquí: hace falta cruzar con la venta y el calendario (calidad-datos, bloque 3.11).

## 6. Columnas que no llegan al análisis

No hay código de carga todavía: scripts/ no tenía ningún script antes de este. Ninguna columna se descarta en la lectura.

## 7. Filtros de negocio

- reglas de negocio §5: la prueba final (del 23/05/2015 al 22/05/2016) está fuera de data/raw/; la venta llega hasta el 22/05/2015: 0 filas de data/raw/ afectadas.
- reglas de negocio §5: el calendario llega a propósito hasta el 19/06/2016; los días después de la fecha de referencia no tienen venta en el caso: 394 filas del calendario.
- reglas de negocio §7, «Población del análisis»: el reconocimiento y la exploración usan solo la construcción; la validación se mira al medir el modelo: 365 columnas de días de la venta en la validación.
- precios después de la última semana de la construcción, que entran en la validación: 250.973 filas de precios.

## 8. Decisiones de negocio pendientes

- **P-01 · calendario, event_name_1.** 30 de sus 30 categorías son raras (menos del 2,5 % de las filas o menos de 5 apariciones, contando los días sin evento). ¿Cómo se leen? Lecturas posibles: (1) cada evento se lee por su nombre, aunque aparezca una vez al año; (2) los eventos se leen por su tipo (event_type_1), juntando los nombres.
- **P-02 · calendario, event_type_1.** 2 de sus 4 categorías son raras (menos del 2,5 % de las filas o menos de 5 apariciones, contando los días sin evento). ¿Cómo se leen? Lecturas posibles: (1) cada tipo de evento se lee por sí solo, aunque alguno tenga pocos días; (2) los tipos con pocos días se leen juntos, o todos los tipos como un solo «día con evento».
- **P-03 · calendario, event_name_2.** 4 de sus 4 categorías son raras (menos del 2,5 % de las filas o menos de 5 apariciones, contando los días sin evento). ¿Cómo se leen? Lecturas posibles: (1) cada segundo evento se lee por su nombre; (2) los segundos eventos se leen por su tipo (event_type_2), juntando los nombres.
- **P-04 · calendario, event_type_2.** 2 de sus 2 categorías son raras (menos del 2,5 % de las filas o menos de 5 apariciones, contando los días sin evento). ¿Cómo se leen? Lecturas posibles: (1) cada tipo del segundo evento se lee por sí solo; (2) el segundo evento se lee junto con el primero, como un día con evento.

## 9. Lo que no se puede saber

- si el precio lleva impuestos de venta (reglas de negocio §6).
- cuándo fija la tienda el precio dentro de la semana (reglas de negocio §5).
- si un día con cero unidades tenía producto en el estante: no hay existencias (reglas de negocio §5).
- qué quiere decir el sufijo fijo de id (la guía no documenta la columna id).

## 10. Datos personales

No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas de negocio §9 dicen que no hay datos de personas y el paso 2a no se hizo. Esta ejecución buscó en cada columna de texto valores con forma de correo, teléfono, documento o cuenta y encontró 0 columnas con ellos. Este método no usa ni deja ninguna columna de datos personales.

## 11. Límites

- el diccionario describe una tabla cada vez; las claves huérfanas o repetidas entre tablas se ven primero en el apartado «Cruces entre tablas» de calidad-datos y se controlan al cruzarlas con integracion-datos
- la detección de datos personales mira columnas enteras; un nombre dentro de texto libre no lo caza
- las descripciones «sin confirmar» son deducciones y no se usan como regla
- el reparto de los vacíos por segmento no se mide aquí: lo mide calidad-datos en el bloque 3.4
- la afirmación de la guía sobre la semana sin precio necesita cruzar tablas y se comprueba en calidad-datos

## Validación de esta ejecución

- todas las columnas de las tres fuentes tienen ficha o están en el bloque de días: sí.
- cada significado tiene procedencia: sí.
- ninguna columna con dato personal muestra valores: sí.
- columnas con valores de forma de dato personal: 0.
- las huellas de data/raw/ son iguales antes y después: sí.
- las 1.575 columnas de días revisadas una a una: 1.575.

## Parámetros

- orden de codificaciones: utf-8, utf-8-sig, cp1252, latin-1 (por defecto).
- filas donde buscar la cabecera de un Excel: — (no aplica: no hay Excel).
- lista completa de valores de un texto: 15 (por defecto).
- categoría rara: menos del 2,5 % de las filas o menos de 5 apariciones (por defecto).
- apertura de bases de datos: — (no aplica: no hay bases de datos).
- ficheros de un ZIP que no se abren: — (no aplica: no hay ZIP).
