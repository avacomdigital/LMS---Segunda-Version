r"""
La identidad y las claves de este equipo para los respaldos, FUERA de la base de datos: una restauración devuelve la base al pasado y NO debe rebobinar ni perder la clave con que se
cifró lo que sigue en disco.

  `estado\nodo.key`    la clave del nodo (AES-256, 32 bytes). En Windows va protegida con DPAPI ligada al EQUIPO (`CRYPTPROTECT_LOCAL_MACHINE`): copiar el archivo a otro equipo no sirve
                       de nada (BR-102). Fuera de Windows (desarrollo) se guarda tal cual.
  `estado\nodo.json`   `nodo_id` (identificador público de este equipo para los respaldos) y, si la institución ya tiene código de custodia, su sal y la clave de custodia DERIVADA envuelta
                       con la clave del nodo. El código en sí NUNCA se guarda.

Escrituras atómicas (temporal → disco → renombrar).
"""
from __future__ import annotations

import ctypes
import json
import os
import threading
import uuid
from ctypes import wintypes
from pathlib import Path

from ..dominio import cripto

_ENTROPIA = b"avacom-respaldo-nodo-v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPTPROTECT_LOCAL_MACHINE = 0x4
_MARCA_DPAPI, _MARCA_CLARA = b"AVK1", b"AVK0"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(datos: bytes) -> tuple[_Blob, object]:
    buf = ctypes.create_string_buffer(bytes(datos), len(datos))
    return _Blob(len(datos), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(datos: bytes, proteger: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    entrada, _b1 = _blob(datos)
    entropia, _b2 = _blob(_ENTROPIA)
    salida = _Blob()
    f = crypt32.CryptProtectData if proteger else crypt32.CryptUnprotectData
    f.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR if proteger else ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                  wintypes.DWORD, ctypes.POINTER(_Blob)]
    f.restype = wintypes.BOOL
    if not f(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, _CRYPTPROTECT_UI_FORBIDDEN | (_CRYPTPROTECT_LOCAL_MACHINE if proteger else 0), ctypes.byref(salida)):
        raise OSError("DPAPI no pudo " + ("proteger" if proteger else "abrir") + " la clave del nodo.")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def _atomico(ruta: Path, datos: bytes) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


class ClaveroDelNodo:
    def __init__(self, carpeta: Path, usar_dpapi: bool | None = None):
        self.carpeta = Path(carpeta) / "estado"
        self.usar_dpapi = (os.name == "nt") if usar_dpapi is None else usar_dpapi
        self._candado = threading.Lock()

    # ------------------------------------------------------------------------------------------------------------------ la clave del nodo
    def clave_del_nodo(self) -> bytes:
        with self._candado:
            ruta = self.carpeta / "nodo.key"
            if ruta.exists():
                crudo = ruta.read_bytes()
                if crudo[:4] == _MARCA_DPAPI:
                    return _dpapi(crudo[4:], proteger=False)
                if crudo[:4] == _MARCA_CLARA and len(crudo) == 4 + cripto.LARGO_CLAVE:
                    return crudo[4:]
                raise OSError("La clave del nodo está dañada.")
            clave = cripto.generar_clave()
            _atomico(ruta, _MARCA_DPAPI + _dpapi(clave, proteger=True) if self.usar_dpapi else _MARCA_CLARA + clave)
            return clave

    # ------------------------------------------------------------------------------------------------------------------ identidad y custodia
    def _leer(self) -> dict:
        ruta = self.carpeta / "nodo.json"
        if ruta.exists():
            try:
                return json.loads(ruta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return {}

    def _escribir(self, datos: dict) -> None:
        _atomico(self.carpeta / "nodo.json", json.dumps(datos, ensure_ascii=True, sort_keys=True, indent=1).encode("ascii"))

    def nodo_id(self) -> str:
        with self._candado:
            datos = self._leer()
            if not datos.get("nodo_id"):
                datos["nodo_id"] = str(uuid.uuid4())
                self._escribir(datos)
            return datos["nodo_id"]

    def custodia(self) -> dict | None:
        datos = self._leer().get("custodia")
        if not datos:
            return None
        try:
            clave = cripto.desenvolver(self.clave_del_nodo(), bytes.fromhex(datos["nonce"]), bytes.fromhex(datos["clave"]), b"avbak-custodia-estado")
            return {"emitida_en": int(datos["emitida_en"]), "sal": bytes.fromhex(datos["sal"]), "clave": clave}
        except (cripto.ClaveIncorrecta, KeyError, ValueError):
            return None

    def guardar_custodia(self, emitida_en: int, sal: bytes, clave: bytes) -> None:
        nodo = self.clave_del_nodo()
        nodo_id = self.nodo_id()
        nonce, envuelta = cripto.envolver(nodo, clave, b"avbak-custodia-estado")
        with self._candado:
            datos = self._leer()
            datos["nodo_id"] = nodo_id
            datos["custodia"] = {"emitida_en": int(emitida_en), "sal": bytes(sal).hex(), "nonce": nonce.hex(), "clave": envuelta.hex()}
            self._escribir(datos)
