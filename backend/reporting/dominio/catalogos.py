"""
Catálogos cerrados de MOD-013 · Reporting: permisos, tipos de reporte, fuentes y los eventos que consume, estados de la proyección, motivos de integración, eventos que
publica, acciones de auditoría, formatos y destinos de exportación, y los topes. Son VALORES del dominio, no tablas. Ningún archivo de esta carpeta importa Django.

Lo que el módulo NO conoce, y no es un olvido (artículo 14): ningún título de curso, lección o pregunta. Sólo referencias (`curso_ref`, `leccion_ref`); el rótulo con que
el módulo dueño lo registró se pide en el momento de mostrar.
"""
from __future__ import annotations

# ------------------------------------------------------------------------------------------------ permisos (sección J del Maestro)

P_VIEW = "reports.view"                  # FUN-143 · el reporte de una clase y los filtros
P_GROUP = "reports.group.view"           # FUN-139
P_STUDENT = "reports.student.view"       # FUN-140 (ya existía en MOD-001)
P_USAGE = "reports.usage.view"           # FUN-142
P_CURRICULUM = "reports.curriculum.view"  # FUN-141 · RESERVADO (V1): la cobertura necesita el currículo congelado de MOD-003
P_EXPORT = "reports.export"              # FUN-146
P_REBUILD = "reports.rebuild"            # FUN-147
P_SETTINGS = "reports.settings.manage"   # EXTENSIÓN TÉCNICA PROPUESTA: umbral de privacidad y política de exportación (el Maestro no da función a esto)
PERMISOS = (P_VIEW, P_GROUP, P_STUDENT, P_USAGE, P_CURRICULUM, P_EXPORT, P_REBUILD, P_SETTINGS)
PERMISOS_DE_LECTURA_ACADEMICA = (P_VIEW, P_GROUP, P_STUDENT)    # los que dan acceso a datos de personas: el técnico no los tiene (BR-097)

# ------------------------------------------------------------------------------------------------ tipos de reporte

CLASE, ALUMNO, GRUPO, USO = "clase", "alumno", "grupo", "uso"
TIPOS = (CLASE, ALUMNO, GRUPO, USO)
COMPARACION, COBERTURA = "comparacion", "cobertura"          # reservados (V1): la ruta existe y responde 501
TIPOS_RESERVADOS = (COMPARACION, COBERTURA)
PERMISO_DE_TIPO = {CLASE: P_VIEW, ALUMNO: P_STUDENT, GRUPO: P_GROUP, USO: P_USAGE}
NOMBRE_DE_TIPO = {CLASE: "de la clase", ALUMNO: "del alumno", GRUPO: "del grupo", USO: "de uso de equipos"}

# ------------------------------------------------------------------------------------------------ fuentes y eventos que consume

AULA, EVALUACION, CALIFICACION, ESTUDIO = "aula", "evaluacion", "calificacion", "estudio"
FUENTES = (AULA, EVALUACION, CALIFICACION, ESTUDIO)

EV_AULA_FINALIZADA = "aula.sesion.finalizada.v1"
EV_AULA_INTENTO = "aula.intento.entregado.v1"
EV_AULA_PRESENCIA = "aula.presencia.registrada.v1"
EV_EST_SESION_CERRADA = "estudio.sesion.cerrada.v1"
EV_EST_INTEGRADO = "estudio.trabajo.integrado.v1"

EVENTOS_CONSUMIDOS: dict[str, tuple[str, ...]] = {
    AULA: (EV_AULA_FINALIZADA, EV_AULA_INTENTO, EV_AULA_PRESENCIA),
    EVALUACION: ("evaluacion.asignada.v1", "evaluacion.intento_abierto.v1", "evaluacion.intento_entregado.v1", "evaluacion.intento_fuera_de_plazo.v1",
                 "evaluacion.intento_calificado.v1", "evaluacion.intento_anulado.v1", "evaluacion.revision_publicada.v1", "evaluacion.envio_tardio_decidido.v1",
                 "evaluacion.asignacion_cerrada.v1"),
    CALIFICACION: ("calificacion.registrada.v1", "calificacion.manual_aplicada.v1", "calificacion.rubrica_aplicada.v1", "calificacion.intento_reabierto.v1",
                   "calificacion.ajustada.v1", "calificacion.publicada.v1", "calificacion.publicacion_retirada.v1", "calificacion.valoracion_docente.v1",
                   "calificacion.anulada.v1", "calificacion.modo_cambiado.v1", "calificacion.escala_adoptada.v1", "calificacion.estado_simple_calculado.v1"),
    ESTUDIO: ("estudio.asignacion.creada.v1", "estudio.asignacion.cerrada.v1", "estudio.leccion.completada.v1", "estudio.practica.terminada.v1",
              EV_EST_INTEGRADO, EV_EST_SESION_CERRADA),
}
# Los eventos de configuración que no nombran un grupo (cambiar la escala o el modo cambia lo que ve cada grupo del nivel): se recalcula todo.
EVENTOS_DE_ALCANCE_GLOBAL = frozenset({"calificacion.modo_cambiado.v1", "calificacion.escala_adoptada.v1"})

