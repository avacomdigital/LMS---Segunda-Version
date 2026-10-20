"""
Los catálogos CERRADOS de MOD-018 · Licensing: estados, banderas, capacidades licenciables, permisos, acciones de bitácora y eventos. Una acción o un permiso que no esté
aquí no existe: `test_arquitectura.py` comprueba que cada uno esté también en el catálogo del módulo dueño (`audit/dominio/catalogos.py`, `acceso/dominio/plantillas.py`).

La lista de rutas intocables y la tabla de rutas licenciables viven en `rutas.py`.
"""
from __future__ import annotations

# ------------------------------------------------------------------------------------------------------------------- estados (P-05)
SIN_LICENCIA, ACTIVA, EN_GRACIA, DEGRADADA, REACTIVADA, LIBERACION_PENDIENTE = "sin_licencia", "activa", "en_gracia", "degradada", "reactivada", "liberacion_pendiente"
ESTADOS = (SIN_LICENCIA, ACTIVA, EN_GRACIA, DEGRADADA, REACTIVADA, LIBERACION_PENDIENTE)

# El «por qué» de un estado (para el texto que ve el administrador).
M_EVALUACION, M_EVALUACION_VENCIDA, M_VIGENTE, M_VENCIDA, M_HUELLA_DISTINTA = "evaluacion", "evaluacion_vencida", "vigente", "vencida", "huella_distinta"
M_LIBERACION_PENDIENTE, M_LIBERACION_NO_CONFIRMADA, M_AUN_NO_VIGENTE, M_REACTIVADA, M_LICENCIA_ILIMITADA = (
    "liberacion_pendiente", "liberacion_no_confirmada", "aun_no_vigente", "reactivada", "licencia_ilimitada")
MOTIVOS = (M_EVALUACION, M_EVALUACION_VENCIDA, M_VIGENTE, M_VENCIDA, M_HUELLA_DISTINTA, M_LIBERACION_PENDIENTE, M_LIBERACION_NO_CONFIRMADA, M_AUN_NO_VIGENTE, M_REACTIVADA,
           M_LICENCIA_ILIMITADA)

# Banderas ORTOGONALES: se suman al estado, no lo reemplazan.
B_RELOJ_SOSPECHOSO, B_HUELLA_PARCIAL, B_INTEGRIDAD_ALTERADA = "reloj_sospechoso", "huella_parcial", "integridad_alterada"
BANDERAS = (B_RELOJ_SOSPECHOSO, B_HUELLA_PARCIAL, B_INTEGRIDAD_ALTERADA)

# ------------------------------------------------------------------------------------------------------------------- capacidades (P-07)
# SÓLO lo que se puede degradar. Todo lo demás (login y sesión, aula en curso y readmisión, evaluación, modo estudio, LECTURA del expediente y de las calificaciones, bitácora,
# latido de equipos, /health/, la propia licencia, respaldo, restauración y actualización) es NÚCLEO: ninguna licencia lo toca (R-01, R-03). Qué módulos son núcleo y cuáles
# licenciables es una propuesta pendiente del CTO (Q-L1).
CAP_REPORTES, CAP_BUSQUEDA, CAP_IMPORTACION, CAP_ADMIN_AVANZADA = "reportes", "busqueda", "importacion", "administracion_avanzada"
CAPACIDADES_LICENCIABLES = (CAP_REPORTES, CAP_BUSQUEDA, CAP_IMPORTACION, CAP_ADMIN_AVANZADA)
TODAS = "*"

ETIQUETAS_DE_CAPACIDAD = {
    CAP_REPORTES: "Reportes y exportaciones", CAP_BUSQUEDA: "Búsqueda", CAP_IMPORTACION: "Importación de padrón y usuarios",
    CAP_ADMIN_AVANZADA: "Administración avanzada (roles, políticas y escalas)",
}

# ------------------------------------------------------------------------------------------------------------------- permisos (P-15)
P_ACTIVAR, P_RENOVAR, P_LEER = "license.activate", "license.renew", "license.read"
PERMISOS = (P_ACTIVAR, P_RENOVAR, P_LEER)
# Lo que el técnico recibe además de la administración (que hereda todo permiso nuevo). El profesor, el alumno y Reportes no reciben ninguno: ven «no disponible por licencia», jamás datos de la licencia.
PERMISOS_DEL_TECNICO = (P_ACTIVAR, P_LEER)

# ------------------------------------------------------------------------------------------------------------------- auditoría (P-16)
A_ACTIVADA, A_RENOVADA, A_LIBERADA, A_SOLICITUD, A_GRACIA, A_DEGRADADA, A_REACTIVADA = (
    "licencia.activada", "licencia.renovada", "licencia.liberada", "licencia.solicitud_generada", "licencia.gracia_iniciada", "licencia.degradada", "licencia.reactivada")
