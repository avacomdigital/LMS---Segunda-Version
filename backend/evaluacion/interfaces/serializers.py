"""
Forma de las entradas HTTP de `/api/evaluacion/`. La validación de NEGOCIO la hace el dominio (`evaluacion/dominio/`): aquí sólo se comprueba que los
campos tengan el tipo esperado. Ningún campo tiene valor por defecto: el dominio distingue una clave AUSENTE de una clave nula (por ejemplo
`intentos_permitidos: null` significa «sin tope», y ausente significa «uno», BR-072), así que `validated_data` sólo trae lo que el cliente mandó.
"""
from __future__ import annotations

from rest_framework import serializers


class _Docente(serializers.Serializer):
    actor = serializers.CharField(max_length=64, required=False, allow_blank=True)
    actor_rotulo = serializers.CharField(max_length=120, required=False, allow_blank=True)


class _Alumno(serializers.Serializer):
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True)
    alumno_id = serializers.CharField(max_length=64, required=False, allow_blank=True)


class AsignacionEntrada(_Docente):
    tipo = serializers.CharField(max_length=10, required=False)
    fuente = serializers.CharField(max_length=16, required=False, allow_blank=True)
    curso_ref = serializers.CharField(max_length=200, required=False, allow_blank=True)
    objeto_ref = serializers.CharField(max_length=120, required=False, allow_blank=True)
    leccion_ref = serializers.CharField(max_length=120, required=False, allow_blank=True)
    titulo = serializers.CharField(max_length=250, required=False, allow_blank=True)
    alcance = serializers.CharField(max_length=16, required=False, allow_blank=True)
    grupo_id = serializers.CharField(max_length=36, required=False, allow_blank=True)
    destinatarios = serializers.ListField(child=serializers.CharField(max_length=64), required=False, allow_null=True)
    sesion_id = serializers.CharField(max_length=36, required=False, allow_blank=True)
    nivel_examen = serializers.CharField(max_length=12, required=False, allow_blank=True)
    tiempo = serializers.JSONField(required=False, allow_null=True)
    intentos_permitidos = serializers.IntegerField(required=False, allow_null=True)
    abre_en = serializers.IntegerField(required=False, allow_null=True)
    limite_en = serializers.IntegerField(required=False, allow_null=True)
    plazo = serializers.CharField(max_length=12, required=False, allow_blank=True)
    gracia_min = serializers.IntegerField(required=False, allow_null=True)
    gracia_ms = serializers.IntegerField(required=False, allow_null=True)
    reactivacion = serializers.CharField(max_length=12, required=False, allow_blank=True)
    recursos = serializers.JSONField(required=False, allow_null=True)
    resultados = serializers.CharField(max_length=16, required=False, allow_blank=True)
    iniciar = serializers.BooleanField(required=False)


class CierreEntrada(_Docente):
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ProrrogaEntrada(_Docente):
    limite_en = serializers.IntegerField(required=False, allow_null=True)


class PlazoEntrada(_Docente):
    limite_en = serializers.IntegerField(required=False, allow_null=True)
    gracia_min = serializers.IntegerField(required=False, allow_null=True)
    gracia_ms = serializers.IntegerField(required=False, allow_null=True)


class NivelEntrada(_Docente):
    nivel_examen = serializers.CharField(max_length=12, required=False, allow_blank=True)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AdmisionEntrada(_Docente):
    decision = serializers.CharField(max_length=12, required=False, allow_blank=True)
    nivel_admitido = serializers.CharField(max_length=12, required=False, allow_blank=True)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ReactivarEntrada(_Docente):
    desde_pregunta = serializers.CharField(max_length=120, required=False, allow_blank=True)


class AnularEntrada(_Docente):
    motivo = serializers.CharField(max_length=300, required=False, allow_blank=True)


class PuntuarEntrada(_Docente):
    puntaje = serializers.FloatField(required=False, allow_null=True)
    comentario = serializers.CharField(max_length=500, required=False, allow_blank=True)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class DecisionEnvioEntrada(_Docente):
    decision = serializers.CharField(max_length=12, required=False, allow_blank=True)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AperturaEntrada(_Alumno):
    nombre = serializers.CharField(max_length=120, required=False, allow_blank=True)
    plataforma = serializers.CharField(max_length=16, required=False, allow_blank=True)
    version_app = serializers.CharField(max_length=32, required=False, allow_blank=True)
    capacidad_control = serializers.CharField(max_length=12, required=False, allow_blank=True)


class RespuestasEntrada(_Alumno):
    respuestas = serializers.ListField(child=serializers.DictField(), required=False, allow_null=True)
    origen = serializers.CharField(max_length=8, required=False, allow_blank=True)
    pregunta_actual = serializers.CharField(max_length=120, required=False, allow_blank=True)
    transcurrido_ms = serializers.IntegerField(required=False, allow_null=True)


class LatidoEntrada(_Alumno):
    pregunta_actual = serializers.CharField(max_length=120, required=False, allow_blank=True)
    transcurrido_ms = serializers.IntegerField(required=False, allow_null=True)
    hora_tableta_ms = serializers.IntegerField(required=False, allow_null=True)
    capacidad_control = serializers.CharField(max_length=12, required=False, allow_blank=True)
    bateria_pct = serializers.IntegerField(required=False, allow_null=True)
    espacio_libre_mb = serializers.IntegerField(required=False, allow_null=True)


class IncidentesEntrada(_Alumno):
    incidentes = serializers.ListField(child=serializers.DictField(), required=False, allow_null=True)


class BloqueoEntrada(_Alumno):
    resultado = serializers.CharField(max_length=12, required=False, allow_blank=True)
    capas = serializers.JSONField(required=False, allow_null=True)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class EntregaEntrada(_Alumno):
    confirmar = serializers.BooleanField(required=False)
    respuestas = serializers.ListField(child=serializers.DictField(), required=False, allow_null=True)
    origen = serializers.CharField(max_length=8, required=False, allow_blank=True)
    transcurrido_ms = serializers.IntegerField(required=False, allow_null=True)
