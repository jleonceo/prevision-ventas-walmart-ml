---
titulo: Reglas de negocio del caso 69 · qué es una venta de un departamento en una tienda, en unidades y en dólares, qué se prevé, con qué horizonte, con qué periodos y frente a qué tres reglas
estado: aprobado por el responsable del caso apartado a apartado el 20/11/2026 («Sí, lo apruebo», §1 a §12); «Lo esperable» (§7), aprobada el 21/11/2026; prueba de comprensión hecha y aplicada el 21/11/2026
fecha_documento: 2026-11-20
dueno: el responsable del caso (decide) · el equipo de análisis (redacta)
fuentes: `00_briefing.md`; `01_ficha_del_caso.md`; el registro del caso; mini workflow de forecasting una plantilla común (D1 a D13) y su guía `01_guia_forecasting.md` (§2, §3, §8 y §9); las reglas del caso 62 como modelo; la guía de participantes del concurso (`../fuentes/M5_guia_de_participantes_2020.docx`, desde el 21/11/2026); la estructura de los datos medida el 20/11/2026 (cabeceras, tiendas, departamentos y calendario hasta el 22/05/2014, sin abrir una sola venta)
---

# Reglas de negocio de Walmart

La empresa y los datos son reales: el concurso M5 Forecasting de Walmart en Kaggle. El caso trabaja con un recorte de
500 productos. La petición y las personas son inventados. Lo que no sale de los datos ni de la documentación del
concurso va marcado como **(supuesto)**.

## 1. La petición

La petición de la dirección de operaciones de tiendas está en `00_briefing.md`: el problema, los objetivos, las preguntas
de partida, el alcance y lo que se entrega. Este documento no lo repite. Las preguntas que se contestan son las que se
aprueben en el paso 1, en «El problema» de `01_ficha_del_caso.md`.

## 2. Contexto del negocio

Walmart es una cadena estadounidense de grandes almacenes que vende al consumidor final en tienda. Vende tres
categorías de producto: alimentación, hogar y ocio. La venta cambia con el día de la semana, los festivos y los días en
que se cobra la ayuda alimentaria (SNAP), así que un día se compara con el mismo día de la semana y no con el anterior
sin más. Si hay una época del año que mueva la venta se mide en el reconocimiento de los datos.

### Personas

| Papel | Quién | Qué hace en el proyecto |
|---|---|---|
| Patrocinador | Dirección de operaciones de tiendas (supuesto) | encarga el caso y aprueba las decisiones |
| Quién lo usa | Compras, jefes de tienda y finanzas (supuesto) | piden mercancía, ponen turnos y preparan el presupuesto con la previsión |
| Dueño de los datos | El concurso M5 Forecasting de Kaggle | publica la venta diaria, los precios y el calendario |
| Quien valida | Control de gestión (supuesto) | comprueba las cifras |

La persona responsable del proyecto es quien resuelve las cuestiones pendientes.

Este documento recoge el contexto funcional, las definiciones y los criterios acordados para el proyecto. No define
la estructura técnica de los datos, las relaciones entre tablas ni las decisiones de implementación.

## 3. Lo que se prevé

### El departamento en una tienda

La **serie** del caso es la venta diaria de un departamento en una tienda. Son 70 series: 7 departamentos en 10 tiendas
(el responsable del caso, 20/11/2026).

- Incluye: la venta de los productos del recorte que pertenecen a ese departamento, sumada, en esa tienda y ese día.
- Excluye: los productos de Walmart que no están en el recorte.
- No implica la venta real del departamento: el recorte tiene 500 de los 3.049 productos del concurso, elegidos al azar. Un total del caso no es un total de Walmart.
- Cada serie se prevé **dos veces, por separado**: una en unidades y otra en dólares (el responsable del caso, 20/11/2026: «Sí, las dos
  previsiones»). Son 140 previsiones.
- Si la petición no lo concreta: «departamento» es un departamento en una tienda, no la suma de las 10 tiendas.

### El producto

Un **producto** es un artículo del catálogo. Dos productos son distintos por su código. El caso no prevé productos: solo
los suma dentro de su departamento.

- Los 500 productos del recorte están en las 10 tiendas.
- Un producto que todavía no se vendía en una tienda suma cero a su departamento esos días. Cuando empieza a venderse,
  la venta del departamento sube sin que haya cambiado la demanda. Cuántos casos hay se mide en el reconocimiento.

### La tienda

Una **tienda** es un punto de venta físico. Dos tiendas son distintas por su código. Pertenece a un estado.

