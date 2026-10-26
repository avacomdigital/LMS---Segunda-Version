"""
La interfaz de MOD-001 para los OTROS módulos del mismo proceso (BR-004), SÓLO LECTURA salvo `revocar_sesiones_por_restauracion`. La usa MOD-018 · Licensing para contar las identidades
activas frente al cupo de la licencia (FUN-190) y MOD-016 · Backup & Recovery para el nombre de la institución y para cerrar las sesiones tras restaurar, sin leer `m01_*`.
"""
from __future__ import annotations

from .infraestructura.contenedor import servicios as _servicios


def contar_usuarios_activos() -> int | None:
    """Las identidades activas que cuentan para el cupo de la licencia (BR-027): sin visitantes, retiradas ni provisionales ya vinculadas. None si el nodo aún no está instalado."""
    s = _servicios()
    fabrica = s.uow_lectura or s.uow
    with fabrica() as uow:
        organizacion = uow.organizaciones.unica()
        return uow.usuarios.contar_activos(organizacion.id) if organizacion is not None else None


def nombre_de_la_organizacion() -> str:
    """El nombre de la institución para las constancias de respaldo; cadena vacía si el nodo aún no está instalado."""
    s = _servicios()
    fabrica = s.uow_lectura or s.uow
    with fabrica() as uow:
        organizacion = uow.organizaciones.unica()
        return organizacion.nombre if organizacion is not None else ""


def revocar_sesiones_por_restauracion() -> int:
    """MOD-016 · FUN-174: tras restaurar un respaldo se revocan TODAS las sesiones abiertas (cada persona entra de nuevo). Devuelve cuántas se cerraron."""
    from .dominio.valores import MotivoCierre

    s = _servicios()
    with s.uow() as uow:
        return uow.sesiones.revocar_todas(MotivoCierre.RESTAURACION.value, s.reloj.ahora_ms())
