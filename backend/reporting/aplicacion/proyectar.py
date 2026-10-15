"""
Recalcular UNA fila derivada desde el módulo dueño (nunca desde la carga de un evento): un evento sólo AVISA que algo cambió y aquí se vuelve a leer la fuente de verdad. Por eso
procesar dos veces el mismo evento no duplica nada, y por eso borrar las proyecciones y reconstruirlas devuelve los mismos reportes (BR-007).

  Proyector.clase   el reporte de una clase terminada y la fila de cada alumno (`m13_clase`, `m13_clase_alumno`)
  Proyector.grupo   el avance de un grupo y el de cada uno de sus alumnos (`m13_avance_grupo`, `m13_avance_alumno`): lee las evaluaciones, el libro y el estudio UNA vez por grupo

Reporting no escribe en ningún dato de otro módulo: todo lo que lee entra por los puertos de `puertos.py`, y todo lo que guarda es `m13_*`.
"""
from __future__ import annotations

from ..dominio import avance as av
from ..dominio import catalogos as cat
from ..dominio import clase as clase_dom
from ..dominio import integracion
from ..dominio.metricas import como_numero, promedio
from .base import _CasoDeUso
from .puertos import UnidadDeTrabajo

_VIVOS = {"no_iniciado", "en_curso", "pausado_desconexion", "restaurando", "en_curso_fuera_de_plazo"}
_PRESENTADO = {"entregado", "en_revision_docente", "calificado"}
SIN_FIN = 2 ** 62          # una señal que no caduca sola (la cola de estudio dura hasta que el nodo integra el trabajo)


def estado_del_intento(estados: set[str]) -> str:
    """El estado de un alumno ante una evaluación a partir de los estados de sus intentos (el anulado no cuenta)."""
    if "calificado" in estados:
        return "calificado"
    if "en_revision_docente" in estados:
        return "en_revision"
    if "entregado" in estados:
        return "entregado"
    if estados & _VIVOS:
        return "en_curso"
    return "sin_intento"


def senales_de_estudio(uow: UnidadDeTrabajo, alumno_ids: list[str]) -> list[dict]:
    """Las tabletas de estos alumnos que avisaron de trabajo de estudio por enviar (no caducan solas)."""
    return [integracion.senal(f["dispositivo_id"], cat.COLA_DE_ESTUDIO, SIN_FIN) for f in uow.equipos_estado.pendientes_de(alumno_ids)]


