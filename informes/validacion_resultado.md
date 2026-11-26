# La validación del modelo · caso 69

Fecha de los datos: 2015-05-22. Sale de `informes/validacion.json`, generado por `scripts/16_validacion.py` el 2026-11-25. Estado: PARADO.

## El veredicto

- **Unidades, a 10 días: gana.** El modelo falla menos que la regla que menos falla en 12 de los 13 orígenes; hacían falta 10. Su ventaja es de +2,28 puntos, con un intervalo del 95 % de +1,23 a +3,49.
- **Dólares, a 28 días: gana.** El modelo falla menos que la regla que menos falla en 12 de los 13 orígenes; hacían falta 10. Su ventaja es de +2,06 puntos, con un intervalo del 95 % de +1,02 a +3,32.

Gana si cumple las dos condiciones de las reglas: al menos 10 orígenes de 13 con el intervalo entero por encima de cero. El intervalo sale de remuestrear 1.000 veces las 70 series enteras, con semilla 42.

## El error frente a las reglas

Error y sesgo por cada 100 vendidos, con las 70 series juntas en los 13 orígenes y sin el 25 de diciembre.

| Objetivo | Previsión | Error | Sesgo |
|---|---|---|---|
| unidades | el modelo | 15,64 | +3,25 |
| unidades | repetir la semana anterior | 22,20 | -1,64 |
| unidades | la media de los últimos 28 días | 21,64 | -3,58 |
| unidades | la media del mismo día de las 4 semanas anteriores | 17,93 | +0,28 |
| unidades | el trivial (la mediana) | 72,51 | -45,94 |
| unidades | el suavizado exponencial | 17,40 | -0,93 |
| dolares | el modelo | 17,37 | +2,12 |
| dolares | repetir la semana anterior | 23,92 | -2,42 |
| dolares | la media de los últimos 28 días | 22,28 | -0,99 |
| dolares | la media del mismo día de las 4 semanas anteriores | 19,44 | -0,94 |
| dolares | el trivial (la mediana) | 69,47 | -43,12 |
| dolares | el suavizado exponencial | 19,29 | -2,04 |

## El suavizado exponencial al lado

- **Unidades, a 10 días:** el modelo falla menos que el suavizado en 10 de 13 orígenes. La diferencia es de +1,75 puntos, con un intervalo de +0,51 a +3,28. Con las mismas pruebas, la lectura es «gana».
- **Dólares, a 28 días:** el modelo falla menos que el suavizado en 13 de 13 orígenes. La diferencia es de +1,91 puntos, con un intervalo de +0,30 a +3,92. Con las mismas pruebas, la lectura es «gana».

Es una lectura: el veredicto se mide solo frente a las tres reglas.

## La recomendación de cada departamento

Si el modelo falla de media más que la regla que menos falla en un departamento, se recomienda esa regla en él. El veredicto principal no cambia.

| Objetivo | Departamento | Error del modelo | Regla que menos falla | Error de la regla | Se recomienda |
|---|---|---|---|---|---|
| unidades | FOODS_1 | 20,33 | la media del mismo día de las 4 semanas anteriores | 23,07 | el modelo |
| unidades | FOODS_2 | 18,47 | la media del mismo día de las 4 semanas anteriores | 24,64 | el modelo |
| unidades | FOODS_3 | 12,53 | la media del mismo día de las 4 semanas anteriores | 14,71 | el modelo |
| unidades | HOBBIES_1 | 22,21 | la media del mismo día de las 4 semanas anteriores | 23,98 | el modelo |
| unidades | HOBBIES_2 | 52,17 | la media de los últimos 28 días | 51,20 | la media de los últimos 28 días |
| unidades | HOUSEHOLD_1 | 13,37 | la media del mismo día de las 4 semanas anteriores | 13,60 | el modelo |
| unidades | HOUSEHOLD_2 | 22,28 | la media del mismo día de las 4 semanas anteriores | 23,07 | el modelo |
| dolares | FOODS_1 | 23,40 | la media de los últimos 28 días | 26,83 | el modelo |
| dolares | FOODS_2 | 18,30 | la media del mismo día de las 4 semanas anteriores | 23,91 | el modelo |
| dolares | FOODS_3 | 14,33 | la media del mismo día de las 4 semanas anteriores | 15,88 | el modelo |
| dolares | HOBBIES_1 | 20,64 | la media del mismo día de las 4 semanas anteriores | 22,31 | el modelo |
| dolares | HOBBIES_2 | 62,44 | la media de los últimos 28 días | 57,97 | la media de los últimos 28 días |
| dolares | HOUSEHOLD_1 | 15,21 | la media del mismo día de las 4 semanas anteriores | 16,45 | el modelo |
| dolares | HOUSEHOLD_2 | 24,96 | la media del mismo día de las 4 semanas anteriores | 24,95 | la media del mismo día de las 4 semanas anteriores |

