---
titulo: Ficha del caso 69, Walmart planifica pedidos y personal de cada departamento sin una previsión medida de lo que va a vender
estado: borrador del 20/11/2026 con «El problema» (paso 0), «Dónde está la empresa» (paso A), «Por qué es buen momento» (paso B) y KPIs, objetivo, palancas, cifra de valor y preguntas semilla (paso C). A, B y C aprobados por el responsable del caso el 20/11/2026 («Vale, los apruebo»). «El problema», aprobado por el responsable del caso en el paso 1 el 21/11/2026 («Sí, apruebo»); sus cifras, revisadas con las tablas corregidas el 24/11/2026; las de la pregunta 4, pasadas a las del exploratorio el 24/11/2026
fecha_documento: 2026-11-20
dueno: el responsable del caso (decide) · el equipo de análisis (mantiene)
fuente: `00_briefing.md`; el registro del caso; mini workflow de forecasting, una plantilla común
---

# Ficha del caso 69

## El problema

Escrita en el paso 0 con el briefing y completada el 21/11/2026 en el paso 1 con las cifras del reconocimiento,
provisionales hasta limpiar los datos. Aprobada por el responsable del caso el 21/11/2026 («Sí, apruebo»).

Cada tienda pide mercancía y pone personal según lo que cree que va a vender cada departamento (briefing, supuesto). Si
se queda corta, el estante se vacía y se pierde la venta. Si se pasa, el dinero queda parado en el almacén. El caso sirve
a **menos gasto y más ingreso a la vez**: menos mercancía parada y menos ventas perdidas, con una previsión diaria de cada
departamento en cada tienda que se equivoque menos que las reglas de hoy.

| Pregunta de partida (briefing) | Método | Lo que exige a los datos |
|---|---|---|
| 1. Cuántas unidades y dólares venderá cada departamento en cada tienda cada día | dos previsiones por separado, una en unidades y otra en dólares; la venta real en dólares se construye con las unidades por el precio de cada producto, sumado. 70 series y 140 previsiones, con previsión recursiva día a día (el responsable del caso, 20/11: «Sí, las dos previsiones»). Si se entrena un modelo por serie o uno para las 70 a la vez se fija en los planteamientos (D7) | venta diaria sin huecos por departamento y tienda; precio de cada producto por semana; calendario con festivos y días SNAP |
| 2. Si se equivoca menos que las tres reglas sin modelo | validación cruzada en el tiempo dentro de la construcción, validación de un año y prueba final de un año, con la regla de ganar escrita antes de medir | partición por fecha; las tres reglas calculadas con los mismos días |
| 3. Cuánto venderá cada tienda y cada categoría al sumar | suma de abajo arriba de las 70 previsiones | cada producto con su departamento y su categoría; cada tienda con su estado |
| 4. Qué días cambia la venta de lo habitual | efecto de festivos, días SNAP, día de la semana, época del año y precio sobre la venta, como variables del modelo | festivos con su tipo; SNAP por estado; el mes; precio medio del departamento por semana |

**Lo que condiciona las respuestas:**
- El dataset es un recorte de 500 de los 3.049 productos del concurso. Los totales del caso no son los totales reales de
  Walmart.
- Los datos traen ventas, no existencias. Un día con venta cero no dice si nadie compró o si no había producto.
- Los precios casi no cambian: mediana de 2 cambios por serie en cinco años. Las promociones no se pueden
  estudiar.
- El horizonte sale del uso de cada previsión: unidades a 10 días, para el pedido semanal y lo que tarda en llegar;
  dólares a 28 días, para el mes de finanzas (el responsable del caso, 20/11/2026).

**Si cada pregunta se puede contestar.** Con las cifras del reconocimiento, solo con la construcción. La
prueba rápida usó 12 cortes del último año de la construcción y un modelo para las 70 series a la vez. Revisadas el
24/11/2026 con las tablas corregidas: la corrección no cambió ningún valor de los datos, así que las cifras
salen iguales. La prueba rápida ya dejaba fuera el 25 de diciembre. Lo que cambia es cómo se lee la cifra del modelo,
porque usaba el precio de la semana prevista.

