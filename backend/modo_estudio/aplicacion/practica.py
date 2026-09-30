"""
StudyPracticeService · la práctica autocalificable, separada de la evaluación formal (FUN-083, FUN-088, BR-055, D-5, D-6, NFR-012).

  AbrirPractica      `POST /lecciones/{id}/practica/` (`study.answer.submit`): reanuda la práctica en curso (FUN-088, `estudio.actividad.reanudada.v1`)
                     o abre la siguiente («Intentar nuevamente»); `nueva: true` fuerza una nueva. Devuelve la actividad SIN claves.
  ResponderPractica  `POST /practicas/{id}/respuestas/`: guarda cada respuesta (idempotente por secuencia, INV-013) y la califica DONDE VIVE la clave
                     (la biblioteca) en UNA llamada por envío: retroalimentación en ≤ 2 s. Sin biblioteca se guarda SIN calificar y se califica en la
                     siguiente lectura o sincronización (D-6).
  TerminarPractica   `POST /practicas/{id}/terminar/`: cierra la práctica, marca su bloque como atendido y dice «7 de 8 correctas». Nunca «nota».

BR-055: nada de esto consume ni modifica `m07_intento` ni `m10_intento`; no hay tope de intentos. DEC-032: el resultado es un conteo amable, no una nota.
Las lecturas de la biblioteca y la calificación ocurren FUERA de la transacción; lo que se guarda se recalcula dentro con el estado vigente.
"""
from __future__ import annotations

from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import practica as practica_dom
from ..dominio.errores import (
    DatosInvalidos,
    FuenteError,
    FuenteNoDisponible,
    NoEncontrado,
    NoEsElTitular,
    PracticaTerminada,
)
from . import dto
from .base import Contexto, _CasoDeUso, asignacion_del_alumno, nuevo_id, resolver_contexto
from .paquetes import semilla_de
from .puertos import Actor, UnidadDeTrabajo
from .tareas import (
    campos_de_actividad,
    exigir_escritura,
    obtener_o_crear,
    refrescar_estructura,
    resumir_practicas,
    terminar_practica,
)


def campos_de_resultado(respuestas: list[dict]) -> dict:
    """Lo que la práctica guarda de sus respuestas: aciertos y la escala interna (que no se publica, DEC-032)."""
    puntaje, maximo = practica_dom.totales(respuestas)
    return {"respuestas": respuestas, "aciertos": practica_dom.aciertos(respuestas), "puntaje": puntaje, "puntaje_maximo": maximo}


def items_de(objeto_ref: str, respuestas: list[dict]) -> list[dict]:
    """Lo que se manda a calificar: la pregunta y lo que el alumno contestó (nunca una clave: no la hay)."""
    return [{"objeto_ref": objeto_ref, "pregunta_ref": r["pregunta_ref"], "respuesta": r["respuesta"]} for r in respuestas]


