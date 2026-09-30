"""
Lo que ven el alumno y el profesor: la forma de cada respuesta del contrato (`spec-driven/04-modo-estudio/02-modelo-y-api.md`, §4),
construida con funciones puras sobre los dicts de los repositorios. Ningún archivo de esta carpeta importa Django.

Ninguna de estas formas lleva contenido del curso ni claves de respuesta: son estado, referencias y rótulos de evidencia. Tampoco
publican una nota (DEC-032): `avance_pct` es cuántos bloques se atendieron; los aciertos de la práctica son un conteo.
"""
from __future__ import annotations

from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import paquete as paquete_dom
from ..dominio import plazo as plazo_dom
from ..dominio import practica as practica_dom


def _numero(valor) -> float:
    return float(valor) if valor is not None else 0.0


# --------------------------------------------------------------------------- lo que ve el alumno

def curso_de(asignacion: dict) -> dict:
    return {"fuente": asignacion["fuente_curso"] or None, "curso_ref": asignacion["curso_ref"],
            "version": asignacion["curso_version"] or None, "titulo": asignacion["curso_rotulo"] or None}


def bloques_del_alumno(asignacion: dict, tarea: dict | None) -> list[dict]:
    """La estructura de bloques con lo que el alumno ya atendió. Las referencias de medios no salen: son del servidor."""
    vistos = set(tarea["bloques_vistos"]) if tarea else set()
    return [{"ref": b["ref"], "indice": b["indice"], "tipo": b["tipo"], "titulo": b["titulo"], "obligatorio": b.get("obligatorio", True),
             "atendido": b["ref"] in vistos, "objeto_ref": b.get("objeto_ref") or None} for b in asignacion["bloques"]]


def ultimo_bloque(asignacion: dict, tarea: dict | None) -> dict | None:
    """El último bloque que tocó el alumno, con la posición dentro de él (`Actividad 4 · 03:28`)."""
    if not tarea or not tarea["ultimo_bloque_ref"]:
        return None
    bloque = bloques_dom.bloque_de(asignacion["bloques"], tarea["ultimo_bloque_ref"])
    if bloque is None:
        return None
    return {"ref": bloque["ref"], "indice": bloque["indice"], "titulo": bloque["titulo"], "tipo": bloque["tipo"],
            "posicion_seg": tarea["posicion_seg"]}


def reanudar(asignacion: dict, tarea: dict | None) -> dict:
    """Desde dónde sigue el alumno (FUN-088): `{bloque_ref, indice, posicion_seg, puede}`."""
    punto = None
    if tarea is not None and tarea["estado"] != cat.COMPLETADA:
        punto = bloques_dom.punto_de_reanudacion(asignacion["bloques"], tarea["bloques_vistos"], tarea["ultimo_bloque_ref"],
                                                 tarea["posicion_seg"])
    return {"bloque_ref": punto["ref"] if punto else None, "indice": punto["indice"] if punto else None,
            "posicion_seg": punto["posicion_seg"] if punto else None, "puede": punto is not None}


def tarea(asignacion: dict, tarea_: dict | None, ahora: int) -> dict | None:
    """El estado de la tarea del alumno; None cuando aún no la ha tocado (equivale a `pendiente`, 0 %)."""
    if tarea_ is None:
        return None
    bloques = asignacion["bloques"]
    vistos = tarea_["bloques_vistos"]
    return {
        "estado": tarea_["estado"],
        "vencida": plazo_dom.vencida(asignacion["fecha_limite"], tarea_["estado"], ahora),
        "fuera_de_plazo": bool(tarea_["fuera_de_plazo"]),
        "avance_pct": _numero(tarea_["avance_pct"]),
        "bloques_total": len(bloques),
        "bloques_obligatorios": len(bloques_dom.obligatorios(bloques)),
        "bloques_atendidos": len(bloques_dom.atendidos(bloques, vistos)),
        "ultimo_bloque": ultimo_bloque(asignacion, tarea_),
        "puede_reanudar": reanudar(asignacion, tarea_)["puede"],
        "abierta_en": tarea_["abierta_en"],
        "ultimo_avance_en": tarea_["ultimo_avance_en"],
        "completada_en": tarea_["completada_en"],
    }


