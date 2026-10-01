"""
Rutas HTTP de MOD-010 (`/api/evaluacion/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM ni la biblioteca.

Contrato de degradación (el mismo del resto del backend, §7 de `spec-driven/06-evaluation-delivery/backend.md`):
  DatosInvalidos / FaltaDispositivo / FaltaAlumno → 400 · SinPermiso (también AlumnoDesconocido) / NoEsElTitular / DispositivoBloqueado / DispositivoInactivo /
  DispositivoAjeno / AdmisionRechazada / ResultadosNoLiberados → 403 · NoEncontrado → 404 · NodoNoInstalado / AdministracionNoPermitida / AsignacionNoAbierta /
  AsignacionCerrada / IntentosAgotados / IntentosAbiertos / TransicionInvalida / IntentoCerrado / VersionNoDisponible / ConfirmacionRequerida / ReactivosPendientes
  → 409 · FuenteError → 502 · FuenteNoDisponible → 503 `{disponible:false, detail, codigo, sugerencia}`. Los errores de `acceso` conservan su forma.

Al aparato se le identifica con su huella `dispositivo` (= `identificador_hw`): en `?dispositivo=` (GET) o en el cuerpo (POST). Sin `dispositivo` ni sesión de
alumno: 400 `falta_dispositivo`. Sin sesión (Q-34) el alumno es el que la tableta declara con `alumno_id` (cuerpo o `?alumno_id=`); el profesor declara `actor`.
"""
from __future__ import annotations

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de
from classroom_engine.interfaces.views import _respuesta_bytes

from ..aplicacion import admisiones as admisiones_cu
from ..aplicacion import asignaciones as asignaciones_cu
from ..aplicacion import calificacion as calificacion_cu
from ..aplicacion import incidentes as incidentes_cu
from ..aplicacion import intentos as intentos_cu
from ..aplicacion import panel as panel_cu
from ..aplicacion import respuestas as respuestas_cu
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from . import serializers as s


def _validar(serializer_cls, datos) -> dict:
    ser = serializer_cls(data=datos if isinstance(datos, dict) else {})
    ser.is_valid(raise_exception=True)
    return dict(ser.validated_data)


class VistaEvaluacion(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.FuenteNoDisponible):
            return Response({"disponible": False, "detail": exc.detalle, "codigo": exc.codigo, "sugerencia": exc.sugerencia, **exc.extra},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if isinstance(exc, errores.ErrorEvaluacion):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    # ------------------------------------------------------------------------------------ quién actúa
    @staticmethod
    def _consulta(request) -> dict:
        return {k: v for k, v in request.query_params.items()}

    def _cuerpo(self, request, serializer) -> dict:
        """El cuerpo validado, con el aparato y la persona declarados completados desde la URL si el cuerpo no los trae."""
        datos = _validar(serializer, request.data)
        for clave in ("dispositivo", "alumno_id", "actor"):
            if not datos.get(clave) and request.query_params.get(clave):
                datos[clave] = request.query_params[clave]
        return datos

    def _alumno(self, request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), el alumno lo decide el aparato (`resolver_contexto`): aquí sólo se declara."""
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True, dispositivo_id=str(principal.dispositivo_id or ""),
                         principal=principal)
        declarado = str(datos.get("alumno_id") or request.query_params.get("alumno_id") or "")
        return Actor(id=declarado[:64], nivel=1, autenticado=False)

    @staticmethod
    def _docente(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare, como en el aula."""
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         principal=principal)
        # Sin nadie declarado el actor queda SIN id: lo operativo se asienta como «docente» (`actor.id or "docente"`), pero anular, que exige una
        # persona con nombre (INV-018), lo rechaza en vez de firmar con un genérico.
        actor_id = str(datos.get("actor") or request.query_params.get("actor") or "")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or request.query_params.get("actor_rotulo") or "")[:120], nivel=2,
                     autenticado=False)

    def _datos_del_alumno(self, request) -> dict:
        return {"dispositivo": request.query_params.get("dispositivo", ""), "alumno_id": request.query_params.get("alumno_id", ""),
                "todas": request.query_params.get("todas") in ("1", "true", "True")}


# ============================================================================== el profesor: asignaciones

class AsignacionesView(VistaEvaluacion):
    def get(self, request):
        c = self._consulta(request)
        return Response({"asignaciones": asignaciones_cu.ListarAsignaciones(servicios()).ejecutar(
            self._docente(request), estado=c.get("estado"), grupo_id=c.get("grupo_id"), sesion_id=c.get("sesion_id"), profesor_id=c.get("profesor"))})

    def post(self, request):
        datos = self._cuerpo(request, s.AsignacionEntrada)
        return Response(asignaciones_cu.CrearAsignacion(servicios()).ejecutar(self._docente(request, datos), datos), status=status.HTTP_201_CREATED)


