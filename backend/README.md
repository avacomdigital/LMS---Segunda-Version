# Backend AVACOM LMS · Django REST Framework

Integra **AVACOM Biblioteca** (dueña de los cursos) con **AVACOM OPS Master** y
**AVACOM Student** (clientes MAUI). Este backend **no administra cursos**: los
lee en vivo de la biblioteca por loopback y guarda únicamente el **expediente
del estudiante** (inscripción, aperturas del visor, progreso, intentos y notas)
y lo que ocurre en el **aula** (MOD-007: sesiones de clase, participantes, foco,
distribuciones y resumen; tablas `m07_*`, ninguna de curso).

```
Tableta (Student) ─┐
                   │ HTTP LAN :8000
OPS Master ────────┼──────────────►  este backend (Django/DRF, SQLite)
                   ┘                      │ loopback · puerto efímero · X-Avacom-Ficha
                                          ▼
                                AVACOM Biblioteca · 127.0.0.1:{puerto de enlace.json}
```

## Requisitos

- Python 3.12 (el entorno virtual queda en `backend/.venv`, ignorado por git).
- AVACOM Biblioteca encendida en el mismo equipo, con la pestaña «Contenido AVACOM»
  abierta y la licencia cargada. Si no está, el backend sigue funcionando en
  modo degradado (503 con motivo en las rutas de contenido; el expediente sigue
  legible con 200).

## Instalar y arrancar

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```

`0.0.0.0:8000` es lo que esperan los clientes: OPS Master en `http://127.0.0.1:8000`
y las tabletas en `http://<IP del equipo maestro>:8000`.

## Probar

```powershell
.venv\Scripts\python manage.py test
```

La suite no necesita la biblioteca real: `tools/host_biblioteca_pruebas.py`
imita el contrato en loopback y escribe su propia nota de enlace, que el backend
encuentra por `AVACOM_CONTENIDO_ENLACE`. Para usar el LMS completo sin la
biblioteca instalada:

```powershell
.venv\Scripts\python -m tools.host_biblioteca_pruebas %TEMP%\enlace-pruebas.json
set AVACOM_CONTENIDO_ENLACE=%TEMP%\enlace-pruebas.json
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```

El aula (`/api/aula/`) habla con la **API de Contenido v2** de la biblioteca
(`link.json`, `Bearer`), que tiene su propio host de pruebas construido a partir del
manifiesto `example.json` y que recorta, baraja y califica como la API real:

```powershell
.venv\Scripts\python -m tools.host_contenido_v2_pruebas %TEMP%\link-pruebas.json
set AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\link-pruebas.json
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```

## Rutas

