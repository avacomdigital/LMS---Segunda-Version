r"""
Composition root de MOD-018: qué adaptador va con qué puerto, en qué modo corre este nodo y dónde guarda su estado.

MODO (R-05, P-12)
  · `firmada`    el adaptador de producción: verifica licencias firmadas y aplica el estado (`proveedores.LicenciaFirmada`)
  · `ilimitada`  el de desarrollo y pruebas: nada se restringe y las ≈1944 pruebas existentes corren sin licencia (`proveedores.LicenciaIlimitada`)

  Un nodo de PRODUCCIÓN (el marcador de canal que escribe el instalador, o `Program Files`, o `AVACOM_LMS_ENTORNO=instalado`; ver `dominio/entorno.py`) usa SIEMPRE `firmada`:
  NINGUNA variable de `backend.env` lo cambia. En desarrollo y pruebas `AVACOM_LICENCIA_MODO=firmada` fuerza la verificación real (así se prueba y se ve en vivo); jamás hay una
  variable que fuerce `ilimitada` en un nodo de producción, porque esa decisión no sale de ninguna variable.

CARPETA DE ESTADO: en producción, SIEMPRE `%ProgramData%\AVACOM\OPS Master\Config\licencia\` (una variable de entorno no puede mover el estado a otra carpeta vacía y reiniciar la ventana
de evaluación); en desarrollo y pruebas, `AVACOM_LICENCIA_DIR` o una carpeta temporal.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from django.conf import settings

from evaluacion.infraestructura.contenedor import RelojNodo      # UN solo reloj del nodo (INV-017): el mismo que usan la evaluación, el libro y los reportes

from ..aplicacion.base import ConfigLicencia, Servicios
from ..dominio import entorno as ent
from ..dominio.politica import POLITICA_PROVISIONAL
from .almacen import AlmacenEnCarpeta
from .anclas import AnclasDeLicencia, RegistroDeWindows
from .autorizacion import AutorizacionLicencia
from .claves import ClavesPublicas
from .conteos import ConteosDeLosDuenos
from .huella_windows import HuellaDeWindows
from .nodo import NodoDeLicencia
from .proteccion import ProtectorAutomatico
from .unidad_trabajo import FabricaUoWLicencia
from .vivo import EstadoVivo

FIRMADA, ILIMITADA = "firmada", "ilimitada"
CARPETA_DE_CLAVES = Path(__file__).resolve().parent.parent / "claves"


class RelojDelNodo:
    """El reloj del nodo (el mismo de los demás módulos: lo que una prueba mueve, mueve aquí) y un reloj monótono que no se cambia desde el reloj del sistema."""

    def ahora_ms(self) -> int:
        return RelojNodo().ahora_ms()

    def monotono_ms(self) -> int:
        return int(time.monotonic() * 1000)


def entorno() -> str:
    """El entorno que clasificó `settings` al arrancar (P-12). Si falta, producción: ante la duda, se licencia."""
    return str(getattr(settings, "AVACOM_LICENCIA_ENTORNO", ent.PRODUCCION))


def modo() -> str:
    if entorno() == ent.PRODUCCION:
        return FIRMADA
    return FIRMADA if str(getattr(settings, "AVACOM_LICENCIA_MODO", "auto")).strip().lower() == FIRMADA else ILIMITADA


def carpeta_de_estado() -> Path:
    if entorno() == ent.PRODUCCION:
        programdata = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(programdata) / "AVACOM" / "OPS Master" / "Config" / "licencia"
    propia = str(getattr(settings, "AVACOM_LICENCIA_DIR", "") or "").strip()
    return Path(propia) if propia else Path(tempfile.gettempdir()) / "avacom-licencia-dev"


def version_del_nodo() -> str:
    """La versión del producto para los asientos y las solicitudes: `AVACOM_LMS_VERSION`, el `manifiesto.json` del instalador, `installer/version.json` o «desarrollo»."""
    configurada = str(getattr(settings, "AVACOM_LMS_VERSION", "") or os.environ.get("AVACOM_LMS_VERSION", "")).strip()
    if configurada:
        return configurada
    raiz = Path(settings.BASE_DIR).parent
    for ruta in (raiz / "manifiesto.json", raiz / "installer" / "version.json"):
        try:
            version = str(json.loads(ruta.read_text(encoding="utf-8-sig")).get("version") or "").strip()
        except Exception:   # noqa: BLE001 — la versión es un rótulo, no un requisito
            continue
        if version:
            return version
    return "desarrollo"


def configuracion() -> ConfigLicencia:
    return ConfigLicencia(politica=POLITICA_PROVISIONAL, entorno=entorno(), modo=modo(), version_del_nodo=version_del_nodo(),
                          concurrencia_normal=int(getattr(settings, "AVACOM_AULA_DISPOSITIVOS_NORMAL", 50)), concurrencia_pico=int(getattr(settings, "AVACOM_AULA_DISPOSITIVOS_PICO", 100)))


_candado = threading.Lock()
_cache: dict[tuple, Servicios] = {}


def servicios() -> Servicios:
    """Los servicios de este nodo. Se cachean por (entorno, modo, carpeta de estado): las pruebas cambian esos valores y reciben una instalación limpia; el nodo, una sola."""
    carpeta = carpeta_de_estado()
    llave = (entorno(), modo(), str(carpeta), settings.BASE_DIR)
    with _candado:
        if llave not in _cache:
            almacen = AlmacenEnCarpeta(carpeta)
            nodo = NodoDeLicencia(almacen, ProtectorAutomatico())
            en_produccion = entorno() == ent.PRODUCCION
            if len(_cache) > 8:
                _cache.clear()
            _cache[llave] = Servicios(
                uow=FabricaUoWLicencia(), reloj=RelojDelNodo(), huella=HuellaDeWindows(), nodo=nodo, anclas=AnclasDeLicencia(almacen, nodo, RegistroDeWindows() if en_produccion and os.name == "nt" else None),
                almacen=almacen, claves=ClavesPublicas(CARPETA_DE_CLAVES, entorno()), conteos=ConteosDeLosDuenos(), autorizacion=AutorizacionLicencia(), vivo=EstadoVivo(),
                config=configuracion())
        return _cache[llave]


def reiniciar() -> None:
    """Para las pruebas: olvida todo lo cacheado."""
    with _candado:
        _cache.clear()
