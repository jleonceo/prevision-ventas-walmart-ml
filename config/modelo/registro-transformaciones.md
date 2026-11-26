# Registro de transformaciones · caso 69

| Nº | Fecha | Qué | Sobre qué | Con qué | Antes | Después | Comprobación |
|---|---|---|---|---|---|---|---|
| T-001 | 18/11/2026 | Recorte de M5 al dataset del caso: 500 productos al azar (semilla 69) × 10 tiendas × 1.941 días; precios de esos productos; calendario entero | `sales_train_evaluation.csv`, `sell_prices.csv`, `calendar.csv` de M5 | `datasets_casos/69_prevision_ventas_walmart/recortar_m5.py` | 30.490 series, 3.049 productos | 5.000 series, 500 productos; 1.139.088 filas de precios | por otra vía (módulo `csv`, sin pandas): 5.000 de 5.000 filas idénticas al original, 11.846.331 unidades en los dos, precios 1.139.088 en los dos, calendario idéntico por SHA-256; caso en rojo: una unidad cambiada da 4.999 de 5.000 |
| T-002 | 18/11/2026 | Borrado de los originales de M5 | los 5 CSV y el ZIP de la descarga | a mano, por nombre | 450.472.284 bytes | 0 | `ls` de la carpeta de descarga, vacía |
| T-003 | 24/11/2026 | El Calendario del modelo (`modelo-datos.md` §6), con el diseño aprobado por el responsable del caso el 24/11/2026: las 14 columnas del calendario corregido sin cambios, más la semana anterior por el orden de las fechas, el periodo de cada día (construcción, validación o sin periodo) y las marcas de mes y semana parciales | `data/processed/calendario_corregido.parquet` | `scripts/04_modelado_datos.py` (`construir_calendario`), con el permiso del responsable del caso («Vale, sí, constrúyelo») | 1.969 filas y 14 columnas | `data/processed/calendario.parquet`: 1.969 filas y 18 columnas; 1.210 días de construcción, 365 de validación y 394 sin periodo; solo la semana 11101 sin anterior | validado antes de guardar (columnas, filas, clave, días seguidos, columnas copiadas iguales, marcas contra `parciales()`); por otra vía (módulo `csv` sobre `data/raw/calendar.csv`, sin pandas): 0 filas distintas de 1.969 en día, fecha, semana, anterior, periodo y marcas; casos en rojo: un día de menos y una columna copiada cambiada no pasan |
| T-004 | 24/11/2026 | Cascada del auditor del cierre del ETL: en `precio_medio_semana_anterior` solo cuentan los productos con precio desde cuatro semanas antes (reglas, apartado 5). La ficha R-009 la escribe el script; la ejecutó la sesión principal dentro de la cascada, no el agente de la petición 09 que nombra su campo 6, que es texto fijo del script | `data/processed/precios_corregido.parquet` y `data/processed/calendario.parquet` | `scripts/04_modelado_datos.py` y `scripts/05_transformacion_datos.py`, con el sí del responsable del caso a la tabla de la cascada («Sí, apruebo los dos») | `hechos_series.parquet` con 490 filas sin precio medio | `data/processed/hechos_series.parquet` con 2.450 filas sin precio medio (semanas 11101 a 11105); las otras 25 columnas, sin cambio en sus cifras de control | caso en rojo antes del cambio (16,25 en lugar de 2,5); por otra vía (venta ancha y numpy): vacíos iguales y diferencia máxima 7,1e-15; las cinco pruebas en verde con `-W error --datos`; huellas de `data/raw/` y de las demás tablas, iguales |

## Fichas de la corrección de datos (`scripts/03_correccion_datos.py`)

### R-001 · 23/11/2026 · calendario.date, de texto a fecha

1. **Tabla y columna:** calendario, `date` (`data/raw/calendar.csv`).
2. **Cómo estaba:** texto con el formato año-mes-día en 1.969 filas, con 0 vacías.
3. **Problema:** C-04 de la calidad: la fecha llega como texto.
4. **Decisión:** corrección técnicamente inequívoca (`criterios.md` §1), porque 0 fechas no se leen con el formato `%Y-%m-%d`. La pide la petición 07.
5. **Qué se hizo:** se lee con el formato explícito, sin inferirlo. Antes de dar la conversión por buena se cuentan las fechas que no se leen.

   ```python
   convertida = pd.to_datetime(calendario["date"], format="%Y-%m-%d", errors="coerce")
   no_convierten = int((convertida.isna() & calendario["date"].notna()).sum())   # tiene que ser 0
   calendario["date"] = convertida
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/03_correccion_datos.py` por la petición 07, lanzado con el sí del responsable del caso («Sí, lánzalo») el 23/11/2026.
7. **Comprobación:** 1.969 fechas leídas con 0 vacías, del 2011-01-29 al 2016-06-19. Al volver a texto dicen el mismo día que el origen en todas las filas (0 diferencias). Filas: 1.969 antes y 1.969 después.
8. **Cómo quedó:** `date` con tipo fecha (datetime64[us]) en `data/processed/calendario_corregido.parquet`.
9. **Cómo deshacer:** `calendario["date"] = calendario["date"].dt.strftime("%Y-%m-%d")`. El origen, `data/raw/calendar.csv`, no cambia.

### R-002 · 23/11/2026 · nombres de columna de calendario

