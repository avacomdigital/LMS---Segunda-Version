"""
Lo DERIVADO (FUN-126, FUN-127, FUN-129): el resultado de cada alumno en cada asignación (estado simple, estado de la calificación y la que cuenta) y el
agregado por periodo y curso. Todo se deduce de MOD-010 (intentos) y de `m11_calificacion`; si se pierde o se restaura un respaldo, `ReconstruirDerivados`
lo vuelve a calcular y queda igual (idempotente).

  RecalcularResultado   tras cada cambio: guarda el resultado y, si cambió, avisa el estado simple y el agregado
  ReconstruirDerivados  FUN-129: borra y vuelve a calcular todo lo derivado, en una sola transacción
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import puntaje as pj
from ..dominio import resultado as res
from .base import _CasoDeUso, contexto_de, exigir_nodo_instalado
from .puertos import Actor, UnidadDeTrabajo


def clasificacion_de(asignacion: dict, fila: dict | None) -> dict:
    """La clasificación pedagógica de una evaluación dada su fila (si la hay): la que se definió o, sin ella, la razonable por su tipo (un examen es sumativo y
    cuenta para lo oficial; una actividad es formativa y no). No consulta nada: quien ya leyó las filas de muchas evaluaciones de una vez la usa sin una consulta más
    por evaluación."""
    if fila is not None:
        return {"tipo_evaluacion": fila["tipo_evaluacion"], "afecta_oficial": fila["afecta_oficial"], "objetivos": fila.get("objetivos") or [], "definida": True}
    if asignacion.get("tipo") == "examen":
        return {"tipo_evaluacion": cat.SUMATIVA, "afecta_oficial": True, "objetivos": [], "definida": False}
    return {"tipo_evaluacion": cat.FORMATIVA, "afecta_oficial": False, "objetivos": [], "definida": False}


def clasificacion_efectiva(uow: UnidadDeTrabajo, asignacion: dict) -> dict:
    """La clasificación de UNA evaluación (con una consulta)."""
    return clasificacion_de(asignacion, uow.clasificaciones.get(asignacion["id"]))


def politica_de_intentos(uow: UnidadDeTrabajo, asignacion: dict) -> str:
    """Qué intento cuenta. Si MOD-010 declarara una política en los ajustes de la asignación (`politica_intentos`), manda esa; mientras no lo haga decide la
    institución, y sin configuración, el último intento registrado (provisional, documentado)."""
    declarada = str((asignacion.get("ajustes") or {}).get("politica_intentos") or "")
    if declarada in cat.POLITICAS_DE_INTENTOS:
        return declarada
    politica = uow.politica.get()["politica_intentos"]
    return politica if politica in cat.POLITICAS_DE_INTENTOS else cat.POLITICA_PROVISIONAL


class RecalcularResultado(_CasoDeUso):
    """Lo llaman los demás casos de uso dentro de SU transacción; no tiene ruta propia."""

    def resultado(self, uow: UnidadDeTrabajo, asignacion: dict, alumno_id: str, ahora: int, *, silencioso: bool = False, agregado: bool = True) -> dict:
        intentos = uow.evaluacion.intentos_del_alumno(asignacion["id"], alumno_id)
        calificaciones = uow.calificaciones.de_asignacion(asignacion["id"], alumno_id)
        politica = politica_de_intentos(uow, asignacion)
        calculado = res.calcular_resultado(intentos, calificaciones, politica)
        contexto = contexto_de(uow, asignacion, alumno_id)
        previo = uow.resultados.get(asignacion["id"], alumno_id)
        fila = uow.resultados.guardar({
            "asignacion_id": asignacion["id"], "alumno_id": alumno_id, **{k: contexto[k] for k in ("grupo_id", "periodo", "curso_ref")},
            "estado_simple": calculado.estado_simple, "estado_calificacion": calculado.estado_calificacion,
            "calificacion_aplicable_id": calculado.calificacion_aplicable_id or "", "puntaje_aplicable": calculado.puntaje_aplicable, "politica_intentos": politica,
            "intentos_total": calculado.intentos_total, "intentos_registrados": calculado.intentos_registrados,
            "cuenta": clasificacion_efectiva(uow, asignacion)["afecta_oficial"], "publicada": calculado.publicada, "actualizado_en": ahora})
        cambio = (previo is None and calculado.estado_simple != cat.NO_INICIADO) or (previo is not None and previo["estado_simple"] != calculado.estado_simple)
        if cambio and not silencioso:
            self._publicar(uow, "Resultado", f"{asignacion['id']}:{alumno_id}", cat.EV_ESTADO_SIMPLE, {
                "asignacion_id": asignacion["id"], "alumno_id": alumno_id, "grupo_id": contexto["grupo_id"], "estado": calculado.estado_simple,
                "anterior": previo["estado_simple"] if previo else None}, ahora)
        if agregado:
            self.agregado(uow, alumno_id, contexto["grupo_id"], contexto["periodo"], contexto["curso_ref"], ahora, silencioso=silencioso)
        return fila

    def agregado(self, uow: UnidadDeTrabajo, alumno_id: str, grupo_id: str, periodo: str, curso_ref: str, ahora: int, *, silencioso: bool = False) -> dict | None:
        """FUN-127. Sin grupo no hay periodo ni agregado."""
        if not grupo_id:
            return None
        resultados = uow.resultados.de_alumno(alumno_id, grupo_id, periodo, curso_ref)
        calculado = res.calcular_agregado(resultados)
        previo = uow.agregados.get(alumno_id, grupo_id, periodo, curso_ref)
        fila = uow.agregados.guardar({
            "alumno_id": alumno_id, "grupo_id": grupo_id, "periodo": periodo, "curso_ref": curso_ref, "calificaciones": calculado.calificaciones,
            "promedio_simple": calculado.promedio_simple, "pendientes": calculado.pendientes, "provisionales": calculado.provisionales,
            "publicadas": calculado.publicadas, "actualizado_en": ahora})
        iguales = previo is not None and all(previo[k] == fila[k] for k in ("calificaciones", "promedio_simple", "pendientes", "provisionales", "publicadas"))
        if not iguales and not silencioso:
            self._publicar(uow, "Agregado", f"{alumno_id}:{grupo_id}:{periodo}:{curso_ref}", cat.EV_AGREGADOS, {
                "alumno_id": alumno_id, "grupo_id": grupo_id, "periodo": periodo, "curso_ref": curso_ref, "calificaciones": calculado.calificaciones,
                "promedio_simple": pj.como_numero(calculado.promedio_simple), "pendientes": calculado.pendientes, "provisionales": calculado.provisionales,
                "publicadas": calculado.publicadas, "oficial": False}, ahora)
        return fila


class ReconstruirDerivados(_CasoDeUso):
    """FUN-129. Borra lo derivado y lo vuelve a calcular de sus fuentes (MOD-010 y las calificaciones): tras restaurar un respaldo, o cuando alguien dude de
    una cifra. Una sola transacción: o queda todo o queda lo de antes. No toca ninguna calificación ni ningún ajuste: sólo lo que se deduce de ellos."""

    def ejecutar(self, actor: Actor, *, desde_el_sistema: bool = False) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            if not desde_el_sistema:
                self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
            exigir_nodo_instalado(uow)
            derivar = RecalcularResultado(self.s)
            borrados = {"resultados": uow.resultados.borrar_todo(), "agregados": uow.agregados.borrar_todo()}
            pares = set(uow.evaluacion.pares_de_resultados()) | {(c["asignacion_id"], c["alumno_id"]) for c in uow.calificaciones.todas()}
            asignaciones: dict[str, dict | None] = {}
            agregados: set[tuple[str, str, str, str]] = set()
            calculados = 0
            for asignacion_id, alumno_id in sorted(pares):
                if asignacion_id not in asignaciones:
                    asignaciones[asignacion_id] = uow.evaluacion.asignacion(asignacion_id)
                asignacion = asignaciones[asignacion_id]
                if asignacion is None:
                    continue                                   # una calificación huérfana (la asignación ya no existe) no genera resultado
                fila = derivar.resultado(uow, asignacion, alumno_id, ahora, silencioso=True, agregado=False)
                calculados += 1
                if fila["grupo_id"]:
                    agregados.add((alumno_id, fila["grupo_id"], fila["periodo"], fila["curso_ref"]))
            for alumno_id, grupo_id, periodo, curso_ref in sorted(agregados):
                derivar.agregado(uow, alumno_id, grupo_id, periodo, curso_ref, ahora, silencioso=True)
            self._publicar(uow, "Derivados", "gradebook", cat.EV_DERIVADAS_RECONSTRUIDAS, {"resultados": calculados, "agregados": len(agregados)}, ahora)
            uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_DERIVADAS, "m11_resultado", "", anterior=borrados,
                                    nuevo={"resultados": calculados, "agregados": len(agregados)})
            return {"resultados": calculados, "agregados": len(agregados), "borrados": borrados, "servidor_en": ahora}
