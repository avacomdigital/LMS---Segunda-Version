"""
Rutas HTTP de MOD-011 (`/api/gradebook/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM ni la biblioteca.

Contrato de degradación (el mismo del resto del backend):
  DatosInvalidos / PuntajeInvalido / EscalaInvalida / FaltaAlumno → 400 · SinPermiso / FueraDeAlcance / AlumnoDesconocido → 403 · NoEncontrado → 404 ·
  ConflictoDeVersion / TransicionInvalida / IntentoNoCalificable / ReactivosPendientes / NoPublicable / ModoSimple / ModoBloqueado / EscalaNoVigente /
  RubricaNoDisponible / RevisionNoPendiente / SolicitudRepetida / NodoNoInstalado → 409 · lo que MOD-010 rechaza llega con su mismo código y estado (FuenteNoDisponible → 503).

Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor` (profesor) o `alumno_id` (alumno).
Toda solicitud de cambio acepta `solicitud_id` (idempotencia) y, sobre una calificación, `version_esperada` (concurrencia optimista).
"""
from __future__ import annotations

import logging

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import ajuste as ajuste_cu
from ..aplicacion import consultas as consultas_cu
from ..aplicacion import consumidor as consumidor_cu
from ..aplicacion import derivados as derivados_cu
from ..aplicacion import escalas as escalas_cu
from ..aplicacion import modo as modo_cu
from ..aplicacion import publicacion as publicacion_cu
from ..aplicacion import registro as registro_cu
from ..aplicacion import revision as revision_cu
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from ..infraestructura.repositorios import AuditoriaGradebook

log = logging.getLogger("avacom.gradebook")
METODOS_QUE_CAMBIAN = ("POST", "PUT", "PATCH", "DELETE")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


