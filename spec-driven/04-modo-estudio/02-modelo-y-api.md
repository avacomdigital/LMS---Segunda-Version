# 02 · Modo Estudio (MOD-008) · Modelo `m08_*` y API `/api/modo-estudio/`

| Campo | Valor |
|---|---|
| Estado | **Contrato de diseño** (2026-09-29). Lo implementan `backend/modo_estudio/` (Django/DRF), `src/Avacom.Lms.Core/Estudio/` (cliente, cola y almacén locales), `src/Avacom.Lms.Student/ModoEstudio/` (pantalla «Modo estudio · Mis lecciones») y `src/Avacom.Lms.Ops/Pages/EstudioPage.*` (asignar y ver quién completó). Lo construido y cómo se comprobó está en §10–§12; el frontend, en [03 · Frontend](03-frontend-student-y-ops.md). |
| Módulo | **MOD-008 · Modo Estudio** del Documento Maestro (DOM-004). 6 capacidades (CAP-046…051), 11 funciones (FUN-080…090), 10 eventos, 6 permisos `study.*`, escenario TST-079. |
| Requisitos de partida | La tabla 008-01…008-09 de [01 · Introducción](01-introduccion.md), las 15 funciones de backend y los 34 apartados del frontend de ese mismo documento. |
| Modelo de datos | Segunda versión (`specs/analisis/segunda-version-modelo.md`): `asignacion` (nueva, dominio Evaluación), el paquete de estudio, y `dispositivo` con `perfil` y `asignado_a_id` (009-06). |
| Dueño único | MOD-008 escribe sólo `m08_*`. El Maestro dice que **no es propietario de ningún grupo de datos** («opera consumiendo hechos de otros módulos»); mientras MOD-010 (asignaciones, intentos) no tenga dueño, las tablas `m08_asignacion` y `m08_practica` viven aquí como **provisionales**, igual que `m07_intento` vive provisional en MOD-007. El resto lo consume por la interfaz de su dueño (§6). |
| Revisión | **2026-09-29 · pedido del usuario (D-15 «identidad declarada»).** En Modo Estudio el alumno **elige quién es** (sin código ni contraseña) y el aparato asignado deja de ser condición para estudiar. Quedan **revisadas** D-1, D-2, D-3 y D-11; Q-69 queda respondida. Las rutas nuevas y los campos que cambian están en §4.1 y §4.5. |

---

## 1 · Decisiones (y por qué)

El Maestro, la tabla de requisitos y el código existente no dicen siempre lo mismo. Estas son las lecturas que se tomaron; ninguna se guardó en silencio.

| # | Decisión | Por qué / alternativa |
|---|---|---|
| D-1 | **(Revisada por D-15.) El modo de estudio sirve en CUALQUIER tableta** registrada, activa y no bloqueada, compartida o asignada. El menú de Student muestra el hexágono si `GET /estado/` responde `disponible = true` (= nodo instalado y tableta utilizable). La **descarga** sí sigue siendo del dueño de una tableta asignada: lo que niega el nodo es el **paquete** en cualquier otra (BR-054, FUN-085, `estudio.descarga.denegada.v1`). | Antes: «existe sólo en un aparato asignado a la persona» (008-01). El usuario lo cambió el 2026-09-29: FUN-080 dice «en una tableta compartida» y así queda (Q-69). |
| D-2 | **(Revisada por D-15.) Un aparato asignado ya no rechaza a quien no es su dueño**: otro alumno estudia en él (lectura, lección, progreso, práctica, completar, sesión, sync). Lo único que sigue siendo del dueño es el **paquete**: si otra persona lo pide, 403 `descarga_denegada` con `motivo = dispositivo_ajeno` y MSG-046. `dispositivo_ajeno` ya no es un error HTTP. | Antes: 403 `dispositivo_ajeno` para todo (BR-058). El nodo no puede verificar quién sostiene la tableta; la asignación nominal de OPS sigue decidiendo quién se lleva material. |
| D-3 | **(Revisada por D-15.) Quién es el alumno.** Con JWT (MOD-001): el del token. Sin sesión (Q-34 abierta, prototipo): el `alumno_id` que declara la tableta —cuerpo o `?alumno_id=`— en **cualquier** aparato, compartido o asignado; **debe existir en el padrón y estar activo** (403 `sin_permiso` con `motivo = alumno_desconocido`). Sin `alumno_id`: un aparato asignado toma a su **dueño** (compatibilidad); uno compartido es 400 `falta_alumno`. | «Esto es un LMS offline y no hay manera de verificar que los estudiantes sean los estudiantes por un sistema central: se maneja así hasta nuevo aviso.» La pantalla «¿Quién eres?» sale de `GET /estudiantes/`. |
| D-4 | **Un «bloque» es la unidad de avance de una lección**, en el orden en que se ve: cada lámina de una `lecture`, cada página de una `explanation`, cada `simulation_lab` y cada `activity` (la práctica). El `exam` **no** es bloque: es evaluación formal y queda fuera (BR-055). Todos los bloques son obligatorios salvo que se declare lo contrario. «Atendido» significa: lámina o página **vista**; laboratorio **abierto**; práctica **terminada al menos una vez** (no se exige nota). | El esquema de curso 1.0 no tiene marca de «obligatorio»; hasta que la haya, todo lo que se estudia lo es. FUN-087 dice «todos los bloques obligatorios fueron atendidos», no «aprobados». Pregunta Q-66 para el CTO. |
| D-5 | **La práctica es una actividad de aprendizaje separada** (`m08_practica`, `modo = 'estudio'` con `CHECK`). No usa `m07_intento` ni `m10_intento`, no consume intentos de evaluación formal y **no tiene tope de intentos** («Puedes intentarlo nuevamente»). El módulo no publica nota ni la guarda como calificación (DEC-032). | BR-055, y la advertencia de la propia introducción: «nunca reutilizar silenciosamente el flujo formal». |
| D-6 | **La clave de respuesta sólo vive en la biblioteca** (`POST /v2/evaluate`). Con el nodo a la vista la práctica califica en ≤ 2 s (NFR-012). **Sin el nodo, lo respondido se guarda en la cola de la tableta y se califica al integrarse**; mientras tanto el alumno ve «Guardado en tu tableta» (MSG-011), no un veredicto. | Enviar claves a la tableta viola la regla de oro de la biblioteca (`answer_keys_forbidden`). Pregunta Q-67: si el CTO quiere feedback sin red, hay que pedir a Contenido un mecanismo de verificación local. |
| D-7 | **El paquete de estudio** es la lección (vista de aula **sin claves**) más los medios que referencia, con su `huella` (SHA-256 del manifiesto), su tamaño y su vigencia. Las **simulaciones** (`simulation_lab`) no se empaquetan: son carpetas sin listado en la API; el bloque dice «necesita el aula». La descarga es reanudable (`Range`) y se guarda cifrada en el aparato. | El esquema de medios no trae tamaño ni huella: el nodo los mide al preparar el paquete. |
| D-8 | **Vigencia**: `fecha_limite + gracia` si la asignación tiene fecha; si no, 14 días (`AVACOM_ESTUDIO_VIGENCIA_DIAS`). Un paquete cuya versión de curso ya no es la instalada está `vencido` (`motivo = version_nueva`). Vencido se evalúa al leer (no hay tarea programada). | Una lección no debería quedarse eternamente en una tableta; MSG-045 «liberamos material vencido». |
| D-9 | **Fecha límite.** `blando` (por defecto, DEC-014): siempre se acepta; lo capturado después de la fecha se marca `fuera_de_plazo`. `endurecido`: la asignación «cierra al vencer»; lo **capturado** antes y **recibido** dentro de la gracia (15 min, DEC-019) se acepta; lo capturado antes pero recibido después queda `pendiente_decision` del profesor (nunca se descarta en silencio, BR-074); lo capturado después del cierre se rechaza. | Se reutiliza `classroom_engine.dominio.actividad.politica_de_recepcion`. |
| D-10 | **Idempotencia del trabajo sin red**: cada evento de la cola lleva `emisor_id` (identidad de la instalación) y `secuencia` monotónica; `m08_sincronizacion` tiene `UNIQUE(emisor_id, secuencia)`. Repetir el envío devuelve el mismo resultado sin duplicar nada. Las respuestas dentro de una práctica (JSON) se fusionan con `fusionar_respuestas` (INV-013, mayor secuencia gana), validado dentro de la transacción. | DEC-023, BR-060, BR-138, TST-029. |
| D-11 | **(Revisada por D-15.) Sincronizar no exige sesión** (BR-137): sin JWT se autoriza por el aparato (registrado, activo, no bloqueado) y por el `alumno_id` declarado (existe y está activo). **Ya no se exige que el aparato sea del alumno**, ni que esté asignado. Cada evento comprueba después que la asignación le alcance. | TST-029. Con varias personas en una misma instalación, `(emisor_id, secuencia)` debe seguir siendo único en ella (D-10): la misma secuencia de otra persona se rechaza como `emisor_ajeno`. |
| D-12 | **Permisos.** Los seis `study.*` del Maestro son de alcance propio (`SELF`) y sólo del rol `STUDENT` (el administrador «no accede al modo de estudio del alumno»). Para CAP-050/051, que el Maestro deja sin permiso, se añaden dos **del proyecto** (como `device.block`): `study.assignment.create` y `study.assignment.review`, para `TEACHER` (sobre sus grupos) y `ADMIN`. | §J de MOD-008 y «Reparto de permisos por rol». |
| D-13 | **Alcance por nivel (008-09)** no se implementa: no hay dónde guardar la configuración por nivel (DEC-017). Queda como pregunta Q-68 con la tabla de adaptación del Maestro (preescolar: sin modo de estudio; primaria: tarea sencilla; secundaria: tarea y repaso; bachillerato: tarea, proyecto y repaso; preuniversitario: paquete descargable completo). | Preguntar al CTO, como pide la tabla. |
| D-14 | **Asignación nominal de aparatos (FUN-092/093)** entra en MOD-009 (`device_manager`): `m09_dispositivo.perfil` (`compartido` por defecto · `asignado`) y `asignado_a_id`, con `POST /api/dispositivos/{id}/asignar/` y `/liberar/`. Liberar exige que el aparato no tenga un paquete de estudio activo. | 008-01 / 009-06 y FUN-093. |
| D-15 | **Identidad declarada · 2026-09-29 · pedido del usuario.** En Modo Estudio el alumno **elige quién es**, sin código ni contraseña (la clase en vivo sí pide código; el estudio no): como la asignación ya tiene un grupo, la tableta pregunta «¿Quién eres?» con los nombres de `GET /estudiantes/` y declara `alumno_id` en cada llamada. Revisa D-1, D-2, D-3 y D-11 y responde Q-69: **el modo de estudio sirve en cualquier tableta**. El paquete sigue siendo sólo del dueño de una tableta asignada (BR-054). | «Clase en vivo sí debería solicitar código, Modo Estudio no; como Modo Estudio ya tiene asignado un grupo, debería solicitar cuál es el estudiante que va a realizar su estudio asignado, para completar el estudio y que le aparezca al profesor. Esto es un LMS offline y no hay manera de verificar que los estudiantes sean los estudiantes por un sistema central: se maneja así hasta nuevo aviso.» Cuando exista verificación central, sólo cambia cómo se resuelve `alumno_id`. |

