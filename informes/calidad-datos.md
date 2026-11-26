# Calidad de los datos · caso 69

Informe generado por `scripts/02_calidad_datos.py` a partir de `informes/calidad-datos.json`. Estado **AVISO**, riesgo medio. Fecha de los datos: 2015-05-22.

## Fuente analizada

- `data/raw/sales_train_evaluation.csv`: 16.286.352 bytes; 5.000 filas; 1.581 columnas; huella `fcbeed85b09a49d3b1b0625a721053388f26e19490bf42e480e97ad6e177b7b2`.
- `data/raw/sell_prices.csv`: 26.245.223 bytes; 854.573 filas; 4 columnas; huella `3a3124852028006f94b6eb2c6b0a313df689ca2c75a6b8aaac0e67447f593a7f`.
- `data/raw/calendar.csv`: 103.469 bytes; 1.969 filas; 14 columnas; huella `d12b5914ef03e66649adf5dd9e996e6602251c22b7a6af8f1f7e3aa12f8860f5`.
- Ejecutado el 2026-11-24 con Python 3.13.15 y pandas 3.0.6, en 7,5 segundos.
- Partió del diccionario del origen: sí (estado AVISO, misma huella: sí).
- Plan aprobado por el responsable del caso el 2026-11-21.

## Resumen

Diagnóstico de las tres tablas con el plan aprobado: 29 problemas y 6 cuestiones pendientes. Las reglas que paran el trabajo no saltan: 0 ventas negativas y 0 semanas con venta y sin precio. Lo que más pesa son 9.438 precios por debajo de 0,5 dólares y los saltos de nivel de 28 series en la construcción.

Lo que la persona responsable tiene que leer antes de corregir:

- **PC-01.** 9.438 precios quedan por debajo de 0,5 dólares, fuera de «Lo esperable». ¿Cómo se leen?
- **PC-02.** En 350 semanas el precio pasa a más del doble que la semana anterior. ¿Cómo se leen?
- **PC-03.** Fuera del 25 de diciembre hay 1 cierre de tienda: WI_1 el 2011-02-02, sin evento. ¿Cómo se lee?
- **PC-04.** El 25 de diciembre suma 22 unidades en 4 años. Esas unidades se venden en 8 de los 40 días de tienda de esa fecha (10 tiendas en 4 años); en los otros 32, la tienda entera vende cero. ¿Cómo se leen las unidades del 25 de diciembre?
- **PC-05.** En la construcción, 28 series tienen un salto de nivel. ¿Cómo se leen?
- **PC-06.** En la validación, 12 series tienen un salto de nivel. ¿Cómo se leen?

## Inspección general

- venta: 5.000 filas y 1.581 columnas, según el diccionario; clave id.
- precios: 854.573 filas y 4 columnas, según el diccionario; clave store_id, item_id, wm_yr_wk.
- calendario: 1.969 filas y 14 columnas, según el diccionario; clave d.
- Venta en la construcción: del 2011-01-29 al 2014-05-22, 1.210 días (d_1 a d_1210).
- Venta en la validación: del 2014-05-23 al 2015-05-22, 365 días (d_1211 a d_1575).
- Precios hasta la semana 11416: semanas 11101 a 11416, 603.600 filas.
- Precios después de la semana 11416: semanas 11417 a 11516, 250.973 filas.
- Calendario, construcción: del 2011-01-29 al 2014-05-22, 1.210 días.
- Calendario, validación: del 2014-05-23 al 2015-05-22, 365 días.
- Calendario, después de la fecha de referencia: del 2015-05-23 al 2016-06-19, 394 días.
- La semana 11416 tiene 6 días en la construcción y 1 en la validación: lo que se reparte por semana se da hasta ella y después.

## Estructura

- venta, periodos repartidos en columnas: una columna por día, de d_1 a d_1575.
- venta, columna doble: id es item_id, store_id y un sufijo, unidos por guion bajo (100 % de las filas).
- todas, celdas que empiezan como una lista o un JSON: 0.
- Columnas vacías: ninguna. Columnas constantes: ninguna.
- Nombre `snap_CA` de calendario: normalizado `snap_ca`; colisión: ninguna.
- Nombre `snap_TX` de calendario: normalizado `snap_tx`; colisión: ninguna.
- Nombre `snap_WI` de calendario: normalizado `snap_wi`; colisión: ninguna.

## Tipos y formatos

