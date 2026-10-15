"""
El avance de UN alumno en UN grupo (CAP-082, FUN-139/140): del detalle por clase, evaluación y estudio que arma `aplicacion/proyectar.py` a las cifras que se muestran, con
un filtro opcional por los cursos de un nodo académico (FUN-143). Funciones PURAS: el mismo detalle da siempre el mismo resumen.

El detalle (`m13_avance_alumno.detalle`) sólo lleva referencias y cifras, jamás un título:
  clases       {sesion_id, curso_ref, finalizada_en, asistio, recibidas, entregadas, puntos, puntos_maximos}
  evaluaciones {asignacion_id, curso_ref, estado_asignacion, presento, sin_presentar, estado_intento, estado_simple, estado, publicada, presentacion, puntaje_aplicable, ultima_en}
  estudios     {asignacion_id, curso_ref, estado, avance_pct, vencida, completada, ultima_en}
Este archivo no importa Django.
"""
from __future__ import annotations

from . import catalogos as cat
from .texto import clave_de_orden
from .metricas import MetricasDeAlumno, a_decimal, como_numero, motivos_de_atencion, porcentaje, promedio, redondear


def _filtrar(items: list[dict], curso_refs: set[str] | None) -> list[dict]:
    return items if curso_refs is None else [i for i in items if i.get("curso_ref") in curso_refs]


def resumir(detalle: dict, curso_refs: set[str] | None = None) -> dict:
    """Las cifras de un alumno a partir de su detalle, opcionalmente sólo de los cursos dados."""
    clases = _filtrar(detalle.get("clases") or [], curso_refs)
    evaluaciones = _filtrar(detalle.get("evaluaciones") or [], curso_refs)
    estudios = _filtrar(detalle.get("estudios") or [], curso_refs)
    asistidas = [c for c in clases if c["asistio"]]
    recibidas = sum(int(c["recibidas"]) for c in asistidas)
    entregadas = sum(int(c["entregadas"]) for c in asistidas)
    puntos = sum((a_decimal(c["puntos"]) or 0 for c in asistidas), a_decimal(0))
    maximos = sum((a_decimal(c["puntos_maximos"]) or 0 for c in asistidas), a_decimal(0))
    sin_presentar = sum(1 for e in evaluaciones if e["sin_presentar"])
    vencidos = sum(1 for s in estudios if s["vencida"])
    ultimas = [c["finalizada_en"] for c in asistidas] + [e["ultima_en"] for e in evaluaciones if e.get("ultima_en")] + [s["ultima_en"] for s in estudios if s.get("ultima_en")]
    metricas = MetricasDeAlumno(clases_total=len(clases), clases_asistidas=len(asistidas), actividades_recibidas=recibidas, actividades_entregadas=entregadas,
                                evaluaciones_sin_presentar=sin_presentar, estudios_vencidos=vencidos)
    return {
        "clases_total": len(clases), "clases_asistidas": len(asistidas), "porcentaje_asistencia": porcentaje(len(asistidas), len(clases)),
        "actividades_recibidas": recibidas, "actividades_entregadas": entregadas, "porcentaje_participacion": porcentaje(entregadas, recibidas),
        "porcentaje_aciertos": porcentaje(puntos, maximos) if maximos > 0 else None,
        "evaluaciones_total": len(evaluaciones), "evaluaciones_presentadas": sum(1 for e in evaluaciones if e["presento"]), "evaluaciones_sin_presentar": sin_presentar,
        "estudios_total": len(estudios), "estudios_completados": sum(1 for s in estudios if s["completada"]), "estudios_vencidos": vencidos,
        "avance_estudio": promedio(s["avance_pct"] for s in estudios), "ultima_actividad_en": max((int(u) for u in ultimas if u), default=None),
        "atencion": motivos_de_atencion(metricas)}


def necesita_atencion(resumen: dict) -> bool:
    return bool(resumen["atencion"])


def motivo_de_atencion(resumen: dict) -> str:
    """El motivo de UNA línea: el más urgente; si hay más, se dice cuántos."""
    motivos = resumen["atencion"]
    if not motivos:
        return ""
    extra = len(motivos) - 1
    return motivos[0]["texto"] + (f" (y {extra} más)" if extra else "")


def ordenar_por_atencion(filas: list[dict]) -> list[dict]:
    """Primero quienes necesitan atención (los que más motivos acumulan, antes), y dentro de cada bloque por nombre: la pantalla de «Su grupo» pone a esos alumnos arriba."""
    return sorted(filas, key=lambda f: (0 if f["atencion"] else 1, -len(f["atencion"]), clave_de_orden(f.get("alumno")), f["alumno_id"]))


def promedio_de(filas: list[dict], clave: str):
    """Media simple de los alumnos que tienen la cifra `clave` (sin cifra no cuenta; sin ninguna, None)."""
    return promedio(f[clave] for f in filas)


def resumen_para_pantalla(r: dict) -> dict:
    """El resumen como viaja en el JSON: `Decimal` → número."""
    salida = dict(r)
    for clave in ("porcentaje_asistencia", "porcentaje_participacion", "porcentaje_aciertos", "avance_estudio"):
        salida[clave] = como_numero(r[clave])
    return salida
