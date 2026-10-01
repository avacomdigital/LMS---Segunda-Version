"""
Lo común a los casos de uso de MOD-010: los servicios que entrega el composition root, la resolución de QUIÉN rinde y DESDE QUÉ APARATO (D-19)
y la visibilidad de una asignación para un alumno (INV-026). Ningún archivo de esta carpeta importa Django.

Quién es el alumno: con sesión (MOD-001), el del token. Sin sesión (Q-34 abierta, prototipo), el `alumno_id` que declara la tableta —lo elige
quien la tiene en la mano, sin código ni contraseña— en cualquier aparato; debe existir en el padrón y estar activo. Sin `alumno_id`: en un aparato
asignado, su dueño (compatibilidad); en uno compartido, 400 `falta_alumno`. Nunca se confunde una cosa con la otra: el aparato es CONTEXTO, la
persona es la IDENTIDAD.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio.errores import (
    AlumnoDesconocido,
    DispositivoBloqueado,
    DispositivoInactivo,
    FaltaAlumno,
    FaltaDispositivo,
    NoEncontrado,
    NodoNoInstalado,
)
from .puertos import Actor, Autorizacion, Contenido, Reloj, UnidadDeTrabajo


@dataclass(frozen=True)
class ConfigEvaluacion:
    """Parámetros que decide la instalación (`AVACOM_EVAL_*`). Los lee el composition root de `settings`; los casos de uso sólo ven este objeto,
    así que la aplicación sigue sin conocer Django."""

    latido_vencido_ms: int = 30_000            # INV-010: la reconexión de un dispositivo se espera hasta 30 s
    latido_seg: int = 5                        # punto de recuperación de 5 s
    gracia_ms: int = cat.GRACIA_MS_POR_DEFECTO     # DEC-019
    max_respuestas: int = 200
    desfase_reloj_ms: int = 5_000              # INV-017
    armado_intentos: int = 200
    archivado_ms: int = cat.ARCHIVO_TRAS_MS


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[[], UnidadDeTrabajo]
    contenido: Contenido
    reloj: Reloj
    autorizacion: Autorizacion
    config: ConfigEvaluacion = field(default_factory=ConfigEvaluacion)


def nuevo_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Contexto:
    """Quién rinde y con qué aparato, ya resuelto y comprobado."""

    actor: Actor
    alumno_id: str
    alumno_rotulo: str
    huella: str                       # lo que el cliente declaró (identificador_hw)
    dispositivo: dict | None          # la fila de MOD-009 o None (no vino, o no está registrado)
    organizacion_id: str | None

    @property
    def dispositivo_id(self) -> str:
        return (self.dispositivo or {}).get("id") or ""

    @property
    def capacidad(self) -> str:
        """Lo que la tableta DECLARÓ poder garantizar. Sin declarar, `abierto`: el nodo no presume lo que no sabe (D-11)."""
        return bloqueo.normalizar_capacidad((self.dispositivo or {}).get("capacidad_control"))

    @property
    def sesion(self) -> str:
        return self.actor.principal.sesion_id if self.actor.principal is not None else ""


def resolver_contexto(uow: UnidadDeTrabajo, actor: Actor, huella: str, *, ahora: int, declarado: str = "", registrar: bool = False,
                      exigir_aparato: bool = False, registro: dict | None = None, comprobar_uso: bool = True,
                      alumno_obligatorio: bool = True) -> Contexto:
    """Resuelve al alumno y a su aparato y comprueba las reglas de MOD-009.

    `registrar` reconoce (y da de alta la primera vez) al aparato y actualiza lo que declara (`registro`: nombre, plataforma, versión y
    `capacidad_control`); las rutas de lectura sólo lo buscan. `exigir_aparato` es para lo que no tiene sentido sin uno registrado. Un aparato
    inactivo o bloqueado no rinde, y el alumno que se declara sin sesión debe existir y estar activo (`comprobar_uso`).
    Errores: falta_dispositivo · falta_alumno · dispositivo_inactivo · dispositivo_bloqueado · sin_permiso (`motivo = alumno_desconocido`)."""
    huella = str(huella or "").strip()
    declarado = str(declarado or "").strip() or (actor.id if not actor.autenticado else "")
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
    asignado = dispositivo is not None and dispositivo.get("perfil") == "asignado"
    if actor.autenticado:
        alumno_id = actor.id
    elif declarado:
        alumno_id = declarado[:64]
    elif asignado:
        alumno_id = dispositivo["asignado_a_id"]
    elif alumno_obligatorio:
        raise FaltaAlumno("Este aparato es compartido y no hay sesión: falta `alumno_id` (quién rinde).")
    else:
        alumno_id = ""
    if alumno_id and comprobar_uso and not actor.autenticado and organizacion and alumno_id not in uow.identidad.alumnos_activos([alumno_id]):
        raise AlumnoDesconocido("El alumno que se declara no existe o no está activo: hay que elegir de nuevo quién eres.", alumno_id=alumno_id)
    rotulo = (uow.identidad.rotulo_persona(alumno_id) if alumno_id else "") or actor.rotulo
    return Contexto(actor=actor, alumno_id=alumno_id, alumno_rotulo=rotulo, huella=huella, dispositivo=dispositivo, organizacion_id=organizacion)


def exigir_nodo_instalado(uow: UnidadDeTrabajo) -> str:
    organizacion = uow.identidad.organizacion_id()
    if not organizacion:
        raise NodoNoInstalado("El nodo aún no está instalado: no hay organización a la que atar grupos, alumnos y aparatos.")
    return organizacion


# ------------------------------------------------------------------ visibilidad de la asignación (INV-026)

def alcanza_al_alumno(uow: UnidadDeTrabajo, asignacion: dict, alumno_id: str) -> bool:
    """¿Le alcanza la asignación? `seleccion`: está entre los destinatarios. `grupo`: es alumno ACTIVO del grupo AHORA (también los que entraron
    después de asignar; el que salió del grupo deja de verla)."""
    if asignacion["alcance"] == cat.SELECCION:
        return alumno_id in (asignacion.get("destinatarios") or [])
    return bool(asignacion["grupo_id"]) and asignacion["grupo_id"] in uow.identidad.grupos_del_alumno(alumno_id)


def asignacion_del_alumno(uow: UnidadDeTrabajo, ctx: Contexto, asignacion_id: str) -> dict:
    """La asignación si LE ALCANZA; si no existe o es de otro grupo, no se revela: 404 (`no_encontrado`)."""
    asignacion = uow.asignaciones.por_id(asignacion_id) if asignacion_id else None
    if asignacion is None or asignacion["estado"] == cat.BORRADOR or not alcanza_al_alumno(uow, asignacion, ctx.alumno_id):
        raise NoEncontrado("No existe esa evaluación para este alumno.", asignacion_id=asignacion_id)
    return asignacion


def destinatarios_de(uow: UnidadDeTrabajo, asignacion: dict) -> list[dict]:
    """Quiénes deben rendir, `[{id, rotulo}]`: los alumnos activos del grupo (ahora) o los de la selección."""
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
