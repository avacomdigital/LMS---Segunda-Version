"""
El sello de dispositivo AVACOM (`.avsello`), la solicitud que lo pide (`.avsol`) y la lista de revocados (`.avrev`). Segunda protección (S1, `09-segunda-proteccion.md`).

Un sello es un archivo firmado por AVACOM (Ed25519, llave `sello-…`, distinta de la de licencias y de la de publicación; SP-07) que dice: «la clave pública de equipo cuya huella es X pertenece a un dispositivo
AVACOM». NO sigue a la MAC, ni al SMBIOS, ni al MachineGuid: sigue a una clave EC P-256 que vive en el TPM (Windows) y no se puede exportar. La MAC y los demás datos viajan como INFORMACIÓN y jamás
deciden (SP-03).

Mismo envoltorio TLV que la licencia (`tlv.py`): la firma cubre todo lo anterior a ella y se verifica ANTES de leer ningún campo.

`.avavsello` (magic AVSL)                                                                                                     etiqueta · tipo · ¿crítica?
    1 id_sello        16 bytes                                                                                                 crítica
    2 serie           texto ASCII ≤ 64 (la del lote de fábrica o la que anota quien entrega)                                  informativa
    3 modelo          texto ≤ 64                                                                                               informativa
    4 origen          u8: 1 fábrica · 2 entrega                                                                                crítica
    5 clave_huella    32 bytes: SHA-256 del SubjectPublicKeyInfo de la clave de identidad del equipo (la que firma el reto)    crítica
    6 cifrado_huella  32 bytes: SHA-256 del SPKI de la clave de CIFRADO del equipo (la que desenvuelve la clave del paquete, S2) informativa (sólo la usa S2)
    7 ek_huella       32 bytes: SHA-256 de la EKPub del TPM, si se pudo leer                                                   informativa
    8 emitido         u64 · ms                                                                                                 crítica
    9 vence           u64 · ms; 0 = no vence (SQ-05)                                                                           crítica
   10 lote            texto ≤ 32                                                                                               informativa
   11 mac             texto ≤ 17: INFORMATIVA, no decide nunca                                                                 informativa
   12 evidencia       u8: 1 inventario de fábrica · 2 cadena de EKCert · 3 activación de credencial del TPM                    crítica   cómo se comprobó que el equipo era de AVACOM
   13 uefi_id         texto: el `AVACOM_DEVICE_ID` de la variable UEFI del equipo que AVACOM autoriza (`AVACOM-OPS-…`)            informativa para el formato, DECISIVA para el Host: sin él el sello no autoriza ningún equipo

`.avsol` (magic AVSO): la solicitud, firmada por el propio equipo con su clave de identidad (ECDSA P-256 · SHA-256 · 64 bytes IEEE P1363 en el lugar de la firma). Su `kid` es siempre `equipo`.
    1 id              16 bytes · 2 serie · 3 modelo · 4 clave_publica (SPKI de la identidad) · 5 cifrado_publica (SPKI RSA de cifrado) · 6 ek_publica (opcional) · 7 mac · 8 proveedor u8 (1 TPM, 0 software) · 9 creada u64
    10 uefi_id        texto: el `AVACOM_DEVICE_ID` que el equipo leyó de su firmware (UEFI) al pedir el sello

`.avrev` (magic AVRV): lista de revocados firmada con la llave de sello. 1 numero u32 (sube con cada lista) · 2 emitida u64 · 3 huellas (n × 32 bytes de `clave_huella`, ≤ 128).

El dominio no toca hardware: la PRUEBA DE POSESIÓN (firmar un reto con la clave del equipo) la hace quien llama y entra a `evaluar` como un booleano.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from . import firma, licencia, tlv
from .errores import LicenciaInvalida

MAGIC_SELLO = b"AVSL"
MAGIC_SOLICITUD_SELLO = b"AVSO"
MAGIC_REVOCADOS = b"AVRV"
MAGIC_CLAVE = b"AVKY"

# Los magic de `tlv.MAGICS` sólo se comprueban al escribir; aquí se amplía el conjunto con los propios sin tocar el formato de licencias.
tlv.MAGICS = tuple(dict.fromkeys((*tlv.MAGICS, MAGIC_SELLO, MAGIC_SOLICITUD_SELLO, MAGIC_REVOCADOS, MAGIC_CLAVE)))
licencia.PREFIJO_TEXTO.update({MAGIC_SELLO: "AVS1.", MAGIC_SOLICITUD_SELLO: "AVO1.", MAGIC_REVOCADOS: "AVV1.", MAGIC_CLAVE: "AVK1."})

T_ID, T_SERIE, T_MODELO, T_ORIGEN, T_CLAVE_HUELLA, T_CIFRADO_HUELLA, T_EK_HUELLA, T_EMITIDO, T_VENCE, T_LOTE, T_MAC, T_EVIDENCIA, T_UEFI_ID = range(1, 14)
CONOCIDOS_SELLO: dict[int, tuple[int, bool]] = {
    T_ID: (16, True), T_SERIE: (64, False), T_MODELO: (64, False), T_ORIGEN: (1, True), T_CLAVE_HUELLA: (32, True), T_CIFRADO_HUELLA: (32, False), T_EK_HUELLA: (32, False),
    T_EMITIDO: (8, True), T_VENCE: (8, True), T_LOTE: (32, False), T_MAC: (17, False), T_EVIDENCIA: (1, True), T_UEFI_ID: (32, False),
}
OBLIGATORIOS_SELLO = (T_ID, T_ORIGEN, T_CLAVE_HUELLA, T_EMITIDO, T_VENCE, T_EVIDENCIA)

S_ID, S_SERIE, S_MODELO, S_CLAVE, S_CIFRADO, S_EK, S_MAC, S_PROVEEDOR, S_CREADA, S_UEFI_ID = range(1, 11)
CONOCIDOS_SOLICITUD: dict[int, tuple[int, bool]] = {
    S_ID: (16, True), S_SERIE: (64, False), S_MODELO: (64, False), S_CLAVE: (128, True), S_CIFRADO: (600, False), S_EK: (600, False), S_MAC: (17, False),
    S_PROVEEDOR: (1, True), S_CREADA: (8, True), S_UEFI_ID: (32, False),
}
OBLIGATORIAS_SOLICITUD = (S_ID, S_CLAVE, S_PROVEEDOR, S_CREADA)

K_ID, K_CIFRADO_HUELLA, K_KID_PAQUETE, K_ENVUELTA, K_EMITIDA, K_VERSION = range(1, 7)
CONOCIDOS_CLAVE: dict[int, tuple[int, bool]] = {K_ID: (16, True), K_CIFRADO_HUELLA: (32, True), K_KID_PAQUETE: (8, True), K_ENVUELTA: (512, True), K_EMITIDA: (8, True), K_VERSION: (32, False)}

R_NUMERO, R_EMITIDA, R_HUELLAS = 1, 2, 3
CONOCIDOS_REVOCADOS: dict[int, tuple[int, bool]] = {R_NUMERO: (4, True), R_EMITIDA: (8, True), R_HUELLAS: (32 * 128, True)}

ORIGEN_FABRICA, ORIGEN_ENTREGA = 1, 2
_ORIGENES = {ORIGEN_FABRICA: "fabrica", ORIGEN_ENTREGA: "entrega"}
EVIDENCIA_INVENTARIO, EVIDENCIA_EKCERT, EVIDENCIA_ACTIVACION = 1, 2, 3
_EVIDENCIAS = {EVIDENCIA_INVENTARIO: "inventario", EVIDENCIA_EKCERT: "ekcert", EVIDENCIA_ACTIVACION: "activacion"}
CONTEXTO_POSESION = b"AVACOM-SELLO1"

# El identificador que el firmware de un dispositivo AVACOM trae en la variable UEFI `AVACOM_DEVICE_ID` (GUID {8b7f9c20-3e51-4c8a-a7d1-91c62e0f4b35}). El formato es el MISMO que comprueba el Host
# (`IdentidadUefi.EsFormatoValido`): un identificador que no lo cumple no se sella ni se acepta. Cumplir el formato NO prueba nada: lo que autoriza es que el sello firmado por AVACOM lo traiga.
FORMATO_UEFI_ID = re.compile(r"AVACOM-OPS-[0-9A-Z]{8,16}")


def uefi_id_valido(texto: str) -> bool:
    return bool(FORMATO_UEFI_ID.fullmatch(texto))
KID_SOLICITUD = "equipo"

# Veredictos de `evaluar` (los mismos que imprime `verificar-dispositivo`).
AUTENTICADO, SIN_SELLO, SELLO_INVALIDO, CLAVE_DISTINTA, REVOCADO, NO_VERIFICABLE = "autenticado", "sin_sello", "sello_invalido", "clave_distinta", "revocado", "no_verificable"


@dataclass(frozen=True)
class Sello:
    id: str
    serie: str
    modelo: str
    origen: str
    clave_huella: bytes
    cifrado_huella: bytes | None
    ek_huella: bytes | None
    emitido: int
    vence: int
    lote: str
    mac: str
    evidencia: str
    kid: str
    sha256: str
    uefi_id: str = ""

    def vencido(self, ahora_ms: int) -> bool:
        return self.vence != 0 and ahora_ms > self.vence


@dataclass(frozen=True)
class Veredicto:
    estado: str
    motivo: str = ""
    sello: Sello | None = None


def mensaje_de_posesion(reto: bytes, clave_huella: bytes) -> bytes:
    """Lo que firma el equipo para probar que tiene la clave: «AVACOM-SELLO1» + reto (32 bytes) + huella de su clave. Atar la huella evita que una firma sirva para otra clave."""
    if len(reto) != 32 or len(clave_huella) != 32:
        raise ValueError("reto y huella miden 32 bytes")
    return CONTEXTO_POSESION + reto + clave_huella


def huella_de_spki(spki: bytes) -> bytes:
    return hashlib.sha256(bytes(spki)).digest()


def _texto(campos: Mapping[int, bytes], etiqueta: int) -> str:
    valor = campos.get(etiqueta, b"")
    try:
        texto = valor.decode("ascii")
    except UnicodeDecodeError:
        raise LicenciaInvalida("campo_invalido") from None
    if not texto.isprintable():
        raise LicenciaInvalida("campo_invalido")
    return texto


def _u(campos: Mapping[int, bytes], etiqueta: int, bytes_: int) -> int:
    valor = campos[etiqueta]
    if len(valor) != bytes_:
        raise LicenciaInvalida("campo_invalido")
    return int.from_bytes(valor, "big")


# --------------------------------------------------------------------------------------------------------------------------------- sello
def codificar_sello(kid: str, s: Sello, firmar) -> bytes:
    """Los bytes firmados del sello. `firmar(bytes) → 64 bytes`. La verdad la tiene `leer_sello`: lo escrito se vuelve a leer en la emisión."""
    campos: dict[int, bytes] = {
        T_ID: bytes.fromhex(s.id.replace("-", "")), T_ORIGEN: bytes([{v: k for k, v in _ORIGENES.items()}[s.origen]]), T_CLAVE_HUELLA: s.clave_huella,
        T_EMITIDO: s.emitido.to_bytes(8, "big"), T_VENCE: s.vence.to_bytes(8, "big"), T_EVIDENCIA: bytes([{v: k for k, v in _EVIDENCIAS.items()}[s.evidencia]]),
    }
    for etiqueta, valor in ((T_SERIE, s.serie), (T_MODELO, s.modelo), (T_LOTE, s.lote), (T_MAC, s.mac)):
        if valor:
            campos[etiqueta] = valor.encode("ascii")
    if s.cifrado_huella:
        campos[T_CIFRADO_HUELLA] = s.cifrado_huella
    if s.ek_huella:
        campos[T_EK_HUELLA] = s.ek_huella
    if s.uefi_id:
        campos[T_UEFI_ID] = s.uefi_id.encode("ascii")
    return tlv.sellar(tlv.escribir(MAGIC_SELLO, kid, campos, CONOCIDOS_SELLO), firmar)


def leer_sello(datos: bytes, claves: Mapping[str, bytes]) -> Sello:
    """Verifica la firma con `claves` (kid → pública) y SÓLO entonces interpreta los campos. Lanza `LicenciaInvalida` con el motivo."""
    abierto = firma.abrir(datos, MAGIC_SELLO, claves, CONOCIDOS_SELLO)
    c = abierto.campos
    if any(t not in c for t in OBLIGATORIOS_SELLO):
        raise LicenciaInvalida("campo_faltante")
    origen = _ORIGENES.get(_u(c, T_ORIGEN, 1))
    evidencia = _EVIDENCIAS.get(_u(c, T_EVIDENCIA, 1))
    if origen is None or evidencia is None or len(c[T_ID]) != 16 or len(c[T_CLAVE_HUELLA]) != 32:
        raise LicenciaInvalida("campo_invalido")
    for etiqueta in (T_CIFRADO_HUELLA, T_EK_HUELLA):
        if etiqueta in c and len(c[etiqueta]) != 32:
            raise LicenciaInvalida("campo_invalido")
    emitido, vence = _u(c, T_EMITIDO, 8), _u(c, T_VENCE, 8)
    if vence and vence <= emitido:
        raise LicenciaInvalida("campo_invalido")
    uefi_id = _texto(c, T_UEFI_ID)
    if uefi_id and not uefi_id_valido(uefi_id):
        raise LicenciaInvalida("campo_invalido")
    ident = c[T_ID].hex()
    return Sello(f"{ident[:8]}-{ident[8:12]}-{ident[12:16]}-{ident[16:20]}-{ident[20:]}", _texto(c, T_SERIE), _texto(c, T_MODELO), origen, c[T_CLAVE_HUELLA],
                 c.get(T_CIFRADO_HUELLA), c.get(T_EK_HUELLA), emitido, vence, _texto(c, T_LOTE), _texto(c, T_MAC), evidencia, abierto.kid, abierto.sha256, uefi_id)


# --------------------------------------------------------------------------------------------------------------------------------- revocados
def codificar_revocados(kid: str, numero: int, emitida: int, huellas: list[bytes], firmar) -> bytes:
    if not 0 <= len(huellas) <= 128 or any(len(h) != 32 for h in huellas):
        raise ValueError("hasta 128 huellas de 32 bytes")
    campos = {R_NUMERO: numero.to_bytes(4, "big"), R_EMITIDA: emitida.to_bytes(8, "big"), R_HUELLAS: b"".join(sorted(set(huellas)))}
    return tlv.sellar(tlv.escribir(MAGIC_REVOCADOS, kid, campos, CONOCIDOS_REVOCADOS), firmar)


def leer_revocados(datos: bytes, claves: Mapping[str, bytes]) -> tuple[int, frozenset[bytes]]:
    c = firma.abrir(datos, MAGIC_REVOCADOS, claves, CONOCIDOS_REVOCADOS).campos
    if any(t not in c for t in (R_NUMERO, R_HUELLAS)) or len(c[R_HUELLAS]) % 32:
        raise LicenciaInvalida("campo_invalido")
    crudo = c[R_HUELLAS]
    return _u(c, R_NUMERO, 4), frozenset(crudo[i:i + 32] for i in range(0, len(crudo), 32))


# --------------------------------------------------------------------------------------------------------------------------------- solicitud
@dataclass(frozen=True)
class Solicitud:
    id: str
    serie: str
    modelo: str
    clave_publica: bytes
    cifrado_publica: bytes | None
    ek_publica: bytes | None
    mac: str
    en_tpm: bool
    creada: int
    clave_huella: bytes
    uefi_id: str = ""


def codificar_solicitud(s: Solicitud, firmar_ecdsa) -> bytes:
    """`firmar_ecdsa(bytes) → 64 bytes P1363`: lo hace la clave de identidad del equipo (en el TPM; no sale de él)."""
    campos: dict[int, bytes] = {S_ID: bytes.fromhex(s.id.replace("-", "")), S_CLAVE: s.clave_publica, S_PROVEEDOR: bytes([1 if s.en_tpm else 0]), S_CREADA: s.creada.to_bytes(8, "big")}
    for etiqueta, valor in ((S_SERIE, s.serie), (S_MODELO, s.modelo), (S_MAC, s.mac), (S_UEFI_ID, s.uefi_id)):
        if valor:
            campos[etiqueta] = valor.encode("ascii")
    if s.cifrado_publica:
        campos[S_CIFRADO] = s.cifrado_publica
    if s.ek_publica:
        campos[S_EK] = s.ek_publica
    return tlv.sellar(tlv.escribir(MAGIC_SOLICITUD_SELLO, KID_SOLICITUD, campos, CONOCIDOS_SOLICITUD), firmar_ecdsa)


def leer_solicitud(datos: bytes) -> Solicitud:
    """Verifica la firma ECDSA con la clave que la propia solicitud trae (prueba de posesión: quien la hizo tiene la privada). NO prueba que el equipo sea de AVACOM: eso lo decide la estación."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    cab = tlv.leer_cabecera(datos, MAGIC_SOLICITUD_SELLO)
    if cab.kid != KID_SOLICITUD:
        raise LicenciaInvalida("formato")
    c = tlv.leer_campos(datos[cab.fin:-tlv.TAM_FIRMA], CONOCIDOS_SOLICITUD)
    if any(t not in c for t in OBLIGATORIAS_SOLICITUD):
        raise LicenciaInvalida("campo_faltante")
    try:
        clave = serialization.load_der_public_key(c[S_CLAVE])
        if not isinstance(clave, ec.EllipticCurvePublicKey) or clave.curve.name != "secp256r1":
            raise LicenciaInvalida("campo_invalido")
        crudo = datos[-tlv.TAM_FIRMA:]
        clave.verify(encode_dss_signature(int.from_bytes(crudo[:32], "big"), int.from_bytes(crudo[32:], "big")), datos[:-tlv.TAM_FIRMA], ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError):
        raise LicenciaInvalida("firma_invalida") from None
    ident = c[S_ID].hex()
    return Solicitud(f"{ident[:8]}-{ident[8:12]}-{ident[12:16]}-{ident[16:20]}-{ident[20:]}", _texto(c, S_SERIE), _texto(c, S_MODELO), c[S_CLAVE], c.get(S_CIFRADO), c.get(S_EK),
                     _texto(c, S_MAC), c[S_PROVEEDOR] == b"\x01", _u(c, S_CREADA, 8), huella_de_spki(c[S_CLAVE]), _texto(c, S_UEFI_ID))


