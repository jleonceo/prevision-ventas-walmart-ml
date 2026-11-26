---
titulo: Propuesta de preselección de variables del caso 69 · si se preselecciona, con qué modo, con qué escenario y qué variables tiene que conservar el negocio
estado: propuesta del agente analista-preparacion-modelo, 24/11/2026; pendiente del responsable del caso. Es una puerta: no se ha preseleccionado nada
fecha_documento: 2026-11-24
dueno: el responsable del caso (decide) · el equipo de análisis (propone)
fuentes: método `preseleccion-variables` §1, §4, §6 y §7, con su `parametros.md` y `metodos.md`; fichas de HistGradientBoosting (§4) y de Ridge (§6); `informes/preparacion.json`; `informes/variables_modelo.json`; `config/modelo/matriz_transformaciones.md`; `config/negocio/01_ficha_del_caso.md` (pregunta 4); `config/metodo/04_planteamientos.md` §2
---

# Propuesta de preselección · caso 69

## Lo que se propone

Hace falta preseleccionar. El método da una respuesta distinta para cada algoritmo. Se propone aplicarla tal cual, en
los dos objetivos por separado:

- **Ridge:** preselección completa, con todos los pasos del método. Es un modelo lineal y el método la pide siempre en
  ese caso; la ficha de Ridge lo repite («la hace antes `preseleccion-variables`»).
- **HistGradientBoosting:** solo los dos pasos que el método pide a los árboles: fuera lo que no puede entrar y una
  variante por variable de origen. La ficha del algoritmo añade que, con muchas variables parecidas, se preselecciona
  igual.
- **Modo comparativo:** eliminación recursiva con validación cruzada, información mutua e importancia por permutación,
  que votan.
- **Escenario de votación: consenso amplio.** Entra una variable si la marcan dos de los tres métodos.

El preprocesador sigue siendo uno por objetivo. La lista que salga se aplica después de él, como selección de
columnas dentro del `Pipeline`, así que no cambia la matriz aprobada.

## Por qué hace falta

El método decide por el tipo de modelo, no por el número de variables. Compiten dos:

- Ridge es lineal. Para ese tipo la preselección va siempre, porque scikit-learn no da la significación de cada
  coeficiente. Además, su paso de «las que dicen lo mismo» es obligatorio, porque un modelo lineal reparte el efecto
  entre variables parecidas.
- HistGradientBoosting maneja bien muchas variables. El método le pide solo quitar lo que no puede entrar y dejar una
  variante por variable.

Cada preprocesador deja 117 columnas de salida, con 82.250 filas de entrenamiento (`preparacion.json` y
`variables_modelo.json`). Hay columnas que dicen casi lo mismo por construcción:

- la media de los últimos 7 días es exactamente la media de los retardos de 1 a 7 días, que también entran;
- cada evento entra dos veces, por la codificación de `event_name_1` o `event_name_2` y por su columna `evento_<nombre>`.
  La matriz aprobada dejó a la preselección elegir entre las dos (respuesta 3).

## Por qué el modo comparativo

El método usa el modo comparativo cuando el resultado decide algo caro o hay duda, con la regla del responsable del caso para lo
opcional: si hay duda, se usa. Aquí hay duda por dos motivos. Con esta previsión, compras y
los jefes de tienda ajustarán el pedido de cada día. Los tres métodos miden cosas distintas: la eliminación recursiva ve las variables juntas, la información mutua
ve cada una sola y la permutación mide lo que pierde un modelo ya entrenado.

Con fecha y partición por fecha, el método fija cómo se calcula:

- pliegues hacia delante (`TimeSeriesSplit(3)`), con las filas ordenadas por fecha;
- la permutación, sobre el 20 % más reciente del entrenamiento, nunca sobre la validación;
- la métrica, el error absoluto medio. Sobre un mismo conjunto de días ordena igual que el error de la previsión del
  caso (unidades falladas por cada 100 vendidas), que es ese error absoluto entre una suma fija;
- sin muestreo: el entrenamiento tiene menos de 100.000 filas, el límite del método;
- modelos auxiliares con valores fijos y semilla 42, sin búsqueda. Sus cifras solo ordenan.

## Por qué consenso amplio

Las reglas del caso no fijan el escenario y el método propone consenso amplio cuando no lo dicen. Entra una variable
que marcan dos métodos. Con consenso fuerte bastaría que un método no la viera para perderla. Con todas las
candidatas, la lista apenas bajaría de las 117 columnas. El escenario se fija una vez, antes de ver el resultado.

## La pregunta al negocio

Antes de cortar, el método pide preguntar qué variables tienen que quedarse aunque salgan abajo en la votación. Entran
sin votar y ganan su par en el paso de «las que dicen lo mismo». La pregunta, para la dirección de operaciones de
tiendas a través del responsable del caso:

> ¿Qué variables tiene que conservar el modelo aunque predigan poco, porque el negocio las necesita para explicar la
> previsión o para actuar con ella?

Dos grupos tienen motivo escrito en los documentos del caso:

- **los efectos de la pregunta 4 de la ficha:** festivos, días SNAP, día de la semana, mes y precio medio de la semana
  anterior. La ficha los pide «como variables del modelo» para decir qué días cambia la venta;
- **la tienda y el departamento:** los planteamientos (§2, decisión 6) fijan un modelo para las 70 combinaciones «con la
  tienda y el departamento como variables».

Lo que se conteste se apunta en las reglas del caso, con su motivo, antes de ejecutar.

## Límites y preguntas abiertas

- **Las variables se miden a un día y el modelo prevé hasta 28.** En el entrenamiento, cada retardo lleva la venta
  real de la víspera. Al prever desde un origen, los retardos cortos pasan a ser previsiones a partir del segundo día
  del horizonte (matriz, «Cómo se calculan en la previsión recursiva»). La preselección puede valorar de más el
  retardo de un día, sobre todo en el modelo de dólares a 28 días. El método no trata este caso. Cuánto cambia la
  lista no se puede saber sin medirlo.
- **El tope de columnas del método no aplica.** Se cuenta por casos de la clase pequeña. Aquí el objetivo es una
  cantidad. El método no fija otro tope para un objetivo continuo. Si el responsable del caso quiere uno para Ridge, es un criterio nuevo.
- **El tiempo de cálculo no está medido.** La eliminación recursiva reentrena un bosque cada vez que quita una
  columna, en tres pliegues y dos objetivos. Si no cabe, el método deja usar la permutación sola.
- **Dos puntos llegarán en los pasos siguientes,** con su propia pregunta:
  - las columnas de eventos repetidas (codificación y `evento_<nombre>`) pueden formar un grupo ambiguo, que se
    pregunta uno a uno;
  - el día de la semana, el mes, los eventos y el día del mes valen lo mismo para todas las series de un día. Por la
    letra del método son «variables del momento». Son calendario conocido de antemano que se repite cada año, así que
    se propondrá no tratarlas como coyuntura.

## Lo que el responsable del caso puede decidir ya

1. Si se preselecciona así: completa en Ridge y solo los pasos de fuera y de una variante en HistGradientBoosting.
2. El modo: comparativo, o la permutación sola si se prefiere ahorrar tiempo de cálculo.
3. El escenario de votación: consenso amplio, fuerte o todas las candidatas.
4. Qué variables conserva el negocio sin votar, con su motivo.
