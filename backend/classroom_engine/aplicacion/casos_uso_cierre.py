"""
El cierre de la clase, completo (007-09): el anclaje curricular que se omitió al empezar y la tarea de estudio.

  AnclarSesion     BR-039 / BR-040: el anclaje curricular es opcional, se ofrece y se sugiere, nunca se exige, y puede
                   asignarse en cualquier momento, incluso con la clase ya cerrada.
  SugerirAnclaje   propone nodos a partir de lo que de verdad se usó en la clase (JRN-011, paso 12), no de una lista fija
  MarcarEstudio    «dejar como tarea de estudio»: marca una distribución como disponible para MOD-008, con fecha límite

Decisión pendiente con el CTO: hoy el anclaje es una lista de `{ref, rotulo}` en `m07_sesion.anclajes`; puede quedar así,
convertirse en `clase.tema_id` (un solo nodo) o en una tabla puente `rel_clase_tema` (varios).
"""
from __future__ import annotations

from ..dominio import curso as cur
from ..dominio import sesion as dom
from ..dominio.errores import DatosInvalidos, ErrorAula, NoEncontrado
from .casos_uso import _CasoDeSesion
from .puertos import Actor

MAX_ANCLAJES = 12


def _limpiar(nodos) -> list[dict]:
    if not isinstance(nodos, list):
        raise DatosInvalidos("`nodos` debe ser una lista de {ref, rotulo}.")
    salida, vistos = [], set()
    for n in nodos:
        if not isinstance(n, dict) or not str(n.get("ref") or "").strip():
            raise DatosInvalidos("Cada nodo exige `ref`.")
        ref = str(n["ref"]).strip()[:120]
        if ref in vistos:
            continue
        vistos.add(ref)
        salida.append({"ref": ref, "rotulo": str(n.get("rotulo") or "")[:250]})
    if len(salida) > MAX_ANCLAJES:
        raise DatosInvalidos(f"Una clase se ancla a lo sumo a {MAX_ANCLAJES} nodos.", nodos=len(salida))
    return salida


class AnclarSesion(_CasoDeSesion):
    """Reemplaza los anclajes de la sesión. Vale con la clase abierta, suspendida, cerrada o archivada (BR-040)."""

    def ejecutar(self, actor: Actor, sesion_id: str, nodos: list[dict]) -> dict:
        nuevos = _limpiar(nodos)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            self._autorizar(actor, dom.P_END, sesion)
            anteriores = sesion["anclajes"] or []
            if anteriores != nuevos:
                uow.sesiones.actualizar_sesion(sesion_id, anclajes=nuevos)
                uow.auditoria.registrar(actor.id, "aula.sesion.anclada", "m07_sesion", sesion_id,
                                        anterior={"anclajes": anteriores}, nuevo={"anclajes": nuevos, "instante": ahora})
                self._difundir(uow, sesion_id, "sesion", anclajes=len(nuevos))
            return {"sesion_id": sesion_id, "anclajes": nuevos, "cambio": anteriores != nuevos}


class SugerirAnclaje(_CasoDeSesion):
    """Los nodos que la clase tocó de verdad: el tema del curso y los `topicRef` / referencias curriculares de los
    objetos que se proyectaron o se lanzaron. Si el curso ya no está disponible, la lista sale vacía con el motivo:
    ofrecer el anclaje no puede fallar."""

    def ejecutar(self, sesion_id: str) -> dict:
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            usados: list[str] = []
            for d in uow.sesiones.distribuciones(sesion_id):
                if d["objeto_ref"] and d["objeto_ref"] not in usados:
                    usados.append(d["objeto_ref"])
            if sesion["objeto_ref"] and sesion["objeto_ref"] not in usados:
                usados.append(sesion["objeto_ref"])
            vigente = uow.sesiones.selector_vigente(sesion_id)
            if vigente and vigente["objeto_ref"] and vigente["objeto_ref"] not in usados:
                usados.append(vigente["objeto_ref"])
            curso_ref, fuente = sesion["curso_ref"], sesion["fuente_curso"] or None
            anclajes = sesion["anclajes"] or []
        if not curso_ref:
            return {"sesion_id": sesion_id, "anclajes": anclajes, "sugerencias": [], "motivo": "La clase no usó ningún curso."}
        try:
            vista, _ = self._vista(fuente, curso_ref, "docente")
        except ErrorAula as error:
            return {"sesion_id": sesion_id, "anclajes": anclajes, "sugerencias": [], "motivo": error.detalle}
        sugerencias: list[dict] = []
        vistos = {a["ref"] for a in anclajes}

        def proponer(ref, rotulo, origen):
            ref = str(ref or "").strip()
            if ref and ref not in vistos:
                vistos.add(ref)
                sugerencias.append({"ref": ref, "rotulo": str(rotulo or ref), "origen": origen})

        tema = (vista.get("clasificacion") or {}).get("tema") or {}
        proponer(tema.get("codigo"), tema.get("nombre"), "tema del curso")
        for objeto_ref in usados:
            try:
                objeto = cur.localizar(vista, objeto_ref=objeto_ref)["objeto"]
            except ErrorAula:
                continue
            proponer(objeto.get("tema_ref"), objeto.get("titulo"), "objeto usado")
            for r in objeto.get("referencias_curriculares") or []:
                proponer(r.get("codigo"), r.get("descripcion") or f"{r.get('marco') or ''} {r.get('codigo') or ''}".strip(), "referencia curricular")
        return {"sesion_id": sesion_id, "anclajes": anclajes, "sugerencias": sugerencias[:MAX_ANCLAJES], "motivo": ""}


class MarcarEstudio(_CasoDeSesion):
    """«Dejar como tarea de estudio» (PAN-008): la distribución queda disponible para MOD-008 hasta `hasta` (ms del reloj
    del nodo). Se puede hacer al cerrar la clase; después, mientras no esté archivada."""

    def ejecutar(self, actor: Actor, sesion_id: str, distribucion_id: str, disponible: bool, hasta: int | None = None) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            sesion = self._sesion(uow, sesion_id)
            self._autorizar(actor, dom.P_END, sesion)
            if sesion["estado"] == dom.ARCHIVADA:
                raise DatosInvalidos("La clase está archivada: ya no se dejan tareas.", estado=sesion["estado"])
            distribucion = uow.sesiones.distribucion(distribucion_id)
            if not distribucion or distribucion["sesion_id"] != sesion_id:
                raise NoEncontrado("No existe esa distribución en esta sesión.", distribucion_id=distribucion_id)
            if hasta is not None and hasta <= ahora:
                raise DatosInvalidos("La fecha límite debe ser posterior a este momento.", hasta=hasta)
            nueva = uow.sesiones.actualizar_distribucion(distribucion_id, disponible_estudio=bool(disponible),
                                                         estudio_hasta=hasta if disponible else None)
            uow.auditoria.registrar(actor.id, "aula.distribucion.estudio", "m07_distribucion", distribucion_id,
                                    anterior={"disponible_estudio": distribucion["disponible_estudio"], "hasta": distribucion["estudio_hasta"]},
                                    nuevo={"disponible_estudio": nueva["disponible_estudio"], "hasta": nueva["estudio_hasta"]})
            self._difundir(uow, sesion_id, "distribucion", distribucion_id=distribucion_id, estudio=bool(disponible))
            return nueva
