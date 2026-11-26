---
titulo: Modelo de datos del caso 69 · la venta diaria de cada departamento en cada tienda, en unidades y en dólares, con sus dos dimensiones y su Calendario
estado: aprobado por el responsable del caso el 24/11/2026; comprobado con `scripts/04_modelado_datos.py` (informes/modelado-datos.json, estado OK), que construye el Calendario
fecha_documento: 2026-11-24
dueno: el responsable del caso (decide) · el equipo de análisis (redacta)
fuentes: `../negocio/01_ficha_del_caso.md`; `../negocio/reglas-negocio.md` (§3 a §7, con el cambio del 24/11/2026); `../metodo/04_planteamientos.md`; `../fuentes/diccionario-datos-origen.json`; `../fuentes/02_datos_necesarios.md`; `registro-transformaciones.md`; `decisiones-correccion.json`; `../../informes/correccion-datos.json`; `../../informes/calidad-datos.json` (sus cruces)
---

# Modelo de datos · caso 69

El modelo tiene una tabla de hechos, la de series, con una fila por departamento, tienda y día. Lleva la venta en
unidades y en dólares. A su lado van el Calendario y dos dimensiones: la de producto y la de tienda. Las tres tablas
corregidas cumplen lo que el diseño afirma de ellas: el script no encontró ninguna contradicción. El responsable del caso lo aprobó el
24/11/2026; el Calendario ya está construido y las otras tres tablas las construye la transformación.

## 1. Fuentes consultadas

- La ficha del caso: las cuatro preguntas, los KPIs y la cifra que mide valor.
- Las reglas de negocio, §3 a §7, con el cambio de §5 del 24/11/2026 (D8, D9 y el 25 de diciembre).
- Los planteamientos: lo que queda por fijar antes de entrenar.
- El diccionario del origen, los datos necesarios y la guía del concurso que citan.
- El registro de transformaciones, el fichero de decisiones de la corrección y los JSON de corrección y de calidad.
- Las tres tablas de `data/processed/`, leídas por el script con las columnas que nombra el diseño.

## 2. Preguntas y lo que necesitan

Las cuatro preguntas se miden en la misma fila: un departamento en una tienda un día.

- **Pregunta 1**, cuántas unidades y dólares venderá cada departamento en cada tienda cada día. Mide la venta en unidades
  y en dólares (reglas, apartado 5). Se reparte por tienda y departamento. La fecha es el día de la venta.
- **Pregunta 2**, si se equivoca menos que las tres reglas sin modelo. Mide el error y la ventaja con los mismos días,
  series y horizonte que el modelo (reglas, apartado 7). Se reparte por corte, con su origen.
- **Pregunta 3**, cuánto venderá cada tienda y cada categoría al sumar. Suma las previsiones de la pregunta 1 por tienda,
  categoría, estado y cadena (reglas, apartado 4, «Cómo cuadran los niveles»). Necesita la categoría de cada departamento y el
  estado de cada tienda.
- **Pregunta 4**, qué días cambia la venta de lo habitual. Mide el efecto de festivos, días SNAP, día de la semana, época
  del año y precio. Necesita del Calendario los eventos, el SNAP del estado de la tienda, el día de la semana y el mes;
  de los precios, el precio medio del departamento por semana.

Las cuatro se contestan con las tablas que hay (ficha, «Si cada pregunta se puede contestar»).

### Cada pregunta de punta a punta

Lo entrecomillado está copiado de la ficha, de las reglas o de los planteamientos.

