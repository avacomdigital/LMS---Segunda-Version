"""
El emisor de PASES DE SOPORTE de PRUEBAS: llaves de desarrollo derivadas de una semilla PÚBLICA (cualquiera puede firmar con ellas, y por eso el nodo SÓLO acepta `claves/desarrollo.json`
en desarrollo y pruebas, nunca en producción). El emisor REAL de AVACOM vive en `tools/respaldo/` y usa la llave privada de producción, que NO está en el repositorio.
"""
from __future__ import annotations

import base64
import hashlib
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from respaldo.dominio import pase as dominio_pase

SEMILLA = b"avacom-respaldo-soporte-semilla-publica-de-pruebas"


def llave_privada(indice: int = 1) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(SEMILLA + str(indice).encode()).digest())


def publica_hex(indice: int = 1) -> str:
    from cryptography.hazmat.primitives import serialization
    return llave_privada(indice).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def emitir(acciones, ahora_ms: int, *, tecnico: str = "Soporte AVACOM", nodo: str = "*", horas: float = 4, pase_id: str | None = None, indice: int = 1, kid: str | None = None,
           emitido_en: int | None = None, vence_en: int | None = None) -> bytes:
    emitido = ahora_ms if emitido_en is None else emitido_en
    payload = {"pase_id": pase_id or str(uuid.uuid4()), "tecnico": tecnico, "emitido_en": emitido, "vence_en": emitido + int(horas * 3_600_000) if vence_en is None else vence_en,
               "acciones": list(acciones), "nodo": nodo, "motivo": "prueba"}
    return dominio_pase.firmar(payload, kid or f"sop-dev-{indice}", llave_privada(indice))


def emitir_b64(*args, **kwargs) -> str:
    return base64.b64encode(emitir(*args, **kwargs)).decode("ascii")
