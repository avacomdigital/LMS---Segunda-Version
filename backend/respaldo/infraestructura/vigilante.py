"""
El vigilante de respaldos: un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py` dentro de un `try/except`, con el patrón de la cola de medios: si no arranca, el nodo sigue). Su
PRIMER ciclo (`arranque`) ocurre en el propio hilo, no en el arranque del servidor: reanudar un respaldo interrumpido puede tardar minutos y el aula no espera por eso. Después, cada
`AVACOM_RESPALDO_INTERVALO_S` segundos, mira el calendario, verifica y reintenta (`aplicacion/vigilante.Tick`).

No corre en las pruebas ni en los comandos de gestión. Un ciclo que falla se registra y el siguiente lo reintenta.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion.vigilante import Tick
from . import contenedor

log = logging.getLogger("avacom.respaldo")

INTERVALO_S = 60.0


class Vigilante(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="respaldo-vigilante", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        self.tick("arranque")
        while not self._detener.wait(self.intervalo_s):
            self.tick()
        connections.close_all()

    @staticmethod
    def tick(origen: str = "tick"):
        close_old_connections()
        try:
            return Tick(contenedor.servicios()).ejecutar(origen)
        except Exception:   # noqa: BLE001 — el siguiente ciclo lo reintenta
            log.exception("El vigilante de respaldos falló", extra={"evento": "respaldo.vigilante_fallo", "ruta": "bad"})
            return None
        finally:
            close_old_connections()


_instancia: Vigilante | None = None
_candado = threading.Lock()


def iniciar() -> Vigilante | None:
    """Arranca el hilo, una sola vez por proceso. `AVACOM_RESPALDO_VIGILANTE=0` lo apaga."""
    global _instancia
    if not getattr(settings, "AVACOM_RESPALDO_VIGILANTE", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Vigilante(float(getattr(settings, "AVACOM_RESPALDO_INTERVALO_S", INTERVALO_S)))
            _instancia.start()
        return _instancia
