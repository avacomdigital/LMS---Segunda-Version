"""
Catálogos cerrados de MOD-016 · Backup & Recovery: tipos y estados del respaldo, hechos del historial, permisos, acciones de bitácora, eventos `respaldo.*` y límites. Es un archivo de
DATOS: no importa Django ni a ningún otro módulo.

Lo que el Maestro no fija y aquí se propone queda marcado como «(extensión)» y aparece en las preguntas para el CTO de `01-diseno.md`.
"""
from __future__ import annotations

MODULO = "respaldo"
SISTEMA = "sistema"

EXTENSION = ".avbak"                    # el archivo de respaldo (cifrado)
EXTENSION_PARCIAL = ".avbak.parcial"    # mientras se escribe: nunca se confunde con un respaldo terminado
MIB = 1024 * 1024
MINUTO_MS = 60_000
HORA_MS = 3_600_000
DIA_MS = 24 * HORA_MS

# ------------------------------------------------------------------------------------------------------------------- permisos (sección J del Maestro + extensiones)
P_LEER = "backup.read"                       # (extensión) ver el estado, el último respaldo y las constancias: administración y técnico, sin datos de personas
P_EJECUTAR = "backup.run"                    # (extensión) «Respaldar ahora» (JRN-018): sólo el técnico AVACOM
P_PROGRAMAR = "backup.schedule"              # FUN-169
P_VERIFICAR = "backup.verify"                # FUN-173
P_EXPORTAR = "backup.export"                 # FUN-176: el técnico + pase de soporte AVACOM (reemplaza la escalada ESC-03: la administración no tiene este permiso que conceder)
P_RESTAURAR = "backup.restore"               # FUN-174: el técnico + pase de soporte AVACOM (reemplaza la escalada ESC-01)
P_RESTAURAR_MODULO = "backup.restore.module"  # FUN-175: el técnico + pase de soporte AVACOM
PERMISOS = (P_LEER, P_EJECUTAR, P_PROGRAMAR, P_VERIFICAR, P_EXPORTAR, P_RESTAURAR, P_RESTAURAR_MODULO)
# Lo que sólo hace el personal de AVACOM WORLD (D-1): la administración de la institución NO tiene ninguno de éstos, ni siquiera por escalada.
PERMISOS_DE_AVACOM = (P_EJECUTAR, P_PROGRAMAR, P_VERIFICAR, P_EXPORTAR, P_RESTAURAR, P_RESTAURAR_MODULO)
# Los que, además del permiso, exigen un pase de soporte firmado por AVACOM (D-2): sacar datos del equipo o reemplazarlos.
PERMISOS_CON_PASE = (P_EXPORTAR, P_RESTAURAR, P_RESTAURAR_MODULO)

# ------------------------------------------------------------------------------------------------------------------- tipos y disparos
T_COMPLETO, T_INCREMENTAL = "completo", "incremental"
TIPOS = (T_COMPLETO, T_INCREMENTAL)

D_PROGRAMADO, D_MANUAL, D_PREVIO_ACTUALIZACION, D_PREVIO_RESTAURACION = "programado", "manual", "previo_a_actualizacion", "previo_a_restauracion"
DISPAROS = (D_PROGRAMADO, D_MANUAL, D_PREVIO_ACTUALIZACION, D_PREVIO_RESTAURACION)

CLASE_PRIMARIO, CLASE_REINSTALABLE = "primario", "reinstalable"      # «Qué entra al respaldo y qué no» del Maestro
CLASES_DE_ARCHIVO = (CLASE_PRIMARIO, CLASE_REINSTALABLE)

