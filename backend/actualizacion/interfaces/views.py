"""
Rutas HTTP de MOD-017 (`/api/actualizacion/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM.

  GET  estado/                           update.read            versión, módulos instalados (versión, datos, contrato, serie), lo en curso, lo programado, lo revertible, espacio
  GET  paquetes/                         update.read            los `.avupd` encontrados en las unidades y la carpeta de entrada (candidatos, con id opaco) y los ya importados con su estado
  POST paquetes/importar/                update.package.import  `{candidato}`: importa y verifica (FUN-180, FUN-181). 201 con la ficha; 422 `firma_invalida` / `paquete_invalido` con `motivo`
  GET  paquetes/<id>/                    update.read            la ficha: qué cambia, peso, compatibilidad, ventana, reversión, historial
  POST paquetes/<id>/programar/          update.schedule        `{desde, hasta}` en ms del reloj del nodo (FUN-182)
  POST paquetes/<id>/desprogramar/       update.schedule        cancela la ventana
  POST paquetes/<id>/aplicar/            update.apply           202 con la orden escrita para el Host (FUN-184); 409 `sesion_activa` con una clase (FUN-183)
  POST paquetes/<id>/revertir/           update.apply           `{nota}`: 202 con la orden de reversión; dentro de 14 días (P-09)
  GET  historial/?limite=&tipo=          update.read            el historial del nodo (FUN-187)

Contrato de errores (el mismo del resto del backend, `{"detail", "codigo", …}`):
  DatosInvalidos → 400 · SinPermiso → 403 · NoEncontrado → 404 · Conflicto y sus hijos → 409 (`contrato_incompatible` con `incompatibilidades`, `espacio_insuficiente`, `sesion_activa`,
  `ya_aplicado`, `serie_menor`, `fuera_de_plazo_reversion`, `estado_invalido`, `actualizacion_en_curso`) · PaqueteRechazado → 422 (`firma_invalida` o `paquete_invalido`, con `motivo`).

Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor`.
"""
from __future__ import annotations

import logging

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import acciones
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios

log = logging.getLogger("avacom.actualizacion")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


class VistaActualizacion(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorActualizacion):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         dispositivo_id=str(principal.dispositivo_id or ""), principal=principal, rol=str(principal.rol_codigo or ""))
        actor_id = str(datos.get("actor") or request.query_params.get("actor") or "")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)


class EstadoView(VistaActualizacion):
    def get(self, request):
        return Response(acciones.ConsultarEstado(servicios()).ejecutar(self._actor(request)))


class PaquetesView(VistaActualizacion):
    def get(self, request):
        return Response(acciones.ListarPaquetes(servicios()).ejecutar(self._actor(request)))


class ImportarView(VistaActualizacion):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(acciones.Importar(servicios()).ejecutar(self._actor(request, datos), datos.get("candidato")), status=status.HTTP_201_CREATED)


class PaqueteView(VistaActualizacion):
    def get(self, request, paquete_id: str):
        return Response(acciones.VerPaquete(servicios()).ejecutar(self._actor(request), paquete_id))


class ProgramarView(VistaActualizacion):
    def post(self, request, paquete_id: str):
        datos = _cuerpo(request)
        return Response(acciones.Programar(servicios()).ejecutar(self._actor(request, datos), paquete_id, datos.get("desde"), datos.get("hasta")))


class DesprogramarView(VistaActualizacion):
    def post(self, request, paquete_id: str):
        datos = _cuerpo(request)
        return Response(acciones.Desprogramar(servicios()).ejecutar(self._actor(request, datos), paquete_id))


class AplicarView(VistaActualizacion):
    def post(self, request, paquete_id: str):
        datos = _cuerpo(request)
        return Response(acciones.Aplicar(servicios()).ejecutar(self._actor(request, datos), paquete_id), status=status.HTTP_202_ACCEPTED)


class RevertirView(VistaActualizacion):
    def post(self, request, paquete_id: str):
        datos = _cuerpo(request)
        return Response(acciones.Revertir(servicios()).ejecutar(self._actor(request, datos), paquete_id, datos.get("nota")), status=status.HTTP_202_ACCEPTED)


class HistorialView(VistaActualizacion):
    def get(self, request):
        q = request.query_params
        try:
            limite = int(q.get("limite") or 100)
        except ValueError:
            raise errores.DatosInvalidos("`limite` debe ser un número.") from None
        return Response(acciones.ConsultarHistorial(servicios()).ejecutar(self._actor(request), limite, q.getlist("tipo")))
