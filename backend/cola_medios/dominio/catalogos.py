"""
Catálogos de la cola de medios: estados de un recurso, prioridades, módulos que piden y motivos de fallo.

Los cinco estados son los del diseño: `pendiente` (esperando turno), `descargando` (el nodo lo trae de AVACOM Contenido), `disponible`
(está en la caché del nodo, con su SHA-256), `fallido` (no se pudo; dice por qué) y `cancelado` (alguien lo detuvo).
"""
from __future__ import annotations

# ------------------------------------------------------------------ estados
PENDIENTE = "pendiente"
DESCARGANDO = "descargando"
DISPONIBLE = "disponible"
FALLIDO = "fallido"
CANCELADO = "cancelado"
ESTADOS = (PENDIENTE, DESCARGANDO, DISPONIBLE, FALLIDO, CANCELADO)
ACTIVOS = (PENDIENTE, DESCARGANDO)          # los que la cola todavía tiene que atender

# -------------------------------------------------------------- prioridades
# Menor número = antes. Lo que el profesor proyecta no espera a nada; las descargas anticipadas del modo estudio van al fondo.
PROYECCION = 0      # lo que el profesor está proyectando en este momento
EVALUACION = 1      # medios de un examen en curso: el reloj del alumno corre
CLASE = 2           # recursos de una clase abierta (una tableta lo pide ahora)
ESTUDIO = 3         # un alumno lee su lección en línea
PAQUETE = 4         # preparación de un paquete de estudio (segundo plano)
PRECARGA = 5        # cualquier otra preparación anticipada
PRIORIDADES = {PROYECCION: "proyeccion", EVALUACION: "evaluacion", CLASE: "clase", ESTUDIO: "estudio", PAQUETE: "paquete", PRECARGA: "precarga"}
URGENTE_HASTA = CLASE                       # el hilo reservado sólo atiende prioridades hasta esta

# ------------------------------------------------------------------ módulos
MODULO_AULA = "aula"
MODULO_ESTUDIO = "estudio"
MODULO_EVALUACION = "evaluacion"
MODULOS = (MODULO_AULA, MODULO_ESTUDIO, MODULO_EVALUACION)

# ------------------------------------------------------------ motivos de fallo
ORIGEN_NO_DISPONIBLE = "origen_no_disponible"   # AVACOM Contenido no contestó (transitorio: se reintenta)
NO_ENCONTRADO = "no_encontrado"                 # el medio o el curso ya no están, o la política lo apagó (no se reintenta)
SIN_ESPACIO = "sin_espacio"                     # no cabe en la caché o en el disco
INCOMPLETO = "incompleto"                       # llegaron menos bytes de los anunciados
INTERNO = "interno"                             # un error del propio nodo
CANCELADO_POR_USUARIO = "cancelado"
SIN_REINTENTO = (NO_ENCONTRADO, SIN_ESPACIO)    # reintentar enseguida no cambia nada

# ------------------------------------------------------------------- ajustes
TROZO_BYTES = 256 * 1024                        # lo que se lee/escribe de una vez
