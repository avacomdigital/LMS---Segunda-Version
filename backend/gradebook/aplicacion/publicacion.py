"""
Publicar calificaciones: el profesor decide CUÁNDO el alumno ve su nota. Entregar una evaluación y calificarla son procesos distintos de publicarla.

  PublicarCalificacion   `revisada → definitiva`: estampa la presentación con la versión de escala vigente del nivel y la deja visible al alumno
  PublicarAsignacion     lo mismo para todas las calificaciones revisadas de una asignación (o las que se indiquen)
  RetirarPublicacion     `definitiva → revisada`: el alumno deja de verla (con motivo)

EXTENSIÓN TÉCNICA PROPUESTA: el Documento Maestro regula la visibilidad (el alumno no ve notas sin publicar, FUN-119…129) pero no define una función de
publicación. Esta lo es: permiso `grades.publish`, eventos `calificacion.publicada.v1` y `calificacion.publicacion_retirada.v1`.

Precondiciones, todas comprobadas en el nodo: el intento sigue calificado del todo en MOD-010 (no anulado, sin revisión pendiente ni calificación pendiente
de la biblioteca), la asignación admite mostrar resultados a los alumnos (su política no es `nunca`) y el nivel está en modo calificaciones con una escala.
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import puntaje as pj
from ..dominio.errores import ConflictoDeVersion, DatosInvalidos, FueraDeAlcance, ModoSimple, NoEncontrado, NoPublicable, TransicionInvalida
from .ajuste import _Cambio, actualizar, reintento
from .base import exigir_en_asignacion, exigir_sobre_resultado, modo_del_nivel, motivo_de, presentar_con, solicitud_de, version_esperada
from .derivados import RecalcularResultado
from .puertos import Actor, UnidadDeTrabajo
from .registro import por_que_no_es_calificable


def motivos_para_no_publicar(uow: UnidadDeTrabajo, c: dict) -> list[str]:
    """Todo lo que impide publicar esta calificación ahora (vacía = se puede)."""
    motivos: list[str] = []
    if c["estado"] != cat.REVISADA:
        motivos.append(f"Está «{c['estado']}»: sólo se publica una calificación revisada.")
    intento = uow.evaluacion.intento(c["intento_id"])
    asignacion = uow.evaluacion.asignacion(c["asignacion_id"])
    if intento is None or asignacion is None:
        return motivos + ["El intento o la asignación ya no existen en la evaluación."]
    razon = por_que_no_es_calificable(intento, uow.evaluacion)
    if razon:
        motivos.append({"anulado": "El intento fue anulado en la evaluación.", "revision_pendiente": "El intento tiene revisiones pendientes.",
                        "calificacion_pendiente": "La biblioteca todavía no calificó todas las respuestas.", "sin_calificar": "El intento no está calificado.",
                        "sin_porcentaje": "El intento no tiene puntuación."}.get(razon, razon))
    if asignacion.get("resultados") == "nunca":
        motivos.append("La evaluación está configurada para no mostrar resultados a los alumnos (política «nunca»): cambia su política antes de publicar.")
    return motivos


class PublicarCalificacion(_Cambio):
    """`datos`: `{version_esperada?, solicitud_id?}`. Idempotente: publicar una calificación ya publicada devuelve la misma, sin duplicar nada."""

    def ejecutar(self, actor: Actor, calificacion_id: str, datos: dict | None = None) -> dict:
        datos = datos or {}
        return self._en_su_transaccion(actor, calificacion_id, cat.P_PUBLISH, lambda uow, c, ahora: self.publicar(uow, actor, c, datos, ahora))

    def publicar(self, uow: UnidadDeTrabajo, actor: Actor, c: dict, datos: dict, ahora: int) -> dict:
        solicitud = solicitud_de(datos)
        if c["estado"] == cat.DEFINITIVA or reintento(uow, c["id"], solicitud, cat.V_PUBLICACION) is not None:
            return self._salida(uow, c, ahora, reintento=True)
        esperada = version_esperada(datos, obligatorio=False)
        if esperada is not None and esperada != c["version"]:
            raise ConflictoDeVersion("Otra persona cambió esta calificación mientras la editabas: vuelve a leerla.", version_actual=c["version"], estado=c["estado"],
                                     puntaje_efectivo=pj.como_numero(c["puntaje_efectivo"]), version_esperada=esperada)
        modo, version = modo_del_nivel(uow, c["nivel_clave"])
        if modo == cat.SIMPLE or version is None:
            raise ModoSimple("El nivel de este grupo está en modo simple: no se publican calificaciones.", nivel_clave=c["nivel_clave"] or None)
        motivos = motivos_para_no_publicar(uow, c)
        if motivos:
            raise NoPublicable("Esta calificación no se puede publicar todavía.", motivos=motivos, estado=c["estado"], calificacion_id=c["id"])
        presentacion = presentar_con(version, c)
        actual = actualizar(uow, c, c["version"], estado=cat.DEFINITIVA, publicada_en=ahora, publicada_por=actor.id or "docente", escala_version_id=version["id"],
                            presentacion=presentacion, actualizada_en=ahora)
        uow.versiones.anexar(c["id"], cat.V_PUBLICACION, actor_id=actor.id or "docente", en=ahora, puntaje_anterior=c["puntaje_efectivo"], puntaje_nuevo=c["puntaje_efectivo"],
                             estado_anterior=c["estado"], estado_nuevo=cat.DEFINITIVA, solicitud_id=solicitud,
                             datos={"escala_version_id": version["id"], "escala": version["codigo"], "numero": version["numero"], "huella": version["huella"],
                                    "etiqueta": presentacion["presentada"]["etiqueta"]})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_ESCALA_CONVERTIDA, {
            "calificacion_id": c["id"], "alumno_id": c["alumno_id"], "escala_version_id": version["id"], "escala": version["codigo"], "numero": version["numero"],
            "interno": pj.como_numero(c["puntaje_efectivo"]), "etiqueta": presentacion["presentada"]["etiqueta"], "motivo": "publicacion"}, ahora)
        self._publicar(uow, "Calificacion", c["id"], cat.EV_PUBLICADA, {
            "calificacion_id": c["id"], "intento_id": c["intento_id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"], "grupo_id": c["grupo_id"],
            "version": actual["version"], "escala_version_id": version["id"]}, ahora)
        uow.auditoria.registrar(actor.id or "docente", cat.A_PUBLICADA, "m11_calificacion", c["id"], anterior={"estado": c["estado"]},
                                nuevo={"estado": cat.DEFINITIVA, "version": actual["version"], "escala": version["codigo"], "numero": version["numero"]})
        asignacion = uow.evaluacion.asignacion(c["asignacion_id"])
        if asignacion is not None:
            RecalcularResultado(self.s).resultado(uow, asignacion, c["alumno_id"], ahora)
        return self._salida(uow, actual, ahora)


class PublicarAsignacion(PublicarCalificacion):
    """`datos`: `{calificacion_ids?: [...], solicitud_id?}`. Publica todas las calificaciones `revisada` de la asignación (o sólo las indicadas); las que no
    cumplen las precondiciones se OMITEN con su motivo, no tumban a las demás."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict | None = None) -> dict:       # type: ignore[override]
        datos = datos or {}
        crudas = datos.get("calificacion_ids")
        if crudas is not None and (not isinstance(crudas, list) or not all(isinstance(i, str) for i in crudas) or len(crudas) > 1000):
            raise DatosInvalidos("`calificacion_ids` debe ser una lista de identificadores de calificación.")
        with self.s.uow() as uow:
            ahora = self.s.reloj.ahora_ms()
            asignacion = uow.evaluacion.asignacion(asignacion_id)
            if asignacion is None:
                raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
            exigir_en_asignacion(uow, self.s.autorizacion, actor, cat.P_PUBLISH, asignacion)
            pedidas = set(crudas or [])
            publicadas, omitidas, ya = [], [], 0
            for c in uow.calificaciones.de_asignacion(asignacion_id):
                if pedidas and c["id"] not in pedidas:
                    continue
                if c["estado"] == cat.DEFINITIVA:
                    ya += 1
                    continue
                try:
                    # Cada calificación se publica con el alcance de SU grupo: una asignación a alumnos de varios grupos no deja publicar a quien sólo enseña en uno.
                    exigir_sobre_resultado(uow, self.s.autorizacion, actor, cat.P_PUBLISH, grupo_id=c["grupo_id"], asignacion_id=asignacion_id)
                except FueraDeAlcance as error:
                    omitidas.append({"calificacion_id": c["id"], "alumno_id": c["alumno_id"], "estado": c["estado"], "codigo": error.codigo, "motivos": [error.detalle]})
                    continue
                try:
                    with uow.aislado():
                        salida = self.publicar(uow, actor, c, {"solicitud_id": ""}, ahora)
                    publicadas.append({"calificacion_id": c["id"], "alumno_id": c["alumno_id"], "version": salida["calificacion"]["version"]})
                except (NoPublicable, TransicionInvalida, ModoSimple) as error:
                    omitidas.append({"calificacion_id": c["id"], "alumno_id": c["alumno_id"], "estado": c["estado"], "codigo": error.codigo,
                                     "motivos": error.extra.get("motivos") or [error.detalle]})
            return {"asignacion_id": asignacion_id, "publicadas": publicadas, "omitidas": omitidas, "ya_publicadas": ya,
                    "total_publicadas": len(publicadas), "servidor_en": ahora}


