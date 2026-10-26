"""
Los puertos hacia lo que NO existe todavía, dejados preparados (P-08, P-20):

  · `RespaldoVerificado` MOD-016 · Backup & Recovery (ya existe): un evento está «incluido en un respaldo verificado» si su secuencia es ≤ la secuencia global del último respaldo
    verificado y restaurable que sigue en el equipo (BR-017, INV-009). Si MOD-016 no responde, responde lo prudente: NADA está respaldado (R-04: la purga no avanza).
  · `RespaldoAusente`   el puerto sin MOD-016: ningún evento está respaldado, la purga no es elegible nunca y la cola crece (Q-N3). Queda para las pruebas y como respaldo del anterior.
  · `SincronizacionAusente`   CAP-095 (V1), el drenaje a servicios remotos con reconocimiento: no está habilitada, así que la cuarta condición de BR-017 se cumple sola.

Su adaptador implementa `cubre(secuencia)` y `verificado_hasta()` y se enchufa en el composition root; nada más cambia.
"""
from __future__ import annotations


class RespaldoVerificado:
    """MOD-016 por su `servicios.py` (BR-004): nunca lanza, y ante cualquier fallo dice que no hay nada respaldado."""

    def cubre(self, secuencia: int) -> bool:
        return int(secuencia) <= self.verificado_hasta()

    def verificado_hasta(self) -> int:
        try:
            from respaldo import servicios as respaldo   # frontera entre módulos: sólo en el adaptador
            return int(respaldo.verificado_hasta())
        except Exception:   # noqa: BLE001 — R-04
            return 0


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
