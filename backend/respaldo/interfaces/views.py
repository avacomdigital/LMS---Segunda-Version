"""
Rutas HTTP de MOD-016 (`/api/respaldo/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM.

  GET  estado/                           backup.read     el último respaldo verificado, los días sin respaldo, lo que está en marcha, la programación, la custodia, las unidades
  GET  respaldos/                        backup.read     los respaldos con su estado derivado
  GET  respaldos/<id>/                   backup.read     la ficha con su historial
  GET  respaldos/<id>/constancia/        backup.read     la constancia para el personal administrativo (`?formato=txt` la descarga como archivo)
  GET  resumen/                          backup.read     el historial para Excel (`?formato=csv` lo descarga)
  GET  informes/ · informes/<nombre>/    backup.read     los archivos que el nodo dejó para el personal administrativo
  GET  destinos/                         backup.read     unidades extraíbles y respaldos encontrados en ellas (ids opacos)
  POST respaldos/ahora/                  backup.run      `{tipo?}` «Respaldar ahora» (FUN-170, FUN-171). 201 con la ficha
  POST respaldos/<id>/verificar/         backup.verify   `{custodia?}` (FUN-173)
  POST respaldos/<id>/exportar/          backup.export   `{unidad, pase}` (FUN-176) · pase de soporte de AVACOM
  POST programacion/                     backup.schedule `{activo?, hora_min?, dias?, completo_cada_dias?, retencion?, incluir_reinstalable?, destino?}` (FUN-169)
  POST custodia/emitir/                  backup.schedule `{reemplazar?}` el código de custodia de la institución: se muestra UNA vez (BR-102)
  POST restaurar/                        backup.restore  `{respaldo_id | candidato, motivo, nota?, custodia?, pase}` (FUN-174) · pase de soporte de AVACOM
  POST restaurar/modulo/                 backup.restore.module  `{modulo, pase}` (FUN-175)

Contrato de errores (el mismo del resto del backend, `{"detail", "codigo", …}`):
  DatosInvalidos → 400 · SinPermiso / PaseRequerido / PaseInvalido → 403 · NoEncontrado → 404 · Conflicto y sus hijos → 409 (`sesion_activa`, `respaldo_en_curso`, `espacio_insuficiente`,
  `sin_respaldo_previo`, `respaldo_fallido`, `restauracion_abortada` con `motivo`, `custodia_requerida`, `custodia_ya_emitida`, `modulo_sin_restauracion_aislada`, `estado_invalido`)
  · RespaldoRechazado → 422 (`respaldo_invalido` / `clave_no_disponible`, con `motivo`).

Quién actúa: SÓLO quien trae sesión. A diferencia de los módulos del prototipo (Q-34), aquí no hay actor «declarado»: un respaldo nunca se pide de forma anónima.
"""
from __future__ import annotations

import logging

from django.http import HttpResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import acciones
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios

log = logging.getLogger("avacom.respaldo")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


def _archivo(texto: str, nombre: str, tipo: str) -> HttpResponse:
    r = HttpResponse(texto.encode("utf-8-sig" if tipo == "text/csv" else "utf-8"), content_type=f"{tipo}; charset=utf-8")
    r["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return r


class VistaRespaldo(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorRespaldo):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    @staticmethod
    def _actor(request) -> Actor:
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True, dispositivo_id=str(principal.dispositivo_id or ""), principal=principal,
                         rol=str(principal.rol_codigo or ""))
        return Actor(id="anonimo", nivel=0, autenticado=False)


class EstadoView(VistaRespaldo):
    def get(self, request):
        return Response(acciones.ConsultarEstado(servicios()).ejecutar(self._actor(request)))


class RespaldosView(VistaRespaldo):
    def get(self, request):
        try:
            limite = int(request.query_params.get("limite") or 100)
        except ValueError:
            raise errores.DatosInvalidos("`limite` debe ser un número.") from None
        return Response(acciones.ListarRespaldos(servicios()).ejecutar(self._actor(request), limite))


class RespaldoView(VistaRespaldo):
    def get(self, request, respaldo_id: str):
        return Response(acciones.VerRespaldo(servicios()).ejecutar(self._actor(request), respaldo_id))


class ConstanciaView(VistaRespaldo):
    def get(self, request, respaldo_id: str):
        r = acciones.ObtenerConstancia(servicios()).ejecutar(self._actor(request), respaldo_id)
        if request.query_params.get("formato") == "txt":
            return _archivo(r["texto"], r["nombre"], "text/plain")
        return Response(r)


class ResumenView(VistaRespaldo):
    def get(self, request):
        r = acciones.ObtenerResumen(servicios()).ejecutar(self._actor(request))
        if request.query_params.get("formato") == "csv":
            return _archivo(r["texto"], r["nombre"], "text/csv")
        return Response(r)


class InformesView(VistaRespaldo):
    def get(self, request):
        return Response({"informes": acciones.ConsultarEstado(servicios()).ejecutar(self._actor(request))["informes"]})


class InformeView(VistaRespaldo):
    def get(self, request, nombre: str):
        r = acciones.LeerInforme(servicios()).ejecutar(self._actor(request), nombre)
        if request.query_params.get("formato") in ("txt", "csv"):
            return _archivo(r["texto"], r["nombre"], "text/csv" if nombre.endswith(".csv") else "text/plain")
        return Response(r)


class DestinosView(VistaRespaldo):
    def get(self, request):
        return Response(acciones.ListarDestinos(servicios()).ejecutar(self._actor(request)))


class AhoraView(VistaRespaldo):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(acciones.RespaldarAhora(servicios()).ejecutar(self._actor(request), str(datos.get("tipo") or "completo")), status=status.HTTP_201_CREATED)


class VerificarView(VistaRespaldo):
    def post(self, request, respaldo_id: str):
        datos = _cuerpo(request)
        return Response(acciones.Verificar(servicios()).ejecutar(self._actor(request), respaldo_id, str(datos["custodia"]) if datos.get("custodia") else None))


class ExportarView(VistaRespaldo):
    def post(self, request, respaldo_id: str):
        datos = _cuerpo(request)
        return Response(acciones.Exportar(servicios()).ejecutar(self._actor(request), respaldo_id, str(datos.get("unidad") or ""), datos.get("pase")))


class ProgramacionView(VistaRespaldo):
    def post(self, request):
        return Response(acciones.Programar(servicios()).ejecutar(self._actor(request), _cuerpo(request)))


class CustodiaView(VistaRespaldo):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(acciones.EmitirCustodia(servicios()).ejecutar(self._actor(request), bool(datos.get("reemplazar"))), status=status.HTTP_201_CREATED)


class RestaurarView(VistaRespaldo):
    def post(self, request):
        return Response(acciones.Restaurar(servicios()).ejecutar(self._actor(request), _cuerpo(request)))


class RestaurarModuloView(VistaRespaldo):
    def post(self, request):
        return Response(acciones.RestaurarModulo(servicios()).ejecutar(self._actor(request), _cuerpo(request)))
