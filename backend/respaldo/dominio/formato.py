r"""
El archivo de respaldo `.avbak` (BR-102, TST-058, TST-059). Un contenedor propio, leído con un lector estricto:

    AVBK · versión (u16) · largo del manifiesto (u32) · manifiesto (JSON canónico, en claro) · trozos { largo (u32) · texto cifrado + etiqueta }

  · El manifiesto va en CLARO y sin datos de personas: identificador, tipo, instante, versión del producto, secuencia global, cuántas entradas y bytes, las dos claves de datos
    envueltas. Así el nodo reconoce y cataloga un respaldo sin descifrarlo (también uno que llegó en una memoria USB).
  · Lo demás —los nombres de los archivos, su contenido, su huella— va CIFRADO, en un flujo de registros: `E` entrada (cabecera JSON + exactamente `bytes` bytes + SHA-256) y `F` fin.
    Ni el nombre de un archivo de un alumno se lee en claro (INV-021).
  · La AAD de cada trozo incluye el SHA-256 de la cabecera completa (magic, versión y manifiesto): cambiar un byte del manifiesto invalida TODOS los trozos. El largo del flujo y
    el número de trozos están en el manifiesto: truncar, sobrar o reordenar se detecta aunque cada trozo, solo, fuera válido.

Escribir no necesita pasar dos veces por los datos: el largo del flujo se calcula de antemano con los tamaños de las entradas, y si una entrada cambió de tamaño mientras se leía el
respaldo falla (`ArchivoCambio`) y se repite. Puro: no importa Django.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import BinaryIO

from . import catalogos as cat
from . import cripto
from .errores import RespaldoRechazado

MAGIC = b"AVBK"
BASE_DE_DATOS = "base.sqlite3"            # el nombre de la entrada de la base de datos dentro del respaldo
_REG_ENTRADA, _REG_FIN = b"E", b"F"
_MAX_MANIFIESTO = 64 * 1024
_MAX_CABECERA = 64 * 1024
_COMPONENTE = re.compile(r"^[\w][\w.\- ()&,'+]{0,119}$")
_UUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class ArchivoCambio(Exception):
    """Un archivo cambió de tamaño mientras se respaldaba: el respaldo no es consistente y se repite."""


@dataclass
class Entrada:
    nombre: str                                    # ruta relativa con `/` (la base es `BASE_DE_DATOS`; lo demás, `<origen>/<ruta>`)
    clase: str
    bytes: int
    abrir: Callable[[], BinaryIO]                  # devuelve un archivo abierto en binario (el formato lo cierra)


# ------------------------------------------------------------------------------------------------------------------- nombres seguros (se validan al escribir Y al leer)
def ruta_segura(nombre: str) -> bool:
    """Sólo rutas relativas con `/`, sin `..`, sin unidad, sin `\\`, sin nombres reservados de Windows y con componentes razonables: nada que escape de la carpeta de destino."""
    if not isinstance(nombre, str) or not nombre or len(nombre) > 400 or "\\" in nombre or ":" in nombre or nombre.startswith("/"):
        return False
    partes = nombre.split("/")
    for p in partes:
        if p in (".", "..") or not _COMPONENTE.match(p) or p.endswith((" ", ".")):
            return False
        if p.split(".")[0].lower() in _RESERVADOS:
            return False
    return True


def _largo_registro(entrada: Entrada) -> int:
    return 1 + 4 + len(_cabecera_de_entrada(entrada)) + int(entrada.bytes) + 32


def _cabecera_de_entrada(entrada: Entrada) -> bytes:
    return json.dumps({"n": entrada.nombre, "c": entrada.clase, "b": int(entrada.bytes)}, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def largo_del_flujo(entradas: list[Entrada]) -> int:
    return sum(_largo_registro(e) for e in entradas) + 1 + 4


def numero_de_trozos(largo: int) -> int:
    return max(1, -(-int(largo) // cat.CHUNK))


def _json_canonico(datos: dict) -> bytes:
    return json.dumps(datos, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _aad_base(cabecera: bytes) -> bytes:
    return hashlib.sha256(b"avbak-aad" + cabecera).digest()


# ------------------------------------------------------------------------------------------------------------------- escribir
def _flujo_plano(entradas: list[Entrada]) -> Iterator[bytes]:
    """El flujo de registros en bloques. Lanza `ArchivoCambio` si una entrada no mide lo declarado."""
    for e in entradas:
        cabecera = _cabecera_de_entrada(e)
        yield _REG_ENTRADA + struct.pack(">I", len(cabecera)) + cabecera
        huella, leidos = hashlib.sha256(), 0
        f = e.abrir()
        try:
            while True:
                bloque = f.read(min(cat.CHUNK, e.bytes - leidos + 1))
                if not bloque:
                    break
                leidos += len(bloque)
                if leidos > e.bytes:
                    raise ArchivoCambio(f"{e.nombre}: creció mientras se respaldaba.")
                huella.update(bloque)
                yield bloque
        finally:
            f.close()
        if leidos != e.bytes:
            raise ArchivoCambio(f"{e.nombre}: midió {leidos} y se esperaban {e.bytes}.")
        yield huella.digest()
    yield _REG_FIN + struct.pack(">I", len(entradas))


def escribir(salida: BinaryIO, base: dict, entradas: list[Entrada], dek: bytes, claves: dict) -> dict:
    """
    Escribe el respaldo en `salida`. `base` trae los campos del manifiesto que decide el llamador (`respaldo_id`, `tipo`, `base_id`, `creado_en`, `producto`, `secuencia_global`, `nodo_id`, …);
    `claves` es lo que envuelve la DEK (`cripto.envolver`). Devuelve `{manifiesto, sha256, bytes}` del archivo completo.
    """
    largo = largo_del_flujo(entradas)
    prefijo = os.urandom(cripto.LARGO_PREFIJO)
    manifiesto = {**base, "formato": cat.FORMATO, "entradas": len(entradas), "bytes_claro": largo, "trozos": numero_de_trozos(largo), "prefijo": prefijo.hex(), "claves": claves}
    cuerpo = _json_canonico(manifiesto)
    if len(cuerpo) > _MAX_MANIFIESTO:
        raise ValueError("El manifiesto es demasiado grande.")
    cabecera = MAGIC + struct.pack(">HI", cat.FORMATO, len(cuerpo)) + cuerpo
    aad = _aad_base(cabecera)
    huella, total = hashlib.sha256(), 0

    def emitir(datos: bytes) -> None:
        nonlocal total
        salida.write(datos)
        huella.update(datos)
        total += len(datos)

    emitir(cabecera)
    contador, pendiente, escrito = 0, bytearray(), 0
    for bloque in _flujo_plano(entradas):
        pendiente += bloque
        while len(pendiente) > cat.CHUNK or (len(pendiente) == cat.CHUNK and escrito + cat.CHUNK < largo):
            trozo = bytes(pendiente[:cat.CHUNK])
            del pendiente[:cat.CHUNK]
            cifrado = cripto.cifrar_trozo(dek, prefijo, aad, contador, trozo, False)
            emitir(struct.pack(">I", len(cifrado)) + cifrado)
            contador += 1
            escrito += len(trozo)
    cifrado = cripto.cifrar_trozo(dek, prefijo, aad, contador, bytes(pendiente), True)
    emitir(struct.pack(">I", len(cifrado)) + cifrado)
    contador += 1
    escrito += len(pendiente)
    if escrito != largo or contador != manifiesto["trozos"]:
        raise ArchivoCambio("El flujo no mide lo calculado: un archivo cambió mientras se respaldaba.")
    return {"manifiesto": manifiesto, "sha256": huella.hexdigest(), "bytes": total}


# ------------------------------------------------------------------------------------------------------------------- leer
def leer_manifiesto(entrada: BinaryIO) -> tuple[dict, bytes]:
    """El manifiesto en claro y la cabecera exacta (para la AAD). No necesita ninguna clave. Un archivo que no tiene la forma se rechaza con motivo."""
    corte = entrada.read(10)
    if len(corte) < 10 or corte[:4] != MAGIC:
        raise RespaldoRechazado("formato_invalido")
    version, largo = struct.unpack(">HI", corte[4:10])
    if version != cat.FORMATO:
        raise RespaldoRechazado("version_no_soportada")
    if largo <= 0 or largo > _MAX_MANIFIESTO:
        raise RespaldoRechazado("formato_invalido")
    cuerpo = entrada.read(largo)
    if len(cuerpo) != largo:
        raise RespaldoRechazado("truncado")
    try:
        manifiesto = json.loads(cuerpo.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise RespaldoRechazado("formato_invalido") from None
    if not isinstance(manifiesto, dict) or manifiesto.get("formato") != cat.FORMATO or _json_canonico(manifiesto) != cuerpo:
        raise RespaldoRechazado("formato_invalido")
    for campo, tipo in (("respaldo_id", str), ("tipo", str), ("trozos", int), ("bytes_claro", int), ("prefijo", str), ("claves", dict), ("entradas", int), ("creado_en", int)):
        if not isinstance(manifiesto.get(campo), tipo) or isinstance(manifiesto.get(campo), bool):
            raise RespaldoRechazado("formato_invalido")
    if not _UUID.match(manifiesto["respaldo_id"]) or not (manifiesto.get("base_id") in (None, "") or _UUID.match(str(manifiesto.get("base_id")))) or len(str(manifiesto.get("nodo_id") or "")) > 36:
        raise RespaldoRechazado("formato_invalido")
    if manifiesto["tipo"] not in cat.TIPOS or manifiesto["trozos"] < 1 or manifiesto["bytes_claro"] < 5 or len(manifiesto["prefijo"]) != cripto.LARGO_PREFIJO * 2:
        raise RespaldoRechazado("formato_invalido")
    return manifiesto, MAGIC + corte[4:10] + cuerpo


def _trozos(entrada: BinaryIO, manifiesto: dict, cabecera: bytes, dek: bytes) -> Iterator[bytes]:
    aad, prefijo = _aad_base(cabecera), bytes.fromhex(manifiesto["prefijo"])
    total = manifiesto["trozos"]
    esperado = manifiesto["bytes_claro"]
    visto = 0
    for i in range(total):
        marco = entrada.read(4)
        if len(marco) != 4:
            raise RespaldoRechazado("truncado")
        (largo,) = struct.unpack(">I", marco)
        if largo < 16 or largo > cat.CHUNK + 16:
            raise RespaldoRechazado("integridad_alterada")
        cifrado = entrada.read(largo)
        if len(cifrado) != largo:
            raise RespaldoRechazado("truncado")
        try:
            claro = cripto.descifrar_trozo(dek, prefijo, aad, i, cifrado, i == total - 1)
        except cripto.TrozoAlterado:
            raise RespaldoRechazado("integridad_alterada") from None
        visto += len(claro)
        if visto > esperado:
            raise RespaldoRechazado("integridad_alterada")
        yield claro
    if entrada.read(1):
        raise RespaldoRechazado("integridad_alterada")
    if visto != esperado:
        raise RespaldoRechazado("truncado")


class _Lector:
    """Reparte el flujo descifrado en las lecturas que pide el analizador de registros."""

    def __init__(self, trozos: Iterator[bytes]):
        self.trozos, self.buf = trozos, bytearray()

    def leer(self, n: int) -> bytes:
        while len(self.buf) < n:
            try:
                self.buf += next(self.trozos)
            except StopIteration:
                raise RespaldoRechazado("truncado") from None
        salida = bytes(self.buf[:n])
        del self.buf[:n]
        return salida

    def fin(self) -> bool:
        return not self.buf and next(self.trozos, None) is None


def recorrer(entrada: BinaryIO, manifiesto: dict, cabecera: bytes, dek: bytes) -> Iterator[tuple[str, dict, Iterator[bytes]]]:
    """
    Recorre las entradas descifrando SOBRE LA MARCHA. Para cada una devuelve `(nombre, info, bloques)`: hay que consumir `bloques` completo antes de pedir la siguiente. Al terminar
    cada entrada comprueba su SHA-256 y, al final, que el número de entradas cuadre con el manifiesto y que no sobre nada.
    """
    lector = _Lector(_trozos(entrada, manifiesto, cabecera, dek))
    vistas, nombres = 0, set()
    while True:
        tipo = lector.leer(1)
        if tipo == _REG_FIN:
            (cuenta,) = struct.unpack(">I", lector.leer(4))
            if cuenta != vistas or cuenta != manifiesto["entradas"] or not lector.fin():
                raise RespaldoRechazado("integridad_alterada")
            return
        if tipo != _REG_ENTRADA:
            raise RespaldoRechazado("integridad_alterada")
        (largo,) = struct.unpack(">I", lector.leer(4))
        if largo > _MAX_CABECERA:
            raise RespaldoRechazado("integridad_alterada")
        try:
            info = json.loads(lector.leer(largo).decode("ascii"))
            nombre, clase, tam = info["n"], info["c"], int(info["b"])
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            raise RespaldoRechazado("integridad_alterada") from None
        if not ruta_segura(nombre) or clase not in cat.CLASES_DE_ARCHIVO or tam < 0 or nombre.lower() in nombres:
            raise RespaldoRechazado("integridad_alterada")
        nombres.add(nombre.lower())
        huella = hashlib.sha256()
        restante = tam

        def bloques(restante=restante, huella=huella) -> Iterator[bytes]:
            while restante > 0:
                n = min(cat.CHUNK, restante)
                trozo = lector.leer(n)
                huella.update(trozo)
                restante -= n
                yield trozo

        yield nombre, {"clase": clase, "bytes": tam}, (consumido := bloques())
        for _ in consumido:                               # si quien llama no consumió todo, se consume aquí (para poder comprobar la huella)
            pass
        if lector.leer(32) != huella.digest():
            raise RespaldoRechazado("integridad_alterada")
        vistas += 1


def abrir_dek(manifiesto: dict, clave_del_nodo: bytes | None, codigo_de_custodia: str | None) -> bytes:
    """
    La clave de datos del respaldo: con la clave de ESTE equipo si fue ella quien lo envolvió (mismo `kid`), o con el código de custodia de la institución. BR-102: en otro equipo, sin
    el código, no hay forma de abrirlo.
    """
    from .errores import ClaveNoDisponible

    claves = manifiesto.get("claves") or {}
    aad = b"avbak-dek|" + manifiesto["respaldo_id"].encode("ascii", "ignore")
    nodo = claves.get("nodo")
    if clave_del_nodo and isinstance(nodo, dict) and nodo.get("kid") == cripto.kid(clave_del_nodo):
        try:
            return cripto.desenvolver(clave_del_nodo, bytes.fromhex(nodo["nonce"]), bytes.fromhex(nodo["dek"]), aad + b"|nodo")
        except (cripto.ClaveIncorrecta, KeyError, ValueError):
            pass
    custodia = claves.get("custodia")
    if codigo_de_custodia and isinstance(custodia, dict):
        secreto = cripto.secreto_de_custodia(codigo_de_custodia)
        if secreto is not None:
            try:
                # el manifiesto no está autenticado antes de abrir la clave: sus parámetros de scrypt NO se obedecen, se exigen los del producto (si no, un archivo ajeno elegiría cuánta CPU gastar)
                if (custodia.get("n"), custodia.get("r"), custodia.get("p")) != (cripto.SCRYPT_N, cripto.SCRYPT_R, cripto.SCRYPT_P):
                    raise ValueError("parámetros de scrypt distintos de los del producto")
                kek = cripto.clave_de_custodia(secreto, bytes.fromhex(custodia["sal"]))
                return cripto.desenvolver(kek, bytes.fromhex(custodia["nonce"]), bytes.fromhex(custodia["dek"]), aad + b"|custodia")
            except (cripto.ClaveIncorrecta, KeyError, ValueError, TypeError, AttributeError):
                pass
    raise ClaveNoDisponible()


def envolver_dek(respaldo_id: str, dek: bytes, clave_del_nodo: bytes, kek_de_custodia: tuple[bytes, bytes] | None) -> dict:
    """`{nodo: …, custodia: … | None}` para el manifiesto. `kek_de_custodia` = (clave derivada, sal); None si la institución todavía no tiene código (el respaldo sólo abre en este equipo)."""
    aad = b"avbak-dek|" + respaldo_id.encode("ascii", "ignore")
    nonce, envuelta = cripto.envolver(clave_del_nodo, dek, aad + b"|nodo")
    claves: dict = {"nodo": {"kid": cripto.kid(clave_del_nodo), "nonce": nonce.hex(), "dek": envuelta.hex()}}
    if kek_de_custodia is not None:
        kek, sal = kek_de_custodia
        nonce, envuelta = cripto.envolver(kek, dek, aad + b"|custodia")
        claves["custodia"] = {"sal": sal.hex(), "n": cripto.SCRYPT_N, "r": cripto.SCRYPT_R, "p": cripto.SCRYPT_P, "nonce": nonce.hex(), "dek": envuelta.hex()}
    return claves
