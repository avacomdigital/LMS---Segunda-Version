"""
Cupo (P-08, BR-027, BR-063): sólo se aplica al CREAR. Nunca a lo que ya existe, a una readmisión ni al latido de un equipo ya registrado: «bloquear lo nuevo, nunca lo existente».

  · Equipos: un equipo NUEVO (la primera vez que se presenta) cuenta contra el límite de equipos de la licencia.
  · Usuarios: una identidad NUEVA (alta, importación de padrón, autorregistro) cuenta contra el límite de usuarios.
  · Concurrencia: 50 en operación normal y 100 en pico (BR-063) salen de la licencia; sin licencia, de los valores de `settings` que ya existen.

Hasta que la identidad de dispositivo sea criptográfica (Fase 5) la huella de un equipo la DECLARA el cliente: el cupo de equipos es blando. La documentación lo dice.
"""
from __future__ import annotations

from dataclasses import dataclass

from .licencia import ILIMITADO

TIPO_EQUIPOS, TIPO_USUARIOS = "equipos", "usuarios"
TIPOS = (TIPO_EQUIPOS, TIPO_USUARIOS)


@dataclass(frozen=True)
class Consumo:
    equipos: int
    usuarios: int


def admite(limite: int, en_uso: int, adicional: int = 1) -> bool:
    """¿Cabe `adicional` más? `ILIMITADO` (0xFFFFFFFF) no tiene tope; un límite de 0 no admite ninguno nuevo."""
    return limite == ILIMITADO or int(en_uso) + int(adicional) <= int(limite)


def porcentaje(en_uso: int, limite: int) -> int | None:
    """Cuánto del límite está en uso (0–100, o más si ya lo superó); None si no hay tope."""
    if limite == ILIMITADO:
        return None
    if limite <= 0:
        return 100 if en_uso > 0 else 0
    return int(round(100 * int(en_uso) / int(limite)))


def concurrencia(licencia_normal: int | None, licencia_pico: int | None, normal_por_defecto: int, pico_por_defecto: int) -> tuple[int, int]:
    """`(normal, pico)` de BR-063: los de la licencia si hay (y no son «sin tope»), si no los de `settings`. Siempre `normal <= pico`."""
    normal = normal_por_defecto if licencia_normal in (None, ILIMITADO) else int(licencia_normal)
    pico = pico_por_defecto if licencia_pico in (None, ILIMITADO) else int(licencia_pico)
    return min(normal, pico), max(normal, pico)