## 4. Agrupaciones

De lo general a lo particular:

- **Producto → departamento → categoría.** Tres categorías y siete departamentos, con estos productos del recorte en
  cada tienda (medido el 20/11/2026):
  - alimentación: FOODS_1 con 43 productos, FOODS_2 con 61 y FOODS_3 con 129;
  - ocio: HOBBIES_1 con 73 y HOBBIES_2 con 27;
  - hogar: HOUSEHOLD_1 con 93 y HOUSEHOLD_2 con 74.
- **Tienda → estado.** Diez tiendas en tres estados: CA_1 a CA_4 en California, TX_1 a TX_3 en Texas y WI_1 a WI_3 en
  Wisconsin.
- No hay subcategoría, marca, proveedor, región dentro del estado ni tamaño de tienda, aunque alguien los pida.

### Cómo cuadran los niveles

La **previsión de un nivel de arriba** (tienda, categoría en una tienda, categoría en la cadena, estado, cadena) es la
suma de las previsiones de sus departamentos en sus tiendas: se reconcilia **de abajo arriba**. Así el presupuesto de
finanzas por tienda y el plan de compras por categoría salen de las mismas cifras (ficha, palanca secundaria).

- Vale para las unidades y para los dólares, cada una con su previsión.
- No implica que el total previsto sea el mejor posible para ese nivel: sumar acumula arriba el error de abajo.
- Si una petición pide otro nivel de modelado u otra forma de reconciliar, es cuestión pendiente.

## 5. Operaciones y tiempo

### La venta

La **venta en unidades** de un departamento en una tienda un día es la suma de las unidades vendidas ese día de sus
productos del recorte. No es número de tickets ni de clientes.

La **venta en dólares** es la suma, producto a producto, de las unidades vendidas por el precio de ese producto en esa
tienda esa semana.

- Un día con cero unidades es un dato válido, no un vacío.
- Las dos ventas cuentan lo vendido, no lo que se habría vendido: los datos no traen existencias.

### El día sin ventas de un departamento

Un **día sin ventas** es un día con cero unidades en un departamento de una tienda. No implica rotura de stock: los
datos no distinguen falta de demanda de falta de producto.

- Si ese día todos los departamentos de la tienda venden cero, es un **cierre de la tienda**. El 25 de diciembre cierran
  casi todas: de 2011 a 2014, 32 de los 40 días de tienda están a cero en todos sus departamentos. Los otros 8 vendieron
  22 unidades entre todos, que se dejan como vendidas. Fuera del 25 de diciembre hay un solo cierre, el de WI_1
  el 02/02/2011, sin evento, que se trata como un 25 de diciembre.
- **Las clases de los días sin ventas** (mini workflow, D8) se midieron en la corrección del paso 3 con la tabla de
  clases de la guía (§3). Cada día a cero de las 70 series va a la primera clase que cumple, en este orden, con sus días
  de serie en la construcción y en la validación:
  - **cierre de la tienda,** 175 y 56: es un dato válido y entra como variable de calendario o de evento;
  - **25 de diciembre sin cierre de la tienda,** 35 y 12: queda fuera del error, como el día entero (§6);
  - **demanda intermitente,** 2.171 y 201: son las 10 series de HOBBIES_2, con menos de 10 unidades de media al día.
    Son ceros válidos; cómo entran al modelo se fija en el paso 5 con la guía (§3);
  - **resto,** 35 y 2: cuatro series de más de 14 unidades de media al día, con el departamento entero a cero y la
    tienda abierta. Los datos no distinguen una rotura de stock de un dato que falta, así que se quedan como ceros
    válidos. Solo 2 de esos días caen en la validación.

### El precio

El **precio** es el de venta de un producto en una tienda durante una semana de Walmart, que va de sábado a viernes: la
media de los siete días de esa semana (guía del concurso, `../fuentes/M5_guia_de_participantes_2020.docx`). Vale para
los siete días de esa semana.

- Una semana sin precio es una semana en que el producto no se vendió en esa tienda (guía del concurso).
- Los precios casi no cambian: mediana de 2 cambios por producto y tienda en cinco años. El caso no estudia
  promociones.
- **El precio de los días a prever se da por conocido**, igual que en el concurso, que lo entrega también para esos días
  (supuesto). Es la decisión D9: el precio que entra en la previsión de un día es el de la semana anterior. Se da por
  conocido también cuando esa semana cae dentro del horizonte, como en el concurso y en el caso 62. El de la semana
  prevista no entra: una semana sin precio es una semana sin venta, así que diría qué productos se venden en ella.
