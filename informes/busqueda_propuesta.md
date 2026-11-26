# Propuesta del ganador de la búsqueda · caso 69

Fecha de los datos: 2015-05-22. Sale de `informes/busqueda.json`, generado por `scripts/15_busqueda.py` el 2026-11-24. Estado: PARADO.

## Qué se propone

- **Unidades, a 10 días:** HistGradientBoosting. Falla 15,6 unidades por cada 100 vendidas de media en los cortes, previendo en recursivo. La regla que menos falla de media es la media del mismo día de las 4 semanas anteriores: falla 18,0.
- **Dólares, a 28 días:** HistGradientBoosting. Falla 17,4 dólares por cada 100 vendidos de media en los cortes, previendo en recursivo. La regla que menos falla de media es la media del mismo día de las 4 semanas anteriores: falla 19,6.

Cada propuesta espera la aprobación del responsable del caso. Hasta entonces la validación sigue cerrada. El estado del JSON es PARADO porque el ganador está en su puerta.

## La receta

| Objetivo | Algoritmo | Hiperparámetros buscados | Semilla | Columnas |
|---|---|---|---|---|
| unidades | HistGradientBoostingRegressor | l2_regularization = 0; learning_rate = 0.1; max_depth = None; max_iter = 500; min_samples_leaf = 205 | 42 | 82 |
| dolares | HistGradientBoostingRegressor | l2_regularization = 0; learning_rate = 0.1; max_depth = None; max_iter = 500; min_samples_leaf = 205 | 42 | 82 |

Las columnas son las de la preselección sin las de event_name_1 ni event_name_2. El preprocesador se ajusta con las filas de cada ajuste. La lista entera está en el JSON.

## Por qué ese algoritmo

- **Unidades:** HistGradientBoosting menos Ridge da -5,42 puntos de media corte a corte, con una desviación de 1,26. La media pasa de la desviación, así que gana el de menos error. Queda HistGradientBoosting.
- **Dólares:** HistGradientBoosting menos Ridge da -5,85 puntos de media corte a corte, con una desviación de 1,54. La media pasa de la desviación, así que gana el de menos error. Queda HistGradientBoosting.

## Ranking

Error por cada 100 vendidos, media de los cortes en recursivo. El entrenamiento se mide a un día en las filas del ajuste de cada corte.

| Objetivo | Algoritmo | Error | Desviación entre cortes | Sesgo | Entrenamiento | Cortes que gana |
|---|---|---|---|---|---|---|
| unidades | HistGradientBoosting | 15,64 | 0,74 | +0,66 | 13,65 | 4 de 5 |
| unidades | Ridge | 21,06 | 1,36 | -1,97 | 20,70 | 0 de 5 |
| dolares | HistGradientBoosting | 17,37 | 0,87 | +2,99 | 14,08 | 5 de 5 |
| dolares | Ridge | 23,23 | 1,42 | -5,59 | 20,67 | 1 de 5 |

«Cortes que gana» cuenta los cortes en que falla menos que la regla que menos falla en ese corte.

| Objetivo | Referencia | Error | Sesgo |
|---|---|---|---|
| unidades | el trivial (la mediana) | 73,69 | -45,66 |
| unidades | repetir la semana anterior | 22,53 | -0,46 |
| unidades | la media de los últimos 28 días | 21,00 | +0,03 |
| unidades | la media del mismo día de las 4 semanas anteriores | 17,96 | -0,36 |
| dolares | el trivial (la mediana) | 69,50 | -40,97 |
| dolares | repetir la semana anterior | 23,85 | -6,91 |
| dolares | la media de los últimos 28 días | 22,93 | -1,04 |
| dolares | la media del mismo día de las 4 semanas anteriores | 19,59 | -1,04 |

## Rejillas ampliadas

