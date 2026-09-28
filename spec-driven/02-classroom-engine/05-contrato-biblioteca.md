# 05 · Classroom Engine · Contrato con la API de Contenido v2 de AVACOM Biblioteca

| Campo | Valor |
|---|---|
| Módulo | MOD-007 · Classroom Engine · fuente de cursos `biblioteca` |
| Estado | **Implementado y verificado contra la API real** (app «AVACOM Contenido», contrato 2, instalada en este equipo el 2026-09-21 con cuatro cursos). Se construyó primero a partir del documento «Mapeo de campos · API de Contenido v2» del equipo de Biblioteca y después se ajustó al contrato que publica la propia API en `GET /v2/openapi.json` (copia en [`openapi.v2.json`](openapi.v2.json)) |
| Sustituye a | La propuesta de [06 · Contrato exigido a la biblioteca](../06-contrato-biblioteca.md) en lo que toca al aula (`/v1/cursos`, `/v1/curso/{ref}`, `evaluacion`, `comprobar`). El contrato 1 sigue vigente para `/api/biblioteca/*` y el flujo de intentos del expediente |
| Cierra | Q-44 (cómo publica la biblioteca el curso 1.0), Q-45 (cómo se piden los medios), parte de Q-48 (quién califica las preguntas del manifiesto) de [01 · Modelo de datos](01-modelo-de-datos.md) §12 |
| Documentos hermanos | [01 · Modelo de datos y API](01-modelo-de-datos.md) · [03 · Journey](03-journey-clase-de-hoy.md) · [04 · Frontend](04-frontend-classroom-engine.md) · [00 · Línea base del contrato 1](../00-linea-base-conexion-biblioteca.md) |
| Continúa en | [06 · Versión 2 de Contenido](06-Versión-2-Contenido.md) (2026-09-28): el esquema de curso 1.0 (`course.schema.json`) y el validador de referencia (`validate_course.py`) que la biblioteca publica junto al `openapi.v2.json`, lo que cambió en el aula y lo que se encontró en vivo con AVACOM Contenido 2.1.7 |

---

## 0 · Resumen

1. **La API v2 entrega el curso que el LMS ya sabía leer, recortado y en dos pasos.** `GET /v2/courses/{courseId}` devuelve el **esquema** (metadatos, lecciones con resúmenes de objeto, lista de medios) y `GET …/lessons/{lessonId}` cada lección **completa** (láminas, páginas, preguntas **sin ninguna clave**, sin `teacherNotes` para el alumno). La fuente `biblioteca` los junta y el normalizador de [01](01-modelo-de-datos.md) §2 no cambió: la vista de aula es la misma con `fuente=biblioteca` que con `fuente=ejemplo`.
2. **Un cliente nuevo y único**, `backend/biblioteca/contenido_v2.py`: `link.json` releído en cada petición, cabecera `X-Avacom-Token`, un 401 reintenta **una** vez tras releer, la ausencia de `link.json` es «sin contenido» (503 con sugerencia), y `POST /v2/evaluate` viaja **siempre con `version`**.
3. **Los medios se sirven por sesiones de medios**: `POST /v2/media-sessions` devuelve URL-capacidad efímeras en un segundo servidor loopback (`mediaPort`); el aula abre una sesión de un minuto por cada petición de bytes, reenvía el flujo con `Range` y no guarda nada.
4. **El aula califica sin guardar**: `POST /api/aula/cursos/{curso_ref}/evaluar/` valida la forma de `response` contra la pregunta tal como la vio el alumno (ids, nunca posiciones), reenvía con la versión y devuelve el veredicto traducido (`puntaje` decimal o nulo, `correcta` booleana o nula, `requiere_correccion_manual`). Persistir el intento sigue siendo de MOD-010 (Q-48, Q-49).
5. **Nada se guarda del curso** (artículo 14): ni catálogo, ni títulos como clave, ni posiciones de opción, ni `token`, ni sesiones de medios. Lo único que el expediente conserva del contenido son `courseId` + `version` y los `lessonId`/`objectId`/`questionId`/`optionId`, tal como pide el mapeo §2.
6. **OPS elige la fuente y Student no.** OPS pide `biblioteca` por defecto y, si no está encendida, ofrece «Usar el curso de ejemplo» con un toque; la tableta no manda `fuente`: sigue la clase del profesor y el backend resuelve.

---

## 1 · Transporte

```
Tableta / OPS ──HTTP LAN :8000──► backend del LMS ──127.0.0.1:{apiPort}   X-Avacom-Token──► API de Contenido v2
                                   (contenido_v2.py) ──127.0.0.1:{mediaPort} /s/{capacidad}/…──► servidor de medios
```

