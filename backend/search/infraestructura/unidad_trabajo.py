"""
Unit of Work sobre Django: una transacción por caso de uso (el documento, su marca de lectura, su evento y su asiento se confirman juntos).

`lectura=True` es para las consultas: NO abre transacción. El nodo corre SQLite con `transaction_mode: IMMEDIATE`, que toma el bloqueo de escritura de TODA la base al
abrir cualquier `atomic`; una búsqueda no debe dejar a las tabletas esperando para guardar sus respuestas. Una consulta nunca escribe en el índice dentro de ese bloque.
"""
from __future__ import annotations

from contextlib import contextmanager

from django.db import transaction

from . import repositorios as r


class UnidadDeTrabajoSearch:
    def __init__(self, lectura: bool = False):
        self._lectura = lectura
        self._atomic = None
        self.indice = r.IndiceFts5()
        self.marcas = r.MarcasDjango()
        self.estado = r.EstadoDjango()
        self.sinonimos = r.SinonimosDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaBusqueda()

    def __enter__(self) -> "UnidadDeTrabajoSearch":
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

    @contextmanager
    def aislado(self):
        """Un savepoint: si lo de dentro falla, se deshace sólo eso y la excepción sigue su camino (para que el que llama decida saltarse la entidad)."""
        with transaction.atomic():
            yield


class FabricaUoWSearch:
    def __call__(self, lectura: bool = False) -> UnidadDeTrabajoSearch:
        return UnidadDeTrabajoSearch(lectura=lectura)
