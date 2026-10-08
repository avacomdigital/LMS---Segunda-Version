"""
Una tarea es el trabajo VIVO de traer un recurso: lo que los hilos de descarga y las peticiones que lo siguen comparten en memoria. El índice persistente
(`cm_recurso`) guarda lo que sobrevive a un reinicio; la tarea guarda el progreso al segundo y el aviso a quien espera.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from ..dominio import catalogos as cat
from ..dominio.clave import ClaveMedio

TERMINADOS = (cat.DISPONIBLE, cat.FALLIDO, cat.CANCELADO)


class Tarea:
    def __init__(self, recurso: dict, clave: ClaveMedio, version: str, prioridad: int, orden: int):
        self.id: str = recurso["id"]
        self.clave = clave
        self.huella = clave.huella()
        self.version = version
        self.prioridad = prioridad
        self.orden = orden
        self.estado = cat.PENDIENTE
        self.bytes_total: int | None = recurso.get("bytes_total")
        self.bytes_hechos = 0
        self.mime = recurso.get("tipo_mime") or ""
        self.sha256 = ""
        self.error: Exception | None = None
        self.error_codigo = ""
        self.cancelar = False
        self.cond = threading.Condition()

    # ------------------------------------------------------------------ estado
    @property
    def terminada(self) -> bool:
        return self.estado in TERMINADOS

    def fijar(self, *, total: int | None, mime: str) -> None:
        with self.cond:
            self.bytes_total = total
            self.mime = mime or self.mime
            self.cond.notify_all()

    def avanzar(self, hechos: int) -> None:
        with self.cond:
            self.bytes_hechos = hechos
            self.cond.notify_all()

    def terminar(self, estado: str, *, error: Exception | None = None, codigo: str = "", sha256: str = "") -> None:
        with self.cond:
            self.estado = estado
            self.error = error
            self.error_codigo = codigo
            if sha256:
                self.sha256 = sha256
            if estado == cat.DISPONIBLE and self.bytes_total is None:
                self.bytes_total = self.bytes_hechos
            self.cond.notify_all()

    def marcar(self, estado: str) -> None:
        with self.cond:
            self.estado = estado
            self.cond.notify_all()

    def esperar(self, condicion: Callable[[], bool], segundos: float) -> bool:
        """Bloquea el hilo hasta que `condicion()` sea verdadera o pasen `segundos`. Devuelve el valor final de la condición."""
        with self.cond:
            return self.cond.wait_for(condicion, timeout=max(0.0, segundos))

    def instantanea(self) -> dict:
        return {"id": self.id, "estado": self.estado, "prioridad": self.prioridad, "bytes_total": self.bytes_total, "bytes_hechos": self.bytes_hechos}
