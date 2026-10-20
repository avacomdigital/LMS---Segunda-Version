"""
Catálogos cerrados de MOD-011 · Gradebook: modos, estados, tipos, escalas, eventos `calificacion.*.v1`, acciones de auditoría y permisos `grades.*`.
Son VALORES del dominio, no tablas. Ningún archivo de esta carpeta importa Django.

Lo que MOD-011 posee (escritor único, BR-003): la calificación normalizada de cada intento con su historial, las escalas con sus versiones, la
configuración de modo por nivel educativo, la política institucional, la clasificación de las evaluaciones y lo derivado (resultado por asignación,
agregado por periodo). Lo que NO posee: los intentos, las respuestas y las rúbricas (MOD-010 y la biblioteca), los grupos y los periodos (MOD-001/002)
ni el progreso del estudiante (MOD-012).
"""
from __future__ import annotations

# ------------------------------------------------------------------------------ el modo por nivel educativo (FUN-125)
# `simple` es el modo por defecto: sin una fila de configuración, un nivel está en modo simple. El alumno no ve notas ni letras: ve su estado.
SIMPLE, CALIFICACIONES = "simple", "calificaciones"
MODOS = (SIMPLE, CALIFICACIONES)

# Los cinco niveles del Documento Maestro (`acceso.dominio.valores.NivelEducativo`). Se repiten aquí para que el dominio no dependa de otro módulo.
NIVELES = ("preescolar", "primaria", "secundaria", "bachillerato", "preuniversitario")

# ------------------------------------------------------------------------------------------- la calificación (ENT-013)
# Estados guardados. `pendiente` y `provisional` NO se guardan: una actividad sin calificar no es un cero, y lo parcial no es una calificación (se
# deducen del intento de MOD-010 al consultar).
#   revisada    registrada con todos sus componentes resueltos (automáticos o por el profesor); el alumno aún no la ve
#   definitiva  el profesor la publicó: es la que ve el alumno; un cambio posterior es un ajuste auditado
#   reabierta   el profesor la reabrió para recalificar (FUN-122): su publicación se retira hasta que se confirme la nueva revisión
#   anulada     MOD-010 anuló el intento (una persona, con motivo): no cuenta para nada
REVISADA, DEFINITIVA, REABIERTA, ANULADA = "revisada", "definitiva", "reabierta", "anulada"
ESTADOS_CALIFICACION = (REVISADA, DEFINITIVA, REABIERTA, ANULADA)
CUENTAN = (REVISADA, DEFINITIVA)                 # las que entran en el resultado aplicable y en los agregados

# Cómo ve el docente el estado de un resultado (lo que se pinta en el libro): los guardados más lo deducido del intento.
PENDIENTE, PROVISIONAL, REVISADO, DEFINITIVO, REABIERTO, ANULADO, SIN_REGISTRO = (
    "pendiente", "provisional", "revisado", "definitivo", "reabierto", "anulado", "sin_registro")
ESTADOS_DE_RESULTADO = (PENDIENTE, PROVISIONAL, REVISADO, DEFINITIVO, REABIERTO, ANULADO, SIN_REGISTRO)

# Quién produjo la puntuación original: el nodo (autocalificación de MOD-010) o una persona (revisión docente).
AUTOMATICA, DOCENTE = "automatica", "docente"
ORIGENES = (AUTOMATICA, DOCENTE)
SISTEMA = "sistema"

# Las reglas de puntuación (INV-019: toda calificación apunta a un intento, un evaluador y UNA REGLA).
REGLA_AUTOMATICA = "mod10.porcentaje.v1"                 # el porcentaje 0–100 que calculó MOD-010 con las claves de la biblioteca
REGLA_REVISION_DOCENTE = "mod10.revision_docente.v1"     # MOD-010 más la puntuación manual de reactivos abiertos
REGLAS = (REGLA_AUTOMATICA, REGLA_REVISION_DOCENTE)

# Qué cambió en una calificación (cada cambio es una fila de `m11_calificacion_version`, sólo inserción).
V_REGISTRO, V_RECALCULO, V_AJUSTE, V_VALORACION, V_REAPERTURA, V_PUBLICACION, V_RETIRO, V_ANULACION, V_RETROALIMENTACION = (
    "registro", "recalculo", "ajuste", "valoracion", "reapertura", "publicacion", "retiro_publicacion", "anulacion", "retroalimentacion")
TIPOS_DE_VERSION = (V_REGISTRO, V_RECALCULO, V_AJUSTE, V_VALORACION, V_REAPERTURA, V_PUBLICACION, V_RETIRO, V_ANULACION, V_RETROALIMENTACION)