`link.json` real (`C:\ProgramData\AVACOM\content\link.json`):

```json
{"contract": 2, "apiPort": 49805, "mediaPort": 49804, "token": "…", "pid": 15788, "startedAt": "2026-09-21T17:00:31Z"}
```

| Regla del mapeo | Cómo se cumple | Dónde |
|---|---|---|
| `link.json` se relee en cada petición | `leer_enlace()` abre el archivo en cada `_pedir()`; nada se guarda en memoria | `contenido_v2.leer_enlace` |
| `apiPort`, `mediaPort` y `token` cambian en cada arranque: **no guardar** | No hay variable de módulo con el puerto ni el token; sólo la ruta del archivo | — |
| El token viaja en la cabecera `X-Avacom-Token` (no `Authorization`) | `CABECERA_TOKEN` | `_pedir()` |
| Un `401` reintenta **una** vez tras releer `link.json` | `_pedir(reintentar=True)` → al primer 401 vuelve a leer y repite con `reintentar=False`; el segundo 401 sube como `BibliotecaError(401, codigo="unauthorized")` → **502 `fuente_error`** | `contenido_v2._pedir` |
| La ausencia de `link.json` produce «sin contenido», no un error | `BibliotecaNoDisponible` → `FuenteNoDisponible` → **503** `{disponible: false, detail: "…sin contenido.", sugerencia}` | `fuente_biblioteca._traducir` |
| `contract` mayor que el que entiende el LMS | `BibliotecaNoDisponible` con «actualiza AVACOM OPS» | `leer_enlace` |
| Sólo loopback, sin proxy, tiempo de espera corto | `ProxyHandler({})`, `127.0.0.1`, `AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG` (3 s); una URL de medio fuera del loopback se rechaza | como en el contrato 1 |
| Ruta de `link.json` | `%ProgramData%\AVACOM\content\link.json` (carpeta `content`, no `contenido`); se fuerza con `AVACOM_CONTENIDO_ENLACE_V2` para el host de pruebas | `settings.py` |

Las URL del servidor de medios no llevan token: la capacidad está en la propia URL (`/s/{capacidad}/{mediaId}`) y caduca con la sesión (`ttlSec`, hasta ocho horas; el aula pide un minuto).

---

## 2 · Rutas que consume el aula

| Ruta de la API v2 | Quién la llama | Para qué | Caso de uso del aula |
|---|---|---|---|
| `GET /v2/health` | `contenido_v2.estado()` | `{contract, schema, index: ready\|rebuilding, installedCourses: n}`. ¿Hay contenido? ¿Se está reconstruyendo el índice? | `EstadoFuente` → `GET /api/aula/fuente/` |
| `GET /v2/courses?page&pageSize` | `FuenteBiblioteca.cursos()` | Fichas (`CourseSummary`) de los cursos instalados y permitidos por la política, paginadas; la huella `v2-…` sale de `courseId@version` | `ConsultarCursos` → `GET /api/aula/cursos/` |
| `GET /v2/courses/{courseId}?mode=class&profile=teacher\|student` | `esquema_curso()` | El **esquema**: metadatos, lecciones con resúmenes de objeto (`pageCount`, `questionCount`, `mediaId`) y medios (`hasCaptions`, `hasTranscript`, `entry`, `simulation`). Para la lista basta con esto | `ConsultarCursos` (una por curso) y primer paso de `curso()` |
| `GET /v2/courses/{courseId}/lessons/{lessonId}?mode=class&profile=&seed=` | `leccion()` | La lección **completa**, filtrada por modo y recortada por perfil. `seed` fija el barajado de las opciones | `ConsultarCurso`, `ConsultarLeccion`, `ConsultarObjeto`, `IniciarSesion`, `DeclararSelector`, `Distribuir`, `EvaluarRespuesta` (una por lección con objetos) |
| `GET /v2/courses/{courseId}/objects/{objectId}?profile=&seed=` | `objeto()` | Un objeto completo. Disponible en el cliente; el aula hoy arma el curso por lecciones | — |
| `POST /v2/media-sessions` `{courseId, mediaIds, ttlSec: 60}` → `GET <url>` en `mediaPort` | `abrir_medio()` | Bytes del medio con `Range` y `HEAD`, en paso a través. Subtítulos (`extras.captions` → `…/@captions`), transcripción (`…/@transcript`) y archivos de una simulación (`<baseUrl><mediaId>/<ruta>`) | `AbrirMedio` → `GET /api/aula/cursos/{ref}/medios/{media_ref}/[subtitulos\|transcripcion\|ruta]` |
| `POST /v2/evaluate` | `evaluar()` | Un veredicto. **Siempre con `version`** (acepta versiones archivadas) | `EvaluarRespuesta` → `POST /api/aula/cursos/{ref}/evaluar/` |
| `POST /v2/evaluate/batch` → `{results[]}` | `evaluar_lote()` | Hasta 200 respuestas en `items`; más de 200 el aula responde 400 | ídem con `items` |
| `GET /v2/courses/{courseId}/questions/{questionId}/grading-guide?version=` | `guia_calificacion()` | Rúbrica y respuesta modelo de una abierta, **sólo para calificar a mano**. Está en el cliente y **no se expone por `/api/aula/`**: es de MOD-011 | — |

