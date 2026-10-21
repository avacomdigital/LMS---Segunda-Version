"""
Las ANCLAS de la secuencia y del reloj (P-12, P-13): lo que se guarda FUERA de la base para que restaurar una copia vieja no reutilice una secuencia (INV-002) ni rebobine el reloj.

  · Secuencia: `AUTOINCREMENT` se reinicia si alguien reemplaza el archivo de la base por una copia vieja. Por eso la secuencia máxima emitida se ancla fuera y, al arrancar, si
    `max(secuencia)` de la base es MENOR que el ancla —o no hay ancla pero la base trae eventos: un equipo nuevo con un respaldo restaurado— se detecta una RESTAURACIÓN y el
    contador salta a `ancla + margen`.
  · Reloj: `ahora = max(reloj del sistema, marca alta)`; la marca alta es monótona y también se ancla fuera. Un retroceso por encima de la tolerancia se declara; un salto hacia
    adelante no cambia nada por sí solo (P-13).

Puro: ni lee archivos ni relojes; recibe los valores y decide. La lógica fina del reloj (fecha adelantada, piso monótono) es de MOD-018 y se unifica en la Fase 6.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import catalogos as cat


@dataclass(frozen=True)
class Ancla:
    secuencia: int = 0                # la mayor secuencia emitida que se llegó a anclar
    marca_alta: int = 0               # el instante más alto que el nodo vio
    escrita_en: int = 0               # cuándo se escribió el ancla (reloj del nodo, ms)


@dataclass(frozen=True)
class ArranqueDeSecuencia:
    restauracion: bool                # la base trae MENOS que el ancla (o no hay ancla y sí hay eventos)
    sin_ancla: bool                   # no había ancla
    contador_minimo: int              # a dónde debe saltar el contador (0 = no hace falta)
    max_en_base: int
    ancla: int


def al_arrancar(max_en_base: int, ancla: int | None, margen: int = cat.MARGEN_SECUENCIA) -> ArranqueDeSecuencia:
    """
    Qué hacer con el contador al arrancar (P-12). Se compara lo que la base tiene con lo que el ancla recuerda:
      · ancla ≤ max_en_base → lo normal (el ancla se refresca por lotes, así que puede ir por detrás): nada que hacer.
      · max_en_base < ancla → RESTAURACIÓN: el contador salta a `ancla + margen` (el margen cubre lo que se pudo emitir desde el último refresco del ancla).
      · sin ancla y la base trae eventos → equipo nuevo con un respaldo restaurado: no hay con qué comparar, así que también salta, a `max_en_base + margen`.
      · sin ancla y la base vacía → instalación nueva: nada.
    """
    max_en_base = int(max_en_base or 0)
    if ancla is None:
        if max_en_base > 0:
            return ArranqueDeSecuencia(True, True, max_en_base + int(margen), max_en_base, 0)
        return ArranqueDeSecuencia(False, True, 0, 0, 0)
    ancla = int(ancla)
    if max_en_base < ancla:
        return ArranqueDeSecuencia(True, False, ancla + int(margen), max_en_base, ancla)
    return ArranqueDeSecuencia(False, False, 0, max_en_base, ancla)


def hay_que_refrescar(ancla: Ancla, secuencia_emitida: int, ahora: int, *, cada_ms: int = cat.ANCLA_CADA_MS, cada_eventos: int = cat.ANCLA_CADA_EVENTOS) -> bool:
    """El ancla se refresca por lotes: sólo si hay algo nuevo que anclar (una secuencia mayor), y entonces cuando pasaron `cada_ms` desde la última escritura o se emitieron
    `cada_eventos` desde entonces, lo que llegue primero. Nunca se escribe un valor menor (la secuencia no baja)."""
    if int(secuencia_emitida) <= int(ancla.secuencia):
        return False
    return int(secuencia_emitida) - int(ancla.secuencia) >= int(cada_eventos) or int(ahora) - int(ancla.escrita_en) >= int(cada_ms)


def ancla_siguiente(ancla: Ancla, secuencia_emitida: int, marca_alta: int, ahora: int) -> Ancla:
    """La que se escribe: nunca baja ninguno de los dos valores."""
    return Ancla(max(int(ancla.secuencia), int(secuencia_emitida)), max(int(ancla.marca_alta), int(marca_alta)), int(ahora))


# -------------------------------------------------------------------------------------------------------------------------------- reloj (P-13)

@dataclass(frozen=True)
class LecturaDeReloj:
    ahora: int                        # el instante que vale: nunca menor que la marca alta
    reloj: int                        # lo que dijo el reloj del sistema
    marca_alta: int
    atras_ms: int                     # cuánto por debajo de la marca está el reloj (0 si no)
    retroceso: bool                   # más que la tolerancia
    restringe: bool                   # el retroceso supera el umbral que restringe el nodo


def leer_reloj(reloj_ms: int, marca_alta_ms: int, *, tolerancia_ms: int = cat.TOLERANCIA_RETROCESO_MS, restringe_ms: int = cat.RETROCESO_RESTRINGE_MS) -> LecturaDeReloj:
    atras = max(0, int(marca_alta_ms) - int(reloj_ms))
    return LecturaDeReloj(max(int(reloj_ms), int(marca_alta_ms)), int(reloj_ms), int(marca_alta_ms), atras, atras > int(tolerancia_ms), atras > int(restringe_ms))


def marca_siguiente(marca_alta_ms: int, ahora_ms: int) -> int:
    """La marca alta nueva: monótona (jamás baja)."""
    return max(int(marca_alta_ms), int(ahora_ms))
