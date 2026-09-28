# 01 · Classroom Engine · Modelo de datos y API

| Campo | Valor |
|---|---|
| Módulo | app `classroom_engine` · **MOD-007 · Classroom Engine** del Documento Maestro (DOM-004 · Operación del Aula) |
| Estado | **Implementado y probado** en `backend/classroom_engine/`: 10 tablas `m07_*` (migración `0001_initial`), consumo del curso en vivo, endpoint de prueba con `example.json` y ciclo de vida completo de la sesión de clase. 43 pruebas nuevas; la suite completa del backend (161) en verde. Pendiente: canal en vivo (§9.6) y lo listado en §12 |
| Prefijo de tablas | `m07_` (CV-01) · 10 tablas · ninguna de curso |
| Plataforma | Python 3.12 · Django 5.2.3 · DRF 3.16.1 · SQLite · arquitectura hexagonal (misma disposición que `acceso/`) |
| Cliente | .NET MAUI: AVACOM LMS OPS (Windows, pantalla táctil **sin teclado**) y AVACOM LMS Student (Windows y Android) |
| Fuentes y prioridad | 1 · restricciones de [00 · Introducción](00-introduccion.md) · 2 · [01 · Constitución](../01-constitucion.md) · 3 · [00 · Línea base](../00-linea-base-conexion-biblioteca.md) · 4 · [06 · Contrato biblioteca](../06-contrato-biblioteca.md) (propuesta) · 5 · MOD-007 del Maestro · 6 · Arquitectura y Datos, Parte XI · 7 · [`example.json`](example.json), orientativo |
| Documentos hermanos | [02 · Sugerencias para el frontend MAUI](02-sugerencias-frontend.md) · [Modelado del acceso](../01-acceso/01-modelado-datos.md) (MOD-001, del que este módulo lee) · [Device Manager](../03-device-manager/00-modelo-y-api.md) (MOD-009, del que este módulo lee y al que pide) |
| Actualización 2026-09-28 | Segunda versión del modelo de datos aplicada al aula (migración `0002_selector_lanzamiento_dispositivos`): **`Foco` pasa a llamarse `Selector`** (`m07_selector`, `POST …/selector/`, clave `selector` en las respuestas, `selectores` en el resumen); la distribución es el **lanzamiento** (`alcance`, `destinatarios`, `excluidos_bloqueados`, `intentos_permitidos`, `tiempo_limite_seg`); el participante referencia su tableta y su sesión de alumno en MOD-009 (`dispositivo_id`, `dim_sesion_alumno_id`), que resuelve el puerto `Dispositivos`: una tableta bloqueada no entra (403 `dispositivo_bloqueado`) ni recibe lanzamientos. 199 pruebas en verde en el backend |

---

## 0 · Resumen ejecutivo

1. **Regla de oro.** Los cursos viven en AVACOM Biblioteca. **Ninguna tabla del LMS guarda una asignatura, un curso, una lección, un objeto, una lámina, un bloque, un medio, una pregunta ni una opción.** MOD-007 guarda lo que ocurre en el aula y, del curso, sólo referencias (`*_ref`, CV-08) y rótulos como evidencia histórica (`*_rotulo`, artículo 13.3). Una prueba de esquema lo comprueba (§11).
2. **El curso se lee en vivo y se normaliza.** El manifiesto de curso (`schemaVersion` 1.0: `media`, `lessons`, `objects`, `blocks`, `questions`) se convierte en cada petición en una **vista de aula** con la misma forma para OPS y Student. La misma función acepta el árbol del contrato 1 (`secciones/items`), así que el LMS no cambia cuando la biblioteca cambie de esquema.
3. **Dos fuentes, un puerto.** `FuenteDeCursos` tiene dos adaptadores: `biblioteca` (el cliente único del LMS) y `ejemplo` (lee `example.json` del disco, sin cachear ni guardar). El endpoint de prueba usa el segundo; el resto del módulo no distingue uno del otro.
4. **Tres catálogos, no una lista plana.** Primero *qué experiencia* es el objeto (`lecture`, `explanation`, `simulation_lab`, `activity`, `exam`), después *qué contenido* pinta cada bloque (`heading`, `text`, `list`, `image`, `video`, `audio`, `pdf`) y, dentro de una actividad, *qué pregunta* (`multiple_choice`, `true_false`, `fill_blanks`, `matching`, `ordering`, `open`). Cada uno lleva `componente`: el nombre del control MAUI que lo representa.
5. **Ninguna clave de corrección sale del backend, para ningún rol.** `isCorrect`, `answer`, `acceptedAnswers`, `pairs`, `correctOrder`, `modelAnswer`, `rubric`, `feedback`… se eliminan por construcción y por un barrido recursivo final (artículo 14.5). Las notas del docente sólo salen con rol `docente`.
6. **El examen no lo ejecuta el aula.** El objeto `exam` se muestra en la estructura como `fuera_de_alcance` con `modulo: MOD-010`, sin preguntas. El aula proyecta, lanza actividades y sigue el grupo; el intento es de MOD-010.
7. **La sesión de clase es lo que MOD-007 posee**: `m07_sesion` (estados `planificada → abierta ⇄ suspendida → cerrada → archivada`, INV-025), `m07_participante` con su bitácora `m07_presencia`, el **selector** como bitácora con un solo vigente (`m07_selector`), los **controles** de seguimiento y bloqueo como periodos (`m07_control`), las **distribuciones** con avance de entrega, los **avisos**, el **resumen** de cierre y la **cola de salida** `aula.*.v1`.
8. **Las invariantes son índices** (CV-07): un código de unión por sesión activa, una sesión activa por grupo (DEC-035), una sesión *abierta* por profesor (BR-045), una participación por persona y sesión (FUN-077), un selector vigente por sesión, un control abierto por tipo, una entrega por participante y distribución.
9. **Las cuatro vías producen la misma sesión** (BR-044): `arbol`, `leccion`, `recurso` y `libre`. Por defecto los alumnos **siguen** al profesor (BR-050) y el cambio de selector se valida contra el curso vigente antes de propagarse (BR-049).
10. **Todo lo que otro módulo aporta entra por un puerto**: biblioteca (curso), identidad y padrón (MOD-001/002), evaluación (MOD-010), reloj (MOD-015, BR-062), auditoría (MOD-019) y cola de salida. Los once permisos `classroom.*` se nombran aquí y los siembra MOD-001 (§12).

---

## 1 · La regla de oro y lo que sigue de ella

> Los cursos provienen de AVACOM Biblioteca y no están en el LMS. Ninguna tabla de la materia (asignatura o curso) se guarda en el LMS.

| Dato | Dónde vive | Qué guarda MOD-007 |
|---|---|---|
| Asignatura, nivel, grado, país, idioma (`classification`) | Biblioteca (manifiesto) | Nada. El panel «Asignaturas» se calcula en vivo agrupando por `subject` |
| Curso, versión, título, créditos, portada | Biblioteca | `curso_ref`, `curso_version` y `curso_rotulo` en la sesión y en el selector |
| Lección, objetivos, temas | Biblioteca | `leccion_ref` y `leccion_rotulo` |
| Objeto (presentación, lectura, laboratorio, actividad, examen) | Biblioteca | `objeto_ref`, `objeto_tipo` y rótulo en el selector y en la distribución |
| Lámina, página, pregunta (la «unidad» que se proyecta) | Biblioteca | `unidad_ref` y `unidad_indice` en el selector |
| Medios (imagen, video, audio, pdf, simulación) | Biblioteca | `media_ref` cuando se proyecta un medio suelto |
| Preguntas, opciones, claves, rúbricas | Biblioteca | **Nada.** Ni siquiera transitan hacia el cliente (§2.5) |
| Quién está en clase, qué se proyectó, qué se lanzó, qué se avisó, cómo terminó | **LMS · MOD-007** | Las 10 tablas `m07_*` |

Consecuencias verificables:

- **Ninguna FK hacia contenido** (CV-08): toda referencia es texto. Cambiar la versión del curso en la biblioteca cambia lo que ven las tabletas sin ninguna operación en el LMS (artículo 14.3).
- **La fuente de ejemplo no es una caché.** Lee `example.json` del disco en cada petición, igual que el cliente relee `enlace.json`. No existe ninguna tabla ni columna donde quepa el manifiesto.
- **Los rótulos no deciden nada.** `curso_rotulo`, `leccion_rotulo`, `rotulo` del selector… existen para poder mostrar la sesión de ayer con la biblioteca cerrada, y se escriben una sola vez.
- **Prueba de esquema.** `classroom_engine.tests.test_arquitectura.test_el_esquema_es_solo_de_aula_sin_curso_ni_claves` falla si aparece una tabla cuyo nombre contenga `curso`, `asignatura`, `leccion`, `objeto`, `lamina`, `bloque`, `medio`, `pregunta`, `opcion` o `materia`, o una columna con `clave`, `correcta` o `solucion`.

---

## 2 · El curso tal como llega de AVACOM Biblioteca

El manifiesto de `example.json` es el ejemplo orientativo del esquema que la biblioteca está terminando de publicar. Esta sección fija **cómo lo lee el LMS**, sin convertirlo en contrato rígido.

### 2.1 · Identidad y versión

| Campo del manifiesto | En el LMS | Nota |
|---|---|---|
| `id` · `avacom.co.lower-secondary.6.science.states-of-matter` | `curso_ref` | La referencia estable de Q-20. Es lo que se escribe en todo el expediente y en el aula |
| `version` · `1.0.0` | `curso_version` | Con qué versión se dio la clase. Un cambio de versión no reescribe el aula |
| `schemaVersion` · `1.0` | `esquema` | Decide el normalizador: `1.0` (manifiesto) o `contrato-1` (árbol antiguo) |
| `translationGroupId` | `grupo_traduccion` | Cursos que son el mismo en otro idioma |
| `language` · `es-CO` | `idioma` | BCP 47 / RFC 5646 |

### 2.2 · Clasificación → navegación

```json
"classification": {
  "country": "CO",                                              ISO 3166-1 alpha-2
  "level":   {"code": "lower_secondary", "name": "Básica secundaria", "order": 2},
  "grade":   {"code": "6", "name": "Sexto", "order": 6},
  "subject": {"code": "science", "name": "Ciencias naturales"},
  "topic":   {"code": "states-of-matter", "name": "Estados de la materia", "order": 2}
}
```

| Nodo | Uso en las pantallas | Regla |
|---|---|---|
| `subject.name` | **Es la opción del panel de navegación «Asignaturas».** `GET /api/aula/cursos/` agrupa los cursos por `subject.code` y devuelve `asignaturas[{codigo, nombre, cursos[]}]` | El nombre se muestra tal cual llega; el LMS no traduce ni renombra |
| `level` | Rótulo secundario del curso y filtro por nivel educativo. Se muestra `name` («Básica secundaria») y se ordena por `order` | El LMS **no interpreta** `level.code`. La correspondencia con `nivel_clave` de MOD-001 (`preescolar`, `primaria`, `secundaria`, `bachillerato`) es Q-46 |
| `grade` | «Sexto» junto al título; ordena dentro del nivel | |
| `topic` | Subtítulo del curso dentro de la asignatura | |
| `country` | Filtro por instalación (la organización de MOD-001 declara `pais`) | ISO 3166-1 |
| `language` | Elegir voz e interfaz | BCP 47 |

Con el árbol del contrato 1 (`nivel`, `grado`, `asignatura` como texto) el normalizador construye la misma `clasificacion`, con `codigo` derivado del nombre, para que el panel no distinga de dónde vino el curso.

### 2.3 · La jerarquía y los tres catálogos

```
COURSE ── media[]  (image · video · audio · pdf · simulation)
       └─ lessons[] ── objects[]
                        ├── lecture        → slides[] → blocks[]   (heading · text · list · image · video)
                        ├── explanation    → pages[]  → blocks[]   (text · audio · pdf)
                        ├── simulation_lab → mediaId → simulation  (+ launchParams)
                        ├── activity       → questions[]           (6 tipos)
                        └── exam           → questions[] + settings de selección y tiempo  (MOD-010)
```

