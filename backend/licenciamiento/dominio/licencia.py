"""
La licencia (`.avlic`): sus campos, su codificación y las reglas de forma. Este archivo SÓLO sabe de bytes y de valores; quien decide qué se puede hacer con ella
(`estado.py`) y quien la firma (el emisor, `tools/licencias/`, que nunca viaja con el nodo) viven aparte.

Campos (etiqueta · tipo · ¿crítica?):

    1  id_licencia   16 bytes (UUID)                              crítica    identifica la licencia a lo largo de renovaciones
    2  serie         u32 ≥ 1                                      crítica    sube con cada archivo nuevo de la misma licencia: no se puede volver a una anterior
    3  aula          texto UTF-8 ≤ 120 caracteres                              sólo informativo (jamás una decisión se toma con él)
    4  emitida       u64 · ms desde 1970                          crítica
    5  desde         u64 · ms                                     crítica    primer instante de vigencia
    6  vence         u64 · ms                                     crítica    fin de la vigencia; empieza la gracia
    7  gracia_dias   u16 ≤ 365                                    crítica    días de gracia después de vencer (y tras un cambio de equipo)
    8  limites       4 × u32: equipos · usuarios · concurrentes normal · concurrentes pico      crítica    0xFFFFFFFF = sin tope
    9  capacidades   lista de códigos ASCII (u8 largo + texto), en orden y sin repetir   crítica    los módulos licenciables que se habilitan (`*` = todos)
    10 huella        k(u8) n(u8) y n × (factor u8 + hash de 32 bytes)           crítica    el equipo maestro al que se sella (k de n factores deben coincidir)
    11 tipo          u8: 1 producción · 2 evaluación · 3 desarrollo              crítica
    12 banderas      u32 de bits + u16 de días de liberación pendiente           crítica    bit 0 = LIBERACION_PENDIENTE
    13 hash_clave_nodo  32 bytes                                              el hash de la llave del nodo para el que se emitió (el emisor lo coteja en una liberación)

Todo lo crítico lo es porque cambia lo que la licencia significa: un nodo viejo que no entiende una etiqueta nueva y crítica debe RECHAZAR el archivo, no ignorarla.
"""
from __future__ import annotations

import base64
import binascii
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from . import firma, tlv
from .errores import LicenciaInvalida

T_ID, T_SERIE, T_AULA, T_EMITIDA, T_DESDE, T_VENCE, T_GRACIA, T_LIMITES, T_CAPACIDADES, T_HUELLA, T_TIPO, T_BANDERAS, T_HASH_NODO = range(1, 14)

CONOCIDOS: dict[int, tuple[int, bool]] = {
    T_ID: (16, True), T_SERIE: (4, True), T_AULA: (480, False), T_EMITIDA: (8, True), T_DESDE: (8, True), T_VENCE: (8, True), T_GRACIA: (2, True),
    T_LIMITES: (16, True), T_CAPACIDADES: (1024, True), T_HUELLA: (2 + 16 * 33, True), T_TIPO: (1, True), T_BANDERAS: (6, True), T_HASH_NODO: (32, False),
}
OBLIGATORIOS = (T_ID, T_SERIE, T_EMITIDA, T_DESDE, T_VENCE, T_GRACIA, T_LIMITES, T_CAPACIDADES, T_HUELLA, T_TIPO)

ILIMITADO = 0xFFFFFFFF
MAX_GRACIA_DIAS = 365
MAX_VIGENCIA_MS = 25 * 366 * 86_400_000
MAX_CAPACIDADES = 64
MAX_FACTORES = 16
BANDERA_LIBERACION_PENDIENTE = 1

TIPO_PRODUCCION, TIPO_EVALUACION, TIPO_DESARROLLO = "produccion", "evaluacion", "desarrollo"
_TIPOS = {1: TIPO_PRODUCCION, 2: TIPO_EVALUACION, 3: TIPO_DESARROLLO}
_CODIGOS_DE_TIPO = {v: k for k, v in _TIPOS.items()}