| Pregunta | Cifra final | Fórmula | Estadístico | Población | Exclusiones | Mínimo |
|---|---|---|---|---|---|---|
| 1 · Cuántas unidades y dólares venderá cada departamento en cada tienda cada día | «dos previsiones por separado, una en unidades y otra en dólares» por serie y día del horizonte: «unidades: 10 días», «dólares: 28 días» (reglas, apartado 5); se miden con el error | error: «suma de las diferencias entre lo previsto y lo real, sin signo, entre la suma de lo real, por 100»; en dólares, «la misma cuenta sobre la previsión en dólares» (reglas, apartado 6) | ratio de sumas: «se calcula sobre todos los días y series del periodo que se mide, no como media de errores de cada día»; «el error que decide es uno solo, el de las 70 series juntas» (reglas, apartado 6) | «las 70 series, con todos sus días del periodo que se mide» (reglas, apartado 7) | el 25 de diciembre «queda fuera del error del modelo y de las tres reglas» (reglas, apartado 6); el cierre de WI_1 del 02/02/2011, como un 25 de diciembre (reglas, apartado 5); «los primeros días de cada serie que no tienen la historia que piden las variables» (reglas, apartado 7) | número de orígenes: por fijar en los planteamientos |
| 2 · Si se equivoca menos que las tres reglas sin modelo | el veredicto en unidades y en dólares, «cada uno por su lado»: gana, o «mejor de media pero no demostrado» si cumple solo la primera condición (reglas, apartado 7) | «se equivoca menos en al menos el 75 % de los orígenes de previsión, redondeando hacia arriba» y «el intervalo del 95 % de la ventaja […] queda entero por encima de cero» (reglas, apartado 7) | recuento de orígenes ganados frente a la regla que menos falla en cada corte e intervalo del 95 % de la ventaja; cómo se calcula el intervalo: por fijar en los planteamientos | las 70 series juntas; «Dónde se decide: en la validación. La prueba final lo confirma una sola vez» (reglas, apartado 7) | las de la pregunta 1 | «con 10 orígenes hacen falta 8» (reglas, apartado 7); número de orígenes: por fijar en los planteamientos |
| 3 · Cuánto venderá cada tienda y cada categoría al sumar | la previsión de tienda, categoría en una tienda, categoría en la cadena, estado y cadena, en unidades y en dólares | «la suma de las previsiones de sus departamentos en sus tiendas: se reconcilia de abajo arriba» (reglas, apartado 4) | suma | «la suma de las previsiones de sus departamentos» (reglas, apartado 7) | «nada más» (reglas, apartado 7) | no decide: «El veredicto principal es el de las 70 series juntas. El de cada tienda se da para leer» (reglas, apartado 7) |
| 4 · Qué días cambia la venta de lo habitual | el efecto de «festivos, días SNAP, día de la semana, época del año y precio sobre la venta, como variables del modelo»; el precio, «solo de forma descriptiva» (ficha) | por fijar en los planteamientos: «con qué fórmula y frente a qué día normal se mide el efecto» | por fijar en los planteamientos, con la fórmula | para describir, «las 70 series en construcción» (reglas, apartado 7, «Reconocimiento y exploración»); como variable, la de la pregunta 1 | al describir, «validación y prueba final» (reglas, apartado 7) | falta: decisión de método, en «Observaciones y pendientes» |
| Sesgo (KPI) | «lo que la previsión se pasa o se queda corta de media, en unidades o en dólares por cada 100 vendidos, cada previsión con el suyo, con signo» (ficha) | «la misma cuenta con signo: positivo si la previsión se pasa, negativo si se queda corta» (reglas, apartado 6) | ratio de sumas con signo, sobre los mismos días y series que el error | la del error | las del error | sin veredicto propio: «Va siempre al lado del error» (reglas, apartado 6) |
| Ventaja frente a las reglas (KPI) | «error de la regla que menos falla en cada corte menos error del modelo, con su intervalo» (ficha) | la misma resta en cada corte; se decide con «Qué cuenta como mejora» (reglas, apartado 7) | diferencia de errores por corte e intervalo del 95 %; cómo se calcula el intervalo: por fijar en los planteamientos | las 70 series juntas, en la validación (reglas, apartado 7) | las de la pregunta 1 | «al menos el 75 % de los orígenes» (reglas, apartado 7); número de orígenes: por fijar en los planteamientos |
| Cifra que mide valor | «Error de la previsión en dólares, por departamento y tienda, cada mes, frente al de la regla que menos falla en cada corte», con el sesgo al lado; vigilan «el sesgo de cada departamento y tienda» y «el error de los días de festivo y de los días SNAP» (ficha) | el error en dólares (reglas, apartado 6); festivos y SNAP son «dos cifras separadas: el error de los días con algún evento del calendario y el de los días SNAP del estado de cada tienda» (reglas, apartado 7) | ratio de sumas por mes; «cómo se arma el error de cada mes de la cifra que mide valor, si los cortes van por días y no por meses»: por fijar en los planteamientos | cada departamento en cada tienda (ficha) | el 25 de diciembre (reglas, apartado 6); un mes «sin todos sus días es parcial y no se compara con uno completo» (reglas, apartado 5) | el veredicto es el de las 70 series juntas; en cada departamento, «si […] el modelo falla de media más que la regla que menos falla, el informe recomienda esa regla» (reglas, apartado 7) |

