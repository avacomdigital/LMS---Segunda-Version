"""
Rutas HTTP de MOD-019 (`/api/auditoria/`). Las vistas sólo traducen HTTP ↔ casos de uso.

Contrato de degradación (el mismo del resto del backend): sin sesión → 401 `sesion_requerida` · sin permiso → 403
`permiso_denegado` (y asiento de denegación, lo deja el middleware) · sin autorización de salida → 403
`autorizacion_requerida` · tramo con salto → 409 `cadena_con_salto` · acción fuera del catálogo → 422
`accion_desconocida` · datos mal formados → 400. PUT/PATCH/DELETE → 405 en todas las rutas (AC-081).
"""
from __future__ import annotations

from django.http import FileResponse
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionRequerida, principal_de

from .. import contexto
from ..aplicacion import consultar, estado, exportar, logs, tecnico, verificar
from ..dominio import catalogos, errores
from ..infraestructura.autorizacion import AutorizacionAcceso
from ..middleware import dispositivo_validado
from ..models import BitacoraTramo
from . import serializers as s

P_READ, P_EXPORT, P_DIAGNOSTICS = "audit.read", "audit.export", "diagnostics.read"


def _validar(serializer_cls, datos, **kwargs) -> dict:
    ser = serializer_cls(data=datos or {}, **kwargs)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


