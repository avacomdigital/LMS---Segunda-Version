"""
El archivo de una exportación: su nombre (seguro para cualquier sistema de archivos, FAT32 y exFAT incluidos, y sin ningún dato de persona), su huella y qué destinos permite
la política del nodo. El cliente (OPS) vuelve a sanear el nombre antes de escribir: aquí se propone, allí se comprueba.
Este archivo no importa Django.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from . import catalogos as cat

PROHIBIDOS = frozenset('\\/:*?"<>|')
RESERVADOS = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})


def _unidades_utf16(texto: str) -> int:
    """Windows mide los nombres en unidades UTF-16: un carácter fuera del plano básico (un emoji) ocupa dos."""
    return len(texto.encode("utf-16-le")) // 2


def _recortar(texto: str, maximo: int) -> str:
    salida, usadas = [], 0
    for ch in texto:
        n = 2 if ord(ch) > 0xFFFF else 1
        if usadas + n > maximo:
            break
        salida.append(ch)
        usadas += n
    return "".join(salida)


def _limpio(texto: str) -> str:
    t = unicodedata.normalize("NFC", texto or "")
    t = "".join("-" if (c in PROHIBIDOS or ord(c) < 32 or ord(c) == 127) else c for c in t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[ -]*-[ -]*", "-", t)                          # «reporte: "8A" <x>» → «reporte-8A-x»: una raya sola entre palabras, sin espacios alrededor
    return t.strip(" .-")


def sanear(propuesto: str, extension: str = "", respaldo: str = "reporte", maximo: int = cat.MAX_NOMBRE_DE_ARCHIVO) -> str:
    """`base.ext` seguro: sin `\\ / : * ? " < > |` ni controles, sin espacios ni puntos al final, sin nombres reservados de Windows, determinista y de a lo sumo `maximo`
    unidades UTF-16 en total (se recorta la base, nunca la extensión). Las tildes y la ñ se conservan."""
    ext = _limpio(extension).lstrip(".").lower()
    sufijo = f".{ext}" if ext else ""
    base = _limpio(propuesto) or _limpio(respaldo) or "reporte"
    if base.lower() in RESERVADOS:
        base = f"reporte-{base}"
    base = _recortar(base, max(1, maximo - _unidades_utf16(sufijo))).strip(" .-") or "reporte"
    return base + sufijo


def nombre_del_reporte(tipo: str, sujeto: str, corte_local: datetime, extension: str) -> str:
    """`reporte-grupo-8A-2026-10-15-1042.xlsx`: el tipo, el sujeto (un código de grupo o un periodo, NUNCA el nombre de una persona), el corte en hora local del nodo y la
    extensión. Determinista: el mismo reporte con el mismo corte da siempre el mismo nombre."""
    sello = corte_local.strftime("%Y-%m-%d-%H%M")
    return sanear(f"reporte-{tipo}-{sujeto}-{sello}" if sujeto else f"reporte-{tipo}-{sello}", extension)


def huella(contenido: bytes) -> str:
    """SHA-256 en hexadecimal minúsculas de los bytes EXACTOS del archivo."""
    return hashlib.sha256(contenido).hexdigest()


def destino_permitido(destino: str, permitir_extraibles: bool) -> bool:
    """La política del nodo: por defecto se puede guardar en todas partes; el administrador puede cerrar los medios extraíbles."""
    if destino not in cat.DESTINOS:
        return False
    return permitir_extraibles or destino != cat.EXTRAIBLE
