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

Si faltan las tres claves, el prototipo las deriva de `SECRET_KEY` con HKDF y `/health/` responde
`"acceso": {"claves_derivadas": true}`. En una instalación distribuida deben venir en `backend.env`.