Lo que el aula **no** pide: `/v2/tree`, `/v2/search`, `/v2/policies` (navegación y política, útiles para MOD-004), `/v2/courses/{id}/exams/{oid}/pool` y `…/questions` (armado de exámenes, MOD-010), nada que cree o modifique contenido (no existe en el contrato) y nada del catálogo plano del contrato 1, que sigue siendo del modo libre «Asignaturas».

### 2.1 · Efecto de `mode=class`

Comprobado en vivo: la API **filtra** por modo. En el curso «Estados de la materia» el examen declara `modes: ["exam"]`, así que con `mode=class` la lección de evaluación llega con `objects: []` y la fuente no la baja. El aula ya trataba el examen como `fuera_de_alcance` (MOD-010), de modo que no cambia nada de lo que se proyecta; sólo desaparece la tarjeta atenuada «Examen» en P2.

### 2.2 · `version` en el curso

La API **no sirve el esquema de una versión archivada**: `GET /v2/courses/{id}` no admite `version` y siempre entrega la instalada. `version` sólo se acepta en `evaluate` y `grading-guide` (`version_not_available` si no está). Por eso `?version=` en `/api/aula/cursos/{ref}/…` exige que coincida con la instalada (otra es 404 `curso_no_encontrado` con `codigo_biblioteca: version_not_available`), y al evaluar un intento de una versión archivada el aula no puede validar la forma contra esa estructura: la reenvía tal cual y la valida la biblioteca (422 `invalid_response` → 400).

---

## 3 · Identificadores · qué guarda el expediente

La tabla del mapeo §2, con su estado en el LMS:

| Identificador | Estable | ¿Se guarda? | Dónde, hoy |
|---|---|---|---|
| `courseId` | sí | **sí** | `m07_sesion.curso_ref`, `m07_selector.curso_ref`, `m07_distribucion.curso_ref`; `m10_intento.curso_ref` |
| `version` | — | **sí, junto al `courseId`** | `m07_sesion.curso_version`, `m07_selector.curso_version` (la de la vista con la que se inició o proyectó; en vivo, `2.0.0`). El veredicto de `/evaluar/` devuelve `version` para que MOD-010 la escriba en el intento |
| `lessonId` | sí | sí | `leccion_ref` en sesión, selector y distribución |
| `objectId` | sí | sí | `objeto_ref` en selector y distribución; `objectId` en cada evaluación |
| `questionId` | sí | sí | `unidad_ref` del selector cuando se proyecta una pregunta; `questionId` en cada evaluación |
| `optionId` | sí | sí (en la respuesta) | `response.selectedOptionIds` validado contra los `id` de la pregunta; **una posición es 400** |
| `mediaId` | sí | sólo si hace falta | `media_ref` del selector cuando se proyecta un medio suelto |
| `topicRef` | sí | recomendado | Viaja en la vista (`tema_ref`); no se guarda todavía (informe por tema es de MOD-012) |
| `translationGroupId` | sí | opcional | Viaja en la vista (`grupo_traduccion`); no se guarda |
| `title`, `subtitle` | **no** | sólo como rótulo histórico | `curso_rotulo`, `leccion_rotulo`, `rotulo` (artículo 13.3). **Nunca son clave** |
| `sessionId` de medios | efímero | **no** | Una sesión de un minuto por petición de bytes; el LMS no la guarda ni la reutiliza |
| `apiPort`, `mediaPort`, `token` | efímeros | **no** | `link.json` releído en cada llamada |

---

## 4 · Preguntas · lo que llega y lo que se envía

Las seis clases de pregunta ya estaban en el normalizador ([01](01-modelo-de-datos.md) §2.5). Lo que fija el contrato y cómo lo aplica el aula:

