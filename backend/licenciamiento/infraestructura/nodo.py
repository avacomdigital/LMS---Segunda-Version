"""
Lo que es propio de ESTA instalación y no sale de ella: el secreto de instalación (la huella de instalación, P-04) y la llave Ed25519 del nodo (firma solicitudes y liberaciones). Ambos
se crean la primera vez que hacen falta, se guardan en la carpeta de estado protegidos (DPAPI de máquina en Windows) y se leen una sola vez por proceso.

Si el archivo existe pero ESTA máquina no lo puede abrir (Windows reinstalado, el disco clonado a otro equipo, un blob dañado) el nodo NO reemplaza en silencio ni se queda con un valor
desechable: un valor que el siguiente arranque olvidara firmaría solicitudes con una llave que nadie recuerda y dejaría las anclas del reloj sin verificar para siempre. Se hace lo
contrario, y de forma que no se pierda nada:

  1. el archivo se APARTA (`<nombre>.ilegible-<fecha>`: se renombra, no se borra; el soporte puede devolverlo si hizo falta);
  2. se crea y se GUARDA uno nuevo: el nodo tiene identidad estable desde este arranque, y una solicitud nueva ya vale para pedir una licencia nueva (F-08);
  3. queda una NOVEDAD que la evaluación asienta como `integridad_alterada` (observación, evento y bitácora, una sola vez): nada se reemplaza sin que el administrador lo pueda saber.

Dos casos NO se tratan así, porque ahí el archivo puede estar perfectamente bien: si DPAPI no responde en este momento (`ProteccionNoDisponible`) y si el archivo está pero el disco no dejó
leerlo ahora. En ambos el archivo no se toca, esta corrida usa un valor desechable y el siguiente arranque vuelve a intentarlo.
"""
from __future__ import annotations

import logging
import secrets
import threading

from ..dominio import catalogos as cat
from ..dominio import firma
from .proteccion import ProteccionNoDisponible

log = logging.getLogger("avacom.licenciamiento")


class NodoDeLicencia:
    def __init__(self, almacen, protector):
        self._almacen, self._protector = almacen, protector
        self._candado = threading.Lock()
        self._secreto: bytes | None = None
        self._llave: tuple[bytes, bytes] | None = None
        self._novedades: list[str] = []          # nombres de los archivos que se apartaron y aún no se asientan

    def _guardar_nuevo(self, nombre: str, crear) -> bytes:
        valor = crear()
        try:
            self._almacen.escribir(nombre, self._protector.proteger(valor))
        except Exception:   # noqa: BLE001 — sin poder guardarlo el secreto vale esta corrida; el siguiente arranque creará otro (la huella de instalación cambiará y se dirá)
            log.exception("No se pudo guardar %s", nombre, extra={"evento": "licencia.secreto_no_guardado", "ruta": "bad"})
        return valor

    def _reemplazar_ilegible(self, nombre: str, crear) -> bytes:
        log.error("No se pudo abrir %s: este equipo no puede leer el secreto guardado; se aparta y se crea uno nuevo", nombre, extra={"evento": "licencia.secreto_ilegible", "ruta": "bad"})
        try:
            apartado = self._almacen.poner_en_cuarentena(nombre)
        except Exception:   # noqa: BLE001 — si no se puede apartar no se pisa: se queda como está
            log.exception("No se pudo apartar %s", nombre, extra={"evento": "licencia.secreto_no_apartado", "ruta": "bad"})
            apartado = None
        if apartado is None:
            return crear()
        log.error("%s quedó apartado como %s", nombre, apartado, extra={"evento": "licencia.secreto_apartado", "ruta": "bad"})
        self._novedades.append(nombre)
        return self._guardar_nuevo(nombre, crear)

    def _cargar_o_crear(self, nombre: str, crear) -> bytes:
        blob = self._almacen.leer(nombre)
        if blob is None:
            if self._almacen.existe(nombre):
                log.error("%s existe pero no se pudo leer ahora: no se toca", nombre, extra={"evento": "licencia.secreto_no_leido", "ruta": "bad"})
                return crear()
            return self._guardar_nuevo(nombre, crear)
        try:
            return self._protector.desproteger(blob)
        except ProteccionNoDisponible:
            log.exception("DPAPI no responde: %s no se toca y esta corrida usa un valor desechable", nombre, extra={"evento": "licencia.secreto_no_disponible", "ruta": "bad"})
            return crear()
        except Exception:   # noqa: BLE001 — ilegible de verdad en esta máquina
            return self._reemplazar_ilegible(nombre, crear)

    def secreto_de_instalacion(self) -> bytes:
        with self._candado:
            if self._secreto is None:
                self._secreto = self._cargar_o_crear(cat.ARCHIVO_SECRETO, lambda: secrets.token_bytes(32))
            return self._secreto

    def _par(self) -> tuple[bytes, bytes]:
        with self._candado:
            if self._llave is None:
                privada = self._cargar_o_crear(cat.ARCHIVO_LLAVE_NODO, lambda: firma.par_nuevo()[0])
                self._llave = (privada, firma.publica_de(privada))
            return self._llave

    def clave_privada(self) -> bytes:
        return self._par()[0]

    def clave_publica(self) -> bytes:
        return self._par()[1]

    def anotar_novedad(self, nombre: str) -> None:
        """Deja una novedad de integridad que no viene de un archivo apartado (la biblioteca nativa que la instalación esperaba y no cargó). Una sola vez por nombre."""
        with self._candado:
            if nombre not in self._novedades:
                self._novedades.append(nombre)

    def tomar_novedades(self) -> list[str]:
        """Los archivos que se apartaron desde la última vez (una sola entrega: la evaluación los asienta)."""
        with self._candado:
            entregadas, self._novedades = self._novedades, []
        return entregadas

    def devolver_novedades(self, nombres: list[str]) -> None:
        """Si lo entregado no llegó a asentarse, vuelve a la cola para el siguiente ciclo."""
        with self._candado:
            self._novedades = list(nombres) + self._novedades