**Objetos** (`TIPOS_OBJETO`): la experiencia pedagógica. Se decide primero.

| `tipo` (biblioteca) | `componente` (MAUI) | Qué contiene en la vista de aula |
|---|---|---|
| `lecture` | `presentacion` | `laminas[]` con `unidad_ref`, `indice`, `titulo`, `duracion_seg`, `bloques[]` · `total_unidades` |
| `explanation` | `lectura` | `paginas[]` con `unidad_ref`, `indice`, `titulo`, `bloques[]` |
| `simulation_lab` | `laboratorio_web` | `simulacion` (el medio resuelto), `parametros_lanzamiento`, `url_lanzamiento`, `objetivo_aprendizaje`, `instrucciones`, `pasos[]`, `preguntas_guia[]` |
| `activity` | `actividad` | `instrucciones`, `ajustes{retroalimentacion, intentos_permitidos, barajar_preguntas, barajar_opciones}`, `preguntas[]`, `puntos_totales` |
| `exam` | `examen` | `fuera_de_alcance: true`, `modulo: "MOD-010"`, `ajustes` de selección y tiempo, `total_preguntas_banco`, **`preguntas: []`** |

**Bloques** (`TIPOS_BLOQUE`): el contenido visual dentro de una lámina o página.

| `tipo` | `componente` | Campos propios |
|---|---|---|
| `heading` | `titulo` | `texto`, `nivel`, `tramos[]` |
| `text` | `texto` | `texto`, `estilo` (`definition`, `highlight`…), `tramos[]` |
| `list` | `lista` | `ordenada`, `items[]`, `items_tramos[][]` |
| `image` | `imagen` | `media_ref`, `url`, `pie`, `texto_alternativo`, `ancho`, `alto`, `mime` |
| `video` | `video` | `media_ref`, `url`, `pie`, `desde_seg`, `hasta_seg`, `autoplay`, `duracion_seg`, `subtitulos_url`, `transcripcion_url` |
| `audio` | `audio` | `media_ref`, `url`, `pie`, `duracion_seg`, `transcripcion_url` |
| `pdf` | `pdf` | `media_ref`, `url`, `pie`, `desde_pagina`, `hasta_pagina`, `paginas`, `url_pagina_inicial` (`…#page=N`) |

**Preguntas** (`TIPOS_PREGUNTA`): sólo lo necesario para preguntar.

| `tipo` | `componente` | Campos propios (sin ninguna clave) |
|---|---|---|
| `multiple_choice` | `opcion_multiple` | `permite_varias`, `opciones[{opcion_ref, texto, tramos}]` |
| `true_false` | `verdadero_falso` | `opciones` fijas `true` / `false` (Verdadero / Falso) |
| `fill_blanks` | `completar` | `plantilla` con `{{b1}}`, `espacios[{espacio_ref, modo_entrada: select|text|numeric, opciones[]}]` |
| `matching` | `relacionar` | `izquierda[{ref, texto}]`, `derecha[{ref, texto}]` (puede haber distractores a la derecha) |
| `ordering` | `ordenar` | `elementos[{ref, texto}]` en el orden en que llegan (ya barajado por la biblioteca) |
| `open` | `abierta` | `formato_respuesta`, `longitud_maxima` |

Comunes: `pregunta_ref`, `enunciado`, `enunciado_tramos`, `tema_ref`, `dificultad`, `duracion_estimada_seg`, `puntos`, `nivel_cognitivo`, `credito_parcial`.

**Medios** (`CLASES_MEDIO`): el catálogo global `media` del manifiesto.

| `kind` | `componente` | Campos en la vista |
|---|---|---|
| `image` | `imagen` | `url`, `ancho`, `alto`, `texto_alternativo`, `mime` |
| `video` | `video` | `url`, `duracion_seg`, `ancho`, `alto`, `subtitulos_url`, `transcripcion_url` |
| `audio` | `audio` | `url`, `duracion_seg`, `transcripcion_url` |
| `pdf` | `pdf` | `url`, `paginas` |
| `simulation` | `webview` | `url` (la entrada), `base_url`, `simulacion{entrada, proveedor, tecnologia, orientacion, ajustes[], destinos[], ancho_diseno, alto_diseno}`, `licencia{tipo, atribucion, fuente_url}` |

### 2.4 · Las referencias que MOD-007 escribe

| Referencia | Origen en el manifiesto | Dónde la escribe MOD-007 |
|---|---|---|
| `curso_ref` · `curso_version` | `id` · `version` | `m07_sesion`, `m07_selector`, `m07_distribucion`, eventos |
| `leccion_ref` | `lessons[].id` | `m07_sesion` (vía `leccion`), `m07_selector`, `m07_distribucion` |
| `objeto_ref` · `objeto_tipo` | `objects[].id` · `objects[].type` | `m07_sesion` (vía `recurso`), `m07_selector`, `m07_distribucion` |
| `unidad_ref` · `unidad_indice` | `slides[].id` / `pages[].id` / `questions[].id` | `m07_selector` (la lámina, página o pregunta proyectada) |
| `media_ref` | `media[].id` | `m07_selector` y `m07_distribucion` cuando se proyecta o difunde un medio suelto |
| `nodo_ref` | (árbol académico, MOD-003) | `m07_sesion` (vía `arbol`) |
| `pregunta_ref` | `questions[].id` | **No la escribe MOD-007**: es de MOD-010 (`m10_intento_pregunta`) |

Toda escritura valida la referencia contra el curso vigente (`dominio.curso.localizar`): un selector o una distribución apuntan siempre a algo que existe en la versión que se está dando.

### 2.5 · Lo que nunca sale del backend

`catalogos.CLAVES_DE_CORRECCION` = `isCorrect`, `answer`, `acceptedAnswers`, `wrongAnswers`, `pairs`, `wrongPairs`, `correctOrder`, `wrongOrders`, `modelAnswer`, `rubric`, `incorrectExamples`, `feedback` (manifiesto) y `clave`, `clave_respuesta`, `respuesta`, `respuesta_correcta`, `correcta`, `es_correcta`, `solucion` (contrato 1).

- El normalizador **construye** cada pregunta con campos explícitos: las claves no llegan por construcción.
- `curso.sin_claves` recorre la vista completa al final: segunda línea de defensa, igual que `biblioteca.cliente.sin_claves`.
- Se aplica a **todos los roles**. La revisión docente con rúbrica y el panel de resultados con la respuesta correcta son de MOD-010/MOD-011 y llegarán por sus propias rutas, no por la vista de aula.
- `teacherNotes` (curso, lección, objeto, lámina) sale como `notas_docente` **sólo** con `rol=docente`.
- Prueba: `test_la_actividad_trae_las_seis_clases_de_pregunta_sin_ninguna_clave` comprueba el JSON completo con `curso.contiene_clave` y con búsqueda textual.

### 2.6 · El examen queda fuera de MOD-007

Por decisión del prompt, los `exam` no entran al Classroom Engine. La vista los conserva para que la estructura de la lección sea completa (la lección 3 sólo tiene un examen), con `fuera_de_alcance: true`, `modulo: "MOD-010"`, sus `ajustes` de selección (`random_balanced`, 4 preguntas, tolerancias) y tiempo (`sum_of_estimates`, 25 % extra), y `total_preguntas_banco: 12`, **sin preguntas**. Iniciar una sesión por vía `recurso` con un examen, declararlo como selector o lanzarlo como actividad responde `400` nombrando a MOD-010.

### 2.7 · Componentes especiales: cómo se mapean

| Componente que trae el contenido | Cómo llega en la vista de aula | Lo que el cliente necesita saber |
|---|---|---|
| **Presentaciones** | Son los `lecture` con `slides[]`: la presentación nativa del manifiesto (`presentacion` → `laminas[]`). No hay binario `.pptx` en el esquema | El selector proyecta una lámina (`unidad_ref`, `unidad_indice`). Si la biblioteca llegara a publicar un `.pptx`, lo convertiría ella a láminas, PDF o HTML; el LMS no analiza binarios de Office (Q-47) |
| **Videos** | Bloque `video` con recorte `desde_seg`/`hasta_seg` y `autoplay`; el medio aporta `duracion_seg`, `subtitulos_url` (WebVTT) y `transcripcion_url` | Un mismo `vid-changes` se usa dos veces con recortes distintos (0–60 s y 60–150 s). El reproductor debe respetar el recorte y ofrecer subtítulos |
| **Audios** | Bloque `audio` en páginas de `explanation`, con `duracion_seg` y transcripción | Reproductor sencillo con transcripción visible (accesibilidad y aula ruidosa) |
| **PDF** | Bloque `pdf` con `desde_pagina`/`hasta_pagina` y `url_pagina_inicial` (`#page=N`) | Mostrar el rango pedido, no el documento completo |
| **Simulaciones HTML5 (WebView)** | Medio `simulation` → `componente: webview`. `url` es la **entrada** (`states-of-matter-basics_es.html`, `index.html`), `base_url` la carpeta; `simulacion.ajustes` trae los *shims* (`block_network`, `scale_to_fit`), `orientacion` (`landscape`), `destinos` (`screen`, `tablet`), `ancho_diseno`/`alto_diseno` | `url_lanzamiento` del laboratorio ya incluye `launchParams` como query (`?startTemp=-10&altitudeMeters=0`). La WebView sólo debe navegar al host del backend (`block_network` se cumple porque el aula no tiene internet y el cliente cancela cualquier otra navegación) |
| **Imágenes** | Bloque `imagen` con `texto_alternativo`, `ancho`, `alto` | `Image` con la URL del backend; alto y ancho evitan saltos de maqueta |
| **Texto con marcado** | El subconjunto «AVACOM Markdown» de `RichText` (`**negrita**`, `*cursiva*`, matemática en línea `$…$`) → `tramos[{texto, negrita, cursiva, matematica}]` en `heading`, `text`, `list`, enunciados, opciones e ítems; la matemática llega ya legible («1/3 × 2»). Ver [06](06-Versión-2-Contenido.md) §4 | Un `FormattedString`; sin librería de Markdown ni motor LaTeX en la tableta |

### 2.8 · Convivencia con el contrato 1

El árbol antiguo (`secciones[] → items[]`) se normaliza con la misma forma (`esquema: "contrato-1"`): cada sección es una `leccion`, cada ítem un `objeto` con `tipo_contrato1`. Los detalles que ese contrato entrega por rutas aparte (`/api/biblioteca/leccion/{ref}/`, `/api/biblioteca/evaluacion/{ref}/`) se indican en `detalle_url`; los medios apuntan a `/api/biblioteca/medio/{ref}/`.

| Ítem contrato 1 | `tipo` | `componente` |
|---|---|---|
| `imagen` · `video` · `audio` · `documento` | `recurso` | `imagen` · `video` · `audio` · `pdf` (con `medio{url}`) |
| `interactivo` | `simulation_lab` | `laboratorio_web` (`url_lanzamiento` = `…/index.html`) |
| `leccion` | `explanation` | `lectura` (`paginas: []`, `detalle_url`) |
| `actividad` | `activity` | `actividad` (`preguntas: []`, `detalle_url`) |
| `evaluacion` | `exam` | `examen` · `fuera_de_alcance` |
| `banco` · `scorm` | (igual) | `no_soportado` · `visible: false` |

---

## 3 · Requisitos que gobiernan el modelo