A_BLOQUEO, A_RELOJ, A_INTEGRIDAD, A_FIRMA_INVALIDA = "licencia.bloqueo_aplicado", "licencia.reloj_sospechoso", "licencia.integridad_alterada", "licencia.firma_invalida"
# Extensiones propuestas (no son del Maestro; se marcan como tales en el diseño).
A_EVALUACION, A_RELOJ_CONFIRMADO = "licencia.evaluacion_iniciada", "licencia.reloj_confirmado"
ACCIONES_DE_AUDITORIA = (A_ACTIVADA, A_RENOVADA, A_LIBERADA, A_SOLICITUD, A_GRACIA, A_DEGRADADA, A_REACTIVADA, A_BLOQUEO, A_RELOJ, A_INTEGRIDAD, A_FIRMA_INVALIDA,
                         A_EVALUACION, A_RELOJ_CONFIRMADO)
EXTENSIONES_DE_AUDITORIA = (A_EVALUACION, A_RELOJ_CONFIRMADO)

# ------------------------------------------------------------------------------------------------------------------- eventos de salida (`.v1`)
EV_ACTIVADA, EV_VALIDADA, EV_CONSUMO, EV_RENOVADA, EV_GRACIA, EV_DEGRADADAS, EV_REACTIVADA = (
    "licencia.activada.v1", "licencia.validada.v1", "licencia.consumo_calculado.v1", "licencia.renovada.v1", "licencia.periodo_gracia_iniciado.v1",
    "licencia.funciones_degradadas.v1", "licencia.reactivada.v1")
EVENTOS_DEL_MAESTRO = (EV_ACTIVADA, EV_VALIDADA, EV_CONSUMO, EV_RENOVADA, EV_GRACIA, EV_DEGRADADAS, EV_REACTIVADA)
# Extensiones propuestas.
EV_LIBERADA, EV_RELOJ, EV_INTEGRIDAD, EV_EVALUACION, EV_AVISO = (
    "licencia.liberada.v1", "licencia.reloj_sospechoso.v1", "licencia.integridad_alterada.v1", "licencia.evaluacion_iniciada.v1", "licencia.aviso_emitido.v1")
EVENTOS_EXTENDIDOS = (EV_LIBERADA, EV_RELOJ, EV_INTEGRIDAD, EV_EVALUACION, EV_AVISO)
EVENTOS = EVENTOS_DEL_MAESTRO + EVENTOS_EXTENDIDOS

# ------------------------------------------------------------------------------------------------------------------- historial de la licencia (m18_licencia)
H_ACTIVADA, H_RENOVADA, H_REACTIVADA, H_LIBERADA = "activada", "renovada", "reactivada", "liberada"
HISTORIAL = (H_ACTIVADA, H_RENOVADA, H_REACTIVADA, H_LIBERADA)

# ------------------------------------------------------------------------------------------------------------------- observaciones (m18_observacion)
# Hechos observados que EXPLICAN el estado y de los que el estado se deriva; de sólo inserción, con cifras y sin contenido.
O_HUELLA_INICIO, O_HUELLA_FIN = "huella_distinta_inicio", "huella_distinta_fin"
O_RETROCESO, O_SALTO, O_CONFIRMADO = "reloj_retroceso", "reloj_salto_adelante", "reloj_confirmado"
O_INTEGRIDAD, O_FIRMA_INVALIDA = "integridad_alterada", "firma_invalida"
OBSERVACIONES = (O_HUELLA_INICIO, O_HUELLA_FIN, O_RETROCESO, O_SALTO, O_CONFIRMADO, O_INTEGRIDAD, O_FIRMA_INVALIDA)

# La carpeta de estado (`%ProgramData%\AVACOM\OPS Master\Config\licencia\`): lo que NO se pierde al restaurar la base de datos.
ARCHIVO_ESPEJO = "actual.avlic"            # copia de la licencia vigente (FUN-194: sirve para reactivarla tras una restauración)
ARCHIVO_TUMBAS = "liberadas.json"          # las licencias que este nodo liberó: una base restaurada no las resucita
ARCHIVO_ANCLA = "ancla-reloj.json"         # marca alta del reloj e inicio de la evaluación, con su verificación
ARCHIVO_SECRETO = "instalacion.bin"        # secreto de instalación (protegido)
ARCHIVO_LLAVE_NODO = "nodo.key"            # llave Ed25519 del nodo (protegida)
# Cómo se nombran, en el asiento y la observación de integridad, los secretos propios que hubo que apartar por no poder abrirlos (nunca el nombre del archivo ni su contenido).
NOMBRES_DE_SECRETO = {ARCHIVO_SECRETO: "secreto_de_instalacion", ARCHIVO_LLAVE_NODO: "llave_del_nodo"}

# Cuánto dura en pantalla una bandera de reloj o de integridad después del hecho que la causó.
BANDERA_RELOJ_MS = 24 * 3_600_000
BANDERA_INTEGRIDAD_MS = 7 * 24 * 3_600_000
# Una misma observación de reloj no se vuelve a asentar antes de esto (un reloj torcido no llena la bitácora).
REPETICION_OBSERVACION_MS = 3_600_000

# Quien actúa cuando nadie lo hace (el programador, el arranque).
SISTEMA = "sistema"
