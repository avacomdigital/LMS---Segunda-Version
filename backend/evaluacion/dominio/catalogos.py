"""
Catálogos cerrados de MOD-010 · Evaluation & Delivery Engine: tipos, alcances, plazos, niveles de control, estados de la asignación y del
intento, catálogo de incidentes, eventos del outbox `evaluacion.*.v1`, permisos `assessment.*` y los textos que el alumno debe leer. Son
VALORES del dominio, no tablas. Ningún archivo de esta carpeta importa Django.

Lo que el módulo NO conoce, y no es un olvido (regla de oro, artículo 14): el examen (sus preguntas, sus claves, su rúbrica). El curso vive
en AVACOM Biblioteca; aquí sólo hay referencias (`*_ref`), la versión congelada, rótulos de evidencia y lo que el alumno hizo.
"""
from __future__ import annotations

from dataclasses import dataclass

# ------------------------------------------------------------------------------ la asignación (ENT-011)

EXAMEN, ACTIVIDAD = "examen", "actividad"
TIPOS = (EXAMEN, ACTIVIDAD)
TIPOS_QUE_ACEPTA_LA_API = (EXAMEN,)       # D-3: la actividad en clase sigue en m07_intento y la de estudio en m08_practica (Q-76)

GRUPO, SELECCION = "grupo", "seleccion"
ALCANCES = (GRUPO, SELECCION)             # `grupo`: todos los alumnos activos, también los que entren después

# DEC-014 · DEC-019. `blando` (por defecto): la fecha límite marca, no cierra. `endurecido`: la asignación cierra al vencer.
BLANDO, ENDURECIDO = "blando", "endurecido"
PLAZOS = (BLANDO, ENDURECIDO)
GRACIA_MS_POR_DEFECTO = 15 * 60 * 1000    # DEC-019
ARCHIVO_TRAS_MS = 24 * 60 * 60 * 1000     # cerrada → archivada a las veinticuatro horas

# Tiempo del intento (§7.2 del modelo): lo que dice la biblioteca, el que fija el profesor, o sin cronómetro.
TIEMPO_BIBLIOTECA, TIEMPO_FIJO, SIN_LIMITE = "biblioteca", "fijo", "sin_limite"
MODOS_TIEMPO = (TIEMPO_BIBLIOTECA, TIEMPO_FIJO, SIN_LIMITE)

# Quién reactiva a un alumno suspendido (PAN-061). `profesor` es la regla del Guion; `automatica` es para actividades sin riesgo.
REACTIVA_PROFESOR, REACTIVA_AUTOMATICA = "profesor", "automatica"
REACTIVACIONES = (REACTIVA_PROFESOR, REACTIVA_AUTOMATICA)

# Cuándo ve el alumno su resultado (`showResults` del examen: never · after_submit · after_teacher_release).
NUNCA, AL_ENTREGAR, TRAS_LIBERAR = "nunca", "al_entregar", "tras_liberar"
RESULTADOS = (NUNCA, AL_ENTREGAR, TRAS_LIBERAR)
RESULTADOS_DE_LA_BIBLIOTECA = {"never": NUNCA, "after_submit": AL_ENTREGAR, "after_teacher_release": TRAS_LIBERAR}

# Los seis estados de la asignación (sección H del Maestro).
BORRADOR, PROGRAMADA, ACTIVA, ACTIVA_FUERA_DE_PLAZO, CERRADA, ARCHIVADA = (
    "borrador", "programada", "activa", "activa_fuera_de_plazo", "cerrada", "archivada")
ESTADOS_ASIGNACION = (BORRADOR, PROGRAMADA, ACTIVA, ACTIVA_FUERA_DE_PLAZO, CERRADA, ARCHIVADA)
ABIERTAS = (ACTIVA, ACTIVA_FUERA_DE_PLAZO)        # reciben intentos y respuestas
CON_CIERRE = (CERRADA, ARCHIVADA)

# ------------------------------------------------------------------- niveles de control (DEC-009, CAP-063)
# De menos a más control. Una tableta ALCANZA el nivel si el rango de su capacidad no es menor que el del nivel.

ABIERTO, SUPERVISADO, CONTROLADO = "abierto", "supervisado", "controlado"
NIVELES = (ABIERTO, SUPERVISADO, CONTROLADO)
RANGO_NIVEL = {ABIERTO: 0, SUPERVISADO: 1, CONTROLADO: 2}

# -------------------------------------------------------------------------------- el intento (ENT-012)
# Los nueve estados del Maestro. `restaurando` y `pausado_desconexion` son los dos «suspendidos».

