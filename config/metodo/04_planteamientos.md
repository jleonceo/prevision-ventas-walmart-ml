---
titulo: Planteamientos · con qué se compara la previsión de cada departamento en cada tienda
estado: decisiones de método aprobadas por el responsable del caso el 24/11/2026; ganador y veredicto, el 25/11/2026
fecha_documento: 2026-11-21
fuentes: `../negocio/reglas-negocio.md` §7; Makridakis, Spiliotis y Assimakopoulos, «The M5 Accuracy competition: Results, findings and conclusions» (2022), apéndice B
---

# Planteamientos · Previsión de ventas de Walmart

## Planteamientos establecidos

### 1 · El suavizado exponencial como referencia del modelo

- Para qué: saber si hace falta un modelo de aprendizaje automático o basta un método estadístico sencillo. Ganar a
  las tres reglas de la empresa no lo demuestra.
- Qué es: una media de la venta pasada en la que los días recientes pesan más que los antiguos, con el ritmo de la
  semana. Solo usa la historia de la propia serie: ni festivos, ni días SNAP, ni precio.
- Por qué: en el concurso, en el nivel de tienda y departamento, el suavizado exponencial falló un 18,0 % menos que
  repetir la semana anterior. El ganador falló un 21,3 % menos que el suavizado (apéndice B del artículo de resultados).
- Cómo se mide: en cada una de las 70 series, en unidades y en dólares, con los mismos cortes, días y horizonte que
  el modelo y las tres reglas. Se dan su error y su sesgo al lado de los de las reglas.
- Qué decide: no cambia la regla de ganar de las reglas de negocio, apartado 7, que se mide solo frente a las tres reglas. Si el modelo
  gana a las reglas pero no al suavizado, el informe lo dice: a la empresa le bastaría el método sencillo.
- Diferencia con el concurso: allí se ajustó a cada producto en cada tienda y se sumó hacia arriba. Aquí se ajusta
  directamente a cada departamento en cada tienda, que es lo que se prevé.
- Cómo se elige su forma: en el apartado 2, decisión 8.

### 2 · Las decisiones de método del modelado

Aprobadas por el responsable del caso el 24/11/2026 («Sí, apruébalo»).

1. **Orígenes de la validación:** 13, cada 28 días, el primero el 22/05/2014 (último día de la construcción) y el
   último el 23/04/2015. El modelo gana en orígenes si se equivoca menos en al menos 10 (el 75 % de 13, hacia arriba).
   Con 28 días de horizonte en dólares, cada día de la validación se prevé una sola vez, del 23/05/2014 al 21/05/2015.
2. **El modelo se ajusta una vez**, con la construcción. Desde cada origen prevé con la venta real hasta ese día y con
   la previsión recursiva después (reglas de negocio, apartado 5, D7). No se reajusta con la validación: se abre una vez, con el ganador.
3. **El intervalo del 95 % de la ventaja:** remuestreo de las 70 combinaciones de departamento y tienda enteras, con
   todos sus días y orígenes, 1.000 veces y con semilla; percentiles 2,5 y 97,5. La ventaja es el error de la regla que
   menos falla menos el del modelo, sobre todo lo remuestreado.
4. **Ningún horizonte cruza** de la validación a la prueba final: la última previsión acaba el 21/05/2015.
5. **El error de cada mes:** cada día previsto cuenta en su mes natural. En dólares cada día sale una vez; en unidades,
   los 10 días previstos de cada tramo de 28. Los meses parciales no se comparan (reglas de negocio, apartado 5).
6. **Un modelo para las 70 combinaciones**, uno en unidades y otro en dólares, con la tienda y el departamento como
   variables. Es el que se probó en el reconocimiento de los datos. Uno por serie multiplicaría por 70 el coste de la
   búsqueda.
