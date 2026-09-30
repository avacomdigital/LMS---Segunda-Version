"""
Rutas HTTP de MOD-008 (`/api/modo-estudio/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM ni la biblioteca.

Contrato de degradación (el mismo del resto del backend, §4 del contrato):
  DatosInvalidos / FaltaDispositivo / FaltaAlumno → 400 · SinPermiso (también AlumnoDesconocido) / NoEsElTitular / DispositivoBloqueado /
  DispositivoInactivo / DescargaDenegada → 403 · NoEncontrado → 404 · NodoNoInstalado / AsignacionCerrada / BloquesPendientes / PracticaTerminada /
  HuellaInvalida → 409 · PaqueteVencido → 410 · FuenteNoDisponible → 503 `{disponible:false, detail, codigo, sugerencia}`. Los errores de `acceso` (sesión,
  políticas) conservan su forma.

Al aparato se le identifica con su huella `dispositivo` (= `identificador_hw`): en `?dispositivo=` (GET, DELETE) o en el cuerpo (POST, PATCH). Sin
`dispositivo` ni sesión de alumno: 400 `falta_dispositivo`. Sin sesión (Q-34) el alumno es el que la tableta declara con `alumno_id` (cuerpo o
`?alumno_id=`) en CUALQUIER aparato, compartido o asignado (D-15, «identidad declarada»); sin declararlo, el dueño de un aparato asignado. El profesor
declara `actor`, como en el aula.
"""
from __future__ import annotations

from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de
from classroom_engine.interfaces.views import _respuesta_bytes

from ..aplicacion import asignaciones as asignaciones_cu
from ..aplicacion import lecciones as lecciones_cu
from ..aplicacion import paquetes as paquetes_cu
from ..aplicacion import practica as practica_cu
from ..aplicacion import sesion as sesion_cu
from ..aplicacion import sincronizacion as sincronizacion_cu
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from . import serializers as s


def _validar(serializer_cls, datos, parcial: bool = False) -> dict:
    ser = serializer_cls(data=datos if isinstance(datos, dict) else {}, partial=parcial)
    ser.is_valid(raise_exception=True)
    return dict(ser.validated_data)


class VistaEstudio(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.FuenteNoDisponible):
            return Response({"disponible": False, "detail": exc.detalle, "codigo": exc.codigo, "sugerencia": exc.sugerencia, **exc.extra},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if isinstance(exc, errores.ErrorEstudio):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    # ------------------------------------------------------------------------- quién actúa
    @staticmethod
    def _huella(request, datos: dict | None = None) -> str:
        return str((datos or {}).get("dispositivo") or request.query_params.get("dispositivo") or "").strip()

    @staticmethod
    def _declarado(request, datos: dict | None = None) -> str:
        """El `alumno_id` que declara la tableta sin sesión (D-3, D-15): en cualquier aparato manda lo declarado y, si no se declara nada,
        un aparato asignado toma a su dueño."""
        return str((datos or {}).get("alumno_id") or request.query_params.get("alumno_id") or "").strip()

    def _cuerpo(self, request, serializer, parcial: bool = False) -> dict:
        """El cuerpo validado, con el aparato y la persona declarada completados desde la URL si el cuerpo no los trae."""
        datos = _validar(serializer, request.data, parcial)
        datos["dispositivo"] = datos.get("dispositivo") or self._huella(request)
        datos["alumno_id"] = datos.get("alumno_id") or self._declarado(request)
        return datos

    def _alumno(self, request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), el alumno lo decide el aparato (`resolver_contexto`): aquí sólo se declara."""
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True,
                         dispositivo_id=str(principal.dispositivo_id or ""), principal=principal)
        return Actor(id=self._declarado(request, datos)[:64], nivel=1, autenticado=False)

    @staticmethod
    def _docente(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare, como en el aula."""
        principal = principal_de(request)
        datos = datos or {}
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         principal=principal)
        actor_id = str(datos.get("actor") or datos.get("profesor_id") or request.query_params.get("actor") or "docente")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)


def _con_etag(respuesta, archivo: dict):
    respuesta["ETag"] = f"\"{archivo['sha256']}\""
    return respuesta


# ============================================================================= estado y sesión de estudio

class EstadoView(VistaEstudio):
    """La pregunta del menú de Student: ¿está el modo de estudio disponible en esta tableta? NUNCA falla."""

    def get(self, request):
        return Response(sesion_cu.ConsultarEstado(servicios()).ejecutar(self._alumno(request), self._huella(request), self._declarado(request)))


