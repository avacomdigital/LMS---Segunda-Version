r"""
Composition root de MOD-017: qué adaptador va con qué puerto, en qué entorno corre este nodo y dónde guarda sus paquetes.

ENTORNO (P-12 de MOD-018, que aquí se reutiliza): lo clasificó `settings.AVACOM_LICENCIA_ENTORNO` al arrancar. Un nodo de PRODUCCIÓN acepta SÓLO las llaves de publicación de
producción y guarda todo en `%ProgramData%\AVACOM\OPS Master\Actualizaciones\`; ninguna variable de `backend.env` lo cambia. En desarrollo y pruebas, `AVACOM_ACTUALIZACION_DIR`
o una carpeta temporal, y además la llave de desarrollo.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from django.conf import settings

from ..aplicacion.base import ConfigActualizacion, Servicios
from ..dominio import catalogos as cat
from .almacen import AlmacenEnCarpeta
from .autorizacion import AutorizacionActualizacion
from .claves import PRODUCCION, ClavesDePublicacion
from .fuentes import FuentesDelNodo
from .provisionales import AulaDelNodo, LicenciaSinRestriccion, MemoriaDelProceso, RelojDelNodo, RespaldoDelHost
from .registro_modulos import RegistroDelNodo, version_del_producto
from .unidad_trabajo import FabricaUoWActualizacion

CARPETA_DE_CLAVES = Path(__file__).resolve().parent.parent / "claves"


def entorno() -> str:
    """El entorno que clasificó `settings` al arrancar (P-12). Si falta, producción: ante la duda, sólo llaves de producción."""
    return str(getattr(settings, "AVACOM_LICENCIA_ENTORNO", PRODUCCION))


def carpeta_de_actualizaciones() -> Path:
    if entorno() == PRODUCCION:
        programdata = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(programdata) / "AVACOM" / "OPS Master" / "Actualizaciones"
    propia = str(getattr(settings, "AVACOM_ACTUALIZACION_DIR", "") or "").strip()
    if propia:
        return Path(propia)
    return Path(tempfile.gettempdir()) / ("avacom-actualizacion-pruebas" if str(getattr(settings, "AVACOM_LMS_ENTORNO", "")) == "pruebas" else "avacom-actualizacion-dev")


def unidades_configuradas() -> list[Path]:
    """Carpetas que hacen de unidad extraíble en desarrollo y pruebas (`AVACOM_ACTUALIZACION_UNIDADES`, separadas por `;`). En producción no hay: las unidades son las reales."""
    if entorno() == PRODUCCION:
        return []
    crudo = str(getattr(settings, "AVACOM_ACTUALIZACION_UNIDADES", "") or "")
    return [Path(p.strip()) for p in crudo.split(";") if p.strip()]


def configuracion() -> ConfigActualizacion:
    max_mb = int(getattr(settings, "AVACOM_ACTUALIZACION_MAX_MB", cat.MAX_PAQUETE_BYTES // cat.MIB))
    return ConfigActualizacion(entorno=entorno(), max_paquete_bytes=min(max(1, max_mb) * cat.MIB, cat.MAX_PAQUETE_BYTES), dias_reversion=cat.DIAS_REVERSION,
                               margen_clase_ms=cat.MARGEN_ANTES_DE_CLASE_MIN * cat.MINUTO_MS, canal=str(getattr(settings, "AVACOM_ACTUALIZACION_CANAL", "") or "").strip(),
                               version_del_nodo=version_del_producto())


_candado = threading.Lock()
_cache: dict[tuple, Servicios] = {}


def servicios() -> Servicios:
    """Los servicios de este nodo. Se cachean por (entorno, carpeta, unidades, base): las pruebas cambian esos valores y reciben una instalación limpia; el nodo, una sola."""
    carpeta = carpeta_de_actualizaciones()
    unidades = unidades_configuradas()
    llave = (entorno(), str(carpeta), tuple(str(u) for u in unidades), str(settings.DATABASES["default"].get("NAME")), settings.BASE_DIR)
    with _candado:
        if llave not in _cache:
            if len(_cache) > 8:
                _cache.clear()
            config = configuracion()
            base = settings.DATABASES["default"].get("NAME")
            _cache[llave] = Servicios(
                uow=FabricaUoWActualizacion(), reloj=RelojDelNodo(), claves=ClavesDePublicacion(CARPETA_DE_CLAVES, entorno()), registro=RegistroDelNodo(),
                fuentes=FuentesDelNodo(carpeta / "entrada", unidades, config.max_paquete_bytes, usar_unidades_reales=entorno() == PRODUCCION),
                almacen=AlmacenEnCarpeta(carpeta, Path(str(base)) if base and str(base) != ":memory:" and not str(base).startswith("file:") else None),
                aula=AulaDelNodo(), licencia=LicenciaSinRestriccion(), respaldo=RespaldoDelHost(), autorizacion=AutorizacionActualizacion(), vivo=MemoriaDelProceso(), config=config)
        return _cache[llave]


def reiniciar() -> None:
    """Para las pruebas: olvida todo lo cacheado."""
    with _candado:
        _cache.clear()
