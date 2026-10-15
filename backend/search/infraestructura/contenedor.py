"""Composition root de MOD-021: qué adaptador va con qué puerto y cómo se leen los parámetros de la instalación."""
from __future__ import annotations

from django.conf import settings

from evaluacion.infraestructura.contenedor import RelojNodo      # MOD-015 · BR-062: UN solo reloj del nodo, el mismo de la evaluación

from ..aplicacion.puertos import Configuracion, Servicios
from ..dominio import catalogos as cat
from .autorizacion import AutorizacionSearch
from .catalogo import CatalogoBiblioteca
from .fuentes import AulaMod7, FuenteClases, FuenteEstudios, FuenteEvaluaciones
from .identidad import IdentidadAcceso
from .unidad_trabajo import FabricaUoWSearch


def configuracion() -> Configuracion:
    """Los topes salen de `settings` (variables AVACOM_SEARCH_*)."""
    return Configuracion(
        sincronizar_al_consultar=bool(getattr(settings, "AVACOM_SEARCH_SINCRONIZAR", True)),
        lote_eventos=int(getattr(settings, "AVACOM_SEARCH_LOTE_EVENTOS", cat.LOTE_DE_EVENTOS)),
        paginas_al_consultar=int(getattr(settings, "AVACOM_SEARCH_PAGINAS_AL_CONSULTAR", 3)),
    )


def servicios() -> Servicios:
    fuentes = [FuenteEvaluaciones(), FuenteEstudios(), FuenteClases()]
    return Servicios(
        uow=FabricaUoWSearch(), fuentes={f.tipo: f for f in fuentes}, identidad=IdentidadAcceso(), autorizacion=AutorizacionSearch(), catalogo=CatalogoBiblioteca(),
        aula=AulaMod7(), reloj=RelojNodo(), config=configuracion(),
    )
