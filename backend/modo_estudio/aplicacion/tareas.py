"""
Las reglas de la tarea del alumno, compartidas por lo que ocurre en línea (lecciones, práctica) y por lo que llega sin red (sincronización):
registrar bloques atendidos, completar la lección, terminar una práctica y refrescar la estructura cuando cambia la versión del curso.
Reciben la unidad de trabajo del caso de uso que las llama: se ejecutan dentro de SU transacción, sin abrir otra. Ninguna importa Django.

Reglas del Documento Maestro que se cumplen aquí:
  - FUN-087: la lección se completa cuando TODOS los bloques obligatorios fueron atendidos (409 `bloques_pendientes`), no cuando el alumno
    sale de la pantalla. El avance se registra por bloques, monotónico: nunca se desatiende uno.
  - DEC-032: `avance_pct` es cuántos bloques se atendieron, no una nota. Al expediente se pasa el mismo avance con
    `expediente.servicios.actualizar_progreso` (monotónico); 100 sella la sección.
  - DEC-014 · D-9: con plazo blando lo hecho después de la fecha límite se acepta y se marca `fuera_de_plazo`.
"""
from __future__ import annotations

from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import plazo as plazo_dom
from ..dominio import practica as practica_dom
from ..dominio.errores import AsignacionCerrada, BloquesPendientes
from .base import nuevo_id
from .puertos import UnidadDeTrabajo


def exigir_escritura(asignacion: dict, ahora: int, *, capturado_en: int | None = None) -> None:
    """Lo que se hace EN LÍNEA (avance, respuestas, completar): con la asignación cerrada —a mano o por un plazo endurecido vencido— es
    409 `asignacion_cerrada`. Lo capturado sin red llega por la sincronización, que sí distingue lo que espera la decisión del profesor."""
    decision, motivo = plazo_dom.politica_de_recepcion(
        fecha_limite=asignacion["fecha_limite"], plazo=asignacion["plazo"], gracia_ms=asignacion["gracia_ms"],
        cerrada_en=asignacion["cerrada_en"], capturado_en=capturado_en if capturado_en is not None else ahora, recibido_en=ahora)
    if decision != plazo_dom.ACEPTAR:
        raise AsignacionCerrada("La asignación ya no admite avance ni respuestas.", motivo=motivo, recepcion=decision,
                                asignacion_id=asignacion["id"])


def obtener_o_crear(uow: UnidadDeTrabajo, asignacion: dict, alumno_id: str, ahora: int) -> dict:
    """La tarea del alumno; se crea al primer contacto (abrir, avanzar, pedir paquete o practicar)."""
    tarea = uow.tareas.obtener(asignacion["id"], alumno_id)
    if tarea is None:
        tarea = uow.tareas.crear({
            "id": nuevo_id(), "asignacion_id": asignacion["id"], "alumno_id": alumno_id, "estado": cat.PENDIENTE,
            "bloques_vistos": [], "avance_pct": 0, "practica_total": int((asignacion.get("practica") or {}).get("total_preguntas") or 0),
            "creada_en": ahora})
    return tarea


def campos_de_actividad(asignacion: dict, tarea: dict, ahora: int, capturado_en: int | None) -> dict:
    """Lo que cambia en la tarea cuando el alumno hace algo: el último avance, `en_curso` si estaba pendiente y `fuera_de_plazo`
    (sticky) si lo capturó después de la fecha límite."""
    campos: dict = {"ultimo_avance_en": ahora}
    if tarea["estado"] == cat.PENDIENTE:
        campos["estado"] = cat.EN_CURSO
    if not tarea["fuera_de_plazo"] and plazo_dom.fuera_de_plazo(asignacion["fecha_limite"], capturado_en if capturado_en is not None else ahora):
        campos["fuera_de_plazo"] = True
    return campos


def abrir_tarea(uow: UnidadDeTrabajo, asignacion: dict, tarea: dict, ahora: int) -> tuple[dict, bool]:
    """La primera vez que se abre la lección la tarea pasa a `en_curso` y queda su `abierta_en`. Devuelve (tarea, primera_vez)."""
    if tarea["abierta_en"] is not None:
        return tarea, False
    campos = {"abierta_en": ahora}
    if tarea["estado"] == cat.PENDIENTE:
        campos["estado"] = cat.EN_CURSO
    return uow.tareas.actualizar(tarea["id"], **campos), True