### Registro de exclusiones

Los recuentos salen del script, en `exclusiones` del JSON.

| Qué sale | De qué cálculo | Recuento | Cómo se trata y por qué | Se puede recuperar |
|---|---|---|---|---|
| Los días de serie del 25 de diciembre | el error, el sesgo y la ventaja del modelo y de las tres reglas (reglas, apartado 6) | 210 días de serie en la construcción; 70 en la validación | se quedan en la tabla de series con su venta: se sabe de antemano que la tienda cierra | sí: no salen de la tabla |
| El cierre de WI_1 el 02/02/2011 | el error, como un 25 de diciembre (reglas, apartado 5; PC-03) | 7 días de serie en la construcción | se queda en la tabla de series a cero: es un cierre real de la tienda | sí: no sale de la tabla |
| Los productos-tienda sin ningún precio | ninguno: suman cero a su departamento (reglas, apartado 3) | 53 productos-tienda, con 0 unidades | se quedan en la venta en filas; su venta en dólares es cero | no hace falta: no salen |
| Los días del calendario sin venta | la tabla de series | 394 días | se quedan en el Calendario sin periodo: la previsión en producción necesita los días que prevé | con la prueba final, que copia la persona responsable |
| Los primeros días de cada serie sin la historia que piden las variables | la previsión y la comparación con las reglas (reglas, apartado 7) | pendiente del paso 5, cuando se fijen las variables | se cuentan en el registro de transformaciones | no: no hay datos antes del 29/01/2011 |

## 3. Tablas

### Las tres tablas de entrada

| Tabla | Grano | Clave del grano | Tipo | Medidas y atributos |
|---|---|---|---|---|
| venta (`venta_corregido.parquet`) | una fila por producto y tienda, con las unidades de cada día en 1.575 columnas (d_1 a d_1575); el grano del hecho es producto, tienda y día; la transformación lo pasa a filas | (item_id, store_id); `id` también es único, repite producto y tienda con un sufijo y el modelo no lo usa (C-02) | hechos | unidades de cada día; dept_id, cat_id y state_id dan los atributos de las dimensiones |
| precios (`precios_corregido.parquet`) | una fila por producto, tienda y semana de Walmart | (store_id, item_id, wm_yr_wk) | hechos: un nivel por semana, que no se suma | sell_price |
| calendario (`calendario_corregido.parquet`) | una fila por día | d; date también es única | dimensión | fecha, semana, día de la semana, mes, año, eventos y SNAP de cada estado |

El script comprobó las tres claves: 0 filas repetidas en cada una, con `id` y `date` únicas.

### Las cuatro tablas del modelo

El Calendario lo construye `scripts/04_modelado_datos.py` (`data/processed/calendario.parquet`, registro de
transformaciones T-003). Las otras tres las construye la transformación con el diseño aprobado.

