"""
Apoyo de las pruebas de identidad de dispositivo: arma cadenas de atestación SINTÉTICAS (raíz → intermedia → hoja con la extensión de Android) con `cryptography`, para que cada defecto
(reto distinto, app ajena, arranque desbloqueado…) se pueda fabricar. Las cadenas REALES capturadas del emulador viven en `tests/fixtures/atestacion/`.
"""
from __future__ import annotations

import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from licenciamiento.dominio import atestacion as at

AHORA = int(dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
PAQUETE = "com.avacom.lms.student"
FIRMA_AVACOM = bytes.fromhex("11" * 32)
FIRMA_AJENA = bytes.fromhex("22" * 32)


# ------------------------------------------------------------------------------------------------------------------ DER
def _largo(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    cuerpo = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(cuerpo)]) + cuerpo


def tlv(etiqueta: int, contenido: bytes) -> bytes:
    return bytes([etiqueta]) + _largo(len(contenido)) + contenido


def entero(n: int) -> bytes:
    cuerpo = n.to_bytes(max(1, (n.bit_length() + 8) // 8), "big", signed=True)
    return tlv(0x02, cuerpo)


def enumerado(n: int) -> bytes:
    return tlv(0x0A, bytes([n]))


def octetos(b: bytes) -> bytes:
    return tlv(0x04, b)


def booleano(v: bool) -> bytes:
    return tlv(0x01, b"\xff" if v else b"\x00")


def secuencia(*partes: bytes) -> bytes:
    return tlv(0x30, b"".join(partes))


def conjunto(*partes: bytes) -> bytes:
    return tlv(0x31, b"".join(partes))


def explicito(numero: int, contenido: bytes) -> bytes:
    """[numero] EXPLICIT de la clase contexto (las etiquetas 704 y 709 llevan etiqueta de varios bytes)."""
    if numero < 31:
        cab = bytes([0xA0 | numero])
    else:
        partes = []
        n = numero
        while True:
            partes.append(n & 0x7F)
            n >>= 7
            if not n:
                break
        partes.reverse()
        cab = bytes([0xBF]) + bytes(p | 0x80 for p in partes[:-1]) + bytes([partes[-1]])
    return cab + _largo(len(contenido)) + contenido


def extension(*, reto: bytes, nivel_atestacion: int = at.NIVEL_TEE, nivel_llave: int | None = None, arranque: int | None = at.ARRANQUE_VERIFICADO, bloqueado: bool | None = True,
              paquetes: tuple[str, ...] = (PAQUETE,), firmas: tuple[bytes, ...] = (FIRMA_AVACOM,), version: int = 300) -> bytes:
    nivel_llave = nivel_atestacion if nivel_llave is None else nivel_llave
    tee = []
    if arranque is not None:
        tee.append(explicito(at.ETIQUETA_RAIZ_DE_CONFIANZA, secuencia(octetos(b"\x00" * 32), booleano(bool(bloqueado)), enumerado(arranque), octetos(b"\x00" * 32))))
    software = []
    if paquetes:
        app = secuencia(conjunto(*[secuencia(octetos(p.encode()), entero(1)) for p in paquetes]), conjunto(*[octetos(f) for f in firmas]))
        software.append(explicito(at.ETIQUETA_APLICACION, octetos(app)))
    return secuencia(entero(version), enumerado(nivel_atestacion), entero(300), enumerado(nivel_llave), octetos(reto), octetos(b""), secuencia(*software), secuencia(*tee))


# ------------------------------------------------------------------------------------------------------------------ certificados
def _nombre(texto: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, texto)])


def _certificado(sujeto: str, clave_publica, emisor: str, clave_emisor, *, ca: bool, serie: int, ext: bytes | None = None, vigente: bool = True) -> x509.Certificate:
    desde = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    hasta = dt.datetime(2035, 1, 1, tzinfo=dt.timezone.utc) if vigente else dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(_nombre(sujeto)).issuer_name(_nombre(emisor)).public_key(clave_publica).serial_number(serie)
         .not_valid_before(desde).not_valid_after(hasta).add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if ext is not None:
        b = b.add_extension(x509.UnrecognizedExtension(at.OID_ATESTACION, ext), critical=False)
    return b.sign(clave_emisor, hashes.SHA256())


def der(c: x509.Certificate) -> bytes:
    return c.public_bytes(serialization.Encoding.DER)


def spki(clave) -> bytes:
    return clave.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


class Entorno:
    """Una raíz propia (que hace de «raíz de Google» en las pruebas), una intermedia, y la clave del equipo."""

    def __init__(self):
        self.raiz_k = ec.generate_private_key(ec.SECP384R1())
        self.inter_k = ec.generate_private_key(ec.SECP256R1())
        self.clave_k = ec.generate_private_key(ec.SECP256R1())
        self.raiz = _certificado("raiz", self.raiz_k.public_key(), "raiz", self.raiz_k, ca=True, serie=1)
        self.inter = _certificado("intermedia", self.inter_k.public_key(), "raiz", self.raiz_k, ca=True, serie=2)
        self.raices = [at.Raiz("prueba", spki(self.raiz.public_key()), AHORA - 10**9, AHORA + 10**11)]
        self.app = at.PoliticaDeApp(frozenset({PAQUETE}), frozenset({FIRMA_AVACOM}))
        self.spki_clave = spki(self.clave_k.public_key())

    def cadena(self, ext: bytes, *, hoja_con_clave=None, vigente: bool = True, serie_hoja: int = 3) -> list[bytes]:
        clave = (hoja_con_clave or self.clave_k).public_key()
        hoja = _certificado("hoja", clave, "intermedia", self.inter_k, ca=False, serie=serie_hoja, ext=ext, vigente=vigente)
        return [der(hoja), der(self.inter), der(self.raiz)]

    def evaluar(self, cadena, nonce: bytes, **kw):
        datos = dict(spki_declarada=self.spki_clave, nonce=nonce, cadena_der=cadena, ahora_ms=AHORA, raices=self.raices, revocadas=frozenset(), app=self.app)
        datos.update(kw)
        return at.evaluar(**datos)

    def firmar_reto(self, nonce: bytes, identificador_hw: str) -> bytes:
        return self.clave_k.sign(at.mensaje_del_reto(nonce, identificador_hw), ec.ECDSA(hashes.SHA256()))
