"""
La criptografía de un respaldo (BR-102, INV-021): AES-256-GCM con `cryptography`, que ya viaja en el runtime del nodo (sin dependencias nuevas).

  · Cada respaldo tiene su PROPIA clave de datos (DEK, 32 bytes al azar). Nunca se reutiliza.
  · La DEK se guarda ENVUELTA en el manifiesto, dos veces: con la clave del nodo (KEK del equipo: restaura en este equipo sin pedir nada) y con la clave de CUSTODIA derivada del código
    que la institución guarda (restaura en otro equipo: BR-102). Sin ninguna de las dos el respaldo es ilegible, también para el técnico.
  · El contenido va en trozos de 1 MiB, cada uno con su etiqueta GCM. El nonce es un prefijo al azar de 4 bytes más el contador del trozo, y la AAD ata el trozo al archivo, a su
    posición y a si es el último: reordenar, repetir, truncar o mezclar trozos de otro respaldo se detecta SIN descifrar nada más.

Puro: no importa Django.
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LARGO_CLAVE = 32
LARGO_NONCE = 12
LARGO_PREFIJO = 4
LARGO_SECRETO_CUSTODIA = 20
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
_MAXMEM = 128 * 1024 * 1024


class ClaveIncorrecta(Exception):
    """La clave no abre lo que se envolvió con ella."""


class TrozoAlterado(Exception):
    """La etiqueta de un trozo no cuadra: el contenido cambió, falta o está en otra posición."""


def generar_clave() -> bytes:
    return os.urandom(LARGO_CLAVE)


def kid(clave: bytes) -> str:
    """Un identificador corto y público de una clave (no la revela): qué clave del equipo envolvió una DEK."""
    return hashlib.sha256(b"avbak-kid" + bytes(clave)).digest()[:8].hex()


# ------------------------------------------------------------------------------------------------------------------- código de custodia
def generar_codigo_de_custodia() -> str:
    """El código que la institución guarda: 20 bytes al azar + 1 de control, en base32 y en grupos de cinco (`XXXXX-XXXXX-…`, 34 caracteres sin los guiones). Se muestra UNA vez."""
    secreto = os.urandom(LARGO_SECRETO_CUSTODIA)
    return _formatear(secreto + _control(secreto))


def _control(secreto: bytes) -> bytes:
    return hashlib.sha256(b"avbak-custodia" + secreto).digest()[:1]


def _formatear(crudo: bytes) -> str:
    texto = base64.b32encode(crudo).decode("ascii").rstrip("=")
    return "-".join(texto[i:i + 5] for i in range(0, len(texto), 5))


def secreto_de_custodia(codigo: str) -> bytes | None:
    """Los 20 bytes del código, o None si el texto no es un código válido (alfabeto, largo o dígito de control). Tolera minúsculas, espacios y guiones de más."""
    limpio = "".join(c for c in str(codigo or "").upper() if c.isalnum())
    limpio = limpio.replace("0", "O").replace("1", "I").replace("8", "B")      # los tres caracteres que se confunden al copiar a mano (el alfabeto base32 no los usa)
    if len(limpio) != 34:
        return None
    try:
        crudo = base64.b32decode(limpio + "=" * 6)
    except ValueError:
        return None
    secreto, control = crudo[:LARGO_SECRETO_CUSTODIA], crudo[LARGO_SECRETO_CUSTODIA:]
    return secreto if control == _control(secreto) else None


def generar_sal() -> bytes:
    return os.urandom(16)


def clave_de_custodia(secreto: bytes, sal: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    return hashlib.scrypt(bytes(secreto), salt=bytes(sal), n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM, dklen=LARGO_CLAVE)


# ------------------------------------------------------------------------------------------------------------------- envolver una clave con otra
def envolver(kek: bytes, dek: bytes, aad: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(LARGO_NONCE)
    return nonce, AESGCM(bytes(kek)).encrypt(nonce, bytes(dek), bytes(aad))


def desenvolver(kek: bytes, nonce: bytes, envuelta: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(bytes(kek)).decrypt(bytes(nonce), bytes(envuelta), bytes(aad))
    except InvalidTag as error:
        raise ClaveIncorrecta("La clave no abre la clave de datos del respaldo.") from error


# ------------------------------------------------------------------------------------------------------------------- el flujo en trozos
def _nonce(prefijo: bytes, contador: int) -> bytes:
    return bytes(prefijo) + struct.pack(">Q", contador)


def _aad(base: bytes, contador: int, ultimo: bool) -> bytes:
    return bytes(base) + struct.pack(">Q", contador) + (b"\x01" if ultimo else b"\x00")


def cifrar_trozo(dek: bytes, prefijo: bytes, aad_base: bytes, contador: int, datos: bytes, ultimo: bool) -> bytes:
    return AESGCM(bytes(dek)).encrypt(_nonce(prefijo, contador), bytes(datos), _aad(aad_base, contador, ultimo))


def descifrar_trozo(dek: bytes, prefijo: bytes, aad_base: bytes, contador: int, cifrado: bytes, ultimo: bool) -> bytes:
    try:
        return AESGCM(bytes(dek)).decrypt(_nonce(prefijo, contador), bytes(cifrado), _aad(aad_base, contador, ultimo))
    except InvalidTag as error:
        raise TrozoAlterado(f"El trozo {contador} no pasa la verificación.") from error
