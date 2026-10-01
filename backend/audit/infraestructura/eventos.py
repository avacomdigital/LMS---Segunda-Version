"""Cola de salida propia de MOD-019 (`m19_evento_salida`): los eventos `auditoria.*.v1` (019-09)."""
from __future__ import annotations

from ..models import EventoSalida

EV_CADENA_VERIFICADA = "auditoria.cadena_verificada.v1"
EV_SALTO_DETECTADO = "auditoria.salto_detectado.v1"
EV_BITACORA_ROTADA = "auditoria.bitacora_rotada.v1"
EV_TRAMO_EXPORTADO = "auditoria.tramo_exportado.v1"
EV_REGISTRO_CREADO = "auditoria.registro_creado.v1"
EVENTOS = (EV_CADENA_VERIFICADA, EV_SALTO_DETECTADO, EV_BITACORA_ROTADA, EV_TRAMO_EXPORTADO, EV_REGISTRO_CREADO)


def publicar(tipo_evento: str, agregado_tipo: str, agregado_id: str, carga: dict) -> EventoSalida:
    if tipo_evento not in EVENTOS:
        raise ValueError(f"Evento fuera del catálogo de MOD-019: {tipo_evento}")
    return EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=str(agregado_id), tipo_evento=tipo_evento, carga=carga)