# Los valores que usa el aula para sus estados (vocabulario público de MOD-007; el dominio no importa su código).
SESION_CERRADA, SESION_ARCHIVADA = "cerrada", "archivada"
SESIONES_TERMINADAS = (SESION_CERRADA, SESION_ARCHIVADA)
SESIONES_ACTIVAS = ("abierta", "suspendida")
PRESENCIA_RECONECTANDO = "reconectando"
PRESENCIAS_QUE_CUENTAN = ("conectado", "reconectando", "salio", "expulsado")      # quien entró de verdad (no el que esperaba ni el rechazado)
INTENTO_ENTREGADO, INTENTO_EN_CURSO, INTENTO_PENDIENTE = "entregado", "en_curso", "pendiente_decision"
ASIGNACION_BORRADOR = "borrador"
ASIGNACIONES_CERRADAS = ("cerrada", "archivada", "activa_fuera_de_plazo")           # donde quien no presentó ya «no presentó»
INTENTO_ANULADO_O_NO_INICIADO = ("anulado", "no_iniciado")

# ------------------------------------------------------------------------------------------------ estado de la proyección (H del Maestro)

AL_DIA, RECONSTRUYENDOSE, REZAGADA = "al_dia", "reconstruyendose", "rezagada"
ESTADOS_DE_PROYECCION = (AL_DIA, RECONSTRUYENDOSE, REZAGADA)     # sólo `reconstruyendose` se guarda; `rezagada` se deriva (hay eventos relevantes sin aplicar)

# ------------------------------------------------------------------------------------------------ integración de los equipos (BR-083)

CONEXION_PERDIDA = "conexion_perdida"    # un participante que quedó «reconectando»: su tableta guarda lo que responde y lo enviará al volver
ENTREGA_PENDIENTE = "entrega_pendiente"  # un intento de una actividad de clase que sigue abierto o pendiente de decisión
COLA_DE_ESTUDIO = "cola_de_estudio"      # la tableta avisó, al cerrar su sesión de estudio, de que le quedaba trabajo por enviar
MOTIVOS_DE_INTEGRACION = (CONEXION_PERDIDA, ENTREGA_PENDIENTE, COLA_DE_ESTUDIO)
GRACIA_DE_INTEGRACION_MS = 15 * 60 * 1000    # tras cerrar la clase el nodo aún acepta lo que sale de la cola de una tableta (DEC-019): pasado ese plazo ya no espera nada

# ------------------------------------------------------------------------------------------------ «necesita atención» (criterios PROPUESTOS, no institucionales)

MOT_POCAS_CLASES, MOT_POCAS_ENTREGAS, MOT_EVALUACIONES, MOT_ESTUDIO = "pocas_clases", "pocas_entregas", "evaluaciones_sin_presentar", "estudio_vencido"
MOTIVOS_DE_ATENCION = (MOT_EVALUACIONES, MOT_POCAS_ENTREGAS, MOT_POCAS_CLASES, MOT_ESTUDIO)       # de más a menos urgente
MIN_CLASES_PARA_JUZGAR = 2        # con menos de dos clases cerradas no se juzga la asistencia
MIN_ACTIVIDADES_PARA_JUZGAR = 3   # con menos de tres actividades recibidas no se juzga la entrega
UMBRAL_DE_ASISTENCIA_PCT = 50
UMBRAL_DE_ENTREGA_PCT = 50

# ------------------------------------------------------------------------------------------------ privacidad (BR-086)

MINIMO_DE_ALUMNOS = 5

# ------------------------------------------------------------------------------------------------ exportación (FUN-146)

