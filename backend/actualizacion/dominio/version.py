"""Versiones del producto y de los módulos: `mayor.menor.parche` (como `installer/version.json`). Puro."""
from __future__ import annotations

import re

_VERSION = re.compile(r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})$")
_NOMBRE_MODULO = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_NOMBRE_MIGRACION = re.compile(r"^\d{4}_[a-z0-9_]{1,80}$")


def analizar(texto) -> tuple[int, int, int] | None:
    """`(mayor, menor, parche)` o None si no es una versión."""
    m = _VERSION.match(str(texto or "").strip())
    return None if m is None else (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def es_version(texto) -> bool:
    return analizar(texto) is not None


def comparar(a: str, b: str) -> int:
    """-1, 0 o 1. Lo que no es una versión cuenta como la más baja de todas."""
    va, vb = analizar(a) or (-1, -1, -1), analizar(b) or (-1, -1, -1)
    return (va > vb) - (va < vb)


def es_nombre_de_modulo(texto) -> bool:
    return bool(_NOMBRE_MODULO.match(str(texto or "")))


def es_nombre_de_migracion(texto) -> bool:
    return bool(_NOMBRE_MIGRACION.match(str(texto or "")))


def numero_de_migracion(nombre: str) -> int:
    """`0004_corte_cola_unica` → 4. La versión de datos de un módulo es el número de su última migración (D-3)."""
    return int(str(nombre)[:4]) if es_nombre_de_migracion(nombre) else 0