- **En el precio medio de un departamento solo cuentan los productos que ya tenían precio cuatro semanas antes** de la
  semana que se toma (el responsable del caso, 24/11/2026). Un producto no tiene huecos de precio: entra la semana de su primera
  venta y sigue hasta el final. Si contara desde que entra, la media de una semana dentro del horizonte avisaría de una
  primera venta que el día de prever no se conoce. Con 28 días de horizonte, el día previsto cae como mucho cuatro
  semanas después de la del origen. Por eso todo producto que cuenta ya se vendía antes del origen.
- La guía no dice cuándo se
  fija el precio. Si cambia a mitad de semana, la media no se conoce hasta el viernes; el caso no lo trata, porque los
  precios casi no cambian.

### Lo que se sabe el día de prever

La previsión de un día solo usa lo que se sabe la víspera: la venta hasta el día anterior, el precio de la semana anterior (D9) y el
calendario, que se conoce de antemano (festivos y días SNAP).

### Fechas

- Cada venta es del día natural de la tienda.
- **El periodo de los datos** va del 29/01/2011 al 22/05/2016: 1.941 días. El calendario llega hasta el 19/06/2016.
- **Los tres periodos** (el responsable del caso, 20/11/2026; mini workflow, D5):
  - **construcción:** del 29/01/2011 al 22/05/2014, 1.210 días. El reconocimiento y la exploración usan solo este
    periodo;
  - **validación:** del 23/05/2014 al 22/05/2015, 365 días. Se mira al medir el modelo frente a las tres reglas;
  - **prueba final:** del 23/05/2015 al 22/05/2016, 366 días. Se aparta del caso antes de empezar el paso 2 y no se mira
    hasta la prueba final, ni para elegir variables ni para ajustar el modelo.
- **Fecha de referencia** del desarrollo: el 22/05/2015, último día que se mira antes de la prueba final. «El último
  año» es la validación, nunca contado desde hoy.
- **La prueba final no es del todo desconocida.** La investigación previa miró parte de ese año: la
  descripción de ceros, tipos de demanda y efectos de SNAP y festivos, con los cinco cortes de diciembre de 2015 a abril de
  2016. Ninguna cifra de ese periodo se usa desde ahora para elegir ni ajustar nada.
- Un mes o una semana sin todos sus días es **parcial** y no se compara con uno completo.

### El horizonte

El **horizonte** es cuántos días por delante se prevé, contados desde el día siguiente al último con ventas conocidas
(el responsable del caso, 20/11/2026: «Sí, así»; mini workflow, D3):

- **unidades: 10 días**, el pedido semanal más lo que tarda en llegar (supuesto sobre el plazo de pedido);
- **dólares: 28 días**, porque finanzas planifica el mes.

Se prevé cada día, aunque el horizonte sea de varios: la previsión que se usa es siempre la más reciente. Cada día
del horizonte se prevé con lo previsto para los días anteriores, que es la **previsión recursiva** (mini workflow, D7).

### Datos vacíos y valores especiales

- Un día sin festivo no es un vacío: es un día normal.
- Un día sin venta de un producto es un cero, no un vacío.
- Una venta negativa sería imposible; si aparece, el trabajo para.
- Un precio que falta en una semana con venta sería un error de los datos: se cuenta y se para antes de calcular dólares.

## 6. Información económica

Todos los importes van en dólares estadounidenses. Si el precio lleva impuestos de venta no consta; no cambia ninguna
respuesta, porque las dos previsiones se comparan con las reglas en la misma moneda.

### Las métricas

- **Error de la previsión** = suma de las diferencias entre lo previsto y lo real, sin signo, entre la suma de lo real,
  por 100. Se lee como **unidades que falla por cada 100 vendidas** (en dólares, dólares que falla por cada 100
  vendidos). Se calcula sobre todos los días y series del periodo que se mide, no como media de errores de cada día.
  Cada corte se mide con todos los días de su horizonte. El error que decide es uno solo, el de las 70 series juntas. El
  de cada departamento decide qué se recomienda usar en él (§7); el de cada tienda se da para leer.
- **El 25 de diciembre**, día de cierre, queda fuera del error del modelo y de las tres reglas: se sabe de antemano que
  la tienda cierra.
- **Error en dólares** = la misma cuenta sobre la previsión en dólares, que es una previsión propia y no las unidades por
  un precio.
