"""
El programador de licenciamiento: lo que la licencia hace SOLA, sin que nadie pulse nada (P-11).

    al arrancar     valida la licencia (FUN-189) ANTES de que llegue la primera petición, para que el camino caliente ya tenga estado
    cada 5 minutos  recalcula el estado (FUN-192 gracia y FUN-193 degradación SALEN del tiempo), cuenta equipos y usuarios (FUN-190), asienta los bloqueos de licencia, publica los
                    eventos y los avisos escalonados (30/14/7/3/1 días), y avanza la marca alta del reloj y sus anclas

Es un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py` dentro de un `try/except`, como la cola de medios: si no arranca, el nodo sigue); no corre en las pruebas ni en los comandos
de gestión. Toda la lógica vive en el caso de uso (`aplicacion/evaluar.Evaluar`); aquí sólo hay un reloj y su tolerancia a fallos: un ciclo que falla se registra y el siguiente lo
reintenta. Calcular NUNCA interrumpe una clase: casi todos los ciclos son sólo lecturas, y las escrituras son transacciones pequeñas (R-07).
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion.evaluar import Evaluar
from . import contenedor

log = logging.getLogger("avacom.licenciamiento")

INTERVALO_S = 300.0


class Programador(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="licenciamiento-programador", daemon=True)
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
            return Evaluar(contenedor.servicios()).ejecutar(origen)
        except Exception:   # noqa: BLE001 — el siguiente ciclo lo reintenta
            log.exception("El programador de la licencia falló", extra={"evento": "licencia.programador_fallo", "ruta": "bad"})
            return None
        finally:
            close_old_connections()


_instancia: Programador | None = None
_candado = threading.Lock()


def iniciar() -> Programador | None:
    """Valida al arrancar y arranca el hilo, una sola vez por proceso. En modo `ilimitada` (desarrollo y pruebas) no hay nada que vigilar. `AVACOM_LICENCIA_PROGRAMADOR=0` lo apaga."""
    global _instancia
    if contenedor.modo() == contenedor.ILIMITADA or not getattr(settings, "AVACOM_LICENCIA_PROGRAMADOR", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            Programador.tick("arranque")                       # FUN-189: la licencia se valida ANTES de atender la primera petición
            _instancia = Programador(float(getattr(settings, "AVACOM_LICENCIA_INTERVALO_S", INTERVALO_S)))
            _instancia.start()
        return _instancia
