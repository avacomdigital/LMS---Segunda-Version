"""
El examen visto desde la fuente de cursos del aula (`classroom_engine`): el `pool` para asignarlo y armar el examen de cada alumno, las preguntas SIN
CLAVES que ve un alumno y la calificación en la biblioteca. Se reutilizan la fuente (biblioteca real o manifiesto de ejemplo), la apertura de medios y
la normalización de preguntas del aula —la misma que ya pintan los controles de Student—; sólo cambia una cosa: las URL de los medios apuntan a las rutas
de este módulo (`/api/evaluacion/intentos/{id}/medios/…`), que sirven únicamente los medios de ESTE examen.

La capa de biblioteca y las fuentes de cursos NO se modifican: lo que sólo el examen necesita (esquema con objetos `exam`, `pool`, preguntas de un alumno)
lo pide `fuentes_examen`, que vive en este módulo.

Regla de oro (artículo 14): nada se cachea ni se guarda. Cada llamada vuelve a preguntar. La clave de una respuesta sólo vive en la biblioteca: aquí sólo
pasan lo que el alumno contestó y el veredicto que devuelve.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from django.db import transaction

from acceso.interfaces.medios import con_pase
from classroom_engine.aplicacion import casos_uso as casos_aula
from classroom_engine.aplicacion.puertos import Bytes
from classroom_engine.dominio import curso as curso_aula
from classroom_engine.dominio import errores as e7
from classroom_engine.dominio import respuestas as respuestas_aula
from classroom_engine.infraestructura.contenedor import servicios as servicios_aula

from cola_medios import servicio as cola

from ..dominio import armado as armado_dom
from ..dominio import errores as e10
from . import fuentes_examen


def traducir(error: Exception) -> Exception:
    """Un error del aula → su equivalente en MOD-010. Lo que no es del aula se deja tal cual."""
    if isinstance(error, e7.FuenteNoDisponible):
        return e10.FuenteNoDisponible(error.detalle, sugerencia=error.sugerencia, **error.extra)
    if isinstance(error, (e7.NoEncontrado, e7.DesactivadoPorPolitica)):
        return e10.NoEncontrado(error.detalle, codigo_fuente=error.codigo, **error.extra)
    if isinstance(error, e7.DatosInvalidos):
        return e10.DatosInvalidos(error.detalle, **error.extra)
    if isinstance(error, e7.ErrorAula):
        return e10.FuenteError(error.detalle, codigo_fuente=error.codigo, **error.extra)
    return error


def medios_de_preguntas(preguntas: list[dict]) -> set[str]:
    """Los `media_ref` que usan unas preguntas CRUDAS: `mediaIds` del enunciado y `mediaId` de opciones, parejas y elementos."""
    ids: set[str] = set()
    for p in preguntas or []:
        if not isinstance(p, dict):
            continue
        ids.update(str(m) for m in (p.get("mediaIds") or []) if m)
        for clave in ("options", "left", "right", "items"):
            for item in p.get(clave) or []:
                if isinstance(item, dict) and item.get("mediaId"):
                    ids.add(str(item["mediaId"]))
    return ids


class ContenidoEvaluacion:
    """Implementa el puerto `Contenido` con `classroom_engine`."""

    @staticmethod
    def _origen(fuente: str, curso_ref: str):
        try:
            return servicios_aula().fuente(fuente or None, curso_ref)
        except e7.ErrorAula as error:
            raise traducir(error) from error

    # ----------------------------------------------------------------------- para asignar
    def examen(self, fuente: str, curso_ref: str, objeto_ref: str) -> dict:
        origen = self._origen(fuente, curso_ref)
        try:
            esquema = fuentes_examen.esquema(origen, curso_ref)
            pool = fuentes_examen.examen_pool(origen, curso_ref, objeto_ref)
        except e7.ErrorAula as error:
            raise traducir(error) from error
        leccion = objeto = None
        for l in esquema.get("lessons") or []:
            for o in l.get("objects") or []:
                if str(o.get("id")) == objeto_ref:
                    leccion, objeto = l, o
        if objeto is None or objeto.get("type") != "exam":
            raise e10.NoEncontrado(f"«{objeto_ref}» no es un examen de ese curso.", curso_ref=curso_ref, objeto_ref=objeto_ref)
        lista = armado_dom.normalizar_pool(pool)
        if not lista:
            raise e10.DatosInvalidos("El banco de preguntas de ese examen está vacío.", objeto_ref=objeto_ref)
        return {
            "fuente": origen.nombre, "curso_ref": str(esquema.get("courseId") or esquema.get("id") or curso_ref),
            "curso_version": str(pool.get("version") or esquema.get("version") or ""), "curso_rotulo": str(esquema.get("title") or ""),
            "leccion_ref": str((leccion or {}).get("id") or ""), "objeto_rotulo": str(objeto.get("title") or ""),
            "titulo": str(objeto.get("title") or "Examen"), "ajustes": armado_dom.ajustes_de_biblioteca(pool.get("settings") or {}), "pool": lista,
        }

    def version_instalada(self, fuente: str, curso_ref: str) -> str | None:
        try:
            estado = self._origen(fuente, curso_ref).estado()
        except Exception:      # noqa: BLE001 — la versión es un dato de cortesía
            return None
        for curso in estado.get("cursos_instalados") or []:
            if str(curso.get("curso_ref")) == curso_ref:
                return str(curso.get("version") or "") or None
        return None

    # ------------------------------------------------------------------ lo que ve UN alumno
    def _crudo(self, fuente: str, curso_ref: str, version: str, objeto_ref: str, refs: list[str], semilla: str):
        origen = self._origen(fuente, curso_ref)
        try:
            datos = fuentes_examen.examen_preguntas(origen, curso_ref, objeto_ref, list(refs), semilla or None)
        except e7.ErrorAula as error:
            raise traducir(error) from error
        instalada = str(datos.get("version") or "")
        if version and instalada and version != instalada:
            raise e10.VersionNoDisponible(
                f"El curso cambió de versión ({version} → {instalada}) desde que se asignó el examen: tu profesor debe volver a asignarlo.",
                asignada=version, instalada=instalada)
        return origen, datos

    @staticmethod
    def _url_de_medios(intento_id: str, dispositivo: str, alumno_id: str):
        """Las URL de los medios de un intento. Llevan `dispositivo` y `alumno_id` porque las pide un visor (WebView, imagen) que no puede mandar
        cabeceras: así la ruta sabe quién pregunta y desde dónde."""
        consulta = urlencode([(k, v) for k, v in (("dispositivo", dispositivo), ("alumno_id", alumno_id)) if v])

        def url(media_ref: str, ruta: str | None) -> str:
            base = f"/api/evaluacion/intentos/{quote(intento_id, safe='')}/medios/{quote(media_ref, safe='')}/"
            if ruta:
                base += quote(ruta.strip("/"), safe="/")
            return con_pase(f"{base}?{consulta}" if consulta else base)

        return url

    def preguntas(self, fuente: str, curso_ref: str, version: str, objeto_ref: str, refs: list[str], semilla: str, *, intento_id: str,
                  dispositivo: str, alumno_id: str) -> dict:
        origen, datos = self._crudo(fuente, curso_ref, version, objeto_ref, refs, semilla)
        crudas = [q for q in datos.get("questions") or [] if isinstance(q, dict)]
        medios: list[dict] = []
        if medios_de_preguntas(crudas):
            try:
                medios = [m for m in fuentes_examen.esquema(origen, curso_ref).get("media") or [] if isinstance(m, dict)]
            except e7.ErrorAula as error:
                raise traducir(error) from error
        vistas = fuentes_examen.preguntas_de_examen(crudas, medios, self._url_de_medios(intento_id, dispositivo, alumno_id))
        # Los medios de ESTAS preguntas (las de este alumno en este intento, no el banco entero) quedan en la cola del nodo con la prioridad de un examen:
        # el reloj del alumno corre. Se hace al confirmarse la transacción (la cola escribe en su propia tabla y no debe esperar a ésta).
        medios_del_intento = [(ref, "") for ref in sorted(medios_de_preguntas(crudas))]
        if medios_del_intento:
            transaction.on_commit(lambda: cola.preparar_medios(medios_del_intento, fuente=fuente or None, curso_ref=curso_ref, modulo=cola.MODULO_EVALUACION,
                                                               contexto_ref=intento_id, prioridad=cola.EVALUACION, persona_id=alumno_id,
                                                               dispositivo_id=dispositivo))
        por_ref = {p["pregunta_ref"]: p for p in vistas}
        return {"titulo": datos.get("title"), "instrucciones": datos.get("instructions"),
                "instrucciones_tramos": curso_aula.tramos(datos.get("instructions")), "version": str(datos.get("version") or ""),
                "preguntas": [por_ref[r] for r in refs if r in por_ref]}

    def medios_de(self, fuente: str, curso_ref: str, version: str, objeto_ref: str, refs: list[str], semilla: str) -> set[str]:
        _, datos = self._crudo(fuente, curso_ref, version, objeto_ref, refs, semilla)
        return medios_de_preguntas([q for q in datos.get("questions") or []])

    def abrir_medio(self, fuente: str, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        """Por la cola de medios del nodo (con la prioridad de un examen). Quien llama (`MedioDelIntento`) ya comprobó que el medio es de ESTE examen y de
        ESTE alumno: la cola sólo reparte bytes, nunca decide quién los lee. Sin la cola, paso a través como siempre."""
        def directo() -> Bytes:
            try:
                return casos_aula.AbrirMedio(servicios_aula()).ejecutar(curso_ref, media_ref, ruta, rango, metodo, fuente or None)
            except e7.ErrorAula as error:
                raise traducir(error) from error

        try:
            return cola.abrir_medio(fuente=fuente or None, curso_ref=curso_ref, media_ref=media_ref, ruta=ruta, rango=rango, metodo=metodo,
                                    modulo=cola.MODULO_EVALUACION, prioridad=cola.EVALUACION, directo=directo)
        except e7.ErrorAula as error:
            raise traducir(error) from error

    # ---------------------------------------------------------------------------- calificar
    def calificar(self, fuente: str, curso_ref: str, version: str, items: list[dict]) -> dict[str, dict | None]:
        """La clave se compara DONDE VIVE, en UNA llamada por lote y siempre con la versión del intento. Sin biblioteca (o sin la capacidad) todo
        queda sin calificar; si el lote falla por una respuesta mal formada, se prueban una por una (con tope) para no dejar sin veredicto a las
        demás."""
        sin_nota: dict[str, dict | None] = {i["pregunta_ref"]: None for i in items}
        if not items:
            return {}
        try:
            origen = self._origen(fuente, curso_ref)
        except Exception:      # noqa: BLE001 — sin fuente no hay veredicto, pero la respuesta se guarda
            return sin_nota
        lote = [{"objectId": i["objeto_ref"], "questionId": i["pregunta_ref"], "response": dict(i["respuesta"])} for i in items]
        try:
            crudos = origen.evaluar_lote(curso_ref, version, lote)
            por_pregunta = {str(c.get("questionId") or ""): c for c in crudos}
            return {i["pregunta_ref"]: respuestas_aula.veredicto(por_pregunta.get(i["pregunta_ref"], crudos[n] if n < len(crudos) else {}), i["pregunta_ref"])
                    for n, i in enumerate(items)}
        except (e7.FuenteNoDisponible, e7.CapacidadAusente):
            return sin_nota                    # la fuente no está: probar una por una sólo sumaría esperas
        except Exception:      # noqa: BLE001
            pass
        veredictos = dict(sin_nota)
        for i in items[:20]:
            try:
                crudo = origen.evaluar(curso_ref, version, i["objeto_ref"], i["pregunta_ref"], dict(i["respuesta"]))
                veredictos[i["pregunta_ref"]] = respuestas_aula.veredicto(crudo, i["pregunta_ref"])
            except Exception:      # noqa: BLE001
                veredictos[i["pregunta_ref"]] = None
        return veredictos
