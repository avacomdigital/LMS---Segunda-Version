"""
Catálogos CERRADOS de MOD-017 · Update Manager: los estados del paquete (H del Maestro y dos internos), los tipos del historial, los permisos, las acciones de bitácora, los
eventos `actualizacion.*.v1`, el formato `.avupd`, sus límites, los plazos y los motivos de rechazo. Es un archivo de DATOS: no importa Django ni a ningún otro módulo.

Lo que el Maestro no fija y aquí se propone queda marcado como «(extensión)» y aparece en las decisiones `D-n` de `01-diseno.md`.
"""
from __future__ import annotations

MODULO = "actualizacion"            # el nombre con que MOD-017 firma sus eventos en la cola única y sus asientos
SISTEMA = "sistema"                 # el actor cuando no hay una persona detrás del hecho (el vigilante, el arranque)

# --------------------------------------------------------------------------------------------------------------------------- estados del paquete (H)
RECIBIDO, VERIFICADO, INCOMPATIBLE, APLICADO, REVERTIDO, ARCHIVADO = "recibido", "verificado", "incompatible", "aplicado", "revertido", "archivado"
ESTADOS_DEL_MAESTRO = (RECIBIDO, VERIFICADO, INCOMPATIBLE, APLICADO, REVERTIDO, ARCHIVADO)
# Internos (extensión, P-05): entre «verificado» y «aplicado» el paquete espera su ventana o el `Host` lo está aplicando. `reversion_fallida` es el único estado en que el aula
# conserva la copia de la base sin haber vuelto atrás (P-07, Q-U4): se avisa y nadie borra nada.
PROGRAMADO, APLICANDO, REVERSION_FALLIDA = "programado", "aplicando", "reversion_fallida"
ESTADOS_EXTENSION = (PROGRAMADO, APLICANDO, REVERSION_FALLIDA)
ESTADOS = ESTADOS_DEL_MAESTRO + ESTADOS_EXTENSION
TERMINALES = (REVERTIDO, ARCHIVADO)

# --------------------------------------------------------------------------------------------------------------------------- el historial (m17_historial.tipo)
# De sólo inserción (P-05): el estado de un paquete se DERIVA de sus filas; no hay un «estado actual» que pueda divergir. `rechazado` es la única fila sin paquete: un archivo
# que no pasó la firma o la forma no se guarda (TST-048, TST-062).
H_RECIBIDO, H_VERIFICADO, H_INCOMPATIBLE, H_PROGRAMADO, H_DESPROGRAMADO, H_VENTANA_VENCIDA = (
    "recibido", "verificado", "incompatible", "programado", "desprogramado", "ventana_vencida")
H_BLOQUEADA, H_APLICANDO, H_APLAZADA, H_APLICADO, H_REVERTIDO, H_REVERSION_FALLIDA, H_ARCHIVADO, H_RECHAZADO = (
    "bloqueada", "aplicando", "aplazada", "aplicado", "revertido", "reversion_fallida", "archivado", "rechazado")
HISTORIAL = (H_RECIBIDO, H_VERIFICADO, H_INCOMPATIBLE, H_PROGRAMADO, H_DESPROGRAMADO, H_VENTANA_VENCIDA, H_BLOQUEADA, H_APLICANDO, H_APLAZADA, H_APLICADO, H_REVERTIDO,
             H_REVERSION_FALLIDA, H_ARCHIVADO, H_RECHAZADO)

