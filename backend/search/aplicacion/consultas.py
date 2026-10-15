"""
Las demás lecturas de Search: las opciones de los filtros, el estado del índice y los sinónimos.

Nada de lo que aquí se devuelve revela recursos que la persona no puede leer: los tipos y los grupos son los SUYOS, el árbol es el de la biblioteca (público para quien
lee contenido) y los conteos del índice sólo los ve quien lo mantiene (`search.reindex`).
"""
from __future__ import annotations

from ..dominio import catalogos as cat
from ..dominio import texto
from ..dominio.errores import DatosInvalidos
from .base import _CasoDeUso, estado_del_indice
from .indexar import Sincronizar
from .puertos import Actor


def _aplanar(nodos: list[dict]) -> dict[str, list[dict]]:
    """El árbol de la biblioteca como listas de valores distintos por nivel (`country`, `level`, `grade`, `subject`, `topic`), en el orden en que aparecen."""
    listas: dict[str, dict[str, dict]] = {"country": {}, "level": {}, "grade": {}, "subject": {}, "topic": {}}

    def recorrer(nodo: dict) -> None:
        tipo = str(nodo.get("kind") or "")
        codigo = str(nodo.get("code") or "")
        if tipo in listas and codigo and codigo not in listas[tipo]:
            listas[tipo][codigo] = {"code": codigo, "name": str(nodo.get("name") or codigo)}
        for hijo in nodo.get("children") or []:
            recorrer(hijo)

    for nodo in nodos:
        recorrer(nodo)
    return {k: list(v.values()) for k, v in listas.items()}


def _recortar(nodos: list[dict]) -> list[dict]:
    return [{"kind": n.get("kind"), "code": n.get("code"), "name": n.get("name"), "count": n.get("count"), "children": _recortar(n.get("children") or [])} for n in nodos]


class OpcionesDeFiltros(_CasoDeUso):
    """FUN-211 · CAP-125. Los valores que se pueden elegir, SOLO los válidos para quien consulta: sus tipos, sus grupos (los que enseña; la administración, todos los
    activos) y los periodos de esos grupos. El árbol académico es el de la biblioteca (no se crea un catálogo paralelo)."""

    def ejecutar(self, actor: Actor) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_CONSULTAR)
        visibilidad = s.autorizacion.visibilidad(actor)
        tipos = [{"value": t, "label": cat.ROTULOS_DE_TIPO[t]} for t in visibilidad.tipos]

        disponible, motivo, nodos = (True, "", [])
        if visibilidad.contenido or visibilidad.tipos_locales:
            disponible, motivo, nodos = s.catalogo.arbol()

        grupos: list[dict] = []
        if visibilidad.tipos_locales:
            if any(visibilidad.alcance_de(t) == cat.ORGANIZACION for t in visibilidad.tipos_locales):
                filas = s.identidad.grupos_activos()
            else:
                filas = [g for g in s.identidad.grupos(sorted(visibilidad.grupos)).values() if g.get("activo")]
            grupos = sorted(({"id": g["id"], "name": g["nombre"], "code": g.get("codigo", ""), "period": g.get("periodo", ""), "level": g.get("nivel_clave", "")}
                             for g in filas), key=lambda g: (g["name"].lower(), g["id"]))
        periodos = sorted({g["period"] for g in grupos if g["period"]}, reverse=True)
        arbol = _aplanar(nodos)
        return {
            "types": tipos,
            "tree": _recortar(nodos),
            "countries": arbol["country"], "levels": arbol["level"], "grades": arbol["grade"], "subjects": arbol["subject"], "topics": arbol["topic"],
            "groups": grupos,
            "periods": periodos,
            "current_period": periodos[0] if periodos else "",
            "catalog": {"status": "ok" if disponible else "unavailable", "reason": "" if disponible else motivo},
        }


class EstadoDelIndice(_CasoDeUso):
    """El estado que ve cualquiera que busca (consultable, rezagado…, con su aviso) y, para quien mantiene el índice (`search.reindex`), el detalle: conteos por tipo,
    marcas de lectura y lo que cada módulo tiene sin aplicar."""

    def ejecutar(self, actor: Actor) -> dict:
        s = self.s
        puede_consultar, puede_mantener = s.autorizacion.tiene(actor, cat.P_CONSULTAR), s.autorizacion.tiene(actor, cat.P_REINDEXAR)
        if not (puede_consultar or puede_mantener):
            s.autorizacion.exigir(actor, cat.P_CONSULTAR)
        estado = estado_del_indice(s)
        resultado = {"index_status": estado["estado"], "index_notice": estado["aviso"], "queryable": True}
        if puede_mantener:
            with s.uow(lectura=True) as uow:
                documentos = uow.indice.contar()
            guardado = estado["guardado"]
            catalogo_disponible, catalogo_motivo, _ = s.catalogo.arbol()
            resultado["detail"] = {
                "documents": documentos, "total": sum(documentos.values()),
                "built_at": guardado.get("construido_en"), "synchronized_at": guardado.get("sincronizado_en"),
                "last_error": guardado.get("error") or "", "last_error_at": guardado.get("error_en"),
                "sources": {nombre: {"mark": m.get("secuencia", 0), "failures": m.get("fallos", 0), "pending": estado["pendientes"].get(nombre, 0)}
                            for nombre, m in estado["marcas"].items()},
                "pending": estado["pendientes"],
                "catalog": {"status": "ok" if catalogo_disponible else "unavailable", "reason": "" if catalogo_disponible else catalogo_motivo},
            }
        return resultado


class PonerAlDia(_CasoDeUso):
    """`POST /api/search/sync/`: aplica ya lo pendiente de las colas de los módulos (lo mismo que hace solo el hilo del nodo)."""

    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_REINDEXAR)
        return Sincronizar(self.s).hasta_vaciar(paginas=200)


class Sinonimos(_CasoDeUso):
    """Los sinónimos son de Search, no del contenido académico: grupos de palabras equivalentes que se aplican al consultar. Los administra quien mantiene el índice."""

    def listar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_REINDEXAR)
        with self.s.uow(lectura=True) as uow:
            return {"groups": uow.sinonimos.grupos()}

    def reemplazar(self, actor: Actor, datos: dict) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_REINDEXAR)
        crudos = datos.get("groups")
        if not isinstance(crudos, list):
            raise DatosInvalidos("«groups» debe ser una lista de grupos de palabras equivalentes.", parametro="groups")
        if len(crudos) > cat.MAX_SINONIMOS:
            raise DatosInvalidos(f"Demasiados grupos (máximo {cat.MAX_SINONIMOS}).", parametro="groups")
        grupos: list[list[str]] = []
        for crudo in crudos:
            if not isinstance(crudo, list):
                raise DatosInvalidos("Cada grupo debe ser una lista de palabras.", parametro="groups")
            palabras = list(dict.fromkeys(texto.normalizar(p) for p in crudo if isinstance(p, str) and texto.normalizar(p)))
            if len(palabras) < 2:
                continue                                  # un grupo de una sola palabra no equivale a nada
            if any(len(p) > cat.MAX_CONSULTA for p in palabras):
                raise DatosInvalidos("Una palabra es demasiado larga.", parametro="groups")
            grupos.append(palabras)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            uow.sinonimos.reemplazar(grupos, ahora, actor.id or cat.SISTEMA)
            uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_SINONIMOS_CONFIGURADOS, "m21_sinonimo", "", nuevo={"grupos": len(grupos)})
        return {"groups": grupos}