def practica_resumen(asignacion: dict, tarea_: dict | None, en_curso: bool) -> dict:
    """La práctica que se ofrece y cómo va (intentos, mejor y última en aciertos). Nunca se llama nota ni evaluación."""
    practica = asignacion.get("practica")
    if not practica:
        return {"disponible": False, "objeto_ref": None, "titulo": None, "total_preguntas": 0, "intentos": 0,
                "mejor_correctas": None, "ultima_correctas": None, "en_curso": False}
    return {
        "disponible": True, "objeto_ref": practica["objeto_ref"], "titulo": practica["titulo"] or None,
        "total_preguntas": int((tarea_ or {}).get("practica_total") or practica["total_preguntas"] or 0),
        "intentos": int((tarea_ or {}).get("practica_intentos") or 0),
        "mejor_correctas": (tarea_ or {}).get("practica_mejor"), "ultima_correctas": (tarea_ or {}).get("practica_ultima"),
        "en_curso": bool(en_curso),
    }


def paquete_resumen(paquete: dict | None, asignacion: dict) -> dict | None:
    """El paquete del aparato que pregunta (o None)."""
    if paquete is None:
        return None
    return {"id": paquete["id"], "estado": paquete["estado"], "motivo": paquete["motivo"], "bytes_total": paquete["bytes_total"],
            "bytes_estimados": asignacion["bytes_estimados"], "vigente_hasta": paquete["vigente_hasta"], "huella": paquete["huella"] or None}


def descarga(asignacion: dict, del_alumno: bool, ajeno: bool = False) -> dict:
    """¿Puede este aparato llevarse el material? Sólo uno asignado a la persona y sólo si el profesor lo permite (BR-054). Uno compartido dice
    `dispositivo_compartido`; el asignado a OTRA persona, `dispositivo_ajeno` (D-15: en él se estudia en línea, pero no se descarga)."""
    if not del_alumno:
        return {"permitida": False, "motivo": cat.DISPOSITIVO_AJENO if ajeno else cat.DISPOSITIVO_COMPARTIDO}
    if not asignacion["paquete_permitido"]:
        return {"permitida": False, "motivo": cat.PAQUETE_NO_PERMITIDO}
    return {"permitida": True, "motivo": ""}


def asignacion_alumno(asignacion: dict, *, tarea_: dict | None, en_curso: bool, paquete: dict | None, del_alumno: bool, ahora: int,
                      con_bloques: bool = True, ajeno: bool = False) -> dict:
    """`AsignacionAlumno` (§4.2): una asignación tal como la ve el alumno en un aparato concreto. No lee la biblioteca: usa los
    rótulos y la estructura guardados, así que funciona con la biblioteca cerrada."""
    return {
        "id": asignacion["id"], "titulo": asignacion["titulo"], "consigna": asignacion["consigna"],
        "descripcion": asignacion["descripcion"], "asignatura": asignacion["asignatura_rotulo"], "unidad": asignacion["unidad_rotulo"],
        "curso": curso_de(asignacion), "leccion_ref": asignacion["leccion_ref"],
        "fecha_limite": asignacion["fecha_limite"], "plazo": asignacion["plazo"], "gracia_ms": asignacion["gracia_ms"],
        "estado_asignacion": asignacion["estado"], "profesor": asignacion["profesor_rotulo"] or None,
        "asignada_en": asignacion["creada_en"],
        "tarea": tarea(asignacion, tarea_, ahora),
        "practica": practica_resumen(asignacion, tarea_, en_curso),
        "evaluacion": asignacion.get("evaluacion") or None,
        "paquete": paquete_resumen(paquete, asignacion),
        "descarga": descarga(asignacion, del_alumno, ajeno),
        "bloques": bloques_del_alumno(asignacion, tarea_) if con_bloques else None,
    }