---

## 2 · Modelo `m08_*`

```
 m08_asignacion ──1:N── m08_tarea ──1:N── m08_practica          (una tarea = una asignación para un alumno)
        │
        └──1:N── m08_paquete   (asignación × alumno × aparato)
 m08_sincronizacion   (libro de eventos recibidos de la cola: UNIQUE emisor_id + secuencia; sin FK)
 m08_evento_salida    (outbox estudio.*.v1, sin FK)
 m09_dispositivo      + perfil, asignado_a_id   (MOD-009)
```

Convenciones del proyecto: prefijo por módulo (CV-01), ids de texto (CV-02), tiempo en milisegundos del reloj del nodo (CV-03, BR-062), nada se borra (CV-05), invariantes como restricciones (CV-07), referencias a otros módulos lógicas (CV-08). **Ninguna tabla guarda contenido del curso ni claves** (artículo 14): sólo referencias `*_ref`, rótulos de evidencia y la estructura de bloques como referencias.

### 2.1 · `m08_asignacion` (nueva · provisional hasta MOD-010)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | uuid |
| `grupo_id` · `grupo_rotulo` | char(36) · char(120) | `m01_grupo` (lógica); vacío si la selección es de alumnos sueltos sin grupo |
| `alcance` | char(16) | `grupo` (todos los alumnos activos del grupo, **también los que entren después**) · `seleccion` |
| `destinatarios` | JSON lista de `alumno_id` | sólo con `seleccion` (no puede quedar vacío) |
| `profesor_id` · `profesor_rotulo` | char(64) · char(120) | quien asigna |
| `fuente_curso` · `curso_ref` · `curso_version` · `curso_rotulo` | | referencias y rótulo de evidencia |
| `leccion_ref` · `leccion_rotulo` | char(120) · char(250) | |
| `titulo` · `descripcion` | char(250) · char(500) | por defecto el rótulo de la lección y su resumen |
| `asignatura_rotulo` · `unidad_rotulo` | char(120) · char(200) | `classification.subject.name` y `classification.topic.name`: la línea «LENGUA CASTELLANA · UNIDAD 2» |
| `consigna` | text | opcional; el profesor no tiene teclado: se ofrece por opciones |
| `bloques` | JSON lista `{ref, indice, objeto_ref, tipo, titulo, obligatorio}` | estructura **al asignar**, como referencias (D-4); se refresca al abrir la lección si la versión cambió |
| `practica` | JSON `{objeto_ref, titulo, total_preguntas}` o nulo | la primera `activity` de la lección |
| `evaluacion` | JSON `{objeto_ref, titulo}` o nulo | el primer `exam`; **sólo informativo** |
| `bytes_estimados` | bigint nulo | suma de medios medidos al asignar; se afina al preparar el paquete |
| `paquete_permitido` | bool (defecto `true`) | «decide si queda disponible en modo de estudio» (JRN-007) |
| `fecha_limite` · `plazo` · `gracia_ms` | bigint nulo · char(12) · int | `plazo`: `blando` (defecto) · `endurecido`; `gracia_ms` defecto 900 000 (DEC-019) |
| `estado` | char(12) | `activa` · `cerrada` |
| `creada_en` · `cerrada_en` · `creado_por` | bigint · bigint nulo · char(64) | |

`CHECK`: `alcance`, `plazo`, `estado` en sus listas; `estado='cerrada'` ⇔ `cerrada_en` no nulo; `gracia_ms ≥ 0`. Índices: `(grupo_id, estado)`, `(estado, fecha_limite)`.