1. **Tabla y columna:** calendario, `snap_CA`, `snap_TX` y `snap_WI`.
2. **Cómo estaba:** 3 nombres con mayúsculas. Las demás columnas de las tres tablas ya seguían la forma normalizada.
3. **Problema:** C-03 de la calidad: nombres que no siguen la forma normalizada.
4. **Decisión:** corrección técnicamente inequívoca (`criterios.md` §5), con 0 colisiones. El diccionario y las reglas nombran las columnas por su nombre de origen, así que el mapeo entero va aquí: `snap_CA` pasa a `snap_ca`; `snap_TX` pasa a `snap_tx`; `snap_WI` pasa a `snap_wi`.
5. **Qué se hizo:** cada nombre pasa a minúsculas, sin tildes y con guion bajo. El mapeo se calcula con esa regla sobre todas las columnas de las tres tablas, sin escribir ningún nombre a mano.

   ```python
   mapeo = {c: normalizar_nombre(c) for c in calendario.columns if normalizar_nombre(c) != c}
   calendario = calendario.rename(columns=mapeo)
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/03_correccion_datos.py` por la petición 07, lanzado con el sí del responsable del caso («Sí, lánzalo») el 23/11/2026.
7. **Comprobación:** 3 nombres cambiados. Los días SNAP de cada estado no cambian: CA, 650 antes y 650 después; TX, 650 antes y 650 después; WI, 650 antes y 650 después.
8. **Cómo quedó:** `data/processed/calendario_corregido.parquet` con `snap_ca`, `snap_tx` y `snap_wi`. La venta y los precios no cambian ningún nombre.
9. **Cómo deshacer:** `calendario = calendario.rename(columns={"snap_ca": "snap_CA", "snap_tx": "snap_TX", "snap_wi": "snap_WI"})`.

### R-003 · 23/11/2026 · lo que se deja sin cambios, con PC-01 a PC-06

1. **Tabla y columna:** venta, precios y calendario. Son 27 problemas de la calidad: C-01, C-02, C-05, C-06, C-07, C-08, C-09, C-10, C-11, C-12, C-13, C-14, C-15, C-16, C-17, C-18, C-19, C-20, C-21, C-22, C-23, C-24, C-25, C-26, C-27, C-28 y C-29.
2. **Cómo estaba:** como llega de `data/raw/`; cada problema está descrito en `informes/calidad-datos.json`.
3. **Problema:** los problemas de la calidad que no tienen corrección y sus cuestiones abiertas, PC-01 a PC-06.
4. **Decisión:** se usan los datos como están. Las cuestiones quedan decididas por la petición 07 con la opción que ofreció la calidad, copiada literal:
   - PC-01 (C-12): «son precios reales de productos baratos y se usan como están».
   - PC-02 (C-13): «son cambios reales de precio y se usan como están».
   - PC-03 (C-14): «es un cierre real de la tienda y se trata como el 25 de diciembre».
   - PC-04 (C-15): «se dejan como vendidas».
   - PC-05 (C-16): «son cambios reales de la venta y la serie se usa entera».
   - PC-06 (C-17): «son cambios reales de la venta y la serie se usa entera».
   El motivo de cada problema está en `informes/correccion-datos.json` (`sin_cambios`). Ninguno cambia una respuesta del caso: la petición lo midió antes de lanzarse.
5. **Qué se hizo:** ningún cambio. Se comprueba que ninguna fila ni valor cambia al deshacer el nombre nuevo y la fecha. Los días a cero de las 70 series se clasifican sin tocar ningún dato (`clases_de_ceros` del JSON).

   ```python
   diferencias = valores_iguales(antes, despues, mapeos, {"calendario": ("date", "%Y-%m-%d")})   # tiene que ser []
   ```

6. **Quién y con qué permiso:** decide el responsable del caso con el sí a la petición 07; el agente analista-preparacion-datos ejecuta `scripts/03_correccion_datos.py` por la petición 07, lanzado con el sí del responsable del caso («Sí, lánzalo») el 23/11/2026.
7. **Comprobación:** 0 valores distintos. Unidades: total, 9.327.191 antes y 9.327.191 después; construcción, 7.003.244 antes y 7.003.244 después; validación, 2.323.947 antes y 2.323.947 después. Suma de `sell_price`: 3.750.011,81 antes y 3.750.011,81 después. Días de serie a cero por clase: construcción: cierre de la tienda 175, 25 de diciembre 35, demanda intermitente 2.171, resto 35; validación: cierre de la tienda 56, 25 de diciembre 12, demanda intermitente 201, resto 2.
8. **Cómo quedó:** las tres tablas de `data/processed/` con los mismos valores que `data/raw/`.
9. **Cómo deshacer:** no hay nada que deshacer. Si una decisión cambia, se añade una ficha nueva que lo diga.

## Fichas de la transformación de datos (`scripts/05_transformacion_datos.py`)

### R-004 · 24/11/2026 · hechos_series: la tabla de series con la venta en dólares (cruces 1 a 5)

1. **Tabla y columna:** `data/processed/hechos_series.parquet` (nueva): `store_id`, `dept_id`, `d`, `cat_id`, `state_id`, `unidades`, `dolares`, las columnas del Calendario y `snap`.

2. **Cómo estaba:** la venta llega con una fila por producto y tienda (5.000 filas) y un día por columna (1.575 días); el precio, por producto, tienda y semana; el Calendario, por día.

3. **Problema o finalidad:** las preguntas 1, 2 y 4 se miden en una fila por departamento en una tienda y día (reglas, apartado 3 y §5; diseño §3 y §8).

4. **Decisión:** reglas de transformación, apartado 1; diseño aprobado, cruces 1 a 5. Un día sin precio suma cero dólares; un día con venta y sin precio para el script (reglas, apartado 5).

5. **Qué se hizo:** la venta pasa a filas, se une con la semana del Calendario, el precio y el departamento con los controles de integracion-datos y se suma por serie y día en céntimos enteros.

   ```python
   larga = venta.melt(id_vars=["item_id", "store_id"], value_vars=dias, var_name="d", value_name="unidades")
   larga = larga.merge(calendario[["d", "date", "wm_yr_wk"]], on="d", how="left", validate="many_to_one", indicator=True)   # cruce 1
   larga = larga.merge(precios, on=["item_id", "store_id", "wm_yr_wk"], how="left", validate="many_to_one", indicator=True)   # cruce 2
   # un día con venta y sin precio para antes de calcular; los días sin precio suman 0 céntimos
   larga["centimos"] = larga["unidades"] * round(larga["sell_price"] * 100)
   larga = larga.merge(dim_producto, on="item_id", how="left", validate="many_to_one", indicator=True)   # cruce 3
   series = larga.groupby(["store_id", "dept_id", "cat_id", "d"]).agg(unidades=("unidades", "sum"), centimos=("centimos", "sum"))
   series = series.merge(dim_tienda, ...)   # cruce 4
   series = series.merge(calendario, ...)   # cruce 5; snap = snap_ca, snap_tx o snap_wi según state_id
   series["dolares"] = series["centimos"] / 100
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/05_transformacion_datos.py` por la petición 09, con las reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`config/negocio/reglas-transformacion.md`) y el diseño aprobado por el responsable del caso el 24/11/2026.

