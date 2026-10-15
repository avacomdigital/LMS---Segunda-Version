"""
Lo común a los casos de uso de MOD-011: los servicios que entrega el composition root, la lectura de los datos de una petición (motivo, versión esperada,
clave de idempotencia), el contexto en que se califica (grupo, nivel, periodo), el modo de un nivel y cómo se ve una calificación. Ningún archivo de esta
carpeta importa Django.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio import escala as esc
from ..dominio import puntaje as pj
from ..dominio.errores import DatosInvalidos, FueraDeAlcance, NodoNoInstalado
from .puertos import Actor, Autorizacion, Reloj, UnidadDeTrabajo


@dataclass(frozen=True)
class ConfigGradebook:
    """Parámetros que decide la instalación (`AVACOM_GRADEBOOK_*`). Los lee el composition root de `settings`; los casos de uso sólo ven este objeto."""

    lote_eventos: int = 100                 # cuántos eventos de MOD-010 procesa UNA transacción del consumidor (cada una toma el bloqueo de escritura del nodo)
    sincronizar_al_consultar: bool = True   # el libro se pone al día con MOD-010 antes de responder (lo que el hilo aún no alcanzó)


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[..., UnidadDeTrabajo]     # `uow()` abre una transacción; `uow(lectura=True)`, una consulta sin ella
    reloj: Reloj
    autorizacion: Autorizacion
    config: ConfigGradebook = field(default_factory=ConfigGradebook)


def nuevo_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------------- lo que trae una petición

def motivo_de(datos: dict, *, obligatorio: bool = True, campo: str = "motivo") -> str:
    """El motivo de un cambio (BR-070): texto de al menos tres letras cuando es obligatorio (un ajuste, una reapertura, una valoración)."""
    texto = " ".join(str(datos.get(campo) or "").split())
    if obligatorio and len(texto) < cat.MIN_MOTIVO:
        raise DatosInvalidos("Todo cambio a una calificación exige un motivo: queda en el historial junto al valor anterior.", campo=campo)
    return texto[:cat.MAX_MOTIVO]


def solicitud_de(datos: dict) -> str:
    """La clave de idempotencia que manda el cliente (`solicitud_id`): reenviar la misma no repite el efecto."""
    return str(datos.get("solicitud_id") or "").strip()[:64]


def version_esperada(datos: dict, *, obligatorio: bool = True) -> int | None:
    """La versión que el cliente leyó: sin ella no hay forma de saber si otra persona cambió la calificación mientras tanto."""
    valor = datos.get("version_esperada")
    if valor in (None, ""):
        if obligatorio:
            raise DatosInvalidos("Falta `version_esperada`: la versión de la calificación que leíste (evita pisar el cambio de otra persona).")
        return None
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise DatosInvalidos("`version_esperada` debe ser un entero positivo.", valor=str(valor)[:20])
    return valor


def comentario_de(datos: dict, campo: str = "comentario") -> str:
    return str(datos.get(campo) or "").strip()[:cat.MAX_COMENTARIO]


def exigir_nodo_instalado(uow: UnidadDeTrabajo) -> str:
    organizacion = uow.identidad.organizacion_id()
    if not organizacion:
        raise NodoNoInstalado("El nodo aún no está instalado: no hay organización a la que atar grupos, alumnos y niveles.")
    return organizacion


# ------------------------------------------------------------------------------------------------- contexto

def contexto_de(uow: UnidadDeTrabajo, asignacion: dict, alumno_id: str) -> dict:
    """El contexto en que se califica: grupo, nivel educativo, periodo y curso. El grupo es el de la asignación; si fue a alumnos sueltos, uno de los grupos
    activos del alumno, elegido SIEMPRE igual: el que enseña quien la asignó (si enseña en alguno) y, si no, el primero por identificador."""
    grupo_id = asignacion.get("grupo_id") or ""
    if not grupo_id:
        grupos = sorted(uow.identidad.grupos_del_alumno(alumno_id))
        dueno = asignacion.get("profesor_id") or ""
        grupo_id = next((g for g in grupos if dueno and uow.identidad.es_docente_del_grupo(g, dueno)), grupos[0] if grupos else "")
    grupo = uow.identidad.grupo(grupo_id) if grupo_id else None
    return {"grupo_id": grupo_id, "nivel_clave": (grupo or {}).get("nivel_clave") or "", "periodo": (grupo or {}).get("periodo") or "",
            "curso_ref": asignacion.get("curso_ref") or ""}


def grupos_de_destinatarios(uow: UnidadDeTrabajo, asignacion: dict) -> list[str]:
    """Los grupos de los alumnos a quienes fue una asignación de alumnos sueltos (sus destinatarios y quienes ya tienen un intento), en orden fijo."""
    alumnos = set(asignacion.get("destinatarios") or []) | {i["alumno_id"] for i in uow.evaluacion.intentos_de_asignacion(asignacion["id"])}
    grupos: set[str] = set()
    for alumno in sorted(alumnos):
        grupos.update(uow.identidad.grupos_del_alumno(alumno))
    return sorted(grupos)


def exigir_en_asignacion(uow: UnidadDeTrabajo, autorizacion, actor: Actor, permisos: str | tuple[str, ...], asignacion: dict) -> None:
    """El alcance de un permiso sobre UNA asignación. Con grupo, el del grupo. Una asignación a alumnos sueltos no tiene grupo, y un grupo vacío no puede
    saltarse la comprobación: la opera quien la asignó o quien enseña en el grupo de alguno de sus alumnos; con el alcance de toda la organización, cualquiera."""
    permisos = (permisos,) if isinstance(permisos, str) else tuple(permisos)
    grupo = asignacion.get("grupo_id") or ""
    if grupo:
        return autorizacion.exigir_alguno(actor, permisos, grupo_id=grupo)
    if actor.autenticado and actor.id and asignacion.get("profesor_id") == actor.id:
        return autorizacion.exigir_alguno(actor, permisos)
    ultimo: FueraDeAlcance | None = None
    for g in grupos_de_destinatarios(uow, asignacion):
        try:
            return autorizacion.exigir_alguno(actor, permisos, grupo_id=g)
        except FueraDeAlcance as error:
            ultimo = error
    if ultimo is not None:
        raise ultimo
    return autorizacion.exigir_alguno(actor, permisos, organizacion=True)


def exigir_sobre_resultado(uow: UnidadDeTrabajo, autorizacion, actor: Actor, permisos: str | tuple[str, ...], *, grupo_id: str, asignacion_id: str) -> None:
    """El alcance de un permiso sobre lo de UN alumno (su calificación o su intento): el del grupo del alumno y, cuando la evaluación fue a alumnos sueltos,
    también el de quien la asignó. Sin grupo no hay nada que comparar: sólo pasa quien tiene el permiso sobre toda la organización."""
    permisos = (permisos,) if isinstance(permisos, str) else tuple(permisos)
    try:
        return autorizacion.exigir_alguno(actor, permisos, grupo_id=grupo_id, organizacion=not grupo_id)
    except FueraDeAlcance:
        asignacion = uow.evaluacion.asignacion(asignacion_id) if asignacion_id else None
        if asignacion is not None and not asignacion.get("grupo_id") and actor.autenticado and actor.id and asignacion.get("profesor_id") == actor.id:
            return autorizacion.exigir_alguno(actor, permisos)
        raise


def modo_del_nivel(uow: UnidadDeTrabajo, nivel_clave: str) -> tuple[str, dict | None]:
    """`(modo, versión de escala)` de un nivel. Sin fila de configuración (o sin nivel), el modo es `simple`: el valor por defecto."""
    config = uow.niveles.get(nivel_clave) if nivel_clave else None
    if config is None or config["modo"] == cat.SIMPLE or not config.get("escala_version_id"):
        return cat.SIMPLE, None
    return cat.CALIFICACIONES, uow.escalas.version(config["escala_version_id"])


def sistema_de(version: dict) -> dict:
    """La escala de un nivel con lo que hace falta para leer una nota suya: quién es (con su versión), de qué país, su rango, desde dónde se aprueba y sus
    tramos. Es lo que ven el profesor en el libro y el alumno junto a su nota; la presentación estampada al publicar no cambia."""
    return {"escala_id": version["escala_id"], "codigo": version["codigo"], "nombre": version["nombre"], "version_id": version["id"], "numero": version["numero"],
            "tipo": version["definicion"].tipo, "pais": version.get("pais") or "", "jurisdiccion": version.get("jurisdiccion") or "", **esc.describir(version["definicion"])}


def presentar_con(version: dict, calificacion: dict) -> dict:
    """La presentación de una calificación con UNA versión de escala, con su identidad para poder interpretarla después."""
    salida = esc.presentar(calificacion["puntaje_efectivo"], version["definicion"], calificacion.get("desempeno_docente") or "")
    salida["escala"] = {"escala_id": version["escala_id"], "codigo": version["codigo"], "nombre": version["nombre"], "version_id": version["id"],
                        "numero": version["numero"], "tipo": version["definicion"].tipo, "huella": version["huella"]}
    return salida


def presentacion_de(uow: UnidadDeTrabajo, calificacion: dict) -> dict | None:
    """Lo que ve el profesor como presentación de una calificación: la instantánea estampada si ya se publicó (con la versión de entonces) o, antes, la
    conversión con la escala VIGENTE del nivel, rotulada `provisional`. En modo simple, o sin escala, no hay presentación."""
    if calificacion["estado"] == cat.DEFINITIVA and calificacion.get("presentacion"):
        return {**calificacion["presentacion"], "provisional": False}
    if calificacion["estado"] in (cat.REABIERTA, cat.ANULADA):
        return None
    modo, version = modo_del_nivel(uow, calificacion.get("nivel_clave") or "")
    if modo != cat.CALIFICACIONES or version is None:
        return None
    return {**presentar_con(version, calificacion), "provisional": True}


def salida_calificacion(uow: UnidadDeTrabajo, c: dict, *, intento: dict | None = None) -> dict:
    """Una calificación como la ve el profesor: lo interno, lo presentado y su trazabilidad. Si se conoce el intento de MOD-010, se avisa cuando éste ya no
    dice lo que se tomó de él (`desfase_con_evaluacion`): alguien cambió la puntuación allá sin reabrir la calificación."""
    desfase = False
    if intento is not None and intento.get("porcentaje") is not None and c["estado"] in (cat.REVISADA, cat.DEFINITIVA):
        try:
            desfase = pj.interno_desde_porcentaje(intento["porcentaje"]) != c["puntaje_fuente"]
        except Exception:      # noqa: BLE001 — un porcentaje ilegible no debe romper la consulta
            desfase = False
    return {
        "id": c["id"], "intento_id": c["intento_id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"], "grupo_id": c["grupo_id"],
        "nivel_clave": c["nivel_clave"], "periodo": c["periodo"], "curso_ref": c["curso_ref"], "numero_intento": c["numero_intento"],
        "puntaje_original": pj.como_numero(c["puntaje_original"]), "puntaje_efectivo": pj.como_numero(c["puntaje_efectivo"]),
        "ajustada": c["puntaje_efectivo"] != c["puntaje_fuente"], "aciertos": c.get("aciertos"), "preguntas": c.get("preguntas"),
        "regla_puntuacion": c["regla_puntuacion"], "origen": c["origen"], "evaluador_id": c["evaluador_id"], "estado": c["estado"], "version": c["version"],
        "publicada": c["estado"] == cat.DEFINITIVA, "publicada_en": c["publicada_en"], "publicada_por": c["publicada_por"],
        "desempeno_docente": c["desempeno_docente"], "desempeno_motivo": c["desempeno_motivo"], "retroalimentacion": c["retroalimentacion"],
        "adaptacion": c["adaptacion"], "presentacion": presentacion_de(uow, c), "desfase_con_evaluacion": desfase,
        "registrada_en": c["registrada_en"], "actualizada_en": c["actualizada_en"],
    }


def salida_version(v: dict) -> dict:
    return {"numero": v["numero"], "tipo": v["tipo"], "puntaje_anterior": pj.como_numero(v["puntaje_anterior"]), "puntaje_nuevo": pj.como_numero(v["puntaje_nuevo"]),
            "estado_anterior": v["estado_anterior"], "estado_nuevo": v["estado_nuevo"], "motivo": v["motivo"], "actor_id": v["actor_id"], "en": v["en"],
            "solicitud_id": v["solicitud_id"]}


class _CasoDeUso:
    """Base de los casos de uso: una transacción por caso, con sus servicios."""

    def __init__(self, servicios: Servicios):
        self.s = servicios

    @staticmethod
    def _publicar(uow: UnidadDeTrabajo, agregado_tipo: str, agregado_id: str, evento: str, carga: dict, ahora: int) -> None:
        """El evento de salida en la misma transacción que el hecho. Nunca lleva comentarios ni el contenido de una respuesta."""
        uow.outbox.publicar(agregado_tipo, agregado_id, evento, {**carga, "instante": ahora})