### 2.2 · `m08_tarea` (el estado de la tarea del alumno)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `asignacion` | FK → `m08_asignacion` CASCADE | |
| `alumno_id` | char(64) | `m01_usuario.id` (lógica) |
| `estado` | char(12) | `pendiente` · `en_curso` · `completada` (vencida es **derivada**: fecha pasada y no completada) |
| `bloques_vistos` | JSON lista de `ref` | sólo referencias que existen en `asignacion.bloques` |
| `ultimo_bloque_ref` · `posicion_seg` | char(200) · int nulo | punto de reanudación («Actividad 4 · 03:28») |
| `avance_pct` | decimal(5,2) | obligatorios atendidos / obligatorios × 100; **no es una nota** (DEC-032) |
| `fuera_de_plazo` | bool | completada o avanzada después de la fecha con plazo blando |
| `practica_intentos` · `practica_mejor` · `practica_ultima` · `practica_total` | smallint | resumen de sus prácticas (aciertos) |
| `abierta_en` · `ultimo_avance_en` · `completada_en` | bigint nulo | reloj del nodo |
| `creada_en` | bigint | |

`UNIQUE(asignacion, alumno_id)` · `CHECK estado='completada' ⇒ completada_en no nulo` · `CHECK avance_pct ∈ [0,100]`. Se crea al primer contacto del alumno (abrir, avanzar, pedir paquete o practicar); una asignación sin tarea equivale a `pendiente`.

### 2.3 · `m08_paquete` (paquete de estudio)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `asignacion` | FK CASCADE · `alumno_id` char(64) · `dispositivo_id` char(36) | `m09_dispositivo.id` (lógica) |
| `estado` | char(16) | `solicitado` · `descargandose` · `disponible` · `vencido` · `denegado` |
| `motivo` | char(48) | denegado: `dispositivo_compartido` · `dispositivo_ajeno` · `paquete_no_permitido`; vencido: `vigencia` · `version_nueva` |
| `curso_version` | char(32) | la del curso al preparar el paquete |
| `huella` · `bytes_total` | char(64) · bigint | SHA-256 del manifiesto canónico; suma de medios |
| `archivos` · `no_incluidos` | JSON | `[{media_ref, clase, mime, bytes, sha256}]` · `[{media_ref, motivo}]` (metadatos, nunca contenido) |
| `vigente_hasta` | bigint nulo | D-8 |
| `solicitado_en` · `descarga_iniciada_en` · `disponible_en` · `retirado_en` · `actualizado_en` | bigint | `retirado_en`: el alumno borró su copia |

`UNIQUE(asignacion, alumno_id, dispositivo_id)` (volver a pedir reutiliza la fila: «Actualizar descarga») · `CHECK estado='disponible' ⇒ huella ≠ '' y disponible_en no nulo`. `vencido` se **calcula al leer** (`vigente_hasta` pasada o versión de curso distinta) y se persiste.

### 2.4 · `m08_practica` (actividad de aprendizaje separada, BR-055)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `tarea` | FK → `m08_tarea` CASCADE · `alumno_id` char(64) | |
| `objeto_ref` · `objeto_rotulo` | char(120) · char(250) | la `activity` practicada |
| `numero` | smallint | 1, 2, 3… sin tope |
| `modo` | char(8) | siempre `estudio` (`CHECK modo='estudio'`): **esta tabla no puede contener intentos formales** |
| `estado` | char(12) | `en_curso` · `terminada` |
| `respuestas` | JSON lista | uno por pregunta: `{pregunta_ref, respuesta, secuencia, sesion_ref, recibida_en, capturada_en, veredicto{puntaje, puntaje_maximo, correcta, pendiente, retroalimentacion[]}}` (formato de `m07_intento.respuestas`) |
| `total_preguntas` · `aciertos` | smallint | `aciertos` = respuestas con `correcta = true` |
| `puntaje` · `puntaje_maximo` | float nulo | sólo de lo ya calificado; **escala interna, no se publica** |
| `origen` | char(8) | `directo` · `cola` |
| `dispositivo_id` | char(36) | |
| `iniciada_en` · `terminada_en` | bigint · bigint nulo | |

`UNIQUE(tarea, objeto_ref, numero)` · `UNIQUE(tarea, objeto_ref) WHERE estado='en_curso'` (una en curso: se **reanuda**, FUN-088) · INV-013 (una respuesta por pregunta y secuencia) se valida en la aplicación, dentro de la transacción, porque es una lista JSON.

### 2.5 · `m08_sincronizacion` (libro de eventos integrados)

`id` bigint auto PK · `emisor_id` char(64) · `secuencia` bigint · `alumno_id` · `dispositivo_id` · `tipo` char(40) · `asignacion_id` char(36) · `estado` (`integrado` · `rechazado` · `pendiente_decision`) · `motivo` char(64) · `ocurrido_en` (normalizada al reloj del nodo) · `ocurrido_en_tableta` (dato adicional, BR-062) · `recibido_en` · `carga` JSON (sólo se conserva completa mientras está `pendiente_decision`; después queda un resumen sin el contenido de las respuestas) · `resultado` JSON (lo que se contestó, para responder igual a un reenvío).

`UNIQUE(emisor_id, secuencia)`: **el reenvío no duplica** (BR-060, CAP-048). Mapeo al estado que ve el cliente: `integrado → synced`, `rechazado → rejected`, `pendiente_decision → conflict`; `pending` es de la propia cola del aparato.

### 2.6 · `m08_evento_salida`

Outbox propio (`estudio.*.v1`), mismo contrato que `m01_`, `m07_` y `m09_`: `agregado_tipo`, `agregado_id`, `tipo_evento`, `carga`, `creado_en`, `publicado_en`, `intentos`. Se escribe en la misma transacción que el hecho (DEC-007). Los eventos aceptados:

| Evento | Función | Carga (más `instante`) |
|---|---|---|
| `estudio.sesion.abierta.v1` | FUN-080 | `alumno_id, dispositivo_id, sesion_id, perfil` |
| `estudio.sesion.cerrada.v1` | FUN-089 | `alumno_id, dispositivo_id, sesion_id, motivo, cola_pendiente, limpieza` |
| `estudio.leccion.abierta.v1` | FUN-082 | `asignacion_id, alumno_id, curso_ref, leccion_ref` |
| `estudio.leccion.completada.v1` | FUN-087 | `asignacion_id, alumno_id, leccion_ref, fuera_de_plazo, origen` |
| `estudio.actividad.reanudada.v1` | FUN-088 | `asignacion_id, alumno_id, practica_id, numero, respondidas` |
| `estudio.paquete.descargado.v1` | FUN-084 | `paquete_id, asignacion_id, alumno_id, dispositivo_id, bytes, huella` |
| `estudio.descarga.denegada.v1` | FUN-085 | `paquete_id, asignacion_id, alumno_id, dispositivo_id, motivo` |
| `estudio.trabajo.integrado.v1` | FUN-086 | `alumno_id, dispositivo_id, emisor_id, integrados, duplicados, rechazados, pendientes_decision, desde_secuencia, hasta_secuencia` |
| `estudio.limpieza.reintentada.v1` | FUN-090 | `alumno_id, dispositivo_id, resultado` |
| `evaluacion.respuesta_registrada.v1` | FUN-083 | `practica_id, asignacion_id, alumno_id, pregunta_ref, secuencia, modo` (sin el contenido de la respuesta, BR-127) |
| `estudio.asignacion.creada.v1` · `estudio.asignacion.cerrada.v1` · `estudio.practica.terminada.v1` | CAP-050 · CAP-051 | propios del proyecto |

