"""
Registrar la calificación normalizada de un intento (FUN-119) y anularla cuando MOD-010 anula el intento.

Una calificación se registra UNA vez por intento y sólo cuando el intento está calificado del todo en MOD-010: en estado `calificado`, sin respuestas
pendientes de revisión docente, sin calificación pendiente de la biblioteca y con porcentaje. Un intento en curso, entregado sin calificar o en revisión NO
produce una calificación (una actividad pendiente no es un cero). Tampoco la produce un nivel en modo simple: completar una actividad no crea un registro
calificable formal. La puntuación se toma de MOD-010 (`porcentaje`, escala 0–100) y se normaliza a dos decimales; aquí no se vuelve a calcular ninguna
respuesta.

Idempotente: registrar dos veces el mismo intento no duplica nada. Un cambio posterior de la puntuación en MOD-010 sólo se recoge si el profesor reabrió la
calificación (FUN-122): de lo contrario no pisa ni la nota ni sus ajustes y se señala como desfase.
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import puntaje as pj
from ..dominio.errores import ConflictoDeVersion, IntentoNoCalificable, ModoSimple, NoEncontrado
from .base import _CasoDeUso, contexto_de, exigir_en_asignacion, exigir_sobre_resultado, modo_del_nivel, nuevo_id, salida_calificacion
from .derivados import RecalcularResultado
from .puertos import Actor, UnidadDeTrabajo


def por_que_no_es_calificable(intento: dict, evaluacion) -> str | None:
    """Por qué un intento todavía no admite una calificación registrada, o None si la admite."""
    if intento["estado"] == cat.I_ANULADO:
        return "anulado"
    if intento["estado"] != cat.I_CALIFICADO:
        return "revision_pendiente" if intento["estado"] == cat.I_EN_REVISION else "sin_calificar"
    if intento.get("calificacion_pendiente"):
        return "calificacion_pendiente"
    if intento.get("requiere_revision") or intento.get("sin_calificar") or evaluacion.pendientes_de(intento):
        return "revision_pendiente"
    if intento.get("porcentaje") is None:
        return "sin_porcentaje"
    return None


_MOTIVOS = {
    "anulado": "El intento fue anulado.",
    "revision_pendiente": "Quedan respuestas por revisar: no se registra una calificación definitiva mientras haya componentes pendientes.",
    "sin_calificar": "El intento aún no está calificado.",
    "calificacion_pendiente": "La biblioteca todavía no calificó las respuestas.",
    "sin_porcentaje": "El intento no tiene puntuación.",
}


class Registrador(_CasoDeUso):
    """La operación común: la usan el consumidor de eventos, la confirmación de una revisión y el registro manual. Corre DENTRO de la transacción del
    llamador. Devuelve `(calificación | None, resultado, motivo)` con `resultado` ∈ creada · recalculada · reabierta · sin_cambios · anulada · modo_simple ·
    anterior_al_modo · no_calificable · ausente. Sólo `confirmar_recalculo` (la confirmación de la revisión de una calificación reabierta) la vuelve a calcular."""

    def registrar(self, uow: UnidadDeTrabajo, intento_id: str, ahora: int, *, actor_id: str, evento_en: int | None = None,
                  confirmar_recalculo: bool = False) -> tuple[dict | None, str, str | None]:
        """`evento_en` es el instante (reloj del nodo) del evento de MOD-010 que lo provoca, si lo hay: un evento ANTERIOR a que el nivel pasara a modo
        calificaciones no registra nada (ni al consumirlo tarde ni al reproducirlo tras una restauración): pasar de modo no convierte notas técnicas solas."""
        intento = uow.evaluacion.intento(intento_id)
        if intento is None:
            return None, "ausente", None
        asignacion = uow.evaluacion.asignacion(intento["asignacion_id"])
        if asignacion is None:
            return None, "ausente", None
        existente = uow.calificaciones.por_intento(intento_id)
        if intento["estado"] == cat.I_ANULADO:
            return self._anular(uow, existente, intento, asignacion, ahora, actor_id), "anulada" if existente else "ausente", None
        motivo = por_que_no_es_calificable(intento, uow.evaluacion)
        if motivo:
            return existente, "no_calificable", motivo
        contexto = contexto_de(uow, asignacion, intento["alumno_id"])
        modo, _ = modo_del_nivel(uow, contexto["nivel_clave"])
        if modo == cat.SIMPLE and existente is None:
            RecalcularResultado(self.s).resultado(uow, asignacion, intento["alumno_id"], ahora)
            return None, "modo_simple", None
        if existente is None and evento_en is not None:
            configuracion = uow.niveles.get(contexto["nivel_clave"]) or {}
            if configuracion.get("modo_desde", 0) > evento_en:
                RecalcularResultado(self.s).resultado(uow, asignacion, intento["alumno_id"], ahora)
                return None, "anterior_al_modo", None
        interno = pj.interno_desde_porcentaje(intento["porcentaje"])
        if existente is None:
            fila, resultado = self._crear(uow, intento, asignacion, contexto, interno, ahora), "creada"
        elif existente["estado"] == cat.REABIERTA and confirmar_recalculo:
            fila, resultado = self._recalcular(uow, existente, intento, interno, ahora, actor_id), "recalculada"
        elif existente["estado"] == cat.REABIERTA:
            fila, resultado = existente, "reabierta"          # un evento (viejo o nuevo) NUNCA cierra una reapertura: la cierra el profesor al confirmar su revisión
        else:
            fila, resultado = existente, "sin_cambios"
        RecalcularResultado(self.s).resultado(uow, asignacion, intento["alumno_id"], ahora)
        return fila, resultado, None

    # ------------------------------------------------------------------------------------------------ creación
    def _crear(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, contexto: dict, interno, ahora: int) -> dict:
        por = (intento.get("calificado_por") or cat.SISTEMA)
        automatica = por == cat.SISTEMA
        aciertos, preguntas = uow.evaluacion.aciertos_de(intento)
        fila = uow.calificaciones.crear({
            "id": nuevo_id(), "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], **contexto,
            "numero_intento": intento.get("numero") or 1, "puntaje_original": interno, "puntaje_efectivo": interno, "puntaje_fuente": interno,
            "aciertos": aciertos, "preguntas": preguntas, "regla_puntuacion": cat.REGLA_AUTOMATICA if automatica else cat.REGLA_REVISION_DOCENTE,
            "origen": cat.AUTOMATICA if automatica else cat.DOCENTE, "evaluador_id": por, "estado": cat.REVISADA, "version": 1,
            "registrada_en": ahora, "actualizada_en": ahora})
        uow.versiones.anexar(fila["id"], cat.V_REGISTRO, actor_id=por, en=ahora, puntaje_nuevo=interno, estado_nuevo=cat.REVISADA,
                             solicitud_id=f"reg:{intento['id']}", datos={"regla": fila["regla_puntuacion"], "origen": fila["origen"]})
        self._publicar(uow, "Calificacion", fila["id"], cat.EV_REGISTRADA, {
            "calificacion_id": fila["id"], "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"],
            "grupo_id": contexto["grupo_id"], "puntaje": pj.como_numero(interno), "regla": fila["regla_puntuacion"], "origen": fila["origen"],
            "evaluador_id": por, "recalculo": False}, ahora)
        uow.auditoria.registrar(por, cat.A_REGISTRADA, "m11_calificacion", fila["id"], nuevo={
            "intento_id": intento["id"], "puntaje": pj.como_numero(interno), "regla": fila["regla_puntuacion"], "estado": cat.REVISADA})
        return fila

    # ---------------------------------------------------------------------------------- recalcular tras reabrir
    def _recalcular(self, uow: UnidadDeTrabajo, c: dict, intento: dict, interno, ahora: int, actor_id: str) -> dict:
        """Confirmar una revisión de una calificación reabierta (FUN-122): el valor efectivo vuelve a ser el que dice MOD-010 tras recalificar.

        Si la calificación tenía un AJUSTE del profesor (efectivo ≠ lo que dijo MOD-010) y recalificar no cambió lo que dice MOD-010, el ajuste sigue en pie: reabrir y
        confirmar sin tocar nada no lo borra. Si recalificar SÍ cambió la puntuación, el ajuste dejó de tener base: el efectivo pasa al nuevo valor y el historial
        guarda que se descartó (con el valor que tenía), para que quien lo ajustó lo vuelva a decidir."""
        por = intento.get("calificado_por") or actor_id or cat.SISTEMA
        aciertos, preguntas = uow.evaluacion.aciertos_de(intento)
        ajuste_vigente = c["puntaje_efectivo"] != c["puntaje_fuente"]
        conserva = ajuste_vigente and interno == c["puntaje_fuente"]
        efectivo = c["puntaje_efectivo"] if conserva else interno
        nueva = uow.calificaciones.actualizar_si_version(
            c["id"], c["version"], puntaje_efectivo=efectivo, puntaje_fuente=interno, aciertos=aciertos, preguntas=preguntas, estado=cat.REVISADA,
            regla_puntuacion=cat.REGLA_REVISION_DOCENTE, origen=cat.DOCENTE, evaluador_id=por, actualizada_en=ahora)
        if nueva is None:
            actual = uow.calificaciones.por_id(c["id"])
            raise ConflictoDeVersion("La calificación cambió mientras se confirmaba la revisión: vuelve a leerla.", version_actual=actual["version"])
        uow.versiones.anexar(c["id"], cat.V_RECALCULO, actor_id=por, en=ahora, puntaje_anterior=c["puntaje_efectivo"], puntaje_nuevo=efectivo,
                             estado_anterior=cat.REABIERTA, estado_nuevo=cat.REVISADA, motivo="Recalificación confirmada tras reabrir",
                             solicitud_id=f"recalculo:{c['id']}:{c['version']}",
                             datos={"regla": cat.REGLA_REVISION_DOCENTE, "fuente_anterior": pj.como_numero(c["puntaje_fuente"]), "fuente_nueva": pj.como_numero(interno),
                                    "ajuste_conservado": conserva, "ajuste_descartado": ajuste_vigente and not conserva})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_REGISTRADA, {
            "calificacion_id": c["id"], "intento_id": intento["id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"], "grupo_id": c["grupo_id"],
            "puntaje": pj.como_numero(efectivo), "regla": cat.REGLA_REVISION_DOCENTE, "origen": cat.DOCENTE, "evaluador_id": por, "recalculo": True}, ahora)
        uow.auditoria.registrar(por, cat.A_REGISTRADA, "m11_calificacion", c["id"],
                                anterior={"puntaje_efectivo": pj.como_numero(c["puntaje_efectivo"]), "estado": cat.REABIERTA},
                                nuevo={"puntaje_efectivo": pj.como_numero(efectivo), "estado": cat.REVISADA, "recalculo": True,
                                       "ajuste_descartado": ajuste_vigente and not conserva})
        return nueva

    # --------------------------------------------------------------------------------------------- anulación
    def _anular(self, uow: UnidadDeTrabajo, c: dict | None, intento: dict, asignacion: dict, ahora: int, actor_id: str) -> dict | None:
        """MOD-010 anuló el intento (una persona, con motivo): la calificación deja de contar. No se borra: queda `anulada` con su historial."""
        if c is None:
            RecalcularResultado(self.s).resultado(uow, asignacion, intento["alumno_id"], ahora)
            return None
        if c["estado"] == cat.ANULADA:
            return c
        nueva = uow.calificaciones.actualizar_si_version(c["id"], c["version"], estado=cat.ANULADA, publicada_en=None, publicada_por="", presentacion={},
                                                          actualizada_en=ahora)
        if nueva is None:
            return uow.calificaciones.por_id(c["id"])
        quien = intento.get("anulado_por") or actor_id or cat.SISTEMA
        uow.versiones.anexar(c["id"], cat.V_ANULACION, actor_id=quien, en=ahora, puntaje_anterior=c["puntaje_efectivo"], estado_anterior=c["estado"],
                             estado_nuevo=cat.ANULADA, motivo=intento.get("motivo_anulacion") or "Intento anulado en la evaluación",
                             solicitud_id=f"anulacion:{c['id']}", datos={"estaba_publicada": c["estado"] == cat.DEFINITIVA})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_ANULADA, {
            "calificacion_id": c["id"], "intento_id": intento["id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"],
            "estaba_publicada": c["estado"] == cat.DEFINITIVA}, ahora)
        uow.auditoria.registrar(quien, cat.A_ANULADA, "m11_calificacion", c["id"], anterior={"estado": c["estado"]}, nuevo={"estado": cat.ANULADA},
                                motivo=intento.get("motivo_anulacion") or None)
        RecalcularResultado(self.s).resultado(uow, asignacion, intento["alumno_id"], ahora)
        return nueva


class RegistrarCalificacion(_CasoDeUso):
    """Registro manual de la calificación de un intento ya calificado (`POST …/intentos/{id}/registrar/`): lo que el consumidor hace solo, a petición del
    profesor. Sirve sobre todo cuando el nivel pasó de modo simple a calificaciones y quedaron evaluaciones calificadas sin registrar: ese paso NO es
    automático (no se convierten notas técnicas en calificaciones sin que alguien lo decida)."""

    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento = uow.evaluacion.intento(intento_id)
            if intento is None:
                raise NoEncontrado("No existe ese intento.", intento_id=intento_id)
            asignacion = uow.evaluacion.asignacion(intento["asignacion_id"])
            contexto = contexto_de(uow, asignacion, intento["alumno_id"])
            exigir_sobre_resultado(uow, self.s.autorizacion, actor, cat.P_MODIFY, grupo_id=contexto["grupo_id"], asignacion_id=asignacion["id"])
            modo, _ = modo_del_nivel(uow, contexto["nivel_clave"])
            fila, resultado, motivo = Registrador(self.s).registrar(uow, intento_id, ahora, actor_id=actor.id or cat.SISTEMA)
            if resultado == "no_calificable":
                raise IntentoNoCalificable(_MOTIVOS.get(motivo or "", "El intento no está calificado."), motivo=motivo, estado=intento["estado"])
            if resultado == "modo_simple":
                raise ModoSimple("El nivel de este grupo está en modo simple: no se registran calificaciones. Un administrador puede activar el modo calificaciones.",
                                 nivel_clave=contexto["nivel_clave"] or None)
            return {"resultado": resultado, "calificacion": salida_calificacion(uow, fila, intento=intento) if fila else None, "servidor_en": ahora, "modo": modo}


class RegistrarAsignacion(_CasoDeUso):
    """Registra de una vez las calificaciones de TODOS los intentos ya calificados de una evaluación (`POST …/asignaciones/{id}/registrar/`): lo mismo que `RegistrarCalificacion`
    para cada intento, a petición del profesor. Es el camino cuando el nivel pasó de modo simple (o de no tener nivel) a modo calificaciones y la evaluación ya estaba calificada:
    ese paso NO registra nada solo, y sin esto el libro dice «sin registro» y no hay nota que ver. Los intentos que aún no se pueden registrar se cuentan con su motivo y no
    impiden los demás. Idempotente: repetirlo no crea nada dos veces. Lo registrado queda `revisada` (provisional, sin publicar): publicar es otra decisión."""

    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = uow.evaluacion.asignacion(asignacion_id)
            if asignacion is None:
                raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
            exigir_en_asignacion(uow, self.s.autorizacion, actor, cat.P_MODIFY, asignacion)
            registrador = Registrador(self.s)
            registradas, ya_registradas, en_modo_simple = [], 0, 0
            omitidas: list[dict] = []
            for intento in uow.evaluacion.intentos_de_asignacion(asignacion_id):
                contexto = contexto_de(uow, asignacion, intento["alumno_id"])
                modo, _ = modo_del_nivel(uow, contexto["nivel_clave"])
                if modo == cat.SIMPLE and uow.calificaciones.por_intento(intento["id"]) is None:
                    en_modo_simple += 1
                    continue
                fila, resultado, motivo = registrador.registrar(uow, intento["id"], ahora, actor_id=actor.id or cat.SISTEMA)
                if resultado == "creada" and fila:
                    registradas.append(fila["id"])
                elif resultado == "no_calificable":
                    omitidas.append({"intento_id": intento["id"], "alumno_id": intento["alumno_id"], "motivo": motivo, "detalle": _MOTIVOS.get(motivo or "", "")})
                elif resultado in ("sin_cambios", "reabierta", "recalculada"):
                    ya_registradas += 1
            return {"asignacion_id": asignacion_id, "registradas": len(registradas), "calificaciones": registradas, "ya_registradas": ya_registradas,
                    "no_registrables": omitidas, "en_modo_simple": en_modo_simple, "servidor_en": ahora}
