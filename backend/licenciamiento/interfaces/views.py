"""
Rutas HTTP de MOD-018 (`/api/licencia/`, P-17). Las vistas sólo traducen HTTP ↔ casos de uso: no tocan el ORM.

  GET  estado/            license.read      el estado, la vigencia, la huella (sólo nivel y cifras), los límites, los módulos y los avisos
  GET  consumo/           license.read      equipos y usuarios frente a lo contratado, y la concurrencia (BR-063)
  GET  capacidades/       cualquier sesión  qué módulos están habilitados, SIN detalles de la licencia
  GET  copia/             license.read      el `.avlic` vigente, para guardar una copia bajo custodia de la institución (CAP-111; extensión: no está en P-17)
  POST solicitud/         license.activate  la solicitud (`.avreq`) de este equipo
  POST activar/           license.activate  instalar un `.avlic` (también reactivar el mismo tras una restauración)
  POST renovar/           license.renew     instalar un `.avlic` posterior de la misma licencia
  POST liberar/           license.activate  la prueba de liberación (`.avrel`); el equipo deja de usar la licencia
  POST reloj/confirmar/   license.activate  extensión: confirmar que la fecha de hoy es la correcta tras un salto sospechoso del reloj

Contrato de errores (el mismo del resto del backend, `{"detail", "codigo", …}`):
  DatosInvalidos / LicenciaInvalida → 400 (con `motivo`) · SinPermiso → 403 · NoEncontrado → 404 · Conflicto / HuellaNoCoincide → 409 ·
  NoDisponiblePorLicencia / CupoAgotado → 402 (nunca 403: el middleware de auditoría lo asentaría como «acceso denegado», VER-10).

Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor`.
Los archivos viajan en JSON: `archivo_b64` (los bytes del archivo) y `texto` (la variante `AVL1.`/`AVQ1.`/`AVR1.` para copiar como texto). Al activar o renovar se manda `licencia`
con el texto `AVL1.…`, o `archivo_b64` con los bytes del `.avlic`.
"""
from __future__ import annotations

import base64
import binascii
import logging

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from acceso.dominio import errores as errores_acceso
from acceso.interfaces.permisos import SesionSiSeExige, principal_de

from ..aplicacion import acciones
from ..aplicacion.base import Actor
from ..dominio import catalogos as cat
from ..dominio import errores
from ..infraestructura.contenedor import servicios

log = logging.getLogger("avacom.licenciamiento")


def _cuerpo(request) -> dict:
    datos = request.data
    if hasattr(datos, "dict") and not isinstance(datos, dict):
        datos = datos.dict()
    if datos in (None, ""):
        return {}
    if not isinstance(datos, dict):
        raise errores.DatosInvalidos("El cuerpo debe ser un objeto JSON.")
    return dict(datos)


def _archivo(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


class VistaLicencia(APIView):
    permission_classes = [SesionSiSeExige]

    def handle_exception(self, exc):
        if isinstance(exc, errores.ErrorLicencia):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, errores_acceso.ErrorAcceso):
            return Response({**exc.extra, "detail": exc.detalle, "codigo": exc.codigo}, status=exc.http)
        if isinstance(exc, exceptions.ValidationError):
            return Response({"detail": "Los datos enviados no tienen la forma esperada.", "codigo": "datos_invalidos", "errores": exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    @staticmethod
    def _actor(request, datos: dict | None = None) -> Actor:
        """Con sesión, quien firma el JWT. Sin sesión (Q-34), quien el cliente declare."""
        datos = datos or {}
        principal = principal_de(request)
        if principal is not None:
            return Actor(id=principal.usuario_id, rotulo=str(datos.get("actor_rotulo") or ""), nivel=int(principal.nivel), autenticado=True,
                         dispositivo_id=str(principal.dispositivo_id or ""), principal=principal, rol=str(principal.rol_codigo or ""))
        actor_id = str(datos.get("actor") or request.query_params.get("actor") or "")
        return Actor(id=actor_id[:64], rotulo=str(datos.get("actor_rotulo") or "")[:120], nivel=2, autenticado=False)


class EstadoView(VistaLicencia):
    def get(self, request):
        return Response(acciones.ConsultarEstado(servicios()).ejecutar(self._actor(request)))


class ConsumoView(VistaLicencia):
    def get(self, request):
        return Response(acciones.ConsultarConsumo(servicios()).ejecutar(self._actor(request)))


class CapacidadesView(VistaLicencia):
    def get(self, request):
        return Response(acciones.ConsultarCapacidades(servicios()).ejecutar(self._actor(request)))


class CopiaView(VistaLicencia):
    def get(self, request):
        r = acciones.ConsultarCopia(servicios()).ejecutar(self._actor(request))
        return Response({"archivo_b64": _archivo(r["archivo"]), "texto": r["texto"], "nombre": r["nombre"], "sha256": r["sha256"], "licencia": r["licencia"]})


class SolicitudView(VistaLicencia):
    def post(self, request):
        datos = _cuerpo(request)
        r = acciones.GenerarSolicitud(servicios()).ejecutar(self._actor(request, datos))
        return Response({"archivo_b64": _archivo(r["archivo"]), "texto": r["texto"], "nombre": r["nombre"], "nivel": r["nivel"], "k": r["k"], "factores": r["factores"],
                         "sha256": r["sha256"]}, status=status.HTTP_201_CREATED)


class _InstalarView(VistaLicencia):
    via = ""

    def post(self, request):
        datos = _cuerpo(request)
        # El permiso se comprueba ANTES de mirar el cuerpo: quien no puede activar no se entera de qué le faltaba al archivo (el caso de uso lo vuelve a comprobar).
        servicios().autorizacion.exigir(self._actor(request, datos), cat.P_RENOVAR if self.via == "renovar" else cat.P_ACTIVAR)
        licencia: bytes | str
        if isinstance(datos.get("licencia"), str) and datos["licencia"].strip():
            licencia = datos["licencia"].strip()                  # sólo se recortan los extremos (un copiar-pegar trae saltos de línea); el texto en sí se lee de forma estricta
        elif isinstance(datos.get("archivo_b64"), str):
            try:
                licencia = base64.b64decode(datos["archivo_b64"], validate=True)
            except (binascii.Error, ValueError):
                raise errores.LicenciaInvalida("formato") from None
        else:
            raise errores.DatosInvalidos("Falta la licencia: manda `licencia` (texto AVL1.…) o `archivo_b64` (los bytes del .avlic).")
        return Response(acciones.Instalar(servicios()).ejecutar(self._actor(request, datos), licencia, self.via))


class ActivarView(_InstalarView):
    via = "activar"


class RenovarView(_InstalarView):
    via = "renovar"


class LiberarView(VistaLicencia):
    def post(self, request):
        datos = _cuerpo(request)
        r = acciones.Liberar(servicios()).ejecutar(self._actor(request, datos))
        archivo, texto, nombre = r.pop("archivo"), r.pop("texto"), r.pop("nombre")
        return Response({"archivo_b64": _archivo(archivo), "texto": texto, "nombre": nombre, **r}, status=status.HTTP_201_CREATED)


class ConfirmarRelojView(VistaLicencia):
    def post(self, request):
        return Response(acciones.ConfirmarReloj(servicios()).ejecutar(self._actor(request, _cuerpo(request))))
