---
titulo: Contrato de producción del caso 69 · cómo se construye cada columna de los dos modelos de previsión
estado: aprobado por el responsable del caso el 25/11/2026, «Apruebo el contrato»
fecha_documento: 2026-11-25
dueno: el responsable del caso (decide) · el equipo de análisis (propone)
fuentes: `informes/busqueda.json`, `informes/validacion.json`, `informes/preparacion.json`, `informes/preseleccion.json`, `informes/variables_modelo.json`, `registro-transformaciones.md`, `matriz_transformaciones.md`, `../metodo/04_planteamientos.md` §2 y `../negocio/reglas-negocio.md` §5 a §7
generado_por: `scripts/19_contrato_produccion.py`; no se edita a mano
---

# Contrato de producción · caso 69

## Lo que aprobó el responsable del caso

Los dos modelos que la validación dio por buenos son HistGradientBoosting en unidades y HistGradientBoosting en dólares. El de unidades usa 82 columnas, que salen de 21 finalistas; el de dólares, 82 columnas de 21 finalistas. Cada finalista tiene su cadena completa en el registro de transformaciones y cada paso de la cadena tiene una de las cuatro clases.

Con este contrato aprobado se escriben el Pipeline, el reentreno y la ejecución diaria. El responsable del caso aprobó estas tres cosas:

- las cadenas y la clase de cada paso;
- los 3 pasos en que el registro dice algo distinto de lo que esperaba la petición;
- lo que el registro no recoge, que va en «Límites».

## Los dos modelos

Cada fila es una serie en un día: su identificador es store_id, dept_id, date. Cada modelo prevé las 70 combinaciones de departamento y tienda a la vez. Ninguno tiene corte, porque los dos prevén una cantidad.

- **Unidades.** Prevé a 10 días con HistGradientBoosting (min_samples_leaf 205, max_iter 500, max_depth sin límite, learning_rate 0.1, l2_regularization 0; semilla 42). Se ajustó con 82.250 filas. Lo aprobó el responsable del caso, 25/11/2026, «Apruebo el ganador».
- **Dólares.** Prevé a 28 días con HistGradientBoosting (min_samples_leaf 205, max_iter 500, max_depth sin límite, learning_rate 0.1, l2_regularization 0; semilla 42). Se ajustó con 82.250 filas. Lo aprobó el responsable del caso, 25/11/2026, «Apruebo el ganador».

Los demás hiperparámetros son los de la librería, con la parada temprana apagada; la lista entera está en `informes/preproduccion.json` y en `informes/busqueda.json`. El veredicto de la validación lo aprobó el responsable del caso, 25/11/2026, «Sí, apruebo el veredicto».

## Las finalistas

Una finalista es la variable de la que salen columnas del modelo. La tabla va del todo a la unidad: la serie, el calendario, el precio y la historia de la venta. Los retardos y las medias salen del objetivo de cada modelo, así que cambian de nombre de uno a otro.

| Finalista | Columnas en unidades | Columnas en dólares |
|---|---|---|
| `store_id` | 10 | 10 |
| `dept_id` | 7 | 7 |
| `weekday` | 7 | 7 |
| `month` | 12 | 12 |
| `snap` | 1 | 1 |
| `evento_<nombre>` | 30 | 30 |
| `precio_medio_semana_anterior` | 1 | 1 |
| `productos_con_precio_semana_anterior` | 1 | 1 |
| `dia_del_mes` | 1 | 1 |
| `<obj>_lag_1` | 1 | 1 |
| `<obj>_lag_2` | 1 | 1 |
| `<obj>_lag_3` | 1 | 1 |
| `<obj>_lag_4` | 1 | 1 |
| `<obj>_lag_5` | 1 | 1 |
| `<obj>_lag_6` | 1 | 1 |
| `<obj>_lag_7` | 1 | 1 |
| `<obj>_lag_14` | 1 | 1 |
| `<obj>_lag_21` | 1 | 1 |
| `<obj>_lag_28` | 1 | 1 |
| `<obj>_media_7` | 1 | 1 |
| `<obj>_media_28` | 1 | 1 |

