# Objetivo del módulo

Registra quién hizo qué, cuándo, sobre qué objeto y con qué resultado, en una bitácora que no se modifica ni se borra. Los asientos se encadenan con huella de verificación, de modo que un salto en la cadena es detectable. Es el módulo que permite demostrar que un técnico no accedió a datos personales de alumnos.

## Objetivos secundarios - Generales

1. Crear un sistema de logs en archivos de texto para poder hacer mantenimiento rápido en pruebas unitarias y testing de happy paths, sad paths y bad paths.
2. Registro en la base de datos en la tabla `bitacora`.
3. Registrar principalmente los movimientos en Classroom Engine.
4. Sistema de evaluaciones.

> **Lo que este documento es.** Sirve de prompt y de documentación para construir MOD-019 · Audit. Se lee de arriba abajo: §1 explica el funcionamiento; §2 fija el sistema de logs en archivo (instalación y pruebas incluidas); §3 revisa el modelo de datos actual y propone el nuevo; §4 especifica el backend; §5 el frontend de AVACOM LMS OPS y de AVACOM Student; §6 el orden de construcción y las preguntas abiertas.
>
> **Fuentes.** Documento Maestro Consolidado v1.0 (MOD-019, FUN-195…201, BR-097/099/100/105, INV-002/003/027, AC-003/054/081, VER-01/04, TST-071/072, NFR-036/039, PAN-240/241/242, DEC-022/034, MSG-052…054, ESC-03, CAP-116/117/118), el modelo v2 (`specs/analisis/segunda-version-modelo.md`, tablas `bitacora`, `evento`, `evaluacion`) y el código de `backend/` a 2026-09-30.

------------------------------

## Requerimientos específicos

| # | Requerimiento | Dominio | Tabla | OPS | Student |
|---|---|---|---|---|---|
| 019-01 | Asiento completo (FUN-195, BR-099, TST-071): actor, acción, objeto, valor anterior y nuevo, motivo, origen y dispositivo | Acceso y RBAC | Columnas en bitacora. El v2 no trae objeto, valores ni motivo. El adaptador de acceso guarda siempre valor_anterior=None | — | Identificar el aparato en cada llamada para poblar dispositivo y origen |
| 019-02 | Cadena de integridad (FUN-196, INV-002) | Acceso y RBAC | Columnas secuencia (monótona) y huella_previa/huella | — | — |
| 019-03 | Inmutabilidad real (BR-100, INV-027, AC-081). Hoy update(), delete(), bulk_* y SQL directo pasan | Acceso y RBAC | No (triggers de BD) | Sin editar ni borrar. Un intento deja asiento nuevo | — |
| 019-04 | Verificar la cadena y detectar saltos (FUN-198/199). Estados: activa, verificada, con salto, rotada | Acceso y RBAC | Nueva bitacora_tramo (desde, hasta, huella de cierre, estado, verificado_en) | Indicador «verificada» o «salto detectado» | — |
| 019-05 | Consulta filtrada por permiso (FUN-197, CAP-116, audit.read). Hoy sin permiso, sin filtros por actor, fecha ni entidad, y sin paginación | Acceso y RBAC | No (índices) | Pantalla «Bitácora» solo lectura (PAN-240), visible solo al Administrador. Escalada temporal (PAN-241) | — |
| 019-06 | Exportar un tramo firmado (FUN-200, BR-105, ESC-03, VER-04, TST-072) | Acceso y RBAC | bitacora_tramo (exportado_en, firma) | Exportador con alcance declarado y autorización por operación (MSG-054) | — |
| 019-07 | Rotación por tamaño (FUN-201). La retención de 5 años y la anonimización son V1 (CAP-117, BR-098) | Acceso y RBAC | bitacora_tramo (archivo, rotado_en) | — | — |
| 019-08 | Cobertura: denegaciones con roles activos, proyección de pantalla con autor y duración (DEC-034), excepciones de nivel, exportaciones, violaciones de INV-003. Hoy no se auditan avisos, presencia ni denegaciones | Acceso y RBAC | No (lista cerrada versionada, como evento.clave) | — | — |
| 019-09 | Derivar de la cola y publicar los 5 eventos auditoria.* (0 de 5). Depende de MOD-015 | Transversal | No | — | — |
| 019-10 | Demostrar que el técnico no accede a datos personales (CAP-118 V1, BR-097, VER-01) | Acceso y RBAC | No | Rol técnico con vistas sin datos de alumnos. Consulta «accesos del técnico» | — |

------------------------------

## Entradas y salidas

**Entradas**

- Acciones sensibles publicadas por los demás módulos, por evento o por llamada directa.
- Catálogo de acciones auditables.
- Consultas filtradas por permiso.
- Umbral de rotación por tamaño.

**Salidas**

- Asiento con actor, acción, objeto, valor anterior y nuevo, origen y dispositivo.
- Cadena de integridad verificable, con detección de saltos.
- Tramos exportables firmados.
- Eventos de creación, verificación, salto detectado y rotación.

**Además (objetivo secundario 1).** En archivo de logs deben mostrarse los errores referentes a escritura, comunicación o cualquier problema en el dispositivo donde se encuentra el LMS AVACOM y AVACOM STUDENT (§2.4).

------------------------------

# 1 · Introducción: cómo funciona

## 1.1 Tres cosas distintas que hoy se confunden

El Maestro dice que MOD-019 **no** incluye «los registros técnicos de servicio». Por eso este trabajo entrega dos sistemas de registro que comparten infraestructura pero no contenido, y que nunca se mezclan:

| | **Bitácora de auditoría** | **Logs de diagnóstico** | **Evento de clase** (`evento` v2) |
|---|---|---|---|
| Pregunta que responde | ¿Quién hizo qué, sobre qué, con qué resultado? | ¿Qué falló en el equipo? (escritura, red, dispositivo) | ¿Qué pasó con el alumno en la clase? |
| Dónde vive | Tabla `bitacora` (BD), encadenada | Archivos de texto rotativos en cada equipo | Tabla `evento` (BD), por participación |
| Quién la lee | Administrador (`audit.read`) | Técnico y quien prueba | Profesor, reportes |
| Se puede borrar | **Nunca** (5 años) | Sí, por rotación (días) | Por retención de clase (30 días) |
| Datos personales | Sólo lo necesario y por identificador | **Prohibidos** (ver §2.6) | Sí, por participación |
| Es evidencia | Sí | No | Parcial |

Regla de oro: **un mismo hecho no se duplica.** La auditoría no republica: referencia el `evento_id` de la cola de salida (`m0X_evento_salida`) cuando deriva de ella (FUN-195 y §3.2 del Maestro), y el log de archivo sólo registra *que* se escribió el asiento (número de secuencia), no su contenido.

## 1.2 Funcionamiento en una línea

```
Caso de uso (aula, acceso, dispositivos, estudio, evaluación)
   └─ dentro de SU transacción: uow.auditoria.registrar(...)           ← misma transacción que el hecho
         └─ Bitácora.anexar():  secuencia+1 · huella = SHA-256(huella_previa ‖ asiento)  ← BEGIN IMMEDIATE
               ├─ INSERT en bitacora (triggers impiden UPDATE/DELETE)
               ├─ línea en logs/auditoria.log  (nivel INFO, sin valores)
               └─ si falla: logs/errores.log  + el caso de uso hace rollback completo
   └─ temporizador: verificar_cadena()  → bitacora_tramo.estado = verificada | con_salto  → evento auditoria.*
   └─ umbral de tamaño: rotar()         → cierra tramo, nuevo tramo activo, archivo firmado
```

Si la bitácora no puede escribirse, **el hecho no ocurre** (rollback). Una acción sensible sin rastro es peor que una acción rechazada.

## 1.3 Qué se audita y qué no

- **Se audita (bitácora):** cambios de calificaciones, permisos, currículo congelado, dispositivos y retención (BR-099); todo lo de Classroom Engine que cambia el estado de la clase (inicio, admisión, expulsión, bloqueo, lanzamiento, cierre, proyección, avisos); evaluaciones y sus correcciones; denegaciones con la lista completa de roles activos; exportaciones (BR-105); intentos de alterar la propia bitácora; accesos y denegaciones del rol técnico.
- **No se audita (bitácora):** latidos, presencia por segundo, lecturas de contenido, pulsaciones, reconexiones de socket. Eso, si interesa, va a **logs de archivo** y a `evento` de clase. Una bitácora inundada de ruido no demuestra nada.
- **Nunca se audita como lectura** un tipo de clase *dominio* (BR-131), salvo la consulta a datos personales de menores, que sí es un asiento (`acceso.dato_personal.consultado`).

