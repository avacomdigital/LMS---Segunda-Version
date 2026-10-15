"""
Unit of Work sobre Django: una transacción por caso de uso (el hecho, su asiento y su evento se confirman juntos).

Igual que el libro, ante CUALQUIER error se revierte TODO: Reporting no tiene transiciones que el reloj provoque ni escribe en módulos ajenos, así que no hay nada que confirmar a
pesar de un rechazo. `lectura=True` es para las consultas: NO abre transacción (el nodo corre SQLite con `transaction_mode: IMMEDIATE`, que toma el bloqueo de escritura de TODA la base
al abrir cualquier `atomic`; un reporte no debe dejar a las tabletas esperando para guardar sus respuestas).
"""
from __future__ import annotations

from contextlib import contextmanager

from django.db import transaction

from . import repositorios as r
from .arbol import ArbolBiblioteca
from .fuentes import AulaFuente, EquiposFuente, EstudioFuente, EvaluacionFuente, LibroFuente
from .identidad import IdentidadAcceso


class Cajones:
    """Los repositorios y las fuentes sin transacción propia: lo que la unidad de trabajo abre dentro de su transacción."""

    def __init__(self):
        self.clases = r.ClasesDjango()
        self.avances = r.AvancesDjango()
        self.equipos_estado = r.EstadoDeEquiposDjango()
        self.marcas = r.MarcasDjango()
        self.estado = r.EstadoDjango()
        self.config = r.ConfigDjango()
        self.exportaciones = r.ExportacionesDjango()
        self.recientes = r.RecientesDjango()
        self.proyecciones = r.ProyeccionesDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaReporting()
        self.identidad = IdentidadAcceso()
        self.aula = AulaFuente()
        self.evaluacion = EvaluacionFuente()
        self.libro = LibroFuente()
        self.estudio = EstudioFuente()
        self.equipos = EquiposFuente()
        self.arbol = ArbolBiblioteca()


class UnidadDeTrabajoReporting(Cajones):
    def __init__(self, lectura: bool = False):
        super().__init__()
        self._lectura = lectura
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoReporting":
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
        """Un savepoint: si lo de dentro falla, se deshace sólo eso y la excepción sigue su camino (para que el que llama decida saltarse el evento)."""
        with transaction.atomic():
            yield


class FabricaUoWReporting:
    def __call__(self, lectura: bool = False) -> UnidadDeTrabajoReporting:
        return UnidadDeTrabajoReporting(lectura=lectura)
