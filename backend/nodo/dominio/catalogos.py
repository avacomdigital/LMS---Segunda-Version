"""
Catálogos cerrados de MOD-015 · Node Platform y Cola de Salida: los estados del nodo (H del Maestro), los estados de un evento y de un consumidor, las SIETE clases de evento con su
retención y su sensibilidad, los permisos, las acciones de bitácora, los eventos `nodo.*` y los límites. Es un archivo de DATOS: no importa Django ni a ningún otro módulo.

Lo que el Maestro no fija y aquí se propone queda marcado como «(propuesta)» y aparece en las preguntas al CTO de `01-diseno.md`.
"""
from __future__ import annotations

MODULO = "nodo"                     # el nombre con que MOD-015 se registra y firma sus propios eventos
SISTEMA = "sistema"                 # el actor cuando no hay una persona ni un aparato detrás del hecho
DISPOSITIVO_NODO = "nodo"           # el «dispositivo de origen» de lo que hace el propio equipo del aula

# --------------------------------------------------------------------------------------------------------------------------- estados del nodo (H)
ARRANCANDO, OPERATIVO, RESTRINGIDO, EN_RECUPERACION, DETENIDO = "arrancando", "operativo", "restringido", "en_recuperacion", "detenido"
ESTADOS_NODO = (ARRANCANDO, OPERATIVO, RESTRINGIDO, EN_RECUPERACION, DETENIDO)

# Motivos por los que el nodo se restringe (Q-N1, propuesta P-09). Son códigos del contrato: la pantalla les pone texto.
M_TRANSACCION_NO_INMEDIATA = "transaccion_no_inmediata"     # `transaction_mode` dejó de ser IMMEDIATE: el orden de la secuencia ya no está garantizado (P-02)
M_DISCO_ESCASO = "disco_escaso"                               # menos de AVACOM_NODO_DISCO_MIN_GB o de AVACOM_NODO_DISCO_MIN_PCT libres
M_BASE_DANADA = "base_danada"                                 # `PRAGMA quick_check` no respondió «ok»
M_WAL_ENORME = "wal_enorme"                                   # el diario WAL supera AVACOM_NODO_WAL_MAX_MB sin volcarse
M_CONSUMIDOR_NUCLEO_SUSPENDIDO = "consumidor_nucleo_suspendido"
M_RELOJ_RETROCEDIDO = "reloj_retrocedido"
MOTIVOS_RESTRICCION = (M_TRANSACCION_NO_INMEDIATA, M_DISCO_ESCASO, M_BASE_DANADA, M_WAL_ENORME, M_CONSUMIDOR_NUCLEO_SUSPENDIDO, M_RELOJ_RETROCEDIDO)

# --------------------------------------------------------------------------------------------------------------------------- estados de un evento (H)
EV_PENDIENTE, EV_APLICADO, EV_RECONOCIDO = "pendiente", "aplicado", "reconocido"     # «reenviado» del Maestro = reconocido por la sincronización remota (V1)
ESTADOS_EVENTO = (EV_PENDIENTE, EV_APLICADO, EV_RECONOCIDO)

# --------------------------------------------------------------------------------------------------------------------------- estados de un consumidor (P-06)
C_AL_DIA, C_REZAGADO, C_RECONSTRUYENDOSE, C_SUSPENDIDO = "al_dia", "rezagado", "reconstruyendose", "suspendido"
ESTADOS_CONSUMIDOR = (C_AL_DIA, C_REZAGADO, C_RECONSTRUYENDOSE, C_SUSPENDIDO)

# --------------------------------------------------------------------------------------------------------------------------- estados de un problema (P-07)
PR_APARTADO, PR_REPROCESADO, PR_DESCARTADO = "apartado", "reprocesado", "descartado"
ESTADOS_PROBLEMA = (PR_APARTADO, PR_REPROCESADO, PR_DESCARTADO)

