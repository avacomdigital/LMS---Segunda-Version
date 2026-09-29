"""
APIViews del módulo de acceso. Sólo traducen HTTP ↔ casos de uso: validan la forma
con serializers, llaman al caso de uso y convierten errores de dominio en códigos.
"""
from __future__ import annotations

from django.conf import settings
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..aplicacion import casos_uso as cu
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from . import serializers as s
from .permisos import SesionRequerida, principal_de


def _validar(serializer_cls, datos, parcial: bool = False) -> dict:
    ser = serializer_cls(data=datos or {}, partial=parcial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


def _bandera(valor) -> bool:
    return str(valor or "").lower() in ("1", "true", "si", "sí", "yes")


class VistaAcceso(APIView):
    """Base: convierte errores de dominio en la forma {detail, codigo, ...} del contrato."""

    permission_classes = [SesionRequerida]

    @property
    def s(self):
        return servicios()

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorAcceso):
            cuerpo = {"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}
            respuesta = Response(cuerpo, status=exc.http)
            if exc.http == 401:
                respuesta["WWW-Authenticate"] = "Bearer"
            return respuesta
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos",
                             "errores": exc.detail}, status=400)
        if isinstance(exc, exceptions.NotAuthenticated):
            return Response({"detail": "Hace falta iniciar sesión.", "codigo": "sesion_requerida"}, status=401,
                            headers={"WWW-Authenticate": "Bearer"})
        if isinstance(exc, exceptions.AuthenticationFailed):
            detalle = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail), "codigo": "sesion_invalida"}
            return Response(detalle, status=401, headers={"WWW-Authenticate": "Bearer"})
        if isinstance(exc, exceptions.PermissionDenied):
            detalle = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail), "codigo": "sin_permiso"}
            return Response(detalle, status=403)
        return super().handle_exception(exc)


class VistaPublica(VistaAcceso):
    permission_classes = [AllowAny]


def _exigir_principal(request):
    principal = principal_de(request)
    if principal is None:
        raise errores.SesionRequerida()
    return principal


# ============================================================ sin sesión


class ConfiguracionView(VistaPublica):
    def get(self, request):
        cuerpo = cu.ConsultarConfiguracion(self.s).ejecutar()
        # Q-34: si el nodo exige sesión, OPS y Student muestran su pantalla de acceso con credenciales; si no, entran como hasta ahora.
        cuerpo["sesion_obligatoria"] = bool(settings.AVACOM_LMS_EXIGIR_SESION)
        return Response(cuerpo)


class InstalacionView(VistaPublica):
    def post(self, request):
        datos = _validar(s.InstalacionEntrada, request.data)
        return Response(cu.InstalarNodo(self.s).ejecutar(datos["organizacion"], datos["administrador"]), status=201)


class SesionesView(VistaPublica):
    """POST = iniciar sesión (FUN-004 / FUN-005, público). GET = listar sesiones (con sesión y permiso)."""

    def post(self, request):
        datos = _validar(s.LoginEntrada, request.data)
        return Response(cu.AutenticarUsuario(self.s).ejecutar(datos["identificador"], datos["secreto"],
                                                               datos["dispositivo"] or None, datos["rol"] or None))

    def get(self, request):
        principal = _exigir_principal(request)
        return Response(cu.ListarSesiones(self.s).ejecutar(
            principal, request.query_params.get("usuario") or None,
            solo_activas=not _bandera(request.query_params.get("todas"))))


class CanjeView(VistaPublica):
    def post(self, request):
        datos = _validar(s.CanjeEntrada, request.data)
        return Response(cu.CanjearAccesoTemporal(self.s).ejecutar(
            datos["dispositivo"] or None, codigo=datos["codigo"] or None,
            grant_id=datos["grant_id"] or None, token=datos["token"] or None))


# ======================================================== identidad propia