class EstudiantesView(VistaEstudio):
    """Los nombres de la pantalla «¿Quién eres?» (D-15): se pregunta ANTES de saber quién es la persona, así que no pide sesión ni permiso."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(sesion_cu.ListarEstudiantes(servicios()).ejecutar(self._alumno(request), self._huella(request)))


class SesionView(VistaEstudio):
    def post(self, request):
        datos = self._cuerpo(request, s.SesionEntrada)
        return Response(sesion_cu.AbrirSesion(servicios()).ejecutar(self._alumno(request, datos), datos))


class SesionCerrarView(VistaEstudio):
    def post(self, request):
        datos = self._cuerpo(request, s.CierreSesionEntrada)
        return Response(sesion_cu.CerrarSesion(servicios()).ejecutar(self._alumno(request, datos), datos))


class SesionLimpiezaView(VistaEstudio):
    """El aparato avisa de que terminó de borrar lo local DESPUÉS de cerrar la sesión: ya no hay sesión, así que no la exige (FUN-090)."""

    permission_classes = [AllowAny]

    def post(self, request):
        datos = self._cuerpo(request, s.LimpiezaEntrada)
        return Response(sesion_cu.ReintentarLimpieza(servicios()).ejecutar(self._alumno(request, datos), datos))


# ============================================================================== pendientes y lección (alumno)

class AsignacionesView(VistaEstudio):
    def get(self, request):
        return Response(asignaciones_cu.ListarAsignaciones(servicios()).ejecutar(
            self._alumno(request), self._huella(request), self._declarado(request)))


class AsignacionView(VistaEstudio):
    def get(self, request, asignacion_id: str):
        return Response(asignaciones_cu.VerAsignacion(servicios()).ejecutar(
            self._alumno(request), asignacion_id, self._huella(request), self._declarado(request)))


class LeccionView(VistaEstudio):
    def get(self, request, asignacion_id: str):
        return Response(lecciones_cu.AbrirLeccion(servicios()).ejecutar(
            self._alumno(request), asignacion_id, self._huella(request), self._declarado(request)))


class MedioDeAsignacionView(VistaEstudio):
    """Bytes de un medio de la lección asignada (con `Range`), sólo si pertenece a ella y la asignación le alcanza al alumno."""

    def _servir(self, request, asignacion_id: str, media_ref: str, ruta: str | None, metodo: str):
        medio = lecciones_cu.AbrirMedioDeLeccion(servicios()).ejecutar(
            self._alumno(request), asignacion_id, media_ref, ruta, request.headers.get("Range"), metodo,
            self._huella(request), self._declarado(request))
        return _respuesta_bytes(request, medio, metodo)

    def get(self, request, asignacion_id: str, media_ref: str, ruta: str | None = None):
        return self._servir(request, asignacion_id, media_ref, ruta, "GET")

    def head(self, request, asignacion_id: str, media_ref: str, ruta: str | None = None):
        return self._servir(request, asignacion_id, media_ref, ruta, "HEAD")


class ProgresoView(VistaEstudio):
    def patch(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.ProgresoEntrada, parcial=True)
        return Response(lecciones_cu.RegistrarProgreso(servicios()).ejecutar(self._alumno(request, datos), asignacion_id, datos))


class CompletarView(VistaEstudio):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.AparatoEntrada)
        return Response(lecciones_cu.CompletarLeccion(servicios()).ejecutar(self._alumno(request, datos), asignacion_id, datos))


# ================================================================================ práctica autocalificable

class PracticaView(VistaEstudio):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.PracticaEntrada)
        return Response(practica_cu.AbrirPractica(servicios()).ejecutar(self._alumno(request, datos), asignacion_id, datos))


class PracticaRespuestasView(VistaEstudio):
    def post(self, request, practica_id: str):
        datos = self._cuerpo(request, s.RespuestasEntrada)
        return Response(practica_cu.ResponderPractica(servicios()).ejecutar(self._alumno(request, datos), practica_id, datos))


class PracticaTerminarView(VistaEstudio):
    def post(self, request, practica_id: str):
        datos = self._cuerpo(request, s.AparatoEntrada)
        return Response(practica_cu.TerminarPractica(servicios()).ejecutar(self._alumno(request, datos), practica_id, datos))


# ======================================================================================= paquete de estudio

class PaquetesView(VistaEstudio):
    def get(self, request):
        return Response(paquetes_cu.ListarPaquetes(servicios()).ejecutar(self._alumno(request), self._huella(request), self._declarado(request)))

    def post(self, request):
        datos = self._cuerpo(request, s.PaqueteEntrada)
        paquete, creado = paquetes_cu.SolicitarPaquete(servicios()).ejecutar(self._alumno(request, datos), datos)
        return Response(paquete, status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class PaqueteView(VistaEstudio):
    def get(self, request, paquete_id: str):
        return Response(paquetes_cu.VerPaquete(servicios()).ejecutar(
            self._alumno(request), paquete_id, self._huella(request), self._declarado(request)))

    def delete(self, request, paquete_id: str):
        cuerpo = request.data if isinstance(request.data, dict) else {}          # el contrato lo pide en `?dispositivo=`; un cuerpo también vale
        return Response(paquetes_cu.RetirarPaquete(servicios()).ejecutar(
            self._alumno(request, cuerpo), paquete_id, self._huella(request, cuerpo), self._declarado(request, cuerpo)))


class ManifiestoView(VistaEstudio):
    def get(self, request, paquete_id: str):
        return Response(paquetes_cu.ObtenerManifiesto(servicios()).ejecutar(
            self._alumno(request), paquete_id, self._huella(request), self._declarado(request)))


class ArchivoDePaqueteView(VistaEstudio):
    """Bytes de un medio del paquete, reanudable (`Range`). El `ETag` es el `sha256` del archivo."""

    def _servir(self, request, paquete_id: str, media_ref: str, metodo: str):
        medio, archivo = paquetes_cu.AbrirArchivoDePaquete(servicios()).ejecutar(
            self._alumno(request), paquete_id, media_ref, request.headers.get("Range"), metodo, self._huella(request), self._declarado(request))
        return _con_etag(_respuesta_bytes(request, medio, metodo), archivo)

    def get(self, request, paquete_id: str, media_ref: str):
        return self._servir(request, paquete_id, media_ref, "GET")

    def head(self, request, paquete_id: str, media_ref: str):
        return self._servir(request, paquete_id, media_ref, "HEAD")


class ConfirmarView(VistaEstudio):
    def post(self, request, paquete_id: str):
        datos = self._cuerpo(request, s.ConfirmarEntrada)
        return Response(paquetes_cu.ConfirmarPaquete(servicios()).ejecutar(self._alumno(request, datos), paquete_id, datos))


# ======================================================================================= trabajo sin red

class SyncView(VistaEstudio):
    """Sincronizar NO exige sesión (BR-137, D-11): sin JWT se autoriza por el aparato registrado y el alumno que declara, aunque el nodo exija sesión
    en el resto de las rutas."""

    permission_classes = [AllowAny]

    def post(self, request):
        datos = self._cuerpo(request, s.SyncEntrada)
        return Response(sincronizacion_cu.Sincronizar(servicios()).ejecutar(self._alumno(request, datos), datos))


class SyncStatusView(VistaEstudio):
    """El estado del libro de la instalación: se autoriza igual que el envío (por el aparato y el alumno declarado), sin sesión."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(sincronizacion_cu.EstadoDeSincronizacion(servicios()).ejecutar(
            self._alumno(request), self._huella(request), request.query_params.get("emisor_id") or "", self._declarado(request)))