def pasar_al_expediente(uow: UnidadDeTrabajo, asignacion: dict, tarea: dict) -> None:
    """El avance de la lección al expediente (upsert monotónico: nunca lo reduce; 100 % sella la sección)."""
    porcentaje = 100.0 if tarea["estado"] == cat.COMPLETADA else float(tarea["avance_pct"])
    if porcentaje > 0:
        uow.expediente.actualizar_progreso(
            asignacion["curso_ref"], tarea["alumno_id"], asignacion["leccion_ref"], porcentaje,
            leccion_rotulo=asignacion["leccion_rotulo"], version=asignacion["curso_version"], actor=tarea["alumno_id"])


def registrar_bloques(uow: UnidadDeTrabajo, asignacion: dict, tarea: dict, *, refs: list[str], bloque_actual: str | None,
                      posicion_seg: int | None, ahora: int, capturado_en: int | None = None) -> tuple[dict, list[str], list[str]]:
    """FUN-087 · PATCH `…/progreso/`. Suma los bloques que el aparato declara atendidos (MONÓTONO: nunca desatiende uno), recuerda el
    bloque actual y su posición y recalcula el avance. Devuelve (tarea, aceptados, desconocidos): una referencia que no existe en la
    estructura de la lección se informa y no se guarda. Repetir lo mismo no cambia nada."""
    bloques = asignacion["bloques"]
    conocidos, desconocidos = bloques_dom.clasificar_refs(bloques, [*refs, *([bloque_actual] if bloque_actual else [])])
    nuevos_vistos = bloques_dom.sumar_vistos(tarea["bloques_vistos"], [r for r in conocidos if r in set(refs)])
    campos: dict = {}
    if nuevos_vistos != tarea["bloques_vistos"]:
        campos["bloques_vistos"] = nuevos_vistos
    if bloque_actual and bloque_actual in conocidos:
        if tarea["ultimo_bloque_ref"] != bloque_actual:
            campos.update(ultimo_bloque_ref=bloque_actual, posicion_seg=posicion_seg)     # otro bloque: la posición anterior ya no vale
        elif posicion_seg is not None and posicion_seg != tarea["posicion_seg"]:
            campos["posicion_seg"] = posicion_seg
    elif not bloque_actual and posicion_seg is not None and tarea["ultimo_bloque_ref"] and posicion_seg != tarea["posicion_seg"]:
        campos["posicion_seg"] = posicion_seg
    if campos:
        campos.update(campos_de_actividad(asignacion, tarea, ahora, capturado_en))
        if tarea["estado"] != cat.COMPLETADA:
            campos["avance_pct"] = bloques_dom.avance_pct(bloques, nuevos_vistos)
        tarea = uow.tareas.actualizar(tarea["id"], **campos)
        pasar_al_expediente(uow, asignacion, tarea)
    return tarea, conocidos, desconocidos


def completar(uow: UnidadDeTrabajo, asignacion: dict, tarea: dict, *, ahora: int, capturado_en: int | None = None,
              origen: str = cat.DIRECTO) -> tuple[dict, bool]:
    """FUN-087. Sin todos los obligatorios atendidos: 409 `bloques_pendientes` con `faltan`. Idempotente: completar lo ya completado
    no repite el evento. Devuelve (tarea, recién_completada)."""
    if tarea["estado"] == cat.COMPLETADA:
        return tarea, False
    faltan = bloques_dom.faltan(asignacion["bloques"], tarea["bloques_vistos"])
    if faltan:
        raise BloquesPendientes(f"Faltan {len(faltan)} bloque(s) obligatorio(s) por atender.", faltan=faltan, asignacion_id=asignacion["id"])
    campos = campos_de_actividad(asignacion, tarea, ahora, capturado_en)
    campos.update(estado=cat.COMPLETADA, completada_en=ahora, avance_pct=100)
    tarea = uow.tareas.actualizar(tarea["id"], **campos)
    pasar_al_expediente(uow, asignacion, tarea)
    uow.outbox.publicar("Tarea", tarea["id"], cat.EV_LECCION_COMPLETADA, {
        "asignacion_id": asignacion["id"], "alumno_id": tarea["alumno_id"], "leccion_ref": asignacion["leccion_ref"],
        "fuera_de_plazo": bool(tarea["fuera_de_plazo"]), "origen": origen, "instante": ahora})
    uow.auditoria.registrar(tarea["alumno_id"], "estudio.leccion.completada", "m08_tarea", tarea["id"],
                            anterior={"estado": cat.EN_CURSO}, nuevo={"estado": cat.COMPLETADA, "asignacion_id": asignacion["id"], "origen": origen})
    return tarea, True


