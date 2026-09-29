# 02 · Modo Estudio (MOD-008) · Modelo `m08_*` y API `/api/modo-estudio/`

| Campo | Valor |
|---|---|
| Estado | **Contrato de diseño** (2026-09-29). Lo implementan `backend/modo_estudio/` (Django/DRF), `src/Avacom.Lms.Core/Estudio/` (cliente, cola y almacén locales), `src/Avacom.Lms.Student/ModoEstudio/` (pantalla «Modo estudio · Mis lecciones») y `src/Avacom.Lms.Ops/Pages/EstudioPage.*` (asignar y ver quién completó). Al final de este documento, §12, queda el estado real de lo construido. |
| Módulo | **MOD-008 · Modo Estudio** del Documento Maestro (DOM-004). 6 capacidades (CAP-046…051), 11 funciones (FUN-080…090), 10 eventos, 6 permisos `study.*`, escenario TST-079. |
| Requisitos de partida | La tabla 008-01…008-09 de [01 · Introducción](01-introduccion.md), las 15 funciones de backend y los 34 apartados del frontend de ese mismo documento. |
| Modelo de datos | Segunda versión (`specs/analisis/segunda-version-modelo.md`): `asignacion` (nueva, dominio Evaluación), el paquete de estudio, y `dispositivo` con `perfil` y `asignado_a_id` (009-06). |
| Dueño único | MOD-008 escribe sólo `m08_*`. El Maestro dice que **no es propietario de ningún grupo de datos** («opera consumiendo hechos de otros módulos»); mientras MOD-010 (asignaciones, intentos) no tenga dueño, las tablas `m08_asignacion` y `m08_practica` viven aquí como **provisionales**, igual que `m07_intento` vive provisional en MOD-007. El resto lo consume por la interfaz de su dueño (§6). |

---

## 1 · Decisiones (y por qué)

El Maestro, la tabla de requisitos y el código existente no dicen siempre lo mismo. Estas son las lecturas que se tomaron; ninguna se guardó en silencio.

