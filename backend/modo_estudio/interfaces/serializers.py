"""
Forma de las entradas HTTP de `/api/modo-estudio/`. Aquí sólo se valida la FORMA (tipos, longitudes); las reglas de negocio las hace el dominio.

Cada serializer declara TODOS los campos que el caso de uso lee: DRF descarta lo que no declara. `dispositivo` es la huella del aparato
(`identificador_hw`); `alumno_id` lo manda la tableta sin sesión, en cualquier aparato: es el alumno que se eligió en «¿Quién eres?» (D-15). Los campos de
contenido libre (`respuestas`, `eventos`) viajan como JSON: el dominio los valida elemento por elemento, porque un elemento malo no debe tumbar a los demás.
"""
from __future__ import annotations

from rest_framework import serializers


class _ConAparato(serializers.Serializer):
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    alumno_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class SesionEntrada(_ConAparato):
    nombre = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    plataforma = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    version_app = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class CierreSesionEntrada(_ConAparato):
    cola_pendiente = serializers.IntegerField(min_value=0, required=False, default=0)
    limpieza = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")


class LimpiezaEntrada(_ConAparato):
    resultado = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")


class ProgresoEntrada(_ConAparato):
    bloques_vistos = serializers.ListField(child=serializers.CharField(max_length=200), required=False, allow_empty=True)
    bloque_actual = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)
    posicion_seg = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    capturado_en = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class AparatoEntrada(_ConAparato):
    """Los POST que no llevan más datos que quién los hace (completar, terminar una práctica)."""


class PracticaEntrada(_ConAparato):
    objeto_ref = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    nueva = serializers.BooleanField(required=False, default=False)


class RespuestasEntrada(_ConAparato):
    respuestas = serializers.JSONField(required=False, allow_null=True)
    terminar = serializers.BooleanField(required=False, default=False)


class PaqueteEntrada(_ConAparato):
    asignacion_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")


class ConfirmarEntrada(_ConAparato):
    huella = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    bytes = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class SyncEntrada(_ConAparato):
    emisor_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    eventos = serializers.JSONField(required=False, allow_null=True)


class _ConActor(serializers.Serializer):
    """El profesor de OPS. Sin sesión (Q-34) declara `actor`; con sesión lo fija el token y estos campos se ignoran."""

    actor = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    actor_rotulo = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class ActorEntrada(_ConActor):
    """Las acciones del profesor que no llevan más datos que quién las hace (cerrar)."""


class AsignacionNuevaEntrada(_ConActor):
    alcance = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    grupo_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")
    alumnos = serializers.ListField(child=serializers.CharField(max_length=64), required=False, allow_empty=True)
    curso_ref = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    fuente = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    leccion_ref = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    titulo = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")
    consigna = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    fecha_limite = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    plazo = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    gracia_min = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    paquete_permitido = serializers.BooleanField(required=False)


class AsignacionCambiosEntrada(_ConActor):
    fecha_limite = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quitar_fecha = serializers.BooleanField(required=False)
    plazo = serializers.CharField(max_length=12, required=False, allow_blank=True, allow_null=True)
    gracia_min = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    titulo = serializers.CharField(max_length=250, required=False, allow_blank=True, allow_null=True)
    consigna = serializers.CharField(max_length=2000, required=False, allow_blank=True, allow_null=True)
    paquete_permitido = serializers.BooleanField(required=False, allow_null=True)


class DecisionEntrada(_ConActor):
    alumno_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    secuencia = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    emisor_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    decision = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
