"""Unit of Work sobre Django: una transacción por caso de uso (el hecho, su auditoría y su evento se confirman juntos)."""
from __future__ import annotations

from django.db import transaction

from . import repositorios as r
from .aula import AulaClasesLectura
from .dispositivos import DispositivosDeviceManager
from .identidad import IdentidadAcceso
from .tiempo_real import TiempoRealEvaluacion


class Cajones:
    """Los repositorios sin transacción propia: lo que usa `evaluacion/servicios.py` (la interfaz para otros módulos) y lo que la unidad de trabajo
    abre dentro de su transacción."""

    def __init__(self):
        self.asignaciones = r.AsignacionesDjango()
        self.intentos = r.IntentosDjango()
        self.admisiones = r.AdmisionesDjango()
        self.incidentes = r.IncidentesDjango()
        self.outbox = r.OutboxDjango()
        self.auditoria = r.AuditoriaEvaluacion()
        self.identidad = IdentidadAcceso()
        self.dispositivos = DispositivosDeviceManager()
        self.aula = AulaClasesLectura()
        self.tiempo_real = TiempoRealEvaluacion()


class UnidadDeTrabajoEvaluacion(Cajones):
    def __init__(self):
        super().__init__()
        self._atomic = None

    def __enter__(self) -> "UnidadDeTrabajoEvaluacion":
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        """Un ERROR DE NEGOCIO (409, 403, 404… `ErrorEvaluacion`) no deshace lo que el reloj ya había provocado en esa misma petición: la pausa de quien dejó de
        dar señal, la entrega por tiempo agotado, el cierre por plazo. Esas transiciones son verdad aunque la acción que las descubrió se rechace, y confirmarlas
        evita repetirlas (y repetir su incidente) en cada intento. Los casos de uso validan ANTES de escribir lo suyo, así que confirmar no deja nada a medias;
        cualquier otra excepción (un fallo de verdad) sí revierte todo, como siempre."""
        from ..dominio.errores import ErrorEvaluacion

        if valor is not None and isinstance(valor, ErrorEvaluacion):
            self._atomic.__exit__(None, None, None)
        else:
            self._atomic.__exit__(tipo, valor, traza)
        self._atomic = None


class FabricaUoWEvaluacion:
    def __call__(self) -> UnidadDeTrabajoEvaluacion:
        return UnidadDeTrabajoEvaluacion()
