"""
La actividad lanzada en clase, vista desde la tableta y desde el profesor (007-05, 007-06, 007-08).

  EnviarRespuestas     la tableta guarda respuestas (una a una, idempotente por secuencia) y, si quiere, entrega el
                       intento. Sirve igual para lo enviado en línea que para lo que sale de la cola local después de
                       una desconexión o del cierre de la clase (BR-052, DEC-019).
  ResultadosActividad  el avance vivo por alumno, los rezagados y el panel agregado que ve el profesor (CAP-043)
  DecidirEnvio         lo que llegó fuera de la ventana de gracia queda a decisión del profesor: nunca se descarta en silencio

Reglas: BR-062 (sólo el reloj del nodo decide), INV-013 (una respuesta por pregunta, sesión y secuencia), BR-071
(cada respuesta se guarda de forma independiente), DEC-003 (escala interna 0-100). El aula NO tiene la clave de las
preguntas: la compara la biblioteca (`fuente.evaluar_lote`) y si no está disponible la respuesta se guarda igual y
queda «sin calificar» — guardar nunca falla de cara al alumno (UXR-004).
"""
from __future__ import annotations

from ..dominio import actividad as act
from ..dominio import respuestas as resp
from ..dominio import sesion as dom
from ..dominio.errores import (
    CapacidadAusente,
    DatosInvalidos,
    DistribucionCerrada,
    FuenteNoDisponible,
    IntentoEntregado,
    IntentosAgotados,
    NoEncontrado,
    ParticipanteExpulsado,
    SinPermiso,
)
from .casos_uso import _CasoDeSesion, _id
from .puertos import Actor, UnidadDeTrabajo

MAX_RESPUESTAS_POR_ENVIO = 200


def _entera(valor) -> int | None:
    try:
        return int(valor) if valor not in (None, "", False) else None
    except (TypeError, ValueError):
        return None


class _Actividad(_CasoDeSesion):
    def _distribucion_de_actividad(self, uow: UnidadDeTrabajo, sesion_id: str, distribucion_id: str) -> dict:
        distribucion = uow.sesiones.distribucion(distribucion_id)
        if not distribucion or distribucion["sesion_id"] != sesion_id:
            raise NoEncontrado("No existe esa distribución en esta sesión.", distribucion_id=distribucion_id)
        if distribucion["clase"] != dom.ACTIVIDAD:
            raise DatosInvalidos("Sólo las actividades se responden; un recurso se abre.", distribucion_id=distribucion_id)
        return distribucion

    def _calificar(self, sesion: dict, distribucion: dict, nuevas: list[dict]) -> dict[str, dict | None]:
        """El veredicto de cada respuesta nueva, comparada donde vive la clave (`/v2/evaluate`). Si la fuente no puede
        (ejemplo, biblioteca cerrada, versión archivada) la respuesta queda sin calificar: None."""
        sin_nota = {r["pregunta_ref"]: None for r in nuevas}
        if not nuevas or not distribucion["objeto_ref"]:
            return {}
        try:
            fuente = self.s.fuente(sesion["fuente_curso"] or None, distribucion["curso_ref"])
        except Exception:   # noqa: BLE001 — sin fuente no hay nota, pero la respuesta se guarda
            return sin_nota
        items = [{"objectId": distribucion["objeto_ref"], "questionId": r["pregunta_ref"], "response": dict(r["respuesta"])} for r in nuevas]
        try:
            crudos = fuente.evaluar_lote(distribucion["curso_ref"], sesion["curso_version"], items)
            por_pregunta = {str(c.get("questionId") or ""): c for c in crudos}
            return {r["pregunta_ref"]: resp.veredicto(por_pregunta.get(r["pregunta_ref"], crudos[i] if i < len(crudos) else {}),
                                                      r["pregunta_ref"]) for i, r in enumerate(nuevas)}
        except (FuenteNoDisponible, CapacidadAusente):
            return sin_nota                     # la fuente no está: probar una por una sólo sumaría esperas
        except Exception:   # noqa: BLE001
            pass
        # Una respuesta mal formada no debe dejar sin nota a las demás: se prueban una por una (con tope).
        veredictos = dict(sin_nota)
        for r in nuevas[:20]:
            try:
                crudo = fuente.evaluar(distribucion["curso_ref"], sesion["curso_version"], distribucion["objeto_ref"],
                                       r["pregunta_ref"], dict(r["respuesta"]))
                veredictos[r["pregunta_ref"]] = resp.veredicto(crudo, r["pregunta_ref"])
            except Exception:   # noqa: BLE001
                veredictos[r["pregunta_ref"]] = None
        return veredictos


