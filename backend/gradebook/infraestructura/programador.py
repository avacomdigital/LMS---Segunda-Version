"""
El programador del Gradebook: lo que el libro hace SOLO, sin que nadie pulse nada.

    cada 5 segundos      lee los eventos nuevos de MOD-010 (intentos abiertos, entregados, calificados, anulados) y pone al día el libro

Es un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`); no corre en las pruebas ni en los comandos de gestión. Toda la lógica vive en el caso de uso
(`aplicacion/consumidor.py`); aquí sólo hay un reloj y su tolerancia a fallos: un tick que falla se registra y el siguiente lo vuelve a intentar.
La corrección del libro NO depende de este hilo: cada consulta del profesor se pone al día antes de responder, y el consumidor es idempotente.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion.consumidor import ConsumirEventos
from .contenedor import servicios

log = logging.getLogger("avacom.gradebook.programador")

INTERVALO_S = 5.0


class Programador(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="gradebook-programador", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        while not self._detener.wait(self.intervalo_s):
            self.tick()
        connections.close_all()

    @staticmethod
    def tick() -> None:
        close_old_connections()
        try:
            resultado = ConsumirEventos(servicios()).hasta_vaciar()
            if resultado["procesados"] or resultado["fallidos"]:        # un barrido sin novedades no ensucia el registro
                log.info("Eventos de la evaluación aplicados al libro: %s", resultado)
        except Exception:   # noqa: BLE001 — el siguiente tick lo reintenta
            log.exception("El programador del libro falló al consumir los eventos de la evaluación")
        finally:
            close_old_connections()


_instancia: Programador | None = None
_candado = threading.Lock()


def iniciar() -> Programador | None:
    """Arranca el programador una sola vez por proceso. `AVACOM_GRADEBOOK_PROGRAMADOR=0` lo desactiva."""
    global _instancia
    if not getattr(settings, "AVACOM_GRADEBOOK_PROGRAMADOR", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Programador(float(getattr(settings, "AVACOM_GRADEBOOK_INTERVALO_S", INTERVALO_S)))
            _instancia.start()
        return _instancia