class _CasoDePractica(_CasoDeUso):
    def _calificar(self, asignacion: dict, objeto_ref: str, respuestas: list[dict]) -> dict[str, tuple[int | None, dict | None]]:
        """UNA llamada a la biblioteca por envío (`evaluar_lote`). `{pregunta_ref: (secuencia, veredicto | None)}`; sin biblioteca, todo None."""
        if not respuestas:
            return {}
        veredictos = self.s.contenido.calificar(asignacion["fuente_curso"], asignacion["curso_ref"], asignacion["curso_version"],
                                                items_de(objeto_ref, respuestas))
        return {r["pregunta_ref"]: (r["secuencia"], veredictos.get(r["pregunta_ref"])) for r in respuestas}

    def _objeto_en_vivo(self, asignacion: dict, ctx: Contexto, objeto_ref: str, *, obligatorio: bool) -> tuple[dict | None, dict | None]:
        """`(leída, objeto)`: la lección en vivo y la actividad. Con `obligatorio=False` la biblioteca cerrada no es error: `(None, None)`
        (guardar la respuesta nunca falla de cara al alumno, D-6)."""
        try:
            leida = self.s.contenido.leccion(fuente=asignacion["fuente_curso"], curso_ref=asignacion["curso_ref"],
                                             leccion_ref=asignacion["leccion_ref"], asignacion_id=asignacion["id"], dispositivo=ctx.huella,
                                             alumno_id=ctx.alumno_para_url, semilla=semilla_de(asignacion["id"]))
        except (FuenteNoDisponible, FuenteError):
            if obligatorio:
                raise
            return None, None
        objeto = next((o for o in leida["leccion"].get("objetos") or []
                       if o.get("objeto_ref") == objeto_ref and o.get("tipo") == "activity"), None)
        if objeto is None and obligatorio:
            raise NoEncontrado("La actividad ya no está en la lección.", objeto_ref=objeto_ref)
        return leida, objeto

    def _practica(self, uow: UnidadDeTrabajo, ctx: Contexto, practica_id: str) -> tuple[dict, dict, dict]:
        """`(práctica, tarea, asignación)` si la práctica es de este alumno; la de otra persona es 403 `no_es_el_titular`."""
        practica = uow.practicas.por_id(practica_id) if practica_id else None
        if practica is None:
            raise NoEncontrado("No existe esa práctica.", practica_id=practica_id)
        if practica["alumno_id"] != ctx.alumno_id:
            raise NoEsElTitular("La práctica es de otra persona: sólo su titular la lee o la escribe.", practica_id=practica_id)
        tarea = uow.tareas.por_id(practica["tarea_id"])
        return practica, tarea, uow.asignaciones.por_id(tarea["asignacion_id"])

    def _guardar_veredictos(self, uow: UnidadDeTrabajo, practica: dict, calificadas: dict) -> tuple[dict, list[str]]:
        """Pone los veredictos sobre las respuestas vigentes (no pisa una respuesta más nueva) y recalcula los aciertos."""
        respuestas, aplicados = practica_dom.aplicar_veredictos(list(practica["respuestas"]), calificadas)
        if aplicados:
            practica = uow.practicas.actualizar(practica["id"], **campos_de_resultado(respuestas))
        return practica, aplicados