------------------------------

# 2 · Sistema de logs en archivos de texto

Es el objetivo secundario 1: poder abrir un archivo y entender en segundos por qué falló una prueba o un equipo del aula, tanto en **happy paths** (todo sale bien y queda constancia), **sad paths** (el caso previsto de error: credencial inválida, permiso denegado, conflicto) como **bad paths** (lo imprevisto: disco lleno, SQLite bloqueado, corte de red a media escritura, reloj desfasado).

## 2.1 Canales y archivos

Un archivo por canal, formato **JSON Lines** (una línea = un evento; se filtra con `grep`/`jq` y también se lee a simple vista con la herramienta de §2.7).

| Archivo | Quién escribe | Qué contiene |
|---|---|---|
| `backend-app.log` | Backend Django | Petición → caso de uso → resultado, con `ruta` happy/sad/bad |
| `backend-errores.log` | Backend | Sólo `WARNING` o superior con traza: escritura, base de datos, WebSocket, programador |
| `backend-auditoria.log` | Módulo Audit | Un renglón por asiento anexado (secuencia, acción, resultado; **sin valores**), verificaciones, saltos, rotaciones |
| `ops-app.log` / `ops-errores.log` | AVACOM LMS OPS (MAUI) | Lo mismo para el cliente del profesor/administrador |
| `student-app.log` / `student-errores.log` | AVACOM Student (MAUI) | Lo mismo para la tableta |
| `instalacion.log` | Instalador / `migrate` | Arranque, migraciones, apertura de la bitácora (asiento génesis), siembra |
| `pruebas-<corrida>.log` | Arnés de pruebas | Todo el backend durante una corrida, etiquetado por caso (ver §2.3) |

**Campos de cada línea** (mínimos):

```json
{"ts":"2026-09-30T10:15:02.314-05:00","nivel":"ERROR","canal":"escritura","app":"student",
 "modulo":"estudio","evento":"cola.persistir_fallo","ruta":"bad",
 "caso":"modo_estudio.test_asignaciones.test_entrega_sin_espacio",
 "dispositivo_id":"d-3f…","corr":"9c1e…","secuencia_bitacora":null,
 "mensaje":"No se pudo escribir la cola de respuestas","detalle":{"errno":28,"libre_mb":0},"traza":"…"}
```

`canal` es una lista **cerrada**: `escritura` · `comunicacion` · `dispositivo` · `aplicacion` · `auditoria` · `instalacion`. `ruta` es `happy` · `sad` · `bad` (el backend lo deduce: 2xx → happy; 4xx previsto → sad; excepción o 5xx → bad).

## 2.2 Dónde se escriben (por entorno)

La carpeta se decide **una sola vez al arrancar**, con esta prioridad:

