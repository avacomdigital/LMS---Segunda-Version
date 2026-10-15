"""
El programador de Reporting: lo que los reportes hacen SOLOS, sin que nadie pulse nada (FUN-144).

    cada minuto      si NO hay una clase abierta: lee la cola de los módulos, recalcula los agregados desactualizados, deja que caduquen las señales de integración y las
                     exportaciones sin confirmar. Con una clase en curso espera: no compite con las tabletas por el turno de escritura del nodo.

Es un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`); no corre en las pruebas ni en los comandos de gestión. Toda la lógica vive en el caso de uso
(`aplicacion/consumidor.ActualizarAgregados`); aquí sólo hay un reloj y su tolerancia a fallos: un tick que falla se registra y el siguiente lo vuelve a intentar.
La corrección de los reportes NO depende de este hilo: cada consulta se pone al día antes de responder, y el consumidor es idempotente.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion.consumidor import ActualizarAgregados
from .contenedor import servicios

log = logging.getLogger("avacom.reporting.programador")

INTERVALO_S = 60.0


class Programador(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="reporting-programador", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        while not self._detener.wait(self.intervalo_s):
            self.tick()
        connections.close_all()

    @staticmethod
    def tick() -> dict | None:
        close_old_connections()
        try:
            resultado = ActualizarAgregados(servicios()).ejecutar()
            if resultado.get("eventos") or resultado.get("grupos") or resultado.get("clases_limpiadas") or resultado.get("exportaciones_caducadas"):
                log.info("Agregados de reportes actualizados: %s", resultado)
            return resultado
        except Exception:   # noqa: BLE001 — el siguiente tick lo reintenta
            log.exception("El programador de reportes falló al actualizar los agregados")
            return None
        finally:
            close_old_connections()


_instancia: Programador | None = None
_candado = threading.Lock()


def iniciar() -> Programador | None:
    """Arranca el programador una sola vez por proceso. `AVACOM_REPORTES_PROGRAMADOR=0` lo desactiva."""
    global _instancia
    if not getattr(settings, "AVACOM_REPORTES_PROGRAMADOR", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Programador(float(getattr(settings, "AVACOM_REPORTES_INTERVALO_S", INTERVALO_S)))
            _instancia.start()
        return _instancia