- **Sesgo** = la misma cuenta con signo: positivo si la previsión se pasa, negativo si se queda corta. Va siempre al lado
  del error, porque el error puede bajar mientras la previsión se queda cada vez más corta. Eso vacía estantes
  (ficha, «La cifra que mide valor»).
- Una previsión no puede ser negativa.

### Lo que no se puede calcular

- El dinero que ahorra la previsión: los datos no traen coste, margen ni existencias.
- Las ventas perdidas por estante vacío: un cero no dice si había producto.
- La venta real de Walmart: el recorte tiene 500 de los 3.049 productos.

## 7. Criterios analíticos acordados

### Las tres reglas sencillas

El modelo se compara siempre con estas tres reglas, que prevén sin modelo (briefing, pregunta 2; mini workflow, D6):

- **repetir la semana anterior:** los 7 últimos días con venta conocida, el del origen incluido, repetidos semana a
  semana hasta cubrir el horizonte;
- **media de los últimos 28 días:** la media diaria de los 28 últimos días con venta conocida, el del origen incluido,
  la misma para todos los días del horizonte;
- **media del mismo día de las 4 semanas anteriores:** para cada día de la semana, la media de ese día en las cuatro
  semanas que acaban en el origen, repetida en el horizonte.

En dólares, cada regla se aplica a la historia de la venta en dólares.

Ninguna regla usa lo que pasa después del origen, igual que el modelo. Así se midieron en la prueba de partida
(`informes/reconocimiento/prueba_cap31.py`, las dos primeras) y en el canario. Cada regla se nombra siempre entera, nunca como «la mejor regla» sin decir cuál. Las tres se calculan con los
mismos días, las mismas series y el mismo horizonte que el modelo.

### Qué cuenta como mejora

El modelo **gana** si se equivoca menos que la regla que menos se equivoca en cada corte con una ventaja demostrada
(regla fijada antes de medir):

- se equivoca menos en al menos el 75 % de los orígenes de previsión, redondeando hacia arriba: con 10 orígenes hacen
  falta 8. El canario pidió 9 de 12; pasarlo al 75 % para cualquier número de orígenes es propuesta del equipo de análisis;
- el intervalo del 95 % de la ventaja (error de la regla que menos falla menos error del modelo, ficha) queda entero por
  encima de cero.

**Dónde se decide:** en la validación. La prueba final lo confirma una sola vez, con la misma regla; si no lo confirma,
se dice.

Si cumple solo la primera, el modelo es mejor de media pero no demostrado. Se dice así. El número de orígenes de la
validación y cómo se calcula el intervalo van a los planteamientos (`../metodo/04_planteamientos.md`), con la sección de
`aprendizaje-automatico` que los fija.

- Vale para las unidades y para los dólares, cada uno por su lado.
- El veredicto principal es el de las 70 series juntas. El de cada tienda se da para leer, sin cambiar el veredicto.
- **Cada departamento, su recomendación** (el responsable del caso, 24/11/2026). El error de las 70 juntas pesa por volumen:
  FOODS_3 es el 48,9 % de las unidades y el 38,9 % de los dólares. Si en un departamento el modelo falla de media más
  que la regla que menos falla, el informe recomienda esa regla en ese departamento. El veredicto principal no cambia.
- Con la cifra que mide valor van siempre el sesgo y el error de los días de festivo y de SNAP (ficha). Son dos cifras
  separadas: el error de los días con algún evento del calendario y el de los días SNAP del estado de cada tienda.

### Preselección de variables

Aprobada por el responsable del caso el 24/11/2026 («Sí, apruébalo»), antes de ver ningún resultado (`preseleccion-variables` §1 y
§4; propuesta en `informes/preseleccion_propuesta.md`):

- **Se preselecciona** en los dos objetivos por separado. En Ridge, con todos los pasos del método. En
  HistGradientBoosting, solo quitar lo que no puede entrar y dejar una variante por variable de origen.
- **Modo comparativo:** la eliminación recursiva con validación cruzada, la información mutua y la importancia por
  permutación votan. Si la eliminación recursiva no cabe en tiempo de cálculo, la permutación sola, y se dice.
- **Escenario de votación: consenso amplio.** Entra una variable si la marcan dos de los tres métodos.
- **Variables que se quedan sin votar**, con su motivo:
  - la tienda y el departamento: un modelo para las 70 combinaciones con las dos como variables (planteamientos §2,
    decisión 6);
  - los festivos, los días SNAP, el día de la semana, el mes y el precio medio de la semana anterior: la pregunta 4 de
    la ficha pide sus efectos «como variables del modelo».