- **dim_producto**, una fila por producto, clave `item_id`. Atributos: departamento (`dept_id`) y categoría (`cat_id`),
  de la venta (reglas, apartado 4). Son 500 productos, cada uno con un solo departamento y una sola categoría.
- **dim_tienda**, una fila por tienda, clave `store_id`. Atributo: estado (`state_id`), de la venta (reglas, apartado 4). Son 10
  tiendas, cada una con un solo estado.
- **Calendario**, una fila por día, clave `d`. Sus columnas están en el apartado 6.
- **hechos_series**, una fila por serie y día, clave (`store_id`, `dept_id`, `d`): 70 series por 1.575 días. Lleva
  `cat_id`, la venta en unidades y la venta en dólares, con su definición de las reglas, apartado 5:
  - venta en unidades: «la suma de las unidades vendidas ese día de sus productos del recorte»;
  - venta en dólares: «la suma, producto a producto, de las unidades vendidas por el precio de ese producto en esa
    tienda esa semana».

Es la tabla de las preguntas 1, 2 y 4. La pregunta 3 suma sus previsiones por tienda, categoría, estado y cadena.

En las diez tiendas cada departamento tiene los mismos productos: FOODS_1 43, FOODS_2 61, FOODS_3 129, HOBBIES_1 73,
HOBBIES_2 27, HOUSEHOLD_1 93 y HOUSEHOLD_2 74.

### La serie es la clave de la tabla de series

La serie, el departamento en una tienda (reglas, apartado 3), es la clave de `hechos_series` y no una dimensión. No tiene
atributos propios: su estado es el de su tienda, que da `dim_tienda`; su categoría, la de su departamento. Una
`dim_serie` repetiría los dos. La categoría viaja en la propia tabla de series. Se toma al sumar los productos, porque
`dim_producto` va por producto y unir la tabla de series con ella por el departamento repetiría cada fila tantas veces
como productos tiene.

### Qué es cada cero de la tabla de series

Las reglas, apartado 5 (D8) reparten los días a cero de las 70 series en cuatro clases, en este orden. Todos son ceros válidos y
se quedan en la tabla:

- «**cierre de la tienda,** 175 y 56: es un dato válido y entra como variable de calendario o de evento»;
- «**25 de diciembre sin cierre de la tienda,** 35 y 12: queda fuera del error, como el día entero (§6)»;
- «**demanda intermitente,** 2.171 y 201: son las 10 series de HOBBIES_2, con menos de 10 unidades de media al día. Son
  ceros válidos; cómo entran al modelo se fija en el paso 5 con la guía (§3)»;
- «**resto,** 35 y 2: cuatro series de más de 14 unidades de media al día, con el departamento entero a cero y la tienda
  abierta […] se quedan como ceros válidos».

Las dos cifras de cada clase son días de serie en la construcción y en la validación. Los días antes de la primera venta
de un producto suman cero a su departamento (reglas, apartado 3): tampoco salen.

## 4. Relaciones

Ninguna cardinalidad sale de los datos. Sale de las reglas y de la guía del concurso que citan. El script mide que las
claves tienen el mismo tipo a los dos lados: lo tienen en las siete relaciones.

