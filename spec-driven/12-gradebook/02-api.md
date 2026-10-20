# 12 · Gradebook (MOD-011) · API `/api/gradebook/`

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-14) en `backend/gradebook/`. El diseño, las decisiones y lo pendiente están en [01-diseno.md](01-diseno.md). |
| Respuestas reales | `tests/Avacom.Lms.Core.Tests/Fixtures/gradebook/*.json`: las captura `backend/gradebook/tests/test_capturar_contrato.py` contra el backend de verdad. Un DTO de C# que no las lee bien es un DTO mal escrito. |
| Cliente | `src/Avacom.Lms.Core/Gradebook/` (`GradebookApi`, `IGradebookApi`, `IGradebookAlumnoApi`, `ModelosGradebook`, `GradebookTexto`). |

## 0 · Convenciones

- **Escala interna 0–100**, `Decimal` con dos decimales. En el JSON viajan como números (`71.43`); el cálculo nunca usa `float` (la conversión a número es lo último que pasa). Una puntuación escrita por una persona se rechaza si sale de 0–100, trae más de dos decimales, no es un número (texto no numérico, booleano, lista u objeto), `NaN`, infinito o un exponente absurdo (`1e999999`) → `400 puntaje_invalido`. El texto numérico (`"85,5"`) se acepta. Los puntos de un reactivo puntuado a mano van de 0 a 100 000 con dos decimales como máximo (el máximo del reactivo lo hace cumplir MOD-010).
- **Quién actúa.** Con sesión (MOD-001), quien firma el JWT. Sin sesión (Q-34, prototipo) el profesor se declara con `actor` (consulta o cuerpo) y el alumno con `alumno_id`. Con `AVACOM_LMS_EXIGIR_SESION=1`, 401 a lo anónimo.
- **Tiempo.** Toda marca es del reloj del **nodo**, en milisegundos. Nada usa el reloj del cliente.
- **Errores.** `{detail, codigo, …extras}`. Los extras nunca pisan `detail` ni `codigo`.

  | HTTP | `codigo` |
  |---|---|
  | 400 | `datos_invalidos` · `puntaje_invalido` · `escala_invalida` (+`problemas[]`, uno por regla incumplida) · `falta_alumno` |
  | 403 | `sin_permiso` (+`permiso`) · `fuera_de_alcance` (el permiso existe pero no llega a ese grupo) |
  | 404 | `no_encontrado` |
  | 409 | `conflicto_de_version` (+`version_actual`, `puntaje_efectivo`, `estado`, `version_esperada`) · `transicion_invalida` · `intento_no_calificable` (+`motivo`) · `reactivos_pendientes` (+`pendientes[]`) · `no_publicable` (+`motivos[]`) · `modo_simple` · `evaluaciones_en_curso` (+`en_curso`) · `escala_no_vigente` · `rubrica_no_disponible` · `revision_no_pendiente` (+`calificacion_id` si ya estaba confirmada) · `solicitud_repetida` · `no_instalado` |
  | 503 y los de MOD-010 | lo que MOD-010 rechaza (`fuente_no_disponible`, `dispositivo_bloqueado`…) llega con **su mismo código y estado** |

- **Idempotencia.** Todo cambio acepta `solicitud_id` (≤ 64 caracteres). Reenviar la misma devuelve lo ya hecho con `reintento: true` y **no** duplica la revisión, el ajuste, el evento ni el asiento. Es lo que hace seguro reintentar tras perder la señal. **Una clave es de UNA operación:** reutilizarla para otra clase de cambio, otro valor o otra pregunta da **409 `solicitud_repetida`** (no un «ya hecho» que no hizo nada): manda una nueva por cada acción. Repetir lo mismo en la configuración (la política, la clasificación de una evaluación, la definición de una escala) tampoco repite eventos, asientos ni versiones: responde `cambiado: false` (la escala, `reintento: true`). **Confirmar una revisión** no lleva clave: su reintento recibe 409 `revision_no_pendiente` con el `calificacion_id`, y un cliente lo trata como «ya confirmada».
- **Concurrencia optimista.** Los cambios sobre una calificación exigen `version_esperada` (la `version` que se leyó). Si otra persona cambió la calificación, **409 `conflicto_de_version`** con la versión y el valor actuales: no se pisa el cambio del otro. La comparación es una sola sentencia `UPDATE … WHERE version = ?`.
- **Una calificación por intento**, y sólo cuando el intento está calificado del todo en MOD-010. Lo pendiente **nunca** es un cero (`puntaje_efectivo: null`, estado `pendiente` o `provisional`).

