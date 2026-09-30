"""
Lo común a los casos de uso de MOD-008: los servicios que entrega el composition root, la resolución de QUIÉN estudia y DESDE QUÉ APARATO
(D-1, D-2, D-3, revisadas por D-15) y la visibilidad de una asignación para un alumno. Ningún archivo de esta carpeta importa Django.

Quién es el alumno (D-15 · «identidad declarada», 2026-09-29): con sesión (MOD-001), el del token. Sin sesión, el `alumno_id` que declara la
tableta —lo elige quien la tiene en la mano, sin código ni contraseña— en CUALQUIER aparato, compartido o asignado; debe existir en el padrón y
estar activo. Sin `alumno_id`: en un aparato asignado, su dueño (compatibilidad); en uno compartido, 400 `falta_alumno`. El aparato asignado ya no
rechaza a quien no es su dueño; lo único que sigue siendo del dueño es el PAQUETE de estudio (BR-054): `Contexto.ajeno` sólo lo usa la descarga.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio.errores import (
    AlumnoDesconocido,
    DispositivoBloqueado,
    DispositivoInactivo,
    FaltaAlumno,
    FaltaDispositivo,
    NoEncontrado,
)
from .puertos import Actor, Autorizacion, Contenido, Reloj, UnidadDeTrabajo

MIB = 1024 * 1024


@dataclass(frozen=True)
class ConfigEstudio:
    """Parámetros que decide la instalación (`AVACOM_ESTUDIO_*`). Los lee el composition root de `settings`; los casos de uso sólo
    ven este objeto, así que la aplicación sigue sin conocer Django."""

    vigencia_dias: int = 14                      # D-8: cuánto dura un paquete de una asignación sin fecha límite
    gracia_ms: int = cat.GRACIA_MS_POR_DEFECTO   # DEC-019: gracia por defecto de una asignación nueva
    medio_max_bytes: int = 512 * MIB             # tope de UN medio al medirlo para el paquete


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[[], UnidadDeTrabajo]
    contenido: Contenido
    reloj: Reloj
    autorizacion: Autorizacion
    config: ConfigEstudio = field(default_factory=ConfigEstudio)


def nuevo_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Contexto:
    """Quién estudia y con qué aparato, ya resuelto y comprobado."""

    actor: Actor
    alumno_id: str
    alumno_rotulo: str
    huella: str                       # lo que el cliente declaró (identificador_hw)
    dispositivo: dict | None          # la fila de MOD-009 o None (no vino, o no está registrado)
    organizacion_id: str | None
    ajeno: bool = False               # el aparato está asignado a OTRA persona: estudia igual (D-15), pero no se lleva el paquete (BR-054)

    @property
    def perfil(self) -> str:
        return (self.dispositivo or {}).get("perfil") or ""

    @property
    def es_del_alumno(self) -> bool:
        """El aparato está asignado a esta persona: lo único que admite el paquete de estudio (BR-054)."""
        return bool(self.dispositivo) and self.perfil == cat.ASIGNADO and self.dispositivo.get("asignado_a_id") == self.alumno_id and not self.ajeno

    @property
    def dispositivo_id(self) -> str:
        return (self.dispositivo or {}).get("id") or ""

    @property
    def alumno_para_url(self) -> str:
        """Lo que hay que poner en la URL de un medio para que la ruta sepa quién pregunta: en un aparato asignado a la persona, nada (sin nadie
        declarado la ruta toma a su dueño); en cualquier otro, quien lo declaró."""
        return "" if self.es_del_alumno else self.alumno_id

    @property
    def sesion(self) -> str:
        return self.actor.principal.sesion_id if self.actor.principal is not None else ""


def resolver_contexto(uow: UnidadDeTrabajo, actor: Actor, huella: str, *, ahora: int, declarado: str = "", registrar: bool = False,
                      exigir_aparato: bool = False, registro: dict | None = None, comprobar_uso: bool = True,
                      alumno_obligatorio: bool = True) -> Contexto:
    """Resuelve al alumno y a su aparato y comprueba las reglas de MOD-009 (D-15: identidad declarada).

    `registrar` reconoce (y da de alta como compartido la primera vez) al aparato: lo hacen las rutas que escriben, igual que el aula y
    el latido; las de lectura sólo lo buscan. `exigir_aparato` es para lo que no tiene sentido sin uno registrado (paquetes, sesión).
    Un aparato inactivo o bloqueado no estudia, y el alumno que se declara sin sesión debe existir y estar activo (`comprobar_uso`); cerrar
    la sesión, limpiar el aparato y retirar el paquete deben poder hacerse siempre.
    `alumno_obligatorio=False` deja `alumno_id` vacío en vez de fallar cuando nadie puede decir quién estudia (la limpieza no lo exige).
    Un aparato asignado a OTRA persona no se rechaza: `Contexto.ajeno` lo dice y sólo la descarga del paquete lo usa (BR-054).
    Errores: falta_dispositivo · falta_alumno · dispositivo_inactivo · dispositivo_bloqueado · sin_permiso (`motivo = alumno_desconocido`)."""
    huella = str(huella or "").strip()
    declarado = str(declarado or "").strip() or (actor.id if not actor.autenticado else "")   # la vista pone en `actor.id` lo que el cliente declaró
    if not huella and not actor.autenticado:
        raise FaltaDispositivo("Falta `dispositivo` (la huella del aparato): sin sesión de alumno no se sabe desde dónde se pregunta.")
    organizacion = uow.identidad.organizacion_id()
    dispositivo = None
    if organizacion:
        if huella and registrar:
            dispositivo = uow.dispositivos.resolver(huella, momento=ahora, **(registro or {}))
        elif huella:
            dispositivo = uow.dispositivos.por_identificador(organizacion, huella)
        elif actor.dispositivo_id:
            dispositivo = uow.dispositivos.por_id(actor.dispositivo_id)
    if dispositivo is None and exigir_aparato:
        raise FaltaDispositivo("Esta función necesita un aparato registrado: falta `dispositivo` o el nodo no lo conoce.")
    if dispositivo is not None and comprobar_uso:
        if not dispositivo["activo"]:
            raise DispositivoInactivo(dispositivo_id=dispositivo["id"], nombre=dispositivo["nombre"])
        if dispositivo["bloqueado"]:
            raise DispositivoBloqueado(dispositivo_id=dispositivo["id"], nombre=dispositivo["nombre"])
    asignado = dispositivo is not None and dispositivo.get("perfil") == cat.ASIGNADO
    if actor.autenticado:
        alumno_id = actor.id
    elif declarado:
        alumno_id = declarado[:64]                      # D-15: quien tiene la tableta elige quién es, en cualquier aparato; lo declarado gana al dueño
    elif asignado:
        alumno_id = dispositivo["asignado_a_id"]        # compatibilidad: sin nadie declarado, el dueño de la tableta asignada
    elif alumno_obligatorio:
        raise FaltaAlumno("Este aparato es compartido y no hay sesión: falta `alumno_id` (quién estudia).")
    else:
        alumno_id = ""
    if alumno_id and comprobar_uso and not actor.autenticado and organizacion and alumno_id not in uow.identidad.alumnos_activos([alumno_id]):
        raise AlumnoDesconocido("El alumno que se declara no existe o no está activo: hay que elegir de nuevo quién eres.", alumno_id=alumno_id)
    ajeno = bool(asignado and alumno_id and dispositivo["asignado_a_id"] != alumno_id)
    rotulo = (uow.identidad.rotulo_persona(alumno_id) if alumno_id else "") or actor.rotulo
    return Contexto(actor=actor, alumno_id=alumno_id, alumno_rotulo=rotulo, huella=huella, dispositivo=dispositivo,
                    organizacion_id=organizacion, ajeno=ajeno)


# ------------------------------------------------------------------ visibilidad de la asignación

def alcanza_al_alumno(uow: UnidadDeTrabajo, asignacion: dict, alumno_id: str) -> bool:
    """¿Le alcanza la asignación? `seleccion`: está entre los destinatarios. `grupo`: es alumno ACTIVO del grupo AHORA (también los
    que entraron después de asignar; el que salió del grupo deja de verla)."""
    if asignacion["alcance"] == cat.SELECCION:
        return alumno_id in (asignacion.get("destinatarios") or [])
    return bool(asignacion["grupo_id"]) and asignacion["grupo_id"] in uow.identidad.grupos_del_alumno(alumno_id)


def asignacion_del_alumno(uow: UnidadDeTrabajo, ctx: Contexto, asignacion_id: str) -> dict:
    """La asignación si LE ALCANZA; si no existe o es de otro grupo, no se revela: 404 (`no_encontrado`)."""
    asignacion = uow.asignaciones.por_id(asignacion_id) if asignacion_id else None
    if asignacion is None or not alcanza_al_alumno(uow, asignacion, ctx.alumno_id):
        raise NoEncontrado("No existe esa asignación para este alumno.", asignacion_id=asignacion_id)
    return asignacion


def destinatarios_de(uow: UnidadDeTrabajo, asignacion: dict) -> list[dict]:
    """Quiénes deben hacer el trabajo, `[{id, rotulo}]`: los alumnos activos del grupo (ahora) o los de la selección."""
    if asignacion["alcance"] == cat.GRUPO:
        return uow.identidad.alumnos_del_grupo(asignacion["grupo_id"]) if asignacion["grupo_id"] else []
    ids = list(dict.fromkeys(asignacion.get("destinatarios") or []))
    rotulos = uow.identidad.rotulos_personas(ids)
    return [{"id": i, "rotulo": rotulos.get(i, i)} for i in ids]


class _CasoDeUso:
    """Base de los casos de uso: una transacción por caso, con sus servicios."""

    def __init__(self, servicios: Servicios):
        self.s = servicios

    def _publicar(self, uow: UnidadDeTrabajo, agregado_tipo: str, agregado_id: str, evento: str, carga: dict, ahora: int) -> None:
        uow.outbox.publicar(agregado_tipo, agregado_id, evento, {**carga, "instante": ahora})