# --------------------------------------------------------------------------------------------------------------------------- las siete clases (Parte XI)
CLASE_DOMINIO, CLASE_APRENDIZAJE, CLASE_AULA, CLASE_DISPOSITIVO = "dominio", "aprendizaje", "aula", "dispositivo"
CLASE_AUDITORIA, CLASE_TECNICO, CLASE_SINCRONIZACION = "auditoria", "tecnico", "sincronizacion"
CLASES = (CLASE_DOMINIO, CLASE_APRENDIZAJE, CLASE_AULA, CLASE_DISPOSITIVO, CLASE_AUDITORIA, CLASE_TECNICO, CLASE_SINCRONIZACION)

DIA_MS = 24 * 3_600_000
PERMANENTE = None                                  # retención sin fin
CICLO_MESES_POR_DEFECTO = 12                       # Q-N4: la duración de un ciclo la define MOD-002, que no existe; se propone un año
RETENCION_MINIMA_DIAS = 7                          # BR-017: la retención mínima configurable, siete días por defecto


def retencion_dias(clase: str, ciclo_meses: int = CICLO_MESES_POR_DEFECTO) -> int | None:
    """La retención del Maestro por clase, en días (None = permanente). «5 ciclos» depende de cuánto dura un ciclo (Q-N4)."""
    return {
        CLASE_DOMINIO: PERMANENTE,
        CLASE_APRENDIZAJE: 5 * int(ciclo_meses) * 30,
        CLASE_AULA: 30,
        CLASE_DISPOSITIVO: 24 * 30,
        CLASE_AUDITORIA: 5 * 365,
        CLASE_TECNICO: 30,
        CLASE_SINCRONIZACION: 30,
    }[clase]


INMUTABLES = (CLASE_AUDITORIA,)                    # «5 años, inmutable»: ni la purga los toca

# --------------------------------------------------------------------------------------------------------------------------- sensibilidad (el sobre)
S_PUBLICA, S_INTERNA, S_PERSONAL, S_PERSONAL_MENOR = "publica", "interna", "personal", "personal_menor"
SENSIBILIDADES = (S_PUBLICA, S_INTERNA, S_PERSONAL, S_PERSONAL_MENOR)

# --------------------------------------------------------------------------------------------------------------------------- el sobre (BR-002, Parte XI)
CAMPOS_DEL_SOBRE = ("evento_id", "tipo", "version", "modulo", "secuencia", "creado_en", "agregado_tipo", "agregado_id", "actor", "dispositivo_id", "correlacion_id", "clase",
                    "sensibilidad")
MAX_TIPO, MAX_MODULO, MAX_AGREGADO_TIPO, MAX_AGREGADO_ID, MAX_ACTOR, MAX_DISPOSITIVO, MAX_CORRELACION = 96, 32, 48, 96, 96, 96, 64
CARGA_MAX_BYTES = 16 * 1024                        # R-13: tope de la carga serializada (propuesta: 16 KB; la carga más grande vista en el inventario cabe de sobra)

# R-13 · BR-127: claves que NUNCA van en una carga (comparación exacta y en minúsculas sobre cada clave del JSON, a cualquier profundidad). Credenciales, tokens, PIN, textos de respuestas
# libres, documentos de identidad, correos, nombres y rutas con archivos. Un productor que las traiga falla en pruebas y desarrollo; en producción el hecho NO se pierde: se acepta con
# la carga reemplazada por `{"_omitida": "carga_con_datos_personales"}` y queda un ERROR y un asiento (R-06).
CLAVES_PROHIBIDAS = frozenset({
    "password", "contrasena", "contraseña", "secreto", "secret", "token", "jwt", "authorization", "pin", "pin_maestro", "clave_secreta", "hash", "salt",
    "correo", "email", "mail", "telefono", "celular", "direccion",
    "nombres", "apellidos", "nombre_completo", "nombre_persona", "alias_persona",
    "documento", "dni", "cedula", "pasaporte", "identificador_personal",
    "texto_respuesta", "respuesta_libre", "respuesta_texto", "contenido_respuesta", "dibujo", "imagen", "archivo", "ruta", "path", "ruta_archivo",
})