| # | Decisión | Por qué / alternativa |
|---|---|---|
| D-1 | **El modo de estudio «existe» sólo en un aparato asignado a la persona.** El menú de Student muestra el hexágono únicamente si `GET /estado/` responde `disponible = true`. La **API** sí acepta a un aparato compartido hasta la descarga: lo que niega es el **paquete** (BR-054, FUN-085, `estudio.descarga.denegada.v1`). | La tabla 008-01 pide «hexágono sólo si el aparato es del alumno»; FUN-080 dice «en una tableta compartida». Con la API permisiva y la interfaz estricta, si el CTO decide un modo en línea para tabletas compartidas sólo cambia la condición del menú. |
| D-2 | **Un aparato asignado sólo admite a su dueño.** Otro alumno sobre esa tableta: 403 `dispositivo_ajeno`. | BR-058: el perfil lo declara y valida el nodo. |
| D-3 | **Quién es el alumno.** Con JWT (MOD-001): el del token. Sin sesión (Q-34 abierta, prototipo): en un aparato asignado, **el dueño del aparato** (se ignora cualquier nombre escrito); en un aparato compartido, el `alumno_id` que el cliente declare. | En el prototipo Student identifica por un nombre escrito (`Identidad.SlugDe`), que no existe en `m01_usuario`; la asignación nominal de OPS es la única identidad verificada por el nodo. |
| D-4 | **Un «bloque» es la unidad de avance de una lección**, en el orden en que se ve: cada lámina de una `lecture`, cada página de una `explanation`, cada `simulation_lab` y cada `activity` (la práctica). El `exam` **no** es bloque: es evaluación formal y queda fuera (BR-055). Todos los bloques son obligatorios salvo que se declare lo contrario. «Atendido» significa: lámina o página **vista**; laboratorio **abierto**; práctica **terminada al menos una vez** (no se exige nota). | El esquema de curso 1.0 no tiene marca de «obligatorio»; hasta que la haya, todo lo que se estudia lo es. FUN-087 dice «todos los bloques obligatorios fueron atendidos», no «aprobados». Pregunta Q-66 para el CTO. |
| D-5 | **La práctica es una actividad de aprendizaje separada** (`m08_practica`, `modo = 'estudio'` con `CHECK`). No usa `m07_intento` ni `m10_intento`, no consume intentos de evaluación formal y **no tiene tope de intentos** («Puedes intentarlo nuevamente»). El módulo no publica nota ni la guarda como calificación (DEC-032). | BR-055, y la advertencia de la propia introducción: «nunca reutilizar silenciosamente el flujo formal». |
| D-6 | **La clave de respuesta sólo vive en la biblioteca** (`POST /v2/evaluate`). Con el nodo a la vista la práctica califica en ≤ 2 s (NFR-012). **Sin el nodo, lo respondido se guarda en la cola de la tableta y se califica al integrarse**; mientras tanto el alumno ve «Guardado en tu tableta» (MSG-011), no un veredicto. | Enviar claves a la tableta viola la regla de oro de la biblioteca (`answer_keys_forbidden`). Pregunta Q-67: si el CTO quiere feedback sin red, hay que pedir a Contenido un mecanismo de verificación local. |
| D-7 | **El paquete de estudio** es la lección (vista de aula **sin claves**) más los medios que referencia, con su `huella` (SHA-256 del manifiesto), su tamaño y su vigencia. Las **simulaciones** (`simulation_lab`) no se empaquetan: son carpetas sin listado en la API; el bloque dice «necesita el aula». La descarga es reanudable (`Range`) y se guarda cifrada en el aparato. | El esquema de medios no trae tamaño ni huella: el nodo los mide al preparar el paquete. |
| D-8 | **Vigencia**: `fecha_limite + gracia` si la asignación tiene fecha; si no, 14 días (`AVACOM_ESTUDIO_VIGENCIA_DIAS`). Un paquete cuya versión de curso ya no es la instalada está `vencido` (`motivo = version_nueva`). Vencido se evalúa al leer (no hay tarea programada). | Una lección no debería quedarse eternamente en una tableta; MSG-045 «liberamos material vencido». |
| D-9 | **Fecha límite.** `blando` (por defecto, DEC-014): siempre se acepta; lo capturado después de la fecha se marca `fuera_de_plazo`. `endurecido`: la asignación «cierra al vencer»; lo **capturado** antes y **recibido** dentro de la gracia (15 min, DEC-019) se acepta; lo capturado antes pero recibido después queda `pendiente_decision` del profesor (nunca se descarta en silencio, BR-074); lo capturado después del cierre se rechaza. | Se reutiliza `classroom_engine.dominio.actividad.politica_de_recepcion`. |
| D-10 | **Idempotencia del trabajo sin red**: cada evento de la cola lleva `emisor_id` (identidad de la instalación) y `secuencia` monotónica; `m08_sincronizacion` tiene `UNIQUE(emisor_id, secuencia)`. Repetir el envío devuelve el mismo resultado sin duplicar nada. Las respuestas dentro de una práctica (JSON) se fusionan con `fusionar_respuestas` (INV-013, mayor secuencia gana), validado dentro de la transacción. | DEC-023, BR-060, BR-138, TST-029. |
| D-11 | **Sincronizar no exige sesión** (BR-137): sin JWT se autoriza por el aparato (registrado, activo, no bloqueado y **asignado** al alumno de los eventos). | TST-029. |
| D-12 | **Permisos.** Los seis `study.*` del Maestro son de alcance propio (`SELF`) y sólo del rol `STUDENT` (el administrador «no accede al modo de estudio del alumno»). Para CAP-050/051, que el Maestro deja sin permiso, se añaden dos **del proyecto** (como `device.block`): `study.assignment.create` y `study.assignment.review`, para `TEACHER` (sobre sus grupos) y `ADMIN`. | §J de MOD-008 y «Reparto de permisos por rol». |
| D-13 | **Alcance por nivel (008-09)** no se implementa: no hay dónde guardar la configuración por nivel (DEC-017). Queda como pregunta Q-68 con la tabla de adaptación del Maestro (preescolar: sin modo de estudio; primaria: tarea sencilla; secundaria: tarea y repaso; bachillerato: tarea, proyecto y repaso; preuniversitario: paquete descargable completo). | Preguntar al CTO, como pide la tabla. |
| D-14 | **Asignación nominal de aparatos (FUN-092/093)** entra en MOD-009 (`device_manager`): `m09_dispositivo.perfil` (`compartido` por defecto · `asignado`) y `asignado_a_id`, con `POST /api/dispositivos/{id}/asignar/` y `/liberar/`. Liberar exige que el aparato no tenga un paquete de estudio activo. | 008-01 / 009-06 y FUN-093. |

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

