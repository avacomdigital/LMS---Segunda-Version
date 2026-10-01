"""
La admisión de una tableta por debajo del nivel de control (FUN-116, CAP-064, BR-075, BR-076, TST-041, AC-046).

Una tableta que no alcanza el nivel que exige el examen NO abre el intento sola: queda `en_espera` y decide el PROFESOR, que la admite en un nivel
menor (con motivo, de forma explícita) o la rechaza. El alumno nunca queda excluido del examen por su dispositivo: el profesor puede admitirlo,
bajar el nivel de todo el examen (FUN-118) o cambiarle la tableta. Admitir no abre el intento: le permite al alumno abrirlo desde su tableta, y
su reloj empieza cuando él lo abre.
"""
from __future__ import annotations

from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio.errores import DatosInvalidos, NoEncontrado, TransicionInvalida
from .base import _CasoDeUso
from .motor import Motor
from .puertos import Actor, UnidadDeTrabajo


def vista_admision(a: dict) -> dict:
    return {k: a.get(k) for k in ("id", "asignacion_id", "alumno_id", "alumno_rotulo", "dispositivo_id", "dispositivo_rotulo", "nivel_exigido",
                                  "nivel_alcanzado", "estado", "nivel_admitido", "motivo", "solicitada_en", "decidido_por", "decidido_en")}


class _Admision(_CasoDeUso):
    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def _asignacion(self, uow: UnidadDeTrabajo, asignacion_id: str, ahora: int) -> dict:
        asignacion = uow.asignaciones.por_id(asignacion_id) if asignacion_id else None
        if asignacion is None:
            raise NoEncontrado("No existe esa evaluación.", asignacion_id=asignacion_id)
        return self.motor.asegurar_asignacion(uow, asignacion, ahora)


class ListarAdmisiones(_Admision):
    """Las tabletas que esperan la decisión del profesor (y, con `todas`, también las ya decididas)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, todas: bool = False) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_READ, asignacion)
            filas = uow.admisiones.de_asignacion(asignacion_id, solo_en_espera=not todas)
            return {"admisiones": [vista_admision(a) for a in filas], "nivel_examen": asignacion["nivel_examen"], "servidor_en": ahora}


class DecidirAdmision(_Admision):
    """`datos`: `{decision: admitir | rechazar, nivel_admitido?, motivo}`. Se puede cambiar un rechazo mientras la evaluación esté abierta; una tableta ya
    admitida no se rechaza (el alumno puede estar presentando)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, admision_id: str, datos: dict) -> dict:
        decision = str(datos.get("decision") or "").strip().lower()
        if decision not in cat.DECISIONES_ADMISION:
            raise DatosInvalidos(f"decision debe ser «{cat.DECISION_ADMITIR}» o «{cat.DECISION_RECHAZAR}».", decision=decision)
        motivo = str(datos.get("motivo") or "").strip()
        if len(motivo) < 3:
            raise DatosInvalidos("La excepción se confirma de forma explícita y con motivo: queda en el expediente del intento.")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = self._asignacion(uow, asignacion_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_OVERRIDE, asignacion)
            admision = uow.admisiones.por_id(admision_id) if admision_id else None
            if admision is None or admision["asignacion_id"] != asignacion_id:
                raise NoEncontrado("No existe esa solicitud de admisión en esta evaluación.", admision_id=admision_id)
            if asignacion["estado"] not in cat.ABIERTAS:
                raise TransicionInvalida("La evaluación no está abierta: ya no se decide sobre tabletas.", estado=asignacion["estado"])
            if admision["estado"] == cat.ADMITIDO:
                raise TransicionInvalida("Esa tableta ya fue admitida: el alumno puede estar presentando.", estado=admision["estado"],
                                         destino=cat.RECHAZADO if decision == cat.DECISION_RECHAZAR else cat.ADMITIDO)
            quien = actor.id or "docente"
            if decision == cat.DECISION_ADMITIR:
                nivel = bloqueo.validar_nivel(datos.get("nivel_admitido"), "nivel_admitido")
                bloqueo.validar_admision(admision["nivel_exigido"], nivel)
                campos = {"estado": cat.ADMITIDO, "nivel_admitido": nivel, "motivo": motivo[:200], "decidido_por": quien[:64], "decidido_en": ahora}
            else:
                campos = {"estado": cat.RECHAZADO, "nivel_admitido": "", "motivo": motivo[:200], "decidido_por": quien[:64], "decidido_en": ahora}
            anterior = {"estado": admision["estado"]}
            admision = uow.admisiones.actualizar(admision_id, **campos)
            intento = next((i for i in uow.intentos.del_alumno(asignacion_id, admision["alumno_id"]) if i["estado"] in cat.VIVOS), None)
            if decision == cat.DECISION_ADMITIR:
                self.motor.publicar(uow, "Admision", admision_id, cat.EV_ADMITIDO_BAJO_NIVEL, {
                    "admision_id": admision_id, "asignacion_id": asignacion_id, "alumno_id": admision["alumno_id"],
                    "dispositivo_id": admision["dispositivo_id"], "nivel_exigido": admision["nivel_exigido"],
                    "nivel_admitido": admision["nivel_admitido"], "por": quien}, ahora)
                uow.auditoria.registrar(quien, cat.A_NIVEL_EXCEPCION, "m10_admision", admision_id, anterior=anterior,
                                        nuevo={"estado": cat.ADMITIDO, "nivel_exigido": admision["nivel_exigido"], "nivel_admitido": admision["nivel_admitido"],
                                               "dispositivo_id": admision["dispositivo_id"]}, motivo=motivo, dispositivo_id=admision["dispositivo_id"] or None)
                if intento is not None:
                    self.motor.incidente(uow, intento, "admitido_bajo_nivel", ahora, detalle={
                        "nivel_exigido": admision["nivel_exigido"], "nivel_admitido": admision["nivel_admitido"], "por": quien, "motivo": motivo},
                        dispositivo_id=admision["dispositivo_id"], actor=quien, asignacion=asignacion)
            uow.auditoria.registrar(quien, "evaluacion.admision.decidida", "m10_admision", admision_id, anterior=anterior,
                                    nuevo={"estado": admision["estado"], "nivel_admitido": admision["nivel_admitido"]}, motivo=motivo)
            self.motor.avisar(uow, asignacion)
            return vista_admision(admision)