- precios.wm_yr_wk: leído como int64, toca código (semana) (codigo_numerico); no se convierte el 0 %.
- calendario.date: leído como str, toca fecha (fecha_como_texto); no se convierte el 0 %.
- calendario.wm_yr_wk: leído como int64, toca código (codigo_numerico); no se convierte el 0 %.
- calendario.wday: leído como int64, toca código (codigo_numerico); no se convierte el 0 %.
- calendario.month: leído como int64, toca código (codigo_numerico); no se convierte el 0 %.
- calendario.year: leído como int64, toca código (codigo_numerico); no se convierte el 0 %.
- calendario.d: leído como str, toca texto (texto_con_numero); no se convierte el 0 %.
- calendario.snap_CA: leído como int64, toca booleano (booleano_enmascarado); no se convierte el 0 %.
- calendario.snap_TX: leído como int64, toca booleano (booleano_enmascarado); no se convierte el 0 %.
- calendario.snap_WI: leído como int64, toca booleano (booleano_enmascarado); no se convierte el 0 %.
- Las demás columnas tienen el tipo que toca por su rol.
- Escala de venta.unidades (d_1 a d_1575) en construcción: 5.914.290 valores de 1 cifra; 134.374 valores de 2 cifras; 1.336 valores de 3 cifras. Salto de escala: no.
- Escala de venta.unidades (d_1 a d_1575) en validación: 1.785.676 valores de 1 cifra; 39.025 valores de 2 cifras; 299 valores de 3 cifras. Salto de escala: no.
- Escala de precios.sell_price en hasta la semana 11416: 570.541 valores de 1 cifra; 33.059 valores de 2 cifras. Salto de escala: no.
- Escala de precios.sell_price en después de la semana 11416: 236.786 valores de 1 cifra; 14.187 valores de 2 cifras. Salto de escala: no.
- Grupos por departamento y periodo con un hueco en el número de cifras: 0.
- Los 9.438 precios por debajo de 0,5 dólares son de 104 productos-tienda; 50 los tienen en todas sus semanas. En los demás, la mediana del producto-tienda entre el precio bajo va de 0,96 a 264 veces: no es un factor uniforme.

## Valores ausentes

- calendario.event_name_1: 91,77 % global; veredicto **repartidos**; segmentos con más: periodo validación 92,05 %; periodo construcción 91,82 %; periodo después de la fecha de referencia 91,37 %.
- calendario.event_type_1: 91,77 % global; veredicto **repartidos**; segmentos con más: periodo validación 92,05 %; periodo construcción 91,82 %; periodo después de la fecha de referencia 91,37 %.
- calendario.event_name_2: 99,75 % global; veredicto **repartidos**; segmentos con más: periodo construcción 99,75 %; periodo después de la fecha de referencia 99,75 %; periodo validación 99,73 %.
- calendario.event_type_2: 99,75 % global; veredicto **repartidos**; segmentos con más: periodo construcción 99,75 %; periodo después de la fecha de referencia 99,75 %; periodo validación 99,73 %.
- precios.sell_price (semana sin fila): 24,04 % global; veredicto **repartidos**; segmentos con más: departamento HOBBIES_2 33,28 %; periodo hasta la semana 11416 30,22 %; departamento HOUSEHOLD_1 29,95 %.
- Semanas producto-tienda sin precio: 270.427, de ellas 258.502 antes del primer precio y 0 en huecos.
- Código «vacío» en calendario.event_name_1 (todo el calendario): 1.807 (91,77 %); documentado: sí; sin evento (reglas, apartado 5).
- Código «vacío» en calendario.event_type_1 (todo el calendario): 1.807 (91,77 %); documentado: sí; sin evento (reglas, apartado 5).
- Código «vacío» en calendario.event_name_2 (todo el calendario): 1.964 (99,75 %); documentado: sí; sin evento (reglas, apartado 5).
- Código «vacío» en calendario.event_type_2 (todo el calendario): 1.964 (99,75 %); documentado: sí; sin evento (reglas, apartado 5).
- Código «0» en venta.unidades (d_1 a d_1575) (construcción): 4.278.752 (70,72 %); documentado: sí; 1.829.500 de esas celdas caen en una semana sin fila de precio (42,76 %).
- Código «0» en venta.unidades (d_1 a d_1575) (validación): 1.135.227 (62,2 %); documentado: sí; 63.489 de esas celdas caen en una semana sin fila de precio (5,59 %).
- Textos y números buscados como posibles códigos de ausencia en las tres tablas: 0 hallados.
- Vacíos por fila en venta: 5.000 filas con 0. Sin las columnas excluidas: 5.000 filas con 0.
- Vacíos por fila en precios: 854.573 filas con 0. Sin las columnas excluidas: 854.573 filas con 0.
- Vacíos por fila en calendario: 5 filas con 0; 157 filas con 2; 1.807 filas con 4. Sin las columnas excluidas: 1.969 filas con 0.

## Duplicados

