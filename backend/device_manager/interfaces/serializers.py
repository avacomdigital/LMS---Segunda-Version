"""Forma de las entradas HTTP de `/api/dispositivos/`. La validación de negocio la hace el dominio."""
from __future__ import annotations

from rest_framework import serializers


class DispositivoEntrada(serializers.Serializer):
    """Registro / emparejamiento de la tableta. Acepta `identificador` (contrato de acceso) o `identificador_hw`."""

    identificador_hw = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    identificador = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    nombre = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    tipo = serializers.ChoiceField(choices=["TABLETA", "MASTER", "OTRO"], required=False, default="TABLETA")
    plataforma = serializers.ChoiceField(choices=["", "windows", "android"], required=False, allow_blank=True, default="")
    version_app = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")

    def validate(self, datos):
        if not (datos.get("identificador_hw") or datos.get("identificador")):
            raise serializers.ValidationError("Falta identificador_hw.")
        return datos


class DispositivoCambios(serializers.Serializer):
    nombre = serializers.CharField(max_length=120, required=False)
    tipo = serializers.ChoiceField(choices=["TABLETA", "MASTER", "OTRO"], required=False)
    activo = serializers.BooleanField(required=False)


class BloqueoEntrada(serializers.Serializer):
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
