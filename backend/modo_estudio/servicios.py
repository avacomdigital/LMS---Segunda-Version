"""
La interfaz de MOD-008 para los OTROS módulos del mismo proceso (BR-004: quien necesita algo de datos ajenos invoca la interfaz del propietario).
La usa MOD-009: liberar un equipo asignado exige que no conserve un paquete de estudio activo (FUN-093). Se resuelve de forma perezosa desde
`device_manager` (sin importarse al cargar), sin ciclo de importación.

Devuelve y recibe tipos simples; no abre ninguna transacción.
"""
from __future__ import annotations

from .infraestructura.contenedor import RelojNodo
from .infraestructura.unidad_trabajo import Cajones


def paquetes_activos_en(dispositivo_id: str, momento: int | None = None) -> int:
    """Cuántos paquetes de estudio conserva un equipo: `solicitado`, `descargandose` o `disponible`, no retirados y todavía vigentes (con el reloj del
    nodo). Un paquete vencido por vigencia ya no es material que proteger."""
    if not dispositivo_id:
        return 0
    return Cajones().paquetes.activos_en(dispositivo_id, momento if momento is not None else RelojNodo().ahora_ms())