- venta: 0 filas idénticas; 45 sin id, item_id, store_id; 0 claves repetidas; 0 duplicados lógicos.
- Filas de la venta con los mismos días que otra: construcción 308, de ellas 306 sin ninguna venta; validación 87, de ellas 87 sin ninguna venta. Es evidencia, no un error.
- precios: 0 filas idénticas; 0 sin identificadores; 0 claves repetidas; 0 duplicados lógicos.
- calendario: 0 filas idénticas; 0 sin d, date; 0 claves repetidas; 0 duplicados lógicos.

## Claves y granularidad

- venta: una fila es un producto en una tienda, con una columna por día; clave id, única: sí. Discrepancia con la guía: ninguna en la clave; la granularidad producto-tienda-día está en forma ancha.
- precios: una fila es un producto en una tienda en una semana de Walmart, con su precio; clave store_id, item_id, wm_yr_wk, única: sí. Discrepancia con la guía: ninguna.
- calendario: una fila es un día; clave d, única: sí. Discrepancia con la guía: ninguna.

## Categóricas y texto

- Códigos fuera de las reglas, apartado 4: dept_id 0; cat_id 0; store_id 0; state_id 0.
- Valores con espacios por fuera: 0. Variantes de mayúsculas: 0.
- Los 30 nombres de evento mezclan estilos: 8 con espacios, 2 con apóstrofo, 1 con guion y 15 pegados con mayúsculas. Al normalizarlos no se junta ninguno.
- Categorías raras de calendario.event_name_1, del diccionario: 30. Quedan como están por D2, cerrada el 21/11/2026.
- Categorías raras de calendario.event_type_1, del diccionario: 2. Quedan como están por D2, cerrada el 21/11/2026.
- Categorías raras de calendario.event_name_2, del diccionario: 4. Quedan como están por D2, cerrada el 21/11/2026.
- Categorías raras de calendario.event_type_2, del diccionario: 2. Quedan como están por D2, cerrada el 21/11/2026.

## Numéricas y outliers

Los límites solo detectan: un atípico no es un error.

- venta, construcción: Q1 0, Q3 1 y mediana 0; rango intercuartílico 705.800; z robusto no se aplica, dispersión cero; los dos no se aplica, dispersión cero; de 6.050.000 valores.
- venta, validación: Q1 0, Q3 1 y mediana 0; rango intercuartílico 245.187; z robusto no se aplica, dispersión cero; los dos no se aplica, dispersión cero; de 1.825.000 valores.
- precios, hasta la semana 11416: Q1 2,18, Q3 5,94 y mediana 3,28; rango intercuartílico 25.957; z robusto 27.200; los dos 25.957; de 603.600 valores.
- precios, después de la semana 11416: Q1 2, Q3 5,97 y mediana 3,28; rango intercuartílico 11.766; z robusto 11.874; los dos 11.766; de 250.973 valores.
- Colas de venta en construcción: los más bajos 0, 1, 2, 3, 4, 5, 6, 7, 8, 9; los más altos 648, 427, 385, 300, 282, 272, 269, 265, 263, 262; mayor salto de 427 a 648.
- Colas de venta en validación: los más bajos 0, 1, 2, 3, 4, 5, 6, 7, 8, 9; los más altos 300, 288, 209, 207, 197, 179, 178, 171, 166, 165; mayor salto de 209 a 288.
- Colas de precios en hasta la semana 11416: los más bajos 0,05, 0,07, 0,08, 0,1, 0,13, 0,16, 0,2, 0,23, 0,25, 0,3; los más altos 29,97, 28,96, 28, 27,98, 27,97, 26,88, 25,97, 24,92, 23,62, 23; mayor salto de 23,62 a 24,92.
- Colas de precios en después de la semana 11416: los más bajos 0,01, 0,05, 0,07, 0,08, 0,1, 0,15, 0,2, 0,23, 0,25, 0,31; los más altos 34,18, 30,32, 29,97, 28,96, 27,98, 25,97, 20,77, 20,38, 19,98, 18,73; mayor salto de 20,77 a 25,97.
- Las colas, la escala y los atípicos de cada departamento están en el JSON, en `colas`, `escala` y `outliers`.

## Fechas

- calendario.date: del 2011-01-29 al 2016-06-19; convención año-mes-día, demostrada con 1.189 fechas de día mayor que 12.
- venta.d_1 a d_1575 (por su fecha en el calendario): del 2011-01-29 al 2015-05-22; convención la del calendario.
- precios.wm_yr_wk: del 11101 al 11516; convención código de semana de Walmart.
- El calendario sigue 394 días después de la fecha de referencia. No son de ningún periodo: se describen aparte y no se marcan como futuros.

## Reglas lógicas e integridad

