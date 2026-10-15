"""Composition root de MOD-011: qué adaptador va con qué puerto y cómo se leen los parámetros de la instalación."""
from __future__ import annotations

from django.conf import settings

from evaluacion.infraestructura.contenedor import RelojNodo      # MOD-015 · BR-062: UN solo reloj del nodo, el mismo de la evaluación

from ..aplicacion.base import ConfigGradebook, Servicios
from .autorizacion import AutorizacionGradebook
from .unidad_trabajo import FabricaUoWGradebook


def configuracion() -> ConfigGradebook:
    """Los topes salen de `settings` (variables AVACOM_GRADEBOOK_*)."""
    return ConfigGradebook(
        lote_eventos=int(getattr(settings, "AVACOM_GRADEBOOK_LOTE_EVENTOS", 100)),
        sincronizar_al_consultar=bool(getattr(settings, "AVACOM_GRADEBOOK_SINCRONIZAR", True)),
    )


def servicios() -> Servicios:
    return Servicios(uow=FabricaUoWGradebook(), reloj=RelojNodo(), autorizacion=AutorizacionGradebook(), config=configuracion())