| # | Requisito (origen) | Dónde se cumple |
|---|---|---|
| R-01 | Ninguna tabla de curso ni de sus partes; sólo referencias y rótulos (regla de oro, art. 14, CV-08) | §5, prueba de esquema |
| R-02 | Cuatro vías de inicio, mismo tipo de sesión (BR-044, DEC-001, FUN-064) | `m07_sesion.via_origen`, `ViaDeInicio.validar`, `IniciarSesion` |
| R-03 | Una sesión abierta por profesor; las suspendidas no cuentan (BR-045) | `ux_m07_profesor_abierta` |
| R-04 | Una sesión activa por grupo; relevo, no acompañamiento (DEC-035) | `ux_m07_grupo_activa`, `relevo_de_sesion_id` |
| R-05 | Código de unión único entre activas, conservado al suspender y reanudar; rotable (FUN-065/066, CMP-012) | `ux_m07_codigo`, `RotarCodigo`, `ReanudarSesion` |
| R-06 | Sólo entra el inscrito o el admitido a mano; expulsión que no borra respuestas (BR-047/048, FUN-067/068/078) | `m07_participante.estado`, `admision_nominal`, puerto `Identidad` |
| R-07 | Readmitir sin duplicar la participación (FUN-077) | `ux_m07_part` + `UnirseASesion` con `participante_id` |
| R-08 | El selector es lo que el profesor declara y se propaga en ≤ 3 s; el alumno en seguimiento no navega (BR-049/050) | `m07_selector` (un vigente), `m07_control(seguimiento)`, `intervalo_sondeo_ms: 2000` |
| R-09 | Bloquear y liberar pantallas (CAP-042, FUN-074) | `m07_control(bloqueo)`, evento `aula.dispositivos.bloqueados.v1` |
| R-10 | Difundir recurso o actividad con confirmación y avance por dispositivo (CAP-040, FUN-070/071) | `m07_distribucion`, `m07_distribucion_entrega` |
| R-11 | Presencia técnica registrada por el nodo, no asistencia académica (FUN-073, CAP-038) | `m07_presencia`, `ultimo_latido_en` |
| R-12 | Reanudar tras caída con mismo selector, participantes y código (BR-051, FUN-076) | Estados `suspendida ⇄ abierta`; nada se reescribe al reanudar |
| R-13 | Cerrada no admite nuevos ni cambios de selector; consolidar evidencia (BR-052, FUN-079, CAP-045) | `exigir_abierta`, `m07_resumen`, `CerrarSesion` |
| R-14 | La marca temporal la asigna el nodo (BR-062); nada del dispositivo decide tiempo | Puerto `Reloj`; `servidor_en` en cada respuesta |
| R-15 | Hecho + auditoría + evento en una transacción (Parte VII, Outbox) | `UnidadDeTrabajoAula`, `m07_evento_salida` |
| R-16 | Dominio y aplicación sin framework; otros módulos sólo por puertos | `test_arquitectura`, `aplicacion/puertos.py` |

---

## 4 · Opciones consideradas

### 4.1 · Cómo entregar el curso al cliente

| Opción | Decisión |
|---|---|
| A · Reenviar el manifiesto tal cual | Rechazada: expone claves, notas del docente y `path` internos; obliga a cada cliente a conocer el esquema |
| B · Guardar una copia normalizada en el LMS | **Rechazada**: viola la regla de oro (segunda verdad) |
| **C · Normalizar en vivo a una «vista de aula» con `componente`, `tramos` y URL del backend, aceptando dos esquemas** | **Elegida**. Es lo que evolucionó del endpoint de prueba (§9.3) |

### 4.2 · Dónde vive el plan de clase (MOD-006)

| Opción | Decisión |
|---|---|
| Implementar `m06_plan` y `m06_bloque` aquí | Rechazada: es otro módulo |
| **Puerto `PlanDeClase` + `plan_id` de texto; el plan efímero se deriva de los objetos de la lección** | **Elegida**. «MOD-006 materializa el plan o genera uno vacío» (JRN-006) |

### 4.3 · Cómo representar el selector

| Opción | Decisión |
|---|---|
| Columna `bloque_vigente_id` en la sesión (como el Maestro) | Rechazada sola: pierde el historial que BR-050 exige registrar |
| **Bitácora `m07_selector` con índice parcial de un solo vigente** | **Elegida**. El resumen cuenta selectores; la sesión no duplica el puntero |

### 4.4 · Seguimiento y bloqueo

| Opción | Decisión |
|---|---|
| Dos banderas en `m07_sesion` | Rechazada: sin historial ni autor |
| **Periodos `m07_control(tipo, desde, hasta)`; abierto = activo; único abierto por tipo** | **Elegida** (CV-05: nada se borra, se cierra con fecha) |

### 4.5 · Identidad de participación

| Opción | Decisión |
|---|---|
| Fila nueva por cada conexión | Rechazada: duplica participación (FUN-077) |
| **Una fila por `(sesion, persona)`; el `id` es el identificador de participación que la tableta conserva; `m07_presencia` guarda cada cambio** | **Elegida** |

### 4.6 · Referencias a personas y grupos (MOD-001/002)

| Opción | Decisión |
|---|---|
| FK físicas a `m01_grupo` / `m01_usuario` | Rechazada por ahora: acopla MOD-007 a las tablas de otro módulo y rompe el modo sin padrón (Q-34) |
| **Referencias lógicas de texto validadas por el puerto `Identidad`, como `persona_id` en el expediente** | **Elegida**; pasan a FK cuando MOD-002 y MOD-009 tengan dueño (Q-52) |

### 4.7 · Historial del código de unión

| Opción | Decisión |
|---|---|
| Tabla `m07_codigo_union` con vigencias | Rechazada: sobra |
| **Columna en la sesión + asiento de auditoría con `valor_anterior` + evento `aula.codigo.rotado.v1`** | **Elegida** |

### 4.8 · Presencia en vivo

| Opción | Decisión |
|---|---|
| Sólo en memoria (como el consumidor de quiz de [07](../07-comunicacion-ops-student.md)) | Rechazada para la clase: CAP-038/045 exigen «quién se conectó» en el resumen |
| **Persistida en `m07_participante` + `m07_presencia`; el canal en vivo (futuro) sólo la difunde** | **Elegida** |

---

## 5 · Modelo de datos (3FN)

### 5.0 · Diagrama

```
 m07_sesion  (SesionDeClase · ENT-015)
   │1                       referencias lógicas → m01_grupo (grupo_id), m01_usuario (profesor_id)
   ├──n m07_participante 1──n m07_presencia            (bitácora de presencia técnica)
   │        │1
   │        └──n m07_distribucion_entrega n──1 m07_distribucion n──1 m07_sesion
   ├──n m07_selector        (un solo vigente por sesión · ux_m07_selector_vigente)
   ├──n m07_control     (un abierto por tipo · ux_m07_control_abierto)
   ├──n m07_aviso       (participante nulo = grupo)
   └──1 m07_resumen     (al cerrar · se conserva cinco años)
 m07_evento_salida  (outbox aula.*.v1, sin FK: agregado_tipo + agregado_id)
```

Convenciones: PK de texto UUID (CV-02), fechas en **bigint milisegundos** del reloj del nodo (CV-03), `creado_en`/`creado_por` en las tablas de negocio (CV-04; `secuencia` llegará con MOD-015, como en `acceso`), nada se borra (CV-05), estados acotados por `CHECK` (CV-06), invariantes como índices parciales (CV-07).

### 5.1 · `m07_sesion` · SesionDeClase

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `grupo_id` · `grupo_rotulo` | char(36) · char(120) | Referencia lógica a `m01_grupo`; vacío = clase sin padrón (Q-34) |
| `profesor_id` · `profesor_rotulo` | char(64) · char(120) | `m01_usuario.id` con sesión; identificador declarado sin ella |
| `relevo_de_sesion_id` | char(36) | DEC-035 · DEC-038 (relevo sin examen en curso) |
| `via_origen` | char(16) | `arbol` · `leccion` · `recurso` · `libre` (BR-044) |
| `plan_id` | char(36) | MOD-006, por el puerto |
| `nodo_ref` | char(120) | MOD-003 (vía `arbol`) |
| `fuente_curso` | char(16) | `biblioteca` · `ejemplo`: de dónde se leyó el curso al iniciar |
| `curso_ref` · `curso_version` · `curso_rotulo` | char(200) · char(32) · char(250) | |
| `leccion_ref` · `leccion_rotulo` | char(120) · char(250) | |
| `objeto_ref` · `objeto_rotulo` | char(120) · char(250) | Vía `recurso` |
| `codigo_union` | char(8) | Seis dígitos legibles a cuatro metros (PAN-002) |
| `estado` | char(16) | `planificada` · `abierta` · `suspendida` · `cerrada` · `archivada` |
| `superficie` | char(64) | `pantalla` · `navegador` · dispositivo desde el que se inició |
| `iniciada_en` · `suspendida_en` · `causa_suspension` · `finalizada_en` · `origen_cierre` · `archivada_en` | bigint / char | `origen_cierre`: `profesor` · `inactividad` · `administrador` · `sistema` |
| `creado_en` · `creado_por` | | |

Índices e invariantes: `ux_m07_codigo` UNIQUE(`codigo_union`) WHERE estado ∈ {abierta, suspendida} · `ux_m07_grupo_activa` UNIQUE(`grupo_id`) WHERE activa y grupo no vacío · `ux_m07_profesor_abierta` UNIQUE(`profesor_id`) WHERE estado = abierta (BR-045) · `ck_m07_sesion_cierre_fechado` · `ck_m07_sesion_archivo_fechado` · `ck_m07_sesion_via_leccion` (curso y lección) · `ck_m07_sesion_via_recurso` (curso y objeto) · `ck_m07_sesion_via_arbol` (nodo).

### 5.2 · `m07_participante` · Participante

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | **Identificador de participación** que la tableta vuelve a presentar (FUN-077) |
| `sesion_id` | FK | |
| `persona_id` · `persona_rotulo` | char(64) · char(120) | Igual que en el expediente |
| `dispositivo` | char(64) | La huella que declara la tableta. Contexto, nunca identidad (DEC-023) |
| `dispositivo_id` · `dim_sesion_alumno_id` | char(36) | Referencias lógicas a `m09_dispositivo` y `m09_dim_sesion_alumno` (MOD-009, 2026-09-28): la tableta reconocida por el inventario y la sesión de alumno abierta en ella al unirse. Vacías si la tableta no declaró huella (prototipo) |
| `sesion_usuario_id` | char(36) | `m01_sesion` (MOD-001), lógica |
| `estado` | char(16) | `esperando` · `conectado` · `reconectando` · `salio` · `rechazado` · `expulsado` |
| `admision_nominal` | bool | BR-047: invitado admitido por el profesor |
| `ingreso` · `salida` · `ultimo_latido_en` | bigint | |
| `admitido_por` · `motivo` | | |

Invariantes: `ux_m07_part` UNIQUE(`sesion_id`, `persona_id`) · `ck_m07_part_salida_fechada` (salio/rechazado/expulsado ⇒ `salida`).

### 5.3 · `m07_presencia` · Presencia (append-only)

`participante_id`, `estado`, `dispositivo`, `detalle` («ingreso», «readmisión», «admitido por el profesor», «suspensión: caida_nodo», «cierre de la sesión»), `momento`. De aquí se reconstruye `conectados_maximo` del resumen.

### 5.4 · `m07_selector` · Selector

| Columna | Nota |
|---|---|
| `id`, `sesion_id` | |
| `curso_ref`, `curso_version`, `leccion_ref`, `objeto_ref`, `objeto_tipo`, `unidad_ref`, `unidad_indice`, `media_ref`, `rotulo` | Referencias validadas contra el curso vigente; `objeto_tipo = medio` cuando se proyecta un medio suelto |
| `vigente`, `declarado_en`, `declarado_por`, `sustituido_en` | Un solo vigente: `ux_m07_selector_vigente`; `ck_m07_selector_sustitucion` (no vigente ⇒ fecha); `ck_m07_selector_referencia` (curso o medio) |

### 5.5 · `m07_control` · Control

