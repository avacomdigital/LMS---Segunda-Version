r"""
Lo que hay que respaldar:

  · la BASE DE DATOS del aula, con la API de respaldo de SQLite sobre la conexión del propio nodo: una copia consistente sin detener a nadie (en modo WAL los escritores siguen).
    Hoy es lo irreemplazable (respuestas, intentos, calificaciones, incidentes, auditoría, presencia: «Qué entra al respaldo y qué no» del Maestro).
  · las CARPETAS de archivos de la institución que declara `AVACOM_RESPALDO_CARPETAS` (`nombre=ruta` o `nombre:reinstalable=ruta`, separadas por `;`). Lo marcado como reinstalable (la
    biblioteca, los medios en caché) NO entra salvo que el técnico lo pida. Un incremental sólo lleva lo modificado desde el respaldo anterior.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from pathlib import Path

from django.db import connection

from ..aplicacion.puertos import ArchivoDeOrigen, CarpetaDeOrigen
from ..dominio import catalogos as cat
from ..dominio import formato

log = logging.getLogger("avacom.respaldo")
_NOMBRE_CARPETA = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


ESPERA_MAXIMA_S = 60


def copiar_base(origen: sqlite3.Connection, destino: sqlite3.Connection) -> None:
    """La API de respaldo de SQLite con una cota: si la base de origen está ocupada (una escritura de esta misma conexión la deja en `LOCKED`) más de `ESPERA_MAXIMA_S`, falla en vez de reintentar para siempre."""
    inicio = time.monotonic()

    def progreso(estado, _restantes, _total):
        if estado in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) and time.monotonic() - inicio > ESPERA_MAXIMA_S:
            raise sqlite3.OperationalError("La base estuvo ocupada más de un minuto: el respaldo se reintenta.")

    origen.backup(destino, pages=-1, progress=progreso, sleep=0.25)


def analizar_carpetas(crudo: str) -> list[CarpetaDeOrigen]:
    salida: list[CarpetaDeOrigen] = []
    for parte in str(crudo or "").split(";"):
        if "=" not in parte:
            continue
        clave, ruta = parte.split("=", 1)
        nombre, _, clase = clave.strip().partition(":")
        clase = clase.strip() or cat.CLASE_PRIMARIO
        if not _NOMBRE_CARPETA.match(nombre) or clase not in cat.CLASES_DE_ARCHIVO or not ruta.strip():
            log.warning("AVACOM_RESPALDO_CARPETAS: se ignora una entrada inválida", extra={"evento": "respaldo.carpeta_invalida", "ruta": "bad"})
            continue
        salida.append(CarpetaDeOrigen(nombre, clase, Path(ruta.strip())))
    return salida[:cat.ORIGENES_DE_ARCHIVO_MAX]


class OrigenDelNodo:
    def __init__(self, carpetas_crudo: str = ""):
        self.carpetas_crudo = carpetas_crudo

    # ------------------------------------------------------------------------------------------------------------------ la base
    def instantanea_de_la_base(self, destino: Path) -> int:
        connection.ensure_connection()
        origen = connection.connection
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        copia = sqlite3.connect(str(destino))
        try:
            copiar_base(origen, copia)
            copia.execute("PRAGMA journal_mode=DELETE")          # una sola archivo: sin -wal ni -shm a su lado
            copia.commit()
        finally:
            copia.close()
        return destino.stat().st_size

    def bytes_de_la_base(self) -> int:
        connection.ensure_connection()
        with connection.cursor() as c:
            c.execute("PRAGMA page_count")
            paginas = c.fetchone()[0]
            c.execute("PRAGMA page_size")
            tam = c.fetchone()[0]
        return int(paginas) * int(tam)

    # ------------------------------------------------------------------------------------------------------------------ los archivos de la institución
    def carpetas(self, incluir_reinstalable: bool) -> list[CarpetaDeOrigen]:
        return [c for c in analizar_carpetas(self.carpetas_crudo) if c.ruta.is_dir() and (incluir_reinstalable or c.clase == cat.CLASE_PRIMARIO)]

    def archivos(self, incluir_reinstalable: bool, desde_ms: int | None) -> tuple[list[ArchivoDeOrigen], list[str]]:
        encontrados: list[ArchivoDeOrigen] = []
        omitidos: list[str] = []
        for carpeta in self.carpetas(incluir_reinstalable):
            for raiz, _dirs, nombres in os.walk(carpeta.ruta, followlinks=False):
                for n in sorted(nombres):
                    ruta = Path(raiz) / n
                    try:
                        if ruta.is_symlink() or not ruta.is_file():
                            continue
                        st = ruta.stat()
                    except OSError:
                        continue
                    nombre = f"{carpeta.nombre}/{ruta.relative_to(carpeta.ruta).as_posix()}"
                    if not formato.ruta_segura(nombre):
                        omitidos.append(nombre)
                        continue
                    modificado = int(st.st_mtime * 1000)
                    if desde_ms is not None and modificado < int(desde_ms):
                        continue
                    encontrados.append(ArchivoDeOrigen(nombre, carpeta.clase, int(st.st_size), modificado, lambda r=ruta: open(r, "rb")))
        return encontrados, omitidos