| Desde | Hacia | Clave a cada lado | Maestro | Cardinalidad | De dónde sale |
|---|---|---|---|---|---|
| venta en filas | Calendario | d → d | Calendario | N:1 | guía del concurso (d_1 … d_n son los días; d_1 es el 29/01/2011); reglas, apartado 5, cada venta es del día natural de la tienda |
| venta en filas | precios | (item_id, store_id, wm_yr_wk del día) → (item_id, store_id, wm_yr_wk) | precios | N:1, los siete días de una semana a su precio | reglas, apartado 5: el precio es el de un producto en una tienda durante una semana de Walmart y vale para sus siete días; definición de la venta en dólares |
| venta en filas | dim_producto | item_id → item_id | dim_producto | N:1 | reglas, apartado 3 (dos productos son distintos por su código) y §4 |
| precios | dim_producto | item_id → item_id | dim_producto | N:1 | reglas, apartado 4; ficha, pregunta 4 |
| hechos_series | dim_tienda | store_id → store_id | dim_tienda | N:1 | reglas, apartado 3 (dos tiendas son distintas por su código y pertenecen a un estado) y §4 |
| hechos_series | Calendario | d → d | Calendario | N:1 | reglas, apartado 3 (la serie es diaria) y §5 |
| hechos_series | precio medio del departamento por semana | (store_id, dept_id, wm_yr_wk_anterior) → (store_id, dept_id, wm_yr_wk) | precio medio | N:1 | reglas, apartado 5, D9; ficha, pregunta 4 |

Claves sin pareja que las reglas ya resuelven:

- Una semana sin precio es una semana sin venta (reglas, apartado 5, guía del concurso). Son 1.892.989 días de producto-tienda,
  todos con cero unidades, que suman cero dólares. Un día con venta y sin precio pararía el trabajo (reglas, apartado 5): hay 0.
- Los 53 productos-tienda sin ningún precio no venden ningún día. Ningún precio queda sin su producto-tienda.
- Las 57 semanas del calendario sin precio son las de los 394 días posteriores a la fecha de referencia.

Los precios no se unen al Calendario por la semana: la semana se repite siete veces en el Calendario. La semana de cada
día sale del Calendario y con ella se busca el precio.

## 5. Hechos con grano distinto

Hay dos tablas de hechos con grano distinto: la venta va por producto, tienda y día; los precios, por producto, tienda
y semana. Se unen fila a fila en un solo caso, el que fija la definición de la venta en dólares (reglas, apartado 5). El precio se
une a la venta de cada día por producto, tienda y semana, con la semana del día sacada del Calendario. El precio no se
suma: se multiplica por las unidades de cada día de su semana.

El precio medio del departamento de la semana anterior se une también a cada día de la serie, por D9 (reglas, apartado 5). Es un
nivel y nunca se suma. Es la media simple de sus productos (planteamientos; el responsable del caso, 24/11/2026), contando solo los que
ya tenían precio cuatro semanas antes (reglas, apartado 5; el responsable del caso, 24/11/2026).

Fuera de eso, ningún par de hechos de grano distinto se une fila a fila.

## 6. Fechas y calendario

### El Calendario

Va por días, con las 1.969 filas de `calendario_corregido.parquet`, del 29/01/2011 al 19/06/2016, sin ningún día que
falte. No lleva fechas fijas en el código, porque en producción cada previsión necesita el calendario de los días que
prevé, hasta 28 por delante (reglas, apartado 5, «Lo que se sabe el día de prever» y «El horizonte»). Se construyó el
24/11/2026, con el diseño aprobado (método, apartado 9), en `data/processed/calendario.parquet`.

| Columna | Qué es | De dónde sale |
|---|---|---|
| d, date | el día y su fecha | calendario |
| year, month | año y mes | calendario |
| weekday, wday | día de la semana, empezando por el sábado | calendario |
| wm_yr_wk | semana de Walmart, de sábado a viernes | calendario |
| wm_yr_wk_anterior | la semana anterior, por el orden de las fechas | orden de las semanas del calendario |
| event_name_1, event_type_1, event_name_2, event_type_2 | hasta dos eventos con su tipo; el vacío es «sin evento» (D2) | calendario |
| snap_ca, snap_tx, snap_wi | SNAP de cada estado | calendario |
| periodo | construcción del 29/01/2011 al 22/05/2014; validación del 23/05/2014 al 22/05/2015; los días posteriores no son de ningún periodo | reglas, apartado 5 |
| mes_parcial, semana_parcial | el mes o la semana no tiene todos sus días dentro de su periodo | reglas, apartado 5 |

