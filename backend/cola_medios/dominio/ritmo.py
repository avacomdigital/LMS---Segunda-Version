"""
Regular el tráfico: un tope de bytes por segundo (cubo de fichas) y un número máximo de transferencias a la vez (cupos).

Los dos son seguros entre hilos (el nodo atiende peticiones, descargas y avisos desde hilos distintos) y no duermen por su cuenta: el cubo dice CUÁNTO
hay que esperar y quien lo usa decide cómo (`time.sleep` en un hilo, `asyncio.sleep` en el bucle del servidor).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class Cubo:
    """Tope global de ancho de banda. `bytes_por_seg = 0` significa sin tope. Permite una ráfaga de hasta un segundo de tráfico."""

    def __init__(self, bytes_por_seg: int = 0, reloj: Callable[[], float] = time.monotonic):
        self._tasa = max(0, int(bytes_por_seg))
        self._reloj = reloj
        self._candado = threading.Lock()
        self._fichas = float(self._tasa)
        self._ultima = reloj()

    @property
    def bytes_por_seg(self) -> int:
        return self._tasa

    def reservar(self, n: int) -> float:
        """Toma `n` bytes del cubo y devuelve los segundos que hay que esperar antes de enviarlos (0 si hay fichas)."""
        if self._tasa <= 0 or n <= 0:
            return 0.0
        with self._candado:
            ahora = self._reloj()
            self._fichas = min(float(self._tasa), self._fichas + (ahora - self._ultima) * self._tasa)
            self._ultima = ahora
            self._fichas -= n
            return 0.0 if self._fichas >= 0 else -self._fichas / self._tasa


class Cupos:
    """N transferencias a la vez. `intentar()` no espera; quien quiera esperar reintenta con la pausa que le convenga."""

    def __init__(self, maximo: int):
        self.maximo = max(1, int(maximo))
        self._candado = threading.Lock()
        self._en_uso = 0
        self.picos = 0

    @property
    def en_uso(self) -> int:
        return self._en_uso

    def intentar(self) -> bool:
        with self._candado:
            if self._en_uso >= self.maximo:
                return False
            self._en_uso += 1
            self.picos = max(self.picos, self._en_uso)
            return True

    def liberar(self) -> None:
        with self._candado:
            if self._en_uso > 0:
                self._en_uso -= 1


class Cupo:
    """Un cupo tomado. Liberarlo dos veces no cuenta dos veces (lo cierra la respuesta y también el generador)."""

    def __init__(self, cupos: Cupos):
        self._cupos = cupos
        self._candado = threading.Lock()
        self._activo = True

    def liberar(self) -> None:
        with self._candado:
            if not self._activo:
                return
            self._activo = False
        self._cupos.liberar()
