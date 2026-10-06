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
from ..aplicacion import estudiantes as est
from ..aplicacion import padron as pad
from ..aplicacion import pin_maestro as pm
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from . import serializers as s
from .permisos import SesionRequerida, SesionSiSeExige, principal_de


def _validar(serializer_cls, datos, parcial: bool = False) -> dict:
    ser = serializer_cls(data=datos or {}, partial=parcial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


def _bandera(valor) -> bool:
    return str(valor or "").lower() in ("1", "true", "si", "sí", "yes")


def _dispositivo_de(request) -> tuple[str | None, str | None]:
    """El equipo que habla, de las dos formas en que lo conoce el aparato: su huella (`?dispositivo=`, la del login) y el id que aprendió del
    nodo (`X-Avacom-Dispositivo`, ya validado por el middleware de MOD-019)."""
    from audit import contexto  # módulo puro, sin modelos
    return (request.query_params.get("dispositivo") or None), contexto.actual().dispositivo_id


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
        return Response(cu.InstalarNodo(self.s).ejecutar(datos["organizacion"], datos["administrador"], datos["pin_maestro"]), status=201)


class SesionesView(VistaPublica):
    """POST = iniciar sesión (FUN-004 / FUN-005, público). GET = listar sesiones (con sesión y permiso)."""

    def post(self, request):
        datos = _validar(s.LoginEntrada, request.data)
        return Response(cu.AutenticarUsuario(self.s).ejecutar(
            datos["identificador"], datos["secreto"], datos["dispositivo"] or None, datos["rol"] or None,
            usuario_id=datos["usuario_id"] or None, pin_maestro=datos["pin_maestro"] or None))

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
                                                            q.get("estado") or None, q.get("origen") or None))

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


# ======================================================== padrón del aula (pantalla «Grupos» de OPS)


class VistaPadron(VistaAcceso):
    """Estudiantes y grupos para OPS. Con sesión, quien firma (con sus permisos); sin sesión sólo mientras el nodo no la exija (Q-34)."""

    permission_classes = [SesionSiSeExige]

    @staticmethod
    def actor(request):
        return principal_de(request)


class PadronView(VistaPadron):
    def get(self, request):
        return Response(pad.EstadoPadron(self.s).ejecutar(self.actor(request)))


class PadronPrepararView(VistaPadron):
    def post(self, request):
        return Response(pad.PrepararAulaDePrueba(self.s).ejecutar(), status=201)


class PadronGruposView(VistaPadron):
    def post(self, request):
        datos = _validar(s.GrupoPadronEntrada, request.data)
        return Response(pad.RegistrarGrupo(self.s).ejecutar(self.actor(request), datos), status=201)


class PadronEstudiantesView(VistaPadron):
    def post(self, request):
        datos = _validar(s.EstudiantePadronEntrada, request.data)
        return Response(pad.RegistrarEstudiante(self.s).ejecutar(self.actor(request), datos), status=201)


class PadronMatriculaView(VistaPadron):
    def post(self, request, pk: str):
        datos = _validar(s.MatriculaEntrada, request.data)
        salida = pad.MatricularEstudiante(self.s).ejecutar(self.actor(request), pk, datos["usuario_id"])
        return Response(salida, status=200 if salida.get("ya_estaba") else 201)

    def delete(self, request, pk: str, usuario_id: str):
        pad.RetirarEstudiante(self.s).ejecutar(self.actor(request), pk, usuario_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ================================================================ PIN maestro y profesores


class PinMaestroView(VistaAcceso):
    """RB-11 y RB-12. Nunca devuelve el PIN ni su huella (RN-04). No existe un «verificar»: el PIN se comprueba dentro de la operación que autoriza (D-A6)."""

    def get(self, request):
        return Response(pm.ConsultarEstadoPinMaestro(self.s).ejecutar(request.user))

    def put(self, request):
        datos = _validar(s.PinMaestroCambioEntrada, request.data)
        return Response(pm.CambiarPinMaestro(self.s).ejecutar(request.user, datos["pin_nuevo"]))


class DocentesRegistroView(VistaPublica):
    """RB-13: sin sesión; autoriza el PIN maestro. Es la excepción deliberada a «toda ruta declara permiso» (02 · Endpoints)."""

    def post(self, request):
        datos = _validar(s.DocenteRegistroEntrada, request.data)
        return Response(pm.RegistrarDocente(self.s).ejecutar(datos), status=201)


class DocentesRestablecerView(VistaPublica):
    """RB-14: sin sesión; autoriza el PIN maestro."""

    def post(self, request):
        datos = _validar(s.DocenteRestablecerEntrada, request.data)
        return Response(pm.RestablecerContrasenaDocente(self.s).ejecutar(datos))


class DocentesView(VistaAcceso):
    """RB-15: `?origen=PIN_MAESTRO` (por defecto). Requiere identity.user.read con alcance de organización."""

    def get(self, request):
        return Response(pm.ListarDocentesPorPinMaestro(self.s).ejecutar(request.user, request.query_params.get("origen") or "PIN_MAESTRO"))


# ========================================================= alumnos y visitantes (la tableta)


class AulaGruposView(VistaPublica):
    """RB-16: sin sesión (PAN-002), sólo desde un equipo registrado (BR-056). `?para=docente`: todos los grupos activos."""

    def get(self, request):
        huella, id_equipo = _dispositivo_de(request)
        return Response(est.ListarGruposDelAula(self.s).ejecutar(huella, id_equipo, para_docente=request.query_params.get("para") == "docente"))


class AulaEstudiantesView(VistaPublica):
    def get(self, request, pk: str):
        huella, id_equipo = _dispositivo_de(request)
        return Response(est.ListarEstudiantesDelGrupo(self.s).ejecutar(pk, huella, id_equipo))


class EstudiantesRegistroView(VistaPublica):
    """RB-17: el alumno crea su propio usuario."""

    def post(self, request):
        datos = _validar(s.EstudianteRegistroEntrada, request.data)
        from audit import contexto
        return Response(est.RegistrarEstudiante(self.s).ejecutar({**datos, "dispositivo_id": contexto.actual().dispositivo_id}), status=201)


class EstudiantePinView(VistaPublica):
    """RB-18: sólo si la cuenta está en «PIN pendiente»."""

    def post(self, request, pk: str):
        datos = _validar(s.EstudiantePinEntrada, request.data)
        from audit import contexto
        return Response(est.EstablecerPinAlumno(self.s).ejecutar(pk, datos["pin"], datos["dispositivo"] or None,
                                                                 contexto.actual().dispositivo_id))


class SesionVisitanteView(VistaPublica):
    """RB-19: entrar como visitante, sin sesión previa ni PIN."""

    def post(self, request):
        datos = _validar(s.VisitanteEntrada, request.data)
        from audit import contexto
        return Response(est.AbrirSesionVisitante(self.s).ejecutar(datos["dispositivo"] or None, contexto.actual().dispositivo_id,
                                                                  datos["grupo_id"] or None))


class VisitantesView(VistaAcceso):
    """RN-46: las visitas que están dentro ahora, con su tableta."""

    def get(self, request):
        return Response(est.ListarVisitantes(self.s).ejecutar(request.user))


class UsuarioConfirmarView(VistaAcceso):
    """RB-20."""

    def post(self, request, pk: str):
        return Response(est.ConfirmarEstudiante(self.s).ejecutar(request.user, pk))
