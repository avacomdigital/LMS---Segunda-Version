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
from cola_medios import servicio as cola

from ..aplicacion import casos_uso as cu
from ..aplicacion import casos_uso_actividad as ca
from ..aplicacion import casos_uso_cierre as cc
from ..aplicacion import casos_uso_tiempo_real as ct
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
    def _persona(request) -> str | None:
        """Con sesión (MOD-001) la tableta sólo habla por sí misma: la persona es la del JWT."""
        principal = principal_de(request)
        return principal.usuario_id if principal is not None else None

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare, como en el expediente."""
        principal = principal_de(request)
        datos = datos or {}
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel),
                         autenticado=True, dispositivo=str(datos.get("dispositivo") or principal.dispositivo_id or ""),
                         sesion_usuario_id=principal.sesion_id, principal=principal)
        actor_id = str(datos.get("profesor_id") or datos.get("actor") or request.query_params.get("actor") or "docente")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("profesor_rotulo") or datos.get("actor_rotulo") or "")[:120],
                     nivel=2, autenticado=False, dispositivo=str(datos.get("dispositivo") or "")[:64])


def _respuesta_bytes(request, medio: Bytes, metodo: str):
    """Bytes de la cola de medios del nodo (caché en disco con Range), bytes generados (ejemplo) con soporte de Range, o paso a través del flujo de la biblioteca."""
    de_la_cola = cola.responder(request, medio, metodo)
    if de_la_cola is not None:
        return de_la_cola
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

    def _servir(self, request, curso_ref: str, media_ref: str, ruta: str | None, metodo: str):
        """Por la cola de medios del nodo: lo que 35 tabletas piden a la vez se trae de la fuente una sola vez. Sin la cola, paso a través como siempre."""
        fuente, rango = self._fuente(request), request.headers.get("Range")
        medio = cola.abrir_medio(fuente=fuente, curso_ref=curso_ref, media_ref=media_ref, ruta=ruta, rango=rango, metodo=metodo,
                                 modulo=cola.MODULO_AULA, prioridad=cola.CLASE,
                                 directo=lambda: cu.AbrirMedio(servicios()).ejecutar(curso_ref, media_ref, ruta, rango, metodo, fuente))
        return _respuesta_bytes(request, medio, metodo)

    def get(self, request, curso_ref: str, media_ref: str, ruta: str | None = None):
        return self._servir(request, curso_ref, media_ref, ruta, "GET")

    def head(self, request, curso_ref: str, media_ref: str, ruta: str | None = None):
        return self._servir(request, curso_ref, media_ref, ruta, "HEAD")


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
        datos = dict(request.data or {})
        principal = principal_de(request)
        if principal is not None:   # con sesión, la persona y su sesión de usuario las fija el JWT, no el cuerpo
            datos["persona_id"] = principal.usuario_id
            datos["sesion_usuario_id"] = principal.sesion_id
        origen = request.META.get("REMOTE_ADDR", "")
        if origen in ("127.0.0.1", "::1"):
            origen = ""   # el propio nodo no se frena por dirección: el freno por tableta sigue valiendo
        resultado = cu.UnirseASesion(servicios()).ejecutar(datos, origen=origen)
        return Response(resultado, status=status.HTTP_201_CREATED if resultado.get("nuevo") else status.HTTP_200_OK)


class ParticipanteAccionView(VistaAula):
    """admitir · rechazar · expulsar (el profesor), ayuda (la tableta levanta o baja la mano), atender (el profesor la
    baja) y proyeccion (DEC-034: estado de la proyección de la pantalla de un alumno)."""

    ACCIONES = {"admitir": cu.AdmitirParticipante, "rechazar": cu.RechazarParticipante, "expulsar": cu.ExpulsarParticipante}

    def post(self, request, sesion_id: str, participante_id: str, accion: str):
        datos = request.data or {}
        if accion == "ayuda":
            return Response(ct.SolicitarAyuda(servicios()).ejecutar(
                sesion_id, participante_id, bool(datos.get("activa", True)), self._persona(request)))
        if accion == "atender":
            return Response(ct.AtenderAyuda(servicios()).ejecutar(self._actor(request, datos), sesion_id, participante_id))
        if accion == "proyeccion":
            return Response(ct.ProyectarAlumno(servicios()).ejecutar(
                self._actor(request, datos), sesion_id, participante_id, bool(datos.get("activa", True))))
        caso = self.ACCIONES.get(accion)
        if caso is None:
            return Response({"detail": f"Acción desconocida «{accion}».", "codigo": "datos_invalidos"}, status=400)
        actor = self._actor(request, datos)
        if accion == "admitir":
            return Response(caso(servicios()).ejecutar(actor, sesion_id, participante_id))
        return Response(caso(servicios()).ejecutar(actor, sesion_id, participante_id, str(datos.get("motivo") or "")))


class PresenciaView(VistaAula):
    """FUN-073: la tableta declara su presencia y recibe el estado que debe pintar."""

    def post(self, request, sesion_id: str, participante_id: str):
        datos = request.data or {}
        desde = datos.get("avisos_desde")
        telemetria = datos.get("telemetria") if isinstance(datos.get("telemetria"), dict) else None
        return Response(cu.RegistrarPresencia(servicios()).ejecutar(
            sesion_id, participante_id, datos.get("estado"), str(datos.get("dispositivo") or ""),
            int(desde) if desde else None, self._persona(request), telemetria))


class EstadoTabletaView(VistaAula):
    """El estado que pinta una tableta. Con WebSocket (`websockets.py`) se pide cuando llega un aviso de cambio y como
    respaldo cada `tiempo_real.respaldo_ms`; sin socket, el cliente sondea cada `intervalo_sondeo_ms`. Cuenta como latido."""

    def get(self, request, sesion_id: str):
        q = request.query_params
        desde = q.get("avisos_desde")
        return Response(cu.EstadoParaTableta(servicios()).ejecutar(
            sesion_id, q.get("participante") or None, int(desde) if desde else None, self._persona(request)))


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
    def get(self, request, sesion_id: str, distribucion_id: str, accion: str):
        """`resultados`: el avance vivo del grupo en una actividad (sólo el profesor)."""
        if accion == "resultados":
            return Response(ca.ResultadosActividad(servicios()).ejecutar(self._actor(request), sesion_id, distribucion_id))
        return Response({"detail": f"Acción desconocida «{accion}».", "codigo": "datos_invalidos"}, status=400)

    def post(self, request, sesion_id: str, distribucion_id: str, accion: str):
        datos = request.data or {}
        if accion == "respuestas":
            return Response(ca.EnviarRespuestas(servicios()).ejecutar(
                sesion_id, distribucion_id, str(datos.get("participante_id") or ""), datos, self._persona(request)),
                status=status.HTTP_200_OK)
        if accion == "estudio":
            hasta = datos.get("hasta")
            return Response(cc.MarcarEstudio(servicios()).ejecutar(
                self._actor(request, datos), sesion_id, distribucion_id, bool(datos.get("disponible", True)),
                int(hasta) if hasta else None))
        if accion == "cerrar":
            return Response(cu.CerrarDistribucion(servicios()).ejecutar(self._actor(request, datos), sesion_id, distribucion_id))
        if accion == "resultados":
            return Response(cu.MostrarResultados(servicios()).ejecutar(self._actor(request, datos), sesion_id, distribucion_id))
        if accion == "confirmar":
            return Response(cu.ConfirmarEntrega(servicios()).ejecutar(
                sesion_id, distribucion_id, str(datos.get("participante_id") or ""), str(datos.get("estado") or "entregado"),
                self._persona(request)))
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


class EnvioDecisionView(VistaAula):
    """DEC-019: el profesor acepta o descarta lo que llegó fuera de la ventana de gracia."""

    def post(self, request, sesion_id: str, distribucion_id: str, intento_id: str, decision: str):
        datos = request.data or {}
        return Response(ca.DecidirEnvio(servicios()).ejecutar(self._actor(request, datos), sesion_id, distribucion_id, intento_id, decision))


class AnclajeView(VistaAula):
    """BR-039 / BR-040: el anclaje curricular es opcional y puede asignarse después de cerrar la clase."""

    def get(self, request, sesion_id: str):
        return Response(cc.SugerirAnclaje(servicios()).ejecutar(sesion_id))

    def post(self, request, sesion_id: str):
        datos = request.data or {}
        return Response(cc.AnclarSesion(servicios()).ejecutar(self._actor(request, datos), sesion_id, datos.get("nodos") or []))


class TiempoRealView(VistaAula):
    """Diagnóstico del canal en tiempo real: sockets por sesión y cuánto tarda en llegar cada aviso (007-01)."""

    def get(self, request):
        from .websockets import ESTADISTICAS   # sólo aquí: el resto de las vistas no conoce Channels
        return Response(ESTADISTICAS.resumen())
