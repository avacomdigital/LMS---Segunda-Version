"""
El árbol académico de AVACOM Biblioteca (país · nivel · grado · materia · tema) visto desde Reporting, sólo para FILTRAR (FUN-143) y siempre EN VIVO: no se guarda nada (artículo 14).
Igual que Search y la evaluación, la capa de biblioteca NO se modifica: este adaptador sólo LEE con el cliente que ya existe (`biblioteca.contenido_v2`). Una biblioteca cerrada no es un
error: el filtro no se aplica y se dice (el reporte sigue con todo lo demás).
"""
from __future__ import annotations

import logging

from biblioteca import contenido_v2 as v2
from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible

log = logging.getLogger("avacom.reporting.arbol")


def _motivo(error: Exception) -> str:
    if isinstance(error, BibliotecaNoDisponible):
        return error.motivo
    if isinstance(error, BibliotecaError):
        log.warning("AVACOM Biblioteca no entregó el árbol de materias (%s)", error.codigo or error.estado)
        return "AVACOM Biblioteca no pudo entregar las materias en este momento."      # sin el código técnico: quien lo lee es un profesor
    return "AVACOM Biblioteca no respondió."


class ArbolBiblioteca:
    def arbol(self) -> tuple[bool, str, list[dict]]:
        try:
            datos = v2._pedir("GET", "/v2/tree")
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            return False, _motivo(error), []
        except Exception as error:   # noqa: BLE001 — nada de lo que pase al otro lado debe romper un reporte
            log.exception("Fallo inesperado al leer el árbol de la biblioteca")
            return False, _motivo(error), []
        return True, "", [n for n in v2._lista(datos, "items", "nodes", "tree") if isinstance(n, dict)]

    def cursos_del_arbol(self, arbol: dict[str, str]) -> set[str] | None:
        try:
            fichas = v2.cursos(**arbol)
        except Exception:   # noqa: BLE001 — sin la biblioteca no se puede saber qué cursos cuelgan de ese nodo
            return None
        return {str(f.get("courseId") or f.get("id")) for f in fichas if f.get("courseId") or f.get("id")}
