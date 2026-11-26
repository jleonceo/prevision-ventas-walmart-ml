---
titulo: Propuesta de la búsqueda del modelo del caso 69 · qué algoritmos, con qué nivel y cómo se miden
estado: aprobada por el responsable del caso el 24/11/2026 tal cual («Sí, tal cual»); escrita por la sesión principal con `informes/modelo_minimo.json`, porque el agente paró antes de la ejecución real
fecha_documento: 2026-11-24
dueno: el responsable del caso (decide) · el equipo de análisis (propone)
fuente: `informes/modelo_minimo.json`; método `aprendizaje-automatico` §5 y `algoritmos.md`; planteamientos §2; reglas, apartado 6 y §7
---

# Propuesta de la búsqueda del modelo

## Lo que dice el modelo mínimo

HistGradientBoosting con sus valores por defecto, medido en cinco cortes del entrenamiento (`informes/modelo_minimo.json`):

| Objetivo | A un día, con la venta real | Recursivo, como se usará | Regla que menos falla | Cortes que gana en recursivo |
|---|---|---|---|---|
| unidades, 10 días | 14,3 | 16,2 | 18,0, la media del mismo día de las 4 semanas anteriores | 4 de 5 |
| dólares, 28 días | 15,6 | 17,5 | 19,6, la misma regla | 4 de 5 |

Error por cada 100 vendidos (reglas, apartado 6). La cifra a un día sale 1,9 puntos mejor que la recursiva en los dos objetivos:
mide algo que el modelo no hará nunca. La regla de la media del mismo día, comprobada por la sesión principal con otro
cálculo en el primer corte de unidades: 19,9, igual que el JSON.

## Lo que se propone

1. **Algoritmos: HistGradientBoosting y Ridge.** HistGradientBoosting es el de la lista del método para la previsión
   y el del modelo mínimo. Ridge es la comparación lineal que pide el recorrido de previsión con saltos de nivel
   (planteamientos §2). El bosque queda fuera: no tiene ficha copiada en el caso ni lista de columnas de la
   preselección, y cuesta unas cinco veces más que HistGradientBoosting por ajuste (6,1 s frente a 1,4 s).
2. **Nivel equilibrado:** 15 candidatos por algoritmo y 5 cortes, el valor por defecto del método. Prueba el 20,8 %
   del espacio de HistGradientBoosting y el 100 % del de Ridge, que tiene 13 combinaciones y va en rejilla entera.
3. **La búsqueda se mide en recursivo**, con la misma función que la validación y la producción: unos 14,5 minutos
   frente a 4,1 a un día. Elegir con la cifra a un día es elegir con la que no se usará.
4. **Los tres 25 de diciembre de cada serie entran en el ajuste y salen de la medida.** Son 210 de 82.250 filas; el
   modelo los reconoce por la columna de Navidad, y las reglas, apartado 6 solo los sacan del error.

## Lo que queda después

El ganador se aprueba antes de abrir la validación; la validación, una vez, con las tres reglas y el suavizado
exponencial.