class YoView(VistaAcceso):
    def get(self, request):
        return Response(cu.ConsultarIdentidad(self.s).ejecutar(request.user))


class CredencialPropiaView(VistaAcceso):
    def put(self, request):
        datos = _validar(s.CambioCredencialEntrada, request.data)
        return Response(cu.CambiarCredencialPropia(self.s).ejecutar(request.user, datos["secreto_actual"], datos["secreto_nuevo"]))


class SesionActualView(VistaAcceso):
    def delete(self, request):
        cu.RevocarSesion(self.s).ejecutar(request.user, None)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SesionView(VistaAcceso):
    def delete(self, request, pk: str):
        cu.RevocarSesion(self.s).ejecutar(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ================================================================ usuarios


class UsuariosView(VistaAcceso):
    def get(self, request):
        q = request.query_params
        return Response(cu.ListarUsuarios(self.s).ejecutar(request.user, q.get("grupo") or None, q.get("rol") or None,
                                                            q.get("estado") or None))

    def post(self, request):
        datos = _validar(s.UsuarioEntrada, request.data)
        return Response(cu.CrearUsuario(self.s).ejecutar(request.user, datos), status=201)


class ImportarUsuariosView(VistaAcceso):
    """FUN-003: carga masiva desde archivo delimitado."""

    def post(self, request):
        datos = _validar(s.ImportacionEntrada, request.data)
        return Response(cu.ImportarUsuarios(self.s).ejecutar(
            request.user, contenido=datos["contenido"] or None, filas=datos["filas"] or None,
            delimitador=datos["delimitador"], grupo_id=datos["grupo_id"] or None))


class UsuarioView(VistaAcceso):
    def get(self, request, pk: str):
        return Response(cu.VerUsuario(self.s).ejecutar(request.user, pk))

    def patch(self, request, pk: str):
        cambios = _validar(s.UsuarioCambios, request.data, parcial=True)
        return Response(cu.ActualizarUsuario(self.s).ejecutar(request.user, pk, cambios))


class UsuarioVincularView(VistaAcceso):
    def post(self, request, pk: str):
        datos = _validar(s.VinculacionEntrada, request.data)
        return Response(cu.VincularUsuarioProvisional(self.s).ejecutar(request.user, pk, datos["usuario_definitivo_id"]))


class UsuarioRolesView(VistaAcceso):
    """FUN-002: asignaciones de rol con alcance y vigencia."""

    def get(self, request, pk: str):
        return Response(cu.VerUsuario(self.s).ejecutar(request.user, pk)["roles"])

    def post(self, request, pk: str):
        datos = _validar(s.RolAsignacion, request.data)
        return Response(cu.AsignarRol(self.s).ejecutar(
            request.user, pk, datos["rol"], datos["alcance_tipo"], datos.get("alcance_id"),
            datos.get("vigente_hasta"), datos["principal"]), status=201)

    def put(self, request, pk: str):
        """Compatibilidad: PUT fija el rol principal con alcance de organización."""
        datos = _validar(s.RolAsignacion, request.data)
        return Response(cu.AsignarRol(self.s).ejecutar(
            request.user, pk, datos["rol"], datos["alcance_tipo"], datos.get("alcance_id"),
            datos.get("vigente_hasta"), True))


class UsuarioRolView(VistaAcceso):
    def delete(self, request, pk: str, asignacion_id: str):
        cu.RevocarRolAsignado(self.s).ejecutar(request.user, pk, asignacion_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsuarioEscaladasView(VistaAcceso):
    def get(self, request, pk: str):
        return Response(cu.VerUsuario(self.s).ejecutar(request.user, pk)["escaladas"])

    def post(self, request, pk: str):
        datos = _validar(s.EscaladaEntrada, request.data)
        return Response(cu.OtorgarEscalada(self.s).ejecutar(request.user, pk, datos["permiso"], datos["alcance"],
                                                             datos["motivo"], datos["vigente_hasta"]), status=201)


class UsuarioEscaladaView(VistaAcceso):
    def delete(self, request, pk: str, permiso: str):
        cu.RevocarEscalada(self.s).ejecutar(request.user, pk, permiso)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsuarioSesionesView(VistaAcceso):
    """FUN-010: revocar todas las sesiones activas de un usuario."""

    def delete(self, request, pk: str):
        return Response(cu.RevocarSesionesDeUsuario(self.s).ejecutar(request.user, pk))


class RestablecerCredencialView(VistaAcceso):
    def post(self, request, pk: str):
        datos = _validar(s.RestablecerEntrada, request.data)
        return Response(cu.RestablecerCredencial(self.s).ejecutar(request.user, pk, datos["secreto"] or None))


class DesbloquearView(VistaAcceso):
    def post(self, request, pk: str):
        return Response(cu.DesbloquearUsuario(self.s).ejecutar(request.user, pk))


# ========================================================= acceso temporal


class AutorizacionesView(VistaAcceso):
    def get(self, request):
        q = request.query_params
        return Response(cu.ListarAutorizaciones(self.s).ejecutar(request.user, q.get("usuario") or None, _bandera(q.get("vigentes"))))

    def post(self, request):
        datos = _validar(s.AutorizacionEntrada, request.data)
        return Response(cu.OtorgarAccesoTemporal(self.s).ejecutar(
            request.user, datos["usuario_id"], datos["tipo"], datos["motivo"], datos["dispositivo_id"] or None,
            datos["evaluacion_ref"] or None, datos["minutos"]), status=201)


class AutorizacionView(VistaAcceso):
    def delete(self, request, pk: str):
        cu.RevocarAccesoTemporal(self.s).ejecutar(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


# =============================================================== catálogos


class RolesView(VistaAcceso):
    def get(self, request):
        return Response(cu.ListarRoles(self.s).ejecutar(request.user))

    def post(self, request):
        datos = _validar(s.RolEntrada, request.data)
        return Response(cu.CrearRol(self.s).ejecutar(request.user, datos), status=201)


class PermisosView(VistaAcceso):
    def get(self, request):
        return Response(cu.ListarPermisos(self.s).ejecutar(request.user))


class PoliticasView(VistaAcceso):
    def get(self, request):
        return Response(cu.ListarPoliticas(self.s).ejecutar(request.user))


class PoliticaView(VistaAcceso):
    def put(self, request, perfil: str):
        cambios = _validar(s.PoliticaCambios, request.data, parcial=True)
        return Response(cu.ConfigurarPolitica(self.s).ejecutar(request.user, perfil, cambios,
                                                                nivel=request.query_params.get("nivel") or None))


class GruposView(VistaAcceso):
    def get(self, request):
        return Response(cu.ListarGrupos(self.s).ejecutar(request.user))

    def post(self, request):
        datos = _validar(s.GrupoEntrada, request.data)
        return Response(cu.CrearGrupo(self.s).ejecutar(request.user, datos), status=201)


class GrupoView(VistaAcceso):
    def get(self, request, pk: str):
        return Response(cu.VerGrupo(self.s).ejecutar(request.user, pk))

    def patch(self, request, pk: str):
        cambios = _validar(s.GrupoCambios, request.data, parcial=True)
        return Response(cu.ActualizarGrupo(self.s).ejecutar(request.user, pk, cambios))


class MiembrosView(VistaAcceso):
    def post(self, request, pk: str):
        datos = _validar(s.MiembroEntrada, request.data)
        salida = cu.AgregarMiembro(self.s).ejecutar(request.user, pk, datos["usuario_id"], datos["papel"])
        return Response(salida, status=200 if salida.get("ya_estaba") else 201)


class MiembroView(VistaAcceso):
    def delete(self, request, pk: str, usuario_id: str):
        cu.RetirarMiembro(self.s).ejecutar(request.user, pk, usuario_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
