"""
El cupo de equipos de la licencia (MOD-018, FUN-091) visto desde MOD-009: por la interfaz pública del módulo dueño (`licenciamiento.servicios`), nunca por sus tablas. Sólo se llama al
REGISTRAR un equipo nuevo; si no cabe, `licenciamiento` lanza SU `CupoAgotado` y aquí se traduce al de este módulo (402 `cupo_agotado`, con el tipo «equipos»).
"""
from __future__ import annotations

from ..dominio import errores


class CupoDeLicencia:
    def exigir_equipo_nuevo(self, en_uso: int, identidad: dict | None = None, identificador_hw: str = "") -> dict | None:
        from licenciamiento import servicios as licencia
        from licenciamiento.dominio.errores import CupoAgotado, IdentidadRequerida
        try:
            return licencia.exigir_equipo_nuevo(en_uso, identidad, identificador_hw)
        except CupoAgotado as error:
            raise errores.CupoAgotado(error.detalle, **error.extra) from error
        except IdentidadRequerida as error:
            raise errores.IdentidadRequerida(error.detalle, **error.extra) from error