- **R-1**, un día con cero unidades es un dato válido, no un vacío (§5): construcción 4.278.752 celdas a cero (70,72 %); validación 1.135.227 celdas a cero (62,2 %).
- **R-2**, un cierre es la tienda entera a cero (§5): 33 cierres; construcción 25, 24 en Navidad; validación 8, 8 en Navidad.
- **R-3**, una semana sin precio es una semana sin venta (§5): semanas con venta y sin precio hasta la semana 11416 0; después de la semana 11416 0; con precio y sin venta hasta la semana 11416 144.674; después de la semana 11416 61.810.
- **R-4**, el precio vale para los siete días de su semana: un precio por producto-tienda y semana (§5): 0 claves repetidas.
- **R-5**, una venta negativa sería imposible; si aparece, el trabajo para (§5): construcción 0 negativos; validación 0 negativos.
- **R-6**, un día sin evento es un día normal (§5): días con evento: construcción 99; validación 29; después de la fecha de referencia 34.
- **R-7**, el precio va de 0,5 a 50 dólares en casi todos los productos (§7, «Lo esperable»): 9.438 por debajo de 0,5 (hasta la semana 11416 6.674; después de la semana 11416 2.764); mínimo 0,01; 0 por encima de 50.

Lo que dejó el reconocimiento, medido en cada periodo:

- **Q-1**, los saltos de nivel (medida D1): construcción 28 series (7 bajadas), la mayor WI_1 FOODS_2 con 7,23 el 2012-10-26; tiendas con salto: WI_1; WI_2; validación 12 series (3 bajadas), la mayor TX_3 HOBBIES_2 con 3,1 el 2014-08-26; tiendas con salto: ninguna.
- **Q-2**, los días anteriores a la primera venta de cada producto-tienda: construcción 1.470.682 días de productos-tienda que empiezan a vender en ella, más 370.260 de 306 que aún no venden al acabarla; validación 45.505 días de productos-tienda que empiezan a vender en ella, más 19.710 de 54 que aún no venden al acabarla; 252 productos-tienda venden por primera vez en la validación.
- **Q-3**, los días de serie a cero fuera de los cierres: construcción 2.241 días, racha más larga de 25 en WI_1 HOBBIES_2; validación 215 días, racha más larga de 3 en CA_4 HOBBIES_2.
- **Q-4**, el cierre de WI_1 del 02/02/2011 sin evento: WI_1 el 2011-02-02, evento: ninguno.
- **Q-5**, las unidades del 25 de diciembre: 2011 6 unidades; 2012 4 unidades; 2013 9 unidades; 2014 3 unidades.
- **Q-6**, los productos-tienda que no venden nunca: construcción 306; validación 87; en ninguno de los dos 54, de ellos 53 sin ningún precio.
- **Q-7**, el precio que llega antes de la primera venta: de 4.946 productos-tienda con precio y venta, 4.920 venden de 0 a 6 días después del primer precio y 0 antes. De los que empiezan a vender después del primer día, tienen el precio de 0 a 6 días antes 3.483 de 3.502 en la construcción; 245 de 252 en la validación.

Riesgos para un modelo, solo señalados:

- precios.sell_price: el precio de la semana prevista dice si hubo venta: una semana sin precio es una semana sin venta (0 semanas con venta y sin precio). Los planteamientos fijan el precio de la semana anterior.
- venta.unidades: el objetivo es continuo y el desequilibrio de clases no aplica; los ceros pesan más en HOBBIES_2, con el 92,41 % de sus celdas a cero en la construcción.
- venta.item_id: categórica con 500 valores.
- venta.id: categórica con 5.000 valores, uno por fila.
- calendario.event_name_1: categórica con 30 valores.
- venta.id, cat_id, state_id: columnas que salen de otras: id del producto y la tienda; cat_id del departamento; state_id de la tienda.
- calendario.weekday, wday, month, year, d: columnas que salen de la fecha.
- precios.wm_yr_wk: la semana 11416 cruza de la construcción a la validación: su precio vale para días de los dos periodos.

## Cruces entre tablas

- venta con precios por item_id, store_id (1:N, relación supuesta): 53 claves de la izquierda sin pareja y 0 de la derecha; formato distinto: no.
- precios con calendario por wm_yr_wk (N:1 frente a las semanas del calendario, relación supuesta): 0 claves de la izquierda sin pareja y 57 de la derecha; formato distinto: no.
- venta (columnas de días) con calendario por d (1:1, relación supuesta): 0 claves de la izquierda sin pareja y 394 de la derecha; formato distinto: no.

## Reglas candidatas para aprobar

Las nueve viñetas del plan dan 17 reglas, cada una contada por separado. Son comprobaciones aprobadas con el plan (D3, 21/11/2026); pasarlas a las reglas de negocio va por la cascada.