class AbrirPractica(_CasoDePractica):
    """FUN-088 · `POST /lecciones/{id}/practica/`: `{dispositivo, objeto_ref?, nueva?}` → `{practica, objeto}`."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ANSWER_SUBMIT)
        nueva = bool(datos.get("nueva"))
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "", registrar=True)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            exigir_escritura(asignacion, ahora)
            objeto_ref = str(datos.get("objeto_ref") or (asignacion.get("practica") or {}).get("objeto_ref") or "")
            bloque = bloques_dom.bloque_de(asignacion["bloques"], objeto_ref) if objeto_ref else None
            if bloque is None or bloque["tipo"] != cat.PRACTICA:
                raise NoEncontrado("La lección no tiene esa práctica.", objeto_ref=objeto_ref or None)
            tarea = uow.tareas.obtener(asignacion["id"], ctx.alumno_id)
            previa = uow.practicas.en_curso(tarea["id"], objeto_ref) if tarea else None
            pendientes = practica_dom.por_calificar(previa["respuestas"]) if previa and not nueva else []
        leida, objeto = self._objeto_en_vivo(asignacion, ctx, objeto_ref, obligatorio=True)
        calificadas = self._calificar(asignacion, objeto_ref, pendientes)       # lo que quedó sin calificar se reintenta al reanudar

        with self.s.uow() as uow:
            asignacion = refrescar_estructura(uow, uow.asignaciones.por_id(asignacion["id"]), leida["curso"], leida["leccion"])
            tarea = obtener_o_crear(uow, asignacion, ctx.alumno_id, ahora)
            tarea = uow.tareas.actualizar(tarea["id"], **campos_de_actividad(asignacion, tarea, ahora, None))     # practicar es empezar
            total = len(objeto.get("preguntas") or [])
            en_curso = uow.practicas.en_curso(tarea["id"], objeto_ref)
            if en_curso and not nueva:
                practica = en_curso
                if practica["total_preguntas"] != total:
                    practica = uow.practicas.actualizar(practica["id"], total_preguntas=total)
                practica, _ = self._guardar_veredictos(uow, practica, calificadas)
                self._publicar(uow, "Practica", practica["id"], cat.EV_ACTIVIDAD_REANUDADA, {
                    "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id, "practica_id": practica["id"],
                    "numero": practica["numero"], "respondidas": len(practica["respuestas"])}, ahora)
                reanudada = True
            else:
                if en_curso:       # «Intentar nuevamente» con otra a medias: la anterior se cierra, no se pierde
                    _, tarea, _ = terminar_practica(uow, asignacion, tarea, en_curso, ahora=ahora)
                practica = uow.practicas.crear({
                    "id": nuevo_id(), "tarea_id": tarea["id"], "alumno_id": ctx.alumno_id, "objeto_ref": objeto_ref,
                    "objeto_rotulo": str(objeto.get("titulo") or ""), "numero": practica_dom.siguiente_numero(uow.practicas.de_tarea(tarea["id"], objeto_ref)),
                    "modo": cat.MODO_ESTUDIO, "estado": cat.EN_CURSO, "respuestas": [], "total_preguntas": total, "aciertos": 0,
                    "origen": cat.DIRECTO, "dispositivo_id": ctx.dispositivo_id, "iniciada_en": ahora})
                reanudada = False
            resumir_practicas(uow, asignacion, tarea)
            return {"practica": dto.practica_abierta(practica, asignacion.get("practica"), reanudada), "objeto": objeto}


class ResponderPractica(_CasoDePractica):
    """FUN-083 · `POST /practicas/{id}/respuestas/`: `{dispositivo, respuestas:[{pregunta_ref, respuesta, secuencia, capturada_en?}], terminar?}`
    → `{acuse, veredictos[], aceptadas[], duplicadas[], superadas[], rechazadas[], practica, resultado?, servidor_en}`."""

    def ejecutar(self, actor: Actor, practica_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ANSWER_SUBMIT)
        terminar = bool(datos.get("terminar"))
        limpias, rechazadas = practica_dom.normalizar_respuestas(datos.get("respuestas") if datos.get("respuestas") is not None else [])
        if not limpias and not rechazadas and not terminar:
            raise DatosInvalidos("`respuestas` debe traer al menos una respuesta (o `terminar: true`).")
        capturas = [r["capturada_en"] for r in limpias if r["capturada_en"]]
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "", registrar=True)
            practica, _, asignacion = self._practica(uow, ctx, practica_id)
            terminada = practica["estado"] == cat.TERMINADA
            if terminada and limpias:
                _, previo = practica_dom.fusionar(practica["respuestas"], [{**r, "veredicto": None} for r in limpias])
                if previo.aceptadas:
                    raise PracticaTerminada("La práctica ya terminó: abre otra («Intentar nuevamente») para seguir practicando.",
                                            practica_id=practica_id, numero=practica["numero"])
            if not terminada:
                exigir_escritura(asignacion, ahora, capturado_en=max(capturas) if capturas else None)
        # Fuera de la transacción: la forma de cada respuesta se valida contra la pregunta tal como la vio el alumno, y se califica.
        _, objeto = self._objeto_en_vivo(asignacion, ctx, practica["objeto_ref"], obligatorio=False)
        limpias, rechazadas = self._validar_formas(objeto, limpias, rechazadas)
        nuevas = [{**r, "recibida_en": ahora, "origen": cat.DIRECTO, "sesion_ref": ctx.sesion or ctx.huella, "veredicto": None} for r in limpias]
        if terminada:
            a_calificar: list[dict] = []
        else:
            _, previo = practica_dom.fusionar(practica["respuestas"], nuevas)
            aceptadas_previas = set(previo.aceptadas)
            # UNA sola llamada: lo pendiente de antes y lo nuevo que se acepta (la respuesta nueva de una pregunta sustituye a la vieja)
            a_calificar = practica_dom.por_calificar(practica["respuestas"]) + [r for r in nuevas if r["pregunta_ref"] in aceptadas_previas]
        calificadas = self._calificar(asignacion, practica["objeto_ref"], list({r["pregunta_ref"]: r for r in a_calificar}.values()))

        with self.s.uow() as uow:
            practica, tarea, asignacion = self._practica(uow, ctx, practica_id)
            if practica["estado"] == cat.TERMINADA:
                resultado_fusion, aceptadas, duplicadas, superadas = None, [], [r["pregunta_ref"] for r in limpias], []
            else:
                fusionadas, resultado_fusion = practica_dom.fusionar(practica["respuestas"], nuevas)
                aceptadas, duplicadas, superadas = resultado_fusion.aceptadas, resultado_fusion.duplicadas, resultado_fusion.superadas
                fusionadas, _ = practica_dom.aplicar_veredictos(fusionadas, calificadas)
                practica = uow.practicas.actualizar(practica["id"], **campos_de_resultado(fusionadas))
                for r in fusionadas:
                    if r["pregunta_ref"] in aceptadas:
                        self._publicar(uow, "Practica", practica["id"], cat.EV_RESPUESTA_REGISTRADA, {
                            "practica_id": practica["id"], "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id,
                            "pregunta_ref": r["pregunta_ref"], "secuencia": r["secuencia"], "modo": cat.MODO_ESTUDIO}, ahora)
                if aceptadas:
                    tarea = uow.tareas.actualizar(tarea["id"], **campos_de_actividad(asignacion, tarea, ahora, max(capturas) if capturas else None))
            resultado = None
            if terminar:
                practica, tarea, _ = terminar_practica(uow, asignacion, tarea, practica, ahora=ahora,
                                                       capturado_en=max(capturas) if capturas else None)
                resultado = practica_dom.resultado_de(practica["respuestas"], practica["total_preguntas"])
            por_ref = {str(r["pregunta_ref"]): r for r in practica["respuestas"]}
            veredictos = [v for v in (practica_dom.veredicto_publico(por_ref[ref]) for ref in calificadas if ref in por_ref) if v is not None]
            return {"acuse": True, "veredictos": veredictos, "aceptadas": aceptadas, "duplicadas": duplicadas, "superadas": superadas,
                    "rechazadas": rechazadas, "practica": dto.practica_resumen_corto(practica), "resultado": resultado, "servidor_en": ahora}

    @staticmethod
    def _validar_formas(objeto: dict | None, limpias: list[dict], rechazadas: list[dict]) -> tuple[list[dict], list[dict]]:
        """Con la actividad a la vista: la pregunta debe existir y la forma de la respuesta ser la de su tipo (ids, nunca posiciones).
        Sin ella (biblioteca cerrada) no se puede comprobar: se guarda y se califica después."""
        if objeto is None:
            return limpias, rechazadas
        aptas, rechazadas = [], list(rechazadas)
        for r in limpias:
            pregunta = practica_dom.pregunta_de(objeto, r["pregunta_ref"])
            if pregunta is None:
                rechazadas.append({"pregunta_ref": r["pregunta_ref"], "motivo": "la pregunta no está en la actividad"})
                continue
            try:
                aptas.append({**r, "respuesta": practica_dom.validar_forma(pregunta, r["respuesta"])})
            except DatosInvalidos as error:
                rechazadas.append({"pregunta_ref": r["pregunta_ref"], "motivo": error.detalle})
        return aptas, rechazadas


class TerminarPractica(_CasoDePractica):
    """FUN-088 · `POST /practicas/{id}/terminar/` → `{practica, resultado}` (con la misma forma que el acuse de las respuestas). Reintenta la
    calificación de lo que quedó pendiente, marca el bloque de la práctica como atendido y emite `estudio.practica.terminada.v1`. Idempotente."""

    def ejecutar(self, actor: Actor, practica_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ANSWER_SUBMIT)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "", registrar=True)
            practica, _, asignacion = self._practica(uow, ctx, practica_id)
            if practica["estado"] != cat.TERMINADA:
                exigir_escritura(asignacion, ahora)
        calificadas = self._calificar(asignacion, practica["objeto_ref"], practica_dom.por_calificar(practica["respuestas"]))

        with self.s.uow() as uow:
            practica, tarea, asignacion = self._practica(uow, ctx, practica_id)
            practica, _ = self._guardar_veredictos(uow, practica, calificadas)
            practica, tarea, _ = terminar_practica(uow, asignacion, tarea, practica, ahora=ahora)
            resultado = practica_dom.resultado_de(practica["respuestas"], practica["total_preguntas"])
            por_ref = {str(r["pregunta_ref"]): r for r in practica["respuestas"]}
            veredictos = [v for v in (practica_dom.veredicto_publico(por_ref[ref]) for ref in calificadas if ref in por_ref) if v is not None]
            return {"acuse": True, "veredictos": veredictos, "aceptadas": [], "duplicadas": [], "superadas": [], "rechazadas": [],
                    "practica": dto.practica_resumen_corto(practica), "resultado": resultado, "servidor_en": ahora}
