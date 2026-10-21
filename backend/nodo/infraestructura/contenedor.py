r"""
Composition root de MOD-015: qué adaptador va con qué puerto, de dónde salen los parámetros (`AVACOM_NODO_*`) y dónde viven las anclas.

CARPETA DE ANCLAS: en producción (el entorno que clasificó `settings.AVACOM_LICENCIA_ENTORNO` al arrancar) SIEMPRE `%ProgramData%\AVACOM\OPS Master\Config\nodo\`; en desarrollo,
`AVACOM_NODO_DIR` o `%TEMP%\avacom-nodo-dev`; en pruebas, la carpeta que fije cada prueba (siempre temporal: jamás ProgramData).

RELOJ: UN solo reloj del nodo (INV-017): el mismo `RelojNodo` de la evaluación que usan el libro, los reportes y la licencia (lo que una prueba mueve, mueve aquí). La marca alta se le
pone encima en `Servicios.ahora_ms` (P-13); la unificación de las seis copias es de la Fase 6.

`servicios()` está en el camino de CADA `publicar` (R-08): la llave de la caché sale de unas pocas lecturas de `settings`; la configuración completa (con la versión del nodo, que lee
un archivo) sólo se arma cuando hay que crear los servicios.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from django.conf import settings

from evaluacion.infraestructura.contenedor import RelojNodo      # UN solo reloj del nodo (INV-017)

from ..aplicacion.base import ConfigNodo, Servicios
from ..aplicacion.puertos import LectorLegado
from ..dominio import catalogos as cat
from ..dominio.estado import Umbrales
from .anclas import AnclasEnCarpeta
from .autorizacion import AutorizacionNodo
from .contexto import ContextoDeAuditoria
from .respaldo import RespaldoAusente, SincronizacionAusente
from .salud import SaludDelEquipo
from .unidad_trabajo import FabricaUoWNodo


class RelojDelNodo:
    def ahora_ms(self) -> int:
        return RelojNodo().ahora_ms()


def entorno() -> str:
    return str(getattr(settings, "AVACOM_LMS_ENTORNO", "desarrollo"))


def en_produccion() -> bool:
    return str(getattr(settings, "AVACOM_LICENCIA_ENTORNO", "produccion")) == "produccion"


def carpeta_de_anclas() -> Path:
    if en_produccion():
        programdata = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(programdata) / "AVACOM" / "OPS Master" / "Config" / "nodo"
    propia = str(getattr(settings, "AVACOM_NODO_DIR", "") or "").strip()
    if propia:
        return Path(propia)
    return Path(tempfile.gettempdir()) / ("avacom-nodo-pruebas" if entorno() == "pruebas" else "avacom-nodo-dev")


_version: str | None = None


def version_del_nodo() -> str:
    """La versión del producto que corre en este nodo: `AVACOM_LMS_VERSION`, el `manifiesto.json` del instalador, `installer/version.json` o «desarrollo». Se lee una vez por proceso."""
    global _version
    if _version is not None:
        return _version
    configurada = str(getattr(settings, "AVACOM_LMS_VERSION", "") or os.environ.get("AVACOM_LMS_VERSION", "")).strip()
    if configurada:
        _version = configurada
        return _version
    import json
    raiz = Path(settings.BASE_DIR).parent
    for ruta in (raiz / "manifiesto.json", raiz / "installer" / "version.json"):
        try:
            version = str(json.loads(ruta.read_text(encoding="utf-8-sig")).get("version") or "").strip()
        except Exception:   # noqa: BLE001 — la versión es un rótulo, no un requisito
            continue
        if version:
            _version = version
            return _version
    _version = "desarrollo"
    return _version


_LLAVES = ("AVACOM_NODO_ESTRICTO", "AVACOM_NODO_EVENTOS_TECNICOS", "AVACOM_NODO_PURGA", "AVACOM_NODO_MAX_INTENTOS", "AVACOM_NODO_LOTE", "AVACOM_NODO_REZAGO_LIMITE",
           "AVACOM_NODO_ANCLA_CADA_EVENTOS", "AVACOM_NODO_ANCLA_CADA_MS", "AVACOM_NODO_CONSUMIDORES_NUCLEO", "AVACOM_LMS_EXIGIR_SESION")


def configuracion() -> ConfigNodo:
    g = lambda nombre, defecto: getattr(settings, nombre, defecto)      # noqa: E731
    return ConfigNodo(
        estricto=bool(g("AVACOM_NODO_ESTRICTO", entorno() != "instalado")),
        lote=int(g("AVACOM_NODO_LOTE", cat.LOTE_DE_EVENTOS)),
        max_intentos=int(g("AVACOM_NODO_MAX_INTENTOS", cat.MAX_INTENTOS)),
        espera_base_ms=int(g("AVACOM_NODO_ESPERA_BASE_MS", cat.ESPERA_BASE_MS)),
        espera_tope_ms=int(g("AVACOM_NODO_ESPERA_TOPE_MS", cat.ESPERA_TOPE_MS)),
        rezago_limite=int(g("AVACOM_NODO_REZAGO_LIMITE", cat.REZAGO_LIMITE)),
        ciclo_meses=int(g("AVACOM_NODO_CICLO_MESES", cat.CICLO_MESES_POR_DEFECTO)),
        retencion_minima_dias=int(g("AVACOM_NODO_RETENCION_MIN_DIAS", cat.RETENCION_MINIMA_DIAS)),
        purga_habilitada=bool(g("AVACOM_NODO_PURGA", False)),
        eventos_tecnicos=bool(g("AVACOM_NODO_EVENTOS_TECNICOS", True)),
        margen_secuencia=int(g("AVACOM_NODO_MARGEN_SECUENCIA", cat.MARGEN_SECUENCIA)),
        ancla_cada_ms=int(g("AVACOM_NODO_ANCLA_CADA_MS", cat.ANCLA_CADA_MS)),
        ancla_cada_eventos=int(g("AVACOM_NODO_ANCLA_CADA_EVENTOS", cat.ANCLA_CADA_EVENTOS)),
        umbrales=Umbrales(disco_min_bytes=int(float(g("AVACOM_NODO_DISCO_MIN_GB", 2)) * 1024 ** 3), disco_min_pct=float(g("AVACOM_NODO_DISCO_MIN_PCT", cat.DISCO_MIN_PCT)),
                          wal_max_bytes=int(float(g("AVACOM_NODO_WAL_MAX_MB", 512)) * 1024 ** 2)),
        consumidores_nucleo=tuple(g("AVACOM_NODO_CONSUMIDORES_NUCLEO", ())),
        version_del_nodo=version_del_nodo(),
    )


_candado = threading.Lock()
_cache: dict[tuple, Servicios] = {}
# Módulo cortado → el lector de su tabla antigua (P-05, R-09). Vive FUERA de la caché: cada módulo se registra UNA vez por proceso (su `apps.ready`), y `reiniciar()` —que las pruebas
# llaman antes de cada prueba— no puede olvidarlo. Cada `Servicios` nuevo nace con una copia, así que lo que una prueba borre de `s.legados` no toca el registro.
_lectores_legados: dict[str, LectorLegado] = {}


def registrar_lector_legado(modulo: str, lector: LectorLegado) -> None:
    with _candado:
        _lectores_legados[modulo] = lector
        for servicios_ in _cache.values():
            servicios_.legados[modulo] = lector


def servicios() -> Servicios:
    """Los servicios de este nodo. Se cachean por (carpeta de anclas, las variables que cambian el comportamiento, base): las pruebas cambian esos valores y reciben una instalación
    limpia; el nodo, una sola."""
    llave = (str(carpeta_de_anclas()), str(settings.DATABASES["default"].get("NAME")), *(repr(getattr(settings, nombre, None)) for nombre in _LLAVES))
    servicios_ = _cache.get(llave)
    if servicios_ is not None:
        return servicios_
    with _candado:
        if llave not in _cache:
            if len(_cache) > 8:
                _cache.clear()
            carpeta = carpeta_de_anclas()
            _cache[llave] = Servicios(uow=FabricaUoWNodo(), reloj=RelojDelNodo(), contexto=ContextoDeAuditoria(), anclas=AnclasEnCarpeta(carpeta), autorizacion=AutorizacionNodo(),
                                      respaldo=RespaldoAusente(), sincronizacion=SincronizacionAusente(), salud=SaludDelEquipo(), config=configuracion(),
                                      legados=dict(_lectores_legados))
        return _cache[llave]


def reiniciar() -> None:
    """Para las pruebas: olvida todo lo cacheado (el estado vivo incluido)."""
    with _candado:
        _cache.clear()
