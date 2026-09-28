"""Unit of Work sobre Django: una transacción por caso de uso (hecho + auditoría + evento juntos)."""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r


class Cajones:
    """Los repositorios sin transacción propia: lo que usan los otros módulos desde `servicios.py`
    dentro de SU transacción (el login de `acceso`, la sesión de clase de `classroom_engine`)."""

    def __init__(self):
        self.dispositivos = r.DispositivosDjango()
        self.sesiones_alumno = r.SesionesAlumnoDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaExpediente()
        self.organizaciones = r.OrganizacionesAcceso()
        self.sesiones_usuario = r.SesionesUsuarioAcceso()


class UnidadDeTrabajoDispositivos(Cajones):
    def __init__(self):
        super().__init__()
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoDispositivos":
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        self._atomic.__exit__(tipo, valor, traza)
        self._atomic = None


class FabricaUoWDispositivos:
    def __call__(self) -> UnidadDeTrabajoDispositivos:
        return UnidadDeTrabajoDispositivos()
