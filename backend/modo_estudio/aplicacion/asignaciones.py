"""
StudyAssignmentService · lo que se asigna y lo que ve cada quien (CAP-050, CAP-051, FUN-081).

Alumno (`study.assignment.read`):
  ListarAsignaciones   `GET /asignaciones/`: sus pendientes con fechas límite, progreso y disponibilidad sin red. Sólo las asignaciones
                       ACTIVAS o completadas por él que le alcanzan (su grupo activo o la selección). No lee la biblioteca: usa los rótulos y
                       la estructura guardados, así que funciona con la biblioteca cerrada.
  VerAsignacion        `GET /asignaciones/{id}/`: una de ellas, con sus bloques y lo que ya atendió.

Profesor (OPS; `study.assignment.create` y `.review`, sobre sus grupos o toda la organización si es administración):
  GruposDelDocente · ListarAsignacionesDocente · CrearAsignacion · VerAsignacionDocente («quién completó») · CambiarAsignacion ·
  CerrarAsignacion. La decisión sobre lo que llegó tarde (BR-074) vive con la sincronización.

Sin sesión (Q-34) todo se permite y el actor lo declara el cliente; con sesión, el permiso y ser docente titular del grupo (o la administración).
Al crear se lee la lección EN VIVO (no se asigna a ciegas) y sólo se guardan referencias, rótulos y la estructura de bloques (artículo 14).
"""
from __future__ import annotations

from ..dominio import asignacion as asignacion_dom
from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import paquete as paquete_dom
from ..dominio.errores import (
    AsignacionCerrada,
    DatosInvalidos,
    NodoNoInstalado,
    NoEncontrado,
    NoEsElTitular,
)
from . import dto
from .base import _CasoDeUso, asignacion_del_alumno, destinatarios_de, nuevo_id, resolver_contexto
from .paquetes import evaluar_paquetes
from .puertos import Actor, UnidadDeTrabajo


# ======================================================================================= alumno

def _construir(uow: UnidadDeTrabajo, ctx, asignaciones: list[dict], ahora: int) -> list[dict]:
    """Las `AsignacionAlumno` de un alumno en un aparato: su tarea, su práctica en curso y el paquete de ESTE aparato."""
    tareas = uow.tareas.de_alumno(ctx.alumno_id, [a["id"] for a in asignaciones])
    en_curso = uow.practicas.con_en_curso([t["id"] for t in tareas.values()])
    paquetes: dict[str, dict] = {}
    if ctx.dispositivo_id:
        vigentes = evaluar_paquetes(uow, uow.paquetes.del_aparato(ctx.alumno_id, ctx.dispositivo_id), ahora)
        paquetes = {p["asignacion_id"]: p for p in vigentes}
    salida = []
    for a in asignaciones:
        t = tareas.get(a["id"])
        objeto = (a.get("practica") or {}).get("objeto_ref")
        salida.append(dto.asignacion_alumno(
            a, tarea_=t, en_curso=bool(t and objeto and (t["id"], objeto) in en_curso), paquete=paquetes.get(a["id"]),
            del_alumno=ctx.es_del_alumno, ahora=ahora, ajeno=ctx.ajeno))
    return salida


class ListarAsignaciones(_CasoDeUso):
    """FUN-081. `{alumno, asignaciones[], resumen{pendientes, descargadas, completadas}, servidor_en}`."""

    def ejecutar(self, actor: Actor, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_READ)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, huella, ahora=ahora, declarado=alumno_id)
            grupos = uow.identidad.grupos_del_alumno(ctx.alumno_id)
            candidatas = uow.asignaciones.candidatas_del_alumno(ctx.alumno_id, grupos)
            tareas = uow.tareas.de_alumno(ctx.alumno_id, [a["id"] for a in candidatas])
            visibles = [a for a in candidatas if a["estado"] == cat.ACTIVA
                        or (a["id"] in tareas and tareas[a["id"]]["estado"] == cat.COMPLETADA)]
            visibles.sort(key=lambda a: (tareas.get(a["id"], {}).get("estado") == cat.COMPLETADA,
                                         a["fecha_limite"] if a["fecha_limite"] is not None else float("inf"), -a["creada_en"]))
            lista = _construir(uow, ctx, visibles, ahora)
            return {
                "alumno": {"id": ctx.alumno_id, "rotulo": ctx.alumno_rotulo or None},
                "asignaciones": lista,
                "resumen": {
                    "pendientes": sum(1 for a in lista if not (a["tarea"] and a["tarea"]["estado"] == cat.COMPLETADA)),
                    "descargadas": sum(1 for a in lista if a["paquete"] and a["paquete"]["estado"] == cat.DISPONIBLE),
                    "completadas": sum(1 for a in lista if a["tarea"] and a["tarea"]["estado"] == cat.COMPLETADA),
                },
                "servidor_en": ahora,
            }


