"""
El pase de medios en la dirección (bugfix 01 · QA-27): cómo llega a un medio quien no puede mandar `Authorization`.

Un video, un audio o una imagen del aula los pide el VISOR (la `<video>`/`<audio>` de la WebView, `Image` de MAUI en Windows y en Android), no el código de la
app, y el visor no sabe poner cabeceras. Con `AVACOM_LMS_EXIGIR_SESION=1` —cómo deja el nodo el instalador— esos GET daban 401 y el reproductor lo contaba como
«formato no compatible». Tres piezas lo resuelven sin abrir el nodo:

  · `con_pase(ruta)` — lo llaman los constructores de URL de medios (aula, modo de estudio, evaluación) mientras sirven una petición con sesión:
    `/api/aula/cursos/C/medios/M/?fuente=biblioteca` → `/api/m/<pase>/aula/cursos/C/medios/M/?fuente=biblioteca`. Sin sesión la ruta queda como estaba.
  · `PaseDeMediosMiddleware` — si la ruta empieza por `/api/m/`, valida el pase (`PaseDeMedios.resolver`: JWT `tipo=medio`, atado a la sesión y vivo mientras ella
    viva), comprueba que sea GET/HEAD sobre una ruta de MEDIOS y reescribe el camino a la ruta normal. Las vistas no se enteran: ven la misma persona de la sesión.
  · `AutenticacionPaseDeMedios` — la clase de autenticación de DRF que entrega esa persona a la vista (si la petición trajo pase).

El pase va en el CAMINO y no en `?token=` porque las simulaciones piden sus propios archivos con rutas relativas (`js/app.js`): un prefijo de camino se hereda, un
parámetro no. Un pase no abre la API, ni el expediente, ni la clase: sólo medios, y sólo mientras la sesión que lo emitió siga viva.
"""
from __future__ import annotations

import logging
import re

from django.http import HttpResponse, JsonResponse
from rest_framework.authentication import BaseAuthentication

from audit import contexto

from ..aplicacion.casos_uso import PaseDeMedios
from ..dominio import errores
from ..infraestructura.contenedor import servicios

log = logging.getLogger("avacom.acceso.medios")

PREFIJO = "/api/m/"

# Las únicas rutas que el pase abre (ya reescritas, sin `/api/`). Cada una conserva su propia autorización: la asignación que le alcanza al alumno, el medio
# que es de ESE examen, la política del curso.
RUTAS_DE_MEDIO = re.compile(
    r"^(?:aula/cursos/[^/]+/medios/[^/]+"
    r"|modo-estudio/asignaciones/[^/]+/medios/[^/]+"
    r"|evaluacion/intentos/[^/]+/medios/[^/]+)")

METODOS = ("GET", "HEAD")


def con_pase(ruta_api: str) -> str:
    """`/api/…` → `/api/m/<pase>/…` si esta petición tiene sesión; en otro caso, la ruta tal cual (modo prototipo sin sesión obligatoria, pruebas, consola)."""
    actual = contexto.actual()
    if not (actual.usuario_id and actual.sesion_id and ruta_api.startswith("/api/")) or ruta_api.startswith(PREFIJO):
        return ruta_api
    try:
        pase = PaseDeMedios(servicios()).emitir(actual.usuario_id, actual.sesion_id)
    except Exception:   # noqa: BLE001 — sin pase la ruta sigue funcionando para quien pueda mandar cabeceras
        log.exception("No se pudo emitir el pase de medios", extra={"evento": "acceso.pase_medios_no_emitido"})
        return ruta_api
    return f"{PREFIJO}{pase}/{ruta_api[len('/api/'):]}"


def _con_cors(respuesta: HttpResponse) -> HttpResponse:
    """Los subtítulos (`<track>`) se piden como recurso de OTRO origen: la página del reproductor se carga desde `about:blank` en Windows y desde
    `file:///android_asset/` en Android. Sin estas cabeceras el navegador los descarta en silencio. Sólo las llevan las direcciones con pase, que ya son
    una capacidad en sí mismas."""
    respuesta["Access-Control-Allow-Origin"] = "*"
    respuesta["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
    respuesta["Access-Control-Allow-Headers"] = "Range, If-Range, Content-Type"
    respuesta["Access-Control-Expose-Headers"] = "Content-Length, Content-Range, Accept-Ranges, Content-Type"
    return respuesta


def _rechazo(estado: int, codigo: str, detalle: str) -> HttpResponse:
    return _con_cors(JsonResponse({"detail": detalle, "codigo": codigo}, status=estado))


class PaseDeMediosMiddleware:
    """Ver el docstring del módulo. Va dentro del middleware de auditoría (que ya fijó el `corr`) y delante de `CommonMiddleware`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ruta = request.path_info
        if not ruta.startswith(PREFIJO):
            return self.get_response(request)
        pase, _, resto = ruta[len(PREFIJO):].partition("/")
        if request.method == "OPTIONS":
            return _con_cors(HttpResponse(status=204))
        if request.method not in METODOS:
            return _rechazo(405, "pase_de_medios_metodo", "Un pase de medios sólo sirve para leer (GET o HEAD).")
        if not pase or not RUTAS_DE_MEDIO.match(resto):
            return _rechazo(403, "pase_de_medios_fuera_de_alcance", "Un pase de medios sólo abre los medios de un curso, de una asignación o de un examen.")
        try:
            principal = PaseDeMedios(servicios()).resolver(pase)
        except errores.ErrorAcceso as error:
            log.warning("Pase de medios rechazado: %s", error.codigo,
                        extra={"evento": "acceso.pase_medios_rechazado", "ruta": "sad", "detalle": {"codigo": error.codigo}})
            return _rechazo(error.http, error.codigo, error.detalle)
        # Desde aquí la petición ES la ruta normal: el registro de auditoría y las vistas ven `/api/aula/…`, nunca el pase.
        normal = "/api/" + resto
        request.path = request.path.replace(f"{PREFIJO}{pase}/", "/api/", 1)
        request.path_info = normal
        request.avacom_principal_medio = principal
        return _con_cors(self.get_response(request))


class AutenticacionPaseDeMedios(BaseAuthentication):
    """Entrega a DRF la persona que resolvió el middleware. Sin pase en la petición no opina (sigue `AutenticacionJwt`)."""

    def authenticate(self, request):
        principal = getattr(request._request, "avacom_principal_medio", None)
        if principal is None:
            return None
        contexto.establecer(usuario_id=principal.usuario_id, rol_codigo=principal.rol_codigo, sesion_id=principal.sesion_id,
                            dispositivo_id=contexto.actual().dispositivo_id or principal.dispositivo_id)
        return principal, None

    def authenticate_header(self, request):
        return "Bearer"
