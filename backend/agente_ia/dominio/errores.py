"""
Errores del agente de IA y su traducción al aula.

Hay una sola familia: `ErrorDeIa`. Cada una lleva el código estable que ve la app (`codigo`), el estado HTTP con el que el backend lo responde, si tiene sentido ofrecer «Reintentar»
(`reintentable`), el texto para quien usa la pantalla (`mensaje`, en español y sin jerga) y el detalle técnico para el log y la bitácora (`detalle`, nunca se le muestra a quien pregunta).

Un fallo de la IA es un estado NORMAL del aula, no un defecto: el servicio local puede estar apagado, el modelo sin instalar o la máquina saturada. Por eso ninguno de estos errores
termina en un 500 sin explicación ni cierra la aplicación: se contesta con el código de aquí y se deja constancia en la bitácora y en el log.

Los códigos del servicio local (`contrato-api-ai-lms.md`, §7) se traducen aquí; los propios del aula son `ai_*`, `*_required`, `*_too_long` y `empty_text`.
"""
from __future__ import annotations

from dataclasses import dataclass

SUGERENCIA_SERVICIO = "Avisa a quien administra el equipo: el servicio «AVACOM Local AI» debe estar en marcha en este equipo."
SUGERENCIA_CONFIGURAR = "El asistente todavía no está configurado en este equipo. Avisa a quien administra el equipo."


@dataclass(frozen=True)
class Regla:
    http: int
    reintentable: bool
    mensaje: str
    sugerencia: str | None = None


# Lo que el aula responde por cada código. Los 4xx del servicio local (422, 404) son errores de programación o de configuración, no de quien pregunta: se contestan como 502
# (el backend no pudo completar la tarea con su proveedor) y se registran como ERROR para que alguien los arregle.
REGLAS: dict[str, Regla] = {
    "ai_disabled": Regla(503, False, "El asistente de IA está desactivado en este equipo."),
    "ai_unreachable": Regla(503, True, "El asistente no está disponible en este momento.", SUGERENCIA_SERVICIO),
    "ai_timeout": Regla(504, True, "El asistente tardó demasiado en responder. Prueba con una pregunta más corta."),
    "ai_invalid_response": Regla(502, True, "El asistente dio una respuesta que no se pudo entender. Intenta de nuevo."),
    "llm_unavailable": Regla(503, True, "El motor del asistente no está en marcha.", SUGERENCIA_SERVICIO),
    "llm_model_missing": Regla(503, False, "El asistente aún no está configurado en este equipo.", SUGERENCIA_CONFIGURAR),
    "context_unavailable": Regla(503, False, "El asistente aún no está configurado en este equipo.", SUGERENCIA_CONFIGURAR),
    "llm_timeout": Regla(504, True, "El asistente tardó demasiado en responder. Prueba con una pregunta más corta."),
    "busy": Regla(429, True, "El asistente está atendiendo otra consulta. Intenta de nuevo en un momento."),
    "llm_error": Regla(502, True, "El asistente no pudo responder. Intenta de nuevo."),
    "tts_unavailable": Regla(503, True, "La voz del asistente no está disponible. Puedes leer la respuesta."),
    "tts_timeout": Regla(504, True, "La voz del asistente tardó demasiado. Puedes leer la respuesta."),
    "tts_busy": Regla(429, True, "La voz del asistente está ocupada. Intenta de nuevo en un momento."),
    "voice_not_found": Regla(502, False, "La voz del asistente no está instalada en este equipo.", SUGERENCIA_CONFIGURAR),
    "internal_error": Regla(502, True, "El asistente tuvo un problema interno. Intenta de nuevo."),
    "ai_internal": Regla(502, True, "El asistente tuvo un problema inesperado. Intenta de nuevo."),
    # validación propia
    "question_required": Regla(400, False, "Escribe una pregunta."),
    "question_too_long": Regla(400, False, "La pregunta es demasiado larga."),
    "text_required": Regla(400, False, "No hay texto para leer en voz alta."),
    "text_too_long": Regla(400, False, "El texto es demasiado largo para leerlo en voz alta."),
    "empty_text": Regla(422, False, "Ese texto no tiene nada que se pueda leer en voz alta."),
    "tts_empty_audio": Regla(422, False, "Ese texto no tiene nada que se pueda leer en voz alta."),
}

# Fallos que son defectos del propio LMS o del servicio (no un estado normal del aula): se registran como ERROR en el log.
DEFECTOS = frozenset({"ai_invalid_response", "internal_error", "ai_internal", "voice_not_found", "text_too_long", "validation_error", "llm_error"})


class ErrorDeIa(Exception):
    def __init__(self, codigo: str, detalle: str = "", *, origen_http: int | None = None, mensaje: str | None = None):
        regla = REGLAS.get(codigo) or Regla(502, False, "El asistente no pudo completar la tarea. Intenta de nuevo.")
        super().__init__(f"{codigo}: {detalle}" if detalle else codigo)
        self.codigo = codigo
        self.detalle = detalle
        self.http = regla.http
        self.reintentable = regla.reintentable
        self.mensaje = mensaje or regla.mensaje
        self.sugerencia = regla.sugerencia
        self.origen_http = origen_http          # el estado que contestó el servicio local, si contestó

    @property
    def es_defecto(self) -> bool:
        return self.codigo in DEFECTOS or self.codigo not in REGLAS

    def cuerpo(self) -> dict:
        """El cuerpo de la respuesta: el mismo formato de degradación del resto del nodo (`detail`, `codigo`, `sugerencia`) más `reintentable`."""
        cuerpo = {"detail": self.mensaje, "codigo": self.codigo, "reintentable": self.reintentable}
        if self.sugerencia:
            cuerpo["sugerencia"] = self.sugerencia
        return cuerpo


def desde_servicio(estado: int, codigo: str, mensaje: str) -> ErrorDeIa:
    """El error que contestó el servicio local (`{success:false,error:{code,message}}` o `{detail:[…]}`), traducido. Un código que no se conoce no se pierde: va en el detalle."""
    codigo = (codigo or "").strip() or f"http_{estado}"
    if codigo not in REGLAS:
        # 5xx desconocido: transitorio y del servicio; 4xx desconocido: configuración o programación.
        return ErrorDeIa("ai_internal" if estado >= 500 else "llm_error", f"{codigo}: {mensaje}", origen_http=estado)
    return ErrorDeIa(codigo, mensaje, origen_http=estado)
