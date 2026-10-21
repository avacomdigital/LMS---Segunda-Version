# 16 · Node Platform y Cola de Salida (MOD-015) · Diseño, decisiones y alcance

| Campo | Valor |
|---|---|
| Estado | **Fases 0 a 2 implementadas** (2026-10-21) más la API `/api/nodo/` y la pestaña «Estado del equipo» de OPS (P-17 y P-18 en lo que no depende de las fases 3 a 6). **Fase 3, primera sesión (2026-10-21): seis módulos cortados** a la cola única —`device_manager`, `search`, `reporting`, `modo_estudio`, `classroom_engine` y `gradebook` escriben **sólo** en `m15_evento`; sus colas `m*_evento_salida` quedan intactas como historia y Reportes y Búsqueda las leen por la fachada (§5, §6 D-23…D-27)—. Siguen en su cola antigua `evaluacion`, `acceso` y `audit` (segunda sesión) y `licenciamiento` (sin fecha: hallazgo 9). Backend `backend/nodo/` (app Django, tablas `m15_*`), cliente `src/Avacom.Lms.Core/Nodo/`, lógica de OPS en `src/Avacom.Lms.Ops/Nodo/` y la pestaña en `Pages/BitacoraPage.Equipo.cs`. |
| Módulo | **MOD-015 · Node Platform y Cola de Salida** (DOM-009 · Plataforma y Continuidad). CAP-093 (parcial: anclas y arranque, sin la máquina completa), CAP-094, CAP-096, CAP-097, CAP-098 (demostrado sobre la cola, no sobre las respuestas: Fase 3), CAP-099 (sólo el estado). FUN-159, 160, 161, 162, 163, 164; FUN-158 y 166 en lo que toca a las anclas; FUN-165 y 167 en su primera parte. |
| Contrato | [02-api.md](02-api.md) — rutas reales capturadas, la interfaz `nodo.servicios`, eventos y permisos. |
| Pruebas | [03-pruebas.md](03-pruebas.md) — qué se probó con qué resultado y **qué no**. Operación: [04-operacion.md](04-operacion.md). |
| Se apoya en | MOD-019 (contexto de la petición y bitácora), MOD-001 (permisos y escalada), el reloj de la evaluación (uno solo, INV-017). El prompt está en [00-prompt.md](00-prompt.md). |

> **Principio (Documento Maestro):** la cola **ordena, conserva y entrega**. Nunca interpreta la carga de un evento ni aplica lógica de un dominio. Su contribución más valiosa es lo que impide: dos módulos escribiendo el mismo dato, un hecho sin su evento, un evento que sobrevive a un hecho que no ocurrió, y una plataforma que detiene una clase.

---

## 1 · Qué entra en este tramo y qué no

| Entra | Dónde |
|---|---|
| La cola única `m15_evento` con secuencia global `AUTOINCREMENT`, el sobre de doce campos y la carga; hecho y evento en la **misma transacción** (BR-001, INV-022) | `nodo/servicios.publicar` · `aplicacion/publicar.py` · `models.Evento` |
| Inmutabilidad del sobre y de la carga (trigger) y marca alta del reloj que sólo sube (trigger) | `migrations/0002_triggers.py` |
| El catálogo de los 164 tipos que ya existen + los 9 del Maestro + 4 extensiones, con clase, sensibilidad, retención y clave de deduplicación (P-04) | `dominio/catalogo_datos.py` (generado) · `dominio/catalogo.py` |
| Validador de nombres BR-122 (ambas formas del Maestro) y de cargas R-13 (claves prohibidas y tope) | `dominio/catalogo.py` · `dominio/sobre.py` |
| La fachada de lectura y el corte por módulo (P-05), probados con un lector legado **falso** | `aplicacion/leer.py` · `dominio/corte.py` |
| Registro de consumidores, marcas por (consumidor, fuente), `aplicar_lote`, reintento con espera creciente, cola de problemas, reproceso y reproducción (P-06, P-07) | `aplicacion/consumidores.py` · `dominio/reintentos.py` |
| La purga con las cuatro condiciones, construida y **apagada**; `PuertoRespaldo` que nunca cubre (P-08) | `dominio/purga.py` · `aplicacion/purga.py` · `infraestructura/respaldo.py` |
| Anclas de la secuencia y del reloj fuera de la base; detección de restauración al arrancar (P-12, P-13) | `dominio/anclas.py` · `infraestructura/anclas.py` · `aplicacion/arranque.py` |
| El estado del nodo con sus motivos (Q-N1), evaluado al pedirlo y publicado sólo al cambiar; `/health/` con el campo aditivo `nodo` (P-09, P-16) | `dominio/estado.py` · `aplicacion/estado.py` · `expediente/views.py` |
| Permisos `node.*` (migración `acceso/0019`), acciones de bitácora del módulo `nodo`, API `/api/nodo/` (P-17) | `acceso/dominio/plantillas.py` · `audit/dominio/catalogos.py` · `nodo/interfaces/` |
| OPS: «Estado del equipo» ampliada (chip, motivos, base, disco, reloj, cola por consumidor, último punto de recuperación, eventos apartados con [Reintentar]/[Reprocesar]/[Reproducir]) y banner del menú (P-18) | `Core/Nodo/` · `Ops/Nodo/` · `Pages/BitacoraPage.Equipo.cs` · `DashboardPage` |
| **Fase 3, primera sesión:** el corte de `device_manager`, `search`, `reporting`, `modo_estudio`, `classroom_engine` y `gradebook` (P-01, P-05, R-03, R-04): su `OutboxDjango.publicar` llama a `nodo.servicios.publicar` en la transacción del hecho y ya no escribe en `m*_evento_salida`; cada uno registra su lector legado al cargar (`apps.ready` → `servicios.eventos_legados`); el corte lo registra una migración de datos idempotente y silenciosa (D-24); `servicios.eventos_desde` y `ultima_secuencia` pasan por la fachada (D-27); paridad por módulo (16 pruebas) | `<modulo>/infraestructura/repositorios.py` · `<modulo>/servicios.py` (nuevos en `search` y `reporting`) · `<modulo>/apps.py` · migraciones `device_manager 0006`, `search 0003`, `reporting 0003`, `modo_estudio 0002`, `classroom_engine 0004`, `gradebook 0004` · `<modulo>/tests/test_paridad_cola.py` · `nodo/pruebas.py` (soporte de pruebas) · `nodo/migrations/0003_agregado_id_256.py` (D-26) |