NO_INICIADO, EN_CURSO, PAUSADO, RESTAURANDO, EN_CURSO_FUERA_DE_PLAZO, ENTREGADO, EN_REVISION, CALIFICADO, ANULADO = (
    "no_iniciado", "en_curso", "pausado_desconexion", "restaurando", "en_curso_fuera_de_plazo",
    "entregado", "en_revision_docente", "calificado", "anulado")
ESTADOS_INTENTO = (NO_INICIADO, EN_CURSO, PAUSADO, RESTAURANDO, EN_CURSO_FUERA_DE_PLAZO, ENTREGADO, EN_REVISION, CALIFICADO, ANULADO)
VIVOS = (NO_INICIADO, EN_CURSO, PAUSADO, RESTAURANDO, EN_CURSO_FUERA_DE_PLAZO)   # a lo sumo uno por alumno y asignación
CORRIENDO = (EN_CURSO, EN_CURSO_FUERA_DE_PLAZO)                                  # el reloj sólo corre en estos dos
SUSPENDIDOS = (PAUSADO, RESTAURANDO)                                             # esperan reactivación
ACEPTAN_RESPUESTAS = (EN_CURSO, EN_CURSO_FUERA_DE_PLAZO, PAUSADO, RESTAURANDO)   # BR-071: lo capturado antes de la pausa llega después
ENTREGADOS = (ENTREGADO, EN_REVISION, CALIFICADO)                                # con `entregado_en`
ANULABLES = ENTREGADOS                                                           # el diagrama no tiene `en_curso → anulado`
ABIERTOS_PARA_EL_NODO = (EN_CURSO, EN_CURSO_FUERA_DE_PLAZO, PAUSADO)             # los que pasan a `restaurando` al arrancar el nodo

SISTEMA = "sistema"            # el actor de lo que hace el nodo; INV-018: jamás anula

# Cómo terminó el intento.
O_ALUMNO, O_TIEMPO, O_PLAZO, O_PROFESOR, O_CIERRE = "alumno", "tiempo", "plazo", "profesor", "cierre"
ORIGENES_ENTREGA = (O_ALUMNO, O_TIEMPO, O_PLAZO, O_PROFESOR, O_CIERRE)

# Lo que llegó fuera de la ventana de gracia (BR-074): nunca se descarta en silencio.
TARDIO_PENDIENTE, TARDIO_ACEPTADO, TARDIO_DESCARTADO = "pendiente_decision", "aceptado", "descartado"
ESTADOS_TARDIO = ("", TARDIO_PENDIENTE, TARDIO_ACEPTADO, TARDIO_DESCARTADO)
DECISION_ACEPTAR, DECISION_DESCARTAR = "aceptar", "descartar"
DECISIONES_ENVIO = (DECISION_ACEPTAR, DECISION_DESCARTAR)

# Cómo llegó una respuesta: en línea o desde la cola de la tableta.
DIRECTO, COLA = "directo", "cola"
ORIGENES_RESPUESTA = (DIRECTO, COLA)

# Causas de una pausa (`pausas[].causa`).
C_SIN_LATIDO, C_REINICIO_NODO, C_MANUAL = "sin_latido", "reinicio_nodo", "manual"
CAUSAS_PAUSA = (C_SIN_LATIDO, C_REINICIO_NODO, C_MANUAL)

# ---------------------------------------------------------------------------- admisión (BR-075, BR-076)

EN_ESPERA, ADMITIDO, RECHAZADO = "en_espera", "admitido", "rechazado"
ESTADOS_ADMISION = (EN_ESPERA, ADMITIDO, RECHAZADO)
DECISION_ADMITIR, DECISION_RECHAZAR = "admitir", "rechazar"
DECISIONES_ADMISION = (DECISION_ADMITIR, DECISION_RECHAZAR)

# El bloqueo que la tableta informa haber aplicado (D-12).
B_APLICADO, B_PARCIAL, B_FALLIDO, B_LIBERADO = "aplicado", "parcial", "fallido", "liberado"
RESULTADOS_BLOQUEO = (B_APLICADO, B_PARCIAL, B_FALLIDO, B_LIBERADO)
CAPAS_BLOQUEO = ("sistema", "app", "capturas", "pantallas")

# ------------------------------------------------------------------------------------------- incidentes
# FUN-117, CAP-066, BR-077. Un incidente NUNCA cambia el estado del intento. El catálogo es cerrado: una tableta sólo puede informar los de
# origen `tableta`; el nodo y el profesor generan los suyos. Severidad: `informativa` · `atencion` · `alta`.

