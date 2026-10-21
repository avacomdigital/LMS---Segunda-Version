# 16 · Node Platform y Cola de Salida (MOD-015) · Pruebas

| Campo | Valor |
|---|---|
| Estado | Fases 0 a 2 verificadas el **2026-10-21** (§1 a §5). **Fase 3, primera sesión, verificada el 2026-10-21** sobre el código final (§6 a §8), sin commit. Lo que **no** se pudo comprobar está en el [§5](#5--lo-que-no-se-probó) y en el [§8](#8--fase-3-lo-que-no-se-probó): léelos antes de dar el tramo por cerrado. |
| Qué dice cada documento | Diseño y decisiones: [01-diseno.md](01-diseno.md) · contrato: [02-api.md](02-api.md) · operación: [04-operacion.md](04-operacion.md). |

## 0 · Fase 3, primera sesión (2026-10-21): seis módulos cortados

| Qué | Resultado |
|---|---|
| Backend · **toda** la suite con los seis cortes (`manage.py test`) | **2512 pruebas, OK, 18 omitidas, 1208 s** (corrida de verificación de la sesión que construyó las Fases 0–2, sobre el árbol final de la Fase 3). Incluye las 128 pruebas de MOD-017 (`actualizacion`), que otra sesión añadió al árbol mientras tanto; 2367 de la Fase 2 + 16 de paridad + 1 de D-28 = 2384 de MOD-015 **sin ninguna prueba existente eliminada**. **Lo que pasó antes, tal cual:** la corrida de la sesión de la Fase 3 (15:06–15:36, 1853 s) terminó con **2 fallos**, los dos en pruebas de la Fase 2: `test_r08_…p95` dio 2,39 ms con la suite y un MSBuild compitiendo por la CPU (a solas, 0,23 ms) y `test_r02_fuera_de_la_transaccion…` esperaba la secuencia 1 y recibió la 100 (el vaciado entre `TransactionTestCase` no devuelve el AUTOINCREMENT a cero y `reset_sequences`, D-23, no lo arregló en SQLite). Esa sesión las repitió aisladas en verde y las dio por pasadas; aquí se dejó constancia del fallo, se hicieron robustas las dos pruebas (D-29: secuencia relativa al contador; la mejor de cinco tandas, y `AVACOM_NODO_SIN_MEDICION=1` deja sólo la comprobación estructural) y se repitió la suite **entera** hasta verla en verde. |
| Backend · los seis módulos cortados + `nodo` antes del tope de 256 (D-26) | 1095 pruebas: `device_manager`, `search`, `modo_estudio` y `classroom_engine` **enteros en verde**; en `gradebook` 127 fallos y en `reporting` 3 (sus boletines, que leen el libro), **todos por la misma causa**: el libro compone `agregado_id` de ≈ 130 caracteres y el sobre admitía 96 (`SobreIncompleto`), así que su consumidor perdía el evento dentro de su savepoint. Corregido con `nodo/0003_agregado_id_256`; la suite completa de arriba es la corrida sobre el código corregido. |
| Backend · paridad por módulo (`<modulo>/tests/test_paridad_cola.py`, 16 pruebas) | **16 OK** (§6): mismo tipo, versión, agregado y carga en `m15_evento` que lo que publicó cada caso de uso; cero filas nuevas en la cola antigua; historia sembrada + corte + marca a mitad de la historia + marca cero, por la fachada y por los consumidores reales de Reportes y Búsqueda. |
| Backend · app `nodo` (`manage.py test nodo`) | **116 OK** con los seis cortes (1 omitida: la captura de contrato; 48 s): las 115 de la Fase 2 más `test_d28_*` (§7). `test_corte.py` simula ahora sobre `licenciamiento` (D-23). `publicar` sigue en p50 0,22 ms · p95 0,68 ms con la CPU libre (con la suite completa corriendo al lado el p95 pasó de 1,5 ms una vez: la prueba R-08 es sensible a la carga de la máquina). |
| `makemigrations --check` | Sin cambios pendientes (todas las apps). Migraciones nuevas: `nodo 0003`, `device_manager 0006`, `search 0003`, `reporting 0003`, `modo_estudio 0002`, `classroom_engine 0004`, `gradebook 0004`. |
| Core · OPS · Student (`dotnet test`) | **2195 OK · 499 OK · 102 OK** (sin cambios en C#: la Fase 3 es sólo backend; se corrieron igual). |
| Instalador **2.11.0** (`installer/latest`) | **Construido y ensayado de punta a punta** a las 14:02 (`Build-Installer.ps1 -OmitirPruebas -VersionAnterior dist\anterior-2.10.0`, 945 s): el bloque B actualizó con el host nuevo una base de la **2.10.0 con datos** (las seis migraciones de corte y `nodo 0003`), `integrity_check` ok, claves conservadas; A, C, D y E también en verde. `AVACOM-OPS-Master-Setup-2.11.0.exe`, 105,9 MB, SHA-256 `B7850F86…5721F4`, con `SHA256.txt` y `LEEME.txt`. **Es el árbol de la Fase 3 sin D-28** (la reparación del contador llegó después): no cambia el comportamiento de la 2.11.0, cuyas migraciones ya van en el orden correcto; protege las migraciones futuras. **La reconstrucción con D-28 no se pudo hacer**: la segunda construcción se colgó al publicar OPS (MSBuild sin CPU 30 min, con la suite completa y otra sesión compilando Student al lado) y la tercera falló en el paso 6 porque otra sesión añadió en este mismo árbol `backend/actualizacion/` (MOD-017, ya en `INSTALLED_APPS`) cuya `tests/test_arquitectura.py` trae el literal «BEGIN PRIVATE KEY» que el escaneo de secretos del paquete rechaza; además, cualquier paquete construido ahora llevaría ese módulo a medias. Cuando el árbol vuelva a ser sólo MOD-015: `Build-Installer.ps1 -OmitirPruebas -VersionAnterior dist\anterior-2.10.0`. No se instaló en un equipo de aula. |
| Revisión independiente del diff (otro agente, sólo lectura) | **(en curso: resultado al final de esta sección)** |

**Mediciones de la Fase 3.** Ninguna nueva: `publicar` no cambió (0,15 ms p50, 1 INSERT) y la fachada añade una consulta a `m15_corte` por lectura (`corte_de`), que Reportes y Búsqueda hacen una vez por fuente y por ciclo.

## 1 · En una mirada (Fases 0 a 2)

| Qué | Resultado |
|---|---|
| Línea base **antes** de tocar nada (`manage.py test`, todas las apps) | **2252 pruebas, OK, 14 omitidas, 818 s** |
| Backend · **toda** la suite con el módulo (`manage.py test`) | **2367 pruebas, OK, 15 omitidas, 1011 s** (2252 + 115 nuevas; la omitida nueva es la captura de contrato) · **ninguna prueba existente cambió**. El instalador se construyó con `-OmitirPruebas` sobre este mismo árbol inmediatamente después de esta corrida. |
| Backend · app `nodo` (`manage.py test nodo`) | **115 pruebas, OK** (1 omitida: la captura de contrato, que sólo corre con `AVACOM_CAPTURAR_CONTRATO`); 5,5 s sin la de concurrencia, ≈ 35 s con ella |
| `makemigrations --check` | Sin cambios pendientes (`nodo` y `acceso`) |
| Core (`dotnet test`) | **2195 OK** (de ellas, 15 de MOD-015: contrato contra las respuestas reales, textos y reglas) |
| OPS (`dotnet test`, sin MAUI) | **499 OK** (7 de MOD-015: las líneas del nodo, la cola, el reproceso con un solo envío) |
| Student (`dotnet test`) | **102 OK** (sin cambios: MOD-015 no toca Student en este tramo) |
| Compilación de OPS Master para Windows (`dotnet build -c Release`) | **0 errores, 0 advertencias nuevas** (la única advertencia es la preexistente de `ReporteBoletinPage.Cabecera`, CS0108) |
| Instalador **2.10.0** (`installer/latest`) | **Construido y ensayado de punta a punta** (`Build-Installer.ps1 -OmitirPruebas -VersionAnterior <staging 2.9.1>`, 540 s): `Ensayar-Paquete.ps1` pasó los bloques A (instalación nueva), B (**actualización desde la 2.9.1 con datos**: las migraciones `nodo 0001-0002` y `acceso 0019` sobre una base creada por el backend viejo, y el administrador vuelve a entrar), C (sin configuración), D (lanzador) y E (migración que falla no pierde nada). `AVACOM-OPS-Master-Setup-2.10.0.exe`, SHA-256 `4AAE1DC1…B6826D`, con `SHA256.txt` y `LEEME.txt`. **No** se instaló en un equipo de aula (§5). |
| Verificación en vivo con UI Automation y capturas | **No hecha en este tramo** (§5): la pestaña se probó por su lógica pura y contra las respuestas reales; la pantalla no se abrió con un nodo aislado |

## 2 · Qué cubre cada suite

**Backend** (`backend/nodo/tests/`, 115 pruebas):

| Archivo | Pruebas | Qué comprueba |
|---|---|---|
| `test_dominio.py` | 33 | **Fase 1, sin Django.** El sobre con sus doce campos y lo que se rellena con el sistema; R-13 (claves prohibidas a cualquier profundidad, tope, en pruebas falla y en producción se omite); BR-122 en las dos formas y lo que rechaza; el catálogo entero con una clase, una sensibilidad y una retención por tipo, los nueve del Maestro y las extensiones; la máquina de reintentos (duplica con tope, jitter determinista con semilla, aparta al máximo) y el saneado de errores; **la tabla de verdad completa de BR-017 (16 combinaciones)**, la retención mínima, lo permanente y lo inmutable, BR-019 sin huecos y BR-018; las anclas (los cuatro casos del arranque, refresco por tiempo o eventos, nunca un valor menor) y el reloj; el corte (contador, plan de lectura, fusión); los estados del nodo con histéresis y las rutas núcleo. **Propiedades con semilla fija** (`SEMILLA = 20261021`): tras restaurar nunca se repite una secuencia (200 corridas), la marca alta nunca baja (5000), una marca previa al corte no pierde ni repite y marca cero reproduce todo (150 corridas con límites y tamaños al azar). |
| `test_arquitectura.py` | 23 | Dominio y aplicación sin Django ni otros módulos; dependencias hacia adentro; las vistas sin ORM; R-09 (nodo no lee tablas ajenas: sólo `audit`, la política de `acceso` y el reloj de la evaluación; nadie fuera de `nodo` toca `m15_*`); el único borrado es la purga; sin internet ni dependencias nuevas; las rutas núcleo existen; las ocho tablas `m15_*` sin FK, sin columnas de contenido ni personas, con `AUTOINCREMENT` y los doce campos; `makemigrations --check`; los triggers existen, **el sobre es inmutable y la marca alta sólo sube**; permisos sembrados y reparto por rol (ADMIN los tres, TECHNICIAN lectura, nadie más); acciones de bitácora y eventos en los catálogos cerrados; cada tipo que los adaptadores de outbox pueden escribir hoy está en el catálogo de la cola. |
| `test_publicar.py` | 14 | Sobre completo con secuencia; actor, aparato y correlación del contexto de la petición (y «aparato:» para una tableta sin sesión); **R-02: una excepción tras publicar no deja ni hecho ni evento y la transacción revertida no consume número; fuera de transacción falla sin escribir** (en `TransactionTestCase`); secuencia estrictamente creciente; R-06 en pruebas (falla) y en producción (entra marcado con ERROR y asiento, sin la carga en el asiento); R-13; `leer` por módulo y tipos con `hasta`; el ancla se refresca por lotes en la carpeta temporal (jamás ProgramData); **`publicar` p95 < 1,5 ms y exactamente 1 consulta**; el reloj no retrocede. Imprime las mediciones. |
| `test_consumidores.py` | 12 | Consumidor nuevo en cero que aplica sólo su fuente y sus tipos; **reproducir desde 0 da el mismo estado y los repetidos se descartan** (BR-007/008); la marca no pasa del evento que falla y el reintento espera (reloj falso, nada duerme); **al agotar los intentos se aparta, la marca avanza hasta él y lo de detrás se relee**; **reprocesar es idempotente, falla si la causa sigue, exige quién aplique y deja asiento**; **un consumidor v1 recibe una v2 con campo extra sin fallar** y una versión que nadie produce se rechaza (INV-006/007); registro mínimo e idempotente; desregistrar (BR-018); rezago que suspende y avisa una vez; **la cola y los problemas no llevan ninguna carga**; eventos técnicos por lote (uno por lote) y apagables; `hasta_vaciar`. |
| `test_corte.py` | 7 | Con un lector legado **falso** (ningún módulo real se corta): el corte sube el contador y deja asiento y evento; de una sola vía; en transacción; **la fachada sirve un flujo continuo legado + nuevo**, filtra por tipos en los dos lados; **una marca previa al corte sigue valiendo (ni pierde ni repite) y marca cero reproduce toda la historia**; un módulo cortado sin lector no se sirve a medias; un problema sobre un evento legado se reprocesa por la fachada. |
| `test_purga.py` | 4 | Apagada por defecto; **con el respaldo ausente nunca borra y dice por qué**; con un respaldo falso borra sólo lo elegible, en orden y sin huecos, nunca lo inmutable, el contador no retrocede, un consumidor rezagado retiene y uno desregistrado deja de retener; la sincronización exige reconocimiento. |
| `test_arranque.py` | 13 | Arrancar abre la fila, publica `servicios_iniciados` y parar la cierra; apagado sucio; **restaurar una copia vieja no repite ninguna secuencia** (ancla por delante → salto con margen, `recuperacion_completada` con sus campos, asiento); sin ancla y con eventos también; ancla dañada o alterada = ausente sin impedir arrancar; lo normal no salta; la marca alta sobrevive al arranque; el estado operativo y la salud publicada **sólo al cambiar**; sin `IMMEDIATE` → restringido con evento y asiento (y vuelta); la lectura real de la salud; `/health/` suma `nodo` sin tocar la base; un consumidor núcleo suspendido restringe. |
| `test_api.py` | 7 | Por rol: administración y técnico ven estado y cola; profesor y alumno 403 con asiento `nodo.acceso_denegado`; problemas sin carga; **el técnico reprocesa sólo con escalada** (403 con el texto de cómo conseguirla, 200 con ella, asiento con su id); la administración reprocesa y reproduce; 404/409/400 con sus códigos; reproceso que vuelve a fallar → 409; con sesión obligatoria lo anónimo recibe 401; el actor de la sesión llega al sobre de lo que publica el nodo. |
| `test_concurrencia.py` | 1 | En un subproceso sobre una base de **archivo** temporal (`nodo/tools/prueba_concurrencia.py`): 20 hilos, 4 procesos, restauración y proceso muerto (§3). |
| `test_capturar_contrato.py` | 1 | Captura las respuestas reales a `tests/Avacom.Lms.Core.Tests/Fixtures/nodo/` (16 archivos). Sólo con `AVACOM_CAPTURAR_CONTRATO`. |

**Core** (`tests/Avacom.Lms.Core.Tests/`): `ContratoNodoTests` (7: cada archivo capturado se lee con su DTO y **ninguno trae `carga`**; estado, restringido, cola, problemas, reproceso, errores, health), `NodoTextoTests` (8: cada estado, motivo, estado de consumidor y problema y cada error tiene su frase sin huecos ni «null»; cifras, fechas y tamaños en español; quién ve el nodo; el banner sólo con restringido o en recuperación y nunca con clase abierta; orden del peor al mejor).

**OPS** (`tests/Avacom.Lms.Ops.Tests/`, sin MAUI): `NodoLogicaTests` (7: las líneas de un nodo operativo y de uno restringido —nada «no medido» sale como cero, el último punto de recuperación dice que MOD-016 no existe—, restauración y apagado sucio, la cola del peor al mejor con sus fuentes y reintentos, el resumen de una línea, y [Reprocesar]/[Reproducir] con **un solo envío aunque se toque dos veces** y el mensaje de «sin permiso» que dice cómo conseguir la escalada).

## 3 · Mediciones (en esta máquina, no en un equipo de aula)

| Qué | Cifra | Cómo |
|---|---|---|
| Commit durable (`synchronous=FULL`, WAL, un evento por transacción) | **p50 1,30 ms · p95 1,73 ms · p99 2,92 ms** (NORMAL: 0,07 / 0,16 / 1,51) | `scratchpad/medir_commit.py`, 2000 commits, SQLite 3.49.1, disco de esta máquina |
| `publicar` dentro de la transacción del hecho | **p50 0,15 ms · p95 0,23 ms · 1 consulta** | `test_publicar.py`, 1000 eventos, base en memoria |
| Tamaño de un evento con carga de 256 B | ≈ 1,7 KB (archivo con WAL) · ≈ 0,6 KB (memoria) | Fase 0 · `test_publicar.py` |
| 20 hilos × 50 eventos, una transacción cada uno | **1000 secuencias sin huecos ni repetidos · 0 «database is locked» · 2,9 s · ≈ 345 commits/s** | `prueba_concurrencia.py` |
| 4 procesos × 50 eventos contra la misma base | 200 sin huecos · 4,5 s | ídem |
| Copia vieja restaurada (la base vuelve a la 1200 cuando se emitió hasta la 1320) | restauración detectada · contador 11 320 · primera secuencia nueva 11 324 · **ninguna repetida** | ídem |
| Proceso matado a mitad de transacción (lotes de 10 con pausa dentro) | `quick_check` ok · 6 lotes completos · **0 a medias** | ídem (`os.kill` desde el padre) |

## 4 · Reglas del Maestro y del prompt, con su prueba

| Regla | Prueba |
|---|---|
| BR-001 / INV-022 / R-02 hecho y evento juntos, o ninguno | `test_publicar.py::test_r02_*` (dos) |
| INV-002 / P-02 / P-12 secuencia estrictamente creciente, nunca reutilizada ni tras restaurar | `test_publicar.py::test_la_secuencia_es_estrictamente_creciente`, `test_arranque.py::test_p12_*`, `test_dominio.py::test_propiedad_tras_restaurar_*`, `test_concurrencia.py` |
| BR-002 / P-03 sobre de doce campos, inmutable | `test_dominio.py::SobreTests`, `test_arquitectura.py::TriggersTests` |
| BR-005 la marca avanza en la misma transacción | `test_consumidores.py::test_br005_*` (y el savepoint de `aplicar_lote`) |
| BR-007 / BR-008 marca cero reproduce todo; repetidos descartados | `test_consumidores.py::test_br008_*`, `test_corte.py::test_una_marca_previa_*` |
| BR-011 / INV-006 / INV-007 versiones | `test_consumidores.py::test_inv006_*` |
| BR-016 / R-04 lo publicado no se borra ni transforma | el trigger; en la Fase 3 ninguna fila de las seis tablas antiguas se borra ni cambia: cada `test_paridad_cola.py` comprueba que la historia sembrada sigue intacta tras el corte y que la tabla antigua no recibe ninguna fila nueva |
| BR-017…019 / INV-009 purga | `test_dominio.py::PurgaTests` (tabla de verdad), `test_purga.py` |
| BR-122 nombres | `test_dominio.py::CatalogoTests` |
| BR-127 / R-13 sin datos personales | `test_dominio.py::test_r13_*`, `test_publicar.py::test_r13_*`, `test_consumidores.py::test_cap097_*`, `test_api.py` |
| BR-130 nada que no cambie estado | `test_arranque.py::test_operativo_sin_motivos_y_salud_publicada_solo_al_cambiar` |
| R-06 falla operativa, nunca cierre | `test_publicar.py::test_r06_*` |
| R-08 un INSERT ≤ 1 ms p95 | `test_publicar.py::test_r08_*` |
| R-09 un escritor por tabla, sin leer tablas ajenas | `test_arquitectura.py` |
| P-17 permisos y escalada | `test_arquitectura.py::PermisosYCatalogosTests`, `test_api.py` |
| FUN-162/163/164 reintento, apartado, reproceso | `test_consumidores.py` |

## 5 · Lo que NO se probó (léelo antes de cerrar el tramo)

1. **Ningún módulo real cortado** en las Fases 0 a 2: la fachada y el corte se probaron con un lector legado falso. La Fase 3 cortó seis con paridad real (§0, §6); quedan cuatro.
2. **La pantalla de OPS no se abrió en vivo** (sin nodo aislado en 8010, sin UI Automation ni capturas con la regla de tercios): se verificó por su lógica pura contra las respuestas reales y por compilación. Queda para el cierre de la Fase 7.
3. **Corte eléctrico real** (NFR-014): aquí sólo un proceso muerto con `os.kill`. El sistema operativo y el disco pueden mentir sobre `fsync` (Q-N8).
4. **NFR-013 (3 minutos)**: no se midió un arranque completo; la máquina de arranque es de la Fase 5.
5. **`synchronous=FULL` explícito y el `integrity_check` completo** (Fase 5): hoy se hereda FULL (medido) y sólo corre `quick_check`.
6. **El `503` del modo restringido**: el estado se evalúa y se publica, pero nada lo responde todavía (D-13).
7. **Tabletas físicas, 100 equipos reales, discos del panel, antivirus, instalación real elevada**: no.
8. **Student**: sin cambios ni pruebas (nada nuevo que ver hasta la Fase 5).
9. **La parada limpia desde el servicio de Windows**: el gancho `atexit` no corre si el host mata el proceso (D-18); se verá como «apagado sucio» en el siguiente arranque.
10. **La revisión independiente por otro agente** del prompt está prevista al terminar las Fases 3 y 5, no en este tramo (hecha en la Fase 3: §0 y §7).

## 6 · Fase 3 · qué comprueba la paridad y qué cambió en las pruebas existentes

**Las 16 pruebas de paridad** (`<modulo>/tests/test_paridad_cola.py`), con los flujos REALES de cada módulo por HTTP (las mismas bases de pruebas que ya usaba cada uno) y el espía `nodo.pruebas.espiar(OutboxDjango)`, que registra lo que cada caso de uso quiso publicar:

| Módulo | Escenario | Qué demuestra |
|---|---|---|
| `device_manager` (2) | registrar una tableta, bloquearla, desbloquearla, asignarla y liberarla | Los cinco eventos en `m15_evento` con el tipo, el agregado y la carga exactos; `modulo`, `version=1`, `catalogado`, sin `carga_omitida`; `evento_id` únicos; el actor de la sesión del administrador; **cero filas en `m09`**. Con historia sembrada (`sembrar_historia` + `recortar`): la fachada sirve historia + nuevo como un flujo; marca a mitad de la historia, marca en el corte y marca al día; filtro por tipos en los dos lados; el lector legado con `desde < id ≤ hasta` y su `hasta` (lote lleno vs tope); la historia sigue intacta (BR-016). |
| `classroom_engine` (2) | iniciar una clase, unirse una tableta, cerrar | Ídem, leído por `servicios.eventos_desde` (lo que llaman Reportes y Búsqueda) con los tipos que consumen; `ultima_secuencia()` = última de la historia sin nada nuevo, y la última nueva después (D-27); tipos vacíos → nada. |
| `modo_estudio` (2) | asignación, lección abierta y completada, práctica con una respuesta | Ídem; **D-25**: `evaluacion.respuesta_registrada.v1` entra firmado por `modo_estudio`, con `modo=estudio`, y `nodo.leer("evaluacion", …)` NO lo devuelve. |
| `gradebook` (2) | examen entregado sin abiertas + `sincronizar` (calificación registrada, estado simple, agregados) | Ídem, leído por `reporting.infraestructura.fuentes.LibroFuente` (el adaptador real de Reportes). Es la prueba que encontró el `agregado_id` largo (D-26). |
| `reporting` (2 + 3) | como productor: clase completa, consumidor al día, reporte del grupo, reconstrucción. Como consumidor: una clase ANTES del corte (copiada a `m07` como historia), otra DESPUÉS; un estudio antes y otro después | Productor: ídem por la fachada. Consumidor: `ConsumirEventos.hasta_vaciar()` con la marca de `aula` en un id de la historia aplica exactamente lo de la historia que faltaba y luego lo nuevo (espía sobre `_Aplicador.aplicar`), deja la marca en `classroom_engine.servicios.ultima_secuencia()`, no reaplica nada al repetir, proyecta las dos clases; con la marca en cero reproduce historia + nuevo y las proyecciones quedan iguales; `estudio` con marca cero y con marca en el corte; **`/estado/` ve historia y nuevo como una sola cola**: `corte_en` es el instante anterior al evento más viejo de la HISTORIA sin aplicar. |
| `search` (2 + 1) | como productor: sincronización incremental y reconstrucción. Como consumidor: clase y estudio antes del corte (historia) y después | Productor: ídem. Consumidor: `Sincronizar` con la marca de `aula` en la apertura de la primera clase (un id antiguo) y `estudio` en cero indexa las dos clases y los dos estudios sin fallos, deja las marcas en `ultima_secuencia()` de cada dueño, una pasada más no lee nada, y con la marca en el corte sólo relee lo nuevo sin duplicar documentos. |

**Lo que cambió en las pruebas existentes (D-23), completo:**

- 20 archivos de pruebas de los seis módulos: `m.EventoSalida.objects` → `cola("<modulo>")` (53 lecturas: `device_manager` 9, `search` 5, `reporting` 12, `modo_estudio` 19, `classroom_engine` 4, `gradebook` 4), con el import `from nodo.pruebas import cola`. Cada aserción conserva su texto. Las lecturas de `m10.EventoSalida` (evaluación, no cortada) no cambian.
- `reporting/tests/test_proyeccion.py`: `test_el_estado_muestra_antiguedad_si_la_cola_va_por_detras` ya no hace `update(creado_en=…)` sobre `m07` (el sobre es inmutable): avanza el reloj diez minutos y espera `corte_en = creado_en del evento más viejo − 1` y `antiguedad ≥ 600 001`; `test_la_cola_de_estudio_de_una_tableta_marca_incompleto…` siembra el `estudio.trabajo.integrado.v1` con `cola("modo_estudio").create(...)` en vez de insertar en `m08`.
- `gradebook/tests/base.py`, `reporting/tests/base.py`, `search/tests/base.py`: `nodo_limpio()` en `setUp` (la marca alta del reloj del nodo no viaja entre pruebas con reloj falso).
- `nodo/tests/test_corte.py`: `MODULO = "licenciamiento"` y dos tipos `licencia.*` (antes `device_manager`, que ya está cortado de verdad); una prueba nueva, `test_d28_*`. `nodo/tests/test_dominio.py`: el `agregado_id` demasiado largo se construye con `cat.MAX_AGREGADO_ID + 1` en vez de 200 letras (D-26 subió el tope a 256). `nodo/tests/base.py`: `BaseNodoTransaccional.reset_sequences = True`, porque el vaciado entre `TransactionTestCase` no reinicia el AUTOINCREMENT y, desde el corte, la suite transaccional del WebSocket del aula publica 99 eventos en `m15_evento` antes que `test_r02_fuera_de_la_transaccion…`, que espera la secuencia 1 (la única falla de la primera corrida completa, 2384 pruebas). Nada más cambia.
- Ninguna otra prueba existente cambió: `acceso`, `audit`, `evaluacion`, `licenciamiento`, `cola_medios`, `expediente`, `biblioteca` quedan como estaban.

## 7 · Fase 3 · revisión independiente

Otro agente, de sólo lectura y sin las conclusiones de esta sesión, revisó el diff con las reglas y lo ya probado (informe completo en las notas de la sesión: `revision-independiente-fase3.md`). **Veredicto: sí cortaría los seis módulos en un aula con este diff**: ningún camino pierde, duplica ni reordena, ninguna publicación queda fuera de transacción (recorrió los ≈ 90 puntos de publicación de los seis módulos, las cuatro entradas de `device_manager.servicios` que publican con `Cajones()` y las unidades de trabajo de sólo lectura de `acceso` y el aula), los 76 tipos de los seis módulos están catalogados con el autor correcto, ninguna carga publicada trae claves prohibidas, los bordes de `planear`/`fusionar` contra `eventos_legados` son correctos y las migraciones son idempotentes y baratas con miles de filas. Hallazgos y qué se hizo con cada uno:

| # | Hallazgo | Qué se hizo |
|---|---|---|
| 1 | **Pérdida latente**: una migración futura que reconstruya `m15_evento` después de un corte devuelve el contador a `max(secuencia)` (SQLite) y el arranque no lo reparaba; el siguiente evento del módulo saldría bajo su corte y la fachada no lo serviría. Lo verificó en una base en memoria (`cortar(30000)` + `alter_field` → contador 3, el evento del aula en la 4, invisible). Este diff no lo dispara (los cortes dependen de `nodo 0003`). | **Corregido (D-28)**: `SQL_REPARAR_CONTADOR` al final de `nodo/0003` y regla en `triggers.py`; el arranque repone el piso (`piso_del_contador`) sin confundirlo con una restauración. Prueba nueva `test_corte.py::test_d28_*` (reconstrucción simulada, reparación por la migración y por el arranque, el evento siguiente sale sobre el corte y la fachada lo sirve). |
| 2 | `agregado_id` > 256 falla en duro también en producción (el libro no recorta su clave compuesta; hoy ≈ 130). | Documentado en `01-diseno.md` §11 y hallazgo 8; sin cambio: recortar un identificador en silencio sería peor. |
| 3 | D-27 decía «como antes» para `eventos_desde` con tipos vacíos y no era exacto (antes avanzaba `hasta`). | Texto de D-27 corregido; ningún llamador pasa tipos vacíos. |
| 4 | Bloqueo marginal: `publicar` serializa la carga y, como mucho cada 5 s / 1000 eventos, hace un `fsync` del ancla dentro de la transacción del hecho; no se repitió la prueba de 35 tabletas. | Ya estaba así desde la Fase 2 (medido: 0,15 ms p50 por `publicar`); queda en §8 como no medido con carga. |
| 5 | `sembrar_historia` corta por encima de las filas que el primer escenario dejó en `m15`: la paridad no ejercita «filas del módulo bajo el corte». | Es lo que produce el hallazgo 1, cubierto ahora por `test_d28_*`. |
| 6 | Las 51 sustituciones en pruebas son textuales y `nodo/pruebas.py` mapea bien; `test_el_estado_muestra_antiguedad…` pasa de `== 600 001` a `>= 600 001` con `corte_en` calculado. | Sin cambio. |
| 7 | `FuenteLegadaAusente` no se captura en el consumidor de Reportes (Search sí); sólo ocurre sin `apps.ready()`. | Sin cambio (D-20: mejor fallar que servir a medias). |

## 8 · Fase 3 · lo que NO se probó

1. **Una instalación real con historia en las colas antiguas**: la actualización 2.10.0 → 2.11.0 del ensayo del instalador corre las seis migraciones de corte sobre una base del backend anterior, pero esa base no tiene eventos en `m07`…`m21` (es la del ensayo); la historia se probó sembrándola en las paridades (`sembrar_historia`). No hay un aula con 2.10.0 instalada de la que tomar una base real.
2. **Corte eléctrico, tabletas físicas, 100 equipos, discos del panel, antivirus, instalación elevada**: igual que en las Fases 0 a 2.
3. **OPS en vivo**: la pestaña «Estado del equipo» muestra `cortes[]` (ya lo hacía) pero no se abrió con un nodo aislado; la Fase 7 lo cierra.
4. **`evaluacion`, `acceso`, `audit` y `licenciamiento`**: siguen en su cola antigua; sus consumidores (gradebook sobre `evaluacion`) no cambian.
5. **Rendimiento de la fachada con tablas antiguas grandes**: `eventos_legados` filtra por `id` (clave primaria) y `tipo_evento__in` sin índice por tipo en las tablas antiguas, como el `eventos_desde` que reemplaza; no se midió con miles de filas.
6. **El instalador con D-28 dentro**: `installer/latest` lleva el árbol de la Fase 3 anterior a D-28 (§0); la reparación del contador se verificó con `nodo` (116) y con la suite completa, no con un paquete ensayado.