`id`, `sesion_id`, `tipo` (`seguimiento` · `bloqueo`), `desde`, `hasta`, `motivo`, `creado_por`, `cerrado_por`. Abierto (`hasta` nulo) = activo. `ux_m07_control_abierto` UNIQUE(`sesion_id`, `tipo`) WHERE hasta IS NULL · `ck_m07_control_vigencia`. Al iniciar la sesión se abre `seguimiento` (BR-050); al cerrar se cierran todos.

### 5.6 · `m07_distribucion` · Distribucion (el lanzamiento)

`id`, `sesion_id`, `clase` (`recurso` · `actividad`), `curso_ref`, `leccion_ref`, `objeto_ref`, `objeto_tipo`, `media_ref`, `rotulo`, `alcance` (`grupo` · `seleccion`), `destinatarios` (JSON: `persona_id` de quienes lo recibieron al lanzar), `excluidos_bloqueados` (JSON: `persona_id` dejados fuera por tableta bloqueada o retirada, MOD-009), `intentos_permitidos` y `tiempo_limite_seg` (las reglas con las que se lanzó; nulos = manda el objeto), `disponible_estudio` (MOD-008), `asignacion_ref` (MOD-010, hoy vacío · Q-49), `abierta_en`, `cerrada_en`, `creado_por`. `ck_m07_dist_referencia` (objeto o medio) · `ck_m07_dist_cierre_posterior` · `ck_m07_dist_intentos` (≥ 1) · `ck_m07_dist_tiempo` (≥ 1). Es la tabla `lanzamiento` de la segunda versión del modelo de datos (2026-09-28).

### 5.7 · `m07_distribucion_entrega` · DistribucionEntrega

`distribucion_id`, `participante_id`, `estado` (`pendiente` · `entregado` · `fallido`), `confirmada_en`, `intentos`. `ux_m07_entrega` · `ck_m07_entrega_confirmada`.

### 5.8 · `m07_aviso` · Aviso

`id`, `sesion_id`, `participante_id` (nulo = grupo), `texto` (300), `enviado_en`, `creado_por`.

### 5.9 · `m07_resumen` · Resumen (1:1, cinco años)

`participantes`, `conectados_maximo`, `admitidos_nominal`, `selectores`, `distribuciones`, `actividades`, `avisos`, `pendientes` (intentos abiertos al cierre, por el puerto `Evaluacion`), `duracion_ms`, `origen_cierre`, `consolidado_en`.

### 5.10 · `m07_evento_salida` · EventoSalida (Transactional Outbox)

`agregado_tipo`, `agregado_id`, `tipo_evento` (sólo los 16 de §6; el adaptador rechaza otro), `carga`, `creado_en`, `publicado_en`, `intentos`. Se escribe en la misma transacción que el hecho. Cuando exista MOD-015 (`m15_evento`) las colas de `acceso` y `aula` se unifican allí.

### 5.11 · Máquinas de estado

```
Sesión (INV-025)                              Participante
planificada ─► abierta ─► cerrada ─► archivada  esperando ─► conectado ⇄ reconectando ⇄ salio
                 ▲  │                (24 h)        │   └────► rechazado                 │
                 │  ▼                              └──── expulsado ◄────────────────────┘
              suspendida ─► cerrada                            (admitir/readmitir: → conectado)
```

Transiciones autorizadas en `dominio.sesion.TRANSICIONES`; cualquier otra responde `409 transicion_invalida` o `409 sesion_cerrada`. Una sesión `suspendida` conserva código, selector y participantes (que pasan a `reconectando`); no admite selector, controles, distribuciones ni avisos hasta reanudar, pero sí que las tabletas vuelvan a presentarse.

Lo anterior definió cada tabla. Lo que sigue analiza ese mismo modelo desde nueve ángulos de diseño relacional, para dejar explícito el razonamiento detrás de cada decisión.

### 5.12 · Lectura de dominio: qué problema resuelve cada grupo de tablas

| Grupo | Tablas | Pregunta del dominio que resuelve |
|---|---|---|
| El hecho de la clase | `m07_sesion` | ¿Qué clase está ocurriendo, iniciada por quién, para qué grupo, a partir de qué contenido, y en qué estado del ciclo de vida? |
| Quién está presente | `m07_participante`, `m07_presencia` | ¿Qué tabletas entraron, en qué estado técnico están ahora, y cuál es su bitácora de conexión? (presencia técnica, no asistencia académica) |
| Qué se está mostrando | `m07_selector` | ¿Qué está proyectando el profesor en este instante, y qué se proyectó antes? |
| Qué restricciones rigen | `m07_control` | ¿Deben las tabletas seguir al profesor, y están las pantallas bloqueadas, desde cuándo y hasta cuándo? |
| Qué se envió a los estudiantes | `m07_distribucion`, `m07_distribucion_entrega` | ¿Qué recurso o actividad se repartió, a quién, y quién ya confirmó recibirlo? |
| Qué se comunicó | `m07_aviso` | ¿Qué mensaje le mandó el profesor al grupo o a un estudiante puntual? |
| Cómo terminó | `m07_resumen` | ¿Cuánto duró la clase y qué pasó en ella, en un solo vistazo, cinco años después? |
| Qué le contamos a los demás | `m07_evento_salida` | ¿Qué hechos de esta clase necesita saber el resto del sistema? |

El hilo común es la **regla de oro** (artículo 14): estas diez tablas describen exclusivamente lo que ocurre *alrededor* del contenido — nunca el contenido mismo, que vive en AVACOM Biblioteca (§1, §5.19).

### 5.13 · Cardinalidad de las relaciones, y por qué

| Relación | Cardinalidad | Por qué es así |
|---|---|---|
| `sesion` → `participante` | 1:N | Una clase reúne a muchas tabletas; cada una es una fila, aunque se reconecte varias veces (la reconexión reutiliza la misma fila, `ux_m07_part`) |
| `participante` → `presencia` | 1:N | Bitácora append-only: cada cambio de estado técnico (conectado, reconectando, salió…) es una fila nueva, nunca una actualización — de aquí sale `conectados_maximo` |
| `sesion` → `selector` | 1:N (con **uno vigente**) | El selector cambia muchas veces durante la clase (BR-049) y BR-050 exige conservar el historial; «cuál es el vigente» es un índice parcial (§5.18), no la cardinalidad |
| `sesion` → `control` | 1:N (a lo sumo **dos abiertos** a la vez) | Hay dos tipos de control (`seguimiento`, `bloqueo`) y cada uno se abre y cierra por separado; el historial completo queda, sólo se exige un abierto **por tipo** |
| `sesion` → `distribucion` | 1:N | Una clase reparte varios recursos y lanza varias actividades a lo largo de la hora |
| `distribucion` ↔ `participante` | **N:M** vía `distribucion_entrega` | Cada distribución llega a varios estudiantes y cada estudiante recibe varias distribuciones a lo largo de la clase; el cruce es la única forma de saber, por pareja, si *ese* estudiante ya confirmó *esa* entrega |
| `sesion` → `aviso` | 1:N | Varios avisos por clase |
| `aviso` → `participante` | **N:1 opcional** | `participante_id` nulo significa «para todo el grupo»; no nulo, «para esta tableta». La misma tabla resuelve un aviso general o dirigido sin necesitar dos tablas de avisos |
| `sesion` ↔ `resumen` | **1:0..1**, PK compartida | Igual que `usuario`↔`persona` en `acceso` (§3.20 de ese módulo): nace una sola vez, en un instante preciso del ciclo de vida (el cierre), nunca antes y nunca más de una vez |
| `sesion` → `evento_salida` | 0:N, **sin FK** | El outbox se correlaciona por `agregado_id` (texto), no por clave foránea — ver §5.15 |

No hay ninguna relación **1:1 obligatoria desde el nacimiento** en el módulo: incluso `resumen`, la más cercana, sólo existe **después** de cerrar (`CerrarSesion`), nunca al abrir.

### 5.14 · La tabla asociativa: `m07_distribucion_entrega`

Es la única N:M genuina del módulo — reflejo de que MOD-007 es, ante todo, una jerarquía dueño→partes (§5.17), no una red de relaciones cruzadas como `acceso`.

| Atributo propio | Por qué hace falta la tabla asociativa |
|---|---|
| `estado` (`pendiente` / `entregado` / `fallido`) | El avance de entrega **no es** un atributo ni de la distribución (una sola para todo el grupo) ni del participante (que puede tener varias entregas pendientes a la vez): es un hecho exclusivo de *ese* cruce |
| `confirmada_en` | Cuándo, para esa pareja en particular, se cerró el ciclo — distinto para cada estudiante aunque la distribución sea la misma |
| `intentos` | Cuántas veces se reintentó la confirmación de *ese* estudiante con *esa* distribución |

Sin esta tabla, «mostrar la barra de progreso de la distribución» (CAP-040) sería imposible de representar: hace falta una fila por pareja para poder agregarlas.

### 5.15 · PK, FK, identidad e integridad referencial

**Claves.** El módulo repite el patrón de `acceso` (§3.22 de ese documento): UUID para todo lo que otro módulo, el cliente MAUI o un evento pueden necesitar señalar por separado (`sesion`, `participante`, `selector`, `control`, `distribucion`, `aviso` — los seis tienen `id` explícito); `BigAutoField` implícito donde la fila jamás se referencia por sí sola y sólo importa como parte de una bitácora o de un cruce (`presencia`, `distribucion_entrega`, `evento_salida` — ninguna declara `id`); y PK compartida en `resumen.sesion_id`, la misma técnica de partición 1:1 que `persona` en `acceso`, aquí usada para una extensión temporal (el cierre) en vez de una extensión de confidencialidad.

Un caso propio del módulo: `participante.id` no es sólo una PK técnica — es, por diseño, el **identificador de participación** que la tableta guarda y vuelve a presentar al reconectar (FUN-077). Un UUID generado como clave sustituta se **promueve** a token de dominio visible por el cliente, porque el dominio necesita un identificador estable, impredecible y ya único que el aparato pueda conservar sin pedir uno nuevo cada vez.

**Integridad referencial física, dentro del módulo.** Todo lo que cuelga de `m07_sesion` usa `CASCADE` (`participante`, `selector`, `control`, `distribucion`, `aviso`) y `distribucion_entrega` usa `CASCADE` hacia sus dos padres (`distribucion`, `participante`): son composición real, la sesión es la raíz del agregado (§5.17) y sus partes no tienen sentido sin ella. En la práctica esa cascada casi nunca se ejecuta — CV-05 hace que nadie borre una `m07_sesion` — pero declararla es la integridad correcta igual: una fila huérfana sería peor que una que nunca se produce.

**Integridad referencial lógica, hacia fuera del módulo.** Aquí está la diferencia real frente a `acceso`: `grupo_id`, `profesor_id`, `persona_id`, `dispositivo`, `sesion_usuario_id` y todos los `*_ref` de curso/lección/objeto/media **no son FK** — son texto plano (CV-08). No es un descuido: es la decisión explícita de §4.6 («acopla MOD-007 a las tablas de otro módulo y rompe el modo sin padrón, Q-34»). La integridad no desaparece, **se traslada**: la valida el puerto `Identidad` contra `acceso` al escribir (`esta_inscrito`) y el puerto `FuenteDeCursos` contra la biblioteca en vivo antes de guardar un selector o una distribución (`dominio.curso.localizar`, §2.4). El mismo backend usa entonces **dos estrategias de integridad referencial a propósito**: física (con `FOREIGN KEY` reales) dentro de un módulo que posee sus datos, y de aplicación (con un puerto que valida antes de escribir) en la frontera entre módulos que no deben acoplarse por esquema. Ambas son integridad referencial; sólo cambia dónde se hace cumplir.

### 5.16 · Por qué el modelo está en 3FN

