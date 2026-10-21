"""
La interfaz de MOD-013 para los OTROS módulos del mismo proceso (BR-004). Hoy sólo lo que MOD-015 necesita desde el corte a la cola única (Fase 3): el lector de la cola antigua
`m13_evento_salida`, que queda intacta como historia de sólo lectura (BR-016). Los reportes se piden por `/api/reportes/`, no por aquí.

Devuelve dicts planos; no abre ninguna transacción.
"""
from __future__ import annotations


def eventos_legados(desde: int, limite: int, tipos: tuple[str, ...] | None, hasta: int) -> tuple[list[dict], int]:
    """El lector de la cola ANTIGUA de este módulo, que MOD-015 llama por su fachada: los eventos con `desde < id ≤ hasta` (y de esos `tipos`, o todos), en orden, y hasta dónde se
    miró. Lo registra `apps.ready` (R-09: la cola no lee tablas ajenas). Lectura pura."""
    from . import models as m

    filas = m.EventoSalida.objects.filter(id__gt=int(desde), id__lte=int(hasta))
    if tipos is not None:
        filas = filas.filter(tipo_evento__in=list(tipos))
    filas = list(filas.order_by("id")[: int(limite)])
    return [{"secuencia": f.id, "tipo": f.tipo_evento, "agregado_tipo": f.agregado_tipo, "agregado_id": f.agregado_id, "carga": f.carga, "creado_en": f.creado_en}
            for f in filas], (filas[-1].id if len(filas) >= int(limite) else int(hasta))
