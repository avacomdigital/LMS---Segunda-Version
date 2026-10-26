r"""
Aplica una restauración SOBRE el equipo vivo. Es la única pieza de MOD-016 que escribe fuera de `m16_*` y de su carpeta, y sólo para devolver lo respaldado:

  · la BASE: con la API de respaldo de SQLite desde la copia ya descifrada y comprobada (`PRAGMA integrity_check`) hacia la conexión del propio nodo. La API copia en UNA transacción de
    escritura de la destino: o queda la base nueva o queda la anterior, nunca una mezcla. Después se restituye el modo WAL del nodo (la copia trae el encabezado del modo de la fuente).
  · los ARCHIVOS: uno a uno con `os.replace` (temporal junto al destino). No se borra lo que sobre.

Se llama con el nodo SIN clase en curso (lo comprueba el caso de uso) y, tras aplicar, el servicio recomienda reiniciar.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from django.db import connection

from ..dominio import formato
from .origen import copiar_base

log = logging.getLogger("avacom.respaldo")

_conocidas: set[tuple[str, str]] | None = None


def migraciones_conocidas() -> set[tuple[str, str]]:
    """Las migraciones que ESTE código trae (las que `manage.py migrate` sabría aplicar)."""
    global _conocidas
    if _conocidas is None:
        from django.db.migrations.loader import MigrationLoader
        _conocidas = set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)
    return _conocidas


def _conexion_del_nodo():
    connection.ensure_connection()
    return connection.connection


class AplicadorSqlite:
    def __init__(self, origen, destino=_conexion_del_nodo):
        self.origen = origen
        self._destino = destino                       # una función que devuelve la conexión sqlite3 de la base VIVA (las pruebas le pasan otra)

    def comprobar_base(self, ruta: Path) -> dict:
        try:
            with closing(sqlite3.connect(Path(ruta).resolve().as_uri() + "?mode=ro", uri=True)) as con:
                resultado = con.execute("PRAGMA integrity_check").fetchall()
                tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                migradas = {tuple(f) for f in con.execute("SELECT app, name FROM django_migrations")} if "django_migrations" in tablas else set()
        except sqlite3.Error:
            return {"integra": False, "migraciones_desconocidas": [], "tablas": 0}
        integra = resultado == [("ok",)] and "django_migrations" in tablas
        desconocidas = sorted(f"{a}.{n}" for a, n in migradas - migraciones_conocidas())
        return {"integra": integra, "migraciones_desconocidas": desconocidas, "tablas": len(tablas)}

    def aplicar_base(self, ruta: Path) -> dict:
        destino = self._destino()
        with closing(sqlite3.connect(str(ruta))) as origen:
            copiar_base(origen, destino)
        try:
            destino.execute("PRAGMA journal_mode=WAL")                # el nodo corre en WAL (settings.py): la copia trae el modo de la fuente
        except sqlite3.Error:
            log.warning("No se pudo restituir el modo WAL tras restaurar", extra={"evento": "respaldo.wal_no_restituido", "ruta": "bad"})
        return {"ok": True}

    def aplicar_archivos(self, nombre_de_carpeta: str, clase: str, desde: Path) -> int:
        carpeta = next((c for c in self.origen.carpetas(True) if c.nombre == nombre_de_carpeta), None)
        if carpeta is None:
            log.warning("La carpeta «%s» del respaldo ya no está configurada: no se restaura", nombre_de_carpeta, extra={"evento": "respaldo.carpeta_ausente", "ruta": "bad"})
            return 0
        raiz = carpeta.ruta.resolve()
        aplicados = 0
        for origen in sorted(p for p in Path(desde).rglob("*") if p.is_file()):
            relativa = origen.relative_to(desde).as_posix()
            if not formato.ruta_segura(f"{nombre_de_carpeta}/{relativa}"):
                continue
            destino = (raiz / relativa).resolve()
            if raiz not in destino.parents:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            tmp = destino.with_name(destino.name + ".restaurando")
            shutil.copy2(origen, tmp)
            os.replace(tmp, destino)
            aplicados += 1
        return aplicados
