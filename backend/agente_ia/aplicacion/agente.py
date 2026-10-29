"""
Los casos de uso del agente de IA: preguntar (pasos 1 y 2 del contrato), hablar (pasos 3 y 4) y el estado del servicio.

Regla de oro: NADA de lo que pase con la IA rompe el aula. Cada fallo —el servicio apagado, el modelo sin instalar, un tiempo agotado, una respuesta que no es lo que se esperaba, un
error nuestro— sale como un `ErrorDeIa` con código, y ANTES de salir queda asentado en la bitácora y en el log (`Registro`). Un fallo al registrar tampoco rompe nada.

Esta capa no conoce el framework: el cliente HTTP, la configuración, el registro y el candado de la voz entran por el constructor.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from ..dominio import wav
from ..dominio.conversacion import conversacion_de
from ..dominio.errores import ErrorDeIa
from ..dominio.troceo import trocear

REINTENTOS_VOZ_OCUPADA = (0.5, 1.0, 1.5)        # espera antes de cada reintento de `tts_busy`: lo único que se reintenta solo (todo lo demás no mejora reintentando)
VELOCIDAD_MIN, VELOCIDAD_MAX = 0.5, 2.0


@dataclass(frozen=True)
class Actor:
    id: str | None
    es_personal: bool = True


@dataclass(frozen=True)
class Voz:
    wav: bytes
    duracion_ms: int
    trozos: int


class Registro(Protocol):
    def consulta_ok(self, actor: Actor, conversacion: str | None, cifras: dict) -> None: ...
    def voz_ok(self, actor: Actor, cifras: dict) -> None: ...
    def fallo(self, accion: str, actor: Actor, conversacion: str | None, error: ErrorDeIa, cifras: dict) -> None: ...
    def validacion(self, operacion: str, actor: Actor, error: ErrorDeIa) -> None: ...
    def estado(self, actor: Actor, cifras: dict, disponible: bool) -> None: ...


class Agente:
    def __init__(self, configuracion: Callable, cliente_de: Callable, registro: Registro, candado_voz: threading.Lock,
                 dormir: Callable[[float], None] = time.sleep, reloj: Callable[[], float] = time.monotonic):
        self._configuracion = configuracion
        self._cliente_de = cliente_de
        self._registro = registro
        self._candado_voz = candado_voz
        self._dormir = dormir
        self._reloj = reloj

    # ------------------------------------------------------------------ preguntar (pasos 1 y 2)

    def preguntar(self, actor: Actor, pregunta: str | None, id_de_pantalla: str | None) -> dict:
        cfg = self._configuracion()
        conversacion = conversacion_de(actor.id, id_de_pantalla)
        texto = (pregunta or "").strip()
        try:
            self._habilitada(cfg)
            if not texto:
                raise ErrorDeIa("question_required")
            if len(texto) > cfg.pregunta_max:
                raise ErrorDeIa("question_too_long", f"{len(texto)} > {cfg.pregunta_max}")
        except ErrorDeIa as error:
            self._rechazar("preguntar", "agente_ia.consulta_fallida", actor, conversacion, error, {"longitud_pregunta": len(texto)})
            raise
        inicio = self._reloj()
        cifras = {"longitud_pregunta": len(texto)}
        try:
            doc = self._cliente_de(cfg).consultar(texto, conversacion, cfg.max_tokens)
            respuesta = str(doc["response"]).strip()
        except ErrorDeIa as error:
            self._fallar("agente_ia.consulta_fallida", actor, conversacion, error, {**cifras, "ms": self._ms(inicio)})
            raise
        except Exception as error:   # noqa: BLE001 — un defecto nuestro tampoco rompe la pantalla
            raise self._inesperado("agente_ia.consulta_fallida", actor, conversacion, error, {**cifras, "ms": self._ms(inicio)}) from error
        ms = self._ms(inicio)
        modelo = str(doc.get("model") or "")
        self._anotar(self._registro.consulta_ok, actor, conversacion, {**cifras, "longitud_texto": len(respuesta), "ms": ms, "modelo": modelo, "ms_servicio": doc.get("processing_time_ms")})
        return {"conversacion": id_de_pantalla or "", "texto": respuesta, "modelo": modelo, "contexto_usado": bool(doc.get("context_used", True)), "ms": ms}

    # ------------------------------------------------------------------ hablar (pasos 3 y 4)

    def hablar(self, actor: Actor, texto: str | None, velocidad: float | None) -> Voz:
        cfg = self._configuracion()
        limpio = (texto or "").strip()
        cifras = {"longitud_texto": len(limpio)}
        trozos: list[str] = []
        try:
            self._habilitada(cfg)
            if not limpio:
                raise ErrorDeIa("text_required")
            if len(limpio) > cfg.voz_texto_max:
                raise ErrorDeIa("text_too_long", f"{len(limpio)} > {cfg.voz_texto_max}")
            trozos = trocear(limpio, cfg.trozo_max)
            if not trozos:
                raise ErrorDeIa("empty_text", "Ningún trozo del texto tiene letras ni números.")
        except ErrorDeIa as error:
            self._rechazar("hablar", "agente_ia.voz_fallida", actor, None, error, cifras)
            raise
        paso = _velocidad(velocidad)
        inicio = self._reloj()
        cifras = {**cifras, "trozos": len(trozos)}
        try:
            audio = self._sintetizar(cfg, trozos, paso)
        except ErrorDeIa as error:
            self._fallar("agente_ia.voz_fallida", actor, None, error, {**cifras, "ms": self._ms(inicio)})
            raise
        except Exception as error:   # noqa: BLE001
            raise self._inesperado("agente_ia.voz_fallida", actor, None, error, {**cifras, "ms": self._ms(inicio)}) from error
        self._anotar(self._registro.voz_ok, actor, {**cifras, "duracion_ms": audio.duracion_ms, "ms": self._ms(inicio)})
        return Voz(audio.wav, audio.duracion_ms, len(trozos))

    def _sintetizar(self, cfg, trozos: list[str], velocidad: float) -> wav.Resultado:
        cliente = self._cliente_de(cfg)
        # La voz del servicio sintetiza de a UNA por vez (y deja cuatro en cola, el resto recibe `tts_busy`): aquí se hace cola de a una por equipo para que dos pantallas no se estorben.
        if not self._candado_voz.acquire(timeout=cfg.voz_turno_s):
            raise ErrorDeIa("tts_busy", f"No hubo turno de voz en {cfg.voz_turno_s:g} s.")
        try:
            audios: list[bytes] = []
            inicio = self._reloj()
            for trozo in trozos:
                restante = cfg.tiempo_voz_total_s - (self._reloj() - inicio)
                if restante < 1:       # la app no espera más que esto: mejor decir «tardó demasiado» que dejarla colgada con el audio a medias
                    raise ErrorDeIa("ai_timeout", f"La voz de {len(trozos)} trozos pasó de {cfg.tiempo_voz_total_s:g} s.")
                try:
                    audios.append(self._sintetizar_trozo(cliente, trozo, velocidad, restante))
                except ErrorDeIa as error:
                    if error.codigo == "tts_empty_audio":
                        continue            # un trozo sin nada pronunciable no echa a perder el resto
                    raise
        finally:
            self._candado_voz.release()
        if not audios:
            raise ErrorDeIa("empty_text", "El servicio no pudo pronunciar ningún trozo.")
        try:
            return wav.unir(audios)
        except wav.WavInvalido as error:
            raise ErrorDeIa("ai_invalid_response", str(error)) from error

    def _sintetizar_trozo(self, cliente, trozo: str, velocidad: float, tiempo: float) -> bytes:
        for espera in (*REINTENTOS_VOZ_OCUPADA, None):
            try:
                return cliente.sintetizar(trozo, velocidad, tiempo)
            except ErrorDeIa as error:
                if error.codigo != "tts_busy" or espera is None:
                    raise
                self._dormir(espera)
        raise ErrorDeIa("tts_busy")      # inalcanzable: el último intento ya lanzó

    # ------------------------------------------------------------------ estado

    def estado(self, actor: Actor) -> dict:
        cfg = self._configuracion()
        if not cfg.habilitada:
            resultado = {"habilitada": False, "servicio_activo": False, "disponible": False, "voz_disponible": False, "codigo": "ai_disabled",
                         "motivo": ErrorDeIa("ai_disabled").mensaje, "modelo": None}
            self._anotar(self._registro.estado, actor, {"evento": "agente_ia.estado", "disponible": False, "codigo": "ai_disabled"}, False)
            return resultado
        try:
            dep = self._cliente_de(cfg).dependencias()
        except ErrorDeIa as error:
            resultado = {"habilitada": True, "servicio_activo": False, "disponible": False, "voz_disponible": False, "codigo": error.codigo, "motivo": error.mensaje,
                         "sugerencia": error.sugerencia, "modelo": None}
            self._anotar(self._registro.estado, actor, {"evento": "agente_ia.estado", "disponible": False, "codigo": error.codigo, "detalle_tecnico": error.detalle[:300]}, False)
            return resultado
        except Exception as error:   # noqa: BLE001
            resultado = {"habilitada": True, "servicio_activo": False, "disponible": False, "voz_disponible": False, "codigo": "ai_internal",
                         "motivo": ErrorDeIa("ai_internal").mensaje, "modelo": None}
            self._anotar(self._registro.estado, actor, {"evento": "agente_ia.estado", "disponible": False, "codigo": "ai_internal", "detalle_tecnico": f"{error.__class__.__name__}: {error}"[:300]}, False)
            return resultado
        resultado = diagnosticar(dep)
        self._anotar(self._registro.estado, actor, {"evento": "agente_ia.estado", "disponible": resultado["disponible"], "voz_disponible": resultado["voz_disponible"],
                                      "codigo": resultado["codigo"]}, resultado["disponible"])
        return resultado

    # ------------------------------------------------------------------ apoyo

    @staticmethod
    def _habilitada(cfg) -> None:
        if not cfg.habilitada:
            raise ErrorDeIa("ai_disabled", "AVACOM_IA_HABILITADA=0")

    def _ms(self, inicio: float) -> int:
        return int((self._reloj() - inicio) * 1000)

    def _rechazar(self, operacion: str, accion: str, actor: Actor, conversacion: str | None, error: ErrorDeIa, cifras: dict) -> None:
        """Una petición que ni siquiera salió hacia el servicio: error de quien pregunta (400/422) o IA desactivada. Los primeros sólo van al log; el apagado se asienta como fallo."""
        if error.codigo == "ai_disabled":
            self._fallar(accion, actor, conversacion, error, cifras)
        else:
            self._anotar(self._registro.validacion, operacion, actor, error)

    def _fallar(self, accion: str, actor: Actor, conversacion: str | None, error: ErrorDeIa, cifras: dict) -> None:
        self._anotar(self._registro.fallo, accion, actor, conversacion, error, cifras)

    @staticmethod
    def _anotar(escribir, *argumentos) -> None:
        try:
            escribir(*argumentos)
        except Exception:   # noqa: BLE001 — el registro nunca rompe la respuesta (la implementación ya se defiende; esto es la última red)
            pass

    def _inesperado(self, accion: str, actor: Actor, conversacion: str | None, causa: Exception, cifras: dict) -> ErrorDeIa:
        error = ErrorDeIa("ai_internal", f"{causa.__class__.__name__}: {causa}")
        self._fallar(accion, actor, conversacion, error, cifras)
        return error


def _velocidad(valor) -> float:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return 1.0
    if v != v:       # NaN
        return 1.0
    return min(VELOCIDAD_MAX, max(VELOCIDAD_MIN, v))


def diagnosticar(dep: dict) -> dict:
    """Lee `GET /health/dependencies` del servicio (`contrato-api-ai-lms.md` §4.4) sin fiarse de que traiga todo: lo que falta cuenta como «no disponible»."""
    def sub(nombre: str) -> dict:
        valor = dep.get(nombre)
        return valor if isinstance(valor, dict) else {}

    ollama, modelo, piper, tts, contexto = sub("ollama"), sub("llm_model"), sub("piper"), sub("tts_model"), sub("context")
    ollama_ok = ollama.get("reachable") is True
    modelo_ok = modelo.get("installed") is True
    contexto_ok = contexto.get("state") == "loaded"
    voz_ok = piper.get("available") is True and (tts.get("loaded") is True or tts.get("file_present") is True)
    if not ollama_ok:
        codigo, motivo = "llm_unavailable", ErrorDeIa("llm_unavailable").mensaje
    elif not modelo_ok:
        codigo, motivo = "llm_model_missing", ErrorDeIa("llm_model_missing").mensaje
    elif not contexto_ok:
        codigo, motivo = "context_unavailable", ErrorDeIa("context_unavailable").mensaje
    else:
        codigo, motivo = None, None
    return {"habilitada": True, "servicio_activo": True, "disponible": codigo is None, "voz_disponible": voz_ok, "codigo": codigo, "motivo": motivo,
            "modelo": str(modelo.get("name") or "") or None,
            "motivo_voz": None if voz_ok else ErrorDeIa("tts_unavailable").mensaje}


__all__ = ["Actor", "Agente", "Voz", "diagnosticar"]
