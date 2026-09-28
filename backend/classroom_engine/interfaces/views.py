"""
Rutas HTTP de MOD-007 (`/api/aula/`). Las vistas sólo traducen HTTP ↔ casos de uso:
no tocan el ORM ni la biblioteca.

Contrato de degradación (mismo que el resto del backend):
  FuenteNoDisponible → 503 {disponible:false, detail, codigo, sugerencia}
  CapacidadAusente   → 501 {detail, codigo, capacidades}
  *NoEncontrado      → 404 · TransicionInvalida / conflictos → 409 · SinPermiso → 403 · DatosInvalidos → 400
"""
from __future__ import annotations

from django.http import HttpResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.interfaces.permisos import SesionSiSeExige, principal_de
from biblioteca import cliente as cliente_biblioteca
from biblioteca.views import _reenviar_flujo, respuesta_de_error

from ..aplicacion import casos_uso as cu
from ..aplicacion.puertos import Actor, Bytes
from ..dominio import errores
from ..infraestructura.contenedor import servicios

CABECERAS_MEDIO = ("Content-Length", "Content-Range", "Accept-Ranges", "Cache-Control")


# ------------------------------------------------------------------- base

class VistaAula(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.FuenteNoDisponible):
            return Response({"disponible": False, "detail": exc.detalle, "codigo": exc.codigo, "sugerencia": exc.sugerencia, **exc.extra},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if isinstance(exc, errores.ErrorAula):
            return Response({"detail": exc.detalle, "codigo": exc.codigo, **exc.extra}, status=exc.http)
        if isinstance(exc, (cliente_biblioteca.BibliotecaNoDisponible, cliente_biblioteca.BibliotecaError)):
            return respuesta_de_error(exc)
        return super().handle_exception(exc)

    @staticmethod
    def _fuente(request) -> str | None:
        return request.query_params.get("fuente") or None

    @staticmethod
    def _version(request) -> str | None:
        """`?version=1.1.0` exige esa versión del curso; la API sólo sirve la instalada (otra es 404). Sin ella, la instalada."""
        return request.query_params.get("version") or None

    @staticmethod
    def _semilla(request) -> str | None:
        """`?semilla=<sesion>` fija el barajado de las opciones: toda la clase ve el mismo orden."""
        return request.query_params.get("semilla") or None

    @staticmethod
    def _rol(request) -> str:
        """El rol lo decide la sesión (MOD-001) cuando hay una; sin sesión lo declara el cliente y por defecto es el más restrictivo."""
        principal = principal_de(request)
        if principal is not None:
            return "estudiante" if str(getattr(principal, "menu", "")) == "student" else "docente"
        return "docente" if request.query_params.get("rol") == "docente" else "estudiante"

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare, como en el expediente."""
        principal = principal_de(request)
        datos = datos or {}
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel),
                         autenticado=True, dispositivo=str(datos.get("dispositivo") or principal.dispositivo_id or ""),
                         sesion_usuario_id=principal.sesion_id)
        actor_id = str(datos.get("profesor_id") or datos.get("actor") or request.query_params.get("actor") or "docente")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("profesor_rotulo") or datos.get("actor_rotulo") or "")[:120],
                     nivel=2, autenticado=False, dispositivo=str(datos.get("dispositivo") or "")[:64])


def _respuesta_bytes(request, medio: Bytes, metodo: str):
    """Bytes generados (ejemplo) con soporte de Range, o paso a través del flujo de la biblioteca."""
    if medio.flujo is not None:
        salida = _reenviar_flujo(medio.flujo, metodo)
    else:
        datos = medio.datos or b""
        rango = request.headers.get("Range")
        desde, hasta, parcial = 0, len(datos) - 1, False
        if rango and rango.startswith("bytes=") and datos:
            a, _, b = rango[6:].partition("-")
            if a == "" and b:
                desde = max(0, len(datos) - int(b))
            else:
                desde = int(a or 0)
                hasta = int(b) if b else len(datos) - 1
            parcial = True
            if desde >= len(datos):
                salida = HttpResponse(status=416)
                salida["Content-Range"] = f"bytes */{len(datos)}"
                return salida
        trozo = datos[desde:hasta + 1]
        salida = HttpResponse(b"" if metodo == "HEAD" else trozo, status=206 if parcial else 200, content_type=medio.tipo)
        salida["Content-Length"] = str(len(trozo))
        salida["Accept-Ranges"] = "bytes"
        if parcial:
            salida["Content-Range"] = f"bytes {desde}-{hasta}/{len(datos)}"
        salida["Cache-Control"] = "no-store"
    for clave, valor in (medio.cabeceras or {}).items():
        salida[clave] = valor
    return salida


# --------------------------------------------------------------- el curso

class FuenteView(VistaAula):
    """¿Hay contenido? Estado de la fuente de cursos (link.json, salud, cursos instalados, huella). Nunca 503."""

    def get(self, request):
        return Response(cu.EstadoFuente(servicios()).ejecutar(self._fuente(request)))


class CursosView(VistaAula):
    """Los cursos ofrecidos por la fuente, agrupados por asignatura (panel de navegación)."""

    def get(self, request):
        return Response(cu.ConsultarCursos(servicios()).ejecutar(self._fuente(request)))


class CursoView(VistaAula):
    """La vista de aula completa: clasificación, medios, lecciones, objetos, bloques y preguntas sin claves."""

    def get(self, request, curso_ref: str):
        return Response(cu.ConsultarCurso(servicios()).ejecutar(
            curso_ref, self._rol(request), self._fuente(request), self._version(request), self._semilla(request)))


class LeccionView(VistaAula):
    def get(self, request, curso_ref: str, leccion_ref: str):
        return Response(cu.ConsultarLeccion(servicios()).ejecutar(
            curso_ref, leccion_ref, self._rol(request), self._fuente(request), self._version(request), self._semilla(request)))


class ObjetoView(VistaAula):
    def get(self, request, curso_ref: str, objeto_ref: str):
        return Response(cu.ConsultarObjeto(servicios()).ejecutar(
            curso_ref, objeto_ref, self._rol(request), self._fuente(request), self._version(request), self._semilla(request)))


class EvaluarView(VistaAula):
    """`POST /v2/evaluate` visto desde el aula: `{version, objeto_ref, pregunta_ref, respuesta}` o
    `{version, items:[…]}` (hasta 200). Devuelve el veredicto sin ninguna clave; no escribe (MOD-010, Q-48)."""

    def post(self, request, curso_ref: str):
        return Response(cu.EvaluarRespuesta(servicios()).ejecutar(curso_ref, request.data or {}, self._fuente(request)))


class MedioView(VistaAula):
    """Bytes de un medio del curso (imagen, audio, pdf, simulación y sus archivos internos, subtítulos, transcripción)."""

    def get(self, request, curso_ref: str, media_ref: str, ruta: str | None = None):
        medio = cu.AbrirMedio(servicios()).ejecutar(curso_ref, media_ref, ruta, request.headers.get("Range"), "GET", self._fuente(request))
        return _respuesta_bytes(request, medio, "GET")

    def head(self, request, curso_ref: str, media_ref: str, ruta: str | None = None):
        medio = cu.AbrirMedio(servicios()).ejecutar(curso_ref, media_ref, ruta, request.headers.get("Range"), "HEAD", self._fuente(request))
        return _respuesta_bytes(request, medio, "HEAD")


class PruebasCursoView(VistaAula):
    """El endpoint de PRUEBA: el curso «Ciencias naturales» del manifiesto de ejemplo, tal como lo
    consumirá el componente MAUI. Siempre usa la fuente «ejemplo»."""

    def get(self, request):
        return Response(cu.ConsultarCurso(servicios()).ejecutar("ejemplo", self._rol(request), "ejemplo"))


class PruebasCursosView(VistaAula):
    def get(self, request):
        return Response(cu.ConsultarCursos(servicios()).ejecutar("ejemplo"))


# ------------------------------------------------------------- la sesión

class SesionesView(VistaAula):
    def get(self, request):
        q = request.query_params
        return Response(cu.ListarSesiones(servicios()).ejecutar(q.get("estado"), q.get("grupo"), q.get("profesor")))

    def post(self, request):
        datos = request.data or {}
        return Response(cu.IniciarSesion(servicios()).ejecutar(self._actor(request, datos), datos), status=status.HTTP_201_CREATED)


class SesionView(VistaAula):
    def get(self, request, sesion_id: str):
        return Response(cu.VerSesion(servicios()).ejecutar(sesion_id))


class UnirseView(VistaAula):
    """La tableta presenta el código de unión (PAN-100/101 → PAN-102)."""

    def post(self, request):
        resultado = cu.UnirseASesion(servicios()).ejecutar(request.data or {})
        return Response(resultado, status=status.HTTP_201_CREATED if resultado.get("nuevo") else status.HTTP_200_OK)


class ParticipanteAccionView(VistaAula):
    ACCIONES = {"admitir": cu.AdmitirParticipante, "rechazar": cu.RechazarParticipante, "expulsar": cu.ExpulsarParticipante}

    def post(self, request, sesion_id: str, participante_id: str, accion: str):
        caso = self.ACCIONES.get(accion)
        if caso is None:
            return Response({"detail": f"Acción desconocida «{accion}».", "codigo": "datos_invalidos"}, status=400)
        datos = request.data or {}
        actor = self._actor(request, datos)
        if accion == "admitir":
            return Response(caso(servicios()).ejecutar(actor, sesion_id, participante_id))
        return Response(caso(servicios()).ejecutar(actor, sesion_id, participante_id, str(datos.get("motivo") or "")))


class PresenciaView(VistaAula):
    """FUN-073: la tableta declara su presencia y recibe el estado que debe pintar."""

    def post(self, request, sesion_id: str, participante_id: str):
        datos = request.data or {}
        desde = datos.get("avisos_desde")
        return Response(cu.RegistrarPresencia(servicios()).ejecutar(
            sesion_id, participante_id, datos.get("estado"), str(datos.get("dispositivo") or ""),
            int(desde) if desde else None))


class EstadoTabletaView(VistaAula):
    """Sondeo de sólo lectura (BR-049: el cambio de selector llega en 3 s; el cliente sondea cada 2 s hasta que haya WebSocket)."""

    def get(self, request, sesion_id: str):
        q = request.query_params
        desde = q.get("avisos_desde")
        return Response(cu.EstadoParaTableta(servicios()).ejecutar(sesion_id, q.get("participante") or None, int(desde) if desde else None))


class SelectorView(VistaAula):
    """FUN-069 · BR-049: el profesor declara qué proyecta (lámina, página, objeto o medio). No es un lanzamiento."""

    def post(self, request, sesion_id: str):
        datos = request.data or {}
        return Response(cu.DeclararSelector(servicios()).ejecutar(self._actor(request, datos), sesion_id, datos), status=201)


class ControlesView(VistaAula):
    def post(self, request, sesion_id: str):
        datos = request.data or {}
        return Response(cu.CambiarControl(servicios()).ejecutar(
            self._actor(request, datos), sesion_id, str(datos.get("tipo") or ""), bool(datos.get("activo", True)),
            str(datos.get("motivo") or "")))


class DistribucionesView(VistaAula):
    def post(self, request, sesion_id: str):
        datos = request.data or {}
        return Response(cu.Distribuir(servicios()).ejecutar(self._actor(request, datos), sesion_id, datos), status=201)


class DistribucionAccionView(VistaAula):
    def post(self, request, sesion_id: str, distribucion_id: str, accion: str):
        datos = request.data or {}
        if accion == "cerrar":
            return Response(cu.CerrarDistribucion(servicios()).ejecutar(self._actor(request, datos), sesion_id, distribucion_id))
        if accion == "resultados":
            return Response(cu.MostrarResultados(servicios()).ejecutar(self._actor(request, datos), sesion_id, distribucion_id))
        if accion == "confirmar":
            return Response(cu.ConfirmarEntrega(servicios()).ejecutar(
                sesion_id, distribucion_id, str(datos.get("participante_id") or ""), str(datos.get("estado") or "entregado")))
        return Response({"detail": f"Acción desconocida «{accion}».", "codigo": "datos_invalidos"}, status=400)


class AvisosView(VistaAula):
    def post(self, request, sesion_id: str):
        datos = request.data or {}
        return Response(cu.EnviarAviso(servicios()).ejecutar(
            self._actor(request, datos), sesion_id, str(datos.get("texto") or ""), datos.get("participante_id") or None), status=201)


class CodigoRotarView(VistaAula):
    def post(self, request, sesion_id: str):
        return Response(cu.RotarCodigo(servicios()).ejecutar(self._actor(request, request.data or {}), sesion_id))


class SesionTransicionView(VistaAula):
    def post(self, request, sesion_id: str, accion: str):
        datos = request.data or {}
        actor = self._actor(request, datos)
        if accion == "suspender":
            return Response(cu.SuspenderSesion(servicios()).ejecutar(actor, sesion_id, str(datos.get("causa") or "manual")))
        if accion == "reanudar":
            return Response(cu.ReanudarSesion(servicios()).ejecutar(actor, sesion_id))
        if accion == "cerrar":
            return Response(cu.CerrarSesion(servicios()).ejecutar(actor, sesion_id, str(datos.get("origen") or "profesor"),
                                                                  bool(datos.get("forzar", False))))
        return Response({"detail": f"Acción desconocida «{accion}».", "codigo": "datos_invalidos"}, status=400)