1. Variable `AVACOM_LMS_DIR_LOGS` (la fija el instalador, una prueba o un técnico).
2. Entorno **instalado** (servicio `AVACOMOPSBackend`, `AVACOM_LMS_DEBUG=0`): `%ProgramData%\AVACOM\OPS Master\Logs\` — la carpeta que el instalador ya crea con la marca de no desinstalar (08-instalador §4 y regla 5.5).
3. Entorno de **desarrollo** (`manage.py runserver/daphne`): `backend\logs\` (en `.gitignore`).
4. Entorno de **pruebas** (`manage.py test`, o `AVACOM_LMS_ENTORNO=pruebas`): **una carpeta temporal por corrida** (`%TEMP%\avacom-lms-pruebas\<fecha-hora>\`). Jamás `ProgramData`: las pruebas no ensucian el registro real del equipo. Es el mismo principio que ya usa `AVACOM_LMS_DIR_FALLOS` en los clientes.

Clientes MAUI: Windows `%LOCALAPPDATA%\AVACOM\lms\logs\`; Android `FileSystem.AppDataDirectory/logs/`; ambos sustituibles por `AVACOM_LMS_DIR_LOGS` (pruebas UIA).

**Rotación y retención.** Por tamaño (2 MB por archivo, 5 archivos: `app.log`, `app.log.1`…) — el mismo criterio que `Registro.cs` del instalador. Los logs de diagnóstico **no** son evidencia: se pueden purgar; la retención de 5 años es de la bitácora, no de estos archivos.

## 2.3 Instalación y entornos de prueba (lo que no se puede olvidar)

**Durante la instalación** (`instalacion.log`):

1. El instalador (host) crea `Logs\` antes que cualquier otra cosa y escribe en `instalacion.log` cada paso con su resultado. Ya existen `preparacion-estado.txt`, `resumen-nodo.txt` y `respaldo-ultimo.txt`; se conservan y se suman a este archivo, no se sustituyen.
2. `migrate` (migración de datos de la bitácora, §3.4) deja en el log cuántas filas de `m19_auditoria` convirtió y cuál fue la huella final.
3. Al terminar la instalación se escribe el **asiento génesis** (`auditoria.bitacora_abierta`, secuencia 1, `huella_previa` = 64 ceros) — «MOD-019 abre la bitácora» del flujo de instalación del Maestro — y la línea correspondiente en `backend-auditoria.log`.
4. **Si no se puede escribir el log** (permisos, disco): la instalación **no falla por eso** (un fallo al registrar no tumba el servicio, como en `Registro.cs`), pero sí avisa en pantalla y cae a la carpeta de respaldo `%TEMP%\avacom-lms\logs\`. **Si no se puede escribir la bitácora, la instalación sí falla**, porque sin bitácora el nodo no es auditable.

**En un entorno de pruebas** (`manage.py test`, arnés UIA, pruebas de carga):

1. El arnés fija `AVACOM_LMS_ENTORNO=pruebas` y una carpeta por corrida. Cada caso marca `caso=<id del test>` en todas sus líneas (una mezcla `TestCase` + filtro de logging).
2. Cada base de datos de prueba arranca con la cadena **vacía pero válida**: el primer asiento de cada prueba crea su génesis (no se hereda la cadena de desarrollo).
3. Los triggers de inmutabilidad están **activos también en pruebas** (se crean por migración). Una prueba que necesite «romper» la cadena para verificar la detección de saltos lo hace con la utilidad `tools/romper_cadena.py`, que desactiva el trigger dentro de una transacción de prueba y lo restituye al salir; nunca con SQL suelto en el test.
4. Cada prueba de aceptación cuenta sus rutas: al menos un **happy** (queda el asiento y su línea), un **sad** (denegado/inválido también deja asiento de resultado `denegado` o `fallido`) y un **bad** (falla la escritura → rollback, `backend-errores.log` con traza, cero asientos parciales).
5. Helper de pruebas `LogsDePrueba` (mixin): `self.lineas_log(canal="escritura", nivel="ERROR")`, `self.assertLogged(evento="cola.persistir_fallo")`, `self.assertNoLogged(nivel="ERROR")` para garantizar que un happy path no deja errores escondidos.
6. Al terminar una corrida fallida el runner imprime la ruta de la carpeta de logs; si pasa, la borra (conservarla con `AVACOM_LMS_CONSERVAR_LOGS=1`).

## 2.4 Qué debe quedar en los logs de archivo (LMS AVACOM y STUDENT)

Esto es lo que pide el requisito: los errores del **dispositivo** donde corre el LMS y Student, no sólo las excepciones sin capturar (que hoy sólo guarda `RegistroDeFallos` en `fallos-{app}.log`, sin niveles, sin rotación y sin categorías).

| Canal | Qué se registra | Ejemplos concretos |
|---|---|---|
| `escritura` | Todo fallo al persistir | Disco lleno o `errno 28`; `IOException`/`UnauthorizedAccessException` al escribir la cola de respuestas (`ColaRespuestas`), el paquete de estudio o el log mismo; SQLite `database is locked` (hay varios hilos: vistas, sockets, programador); transacción revertida; escritura de la bitácora fallida; archivo de paquete con huella inválida |
| `comunicacion` | Todo fallo de red o de contrato | `HttpRequestException`, timeout, 401/403/409/5xx con la ruta (sin cuerpo con datos personales); caída y reintento del WebSocket (`ActivitySocketClient`, `AulaSocketClient`) con duración de la caída; nodo no alcanzable; `link.json` de Contenido ausente o con token rechazado; reloj del nodo vs reloj del equipo (`RelojNodo`) con el desfase medido |
| `dispositivo` | Condiciones del aparato | Espacio libre bajo; batería baja; cambio de red; arranque tras reinicio; versión de app; bloqueo por el administrador; clave de cifrado del equipo no disponible; WebView que no carga |
| `aplicacion` | Excepciones no controladas y lógica inesperada | Lo que hoy va a `fallos-*.log`; estados imposibles; componentes que no se pintan (p. ej. `D2DERR_BAD_NUMBER` de Win2D) |
| `instalacion` | Pasos del instalador | Ver §2.3 |

Cada línea lleva siempre `app` (`backend`/`ops`/`student`), `dispositivo_id` (si está registrado), versión de la app y el `corr` de la operación. Los clientes **heredan** `RegistroDeFallos` (mismo punto de entrada `Observar`) y lo amplían a `RegistroLocal` en `Avacom.Lms.Core/Services/`, con niveles, rotación y canales; `RegistroDeFallos.Escribir` queda como fachada para no tocar los sitios que ya lo llaman.

**Envío al nodo (mejor esfuerzo).** Student y OPS acumulan los renglones `WARNING+` y, cuando hay red del aula, los entregan con el latido (009-04) a `POST /api/logs/clientes/` (§4.5). El nodo los escribe en `backend-clientes.log` con el `dispositivo_id` autenticado. Si la entrega falla, el log local conserva todo: **la red no puede ser requisito para diagnosticar un fallo de red**.

## 2.5 Reglas de implementación (backend)

- `settings.LOGGING` con `dictConfig`: un `RotatingFileHandler` por canal, un formateador JSON propio (sin dependencias nuevas) y un filtro que agrega `caso`, `corr`, `dispositivo_id`.
- Un middleware asigna `corr` (UUID) por petición y lo devuelve en `X-Avacom-Correlacion`; ese mismo `corr` viaja al asiento de bitácora y al evento de cola (`correlacion_id`). **Con un identificador se reconstruye la operación entera**: petición, asiento, evento y error.
- Un `except` que traga una excepción **debe** registrarla (`logger.exception`). Prohibido el `except: pass` fuera de la escritura del propio log (que no puede recursar).
- El logger nunca eleva excepciones al llamador.

## 2.6 Privacidad de los logs

Los logs son texto plano legible por el técnico (BR-097). Por tanto: **ni contraseñas, PIN, tokens, cuerpos de petición, respuestas de alumnos, nombres ni DNI.** Sólo identificadores (`usuario_id`, `dispositivo_id`), códigos (`errno`, HTTP) y cifras. Un filtro de saneamiento descarta claves prohibidas (`secreto`, `pin`, `token`, `password`, `respuesta`, `nombre`) antes de escribir; una prueba lo verifica sembrando esos valores y comprobando que no aparecen.

## 2.7 Mantenimiento rápido

Herramienta `backend/tools/ver_logs.py`:

```
python tools/ver_logs.py --ultimos 50 --nivel ERROR --canal escritura
python tools/ver_logs.py --caso modo_estudio.test_asignaciones --ruta bad
python tools/ver_logs.py --corr 9c1e…          # sigue una operación de punta a punta
```

Imprime legible (hora, nivel, canal, mensaje) y resume por ruta: *happy 41 · sad 7 · bad 1*. La pestaña «Errores» de OPS (§5.1) lee lo mismo a través de la API.

------------------------------

# 3 · Modelo de datos

## 3.1 Estado actual (revisado en el código)

| Hallazgo | Dónde | Consecuencia |
|---|---|---|
| Existe `m19_auditoria` (`expediente.Auditoria`): `actor_id`, `accion`, `objeto_tabla`, `objeto_id`, `valor_anterior`, `valor_nuevo`, `momento` (ms) | `backend/expediente/models.py` | Es el embrión de `bitacora`. Falta dispositivo, origen, motivo, resultado, módulo, secuencia y huellas |
| «Sólo escritura» se impone únicamente en Python (`save`/`delete` lanzan `ValueError`) | mismo | `update()`, `delete()` de QuerySet, `bulk_*` y SQL directo pasan (019-03) |
| **Siempre `valor_anterior=None`** en el adaptador de acceso (`AuditoriaExpediente.registrar`); el puerto de Classroom Engine sí admite `anterior` pero casi nadie lo pasa | `acceso/infraestructura/repositorios.py`, `classroom_engine/aplicacion/puertos.py` | AC-054 (valor 72 → 80 con motivo) hoy es inalcanzable |
| Lo escriben **tres módulos por puertos distintos** y todos caen en `m19_auditoria`: acceso (`identity.*`), aula (`aula.*`, ~25 acciones), dispositivos (`dispositivos.*`) | `uow.auditoria.registrar(...)` | Hay que conservar la firma del puerto: ~30 llamadas no deben cambiar |
| `GET /api/auditoria/` (`AuditoriaView`): sin permiso, filtro sólo por `accion`, tope de 500 filas | `expediente/views.py` | Cualquier usuario autenticado lee todo (019-05) |
| `backend/audit/` **existe vacía** | — | Ahí va la nueva app (`audit`, prefijo de tablas `m19_`) |
| No hay `modulo_app` en el código; el permiso guarda el módulo como texto (`m01_permiso.modulo`) | `acceso/models.py` | `bitacora.modulo_app_id` del v2 se materializa como `modulo` (texto) hasta que exista la tabla |
| No hay tablas `evaluacion` ni `calificacion` todavía; hoy hay `m07_intento` (aula) y `m10_intento*` (expediente) | — | El catálogo de acciones de evaluación queda definido ya; el punto de llamada se conecta cuando nazcan las tablas |
| Instalador ya crea `Logs\` y `AVACOM_LMS_DB`; no hay `LOGGING` en `settings.py` | `installer/`, `settings.py` | §2 es nuevo en el backend |

## 3.2 Propuesta: tablas

Se mantiene el dominio **Acceso y RBAC** del v2 y el estilo del backend (ids texto/UUID, instantes en milisegundos del reloj del nodo, tablas `m19_*`). Pasa de 1 a 2 tablas de auditoría (el v2 sube de 28 a 29; la cifra exacta la confirma el CTO, ver §6).

### `bitacora` (→ `m19_bitacora`, sustituye a `m19_auditoria`) · sólo inserción

| Columna | Tipo | Nulo | Notas |
|---|---|---|---|
| `id` | UUID (texto 36) | no | PK, generado en el nodo |
| `secuencia` | BIGINT | no | **UNIQUE**, monótona, sin huecos ni reutilización. Es la base de la cadena (019-02) |
| `huella_previa` | CHAR(64) | no | Hex SHA-256 del asiento anterior; génesis = 64 ceros |
| `huella` | CHAR(64) | no | SHA-256 de `huella_previa ‖ contenido canónico del asiento` |
| `ocurrido_en` | BIGINT (ms) | no | Reloj del **nodo**, nunca el de la tableta (Maestro §eventos) |
| `usuario_id` | FK `m01_usuario` RESTRICT | sí | NULL = sistema. Es el v2 (`usuario_id`) |
| `actor_tipo` | VARCHAR(12) | no | `usuario` · `sistema` · `dispositivo` · `instalador` |
| `roles_activos` | JSON | sí | Lista completa de roles con que actuó (obligatoria en denegaciones; BR de unión de roles) |
| `modulo` | VARCHAR(24) | no | `acceso` · `aula` · `dispositivos` · `estudio` · `evaluacion` · `auditoria` · `instalacion`. Sustituye a `modulo_app_id` |
| `accion` | VARCHAR(64) | no | De la **lista cerrada** `catalogos.ACCIONES` (versionada, como `evento.clave`). Formato `<dominio>.<objeto>.<verbo>` |
| `resultado` | VARCHAR(16) | no | `ok` · `denegado` · `fallido` |
| `objeto_tabla` | VARCHAR(64) | sí | Ej. `m07_sesion` |
| `objeto_id` | VARCHAR(64) | sí | Identificador del objeto afectado |
| `valor_anterior` | JSON | sí | Sólo los campos que cambian, **no** la fila entera |
| `valor_nuevo` | JSON | sí | Ídem |
| `motivo` | VARCHAR(250) | sí | Obligatorio para las acciones marcadas `exige_motivo` (calificaciones, escaladas, exportaciones) |
| `origen` | VARCHAR(12) | no | `api` · `ws` · `sistema` · `instalador` · `migracion` · `prueba` |
| `dispositivo_id` | FK `m09_dispositivo` RESTRICT | sí | Aparato desde el que se hizo (019-01) |
| `correlacion_id` | VARCHAR(36) | sí | El `corr` de §2.5; une asiento, evento y log |
| `evento_id` | VARCHAR(64) | sí | Referencia al evento de la cola del que derivó (FUN-195/019-09): no se republica |
| `tramo_id` | FK `bitacora_tramo` RESTRICT | no | Tramo en que quedó |

Índices: `(usuario_id, ocurrido_en)`, `(modulo, ocurrido_en)`, `(resultado, ocurrido_en)`, `(objeto_tabla, objeto_id, ocurrido_en)`, `(accion, ocurrido_en)`, `(dispositivo_id, ocurrido_en)` y `UNIQUE(secuencia)`.

CHECK: `resultado IN (...)`, `origen IN (...)`, `actor_tipo='usuario' → usuario_id IS NOT NULL`, `secuencia >= 1`.

**Contenido canónico para la huella** (debe ser idéntico al recalcular): JSON con claves ordenadas, sin espacios, UTF-8, con `secuencia, ocurrido_en, usuario_id, actor_tipo, roles_activos, modulo, accion, resultado, objeto_tabla, objeto_id, valor_anterior, valor_nuevo, motivo, origen, dispositivo_id, correlacion_id, evento_id`. Enteros sin notación científica; `null` explícito.

### `bitacora_tramo` (nueva)

Un tramo es un segmento contiguo de la cadena. El **tramo activo** además hace de «cabeza» de la cadena (su `hasta_secuencia` y `huella_cierre` se actualizan en la misma transacción que el asiento; así no hace falta una tercera tabla y el cierre del tramo es natural).

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `desde_secuencia` | BIGINT | Primer asiento |
| `hasta_secuencia` | BIGINT | Último asiento (cabeza mientras está `activa`) |
| `huella_cierre` | CHAR(64) | Huella del último asiento; al rotar pasa a ser la `huella_previa` del primero del tramo siguiente |
| `estado` | VARCHAR(12) | `activa` · `verificada` · `con_salto` · `rotada` (019-04) |
| `verificado_en` | BIGINT | Última verificación |
| `salto_en_secuencia` | BIGINT, nulo | Primera secuencia discordante |
| `exportado_en` | BIGINT, nulo | (019-06) |
| `firma` | TEXT, nulo | Firma HMAC-SHA256 del manifiesto (§3.3) |
| `archivo` | VARCHAR(260), nulo | Ruta del archivo de tramo rotado (019-07) |
| `rotado_en` | BIGINT, nulo | |
| `creado_en` | BIGINT | |

Reglas: un único tramo `activa` a la vez (índice único parcial, como INV-011/DEC-023 en Device Manager); `desde ≤ hasta`; tramos contiguos sin solaparse.

### Lo que **no** se agrega

- Ninguna tabla de «lectura de auditoría»: la consulta es lectura de `bitacora` (y cada consulta se asienta, ver §4.2).
- Ninguna tabla nueva para logs: son archivos (§2).
- No se toca `evento`, `evaluacion` ni `calificacion`: sólo se **referencian** desde `objeto_*`/`evento_id`.

## 3.3 Inmutabilidad, cadena y firma

**Inmutabilidad en tres capas** (019-03, INV-027, AC-081):

1. **Aplicación.** El *manager* de `Bitacora` no expone `update/delete/bulk_update/bulk_create`; `save()` de una fila existente y `delete()` lanzan `BitacoraInmutable`. Un intento de la capa de aplicación **deja un asiento nuevo** `auditoria.alteracion_intentada` (resultado `denegado`, con actor, objeto pretendido y la operación).
2. **Base de datos.** Triggers SQLite creados por migración:
   ```sql
   CREATE TRIGGER m19_bitacora_no_update BEFORE UPDATE ON m19_bitacora
     BEGIN SELECT RAISE(ABORT, 'bitacora_inmutable'); END;
   CREATE TRIGGER m19_bitacora_no_delete BEFORE DELETE ON m19_bitacora
     BEGIN SELECT RAISE(ABORT, 'bitacora_inmutable'); END;
   ```
   Un `RAISE(ABORT)` revierte su sentencia y no puede insertar el asiento del intento. Por eso, cuando el intento llega *por la aplicación*, el adaptador captura `bitacora_inmutable` y escribe el asiento `auditoria.alteracion_intentada` en una transacción **aparte**. Un intento por SQL *fuera* de la aplicación queda bloqueado por el trigger, y si alguien **suprime el trigger** (o edita el archivo de BD) se detecta en el siguiente punto:
3. **Detección.** La verificación (§4.3) comprueba además que ambos triggers existan en `sqlite_master`; su ausencia es `auditoria.salto_detectado` con causa `triggers_ausentes`. Es la defensa de última instancia: no se pretende impedir al dueño del disco, se pretende que **no pueda alterar sin que se note**.

**Anexar (atómico).** Dentro de la transacción del caso de uso (SQLite ya abre con `BEGIN IMMEDIATE`, lo que serializa a los escritores): leer cabeza del tramo activo → `secuencia = hasta_secuencia + 1` → calcular `huella` → `INSERT` → actualizar cabeza. Si algo falla, todo el caso de uso revierte.

**Firma de un tramo exportado** (019-06). Manifiesto `{tramo_id, desde, hasta, huella_inicial, huella_cierre, total, exportado_por, exportado_en, version_formato}` firmado con HMAC-SHA256 con una clave derivada de `AVACOM_LMS_SECRET` (mismo mecanismo de claves del instalador: `AVACOM_LMS_CLAVE_*`). La clave no sale del nodo: la firma prueba «lo emitió este nodo y no fue modificado». La verificación por terceros (firma asimétrica) queda como pregunta al CTO (§6).

**Después de restaurar un respaldo.** La cadena continúa desde la cabeza restaurada; se asienta `auditoria.restauracion_registrada` con la cabeza que había antes (recuperada del log de archivo, por eso los logs de `backend-auditoria.log` incluyen `secuencia` y `huella`). El salto hacia atrás entre la copia y el log queda visible, no oculto (INV-002 exige secuencias sin reutilización; este caso se documenta en vez de disimularse).

## 3.4 Migración desde `m19_auditoria`

Una migración de datos, reversible sólo hacia adelante:

1. Crear `m19_bitacora`, `m19_bitacora_tramo` y los triggers.
2. Copiar cada fila de `m19_auditoria` **por orden `(momento, id)`** asignando `secuencia`, `huella_previa` y `huella` (la cadena nace con el historial actual); `origen='migracion'`, `actor_tipo` deducido (`sistema` si el actor es `sistema`/vacío), `modulo` deducido del prefijo de `accion` (`identity.`→`acceso`, `aula.`→`aula`, `dispositivos.`→`dispositivos`), `resultado='ok'`, `valor_anterior` tal como esté.
3. Crear el tramo activo con la cabeza resultante y escribir `auditoria.bitacora_abierta` si la tabla origen estaba vacía; si no, `auditoria.cadena_migrada` con el conteo.
4. Dejar `m19_auditoria` **sin escritura** (un trigger la hace de sólo lectura) durante un ciclo de versión y retirarla después.
5. `expediente.Auditoria` pasa a ser una vista de lectura; `AuditoriaView` se sustituye por §4.2.

## 3.5 Catálogo de acciones auditables (lista cerrada, versionada)

Vive en `audit/dominio/catalogos.py`: constante `ACCIONES = {clave: Accion(modulo, exige_motivo, sensible, evento_origen)}` con un `VERSION_CATALOGO`. Anexar una clave fuera del catálogo falla en pruebas (y en producción se registra `auditoria.accion_desconocida` en vez de perder el hecho).

| Módulo | Acciones (las vigentes ya están en el código y **se conservan**) | Nuevas |
|---|---|---|
| `acceso` | `identity.user.creado`, `…rol.asignado`, `…escalada.concedida/revocada`, `…credencial.restablecida`, `…sesion.revocada` … (las actuales de MOD-001) | `acceso.denegado` (con `roles_activos`, permiso solicitado, objeto pretendido), `acceso.dato_personal.consultado` (menores, BR-131), `acceso.escalada.consumida`, `acceso.escalada.vencida` |
| `aula` (**Classroom Engine, prioridad**) | `aula.sesion.iniciada/archivada/suspendida/reanudada/finalizada/anclada`, `aula.participante.ingreso/admitido/rechazado/expulsado`, `aula.selector.declarado`, `aula.control.<tipo>`, `aula.distribucion.<clase>/cerrada/estudio`, `aula.resultados.mostrados`, `aula.codigo.rotado`, `aula.proyeccion.iniciada/terminada`, `aula.ayuda.*`, `aula.envio.<decisión>` | `aula.aviso.enviado` (a dispositivo o grupo), `aula.presencia.perdida` / `aula.presencia.recuperada` (**sólo la transición**, nunca el latido), `aula.proyeccion.terminada` **con `duracion_seg`** (DEC-034), `aula.nivel.excepcion` (excepción de nivel de control), `aula.denegado` |
| `dispositivos` | `dispositivos.asignado`, `dispositivos.liberado`, y las actuales de bloqueo/alta/baja | `dispositivos.borrado_remoto` (sólo administrador, BR-064), `dispositivos.limpieza_registrada` |
| `estudio` | (pendiente de MOD-008) | `estudio.paquete.descargado/denegado`, `estudio.asignacion.creada`, `estudio.entrega.integrada` |
| `evaluacion` | (pendiente de MOD-010/011) | `evaluacion.iniciada`, `evaluacion.enviada`, `evaluacion.anulada`, `calificacion.modificada` (**valor anterior, nuevo, autor y motivo**; DEC-022, BR-070), `calificacion.reabierta`, `calificacion.correccion_posterior_cierre` (exige escalada del profesor) |
| `auditoria` | `auditoria.registro_creado`, `…cadena_verificada`, `…salto_detectado`, `…bitacora_rotada`, `…tramo_exportado` (los 5 eventos de 019-09) | `auditoria.alteracion_intentada`, `auditoria.consulta_realizada`, `auditoria.exportacion_denegada`, `auditoria.violacion_inv003` (escritura desde módulo no declarado), `auditoria.restauracion_registrada`, `auditoria.bitacora_abierta` |
| `instalacion` | — | `instalacion.organizacion_creada`, `instalacion.licencia_activada`, `instalacion.migracion_aplicada` |

**Sistema de evaluaciones (objetivo secundario 4).** Cada cambio de resultado deja un asiento con el `objeto_tabla` (`evaluacion`/`calificacion`), `objeto_id` y, en los cambios de nota, `valor_anterior={"valor_interno":72}`, `valor_nuevo={"valor_interno":80}`, `motivo` y `usuario_id` (AC-054). INV-019: la calificación apunta a un intento, un evaluador y una regla de puntuación; el asiento copia esos tres identificadores en `valor_nuevo` para que sea defendible sin consultar otras tablas. Distinción con `evento` (v2): el `evento` de categoría `evaluacion` cuenta *lo que hizo el alumno en clase*; la bitácora cuenta *quién cambió un resultado y por qué*.

## 3.6 Manejo del documento de los logs

Los logs deben funcionar en un archivo plano, fácil de leer en windows y en android. 

Cada registro debería tener campos como timestamp, level, module, event, message, error_code, correlation_id y datos de contexto. Luego el registro muestra el error, wargnings o info de cada ejecución del programa. 

También se debe considerar: 
1. Límite de almacenamiento, muy importante en dispositivos offline. El sistema nunca debería llenar el disco por culpa de los logs.
2. Buffer offline: los logs deben funcionar aunque no exista Internet.
3. Exportación de diagnóstico, idealmente con un botón como Exportar diagnóstico, que genere un ZIP con logs, versión, configuración no sensible y datos técnicos.

------------------------------

# 4 · Backend: lógica y endpoints

## 4.1 Estructura (mismo patrón que Classroom Engine y Device Manager)

```
backend/audit/                      (app Django «audit»; hoy vacía)
  dominio/     asiento.py  huella.py  catalogos.py  tramo.py  errores.py
  aplicacion/  anexar.py  consultar.py  verificar.py  exportar.py  rotar.py  tecnico.py  puertos.py
  infraestructura/  repositorios.py  unidad_trabajo.py  triggers.py  archivo_logs.py  firma.py
  interfaces/  urls.py  views.py  serializers.py
  logging_setup.py   middleware.py  migrations/  tests/
