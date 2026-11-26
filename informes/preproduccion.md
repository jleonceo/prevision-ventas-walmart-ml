# La preproducción del caso 69

Fecha de los datos: 2015-05-22. Sale de `informes/preproduccion.json`, generado por `scripts/19_contrato_produccion.py` el 25/11/2026. Estado: OK.

El código de producción está escrito y sus 17 comprobaciones salen en verde. También pasó el lote, que es el año guardado. El modelo en uso es `modelos/reentrenos/2015-05-22`: lo aprobó el responsable del caso, 25/11/2026: «Sí, apruebo el reentrenado», con la prueba final delante (informes/prueba_final.json).

## Las finalistas y su cadena

- **Unidades.** El modelo usa 82 columnas, que salen de 21 finalistas; las primeras son `store_id`, `dept_id`, `weekday`, `month`.
- **Dólares.** El modelo usa 82 columnas, que salen de 21 finalistas; las primeras son `store_id`, `dept_id`, `weekday`, `month`.

Cada finalista tiene su cadena completa en el registro de transformaciones, desde el origen hasta el modelo, con la clase de cada paso. Las cadenas están en `config/modelo/contrato_produccion.md`.

## El contrato

El responsable del caso aprobó el contrato el 25/11/2026 con las palabras «Apruebo el contrato»; su ficha es la R-021 del registro.
Los dos modelos son HistGradientBoosting con la receta fija de la búsqueda, semilla 42. En 3 pasos el registro dice algo distinto de lo que esperaba la petición; manda el registro.

## Qué hace cada script

- `scripts/produccion_prevision.py`: las piezas del Pipeline, los pasos que no aprenden y los que necesitan otras filas, sin ejecutar nada al importarse.
- `produccion/reentrenar.py`: rehace los dos modelos con la receta fija del contrato, quita contadas las filas sin historia y los guarda con su ficha en una carpeta nueva; si la carpeta ya existe, para sin tocarla.
- `produccion/ejecutar.py`: prevé cada serie desde el último día con venta, día a día, sin quitar ninguna fila; la que no se puede prever sale vacía con su motivo.
- `tests/comprobar_produccion_por_otro_camino.py`: rehace las previsiones sin cargar el modelo guardado ni importar el código de producción y las compara fila a fila.
- `produccion/configuracion.json`: las rutas, los horizontes, la semilla, la tolerancia y el modelo en uso, que decide el responsable del caso.

## El reentreno

El primer reentreno está en `modelos/reentrenos/2026-11-25`. Se ajustó con 82.250 filas de la construcción, las mismas que el modelado.
Da fila a fila las previsiones de la validación en sus 13 orígenes, con la tolerancia de 1e-12.

El reentrenado con un año más está en `modelos/reentrenos/2015-05-22`: se ajustó con 107.800 filas, construcción y validación juntas.

Los dos se midieron en la prueba final, con las mismas reglas que la validación. Cuando se midieron no había modelo en uso: el primer reentreno hizo su papel en la comparación.

| Objetivo | Modelo | Veredicto | Orígenes que gana | Ventaja | Error del modelo | Sesgo |
|---|---|---|---|---|---|---|
| Unidades | primer reentreno | no gana | 9 de 13 | 1,61 | 15,29 | 2,76 |
| Unidades | reentrenado | gana | 12 de 13 | 2,40 | 14,50 | 0,27 |
| Dólares | primer reentreno | gana | 12 de 13 | 1,15 | 17,46 | 0,24 |
| Dólares | reentrenado | gana | 13 de 13 | 2,41 | 16,21 | -0,50 |

La ventaja son los puntos de error que el modelo falla menos que la regla que menos falla en cada origen; el error y el sesgo van por cada 100 vendidos. Las cifras enteras están en `informes/prueba_final.json`.

## El lote

El lote es el año guardado. La ejecución diaria se lanzó 16 veces con el primer reentreno, una por origen, con la venta cortada en cada uno.
Había que prever 42.560 filas de serie y día y salieron 42.560. Ninguna quedó sin previsión.
Las salidas están en `data/processed/prueba_final/tal_como_esta`.

## La prueba por otro camino

Sobre los 13 orígenes de la validación, la prueba coincide con la tolerancia de 1e-12; sale en rojo con una previsión estropeada a propósito.
En el lote, 42.560 filas de 16 orígenes: coinciden todas; la previsión estropeada sale en rojo.
En el lote del reentrenado, 42.560 filas de 16 orígenes: coinciden todas; la previsión estropeada sale en rojo.

## Validaciones

- Cada columna del modelo sale de una finalista: en verde.
- Cada finalista tiene su cadena completa en el registro: en verde.
- Nada aprende antes de la partición: en verde.
- El contrato no tiene campos vacíos: en verde.
- El modelo recibe exactamente las columnas del contrato: en verde.
- La ejecución saca una fila por serie y día: en verde.
- El primer reentreno da las previsiones de la validación: en verde.
- La prueba por otro camino coincide en la validación y sale en rojo con la previsión estropeada: en verde.
- La ejecución no quita filas: en verde.
- El modelo solo se carga si cuadra su ficha: en verde.
- Con otra tabla el reentreno sale distinto: en verde.
- La ejecución para con la venta de otro día: en verde.
- Ninguna previsión sale vacía sin motivo ni negativa: en verde.
- La prueba por otro camino coincide en el lote y sale en rojo con la previsión estropeada: en verde.
- El lote saca tantas filas como había que prever: en verde.
- La prueba por otro camino coincide en el lote del reentrenado y sale en rojo con la previsión estropeada: en verde.
- El modelo en uso es uno de los medidos: en verde.

## Parámetros usados

- Retardos: 1, 2, 3, 4, 5, 6, 7, 14, 21, 28 (`informes/variables_modelo.json`).
- Ventanas de las medias: 7, 28 (`informes/variables_modelo.json`).
- Semanas previas con precio: 4 (`informes/variables_modelo.json`).
- Ficha de la preselección: R-018 (`informes/preseleccion.json`).
- Tolerancia de la prueba por otro camino: 1e-12 (los parámetros del método preproduccion).

## Datos personales

No existe `config/fuentes/proteccion-datos.json`: los datos no pasaron por la protección. Las tablas son ventas por departamento y tienda. Ni el contrato ni el código de producción usan columnas sobre personas.

## Límites

- El precio de los días a prever se da por conocido, también dentro del horizonte (reglas, apartado 5, D9). Es un supuesto.
- Los modelos guardados ejecutan código al abrirse: solo se cargan si cuadra su ficha.
- Las entradas de cada origen del lote se armaron fuera del caso y no se guardan; sus huellas están en el resumen del lote (`data/processed/prueba_final/tal_como_esta/resumen.json`).
- La prueba por otro camino se hizo sobre el lote de los dos modelos.
