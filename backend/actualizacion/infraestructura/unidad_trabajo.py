"""
Unit of Work sobre Django: una transacción por caso de uso (el hecho, su asiento y su evento se confirman juntos, BR-001).

`lectura=True` es para las consultas: NO abre transacción (el nodo corre SQLite con `transaction_mode: IMMEDIATE`, que toma el bloqueo de escritura de TODA la base al abrir cualquier
`atomic`; listar paquetes no debe dejar a las tabletas esperando para guardar sus respuestas).
"""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r


class UnidadDeTrabajoActualizacion:
    def __init__(self, lectura: bool = False):
        self.paquetes = r.PaquetesDjango()
        self.historial = r.HistorialDjango()
        self.eventos = r.EventosDelNodo()
        self.auditoria = r.AuditoriaActualizacion()
        self._lectura = lectura
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoActualizacion":
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


class FabricaUoWActualizacion:
    def __call__(self, lectura: bool = False) -> UnidadDeTrabajoActualizacion:
        return UnidadDeTrabajoActualizacion(lectura=lectura)