| Ruta | Verbo | Qué hace |
|---|---|---|
| `/health/` | GET | Estado del backend y de la biblioteca |
| `/api/biblioteca/estado/` | GET | `estado()` de la biblioteca; nunca falla |
| `/api/biblioteca/cursos/?persona=` | GET | Cursos ofrecidos (con progreso de la persona) |
| `/api/biblioteca/cursos/{curso_ref}/?persona=` | GET | Árbol vigente del curso anotado con el expediente |
| `/api/biblioteca/medio/{ref}/[ruta]` | GET, HEAD | Bytes de un material (capacidad `medio`, con `Range`) |
| `/api/biblioteca/leccion/{ref}/` | GET | Pasos de una lección (capacidad `leccion`) |
| `/api/biblioteca/evaluacion/{ref}/` | GET | Preguntas sin clave (capacidad `evaluacion`) |
| `/api/biblioteca/voz/{ref}/[pregunta]/` | GET | Instrucción hablada (capacidad `voz`) |
| `/api/biblioteca/mostrar/` | POST | Proyecta en la pantalla del aula |
| `/api/biblioteca/catalogo/`, `taxonomia/`, `elementos/{ref}/` | GET | Navegación fina |
| `/api/students/{persona}/courses/` | GET | Cursos de la persona con progreso; 200 aunque la biblioteca esté cerrada |
| `/api/students/{persona}/courses/{curso_ref}/progress/` | GET, POST | Progreso por sección (upsert monotónico) |
| `/api/aperturas/`, `/api/aperturas/{id}/cerrar/` | POST | El visor del contenido: qué abrió cada persona y cuánto tiempo |
| `/api/intentos/start|answer|finish/` | POST | Evaluaciones con corrección delegada a la biblioteca |
| `/api/resultados/`, `/api/resultados/{id}/` | GET | Notas |
| `/api/cursos/{curso_ref}/consolidado/` | GET | Consolidado docente por estudiante |
| `/api/inscripciones/` | GET, POST, DELETE lógico | Inscripción |
| `/api/auditoria/` | GET | Sólo lectura |
| `/api/courses/…` y demás rutas de administración | cualquier verbo | **409** `administracion_no_permitida` |
| `/api/aula/fuente/[?fuente=]` | GET | Estado de la fuente de cursos (¿hay `link.json`? ¿responde `/v2/health`? cursos instalados y huella). Nunca 503 |
| `/api/aula/cursos/[?fuente=biblioteca|ejemplo]` | GET | Cursos agrupados por **asignatura** (`classification.subject`) para el panel de navegación. La fuente `biblioteca` habla la **API de Contenido v2** (`link.json`, `X-Avacom-Token`, sesiones de medios; ver `spec-driven/02-classroom-engine/05-contrato-biblioteca.md`) |
| `/api/aula/cursos/{curso_ref}/evaluar/` | POST | `{version?, objeto_ref, pregunta_ref, respuesta}` o `{items[…]}` → veredicto de `POST /v2/evaluate` (`puntaje` decimal o nulo, `correcta`, `requiere_correccion_manual`) sin ninguna clave; no escribe |
| `/api/aula/cursos/{curso_ref}/[?rol=docente&version=]` | GET | La **vista de aula** del curso: lecciones, objetos (`presentacion`, `lectura`, `laboratorio_web`, `actividad`, `examen`), bloques, medios y preguntas **sin claves**, con `componente` para MAUI. `version` pide una versión archivada |
| `/api/aula/cursos/{curso_ref}/lecciones/{ref}/`, `objetos/{ref}/` | GET | Una lección o un objeto sueltos |
| `/api/aula/cursos/{curso_ref}/medios/{media_ref}/[ruta]` | GET, HEAD | Bytes del medio (`Range`); con la fuente `ejemplo`, marcadores PNG/WAV/PDF/HTML/VTT |
| `/api/aula/pruebas/curso/`, `/api/aula/pruebas/cursos/` | GET | **Endpoint de prueba**: el curso «Ciencias naturales» de `spec-driven/02-classroom-engine/example.json`, leído del disco en cada petición |
| `/api/aula/sesiones/` | GET · POST | Listar sesiones de clase · **iniciar** una por cualquiera de las cuatro vías (`arbol`, `leccion`, `recurso`, `libre`) |
| `/api/aula/sesiones/unirse/` | POST | La tableta entra con el **código de unión** (o se readmite con su `participante_id`) |
| `/api/aula/sesiones/{id}/` · `estado/` | GET | Detalle para el profesor · estado para la tableta (selector, seguimiento, bloqueo, pendientes, avisos; sondeo cada 2 s, que cuenta como latido de la tableta) |
| `/api/aula/sesiones/{id}/selector/`, `controles/`, `distribuciones/…`, `avisos/`, `codigo/rotar/` | POST | Declarar el **selector** (lo que se proyecta), bloquear/seguir, **lanzar** recurso o actividad con `alcance`, `participantes`, `intentos_permitidos` y `tiempo_limite_seg` (+ `confirmar/`, `cerrar/`, `resultados/`; las tabletas bloqueadas quedan en `excluidos_bloqueados`), avisar, rotar el código |
| `/api/aula/sesiones/{id}/participantes/{pid}/presencia/` · `admitir/` · `rechazar/` · `expulsar/` | POST | Presencia técnica declarada por la tableta · decisiones del profesor |
| `/api/aula/sesiones/{id}/suspender/` · `reanudar/` · `cerrar/` | POST | Caída del nodo · reanudar con el mismo código · cerrar y consolidar el **resumen** |
| `/api/acceso/configuracion/` | GET | Qué identificador y qué secreto usa cada perfil (para pintar el login). Sin sesión |
| `/api/acceso/instalacion/` | POST | Primer arranque: organización, políticas y primer administrador. Sólo una vez |
| `/api/dispositivos/` | POST · GET | **MOD-009 · Device Manager** (app `device_manager`, tablas `m09_*`): registro idempotente de la tableta por su huella (`identificador_hw`, `nombre`, `plataforma`, `version_app`) · inventario con estado en vivo (`en_linea`, `bloqueado`, `sesion_abierta`; `?todos=1` incluye las retiradas) |
| `/api/dispositivos/latido/` | POST | La tableta dice que sigue viva (registra si es nueva) y recibe si está bloqueada o retirada |
| `/api/dispositivos/{id}/` · `bloquear/` · `desbloquear/` | GET, PATCH · POST | Ficha y alta/baja (`nombre`, `tipo`, `activo`; dar de baja cierra sus sesiones) · bloqueo reversible: una tableta bloqueada no entra a clase ni recibe lanzamientos |
| `/api/dispositivos/{id}/asignar/` · `liberar/` | POST | **Perfil del equipo** (FUN-092, FUN-093): `asignar` (`{alumno_id}`) lo deja a nombre de una persona (`perfil = asignado`, `asignado_a {id, rotulo}`; 409 `dispositivo_ya_asignado` si ya es de otra) y `liberar` lo devuelve al aula (409 `paquete_sin_integrar` mientras conserve un paquete de estudio activo). Permisos `device.assign` / `device.release` |
| `/api/modo-estudio/…` | GET, POST, PATCH, DELETE | **MOD-008 · Modo Estudio** (app `modo_estudio`, tablas `m08_*`, contrato en [`spec-driven/04-modo-estudio/02-modelo-y-api.md`](../spec-driven/04-modo-estudio/02-modelo-y-api.md)): `estado/` (la pregunta del menú de Student: `disponible` en cualquier tableta utilizable; nunca falla) · `estudiantes/` (los nombres de «¿Quién eres?»: grupos con trabajo asignado y sus alumnos, sin sesión ni permiso) · `sesion/` · `asignaciones/` (pendientes, con sus medios autorizados) · `lecciones/{id}/` (abrir, `progreso/`, `completar/`, `practica/`) · `practicas/{id}/respuestas/`, `terminar/` (práctica autocalificable separada de la evaluación formal) · `paquetes/` (paquete descargable con huella, `Range` y vigencia; sólo se lo lleva el dueño de una tableta asignada) · `sync/`, `sync/status/` (trabajo sin red, idempotente por `emisor_id + secuencia`) · `docente/grupos/`, `docente/asignaciones/…` (asignar, «quién completó», cerrar, decidir lo que llegó fuera de plazo). Al aparato se le identifica con `dispositivo` (su huella) y, sin sesión, al alumno con el `alumno_id` que la tableta declara (identidad declarada, D-15: sin código ni contraseña; debe existir y estar activo) |
| `/api/evaluacion/…` | GET, POST, PATCH | **MOD-010 · Evaluation & Delivery Engine** (app `evaluacion`, tablas `m10_*`, contrato en [`spec-driven/06-evaluation-delivery/backend.md`](../spec-driven/06-evaluation-delivery/backend.md)): el examen vive en AVACOM Biblioteca y aquí sólo queda lo que el alumno hizo con él. Profesor: `asignaciones/` (asignar con nivel de control obligatorio, `iniciar/`, `cerrar/`, `prorrogar/`, `reabrir/`, `plazo/`, `endurecer/`, `nivel/`, `degradar/`, `liberar-resultados/`) · `asignaciones/{id}/panel/` (ordenado por quién necesita al profesor) · `elegibilidad/` · `admisiones/…/decidir/` · `reactivar/` · `resultados/` · `intentos/{id}/` (expediente de sólo lectura) · `revision/` · `reactivar/` · `cerrar/` · `anular/` (una persona con motivo; el sistema jamás) · `respuestas/{ref}/puntuar/` · `publicar/` · `decidir-envio/` · `recalificar/`. Alumno (se identifica con `dispositivo` y, sin sesión, `alumno_id`): `estudiantes/` (el «¿Quién eres?» sin sesión) · `mias/` · `asignaciones/{id}/antesala/` · `asignaciones/{id}/intentos/` (201 abierto · 200 reanudado · 202 espera al profesor) · `intentos/{id}/estado/`, `latido/` (el nodo devuelve el plan de bloqueo), `preguntas/` (sin claves), `medios/`, `respuestas/` (idempotente por pregunta + sesión + secuencia), `incidentes/`, `bloqueo/` (lo que la tableta logró aplicar), `entregar/`, `resultado/` (sólo si el profesor lo liberó). `evaluaciones/` y `reactivos/` responden 409: crearlos es de la biblioteca |
| `/api/auditoria/asientos/` · `asientos/{id}/` | GET | **MOD-019 · Audit** (app `audit`, tablas `m19_*`, prompt en [`spec-driven/05-audit-logs/introduccion.md`](../spec-driven/05-audit-logs/introduccion.md)): la bitácora encadenada, sólo lectura con `audit.read` (Administrador). Filtros `actor`, `actor_tipo`, `desde`/`hasta` (ms), `modulo`, `accion` (admite `aula.control.*`), `resultado`, `objeto_tabla`, `objeto_id`, `dispositivo`, `correlacion`, `texto` (sobre el motivo), `tramo`, `sensible`; cursor por secuencia (`antes=` hacia atrás, `despues=` hacia adelante, `limite` ≤ 200). **Cada consulta deja un asiento** `auditoria.consulta_realizada`. Los asientos sensibles (calificaciones, datos de menores) llegan con `valor_anterior/nuevo` enmascarados salvo que el actor tenga una **escalada vigente** de `audit.read` (BR-131); el detalle trae `huella` y `huella_previa` completas |
| `/api/auditoria/catalogo/` · `tramos/` · `estado/` · `verificar/` | GET · GET · GET · POST | Lista cerrada de acciones y módulos (alimenta los filtros de OPS) · tramos de la cadena (`activa`, `verificada`, `con_salto`, `rotada`) · semáforo: cabeza (`secuencia`, huella abreviada), `salto_detectado`, `triggers_ok`, tamaño frente al umbral de rotación · verificar la cadena ahora (`{estado, verificados, salto_en, causa}`; también la verifica un temporizador) |
| `/api/auditoria/exportar/` · `exportaciones/` · `exportaciones/{id}/descargar/` | POST · GET · GET | Exportar un tramo (`tramo_id`) o un rango (`desde`, `hasta`) con `motivo_codigo` de una lista: exige `audit.export` **y** una autorización de salida vigente (escalada temporal de `audit.export` concedida por otra identidad); sin ella → 403 `autorizacion_requerida`, sin archivo y con asiento `auditoria.exportacion_denegada`; con salto → 409 `cadena_con_salto`. Genera `<logs>\auditoria\exportaciones\exportacion-<id>.jsonl` (manifiesto firmado HMAC + asientos), asienta `auditoria.tramo_exportado` y consume la escalada (ESC-03) |
| `/api/auditoria/tecnico/accesos/` | GET | «Accesos del técnico» (019-10): acciones y denegaciones de quienes tienen rol TECHNICIAN, con `sin_acceso_a_datos_personales` y `cadena_verificada` |
| `/api/logs/` | GET | Últimas líneas de los logs JSON Lines del nodo por `canal`, `nivel`, `app`, `ruta`, `desde`, `corr`, `dispositivo`, `evento`, `archivo`, `ultimos`. Exige `diagnostics.read` (Técnico y Administrador). Sin datos personales |
| `/api/logs/clientes/` | POST | OPS y Student entregan sus renglones `WARNING+` (`{app, version_app, renglones:[{ts, nivel, canal, app, modulo, evento, ruta, mensaje, detalle, traza, corr}]}`) con `X-Avacom-Dispositivo` (equipo activo) o sesión; van a `backend-clientes.log`, nunca a la bitácora. Tope de renglones por entrega y por minuto. Responde 202 `{recibidos, escritos, descartados}` |
| `/api/acceso/sesiones/` | POST · GET | Iniciar sesión (JWT de 4 h, **una sola por persona**, rol efectivo elegible) · listar sesiones |
| `/api/acceso/sesiones/actual/`, `/api/acceso/sesiones/{id}/`, `/api/acceso/usuarios/{id}/sesiones/` | DELETE | Cerrar la propia · revocar ajena · revocar todas las de un usuario |
| `/api/acceso/yo/`, `/api/acceso/yo/credencial/` | GET · PUT | Identidad, rol efectivo, roles disponibles, permisos y menú · cambiar la propia clave |
| `/api/acceso/usuarios/…` | GET, POST, PATCH | Usuarios, `importar/`, `vincular/` (admisión nominal), `roles/` (asignaciones con alcance y vigencia), `escaladas/`, `credencial/restablecer/`, `desbloquear/` |
| `/api/acceso/autorizaciones-temporales/…` | POST, GET, DELETE · `canjear/` | Acceso temporal a examen (tableta autorizada o código de un solo uso) |
| `/api/acceso/roles/`, `permisos/`, `politicas/{perfil}/[?nivel=]`, `grupos/…` | GET, POST, PUT, PATCH | Catálogos y configuración del colegio, políticas por nivel educativo |