backend/tools/ver_logs.py  romper_cadena.py
```

`dominio/` no importa Django (como el resto). `huella.py` es una función pura (`calcular(huella_previa, asiento) -> str`), la base de las pruebas de cadena.

## 4.2 Endpoints (prefijo `/api/auditoria/`, reemplaza al actual)

Todos exigen sesión. Las respuestas de error usan el formato del backend (`codigo` estable + mensaje). La paginación es por **cursor de secuencia** (`?despues=<secuencia>&limite=100`, máx. 200): estable aunque lleguen asientos nuevos.

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /api/auditoria/asientos/` | `audit.read` (ORGANIZATION) | Lista filtrada y paginada. Filtros: `actor`, `desde`/`hasta` (ms), `modulo`, `accion`, `resultado`, `objeto_tabla`, `objeto_id`, `dispositivo`, `correlacion`, `texto` (sobre `motivo`). **Cada consulta deja un asiento** `auditoria.consulta_realizada` con los filtros usados. |
| `GET /api/auditoria/asientos/{id}/` | `audit.read` | Un asiento completo, con `valor_anterior/nuevo` y su `huella`. |
| `GET /api/auditoria/catalogo/` | `audit.read` | Lista cerrada de acciones y módulos (alimenta los filtros de OPS). |
| `GET /api/auditoria/tramos/` | `audit.read` | Tramos con estado, rango, verificado_en, exportado_en. |
| `POST /api/auditoria/verificar/` | `audit.read` | Dispara `verificar_cadena()` ahora (además del temporizador). Devuelve `{estado, verificados, salto_en}`. |
| `GET /api/auditoria/estado/` | `audit.read` | Resumen: cabeza (`secuencia`, `huella` abreviada), tramo activo, último verificado, `salto_detectado`, tamaño y umbral de rotación. |
| `POST /api/auditoria/exportar/` | `audit.export` **y** autorización de salida vigente (ESC-03: 30 min o una operación) | Cuerpo: `{tramo_id | desde, hasta, motivo_codigo}`. Genera un archivo firmado y cierra la escalada por consumo. Sin autorización: `403 autorizacion_requerida`, **no** se genera archivo y se asienta `auditoria.exportacion_denegada` (VER-04, TST-072). |
| `GET /api/auditoria/exportaciones/{id}/descargar/` | `audit.export` | Descarga del archivo de esa exportación. |
| `GET /api/auditoria/tecnico/accesos/` | `audit.read` (Administrador) | Consulta «accesos del técnico» (019-10): asientos cuyo `actor` tiene rol técnico, más sus **denegaciones** (VER-01). |
| `POST /api/logs/clientes/` | sesión o dispositivo admitido | Recibe renglones `WARNING+` de OPS/Student (§2.4). Los escribe en `backend-clientes.log`; **no** toca la bitácora. Tope de tamaño y tasa por dispositivo. |
| `GET /api/logs/` | `diagnostics.read` (nuevo; Técnico y Administrador) | Últimas líneas de los logs por `canal`, `nivel`, `app`, `desde`, `corr`. Sólo lectura, sin datos personales (§2.6). |

