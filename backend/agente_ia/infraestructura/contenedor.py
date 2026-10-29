"""El agente de IA armado con sus piezas reales. Las pruebas lo sustituyen con `reemplazar(...)`."""
from __future__ import annotations

import threading

from ..aplicacion.agente import Agente
from . import configuracion
from .cliente import ClienteIa
from .registro import RegistroDeAuditoriaYLog

_candado_voz = threading.Lock()         # una síntesis por equipo (el servicio local sólo sintetiza de a una)
_sustituto: Agente | None = None


def _cliente_de(cfg: configuracion.Configuracion) -> ClienteIa:
    return ClienteIa(cfg.url, cfg.tiempo_llm_s, cfg.tiempo_voz_s, cfg.tiempo_salud_s)


def agente() -> Agente:
    if _sustituto is not None:
        return _sustituto
    return Agente(configuracion.actual, _cliente_de, RegistroDeAuditoriaYLog(), _candado_voz)


def reemplazar(otro: Agente | None) -> None:
    """Sólo para pruebas."""
    global _sustituto
    _sustituto = otro
