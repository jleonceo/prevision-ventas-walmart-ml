---
titulo: El briefing del caso 69 · prever la venta diaria de cada departamento en cada tienda de Walmart
estado: aprobado por el responsable del caso el 20/11/2026 («Sí, lo apruebo»); las preguntas son de partida y se fijan en el paso 1
fecha_documento: 2026-11-20
dueno: el responsable del caso (decide) · el equipo de análisis (redacta)
fuentes: el responsable del caso, 18/11 y 20/11/2026; `datasets_casos/69_prevision_ventas_walmart/00_LEEME.md`; plantilla una plantilla común; mini workflow una plantilla común, F0
---

# Briefing · Previsión de ventas por departamento y tienda

| De: | Dirección de operaciones de tiendas (supuesto) |
|---|---|
| Para: | Equipo de análisis de datos |
| Fecha: | 20/11/2026 |

## La empresa
| Empresa | Walmart, cadena estadounidense de grandes almacenes |
|---|---|
| Sector | Comercio minorista con tres categorías de producto: alimentación, hogar y ocio |
| Tamaño | No consta en los datos. El caso trabaja con 10 tiendas en tres estados: 4 en California, 3 en Texas y 3 en Wisconsin |
| Clientes y mercado | Particulares que compran en tienda (supuesto) |
| Sistemas | Un registro de unidades vendidas por producto, tienda y día, con el precio de cada producto por semana y un calendario con festivos y días de ayuda alimentaria (SNAP) |

## El problema
Cada tienda decide cuánto pedir de cada departamento y cuánta gente poner cada día sin una previsión medida: repite lo
que vendió hace poco (supuesto). Si se queda corta, faltan productos en el estante y se pierden ventas. Si se pasa, el
almacén se llena y el dinero queda parado en mercancía. Lo que cuesta hoy no consta.

## Contexto
La dirección quiere planificar con una previsión que se equivoque menos que las reglas que ya usa (supuesto). Empieza por
los departamentos de 10 tiendas. Si sale bien, la previsión se ejecutaría cada día y llegaría a compras y a finanzas con
las mismas cifras.

## Objetivos
1. Prever cuántas unidades y cuántos dólares venderá cada departamento en cada tienda en los próximos días.
2. Medir si esa previsión se equivoca menos que las reglas que se usan sin modelo.
3. Dar a finanzas la previsión de cada tienda y a compras la de cada categoría, que cuadren entre sí.

## Preguntas de partida
Son las preguntas que la empresa quiere contestar. Se revisan con los datos y se fijan al aprobar el problema.
1. ¿Cuántas unidades y cuántos dólares venderá cada departamento en cada tienda cada día del horizonte? (cuánto se pide y
   cuánta gente se pone)
2. ¿Se equivoca esa previsión menos que repetir la semana anterior, la media de los últimos 28 días o la media del mismo
   día de las 4 semanas anteriores? (si se adopta el modelo o basta una regla)
3. ¿Cuánto venderá cada tienda y cada categoría al sumar los departamentos? (el presupuesto de finanzas y el plan de
   compras)
4. ¿Qué días cambia la venta de lo habitual: festivos, días de ayuda alimentaria, día de la semana o cambios de precio?
   (qué días se refuerza el pedido y el personal)

Las conclusiones tienen que poder convertirse en pasos concretos que reduzcan las roturas de estante y el stock parado.

## Alcance
- Periodo: del 29/01/2011 al 22/05/2016. Construcción hasta el 22/05/2014, validación del 23/05/2014 al 22/05/2015 y
  prueba final del 23/05/2015 al 22/05/2016, apartada hasta el final (el responsable del caso, 20/11/2026).
- Fuentes: el concurso M5 Forecasting de Walmart en Kaggle. El caso usa un recorte de 500 productos elegidos al azar de
  los 3.049 del concurso, en sus 10 tiendas.
- Qué entra: los 7 departamentos de las 10 tiendas, con la venta de los 500 productos sumada por departamento. Son 70
  series diarias.
- Qué queda fuera: la previsión de cada producto en cada tienda; el estudio de promociones, porque los precios casi no
  cambian; la venta de los productos que no están en el recorte.
- Horizonte: unidades a 10 días y dólares a 28 (el responsable del caso, 20/11/2026).
- Indicadores principales: unidades que falla la previsión por cada 100 vendidas, frente a las tres reglas; el sesgo,
  si la previsión tiende a pasarse o a quedarse corta; las mismas cifras en dólares.

## Entregables
- Informe ejecutivo para el equipo directivo, de dos páginas A4 y tres con el anexo, con las conclusiones, el plan de
  acción y el trabajo realizado.
- Informe final con la respuesta a cada pregunta, sus límites y las decisiones propuestas.
- Cuadro de mando para seguir la previsión frente a la venta real y filtrar por estado, tienda, categoría y departamento.
- Un proceso que prevé cada día con la historia hasta ayer, publicado como repositorio con su documentación técnica.
- Plazos: no consta.

## Cómo se trabaja
- Acceso a los datos: ficheros públicos del concurso. La licencia obliga a citar la fuente y prohíbe redistribuir los
  datos, así que el repositorio no los lleva.
- Método: la previsión tiene que ganar a las tres reglas con la prueba fijada antes de medir. Las técnicas se explican a
  quien las va a usar. No usa IA generativa al ejecutarse.
- Confidencialidad: los datos son de productos y tiendas y no traen nada de personas.
- Transparencia: los métodos y las herramientas se explican en la documentación técnica.
- Acciones: cada conclusión acaba en una propuesta práctica, o en lo que faltaría saber para proponerla.

## Quién está
| Papel | Quién |
|---|---|
| Encarga y decide | Dirección de operaciones de tiendas (supuesto) |
| Usa el resultado | Compras, jefes de tienda y finanzas (supuesto) |
| Da los datos | El concurso M5 Forecasting de Kaggle |
| Valida las cifras | Control de gestión (supuesto) |