### 2.7 · MOD-009: `m09_dispositivo` gana el perfil

`perfil` char(12) (`compartido` por defecto · `asignado`) · `asignado_a_id` char(64) nulo · `asignado_en` bigint nulo. `CHECK (perfil='asignado') = (asignado_a_id IS NOT NULL)`. Eventos `dispositivo.asignado.v1` y `dispositivo.liberado.v1` (FUN-092, FUN-093) en `m09_evento_salida`. El DTO del dispositivo añade `perfil` y `asignado_a {id, rotulo}`.

---

## 3 · Permisos

| Permiso | Función | Rol · alcance |
|---|---|---|
| `study.open` | FUN-080 abrir y cerrar la sesión de estudio | `STUDENT` · `SELF` |
| `study.assignment.read` | FUN-081 listar pendientes | `STUDENT` · `SELF` |
| `study.lesson.open` | FUN-082 abrir la lección (y sus medios) | `STUDENT` · `SELF` |
| `study.lesson.complete` | FUN-087 marcar completada (y registrar avance) | `STUDENT` · `SELF` |
| `study.answer.submit` | FUN-083 / FUN-088 practicar y reanudar | `STUDENT` · `SELF` |
| `study.package.download` | FUN-084 pedir, bajar, confirmar y retirar el paquete | `STUDENT` · `SELF` |
| `study.assignment.create` | CAP-050 asignar a un alumno o al grupo (del proyecto) | `TEACHER` · `ASSIGNED_GROUPS`, `ADMIN` · `ORGANIZATION` |
| `study.assignment.review` | CAP-051 ver quién completó (del proyecto) | igual |
| `device.assign` · `device.release` | FUN-092 · FUN-093 | `identity.device.manage` (técnico, administrador) |

Se siembran en `acceso.dominio.plantillas` y en la migración `acceso/0007_permisos_estudio.py` (idempotente, como la 0006). **Sin sesión** (Q-34) todo se permite, igual que en el aula y el expediente; **con sesión** un permiso ausente del rol es 403 `sin_permiso`. Sólo el alumno **titular** de la tarea la lee o la escribe.

---

## 4 · Contrato HTTP · `/api/modo-estudio/`

Convenciones: tiempos en ms del **reloj del nodo**; toda respuesta con hora lleva `servidor_en` (el cliente aprende su desfase, `RelojNodo`); los errores son `{detail, codigo, …}`. Al aparato se le identifica con su huella `dispositivo` (= `identificador_hw`, p. ej. `student-DESKTOP-01`): en `?dispositivo=` (GET) o en el cuerpo (POST). Sin `dispositivo` ni sesión de alumno: 400 `falta_dispositivo`. **Al alumno** (D-3, D-15): con sesión, el del token; sin ella, el `alumno_id` que declara la tableta —en el cuerpo o en `?alumno_id=`— en cualquier aparato; sin `alumno_id`, el dueño de una tableta asignada, y en una compartida 400 `falta_alumno`.

| Código | HTTP | Cuándo |
|---|---|---|
| `datos_invalidos` | 400 | forma o valores incorrectos |
| `falta_dispositivo` · `falta_alumno` | 400 | el aparato o (sin sesión y sin dueño) la persona |
| `sin_permiso` · `no_es_el_titular` | 403 | permiso `study.*` ausente, o —con `motivo = alumno_desconocido`— el `alumno_id` declarado no existe o está inactivo · tarea, práctica o paquete de otra persona |
| `dispositivo_bloqueado` · `dispositivo_inactivo` | 403 | MOD-009 |
| `descarga_denegada` | 403 | BR-054: aparato compartido, asignado a OTRA persona (`paquete.motivo = dispositivo_ajeno`, D-2) o `paquete_permitido = false`; lleva `paquete` y `mensaje` (MSG-046) |
| `no_encontrado` | 404 | asignación, paquete, práctica o medio inexistentes o no visibles para el alumno |
| `no_instalado` | 409 | el nodo no tiene organización (MOD-001) |
| `asignacion_cerrada` | 409 | ya no admite avance ni respuestas |
| `bloques_pendientes` | 409 | FUN-087 sin todos los obligatorios; lleva `faltan[{ref, indice, titulo}]` |
| `practica_terminada` | 409 | responder sobre una práctica terminada |
| `paquete_vencido` | 410 | sirve el manifiesto o un archivo de un paquete vencido |
| `huella_invalida` | 409 | `confirmar` con una huella distinta de la del manifiesto |
| `fuente_no_disponible` | 503 | la biblioteca no responde (`disponible: false`, `sugerencia`) |

### 4.1 · Estado y sesión de estudio

| Ruta | Verbo | Permiso | Cuerpo → respuesta |
|---|---|---|---|
| `/estado/?dispositivo=[&alumno_id=]` | GET | — | `{disponible, motivo, perfil, alumno{id,rotulo}\|null, dueno{id,rotulo}\|null, dispositivo{id,nombre,identificador_hw}\|null, descarga_permitida, servidor_en}`. Nunca falla: es la pregunta del menú. `disponible` = **esta tableta puede usar el modo de estudio**: nodo instalado y aparato registrado, activo y no bloqueado, compartido o asignado (D-1 revisada). `motivo`: `""` · `nodo_no_instalado` · `dispositivo_desconocido` · `dispositivo_bloqueado` · `dispositivo_inactivo` (ya no hay motivos de perfil: `dispositivo_compartido` y `dispositivo_ajeno` salieron del estado). `perfil`: `""` (aparato desconocido) · `compartido` · `asignado`. `alumno`: el `alumno_id` declarado si existe y está activo (con sesión, el del token), si no `null`. `dueno`: a quién está asignada la tableta, o `null`. `descarga_permitida` = disponible, de perfil `asignado` y (no se declaró a nadie o el declarado es el dueño) (BR-054). Un aparato que la tableta nunca registró es `dispositivo_desconocido`: el cliente lo da de alta con `POST /api/dispositivos/latido/` y vuelve a preguntar (aquí no hay autoregistro) |
| `/estudiantes/?dispositivo=` | GET | — (ni sesión ni permiso: la identidad se declara) | Los nombres de la pantalla «¿Quién eres?» → `{disponible, motivo, grupos[{id, codigo, nombre, alumnos[{id, rotulo}]}], dueno{id,rotulo}\|null, servidor_en}`. Siempre 200. `disponible` y `motivo` son los de `/estado/`; con la tableta inutilizable, `grupos = []`. `grupos`: los grupos activos con **al menos una asignación ACTIVA** (de alcance `grupo`, o `seleccion` con grupo) y **todos** sus alumnos ACTIVOS; los destinatarios de una `seleccion` sin grupo van en un grupo sintético `{id: "", codigo: "", nombre: "Alumnos"}`. Un grupo sin alumnos activos no se lista. Sólo nombres: ningún otro dato de las personas. `?alumno_id=` o la sesión no cambian la respuesta. Sin `dispositivo` y sin sesión: 400 `falta_dispositivo`. Es de sólo lectura: no registra la tableta |
| `/sesion/` | POST | `study.open` | `{dispositivo, alumno_id?, nombre?, plataforma?, version_app?}` → `{sesion_id, alumno, dispositivo, perfil, servidor_en}`. Abre la sesión de alumno en MOD-009 (relevo si hay otra, en esa tableta o del mismo alumno en otra) y emite `estudio.sesion.abierta.v1`. Sirve en cualquier tableta (D-15) |
| `/sesion/cerrar/` | POST | `study.open` | `{dispositivo, cola_pendiente?: n, limpieza?: "completa"\|"pendiente"}` → `{cerrada: true}`. Cierra la sesión en MOD-009 (`usuario`) y emite `estudio.sesion.cerrada.v1`. Idempotente |
| `/sesion/limpieza/` | POST | — | `{dispositivo, resultado: "completa"}` → `{ok: true}` · `estudio.limpieza.reintentada.v1` (FUN-090) |