## Los pasos por clase

Cada paso va a un sitio según su clase. Las fichas son las del registro de transformaciones; el preprocesador sigue la matriz aprobada (R-011) y el modelo, la R-020.

### Quita filas

Van solo en el reentreno, antes del Pipeline y contado; nunca en la ejecución diaria.

- R-010 · el entrenamiento son las filas de la construcción, hasta el 22/05/2014; al reentrenar, la tabla que se pasa marca el corte. Lo usan: todas las finalistas.
- R-017 · salen del entrenamiento los primeros 35 días de cada serie, que no tienen la historia que piden las variables. Lo usan: todas las finalistas.

### No aprende

Van en el módulo .py como función, dentro del Pipeline con FunctionTransformer o antes con pandas, igual al reentrenar que al ejecutar.

- T-001 · las series suman los 500 productos del recorte de M5 en las 10 tiendas. Lo usan: `store_id`, `dept_id`, `precio_medio_semana_anterior`, `productos_con_precio_semana_anterior`, `<obj>_lag_1`, `<obj>_lag_2`, `<obj>_lag_3`, `<obj>_lag_4`, `<obj>_lag_5`, `<obj>_lag_6`, `<obj>_lag_7`, `<obj>_lag_14`, `<obj>_lag_21`, `<obj>_lag_28`, `<obj>_media_7`, `<obj>_media_28`.
- R-002 · las columnas SNAP de cada estado pasan a minúsculas. Lo usan: `snap`.
- R-001 · la fecha del calendario se lee como fecha con el formato año-mes-día. Lo usan: `precio_medio_semana_anterior`, `productos_con_precio_semana_anterior`, `dia_del_mes`, `<obj>_lag_1`, `<obj>_lag_2`, `<obj>_lag_3`, `<obj>_lag_4`, `<obj>_lag_5`, `<obj>_lag_6`, `<obj>_lag_7`, `<obj>_lag_14`, `<obj>_lag_21`, `<obj>_lag_28`, `<obj>_media_7`, `<obj>_media_28`.
- R-004 · la venta de cada producto se une con el calendario, el precio, el producto y la tienda; se suma por departamento, tienda y día en unidades y en céntimos; snap es el del estado de la tienda. Lo usan: todas las finalistas.
- R-007 · una fila por producto con su departamento. Lo usan: `dept_id`, `precio_medio_semana_anterior`, `productos_con_precio_semana_anterior`, `<obj>_lag_1`, `<obj>_lag_2`, `<obj>_lag_3`, `<obj>_lag_4`, `<obj>_lag_5`, `<obj>_lag_6`, `<obj>_lag_7`, `<obj>_lag_14`, `<obj>_lag_21`, `<obj>_lag_28`, `<obj>_media_7`, `<obj>_media_28`.
- T-003 · el Calendario añade a cada día su semana anterior, por el orden de las fechas. Lo usan: `weekday`, `month`, `evento_<nombre>`, `precio_medio_semana_anterior`, `productos_con_precio_semana_anterior`.
- R-008 · una fila por tienda con su estado. Lo usan: `snap`.
- R-015 · una columna de 0 y 1 por evento de la lista, a 1 si el día lo trae en event_name_1 o en event_name_2. Lo usan: `evento_<nombre>`.
- R-016 · el día del mes, de 1 a 31, sacado de la fecha. Lo usan: `dia_del_mes`.
- R-011 · el preprocesador la deja pasar tal cual. Lo usan: `snap`, `evento_<nombre>`.
- R-018 · el modelo toma por su nombre las columnas del ganador; las de event_name_1 y event_name_2 no entran (reglas, apartado 7). Lo usan: todas las finalistas.

### Necesita otras filas

Van con las filas anteriores a cada día, nunca con las posteriores ni con el propio día: al reentrenar, con la propia tabla de entrenamiento; al prever, con la tabla de historia que ya lleva lo previsto (previsión recursiva, reglas, apartado 5).