- unidades, HistGradientBoosting, l2_regularization (rango plano, lado alto): se probó 2.0.
- unidades, HistGradientBoosting, l2_regularization (borde y rango plano, lado bajo): no se amplía porque -1 queda por debajo del mínimo válido (0.0).
- unidades, HistGradientBoosting, learning_rate (borde y rango plano, lado alto): se probó 0.20000000000000004.
- unidades, HistGradientBoosting, learning_rate (rango plano, lado bajo): se probó 0.025000000000000005.
- unidades, HistGradientBoosting, max_depth (borde, lado alto): no se amplía porque «sin límite» ya es el valor más alto.
- unidades, HistGradientBoosting, max_iter (borde y rango plano, lado alto): se probó 1250.
- unidades, HistGradientBoosting, max_iter (rango plano, lado bajo): se probó 50.
- unidades, HistGradientBoosting, min_samples_leaf (rango plano, lado alto): se probó 3296.
- unidades, HistGradientBoosting, min_samples_leaf (borde y rango plano, lado bajo): se probó 51.
- dolares, HistGradientBoosting, l2_regularization (rango plano, lado alto): se probó 2.0.
- dolares, HistGradientBoosting, l2_regularization (borde y rango plano, lado bajo): no se amplía porque -1 queda por debajo del mínimo válido (0.0).
- dolares, HistGradientBoosting, learning_rate (borde y rango plano, lado alto): se probó 0.20000000000000004.
- dolares, HistGradientBoosting, learning_rate (rango plano, lado bajo): se probó 0.025000000000000005.
- dolares, HistGradientBoosting, max_depth (borde, lado alto): no se amplía porque «sin límite» ya es el valor más alto.
- dolares, HistGradientBoosting, max_iter (borde y rango plano, lado alto): se probó 1250.
- dolares, HistGradientBoosting, max_iter (rango plano, lado bajo): se probó 50.
- dolares, HistGradientBoosting, min_samples_leaf (rango plano, lado alto): se probó 3296.
- dolares, HistGradientBoosting, min_samples_leaf (borde y rango plano, lado bajo): se probó 51.
- dolares, Ridge, alpha (borde, lado bajo): se probó 26.009733754884916.
- Segunda búsqueda de HistGradientBoosting en unidades: mejora -0,06 de media con una desviación de 0,32. No se sostiene pliegue a pliegue: se queda el de la primera.
- Segunda búsqueda de HistGradientBoosting en dolares: mejora +0,10 de media con una desviación de 0,42. No se sostiene pliegue a pliegue: se queda el de la primera.
- Segunda búsqueda de Ridge en dolares: mejora -0,00 de media con una desviación de 0,07. No se sostiene pliegue a pliegue: se queda el de la primera.

## Qué variables pesan

Puntos de error que se pierden al barajar cada variable de origen, media de los cortes. Las cinco primeras de cada ganador:

| Objetivo | Variable | Importancia |
|---|---|---|
| unidades | unidades_media_7 | 28,84 |
| unidades | unidades_lag_1 | 13,87 |
| unidades | unidades_media_28 | 6,45 |
| unidades | weekday | 3,15 |
| unidades | unidades_lag_7 | 2,53 |
| dolares | dolares_media_7 | 21,80 |
| dolares | dolares_lag_1 | 8,56 |
| dolares | dolares_media_28 | 5,90 |
| dolares | dolares_lag_7 | 4,00 |
| dolares | weekday | 3,84 |

- **Unidades:** las dos primeras llevan el 66 % de la importancia positiva. Una regresión lineal con solo esas dos falla 21,8 de media. El ganador la supera pliegue a pliegue. En el último corte, con el objetivo barajado falla 81,0. Con la venta real puesta como variable falla 0,9. Las dos cifras dicen que la comprobación ve una fuga cuando la hay.
- **Dólares:** las dos primeras llevan el 56 % de la importancia positiva. Una regresión lineal con solo esas dos falla 25,3 de media. El ganador la supera pliegue a pliegue. En el último corte, con el objetivo barajado falla 70,5. Con la venta real puesta como variable falla 1,6. Las dos cifras dicen que la comprobación ve una fuga cuando la hay.

## Entrenamiento frente a validación cruzada

- **Unidades:** 13,65 en entrenamiento frente a 15,64 en recursivo. A un día con los retardos reales, 14,16.
- **Dólares:** 14,08 en entrenamiento frente a 17,37 en recursivo. A un día con los retardos reales, 15,55.

La distancia no tiene una vara fija (manual 19.3): se lee al lado de la del otro algoritmo, que está en el ranking.

## Límites

- Ninguna cifra mira la validación. Todas salen del entrenamiento, con los cortes del modelo mínimo.
- La importancia se mide a un día con los retardos reales: en la recursión los retardos salen de lo previsto y no se pueden barajar.
- Cuánto se amplía una rejilla no está escrito en el método. Se toma un paso más de su progresión y se prueba con el resto de la receta del mejor candidato.
- La desviación entre cortes divide por n − 1 (manual 3.6). El modelo mínimo dividía por n.
- El suavizado exponencial no se mide aquí: va con la validación.

## Lo que puede decidir el responsable del caso

- Aprobar el ganador de cada objetivo con su receta, para abrir la validación una vez.
- Pedir otra cosa antes de abrirla.