# --------------------------------------------------------------------------------------------------------------------------------- veredicto
def evaluar(datos_sello: bytes | None, claves: Mapping[str, bytes], clave_huella_del_equipo: bytes | None, posesion: bool | None, revocados: frozenset[bytes], ahora_ms: int) -> Veredicto:
    """
    El veredicto sobre un equipo. El orden importa: primero lo que no se puede leer, luego lo que se puede probar.

      sin_sello       no hay archivo de sello.
      sello_invalido  no verifica (firma, kid, formato, vencido). `motivo` dice cuál.
      no_verificable  hay sello válido pero el equipo no pudo mostrar su clave (sin TPM, TPM bloqueado, error): NO es lo mismo que «clave distinta» y el instalador lo trata como fallo del
                      sistema, no como fraude (SR-03).
      clave_distinta  el equipo tiene una clave y no es la del sello (el sello fue copiado de otro equipo) o no supo firmar el reto.
      revocado        la huella del sello está en la lista de revocados.
      autenticado     todo cuadra: firma, vigencia, clave presente y firmando, y no revocado.
    """
    if not datos_sello:
        return Veredicto(SIN_SELLO)
    try:
        sello = leer_sello(datos_sello, claves)
    except LicenciaInvalida as error:
        return Veredicto(SELLO_INVALIDO, error.motivo if hasattr(error, "motivo") else str(error))
    if sello.vencido(ahora_ms):
        return Veredicto(SELLO_INVALIDO, "vencido", sello)
    if sello.clave_huella in revocados:
        return Veredicto(REVOCADO, "", sello)
    if clave_huella_del_equipo is None:
        return Veredicto(NO_VERIFICABLE, "sin_clave", sello)
    if clave_huella_del_equipo != sello.clave_huella:
        return Veredicto(CLAVE_DISTINTA, "otra_clave", sello)
    if posesion is not True:
        return Veredicto(CLAVE_DISTINTA if posesion is False else NO_VERIFICABLE, "sin_posesion" if posesion is False else "no_firmo", sello)
    return Veredicto(AUTENTICADO, "", sello)


