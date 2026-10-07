# 06 · Classroom Engine · Versión 2 de Contenido: esquema de curso 1.0 y validador de referencia

| Campo | Valor |
|---|---|
| Módulo | MOD-007 · Classroom Engine · fuente de cursos `biblioteca` (API de Contenido v2) |
| Estado | **Implementado y probado** (2026-09-28). Backend: 219 pruebas en verde (104 del aula y la biblioteca, 20 nuevas de contrato). Núcleo MAUI: 16 en verde. `Avacom.Lms.Ui` y `Avacom.Lms.Ops` compilan. Verificado en vivo contra la app «AVACOM Contenido» **2.1.7** hasta donde su estado lo permitió (§6) |
| Entrada | Los tres archivos que publica el equipo de Biblioteca: [`openapi.v2.json`](openapi.v2.json) (sin cambios), [`course.schema.json`](course.schema.json) (**nuevo**, la estructura del curso 1.0) y [`validate_course.py`](validate_course.py) (**nuevo**, las reglas que un curso debe cumplir para instalarse, lo que un alumno puede recibir y la corrección de referencia) |
| Complementa a | [05 · Contrato con la API de Contenido v2](05-contrato-biblioteca.md): todo lo de transporte, rutas, identificadores, errores y medios sigue vigente. Este documento cubre lo que 05 no podía saber: la forma exacta del curso y las reglas de corrección |
| Documentos hermanos | [01 · Modelo de datos y API](01-modelo-de-datos.md) · [04 · Frontend](04-frontend-classroom-engine.md) · [00 · Introducción](00-introduccion.md) (`example.json`) |

---

## 0 · Resumen

1. **Los endpoints, los puertos al azar y el token no cambian.** El `openapi.v2.json` entregado es **idéntico byte a byte** a la copia del 2026-09-21 que ya estaba en el repo (`diff` vacío): `link.json` con `apiPort`/`mediaPort`/`token` efímeros, la cabecera `X-Avacom-Token`, las sesiones de medios y los códigos de error se mantienen. El cifrado tampoco toca al LMS: el curso viaja cifrado **dentro del paquete** (`course.json.enc`, firmado) y lo descifra la biblioteca; el aula sólo ve JSON por loopback, como siempre.
2. **Lo nuevo es la definición formal de la estructura**: `course.schema.json` (`$id urn:avacom:content:course:1.0`, JSON Schema 2020-12, `additionalProperties: false` en casi todo) y `validate_course.py`, que la biblioteca declara como «la definición ejecutable de las reglas» que su implementación en C# replica.
3. **`example.json` cumple el esquema y las reglas sin un solo error ni aviso.** La vista de aula ya era compatible; los ajustes de este documento son por lo que el esquema **permite** y el ejemplo no ejercitaba: `*cursiva*` y matemática en línea en `RichText`, medios en el enunciado (`mediaIds`), opciones e ítems que son **imágenes** (`ChoiceItem.mediaId`), `points` decimal, `timeLimitSec`, `fixedSec`, `estimatedSec` en páginas y `curriculumRefs` en lección, objeto y pregunta.
4. **La corrección de referencia fija dos cosas que el aula asumía distinto**: `correct` es **siempre booleano** en las preguntas automáticas (`ratio == 1.0`, así que el crédito parcial es `correct: false` con puntos), y `feedback[0]` es **siempre la retroalimentación general**, seguida de las específicas de la opción, el hueco, la pareja o el orden elegidos. Coincide con lo observado en vivo el 21-09 («la API real devuelve `false` en el crédito parcial»); el host de pruebas ahora está **calcado** de `evaluate_response` y `visible_object`, con paridad probada función a función.
5. **Dos claves más que nunca salen del aula**: `keywords` (de una abierta) y `numericTolerance` (de un hueco), que el validador lista entre las que revelan la respuesta. `includeActivityKeys` existe en el contrato y **el aula no lo usa** (artículo 14: la clave se compara donde vive); hay prueba de que nunca viaja.
6. **Hallazgo en vivo**: la app instalada hoy (**2.1.7**) publica un contrato **más nuevo que los archivos entregados**: valida con un esquema que renombra los ajustes de examen, añade un séptimo tipo de pregunta (`drag_drop`), `track`, `relation` y `hasSpeech`; añade `/v2/packages` y `/v2/curriculum`, retira `/v2/policies`, acepta `version` en curso, lección y objeto, y responde **500 `package_invalid`** para tres de los cuatro paquetes instalados (§6). El aula ya degrada bien ante eso (ficha marcada en el panel, 502 `paquete_invalido` con sugerencia) y entiende los dos nombres de los ajustes de examen.

---

## 1 · Los archivos del contrato

| Archivo | Qué define | Copia en el repo | Respecto a lo que había |
|---|---|---|---|
| `openapi.v2.json` | Rutas, parámetros, esquemas de respuesta y códigos de error de la API de Contenido v2 | [`openapi.v2.json`](openapi.v2.json) | **Sin cambios** (idéntico a la copia del 21-09) |
| `course.schema.json` | La **estructura** de `course.json`: curso → lecciones → objetos (`lecture`, `explanation`, `simulation_lab`, `activity`, `exam`) → bloques y preguntas; medios y licencias; sólo validación estructural | [`course.schema.json`](course.schema.json) | **Nuevo.** Hasta ahora el aula se guiaba por `example.json` y por el «Mapeo de campos» |
| `validate_course.py` | Dos capas: (1) estructura con el esquema; (2) **semántica**: ids únicos, referencias, subconjunto de modos, claves completas, viabilidad del examen, seguridad sin red, licencias. Además `visible_object` (lo que recibe un alumno) y `evaluate_response` (la corrección) | [`validate_course.py`](validate_course.py) | **Nuevo.** Es «la definición ejecutable de las reglas» que la biblioteca implementa en C# con los mismos códigos |
| *(en vivo)* `openapi.json` de la app 2.1.7 | Lo que publica `GET /v2/openapi.json` de la app instalada hoy | [`openapi.v2.instalado-2.1.7.json`](openapi.v2.instalado-2.1.7.json) | Más nuevo que el entregado (§6.1) |
| *(en vivo)* esquema de la app 2.1.7 | El `course.schema.json` incrustado en `Avacom.Content.Core.dll`, con el que la app valida los paquetes | [`course.schema.instalado-2.1.7.json`](course.schema.instalado-2.1.7.json) | Mismo `$id` 1.0, contenido distinto (§6.1) |