7. **Comprobación:** venta en filas: 7.875.000 filas, 9.327.191 unidades y 24.982.728,54 dólares; 0 días con venta y sin precio; 1.892.989 días sin precio. Tabla de series: 110.250 filas con la clave sin repetir; construcción 84.700 filas, 7.003.244 unidades y 18.167.205,84 dólares; validación 25.550 filas, 2.323.947 unidades y 6.815.522,70 dólares. Las sumas de los 5 cruces coinciden antes y después.

8. **Cómo quedó:** 110.250 filas y 26 columnas en `data/processed/hechos_series.parquet`.

9. **Cómo deshacer:** borrar `data/processed/hechos_series.parquet`. Las tablas de entrada no cambian.

Regla: `series_y_dolares` · huella `24c7bcbb6951`

### R-005 · 24/11/2026 · hechos_series: cierre_tienda, fuera_del_error y clase_cero

1. **Tabla y columna:** `hechos_series`: `cierre_tienda`, `fuera_del_error` y `clase_cero` (nuevas).

2. **Cómo estaba:** los ceros de las series no decían si eran un cierre, un 25 de diciembre o una demanda baja.

3. **Problema o finalidad:** medir el error sin los días que se saben de antemano y describir los ceros (reglas, apartado 5, D8, y §6).

4. **Decisión:** reglas de transformación, apartado 1. Las tres se conocen después del día; clase_cero usa la media del periodo entero y nunca entra como variable del modelo.

5. **Qué se hizo:** se marcan con la regla de `clasificar_ceros` de la corrección, sin importarla.

   ```python
   df["cierre_tienda"] = df.groupby(["store_id", "d"])["unidades"].transform("sum") == 0
   df["fuera_del_error"] = navidad | df["cierre_tienda"]
   media = df["unidades"].where(~df["cierre_tienda"]).groupby([store_id, dept_id, periodo]).transform("mean")
   clase = np.select([cero & cierre, cero & ~cierre & navidad, cero & ~cierre & ~navidad & (media < 10), cero],
                     ["cierre", "25_diciembre", "demanda_intermitente", "resto"])   # vacía en los días con venta
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/05_transformacion_datos.py` por la petición 09, con las reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`config/negocio/reglas-transformacion.md`) y el diseño aprobado por el responsable del caso el 24/11/2026.

7. **Comprobación:** cierre_tienda: 175 y 56 días de serie en construcción y validación; fuera_del_error: 217 y 70. clase_cero en la construcción: cierre 175, 25 de diciembre 35, demanda intermitente 2.171 y resto 35; en la validación: 56, 12, 201 y 2.

8. **Cómo quedó:** tres columnas más en `data/processed/hechos_series.parquet`; los datos de venta no cambian.

9. **Cómo deshacer:** quitar las tres columnas: `df = df.drop(columns=["cierre_tienda", "fuera_del_error", "clase_cero"])`.

Regla: `marcas` · huella `d48009a01f72`

### R-006 · 24/11/2026 · hechos_series: precio_medio_semana_anterior (cruces 6 y 7)

1. **Tabla y columna:** `hechos_series`: `precio_medio_semana_anterior` (nueva).

2. **Cómo estaba:** el precio va por producto, tienda y semana; la serie va por departamento y día.

3. **Problema o finalidad:** el precio que entra en la previsión de un día es el de la semana anterior (reglas, apartado 5, D9; ficha, pregunta 4).

4. **Decisión:** media simple de los productos del departamento con precio en la tienda esa semana, unida por `wm_yr_wk_anterior` del Calendario (el responsable del caso, 24/11/2026). Es un nivel: nunca se suma ni se redondea.

5. **Qué se hizo:** se une el departamento a cada precio, se hace la media por tienda, departamento y semana y se une a cada día por su semana anterior.

   ```python
   precios = precios.merge(dim_producto[["item_id", "dept_id"]], on="item_id", how="left", validate="many_to_one")   # cruce 6
   medio = precios.groupby(["store_id", "dept_id", "wm_yr_wk"]).agg(precio_medio_semana_anterior=("sell_price", "mean"))
   series = series.merge(medio.rename(columns={"wm_yr_wk": "wm_yr_wk_anterior"}),
                         on=["store_id", "dept_id", "wm_yr_wk_anterior"], how="left", validate="many_to_one")   # cruce 7
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/05_transformacion_datos.py` por la petición 09, con las reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`config/negocio/reglas-transformacion.md`) y el diseño aprobado por el responsable del caso el 24/11/2026.

7. **Comprobación:** 15.750 grupos de tienda, departamento y semana con algún precio; 0 sin ninguno. Quedan vacías 490 filas, las de la semana 11101, sin anterior.

8. **Cómo quedó:** una columna más en `data/processed/hechos_series.parquet`.

9. **Cómo deshacer:** quitar la columna: `df = df.drop(columns="precio_medio_semana_anterior")`.

Regla: `precio_medio` · huella `2f4a5530c863`

### R-007 · 24/11/2026 · dim_producto: una fila por producto

1. **Tabla y columna:** `data/processed/dim_producto.parquet` (nueva): `item_id`, `dept_id` y `cat_id`.

2. **Cómo estaba:** el departamento y la categoría de cada producto venían repetidos en cada fila de la venta.

3. **Problema o finalidad:** dimensión de producto del diseño (§3); la usan los cruces 3 y 6.

4. **Decisión:** reglas de transformación, apartado 2.

