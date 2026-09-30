"""
Catálogos cerrados de MOD-008 · Modo Estudio: alcances, plazos, estados, motivos, tipos de evento de la cola del aparato, eventos
del outbox `estudio.*.v1` y permisos `study.*`. Son VALORES del dominio, no tablas. Ningún archivo de esta carpeta importa Django.

Lo que el módulo NO conoce, y no es un olvido (regla de oro, artículo 14): el contenido del curso ni sus claves de respuesta. El
curso vive en AVACOM Biblioteca; aquí sólo hay referencias (`*_ref`), rótulos de evidencia y la estructura de bloques como
referencias.
"""
from __future__ import annotations

# ------------------------------------------------------------------ la asignación (CAP-050)

GRUPO, SELECCION = "grupo", "seleccion"
ALCANCES = (GRUPO, SELECCION)     # `grupo`: todos los alumnos activos, también los que entren después · `seleccion`: los que se nombran

# D-9 · DEC-014 · DEC-019. `blando` (por defecto): la fecha límite marca, no cierra. `endurecido`: la asignación cierra al vencer.
BLANDO, ENDURECIDO = "blando", "endurecido"
PLAZOS = (BLANDO, ENDURECIDO)
GRACIA_MS_POR_DEFECTO = 15 * 60 * 1000       # DEC-019: 15 minutos

ACTIVA, CERRADA = "activa", "cerrada"
ESTADOS_ASIGNACION = (ACTIVA, CERRADA)

# ---------------------------------------------------------------------------- la tarea del alumno

PENDIENTE, EN_CURSO, COMPLETADA = "pendiente", "en_curso", "completada"   # «vencida» es DERIVADA: fecha pasada y no completada
ESTADOS_TAREA = (PENDIENTE, EN_CURSO, COMPLETADA)

# -------------------------------------------------------------------------- los bloques (D-4)
# Un bloque es la unidad de avance de una lección, en el orden en que se ve. El `exam` NO es bloque: es evaluación formal (BR-055).

LAMINA, PAGINA, LABORATORIO, PRACTICA = "lamina", "pagina", "laboratorio", "practica"
TIPOS_BLOQUE = (LAMINA, PAGINA, LABORATORIO, PRACTICA)

# --------------------------------------------------------------------------- el paquete (D-7, D-8)

SOLICITADO, DESCARGANDOSE, DISPONIBLE, VENCIDO, DENEGADO = "solicitado", "descargandose", "disponible", "vencido", "denegado"
ESTADOS_PAQUETE = (SOLICITADO, DESCARGANDOSE, DISPONIBLE, VENCIDO, DENEGADO)
PAQUETE_ACTIVO = (SOLICITADO, DESCARGANDOSE, DISPONIBLE)   # lo que un equipo conserva; liberar el equipo exige que no haya ninguno

DISPOSITIVO_COMPARTIDO, DISPOSITIVO_AJENO, PAQUETE_NO_PERMITIDO = "dispositivo_compartido", "dispositivo_ajeno", "paquete_no_permitido"
MOTIVOS_DENEGADO = (DISPOSITIVO_COMPARTIDO, DISPOSITIVO_AJENO, PAQUETE_NO_PERMITIDO)
VIGENCIA, VERSION_NUEVA = "vigencia", "version_nueva"
MOTIVOS_VENCIDO = (VIGENCIA, VERSION_NUEVA)

# Por qué un medio de la lección no viaja en el paquete (`no_incluidos[].motivo`).
NO_INCLUIDO_SIMULACION = "simulacion_requiere_nodo"      # Q-71: la API no lista los archivos de una simulación
NO_INCLUIDO_NO_DISPONIBLE = "medio_no_disponible"        # la fuente no lo tiene (o no lo sirve)
NO_INCLUIDO_DEMASIADO_GRANDE = "medio_demasiado_grande"  # supera el tope de tamaño de un medio (AVACOM_ESTUDIO_MEDIO_MAX_MB)

