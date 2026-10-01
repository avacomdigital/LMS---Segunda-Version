"""Composition root de MOD-010: qué adaptador va con qué puerto y cómo se leen los parámetros de la instalación."""
from __future__ import annotations

import time

from django.conf import settings

from ..aplicacion.base import ConfigEvaluacion, Servicios
from .autorizacion import AutorizacionEvaluacion
from .contenido import ContenidoEvaluacion
from .unidad_trabajo import FabricaUoWEvaluacion


class RelojNodo:
    """BR-062 / INV-017: la marca temporal autoritativa la pone el equipo del aula."""

    def ahora_ms(self) -> int:
        return int(time.time() * 1000)


def configuracion() -> ConfigEvaluacion:
    """Los tiempos y los topes salen de `settings` (variables AVACOM_EVAL_*)."""
    return ConfigEvaluacion(
        latido_vencido_ms=int(getattr(settings, "AVACOM_EVAL_LATIDO_VENCIDO_MS", 30_000)),
        latido_seg=int(getattr(settings, "AVACOM_EVAL_LATIDO_SEG", 5)),
        gracia_ms=int(getattr(settings, "AVACOM_EVAL_GRACIA_MIN", 15)) * 60_000,
        max_respuestas=int(getattr(settings, "AVACOM_EVAL_MAX_RESPUESTAS", 200)),
        desfase_reloj_ms=int(getattr(settings, "AVACOM_EVAL_DESFASE_RELOJ_MS", 5_000)),
        armado_intentos=int(getattr(settings, "AVACOM_EVAL_ARMADO_INTENTOS", 200)),
        archivado_ms=int(getattr(settings, "AVACOM_EVAL_ARCHIVADO_H", 24)) * 3_600_000,
    )


def servicios() -> Servicios:
    return Servicios(uow=FabricaUoWEvaluacion(), contenido=ContenidoEvaluacion(), reloj=RelojNodo(), autorizacion=AutorizacionEvaluacion(),
                     config=configuracion())