| Tipo | Llega **sin** | Vista de aula | `response` que exige `/v2/evaluate` | Validación previa del aula (`dominio/respuestas.py`) |
|---|---|---|---|---|
| `multiple_choice` | marca de correcta; opciones **barajadas** en cada llamada (`seed` fija el orden) | `opciones[{opcion_ref, texto}]`, `permite_varias` | `{"selectedOptionIds": ["a"]}` | lista no vacía de `id` existentes; una sola si `permite_varias` es falso; se eliminan repetidos |
| `true_false` | `answer` | dos opciones fijas `true`/`false` | `{"value": true}` | booleano (o `"true"`/`"false"`) |
| `fill_blanks` | valor esperado de cada hueco | `plantilla` con `{{id}}`, `espacios[{espacio_ref, modo_entrada, opciones}]` | `{"blanks": {"b1": "2", "b2": "5"}}` | cada clave es un hueco de la plantilla; los valores viajan como texto |
| `matching` | `pairs`, `wrongPairs`; `right` trae **distractores** | `izquierda[]`, `derecha[]` (más larga) | `{"pairs": [{"leftId","rightId"}]}` | cada `leftId` está en `izquierda` y cada `rightId` en `derecha` |
| `ordering` | `correctOrder`; `items` **desordenados** | `elementos[]` | `{"order": ["o14","o13","o12"]}` | exactamente los elementos de la pregunta, una vez cada uno |
| `open` | `modelAnswer`, `rubric`, `incorrectExamples` | `formato_respuesta`, `longitud_maxima` | `{"text"}` **o** `{"drawingRef"}` **o** `{"audioRef"}` | exactamente uno de los tres; `text` respeta `longitud_maxima` |
| *desconocido* | — | `componente: no_soportado`, se **muestra** | tal cual | se reenvía sin tocar: conjunto abierto (§9 del mapeo) |

### 4.1 · El veredicto

`POST /api/aula/cursos/{curso_ref}/evaluar/?fuente=biblioteca` (respuesta real de la API instalada):

```json
→ {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["a"]}}
← {"fuente": "biblioteca", "curso_ref": "avacom.co.lower-secondary.6.science.states-of-matter", "version": "2.0.0",
   "objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "puntaje": 1.0, "puntaje_maximo": 1.0, "correcta": true,
   "requiere_correccion_manual": false, "pendiente": false,
   "retroalimentacion": ["Correcto: el aire es una mezcla de gases."]}
```

| Campo del contrato | Campo del aula | Regla |
|---|---|---|
| `score` (número **o nulo**) | `puntaje` | `float` o `null`. Con `requiresManualGrading` es **siempre** `null` aunque llegara un número: no se inventa nota |
| `maxScore` (puede no ser entero) | `puntaje_maximo` | `float` |
| `correct` (booleano **o nulo**) | `correcta` | `null` en abiertas; la API real devuelve `false` en el crédito parcial (2.0 de 3.0), el aula lo conserva tal cual |
| `requiresManualGrading` | `requiere_correccion_manual` | `true` → el intento queda **pendiente**. En la respuesta real de una abierta `score` y `correct` **no vienen** (ausentes, no nulos): el aula los trata igual |
| — | `pendiente` | `requiere_correccion_manual` o `puntaje` nulo: lo que MOD-010 debe dejar en `pendiente_correccion` |
| `feedback` (lista, puede venir vacía) | `retroalimentacion` | lista de texto; nunca contiene la clave |

`version`: si el cuerpo no la trae, se usa la del curso instalado; en ambos casos viaja a `/v2/evaluate`. Con `{"version": "…", "items": [{objeto_ref, pregunta_ref, respuesta}…]}` se usa `/v2/evaluate/batch` y la respuesta es `{veredictos[], pendientes}`.

La fuente `ejemplo` responde **501 `capacidad_ausente`**: el manifiesto de ejemplo trae las claves, pero la regla es que la clave se compara sólo donde vive; el aula no simula veredictos. La validación de forma (§4) sí se ejecuta antes, así que una respuesta mal formada es 400 con cualquier fuente.

---

## 5 · Enumeraciones y conjuntos abiertos

Valores del contrato (mapeo §3) frente a los catálogos del aula (`dominio/catalogos.py`):