- **RC-01** (venta: dept_id, cat_id). Dept_id empieza por cat_id. La incumplen 0 filas.
- **RC-02** (venta: item_id, dept_id). Item_id empieza por dept_id. La incumplen 0 filas.
- **RC-03** (venta: store_id, state_id). Store_id empieza por state_id. La incumplen 0 filas.
- **RC-04** (venta: id, item_id, store_id). Id es item_id, store_id y el sufijo evaluation, unidos por guion bajo. La incumplen 0 filas.
- **RC-05** (calendario: wday, weekday). Wday casa con weekday. La incumplen 0 días.
- **RC-06** (calendario: month, date). Month casa con date. La incumplen 0 días.
- **RC-07** (calendario: year, date). Year casa con date. La incumplen 0 días.
- **RC-08** (calendario: event_name_1, event_type_1). Event_type_1 está vacío si y solo si lo está event_name_1. La incumplen 0 días.
- **RC-09** (calendario: event_name_2, event_type_2). Event_type_2 está vacío si y solo si lo está event_name_2. La incumplen 0 días.
- **RC-10** (calendario: event_name_1, event_name_2). No hay segundo evento sin primero. La incumplen 0 días.
- **RC-11** (calendario: wm_yr_wk). La semana de Walmart tiene siete días. La incumplen 2 días.
- **RC-12** (calendario: wm_yr_wk, weekday). La semana de Walmart empieza en sábado. La incumplen 0 semanas.
- **RC-13** (calendario: event_name_1, event_type_1, event_name_2, event_type_2). Cada nombre de evento tiene siempre el mismo tipo. La incumplen 0 apariciones de evento.
- **RC-14** (precios: item_id, store_id, wm_yr_wk). Un producto-tienda con precio lo tiene todas las semanas entre la primera y la última, sin huecos. La incumplen 0 semanas que faltan.
- **RC-15** (precios: item_id, store_id, wm_yr_wk). Un producto-tienda con precio lo tiene hasta la última semana, la 11516. La incumplen 0 productos-tienda.
- **RC-16** (precios: sell_price, wm_yr_wk). El precio de un producto-tienda no pasa de más del doble de una semana a la siguiente. La incumplen 350 semanas.
- **RC-17** (calendario: snap_CA, snap_TX, snap_WI, date). El SNAP sigue una regla fija por día del mes en cada estado. La incumplen 0 días.

## Resumen de problemas detectados