XLSX, CSV = "xlsx", "csv"
FORMATOS = (XLSX, CSV)
EXTENSION_DE = {XLSX: "xlsx", CSV: "csv"}
TIPO_MIME = {XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", CSV: "text/csv; charset=utf-8"}

EXTRAIBLE, CARPETA_LOCAL, RED = "extraible", "carpeta_local", "red"
DESTINOS = (EXTRAIBLE, CARPETA_LOCAL, RED)
ETIQUETA_DE_DESTINO = {EXTRAIBLE: "una memoria extraíble", CARPETA_LOCAL: "una carpeta de este equipo", RED: "una carpeta de red"}

EXP_AUTORIZADA, EXP_ENTREGADA, EXP_CADUCADA = "autorizada", "entregada", "caducada"      # `autorizada` = «sin confirmar»
ESTADOS_DE_EXPORTACION = (EXP_AUTORIZADA, EXP_ENTREGADA, EXP_CADUCADA)
RES_GUARDADO, RES_FALLIDO = "guardado", "fallido"
RESULTADOS = (RES_GUARDADO, RES_FALLIDO)
TTL_DE_EXPORTACION_MS = 15 * 60 * 1000       # una exportación que nadie confirma caduca a los quince minutos y no cuenta como entregada

# Por qué no se pudo guardar (el cliente clasifica el error del sistema; es un contrato con `Avacom.Lms.Core.Reporting.MotivosDeEscritura`).
MOTIVOS_DE_FALLO = ("medio_retirado", "sin_espacio", "protegido_contra_escritura", "sin_permiso", "ruta_de_red_inalcanzable", "nombre_invalido",
                    "bloqueado_por_antivirus", "archivo_en_uso", "verificacion_fallida", "cancelado", "otro")

# Para qué se exporta (lista cerrada: el nodo principal no tiene teclado). Sólo se pide si el administrador lo exige.
RAZONES_DE_EXPORTACION = {
    "entrega_a_familias": "Entrega a las familias",
    "entrega_a_coordinacion": "Entrega a coordinación o secretaría",
    "reunion_de_equipo": "Reunión del equipo docente",
    "respaldo_del_profesor": "Respaldo del propio profesor",
    "otra_gestion_escolar": "Otra gestión escolar",
}

# ------------------------------------------------------------------------------------------------ eventos que publica (versionados)

EV_GRUPO_GENERADO = "reporte.grupo_generado.v1"
EV_ALUMNO_GENERADO = "reporte.alumno_generado.v1"
EV_USO_GENERADO = "reporte.uso_generado.v1"
EV_COBERTURA_GENERADO = "reporte.cobertura_generado.v1"      # RESERVADO: se declara y no se emite (V1)
EV_AGREGADOS_ACTUALIZADOS = "reporte.agregados_actualizados.v1"
EV_AGREGADOS_RECONSTRUIDOS = "reporte.agregados_reconstruidos.v1"
EV_MARCADO_INCOMPLETO = "reporte.marcado_incompleto.v1"
EV_EXPORTADO = "reporte.exportado.v1"
EVENTOS = (EV_GRUPO_GENERADO, EV_ALUMNO_GENERADO, EV_USO_GENERADO, EV_COBERTURA_GENERADO, EV_AGREGADOS_ACTUALIZADOS, EV_AGREGADOS_RECONSTRUIDOS,
           EV_MARCADO_INCOMPLETO, EV_EXPORTADO)
EVENTOS_RESERVADOS = (EV_COBERTURA_GENERADO,)
EVENTO_DE_TIPO = {GRUPO: EV_GRUPO_GENERADO, ALUMNO: EV_ALUMNO_GENERADO, USO: EV_USO_GENERADO}      # la clase no tiene función propia en el Maestro: no emite

# ------------------------------------------------------------------------------------------------ acciones de auditoría (catálogo de MOD-019)

SISTEMA = "sistema"
A_GENERADO = "reporte.generado"                                  # un reporte NOMINAL se generó (quién, cuál, alcance, filas)
A_EXPORT_AUTORIZADA = "reporte.exportacion_autorizada"
A_EXPORTADO = "reporte.exportado"
A_EXPORT_FALLIDA = "reporte.exportacion_fallida"
A_EXPORT_CADUCADA = "reporte.exportacion_caducada"
A_ACCESO_DENEGADO = "reporte.acceso_denegado"                   # TST-069: quien no puede leer datos académicos y lo intentó
A_RECONSTRUIDO = "reporte.agregados_reconstruidos"
A_CONFIGURACION = "reporte.configuracion_cambiada"
A_EVENTO_OMITIDO = "reporte.evento_omitido"
ACCIONES_DE_AUDITORIA = (A_GENERADO, A_EXPORT_AUTORIZADA, A_EXPORTADO, A_EXPORT_FALLIDA, A_EXPORT_CADUCADA, A_ACCESO_DENEGADO, A_RECONSTRUIDO, A_CONFIGURACION,
                         A_EVENTO_OMITIDO)

# ------------------------------------------------------------------------------------------------ topes

LOTE_DE_EVENTOS = 100
MAX_FALLOS_DE_EVENTO = 5          # un evento que no se puede aplicar retiene la marca este número de ciclos y luego se deja atrás CON un asiento
MAX_CLASES_EN_LISTA = 200
MAX_RECIENTES = 10
MAX_FILAS_EXPORTABLES = 200_000   # tope duro: un reporte nunca llega a esto (un grupo tiene decenas de alumnos); evita una petición absurda
MAX_NOMBRE_DE_ARCHIVO = 100