# --------------------------------------------------------------------------------------- tipos de evaluación (pedagogía)
DIAGNOSTICA, FORMATIVA, SUMATIVA = "diagnostica", "formativa", "sumativa"
TIPOS_DE_EVALUACION = (DIAGNOSTICA, FORMATIVA, SUMATIVA)

# ---------------------------------------------------------------------------------------------------- estado simple
# Estado de presentación del modo simple (FUN-126). Se deduce de los intentos de MOD-010; MOD-012 sigue siendo el dueño del progreso del estudiante.
NO_INICIADO, EN_PROGRESO, COMPLETADO = "no_iniciado", "en_progreso", "completado"
ESTADOS_SIMPLES = (NO_INICIADO, EN_PROGRESO, COMPLETADO)

# Los estados del intento de MOD-010 que importan aquí (sus valores; no se importa su módulo).
I_NO_INICIADO, I_EN_REVISION, I_CALIFICADO, I_ANULADO, I_ENTREGADO = "no_iniciado", "en_revision_docente", "calificado", "anulado", "entregado"
I_ENTREGADOS = (I_ENTREGADO, I_EN_REVISION, I_CALIFICADO)
I_VIVOS = ("en_curso", "pausado_desconexion", "restaurando", "en_curso_fuera_de_plazo")
A_EN_CURSO = ("programada", "activa", "activa_fuera_de_plazo")      # asignaciones de MOD-010 que cuentan como «evaluaciones en curso»

# --------------------------------------------------------------------------------------------- escalas (FUN-124)
NUMERICA, ALFABETICA, CUALITATIVA, COMPETENCIAS = "numerica", "alfabetica", "cualitativa", "competencias"
TIPOS_DE_ESCALA = (NUMERICA, ALFABETICA, CUALITATIVA, COMPETENCIAS)
# Cómo se pasa de la escala interna 0–100 a lo que se presenta:
#   interpolada  una polilínea de puntos (interno → valor): cubre la lineal (dos puntos) y la que tiene una exigencia (p. ej. 60 % ↔ 4,0)
#   tramos       el intervalo del interno donde cae decide la etiqueta (letras, conceptos, niveles de competencia)
INTERPOLADA, TRAMOS = "interpolada", "tramos"
CONVERSIONES = (INTERPOLADA, TRAMOS)
# Reglas de redondeo, deterministas y sobre Decimal.
MITAD_ARRIBA, MITAD_PAR, ABAJO, ARRIBA = "mitad_arriba", "mitad_par", "abajo", "arriba"
REDONDEOS = (MITAD_ARRIBA, MITAD_PAR, ABAJO, ARRIBA)
MAX_DECIMALES = 4

# ------------------------------------------------------------------------------ política de intentos (4.5)
# MOD-010 no declara cuál intento cuenta cuando hay varios: la selección es una política CONFIGURABLE de la institución, con `ultimo` como
# comportamiento provisional documentado (el último intento registrado). Se sustituye por lo que declare MOD-010 en cuanto lo declare.
ULTIMO, MEJOR, PRIMERO, PROMEDIO = "ultimo", "mejor", "primero", "promedio"
POLITICAS_DE_INTENTOS = (ULTIMO, MEJOR, PRIMERO, PROMEDIO)
POLITICA_PROVISIONAL = ULTIMO

# ------------------------------------------------------------------------------------------- bandeja de revisión
R_PENDIENTE, R_REABIERTA = "pendiente", "reabierta"
MOTIVOS_DE_REVISION = (R_PENDIENTE, R_REABIERTA)
REVISION_MANUAL, REVISION_RUBRICA = "manual", "rubrica"
TIPOS_DE_REVISION = (REVISION_MANUAL, REVISION_RUBRICA)
# Lo que exige revisión humana: respuesta abierta, dibujo y proyecto o entrega (la biblioteca hoy sólo publica `open`; dibujo y audio llegan como
# referencias a MOD-014 dentro de la respuesta abierta: `drawingRef`, `audioRef`).
FORMAS_DE_REVISION = ("abierta", "dibujo", "proyecto")

