---
titulo: Reglas de transformación del caso 69 · la tabla de series por departamento, tienda y día, con sus dos dimensiones
estado: aprobado por el responsable del caso el 24/11/2026, con la media simple del precio del departamento; el mismo día, solo con los productos que ya tenían precio cuatro semanas antes
fecha_documento: 2026-11-24
dueno: el responsable del caso (decide) · el equipo de análisis (redacta)
fuentes: `../modelo/modelo-datos.md` (aprobado el 24/11/2026); `reglas-negocio.md` §3 a §7; `01_ficha_del_caso.md`; `../metodo/04_planteamientos.md`; `../modelo/registro-transformaciones.md`; `../../informes/modelado-datos.json` y `../../informes/correccion-datos.json`; la plantilla común una plantilla común
---

# Reglas de transformación del proyecto

> Este fichero lo lee el método `transformacion-datos`. Dice qué tablas nuevas necesita el análisis y de dónde sale cada
> columna. Los criterios no se definen aquí: vienen de `reglas-negocio.md`, que se cita por apartado. Un criterio lo
> decidió el responsable del caso aquí: el precio medio del departamento es la media simple de sus productos (apartado 1,
> `precio_medio_semana_anterior`; el responsable del caso, 24/11/2026). Es de método y quedó fijado en los planteamientos. Qué productos
> cuentan en ella lo fija `reglas-negocio.md` §5.

## Proyecto de previsión de la venta de Walmart por departamento y tienda

### De qué se parte

De las tablas corregidas y del Calendario, siguiendo el diseño aprobado en `config/modelo/modelo-datos.md`.
No hay integración previa: todos los cruces parten de la venta en filas y los hace esta transformación, con los
controles de `integracion-datos` en cada uno (diseño §7).

- `venta_corregido.parquet`: una fila por producto y tienda, con las unidades de cada día en 1.575 columnas, de d_1
  (29/01/2011) a d_1575 (22/05/2015).
- `precios_corregido.parquet`: una fila por producto, tienda y semana de Walmart, con su precio.
- `calendario.parquet`: una fila por día, del 29/01/2011 al 19/06/2016, con la semana anterior, el periodo y las marcas
  de parcial (registro de transformaciones, T-003).

Las tablas de entrada no se modifican. Cada tabla nueva se guarda aparte en `data/processed/`. La fecha de referencia
es el 22/05/2015 (reglas, apartado 5, «Fechas»).

La transformación pasa primero la venta a una fila por producto, tienda y día (7.875.000 filas) y le une la semana del
Calendario, el precio de esa semana y el departamento (cruces 1 a 3 del diseño). Esa tabla intermedia no se guarda: no
es una tabla de entrega del diseño.

### 1. Tabla de series (una fila por departamento en una tienda y día)

Nueva tabla, `hechos_series.parquet`. Entran los 1.575 días de la venta de las 70 series, sin quitar ninguno: todos son
de la construcción o de la validación (reglas, apartado 7, «Población del análisis»). Cada fila es la venta de un departamento
en una tienda un día natural (reglas, apartado 3 y §5).

La clave y las dimensiones:

- `store_id`, `dept_id` y `d`: identifican la fila (diseño, decisión 2).
- `cat_id`: la categoría del departamento, tomada al sumar sus productos (diseño, decisión 3).
- `state_id`: el estado de la tienda, de `dim_tienda` (cruce 4; reglas, apartado 4).

La venta, que es lo que se prevé (reglas, apartado 5, «La venta»):

- `unidades`: la suma de las unidades de los productos del departamento en la tienda ese día. Un día sin venta vale
  cero y no queda vacío.
- `dolares`: la suma, producto a producto, de las unidades de cada día por el precio de ese producto en esa tienda la
  semana del día. Se calcula en céntimos enteros y se guarda en dólares con dos decimales. Un día sin precio suma cero
  dólares, porque una semana sin precio es una semana sin venta. Si un día tuviera venta y no tuviera precio, la
  transformación para antes de calcular (reglas, apartado 5, «Datos vacíos y valores especiales»).

Del Calendario, unido por `d` (cruce 5; reglas, apartado 5):

- `date`, `year`, `month`, `weekday`, `wday`, `wm_yr_wk` y `wm_yr_wk_anterior`, como están en el Calendario.
- `event_name_1`, `event_type_1`, `event_name_2` y `event_type_2`: el vacío es «sin evento», un día normal (reglas, apartado 5).
- `snap`: el día SNAP del estado de la tienda, tomado de `snap_ca`, `snap_tx` o `snap_wi` según `state_id`. Las otras
  dos columnas no se traen.
- `periodo`, `mes_parcial` y `semana_parcial`, como están en el Calendario. Un mes o una semana parcial no se compara con
  uno completo (reglas, apartado 5).