### 4.2 · Pendientes y lección (alumno)

| Ruta | Verbo | Permiso | Respuesta |
|---|---|---|---|
| `/asignaciones/?dispositivo=` | GET | `study.assignment.read` | `{alumno, asignaciones[AsignacionAlumno], resumen{pendientes, descargadas, completadas}, servidor_en}`. Sólo asignaciones **activas o completadas por él** que le alcanzan (grupo activo o selección). No lee la biblioteca (usa los rótulos y la estructura guardados): funciona con la biblioteca cerrada |
| `/asignaciones/{id}/?dispositivo=` | GET | `study.assignment.read` | `AsignacionAlumno` (con `bloques[]` y su `atendido`) |
| `/lecciones/{id}/?dispositivo=` | GET | `study.lesson.open` | Abre la lección (`{id}` = id de la **asignación**, que fija curso, versión y lección): `{asignacion, curso, leccion, bloques[], reanudar, servidor_en}`. `leccion` es la vista de aula **sin claves** (`classroom_engine`), con las URL de los medios apuntando a `/asignaciones/{id}/medios/…`. Crea la tarea, la pasa a `en_curso` y emite `estudio.leccion.abierta.v1` la primera vez |
| `/asignaciones/{id}/medios/{media_ref}/[ruta]` | GET · HEAD | `study.lesson.open` | Bytes del medio (`Range`), sólo si el medio **pertenece a la lección asignada** y la asignación le alcanza al alumno |
| `/lecciones/{id}/progreso/` | PATCH | `study.lesson.complete` | `{dispositivo, bloques_vistos?: [ref], bloque_actual?: ref, posicion_seg?: n, capturado_en?: ms}` → `{tarea, aceptados[], desconocidos[]}`. **Monótono**: nunca desatiende un bloque. Recalcula `avance_pct` y lo pasa al expediente (`actualizar_progreso`, monotónico). Con la asignación cerrada: 409 |
| `/lecciones/{id}/completar/` | POST | `study.lesson.complete` | `{dispositivo}` → `{tarea}` con `estado=completada` y `estudio.leccion.completada.v1`; sin todos los obligatorios: 409 `bloques_pendientes`. Sella la sección en el expediente (100 %). Idempotente |

`AsignacionAlumno`:

```json
{
  "id": "…", "titulo": "Área y volumen con lenguaje algebraico", "consigna": "", "descripcion": "…",
  "asignatura": "Lengua Castellana", "unidad": "Unidad 2",
  "curso": {"fuente": "biblioteca", "curso_ref": "…", "version": "1.0.0", "titulo": "…"},
  "leccion_ref": "…",
  "fecha_limite": 1759600000000, "plazo": "blando", "gracia_ms": 900000, "estado_asignacion": "activa",
  "profesor": "Ms. Carter", "asignada_en": 1759000000000,
  "tarea": {
    "estado": "en_curso", "vencida": false, "fuera_de_plazo": false, "avance_pct": 57.14,
    "bloques_total": 7, "bloques_obligatorios": 7, "bloques_atendidos": 4,
    "ultimo_bloque": {"ref": "…", "indice": 4, "titulo": "…", "tipo": "lamina", "posicion_seg": 208},
    "puede_reanudar": true, "abierta_en": 1, "ultimo_avance_en": 2, "completada_en": null
  },
  "practica": {"disponible": true, "objeto_ref": "…", "titulo": "Comprueba lo aprendido", "total_preguntas": 8,
               "intentos": 2, "mejor_correctas": 7, "ultima_correctas": 6, "en_curso": false},
  "evaluacion": {"objeto_ref": "…", "titulo": "Evaluación de la Unidad 2"},
  "paquete": {"id": "…", "estado": "disponible", "motivo": "", "bytes_total": 88080384, "bytes_estimados": 88080384,
              "vigente_hasta": 1759700000000, "huella": "…"},
  "descarga": {"permitida": true, "motivo": ""},
  "bloques": [{"ref": "…", "indice": 1, "tipo": "lamina", "titulo": "…", "obligatorio": true, "atendido": true}]
}
```

`tarea` es `null` cuando el alumno aún no la ha tocado (equivale a `pendiente`, 0 %). `paquete` es el del **aparato que pregunta** (o `null`). `descarga.motivo`: `""` · `dispositivo_compartido` · `dispositivo_ajeno` (tableta asignada a otra persona, D-2) · `paquete_no_permitido`.

### 4.3 · Práctica autocalificable (separada de la evaluación formal)

| Ruta | Verbo | Permiso | Cuerpo → respuesta |
|---|---|---|---|
| `/lecciones/{id}/practica/` | POST | `study.answer.submit` | `{dispositivo, objeto_ref?, nueva?: bool}` → `{practica, objeto}`. Reanuda la práctica en curso (FUN-088, `estudio.actividad.reanudada.v1`) o abre la siguiente (`numero` + 1: «Intentar nuevamente»); `nueva: true` fuerza una nueva. `objeto` es la `activity` de aula con sus preguntas **sin claves**. `practica`: `{id, numero, estado, objeto_ref, titulo, total_preguntas, respondidas{pregunta_ref: {respuesta, veredicto}}, aciertos, iniciada_en, reanudada}` |
| `/practicas/{id}/respuestas/` | POST | `study.answer.submit` | `{dispositivo, respuestas:[{pregunta_ref, respuesta, secuencia, capturada_en?}], terminar?: bool}` → `{acuse, veredictos[], aceptadas[], duplicadas[], superadas[], rechazadas[], practica{id, estado, respondidas, aciertos, total_preguntas, sin_calificar}, resultado?, servidor_en}`. **Feedback en ≤ 2 s.** `veredicto`: `{pregunta_ref, correcta, puntaje, puntaje_maximo, pendiente, retroalimentacion[]}` (sin clave). La forma de `respuesta` se valida con `validar_respuesta` de `classroom_engine` (ids, nunca posiciones). Si la biblioteca no responde, la respuesta **se guarda sin calificar** (`veredicto = null`) y se califica en la siguiente lectura o sincronización |
| `/practicas/{id}/terminar/` | POST | `study.answer.submit` | `{dispositivo}` → `{practica, resultado}`. `resultado`: `{correctas, total, porcentaje, mensaje, revision[{pregunta_ref, correcta, retroalimentacion[]}], sin_calificar}`. Marca el bloque de la práctica como atendido y emite `estudio.practica.terminada.v1`. Nunca se llama «nota» ni «evaluación» |

Reglas: **no** consume ni modifica `m07_intento` ni `m10_intento` (prueba de arquitectura y de datos); no hay tope de intentos; con la asignación cerrada, 409. Cada respuesta aceptada emite `evaluacion.respuesta_registrada.v1` con `modo: "estudio"`.

### 4.4 · Paquete de estudio (CAP-047)

