"""Parámetros del aula que decide la instalación (tiempos, capacidad, frenos). Los lee el composition root de
`settings`; los casos de uso sólo ven este objeto, así que el dominio y la aplicación siguen sin conocer Django."""
from __future__ import annotations

from dataclasses import dataclass

from ..dominio import sesion as dom


@dataclass(frozen=True)
class ConfigAula:
    latido_vencido_ms: int = 15_000                 # «conectado» sin latido en este tiempo → «reconectando» (FUN-073)
    ausencia_ms: int = 5 * 60 * 1000                # «reconectando» sin latido en este tiempo → «salió»
    inactividad_ms: int = 120 * 60 * 1000           # clase abierta sin actividad en este tiempo → se cierra sola (JRN-011)
    dispositivos_normal: int = dom.CAPACIDAD_NORMAL   # BR-063
    dispositivos_pico: int = dom.CAPACIDAD_PICO
    unirse_intentos: int = 8                        # fallos de código permitidos por tableta en la ventana
    unirse_ventana_ms: int = 60_000
    ventana_reanudacion_ms: int = dom.VENTANA_REANUDACION_MS   # BR-051
    gracia_entrega_ms: int = dom.GRACIA_ENTREGA_MS             # DEC-019
    intervalo_latido_ms: int = 5_000                # cada cuánto debe mandar latido una tableta conectada por WebSocket
    intervalo_respaldo_ms: int = 15_000             # sondeo de respaldo con el WebSocket vivo (por si se pierde un aviso)
