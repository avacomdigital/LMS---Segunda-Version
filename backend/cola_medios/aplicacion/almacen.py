"""
El disco de la caché: un archivo por recurso (`objetos/<aa>/<id>.bin`), que crece mientras se descarga y se queda como está al terminar.

Se nombra por el id del recurso y no por su SHA-256 a propósito: mientras baja, las peticiones que lo siguen lo tienen abierto, y en Windows un archivo abierto
no se puede renombrar. El SHA-256 se calcula al vuelo, se guarda en la base y es el `ETag`; el archivo en sí no se sirve nunca como archivo estático: sólo
lo lee la cola, detrás de la autorización del módulo que lo pidió.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path


class Lectores:
    """Cuántas respuestas están leyendo cada archivo ahora mismo: un archivo en lectura no se expulsa."""

    def __init__(self):
        self._candado = threading.Lock()
        self._cuenta: dict[str, int] = {}

    def entrar(self, recurso_id: str) -> None:
        with self._candado:
            self._cuenta[recurso_id] = self._cuenta.get(recurso_id, 0) + 1

    def salir(self, recurso_id: str) -> None:
        with self._candado:
            n = self._cuenta.get(recurso_id, 0) - 1
            if n > 0:
                self._cuenta[recurso_id] = n
            else:
                self._cuenta.pop(recurso_id, None)

    def activos(self, recurso_id: str) -> int:
        with self._candado:
            return self._cuenta.get(recurso_id, 0)

    def total(self) -> int:
        with self._candado:
            return sum(self._cuenta.values())


class Almacen:
    def __init__(self, carpeta: str | os.PathLike):
        self.carpeta = Path(carpeta)
        self.lectores = Lectores()

    def preparar(self) -> None:
        (self.carpeta / "objetos").mkdir(parents=True, exist_ok=True)

    def vaciar(self) -> None:
        """Borra todo lo guardado (pruebas y «Vaciar caché»). En Windows lo que esté abierto se queda y el barrido de huérfanos lo quita luego."""
        shutil.rmtree(self.carpeta / "objetos", ignore_errors=True)
        self.preparar()

    def ruta(self, recurso_id: str) -> Path:
        return self.carpeta / "objetos" / recurso_id[:2] / f"{recurso_id}.bin"

    def abrir_para_escribir(self, recurso_id: str, *, continuar: bool):
        ruta = self.ruta(recurso_id)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        return open(ruta, "ab" if continuar else "wb")

    def tamano(self, recurso_id: str) -> int:
        try:
            return self.ruta(recurso_id).stat().st_size
        except OSError:
            return 0

    def existe(self, recurso_id: str) -> bool:
        return self.ruta(recurso_id).is_file()

    def borrar(self, recurso_id: str) -> bool:
        """True si ya no está. En Windows un archivo abierto no se borra: se queda y el barrido de huérfanos lo quita después."""
        try:
            self.ruta(recurso_id).unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def libre_bytes(self) -> int:
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            return shutil.disk_usage(self.carpeta).free
        except OSError:
            return 0

    def huerfanos(self, ids_validos: set[str], *, mas_viejos_de_seg: float = 600.0) -> list[Path]:
        """Archivos de `objetos/` que ninguna fila reclama y que llevan un rato sin tocarse (restos de un recurso expulsado o de un reinicio a medias)."""
        salida: list[Path] = []
        raiz = self.carpeta / "objetos"
        if not raiz.is_dir():
            return salida
        limite = time.time() - mas_viejos_de_seg
        for archivo in raiz.rglob("*.bin"):
            try:
                if archivo.stem not in ids_validos and archivo.stat().st_mtime < limite:
                    salida.append(archivo)
            except OSError:
                continue
        return salida