El LMS **no valida cursos**: eso lo hace la biblioteca antes de instalar (`E-PKG-*`) y el validador al publicar. El validador se guarda como referencia ejecutable, como guarda de `example.json` y como oráculo del host de pruebas. Necesita `jsonschema>=4.18`, que **no** es dependencia del LMS: sin él, las tres pruebas que lo importan se omiten y las demás siguen valiendo (§8).

---

## 2 · Lo que se mantiene, comprobado

| Regla | Cómo se comprobó | Estado |
|---|---|---|
| Rutas del aula: `/v2/health`, `/v2/courses`, `/v2/courses/{id}` (+ `lessons`, `objects`), `/v2/media-sessions`, `/v2/evaluate` (+ `batch`), `grading-guide` | `diff` del `openapi.v2.json` entregado con la copia del repo: vacío | Igual |
| `link.json` en `%ProgramData%\AVACOM\content\`, puertos al azar en cada arranque, releído en cada petición | Descripción del `openapi` sin cambios; en vivo hoy la app arrancó tres veces con puertos distintos (53764, 58657, 65473) y el aula la siguió sin reiniciar nada | Igual |
| Token en `X-Avacom-Token`, un reintento tras 401 | `securitySchemes.token` sin cambios | Igual |
| Cifrado del paquete | `course.schema.json`: «Travels encrypted inside the signed package as `course.json.enc`». Lo descifra la biblioteca; el LMS nunca ve el paquete | No aplica al LMS |
| Medios por sesión (`POST /v2/media-sessions` → URL-capacidad en `mediaPort`) | `MediaSessionRequest`/`MediaSession` sin cambios | Igual |
| `mode=class` filtra objetos; `profile=student` recorta `teacherNotes`; `seed` fija el barajado | Parámetros sin cambios; el validador lo confirma (§3.6) | Igual |
| Errores `{"error": {"code", "message", "details"}}` | `Error` sin cambios; código nuevo en vivo: `package_invalid` (§6.3) | Igual + 1 |

---

## 3 · Lo que el esquema 1.0 fija y cómo lo cumple el aula

### 3.1 · Identificadores

| Regla del esquema o del validador | Efecto en el LMS |
|---|---|
| `Id`: `^[a-z0-9]+(?:[._-][a-z0-9]+)*$`, hasta **120** caracteres, permanente (nunca se reutiliza ni se renombra) | `curso_ref` (200), `leccion_ref`, `objeto_ref`, `unidad_ref`, `media_ref` (120) y `curso_version` (32, semver `x.y.z`) caben. Ningún cambio de columna |
| Únicos en **todo el curso**: medios, temas y subtemas, lecciones, objetos, láminas y páginas, preguntas (`E-ID-DUP`) | `localizar()` puede buscar una unidad por su ref dentro del objeto sin ambigüedad |
| Únicos sólo **dentro de su pregunta**: opciones, huecos, ítems de relacionar y ordenar (`E-ID-DUP-LOCAL`) | La respuesta viaja con `pregunta_ref` + `opcion_ref`; nunca se guarda una opción sin su pregunta |
| `translationGroupId`: informativo, cada traducción es un curso aparte | `grupo_traduccion` en la vista, no se guarda |

### 3.2 · Curso, lección y objeto

Campos del esquema que la vista de aula no exponía y ahora sí:

| Esquema | Vista de aula | Dónde |
|---|---|---|
| `curriculumRefs` en lección, objeto y pregunta (antes sólo en el curso) | `referencias_curriculares[{marco, codigo, descripcion, relacion}]` | lección, objeto, pregunta |
| `ContentPage.estimatedSec` en páginas de `explanation` (ya salía en láminas) | `duracion_seg` | `paginas[]` |
| `ActivityObject.settings.timeLimitSec` | `ajustes.tiempo_limite_seg` | actividad |
| `ExamObject.settings.timeLimit.fixedSec` | `ajustes.tiempo.fijo_seg` | examen (informativo, MOD-010) |
| `ActivityObject.instructions` (RichText) | `instrucciones_tramos` | actividad |
| `points` es `number` (`exclusiveMinimum: 0`) | `puntos` decimal y `puntos_totales` = suma decimal (antes se truncaba con `int()`); en C# `double?` | pregunta, actividad |

Lo demás ya estaba: `classification` (país ISO, nivel/grado con `order`, asignatura, tema), `credits`, `keywords`, `estimatedDurationMin`, `coverMediaId` (debe ser una imagen), `topics` con `subtopics`, `launchParams`, los ajustes de actividad y examen.

### 3.3 · `RichText` → `tramos`

El esquema define `RichText` como el **subconjunto «AVACOM Markdown»**: `**negrita**`, `*cursiva*`, listas con viñeta y numeradas, saltos de línea y **matemática en línea entre `$...$`**; el HTML crudo está prohibido y el renderizador lo escapa. `ShortText` (títulos, rótulos, hasta 300) no lleva marcado.

| Marca | Tramo | Cliente MAUI |
|---|---|---|
| `**texto**` | `{texto, negrita: true}` | Inter 600 (como hasta ahora) |
| `*texto*` | `{texto, cursiva: true}` | `FontAttributes.Italic` (no hay Inter Italic empaquetada: es la única itálica sintética del kit, la misma del bloque `formula`) |
| `$\frac{1}{3} \times 2$` | `{texto: "1/3 × 2", matematica: true}` (ya legible con `texto_formula`, sin motor LaTeX en la tableta) | itálica |
| listas y saltos de línea | viajan tal cual dentro de `texto` | la `Label` respeta los saltos |
| `2*3*4` | no es cursiva (un asterisco pegado a un dígito o letra no abre marca) | — |

`tramos[]` ahora lleva siempre las cuatro claves (`texto`, `negrita`, `cursiva`, `matematica`) y se aplica también a los ítems de relacionar y ordenar y a las instrucciones de la actividad. `texto_plano()` deja la matemática en su lectura. En C# `Tramo` recibe `Cursiva` y `Matematica` con valor por defecto `false`: un backend anterior que sólo mande `negrita` sigue deserializando.

### 3.4 · Medios y licencias

| Regla | Efecto |
|---|---|
| `Media.kind`: `image · video · audio · pdf · simulation`; `altText` **obligatorio** en imágenes; `captionsPath`/`transcriptPath` (la API publica `hasCaptions`/`hasTranscript`) | Sin cambios en la vista (`texto_alternativo`, `subtitulos_url`, `transcripcion_url`) |
| `License.type`: `avacom · cc-by-4.0 · cc-by-sa-4.0 · cc-by-nc-4.0 · cc-by-3.0 · public-domain · licensed · other`; `attribution` es «el texto exacto a mostrar junto al punto de uso cuando la licencia lo exige»; `sourceUrl` es **el único campo donde se permite una URL** y nunca se carga | `licencia{tipo, atribucion, fuente_url}`; el visor ya muestra la atribución (PhET, CC BY 4.0) |
| `E-NET-EXTERNAL`: ninguna cadena del curso (salvo `license`) puede contener `http(s)://`, `//` ni `www.` | El aula no tiene internet; la `WebView` nunca va a necesitarla |
| `SimulationRuntime`: `provider`, `technology` (incluye `flash_ruffle`), `designWidth/Height`, `orientation`, `shims` (`block_network` siempre aplicado), `supportsTargets` (`screen`, `tablet`); `E-SIM-DESIGN-SIZE` | `simulacion{proveedor, tecnologia, ancho_diseno, alto_diseno, orientacion, ajustes, destinos}`, sin cambios |
| `E-LIC-*`: CC exige `attribution`; `cc-by-nc` y PhET publicado desde 2026-03-29 exigen `agreementRef` | Lo hace cumplir la biblioteca al publicar; el aula sólo muestra |

