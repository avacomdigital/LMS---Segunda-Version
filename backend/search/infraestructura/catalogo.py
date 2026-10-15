"""
El catálogo de AVACOM Biblioteca visto desde Search: cursos, lecciones y recursos, buscados EN VIVO (`GET /v2/search`) y nunca guardados (artículo 14).

La capa de biblioteca NO se modifica (decisión del proyecto): este adaptador sólo LEE con el cliente que ya existe (`biblioteca.contenido_v2`), igual que `evaluacion` y
`cola_medios`. Cada consulta vuelve a preguntar; lo que la biblioteca retira o la política del nodo desactiva deja de salir en ese mismo instante (TST-044), sin que
Search haga nada. Una biblioteca cerrada no es un error: se dice «no disponible» con su motivo y la búsqueda sigue con lo del LMS.

Lo que nunca se pide ni se devuelve: las preguntas (`scope=question`) —pueden ser de exámenes—, las claves de respuesta ni el contenido completo de una lección.
"""
from __future__ import annotations

import logging

from biblioteca import contenido_v2 as v2
from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible

from ..aplicacion.puertos import Impacto, ResultadoDelCatalogo
from ..dominio import catalogos as cat
from ..dominio import texto

log = logging.getLogger("avacom.search.catalogo")

_TIPO_DE_AMBITO = {"course": cat.CURSO, "lesson": cat.LECCION, "object": cat.RECURSO}


def _motivo(error: Exception) -> tuple[str, str]:
    if isinstance(error, BibliotecaNoDisponible):
        return error.motivo, error.sugerencia or ""
    if isinstance(error, BibliotecaError):
        return f"AVACOM Biblioteca respondió con un error ({error.codigo or error.estado}).", ""
    return "AVACOM Biblioteca no pudo atender la búsqueda.", ""


class CatalogoBiblioteca:
    def buscar(self, consulta: str, arbol: dict[str, str], tipos: tuple[str, ...], limite: int) -> ResultadoDelCatalogo:
        try:
            datos = v2._pedir("GET", "/v2/search", consulta={"q": consulta, "scope": "all", "profile": "teacher", **arbol})
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            if isinstance(error, BibliotecaError) and error.codigo == "invalid_parameter":
                log.warning("La biblioteca rechazó la búsqueda (%s)", error.detalle)
            motivo, sugerencia = _motivo(error)
            return ResultadoDelCatalogo(disponible=False, motivo=motivo, sugerencia=sugerencia)
        except Exception as error:   # noqa: BLE001 — nada de lo que pase al otro lado debe romper la búsqueda del LMS
            log.exception("Fallo inesperado al buscar en la biblioteca")
            motivo, sugerencia = _motivo(error)
            return ResultadoDelCatalogo(disponible=False, motivo=motivo, sugerencia=sugerencia)

        items = [i for i in v2._lista(datos, "items", "results", "hits") if isinstance(i, dict)]
        impactos: list[Impacto] = []
        for posicion, item in enumerate(items):
            tipo = _TIPO_DE_AMBITO.get(str(item.get("scope") or "").lower())
            curso_ref = str(item.get("courseId") or item.get("curso") or "")
            if tipo is None or tipo not in tipos or not curso_ref:
                continue                                        # una pregunta (o algo que no se pidió) no entra
            plano, resaltados = texto.quitar_marcas(str(item.get("snippet") or ""))
            ruta = tuple(str(n) for n in (item.get("treePath") or []) if n)
            impactos.append(Impacto(tipo=tipo, curso_ref=curso_ref, titulo=str(item.get("title") or curso_ref), leccion_ref=str(item.get("lessonId") or ""),
                                    objeto_ref=str(item.get("objectId") or ""), fragmento=plano, resaltados=tuple(resaltados), ruta_arbol=ruta, posicion=posicion))
            if len(impactos) >= limite:
                break
        total = datos.get("total") if isinstance(datos, dict) else None
        return ResultadoDelCatalogo(disponible=True, impactos=tuple(impactos), total=int(total) if isinstance(total, int) else len(impactos))

    def arbol(self) -> tuple[bool, str, list[dict]]:
        try:
            datos = v2._pedir("GET", "/v2/tree")
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            return False, _motivo(error)[0], []
        except Exception as error:   # noqa: BLE001
            log.exception("Fallo inesperado al leer el árbol de la biblioteca")
            return False, _motivo(error)[0], []
        return True, "", [n for n in v2._lista(datos, "items", "nodes", "tree") if isinstance(n, dict)]

    def cursos_del_arbol(self, arbol: dict[str, str]) -> set[str] | None:
        try:
            fichas = v2.cursos(**arbol)
        except Exception:   # noqa: BLE001 — sin la biblioteca no se puede saber qué cursos cuelgan de ese nodo
            return None
        return {str(f.get("courseId") or f.get("id")) for f in fichas if f.get("courseId") or f.get("id")}

    def existe(self, curso_ref: str, leccion_ref: str = "", objeto_ref: str = "") -> bool | None:
        try:
            esquema = v2.esquema_curso(curso_ref)
        except BibliotecaError as error:
            if error.estado == 404 or error.codigo in ("course_not_found", "not_found"):
                return False
            if error.codigo in ("policy_disabled", "disabled_by_policy"):
                return False
            return None
        except Exception:   # noqa: BLE001
            return None
        if not leccion_ref and not objeto_ref:
            return True
        for leccion in esquema.get("lessons") or []:
            if leccion_ref and str(leccion.get("id")) != leccion_ref:
                continue
            if not objeto_ref:
                return True
            if any(str(o.get("id")) == objeto_ref for o in leccion.get("objects") or []):
                return True
        return False