S_INFORMATIVA, S_ATENCION, S_ALTA = "informativa", "atencion", "alta"
SEVERIDADES = (S_INFORMATIVA, S_ATENCION, S_ALTA)
RANGO_SEVERIDAD = {S_INFORMATIVA: 0, S_ATENCION: 1, S_ALTA: 2}

O_TABLETA, O_NODO, O_DOCENTE = "tableta", "nodo", "profesor"
ORIGENES_INCIDENTE = (O_TABLETA, O_NODO, O_DOCENTE)
RESOLUCION_REGISTRADO = "registrado"      # lo único que el sistema hace con un incidente


@dataclass(frozen=True)
class TipoIncidente:
    clave: str
    origen: str
    severidad: str
    etiqueta: str


def _t(clave: str, origen: str, severidad: str, etiqueta: str) -> TipoIncidente:
    return TipoIncidente(clave, origen, severidad, etiqueta)


_INCIDENTES: tuple[TipoIncidente, ...] = (
    _t("salida_de_app", O_TABLETA, S_INFORMATIVA, "Salió de la aplicación"),
    _t("regreso_a_app", O_TABLETA, S_INFORMATIVA, "Volvió a la aplicación"),
    _t("cierre_bloqueado", O_TABLETA, S_INFORMATIVA, "Intentó cerrar la aplicación"),
    _t("tecla_bloqueada", O_TABLETA, S_INFORMATIVA, "Pulsó una tecla bloqueada"),
    _t("pantalla_adicional", O_TABLETA, S_ATENCION, "Hay una pantalla adicional"),
    _t("bloqueo_parcial", O_TABLETA, S_ATENCION, "El bloqueo se aplicó a medias"),
    _t("bloqueo_fallido", O_TABLETA, S_ALTA, "El bloqueo no se pudo aplicar"),
    _t("bloqueo_liberado", O_TABLETA, S_ALTA, "El bloqueo se soltó durante el examen"),
    _t("consulta_recurso", O_TABLETA, S_INFORMATIVA, "Consultó un recurso habilitado"),
    _t("desconexion", O_NODO, S_ATENCION, "Se perdió la señal de la tableta"),
    _t("reconexion", O_NODO, S_INFORMATIVA, "La tableta volvió a dar señal"),
    _t("reinicio_nodo", O_NODO, S_INFORMATIVA, "El equipo del aula se reinició"),
    _t("cambio_de_dispositivo", O_NODO, S_ATENCION, "Continuó desde otra tableta"),
    _t("respuesta_tardia", O_NODO, S_INFORMATIVA, "Llegaron respuestas de una sesión superada o de una pausa"),
    _t("reloj_desfasado", O_NODO, S_ATENCION, "El reloj de la tableta está desfasado"),
    _t("tiempo_agotado", O_NODO, S_INFORMATIVA, "Se agotó el tiempo"),
    _t("entrega_automatica", O_NODO, S_INFORMATIVA, "El plazo venció y el nodo entregó"),
    _t("reactivado", O_DOCENTE, S_INFORMATIVA, "El profesor lo reactivó"),
    _t("degradacion", O_DOCENTE, S_INFORMATIVA, "El profesor bajó el nivel de control"),
    _t("admitido_bajo_nivel", O_DOCENTE, S_INFORMATIVA, "El profesor admitió la tableta por debajo del nivel"),
)
INCIDENTES: dict[str, TipoIncidente] = {t.clave: t for t in _INCIDENTES}
INCIDENTES_DE_LA_TABLETA = tuple(t.clave for t in _INCIDENTES if t.origen == O_TABLETA)
BLOQUEO_PARCIAL, BLOQUEO_FALLIDO, BLOQUEO_LIBERADO = "bloqueo_parcial", "bloqueo_fallido", "bloqueo_liberado"

# ---------------------------------------------------------------------------- textos obligatorios
# La última columna de la tabla de niveles del Guion (JRN-010): el alumno sabe SIEMPRE bajo qué condiciones presenta. Es obligatorio.

