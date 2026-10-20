"""
Rutas HTTP de MOD-013 (`/api/reportes/`). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM ni la biblioteca.

Contrato de degradación (el mismo del resto del backend):
  DatosInvalidos / MotivoRequerido → 400 · SinPermiso / FueraDeAlcance / DestinoNoPermitido → 403 · NoEncontrado → 404 ·
  NodoNoInstalado / ClaseEnCurso / AlumnoSinGrupo / SinSesionesFinalizadas / SesionActiva / ReconstruccionEnCurso / ExportacionCaducada / ExportacionYaConfirmada / HuellaDistinta /
  ConflictoDeVersion → 409 · CapacidadReservada → 501.

Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor` (y `actor_rotulo`). Todo 403 sobre datos académicos —también el del rol
técnico (TST-069)— deja un asiento `reporte.acceso_denegado` con quién, qué permiso pedía y sobre qué ruta.

`POST /exportaciones/` responde el ARCHIVO (no un JSON): su contenido va en el cuerpo y sus datos en las cabeceras `X-Avacom-Export-*`, para que el cliente lo baje directo a un archivo
sin cargarlo entero en memoria; los errores siguen siendo JSON.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from django.http import FileResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import ajustes as ajustes_cu
from ..aplicacion import consumidor as consumidor_cu
from ..aplicacion import exportar as exportar_cu
from ..aplicacion import reportes as reportes_cu
from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from ..infraestructura.repositorios import AuditoriaReporting

log = logging.getLogger("avacom.reporting")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


class VistaReportes(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorReporting):
            if isinstance(exc, errores.SinPermiso):
                self._auditar_denegacion(exc)
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def _auditar_denegacion(self, exc) -> None:
        """TST-069: el intento de leer o exportar datos académicos sin poder hacerlo queda en la bitácora (también cuando lo intenta el rol técnico)."""
        try:
            try:
                datos = _cuerpo(self.request) if self.request.method in ("POST", "PUT", "PATCH") else {}
            except Exception:   # noqa: BLE001 — un cuerpo ilegible no impide asentar quién lo intentó
                datos = {}
            actor = self._actor(self.request, datos)
            AuditoriaReporting().denegada(actor.id, exc.extra.get("permiso"), self.request.method, self.request.path, exc.codigo,
                                          {"grupo_id": exc.extra.get("grupo_id"), "rol": actor.rol or None})
        except Exception:   # noqa: BLE001 — la denegación ya se dio; no fallar la respuesta por el asiento
            log.exception("No se pudo asentar el intento de lectura denegado")

    # ------------------------------------------------------------------------------------------------------------------ quién actúa
    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare."""
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         dispositivo_id=str(principal.dispositivo_id or ""), principal=principal, rol=str(principal.rol_codigo or ""))
        actor_id = str(datos.get("actor") or request.query_params.get("actor") or "")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or request.query_params.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)

    @staticmethod
    def _consulta(request) -> dict:
        return {k: v for k, v in request.query_params.items()}


# =================================================================================================================== leer

class ClasesView(VistaReportes):
    def get(self, request):
        return Response(reportes_cu.ListaDeClases(servicios()).ejecutar(self._actor(request), self._consulta(request)))


class ClaseView(VistaReportes):
    def get(self, request, sesion_id: str):
        return Response(reportes_cu.ReporteDeClase(servicios()).ejecutar(self._actor(request), sesion_id, self._consulta(request)))


class GrupoView(VistaReportes):
    def get(self, request, grupo_id: str):
        return Response(reportes_cu.ReporteDeGrupo(servicios()).ejecutar(self._actor(request), grupo_id, self._consulta(request)))


class AlumnosView(VistaReportes):
    def get(self, request):
        return Response(reportes_cu.AlumnosDelGrupo(servicios()).ejecutar(self._actor(request), self._consulta(request).get("grupo_id", "")))


class AlumnoView(VistaReportes):
    def get(self, request, alumno_id: str):
        return Response(reportes_cu.ReporteDeAlumno(servicios()).ejecutar(self._actor(request), alumno_id, self._consulta(request)))


class UsoView(VistaReportes):
    def get(self, request):
        return Response(reportes_cu.ReporteDeUso(servicios()).ejecutar(self._actor(request), self._consulta(request)))


class BoletinView(VistaReportes):
    """El boletín académico de un estudiante (`grupo_id` opcional: sin él, el primero de sus grupos que se puede ver)."""

    def get(self, request, alumno_id: str):
        return Response(reportes_cu.ReporteDeBoletin(servicios()).ejecutar(self._actor(request), alumno_id, self._consulta(request)))


class BoletinesView(VistaReportes):
    """Los boletines de todos los estudiantes de un grupo (`grupo_id` obligatorio): lo que se exporta como un archivo por estudiante."""

    def get(self, request):
        c = self._consulta(request)
        return Response(reportes_cu.ReporteDeBoletin(servicios()).ejecutar_grupo(self._actor(request), c.get("grupo_id", ""), c))