# --------------------------------------------------------------------------------------------------------------------------- la orden al Host y su resultado (P-06)
ACCION_APLICAR, ACCION_REVERTIR = "aplicar", "revertir"
ACCIONES = (ACCION_APLICAR, ACCION_REVERTIR)
FORMATO_ORDEN = 1
ARCHIVO_ORDEN, ARCHIVO_RESULTADO = "orden.json", "resultado.json"
# Los pasos con checkpoint (P-07). El Host escribe `checkpoint.json` antes de cada uno; si muere a mitad, al volver reanuda o revierte.
PASO_COMPROBAR, PASO_RESPALDAR, PASO_INSTANTANEA, PASO_COPIAR, PASO_MIGRAR, PASO_VERIFICAR = "comprobar", "respaldar", "instantanea", "copiar", "migrar", "verificar"
PASOS = (PASO_COMPROBAR, PASO_RESPALDAR, PASO_INSTANTANEA, PASO_COPIAR, PASO_MIGRAR, PASO_VERIFICAR)
PASOS_REVERSION = (PASO_COMPROBAR, PASO_RESPALDAR, PASO_COPIAR, PASO_MIGRAR, PASO_VERIFICAR)
# Lo que el Host responde en `resultado.json`.
R_APLICADO, R_REVERTIDO, R_REVERSION_FALLIDA, R_APLAZADA, R_RECHAZADA = "aplicado", "revertido", "reversion_fallida", "aplazada", "rechazada"
RESULTADOS = (R_APLICADO, R_REVERTIDO, R_REVERSION_FALLIDA, R_APLAZADA, R_RECHAZADA)

# --------------------------------------------------------------------------------------------------------------------------- permisos (P-10, C-8)
P_APLICAR, P_IMPORTAR, P_PROGRAMAR, P_LEER = "update.apply", "update.package.import", "update.schedule", "update.read"
PERMISOS = (P_APLICAR, P_IMPORTAR, P_PROGRAMAR, P_LEER)
PERMISOS_DE_LA_FICHA = (P_APLICAR, P_IMPORTAR, P_PROGRAMAR)          # sección J de la ficha; sólo `update.apply` está además en la tabla de permisos del Maestro
PERMISOS_EXTENSION = (P_LEER,)                                       # ver estado e historial, sin datos de personas (extensión, Q-U3)
PERMISOS_DEL_TECNICO = (P_IMPORTAR, P_LEER)                          # `update.apply` sólo por escalada temporal (ESC-01, 4 h)

# --------------------------------------------------------------------------------------------------------------------------- auditoría (P-13)
A_IMPORTADO, A_VERIFICADO, A_RECHAZADO, A_PROGRAMADO, A_APLICADO, A_REVERTIDO, A_REVERSION_FALLIDA, A_BLOQUEADA, A_FIRMA_INVALIDA, A_INTEGRIDAD_ALTERADA = (
    "actualizacion.importado", "actualizacion.verificado", "actualizacion.rechazado", "actualizacion.programado", "actualizacion.aplicado", "actualizacion.revertido",
    "actualizacion.reversion_fallida", "actualizacion.bloqueada", "actualizacion.firma_invalida", "actualizacion.integridad_alterada")
# Extensiones (no están en P-13): la orden que se deja al Host, el fin del plazo de reversión, la ventana cancelada o vencida y el aplazamiento por una clase.
A_ORDEN_EMITIDA, A_ARCHIVADO, A_DESPROGRAMADO, A_APLAZADA = (
    "actualizacion.orden_emitida", "actualizacion.archivado", "actualizacion.desprogramado", "actualizacion.aplazada")
ACCIONES_DE_AUDITORIA = (A_IMPORTADO, A_VERIFICADO, A_RECHAZADO, A_PROGRAMADO, A_APLICADO, A_REVERTIDO, A_REVERSION_FALLIDA, A_BLOQUEADA, A_FIRMA_INVALIDA,
                         A_INTEGRIDAD_ALTERADA, A_ORDEN_EMITIDA, A_ARCHIVADO, A_DESPROGRAMADO, A_APLAZADA)
EXTENSIONES_DE_AUDITORIA = (A_ORDEN_EMITIDA, A_ARCHIVADO, A_DESPROGRAMADO, A_APLAZADA)

# --------------------------------------------------------------------------------------------------------------------------- eventos (P-12)
EV_DISPONIBLE, EV_IMPORTADO, EV_VERIFICADO, EV_PROGRAMADA, EV_BLOQUEADA, EV_APLICADA, EV_MIGRACION, EV_REVERTIDA, EV_RESULTADO = (
    "actualizacion.disponible_detectada.v1", "actualizacion.paquete_importado.v1", "actualizacion.paquete_verificado.v1", "actualizacion.ventana_programada.v1",
    "actualizacion.bloqueada.v1", "actualizacion.modulo_aplicada.v1", "actualizacion.migracion_ejecutada.v1", "actualizacion.revertida.v1",
    "actualizacion.resultado_registrado.v1")
