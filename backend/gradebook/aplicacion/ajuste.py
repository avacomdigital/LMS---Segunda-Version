"""
Cambiar una calificación ya registrada, siempre con rastro:

  AjustarCalificacion      FUN-123: el profesor cambia el valor efectivo, con motivo obligatorio; el original NO se sobrescribe
  ReabrirCalificacion      FUN-122: la deja en revisión para recalificar; si estaba publicada, se retira
  ValorarDesempeno         la valoración pedagógica del profesor sobre el nivel de desempeño (la presentación no es sólo una cuenta)
  RetroalimentarCalificacion  la retroalimentación descriptiva y el ajuste razonable aplicado (inclusión)

Todo cambio comparte tres garantías:
  · Concurrencia optimista. El cliente manda la `version_esperada` que leyó; si otra persona cambió la calificación mientras tanto, 409 `conflicto_de_version`
    con la versión actual (no se pisa el cambio del otro).
  · Idempotencia. La `solicitud_id` del cliente identifica la solicitud: reenviarla (un reintento tras perder la señal) devuelve lo ya hecho y no duplica.
  · Historial. Cada cambio es una fila de `m11_calificacion_version` (valor anterior, nuevo, motivo, quién, cuándo según el reloj del nodo), un asiento
    de auditoría y un evento, todo en la misma transacción.
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import puntaje as pj
from ..dominio.errores import ConflictoDeVersion, DatosInvalidos, NoEncontrado, PuntajeInvalido, SolicitudRepetida, TransicionInvalida
from .base import (
    _CasoDeUso,
    comentario_de,
    exigir_sobre_resultado,
    modo_del_nivel,
    motivo_de,
    presentar_con,
    salida_calificacion,
    salida_version,
    solicitud_de,
    version_esperada,
)
from .derivados import RecalcularResultado
from .puertos import Actor, UnidadDeTrabajo


def cargar(uow: UnidadDeTrabajo, calificacion_id: str) -> dict:
    c = uow.calificaciones.por_id(calificacion_id) if calificacion_id else None
    if c is None:
        raise NoEncontrado("No existe esa calificación.", calificacion_id=calificacion_id)
    return c


def reintento(uow: UnidadDeTrabajo, calificacion_id: str, solicitud: str, tipo: str | None = None) -> dict | None:
    """La fila de historial que ya produjo esa solicitud, si es un reenvío. Con `tipo`, una `solicitud_id` que ya hizo OTRA clase de cambio no es un reenvío:
    reutilizarla para una acción distinta se rechaza (409 `solicitud_repetida`) en lugar de devolver «ya hecho» sin hacer nada."""
    previa = uow.versiones.por_solicitud(calificacion_id, solicitud) if solicitud else None
    if previa is not None and tipo is not None and previa["tipo"] != tipo:
        raise SolicitudRepetida("Esa `solicitud_id` ya se usó para otra operación sobre esta calificación: manda una nueva por cada acción.",
                                solicitud_id=solicitud, tipo_previo=previa["tipo"])
    return previa


def actualizar(uow: UnidadDeTrabajo, c: dict, esperada: int, **campos) -> dict:
    """Compara la versión y cambia en una sola sentencia. Si alguien se adelantó: 409 con la versión y el valor que hay ahora."""
    nueva = uow.calificaciones.actualizar_si_version(c["id"], esperada, **campos)
    if nueva is None:
        actual = uow.calificaciones.por_id(c["id"])
        raise ConflictoDeVersion("Otra persona cambió esta calificación mientras la editabas: vuelve a leerla antes de cambiarla.", version_actual=actual["version"],
                                 puntaje_efectivo=pj.como_numero(actual["puntaje_efectivo"]), estado=actual["estado"], version_esperada=esperada)
    return nueva


def _verificar_version(c: dict, esperada: int) -> None:
    if c["version"] != esperada:
        raise ConflictoDeVersion("Otra persona cambió esta calificación mientras la editabas: vuelve a leerla antes de cambiarla.", version_actual=c["version"],
                                 puntaje_efectivo=pj.como_numero(c["puntaje_efectivo"]), estado=c["estado"], version_esperada=esperada)


class _Cambio(_CasoDeUso):
    """Lo que comparten los cambios: cargar, comprobar el alcance y devolver la calificación con su historial."""

    @staticmethod
    def _salida(uow: UnidadDeTrabajo, c: dict, ahora: int, *, reintento: bool = False) -> dict:
        intento = uow.evaluacion.intento(c["intento_id"])
        return {"calificacion": salida_calificacion(uow, c, intento=intento), "historial": [salida_version(v) for v in uow.versiones.de(c["id"])],
                "reintento": reintento, "servidor_en": ahora}

    def _en_su_transaccion(self, actor: Actor, calificacion_id: str, permiso: str, hacer):
        with self.s.uow() as uow:
            ahora = self.s.reloj.ahora_ms()         # ya con el bloqueo de escritura: el instante del historial sigue el orden de sus números
            c = cargar(uow, calificacion_id)
            exigir_sobre_resultado(uow, self.s.autorizacion, actor, permiso, grupo_id=c["grupo_id"], asignacion_id=c["asignacion_id"])
            return hacer(uow, c, ahora)


class AjustarCalificacion(_Cambio):
    """`datos`: `{puntaje_nuevo, motivo, version_esperada, solicitud_id?}`. Sólo una calificación `revisada` o `definitiva`: una reabierta se resuelve
    confirmando su revisión, y una anulada no cuenta. Sobre una publicada el ajuste es válido y queda marcado como POSTERIOR A LA PUBLICACIÓN (evento y
    auditoría); la presentación estampada se vuelve a calcular con la MISMA versión de escala con que se publicó."""

    def ejecutar(self, actor: Actor, calificacion_id: str, datos: dict) -> dict:
        solicitud = solicitud_de(datos)
        return self._en_su_transaccion(actor, calificacion_id, cat.P_MODIFY, lambda uow, c, ahora: self._ajustar(uow, actor, c, datos, solicitud, ahora))

    def _ajustar(self, uow: UnidadDeTrabajo, actor: Actor, c: dict, datos: dict, solicitud: str, ahora: int) -> dict:
        previa = reintento(uow, c["id"], solicitud, cat.V_AJUSTE)
        if previa is not None:
            try:
                pedido = pj.validar_interno(datos.get("puntaje_nuevo"), campo="puntaje_nuevo")
            except PuntajeInvalido:
                pedido = None
            if pedido is not None and pedido != previa["puntaje_nuevo"]:
                raise SolicitudRepetida("Esa `solicitud_id` ya ajustó esta calificación a otro valor: manda una nueva por cada ajuste.", solicitud_id=solicitud,
                                        puntaje_nuevo=pj.como_numero(previa["puntaje_nuevo"]))
            return self._salida(uow, c, ahora, reintento=True)
        if c["estado"] not in cat.CUENTAN:
            raise TransicionInvalida(f"Una calificación «{c['estado']}» no se ajusta: " + (
                "termina primero su revisión." if c["estado"] == cat.REABIERTA else "el intento fue anulado."), estado=c["estado"])
        nuevo = pj.validar_interno(datos.get("puntaje_nuevo"), campo="puntaje_nuevo")
        motivo = motivo_de(datos)
        esperada = version_esperada(datos)
        _verificar_version(c, esperada)
        if nuevo == c["puntaje_efectivo"]:
            raise DatosInvalidos("El valor nuevo es igual al vigente: no hay nada que ajustar.", puntaje_efectivo=pj.como_numero(c["puntaje_efectivo"]))
        publicada = c["estado"] == cat.DEFINITIVA
        campos: dict = {"puntaje_efectivo": nuevo, "actualizada_en": ahora}
        presentacion = None
        if publicada and c.get("escala_version_id"):
            presentacion = presentar_con(uow.escalas.version(c["escala_version_id"]), {**c, "puntaje_efectivo": nuevo})
            campos["presentacion"] = presentacion
        try:
            actual = actualizar(uow, c, esperada, **campos)
        except ConflictoDeVersion:
            if reintento(uow, c["id"], solicitud, cat.V_AJUSTE) is not None:         # dos envíos simultáneos de la misma solicitud: gana el primero y el otro es un reenvío
                return self._salida(uow, uow.calificaciones.por_id(c["id"]), ahora, reintento=True)
            raise
        uow.versiones.anexar(c["id"], cat.V_AJUSTE, actor_id=actor.id or "docente", en=ahora, puntaje_anterior=c["puntaje_efectivo"], puntaje_nuevo=nuevo,
                             estado_anterior=c["estado"], estado_nuevo=c["estado"], motivo=motivo, solicitud_id=solicitud,
                             datos={"posterior_a_publicacion": publicada, "version": actual["version"]})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_AJUSTADA, {
            "calificacion_id": c["id"], "intento_id": c["intento_id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"], "grupo_id": c["grupo_id"],
            "anterior": pj.como_numero(c["puntaje_efectivo"]), "nuevo": pj.como_numero(nuevo), "version": actual["version"], "posterior_a_publicacion": publicada}, ahora)
        if presentacion is not None:
            self._publicar(uow, "Calificacion", c["id"], cat.EV_ESCALA_CONVERTIDA, {
                "calificacion_id": c["id"], "alumno_id": c["alumno_id"], "escala_version_id": c["escala_version_id"], "interno": pj.como_numero(nuevo),
                "etiqueta": presentacion["presentada"]["etiqueta"], "motivo": "ajuste_posterior_a_publicacion"}, ahora)
        uow.auditoria.registrar(actor.id or "docente", cat.A_MODIFICADA, "m11_calificacion", c["id"],
                                anterior={"puntaje_efectivo": pj.como_numero(c["puntaje_efectivo"]), "version": c["version"], "estado": c["estado"]},
                                nuevo={"puntaje_efectivo": pj.como_numero(nuevo), "version": actual["version"], "posterior_a_publicacion": publicada,
                                       "puntaje_original": pj.como_numero(c["puntaje_original"])}, motivo=motivo)
        asignacion = uow.evaluacion.asignacion(c["asignacion_id"])
        if asignacion is not None:
            RecalcularResultado(self.s).resultado(uow, asignacion, c["alumno_id"], ahora)
        return self._salida(uow, actual, ahora)


class ReabrirCalificacion(_Cambio):
    """`datos`: `{motivo, version_esperada, solicitud_id?}`. La calificación pasa a `reabierta`: deja de contar, el alumno deja de verla y entra a la
    bandeja de revisión. MOD-010 sigue siendo el dueño del intento: el libro no lo modifica."""

    def ejecutar(self, actor: Actor, calificacion_id: str, datos: dict) -> dict:
        solicitud = solicitud_de(datos)
        return self._en_su_transaccion(actor, calificacion_id, cat.P_REOPEN, lambda uow, c, ahora: self._reabrir(uow, actor, c, datos, solicitud, ahora))

    def _reabrir(self, uow: UnidadDeTrabajo, actor: Actor, c: dict, datos: dict, solicitud: str, ahora: int) -> dict:
        if reintento(uow, c["id"], solicitud, cat.V_REAPERTURA) is not None:
            return self._salida(uow, c, ahora, reintento=True)
        if c["estado"] not in cat.CUENTAN:
            raise TransicionInvalida(f"Sólo se reabre una calificación revisada o definitiva; ésta está «{c['estado']}».", estado=c["estado"])
        motivo = motivo_de(datos)
        esperada = version_esperada(datos)
        _verificar_version(c, esperada)
        estaba_publicada = c["estado"] == cat.DEFINITIVA
        actual = actualizar(uow, c, esperada, estado=cat.REABIERTA, publicada_en=None, publicada_por="", presentacion={}, actualizada_en=ahora)
        uow.versiones.anexar(c["id"], cat.V_REAPERTURA, actor_id=actor.id or "docente", en=ahora, puntaje_anterior=c["puntaje_efectivo"], estado_anterior=c["estado"],
                             estado_nuevo=cat.REABIERTA, motivo=motivo, solicitud_id=solicitud,
                             datos={"estaba_publicada": estaba_publicada, "presentacion_previa": c.get("presentacion") or {}})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_INTENTO_REABIERTO, {
            "calificacion_id": c["id"], "intento_id": c["intento_id"], "asignacion_id": c["asignacion_id"], "alumno_id": c["alumno_id"], "grupo_id": c["grupo_id"],
            "estaba_publicada": estaba_publicada, "version": actual["version"]}, ahora)
        uow.auditoria.registrar(actor.id or "docente", cat.A_REABIERTA, "m11_calificacion", c["id"],
                                anterior={"estado": c["estado"], "puntaje_efectivo": pj.como_numero(c["puntaje_efectivo"]), "publicada": estaba_publicada},
                                nuevo={"estado": cat.REABIERTA, "version": actual["version"]}, motivo=motivo)
        asignacion = uow.evaluacion.asignacion(c["asignacion_id"])
        if asignacion is not None:
            RecalcularResultado(self.s).resultado(uow, asignacion, c["alumno_id"], ahora)
        return self._salida(uow, actual, ahora)


class ValorarDesempeno(_Cambio):
    """`datos`: `{tramo, motivo, version_esperada, solicitud_id?}` (con `tramo` vacío se retira la valoración y vuelve el nivel que sale de la cuenta). El
    profesor fija el nivel de desempeño con su criterio pedagógico: no cambia el resultado interno."""

    def ejecutar(self, actor: Actor, calificacion_id: str, datos: dict) -> dict:
        solicitud = solicitud_de(datos)
        return self._en_su_transaccion(actor, calificacion_id, cat.P_MODIFY, lambda uow, c, ahora: self._valorar(uow, actor, c, datos, solicitud, ahora))

    def _valorar(self, uow: UnidadDeTrabajo, actor: Actor, c: dict, datos: dict, solicitud: str, ahora: int) -> dict:
        if reintento(uow, c["id"], solicitud, cat.V_VALORACION) is not None:
            return self._salida(uow, c, ahora, reintento=True)
        if c["estado"] not in cat.CUENTAN:
            raise TransicionInvalida(f"Una calificación «{c['estado']}» no se valora.", estado=c["estado"])
        clave = str(datos.get("tramo") or "").strip()
        motivo = motivo_de(datos)
        esperada = version_esperada(datos)
        _verificar_version(c, esperada)
        if c["estado"] == cat.DEFINITIVA and c.get("escala_version_id"):
            version = uow.escalas.version(c["escala_version_id"])
        else:
            _, version = modo_del_nivel(uow, c["nivel_clave"])
        if version is None:
            raise DatosInvalidos("El nivel de esta calificación no tiene una escala con niveles de desempeño: no hay qué valorar.", nivel_clave=c["nivel_clave"])
        if clave and clave not in {t.clave for t in version["definicion"].tramos}:
            raise DatosInvalidos(f"El nivel «{clave}» no existe en la escala «{version['nombre']}».", tramo=clave,
                                 validos=[t.clave for t in version["definicion"].tramos])
        campos: dict = {"desempeno_docente": clave, "desempeno_motivo": motivo if clave else "", "actualizada_en": ahora}
        presentacion = None
        if c["estado"] == cat.DEFINITIVA:
            presentacion = presentar_con(version, {**c, "desempeno_docente": clave})
            campos["presentacion"] = presentacion
        actual = actualizar(uow, c, esperada, **campos)
        uow.versiones.anexar(c["id"], cat.V_VALORACION, actor_id=actor.id or "docente", en=ahora, puntaje_anterior=c["puntaje_efectivo"], puntaje_nuevo=c["puntaje_efectivo"],
                             estado_anterior=c["estado"], estado_nuevo=c["estado"], motivo=motivo, solicitud_id=solicitud,
                             datos={"tramo_anterior": c["desempeno_docente"], "tramo_nuevo": clave, "posterior_a_publicacion": c["estado"] == cat.DEFINITIVA})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_VALORACION, {
            "calificacion_id": c["id"], "alumno_id": c["alumno_id"], "tramo_anterior": c["desempeno_docente"], "tramo_nuevo": clave,
            "posterior_a_publicacion": c["estado"] == cat.DEFINITIVA, "version": actual["version"]}, ahora)
        uow.auditoria.registrar(actor.id or "docente", cat.A_VALORACION, "m11_calificacion", c["id"], anterior={"desempeno_docente": c["desempeno_docente"]},
                                nuevo={"desempeno_docente": clave, "version": actual["version"], "posterior_a_publicacion": presentacion is not None}, motivo=motivo)
        return self._salida(uow, actual, ahora)


class RetroalimentarCalificacion(_Cambio):
    """`datos`: `{fortalezas?, dificultades?, oportunidades?, comentario?, adaptacion?, version_esperada, solicitud_id?}`. La retroalimentación pedagógica
    (qué hizo bien, qué le costó, cómo mejorar) y el ajuste razonable de evaluación que se aplicó. Es texto del profesor: no cambia ninguna cifra."""

    CAMPOS = ("fortalezas", "dificultades", "oportunidades", "comentario")

    def ejecutar(self, actor: Actor, calificacion_id: str, datos: dict) -> dict:
        solicitud = solicitud_de(datos)
        return self._en_su_transaccion(actor, calificacion_id, cat.P_MODIFY, lambda uow, c, ahora: self._retroalimentar(uow, actor, c, datos, solicitud, ahora))

    def _retroalimentar(self, uow: UnidadDeTrabajo, actor: Actor, c: dict, datos: dict, solicitud: str, ahora: int) -> dict:
        if reintento(uow, c["id"], solicitud, cat.V_RETROALIMENTACION) is not None:
            return self._salida(uow, c, ahora, reintento=True)
        if c["estado"] == cat.ANULADA:
            raise TransicionInvalida("Una calificación anulada no se retroalimenta.", estado=c["estado"])
        esperada = version_esperada(datos)
        _verificar_version(c, esperada)
        nueva = {k: comentario_de(datos, k) for k in self.CAMPOS if k in datos}
        if not nueva and "adaptacion" not in datos:
            raise DatosInvalidos("No hay nada que guardar: manda al menos uno de " + ", ".join(self.CAMPOS) + " o `adaptacion`.")
        retro = {**(c.get("retroalimentacion") or {}), **nueva}
        campos: dict = {"retroalimentacion": retro, "actualizada_en": ahora}
        if "adaptacion" in datos:
            campos["adaptacion"] = str(datos.get("adaptacion") or "").strip()[:300]
        actual = actualizar(uow, c, esperada, **campos)
        uow.versiones.anexar(c["id"], cat.V_RETROALIMENTACION, actor_id=actor.id or "docente", en=ahora, estado_anterior=c["estado"], estado_nuevo=c["estado"],
                             solicitud_id=solicitud, datos={"campos": sorted(nueva) + (["adaptacion"] if "adaptacion" in datos else []),
                                                            "posterior_a_publicacion": c["estado"] == cat.DEFINITIVA})
        self._publicar(uow, "Calificacion", c["id"], cat.EV_RETROALIMENTADA, {
            "calificacion_id": c["id"], "alumno_id": c["alumno_id"], "campos": sorted(nueva), "posterior_a_publicacion": c["estado"] == cat.DEFINITIVA,
            "version": actual["version"]}, ahora)
        uow.auditoria.registrar(actor.id or "docente", cat.A_RETROALIMENTADA, "m11_calificacion", c["id"], nuevo={"campos": sorted(nueva), "version": actual["version"],
                                                                                                                  "posterior_a_publicacion": c["estado"] == cat.DEFINITIVA})
        return self._salida(uow, actual, ahora)