Cada hecho se une con su fecha:

- la venta, por `d`: d_1 es el sábado 29/01/2011 y d_1575 el viernes 22/05/2015;
- el precio, por `wm_yr_wk`: la venta trae 225 semanas, de la 11101 a la 11516, todas de siete días; los precios traen
  las mismas 225.

**La semana 11416 cruza los dos periodos.** El 22/05/2014, último día de la construcción, es jueves de la semana 11416.
Esa semana tiene 6 días en la construcción y 1 en la validación, así que su precio vale para días de los dos periodos. El
periodo se corta por día, nunca por semana.

Los periodos parciales que marca el Calendario:

- construcción: los meses 2011-01 y 2014-05 y la semana 11416;
- validación: los meses 2014-05 y 2015-05 y la semana 11416;
- días sin periodo: los meses 2015-05 y 2016-06 y la semana 11621, que solo tiene 2 días en el calendario.

**La semana anterior se toma por orden.** El código de semana salta cinco veces al cambiar de año, por ejemplo de la
11152 a la 11201. Restar 1 al código daría una semana que no existe.

### Cada dato a la fecha

Para la tabla de series. La previsión de un día solo usa lo que se sabe la víspera (reglas, apartado 5).

| Dato | Tabla de origen | Fecha con que se corta | Valor que toma | Regla que lo define | Desde cuándo se conoce |
|---|---|---|---|---|---|
| Venta en unidades del día | venta | el día que se prevé | la suma de las unidades de los productos del departamento en la tienda ese día | reglas, apartado 5, la venta | al cerrar el día; es el objetivo de la previsión |
| Venta en dólares del día | venta, precios y Calendario | el día y su semana | la suma de unidades por el precio de esa semana | reglas, apartado 5, la venta | al cerrar el día; es el objetivo de la previsión |
| Historia de la venta | hechos_series | hasta el día anterior | la venta real hasta el origen; dentro del horizonte, lo previsto para los días anteriores | reglas, apartado 5, «Lo que se sabe el día de prever» y «El horizonte» (previsión recursiva) | la víspera |
| Precio de cada producto | precios | la semana anterior a la del día que se prevé | el precio de esa semana | reglas, apartado 5, D9 | se da por conocido también cuando esa semana cae dentro del horizonte |
| Precio medio del departamento | precios y dim_producto | la semana anterior | la media simple de los precios de sus productos con precio esa semana que ya lo tenían cuatro semanas antes | reglas, apartado 5, D9; ficha, pregunta 4; planteamientos (el responsable del caso, 24/11/2026) | como el precio |
| Precio de la semana que se prevé | precios | no entra | ninguno: una semana sin precio es una semana sin venta y diría qué productos se venden en ella | reglas, apartado 5, D9 | no se usa |
| Día de la semana, mes, año y semana | Calendario | el día que se prevé | los del calendario | reglas, apartado 5 | de antemano |
| Eventos | Calendario | el día que se prevé | hasta dos eventos con su tipo | reglas, apartado 5 | de antemano |
| SNAP | Calendario y dim_tienda | el día que se prevé | el SNAP del estado de la tienda | reglas, apartado 5 | de antemano |
| Periodo y marca de parcial | Calendario | el día que se prevé | los del apartado anterior | reglas, apartado 5 | de antemano |

## 7. Forma de entrega al análisis

**Tablas separadas:** `hechos_series`, `dim_producto`, `dim_tienda` y `Calendario`. Los cruces del plan llevan a la tabla
de series las columnas que piden las preguntas. Las dimensiones se entregan para sumar las previsiones por nivel en la
pregunta 3 y para cuadrar los totales de tienda y de categoría. `dim_producto` solo la usa la transformación en los
cruces 3 y 6; se entrega porque son 500 filas y sirve para rehacer el total de cada categoría.