class RetirarPublicacion(_Cambio):
    """`datos`: `{motivo, version_esperada, solicitud_id?}`. El alumno deja de ver la calificación; vuelve a `revisada` y puede publicarse otra vez."""

    def ejecutar(self, actor: Actor, calificacion_id: str, datos: dict) -> dict:
        solicitud = solicitud_de(datos)
        return self._en_su_transaccion(actor, calificacion_id, cat.P_PUBLISH, lambda uow, c, ahora: self._retirar(uow, actor, c, datos, solicitud, ahora))

    def _retirar(self, uow: UnidadDeTrabajo, actor: Actor, c: dict, datos: dict, solicitud: str, ahora: int) -> dict:
        if reintento(uow, c["id"], solicitud, cat.V_RETIRO) is not None:
            return self._salida(uow, c, ahora, reintento=True)
        if c["estado"] != cat.DEFINITIVA:
            raise TransicionInvalida(f"Sólo se retira la publicación de una calificación definitiva; ésta está «{c['estado']}».", estado=c["estado"])
        motivo = motivo_de(datos)
        esperada = version_esperada(datos)
        if esperada != c["version"]:
            raise ConflictoDeVersion("Otra persona cambió esta calificación mientras la editabas: vuelve a leerla.", version_actual=c["version"], estado=c["estado"],
                                     puntaje_efectivo=pj.como_numero(c["puntaje_efectivo"]), version_esperada=esperada)
        actual = actualizar(uow, c, esperada, estado=cat.REVISADA, publicada_en=None, publicada_por="", presentacion={}, actualizada_en=ahora)
        uow.versiones.anexar(c["id"], cat.V_RETIRO, actor_id=actor.id or "docente", en=ahora, puntaje_anterior=c["puntaje_efectivo"], puntaje_nuevo=c["puntaje_efectivo"],
                             estado_anterior=cat.DEFINITIVA, estado_nuevo=cat.REVISADA, motivo=motivo, solicitud_id=solicitud,
                             datos={"presentacion_previa": c.get("presentacion") or {}})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_PUBLICACION_RETIRADA, {
            "calificacion_id": c["id"], "intento_id": c["intento_id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"], "version": actual["version"]}, ahora)
        uow.auditoria.registrar(actor.id or "docente", cat.A_PUBLICACION_RETIRADA, "m11_calificacion", c["id"], anterior={"estado": cat.DEFINITIVA},
                                nuevo={"estado": cat.REVISADA, "version": actual["version"]}, motivo=motivo)
        asignacion = uow.evaluacion.asignacion(c["asignacion_id"])
        if asignacion is not None:
            RecalcularResultado(self.s).resultado(uow, asignacion, c["alumno_id"], ahora)
        return self._salida(uow, actual, ahora)