- **Los festivos, una columna por festivo** (`evento_<nombre>`), a 1 si el día lo tiene, venga en el primer campo de
  evento o en el segundo; `event_name_1` y `event_name_2` no entran (el responsable del caso, 24/11/2026: «Un día es festivo y punto»).

### Población del análisis

| Uso | Entra | Sale |
|---|---|---|
| Previsión y comparación con las reglas | las 70 series, con todos sus días del periodo que se mide | los primeros días de cada serie que no tienen la historia que piden las variables, contados en el registro de transformaciones |
| Reconocimiento y exploración | las 70 series en construcción | validación y prueba final |
| Totales de tienda y categoría | la suma de las previsiones de sus departamentos | nada más |

### Lo esperable

La escribió el 21/11/2026 un revisor que no había visto las cifras de los datos, solo con el briefing, la ficha y estas
reglas (petición 02). No hay mapa del sector: todos los rangos son **criterio propio** y de orden
de magnitud, nunca cifras del sector. El equipo de análisis la repasó y el responsable del caso la aprobó el 21/11/2026 («Sí, escríbela»).

| Magnitud o indicador | Rango esperable | Qué haría sospechar | Con qué tiene que ser coherente | Qué no se mezcla | Por qué ese rango |
|---|---|---|---|---|---|
| Venta diaria de un departamento en una tienda, en unidades | no se puede saber el nivel antes de medir; un número entero y no negativo, de decenas a pocos miles al día | una cifra negativa o con decimales; un salto de nivel duradero sin festivo, que puede ser un producto que empieza a venderse (§3) | la venta en dólares del mismo día; el número de productos del departamento (§4); la suma de la tienda | departamento del caso y departamento real de Walmart; unidades y demanda o tickets | un departamento suma muchos artículos que rotan poco cada uno |
| Venta diaria de un departamento en una tienda, en dólares | no se puede saber el nivel antes de medir; positiva, de cientos a decenas de miles de dólares al día | dólares con cero unidades o cero dólares con unidades; un precio medio por unidad de cientos de dólares o de céntimos | las unidades del mismo día y el precio de la semana (§5) | la venta en dólares producto a producto (§5) y las unidades de la serie por un precio único | un artículo de gran almacén cuesta de uno a varias decenas de dólares |
| Precio (§5) | de 0,5 a 50 dólares por unidad en casi todos los productos; igual los siete días de la semana | precio cero o negativo; una semana con venta y sin precio, que para el trabajo (§5); un precio que cambia a diario; un salto de más del doble de una semana a otra | la venta en dólares; que casi no cambie (§5) | semana de Walmart y semana natural; precio de un producto y precio medio del departamento | los precios de un gran almacén de consumo llegan como mucho a pocas decenas de dólares |
| Días sin ventas de un departamento (§5) | no se puede saber cuántos antes de medir; pocos o ninguno en los departamentos grandes, más en los pequeños | días seguidos a cero en un departamento grande de alimentación; un departamento pequeño casi siempre a cero | el cierre de la tienda; el tamaño del departamento: más productos, menos ceros | día sin ventas y rotura de stock; día sin ventas y cierre | cuantos más productos suma una serie, más raro es que todos vendan cero a la vez |
| Cierres de tienda | muy pocos al año; el 25 de diciembre la venta es cero (§5) | más de uno o dos cierres al año fuera del 25 de diciembre; un cierre en una sola tienda sin causa | el calendario; el mismo día en todos los departamentos de la tienda | cierre y día sin ventas de un departamento | una cadena de grandes almacenes solo cierra en fiestas señaladas o por causas excepcionales |
| Cambio de la venta en festivos | de un 20 % menos a un 20 % más que un día normal, con signo según el festivo y el departamento; el 25 de diciembre aparte | más de un 50 % en un festivo que no sea el 25 de diciembre; el mismo signo en todos los departamentos y festivos | el error de la previsión en festivos, que se espera mayor que en días normales | festivo y día SNAP; efecto sobre la venta y efecto sobre el error | un festivo mueve la venta de un comercio unas decenas por ciento como mucho, salvo el cierre |
| Cambio de la venta en días SNAP | de 0 a un 10 % más que un día sin SNAP, sobre todo en alimentación; poco o nada en ocio y hogar | un efecto negativo en alimentación; más de un 20 %; el mismo efecto en todos los departamentos | el estado, porque el calendario SNAP va por estado | día SNAP y festivo; efecto SNAP y efecto del día de la semana | la ayuda alimentaria se gasta sobre todo en comida |
| Cambio de la venta según el día de la semana | el día más fuerte vende de 1,1 a 1,5 veces el más flojo en el mismo departamento; el fin de semana, por encima | todos los días iguales; un día con más del doble que el más flojo; el día más fuerte distinto en cada tienda sin motivo | que la media de los últimos 28 días falle más que las otras dos reglas cuanto más marcado sea el ritmo de la semana | día de la semana y semana de Walmart | es el ritmo más estable del comercio minorista (§2) |
| Error de la previsión, en unidades | de 15 a 45 unidades falladas por cada 100 vendidas; menor en los departamentos grandes | menos de 5, que apunta a que la previsión usa el futuro; más de 100; el mismo error en todas las series | por debajo del error de la regla que menos falla en ese corte; nunca por debajo del sesgo sin signo; los totales de tienda y de categoría, con menos error | error sobre todos los días y series (§6) y media de errores de cada día; horizonte de 10 días y de 28 | una venta diaria de varios productos tiene un ruido que ninguna previsión quita |
| Error en dólares | del mismo orden que en unidades, de 15 a 45 dólares fallados por cada 100 vendidos, algo mayor por el horizonte de 28 días | más de 15 puntos de diferencia con el error en unidades sin explicación | el error en unidades, porque el precio casi no cambia; un horizonte más largo da más error | la previsión en dólares y las unidades previstas por un precio (§10) | los dólares se mueven con las unidades y a 28 días hay más días previstos sobre lo previsto |
| Sesgo | de -5 a +5 por cada 100 en el modelo; algo más en las reglas | más de 10 sin signo con un error bajo; siempre negativo en todas las series | el error, que nunca es menor que el sesgo sin signo | sesgo y error; el sesgo en unidades y el de dólares | una previsión bien hecha se pasa y se queda corta casi por igual |
| Ventaja frente a las reglas | de 0 a 10 puntos; el intervalo del 95 % puede incluir el cero | más de 15 puntos se revisa por si la previsión usa el futuro, sin darla por error: en el concurso, el mejor modelo falló un tercio menos que repetir la semana anterior; una ventaja negativa con veredicto «gana» | el error del modelo y el de las tres reglas en el mismo corte; la regla de ganar de este §7 | la regla que menos falla en un corte y una regla concreta; la ventaja en unidades y en dólares | las reglas ya recogen el ritmo de la semana, así que el modelo gana pocos puntos |
| Error de repetir la semana anterior | de 20 a 55 por cada 100 | menos que el modelo en casi todos los cortes; menos de 10 | las otras dos reglas con los mismos días, series y horizonte; mayor que la media del mismo día de las 4 semanas anteriores | cada regla, con su nombre entero | copiar una sola semana mantiene su ritmo, pero también su ruido |
| Error de la media de los últimos 28 días | de 25 a 60 por cada 100; la peor si la semana tiene un ritmo marcado | que sea la que menos falla en un departamento con ritmo semanal marcado; menos de 10 | el ritmo del día de la semana: cuanto más marcado, peor queda esta regla | cada regla, con su nombre entero | una media única borra el día de la semana |
| Error de la media del mismo día de las 4 semanas anteriores | de 18 a 45 por cada 100; la que menos falla en la mayoría de los cortes, como expectativa | que sea claramente peor que las otras dos en casi todos los cortes; menos de 10 | las otras dos reglas y el modelo | cada regla, con su nombre entero | une el ritmo de la semana con la media de cuatro semanas |
| Totales de tienda | la suma exacta de sus 7 departamentos, en unidades y en dólares; con un error por cada 100 no mayor que el de un departamento típico | un total que no es la suma de sus departamentos; un total con más error que todos sus departamentos | la venta de la tienda; los totales de categoría, que salen de las mismas previsiones | total de la tienda del caso y de Walmart; unidades y dólares | al sumar, los errores de los departamentos se compensan en parte |
| Totales de categoría | la suma exacta de sus departamentos en las 10 tiendas; en unidades, alimentación por encima de hogar y de ocio (233, 167 y 100 productos del recorte, cifra medida en los datos, no de venta) | una categoría por encima de alimentación en unidades sin causa; un total que no cuadra | la suma de todas las categorías, igual a la de todas las tiendas | unidades y dólares; el recorte y el total de Walmart | se cuadra de abajo arriba (§4) y el reparto en unidades sigue el número de productos |