# --------------------------------------------------------------------------------------------------------------------------- consumidores, reintentos, lotes (P-06, P-07)
LOTE_DE_EVENTOS = 200
MAX_INTENTOS = 5                                   # al quinto fallo el evento se aparta a `m15_problema` y la marca avanza (BR-008 hace seguro reintentar)
ESPERA_BASE_MS = 1_000                             # 1 s, 2 s, 4 s, 8 s, 16 s… con tope y jitter
ESPERA_TOPE_MS = 60_000
JITTER = 0.2                                       # ± 20 %
REZAGO_LIMITE = 10_000                             # eventos sin aplicar a partir de los cuales un consumidor se declara `suspendido` y se avisa (BR-018; propuesta)
MAX_ERROR = 200                                    # el último error de un problema, ya saneado, se recorta a esto

# --------------------------------------------------------------------------------------------------------------------------- anclas (P-12, P-13)
ANCLA_CADA_MS = 5_000                              # el ancla de la secuencia y del reloj se refresca como mucho cada 5 s…
ANCLA_CADA_EVENTOS = 1_000                         # …o cada 1000 eventos publicados, lo que llegue primero
# Margen con que salta el contador al detectar una restauración: lo emitible en el intervalo del ancla con holgura. Medido en la Fase 0: un INSERT ≈ 0,02 ms y un commit durable
# ≈ 1,3 ms, así que en 5 s caben a lo sumo ≈ 3 800 commits de un evento; 10 000 lo cubre con margen (propuesta).
MARGEN_SECUENCIA = 10_000
TOLERANCIA_RETROCESO_MS = 5 * 60_000               # el reloj por debajo de la marca alta más de 5 min es un retroceso (propuesta; MOD-018 usa 24 h para la licencia)
RETROCESO_RESTRINGE_MS = 24 * 3_600_000            # un retroceso de más de un día deja al nodo restringido (Q-N1, propuesta)

# --------------------------------------------------------------------------------------------------------------------------- umbrales del modo restringido (Q-N1, propuesta)
DISCO_MIN_BYTES = 2 * 1024 ** 3                    # < 2 GB libres
DISCO_MIN_PCT = 5.0                                # o < 5 %
WAL_MAX_BYTES = 512 * 1024 ** 2                    # un WAL de más de 512 MB sin checkpoint
HISTERESIS = 1.25                                  # se sale del modo restringido cuando la condición mejora un 25 % sobre el umbral de entrada

# --------------------------------------------------------------------------------------------------------------------------- permisos (sección J y P-17)
P_REPLAY = "node.queue.replay"                     # del Maestro: reprocesar y reproducir (administración; el técnico por escalada temporal)
P_READ = "node.queue.read"                         # extensión técnica propuesta: ver la cola y los problemas, sin carga útil (administración y técnico)
P_HEALTH = "node.health.read"                      # extensión técnica propuesta: el estado del nodo y su salud (administración y técnico)
PERMISOS = (P_REPLAY, P_READ, P_HEALTH)
PERMISOS_EXTENSION = (P_READ, P_HEALTH)

# --------------------------------------------------------------------------------------------------------------------------- acciones de bitácora (MOD-019, catálogo cerrado)
A_EVENTO_APARTADO = "nodo.evento_apartado"
A_EVENTO_REPROCESADO = "nodo.evento_reprocesado"
A_REPROCESO_FALLIDO = "nodo.reproceso_fallido"
A_CONSUMIDOR_REPRODUCIDO = "nodo.consumidor_reproducido"
A_CONSUMIDOR_REGISTRADO = "nodo.consumidor_registrado"
A_CONSUMIDOR_DESREGISTRADO = "nodo.consumidor_desregistrado"
A_MODULO_CORTADO = "nodo.modulo_cortado"
A_MODULO_INCOMPATIBLE = "nodo.modulo_incompatible"
A_RESTAURACION_DETECTADA = "nodo.restauracion_detectada"
A_EVENTO_NO_CATALOGADO = "nodo.evento_no_catalogado"
A_PURGA_EJECUTADA = "nodo.purga_ejecutada"
A_ACCESO_DENEGADO = "nodo.acceso_denegado"
A_MODO_RESTRINGIDO = "nodo.modo_restringido"
ACCIONES_DE_AUDITORIA = (A_EVENTO_APARTADO, A_EVENTO_REPROCESADO, A_REPROCESO_FALLIDO, A_CONSUMIDOR_REPRODUCIDO, A_CONSUMIDOR_REGISTRADO, A_CONSUMIDOR_DESREGISTRADO,
                         A_MODULO_CORTADO, A_MODULO_INCOMPATIBLE, A_RESTAURACION_DETECTADA, A_EVENTO_NO_CATALOGADO, A_PURGA_EJECUTADA, A_ACCESO_DENEGADO, A_MODO_RESTRINGIDO)