class EnviarRespuestas(_Actividad):
    """`datos`: {respuestas: [{pregunta_ref, respuesta, secuencia, capturada_en?, capturada_en_tableta?}], entregar?, origen?}.

    `intento_numero` (opcional pero recomendado) es el número de intento que la tableta cree que está respondiendo: así un
    reenvío de lo ya entregado se acusa sin abrir un intento nuevo, y el primer envío de un intento nuevo lo crea.

    `capturada_en` es la hora en que la tableta capturó la respuesta YA NORMALIZADA al reloj del nodo con el desfase que
    aprendió de `servidor_en`; la hora cruda del aparato (`capturada_en_tableta`) sólo se conserva como dato adicional
    (AC-072). Sin ella se toma la de recepción."""

    def _calificar_antes(self, sesion_id: str, distribucion_id: str, limpias: list[dict]) -> dict:
        """`{(pregunta_ref, secuencia): (respuesta, veredicto)}` de lo que llega, calculado SIN el turno de escritura de la base.

        Lo único que necesita es leer la sesión y la distribución (sin transacción) y preguntarle a la fuente: no depende de lo que ya haya guardado el intento.
        Dentro de la transacción se reutiliza sólo si la respuesta que quedó aceptada es EXACTAMENTE la que se calificó; lo demás se califica allí como siempre.
        Es una ayuda: ante cualquier fallo devuelve vacío y todo sigue como antes (más lento, igual de correcto)."""
        if self.s.uow_lectura is None or not limpias:
            return {}
        try:
            with self.s.uow_lectura() as uow:
                sesion = self._sesion(uow, sesion_id)
                distribucion = self._distribucion_de_actividad(uow, sesion_id, distribucion_id)
            veredictos = self._calificar(sesion, distribucion, [dict(r, veredicto=None) for r in limpias])
            return {(r["pregunta_ref"], r["secuencia"]): (r["respuesta"], veredictos[r["pregunta_ref"]]) for r in limpias if r["pregunta_ref"] in veredictos}
        except Exception:   # noqa: BLE001
            return {}

    def ejecutar(self, sesion_id: str, distribucion_id: str, participante_id: str, datos: dict,
                 persona_autenticada: str | None = None) -> dict:
        entrada = datos.get("respuestas")
        entregar = bool(datos.get("entregar"))
        if entrada is None:
            entrada = []
        if not isinstance(entrada, list) or (not entrada and not entregar):
            raise DatosInvalidos("`respuestas` debe ser una lista con al menos una respuesta (o `entregar: true`).")
        if len(entrada) > MAX_RESPUESTAS_POR_ENVIO:
            raise DatosInvalidos(f"Un envío admite hasta {MAX_RESPUESTAS_POR_ENVIO} respuestas.", respuestas=len(entrada))
        origen = str(datos.get("origen") or "directo")
        if origen not in ("directo", "cola"):
            raise DatosInvalidos("`origen` es «directo» o «cola».")
        limpias: list[dict] = []
        rechazadas: list[dict] = []
        for r in entrada:
            if not isinstance(r, dict) or not str(r.get("pregunta_ref") or ""):
                rechazadas.append({"pregunta_ref": "", "motivo": "falta pregunta_ref"})
                continue
            if not isinstance(r.get("respuesta"), dict) or not r["respuesta"]:
                rechazadas.append({"pregunta_ref": str(r["pregunta_ref"]), "motivo": "la respuesta debe ser un objeto no vacío"})
                continue
            secuencia = _entera(r.get("secuencia")) or 0
            if secuencia < 1:
                rechazadas.append({"pregunta_ref": str(r["pregunta_ref"]), "motivo": "la secuencia debe ser un entero ≥ 1"})
                continue
            limpias.append({"pregunta_ref": str(r["pregunta_ref"]), "respuesta": dict(r["respuesta"]), "secuencia": secuencia,
                            "capturada_en": _entera(r.get("capturada_en")), "capturada_en_tableta": _entera(r.get("capturada_en_tableta"))})

        ahora = self.s.reloj.ahora_ms()
        # La calificación va a AVACOM Contenido (`/v2/evaluate/batch`, ~50 ms o más). Hecha DENTRO de la transacción retenía el turno de escritura de SQLite
        # durante todo el viaje: con 35 tabletas entregando a la vez cada respuesta esperaba a las demás (p95 de 5 s, hasta 7 s: prueba del 2026-10-08).
        previos = self._calificar_antes(sesion_id, distribucion_id, limpias)
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            distribucion = self._distribucion_de_actividad(uow, sesion_id, distribucion_id)
            participante = self._participante(uow, sesion, participante_id)
            self._persona_propia(persona_autenticada, participante)
            if participante["estado"] in (dom.EXPULSADO, dom.RECHAZADO):
                raise ParticipanteExpulsado(participante_id=participante_id, estado=participante["estado"])
            if not any(e["participante_id"] == participante_id for e in distribucion["entregas"]["detalle"]):
                raise SinPermiso("Esta actividad no se lanzó a este participante.", distribucion_id=distribucion_id)

            # ---- ¿qué se hace con lo que llega? (BR-052, DEC-019)
            cerrada_en = distribucion["cerrada_en"]
            capturas = [r["capturada_en"] for r in limpias if r["capturada_en"]]
            politica = act.politica_de_recepcion(cerrada_en=cerrada_en, capturada_en=max(capturas) if capturas else None,
                                                 recibida_en=ahora, gracia_ms=self.s.config.gracia_entrega_ms)
            if politica == act.RECHAZAR:
                raise DistribucionCerrada("La actividad ya se cerró y esto se capturó después del cierre.", cerrada_en=cerrada_en)

            propios = uow.sesiones.intentos(distribucion_id, participante_id)
            en_curso = next((i for i in propios if i["estado"] == dom.EN_CURSO), None)
            por_decidir = next((i for i in propios if i["estado"] == dom.PENDIENTE_DECISION), None)
            del_cierre = next((i for i in propios if i["estado"] == dom.INTENTO_ENTREGADO and i["origen_envio"] == "cierre"), None)
            tarde = cerrada_en is not None
            numero = _entera(datos.get("intento_numero"))
            objetivo = next((i for i in propios if i["numero"] == numero), None) if numero else None
            if numero and objetivo is None and numero != len(propios) + 1:
                raise DatosInvalidos("El número de intento debe ser el siguiente al último.", intento_numero=numero, siguiente=len(propios) + 1)

            def crear(estado: str, recuperado: bool):
                return uow.sesiones.crear_intento({
                    "id": _id(), "distribucion_id": distribucion_id, "participante_id": participante_id,
                    "persona_id": participante["persona_id"], "numero": numero or len(propios) + 1, "estado": estado,
                    "iniciado_en": ahora, "respuestas": [], "origen_envio": origen if estado == dom.EN_CURSO else "cola",
                    "recuperado_de_cola": recuperado, "dispositivo_id": participante["dispositivo_id"]})

            if politica == act.DECIDE_EL_PROFESOR:
                intento = por_decidir or crear(dom.PENDIENTE_DECISION, False)
            elif objetivo is not None:
                if objetivo["estado"] in (dom.EN_CURSO, dom.PENDIENTE_DECISION) or (
                        objetivo["estado"] == dom.INTENTO_ENTREGADO and tarde and objetivo["origen_envio"] == "cierre"):
                    intento = objetivo
                elif objetivo["estado"] == dom.INTENTO_ENTREGADO and all(
                        any(r["pregunta_ref"] == x["pregunta_ref"] and int(r.get("secuencia") or 0) >= x["secuencia"]
                            for r in objetivo["respuestas"]) for x in limpias):
                    intento = objetivo      # reenvío de lo ya entregado: se acusa sin tocar nada (INV-005)
                else:
                    raise IntentoEntregado(f"El intento {numero} ya está {objetivo['estado']}: no admite respuestas nuevas.",
                                           intento_numero=numero, estado=objetivo["estado"])
            elif en_curso:
                intento = en_curso
            elif tarde and del_cierre:
                intento = del_cierre   # lo que llegó por la cola se suma al intento que el cierre entregó
            else:
                permitidos = distribucion["intentos_permitidos"]
                usados = sum(1 for i in propios if i["estado"] != dom.DESCARTADO)
                if permitidos and usados >= permitidos:
                    raise IntentosAgotados(f"La actividad admite {permitidos} intento(s) y ya se usaron.", intentos_permitidos=permitidos)
                intento = crear(dom.EN_CURSO, tarde)

            # ---- fusión idempotente (INV-013) y calificación de lo nuevo
            nuevas = [{**r, "recibida_en": ahora, "origen": origen if not tarde else "cola", "veredicto": None} for r in limpias]
            fusionadas, resultado = act.fusionar_respuestas(intento["respuestas"], nuevas, sesion_usuario_id=participante.get("sesion_usuario_id", ""))
            a_calificar = [r for r in fusionadas if r["pregunta_ref"] in set(resultado.aceptadas)]
            if politica == act.ACEPTAR and a_calificar:
                veredictos = {}
                faltan = []
                for r in a_calificar:
                    previo = previos.get((r["pregunta_ref"], r["secuencia"]))
                    if previo is not None and previo[0] == r["respuesta"]:
                        veredictos[r["pregunta_ref"]] = previo[1]
                    else:
                        faltan.append(r)
                if faltan:
                    veredictos.update(self._calificar(sesion, distribucion, faltan))
                for r in fusionadas:
                    if r["pregunta_ref"] in veredictos:
                        r["veredicto"] = veredictos[r["pregunta_ref"]]
            campos: dict = {"respuestas": fusionadas}
            if capturas:
                campos["capturado_en"] = max(capturas + [intento["capturado_en"] or 0])
            if tarde and politica == act.ACEPTAR:
                campos["recuperado_de_cola"] = True
            puntaje, maximo, _ = act.totales_del_intento(fusionadas)
            campos.update(puntaje=puntaje, puntaje_maximo=maximo)
            intento = uow.sesiones.actualizar_intento(intento["id"], **campos)

            for ref in resultado.aceptadas:
                self._publicar(uow, sesion_id, dom.EV_RESPUESTA_REGISTRADA, {
                    "intento_id": intento["id"], "distribucion_id": distribucion_id, "participante_id": participante_id,
                    "pregunta_ref": ref, "instante": ahora})   # sin el contenido de la respuesta (BR-127)
            for ref in resultado.duplicadas:
                self._publicar(uow, sesion_id, dom.EV_RESPUESTA_DEDUPLICADA, {
                    "intento_id": intento["id"], "pregunta_ref": ref, "causa": "reenvío", "instante": ahora})

            # ---- entrega: pedida, o implícita si la actividad ya se cerró (nadie más puede entregarla)
            entregado = intento["estado"] == dom.INTENTO_ENTREGADO
            if politica == act.ACEPTAR and intento["estado"] == dom.EN_CURSO and (entregar or tarde):
                intento = self._entregar_intento(uow, sesion_id, intento, ahora, "cola" if (tarde or origen == "cola") else "directo",
                                                 recuperado_de_cola=tarde)
                entregado = True
            if resultado.aceptadas or entregado:
                self._difundir(uow, sesion_id, "resultados", distribucion_id=distribucion_id, participante_id=participante_id)
            return {
                "acuse": True,
                "politica": politica,
                "intento": {"id": intento["id"], "estado": intento["estado"], "numero": intento["numero"],
                            "respondidas": len(intento["respuestas"]), "recuperado_de_cola": intento["recuperado_de_cola"],
                            "secuencia_maxima": max([int(r.get("secuencia") or 0) for r in intento["respuestas"]] or [0])},
                "aceptadas": resultado.aceptadas, "duplicadas": resultado.duplicadas, "superadas": resultado.superadas,
                "rechazadas": rechazadas, "recibida_en": ahora, "servidor_en": ahora,
            }