| Ruta | Verbo | Permiso | Cuerpo → respuesta |
|---|---|---|---|
| `/paquetes/` | POST | `study.package.download` | `{dispositivo, asignacion_id}` → `201`/`200` `{paquete}` en `solicitado`, con `archivos[]`, `no_incluidos[]`, `bytes_total`, `huella`, `vigente_hasta`. Vuelve a pedirlo el que quiere «Actualizar descarga» (reutiliza la fila, refresca manifiesto y vigencia). **Aparato compartido, asignado a otra persona o `paquete_permitido=false` → 403 `descarga_denegada`** con `{paquete{estado:"denegado", motivo: dispositivo_compartido \| dispositivo_ajeno \| paquete_no_permitido}, mensaje}` y `estudio.descarga.denegada.v1` (FUN-085) |
| `/paquetes/?dispositivo=` | GET | `study.package.download` | `{paquetes[]}` del aparato para su dueño, con el estado ya evaluado (`vencido`) |
| `/paquetes/{id}/?dispositivo=` | GET | idem | `paquete` |
| `/paquetes/{id}/manifiesto/?dispositivo=` | GET | idem | El manifiesto: `{paquete_id, asignacion, curso, leccion_ref, vigente_hasta, generado_en, leccion (vista de aula sin claves), archivos[], no_incluidos[], huella}`. La `huella` es el SHA-256 hexadecimal del JSON canónico (claves ordenadas, sin espacios, UTF-8) del manifiesto **sin el campo `huella`**. Pasa a `descargandose`. 410 `paquete_vencido` si vencido |
| `/paquetes/{id}/archivos/{media_ref}/?dispositivo=` | GET · HEAD | idem | Bytes del medio con `Range` (reanudable), sólo los de `archivos[]`. `ETag` = el `sha256` del archivo |
| `/paquetes/{id}/confirmar/` | POST | idem | `{dispositivo, huella, bytes}` → `paquete` en `disponible` y `estudio.paquete.descargado.v1`; huella distinta: 409 `huella_invalida` |
| `/paquetes/{id}/?dispositivo=` | DELETE | idem | El alumno borra su copia (`retirado_en`). El paquete deja de listarse |

### 4.5 · Trabajo sin red (CAP-048)

| Ruta | Verbo | Cuerpo → respuesta |
|---|---|---|
| `/sync/` | POST | `{dispositivo, emisor_id, eventos:[{secuencia, tipo, ocurrido_en, ocurrido_en_tableta?, carga}], alumno_id?}` → `{acuse: true, servidor_en, resultados[{secuencia, estado, motivo, detalle}], resumen{integrados, duplicados, rechazados, pendientes_decision}, asignaciones[{id, tarea}], veredictos[{asignacion_id, objeto_ref, numero, pregunta_ref, veredicto}]}`. Máximo 200 eventos por envío; se procesan **en orden de secuencia**; cada uno en su transacción; el envío completo es idempotente. Sin sesión se autoriza por el aparato (registrado, activo, no bloqueado: si no, 403 `sin_permiso` con `motivo = dispositivo_desconocido`, o `dispositivo_bloqueado`/`dispositivo_inactivo`) y por el `alumno_id` declarado (existe y está activo: si no, 403 `sin_permiso` con `motivo = alumno_desconocido`); ya no hace falta que el aparato sea del alumno ni que esté asignado (D-11 revisada por D-15). Sin `alumno_id`, un aparato asignado sincroniza para su dueño y uno compartido es 400 `falta_alumno`. Cada evento comprueba que la asignación le alcance al alumno |
| `/sync/status/?dispositivo=&emisor_id=[&alumno_id=]` | GET | `{emisor_id, ultima_secuencia, conteos{synced, rejected, conflict}, pendientes_decision[{secuencia, tipo, asignacion_id, motivo}]}`. Lo que el libro tiene de **ese alumno** en esa instalación; se autoriza igual que `/sync/` |

`estado` de cada resultado: `integrado` · `duplicado` · `rechazado` · `pendiente_decision`. Tipos y `carga`:

| `tipo` | `carga` | Efecto |
|---|---|---|
| `study.block.viewed` | `{asignacion_id, bloques_vistos[], bloque_actual?, posicion_seg?}` | como `PATCH …/progreso/` |
| `study.answer.submitted` | `{asignacion_id, objeto_ref, intento_numero, pregunta_ref, respuesta, secuencia_respuesta}` | abre o reanuda la práctica `(tarea, objeto_ref, intento_numero)` y fusiona la respuesta (INV-013); la califica |
| `study.practice.finished` | `{asignacion_id, objeto_ref, intento_numero}` | como `…/terminar/` |
| `study.lesson.completed` | `{asignacion_id}` | como `…/completar/` (sin todos los obligatorios: `rechazado`, `bloques_pendientes`) |

Política de plazo (D-9) sobre `ocurrido_en` (capturado) y `recibido_en` (llegada): blando → siempre `integrado` (con `fuera_de_plazo` si `ocurrido_en > fecha_limite`); endurecido → `integrado` / `pendiente_decision` / `rechazado` según `politica_de_recepcion`.

### 4.6 · Profesor (OPS) · `/docente/…`

Sin sesión se permite (Q-34), declarando `actor` como en el aula. Con sesión: `study.assignment.create` / `.review` y ser docente titular del grupo (o administración).

| Ruta | Verbo | Cuerpo → respuesta |
|---|---|---|
| `/docente/grupos/` | GET | `{instalado, grupos[{id, codigo, nombre, nivel_clave, alumnos[{id, rotulo}]}]}` — sus grupos (todos si es administración o no hay sesión). `instalado:false` sin organización |
| `/docente/asignaciones/` | GET | `?grupo_id=&estado=` → `{asignaciones[{id, titulo, asignatura, unidad, grupo_id, grupo_rotulo, curso, leccion_ref, fecha_limite, plazo, estado, alcance, paquete_permitido, destinatarios_total, completaron, en_curso, pendientes, fuera_de_plazo, pendientes_decision, creada_en}]}` |
| `/docente/asignaciones/` | POST | `{alcance: "grupo"\|"seleccion", grupo_id?, alumnos?[], curso_ref, fuente?, leccion_ref, titulo?, consigna?, fecha_limite?, plazo?, gracia_min?, paquete_permitido?, actor?, actor_rotulo?}` → `201` `AsignacionDocente`. Lee la lección **en vivo** para guardar rótulos, bloques, práctica, evaluación y `bytes_estimados`; sin biblioteca: 503 (no se asigna a ciegas). Emite `estudio.asignacion.creada.v1` |
| `/docente/asignaciones/{id}/` | GET | `AsignacionDocente` + `alumnos[{alumno_id, rotulo, estado, vencida, fuera_de_plazo, avance_pct, bloques_atendidos, bloques_total, ultimo_avance_en, completada_en, practica{intentos, mejor_correctas, total}, paquete{estado}, dispositivo{id, nombre, perfil}\|null, pendientes_decision, decisiones[{emisor_id, secuencia, tipo, motivo, ocurrido_en, recibido_en}]}]` — **quién completó** (CAP-051): los destinatarios (grupo activo o selección) con o sin tarea; `decisiones` son los envíos que esperan al profesor (BR-074) |
| `/docente/asignaciones/{id}/` | PATCH | `{fecha_limite?, plazo?, gracia_min?, titulo?, consigna?, paquete_permitido?}` (endurecer o mover la fecha) |
| `/docente/asignaciones/{id}/cerrar/` | POST | → `AsignacionDocente` en `cerrada` · `estudio.asignacion.cerrada.v1` |
| `/docente/asignaciones/{id}/decisiones/` | POST | `{alumno_id, emisor_id, secuencia, decision: "aceptar"\|"descartar", actor?}` → resuelve un `pendiente_decision` (BR-074): aceptar aplica el evento guardado. `(emisor_id, secuencia)` es la clave del libro de sincronización; el par sale de `decisiones[]` del detalle |

