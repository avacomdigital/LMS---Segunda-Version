"""
Unit of Work sobre Django: una transacción por caso de uso (el hecho, su asiento y su evento se confirman juntos).

`lectura=True` es para las consultas: NO abre transacción (el nodo corre SQLite con `transaction_mode: IMMEDIATE`, que toma el bloqueo de escritura de TODA la base al abrir cualquier
`atomic`; evaluar la licencia cada pocos minutos no debe dejar a las tabletas esperando para guardar sus respuestas, R-07).
"""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r


class Cajones:
    def __init__(self):
        self.instalacion = r.InstalacionDjango()
        self.historial = r.HistorialDjango()
        self.observaciones = r.ObservacionesDjango()
        self.marca = r.MarcaDjango()
        self.consumo = r.ConsumoDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaLicencia()


class UnidadDeTrabajoLicencia(Cajones):
    def __init__(self, lectura: bool = False):
        super().__init__()
        self._lectura = lectura
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoLicencia":
        if not self._lectura:
            self._atomic = transaction.atomic()
            self._atomic.__enter__()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        if self._atomic is None:
            return
        try:
            self._atomic.__exit__(tipo, valor, traza)
        finally:
            self._atomic = None


class FabricaUoWLicencia:
    def __call__(self, lectura: bool = False) -> UnidadDeTrabajoLicencia:
        return UnidadDeTrabajoLicencia(lectura=lectura)
