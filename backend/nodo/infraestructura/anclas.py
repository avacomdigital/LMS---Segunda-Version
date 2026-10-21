r"""
Las anclas FUERA de la base (P-12, P-13): un archivo JSON en la carpeta de estado del nodo con la mayor secuencia emitida y la marca alta del reloj, escrito de forma ATÓMICA
(temporal → vaciado a disco → renombrar) con una huella SHA-256 para detectar un archivo a medias o editado. Una copia de seguridad restaurada no lo rebobina: por eso sirve para
detectar la restauración y no repetir una secuencia (INV-002).

Carpeta: en producción `%ProgramData%\AVACOM\OPS Master\Config\nodo\`; en desarrollo, `AVACOM_NODO_DIR` o una carpeta temporal estable; en las pruebas SIEMPRE una carpeta temporal
por corrida (jamás ProgramData). Un archivo ilegible equivale a ausente (se dice en el log): nunca impide arrancar.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from ..dominio.anclas import Ancla

log = logging.getLogger("avacom.nodo")

ARCHIVO = "ancla-cola.json"


def _huella(cuerpo: dict) -> str:
    base = json.dumps({k: v for k, v in cuerpo.items() if k != "huella"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"avacom-nodo-ancla-v1|" + base).hexdigest()


class AnclasEnCarpeta:
    def __init__(self, carpeta: Path | str):
        self.carpeta = Path(carpeta)
        self.ruta = self.carpeta / ARCHIVO

    def leer(self) -> Ancla | None:
        try:
            crudo = self.ruta.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            log.exception("No se pudo leer el ancla %s: se trata como ausente", self.ruta, extra={"evento": "nodo.ancla_ilegible", "ruta": "bad"})
            return None
        try:
            cuerpo = json.loads(crudo.decode("utf-8"))
            if cuerpo.get("huella") != _huella(cuerpo):
                log.error("El ancla %s no pasa su verificación: se trata como ausente", self.ruta, extra={"evento": "nodo.ancla_alterada", "ruta": "bad"})
                return None
            return Ancla(int(cuerpo["secuencia"]), int(cuerpo.get("marca_alta", 0)), int(cuerpo.get("escrita_en", 0)))
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            log.exception("El ancla %s está dañada: se trata como ausente", self.ruta, extra={"evento": "nodo.ancla_danada", "ruta": "bad"})
            return None

    def escribir(self, ancla: Ancla) -> None:
        cuerpo = {"secuencia": int(ancla.secuencia), "marca_alta": int(ancla.marca_alta), "escrita_en": int(ancla.escrita_en)}
        cuerpo["huella"] = _huella(cuerpo)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        temporal = self.ruta.with_name(f".{ARCHIVO}.{os.getpid()}.tmp")
        try:
            with open(temporal, "wb") as archivo:
                archivo.write(json.dumps(cuerpo, separators=(",", ":")).encode("utf-8"))
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, self.ruta)
        finally:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass


class AnclasEnMemoria:
    """Para las pruebas de dominio y de aplicación: la misma interfaz sin disco."""

    def __init__(self, ancla: Ancla | None = None):
        self.ancla = ancla
        self.escrituras = 0

    def leer(self) -> Ancla | None:
        return self.ancla

    def escribir(self, ancla: Ancla) -> None:
        self.ancla = ancla
        self.escrituras += 1