**`integracion-datos` no tiene nada que cruzar antes de la transformación.** Todos los cruces parten de la venta en
filas o de la tabla de series, que solo existen cuando la transformación reestructura la venta (C-01). Los hace la
transformación, con los controles de `integracion-datos` en cada uno: unicidad del maestro, claves nulas, formato,
huérfanas en los dos sentidos, filas antes y después y la suma de las unidades.

## 8. Plan de cruces

Todos por la izquierda, desde los hechos y muchos a uno. La suma que no puede cambiar es la de las unidades: 9.327.191.
Desde el cruce 2 tampoco cambian los dólares: 24.982.728,54.

| Orden | Partida | Se une | Clave | Cardinalidad | Aporta | Control | Agregar antes |
|---|---|---|---|---|---|---|---|
| 1 | venta en filas | Calendario | d | N:1 | date, wm_yr_wk | unidades | no |
| 2 | venta en filas | precios | item_id, store_id, wm_yr_wk | N:1 | sell_price; dólares = unidades × precio, con cero en los días sin precio | unidades | no |
| 3 | venta en filas | dim_producto | item_id | N:1 | dept_id, cat_id | unidades, dólares | no |
| 4 | hechos_series | dim_tienda | store_id | N:1 | state_id | unidades, dólares | sí: la venta en filas se suma a tienda, departamento y día, con cat_id |
| 5 | hechos_series | Calendario | d | N:1 | fecha, semana y semana anterior, eventos, SNAP del estado, periodo y marcas de parcial | unidades, dólares | no |
| 6 | precios | dim_producto | item_id | N:1 | dept_id | filas, sell_price | no |
| 7 | hechos_series | precio medio del departamento por semana | store_id, dept_id, wm_yr_wk_anterior → wm_yr_wk | N:1 | el precio medio de la semana anterior | unidades, dólares | sí: los precios con su departamento se resumen por tienda, departamento y semana |

En el cruce 7 el precio medio es la media simple de los precios de los productos del departamento con precio esa
semana (planteamientos; el responsable del caso, 24/11/2026). Solo cuentan los que ya tenían precio cuatro semanas antes, para que no avise
de una primera venta dentro del horizonte (reglas, apartado 5). No necesita las unidades de la venta.

## 9. Decisiones de modelado

1. **El precio se une a la venta de cada día** por producto, tienda y semana, con la semana del día sacada del
   Calendario. El precio no se suma: se multiplica por las unidades de cada día de su semana. Lo deciden las reglas, apartado 5,
   con la definición de la venta en dólares. Un día sin precio suma cero dólares, porque una semana sin precio es una
   semana sin venta (reglas, apartado 5). Escrito el 24/11/2026.
2. **La serie es la clave de la tabla de series**, (`store_id`, `dept_id`): no es una dimensión. Por qué: apartado 3.
   Propuesta del equipo de análisis, 24/11/2026.
3. **La categoría viaja en la tabla de series**, tomada al sumar los productos. Unir la tabla de series con
   `dim_producto` por el departamento multiplicaría las filas. Propuesta del equipo de análisis, 24/11/2026.
4. **La semana anterior se guarda en el Calendario** (`wm_yr_wk_anterior`), por el orden de las fechas. El código salta
   cinco veces al cambiar de año. Propuesta del equipo de análisis, 24/11/2026, para aplicar D9.
5. **El precio medio del departamento de la semana anterior se une a cada día de la serie.** Es un nivel y nunca se
   suma. D9 lo dice del precio que entra en la previsión de un día; aplicarlo al precio medio del departamento es
   propuesta del equipo de análisis, 24/11/2026.
6. **Un mes o una semana es parcial** si no tiene todos sus días dentro de su periodo. Para los días sin periodo, dentro
   del calendario. Es la lectura del equipo de análisis de las reglas, apartado 5, 24/11/2026.
7. **Los cruces los hace la transformación** con los controles de `integracion-datos`, porque todos parten de la venta en
   filas. Propuesta del equipo de análisis, 24/11/2026.