class ResultadosActividad(_Actividad):
    """CAP-043 · FUN-072 · PAN-004: el avance vivo del grupo. Sólo lo ve el profesor: `puntaje` y `porcentaje` son la
    nota provisional de lo ya calificado (escala 0-100) y el alumno NUNCA la recibe antes de que el profesor la publique
    (DEC-032). Con menos de tres entregas no hay promedio (CMP-043)."""

    def ejecutar(self, actor: Actor, sesion_id: str, distribucion_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            self._autorizar(actor, dom.P_RESULTS_VIEW, sesion)
            distribucion = self._distribucion_de_actividad(uow, sesion_id, distribucion_id)
            participantes = {p["id"]: p for p in uow.sesiones.participantes(sesion_id)}
            intentos = uow.sesiones.intentos(distribucion_id)
            total = distribucion["total_preguntas"]
            filas = []
            for entrega in distribucion["entregas"]["detalle"]:
                p = participantes.get(entrega["participante_id"])
                if p is None:
                    continue
                propios = [i for i in intentos if i["participante_id"] == p["id"]]
                entregado = next((i for i in propios if i["estado"] == dom.INTENTO_ENTREGADO), None)
                en_curso = next((i for i in propios if i["estado"] == dom.EN_CURSO), None)
                decidir = next((i for i in propios if i["estado"] == dom.PENDIENTE_DECISION), None)
                vigente = entregado or en_curso or decidir
                estado = (dom.INTENTO_ENTREGADO if entregado else dom.RESPONDIENDO if en_curso
                          else dom.PENDIENTE_DECISION if decidir else dom.SIN_EMPEZAR)
                respondidas = len(vigente["respuestas"]) if vigente else 0
                avance = (min(1.0, respondidas / total) if total else (1.0 if entregado else 0.0))
                filas.append({
                    "participante_id": p["id"], "persona_id": p["persona_id"], "rotulo": p["persona_rotulo"], "presencia": p["estado"],
                    "estado": estado, "respondidas": respondidas, "total_preguntas": total, "avance": round(avance, 4),
                    "puntaje": vigente["puntaje"] if vigente else None, "puntaje_maximo": vigente["puntaje_maximo"] if vigente else None,
                    "porcentaje": act.porcentaje(vigente["puntaje"], vigente["puntaje_maximo"]) if vigente else None,
                    "sin_calificar": sum(1 for r in (vigente["respuestas"] if vigente else [])
                                         if (r.get("veredicto") or {}).get("puntaje") is None or (r.get("veredicto") or {}).get("pendiente")),
                    "intento_id": vigente["id"] if vigente else None, "origen_envio": vigente["origen_envio"] if vigente else "",
                    "recuperado_de_cola": bool(vigente and vigente["recuperado_de_cola"]),
                    "entregado_en": entregado["enviado_en"] if entregado else None,
                    "bloqueada": False, "rezagado": False,
                })
            rezagados = act.marcar_rezagados(filas) if distribucion["cerrada_en"] is None else 0
            por_estado = {e: sum(1 for f in filas if f["estado"] == e) for e in
                          (dom.INTENTO_ENTREGADO, dom.RESPONDIENDO, dom.SIN_EMPEZAR, dom.PENDIENTE_DECISION)}
            porcentajes = [f["porcentaje"] for f in filas if f["estado"] == dom.INTENTO_ENTREGADO and f["porcentaje"] is not None]
            filas.sort(key=lambda f: (not f["rezagado"], f["estado"] == dom.INTENTO_ENTREGADO, f["rotulo"].lower()))
            return {
                "sesion_id": sesion_id, "distribucion": {k: distribucion[k] for k in (
                    "id", "rotulo", "objeto_ref", "total_preguntas", "puntos_totales", "intentos_permitidos", "tiempo_limite_seg",
                    "abierta_en", "cerrada_en", "abierta")},
                "cronometro": self._cronometro(distribucion, sesion, ahora),
                "totales": {"destinatarios": len(filas), "entregaron": por_estado[dom.INTENTO_ENTREGADO],
                            "respondiendo": por_estado[dom.RESPONDIENDO], "sin_empezar": por_estado[dom.SIN_EMPEZAR],
                            "por_decidir": por_estado[dom.PENDIENTE_DECISION], "rezagados": rezagados,
                            "promedio_porcentaje": round(sum(porcentajes) / len(porcentajes), 2) if len(porcentajes) >= 3 else None,
                            "datos_suficientes": len(porcentajes) >= 3},
                "filas": filas, "servidor_en": ahora,
            }


class DecidirEnvio(_Actividad):
    """DEC-019: lo que llegó fuera de la ventana de gracia espera al profesor, que lo acepta o lo descarta. Queda constancia
    de quién decidió."""

    def ejecutar(self, actor: Actor, sesion_id: str, distribucion_id: str, intento_id: str, decision: str) -> dict:
        if decision not in ("aceptar", "descartar"):
            raise DatosInvalidos("La decisión es «aceptar» o «descartar».")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            self._autorizar(actor, dom.P_ACTIVITY_CLOSE, sesion)
            distribucion = self._distribucion_de_actividad(uow, sesion_id, distribucion_id)
            intento = uow.sesiones.intento(intento_id)
            if not intento or intento["distribucion_id"] != distribucion_id:
                raise NoEncontrado("No existe ese intento en esta actividad.", intento_id=intento_id)
            if intento["estado"] != dom.PENDIENTE_DECISION:
                raise DatosInvalidos("Sólo se decide sobre un envío pendiente de decisión.", estado=intento["estado"])
            if decision == "descartar":
                intento = uow.sesiones.actualizar_intento(intento_id, estado=dom.DESCARTADO)
            else:
                nuevas = [r for r in intento["respuestas"] if r.get("veredicto") is None]
                veredictos = self._calificar(sesion, distribucion, nuevas)
                for r in intento["respuestas"]:
                    if r["pregunta_ref"] in veredictos:
                        r["veredicto"] = veredictos[r["pregunta_ref"]]
                uow.sesiones.actualizar_intento(intento_id, respuestas=intento["respuestas"])
                intento = self._entregar_intento(uow, sesion_id, uow.sesiones.intento(intento_id), ahora, "cola", recuperado_de_cola=True)
            uow.auditoria.registrar(actor.id, f"aula.envio.{decision}", "m07_intento", intento_id,
                                    anterior={"estado": dom.PENDIENTE_DECISION}, nuevo={"estado": intento["estado"]})
            self._difundir(uow, sesion_id, "resultados", distribucion_id=distribucion_id, participante_id=intento["participante_id"])
            return {"intento_id": intento_id, "estado": intento["estado"], "decidido_por": actor.id, "decidido_en": ahora}
