"""Composition root de MOD-008: qué adaptador va con qué puerto y cómo se leen los parámetros de la instalación."""
from __future__ import annotations

import time

from django.conf import settings

from ..aplicacion.base import MIB, ConfigEstudio, Servicios
from .autorizacion import AutorizacionEstudio
from .contenido import ContenidoAula
from .unidad_trabajo import FabricaUoWEstudio


class RelojNodo:
    """BR-062 / INV-017: la marca temporal autoritativa la pone el equipo del aula."""

    def ahora_ms(self) -> int:
        return int(time.time() * 1000)


def configuracion() -> ConfigEstudio:
    """La vigencia de los paquetes, la gracia por defecto y el tope de un medio salen de `settings` (variables AVACOM_ESTUDIO_*)."""
    return ConfigEstudio(
        vigencia_dias=int(getattr(settings, "AVACOM_ESTUDIO_VIGENCIA_DIAS", 14)),
        gracia_ms=int(getattr(settings, "AVACOM_ESTUDIO_GRACIA_MIN", 15)) * 60_000,
        medio_max_bytes=int(getattr(settings, "AVACOM_ESTUDIO_MEDIO_MAX_MB", 512)) * MIB,
    )


def servicios() -> Servicios:
    return Servicios(uow=FabricaUoWEstudio(), contenido=ContenidoAula(), reloj=RelojNodo(), autorizacion=AutorizacionEstudio(),
                     config=configuracion())