# --------------------------------------------------------------------------------------------------------------------------- eventos nodo.* (sección L; P-15)
EV_SERVICIOS_INICIADOS = "nodo.servicios_iniciados.v1"
EV_EVENTO_PUBLICADO = "nodo.evento_publicado.v1"                 # agregado por lote y consumidor (Q-N6)
EV_MARCA_AVANZADA = "nodo.marca_lectura_avanzada.v1"            # agregado por lote y consumidor (Q-N6)
EV_ENTREGA_REINTENTADA = "nodo.entrega_reintentada.v1"
EV_EVENTO_APARTADO = "nodo.evento_apartado.v1"
EV_EVENTO_REPROCESADO = "nodo.evento_reprocesado.v1"
EV_RECUPERACION_COMPLETADA = "nodo.recuperacion_completada.v1"
EV_SALUD_EVALUADA = "nodo.salud_evaluada.v1"                    # sólo al CAMBIAR (BR-130)
EV_INGRESO_LIMITADO = "nodo.ingreso_limitado.v1"
EVENTOS_DEL_MAESTRO = (EV_SERVICIOS_INICIADOS, EV_EVENTO_PUBLICADO, EV_MARCA_AVANZADA, EV_ENTREGA_REINTENTADA, EV_EVENTO_APARTADO, EV_EVENTO_REPROCESADO,
                       EV_RECUPERACION_COMPLETADA, EV_SALUD_EVALUADA, EV_INGRESO_LIMITADO)
# Extensiones (marcadas como tales, P-15): no están en el Maestro.
EV_RELOJ_RETROCEDIO = "nodo.reloj_retrocedido.v1"
EV_MODO_RESTRINGIDO = "nodo.modo_restringido.v1"
EV_CONSUMIDOR_REZAGADO = "nodo.consumidor_rezagado.v1"
EV_MODULO_CORTADO = "nodo.modulo_cortado.v1"
EVENTOS_EXTENSION = (EV_RELOJ_RETROCEDIO, EV_MODO_RESTRINGIDO, EV_CONSUMIDOR_REZAGADO, EV_MODULO_CORTADO)
EVENTOS = EVENTOS_DEL_MAESTRO + EVENTOS_EXTENSION
# Los de la clase sincronización describen el movimiento de la propia cola; los demás son técnicos.
EVENTOS_DE_SINCRONIZACION = (EV_EVENTO_PUBLICADO, EV_MARCA_AVANZADA, EV_ENTREGA_REINTENTADA, EV_EVENTO_APARTADO, EV_EVENTO_REPROCESADO)

# --------------------------------------------------------------------------------------------------------------------------- rutas núcleo (R-01)
# Lo que la plataforma JAMÁS rechaza por una condición suya (el modo restringido sólo responde 503 fuera de esto). Se deriva de los `urls.py` reales; es la lista de referencia que
# usará el middleware de la Fase 5 y la comprueba una prueba de arquitectura contra las rutas registradas.
PREFIJOS_NUCLEO = (
    "/health/", "/api/acceso/sesiones/", "/api/acceso/yo/", "/api/acceso/pin-maestro/", "/api/acceso/docentes/registro/", "/api/acceso/estudiantes/registro/",
    "/api/aula/", "/api/evaluacion/", "/api/modo-estudio/", "/api/dispositivos/latido/", "/api/logs/clientes/", "/api/nodo/", "/api/m/", "/api/medios/",
)
