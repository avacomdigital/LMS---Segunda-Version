# 16 · Node Platform y Cola de Salida (MOD-015) · Pruebas

| Campo | Valor |
|---|---|
| Estado | Verificado el **2026-10-21** sobre el código final de las Fases 0 a 2 (más la API y la pestaña de OPS), sin commit. Lo que **no** se pudo comprobar está en el [§5](#5--lo-que-no-se-probó): léelo antes de dar el tramo por cerrado. |
| Qué dice cada documento | Diseño y decisiones: [01-diseno.md](01-diseno.md) · contrato: [02-api.md](02-api.md) · operación: [04-operacion.md](04-operacion.md). |

## 1 · En una mirada

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
| BR-016 / R-04 lo publicado no se borra ni transforma | el trigger; ninguna tabla `*_evento_salida` se toca (nada se cortó) |
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

1. **Ningún módulo real cortado**: la fachada y el corte se probaron con un lector legado falso. La paridad por módulo es de la Fase 3.
2. **La pantalla de OPS no se abrió en vivo** (sin nodo aislado en 8010, sin UI Automation ni capturas con la regla de tercios): se verificó por su lógica pura contra las respuestas reales y por compilación. Queda para el cierre de la Fase 7.
3. **Corte eléctrico real** (NFR-014): aquí sólo un proceso muerto con `os.kill`. El sistema operativo y el disco pueden mentir sobre `fsync` (Q-N8).
4. **NFR-013 (3 minutos)**: no se midió un arranque completo; la máquina de arranque es de la Fase 5.
5. **`synchronous=FULL` explícito y el `integrity_check` completo** (Fase 5): hoy se hereda FULL (medido) y sólo corre `quick_check`.
6. **El `503` del modo restringido**: el estado se evalúa y se publica, pero nada lo responde todavía (D-13).
7. **Tabletas físicas, 100 equipos reales, discos del panel, antivirus, instalación real elevada**: no.
8. **Student**: sin cambios ni pruebas (nada nuevo que ver hasta la Fase 5).
9. **La parada limpia desde el servicio de Windows**: el gancho `atexit` no corre si el host mata el proceso (D-18); se verá como «apagado sucio» en el siguiente arranque.
10. **La revisión independiente por otro agente** del prompt está prevista al terminar las Fases 3 y 5, no en este tramo.
