---
titulo: El lote diario de la previsión del caso 69
estado: escrito el 25/11/2026 (petición 29); la tarea programada no está creada ni activada, lo decide el responsable del caso (puerta 6)
fecha_documento: 2026-11-25
dueno: el responsable del caso (decide) · el equipo de análisis (mantiene)
fuentes: `produccion/lote_diario.py`, `produccion/lote_diario.ps1`, `produccion/vuelta_atras.py`, `produccion/configuracion.json`, `informes/despliegue.json`, método `despliegue` (parte 1 y `programacion.md`)
---

# El lote diario de la previsión

El lote prevé cada día, sin nadie delante, las unidades a 10 días y los dólares a 28 de las 70 series de departamento y tienda. Usa el modelo en uso de la configuración, hoy `modelos/reentrenos/2015-05-22`. Se lanza con una sola orden y deja la salida del día en su carpeta. Si algo no cuadra, para con un mensaje claro y no escribe ninguna previsión.

## Cómo se lanza

La orden es la misma a mano que desde una tarea programada. Funciona desde cualquier carpeta:

```
powershell.exe -NoProfile -File <carpeta del repositorio>\produccion\lote_diario.ps1
```

El envoltorio lee `produccion/configuracion.json` (apartado `lote_diario`), lanza el lote con el Python del entorno del caso y guarda todo lo que imprime. No necesita argumentos. Admite tres, que pasa tal cual al lote:

- `--repetir` vuelve a prever a propósito desde un día que ya se previó;
- `--origen AAAA-MM-DD` dice qué día tiene que ser ayer; si la venta no llega hasta él, el lote para;
- `--fecha AAAA-MM-DD` cambia el nombre de la carpeta de salida, que por defecto es la fecha de hoy.

## Qué hace y qué deja

El lote toma como origen el último día con venta, que es el día de ayer según los datos. Antes de prever comprueba cuatro cosas:

- que ese día llegó entero, con dato en todos los productos;
- que la venta avanzó respecto de la última ejecución buena del registro;
- que el origen no cae antes del último día con que se entrenó el modelo en uso;
- que el intérprete es el del entorno del caso.

Después llama a `produccion/ejecutar.py`, el mismo código que se probó en la preproducción, sin copiar nada de su lógica. Al acabar deja:

- `data/predicciones/AAAA-MM-DD/`, con `previsiones.parquet` (una fila por serie y día previsto) y `resumen.json` (filas, huellas de las entradas, modelo y comprobaciones);
- `data/predicciones/_archivo/`, donde pasa la salida anterior del mismo día antes de pisarla;
- `data/predicciones/registro_lote_diario.jsonl`, con una línea por ejecución: inicio, fin, duración, estado, origen y mensaje;
- `data/predicciones/_registros/lote_diario_AAAAMMDD_HHMMSS.log`, con lo que imprimió el lote, errores incluidos.

Las entradas son la venta y el calendario de `data/raw/`. Los precios llegan de `data/raw/` y de `data/raw/reserva/`, porque el precio de los días a prever se da por conocido (reglas, apartado 5, D9).

## Qué hace si falla

El envoltorio sale con el código del lote, que es lo que vería la tarea programada:

- **0**: la previsión del día quedó guardada con sus comprobaciones en verde;
- **1**: el lote paró porque la entrada o una comprobación no lo permiten, por ejemplo cuando la venta no llega hasta ayer;
- **2**: hubo un fallo técnico, con su traza en el registro del envoltorio.

En los casos 1 y 2 no se escribe ninguna previsión y la salida que hubiera de ese día sigue intacta. El motivo está en la última línea del registro y en el `.log` de esa ejecución. Si la venta nueva no llegó, basta con esperar a que llegue y volver a lanzarlo.

## La vuelta atrás

Hay dos vueltas atrás, cada una con su orden. Ninguna borra nada.

Para volver a otro modelo, la configuración pasa a nombrarlo y guarda antes una copia de la de ahora en `produccion/_archivo/`. La orden comprueba primero que la carpeta trae los dos modelos con su ficha y que cada fichero es el de su ficha. Cambiar el modelo en uso lo decide el responsable del caso:

```
python -W error produccion/vuelta_atras.py modelo --a modelos/reentrenos/2026-11-25 --decide "el responsable del caso, DD/MM/AAAA: «...» (referencia de la decisión)"
```

Para deshacer la salida de un día, su carpeta pasa a `data/predicciones/_archivo/`. Con `--restaurar`, una ejecución archivada de ese mismo día vuelve a ser la suya:

```
python -W error produccion/vuelta_atras.py salida --fecha AAAA-MM-DD [--restaurar AAAA-MM-DD_<hora>]
```

Las dos órdenes se lanzan con el Python del entorno del caso. Las dos se ensayaron sobre una copia de trabajo, nunca sobre la configuración real. El resultado del ensayo está en `informes/despliegue.json`, apartado `vuelta_atras`.

## Límites

- La tarea programada no existe. Crearla, su hora y la cuenta con que se ejecuta los decide el responsable del caso (puerta 6). Lanzar el envoltorio a mano prueba la acción, no el desencadenador: la tarea estará probada cuando su ejecución aparezca en el historial a la hora programada.
- El aviso por ausencia no está montado. Falta decidir cuántas ejecuciones se esperan por semana y quién lee los avisos.
- Los datos del caso no cambian. Con `data/raw/` como está, el lote de hoy prevé desde el 22/05/2015; mientras no llegue un día nuevo, cada lanzamiento siguiente para porque la venta no avanza, salvo con `--repetir`.
- El servidor de producción es una carpeta del caso. Es una simplificación, no lo ideal.
- La previsión de los próximos días del cuadro de mando, del 23/05/2016 al 19/06/2016, se hizo una sola vez con `produccion/lote_prueba_final.py --origen 2016-05-22`, no con el lote diario; está en `data/predicciones/desde_2016-05-22/`.

## Lo que puede decidir el responsable del caso

- Crear la tarea diaria en el Programador de tareas, a qué hora y con dos opciones: ejecutarse aunque no haya sesión iniciada y ejecutarse en cuanto se pueda si se perdió un inicio.
- Quién lee los avisos por error y por ausencia.
- Cuántas ejecuciones se esperan por semana, que fija el aviso por ausencia.
