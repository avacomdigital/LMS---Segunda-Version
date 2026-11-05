r"""
La carpeta de respaldos (`%ProgramData%\AVACOM\OPS Master\Respaldos\`):

    *.avbak            los respaldos terminados (cifrados)
    trabajo\           instantáneas y restauraciones en curso; se vacía solo
    estado\            la clave y la identidad del nodo (ver `clavero.py`)
    Informes\          LO QUE LEE EL PERSONAL ADMINISTRATIVO: una constancia por respaldo, el resumen CSV y los informes de restauración (texto llano, sin datos de personas)
    entrada\           donde se deja un respaldo traído a mano para restaurar

Todo se escribe como temporal y se renombra: nunca queda un respaldo ni un informe a medias con su nombre final.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from ..dominio import catalogos as cat

_NOMBRE_INFORME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
_NOMBRE_RESPALDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.avbak$")


class AlmacenEnCarpeta:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        self.trabajo = self.raiz / "trabajo"
        self.informes = self.raiz / "Informes"
        for carpeta in (self.raiz, self.trabajo, self.informes, self.raiz / "entrada"):
            carpeta.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------------------------------------------------------ los respaldos
    def abrir_para_escribir(self, respaldo_id: str) -> tuple[BinaryIO, tuple]:
        ruta = self.raiz / f"{re.sub(r'[^A-Za-z0-9-]', '', respaldo_id)[:40]}{cat.EXTENSION_PARCIAL}"
        f = open(ruta, "wb")
        return f, (f, ruta)

    def terminar(self, manija: tuple, respaldo_id: str, creado_en: int, tipo: str) -> str:
        f, ruta = manija
        f.flush()
        os.fsync(f.fileno())
        f.close()
        fecha = datetime.fromtimestamp(int(creado_en) / 1000).strftime("%Y%m%d-%H%M")
        nombre = f"respaldo-{fecha}-{tipo}-{respaldo_id[:8].lower()}{cat.EXTENSION}"
        os.replace(ruta, self.raiz / nombre)
        return nombre

    def descartar(self, manija: tuple) -> None:
        f, ruta = manija
        try:
            f.close()
        except OSError:
            pass
        try:
            ruta.unlink()
        except OSError:
            pass

    def _ruta(self, nombre: str) -> Path | None:
        return self.raiz / nombre if _NOMBRE_RESPALDO.match(nombre or "") else None

    def abrir(self, nombre: str) -> BinaryIO | None:
        ruta = self._ruta(nombre)
        try:
            return open(ruta, "rb") if ruta is not None else None
        except OSError:
            return None

    def tamano(self, nombre: str) -> int | None:
        ruta = self._ruta(nombre)
        try:
            return ruta.stat().st_size if ruta is not None else None
        except OSError:
            return None

    def borrar(self, nombre: str) -> bool:
        ruta = self._ruta(nombre)
        try:
            if ruta is not None:
                ruta.unlink()
                return True
        except OSError:
            pass
        return False

    def listar(self) -> list[str]:
        return sorted(p.name for p in self.raiz.iterdir() if p.is_file() and _NOMBRE_RESPALDO.match(p.name))

    def ruta_de(self, nombre: str) -> Path | None:
        ruta = self._ruta(nombre)
        return ruta if ruta is not None and ruta.is_file() else None

    # ------------------------------------------------------------------------------------------------------------------ trabajo
    def carpeta_de_trabajo(self, etiqueta: str) -> Path:
        self.trabajo.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=f"{re.sub(r'[^A-Za-z0-9-]', '', etiqueta)[:40]}-", dir=self.trabajo))

    def limpiar_trabajo(self, ruta: Path) -> None:
        try:
            if self.trabajo.resolve() in Path(ruta).resolve().parents:
                shutil.rmtree(ruta, ignore_errors=True)
        except OSError:
            pass

    def espacio_libre(self) -> int | None:
        try:
            return shutil.disk_usage(self.raiz).free
        except OSError:
            return None

    # ------------------------------------------------------------------------------------------------------------------ informes
    def guardar_informe(self, nombre: str, texto: str, con_bom: bool = False) -> None:
        if not _NOMBRE_INFORME.match(nombre):
            raise ValueError("Nombre de informe inválido.")
        self.informes.mkdir(parents=True, exist_ok=True)
        tmp = self.informes / (nombre + ".tmp")
        tmp.write_text(texto, encoding="utf-8-sig" if con_bom else "utf-8", newline="")
        os.replace(tmp, self.informes / nombre)

    def leer_informe(self, nombre: str) -> str | None:
        if not _NOMBRE_INFORME.match(nombre or ""):
            return None
        try:
            return (self.informes / nombre).read_bytes().decode("utf-8-sig")
        except OSError:
            return None

    def listar_informes(self) -> list[str]:
        try:
            return sorted((p.name for p in self.informes.iterdir() if p.is_file() and not p.name.endswith(".tmp")), reverse=True)
        except OSError:
            return []
