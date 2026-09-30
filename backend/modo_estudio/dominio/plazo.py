"""
La fecha límite de una asignación y lo que se hace con el trabajo que llega tarde (D-9, D-8). Dominio puro: no importa Django.

Reglas del Documento Maestro que se cumplen aquí:
  - DEC-014 · plazo BLANDO (por defecto): la fecha límite marca, no cierra. Siempre se acepta; lo capturado después de la fecha se marca
    `fuera_de_plazo`.
  - Plazo ENDURECIDO: la asignación «cierra al vencer». Lo capturado antes y recibido dentro de la gracia se acepta; lo capturado antes
    pero recibido después queda PENDIENTE de la decisión del profesor (BR-074: nunca se descarta en silencio); lo capturado después
    del cierre se rechaza. Es la misma política de recepción del aula (`classroom_engine.dominio.actividad.politica_de_recepcion`,
    BR-052, DEC-019): se reutiliza, no se copia.
  - BR-062 / INV-017: ninguna hora con valor académico sale del reloj del aparato. El aparato manda cuándo capturó (`ocurrido_en`),
    ya normalizado al reloj del nodo; el nodo decide con SU reloj (`recibido_en`).
  - «Vencida» no se guarda: es derivada (fecha pasada y tarea no completada).
"""
from __future__ import annotations

from classroom_engine.dominio import actividad as politica_del_aula

from . import catalogos as cat

DIA_MS = 24 * 60 * 60 * 1000

ACEPTAR = politica_del_aula.ACEPTAR
DECIDE_EL_PROFESOR = politica_del_aula.DECIDE_EL_PROFESOR
RECHAZAR = politica_del_aula.RECHAZAR


def cierre_efectivo(*, fecha_limite: int | None, plazo: str, cerrada_en: int | None) -> tuple[int | None, str]:
    """El instante a partir del cual la asignación deja de aceptar trabajo sin más, y por qué: `(instante, motivo)`.
    Lo primero que ocurra entre el cierre que hizo el profesor y la fecha límite de un plazo endurecido."""
    candidatos: list[tuple[int, str]] = []
    if cerrada_en is not None:
        candidatos.append((int(cerrada_en), cat.MOTIVO_ASIGNACION_CERRADA))
    if plazo == cat.ENDURECIDO and fecha_limite is not None:
        candidatos.append((int(fecha_limite), cat.MOTIVO_PLAZO_VENCIDO))
    return min(candidatos) if candidatos else (None, "")


def politica_de_recepcion(*, fecha_limite: int | None, plazo: str, gracia_ms: int, cerrada_en: int | None,
                          capturado_en: int | None, recibido_en: int) -> tuple[str, str]:
    """¿Qué se hace con un trabajo que llega ahora? `(decisión, motivo)`: ACEPTAR (motivo vacío), DECIDE_EL_PROFESOR
    (`fuera_de_gracia`) o RECHAZAR (`plazo_vencido` o `asignacion_cerrada`, según cuál fue el cierre). Con plazo blando y sin cierre
    manual la asignación nunca cierra: siempre se acepta."""
    cierre, motivo = cierre_efectivo(fecha_limite=fecha_limite, plazo=plazo, cerrada_en=cerrada_en)
    decision = politica_del_aula.politica_de_recepcion(
        cerrada_en=cierre, capturada_en=capturado_en, recibida_en=recibido_en, gracia_ms=gracia_ms)
    if decision == ACEPTAR:
        return ACEPTAR, ""
    if decision == DECIDE_EL_PROFESOR:
        return DECIDE_EL_PROFESOR, cat.MOTIVO_FUERA_DE_GRACIA
    return RECHAZAR, motivo


def fuera_de_plazo(fecha_limite: int | None, capturado_en: int | None) -> bool:
    """Lo capturado después de la fecha límite (con plazo blando se acepta, marcado)."""
    return fecha_limite is not None and capturado_en is not None and int(capturado_en) > int(fecha_limite)


def vencida(fecha_limite: int | None, estado_tarea: str, ahora: int) -> bool:
    """«Vencida» es derivada: la fecha pasó y la tarea no está completada. Sin fecha nunca vence."""
    return fecha_limite is not None and estado_tarea != cat.COMPLETADA and ahora > int(fecha_limite)


def vigente_hasta(*, fecha_limite: int | None, gracia_ms: int, ahora: int, vigencia_dias: int) -> int:
    """D-8: hasta cuándo sirve un paquete descargado. `fecha_limite + gracia` si la asignación tiene fecha; si no, los días de
    `AVACOM_ESTUDIO_VIGENCIA_DIAS` (14) desde que se pide. Si esa fecha ya pasó (un plazo blando que se sigue aceptando tarde), el
    paquete no nace vencido: dura lo normal desde que se pide."""
    normal = ahora + max(1, int(vigencia_dias)) * DIA_MS
    if fecha_limite is None:
        return normal
    limite = int(fecha_limite) + max(0, int(gracia_ms))
    return limite if limite > ahora else normal


def paquete_vencido_por_vigencia(vigente_hasta_ms: int | None, ahora: int) -> bool:
    return vigente_hasta_ms is not None and ahora > int(vigente_hasta_ms)


def gracia_en_ms(gracia_min) -> int:
    """`gracia_min` (minutos, como lo pide OPS) → `gracia_ms`. Ausente: los 15 minutos de DEC-019."""
    return cat.GRACIA_MS_POR_DEFECTO if gracia_min in (None, "") else int(gracia_min) * 60_000
