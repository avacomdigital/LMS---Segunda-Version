"""
Cifra el codigo propio del backend en `codigo.avpkg` (segunda proteccion, S2). Lo corre Build-Installer.ps1 sobre la COPIA del backend que va al paquete (dist\\staging\\Backend), con el Python
EMBEBIDO del paquete (para que la magia del bytecode sea exactamente la del runtime que lo va a cargar), nunca sobre el repositorio.

    python Cifrar-Backend.py --backend <carpeta> --escribir-clave <archivo.hex> [--clave-hex <64 hex>] [--eliminar-fuentes] [--exigir-cero-py]

  · Cada `.py` se compila a bytecode (`marshal`) y se cifra con AES-256-GCM; la llave de cada modulo sale de la llave de paquete `K` con HKDF-SHA256 y la ruta del modulo (un modulo no se puede
    cambiar de sitio dentro del paquete: la ruta es dato asociado). El indice (los nombres de los modulos) tambien va cifrado. Formato y lector: `installer/src/payload/avacom_boot.py`.
  · `K` es de 32 bytes aleatorios por compilacion (o la que se pase con --clave-hex, para repetir un paquete). NO se escribe en la carpeta del backend ni se imprime: va al archivo de
    --escribir-clave, que debe estar FUERA de la carpeta del backend (lo custodia quien emite los sellos; ver 09-segunda-proteccion.md). Se imprime solo su `kid`.
  · `--eliminar-fuentes` borra los `.py` de la carpeta una vez escrito el paquete: lo que queda son datos (JSON) y `codigo.avpkg`. Con `--exigir-cero-py` falla si queda alguno.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "payload"))
import avacom_boot as b  # noqa: E402
import importlib.util  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
import marshal  # noqa: E402

IGNORAR = {"__pycache__", ".venv", "logs", ".git", "node_modules"}


def modulos_de(raiz: Path):
    """`(nombre del modulo, ruta relativa con /, ¿paquete?, ruta absoluta)` de cada .py de la carpeta."""
    for ruta in sorted(raiz.rglob("*.py")):
        if any(parte in IGNORAR for parte in ruta.relative_to(raiz).parts):
            continue
        rel = ruta.relative_to(raiz).as_posix()
        partes = rel[:-3].split("/")
        es_pkg = partes[-1] == "__init__"
        if es_pkg:
            partes = partes[:-1]
        if not partes:
            continue                       # un __init__.py suelto en la raiz no es un modulo
        yield ".".join(partes), rel, es_pkg, ruta


def construir(raiz: Path, k: bytes) -> tuple[bytes, int]:
    """Los bytes de `codigo.avpkg` y cuantos modulos lleva."""
    indice: dict[str, dict] = {}
    blobs = bytearray()
    for nombre, rel, es_pkg, ruta in modulos_de(raiz):
        codigo = compile(ruta.read_bytes(), rel, "exec", dont_inherit=True, optimize=0)
        nonce = secrets.token_bytes(12)
        cifrado = AESGCM(b._derivar(k, b"modulo|" + rel.encode("utf-8"))).encrypt(nonce, marshal.dumps(codigo), rel.encode("utf-8"))
        indice[nombre] = {"r": rel, "p": es_pkg, "o": len(blobs), "l": len(cifrado), "n": nonce.hex()}
        blobs += cifrado
    if not indice:
        raise SystemExit("La carpeta no tiene ningun .py que cifrar.")
    magia = importlib.util.MAGIC_NUMBER[:4]
    nonce_indice = secrets.token_bytes(12)
    # el largo del indice cifrado = largo del JSON + 16 (la etiqueta de GCM): se calcula antes de escribir la cabecera, que es dato asociado
    crudo = json.dumps({"modulos": indice, "datos_sha256": hashlib.sha256(bytes(blobs)).hexdigest()}, separators=(",", ":")).encode("utf-8")
    cabecera = (b.MAGIC + b.VERSION.to_bytes(2, "big") + bytes([b.ALGORITMO_AES256GCM]) + b.kid_de(k) + magia + bytes([sys.version_info[0], sys.version_info[1]])
                + nonce_indice + (len(crudo) + 16).to_bytes(4, "big"))
    cifrado_indice = AESGCM(b._derivar(k, b"indice")).encrypt(nonce_indice, crudo, cabecera)
    return cabecera + cifrado_indice + bytes(blobs), len(indice)


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--backend", required=True)
    a.add_argument("--escribir-clave", required=True, help="Archivo (FUERA de la carpeta del backend) donde se guarda K en hexadecimal")
    a.add_argument("--clave-hex")
    a.add_argument("--eliminar-fuentes", action="store_true")
    a.add_argument("--exigir-cero-py", action="store_true")
    n = a.parse_args()
    raiz = Path(n.backend).resolve()
    destino_clave = Path(n.escribir_clave).resolve()
    if not raiz.is_dir():
        raise SystemExit(f"No existe la carpeta {raiz}.")
    if raiz in destino_clave.parents:
        raise SystemExit("La llave K no puede guardarse dentro de la carpeta del backend: viajaria en el instalador.")
    k = bytes.fromhex(n.clave_hex) if n.clave_hex else secrets.token_bytes(32)
    if len(k) != 32:
        raise SystemExit("La llave K mide 32 bytes (64 hexadecimales).")
    datos, cuantos = construir(raiz, k)
    (raiz / b.NOMBRE_DEL_PAQUETE).write_bytes(datos)
    destino_clave.parent.mkdir(parents=True, exist_ok=True)
    with open(destino_clave, "w", encoding="ascii", newline="\n") as f:
        f.write(k.hex() + "\n")
    quitados = 0
    if n.eliminar_fuentes:
        for _, _, _, ruta in modulos_de(raiz):
            ruta.unlink()
            quitados += 1
        for carpeta in sorted((p for p in raiz.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if carpeta.name in IGNORAR:
                continue
            try:
                carpeta.rmdir()                  # solo las que quedaron vacias
            except OSError:
                pass
    restantes = [p for p in raiz.rglob("*.py") if not any(x in IGNORAR for x in p.relative_to(raiz).parts)]
    if n.exigir_cero_py and restantes:
        raise SystemExit(f"Quedaron {len(restantes)} .py en la carpeta (p. ej. {restantes[0].relative_to(raiz)}).")
    print(f"modulos={cuantos} paquete_bytes={len(datos)} kid={b.kid_de(k).hex()} fuentes_quitadas={quitados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
