"""
Las llaves PÚBLICAS de PUBLICACIÓN que este nodo acepta para verificar paquetes (P-03, Q-U8): en el repositorio sólo hay públicas. Son llaves DISTINTAS de las de licencias.

  `actualizacion/claves/produccion.json`   la VIGENTE y la SIGUIENTE (≥ 2 para rotar sin dejar a nadie sin actualizaciones). Mientras el CTO no haga la ceremonia de llaves, la lista está
                                           VACÍA: un nodo de producción no acepta ningún paquete (y lo dice con `kid_desconocido`).
  `actualizacion/claves/desarrollo.json`   la llave de DESARROLLO (`upd-dev-1`, `upd-dev-2`): sólo si el entorno es desarrollo o pruebas por construcción (P-12 de MOD-018). El instalador
                                           NO debe copiarla al paquete (Fase 4: añadirla a las exclusiones de `Build-Installer.ps1`) y, aunque la copiara, un nodo de producción no la carga.

Formato: `{"version": 1, "claves": [{"kid": "upd-2026-1", "publica": "<64 hexadecimales>", "estado": "vigente|siguiente|retirada"}]}`. Una entrada mal formada o `retirada` se ignora.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("avacom.actualizacion")

_KID = re.compile(r"^[a-z0-9._-]{1,32}$")
ESTADOS_QUE_VALEN = ("vigente", "siguiente")
PRODUCCION = "produccion"


def cargar(archivo: Path) -> dict[str, bytes]:
    if not archivo.is_file():
        return {}
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        log.exception("El archivo de llaves de publicación %s no se pudo leer", archivo.name, extra={"evento": "actualizacion.claves_ilegibles", "ruta": "bad"})
        return {}
    salida: dict[str, bytes] = {}
    for entrada in datos.get("claves", []) if isinstance(datos, dict) else []:
        try:
            kid, estado = str(entrada["kid"]), str(entrada.get("estado", "vigente"))
            publica = bytes.fromhex(str(entrada["publica"]))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if _KID.match(kid) and len(publica) == 32 and estado in ESTADOS_QUE_VALEN:
            salida[kid] = publica
    return salida


class ClavesDePublicacion:
    def __init__(self, carpeta: Path, entorno: str):
        self._carpeta, self._entorno = Path(carpeta), entorno
        self._cache: dict[str, bytes] | None = None

    def publicas(self) -> dict[str, bytes]:
        if self._cache is None:
            claves = cargar(self._carpeta / "produccion.json")
            if self._entorno != PRODUCCION:
                claves = {**cargar(self._carpeta / "desarrollo.json"), **claves}
            self._cache = claves
        return dict(self._cache)