La app `classroom_engine/` implementa **MOD-007 · Classroom Engine** (sesión de clase, participantes, selector, controles,
distribuciones —el lanzamiento—, avisos, resumen y cola de salida `aula.*.v1`) con la misma arquitectura hexagonal. La app
`device_manager/` implementa **MOD-009 · Device Manager** (inventario `m09_dispositivo`, sesión de alumno en la tableta
`m09_dim_sesion_alumno` con INV-011, cola `dispositivo.*.v1`); el aula y el login la consultan por `device_manager/servicios.py`,
nunca por su ORM. Está especificado en
[`spec-driven/02-classroom-engine/01-modelo-de-datos.md`](../spec-driven/02-classroom-engine/01-modelo-de-datos.md) (modelo `m07_*`
y contrato de `/api/aula/`) y [`02-sugerencias-frontend.md`](../spec-driven/02-classroom-engine/02-sugerencias-frontend.md) (componente MAUI).
No guarda ningún curso: lo lee en vivo de la biblioteca o del manifiesto de ejemplo y sólo escribe referencias.

La app `modo_estudio/` implementa **MOD-008 · Modo Estudio** con la misma arquitectura hexagonal: el producto cuando no hay profesor delante. Lee la
lección en vivo por los casos de uso del aula (no guarda ningún curso ni ninguna clave de respuesta), deja practicar con retroalimentación inmediata
en una actividad separada de la evaluación formal (nunca toca `m07_intento` ni `m10_intento`), entrega un paquete descargable sólo al dueño de una
tableta asignada (`perfil = asignado`, MOD-009) e integra sin duplicar el trabajo que la tableta hizo sin red. Sirve en cualquier tableta registrada: quien
la tiene en la mano elige quién es (`GET /api/modo-estudio/estudiantes/`), sin código ni contraseña, y el nodo sólo comprueba que exista y esté activo.