**No existe** ningún `PUT/PATCH/DELETE` sobre asientos, tramos ni logs. `OPTIONS` y un `405` explícito lo dejan claro, y una prueba recorre todas las rutas de `audit` comprobando que ninguna acepta esos verbos (AC-081: intentar editar → denegado → asiento nuevo).

**Estados de error útiles:** `403 permiso_denegado` (con asiento de denegación), `403 autorizacion_requerida`, `409 cadena_con_salto` (al exportar un tramo con salto: se exige aclarar primero, FUN-200 pide «rango verificado»), `422 accion_desconocida`.

## 4.3 Lógica por caso de uso

**Anexar (puerto `Auditoria` de cada módulo → adaptador `BitacoraAdaptador`).** Se mantiene la firma actual `registrar(actor, accion, tabla, objeto_id, nuevo)` para no tocar las ~30 llamadas, y se **amplía con parámetros opcionales** `anterior=None, motivo=None, resultado="ok", dispositivo_id=None, evento_id=None`. Los módulos se migran poco a poco a pasar `anterior` (hoy ninguno lo pasa salvo Classroom Engine, y allí casi siempre es `None`). `actor`, `origen`, `dispositivo_id`, `correlacion_id` se toman del **contexto de la petición** (middleware: `ContextoAuditoria`), de modo que un módulo no pueda olvidarlos.