5. **Qué se hizo:** una fila por producto con su departamento y su categoría.

   ```python
   dim_producto = venta[["item_id", "dept_id", "cat_id"]].drop_duplicates().sort_values("item_id")
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/05_transformacion_datos.py` por la petición 09, con las reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`config/negocio/reglas-transformacion.md`) y el diseño aprobado por el responsable del caso el 24/11/2026.

7. **Comprobación:** 500 filas, 0 filas con la clave repetida. Por departamento: FOODS_1 43, FOODS_2 61, FOODS_3 129, HOBBIES_1 73, HOBBIES_2 27, HOUSEHOLD_1 93, HOUSEHOLD_2 74.

8. **Cómo quedó:** 500 filas y 3 columnas en `data/processed/dim_producto.parquet`.

9. **Cómo deshacer:** borrar `data/processed/dim_producto.parquet`.

Regla: `dim_producto` · huella `d7033740a4b4`

### R-008 · 24/11/2026 · dim_tienda: una fila por tienda

1. **Tabla y columna:** `data/processed/dim_tienda.parquet` (nueva): `store_id` y `state_id`.

2. **Cómo estaba:** el estado de cada tienda venía repetido en cada fila de la venta.

3. **Problema o finalidad:** dimensión de tienda del diseño (§3); la usa el cruce 4 y la suma de la pregunta 3.

4. **Decisión:** reglas de transformación, apartado 3.

5. **Qué se hizo:** una fila por tienda con su estado.

   ```python
   dim_tienda = venta[["store_id", "state_id"]].drop_duplicates().sort_values("store_id")
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/05_transformacion_datos.py` por la petición 09, con las reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`config/negocio/reglas-transformacion.md`) y el diseño aprobado por el responsable del caso el 24/11/2026.

7. **Comprobación:** 10 filas, 0 filas con la clave repetida. Por estado: CA 4, TX 3, WI 3.

8. **Cómo quedó:** 10 filas y 2 columnas en `data/processed/dim_tienda.parquet`.

9. **Cómo deshacer:** borrar `data/processed/dim_tienda.parquet`.

Regla: `dim_tienda` · huella `0682d0ca3e41`

### R-009 · 24/11/2026 · hechos_series: precio_medio_semana_anterior (cruces 6 y 7)

1. **Tabla y columna:** `hechos_series`: `precio_medio_semana_anterior` (nueva).

2. **Cómo estaba:** el precio va por producto, tienda y semana; la serie va por departamento y día.

3. **Problema o finalidad:** el precio que entra en la previsión de un día es el de la semana anterior (reglas, apartado 5, D9; ficha, pregunta 4).

4. **Decisión:** media simple de los productos del departamento con precio en la tienda esa semana que ya lo tenían cuatro semanas antes, unida por `wm_yr_wk_anterior` del Calendario (el responsable del caso, 24/11/2026; reglas, apartado 5). Un producto entra la semana de su primera venta: contado desde entonces, avisaría de esa venta dentro del horizonte. Es un nivel: nunca se suma ni se redondea. Cambia la regla `precio_medio`, que tenía la huella `2f4a5530c863`.