Convenciones: tiempos en ms del **reloj del nodo**; toda respuesta con hora lleva `servidor_en` (el cliente aprende su desfase, `RelojNodo`); los errores son `{detail, codigo, …}`. Al aparato se le identifica con su huella `dispositivo` (= `identificador_hw`, p. ej. `student-DESKTOP-01`): en `?dispositivo=` (GET) o en el cuerpo (POST). Sin `dispositivo` ni sesión de alumno: 400 `falta_dispositivo`.

| Código | HTTP | Cuándo |
|---|---|---|
| `datos_invalidos` | 400 | forma o valores incorrectos |
| `falta_dispositivo` · `falta_alumno` | 400 | el aparato o (aparato compartido sin sesión) la persona |
| `sin_permiso` · `no_es_el_titular` | 403 | permiso `study.*` ausente · tarea o asignación de otra persona |
| `dispositivo_bloqueado` · `dispositivo_inactivo` | 403 | MOD-009 |
| `dispositivo_ajeno` | 403 | aparato asignado a otra persona (D-2) |
| `descarga_denegada` | 403 | BR-054: aparato compartido (o `paquete_permitido = false`); lleva `paquete` y `mensaje` (MSG-046) |
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
| `/estado/?dispositivo=` | GET | — | `{disponible, motivo, perfil, alumno{id,rotulo}\|null, dispositivo{id,nombre,identificador_hw}\|null, descarga_permitida, servidor_en}`. `motivo`: `""` · `nodo_no_instalado` · `dispositivo_desconocido` · `dispositivo_bloqueado` · `dispositivo_inactivo` · `dispositivo_compartido` · `dispositivo_ajeno`. Nunca falla: es la pregunta del menú. `disponible` = aparato asignado a esta persona y utilizable |
| `/sesion/` | POST | `study.open` | `{dispositivo, nombre?, plataforma?, version_app?}` → `{sesion_id, alumno, dispositivo, perfil, servidor_en}`. Abre la sesión de alumno en MOD-009 (relevo si hay otra) y emite `estudio.sesion.abierta.v1` |
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