La app `audit/` implementa **MOD-019 · Audit** con la misma arquitectura hexagonal. Dos registros que comparten infraestructura y nunca se
mezclan: la **bitácora** (`m19_bitacora`, de sólo inserción: cada asiento lleva `secuencia` monótona y `huella = SHA-256(huella_previa ‖ asiento)`;
triggers de SQLite abortan todo UPDATE/DELETE y el manager del ORM deja un asiento `auditoria.alteracion_intentada` ante cualquier intento;
`m19_bitacora_tramo` lleva la cabeza y los tramos verificados/rotados) y los **logs de diagnóstico** (archivos JSON Lines por canal, §2 del prompt).
Los demás módulos no cambiaron de puerto: `uow.auditoria.registrar(actor, accion, tabla, objeto_id, anterior, nuevo, motivo=…, resultado=…)` llega a
`audit.servicios.anexar`, que toma actor, rol, aparato, origen y `corr` del **contexto de la operación** (`audit.contexto`, fijado por el middleware,
la autenticación JWT, el WebSocket o el programador). `m19_auditoria` sigue existiendo como VISTA de lectura sobre la bitácora (y la tabla vieja queda
como `m19_auditoria_legado`, de sólo lectura, durante un ciclo de versión). Todo 403 del backend deja `acceso.denegado` con los roles activos y el
permiso pedido; las acciones viven en un catálogo cerrado (`audit/dominio/catalogos.py`): una clave desconocida falla en pruebas y en producción se
asienta como `auditoria.accion_desconocida`.