### 4.7 · MOD-009 · dispositivos asignados

| Ruta | Verbo | Permiso | Cuerpo → respuesta |
|---|---|---|---|
| `/api/dispositivos/{id}/asignar/` | POST | `device.assign` | `{alumno_id, actor?}` → dispositivo con `perfil: "asignado"`. Un aparato que ya es de otra persona: 409 `dispositivo_ya_asignado` (primero se libera). `dispositivo.asignado.v1` + bitácora |
| `/api/dispositivos/{id}/liberar/` | POST | `device.release` | `{actor?}` → dispositivo `compartido`. 409 `paquete_sin_integrar` si tiene un paquete de estudio activo (`solicitado`, `descargandose`, `disponible`). `dispositivo.liberado.v1` + bitácora |

---

## 5 · Cliente (Core, C#)

`Avacom.Lms.Core/Models/EstudioModels.cs` (los DTO de arriba como `record`, `snake_case`), `Services/IEstudioApi` y `EstudioApi` (alumno y profesor; mismas reglas de degradación que `AulaApi`: un error HTTP o de red devuelve `null` y deja el motivo en `UltimoError`), y en `Avacom.Lms.Core/Estudio/`:

| Pieza | Qué hace |
|---|---|
| `ArchivoCifrado` (+ `EscritorCifrado`, `LectorCifrado`, `DocumentoCifrado`) | AES-256-GCM por bloques de 64 KiB con acceso aleatorio y reanudable; los documentos pequeños se sellan enteros con su lugar como dato asociado. |
| `AlmacenEstudio` | El almacén local cifrado por alumno: lista de pendientes, avance de cada tarea, manifiestos y medios de los paquetes, vigencia, espacio y borrado. Un archivo que no se puede descifrar se trata como ausente. |
| `DescargadorDePaquetes` | Baja un paquete completo, cada archivo reanudable (`Range`) y cifrado al escribirse; verifica la huella del manifiesto (sobre el texto tal como llegó) y el SHA-256 de cada archivo; pausar es cancelar el token. |
| `ColaEstudio` | La cola cifrada con `emisor_id` (una por instalación) y `secuencia` monótona **global** persistida **antes** de enviar (con varias personas en la tableta las secuencias no se repiten); se borra sólo con el acuse. |
| `SincronizadorEstudio` | Vacía la cola hacia `POST /sync/`, en orden, hasta 200 por envío y un envío por alumno; sin conexión no pierde nada. |
| `ServidorLocalDeMedios` | HTTP en `127.0.0.1` con `Range` y una capacidad aleatoria en la ruta, para que la lección descargada se lea sin red con los mismos visores. |
| `JsonCanonico` | La huella del manifiesto: SHA-256 del JSON canónico (claves ordenadas, sin espacios, UTF-8) sin el campo `huella`. |

La clave local la entrega `IProveedorDeClave` (Student: DPAPI en Windows, `SecureStorage` en Android; las pruebas, una en memoria). Desde D-15 el cliente añade `EstudiantesAsync` (`GET /estudiantes/`) y `EstadoEstudio.Dueno`.

## 6 · Cómo usa a los otros módulos

| Puerto (MOD-008) | Adaptador | De quién |
|---|---|---|
| `Contenido` (lección sin claves, evaluar, medios) | `ConsultarLeccion`, `EvaluarRespuesta`… de `classroom_engine.aplicacion` con `Servicios` propio (URL de medios de MOD-008) | MOD-007 / Biblioteca |
| `Dispositivos` (resolver, perfil, sesión de alumno, latido) | `device_manager.servicios` | MOD-009 |
| `Identidad` (grupos, alumnos, docente del grupo, rótulos) | lectura de `m01_*` | MOD-001 |
| `Expediente` (`actualizar_progreso`) | `expediente.servicios` | expediente |
| `Autorizacion` | `AutorizacionEstudio`: permisos `study.*` con la política de MOD-001 | MOD-001 |
| `Auditoria` · `Outbox` | `m19_auditoria` · `m08_evento_salida` | expediente · propio |

Arquitectura hexagonal como el resto: `dominio/` y `aplicacion/` no importan Django, las vistas no tocan el ORM, todas las tablas son `m08_*`, ninguna guarda contenido ni claves. Los cinco servicios que pide la introducción son los casos de uso de `aplicacion/`: asignaciones, lecciones, paquetes, práctica y sincronización.

## 7 · Pantallas

| Superficie | Pantalla | Qué resuelve |
|---|---|---|
| Student | «Modo estudio · Mis lecciones» (`StudyModePage`) | PAN-124/130: pendientes, descargadas, completadas; descarga con progreso; abrir, reanudar y completar; práctica; estados de guardado; vacío y esqueleto |
| Student | visor de lección y práctica | leer con los visores del aula (en línea o desde el paquete) y practicar con feedback inmediato |
| Student | «¿Quién eres?» | los grupos y alumnos de `GET /estudiantes/`: la persona elige su nombre (sin código ni contraseña, D-15) y la tableta lo declara en cada llamada; sólo se muestra el grupo de la asignación |
| Student | menú | hexágono «Modo de estudio» **siempre visible** (no pide código, D-15; `estado.disponible` sólo se usa al entrar, para explicar que una tableta bloqueada o retirada no puede estudiar); «Salir» cierra la sesión de estudio y limpia la tableta (008-07) |
| OPS | «Modo de estudio» (`EstudioPage`) | asignar una lección a un grupo o a alumnos, con fecha límite por opciones; ver quién completó; cerrar |
| OPS | «Dispositivos» | marcar un aparato como asignado a un alumno o compartido (008-01) |

## 8 · Pruebas exigidas

Backend: arquitectura (dominio y aplicación sin framework, vistas sin ORM, tablas `m08_*`, sin columnas de clave, `m07_intento` y `m10_intento` intactos tras practicar); permisos; asignaciones (grupo, selección, visibilidad, cierre); lección (abrir, reanudar, progreso monótono, completar con y sin bloques pendientes, expediente); paquete (asignado sí, compartido no con evento, ajeno con `descarga_denegada` y evento, manifiesto y huella, `Range`, confirmar con huella mala, vigencia y versión, retirar y volver a pedir); práctica (calificar, reanudar, terminar, reintentar, sin biblioteca guarda sin calificar); sincronización (reenvío idempotente, orden, sin sesión con el alumno declarado en cualquier aparato, alumno inexistente o inactivo, plazo blando y endurecido, decisión del profesor con el par `(emisor_id, secuencia)` que sale de `decisiones[]`); identidad declarada (`/estudiantes/` con sus grupos, el grupo sintético y el aparato inutilizable; alumno declarado en la tableta asignada a otro: estudia, aparece ante el profesor y no descarga); dispositivos (asignar, liberar, precondición).
Core: cifrado (ida y vuelta, acceso aleatorio, manipulación detectada), descarga reanudable con huella, cola (secuencia que no retrocede, persiste antes de enviar, acuse borra), sincronizador (sin conexión conserva, duplicado no reenvía).

## 9 · Preguntas para el CTO

