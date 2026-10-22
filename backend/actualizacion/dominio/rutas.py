"""
Rutas seguras dentro de un paquete (A3, R-07): relativas, con `/`, sin `..`, sin letra de unidad, sin nombres reservados de Windows, con extensiones de código o datos, y
SÓLO dentro de las apps que el paquete declara (más el registro de módulos). `backend/biblioteca/` es intocable (R-12). Puro.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from . import catalogos as cat
from .errores import rechazo

_COMPONENTE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_LETRA_DE_UNIDAD = re.compile(r"^[A-Za-z]:")
_RESERVADOS = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))})
_PROHIBIDOS = frozenset({"__pycache__"})


def validar(ruta) -> str:
    """La ruta tal cual si es segura; si no, el rechazo con su motivo."""
    if not isinstance(ruta, str) or not ruta or len(ruta) > cat.MAX_RUTA or "\\" in ruta or "\0" in ruta or ruta != ruta.strip():
        raise rechazo("ruta_invalida")
    if ruta.startswith("/") or _LETRA_DE_UNIDAD.match(ruta):
        raise rechazo("ruta_absoluta")
    partes = ruta.split("/")
    for parte in partes:
        if parte == "..":
            raise rechazo("ruta_con_retroceso")
        if parte in ("", ".") or parte in _PROHIBIDOS or len(parte) > cat.MAX_COMPONENTE or not _COMPONENTE.match(parte) or parte.endswith("."):
            raise rechazo("ruta_invalida")
        if parte.split(".")[0].upper() in _RESERVADOS:
            raise rechazo("ruta_invalida")
    nombre = partes[-1]
    punto = nombre.rfind(".")
    extension = nombre[punto:].lower() if punto > 0 else ""
    if extension not in cat.EXTENSIONES_PERMITIDAS:
        raise rechazo("extension_prohibida")
    return ruta


def exigir_dentro_de(ruta: str, modulos: Iterable[str]) -> None:
    """R-07: un paquete de módulo sólo trae archivos de las apps que declara y, como mucho, el registro de módulos. Nunca `biblioteca/` ni nada fuera de `backend/`."""
    partes = ruta.split("/")
    if partes[0] in cat.APPS_INTOCABLES:
        raise rechazo("ruta_intocable")
    if ruta in cat.RUTAS_PERMITIDAS_FUERA_DE_APP:
        return
    if len(partes) < 2 or partes[0] not in set(modulos):
        raise rechazo("ruta_fuera_del_modulo")
