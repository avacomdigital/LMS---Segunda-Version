"""
Las respuestas de un intento, desde la tableta y desde el profesor (FUN-110, FUN-111, CAP-065; BR-009, BR-071, BR-074, BR-138; INV-013):

  EnviarRespuestas   la tableta guarda respuestas (una a una, idempotente por pregunta + sesión + secuencia). Sirve igual para lo enviado en línea
                     que para lo que sale de la cola local tras una desconexión. Cada respuesta se guarda en el momento en que se confirma, sin
                     esperar a la entrega del intento (BR-071).
  DecidirEnvio       BR-074: lo que llegó fuera de la ventana de gracia espera al profesor, que lo acepta o lo descarta. Nunca se descarta en silencio.

Un reenvío del mismo paquete se acusa igual y no cambia nada (INV-005, TST-040). Lo que llega a un intento ya entregado pasa por la política de
recepción del plazo (D-14): se acepta dentro de la gracia, espera al profesor pasada ésta y se rechaza si se capturó después del cierre.
"""
from __future__ import annotations

from ..dominio import asignacion as asig_dom
from ..dominio import catalogos as cat
from ..dominio import intento as int_dom
from ..dominio import respuestas as resp_dom
from ..dominio.errores import (
    AsignacionCerrada,
    DatosInvalidos,
    IntentoCerrado,
    NoEncontrado,
    TransicionInvalida,
)
from .alumno import _Alumno
from .base import Contexto, _CasoDeUso
from .motor import Motor
from .puertos import Actor, UnidadDeTrabajo