7. **Historia que piden las variables:** retardos de 1 a 7, 14, 21 y 28 días y medias de 7 y 28 días, siempre con lo
   anterior al día previsto. Quedan fuera los primeros 35 días de cada serie, que se cuentan en el registro de
   transformaciones: 29 por los retardos y 6 más porque el precio medio de la semana anterior está vacío en las cinco
   primeras semanas. Con 35 no queda ningún vacío en el entrenamiento ni en la validación. La llegada de productos nuevos
   entra como candidata en la matriz: los productos del departamento con precio la semana anterior que ya tenían precio
   cuatro semanas antes, la regla del precio medio.
8. **El suavizado exponencial:** `statsmodels` 0.15, `ExponentialSmoothing` con estacionalidad semanal aditiva y sin
   tendencia, ajustado en cada serie con su historia hasta cada origen. La forma multiplicativa no admite los ceros de
   HOBBIES_2.

**Algoritmos y búsqueda (24/11/2026, «Sí, tal cual»):** HistGradientBoosting y Ridge, sin el bosque; nivel equilibrado
(15 candidatos por algoritmo, Ridge en rejilla entera de 13, y 5 cortes por fecha); cada candidato se mide con la
previsión recursiva desde el origen de cada corte, con el error de las reglas de negocio, apartado 6; los 25 de diciembre entran en el ajuste
y salen de la medida. Cifras en `informes/modelo_minimo.json`.

**Ganador (25/11/2026, «Apruebo el ganador»):** HistGradientBoosting en los dos objetivos, con la
receta de `informes/busqueda.json`: `learning_rate` 0,1, sin límite de profundidad, `max_iter` 500, `min_samples_leaf`
205, sin regularización, semilla 42 y 82 columnas. En los cortes del entrenamiento falla 15,6 en unidades y 17,4 en
dólares por cada 100 vendidos, en recursivo; la regla que menos falla, 18,0 y 19,6. Con esto se abre la validación, una
vez (decisiones 1 a 5 y 8 de este apartado).

**Veredicto de la validación (25/11/2026, «Sí, apruebo el veredicto»):** el modelo gana en los dos objetivos
(`informes/validacion.json`). Falla menos que la regla que menos falla en 12 de los 13 orígenes, con una ventaja de
+2,28 puntos en unidades (intervalo +1,23 a +3,49) y +2,06 en dólares (+1,02 a +3,32). Se recomienda el modelo en todos
los departamentos salvo HOBBIES_2, donde va la media de los últimos 28 días en los dos objetivos, y HOUSEHOLD_2 en
dólares, donde va la media del mismo día de las 4 semanas anteriores (por 0,02 puntos).

### 3 · Lo fijado para la exploración y las variables

- SNAP se compara solo dentro de los días 1 a 15 del mes: la venta de los días con SNAP del estado de la tienda
  frente a la de los días sin SNAP de esa misma quincena. Los días SNAP caen siempre en esa quincena (400 por estado en
  la construcción), así que compararlos con el resto del mes mezclaría SNAP con principio de mes.
- Los festivos y demás eventos dan su efecto por departamento, sumando las 10 tiendas, con un mínimo de 30 días de
  serie por evento. El día normal es la media del mismo día de la semana en las cuatro semanas anteriores sin evento.
- Las dos cifras son cocientes de medias de unidades por día de serie, sin los días fuera del error (reglas de negocio, apartado 6).
- El día de la semana se mide como la venta media del día más fuerte entre la del más flojo, por departamento.
- El mes se mide como la venta media de cada mes completo entre la media de los meses completos, por categoría.
- El precio solo se describe: la correlación de Spearman entre el precio medio de la semana anterior y las unidades
  de la semana, por serie.
- El precio que entra al modelo es el de la semana anterior, nunca el de la semana prevista. Una semana sin precio es
  una semana sin venta, así que el precio medio de la semana prevista diría qué productos se venden en ella.
- El precio medio de un departamento es la media simple de los precios de sus productos con precio esa semana,
  contando solo los que ya tenían precio cuatro semanas antes. Detalle en las reglas de transformación, apartado 1.
