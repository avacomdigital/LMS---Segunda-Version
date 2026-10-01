"""
Lo que MOD-010 necesita de un curso para evaluarlo y que la fuente de cursos del aula no ofrece: el esquema CON los objetos de modo `exam`, el `pool` de un
examen y las preguntas de UN alumno, sin claves (rutas `GET /v2/courses/{id}`, `/exams/{oid}/pool` y `/exams/{oid}/questions` del contrato 2).

Vive aquí a propósito: la capa de biblioteca (`biblioteca/`) y las fuentes de cursos de `classroom_engine` NO se tocan para evaluar. Este módulo sólo
LEE de ellas: con la biblioteca le pregunta a su cliente tal como está (`biblioteca.contenido_v2`) y, con la fuente de ejemplo, al manifiesto que esa
fuente ya sirve. Nada se guarda: cada llamada vuelve a preguntar (artículo 14).
"""
from __future__ import annotations

import random

from biblioteca import contenido_v2 as v2
from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible
from classroom_engine.dominio import curso as curso_aula

from ..dominio import errores as e10

RUTA_EXAMEN_POOL = "/v2/courses/{curso}/exams/{objeto}/pool"
RUTA_EXAMEN_PREGUNTAS = "/v2/courses/{curso}/exams/{objeto}/questions"
SUGERENCIA_INDICE = "La biblioteca está reconstruyendo su índice; vuelve a intentarlo en unos segundos."

CODIGOS_POLITICA = ("policy_disabled", "disabled_by_policy")
CODIGOS_NO_ENCONTRADO = ("course_not_found", "version_not_available", "not_found", "lesson_not_found", "object_not_found", "question_not_found")


def _es_biblioteca(origen) -> bool:
    return getattr(origen, "nombre", "") == "biblioteca"


def _traducir(error: Exception, *, curso_ref: str = "") -> Exception:
    """Un fallo de la biblioteca → su equivalente en MOD-010 (los mismos significados que ya tienen para el aula)."""
    if isinstance(error, BibliotecaNoDisponible):
        return e10.FuenteNoDisponible(error.motivo, sugerencia=error.sugerencia)
    if not isinstance(error, BibliotecaError):
        return error
    codigo, estado, detalle = error.codigo, error.estado, error.detalle
    extra = {"codigo_fuente": codigo} if codigo else {}
    if codigo == "index_rebuilding" or estado == 503:
        return e10.FuenteNoDisponible(detalle or "La biblioteca está reconstruyendo su índice.", sugerencia=SUGERENCIA_INDICE, **extra)
    if codigo in CODIGOS_POLITICA or codigo in CODIGOS_NO_ENCONTRADO or estado == 404:
        return e10.NoEncontrado(detalle, curso_ref=curso_ref, **extra)
    if codigo in ("invalid_parameter", "invalid_response") or estado in (400, 422):
        return e10.DatosInvalidos(detalle, **extra)
    return e10.FuenteError(detalle, estado_biblioteca=estado, **extra)


def _preguntar(curso_ref: str, ruta: str, consulta: dict | None = None):
    try:
        return v2._pedir("GET", ruta, consulta=consulta)
    except (BibliotecaNoDisponible, BibliotecaError) as error:
        raise _traducir(error, curso_ref=curso_ref) from error


# ------------------------------------------------------------------------------------------------------------ lo que sirve la fuente
def esquema(origen, curso_ref: str) -> dict:
    """El esquema LIGERO del curso para asignar un examen: metadatos, lecciones con resúmenes de objeto —también los de modo `exam`— y la lista de
    medios. Con la biblioteca se pide con `mode=exam` (con `mode=class` el examen no aparece)."""
    if _es_biblioteca(origen):
        try:
            datos = v2.esquema_curso(curso_ref, modo="exam", perfil="student")
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            raise _traducir(error, curso_ref=curso_ref) from error
        if not isinstance(datos, dict):
            raise e10.FuenteError("La biblioteca no devolvió el esquema del curso.", curso_ref=curso_ref)
        return datos
    m = origen.curso(curso_ref)
    lecciones = [{"id": l.get("id"), "title": l.get("title"),
                  "objects": [{"id": o.get("id"), "type": o.get("type"), "title": o.get("title"), "modes": o.get("modes"),
                               "questionCount": len(o.get("questions") or [])} for o in l.get("objects") or []]}
                 for l in m.get("lessons") or []]
    return {"courseId": m.get("id"), "id": m.get("id"), "version": m.get("version"), "title": m.get("title"), "lessons": lecciones,
            "media": list(m.get("media") or [])}


