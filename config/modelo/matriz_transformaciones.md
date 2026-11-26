---
titulo: Matriz de transformaciones del caso 69 · qué entra en los dos modelos de previsión y cómo
estado: aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»), con las cuatro respuestas de «Lo que aprobó el responsable del caso»; propuesta por el agente analista-preparacion-modelo el mismo día
fecha_documento: 2026-11-24
dueno: el responsable del caso (decide) · el equipo de análisis (propone)
fuentes: `../negocio/reglas-negocio.md` §3 a §7; `../negocio/reglas-transformacion.md`; `../metodo/04_planteamientos.md` §2; `../../informes/particion.json`, `transformacion-datos.json`, `analisis-exploratorio__hechos_series.json` y `calidad-datos.json`; las fichas de HistGradientBoosting y de Ridge en `../../assets/fichas_de_algoritmos/`; el método `preparacion-modelo` §3 y su `catalogo.md`
---

# Matriz de transformaciones · caso 69

## Lo que aprobó el responsable del caso

El 24/11/2026, la matriz con estas cuatro respuestas, que mandan sobre lo que digan las filas de abajo:

1. **cuestión 001:** en `productos_con_precio_semana_anterior` cuentan solo los productos que ya tenían precio cuatro semanas
   antes, la regla del precio medio. Entra como candidata.
2. **Los días sin precio:** salen los primeros 35 días de cada serie, no 29. No queda ningún vacío en el
   entrenamiento ni en la validación, así que el precio medio va sin relleno y sin la marca `_faltante`
   (planteamientos §2, decisión 7).
3. **`evento_<nombre>`** entra como candidata, al lado de `event_name_1` y `event_name_2`: la preselección elige.
4. **`dia_del_mes`** entra como candidata.

## Lo que se pide aprobar

El responsable del caso tiene que aprobar, cambiar o quitar cada fila de las tablas de abajo. Con la matriz aprobada se construye el
preprocesador; sin ella no se construye nada.

Entran 8 columnas de la tabla de series de las 26 que tiene; las otras 18 se quedan fuera, cada una con su motivo. Las
variables nuevas candidatas son 25, todas sin crear todavía: 12 por cada modelo y una pendiente de la cuestión cuestión 001,
que no entra hasta que el responsable del caso la resuelva. Aparte van dos candidatas que no estaban en los planteamientos.

Lo que ya estaba fijado y esta matriz solo aplica:

- **Dos modelos.** Uno prevé las unidades a 10 días y otro los dólares a 28, cada uno para las 70 combinaciones de
  departamento y tienda, con la tienda y el departamento como variables (planteamientos §2, decisión 6).
- **Previsión recursiva.** Cada día del horizonte se prevé con lo previsto para los días anteriores (reglas, apartado 5).
- **Dos algoritmos compiten,** HistGradientBoosting y Ridge, con un solo preprocesador para los dos.
- **Lo que se sabe el día de prever** es la venta hasta el día anterior, el precio de la semana anterior y el
  calendario (reglas, apartado 5).

## La partición en que se apoya

Las dos partes son exactamente las filas de cada periodo que apartó el paso 2, comprobado en código
(`informes/particion.json`):

- **entrenamiento:** la construcción, del 29/01/2011 al 22/05/2014, con 84.700 filas de las 70 combinaciones;
- **validación:** del 23/05/2014 al 22/05/2015, con 25.550 filas de las mismas 70 combinaciones.

No hay lote de producción: la prueba final está fuera del caso.

## Diagnóstico

- **No hay desequilibrio de clases:** los dos objetivos son cantidades, unidades y dólares por día.
- **Los objetivos tienen colas largas y nadie las ha tratado.** En la construcción, las unidades diarias de una serie
  tienen mediana 51 y llegan a 1.030; los dólares, mediana 151,84 y máximo 3.014,14 (exploratorio). La corrección dejó
  los valores como son, porque son ventas reales (PC-01 a PC-06). Lo que se calcula de ellos, los retardos y las
  medias, hereda esas colas.
- **Hay saltos de nivel duraderos** en 28 de las 70 series (exploratorio, H-06). Los retardos y las medias llevan el
  nivel reciente de cada serie, así que lo siguen.
- **El precio medio no tiene señales de cola** en el exploratorio y está vacío en las cinco primeras semanas.
- **Las fugas que señala el exploratorio** son las tres marcas que se conocen al cerrar el día y los dos objetivos del
  mismo día (alertas A-23 a A-26). Ninguna entra.
- **En la validación aparece un evento nuevo en la segunda columna de eventos:** «Father's day» va en `event_name_2`,
  que en el entrenamiento solo trae Easter, Cinco De Mayo y OrthodoxEaster. En `event_name_1` sí está.

