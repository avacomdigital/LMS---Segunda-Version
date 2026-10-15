"""
Rutas HTTP de MOD-021 (`/api/search/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM ni la biblioteca.

  GET  /api/search/             buscar por texto con filtros (search.query)
  GET  /api/search/filters/     las opciones de filtro válidas para quien consulta (search.query)
  GET  /api/search/status/      el estado del índice; el detalle sólo con search.reindex
  POST /api/search/open/        comprobar de nuevo el permiso sobre el recurso original antes de abrirlo (search.query)
  POST /api/search/reindex/     reconstruir el índice completo (search.reindex; exige que no haya una clase en curso)
  POST /api/search/sync/        aplicar ya lo que los módulos publicaron (search.reindex)
  GET·PUT /api/search/synonyms/ los sinónimos (search.reindex)

Contrato de degradación (el mismo del resto del backend): DatosInvalidos / ConsultaVacia / ConsultaInvalida → 400 · SinPermiso / FueraDeAlcance → 403 · NoEncontrado → 404 ·
SesionActiva / ReconstruccionEnCurso → 409 · CatalogoNoDisponible → 503.
Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor`.
"""
from __future__ import annotations

import logging

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import buscar as buscar_cu
from ..aplicacion import consultas as consultas_cu
from ..aplicacion import indexar as indexar_cu
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios

log = logging.getLogger("avacom.search")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


class VistaSearch(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorBusqueda):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare."""
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True, dispositivo_id=str(principal.dispositivo_id or ""), principal=principal)
        declarado = str((datos or {}).get("actor") or request.query_params.get("actor") or "")
        return Actor(id=declarado[:64], nivel=2, autenticado=False)


class BuscarView(VistaSearch):
    def get(self, request):
        return Response(buscar_cu.Buscar(servicios()).ejecutar(self._actor(request), {k: v for k, v in request.query_params.items()}))


class FiltrosView(VistaSearch):
    def get(self, request):
        return Response(consultas_cu.OpcionesDeFiltros(servicios()).ejecutar(self._actor(request)))


class EstadoView(VistaSearch):
    def get(self, request):
        return Response(consultas_cu.EstadoDelIndice(servicios()).ejecutar(self._actor(request)))


class AbrirView(VistaSearch):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(buscar_cu.Abrir(servicios()).ejecutar(self._actor(request, datos), datos))


class ReindexView(VistaSearch):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(indexar_cu.Reconstruir(servicios()).ejecutar(self._actor(request, datos)))


class SyncView(VistaSearch):
    def post(self, request):
        return Response(consultas_cu.PonerAlDia(servicios()).ejecutar(self._actor(request, _cuerpo(request))))


class SinonimosView(VistaSearch):
    def get(self, request):
        return Response(consultas_cu.Sinonimos(servicios()).listar(self._actor(request)))

    def put(self, request):
        datos = _cuerpo(request)
        return Response(consultas_cu.Sinonimos(servicios()).reemplazar(self._actor(request, datos), datos))
