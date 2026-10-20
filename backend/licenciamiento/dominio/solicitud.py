"""
Lo que el nodo escribe y firma con SU propia llave (no la de AVACOM): la solicitud de licencia (`.avreq`) y la prueba de liberación (`.avrel`).

  .avreq   nonce · versión del nodo · creada · nivel de huella · huella (k de n factores, hasheados) · llave pública del nodo · licencia vigente (si hay) · aula (informativo)
  .avrel   id de la licencia que se libera · serie · liberada · nonce · llave pública del nodo

Van firmadas con la llave del nodo (Ed25519) y su `kid` ES la llave pública en hexadecimal: el emisor las verifica contra sí mismas, lo que demuestra que quien pide posee esa llave
y que nadie alteró la huella en el camino. NO llevan identificadores crudos del equipo (sólo hashes con clave de producto), ni datos de personas, ni el nombre del colegio salvo el
rótulo del aula que el propio administrador ya conoce.

Como el aula no tiene internet, el nodo NO puede saber si su licencia está activa en otro equipo: lo sabe el emisor y lo escribe en la licencia (`LIBERACION_PENDIENTE`).
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from . import firma, licencia, tlv
from .errores import LicenciaInvalida
from .huella import NIVEL_HARDWARE, NIVEL_INSTALACION

# --------------------------------------------------------------------------------------------------------------- solicitud (.avreq)
R_NONCE, R_VERSION, R_CREADA, R_NIVEL, R_HUELLA, R_CLAVE_NODO, R_LICENCIA, R_AULA = range(1, 9)
CONOCIDOS_SOLICITUD: dict[int, tuple[int, bool]] = {
    R_NONCE: (16, True), R_VERSION: (32, False), R_CREADA: (8, True), R_NIVEL: (1, True), R_HUELLA: (2 + 16 * 33, True), R_CLAVE_NODO: (32, True),
    R_LICENCIA: (16, False), R_AULA: (480, False),
}
_NIVELES = {1: NIVEL_HARDWARE, 2: NIVEL_INSTALACION}
_CODIGO_DE_NIVEL = {v: k for k, v in _NIVELES.items()}


@dataclass(frozen=True)
class Solicitud:
    nonce: bytes
    version_nodo: str
    creada: int
    nivel: str
    huella: licencia.HuellaDeLicencia
    clave_nodo: bytes
    licencia_vigente: str | None
    aula: str
    sha256: str = ""


def construir_solicitud(clave_privada: bytes, *, nonce: bytes, version_nodo: str, creada: int, nivel: str, huella: licencia.HuellaDeLicencia,
                        licencia_vigente: str | None = None, aula: str = "") -> bytes:
    if len(nonce) != 16:
        raise ValueError("el nonce mide 16 bytes")
    clave_nodo = firma.publica_de(clave_privada)
    campos = {
        R_NONCE: bytes(nonce), R_CREADA: int(creada).to_bytes(8, "big"), R_NIVEL: bytes([_CODIGO_DE_NIVEL[nivel]]),
        R_HUELLA: licencia.codificar_huella(huella), R_CLAVE_NODO: clave_nodo,
    }
    if version_nodo:
        campos[R_VERSION] = version_nodo.encode("utf-8")[:32]
    if licencia_vigente:
        campos[R_LICENCIA] = uuid.UUID(licencia_vigente).bytes
    if aula:
        campos[R_AULA] = aula.encode("utf-8")[:480]
    sin_firma = tlv.escribir(tlv.MAGIC_SOLICITUD, clave_nodo.hex(), campos, CONOCIDOS_SOLICITUD)
    return tlv.sellar(sin_firma, lambda datos: firma.firmar(clave_privada, datos))


def leer_solicitud(datos: bytes, verificador: firma.Verificador = firma.verificar) -> Solicitud:
    """Lo que el EMISOR hace con un `.avreq`: verificar que lo firmó la llave que declara y leer la huella. (El nodo también la usa para reconocer una solicitud propia.)"""
    abierto = firma.abrir_autofirmado(datos, tlv.MAGIC_SOLICITUD, CONOCIDOS_SOLICITUD, verificador)
    c = abierto.campos
    for etiqueta in (R_NONCE, R_CREADA, R_NIVEL, R_HUELLA, R_CLAVE_NODO):
        if etiqueta not in c:
            raise LicenciaInvalida("campo_faltante")
    if len(c[R_NONCE]) != 16 or len(c[R_CREADA]) != 8 or len(c[R_NIVEL]) != 1 or len(c[R_CLAVE_NODO]) != 32 or c[R_CLAVE_NODO].hex() != abierto.kid:
        raise LicenciaInvalida("campo_invalido")
    nivel = _NIVELES.get(c[R_NIVEL][0])
    if nivel is None:
        raise LicenciaInvalida("campo_invalido")
    vigente = None
    if R_LICENCIA in c:
        if len(c[R_LICENCIA]) != 16:
            raise LicenciaInvalida("campo_invalido")
        vigente = str(uuid.UUID(bytes=c[R_LICENCIA]))
    return Solicitud(bytes(c[R_NONCE]), _texto(c.get(R_VERSION, b"")), int.from_bytes(c[R_CREADA], "big"), nivel, licencia.decodificar_huella(c[R_HUELLA]),
                     bytes(c[R_CLAVE_NODO]), vigente, _texto(c.get(R_AULA, b"")), abierto.sha256)


def _texto(valor: bytes) -> str:
    try:
        return valor.decode("utf-8")
    except UnicodeDecodeError:
        raise LicenciaInvalida("campo_invalido") from None


# --------------------------------------------------------------------------------------------------------------- liberación (.avrel)
L_LICENCIA, L_SERIE, L_LIBERADA, L_NONCE, L_CLAVE_NODO = range(1, 6)
CONOCIDOS_LIBERACION: dict[int, tuple[int, bool]] = {
    L_LICENCIA: (16, True), L_SERIE: (4, True), L_LIBERADA: (8, True), L_NONCE: (16, True), L_CLAVE_NODO: (32, True),
}


@dataclass(frozen=True)
class Liberacion:
    licencia_id: str
    serie: int
    liberada: int
    nonce: bytes
    clave_nodo: bytes
    sha256: str = ""


def construir_liberacion(clave_privada: bytes, *, licencia_id: str, serie: int, liberada: int, nonce: bytes) -> bytes:
    if len(nonce) != 16:
        raise ValueError("el nonce mide 16 bytes")
    clave_nodo = firma.publica_de(clave_privada)
    campos = {
        L_LICENCIA: uuid.UUID(licencia_id).bytes, L_SERIE: int(serie).to_bytes(4, "big"), L_LIBERADA: int(liberada).to_bytes(8, "big"),
        L_NONCE: bytes(nonce), L_CLAVE_NODO: clave_nodo,
    }
    sin_firma = tlv.escribir(tlv.MAGIC_LIBERACION, clave_nodo.hex(), campos, CONOCIDOS_LIBERACION)
    return tlv.sellar(sin_firma, lambda datos: firma.firmar(clave_privada, datos))


def leer_liberacion(datos: bytes, verificador: firma.Verificador = firma.verificar) -> Liberacion:
    abierto = firma.abrir_autofirmado(datos, tlv.MAGIC_LIBERACION, CONOCIDOS_LIBERACION, verificador)
    c = abierto.campos
    for etiqueta in (L_LICENCIA, L_SERIE, L_LIBERADA, L_NONCE, L_CLAVE_NODO):
        if etiqueta not in c:
            raise LicenciaInvalida("campo_faltante")
    if len(c[L_LICENCIA]) != 16 or len(c[L_SERIE]) != 4 or len(c[L_LIBERADA]) != 8 or len(c[L_NONCE]) != 16 or len(c[L_CLAVE_NODO]) != 32 or c[L_CLAVE_NODO].hex() != abierto.kid:
        raise LicenciaInvalida("campo_invalido")
    return Liberacion(str(uuid.UUID(bytes=c[L_LICENCIA])), int.from_bytes(c[L_SERIE], "big"), int.from_bytes(c[L_LIBERADA], "big"), bytes(c[L_NONCE]), bytes(c[L_CLAVE_NODO]),
                      abierto.sha256)


def campos_de_solicitud(s: Solicitud) -> Mapping[str, object]:
    """Lo que se puede MOSTRAR de una solicitud (el emisor la inspecciona): sin los hashes crudos."""
    return {"nivel": s.nivel, "k": s.huella.k, "factores": len(s.huella.factores), "version_nodo": s.version_nodo, "aula": s.aula, "creada": s.creada}
