"""
Unit of Work sobre Django para MOD-015. `lectura=True` NO abre transacción (el nodo corre SQLite con `transaction_mode: IMMEDIATE`, que toma el bloqueo de escritura de TODA la base al
abrir cualquier `atomic`: los consumidores miran primero sin bloqueo, R-08). `en_transaccion()` es lo que `publicar` exige (BR-001): la transacción es la de la CONEXIÓN, así que da lo
mismo que la haya abierto el caso de uso de otro módulo o esta unidad de trabajo.
"""
from __future__ import annotations

from contextlib import contextmanager

from django.db import connection, transaction

from . import repositorios as r


class UnidadDeTrabajoNodo:
    def __init__(self, lectura: bool = False):
        self.eventos = r.EventosDjango()
        self.cortes = r.CortesDjango()
        self.modulos = r.ModulosDjango()
        self.consumidores = r.ConsumidoresDjango()
        self.marcas = r.MarcasDjango()
        self.problemas = r.ProblemasDjango()
        self.arranques = r.ArranquesDjango()
        self.marca_alta = r.MarcaAltaDjango()
        self.auditoria = r.AuditoriaNodo()
        self._lectura = lectura
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoNodo":
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

    @staticmethod
    def en_transaccion() -> bool:
        return bool(connection.in_atomic_block)

    @contextmanager
    def aislado(self):
        """Un savepoint: si lo de dentro falla, se deshace sólo eso y la excepción sigue su camino."""
        with transaction.atomic():
            yield


class FabricaUoWNodo:
    def __call__(self, lectura: bool = False) -> UnidadDeTrabajoNodo:
        return UnidadDeTrabajoNodo(lectura=lectura)
