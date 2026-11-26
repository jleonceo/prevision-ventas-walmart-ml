---
titulo: Datos necesarios del caso 69 · la venta, los precios y el calendario del concurso M5, qué cubren de cada pregunta y qué falta
estado: escrito el 21/11/2026 en el paso 2, con la prueba final ya apartada; aprobado por el responsable del caso el 21/11/2026 («Apruebo el paso 2»)
fecha_documento: 2026-11-21
dueno: el responsable del caso (decide) · el equipo de análisis (redacta)
fuente: `../negocio/00_briefing.md`; `../negocio/01_ficha_del_caso.md`; `../negocio/reglas-negocio.md`; `M5_guia_de_participantes_2020.docx`; `datasets_casos/69_prevision_ventas_walmart/00_LEEME.md` y `manifiesto_entrega_21112026.txt`
---

# Datos necesarios

## 1. Entidades y datos de cada una

- **Producto:** su código, su departamento y su categoría. Del recorte, 500 productos. No se sabe su marca, su
  proveedor ni si estaba en el estante.
- **Tienda:** su código y su estado. No se sabe su tamaño, cuándo abrió ni si tuvo obras.
- **Día:** la fecha, su semana de Walmart, el día de la semana, hasta dos eventos con su tipo y si ese día se cobra la
  ayuda alimentaria (SNAP) en cada estado.
- **Semana:** el precio de cada producto en cada tienda, la media de sus siete días.

## 2. Las tablas

- **La venta** (`sales_train_evaluation.csv`): una fila por producto y tienda (5.000 filas) y una columna por día con las
  unidades vendidas.
- **Los precios** (`sell_prices.csv`): una fila por producto, tienda y semana con su precio. Una semana sin fila es una
  semana en que el producto no se vendió en esa tienda (guía del concurso).
- **El calendario** (`calendar.csv`): una fila por día, del 29/01/2011 al 19/06/2016.

Se usan en este orden: la venta se une al calendario por el día y después a los precios por la semana, el producto y la
tienda. La venta y los precios no se pueden unir directamente, porque la venta no trae la semana.

## 3. Historial

En el caso, del 29/01/2011 al 22/05/2015: 1.575 días, que son la construcción (1.210) y la validación (365) de las
reglas, apartado 5. La **prueba final**, del 23/05/2015 al 22/05/2016, está apartada fuera del caso desde el 21/11/2026 y no se
mira hasta el final. El calendario va entero, porque no trae ventas y los festivos se conocen de antemano.

## 4. Fuentes internas

Ninguna: el caso no tiene acceso a sistemas de Walmart. Todo sale del concurso.

## 5. Fuentes externas

- El concurso M5 Forecasting de Kaggle: los tres ficheros, recortados a 500 productos (`datasets_casos/69_prevision_ventas_walmart/00_LEEME.md`).
- La guía de participantes del concurso (`M5_guia_de_participantes_2020.docx`), que define cada columna.

## 6. Datos personales

No hay. Los datos son de productos, tiendas, precios y calendario (reglas, apartado 9).

## 7. Cobertura de las preguntas

Cada pregunta de la ficha, con lo que la mueve según el negocio y la columna que lo cubre.

| Pregunta | Lo que la mueve, según el negocio | Lo cubre | Si falta |
|---|---|---|---|
| 1 · Cuánto venderá cada departamento en cada tienda | la venta de los días anteriores | las unidades de cada día | — |
| 1 | el día de la semana | el día de la semana del calendario | — |
| 1 | festivos y eventos | los dos eventos del día, con su tipo | — |
| 1 | el cobro de la ayuda alimentaria | SNAP por estado | — |
| 1 | el precio | el precio de cada semana | — |
| 1 | las promociones | falta: el precio casi no cambia y no hay marca de promoción | no se puede pedir: el dataset es público y cerrado |
| 1 | si había producto en el estante | falta: no hay existencias | no se puede pedir |
| 1 | el tiempo y la competencia | falta | no se puede pedir; se podría traer el tiempo de fuera, pero no se trae |
| 1 | la venta en dólares | unidades por precio de cada producto, sumado | — |
| 2 · Si se equivoca menos que las tres reglas | la venta de los días anteriores al origen | las unidades de cada día | — |
| 3 · Totales de tienda y de categoría | a qué departamento, categoría, tienda y estado pertenece cada producto | las columnas de identidad de la venta | — |
| 4 · Qué días cambia la venta | festivos, SNAP, día de la semana y precio | los mismos que en la pregunta 1 | los mismos límites: sin promociones ni existencias |

**Lo que la granularidad no deja saber:** de cada producto se sabe la venta de cada día, pero el precio solo por semana.
Un cambio de precio a mitad de semana no se ve. Un día con cero ventas no dice si faltó el producto.

## 8. Lo que entra en el caso

En `data/raw/`, marcados de solo lectura el 21/11/2026:
- la venta, del 29/01/2011 al 22/05/2015;
- los precios, hasta la semana que acaba el 22/05/2015;
- el calendario, entero.

Fuera del caso, en `datasets_casos/69_prevision_ventas_walmart/reservado/`: los tres ficheros enteros (`completo/`) y la
prueba final (`prueba_final/`). Entran en el caso solo en la prueba final, copiados por la persona responsable. Las
huellas están en `manifiesto_entrega_21112026.txt`.

La licencia del concurso prohíbe redistribuir los datos: ningún fichero de `data/raw/` se publica.
