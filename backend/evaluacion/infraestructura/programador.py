"""
El programador del nodo: lo que la evaluación hace SOLA, sin que nadie pulse nada (D-15, INV-010, BR-051).

    al arrancar          los intentos que estaban abiertos quedan `restaurando`, con el reloj congelado en su último latido (nunca se entregan ni se anulan)
    cada 5 segundos      activa lo programado, vence plazos, pausa a quien dejó de dar señal, entrega a quien agotó el tiempo, reintenta calificaciones
    cada minuto          cerrada hace más de 24 horas → archivada

Es un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`); no corre en las pruebas ni en los comandos de gestión. Toda la lógica vive en los casos
de uso (`aplicacion/barrido.py`); aquí sólo hay un reloj y su tolerancia a fallos: un tick que falla se registra y el siguiente lo vuelve a intentar.
La corrección de la evaluación NO depende de este hilo: cada caso de uso aplica las mismas transiciones perezosamente.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion import barrido
from .contenedor import servicios

log = logging.getLogger("avacom.evaluacion.programador")

INTERVALO_S = 5.0
ARCHIVADO_CADA_S = 60.0


class Programador(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="evaluacion-programador", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        if getattr(settings, "AVACOM_EVAL_DETECTAR_REINICIO", True):
            self._seguro("recuperar tras el reinicio", lambda: barrido.RecuperarTrasReinicio(servicios()).ejecutar())
        transcurrido = 0.0
        while not self._detener.wait(self.intervalo_s):
            transcurrido += self.intervalo_s
            self.tick(archivar=transcurrido >= ARCHIVADO_CADA_S)
            if transcurrido >= ARCHIVADO_CADA_S:
                transcurrido = 0.0
        connections.close_all()

    def tick(self, archivar: bool = False) -> None:
        self._seguro("barrer intentos", lambda: barrido.BarrerNodo(servicios()).ejecutar())
        if archivar:
            self._seguro("archivar cerradas", lambda: barrido.ArchivarCerradas(servicios()).ejecutar())

    @staticmethod
    def _seguro(nombre: str, tarea) -> None:
        close_old_connections()
        try:
            resultado = tarea()
            if any(resultado.values()) if isinstance(resultado, dict) else resultado:      # un barrido sin novedades no ensucia el registro
                log.info("%s: %s", nombre, resultado)
        except Exception:   # noqa: BLE001 — el siguiente tick lo reintenta
            log.exception("El programador de la evaluación falló en «%s»", nombre)
        finally:
            close_old_connections()


_instancia: Programador | None = None
_candado = threading.Lock()


def iniciar() -> Programador | None:
    """Arranca el programador una sola vez por proceso. `AVACOM_EVAL_PROGRAMADOR=0` lo desactiva."""
    global _instancia
    if not getattr(settings, "AVACOM_EVAL_PROGRAMADOR", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Programador()
            _instancia.start()
        return _instancia