class Proyector(_CasoDeUso):
    # ------------------------------------------------------------------------------------------------------------------ una clase
    def clase(self, uow: UnidadDeTrabajo, sesion_id: str, ahora: int) -> dict:
        """Recalcula la clase `sesion_id` si ya terminó. Devuelve `{cambio, grupo_id, nueva_incompletitud}`: `cambio` es False si lo recalculado es idéntico a lo guardado
        (misma huella: no se escribe nada); `nueva_incompletitud` lleva el resumen de integración cuando la clase PASÓ a incompleta (para avisarlo una sola vez)."""
        detalle = uow.aula.detalle_de_sesion(sesion_id)
        previa = uow.clases.get(sesion_id)
        if detalle is None:
            if previa is not None:
                uow.clases.eliminar(sesion_id)
            return {"cambio": previa is not None, "grupo_id": (previa or {}).get("grupo_id", ""), "nueva_incompletitud": None}
        resumen = clase_dom.resumir(detalle, ahora)
        if resumen is None:                                          # aún no termina: su reporte se arma al cerrarla
            return {"cambio": False, "grupo_id": (previa or {}).get("grupo_id", ""), "nueva_incompletitud": None}
        c = resumen["clase"]
        grupo = uow.identidad.grupo(c["grupo_id"]) if c["grupo_id"] else None
        fila = {**c, "periodo": (grupo or {}).get("periodo") or "", "nivel_clave": (grupo or {}).get("nivel_clave") or ""}
        fila["huella"] = clase_dom.huella({k: v for k, v in fila.items() if k != "huella"} | {"alumnos": resumen["alumnos"]})
        fila["corte_en"] = ahora
        cambio = uow.clases.guardar(fila, resumen["alumnos"])
        nueva = None
        if cambio:
            antes = integracion.resumir(previa["senales"], 0, ahora) if previa else None
            despues = integracion.resumir(c["senales"], c["equipos"], ahora)
            if integracion.nueva_incompletitud(antes, despues):
                nueva = despues
            if c["grupo_id"]:
                uow.avances.marcar_sucio(c["grupo_id"], ahora)
        return {"cambio": cambio, "grupo_id": c["grupo_id"], "nueva_incompletitud": nueva}

    # ------------------------------------------------------------------------------------------------------------------ un grupo
    def grupo(self, uow: UnidadDeTrabajo, grupo_id: str, ahora: int) -> dict:
        """Recalcula el avance del grupo y el de todos sus alumnos. Devuelve `{alumnos}`. Lee de los dueños (evaluaciones, libro, estudio) UNA vez por grupo,
        no una por alumno: un grupo de 35 es unas 30 consultas, no mil."""
        grupo = uow.identidad.grupo(grupo_id)
        if grupo is None or not grupo["activo"]:
            uow.avances.eliminar_grupo(grupo_id)                    # un grupo que ya no existe no deja un avance «sucio» para siempre
            return {"alumnos": 0}
        padron = uow.identidad.alumnos_del_grupo(grupo_id)
        alumno_ids = [a["id"] for a in padron]
        clases = uow.clases.de_grupo(grupo_id)
        por_clase = uow.clases.alumnos_de_clases([c["sesion_id"] for c in clases])
        asignaciones = [a for a in uow.evaluacion.asignaciones_de_grupo(grupo_id) if a["estado"] != cat.ASIGNACION_BORRADOR]
        intentos = {a["id"]: uow.evaluacion.intentos_de_asignacion(a["id"]) for a in asignaciones}
        libro = uow.libro.resultados_del_grupo(grupo_id) or {"resultados": [], "modo": "simple", "escala": None}
        del_libro = {(r["asignacion_id"], r["alumno_id"]): r for r in libro["resultados"]}
        estudios = uow.estudio.asignaciones_de_estudio([grupo_id])
        tareas = {(t["asignacion_id"], t["alumno_id"]): t for t in uow.estudio.tareas_de([e["id"] for e in estudios])}

        filas: list[dict] = []
        for alumno_id in alumno_ids:
            detalle = {"clases": self._clases_de(alumno_id, clases, por_clase),
                       "evaluaciones": self._evaluaciones_de(alumno_id, asignaciones, intentos, del_libro),
                       "estudios": self._estudios_de(alumno_id, estudios, tareas, ahora)}
            r = av.resumir(detalle)
            filas.append({
                "grupo_id": grupo_id, "alumno_id": alumno_id, "clases_total": r["clases_total"], "clases_asistidas": r["clases_asistidas"],
                "actividades_recibidas": r["actividades_recibidas"], "actividades_entregadas": r["actividades_entregadas"],
                "porcentaje_aciertos": r["porcentaje_aciertos"], "evaluaciones_total": r["evaluaciones_total"], "evaluaciones_presentadas": r["evaluaciones_presentadas"],
                "evaluaciones_sin_presentar": r["evaluaciones_sin_presentar"], "estudios_total": r["estudios_total"], "estudios_completados": r["estudios_completados"],
                "estudios_vencidos": r["estudios_vencidos"], "avance_estudio": r["avance_estudio"], "atencion": r["atencion"],
                "ultima_actividad_en": r["ultima_actividad_en"], "detalle": detalle, "corte_en": ahora, "_participacion": r["porcentaje_participacion"]})
        uow.avances.guardar_alumnos(grupo_id, [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas])

        senales = integracion.unir([s for c in clases for s in c["senales"]], senales_de_estudio(uow, alumno_ids))
        equipos = {s["equipo"] for c in clases for s in c["senales"]} | {s["equipo"] for s in senales}
        despues = integracion.resumir(senales, len(equipos), ahora)
        uow.avances.guardar_grupo({
            "grupo_id": grupo_id, "periodo": grupo["periodo"], "nivel_clave": grupo["nivel_clave"] or "", "modo": libro.get("modo") or "simple", "escala": libro.get("escala"),
            "alumnos": len(filas), "clases": len(clases),
            "evaluaciones": len(asignaciones), "estudios": len(estudios), "en_atencion": sum(1 for f in filas if f["atencion"]),
            "promedio_participacion": promedio(f["_participacion"] for f in filas), "promedio_aciertos": promedio(f["porcentaje_aciertos"] for f in filas),
            "estado_integracion": despues["estado"], "motivos_integracion": [m["codigo"] for m in despues["motivos"]], "desactualizado": False,
            "desactualizado_en": None, "corte_en": ahora})
        return {"alumnos": len(filas)}

    # ------------------------------------------------------------------------------------------------------------ el detalle de UN alumno
    @staticmethod
    def _clases_de(alumno_id: str, clases: list[dict], por_clase: dict[str, dict[str, dict]]) -> list[dict]:
        salida = []
        for c in clases:
            fila = por_clase.get(c["sesion_id"], {}).get(alumno_id)
            salida.append({"sesion_id": c["sesion_id"], "curso_ref": c["curso_ref"], "finalizada_en": c["finalizada_en"], "asistio": fila is not None,
                           "recibidas": fila["actividades_recibidas"] if fila else 0, "entregadas": fila["actividades_entregadas"] if fila else 0,
                           "puntos": como_numero(fila["puntos"]) if fila else 0, "puntos_maximos": como_numero(fila["puntos_maximos"]) if fila else 0})
        return salida

    @staticmethod
    def _evaluaciones_de(alumno_id: str, asignaciones: list[dict], intentos: dict[str, list[dict]], del_libro: dict) -> list[dict]:
        salida = []
        for a in asignaciones:
            if a["alcance"] != "grupo" and alumno_id not in (a.get("destinatarios") or []):
                continue
            mios = [i for i in intentos.get(a["id"], []) if i["alumno_id"] == alumno_id and i["estado"] != "anulado"]
            estado = estado_del_intento({i["estado"] for i in mios})
            presento = estado in ("calificado", "en_revision", "entregado")
            r = del_libro.get((a["id"], alumno_id))
            salida.append({
                "asignacion_id": a["id"], "curso_ref": a["curso_ref"], "estado_asignacion": a["estado"], "presento": presento,
                "sin_presentar": (not presento) and a["estado"] in cat.ASIGNACIONES_CERRADAS, "estado_intento": estado,
                "estado_simple": r["estado_simple"] if r else "no_iniciado", "estado": r["estado"] if r else "sin_registro", "publicada": bool(r and r["publicada"]),
                "presentacion": r["presentacion"] if r else None, "puntaje_aplicable": r["puntaje_aplicable"] if r else None,
                "ultima_en": max((i.get("entregado_en") or 0 for i in mios), default=0) or None})
        return salida

    @staticmethod
    def _estudios_de(alumno_id: str, estudios: list[dict], tareas: dict, ahora: int) -> list[dict]:
        salida = []
        for e in estudios:
            if e["alcance"] != "grupo" and alumno_id not in (e.get("destinatarios") or []):
                continue
            t = tareas.get((e["id"], alumno_id))
            estado = t["estado"] if t else "pendiente"
            completada = estado == "completada"
            salida.append({"asignacion_id": e["id"], "curso_ref": e["curso_ref"], "estado": estado, "avance_pct": t["avance_pct"] if t else 0, "completada": completada,
                           "vencida": (not completada) and e.get("fecha_limite") is not None and ahora > int(e["fecha_limite"]),
                           "ultima_en": (t.get("completada_en") or t.get("ultimo_avance_en")) if t else None})
        return salida