### 3.5 · Preguntas

`QuestionBase`: `id`, `type`, `prompt` (RichText), `mediaIds[]`, `topicRef`, `difficulty` 1–5, `estimatedSec` ≥ 5, `points`, `cognitiveLevel` (Bloom), `curriculumRefs`, `teacherNotes`, `feedback{correct, incorrect}` (obligatorio), `partialCredit`.

| Tipo | Lo que el esquema añade y el ejemplo no usaba | Vista de aula (nuevo en **negrita**) |
|---|---|---|
| común | `mediaIds`: imagen, video, audio o pdf «mostrados con el enunciado, en este orden» | **`medios[]`** (la vista completa de cada medio, con `url`; un id que no existe llega con `ausente: true`) · **`referencias_curriculares`** · `puntos` decimal |
| `multiple_choice` | cada opción lleva `text` **o** `mediaId` (imagen), o ambos; 2 a 8 opciones | `opciones[{opcion_ref, texto, tramos, **media_ref, url, texto_alternativo**}]` |
| `true_false` | `answer` (clave) | dos opciones fijas, sin cambios |
| `fill_blanks` | `template` con `{{id}}` exactamente una vez por hueco (`E-BLANK-TEMPLATE`); `inputMode` `text · select · numeric`; `choices` obligatorio en `select` y debe contener una aceptada y una incorrecta (`E-BLANK-SELECT`); `caseSensitive`, `ignoreAccents`, `numericTolerance` | `plantilla`, `espacios[{espacio_ref, modo_entrada, opciones}]`, sin cambios (la normalización es de la corrección, §5) |
| `matching` | `left`/`right` son `ChoiceItem` (texto o **imagen**); `right` puede traer distractores; cada `left` tiene exactamente una pareja correcta | `izquierda[]`, `derecha[]` con `{ref, texto, **tramos, media_ref, url, texto_alternativo**}` |
| `ordering` | `items` son `ChoiceItem`; «siempre barajados antes de mostrar, el orden del archivo no significa nada» | `elementos[]` con la misma forma que los ítems |
| `open` | `responseFormat` `text · drawing · audio`, `maxLength`; `rubric` (suma exacta de `points`, `E-OPEN-RUBRIC-POINTS`) y `keywords` (clave) | `formato_respuesta`, `longitud_maxima`, sin cambios |

El visor MAUI (`AulaContenidoView`) pinta los medios del enunciado (la imagen se ve, video/audio/pdf se anuncian con una píldora), las opciones con imagen y los ítems con imagen.

### 3.6 · Reglas del validador que el aula asume

| Código | Regla | Consecuencia para el aula |
|---|---|---|
| `E-MODE-SUBSET` | Los modos de la lección ⊆ los del curso; los del objeto ⊆ los de la lección | Filtrar por `mode=class` es seguro a cualquier nivel |
| `E-MODE-EXAM-ONLY` | Un `exam` sólo puede declarar `modes: ["exam"]` y ningún otro objeto puede estar en modo `exam` | **Con `mode=class` nunca llega un examen** (lo visto en 05 §2.1 es regla, no casualidad) |
| `E-MODE-SIMPLE-OPEN` | Sin preguntas abiertas en modo `simple` (nadie las califica) | Preescolar y modo invitado no producen intentos pendientes |
| `E-EXAM-TOPIC` | Toda pregunta de examen lleva `topicRef` | MOD-010 puede informar por tema |
| `E-EXAM-COUNT`, `E-EXAM-TOPICS`, `W-EXAM-POOL-SMALL`, `W-EXAM-TOLERANCE-ZERO` | Viabilidad del `random_balanced` | MOD-010; el aula sólo muestra los ajustes |
| `E-PLACEHOLDER` | Sin `TODO`, `TBD`, `FIXME`, `lorem ipsum`, `[placeholder]` | No hace falta filtrar en el aula |
| `W-BRAND-TERM` | Sin guion largo `—`; «tablero» → «pantalla» o «eScreen»; «aula virtual» → «aula digital» | Vale también para los textos de OPS y Student: **pendiente** una pasada sobre los rótulos del LMS |

---

## 4 · Lo que un dispositivo de alumno puede recibir: `visible_object`

`validate_course.py` define qué quita la API antes de entregar una pregunta:

| Nivel | Campos que se quitan (por tipo) |
|---|---|
| pregunta | `multiple_choice`: `feedback` · `true_false`: `answer`, `feedback` · `fill_blanks`: `feedback` · `matching`: `pairs`, `wrongPairs`, `feedback` · `ordering`: `correctOrder`, `wrongOrders`, `feedback` · `open`: `modelAnswer`, `rubric`, `incorrectExamples`, **`keywords`**, `feedback` |
| opción | `isCorrect`, `feedback` |
| hueco | `acceptedAnswers`, `wrongAnswers`, **`numericTolerance`** |
| perfil `student` | `teacherNotes` del objeto, de cada lámina o página y de cada pregunta |

