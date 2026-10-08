"""Unit of Work sobre Django: una transacción por caso de uso (hecho + auditoría + evento juntos)."""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r
from .tiempo_real import TiempoRealCanales


class UnidadDeTrabajoAula:
    def __init__(self, solo_lectura: bool = False):
        self._atomic = None
        # Una carpeta de sólo lectura no abre transacción (cada consulta va en autocommit y no toma el turno de escritura de SQLite): sirve para leer lo que
        # hace falta ANTES de una llamada lenta a otro servicio, sin retener a los demás escritores mientras se espera (prueba de 35 tabletas, 2026-10-08).
        self._solo_lectura = solo_lectura

    def __enter__(self) -> "UnidadDeTrabajoAula":
        if not self._solo_lectura:
            self._atomic = transaction.atomic()
            self._atomic.__enter__()
        self.sesiones = r.SesionesDjango()
        self.tiempo_real = TiempoRealCanales()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaExpediente()
        self.identidad = r.IdentidadAcceso()
        self.dispositivos = r.DispositivosDeviceManager()
        self.evaluacion = r.EvaluacionExpediente()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        if self._atomic is not None:
            self._atomic.__exit__(tipo, valor, traza)
            self._atomic = None


class FabricaUoWAula:
    def __init__(self, solo_lectura: bool = False):
        self._solo_lectura = solo_lectura

    def __call__(self) -> UnidadDeTrabajoAula:
        return UnidadDeTrabajoAula(self._solo_lectura)
