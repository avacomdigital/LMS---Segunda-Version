"""
El contexto de la operación en curso, de MOD-019 (`audit/contexto.py`, contextvars): de ahí salen el actor, el aparato y la correlación del sobre cuando el productor no los pasa
(P-03: un solo sitio). Fuera de una petición (un programador, una migración, una prueba sin sesión) el actor es `sistema`.
"""
from __future__ import annotations

from ..dominio import catalogos as cat


class ContextoDeAuditoria:
    def actual(self) -> tuple[str | None, str | None, str | None]:
        try:
            from audit import contexto
            c = contexto.actual()
        except Exception:   # noqa: BLE001 — sin contexto no hay nada que heredar
            return None, None, None
        actor = c.usuario_id or (f"aparato:{c.dispositivo_id}" if c.dispositivo_id and c.origen in (contexto.ORIGEN_API, contexto.ORIGEN_WS) else None) or cat.SISTEMA
        return actor, c.dispositivo_id or None, c.corr or None


class ContextoFijo:
    """Para las pruebas: lo que se le diga."""

    def __init__(self, actor: str | None = None, dispositivo_id: str | None = None, correlacion_id: str | None = None):
        self.valores = (actor, dispositivo_id, correlacion_id)

    def actual(self) -> tuple[str | None, str | None, str | None]:
        return self.valores
