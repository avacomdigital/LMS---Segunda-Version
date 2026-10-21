"""
Los puertos hacia lo que NO existe todavía, dejados preparados (P-08, P-20):

  · `RespaldoAusente`   MOD-016 · Backup & Recovery. Hasta que exista, ningún evento está «incluido en un respaldo verificado»: la purga no es elegible nunca y la cola crece (Q-N3).
  · `SincronizacionAusente`   CAP-095 (V1), el drenaje a servicios remotos con reconocimiento: no está habilitada, así que la cuarta condición de BR-017 se cumple sola.

Cuando MOD-016 exista, su adaptador implementa `cubre(secuencia)` y `verificado_hasta()` y se enchufa en el composition root; nada más cambia.
"""
from __future__ import annotations


class RespaldoAusente:
    def cubre(self, secuencia: int) -> bool:
        return False

    def verificado_hasta(self) -> int:
        return 0


class RespaldoFijo:
    """Para las pruebas de la purga: «todo hasta esta secuencia está en un respaldo verificado»."""

    def __init__(self, hasta: int = 0):
        self.hasta = int(hasta)

    def cubre(self, secuencia: int) -> bool:
        return int(secuencia) <= self.hasta

    def verificado_hasta(self) -> int:
        return self.hasta


class SincronizacionAusente:
    def habilitada(self) -> bool:
        return False

    def reconocida_hasta(self) -> int:
        return 0


class SincronizacionFija:
    def __init__(self, habilitada: bool = True, reconocida_hasta: int = 0):
        self._habilitada, self._hasta = habilitada, int(reconocida_hasta)

    def habilitada(self) -> bool:
        return self._habilitada

    def reconocida_hasta(self) -> int:
        return self._hasta