def resumir_practicas(uow: UnidadDeTrabajo, asignacion: dict, tarea: dict) -> dict:
    """Recalcula lo que la tarea guarda de sus prácticas (intentos, mejor y última en aciertos, total) desde las prácticas mismas, así
    lo que se califica después —sin red— también queda reflejado."""
    principal = asignacion.get("practica") or {}
    if not principal.get("objeto_ref"):
        return tarea
    resumen = practica_dom.resumen_de_practicas(uow.practicas.de_tarea(tarea["id"], principal["objeto_ref"]),
                                                int(principal.get("total_preguntas") or 0))
    if any(tarea[k] != v for k, v in resumen.items()):
        tarea = uow.tareas.actualizar(tarea["id"], **resumen)
    return tarea


def terminar_practica(uow: UnidadDeTrabajo, asignacion: dict, tarea: dict, practica: dict, *, ahora: int,
                      capturado_en: int | None = None) -> tuple[dict, dict, bool]:
    """FUN-088 · BR-055. Cierra la práctica (sin nota: «Puedes intentarlo nuevamente») y marca su bloque como atendido: práctica
    terminada al menos una vez, sin exigir aciertos (D-4). Idempotente. Devuelve (práctica, tarea, recién_terminada)."""
    if practica["estado"] == cat.TERMINADA:      # nada que cerrar, pero lo calificado después sí cambia el resumen de la tarea
        return practica, resumir_practicas(uow, asignacion, tarea), False
    practica = uow.practicas.actualizar(practica["id"], estado=cat.TERMINADA, terminada_en=max(ahora, practica["iniciada_en"]))
    tarea, _, _ = registrar_bloques(uow, asignacion, tarea, refs=[practica["objeto_ref"]], bloque_actual=None, posicion_seg=None,
                                    ahora=ahora, capturado_en=capturado_en)
    if tarea["estado"] == cat.PENDIENTE:       # una práctica terminada de una lección cuyo bloque no existe: la tarea igual empezó
        tarea = uow.tareas.actualizar(tarea["id"], **campos_de_actividad(asignacion, tarea, ahora, capturado_en))
    tarea = resumir_practicas(uow, asignacion, tarea)
    uow.outbox.publicar("Practica", practica["id"], cat.EV_PRACTICA_TERMINADA, {
        "practica_id": practica["id"], "asignacion_id": asignacion["id"], "alumno_id": tarea["alumno_id"], "numero": practica["numero"],
        "respondidas": len(practica["respuestas"]), "aciertos": practica["aciertos"], "instante": ahora})
    return practica, tarea, True


def refrescar_estructura(uow: UnidadDeTrabajo, asignacion: dict, ficha: dict, leccion: dict) -> dict:
    """La lección tiene una versión nueva: la estructura guardada (referencias y rótulos) se rehace conservando lo ya visto. Se llama
    cada vez que se lee la lección en vivo. Sin cambio de versión, no hace nada."""
    version = str(ficha.get("version") or "")
    if not version or version == asignacion["curso_version"]:
        return asignacion
    bloques = bloques_dom.bloques_de_leccion(leccion)
    asignacion = uow.asignaciones.actualizar(
        asignacion["id"], curso_version=version, bloques=bloques, practica=bloques_dom.practica_de_leccion(leccion),
        evaluacion=bloques_dom.evaluacion_de_leccion(leccion), leccion_rotulo=str(leccion.get("titulo") or asignacion["leccion_rotulo"]),
        curso_rotulo=str(ficha.get("titulo") or asignacion["curso_rotulo"]))
    for tarea in uow.tareas.de_asignacion(asignacion["id"]):
        vistos = bloques_dom.conservar_vistos(tarea["bloques_vistos"], bloques)
        cambios: dict = {}
        if vistos != tarea["bloques_vistos"]:
            cambios["bloques_vistos"] = vistos
        if tarea["estado"] != cat.COMPLETADA:
            avance = bloques_dom.avance_pct(bloques, vistos)
            if avance != float(tarea["avance_pct"]):
                cambios["avance_pct"] = avance
        if tarea["ultimo_bloque_ref"] and bloques_dom.bloque_de(bloques, tarea["ultimo_bloque_ref"]) is None:
            cambios.update(ultimo_bloque_ref="", posicion_seg=None)
        if cambios:
            uow.tareas.actualizar(tarea["id"], **cambios)
    uow.auditoria.registrar("sistema", "estudio.asignacion.estructura_refrescada", "m08_asignacion", asignacion["id"],
                            nuevo={"curso_version": version, "bloques": len(bloques)})
    return asignacion