| Regla | En el LMS |
|---|---|
| Las claves de un **examen** se quitan siempre, se pida lo que se pida | — |
| `includeActivityKeys=true` conserva las claves de una **actividad con `feedback: immediate`**; con un examen es **403 `answer_keys_forbidden`** | El aula **no lo pide** (prueba: ninguna consulta al host lo lleva). La retroalimentación inmediata se resuelve con `POST /evaluar/` por pregunta (artículo 14) |
| `CLAVES_DE_CORRECCION` (el barrido de segunda línea del aula) | Ahora incluye `keywords` y `numericTolerance` (y `placements`/`wrongPlacements` de §6.1). Una prueba lee las constantes `ANSWER_KEY_*` del validador con `ast` y comprueba que **todas** están en el conjunto del aula: si la biblioteca añade una, la prueba avisa |
| El host de pruebas | `objeto_visible()` y `leccion_visible()` calcados de `visible_object`; con `jsonschema` instalado se comprueba la **paridad** sobre los 8 objetos de `example.json` × 2 perfiles × con y sin claves de actividad |

---

## 5 · La corrección de referencia: `evaluate_response`

| Tipo | Ratio | Retroalimentación específica | Crédito parcial (`partialCredit`) |
|---|---|---|---|
| `true_false` | `value is answer` | — | no aplica |
| `multiple_choice` | conjunto elegido == conjunto correcto | `feedback` de cada opción **incorrecta elegida** | **sólo con `allowMultiple`**: `max(0, (aciertos − fallos) / correctas)` |
| `fill_blanks` | huecos acertados / huecos | `feedback` del `wrongAnswer` que coincide (normalizado) | acertados / total; sin él, todo o nada |
| `matching` | parejas dadas == correctas | `feedback` de cada `wrongPair` presente | correctas dadas / correctas |
| `ordering` | orden == `correctOrder` | `feedback` del `wrongOrder` igual al dado | posiciones acertadas / total |
| `open` | — | ninguna | `score: null`, `correct: null`, `requiresManualGrading: true`, `feedback: []` |

Normalización de `fill_blanks`: espacios colapsados; `caseSensitive` (falso por defecto) e `ignoreAccents` (verdadero por defecto) del hueco; en `numeric` se admite **coma decimal** y `|respuesta − aceptada| ≤ numericTolerance`.

Resultado: `score = round(points × ratio, 4)`, **`correct = ratio == 1.0`** (booleano, nunca nulo en las automáticas), y `feedback` con la **general primero** (`feedback.correct` o `.incorrect`) seguida de las específicas.

Lo que cambia para el aula y sus clientes:

| Antes (host y pruebas) | Ahora (referencia) | Efecto |
|---|---|---|
| `correcta: null` en crédito parcial | `correcta: false` con `puntaje > 0` | Igual que la API real del 21-09. `veredicto()` ya lo admitía; cambiaron dos expectativas de prueba |
| retroalimentación específica y luego la general | **general primero** | `retroalimentacion[0]` se puede mostrar como titular y el resto como detalle |
| crédito parcial en opción múltiple sin exigir `allowMultiple` | exige `allowMultiple` | Una pregunta de una sola respuesta es todo o nada |
| numérico sin tolerancia ni coma | tolerancia y coma | `"0,0"` es correcto para `0` |

Ejemplos con `example.json` (host de pruebas, misma salida que `evaluate_response`):

| Pregunta | Respuesta | `puntaje` / `puntaje_maximo` | `correcta` | `retroalimentacion` |
|---|---|---|---|---|
| `l1-act-q3` (completar, parcial) | `b1: propio`, `b2: masa` | 1.0 / 2.0 | `false` | «Piensa en el agua pasando de un vaso a una botella.», «La masa no cambia al cambiar de recipiente.» |
| `l1-act-q4` (relacionar, parcial) | 2 de 3 + `gas → none` | 2.0 / 3.0 | `false` | «Recuerda los tres recipientes de la cátedra.», «Los gases sí tienen partículas, solo que muy separadas.» |
| `l2-act-q3` (numérico) | `"0,0"` | 1.0 / 1.0 | `true` | «Correcto.» |
| `l2-act-q3` | `"100"` | 0.0 / 1.0 | `false` | «Piensa en el hielo, no en el agua hirviendo.», «100 °C es la ebullición a nivel del mar.» |
| `l1-act-q6` (abierta) | texto | `null` / 4.0 | `null` | `[]`, `pendiente: true` |

---

## 6 · Hallazgo en vivo · AVACOM Contenido 2.1.7 (2026-09-28)

Mientras se hacía este trabajo, en el equipo estaba encendida una app «AVACOM Contenido» **2.1.7** (`/v2/health` publica ahora `appVersion`). Lo que dice difiere de los archivos entregados.

### 6.1 · El contrato instalado es más nuevo que el entregado

`GET /v2/openapi.json` de la app frente al `openapi.v2.json` entregado (copia en [`openapi.v2.instalado-2.1.7.json`](openapi.v2.instalado-2.1.7.json)):

| Cambio | Detalle | Efecto en el aula |
|---|---|---|
| Rutas nuevas | `GET /v2/packages[?deep]` y `GET /v2/packages/{courseId}`: integridad de cada paquete (`status: ok · broken · missing`, `problems[{code: E-PKG-…, message}]`) · `GET /v2/curriculum` y `GET /v2/curriculum/{nodeId}/content?descendants`: catálogo curricular y contenido anclado a un nodo | Ninguno hoy; `packages` explica los 500 de §6.2 |
| Ruta retirada | `GET /v2/policies` → 404 `not_found` | Ninguno (el aula no la usaba) |
| Parámetro nuevo `version` | En `courses/{id}`, `lessons/{lid}`, `objects/{oid}`, `exams/{oid}/pool` y `…/questions`: «una versión archivada se sirve mientras dure su retención, para que una clase que empezó antes de una actualización siga leyendo lo que empezó» | **Cambia 05 §2.2**: el aula podría dejar de rechazar `?version=` distinta de la instalada. Pendiente (Q-55) |
| `Health.appVersion` | Build de la app (`2.1.7`) | `version_app` en `GET /api/aula/fuente/` |
| `Classification.track` | `school` (por defecto) o `complementary` (idiomas, artes: los cuatro niveles guardan área, asignatura, nivel de dominio y tema) | `clasificacion.pista` |
| Error nuevo | **500 `package_invalid`** «Installed package failed verification: E-PKG-COURSE» en curso, lección, objeto, medios y `evaluate` de un paquete roto; `/v2/courses` **sí lo lista** | §6.3 |