## Cómo se decidió el escalado

Compiten dos algoritmos con un preprocesador común, así que se escala (catálogo, «Escalado por algoritmo», pregunta 1).
A HistGradientBoosting no le cambia nada y a Ridge le hace falta, porque su castigo suma coeficientes de variables
distintas (ficha de Ridge §6). Las columnas de 0 y 1 no se escalan (pregunta 2). Lo que sale de los objetivos tiene
colas sin tratar y lleva `RobustScaler` (pregunta 3). El resto de numéricas lleva `StandardScaler`, el de las
regresiones (pregunta 4). Ninguna salida es dispersa y no hay min-max, así que no aplica ninguna de las trampas de la
pregunta 5. La columna «escalado» de cada fila dice qué pregunta lo decidió.

## Las columnas de la tabla de series que entran

| variable | tipo | rama | escalado | relleno | salida | entra | porqué | desde cuándo se conoce |
|---|---|---|---|---|---|---|---|---|
| store_id | nominal | una columna por categoría, `OneHotEncoder(sparse_output=False)`, sin `drop` | ninguno (pregunta 2: columnas de 0 y 1) | no tiene vacíos | `store_id_ohe_<tienda>`, 10 columnas | sí | planteamientos §2, decisión 6: la tienda es variable del modelo; Ridge está regularizado y no necesita quitar una columna (catálogo, categóricas) | de antemano: la tienda no cambia |
| dept_id | nominal | una columna por categoría, como `store_id` | ninguno (pregunta 2) | no tiene vacíos | `dept_id_ohe_<departamento>`, 7 columnas | sí | planteamientos §2, decisión 6 | de antemano: el departamento no cambia |
| weekday | nominal | una columna por categoría | ninguno (pregunta 2) | no tiene vacíos | `weekday_ohe_<día>`, 7 columnas | sí | el día más fuerte vende de 1,22 a 1,51 veces el más flojo y siempre cae en fin de semana (exploratorio, H-03). El efecto no crece con el número del día, así que va como categoría para que Ridge lo pueda usar | de antemano: calendario (reglas, apartado 5) |
| month | nominal | una columna por categoría | ninguno (pregunta 2) | no tiene vacíos | `month_ohe_<mes>`, 12 columnas | sí | ningún mes se aparta más de un 9 % de la media (exploratorio, H-08): pesa poco, pero diciembre no va al lado de enero si entra como número | de antemano: calendario |
| event_name_1 | nominal | una columna por categoría, `handle_unknown="infrequent_if_exist"` | ninguno (pregunta 2) | constante «sin evento», sin marca: el vacío significa «día sin evento» (reglas, apartado 5) y esa categoría no existe en los datos con otro significado | `event_name_1_ohe_<evento>`, 31 columnas | sí | 29 eventos dentro del error con al menos 30 días de serie (planteamientos §2); en la construcción cada evento tiene al menos 210 filas, por encima del mínimo de 30 para no agrupar (parametros.md) | de antemano: calendario |
| event_name_2 | nominal | como `event_name_1` | ninguno (pregunta 2) | «sin evento», como `event_name_1` | `event_name_2_ohe_<evento>`, 4 columnas | sí | tres eventos de 70 filas cada uno en el entrenamiento. Con «Father's day», que solo aparece aquí en la validación, la fila sale con todas estas columnas a cero. Por eso se propone aparte la candidata `evento_<nombre>` | de antemano: calendario |
| snap | binaria | tal cual | ninguno (pregunta 2) | no tiene vacíos | `snap` | sí | SNAP sube la alimentación de un 4,3 % a un 24,0 % frente a los días sin SNAP de la misma quincena (exploratorio, H-04) | de antemano: calendario SNAP del estado de la tienda (reglas, apartado 5) |
| precio_medio_semana_anterior | continua | tal cual | `StandardScaler` (pregunta 3: sin colas en el exploratorio; pregunta 4: el de las regresiones) | ninguno: salen los 35 primeros días de cada serie (aprobado, respuesta 2) | `precio_medio_semana_anterior_ss` | sí | D9 y una nota interna (reglas, apartado 5). Vacía en las semanas 11101 a 11105, 35 días. Con los 35 primeros días de cada serie fuera (planteamientos §2, decisión 7) no queda ningún día con el precio vacío | de antemano: el precio de la semana anterior se da por conocido también dentro del horizonte (reglas, apartado 5, D9) |

## Las columnas de la tabla de series que no entran

