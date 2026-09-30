"""
StudySyncService · el trabajo que se hizo sin red y se integra sin duplicar ni exigir sesión (CAP-048, FUN-086, D-9, D-10, D-11,
BR-059, BR-060, BR-137, BR-138, TST-029, BR-074).

  Sincronizar             `POST /sync/`: hasta 200 eventos de la cola del aparato, procesados EN ORDEN de secuencia, cada uno en SU transacción (uno malo
                          no tumba a los demás). `UNIQUE(emisor_id, secuencia)`: reenviar devuelve `duplicado` con el mismo resultado y no duplica nada.
                          Sin sesión se autoriza por el aparato (registrado, activo, no bloqueado) y por el alumno que declara (existe y está
                          activo); ya no hace falta que el aparato sea suyo (D-11 revisada por D-15). Cada evento comprueba que la asignación le alcance.
  EstadoDeSincronizacion  `GET /sync/status/`: lo que el libro tiene de la instalación (synced · rejected · conflict) y lo que espera al profesor.
  DecidirPendiente        `POST /docente/asignaciones/{id}/decisiones/`: el profesor acepta o descarta lo que llegó fuera de la gracia (BR-074).

La política de plazo (D-9) decide sobre `ocurrido_en` (capturado, ya normalizado al reloj del nodo) y `recibido_en` (llegada): blando → siempre se
integra (con `fuera_de_plazo` si se capturó después de la fecha); endurecido → se integra, queda `pendiente_decision` o se rechaza (`politica_de_recepcion`).
Un evento `study.answer.submitted` abre o reanuda la práctica `(tarea, objeto_ref, intento_numero)` y fusiona la respuesta (INV-013); las respuestas
se califican DESPUÉS de integrar, en UNA llamada por actividad, y los veredictos vuelven en la respuesta del envío.

Lo que se decide dentro de una transacción y debe quedar escrito aunque el evento se rechace (el libro) se escribe en otra, después de deshacer el efecto.
"""
from __future__ import annotations

import logging

from ..dominio import asignacion as asignacion_dom
from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import plazo as plazo_dom
from ..dominio import practica as practica_dom
from ..dominio import sync as sync_dom
from ..dominio.errores import (
    DatosInvalidos,
    ErrorEstudio,
    FuenteError,
    FuenteNoDisponible,
    NoEncontrado,
    PracticaEnCurso,
    PracticaTerminada,
    SinPermiso,
)
from . import dto
from .asignaciones import _asignacion, _exigir_titular
from .base import Contexto, Servicios, _CasoDeUso, alcanza_al_alumno, nuevo_id, resolver_contexto
from .practica import campos_de_resultado, items_de
from .puertos import Actor, UnidadDeTrabajo
from .tareas import campos_de_actividad, completar, obtener_o_crear, registrar_bloques, resumir_practicas, terminar_practica

log = logging.getLogger(__name__)


# ============================================================================== efectos de cada evento

def _objeto_de(lecturas: dict[str, dict | None], asignacion_id: str, objeto_ref: str) -> dict | None:
    """La actividad tal como se leyó en vivo antes de procesar (None: la biblioteca no estaba o la actividad ya no existe)."""
    leida = lecturas.get(asignacion_id)
    if not leida:
        return None
    return next((o for o in leida["leccion"].get("objetos") or [] if o.get("objeto_ref") == objeto_ref and o.get("tipo") == "activity"), None)