class AsignacionView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        return Response(asignaciones_cu.VerAsignacion(servicios()).ejecutar(self._docente(request), asignacion_id))


class IniciarView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(asignaciones_cu.IniciarAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id))


class CerrarAsignacionView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(asignaciones_cu.CerrarAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos.get("motivo", "")))


class ProrrogarView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.ProrrogaEntrada)
        return Response(asignaciones_cu.ProrrogarAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos.get("limite_en")))


class ReabrirView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.ProrrogaEntrada)
        return Response(asignaciones_cu.ReabrirAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos.get("limite_en")))


class PlazoView(VistaEvaluacion):
    def patch(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.PlazoEntrada)
        return Response(asignaciones_cu.ConfigurarPlazo(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos))


class EndurecerView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.ProrrogaEntrada)
        return Response(asignaciones_cu.EndurecerPlazo(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos.get("limite_en")))


class NivelView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.NivelEntrada)
        return Response(asignaciones_cu.DefinirNivel(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos.get("nivel_examen")))


class DegradarView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.NivelEntrada)
        return Response(asignaciones_cu.DegradarNivel(servicios()).ejecutar(
            self._docente(request, datos), asignacion_id, datos.get("nivel_examen"), datos.get("motivo", "")))


class LiberarResultadosView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(asignaciones_cu.LiberarResultados(servicios()).ejecutar(self._docente(request, datos), asignacion_id))


# ====================================================================== el profesor: vigilar y decidir

class PanelView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        return Response(panel_cu.PanelDeAsignacion(servicios()).ejecutar(self._docente(request), asignacion_id))


class ElegibilidadView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        return Response(panel_cu.Elegibilidad(servicios()).ejecutar(self._docente(request), asignacion_id, request.query_params.get("nivel")))


class ResultadosView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        return Response(panel_cu.ResultadosDeAsignacion(servicios()).ejecutar(self._docente(request), asignacion_id))


class AdmisionesView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        return Response(admisiones_cu.ListarAdmisiones(servicios()).ejecutar(
            self._docente(request), asignacion_id, todas=request.query_params.get("todas") in ("1", "true", "True")))


class AdmisionDecidirView(VistaEvaluacion):
    def post(self, request, asignacion_id: str, admision_id: str):
        datos = self._cuerpo(request, s.AdmisionEntrada)
        return Response(admisiones_cu.DecidirAdmision(servicios()).ejecutar(self._docente(request, datos), asignacion_id, admision_id, datos))


class ReactivarTodosView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        """Cuántos esperan reactivación (el profesor ve el número ANTES de confirmar, Guion paso 12)."""
        return Response(intentos_cu.ReactivarTodos(servicios()).ejecutar(self._docente(request), asignacion_id, solo_contar=True))

    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(intentos_cu.ReactivarTodos(servicios()).ejecutar(self._docente(request, datos), asignacion_id))


# ===================================================================== el profesor: sobre un intento

class IntentoView(VistaEvaluacion):
    """PAN-062: el expediente del intento, sólo lectura."""

    def get(self, request, intento_id: str):
        return Response(panel_cu.ExpedienteDelIntento(servicios()).ejecutar(self._docente(request), intento_id))


class RevisionView(VistaEvaluacion):
    def get(self, request, intento_id: str):
        return Response(calificacion_cu.RevisionDelIntento(servicios()).ejecutar(self._docente(request), intento_id))


class ReactivarView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.ReactivarEntrada)
        return Response(intentos_cu.ReactivarIntento(servicios()).ejecutar(self._docente(request, datos), intento_id, datos.get("desde_pregunta", "")))


class CerrarIntentoView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(intentos_cu.CerrarIntento(servicios()).ejecutar(self._docente(request, datos), intento_id))


class AnularView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.AnularEntrada)
        return Response(intentos_cu.AnularIntento(servicios()).ejecutar(self._docente(request, datos), intento_id, datos.get("motivo", "")))


class PuntuarView(VistaEvaluacion):
    def post(self, request, intento_id: str, pregunta_ref: str):
        datos = self._cuerpo(request, s.PuntuarEntrada)
        return Response(calificacion_cu.PuntuarRespuesta(servicios()).ejecutar(self._docente(request, datos), intento_id, pregunta_ref, datos))


class PublicarView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(calificacion_cu.PublicarIntento(servicios()).ejecutar(self._docente(request, datos), intento_id))