Lo que caiga fuera de un rango no es un error por sí solo: se mira, se explica y, si cambia una regla, sigue la
cascada.

## 8. Criterios específicos del análisis

Cuando una petición fije una comparación, un umbral o un indicador para un requerimiento concreto, se respeta esa
definición en esa petición.

Esas definiciones no se aplican a otros análisis.

## 9. Datos personales

No aplica: los datos son de productos, tiendas, precios y calendario. No traen nada de personas (una nota interna, el paso 2a no
se hace).

Si en los datos aparece un dato personal en claro, el trabajo para y se avisa.

## 10. Criterios de interpretación

Los términos de negocio se interpretan según las definiciones de este documento y no solo por su significado
habitual.

Debe distinguirse especialmente entre:

- unidades vendidas y demanda: se vende lo que hay en la estantería;
- día sin ventas y rotura de stock;
- la venta de un departamento del caso y la del departamento real de Walmart;
- la previsión en dólares y las unidades previstas por un precio: son dos previsiones distintas;
- el error de un día y el error del horizonte entero;
- la previsión y el objetivo de ventas;
- la regla que menos se equivoca en un corte y una regla concreta: la primera cambia de un corte a otro.

No deben inferirse estructuras de datos, relaciones, fórmulas o criterios de exclusión que no estén confirmados por el
contexto disponible.