El esquema con el que la app valida (incrustado en `Avacom.Content.Core.dll`, copia en [`course.schema.instalado-2.1.7.json`](course.schema.instalado-2.1.7.json)) tiene el **mismo `$id` y `schemaVersion` 1.0** que el entregado, pero no es el mismo:

| Parte | Entregado | Instalado 2.1.7 | Aula |
|---|---|---|---|
| Tipos de pregunta | 6 | **7**: `drag_drop` (`items` que se arrastran a `targets` con `label` o `mediaId`; `placements` y `wrongPlacements` son la clave) | `componente: no_soportado`, se muestra; `placements`/`wrongPlacements` añadidos a las claves que nunca salen |
| `QuestionBase.points` | obligatorio | opcional: las preguntas de **actividad** lo exigen y las de **examen** lo prohíben («cada pregunta sorteada pesa lo mismo») | `puntos` puede ser `null` en un examen (no se muestra) |
| `ExamObject.settings` | `selection.difficultyTolerancePct`, `timeTolerancePct`; `timeLimit.policy` + `fixedSec`/`extraPct`; `passingScorePct` obligatorio | `difficultyTolerancePercent`, `timeTolerancePercent`; `timeLimit` con **uno solo** de `fixedSec` o `extraPercent` (sin `policy`); sin `passingScorePct` | El normalizador acepta **ambos nombres** y deriva `politica` (`fixed`, `sum_of_estimates`, `none`) |
| Curso | — | `curriculumNodes[{id, name, parent, type}]` (las habilidades que trabaja), `previousTopics[]` | Ignorados (conjunto abierto) |
| `CurriculumRef` | `framework`, `code`, `description` | + `relation: teaches · assesses` | `referencias_curriculares[].relacion` |
| `Media` | — | + `hasSpeech` (audio/video con habla exigen subtítulos y transcripción), `posterPath` | `tiene_voz` |
| Descripciones | escuetas | extensas, con la intención de cada campo | — |

### 6.2 · Los paquetes instalados no pasan la verificación

`GET /v2/packages` a las 15:46:

| Paquete | Estado | Problemas |
|---|---|---|
| `avacom.co.lower-secondary.6.science.states-of-matter@2.0.0` | **broken** | `E-PKG-COURSE`, 23 errores `E-SCHEMA`: `difficultyTolerancePct`/`timeTolerancePct` no admitidos y `…Percent` obligatorios; `timeLimit.policy` y `extraPct` no admitidos; `passingScorePct` no admitido; las 12 preguntas del examen declaran `points` |
| `avacom.co.primary.4.math.fractions.intro@1.2.0` | **broken** | `E-PKG-COURSE`, 17 errores de la misma familia |
| `avacom.co.preschool.transicion.language.vowels@1.0.0` | ok | — |
| `avacom.us.middle-school.8.social-studies.us-constitution@1.0.0` | **broken** | `E-PKG-COURSE`, 10 errores (`timeLimit.policy`, `passingScorePct`, `points` en examen) |

Es decir: los paquetes se publicaron con el esquema **entregado** (el que valida `example.json` sin errores) y la app 2.1.7 los rechaza con el suyo. Entre las 15:55 y las 15:58 la app se reinició dos veces y la lista quedó vacía: los paquetes se estaban reinstalando cuando se cerró este documento, así que la cadena completa contra 2.1.7 quedó verificada con el host de pruebas (§8) y sólo el estado de la fuente en vivo.

### 6.3 · Cómo degrada el aula ahora

| Situación | Antes | Ahora |
|---|---|---|
| Un paquete roto en la lista | `GET /api/aula/cursos/` → **502** para toda la lista (un curso roto dejaba sin panel al docente) | La ficha **se conserva, marcada**: `no_disponible: {codigo: paquete_invalido, detalle, codigo_biblioteca: package_invalid, sugerencia}`, con clasificación y título (viene de `/v2/courses`) y `lecciones: 0`, `portada_url: null`. Los demás cursos siguen |
| Abrir, evaluar o pedir un medio del paquete roto | 502 `fuente_error` genérico | **502 `paquete_invalido`** con `codigo_biblioteca: package_invalid`, `estado_biblioteca: 500`, `curso_ref` y `sugerencia` («reinstálalo o pide a la biblioteca una versión publicada con el esquema vigente») |
| OPS · «Clase de hoy» | La tarjeta abría y fallaba | La tarjeta se ve **atenuada con acento ámbar** y el detalle «No disponible · el paquete no pasa la verificación de AVACOM Contenido»; al tocarla, una alerta de un toque con la sugerencia |
| `GET /api/aula/fuente/` | `contrato`, `puertos`, `huella`, cursos | + `esquema` («1.0») y `version_app` («2.1.7»): para saber con qué build se habla antes de culpar al contenido |

### 6.4 · Preguntas para el equipo de Biblioteca

| # | Pregunta | Por qué importa |
|---|---|---|
| Q-55 | ¿Cuál es el esquema vigente: el `course.schema.json` entregado o el que trae la app 2.1.7? ¿Se va a subir `schemaVersion` (hoy los dos dicen `1.0` con cambios incompatibles en `ExamObject.settings` y `points`)? | El aula acepta ambos, pero `/v2/health.schema` debería distinguirlos |
| Q-56 | `version` en `courses/{id}`, `lessons` y `objects`: ¿retención por defecto? ¿Se sirve el esquema con `mode`/`profile` igual que la instalada? | Permitiría que una clase abierta antes de una actualización siga leyendo su versión (05 §2.2 y `m07_sesion.curso_version`) |
| Q-57 | `drag_drop`: forma de `response` en `/v2/evaluate` (¿`{placements: [{itemId, targetId}]}`?) y qué devuelve `visible_object` de los `targets` | Sin eso el aula lo muestra como `no_soportado` y reenvía la respuesta tal cual |
| Q-58 | ¿Va a haber un `validate_course.py` para el esquema 2.1.7 (con `drag_drop` en `ANSWER_KEY_FIELDS` y `evaluate_response`)? | El host de pruebas se calca del validador; sin él, la paridad se queda en 6 tipos |
| Q-59 | `docs/EJEMPLOS-API-LMS.md`, citado en cada respuesta del `openapi` 2.1.7, no llegó | Cargas reales de cada ruta para las pruebas |
| Q-60 | `hasSpeech` y `posterPath`: ¿la API publicará `hasPoster` o la URL del póster en la sesión de medios? | El catálogo de OPS podría mostrar la miniatura del video |

