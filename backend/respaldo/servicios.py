"""
La interfaz de MOD-016 para los OTROS módulos del mismo proceso (BR-004): quien necesita saber qué hay respaldado pregunta aquí; nadie lee `m16_*`. La usan la purga de la cola única
(MOD-015, BR-017: «quedó incluido en un respaldo verificado») y `/health/`.

  · R-04  NINGÚN fallo interno de respaldo llega a quien pregunta: se registra y se responde lo más prudente (que NO hay respaldo verificado: la purga no avanza).
"""
from __future__ import annotations

import logging

from .dominio import catalogos as cat

log = logging.getLogger("avacom.respaldo")


def _s():
    from .infraestructura import contenedor
    return contenedor.servicios()


def verificado_hasta() -> int:
    """La mayor secuencia global de la cola única que está incluida en un respaldo VERIFICADO y restaurable que sigue en el equipo (BR-017, INV-009). 0 si no hay ninguno. Nunca lanza."""
    try:
        from .aplicacion.motor import Motor
        s = _s()
        with s.uow(lectura=True) as uow:
            return max((int(f["secuencia_global"]) for f in Motor(s).fichas(uow) if f["restaurable"]), default=0)
    except Exception:   # noqa: BLE001 — R-04
        log.exception("No se pudo consultar el último respaldo verificado", extra={"evento": "respaldo.consulta_fallo", "ruta": "bad"})
        return 0


def cubre(secuencia: int) -> bool:
    return int(secuencia) <= verificado_hasta()


def estado_resumido() -> dict:
    """Lo que `/health/` añade: `{ultimo_verificado_en, dias_sin_respaldo, aviso, en_marcha}`. Nunca lanza y no revela rutas ni personas."""
    try:
        from .aplicacion.acciones import ConsultarEstado
        r = ConsultarEstado(_s()).resumen()
        ultimo = r["ultimo_restaurable"]
        return {"ultimo_verificado_en": None if ultimo is None else ultimo["creado_en"], "dias_sin_respaldo": r["dias_sin_respaldo"], "aviso": r["aviso_sin_respaldo"],
                "en_marcha": r["en_marcha"] is not None, "custodia_emitida": r["custodia"]["emitida"]}
    except Exception as error:   # noqa: BLE001 — el health nunca falla por el respaldo
        return {"ultimo_verificado_en": None, "dias_sin_respaldo": None, "aviso": None, "en_marcha": None, "error": str(error)[:200]}


def tick(origen: str = "manual") -> dict | None:
    """Un ciclo del vigilante a mano (las pruebas y el técnico)."""
    from .infraestructura.vigilante import Vigilante
    return Vigilante.tick(origen)


MODULO = cat.MODULO