# ------------------------------------------------------------------------------------------------------------------- historial (sólo inserción)
H_INICIADO = "iniciado"
H_COMPLETO = "completo_ejecutado"
H_INCREMENTAL = "incremental_ejecutado"
H_FALLIDO = "fallido"
H_INTERRUMPIDO = "interrumpido"
H_REANUDADO = "reanudado"
H_VERIFICADO = "verificado"
H_NO_VERIFICADO = "no_verificado"
H_EXPORTADO = "exportado"
H_CADUCADO = "caducado"
H_PROGRAMADO = "programado"
H_CUSTODIA = "custodia_emitida"
H_RESTAURACION_INICIADA = "restauracion_iniciada"
H_RESTAURADO = "restauracion_completada"
H_RESTAURACION_ABORTADA = "restauracion_abortada"
H_MODULO_RESTAURADO = "modulo_restaurado"
H_INDICE = "indice_reconstruido"
HISTORIAL = (H_INICIADO, H_COMPLETO, H_INCREMENTAL, H_FALLIDO, H_INTERRUMPIDO, H_REANUDADO, H_VERIFICADO, H_NO_VERIFICADO, H_EXPORTADO, H_CADUCADO, H_PROGRAMADO, H_CUSTODIA,
             H_RESTAURACION_INICIADA, H_RESTAURADO, H_RESTAURACION_ABORTADA, H_MODULO_RESTAURADO, H_INDICE)
# Los hechos que cierran un intento de respaldo (con éxito o sin él).
H_TERMINALES = (H_COMPLETO, H_INCREMENTAL, H_FALLIDO)

# ------------------------------------------------------------------------------------------------------------------- estados que el Maestro nombra (H) + dos de extensión
E_EN_CURSO = "en_curso"
E_NO_VERIFICADO = "completo_no_verificado"
E_VERIFICADO = "completo_verificado"
E_EXPORTADO = "exportado"
E_CADUCADO = "caducado"
E_INCOMPLETO = "incompleto"          # (extensión) quedó a medias porque el nodo se apagó: se rehace con el mismo identificador (FUN-177)
E_FALLIDO = "fallido"                # (extensión) terminó con error y no produjo un respaldo
ESTADOS = (E_EN_CURSO, E_NO_VERIFICADO, E_VERIFICADO, E_EXPORTADO, E_CADUCADO, E_INCOMPLETO, E_FALLIDO)

# ------------------------------------------------------------------------------------------------------------------- eventos (los diez del Maestro + extensiones)
EV_PROGRAMADO = "respaldo.programado.v1"
EV_COMPLETO = "respaldo.completo_ejecutado.v1"
EV_INCREMENTAL = "respaldo.incremental_ejecutado.v1"
EV_VERIFICADO = "respaldo.verificado.v1"
EV_RESTAURADO = "respaldo.restauracion_completada.v1"
EV_MODULO_RESTAURADO = "respaldo.modulo_restaurado.v1"
EV_EXPORTADO = "respaldo.exportado.v1"
EV_REANUDADO = "respaldo.reanudado.v1"
EV_INDICE = "respaldo.indice_reconstruido.v1"
EV_PUNTO = "respaldo.punto_recuperacion_creado.v1"       # FUN-172: NO se publica todavía (D-14): el catálogo lo declara para cuando exista
EV_FALLIDO = "respaldo.fallido.v1"                       # (extensión)
EV_RESTAURACION_ABORTADA = "respaldo.restauracion_abortada.v1"   # (extensión)
EV_CADUCADO = "respaldo.caducado.v1"                     # (extensión)
EV_CUSTODIA = "respaldo.custodia_emitida.v1"             # (extensión)
EVENTOS = (EV_PROGRAMADO, EV_COMPLETO, EV_INCREMENTAL, EV_VERIFICADO, EV_RESTAURADO, EV_MODULO_RESTAURADO, EV_EXPORTADO, EV_REANUDADO, EV_INDICE, EV_PUNTO,
           EV_FALLIDO, EV_RESTAURACION_ABORTADA, EV_CADUCADO, EV_CUSTODIA)

