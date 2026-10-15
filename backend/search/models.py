"""
MOD-021 · Search · tablas `m21_*`.

Lo que el módulo POSEE (escritor único, BR-003): la proyección de búsqueda de las entidades del LMS (`m21_documento` y su tabla de texto completo
`m21_documento_fts`, SQLite FTS5), la marca de lectura de cada cola que consume, el estado del índice, los sinónimos y su cola de salida.

Lo que NO hay, y no es un olvido (artículo 14): ninguna tabla ni columna con cursos, lecciones, recursos, preguntas ni claves. El catálogo de AVACOM Biblioteca se
pregunta en vivo en cada consulta y no se guarda. Tampoco hay copia de grupos, personas ni permisos: se leen de MOD-001 cuando se consulta.

Todo es RECONSTRUIBLE: vaciar `m21_documento` y volver a construirlo desde los módulos propietarios no pierde ningún dato académico (FUN-215). Ninguna columna decide
quién puede leer algo: `grupo_id` y `profesor_id` sólo sirven para acotar la consulta; el permiso se evalúa en cada consulta con lo vigente.
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import Q

from .dominio import catalogos as cat


def ahora_ms() -> int:
    return int(time.time() * 1000)


class Documento(models.Model):
    """La proyección de UNA entidad del LMS (evaluación, estudio asignado o clase). El texto original se guarda tal cual para mostrarlo; el texto de BÚSQUEDA (raíces)
    vive en `m21_documento_fts`, cuyo `rowid` es el `id` de esta fila."""

    id = models.BigAutoField(primary_key=True)
    tipo = models.CharField(max_length=16)
    entidad_id = models.CharField(max_length=64)
    subtipo = models.CharField(max_length=16, blank=True, default="")
    titulo = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True, default="")
    palabras = models.TextField(blank=True, default="")
    contexto = models.CharField(max_length=400, blank=True, default="")
    grupo_id = models.CharField(max_length=36, blank=True, default="")
    profesor_id = models.CharField(max_length=64, blank=True, default="")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    estado = models.CharField(max_length=24, blank=True, default="")
    referencia = models.JSONField(default=dict)
    huella = models.CharField(max_length=40)
    origen_actualizado_en = models.BigIntegerField(null=True, blank=True)
    indexado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m21_documento"
        constraints = [
            models.UniqueConstraint(fields=["tipo", "entidad_id"], name="ux_m21_documento_entidad"),
            models.CheckConstraint(condition=Q(tipo__in=cat.TIPOS_LOCALES), name="ck_m21_documento_tipo"),
        ]
        indexes = [models.Index(fields=["tipo", "grupo_id"], name="ix_m21_documento_grupo"), models.Index(fields=["curso_ref"], name="ix_m21_documento_curso")]

    def __str__(self) -> str:
        return f"{self.tipo}:{self.entidad_id} · {self.titulo}"


class MarcaDeLectura(models.Model):
    """Hasta dónde se leyó la cola de salida de un módulo propietario (`evaluacion`, `estudio`, `aula`). Avanza en la MISMA transacción que lo que se aplicó."""

    fuente = models.CharField(max_length=24, primary_key=True)
    secuencia = models.BigIntegerField(default=0)
    fallo_secuencia = models.BigIntegerField(default=0)
    fallos = models.PositiveSmallIntegerField(default=0)
    actualizada_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m21_marca_lectura"


class EstadoIndice(models.Model):
    """Una sola fila (`indice`). Guarda construyéndose · consultable · reconstruyéndose; «rezagado» se deriva al consultar (no se guarda: nunca queda viejo)."""

    id = models.CharField(max_length=16, primary_key=True, default="indice")
    estado = models.CharField(max_length=20, default=cat.CONSTRUYENDOSE)
    construido_en = models.BigIntegerField(null=True, blank=True)
    sincronizado_en = models.BigIntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True, default="")
    error_en = models.BigIntegerField(null=True, blank=True)
    reconstruccion_desde = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m21_estado_indice"
        constraints = [models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_GUARDADOS), name="ck_m21_estado_indice_estado")]


class Sinonimo(models.Model):
    """Un grupo de palabras que se buscan como una sola («examen», «evaluación», «prueba»). Es de Search, no del contenido: se administra aparte y se aplica al consultar."""

    id = models.BigAutoField(primary_key=True)
    palabras = models.JSONField(default=list)         # palabras ya normalizadas
    actualizado_en = models.BigIntegerField(default=ahora_ms)
    actualizado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m21_sinonimo"


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-021 (`busqueda.*.v1`). Se escribe en la misma transacción que el hecho. Cuando exista MOD-015 (m15_evento) las colas de todos los
    módulos se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=80)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m21_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m21_outbox")]