PREFIJO_TEXTO = {tlv.MAGIC_LICENCIA: "AVL1.", tlv.MAGIC_SOLICITUD: "AVQ1.", tlv.MAGIC_LIBERACION: "AVR1."}
_CODIGO_DE_CAPACIDAD = re.compile(r"^[a-z0-9_*]{1,24}$")
_BASE64_URL = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Limites:
    equipos: int
    usuarios: int
    concurrentes_normal: int
    concurrentes_pico: int


@dataclass(frozen=True)
class HuellaDeLicencia:
    """Los factores de hardware (hashes con clave de producto, nunca identificadores crudos) a los que se selló la licencia, y cuántos deben coincidir."""

    k: int
    factores: tuple[tuple[int, bytes], ...]

    def es_la_misma(self, otra: HuellaDeLicencia) -> bool:
        """Mismos factores y mismo k, sin importar el orden en que viajen en el archivo."""
        return self.k == otra.k and frozenset(self.factores) == frozenset(otra.factores)


@dataclass(frozen=True)
class Licencia:
    id: str
    serie: int
    aula: str
    emitida: int
    desde: int
    vence: int
    gracia_dias: int
    limites: Limites
    capacidades: frozenset[str]
    huella: HuellaDeLicencia
    tipo: str
    liberacion_pendiente: bool = False
    liberacion_dias: int = 0
    hash_clave_nodo: bytes | None = None
    kid: str = ""
    sha256: str = ""         # huella del archivo: la forma de citarla en la bitácora y en los eventos

    def habilita(self, capacidad: str) -> bool:
        return "*" in self.capacidades or capacidad in self.capacidades


# --------------------------------------------------------------------------------------------------------------------- valores
def _entero(valor: bytes, bytes_: int) -> int:
    if len(valor) != bytes_:
        raise LicenciaInvalida("campo_invalido")
    return int.from_bytes(valor, "big")


def codificar_huella(huella: HuellaDeLicencia) -> bytes:
    if not 1 <= len(huella.factores) <= MAX_FACTORES or not 1 <= huella.k <= len(huella.factores):
        raise ValueError("huella fuera de rango")
    cuerpo = bytes([huella.k, len(huella.factores)])
    for factor, hash_ in huella.factores:
        if len(hash_) != 32:
            raise ValueError("el hash de un factor mide 32 bytes")
        cuerpo += bytes([factor]) + hash_
    return cuerpo


def decodificar_huella(valor: bytes) -> HuellaDeLicencia:
    if len(valor) < 2:
        raise LicenciaInvalida("campo_invalido")
    k, n = valor[0], valor[1]
    if not 1 <= n <= MAX_FACTORES or not 1 <= k <= n or len(valor) != 2 + 33 * n:
        raise LicenciaInvalida("campo_invalido")
    factores: list[tuple[int, bytes]] = []
    anterior = 0
    for i in range(n):
        base = 2 + 33 * i
        factor = valor[base]
        if factor <= anterior or factor > 32:      # en orden y sin repetir: una sola forma de escribirlos
            raise LicenciaInvalida("campo_invalido")
        anterior = factor
        factores.append((factor, bytes(valor[base + 1: base + 33])))
    return HuellaDeLicencia(k, tuple(factores))


def _codificar_capacidades(capacidades: frozenset[str] | set[str]) -> bytes:
    codigos = sorted(capacidades)
    if len(codigos) > MAX_CAPACIDADES or any(not _CODIGO_DE_CAPACIDAD.match(c) for c in codigos):
        raise ValueError("capacidades fuera de rango")
    return b"".join(bytes([len(c)]) + c.encode("ascii") for c in codigos)


def _decodificar_capacidades(valor: bytes) -> frozenset[str]:
    codigos: list[str] = []
    pos = 0
    while pos < len(valor):
        largo = valor[pos]
        pos += 1
        if largo == 0 or pos + largo > len(valor) or len(codigos) >= MAX_CAPACIDADES:
            raise LicenciaInvalida("campo_invalido")
        try:
            codigo = valor[pos:pos + largo].decode("ascii")
        except UnicodeDecodeError:
            raise LicenciaInvalida("campo_invalido") from None
        pos += largo
        if not _CODIGO_DE_CAPACIDAD.match(codigo) or (codigos and codigo <= codigos[-1]):    # en orden y sin repetir
            raise LicenciaInvalida("campo_invalido")
        codigos.append(codigo)
    return frozenset(codigos)