class VistaGradebook(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorGradebook):
            if isinstance(exc, errores.SinPermiso) and self.request.method in METODOS_QUE_CAMBIAN:
                self._auditar_denegacion(exc)
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def _auditar_denegacion(self, exc) -> None:
        """TST-069: el intento de modificar sin autorización queda en la bitácora (también cuando lo intenta el rol técnico)."""
        try:
            actor = self._docente(self.request)
            AuditoriaGradebook().denegada(actor.id, exc.extra.get("permiso"), self.request.method, self.request.path, exc.codigo,
                                          {"grupo_id": exc.extra.get("grupo_id"), "rol": getattr(actor.principal, "rol_codigo", None)})
        except Exception:   # noqa: BLE001 — la denegación ya se dio; no fallar la respuesta por el asiento
            log.exception("No se pudo asentar el intento de modificación denegado")

    # ------------------------------------------------------------------------------------------------ quién actúa
    @staticmethod
    def _docente(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare."""
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         dispositivo_id=str(principal.dispositivo_id or ""), principal=principal)
        actor_id = str(datos.get("actor") or request.query_params.get("actor") or "")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or request.query_params.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)

    @staticmethod
    def _alumno(request, datos: dict | None = None) -> Actor:
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True, dispositivo_id=str(principal.dispositivo_id or ""), principal=principal)
        declarado = str(datos.get("alumno_id") or request.query_params.get("alumno_id") or "")
        return Actor(id=declarado[:64], nivel=1, autenticado=False)

    @staticmethod
    def _consulta(request) -> dict:
        return {k: v for k, v in request.query_params.items()}

    @staticmethod
    def _al_dia() -> None:
        """Antes de responder una consulta, el libro se pone al día con lo que MOD-010 ya publicó (el hilo del nodo puede ir unos segundos detrás). Un fallo
        aquí no impide leer lo que ya hay."""
        svc = servicios()
        if not svc.config.sincronizar_al_consultar:
            return
        try:
            consumidor_cu.ConsumirEventos(svc).hasta_vaciar(paginas=5)
        except Exception:   # noqa: BLE001
            log.exception("El libro no pudo ponerse al día con la evaluación antes de responder")


# =================================================================================================== el profesor: leer

class LibroView(VistaGradebook):
    def get(self, request):
        c = self._consulta(request)
        self._al_dia()
        return Response(consultas_cu.LibroDelGrupo(servicios()).ejecutar(
            self._docente(request), c.get("grupo_id", ""), asignacion_id=c.get("asignacion_id", ""), periodo=c.get("periodo", ""), curso_ref=c.get("curso_ref", ""), q=c.get("q", "")))


class ResumenView(VistaGradebook):
    def get(self, request):
        c = self._consulta(request)
        self._al_dia()
        return Response(consultas_cu.ResumenDePeriodo(servicios()).ejecutar(self._docente(request), c.get("grupo_id", ""), periodo=c.get("periodo", ""), curso_ref=c.get("curso_ref", "")))


class EstudianteView(VistaGradebook):
    def get(self, request, alumno_id: str):
        self._al_dia()
        return Response(consultas_cu.HistorialDelEstudiante(servicios()).ejecutar(self._docente(request), alumno_id, grupo_id=self._consulta(request).get("grupo_id", "")))


class AsignacionView(VistaGradebook):
    def get(self, request, asignacion_id: str):
        self._al_dia()
        return Response(consultas_cu.CalificacionesDeAsignacion(servicios()).ejecutar(self._docente(request), asignacion_id))


class ClasificacionView(VistaGradebook):
    def get(self, request, asignacion_id: str):
        return Response(modo_cu.VerClasificacion(servicios()).ejecutar(self._docente(request), asignacion_id))

    def put(self, request, asignacion_id: str):
        datos = _cuerpo(request)
        return Response(modo_cu.ClasificarEvaluacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos))


class CalificacionView(VistaGradebook):
    def get(self, request, calificacion_id: str):
        self._al_dia()
        return Response(consultas_cu.DetalleDeCalificacion(servicios()).ejecutar(self._docente(request), calificacion_id))


# ================================================================================= el profesor: registrar, revisar, cambiar

class RegistrarView(VistaGradebook):
    def post(self, request, intento_id: str):
        datos = _cuerpo(request)
        return Response(registro_cu.RegistrarCalificacion(servicios()).ejecutar(self._docente(request, datos), intento_id))


class BandejaView(VistaGradebook):
    def get(self, request):
        c = self._consulta(request)
        self._al_dia()
        return Response(revision_cu.BandejaDeRevision(servicios()).ejecutar(self._docente(request), grupo_id=c.get("grupo_id", ""), asignacion_id=c.get("asignacion_id", "")))


class RevisionView(VistaGradebook):
    def get(self, request, intento_id: str):
        return Response(revision_cu.DetalleDeRevision(servicios()).ejecutar(self._docente(request), intento_id))


class AplicarRevisionView(VistaGradebook):
    def post(self, request, intento_id: str, pregunta_ref: str):
        datos = _cuerpo(request)
        return Response(revision_cu.AplicarRevision(servicios()).ejecutar(self._docente(request, datos), intento_id, pregunta_ref, datos))


class ConfirmarRevisionView(VistaGradebook):
    def post(self, request, intento_id: str):
        datos = _cuerpo(request)
        return Response(revision_cu.ConfirmarRevision(servicios()).ejecutar(self._docente(request, datos), intento_id, datos))


class AjustarView(VistaGradebook):
    def post(self, request, calificacion_id: str):
        datos = _cuerpo(request)
        return Response(ajuste_cu.AjustarCalificacion(servicios()).ejecutar(self._docente(request, datos), calificacion_id, datos))


class ReabrirView(VistaGradebook):
    def post(self, request, calificacion_id: str):
        datos = _cuerpo(request)
        return Response(ajuste_cu.ReabrirCalificacion(servicios()).ejecutar(self._docente(request, datos), calificacion_id, datos))


class ValoracionView(VistaGradebook):
    def post(self, request, calificacion_id: str):
        datos = _cuerpo(request)
        return Response(ajuste_cu.ValorarDesempeno(servicios()).ejecutar(self._docente(request, datos), calificacion_id, datos))


class RetroalimentacionView(VistaGradebook):
    def post(self, request, calificacion_id: str):
        datos = _cuerpo(request)
        return Response(ajuste_cu.RetroalimentarCalificacion(servicios()).ejecutar(self._docente(request, datos), calificacion_id, datos))


class PublicarView(VistaGradebook):
    def post(self, request, calificacion_id: str):
        datos = _cuerpo(request)
        return Response(publicacion_cu.PublicarCalificacion(servicios()).ejecutar(self._docente(request, datos), calificacion_id, datos))


class RetirarPublicacionView(VistaGradebook):
    def post(self, request, calificacion_id: str):
        datos = _cuerpo(request)
        return Response(publicacion_cu.RetirarPublicacion(servicios()).ejecutar(self._docente(request, datos), calificacion_id, datos))


class PublicarAsignacionView(VistaGradebook):
    def post(self, request, asignacion_id: str):
        datos = _cuerpo(request)
        return Response(publicacion_cu.PublicarAsignacion(servicios()).ejecutar(self._docente(request, datos), asignacion_id, datos))


# ================================================================================================ la administración

class ConfiguracionView(VistaGradebook):
    def get(self, request):
        return Response(modo_cu.VerConfiguracion(servicios()).ejecutar(self._docente(request)))


class NivelView(VistaGradebook):
    def put(self, request, nivel_clave: str):
        datos = _cuerpo(request)
        return Response(modo_cu.ConfigurarNivel(servicios()).ejecutar(self._docente(request, datos), nivel_clave, datos))

    post = put


class PoliticaView(VistaGradebook):
    def put(self, request):
        datos = _cuerpo(request)
        return Response(modo_cu.ConfigurarPolitica(servicios()).ejecutar(self._docente(request, datos), datos))


class PlantillasView(VistaGradebook):
    def get(self, request):
        return Response(escalas_cu.PlantillasDeEscalas(servicios()).ejecutar(self._docente(request), self._consulta(request).get("pais", "")))


class EscalasView(VistaGradebook):
    def get(self, request):
        return Response(escalas_cu.ListarEscalas(servicios()).ejecutar(self._docente(request)))

    def post(self, request):
        datos = _cuerpo(request)
        return Response(escalas_cu.CrearEscala(servicios()).ejecutar(self._docente(request, datos), datos), status=status.HTTP_201_CREATED)


class AdoptarView(VistaGradebook):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(escalas_cu.AdoptarPlantilla(servicios()).ejecutar(self._docente(request, datos), datos), status=status.HTTP_201_CREATED)


class VistaPreviaView(VistaGradebook):
    def post(self, request):
        datos = _cuerpo(request)
        return Response(escalas_cu.VistaPreviaDeEscala(servicios()).ejecutar(self._docente(request, datos), datos))


class EscalaView(VistaGradebook):
    def get(self, request, escala_id: str):
        return Response(escalas_cu.VerEscala(servicios()).ejecutar(self._docente(request), escala_id))


class VersionesDeEscalaView(VistaGradebook):
    def post(self, request, escala_id: str):
        datos = _cuerpo(request)
        return Response(escalas_cu.NuevaVersionDeEscala(servicios()).ejecutar(self._docente(request, datos), escala_id, datos), status=status.HTTP_201_CREATED)


class SincronizarView(VistaGradebook):
    """Pone el libro al día con los eventos de MOD-010 ahora mismo (el hilo del nodo lo hace cada pocos segundos)."""

    def post(self, request):
        actor = self._docente(request, _cuerpo(request))
        svc = servicios()
        svc.autorizacion.exigir(actor, "results.read")
        return Response(consumidor_cu.ConsumirEventos(svc).hasta_vaciar())


class ReconstruirView(VistaGradebook):
    """FUN-129: reconstruir lo derivado tras una restauración (`reproducir`: además vuelve a leer todos los eventos de MOD-010)."""

    def post(self, request):
        datos = _cuerpo(request)
        actor = self._docente(request, datos)
        if datos.get("reproducir"):
            return Response(consumidor_cu.ReproducirYReconstruir(servicios()).ejecutar(actor, reproducir=True))
        return Response(derivados_cu.ReconstruirDerivados(servicios()).ejecutar(actor))


# ====================================================================================================== el alumno

class MisResultadosView(VistaGradebook):
    def get(self, request):
        self._al_dia()
        return Response(consultas_cu.MisResultados(servicios()).ejecutar(self._alumno(request)))