| variable | entra | porqué | desde cuándo se conoce |
|---|---|---|---|
| d | no | identificador del día (petición; exploratorio, tipificación) | de antemano |
| unidades | no | objetivo del modelo de unidades. En el de dólares sería la venta del mismo día (alerta A-26) | al cerrar el día |
| dolares | no | objetivo del modelo de dólares. En el de unidades sería la venta del mismo día (alerta A-26) | al cerrar el día |
| periodo | no | marca la partición; no describe la venta (petición) | de antemano |
| cierre_tienda | no | se conoce al cerrar el día y sale de las unidades (reglas de transformación, apartado 1; alerta A-23). El 25 de diciembre ya entra por `event_name_1` | al cerrar el día |
| fuera_del_error | no | se conoce al cerrar el día; sirve para medir el error (alerta A-25) | al cerrar el día |
| clase_cero | no | usa la media del periodo entero y solo describe (reglas de transformación; alerta A-24) | después del periodo entero |
| cat_id | no | copia de `dept_id`: cada departamento tiene una sola categoría, medido en el entrenamiento (`programacion-del-caso`, error 33) | de antemano |
| state_id | no | copia de `store_id`: cada tienda tiene un solo estado, medido en el entrenamiento (error 33) | de antemano |
| wday | no | copia de `weekday` con un número: cada día de la semana tiene un solo código (error 33) | de antemano |
| event_type_1 | no | copia agrupada de `event_name_1`: cada evento tiene un solo tipo (calidad, 0 nombres con más de uno) | de antemano |
| event_type_2 | no | copia agrupada de `event_name_2`, por el mismo motivo | de antemano |
| year | no | en la validación toma 2015, que el entrenamiento no tiene. HistGradientBoosting lo pone en el último tramo y Ridge lo prolonga en línea recta. El nivel de cada serie ya entra con los retardos y las medias | de antemano |
| date | no | una fecha no entra tal cual; sus componentes ya están en `weekday` y `month` (catálogo, «Fechas») | de antemano |
| wm_yr_wk | no | identificador de la semana del precio (exploratorio, tipificación) | de antemano |
| wm_yr_wk_anterior | no | identificador de la semana anterior; ya se usó para traer el precio | de antemano |
| mes_parcial | no | marca para no comparar meses incompletos (reglas, apartado 5); no describe la venta | de antemano |
| semana_parcial | no | marca para no comparar semanas incompletas (reglas, apartado 5); no describe la venta | de antemano |

`store_id` y `dept_id` forman la clave con `d`, pero entran como variables porque lo fijan los planteamientos.

## Las variables nuevas candidatas

Son las de los planteamientos §2, decisión 7. Ninguna existe todavía: si el responsable del caso las aprueba, las crea
`transformacion-datos`, porque necesitan otras filas de la misma serie. Cada una se calcula dentro de cada combinación
de departamento y tienda, con los días ordenados por fecha. Solo usa días anteriores al previsto. `<obj>` es
`unidades` en el modelo de unidades y `dolares` en el de dólares: cada modelo usa la historia de su propio objetivo.

| variable | tipo | rama | escalado | relleno | salida | entra | porqué | desde cuándo se conoce |
|---|---|---|---|---|---|---|---|---|
| `<obj>_lag_1` a `<obj>_lag_7` | continua | tal cual | `RobustScaler` (pregunta 3: colas sin tratar) | ninguno: las filas sin historia salen (planteamientos §2, decisión 7) | `<obj>_lag_k_rs` | sí | la autocorrelación a 1 y a 7 días va de 0,19 a 0,70 en mediana por departamento (exploratorio, H-07) | al cerrar el día t−k |
| `<obj>_lag_14`, `_lag_21`, `_lag_28` | continua | tal cual | `RobustScaler` (pregunta 3) | ninguno | `<obj>_lag_k_rs` | sí | el mismo día de la semana en las semanas anteriores; la autocorrelación a 14 y 28 días sigue alta en FOODS_3 y HOUSEHOLD_1 (exploratorio) | al cerrar el día t−k |
| `<obj>_media_7` | continua | tal cual | `RobustScaler` (pregunta 3) | ninguno | `<obj>_media_7_rs` | sí | el nivel de la última semana, de t−7 a t−1 | al cerrar el día t−1 |
| `<obj>_media_28` | continua | tal cual | `RobustScaler` (pregunta 3) | ninguno | `<obj>_media_28_rs` | sí | el nivel de las últimas cuatro semanas, de t−28 a t−1; sigue los saltos de nivel (H-06) | al cerrar el día t−1 |
| `productos_con_precio_semana_anterior` | discreta | tal cual | `StandardScaler` (pregunta 4) | ninguno en la semana con precio; las cinco primeras semanas, como el precio medio | `productos_con_precio_semana_anterior_ss` | sí, candidata (cuestión 001 resuelta) | en una serie, la llegada de productos nuevos multiplica la venta por 7,2 (ficha; planteamientos §2, decisión 7) | de antemano: solo cuentan los productos con precio cuatro semanas antes (cuestión 001) |