**Identificar el aparato en cada llamada (019-01).** Los clientes envían `X-Avacom-Dispositivo: <dispositivo_id>` en cada petición y en el handshake del WebSocket; el middleware lo valida contra `m09_dispositivo` (activo, no bloqueado) y lo coloca en el contexto. Sin cabecera (una prueba, un curl) → `origen='api'` y `dispositivo_id=NULL`, nunca inventado.

**Derivar de la cola (019-09, MOD-015).** Un consumidor con marca de lectura propia lee `m0X_evento_salida` en orden, traduce tipo de evento → acción del catálogo y anexa referenciando `evento_id`, **sin republicar**. Hasta que MOD-015 exista, cada módulo sigue llamando directo (el Maestro admite las dos rutas) y el `evento_id` queda NULL. Deriva de sí mismo únicamente los cinco `auditoria.*`, que sí publica.

**Verificar (`verificar_cadena`, temporizador + endpoint).** Recorre el tramo por secuencia recalculando `huella` con `huella_previa`; detecta (a) huella discordante, (b) hueco o repetición de secuencia, (c) `huella_previa` ≠ huella del anterior, (d) triggers ausentes. Resultado: `tramo.estado = verificada` y evento `auditoria.cadena_verificada.v1`; o `con_salto` con `salto_en_secuencia` y evento `auditoria.salto_detectado.v1` (prioridad alta → notificación al administrador y línea `ERROR` en `backend-auditoria.log`). Verifica en bloques (p. ej. 5.000 asientos) retomando de la última secuencia verificada, para no bloquear el nodo durante una clase (los avisos administrativos no interrumpen una sesión activa). Precondición FUN-198: al menos dos asientos.

**Rotar (FUN-201).** Cuando el tamaño de `m19_bitacora` supera el umbral (por defecto **100 MB**, configurable, p. ej. `AVACOM_LMS_AUDITORIA_UMBRAL_MB`) el temporizador: verifica el tramo activo → lo marca `rotada`, escribe su archivo (`Logs\auditoria\tramo-<desde>-<hasta>.jsonl` + manifiesto firmado) → abre un tramo nuevo cuyo primer asiento toma `huella_previa = huella_cierre`. **Las filas no se borran de la tabla** (INV-027): la rotación sólo las «congela» y las archiva; la purga a 5 años y la anonimización (CAP-117, BR-098) son V1 y cuando lleguen operarán sobre archivos rotados, nunca editando asientos. Emite `auditoria.bitacora_rotada.v1`.

**Exportar (FUN-200, BR-105, ESC-03).** Precondiciones: permiso `audit.export`, autorización de salida **vigente por operación**, rango existente y tramo `verificada`. El archivo contiene los asientos del rango, el manifiesto y la firma; se asienta `auditoria.tramo_exportado` con alcance, rango, autor y motivo (lista, no texto libre; ver nodo táctil en §5.1). Se cierra la escalada por consumo. Mensaje al usuario: MSG-054.

**Técnico sin datos personales (019-10, BR-097, CAP-118, AC-003, VER-01).** El rol `TECHNICIAN` (en `acceso/dominio/plantillas.py`) **no recibe** `audit.read` ni `audit.export` (ninguna escalada alcanza la exportación de auditoría para el técnico, ESC del Maestro). Un intento del técnico de abrir una respuesta de alumno responde `403`, sin opción de escalada, y deja un asiento `acceso.denegado` con `permiso_solicitado` y `objeto` pretendido. Sus vistas (`/api/logs/`, estado del equipo) **sólo** exponen identificadores y cifras. Para *demostrar* que no accedió a datos personales: la consulta `tecnico/accesos/` lista sus acciones y denegaciones; la ausencia de `acceso.dato_personal.consultado` a nombre del técnico, con la cadena `verificada`, es la prueba.

## 4.4 Seguridad de la propia consulta

- Filtros **siempre** dentro del alcance del permiso: `audit.read` con alcance ORGANIZATION ve toda la organización; sin él, `403` y asiento.
- La respuesta no incluye `huella` completa salvo en el detalle de un asiento (evita ruido y fuga de estructura; el detalle la muestra para la verificación).
- Los `valor_anterior/valor_nuevo` de asientos que tocan datos personales de menores se devuelven **enmascarados** salvo que la escalada vigente lo autorice (BR-131).

## 4.5 Pruebas obligatorias (happy / sad / bad)

| Prueba | Ruta | Comprueba |
|---|---|---|
| TST-071 · 5 acciones sensibles | happy | 5 asientos con actor, fecha, valor anterior y motivo |
| AC-054 · calificación 72→80 | happy | `valor_anterior=72`, `valor_nuevo=80`, autor, motivo |
| AC-081 · editar/borrar un asiento | sad | Denegado, asiento intacto, **asiento nuevo** del intento (ORM, QuerySet, `bulk_*`; SQL directo abortado por trigger) |
| TST-072 · exportar sin autorización | sad | `403 autorizacion_requerida`, sin archivo, intento registrado |
| AC-003/VER-01 · técnico abre evidencia | sad | `403`, cero bytes, asiento de denegación con permiso y objeto |
| Cadena íntegra | happy | `verificada`; estado y evento emitidos |
| Romper la cadena (`tools/romper_cadena.py`) | bad | `con_salto` con la secuencia correcta; `auditoria.salto_detectado`; triggers ausentes también se detectan |
| Falla la escritura de la bitácora | bad | Rollback del caso de uso; traza en `backend-errores.log`; cero asientos parciales |
| Concurrencia (varios hilos anexando) | bad | Secuencias únicas y sin huecos; huellas encadenadas |
| Rotación por tamaño | happy | Tramo nuevo enlazado por `huella_cierre`; filas intactas |
| Restauración de respaldo | bad | Cadena continúa; asiento de restauración; aviso |
| Privacidad de logs | sad | Claves prohibidas no aparecen en ningún archivo |
| Ruta sin verbo de escritura | sad | Ninguna ruta de `audit` acepta `PUT/PATCH/DELETE` |

NFR-036 (cero alteraciones sin detectar, 60 meses) y NFR-039 (técnico, 100 % de acciones auditadas) son los criterios de aceptación del conjunto.

------------------------------

# 5 · Frontend

Regla común: el nodo principal de OPS es **táctil y sin teclado** — ninguna pantalla de este módulo exige escribir; los filtros son selectores, chips y fechas de calendario, y los motivos se eligen de una lista. Las tarjetas siguen la composición de OPS (vidrio, tercio central) y se verifican con el overlay de tercios antes de darlas por buenas.

## 5.1 AVACOM LMS OPS (Windows · consola S4 · Administrador y Técnico)

OPS es la única app con pantallas de este módulo. Ruta de la pantalla: **`/logs-bitacora`** (la que ya prevé el mapa de navegación del prompt del LMS: «Pestañas para comportamiento y errores»), con menú solo para Administrador y Técnico, y contenido distinto por rol.

**PAN-240 · «Bitácora» (Administrador)** — solo lectura.

| Pestaña | Contenido | Datos |
|---|---|---|
| **Comportamiento** (bitácora) | Tabla paginada por cursor: hora, actor, acción (etiqueta en español desde `catalogo/`), objeto, resultado (chip verde/ámbar/rojo), dispositivo. Filtros: rango de fechas, actor (selector de personas), módulo, resultado, acción. Al tocar una fila se abre el **detalle** con valor anterior → nuevo (diferencia resaltada), motivo, origen, `correlacion`, huella abreviada y «ver operación completa» (filtra por `correlacion`). | `GET asientos/` |
| **Integridad** | Semáforo grande: **«Cadena verificada»** (verde, con fecha) o **«Salto detectado en la secuencia N»** (rojo, con causa). Lista de tramos (activa, verificada, con salto, rotada), botón «Verificar ahora», barra de tamaño frente al umbral de rotación. | `estado/`, `tramos/`, `verificar/` |
| **Exportaciones** | Exportador con **alcance declarado** (tramo o rango), selector de motivo y paso explícito «autorizar esta salida». Sin autorización vigente muestra MSG de autorización requerida. Éxito: MSG-054 («Queda registrado que exportaste {alcance}»). | `exportar/` |
| **Accesos del técnico** | Lista de acciones y **denegaciones** del rol técnico y el indicador «sin acceso a datos personales en el periodo». | `tecnico/accesos/` |
| **Errores** | Últimas líneas de los logs (`backend`, `ops`, `student`) por canal y nivel; chip de `ruta` happy/sad/bad. No muestra datos personales. | `GET /api/logs/` |

