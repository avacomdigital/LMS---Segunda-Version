"""
Rutas HTTP del agente de IA (`/api/agente-ia/`). Las vistas sólo traducen HTTP ↔ casos de uso (`aplicacion/agente.py`).

  POST /api/agente-ia/preguntar/  {pregunta, conversacion?}  → {conversacion, texto, modelo, contexto_usado, ms}       (pasos 1 y 2: la pregunta al modelo)
  POST /api/agente-ia/hablar/     {texto, velocidad?}        → audio/wav  (X-Audio-Duration-Ms, X-Audio-Chunks)        (pasos 3 y 4: la voz de ese texto)
  GET  /api/agente-ia/estado/                                → {disponible, voz_disponible, servicio_activo, codigo, motivo, modelo}

Contrato de degradación (el mismo del resto del nodo): un fallo de la IA se responde con `{detail, codigo, reintentable, sugerencia?}` y el estado de `dominio/errores.py`
(503 servicio apagado o sin configurar, 504 tiempo agotado, 429 ocupado, 502 respuesta inválida, 400/422 petición inválida). Jamás un 500 sin explicación y jamás un cierre de la
app: el texto de la pregunta y el de la respuesta viajan en peticiones separadas, así que un fallo de voz no pierde la respuesta escrita.

Quién puede usarlo: cualquier persona del PERSONAL con sesión (con `AVACOM_LMS_EXIGIR_SESION=1`; sin ella, como el resto del nodo, quien el cliente declare). Una tableta de alumno no.
"""
from __future__ import annotations

import logging

from django.http import HttpResponse
from rest_framework import exceptions, status
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion.agente import Actor
from ..dominio.errores import ErrorDeIa
from ..infraestructura.contenedor import agente

log = logging.getLogger("avacom.agente_ia")


class IgnorarAccept(DefaultContentNegotiation):
    """La respuesta de `hablar/` es audio y el cliente puede pedir `Accept: audio/wav`: la negociación estándar de DRF contestaría 406 antes de llegar a la vista."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    return dict(datos) if isinstance(datos, dict) else {}


def _menu_de(principal) -> str:
    """El menú de la sesión como texto: «student», «teacher»… `Menu` es un `str`+`Enum`, y `str(Menu.STUDENT)` es «Menu.STUDENT», no «student» (así dejaba pasar a los alumnos): se toma `.value`."""
    menu = getattr(principal, "menu", "")
    return str(getattr(menu, "value", menu))


class VistaIa(APIView):
    permission_classes = [SesionSiSeExige]
    content_negotiation_class = IgnorarAccept

    def _actor(self, request) -> Actor:
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, es_personal=_menu_de(principal) != "student")
        declarado = str(_cuerpo(request).get("actor") or request.query_params.get("actor") or "")[:64]
        return Actor(id=declarado or None, es_personal=True)

    @staticmethod
    def _sin_permiso() -> Response:
        return Response({"detail": "El agente de IA es para el personal del aula.", "codigo": "sin_permiso"}, status=status.HTTP_403_FORBIDDEN)

    def handle_exception(self, exc):
        if isinstance(exc, ErrorDeIa):
            return Response(exc.cuerpo(), status=exc.http)
        if isinstance(exc, exceptions.APIException):         # sin sesión, método no permitido, JSON mal formado: lo de siempre
            return super().handle_exception(exc)
        # Un defecto de esta capa (no de la IA): se registra con su traza y el aula recibe una respuesta con código, no un 500 en blanco.
        log.exception("Falló el agente de IA fuera de los casos de uso", extra={"evento": "agente_ia.defecto", "ruta": "bad", "modulo": "agente_ia"})
        error = ErrorDeIa("ai_internal", f"{exc.__class__.__name__}: {exc}")
        return Response(error.cuerpo(), status=error.http)


class PreguntarView(VistaIa):
    def post(self, request):
        actor = self._actor(request)
        if not actor.es_personal:
            return self._sin_permiso()
        datos = _cuerpo(request)
        pregunta, pantalla = datos.get("pregunta"), datos.get("conversacion")
        return Response(agente().preguntar(actor, pregunta if isinstance(pregunta, str) else None, pantalla if isinstance(pantalla, str) else None))


class HablarView(VistaIa):
    def post(self, request):
        actor = self._actor(request)
        if not actor.es_personal:
            return self._sin_permiso()
        datos = _cuerpo(request)
        texto = datos.get("texto")
        voz = agente().hablar(actor, texto if isinstance(texto, str) else None, datos.get("velocidad"))
        respuesta = HttpResponse(voz.wav, content_type="audio/wav")
        respuesta["X-Audio-Duration-Ms"] = str(voz.duracion_ms)
        respuesta["X-Audio-Chunks"] = str(voz.trozos)
        respuesta["Cache-Control"] = "no-store"
        return respuesta


class EstadoView(VistaIa):
    def get(self, request):
        actor = self._actor(request)
        if not actor.es_personal:
            return self._sin_permiso()
        return Response(agente().estado(actor))