class RecalificarView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.CierreEntrada)
        return Response(calificacion_cu.Recalificar(servicios()).ejecutar(self._docente(request, datos), intento_id))


class DecidirEnvioView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.DecisionEnvioEntrada)
        return Response(respuestas_cu.DecidirEnvio(servicios()).ejecutar(self._docente(request, datos), intento_id, datos.get("decision", ""), datos.get("motivo", "")))


# ================================================================================== el alumno: descubrir

class MisEvaluacionesView(VistaEvaluacion):
    def get(self, request):
        datos = self._datos_del_alumno(request)
        return Response(panel_cu.MisEvaluaciones(servicios()).ejecutar(self._alumno(request, datos), datos))


class AntesalaView(VistaEvaluacion):
    def get(self, request, asignacion_id: str):
        datos = self._datos_del_alumno(request)
        return Response(panel_cu.Antesala(servicios()).ejecutar(self._alumno(request, datos), asignacion_id, datos))


class AbrirIntentoView(VistaEvaluacion):
    def post(self, request, asignacion_id: str):
        datos = self._cuerpo(request, s.AperturaEntrada)
        cuerpo, http = intentos_cu.AbrirIntento(servicios()).ejecutar(self._alumno(request, datos), asignacion_id, datos)
        return Response(cuerpo, status=http)


# ================================================================================= el alumno: presentar

class EstadoView(VistaEvaluacion):
    def get(self, request, intento_id: str):
        datos = self._datos_del_alumno(request)
        return Response(intentos_cu.EstadoDelIntento(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


class LatidoView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.LatidoEntrada)
        return Response(intentos_cu.Latido(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


class PreguntasView(VistaEvaluacion):
    def get(self, request, intento_id: str):
        datos = self._datos_del_alumno(request)
        respuesta = Response(intentos_cu.PreguntasDelIntento(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))
        respuesta["Cache-Control"] = "no-store"          # un examen no se queda en la caché de la tableta
        return respuesta


class MedioView(VistaEvaluacion):
    """Bytes de un medio de una pregunta de ESTE examen (con `Range`)."""

    def _servir(self, request, intento_id: str, media_ref: str, ruta: str | None, metodo: str):
        datos = self._datos_del_alumno(request)
        medio = intentos_cu.MedioDelIntento(servicios()).ejecutar(self._alumno(request, datos), intento_id, media_ref, ruta, request.headers.get("Range"), metodo, datos)
        respuesta = _respuesta_bytes(request, medio, metodo)
        respuesta["Cache-Control"] = "no-store"
        return respuesta

    def get(self, request, intento_id: str, media_ref: str, ruta: str | None = None):
        return self._servir(request, intento_id, media_ref, ruta, "GET")

    def head(self, request, intento_id: str, media_ref: str, ruta: str | None = None):
        return self._servir(request, intento_id, media_ref, ruta, "HEAD")


class RespuestasView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.RespuestasEntrada)
        return Response(respuestas_cu.EnviarRespuestas(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


class IncidentesView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.IncidentesEntrada)
        return Response(incidentes_cu.RegistrarIncidentes(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


class BloqueoView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.BloqueoEntrada)
        return Response(incidentes_cu.InformarBloqueo(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


class EntregarView(VistaEvaluacion):
    def post(self, request, intento_id: str):
        datos = self._cuerpo(request, s.EntregaEntrada)
        return Response(intentos_cu.EntregarIntento(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


class ResultadoView(VistaEvaluacion):
    def get(self, request, intento_id: str):
        datos = self._datos_del_alumno(request)
        return Response(calificacion_cu.ResultadoDelAlumno(servicios()).ejecutar(self._alumno(request, datos), intento_id, datos))


# ============================================================================ FUN-103 y FUN-104 (biblioteca)

class AdministracionRechazadaView(VistaEvaluacion):
    """Crear una evaluación o añadir un reactivo es de AVACOM Biblioteca (artículo 14, 14.2): cualquier verbo responde 409 nombrando al dueño."""

    operacion = "Crear una evaluación"

    def _rechazar(self, request):
        datos = request.data if isinstance(request.data, dict) else {}
        asignaciones_cu.RechazarAdministracion(servicios()).ejecutar(self._docente(request, datos), self.operacion)

    def get(self, request, *args, **kwargs):
        return self._rechazar(request)

    post = put = patch = delete = get


class EvaluacionesRechazadaView(AdministracionRechazadaView):
    operacion = "Crear una evaluación con banco de reactivos (FUN-103)"


class ReactivosRechazadaView(AdministracionRechazadaView):
    operacion = "Añadir un reactivo a una evaluación (FUN-104)"