5. **Qué se hizo:** se une el departamento a cada precio, se hace la media por tienda, departamento y semana y se une a cada día por su semana anterior.

   ```python
   precios = precios.merge(dim_producto[["item_id", "dept_id"]], on="item_id", how="left", validate="many_to_one")   # cruce 6
   posicion = precios["wm_yr_wk"].map(orden_de_las_semanas)   # por el orden de las fechas
   cuenta = posicion - posicion.groupby([precios["store_id"], precios["item_id"]]).transform("min") >= 4
   medio = (precios.assign(precio=precios["sell_price"].where(cuenta))
            .groupby(["store_id", "dept_id", "wm_yr_wk"]).agg(precio_medio_semana_anterior=("precio", "mean")))
   series = series.merge(medio.rename(columns={"wm_yr_wk": "wm_yr_wk_anterior"}),
                         on=["store_id", "dept_id", "wm_yr_wk_anterior"], how="left", validate="many_to_one")   # cruce 7
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-datos ejecuta `scripts/05_transformacion_datos.py` por la petición 09, con las reglas de transformación aprobadas por el responsable del caso el 24/11/2026 (`config/negocio/reglas-transformacion.md`) y el diseño aprobado por el responsable del caso el 24/11/2026.

7. **Comprobación:** 15.750 grupos de tienda, departamento y semana con algún precio; 0 sin ninguno. En 280 no cuenta ningún producto; quedan fuera 19.769 precios de productos con menos de cuatro semanas de precio. Quedan vacías 2.450 filas, las de las semanas 11101, 11102, 11103, 11104, 11105: sin anterior o sin ningún producto que cuente.

8. **Cómo quedó:** una columna más en `data/processed/hechos_series.parquet`.

9. **Cómo deshacer:** quitar la columna: `df = df.drop(columns="precio_medio_semana_anterior")`.

Regla: `precio_medio` · huella `77cca35c6cc5`

## Fichas de la preparación para el modelo (`scripts/10_particion.py`)

### R-010 · 24/11/2026 · partición en entrenamiento y validación

1. **Tabla y columna:** `data/processed/hechos_series.parquet`, columna `periodo`; salen `data/processed/hechos_series_entrenamiento.parquet` y `data/processed/hechos_series_validacion.parquet` (nuevas).

2. **Cómo estaba:** una sola tabla de 110.250 filas, con el periodo de cada día puesto en el paso 2.

3. **Problema o finalidad:** entrenar sin que nada aprenda de la validación (preparacion-modelo §1).

4. **Decisión:** partición por fecha, la que apartó el paso 2 (reglas-negocio §5, «Fechas»). No se vuelve a partir: entrenamiento son las filas de la construcción y validación las de la validación. No hay lote de producción: la prueba final está fuera del caso. Sin azar; la semilla 42 se escribe porque el método la pide.

5. **Qué se hizo:** se separan las filas de cada periodo con una máscara, se comprueba que cada parte son exactamente esas filas y que sus fechas son los tramos de `informes/transformacion-datos.json`. Se guardan solo con todas las comprobaciones en verde.

   ```python
   partes = {parte: tabla[tabla["periodo"] == periodo].sort_values(["store_id", "dept_id", "d"]).reset_index(drop=True)
             for parte, periodo in {"entrenamiento": "construccion", "validacion": "validacion"}.items()}
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/10_particion.py` por la petición de la partición y la matriz de la sesión principal, el 24/11/2026.

7. **Comprobación:** entrenamiento con 84.700 filas, 7.003.244 unidades y 18.167.205,84 dólares, del 29/01/2011 al 22/05/2014; validación con 25.550 filas, 2.323.947 unidades y 6.815.522,70 dólares, del 23/05/2014 al 22/05/2015, 365 días; 70 combinaciones y 26 columnas en cada parte. 0 filas compartidas, 0 perdidas y 0 repetidas; cada parte igual a su periodo; partes releídas iguales a las separadas. Cada comprobación tiene su caso en rojo en `tests/probar_10_particion.py`. Huella de `hechos_series.parquet` igual antes y después (`31a6a1fbac4f…`).

8. **Cómo quedó:** `hechos_series_entrenamiento.parquet` (huella `5f59c9aed638…`) y `hechos_series_validacion.parquet` (huella `08653136219d…`); el detalle, en `informes/particion.json`.

9. **Cómo deshacer:** borrar las dos partes y `informes/particion.json`. La tabla de series no cambia.

### R-011 · 24/11/2026 · matriz de transformaciones aprobada

1. **Tabla y columna:** `data/processed/hechos_series_entrenamiento.parquet` y `hechos_series_validacion.parquet`; la receta, en `config/modelo/matriz_transformaciones.md`.

2. **Cómo estaba:** la matriz propuesta por el agente analista-preparacion-modelo, con cuestión 001 abierta y dos candidatas suyas sin aprobar.

3. **Problema o finalidad:** fijar qué entra en los dos modelos de previsión y cómo se transforma (preparacion-modelo §3).

4. **Decisión:** El responsable del caso aprobó la matriz el 24/11/2026 («Sí, apruébala») con cuatro respuestas: cuestión 001 con los productos que ya tenían precio cuatro semanas antes; fuera los primeros 35 días de cada serie en vez de 29, y el precio medio sin relleno ni marca; `evento_<nombre>` y `dia_del_mes`, candidatas.

5. **Qué se hizo:** ningún dato cambia todavía. Las variables nuevas y la salida de los 35 primeros días se aplican en la petición siguiente, con su propia ficha y sus recuentos.

6. **Quién y con qué permiso:** la sesión principal, con la aprobación del responsable del caso.

7. **Comprobación:** medido por la sesión principal el 24/11/2026 sobre las dos partes: el precio medio está vacío en los 35 primeros días de cada una de las 70 series (2.450 días) y en ninguno más; en la validación, 0 vacíos.

8. **Cómo quedó:** la matriz, en estado aprobada.

9. **Cómo deshacer:** volver la matriz a «propuesta» y abrir de nuevo cuestión 001.

## Fichas de las variables del modelo (`scripts/11_variables_modelo.py`)

### R-012 · 24/11/2026 · `hechos_modelo_entrenamiento` y `hechos_modelo_validacion`: retardos y medias de unidades

1. **Tabla y columna:** `hechos_modelo_entrenamiento` y `hechos_modelo_validacion` (nuevas): `unidades_lag_1` a `unidades_lag_7`, `unidades_lag_14`, `unidades_lag_21`, `unidades_lag_28`, `unidades_media_7` y `unidades_media_28`.

2. **Cómo estaba:** la venta en unidades de cada día, sin su historia en la misma fila.

3. **Problema o finalidad:** el modelo de unidades prevé con la venta hasta la víspera (reglas, apartado 5, «Lo que se sabe el día de prever»).

4. **Decisión:** la fijan los planteamientos (§2, decisión 7) con la matriz aprobada: dentro de cada serie ordenada por fecha, solo con días anteriores al de la fila. La misma función sirve para la previsión recursiva. Las dos partes se calculan sobre la historia unida, así que los primeros días de la validación toman los últimos del entrenamiento. Salen del objetivo: el modelo de dólares usa solo las de dólares y el de unidades, las suyas.

5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.

   ```python
   comprobar_sin_huecos(historia)   # para si una serie tiene un día que falta o repetido
   grupo = historia.sort_values(["store_id", "dept_id", "date"]).groupby(["store_id", "dept_id"])["unidades"]
   df["unidades_lag_k"] = grupo.shift(k)   # k = 1..7, 14, 21, 28
   df["unidades_media_w"] = grupo.shift(1) agrupado por serie .rolling(w, min_periods=w).mean()   # w = 7, 28
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/11_variables_modelo.py` por la petición de la sesión principal del 24/11/2026 (variables nuevas, preprocesador y propuesta de preselección), con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).

7. **Comprobación:** entrenamiento: `unidades_lag_1` suma 6.844.472, `unidades_lag_28` 6.792.938 y `unidades_media_28` 6.817.389,54; validación: 2.323.283, 2.323.072 y 2.323.660,96. 0 vacíos en las dos tablas. Rehechas por otro camino (unión por serie y fecha t − k): 0 filas distintas.

8. **Cómo quedó:** 12 columnas más en cada tabla.

9. **Cómo deshacer:** quitar las columnas: `df = df.drop(columns=vp.nombres_variables("unidades"))`.

Regla: `retardos_unidades` · huella `58eb3eaa1722`

### R-013 · 24/11/2026 · `hechos_modelo_entrenamiento` y `hechos_modelo_validacion`: retardos y medias de dólares

1. **Tabla y columna:** `hechos_modelo_entrenamiento` y `hechos_modelo_validacion` (nuevas): `dolares_lag_1` a `dolares_lag_7`, `dolares_lag_14`, `dolares_lag_21`, `dolares_lag_28`, `dolares_media_7` y `dolares_media_28`.

2. **Cómo estaba:** la venta en dólares de cada día, sin su historia en la misma fila.

3. **Problema o finalidad:** el modelo de dólares prevé con la venta hasta la víspera (reglas, apartado 5, «Lo que se sabe el día de prever»).

4. **Decisión:** la fijan los planteamientos (§2, decisión 7) con la matriz aprobada: dentro de cada serie ordenada por fecha, solo con días anteriores al de la fila. La misma función sirve para la previsión recursiva. Las dos partes se calculan sobre la historia unida, así que los primeros días de la validación toman los últimos del entrenamiento. Salen del objetivo: el modelo de dólares usa solo las de dólares y el de unidades, las suyas.

5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.

   ```python
   comprobar_sin_huecos(historia)   # para si una serie tiene un día que falta o repetido
   grupo = historia.sort_values(["store_id", "dept_id", "date"]).groupby(["store_id", "dept_id"])["dolares"]
   df["dolares_lag_k"] = grupo.shift(k)   # k = 1..7, 14, 21, 28
   df["dolares_media_w"] = grupo.shift(1) agrupado por serie .rolling(w, min_periods=w).mean()   # w = 7, 28
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/11_variables_modelo.py` por la petición de la sesión principal del 24/11/2026 (variables nuevas, preprocesador y propuesta de preselección), con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).

7. **Comprobación:** entrenamiento: `dolares_lag_1` suma 17.768.502,62, `dolares_lag_28` 17.595.206,40 y `dolares_media_28` 17.679.525,13; validación: 6.811.631,97, 6.765.303,59 y 6.789.408,83. 0 vacíos en las dos tablas. Rehechas por otro camino (unión por serie y fecha t − k): 0 filas distintas.

8. **Cómo quedó:** 12 columnas más en cada tabla.

9. **Cómo deshacer:** quitar las columnas: `df = df.drop(columns=vp.nombres_variables("dolares"))`.

Regla: `retardos_dolares` · huella `58eb3eaa1722`

### R-014 · 24/11/2026 · `hechos_modelo_entrenamiento` y `hechos_modelo_validacion`: productos_con_precio_semana_anterior

1. **Tabla y columna:** `hechos_modelo_entrenamiento` y `hechos_modelo_validacion` (nueva): `productos_con_precio_semana_anterior`.

2. **Cómo estaba:** el precio va por producto, tienda y semana; no había ninguna cifra de los productos que se venden en cada departamento.

3. **Problema o finalidad:** que el modelo vea la llegada de productos nuevos, que en una serie multiplica la venta por 7,2 (ficha; planteamientos §2, decisión 7).

4. **Decisión:** cuestión 001, resuelta por el responsable del caso el 24/11/2026: cuentan los productos del departamento con precio en la tienda la semana anterior que ya tenían precio cuatro semanas antes, la regla del precio medio (reglas, apartado 5, «El precio»). Las semanas se ordenan por sus fechas, porque el código salta al cambiar de año.

5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.

   ```python
   posicion = precios["wm_yr_wk"].map(orden_de_las_semanas)   # por el orden de las fechas
   cuenta = posicion - posicion.groupby([store_id, item_id]).transform("min") >= 4
   conteo = precios.assign(cuenta=cuenta).groupby(["store_id", "dept_id", "wm_yr_wk"])["cuenta"].sum()
   df = df.merge(conteo, left_on=[..., "wm_yr_wk_anterior"], right_on=[..., "wm_yr_wk"], validate="many_to_one")
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/11_variables_modelo.py` por la petición de la sesión principal del 24/11/2026 (variables nuevas, preprocesador y propuesta de preselección), con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).

7. **Comprobación:** en el entrenamiento suma 4.056.817, de 3 a 123 por fila. En la validación suma 1.752.315, de 19 a 129. 0 vacíos.

8. **Cómo quedó:** una columna más en cada tabla.

9. **Cómo deshacer:** quitar la columna: `df = df.drop(columns="productos_con_precio_semana_anterior")`.

Regla: `productos_con_precio` · huella `9e3849b43fd4`

### R-015 · 24/11/2026 · `hechos_modelo_entrenamiento` y `hechos_modelo_validacion`: evento_<nombre>

1. **Tabla y columna:** `hechos_modelo_entrenamiento` y `hechos_modelo_validacion` (nuevas): una columna `evento_<nombre>` por evento, 30 en total.

2. **Cómo estaba:** el evento de un día está en `event_name_1` o en `event_name_2`.

3. **Problema o finalidad:** «Father's day» cae en `event_name_2` en la validación y en el entrenamiento solo en `event_name_1`; con las dos columnas por separado, ese día sale sin evento (matriz, candidatas).

4. **Decisión:** matriz aprobada, respuesta 3: candidata al lado de `event_name_1` y `event_name_2`. La lista de eventos sale solo del entrenamiento. El nombre de la columna es el del evento tal cual, sin cambiarlo.

5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.

   ```python
   eventos = sorted(set(ent["event_name_1"].dropna()) | set(ent["event_name_2"].dropna()))
   df[f"evento_{e}"] = ((df["event_name_1"] == e) | (df["event_name_2"] == e)).astype(int)
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/11_variables_modelo.py` por la petición de la sesión principal del 24/11/2026 (variables nuevas, preprocesador y propuesta de preselección), con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).

7. **Comprobación:** 30 eventos en el entrenamiento; 0 nuevos en la validación. Días de serie con algún evento: 6.720 en el entrenamiento y 2.030 en la validación.

8. **Cómo quedó:** 30 columnas de 0 y 1 más en cada tabla.

9. **Cómo deshacer:** quitar las columnas que empiezan por `evento_`.

Regla: `eventos` · huella `82aa9eea6a3c`

### R-016 · 24/11/2026 · `hechos_modelo_entrenamiento` y `hechos_modelo_validacion`: dia_del_mes

1. **Tabla y columna:** `hechos_modelo_entrenamiento` y `hechos_modelo_validacion` (nueva): `dia_del_mes`.

2. **Cómo estaba:** la fecha entera, en `date`.

3. **Problema o finalidad:** los días SNAP caen siempre en los días 1 a 15 del mes: el día del mes da esa quincena aunque no haya SNAP (matriz, candidatas).

4. **Decisión:** matriz aprobada, respuesta 4: candidata.

5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.

   ```python
   df["dia_del_mes"] = df["date"].dt.day
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/11_variables_modelo.py` por la petición de la sesión principal del 24/11/2026 (variables nuevas, preprocesador y propuesta de preselección), con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).

7. **Comprobación:** de 1 a 31 en el entrenamiento; 0 vacíos en las dos tablas.

8. **Cómo quedó:** una columna más en cada tabla.

9. **Cómo deshacer:** quitar la columna: `df = df.drop(columns="dia_del_mes")`.

Regla: `dia_del_mes` · huella `33a2bb11106d`

### R-017 · 24/11/2026 · hechos_modelo_entrenamiento: salen los primeros 35 días de cada serie

1. **Tabla y columna:** `hechos_modelo_entrenamiento`: filas.

2. **Cómo estaba:** el entrenamiento tenía 84.700 filas, 70 series con 1.210 días cada una.

3. **Problema o finalidad:** los primeros días de cada serie no tienen la historia que piden las variables: 29 por los retardos y 6 más porque el precio medio de la semana anterior está vacío en las cinco primeras semanas (reglas, apartado 7, «Población del análisis»).

4. **Decisión:** lo fijan los planteamientos (§2, decisión 7) con la respuesta 2 de la matriz aprobada (el responsable del caso, 24/11/2026): salen 35 días, no 29. La validación no pierde ninguna fila. No cambian ninguna respuesta: son días de la construcción de 2011, fuera de la validación donde se decide y se mide el modelo.

5. **Qué se hizo:** con `scripts/variables_prevision.py`, desde `scripts/11_variables_modelo.py`.

   ```python
   puesto = ent.groupby(["store_id", "dept_id"])["date"].rank(method="first")
   ent = ent[puesto > 35]
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo ejecuta `scripts/11_variables_modelo.py` por la petición de la sesión principal del 24/11/2026 (variables nuevas, preprocesador y propuesta de preselección), con la matriz de transformaciones aprobada por el responsable del caso el 24/11/2026 («Sí, apruébala»).

