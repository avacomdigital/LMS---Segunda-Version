"""
Buscar (FUN-211 · FUN-213) y abrir un resultado.

El orden de lo que ocurre en una consulta es lo que hace que BR-088 se cumpla aunque el índice esté rezagado:

  1. permiso `search.query` y lo que la persona puede LEER ahora (MOD-001, datos vigentes: tipos, alcance y grupos).
  2. el índice local propone candidatos: la consulta de texto completo YA lleva las reglas de lectura y los filtros en la propia consulta SQL (antes de ordenar, de
     verificar y de paginar).
  3. cada candidato se VERIFICA en vivo con su módulo propietario: existe, es buscable, su grupo sigue activo y la persona sigue pudiendo leerlo con lo que valen
     AHORA su grupo y su dueño. Lo que no pasa se descarta; lo que el dueño ya no tiene se purga del índice.
  4. el catálogo de la biblioteca (cursos, lecciones, recursos) se pregunta en vivo; lo que ella retiró no aparece, y a lo suyo sólo se le aplica `content.read`.
  5. se puntúa todo con la misma escala, se ordena, se CUENTA lo visible y recién entonces se pagina.

Un candidato que no pasa la verificación no cuenta en el total, no aparece y no deja rastro en lo devuelto (ni fragmento, ni sugerencia, ni conteo).
"""
from __future__ import annotations

import logging
from collections import defaultdict

from ..dominio import catalogos as cat
from ..dominio import consulta as dom_consulta
from ..dominio import ranking, texto
from ..dominio.documento import Documento, Visibilidad
from ..dominio.errores import CatalogoNoDisponible, DatosInvalidos, NoEncontrado
from .base import _CasoDeUso, estado_del_indice
from .indexar import Purgar, Sincronizar
from .puertos import Actor, Regla

log = logging.getLogger("avacom.search.buscar")

ANCHO_DE_DESCRIPCION = 220


def _breve(descripcion: str, ancho: int = ANCHO_DE_DESCRIPCION) -> str:
    limpio = " ".join(str(descripcion or "").split())
    return limpio if len(limpio) <= ancho else limpio[: ancho - 1].rstrip() + "…"


def objetivo_de_navegacion(doc: Documento) -> dict:
    """Lo que el cliente necesita para abrir la entidad en SU módulo (no hay una pantalla paralela de Search)."""
    return {"entity_type": doc.tipo, "entity_id": doc.entidad_id, "group_id": doc.grupo_id, "course_ref": doc.curso_ref,
            "lesson_ref": str(doc.referencia.get("leccion_ref") or ""), "object_ref": str(doc.referencia.get("objeto_ref") or ""),
            "source": str(doc.referencia.get("fuente") or "")}