CONDICIONES: dict[str, dict] = {
    CONTROLADO: {
        "titulo": "Examen controlado",
        "texto": "Durante este examen tu tableta solo muestra el examen. Si sales, tu profesor lo verá, y tus respuestas se guardan igual.",
        "sistema": "El dispositivo queda dedicado al examen. Salir de la aplicación se registra como incidente informativo.",
        "profesor": "Estado por alumno e incidentes conforme ocurren, sin sonido ni alarma.",
        "registra": ["Salidas de la aplicación", "Tus respuestas y el tiempo que tomaste"],
    },
    SUPERVISADO: {
        "titulo": "Examen supervisado",
        "texto": "Puedes consultar los materiales que tu profesor dejó disponibles. Quedará registrado qué consultaste.",
        "sistema": "El alumno puede consultar los recursos que el profesor habilitó. Las consultas quedan registradas.",
        "profesor": "Qué recursos consultó cada alumno y cuánto tiempo.",
        "registra": ["Los materiales que consultas", "Salidas de la aplicación", "Tus respuestas y el tiempo que tomaste"],
    },
    ABIERTO: {
        "titulo": "Examen abierto",
        "texto": "Este examen es de consulta libre. Solo se registra tu respuesta y el tiempo que tomaste.",
        "sistema": "Sin restricción de uso del dispositivo. Solo se registran entrega y tiempo.",
        "profesor": "Avance y entregas, sin registro de conducta.",
        "registra": ["Tus respuestas y el tiempo que tomaste"],
    },
}

# MSG-033 (alumno suspendido), MSG-036 (tabletas que no alcanzan) y lo que sigue a una entrega (PAN-123).
MENSAJE_SUSPENDIDO = ("Todo lo que respondiste está guardado y el tiempo está detenido. Tu examen queda en pausa. "
                      "Avisa a tu profesor para continuar.")
MENSAJE_EN_ESPERA = "Tu tableta no alcanza el nivel de control de este examen. Tu profesor debe decidir cómo continuar."
MENSAJE_RECHAZADA = "Tu profesor no admitió esta tableta para el examen. Pídele que te indique cómo continuar."
QUE_SIGUE = {
    "resultado_al_liberar": "Tu examen quedó entregado. Tu profesor publicará los resultados.",
    "en_revision": "Tu examen quedó entregado. Algunas respuestas las revisa tu profesor.",
    "sin_resultado": "Tu examen quedó entregado.",
}

# ------------------------------------------------------------------------------------------ eventos
# Los eventos `evaluacion.*.v1` del outbox `m10_evento_salida`. Los catorce primeros son del Maestro (sección L); `evaluacion.creada.v1` y
# `evaluacion.reactivo.anadido.v1` NO se publican aquí: FUN-103 y FUN-104 se trasladaron a la biblioteca (D-2). Los demás son del proyecto.

EV_ASIGNADA = "evaluacion.asignada.v1"
EV_AUTOCALIFICACION = "evaluacion.autocalificacion.completada.v1"
EV_ADMITIDO_BAJO_NIVEL = "evaluacion.dispositivo_admitido_bajo_nivel.v1"
EV_PLAZO_CONFIGURADO = "evaluacion.fecha_limite.configurada.v1"
EV_PLAZO_ENDURECIDO = "evaluacion.fecha_limite.endurecida.v1"
EV_INCIDENTE = "evaluacion.incidente_registrado.v1"
EV_INTENTO_ABIERTO = "evaluacion.intento_abierto.v1"
EV_INTENTO_ENTREGADO = "evaluacion.intento_entregado.v1"
EV_INTENTO_FUERA_DE_PLAZO = "evaluacion.intento_fuera_de_plazo.v1"
EV_NIVEL_DEFINIDO = "evaluacion.nivel_examen.definido.v1"
EV_NIVEL_DEGRADADO = "evaluacion.nivel_examen_degradado.v1"
EV_RESPUESTA_DEDUPLICADA = "evaluacion.respuesta_deduplicada.v1"
EV_RESPUESTA_REGISTRADA = "evaluacion.respuesta_registrada.v1"
EV_REVISION_SOLICITADA = "evaluacion.revision.solicitada.v1"
EVENTOS_DEL_MAESTRO = (EV_ASIGNADA, EV_AUTOCALIFICACION, EV_ADMITIDO_BAJO_NIVEL, EV_PLAZO_CONFIGURADO, EV_PLAZO_ENDURECIDO, EV_INCIDENTE,
                       EV_INTENTO_ABIERTO, EV_INTENTO_ENTREGADO, EV_INTENTO_FUERA_DE_PLAZO, EV_NIVEL_DEFINIDO, EV_NIVEL_DEGRADADO,
                       EV_RESPUESTA_DEDUPLICADA, EV_RESPUESTA_REGISTRADA, EV_REVISION_SOLICITADA)
NO_SE_PUBLICAN_AQUI = ("evaluacion.creada.v1", "evaluacion.reactivo.anadido.v1")

