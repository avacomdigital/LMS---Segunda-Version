"""
`ActualizacionMiddleware` (P-08, R-01, R-02): el ÚNICO sitio donde una actualización puede responder «el aula se está actualizando».

  · SÓLO el inicio de una clase (`POST /api/aula/sesiones/`), y SÓLO desde que el nodo acepta una orden hasta que el Host devuelve su resultado. Ninguna clase ya abierta se toca:
    unirse, responder, los exámenes, el modo de estudio y sus colas siguen igual (R-02: ninguna ruta con cola del cliente cambia).
  · 503 `actualizacion_en_curso` con `Retry-After`, y NO un 4xx: el cliente conserva su cola ante un 5xx y la descarta ante un 4xx (`Core/Services/ColaRespuestas.cs`). Tampoco es un 403:
    el middleware de auditoría asentaría un «acceso denegado» (P-13).
  · El estado se lee de MEMORIA (`servicios.en_curso`); `try/except` TOTAL que DEJA PASAR y registra (R-04): un fallo de este módulo jamás produce un 500 ni cierra una ruta de negocio.
"""
from __future__ import annotations

import logging

from django.http import JsonResponse

from .. import servicios

log = logging.getLogger("avacom.actualizacion")

RUTA_INICIO_DE_CLASE = "/api/aula/sesiones/"
MENSAJE = "El aula se está actualizando; vuelve a intentarlo en unos minutos."
REINTENTAR_EN_S = 60


class ActualizacionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            respuesta = self._diferir(request)
        except Exception:   # noqa: BLE001 — R-04: ante cualquier fallo, la petición pasa
            log.exception("La actualización no pudo decidir sobre una petición; pasa", extra={"evento": "actualizacion.middleware_fallo", "ruta": "bad"})
            respuesta = None
        return respuesta if respuesta is not None else self.get_response(request)

    @staticmethod
    def _diferir(request):
        if request.method != "POST" or request.path_info != RUTA_INICIO_DE_CLASE:
            return None
        if not servicios.en_curso():
            return None
        respuesta = JsonResponse({"detail": MENSAJE, "codigo": "actualizacion_en_curso", "reintentar_en_s": REINTENTAR_EN_S}, status=503)
        respuesta["Retry-After"] = str(REINTENTAR_EN_S)
        return respuesta
