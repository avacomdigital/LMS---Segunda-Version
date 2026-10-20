"""
El cupo de identidades de la licencia (MOD-018, BR-027) visto desde MOD-001: por la interfaz pública del módulo dueño (`licenciamiento.servicios`), nunca por sus tablas. Sólo se llama
al CREAR una identidad; si no cabe, `licenciamiento` lanza SU `CupoAgotado` y aquí se traduce al de este módulo (402 `cupo_agotado`, con el tipo «usuarios»), para que cada vista lo
devuelva con la forma de siempre y la importación de padrón rechace la fila y siga con las demás.
"""
from __future__ import annotations

from ..dominio import errores


class CupoDeLicencia:
    def exigir_usuario_nuevo(self, en_uso: int) -> None:
        from licenciamiento import servicios as licencia
        from licenciamiento.dominio.errores import CupoAgotado
        try:
            licencia.exigir_usuario_nuevo(en_uso)
        except CupoAgotado as error:
            raise errores.CupoAgotado(error.detalle, **error.extra) from error
