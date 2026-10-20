"""
Protección de los secretos propios del nodo (el secreto de instalación y su llave Ed25519): DPAPI con el ámbito de la MÁQUINA en Windows (`CRYPTPROTECT_LOCAL_MACHINE`): lo abre el
servicio (SYSTEM) y cualquier cuenta de esta máquina, y no se puede abrir copiando el archivo a OTRO equipo. Medido en la Fase 0 sin elevar privilegios: ida y vuelta correcta, y un blob
alterado o una entropía distinta fallan.

Límites que se dicen en voz alta: quien tenga el DISCO COMPLETO clonado y lo arranque en otro hardware obtiene las mismas llaves de máquina de DPAPI; por eso la huella de INSTALACIÓN es el
nivel más débil y se muestra como tal. Fuera de Windows (desarrollo, pruebas) no hay DPAPI: `SinProteccion` guarda los bytes con una marca y nada más.

Cada blob lleva una marca de 5 bytes que dice con qué se protegió, para poder leer lo que dejó una versión sin DPAPI y no confundirlo.
"""
from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger("avacom.licenciamiento")

ENTROPIA = b"AVACOM LMS licencia v1"
MARCA_SIN_PROTECCION, MARCA_DPAPI = b"AVLP0", b"AVLP1"
CRYPTPROTECT_UI_FORBIDDEN, CRYPTPROTECT_LOCAL_MACHINE = 0x1, 0x4


class ProteccionFallida(Exception):
    """El blob no se pudo abrir: otra máquina, formato desconocido o un blob dañado. Es un hecho del ARCHIVO, no del momento."""


class ProteccionNoDisponible(ProteccionFallida):
    """El archivo parece bueno pero DPAPI no responde en este momento: es un hecho del ENTORNO, y no hay que concluir nada del archivo (no se aparta ni se reemplaza)."""


class SinProteccion:
    nombre = "sin_proteccion"

    def proteger(self, datos: bytes) -> bytes:
        return MARCA_SIN_PROTECCION + bytes(datos)

    def desproteger(self, blob: bytes) -> bytes:
        if blob[:5] != MARCA_SIN_PROTECCION:
            raise ProteccionFallida("El archivo no está en el formato sin protección.")
        return bytes(blob[5:])


class DpapiDeMaquina:
    nombre = "dpapi_maquina"

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        raiz = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        crypt32 = ctypes.WinDLL(os.path.join(raiz, "crypt32.dll"), use_last_error=True)         # ruta absoluta: nunca el directorio actual ni el PATH
        kernel32 = ctypes.WinDLL(os.path.join(raiz, "kernel32.dll"), use_last_error=True)
        p_blob, p_void = ctypes.POINTER(Blob), ctypes.c_void_p
        crypt32.CryptProtectData.argtypes = [p_blob, wintypes.LPCWSTR, p_blob, p_void, p_void, wintypes.DWORD, p_blob]
        crypt32.CryptUnprotectData.argtypes = [p_blob, p_void, p_blob, p_void, p_void, wintypes.DWORD, p_blob]
        crypt32.CryptProtectData.restype = crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [p_void]
        kernel32.LocalFree.restype = p_void
        self._c, self._Blob, self._crypt32, self._kernel32 = ctypes, Blob, crypt32, kernel32

    def _blob(self, datos: bytes):
        buffer = self._c.create_string_buffer(bytes(datos), max(len(datos), 1))
        return self._Blob(len(datos), self._c.cast(buffer, self._c.POINTER(self._c.c_char))), buffer

    def _llamar(self, proteger: bool, datos: bytes) -> bytes:
        c = self._c
        entrada, retener_a = self._blob(datos)
        entropia, retener_b = self._blob(ENTROPIA)
        salida = self._Blob()
        if proteger:
            ok = self._crypt32.CryptProtectData(c.byref(entrada), "AVACOM", c.byref(entropia), None, None, CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE, c.byref(salida))
        else:
            ok = self._crypt32.CryptUnprotectData(c.byref(entrada), None, c.byref(entropia), None, None, CRYPTPROTECT_UI_FORBIDDEN, c.byref(salida))
        if not ok:
            raise ProteccionFallida(f"DPAPI respondió con el error {c.get_last_error()}")
        try:
            return c.string_at(salida.pbData, salida.cbData)
        finally:
            self._kernel32.LocalFree(c.cast(salida.pbData, c.c_void_p))
            del retener_a, retener_b

    def proteger(self, datos: bytes) -> bytes:
        return MARCA_DPAPI + self._llamar(True, datos)

    def desproteger(self, blob: bytes) -> bytes:
        if blob[:5] != MARCA_DPAPI:
            raise ProteccionFallida("El archivo no está protegido con DPAPI.")
        return self._llamar(False, bytes(blob[5:]))


class ProtectorAutomatico:
    """DPAPI de máquina si Windows lo da; si no, sin protección (se registra). Lee los dos formatos: lo que dejó una instalación sin DPAPI se sigue abriendo."""

    def __init__(self):
        self._sin = SinProteccion()
        self._dpapi = None
        if sys.platform == "win32":
            try:
                candidato = DpapiDeMaquina()
                if candidato.desproteger(candidato.proteger(b"prueba-avacom")) == b"prueba-avacom":
                    self._dpapi = candidato
            except Exception:   # noqa: BLE001 — sin DPAPI se sigue: el nivel de la huella lo dirá
                log.exception("DPAPI no está disponible: los secretos del nodo se guardan sin proteger", extra={"evento": "licencia.dpapi_no_disponible", "ruta": "bad"})

    @property
    def nombre(self) -> str:
        return self._dpapi.nombre if self._dpapi else self._sin.nombre

    def proteger(self, datos: bytes) -> bytes:
        return (self._dpapi or self._sin).proteger(datos)

    def desproteger(self, blob: bytes) -> bytes:
        if blob[:5] == MARCA_DPAPI:
            if self._dpapi is None:
                raise ProteccionNoDisponible("El archivo está protegido con DPAPI y DPAPI no responde en esta máquina ahora.")
            return self._dpapi.desproteger(blob)
        return self._sin.desproteger(blob)