# ============================================================================================ profesor (OPS)

class DocenteGruposView(VistaEstudio):
    def get(self, request):
        return Response(asignaciones_cu.GruposDelDocente(servicios()).ejecutar(self._docente(request)))


class DocenteAsignacionesView(VistaEstudio):
    def get(self, request):
        q = request.query_params
        return Response(asignaciones_cu.ListarAsignacionesDocente(servicios()).ejecutar(
            self._docente(request), q.get("grupo_id") or None, q.get("estado") or None))

    def post(self, request):
        datos = _validar(s.AsignacionNuevaEntrada, request.data)
        return Response(asignaciones_cu.CrearAsignacion(servicios()).ejecutar(self._docente(request, datos), datos), status=status.HTTP_201_CREATED)


class DocenteAsignacionView(VistaEstudio):
    def get(self, request, asignacion_id: str):
        return Response(asignaciones_cu.VerAsignacionDocente(servicios()).ejecutar(self._docente(request), asignacion_id))

    def patch(self, request, asignacion_id: str):
        datos = _validar(s.AsignacionCambiosEntrada, request.data, parcial=True)
        return Response(asignaciones_cu.CambiarAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos))


class DocenteCerrarView(VistaEstudio):
    def post(self, request, asignacion_id: str):
        datos = _validar(s.ActorEntrada, request.data)
        return Response(asignaciones_cu.CerrarAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id))


class DocenteDecisionesView(VistaEstudio):
    def post(self, request, asignacion_id: str):
        datos = _validar(s.DecisionEntrada, request.data)
        return Response(sincronizacion_cu.DecidirPendiente(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos))