7. **Comprobación:** salen 2.450 filas, del 29/01/2011 al 04/03/2011. Llevan 157.519 unidades y 394.448,77 dólares. Quedan 82.250 filas. Después, 0 vacíos en las variables nuevas y en el precio medio.

8. **Cómo quedó:** `hechos_modelo_entrenamiento.parquet` con 82.250 filas; las quitadas siguen en `hechos_series_entrenamiento.parquet`.

9. **Cómo deshacer:** volver a unir las filas quitadas desde `hechos_series_entrenamiento.parquet`; sus retardos y su precio medio salen vacíos, así que la validación de vacíos del script tendría que cambiar con ellas.

Regla: `primeros_dias` · huella `70fd4542d4b1`

## Fichas de la preselección de variables (`scripts/13_preseleccion.py`)

### R-018 · 24/11/2026 · preselección de variables: listas de columnas y escenario

1. **Tabla y columna:** las columnas de salida del preprocesador de cada objetivo (`scripts/preparacion_prevision.py`), ajustado con `hechos_modelo_entrenamiento`.

2. **Cómo estaba:** las dos listas tenían todas las columnas de salida del preprocesador.

3. **Problema o finalidad:** Ridge es lineal y el método pide preseleccionar siempre; a HistGradientBoosting solo se le quita lo que no puede entrar y se deja una variante por variable.

