"""
Identidad de dispositivo (MOD-018, Fase 5, P-24): los casos de uso. El dominio (`dominio/atestacion.py`) sabe comprobar; aquí se arma el recorrido:

    reto      el nodo emite un reto de 32 bytes, de un solo uso y con vencimiento (público: es el equipo el que se presenta)
    enrolar   el equipo trae su clave pública, la firma del reto y (en Android) la cadena de atestación; el nodo verifica, decide el nivel de garantía y lo guarda en `device_manager`

Se identifica AL ABRIR SESIÓN (y en el primer contacto): no hay una firma por petición. Un equipo sin clave, o cuya prueba falla, SIGUE funcionando con garantía `declarada` o `software`:
esto nunca decide si una tableta entra a clase (OQ-043, R-01). Lo único que puede exigir la licencia es un nivel mínimo para dar de alta un equipo NUEVO.
"""
from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass

from ..dominio import atestacion as at
from ..dominio.errores import DatosInvalidos, IdentidadInvalida, IdentidadRequerida, RetoInvalido
from .base import Actor, _CasoDeUso

log = logging.getLogger("avacom.licenciamiento")

MAX_CADENA_B64 = 8192             # el tope de un certificado de atestación real ronda 1 KB; la cadena entera, 4 KB
MAX_ELEMENTOS = at.MAX_CADENA


@dataclass(frozen=True)
class Verificada:
    """Una prueba de clave ya comprobada: lo que se guarda en el equipo y lo que se responde."""

    clave_publica: str          # SubjectPublicKeyInfo en base64 (pública)
    clave_huella: str           # SHA-256 hex de la llave
    garantia: str
    motivo: str
    detalle: dict
    con_cadena: bool


def _b64(valor, campo: str, maximo: int = MAX_CADENA_B64) -> bytes:
    if not isinstance(valor, str) or not valor or len(valor) > maximo:
        raise DatosInvalidos(f"Falta `{campo}` o no tiene la forma esperada (base64).", campo=campo)
    try:
        return base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError):
        raise DatosInvalidos(f"`{campo}` no es base64 válido.", campo=campo) from None


def verificar_prueba(s, identificador_hw: str, prueba: dict) -> Verificada:
    """
    La prueba de clave de un equipo. El reto se CONSUME primero (vale una vez, salga como salga lo demás: no hay forma de usar la respuesta del nodo como oráculo), luego se comprueba la
    posesión y, si trae cadena, la atestación. Lanza `RetoInvalido` o `IdentidadInvalida` (400); jamás deja pasar algo sin firma válida.
    """
    if not isinstance(prueba, dict):
        raise DatosInvalidos("La identidad debe ser un objeto con nonce, clave_publica, firma y (opcional) cadena.")
    nonce = _b64(prueba.get("nonce"), "nonce", 128)
    ahora = s.reloj.ahora_ms()
    if len(nonce) < at.MIN_RETO or not s.retos.consumir(nonce, ahora):
        raise RetoInvalido()
    spki = _b64(prueba.get("clave_publica"), "clave_publica", 512)
    firma = _b64(prueba.get("firma"), "firma", 256)
    try:
        at.cargar_clave_publica(spki)
    except ValueError:
        raise IdentidadInvalida("La clave no es una clave pública EC P-256 válida.", motivo="clave") from None
    if not at.verificar_posesion(spki, firma, nonce, identificador_hw):
        raise IdentidadInvalida("La firma del reto no corresponde a esa clave y a este equipo.", motivo="firma")
    cadena_b64 = prueba.get("cadena") or []
    if not isinstance(cadena_b64, list) or len(cadena_b64) > MAX_ELEMENTOS:
        raise DatosInvalidos("`cadena` debe ser una lista corta de certificados en base64.", campo="cadena")
    cadena = [_b64(c, "cadena") for c in cadena_b64]
    resultado = _evaluar(s, spki, nonce, cadena, ahora)
    detalle = {**resultado.detalle, "motivo": resultado.motivo}
    proveedor = str(prueba.get("proveedor") or "")[:24]
    if proveedor:
        detalle["proveedor_declarado"] = proveedor          # lo que el equipo DICE de dónde vive su clave: informativo, nunca sube el nivel
    return Verificada(base64.b64encode(spki).decode("ascii"), at.huella_de_clave(spki), resultado.garantia, resultado.motivo, detalle, bool(cadena))


