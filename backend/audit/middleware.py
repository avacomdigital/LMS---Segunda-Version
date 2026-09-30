"""
Middleware de correlación y contexto de auditoría (§2.5 y §4.3 del prompt de MOD-019).

    1. Asigna un `corr` (UUID) a cada petición —o respeta el que trae `X-Avacom-Correlacion`— y lo devuelve en la
       respuesta con la misma cabecera. Ese mismo `corr` viaja al asiento de bitácora y al evento de cola.
    2. Identifica el aparato (019-01): `X-Avacom-Dispositivo: <dispositivo_id>` se valida contra m09_dispositivo
       (activo y no bloqueado) y se coloca en el contexto. Sin cabecera, o con una inválida, queda NULL: nunca se inventa.
    3. Deja una línea en backend-app.log por petición, con `ruta` happy/sad/bad deducida del estado HTTP.
    4. Toda respuesta 403 deja un asiento `acceso.denegado` con los roles activos, el permiso solicitado y la ruta
       (019-08). Lo hace aquí, en un solo sitio, para que ningún módulo pueda olvidarlo.
"""
from __future__ import annotations

import json
import logging
import re
import time

from . import contexto
from .logging_setup import CANAL_DISPOSITIVO, LOGGER_APP, ruta_por_estado

log = logging.getLogger(LOGGER_APP)

CABECERA_CORRELACION = "X-Avacom-Correlacion"
CABECERA_DISPOSITIVO = "X-Avacom-Dispositivo"
_CORR_VALIDO = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
_ID_VALIDO = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# Rutas que no dejan línea por petición (ruido): el latido y el canal de estáticos.
_SILENCIOSAS = ("/api/dispositivos/latido/", "/static/")


def corr_de_cabecera(valor: str | None) -> str:
    valor = (valor or "").strip()
    return valor if _CORR_VALIDO.match(valor) else contexto.nuevo_corr()


def dispositivo_validado(valor: str | None) -> str | None:
    """El id de m09_dispositivo si existe, está activo y no está bloqueado; si no, None (y una línea WARNING)."""
    valor = (valor or "").strip()
    if not valor or not _ID_VALIDO.match(valor):
        return None
    try:
        from device_manager.models import Dispositivo   # frontera: sólo aquí, y perezoso
        fila = Dispositivo.objects.filter(pk=valor).values("activo", "bloqueado").first()
    except Exception:   # noqa: BLE001 — sin tabla aún (migraciones) o base caída: nunca se inventa
        log.exception("No se pudo validar la cabecera de dispositivo", extra={"canal": CANAL_DISPOSITIVO, "evento": "dispositivo.cabecera_error"})
        return None
    if fila is None:
        log.warning("La cabecera X-Avacom-Dispositivo no corresponde a ningún equipo registrado",
                    extra={"canal": CANAL_DISPOSITIVO, "evento": "dispositivo.cabecera_rechazada", "detalle": {"motivo": "no_registrado", "id": valor}})
        return None
    if not fila["activo"] or fila["bloqueado"]:
        log.warning("Petición desde un equipo retirado o bloqueado",
                    extra={"canal": CANAL_DISPOSITIVO, "evento": "dispositivo.cabecera_rechazada",
                           "detalle": {"motivo": "bloqueado" if fila["bloqueado"] else "inactivo", "dispositivo_id": valor}})
        return None
    return valor


class CorrelacionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        corr = corr_de_cabecera(request.headers.get(CABECERA_CORRELACION))
        dispositivo_id = dispositivo_validado(request.headers.get(CABECERA_DISPOSITIVO))
        token = contexto.establecer(corr=corr, dispositivo_id=dispositivo_id, origen=contexto.ORIGEN_API,
                                    usuario_id=None, rol_codigo=None, sesion_id=None)
        request.avacom_corr = corr
        inicio = time.monotonic()
        try:
            try:
                respuesta = self.get_response(request)
            except Exception:
                self._registrar(request, 500, inicio, excepcion=True)
                raise
            self._contexto_de_sesion(request)
            self._registrar(request, respuesta.status_code, inicio)
            respuesta[CABECERA_CORRELACION] = corr
            if respuesta.status_code == 403:
                self._denegacion(request, respuesta)
            return respuesta
        finally:
            contexto.restaurar(token)

    # ------------------------------------------------------------------ apoyo
    @staticmethod
    def _contexto_de_sesion(request) -> None:
        """DRF autentica dentro de la vista y deja el Principal en request.user: se copia al contexto para el log."""
        principal = getattr(request, "user", None)
        usuario_id = getattr(principal, "usuario_id", None)
        if usuario_id:
            contexto.establecer(usuario_id=usuario_id, rol_codigo=getattr(principal, "rol_codigo", None),
                                sesion_id=getattr(principal, "sesion_id", None),
                                dispositivo_id=contexto.actual().dispositivo_id or getattr(principal, "dispositivo_id", None))

    @staticmethod
    def _registrar(request, status: int, inicio: float, excepcion: bool = False) -> None:
        ruta = request.path
        if any(ruta.startswith(s) for s in _SILENCIOSAS) and status < 400:
            return
        cual = ruta_por_estado(status, excepcion)
        nivel = logging.ERROR if cual == "bad" else logging.INFO
        try:
            log.log(nivel, "%s %s → %s", request.method, ruta, status, exc_info=excepcion,
                    extra={"evento": "http.peticion", "ruta": cual,
                           "detalle": {"metodo": request.method, "path": ruta, "estado": status,
                                       "ms": int((time.monotonic() - inicio) * 1000)}})
        except Exception:   # noqa: BLE001 — el logger nunca eleva al llamador
            pass

    @staticmethod
    def _denegacion(request, respuesta) -> None:
        """Un 403 es un hecho auditable: quién, con qué roles, qué permiso pidió y sobre qué ruta (019-08, VER-01)."""
        cuerpo: dict = {}
        try:
            contenido = getattr(respuesta, "content", b"")
            if contenido:
                cuerpo = json.loads(contenido.decode("utf-8"))
        except Exception:   # noqa: BLE001 — cuerpo no JSON: se asienta sin detalle
            cuerpo = {}
        if not isinstance(cuerpo, dict):
            cuerpo = {}
        try:
            from . import servicios
            servicios.registrar_denegacion(
                codigo=str(cuerpo.get("codigo") or "sin_permiso"),
                permiso=cuerpo.get("permiso"),
                metodo=request.method, ruta=request.path,
                objeto=cuerpo.get("objeto"),
            )
        except Exception:   # noqa: BLE001 — la denegación ya se dio; no fallar la respuesta por el asiento
            log.exception("No se pudo asentar la denegación", extra={"evento": "auditoria.denegacion_no_asentada", "ruta": "bad"})