# --------------------------------------------------------------------------------------------------------------------------------- clave del paquete (.avclave)
@dataclass(frozen=True)
class ClaveDePaquete:
    """La llave `K` de UNA version del paquete, ENVUELTA para la clave de cifrado de UN equipo (RSA-OAEP-SHA256, S2). Sólo el TPM de ese equipo la desenvuelve; sin ella el código no se abre."""
    id: str
    cifrado_huella: bytes     # SHA-256 del SPKI de la clave de cifrado del equipo a la que va envuelta
    kid_paquete: bytes        # `kid_de(K)`: qué paquete abre (8 bytes)
    envuelta: bytes           # RSA-OAEP(K): 256 bytes con RSA-2048
    emitida: int
    version: str
    kid: str
    sha256: str


def codificar_clave(kid: str, c: ClaveDePaquete, firmar) -> bytes:
    campos = {K_ID: bytes.fromhex(c.id.replace("-", "")), K_CIFRADO_HUELLA: c.cifrado_huella, K_KID_PAQUETE: c.kid_paquete, K_ENVUELTA: c.envuelta, K_EMITIDA: c.emitida.to_bytes(8, "big")}
    if c.version:
        campos[K_VERSION] = c.version.encode("ascii")
    return tlv.sellar(tlv.escribir(MAGIC_CLAVE, kid, campos, CONOCIDOS_CLAVE), firmar)


def leer_clave(datos: bytes, claves: Mapping[str, bytes]) -> ClaveDePaquete:
    abierto = firma.abrir(datos, MAGIC_CLAVE, claves, CONOCIDOS_CLAVE)
    c = abierto.campos
    if any(t not in c for t in (K_ID, K_CIFRADO_HUELLA, K_KID_PAQUETE, K_ENVUELTA, K_EMITIDA)):
        raise LicenciaInvalida("campo_faltante")
    if len(c[K_ID]) != 16 or len(c[K_CIFRADO_HUELLA]) != 32 or len(c[K_KID_PAQUETE]) != 8 or not 64 <= len(c[K_ENVUELTA]) <= 512:
        raise LicenciaInvalida("campo_invalido")
    ident = c[K_ID].hex()
    return ClaveDePaquete(f"{ident[:8]}-{ident[8:12]}-{ident[12:16]}-{ident[16:20]}-{ident[20:]}", c[K_CIFRADO_HUELLA], c[K_KID_PAQUETE], c[K_ENVUELTA], _u(c, K_EMITIDA, 8), _texto(c, K_VERSION),
                           abierto.kid, abierto.sha256)
