"""Freno en memoria a los intentos repetidos de unirse con un código equivocado (007-10).

El nodo del aula es un solo proceso: un contador en memoria basta y reiniciar el nodo lo pone a cero, que es
justo lo que se quiere de un freno que sólo debe frenar ráfagas. El código de unión tiene seis dígitos: sin
freno, una tableta podría probar el millón de combinaciones en minutos."""
from __future__ import annotations

import threading


class LimitadorEnMemoria:
    """Implementa `aplicacion.puertos.Limitador`: `maximo` fallos por clave dentro de `ventana_ms`."""

    def __init__(self, maximo: int, ventana_ms: int):
        self.maximo = max(1, int(maximo))
        self.ventana_ms = max(1, int(ventana_ms))
        self._fallos: dict[str, list[int]] = {}
        self._candado = threading.Lock()

    def _recientes(self, clave: str, ahora: int) -> list[int]:
        recientes = [t for t in self._fallos.get(clave, []) if ahora - t < self.ventana_ms]
        if recientes:
            self._fallos[clave] = recientes
        else:
            self._fallos.pop(clave, None)
        return recientes

    def registrar_fallo(self, clave: str, ahora: int) -> None:
        if not clave:
            return
        with self._candado:
            self._recientes(clave, ahora)
            self._fallos.setdefault(clave, []).append(ahora)

    def bloqueado(self, clave: str, ahora: int) -> int:
        if not clave:
            return 0
        with self._candado:
            recientes = self._recientes(clave, ahora)
            if len(recientes) < self.maximo:
                return 0
            return max(1, recientes[0] + self.ventana_ms - ahora)

    def olvidar(self, clave: str) -> None:
        with self._candado:
            self._fallos.pop(clave, None)
