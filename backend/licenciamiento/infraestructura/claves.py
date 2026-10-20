"""
Las llaves PÚBLICAS que este nodo acepta para verificar licencias (P-03): en el repositorio sólo hay públicas.

  `licenciamiento/claves/produccion.json`   las llaves de producción: la VIGENTE y la SIGUIENTE (≥ 2 para rotar sin dejar a nadie sin clase). Mientras el CTO no haga la ceremonia
                                            de llaves (Q-L3), la lista está VACÍA: un nodo de producción no acepta ninguna licencia y opera en su ventana de evaluación.
  `licenciamiento/claves/desarrollo.json`   la llave de DESARROLLO (`dev-1`, `dev-2`): se acepta SÓLO si el entorno es desarrollo o pruebas por construcción (P-12). El instalador NO la
                                            copia al paquete (una prueba sobre el contenido lo comprueba) y, aunque la copiara, un nodo de producción no la carga.

Formato: `{"version": 1, "claves": [{"kid": "prod-2026-1", "publica": "<64 hexadecimales>", "estado": "vigente|siguiente|retirada"}]}`. Una entrada mal formada o `retirada` se ignora.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("avacom.licenciamiento")

_KID = re.compile(r"^[a-z0-9._-]{1,32}$")
ESTADOS_QUE_VALEN = ("vigente", "siguiente")


def cargar(archivo: Path) -> dict[str, bytes]:
    if not archivo.is_file():
        return {}
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        log.exception("El archivo de llaves públicas %s no se pudo leer", archivo.name, extra={"evento": "licencia.claves_ilegibles", "ruta": "bad"})
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


class ClavesPublicas:
    def __init__(self, carpeta: Path, entorno: str):
        self._carpeta, self._entorno = Path(carpeta), entorno
        self._cache: dict[str, bytes] | None = None

    def publicas(self) -> dict[str, bytes]:
        if self._cache is None:
            claves = cargar(self._carpeta / "produccion.json")
            if self._entorno != "produccion":
                claves = {**cargar(self._carpeta / "desarrollo.json"), **claves}
            self._cache = claves
        return dict(self._cache)