class Buscar(_CasoDeUso):
    def ejecutar(self, actor: Actor, parametros: dict) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_CONSULTAR)
        consulta = dom_consulta.interpretar(parametros)
        visibilidad = s.autorizacion.visibilidad(actor)
        self._poner_al_dia()
        estado = estado_del_indice(s)

        pedidos = consulta.filtros.tipos or cat.TIPOS
        tipos = tuple(t for t in cat.TIPOS if t in pedidos and t in visibilidad.tipos)         # un tipo que no puede leer se ignora: no se revela que existe
        tipos_locales = tuple(t for t in tipos if t in cat.TIPOS_LOCALES)
        tipos_catalogo = tuple(t for t in tipos if t in cat.TIPOS_DE_CATALOGO)

        with s.uow(lectura=True) as uow:
            sinonimos = uow.sinonimos.mapa()
        aviso_de_filtro = ""
        locales, modo, tope_local, obsoletos = [], "all", False, defaultdict(list)
        if tipos_locales:
            locales, modo, tope_local, obsoletos, aviso_de_filtro = self._locales(consulta, visibilidad, tipos_locales, sinonimos)

        catalogo = None
        if tipos_catalogo and visibilidad.contenido and not consulta.filtros.hay_ambito_de_grupo:
            catalogo = s.catalogo.buscar(consulta.original, consulta.filtros.del_arbol, tipos_catalogo, cat.TOPE_DEL_CATALOGO)

        resultados = [*self._pintar_locales(consulta, locales), *(self._pintar_catalogo(consulta, catalogo) if catalogo and catalogo.disponible else [])]
        resultados.sort(key=lambda r: (-r["score"], cat.TIPOS.index(r["entity_type"]), texto.normalizar(r["title"]), r["entity_id"]))
        total = len(resultados)
        pagina = resultados[consulta.desplazamiento: consulta.desplazamiento + consulta.limite]
        exacto = not tope_local and not (catalogo and catalogo.disponible and catalogo.total > len(catalogo.impactos))

        self._purgar(obsoletos)
        return {
            "query": consulta.original,
            "normalized": consulta.normal,
            "total": total,
            "total_exact": exacto,
            "page": consulta.pagina,
            "page_size": consulta.limite,
            "has_more": consulta.desplazamiento + consulta.limite < total,
            "results": pagina,
            "filters_applied": consulta.filtros.como_dict(),
            "match_mode": modo,
            "index_status": estado["estado"],
            "index_notice": estado["aviso"],
            "sources": {
                "local": {"status": "ok" if tipos_locales else "not_requested", "types": list(tipos_locales)},
                "catalog": {"status": ("unavailable" if catalogo and not catalogo.disponible else "ok" if catalogo else "not_requested"),
                            "reason": catalogo.motivo if catalogo and not catalogo.disponible else "",
                            "hint": catalogo.sugerencia if catalogo and not catalogo.disponible else ""},
            },
            "notice": aviso_de_filtro,
        }

    # ------------------------------------------------------------------------------------------------ el índice local
    def _poner_al_dia(self) -> None:
        """Antes de responder, el índice se pone al día con lo que los módulos ya publicaron (el hilo del nodo puede ir unos segundos detrás). Un fallo aquí no impide
        consultar lo que ya hay: se dirá «rezagado»."""
        if not self.s.config.sincronizar_al_consultar:
            return
        try:
            Sincronizar(self.s).hasta_vaciar(paginas=self.s.config.paginas_al_consultar)
        except Exception:   # noqa: BLE001
            log.exception("Search no pudo ponerse al día antes de responder")

    def _locales(self, consulta, visibilidad: Visibilidad, tipos: tuple[str, ...], sinonimos: dict):
        """`(candidatos verificados, modo, truncado, obsoletos por tipo, aviso)`. Cada candidato es `(fila del índice, documento vigente, grupo vigente)`."""
        s = self.s
        filtros = consulta.filtros
        vacio = ([], "all", False, defaultdict(list), "")
        grupo_ids: set[str] | None = None
        if filtros.grupo_id:
            grupo_ids = {filtros.grupo_id}
        if filtros.periodo:
            del_periodo = set(s.identidad.grupos_de_periodo(filtros.periodo))
            grupo_ids = del_periodo if grupo_ids is None else grupo_ids & del_periodo
        curso_refs: set[str] | None = None
        if filtros.hay_arbol:
            curso_refs = s.catalogo.cursos_del_arbol(filtros.del_arbol)
            if curso_refs is None:
                return (*vacio[:4], "AVACOM Biblioteca no contestó: no se puede aplicar el filtro por materia, grado o nivel a evaluaciones, estudios y clases.")
        if (grupo_ids is not None and not grupo_ids) or (curso_refs is not None and not curso_refs):
            return vacio

        reglas = [Regla(t, visibilidad.alcance_de(t), tuple(sorted(visibilidad.grupos)), visibilidad.persona_id) for t in tipos]
        argumentos = dict(grupo_ids=sorted(grupo_ids) if grupo_ids is not None else None, curso_refs=sorted(curso_refs) if curso_refs is not None else None,
                          tope=cat.TOPE_DE_CANDIDATOS)
        with s.uow(lectura=True) as uow:
            filas = uow.indice.buscar(dom_consulta.expresion_match(consulta, sinonimos, todas=True), reglas, **argumentos)
            modo = "all"
            if not filas and len(consulta.raices) > 1:        # ninguna entidad tiene TODAS las palabras: se relaja a «alguna» (las que tienen más, salen primero)
                filas = uow.indice.buscar(dom_consulta.expresion_match(consulta, sinonimos, todas=False), reglas, **argumentos)
                modo = "any"
        truncado = len(filas) >= cat.TOPE_DE_CANDIDATOS

        # ---- verificación EN VIVO con el dueño
        vivos: dict[tuple[str, str], Documento] = {}
        obsoletos: dict[str, list[str]] = defaultdict(list)
        por_tipo: dict[str, list[str]] = defaultdict(list)
        for fila in filas:
            por_tipo[fila["tipo"]].append(fila["entidad_id"])
        for tipo, ids in por_tipo.items():
            actuales = s.fuentes[tipo].documentos(ids)
            for entidad_id in ids:
                if entidad_id in actuales:
                    vivos[(tipo, entidad_id)] = actuales[entidad_id]
                else:
                    obsoletos[tipo].append(entidad_id)
        grupos = s.identidad.grupos(sorted({d.grupo_id for d in vivos.values() if d.grupo_id}))
        verificados = []
        for fila in filas:
            doc = vivos.get((fila["tipo"], fila["entidad_id"]))
            if doc is None:
                continue
            grupo = grupos.get(doc.grupo_id) if doc.grupo_id else None
            if doc.grupo_id and (grupo is None or not grupo.get("activo")):
                continue                                                        # su grupo se desactivó: la entidad deja de aparecer (existe, pero no se busca)
            if not visibilidad.puede_leer(doc.tipo, doc.grupo_id, doc.profesor_id):
                continue                                                        # BR-088 con lo que vale AHORA, no con lo que valía al indexar
            if grupo_ids is not None and doc.grupo_id not in grupo_ids:
                continue
            if curso_refs is not None and doc.curso_ref not in curso_refs:
                continue
            verificados.append((fila, doc, grupo))
        return verificados, modo, truncado, obsoletos, ""

    def _pintar_locales(self, consulta, candidatos) -> list[dict]:
        salida = []
        ultima = consulta.raices[-1] if consulta.raices else ""
        for fila, doc, grupo in candidatos:
            puntaje, escalon = ranking.puntuar(consulta, titulo=doc.titulo, palabras=doc.palabras, descripcion=doc.descripcion, contexto=doc.contexto, bm25=fila["bm25"])
            resumen = doc.descripcion or " · ".join(p for p in (str(doc.referencia.get("curso") or ""), str(doc.referencia.get("leccion") or "")) if p)
            fragmento, resaltados = texto.fragmento(resumen, list(consulta.raices), prefijo_final=bool(ultima))
            salida.append({
                "id": doc.entidad_id, "entity_type": doc.tipo, "entity_id": doc.entidad_id, "subtype": doc.subtipo,
                "title": doc.titulo, "description": _breve(resumen), "snippet": fragmento, "highlights": [list(r) for r in resaltados],
                "score": puntaje, "match": escalon, "source": "local", "status": doc.estado,
                "context": {"group_id": doc.grupo_id, "group_name": (grupo or {}).get("nombre", ""), "period": (grupo or {}).get("periodo", ""),
                            "course_ref": doc.curso_ref, "course_label": str(doc.referencia.get("curso") or ""),
                            "lesson_label": str(doc.referencia.get("leccion") or ""), "tree_path": []},
                "navigation_target": objetivo_de_navegacion(doc),
            })
        return salida

    # ------------------------------------------------------------------------------------------------ el catálogo (en vivo)
    def _pintar_catalogo(self, consulta, catalogo) -> list[dict]:
        salida, vistos = [], set()
        total = len(catalogo.impactos)
        for impacto in catalogo.impactos:
            clave = (impacto.tipo, impacto.curso_ref, impacto.leccion_ref, impacto.objeto_ref)
            if clave in vistos:
                continue
            vistos.add(clave)
            puntaje, escalon = ranking.puntuar(consulta, titulo=impacto.titulo, descripcion=impacto.fragmento, posicion=impacto.posicion, total=total)
            entidad_id = impacto.objeto_ref or impacto.leccion_ref or impacto.curso_ref
            salida.append({
                "id": entidad_id, "entity_type": impacto.tipo, "entity_id": entidad_id, "subtype": "",
                "title": impacto.titulo, "description": _breve(impacto.fragmento), "snippet": impacto.fragmento, "highlights": [list(r) for r in impacto.resaltados],
                "score": puntaje, "match": escalon, "source": "catalog", "status": "",
                "context": {"group_id": "", "group_name": "", "period": "", "course_ref": impacto.curso_ref, "course_label": "", "lesson_label": "",
                            "tree_path": list(impacto.ruta_arbol)},
                "navigation_target": {"entity_type": impacto.tipo, "entity_id": entidad_id, "group_id": "", "course_ref": impacto.curso_ref,
                                      "lesson_ref": impacto.leccion_ref, "object_ref": impacto.objeto_ref, "source": "biblioteca"},
            })
        return salida

    def _purgar(self, obsoletos: dict[str, list[str]]) -> None:
        for tipo, ids in obsoletos.items():
            try:
                Purgar(self.s).ejecutar(tipo, ids)
            except Exception:   # noqa: BLE001 — limpiar el índice es un favor: si falla, el próximo ciclo lo hará
                log.exception("No se pudieron purgar %s entradas obsoletas de %s", len(ids), tipo)


