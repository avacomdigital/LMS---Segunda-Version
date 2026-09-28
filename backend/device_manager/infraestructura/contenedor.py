"""Composition root de MOD-009: qué adaptador va con qué puerto."""
from __future__ import annotations

import time

from ..aplicacion.casos_uso import Servicios
from .repositorios import AutorizacionAcceso
from .unidad_trabajo import FabricaUoWDispositivos


class RelojNodo:
    """BR-062 / INV-017: la marca temporal autoritativa la pone el equipo del aula."""

    def ahora_ms(self) -> int:
        return int(time.time() * 1000)


def servicios() -> Servicios:
    return Servicios(uow=FabricaUoWDispositivos(), reloj=RelojNodo(), autorizacion=AutorizacionAcceso())