`tarea` es `null` cuando el alumno aún no la ha tocado (equivale a `pendiente`, 0 %). `paquete` es el del **aparato que pregunta** (o `null`).

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
| `/paquetes/` | POST | `study.package.download` | `{dispositivo, asignacion_id}` → `201`/`200` `{paquete}` en `solicitado`, con `archivos[]`, `no_incluidos[]`, `bytes_total`, `huella`, `vigente_hasta`. Vuelve a pedirlo el que quiere «Actualizar descarga» (reutiliza la fila, refresca manifiesto y vigencia). **Aparato compartido o `paquete_permitido=false` → 403 `descarga_denegada`** con `{paquete{estado:"denegado", motivo}, mensaje}` y `estudio.descarga.denegada.v1` (FUN-085) |
| `/paquetes/?dispositivo=` | GET | `study.package.download` | `{paquetes[]}` del aparato para su dueño, con el estado ya evaluado (`vencido`) |
| `/paquetes/{id}/?dispositivo=` | GET | idem | `paquete` |
| `/paquetes/{id}/manifiesto/?dispositivo=` | GET | idem | El manifiesto: `{paquete_id, asignacion, curso, leccion_ref, vigente_hasta, generado_en, leccion (vista de aula sin claves), archivos[], no_incluidos[], huella}`. La `huella` es el SHA-256 hexadecimal del JSON canónico (claves ordenadas, sin espacios, UTF-8) del manifiesto **sin el campo `huella`**. Pasa a `descargandose`. 410 `paquete_vencido` si vencido |
| `/paquetes/{id}/archivos/{media_ref}/?dispositivo=` | GET · HEAD | idem | Bytes del medio con `Range` (reanudable), sólo los de `archivos[]`. `ETag` = el `sha256` del archivo |
| `/paquetes/{id}/confirmar/` | POST | idem | `{dispositivo, huella, bytes}` → `paquete` en `disponible` y `estudio.paquete.descargado.v1`; huella distinta: 409 `huella_invalida` |
| `/paquetes/{id}/?dispositivo=` | DELETE | idem | El alumno borra su copia (`retirado_en`). El paquete deja de listarse |

### 4.5 · Trabajo sin red (CAP-048)

| Ruta | Verbo | Cuerpo → respuesta |
|---|---|---|
| `/sync/` | POST | `{dispositivo, emisor_id, eventos:[{secuencia, tipo, ocurrido_en, ocurrido_en_tableta?, carga}], alumno_id?}` → `{acuse: true, servidor_en, resultados[{secuencia, estado, motivo, detalle}], resumen{integrados, duplicados, rechazados, pendientes_decision}, asignaciones[{id, tarea}], veredictos[{asignacion_id, objeto_ref, numero, pregunta_ref, veredicto}]}`. Máximo 200 eventos por envío; se procesan **en orden de secuencia**; cada uno en su transacción; el envío completo es idempotente. Sin sesión se autoriza por el aparato asignado (D-11) |
| `/sync/status/?dispositivo=&emisor_id=` | GET | `{emisor_id, ultima_secuencia, conteos{synced, rejected, conflict}, pendientes_decision[{secuencia, tipo, asignacion_id, motivo}]}` |

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
| `/docente/asignaciones/{id}/` | GET | `AsignacionDocente` + `alumnos[{alumno_id, rotulo, estado, vencida, fuera_de_plazo, avance_pct, bloques_atendidos, bloques_total, ultimo_avance_en, completada_en, practica{intentos, mejor_correctas, total}, paquete{estado}, dispositivo{id, nombre, perfil}\|null, pendientes_decision}]` — **quién completó** (CAP-051): los destinatarios (grupo activo o selección) con o sin tarea |
| `/docente/asignaciones/{id}/` | PATCH | `{fecha_limite?, plazo?, gracia_min?, titulo?, consigna?, paquete_permitido?}` (endurecer o mover la fecha) |
| `/docente/asignaciones/{id}/cerrar/` | POST | → `AsignacionDocente` en `cerrada` · `estudio.asignacion.cerrada.v1` |
| `/docente/asignaciones/{id}/decisiones/` | POST | `{alumno_id, secuencia, emisor_id?, decision: "aceptar"\|"descartar", actor?}` → resuelve un `pendiente_decision` (BR-074): aceptar aplica el evento guardado |

### 4.7 · MOD-009 · dispositivos asignados

| Ruta | Verbo | Permiso | Cuerpo → respuesta |
|---|---|---|---|
| `/api/dispositivos/{id}/asignar/` | POST | `device.assign` | `{alumno_id, actor?}` → dispositivo con `perfil: "asignado"`. Un aparato que ya es de otra persona: 409 `dispositivo_ya_asignado` (primero se libera). `dispositivo.asignado.v1` + bitácora |
| `/api/dispositivos/{id}/liberar/` | POST | `device.release` | `{actor?}` → dispositivo `compartido`. 409 `paquete_sin_integrar` si tiene un paquete de estudio activo (`solicitado`, `descargandose`, `disponible`). `dispositivo.liberado.v1` + bitácora |