EVENTOS_DEL_MAESTRO = (EV_DISPONIBLE, EV_IMPORTADO, EV_VERIFICADO, EV_PROGRAMADA, EV_BLOQUEADA, EV_APLICADA, EV_MIGRACION, EV_REVERTIDA, EV_RESULTADO)
EV_RECHAZADO, EV_REVERSION_FALLIDA = "actualizacion.paquete_rechazado.v1", "actualizacion.reversion_fallida.v1"
EVENTOS_EXTENSION = (EV_RECHAZADO, EV_REVERSION_FALLIDA)
EVENTOS = EVENTOS_DEL_MAESTRO + EVENTOS_EXTENSION
AGREGADO_PAQUETE = "paquete_actualizacion"

# --------------------------------------------------------------------------------------------------------------------------- el formato .avupd (P-02)
EXTENSION = ".avupd"
NOMBRE_MANIFIESTO, NOMBRE_FIRMA, CARPETA_ARCHIVOS = "manifiesto.json", "manifiesto.firma", "archivos/"
MAGIC = b"AVUP"                      # cabecera de `manifiesto.firma`: magic · versión(u16) · largo del kid(u8) · kid · firma(64). La firma cubre magic, versión, kid y el manifiesto.
VERSION_FIRMA = 1
FORMATO_MANIFIESTO = 1
TAM_FIRMA = 64
MAX_KID = 32
ETIQUETAS_CRITICAS_CONOCIDAS: tuple[str, ...] = ()     # un manifiesto que exija una etiqueta crítica que esta versión no entiende se rechaza (como en MOD-018)
PRODUCTO = "AVACOM LMS"

# Lo que un paquete de MÓDULO puede traer (R-07): archivos de las apps que declara, y el registro de módulos. Nada más.
RUTAS_PERMITIDAS_FUERA_DE_APP = ("avacom_lms/modulos.json",)
APPS_INTOCABLES = ("biblioteca",)                                    # R-12
EXTENSIONES_PERMITIDAS = (".py", ".json", ".txt", ".md", ".html", ".css", ".js", ".sql", ".csv", ".ini", ".cfg")
MAX_RUTA = 200
MAX_COMPONENTE = 80

# --------------------------------------------------------------------------------------------------------------------------- límites (A3: bomba de descompresión, rutas, tamaños)
MIB = 1024 * 1024
MAX_PAQUETE_BYTES = 512 * MIB         # el contenedor completo; se puede bajar desde `settings`, nunca subir por encima de esto
MAX_ARCHIVO_BYTES = 64 * MIB          # un archivo de código de más de 64 MB no es un archivo de código
MAX_MANIFIESTO_BYTES = 1 * MIB
MAX_ARCHIVOS = 5000
MAX_MODULOS_POR_PAQUETE = 20
MAX_MIGRACIONES_POR_MODULO = 50
MAX_NOMBRE = 120
MAX_NOTA = 2000

# --------------------------------------------------------------------------------------------------------------------------- plazos (P-08, P-09, C-3)
DIA_MS = 24 * 3_600_000
MINUTO_MS = 60_000
DIAS_REVERSION = 14                               # la instantánea se conserva 14 días; después el registro queda `archivado`
MARGEN_ANTES_DE_CLASE_MIN = 15                    # Q-U9: no se empieza una aplicación a menos de 15 min de una clase programada (si el nodo conoce el horario)
LIMITE_MIN_EVALUACION, LIMITE_MIN_GENERAL = 3, 5  # Q-U2 / C-3: tiempo máximo de reversión que el Host debe cumplir
VENTANA_MAX_MS = 24 * 3_600_000                   # una ventana dura como mucho un día
VENTANA_MIN_MS = 10 * MINUTO_MS                   # y como poco diez minutos: menos no alcanza para aplicar y verificar
VENTANA_TOLERANCIA_PASADO_MS = 5 * MINUTO_MS      # «desde» puede estar hasta cinco minutos en el pasado (el reloj de quien programa no es el del nodo)
VENTANA_MAX_ADELANTO_MS = 90 * DIA_MS             # y como mucho a 90 días vista