def asignacion_estable(asignacion: dict) -> dict:
    """Lo que el manifiesto de un paquete dice de la asignación: sólo lo ESTABLE (estructura y rótulos), nunca el avance, el estado
    ni las fechas. Si el profesor mueve una fecha o cierra la asignación, la huella del paquete no cambia."""
    return {
        "id": asignacion["id"], "titulo": asignacion["titulo"], "descripcion": asignacion["descripcion"],
        "asignatura": asignacion["asignatura_rotulo"], "unidad": asignacion["unidad_rotulo"],
        "curso": curso_de(asignacion), "leccion_ref": asignacion["leccion_ref"],
        "bloques": [{"ref": b["ref"], "indice": b["indice"], "tipo": b["tipo"], "titulo": b["titulo"],
                     "obligatorio": b.get("obligatorio", True), "objeto_ref": b.get("objeto_ref") or None} for b in asignacion["bloques"]],
        "practica": ({"disponible": True, **asignacion["practica"]} if asignacion.get("practica") else None),
        "evaluacion": asignacion.get("evaluacion") or None,
    }


# --------------------------------------------------------------------------------- la práctica

def practica_abierta(practica: dict, asignacion_practica: dict | None, reanudada: bool) -> dict:
    """`practica` de `POST /lecciones/{id}/practica/`: `{id, numero, estado, objeto_ref, titulo, total_preguntas,
    respondidas{pregunta_ref: {respuesta, veredicto}}, aciertos, iniciada_en, reanudada}`."""
    return {
        "id": practica["id"], "numero": practica["numero"], "estado": practica["estado"], "objeto_ref": practica["objeto_ref"],
        "titulo": practica["objeto_rotulo"] or (asignacion_practica or {}).get("titulo") or None,
        "total_preguntas": practica["total_preguntas"], "respondidas": practica_dom.respondidas_del_alumno(practica["respuestas"]),
        "aciertos": practica["aciertos"], "iniciada_en": practica["iniciada_en"], "reanudada": bool(reanudada),
    }


def practica_resumen_corto(practica: dict) -> dict:
    """`practica` de las respuestas y del cierre: `{id, estado, respondidas, aciertos, total_preguntas, sin_calificar}`. Lleva además
    `numero`, `objeto_ref` y `terminada_en`, que el aparato guarda para reanudar y para el resumen de la tarea."""
    return {"id": practica["id"], "estado": practica["estado"], "numero": practica["numero"], "objeto_ref": practica["objeto_ref"],
            **practica_dom.resumen(practica["respuestas"], practica["total_preguntas"]), "terminada_en": practica["terminada_en"]}


# ---------------------------------------------------------------------------------- el paquete

def paquete(p: dict, ahora: int) -> dict:
    """`paquete` (§4.4): con `archivos[]` y `no_incluidos[]`, la huella y la vigencia. Sólo metadatos, nunca contenido."""
    return {
        "id": p["id"], "asignacion_id": p["asignacion_id"], "dispositivo_id": p["dispositivo_id"], "estado": p["estado"],
        "motivo": p["motivo"], "curso_version": p["curso_version"] or None, "bytes_total": p["bytes_total"],
        "huella": p["huella"] or None, "vigente_hasta": p["vigente_hasta"], "solicitado_en": p["solicitado_en"],
        "disponible_en": p["disponible_en"], "archivos": list(p["archivos"]), "no_incluidos": list(p["no_incluidos"]),
        "servidor_en": ahora,
    }


def respuesta_de_paquete(p: dict, ahora: int) -> dict:
    """El paquete de `POST /paquetes/`, `GET /paquetes/{id}/` y `confirmar`: `{paquete}` (§4.4). Los mismos campos viajan también al
    nivel superior, así quien lea el paquete «pelado» y quien lea `{paquete}` reciben lo mismo."""
    cuerpo = paquete(p, ahora)
    return {**cuerpo, "paquete": cuerpo}


# ------------------------------------------------------------------------- lo que ve el profesor