def _examen_del_manifiesto(origen, curso_ref: str, objeto_ref: str) -> tuple[dict, dict]:
    manifiesto = origen.curso(curso_ref)
    for leccion in manifiesto.get("lessons") or []:
        for objeto in leccion.get("objects") or []:
            if str(objeto.get("id")) == objeto_ref and objeto.get("type") == "exam":
                return manifiesto, objeto
    raise e10.NoEncontrado(f"El examen «{objeto_ref}» no está en el manifiesto de ejemplo.", curso_ref=curso_ref, objeto_ref=objeto_ref)


def examen_pool(origen, curso_ref: str, objeto_ref: str) -> dict:
    """`ExamPool`: `{courseId, version, objectId, settings, questions[{questionId, type, topicRef, difficulty, estimatedSec, points}]}`. Con ellos se
    arma el examen de cada alumno. Sin enunciados ni claves."""
    if _es_biblioteca(origen):
        return _preguntar(curso_ref, RUTA_EXAMEN_POOL.format(curso=v2._ref(curso_ref), objeto=v2._ref(objeto_ref)))
    manifiesto, examen = _examen_del_manifiesto(origen, curso_ref, objeto_ref)
    return {"courseId": manifiesto.get("id"), "version": manifiesto.get("version"), "objectId": examen.get("id"),
            "settings": dict(examen.get("settings") or {}),
            "questions": [{"questionId": q.get("id"), "type": q.get("type"), "topicRef": q.get("topicRef"), "difficulty": q.get("difficulty"),
                           "estimatedSec": q.get("estimatedSec"), "points": q.get("points")} for q in examen.get("questions") or []]}


def examen_preguntas(origen, curso_ref: str, objeto_ref: str, ids: list[str], semilla: str | None = None) -> dict:
    """`ExamQuestions`: `{courseId, version, objectId, title, instructions, questions[]}` con SÓLO las preguntas pedidas, sin claves, en el orden de
    `ids` y con opciones y elementos barajados de forma reproducible por `semilla` (como lo hace la biblioteca)."""
    if _es_biblioteca(origen):
        return _preguntar(curso_ref, RUTA_EXAMEN_PREGUNTAS.format(curso=v2._ref(curso_ref), objeto=v2._ref(objeto_ref)),
                          {"ids": ",".join(str(i) for i in ids), "seed": semilla})
    manifiesto, examen = _examen_del_manifiesto(origen, curso_ref, objeto_ref)
    por_id = {str(q.get("id")): q for q in examen.get("questions") or []}
    faltan = [i for i in ids if i not in por_id]
    if faltan:
        raise e10.NoEncontrado(f"Preguntas que no están en el examen: {', '.join(faltan)}.", curso_ref=curso_ref, pregunta_ref=",".join(faltan))
    salida = []
    for ref in ids:
        pregunta = curso_aula.sin_claves({k: v for k, v in por_id[ref].items() if k != "teacherNotes"})
        for clave in ("options", "right", "items"):
            lista = pregunta.get(clave)
            if isinstance(lista, list) and len(lista) > 1:
                random.Random(f"{semilla or ''}|{ref}|{clave}").shuffle(lista)
        salida.append(pregunta)
    return {"courseId": manifiesto.get("id"), "version": manifiesto.get("version"), "objectId": examen.get("id"), "title": examen.get("title"),
            "instructions": examen.get("instructions"), "questions": salida}


# ------------------------------------------------------------------------------------------------------------ lo que ve UN alumno
def preguntas_de_examen(preguntas: list[dict], medios: list[dict], url_medio) -> list[dict]:
    """Las preguntas de UN alumno, tal como las entrega `examen_preguntas` —ya sin claves—, en la vista de aula que los controles de Student ya saben
    pintar. Cada alumno las ve en su propio orden porque la fuente ya las barajó con su semilla. Defensa en profundidad: un barrido final vuelve a
    quitar cualquier clave de corrección (artículo 14.5)."""
    catalogo = {x["media_ref"]: x for x in (curso_aula._medio(m, url_medio) for m in medios or [] if isinstance(m, dict))}
    return [curso_aula.sin_claves(curso_aula._pregunta(p, catalogo, url_medio, "estudiante")) for p in preguntas or [] if isinstance(p, dict)]
