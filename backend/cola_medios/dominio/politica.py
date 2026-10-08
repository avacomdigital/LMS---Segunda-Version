"""
Cuándo y a quién sacar de la caché cuando no cabe lo nuevo: el que lleva más tiempo sin usarse, sin tocar lo que alguien está leyendo ni lo que se
usó hace muy poco.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidato:
    id: str
    bytes: int
    ultimo_uso_ms: int
    en_uso: bool = False


def elegir_expulsiones(candidatos: list[Candidato], liberar: int, ahora_ms: int, proteger_ms: int) -> list[str]:
    """Ids a expulsar, del menos reciente al más, hasta liberar `liberar` bytes. Devuelve lo que se pueda aunque no alcance."""
    elegidos: list[str] = []
    liberado = 0
    for c in sorted(candidatos, key=lambda x: x.ultimo_uso_ms):
        if liberado >= liberar:
            break
        if c.en_uso or ahora_ms - c.ultimo_uso_ms < proteger_ms:
            continue
        elegidos.append(c.id)
        liberado += c.bytes
    return elegidos
