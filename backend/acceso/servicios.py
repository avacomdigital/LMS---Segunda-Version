"""
La interfaz de MOD-001 para los OTROS módulos del mismo proceso (BR-004), SÓLO LECTURA. Hoy la usa MOD-018 · Licensing para contar las identidades activas frente al cupo de la licencia
(FUN-190) sin leer `m01_*`.
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