## Los días de evento y los días SNAP

| Objetivo | Días | Error del modelo | Sesgo del modelo | Error de la regla que menos falla en ellos |
|---|---|---|---|---|
| unidades | con algún evento | 17,78 | +6,51 | la media del mismo día de las 4 semanas anteriores: 18,81 |
| unidades | SNAP del estado de la tienda | 15,37 | +2,18 | la media del mismo día de las 4 semanas anteriores: 18,66 |
| dolares | con algún evento | 18,49 | +2,51 | la media del mismo día de las 4 semanas anteriores: 20,88 |
| dolares | SNAP del estado de la tienda | 16,72 | +1,16 | la media del mismo día de las 4 semanas anteriores: 19,34 |

## Lo que matiza la ventaja

Son lecturas con las mismas previsiones y las mismas filas medidas que el veredicto. No lo cambian.

### Unidades, a 10 días

- **La ventaja se concentra.** Las 5 series que más aportan suman +1,37 de los +2,28 puntos: WI_2 FOODS_3 (+0,51); WI_2 FOODS_2 (+0,40); WI_3 FOODS_3 (+0,24); CA_3 FOODS_3 (+0,14); CA_1 FOODS_3 (+0,08).
- **Sin algunas tiendas.** Sin WI_2 y WI_3 juntas, la ventaja es de +1,20 puntos. Sin cada tienda: sin CA_1, +2,44; sin CA_2, +2,42; sin CA_3, +2,39; sin CA_4, +2,38; sin TX_1, +2,36; sin TX_2, +2,39; sin TX_3, +2,41; sin WI_1, +2,41; sin WI_2, +1,46; sin WI_3, +2,12.
- **Remuestreando tiendas enteras**, el intervalo del 95 % de la ventaja va de +1,08 a +3,77 (10 tiendas, 1.000 remuestreos). El veredicto usa el de series.
- **Series en que alguna regla falla menos que el modelo:** 16 de 70: CA_1 HOBBIES_2; CA_2 FOODS_3; CA_2 HOUSEHOLD_1; CA_4 FOODS_1; CA_4 HOBBIES_2; CA_4 HOUSEHOLD_1; TX_2 HOBBIES_2; TX_2 HOUSEHOLD_2; TX_3 FOODS_3; TX_3 HOUSEHOLD_1; WI_1 FOODS_3; WI_1 HOBBIES_2; WI_2 HOBBIES_2; WI_2 HOUSEHOLD_2; WI_3 HOBBIES_1; WI_3 HOBBIES_2.
- **Eventos del calendario** del 23/05/2014 al 22/05/2015: 8 de 30 caen en días medidos. Sin cubrir: NBAFinalsStart (05/06/2014, fuera del horizonte); Father's day (15/06/2014, fuera del horizonte); NBAFinalsEnd (15/06/2014, fuera del horizonte); IndependenceDay (04/07/2014, fuera del horizonte); Eid al-Fitr (29/07/2014, fuera del horizonte); LaborDay (01/09/2014, fuera del horizonte); EidAlAdha (04/10/2014, fuera del horizonte); Halloween (31/10/2014, fuera del horizonte); Thanksgiving (27/11/2014, fuera del horizonte); Chanukah End (24/12/2014, fuera del horizonte); Christmas (25/12/2014, fuera del horizonte); NewYear (01/01/2015, fuera del horizonte); MartinLutherKingDay (19/01/2015, fuera del horizonte); ValentinesDay (14/02/2015, fuera del horizonte); PresidentsDay (16/02/2015, fuera del horizonte); LentStart (18/02/2015, fuera del horizonte); LentWeek2 (25/02/2015, fuera del horizonte); StPatricksDay (17/03/2015, fuera del horizonte); Pesach End (11/04/2015, fuera del horizonte); OrthodoxEaster (12/04/2015, fuera del horizonte); Cinco De Mayo (05/05/2015, fuera del horizonte); Mother's day (10/05/2015, fuera del horizonte).
- **Filas medidas por día de la semana:** lunes, 910; martes, 910; miércoles, 910; jueves, 910; viernes, 1.820; sábado, 1.820; domingo, 1.820.

