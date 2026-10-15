"""
Unit of Work sobre Django: una transacción por caso de uso (el hecho, su historial, su auditoría y su evento se confirman juntos).

A diferencia de la evaluación, que confirma los errores de negocio porque el reloj ya provocó transiciones que son verdad aunque la acción se rechace, el libro
no tiene transiciones que el tiempo provoque: ante CUALQUIER error se revierte TODO, también lo que MOD-010 hizo dentro de esta transacción por encargo del
libro (una puntuación, el cierre de una revisión). Así no queda una revisión a medias en MOD-010 y sin calificación en el libro.
"""
from __future__ import annotations

from contextlib import contextmanager

from django.db import transaction

from . import repositorios as r
from .evaluacion import EvaluacionMod10
from .guia import GuiaBiblioteca
from .identidad import IdentidadAcceso


class Cajones:
    """Los repositorios sin transacción propia: lo que la unidad de trabajo abre dentro de su transacción."""

    def __init__(self):
        self.calificaciones = r.CalificacionesDjango()
        self.versiones = r.VersionesDjango()
        self.revisiones = r.RevisionesDjango()
        self.escalas = r.EscalasDjango()
        self.niveles = r.NivelesDjango()
        self.politica = r.PoliticaDjango()
        self.clasificaciones = r.ClasificacionesDjango()
        self.resultados = r.ResultadosDjango()
        self.agregados = r.AgregadosDjango()
        self.marcas = r.MarcasDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaGradebook()
        self.identidad = IdentidadAcceso()
        self.evaluacion = EvaluacionMod10()
        self.guia = GuiaBiblioteca()


class UnidadDeTrabajoGradebook(Cajones):
    """`lectura=True` es para las consultas: NO abre transacción. El nodo corre SQLite con `transaction_mode: IMMEDIATE`, que toma el bloqueo de escritura de TODA
    la base al abrir cualquier `atomic`; una consulta (y las llamadas a la biblioteca que algunas hacen) no debe dejar a las tabletas esperando para guardar sus
    respuestas. Una consulta nunca escribe, así que no necesita lo que la transacción da (todo o nada)."""

    def __init__(self, lectura: bool = False):
        super().__init__()
        self._lectura = lectura
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoGradebook":
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


class FabricaUoWGradebook:
    def __call__(self, lectura: bool = False) -> UnidadDeTrabajoGradebook:
        return UnidadDeTrabajoGradebook(lectura=lectura)
