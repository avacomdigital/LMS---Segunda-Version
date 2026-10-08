"""
Cola de medios · tablas `cm_*`.

Lo que se guarda: qué recursos (video, audio, imagen, PDF, páginas html…) trajo o está trayendo el nodo desde AVACOM Contenido, en qué estado van, cuántos
bytes llevan, su SHA-256 y quién los pidió. Los BYTES viven en disco (`AVACOM_COLA_DIR`); aquí sólo está el índice.

Lo que NO hay (regla de oro, artículo 14): ninguna tabla ni columna de curso, lección, pregunta o clave de respuesta. Un recurso es una referencia
(`curso_ref`, `media_ref`, `ruta`) y los bytes de un medio que la biblioteca ya autorizó servir. El curso y la autorización siguen siendo de AVACOM
Biblioteca: el nodo la consulta antes de servir una copia (ver `aplicacion/servidor.py`).

La caché es REGENERABLE, no expediente: expulsar un recurso borra su fila (no hay CV-05 «nada se borra» aquí) y la próxima petición lo vuelve a traer.
Convenciones del repo: prefijo por módulo, identificadores de texto, tiempo en milisegundos del reloj del nodo.
"""
from __future__ import annotations

from django.db import models
from django.db.models import Q

from .dominio import catalogos as cat


def _lista(valores) -> list[tuple[str, str]]:
    return [(v, v) for v in valores]


class Recurso(models.Model):
    """Un medio (o un archivo interno de una simulación) y su copia en la caché del nodo."""

    id = models.CharField(max_length=36, primary_key=True)
    clave = models.CharField(max_length=64, unique=True)                     # SHA-256 de (fuente, curso_ref, media_ref, ruta)
    fuente = models.CharField(max_length=16)                                 # biblioteca | ejemplo
    curso_ref = models.CharField(max_length=200)
    curso_version = models.CharField(max_length=32, blank=True, default="")  # la versión instalada cuando se trajo: si cambia, la copia se descarta
    media_ref = models.CharField(max_length=200)
    ruta = models.CharField(max_length=500, blank=True, default="")         # vacía = el medio; si no, el archivo interno o `subtitulos`…
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS), default=cat.PENDIENTE)
    prioridad = models.SmallIntegerField(default=cat.CLASE)
    tipo_mime = models.CharField(max_length=200, blank=True, default="")
    bytes_total = models.BigIntegerField(null=True, blank=True)              # lo que anunció la fuente; None si no lo dijo
    bytes_hechos = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")         # huella del contenido ya completo (también es el ETag)
    cabeceras = models.JSONField(default=dict)                               # las `X-Avacom-*` que la fuente puso, para devolverlas igual
    intentos = models.IntegerField(default=0)
    error_codigo = models.CharField(max_length=40, blank=True, default="")
    error_detalle = models.CharField(max_length=500, blank=True, default="")
    reintentar_despues = models.BigIntegerField(null=True, blank=True)       # un fallido no se vuelve a intentar antes de este instante
    usos = models.BigIntegerField(default=0)
    creado_en = models.BigIntegerField()
    actualizado_en = models.BigIntegerField()
    iniciado_en = models.BigIntegerField(null=True, blank=True)
    terminado_en = models.BigIntegerField(null=True, blank=True)
    validado_en = models.BigIntegerField(null=True, blank=True)
    ultimo_uso_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "cm_recurso"
        constraints = [
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS), name="cm_recurso_estado_valido"),
            models.CheckConstraint(condition=Q(bytes_hechos__gte=0), name="cm_recurso_bytes_hechos_no_negativos"),
        ]
        indexes = [
            models.Index(fields=["estado", "prioridad"], name="cm_recurso_cola"),
            models.Index(fields=["curso_ref", "media_ref"], name="cm_recurso_medio"),
            models.Index(fields=["ultimo_uso_en"], name="cm_recurso_uso"),
        ]


class Solicitud(models.Model):
    """Quién quiere un recurso y para qué: el vínculo entre la cola de bytes y la actividad del aula, del estudio o del examen.

    Es lo que permite mostrar el avance de los recursos de UNA clase (`contexto_ref` = la sesión), de UNA asignación o de UN intento, y lo que fija la
    prioridad de un recurso (la mejor de sus solicitudes vigentes). Una proyección que el profesor reemplaza baja a `clase`."""

    id = models.CharField(max_length=36, primary_key=True)
    recurso = models.ForeignKey(Recurso, on_delete=models.CASCADE, related_name="solicitudes", db_column="recurso_id")
    modulo = models.CharField(max_length=12, choices=_lista(cat.MODULOS))
    contexto_ref = models.CharField(max_length=64, blank=True, default="")  # sesion_id | asignacion_id | intento_id
    prioridad = models.SmallIntegerField(default=cat.CLASE)
    persona_id = models.CharField(max_length=64, blank=True, default="")    # lógica (m01_usuario)
    dispositivo_id = models.CharField(max_length=64, blank=True, default="")  # lógica (m09_dispositivo)
    creada_en = models.BigIntegerField()
    vence_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "cm_solicitud"
        constraints = [
            models.CheckConstraint(condition=Q(modulo__in=cat.MODULOS), name="cm_solicitud_modulo_valido"),
            models.UniqueConstraint(fields=["recurso", "modulo", "contexto_ref", "persona_id"], name="cm_solicitud_unica"),
        ]
        indexes = [models.Index(fields=["modulo", "contexto_ref"], name="cm_solicitud_contexto")]