| NO entra (queda preparado y dicho) | Por qué |
|---|---|
| **Cortar `evaluacion`, `acceso` y `audit`** (segunda sesión de la Fase 3) y `licenciamiento` (sin sesión asignada) | P-01: un módulo por paso, con paridad; `evaluacion` lleva además la prueba de proceso muerto sobre respuestas (P-11). |
| Migrar gradebook, reporting y search al registro (Fase 4) | Siguen con sus marcas y su mecanismo; `aplicar_lote` los espera. |
| La máquina de arranque completa, el supervisor de programadores, el `503` del modo restringido y el `synchronous=FULL` explícito (Fase 5) | El estado ya se evalúa y se publica; falta el middleware que lo aplica y el programador que lo vigila. **Nada responde 503 todavía.** |
| Unificar las seis copias del reloj y la huella con MOD-018 (Fase 6) | `ahora_ms()` ya es `max(reloj, marca alta)`; MOD-018 tiene la lógica fina de la fecha adelantada. |
| Student | «En recuperación» no puede ocurrir antes de la Fase 5; el texto ya está en `NodoTexto.RecuperacionParaStudent`. |
| CAP-095 (drenaje remoto), 019-09 (bitácora desde la cola), Q-38 (identificador de cinco segmentos), aislamiento por ruta | V1 / decisión del CTO (P-20). Quedan la clase `sincronizacion`, el estado `reconocido`, `PuertoSincronizacion` y `nuevo_id()`. |

## 2 · Arquitectura

Hexagonal, igual que `gradebook/`, `search/`, `reporting/` y `licenciamiento/`:

```
backend/nodo/
├── models.py                m15_* (§3)
├── servicios.py             la interfaz para los OTROS módulos (publicar, leer, cortar, consumidores, reloj, estado, arranque)
├── pruebas.py               soporte para las PRUEBAS de los módulos cortados (cola(modulo), espiar, sembrar_historia, nodo_limpio): ningún caso de uso lo importa
├── dominio/                 puro, sin Django: catalogos · catalogo (+ catalogo_datos generado) · sobre · reintentos · purga · anclas · corte · estado · errores
├── aplicacion/              casos de uso, sin Django: puertos · base (config y estado vivo) · publicar · leer (fachada y corte) · consumidores · purga · estado · arranque
├── infraestructura/         ORM (repositorios, unidad de trabajo), anclas en archivo, contexto de MOD-019, salud del equipo, autorización por MOD-001, respaldo ausente, triggers, contenedor
├── interfaces/              vistas DRF y rutas (/api/nodo/)
├── migrations/              0001_initial · 0002_triggers · 0003_agregado_id_256 (Fase 3, D-26: repone los triggers)
├── tools/                   inventario_colas.py · generar_catalogo.py · prueba_concurrencia.py
└── tests/
```

**Frontera (R-09).** `nodo` escribe sólo `m15_*` y **no lee ninguna tabla ajena**: la historia de un módulo cortado la sirve el **lector legado** que el propio módulo registra (`registrar_lector_legado`), el contexto de la petición entra por `audit.contexto`, los permisos por la política de MOD-001 y el reloj es el de la evaluación. Una prueba de arquitectura lo comprueba, y también que nadie fuera de `nodo` toca `m15_*`.

**Cliente y OPS.**

```
src/Avacom.Lms.Core/Nodo/      ModelosNodo (DTOs) · INodoApi/NodoApi · NodoTexto (estados, motivos, cifras, errores, banner) · ReglasDeNodo (quién ve, banner, orden)
src/Avacom.Lms.Ops/Nodo/       ResumenDelEquipo (las líneas y la cola, puro) · FlujoDeReproceso (una confirmación, un envío)
src/Avacom.Lms.Ops/Pages/      BitacoraPage.Equipo.cs (la sección del nodo en «Estado del equipo») · DashboardPage (banner `NodoBanner`)
```

## 3 · Tablas `m15_*` (8)