**1FN/2FN**: igual que en `acceso` — columnas atómicas, PK de una sola columna en las diez tablas (o compartida en `resumen`, que sigue siendo una sola columna), así que no hay dependencia parcial posible.

**3FN**, con el mismo cuidado en los casos que a primera vista parecen copias:

- `curso_rotulo`, `leccion_rotulo`, `objeto_rotulo`, `grupo_rotulo`, `profesor_rotulo` **parecen** redundantes (copian un título que también existe en la biblioteca o en `acceso`) pero no son una dependencia transitiva porque **no se actualizan nunca** tras la escritura inicial (§1: «los rótulos no deciden nada»): son una fotografía histórica, no un valor que deba mantenerse sincronizado. La prueba de que no violan 3FN es que **pueden divergir** legítimamente del valor actual en la fuente — si un curso cambia de título mañana, la clase de hoy sigue mostrando el título con el que se dio, a propósito. Es el mismo patrón que una factura que conserva el nombre del producto tal como se llamaba el día de la venta.
- `m07_selector` y `m07_distribucion` repiten `curso_ref`/`curso_version` aunque `m07_sesion` ya los tiene: no es redundancia, es un hecho propio de cada evento — qué versión del curso estaba vigente en **ese** instante de proyección o de reparto, que en principio podría no coincidir con la versión con la que arrancó la sesión.
- No existe un contador `sesion.participantes_actual` ni `sesion.selector_actual_id`: ambos se calculan (`COUNT`, índice parcial `ux_m07_selector_vigente`) en vez de mantenerse como columna cacheada — el mismo criterio que evitó `usuario.credencial_activa_id` en `acceso`.

### 5.17 · Tablas transitivas y forma del modelo

**Tabla transitiva** (de tránsito obligado): `m07_distribucion_entrega` es la única — `distribucion` y `participante` sólo se conectan a través de ella (§5.14).

**Forma del modelo.** De los dos módulos analizados, `classroom_engine` es el que más se acerca, visualmente, a una **estrella**: `m07_sesion` es un centro único del que cuelgan directamente cinco tablas satélite (`participante`, `selector`, `control`, `distribucion`, `aviso`), sin que esas cinco dependan entre sí (salvo `distribucion_entrega`, que conecta dos de ellas). No hay cadena de dependencias-de-dependencias como la de `acceso` (`miembro_grupo → grupo → politica_credencial → organizacion`): aquí casi todo está a un salto de la sesión. Dicho eso, **sigue sin ser un esquema en estrella en el sentido de un almacén de datos**: estas tablas se escriben continuamente mientras la clase ocurre (no se cargan una vez por ETL), llevan sus propias reglas de integridad (`CHECK`, índices parciales) y no están desnormalizadas para lectura agregada. Lo interesante es que **`m07_resumen` es, literalmente, la fila de hechos que un modelo en estrella real querría**: llega pre-agregada (conteos, duración, origen de cierre) exactamente en el grano «una fila por sesión de clase», calculada una sola vez al cerrar y nunca más tocada. Si algún módulo de reportes necesita un data mart de actividad de aula, `m07_resumen` es casi directamente su tabla de hechos; el resto de `m07_*` sería la fuente para construir dimensiones (`dim_sesion`, `dim_participante`) o hechos de grano más fino (uno por selector, uno por distribución).

### 5.18 · Qué consulta justifica cada índice

| Índice | Consulta que resuelve |
|---|---|
| `ux_m07_codigo` (única, `codigo_union` con estado en `ACTIVAS`) | **La consulta más caliente del módulo**: una tableta teclea seis dígitos y hay que encontrar la sesión activa en O(1) (`UnirseASesion`, FUN-065) |
| `ux_m07_grupo_activa` / `ux_m07_profesor_abierta` | Antes de iniciar: «¿mi grupo ya tiene una clase activa?» (DEC-035) / «¿ya tengo yo una clase abierta?» (BR-045) — el mismo índice que impone la regla sirve para consultarla |
| `ix_m07_sesion_prof` (`profesor_id, iniciada_en`) | Historial de clases de un profesor, ordenado — panel docente |
| `ix_m07_sesion_estado` (`estado, finalizada_en`) | El barrido periódico que archiva las cerradas hace más de 24 h (`ArchivarSesiones`) |
| `ux_m07_part` (única, `sesion, persona_id`) | «¿Esta persona ya es participante?» al unirse o reconectar, sin duplicar la fila (FUN-077) |
| `ix_m07_part_estado` (`sesion, estado`) | El conteo en vivo (conectados/esperando/reconectando) que pide **cada sondeo de 2 segundos** de cada tableta y del panel del profesor — probablemente el índice de mayor tráfico de todo el backend |
| `ix_m07_presencia` (`participante, momento`) | Reconstruir `conectados_maximo` y la línea de tiempo de conexión de un participante al cerrar la sesión (`m07_resumen`) |
| `ux_m07_selector_vigente` (única, `sesion` con `vigente=True`) | «¿Qué se está mostrando ahora?» — otra consulta de sondeo de 2 s, en cada tableta conectada |
| `ix_m07_selector` (`sesion, declarado_en`) | Historial de selector para el panel docente («qué vimos, en orden») |
| `ux_m07_control_abierto` (única, `sesion, tipo` con `hasta IS NULL`) | «¿Está el bloqueo o el seguimiento activo ahora?» — se sondea junto con el selector |
| `ix_m07_dist_abiertas` (`sesion, cerrada_en`) | Qué distribuciones siguen abiertas — el aviso `409 actividades_abiertas` de `CerrarSesion` (FUN-079) depende de esta consulta |
| `ux_m07_entrega` (única, `distribucion, participante`) | «¿Ya confirmó este estudiante esta distribución?» — la barra de progreso de CAP-040 se agrupa sobre este índice |
| `ix_m07_aviso` (`sesion, enviado_en`) | El parámetro `avisos_desde` de `estado/`: «avisos nuevos desde la última vez que pregunté» |
| `ix_m07_outbox` (`publicado_en, creado_en`) | El mismo patrón de relevo de outbox que en `acceso` |

La observación que vale la pena resaltar: al menos tres de estos índices (`ix_m07_part_estado`, `ux_m07_selector_vigente`, `ux_m07_control_abierto`) se ejecutan una vez cada dos segundos por cada tableta conectada (§9.6) — son, con diferencia, los índices más exigidos de los dos módulos analizados, y están diseñados exactamente para esa carga: lecturas puntuales por sesión, resueltas por un índice parcial o compuesto, nunca un recorrido completo de la tabla.

### 5.19 · Linaje de datos: de dónde viene cada dato y cuál es la fuente de verdad

| Dato | Fuente de verdad | Cómo llega a `classroom_engine` |
|---|---|---|
| Asignatura, curso, lección, objeto, lámina, pregunta, medio | **AVACOM Biblioteca**, exclusivamente | Se lee en vivo en cada petición por el puerto `FuenteDeCursos` (adaptador `FuenteBiblioteca`, API de Contenido v2 con `link.json` + `X-Avacom-Token`); MOD-007 **nunca** la copia a una tabla — sólo congela `*_ref` + `*_rotulo` en el instante en que se usó (§5.16) |
| Persona, grupo, inscripción | **`acceso`** (MOD-001/002) | Vía el puerto `Identidad`; la referencia (`persona_id`, `grupo_id`) es el mismo `usuario.id`/`grupo.id` que ya es autoritativo en ese módulo (frontera lógica, no física — Q-52) |
| Qué pasó en la clase (quién entró, qué se mostró, qué se repartió, qué se avisó, cómo cerró) | **Este módulo, `m07_*`** | Es el único punto del backend donde estos hechos se originan; no hay una fuente anterior que reflejar |
| Nota, intento, corrección | **Fuera de alcance** (MOD-010/`expediente m10_*`) | MOD-007 sólo pide `preparar_asignacion`/`intentos_abiertos` por el puerto `Evaluacion`; no guarda ni un puntaje |
| Marca de tiempo de cada `*_en` | El reloj del nodo, por el puerto `Reloj` (BR-062) | Nunca el reloj del cliente: cada respuesta añade `servidor_en` para que la tableta se alinee, en vez de que el dispositivo dicte cuándo pasó algo |
| Eventos `aula.*.v1` | El hecho ya escrito en `m07_*`, en la misma transacción | `m07_evento_salida` es el mecanismo de propagación, no una fuente adicional — igual que en `acceso` (§3.26 de ese documento) |
| Asientos de auditoría (`aula.*`) | **`m19_auditoria`**, alojada en el app `expediente` (MOD-019) | Por el puerto `Auditoria` → adaptador `AuditoriaExpediente`, en la misma transacción que el hecho. Es un sumidero append-only **compartido** por los tres módulos del backend; por eso un esquema con sólo las `m07_*` (o sólo `m01_*` + `m07_*`) no incluye su propia auditoría |

En síntesis, `classroom_engine` es intencionalmente el módulo con **menos fuentes de verdad propias** de los tres del backend: posee un único tipo de dato genuino (la sesión de clase y lo que ocurre en ella) y para todo lo demás actúa como consumidor disciplinado de otros dueños — exactamente lo que exige la regla de oro del artículo 14.

### 5.20 · Conclusión: cómo el modelo resuelve el dominio del aula

MOD-007 tiene un solo agregado (`m07_sesion`) y diez tablas cuya única función es dejar constancia, con integridad y sin ambigüedad, de todo lo que ese agregado vive entre que se abre y se archiva. La forma casi estelar del modelo (§5.17) no es casualidad: refleja que el dominio real **es** así — una clase con partes que le pertenecen, no una red de entidades independientes como en `acceso`. Por eso el módulo necesita una sola tabla asociativa (`distribucion_entrega`) en vez de cuatro, y por eso puede permitirse `CASCADE` en casi todas sus FK internas sin miedo: nada fuera de la sesión depende de sus partes. La disciplina más importante, sin embargo, no está en lo que el modelo guarda, sino en lo que **se niega a guardar**: ninguna tabla de curso, ninguna clave de corrección, ninguna FK hacia contenido. Esa renuncia —sostenida con referencias lógicas validadas por puertos en vez de claves foráneas físicas (§5.15)— es lo que le permite a la biblioteca cambiar de versión, de esquema o de proveedor sin que una sola fila de `m07_*` deje de tener sentido. El modelo resuelve el dominio del aula precisamente por lo poco que decide poseer.

---

## 6 · Eventos que publica

Los dieciséis de la sección L del Maestro, en `m07_evento_salida` con `agregado_tipo = SesionDeClase` y `sesion_id` en toda carga.

| Evento | Cuándo | Carga (además de `sesion_id`, `instante`) |
|---|---|---|
| `aula.sesion.iniciada.v1` | FUN-064 | `grupo_id`, `plan_id`, `profesor_id`, `via_origen`, `curso_ref`, `leccion_ref`, `superficie` |
| `aula.codigo.generado.v1` | FUN-065 | `codigo_union` |
| `aula.codigo.rotado.v1` | FUN-066 | `codigo_union` (el anterior queda en auditoría) |
| `aula.dispositivo.admitido.v1` | FUN-067 / ingreso directo | `participante_id`, `persona_id`, `dispositivo`, `inscrito`, `admision_nominal` |
| `aula.dispositivo.rechazado.v1` | FUN-068 | `participante_id` |
| `aula.dispositivo.readmitido.v1` | FUN-077 / BR-048 | `participante_id`, `persona_id`, `dispositivo` |
| `aula.dispositivo.expulsado.v1` | FUN-078 | `participante_id`, `persona_id` |
| `aula.dispositivos.bloqueados.v1` | FUN-074 | `bloqueados` (true al bloquear, false al liberar) |
| `aula.presencia.registrada.v1` | FUN-073 | `participante_id`, `estado` |
| `aula.recurso.proyectado.v1` | FUN-069 / selector inicial | `curso_ref`, `curso_version`, `leccion_ref`, `objeto_ref`, `objeto_tipo`, `unidad_ref`, `unidad_indice`, `media_ref`, `rotulo`, `inicial` |
| `aula.actividad.lanzada.v1` | FUN-070 | `distribucion_id`, `curso_ref`, `objeto_ref`, `asignacion_ref`, `destinatarios` |
| `aula.actividad.cerrada.v1` | FUN-071 / cierre forzado | `distribucion_id`, `asignacion_ref`, `por_cierre_de_sesion` |
| `aula.resultados.mostrados.v1` | FUN-072 | `distribucion_id` |
| `aula.mensaje.enviado.v1` | FUN-075 | `aviso_id`, `participante_id`, `alcance` |
| `aula.sesion.reanudada.v1` | FUN-076 | `causa`, `instante_corte`, `instante_reanudacion`, `dispositivos_por_recuperar`, `codigo_union` |
| `aula.sesion.finalizada.v1` | FUN-079 | `instante_fin`, `origen_cierre`, `actividades_cerradas`, `dispositivos_liberados`, `presencia_consolidada`, `pendientes` |

