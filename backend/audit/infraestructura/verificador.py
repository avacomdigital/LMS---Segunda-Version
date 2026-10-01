"""
El temporizador de la bitácora (§1.2, §4.3): un hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`, como el
programador del aula) que cada `AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S` segundos (una hora por defecto) verifica la
cadena y, si el tramo abierto supera el umbral de tamaño, lo rota. No corre en las pruebas ni en los comandos de
gestión. Un tick que falla se registra y el siguiente lo reintenta: el nodo no se cae por esto.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from .. import contexto
from ..aplicacion import rotar, verificar
from ..logging_setup import CANAL_AUDITORIA, LOGGER_AUDITORIA

log = logging.getLogger(LOGGER_AUDITORIA)

PRIMERA_ESPERA_S = 60.0


class Verificador(threading.Thread):
    def __init__(self, cada_s: float):
        super().__init__(name="auditoria-verificador", daemon=True)
        self.cada_s = cada_s
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        espera = min(PRIMERA_ESPERA_S, self.cada_s)
        while not self._detener.wait(espera):
            espera = self.cada_s
            self.tick()
        connections.close_all()

    def tick(self) -> None:
        with contexto.con(origen=contexto.ORIGEN_SISTEMA, corr=contexto.nuevo_corr(), usuario_id=None, rol_codigo=None, dispositivo_id=None):
            self._seguro("verificar la cadena", lambda: verificar.verificar_cadena())
            self._seguro("rotar por tamaño", rotar.rotar_si_supera)

    @staticmethod
    def _seguro(nombre: str, tarea) -> None:
        close_old_connections()
        try:
            resultado = tarea()
            if resultado:
                log.info("%s: %s", nombre, resultado.get("estado", "ok") if isinstance(resultado, dict) else resultado,
                         extra={"canal": CANAL_AUDITORIA, "evento": "auditoria.temporizador", "ruta": "happy"})
        except Exception:   # noqa: BLE001 — el siguiente tick lo reintenta
            log.exception("El temporizador de auditoría falló en «%s»", nombre,
                          extra={"canal": CANAL_AUDITORIA, "evento": "auditoria.temporizador_fallo", "ruta": "bad"})
        finally:
            close_old_connections()


_instancia: Verificador | None = None
_candado = threading.Lock()


def iniciar() -> Verificador | None:
    """Arranca el verificador una sola vez por proceso. `AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S=0` lo desactiva."""
    global _instancia
    cada_s = float(getattr(settings, "AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S", 3600) or 0)
    if cada_s <= 0:
        return None
    with _candado:
        if _instancia is None or not _instancia.is_alive():
            _instancia = Verificador(cada_s)
            _instancia.start()
        return _instancia