EV_INTENTO_PAUSADO = "evaluacion.intento_pausado.v1"
EV_INTENTO_REACTIVADO = "evaluacion.intento_reactivado.v1"
EV_INTENTO_RESTAURADO = "evaluacion.intento_restaurado.v1"
EV_INTENTO_ANULADO = "evaluacion.intento_anulado.v1"
EV_INTENTO_CALIFICADO = "evaluacion.intento_calificado.v1"
EV_REVISION_PUBLICADA = "evaluacion.revision_publicada.v1"
EV_ADMISION_SOLICITADA = "evaluacion.admision_solicitada.v1"
EV_ENVIO_TARDIO_PENDIENTE = "evaluacion.envio_tardio_pendiente.v1"
EV_ENVIO_TARDIO_DECIDIDO = "evaluacion.envio_tardio_decidido.v1"
EV_ASIGNACION_CERRADA = "evaluacion.asignacion_cerrada.v1"
EV_RESULTADOS_LIBERADOS = "evaluacion.resultados_liberados.v1"
EVENTOS_PROPIOS = (EV_INTENTO_PAUSADO, EV_INTENTO_REACTIVADO, EV_INTENTO_RESTAURADO, EV_INTENTO_ANULADO, EV_INTENTO_CALIFICADO,
                   EV_REVISION_PUBLICADA, EV_ADMISION_SOLICITADA, EV_ENVIO_TARDIO_PENDIENTE, EV_ENVIO_TARDIO_DECIDIDO,
                   EV_ASIGNACION_CERRADA, EV_RESULTADOS_LIBERADOS)
EVENTOS = EVENTOS_DEL_MAESTRO + EVENTOS_PROPIOS

# ------------------------------------------------------------------------------- auditoría (MOD-019)
# Acciones del catálogo cerrado de `audit.dominio.catalogos`. Las tres primeras ya estaban reservadas para este módulo.

A_INTENTO_ABIERTO, A_INTENTO_ENTREGADO, A_INTENTO_ANULADO = "evaluacion.iniciada", "evaluacion.enviada", "evaluacion.anulada"
A_PUNTAJE_MODIFICADO = "calificacion.modificada"
A_NIVEL_EXCEPCION = "aula.nivel.excepcion"

# -------------------------------------------------------------------------------------------- permisos
# Sección J de MOD-010 (los 11 del Maestro) más cinco del proyecto. Los siembra MOD-001 (`acceso.dominio.plantillas`, migración 0009).
# `assessment.create` y `assessment.item.create` existen en el catálogo pero no tienen ruta: FUN-103/104 son de la biblioteca (D-2).

P_CREATE, P_ITEM_CREATE = "assessment.create", "assessment.item.create"
P_EXAM_MODE_SET, P_DEADLINE_SET, P_DEADLINE_ENFORCE, P_ASSIGN = (
    "assessment.exam_mode.set", "assessment.deadline.set", "assessment.deadline.enforce", "assessment.assign")
P_ATTEMPT_START, P_ANSWER_SUBMIT, P_ATTEMPT_SUBMIT = "assessment.attempt.start", "assessment.answer.submit", "assessment.attempt.submit"
P_OVERRIDE, P_DOWNGRADE = "assessment.exam_mode.override", "assessment.exam_mode.downgrade"
P_READ, P_REACTIVATE, P_VOID, P_REVIEW, P_RESULTS_VIEW = (
    "assessment.read", "assessment.attempt.reactivate", "assessment.attempt.void", "assessment.review", "assessment.results.view")
PERMISOS_DEL_ALUMNO = (P_ATTEMPT_START, P_ANSWER_SUBMIT, P_ATTEMPT_SUBMIT)
PERMISOS_DEL_MAESTRO = (P_CREATE, P_ITEM_CREATE, P_EXAM_MODE_SET, P_DEADLINE_SET, P_DEADLINE_ENFORCE, P_ASSIGN, P_ATTEMPT_START,
                        P_ANSWER_SUBMIT, P_ATTEMPT_SUBMIT, P_OVERRIDE, P_DOWNGRADE)
PERMISOS_DEL_DOCENTE = (P_EXAM_MODE_SET, P_DEADLINE_SET, P_DEADLINE_ENFORCE, P_ASSIGN, P_OVERRIDE, P_DOWNGRADE, P_READ, P_REACTIVATE,
                        P_VOID, P_REVIEW, P_RESULTS_VIEW)
PERMISOS = PERMISOS_DEL_ALUMNO + PERMISOS_DEL_DOCENTE
