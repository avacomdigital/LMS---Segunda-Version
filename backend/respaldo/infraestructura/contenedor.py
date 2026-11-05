r"""
Composition root de MOD-016: qué adaptador va con qué puerto, en qué entorno corre este nodo y dónde guarda sus respaldos.

ENTORNO (P-12 de MOD-018, que aquí se reutiliza): lo clasificó `settings.AVACOM_LICENCIA_ENTORNO` al arrancar. Un nodo de PRODUCCIÓN guarda todo en
`%ProgramData%\AVACOM\OPS Master\Respaldos\`, usa las unidades extraíbles reales y acepta SÓLO las llaves de soporte de producción; ninguna variable de `backend.env` lo cambia. En
desarrollo y pruebas, `AVACOM_RESPALDO_DIR` o una carpeta temporal, carpetas que hacen de unidades, y además la llave de desarrollo.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from django.conf import settings

from ..aplicacion.base import ConfigRespaldo, Servicios
from .adaptadores import AulaDelNodo, MemoriaDelProceso, ModulosDelNodo, NodoDelProducto, RelojDelNodo, SoporteDeAvacom, TrasRestaurarDelNodo
from .almacen import AlmacenEnCarpeta
from .aplicador import AplicadorSqlite
from .autorizacion import AutorizacionRespaldo
from .clavero import ClaveroDelNodo
from .origen import OrigenDelNodo
from .unidad_trabajo import FabricaUoWRespaldo
from .unidades import UnidadesDelNodo

CARPETA_DE_CLAVES = Path(__file__).resolve().parent.parent / "claves"
PRODUCCION = "produccion"


def entorno() -> str:
    """El entorno que clasificó `settings` al arrancar (P-12). Si falta, producción: ante la duda, sólo llaves de producción."""
    return str(getattr(settings, "AVACOM_LICENCIA_ENTORNO", PRODUCCION))


def carpeta_de_respaldos() -> Path:
    if entorno() == PRODUCCION:
        programdata = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(programdata) / "AVACOM" / "OPS Master" / "Respaldos"
    propia = str(getattr(settings, "AVACOM_RESPALDO_DIR", "") or "").strip()
    if propia:
        return Path(propia)
    return Path(tempfile.gettempdir()) / ("avacom-respaldo-pruebas" if str(getattr(settings, "AVACOM_LMS_ENTORNO", "")) == "pruebas" else "avacom-respaldo-dev")


def unidades_configuradas() -> list[Path]:
    """Carpetas que hacen de unidad extraíble en desarrollo y pruebas (`AVACOM_RESPALDO_UNIDADES`, separadas por `;`). En producción no hay: las unidades son las reales."""
    if entorno() == PRODUCCION:
        return []
    crudo = str(getattr(settings, "AVACOM_RESPALDO_UNIDADES", "") or "")
    return [Path(p.strip()) for p in crudo.split(";") if p.strip()]


def carpetas_de_origen() -> str:
    return str(getattr(settings, "AVACOM_RESPALDO_CARPETAS", "") or "")


_candado = threading.Lock()
_cache: dict[tuple, Servicios] = {}


def servicios() -> Servicios:
    """Los servicios de este nodo. Se cachean por (entorno, carpeta, unidades, carpetas de origen, base): las pruebas cambian esos valores y reciben una instalación limpia; el nodo, una sola."""
    carpeta = carpeta_de_respaldos()
    unidades = unidades_configuradas()
    llave = (entorno(), str(carpeta), tuple(str(u) for u in unidades), carpetas_de_origen(), str(settings.DATABASES["default"].get("NAME")))
    with _candado:
        if llave not in _cache:
            if len(_cache) > 8:
                _cache.clear()
            origen = OrigenDelNodo(carpetas_de_origen())
            _cache[llave] = Servicios(
                uow=FabricaUoWRespaldo(), reloj=RelojDelNodo(), nodo=NodoDelProducto(), aula=AulaDelNodo(), clavero=ClaveroDelNodo(carpeta), soporte=SoporteDeAvacom(CARPETA_DE_CLAVES, entorno()),
                origen=origen, almacen=AlmacenEnCarpeta(carpeta), unidades=UnidadesDelNodo(carpeta / "entrada", unidades, usar_unidades_reales=entorno() == PRODUCCION),
                aplicador=AplicadorSqlite(origen), tras=TrasRestaurarDelNodo(), modulos=ModulosDelNodo(), autorizacion=AutorizacionRespaldo(), vivo=MemoriaDelProceso(),
                config=ConfigRespaldo(entorno=entorno()))
        return _cache[llave]


def reiniciar() -> None:
    """Para las pruebas: olvida todo lo cacheado."""
    with _candado:
        _cache.clear()
