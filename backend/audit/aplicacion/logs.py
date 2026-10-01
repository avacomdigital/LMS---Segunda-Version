"""
Logs de diagnóstico por la API (§2.4, §4.2): recibir los renglones WARNING+ de OPS y Student (mejor esfuerzo, con
tope de tamaño y de tasa por equipo; NO toca la bitácora) y leer las últimas líneas del nodo para la pestaña
«Errores» de OPS y el «Estado del equipo» del técnico (sólo identificadores y cifras).
"""
from __future__ import annotations

import threading
import time

from django.conf import settings

from ..dominio import errores
from ..infraestructura import archivo_logs

_tasa: dict[str, tuple[float, int]] = {}
_candado = threading.Lock()
VENTANA_S = 60.0


def _tope_renglones() -> int:
    return int(getattr(settings, "AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES", 200))


def _tope_por_minuto() -> int:
    return int(getattr(settings, "AVACOM_LMS_LOGS_CLIENTES_MAX_POR_MINUTO", 1000))


def _cupo(dispositivo_id: str, pedidos: int) -> int:
    """Cuántos renglones puede entregar este equipo ahora sin pasar el tope por minuto."""
    ahora = time.monotonic()
    with _candado:
        inicio, cuenta = _tasa.get(dispositivo_id, (ahora, 0))
        if ahora - inicio >= VENTANA_S:
            inicio, cuenta = ahora, 0
        libres = max(0, _tope_por_minuto() - cuenta)
        aceptados = min(pedidos, libres)
        _tasa[dispositivo_id] = (inicio, cuenta + aceptados)
        return aceptados


def recibir_de_clientes(dispositivo_id: str | None, app: str, version_app: str, renglones: list[dict]) -> dict:
    """Escribe los renglones en backend-clientes.log. Sin equipo autenticado no se acepta nada (nunca se inventa)."""
    if not dispositivo_id:
        raise errores.SinPermiso("La entrega de logs exige un equipo registrado y activo (X-Avacom-Dispositivo) o una sesión.",
                                 permiso="logs.clientes", codigo_detalle="dispositivo_requerido")
    recibidos = len(renglones)
    renglones = renglones[: _tope_renglones()]
    aceptados = _cupo(dispositivo_id, len(renglones))
    for renglon in renglones[:aceptados]:
        archivo_logs.escribir_de_cliente(renglon, dispositivo_id, app, version_app)
    return {"recibidos": recibidos, "escritos": aceptados, "descartados": recibidos - aceptados, "dispositivo_id": dispositivo_id}


def leer(filtros: dict, ultimos: int | None = None) -> dict:
    return archivo_logs.leer(filtros, ultimos=int(ultimos or 200))


def reiniciar_tasa() -> None:
    with _candado:
        _tasa.clear()