# MSG-046: lo que ve el alumno cuando intenta llevarse el material en una tableta compartida (o asignada a otra persona).
MENSAJE_DESCARGA_DENEGADA = "Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti."
MENSAJE_PAQUETE_NO_PERMITIDO = "Tu profesor no dejó este material para llevártelo. Puedes estudiarlo con la tableta conectada al aula."

# ---------------------------------------------------------------------- perfil del equipo (MOD-009)

COMPARTIDO, ASIGNADO = "compartido", "asignado"     # los mismos valores de `device_manager.dominio.dispositivo` (lo comprueba una prueba)

# ------------------------------------------------------------------ la práctica (D-5, D-6, BR-055)

MODO_ESTUDIO = "estudio"     # la única `modo` que admite `m08_practica`: la tabla no puede contener intentos formales
TERMINADA = "terminada"
ESTADOS_PRACTICA = (EN_CURSO, TERMINADA)
DIRECTO, COLA = "directo", "cola"   # cómo llegó lo último: en línea o desde la cola del aparato
ORIGENES = (DIRECTO, COLA)

# ------------------------------------------------------------------- trabajo sin red (D-10, D-11)

INTEGRADO, DUPLICADO, RECHAZADO, PENDIENTE_DECISION = "integrado", "duplicado", "rechazado", "pendiente_decision"
ESTADOS_RESULTADO = (INTEGRADO, DUPLICADO, RECHAZADO, PENDIENTE_DECISION)   # lo que se responde por cada evento
ESTADOS_LIBRO = (INTEGRADO, RECHAZADO, PENDIENTE_DECISION)                  # lo que queda en `m08_sincronizacion` (duplicado no se guarda)
# El estado que ve la cola del aparato (`pending` es de la propia cola).
ESTADO_EN_APARATO = {INTEGRADO: "synced", RECHAZADO: "rejected", PENDIENTE_DECISION: "conflict"}

T_BLOQUE_VISTO, T_RESPUESTA_ENVIADA, T_PRACTICA_TERMINADA, T_LECCION_COMPLETADA = (
    "study.block.viewed", "study.answer.submitted", "study.practice.finished", "study.lesson.completed")
TIPOS_EVENTO = (T_BLOQUE_VISTO, T_RESPUESTA_ENVIADA, T_PRACTICA_TERMINADA, T_LECCION_COMPLETADA)
MAX_EVENTOS_POR_ENVIO = 200

# Por qué se rechaza (o espera) un evento: es `motivo` del resultado. Los códigos de error del módulo también valen como motivo.
MOTIVO_EVENTO_INVALIDO = "evento_invalido"
MOTIVO_PLAZO_VENCIDO = "plazo_vencido"                  # plazo endurecido: se capturó después de la fecha límite
MOTIVO_ASIGNACION_CERRADA = "asignacion_cerrada"
MOTIVO_FUERA_DE_GRACIA = "fuera_de_gracia"              # capturado a tiempo pero recibido después de la gracia: decide el profesor (BR-074)
MOTIVO_ACEPTADO_POR_DOCENTE = "aceptado_por_docente"
MOTIVO_DESCARTADO_POR_DOCENTE = "descartado_por_docente"

DECISION_ACEPTAR, DECISION_DESCARTAR = "aceptar", "descartar"
DECISIONES = (DECISION_ACEPTAR, DECISION_DESCARTAR)

# ----------------------------------------------------------------------- estado de la sesión de estudio
# `motivo` de `GET /estado/` y de `GET /estudiantes/` (§4.1): por qué el modo de estudio no está disponible en este aparato. Desde D-15
# sirve en CUALQUIER tableta registrada, activa y no bloqueada (compartida o asignada): ya no hay motivos de perfil.

MOTIVO_NODO_NO_INSTALADO = "nodo_no_instalado"
MOTIVO_DISPOSITIVO_DESCONOCIDO = "dispositivo_desconocido"
MOTIVO_DISPOSITIVO_BLOQUEADO = "dispositivo_bloqueado"
MOTIVO_DISPOSITIVO_INACTIVO = "dispositivo_inactivo"
MOTIVO_ALUMNO_DESCONOCIDO = "alumno_desconocido"   # `motivo` de un 403 `sin_permiso`: el `alumno_id` declarado no existe o está inactivo (D-15)