def aplicar_evento(uow: UnidadDeTrabajo, *, alumno_id: str, dispositivo_id: str, emisor_id: str, asignacion: dict, tipo: str, carga: dict,
                   ocurrido_en: int, recibido_en: int, lecturas: dict[str, dict | None]) -> tuple[dict, str | None]:
    """El efecto de UN evento ya validado y aceptado por la política de plazo. Devuelve `(detalle, práctica tocada | None)`. Lanza el error del
    módulo (NoEncontrado, BloquesPendientes, PracticaTerminada…) si el evento no se puede integrar: quien llama deshace lo hecho y lo rechaza."""
    tarea = obtener_o_crear(uow, asignacion, alumno_id, recibido_en)
    if tipo == cat.T_BLOQUE_VISTO:
        tarea, aceptados, desconocidos = registrar_bloques(
            uow, asignacion, tarea, refs=carga["bloques_vistos"], bloque_actual=carga["bloque_actual"], posicion_seg=carga["posicion_seg"],
            ahora=recibido_en, capturado_en=ocurrido_en)
        return {"aceptados": aceptados, "desconocidos": desconocidos, "fuera_de_plazo": bool(tarea["fuera_de_plazo"])}, None

    if tipo == cat.T_LECCION_COMPLETADA:
        tarea, recien = completar(uow, asignacion, tarea, ahora=recibido_en, capturado_en=ocurrido_en, origen=cat.COLA)
        return {"estado": tarea["estado"], "recien_completada": recien, "fuera_de_plazo": bool(tarea["fuera_de_plazo"])}, None

    bloque = bloques_dom.bloque_de(asignacion["bloques"], carga["objeto_ref"])
    if bloque is None or bloque["tipo"] != cat.PRACTICA:
        raise NoEncontrado("La lección no tiene esa práctica.", objeto_ref=carga["objeto_ref"])
    practica = uow.practicas.obtener(tarea["id"], carga["objeto_ref"], carga["intento_numero"])

    if tipo == cat.T_PRACTICA_TERMINADA:
        if practica is None:
            raise NoEncontrado("No existe esa práctica: no hay respuestas de ese intento.", objeto_ref=carga["objeto_ref"],
                               intento_numero=carga["intento_numero"])
        practica, tarea, recien = terminar_practica(uow, asignacion, tarea, practica, ahora=recibido_en, capturado_en=ocurrido_en)
        return {"practica_id": practica["id"], "numero": practica["numero"], "recien_terminada": recien}, practica["id"]

    # T_RESPUESTA_ENVIADA: abre o reanuda la práctica y fusiona la respuesta (INV-013)
    objeto = _objeto_de(lecturas, asignacion["id"], carga["objeto_ref"])
    respuesta = carga["respuesta"]
    if objeto is not None:
        pregunta = practica_dom.pregunta_de(objeto, carga["pregunta_ref"])
        if pregunta is None:
            raise NoEncontrado("La pregunta no está en la actividad.", pregunta_ref=carga["pregunta_ref"])
        respuesta = practica_dom.validar_forma(pregunta, respuesta)
    if practica is None:
        en_curso = uow.practicas.en_curso(tarea["id"], carga["objeto_ref"])
        if en_curso is not None:
            raise PracticaEnCurso("Hay otra práctica de esa actividad en curso: cierra el intento anterior antes de abrir el siguiente.",
                                  numero_en_curso=en_curso["numero"], intento_numero=carga["intento_numero"])
        principal = asignacion.get("practica") or {}
        total = len(objeto.get("preguntas") or []) if objeto is not None else (
            int(principal.get("total_preguntas") or 0) if principal.get("objeto_ref") == carga["objeto_ref"] else 0)
        practica = uow.practicas.crear({
            "id": nuevo_id(), "tarea_id": tarea["id"], "alumno_id": alumno_id, "objeto_ref": carga["objeto_ref"],
            "objeto_rotulo": str((objeto or {}).get("titulo") or principal.get("titulo") or ""), "numero": carga["intento_numero"],
            "modo": cat.MODO_ESTUDIO, "estado": cat.EN_CURSO, "respuestas": [], "total_preguntas": total, "aciertos": 0,
            "origen": cat.COLA, "dispositivo_id": dispositivo_id, "iniciada_en": min(ocurrido_en, recibido_en)})
    nueva = {"pregunta_ref": carga["pregunta_ref"], "respuesta": respuesta, "secuencia": carga["secuencia_respuesta"],
             "recibida_en": recibido_en, "capturada_en": ocurrido_en, "origen": cat.COLA, "sesion_ref": emisor_id, "veredicto": None}
    fusionadas, resultado = practica_dom.fusionar(practica["respuestas"], [nueva])
    if practica["estado"] == cat.TERMINADA and resultado.aceptadas:
        raise PracticaTerminada("La práctica ya terminó: esa respuesta llegó tarde para ese intento.", practica_id=practica["id"],
                                numero=practica["numero"])
    if resultado.aceptadas:
        practica = uow.practicas.actualizar(practica["id"], **campos_de_resultado(fusionadas))
        uow.outbox.publicar("Practica", practica["id"], cat.EV_RESPUESTA_REGISTRADA, {
            "practica_id": practica["id"], "asignacion_id": asignacion["id"], "alumno_id": alumno_id,
            "pregunta_ref": carga["pregunta_ref"], "secuencia": carga["secuencia_respuesta"], "modo": cat.MODO_ESTUDIO,
            "instante": recibido_en})
        tarea = uow.tareas.actualizar(tarea["id"], **campos_de_actividad(asignacion, tarea, recibido_en, ocurrido_en))
    resumir_practicas(uow, asignacion, tarea)
    return {"practica_id": practica["id"], "numero": practica["numero"], "pregunta_ref": carga["pregunta_ref"],
            "aceptada": bool(resultado.aceptadas), "duplicada": bool(resultado.duplicadas), "superada": bool(resultado.superadas)}, practica["id"]