class FiltrosView(VistaReportes):
    def get(self, request):
        return Response(reportes_cu.Filtros(servicios()).ejecutar(self._actor(request)))


class RecientesView(VistaReportes):
    def get(self, request):
        return Response(reportes_cu.Recientes(servicios()).ejecutar(self._actor(request)))


class ReservadaView(VistaReportes):
    """CAP-083 (comparar grupos) y CAP-085 / FUN-141 (cobertura curricular): previstas para V1. La ruta existe para que el cliente sepa que está reservada, no que se perdió."""

    capacidad = ""

    def get(self, request):
        raise errores.CapacidadReservada(
            "Comparar el avance entre grupos llega en una versión posterior." if self.capacidad == cat.COMPARACION
            else "La cobertura curricular real contra la planeada llega en una versión posterior: necesita el currículo congelado del ciclo.", capacidad=self.capacidad,
            permiso=cat.P_CURRICULUM)


class ComparacionView(ReservadaView):
    capacidad = cat.COMPARACION


class CoberturaView(ReservadaView):
    capacidad = cat.COBERTURA


# =================================================================================================================== configuración y estado

class ConfiguracionView(VistaReportes):
    def get(self, request):
        return Response(ajustes_cu.VerConfiguracion(servicios()).ejecutar(self._actor(request)))

    def put(self, request):
        cuerpo = _cuerpo(request)
        return Response(ajustes_cu.CambiarConfiguracion(servicios()).ejecutar(self._actor(request, cuerpo), cuerpo))


class EstadoView(VistaReportes):
    def get(self, request):
        return Response(ajustes_cu.EstadoDeAgregados(servicios()).ejecutar(self._actor(request)))


class ActualizarView(VistaReportes):
    """FUN-144 a petición: pone al día la cola y recalcula los agregados desactualizados aunque haya una clase abierta (quien lo pide sabe lo que hace)."""

    def post(self, request):
        cuerpo = _cuerpo(request)
        actor = self._actor(request, cuerpo)
        servicios().autorizacion.exigir(actor, cat.P_REBUILD)
        return Response(consumidor_cu.ActualizarAgregados(servicios()).ejecutar(forzar=True))


class ReconstruirView(VistaReportes):
    def post(self, request):
        cuerpo = _cuerpo(request)
        return Response(consumidor_cu.Reconstruir(servicios()).ejecutar(self._actor(request, cuerpo)))


# =================================================================================================================== exportar

class AlcanceView(VistaReportes):
    def post(self, request):
        cuerpo = _cuerpo(request)
        return Response(exportar_cu.AlcanceDeExportacion(servicios()).ejecutar(self._actor(request, cuerpo), cuerpo))


class ExportacionesView(VistaReportes):
    def get(self, request):
        return Response(exportar_cu.MisExportaciones(servicios()).ejecutar(self._actor(request)))

    def post(self, request):
        """1.er tiempo: autoriza, genera y entrega el archivo (cuerpo binario + cabeceras `X-Avacom-Export-*`)."""
        cuerpo = _cuerpo(request)
        r = exportar_cu.AutorizarExportacion(servicios()).ejecutar(self._actor(request, cuerpo), cuerpo)
        e, archivo = r["exportacion"], r["archivo"]
        respuesta = FileResponse(archivo.contenido, content_type=cat.TIPO_MIME[e["formato"]], status=status.HTTP_201_CREATED)
        respuesta["Content-Length"] = str(archivo.bytes_total)
        respuesta["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(e['nombre_archivo'])}"
        respuesta["Cache-Control"] = "no-store"
        for cabecera, valor in (("Id", e["id"]), ("Huella", e["huella"]), ("Filas", e["filas"]), ("Bytes", e["bytes"]), ("Formato", e["formato"]), ("Tipo", e["tipo"]),
                                ("Nombre", quote(e["nombre_archivo"])), ("Expira-En", e["expira_en"]), ("Corte-En", e["corte_en"]), ("Nominal", "true" if e["nominal"] else "false"),
                                ("Umbral-Aplicado", "true" if e["umbral_aplicado"] else "false"), ("Destino", e["destino_autorizado"])):
            respuesta[f"X-Avacom-Export-{cabecera}"] = str(valor)
        return respuesta


class ExportacionView(VistaReportes):
    def get(self, request, exportacion_id: str):
        return Response(exportar_cu.VerExportacion(servicios()).ejecutar(self._actor(request), exportacion_id))


class ConfirmarView(VistaReportes):
    """2.º tiempo: el cliente dice qué pasó al escribir (guardado o fallido), en qué tipo de destino y la huella que verificó releyendo."""

    def post(self, request, exportacion_id: str):
        cuerpo = _cuerpo(request)
        return Response(exportar_cu.ConfirmarExportacion(servicios()).ejecutar(self._actor(request, cuerpo), exportacion_id, cuerpo))
