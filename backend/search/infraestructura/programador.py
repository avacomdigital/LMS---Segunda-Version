"""
El programador de Search: lo que el índice hace SOLO, sin que nadie pulse nada.

    cada 5 segundos      lee los eventos nuevos de MOD-010, MOD-008 y MOD-007 y pone al día el índice; la primera vez, lo construye.

Es un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`); no corre en las pruebas ni en los comandos de gestión. Toda la lógica vive en el caso de uso
(`aplicacion/indexar.py`); aquí sólo hay un reloj y su tolerancia a fallos: un ciclo que falla se registra y el siguiente lo vuelve a intentar.
La corrección de la búsqueda NO depende de este hilo: cada consulta pone el índice al día antes de responder, y cada resultado se verifica en vivo con su dueño.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion.indexar import Sincronizar
from .contenedor import servicios

log = logging.getLogger("avacom.search.programador")

INTERVALO_S = 5.0


class Programador(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="search-programador", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        self.tick()                                  # al arrancar: construir el índice si hace falta, sin esperar al primer intervalo
        while not self._detener.wait(self.intervalo_s):
            self.tick()
        connections.close_all()

    @staticmethod
    def tick() -> None:
        close_old_connections()
        try:
            resultado = Sincronizar(servicios()).hasta_vaciar()
            if resultado["indexados"] or resultado["purgados"] or resultado["fallidos"]:        # un ciclo sin novedades no ensucia el registro
                log.info("Índice de búsqueda al día: %s", resultado)
        except Exception:   # noqa: BLE001 — el siguiente ciclo lo reintenta
            log.exception("El programador de la búsqueda falló al poner el índice al día")
        finally:
            close_old_connections()


_instancia: Programador | None = None
_candado = threading.Lock()


def iniciar() -> Programador | None:
    """Arranca el programador una sola vez por proceso. `AVACOM_SEARCH_PROGRAMADOR=0` lo desactiva."""
    global _instancia
    if not getattr(settings, "AVACOM_SEARCH_PROGRAMADOR", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Programador(float(getattr(settings, "AVACOM_SEARCH_INTERVALO_S", INTERVALO_S)))
            _instancia.start()
        return _instancia
