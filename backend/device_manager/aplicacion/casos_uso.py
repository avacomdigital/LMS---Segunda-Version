"""
Casos de uso de MOD-009 · Device Manager.

Dos familias:
  1. El inventario (RegistrarDispositivo, ListarDispositivos, VerDispositivo, ActualizarDispositivo,
     BloquearDispositivo, DesbloquearDispositivo, RegistrarLatido): lo que opera el técnico, el
     administrador o el profesor desde OPS, y lo que la tableta declara de sí misma.
  2. La sesión de alumno en el dispositivo (abrir_sesion_alumno, cerrar_sesion_alumno): la usa el
     aula (MOD-007) al unirse y al salir; se expone también como caso de uso para pruebas.

Las reglas viven en funciones de módulo que reciben la unidad de trabajo, para que el aula y el
login (`device_manager/servicios.py`) las ejecuten dentro de SU transacción sin abrir otra.
Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..dominio import dispositivo as dom
from ..dominio.errores import DispositivoBloqueado, DispositivoInactivo, NoEncontrado, NodoNoInstalado
from .puertos import Actor, Autorizacion, Reloj, UnidadDeTrabajo


@dataclass
class Servicios:
    uow: Callable[[], UnidadDeTrabajo]
    reloj: Reloj
    autorizacion: Autorizacion


def _id() -> str:
    return str(uuid.uuid4())


# =================================================================== reglas puras

def dto(dispositivo: dict, ahora: int, sesion_abierta: dict | None = None) -> dict:
    """Lo que ven OPS y la tableta. `identificador` se conserva junto a `identificador_hw` porque el
    registro de la tableta (CAP-053) lo envía con ese nombre desde el contrato de acceso."""
    return {
        **dispositivo,
        "identificador": dispositivo["identificador_hw"],
        "en_linea": dom.en_linea(dispositivo.get("ultimo_latido_en"), ahora),
        "sesion_abierta": ({"id": sesion_abierta["id"], "alumno_id": sesion_abierta["alumno_id"],
                            "iniciada_en": sesion_abierta["iniciada_en"]} if sesion_abierta else None),
    }


def organizacion_de(uow: UnidadDeTrabajo) -> str:
    org = uow.organizaciones.unica_id()
    if not org:
        raise NodoNoInstalado()
    return org


def resolver(uow: UnidadDeTrabajo, ahora: int, identificador_hw: str, nombre: str = "", tipo: str = dom.TABLETA,
             plataforma: str = "", version_app: str = "", actor: str = "") -> tuple[dict, bool]:
    """CAP-052/053: registra la tableta la primera vez que se presenta y, después, sólo la reconoce
    (idempotente por organización + huella). Devuelve (dispositivo, creado). Nunca la bloquea ni la
    activa: eso lo decide el aula o el administrador."""
    org = organizacion_de(uow)
    identificador_hw = dom.normalizar_identificador(identificador_hw)
    plataforma = dom.validar_plataforma(plataforma)
    existente = uow.dispositivos.por_identificador(org, identificador_hw)
    if existente:
        campos: dict = {"ultimo_latido_en": ahora}
        nombre = dom.normalizar_nombre(nombre)
        if nombre and nombre != existente["nombre"]:
            campos["nombre"] = nombre
        if plataforma and plataforma != existente["plataforma"]:
            campos["plataforma"] = plataforma
        if version_app and version_app[:32] != existente["version_app"]:
            campos["version_app"] = version_app[:32]
        if not dom.en_linea(existente["ultimo_latido_en"], ahora):
            uow.outbox.publicar("Dispositivo", existente["id"], dom.EV_RECONECTADO,
                                {"dispositivo_id": existente["id"], "silencio_ms": ahora - existente["ultimo_latido_en"], "instante": ahora})
        return uow.dispositivos.actualizar(existente["id"], **campos), False
    dispositivo = uow.dispositivos.crear({
        "id": _id(), "organizacion_id": org, "identificador_hw": identificador_hw,
        "nombre": dom.normalizar_nombre(nombre, por_defecto=identificador_hw), "tipo": dom.validar_tipo(tipo),
        "plataforma": plataforma, "version_app": str(version_app or "")[:32], "activo": True, "bloqueado": False,
        "registrado_en": ahora, "ultimo_latido_en": ahora,
    })
    uow.outbox.publicar("Dispositivo", dispositivo["id"], dom.EV_REGISTRADO, {
        "dispositivo_id": dispositivo["id"], "nombre": dispositivo["nombre"], "tipo": dispositivo["tipo"],
        "plataforma": plataforma, "instante": ahora})
    uow.auditoria.registrar(actor or "sistema", "dispositivos.registrado", "m09_dispositivo", dispositivo["id"],
                            nuevo={"identificador_hw": identificador_hw, "nombre": dispositivo["nombre"]})
    return dispositivo, True


def latido(uow: UnidadDeTrabajo, ahora: int, dispositivo_id: str, plataforma: str = "", version_app: str = "",
           espacio_libre_mb: int | None = None, bateria_pct: int | None = None) -> dict | None:
    """La tableta dio señal de vida (el sondeo del aula, la presencia, el propio latido), y opcionalmente cuánto
    espacio y batería le quedan (lo lee el profesor antes de distribuir un paquete: MSG-045)."""
    actual = uow.dispositivos.por_id(dispositivo_id)
    if not actual:
        return None
    campos: dict = {"ultimo_latido_en": ahora}
    if espacio_libre_mb is not None:
        campos["espacio_libre_mb"] = max(0, int(espacio_libre_mb))
    if bateria_pct is not None:
        campos["bateria_pct"] = max(0, min(100, int(bateria_pct)))
    if plataforma:
        campos["plataforma"] = dom.validar_plataforma(plataforma)
    if version_app:
        campos["version_app"] = str(version_app)[:32]
    if not dom.en_linea(actual["ultimo_latido_en"], ahora):
        uow.outbox.publicar("Dispositivo", dispositivo_id, dom.EV_RECONECTADO,
                            {"dispositivo_id": dispositivo_id, "silencio_ms": ahora - actual["ultimo_latido_en"], "instante": ahora})
    return uow.dispositivos.actualizar(dispositivo_id, **campos)


def exigir_disponible(dispositivo: dict) -> None:
    """Regla de oro: bloqueado o retirado no abre sesión ni recibe lanzamientos."""
    if not dispositivo["activo"]:
        raise DispositivoInactivo(dispositivo_id=dispositivo["id"], nombre=dispositivo["nombre"])
    if dispositivo["bloqueado"]:
        raise DispositivoBloqueado(dispositivo_id=dispositivo["id"], nombre=dispositivo["nombre"])


def abrir_sesion_alumno(uow: UnidadDeTrabajo, ahora: int, alumno_id: str, dispositivo_id: str, actor: str = "") -> dict:
    """La Dim Sesión Alumno. Idempotente si el mismo alumno ya tiene abierta la de esta tableta.
    INV-011: la sesión de OTRO alumno en la misma tableta se cierra (relevo, tableta compartida).
    DEC-023: la sesión del mismo alumno en OTRA tableta se cierra (relevo, cambió de equipo)."""
    dispositivo = uow.dispositivos.por_id(dispositivo_id)
    if not dispositivo:
        raise NoEncontrado(dispositivo_id=dispositivo_id)
    exigir_disponible(dispositivo)
    en_tableta = uow.sesiones_alumno.abierta_en_dispositivo(dispositivo_id)
    if en_tableta and en_tableta["alumno_id"] == alumno_id:
        return en_tableta
    if en_tableta:
        _cerrar(uow, ahora, en_tableta, dom.RELEVO, actor)
    del_alumno = uow.sesiones_alumno.abierta_de_alumno(alumno_id)
    if del_alumno:
        _cerrar(uow, ahora, del_alumno, dom.RELEVO, actor)
    sesion = uow.sesiones_alumno.crear({"id": _id(), "alumno_id": alumno_id, "dispositivo_id": dispositivo_id,
                                        "iniciada_en": ahora, "finalizada_en": None, "motivo_cierre": ""})
    uow.outbox.publicar("DimSesionAlumno", sesion["id"], dom.EV_SESION_ABIERTA, {
        "sesion_id": sesion["id"], "alumno_id": alumno_id, "dispositivo_id": dispositivo_id, "instante": ahora})
    return sesion


def cerrar_sesion_alumno(uow: UnidadDeTrabajo, ahora: int, sesion_id: str, motivo: str = dom.USUARIO, actor: str = "") -> dict | None:
    sesion = uow.sesiones_alumno.sesion(sesion_id)
    if not sesion or sesion["finalizada_en"] is not None:
        return sesion
    return _cerrar(uow, ahora, sesion, dom.validar_motivo_cierre(motivo), actor)


def _cerrar(uow: UnidadDeTrabajo, ahora: int, sesion: dict, motivo: str, actor: str) -> dict:
    cerrada = uow.sesiones_alumno.cerrar(sesion["id"], max(ahora, sesion["iniciada_en"]), motivo)
    uow.outbox.publicar("DimSesionAlumno", sesion["id"], dom.EV_SESION_CERRADA, {
        "sesion_id": sesion["id"], "alumno_id": sesion["alumno_id"], "dispositivo_id": sesion["dispositivo_id"],
        "motivo": motivo, "instante": ahora})
    return cerrada or sesion


def cambiar_bloqueo(uow: UnidadDeTrabajo, ahora: int, dispositivo_id: str, bloqueado: bool, actor: str, motivo: str = "") -> dict:
    dispositivo = uow.dispositivos.por_id(dispositivo_id)
    if not dispositivo:
        raise NoEncontrado(dispositivo_id=dispositivo_id)
    if dispositivo["bloqueado"] == bloqueado:
        return dispositivo
    dispositivo = uow.dispositivos.actualizar(dispositivo_id, bloqueado=bloqueado)
    evento = dom.EV_BLOQUEADO if bloqueado else dom.EV_DESBLOQUEADO
    uow.outbox.publicar("Dispositivo", dispositivo_id, evento, {"dispositivo_id": dispositivo_id, "motivo": motivo, "instante": ahora})
    uow.auditoria.registrar(actor, "dispositivos.bloqueado" if bloqueado else "dispositivos.desbloqueado", "m09_dispositivo",
                            dispositivo_id, anterior={"bloqueado": not bloqueado}, nuevo={"bloqueado": bloqueado, "motivo": motivo})
    return dispositivo


# ================================================================= casos de uso

class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios

    def _dispositivo(self, uow: UnidadDeTrabajo, dispositivo_id: str) -> dict:
        dispositivo = uow.dispositivos.por_id(dispositivo_id)
        if not dispositivo:
            raise NoEncontrado(dispositivo_id=dispositivo_id)
        return dispositivo

    def _dto(self, uow: UnidadDeTrabajo, dispositivo: dict, ahora: int) -> dict:
        return dto(dispositivo, ahora, uow.sesiones_alumno.abierta_en_dispositivo(dispositivo["id"]))


class RegistrarDispositivo(_CasoDeUso):
    """CAP-052 · CAP-053 · FUN-091. Público: es la tableta la que se presenta (emparejamiento por huella)."""

    def ejecutar(self, datos: dict, actor: str = "") -> tuple[dict, bool]:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo, creado = resolver(
                uow, ahora, datos.get("identificador_hw") or datos.get("identificador"), nombre=datos.get("nombre"),
                tipo=datos.get("tipo") or dom.TABLETA, plataforma=datos.get("plataforma"), version_app=datos.get("version_app"),
                actor=actor)
            return self._dto(uow, dispositivo, ahora), creado


class RegistrarLatido(_CasoDeUso):
    """La tableta dice que sigue viva y qué app corre. Si es nueva, se registra (CAP-053); la respuesta le
    dice si está bloqueada o retirada para que el cliente no insista en unirse a una clase."""

    def ejecutar(self, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo, _ = resolver(
                uow, ahora, datos.get("identificador_hw") or datos.get("identificador"), nombre=datos.get("nombre"),
                tipo=datos.get("tipo") or dom.TABLETA, plataforma=datos.get("plataforma"), version_app=datos.get("version_app"))
            return {**self._dto(uow, dispositivo, ahora), "servidor_en": ahora}


class ListarDispositivos(_CasoDeUso):
    """CAP-054 · FUN-094: el inventario con su estado en vivo (latido, bloqueo, sesión abierta)."""

    def ejecutar(self, actor: Actor, solo_activos: bool = True) -> list[dict]:
        self.s.autorizacion.exigir(actor, dom.P_READ)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            org = organizacion_de(uow)
            filas = uow.dispositivos.listar(org, solo_activos)
            abiertas = uow.sesiones_alumno.abiertas_por_dispositivo([d["id"] for d in filas])
            return [dto(d, ahora, abiertas.get(d["id"])) for d in filas]


class VerDispositivo(_CasoDeUso):
    def ejecutar(self, actor: Actor, dispositivo_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_READ)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            return self._dto(uow, self._dispositivo(uow, dispositivo_id), ahora)


class ActualizarDispositivo(_CasoDeUso):
    """Nombre, tipo y alta/baja. Dar de baja cierra las sesiones abiertas en el equipo (de alumno y de login)
    y conserva su historial (CAP-057 en su parte MVP; el borrado remoto es V1)."""

    def ejecutar(self, actor: Actor, dispositivo_id: str, cambios: dict) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_UPDATE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo = self._dispositivo(uow, dispositivo_id)
            campos: dict = {}
            if "nombre" in cambios:
                campos["nombre"] = dom.normalizar_nombre(cambios.get("nombre"), obligatorio=True)
            if "tipo" in cambios:
                campos["tipo"] = dom.validar_tipo(cambios.get("tipo"))
            if "activo" in cambios:
                campos["activo"] = bool(cambios["activo"])
            sesiones_cerradas = 0
            if campos.get("activo") is False and dispositivo["activo"]:
                abierta = uow.sesiones_alumno.abierta_en_dispositivo(dispositivo_id)
                if abierta:
                    _cerrar(uow, ahora, abierta, dom.SISTEMA, actor.id)
                    sesiones_cerradas += 1
                sesiones_cerradas += uow.sesiones_usuario.cerrar_en_dispositivo(dispositivo_id, ahora, actor.id)
            if campos:
                dispositivo = uow.dispositivos.actualizar(dispositivo_id, **campos)
                uow.outbox.publicar("Dispositivo", dispositivo_id, dom.EV_INVENTARIO_ACTUALIZADO, {
                    "dispositivo_id": dispositivo_id, "campos": sorted(campos), "instante": ahora})
                uow.auditoria.registrar(actor.id, "dispositivos.actualizado", "m09_dispositivo", dispositivo_id,
                                        nuevo={**campos, "sesiones_cerradas": sesiones_cerradas})
            return self._dto(uow, dispositivo, ahora)


class BloquearDispositivo(_CasoDeUso):
    """Deja la tableta fuera de las sesiones nuevas y de los lanzamientos, sin darla de baja. Reversible."""

    def ejecutar(self, actor: Actor, dispositivo_id: str, motivo: str = "") -> dict:
        self.s.autorizacion.exigir(actor, dom.P_BLOCK)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            return self._dto(uow, cambiar_bloqueo(uow, ahora, dispositivo_id, True, actor.id, str(motivo or "")[:200]), ahora)


class DesbloquearDispositivo(_CasoDeUso):
    def ejecutar(self, actor: Actor, dispositivo_id: str, motivo: str = "") -> dict:
        self.s.autorizacion.exigir(actor, dom.P_BLOCK)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            return self._dto(uow, cambiar_bloqueo(uow, ahora, dispositivo_id, False, actor.id, str(motivo or "")[:200]), ahora)


class AbrirSesionAlumno(_CasoDeUso):
    def ejecutar(self, alumno_id: str, dispositivo_id: str, actor: str = "") -> dict:
        with self.s.uow() as uow:
            return abrir_sesion_alumno(uow, self.s.reloj.ahora_ms(), alumno_id, dispositivo_id, actor)


class CerrarSesionAlumno(_CasoDeUso):
    def ejecutar(self, sesion_id: str, motivo: str = dom.USUARIO, actor: str = "") -> dict | None:
        with self.s.uow() as uow:
            return cerrar_sesion_alumno(uow, self.s.reloj.ahora_ms(), sesion_id, motivo, actor)