# --------------------------------------------------------------------------------------------------------------------------- orígenes de un paquete (P-11, P-18)
O_UNIDAD, O_ENTRADA, O_INTERNET = "unidad", "entrada", "internet"
ORIGENES = (O_UNIDAD, O_ENTRADA, O_INTERNET)

# --------------------------------------------------------------------------------------------------------------------------- motivos de rechazo (contrato con OPS: no se renombran)
# Los que son de FIRMA responden `firma_invalida` (422) y asientan `actualizacion.firma_invalida`; los demás responden `paquete_invalido` (422) y asientan `integridad_alterada`.
MOTIVOS_DE_FIRMA = ("sin_firma", "firma_formato", "version_firma_desconocida", "kid_invalido", "kid_desconocido", "firma_invalida")
MENSAJES_DE_MOTIVO = {
    "demasiado_grande": "El archivo es demasiado grande para ser un paquete de actualización.",
    "demasiado_corto": "El archivo está incompleto o dañado.",
    "estructura": "El archivo no tiene la forma de un paquete de actualización de AVACOM.",
    "truncado": "El paquete está incompleto: faltan bytes al final.",
    "bytes_sobrantes": "El paquete trae bytes que no forman parte de él.",
    "cifrado": "El paquete está cifrado y este equipo no acepta paquetes cifrados.",
    "zip64": "El paquete usa una variante del formato que este equipo no acepta.",
    "metodo": "Un archivo del paquete viene comprimido: un paquete de AVACOM va sin comprimir.",
    "nombre_duplicado": "El paquete trae dos archivos con el mismo nombre.",
    "directorio": "El paquete trae una carpeta como entrada: sólo se aceptan archivos.",
    "enlace": "El paquete trae un enlace simbólico: no se acepta.",
    "sin_manifiesto": "Al paquete le falta su manifiesto.",
    "sin_firma": "El paquete no está firmado: no se instala nada sin firma.",
    "firma_formato": "La firma del paquete no tiene el formato esperado.",
    "version_firma_desconocida": "La firma usa una versión que este equipo no entiende.",
    "kid_invalido": "La firma nombra una llave con un identificador inválido.",
    "kid_desconocido": "El paquete fue firmado con una llave que este equipo no reconoce.",
    "firma_invalida": "La firma del paquete no es válida: el archivo fue modificado o no es de AVACOM.",
    "manifiesto_ilegible": "El manifiesto del paquete no se puede leer.",
    "version_formato_desconocida": "El paquete usa una versión del manifiesto que este equipo no entiende: actualiza AVACOM OPS.",
    "etiqueta_critica_desconocida": "El paquete exige algo que esta versión no entiende: actualiza AVACOM OPS.",
    "campo_faltante": "Al manifiesto le falta información obligatoria.",
    "campo_invalido": "El manifiesto trae un dato fuera de rango.",
    "producto_distinto": "El paquete no es para este producto.",
    "ruta_invalida": "El paquete trae una ruta de archivo que no se acepta.",
    "ruta_absoluta": "El paquete trae una ruta absoluta.",
    "ruta_con_retroceso": "El paquete trae una ruta con «..».",
    "ruta_duplicada": "El manifiesto declara dos veces la misma ruta.",
    "ruta_fuera_del_modulo": "El paquete trae un archivo fuera de los módulos que declara.",
    "ruta_intocable": "El paquete intenta tocar lo que un paquete de módulo no puede tocar.",
    "extension_prohibida": "El paquete trae un tipo de archivo que no se acepta.",
    "archivo_no_declarado": "El paquete trae un archivo que el manifiesto no declara.",
    "archivo_faltante": "Al paquete le falta un archivo que el manifiesto declara.",
    "tamano_distinto": "Un archivo del paquete no mide lo que el manifiesto declara.",
    "sha_distinto": "Un archivo del paquete no coincide con su huella: fue modificado.",
    "demasiados_archivos": "El paquete trae más archivos de los que se aceptan.",
}

__all__ = [nombre for nombre in dir() if not nombre.startswith("_")]
