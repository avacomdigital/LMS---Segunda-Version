"""
Arranque del backend CIFRADO de AVACOM OPS Master (segunda proteccion, S2).

El codigo propio del backend no viaja como `.py` ni como `.pyc`: viaja en `Backend\\codigo.avpkg`, un archivo que guarda el BYTECODE de cada modulo cifrado (AES-256-GCM, una llave por modulo
derivada de una llave de paquete `K`). `K` no esta en el instalador ni en el disco: el Host la libera desde el TPM del equipo sellado (clave de cifrado RSA no exportable) y se la pasa a este
programa por la ENTRADA ESTANDAR, en la primera linea:

    AVACOM-CLAVE <64 hexadecimales>\\n

Este archivo es PUBLICO por diseno (no lleva ningun secreto, como el resto de Runtime): lo unico que hace es leer `K`, abrir el paquete y poner un buscador de modulos delante del de Python. Lo que
protege es que sin `K` el codigo no existe en claro; lo que NO protege (declarado): quien administra el equipo y puede volcar la memoria del proceso mientras corre vera el codigo y `K` (A4).

Uso (lo lanza el Host; nadie lo corre a mano):

    python avacom_boot.py manage <argumentos de manage.py>      → ejecuta el `manage.py` del paquete
    python avacom_boot.py script <ruta.py> [argumentos]         → ejecuta un script suelto (el arranque del servidor) con el paquete ya instalado
    python avacom_boot.py code <codigo> [argumentos]            → el equivalente de `python -c <codigo>` (el Host lo usa para leer la configuracion efectiva)

Lo que se resuelve para que Django funcione sin archivos `.py`:
  · `sys.meta_path[0]`: busca modulos y paquetes en el paquete cifrado (`__file__` y `__path__` apuntan a la carpeta REAL de Backend, para que los datos que viajan al lado —JSON de llaves, atestacion—
    se encuentren igual).
  · `sys.path_hooks[0]`: para que `pkgutil.iter_modules` liste los modulos cifrados de una carpeta (Django descubre asi las migraciones y los comandos de manage.py).
"""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import marshal
import os
import runpy
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"AVPK"
VERSION = 1
ALGORITMO_AES256GCM = 1
PREFIJO_CLAVE = "AVACOM-CLAVE "
NOMBRE_DEL_PAQUETE = "codigo.avpkg"


class ErrorDePaquete(Exception):
    """El paquete cifrado no se puede abrir (falta, esta alterado, es de otro Python o la llave no es la suya)."""


def _derivar(k: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"avacom-pkg|" + info).derive(k)


def kid_de(k: bytes) -> bytes:
    """Un identificador de 8 bytes de la llave (SHA-256 de la llave), para saber qué `.avclave` abre qué paquete sin revelar la llave."""
    return hashlib.sha256(b"avacom-kid|" + k).digest()[:8]


def leer_cabecera(datos: bytes) -> dict:
    """La cabecera NO esta cifrada (dice con que llave y con que Python se hizo): `kid`, magia del bytecode y el largo del indice."""
    if len(datos) < 4 + 2 + 1 + 8 + 4 + 2 + 12 + 4 or datos[:4] != MAGIC:
        raise ErrorDePaquete("formato")
    version = int.from_bytes(datos[4:6], "big")
    if version != VERSION or datos[6] != ALGORITMO_AES256GCM:
        raise ErrorDePaquete("version")
    kid, magia, py = datos[7:15], datos[15:19], (datos[19], datos[20])
    nonce = datos[21:33]
    largo = int.from_bytes(datos[33:37], "big")
    if 37 + largo > len(datos):
        raise ErrorDePaquete("formato")
    return {"kid": kid, "magia": magia, "python": py, "nonce": nonce, "largo_indice": largo, "inicio_indice": 37, "inicio_datos": 37 + largo, "cabecera": datos[:37]}