### Dólares, a 28 días

- **La ventaja se concentra.** Las 5 series que más aportan suman +1,15 de los +2,06 puntos: WI_2 FOODS_3 (+0,45); WI_2 FOODS_2 (+0,34); WI_3 FOODS_3 (+0,20); WI_3 FOODS_2 (+0,09); WI_2 HOUSEHOLD_1 (+0,08).
- **Sin algunas tiendas.** Sin WI_2 y WI_3 juntas, la ventaja es de +0,99 puntos. Sin cada tienda: sin CA_1, +2,17; sin CA_2, +2,31; sin CA_3, +2,35; sin CA_4, +2,18; sin TX_1, +2,13; sin TX_2, +2,08; sin TX_3, +2,10; sin WI_1, +2,16; sin WI_2, +1,29; sin WI_3, +1,86.
- **Remuestreando tiendas enteras**, el intervalo del 95 % de la ventaja va de +0,79 a +3,80 (10 tiendas, 1.000 remuestreos). El veredicto usa el de series.
- **Series en que alguna regla falla menos que el modelo:** 19 de 70: CA_1 HOBBIES_2; CA_1 HOUSEHOLD_2; CA_2 FOODS_3; CA_3 FOODS_3; CA_3 HOBBIES_2; CA_4 FOODS_3; CA_4 HOBBIES_2; CA_4 HOUSEHOLD_1; TX_1 HOBBIES_2; TX_1 HOUSEHOLD_2; TX_2 HOBBIES_2; TX_2 HOUSEHOLD_2; TX_3 HOBBIES_2; TX_3 HOUSEHOLD_2; WI_1 HOBBIES_2; WI_2 HOBBIES_2; WI_2 HOUSEHOLD_2; WI_3 HOBBIES_2; WI_3 HOUSEHOLD_2.
- **Eventos del calendario** del 23/05/2014 al 22/05/2015: 29 de 30 caen en días medidos. Sin cubrir: Christmas (25/12/2014, fuera del error).
- **Filas medidas por día de la semana:** lunes, 3.640; martes, 3.640; miércoles, 3.640; jueves, 3.570; viernes, 3.640; sábado, 3.640; domingo, 3.640.


## La previsión sumada

La previsión de la cadena, de cada estado, de cada tienda y de cada categoría es la suma de las de sus series tal como se miden: acotadas en cero y, en unidades, redondeadas antes de sumar. El error y el sesgo salen de las filas sumadas de todos los orígenes juntos. Es una lectura: el veredicto no cambia.

### Unidades, a 10 días

En la cadena, el modelo falla menos que la regla que menos falla en cada origen en 9 de los 13 orígenes.

| Nivel | Grupo | Filas sumadas | Error del modelo | Sesgo del modelo | Regla que menos falla | Error de la regla | El modelo falla menos |
|---|---|---|---|---|---|---|---|
| cadena | las 70 series | 130 | 4,88 | +3,25 | la media del mismo día de las 4 semanas anteriores | 7,15 | sí |
| estado | CA | 130 | 5,59 | +3,86 | la media del mismo día de las 4 semanas anteriores | 7,30 | sí |
| estado | TX | 130 | 6,28 | +3,50 | la media del mismo día de las 4 semanas anteriores | 7,53 | sí |
| estado | WI | 130 | 6,87 | +2,07 | la media del mismo día de las 4 semanas anteriores | 12,63 | sí |
| tienda | CA_1 | 130 | 7,80 | +2,14 | la media del mismo día de las 4 semanas anteriores | 9,01 | sí |
| tienda | CA_2 | 130 | 9,60 | +5,14 | la media del mismo día de las 4 semanas anteriores | 9,72 | sí |
| tienda | CA_3 | 130 | 8,10 | +4,40 | la media del mismo día de las 4 semanas anteriores | 10,05 | sí |
| tienda | CA_4 | 130 | 8,50 | +4,23 | la media del mismo día de las 4 semanas anteriores | 9,04 | sí |
| tienda | TX_1 | 130 | 8,60 | +4,18 | la media del mismo día de las 4 semanas anteriores | 9,19 | sí |
| tienda | TX_2 | 130 | 7,51 | +4,13 | la media del mismo día de las 4 semanas anteriores | 8,68 | sí |
| tienda | TX_3 | 130 | 9,64 | +2,20 | la media del mismo día de las 4 semanas anteriores | 10,82 | sí |
| tienda | WI_1 | 130 | 8,59 | +0,58 | la media del mismo día de las 4 semanas anteriores | 9,34 | sí |
| tienda | WI_2 | 130 | 9,28 | +0,90 | la media del mismo día de las 4 semanas anteriores | 18,61 | sí |
| tienda | WI_3 | 130 | 10,36 | +5,55 | la media del mismo día de las 4 semanas anteriores | 14,17 | sí |
| categoría | FOODS | 130 | 5,52 | +3,31 | la media del mismo día de las 4 semanas anteriores | 8,92 | sí |
| categoría | HOBBIES | 130 | 9,21 | +0,28 | la media del mismo día de las 4 semanas anteriores | 10,29 | sí |
| categoría | HOUSEHOLD | 130 | 6,39 | +4,37 | la media del mismo día de las 4 semanas anteriores | 6,91 | sí |

