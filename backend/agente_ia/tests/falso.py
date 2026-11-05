"""
Un AVACOM Local AI de mentira, por HTTP de verdad (un servidor en un hilo, puerto libre), para probar el cliente y los casos de uso SIN Qwen ni Ollama ni Piper: habla el mismo
contrato que `contrato-api-ai-lms.md` (los dos formatos de error incluidos) y deja ver cada petición que recibió (ruta, cuerpo decodificado como UTF-8 y cabeceras).

Cada ruta se programa con una lista de «guiones»: cada petición consume el siguiente (el último se repite). Un guion es `(estado, cuerpo, espera_s)`; `cuerpo` puede ser `dict` (JSON),
`bytes` (tal cual) o un callable que recibe la petición.
"""
from __future__ import annotations

import json
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FRECUENCIA = 22050


def wav_de(segundos: float = 0.2, valor: int = 1000, frecuencia: int = FRECUENCIA) -> bytes:
    """Un WAV PCM 16 bits mono canónico (el mismo formato que devuelve Piper)."""
    n = int(frecuencia * segundos)
    datos = struct.pack(f"<{n}h", *([valor] * n))
    return (b"RIFF" + struct.pack("<I", 36 + len(datos)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, frecuencia, frecuencia * 2, 2, 16) + b"data"
            + struct.pack("<I", len(datos)) + datos)


def respuesta_llm(texto: str = "¡Hola! Soy el asistente virtual de AVACOM. Estoy aquí para ayudarte con tus clases.", **extra) -> dict:
    return {"success": True, "model": "qwen3:8b", "conversation_id": "x", "language": "es", "response": texto, "processing_time_ms": 8, "context_used": True,
            "usage": {"prompt_tokens": 300, "completion_tokens": 30, "tokens_per_second": 10.0}, **extra}


def error_servicio(codigo: str, mensaje: str = "fallo") -> dict:
    return {"success": False, "error": {"code": codigo, "message": mensaje}}


DEPENDENCIAS_SANAS = {
    "status": "ok", "ollama": {"reachable": True, "version": "0.0-test", "error": None}, "llm_model": {"name": "qwen3:8b", "installed": True},
    "piper": {"package": "1.8.0", "available": True}, "tts_model": {"voice": "es_MX-claude-high", "file_present": True, "loaded": True, "sample_rate": 22050, "error": None},
    "context": {"state": "loaded", "path": "C:\\x\\avacom-context.txt", "size_chars": 2592, "sha256": "x", "error": None},
}


class Peticion:
    def __init__(self, metodo: str, ruta: str, cabeceras: dict, cuerpo: bytes):
        self.metodo, self.ruta, self.cabeceras, self.crudo = metodo, ruta, cabeceras, cuerpo

    @property
    def json(self):
        return json.loads(self.crudo.decode("utf-8")) if self.crudo else None


class _Servidor(ThreadingHTTPServer):
    def handle_error(self, request, client_address):      # un cliente que se cansó de esperar (prueba de tiempos) no debe ensuciar la salida
        pass


class ServicioIaFalso:
    def __init__(self):
        self.guiones: dict[str, list] = {}
        self.recibidas: list[Peticion] = []
        self._cerrojo = threading.Lock()
        self.reiniciar()
        servicio = self

        class Manejador(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def _atender(self):
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = self.rfile.read(largo) if largo else b""
                peticion = Peticion(self.command, self.path, {k: v for k, v in self.headers.items()}, cuerpo)
                estado, contenido, espera = servicio._siguiente(peticion)
                servicio._entrar(peticion)
                try:
                    if espera:
                        time.sleep(espera)
                finally:
                    servicio._salir(peticion)
                if callable(contenido):
                    contenido = contenido(peticion)
                if isinstance(contenido, (dict, list)):
                    datos, tipo = json.dumps(contenido, ensure_ascii=False).encode("utf-8"), "application/json"
                elif isinstance(contenido, bytes):
                    datos, tipo = contenido, "audio/wav" if contenido[:4] == b"RIFF" else "text/html"
                else:
                    datos, tipo = str(contenido).encode("utf-8"), "text/plain"
                self.send_response(estado)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            do_GET = do_POST = _atender

        self._servidor = _Servidor(("127.0.0.1", 0), Manejador)
        self._servidor.daemon_threads = True
        self.puerto = self._servidor.server_address[1]
        self.url = f"http://127.0.0.1:{self.puerto}"
        self._hilo = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._hilo.start()

    # ---------------------------------------------------------------- guiones

    def reiniciar(self) -> None:
        with self._cerrojo:
            self.recibidas = []
            self.guiones = {"/llm/query": [(200, respuesta_llm(), 0)], "/audio/gen-voice": [(200, lambda _p: wav_de(), 0)], "/health/dependencies": [(200, DEPENDENCIAS_SANAS, 0)],
                            "/health": [(200, {"status": "ok"}, 0)]}
            self._turnos: dict[str, int] = {}
            self._activas: dict[str, int] = {}
            self.maximo_simultaneas: dict[str, int] = {}          # cuántas peticiones a la vez llegaron a cada ruta (la voz del servicio real sólo atiende de a una)

    def programar(self, ruta: str, *guiones) -> None:
        with self._cerrojo:
            self.guiones[ruta] = [g if len(g) == 3 else (*g, 0) for g in guiones]
            self._turnos[ruta] = 0

    def _siguiente(self, peticion: Peticion):
        ruta = peticion.ruta.split("?")[0]
        with self._cerrojo:
            self.recibidas.append(peticion)
            lista = self.guiones.get(ruta)
            if not lista:
                return 404, error_servicio("not_found", ruta), 0
            i = self._turnos.get(ruta, 0)
            self._turnos[ruta] = i + 1
            return lista[min(i, len(lista) - 1)]

    def _entrar(self, peticion: Peticion) -> None:
        ruta = peticion.ruta.split("?")[0]
        with self._cerrojo:
            self._activas[ruta] = self._activas.get(ruta, 0) + 1
            self.maximo_simultaneas[ruta] = max(self.maximo_simultaneas.get(ruta, 0), self._activas[ruta])

    def _salir(self, peticion: Peticion) -> None:
        with self._cerrojo:
            self._activas[peticion.ruta.split("?")[0]] -= 1

    def de(self, ruta: str) -> list[Peticion]:
        return [p for p in self.recibidas if p.ruta.split("?")[0] == ruta]

    def cerrar(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()
