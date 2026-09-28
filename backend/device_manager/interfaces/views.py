"""
Rutas HTTP de MOD-009 (`/api/dispositivos/`). Las vistas sólo traducen HTTP ↔ casos de uso.

Contrato de degradación (el mismo del resto del backend):
  DatosInvalidos → 400 · SinPermiso / DispositivoBloqueado / DispositivoInactivo → 403 ·
  NoEncontrado → 404 · NodoNoInstalado → 409. Los errores de `acceso` (sesión, políticas) conservan su forma.

Las tabletas llegan por la IP LAN del equipo maestro (`0.0.0.0:8000`); el registro y el latido son
públicos porque es la propia tableta la que se presenta (CAP-053) antes de tener sesión.
"""
from __future__ import annotations

from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import casos_uso as cu
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from . import serializers as s


def _validar(serializer_cls, datos, parcial: bool = False) -> dict:
    ser = serializer_cls(data=datos or {}, partial=parcial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


def _bandera(valor) -> bool:
    return str(valor or "").lower() in ("1", "true", "si", "sí", "yes")


class VistaDispositivos(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorDispositivos):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos",
                             "errores": exc.detail}, status=400)
        return super().handle_exception(exc)

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare, como en el aula."""
        principal = principal_de(request)
        datos = datos or {}
        if principal is not None:
            return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True, principal=principal)
        actor_id = str(datos.get("actor") or datos.get("profesor_id") or request.query_params.get("actor") or "docente")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)


class DispositivosView(VistaDispositivos):
    """GET: inventario con estado en vivo (CAP-054). POST: registro idempotente de la tableta (CAP-053, público)."""

    def get(self, request):
        solo_activos = not _bandera(request.query_params.get("todos"))
        return Response(cu.ListarDispositivos(servicios()).ejecutar(self._actor(request), solo_activos))

    def post(self, request):
        datos = _validar(s.DispositivoEntrada, request.data)
        dto, creado = cu.RegistrarDispositivo(servicios()).ejecutar(datos, actor=self._actor(request, datos).id)
        return Response(dto, status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class LatidoView(VistaDispositivos):
    """La tableta declara que sigue viva (público, sin sesión): le responde si está bloqueada o retirada."""

    permission_classes = [AllowAny]

    def post(self, request):
        datos = _validar(s.DispositivoEntrada, request.data)
        return Response(cu.RegistrarLatido(servicios()).ejecutar(datos))


class DispositivoView(VistaDispositivos):
    def get(self, request, pk: str):
        return Response(cu.VerDispositivo(servicios()).ejecutar(self._actor(request), pk))

    def patch(self, request, pk: str):
        cambios = _validar(s.DispositivoCambios, request.data, parcial=True)
        return Response(cu.ActualizarDispositivo(servicios()).ejecutar(self._actor(request, request.data), pk, cambios))


class DispositivoAccionView(VistaDispositivos):
    ACCIONES = {"bloquear": cu.BloquearDispositivo, "desbloquear": cu.DesbloquearDispositivo}

    def post(self, request, pk: str, accion: str):
        caso = self.ACCIONES.get(accion)
        if caso is None:
            return Response({"detail": f"Acción desconocida «{accion}».", "codigo": "datos_invalidos"}, status=400)
        datos = _validar(s.BloqueoEntrada, request.data)
        return Response(caso(servicios()).ejecutar(self._actor(request, request.data), pk, datos.get("motivo") or ""))
