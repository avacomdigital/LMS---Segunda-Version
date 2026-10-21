"""
La regla de purga (P-08): BR-017 con sus CUATRO condiciones a la vez, BR-018 (un consumidor desinstalado deja de bloquear; uno suspendido bloquea hasta su límite de rezago, y
entonces se avisa), BR-019 (por lote, en orden de secuencia, sin huecos en el tramo vigente) e INV-009 (nunca lo que un consumidor registrado necesita ni lo que no está respaldado).

Construida y APAGADA: sin MOD-016 el respaldo nunca «cubre» nada, así que nada es elegible. Puro: no importa Django.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from . import catalogos as cat


@dataclass(frozen=True)
class Condiciones:
    superado_por_todos: bool          # 1 · todos los consumidores registrados lo superaron con su marca
    en_respaldo_verificado: bool      # 2 · quedó incluido en un respaldo verificado (MOD-016)
    retencion_cumplida: bool          # 3 · pasó la retención mínima (7 días por defecto) Y la de su clase
    reconocido_o_sin_sincronizacion: bool   # 4 · si hay sincronización habilitada, ya fue reconocido por ella
    inmutable: bool = False           # la clase auditoría nunca se purga

    @property
    def elegible(self) -> bool:
        return (self.superado_por_todos and self.en_respaldo_verificado and self.retencion_cumplida and self.reconocido_o_sin_sincronizacion and not self.inmutable)

    def motivos(self) -> tuple[str, ...]:
        faltan = []
        if not self.superado_por_todos:
            faltan.append("consumidor_pendiente")
        if not self.en_respaldo_verificado:
            faltan.append("sin_respaldo_verificado")
        if not self.retencion_cumplida:
            faltan.append("retencion_vigente")
        if not self.reconocido_o_sin_sincronizacion:
            faltan.append("sin_reconocer")
        if self.inmutable:
            faltan.append("inmutable")
        return tuple(faltan)


@dataclass(frozen=True)
class Evento:
    secuencia: int
    creado_en: int
    retencion_dias: int | None        # None = permanente: jamás se purga
    inmutable: bool = False


def evaluar(evento: Evento, *, marcas: Iterable[int], ahora: int, respaldo_cubre: Callable[[int], bool], sincronizacion_habilitada: bool = False,
            reconocida_hasta: int = 0, retencion_minima_dias: int = cat.RETENCION_MINIMA_DIAS) -> Condiciones:
    """
    Las cuatro condiciones para UN evento. `marcas` son las marcas de TODOS los consumidores registrados (un desinstalado ya no está: BR-018); sin consumidores registrados la
    condición 1 se cumple sola (nadie lo necesita). `respaldo_cubre(secuencia)` lo responde MOD-016 por el puerto; hoy siempre False.
    """
    marcas = list(marcas)
    superado = all(int(m) >= int(evento.secuencia) for m in marcas)
    if evento.retencion_dias is None:
        retencion = False
    else:
        dias = max(int(retencion_minima_dias), int(evento.retencion_dias))
        retencion = int(ahora) - int(evento.creado_en) >= dias * cat.DIA_MS
    reconocido = (not sincronizacion_habilitada) or int(reconocida_hasta) >= int(evento.secuencia)
    return Condiciones(superado, bool(respaldo_cubre(int(evento.secuencia))), retencion, reconocido, evento.inmutable)


def lote_purgable(eventos: Iterable[Evento], **condiciones) -> list[int]:
    """
    BR-019: las secuencias que se pueden borrar en ESTE lote, en orden y SIN huecos: se recorre desde la más baja y se para en la primera que no es elegible (lo que sigue, aunque
    fuera elegible, esperaría: borrar «saltando» dejaría un hueco en el tramo vigente).
    """
    salida: list[int] = []
    for evento in sorted(eventos, key=lambda e: e.secuencia):
        if not evaluar(evento, **condiciones).elegible:
            break
        salida.append(int(evento.secuencia))
    return salida


def bloquea_la_purga(marca: int, ultima_secuencia: int, limite_rezago: int) -> tuple[bool, bool]:
    """BR-018: `(bloquea, avisar)`. Un consumidor rezagado bloquea la purga mientras su rezago no supere el límite; superado, SIGUE bloqueando (INV-009) pero hay que avisar al
    administrador: algo está mal con ese consumidor y es él quien decide desregistrarlo."""
    rezago = max(0, int(ultima_secuencia) - int(marca))
    return rezago > 0, rezago > int(limite_rezago)
