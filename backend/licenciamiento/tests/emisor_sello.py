"""Llaves de DESARROLLO del sello de dispositivo (derivadas de una semilla pública, como `emisor.py`): sólo las acepta un nodo de desarrollo o de pruebas; el instalador excluye `desarrollo.json`."""
from __future__ import annotations

import hashlib

from licenciamiento.dominio import firma

SEMILLA = b"avacom-sello-desarrollo-v1"
KID_SELLO_DEV_1 = "sello-dev-1"


def clave_privada(kid: str = KID_SELLO_DEV_1) -> bytes:
    return hashlib.sha256(SEMILLA + b"|" + kid.encode("ascii")).digest()


def claves_publicas() -> dict[str, bytes]:
    return {KID_SELLO_DEV_1: firma.publica_de(clave_privada())}
