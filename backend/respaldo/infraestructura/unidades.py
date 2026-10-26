r"""
Las unidades extraíbles y la carpeta de entrada (FUN-176, JRN-019): los `.avbak` se EXPORTAN a `AVACOM\Respaldos\` de una unidad y se TRAEN de ahí para restaurar en un equipo nuevo. La API
nunca recibe una letra de unidad ni una ruta: cada unidad y cada archivo tienen un identificador opaco y es el nodo quien lo resuelve.

En desarrollo y pruebas, `AVACOM_RESPALDO_UNIDADES` (carpetas separadas por `;`) hace de unidades extraíbles (una carpeta montada con `subst` también sirve).
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
from pathlib import Path

from ..aplicacion.puertos import CandidatoDeRespaldo, Unidad
from ..dominio import catalogos as cat
from ..dominio.errores import EspacioInsuficiente, NoEncontrado

DRIVE_REMOVABLE = 2
SUBCARPETAS = ("", "AVACOM", "AVACOM/Respaldos")
DESTINO = ("AVACOM", "Respaldos")


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


def _id(*partes: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:24]


class UnidadesDelNodo:
    def __init__(self, entrada: Path, unidades_fijas: list[Path] | None = None, usar_unidades_reales: bool = True):
        self.entrada = Path(entrada)
        self.unidades_fijas = [Path(u) for u in (unidades_fijas or [])]
        self.usar_unidades_reales = usar_unidades_reales

    def _raices(self) -> list[tuple[str, str, Path]]:
        raices = [(_id("fija", str(u)), u.name or str(u), u) for u in self.unidades_fijas]
        if self.usar_unidades_reales:
            raices += [(_id("extraible", rotulo), rotulo, raiz) for rotulo, raiz in unidades_extraibles()]
        return raices

    def listar(self) -> list[Unidad]:
        salida = []
        for uid, rotulo, raiz in self._raices():
            try:
                libre = shutil.disk_usage(raiz).free
            except OSError:
                continue                                                 # la unidad se retiró entre dos lecturas
            salida.append(Unidad(uid, rotulo, int(libre)))
        return salida

    def copiar(self, unidad_id: str, origen: Path, nombre: str, extras: dict[str, str] | None = None) -> str:
        for uid, rotulo, raiz in self._raices():
            if uid != unidad_id:
                continue
            tam = Path(origen).stat().st_size
            try:
                libre = shutil.disk_usage(raiz).free
            except OSError:
                raise NoEncontrado("Esa unidad ya no está conectada.") from None
            if libre < tam + cat.MARGEN_ESPACIO // 8:
                raise EspacioInsuficiente(f"La unidad tiene {libre // cat.MIB} MB libres y el respaldo mide {tam // cat.MIB} MB.", necesario=tam, libre=libre)
            destino = raiz.joinpath(*DESTINO)
            destino.mkdir(parents=True, exist_ok=True)
            tmp = destino / (nombre + ".parcial")
            try:
                shutil.copyfile(origen, tmp)
                if tmp.stat().st_size != tam:
                    raise OSError("La copia no midió lo mismo que el original.")
                os.replace(tmp, destino / nombre)
            finally:
                if tmp.exists():
                    tmp.unlink()
            for extra, texto in (extras or {}).items():
                (destino / extra).write_text(texto, encoding="utf-8")
            return rotulo
        raise NoEncontrado("Esa unidad ya no está conectada.")

    def _enumerar(self) -> list[tuple[CandidatoDeRespaldo, Path]]:
        fuentes = [("Carpeta de entrada", self.entrada, ("",))] + [(rotulo, raiz, SUBCARPETAS) for _uid, rotulo, raiz in self._raices()]
        salida: list[tuple[CandidatoDeRespaldo, Path]] = []
        vistos: set[Path] = set()
        for rotulo, raiz, subs in fuentes:
            for sub in subs:
                carpeta = raiz / sub if sub else raiz
                try:
                    archivos = sorted(p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() == cat.EXTENSION)
                except OSError:
                    continue
                for ruta in archivos:
                    if ruta in vistos:
                        continue
                    vistos.add(ruta)
                    try:
                        st = ruta.stat()
                    except OSError:
                        continue
                    salida.append((CandidatoDeRespaldo(_id(rotulo, sub, ruta.name, st.st_size, int(st.st_mtime)), ruta.name[:160], int(st.st_size), rotulo, int(st.st_mtime * 1000)), ruta))
        return salida

    def candidatos(self) -> list[CandidatoDeRespaldo]:
        return [c for c, _ in self._enumerar()]

    def traer(self, candidato_id: str, destino: Path) -> CandidatoDeRespaldo | None:
        for candidato, ruta in self._enumerar():
            if candidato.id != candidato_id:
                continue
            destino = Path(destino)
            destino.mkdir(parents=True, exist_ok=True)
            tmp = destino / (candidato.nombre + ".parcial")
            try:
                shutil.copyfile(ruta, tmp)
                os.replace(tmp, destino / candidato.nombre)
            except OSError:
                return None
            return candidato
        return None