# ----------------------------------------------------------------------------------------------------- eventos
# Los once nombres del Documento Maestro (sección L de MOD-011); `libro_exportado` es de V1.
EV_REGISTRADA = "calificacion.registrada.v1"
EV_MANUAL_APLICADA = "calificacion.manual_aplicada.v1"
EV_RUBRICA_APLICADA = "calificacion.rubrica_aplicada.v1"
EV_INTENTO_REABIERTO = "calificacion.intento_reabierto.v1"
EV_AJUSTADA = "calificacion.ajustada.v1"
EV_ESCALA_CONVERTIDA = "calificacion.escala_convertida.v1"
EV_MODO_CAMBIADO = "calificacion.modo_cambiado.v1"
EV_ESTADO_SIMPLE = "calificacion.estado_simple_calculado.v1"
EV_AGREGADOS = "calificacion.agregados_recalculados.v1"
EV_LIBRO_EXPORTADO = "calificacion.libro_exportado.v1"                 # V1
EV_DERIVADAS_RECONSTRUIDAS = "calificacion.derivadas_reconstruidas.v1"
EVENTOS_DEL_MAESTRO = (EV_REGISTRADA, EV_MANUAL_APLICADA, EV_RUBRICA_APLICADA, EV_INTENTO_REABIERTO, EV_AJUSTADA, EV_ESCALA_CONVERTIDA,
                       EV_MODO_CAMBIADO, EV_ESTADO_SIMPLE, EV_AGREGADOS, EV_LIBRO_EXPORTADO, EV_DERIVADAS_RECONSTRUIDAS)
# EXTENSIÓN TÉCNICA PROPUESTA (no están en el Documento Maestro): la publicación, la valoración docente, la anulación y la configuración.
EV_PUBLICADA = "calificacion.publicada.v1"
EV_PUBLICACION_RETIRADA = "calificacion.publicacion_retirada.v1"
EV_VALORACION = "calificacion.valoracion_docente.v1"
EV_ANULADA = "calificacion.anulada.v1"
EV_ESCALA_ADOPTADA = "calificacion.escala_adoptada.v1"
EV_POLITICA = "calificacion.politica_configurada.v1"
EV_CLASIFICACION = "calificacion.clasificacion_definida.v1"
EV_RETROALIMENTADA = "calificacion.retroalimentada.v1"
EV_OBSERVACION = "calificacion.observacion_registrada.v1"
EVENTOS_PROPUESTOS = (EV_PUBLICADA, EV_PUBLICACION_RETIRADA, EV_VALORACION, EV_ANULADA, EV_ESCALA_ADOPTADA, EV_POLITICA, EV_CLASIFICACION, EV_RETROALIMENTADA,
                      EV_OBSERVACION)
EVENTOS = EVENTOS_DEL_MAESTRO + EVENTOS_PROPUESTOS

# Los eventos de MOD-010 (`m10_evento_salida`) que este módulo consume. Todos llevan `asignacion_id`, `alumno_id` e `intento_id`.
EV10_INTENTO_ABIERTO = "evaluacion.intento_abierto.v1"
EV10_INTENTO_ENTREGADO = "evaluacion.intento_entregado.v1"
EV10_INTENTO_FUERA_DE_PLAZO = "evaluacion.intento_fuera_de_plazo.v1"
EV10_REVISION_SOLICITADA = "evaluacion.revision.solicitada.v1"
EV10_INTENTO_CALIFICADO = "evaluacion.intento_calificado.v1"
EV10_INTENTO_ANULADO = "evaluacion.intento_anulado.v1"
EV10_ENVIO_TARDIO_DECIDIDO = "evaluacion.envio_tardio_decidido.v1"
EV10_INTENTO_REACTIVADO = "evaluacion.intento_reactivado.v1"
EVENTOS_CONSUMIDOS = (EV10_INTENTO_ABIERTO, EV10_INTENTO_ENTREGADO, EV10_INTENTO_FUERA_DE_PLAZO, EV10_REVISION_SOLICITADA, EV10_INTENTO_CALIFICADO,
                      EV10_INTENTO_ANULADO, EV10_ENVIO_TARDIO_DECIDIDO, EV10_INTENTO_REACTIVADO)
CONSUMIDOR = "gradebook.evaluacion"          # el nombre de la marca de lectura
FUENTE_EVENTOS = "m10_evento_salida"

# ---------------------------------------------------------------------------------- auditoría (MOD-019)
# Acciones del catálogo cerrado de `audit.dominio.catalogos`. `calificacion.modificada` y `calificacion.reabierta` ya estaban reservadas.
A_REGISTRADA = "calificacion.registrada"
A_MANUAL = "calificacion.manual_aplicada"
A_RUBRICA = "calificacion.rubrica_aplicada"
A_MODIFICADA = "calificacion.modificada"
A_REABIERTA = "calificacion.reabierta"
A_PUBLICADA = "calificacion.publicada"
A_PUBLICACION_RETIRADA = "calificacion.publicacion_retirada"
A_VALORACION = "calificacion.valoracion_docente"
A_ANULADA = "calificacion.anulada"
A_MODO_CAMBIADO = "calificacion.modo_cambiado"
A_ESCALA_ADOPTADA = "calificacion.escala_adoptada"
A_POLITICA = "calificacion.politica_configurada"
A_CLASIFICACION = "calificacion.clasificacion_definida"
A_DENEGADA = "calificacion.modificacion_denegada"
A_DERIVADAS = "calificacion.derivadas_reconstruidas"
A_RETROALIMENTADA = "calificacion.retroalimentada"
A_EVENTO_OMITIDO = "calificacion.evento_omitido"
A_OBSERVACION = "calificacion.observacion_registrada"
ACCIONES_NUEVAS = (A_REGISTRADA, A_MANUAL, A_RUBRICA, A_PUBLICADA, A_PUBLICACION_RETIRADA, A_VALORACION, A_ANULADA, A_MODO_CAMBIADO,
                   A_ESCALA_ADOPTADA, A_POLITICA, A_CLASIFICACION, A_DENEGADA, A_DERIVADAS, A_RETROALIMENTADA, A_EVENTO_OMITIDO, A_OBSERVACION)