- **C-01** (3.2, venta.d_1 a d_1575): 1.575 columnas, una por día. Forma no tabular: los días están repartidos en columnas.
- **C-02** (3.2, venta.id): 5.000 de 5.000 filas son item_id, store_id y el sufijo evaluation. Columna doble: repite el producto y la tienda.
- **C-03** (3.2, calendario.snap_CA, snap_TX, snap_WI): 3 nombres con mayúsculas; 0 colisiones al normalizar. Nombres que no siguen la forma normalizada.
- **C-04** (3.3, calendario.date): texto en año-mes-día; 0 fechas no se leen con ese formato. La fecha llega como texto.
- **C-05** (3.4, calendario.event_name_1): 1.807 vacíos de 1.969 días (91,77 %); 30 categorías raras. El vacío es «sin evento» (reglas, apartado 5); las categorías raras quedan como están por D2, cerrada el 21/11/2026.
- **C-06** (3.4, calendario.event_type_1): 1.807 vacíos de 1.969 días (91,77 %); 2 categorías raras. El vacío es «sin evento» (reglas, apartado 5); las categorías raras quedan como están por D2, cerrada el 21/11/2026.
- **C-07** (3.4, calendario.event_name_2): 1.964 vacíos de 1.969 días (99,75 %); 4 categorías raras. El vacío es «sin evento» (reglas, apartado 5); las categorías raras quedan como están por D2, cerrada el 21/11/2026.
- **C-08** (3.4, calendario.event_type_2): 1.964 vacíos de 1.969 días (99,75 %); 2 categorías raras. El vacío es «sin evento» (reglas, apartado 5); las categorías raras quedan como están por D2, cerrada el 21/11/2026.
- **C-09** (3.4, precios.sell_price (semana sin fila)): 270.427 de 1.125.000 semanas producto-tienda sin precio (24,04 %): 258.502 antes del primer precio, 0 en huecos y 11.925 en los 53 productos-tienda sin ningún precio. Veredicto del reparto: repartidos; la guía y las reglas, apartado 5 la documentan como semana sin venta.
- **C-10** (3.4, venta.unidades): 4.278.752 de 6.050.000 celdas a cero (70,72 %) en la construcción. Dato válido (reglas, apartado 5); por su peso en el extremo del rango sería un código numérico candidato.
- **C-11** (3.4, venta.unidades): 1.135.227 de 1.825.000 celdas a cero (62,2 %) en la validación. Dato válido (reglas, apartado 5); por su peso en el extremo del rango sería un código numérico candidato.
- **C-12** (3.10, precios.sell_price): 9.438 precios por debajo de 0,5 dólares: 6.674 hasta la semana 11416 y 2.764 después; mínimo 0,01. Fuera del rango de «Lo esperable» (reglas, apartado 7); 50 productos-tienda los tienen en todas sus semanas.
- **C-13** (3.10, precios.sell_price): 350 subidas de más del doble de una semana a la siguiente, en 215 productos-tienda. «Lo esperable» (reglas, apartado 7) lo señala como sospechoso.
- **C-14** (3.10, venta.unidades): 33 cierres: 25 en la construcción y 8 en la validación; fuera del 25 de diciembre, WI_1 el 2011-02-02 sin evento. «Lo esperable» (reglas, apartado 7): un cierre en una sola tienda sin causa hace sospechar.
- **C-15** (3.10, venta.unidades): unidades del 25 de diciembre, las 5.000 series sumadas: 2011, 6; 2012, 4; 2013, 9; 2014, 3. En 32 de los 40 días de tienda del 25 de diciembre (10 tiendas en 4 años) la tienda entera vende cero, que es un cierre según las reglas, apartado 5. Las unidades se venden en los otros 8 días de tienda.
- **C-16** (3.10, venta.unidades por serie): 28 de 70 series con salto de nivel en la construcción, 7 de ellos bajadas; el mayor, WI_1 FOODS_2, 7,23 veces el 2012-10-26; tiendas con salto: WI_1 (1,87 veces el 2012-10-26); WI_2 (1,76 veces el 2012-05-31). Medido con D1, cerrada el 21/11/2026; «Lo esperable» (reglas, apartado 7) señala un salto duradero sin festivo, que puede ser un producto que empieza a venderse.
- **C-17** (3.10, venta.unidades por serie): 12 de 70 series con salto de nivel en la validación, 3 de ellos bajadas; el mayor, TX_3 HOBBIES_2, 3,1 veces el 2014-08-26; tiendas con salto: ninguna. Medido con D1, cerrada el 21/11/2026; «Lo esperable» (reglas, apartado 7) señala un salto duradero sin festivo, que puede ser un producto que empieza a venderse.
- **C-18** (3.10, venta.unidades por serie): días de serie a cero fuera de los cierres: construcción 2.241, con la racha más larga de 25 días en WI_1 HOBBIES_2; validación 215, con la racha más larga de 3 días en CA_4 HOBBIES_2. HOBBIES_2 tiene 2.177 de los de la construcción.
- **C-19** (3.10, venta.unidades): días producto-tienda a cero antes de la primera venta: construcción 1.470.682 de los que empiezan a vender en ella, más 370.260 de los 306 que aún no venden al acabarla; validación 45.505 de los que empiezan a vender en ella, más 19.710 de los 54 que aún no venden al acabarla; 252 productos-tienda venden por primera vez en la validación. Suman cero a su departamento sin que cambie la demanda (reglas, apartado 3).
- **C-20** (3.10, venta.unidades): productos-tienda sin ninguna venta: 306 en la construcción; 87 en la validación; 54 en ninguno de los dos, 53 de ellos sin ningún precio. Suman cero a su departamento.
- **C-21** (3.10, precios.sell_price): 206.484 semanas producto-tienda con precio y sin venta. Descripción: el precio no dice que hubo venta.
- **C-22** (3.9, calendario.wm_yr_wk): la semana 11416 tiene 6 días en la construcción y 1 en la validación. Su precio vale para días de los dos periodos.
- **C-23** (3.9, calendario.date): 394 días después de la fecha de referencia. A propósito (reglas, apartado 5); no son de ningún periodo.
- **C-24** (3.10, calendario.wm_yr_wk): semanas incompletas: la 11621, con 2 días. La última semana del calendario acaba con el fichero.
- **C-25** (3.8, venta.unidades (d_1 a d_1575)): construcción: rango intercuartílico 705.800; z robusto no se aplica, dispersión cero; los dos no se aplica, dispersión cero; de 6.050.000 valores. Un atípico no es un error; los límites solo detectan.
- **C-26** (3.8, venta.unidades (d_1 a d_1575)): validación: rango intercuartílico 245.187; z robusto no se aplica, dispersión cero; los dos no se aplica, dispersión cero; de 1.825.000 valores. Un atípico no es un error; los límites solo detectan.
- **C-27** (3.8, precios.sell_price): hasta la semana 11416: rango intercuartílico 25.957; z robusto 27.200; los dos 25.957; de 603.600 valores. Un atípico no es un error; los límites solo detectan.
- **C-28** (3.8, precios.sell_price): después de la semana 11416: rango intercuartílico 11.766; z robusto 11.874; los dos 11.766; de 250.973 valores. Un atípico no es un error; los límites solo detectan.
- **C-29** (3.11, venta.item_id, store_id): 53 productos-tienda de la venta sin ningún precio; 0 pares de los precios sin venta. Arrastran 0 unidades.