| Tabla | Qué guarda |
|---|---|
| `m15_evento` | La cola única: `secuencia` (INTEGER PRIMARY KEY AUTOINCREMENT), `evento_id` (UUID4 hex, único), `tipo`, `version`, `modulo`, `creado_en`, `agregado_tipo`, `agregado_id`, `actor`, `dispositivo_id`, `correlacion_id`, `clase`, `sensibilidad`, `carga`, y dos marcas de R-06: `catalogado`, `carga_omitida`. **Inmutable** (trigger `m15_evento_inmutable`). Índices: `(modulo, secuencia)`, `(tipo, secuencia)`. |
| `m15_corte` | Por módulo cortado: `ultima_legada` (el último id de su tabla antigua), `cortado_en`, `version_contrato`. De una sola vía. |
| `m15_modulo` | El registro de módulos con versión de módulo, de datos y de contrato (BR-012). Hoy sin filas: lo llena la Fase 5. |
| `m15_consumidor` | Nombre, módulo, fuentes, tipos, versión de contrato declarada, límite de rezago, estado (`al_dia`, `rezagado`, `reconstruyendose`, `suspendido`), `activo` (BR-018). |
| `m15_marca_lectura` | Una fila por (consumidor, fuente): la marca (BR-005), el evento que la retiene con sus intentos y su próximo intento (P-07), `reconstruyendose`. |
| `m15_problema` | Los eventos apartados (FUN-163): consumidor, fuente, secuencia, `evento_id`, tipo, intentos, último error **saneado**, estado, quién lo reprocesó. Nunca la carga. |
| `m15_arranque` | Una fila por arranque, cerrada en la parada limpia; lo que decidieron las anclas (restauración, contador). |
| `m15_marca_alta` | La marca alta del reloj (P-13). Sólo sube (trigger). |

Sin claves foráneas (ni dentro ni fuera del módulo). Sin trigger de `DELETE` (P-03): el único borrado de la aplicación es la purga, y una prueba lo comprueba.

## 4 · Línea base y mediciones (Fase 0)

| Qué | Resultado |
|---|---|
| Suite completa antes de tocar nada (`manage.py test`) | **2252 pruebas, OK, 14 omitidas, 818 s** (2026-10-21). |
| Colas privadas encontradas por el inventario (`nodo/tools/inventario_colas.py`) | **Diez**, no nueve: el prompt no contaba `m18_evento_salida` (licenciamiento, 12 tipos). **164 tipos** producidos (el prompt estimaba ≈150). |
| Commit durable en esta máquina (SQLite 3.49.1, WAL, tabla igual a `m15_evento`, 2000 commits de un evento, `scratchpad/medir_commit.py`) | `synchronous=FULL`: **p50 1,30 ms · p95 1,73 ms · p99 2,92 ms**. `NORMAL`: p50 0,07 · p95 0,16 · p99 1,51 ms. El `INSERT` solo, dentro de una transacción abierta: p50 0,016 · p95 0,025 ms. |
| `publicar` (lo que añade a la transacción del hecho; base de pruebas en memoria, 1000 eventos) | **p50 0,15 ms · p95 0,23 ms · 1 consulta (un `INSERT` con SQL directo)**. Con el ORM eran 1,7 / 2,35 ms: D-3. |
| Tamaño de un evento (fila + índices) con una carga de respuesta de 256 B | ≈ **1,7 KB** en una base de archivo con WAL (medida de la Fase 0) · ≈ 0,6 KB en la base en memoria de las pruebas. |
| Concurrencia (`nodo/tools/prueba_concurrencia.py`, base de archivo temporal) | 20 hilos × 50 eventos: **1000 secuencias sin huecos ni repetidos, 0 «database is locked», 2,9 s (345 commits/s)** · 4 procesos × 50: 200 sin huecos, 4,5 s · copia vieja restaurada: restauración detectada, contador saltó de 1320 a 11 320, ninguna secuencia repetida · proceso matado a mitad de transacción: `quick_check` ok, 6 lotes completos, **0 a medias**. |

**Estimación del crecimiento sin purga (Q-N3).** Una clase de 30 alumnos con una actividad de 5 preguntas produce hoy ≈ 300 eventos (unirse, presencia, respuestas, entregas, sesión): ≈ 0,5 MB. Seis clases al día ≈ 3 MB; 200 días lectivos ≈ **0,6 GB por año**, sin contar los eventos técnicos agregados por lote (uno por lote aplicado y consumidor). Es una estimación con las cargas de hoy, no una medición de aula real.

## 5 · Inventario de las colas (Fase 0, regenerable) y registro de los cortes (Fase 3)

| Cola | Módulo | Tipos que produce | Quién la lee | Marca del lector | Corte a la cola única |
|---|---|---|---|---|---|
| `m01_evento_salida` | acceso | `identidad.*` (40) | nadie | — | pendiente (segunda sesión) |
| `m07_evento_salida` | classroom_engine | `aula.*` (22) | reporting, search, **por la fachada** (`classroom_engine.servicios.eventos_desde` → `nodo.servicios.leer`) | `m13_marca_consumidor`, `m21_marca_lectura` (siguen valiendo: un id antiguo o una secuencia global) | **cortada** · `classroom_engine/0004_corte_cola_unica` · lector `servicios.eventos_legados` |
| `m08_evento_salida` | modo_estudio | `estudio.*` (12) **+ `evaluacion.respuesta_registrada.v1`** (coautor, D-25) | reporting, search, por la fachada | ídem | **cortada** · `modo_estudio/0002_corte_cola_unica` |
| `m09_evento_salida` | device_manager | `dispositivo.*` (9) | nadie (reporting lee equipos por id, no la cola); la fachada sirve la historia si alguien la pide | — | **cortada** · `device_manager/0006_corte_cola_unica` |
| `m10_evento_salida` | evaluacion | `evaluacion.*` (29) | gradebook, reporting, search | `m11_marca_consumidor`, `m13_marca_consumidor`, `m21_marca_lectura` | pendiente (segunda sesión, con P-11) |
| `m11_evento_salida` | gradebook | `calificacion.*` (20) | reporting, por la fachada (`LibroFuente` → `gradebook.servicios.eventos_desde`) | `m13_marca_consumidor` | **cortada** · `gradebook/0004_corte_cola_unica` |
| `m13_evento_salida` | reporting | `reporte.*` (9) | nadie | — | **cortada** · `reporting/0003_corte_cola_unica` |
| `m18_evento_salida` | licenciamiento | `licencia.*` (12) | nadie | — | sin sesión asignada (hallazgo 9); `test_corte.py` simula el corte sobre este módulo |
| `m19_evento_salida` | audit | `auditoria.*` (5, catálogo cerrado) | nadie | — | pendiente (segunda sesión) |
| `m21_evento_salida` | search | `busqueda.*` (6) | nadie | — | **cortada** · `search/0003_corte_cola_unica` |

