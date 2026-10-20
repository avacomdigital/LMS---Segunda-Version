"""
Las llaves de emisión: generar el par Ed25519, guardar la PRIVADA cifrada con una frase de paso (`<kid>.avkey`) y publicar la PÚBLICA (`<kid>.pub`).

  · La privada se cifra con AES-256-GCM; la clave sale de la frase de paso con scrypt (N=2^15, r=8, p=1) y una sal propia. El nombre de la llave y su pública van como dato
    asociado: cambiar el `kid` o la pública del archivo hace que ya no abra.
  · La frase de paso mide al menos 16 caracteres. Nunca se guarda ni se escribe en ningún registro.
  · La pública es un texto de cinco líneas (`kid`, `publica`, `sha256`, `creada`): es lo que se entrega al equipo de desarrollo para `backend/licenciamiento/claves/`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .dominio_nodo import firma

FORMATO = "avacom-avkey"
VERSION = 1
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
MIN_FRASE = 16
_KID = re.compile(r"^[a-z0-9._-]{1,32}$")          # 32 es lo que acepta el cargador de llaves públicas del nodo (infraestructura/claves.py)
ENCABEZADO_PUBLICA = "avacom-llave-publica"
ESTADOS_QUE_VALEN = ("vigente", "siguiente")         # los mismos que acepta el nodo; `retirada` se ignora


class ErrorDeLlave(ValueError):
    """Algo no está bien con una llave (nombre, frase de paso, archivo dañado). El mensaje se le muestra tal cual a quien opera."""


@dataclass(frozen=True)
class LlaveAbierta:
    kid: str
    privada: bytes
    publica: bytes


def kid_valido(kid: object) -> str:
    if not isinstance(kid, str) or not _KID.match(kid):
        raise ErrorDeLlave("El nombre de la llave (kid) sólo puede llevar minúsculas, números, punto, guion y guion bajo (hasta 32 caracteres), por ejemplo «prod-2026-1».")
    return kid


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def _derivar(frase: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=sal, length=32, n=n, r=r, p=p).derive(frase.encode("utf-8"))


def _dato_asociado(kid: str, publica_hex: str) -> bytes:
    return f"{FORMATO}|{VERSION}|{kid}|{publica_hex}".encode("utf-8")


def texto_publica(kid: str, publica: bytes, creada: str) -> str:
    return "\n".join([ENCABEZADO_PUBLICA, f"kid={kid}", f"publica={publica.hex()}", f"sha256={hashlib.sha256(publica).hexdigest()}", f"creada={creada}", ""])


def huella_de_publica(publica: bytes) -> str:
    return hashlib.sha256(publica).hexdigest()


def entrada_para_el_nodo(kid: str, publica: bytes, estado: str = "vigente") -> str:
    """El archivo que se pega en `backend/licenciamiento/claves/produccion.json` (o se une a él): el MISMO formato que lee el nodo. Sólo lleva la pública."""
    return json.dumps({"version": 1, "claves": [{"kid": kid_valido(kid), "publica": publica.hex(), "estado": estado}]}, indent=2) + "\n"


def leer_claves_del_nodo(texto: str) -> dict[str, bytes]:
    """`{kid: pública}` de un archivo en el formato de `produccion.json` del nodo. Una entrada mal formada o `retirada` se ignora, como hace el nodo."""
    try:
        datos = json.loads(texto)
    except ValueError as error:
        raise ErrorDeLlave("El archivo de llaves públicas no es un JSON válido.") from error
    salida: dict[str, bytes] = {}
    for entrada in datos.get("claves", []) if isinstance(datos, dict) else []:
        try:
            kid, estado, publica = str(entrada["kid"]), str(entrada.get("estado", "vigente")), bytes.fromhex(str(entrada["publica"]))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if _KID.match(kid) and len(publica) == 32 and estado in ESTADOS_QUE_VALEN:
            salida[kid] = publica
    return salida


def generar(kid: str, frase: str, creada: str, azar=secrets.token_bytes) -> tuple[bytes, str, bytes]:
    """`(contenido del .avkey, texto del .pub, pública)`. La privada nunca sale de aquí en claro."""
    kid_valido(kid)
    if not isinstance(frase, str) or len(frase) < MIN_FRASE:
        raise ErrorDeLlave(f"La frase de paso debe tener al menos {MIN_FRASE} caracteres.")
    privada, publica = firma.par_nuevo()
    sal, nonce = azar(16), azar(12)
    cifrado = AESGCM(_derivar(frase, sal, SCRYPT_N, SCRYPT_R, SCRYPT_P)).encrypt(nonce, privada, _dato_asociado(kid, publica.hex()))
    documento = {
        "formato": FORMATO, "version": VERSION, "kid": kid, "publica": publica.hex(), "creada": creada,
        "kdf": {"nombre": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "sal": _b64(sal)},
        "cifrado": {"nombre": "aes-256-gcm", "nonce": _b64(nonce), "datos": _b64(cifrado)},
    }
    return (json.dumps(documento, indent=2, sort_keys=True) + "\n").encode("utf-8"), texto_publica(kid, publica, creada), publica


def abrir(avkey: bytes, frase: str) -> LlaveAbierta:
    """Abre un `.avkey`. Una frase equivocada, un archivo alterado o uno que no es de AVACOM dan `ErrorDeLlave`."""
    try:
        d = json.loads(bytes(avkey).decode("utf-8"))
        if d["formato"] != FORMATO or d["version"] != VERSION:
            raise ErrorDeLlave("Este archivo no es una llave privada de AVACOM de esta versión.")
        kid, publica_hex = kid_valido(d["kid"]), str(d["publica"])
        kdf, cif = d["kdf"], d["cifrado"]
        if kdf["nombre"] != "scrypt" or cif["nombre"] != "aes-256-gcm":
            raise ErrorDeLlave("La llave usa un cifrado que esta herramienta no entiende.")
        sal, nonce, datos = base64.b64decode(kdf["sal"], validate=True), base64.b64decode(cif["nonce"], validate=True), base64.b64decode(cif["datos"], validate=True)
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
    except ErrorDeLlave:
        raise
    except Exception as error:     # noqa: BLE001 — cualquier archivo mal formado
        raise ErrorDeLlave("El archivo de la llave está dañado o no es una llave de AVACOM.") from error
    if not 2 ** 14 <= n <= 2 ** 20 or r < 1 or p < 1:
        raise ErrorDeLlave("El archivo de la llave trae parámetros fuera de rango.")
    try:
        privada = AESGCM(_derivar(frase or "", sal, n, r, p)).decrypt(nonce, datos, _dato_asociado(kid, publica_hex))
    except InvalidTag:
        raise ErrorDeLlave("La frase de paso no abre esta llave (o el archivo fue alterado).") from None
    if len(privada) != 32 or firma.publica_de(privada).hex() != publica_hex:
        raise ErrorDeLlave("El archivo de la llave está dañado: la pública no corresponde a la privada.")
    return LlaveAbierta(kid, privada, bytes.fromhex(publica_hex))


def leer_publica(texto: str) -> tuple[str, bytes]:
    """`(kid, pública)` de un `.pub`. Comprueba el SHA-256 si el archivo lo trae."""
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    if not lineas or lineas[0] != ENCABEZADO_PUBLICA:
        raise ErrorDeLlave("Este archivo no es una llave pública de AVACOM.")
    campos = dict(linea.split("=", 1) for linea in lineas[1:] if "=" in linea)
    try:
        kid = kid_valido(campos["kid"])
        publica = bytes.fromhex(campos["publica"])
    except (KeyError, ValueError) as error:
        raise ErrorDeLlave("La llave pública está incompleta o dañada.") from error
    if len(publica) != 32:
        raise ErrorDeLlave("La llave pública no mide 32 bytes.")
    if "sha256" in campos and campos["sha256"].lower() != huella_de_publica(publica):
        raise ErrorDeLlave("La huella de la llave pública no coincide: el archivo fue alterado.")
    return kid, publica