Cuando una petición requiera una interpretación no recogida en estas reglas, se identifica como una cuestión
pendiente antes de adoptar un criterio.

## 11. Información adicional del proyecto

Estas reglas se complementan con la documentación del concurso M5, que se guarda en `config/fuentes/`.

La documentación técnica que se genere durante el proyecto se mantiene separada de estas reglas.

## 12. Vocabulario

| Palabra | Qué significa en este caso | Con qué se confunde |
|---|---|---|
| serie | la venta diaria de un departamento en una tienda | un producto en una tienda |
| venta | unidades vendidas en un día; o su importe, si se dice «en dólares» | demanda; ingreso total de Walmart |
| departamento | uno de los siete (FOODS_1 a HOUSEHOLD_2) en una tienda | el departamento de la cadena entera |
| previsión | la venta esperada de un día futuro | objetivo de ventas |
| horizonte | los días que se prevén: 10 en unidades y 28 en dólares | periodo de prueba |
| origen | el último día con ventas conocidas desde el que se prevé | primer día previsto |
| corte | un origen con su horizonte, usado para medir | partición de los datos |
| error | lo que falla la previsión por cada 100 vendidas | error medio por día |
| sesgo | si la previsión se pasa o se queda corta, con signo | error |
| las tres reglas | repetir la semana anterior; media de 28 días; media del mismo día de 4 semanas | «la mejor regla» sin decir cuál |
| reconciliar | hacer que los niveles sumen lo mismo, de abajo arriba | cuadrar contra lo vendido |
| día SNAP | día en que se cobra la ayuda alimentaria en ese estado | festivo |
| cierre | día con toda la tienda a cero | día sin ventas de un departamento |
| semana | de sábado a viernes, la del precio | semana natural de lunes a domingo |
| construcción, validación, prueba final | los tres periodos del §5 | entrenamiento y prueba de un corte |

## 13. Historial de cambios