---

## 7 · Lo que cambió en el código

| Capa | Archivo | Cambio |
|---|---|---|
| Referencia | `spec-driven/02-classroom-engine/course.schema.json`, `validate_course.py` | **Nuevos**, copias de lo entregado, junto a `openapi.v2.json` y `example.json` |
| Referencia | `…/openapi.v2.instalado-2.1.7.json`, `…/course.schema.instalado-2.1.7.json` | **Nuevos**, lo que publica y con lo que valida la app instalada hoy (§6.1) |
| Aula · dominio | `classroom_engine/dominio/catalogos.py` | `CLAVES_DE_CORRECCION` + `keywords`, `numericTolerance`, `placements`, `wrongPlacements` |
| Aula · dominio | `classroom_engine/dominio/curso.py` | `tramos()` con `*cursiva*` y `$matemática$` (cuatro claves por tramo); `_pregunta(p, medios, url_medio)`: `medios[]`, opciones e ítems con `media_ref`/`url`/`texto_alternativo` y `tramos`, `referencias_curriculares`; `_referencias()` común (con `relacion`); `puntos_totales` decimal (`_decimal`); `tiempo_limite_seg`, `fijo_seg`, `duracion_seg` de página, `instrucciones_tramos` de actividad; ajustes de examen con los dos nombres y `politica` derivada; `clasificacion.pista`; `tiene_voz`; `no_disponible` en el resumen |
| Aula · dominio | `classroom_engine/dominio/errores.py` | **`PaqueteInvalido`** (502 `paquete_invalido`) |
| Aula · infraestructura | `classroom_engine/infraestructura/fuente_biblioteca.py` | `package_invalid` → `PaqueteInvalido` con `SUGERENCIA_PAQUETE`; en la lista, la ficha rota se conserva marcada |
| Biblioteca (cliente) | `biblioteca/contenido_v2.py` | `estado()` con `esquema` y `version_app` |
| Pruebas · host | `tools/host_contenido_v2_pruebas.py` | `objeto_visible`/`leccion_visible` (= `visible_object`), `calificar` (= `evaluate_response`), `includeActivityKeys` y 403 `answer_keys_forbidden`, `invalidos` → 500 `package_invalid`, `appVersion` en `health` |
| Pruebas | `classroom_engine/tests/test_contrato_v2.py` | **Nuevo** (20): esquema y catálogos, claves del validador ⊆ claves del aula, `example.json` válido, paridad de recorte y de corrección con el validador (3 pruebas que exigen `jsonschema`), reglas de corrección sin `jsonschema`, normalizador según el esquema (medios, opciones con imagen, decimales, tiempos, 2.1.7), el aula nunca pide claves, el host entiende `includeActivityKeys`, estado con `esquema`/`version_app`, paquete inválido (lista marcada, 502) |
| Pruebas | `classroom_engine/tests/test_curso.py` | Tramos con cuatro claves, cursiva y matemática; `ajustes.tiempo_limite_seg`; `medios`/`media_ref` en preguntas; crédito parcial con `correcta: false` y retroalimentación general primero; numérico con coma |
| MAUI · núcleo | `Avacom.Lms.Core/Models/AulaModels.cs` | `Tramo(Cursiva, Matematica)`; `OpcionAula` y `ElementoAula` con `MediaRef`, `Url`, `TextoAlternativo` (+ `Tramos` en ítems); `PreguntaAula.Medios`, `Puntos` `double?`; `ObjetoAula.PuntosTotales` `double?`; `AjustesActividad.TiempoLimiteSeg`; `FichaCurso.NoDisponible` (`NoDisponibleAula`) y `Detalle` |
| MAUI · Ui | `Design/Ds.cs` | `Formateado()` aplica itálica a `cursiva` y `matematica` |
| MAUI · Ui | `Controls/AulaContenidoView.cs` | Medios del enunciado (imagen visible, resto como píldora), opciones e ítems con imagen (`ImagenDeMedio`, `TextoOImagen`, `Item`) |
| MAUI · OPS | `Pages/ClaseHoyPage.xaml.cs` | Tarjeta atenuada y alerta para un curso `no_disponible` |
| MAUI · pruebas | `Avacom.Lms.Core.Tests/AulaApiTests.cs` | La vista con tramos de cursiva y matemática, puntos decimales, medios y opción con imagen |
| Docs | `01-modelo-de-datos.md`, `05-contrato-biblioteca.md`, `README.md` | Tramos con cuatro claves; «Continúa en 06»; índice |

---

## 8 · Cómo se probó

**El validador sobre el ejemplo** (con `jsonschema` instalado en una carpeta aparte, no en el `.venv` del backend):

```
python spec-driven/02-classroom-engine/validate_course.py spec-driven/02-classroom-engine/example.json
→ 0 errors, 0 warnings
```

**Backend** (`backend\.venv\Scripts\python manage.py test`): **219** pruebas en verde, 104 de `classroom_engine` + `biblioteca`. Las tres de paridad con el validador se ejecutan sólo si `jsonschema` está disponible:

```
set PYTHONPATH=<carpeta con jsonschema>
backend\.venv\Scripts\python manage.py test classroom_engine.tests.test_contrato_v2
→ Ran 20 tests · OK          (sin jsonschema: OK (skipped=3))
```

