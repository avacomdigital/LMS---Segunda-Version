"""Composition root de MOD-013: qué adaptador va con qué puerto y cómo se leen los parámetros de la instalación."""
from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from evaluacion.infraestructura.contenedor import RelojNodo      # MOD-015 · BR-062: UN solo reloj del nodo, el mismo de la evaluación y el libro

from ..aplicacion.base import ConfigReporting, Servicios
from .archivos import EscritorDeArchivos
from .autorizacion import AutorizacionReporting
from .unidad_trabajo import FabricaUoWReporting


class RelojReporting:
    """El reloj del nodo (el mismo que en el resto de los módulos: lo que una prueba mueve, mueve aquí) y su zona horaria, para que el nombre y la cabecera del archivo hablen en hora local."""

    def ahora_ms(self) -> int:
        return RelojNodo().ahora_ms()

    def a_local(self, ms: int):
        from datetime import datetime
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.get_current_timezone())


def version_del_nodo() -> str:
    """
    La versión del producto que corre en este nodo, para la cabecera de cada archivo exportado (BR-083). En orden: `AVACOM_LMS_VERSION` si alguien la fija a propósito; el
    `manifiesto.json` que el instalador deja junto a la carpeta Backend (así lo sabe un nodo INSTALADO); `installer/version.json` (en desarrollo); y «desarrollo» si no hay nada de eso.
    """
    configurada = str(getattr(settings, "AVACOM_LMS_VERSION", "") or os.environ.get("AVACOM_LMS_VERSION", "")).strip()
    if configurada:
        return configurada
    import json
    raiz = Path(settings.BASE_DIR).parent
    for ruta in (raiz / "manifiesto.json", raiz / "installer" / "version.json"):
        try:
            version = str(json.loads(ruta.read_text(encoding="utf-8-sig")).get("version") or "").strip()
        except Exception:   # noqa: BLE001 — la versión es una cabecera, no un requisito
            continue
        if version:
            return version
    return "desarrollo"


def configuracion() -> ConfigReporting:
    """Los topes salen de `settings` (variables AVACOM_REPORTES_*)."""
    return ConfigReporting(
        sincronizar_al_consultar=bool(getattr(settings, "AVACOM_REPORTES_SINCRONIZAR", True)),
        ttl_exportacion_ms=int(getattr(settings, "AVACOM_REPORTES_EXPORTACION_TTL_S", 900)) * 1000,
        version_del_nodo=version_del_nodo(),
    )


def servicios() -> Servicios:
    return Servicios(uow=FabricaUoWReporting(), reloj=RelojReporting(), autorizacion=AutorizacionReporting(), escritor=EscritorDeArchivos(), config=configuracion())