| Conjunto | Contrato v2 | Aula | Si llega otro valor |
|---|---|---|---|
| Modos | `simple · class · exam · review · free_learning` | `MODOS` (iguales) | se conserva en `modos[]` |
| Tipos de objeto | `lecture · explanation · simulation_lab · activity · exam` | `TIPOS_OBJETO` | `componente: no_soportado`, con `crudo` sin claves: **se muestra** |
| Tipos de pregunta | `multiple_choice · true_false · fill_blanks · matching · ordering · open` | `TIPOS_PREGUNTA` | `componente: no_soportado`; la respuesta se reenvía tal cual |
| Tipos de medio | `image · video · audio · pdf · simulation` | `CLASES_MEDIO` | `componente: no_soportado` |
| Bloques | `heading · text · list · formula · image · video · audio · pdf` | `TIPOS_BLOQUE`, **con `formula`** (`{latex, display}` → `componente: formula`, `latex`, `en_bloque`, `texto` legible «1/3 × 2») | `crudo` (aviso en el cliente) |
| Nivel cognitivo | `remember … create` | `nivel_cognitivo`, informativo | se conserva |
| Ajustes de actividad | `feedback: immediate · on_submit · none` | `ajustes.retroalimentacion` | se conserva |
| Ajustes de examen | `selection.strategy`, `timeLimit.policy`, `showResults` | `ajustes` del objeto `exam` | se conserva (MOD-010) |
| Simuladores | `provider`, `technology`, `orientation`, `shims`, `supportsTargets` | `simulacion{proveedor, tecnologia, orientacion, ajustes, destinos}` | se conserva |
| Códigos de error | los del mapeo más los del `openapi.json`: `object_not_found · question_not_found · version_not_available · media_session_not_found · policy_disabled · answer_keys_forbidden` | §6 | `502 fuente_error` con `codigo_biblioteca` |

El curso «Fracciones: partes de un todo» ya usa `formula` (`\frac{1}{3}`): por eso el bloque se añadió al normalizador y al visor MAUI (texto matemático legible, sin motor LaTeX en la tableta).

Regla del contrato que el LMS ya cumplía y que se comprobó de nuevo: **añadir un campo no rompe a nadie**. El normalizador toma los campos por nombre e ignora el resto (`countryName`, `updatedAt`, `lessonCount`…); ningún deserializador estricto falla ante una propiedad desconocida. Los tipos del LMS no se generaron desde `course.schema.json`: los opcionales son anulables (`None`), no valores por defecto.

---

## 6 · Errores · del contrato al aula

| API v2 | Estado | Código del aula | HTTP del aula | Qué ve el cliente |
|---|---|---|---|---|
| sin `link.json`, puerto muerto, sin respuesta a tiempo | — | `fuente_no_disponible` | **503** `{disponible: false, detail, sugerencia}` | «Biblioteca apagada · tocar para usar el ejemplo» |
| `index_rebuilding` (o `index: rebuilding` en `/v2/health`) | 503 | `fuente_no_disponible` + `codigo_biblioteca` | 503 con `sugerencia: "…vuelve a intentarlo en unos segundos"` | igual, con «Reintentar» |
| `course_not_found`, `version_not_available` | 404 | `curso_no_encontrado` | 404 | sin inventar título |
| `not_found`, `lesson_not_found`, `object_not_found`, `question_not_found`, `media_session_not_found` | 404 | `referencia_no_encontrada` | 404 | |
| `invalid_parameter` por un `mediaId` que no está en el curso (`media-sessions`) | 400 | `referencia_no_encontrada` | 404 | el aula lo traduce: para ella es «no existe» |
| `policy_disabled` (`disabled_by_policy` en el mapeo) | 403 | `desactivado_por_politica` | **404** | lo que la política desactivó **no se muestra ni se guarda**; en la lista no viene |
| `invalid_parameter` | 400 | `datos_invalidos` | 400 | |
| `invalid_response` (forma de `response` incorrecta; sólo llega con versiones archivadas, porque el aula valida antes) | 422 | `datos_invalidos` | 400 | |
| `unauthorized` tras el reintento | 401 | `fuente_error` + `codigo_biblioteca: unauthorized` | **502** | |
| `answer_keys_forbidden` y cualquier otro | * | `fuente_error` + `estado_biblioteca` | 502 | |