# ================================================================================== calificar lo integrado

def calificar_practicas(servicios: Servicios, practicas: dict[str, str]) -> list[dict]:
    """Después de integrar: califica lo que las prácticas tocadas tienen sin veredicto (lo nuevo y lo que quedó pendiente de antes), en UNA
    llamada por actividad, y guarda los veredictos. Devuelve `veredictos[{asignacion_id, objeto_ref, numero, pregunta_ref, veredicto}]`.
    Sin biblioteca no califica nada y no falla: quedan pendientes para la siguiente lectura o sincronización (D-6)."""
    if not practicas:
        return []
    grupos: dict[tuple[str, str], dict] = {}
    with servicios.uow() as uow:
        for practica_id, asignacion_id in practicas.items():
            practica = uow.practicas.por_id(practica_id)
            pendientes = practica_dom.por_calificar(practica["respuestas"]) if practica else []
            if not pendientes:
                continue
            grupo = grupos.setdefault((asignacion_id, practica["objeto_ref"]),
                                      {"asignacion": uow.asignaciones.por_id(asignacion_id), "practicas": {}})
            grupo["practicas"][practica_id] = pendientes
    salida: list[dict] = []
    for (asignacion_id, objeto_ref), grupo in grupos.items():
        asignacion = grupo["asignacion"]
        respuestas = [r for pendientes in grupo["practicas"].values() for r in pendientes]
        unicas = list({r["pregunta_ref"]: r for r in respuestas}.values())
        veredictos = servicios.contenido.calificar(asignacion["fuente_curso"], asignacion["curso_ref"], asignacion["curso_version"],
                                                   items_de(objeto_ref, unicas))
        if not any(v is not None for v in veredictos.values()):
            continue
        with servicios.uow() as uow:
            for practica_id, pendientes in grupo["practicas"].items():
                practica = uow.practicas.por_id(practica_id)
                calificadas = {r["pregunta_ref"]: (r["secuencia"], veredictos.get(r["pregunta_ref"])) for r in pendientes}
                respuestas_nuevas, aplicados = practica_dom.aplicar_veredictos(list(practica["respuestas"]), calificadas)
                if not aplicados:
                    continue
                practica = uow.practicas.actualizar(practica_id, **campos_de_resultado(respuestas_nuevas))
                tarea = uow.tareas.por_id(practica["tarea_id"])
                resumir_practicas(uow, uow.asignaciones.por_id(asignacion_id), tarea)
                por_ref = {str(r["pregunta_ref"]): r for r in practica["respuestas"]}
                for ref in aplicados:
                    salida.append({"asignacion_id": asignacion_id, "objeto_ref": objeto_ref, "numero": practica["numero"],
                                   "pregunta_ref": ref, "veredicto": practica_dom.veredicto_publico(por_ref[ref])})
    return salida


