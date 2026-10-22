"""
El vigilante de actualizaciones: un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py` dentro de un `try/except`, con el patrón de la cola de medios: si no arranca, el nodo
sigue). Al arrancar lee `resultado.json` (FUN-187) ANTES de atender la primera petición, para que el 503 del inicio de clases se levante en cuanto el nodo vuelve; después, cada
`AVACOM_ACTUALIZACION_INTERVALO_S` segundos, abre ventanas, archiva lo vencido y anuncia paquetes nuevos (`aplicacion/vigilante.Tick`).

No corre en las pruebas ni en los comandos de gestión. Un ciclo que falla se registra y el siguiente lo reintenta.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion.vigilante import Tick
from . import contenedor

log = logging.getLogger("avacom.actualizacion")

INTERVALO_S = 30.0


class Vigilante(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="actualizacion-vigilante", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        while not self._detener.wait(self.intervalo_s):
            self.tick()
        connections.close_all()

    @staticmethod
    def tick(origen: str = "tick"):
        close_old_connections()
        try:
            return Tick(contenedor.servicios()).ejecutar(origen)
        except Exception:   # noqa: BLE001 — el siguiente ciclo lo reintenta
            log.exception("El vigilante de actualizaciones falló", extra={"evento": "actualizacion.vigilante_fallo", "ruta": "bad"})
            return None
        finally:
            close_old_connections()


_instancia: Vigilante | None = None
_candado = threading.Lock()


def iniciar() -> Vigilante | None:
    """Procesa el resultado pendiente y arranca el hilo, una sola vez por proceso. `AVACOM_ACTUALIZACION_VIGILANTE=0` lo apaga."""
    global _instancia
    if not getattr(settings, "AVACOM_ACTUALIZACION_VIGILANTE", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            Vigilante.tick("arranque")
            _instancia = Vigilante(float(getattr(settings, "AVACOM_ACTUALIZACION_INTERVALO_S", INTERVALO_S)))
            _instancia.start()
        return _instancia