**PAN-241 · Escalada temporal.** Pantalla conectada desde «Bitácora»: permiso concedido, **motivo**, caducidad, quién lo autorizó. Es lo que habilita leer/exportar cuando el rol no lo tiene (MSG-052 «Tienes acceso a {alcance} hasta el {fecha}. Se registra todo lo que hagas» y MSG-053 al vencer). Reutiliza `m01_usuario_permiso`/`autorizacion_temporal` ya existentes en Acceso.

**PAN-242 · «Estado del equipo» (Técnico).** Servicios, espacio, cola pendiente, último punto de recuperación y **pestaña de errores** (la misma de arriba, sin bitácora): el técnico diagnostica escritura, red y dispositivo **sin ver datos de alumnos**. No ve «Comportamiento» ni «Exportaciones».

**Comportamiento de UI:**
- Nada de auditoría interrumpe una clase activa: los avisos de salto o de umbral son **alertas administrativas diferidas**, no ventanas emergentes durante una sesión (S4).
- Sin botones de editar ni borrar en ninguna fila, nunca. Los estados vacíos lo dicen con claridad («La bitácora sólo se agrega; nadie puede editarla»).
- Mientras carga, esqueleto; ante un error de red, el mensaje corto con causa y «Reintentar», y la línea al log local de OPS (`comunicacion`).
- Acceso a la pantalla sin `audit.read` → no aparece el menú; si se llega por enlace, `403` con mensaje claro y asiento.

**Lo que OPS sí debe hacer para auditar (no son pantallas):** enviar `X-Avacom-Dispositivo` en cada llamada (`ClienteJson.cs`), escribir sus logs locales (§2.4) y entregarlos al nodo con el latido.

## 5.2 AVACOM Student (Windows y Android · alumno)

**Student no tiene pantalla de bitácora ni de logs**: el alumno nunca consulta auditoría (Maestro: el modo de estudio del alumno no lo toca nadie más, y ninguna escalada le da acceso). Su trabajo es **alimentar** la auditoría y el diagnóstico sin molestar:

| Qué | Cómo |
|---|---|
| **Identificarse en cada llamada** (019-01) | Cabecera `X-Avacom-Dispositivo` en cada petición HTTP y en el handshake de `ActivitySocketClient`/`AulaSocketClient`. Con ella el asiento conoce el aparato y el origen (`ws`/`api`). |
| **Logs locales** (§2.4) | `RegistroLocal` escribe `student-app.log` y `student-errores.log` en `FileSystem.AppDataDirectory/logs` (Android) o `%LOCALAPPDATA%\AVACOM\lms\logs` (Windows): fallos de escritura de la cola de respuestas y del paquete de estudio, caídas del socket con su duración, poco espacio, poca batería, reloj desfasado, excepciones no controladas (hoy sólo `fallos-student.log`). |
| **Entrega al nodo** (mejor esfuerzo) | Con el latido (009-04), sube los renglones `WARNING+` a `POST /api/logs/clientes/`. Sin red, espera: el log local conserva todo. La cola de envío se vacía sola al volver a la red del aula. |
| **Indicador de proyección** (CMP-063, DEC-034) | Cuando la pantalla del alumno se proyecta, la tableta muestra un indicador **discreto y permanente** («Proyectando»). Es la salvaguarda visible del hecho que el nodo asienta (`aula.proyeccion.iniciada/terminada` con autor y duración). Nunca durante un examen. |
| **Errores al alumno** | Mensajes cortos y sin jerga («No pudimos guardar tu respuesta. Sigue; lo reintentaremos»); el detalle técnico va **sólo** al log. Nunca se le muestra un número de secuencia, huella ni nada de auditoría. |
| **Sin datos personales en el log** | Mismas reglas del §2.6: ningún nombre, PIN, ni respuestas. |

Tablet Android: los logs viven en el almacenamiento privado de la app (no expuestos al alumno) y se limpian con el resto del aparato al cerrar la sesión de estudio en un equipo compartido (BR-053, FUN-089/090): el log local **no** puede conservar datos de la persona saliente, por eso no los contiene.

## 5.3 Resumen OPS ↔ Student

| | OPS | Student |
|---|---|---|
| Pantalla de bitácora | Sí (Administrador), con pestañas | **No** |
| Pantalla de errores | Sí (Administrador y Técnico) | **No** |
| Logs en archivo local | Sí | Sí |
| Cabecera de dispositivo en cada llamada | Sí | Sí |
| Entrega de logs al nodo | Sí | Sí |
| Indicador de hechos auditados | — | Sólo «Proyectando» |

------------------------------

# 6 · Orden de construcción y preguntas abiertas

## 6.1 Fases sugeridas (cada una se entrega verde con sus pruebas)

1. **Logging del backend** (§2): `LOGGING`, JSON, carpeta por entorno, `corr` y middleware, `ver_logs.py`, `LogsDePrueba`. Sin tocar el modelo. *Permite trabajar el resto con diagnóstico.*
2. **Bitácora**: app `audit`, `bitacora`/`bitacora_tramo`, huella, anexar, triggers, migración desde `m19_auditoria`, adaptador compatible con los tres puertos actuales. Pruebas 019-01/02/03.
3. **Verificación, rotación y estado** (019-04/07) y los 5 eventos `auditoria.*`.
4. **Consulta y permisos** (019-05): `audit.read`, filtros, cursor; retirar la ruta vieja.
5. **Cobertura de Classroom Engine** (019-08): nuevas acciones (avisos, presencia, duración de proyección, denegaciones), y paso de `anterior`/`motivo` donde falte.
6. **Exportación firmada** (019-06) con la autorización de salida de Acceso.
7. **Técnico** (019-10) y `diagnostics.read`.
8. **Clientes**: `RegistroLocal` en Core, cabecera de dispositivo, entrega con el latido (OPS y Student).
9. **Pantallas de OPS** (§5.1).
10. **Evaluaciones**: conectar `evaluacion.*`/`calificacion.modificada` cuando existan sus tablas.
11. **Derivar de la cola** (019-09) cuando MOD-015 exista.

## 6.2 Preguntas abiertas para el CTO

1. **Tabla adicional.** El v2 tiene 28 tablas; `bitacora_tramo` la sube a 29 (y el v2 no trae `bitacora.modulo`, sino `modulo_app_id`, que aún no existe en el código). ¿Se acepta `modulo` como texto hasta que exista `modulo_app`? *(Propuesta: sí.)*
2. **Firma.** ¿HMAC con la clave del nodo (propuesto) o firma asimétrica para que un tercero verifique sin el nodo?
3. **Umbral de rotación** por defecto (propuesto 100 MB) y cadencia de verificación (propuesta: cada hora fuera de clase y al rotar).
4. **Permiso `diagnostics.read`** no existe en el Maestro; ¿se crea o el técnico lo recibe bajo `identity.device.manage`? *(Propuesta: permiso propio.)*
5. **Logs de clientes en el nodo.** ¿El nodo guarda los renglones que suben OPS/Student (propuesto, sin datos personales) o cada equipo guarda lo suyo?
6. **Presencia.** Se audita sólo la transición; ¿basta para NFR y el caso «demostrar que el alumno estaba conectado»?
7. **Restauración de respaldo** y secuencias: el Maestro pide secuencias sin reutilización (INV-002, de la cola) — ¿se exige lo mismo de la bitácora tras restaurar, lo que obligaría a guardar la cabeza fuera de la base de datos (propuesta: en `backend-auditoria.log`)?

------------------------------

# 7 · Estado de construcción (2026-09-30)

Backend construido en siete commits `Feature:` sobre `main` (app `audit`, tablas `m19_*`, 616 + 71 pruebas en verde). Lo que cambió respecto a lo propuesto arriba se anota en §7.3; las pantallas de OPS y el lado cliente (§5) van en el siguiente paso.

## 7.1 Fases entregadas (contra §6.1)

