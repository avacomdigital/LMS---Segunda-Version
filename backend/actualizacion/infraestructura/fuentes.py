r"""
Dónde pueden aparecer paquetes (CAP-106, P-11): las unidades EXTRAÍBLES de Windows (la raíz y su carpeta `AVACOM\`) y la carpeta `Actualizaciones\entrada\`. La API nunca recibe una
ruta: cada `.avupd` encontrado recibe un identificador opaco (huella de dónde está, cómo se llama, cuánto mide y cuándo cambió), y es el nodo quien lo resuelve al importar.

En desarrollo y pruebas, `AVACOM_ACTUALIZACION_UNIDADES` (carpetas separadas por `;`) hace de unidades extraíbles (una carpeta montada con `subst` también sirve).
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path

from ..aplicacion.puertos import Candidato
from ..dominio import catalogos as cat

DRIVE_REMOVABLE = 2
SUBCARPETAS = ("", "AVACOM")


def unidades_extraibles() -> list[tuple[str, Path]]:
    """`(rótulo, raíz)` de cada unidad extraíble montada (sólo Windows)."""
    if os.name != "nt":
        return []
    try:
        mascara = ctypes.windll.kernel32.GetLogicalDrives()
    except (AttributeError, OSError):
        return []
    salida = []
    for i in range(26):
        if not mascara & (1 << i):
            continue
        letra = f"{chr(65 + i)}:\\"
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letra)) == DRIVE_REMOVABLE:
                salida.append((letra[:2], Path(letra)))
        except (AttributeError, OSError):
            continue
    return salida


class FuentesDelNodo:
    def __init__(self, entrada: Path, unidades_fijas: list[Path] | None = None, max_bytes: int = cat.MAX_PAQUETE_BYTES, usar_unidades_reales: bool = True):
        self.entrada = Path(entrada)
        self.unidades_fijas = [Path(u) for u in (unidades_fijas or [])]
        self.max_bytes = int(max_bytes)
        self.usar_unidades_reales = usar_unidades_reales

    def _fuentes(self) -> list[tuple[str, str, Path]]:
        fuentes: list[tuple[str, str, Path]] = [(cat.O_ENTRADA, "Carpeta de entrada", self.entrada)]
        for u in self.unidades_fijas:
            fuentes.append((cat.O_UNIDAD, u.name or str(u), u))
        if self.usar_unidades_reales:
            for rotulo, raiz in unidades_extraibles():
                fuentes.append((cat.O_UNIDAD, rotulo, raiz))
        return fuentes

    def _enumerar(self) -> list[tuple[Candidato, Path]]:
        salida: list[tuple[Candidato, Path]] = []
        for origen, rotulo, raiz in self._fuentes():
            for sub in (SUBCARPETAS if origen == cat.O_UNIDAD else ("",)):
                carpeta = raiz / sub if sub else raiz
                try:
                    entradas = sorted(p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() == cat.EXTENSION)
                except OSError:
                    continue
                for ruta in entradas:
                    try:
                        st = ruta.stat()
                    except OSError:
                        continue
                    huella = hashlib.sha256(f"{origen}|{rotulo}|{sub}|{ruta.name}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")).hexdigest()[:24]
                    salida.append((Candidato(id=huella, nombre=ruta.name[:160], origen=origen, bytes=int(st.st_size), modificado_en=int(st.st_mtime * 1000), fuente=rotulo), ruta))
        return salida

    def candidatos(self) -> list[Candidato]:
        return [c for c, _ in self._enumerar()]

    def leer(self, candidato_id: str) -> tuple[Candidato, bytes] | None:
        for candidato, ruta in self._enumerar():
            if candidato.id != candidato_id:
                continue
            try:
                with open(ruta, "rb") as f:
                    datos = f.read(self.max_bytes + 1)       # acotado: lo que pase del tope lo rechaza el verificador (`demasiado_grande`)
            except OSError:
                return None
            return candidato, datos
        return None
