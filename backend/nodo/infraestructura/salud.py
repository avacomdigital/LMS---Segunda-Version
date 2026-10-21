"""
Lo que la infraestructura MIDE del equipo y de la base para el estado del nodo (P-09, P-16): el modo de transacción con que corre la conexión (P-02), `PRAGMA quick_check` (una vez,
al arrancar: en una base grande tarda), el tamaño del diario WAL y el espacio libre del disco donde vive la base. Nunca lanza: lo que no se pueda medir se informa como «no medido».
"""
from __future__ import annotations

import logging
import os
import shutil
import threading

from django.conf import settings
from django.db import connection

from ..dominio.estado import LecturaDeSalud

log = logging.getLogger("avacom.nodo")


class SaludDelEquipo:
    def __init__(self):
        self._candado = threading.Lock()
        self._integra: bool | None = None

    @staticmethod
    def ruta_de_la_base() -> str:
        return str(settings.DATABASES["default"].get("NAME") or "")

    @staticmethod
    def transaccion_inmediata() -> bool:
        return str(settings.DATABASES["default"].get("OPTIONS", {}).get("transaction_mode") or "").upper() == "IMMEDIATE"

    def comprobar_integridad(self) -> bool:
        """`PRAGMA quick_check` (P-10). Se hace UNA vez por proceso; el `integrity_check` completo queda para la Fase 5 (tras un apagado sucio)."""
        with self._candado:
            if self._integra is not None:
                return self._integra
            try:
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA quick_check")
                    filas = [str(f[0]) for f in cursor.fetchall()]
                self._integra = filas == ["ok"]
                if not self._integra:
                    log.error("PRAGMA quick_check: %s", "; ".join(filas)[:500], extra={"evento": "nodo.quick_check", "ruta": "bad"})
            except Exception:   # noqa: BLE001 — una base en memoria o cerrada: no se puede saber; no se restringe por no saber
                log.exception("No se pudo ejecutar PRAGMA quick_check")
                self._integra = True
            return self._integra

    def olvidar_integridad(self) -> None:
        with self._candado:
            self._integra = None

    def leer(self) -> LecturaDeSalud:
        ruta = self.ruta_de_la_base()
        wal = 0
        libre = total = None
        if ruta and ruta != ":memory:" and os.path.isabs(ruta):
            try:
                wal = os.path.getsize(ruta + "-wal")
            except OSError:
                wal = 0
            try:
                uso = shutil.disk_usage(os.path.dirname(ruta) or ".")
                libre, total = int(uso.free), int(uso.total)
            except OSError:
                libre = total = None
        integra = self._integra if self._integra is not None else True
        return LecturaDeSalud(transaccion_inmediata=self.transaccion_inmediata(), base_integra=integra, disco_libre_bytes=libre, disco_total_bytes=total, wal_bytes=int(wal))


class SaludFija:
    """Para las pruebas: la lectura que se le dé."""

    def __init__(self, lectura: LecturaDeSalud | None = None):
        self.lectura = lectura or LecturaDeSalud()

    def leer(self) -> LecturaDeSalud:
        return self.lectura

    def comprobar_integridad(self) -> bool:
        return self.lectura.base_integra