Además, asientos en `m19_auditoria` con acciones `aula.*` (sesión iniciada, suspendida, reanudada, finalizada, archivada; participante ingreso/admitido/rechazado/expulsado; selector declarado; control cambiado; distribución creada/cerrada; resultados; código rotado).

---

## 7 · Puertos hacia otros módulos

| Puerto (`aplicacion/puertos.py`) | Módulo | Qué pide MOD-007 | Adaptador del prototipo |
|---|---|---|---|
| `FuenteDeCursos` | Biblioteca (MOD-004) | `cursos()`, `curso(ref, version, rol)`, `medio(...)`, `evaluar(...)`, `evaluar_lote(...)`, `estado()` | `FuenteBiblioteca` (API de Contenido v2 vía `biblioteca.contenido_v2`, ver [05](05-contrato-biblioteca.md)) y `FuenteEjemplo` (`example.json`; no califica: 501) |
| `Identidad` | MOD-001 / MOD-002 | Rótulos de persona y grupo; `esta_inscrito(grupo, persona)` → `True`/`False`/`None` (no se sabe) | `IdentidadAcceso`: lee `m01_*`; sin grupo o sin padrón devuelve `None` y no bloquea |
| `Evaluacion` | MOD-010 | `preparar_asignacion(...)` al lanzar una actividad; `intentos_abiertos(...)` al cerrar | `EvaluacionExpediente`: hoy devuelve `''` y cuenta `m10_intento` abiertos (Q-49) |
| `Reloj` | MOD-015 | `ahora_ms()` (BR-062) | `RelojNodo` |
| `Auditoria` | MOD-019 | `registrar(...)` | `AuditoriaExpediente` → `m19_auditoria` |
| `Outbox` | MOD-015 | `publicar(...)` | `OutboxDjango` → `m07_evento_salida` |
| `Autorizacion` | MOD-001 | `exigir(actor, permiso classroom.*)` | `AutorizacionPrototipo`: con sesión, sólo nivel ≥ 2 opera la clase; sin sesión (Q-34) se permite (Q-50) |
| `PlanDeClase` (nombrado, no implementado) | MOD-006 | Materializar el plan | `plan_id` de texto; el plan efímero son los objetos de la lección (Q-54) |

---

## 8 · Arquitectura del módulo

```
backend/classroom_engine/
  dominio/       catalogos.py (los tres catálogos y las claves prohibidas) · curso.py (normalizador, localizar, tramos)
                 sesion.py (estados, transiciones, eventos, permisos, ViaDeInicio, código) · errores.py
  aplicacion/    puertos.py (Protocols) · casos_uso.py (5 de curso + 18 de sesión)
  infraestructura/ fuente_ejemplo.py · fuente_biblioteca.py · marcadores.py (PNG/WAV/PDF/HTML/VTT de ejemplo)
                 repositorios.py (ORM m07_*, outbox, auditoría, identidad, evaluación, autorización)
                 unidad_trabajo.py · contenedor.py (composition root y URL de medios)
  interfaces/    urls.py · views.py (APIView, traducción de errores)
  models.py · migrations/0001_initial.py · tests/ (arquitectura, curso, sesiones)
```

Reglas verificables (`tests/test_arquitectura.py`): `dominio/` y `aplicacion/` no importan `django`, `rest_framework`, `pydantic`, `sqlalchemy` ni `fastapi`; `interfaces/views.py` no toca `.objects.` ni el cliente de la biblioteca; el esquema es sólo `m07_*` sin tablas de contenido ni columnas de clave.

---

## 9 · API · `/api/aula/`

### 9.1 · Convenciones

- **Errores**: `{ "detail", "codigo", …extra }`. `400 datos_invalidos` · `403 sin_permiso` / `participante_expulsado` · `404 no_encontrado` / `curso_no_encontrado` / `referencia_no_encontrada` / `codigo_invalido` · `409 transicion_invalida` / `sesion_cerrada` / `sesion_activa_existente` / `grupo_con_sesion_activa` / `actividades_abiertas` / `sin_participantes_admitidos` · `501 capacidad_ausente` (con `capacidades`) · `502 fuente_error` · `503 fuente_no_disponible` (con `disponible: false` y `sugerencia`).
- **Fechas**: milisegundos desde época, del reloj del nodo. Toda respuesta de sesión trae `servidor_en` para que la tableta se alinee sin usar su reloj.
- **`?fuente=biblioteca|ejemplo`**: la fuente del curso. Sin parámetro, la configurada (`AVACOM_AULA_FUENTE_CURSOS`, por defecto `biblioteca`); si la referencia es la del manifiesto de ejemplo, se resuelve sola. La fuente `biblioteca` habla la API de Contenido v2 ([05](05-contrato-biblioteca.md)).
- **`?version=2.0.0`**: exige esa versión del curso. La API v2 sólo sirve el esquema de la instalada (otra es 404 `version_not_available`); sin parámetro, la instalada: la clase en vivo siempre ve la versión vigente (artículo 14.3).
- **`?semilla=<sesion>`**: fija el barajado de las opciones (`seed` de la API v2) para que toda la clase vea el mismo orden.
- **`?rol=docente`**: incluye `notas_docente`. Con JWT de MOD-001 el rol lo decide la sesión (`menu = student` ⇒ estudiante) y el parámetro se ignora. Por defecto, estudiante.
- **Actor** (Q-34): con JWT, quien firma; sin JWT, `profesor_id` (o `actor`) del cuerpo, como `actor` en el expediente. Con JWT de estudiante, las funciones del profesor responden `403 sin_permiso`.
- **Permiso DRF**: `SesionSiSeExige` (exige sesión sólo con `AVACOM_LMS_EXIGIR_SESION=1`).

### 9.2 · Consumo del curso (sólo lectura, nunca escribe)

| Ruta | Verbo | Devuelve |
|---|---|---|
| `/api/aula/cursos/?fuente=` | GET | `{fuente, disponible, asignaturas[{codigo, nombre, cursos[ficha]}], cursos[ficha]}` |
| `/api/aula/cursos/{curso_ref}/?fuente=&rol=` | GET | La **vista de aula** completa |
| `/api/aula/cursos/{curso_ref}/lecciones/{leccion_ref}/` | GET | `{curso: ficha, leccion}` (lo que baja una tableta al seguir la clase) |
| `/api/aula/cursos/{curso_ref}/objetos/{objeto_ref}/` | GET | `{curso: ficha, leccion (sin objetos), objeto}` |
| `/api/aula/cursos/{curso_ref}/medios/{media_ref}/` | GET · HEAD | Bytes del medio, con `Range` |
| `/api/aula/cursos/{curso_ref}/medios/{media_ref}/{ruta}` | GET · HEAD | Archivo interno (`index.html`, `…_es.html`) o `subtitulos` / `transcripcion` |
| `/api/aula/fuente/?fuente=` | GET | Estado de la fuente, **nunca 503**: `{fuente, disponible, motivo, sugerencia, huella, cursos_instalados[{curso_ref, version, titulo}]}` |
| `/api/aula/cursos/{curso_ref}/evaluar/?fuente=` | POST | `{version?, objeto_ref, pregunta_ref, respuesta}` o `{version?, items[…]}` (≤ 200) → veredicto `{puntaje, puntaje_maximo, correcta, requiere_correccion_manual, pendiente, retroalimentacion[]}` sin ninguna clave. No escribe: el intento es de MOD-010 ([05](05-contrato-biblioteca.md) §4) |
| `/api/aula/pruebas/cursos/` | GET | La lista con la fuente `ejemplo` forzada |
| `/api/aula/pruebas/curso/?rol=` | GET | **El endpoint de prueba**: «Ciencias naturales · Estados de la materia y sus cambios» |

La ficha (cabecera de la vista, sin estructura):

```json
{
  "fuente": "ejemplo", "esquema": "1.0",
  "curso_ref": "avacom.co.lower-secondary.6.science.states-of-matter", "version": "1.0.0",
  "titulo": "Estados de la materia y sus cambios", "subtitulo": "Sólido, líquido, gas y lo que pasa al calentar o enfriar",
  "idioma": "es-CO", "grupo_traduccion": "avacom.lower-secondary.6.science.states-of-matter",
  "clasificacion": { "pais": "CO", "idioma": "es-CO",
                     "nivel": {"codigo": "lower_secondary", "nombre": "Básica secundaria", "orden": 2},
                     "grado": {"codigo": "6", "nombre": "Sexto", "orden": 6},
                     "asignatura": {"codigo": "science", "nombre": "Ciencias naturales"},
                     "tema": {"codigo": "states-of-matter", "nombre": "Estados de la materia", "orden": 2} },
  "duracion_estimada_min": 180, "modos": ["simple", "class", "exam", "review", "free_learning"],
  "portada_url": "/api/aula/cursos/avacom.co.lower-secondary.6.science.states-of-matter/medios/img-cover-matter/?fuente=ejemplo",
  "lecciones": 3, "objetos": 8, "medios": 8,
  "resumen": { "lecciones": 3, "objetos": 8, "objetos_por_tipo": {"lecture": 2, "explanation": 1, "simulation_lab": 2, "activity": 2, "exam": 1},
               "medios": 8, "preguntas": 9, "fuera_de_alcance": [{"objeto_ref": "l3-exam", "tipo": "exam", "modulo": "MOD-010"}] }
}
```

Una lámina de la presentación (`lecciones[0].objetos[0].laminas[1]`, rol docente):

```json
{ "unidad_ref": "l1-lecture-s2", "indice": 2, "titulo": "Tres estados, tres formas de ordenarse", "duracion_seg": 420,
  "bloques": [
    { "tipo": "image", "componente": "imagen", "media_ref": "img-particles",
      "url": "/api/aula/cursos/avacom.co.lower-secondary.6.science.states-of-matter/medios/img-particles/?fuente=ejemplo",
      "pie": "Las mismas partículas, ordenadas de tres maneras.", "mime": "image/png", "titulo": "Modelo de partículas",
      "texto_alternativo": "Tres recipientes. …", "ancho": 1280, "alto": 720 },
    { "tipo": "list", "componente": "lista", "ordenada": false,
      "items": ["**Sólido:** forma y volumen propios. …", "…", "…"],
      "items_tramos": [[{"texto": "Sólido:", "negrita": true}, {"texto": " forma y volumen propios. …", "negrita": false}], …] }
  ],
  "notas_docente": {"tips": ["Señale cada recipiente y pregunte qué tan libres se mueven las partículas."]} }
```

Un laboratorio con parámetros de lanzamiento (`lecciones[1].objetos[1]`):