Todas con la misma forma (`agregado_tipo`, `agregado_id`, `tipo_evento`, `carga`, `creado_en`, `publicado_en`, `intentos`) e `id` autoincremental por tabla. Todas tienen el **mismo puerto** `publicar(agregado_tipo, agregado_id, tipo_evento, carga)` salvo `acceso` (`publicar(EventoSalida)`) y `audit` (`infraestructura/eventos.py`): son el punto de corte de la Fase 3.

**Cómo quedó cada módulo cortado** (el mismo patrón en los seis): `OutboxDjango.publicar` conserva la comprobación contra su catálogo y llama a `nodo.servicios.publicar(<modulo>, agregado_tipo, agregado_id, tipo, carga)` dentro de la transacción de su unidad de trabajo (que ya era `atomic` en todos los puntos de publicación: se revisó cada llamada, incluidas las de `device_manager.servicios` que acceso, aula, evaluación y estudio invocan dentro de la suya); `servicios.eventos_legados(desde, limite, tipos, hasta)` lee su tabla antigua con `desde < id ≤ hasta`; `apps.ready` lo registra con `registrar_lector_legado`; la migración de datos corta con `max(id)` de la tabla antigua (0 en una instalación nueva); `servicios.eventos_desde` devuelve `nodo.servicios.leer(<modulo>, …)` y `ultima_secuencia` es `max(última secuencia del módulo en m15, ultima_legada)` (D-27). En una instalación nueva el corte queda en 0 y el lector legado nunca se llama.

## 6 · Decisiones

Lo que el prompt no resolvía (o lo que midió distinto) se decidió con sus criterios —no cortar una clase, no perder ni duplicar, tocar menos archivos ajenos, reversible, probable aquí— y se dice aquí. Las marcadas **(CTO)** están en §9.

