r"""
El pase de soporte de AVACOM (D-2): lo que hace que exportar y restaurar sean SÓLO de las personas que tienen el software de AVACOM WORLD. El permiso lo da el rol; el pase lo da quien
tiene la llave privada de AVACOM. Un técnico que no es de AVACOM —o una cuenta de técnico creada por la propia institución— no puede producirlo.

    AVSP · largo del kid (u8) · kid · firma Ed25519 (64) · payload JSON canónico

  · La firma cubre `AVSP|kid|payload`: nadie cambia el kid ni el contenido. El algoritmo está fijado (sin `alg`), como en las licencias y en las actualizaciones.
  · El payload dice quién (`tecnico`, un rótulo), cuándo (`emitido_en`, `vence_en`: un día como máximo), para qué (`acciones`, permisos `backup.*`) y para qué equipo (`nodo`: el
    identificador del nodo o `*` para cualquiera: una restauración en un equipo NUEVO no puede saber de antemano su identificador).
  · Un pase se usa UNA vez (`pase_id` queda registrado, sólo inserción): una copia del archivo no sirve para una segunda operación.
  · Las llaves públicas que el nodo acepta son las de `respaldo/claves/`; en producción, sólo las de producción (vacías hasta la ceremonia de llaves: ver 01-diseno.md).

Puro: no importa Django. Usa `cryptography`, que ya viaja en el runtime del nodo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import catalogos as cat
from .errores import PaseInvalido

MAGIC = b"AVSP"
FORMATO = 1
_MAX_PAYLOAD = 2048
_P = 2 ** 255 - 19
# Los puntos de orden pequeño de Ed25519 (0, 1, p-1, los dos de orden 8 y las codificaciones no canónicas): con ellos una «firma universal» valdría para cualquier mensaje.
_Y_PEQUENO = frozenset({0, 1, _P - 1, _P, _P + 1,
                        int.from_bytes(bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"), "little"),
                        int.from_bytes(bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"), "little")})


@dataclass(frozen=True)
class Pase:
    pase_id: str
    tecnico: str
    emitido_en: int
    vence_en: int
    acciones: tuple[str, ...]
    nodo: str
    kid: str
    motivo: str = ""

    def a_dict(self) -> dict:
        return {"pase_id": self.pase_id, "tecnico": self.tecnico, "emitido_en": self.emitido_en, "vence_en": self.vence_en, "acciones": list(self.acciones), "nodo": self.nodo,
                "kid": self.kid, "motivo": self.motivo}


def _pequeno(codificado: bytes) -> bool:
    return (int.from_bytes(bytes(codificado), "little") & ((1 << 255) - 1)) in _Y_PEQUENO


def _verificar_firma(clave: bytes, firma: bytes, mensaje: bytes) -> bool:
    if len(clave) != 32 or len(firma) != 64 or _pequeno(clave) or _pequeno(firma[:32]):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(bytes(clave)).verify(bytes(firma), bytes(mensaje))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _canonico(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def firmar(payload: dict, kid: str, clave_privada) -> bytes:
    """Lo usa el EMISOR de AVACOM (`tools/respaldo/`) y las pruebas; el nodo nunca firma un pase. `clave_privada` es un `Ed25519PrivateKey`."""
    cuerpo = _canonico({"formato": FORMATO, **payload})
    k = kid.encode("ascii")
    firma = clave_privada.sign(MAGIC + b"|" + k + b"|" + cuerpo)
    return MAGIC + bytes([len(k)]) + k + firma + cuerpo


def abrir(datos: bytes, publicas: dict[str, bytes], ahora_ms: int, permiso: str, nodo_id: str) -> Pase:
    """Verifica el pase ANTES de interpretar lo que dice y devuelve lo que autoriza. Lanza `PaseInvalido` con un motivo estable (`PaseInvalido.motivo`)."""
    datos = bytes(datos or b"")
    if len(datos) < 5 + 64 + 2 or datos[:4] != MAGIC or len(datos) > _MAX_PAYLOAD + 128:
        raise PaseInvalido("formato")
    largo_kid = datos[4]
    if largo_kid == 0 or len(datos) < 5 + largo_kid + 64 + 2:
        raise PaseInvalido("formato")
    try:
        kid = datos[5:5 + largo_kid].decode("ascii")
    except UnicodeDecodeError:
        raise PaseInvalido("formato") from None
    firma = datos[5 + largo_kid:5 + largo_kid + 64]
    cuerpo = datos[5 + largo_kid + 64:]
    if len(cuerpo) > _MAX_PAYLOAD:
        raise PaseInvalido("formato")
    clave = publicas.get(kid)
    if clave is None:
        raise PaseInvalido("kid_desconocido")
    if not _verificar_firma(clave, firma, MAGIC + b"|" + kid.encode("ascii") + b"|" + cuerpo):
        raise PaseInvalido("firma_invalida")
    try:
        p = json.loads(cuerpo.decode("ascii"))
        if not isinstance(p, dict) or p.get("formato") != FORMATO or _canonico(p) != cuerpo:
            raise ValueError
        acciones = p["acciones"]
        pase = Pase(pase_id=str(p["pase_id"]), tecnico=str(p["tecnico"])[:120], emitido_en=int(p["emitido_en"]), vence_en=int(p["vence_en"]),
                    acciones=tuple(str(a) for a in acciones), nodo=str(p.get("nodo") or "*"), kid=kid, motivo=str(p.get("motivo") or "")[:cat.MAX_NOTA])
        if not pase.pase_id or not isinstance(acciones, list) or not pase.acciones or any(a not in cat.PERMISOS_CON_PASE for a in pase.acciones):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise PaseInvalido("contenido") from None
    if pase.vence_en - pase.emitido_en > cat.VIGENCIA_PASE_MAX_MS or pase.vence_en <= pase.emitido_en:
        raise PaseInvalido("vigencia_excesiva")
    if ahora_ms + cat.TOLERANCIA_PASE_MS < pase.emitido_en:
        raise PaseInvalido("aun_no_vigente")
    if ahora_ms > pase.vence_en:
        raise PaseInvalido("vencido")
    if permiso not in pase.acciones:
        raise PaseInvalido("accion_no_incluida")
    if pase.nodo != "*" and pase.nodo != nodo_id:
        raise PaseInvalido("otro_equipo")
    return pase
