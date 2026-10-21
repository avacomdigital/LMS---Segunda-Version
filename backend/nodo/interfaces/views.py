"""
Rutas HTTP de MOD-015 (`/api/nodo/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM. Son rutas NÚCLEO (R-01): el modo restringido jamás las rechaza.

Contrato de degradación (el mismo del resto del backend): DatosInvalidos → 400 · SinPermiso → 403 · NoEncontrado / ConsumidorDesconocido → 404 · ModuloYaCortado /
ContratoIncompatible / ConsumidorSinAplicador / ProblemaYaResuelto / ReprocesoFallido → 409 · NodoRestringido → 503 (+ Retry-After).

Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor`. Todo 403 deja el asiento `nodo.acceso_denegado`. NINGUNA respuesta
lleva la carga de un evento (R-13): el técnico ve metadatos.
"""
from __future__ import annotations

import logging

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from .. import servicios
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.repositorios import AuditoriaNodo

log = logging.getLogger("avacom.nodo")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


class VistaNodo(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorNodo):
            if isinstance(exc, errores.SinPermiso):
                self._auditar_denegacion(exc)
            respuesta = Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
            if exc.http == 503:
                respuesta["Retry-After"] = "30"
            return respuesta
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def _auditar_denegacion(self, exc) -> None:
        try:
            actor = self._actor(self.request)
            AuditoriaNodo().denegada(actor.id, exc.extra.get("permiso"), self.request.method, self.request.path, exc.codigo, {"rol": actor.rol or None})
        except Exception:   # noqa: BLE001 — la denegación ya se dio; no fallar la respuesta por el asiento
            log.exception("No se pudo asentar el intento denegado sobre la cola")

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         dispositivo_id=str(principal.dispositivo_id or ""), principal=principal, rol=str(principal.rol_codigo or ""))
        actor_id = str(datos.get("actor") or request.query_params.get("actor") or "")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or request.query_params.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)


class EstadoView(VistaNodo):
    def get(self, request):
        return Response(servicios.estado(self._actor(request)))


class ColaView(VistaNodo):
    def get(self, request):
        return Response(servicios.cola(self._actor(request)))


class ProblemasView(VistaNodo):
    def get(self, request):
        q = request.query_params
        try:
            limite = int(q.get("limite") or 100)
        except ValueError:
            raise errores.DatosInvalidos("`limite` debe ser un número.", campo="limite")
        return Response(servicios.problemas(self._actor(request), q.get("consumidor") or None, q.get("estado") or None, limite))


class ReprocesarView(VistaNodo):
    def post(self, request, problema_id: int):
        return Response(servicios.reprocesar(problema_id, self._actor(request, _cuerpo(request))))


class ReproducirView(VistaNodo):
    def post(self, request, nombre: str):
        datos = _cuerpo(request)
        fuente = str(datos.get("fuente") or "") or None
        return Response(servicios.reproducir(nombre, fuente, actor=self._actor(request, datos)))
