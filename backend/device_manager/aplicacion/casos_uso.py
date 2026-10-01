"""
Casos de uso de MOD-009 · Device Manager.

Dos familias:
  1. El inventario (RegistrarDispositivo, ListarDispositivos, VerDispositivo, ActualizarDispositivo,
     BloquearDispositivo, DesbloquearDispositivo, RegistrarLatido, AsignarDispositivo, LiberarDispositivo):
     lo que opera el técnico, el administrador o el profesor desde OPS, y lo que la tableta declara de sí misma.
     Asignar y liberar (FUN-092, FUN-093) cambian el perfil del equipo: `compartido` (del aula) o `asignado` a una persona,
     condición de la descarga de paquetes del modo de estudio (008-01, BR-054).
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
from ..dominio.errores import (
    DispositivoBloqueado,
    DispositivoInactivo,
    DispositivoYaAsignado,
    NoEncontrado,
    NodoNoInstalado,
    PaqueteSinIntegrar,
)
from .puertos import Actor, Autorizacion, Reloj, UnidadDeTrabajo


@dataclass
class Servicios:
    uow: Callable[[], UnidadDeTrabajo]
    reloj: Reloj
    autorizacion: Autorizacion


def _id() -> str:
    return str(uuid.uuid4())


# =================================================================== reglas puras

def dto(dispositivo: dict, ahora: int, sesion_abierta: dict | None = None, rotulo_asignado: str = "") -> dict:
    """Lo que ven OPS y la tableta. `identificador` se conserva junto a `identificador_hw` porque el
    registro de la tableta (CAP-053) lo envía con ese nombre desde el contrato de acceso. `perfil` y `asignado_a`
    (009-06) dicen si el equipo es del aula o de una persona, y de quién."""
    dueno = dispositivo.get("asignado_a_id")
    return {
        **dispositivo,
        "identificador": dispositivo["identificador_hw"],
        "perfil": dispositivo.get("perfil") or dom.COMPARTIDO,
        "asignado_a": {"id": dueno, "rotulo": rotulo_asignado} if dueno else None,
        "en_linea": dom.en_linea(dispositivo.get("ultimo_latido_en"), ahora),
        "sesion_abierta": ({"id": sesion_abierta["id"], "alumno_id": sesion_abierta["alumno_id"],
                            "iniciada_en": sesion_abierta["iniciada_en"]} if sesion_abierta else None),
    }


def organizacion_de(uow: UnidadDeTrabajo) -> str:
    org = uow.organizaciones.unica_id()
    if not org:
        raise NodoNoInstalado()
    return org


def _campos_de_capacidad(actual: dict | None, capacidad_control, capacidad_detalle, ahora: int) -> dict:
    """MOD-010: lo que la tableta declara poder garantizar en un examen. Sólo se escribe si la tableta lo DECLARA (None = no dijo nada)."""
    if capacidad_control is None and capacidad_detalle is None:
        return {}
    campos: dict = {}
    if capacidad_control is not None:
        declarada = dom.validar_capacidad_control(capacidad_control)
        if declarada != (actual or {}).get("capacidad_control", ""):
            campos["capacidad_control"] = declarada
        campos["capacidad_declarada_en"] = ahora
    if isinstance(capacidad_detalle, dict):
        campos["capacidad_detalle"] = {str(k)[:40]: v for k, v in list(capacidad_detalle.items())[:20]}
    return campos


def resolver(uow: UnidadDeTrabajo, ahora: int, identificador_hw: str, nombre: str = "", tipo: str = dom.TABLETA,
             plataforma: str = "", version_app: str = "", actor: str = "", capacidad_control=None, capacidad_detalle=None) -> tuple[dict, bool]:
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
        campos.update(_campos_de_capacidad(existente, capacidad_control, capacidad_detalle, ahora))
        if not dom.en_linea(existente["ultimo_latido_en"], ahora):
            uow.outbox.publicar("Dispositivo", existente["id"], dom.EV_RECONECTADO,
                                {"dispositivo_id": existente["id"], "silencio_ms": ahora - existente["ultimo_latido_en"], "instante": ahora})
        return uow.dispositivos.actualizar(existente["id"], **campos), False
    dispositivo = uow.dispositivos.crear({
        "id": _id(), "organizacion_id": org, "identificador_hw": identificador_hw,
        "nombre": dom.normalizar_nombre(nombre, por_defecto=identificador_hw), "tipo": dom.validar_tipo(tipo),
        "plataforma": plataforma, "version_app": str(version_app or "")[:32], "activo": True, "bloqueado": False,
        "registrado_en": ahora, "ultimo_latido_en": ahora, **_campos_de_capacidad(None, capacidad_control, capacidad_detalle, ahora),
    })
    uow.outbox.publicar("Dispositivo", dispositivo["id"], dom.EV_REGISTRADO, {
        "dispositivo_id": dispositivo["id"], "nombre": dispositivo["nombre"], "tipo": dispositivo["tipo"],
        "plataforma": plataforma, "instante": ahora})
    uow.auditoria.registrar(actor or "sistema", "dispositivos.registrado", "m09_dispositivo", dispositivo["id"],
                            nuevo={"identificador_hw": identificador_hw, "nombre": dispositivo["nombre"]})
    return dispositivo, True


def latido(uow: UnidadDeTrabajo, ahora: int, dispositivo_id: str, plataforma: str = "", version_app: str = "",
           espacio_libre_mb: int | None = None, bateria_pct: int | None = None, capacidad_control=None, capacidad_detalle=None) -> dict | None:
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
    campos.update(_campos_de_capacidad(actual, capacidad_control, capacidad_detalle, ahora))
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
        dueno = dispositivo.get("asignado_a_id")
        rotulo = uow.alumnos.rotulos([dueno]).get(dueno, "") if dueno else ""
        return dto(dispositivo, ahora, uow.sesiones_alumno.abierta_en_dispositivo(dispositivo["id"]), rotulo)


class RegistrarDispositivo(_CasoDeUso):
    """CAP-052 · CAP-053 · FUN-091. Público: es la tableta la que se presenta (emparejamiento por huella)."""

    def ejecutar(self, datos: dict, actor: str = "") -> tuple[dict, bool]:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo, creado = resolver(
                uow, ahora, datos.get("identificador_hw") or datos.get("identificador"), nombre=datos.get("nombre"),
                tipo=datos.get("tipo") or dom.TABLETA, plataforma=datos.get("plataforma"), version_app=datos.get("version_app"),
                actor=actor, capacidad_control=datos.get("capacidad_control"), capacidad_detalle=datos.get("capacidad_detalle"))
            return self._dto(uow, dispositivo, ahora), creado


class RegistrarLatido(_CasoDeUso):
    """La tableta dice que sigue viva y qué app corre. Si es nueva, se registra (CAP-053); la respuesta le
    dice si está bloqueada o retirada para que el cliente no insista en unirse a una clase."""

    def ejecutar(self, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo, _ = resolver(
                uow, ahora, datos.get("identificador_hw") or datos.get("identificador"), nombre=datos.get("nombre"),
                tipo=datos.get("tipo") or dom.TABLETA, plataforma=datos.get("plataforma"), version_app=datos.get("version_app"),
                capacidad_control=datos.get("capacidad_control"), capacidad_detalle=datos.get("capacidad_detalle"))
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
            rotulos = uow.alumnos.rotulos([d["asignado_a_id"] for d in filas if d.get("asignado_a_id")])
            return [dto(d, ahora, abiertas.get(d["id"]), rotulos.get(d.get("asignado_a_id") or "", "")) for d in filas]


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


class AsignarDispositivo(_CasoDeUso):
    """FUN-092 · 008-01: el equipo pasa a ser nominal de una persona (perfil `asignado`). Sólo su dueño se lleva en él los paquetes
    del modo de estudio (BR-054); estudiar en línea sirve en cualquier equipo. Un equipo que ya es de OTRA persona no se reasigna:
    primero se libera (409). Asignar a la misma persona es idempotente. Cualquier alumno que tuviera abierta una sesión en el
    equipo compartido queda fuera: el equipo deja de ser del aula."""

    def ejecutar(self, actor: Actor, dispositivo_id: str, alumno_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_ASSIGN)
        alumno_id = dom.normalizar_alumno(alumno_id)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo = self._dispositivo(uow, dispositivo_id)
            if not dispositivo["activo"]:
                raise DispositivoInactivo(dispositivo_id=dispositivo_id, nombre=dispositivo["nombre"])
            if uow.alumnos.existe(alumno_id) is False:
                raise NoEncontrado("No existe esa persona en el padrón: no se le puede asignar un equipo.", alumno_id=alumno_id)
            if dispositivo["perfil"] == dom.ASIGNADO:
                if dispositivo["asignado_a_id"] == alumno_id:
                    return self._dto(uow, dispositivo, ahora)
                raise DispositivoYaAsignado(
                    "El equipo ya está asignado a otra persona: libéralo antes de asignarlo de nuevo.",
                    dispositivo_id=dispositivo_id, asignado_a_id=dispositivo["asignado_a_id"])
            abierta = uow.sesiones_alumno.abierta_en_dispositivo(dispositivo_id)
            if abierta and abierta["alumno_id"] != alumno_id:
                _cerrar(uow, ahora, abierta, dom.SISTEMA, actor.id)
            dispositivo = uow.dispositivos.actualizar(dispositivo_id, perfil=dom.ASIGNADO, asignado_a_id=alumno_id, asignado_en=ahora)
            uow.outbox.publicar("Dispositivo", dispositivo_id, dom.EV_ASIGNADO, {
                "dispositivo_id": dispositivo_id, "alumno_id": alumno_id, "instante": ahora})
            uow.auditoria.registrar(actor.id, "dispositivos.asignado", "m09_dispositivo", dispositivo_id,
                                    anterior={"perfil": dom.COMPARTIDO}, nuevo={"perfil": dom.ASIGNADO, "asignado_a_id": alumno_id})
            return self._dto(uow, dispositivo, ahora)


class LiberarDispositivo(_CasoDeUso):
    """FUN-093: el equipo vuelve a ser del aula (perfil `compartido`). Exige que no conserve un paquete de estudio activo
    (`solicitado`, `descargandose` o `disponible`): liberarlo así dejaría el material a la vista del siguiente alumno (409
    `paquete_sin_integrar`); el alumno, o quien lo administre, lo retira primero. Liberar un equipo compartido no hace nada."""

    def ejecutar(self, actor: Actor, dispositivo_id: str) -> dict:
        self.s.autorizacion.exigir(actor, dom.P_RELEASE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            dispositivo = self._dispositivo(uow, dispositivo_id)
            if dispositivo["perfil"] != dom.ASIGNADO:
                return self._dto(uow, dispositivo, ahora)
            activos = uow.paquetes_estudio.activos_en(dispositivo_id)
            if activos:
                raise PaqueteSinIntegrar(
                    f"El equipo conserva {activos} paquete(s) de estudio: deben retirarse antes de liberarlo.",
                    dispositivo_id=dispositivo_id, paquetes=activos)
            dueno = dispositivo["asignado_a_id"]
            abierta = uow.sesiones_alumno.abierta_en_dispositivo(dispositivo_id)
            if abierta:
                _cerrar(uow, ahora, abierta, dom.SISTEMA, actor.id)
            dispositivo = uow.dispositivos.actualizar(dispositivo_id, perfil=dom.COMPARTIDO, asignado_a_id=None, asignado_en=None)
            uow.outbox.publicar("Dispositivo", dispositivo_id, dom.EV_LIBERADO, {
                "dispositivo_id": dispositivo_id, "alumno_id": dueno, "instante": ahora})
            uow.auditoria.registrar(actor.id, "dispositivos.liberado", "m09_dispositivo", dispositivo_id,
                                    anterior={"perfil": dom.ASIGNADO, "asignado_a_id": dueno}, nuevo={"perfil": dom.COMPARTIDO})
            return self._dto(uow, dispositivo, ahora)


class AbrirSesionAlumno(_CasoDeUso):
    def ejecutar(self, alumno_id: str, dispositivo_id: str, actor: str = "") -> dict:
        with self.s.uow() as uow:
            return abrir_sesion_alumno(uow, self.s.reloj.ahora_ms(), alumno_id, dispositivo_id, actor)


class CerrarSesionAlumno(_CasoDeUso):
    def ejecutar(self, sesion_id: str, motivo: str = dom.USUARIO, actor: str = "") -> dict | None:
        with self.s.uow() as uow:
            return cerrar_sesion_alumno(uow, self.s.reloj.ahora_ms(), sesion_id, motivo, actor)