def _texto(valor: bytes, maximo: int) -> str:
    try:
        texto = valor.decode("utf-8")
    except UnicodeDecodeError:
        raise LicenciaInvalida("campo_invalido") from None
    if len(texto) > maximo or any(ord(c) < 32 or ord(c) == 127 for c in texto) or texto != texto.strip():
        raise LicenciaInvalida("campo_invalido")
    return texto


# --------------------------------------------------------------------------------------------------------------------- codificar
def campos_de(licencia: Licencia) -> dict[int, bytes]:
    """Los campos tal como se escriben en el archivo (lo usa el emisor; el nodo sólo lee)."""
    campos = {
        T_ID: uuid.UUID(licencia.id).bytes,
        T_SERIE: licencia.serie.to_bytes(4, "big"),
        T_EMITIDA: licencia.emitida.to_bytes(8, "big"),
        T_DESDE: licencia.desde.to_bytes(8, "big"),
        T_VENCE: licencia.vence.to_bytes(8, "big"),
        T_GRACIA: licencia.gracia_dias.to_bytes(2, "big"),
        T_LIMITES: b"".join(n.to_bytes(4, "big") for n in (licencia.limites.equipos, licencia.limites.usuarios,
                                                           licencia.limites.concurrentes_normal, licencia.limites.concurrentes_pico)),
        T_CAPACIDADES: _codificar_capacidades(licencia.capacidades),
        T_HUELLA: codificar_huella(licencia.huella),
        T_TIPO: bytes([_CODIGOS_DE_TIPO[licencia.tipo]]),
    }
    if licencia.aula:
        campos[T_AULA] = licencia.aula.encode("utf-8")
    if licencia.liberacion_pendiente or licencia.liberacion_dias:
        campos[T_BANDERAS] = (BANDERA_LIBERACION_PENDIENTE if licencia.liberacion_pendiente else 0).to_bytes(4, "big") + licencia.liberacion_dias.to_bytes(2, "big")
    if licencia.hash_clave_nodo:
        campos[T_HASH_NODO] = licencia.hash_clave_nodo
    return campos


def sin_firma(licencia: Licencia, kid: str) -> bytes:
    return tlv.escribir(tlv.MAGIC_LICENCIA, kid, campos_de(licencia), CONOCIDOS)


