"""
Aviso a las pantallas de una clase cuando cambia el estado de sus recursos: un `cambio` con `que = "medios"` por el canal en tiempo real del aula.

El aviso NUNCA lleva bytes ni contenido: sólo cuántos recursos de esa clase están listos, preparándose o fallidos. Los clientes que no lo conocen lo tratan
como cualquier otro cambio (piden el estado por HTTP). Se agrupa: como mucho uno cada `intervalo` segundos por clase, para que preparar un objeto de diez
medios no sacuda a cuarenta tabletas diez veces.
"""
from __future__ import annotations

import logging
import threading
import time

from django.db import close_old_connections

from ..dominio import catalogos as cat
from ..aplicacion.puertos import Registro

log = logging.getLogger("avacom.cola_medios")


class DifusionAula:
    def __init__(self, registro: Registro, intervalo_seg: float = 2.0):
        self.registro = registro
        self.intervalo = intervalo_seg
        self._candado = threading.Lock()
        self._ultimo: dict[str, float] = {}
        self._diferidos: dict[str, threading.Timer] = {}

    def recurso_cambio(self, modulo: str, contexto_ref: str) -> None:
        if modulo != cat.MODULO_AULA or not contexto_ref:
            return          # el modo estudio y la evaluación consultan su avance por HTTP; sólo la clase en vivo recibe aviso
        with self._candado:
            ahora = time.monotonic()
            desde = ahora - self._ultimo.get(contexto_ref, 0.0)
            if desde >= self.intervalo:
                self._ultimo[contexto_ref] = ahora
                enviar_ya = True
            else:
                enviar_ya = False
                if contexto_ref not in self._diferidos:
                    temporizador = threading.Timer(self.intervalo - desde, self._enviar_diferido, (contexto_ref,))
                    temporizador.daemon = True
                    self._diferidos[contexto_ref] = temporizador
                    temporizador.start()
        if enviar_ya:
            self._enviar(contexto_ref)

    def _enviar_diferido(self, contexto_ref: str) -> None:
        with self._candado:
            self._diferidos.pop(contexto_ref, None)
            self._ultimo[contexto_ref] = time.monotonic()
        self._enviar(contexto_ref)

    def _enviar(self, contexto_ref: str) -> None:
        from classroom_engine.infraestructura.tiempo_real import TiempoRealCanales
        try:
            filas = self.registro.del_contexto(contexto_ref, cat.MODULO_AULA)
            carga = {
                "listos": sum(1 for f in filas if f["estado"] == cat.DISPONIBLE),
                "preparando": sum(1 for f in filas if f["estado"] in cat.ACTIVOS),
                "fallidos": sum(1 for f in filas if f["estado"] in (cat.FALLIDO, cat.CANCELADO)),
            }
            TiempoRealCanales._emitir(contexto_ref, "medios", carga, False)
        except Exception:   # noqa: BLE001 — el aviso es una cortesía: la clase sigue sin él
            log.exception("No se pudo avisar a la clase del estado de sus medios", extra={"evento": "medios.cola.aviso_fallo"})
        finally:
            close_old_connections()


class SinDifusion:
    def recurso_cambio(self, modulo: str, contexto_ref: str) -> None:
        return None