8. **`id` no entra en el modelo**: la clave es `item_id` con `store_id` (corrección, C-02; petición 07, 23/11/2026).

El responsable del caso aprobó el diseño entero el 24/11/2026 («Vale, apruebo el diseño»), con la decisión 5 explicada antes: es D9
aplicado al nivel que se prevé, y la prueba rápida del reconocimiento ya usó ese precio. La escribe el equipo de análisis con
su sí.

Aprobado: sí · el responsable del caso · 2026-11-24

## 10. Observaciones y pendientes

### Lo que comprobó el script

Las 37 cifras de control de la petición salen iguales (informes/modelado-datos.json, `cifras_de_control`). Ningún dato
contradice el diseño. Las huellas de las tres tablas de entrada son las mismas antes y después.

### Pendientes de método

**El precio medio del departamento por semana**, ya fijado: la media simple (planteamientos; el responsable del caso, 24/11/2026), con los
productos que ya tenían precio cuatro semanas antes (reglas, apartado 5). La comparación de abajo se midió antes de ese
límite, con todos los productos con precio. La
ponderada necesitaba las unidades de la semana anterior, que dentro del horizonte todavía no se conocen. Lo que separa
a las dos, medido en la construcción sobre 12.108 semanas de departamento en tienda con las dos medias:

- la diferencia relativa sin signo es de 28,52 % de media y 28,04 % de mediana;
- el percentil 95 llega al 51,97 % y la máxima al 93,39 %;
- la ponderada queda por debajo de la simple en el 95,02 % de las semanas: los productos baratos venden más unidades;
- por departamento, la diferencia media va del 20,11 % de HOBBIES_2 al 43,23 % de HOBBIES_1.

En 2 semanas de departamento en tienda hay precio pero ninguna unidad vendida: ahí la ponderada no existe.

**El mínimo de la pregunta 4.** Ni las reglas ni los planteamientos dicen cuántos días de un evento hacen falta para dar
su efecto. Cada festivo aparece de 4 a 6 veces en el calendario entero (diccionario). Va a los planteamientos con la
fórmula de cada efecto.

**Lo que los planteamientos ya tienen por fijar** y este diseño deja en su celda: el número de orígenes, el intervalo
del 95 %, la fórmula de cada efecto, el error de cada mes, el corte cuyo horizonte cruza de un periodo al siguiente y los
primeros días sin historia.

### Lo que dicen distinto dos documentos

- La ficha, en el método de la pregunta 1, decía «Un modelo por serie: 70 series y 140 previsiones (D7)». Desde el
  24/11/2026 dice, como los planteamientos, que está por fijar. No cambia el modelo de datos: la tabla de
  series sirve a los dos.
- La ficha define el error «por departamento, tienda y periodo». Las reglas, apartado 6 dicen que el que decide es el de las 70
  series juntas, que el de cada departamento decide qué se recomienda en él y que el de cada tienda se da para leer. No
  se contradicen: el diseño sigue a las reglas.

### Lo que el diseño no comprueba

- El script comprueba el grano y los tipos de las claves. Si las claves casan entre tablas lo mide `integracion-datos`,
  salvo los recuentos del registro de exclusiones.
- En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar. El diccionario y la corrección
  cuentan cero vacíos en las claves de las tres tablas; si apareciera uno, el cruce para antes de unir.
- Un maestro que cambia con el tiempo se modela con la versión que hay. Aquí el departamento de un producto y el estado
  de una tienda no cambian en los datos.

### Ninguna cuestión de negocio abierta

Cada celda del diseño se llena con las reglas, la ficha, los planteamientos o la petición. No hace falta
`cuestiones-pendientes.md`.

### Datos personales

No existe `config/fuentes/proteccion-datos.json`: no hay datos personales (reglas, apartado 9). El modelo no usa ni
deja ninguna columna de personas.