Todos llevan `codigo_biblioteca` cuando la API mandó código, para que el soporte pueda cruzar con los registros de la biblioteca (`%ProgramData%\AVACOM\content\logs\`).

---

## 7 · Cómo se probó

### 7.1 · Contra la API instalada (2026-09-21)

Con la app «AVACOM Contenido» encendida (`Avacom.Content.App.exe`, API en `apiPort`, medios en `mediaPort`) y cuatro cursos instalados, el backend del LMS respondió:

| Llamada del aula | Resultado |
|---|---|
| `GET /api/aula/fuente/?fuente=biblioteca` | `disponible: true`, contrato 2, puertos, huella `v2-…`, los cuatro cursos instalados con su versión |
| `GET /api/aula/cursos/?fuente=biblioteca` | Cuatro asignaturas: Ciencias naturales (Estados de la materia 2.0.0), Dimensión comunicativa (Las vocales), Matemáticas (Fracciones), Social Studies (The U.S. Constitution); 85 ms |
| `GET /api/aula/cursos/{estados}/?rol=docente` | Esquema + 2 lecciones completas (la de examen viene vacía con `mode=class`): 7 objetos, 12 preguntas, 16 medios, `notas_docente` presentes, **ninguna clave**; 50 ms |
| ídem sin `rol` | sin `notas_docente` |
| Los otros tres cursos | Se normalizan completos; Fracciones trae `formula` |
| `GET …/objetos/l1-activity/?semilla=aula-1` | Mismo orden de opciones en dos llamadas seguidas |
| `GET …/medios/img-particles/` · `vid-changes/` con `Range` · `HEAD` | PNG 13 036 B · `206 bytes 0-9/154451` · `Content-Length` sin cuerpo |
| `…/vid-changes/subtitulos` · `…/aud-summary/transcripcion` | WebVTT · texto |
| `…/sim-heating-curve/index.html` · `…/sim-phet-states/states-of-matter-basics_es.html` · pdf · audio | 200 con su `Content-Type` |
| `…/medios/no-existe/` | 404 `referencia_no_encontrada` |
| `POST …/evaluar/` opción `a` · relacionar 2 de 3 · abierta · lote de 2 | `1.0/1.0 correcta` · `2.0/3.0` · `puntaje: null, pendiente: true` · `pendientes: 0` |
| `POST …/evaluar/` con `selectedIndex` | 400 antes de llegar a la biblioteca |
| `POST /api/aula/sesiones/` vía `leccion` con `fuente=biblioteca` | Sesión abierta con `curso_version: "2.0.0"`, selector inicial en la primera lámina; cerrada después |

### 7.2 · Sin la biblioteca: el host de pruebas

`backend/tools/host_contenido_v2_pruebas.py` imita la API v2 **con la forma real** a partir del manifiesto completo (`example.json`, que sí trae las claves): dos servidores (API y medios), `X-Avacom-Token`, `/v2/courses` paginado, esquema con resúmenes de objeto, lecciones y objetos completos recortados, `seed`, filtro por `mode`, `policy_disabled`, `index_rebuilding`, `version_not_available`, `evaluate` con crédito parcial y 422, `media-sessions` con `@captions`, `@transcript`, `@files` y `Range`. Escribe `link.json` con `contract`, `apiPort`, `mediaPort`, `token` y `pid`, y puede forzar 401 seguidos (`rechazar_proximas`).

```
cd backend
.venv\Scripts\python -m tools.host_contenido_v2_pruebas %TEMP%\link-pruebas.json
set AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\link-pruebas.json
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```

| Suite | Pruebas | Qué comprueba |
|---|---|---|
| `classroom_engine.tests.test_curso · ConLaApiDeContenidoV2Tests` (13) | misma vista que el ejemplo (con `mode=class` y `profile` por rol); opciones barajadas identificadas por `id`; la lista pide el esquema de cada curso; el curso se arma con el esquema y cada lección completa, `hasCaptions` → `subtitulos_url`, `semilla` → `seed`; sólo la versión instalada; **401 reintenta una sola vez** y el segundo es 502; códigos de error traducidos; estado de la fuente; medios por sesión de un minuto con `Range`, subtítulos, transcripción y archivo interno; evaluar opción múltiple **siempre con `version`**; los demás tipos y el crédito parcial decimal; abierta pendiente; lote con versión archivada y 422 → 400 |
| `classroom_engine.tests.test_curso · CursoDeEjemploTests` (+2) | sin `link.json` → 503 «sin contenido» y `GET /api/aula/fuente/`; la fuente de ejemplo no califica (501) pero valida la forma (400) |
| `classroom_engine.tests.test_respuestas` (5) | la forma de `response` por tipo (17 casos inválidos), tipo desconocido reenviado, `score`/`correct` nulos y decimales, corrección manual sin nota |
| `Avacom.Lms.Core.Tests · AulaApiTests` (+1) | sin fuente el parámetro no viaja; con fuente se añade a la consulta |

Totales: **59** pruebas del aula, **177** del backend, **15** del núcleo MAUI.

### 7.3 · Lista de verificación del mapeo (§8), con veredicto

| | Estado |
|---|---|
| Las tablas del expediente guardan `courseId` **y** `version` | ✅ `m07_sesion`, `m07_selector`; `m10_intento` guarda `curso_ref` y recibe `version` en el veredicto (falta la columna: Q-48) |
| Guardan `lessonId`, `objectId`, `questionId`, no títulos | ✅ `*_ref`; los títulos sólo como `*_rotulo` |
| La respuesta de una opción guarda su `id`, no su índice | ✅ `selectedOptionIds` validado contra los `id` de la pregunta; un índice es 400 |
| `score` y `correct` admiten nulo | ✅ `puntaje`, `correcta` → `None` (también cuando la API los omite) |
| `score` y `points` admiten decimales | ✅ `float`; `puntos_totales` de la actividad se suma como decimal |
| `requiresManualGrading: true` deja el intento pendiente, sin nota | ✅ `puntaje: null`, `pendiente: true` aunque llegue un número |
| Los tipos se generaron desde `openapi.v2.json`, no desde `course.schema.json` | ✅ el normalizador lee por nombre y todo opcional es anulable; el `openapi.v2.json` real está guardado junto a este documento |
| Un tipo de objeto o de pregunta desconocido **se muestra**, no se descarta | ✅ `componente: no_soportado` + `crudo` |
| `/v2/evaluate` se llama con `version` | ✅ obligatorio en el cliente (`ValueError` sin ella) y siempre puesto por el caso de uso |
| No hay ninguna tabla que replique el catálogo | ✅ `test_el_esquema_es_solo_de_aula_sin_curso_ni_claves` |
| `link.json` se relee en cada petición | ✅ |
| Un `401` reintenta **una** vez tras releer `link.json` | ✅ probado |
| La ausencia de `link.json` produce «sin contenido», no un error | ✅ 503 con `disponible: false` y sugerencia |

---

## 8 · Los supuestos iniciales y lo que resultó

La primera versión se escribió sólo con el mapeo de campos, con ocho supuestos. Al instalar la API se comprobaron uno por uno contra `GET /v2/openapi.json` y contra las respuestas reales:

| # | Supuesto inicial | Realidad | Cambio |
|---|---|---|---|
| A-1 | Token como `Authorization: Bearer` | **No.** Cabecera propia `X-Avacom-Token` (`securitySchemes.token`, `apiKey in header`) | `CABECERA_TOKEN` |
| A-2 | `GET /v2/courses` devuelve la lista | **Sí**, como `CoursePage` `{items, page, pageSize, total}` con filtros | Paginación en `cursos()` |
| A-3 | Bytes en `GET /v2/courses/{id}/media/{mediaId}` | **No.** `POST /v2/media-sessions` → URL-capacidad en un **segundo servidor** (`mediaPort`), con `extras` para subtítulos, transcripción y archivos de simulación | `sesion_medios()` + `_pedir_medio()`; una sesión de 60 s por petición |
| A-4 | `link.json` en `%ProgramData%\AVACOM\contenido\` | **No.** En `%ProgramData%\AVACOM\content\link.json`, con `contract`, `apiPort`, `mediaPort`, `token`, `pid`, `startedAt` | `ruta_enlace()`, `leer_enlace()` |
| A-5 | Errores `{"error": {"code", "message"}}` | **Sí**, más `details: {}` | — |
| A-6 | `?mode=class` filtra los objetos | **Sí**: la lección de examen llega con `objects: []` | — |
| A-7 | El curso trae `id` | **No**: trae `courseId`; lecciones y objetos sí traen `id` | `_con_id()` |
| A-8 | `installedCourses` es una lista | **No**: es un **entero**; la lista sale de `/v2/courses` | `estado()` |
| — | (no previsto) el curso llega completo en una llamada | **No**: `GET /v2/courses/{id}` es el **esquema** (resúmenes de objeto); las láminas y preguntas se piden por lección u objeto | `curso()` = esquema + `leccion()` por cada lección con objetos |
| — | (no previsto) `?version=` en el curso | **No existe**: sólo en `evaluate` y `grading-guide` | §2.2 |
| — | (no previsto) `seed` para el barajado | **Existe** en lección y objeto | `?semilla=` en `/api/aula/cursos/{ref}/…` |
| — | (no previsto) `hasCaptions`/`hasTranscript` en vez de `captionsPath`/`transcriptPath` | La API no publica rutas internas | `_medio()` del normalizador acepta ambos |

---

## 9 · Lo que cambió en el código

| Capa | Archivo | Cambio |
|---|---|---|
| Biblioteca (cliente) | `backend/biblioteca/contenido_v2.py` | **Nuevo.** `leer_enlace` (`content/link.json`, `contract`, `mediaPort`), `_pedir` (`X-Avacom-Token`, 401 → releer y reintentar una vez), `salud`, `cursos` (paginado), `esquema_curso`, `leccion`, `objeto`, `curso` (esquema + lecciones), `guia_calificacion`, `evaluar`, `evaluar_lote` (troceo a 200, `results`), `sesion_medios`, `abrir_medio` (sesión de 60 s, `@captions`, `@transcript`, archivos internos), `huella`, `estado` |
| Biblioteca (cliente) | `backend/biblioteca/cliente.py` | `BibliotecaError.codigo` (código del contrato v2; vacío en el contrato 1) |
| Aula · dominio | `classroom_engine/dominio/respuestas.py` | **Nuevo.** `validar_respuesta(pregunta, respuesta)` por tipo y `veredicto(bruto)` |
| Aula · dominio | `classroom_engine/dominio/errores.py` | `DesactivadoPorPolitica` (404 `desactivado_por_politica`) |
| Aula · dominio | `classroom_engine/dominio/catalogos.py`, `curso.py` | Bloque `formula` (`latex`, `en_bloque`, `texto` legible con `texto_formula`); `hasCaptions`/`hasTranscript` |
| Aula · puertos | `classroom_engine/aplicacion/puertos.py` | `FuenteDeCursos.curso(ref, *, version, rol, semilla)`, `evaluar`, `evaluar_lote`, `estado` |
| Aula · casos de uso | `classroom_engine/aplicacion/casos_uso.py` | `_vista(…, version, semilla)`; `ConsultarCurso/Leccion/Objeto` con `version` y `semilla`; **`EstadoFuente`**, **`EvaluarRespuesta`** (con versión archivada delega la validación en la biblioteca) |
| Aula · infraestructura | `classroom_engine/infraestructura/fuente_biblioteca.py` | Reescrito sobre `contenido_v2`: lista por esquemas, curso por lecciones, `mode=class`, `profile` por rol, traducción de todos los códigos del `openapi.json` |
| Aula · infraestructura | `classroom_engine/infraestructura/fuente_ejemplo.py` | Misma firma; `version` distinta → 404; `evaluar` → 501; `estado` |
| Aula · HTTP | `classroom_engine/interfaces/views.py`, `urls.py` | `GET fuente/`, `?version=` y `?semilla=` en curso/lección/objeto, `POST cursos/{ref}/evaluar/` |
| Configuración | `backend/avacom_lms/settings.py` | `AVACOM_CONTENIDO_ENLACE_V2` |
| Pruebas | `backend/tools/host_contenido_v2_pruebas.py` | **Nuevo** host con la forma real de la API v2 (dos servidores) |
| Pruebas | `classroom_engine/tests/test_curso.py`, `test_respuestas.py` | Suite v2 (sustituye a la del host del contrato 1 para el aula), respuestas |
| Referencia | `spec-driven/02-classroom-engine/openapi.v2.json` | Copia del contrato que publica la API instalada |
| MAUI · núcleo | `Avacom.Lms.Core/Services/AulaApi.cs` | `Fuente` anulable: sin fuente el parámetro no viaja |
| MAUI · Ui | `Controls/AulaContenidoView.cs` | Bloque `formula` (texto matemático legible, itálica, sobre lienzo) |
| MAUI · OPS | `Sesion.cs`, `Pages/ClaseHoyPage.xaml.cs` | `FuenteAula` en `Preferences` (por defecto `biblioteca`); alerta ámbar «Biblioteca no está encendida» con **«Usar el curso de ejemplo»**; el chip de fuente alterna al tocarlo |
| MAUI · Student | `Sesion.cs` | Sin `FuenteAula`: la tableta no elige fuente |

---

## 10 · Lo que queda fuera y dónde sigue

| Qué | Dueño | Nota |
|---|---|---|
| Guardar el intento, la respuesta y el veredicto (`m10_intento`, `m10_intento_respuesta`) con `version`, `score` decimal/nulo y estado `pendiente_correccion` | MOD-010 (Q-48, Q-49) | El aula ya devuelve todo lo necesario en `/evaluar/`; el flujo de intentos del expediente sigue con el contrato 1 (`/v1/comprobar`) hasta que se migre |
| Armar el examen por alumno (`/v2/courses/{id}/exams/{oid}/pool` y `…/questions?ids&seed`) | MOD-010 | La API ya lo ofrece; el aula sigue sin ejecutar exámenes |
| Calificar a mano una abierta con `grading-guide` | MOD-011 | El cliente ya la pide; falta la pantalla del docente y la ruta, fuera del aula |
| Responder la actividad desde la tableta (S2) | Frontend MOD-007 | La vista previa puede pasar a enviar `POST /evaluar/` con la forma de §4 cuando MOD-010 guarde el intento; conviene pasar `semilla=<sesion>` para que toda la clase vea el mismo orden |
| Pasar `semilla` desde OPS y Student | Frontend MOD-007 | El backend ya la acepta; hoy los clientes no la mandan |
| Bajar sólo el objeto en selector (`/v2/courses/{id}/objects/{oid}`) en vez del curso entero | Backend MOD-007 | Hoy cada petición de objeto arma el curso (esquema + lecciones), unas decenas de milisegundos en loopback; optimizar si una tableta lo nota |
| Árbol, búsqueda y política (`/v2/tree`, `/v2/search`, `/v2/policies`) | MOD-004 | Fuera del aula |
| Caché en memoria de minutos invalidada por la huella | — | **No se implementa**: el artículo 14 prefiere preguntar siempre; `huella` queda disponible si algún día hace falta |