| Fecha | Qué cambió | Quién lo decidió | Qué se revisó por el cambio |
|---|---|---|---|
| 20/11/2026 | Primera versión, con lo decidido en la inspección, el briefing, la ficha y las decisiones D1 a D7 del mini workflow | El equipo de análisis la escribe; pendiente del responsable del caso | briefing y ficha. Dos choques, sin tocar hasta que el responsable del caso apruebe la cascada: la ficha define el error en dólares como las unidades falladas por el precio de cada producto; aquí es el error de la previsión en dólares, que no va por producto; el briefing dice que el horizonte «no consta», pero ya está fijado |
| 20/11/2026 | Aprobadas apartado a apartado, §1 a §12, sin cambios de texto | El responsable del caso: «Sí, lo apruebo» en cada apartado | ninguno: no cambia el texto |
| 20/11/2026 | Cascada de los dos choques: en la ficha, el error en dólares pasa a ser el de la previsión en dólares (antes, unidades falladas por el precio de cada producto), el sesgo vale para las dos previsiones y la ventaja y la cifra que mide valor se miden frente a la regla que menos falla en cada corte (antes, «la mejor de las tres reglas»; la cifra que mide valor no estaba en la tabla y salió en la segunda búsqueda); en el briefing, el horizonte pasa de «no consta» a 10 días en unidades y 28 en dólares. Estas reglas no cambian | El responsable del caso: «sigue», con la tabla de la cascada delante | `01_ficha_del_caso.md` y `00_briefing.md`; sin scripts, datos derivados ni informes afectados |
| 21/11/2026 | Cascada del precio, con la guía del concurso guardada: el precio es la media de los siete días de la semana; la semana sin precio deja de ser supuesto; el precio de los días a prever se da por conocido como en el concurso (antes, «la tienda fija el precio de la semana antes de que empiece», que la guía no dice). D9 no cambia. La guía, añadida a las fuentes | El responsable del caso: «Apruebo la tabla» | ficha y briefing (precio por semana, sin cambio); §5 venta en dólares, «Lo que se sabe el día de prever» y precio que falta (sin cambio); sin scripts, datos derivados ni informes afectados |
| 21/11/2026 | «Lo esperable» (§7), escrita a ciegas por un revisor, con tres ajustes del equipo de análisis: el número de productos por categoría, marcado como cifra medida en los datos; quitada una frase que no se entendía en los totales de categoría; una ventaja de más de 15 puntos se revisa sin darla por error, por el concurso | El responsable del caso: «Sí, escríbela» | ninguno: llena un apartado pendiente y no cambia otra regla |
| 21/11/2026 | Prueba de comprensión. Texto: las ventanas de las tres reglas incluyen el día del origen, como el código (antes, «los 7 días anteriores al origen»); cada corte se mide con todos los días de su horizonte; el error que decide es el de las 70 series juntas; las reglas en dólares, sobre la historia en dólares; el intervalo, de la ventaja y por encima de cero (antes, «de la diferencia de error, por debajo de cero»). Criterios nuevos: se decide en la validación y la prueba final confirma una vez; «3 de cada 4» pasa a «al menos el 75 %, redondeando hacia arriba»; el 25 de diciembre fuera del error; festivos y SNAP, dos cifras separadas | El responsable del caso: «Apruebo la tabla» | ficha: «140 series» pasa a 70 series y 140 previsiones, la venta real en dólares separada de la previsión, rangos del sector frente a «Lo esperable»; planteamientos: lo que queda por fijar; sin scripts, datos derivados ni informes afectados (`prueba_cap31.py` ya usaba el día del origen) |
| 24/11/2026 | Cascada de §5 tras la corrección. D9: entra el precio de la semana anterior, dado por conocido también dentro del horizonte (antes, «con su valor de esa semana»); en «Lo que se sabe el día de prever», el precio de la semana anterior (antes, «el precio de cada semana»). El 25 de diciembre: 32 de 40 días de tienda cerrados y 22 unidades que se dejan como vendidas; el cierre de WI_1 el 02/02/2011 se trata como un 25 de diciembre (antes, «el 25 de diciembre la venta es cero»). D8 escrita con sus cuatro clases medidas (antes, pendiente de la limpieza, «paso 2», que es el paso 3) | El responsable del caso: «Apruebo la tabla» | ficha y planteamientos (ya decían la semana anterior, sin cambio); §6 (el 25 de diciembre fuera del error, sin cambio); «Lo esperable» de §7, escrita antes de medir, sin cambio; diccionario, scripts 01 a 03, Parquet, registro de transformaciones e informes de calidad y corrección: sin afectar |
| 24/11/2026 | Cascada del auditor del cierre del ETL. §5: en el precio medio del departamento solo cuentan los productos con precio desde cuatro semanas antes (antes, todos los que tenían precio esa semana, lo que avisaba de las primeras ventas dentro del horizonte). §6 y §7: en cada departamento donde el modelo falla de media más que la regla que menos falla, se recomienda esa regla (antes, el de cada departamento solo «para leer») | El responsable del caso: «Sí, apruebo los dos» | reglas de transformación, diseño del modelo de datos, planteamientos y ficha; scripts 04 y 05 con sus pruebas; `hechos_series.parquet`, informes de modelado y transformación, cifras de referencia y una ficha nueva en el registro |
| 24/11/2026 | Preselección de variables (§7, apartado nuevo): si se hace, modo comparativo, consenso amplio y las variables que se quedan sin votar | El responsable del caso: «Sí, apruébalo» | ninguno: criterio nuevo, antes de preseleccionar; no cambia otra regla ni ningún resultado |
| 24/11/2026 | Los festivos entran como una columna por festivo, sin importar el campo en que vengan | El responsable del caso: «Un día es festivo y punto» | la lista final de la preselección (P-01); ningún resultado entregado |