```json
{ "objeto_ref": "l2-lab-heating", "tipo": "simulation_lab", "componente": "laboratorio_web",
  "titulo": "Laboratorio: curva de calentamiento", "modos": ["class", "review"], "duracion_estimada_seg": 900,
  "parametros_lanzamiento": {"startTemp": -10, "altitudeMeters": 0},
  "url_lanzamiento": "/api/aula/cursos/…/medios/sim-heating-curve/index.html?fuente=ejemplo&startTemp=-10&altitudeMeters=0",
  "simulacion": { "media_ref": "sim-heating-curve", "clase": "simulation", "componente": "webview", "mime": "text/html",
                  "url": "/api/aula/cursos/…/medios/sim-heating-curve/index.html?fuente=ejemplo", "base_url": "/api/aula/cursos/…/medios/sim-heating-curve/?fuente=ejemplo",
                  "simulacion": {"entrada": "index.html", "proveedor": "avacom", "tecnologia": "html5_canvas", "orientacion": "landscape",
                                 "ajustes": ["scale_to_fit", "block_network"], "destinos": ["screen", "tablet"], "ancho_diseno": 1280, "alto_diseno": 720} },
  "objetivo_aprendizaje": "Reconocer que durante un cambio de estado la temperatura se mantiene constante …",
  "instrucciones": "Enciende el calentador y observa la gráfica de temperatura contra tiempo.",
  "pasos": ["Empieza con hielo a -10 °C.", "Enciende el calentador.", "Marca en la gráfica dónde ocurre cada cambio de estado."],
  "preguntas_guia": ["¿Qué pasa con la temperatura mientras el hielo se derrite?"] }
```

Una pregunta de completar, tal como la ve el estudiante (sin `acceptedAnswers`, sin `wrongAnswers`, sin `feedback`):

```json
{ "pregunta_ref": "l1-act-q3", "tipo": "fill_blanks", "componente": "completar", "enunciado": "Completa.",
  "tema_ref": "st-liquid", "dificultad": 2, "duracion_estimada_seg": 40, "puntos": 2, "credito_parcial": true,
  "plantilla": "Un líquido tiene volumen {{b1}} y toma la {{b2}} del recipiente.",
  "espacios": [{"espacio_ref": "b1", "modo_entrada": "select", "opciones": ["propio", "variable"]},
               {"espacio_ref": "b2", "modo_entrada": "select", "opciones": ["forma", "masa"]}] }
```

### 9.3 · El endpoint de prueba y su evolución para el componente MAUI

**Tarea 2 · lo que se pidió.** Un endpoint que permita consumir el curso «Ciencias naturales» de `example.json`. Está en `GET /api/aula/pruebas/curso/` y, con la referencia real, en `GET /api/aula/cursos/{curso_ref}/?fuente=ejemplo`. Lee el archivo en cada petición (ruta en `AVACOM_AULA_CURSO_EJEMPLO`), no lo guarda, y lo entrega por la misma vista que usará la biblioteca real.

**Tarea 3 · lo que se modificó pensando en el frontend .NET MAUI.** Un reenvío del JSON crudo habría servido para «ver algo», pero no para construir el componente. Cambios respecto a ese punto de partida:

| Cambio | Por qué le sirve al componente MAUI |
|---|---|
| `componente` en cada objeto, bloque, medio y pregunta | Un `DataTemplateSelector` elige la vista por un campo, sin conocer el esquema de la biblioteca |
| Nombres estables en español `snake_case` (`curso_ref`, `laminas`, `unidad_ref`…) y los códigos originales en `tipo` | Los DTO de C# se escriben una vez; los códigos de la biblioteca siguen visibles para trazabilidad |
| `tramos[]` en todo texto con marcado (`**negrita**`, `*cursiva*`, `$matemática$`) | `FormattedString` directo; nada de Markdown en la tableta |
| `url`, `url_lanzamiento`, `url_pagina_inicial`, `subtitulos_url`, `transcripcion_url` **relativas al backend** | El cliente sólo antepone su `BaseUri`; la tableta nunca conoce la biblioteca (línea base §1) |
| Medios de **marcador** para el ejemplo (PNG, WAV, PDF de 3 páginas, HTML de simulación, VTT, texto) con `Range` y `HEAD` | Se pueden probar `Image`, `MediaElement`, el visor PDF y la `WebView` sin la biblioteca. El video se responde `404` explicativo: un MP4 no se fabrica |
| `rol` (`estudiante` por defecto) y barrido de claves para todos | La tableta del alumno recibe exactamente lo que puede ver; el panel del docente recibe además las notas |
| `exam` marcado `fuera_de_alcance` con `modulo` | El componente pinta la estructura completa y deja el examen a MOD-010 |
| Rutas de lección y objeto sueltos | La tableta que sigue la clase baja sólo lo que el selector señala |
| Alias `ejemplo` y resolución automática de la fuente | El desarrollador de MAUI no necesita el `id` largo ni el parámetro para empezar |
| `resumen` con conteos y `objetos_por_tipo` | Cabecera y pruebas de la pantalla sin recorrer el árbol |

### 9.4 · Medios y marcadores de ejemplo

| `kind` | Con `fuente=ejemplo` | Con `fuente=biblioteca` |
|---|---|---|
| `image` | PNG generado (banda roja, recuadro; usa `width`/`height`) | Paso a través de una **sesión de medios** (`POST /v2/media-sessions` → URL en `mediaPort`, [05](05-contrato-biblioteca.md) §2) |
| `audio` | WAV de un tono de 1 s | Paso a través |
| `pdf` | PDF válido con `pageCount` páginas numeradas | Paso a través |
| `simulation` | HTML5 con lienzo de partículas que respeta `scale_to_fit`, lee `startTemp` del query y bloquea toda red | `…/medios/{ref}/{ruta}` → `<baseUrl de la sesión>{mediaId}/{ruta}` en el servidor de medios |
| `video` | `404 referencia_no_encontrada` con `sugerencia` | Paso a través con `Range` → `206 Content-Range` |
| `…/subtitulos` · `…/transcripcion` | WebVTT y texto de ejemplo cuando el medio declara `captionsPath` / `transcriptPath` | Q-45 |

Toda respuesta de marcador lleva `X-Avacom-Marcador: ejemplo` y `X-Avacom-Rotulo` para que el cliente pueda avisar que está viendo un sustituto.

### 9.5 · La sesión de clase

| Ruta | Verbo | Función | Cuerpo → respuesta |
|---|---|---|---|
| `/api/aula/sesiones/` | GET | Listar (y archivar las cerradas hace > 24 h) | `?estado=abierta,suspendida&grupo=&profesor=` → `{sesiones[], archivadas_ahora, servidor_en}` |
| `/api/aula/sesiones/` | POST | **FUN-064** Iniciar | `{via, grupo_id?, curso_ref?, leccion_ref?, objeto_ref?, nodo_ref?, fuente?, plan_id?, superficie?, profesor_id, profesor_rotulo?}` → `201` detalle docente |
| `/api/aula/sesiones/{id}/` | GET | PAN-001 / PAN-022 | Detalle docente: sesión + `selector` + `seguimiento` + `pantallas_bloqueadas` + `controles` + `participantes` + `conteo` + `distribuciones` + `avisos` + `resumen` |
| `/api/aula/sesiones/unirse/` | POST | **FUN-067 / FUN-077** | `{codigo_union, persona_id, persona_rotulo?, dispositivo?, plataforma?, version_app?, participante_id?, sesion_usuario_id?}` → `201` (nuevo) / `200` (readmisión) estado para la tableta + `nuevo`, `en_espera`. Con `dispositivo`, MOD-009 reconoce (o registra) la tableta y abre su sesión de alumno; `403 dispositivo_bloqueado` / `dispositivo_inactivo` si no puede entrar |
| `…/{id}/participantes/{pid}/admitir/` · `rechazar/` · `expulsar/` | POST | **FUN-067 / 068 / 078** | `{motivo?}` → participante |
| `…/{id}/participantes/{pid}/presencia/` | POST | **FUN-073** | `{estado: conectado|reconectando|salio, dispositivo?, avisos_desde?}` → estado para la tableta |
| `…/{id}/estado/?participante=&avisos_desde=` | GET | Sondeo de la tableta | Estado para la tableta (`intervalo_sondeo_ms: 2000`) |
| `…/{id}/selector/` | POST | **FUN-069 · BR-049** | `{objeto_ref, unidad_ref?, leccion_ref?}` o `{media_ref, rotulo}` → `201` selector vigente |
| `…/{id}/controles/` | POST | **FUN-074 · BR-050** | `{tipo: bloqueo|seguimiento, activo, motivo?}` → `{cambio, seguimiento, pantallas_bloqueadas, controles}` |
| `…/{id}/distribuciones/` | POST | **FUN-070 · CAP-040** | `{clase: recurso|actividad, objeto_ref?|media_ref?, alcance?, participantes[]?, intentos_permitidos?, tiempo_limite_seg?, disponible_estudio?}` → `201` distribución con `entregas`, `destinatarios` y `excluidos_bloqueados`; `409 sin_participantes_admitidos` (con `excluidos_bloqueados`) si no queda ninguna tableta que pueda recibirla |
| `…/{id}/distribuciones/{did}/confirmar/` | POST | Confirmación de la tableta | `{participante_id, estado?: entregado|fallido}` |
| `…/{id}/distribuciones/{did}/cerrar/` | POST | **FUN-071** | → distribución cerrada |
| `…/{id}/distribuciones/{did}/resultados/` | POST | **FUN-072** | → `{distribucion, mostrado_en}` (los datos agregados son de MOD-010/011) |
| `…/{id}/avisos/` | POST | **FUN-075** | `{texto, participante_id?}` → `201` aviso |
| `…/{id}/codigo/rotar/` | POST | **FUN-066** | → `{codigo_union, rotado_en}` |
| `…/{id}/suspender/` | POST | Caída del nodo / manual | `{causa: caida_nodo|corte_electrico|reinicio|manual}` → detalle |
| `…/{id}/reanudar/` | POST | **FUN-076 · BR-051** | → detalle (mismo código, selector y participantes) |
| `…/{id}/cerrar/` | POST | **FUN-079 · BR-052** | `{origen?, forzar?}` → detalle con `resumen`; `409 actividades_abiertas` si hay actividades abiertas y no se fuerza (MSG-016) |

Iniciar desde una lección (respuesta abreviada):

```json
{ "id": "e9db8ea5-…", "estado": "abierta", "activa": true, "codigo_union": "613385",
  "via_origen": "leccion", "fuente_curso": "ejemplo",
  "curso_ref": "avacom.co.lower-secondary.6.science.states-of-matter", "curso_version": "1.0.0",
  "curso_rotulo": "Estados de la materia y sus cambios", "leccion_ref": "l1-three-states", "leccion_rotulo": "Los tres estados de la materia",
  "profesor_id": "prof-1", "profesor_rotulo": "Prof. Gómez", "superficie": "pantalla", "iniciada_en": 1789683790346,
  "selector": { "objeto_ref": "l1-lecture", "objeto_tipo": "lecture", "unidad_ref": "", "rotulo": "Todo lo que nos rodea es materia", "vigente": true },
  "seguimiento": true, "pantallas_bloqueadas": false,
  "conteo": {"total": 0, "conectados": 0, "reconectando": 0, "esperando": 0, "salieron": 0},
  "participantes": [], "distribuciones": [], "avisos": [], "resumen": null, "servidor_en": 1789683790382 }
```

Lo que recibe la tableta al unirse y en cada sondeo (`estado/`): **sin código de unión ni lista de participantes**, que son de la superficie del aula.

