r"""
Las ANCLAS del reloj (P-06): la marca alta guardada FUERA de la base de datos, para que restaurar una copia de seguridad vieja no «rebobine» el vencimiento.

  · un archivo en la carpeta de estado (`ancla-reloj.json`): la marca alta y el inicio de la ventana de evaluación, con una verificación (HMAC-SHA256 con una llave derivada del secreto de
    instalación): si alguien edita el archivo, la verificación falla, el ancla NO cuenta y se avisa como integridad alterada
  · una clave del registro de Windows (`HKLM\SOFTWARE\AVACOM\OPS Master\Licencia`, valores `Marca` y `Mac`), sólo en producción: la escribe el servicio (SYSTEM)

Y una tercera ancla vive en otro módulo: la fecha del último asiento de la bitácora encadenada (MOD-019).

Lo que esto NO impide (A4): quien administra el equipo y conoce el diseño puede borrar el archivo y la clave y, con una copia vieja de la base, volver a un estado anterior. Se deja
rastro y se limita el daño; no se promete lo contrario (04-proteccion.md). La Fase 4 moverá la verificación a la biblioteca nativa (`avl_clock_advance`).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path

from ..aplicacion.puertos import LecturaDeAnclas
from ..dominio import catalogos as cat
from .integridad import ARCHIVO as ARCHIVO_DE_SENAL
from .integridad import SenalDeIntegridad

log = logging.getLogger("avacom.licenciamiento")

RAMA = r"SOFTWARE\AVACOM\OPS Master\Licencia"


def _mac(secreto: bytes, marca: int, instalada_en: int | None) -> str:
    llave = hashlib.sha256(b"avl-ancla-v1|" + secreto).digest()
    return hmac.new(llave, f"{int(marca)}|{'' if instalada_en is None else int(instalada_en)}".encode("ascii"), hashlib.sha256).hexdigest()


class RegistroDeWindows:
    """La clave del registro. Leer puede cualquiera; escribir, sólo SYSTEM o un administrador: quien no puede, no escribe y no pasa nada."""

    def leer(self) -> tuple[int, str] | None:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RAMA, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as clave:
                marca, _ = winreg.QueryValueEx(clave, "Marca")
                mac, _ = winreg.QueryValueEx(clave, "Mac")
            return int(marca), str(mac)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None

    def escribir(self, marca: int, mac: str) -> None:
        import winreg
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, RAMA, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as clave:
                winreg.SetValueEx(clave, "Marca", 0, winreg.REG_QWORD, int(marca))
                winreg.SetValueEx(clave, "Mac", 0, winreg.REG_SZ, mac)
        except OSError:
            pass            # sin permiso de escritura (un desarrollador): el ancla de archivo y la de la bitácora siguen


class AnclasDeLicencia:
    def __init__(self, almacen, nodo, registro: RegistroDeWindows | None = None, senal: SenalDeIntegridad | None = None):
        self._almacen, self._nodo, self._registro = almacen, nodo, registro
        # P-23: la señal de integridad del despliegue (la deja el Host junto a la carpeta de estado: `Config\integridad.json`). Sólo en un nodo instalado de Windows (el que tiene `registro`);
        # en desarrollo y pruebas no se lee nada salvo que se inyecte.
        self._senal = senal if senal is not None else (SenalDeIntegridad(Path(almacen.carpeta).parent / ARCHIVO_DE_SENAL) if registro is not None and hasattr(almacen, "carpeta") else None)

    def leer(self) -> LecturaDeAnclas:
        secreto = self._nodo.secreto_de_instalacion()
        marcas: dict[str, int] = {}
        alteradas: list[str] = []
        instalada_en = None
        crudo = self._almacen.leer(cat.ARCHIVO_ANCLA)
        if crudo is not None:
            try:
                datos = json.loads(crudo.decode("utf-8"))
                marca, instalada = int(datos["marca"]), datos.get("instalada_en")
                instalada = int(instalada) if instalada is not None else None
                if hmac.compare_digest(str(datos.get("mac", "")), _mac(secreto, marca, instalada)):
                    marcas["archivo"], instalada_en = marca, instalada
                else:
                    alteradas.append("archivo")
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                alteradas.append("archivo")
        if self._registro is not None:
            leido = self._registro.leer()
            if leido is not None:
                marca, mac = leido
                if hmac.compare_digest(mac, _mac(secreto, marca, None)):
                    marcas["registro"] = marca
                else:
                    alteradas.append("registro")
        if self._senal is not None:
            alteradas.extend(self._senal.alteradas())       # `despliegue:<tipo>`: evidencia del Host; recorre el mismo camino que las demás alteraciones y jamás degrada nada
        return LecturaDeAnclas(marcas=marcas, instalada_en=instalada_en, alteradas=tuple(alteradas))

    def escribir(self, marca_ms: int, instalada_en: int | None = None) -> None:
        secreto = self._nodo.secreto_de_instalacion()
        if instalada_en is None:
            instalada_en = self.leer().instalada_en           # conserva el que ya hay (verificado)
        cuerpo = {"marca": int(marca_ms), "instalada_en": instalada_en, "mac": _mac(secreto, marca_ms, instalada_en)}
        self._almacen.escribir(cat.ARCHIVO_ANCLA, json.dumps(cuerpo, separators=(",", ":")).encode("utf-8"))
        if self._registro is not None:
            self._registro.escribir(marca_ms, _mac(secreto, marca_ms, None))