| Fase | Entregado | Dónde |
|---|---|---|
| 1 · Logging del backend | `LOGGING` con `dictConfig`, un `RotatingFileHandler` por canal (2 MB × 5), formateador JSON propio, filtro de saneamiento (§2.6), carpeta por entorno (§2.2) con caída a `%TEMP%`, `corr` por petición (`X-Avacom-Correlacion`), línea por petición con `ruta` happy/sad/bad, `tools/ver_logs.py`, corredor de pruebas que etiqueta `caso=<id del test>` y borra la carpeta si todo pasa, mixin `LogsDePrueba` | `audit/logging_setup.py`, `contexto.py`, `middleware.py`, `pruebas.py`, `settings.py` |
| 2 · Bitácora | `m19_bitacora` + `m19_bitacora_tramo`, huella SHA-256 sobre el contenido canónico, génesis (64 ceros), anexado atómico con avance de cabeza, inmutabilidad en tres capas (manager/`save`/`delete` con asiento `auditoria.alteracion_intentada`; triggers `m19_bitacora_no_update/_no_delete`; verificación de triggers en `sqlite_master`), catálogo cerrado versionado, migración del historial (172 filas convertidas en el nodo de desarrollo, cadena verificada), `m19_auditoria` como VISTA de lectura y `m19_auditoria_legado` de sólo lectura, adaptador compatible con los cuatro puertos (firma conservada + `motivo`, `resultado`, `dispositivo_id`, `evento_id`) | `audit/dominio/`, `audit/models.py`, `audit/aplicacion/anexar.py`, `audit/servicios.py`, `audit/migrations/0001_initial.py`, `expediente/migrations/0003_auditoria_vista.py` |
| 3 · Verificación, rotación, estado, eventos | Verificación por bloques (5.000) retomando de `verificado_hasta`; causas `huella_discordante`, `secuencia_con_hueco`, `secuencia_repetida`, `huella_previa_no_enlaza`, `cabeza_discordante`, `triggers_ausentes`; rotación por tamaño estimado con archivo `tramo-<desde>-<hasta>.jsonl` + manifiesto HMAC y tramo nuevo enlazado por `huella_cierre`; temporizador (hilo ASGI, cada hora); cola `m19_evento_salida` con `auditoria.cadena_verificada/salto_detectado/bitacora_rotada/tramo_exportado.v1`; `tools/romper_cadena.py` | `audit/aplicacion/verificar.py`, `rotar.py`, `estado.py`, `audit/infraestructura/verificador.py`, `firma.py`, `archivos.py`, `eventos.py` |
| 4 · Consulta y permisos | `GET /api/auditoria/asientos/` con todos los filtros de §4.2, cursor por secuencia (`antes`/`despues`), asiento `auditoria.consulta_realizada`, enmascarado BR-131 (sin escalada vigente de `audit.read`), detalle con huellas completas y asiento `acceso.dato_personal.consultado`; `catalogo/`, `tramos/`, `estado/`, `verificar/`; 405 en todo PUT/PATCH/DELETE; permisos `audit.export` y `diagnostics.read` sembrados (acceso 0008); ruta vieja del expediente retirada | `audit/aplicacion/consultar.py`, `audit/interfaces/`, `acceso/dominio/plantillas.py` |
| 5 · Cobertura de Classroom Engine | `aula.aviso.enviado` (alcance y largo, sin texto), `aula.presencia.perdida/recuperada` (sólo la transición: declarada, socket cerrado, latido vencido, ausencia prolongada), `aula.proyeccion.terminada` con `duracion_seg`, `aula.denegado` para los 403 del aula; contexto `ws` en el WebSocket (persona, aparato por cabecera `X-Avacom-Dispositivo` o `?dispositivo=`, `corr` por conexión) | `classroom_engine/aplicacion/casos_uso*.py`, `interfaces/websockets.py` |
| 6 · Exportación firmada | `POST /api/auditoria/exportar/` (tramo o rango, motivo de lista cerrada), exige `audit.export` **y** escalada vigente de `audit.export` concedida por otra identidad; sin ella 403 `autorizacion_requerida` + `auditoria.exportacion_denegada` sin archivo; rango con salto 409; archivo `exportaciones/exportacion-<id>.jsonl`, asiento `auditoria.tramo_exportado`, consumo de la escalada (`acceso.escalada.consumida`); `exportaciones/` y `…/descargar/` | `audit/aplicacion/exportar.py` |
| 7 · Técnico y logs | `diagnostics.read` para TECHNICIAN (nunca `audit.read`); `GET /api/auditoria/tecnico/accesos/` con `sin_acceso_a_datos_personales`; `GET /api/logs/` (lectura saneada); `POST /api/logs/clientes/` (equipo activo o sesión; topes por entrega y por minuto; nunca la bitácora) | `audit/aplicacion/tecnico.py`, `logs.py`, `audit/infraestructura/archivo_logs.py` |
| 8 · Clientes · 9 · Pantallas | **Pendiente** (siguiente prompt): `RegistroLocal` en Core, cabecera de dispositivo en `ClienteJson`, entrega con el latido, pantallas de OPS | — |
| 10 · Evaluaciones | Catálogo listo (`evaluacion.*`, `calificacion.*` con `exige_motivo`); el punto de llamada espera a MOD-010/011 | `audit/dominio/catalogos.py` |
| 11 · Derivar de la cola | Pendiente de MOD-015; `evento_id` queda NULL salvo en lo migrado (`m19_auditoria:<id>`) | — |

## 7.2 Pruebas de §4.5 cubiertas

TST-071 (`test_tst_071_…`), AC-054 (`test_ac_054_…` y el detalle enmascarado), AC-081 (ORM, QuerySet, `bulk_*`, SQL directo abortado por trigger, verbos HTTP), TST-072 (`test_tst_072_…`), AC-003/VER-01 (técnico denegado con asiento y `tecnico/accesos/`), cadena íntegra, romper la cadena (alterar, borrar, cabeza, triggers ausentes), falla de escritura con rollback y traza, rotación, privacidad de los logs, ninguna ruta con verbo de escritura. **No cubiertas:** concurrencia con varios hilos (la base de pruebas es en memoria; el aislamiento lo da `BEGIN IMMEDIATE` y `UNIQUE(secuencia)`) y restauración de respaldo (queda documentada en §3.3, sin código).

## 7.3 Decisiones tomadas al construir (para confirmar con el CTO)

1. **`usuario_id` es referencia lógica, no FK.** Con Q-34 abierta los módulos declaran actores que no son usuarios (`docente`, `cliente`, un `persona_id`); por eso `actor_tipo` tiene un valor más que §3.2: `declarado` (el asiento no prueba la identidad). `dispositivo_id` sí es FK RESTRICT a `m09_dispositivo`.
2. **`estado` del tramo abierto.** Un único tramo recibe asientos (`abierta = 1`, índice único parcial) y puede estar `activa`, `verificada` (con `verificado_hasta` diciendo hasta dónde) o `con_salto`; al rotar pasa a `rotada`. Un tramo rotado que luego falla la verificación queda `con_salto` con `rotado_en` puesto.
3. **Autorización de salida = escalada de `audit.export`.** El rol por sí solo no exporta; la escalada la concede otra identidad con motivo y caducidad (BR-101) y se consume en la operación (ESC-03). Lo mismo abre el enmascarado de BR-131: una escalada vigente de `audit.read`.
4. **Un 403 cualquiera deja asiento** (`acceso.denegado`, o `aula.denegado` bajo `/api/aula/`) desde el middleware, con `roles_activos = [rol efectivo de la sesión]`: BR-021 fija un rol efectivo por sesión, así que la «lista completa» es ese rol más las escaladas vigentes (visibles en `identidad.escalada.*`).
5. **Tamaño de rotación estimado** (largo de los campos variables + 320 bytes por fila): SQLite no da el tamaño por tabla sin `dbstat`.
6. **`auditoria.registro_creado.v1` no se publica por asiento**: duplicaría cada escritura. Los otros cuatro eventos sí (`m19_evento_salida`).
7. **Cola de salida propia** (`m19_evento_salida`) hasta MOD-015, como hacen `m01_` y `m07_`. No cuenta como tabla del modelo v2.
8. **`aula.nivel.excepcion`** está en el catálogo pero el aula aún no tiene excepciones de nivel de control: sin punto de llamada.
9. **Pruebas con `TransactionTestCase`** (`test_websockets.py`): el vaciado de tablas es un `DELETE` que los triggers abortan; el corredor de pruebas los retira y repone sólo alrededor de ese vaciado. En producción nada toca los triggers.
10. **Migraciones futuras sobre `m19_bitacora`**: el editor de esquema de SQLite reconstruye la tabla en muchos `AlterField` y pierde los triggers; toda migración debe terminar con `RunSQL(triggers.sentencias(triggers.SQL_CREAR))`. La verificación lo detectaría igualmente (`triggers_ausentes`).
