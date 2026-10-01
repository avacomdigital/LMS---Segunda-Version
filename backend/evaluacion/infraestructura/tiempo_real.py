"""
Adaptador del puerto `TiempoReal`: reutiliza el canal del aula (Django Channels, 007-01). Cada cambio de una evaluación que nació en una clase se avisa
a las tabletas y al profesor; el aviso sale al CONFIRMARSE la transacción y NUNCA lleva contenido académico (ni respuestas, ni nombres, ni claves): el
cliente vuelve a pedir por HTTP, que sigue siendo la única fuente de verdad y el respaldo cuando el WebSocket se cae. Una evaluación sin clase no
avisa por aquí: la tableta la descubre en su sondeo (`GET /mias/`) y en su latido de 5 s.

    evaluacion         → profesor y todas las tabletas de la clase
    evaluacion_panel   → sólo el profesor
"""
from __future__ import annotations

import logging

log = logging.getLogger("avacom.evaluacion.tiempo_real")


class TiempoRealEvaluacion:
    def cambio(self, sesion_id: str, que: str, carga: dict | None = None) -> None:
        if not sesion_id:
            return
        try:
            from classroom_engine.infraestructura.tiempo_real import TiempoRealCanales
            TiempoRealCanales().cambio(sesion_id, que, carga)
        except Exception:   # noqa: BLE001 — un aviso que no sale no tumba el examen: el sondeo lo cubre
            log.exception("No se pudo avisar el cambio «%s» de la clase %s", que, sesion_id)
