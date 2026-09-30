"""
StudyLessonService · abrir, reanudar, registrar avance y completar una lección asignada (FUN-082, FUN-087, FUN-088).

  AbrirLeccion          `GET /lecciones/{id}/` (`study.lesson.open`; `{id}` es el de la ASIGNACIÓN, que fija curso, versión y lección): lee la
                        lección EN VIVO sin claves, con los medios apuntando a las rutas de este módulo; crea la tarea, la pasa a `en_curso` y emite
                        `estudio.leccion.abierta.v1` la primera vez. Si la versión del curso cambió, rehace la estructura de bloques conservando lo visto.
  AbrirMedioDeLeccion   `GET/HEAD /asignaciones/{id}/medios/{media_ref}/[ruta]` (`study.lesson.open`): bytes del medio con `Range`, sólo si el medio
                        pertenece a la lección asignada y la asignación le alcanza al alumno.
  RegistrarProgreso     `PATCH /lecciones/{id}/progreso/` (`study.lesson.complete`): bloques atendidos, bloque actual y posición. MONÓTONO.
  CompletarLeccion      `POST /lecciones/{id}/completar/` (`study.lesson.complete`): sólo con todos los obligatorios atendidos (409 `bloques_pendientes`).

Una asignación cerrada se puede LEER pero no admite avance (409 `asignacion_cerrada`). Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio.errores import DatosInvalidos, NoEncontrado
from . import dto
from .base import _CasoDeUso, asignacion_del_alumno, resolver_contexto
from .paquetes import semilla_de
from .puertos import Actor, Bytes
from .tareas import abrir_tarea, completar, exigir_escritura, obtener_o_crear, refrescar_estructura, registrar_bloques


def _entero(valor, nombre: str) -> int | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or int(valor) != valor or valor < 0:
        raise DatosInvalidos(f"`{nombre}` debe ser un entero mayor o igual que 0.", campo=nombre)
    return int(valor)


class AbrirLeccion(_CasoDeUso):
    """FUN-082. `{asignacion, curso, leccion, bloques[], reanudar, servidor_en}`. La lección es la vista de aula SIN claves, leída en vivo:
    sin biblioteca es 503 (`fuente_no_disponible`); la lista de pendientes, en cambio, sí funciona (usa lo guardado)."""

    def ejecutar(self, actor: Actor, asignacion_id: str, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LESSON_OPEN)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, huella, ahora=ahora, declarado=alumno_id, registrar=True)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
        leida = self.s.contenido.leccion(fuente=asignacion["fuente_curso"], curso_ref=asignacion["curso_ref"],
                                         leccion_ref=asignacion["leccion_ref"], asignacion_id=asignacion["id"], dispositivo=ctx.huella,
                                         alumno_id=ctx.alumno_para_url, semilla=semilla_de(asignacion["id"]))
        with self.s.uow() as uow:
            asignacion = refrescar_estructura(uow, uow.asignaciones.por_id(asignacion["id"]), leida["curso"], leida["leccion"])
            tarea = uow.tareas.obtener(asignacion["id"], ctx.alumno_id)
            if asignacion["estado"] == cat.ACTIVA:      # una asignación cerrada se lee, pero no se empieza
                tarea = tarea or obtener_o_crear(uow, asignacion, ctx.alumno_id, ahora)
                tarea, primera_vez = abrir_tarea(uow, asignacion, tarea, ahora)
                if primera_vez:
                    self._publicar(uow, "Tarea", tarea["id"], cat.EV_LECCION_ABIERTA, {
                        "asignacion_id": asignacion["id"], "alumno_id": ctx.alumno_id, "curso_ref": asignacion["curso_ref"],
                        "leccion_ref": asignacion["leccion_ref"]}, ahora)
            paquete = next((p for p in uow.paquetes.del_aparato(ctx.alumno_id, ctx.dispositivo_id) if p["asignacion_id"] == asignacion["id"]),
                           None) if ctx.dispositivo_id else None
            en_curso = bool(tarea and (asignacion.get("practica") or {}).get("objeto_ref")
                            and uow.practicas.en_curso(tarea["id"], asignacion["practica"]["objeto_ref"]))
            return {
                "asignacion": dto.asignacion_alumno(asignacion, tarea_=tarea, en_curso=en_curso, paquete=paquete,
                                                    del_alumno=ctx.es_del_alumno, ahora=ahora, ajeno=ctx.ajeno),
                "curso": leida["curso"], "leccion": leida["leccion"],
                "bloques": dto.bloques_del_alumno(asignacion, tarea),
                "reanudar": dto.reanudar(asignacion, tarea),
                "servidor_en": ahora,
            }


class AbrirMedioDeLeccion(_CasoDeUso):
    """Bytes de un medio de la lección asignada (imagen, audio, pdf, video, subtítulos, transcripción o un archivo interno de una
    simulación), en paso a través y con `Range`. Sólo se sirve lo que pertenece a la lección asignada: la asignación fija qué medios."""

    def ejecutar(self, actor: Actor, asignacion_id: str, media_ref: str, ruta: str | None = None, rango: str | None = None,
                 metodo: str = "GET", huella: str = "", alumno_id: str = "") -> Bytes:
        self.s.autorizacion.exigir(actor, cat.P_LESSON_OPEN)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, huella, ahora=ahora, declarado=alumno_id)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
        if media_ref not in bloques_dom.medios_de_bloques(asignacion["bloques"]):
            raise NoEncontrado("Ese medio no pertenece a la lección asignada.", media_ref=media_ref)
        return self.s.contenido.abrir_medio(asignacion["fuente_curso"], asignacion["curso_ref"], media_ref, ruta, rango, metodo)


class RegistrarProgreso(_CasoDeUso):
    """FUN-087. `PATCH /lecciones/{id}/progreso/`: `{dispositivo, bloques_vistos?: [ref], bloque_actual?: ref, posicion_seg?: n, capturado_en?: ms}`
    → `{tarea, aceptados[], desconocidos[]}`. MONÓTONO: nunca desatiende un bloque. Recalcula `avance_pct` y lo pasa al expediente."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LESSON_COMPLETE)
        refs = datos.get("bloques_vistos") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise DatosInvalidos("`bloques_vistos` debe ser una lista de referencias de bloque.", campo="bloques_vistos")
        actual = datos.get("bloque_actual")
        if actual is not None and not isinstance(actual, str):
            raise DatosInvalidos("`bloque_actual` debe ser la referencia de un bloque.", campo="bloque_actual")
        posicion = bloques_dom.validar_posicion(datos.get("posicion_seg"))
        capturado = _entero(datos.get("capturado_en"), "capturado_en")
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "", registrar=True)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            exigir_escritura(asignacion, ahora, capturado_en=capturado)
            tarea = obtener_o_crear(uow, asignacion, ctx.alumno_id, ahora)
            tarea, aceptados, desconocidos = registrar_bloques(uow, asignacion, tarea, refs=refs, bloque_actual=actual or None,
                                                               posicion_seg=posicion, ahora=ahora, capturado_en=capturado)
            return {"tarea": dto.tarea(asignacion, tarea, ahora), "aceptados": aceptados, "desconocidos": desconocidos}


class CompletarLeccion(_CasoDeUso):
    """FUN-087. `POST /lecciones/{id}/completar/` → `{tarea}` con `estado = completada` y `estudio.leccion.completada.v1`. Sin todos los
    obligatorios atendidos: 409 `bloques_pendientes` con `faltan[{ref, indice, titulo}]`. Sella la sección en el expediente (100 %).
    Idempotente: completar lo ya completado devuelve la tarea sin repetir el evento."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LESSON_COMPLETE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id") or "", registrar=True)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            tarea = uow.tareas.obtener(asignacion["id"], ctx.alumno_id)
            if tarea is None or tarea["estado"] != cat.COMPLETADA:
                exigir_escritura(asignacion, ahora)
                tarea = tarea or obtener_o_crear(uow, asignacion, ctx.alumno_id, ahora)
            tarea, _ = completar(uow, asignacion, tarea, ahora=ahora)
            return {"tarea": dto.tarea(asignacion, tarea, ahora)}