class Paquete:
    """El paquete abierto: el indice descifrado y los datos en memoria. `modulo(nombre)` devuelve el codigo de un modulo (descifra al pedirlo)."""

    def __init__(self, datos: bytes, k: bytes):
        c = leer_cabecera(datos)
        if c["kid"] != kid_de(k):
            raise ErrorDePaquete("llave_distinta")
        if c["magia"] != importlib.util.MAGIC_NUMBER[:4] or c["python"] != (sys.version_info[0], sys.version_info[1]):
            raise ErrorDePaquete("python_distinto")
        try:
            crudo = AESGCM(_derivar(k, b"indice")).decrypt(c["nonce"], datos[c["inicio_indice"]:c["inicio_datos"]], c["cabecera"])
        except InvalidTag:
            raise ErrorDePaquete("alterado") from None
        self._datos = memoryview(datos)[c["inicio_datos"]:]
        self._k = bytearray(k)
        contenido = json.loads(crudo.decode("utf-8"))
        # El indice esta autenticado y lleva el SHA-256 de TODOS los datos: un byte cambiado en cualquier modulo se detecta al abrir, no cuando ese modulo se importe por primera vez.
        if hashlib.sha256(self._datos).hexdigest() != contenido["datos_sha256"]:
            raise ErrorDePaquete("alterado")
        self._indice: dict[str, dict] = contenido["modulos"]
        self.kid = c["kid"]
        self._ramas: dict[str, set[str]] = {}
        for nombre, e in self._indice.items():
            padre = nombre.rpartition(".")[0]
            self._ramas.setdefault(padre, set()).add(nombre)
            if e["p"]:
                self._ramas.setdefault(nombre, set())

    def __contains__(self, nombre: str) -> bool:
        return nombre in self._indice

    def es_paquete(self, nombre: str) -> bool:
        return bool(self._indice[nombre]["p"])

    def ruta(self, nombre: str) -> str:
        return self._indice[nombre]["r"]

    def hijos(self, paquete: str) -> list[tuple[str, bool]]:
        """(nombre corto, ¿es paquete?) de lo que hay directamente dentro de `paquete` ('' = la raiz)."""
        return sorted((h.rpartition(".")[2], self._indice[h]["p"]) for h in self._ramas.get(paquete, ()))

    def codigo(self, nombre: str):
        e = self._indice[nombre]
        blob = bytes(self._datos[e["o"]:e["o"] + e["l"]])
        try:
            crudo = AESGCM(_derivar(bytes(self._k), b"modulo|" + e["r"].encode("utf-8"))).decrypt(bytes.fromhex(e["n"]), blob, e["r"].encode("utf-8"))
        except InvalidTag:
            raise ErrorDePaquete("alterado") from None
        return marshal.loads(crudo)


class _Cargador(importlib.abc.Loader):
    def __init__(self, paquete: Paquete, raiz: Path):
        self._p, self._raiz = paquete, raiz

    def create_module(self, spec):
        return None

    def get_code(self, nombre: str):
        return self._p.codigo(nombre)

    def exec_module(self, modulo):
        exec(self.get_code(modulo.__spec__.name), modulo.__dict__)       # noqa: S102 — el codigo es el propio del producto, ya autenticado por GCM

    def get_filename(self, nombre: str) -> str:
        return str(self._raiz / self._p.ruta(nombre))

    def is_package(self, nombre: str) -> bool:
        return self._p.es_paquete(nombre)


class Buscador(importlib.abc.MetaPathFinder):
    """El buscador que se pone delante del de Python: resuelve los modulos que estan en el paquete y deja pasar los demas (Django, DRF, la biblioteca estandar)."""

    def __init__(self, paquete: Paquete, raiz: Path):
        self._p, self._raiz = paquete, raiz
        self._cargador = _Cargador(paquete, raiz)

    def find_spec(self, nombre, ruta=None, destino=None):
        if nombre not in self._p:
            return None
        archivo = self._cargador.get_filename(nombre)
        spec = importlib.machinery.ModuleSpec(nombre, self._cargador, origin=archivo, is_package=self._p.es_paquete(nombre))
        spec.has_location = True
        if self._p.es_paquete(nombre):
            spec.submodule_search_locations = [str(Path(archivo).parent)]
        return spec

    def invalidate_caches(self):
        pass