# ------------------------------------------------------------------------------------------------------------------- bitácora (MOD-019): sólo ids, tipos, cifras y huellas; nunca rutas de personas ni contenido
A_PROGRAMADO = "respaldo.programado"
A_COMPLETO = "respaldo.completo_ejecutado"
A_INCREMENTAL = "respaldo.incremental_ejecutado"
A_FALLIDO = "respaldo.fallido"
A_VERIFICADO = "respaldo.verificado"
A_NO_VERIFICADO = "respaldo.no_verificado"
A_EXPORTADO = "respaldo.exportado"
A_RESTAURADO = "respaldo.restauracion_completada"
A_RESTAURACION_ABORTADA = "respaldo.restauracion_abortada"
A_MODULO_RESTAURADO = "respaldo.modulo_restaurado"
A_REANUDADO = "respaldo.reanudado"
A_CADUCADO = "respaldo.caducado"
A_CUSTODIA = "respaldo.custodia_emitida"
A_PASE_RECHAZADO = "respaldo.pase_rechazado"
A_ACCESO_DENEGADO = "respaldo.acceso_denegado"
ACCIONES_DE_AUDITORIA = (A_PROGRAMADO, A_COMPLETO, A_INCREMENTAL, A_FALLIDO, A_VERIFICADO, A_NO_VERIFICADO, A_EXPORTADO, A_RESTAURADO, A_RESTAURACION_ABORTADA,
                         A_MODULO_RESTAURADO, A_REANUDADO, A_CADUCADO, A_CUSTODIA, A_PASE_RECHAZADO, A_ACCESO_DENEGADO)

# ------------------------------------------------------------------------------------------------------------------- límites y valores por defecto
CHUNK = 1 * MIB                          # el tamaño del trozo cifrado: la memoria que usa un respaldo es de este orden, no del tamaño de la base
FORMATO = 1
MAX_NOTA = 280
MAX_ACTOR = 64
RETENCION_POR_DEFECTO = 14               # respaldos verificados que se conservan (la retención por clase de dato del Maestro se afina con el CTO: Q-B4)
COMPLETO_CADA_DIAS = 7                   # entre dos completos van incrementales
HORA_POR_DEFECTO_MIN = 2 * 60            # 02:00 hora local del equipo
AVISO_SIN_RESPALDO_DIAS = 7              # MSG-066: «sin respaldo en siete días»
PRUEBA_DE_RECUPERACION_CADA_DIAS = 30    # CAP-103 (V1): la prueba periódica de restaurabilidad
MARGEN_ESPACIO = 64 * MIB
VIGENCIA_PASE_MAX_MS = 24 * HORA_MS      # un pase de soporte vale como mucho un día (el mismo tope de ESC-05)
TOLERANCIA_PASE_MS = 5 * MINUTO_MS       # el reloj de quien emite y el del nodo no están sincronizados al milisegundo
ORIGENES_DE_ARCHIVO_MAX = 8
DIAS = (0, 1, 2, 3, 4, 5, 6)             # lunes = 0
# Por qué se restaura: una lista cerrada (el nodo principal no tiene teclado: nada que exija escribir). La nota es opcional.
MOTIVOS_DE_RESTAURACION = ("equipo_danado", "equipo_nuevo", "datos_danados", "error_humano", "prueba_de_recuperacion", "otro")

MENSAJES_DE_MOTIVO = {
    "formato_invalido": "El archivo no es un respaldo de AVACOM o está dañado.",
    "version_no_soportada": "El respaldo fue hecho por una versión del formato que este equipo no entiende.",
    "clave_no_disponible": "Este equipo no puede abrir el respaldo: hace falta el código de custodia de la institución.",
    "integridad_alterada": "El respaldo está alterado o incompleto: no se restaura.",
    "truncado": "El respaldo está truncado: no se restaura.",
    "huella_distinta": "La huella del archivo no coincide con la registrada.",
    "base_danada": "La base de datos del respaldo no pasó la verificación de integridad.",
    "cadena_incompleta": "Falta algún respaldo de la cadena de un incremental.",
    "base_de_version_posterior": "El respaldo es de una versión más nueva del producto que la instalada: actualiza el equipo antes de restaurar.",
    "punto_de_retorno": "No se pudo tomar el respaldo de seguridad previo: no se restaura sin un punto de retorno.",
}