Las marcas para medir el error y describir los ceros:

- `cierre_tienda`: verdadero si ese día los siete departamentos de la tienda venden cero (reglas, apartado 5, «El día sin ventas»).
  Se sabe al cerrar el día. No es una variable que se conozca la víspera, salvo el 25 de diciembre, que ya trae el
  Calendario como evento.
- `fuera_del_error`: verdadero el 25 de diciembre y en el cierre de una tienda fuera del 25 de diciembre, que se trata
  igual (reglas, apartado 5 y §6). Esas filas se quedan en la tabla con su venta, pero no entran en el error, el sesgo ni la
  ventaja.
- `clase_cero`: en los días con cero unidades, la clase de D8 (reglas, apartado 5), en este orden: `cierre`, `25_diciembre`,
  `demanda_intermitente` y `resto`. Vacío en los días con venta. La demanda intermitente es la de una serie con menos de
  10 unidades de media al día en su periodo, sin contar sus días de cierre, como la midió la corrección. Esa media usa el
  periodo entero, así que la clase es para describir y nunca entra como variable del modelo.

El precio que entra en la previsión (reglas, apartado 5, D9; diseño, decisión 5):

- `precio_medio_semana_anterior`: la media simple de los precios de los productos del departamento que tienen precio en
  esa tienda la semana anterior a la del día (`wm_yr_wk_anterior`) y que ya lo tenían cuatro semanas antes de esa semana
  (reglas, apartado 5, «El precio»). Es un nivel y nunca se suma entre filas ni entre series. Queda vacío en los días de las cinco
  primeras semanas, de la 11101 a la 11105: la primera no tiene anterior y en las cuatro siguientes ningún producto lleva
  cuatro semanas con precio.
  - **Por qué cuatro semanas antes (el responsable del caso, 24/11/2026: «Sí, apruebo los dos»).** Un producto entra la semana de su
    primera venta y no vuelve a quedarse sin precio. Contado desde que entra, la media de una semana dentro del horizonte
    avisaría de una primera venta que el día de prever no se conoce. Con 28 días de horizonte, el día previsto cae como
    mucho cuatro semanas después de la del origen, así que todo producto que cuenta ya se vendía antes del origen. Sin
    contar, quedan 19.769 de las 854.573 filas de precio.
  - **Por qué la media simple (propuesta del equipo de análisis; el responsable del caso, 24/11/2026: «Por lo que dices, hay que hacerlo así»).** La ponderada por unidades necesita las
    unidades vendidas la semana anterior. Desde la segunda semana del horizonte, esa semana cae entera o en parte dentro
    del horizonte, así que sus unidades todavía no se conocen: pasa en los dos horizontes, el de 10 días y el de 28. D9 da
    por conocido el precio de esa semana; la venta solo se conoce hasta el origen, el último día con venta conocida
    (reglas, apartado 5, «Lo que se sabe el día de prever» y «El horizonte»). La simple solo usa precios. Es también la que usó
    la prueba rápida del reconocimiento. Lo que separa a las dos medias está medido en el diseño §10: 28,52 % de
    diferencia media.
  - **Lo que arrastró, por la cascada del caso:** el punto «cómo se calcula el precio medio de un departamento» pasó a
    fijado en los planteamientos; el diseño §5, §6, §8 y §10 dejaron de decir «por fijar»; el cruce 7 y la pregunta
    pendiente de `scripts/04_modelado_datos.py` cambiaron con él.

Comprobación: las unidades y los dólares de la tabla de series son los de la venta en filas. Sus filas son las 70
series por los 1.575 días. Medido por el equipo de análisis con el intérprete del caso el 24/11/2026, sobre los datos de hoy:

- venta en filas: 7.875.000 filas, 9.327.191 unidades y 24.982.728,54 dólares, iguales a `cifras_de_control` del
  modelado;
- tabla de series: 110.250 filas, 84.700 de la construcción y 25.550 de la validación; cada serie tiene una sola
  categoría;
- `cierre_tienda`: 175 días de serie en la construcción y 56 en la validación;
- `fuera_del_error`: 217 días de serie en la construcción y 70 en la validación. Son 210 y 70 del 25 de diciembre, más
  los 7 del cierre de WI_1 el 02/02/2011 (d_5);
- `clase_cero` en la construcción: cierre 175, 25 de diciembre 35, demanda intermitente 2.171 y resto 35; en la
  validación: 56, 12, 201 y 2. Las diez series intermitentes son las de HOBBIES_2. Las ocho cifras son las de
  `clases_de_ceros` de la corrección;
