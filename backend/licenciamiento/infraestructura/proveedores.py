"""
Los dos adaptadores del puerto «de dónde sale el estado de la licencia» (R-05):

  `LicenciaIlimitada`  desarrollo y pruebas: nada se restringe. Los límites de concurrencia (BR-063) son los de `settings` de siempre y NO hay cupo de equipos ni de usuarios.
  `LicenciaFirmada`    producción: la instantánea que calcula `Evaluar` con la licencia firmada, la huella de este equipo y el reloj confiable.

Los dos responden SIN consultar la base de datos (R-07): leen la instantánea en memoria. Si la de producción todavía no se calculó (el nodo acaba de arrancar), devuelve None y quien
pregunta deja pasar (R-04): una licencia que no se pudo evaluar nunca cierra nada.
"""
from __future__ import annotations

import time

from ..aplicacion.base import Servicios, ilimitada
from ..aplicacion.puertos import Instantanea


class LicenciaIlimitada:
    def __init__(self, servicios: Servicios):
        self._s = servicios
        self._instantanea: Instantanea | None = None

    def instantanea(self) -> Instantanea:
        if self._instantanea is None:
            self._instantanea = ilimitada(self._s.config, int(time.time() * 1000))
        return self._instantanea


class LicenciaFirmada:
    def __init__(self, servicios: Servicios):
        self._s = servicios

    def instantanea(self) -> Instantanea | None:
        return self._s.vivo.leer()


def proveedor(servicios: Servicios):
    return LicenciaFirmada(servicios) if servicios.config.modo == "firmada" else LicenciaIlimitada(servicios)