```json
{ "sesion": { "id": "e9db8ea5-…", "estado": "abierta", "fuente_curso": "ejemplo", "curso_ref": "avacom.co.…", "curso_version": "1.0.0",
              "curso_rotulo": "Estados de la materia y sus cambios", "leccion_ref": "l1-three-states", "leccion_rotulo": "Los tres estados de la materia",
              "grupo_rotulo": "", "profesor_rotulo": "Prof. Gómez" },
  "activa": true,
  "participante": { "id": "ae63f13b-…", "persona_id": "ana-perez", "persona_rotulo": "Ana Pérez", "dispositivo": "student-tab-07",
                    "estado": "conectado", "admision_nominal": false, "ingreso": 1789683790399, "ultimo_latido_en": 1789683790399 },
  "selector": { "objeto_ref": "l1-lecture", "objeto_tipo": "lecture", "unidad_ref": "l1-lecture-s2", "unidad_indice": 2,
            "rotulo": "Tres estados, tres formas de ordenarse", "declarado_en": 1789683790422 },
  "seguimiento": true, "pantallas_bloqueadas": true,
  "pendientes": [ { "id": "2f2b93ef-…", "clase": "actividad", "objeto_ref": "l1-activity", "objeto_tipo": "activity",
                    "rotulo": "Practica: los tres estados", "entrega": "pendiente", "abierta_en": 1789683790460 } ],
  "avisos": [ { "id": "b27cf0c3-…", "participante_id": null, "texto": "Miren la pantalla, por favor.", "enviado_en": 1789683790482 } ],
  "servidor_en": 1789683790502, "intervalo_sondeo_ms": 2000 }
```

El resumen al cerrar:

```json
{ "participantes": 1, "conectados_maximo": 1, "admitidos_nominal": 0, "selectores": 2, "distribuciones": 1, "actividades": 1,
  "avisos": 1, "pendientes": 0, "duracion_ms": 164, "origen_cierre": "profesor", "consolidado_en": 1789683790510 }
```

### 9.6 · Tiempo real

Hoy la tableta **sondea** `GET …/estado/` cada `intervalo_sondeo_ms` (2 s), lo que cumple BR-049 (≤ 3 s) en un aula de 50 dispositivos con un backend en el mismo equipo. El paso siguiente es el canal de Django Channels ya previsto en [07 · Comunicación](../07-comunicacion-ops-student.md) §4.8: `ws://<IP>:8000/ws/aula/{sesion_id}/?participante=` que difunde, tal cual, los eventos de `m07_evento_salida` (selector, controles, distribuciones, avisos, cierre). El contrato de los eventos no cambia: es el de §6 (Q-51).

### 9.7 · Degradación

| Situación | Respuesta | Escribe |
|---|---|---|
| Biblioteca cerrada y `fuente=biblioteca` | `503 fuente_no_disponible` con `sugerencia` | No |
| Capacidad no publicada | `501 capacidad_ausente` con `capacidades` | No |
| Manifiesto de ejemplo ausente o ilegible | `503` con la ruta esperada y cómo configurarla | No |
| Iniciar o proyectar con la fuente caída | `503` (FUN-064/069 exigen que el recurso esté disponible) | No |
| Video del ejemplo | `404` explicativo con `sugerencia` | No |
| Código de una sesión cerrada | `404 codigo_invalido` (BR-052) | No |
| Sesión suspendida | Unirse sí (`reconectando`); selector, controles, distribuciones y avisos `409` hasta reanudar | Sólo presencia |
| «No se pudo comprobar» | Nunca se marca ausente nada: la sesión se abre igual por vía `libre` | — |

---

## 10 · Trazabilidad

| Maestro | Tabla / regla | Ruta | Prueba |
|---|---|---|---|
| CAP-037 · FUN-064 · BR-044/045/046 · DEC-035 | `m07_sesion`, `ux_m07_profesor_abierta`, `ux_m07_grupo_activa` | `POST sesiones/` | `IniciarTests` |
| FUN-065 · FUN-066 · CMP-012 | `codigo_union`, `ux_m07_codigo` | `POST codigo/rotar/` | `test_rotar_el_codigo` |
| CAP-038 · FUN-067/068/077/078 · BR-047/048 | `m07_participante`, `m07_presencia`, `ux_m07_part` | `unirse/`, `admitir/`, `rechazar/`, `expulsar/` | `ParticipantesTests`, `ConPadronTests` |
| FUN-073 | `m07_presencia`, `ultimo_latido_en` | `presencia/`, `estado/` | `test_presencia_declarada_y_estado_para_la_tableta` |
| CAP-039 · FUN-069 · BR-049 | `m07_selector`, `ux_m07_selector_vigente` | `POST selector/` | `test_declarar_el_selector_lo_ve_la_tableta` |
| CAP-042 · FUN-074 · BR-050 | `m07_control`, `ux_m07_control_abierto` | `POST controles/` | `test_bloquear_pantallas_y_liberar_el_seguimiento` |
| CAP-040 · FUN-070/071/072 | `m07_distribucion`, `m07_distribucion_entrega` | `distribuciones/…` | `test_lanzar_una_actividad_confirmar_y_cerrar` |
| FUN-075 | `m07_aviso` | `POST avisos/` | `test_avisos_al_grupo_y_a_una_tableta` |
| CAP-041 · FUN-076 · BR-051 | Estados `suspendida ⇄ abierta` | `suspender/`, `reanudar/` | `test_suspender_y_reanudar_…` |
| CAP-045 · FUN-079 · BR-052 · MSG-016 | `m07_resumen`, `exigir_abierta` | `cerrar/` | `test_cerrar_consolida_el_resumen_y_no_se_reabre` |
| Sección H (archivo a 24 h) · INV-025 | `TRANSICIONES`, `ARCHIVO_TRAS_MS` | `GET sesiones/` | `test_las_cerradas_se_archivan_…` |
| Sección L (16 eventos) | `m07_evento_salida` | todas | aserciones de `eventos()` en cada prueba |
| Sección J (11 permisos) | `dominio.sesion.PERMISOS`, `AutorizacionPrototipo` | todas las del profesor | `ConPadronTests` (403 al estudiante) |
| Art. 13/14 · CV-08 · regla de oro | Sin tablas de curso; `*_ref`/`*_rotulo` | — | `test_el_esquema_es_solo_de_aula_sin_curso_ni_claves` |
| Art. 14.5 · CA-08 | `CLAVES_DE_CORRECCION`, `sin_claves` | `cursos/…` | `test_la_actividad_trae_…_sin_ninguna_clave`, `test_las_notas_del_docente_…` |

---

## 11 · Pruebas

| Suite | Qué comprueba |
|---|---|
| `classroom_engine.tests.test_arquitectura` (3) | Sin frameworks en dominio/aplicación; vistas sin ORM; esquema sólo `m07_*` sin contenido ni claves |
| `classroom_engine.tests.test_curso` (30) | Endpoint de prueba, clasificación, componentes, láminas/tramos, lectura (audio/pdf), laboratorio (WebView, parámetros), seis preguntas sin claves, examen fuera de alcance, notas del docente por rol, lista por asignatura, lección/objeto sueltos, resolución automática de la fuente, fuente desconocida, sin `link.json` («sin contenido», `fuente/`), la fuente de ejemplo no califica pero valida la forma, marcadores (PNG/WAV/PDF/HTML/VTT/texto, `Range`, `HEAD`), video 404; normalizador (tramos, agrupación, `sin_claves`, `localizar`, árbol del contrato 1); **la misma vista servida por la API de Contenido v2** (host de pruebas: `mode`/`profile`, opciones barajadas por `id`, lista, `?version=`, 401 con un solo reintento, códigos de error, estado de la fuente, medios en paso a través, evaluar por tipo con crédito parcial decimal, abierta pendiente, lote) |
| `classroom_engine.tests.test_respuestas` (5) | La forma de `response` por tipo de pregunta (17 casos inválidos), tipo desconocido reenviado, `score`/`correct` nulos y decimales, corrección manual sin nota |
| `classroom_engine.tests.test_sesiones` (21) | Iniciar por las cuatro vías, BR-045, DEC-035, vías mal formadas, unirse y readmitir, código equivocado, presencia, expulsar/readmitir, selector, controles, distribuciones, avisos, rotar código, suspender/reanudar, cerrar con resumen y BR-052, archivo a 24 h, padrón de MOD-001 (inscrito entra, invitado espera, 403 al estudiante) |

Ejecutar: `cd backend; .venv\Scripts\python manage.py test classroom_engine` (o toda la suite sin argumento).

---

## 12 · Preguntas abiertas

| Q | Pregunta | Estado | Propuesta |
|---|---|---|---|
| Q-44 | ¿Cómo publica la biblioteca el manifiesto 1.0? | **Cerrada** ([05](05-contrato-biblioteca.md)) | Por la **API de Contenido v2**: `GET /v2/courses/{courseId}?version=&mode=&profile=` devuelve el curso 1.0 **recortado** (sin claves, sin `teacherNotes` para el alumno). El normalizador no cambió; la fuente `biblioteca` habla v2 con `link.json` + `Bearer` |
| Q-45 | ¿Cómo se piden los medios de un paquete? | **Cerrada** ([05](05-contrato-biblioteca.md) §2) | `POST /v2/media-sessions {courseId, mediaIds}` devuelve URL-capacidad efímeras en el servidor de medios (`mediaPort`), con `@captions`, `@transcript` y los archivos de cada simulación; el aula abre una sesión de un minuto por petición y reenvía los bytes con `Range` |
| Q-46 | Correspondencia `level.code` ↔ `nivel_clave` de MOD-001 | **Abierta** | `preschool → preescolar`, `primary → primaria`, `lower_secondary → secundaria`, `upper_secondary → bachillerato`. Decide qué política de credencial y qué familia de interfaz (DEC-039) aplican al curso |
| Q-47 | Presentaciones `.pptx` | **Abierta** | El esquema no las trae: la presentación es `lecture.slides`. Si la biblioteca recibe `.pptx`, los convierte ella (láminas, PDF o HTML) y publica el resultado como medio; el LMS no analiza Office |
| Q-48 | ¿Quién ejecuta el `exam` y las preguntas del manifiesto? | **Parcial** ([05](05-contrato-biblioteca.md) §4 y §10) | La biblioteca califica por `POST /v2/evaluate` (`courseId`, `version`, `objectId`, `questionId`, `response` por tipo) y el aula lo expone en `POST /api/aula/cursos/{ref}/evaluar/` con la forma validada y el veredicto traducido (`puntaje` nulo o decimal, `requiere_correccion_manual` → pendiente). **Falta** que MOD-010 guarde el intento con `version` y estado `pendiente_correccion`, y el `exam` sigue siendo suyo |
| Q-49 | `asignacion_ref` al lanzar una actividad | **Abierta** | Hoy `''`. MOD-010 debe emitir la asignación (`m10_asignacion.sesion_id`) al recibir `aula.actividad.lanzada.v1` y devolverla por el puerto `Evaluacion` |
| Q-50 | Permisos `classroom.*` en MOD-001 | **Abierta** | Sembrar los once (`classroom.start … classroom.end`) con alcance `ASSIGNED_GROUPS` para TEACHER y `ORGANIZATION` para ADMIN; sustituir `AutorizacionPrototipo` por `PoliticaAutorizacion` |
| Q-51 | Canal en vivo | **Abierta** | Channels con `InMemoryChannelLayer` (Q-36) y ruta `ws/aula/{sesion_id}/`, difundiendo los eventos de §6. Mientras, sondeo de 2 s |
| Q-52 | FK físicas a grupo, profesor y dispositivo | **Abierta** | Cuando MOD-002 y MOD-009 existan con dueño; hoy referencias lógicas validadas por `Identidad` |
| Q-53 | Detección de caída y cierre por inactividad | **Abierta** | MOD-015 debe llamar a `suspender/` (causa `caida_nodo`) al arrancar con sesiones abiertas y `cerrar/` con `origen: inactividad` a los 20 min (MSG-025). La ventana de 3 min de BR-051 se registra (`ventana_ms` en auditoría) y no se impone |
| Q-54 | Plan de clase (MOD-006) y relevo de profesor (DEC-035/038) | **Abierta** | `plan_id` y `relevo_de_sesion_id` están en el modelo; los casos de uso llegan con sus módulos |