---

## 5 · Cliente (Core, C#)

`Avacom.Lms.Core/Estudio/`: `EstudioModels.cs` (los DTO de arriba como `record`), `IEstudioApi`/`EstudioApi` (alumno y profesor; mismas reglas de degradación que `AulaApi`), `ArchivoCifrado` (AES-256-GCM por bloques de 64 KiB con acceso aleatorio), `AlmacenPaquetes` (manifiestos y medios cifrados por alumno, vigencia, espacio, borrado), `DescargadorDePaquetes` (reanudable, con progreso, pausa y verificación de huella), `ColaEstudio` (cola cifrada con `emisor_id` y secuencia persistida **antes** de enviar), `SincronizadorEstudio` y `ServidorLocalDeMedios` (HTTP en `127.0.0.1` con `Range`, para que la lección descargada se lea sin red con los mismos visores). La clave local la entrega `IProveedorDeClave` (Student: `SecureStorage` en Android y DPAPI en Windows).

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
| Student | menú | hexágono «Modo de estudio» sólo con `estado.disponible` (008-01); «Salir» cierra la sesión de estudio (008-07) |
| OPS | «Modo de estudio» (`EstudioPage`) | asignar una lección a un grupo o a alumnos, con fecha límite por opciones; ver quién completó; cerrar |
| OPS | «Dispositivos» | marcar un aparato como asignado a un alumno o compartido (008-01) |

## 8 · Pruebas exigidas

Backend: arquitectura (dominio y aplicación sin framework, vistas sin ORM, tablas `m08_*`, sin columnas de clave, `m07_intento` y `m10_intento` intactos tras practicar); permisos; asignaciones (grupo, selección, visibilidad, cierre); lección (abrir, reanudar, progreso monótono, completar con y sin bloques pendientes, expediente); paquete (asignado sí, compartido no con evento, ajeno, manifiesto y huella, `Range`, confirmar con huella mala, vigencia y versión, retirar y volver a pedir); práctica (calificar, reanudar, terminar, reintentar, sin biblioteca guarda sin calificar); sincronización (reenvío idempotente, orden, sin sesión, ajeno, plazo blando y endurecido, decisión del profesor); dispositivos (asignar, liberar, precondición).
Core: cifrado (ida y vuelta, acceso aleatorio, manipulación detectada), descarga reanudable con huella, cola (secuencia que no retrocede, persiste antes de enviar, acuse borra), sincronizador (sin conexión conserva, duplicado no reenvía).

## 9 · Preguntas para el CTO

| # | Pregunta |
|---|---|
| Q-66 | ¿Qué bloques de una lección son obligatorios? Hoy todos (D-4). ¿Hace falta una marca `required` en el esquema de curso? |
| Q-67 | ¿Práctica con feedback **sin** red? Hoy se guarda y se califica al reconectar (D-6). Exige que Contenido publique verificación local sin exponer la clave. |
| Q-68 | ¿Dónde vive la configuración de modo de estudio por nivel (008-09, DEC-017)? |
| Q-69 | ¿Un aparato compartido debe poder usar el modo de estudio **en línea** (FUN-080, DEC-013) o el hexágono sigue siendo sólo del aparato del alumno (008-01)? |
| Q-70 | La práctica y las tareas viven provisionalmente en `m08_*`. ¿Pasan a MOD-010 (con `intento.asignacion_id` y `modo`, como propone la tabla 008-05) cuando exista? |
| Q-71 | Simulaciones sin red: la API no lista los archivos de una simulación, por eso no se empaquetan. ¿Contenido puede publicar el listado? |
