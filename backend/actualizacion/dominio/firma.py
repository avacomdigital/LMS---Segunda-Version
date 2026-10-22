"""
La firma de un paquete `.avupd` (P-02, P-03): Ed25519 (RFC 8032) con `cryptography`, que ya viaja en el runtime del nodo.

  · El algoritmo está FIJADO: no hay un campo `alg`. El `kid` elige entre las llaves públicas de PUBLICACIÓN que el nodo conoce (≥ 2 en producción: la vigente y la siguiente).
    Son llaves distintas de las de licencias (Q-U8): otra ceremonia, otro `kid`.
  · `manifiesto.firma` =  magic `AVUP` · versión (u16, orden de red) · largo del kid (u8) · kid · firma (64 bytes). Nada más: un byte de más o de menos es `firma_formato`.
  · La firma cubre la cabecera (magic, versión y kid) Y los bytes EXACTOS de `manifiesto.json`: nadie puede «degradar» un paquete cambiando la versión de la firma o el kid, y el
    manifiesto se verifica antes de interpretar un solo campo suyo.

`verificar` nunca lanza: una llave mal formada o una firma que no cuadra es simplemente «no».
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import catalogos as cat
from .errores import rechazo

_KID = re.compile(rb"^[a-z0-9._-]{1,32}$")
_CABECERA = struct.Struct(">4sHB")        # magic, versión, largo del kid


def verificar(clave_publica: bytes, firma: bytes, mensaje: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes(clave_publica)).verify(bytes(firma), bytes(mensaje))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def firmar(clave_privada: bytes, mensaje: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(bytes(clave_privada)).sign(bytes(mensaje))


def par_nuevo() -> tuple[bytes, bytes]:
    """`(privada, pública)` de 32 bytes cada una. Las de publicación se generan FUERA del nodo (tools/actualizacion); esto lo usan las pruebas."""
    privada = Ed25519PrivateKey.generate()
    return (privada.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()),
            privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def publica_de(clave_privada: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(bytes(clave_privada)).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


@dataclass(frozen=True)
class Firma:
    version: int
    kid: str
    firma: bytes


def cabecera(kid: str, version: int = cat.VERSION_FIRMA) -> bytes:
    kid_b = kid.encode("ascii")
    return _CABECERA.pack(cat.MAGIC, version, len(kid_b)) + kid_b


def mensaje_firmado(kid: str, manifiesto: bytes, version: int = cat.VERSION_FIRMA) -> bytes:
    """Lo que se firma: la cabecera y los bytes exactos del manifiesto."""
    return cabecera(kid, version) + bytes(manifiesto)


def escribir(kid: str, firma: bytes, version: int = cat.VERSION_FIRMA) -> bytes:
    """El contenido de `manifiesto.firma`."""
    if len(firma) != cat.TAM_FIRMA:
        raise ValueError("la firma Ed25519 mide 64 bytes")
    return cabecera(kid, version) + bytes(firma)


def leer(datos: bytes) -> Firma:
    """La cabecera de `manifiesto.firma`, sin verificar nada todavía (hace falta el kid para saber con qué llave). Rechaza lo que no tenga la forma exacta."""
    datos = bytes(datos)
    if len(datos) < _CABECERA.size + 1 + cat.TAM_FIRMA:
        raise rechazo("firma_formato")
    magic, version, largo_kid = _CABECERA.unpack_from(datos, 0)
    if magic != cat.MAGIC:
        raise rechazo("firma_formato")
    if version != cat.VERSION_FIRMA:
        raise rechazo("version_firma_desconocida")
    if largo_kid == 0 or largo_kid > cat.MAX_KID:
        raise rechazo("kid_invalido")
    inicio_kid = _CABECERA.size
    kid = datos[inicio_kid:inicio_kid + largo_kid]
    if len(kid) != largo_kid or not _KID.match(kid):
        raise rechazo("kid_invalido")
    firma = datos[inicio_kid + largo_kid:]
    if len(firma) != cat.TAM_FIRMA:
        raise rechazo("firma_formato")
    return Firma(version, kid.decode("ascii"), firma)


def sellar(kid: str, clave_privada: bytes, manifiesto: bytes) -> bytes:
    """Para el emisor: `manifiesto.firma` de ese manifiesto con esa llave."""
    return escribir(kid, firmar(clave_privada, mensaje_firmado(kid, manifiesto)))