def _evaluar(s, spki: bytes, nonce: bytes, cadena: list[bytes], ahora: int) -> at.Resultado:
    if not cadena:
        return at.Resultado(at.SOFTWARE, at.M_SIN_CADENA)
    try:
        return at.evaluar(spki_declarada=spki, nonce=nonce, cadena_der=cadena, ahora_ms=ahora, raices=s.atestacion.raices(), revocadas=s.atestacion.revocadas(), app=s.atestacion.app())
    except Exception:   # noqa: BLE001 — una atestación que no se puede evaluar es «software», nunca un error que frene al equipo
        log.exception("No se pudo evaluar la atestación de un equipo", extra={"evento": "licencia.identidad_fallo", "ruta": "bad"})
        return at.Resultado(at.SOFTWARE, at.M_CADENA_INVALIDA)


class EmitirReto(_CasoDeUso):
    def ejecutar(self) -> dict:
        nonce, vence = self.s.retos.entregar(self.s.reloj.ahora_ms())
        return {"nonce": base64.b64encode(nonce).decode("ascii"), "vence_en": vence, "algoritmo": "ecdsa-p256-sha256", "contexto": at.PREFIJO_DEL_RETO.decode("ascii")}


class Enrolar(_CasoDeUso):
    """Público (como el latido): el equipo se identifica antes de tener sesión y otra vez al abrirla. Guarda la identidad en `device_manager`; no lo bloquea nunca."""

    def ejecutar(self, datos: dict) -> dict:
        identificador_hw = str(datos.get("identificador_hw") or datos.get("identificador") or "").strip()
        if not identificador_hw or len(identificador_hw) > 128:
            raise DatosInvalidos("Falta identificador_hw (la huella con que el equipo se registró).")
        prueba = datos.get("identidad") if isinstance(datos.get("identidad"), dict) else datos
        v = verificar_prueba(self.s, identificador_hw, prueba)
        previo = self.s.equipos.de(identificador_hw)
        # Con clave ya enrolada y SIN cadena es una confirmación de sesión: se conserva el nivel (no se baja a «software» por no traer la cadena otra vez).
        garantia = None if previo and not v.con_cadena else v.garantia
        actor = identificador_hw
        equipo = self.s.equipos.registrar(identificador_hw, v.clave_publica, v.clave_huella, garantia, v.detalle, self.s.reloj.ahora_ms(), actor)
        if v.con_cadena and v.garantia != at.HARDWARE:
            log.info("Atestación sin nivel hardware: %s", v.motivo, extra={"evento": "licencia.identidad_software", "ruta": "ok"})
        return {"garantia": equipo["garantia"], "motivo": v.motivo if garantia is not None else "confirmada", "clave_huella": equipo["clave_huella"], "dispositivo_id": equipo["id"],
                "confirmada_en": equipo.get("garantia_en"), "detalle": equipo.get("garantia_detalle") or {}}


def identidad_de_equipo_nuevo(s, identidad: dict | None, identificador_hw: str, estricta: bool) -> dict | None:
    """
    El gancho del cupo (`servicios.exigir_equipo_nuevo`): verifica la prueba que trae un equipo NUEVO y devuelve lo que se guarda en él, o None si no hay prueba válida.
    `estricta` (nodo de producción) aplica el mínimo que fija la licencia: sin el nivel pedido, `IdentidadRequerida` (402) y el equipo no se da de alta; lo registrado antes no se toca.
    """
    minimo = s.config.identidad_minima if s.config.identidad_minima in at.GARANTIAS else at.DECLARADA
    verificada: Verificada | None = None
    if identidad:
        try:
            verificada = verificar_prueba(s, identificador_hw, identidad)
        except (RetoInvalido, IdentidadInvalida, DatosInvalidos) as error:
            log.warning("La prueba de clave de un equipo nuevo no pasó: %s", error.codigo, extra={"evento": "licencia.identidad_rechazada", "ruta": "bad"})
    nivel = verificada.garantia if verificada else at.DECLARADA
    if estricta and not at.al_menos(nivel, minimo):
        raise IdentidadRequerida(f"Para dar de alta un equipo nuevo, la licencia pide identidad con garantía «{minimo}» y este llegó con «{nivel}».", minimo=minimo, nivel=nivel)
    if verificada is None:
        return None
    return {"clave_publica": verificada.clave_publica, "clave_huella": verificada.clave_huella, "garantia": verificada.garantia, "garantia_detalle": verificada.detalle}


__all__ = ["Actor", "EmitirReto", "Enrolar", "Verificada", "identidad_de_equipo_nuevo", "verificar_prueba"]