Logs: la carpeta se decide una sola vez al arrancar (`AVACOM_LMS_DIR_LOGS` → instalado `%ProgramData%\AVACOM\OPS Master\Logs` → desarrollo
`backend\logs` → pruebas: carpeta temporal por corrida que se borra si todo pasa). Cada petición recibe un `corr` (`X-Avacom-Correlacion`, se
respeta si el cliente lo manda) que une petición, asiento, evento y error; `X-Avacom-Dispositivo` identifica al aparato en cada llamada (se valida
contra `m09_dispositivo`; nunca se inventa). Herramientas: `python tools/ver_logs.py --ultimos 50 --nivel ERROR --canal escritura` (también
`--caso`, `--ruta`, `--corr`, `--app`) y `python tools/romper_cadena.py --secuencia 7` (sólo pruebas: rompe la cadena para comprobar que se
detecta). En las pruebas, el mixin `audit.pruebas.LogsDePrueba` ofrece `lineas_log(...)`, `assertLogged(...)` y `assertNoLogged(...)` sobre las
líneas del caso en curso.

Para probar el consumo del curso sin la biblioteca:

```powershell
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
# en otra consola
curl http://127.0.0.1:8000/api/aula/pruebas/curso/?rol=docente
curl -o lamina.png http://127.0.0.1:8000/api/aula/cursos/avacom.co.lower-secondary.6.science.states-of-matter/medios/img-particles/
```

