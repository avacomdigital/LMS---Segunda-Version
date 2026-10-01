"""Validación de entrada de `/api/auditoria/` y `/api/logs/`. Los filtros son selectores, nunca texto libre obligatorio (nodo táctil)."""
from __future__ import annotations

from rest_framework import serializers

from ..dominio import asiento as dom
from ..dominio import catalogos
from ..logging_setup import APPS, CANALES


class FiltrosConsulta(serializers.Serializer):
    actor = serializers.CharField(required=False, max_length=64)
    actor_tipo = serializers.ChoiceField(required=False, choices=dom.ACTORES)
    desde = serializers.IntegerField(required=False, min_value=0)
    hasta = serializers.IntegerField(required=False, min_value=0)
    modulo = serializers.ChoiceField(required=False, choices=catalogos.MODULOS)
    accion = serializers.CharField(required=False, max_length=64)
    resultado = serializers.ChoiceField(required=False, choices=dom.RESULTADOS)
    objeto_tabla = serializers.CharField(required=False, max_length=64)
    objeto_id = serializers.CharField(required=False, max_length=64)
    dispositivo = serializers.CharField(required=False, max_length=64)
    correlacion = serializers.CharField(required=False, max_length=64)
    texto = serializers.CharField(required=False, max_length=100)
    tramo = serializers.CharField(required=False, max_length=36)
    sensible = serializers.BooleanField(required=False, allow_null=True)
    limite = serializers.IntegerField(required=False, min_value=1, max_value=200)
    antes = serializers.IntegerField(required=False, min_value=1)
    despues = serializers.IntegerField(required=False, min_value=0)

    def validate(self, datos):
        if datos.get("antes") is not None and datos.get("despues") is not None:
            raise serializers.ValidationError("Use `antes` o `despues`, no ambos.")
        return datos


class ExportacionEntrada(serializers.Serializer):
    """Alcance declarado: un tramo entero o un rango de secuencias; motivo de una lista cerrada (nodo táctil, MSG-054)."""

    tramo_id = serializers.CharField(required=False, max_length=36)
    desde = serializers.IntegerField(required=False, min_value=1)
    hasta = serializers.IntegerField(required=False, min_value=1)
    motivo_codigo = serializers.CharField(max_length=40)
    motivo_detalle = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate(self, datos):
        if not datos.get("tramo_id") and (datos.get("desde") is None or datos.get("hasta") is None):
            raise serializers.ValidationError("Indique `tramo_id` o el rango `desde` y `hasta`.")
        if datos.get("desde") is not None and datos.get("hasta") is not None and datos["hasta"] < datos["desde"]:
            raise serializers.ValidationError("`hasta` debe ser mayor o igual que `desde`.")
        return datos


class RenglonCliente(serializers.Serializer):
    """Un renglón de log de OPS/Student (§2.4): mismos campos mínimos de §2.1, sin datos personales."""

    ts = serializers.CharField(max_length=40)
    nivel = serializers.ChoiceField(choices=("WARNING", "ERROR", "CRITICAL", "INFO", "DEBUG"))
    canal = serializers.ChoiceField(choices=CANALES)
    app = serializers.ChoiceField(choices=APPS)
    modulo = serializers.CharField(required=False, allow_blank=True, max_length=40)
    evento = serializers.CharField(required=False, allow_blank=True, max_length=80)
    ruta = serializers.ChoiceField(required=False, choices=("happy", "sad", "bad"))
    mensaje = serializers.CharField(max_length=2000)
    detalle = serializers.JSONField(required=False, allow_null=True)
    traza = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=8000)
    corr = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=64)
    version_app = serializers.CharField(required=False, allow_blank=True, max_length=32)


class EntregaClientes(serializers.Serializer):
    dispositivo_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    app = serializers.ChoiceField(choices=("ops", "student"))
    version_app = serializers.CharField(required=False, allow_blank=True, max_length=32)
    renglones = RenglonCliente(many=True)


class FiltrosLogs(serializers.Serializer):
    canal = serializers.ChoiceField(required=False, choices=CANALES)
    nivel = serializers.ChoiceField(required=False, choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
    app = serializers.ChoiceField(required=False, choices=APPS)
    ruta = serializers.ChoiceField(required=False, choices=("happy", "sad", "bad"))
    desde = serializers.CharField(required=False, max_length=40)
    corr = serializers.CharField(required=False, max_length=64)
    dispositivo = serializers.CharField(required=False, max_length=64)
    evento = serializers.CharField(required=False, max_length=80)
    archivo = serializers.CharField(required=False, max_length=40)
    ultimos = serializers.IntegerField(required=False, min_value=1, max_value=1000)