| # | Decisión | Por qué |
|---|---|---|
| D-1 | **Alcance:** Fases 0–2 completas **más** la API `/api/nodo/` y la pantalla de OPS (P-17/P-18) en lo que no depende de las fases 3–6, porque la petición pedía «backend y endpoints» y «frontend». **Ningún módulo se corta.** | P-01: la cola se prueba a fondo antes de mover a nadie. La pantalla ya sirve con los consumidores que se registren. |
| D-2 | **Diez colas, no nueve.** `m18_evento_salida` (licenciamiento) entra al inventario y al catálogo con sus 12 tipos. | Manda el repo. |
| D-3 | **`publicar` escribe con SQL directo** (un `INSERT` por `cursor.execute`), no con `Model.objects.create`. | R-08: el ORM costaba 1,7 ms p50 por fila (instanciación, señales); con SQL directo, 0,15 ms. La carga se guarda como el JSON de `JSONField`, así que el ORM la lee igual. |
| D-4 | **La marca vive en `m15_marca_lectura`**, una fila por (consumidor, fuente), no dentro de `m15_consumidor`. | La marca avanza en la misma transacción que el efecto (BR-005) y un `UPDATE` de una fila es más seguro que reescribir un JSON. |
| D-5 | **Los tipos se declaran por nombre base**: un consumidor que declara `x.y.v1` recibe también `x.y.v2` y siguientes (INV-006, ignorando lo que no conoce); declarar una versión que nadie produce es un contrato incompatible y el registro **se rechaza con asiento** (INV-007), escrito fuera de la transacción revertida. | BR-011. Probado: una v2 con un campo extra no hace fallar al consumidor v1. |
| D-6 | **Al apartar un evento, la marca avanza hasta ÉL**, no hasta el final del lote. Lo que falló detrás se vuelve a leer en el siguiente lote (reaplicar es idempotente, BR-008). | El mecanismo actual de gradebook y reporting, al dejar atrás el primero, pasa de largo de cualquier otro fallo del mismo lote (§8, hallazgo 3). |
| D-7 | **La purga mira la marca de cada consumidor sólo sobre su fuente**: a un evento del módulo M lo retienen las marcas de los consumidores activos que leen M. | Una marca sobre `evaluacion` no dice nada de un evento de `audit`. |
| D-8 | **Eventos técnicos por lote (Q-N6):** `nodo.marca_lectura_avanzada.v1` una vez por lote con ≥ 1 aplicado (rango, conteos); `nodo.entrega_reintentada.v1` por fallo (raros); `nodo.evento_apartado.v1` y `nodo.evento_reprocesado.v1` por evento; `nodo.salud_evaluada.v1` sólo al cambiar. **`nodo.evento_publicado.v1` no se emite**: sería el mismo dato que la marca avanzada. `AVACOM_NODO_EVENTOS_TECNICOS=0` los apaga. **(CTO)** | P-15: uno por evento duplicaría la cola. Un evento `nodo.*` jamás provoca otro: nadie consume `nodo`. |
| D-9 | **Anclas:** un archivo JSON (`ancla-cola.json`) con la mayor secuencia emitida y la marca alta, escrito de forma atómica con una huella SHA-256 (detecta un archivo a medias o editado; no es una defensa contra quien administra el equipo), refrescado cada 5 s o cada 1000 eventos; margen de salto **10 000** (lo emitible en 5 s a 1,3 ms por commit son ≈ 3 800). La primera llamada sólo abre la ventana de tiempo. | P-12. |
| D-10 | **Sin ancla y con eventos en la base también es una restauración** (equipo nuevo con un respaldo): el contador salta a `max + margen`. | No hay con qué comparar; saltar no cuesta nada y no repetir es INV-002. |
| D-11 | **Reloj:** `ahora_ms() = max(reloj del sistema, marca alta)`, marca alta en memoria, en el ancla y en `m15_marca_alta`; detección de retroceso con tolerancia de 5 min y restricción a partir de 24 h (Q-N1). La lógica de la **fecha adelantada** (Q-L13) sigue en MOD-018 hasta la Fase 6. | P-13, P-14: implementar una vez. |
| D-12 | **El estado del nodo se evalúa al pedirlo** (`/api/nodo/estado/`, `arrancar()`), no por un programador (Fase 5). Un proceso que no arranca por `asgi.py` (una prueba, un comando) no se queda «arrancando». | Sin supervisor todavía; evaluar es barato (una lectura del disco y de la cola). |
| D-13 | **El modo restringido se declara pero aún no se aplica:** el estado y sus motivos se evalúan, se publican y se asientan; el middleware que responde `503` en rutas no núcleo es de la Fase 5. `NodoRestringido` (503 + `Retry-After`) ya existe para entonces. | No cortar una clase: hasta tener el middleware probado contra la lista de rutas núcleo, nadie recibe un 503. |
| D-14 | **`/health/` suma el campo `nodo`** leyendo sólo memoria (sin consultas), con `try/except`. | R-11: el health nunca falla por el nodo ni toma el bloqueo de escritura. |
| D-15 | **El catálogo se genera del código** (`generar_catalogo.py`): clase por prefijo con excepciones (configuración y estructura son *dominio*; lo derivado y técnico, *técnico*), sensibilidad conservadora (lo que nombra a un alumno es `personal_menor`), claves de deduplicación del Maestro en sus quince fichas y la del agregado para el resto. Un tipo desconocido en producción entra como `personal_menor`. **(CTO, Q-N5)** | BR-133: la clase se declara en el documento, no en el productor. |
| D-16 | **Claves prohibidas por nombre exacto** (a cualquier profundidad), no por subcadena: `clave` (la de deduplicación) no cuenta; `password`, `token`, `pin`, `nombres`, `dni`, `correo`, `texto_respuesta`, `ruta`… sí. Tope de carga 16 KB. En producción la carga se reemplaza por `{"_omitida": …}` y queda asiento (R-06). | R-13 sin falsos positivos sobre las cargas de hoy. |
| D-17 | **Permisos:** la administración recibe los tres; el técnico `node.queue.read` y `node.health.read`; `node.queue.replay` llega al técnico **por escalada temporal**, que MOD-001 ya suma a las concesiones (`permisos_adicionales`). Probado por la API. | P-17 tal cual. |
| D-18 | **La parada limpia es un gancho `atexit`** registrado desde `asgi.py`. Si el servicio mata el proceso, no corre y el siguiente arranque dirá «apagado sucio». | No tocar `avacom_ops_backend.py` (del instalador) en este tramo; la Fase 5 añade la llamada explícita. |
| D-19 | **OPS:** se amplía «Estado del equipo» (sin pantalla nueva); el banner del menú lee `/health/` (público, sin permiso, sin base); [Reintentar] vuelve a leer; [Reprocesar] y [Reproducir] piden **una** confirmación y envían una sola vez; sin teclado; sólo `Border`, `Label` y `Button`. Student no cambia. | P-18, R-17. |
| D-20 | **El lector legado es una función que el módulo registra** (`registrar_lector_legado(modulo, f)`), con la firma `(desde, limite, tipos, hasta)`. Un módulo cortado sin lector en el proceso **no se sirve a medias**: la lectura falla con `fuente_legada_ausente`. | R-09: la cola no lee tablas ajenas; mejor fallar que perder historia. |
| D-21 | **Reprocesar exige que el consumidor corra en este proceso** (su `aplicar` registrado en memoria); si no, 409 `consumidor_sin_aplicador`. | FUN-164 sin reescribir la lógica de nadie. |
| D-22 | **`procesados` cuenta aplicaciones sin error**, incluidas las que el consumidor descarta por repetidas (BR-008). | Igual que los consumidores de hoy; el consumidor es quien sabe si ya lo tenía. |
| D-23 | **(Fase 3) Las pruebas existentes que leían la cola antigua del módulo cambian de dónde leen, no qué comprueban.** 53 lecturas de `m.EventoSalida.objects` en 20 archivos de pruebas de los seis módulos (incluidos los ayudantes `eventos*()` de sus bases) pasan a `cola("<modulo>")` de `nodo/pruebas.py`, que ofrece el mismo subconjunto de la API del manager sobre `m15_evento` con el vocabulario antiguo (`id`, `tipo_evento`…): cada aserción queda textualmente igual. Dos pruebas de Reportes que *escribían* en colas ajenas cambian de mecanismo (mover el reloj en vez de `update(creado_en=…)`, porque el sobre es inmutable; `cola("modo_estudio").create(...)` en vez de insertar en `m08`). `test_corte.py` de `nodo` simula el corte sobre `licenciamiento` (ya no sobre `device_manager`, que está cortado de verdad). Las tres suites que mueven el reloj falso de la evaluación (gradebook, reporting, search) reinician el estado vivo del nodo en cada prueba (`nodo_limpio()`), porque la marca alta del reloj (P-13) no debe viajar de una prueba a otra. | El prompt pedía «sin cambiar ninguna prueba existente» y a la vez «sin doble escritura»: con el corte, una prueba que busca el evento en `m*_evento_salida` no puede pasar. Manda el repo: se cambió lo mínimo y se lista completo en `03-pruebas.md` §6. |
| D-24 | **El corte que registra una migración de datos es silencioso**: la fila de `m15_corte` y el salto del contador, sin asiento `nodo.modulo_cortado` ni evento `nodo.modulo_cortado.v1` (`cortar(..., asentar=False)`). Un corte hecho en caliente (la API o una prueba) sigue dejando los dos. | Una migración corre bajo el instalador sin actor ni contexto, y publicar desde ella dejaría secuencias y asientos en **toda** base recién creada (la de las pruebas incluida: las 115 pruebas de `nodo` cuentan secuencias y asientos desde cero). La huella del corte es la fila de `m15_corte`, que `/api/nodo/cola/` enseña en `cortes[]`. |
| D-25 | **Un tipo puede declarar coautores** (`catalogo.COAUTORES`): hoy sólo `evaluacion.respuesta_registrada.v1`, que el modo de estudio publica por cada respuesta de práctica (FUN-083) con el nombre del tipo de MOD-010 y una carga propia. El sobre lleva `modulo = modo_estudio`, así que quien lee la fuente `evaluacion` no lo recibe. **(CTO, hallazgo 7)** | R-09 («un hecho tiene un solo autor») chocaba con el repo: sin la excepción el corte del modo de estudio rechazaba (en pruebas) o marcaba `modulo_ajeno` (en producción) cada respuesta de práctica. No se renombra el tipo: sería cambiar el contrato de un módulo ajeno. |
| D-26 | **`agregado_id` del sobre sube de 96 a 256 caracteres** (migración `nodo/0003`, que reconstruye `m15_evento` y repone los triggers). | La paridad del libro lo encontró: el agregado de sus agregados por periodo es `alumno:grupo:periodo:curso_ref` (≈ 130 caracteres con una referencia de AVACOM Biblioteca); con 96 el evento no entraba (`SobreIncompleto`) y el consumidor del libro lo perdía en silencio dentro de su savepoint. La columna antigua de `m11` tampoco lo limitaba (SQLite no aplica `max_length`). |
| D-27 | **El registro de lectores legados vive fuera de la caché de servicios** (`contenedor._lectores_legados`): cada módulo se registra una vez por proceso en `apps.ready`, y `reiniciar()` (las pruebas) no lo olvida; cada `Servicios` nace con una copia. `ultima_secuencia()` de un módulo cortado es `max(última secuencia suya en m15, ultima_legada)`, para que un consumidor que se pone «al día» antes de que el módulo publique nada nuevo no vuelva a la marca cero; `eventos_desde` con una tupla de tipos vacía devuelve `([], secuencia)` (antes devolvía `hasta = último id` sin eventos, es decir, hacía avanzar la marca sin leer nada; ningún llamador pasa tipos vacíos). | Sin el registro fuera de la caché, las pruebas de `nodo` dejaban a los módulos reales sin lector; con `ultima_secuencia()` leyendo sólo `m15`, Search ponía sus marcas en 0 al reconstruir si el módulo aún no había publicado tras el corte. |
| D-28 | **El contador de `m15_evento` nunca queda por debajo del mayor corte.** Toda migración que reconstruya la tabla termina con `triggers.SQL_REPARAR_CONTADOR` (además de reponer los triggers), y el arranque del nodo repone el mismo piso (`piso_del_contador`, puro) si una migración lo olvidó, sin confundirlo con una restauración. `nodo/0003` ya lo hace. | Hallazgo 1 de la revisión independiente de la Fase 3: SQLite devuelve el AUTOINCREMENT a `max(secuencia)` al reconstruir la tabla; tras un corte por migración (sin evento técnico, la tabla puede estar casi vacía) el siguiente evento del módulo saldría bajo su corte y la fachada no lo serviría jamás. En este diff el orden de las migraciones lo evitaba; la segunda sesión y cualquier migración futura de `nodo` no podían depender de recordarlo. |
| D-29 | **Las dos pruebas de la Fase 2 que la suite completa de la Fase 3 vio fallar se hicieron robustas sin bajar lo que exigen:** `test_r02_fuera_de_la_transaccion…` comprueba que dentro de la transacción se escribe la secuencia `contador + 1` (no «1»: el vaciado entre `TransactionTestCase` no devuelve el AUTOINCREMENT a cero y `reset_sequences` no lo hace en SQLite), y `test_r08_…p95` toma la **mejor de cinco tandas** de 1000 (mide el coste del código, no el ruido de la máquina: con la suite y un MSBuild al lado el mismo código dio 2,39 ms y a solas 0,23 ms); `AVACOM_NODO_SIN_MEDICION=1` deja sólo la comprobación estructural (una consulta). | Una corrida completa que termina en rojo no se da por verde repitiendo aparte las que fallaron: se corrige la causa y se repite entera (03-pruebas §0). |