| Suite | Pruebas | Qué comprueba |
|---|---|---|
| `test_contrato_v2 · EsquemaYValidadorTests` (5) | Los archivos están junto al `openapi`; los `enum` del esquema son los catálogos del aula; `ANSWER_KEY_*` ⊆ `CLAVES_DE_CORRECCION`; `example.json` válido (estructura y semántica, sin avisos); **paridad** de `objeto_visible` con `visible_object` (8 objetos × 2 perfiles × 2) y de `calificar` con `evaluate_response` (21 respuestas de los seis tipos, con crédito parcial, coma decimal, acentos, parejas y órdenes equivocados) |
| `test_contrato_v2 · RecorteYCorreccionDelHostTests` (6) | `correct` booleano y general primero; opción múltiple parcial sólo con `allowMultiple` (y castigo por fallo); normalización de completar y tolerancia numérica; ordenar por posiciones; abierta sin nota; recorte por tipo y perfil, `includeActivityKeys` y examen |
| `test_contrato_v2 · NormalizadorSegunElEsquemaTests` (5) | Medios en la pregunta, opciones e ítems con imagen, tramos con cursiva y matemática, `puntos` decimal, `tiempo_limite_seg`, `fijo_seg`, `duracion_seg`; el esquema 2.1.7 (`…Percent`, `timeLimit` sin `policy`, `drag_drop`, `relation`, `track`, `hasSpeech`); `sin_claves` con `keywords` y `numericTolerance` |
| `test_contrato_v2 · ElAulaNuncaPideLasClavesTests` (3) | Ninguna consulta lleva `includeActivityKeys`; el host lo entiende como el contrato (200 con claves en una actividad inmediata, 403 con examen); `fuente/` con `esquema` y `version_app` |
| `test_contrato_v2 · PaqueteInvalidoTests` (2) | Con un paquete roto la lista conserva la ficha marcada y agrupa igual; abrir, evaluar o pedir un medio es 502 `paquete_invalido` con sugerencia; el curso sano no se ve afectado |
| `test_curso` (ajustadas) | Tramos, ajustes, medios en preguntas, `puntos_totales` 13.0, crédito parcial `false` y orden de la retroalimentación, numérico con coma |

**MAUI**: `dotnet test tests/Avacom.Lms.Core.Tests` → 16 en verde; `dotnet build src/Avacom.Lms.Ui … -f net10.0-windows10.0.19041.0` → 0 avisos; OPS compilada a una carpeta aparte (la instancia del usuario estaba abierta).

**En vivo** (app 2.1.7, 15:44–15:58): `GET /api/aula/fuente/` → `disponible: true, contrato: 2, esquema: "1.0", version_app: "2.1.7"` (tres arranques, tres puertos, sin reiniciar el backend); `/v2/packages` como en §6.2; curso, lección y `evaluate` de un paquete roto → 500 `package_invalid` → antes de este cambio 502 `fuente_error` para toda la lista; al cerrar, la lista estaba vacía (reinstalación en curso) y el panel respondió 200 sin cursos y sin error.

---

## 9 · Lista de verificación

| | Estado |
|---|---|
| `openapi.v2.json` entregado = copia del repo (rutas, puertos al azar, token, medios, errores) | ✅ `diff` vacío |
| `example.json` cumple `course.schema.json` y `validate_course.py` | ✅ 0 errores, 0 avisos |
| Los `enum` cerrados del esquema coinciden con los catálogos del aula | ✅ prueba |
| Todas las claves que `visible_object` quita están en `CLAVES_DE_CORRECCION` | ✅ prueba (leídas del validador) |
| El host de pruebas recorta y califica como el validador | ✅ paridad probada |
| `correct` booleano, `feedback[0]` general | ✅ host, pruebas y documento |
| `RichText` completo en `tramos` (negrita, cursiva, matemática) | ✅ backend y MAUI |
| `mediaIds`, opciones e ítems con imagen | ✅ backend y MAUI |
| `points` decimal en backend y C# | ✅ |
| `includeActivityKeys` nunca viaja | ✅ prueba |
| Identificadores del esquema caben en las columnas del expediente | ✅ 120 ≤ 120/200 |
| Paquete roto: lista marcada, 502 `paquete_invalido`, tarjeta atenuada en OPS | ✅ host y OPS; en vivo, pendiente de que los paquetes se reinstalen |
| Ajustes de examen con los dos nombres (entregado y 2.1.7) | ✅ |
| `drag_drop` | ⚠️ se muestra como `no_soportado`; corrección y forma de respuesta por confirmar (Q-57) |
| `version` en curso, lección y objeto (2.1.7) | ⚠️ no se usa todavía (Q-56) |
| Términos de marca (`W-BRAND-TERM`) en los rótulos del LMS | ⚠️ pendiente |

---

## 10 · Lo que queda fuera y dónde sigue

| Qué | Dueño | Nota |
|---|---|---|
| Decidir el esquema vigente y subir `schemaVersion` (Q-55) | Biblioteca | Hasta entonces el aula acepta los dos |
| Servir versiones archivadas con `?version=` (Q-56) | Backend MOD-007 | Cambia 05 §2.2; `m07_sesion.curso_version` ya está guardada para pedirla |
| Visor y respuesta de `drag_drop` (Q-57) | Frontend + backend MOD-007 | Hoy `no_soportado`; `validar_respuesta` reenvía tal cual |
| Abrir desde la tableta un video, audio o pdf adjunto a una pregunta | Frontend MOD-007 | El visor los anuncia con una píldora; la imagen sí se ve |
| Inter Italic empaquetada | Design system | Hoy itálica sintética para `cursiva` y `matematica` |
| Mostrar `curriculumNodes`, `relation` y `/v2/curriculum` (informe por habilidad) | MOD-012 | La vista ya lleva `relacion` en `referencias_curriculares` |
| Pasada de `W-BRAND-TERM` sobre los rótulos de OPS y Student | Frontend | «tablero» → «pantalla», sin guion largo |
| `jsonschema` en el `.venv` | — | No se añade a `requirements.txt`: el LMS no valida cursos; las pruebas de paridad se omiten sin él |
---

## 11 · Contrato del 2026-10-07: lecciones en html, pausas de video, póster y `drag_drop`

Gabriel entregó el 2026-10-07 `openapi.v2 (3).json`, `course.schema (3).json` y `mensajes.es.json` (los mensajes en español del validador y del instalador de paquetes). Copias en esta carpeta: `openapi.v2.json`, `course.schema.json` (sustituyen a las del 2026-09-28; las de la app 2.1.7 siguen en `*.instalado-2.1.7.json`) y `mensajes.es.json`. `validate_course (2).py` (2026-10-01) es byte a byte el del 2026-09-28: el validador **no** conoce todavía `drag_drop` ni `html`.

### 11.1 Qué cambia frente a lo que la app 2.1.7 publica