class Abrir(_CasoDeUso):
    """§7 punto 6: al abrir un resultado se VUELVE a comprobar el permiso sobre el recurso original, con lo vigente. El índice pudo ir rezagado y la persona pudo perder
    el acceso entre la búsqueda y el toque. No se distingue «no existe» de «no puedes leerlo»: no se revela qué hay."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_CONSULTAR)
        tipo = str(datos.get("entity_type") or datos.get("type") or "").strip().lower()
        entidad_id = str(datos.get("entity_id") or datos.get("id") or "").strip()
        if tipo not in cat.TIPOS:
            raise DatosInvalidos("«entity_type» no es un tipo de resultado conocido.", parametro="entity_type", validos=list(cat.TIPOS))
        if not entidad_id or len(entidad_id) > 250:
            raise DatosInvalidos("Falta «entity_id».", parametro="entity_id")
        visibilidad = s.autorizacion.visibilidad(actor)
        if tipo in cat.TIPOS_LOCALES:
            return self._local(actor, visibilidad, tipo, entidad_id)
        return self._catalogo(actor, visibilidad, tipo, entidad_id, datos)

    def _local(self, actor: Actor, visibilidad: Visibilidad, tipo: str, entidad_id: str) -> dict:
        s = self.s
        doc = s.fuentes[tipo].documento(entidad_id)
        if doc is None:
            raise NoEncontrado("Ese resultado ya no está disponible.")
        if doc.grupo_id:
            grupo = s.identidad.grupos([doc.grupo_id]).get(doc.grupo_id)
            if grupo is None or not grupo.get("activo"):
                raise NoEncontrado("Ese resultado ya no está disponible.")
        if not visibilidad.puede_leer(tipo, doc.grupo_id, doc.profesor_id):
            self._denegar(actor, cat.PERMISO_DE_LECTURA[tipo], {"entity_type": tipo, "entity_id": entidad_id})
            raise NoEncontrado("Ese resultado ya no está disponible.")
        return {"allowed": True, "verified": True, "navigation_target": objetivo_de_navegacion(doc)}

    def _catalogo(self, actor: Actor, visibilidad: Visibilidad, tipo: str, entidad_id: str, datos: dict) -> dict:
        s = self.s
        if not visibilidad.contenido:
            self._denegar(actor, cat.PERMISO_DE_LECTURA[tipo], {"entity_type": tipo, "entity_id": entidad_id})
            raise NoEncontrado("Ese resultado ya no está disponible.")
        curso_ref = str(datos.get("course_ref") or (entidad_id if tipo == cat.CURSO else "")).strip()
        if not curso_ref:
            raise DatosInvalidos("Falta «course_ref» para abrir una lección o un recurso.", parametro="course_ref")
        leccion_ref = str(datos.get("lesson_ref") or (entidad_id if tipo == cat.LECCION else "")).strip()
        objeto_ref = str(datos.get("object_ref") or (entidad_id if tipo == cat.RECURSO else "")).strip()
        existe = s.catalogo.existe(curso_ref, leccion_ref, objeto_ref)
        if existe is None:
            raise CatalogoNoDisponible("AVACOM Biblioteca no contestó: sin ella no se puede abrir el contenido. Abre la aplicación de contenido y vuelve a intentarlo.")
        if not existe:
            raise NoEncontrado("Ese resultado ya no está disponible.")
        return {"allowed": True, "verified": True, "navigation_target": {
            "entity_type": tipo, "entity_id": entidad_id, "group_id": "", "course_ref": curso_ref, "lesson_ref": leccion_ref, "object_ref": objeto_ref, "source": "biblioteca"}}

    def _denegar(self, actor: Actor, permiso: str, objeto: dict) -> None:
        """Un intento de abrir lo que no se puede leer deja asiento propio (con quién, qué permiso pedía y sobre qué)."""
        try:
            with self.s.uow() as uow:
                uow.auditoria.denegada(actor.id, permiso, objeto)
        except Exception:   # noqa: BLE001 — la negativa ya se dio; no fallar la respuesta por el asiento
            log.exception("No se pudo asentar la apertura denegada")