## 7 · Estados

**Nodo** (`dominio/estado.py`): `arrancando → operativo ⇄ restringido`; `en_recuperacion` y `detenido` existen y se publican, pero sólo la Fase 5 los pone en juego. Motivos de restricción (Q-N1, umbrales como dato en `AVACOM_NODO_*`): `transaccion_no_inmediata`, `base_danada`, `disco_escaso` (< 2 GB o < 5 %), `wal_enorme` (> 512 MB), `consumidor_nucleo_suspendido`, `reloj_retrocedido` (> 24 h). Histéresis: se sale cuando la condición mejora un 25 % sobre el umbral de entrada. **Nunca cierra una clase.**

**Evento**: `pendiente` (algún consumidor registrado de su fuente no lo superó), `aplicado`, `reconocido` (sincronización, V1). Se derivan; no se guardan.

**Consumidor**: `al_dia`, `rezagado`, `suspendido` (rezago > límite: se avisa con `ERROR` y `nodo.consumidor_rezagado.v1`, una vez), `reconstruyendose` (marca en cero hasta alcanzar la cola).

**Problema**: `apartado → reprocesado`; `descartado` reservado.

## 8 · Hallazgos en módulos ajenos (se reportan, no se corrigen)

1. **`aula.proyeccion.alumno.v1`** no lleva la acción en participio (BR-122). Sigue en el catálogo tal cual; `catalogo.hallazgos()` lo lista.
2. **`mod10.porcentaje.v1` y `mod10.revision_docente.v1`** (gradebook) tienen forma de tipo de evento pero no son eventos (el inventario los capta como «consumidos»): conviene renombrarlos para que ninguna herramienta los confunda.
3. **Gradebook y Reporting, al dejar atrás un evento tras `MAX_FALLOS_DE_EVENTO`, ponen la marca al final del lote** (`hasta = nueva`): si en ese mismo lote falló un segundo evento, pasa de largo sin asiento. `aplicar_lote` lo hace distinto (D-6); la Fase 4 lo resuelve al migrarlos.
4. **Search expone `eventos_desde(secuencia, limite)` sin `tipos`** (filtra en Python): su firma difiere de la de los demás; la Fase 4 lo normaliza.
5. **El prompt no contaba `m18_evento_salida`** (licenciamiento).
6. Ninguna carga de los catálogos trae claves de la lista prohibida. La paridad de la Fase 3 (seis módulos, con sus flujos reales por HTTP) no encontró ninguna carga con claves prohibidas ni por encima de los 16 KB: ningún evento entró marcado.
7. **El modo de estudio publica `evaluacion.respuesta_registrada.v1`** (FUN-083) por cada respuesta de práctica, con el nombre de un tipo de MOD-010 y una carga distinta (práctica y asignación de estudio, sin `intento_id`): el inventario lo clasificaba como «consumido». Se admite como coautor (D-25); el CTO decide si merece un tipo propio (`estudio.respuesta.registrada.v1`), que es un cambio de contrato de MOD-008.
8. **El libro compone `agregado_id` de más de 96 caracteres** (`alumno:grupo:periodo:curso_ref` en `calificacion.agregados_recalculados.v1`) y su columna `m11_evento_salida.agregado_id` declara `max_length` corto: SQLite no lo aplica, así que nunca falló. La cola única lo admite desde D-26; convendría que el libro declarara el largo real.
9. **`licenciamiento` (`m18_evento_salida`) no está en el plan de la Fase 3** del prompt (ni en la primera sesión ni en la segunda). Sigue en su cola antigua; nadie la lee. Pide una decisión: cortarlo en la segunda sesión o dejarlo para la Fase 6, cuando MOD-018 y MOD-015 unifiquen el reloj.
10. **`m09_evento_salida.agregado_id` tenía `max_length=36`** y `device_manager` no recortaba: también sin efecto en SQLite. La cola única lo admite.