class _BuscadorDeRuta:
    """Lo que `pkgutil.iter_modules([carpeta])` encuentra para una carpeta de Backend: los modulos del paquete cifrado que viven en ella."""

    def __init__(self, paquete: Paquete, raiz: Path, carpeta: Path):
        self._p = paquete
        self._rel = carpeta.relative_to(raiz).as_posix()
        self._nombre = "" if self._rel == "." else self._rel.replace("/", ".")

    def find_spec(self, nombre, destino=None):
        return None            # la busqueda real la hace el buscador de meta_path

    def iter_modules(self, prefijo: str = ""):
        for corto, es_pkg in self._p.hijos(self._nombre):
            yield prefijo + corto, es_pkg


def _gancho_de_ruta(paquete: Paquete, raiz: Path):
    raiz_texto = os.path.normcase(str(raiz))

    def gancho(ruta_texto: str):
        try:
            actual = Path(ruta_texto)
            if not os.path.normcase(str(actual)).startswith(raiz_texto):
                raise ImportError
            carpeta = actual.resolve()
            carpeta.relative_to(raiz)
        except (ValueError, OSError):
            raise ImportError from None
        rel = carpeta.relative_to(raiz).as_posix()
        nombre = "" if rel == "." else rel.replace("/", ".")
        if nombre and nombre not in paquete:
            raise ImportError
        return _BuscadorDeRuta(paquete, raiz, carpeta)

    return gancho


def instalar(paquete: Paquete, raiz: Path) -> Buscador:
    """Pone el paquete delante: buscador de modulos y gancho de rutas. Se puede llamar una vez por proceso."""
    raiz = raiz.resolve()
    buscador = Buscador(paquete, raiz)
    sys.meta_path.insert(0, buscador)
    sys.path_hooks.insert(0, _gancho_de_ruta(paquete, raiz))
    sys.path_importer_cache.clear()
    # `pkgutil.iter_modules` usa el metodo `iter_modules` del buscador de la ruta (`_BuscadorDeRuta`) sin que haga falta registrar nada.
    return buscador


# --------------------------------------------------------------------------------------------------------------------------------- arranque
def leer_clave_de_la_entrada(flujo=None) -> bytes:
    """La primera linea de la entrada: `AVACOM-CLAVE <hex>`. Nada mas se lee: lo que siga (la orden «detener» del Host) lo consume el servidor."""
    flujo = flujo or sys.stdin
    linea = flujo.readline()
    if not linea.startswith(PREFIJO_CLAVE):
        raise ErrorDePaquete("sin_clave")
    try:
        k = bytes.fromhex(linea[len(PREFIJO_CLAVE):].strip())
    except ValueError:
        raise ErrorDePaquete("sin_clave") from None
    if len(k) != 32:
        raise ErrorDePaquete("sin_clave")
    return k


def abrir(raiz_de_backend: Path, k: bytes) -> Paquete:
    ruta = raiz_de_backend / NOMBRE_DEL_PAQUETE
    try:
        return Paquete(ruta.read_bytes(), k)
    except OSError as error:
        raise ErrorDePaquete("sin_paquete") from error


def principal(argv: list[str]) -> int:
    runtime = Path(__file__).resolve().parent
    backend = (runtime.parent / "Backend").resolve()
    if len(argv) < 2 or argv[1] not in ("manage", "script", "code"):
        print("uso: avacom_boot.py manage <args> | script <ruta.py> [args] | code <codigo> [args]", file=sys.stderr)
        return 2
    try:
        k = leer_clave_de_la_entrada()
        paquete = abrir(backend, k)
    except ErrorDePaquete as error:
        print(f"AVACOM: no se pudo abrir el codigo del nodo ({error}).", file=sys.stderr)
        return 3
    instalar(paquete, backend)
    k = b""                                                         # el Paquete conserva su propia copia (bytearray); esta referencia ya no hace falta
    if argv[1] == "manage":
        sys.argv = ["manage.py", *argv[2:]]
        os.chdir(backend)
        runpy.run_module("manage", run_name="__main__", alter_sys=False)
        return 0
    if argv[1] == "code":                                           # el equivalente de `python -c <codigo>`, con el paquete ya instalado
        sys.argv = ["-c", *argv[3:]]
        os.chdir(backend)
        exec(compile(argv[2], "<-c>", "exec"), {"__name__": "__main__", "__builtins__": __builtins__})      # noqa: S102 — lo que pide el propio Host
        return 0
    sys.argv = argv[2:]
    runpy.run_path(argv[2], run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv))