4. **Decisión:** reglas, apartado 7, «Preselección de variables» (el responsable del caso, 24/11/2026): modo comparativo, escenario «consenso amplio»; las obligatorias entran sin votar. No se usó la validación.

5. **Qué se hizo:** `scripts/13_preseleccion.py`. La lista se aplica después del preprocesador; no cambia la tabla.

   ```python
   x = construir_preprocesador(objetivo, columnas_evento).fit_transform(entrenamiento)
   votos = mi_por_encima_del_salto + (rfecv.ranking_ == 1) + permutacion_por_encima_del_salto
   ridge = obligatorias + votadas_con_2_o_mas - las_de_menos_mi_en_cada_par_spearman_0_5
   ```

6. **Quién y con qué permiso:** el agente analista-preparacion-modelo deja `scripts/13_preseleccion.py` por la petición de la sesión principal del 24/11/2026, con lo aprobado por el responsable del caso en las reglas, apartado 7 («Sí, apruébalo»).

7. **Comprobación:** las seis validaciones del método, apartado 8 y los controles de obligatorias, pliegues por fecha y reserva reciente, en `informes/preseleccion.json`. El grupo de los eventos (dos codificaciones del mismo evento) queda para el responsable del caso como P-01, con sus dos opciones; mientras, las dos codificaciones siguen en las dos listas.

8. **Cómo quedó:**
   - **unidades, Ridge:** 104 columnas de 117: `store_id` (10 columnas); `dept_id` (7 columnas); `weekday` (7 columnas); `month` (12 columnas); `event_name_1` (31 columnas); `event_name_2` (4 columnas); `snap`; `evento_<nombre>` (30 columnas); `precio_medio_semana_anterior`; `unidades_media_7`.
   - **unidades, HistGradientBoosting:** 117 columnas, las de salida del preprocesador que pueden entrar.
   - **dolares, Ridge:** 104 columnas de 117: `store_id` (10 columnas); `dept_id` (7 columnas); `weekday` (7 columnas); `month` (12 columnas); `event_name_1` (31 columnas); `event_name_2` (4 columnas); `snap`; `evento_<nombre>` (30 columnas); `precio_medio_semana_anterior`; `dolares_media_7`.
   - **dolares, HistGradientBoosting:** 117 columnas, las de salida del preprocesador que pueden entrar.

9. **Cómo deshacer:** usar la lista completa de salida del preprocesador (`informes/preparacion.json`, `columnas_salida`).

Regla: `preseleccion` · huella `f191bd8e2ecd`

## Fichas de la preproducción (`scripts/19_contrato_produccion.py`)

### R-019 · 25/11/2026 · preselección: los festivos, decididos (cierra P-01 de R-018)