class VistaAuditoria(APIView):
    """Sólo lectura o POST de operación. Toda ruta exige sesión; la autorización real la decide la política de MOD-001."""

    permission_classes = [SesionRequerida]
    http_method_names = ["get", "post", "head", "options"]
    autorizacion = AutorizacionAcceso()

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorAuditoria):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos",
                             "errores": exc.detail}, status=400)
        if isinstance(exc, exceptions.MethodNotAllowed):
            return Response({"detail": "La bitácora sólo se agrega: nadie puede editarla ni borrarla.", "codigo": "bitacora_inmutable"},
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return super().handle_exception(exc)

    def exigir(self, request, permiso: str):
        principal = principal_de(request)
        self.autorizacion.exigir(principal, permiso)
        return principal

    def enmascarar(self, principal) -> bool:
        """BR-131: los valores de los asientos sensibles sólo se ven con una escalada vigente de audit.read."""
        return not self.autorizacion.tiene_escalada(principal, P_READ)


class AsientosView(VistaAuditoria):
    def get(self, request):
        principal = self.exigir(request, P_READ)
        datos = _validar(s.FiltrosConsulta, request.query_params.dict())
        limite, antes, despues = datos.pop("limite", None), datos.pop("antes", None), datos.pop("despues", None)
        return Response(consultar.listar(principal, datos, limite=limite, antes=antes, despues=despues, enmascarar=self.enmascarar(principal)))


class AsientoView(VistaAuditoria):
    def get(self, request, pk: str):
        principal = self.exigir(request, P_READ)
        return Response(consultar.detalle(principal, pk, enmascarar=self.enmascarar(principal)))


class CatalogoView(VistaAuditoria):
    def get(self, request):
        self.exigir(request, P_READ)
        return Response({"version": catalogos.VERSION_CATALOGO,
                         "modulos": [{"clave": m, "etiqueta": catalogos.ETIQUETAS_MODULO[m]} for m in catalogos.MODULOS if m != catalogos.M_PRUEBAS],
                         "acciones": catalogos.como_lista(),
                         "resultados": [{"clave": "ok", "etiqueta": "Correcto"}, {"clave": "denegado", "etiqueta": "Denegado"}, {"clave": "fallido", "etiqueta": "Fallido"}],
                         "origenes": ["api", "ws", "sistema", "instalador", "migracion", "prueba"]})


class TramosView(VistaAuditoria):
    def get(self, request):
        self.exigir(request, P_READ)
        return Response({"tramos": [estado.tramo_como_dict(t) for t in BitacoraTramo.objects.order_by("desde_secuencia")]})


class VerificarView(VistaAuditoria):
    def post(self, request):
        self.exigir(request, P_READ)
        todos = str(request.data.get("todos") if hasattr(request.data, "get") else "").lower() in ("1", "true", "si", "sí")
        return Response(verificar.verificar_cadena(todos=todos))


class EstadoView(VistaAuditoria):
    def get(self, request):
        self.exigir(request, P_READ)
        return Response(estado.estado())


class ExportarView(VistaAuditoria):
    """FUN-200 / BR-105 / ESC-03: exporta un tramo o un rango firmado. Exige audit.export Y autorización de salida vigente."""

    def post(self, request):
        principal = self.exigir(request, P_EXPORT)
        datos = _validar(s.ExportacionEntrada, request.data)
        return Response(exportar.exportar(principal, self.autorizacion, tramo_id=datos.get("tramo_id"), desde=datos.get("desde"),
                                          hasta=datos.get("hasta"), motivo_codigo=datos["motivo_codigo"], motivo_detalle=datos.get("motivo_detalle") or ""),
                        status=status.HTTP_201_CREATED)


class ExportacionesView(VistaAuditoria):
    def get(self, request):
        principal = self.exigir(request, P_EXPORT)
        return Response({"exportaciones": exportar.listar(), "motivos": exportar.motivos(),
                         "autorizacion_vigente": self.autorizacion.tiene_escalada(principal, P_EXPORT)})


class DescargarExportacionView(VistaAuditoria):
    def get(self, request, pk: str):
        self.exigir(request, P_EXPORT)
        ruta, _fila = exportar.archivo_de(pk)
        respuesta = FileResponse(ruta.open("rb"), content_type="application/x-ndjson", as_attachment=True, filename=ruta.name)
        return respuesta


class TecnicoAccesosView(VistaAuditoria):
    """019-10: acciones y denegaciones del rol técnico, y el indicador «sin acceso a datos personales en el periodo»."""

    def get(self, request):
        principal = self.exigir(request, P_READ)
        datos = _validar(s.FiltrosConsulta, request.query_params.dict())
        return Response(tecnico.accesos(principal, desde=datos.get("desde"), hasta=datos.get("hasta"), limite=datos.get("limite") or 100,
                                        antes=datos.get("antes"), enmascarar=self.enmascarar(principal)))


# ---------------------------------------------------------------------------- logs

class LogsView(VistaAuditoria):
    """Últimas líneas de los logs por canal, nivel, app, desde y corr. Sólo lectura, sin datos personales (§2.6)."""

    def get(self, request):
        self.exigir(request, P_DIAGNOSTICS)
        datos = _validar(s.FiltrosLogs, request.query_params.dict())
        ultimos = datos.pop("ultimos", None)
        return Response(logs.leer(datos, ultimos=ultimos))


class LogsClientesView(VistaAuditoria):
    """Recibe renglones WARNING+ de OPS/Student (§2.4). Sesión o dispositivo admitido (cabecera o cuerpo); no toca la bitácora."""

    permission_classes = [AllowAny]

    def post(self, request):
        datos = _validar(s.EntregaClientes, request.data)
        dispositivo_id = contexto.actual().dispositivo_id or dispositivo_validado(datos.get("dispositivo_id"))
        if dispositivo_id is None and principal_de(request) is not None:
            dispositivo_id = getattr(principal_de(request), "dispositivo_id", None) or dispositivo_validado(datos.get("dispositivo_id"))
        if dispositivo_id is None and principal_de(request) is None:
            raise errores.SinPermiso("La entrega de logs exige un equipo registrado y activo (X-Avacom-Dispositivo) o una sesión.",
                                     permiso="logs.clientes")
        if dispositivo_id is None:
            # Sesión sin equipo conocido (por ejemplo OPS en el nodo): se acepta y se atribuye al usuario, no a un aparato inventado.
            dispositivo_id = f"sesion:{principal_de(request).usuario_id}"
        return Response(logs.recibir_de_clientes(dispositivo_id, datos["app"], datos.get("version_app") or "", datos["renglones"]),
                        status=status.HTTP_202_ACCEPTED)
