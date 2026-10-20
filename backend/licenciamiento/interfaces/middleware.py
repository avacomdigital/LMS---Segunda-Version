"""
`LicenciaMiddleware` (P-10): el ÚNICO sitio donde una licencia puede responder «no disponible por licencia».

  · Una tabla «método + ruta → capacidad» y la lista blanca de lo intocable (`dominio/rutas.py`, derivada de los `urls.py` reales): lo intocable manda sobre la tabla. El WebSocket no pasa
    por aquí y nunca se bloquea.
  · El estado se lee de MEMORIA: cero consultas SQL en el camino de una petición (R-07).
  · `try/except` TOTAL que DEJA PASAR y registra (R-04): un fallo de licenciamiento jamás produce un 500 ni cierra una ruta de negocio.
  · La respuesta es un 402 `no_disponible_por_licencia` con la capacidad, y NO un 403: el middleware de auditoría asentaría un 403 como `acceso.denegado`, y el Maestro (VER-10) exige
    «no disponible por licencia, conservar la concesión del permiso en el rol y registrar un bloqueo de licencia». El asiento `licencia.bloqueo_aplicado` lo escribe el programador,
    agregado: uno por actor, capacidad y hora.
  · Nunca se devuelve en una ruta que cargue colas del cliente (R-02): esas son intocables.
"""
from __future__ import annotations

import logging

from django.http import JsonResponse

from .. import servicios
from ..dominio import rutas
from ..dominio.catalogos import ETIQUETAS_DE_CAPACIDAD

log = logging.getLogger("avacom.licenciamiento")

MENSAJE = "Este módulo no está disponible con la licencia actual. Tu permiso se conserva: vuelve a funcionar al renovar la licencia."


def _actor(request) -> str:
    """Quién pidió lo bloqueado, para el asiento agregado: quien firma el JWT (se verifica la firma, sin tocar la base de datos), o el equipo, o «anonimo»."""
    try:
        cabecera = request.headers.get("Authorization", "")
        if cabecera.lower().startswith("bearer "):
            from acceso.infraestructura.contenedor import servicios as servicios_acceso
            return str(servicios_acceso().tokens.leer(cabecera[7:].strip()).get("sub") or "anonimo")
    except Exception:   # noqa: BLE001 — un token malo no cambia lo que se responde
        pass
    return servicios._actor_actual()


class LicenciaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            respuesta = self._bloquear(request)
        except Exception:   # noqa: BLE001 — R-04: ante cualquier fallo, la petición pasa
            log.exception("La licencia no pudo decidir sobre una petición; pasa", extra={"evento": "licencia.middleware_fallo", "ruta": "bad"})
            respuesta = None
        return respuesta if respuesta is not None else self.get_response(request)

    @staticmethod
    def _bloquear(request):
        if request.method == "OPTIONS":                       # la consulta previa no lleva datos ni pide ningún módulo
            return None
        # HEAD se trata como GET (DRF lo atiende con la vista GET): `rutas.capacidad_de` ya lo trae en la tabla, así que un HEAD a un módulo apagado también recibe el 402.
        capacidad = rutas.capacidad_de(request.method, request.path_info)
        if capacidad is None or servicios.capacidad_habilitada(capacidad):
            return None
        servicios.registrar_bloqueo_de_modulo(capacidad, _actor(request))
        return JsonResponse({"detail": MENSAJE, "codigo": "no_disponible_por_licencia", "capacidad": capacidad, "modulo": ETIQUETAS_DE_CAPACIDAD.get(capacidad, capacidad)}, status=402)
