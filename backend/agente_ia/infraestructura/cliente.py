"""
ÚNICO cliente del LMS hacia AVACOM Local AI (el servicio de IA local: Qwen por Ollama + la voz Piper). Es el único `urlopen` del backend que apunta a ese servicio.

Reglas (de `contrato-api-ai-lms.md`):
  · UTF-8 en todo el cuerpo, `Content-Type: application/json; charset=utf-8`.
  · Sin proxy: la dirección es el bucle local del propio equipo; un proxy del sistema (colegios, antivirus) jamás debe intermediarla.
  · Cada llamada con su tope de tiempo: el modelo puede tardar minutos en CPU (≈150 s en el peor caso medido por el servicio); la voz, un minuto por trozo.
  · Nada de lo que contesta el servicio se da por bueno sin mirarlo: el JSON debe traer el texto, y un «audio» debe ser un WAV. Si no, `ai_invalid_response`, no una pantalla en blanco.
  · Todo fallo sale como `ErrorDeIa` con un código del catálogo (`dominio/errores.py`): «no conecta», «tardó demasiado», o el código del propio servicio (`llm_unavailable`, `busy`, `tts_busy`…).
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from ..dominio import wav
from ..dominio.errores import ErrorDeIa, desde_servicio

_abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))

TOPE_RESPUESTA_JSON = 2 * 1024 * 1024        # una respuesta del modelo son unos cientos de caracteres
TOPE_AUDIO = 16 * 1024 * 1024                # un trozo de 450 caracteres pesa ≈ 2 MB
TIEMPO_CONEXION_S = 4.0                      # abrir el socket al servicio: en el mismo equipo o contesta ya o no está (Windows tarda ≈2 s en decir «rechazado»)


class ClienteIa:
    def __init__(self, url: str, tiempo_llm_s: float, tiempo_voz_s: float, tiempo_salud_s: float):
        self.url = url.rstrip("/")
        self.tiempo_llm_s = tiempo_llm_s
        self.tiempo_voz_s = tiempo_voz_s
        self.tiempo_salud_s = tiempo_salud_s

    # ------------------------------------------------------------------ llamadas

    def consultar(self, pregunta: str, conversacion: str | None, max_tokens: int) -> dict:
        """`POST /llm/query` (pasos 1 y 2). Devuelve el JSON del servicio ya validado (`response` es un texto no vacío)."""
        cuerpo = {"query": pregunta, "use_avacom_context": True, "max_tokens": max_tokens}
        if conversacion:
            cuerpo["conversation_id"] = conversacion
        datos, _ = self._enviar("POST", "/llm/query", cuerpo, self.tiempo_llm_s, TOPE_RESPUESTA_JSON)
        try:
            doc = json.loads(datos.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ErrorDeIa("ai_invalid_response", f"El servicio no contestó un JSON ({error.__class__.__name__}).") from error
        texto = doc.get("response") if isinstance(doc, dict) else None
        if not isinstance(texto, str) or not texto.strip():
            raise ErrorDeIa("ai_invalid_response", "El servicio contestó sin el texto de la respuesta.")
        return doc

    def sintetizar(self, texto: str, velocidad: float, tiempo: float | None = None) -> bytes:
        """`POST /audio/gen-voice` (pasos 3 y 4) para UN trozo. Devuelve un WAV validado. `tiempo` acota la espera por debajo del tope normal de un trozo."""
        cuerpo = {"text": texto, "speed": velocidad, "format": "wav"}
        datos, cabeceras = self._enviar("POST", "/audio/gen-voice", cuerpo, min(self.tiempo_voz_s, tiempo) if tiempo else self.tiempo_voz_s, TOPE_AUDIO)
        try:
            wav.analizar(datos)
        except wav.WavInvalido as error:
            tipo = cabeceras.get("Content-Type", "?")
            raise ErrorDeIa("ai_invalid_response", f"El servicio no contestó audio válido ({error}; tipo {tipo}, {len(datos)} bytes).") from error
        return datos

    def dependencias(self) -> dict:
        """`GET /health/dependencies`: el estado de Ollama, del modelo, de Piper y del contexto."""
        datos, _ = self._enviar("GET", "/health/dependencies", None, self.tiempo_salud_s, TOPE_RESPUESTA_JSON)
        try:
            doc = json.loads(datos.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ErrorDeIa("ai_invalid_response", f"El estado del servicio no es un JSON ({error.__class__.__name__}).") from error
        if not isinstance(doc, dict):
            raise ErrorDeIa("ai_invalid_response", "El estado del servicio no tiene la forma esperada.")
        return doc

    # ------------------------------------------------------------------ transporte

    def _comprobar_conexion(self, tiempo: float) -> None:
        """Antes de esperar minutos por el modelo, comprobar que hay alguien escuchando: un servicio apagado o colgado se dice como «no disponible» en pocos segundos, no tras 160 s."""
        partes = urllib.parse.urlsplit(self.url)
        host = partes.hostname or "127.0.0.1"
        puerto = partes.port or (443 if partes.scheme == "https" else 80)
        try:
            socket.create_connection((host, puerto), timeout=min(TIEMPO_CONEXION_S, tiempo)).close()
        except OSError as error:        # rechazado, tiempo agotado, red inalcanzable…
            raise ErrorDeIa("ai_unreachable", f"No se pudo abrir {host}:{puerto} ({error.__class__.__name__}: {error})") from error

    def _enviar(self, metodo: str, ruta: str, cuerpo: dict | None, tiempo: float, tope: int) -> tuple[bytes, dict]:
        self._comprobar_conexion(tiempo)
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8") if cuerpo is not None else None
        peticion = urllib.request.Request(self.url + ruta, data=datos, method=metodo)
        if datos is not None:
            peticion.add_header("Content-Type", "application/json; charset=utf-8")
        peticion.add_header("Accept", "application/json, audio/wav")
        try:
            with _abridor.open(peticion, timeout=tiempo) as respuesta:
                contenido = respuesta.read(tope + 1)
                if len(contenido) > tope:
                    raise ErrorDeIa("ai_invalid_response", f"La respuesta de {ruta} supera el tope de {tope} bytes.")
                return contenido, dict(respuesta.headers.items())
        except urllib.error.HTTPError as error:
            raise self._error_http(error, ruta) from error
        except ErrorDeIa:
            raise
        except (socket.timeout, TimeoutError) as error:
            raise ErrorDeIa("ai_timeout", f"{metodo} {ruta} no contestó en {tiempo:g} s.") from error
        except urllib.error.URLError as error:
            motivo = error.reason
            if isinstance(motivo, (socket.timeout, TimeoutError)):
                raise ErrorDeIa("ai_timeout", f"{metodo} {ruta}: no se pudo conectar a tiempo ({tiempo:g} s).") from error
            raise ErrorDeIa("ai_unreachable", f"{metodo} {ruta}: {motivo.__class__.__name__}: {motivo}") from error
        except (ConnectionError, OSError) as error:         # reinicio de la conexión a medias, respuesta cortada (IncompleteRead es HTTPException, abajo)
            raise ErrorDeIa("ai_unreachable", f"{metodo} {ruta}: {error.__class__.__name__}: {error}") from error
        except Exception as error:   # noqa: BLE001 — http.client.HTTPException (RemoteDisconnected, IncompleteRead, BadStatusLine…) y cualquier otra cosa del transporte
            raise ErrorDeIa("ai_unreachable", f"{metodo} {ruta}: {error.__class__.__name__}: {error}") from error

    @staticmethod
    def _error_http(error: urllib.error.HTTPError, ruta: str) -> ErrorDeIa:
        """Los dos formatos de error del servicio: `{success:false,error:{code,message}}` y el `{detail:[…]}` de FastAPI para los 422."""
        codigo, mensaje = "", f"{error.code} {error.reason}"
        try:
            doc = json.loads(error.read(TOPE_RESPUESTA_JSON).decode("utf-8", errors="replace"))
            if isinstance(doc, dict):
                if isinstance(doc.get("error"), dict):
                    codigo = str(doc["error"].get("code") or "")
                    mensaje = str(doc["error"].get("message") or mensaje)
                elif "detail" in doc:
                    codigo = "validation_error"
                    mensaje = str(doc["detail"])[:500]
        except Exception:   # noqa: BLE001 — un cuerpo que no es JSON (una página de un proxy, un cuerpo cortado) no cambia el estado HTTP: se conserva
            pass
        return desde_servicio(error.code, codigo, f"{ruta}: {mensaje}")