LIMPIEZA_COMPLETA, LIMPIEZA_PENDIENTE = "completa", "pendiente"
LIMPIEZAS = (LIMPIEZA_COMPLETA, LIMPIEZA_PENDIENTE)

# ------------------------------------------------------------------------------------------ eventos
# Los eventos `estudio.*.v1` del outbox `m08_evento_salida` (§2.6). Los tres últimos son propios del proyecto (CAP-050, CAP-051 y el
# fin de una práctica). `evaluacion.respuesta_registrada.v1` es de MOD-010 en el Maestro: mientras no exista, se publica desde aquí con
# `modo = "estudio"` y sin el contenido de la respuesta (BR-127).

EV_SESION_ABIERTA = "estudio.sesion.abierta.v1"                 # FUN-080
EV_SESION_CERRADA = "estudio.sesion.cerrada.v1"                 # FUN-089
EV_LECCION_ABIERTA = "estudio.leccion.abierta.v1"               # FUN-082
EV_LECCION_COMPLETADA = "estudio.leccion.completada.v1"         # FUN-087
EV_ACTIVIDAD_REANUDADA = "estudio.actividad.reanudada.v1"       # FUN-088
EV_PAQUETE_DESCARGADO = "estudio.paquete.descargado.v1"         # FUN-084
EV_DESCARGA_DENEGADA = "estudio.descarga.denegada.v1"           # FUN-085
EV_TRABAJO_INTEGRADO = "estudio.trabajo.integrado.v1"           # FUN-086
EV_LIMPIEZA_REINTENTADA = "estudio.limpieza.reintentada.v1"     # FUN-090
EV_RESPUESTA_REGISTRADA = "evaluacion.respuesta_registrada.v1"  # FUN-083
EV_ASIGNACION_CREADA = "estudio.asignacion.creada.v1"           # CAP-050
EV_ASIGNACION_CERRADA = "estudio.asignacion.cerrada.v1"         # CAP-051
EV_PRACTICA_TERMINADA = "estudio.practica.terminada.v1"
EVENTOS = (EV_SESION_ABIERTA, EV_SESION_CERRADA, EV_LECCION_ABIERTA, EV_LECCION_COMPLETADA, EV_ACTIVIDAD_REANUDADA,
           EV_PAQUETE_DESCARGADO, EV_DESCARGA_DENEGADA, EV_TRABAJO_INTEGRADO, EV_LIMPIEZA_REINTENTADA, EV_RESPUESTA_REGISTRADA,
           EV_ASIGNACION_CREADA, EV_ASIGNACION_CERRADA, EV_PRACTICA_TERMINADA)

# -------------------------------------------------------------------------------------------- permisos
# Sección J de MOD-008. Los seis primeros son del alumno sobre lo suyo (SELF, sólo el rol STUDENT). Los dos últimos son del proyecto
# (el Maestro no da permiso a CAP-050/051): el profesor sobre sus grupos y la administración. Los siembra MOD-001.

P_OPEN, P_ASSIGNMENT_READ, P_LESSON_OPEN, P_LESSON_COMPLETE, P_ANSWER_SUBMIT, P_PACKAGE_DOWNLOAD = (
    "study.open", "study.assignment.read", "study.lesson.open", "study.lesson.complete", "study.answer.submit", "study.package.download")
P_ASSIGNMENT_CREATE, P_ASSIGNMENT_REVIEW = "study.assignment.create", "study.assignment.review"
PERMISOS_DEL_ALUMNO = (P_OPEN, P_ASSIGNMENT_READ, P_LESSON_OPEN, P_LESSON_COMPLETE, P_ANSWER_SUBMIT, P_PACKAGE_DOWNLOAD)
PERMISOS_DEL_DOCENTE = (P_ASSIGNMENT_CREATE, P_ASSIGNMENT_REVIEW)
PERMISOS = PERMISOS_DEL_ALUMNO + PERMISOS_DEL_DOCENTE