> **2026-10-19.** El libro y el boletín se segmentan por materia y por curso (`subject=`, `curso_ref=`), toda calificación trae `bruto` (puntos, porcentaje) y el profesor deja recomendaciones por periodo (`PUT estudiantes/{id}/observacion/`): ver [05-correcciones-cto-2026-10-19.md §3](05-correcciones-cto-2026-10-19.md#3--api-lo-que-se-añade-a-02-apimd).

## 1 · El profesor: leer (permiso `results.read`)

| Ruta | Verbo | Qué hace |
|---|---|---|
| `libro/?grupo_id=&asignacion_id=&periodo=&curso_ref=&q=&vista=` | GET | **El libro del grupo**: `grupo`, `modo` (`simple`/`calificaciones`), `escala` (del nivel), `politica_intentos`, `asignaciones[]` (las columnas: `id`, `titulo`, `tipo_evaluacion`, `afecta_oficial`, `por_revisar`…), `alumnos[]` (`alumno_id`, `rotulo`, `celdas{asignacion_id → celda}`, `agregados[]`) y `totales`. Antes de responder se pone al día con lo que MOD-010 ya publicó. **`vista=resumen`** (la que usan las listas de OPS) no manda las celdas (`celdas: {}`) sino lo que lleva cada estudiante en `alumnos[].resumen` (`evaluaciones`, `conteo`, `promedio_simple`, `presentado`) y lo que hay que hacer con cada evaluación en `asignaciones[].conteo` (completadas, con nota, publicadas, sin publicar, por revisar, sin registro, pendientes, aprobadas, no aprobadas); sin `vista` o con `vista=completo`, el libro de siempre (que también trae esos resúmenes). En modo simple el nodo no cuenta notas, registros ni publicaciones. |
| `resumen/?grupo_id=&periodo=&curso_ref=` | GET | El periodo: por curso y alumno, `calificaciones`, `promedio_simple`, `pendientes`, `provisionales`, `publicadas`; `promedio_del_grupo` sólo con ≥ 3 alumnos (CMP-043). **`oficial: false`, `ponderado: false`**: promedio simple informativo. |
| `estudiantes/{alumno_id}/?grupo_id=` | GET | Historial del estudiante: por grupo, sus `calificaciones[]`, `resultados[]` y `agregados[]`. |
| `asignaciones/{id}/` | GET | Calificaciones e intentos de una evaluación: por alumno, sus `intentos[]` (cada uno con su `calificacion`), el `resultado` aplicable, `politica_intentos` y `clasificacion`. |
| `estudiantes/{id}/boletin/?grupo_id=&curso_ref=&desde=&limite=` | GET | **El boletín de un estudiante en un grupo** (vista del profesor; `results.read` sobre el grupo; `grupo_id` obligatorio). Responde `{alumno, grupo, modo, sistema, resumen{evaluaciones, conteo{completadas, con_nota, publicadas, sin_publicar, por_revisar, sin_registro, pendientes, aprobadas, no_aprobadas}, promedio_simple, presentado, oficial:false, ponderado:false}, cursos[{curso_ref, curso_rotulo, evaluaciones, conteo, promedio_simple, presentado}], insights{tendencia, mejor_curso, curso_a_reforzar, constancia, comentarios{fortalezas, dificultades, oportunidades}, informativo:true}, evaluaciones{curso_ref, total, desde, limite, items[]}}`. `evaluaciones` es UNA página, de la evaluación más reciente a la más antigua (por la fecha de la evaluación): las de `curso_ref` si se pide, o las más recientes de todos los cursos. Cada `item` trae el estado, la nota presentada (provisional mientras no se publica), el resultado interno que sólo ve el profesor y si está ajustada. `limite` 1–100 (20 por defecto), `desde` ≥ 0; otra cosa, 400. Sin `grupo_id`, 400; un estudiante que no es del grupo ni tiene calificaciones en él, 404. En modo simple no hay `sistema` ni cifras. |
| `calificaciones/{id}/` | GET | Una calificación con su `historial[]` (versiones), las `revisiones[]` que la produjeron, un resumen del `intento` y el `sistema` con que se presentó (la versión estampada al publicar, o la vigente si aún no se publicó). |

**La celda** (`libro.alumnos[].celdas[asignacion]`): `estado_simple` (`no_iniciado`/`en_progreso`/`completado`), `estado` (`pendiente`, `provisional`, `revisado`, `definitivo`, `reabierto`, `anulado`, `sin_registro`), `publicada`, `ajustada`, `intentos{total, registrados}`, `calificacion_id`, `version`, `puntaje_efectivo`, `puntaje_original`, `presentacion`, `politica_intentos`.

**La calificación** (`salida_calificacion`): `puntaje_original` (lo que se registró; **no cambia jamás**), `puntaje_efectivo` (el vigente), `ajustada`, `regla_puntuacion` (`mod10.porcentaje.v1` o `mod10.revision_docente.v1`), `origen` (`automatica`/`docente`), `evaluador_id` (`sistema` o la persona), `estado` (`revisada` → `definitiva`; `reabierta`; `anulada`), `version`, `publicada`/`publicada_en`/`publicada_por`, `desempeno_docente`, `retroalimentacion{fortalezas, dificultades, oportunidades, comentario}`, `adaptacion`, `presentacion`, `desfase_con_evaluacion` (MOD-010 ya no dice lo que se tomó de él: alguien cambió allá la puntuación sin reabrir aquí; **no se pisa en silencio**, se avisa).

**La presentación** separa cuatro cosas que no son la misma: `{interno, presentada{valor, etiqueta, clave}, desempeno{nivel, clave, tramo, origen: calculo|docente}, aprobacion{cumple_criterio}, escala{…, version_id, huella}, provisional}`. Antes de publicar es `provisional: true` (con la escala vigente del nivel); al publicar queda **estampada** con la versión de escala de entonces.

## 2 · El profesor: revisar (FUN-120, FUN-121)

| Ruta | Verbo | Permiso | Qué hace |
|---|---|---|---|
| `revisiones/?grupo_id=&asignacion_id=` | GET | `grades.modify` o `grades.rubric.apply` | **La bandeja**: `items[]` con `motivo` `pendiente` (intento en `en_revision_docente`, con `pendientes[]`) o `reabierta` (una calificación reabierta), `total`, `pendientes`, `reabiertas`. Sin `grupo_id`, sólo los grupos del profesor **más lo asignado a alumnos sueltos** que opera (la asignó o enseña a alguno de sus alumnos; de esas, sólo los intentos de sus alumnos). |
| `revisiones/{intento}/` | GET | idem | Un intento para revisar: `intento{…pendientes, reabierta, puede_confirmar}` y `filas[]` por pregunta: `forma` (`abierta`/`dibujo`/`proyecto`), `enunciado`, `respuesta`, `evidencias[]` (referencias a MOD-014: sólo `{tipo, ref}`), `requiere_revision`, `pendiente`, `puntaje_actual`, `comentario` y, si la hay, la `rubrica{criterios[{id, criterio, puntos_max}], respuesta_modelo, puntos}` de la biblioteca. |
| `revisiones/{intento}/respuestas/{pregunta_ref}/` | POST | `grades.modify` (manual) · `grades.rubric.apply` (rúbrica) | **Manual** `{puntaje, comentario?, motivo?, solicitud_id?}` o **rúbrica** `{criterios:[{criterio_id, puntos}], comentario?, …}` (deben venir *todos* los criterios; cada uno de 0 a lo que vale; el total no supera lo que vale la pregunta). Cambiar un puntaje ya asentado exige `motivo`. Devuelve `{puntaje, pendientes[], listo_para_confirmar, porcentaje_provisional, reintento}`. |
| `revisiones/{intento}/confirmar/` | POST | idem | Con todo puntuado, cierra la revisión (MOD-010 pasa el intento a `calificado`) y **registra la calificación** (FUN-119). Con pendientes, 409 `reactivos_pendientes`. Para una calificación reabierta, la recalcula: si recalificar **no** cambió lo que dice MOD-010, un **ajuste** del profesor sigue vigente; si lo cambió, el ajuste se descarta y la respuesta lo dice (`ajuste_descartado: true`, `ajuste_anterior`) además de quedar en el historial. |
| `intentos/{id}/registrar/` | POST | `grades.modify` | El registro a petición (lo que el consumidor hace solo): útil cuando un nivel pasó de modo simple a calificaciones. 409 `intento_no_calificable` (+`motivo`) o `modo_simple`. |

La puntuación de cada reactivo **la asienta MOD-010** (dueño de la respuesta), con sus reglas y su permiso `assessment.review`; el libro guarda la **traza** (`m11_revision`: puntaje, desglose por criterio, comentario, quién, cuándo) y la calificación resultante. Una calificación ya registrada **no** se puntúa por la puerta de atrás: primero se reabre.

## 3 · El profesor: cambiar una calificación (FUN-122, FUN-123)

Todos devuelven `{calificacion, historial[], reintento, servidor_en}` y exigen `version_esperada` (salvo `publicar`, donde es opcional).

| Ruta | Permiso | Cuerpo | Efecto |
|---|---|---|---|
| `calificaciones/{id}/ajustar/` | `grades.modify` | `{puntaje_nuevo, motivo, version_esperada, solicitud_id?}` | **FUN-123.** Cambia `puntaje_efectivo`; el original queda; fila de historial `ajuste` con valor anterior, nuevo, motivo, quién y cuándo (reloj del nodo); asiento `calificacion.modificada`; evento `calificacion.ajustada.v1`. Sin motivo (≥ 3 letras) → 400. Sobre una publicada es válido y queda marcado `posterior_a_publicacion` y se vuelve a presentar con la **misma** versión de escala. No se ajusta una `reabierta` ni una `anulada`. |
| `calificaciones/{id}/reabrir/` | `grades.reopen` | `{motivo, version_esperada, solicitud_id?}` | **FUN-122.** Pasa a `reabierta`: deja de contar, el alumno deja de verla y entra a la bandeja. Un evento (viejo o nuevo) **nunca** cierra una reapertura: la cierra el profesor al confirmar su revisión. |
| `calificaciones/{id}/valoracion/` | `grades.modify` | `{tramo, motivo, version_esperada}` | La valoración pedagógica del nivel de desempeño (la presentación no es sólo una cuenta). `tramo: ""` la retira. No cambia el resultado interno. |
| `calificaciones/{id}/retroalimentacion/` | `grades.modify` | `{fortalezas?, dificultades?, oportunidades?, comentario?, adaptacion?, version_esperada}` | Texto del profesor (y el ajuste razonable aplicado). No toca ninguna cifra. |

## 4 · El profesor: publicar (extensión técnica propuesta, permiso `grades.publish`)

| Ruta | Cuerpo | Efecto |
|---|---|---|
| `calificaciones/{id}/publicar/` | `{version_esperada?, solicitud_id?}` | `revisada → definitiva`. Estampa la presentación con la versión de escala vigente del nivel. **Precondiciones, todas en el nodo:** el intento sigue `calificado` del todo en MOD-010 (no anulado, sin revisión pendiente, sin calificación pendiente de la biblioteca), la asignación no está en política `nunca`, el nivel está en modo calificaciones. Si no: 409 `no_publicable` con todos los `motivos`. Idempotente. |
| `calificaciones/{id}/retirar-publicacion/` | `{motivo, version_esperada}` | `definitiva → revisada`; el alumno deja de verla. |
| `asignaciones/{id}/registrar/` | — | **Registrar lo calificado.** Registra las calificaciones de todos los intentos ya calificados de la evaluación (lo mismo que `intentos/{id}/registrar/` para cada uno). Es el camino cuando el nivel pasó de modo simple —o de no tener nivel— a modo calificaciones con la evaluación ya calificada: ese paso **no registra nada solo** (D-2) y la celda queda `sin_registro`. Responde `{registradas, calificaciones[], ya_registradas, no_registrables[{intento_id, alumno_id, motivo, detalle}], en_modo_simple}`; lo que aún no se puede (revisión pendiente…) no tumba a lo demás. Idempotente. Lo registrado queda `revisada` (provisional, sin publicar). Necesita `grades.modify` sobre el grupo. |
| `asignaciones/{id}/publicar/` | `{calificacion_ids?}` | Publica las `revisada` de la asignación (o las indicadas); las que no cumplen se **omiten con su motivo**, no tumban a las demás. |
| `asignaciones/{id}/clasificacion/` | GET · PUT `{tipo_evaluacion, afecta_oficial?, objetivos?}` | Diagnóstica, formativa o sumativa y si cuenta para lo oficial (sin fila: un examen es sumativo y oficial; una actividad, formativa). `objetivos` son referencias a objetivos o competencias de la biblioteca o de MOD-012. Recalcula los agregados. Permiso `grades.modify`. |

## 5 · La administración (`grades.mode.set`; leer, `results.read`)

| Ruta | Verbo | Qué hace |
|---|---|---|
| `configuracion/` | GET | Los cinco `niveles[]` (`modo`, `por_defecto`, `escala` —con el sistema: `pais`, `valor_min`, `valor_max`, `aprobacion_minima`, `aprueba_desde`, `tramos[]`—, `version`), la `politica` y las `escalas[]` adoptadas. **Sin fila de configuración un nivel está en modo `simple`.** |
| `niveles/{nivel}/` | PUT | `{modo, escala_id \| escala_version_id, validar?, version_esperada?}`. **FUN-125.** `validar: true` no cambia nada y responde `{permitido, bloqueos[], advertencias[], en_curso, de, a}`. No se alterna el modo mientras haya evaluaciones abiertas, programadas o con intentos vivos en ese nivel (también las asignadas a alumnos sueltos de sus grupos) → 409 `evaluaciones_en_curso`. Cambiar sólo la escala de un nivel que ya calificaba no es un cambio de modo y no descarta nada. Cambiar de modo no convierte nada solo: ni registra las notas técnicas que ya existían ni borra las calificaciones registradas. Idempotente. |
| `politica/` | PUT | `{pais?, jurisdiccion?, institucion?, politica_intentos?, ponderaciones?}`. `politica_intentos`: `ultimo` (**provisional**), `mejor`, `primero`, `promedio`. Cambiarla recalcula lo derivado. Las `ponderaciones` se guardan para V1 y **no se aplican**. Responde `cambiado` (`false` si ya estaba así: no hay evento ni asiento). |
| `escalas/plantillas/?pais=` | GET | El catálogo de plantillas **orientativas** (España —términos y 0–10—, EE. UU. —letras, GPA y porcentaje—, México —0–10 y 5–10—, Colombia, Chile, Perú, Ecuador y las genéricas 0–5, 0–10, 0–20, 0–100, letras y conceptual), cada una con su `advertencia`, `referencia`, `definicion` y `sistema` (el resumen para leerla: rango, mínimo para aprobar y tramos). No presentan nada mientras no se adoptan. |
| `escalas/adoptar/` | POST | `{plantilla, codigo?, nombre?, jurisdiccion?, nota?, definicion?}` → 201. La institución adopta la plantilla (opcionalmente con sus ajustes): nace la escala y su versión 1 con su `huella`. |
| `escalas/` | GET · POST | Listar · crear una escala propia `{codigo, nombre, pais?, jurisdiccion?, nota?, definicion}`. |
| `escalas/{id}/` · `escalas/{id}/versiones/` | GET · POST | Ver con sus versiones · publicar **otra versión** (`{definicion, nota?}`) → 201. Las anteriores no cambian y no hay ruta para editarlas. Una versión nueva no cambia el tipo de la escala. |
| `escalas/vista-previa/` | POST | `{definicion \| escala_version_id \| plantilla, valores?}` → `conversiones[]` (cuatro bloques separados). No guarda nada. |
| `derivados/reconstruir/` | POST | **FUN-129.** `{reproducir?}`: reconstruye el resultado por asignación y el agregado por periodo; con `reproducir`, además reinicia la marca de lectura y vuelve a aplicar todos los eventos de MOD-010 (idempotente). No toca ninguna calificación. También `python manage.py gradebook_reconstruir [--reproducir]`. |
| `sincronizar/` | POST | Pone el libro al día con MOD-010 ahora mismo (el hilo del nodo lo hace cada 5 s y cada consulta del libro también). Lotes de 100 eventos. Un evento que falla retiene la marca: `fallidos[]` lo dice y el ciclo siguiente lo reintenta; tras cinco ciclos seguidos se deja atrás con el asiento `calificacion.evento_omitido` (D-18). |

**La definición de una escala** (`definicion`): `{tipo: numerica|alfabetica|cualitativa|competencias, conversion: interpolada|tramos, decimales 0–4, redondeo: mitad_arriba|mitad_par|abajo|arriba, valor_min, valor_max, puntos: [[interno, valor], …], aprobacion_minima, tramos: [{orden, clave, etiqueta, desde, hasta, nivel_desempeno, aprueba, descripcion}]}`. Los números viajan como **texto** en la definición (para que la huella no dependa de un `float`). Los tramos son `[desde, hasta)` sobre la escala interna (el último incluye el 100) y deben cubrir de 0 a 100 **sin huecos ni solapamientos**; una numérica va por `interpolada` (una polilínea de puntos de 0 a 100, que no decrece). Cualquier incumplimiento → 400 `escala_invalida` con la lista completa de `problemas`.

## 6 · El alumno

| Ruta | Verbo | Qué hace |
|---|---|---|
| `mias/?alumno_id=` | GET | Sus resultados, sólo los suyos. Con sesión, el JWT dice quién es; sin ella, el `alumno_id` debe existir y estar activo (no se comprueba el dispositivo: Q-34). |

Cada `items[]`: `asignacion_id`, `titulo`, `estado_simple`, `simbolo` (`vacio`/`medio`/`lleno`), `modo` y, según el modo:

- **`simple`** (preescolar y todo nivel sin configurar): **ni un número, ni una letra**. Sólo estado y símbolo; `aciertos.simbolos` (`acierto`/`fallo`) únicamente si MOD-010 ya liberó el resultado a ese alumno. La puntuación técnica de MOD-010 no se convierte en nota.
- **`calificaciones`**: antes de publicar, `estado` ∈ `no_iniciado` · `en_progreso` · `entregado` · `en_revision` · `resultado_no_publicado` y `calificacion: null` (**la nota no sale; tampoco una cifra parcial**). Publicada: `estado: publicado` y `calificacion{presentada, desempeno, aprobacion, escala{nombre, tipo}, retroalimentacion, publicada_en, numero_intento}`. **No** lleva el resultado interno (0–100). **Lo mismo en la ruta de MOD-010** (D-24): en un nivel en modo calificaciones, `GET /api/evaluacion/intentos/{id}/resultado/` da 403 `resultados_no_liberados` (con `retenido_por: "libro_de_calificaciones"`) mientras la calificación de ese intento no esté publicada, y `resultado_disponible` es `false` en `estado`, `mias` y la entrega (`que_sigue: resultado_en_libro`); en modo simple manda la política de la evaluación. Lo que se muestra es **lo que cuenta en el libro** (D-20): si el intento que la política elige aún no está publicado, `resultado_no_publicado` (no se enseña otro más viejo); con `promedio`, la media, sólo con todos publicados (`numero_intento: null`).

## 7 · Eventos de salida (`m11_evento_salida`)

Los once del Documento Maestro: `calificacion.registrada.v1` · `manual_aplicada` · `rubrica_aplicada` · `intento_reabierto` · `ajustada` · `escala_convertida` · `modo_cambiado` · `estado_simple_calculado` · `agregados_recalculados` · `libro_exportado` (V1, no se emite todavía) · `derivadas_reconstruidas`. **Extensión técnica propuesta:** `publicada` · `publicacion_retirada` · `valoracion_docente` · `retroalimentada` · `anulada` · `escala_adoptada` · `politica_configurada` · `clasificacion_definida`. Se escriben en la misma transacción que el hecho. Nunca llevan un comentario ni el contenido de una respuesta.

**Consume** de MOD-010 (`m10_evento_salida`, por su interfaz `evaluacion.servicios`, con marca de lectura `m11_marca_consumidor`): `intento_abierto`, `intento_entregado`, `intento_fuera_de_plazo`, `revision.solicitada`, `intento_calificado`, `intento_anulado`, `envio_tardio_decidido`, `intento_reactivado`. El evento no lleva el resultado: avisa que algo cambió y el libro **vuelve a leer el intento** (la fuente de verdad); por eso procesar un evento dos veces no duplica nada.

## 8 · Permisos

| Permiso | Quién | Para qué |
|---|---|---|
| `grades.modify` | Profesor (sus grupos) | Calificar a mano, ajustar, valorar, retroalimentar, clasificar, registrar |
| `grades.rubric.apply` | Profesor (sus grupos) | Aplicar una rúbrica |
| `grades.reopen` | Profesor (sus grupos) | Reabrir para recalificar |
| `grades.publish` *(propuesto)* | Profesor (sus grupos) | Publicar y retirar la publicación |
| `grades.mode.set` | Administración | Modo, escalas, política, reconstruir |
| `grades.export` | Administración | Exportar el libro (V1: la ruta llega con V1) |
| `results.read` (ya existía) | Profesor (sus grupos), administración y reportes (toda la organización); el alumno lo tiene sobre lo suyo | Leer |

El **técnico** no tiene ninguno (ni lee datos académicos); la **administración no califica directamente**; **reportes** sólo lee. Un 403 deja el asiento genérico `acceso.denegado` (019-08) y, si fue un intento de **modificar**, además `calificacion.modificacion_denegada` con quién, qué permiso pedía y sobre qué ruta (TST-069).
