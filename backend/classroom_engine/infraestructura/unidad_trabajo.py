"""Unit of Work sobre Django: una transacción por caso de uso (hecho + auditoría + evento juntos)."""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r


class UnidadDeTrabajoAula:
    def __init__(self):
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoAula":
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        self.sesiones = r.SesionesDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaExpediente()
        self.identidad = r.IdentidadAcceso()
        self.dispositivos = r.DispositivosDeviceManager()
        self.evaluacion = r.EvaluacionExpediente()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        self._atomic.__exit__(tipo, valor, traza)
        self._atomic = None


class FabricaUoWAula:
    def __call__(self) -> UnidadDeTrabajoAula:
        return UnidadDeTrabajoAula()
