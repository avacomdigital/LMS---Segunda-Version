"""
Lo instalado (P-01, P-04, D-3): el registro de módulos de `avacom_lms/modulos.json`, la versión de DATOS viva de cada app (el número de su última migración aplicada, de
`django_migrations`), la versión del producto (`AVACOM_LMS_VERSION`, el `manifiesto.json` del instalador o `installer/version.json`) y el contrato que este LMS habla con AVACOM
Biblioteca (se LEE de `biblioteca.contenido_v2.CONTRATO` y nada más; R-12).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from ..dominio import registro as dom
from ..dominio import version as ver
from ..dominio.errores import DatosInvalidos

log = logging.getLogger("avacom.actualizacion")
ARCHIVO_REGISTRO = "modulos.json"


def ruta_del_registro() -> Path:
    return Path(settings.BASE_DIR) / "avacom_lms" / ARCHIVO_REGISTRO


def version_del_producto() -> str:
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
    return "0.0.0"


def contrato_de_la_biblioteca() -> int:
    try:
        from biblioteca.contenido_v2 import CONTRATO      # sólo se LEE la constante (R-12)
        return int(CONTRATO)
    except Exception:   # noqa: BLE001
        return 2


def versiones_de_datos() -> dict[str, int]:
    """{app: número de la última migración aplicada}."""
    salida: dict[str, int] = {}
    try:
        for app, nombre in MigrationRecorder(connection).applied_migrations():
            salida[app] = max(salida.get(app, 0), ver.numero_de_migracion(nombre))
    except Exception:   # noqa: BLE001 — sin tabla de migraciones (una base recién creada) no hay versión de datos
        log.exception("No se pudieron leer las migraciones aplicadas", extra={"evento": "actualizacion.migraciones_ilegibles", "ruta": "bad"})
    return salida


class RegistroDelNodo:
    def __init__(self, ruta: Path | None = None):
        self._ruta = Path(ruta) if ruta else None
        self._cache: dict[str, dom.ModuloRegistrado] | None = None

    def registrados(self) -> dict[str, dom.ModuloRegistrado]:
        if self._cache is None:
            ruta = self._ruta or ruta_del_registro()
            try:
                self._cache = dom.leer(json.loads(ruta.read_text(encoding="utf-8-sig")))
            except (OSError, ValueError) as error:
                raise DatosInvalidos(f"El registro de módulos ({ruta.name}) no se puede leer.") from error
        return self._cache

    def instalacion(self) -> dom.Instalacion:
        datos = versiones_de_datos()
        modulos = {nombre: dom.instalado(m, datos.get(nombre, 0)) for nombre, m in self.registrados().items()}
        return dom.Instalacion(version_producto=version_del_producto(), contrato_biblioteca=contrato_de_la_biblioteca(), modulos=modulos)