| Cambio | Dónde | Qué hace el aula |
|---|---|---|
| Medio de clase **`html`** (carpeta con páginas, estilos y fuentes; `entry` obligatorio). Dentro de una página, otro medio se nombra `../{mediaId}`, sus subtítulos `../{mediaId}/@captions`, el póster `../{mediaId}/@poster` | `Media.kind` | `clase: "html"`, `componente: "html"`, `url` = su página de entrada, `base_url`, `entrada`. Las rutas relativas se sirven: ruta de medios **sin barra final** (`/medios/{ref}`), `@captions`/`@transcript`/`@poster` en `abrir_medio`. Con sesión obligatoria heredan el pase del camino (bugfix 01) |
| **`html {mediaId, entry}`** en cátedra y explicación: la misma lámina o página maquetada por el curso; sección n = `entry#s{n}` | `LectureObject`, `ExplanationObject` | El objeto trae `html {media_ref, entrada, url, base_url, ausente}` y cada lámina o página `url_html` = `url#s{n}`. Los bloques se entregan siempre (respaldo, búsqueda, accesibilidad). OPS y Student cargan `url_html` en una WebView acotada al nodo y cambian de lámina cambiando sólo el `#s{n}` |
| **`interactions`** en un video: hasta 6 pausas para pensar (`atSec`, `prompt`, 2-4 opciones con `isCorrect` y `feedback`, `teacherTip`) | `Media` | `pausas [{pausa_ref, en_seg, enunciado, opciones [{opcion_ref, texto, es_respuesta, explicacion}], consejo_docente}]` en el medio y en cada bloque de video. Es formativo: la respuesta y su razón viajan a propósito (el contrato manda mostrarlas al elegir); `consejo_docente` sólo con rol docente. El reproductor del aula se detiene en `en_seg`, pregunta, muestra la explicación y sigue |
| **`posterPath`** en video; `extras[mediaId].poster` en la sesión de medios | `Media`, `MediaSession` | `poster_url` (`/medios/{ref}/poster`) en el medio y en el bloque, **siempre**: el resumen de medios del `CourseOutline` no lista `posterPath`, así que el nodo no sabe de antemano si hay; la ruta responde 404 cuando no viene y el reproductor lo ignora. Pregunta abierta para Biblioteca: ¿`media[]` del curso reenvía `posterPath` e `interactions`, o sólo la sesión de medios? |
| **`drag_drop`**, séptimo tipo de pregunta (`DragDropQuestion`, `DragTarget`) | `Question.type` | `componente: "arrastrar"`, `elementos` (piezas, `ChoiceItem`) y `zonas` (`DragTarget`: rótulo o imagen). `validar_respuesta` exige `placements [{itemId, targetId}]` con referencias de la pregunta y una pieza en una zona como mucho (las distractoras pueden quedarse fuera). Tableta: `EditorArrastrar` (tocar pieza → tocar zona); OPS: vista previa con bandeja y zonas. Claves `placements`/`wrongPlacements` ya estaban en `CLAVES_DE_CORRECCION` |
| Clasificación con **`track`** (`school`/`complementary`), **`area`** y `subject.order`; `level`/`grade` sólo obligatorios en la pista escolar | `Classification` | Sin cambio en el aula: `pista` ya se normalizaba y `area` se ignora (ningún curso instalado la usa). Pendiente si llega un curso complementario (idiomas, artes) |
| Examen: desaparecen `difficultyTolerancePercent`, `timeTolerancePercent` y `timeLimit.extraPercent`; `coverAllTopics` obligatorio con `random_balanced`; `timeLimit` sólo `fixedSec` | `ExamObject.settings` | MOD-010 ya leía estos campos con `.get` y arma con tolerancia 100 % cuando faltan (`armado.py`): sin cambio de código. Un examen sin `timeLimit` queda sin límite salvo que el profesor lo fije al asignar |
| `GET /v2/curriculum?country=` y `Classification.area` en la API | `openapi` | El aula no consume `/v2/curriculum` |

### 11.2 Lo que NO trae todavía la Contenido instalada (2.1.7, 7 cursos)

**Este equipo no tiene la Contenido nueva** (Gabriel, 2026-10-07): la 2.1.7 instalada sirve 7 cursos sin medios `html`, objetos con `html`, `interactions` ni `posterPath`, y lo que publica no prueba el contrato 2; la guía son los tres documentos entregados. Todo lo de 11.1 se probó con la API de Contenido de pruebas (`classroom_engine/tests/test_contrato_html.py`, 8 pruebas): manifiesto de ejemplo + cátedra 1 maquetada en html que nombra `../vid-changes`, `../vid-changes/@captions`, `../vid-changes/@poster` y `estilos.css`, y el video con póster y una pausa. **Falta la prueba con un paquete real de Contenido que traiga html**: en cuanto exista uno instalado, repetir ESC-01-02 con él.

### 11.3 Sesiones de medios reutilizadas (para 35 tabletas)

Medido el 2026-10-07 contra la Contenido real: `POST /v2/media-sessions` cuesta 43 ms (mediana; p90 54 ms) y un trozo de 64 KiB 5 ms. Hasta hoy el nodo abría una sesión de un minuto por **cada** petición de bytes, y un `<video>` pide varios trozos (`Range`). Ahora `biblioteca/contenido_v2.abrir_medio` reutiliza una sesión por (curso, medio, servidor de medios, token) durante 15 min (`AVACOM_CONTENIDO_SESION_MEDIOS_SEG`; `0` = como antes), con margen de un minuto, y si Contenido la olvida (reinicio, revocación: `media_session_not_found`) abre otra una sola vez. Lo guardado es sólo la URL-capacidad que Contenido emitió con ese fin; ni el curso ni el token se guardan. `link.json` se sigue releyendo en cada petición.

### 11.4 Archivos tocados

`classroom_engine/dominio/catalogos.py` (`html`, `drag_drop`), `classroom_engine/dominio/curso.py` (`_medio` con `rol`, `_pausas`, `_html_de_objeto`, `url_html`, `poster_url`), `classroom_engine/interfaces/urls.py` y `modo_estudio/interfaces/urls.py` (ruta de medio sin barra final), `biblioteca/contenido_v2.py` (`@captions`/`@transcript`/`@poster`, sesiones reutilizadas), `tools/host_contenido_v2_pruebas.py` (html por `entry`, `extras.poster`), `avacom_lms/settings.py` (`AVACOM_CONTENIDO_SESION_MEDIOS_SEG`); clientes: `Avacom.Lms.Core/Models/AulaModels.cs` (`HtmlAula`, `PausaAula`, `UrlHtml`, `PosterUrl`, `TieneHtml`), `Avacom.Lms.Ui/Controls/AulaContenidoView.cs` (`MostrarHtml`, pausas y póster en el reproductor, opciones marcables en la vista previa de una actividad). La capa de biblioteca se tocó desde el propio módulo de biblioteca y el normalizador desde el aula, que son sus dueños; ningún otro módulo entra en ellos.