# --------------------------------------------------------------------------------------------------------------------- interpretar
def desde_campos(campos: Mapping[int, bytes], kid: str = "", sha256: str = "") -> Licencia:
    """De los campos YA verificados (la firma se comprobó antes) a una licencia, con las reglas de forma: rangos, orden y coherencia. No decide nada sobre «hoy»."""
    for etiqueta in OBLIGATORIOS:
        if etiqueta not in campos:
            raise LicenciaInvalida("campo_faltante")
    try:
        identificador = str(uuid.UUID(bytes=campos[T_ID])) if len(campos[T_ID]) == 16 else None
    except ValueError:
        identificador = None
    if identificador is None:
        raise LicenciaInvalida("campo_invalido")
    serie = _entero(campos[T_SERIE], 4)
    emitida, desde, vence = _entero(campos[T_EMITIDA], 8), _entero(campos[T_DESDE], 8), _entero(campos[T_VENCE], 8)
    gracia = _entero(campos[T_GRACIA], 2)
    if serie < 1 or gracia > MAX_GRACIA_DIAS or not 0 < emitida < 2**62 or not 0 < desde < vence < 2**62 or vence - desde > MAX_VIGENCIA_MS:
        raise LicenciaInvalida("campo_invalido")
    crudo_limites = campos[T_LIMITES]
    if len(crudo_limites) != 16:
        raise LicenciaInvalida("campo_invalido")
    equipos, usuarios, normal, pico = (int.from_bytes(crudo_limites[i:i + 4], "big") for i in (0, 4, 8, 12))
    if normal > pico:
        raise LicenciaInvalida("campo_invalido")
    tipo = _TIPOS.get(_entero(campos[T_TIPO], 1))
    if tipo is None:
        raise LicenciaInvalida("campo_invalido")
    pendiente, dias = False, 0
    if T_BANDERAS in campos:
        valor = campos[T_BANDERAS]
        if len(valor) != 6:
            raise LicenciaInvalida("campo_invalido")
        bits, dias = int.from_bytes(valor[:4], "big"), int.from_bytes(valor[4:], "big")
        if bits & ~BANDERA_LIBERACION_PENDIENTE or dias > MAX_GRACIA_DIAS:
            raise LicenciaInvalida("campo_invalido")
        pendiente = bool(bits & BANDERA_LIBERACION_PENDIENTE)
        if not pendiente and dias:
            raise LicenciaInvalida("campo_invalido")
    hash_nodo = campos.get(T_HASH_NODO)
    if hash_nodo is not None and len(hash_nodo) != 32:
        raise LicenciaInvalida("campo_invalido")
    return Licencia(
        id=identificador, serie=serie, aula=_texto(campos[T_AULA], 120) if T_AULA in campos else "", emitida=emitida, desde=desde, vence=vence, gracia_dias=gracia,
        limites=Limites(equipos, usuarios, normal, pico), capacidades=_decodificar_capacidades(campos[T_CAPACIDADES]), huella=decodificar_huella(campos[T_HUELLA]),
        tipo=tipo, liberacion_pendiente=pendiente, liberacion_dias=dias, hash_clave_nodo=bytes(hash_nodo) if hash_nodo is not None else None, kid=kid, sha256=sha256)


def leer(datos: bytes, claves: Mapping[str, bytes], verificador: firma.Verificador = firma.verificar) -> Licencia:
    """Un `.avlic` binario → licencia. Verifica la firma antes de interpretar nada y rechaza lo que no sea EXACTAMENTE una licencia bien formada."""
    abierto = firma.abrir(datos, tlv.MAGIC_LICENCIA, claves, CONOCIDOS, verificador)
    return desde_campos(abierto.campos, kid=abierto.kid, sha256=abierto.sha256)


# --------------------------------------------------------------------------------------------------------------------- variante texto
def a_texto(datos: bytes, magic: bytes = tlv.MAGIC_LICENCIA) -> str:
    """`AVL1.` + base64url sin relleno: para copiar la licencia como texto cuando no hay forma de mover el archivo."""
    return PREFIJO_TEXTO[magic] + base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def de_texto(texto: str, magic: bytes = tlv.MAGIC_LICENCIA) -> bytes:
    """El texto → los bytes del archivo, de forma ESTRICTA: sólo la forma canónica (sin espacios, sin relleno, sin caracteres sobrantes). Una variante «equivalente» del mismo
    texto no es otro texto válido: con ella sería posible fabricar archivos distintos que leen igual, y cada archivo debe tener una sola forma."""
    prefijo = PREFIJO_TEXTO[magic]
    if not isinstance(texto, str) or not texto.startswith(prefijo) or len(texto) > (tlv.MAX_ARCHIVO * 4) // 3 + 16:
        raise LicenciaInvalida("texto")
    cuerpo = texto[len(prefijo):]
    if not cuerpo or not _BASE64_URL.match(cuerpo) or len(cuerpo) % 4 == 1:
        raise LicenciaInvalida("texto")
    try:
        datos = base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4))
    except (binascii.Error, ValueError):
        raise LicenciaInvalida("texto") from None
    if base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii") != cuerpo:      # los bits sobrantes del último carácter tienen que ser cero
        raise LicenciaInvalida("texto")
    return datos


def leer_texto(texto: str, claves: Mapping[str, bytes], verificador: firma.Verificador = firma.verificar) -> Licencia:
    return leer(de_texto(texto), claves, verificador)