class EnviarRespuestas(_Alumno):
    """`datos`: `{dispositivo, alumno_id, respuestas: [{pregunta_ref, respuesta, secuencia, capturada_en?, capturada_en_tableta?}], origen?,
    pregunta_actual?, transcurrido_ms?}`. Devuelve el acuse: qué se aceptó, qué era un reenvío, qué llegó superado y qué se rechazó y por qué."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            self.s.autorizacion.exigir(actor, cat.P_ANSWER_SUBMIT)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            sesion = self.sesion_de(ctx, intento)
            return self.integrar(uow, intento, asignacion, sesion, datos, ahora, permitir_vacio=False)

    # ---------------------------------------------------------------------------------------- la integración

    def integrar(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, sesion: dict, datos: dict, ahora: int, *,
                 permitir_vacio: bool) -> dict:
        """Lo que comparten `EnviarRespuestas` y la entrega: valida, fusiona, publica y acusa recibo. Escribe en el intento."""
        origen = str(datos.get("origen") or cat.DIRECTO)
        if origen not in cat.ORIGENES_RESPUESTA:
            raise DatosInvalidos(f"`origen` debe ser uno de: {', '.join(cat.ORIGENES_RESPUESTA)}.", origen=origen)
        entrada = datos.get("respuestas")
        if not permitir_vacio and (not isinstance(entrada, list) or not entrada):
            raise DatosInvalidos("`respuestas` debe ser una lista con al menos una respuesta.")
        limpias, rechazadas = resp_dom.limpiar_respuestas(
            entrada, intento["armado"], (intento.get("armado_meta") or {}).get("tipos") or {}, self.s.config.max_respuestas)
        estado = intento["estado"]
        if estado in cat.ENTREGADOS:
            return self._tardia(uow, intento, asignacion, sesion, limpias, rechazadas, origen, ahora)
        if estado not in cat.ACEPTAN_RESPUESTAS:
            raise IntentoCerrado(f"El intento está «{estado}»: no admite respuestas.", estado=estado)

        fusionadas, resultado = resp_dom.fusionar(intento["respuestas"], limpias, sesion_ref=sesion["sesion_ref"],
                                                  sesion_orden=int(sesion.get("orden") or 0), ahora=ahora, origen=origen)
        campos: dict = {"respuestas": fusionadas, "secuencia_maxima": resp_dom.secuencia_maxima(fusionadas)}
        if limpias:
            campos["ultimo_latido_en"] = ahora          # escribir es estar vivo
        actual = str(datos.get("pregunta_actual") or "")
        if actual and actual in intento["armado"]:
            campos["pregunta_actual"] = actual
        campos.update(int_dom.reconciliar_reloj({**intento, **campos}, ahora, datos.get("transcurrido_ms")))
        intento = uow.intentos.actualizar(intento["id"], **campos)
        self._publicar_resultado(uow, intento, asignacion, resultado, sesion, ahora)
        if estado in cat.SUSPENDIDOS and (resultado.aceptadas or resultado.superadas):
            self.motor.incidente(uow, intento, "respuesta_tardia", ahora, detalle={
                "preguntas": sorted(set(resultado.aceptadas + resultado.superadas)), "motivo": "capturadas_durante_una_pausa"},
                ref_cliente=self._clave_de_lote(sesion["sesion_ref"], limpias), asignacion=asignacion)
        elif resultado.superadas:
            self.motor.incidente(uow, intento, "respuesta_tardia", ahora, detalle={
                "preguntas": sorted(set(resultado.superadas)), "motivo": "sesion_superada_o_secuencia_menor"},
                ref_cliente=self._clave_de_lote(sesion["sesion_ref"], limpias), asignacion=asignacion)
        if resultado.aceptadas:
            self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
        return self._acuse(intento, asignacion, resultado, rechazadas, ahora, politica=asig_dom.ACEPTAR)

    @staticmethod
    def _clave_de_lote(sesion_ref: str, limpias: list[dict]) -> str:
        """Un lote reenviado produce el mismo incidente una sola vez (INV-005)."""
        huella = "|".join(sorted(f"{r['pregunta_ref']}:{r['secuencia']}" for r in limpias))
        return f"tardia:{sesion_ref[:8]}:{abs(hash(huella)) % 10**10}"

    def _publicar_resultado(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, resultado: resp_dom.ResultadoFusion, sesion: dict,
                            ahora: int) -> None:
        por_ref = {r["pregunta_ref"]: r for r in intento["respuestas"]}
        for ref in resultado.aceptadas:
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_RESPUESTA_REGISTRADA, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "pregunta_ref": ref,
                "curso_version": intento["curso_version"], "sesion_ref": sesion["sesion_ref"],
                "secuencia": (por_ref.get(ref) or {}).get("secuencia")}, ahora)       # sin el contenido de la respuesta (BR-127)
        for ref in resultado.duplicadas:
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_RESPUESTA_DEDUPLICADA, {
                "intento_id": intento["id"], "pregunta_ref": ref, "causa": "reenvio", "clave": f"{intento['id']}|{ref}|{sesion['sesion_ref']}"}, ahora)

    def _acuse(self, intento: dict, asignacion: dict, resultado: resp_dom.ResultadoFusion, rechazadas: list[dict], ahora: int, *,
               politica: str) -> dict:
        return {
            "acuse": True, "politica": politica,
            "aceptadas": resultado.aceptadas, "duplicadas": resultado.duplicadas, "superadas": resultado.superadas, "rechazadas": rechazadas,
            "intento": {"id": intento["id"], "estado": intento["estado"], "respondidas": len(intento["respuestas"]),
                        "secuencia_maxima": intento.get("secuencia_maxima") or 0, "envio_tardio": intento.get("envio_tardio") or ""},
            "reloj": int_dom.reloj(intento, ahora), "recibida_en": ahora, "servidor_en": ahora}

    # --------------------------------------------------------------------------- lo que llega a un intento ya entregado

    def _tardia(self, uow: UnidadDeTrabajo, intento: dict, asignacion: dict, sesion: dict, limpias: list[dict], rechazadas: list[dict],
                origen: str, ahora: int) -> dict:
        """BR-074, DEC-019, TST-042. Un reenvío idéntico de lo ya entregado se acusa sin tocar nada (INV-005). Lo demás depende de QUIÉN entregó y de
        CUÁNDO se capturó: si entregó el alumno, no hay más respuestas; si entregó el nodo (tiempo, plazo, cierre), lo capturado antes del corte se
        acepta dentro de la gracia y, pasada ésta, espera al profesor; lo capturado después se rechaza."""
        _, prueba = resp_dom.fusionar(intento["respuestas"], limpias, sesion_ref=sesion["sesion_ref"], sesion_orden=int(sesion.get("orden") or 0),
                                      ahora=ahora, origen=origen)
        if not prueba.aceptadas and not prueba.superadas:
            self._publicar_resultado(uow, intento, asignacion, prueba, sesion, ahora)
            return self._acuse(intento, asignacion, prueba, rechazadas, ahora, politica=asig_dom.ACEPTAR)
        if intento["estado"] == cat.ANULADO or intento.get("origen_entrega") == cat.O_ALUMNO:
            raise IntentoCerrado("El intento ya se entregó: no admite respuestas nuevas.", estado=intento["estado"])
        capturas = [r["capturada_en"] for r in limpias if r.get("capturada_en")]
        cierre = asig_dom.cierre_de_recepcion(intento, asignacion)
        politica = asig_dom.politica_de_recepcion(cerrada_en=cierre, capturada_en=max(capturas) if capturas else None,
                                                  recibida_en=ahora, gracia_ms=asignacion["gracia_ms"])
        if politica == asig_dom.RECHAZAR:
            raise AsignacionCerrada("El examen ya se entregó y esto se capturó después del cierre.", entregado_en=intento.get("entregado_en"),
                                    cerrado_en=cierre)
        if politica == asig_dom.ACEPTAR:
            fusionadas, resultado = resp_dom.fusionar(intento["respuestas"], limpias, sesion_ref=sesion["sesion_ref"],
                                                      sesion_orden=int(sesion.get("orden") or 0), ahora=ahora, origen=cat.COLA)
            intento = uow.intentos.actualizar(intento["id"], respuestas=fusionadas, secuencia_maxima=resp_dom.secuencia_maxima(fusionadas))
            self._publicar_resultado(uow, intento, asignacion, resultado, sesion, ahora)
            self.motor.incidente(uow, intento, "respuesta_tardia", ahora, detalle={
                "preguntas": sorted(set(resultado.aceptadas)), "motivo": "dentro_de_la_gracia"},
                ref_cliente=self._clave_de_lote(sesion["sesion_ref"], limpias), asignacion=asignacion)
            intento = self.motor.recalificar(uow, intento, asignacion, ahora)
            return self._acuse(intento, asignacion, resultado, rechazadas, ahora, politica=politica)
        # DECIDE_EL_PROFESOR: se conservan, nunca se descartan en silencio (BR-074)
        pendientes = list(intento.get("respuestas_pendientes") or [])
        ya = {(p["pregunta_ref"], p.get("sesion_ref"), p["secuencia"]) for p in pendientes}
        nuevas = 0
        for r in limpias:
            clave = (r["pregunta_ref"], sesion["sesion_ref"], r["secuencia"])
            if clave in ya:
                continue
            pendientes.append({**r, "sesion_ref": sesion["sesion_ref"], "sesion_orden": int(sesion.get("orden") or 0), "recibida_en": ahora,
                               "origen": origen})
            nuevas += 1
        campos: dict = {"respuestas_pendientes": pendientes}
        if nuevas and intento.get("envio_tardio") != cat.TARDIO_PENDIENTE:
            campos["envio_tardio"] = cat.TARDIO_PENDIENTE
        intento = uow.intentos.actualizar(intento["id"], **campos)
        if nuevas:
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_ENVIO_TARDIO_PENDIENTE, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "respuestas": nuevas}, ahora)
            self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
        return self._acuse(intento, asignacion, resp_dom.ResultadoFusion(), rechazadas, ahora, politica=politica)


class DecidirEnvio(_CasoDeUso):
    """BR-074: el profesor decide, caso por caso, lo que llegó fuera de la ventana de gracia. Queda constancia de quién decidió y cuándo."""

    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def ejecutar(self, actor: Actor, intento_id: str, decision: str, motivo: str = "") -> dict:
        if decision not in cat.DECISIONES_ENVIO:
            raise DatosInvalidos(f"La decisión es «{cat.DECISION_ACEPTAR}» o «{cat.DECISION_DESCARTAR}».", decision=decision)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento = uow.intentos.por_id(intento_id) if intento_id else None
            if intento is None:
                raise NoEncontrado("No existe ese intento.", intento_id=intento_id)
            asignacion = uow.asignaciones.por_id(intento["asignacion_id"])
            self.s.autorizacion.exigir(actor, cat.P_DEADLINE_ENFORCE, asignacion)
            if intento.get("envio_tardio") != cat.TARDIO_PENDIENTE:
                raise TransicionInvalida("Sólo se decide sobre un envío pendiente de decisión.", estado=intento["estado"],
                                         envio_tardio=intento.get("envio_tardio") or "")
            quien = actor.id or "docente"
            if decision == cat.DECISION_ACEPTAR:
                respuestas = list(intento["respuestas"])
                for grupo in self._por_sesion(intento["respuestas_pendientes"]):
                    respuestas, _ = resp_dom.fusionar(respuestas, grupo["respuestas"], sesion_ref=grupo["sesion_ref"], sesion_orden=grupo["orden"],
                                                      ahora=ahora, origen=cat.COLA)
                intento = uow.intentos.actualizar(intento["id"], respuestas=respuestas, secuencia_maxima=resp_dom.secuencia_maxima(respuestas))
                destino, nuevo = cat.TARDIO_ACEPTADO, "evaluacion.envio.aceptado"
            else:
                destino, nuevo = cat.TARDIO_DESCARTADO, "evaluacion.envio.descartado"
            decidido = {"decision": decision, "por": quien, "en": ahora, "motivo": str(motivo or "")[:200]}
            intento = uow.intentos.actualizar(intento["id"], envio_tardio=destino, decision_envio=decidido)
            if decision == cat.DECISION_ACEPTAR:
                intento = self.motor.recalificar(uow, intento, asignacion, ahora)
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_ENVIO_TARDIO_DECIDIDO, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "decision": decision, "por": quien}, ahora)
            uow.auditoria.registrar(quien, nuevo, "m10_intento_formal", intento["id"], anterior={"envio_tardio": cat.TARDIO_PENDIENTE},
                                    nuevo={"envio_tardio": destino}, **({"motivo": decidido["motivo"]} if decidido["motivo"] else {}))
            self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
            return {"intento_id": intento["id"], "estado": intento["estado"], "envio_tardio": destino, "decidido_por": quien, "decidido_en": ahora}

    @staticmethod
    def _por_sesion(pendientes: list[dict]) -> list[dict]:
        grupos: dict[tuple, dict] = {}
        for p in pendientes:
            clave = (p.get("sesion_ref", ""), int(p.get("sesion_orden") or 0))
            grupo = grupos.setdefault(clave, {"sesion_ref": clave[0], "orden": clave[1], "respuestas": []})
            grupo["respuestas"].append({k: p[k] for k in ("pregunta_ref", "respuesta", "secuencia", "capturada_en", "capturada_en_tableta") if k in p})
        return list(grupos.values())
