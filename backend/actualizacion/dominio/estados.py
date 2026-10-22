"""
La máquina de estados del paquete (P-05, H del Maestro), como función PURA sobre el historial de sólo inserción: no se guarda un «estado actual»; se DERIVA de las filas.

    (sin filas) ─recibido→ recibido ─verificado→ verificado ─programado→ programado ─aplicando→ aplicando ─aplicado→ aplicado ─archivado→ archivado
                                     │ incompatible ↔ verificado        │ desprogramado / ventana_vencida → verificado        │ revertido → revertido
                                     └──────────── aplicando ───────────┘ bloqueada (no cambia)                               │ reversion_fallida → reversion_fallida
                                                                                                                               └ aplazada → el estado anterior
    aplicado ─aplicando (revertir, ≤ 14 días)→ aplicando ─revertido→ revertido · reversion_fallida ─aplicando→ aplicando (se reintenta)

Los estados del Maestro son seis; `programado`, `aplicando` y `reversion_fallida` son extensiones (§catálogos). `rechazado` no es un estado: es una fila sin paquete.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from . import catalogos as cat
from .errores import EstadoInvalido, FueraDePlazoReversion


class Fila(Protocol):
    tipo: str
    en: int
    detalle: Any


# (estado actual, tipo de fila) → estado nuevo. `None` = sin filas todavía. `H_APLAZADA` vuelve al estado ANTERIOR a `aplicando` (lo resuelve `transicion`).
TRANSICIONES: dict[tuple[str | None, str], str] = {
    (None, cat.H_RECIBIDO): cat.RECIBIDO,
    (cat.RECIBIDO, cat.H_VERIFICADO): cat.VERIFICADO,
    (cat.RECIBIDO, cat.H_INCOMPATIBLE): cat.INCOMPATIBLE,
    (cat.VERIFICADO, cat.H_INCOMPATIBLE): cat.INCOMPATIBLE,
    (cat.INCOMPATIBLE, cat.H_VERIFICADO): cat.VERIFICADO,
    (cat.VERIFICADO, cat.H_PROGRAMADO): cat.PROGRAMADO,
    (cat.PROGRAMADO, cat.H_PROGRAMADO): cat.PROGRAMADO,
    (cat.PROGRAMADO, cat.H_DESPROGRAMADO): cat.VERIFICADO,
    (cat.PROGRAMADO, cat.H_VENTANA_VENCIDA): cat.VERIFICADO,
    (cat.VERIFICADO, cat.H_BLOQUEADA): cat.VERIFICADO,
    (cat.PROGRAMADO, cat.H_BLOQUEADA): cat.PROGRAMADO,
    (cat.INCOMPATIBLE, cat.H_BLOQUEADA): cat.INCOMPATIBLE,
    (cat.VERIFICADO, cat.H_APLICANDO): cat.APLICANDO,
    (cat.PROGRAMADO, cat.H_APLICANDO): cat.APLICANDO,
    (cat.APLICANDO, cat.H_APLICADO): cat.APLICADO,
    (cat.APLICANDO, cat.H_REVERTIDO): cat.REVERTIDO,
    (cat.APLICANDO, cat.H_REVERSION_FALLIDA): cat.REVERSION_FALLIDA,
    (cat.APLICADO, cat.H_APLICANDO): cat.APLICANDO,
    (cat.APLICADO, cat.H_ARCHIVADO): cat.ARCHIVADO,
    (cat.APLICADO, cat.H_BLOQUEADA): cat.APLICADO,                    # una reversión pedida con una clase abierta
    (cat.REVERSION_FALLIDA, cat.H_APLICANDO): cat.APLICANDO,
    (cat.REVERSION_FALLIDA, cat.H_BLOQUEADA): cat.REVERSION_FALLIDA,
}


def transicion(estado: str | None, previo: str | None, tipo: str) -> str:
    """El estado tras una fila de ese tipo, o `EstadoInvalido`. `previo` es el estado anterior a `aplicando` (a él vuelve una aplicación aplazada)."""
    if tipo == cat.H_APLAZADA:
        if estado != cat.APLICANDO:
            raise EstadoInvalido(f"Un paquete «{estado}» no se puede aplazar: no se estaba aplicando.", estado=estado, tipo=tipo)
        return previo if previo in (cat.VERIFICADO, cat.PROGRAMADO) else cat.VERIFICADO
    nuevo = TRANSICIONES.get((estado, tipo))
    if nuevo is None:
        raise EstadoInvalido(f"Un paquete «{estado or 'nuevo'}» no admite «{tipo}».", estado=estado, tipo=tipo)
    return nuevo


@dataclass(frozen=True)
class Derivado:
    """Lo que las filas dicen de un paquete en un instante."""

    estado: str | None
    previo: str | None                 # el estado antes de `aplicando` (a él se vuelve si el Host aplaza)
    aplicado_en: int | None            # la última aplicación exitosa que sigue vigente (None si se revirtió o se archivó)
    revertible_hasta: int | None       # `aplicado_en` + 14 días
    ventana: dict | None               # {desde, hasta} si está programado
    orden_id: str | None               # la orden en curso si está `aplicando`
    accion: str | None                 # `aplicar` o `revertir` si está `aplicando`
    ultima_en: int | None
    incompatibilidades: tuple = ()     # la lista de la última fila `incompatible` si sigue incompatible

    @property
    def en_curso(self) -> bool:
        return self.estado == cat.APLICANDO

    def revertible(self, ahora: int) -> bool:
        return self.estado == cat.APLICADO and self.revertible_hasta is not None and int(ahora) < self.revertible_hasta

    def plazo_vencido(self, ahora: int) -> bool:
        return self.estado == cat.APLICADO and self.revertible_hasta is not None and int(ahora) >= self.revertible_hasta


def derivar(filas: Sequence[Fila], dias_reversion: int = cat.DIAS_REVERSION) -> Derivado:
    """El estado a partir de las filas del paquete, en orden de inserción. Las filas se aplican una a una; una fila imposible lanza `EstadoInvalido` (jamás debería existir)."""
    estado: str | None = None
    previo: str | None = None
    aplicado_en = ventana = orden_id = accion = ultima_en = None
    incompatibilidades: tuple = ()
    for fila in filas:
        detalle = fila.detalle if isinstance(fila.detalle, dict) else {}
        if fila.tipo == cat.H_APLICANDO:
            previo = estado
        nuevo = transicion(estado, previo, fila.tipo)
        if fila.tipo == cat.H_APLICADO:
            aplicado_en = int(fila.en)
        elif fila.tipo in (cat.H_REVERTIDO, cat.H_ARCHIVADO, cat.H_REVERSION_FALLIDA):
            aplicado_en = None
        if fila.tipo == cat.H_PROGRAMADO:
            ventana = {"desde": int(detalle.get("desde", 0)), "hasta": int(detalle.get("hasta", 0))}
        elif nuevo in (cat.VERIFICADO, cat.INCOMPATIBLE, cat.APLICADO, cat.REVERTIDO, cat.ARCHIVADO, cat.REVERSION_FALLIDA):
            ventana = None
        if fila.tipo == cat.H_APLICANDO:
            orden_id, accion = str(detalle.get("orden_id") or ""), str(detalle.get("accion") or cat.ACCION_APLICAR)
        elif nuevo != cat.APLICANDO:
            orden_id = accion = None
        incompatibilidades = tuple(detalle.get("incompatibilidades") or ()) if fila.tipo == cat.H_INCOMPATIBLE else (incompatibilidades if nuevo == cat.INCOMPATIBLE else ())
        estado, ultima_en = nuevo, int(fila.en)
    return Derivado(estado=estado, previo=previo, aplicado_en=aplicado_en, revertible_hasta=None if aplicado_en is None else aplicado_en + dias_reversion * cat.DIA_MS,
                    ventana=ventana, orden_id=orden_id, accion=accion, ultima_en=ultima_en, incompatibilidades=incompatibilidades)


def exigir_revertible(derivado: Derivado, ahora: int) -> None:
    if derivado.estado == cat.REVERSION_FALLIDA:
        return                                                         # se puede reintentar la reversión
    if derivado.estado != cat.APLICADO:
        raise EstadoInvalido(f"Sólo se revierte un paquete aplicado; éste está «{derivado.estado}».", estado=derivado.estado)
    if not derivado.revertible(ahora):
        raise FueraDePlazoReversion(revertible_hasta=derivado.revertible_hasta)


def exigir_aplicable(derivado: Derivado) -> None:
    if derivado.estado not in (cat.VERIFICADO, cat.PROGRAMADO, cat.INCOMPATIBLE):
        raise EstadoInvalido(f"Sólo se aplica un paquete verificado; éste está «{derivado.estado}».", estado=derivado.estado)


def exigir_programable(derivado: Derivado) -> None:
    if derivado.estado not in (cat.VERIFICADO, cat.PROGRAMADO):
        raise EstadoInvalido(f"Sólo se programa un paquete verificado; éste está «{derivado.estado}».", estado=derivado.estado)


def resultado_a_fila(resultado: str, accion: str) -> str:
    """El tipo de fila del historial que corresponde a lo que el Host respondió (P-06, FUN-187)."""
    if resultado == cat.R_APLICADO:
        return cat.H_APLICADO
    if resultado == cat.R_REVERTIDO:
        return cat.H_REVERTIDO
    if resultado == cat.R_REVERSION_FALLIDA:
        return cat.H_REVERSION_FALLIDA
    if resultado == cat.R_APLAZADA:
        return cat.H_APLAZADA
    # `rechazada`: el Host no pudo ni empezar (comprobaciones finales). Para una reversión equivale a que no se revirtió; para una aplicación, a que se aplazó.
    return cat.H_APLAZADA if accion == cat.ACCION_APLICAR else cat.H_REVERSION_FALLIDA
