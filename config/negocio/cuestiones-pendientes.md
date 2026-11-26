# Cuestiones pendientes · caso 69

Las resuelve la persona responsable del proyecto. Una cuestión resuelta no se borra: cambia de estado y recoge la fecha,
lo decidido y dónde quedó. Estados: abierta, resuelta y no resoluble con los datos disponibles.

## cuestión 001 · Qué productos cuentan en «productos del departamento con precio la semana anterior»

- Fecha: 24/11/2026.
- Estado: resuelta el 24/11/2026.
- Petición: la matriz de transformaciones del paso 5 (petición de la partición y la matriz). Los planteamientos, §2,
  decisión 7, proponen como candidata «los productos del departamento con precio la semana anterior», para que el
  modelo vea la llegada de productos nuevos.
- Motivo: contada tal cual, la variable avisa dentro del horizonte de una venta que el día de prever no se conoce.
  Un producto tiene precio en una semana solo si se vendió en ella. Entra la semana de su primera venta (reglas, apartado 5,
  «El precio»). Dentro del horizonte, la semana anterior al día previsto puede caer después del origen: si en ella
  aparece un producto nuevo, la cifra sube y dice que ese producto ya se vendió. Es el mismo aviso que el responsable del caso cortó en el
  precio medio el 24/11/2026 con la regla de las cuatro semanas. Esa regla está escrita solo para el precio
  medio. La que fijan los planteamientos para esta candidata no dice qué productos cuentan.
- Opciones que se ven, sin elegir ninguna:
  - contar todos los productos con precio la semana anterior, como dicen los planteamientos, aceptando el aviso dentro
    del horizonte;
  - contar solo los que ya tenían precio cuatro semanas antes, como el precio medio: no avisa de nada, pero la llegada
    de un producto se ve cinco semanas después de su primera venta;
  - contar en cada día previsto los productos con precio en la última semana que acaba el día del origen o antes, la misma cifra
    para todo el horizonte: no avisa de nada; en el entrenamiento, con un día de horizonte, coincide con la primera
    opción.
- Lo que haría falta para resolverla: que el responsable del caso elija cómo se cuenta. Mientras tanto, la candidata queda en la
  matriz como pendiente de esta cuestión y no entra.
- Lo decidido (el responsable del caso, 24/11/2026, «Sí, apruébala»): la segunda opción. Cuentan solo los productos que ya
  tenían precio cuatro semanas antes, la misma regla que el precio medio. La primera usa ventas que el día de prever no
  se conocen; la tercera daría al modelo una cifra distinta al entrenar y al prever.
- Dónde quedó: `../metodo/04_planteamientos.md` §2, decisión 7, y `../modelo/matriz_transformaciones.md`.