## Posibles acciones

Ninguna se ejecuta en esta fase.

- C-01: pasar a una fila por producto-tienda-día al transformar.
- C-02: no usarla como variable; la clave es item_id con store_id.
- C-03: normalizar el nombre en la corrección.
- C-04: leerla como fecha con su formato.
- C-05: cómo se leen se decide en las reglas de transformación (D2).
- C-06: cómo se leen se decide en las reglas de transformación (D2).
- C-07: cómo se leen se decide en las reglas de transformación (D2).
- C-08: cómo se leen se decide en las reglas de transformación (D2).
- C-09: ninguna en la calidad; el dólar se calcula solo donde hay precio.
- C-10: ninguna: no es un vacío.
- C-11: ninguna: no es un vacío.
- C-12: preguntar, nunca quitar.
- C-13: preguntar, nunca quitar.
- C-14: preguntar.
- C-15: preguntar; el 25 de diciembre ya queda fuera del error (reglas, apartado 6).
- C-16: medir en la corrección si cambia alguna respuesta.
- C-17: medir en la corrección si cambia alguna respuesta.
- C-18: clasificarlos en la limpieza con la tabla de clases (reglas, apartado 5).
- C-19: medir en la corrección si cambia alguna respuesta.
- C-20: medir si quitarlos cambia alguna respuesta.
- C-22: tenerlo en cuenta al cortar por periodo.
- C-25: ninguna en la calidad.
- C-26: ninguna en la calidad.
- C-27: ninguna en la calidad.
- C-28: ninguna en la calidad.
- C-29: ninguna: no venden.
- PC-01, para la persona responsable: 9.438 precios quedan por debajo de 0,5 dólares, fuera de «Lo esperable». ¿Cómo se leen? Lecturas: (1) son precios reales de productos baratos y se usan como están; (2) son errores del dato y no se usan para calcular dólares. Después, la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»).
- PC-02, para la persona responsable: En 350 semanas el precio pasa a más del doble que la semana anterior. ¿Cómo se leen? Lecturas: (1) son cambios reales de precio y se usan como están; (2) son errores del dato y esas semanas no se usan para calcular dólares. Después, la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»).
- PC-03, para la persona responsable: Fuera del 25 de diciembre hay 1 cierre de tienda: WI_1 el 2011-02-02, sin evento. ¿Cómo se lee? Lecturas: (1) es un cierre real de la tienda y se trata como el 25 de diciembre; (2) es un día sin dato y se trata como vacío. Después, la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»).
- PC-04, para la persona responsable: El 25 de diciembre suma 22 unidades en 4 años. Esas unidades se venden en 8 de los 40 días de tienda de esa fecha (10 tiendas en 4 años); en los otros 32, la tienda entera vende cero. ¿Cómo se leen las unidades del 25 de diciembre? Lecturas: (1) se dejan como vendidas; (2) se leen como cierre, con la venta a cero. Después, la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»).
- PC-05, para la persona responsable: En la construcción, 28 series tienen un salto de nivel. ¿Cómo se leen? Lecturas: (1) son cambios reales de la venta y la serie se usa entera; (2) la historia anterior al salto no representa la serie y se marca. Después, la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»).
- PC-06, para la persona responsable: En la validación, 12 series tienen un salto de nivel. ¿Cómo se leen? Lecturas: (1) son cambios reales de la venta y la serie se usa entera; (2) la historia anterior al salto no representa la serie y se marca. Después, la corrección mide si cambia alguna respuesta (EQUIPO.md, «Datos que no sirven o están mal»).

Las cuestiones pendientes no eligen ninguna lectura: las decide la persona responsable.

## Parámetros usados