**Cómo se calculan en la previsión recursiva.** Para un día previsto t con origen o, la historia de la serie es la venta
real hasta o seguida de lo que el modelo ya previó de o+1 a t−1, sin bajar de cero (reglas, apartado 5 y §6). En el modelo de
dólares, esa historia es la de dólares previstos, nunca unidades por un precio. Con esa historia:

- **`<obj>_lag_k`** es el valor de la historia en t−k. Es real si t−k cae en el origen o antes; si cae después, es
  una previsión:
  - en unidades, con 10 días de horizonte, los retardos de 1 a 7 son previsiones a partir del día k+1 del horizonte;
    los de 14, 21 y 28 días son siempre reales;
  - en dólares, con 28 días de horizonte, todos los retardos hasta el de 21 días son previsiones a partir del día k+1;
    el de 28 días es siempre real.
- **`<obj>_media_7` y `<obj>_media_28`** son la media de la historia de t−7 (o t−28) a t−1. En el día h del horizonte
  mezclan días reales con h−1 días previstos, como mucho 7 o 28.
- **El 25 de diciembre,** si cae dentro de un horizonte, entra en la historia con lo que el modelo previó para él, como
  cualquier otro día (reglas, apartado 5, «El horizonte»).
- **En el entrenamiento** cada fila se calcula con la venta real hasta el día anterior, que es la previsión a un día.
  Las previsiones solo aparecen al prever desde un origen.

## Candidatas que no estaban en los planteamientos

Van aparte, con su motivo. Las propone el equipo de análisis y no entran si el responsable del caso no las aprueba.

| variable | tipo | rama | escalado | relleno | salida | entra | porqué | desde cuándo se conoce |
|---|---|---|---|---|---|---|---|---|
| `evento_<nombre>` | binaria, una por evento | una columna por evento, a 1 si el evento está en `event_name_1` o en `event_name_2` | ninguno (pregunta 2) | 0 en los días sin ese evento | `evento_<nombre>` | sí, candidata al lado de `event_name_1` y `event_name_2` (aprobado, respuesta 3) | «Father's day» cae en `event_name_2` en la validación y en el entrenamiento solo aparece en `event_name_1` (medido en las dos partes). Con las dos columnas por separado, ese día sale sin evento | de antemano: calendario |
| `dia_del_mes` | discreta, de 1 a 31 | tal cual, sacada de `date` | `StandardScaler` (pregunta 4) | no tiene vacíos | `dia_del_mes_ss` | sí, candidata (aprobado, respuesta 4) | los días SNAP caen siempre en los días 1 a 15 del mes (planteamientos, alcance del exploratorio). El día del mes da al modelo esa quincena aunque no haya SNAP | de antemano: calendario |

## Límites y preguntas abiertas

- **cuestión 001, resuelta el 24/11/2026** (respuesta 1). Antes estaba abierta: sin ella, la candidata de los productos con precio no entraba. Contada tal cual avisa de la
  primera venta de un producto dentro del horizonte (`../negocio/cuestiones-pendientes.md`).
- **La marca `precio_medio_semana_anterior_faltante`** solo vale 1 en 6 días por serie del entrenamiento, si salen los
  29 primeros días. En la validación vale siempre 0. La preselección puede encontrarla sin variación útil (error 33).
  Quitar también esos 6 días de cada serie evitaría el relleno, pero es un criterio que no está escrito. **Superado:**
  el responsable del caso aprobó quitarlos (respuesta 2); la marca ya no existe.
- **No se proponen ramas de gaussianizar** para Ridge. El catálogo no la hace obligatoria, el supuesto de normalidad es
  de los residuos y no de las variables. Con el modelo de árboles en competencia, el preprocesador es uno. Si Ridge
  queda lejos de HistGradientBoosting, es la primera vía que se probaría.
- **Los días fuera del error** siguen en las dos partes. Si entran en el ajuste del modelo lo decide
  `aprendizaje-automatico`, no esta matriz.
- **Los conteos de las candidatas** (cuántas filas quedan sin historia, cuántas con el precio vacío) se miden cuando se
  creen, en `transformacion-datos`. Van al registro de transformaciones.

## Lo que el responsable del caso podía decidir (decidido el 24/11/2026, arriba)

- Aprobar la matriz como está, o cambiar las filas que quiera.
- Resolver cuestión 001 con una de sus tres opciones.
- Aceptar o quitar las dos candidatas que no estaban en los planteamientos.
- Decidir si los 6 días con el precio vacío salen o se rellenan con su marca.
