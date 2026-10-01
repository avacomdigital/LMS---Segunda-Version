"""
ESTE ARCHIVO ES PARA EL USO DE WEB SOCKETS (Django Channels) EN EL AULA — MOD-007 · Classroom Engine.

Aquí, y sólo aquí, vive todo lo que habla por WebSocket: el consumidor de la sesión de clase, su ruta y las
estadísticas de entrega. Las vistas REST (`views.py`) y los casos de uso NO importan nada de Channels; el aviso
a las pantallas sale por el puerto `TiempoReal` (`infraestructura/tiempo_real.py`).

    ws://<nodo>:8000/ws/aula/sesiones/<sesion_id>/?rol=docente
    ws://<nodo>:8000/ws/aula/sesiones/<sesion_id>/?rol=estudiante&participante=<participante_id>
        (opcional: &token=<JWT de MOD-001>; con AVACOM_LMS_EXIGIR_SESION=1 es obligatorio)

Lo que el servidor envía (JSON, una línea por mensaje):
    {"tipo":"hola", "rol", "sesion":{id,estado}, "servidor_en", "latido_ms", "respaldo_ms", "conteo"?, "participante"?}
        al conectar. El profesor recibe el conteo de participantes: es lo primero que pinta el recuadro verde.
    {"tipo":"conteo", conectados, reconectando, esperando, salieron, total, "emitido_en"}
        sólo al profesor, cada vez que cambia la presencia de alguien (007-01, 007-04).
    {"tipo":"cambio", "que", "carga", "emitido_en"}
        algo cambió en la sesión: selector · controles · distribucion · aviso · presencia · codigo · sesion · resultados ·
        entregas · ayuda · proyeccion. NUNCA lleva contenido académico: el cliente pide el estado por HTTP.
    {"tipo":"pong", "t", "servidor_en"}   respuesta a {"tipo":"ping","t":…}: sirve para medir el viaje de ida y vuelta.
    {"tipo":"error", "codigo", "detalle"} y después el cierre con un código 44xx.

Lo que el cliente envía:
    {"tipo":"latido", "telemetria":{espacio_libre_mb, bateria_pct}?}   cada `latido_ms` (sólo tabletas)
    {"tipo":"presencia", "estado":"conectado|reconectando|salio", "telemetria"?}   declaración de presencia
    {"tipo":"ping", "t":<lo que sea>}

Códigos de cierre: 4401 sesión requerida o inválida · 4403 sin permiso o participante expulsado · 4404 sesión o
participante inexistentes · 4400 petición mal formada.

Si el socket se cae, nada se pierde: el HTTP sigue siendo la fuente de verdad y los clientes vuelven a sondear
hasta reconectar. Una tableta cuyo socket se cierra y no vuelve en unos segundos pasa a «reconectando».
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.urls import re_path

from ..aplicacion import casos_uso_tiempo_real as tr
from ..aplicacion.puertos import Actor
from ..dominio import errores
from ..dominio import sesion as dom
from ..infraestructura.contenedor import servicios
from ..infraestructura.tiempo_real import (   # noqa: F401 — TIPO_MENSAJE documenta el nombre del manejador
    TIPO_MENSAJE,
    grupo_alumnos,
    grupo_docente,
    grupo_participante,
    mensaje_conteo,
    registrar_bucle,
)

log = logging.getLogger("avacom.aula.websockets")

GRACIA_DESCONEXION_S = 3.0   # una tableta cuyo socket no vuelve en este tiempo pasa a «reconectando»

CIERRE_SESION_REQUERIDA, CIERRE_SIN_PERMISO, CIERRE_NO_EXISTE, CIERRE_PETICION = 4401, 4403, 4404, 4400


# --------------------------------------------------------------------------- estadísticas

class Estadisticas:
    """Cuántos sockets hay por sesión y cuánto tardó cada aviso en llegar al socket desde que se confirmó el hecho
    (007-01: «hoy es sondeo de 2 s sin medir»). Es de este proceso y se reinicia con él."""

    def __init__(self):
        self.conexiones: dict[tuple[str, str, str], int] = {}
        self.demoras: deque[int] = deque(maxlen=1000)
        self.enviados = 0

    def conectar(self, sesion_id: str, rol: str, participante_id: str) -> None:
        clave = (sesion_id, rol, participante_id)
        self.conexiones[clave] = self.conexiones.get(clave, 0) + 1

    def desconectar(self, sesion_id: str, rol: str, participante_id: str) -> None:
        clave = (sesion_id, rol, participante_id)
        restantes = self.conexiones.get(clave, 0) - 1
        if restantes > 0:
            self.conexiones[clave] = restantes
        else:
            self.conexiones.pop(clave, None)

    def sockets_de(self, sesion_id: str, participante_id: str) -> int:
        return self.conexiones.get((sesion_id, "estudiante", participante_id), 0)

    def entrega(self, demora_ms: int) -> None:
        self.enviados += 1
        self.demoras.append(max(0, int(demora_ms)))

    def resumen(self) -> dict:
        por_sesion: dict[str, dict] = {}
        for (sesion_id, rol, _), n in self.conexiones.items():
            ficha = por_sesion.setdefault(sesion_id, {"docentes": 0, "alumnos": 0})
            ficha["docentes" if rol == "docente" else "alumnos"] += n
        ordenadas = sorted(self.demoras)

        def percentil(p: float) -> int | None:
            return ordenadas[min(len(ordenadas) - 1, int(len(ordenadas) * p))] if ordenadas else None

        return {"sesiones": por_sesion, "avisos_entregados": self.enviados,
                "demora_ms": {"muestras": len(ordenadas), "p50": percentil(0.50), "p95": percentil(0.95),
                              "maximo": ordenadas[-1] if ordenadas else None},
                "objetivo_ms": 3000}   # BR-049: el foco llega a los dispositivos en seguimiento en 3 s como máximo


ESTADISTICAS = Estadisticas()
_desconexiones: dict[tuple[str, str], asyncio.Task] = {}


# ------------------------------------------------------------------------------ sesión (JWT)

def _contexto_ws(principal, dispositivo_cabecera: str | None, corr: str | None):
    """MOD-019: lo que corre por este socket deja asientos y líneas con origen `ws`, la persona de la sesión, el aparato
    (cabecera X-Avacom-Dispositivo del handshake, validada contra m09_dispositivo, o el de la sesión) y un `corr` por conexión."""
    from audit import contexto
    from audit.middleware import dispositivo_validado
    dispositivo_id = dispositivo_validado(dispositivo_cabecera) or (getattr(principal, "dispositivo_id", None) if principal else None)
    return contexto.con(origen=contexto.ORIGEN_WS, corr=corr or contexto.nuevo_corr(),
                        usuario_id=getattr(principal, "usuario_id", None), rol_codigo=getattr(principal, "rol_codigo", None),
                        sesion_id=getattr(principal, "sesion_id", None), dispositivo_id=dispositivo_id)


def _cabecera(scope, nombre: bytes) -> str | None:
    for clave, valor in scope.get("headers") or []:
        if clave.lower() == nombre:
            return valor.decode("utf-8", "ignore")
    return None


def _principal(token: str):
    """El Principal de MOD-001 si el token es válido; None si no hay token. Un token roto lanza ErrorAcceso."""
    if not token:
        return None
    from acceso.aplicacion.casos_uso import ResolverPrincipal
    from acceso.infraestructura.contenedor import servicios as servicios_acceso
    return ResolverPrincipal(servicios_acceso()).ejecutar(token)


def _actor_de(principal, rol: str) -> Actor | None:
    if principal is None:
        return None
    return Actor(id=principal.usuario_id, nivel=int(principal.nivel), autenticado=True,
                 dispositivo=str(principal.dispositivo_id or ""), sesion_usuario_id=principal.sesion_id, principal=principal)


def _conectar(sesion_id: str, rol: str, participante_id: str, principal, dispositivo: str | None = None, corr: str | None = None) -> dict:
    """Valida quién se conecta y arma el saludo (síncrono: toca la base)."""
    s = servicios()
    with _contexto_ws(principal, dispositivo, corr):
        if rol == "docente" and principal is not None:
            # Con sesión, ver la clase en vivo exige el permiso y ser su titular (o la administración).
            with s.uow() as uow:
                sesion = uow.sesiones.sesion(sesion_id)
            if sesion is not None:
                s.autorizacion.exigir(_actor_de(principal, rol), dom.P_RESULTS_VIEW, sesion)
        persona = principal.usuario_id if (principal is not None and rol == "estudiante") else None
        return tr.ConectarTiempoReal(s).ejecutar(sesion_id, rol, participante_id or None, persona)


def _latido(sesion_id: str, participante_id: str, estado: str | None, telemetria: dict | None, principal,
            dispositivo: str | None = None, corr: str | None = None) -> dict:
    persona = principal.usuario_id if principal is not None else None
    with _contexto_ws(principal, dispositivo, corr):
        return tr.LatidoParticipante(servicios()).ejecutar(sesion_id, participante_id, estado, telemetria, persona)


def _perder(sesion_id: str, participante_id: str, dispositivo: str | None = None, corr: str | None = None) -> bool:
    with _contexto_ws(None, dispositivo, corr):
        return tr.PerderConexion(servicios()).ejecutar(sesion_id, participante_id)


def _conteo(sesion_id: str) -> dict:
    return mensaje_conteo(sesion_id)


# ------------------------------------------------------------------------------- consumidor

class ConsumidorAula(AsyncJsonWebsocketConsumer):
    """Un socket por pantalla conectada a una sesión de clase. Docente: recibe avisos y el conteo. Estudiante: recibe
    avisos, manda latido y declara su presencia."""

    sesion_id = ""
    rol = "estudiante"
    participante_id = ""
    principal = None
    grupos: list[str]

    # ---------------------------------------------------------------- conexión
    async def connect(self):
        self.grupos = []
        self.sesion_id = self.scope["url_route"]["kwargs"]["sesion_id"]
        consulta = parse_qs(self.scope.get("query_string", b"").decode("utf-8", "ignore"))
        self.rol = "docente" if (consulta.get("rol") or [""])[0] == "docente" else "estudiante"
        self.participante_id = (consulta.get("participante") or [""])[0]
        token = (consulta.get("token") or [""])[0]
        # MOD-019: el aparato se declara en el handshake (cabecera) o, si el cliente no puede poner cabeceras, en la consulta.
        self.dispositivo = _cabecera(self.scope, b"x-avacom-dispositivo") or (consulta.get("dispositivo") or [""])[0] or None
        self.corr = _cabecera(self.scope, b"x-avacom-correlacion") or None
        await self.accept()   # se acepta y luego se cierra con código propio: el cliente puede saber por qué
        registrar_bucle(asyncio.get_running_loop())

        try:
            self.principal = await database_sync_to_async(_principal)(token)
        except Exception:   # noqa: BLE001 — token roto o caducado (ErrorAcceso de MOD-001)
            return await self._rechazar(CIERRE_SESION_REQUERIDA, "sesion_invalida", "El token no es válido o caducó.")
        if self.principal is None and (settings.AVACOM_LMS_EXIGIR_SESION or token):
            return await self._rechazar(CIERRE_SESION_REQUERIDA, "sesion_requerida", "Hace falta iniciar sesión.")
        if self.rol == "estudiante" and not self.participante_id:
            return await self._rechazar(CIERRE_PETICION, "datos_invalidos", "Falta el participante.")

        try:
            saludo = await database_sync_to_async(_conectar)(self.sesion_id, self.rol, self.participante_id, self.principal, self.dispositivo, self.corr)
        except errores.NoEncontrado as error:
            return await self._rechazar(CIERRE_NO_EXISTE, error.codigo, error.detalle)
        except (errores.SinPermiso, errores.ParticipanteExpulsado) as error:
            return await self._rechazar(CIERRE_SIN_PERMISO, error.codigo, error.detalle)

        grupos = [grupo_docente(self.sesion_id)] if self.rol == "docente" else [
            grupo_alumnos(self.sesion_id), grupo_participante(self.sesion_id, self.participante_id)]
        for grupo in grupos:
            await self.channel_layer.group_add(grupo, self.channel_name)
        self.grupos = grupos
        ESTADISTICAS.conectar(self.sesion_id, self.rol, self.participante_id if self.rol == "estudiante" else "")
        pendiente = _desconexiones.pop((self.sesion_id, self.participante_id), None)
        if pendiente is not None:
            pendiente.cancel()   # volvió antes de que pasara la gracia: nunca dejó de estar conectada
        await self.send_json({"tipo": "hola", "rol": self.rol, **saludo})
        if self.rol == "estudiante":
            # Abrir el socket es declararse conectado: reabre la sesión de alumno y avisa al profesor (007-04).
            try:
                await database_sync_to_async(_latido)(self.sesion_id, self.participante_id, dom.CONECTADO, None, self.principal, self.dispositivo, self.corr)
            except errores.ErrorAula:
                log.debug("No se pudo declarar la presencia al conectar", exc_info=True)

    async def _rechazar(self, codigo_cierre: int, codigo: str, detalle: str):
        await self.send_json({"tipo": "error", "codigo": codigo, "detalle": detalle})
        await self.close(code=codigo_cierre)

    async def disconnect(self, code):
        for grupo in getattr(self, "grupos", []):
            await self.channel_layer.group_discard(grupo, self.channel_name)
        if not self.grupos:
            return
        ESTADISTICAS.desconectar(self.sesion_id, self.rol, self.participante_id if self.rol == "estudiante" else "")
        if self.rol == "estudiante" and self.participante_id and not ESTADISTICAS.sockets_de(self.sesion_id, self.participante_id):
            clave = (self.sesion_id, self.participante_id)
            _desconexiones[clave] = asyncio.ensure_future(self._reconectando_si_no_vuelve(*clave))

    @staticmethod
    async def _reconectando_si_no_vuelve(sesion_id: str, participante_id: str):
        try:
            await asyncio.sleep(GRACIA_DESCONEXION_S)
            if ESTADISTICAS.sockets_de(sesion_id, participante_id):
                return
            await database_sync_to_async(_perder)(sesion_id, participante_id)
        except asyncio.CancelledError:
            raise
        except Exception:   # noqa: BLE001 — el barrido por latido lo corregirá
            log.debug("No se pudo marcar «reconectando» tras cerrar el socket", exc_info=True)
        finally:
            _desconexiones.pop((sesion_id, participante_id), None)

    # ------------------------------------------------------------- lo que manda el cliente
    async def receive_json(self, contenido, **kwargs):
        if not isinstance(contenido, dict):
            return await self.send_json({"tipo": "error", "codigo": "datos_invalidos", "detalle": "Se esperaba un objeto JSON."})
        tipo = contenido.get("tipo")
        if tipo == "ping":
            return await self.send_json({"tipo": "pong", "t": contenido.get("t"), "servidor_en": int(time.time() * 1000)})
        if self.rol != "estudiante":
            return   # el profesor sólo escucha: sus órdenes viajan por HTTP, con su permiso y su auditoría
        if tipo in ("latido", "presencia"):
            estado = contenido.get("estado") if tipo == "presencia" else None
            telemetria = contenido.get("telemetria") if isinstance(contenido.get("telemetria"), dict) else None
            try:
                await database_sync_to_async(_latido)(self.sesion_id, self.participante_id, estado, telemetria, self.principal, self.dispositivo, self.corr)
            except errores.ParticipanteExpulsado as error:
                await self._rechazar(CIERRE_SIN_PERMISO, error.codigo, error.detalle)
            except errores.ErrorAula as error:
                await self.send_json({"tipo": "error", "codigo": error.codigo, "detalle": error.detalle})

    # -------------------------------------------------------------- lo que llega del grupo
    async def aula_mensaje(self, evento):
        """Manejador de `{"type": TIPO_MENSAJE}` ("aula.mensaje" → `aula_mensaje`): reenvía el aviso tal cual y mide
        cuánto tardó desde que se confirmó el hecho hasta que salió por el socket."""
        mensaje = evento["mensaje"]
        emitido = mensaje.get("emitido_en")
        await self.send_json(mensaje)
        if emitido:
            ESTADISTICAS.entrega(int(time.time() * 1000) - int(emitido))


websocket_urlpatterns = [
    re_path(r"^ws/aula/sesiones/(?P<sesion_id>[^/]+)/$", ConsumidorAula.as_asgi()),
]
