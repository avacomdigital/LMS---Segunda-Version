r"""
La lectura de los factores de hardware de ESTE equipo (P-04), de SÓLO LECTURA y sin privilegios elevados:

  · `MachineGuid`: `HKLM\SOFTWARE\Microsoft\Cryptography` (el registro lo puede leer cualquiera)
  · SMBIOS: `GetSystemFirmwareTable('RSMB')` → `dominio/smbios.py` lo interpreta (UUID, series de placa y chasis)

Medido en la Fase 0 en la máquina de desarrollo: ≈ 0,11 ms (CIM por PowerShell tarda 2–3 s y da exactamente los mismos valores: no se usa). El UUID de SMBIOS sólo coincide con CIM si se
decodifica en formato mixto (little endian en los tres primeros campos, `uuid.UUID(bytes_le=…)`); el parser puro lo hace así.

Fuera de Windows no hay nada que leer: devuelve vacío y el nodo usa la huella de instalación. Este archivo nunca lanza: lo que no se pueda leer, no se lee (R-04). La Fase 4 llevará esta
lectura a la biblioteca nativa (`avl_fp_collect`); esta es la referencia y el respaldo.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

from ..dominio import smbios

log = logging.getLogger("avacom.licenciamiento")

VIGENCIA_S = 600           # los factores de hardware no cambian mientras el equipo está encendido: se leen una vez cada diez minutos
FIRMA_RSMB = int.from_bytes(b"RSMB", "big")


def machine_guid() -> str:
    if sys.platform != "win32":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as clave:
            return str(winreg.QueryValueEx(clave, "MachineGuid")[0])
    except OSError:
        return ""


def tabla_smbios() -> bytes:
    if sys.platform != "win32":
        return b""
    import ctypes
    kernel32 = ctypes.WinDLL(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "kernel32.dll"), use_last_error=True)
    funcion = kernel32.GetSystemFirmwareTable
    funcion.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    funcion.restype = ctypes.c_uint32
    tamano = funcion(FIRMA_RSMB, 0, None, 0)
    if not tamano:
        return b""
    buffer = ctypes.create_string_buffer(tamano)
    escrito = funcion(FIRMA_RSMB, 0, buffer, tamano)
    return buffer.raw[:escrito] if escrito else b""


class HuellaDeWindows:
    def __init__(self, vigencia_s: float = VIGENCIA_S):
        self._vigencia = vigencia_s
        self._candado = threading.Lock()
        self._cache: tuple[float, dict[int, str]] | None = None

    def crudos(self) -> dict[int, str]:
        with self._candado:
            if self._cache is not None and time.monotonic() - self._cache[0] < self._vigencia:
                return dict(self._cache[1])
            try:
                valores = smbios.factores(smbios.leer_tabla(tabla_smbios()), machine_guid())
            except Exception:   # noqa: BLE001 — sin lectura de hardware se usa la huella de instalación
                log.exception("No se pudo leer el hardware de este equipo", extra={"evento": "licencia.huella_lectura_fallo", "ruta": "bad"})
                valores = {}
            self._cache = (time.monotonic(), valores)
            return dict(valores)
