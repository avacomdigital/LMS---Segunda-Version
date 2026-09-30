"""
Contexto de auditoría de la operación en curso (§2.5 y §4.3 del prompt de MOD-019).

Con UN identificador de correlación (`corr`) se reconstruye la operación entera: la petición HTTP (o el mensaje de
WebSocket, o el tick del programador), el asiento de bitácora que dejó, el evento de cola y el error si lo hubo.
El middleware lo fija al entrar una petición; el consumidor de WebSocket al abrir el socket; el programador y las
migraciones lo declaran a mano. Todo lo que se escribe mientras dura la operación (logs y asientos) lo hereda sin
que el módulo que escribe tenga que acordarse de pasarlo: por eso vive en `contextvars` y no en parámetros.

No importa Django: lo usan `logging_setup.py` (antes de que existan las apps) y el dominio de la bitácora.
"""
from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, replace

ORIGEN_API = "api"
ORIGEN_WS = "ws"
ORIGEN_SISTEMA = "sistema"
ORIGEN_INSTALADOR = "instalador"
ORIGEN_MIGRACION = "migracion"
ORIGEN_PRUEBA = "prueba"
ORIGENES = (ORIGEN_API, ORIGEN_WS, ORIGEN_SISTEMA, ORIGEN_INSTALADOR, ORIGEN_MIGRACION, ORIGEN_PRUEBA)


@dataclass(frozen=True)
class Contexto:
    corr: str | None = None            # identificador de correlación de la operación (UUID)
    usuario_id: str | None = None      # quien firma la sesión (Principal de MOD-001), si la hay
    rol_codigo: str | None = None      # el rol efectivo de esa sesión (BR-021)
    dispositivo_id: str | None = None  # el aparato validado contra m09_dispositivo; nunca inventado
    origen: str = ORIGEN_SISTEMA       # api · ws · sistema · instalador · migracion · prueba
    caso: str | None = None            # id del test en curso (sólo en pruebas)
    sesion_id: str | None = None       # sesión de usuario (m01_sesion) si la hay

    def roles_activos(self) -> list[str]:
        return [self.rol_codigo] if self.rol_codigo else []


_actual: contextvars.ContextVar[Contexto] = contextvars.ContextVar("avacom_contexto_auditoria", default=Contexto())


def actual() -> Contexto:
    return _actual.get()


def nuevo_corr() -> str:
    return str(uuid.uuid4())


def establecer(**campos) -> contextvars.Token:
    """Sustituye campos del contexto vigente. Devuelve el token para `restaurar`."""
    return _actual.set(replace(_actual.get(), **campos))


def restaurar(token: contextvars.Token) -> None:
    _actual.reset(token)


def limpiar() -> contextvars.Token:
    return _actual.set(Contexto())


class con:
    """`with contexto.con(origen="sistema", corr=...):` — fija campos durante un bloque y los devuelve al salir."""

    def __init__(self, **campos):
        self.campos = campos
        self._token = None

    def __enter__(self) -> Contexto:
        self._token = establecer(**self.campos)
        return _actual.get()

    def __exit__(self, *_):
        if self._token is not None:
            restaurar(self._token)
            self._token = None
        return False