class VerAsignacion(_CasoDeUso):
    """`GET /asignaciones/{id}/`: `AsignacionAlumno` con `bloques[]` y su `atendido`. Una asignación de otro grupo es 404."""

    def ejecutar(self, actor: Actor, asignacion_id: str, huella: str = "", alumno_id: str = "") -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_READ)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = resolver_contexto(uow, actor, huella, ahora=ahora, declarado=alumno_id)
            asignacion = asignacion_del_alumno(uow, ctx, asignacion_id)
            return _construir(uow, ctx, [asignacion], ahora)[0]


# ====================================================================================== profesor

def _es_administracion(actor: Actor) -> bool:
    return actor.autenticado and actor.nivel >= 3


def _sin_titularidad(actor: Actor) -> bool:
    """Sin sesión (Q-34) o con administración no se comprueba la titularidad: el resto sólo opera lo suyo."""
    return not actor.autenticado or _es_administracion(actor)


def _grupos_del_actor(uow: UnidadDeTrabajo, actor: Actor) -> list[dict]:
    """Los grupos que el actor puede asignar: los suyos (docente) o todos (administración, o sin sesión)."""
    return uow.identidad.grupos_activos() if _sin_titularidad(actor) else uow.identidad.grupos_del_docente(actor.id)


def _exigir_titular(uow: UnidadDeTrabajo, actor: Actor, asignacion: dict) -> None:
    """Con sesión: ser quien asignó o docente titular del grupo, o administración."""
    if _sin_titularidad(actor) or asignacion["profesor_id"] == actor.id:
        return
    if asignacion["grupo_id"] and uow.identidad.es_docente_del_grupo(asignacion["grupo_id"], actor.id):
        return
    raise NoEsElTitular("La asignación es de otro profesor: sólo su titular o la administración la opera.", asignacion_id=asignacion["id"],
                        profesor_id=asignacion["profesor_id"])


def _exigir_organizacion(uow: UnidadDeTrabajo) -> None:
    if not uow.identidad.organizacion_id():
        raise NodoNoInstalado()


def totales_de(uow: UnidadDeTrabajo, asignacion: dict, destinatarios: list[dict] | None = None) -> dict:
    """Cuántos completaron, van en curso y siguen pendientes entre los DESTINATARIOS (grupo activo o selección), tengan o no tarea."""
    destinatarios = destinatarios if destinatarios is not None else destinatarios_de(uow, asignacion)
    ids = {d["id"] for d in destinatarios}
    tareas = [t for t in uow.tareas.de_asignacion(asignacion["id"]) if t["alumno_id"] in ids]
    completaron = sum(1 for t in tareas if t["estado"] == cat.COMPLETADA)
    en_curso = sum(1 for t in tareas if t["estado"] == cat.EN_CURSO)
    return {
        "destinatarios_total": len(ids), "completaron": completaron, "en_curso": en_curso,
        "pendientes": len(ids) - completaron - en_curso, "fuera_de_plazo": sum(1 for t in tareas if t["fuera_de_plazo"]),
        "pendientes_decision": len(uow.sincronizaciones.pendientes_de_decision(asignacion_id=asignacion["id"])),
    }


class GruposDelDocente(_CasoDeUso):
    """`GET /docente/grupos/`: sus grupos con sus alumnos (todos si es administración o no hay sesión). `instalado:false` sin organización."""

    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_CREATE)
        with self.s.uow() as uow:
            if not uow.identidad.organizacion_id():
                return {"instalado": False, "grupos": []}
            return {"instalado": True, "grupos": [
                {"id": g["id"], "codigo": g["codigo"], "nombre": g["nombre"], "nivel_clave": g["nivel_clave"],
                 "alumnos": uow.identidad.alumnos_del_grupo(g["id"])} for g in _grupos_del_actor(uow, actor)]}