- R-009 · media simple del precio de la semana anterior de los productos del departamento que ya tenían precio cuatro semanas antes. Lo usan: `precio_medio_semana_anterior`.
- R-014 · cuántos productos del departamento tenían precio la semana anterior y ya lo tenían cuatro semanas antes. Lo usan: `productos_con_precio_semana_anterior`.
- R-012 y R-013 · retardos de 1 a 7, 14, 21 y 28 días y medias de 7 y 28 días del objetivo de la serie, unidades o dólares según el modelo. Lo usan: `<obj>_lag_1`, `<obj>_lag_2`, `<obj>_lag_3`, `<obj>_lag_4`, `<obj>_lag_5`, `<obj>_lag_6`, `<obj>_lag_7`, `<obj>_lag_14`, `<obj>_lag_21`, `<obj>_lag_28`, `<obj>_media_7`, `<obj>_media_28`.

### Aprende

Van dentro del Pipeline, con fit en el entrenamiento.

- R-015 · la lista de eventos se saca de los días de entrenamiento. Lo usan: `evento_<nombre>`.
- R-011 · el preprocesador codifica o escala la finalista. Lo usan: `store_id`, `dept_id`, `weekday`, `month`, `precio_medio_semana_anterior`, `productos_con_precio_semana_anterior`, `dia_del_mes`, `<obj>_lag_1`, `<obj>_lag_2`, `<obj>_lag_3`, `<obj>_lag_4`, `<obj>_lag_5`, `<obj>_lag_6`, `<obj>_lag_7`, `<obj>_lag_14`, `<obj>_lag_21`, `<obj>_lag_28`, `<obj>_media_7`, `<obj>_media_28`.
- R-020 · el ganador se ajusta con las filas del entrenamiento, con la receta fija. Lo usan: todas las finalistas.

## La cadena de cada finalista

Cada cadena va en el orden en que se aplica, del origen al modelo. Entre paréntesis, la clase de cada paso: Q quita filas, N no aprende, H necesita otras filas y A aprende. Las cadenas de dólares son iguales con la ficha R-013 en lugar de R-012.