### Dólares, a 28 días

En la cadena, el modelo falla menos que la regla que menos falla en cada origen en 12 de los 13 orígenes.

| Nivel | Grupo | Filas sumadas | Error del modelo | Sesgo del modelo | Regla que menos falla | Error de la regla | El modelo falla menos |
|---|---|---|---|---|---|---|---|
| cadena | las 70 series | 363 | 4,91 | +2,12 | la media del mismo día de las 4 semanas anteriores | 7,62 | sí |
| estado | CA | 363 | 5,87 | +3,08 | la media del mismo día de las 4 semanas anteriores | 7,45 | sí |
| estado | TX | 363 | 6,56 | +1,67 | la media del mismo día de las 4 semanas anteriores | 8,54 | sí |
| estado | WI | 363 | 7,22 | +1,03 | la media del mismo día de las 4 semanas anteriores | 13,11 | sí |
| tienda | CA_1 | 363 | 7,63 | +1,71 | la media del mismo día de las 4 semanas anteriores | 9,48 | sí |
| tienda | CA_2 | 363 | 11,74 | +7,48 | la media del mismo día de las 4 semanas anteriores | 10,02 | no |
| tienda | CA_3 | 363 | 7,76 | +1,47 | la media del mismo día de las 4 semanas anteriores | 9,74 | sí |
| tienda | CA_4 | 363 | 9,31 | +4,73 | la media del mismo día de las 4 semanas anteriores | 9,52 | sí |
| tienda | TX_1 | 363 | 8,60 | +3,39 | la media del mismo día de las 4 semanas anteriores | 9,41 | sí |
| tienda | TX_2 | 363 | 8,41 | +1,27 | la media del mismo día de las 4 semanas anteriores | 10,98 | sí |
| tienda | TX_3 | 363 | 9,13 | +0,63 | la media del mismo día de las 4 semanas anteriores | 10,67 | sí |
| tienda | WI_1 | 363 | 9,27 | -0,03 | la media del mismo día de las 4 semanas anteriores | 10,93 | sí |
| tienda | WI_2 | 363 | 9,39 | -1,26 | la media del mismo día de las 4 semanas anteriores | 18,48 | sí |
| tienda | WI_3 | 363 | 10,75 | +5,61 | la media del mismo día de las 4 semanas anteriores | 15,09 | sí |
| categoría | FOODS | 363 | 6,57 | +3,74 | la media del mismo día de las 4 semanas anteriores | 10,00 | sí |
| categoría | HOBBIES | 363 | 7,70 | -1,22 | la media del mismo día de las 4 semanas anteriores | 9,79 | sí |
| categoría | HOUSEHOLD | 363 | 6,57 | +0,07 | la media del mismo día de las 4 semanas anteriores | 8,45 | sí |


## Datos personales

No existe `config/fuentes/proteccion-datos.json`: los datos no pasaron por la protección. Las tablas son ventas por departamento y tienda y esta validación no usa ninguna columna sobre personas.

## Límites

- Los días previstos van del 23/05/2014 al 21/05/2015. La prueba final lo confirma una sola vez.
- El modelo se ajustó una vez con la construcción y no se reajusta en la validación. En la ejecución diaria se reajustaría.
- Las cifras miden lo vendido. Los datos no traen existencias, así que un día a cero no dice si había producto.
- El modelo detecta asociaciones con el calendario y con la venta pasada. No dice qué causa la venta.
- Si cambia la forma de vender, el error sube y hay que volver a medir.

## Lo que puede decidir el responsable del caso

- Aprobar el veredicto de cada objetivo y la recomendación por departamento, para pasar al informe.
- Pedir otra cosa antes del informe.
