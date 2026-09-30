"""
Los bloques de una lección y el avance del alumno sobre ellos (D-4, FUN-087). Dominio puro: no importa Django ni sabe de HTTP.

Un «bloque» es la unidad de avance de una lección, en el orden en que se ve: cada lámina de una presentación (`lecture`), cada página
de una lectura (`explanation`), cada laboratorio (`simulation_lab`) y cada actividad (`activity`, la práctica). El examen NO es bloque:
es evaluación formal y queda fuera (BR-055). Todos los bloques son obligatorios mientras el esquema de curso 1.0 no tenga una marca
`required` (Q-66).

«Atendido» significa: lámina o página VISTA; laboratorio ABIERTO; práctica TERMINADA al menos una vez (no se exige nota). Una lección
se completa cuando todos los bloques obligatorios fueron atendidos, no cuando el alumno sale de la pantalla.

La estructura se guarda como REFERENCIAS (artículo 14: el contenido no se guarda): cada bloque lleva un `ref` estable
(`"{objeto_ref}:{unidad_ref}"` para láminas y páginas, `objeto_ref` para laboratorios y práctica) y el rótulo que se vio al asignar.
Lleva además las referencias de los medios que usa (`medios`): así se sabe qué medios pertenecen a la lección sin volver a leerla.
"""
from __future__ import annotations

from collections.abc import Iterable

from . import catalogos as cat
from .errores import DatosInvalidos

_OBJETO_LAMINAS, _OBJETO_PAGINAS, _OBJETO_LABORATORIO, _OBJETO_ACTIVIDAD, _OBJETO_EXAMEN = (
    "lecture", "explanation", "simulation_lab", "activity", "exam")


# ------------------------------------------------------------------ estructura de la lección

def _unicos(refs: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(r for r in refs if r))


def _medios_de_unidad(unidad: dict) -> list[str]:
    """Las referencias de medio de una lámina o página: los bloques de imagen, video, audio y pdf."""
    return _unicos(str(b.get("media_ref") or "") for b in unidad.get("bloques") or [] if isinstance(b, dict))


def _medios_de_pregunta(pregunta: dict) -> list[str]:
    """Imágenes, video, audio o pdf que acompañan al enunciado, y las imágenes de opciones, parejas y elementos."""
    refs = [str(m.get("media_ref") or "") for m in pregunta.get("medios") or [] if isinstance(m, dict)]
    for coleccion in ("opciones", "izquierda", "derecha", "elementos"):
        refs += [str(i.get("media_ref") or "") for i in pregunta.get(coleccion) or [] if isinstance(i, dict)]
    return _unicos(refs)


def _bloque(ref: str, objeto: dict, tipo: str, titulo: str, medios: list[str]) -> dict:
    return {"ref": ref, "indice": 0, "objeto_ref": str(objeto.get("objeto_ref") or ""), "tipo": tipo,
            "titulo": titulo, "obligatorio": True, "medios": _unicos(medios)}


def bloques_de_leccion(leccion: dict) -> list[dict]:
    """La estructura de bloques de una lección de la vista de aula (sin claves), en el orden en que se ve.
    Cada bloque: `{ref, indice (desde 1), objeto_ref, tipo, titulo, obligatorio, medios}`."""
    bloques: list[dict] = []
    for objeto in leccion.get("objetos") or []:
        tipo = objeto.get("tipo")
        objeto_ref = str(objeto.get("objeto_ref") or "")
        titulo_objeto = str(objeto.get("titulo") or "")
        if tipo in (_OBJETO_LAMINAS, _OBJETO_PAGINAS):
            unidades = objeto.get("laminas" if tipo == _OBJETO_LAMINAS else "paginas") or []
            tipo_bloque = cat.LAMINA if tipo == _OBJETO_LAMINAS else cat.PAGINA
            for numero, unidad in enumerate(unidades, start=1):
                titulo = str(unidad.get("titulo") or "").strip() or f"{titulo_objeto} · {numero}"
                bloques.append(_bloque(f"{objeto_ref}:{unidad.get('unidad_ref')}", objeto, tipo_bloque, titulo, _medios_de_unidad(unidad)))
        elif tipo == _OBJETO_LABORATORIO:
            simulacion = objeto.get("simulacion") or {}
            bloques.append(_bloque(objeto_ref, objeto, cat.LABORATORIO, titulo_objeto, [str(simulacion.get("media_ref") or "")]))
        elif tipo == _OBJETO_ACTIVIDAD:
            medios = [m for p in objeto.get("preguntas") or [] for m in _medios_de_pregunta(p)]
            bloques.append(_bloque(objeto_ref, objeto, cat.PRACTICA, titulo_objeto, medios))
        # el examen (y cualquier objeto que este LMS no conozca) no es un bloque de estudio
    for indice, bloque in enumerate(bloques, start=1):
        bloque["indice"] = indice
    return bloques


def practica_de_leccion(leccion: dict) -> dict | None:
    """La primera actividad de la lección: la práctica que se ofrece. `{objeto_ref, titulo, total_preguntas}` o None."""
    for objeto in leccion.get("objetos") or []:
        if objeto.get("tipo") == _OBJETO_ACTIVIDAD:
            return {"objeto_ref": str(objeto.get("objeto_ref") or ""), "titulo": str(objeto.get("titulo") or ""),
                    "total_preguntas": len(objeto.get("preguntas") or [])}
    return None