| Pregunta | Tabla y objetivo | Veredicto | La cifra que lo sostiene |
|---|---|---|---|
| 1 | una fila por departamento, tienda y día, con unidades, dólares, calendario y precio; el objetivo, la venta de cada día del horizonte | **se contesta** | sin precio, el modelo rápido falla 16,2 unidades por cada 100 a 10 días y 17,8 dólares por cada 100 a 28 días. Es la cifra sin ninguna fuga: con el precio de la semana prevista, que deja ver qué productos se venden, salía 16,0 y 17,4 |
| 2 | la misma tabla, con las tres reglas en los mismos cortes | **se contesta**; si la ventaja queda demostrada, solo lo dice la validación con su intervalo | el modelo rápido gana a la regla que menos falla en 10 de 12 cortes en unidades y en 12 de 12 en dólares, también sin precio. La ventaja media, 1,5 y 2,1 puntos, se midió con el precio de la semana prevista; sin precio no se midió |
| 3 | la suma de las 70 previsiones por tienda, categoría, estado y cadena | **se contesta** | los 500 productos están en las 10 tiendas con su departamento y su categoría; las claves cruzan sin huecos |
| 4 | la misma tabla, con festivos, SNAP, día de la semana, mes y precio | **se contesta** para festivos, SNAP, día de la semana y época del año; el precio, **solo de forma descriptiva** | Cifras del exploratorio, por departamento y con las fórmulas de los planteamientos. Acción de Gracias baja la venta de todos los departamentos, del 9,1 % al 72,2 %; Año Nuevo, del 20,0 % al 77,8 %. SNAP sube la alimentación del 4,3 % al 24,0 % (FOODS_2) y apenas mueve ocio y hogar. El día más fuerte vende de 1,22 a 1,51 veces el más flojo, siempre en fin de semana. El mes pesa menos: ningún mes se aparta más de un 9 % de la media (mayo en hogar, −8,9 %). Spearman entre precio y unidades, de −0,38 a 0,24 en mediana por departamento: describe, no mide un efecto. El 41,1 % de los productos-tienda no cambia nunca de precio y no hay promociones. El responsable del caso dio por normales las cifras que pasan de «Lo esperable» (24/11/2026) |

**Cómo se entrena, igual que se usará.** Cada día, con lo que se sabe la víspera, día a día hacia delante (previsión
recursiva). El precio que entra al modelo es el de la semana anterior: una semana sin precio es una semana sin venta
(guía del concurso), así que el precio medio de la semana prevista diría qué productos se vendieron en ella. Medido:
con el precio de la semana anterior, el modelo rápido falla lo mismo (15,9 y 17,5); sin precio, algo más (16,2 y 17,8),
y gana en los mismos cortes. Desde el 24/11/2026, en ese precio medio solo cuentan los productos que ya tenían precio
cuatro semanas antes: contados desde su entrada, avisaban de su primera venta dentro del horizonte (reglas, apartado 5).
Las cuatro cifras de la prueba rápida se midieron antes, con todos los productos.

**Las seis comprobaciones de un modelo que decide:**
- **La decisión:** la previsión informa y decide una persona (compras, jefes de tienda y finanzas). Importan los dos
  errores: quedarse corto vacía estantes y pasarse deja mercancía parada. Por eso el error va siempre con el sesgo.
- **La valoración:** la forma es «informar sin decisión automática». La cifra que mide valor es el error en dólares
  frente a la regla que menos falla, con el sesgo al lado. Los datos no traen coste, margen ni existencias (reglas, apartado 6):
  no hay importes que fijar. Forma decidida por el responsable del caso el 21/11/2026 («Sí, esa forma»).
- **La ventana del objetivo:** viene dada, las unidades vendidas cada día. No hay que construirla.
- **El calendario de los datos:** la venta de ayer está disponible al prever (supuesto, reglas, apartado 5). No consta el retraso
  de carga real.
- **La forma de entrega:** por lotes, una previsión cada día (briefing, «Entregables»).
- **La clasificación normativa:** no aplica, porque la previsión no decide sobre personas.

**Lo que el reconocimiento deja para los planteamientos:** si se entrena un modelo por serie (D7) o uno para las 70
series, que es el que se probó; cómo entran los productos que empiezan a venderse, que en una serie multiplican la venta
por 7,2; la fórmula de cada efecto de la pregunta 4.

## Dónde está la empresa

Propuesto el 20/11/2026 en el paso A. Aprobado por el responsable del caso el 20/11/2026.

**Business analytics**, segundo peldaño de cinco (supuesto). El briefing dice que cada tienda planifica repitiendo lo
que vendió hace poco: mide lo que pasó, pero no prevé. Ninguna fuente del caso dice cómo planifica Walmart de verdad.

El caso la sube a **data science**: una previsión con un modelo que se reentrena y se ejecuta cada día. No llega a
inteligencia artificial: el pedido y los turnos los decide una persona con la previsión delante.

## Por qué es buen momento

Propuesto el 20/11/2026 en el paso B. Aprobado por el responsable del caso el 20/11/2026.