| # | Pregunta |
|---|---|
| Q-66 | ¿Qué bloques de una lección son obligatorios? Hoy todos (D-4). ¿Hace falta una marca `required` en el esquema de curso? |
| Q-67 | ¿Práctica con feedback **sin** red? Hoy se guarda y se califica al reconectar (D-6). Exige que Contenido publique verificación local sin exponer la clave. |
| Q-68 | ¿Dónde vive la configuración de modo de estudio por nivel (008-09, DEC-017)? |
| Q-69 | ~~¿Un aparato compartido debe poder usar el modo de estudio **en línea** (FUN-080, DEC-013) o el hexágono sigue siendo sólo del aparato del alumno (008-01)?~~ **Respondida por el usuario el 2026-09-29 (D-15): el modo de estudio sirve en cualquier tableta.** El hexágono sale con `estado.disponible`; sólo la descarga del paquete sigue siendo del dueño de una tableta asignada (BR-054). |
| Q-70 | La práctica y las tareas viven provisionalmente en `m08_*`. ¿Pasan a MOD-010 (con `intento.asignacion_id` y `modo`, como propone la tabla 008-05) cuando exista? |
| Q-71 | Simulaciones sin red: la API no lista los archivos de una simulación, por eso no se empaquetan. ¿Contenido puede publicar el listado? |
| Q-72 | «Salir» (008-07, BR-053) limpia la tableta y **también borra las descargas** de una tableta asignada, pero descargar existe para estudiar en casa sin el aula. ¿«Salir» debe conservar las descargas cuando la tableta es de su dueño, o el alumno cierra la app sin pulsar «Salir»? Hoy se sigue la letra de la tabla. |
| Q-73 | DEC-032 (008-09): el alumno no ve avance calculado hacia una calificación no publicada. «Asignaturas» de Student pinta «N % completado» por curso (avance de lo visto, no una nota). ¿Se conserva como «avance de lectura» o se sustituye por conteos («3 de 8 lecciones»)? No se cambió. |
| Q-74 | Identidad declarada (D-15): hoy cualquiera puede elegir el nombre de otro compañero. Cuando haya un modo de verificar (PIN del alumno, código de un solo uso que dé el profesor, tarjeta), ¿en qué momento se pide: al entrar al modo de estudio, al descargar o al enviar? |

---

## 10 · Frontend

Está descrito en [03 · Frontend Student y OPS](03-frontend-student-y-ops.md): la pantalla «Modo estudio · Mis lecciones» y «¿Quién eres?», el trabajo sin red del cliente, «Salir», la página de OPS para asignar y ver quién completó, y «Dispositivos».

## 11 · Cómo se comprobó

| Capa | Comprobación | Resultado |
|---|---|---|
| Backend | `manage.py test --noinput` completo (dominio, aplicación, vistas, arquitectura, permisos, paquetes, práctica, sincronización, identidad declarada, MOD-009) | 584 pruebas OK (3 omitidas); línea base 309. `check` y `makemigrations --check` sin cambios. Ruta de actualización probada desde acceso 0006 / device_manager 0003. |
| Core (C#) | `dotnet test tests/Avacom.Lms.Core.Tests` | 267 OK: cifrado, almacén, descarga reanudable con huella, cola, sincronizador, servidor local, JSON canónico (contra datos generados con Python) y el cliente de `/api/modo-estudio/`. |
| Student (lógica) | `dotnet test tests/Avacom.Lms.Student.Tests`: compila **los mismos archivos** de la app (servicio, sesiones, descargas, conectividad) con sustitutos mínimos de MAUI Essentials | 61 OK: «¿Quién eres?», estados de la lista, lección desde el aula y desde el paquete, guardar primero y enviar después, práctica con y sin aula, veredictos al integrarse, «Salir» con y sin trabajo pendiente, descargas, conectividad. |
| Student y OPS (pantallas) | Compilación Windows sin errores ni advertencias (desde una copia de `src`, para no chocar con las apps abiertas); Android compila Student; capturas y UI Automation de cada estado en demostración y contra un **nodo de prueba aparte** (puerto 8010, base propia) con la **biblioteca real** | Ver §12. |

## 12 · Estado real (2026-09-29)

**Construido**

- **Backend** `backend/modo_estudio/` (hexagonal en español: `dominio/`, `aplicacion/`, `infraestructura/`, `interfaces/`): 6 tablas `m08_*`, migración `0001`; permisos `study.*` (migración `acceso/0007`: STUDENT 6, TEACHER 2, ADMIN 2); perfil y dueño del equipo (migración `device_manager/0004`, FUN-092/093); asignaciones, lección, paquetes, práctica y sincronización; `GET /estudiantes/` y `GET /estado/` con `dueno` (D-15). Las decisiones que el contrato dejó abiertas se tomaron así: las respuestas de paquete llevan los campos planos y también dentro de `paquete`; el manifiesto guarda un subconjunto estable de la asignación (sin fechas ni estado, para que la huella no cambie si el profesor mueve la fecha); una simulación no se empaqueta y un medio mayor que `AVACOM_ESTUDIO_MEDIO_MAX_MB` (512) va a `no_incluidos`; `evaluacion.respuesta_registrada.v1` se publica desde aquí mientras MOD-010 no exista. Variables: `AVACOM_ESTUDIO_VIGENCIA_DIAS` (14), `AVACOM_ESTUDIO_GRACIA_MIN` (15), `AVACOM_ESTUDIO_MEDIO_MAX_MB` (512).
- **Core**: almacén, cola, descargas, sincronizador y servidor local de medios cifrados (§5).
- **Student**: «Modo estudio · Mis lecciones» (lista, lección, práctica), «¿Quién eres?», descargas, guardado ✓/↑/↻, «Salir» con limpieza; modo demostración (`AVACOM_ESTUDIO_DEMO=1`).
- **OPS**: `EstudioPage` (asignaciones, quién completó con decisiones pendientes, asignar en tres pasos), hexágono «Modo de estudio» y «Dispositivos» (asignar/devolver tableta).
- **Ui**: `PracticaEstudioView`. Además se corrigió un defecto ajeno: `AulaContenidoView` dejaba el texto de estilo `definition` en la columna de 6 px (se leía letra por letra).

**Ojo al actualizar un equipo que ya tiene el LMS**: hay que ejecutar `backend\.venv\Scripts\python manage.py migrate` (acceso 0007, device_manager 0004, modo_estudio 0001). Mientras no se aplique, lo único que no se ve afectado es lo que ya responde «el nodo aún no está instalado».

**Límites conocidos**

1. **La práctica sin red no se califica en la tableta** (Q-67): la clave sólo vive en la biblioteca; se guarda y se califica al integrarse.
2. **Las simulaciones no se descargan** (Q-71): el bloque de laboratorio dice que necesita el aula.
3. **Nadie verifica quién es quién** (D-15, Q-74): es una decisión del usuario para un LMS offline.
4. **«Salir» borra también las descargas** (Q-72).
5. **Alcance por nivel y vista «Mi trabajo»** (008-09) no se implementan (Q-68); la barra de % de «Asignaturas» no se cambió (Q-73).
6. Las pantallas de Student y OPS (XAML y ViewModels) se comprobaron a mano con capturas y UI Automation, no con pruebas automáticas; Android compila pero no se probó en una tableta.
7. Sin organización instalada (la base de desarrollo de este repositorio) el nodo contesta «no instalado» y no hay a quién asignar: hay que instalar el nodo y crear grupos para verlo funcionar de punta a punta.

