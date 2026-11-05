"""
Firma y verificación de los archivos de licenciamiento: Ed25519 (RFC 8032) con `cryptography`, que ya viaja en el runtime del nodo (sin dependencias nuevas).

  · El algoritmo está fijado. No existe un campo `alg`.
  · `abrir` verifica la firma ANTES de interpretar ningún campo (`tlv.leer_campos`): un archivo alterado se rechaza sin haber mirado lo que dice.
  · El `kid` de la cabecera elige entre las llaves públicas que el nodo conoce (≥ 2 en producción: la vigente y la siguiente, para rotar sin dejar a nadie sin clase). Un
    archivo firmado por el propio nodo (solicitud, liberación) lleva su llave pública en hexadecimal como `kid`: se verifica contra sí mismo.
  · El verificador se puede sustituir (`verificador=`): la biblioteca nativa de la Fase 4 entrará por ahí, y la de referencia (ésta) sigue siendo la de respaldo.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import tlv
from .errores import LicenciaInvalida

Verificador = Callable[[bytes, bytes, bytes], bool]       # (clave pública de 32 bytes, firma de 64, mensaje) → ¿válida?


_P = 2**255 - 19
# Las coordenadas y de los puntos de ORDEN PEQUEÑO de Ed25519: 0, 1, p-1, las dos de orden 8 y las codificaciones no canónicas p y p+1 (D-33).
_Y_DE_ORDEN_PEQUENO = frozenset({0, 1, _P - 1, _P, _P + 1,
                                 int.from_bytes(bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"), "little"),
                                 int.from_bytes(bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"), "little")})


def tiene_orden_pequeno(codificado: bytes) -> bool:
    """¿Esta codificación de punto (llave pública o `R` de una firma) es de orden pequeño? Con el bit de signo o sin él."""
    return (int.from_bytes(bytes(codificado), "little") & ((1 << 255) - 1)) in _Y_DE_ORDEN_PEQUENO


def verificar_referencia(clave_publica: bytes, firma: bytes, mensaje: bytes) -> bool:
    """
    La verificación de referencia (`cryptography`). Nunca lanza: una llave mal formada o una firma que no cuadra es simplemente «no». Rechaza además la llave pública y el `R` de la firma
    de orden pequeño (la ecuación cofactorizada de la RFC 8032 los acepta con S = 0 para cualquier mensaje: una «firma universal»; la nativa también los rechaza, D-33).
    """
    if len(clave_publica) == 32 and len(firma) == 64 and (tiene_orden_pequeno(clave_publica) or tiene_orden_pequeno(firma[:32])):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(bytes(clave_publica)).verify(bytes(firma), bytes(mensaje))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# La biblioteca nativa (Fase 4) entra por aquí: `infraestructura/nativo.py` instala su `avl_verify_detached` al cargar. El dominio no importa nada de la infraestructura: sólo guarda la
# función que le dan. Si la nativa lanza una excepción, se usa la referencia; si dice «no», es «no» (la referencia y la nativa dan el mismo veredicto: pruebas diferenciales).
_verificador_alterno: Verificador | None = None


def instalar_verificador_alterno(verificador: Verificador | None) -> None:
    global _verificador_alterno
    _verificador_alterno = verificador


def verificar(clave_publica: bytes, firma: bytes, mensaje: bytes) -> bool:
    alterno = _verificador_alterno
    if alterno is not None:
        try:
            return bool(alterno(clave_publica, firma, mensaje))
        except Exception:   # noqa: BLE001 — la nativa nunca es obligatoria
            pass
    return verificar_referencia(clave_publica, firma, mensaje)


def firmar(clave_privada: bytes, mensaje: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(bytes(clave_privada)).sign(bytes(mensaje))


def par_nuevo() -> tuple[bytes, bytes]:
    """`(privada, pública)` de 32 bytes cada una. Lo usa el nodo para su propia llave; las de emisión se generan fuera (tools/licencias)."""
    privada = Ed25519PrivateKey.generate()
    return (privada.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()),
            privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def publica_de(clave_privada: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(bytes(clave_privada)).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def huella_de_clave(clave_publica: bytes) -> bytes:
    """SHA-256 de una llave pública: identifica a un nodo (`hash_clave_nodo`) sin llevar la llave."""
    return hashlib.sha256(bytes(clave_publica)).digest()


@dataclass(frozen=True)
class Abierto:
    magic: bytes
    kid: str
    campos: dict[int, bytes]
    sha256: str            # huella del archivo completo: sirve para citarlo en la bitácora sin copiar su contenido


def abrir(datos: bytes, magic: bytes, claves: Mapping[str, bytes], conocidos: Mapping[int, tuple[int, bool]], verificador: Verificador = verificar) -> Abierto:
    """Un archivo firmado por una llave conocida (`kid`→llave pública). Rechaza ANTES de interpretar cualquier campo si la firma no es válida."""
    cabecera = tlv.leer_cabecera(datos, magic)
    clave = claves.get(cabecera.kid)
    if clave is None:
        raise LicenciaInvalida("kid_desconocido")
    return _abrir_con(datos, cabecera, clave, conocidos, verificador)


def abrir_autofirmado(datos: bytes, magic: bytes, conocidos: Mapping[int, tuple[int, bool]], verificador: Verificador = verificar) -> Abierto:
    """Un archivo que el nodo firmó con su propia llave: el `kid` ES la llave pública (64 caracteres hexadecimales) y se verifica contra ella."""
    cabecera = tlv.leer_cabecera(datos, magic)
    try:
        clave = bytes.fromhex(cabecera.kid)
    except ValueError:
        raise LicenciaInvalida("formato") from None
    if len(clave) != 32 or clave.hex() != cabecera.kid:
        raise LicenciaInvalida("formato")
    return _abrir_con(datos, cabecera, clave, conocidos, verificador)


def _abrir_con(datos: bytes, cabecera: tlv.Cabecera, clave: bytes, conocidos: Mapping[int, tuple[int, bool]], verificador: Verificador) -> Abierto:
    firmado, firma = datos[:-tlv.TAM_FIRMA], datos[-tlv.TAM_FIRMA:]
    if not verificador(clave, firma, firmado):
        raise LicenciaInvalida("firma_invalida")
    campos = tlv.leer_campos(datos[cabecera.fin:-tlv.TAM_FIRMA], conocidos)
    return Abierto(cabecera.magic, cabecera.kid, campos, hashlib.sha256(datos).hexdigest())