| Condición | Situación |
|---|---|
| Caso de uso | En la agenda: se pide y se pone personal cada semana (supuesto). Accionable: la previsión cambia el pedido siguiente. Medible: el error se mide cada día contra la venta real. Rápido: los datos están y un entrenamiento de las 70 series dura minutos |
| Quién lo usa | Compras, jefes de tienda y finanzas (supuesto) |
| Sponsor | La dirección de operaciones de tiendas, que encarga el caso (supuesto) |

## KPIs

Propuestos el 20/11/2026 en el paso C. Aprobados por el responsable del caso el 20/11/2026.

| KPI | Cómo se calcula | Mejor si |
|---|---|---|
| Error de la previsión | unidades que falla por cada 100 vendidas: suma de las diferencias entre previsto y real, sin signo, entre la suma de lo vendido, por departamento, tienda y periodo | baja |
| Error en dólares | dólares que falla la previsión en dólares por cada 100 vendidos, con la misma cuenta que en unidades | baja |
| Sesgo | lo que la previsión se pasa o se queda corta de media, en unidades o en dólares por cada 100 vendidos, cada previsión con el suyo, con signo | cerca de 0 |
| Ventaja frente a las reglas | error de la regla que menos falla en cada corte menos error del modelo, con su intervalo | sube y por encima de 0 |
| Venta por departamento y tienda | unidades y dólares vendidos cada día | se mide; describe, no decide |

Rangos del sector: no constan, porque el paso 0b se hace sin búsqueda del sector. Los rangos de criterio propio
están en las reglas, §7, «Lo esperable».

## Objetivo y palancas

**Objetivo.** Planificar pedidos y personal de cada departamento con una previsión que se equivoque menos que las reglas
de hoy (briefing, «Objetivos»).

| Palanca | Por qué | Indicador | Sector |
|---|---|---|---|
| **Ajustar el pedido de cada departamento a la previsión** (principal) | menos mercancía parada cuando la previsión baja y menos estantes vacíos cuando sube | error en dólares y sesgo, frente a las tres reglas | no consta |
| **Dar a finanzas y a compras totales que cuadren** (secundaria) | el presupuesto de cada tienda y el plan de cada categoría salen de las mismas previsiones | error del total de cada tienda y de cada categoría | no consta |
**Business case (paso 4b, 24/11/2026).** Con la base del recorte, 507.897 dólares de venta al mes en 2013, el retorno
a tres años es de −84,7 % en el escenario bajo y de −11,1 % en el central. Solo el alto sale a cuenta, con 223,3 %, y
recupera la inversión en el mes 10. Lo que decide el signo es el coste del proyecto: el valor en juego es pequeño. Los
importes sin fuente los decidió el equipo de análisis a petición del responsable del caso. Detalle en `informes/business_case.json` y `.xlsx`.

## La cifra que mide valor

**Error de la previsión en dólares**, por departamento y tienda, cada mes, frente al de la regla que menos falla en cada corte.
En el departamento donde el modelo falle de media más que esa regla, se recomienda la regla (reglas, apartado 7).

| Pregunta de la cifra de valor | Respuesta |
|---|---|
| ¿Qué consigue el cliente? | Quien pide la mercancía acierta más: menos dinero parado y menos estantes vacíos |
| ¿De quién? | De cada departamento en cada tienda |
| ¿Se mide cada periodo? | Sí, cada día y cada mes, con la misma definición |
| ¿Se puede actuar en semanas? | Sí: cambia el pedido siguiente |
| ¿Puede bajar sin más valor? | Sí: el error total puede bajar mientras la previsión se queda corta cada vez más; eso vacía estantes. Por eso va siempre con el sesgo al lado |

**Cifras que vigilan el camino:**
- el sesgo de cada departamento y tienda;
- el error de los días de festivo y de los días SNAP, que son los que más cambian.

## Preguntas semilla

Se contestan en el reconocimiento (2c), solo con los datos de construcción, hasta el 22/05/2014.

**La venta**
- ¿Cuántos días tiene cada departamento y tienda con venta cero?
- ¿Cuántos de esos días son cierres de toda la tienda?
- ¿Hay saltos de nivel en alguna serie, como una tienda que abre o un departamento que cambia?

**Los días que cambian**
- ¿Cuánto sube o baja la venta de cada departamento en festivos, en días SNAP y en cada día de la semana?
- ¿Cuántas veces cambia el precio medio de cada departamento?
- ¿Cambia la venta cuando cambia el precio?

**El valor**
- ¿Cuántos dólares vende cada departamento y tienda al día?
- ¿Qué parte del total hace cada uno?