# ------------------------------------------------------------------------------ observaciones del docente (boletín)
# Lo que el profesor recomienda a un estudiante en un periodo (la cuarta pregunta del boletín: «¿qué debe mejorar?»). El nodo principal no tiene teclado: las
# recomendaciones son frases de un catálogo cerrado que se tocan; el texto libre es un extra opcional. Una observación es de un alumno en un grupo y un periodo,
# general (`curso_ref` vacío) o de un curso.
RECOMENDACIONES: dict[str, str] = {
    "repasar_conceptos": "Repasar los conceptos básicos de la materia antes de la próxima evaluación",
    "practicar_ejercicios": "Practicar más ejercicios del tema con el modo estudio",
    "leer_con_atencion": "Leer con atención el enunciado completo antes de responder",
    "justificar_respuestas": "Justificar las respuestas con el procedimiento o un ejemplo",
    "revisar_antes_de_entregar": "Revisar las respuestas antes de entregar",
    "participar_en_clase": "Participar más en las actividades de clase",
    "entregar_a_tiempo": "Entregar las evaluaciones y tareas dentro del plazo",
    "pedir_ayuda": "Pedir ayuda al profesor cuando algo no quede claro",
    "organizar_el_tiempo": "Organizar el tiempo de estudio en casa",
    "trabajo_en_equipo": "Colaborar con los compañeros en el trabajo en equipo",
    "mantener_el_ritmo": "Mantener el ritmo de trabajo: va bien",
    "ampliar_lecturas": "Ampliar con lecturas y retos adicionales: puede ir más allá",
    "acompanamiento_familiar": "Conviene el acompañamiento de la familia en las tareas",
    "apoyo_especializado": "Conviene valorar un apoyo pedagógico especializado",
}
MAX_RECOMENDACIONES = 6
MAX_OBSERVACION = 600

# Cuántas veces seguidas puede fallar la aplicación de UN evento de MOD-010 antes de que el libro lo deje atrás (con su asiento en la bitácora): un fallo pasajero
# se reintenta en el siguiente ciclo y un evento que nunca se puede aplicar no detiene la cola para siempre.
MAX_FALLOS_DE_EVENTO = 5

# -------------------------------------------------------------------------------------------------- permisos
# Los cinco del Documento Maestro (sección J de MOD-011). `grades.export` es de V1 (se siembra; la ruta llega con V1). `grades.publish` es una
# EXTENSIÓN TÉCNICA PROPUESTA: el Maestro regula la visibilidad (el alumno no ve notas sin publicar) pero no da una función propia a publicar.
# Leer el libro usa `results.read`, que ya existe (el docente sobre sus grupos, la administración y reportes sobre toda la organización).
P_MODIFY, P_REOPEN, P_RUBRIC_APPLY, P_MODE_SET, P_EXPORT = (
    "grades.modify", "grades.reopen", "grades.rubric.apply", "grades.mode.set", "grades.export")
P_PUBLISH = "grades.publish"
P_READ = "results.read"
PERMISOS_DEL_MAESTRO = (P_MODIFY, P_REOPEN, P_RUBRIC_APPLY, P_MODE_SET, P_EXPORT)
PERMISOS_PROPUESTOS = (P_PUBLISH,)
PERMISOS = PERMISOS_DEL_MAESTRO + PERMISOS_PROPUESTOS
PERMISOS_DEL_DOCENTE = (P_MODIFY, P_REOPEN, P_RUBRIC_APPLY, P_PUBLISH)      # calificar es del profesor sobre SUS grupos
PERMISOS_DE_ADMINISTRACION = (P_MODE_SET, P_EXPORT)                         # configurar el modo y exportar; la administración no califica directamente

# Tamaños y topes
MAX_MOTIVO = 300
MIN_MOTIVO = 3
MAX_COMENTARIO = 2000