## 9 · Preguntas para el CTO (con la opción tomada)

| # | Pregunta | Opción tomada |
|---|---|---|
| Q-N1 | ¿Cuándo se restringe el nodo y qué se restringe? | Motivos y umbrales de §7, como dato (`AVACOM_NODO_DISCO_MIN_GB`, `_PCT`, `_WAL_MAX_MB`, 24 h de retroceso); restringe sólo rutas no núcleo (lista en `catalogos.PREFIJOS_NUCLEO`), y todavía no se aplica (D-13). |
| Q-N2 | Q-38: ¿se migra ahora el identificador de cinco segmentos y la columna `secuencia`? | No. `nuevo_id()` da UUID4 y la secuencia global existe; nada se migra. |
| Q-N3 | Sin MOD-016 no hay purga: ¿se acepta que la cola crezca? | Sí: ≈ 0,6 GB/año estimados (§4). La purga está construida y apagada; no se propone una purga manual sin respaldo verificado. |
| Q-N4 | ¿Cuánto dura un ciclo (retención «5 ciclos»)? | 12 meses por defecto (`AVACOM_NODO_CICLO_MESES`). |
| Q-N5 | ¿Quién cura la clase y la sensibilidad de los 177 tipos? | Asignación inicial por reglas en `generar_catalogo.py`; se pide revisión. |
| Q-N6 | ¿`evento_publicado` y `marca_lectura_avanzada` agregados por lote? | Agregados; `evento_publicado` no se emite (D-8). |
| Q-N7 | ¿La bitácora derivada de la cola (019-09) en la Fase 4 o en MOD-019? | En MOD-019, con su propia marca. |
| Q-N8 | Corte eléctrico real y 100 equipos físicos: ¿quién, dónde, con qué hardware? | No se puede aquí: aquí sólo proceso muerto y procesos simulados. |
| Q-N9 | `synchronous=FULL` exige disco razonable: ¿el mínimo del panel? | Aún no se fija (Fase 5): hoy se hereda FULL; en este disco un commit durable cuesta 1,3 ms. |
| Q-N10 | ¿Cuándo se construye el drenaje remoto (CAP-095)? | V1. Queda `PuertoSincronizacion`. |
| Q-N11 | ¿Quién va primero, MOD-015 o MOD-018? | MOD-018 ya construyó el reloj y la huella; la Fase 6 los pone detrás del puerto de `nodo`. |