- límite del rango intercuartílico: 1,5 (por defecto).
- límite del z robusto: 3,5 (por defecto).
- segmento mínimo para el reparto de nulos: 30 (por defecto).
- concentración de nulos en un segmento: 2 (por defecto: el doble del porcentaje global).
- categoría rara: menos del 2,5 % de las filas o menos de 5 apariciones (por defecto, el mismo del diccionario).
- código de ausencia numérico candidato: 5 (por defecto: un valor en un extremo del rango con ese porcentaje de las filas o más).
- colas de cada magnitud: 10 (por defecto; por departamento y periodo, a petición de la petición).
- fecha de Excel candidata: 20.000, 60.000 (por defecto; no aplica en este caso).
- horizonte de fechas futuras: 2015-05-22 (reglas de negocio §5, fecha de referencia, para la venta y los precios).
- horizonte del calendario: 2016-06-19 (reglas de negocio §5: llega hasta ahí a propósito; sus días posteriores no se marcan como futuros).
- dimensiones del reparto: periodo, tienda, estado, departamento, categoria (plan aprobado, apartado 3).
- rango del precio: 0,5, 50 (reglas de negocio §7, «Lo esperable»).
- subida de precio sospechosa: 2 (reglas de negocio §7, «Lo esperable»: un salto de más del doble de una semana a otra).
- constante del z robusto: 0,6745 (convención del z robusto modificado de Iglewicz y Hoaglin; el método fija solo el límite).
- ventana de los saltos de nivel: 91 (D1, cerrada como criterio técnico el 21/11/2026: la del reconocimiento, celda 57).
- días con dato en cada ventana: 80 (D1, cerrada el 21/11/2026).
- razón de un salto de nivel: 1,5 (D1, cerrada el 21/11/2026: después entre antes de 1,5 o más, o de 1 entre 1,5 o menos).
- D1, la medida de los saltos de nivel: cerrada el 2026-11-21.
- D2, los nombres y los tipos de evento con pocos días (P-01 a P-04 del diccionario): cerrada el 2026-11-21.
- D3, las reglas candidatas del apartado 7 del plan: cerrada el 2026-11-21.
- Teoría del manual aplicada: 7.1, 7.2 y 33.1, el orden del diagnóstico: muestra, visión global, nulos, duplicados, valores únicos y estadísticos; 7.3, nulos por columna, por fila y códigos de ausencia, con su reparto; 7.4, duplicados exactos, sin identificadores y casi duplicados; 7.5 y 33.10, valores únicos y categorías raras, solo como diagnóstico; 7.6, 33.9 y 33.11, escala, colas, rango intercuartílico y z robusto con la mediana y la desviación absoluta mediana; un atípico no es un error; 14.13 y 14.15, fechas leídas con su formato y días que faltan en la serie; 7.8 y 7.9, lo que el diagnóstico automático no ve: tiempo, cruces y negocio.

## Datos personales

No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección. Las reglas de negocio §9 dicen que los datos son de productos, tiendas, precios y calendario; no traen nada de personas. El diccionario buscó valores con forma de dato personal en cada columna de texto y los encontró en 0 columnas. Este método no usa ni deja ninguna columna de datos personales.

## Límites de esta revisión

- Se revisaron tres relaciones: venta y precios por producto y tienda; precios y calendario por la semana; venta y calendario por el día.
- Los vacíos de los eventos se segmentaron solo por periodo, la única dimensión del calendario. La semana sin precio se segmentó por periodo, tienda, estado, departamento y categoría. Un segmento no revisado puede esconder una concentración.
- En los eventos el doble del porcentaje global pasa del 100 %: ningún segmento puede llegar a él y el veredicto «repartidos» sale por construcción.
- Las cifras de la validación describen y no se cruzan con el precio, los eventos ni el SNAP, salvo las comprobaciones de las reglas que lo piden.
- Las cifras del diccionario no se recalculan: filas, columnas, tipos, vacíos, distintos, categorías raras y relaciones dentro de cada tabla.
- La prueba final no está en el caso y nada de este diagnóstico la mira.
- No se aplicó la búsqueda de fechas de Excel (comprobaciones.md §6): ninguna columna de fecha está guardada como número.
- No se aplicó la búsqueda de instrucciones dentro del texto (bloque 3.7): ninguna columna es texto libre.
- No se aplicó el control de clases desbalanceadas (comprobaciones.md §2): el objetivo es continuo.
- No se aplicó el z robusto donde la desviación absoluta mediana es cero: dispersión cero en 16 grupos (venta total construcción; venta total validación; venta FOODS_1 construcción; venta FOODS_1 validación; venta FOODS_2 construcción; venta FOODS_2 validación; venta FOODS_3 construcción; venta FOODS_3 validación; venta HOBBIES_1 construcción; venta HOBBIES_1 validación; venta HOBBIES_2 construcción; venta HOBBIES_2 validación; venta HOUSEHOLD_1 construcción; venta HOUSEHOLD_1 validación; venta HOUSEHOLD_2 construcción; venta HOUSEHOLD_2 validación).
- No se aplicó el rango intercuartílico donde Q1 y Q3 son iguales: dispersión cero en 4 grupos (venta HOBBIES_2 construcción; venta HOBBIES_2 validación; venta HOUSEHOLD_2 construcción; venta HOUSEHOLD_2 validación).
- No se aplicó el factor de una escala perdida: ninguna magnitud tiene un hueco en su número de cifras.
- No se aplicó nada de la prueba final: no está en el caso (reglas, apartado 5).
