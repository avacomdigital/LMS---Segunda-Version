"""
Envoltura binaria de los archivos de licenciamiento (`.avlic` licencia, `.avreq` solicitud, `.avrel` liberación).

    magic(4) · versión(u16) · largo del kid(u8) · kid · [ etiqueta(u16) · largo(u16) · valor ]… · firma(64)

  · Todo va en orden de red (big endian). La firma Ed25519 cubre TODO lo anterior a ella —magic, versión y kid incluidos— para que nadie pueda «degradar» un archivo cambiando
    su versión. El algoritmo está FIJADO: no hay un campo `alg` que negociar.
  · La cabecera es lo único que se lee antes de verificar la firma (hace falta el `kid` para saber con qué llave). Los campos se interpretan DESPUÉS (`firma.abrir`).
  · Las etiquetas van en orden estrictamente ascendente: cada archivo se escribe de una sola manera (sin duplicados ni reordenamientos que den dos archivos «iguales»).
    El bit 15 marca una etiqueta CRÍTICA: quien no la entiende rechaza el archivo; una no crítica que no se conoce se ignora.
  · Topes: el archivo completo, cada valor y la cantidad de etiquetas. Un archivo más grande que una licencia no es una licencia.

Este archivo no importa criptografía: sólo sabe leer y escribir bytes (y por eso lo puede probar cualquiera sin llaves).
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .errores import LicenciaInvalida

MAGIC_LICENCIA = b"AVLC"
MAGIC_SOLICITUD = b"AVRQ"
MAGIC_LIBERACION = b"AVRL"
MAGICS = (MAGIC_LICENCIA, MAGIC_SOLICITUD, MAGIC_LIBERACION)

VERSION_FORMATO = 1
TAM_FIRMA = 64
MAX_ARCHIVO = 16 * 1024          # una licencia real mide menos de 600 bytes
MAX_VALOR = 4096
MAX_CAMPOS = 32
MAX_KID = 64                     # una licencia usa un kid corto («prod-2026-1»); un archivo firmado por el nodo usa su llave pública en hexadecimal (64 caracteres)
CRITICA = 0x8000

_KID_VALIDO = re.compile(rb"^[a-z0-9._-]{1,64}\Z")        # \Z y no $: con $ un «\n» final también pasaba (lo halló la prueba diferencial contra la nativa, D-32)
_MINIMO = 4 + 2 + 1 + 1 + TAM_FIRMA


@dataclass(frozen=True)
class Cabecera:
    magic: bytes
    version: int
    kid: str
    fin: int          # desplazamiento donde empiezan los campos


def leer_cabecera(datos: bytes, magic_esperado: bytes) -> Cabecera:
    """Lo mínimo que se lee antes de verificar: magic, versión y kid, con todos los topes comprobados. No interpreta ningún campo."""
    if len(datos) > MAX_ARCHIVO:
        raise LicenciaInvalida("demasiado_grande")
    if len(datos) < _MINIMO:
        raise LicenciaInvalida("demasiado_corta")
    if datos[:4] != magic_esperado:
        raise LicenciaInvalida("formato")
    version = int.from_bytes(datos[4:6], "big")
    if version != VERSION_FORMATO:        # ni menor (degradación) ni mayor (no se entiende): sólo la que este nodo sabe leer
        raise LicenciaInvalida("version_no_soportada")
    largo_kid = datos[6]
    if not 1 <= largo_kid <= MAX_KID or 7 + largo_kid + TAM_FIRMA > len(datos):
        raise LicenciaInvalida("formato")
    kid = datos[7:7 + largo_kid]
    if not _KID_VALIDO.match(kid):
        raise LicenciaInvalida("formato")
    return Cabecera(magic_esperado, version, kid.decode("ascii"), 7 + largo_kid)


def leer_campos(cuerpo: bytes, conocidos: Mapping[int, tuple[int, bool]]) -> dict[int, bytes]:
    """
    Interpreta los campos (y sólo debe llamarse con la firma ya verificada). `conocidos` = `{etiqueta: (largo máximo, ¿crítica?)}`, con la etiqueta SIN el bit crítico.
    Devuelve `{etiqueta: valor}` con las conocidas; ignora las no críticas que no conoce y rechaza las críticas desconocidas, el desorden, los duplicados, los valores
    más largos de lo permitido y cualquier byte que sobre.
    """
    campos: dict[int, bytes] = {}
    pos = 0
    ultima = 0
    total = 0
    while pos < len(cuerpo):
        total += 1
        if total > MAX_CAMPOS or pos + 4 > len(cuerpo):
            raise LicenciaInvalida("formato")
        etiqueta = int.from_bytes(cuerpo[pos:pos + 2], "big")
        largo = int.from_bytes(cuerpo[pos + 2:pos + 4], "big")
        pos += 4
        numero = etiqueta & 0x7FFF
        critica = bool(etiqueta & CRITICA)
        if numero == 0 or numero <= ultima:
            raise LicenciaInvalida("formato")
        ultima = numero
        if largo > MAX_VALOR or pos + largo > len(cuerpo):
            raise LicenciaInvalida("formato")
        valor = bytes(cuerpo[pos:pos + largo])
        pos += largo
        if numero in conocidos:
            maximo, debe_ser_critica = conocidos[numero]
            if critica != debe_ser_critica:
                raise LicenciaInvalida("formato")
            if largo > maximo:
                raise LicenciaInvalida("campo_invalido")
            campos[numero] = valor
        elif critica:
            raise LicenciaInvalida("etiqueta_critica_desconocida")
    return campos


def escribir(magic: bytes, kid: str, campos: Mapping[int, bytes], conocidos: Mapping[int, tuple[int, bool]], version: int = VERSION_FORMATO) -> bytes:
    """El archivo SIN firma, con las etiquetas en orden y el bit crítico que declara `conocidos`. Quien tenga la llave privada lo sella con `sellar`."""
    if magic not in MAGICS:
        raise ValueError("magic desconocido")
    codigo = kid.encode("ascii")
    if not _KID_VALIDO.match(codigo):
        raise ValueError("kid inválido")
    partes = [magic, version.to_bytes(2, "big"), bytes([len(codigo)]), codigo]
    for numero in sorted(campos):
        valor = campos[numero]
        if numero not in conocidos:
            raise ValueError(f"etiqueta desconocida: {numero}")
        maximo, critica = conocidos[numero]
        if len(valor) > maximo or len(valor) > MAX_VALOR:
            raise ValueError(f"valor demasiado largo en la etiqueta {numero}")
        partes += [(numero | (CRITICA if critica else 0)).to_bytes(2, "big"), len(valor).to_bytes(2, "big"), valor]
    return b"".join(partes)


def sellar(sin_firma: bytes, firmar: Callable[[bytes], bytes]) -> bytes:
    """Añade la firma (la calcula `firmar` sobre TODO lo anterior). El resultado nunca supera el tope de un archivo."""
    firma = firmar(sin_firma)
    if len(firma) != TAM_FIRMA:
        raise ValueError("la firma no mide 64 bytes")
    datos = sin_firma + firma
    if len(datos) > MAX_ARCHIVO:
        raise ValueError("archivo demasiado grande")
    return datos
