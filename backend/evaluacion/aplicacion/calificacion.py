"""
Calificación y revisión docente (CAP-060, CAP-062, FUN-112, FUN-113; BR-068, BR-069; DEC-032; D-16, D-17):

  RevisionDelIntento  lo que el profesor necesita para revisar: las preguntas que vio el alumno, sus respuestas y los veredictos
  PuntuarRespuesta    el profesor puntúa un reactivo que sólo él puede puntuar (abierto, dibujo, proyecto)
  PublicarIntento     `en_revision_docente → calificado` cuando no queda nada pendiente
  Recalificar         reintenta la calificación pendiente (la biblioteca no estaba al entregar); idempotente (INV-005)
  LiberarResultadoDelIntento  RF-004: el profesor publica el resultado de UN alumno (sin esperar al grupo ni a la fecha)
  ResultadoDelAlumno  lo que el alumno ve de su nota, SÓLO cuando está publicada según la política (DEC-032, RF-004), comprobado en el nodo

MOD-010 produce la puntuación en la escala interna de 0 a 100; la nota PUBLICADA es de MOD-011, que aún no existe: `puntuar` y `publicar` son lo
mínimo para cerrar el ciclo y quedan marcados como provisionales (D-17, Q-84).
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import intento as int_dom
from ..dominio import respuestas as resp_dom
from ..dominio.errores import (
    DatosInvalidos,
    NoEncontrado,
    ReactivosPendientes,
    ResultadosNoLiberados,
    TransicionInvalida,
)
from .alumno import _Alumno
from .base import _CasoDeUso
from .motor import Motor
from .puertos import Actor


class _Revisor(_CasoDeUso):
    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def _cargar(self, uow, intento_id: str, ahora: int) -> tuple[dict, dict]:
        intento = uow.intentos.por_id(intento_id) if intento_id else None
        if intento is None:
            raise NoEncontrado("No existe ese intento.", intento_id=intento_id)
        asignacion = self.motor.asegurar_asignacion(uow, uow.asignaciones.por_id(intento["asignacion_id"]), ahora)
        return uow.intentos.por_id(intento_id), asignacion


class RevisionDelIntento(_Revisor):
    """Para `assessment.review`. Las preguntas se piden a la biblioteca con la versión y la semilla del intento: se ve exactamente lo que vio el alumno."""

    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._cargar(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REVIEW, asignacion)
            if not intento["armado"]:
                raise TransicionInvalida("El intento todavía no tiene examen armado.", estado=intento["estado"])
            vista = self.s.contenido.preguntas(asignacion["fuente_curso"], asignacion["curso_ref"], intento["curso_version"], asignacion["objeto_ref"],
                                               list(intento["armado"]), intento["semilla"], intento_id=intento["id"], dispositivo="", alumno_id=intento["alumno_id"])
            por_ref = {r["pregunta_ref"]: r for r in intento["respuestas"]}
            filas = []
            for pregunta in vista["preguntas"]:
                r = por_ref.get(pregunta["pregunta_ref"])
                filas.append({"pregunta": pregunta, "respuesta": (r or {}).get("respuesta"), "secuencia": (r or {}).get("secuencia"),
                              "veredicto": (r or {}).get("veredicto"), "revision": (r or {}).get("revision"), "historial": (r or {}).get("historial") or [],
                              "respondida": r is not None})
            return {"intento": {"id": intento["id"], "estado": intento["estado"], "alumno_id": intento["alumno_id"], "alumno_rotulo": intento["alumno_rotulo"],
                                "porcentaje": intento.get("porcentaje"), "puntaje": intento.get("puntaje"), "puntaje_maximo": intento.get("puntaje_maximo"),
                                "requiere_revision": intento["requiere_revision"], "pendientes": resp_dom.pendientes_de_revision(intento["respuestas"])},
                    "titulo": vista.get("titulo") or asignacion["titulo"], "filas": filas, "servidor_en": ahora}


class PuntuarRespuesta(_Revisor):
    """`datos`: `{puntaje, comentario?, motivo?}`. Cambiar un puntaje YA puesto exige `motivo` y deja el asiento `calificacion.modificada` con el valor
    anterior y el nuevo (DEC-022, BR-070)."""

    def ejecutar(self, actor: Actor, intento_id: str, pregunta_ref: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._cargar(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REVIEW, asignacion)
            if intento["estado"] not in (cat.EN_REVISION, cat.CALIFICADO):
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: sólo se puntúa uno en revisión docente o ya calificado.",
                                         estado=intento["estado"])
            respuestas = [dict(r) for r in intento["respuestas"]]
            objetivo = next((r for r in respuestas if r["pregunta_ref"] == pregunta_ref), None)
            if objetivo is None:
                raise NoEncontrado("Esa pregunta no tiene respuesta en este intento.", pregunta_ref=pregunta_ref)
            veredicto = objetivo.get("veredicto") or {}
            if not (veredicto.get("requiere_correccion_manual") or veredicto.get("pendiente") or objetivo.get("revision")):
                raise DatosInvalidos("Ese reactivo se califica solo: el profesor puntúa los que la biblioteca marca para corrección manual.",
                                     pregunta_ref=pregunta_ref)
            maximo = veredicto.get("puntaje_maximo")
            if maximo is None:
                maximo = ((intento.get("armado_meta") or {}).get("puntos") or {}).get(pregunta_ref)
            puntaje = self._puntaje(datos.get("puntaje"), maximo)
            previo = objetivo.get("revision")
            motivo = str(datos.get("motivo") or "").strip()
            if previo and previo.get("revisada_en") and len(motivo) < 3:
                raise DatosInvalidos("Cambiar un puntaje ya asentado exige un motivo: queda el valor anterior y el nuevo en la bitácora.",
                                     puntaje_anterior=previo.get("puntaje"))
            quien = actor.id or "docente"
            objetivo["revision"] = {"puntaje": puntaje, "comentario": str(datos.get("comentario") or "")[:500], "revisada_por": quien[:64], "revisada_en": ahora}
            totales = resp_dom.totales(respuestas, intento["armado"], (intento.get("armado_meta") or {}).get("puntos") or {})
            requiere = resp_dom.requiere_revision(respuestas)
            intento = uow.intentos.actualizar(intento["id"], respuestas=respuestas, puntaje=totales["puntaje"], puntaje_maximo=totales["puntaje_maximo"],
                                              porcentaje=totales["porcentaje"], sin_calificar=totales["sin_calificar"], requiere_revision=requiere)
            if previo and previo.get("revisada_en"):
                uow.auditoria.registrar(quien, cat.A_PUNTAJE_MODIFICADO, "m10_intento_formal", intento["id"],
                                        anterior={"pregunta_ref": pregunta_ref, "puntaje": previo.get("puntaje")},
                                        nuevo={"pregunta_ref": pregunta_ref, "puntaje": puntaje}, motivo=motivo)
            self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
            return {"intento_id": intento["id"], "pregunta_ref": pregunta_ref, "puntaje": puntaje, "pendientes": resp_dom.pendientes_de_revision(respuestas),
                    "porcentaje": intento.get("porcentaje"), "servidor_en": ahora}

    @staticmethod
    def _puntaje(valor, maximo) -> float:
        if isinstance(valor, bool) or valor in (None, ""):
            raise DatosInvalidos("Falta `puntaje`.")
        try:
            puntaje = float(valor)
        except (TypeError, ValueError):
            raise DatosInvalidos("`puntaje` debe ser un número.", puntaje=valor)
        if puntaje < 0 or (maximo is not None and puntaje > float(maximo)):
            raise DatosInvalidos(f"`puntaje` debe estar entre 0 y {maximo}.", puntaje=puntaje, maximo=maximo)
        return puntaje


class PublicarIntento(_Revisor):
    """`en_revision_docente → calificado`: la persona que publica queda como evaluador (INV-019). Con reactivos sin puntuar, 409 `reactivos_pendientes`."""

    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._cargar(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REVIEW, asignacion)
            if intento["estado"] != cat.EN_REVISION:
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: sólo se publica uno en revisión docente.", estado=intento["estado"],
                                         destino=cat.CALIFICADO)
            pendientes = resp_dom.pendientes_de_revision(intento["respuestas"])
            if pendientes:
                raise ReactivosPendientes(f"Quedan {len(pendientes)} reactivo(s) sin puntuar.", pendientes=pendientes)
            int_dom.comprobar_transicion(intento["estado"], cat.CALIFICADO)
            quien = actor.id or "docente"
            intento = uow.intentos.actualizar(intento["id"], estado=cat.CALIFICADO, calificado_por=quien[:64], calificado_en=ahora, requiere_revision=False,
                                              porcentaje=intento["porcentaje"] if intento.get("porcentaje") is not None else 0.0)
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_REVISION_PUBLICADA, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "calificado_por": quien}, ahora)
            self.motor.publicar(uow, "Intento", intento["id"], cat.EV_INTENTO_CALIFICADO, {
                "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "porcentaje": intento["porcentaje"],
                "calificado_por": quien}, ahora)
            uow.auditoria.registrar(quien, "evaluacion.revision.publicada", "m10_intento_formal", intento["id"], anterior={"estado": cat.EN_REVISION},
                                    nuevo={"estado": cat.CALIFICADO, "porcentaje": intento["porcentaje"]})
            self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
            # Calificar NO es publicar (RF-004): el alumno sigue sin ver su nota salvo que la política ya lo permita. Esta puede ser la última del grupo.
            asignacion = self.motor.asegurar_publicacion(uow, asignacion, ahora, grupo=True)
            return {"intento_id": intento["id"], "estado": intento["estado"], "porcentaje": intento["porcentaje"], "calificado_por": quien,
                    "calificado_en": ahora, "resultado_publicado": self.motor.resultado_disponible(asignacion, intento)}


class LiberarResultadoDelIntento(_Revisor):
    """RF-004 (publicación individual): el profesor publica el resultado de UN alumno sin esperar al grupo ni a la fecha. Exige un intento `calificado`
    (con la calificación completa: con reactivos por revisar o la biblioteca pendiente no hay nada publicable) y una política distinta de `nunca`.
    Idempotente: la primera publicación manda. Queda quién y cuándo, el evento `evaluacion.resultado_intento_liberado.v1` y el asiento."""

    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._cargar(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_RESULTS_VIEW, asignacion)
            if asignacion["resultados"] == cat.NUNCA:
                raise TransicionInvalida("La evaluación no muestra resultados a los alumnos (política «nunca»): cambia la política antes de publicar uno.",
                                         estado=intento["estado"], resultados=asignacion["resultados"])
            if intento["estado"] == cat.EN_REVISION:
                pendientes = resp_dom.pendientes_de_revision(intento["respuestas"])
                raise ReactivosPendientes(f"Quedan {len(pendientes)} reactivo(s) sin puntuar: puntúalos y publica la calificación antes.", pendientes=pendientes)
            if intento["estado"] != cat.CALIFICADO or intento.get("calificacion_pendiente"):
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: sólo se publica el resultado de uno calificado.", estado=intento["estado"],
                                         destino=cat.CALIFICADO)
            quien = (actor.id or "docente")[:64]
            if intento.get("liberado_en") is None:
                intento = uow.intentos.actualizar(intento["id"], liberado_en=ahora, liberado_por=quien)
                self.motor.publicar(uow, "Intento", intento["id"], cat.EV_RESULTADO_INTENTO_LIBERADO, {
                    "intento_id": intento["id"], "asignacion_id": asignacion["id"], "alumno_id": intento["alumno_id"], "liberado_en": ahora, "por": quien,
                    "origen": cat.ORIGEN_LIBERACION_MANUAL}, ahora)
                uow.auditoria.registrar(quien, cat.A_RESULTADO_INTENTO_LIBERADO, "m10_intento_formal", intento["id"], anterior={"liberado_en": None},
                                        nuevo={"liberado_en": ahora, "alumno_id": intento["alumno_id"]})
                self.motor.avisar(uow, asignacion, "evaluacion", intento_id=intento["id"])
            return {"intento_id": intento["id"], "estado": intento["estado"], "liberado_en": intento["liberado_en"], "liberado_por": intento["liberado_por"],
                    "resultado_publicado": self.motor.resultado_disponible(asignacion, intento), "servidor_en": ahora}


class Recalificar(_Revisor):
    def ejecutar(self, actor: Actor, intento_id: str) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            intento, asignacion = self._cargar(uow, intento_id, ahora)
            self.s.autorizacion.exigir(actor, cat.P_REVIEW, asignacion)
            if intento["estado"] not in cat.ENTREGADOS:
                raise TransicionInvalida(f"El intento está «{intento['estado']}»: sólo se recalifica uno entregado.", estado=intento["estado"])
            intento = self.motor.recalificar(uow, intento, asignacion, ahora)
            return {"intento_id": intento["id"], "estado": intento["estado"], "calificacion_pendiente": intento["calificacion_pendiente"],
                    "porcentaje": intento.get("porcentaje"), "servidor_en": ahora}


class ResultadoDelAlumno(_Alumno):
    """DEC-032: el alumno NUNCA recibe su nota antes de que el profesor la libere. Con reactivos por revisar no hay resultado parcial."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            asignacion = self.motor.asegurar_publicacion(uow, asignacion, ahora, grupo=True)     # lo que la política ya provocó, con el reloj del nodo
            if not self.motor.resultado_disponible(asignacion, intento):
                raise ResultadosNoLiberados(estado=intento["estado"], resultados=asignacion["resultados"], publicar_en=asignacion.get("publicar_en"),
                                            retenido_por=self.motor.resultado_retenido_por(asignacion, intento))      # no nulo: lo retiene otro módulo (el libro de calificaciones)
            aprobacion = asignacion.get("aprobacion_pct")
            detalle = []
            for ref in intento["armado"]:
                r = next((x for x in intento["respuestas"] if x["pregunta_ref"] == ref), None)
                puntaje, maximo = resp_dom.puntaje_de(r) if r else (0.0, (intento["armado_meta"].get("puntos") or {}).get(ref))
                v = (r or {}).get("veredicto") or {}
                detalle.append({"pregunta_ref": ref, "respondida": r is not None, "puntaje": puntaje, "puntaje_maximo": maximo, "correcta": v.get("correcta"),
                                "retroalimentacion": v.get("retroalimentacion") or [], "comentario": ((r or {}).get("revision") or {}).get("comentario", "")})
            return {"intento_id": intento["id"], "asignacion_id": asignacion["id"], "porcentaje": intento["porcentaje"], "puntaje": intento["puntaje"], "puntaje_maximo": intento["puntaje_maximo"],
                    "aprobado": (intento["porcentaje"] >= aprobacion) if aprobacion is not None and intento["porcentaje"] is not None else None,
                    "aprobacion_pct": aprobacion, "detalle": detalle, "servidor_en": ahora}