## 10 · Plan de los tramos que siguen

Fase 3, **primera sesión hecha** (2026-10-21): `device_manager`, `search`, `reporting`, `modo_estudio`, `classroom_engine`, `gradebook` cortados con el patrón de §5. **Segunda sesión**: `evaluacion` (con la prueba de proceso muerto sobre respuestas, P-11), `acceso` (su puerto es `publicar(EventoSalida)`) y `audit` (`infraestructura/eventos.py`); decidir `licenciamiento` (hallazgo 9). Lo que la primera sesión deja listo para la segunda: `nodo/pruebas.py` (`cola`, `espiar`, `sembrar_historia`, `como_consumidor`, `nodo_limpio`), el patrón de migración (`cortar(..., asentar=False)` idempotente, dependiente de `nodo 0003`), las pruebas de paridad como plantilla, y dos trampas ya resueltas: toda prueba que lea la cola antigua del módulo debe pasar a `cola("<modulo>")`, y la segunda sesión debe mover el `MODULO` de `nodo/tests/test_corte.py` si corta `licenciamiento`. Fase 4: los tres consumidores a `aplicar_lote`. Fase 5: arranque completo, supervisor, 503, `synchronous`, llamada desde `avacom_ops_backend.py`. Fase 6: reloj y huella con MOD-018. Fase 7: lo que falte de pantalla (servicios con latido). Fase 8: continuidad y carga.

**Pendiente de documentación:** `spec-driven/10-modelo-datos-implementado.md` no se regeneró (su pipeline vive en `specs/analisis/`, material privado fuera del repo): las ocho tablas `m15_*` están descritas en §3 y en los docstrings de `nodo/models.py`.

## 11 · Riesgos

- **El gancho `atexit` no corre si el servicio mata el proceso** → falsos «apagado sucio» hasta la Fase 5 (D-18). Sólo informa; no cambia el estado.
- **La cola crece sin purga** (Q-N3): ≈ 0,6 GB/año estimados con las cargas de hoy.
- **El margen de 10 000** cubre lo emitible en el intervalo del ancla en esta máquina; en un disco más rápido conviene medir de nuevo (`AVACOM_NODO_MARGEN_SECUENCIA`).
- **Las secuencias de las colas antiguas y la global se solapan hasta el corte**: hoy no importa (nadie lee `m15_evento` como fuente de un módulo no cortado); al cortar, el contador salta por encima del último id legado (probado con historia real en las seis paridades).
- **Las seis migraciones de corte usan los modelos vivos de `nodo` por su interfaz** (`nodo.servicios.cortar`), no los históricos: si una migración posterior de `nodo` cambiara `m15_corte`, `m15_evento` o `sqlite_sequence`, debe declararse como dependencia en ellas (hoy dependen de `nodo 0003`). Un `migrate` desde cero sigue siendo válido mientras eso se respete. Y **toda migración que reconstruya `m15_evento` debe terminar con `SQL_CREAR` y `SQL_REPARAR_CONTADOR`** (D-28): la regla está en el docstring de `infraestructura/triggers.py` y el arranque la respalda.
- **Un `agregado_id` de más de 256 caracteres falla en duro** (`SobreIncompleto`, también en producción: el tope del sobre no entra en la degradación R-06, que es sólo para la carga). El libro compone `alumno:grupo:periodo:curso_ref` sin recortar (≈ 130 hoy); con una referencia de curso de más de ≈ 180 caracteres su consumidor reintentaría ese evento y lo dejaría atrás con asiento. Hallazgo 8; la Fase 4 (consumidores sobre el registro) es el momento de decidir si el libro debe componer ese agregado con identificadores.
- **`TransactionTestCase` vacía `m15_corte` con el resto de tablas** tras cada una de sus pruebas: el resto de la corrida ve los módulos «sin corte» y lee sólo `m15_evento`. Es inocuo (en pruebas la cola antigua está vacía) y explica por qué las paridades siembran su propia historia con `recortar`.