El módulo de acceso implementa **MOD-001 · Identity & Access** del Documento Maestro de AVACOM LMS. Está
especificado en [`spec-driven/01-acceso/`](../spec-driven/01-acceso/01-modelado-datos.md) (modelo de datos),
[`02-Endpoints.md`](../spec-driven/01-acceso/02-Endpoints.md) (contrato), [`03-casos-de-uso-backend.md`](../spec-driven/01-acceso/03-casos-de-uso-backend.md)
(guía de lectura) y [`04-Lineamientos-Al-Documento-Maestro.md`](../spec-driven/01-acceso/04-Lineamientos-Al-Documento-Maestro.md)
(cruce con el Maestro). Vive en `acceso/` con arquitectura hexagonal: `dominio/` y `aplicacion/` no importan Django;
`infraestructura/` e `interfaces/` son los adaptadores (ORM, Argon2id, AES-GCM, JWT, DRF).

## Instalar el nodo (módulo de acceso)

Tras `migrate`, el catálogo de permisos y los roles `STUDENT`, `TEACHER` y `ADMIN` ya están sembrados.
La organización y el primer administrador se crean una sola vez, desde la API (`POST /api/acceso/instalacion/`)
o con el comando:

```powershell
.venv\Scripts\python manage.py acceso_instalar --codigo IE-SANJOSE --nombre "IE San José" --pais CO --admin-dni 1042888795 --admin-nombres Ana --admin-apellidos Pérez
```

Si no se pasa `--admin-password`, se genera una y se muestra **una sola vez**.

Para cargar el padrón sin red desde un archivo delimitado (FUN-003 del Documento Maestro), con las columnas
`rol, alias, nombres, apellidos, tipo_identificador, identificador, grupo, secreto`:

```powershell
.venv\Scripts\python manage.py acceso_importar padron.csv --actor-dni 1042888795
```

Los identificadores que ya existen se fusionan (no se duplica la persona) y las filas con error se listan con su
motivo sin abortar el lote.

Códigos de degradación: **503** biblioteca ausente (con `sugerencia`), **501**
capacidad no publicada (con `capacidades`), **502** la biblioteca contestó con
error, **404/403** referencia inexistente o desactivada por la escuela.

## Variables de entorno