1. **Tabla y columna:** las listas de columnas de los dos objetivos (R-018): `event_name_1` y `event_name_2`.
2. **Cómo estaba:** R-018 deja P-01 abierta, con las dos codificaciones de los festivos en las dos listas.
3. **Problema o finalidad:** un mismo festivo entraba dos veces, como `event_name_<n>` y como `evento_<nombre>`.
4. **Decisión:** El responsable del caso, 24/11/2026: «Un día es festivo y punto» (reglas, apartado 7). Entra una columna por festivo (`evento_<nombre>`), venga en el primer campo o en el segundo; `event_name_1` y `event_name_2` no entran.
5. **Qué se hizo:** la búsqueda (`scripts/15_busqueda.py`) usó ya las listas sin esas dos columnas. R-018 no se reescribió: esta ficha recoge lo decidido.
6. **Quién y con qué permiso:** la sesión principal, con la decisión del responsable del caso del 24/11/2026; la ficha la escribe el 25/11/2026, al aprobar el responsable del caso el contrato.
7. **Comprobación:** ninguna de las 82 columnas de cada ganador (`informes/busqueda.json`) sale de `event_name_1` ni de `event_name_2`; comprobado al revisar el contrato.
8. **Cómo quedó:** 82 columnas por objetivo, de 21 finalistas.
9. **Cómo deshacer:** volver a las listas de R-018.

### R-020 · 25/11/2026 · el modelo ganador de cada objetivo

1. **Tabla y columna:** el modelo de unidades y el de dólares, ajustados con `hechos_modelo_entrenamiento`.
2. **Cómo estaba:** la receta, solo en `informes/busqueda.json`; ningún modelo guardado (el script 16 lo ajusta en memoria).
3. **Problema o finalidad:** el contrato de producción necesita el último paso de cada cadena con su ficha.
4. **Decisión:** El responsable del caso, 25/11/2026, «Apruebo el ganador»; el veredicto de la validación, «Sí, apruebo el veredicto».
5. **Qué se hizo:** HistGradientBoosting en los dos objetivos: `learning_rate` 0,1, sin límite de profundidad, `max_iter` 500, `min_samples_leaf` 205, `l2_regularization` 0, sin parada temprana, semilla 42; 82 columnas. Los demás hiperparámetros, en `informes/busqueda.json` (`ganador`).
6. **Quién y con qué permiso:** el agente de la búsqueda deja `scripts/15_busqueda.py`; la sesión principal escribe esta ficha al aprobar el responsable del caso el contrato.
7. **Comprobación:** ajustado con 82.250 filas en cada objetivo; en la validación gana en 12 de 13 orígenes en los dos objetivos (`informes/validacion.json`).
8. **Cómo quedó:** la receta, en `informes/busqueda.json`; el modelo guardado llega con el primer reentreno de producción.
9. **Cómo deshacer:** volver a la regla que menos falla, como prevé el informe final si el modelo no gana en el año guardado.

### R-021 · 25/11/2026 · contrato de producción aprobado

1. **Tabla y columna:** las 82 columnas de cada ganador; el contrato, en `config/modelo/contrato_produccion.md` e `informes/preproduccion.json`.
2. **Cómo estaba:** el contrato propuesto, en PARADO a la espera del responsable del caso.
3. **Problema o finalidad:** fijar cómo se construye cada columna al reentrenar y al prever, antes de escribir el código de producción (método `preproduccion`, parte 1).
4. **Decisión:** El responsable del caso, 25/11/2026: «Apruebo el contrato». Con él, las tres diferencias con la petición, que manda el registro: la lista de eventos aprende del entrenamiento (R-015); el codificador y los dos escaladores aprenden (R-011); la partición también quita filas (R-010).
5. **Qué se hizo:** ningún dato cambia. El contrato separa cada paso en cuatro clases: quita filas (R-010, R-017), solo al reentrenar; no aprende; necesita otras filas (R-009, R-012, R-013, R-014), con la historia que ya lleva lo previsto; aprende (R-015, R-011 y el modelo, R-020), con fit en el entrenamiento.
6. **Quién y con qué permiso:** el agente de la petición 26 deja `scripts/19_contrato_produccion.py`; el responsable del caso lo aprueba el 25/11/2026.
7. **Comprobación:** prueba 19 en rojo antes y en verde después; las 82 columnas de cada ganador están en el contrato; su cuenta cuadra con las 21 finalistas.
8. **Cómo quedó:** el contrato aprobado. Pendiente de la parte 2: que el primer reentreno dé exactamente las previsiones de la validación.
9. **Cómo deshacer:** volver el contrato a propuesto; no hay código de producción que retirar hasta la petición 27.

### R-022 · 25/11/2026 · el modelo en uso: el reentrenado con un año más

1. **Tabla y columna:** los dos modelos de previsión; `produccion/configuracion.json`, `modelo_en_uso`.
2. **Cómo estaba:** ningún modelo en uso; el candidato era el primer reentreno (`modelos/reentrenos/2026-11-25`), igual al de la validación.
3. **Problema o finalidad:** en la prueba final, el candidato no se confirmó en unidades (9 de 13 orígenes, la regla pide 10); en dólares sí (12 de 13).
4. **Decisión:** El responsable del caso, 25/11/2026: «Sí, apruebo el reentrenado». El reentrenado es la receta de R-020 sin cambios, ajustada con todo lo anterior al 23/05/2015; ganó en la prueba final en unidades (12 de 13) y en dólares (13 de 13).
5. **Qué se hizo:** `modelo_en_uso` pasa a `modelos/reentrenos/2015-05-22`; el primer reentreno queda descartado, sin borrar.
6. **Quién y con qué permiso:** la sesión principal, con la aprobación del responsable del caso.
7. **Comprobación:** los dos modelos cargan con su ficha (versiones y huella) desde la configuración; la prueba final, rehecha por la sesión principal con su propio código.
8. **Cómo quedó:** el reentrenado en uso para los dos objetivos.
9. **Cómo deshacer:** `modelo_en_uso` a null o al primer reentreno en `produccion/configuracion.json`.