| Finalista | Cadena |
|---|---|
| `store_id` | T-001 (N) · R-004 (N) · R-010 (Q) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `dept_id` | T-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `weekday` | T-003 (N) · R-004 (N) · R-010 (Q) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `month` | T-003 (N) · R-004 (N) · R-010 (Q) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `snap` | R-002 (N) · R-008 (N) · R-004 (N) · R-010 (Q) · R-017 (Q) · R-011 (N) · R-018 (N) · R-020 (A) |
| `evento_<nombre>` | T-003 (N) · R-004 (N) · R-010 (Q) · R-015 (A) · R-015 (N) · R-017 (Q) · R-011 (N) · R-018 (N) · R-020 (A) |
| `precio_medio_semana_anterior` | T-001 (N) · R-001 (N) · T-003 (N) · R-007 (N) · R-004 (N) · R-009 (H) · R-010 (Q) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `productos_con_precio_semana_anterior` | T-001 (N) · R-001 (N) · T-003 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-014 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `dia_del_mes` | R-001 (N) · R-004 (N) · R-010 (Q) · R-016 (N) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_1` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_2` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_3` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_4` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_5` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_6` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_7` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_14` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_21` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_lag_28` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_media_7` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |
| `<obj>_media_28` | T-001 (N) · R-001 (N) · R-007 (N) · R-004 (N) · R-010 (Q) · R-012 (H) · R-017 (Q) · R-011 (A) · R-018 (N) · R-020 (A) |

## La previsión día a día

Las unidades se prevén a 10 días y los dólares a 28, siempre desde el último día con venta conocida. Cada día del horizonte se prevé con lo previsto para los anteriores.

- **Historia mínima.** Cada previsión necesita la venta de la serie en su objetivo durante los 28 días que acaban en el origen, porque el retardo y la media más largos miran 28 días atrás.
- **Precios.** Hacen falta los precios de cada producto desde 4 semanas antes de la semana anterior al primer día previsto hasta la semana anterior al último; con menos, un producto que ya se vendía contaría como nuevo (reglas, apartado 5, «El precio»).
- **Calendario.** Hacen falta los días a prever con su día de la semana, mes, fecha, eventos, días SNAP de cada estado y semana de Walmart, más la semana anterior a la del primer día.
- **Lo que se prevé.** El objetivo de los días a prever llega vacío, nunca cero: un cero de relleno no se distingue de una venta de cero.
- **Cómo se prevé.** Se prevé día a día, desde el día siguiente al origen hasta el último del horizonte. Los retardos y las medias de cada día se calculan con la tabla de historia que ya lleva lo previsto.
- **Unión.** Cada previsión se escribe en la historia uniendo por store_id, dept_id y fecha, nunca por posición; se comprueba que ningún día a prever queda sin previsión.
- **Acotar.** La previsión se acota en cero, antes de escribir la previsión en la historia (reglas, apartado 6).
- **Redondeo.** En unidades, al entero, con la mitad hacia arriba, solo al medir y en la salida; la historia guarda lo previsto sin redondear. Los dólares no se redondean.
- **Un modelo.** Hay uno para las 70 combinaciones de departamento y tienda, no uno por serie (planteamientos §2, decisión 6).
- **El 25 de diciembre.** Entra en la historia con lo previsto, como cualquier día (matriz); al reentrenar entra en el ajuste.
- **Series sin historia.** Una serie sin 28 días de historia sale con la previsión vacía y su motivo; no se quita.
- **Nombre de la previsión.** La columna de la previsión no se llama como el objetivo.

## Lo que el registro dice distinto de lo esperado

La petición esperaba que solo aprendiera el modelo y que solo quitaran filas los primeros 35 días. El registro dice otra cosa en estos pasos. Manda el registro:

- R-010 · el entrenamiento son las filas de la construcción, hasta el 22/05/2014; al reentrenar, la tabla que se pasa marca el corte: es «quita filas»; la petición no lo nombraba.
- R-011 · el preprocesador codifica y escala las finalistas con lo que aprende del entrenamiento: es «aprende»; la petición no lo nombraba.
- R-015 · la lista de eventos se saca de los días de entrenamiento: es «aprende»; la petición esperaba «no aprende».

## Lo que ya existe para la parte 2

Estos módulos ya están en disco. La parte 2 los revisa contra este contrato antes de escribir nada nuevo:

- `scripts/variables_prevision.py`;
- `scripts/preparacion_prevision.py`;
- `scripts/prevision_recursiva.py`.

## Datos personales

No existe `config/fuentes/proteccion-datos.json`: los datos no pasaron por la protección. Las tablas son ventas por departamento y tienda. El contrato no usa ninguna columna sobre personas.

## Límites

- La ficha R-018 sigue diciendo que la cuestión de los eventos está abierta, porque una ficha no se reescribe. El responsable del caso la resolvió el 24/11/2026 (reglas, apartado 7): lo recoge la ficha R-019 y el ganador no usa event_name_1 ni event_name_2.
- El preprocesador del desarrollo se ajustó con las ramas de event_name_1 y event_name_2, cuyas columnas después no entran en el modelo. El código de producción no las lleva: sin ellas, el primer reentreno da las previsiones de la validación fila a fila, con la tolerancia de 1e-12. Cada rama aprende solo de su columna.
- El precio de los días a prever se da por conocido, también dentro del horizonte (reglas, apartado 5, D9; supuesto).
- La historia de precios de cuatro semanas vale porque un producto no tiene huecos de precio (reglas, apartado 5). Si llegara uno con huecos, la cuenta cambiaría.
- El lote de producción es el año guardado, que se abrió después de aprobar este contrato (petición 28). Lo que se vio en él no cambia el contrato.
- La ficha del contrato está en el registro: R-021.

## La aprobación

El responsable del caso aprobó el contrato el 25/11/2026 con las palabras «Apruebo el contrato». Su ficha es la R-021 del registro de transformaciones. Con ella empieza la parte 2: el Pipeline, el reentreno y la ejecución diaria.
