# 16 · Node Platform y Cola de Salida (MOD-015) · Diseño, decisiones y alcance

| Campo | Valor |
|---|---|
| Estado | **Fases 0 a 2 implementadas** (2026-10-21) más la API `/api/nodo/` y la pestaña «Estado del equipo» de OPS (P-17 y P-18 en lo que no depende de las fases 3 a 6). **Ningún módulo se cortó** a la cola única: las diez colas `m*_evento_salida` siguen como están (Fase 3, en dos sesiones). Backend `backend/nodo/` (app Django, tablas `m15_*`), cliente `src/Avacom.Lms.Core/Nodo/`, lógica de OPS en `src/Avacom.Lms.Ops/Nodo/` y la pestaña en `Pages/BitacoraPage.Equipo.cs`. |
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

| NO entra (queda preparado y dicho) | Por qué |
|---|---|
| **Cortar cualquier módulo** (Fase 3) | P-01: un módulo por paso, con paridad. Este tramo construye y prueba la cola **sin mover a nadie**. |
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
├── dominio/                 puro, sin Django: catalogos · catalogo (+ catalogo_datos generado) · sobre · reintentos · purga · anclas · corte · estado · errores
├── aplicacion/              casos de uso, sin Django: puertos · base (config y estado vivo) · publicar · leer (fachada y corte) · consumidores · purga · estado · arranque
├── infraestructura/         ORM (repositorios, unidad de trabajo), anclas en archivo, contexto de MOD-019, salud del equipo, autorización por MOD-001, respaldo ausente, triggers, contenedor
├── interfaces/              vistas DRF y rutas (/api/nodo/)
├── migrations/              0001_initial · 0002_triggers
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

## 5 · Inventario de las colas (Fase 0, regenerable)

| Cola | Módulo | Tipos que produce | Quién la lee hoy | Marca del lector |
|---|---|---|---|---|
| `m01_evento_salida` | acceso | `identidad.*` (40) | nadie | — |
| `m07_evento_salida` | classroom_engine | `aula.*` (22) | reporting, search | `m13_marca_consumidor`, `m21_marca_lectura` |
| `m08_evento_salida` | modo_estudio | `estudio.*` (12) | reporting, search | ídem |
| `m09_evento_salida` | device_manager | `dispositivo.*` (9) | reporting (sólo por id, no la cola) | — |
| `m10_evento_salida` | evaluacion | `evaluacion.*` (29) | gradebook, reporting, search | `m11_marca_consumidor`, `m13_marca_consumidor`, `m21_marca_lectura` |
| `m11_evento_salida` | gradebook | `calificacion.*` (20) | reporting | `m13_marca_consumidor` |
| `m13_evento_salida` | reporting | `reporte.*` (9) | nadie | — |
| `m18_evento_salida` | licenciamiento | `licencia.*` (12) | nadie | — |
| `m19_evento_salida` | audit | `auditoria.*` (5, catálogo cerrado) | nadie | — |
| `m21_evento_salida` | search | `busqueda.*` (6) | nadie | — |

Todas con la misma forma (`agregado_tipo`, `agregado_id`, `tipo_evento`, `carga`, `creado_en`, `publicado_en`, `intentos`) e `id` autoincremental por tabla. Todas tienen el **mismo puerto** `publicar(agregado_tipo, agregado_id, tipo_evento, carga)` salvo `acceso` (`publicar(EventoSalida)`) y `audit` (`infraestructura/eventos.py`): son el punto de corte de la Fase 3.

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
6. Ninguna carga de los catálogos trae claves de la lista prohibida; las cargas reales se revisarán en vivo con la paridad de la Fase 3.

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

Fase 3 (dos sesiones): `device_manager`, `search`, `reporting`, `modo_estudio`, `classroom_engine`, `gradebook`; luego `evaluacion` (con la prueba de proceso muerto sobre respuestas), `acceso`, `audit`. Por módulo: el adaptador llama `nodo.servicios.publicar` (sin doble escritura), `registrar_lector_legado` + `cortar(modulo, max(id))` en una migración de datos, `servicios.eventos_desde` pasa a `nodo.servicios.leer`, paridad, suite en verde. Fase 4: los tres consumidores a `aplicar_lote`. Fase 5: arranque completo, supervisor, 503, `synchronous`, llamada desde `avacom_ops_backend.py`. Fase 6: reloj y huella con MOD-018. Fase 7: lo que falte de pantalla (servicios con latido). Fase 8: continuidad y carga.

**Pendiente de documentación:** `spec-driven/10-modelo-datos-implementado.md` no se regeneró (su pipeline vive en `specs/analisis/`, material privado fuera del repo): las ocho tablas `m15_*` están descritas en §3 y en los docstrings de `nodo/models.py`.

## 11 · Riesgos

- **El gancho `atexit` no corre si el servicio mata el proceso** → falsos «apagado sucio» hasta la Fase 5 (D-18). Sólo informa; no cambia el estado.
- **La cola crece sin purga** (Q-N3): ≈ 0,6 GB/año estimados con las cargas de hoy.
- **El margen de 10 000** cubre lo emitible en el intervalo del ancla en esta máquina; en un disco más rápido conviene medir de nuevo (`AVACOM_NODO_MARGEN_SECUENCIA`).
- **Las secuencias de las colas antiguas y la global se solapan hasta el corte**: hoy no importa (nadie lee `m15_evento` como fuente de un módulo no cortado); al cortar, el contador salta por encima del último id legado.
