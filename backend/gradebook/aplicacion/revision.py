"""
La revisión docente de lo que sólo un profesor puede calificar (FUN-120, FUN-121): respuesta abierta, dibujo y proyecto o entrega.

  BandejaDeRevision   lo que espera al profesor: intentos en revisión de MOD-010 y calificaciones que él reabrió
  DetalleDeRevision   un intento para revisar: cada pregunta con su respuesta, evidencias y, si la hay, la rúbrica de la biblioteca
  AplicarRevision     puntúa un reactivo, a mano (FUN-120) o por rúbrica (FUN-121), con comentario pedagógico
  ConfirmarRevision   cuando no queda nada pendiente, cierra la revisión y registra la calificación

Quién guarda qué: la respuesta y la puntuación del reactivo son de MOD-010 (el libro se las pide por su interfaz); la rúbrica es de la biblioteca (se pide
en el momento y no se guarda); aquí queda la TRAZA de cada revisión (`m11_revision`: puntaje, desglose por criterio, comentario, quién y cuándo) y la
calificación resultante. Un intento no se califica por completo mientras quede un componente obligatorio pendiente.
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import puntaje as pj
from ..dominio import resultado as res
from ..dominio import rubrica as rub
from ..dominio.errores import DatosInvalidos, FueraDeAlcance, NoEncontrado, RevisionNoPendiente, RubricaNoDisponible, SolicitudRepetida, TransicionInvalida
from .base import _CasoDeUso, comentario_de, contexto_de, exigir_en_asignacion, exigir_sobre_resultado, salida_calificacion, solicitud_de
from .puertos import Actor, UnidadDeTrabajo
from .registro import Registrador

PERMISOS_DE_REVISION = (cat.P_MODIFY, cat.P_RUBRIC_APPLY)


def _contexto_del_intento(uow: UnidadDeTrabajo, intento_id: str) -> tuple[dict, dict, dict]:
    intento = uow.evaluacion.intento(intento_id) if intento_id else None
    if intento is None:
        raise NoEncontrado("No existe ese intento.", intento_id=intento_id)
    asignacion = uow.evaluacion.asignacion(intento["asignacion_id"])
    if asignacion is None:
        raise NoEncontrado("No existe la asignación de ese intento.", asignacion_id=intento["asignacion_id"])
    return intento, asignacion, contexto_de(uow, asignacion, intento["alumno_id"])


def _evidencias(respuesta) -> list[dict]:
    """Las referencias a evidencias (MOD-014) que lleva una respuesta: dibujo y audio. Sólo referencias: los archivos no pasan por aquí."""
    salida = []
    if isinstance(respuesta, dict):
        if respuesta.get("drawingRef"):
            salida.append({"tipo": "dibujo", "ref": str(respuesta["drawingRef"])})
        if respuesta.get("audioRef"):
            salida.append({"tipo": "audio", "ref": str(respuesta["audioRef"])})
    return salida


def _rubrica_a_salida(guia: dict | None) -> dict | None:
    if guia is None:
        return None
    return {"criterios": [{"id": c["id"], "criterio": c["criterio"], "puntos_max": pj.como_numero(c["puntos_max"])} for c in guia["rubrica"]],
            "respuesta_modelo": guia.get("respuesta_modelo"), "puntos": guia.get("puntos"), "formato": guia.get("formato")}


class BandejaDeRevision(_CasoDeUso):
    def ejecutar(self, actor: Actor, *, grupo_id: str = "", asignacion_id: str = "") -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            self.s.autorizacion.exigir_alguno(actor, PERMISOS_DE_REVISION, grupo_id=grupo_id)
            visibles = self.s.autorizacion.grupos_visibles(actor, cat.P_MODIFY)         # None: toda la organización
            if asignacion_id:
                asignacion = uow.evaluacion.asignacion(asignacion_id)
                if asignacion is None:
                    raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
                exigir_en_asignacion(uow, self.s.autorizacion, actor, PERMISOS_DE_REVISION, asignacion)
                asignaciones = [asignacion]
                grupos = [asignacion.get("grupo_id") or ""]
            else:
                grupos = [grupo_id] if grupo_id else (uow.identidad.todos_los_grupos() if visibles is None else visibles)
                asignaciones = [a for g in grupos for a in uow.evaluacion.asignaciones_de_grupo(g)]
                if not grupo_id:
                    # Las que fueron a alumnos sueltos no están en ningún grupo: se suman las que el actor opera (las que asignó o donde enseña a alguno de sus alumnos).
                    for a in uow.evaluacion.asignaciones_sin_grupo():
                        try:
                            exigir_en_asignacion(uow, self.s.autorizacion, actor, PERMISOS_DE_REVISION, a)
                        except FueraDeAlcance:
                            continue
                        asignaciones.append(a)
            por_asignacion = {a["id"]: a for a in asignaciones}

            def operable(a: dict, alumno_id: str) -> bool:
                """En una asignación a alumnos sueltos, quien enseña a unos de ellos no revisa a los demás (sólo la organización entera o quien la asignó)."""
                if a.get("grupo_id") or visibles is None or (actor.autenticado and actor.id and actor.id == a.get("profesor_id")):
                    return True
                return bool(set(visibles) & set(uow.identidad.grupos_del_alumno(alumno_id)))

            items: list[dict] = []
            for intento in uow.evaluacion.intentos_en_revision(list(por_asignacion)):
                a = por_asignacion[intento["asignacion_id"]]
                if not operable(a, intento["alumno_id"]):
                    continue
                pendientes = uow.evaluacion.pendientes_de(intento)
                items.append(self._item(uow, a, intento, cat.R_PENDIENTE, pendientes, None))
            for g in [g for g in grupos if g]:
                for c in uow.calificaciones.de_grupo(g):
                    if c["estado"] != cat.REABIERTA or (asignacion_id and c["asignacion_id"] != asignacion_id):
                        continue
                    a = por_asignacion.get(c["asignacion_id"]) or uow.evaluacion.asignacion(c["asignacion_id"])
                    intento = uow.evaluacion.intento(c["intento_id"])
                    if a is not None and intento is not None:
                        items.append(self._item(uow, a, intento, cat.R_REABIERTA, [], c))
            items.sort(key=lambda i: (i["entregado_en"] or 0, i["intento_id"]))
            return {"items": items, "total": len(items), "pendientes": sum(1 for i in items if i["motivo"] == cat.R_PENDIENTE),
                    "reabiertas": sum(1 for i in items if i["motivo"] == cat.R_REABIERTA), "servidor_en": ahora}

    @staticmethod
    def _item(uow: UnidadDeTrabajo, asignacion: dict, intento: dict, motivo: str, pendientes: list[str], calificacion: dict | None) -> dict:
        grupo = uow.identidad.grupo(asignacion.get("grupo_id") or "") if asignacion.get("grupo_id") else None
        provisional = None
        if intento.get("porcentaje") is not None:
            provisional = pj.como_numero(pj.interno_desde_porcentaje(intento["porcentaje"]))
        return {"intento_id": intento["id"], "asignacion_id": asignacion["id"], "titulo": asignacion["titulo"], "curso_rotulo": asignacion.get("curso_rotulo") or "",
                "grupo_id": asignacion.get("grupo_id") or "", "grupo_rotulo": (grupo or {}).get("nombre") or asignacion.get("grupo_rotulo") or "",
                "alumno_id": intento["alumno_id"], "alumno_rotulo": intento.get("alumno_rotulo") or "", "estado_intento": intento["estado"], "motivo": motivo,
                "pendientes": pendientes, "n_pendientes": len(pendientes), "porcentaje_provisional": provisional, "entregado_en": intento.get("entregado_en"),
                "calificacion_id": calificacion["id"] if calificacion else None, "version": calificacion["version"] if calificacion else None}


class DetalleDeRevision(_CasoDeUso):
    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            intento, asignacion, contexto = _contexto_del_intento(uow, intento_id)
            exigir_sobre_resultado(uow, self.s.autorizacion, actor, PERMISOS_DE_REVISION, grupo_id=contexto["grupo_id"], asignacion_id=asignacion["id"])
            base = uow.evaluacion.revision_del_intento(actor, intento_id)
            calificacion = uow.calificaciones.por_intento(intento_id)
            pendientes = uow.evaluacion.pendientes_de(intento)
            trazas = uow.revisiones.de_intento(intento_id)
            filas = []
            for fila in base["filas"]:
                pregunta = fila["pregunta"]
                ref = pregunta["pregunta_ref"]
                veredicto = fila.get("veredicto") or {}
                revision = fila.get("revision") or {}
                revisable = bool(veredicto.get("requiere_correccion_manual") or veredicto.get("pendiente") or revision)
                guia = uow.guia.de(asignacion.get("fuente_curso") or "", asignacion["curso_ref"], intento.get("curso_version") or "", ref) if revisable else None
                maximo = veredicto.get("puntaje_maximo", pregunta.get("puntos"))
                filas.append({
                    "pregunta_ref": ref, "tipo": pregunta.get("tipo"), "forma": res.forma_de_revision(pregunta.get("tipo") or "", fila.get("respuesta")),
                    "enunciado": pregunta.get("enunciado"), "puntaje_maximo": maximo, "respuesta": fila.get("respuesta"), "respondida": fila.get("respondida"),
                    "evidencias": _evidencias(fila.get("respuesta")), "requiere_revision": revisable, "pendiente": ref in pendientes, "revisada": bool(revision.get("revisada_en")),
                    "puntaje_actual": revision.get("puntaje", veredicto.get("puntaje")), "comentario": revision.get("comentario", ""),
                    "revisada_por": revision.get("revisada_por", ""), "revisada_en": revision.get("revisada_en"), "rubrica": _rubrica_a_salida(guia),
                    "revisiones": [{"numero": t["numero"], "tipo": t["tipo"], "puntaje": pj.como_numero(t["puntaje"]), "revisor_id": t["revisor_id"], "revisada_en": t["revisada_en"]}
                                   for t in trazas if t["pregunta_ref"] == ref]})
            reabierta = calificacion is not None and calificacion["estado"] == cat.REABIERTA
            return {"intento": {"id": intento["id"], "asignacion_id": asignacion["id"], "titulo": base.get("titulo") or asignacion["titulo"], "estado": intento["estado"],
                                "alumno_id": intento["alumno_id"], "alumno_rotulo": intento.get("alumno_rotulo") or "", "grupo_id": contexto["grupo_id"],
                                "porcentaje_provisional": None if intento.get("porcentaje") is None else pj.como_numero(pj.interno_desde_porcentaje(intento["porcentaje"])),
                                "pendientes": pendientes, "reabierta": reabierta, "calificacion_id": calificacion["id"] if calificacion else None,
                                "calificacion_version": calificacion["version"] if calificacion else None},
                    "puede_confirmar": (intento["estado"] == cat.I_EN_REVISION and not pendientes) or (reabierta and not pendientes),
                    "filas": filas, "servidor_en": ahora}


class AplicarRevision(_CasoDeUso):
    """`datos`: `{puntaje}` (manual, FUN-120) o `{criterios: [{criterio_id, puntos}]}` (rúbrica, FUN-121), más `comentario`, `motivo` (obligatorio al
    cambiar un puntaje ya asentado) y `solicitud_id` (idempotencia: reenviar la misma solicitud devuelve lo ya hecho, sin duplicar la revisión)."""

    def ejecutar(self, actor: Actor, intento_id: str, pregunta_ref: str, datos: dict) -> dict:
        por_rubrica = datos.get("criterios") is not None
        if por_rubrica and datos.get("puntaje") is not None:
            raise DatosInvalidos("Manda `puntaje` (manual) o `criterios` (rúbrica), no los dos.")
        if not por_rubrica and datos.get("puntaje") is None:
            raise DatosInvalidos("Falta la puntuación: `puntaje` (manual) o `criterios` (rúbrica).")
        with self.s.uow() as uow:
            ahora = self.s.reloj.ahora_ms()         # ya con el bloqueo de escritura: el orden de las revisiones es el de sus instantes
            intento, asignacion, contexto = _contexto_del_intento(uow, intento_id)
            exigir_sobre_resultado(uow, self.s.autorizacion, actor, cat.P_RUBRIC_APPLY if por_rubrica else cat.P_MODIFY, grupo_id=contexto["grupo_id"],
                                   asignacion_id=asignacion["id"])
            solicitud = solicitud_de(datos)
            if solicitud:
                previa = uow.revisiones.por_solicitud(intento_id, solicitud)
                if previa is not None:
                    if previa["pregunta_ref"] != pregunta_ref:
                        raise SolicitudRepetida("Esa `solicitud_id` ya puntuó otra pregunta de este intento: manda una nueva por cada puntuación.",
                                                solicitud_id=solicitud, pregunta_ref=previa["pregunta_ref"])
                    return self._salida(uow, intento, previa, ahora, reintento=True)
            calificacion = uow.calificaciones.por_intento(intento_id)
            if calificacion is not None and calificacion["estado"] != cat.REABIERTA:
                raise TransicionInvalida("Esta calificación ya está registrada: para recalificar, reábrela primero (queda el motivo y el valor anterior).",
                                         estado=calificacion["estado"])
            if calificacion is None and intento["estado"] != cat.I_EN_REVISION:
                raise RevisionNoPendiente(f"El intento está «{intento['estado']}»: sólo se revisa uno en revisión docente.", estado=intento["estado"])
            guia = None
            criterios: list[dict] = []
            if por_rubrica:
                guia = uow.guia.de(asignacion.get("fuente_curso") or "", asignacion["curso_ref"], intento.get("curso_version") or "", pregunta_ref)
                if guia is None or not guia["rubrica"]:
                    raise RubricaNoDisponible("La biblioteca no entregó la rúbrica de esta pregunta: puntúala a mano o vuelve a intentarlo.", pregunta_ref=pregunta_ref)
                maximo_guia = pj.a_decimal(guia["puntos"], campo="puntos") if guia.get("puntos") is not None else None
                puntaje, maximo, criterios = rub.aplicar(guia["rubrica"], datos.get("criterios"), maximo_guia)
            else:
                puntaje, maximo = pj.validar_puntos(datos.get("puntaje"), campo="puntaje"), None
            comentario = comentario_de(datos)
            ya = [t for t in uow.revisiones.de_intento(intento_id) if t["pregunta_ref"] == pregunta_ref]
            respuesta = next((r.get("respuesta") for r in intento["respuestas"] if r["pregunta_ref"] == pregunta_ref), None)
            resultado = uow.evaluacion.puntuar(actor, intento_id, pregunta_ref, {"puntaje": float(puntaje), "comentario": comentario, "motivo": str(datos.get("motivo") or "")})
            maximo_final = maximo if maximo is not None else (resultado.get("puntaje_maximo") if isinstance(resultado, dict) else None)
            fila = uow.revisiones.anexar({
                "intento_id": intento_id, "pregunta_ref": pregunta_ref, "numero": len(ya) + 1, "tipo": cat.REVISION_RUBRICA if por_rubrica else cat.REVISION_MANUAL,
                "forma": res.forma_de_revision("open", respuesta), "puntaje": puntaje,
                "puntaje_maximo": None if maximo_final is None else pj.a_decimal(maximo_final, campo="maximo"), "criterios": criterios, "comentario": comentario,
                "evidencias": _evidencias(respuesta), "revisor_id": actor.id or cat.SISTEMA, "revisada_en": ahora, "solicitud_id": solicitud})
            evento = cat.EV_RUBRICA_APLICADA if por_rubrica else cat.EV_MANUAL_APLICADA
            self._publicar(uow, "Revision", f"{intento_id}:{pregunta_ref}", evento, {
                "intento_id": intento_id, "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "pregunta_ref": pregunta_ref,
                "puntaje": pj.como_numero(puntaje), "puntaje_maximo": pj.como_numero(fila["puntaje_maximo"]), "criterios": len(criterios), "numero": fila["numero"]}, ahora)
            uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_RUBRICA if por_rubrica else cat.A_MANUAL, "m10_intento_formal", intento_id,
                                    nuevo={"pregunta_ref": pregunta_ref, "puntaje": pj.como_numero(puntaje), "numero": fila["numero"]},
                                    motivo=str(datos.get("motivo") or "").strip() or None)
            return self._salida(uow, uow.evaluacion.intento(intento_id), fila, ahora)

    @staticmethod
    def _salida(uow: UnidadDeTrabajo, intento: dict, fila: dict, ahora: int, *, reintento: bool = False) -> dict:
        pendientes = uow.evaluacion.pendientes_de(intento)
        return {"intento_id": intento["id"], "pregunta_ref": fila["pregunta_ref"], "numero": fila["numero"], "tipo": fila["tipo"], "puntaje": pj.como_numero(fila["puntaje"]),
                "puntaje_maximo": pj.como_numero(fila["puntaje_maximo"]), "criterios": fila["criterios"], "comentario": fila["comentario"], "pendientes": pendientes,
                "listo_para_confirmar": not pendientes, "porcentaje_provisional": None if intento.get("porcentaje") is None else pj.como_numero(pj.interno_desde_porcentaje(intento["porcentaje"])),
                "reintento": reintento, "servidor_en": ahora}


class ConfirmarRevision(_CasoDeUso):
    """Cierra la revisión: con todo puntuado, MOD-010 pasa el intento a `calificado` y el libro registra la calificación (FUN-119). Con reactivos sin
    puntuar, 409 `reactivos_pendientes`. Para una calificación reabierta, MOD-010 ya está en `calificado` y sólo se recalcula."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict | None = None) -> dict:
        with self.s.uow() as uow:
            ahora = self.s.reloj.ahora_ms()
            intento, asignacion, contexto = _contexto_del_intento(uow, intento_id)
            exigir_sobre_resultado(uow, self.s.autorizacion, actor, PERMISOS_DE_REVISION, grupo_id=contexto["grupo_id"], asignacion_id=asignacion["id"])
            calificacion = uow.calificaciones.por_intento(intento_id)
            reabierta = calificacion is not None and calificacion["estado"] == cat.REABIERTA
            if intento["estado"] == cat.I_EN_REVISION:
                uow.evaluacion.publicar_revision(actor, intento_id)
            elif not (intento["estado"] == cat.I_CALIFICADO and reabierta):
                if calificacion is not None and calificacion["estado"] in (cat.REVISADA, cat.DEFINITIVA):
                    raise RevisionNoPendiente("Esta calificación ya está confirmada.", estado=calificacion["estado"], calificacion_id=calificacion["id"])
                raise RevisionNoPendiente(f"El intento está «{intento['estado']}»: sólo se confirma la revisión de uno en revisión docente o reabierto.",
                                          estado=intento["estado"])
            ajuste_previo = calificacion["puntaje_efectivo"] if reabierta and calificacion["puntaje_efectivo"] != calificacion["puntaje_fuente"] else None
            fila, resultado, _ = Registrador(self.s).registrar(uow, intento_id, ahora, actor_id=actor.id or cat.SISTEMA, confirmar_recalculo=True)
            intento = uow.evaluacion.intento(intento_id)
            # Si recalificar cambió la puntuación, el ajuste que el profesor había hecho dejó de tener base y se descartó: se le dice cuál era (también queda en el historial).
            descartado = fila is not None and ajuste_previo is not None and fila["puntaje_efectivo"] != ajuste_previo
            return {"intento_id": intento_id, "estado": intento["estado"], "resultado": resultado, "registrada": fila is not None,
                    "calificacion": salida_calificacion(uow, fila, intento=intento) if fila else None, "ajuste_descartado": descartado,
                    "ajuste_anterior": pj.como_numero(ajuste_previo) if descartado else None, "servidor_en": ahora}
