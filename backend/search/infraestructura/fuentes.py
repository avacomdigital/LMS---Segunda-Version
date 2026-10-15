"""
Las fuentes locales de Search: lo que cada módulo propietario deja buscar de lo SUYO, pedido por la interfaz del dueño (`<módulo>.servicios`, BR-004). Search nunca lee ni
escribe `m10_*`, `m08_*` ni `m07_*`: el evento avisa que algo cambió y aquí se vuelve a leer el estado ACTUAL de la entidad.

  FuenteEvaluaciones   MOD-010 · las asignaciones de exámenes y actividades (no los borradores ni las archivadas)
  FuenteEstudios       MOD-008 · las lecciones asignadas para estudiar
  FuenteClases         MOD-007 · las sesiones de clase (planificadas, abiertas, suspendidas y cerradas; no las archivadas)

Lo que se proyecta es lo MÍNIMO para encontrar la entidad (título, descripción, palabras clave y contexto) y para acotar la consulta (`grupo_id`, `profesor_id`,
`curso_ref`). Nunca se proyectan alumnos, respuestas, notas ni claves; ni el contenido de un curso.
"""
from __future__ import annotations

from collections.abc import Iterator

from ..dominio import catalogos as cat
from ..dominio.documento import Documento
from .identidad import IdentidadAcceso


def _unir(*partes) -> str:
    return " ".join(str(p).strip() for p in partes if p and str(p).strip())


def _texto(*partes, separador: str = " · ") -> str:
    return separador.join(str(p).strip() for p in partes if p and str(p).strip())


class FuenteEvaluaciones:
    tipo = cat.EVALUACION
    fuente = cat.FUENTE_EVALUACION

    @staticmethod
    def _tipos_de_evento() -> tuple[str, ...]:
        from evaluacion.dominio import catalogos as ev

        return (ev.EV_ASIGNADA, ev.EV_NIVEL_DEFINIDO, ev.EV_PLAZO_CONFIGURADO, ev.EV_PLAZO_ENDURECIDO, ev.EV_NIVEL_DEGRADADO, ev.EV_ASIGNACION_CERRADA,
                ev.EV_RESULTADOS_LIBERADOS, ev.EV_RESULTADOS_CONFIGURADOS)

    def eventos_desde(self, secuencia: int, limite: int) -> tuple[list[dict], int]:
        from evaluacion import servicios as dueno

        eventos, hasta = dueno.eventos_desde(secuencia, limite, self._tipos_de_evento())
        return [{"secuencia": e["secuencia"], "tipo": e["tipo"], "entidad_id": e["carga"].get("asignacion_id"), "creado_en": e["creado_en"]}
                for e in eventos if (e.get("carga") or {}).get("asignacion_id")], hasta

    def ultima_secuencia(self) -> int:
        from evaluacion import servicios as dueno

        return dueno.ultima_secuencia()

    @staticmethod
    def _documento(a: dict | None) -> Documento | None:
        from evaluacion.dominio import catalogos as ev

        if not a or a.get("estado") in (ev.BORRADOR, ev.ARCHIVADA):
            return None
        tipo = a.get("tipo") or ev.EXAMEN
        etiquetas = "examen evaluacion" if tipo == ev.EXAMEN else "actividad evaluacion"
        return Documento(
            tipo=cat.EVALUACION, entidad_id=a["id"], subtipo=tipo, titulo=a.get("titulo") or "Evaluación",
            descripcion=a.get("descripcion") or "", palabras=_unir(a.get("curso_rotulo"), a.get("objeto_rotulo")),
            contexto=_unir(a.get("grupo_rotulo")), etiquetas=etiquetas, grupo_id=a.get("grupo_id") or "", profesor_id=a.get("profesor_id") or "", curso_ref=a.get("curso_ref") or "",
            estado=a.get("estado") or "",
            referencia={"fuente": a.get("fuente_curso") or "", "leccion_ref": a.get("leccion_ref") or "", "objeto_ref": a.get("objeto_ref") or "",
                        "curso": a.get("curso_rotulo") or "", "leccion": a.get("objeto_rotulo") or ""},
            origen_actualizado_en=a.get("creada_en"))

    def documento(self, entidad_id: str) -> Documento | None:
        from evaluacion import servicios as dueno

        return self._documento(dueno.asignacion(entidad_id))

    def documentos(self, entidad_ids: list[str]) -> dict[str, Documento]:
        salida = {}
        for entidad_id in entidad_ids:
            documento = self.documento(entidad_id)
            if documento is not None:
                salida[entidad_id] = documento
        return salida

    def todos(self) -> Iterator[Documento]:
        from evaluacion import servicios as dueno

        vistos: set[str] = set()
        filas = [fila for grupo in IdentidadAcceso().grupos_activos() for fila in dueno.asignaciones_de_grupo(grupo["id"])] + dueno.asignaciones_sin_grupo()
        for fila in filas:
            if fila["id"] in vistos:
                continue
            vistos.add(fila["id"])
            documento = self._documento(fila)
            if documento is not None:
                yield documento