def decision_pendiente(fila: dict) -> dict:
    """Un envío que espera al profesor (BR-074): la clave `(emisor_id, secuencia)` con la que se resuelve, y por qué espera."""
    return {"emisor_id": fila["emisor_id"], "secuencia": fila["secuencia"], "tipo": fila["tipo"], "motivo": fila["motivo"],
            "ocurrido_en": fila["ocurrido_en"], "recibido_en": fila["recibido_en"]}


def fila_de_alumno(asignacion: dict, alumno: dict, tarea_: dict | None, paquetes: list[dict], dispositivo: dict | None,
                   decisiones: list[dict], ahora: int) -> dict:
    """Una fila de «quién completó» (CAP-051): un destinatario con o sin tarea. `decisiones` son sus envíos pendientes de decisión
    (filas del libro de sincronización); `pendientes_decision` es cuántos son."""
    bloques = asignacion["bloques"]
    estado = tarea_["estado"] if tarea_ else cat.PENDIENTE
    total_practica = int((asignacion.get("practica") or {}).get("total_preguntas") or 0)
    estado_paquete = paquete_dom.resumen_de_estado(paquetes)
    return {
        "alumno_id": alumno["id"], "rotulo": alumno["rotulo"], "estado": estado,
        "vencida": plazo_dom.vencida(asignacion["fecha_limite"], estado, ahora),
        "fuera_de_plazo": bool(tarea_ and tarea_["fuera_de_plazo"]),
        "avance_pct": _numero(tarea_["avance_pct"]) if tarea_ else 0.0,
        "bloques_atendidos": len(bloques_dom.atendidos(bloques, tarea_["bloques_vistos"])) if tarea_ else 0,
        "bloques_total": len(bloques),
        "ultimo_avance_en": tarea_["ultimo_avance_en"] if tarea_ else None,
        "completada_en": tarea_["completada_en"] if tarea_ else None,
        "practica": {"intentos": int(tarea_["practica_intentos"]) if tarea_ else 0,
                     "mejor_correctas": tarea_["practica_mejor"] if tarea_ else None,
                     "total": int(tarea_["practica_total"] or total_practica) if tarea_ else total_practica},
        "paquete": {"estado": estado_paquete} if estado_paquete else None,
        "dispositivo": ({"id": dispositivo["id"], "nombre": dispositivo["nombre"], "perfil": dispositivo.get("perfil") or cat.COMPARTIDO}
                        if dispositivo else None),
        "pendientes_decision": len(decisiones),
        "decisiones": [decision_pendiente(f) for f in decisiones],
    }


def asignacion_docente(asignacion: dict, *, totales: dict, alumnos: list[dict] | None = None) -> dict:
    """`AsignacionDocente` (§4.6): la asignación con sus totales y, en el detalle, la tabla de alumnos."""
    salida = {
        "id": asignacion["id"], "titulo": asignacion["titulo"], "descripcion": asignacion["descripcion"],
        "consigna": asignacion["consigna"], "asignatura": asignacion["asignatura_rotulo"], "unidad": asignacion["unidad_rotulo"],
        "grupo_id": asignacion["grupo_id"] or None, "grupo_rotulo": asignacion["grupo_rotulo"] or None,
        "curso": curso_de(asignacion), "leccion_ref": asignacion["leccion_ref"], "leccion_rotulo": asignacion["leccion_rotulo"],
        "fecha_limite": asignacion["fecha_limite"], "plazo": asignacion["plazo"], "gracia_ms": asignacion["gracia_ms"],
        "estado": asignacion["estado"], "alcance": asignacion["alcance"], "paquete_permitido": asignacion["paquete_permitido"],
        "profesor": asignacion["profesor_rotulo"] or None, "bytes_estimados": asignacion["bytes_estimados"],
        "bloques_total": len(asignacion["bloques"]), "practica": asignacion.get("practica") or None,
        "evaluacion": asignacion.get("evaluacion") or None,
        "creada_en": asignacion["creada_en"], "cerrada_en": asignacion["cerrada_en"], **totales,
    }
    if alumnos is not None:
        salida["alumnos"] = alumnos
    return salida
