r"""
Busca la llave K del paquete (la de custodia) dentro de una carpeta o de un archivo: en bruto (32 bytes), en hexadecimal (minusculas y mayusculas) y en base64. Lo corre Build-Installer.ps1 sobre
dist\staging despues de cifrar: K no puede aparecer en ningun archivo que viaje.

    python Buscar-Llave.py --clave-archivo <k.hex> <carpeta-o-archivo> [...]

Salida: 0 si no aparece en ninguno · 1 si aparece (imprime donde) · 3 uso o datos invalidos. NO imprime K.
Un .exe de Inno Setup va comprimido: buscar K ahi dentro solo prueba algo si K estuviera en el instalador sin comprimir; la prueba que cuenta es la del contenido (dist\staging).
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

BLOQUE = 8 << 20


def patrones(k: bytes) -> list[tuple[str, bytes]]:
    h = k.hex()
    return [
        ("bytes", k),
        ("hex", h.encode("ascii")),
        ("HEX", h.upper().encode("ascii")),
        ("base64", base64.b64encode(k)),
        ("base64url", base64.urlsafe_b64encode(k)),
        ("utf-16 hex", h.encode("utf-16-le")),
    ]


def buscar_en(ruta: Path, pats: list[tuple[str, bytes]]) -> list[str]:
    solape = max(len(p) for _, p in pats)
    hallados: set[str] = set()
    with open(ruta, "rb") as f:
        previo = b""
        while True:
            bloque = f.read(BLOQUE)
            if not bloque:
                break
            datos = previo + bloque
            for nombre, p in pats:
                if p in datos:
                    hallados.add(nombre)
            previo = datos[-(solape - 1):]
    return sorted(hallados)


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--clave-archivo", required=True)
    a.add_argument("rutas", nargs="+")
    n = a.parse_args()
    try:
        k = bytes.fromhex(Path(n.clave_archivo).read_text(encoding="ascii").strip())
    except (OSError, ValueError) as e:
        print(f"No se pudo leer la llave de custodia: {e}", file=sys.stderr)
        return 3
    if len(k) != 32:
        print("La llave de custodia no mide 32 bytes.", file=sys.stderr)
        return 3
    pats = patrones(k)
    archivos = 0
    bytes_total = 0
    hits = 0
    for raiz in n.rutas:
        r = Path(raiz)
        lista = [r] if r.is_file() else [Path(c) / x for c, _, xs in os.walk(r) for x in xs]
        for ruta in lista:
            try:
                tam = ruta.stat().st_size
                encontrados = buscar_en(ruta, pats)
            except OSError as e:
                print(f"No se pudo leer {ruta}: {e}", file=sys.stderr)
                return 3
            archivos += 1
            bytes_total += tam
            if encontrados:
                hits += 1
                print(f"LLAVE ENCONTRADA ({', '.join(encontrados)}) en {ruta}")
    print(f"archivos_revisados={archivos} bytes={bytes_total} coincidencias={hits}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