class FuenteEstudios:
    tipo = cat.ESTUDIO
    fuente = cat.FUENTE_ESTUDIO

    @staticmethod
    def _tipos_de_evento() -> tuple[str, ...]:
        from modo_estudio.dominio import catalogos as es

        return (es.EV_ASIGNACION_CREADA, es.EV_ASIGNACION_CERRADA)

    def eventos_desde(self, secuencia: int, limite: int) -> tuple[list[dict], int]:
        from modo_estudio import servicios as dueno

        eventos, hasta = dueno.eventos_desde(secuencia, limite, self._tipos_de_evento())
        return [{"secuencia": e["secuencia"], "tipo": e["tipo"], "entidad_id": e["agregado_id"], "creado_en": e["creado_en"]}
                for e in eventos if e.get("agregado_tipo") == "Asignacion" and e.get("agregado_id")], hasta

    def ultima_secuencia(self) -> int:
        from modo_estudio import servicios as dueno

        return dueno.ultima_secuencia()

    @staticmethod
    def _documento(a: dict | None) -> Documento | None:
        if not a:
            return None
        return Documento(
            tipo=cat.ESTUDIO, entidad_id=a["id"], titulo=a.get("titulo") or "Estudio asignado", descripcion=a.get("descripcion") or "",
            palabras=_unir(a.get("curso_rotulo"), a.get("leccion_rotulo"), a.get("asignatura_rotulo"), a.get("unidad_rotulo")),
            contexto=_unir(a.get("grupo_rotulo")), etiquetas="estudio tarea asignado", grupo_id=a.get("grupo_id") or "", profesor_id=a.get("profesor_id") or "", curso_ref=a.get("curso_ref") or "",
            estado=a.get("estado") or "",
            referencia={"fuente": a.get("fuente_curso") or "", "leccion_ref": a.get("leccion_ref") or "", "curso": a.get("curso_rotulo") or "",
                        "leccion": a.get("leccion_rotulo") or ""},
            origen_actualizado_en=a.get("creada_en"))

    def documento(self, entidad_id: str) -> Documento | None:
        from modo_estudio import servicios as dueno

        return self._documento(dueno.asignacion(entidad_id))

    def documentos(self, entidad_ids: list[str]) -> dict[str, Documento]:
        salida = {}
        for entidad_id in entidad_ids:
            documento = self.documento(entidad_id)
            if documento is not None:
                salida[entidad_id] = documento
        return salida

    def todos(self) -> Iterator[Documento]:
        from modo_estudio import servicios as dueno

        for fila in dueno.asignaciones():
            documento = self._documento(fila)
            if documento is not None:
                yield documento


class FuenteClases:
    tipo = cat.CLASE
    fuente = cat.FUENTE_AULA

    @staticmethod
    def _tipos_de_evento() -> tuple[str, ...]:
        from classroom_engine.dominio import sesion as dom

        return (dom.EV_SESION_INICIADA, dom.EV_SESION_REANUDADA, dom.EV_SESION_SUSPENDIDA, dom.EV_SESION_FINALIZADA)

    def eventos_desde(self, secuencia: int, limite: int) -> tuple[list[dict], int]:
        from classroom_engine import servicios as dueno

        eventos, hasta = dueno.eventos_desde(secuencia, limite, self._tipos_de_evento())
        return [{"secuencia": e["secuencia"], "tipo": e["tipo"], "entidad_id": e["agregado_id"], "creado_en": e["creado_en"]}
                for e in eventos if e.get("agregado_id")], hasta

    def ultima_secuencia(self) -> int:
        from classroom_engine import servicios as dueno

        return dueno.ultima_secuencia()

    @staticmethod
    def _documento(s: dict | None) -> Documento | None:
        from classroom_engine.dominio import sesion as dom

        if not s or s.get("estado") == dom.ARCHIVADA:
            return None
        anclajes = " ".join(str(a.get("rotulo") or "") for a in (s.get("anclajes") or []) if isinstance(a, dict))
        titulo = s.get("leccion_rotulo") or s.get("objeto_rotulo") or s.get("curso_rotulo") or "Clase sin tema"
        return Documento(
            tipo=cat.CLASE, entidad_id=s["id"], titulo=titulo,
            descripcion=_texto(s.get("curso_rotulo") if titulo != s.get("curso_rotulo") else "", f"Grupo {s['grupo_rotulo']}" if s.get("grupo_rotulo") else ""),
            palabras=_unir(s.get("curso_rotulo"), s.get("leccion_rotulo"), s.get("objeto_rotulo"), anclajes),
            contexto=_unir(s.get("grupo_rotulo"), s.get("profesor_rotulo")), etiquetas="clase sesion", grupo_id=s.get("grupo_id") or "", profesor_id=s.get("profesor_id") or "",
            curso_ref=s.get("curso_ref") or "", estado=s.get("estado") or "",
            referencia={"fuente": s.get("fuente_curso") or "", "leccion_ref": s.get("leccion_ref") or "", "objeto_ref": s.get("objeto_ref") or "",
                        "curso": s.get("curso_rotulo") or "", "leccion": s.get("leccion_rotulo") or ""},
            origen_actualizado_en=s.get("finalizada_en") or s.get("iniciada_en") or s.get("creado_en"))

    def documento(self, entidad_id: str) -> Documento | None:
        from classroom_engine import servicios as dueno

        return self._documento(dueno.sesion(entidad_id))

    def documentos(self, entidad_ids: list[str]) -> dict[str, Documento]:
        salida = {}
        for entidad_id in entidad_ids:
            documento = self.documento(entidad_id)
            if documento is not None:
                salida[entidad_id] = documento
        return salida

    def todos(self) -> Iterator[Documento]:
        from classroom_engine import servicios as dueno

        for fila in dueno.sesiones():
            documento = self._documento(fila)
            if documento is not None:
                yield documento


class AulaMod7:
    """MOD-007 visto desde Search: sólo si hay una clase en curso."""

    def hay_sesion_activa(self) -> bool:
        from classroom_engine import servicios as dueno

        return dueno.hay_sesion_activa()