def evaluacion_de_leccion(leccion: dict) -> dict | None:
    """El primer examen de la lección: sólo informativo, nunca se practica aquí (BR-055). `{objeto_ref, titulo}` o None."""
    for objeto in leccion.get("objetos") or []:
        if objeto.get("tipo") == _OBJETO_EXAMEN:
            return {"objeto_ref": str(objeto.get("objeto_ref") or ""), "titulo": str(objeto.get("titulo") or "")}
    return None


def medios_de_leccion(leccion: dict) -> list[str]:
    """Todos los medios que usa la lección (láminas, páginas, laboratorios y práctica), en el orden en que aparecen."""
    return _unicos(m for b in bloques_de_leccion(leccion) for m in b["medios"])


def medios_de_bloques(bloques: Iterable[dict]) -> set[str]:
    """Los medios que pertenecen a la lección asignada, según la estructura guardada: lo único que se sirve por la asignación."""
    return {m for b in bloques for m in b.get("medios") or []}


# ------------------------------------------------------------------------- avance del alumno

def bloque_de(bloques: Iterable[dict], ref: str) -> dict | None:
    return next((b for b in bloques if b["ref"] == ref), None)


def obligatorios(bloques: Iterable[dict]) -> list[dict]:
    return [b for b in bloques if b.get("obligatorio", True)]


def atendidos(bloques: Iterable[dict], vistos: Iterable[str]) -> list[dict]:
    """Los bloques de la estructura que el alumno ya atendió (los `vistos` que ya no existen en la lección no cuentan)."""
    vistos = set(vistos)
    return [b for b in bloques if b["ref"] in vistos]


def avance_pct(bloques: Iterable[dict], vistos: Iterable[str]) -> float:
    """Obligatorios atendidos / obligatorios × 100. NO es una nota (DEC-032)."""
    obligatorias = obligatorios(bloques)
    if not obligatorias:
        return 0.0
    vistos = set(vistos)
    hechos = sum(1 for b in obligatorias if b["ref"] in vistos)
    return round(100.0 * hechos / len(obligatorias), 2)


def faltan(bloques: Iterable[dict], vistos: Iterable[str]) -> list[dict]:
    """Los obligatorios sin atender, para `409 bloques_pendientes`: `[{ref, indice, titulo}]`."""
    vistos = set(vistos)
    return [{"ref": b["ref"], "indice": b["indice"], "titulo": b["titulo"]} for b in obligatorios(bloques) if b["ref"] not in vistos]


def esta_completa(bloques: Iterable[dict], vistos: Iterable[str]) -> bool:
    """Todos los obligatorios atendidos (FUN-087)."""
    return not faltan(bloques, vistos)


def clasificar_refs(bloques: Iterable[dict], refs: Iterable[str]) -> tuple[list[str], list[str]]:
    """(conocidos, desconocidos) de las referencias que declara el aparato, sin repetir y en el orden en que llegaron."""
    existentes = {b["ref"] for b in bloques}
    unicos = _unicos(str(r) for r in refs)
    return [r for r in unicos if r in existentes], [r for r in unicos if r not in existentes]


def sumar_vistos(vistos: list[str], nuevos: Iterable[str]) -> list[str]:
    """Progreso MONÓTONO: nunca se desatiende un bloque; sólo se suma."""
    return list(dict.fromkeys([*vistos, *nuevos]))


def conservar_vistos(vistos: Iterable[str], bloques_nuevos: Iterable[dict]) -> list[str]:
    """La lección cambió de versión: se conserva lo ya visto que todavía existe (`vistos` sólo guarda referencias que existen)."""
    existentes = {b["ref"] for b in bloques_nuevos}
    return [r for r in dict.fromkeys(vistos) if r in existentes]


def punto_de_reanudacion(bloques: list[dict], vistos: Iterable[str], ultimo_ref: str, posicion_seg: int | None) -> dict | None:
    """Desde dónde sigue el alumno («Actividad 4 · 03:28»): el último bloque que tocó; si no dejó marca pero ya atendió algo,
    el primer bloque sin atender. `{ref, indice, titulo, tipo, posicion_seg}` o None si no hay nada que reanudar."""
    vistos = set(vistos)
    bloque = bloque_de(bloques, ultimo_ref) if ultimo_ref else None
    if bloque is not None:
        return {"ref": bloque["ref"], "indice": bloque["indice"], "titulo": bloque["titulo"], "tipo": bloque["tipo"],
                "posicion_seg": posicion_seg}
    if any(b["ref"] in vistos for b in bloques):
        siguiente = next((b for b in bloques if b["ref"] not in vistos), None)
        if siguiente is not None:
            return {"ref": siguiente["ref"], "indice": siguiente["indice"], "titulo": siguiente["titulo"], "tipo": siguiente["tipo"],
                    "posicion_seg": None}
    return None


def validar_posicion(valor) -> int | None:
    """`posicion_seg`: segundos desde el inicio del bloque; un entero ≥ 0 o ausente."""
    if valor in (None, ""):
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or int(valor) != valor or valor < 0:
        raise DatosInvalidos("`posicion_seg` debe ser un entero de segundos mayor o igual que 0.", posicion_seg=valor)
    return int(valor)