| Variable | Para qué |
|---|---|
| `AVACOM_CONTENIDO_ENLACE` | Ruta forzada de la nota de enlace del contrato 1 (`enlace.json`; pruebas / host de pruebas) |
| `AVACOM_CONTENIDO_ENLACE_V2` | Ruta forzada de `link.json`, la nota de la API de Contenido v2 (`apiPort`, `mediaPort`, `token`); por defecto `%ProgramData%\AVACOM\content\link.json` |
| `AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG` | Tiempo de espera hacia la biblioteca (3 s por defecto) |
| `AVACOM_LMS_DB` | Ruta del SQLite (por defecto `backend/db.sqlite3`) |
| `AVACOM_LMS_DEBUG` | `1` por defecto en el prototipo |
| `AVACOM_LMS_CLAVE_DATOS` | Clave AES-256-GCM para los datos personales (32 bytes en base64) |
| `AVACOM_LMS_CLAVE_INDICE` | Clave HMAC-SHA-256 del índice ciego (búsqueda de DNI/código/correo) |
| `AVACOM_LMS_CLAVE_TOKENS` | Clave HS256 de los JWT |
| `AVACOM_LMS_EXIGIR_SESION` | `0` por defecto. Con `1`, expediente y biblioteca exigen sesión (Q-34) |
| `AVACOM_AULA_FUENTE_CURSOS` | Fuente de cursos por defecto de `/api/aula/`: `biblioteca` (por defecto) o `ejemplo` |
| `AVACOM_AULA_CURSO_EJEMPLO` | Ruta del manifiesto de ejemplo (por defecto `spec-driven/02-classroom-engine/example.json`) |
| `AVACOM_ESTUDIO_VIGENCIA_DIAS` | Modo Estudio: cuánto dura en el aparato un paquete de una asignación sin fecha límite (14 días por defecto; con fecha, hasta la fecha más la gracia) |
| `AVACOM_ESTUDIO_GRACIA_MIN` | Modo Estudio: minutos de gracia por defecto de una asignación nueva (15, DEC-019) |
| `AVACOM_ESTUDIO_MEDIO_MAX_MB` | Modo Estudio: tope de tamaño de UN medio al preparar un paquete (512 MB); uno mayor queda fuera del paquete (`medio_demasiado_grande`) |
| `AVACOM_EVAL_LATIDO_VENCIDO_MS` | Evaluación: silencio de la tableta tras el cual el intento se pausa y su reloj se congela en el último latido (30000, INV-010) |
| `AVACOM_EVAL_LATIDO_SEG` | Evaluación: cadencia de latido que se recomienda a la tableta (5 s, punto de recuperación) |
| `AVACOM_EVAL_GRACIA_MIN` | Evaluación: minutos de gracia por defecto de una asignación nueva (15, DEC-019) |
| `AVACOM_EVAL_PROGRAMADOR` | Evaluación: `0` desactiva el programador del nodo (pausa por falta de latido, entrega por tiempo o plazo, activación y archivado, recalificación) |
| `AVACOM_EVAL_DETECTAR_REINICIO` | Evaluación: `0` no pasa los intentos abiertos a `restaurando` al arrancar el nodo (BR-051) |
| `AVACOM_EVAL_ARCHIVADO_H` | Evaluación: horas que una asignación cerrada espera antes de pasar a `archivada` (24) |
| `AVACOM_EVAL_MAX_RESPUESTAS` | Evaluación: tope de respuestas por envío (200) |
| `AVACOM_EVAL_DESFASE_RELOJ_MS` | Evaluación: desfase del reloj de la tableta a partir del cual se registra `reloj_desfasado` (5000, INV-017) |
| `AVACOM_EVAL_ARMADO_INTENTOS` | Evaluación: combinaciones que prueba el armado `random_balanced` (200) |
| `AVACOM_LMS_DIR_LOGS` | Audit: carpeta de los logs JSON Lines (manda sobre la elección por entorno). Si no se puede escribir, se cae a `%TEMP%\avacom-lms\logs` y `settings.AVACOM_LMS_AVISO_LOGS` lo dice |
| `AVACOM_LMS_ENTORNO` | `instalado` · `desarrollo` · `pruebas`. Sin ella: `manage.py test` es pruebas, `AVACOM_LMS_DEBUG=0` es instalado, lo demás desarrollo |
| `AVACOM_LMS_NIVEL_LOG` | Nivel mínimo de `backend-app.log` (`INFO` por defecto; en pruebas siempre `DEBUG`) |
| `AVACOM_LMS_CONSERVAR_LOGS` | `1` conserva la carpeta de logs de una corrida de pruebas que pasó (por defecto se borra; si falló se imprime su ruta) |
| `AVACOM_LMS_AUDITORIA_UMBRAL_MB` | Audit: umbral de rotación de la bitácora por tamaño (100 MB). Las filas no se borran: se archivan en `<logs>\auditoria\tramo-<desde>-<hasta>.jsonl` con manifiesto firmado |
| `AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S` | Audit: cadencia del verificador de la cadena en el proceso ASGI (3600 s; `0` lo desactiva) |
| `AVACOM_LMS_AUDITORIA_ESTRICTA` | Audit: `1` hace fallar una acción fuera del catálogo (por defecto sólo en pruebas); con `0` se asienta `auditoria.accion_desconocida` |
| `AVACOM_LMS_CLAVE_AUDITORIA` | Audit: clave HMAC (base64) de la firma de tramos y exportaciones; si falta se deriva de `SECRET_KEY` |
| `AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES` · `_MAX_POR_MINUTO` | Audit: tope de renglones por entrega (200) y por minuto (1000) que `POST /api/logs/clientes/` acepta de cada equipo |

Si faltan las tres claves, el prototipo las deriva de `SECRET_KEY` con HKDF y `/health/` responde
`"acceso": {"claves_derivadas": true}`. En una instalación distribuida deben venir en `backend.env`.
