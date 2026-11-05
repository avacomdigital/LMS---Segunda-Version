"""
Identidad de dispositivo (MOD-018, Fase 5, P-24): lo que el nodo sabe comprobar SIN internet sobre la clave que un equipo dice tener.

Dos pruebas, de fuerza distinta, y un nivel de garantía que sale de ellas:

  · PRUEBA DE POSESIÓN  el equipo firma un reto del nodo con su clave EC P-256 (ECDSA, SHA-256). Demuestra que quien habla tiene la clave que declara; no dice DÓNDE vive esa clave.
  · ATESTACIÓN          (sólo Android) la cadena de certificados que el Keystore entrega al crear la clave, con el reto del nodo dentro. Si la cadena llega a una raíz de Google que viaja en
                        el paquete, y dice que la clave vive en un entorno seguro (TEE o StrongBox), con el arranque verificado y el gestor de arranque cerrado, y que la app es la de AVACOM,
                        entonces el equipo tiene el nivel `hardware`.

  hardware   atestación válida de punta a punta (raíz de Google, TEE o StrongBox, arranque verificado, cerrado, app de AVACOM, reto del nodo, llave = la declarada)
  software   la prueba de posesión es válida pero la atestación falta o no pasa algo de lo anterior (un emulador, un Windows con su clave en software o en TPM que el nodo no puede
             comprobar, un arranque desbloqueado…). El motivo queda en el detalle
  declarada  el equipo no tiene clave o no la presentó: sólo la huella que él mismo dice (lo de siempre)

Nada de esto detiene una clase: un nivel bajo no bloquea a nadie por sí solo; el administrador puede pedir un mínimo para dar de alta equipos NUEVOS (política) y lo ya registrado sigue.

Este archivo es puro (sin Django, sin reloj, sin red): recibe `ahora_ms`, las raíces, la lista de revocadas y la política de la app. Una cadena mal formada nunca lanza: es «software» con su motivo.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509 import ObjectIdentifier

HARDWARE, SOFTWARE, DECLARADA = "hardware", "software", "declarada"
GARANTIAS = (DECLARADA, SOFTWARE, HARDWARE)                     # de menor a mayor

OID_ATESTACION = ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")
PREFIJO_DEL_RETO = b"AVACOM-ID1"
MIN_RETO = 16
MAX_CADENA = 6
MAX_EXTENSION = 8192

# attestationSecurityLevel / keymasterSecurityLevel
NIVEL_SOFTWARE, NIVEL_TEE, NIVEL_STRONGBOX = 0, 1, 2
NOMBRES_NIVEL = {NIVEL_SOFTWARE: "software", NIVEL_TEE: "tee", NIVEL_STRONGBOX: "strongbox"}
# verifiedBootState
ARRANQUE_VERIFICADO, ARRANQUE_AUTOFIRMADO, ARRANQUE_NO_VERIFICADO, ARRANQUE_FALLIDO = 0, 1, 2, 3
NOMBRES_ARRANQUE = {0: "verificado", 1: "autofirmado", 2: "no_verificado", 3: "fallido"}
ETIQUETA_RAIZ_DE_CONFIANZA, ETIQUETA_APLICACION = 704, 709

M_OK = "ok"
M_SIN_CADENA = "sin_cadena"
M_CADENA_INVALIDA = "cadena_invalida"
M_RAIZ_DESCONOCIDA = "raiz_desconocida"
M_FUERA_DE_VIGENCIA = "certificado_fuera_de_vigencia"
M_REVOCADO = "certificado_revocado"
M_SIN_EXTENSION = "sin_extension"
M_RETO_DISTINTO = "reto_distinto"
M_CLAVE_DISTINTA = "clave_distinta"
M_NIVEL_SOFTWARE = "clave_en_software"
M_ARRANQUE = "arranque_no_verificado"
M_GESTOR_ABIERTO = "gestor_de_arranque_abierto"
M_APP_AJENA = "app_ajena"
M_PAQUETE_AJENO = "paquete_ajeno"
M_SIN_PRUEBA = "sin_prueba_de_posesion"


class AtestacionInvalida(Exception):
    """La estructura de la extensión no se puede leer. Se convierte en un motivo, no sale del módulo."""


# --------------------------------------------------------------------------------------------------------------------- DER mínimo
@dataclass(frozen=True)
class _Elemento:
    clase: int          # 0 universal · 1 aplicación · 2 contexto · 3 privada
    construido: bool
    numero: int
    contenido: bytes


def _leer(datos: bytes, pos: int = 0) -> tuple[_Elemento, int]:
    """Un elemento DER (etiqueta, largo, contenido) y dónde termina. Sólo largos definidos y topes: lo que no cuadra lanza `AtestacionInvalida`."""
    if pos >= len(datos):
        raise AtestacionInvalida("fin_inesperado")
    primero = datos[pos]
    pos += 1
    clase, construido, numero = primero >> 6, bool(primero & 0x20), primero & 0x1F
    if numero == 0x1F:                                     # etiqueta de varios bytes (704 y 709 lo son)
        numero = 0
        for _ in range(4):
            if pos >= len(datos):
                raise AtestacionInvalida("etiqueta_truncada")
            byte = datos[pos]
            pos += 1
            numero = (numero << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
        else:
            raise AtestacionInvalida("etiqueta_larga")
    if pos >= len(datos):
        raise AtestacionInvalida("largo_truncado")
    largo = datos[pos]
    pos += 1
    if largo & 0x80:
        cuantos = largo & 0x7F
        if not 1 <= cuantos <= 3 or pos + cuantos > len(datos):
            raise AtestacionInvalida("largo_invalido")
        largo = int.from_bytes(datos[pos:pos + cuantos], "big")
        pos += cuantos
    if pos + largo > len(datos):
        raise AtestacionInvalida("contenido_truncado")
    return _Elemento(clase, construido, numero, bytes(datos[pos:pos + largo])), pos + largo


def _hijos(contenido: bytes) -> list[_Elemento]:
    salida, pos = [], 0
    while pos < len(contenido):
        elemento, pos = _leer(contenido, pos)
        salida.append(elemento)
        if len(salida) > 128:
            raise AtestacionInvalida("demasiados_elementos")
    return salida


def _entero(e: _Elemento) -> int:
    if e.clase != 0 or e.numero not in (2, 10) or not e.contenido or len(e.contenido) > 9:
        raise AtestacionInvalida("entero")
    return int.from_bytes(e.contenido, "big", signed=True)


def _octetos(e: _Elemento) -> bytes:
    if e.clase != 0 or e.numero != 4:
        raise AtestacionInvalida("octetos")
    return e.contenido


def _booleano(e: _Elemento) -> bool:
    if e.clase != 0 or e.numero != 1 or len(e.contenido) != 1:
        raise AtestacionInvalida("booleano")
    return e.contenido[0] != 0


# --------------------------------------------------------------------------------------------------------------------- KeyDescription
@dataclass(frozen=True)
class Descripcion:
    """Lo que dice la extensión `1.3.6.1.4.1.11129.2.1.17` de la hoja. Lo que falta queda en `None`."""

    version: int
    nivel_atestacion: int
    nivel_llave: int
    reto: bytes
    arranque: int | None = None
    bloqueado: bool | None = None
    paquetes: tuple[str, ...] = ()
    firmas_app: tuple[bytes, ...] = ()
    ubicaciones: tuple[str, ...] = field(default_factory=tuple)      # dónde se encontró la raíz de confianza (informativo)


def leer_descripcion(extension: bytes) -> Descripcion:
    if len(extension) > MAX_EXTENSION:
        raise AtestacionInvalida("demasiado_grande")
    raiz, fin = _leer(extension)
    if fin != len(extension) or raiz.clase != 0 or raiz.numero != 16 or not raiz.construido:
        raise AtestacionInvalida("no_es_una_secuencia")
    campos = _hijos(raiz.contenido)
    if len(campos) < 8:
        raise AtestacionInvalida("pocos_campos")
    version, nivel_atestacion, _km, nivel_llave = (_entero(campos[0]), _entero(campos[1]), _entero(campos[2]), _entero(campos[3]))
    reto = _octetos(campos[4])
    arranque: int | None = None
    bloqueado: bool | None = None
    paquetes: list[str] = []
    firmas: list[bytes] = []
    donde: list[str] = []
    for nombre, lista in (("tee", campos[7]), ("software", campos[6])):          # primero lo que impone el entorno seguro; si no, lo del sistema
        if lista.numero != 16:
            raise AtestacionInvalida("lista_de_autorizacion")
        for item in _hijos(lista.contenido):
            if item.clase != 2 or not item.construido:
                continue
            interior = _hijos(item.contenido)
            if item.numero == ETIQUETA_RAIZ_DE_CONFIANZA and arranque is None and interior:
                raiz_conf = _hijos(interior[0].contenido)
                if len(raiz_conf) >= 3:
                    bloqueado, arranque = _booleano(raiz_conf[1]), _entero(raiz_conf[2])
                    donde.append(nombre)
            elif item.numero == ETIQUETA_APLICACION and not paquetes and interior:
                paquetes, firmas = _aplicacion(_octetos(interior[0]))
    return Descripcion(version, nivel_atestacion, nivel_llave, reto, arranque, bloqueado, tuple(paquetes), tuple(firmas), tuple(donde))


def _aplicacion(contenido: bytes) -> tuple[list[str], list[bytes]]:
    secuencia, _ = _leer(contenido)
    partes = _hijos(secuencia.contenido)
    if len(partes) < 2:
        raise AtestacionInvalida("aplicacion")
    paquetes: list[str] = []
    for info in _hijos(partes[0].contenido):
        nombre = _octetos(_hijos(info.contenido)[0])
        paquetes.append(nombre.decode("utf-8", "replace"))
    firmas = [_octetos(e) for e in _hijos(partes[1].contenido)]
    return paquetes, firmas


# --------------------------------------------------------------------------------------------------------------------- política y resultado
@dataclass(frozen=True)
class Raiz:
    nombre: str
    spki: bytes                  # SubjectPublicKeyInfo DER: se compara la llave, no el nombre
    desde_ms: int
    hasta_ms: int


@dataclass(frozen=True)
class PoliticaDeApp:
    """La app que se acepta: el paquete y los SHA-256 de los certificados con que se firma (de AVACOM). Vacía = no se puede comprobar la app (todo cae a software)."""

    paquetes: frozenset[str] = frozenset()
    firmas: frozenset[bytes] = frozenset()


@dataclass(frozen=True)
class Resultado:
    garantia: str
    motivo: str
    detalle: dict = field(default_factory=dict)


def mensaje_del_reto(nonce: bytes, identificador_hw: str) -> bytes:
    """Lo que el equipo firma: el reto del nodo atado a SU huella declarada (la prueba no sirve para otro equipo)."""
    return PREFIJO_DEL_RETO + bytes(nonce) + identificador_hw.encode("utf-8")


def huella_de_clave(spki: bytes) -> str:
    """SHA-256 (hex) de la llave pública: con ella se reconoce a un equipo sin guardar la llave en las pantallas."""
    return hashlib.sha256(bytes(spki)).hexdigest()


def cargar_clave_publica(spki: bytes) -> ec.EllipticCurvePublicKey:
    clave = serialization.load_der_public_key(bytes(spki))
    if not isinstance(clave, ec.EllipticCurvePublicKey) or not isinstance(clave.curve, ec.SECP256R1):
        raise ValueError("la clave no es EC P-256")
    return clave


def _a_der(firma: bytes) -> bytes:
    """Android (Java) entrega la firma ECDSA en DER; Windows (CNG) en formato P1363 (r y s de 32 bytes cada uno). Se aceptan las dos."""
    if len(firma) == 64:
        return encode_dss_signature(int.from_bytes(firma[:32], "big"), int.from_bytes(firma[32:], "big"))
    return bytes(firma)


def verificar_posesion(spki: bytes, firma: bytes, nonce: bytes, identificador_hw: str) -> bool:
    """¿El dueño de esta llave firmó este reto para este equipo? La firma puede venir en DER (Android) o en P1363 de 64 bytes (CNG). Nunca lanza."""
    try:
        cargar_clave_publica(spki).verify(_a_der(firma), mensaje_del_reto(nonce, identificador_hw), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# --------------------------------------------------------------------------------------------------------------------- la cadena
def _spki(certificado: x509.Certificate) -> bytes:
    return certificado.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _fuera_de_vigencia(c: x509.Certificate, ahora_ms: int) -> bool:
    desde = int(c.not_valid_before_utc.timestamp() * 1000)
    hasta = int(c.not_valid_after_utc.timestamp() * 1000)
    return not desde <= ahora_ms <= hasta


def _serial_revocado(c: x509.Certificate, revocadas: frozenset[str]) -> bool:
    return str(c.serial_number) in revocadas or format(c.serial_number, "x") in revocadas


def evaluar(*, spki_declarada: bytes, nonce: bytes, cadena_der: Iterable[bytes], ahora_ms: int, raices: Iterable[Raiz], revocadas: frozenset[str],
            app: PoliticaDeApp) -> Resultado:
    """
    El nivel que se gana con la atestación de Android. Se llama sólo con la prueba de posesión ya verificada. Devuelve `hardware` o `software` con el PRIMER motivo que falló;
    jamás lanza y jamás da `hardware` si algo no se pudo comprobar.
    """
    cadena = list(cadena_der)
    if not cadena:
        return Resultado(SOFTWARE, M_SIN_CADENA)
    if len(cadena) > MAX_CADENA or len(nonce) < MIN_RETO:
        return Resultado(SOFTWARE, M_CADENA_INVALIDA)
    try:
        certs = [x509.load_der_x509_certificate(bytes(c)) for c in cadena]
    except ValueError:
        return Resultado(SOFTWARE, M_CADENA_INVALIDA)
    detalle: dict = {"certificados": len(certs)}
    try:
        for i in range(len(certs) - 1):
            certs[i].verify_directly_issued_by(certs[i + 1])
        certs[-1].verify_directly_issued_by(certs[-1])        # la última es autofirmada: una raíz
    except (ValueError, TypeError, InvalidSignature):
        return Resultado(SOFTWARE, M_CADENA_INVALIDA, detalle)
    raiz = next((r for r in raices if r.spki == _spki(certs[-1])), None)
    if raiz is None:
        return Resultado(SOFTWARE, M_RAIZ_DESCONOCIDA, detalle)
    detalle["raiz"] = raiz.nombre
    if not raiz.desde_ms <= ahora_ms <= raiz.hasta_ms or any(_fuera_de_vigencia(c, ahora_ms) for c in certs[1:]):
        return Resultado(SOFTWARE, M_FUERA_DE_VIGENCIA, detalle)
    if any(_serial_revocado(c, revocadas) for c in certs):
        return Resultado(SOFTWARE, M_REVOCADO, detalle)
    hoja = certs[0]
    if _spki(hoja) != bytes(spki_declarada):
        return Resultado(SOFTWARE, M_CLAVE_DISTINTA, detalle)
    try:
        extensiones = [e for e in hoja.extensions if e.oid == OID_ATESTACION]
        if len(extensiones) != 1:
            return Resultado(SOFTWARE, M_SIN_EXTENSION, detalle)
        descripcion = leer_descripcion(extensiones[0].value.value)
    except (AtestacionInvalida, ValueError, AttributeError):
        return Resultado(SOFTWARE, M_SIN_EXTENSION, detalle)
    detalle.update({"version_atestacion": descripcion.version, "nivel": NOMBRES_NIVEL.get(descripcion.nivel_atestacion, "desconocido"),
                    "arranque": NOMBRES_ARRANQUE.get(descripcion.arranque, "sin_dato"), "gestor_cerrado": descripcion.bloqueado})
    if descripcion.reto != bytes(nonce):
        return Resultado(SOFTWARE, M_RETO_DISTINTO, detalle)
    if descripcion.nivel_atestacion not in (NIVEL_TEE, NIVEL_STRONGBOX) or descripcion.nivel_llave not in (NIVEL_TEE, NIVEL_STRONGBOX):
        return Resultado(SOFTWARE, M_NIVEL_SOFTWARE, detalle)
    if descripcion.arranque != ARRANQUE_VERIFICADO:
        return Resultado(SOFTWARE, M_ARRANQUE, detalle)
    if descripcion.bloqueado is not True:
        return Resultado(SOFTWARE, M_GESTOR_ABIERTO, detalle)
    if not app.paquetes or not app.firmas or not descripcion.paquetes or not set(descripcion.paquetes) <= app.paquetes:
        return Resultado(SOFTWARE, M_PAQUETE_AJENO, detalle)
    if not descripcion.firmas_app or not set(descripcion.firmas_app) <= app.firmas:
        return Resultado(SOFTWARE, M_APP_AJENA, detalle)
    return Resultado(HARDWARE, M_OK, detalle)


def al_menos(garantia: str, minimo: str) -> bool:
    """¿`garantia` llega al `minimo` que pide la política? Un valor desconocido no llega a nada."""
    return garantia in GARANTIAS and minimo in GARANTIAS and GARANTIAS.index(garantia) >= GARANTIAS.index(minimo)
