"""
La interfaz de MOD-017 para los OTROS módulos del mismo proceso (BR-004): quien necesita saber si hay una actualización en curso pregunta aquí; nadie lee `m17_*`. La usan el
middleware que difiere el inicio de clases (P-08) y `/health/`.

  · R-04  NINGÚN fallo interno de actualización llega a quien pregunta: se registra y se responde «no hay nada en curso» (nunca se cierra el aula por esto).
"""
from __future__ import annotations

import logging

from .dominio import catalogos as cat

log = logging.getLogger("avacom.actualizacion")


def _s():
    from .infraestructura import contenedor
    return contenedor.servicios()


def en_curso() -> bool:
    """¿Hay una orden aceptada y sin resultado? (desde que se acepta hasta que termina, el inicio de clases responde 503 `actualizacion_en_curso`). De memoria; nunca lanza."""
    try:
        from .aplicacion.acciones import hay_orden_en_curso
        return hay_orden_en_curso(_s())
    except Exception:   # noqa: BLE001 — R-04
        log.exception("No se pudo consultar si hay una actualización en curso", extra={"evento": "actualizacion.en_curso_fallo", "ruta": "bad"})
        return False


def estado_resumido() -> dict:
    """Lo que `/health/` añade (sólo el estado): `{estado, en_curso, programados, orden_pendiente}`. Nunca lanza."""
    try:
        from .aplicacion.acciones import ConsultarEstado
        r = ConsultarEstado(_s()).resumen(con_modulos=False)
        return {"estado": r["estado"], "en_curso": r["en_curso"], "programados": len(r["programados"]), "orden_pendiente": r["orden_pendiente"]}
    except Exception as error:   # noqa: BLE001 — el health nunca falla por la actualización
        return {"estado": "desconocido", "en_curso": None, "programados": 0, "orden_pendiente": False, "error": str(error)[:200]}


def tick(origen: str = "manual") -> dict | None:
    """Un ciclo del vigilante a mano (las pruebas y el técnico)."""
    from .infraestructura.vigilante import Vigilante
    return Vigilante.tick(origen)


MODULO = cat.MODULO
