"""
El programador del nodo: lo que el aula hace SOLA, sin que nadie pulse nada (007-02, 007-03, 007-04).

    al arrancar          las clases que estaban abiertas quedaron interrumpidas → se suspenden para reanudarlas (BR-051)
    cada 5 segundos      «conectado» sin latido → «reconectando» → «salió» (FUN-073)
                         clase abierta sin actividad durante 120 minutos → se cierra sola (JRN-011)
    cada minuto          cerrada hace más de 24 horas → archivada (sección H)

Es un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`); no corre en las pruebas ni en los comandos de gestión.
Toda la lógica vive en los casos de uso (`aplicacion/casos_uso_tiempo_real.py`); aquí sólo hay un reloj y su tolerancia
a fallos: un tick que falla se registra y el siguiente lo vuelve a intentar, el aula no se cae por esto.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from ..aplicacion import casos_uso_tiempo_real as tr
from .contenedor import servicios

log = logging.getLogger("avacom.aula.programador")

INTERVALO_S = 5.0
ARCHIVADO_CADA_S = 60.0


class Programador(threading.Thread):
    def __init__(self, intervalo_s: float = INTERVALO_S):
        super().__init__(name="aula-programador", daemon=True)
        self.intervalo_s = intervalo_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        if getattr(settings, "AVACOM_AULA_DETECTAR_CAIDA", True):
            self._seguro("detectar caída del nodo", lambda: tr.DetectarCaida(servicios()).ejecutar())
        transcurrido = 0.0
        while not self._detener.wait(self.intervalo_s):
            transcurrido += self.intervalo_s
            self.tick(archivar=transcurrido >= ARCHIVADO_CADA_S)
            if transcurrido >= ARCHIVADO_CADA_S:
                transcurrido = 0.0
        connections.close_all()

    def tick(self, archivar: bool = False) -> None:
        self._seguro("barrer presencia", lambda: tr.BarrerPresencia(servicios()).ejecutar())
        self._seguro("cerrar inactivas", lambda: tr.CerrarInactivas(servicios()).ejecutar())
        if archivar:
            self._seguro("archivar cerradas", lambda: tr.ArchivarCerradas(servicios()).ejecutar())

    @staticmethod
    def _seguro(nombre: str, tarea) -> None:
        close_old_connections()
        try:
            resultado = tarea()
            if resultado:
                log.info("%s: %s", nombre, resultado)
        except Exception:   # noqa: BLE001 — el siguiente tick lo reintenta
            log.exception("El programador del aula falló en «%s»", nombre)
        finally:
            close_old_connections()


_instancia: Programador | None = None
_candado = threading.Lock()


def iniciar() -> Programador | None:
    """Arranca el programador una sola vez por proceso. `AVACOM_AULA_PROGRAMADOR=0` lo desactiva."""
    global _instancia
    if not getattr(settings, "AVACOM_AULA_PROGRAMADOR", True):
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Programador()
            _instancia.start()
        return _instancia
