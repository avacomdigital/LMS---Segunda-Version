"""
El planificador: la cola ligera en memoria. Guarda las tareas VIVAS (pendientes y en descarga) y entrega la siguiente por prioridad y, a igual prioridad,
por orden de llegada. Sus estados viven además en la base (`cm_recurso`), así que tras un reinicio se reconstruye de ahí.

Un hilo de descarga reservado (`urgente_solo`) sólo toma tareas urgentes (lo que se proyecta, un examen, una clase): si todos los hilos estuvieran bajando
paquetes de estudio de 400 MB, lo que el profesor acaba de proyectar esperaría minutos.
"""
from __future__ import annotations

import heapq
import itertools
import threading
import time

from ..dominio import catalogos as cat
from ..dominio.clave import ClaveMedio
from .tarea import Tarea


class Planificador:
    def __init__(self):
        self.candado = threading.RLock()
        self._despertar = threading.Condition(self.candado)
        self._activas: dict[str, Tarea] = {}
        self._montículo: list[tuple[int, int, str]] = []
        self._orden = itertools.count()
        self._cerrado = False

    # --------------------------------------------------------------- consulta
    def activa(self, huella: str) -> Tarea | None:
        with self.candado:
            return self._activas.get(huella)

    def activas(self) -> list[Tarea]:
        with self.candado:
            return list(self._activas.values())

    def contar(self) -> dict[str, int]:
        with self.candado:
            tareas = list(self._activas.values())
        return {cat.PENDIENTE: sum(1 for t in tareas if t.estado == cat.PENDIENTE), cat.DESCARGANDO: sum(1 for t in tareas if t.estado == cat.DESCARGANDO)}

    # ------------------------------------------------------------- escritura
    def crear(self, recurso: dict, clave: ClaveMedio, version: str, prioridad: int) -> Tarea:
        """La tarea del recurso: la que ya hay si la hay (varias tabletas piden lo mismo y se baja una vez) o una nueva."""
        with self.candado:
            existente = self._activas.get(clave.huella())
            if existente is not None:
                self.priorizar(existente, prioridad)
                return existente
            tarea = Tarea(recurso, clave, version, prioridad, next(self._orden))
            self._activas[tarea.huella] = tarea
            heapq.heappush(self._montículo, (tarea.prioridad, tarea.orden, tarea.huella))
            self._despertar.notify()
            return tarea

    def priorizar(self, tarea: Tarea, prioridad: int) -> None:
        """Sube la prioridad de una tarea pendiente (nunca la baja: eso es `bajar`)."""
        with self.candado:
            if prioridad < tarea.prioridad:
                tarea.prioridad = prioridad
                if tarea.estado == cat.PENDIENTE:
                    heapq.heappush(self._montículo, (tarea.prioridad, tarea.orden, tarea.huella))
                    self._despertar.notify()

    def bajar(self, recurso_ids: list[str], a: int) -> None:
        """Lo que dejó de proyectarse pasa a prioridad de clase (sólo baja; una tarea ya urgente por otro motivo no sube)."""
        ids = set(recurso_ids)
        with self.candado:
            for tarea in self._activas.values():
                if tarea.id in ids and tarea.prioridad < a:
                    tarea.prioridad = a
                    if tarea.estado == cat.PENDIENTE:
                        heapq.heappush(self._montículo, (tarea.prioridad, tarea.orden, tarea.huella))
            self._despertar.notify_all()

    def terminar(self, tarea: Tarea) -> None:
        with self.candado:
            if self._activas.get(tarea.huella) is tarea:
                del self._activas[tarea.huella]

    def siguiente(self, *, urgente_solo: bool, segundos: float) -> Tarea | None:
        """La tarea más urgente que espera turno, ya marcada como `descargando`; None si no hay nada (o se cerró) pasado el plazo."""
        limite = time.monotonic() + segundos
        with self._despertar:
            while not self._cerrado:
                while self._montículo:
                    prioridad, _, huella = self._montículo[0]
                    tarea = self._activas.get(huella)
                    if tarea is None or tarea.estado != cat.PENDIENTE or tarea.prioridad != prioridad:
                        heapq.heappop(self._montículo)      # entrada vieja: la tarea ya terminó o cambió de prioridad
                        continue
                    if urgente_solo and prioridad > cat.URGENTE_HASTA:
                        break
                    heapq.heappop(self._montículo)
                    tarea.marcar(cat.DESCARGANDO)
                    return tarea
                restante = limite - time.monotonic()
                if restante <= 0:
                    return None
                self._despertar.wait(restante)
        return None

    def cerrar(self) -> None:
        with self._despertar:
            self._cerrado = True
            self._despertar.notify_all()