# ======================================================================================== sincronizar

class Sincronizar(_CasoDeUso):
    """`POST /sync/`: `{dispositivo, emisor_id, eventos:[{secuencia, tipo, ocurrido_en, ocurrido_en_tableta?, carga}], alumno_id?}`
    → `{acuse, servidor_en, resultados[{secuencia, estado, motivo, detalle}], resumen, asignaciones[{id, tarea}], veredictos[]}`."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        if actor.autenticado:       # con sesión, el rol debe poder avanzar, completar y practicar: el profesor y la administración no
            self.s.autorizacion.exigir(actor, cat.P_LESSON_COMPLETE)
            self.s.autorizacion.exigir(actor, cat.P_ANSWER_SUBMIT)
        emisor_id = sync_dom.normalizar_emisor(datos.get("emisor_id"))
        crudos = sync_dom.validar_envio(datos.get("eventos"))
        recibido_en = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = contexto_de_sync(uow, actor, datos.get("dispositivo"), datos.get("alumno_id") or "", recibido_en)

        resultados: list[dict] = []
        validos: list[dict] = []
        for bruto in crudos:
            try:
                validos.append(sync_dom.normalizar_evento(bruto))
            except DatosInvalidos as error:      # sin secuencia válida no se puede ni registrar: se rechaza y se dice por qué
                secuencia = bruto.get("secuencia") if isinstance(bruto, dict) else None
                resultados.append({"secuencia": secuencia if isinstance(secuencia, int) and not isinstance(secuencia, bool) else None,
                                   "estado": cat.RECHAZADO, "motivo": cat.MOTIVO_EVENTO_INVALIDO, "detalle": {"detail": error.detalle}})
        validos = sync_dom.ordenar(validos)
        lecturas = self._leer_actividades(ctx, validos)

        practicas: dict[str, str] = {}
        tocadas: dict[str, None] = {}
        for ev in validos:
            resultado = self._integrar(ctx, emisor_id, ev, recibido_en, lecturas, practicas, tocadas)
            if resultado is not None:
                resultados.append(resultado)
        veredictos = calificar_practicas(self.s, practicas)

        resumen = sync_dom.contar(resultados)
        with self.s.uow() as uow:
            asignaciones = []
            for asignacion_id in tocadas:
                asignacion = uow.asignaciones.por_id(asignacion_id)
                if asignacion is not None and alcanza_al_alumno(uow, asignacion, ctx.alumno_id):
                    asignaciones.append({"id": asignacion_id, "tarea": dto.tarea(asignacion, uow.tareas.obtener(asignacion_id, ctx.alumno_id),
                                                                                  self.s.reloj.ahora_ms())})
            if validos:
                self._publicar(uow, "Sincronizacion", emisor_id, cat.EV_TRABAJO_INTEGRADO, {
                    "alumno_id": ctx.alumno_id, "dispositivo_id": ctx.dispositivo_id, "emisor_id": emisor_id, **{
                        k: resumen[k] for k in ("integrados", "duplicados", "rechazados", "pendientes_decision")},
                    "desde_secuencia": validos[0]["secuencia"], "hasta_secuencia": validos[-1]["secuencia"]}, recibido_en)
        return {"acuse": True, "servidor_en": self.s.reloj.ahora_ms(), "resultados": resultados, "resumen": resumen,
                "asignaciones": asignaciones, "veredictos": veredictos}

    # ------------------------------------------------------------------------------ lo que se lee antes
    def _leer_actividades(self, ctx: Contexto, eventos: list[dict]) -> dict[str, dict | None]:
        """Para validar la forma de las respuestas hace falta ver la actividad: se lee UNA vez por asignación, antes de procesar y fuera de las
        transacciones. Sin biblioteca no se puede validar y se guarda igual (se califica después)."""
        ids = list(dict.fromkeys(
            str(e["carga"].get("asignacion_id") or "") for e in eventos
            if e["tipo"] == cat.T_RESPUESTA_ENVIADA and isinstance(e["carga"], dict)))
        if not ids:
            return {}
        with self.s.uow() as uow:
            asignaciones = {i: uow.asignaciones.por_id(i) for i in ids if i}
            asignaciones = {i: a for i, a in asignaciones.items() if a is not None and alcanza_al_alumno(uow, a, ctx.alumno_id)}
        lecturas: dict[str, dict | None] = {}
        for i, a in asignaciones.items():
            try:
                lecturas[i] = self.s.contenido.leccion(fuente=a["fuente_curso"], curso_ref=a["curso_ref"], leccion_ref=a["leccion_ref"],
                                                       asignacion_id=a["id"], dispositivo=ctx.huella, alumno_id=ctx.alumno_para_url,
                                                       semilla=f"estudio|{a['id']}")
            except (FuenteNoDisponible, FuenteError, NoEncontrado):
                lecturas[i] = None
        return lecturas

    # ---------------------------------------------------------------------------- un evento, su transacción
    def _integrar(self, ctx: Contexto, emisor_id: str, ev: dict, recibido_en: int, lecturas: dict, practicas: dict, tocadas: dict) -> dict | None:
        try:
            with self.s.uow() as uow:
                previo = uow.sincronizaciones.por_emisor_y_secuencia(emisor_id, ev["secuencia"])
                if previo is not None:
                    return self._duplicado(ctx, previo, tocadas)
                return self._procesar(uow, ctx, emisor_id, ev, recibido_en, lecturas, practicas, tocadas)
        except ErrorEstudio as error:
            return self._rechazar(ctx, emisor_id, ev, recibido_en, error, tocadas)
        except Exception:      # noqa: BLE001 — un fallo de UN evento no tumba a los demás; sin acuse, la cola lo reenvía
            log.exception("Modo estudio · falló la integración del evento %s de %s", ev["secuencia"], emisor_id)
            with self.s.uow() as uow:      # una carrera con otro envío igual: si ya está en el libro, es un duplicado
                previo = uow.sincronizaciones.por_emisor_y_secuencia(emisor_id, ev["secuencia"])
                return self._duplicado(ctx, previo, tocadas) if previo is not None else None

    def _duplicado(self, ctx: Contexto, previo: dict, tocadas: dict) -> dict:
        """El reenvío devuelve `duplicado` con el mismo resultado guardado y no toca nada (BR-060). Un evento de OTRA persona con la misma secuencia
        no se revela: se rechaza."""
        if previo["alumno_id"] != ctx.alumno_id:
            return {"secuencia": previo["secuencia"], "estado": cat.RECHAZADO, "motivo": "emisor_ajeno",
                    "detalle": {"detail": "Esa secuencia ya la usó otra persona con ese emisor."}}
        if previo["asignacion_id"]:
            tocadas[previo["asignacion_id"]] = None
        guardado = previo["resultado"] or {}
        return {"secuencia": previo["secuencia"], "estado": cat.DUPLICADO, "motivo": previo["motivo"],
                "detalle": {**(guardado.get("detalle") or {}), "estado_original": previo["estado"]}}

    def _procesar(self, uow: UnidadDeTrabajo, ctx: Contexto, emisor_id: str, ev: dict, recibido_en: int, lecturas: dict, practicas: dict,
                  tocadas: dict) -> dict:
        carga = sync_dom.validar_carga(ev["tipo"], ev["carga"])
        tocadas[carga["asignacion_id"]] = None
        asignacion = uow.asignaciones.por_id(carga["asignacion_id"])
        if asignacion is None or not alcanza_al_alumno(uow, asignacion, ctx.alumno_id):
            raise NoEncontrado("No existe esa asignación para este alumno.", asignacion_id=carga["asignacion_id"])
        # Lo capturado no puede ser posterior a la llegada: el reloj del nodo manda (BR-062).
        ocurrido_en = min(ev["ocurrido_en"] if ev["ocurrido_en"] is not None else recibido_en, recibido_en)
        base = {"emisor_id": emisor_id, "secuencia": ev["secuencia"], "alumno_id": ctx.alumno_id, "dispositivo_id": ctx.dispositivo_id,
                "tipo": ev["tipo"], "asignacion_id": asignacion["id"], "ocurrido_en": ocurrido_en,
                "ocurrido_en_tableta": ev["ocurrido_en_tableta"], "recibido_en": recibido_en}
        decision, motivo = plazo_dom.politica_de_recepcion(
            fecha_limite=asignacion["fecha_limite"], plazo=asignacion["plazo"], gracia_ms=asignacion["gracia_ms"],
            cerrada_en=asignacion["cerrada_en"], capturado_en=ocurrido_en, recibido_en=recibido_en)
        if decision == plazo_dom.RECHAZAR:
            return self._libro(uow, base, cat.RECHAZADO, motivo, {"detail": "Se capturó después del cierre de la asignación."}, carga)
        if decision == plazo_dom.DECIDE_EL_PROFESOR:      # BR-074: no se descarta en silencio; se guarda la carga completa hasta que decida
            return self._libro(uow, base, cat.PENDIENTE_DECISION, motivo, {"detail": "Llegó fuera de la gracia: decide el profesor."}, carga,
                               conservar_carga=True)
        detalle, practica_id = aplicar_evento(uow, alumno_id=ctx.alumno_id, dispositivo_id=ctx.dispositivo_id, emisor_id=emisor_id,
                                              asignacion=asignacion, tipo=ev["tipo"], carga=carga, ocurrido_en=ocurrido_en,
                                              recibido_en=recibido_en, lecturas=lecturas)
        if practica_id:
            practicas[practica_id] = asignacion["id"]
        return self._libro(uow, base, cat.INTEGRADO, "", detalle, carga)

    def _libro(self, uow: UnidadDeTrabajo, base: dict, estado: str, motivo: str, detalle: dict, carga: dict, *, conservar_carga: bool = False) -> dict:
        """Escribe el evento en el libro (`UNIQUE(emisor_id, secuencia)`) y devuelve lo que se le responde al aparato."""
        uow.sincronizaciones.crear({**base, "estado": estado, "motivo": motivo,
                                    "carga": carga if conservar_carga else sync_dom.resumen_de_carga(carga),
                                    "resultado": {"estado": estado, "motivo": motivo, "detalle": detalle}})
        return {"secuencia": base["secuencia"], "estado": estado, "motivo": motivo, "detalle": detalle}

    def _rechazar(self, ctx: Contexto, emisor_id: str, ev: dict, recibido_en: int, error: ErrorEstudio, tocadas: dict) -> dict:
        """El efecto se deshizo con la transacción; el rechazo queda en el libro (otra transacción) para que el reenvío diga lo mismo."""
        asignacion_id = str(ev["carga"].get("asignacion_id") or "") if isinstance(ev["carga"], dict) else ""
        ocurrido_en = min(ev["ocurrido_en"] if ev["ocurrido_en"] is not None else recibido_en, recibido_en)
        with self.s.uow() as uow:
            previo = uow.sincronizaciones.por_emisor_y_secuencia(emisor_id, ev["secuencia"])
            if previo is not None:
                return self._duplicado(ctx, previo, tocadas)
            base = {"emisor_id": emisor_id, "secuencia": ev["secuencia"], "alumno_id": ctx.alumno_id, "dispositivo_id": ctx.dispositivo_id,
                    "tipo": ev["tipo"][:40], "asignacion_id": asignacion_id[:36], "ocurrido_en": ocurrido_en,
                    "ocurrido_en_tableta": ev["ocurrido_en_tableta"], "recibido_en": recibido_en}
            return self._libro(uow, base, cat.RECHAZADO, error.codigo, {"detail": error.detalle, **error.extra}, ev["carga"])


def contexto_de_sync(uow: UnidadDeTrabajo, actor: Actor, huella: str, declarado: str, ahora: int) -> Contexto:
    """D-11 (revisada por D-15): sin sesión (BR-137) se autoriza por el APARATO —registrado, activo y no bloqueado— y por la persona que declara
    (`alumno_id`: debe existir y estar activa); YA NO hace falta que el aparato sea suyo, ni siquiera que esté asignado. Sin `alumno_id`, en un
    aparato asignado sincroniza su dueño (compatibilidad) y en uno compartido es 400 `falta_alumno`. Con sesión (MOD-001) la persona es la del
    token. Cada evento comprueba después que la asignación le alcance."""
    declarado = str(declarado or "").strip() or (actor.id if not actor.autenticado else "")
    ctx = resolver_contexto(uow, actor, huella, ahora=ahora, declarado=declarado)
    if not actor.autenticado and ctx.dispositivo is None:
        raise SinPermiso("Sincronizar sin iniciar sesión exige un aparato registrado en el nodo (D-11).", motivo=cat.MOTIVO_DISPOSITIVO_DESCONOCIDO)
    return ctx


class EstadoDeSincronizacion(_CasoDeUso):
    """`GET /sync/status/?dispositivo=&emisor_id=` → `{emisor_id, ultima_secuencia, conteos{synced, rejected, conflict}, pendientes_decision[]}`. Es
    lo que el libro tiene de ESA persona en esa instalación."""

    def ejecutar(self, actor: Actor, huella: str, emisor_id: str, alumno_id: str = "") -> dict:
        if actor.autenticado:
            self.s.autorizacion.exigir(actor, cat.P_ANSWER_SUBMIT)
        emisor_id = sync_dom.normalizar_emisor(emisor_id)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = contexto_de_sync(uow, actor, huella, alumno_id, ahora)
            filas = uow.sincronizaciones.del_emisor(emisor_id, ctx.alumno_id)
            return {
                "emisor_id": emisor_id, "ultima_secuencia": max((f["secuencia"] for f in filas), default=0),
                "conteos": sync_dom.conteos_del_aparato(filas),
                "pendientes_decision": [{"secuencia": f["secuencia"], "tipo": f["tipo"], "asignacion_id": f["asignacion_id"], "motivo": f["motivo"]}
                                        for f in filas if f["estado"] == cat.PENDIENTE_DECISION],
            }


class DecidirPendiente(_CasoDeUso):
    """BR-074 · `POST /docente/asignaciones/{id}/decisiones/` (`study.assignment.review`): `{alumno_id, secuencia, emisor_id?, decision, actor?}`.
    ACEPTAR aplica el evento guardado (se capturó a tiempo, llegó tarde); DESCARTAR lo deja rechazado. Nunca se descarta en silencio: queda
    constancia de quién decidió."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_REVIEW)
        decision = asignacion_dom.validar_decision(datos)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = _asignacion(uow, asignacion_id)
            _exigir_titular(uow, actor, asignacion)
            filas = uow.sincronizaciones.por_decision(asignacion_id, decision["alumno_id"], decision["secuencia"], decision["emisor_id"])
            if not filas:
                raise NoEncontrado("No hay ningún envío de ese alumno con esa secuencia en esta asignación.", secuencia=decision["secuencia"])
            if len(filas) > 1:
                raise DatosInvalidos("Hay envíos con esa secuencia de más de una instalación: indica emisor_id.", secuencia=decision["secuencia"])
            fila = filas[0]
            if fila["estado"] != cat.PENDIENTE_DECISION:
                raise DatosInvalidos("Sólo se decide sobre un envío pendiente de decisión.", estado=fila["estado"], secuencia=fila["secuencia"])
        lecturas = self._leer_actividad(asignacion, fila)

        practicas: dict[str, str] = {}
        estado, motivo, detalle = cat.RECHAZADO, cat.MOTIVO_DESCARTADO_POR_DOCENTE, {}
        try:
            with self.s.uow() as uow:
                if decision["decision"] == cat.DECISION_ACEPTAR:
                    detalle, practica_id = aplicar_evento(
                        uow, alumno_id=fila["alumno_id"], dispositivo_id=fila["dispositivo_id"], emisor_id=fila["emisor_id"],
                        asignacion=asignacion, tipo=fila["tipo"], carga=fila["carga"], ocurrido_en=fila["ocurrido_en"], recibido_en=ahora,
                        lecturas=lecturas)
                    if practica_id:
                        practicas[practica_id] = asignacion["id"]
                    estado, motivo = cat.INTEGRADO, cat.MOTIVO_ACEPTADO_POR_DOCENTE
                self._cerrar(uow, actor, fila, decision["decision"], estado, motivo, detalle, ahora)
        except ErrorEstudio as error:      # aceptar no fue posible (p. ej. ya no hay bloques pendientes que cumplir): queda rechazado, con su causa
            estado, motivo, detalle = cat.RECHAZADO, error.codigo, {"detail": error.detalle, **error.extra}
            with self.s.uow() as uow:
                self._cerrar(uow, actor, fila, decision["decision"], estado, motivo, detalle, ahora)
        calificar_practicas(self.s, practicas)
        return {"asignacion_id": asignacion_id, "alumno_id": fila["alumno_id"], "secuencia": fila["secuencia"], "emisor_id": fila["emisor_id"],
                "decision": decision["decision"], "estado": estado, "motivo": motivo, "decidido_por": actor.id, "decidido_en": ahora}

    def _leer_actividad(self, asignacion: dict, fila: dict) -> dict[str, dict | None]:
        """Sólo una respuesta necesita ver la actividad (para validar su forma). Sin biblioteca, se aplica igual y se califica después."""
        if fila["tipo"] != cat.T_RESPUESTA_ENVIADA:
            return {}
        try:
            return {asignacion["id"]: self.s.contenido.leccion(
                fuente=asignacion["fuente_curso"], curso_ref=asignacion["curso_ref"], leccion_ref=asignacion["leccion_ref"],
                asignacion_id=asignacion["id"], dispositivo="", alumno_id=fila["alumno_id"], semilla=f"estudio|{asignacion['id']}")}
        except (FuenteNoDisponible, FuenteError, NoEncontrado):
            return {}

    def _cerrar(self, uow: UnidadDeTrabajo, actor: Actor, fila: dict, decision: str, estado: str, motivo: str, detalle: dict, ahora: int) -> None:
        uow.sincronizaciones.actualizar(fila["id"], estado=estado, motivo=motivo, carga=sync_dom.resumen_de_carga(fila["carga"]),
                                        resultado={"estado": estado, "motivo": motivo, "detalle": detalle, "decidido_por": actor.id,
                                                   "decidido_en": ahora})
        uow.auditoria.registrar(actor.id, f"estudio.envio.{decision}", "m08_sincronizacion", str(fila["id"]),
                                anterior={"estado": cat.PENDIENTE_DECISION}, nuevo={"estado": estado, "motivo": motivo,
                                                                                 "secuencia": fila["secuencia"], "alumno_id": fila["alumno_id"]})
        if estado == cat.INTEGRADO:
            self._publicar(uow, "Sincronizacion", fila["emisor_id"], cat.EV_TRABAJO_INTEGRADO, {
                "alumno_id": fila["alumno_id"], "dispositivo_id": fila["dispositivo_id"], "emisor_id": fila["emisor_id"], "integrados": 1,
                "duplicados": 0, "rechazados": 0, "pendientes_decision": 0, "desde_secuencia": fila["secuencia"],
                "hasta_secuencia": fila["secuencia"]}, ahora)