- `precio_medio_semana_anterior`: 15.470 de los 15.750 grupos de tienda, departamento y semana (70 por 225) tienen algún
  producto que cuenta; los 280 que no, son los de las semanas 11101 a 11104. Quedan vacías 2.450 filas, las 70 series en
  los 35 días de las semanas 11101 a 11105, todas de la construcción. Medido por el equipo de análisis el 24/11/2026.

### 2. Dimensión de producto (una fila por producto)

Nueva tabla, `dim_producto.parquet`, con los 500 productos del recorte (diseño §3; reglas, apartado 4).

- `item_id`: la clave.
- `dept_id` y `cat_id`: el departamento y la categoría, de la venta.

Comprobación: 500 filas, la clave sin repetir; cada producto con un solo departamento y una sola categoría. Medido por el
modelado el 24/11/2026: 0 productos con más de uno. Por departamento: FOODS_1 43, FOODS_2 61, FOODS_3 129, HOBBIES_1 73,
HOBBIES_2 27, HOUSEHOLD_1 93 y HOUSEHOLD_2 74.

### 3. Dimensión de tienda (una fila por tienda)

Nueva tabla, `dim_tienda.parquet`, con las 10 tiendas (diseño §3; reglas, apartado 4).

- `store_id`: la clave.
- `state_id`: el estado de la tienda, de la venta.

Comprobación: 10 filas, la clave sin repetir; cada tienda con un solo estado, 4 en California, 3 en Texas y 3 en
Wisconsin (reglas, apartado 4). Medido por el modelado el 24/11/2026: 0 tiendas con más de un estado.

### 4. Registro de exclusiones

No crea ningún dataset de análisis. Deja en el informe de la transformación una tabla con una fila por cada clase que
sale de algún cálculo (reglas, apartado 7, «Población del análisis»), con los días de serie, las unidades y los dólares sacados
del código:

- los días del 25 de diciembre y el cierre de WI_1 del 02/02/2011 (`fuera_del_error`): salen del error, del sesgo y de
  la ventaja; se quedan en la tabla;
- los 35 días de las semanas 11101 a 11105 sin precio medio de la semana anterior: el vacío de
  `precio_medio_semana_anterior`;
- los 53 productos-tienda sin ningún precio: no venden ningún día y suman cero a su departamento, así que no salen de
  nada;
- los 394 días del Calendario posteriores a la fecha de referencia: no tienen venta en el caso y no están en la tabla de
  series; siguen en el Calendario para producción;
- los primeros días de cada serie sin la historia que piden las variables: se cuentan en el paso 5, cuando se fijen las
  variables (reglas, apartado 7).

Al lado de cada clase, si se puede recuperar: las cuatro primeras siguen en la tabla o en sus fuentes; los primeros
días no, porque no hay datos antes del 29/01/2011.

### Lo que los pasos siguientes necesitan

- **Exploración (paso 4):** la tabla de series con sus marcas. Lo que se mira por producto, como los productos que
  empiezan a venderse y la estrategia de precio, se lee de las tablas corregidas, que siguen en `data/processed/`.
- **Variables, transformación y modelo (paso 5):** la tabla de series como base de los retardos, las ventanas y el
  calendario, con `fuera_del_error` para medir y `periodo` para cortar.
- **Totales de la pregunta 3:** `dim_tienda` y `cat_id` para sumar las previsiones de abajo arriba (reglas, apartado 4).
- **Producción:** el Calendario con los días posteriores a la fecha de referencia, para los días que se prevén.

### Lo que no se hace en esta fase

- No se crean retardos, ventanas ni marcas de racha: son las variables del paso 5. Antes hay que fijar la historia mínima
  y decidir si se entrena un modelo por serie o uno para las 70 series, que está en los planteamientos.
- No se codifican las categóricas ni se escala nada.
- No se eligen variables ni se ajusta ningún modelo.
- No se fija el número de orígenes de la validación: es de los planteamientos.
- No se imputa ningún vacío. Los vacíos nuevos son dos: el precio medio de las cinco primeras semanas y la clase de
  cero en los días con venta, que no tienen clase.
- No se calcula el efecto de festivos, SNAP, día de la semana ni precio: es la pregunta 4, con su fórmula por fijar en
  los planteamientos.

## Historial de cambios

| Fecha | Cambio | Quién |
|---|---|---|
| 24/11/2026 | Primera versión, con la media simple del precio medio del departamento (antes «simple o ponderada, por fijar» en los planteamientos y el diseño) | El equipo de análisis redacta; el responsable del caso aprueba |
| 24/11/2026 | En `precio_medio_semana_anterior` solo cuentan los productos con precio desde cuatro semanas antes (antes, todos los que tenían precio esa semana). Vacíos de 490 a 2.450 filas | El responsable del caso: «Sí, apruebo los dos» |
