"""Unit of Work sobre Django: una transacción por caso de uso (el hecho, su auditoría y su evento se confirman juntos)."""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r
from .dispositivos import DispositivosDeviceManager
from .expediente import ExpedienteProgreso
from .identidad import IdentidadAcceso


class Cajones:
    """Los repositorios sin transacción propia: lo que usa `modo_estudio/servicios.py` (la interfaz para otros módulos) y lo que la
    unidad de trabajo abre dentro de su transacción."""

    def __init__(self):
        self.asignaciones = r.AsignacionesDjango()
        self.tareas = r.TareasDjango()
        self.paquetes = r.PaquetesDjango()
        self.practicas = r.PracticasDjango()
        self.sincronizaciones = r.SincronizacionesDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaExpediente()
        self.identidad = IdentidadAcceso()
        self.dispositivos = DispositivosDeviceManager()
        self.expediente = ExpedienteProgreso()


class UnidadDeTrabajoEstudio(Cajones):
    def __init__(self):
        super().__init__()
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoEstudio":
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        self._atomic.__exit__(tipo, valor, traza)
        self._atomic = None


class FabricaUoWEstudio:
    def __call__(self) -> UnidadDeTrabajoEstudio:
        return UnidadDeTrabajoEstudio()
