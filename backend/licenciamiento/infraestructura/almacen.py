r"""
La carpeta de estado de la licencia: `%ProgramData%\AVACOM\OPS Master\Config\licencia\` en un nodo instalado (R-11: NO `SecureStorage`, que es por usuario mientras el servicio corre como
SYSTEM; se conserva al actualizar y, por omisión, al desinstalar). Archivos con nombre fijo, escritos de forma ATÓMICA (temporal → vaciado a disco → renombrar): un corte de luz nunca deja
un archivo a medias. Un archivo ilegible equivale a ausente para lo que se puede recalcular (el espejo, las tumbas, las anclas): nunca cierra nada (R-04). Para lo que NO se puede recalcular
(el secreto de instalación y la llave del nodo) `existe` distingue «no está» de «está y no pude leerlo», y `poner_en_cuarentena` aparta el archivo sin borrarlo.
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger("avacom.licenciamiento")

_NOMBRE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SUFIJO_ILEGIBLE = ".ilegible-"
CUARENTENA_MAXIMA = 5            # de cada archivo se conservan los últimos que se apartaron: un lazo de fallos no llena el disco


def _nombre_apartado(nombre: str, existentes, ahora_s: float) -> str:
    """`<nombre>.ilegible-<n:04d>-<fecha UTC>`. El número SUBE con cada archivo apartado: el orden por nombre es el orden en el tiempo aunque el reloj se mueva o se limpien los viejos
    (nunca se reutiliza el nombre de uno borrado: la limpieza conserva siempre los más recientes); la fecha es para quien lo busque."""
    prefijo = f"{nombre}{SUFIJO_ILEGIBLE}"
    numeros = [int(n[len(prefijo):len(prefijo) + 4]) for n in existentes if n.startswith(prefijo) and n[len(prefijo):len(prefijo) + 4].isdigit()]
    return f"{prefijo}{max(numeros, default=0) + 1:04d}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime(ahora_s))}"


def _sobrantes(nombres) -> list[str]:
    """De los archivos apartados de un mismo nombre, los que SOBRAN (los más viejos: el nombre ordena por antigüedad)."""
    return sorted(nombres)[:-CUARENTENA_MAXIMA]


class AlmacenEnCarpeta:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)

    def _ruta(self, nombre: str) -> Path:
        if not _NOMBRE.match(nombre):
            raise ValueError(f"Nombre de archivo de estado no válido: {nombre!r}")
        return self.carpeta / nombre

    def leer(self, nombre: str) -> bytes | None:
        try:
            return self._ruta(nombre).read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            log.exception("No se pudo leer %s de la carpeta de estado de la licencia", nombre, extra={"evento": "licencia.estado_lectura_fallo", "ruta": "bad"})
            return None

    def existe(self, nombre: str) -> bool:
        try:
            return self._ruta(nombre).exists()
        except OSError:
            return True              # ante la duda, está: lo que no se puede mirar no se pisa

    def escribir(self, nombre: str, datos: bytes) -> None:
        destino = self._ruta(nombre)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(f".{nombre}.{os.getpid()}.tmp")
        try:
            with open(temporal, "wb") as archivo:
                archivo.write(datos)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        finally:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass

    def borrar(self, nombre: str) -> None:
        try:
            self._ruta(nombre).unlink(missing_ok=True)
        except OSError:
            log.exception("No se pudo borrar %s de la carpeta de estado de la licencia", nombre, extra={"evento": "licencia.estado_borrado_fallo", "ruta": "bad"})

    def poner_en_cuarentena(self, nombre: str) -> str | None:
        """Aparta `nombre` a `nombre.ilegible-<fecha UTC>` (renombrar, nunca borrar) y devuelve el nombre nuevo; `None` si no se pudo. Sólo se conservan los últimos `CUARENTENA_MAXIMA`."""
        origen = self._ruta(nombre)
        try:
            apartado = _nombre_apartado(nombre, (p.name for p in self.carpeta.glob(f"{nombre}{SUFIJO_ILEGIBLE}*")), time.time())
            os.replace(origen, self.carpeta / apartado)
        except OSError:
            log.exception("No se pudo apartar %s de la carpeta de estado de la licencia", nombre, extra={"evento": "licencia.estado_cuarentena_fallo", "ruta": "bad"})
            return None
        try:
            for viejo in _sobrantes(p.name for p in self.carpeta.glob(f"{nombre}{SUFIJO_ILEGIBLE}*")):
                (self.carpeta / viejo).unlink(missing_ok=True)
        except OSError:
            pass                     # limpiar es un lujo: el archivo ya quedó apartado
        return apartado


class AlmacenEnMemoria:
    """Para las pruebas: la misma interfaz sin tocar el disco."""

    def __init__(self):
        self.archivos: dict[str, bytes] = {}

    def leer(self, nombre: str) -> bytes | None:
        return self.archivos.get(nombre)

    def existe(self, nombre: str) -> bool:
        return nombre in self.archivos

    def escribir(self, nombre: str, datos: bytes) -> None:
        self.archivos[nombre] = bytes(datos)

    def borrar(self, nombre: str) -> None:
        self.archivos.pop(nombre, None)

    def poner_en_cuarentena(self, nombre: str) -> str | None:
        if nombre not in self.archivos:
            return None
        apartado = _nombre_apartado(nombre, list(self.archivos), time.time())
        self.archivos[apartado] = self.archivos.pop(nombre)
        for viejo in _sobrantes(n for n in self.archivos if n.startswith(f"{nombre}{SUFIJO_ILEGIBLE}")):
            self.archivos.pop(viejo, None)
        return apartado