class ListarAsignacionesDocente(_CasoDeUso):
    """`GET /docente/asignaciones/?grupo_id=&estado=` (`study.assignment.review`). Con sesión de docente, las suyas y las de sus grupos."""

    def ejecutar(self, actor: Actor, grupo_id: str | None = None, estado: str | None = None) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_REVIEW)
        if estado and estado not in cat.ESTADOS_ASIGNACION:
            raise DatosInvalidos(f"Estado desconocido: {estado!r}. Estados: {', '.join(cat.ESTADOS_ASIGNACION)}.", estado=estado)
        with self.s.uow() as uow:
            filas = uow.asignaciones.listar(grupo_id=grupo_id or None, estado=estado or None)
            if not _sin_titularidad(actor):
                mios = {g["id"] for g in uow.identidad.grupos_del_docente(actor.id)}
                filas = [a for a in filas if a["profesor_id"] == actor.id or a["grupo_id"] in mios]
            return {"asignaciones": [dto.asignacion_docente(a, totales=totales_de(uow, a)) for a in filas]}


class CrearAsignacion(_CasoDeUso):
    """CAP-050 · `POST /docente/asignaciones/`. Lee la lección EN VIVO para guardar rótulos, la estructura de bloques (D-4), la práctica y
    la evaluación (informativa) y mide lo que pesan sus medios (`bytes_estimados`); sin biblioteca es 503 (no se asigna a ciegas)."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_CREATE)
        nueva = asignacion_dom.validar_nueva(datos, self.s.config.gracia_ms)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            _exigir_organizacion(uow)
            grupo = self._validar_destinatarios(uow, actor, nueva)
            profesor_rotulo = actor.rotulo or uow.identidad.rotulo_persona(actor.id)
        # La lección se lee EN VIVO, fuera de la transacción: la biblioteca puede tardar y no debe retener la escritura de nadie.
        leida = self.s.contenido.leccion(fuente=nueva["fuente"], curso_ref=nueva["curso_ref"], leccion_ref=nueva["leccion_ref"])
        ficha, leccion = leida["curso"], leida["leccion"]
        bloques = bloques_dom.bloques_de_leccion(leccion)
        if not bloques:
            raise DatosInvalidos("La lección no tiene nada que estudiar: sin láminas, páginas, laboratorios ni práctica.",
                                 leccion_ref=nueva["leccion_ref"])
        estimados = self._estimar_bytes(leida, bloques)
        clasificacion = ficha.get("clasificacion") or {}
        with self.s.uow() as uow:
            asignacion = uow.asignaciones.crear({
                "id": nuevo_id(), "grupo_id": nueva["grupo_id"], "grupo_rotulo": (grupo or {}).get("nombre", ""),
                "alcance": nueva["alcance"], "destinatarios": nueva["alumnos"], "profesor_id": actor.id,
                "profesor_rotulo": profesor_rotulo, "fuente_curso": leida["fuente"], "curso_ref": ficha["curso_ref"],
                "curso_version": ficha.get("version") or "", "curso_rotulo": ficha.get("titulo") or "",
                "leccion_ref": leccion["leccion_ref"], "leccion_rotulo": leccion.get("titulo") or "",
                "titulo": nueva["titulo"] or leccion.get("titulo") or leccion["leccion_ref"],
                "descripcion": str(leccion.get("resumen") or "")[:500],
                "asignatura_rotulo": str((clasificacion.get("asignatura") or {}).get("nombre") or ""),
                "unidad_rotulo": str((clasificacion.get("tema") or {}).get("nombre") or ""),
                "consigna": nueva["consigna"], "bloques": bloques, "practica": bloques_dom.practica_de_leccion(leccion),
                "evaluacion": bloques_dom.evaluacion_de_leccion(leccion), "bytes_estimados": estimados,
                "paquete_permitido": nueva["paquete_permitido"], "fecha_limite": nueva["fecha_limite"], "plazo": nueva["plazo"],
                "gracia_ms": nueva["gracia_ms"], "estado": cat.ACTIVA, "creada_en": ahora, "creado_por": actor.id})
            totales = totales_de(uow, asignacion)
            self._publicar(uow, "Asignacion", asignacion["id"], cat.EV_ASIGNACION_CREADA, {
                "asignacion_id": asignacion["id"], "grupo_id": asignacion["grupo_id"], "alcance": asignacion["alcance"],
                "curso_ref": asignacion["curso_ref"], "leccion_ref": asignacion["leccion_ref"], "profesor_id": actor.id,
                "destinatarios_total": totales["destinatarios_total"], "fecha_limite": asignacion["fecha_limite"],
                "plazo": asignacion["plazo"]}, ahora)
            uow.auditoria.registrar(actor.id, "estudio.asignacion.creada", "m08_asignacion", asignacion["id"], nuevo={
                "grupo_id": asignacion["grupo_id"], "alcance": asignacion["alcance"], "curso_ref": asignacion["curso_ref"],
                "leccion_ref": asignacion["leccion_ref"], "fecha_limite": asignacion["fecha_limite"], "plazo": asignacion["plazo"],
                "destinatarios_total": totales["destinatarios_total"]})
            return dto.asignacion_docente(asignacion, totales=totales)

    def _validar_destinatarios(self, uow: UnidadDeTrabajo, actor: Actor, nueva: dict) -> dict | None:
        """El grupo existe y está activo; los alumnos existen (y son del grupo, si se nombra uno); y quien asigna es su titular."""
        grupo = None
        if nueva["grupo_id"]:
            grupo = uow.identidad.grupo(nueva["grupo_id"])
            if grupo is None:
                raise NoEncontrado("No existe ese grupo.", grupo_id=nueva["grupo_id"])
            if not grupo["activo"]:
                raise DatosInvalidos("El grupo está inactivo: no se le puede asignar trabajo.", grupo_id=nueva["grupo_id"])
            if not _sin_titularidad(actor) and not uow.identidad.es_docente_del_grupo(grupo["id"], actor.id):
                raise NoEsElTitular("Sólo el docente titular del grupo o la administración le asigna trabajo.", grupo_id=grupo["id"])
        if nueva["alcance"] == cat.SELECCION:
            conocidos = uow.identidad.alumnos_conocidos(nueva["alumnos"])
            if conocidos is not None and set(nueva["alumnos"]) - conocidos:
                raise DatosInvalidos("Hay alumnos que no existen en el padrón.", desconocidos=sorted(set(nueva["alumnos"]) - conocidos))
            if grupo is not None:
                del_grupo = {a["id"] for a in uow.identidad.alumnos_del_grupo(grupo["id"])}
                if set(nueva["alumnos"]) - del_grupo:
                    raise DatosInvalidos("Hay alumnos que no pertenecen al grupo.", ajenos=sorted(set(nueva["alumnos"]) - del_grupo))
            elif not _sin_titularidad(actor):
                mios = {a["id"] for g in uow.identidad.grupos_del_docente(actor.id) for a in uow.identidad.alumnos_del_grupo(g["id"])}
                if set(nueva["alumnos"]) - mios:
                    raise NoEsElTitular("Sólo se le asigna trabajo a alumnos de sus grupos.", ajenos=sorted(set(nueva["alumnos"]) - mios))
        return grupo

    def _estimar_bytes(self, leida: dict, bloques: list[dict]) -> int | None:
        """Suma lo que pesan los medios que se pueden llevar (las simulaciones no viajan: Q-71). Sin medios pesa 0; si ninguno se pudo
        medir, se ignora (None): el tamaño se afina al preparar el paquete."""
        refs = [r for r in sorted(bloques_dom.medios_de_bloques(bloques)) if not paquete_dom.es_simulacion((leida["medios"] or {}).get(r))]
        if not refs:
            return 0
        medidos = [t for t in (self.s.contenido.tamano_de(leida["fuente"], leida["curso"]["curso_ref"], r) for r in refs) if t is not None]
        return sum(medidos) if medidos else None


class VerAsignacionDocente(_CasoDeUso):
    """CAP-051 · `GET /docente/asignaciones/{id}/` (`study.assignment.review`): **quién completó**. Los destinatarios (grupo activo o
    selección), con o sin tarea, con su avance, su práctica, su paquete, el aparato que tienen y los envíos que esperan su decisión
    (`decisiones[{emisor_id, secuencia, tipo, motivo, ocurrido_en, recibido_en}]`: el par `(emisor_id, secuencia)` es lo que
    `POST …/decisiones/` necesita para resolver cada uno, BR-074)."""

    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_REVIEW)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = _asignacion(uow, asignacion_id)
            _exigir_titular(uow, actor, asignacion)
            destinatarios = destinatarios_de(uow, asignacion)
            ids = [d["id"] for d in destinatarios]
            tareas = {t["alumno_id"]: t for t in uow.tareas.de_asignacion(asignacion["id"])}
            paquetes: dict[str, list[dict]] = {}
            for p in uow.paquetes.de_asignacion(asignacion["id"]):
                paquetes.setdefault(p["alumno_id"], []).append(p)
            pendientes: dict[str, list[dict]] = {}      # los envíos que esperan al profesor, por alumno (BR-074): de aquí sale `decisiones[]`
            for fila in uow.sincronizaciones.pendientes_de_decision(asignacion_id=asignacion["id"]):
                pendientes.setdefault(fila["alumno_id"], []).append(fila)
            propios = uow.dispositivos.asignados_a(ids)
            filas = []
            for alumno in sorted(destinatarios, key=lambda d: (d["rotulo"] or d["id"]).lower()):
                aparato = propios.get(alumno["id"])
                if aparato is None:
                    sesion = uow.dispositivos.sesion_abierta_de_alumno(alumno["id"])
                    aparato = uow.dispositivos.por_id(sesion["dispositivo_id"]) if sesion else None
                filas.append(dto.fila_de_alumno(asignacion, alumno, tareas.get(alumno["id"]), paquetes.get(alumno["id"], []), aparato,
                                                pendientes.get(alumno["id"], []), ahora))
            return dto.asignacion_docente(asignacion, totales=totales_de(uow, asignacion, destinatarios), alumnos=filas)


def _asignacion(uow: UnidadDeTrabajo, asignacion_id: str) -> dict:
    asignacion = uow.asignaciones.por_id(asignacion_id)
    if asignacion is None:
        raise NoEncontrado("No existe esa asignación.", asignacion_id=asignacion_id)
    return asignacion


class CambiarAsignacion(_CasoDeUso):
    """`PATCH /docente/asignaciones/{id}/` (`study.assignment.create`): endurecer el plazo o mover la fecha, la gracia, el título, la
    consigna o si el material se puede llevar. Una asignación cerrada no se toca."""

    def ejecutar(self, actor: Actor, asignacion_id: str, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_CREATE)
        cambios = asignacion_dom.validar_cambios(datos)
        with self.s.uow() as uow:
            asignacion = _asignacion(uow, asignacion_id)
            _exigir_titular(uow, actor, asignacion)
            if asignacion["estado"] == cat.CERRADA:
                raise AsignacionCerrada("La asignación está cerrada: ya no se puede cambiar.", asignacion_id=asignacion_id)
            anterior = {k: asignacion[k] for k in cambios}
            asignacion = uow.asignaciones.actualizar(asignacion_id, **cambios)
            uow.auditoria.registrar(actor.id, "estudio.asignacion.actualizada", "m08_asignacion", asignacion_id,
                                    anterior=anterior, nuevo=cambios)
            return dto.asignacion_docente(asignacion, totales=totales_de(uow, asignacion))


class CerrarAsignacion(_CasoDeUso):
    """CAP-051 · `POST /docente/asignaciones/{id}/cerrar/` (`study.assignment.create`): ya no admite avance ni respuestas en línea; lo que llegue
    sin red se decide por la política de plazo. Idempotente."""

    def ejecutar(self, actor: Actor, asignacion_id: str) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_ASSIGNMENT_CREATE)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            asignacion = _asignacion(uow, asignacion_id)
            _exigir_titular(uow, actor, asignacion)
            if asignacion["estado"] != cat.CERRADA:
                asignacion = uow.asignaciones.actualizar(asignacion_id, estado=cat.CERRADA, cerrada_en=ahora)
                totales = totales_de(uow, asignacion)
                self._publicar(uow, "Asignacion", asignacion_id, cat.EV_ASIGNACION_CERRADA, {
                    "asignacion_id": asignacion_id, "grupo_id": asignacion["grupo_id"], "actor": actor.id,
                    "destinatarios_total": totales["destinatarios_total"], "completaron": totales["completaron"]}, ahora)
                uow.auditoria.registrar(actor.id, "estudio.asignacion.cerrada", "m08_asignacion", asignacion_id,
                                        anterior={"estado": cat.ACTIVA}, nuevo={"estado": cat.CERRADA, "completaron": totales["completaron"]})
            return dto.asignacion_docente(asignacion, totales=totales_de(uow, asignacion))
