"""
El árbol académico de AVACOM Biblioteca (país · nivel · grado · materia · tema) visto desde el libro, SÓLO para ponerle NOMBRE a las materias (el código ya viene en el
`curso_ref`: `dominio/curso.py`) y siempre EN VIVO: no se guarda nada (artículo 14). La capa de biblioteca NO se modifica: este adaptador sólo LEE con el cliente que ya
existe (`biblioteca.contenido_v2`), igual que Reportes y Search. Una biblioteca cerrada no es un error: las materias se muestran por su código en palabras.
"""
from __future__ import annotations

import logging

from biblioteca import contenido_v2 as v2
from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible

log = logging.getLogger("avacom.gradebook.arbol")


def _nombres(nodos: list, salida: dict[str, str]) -> None:
    for n in nodos:
        if not isinstance(n, dict):
            continue
        if n.get("kind") == "subject" and n.get("code"):
            salida.setdefault(str(n["code"]), str(n.get("name") or n["code"]))
        _nombres(n.get("children") or [], salida)


class ArbolBiblioteca:
    def __init__(self):
        self._cache: dict[str, str] | None = None

    def nombres_de_materias(self) -> dict[str, str]:
        """`{código de materia: nombre}` según el árbol de la biblioteca; vacío si no responde (y se anota, sin romper el libro). Se lee una vez por unidad de trabajo."""
        if self._cache is not None:
            return self._cache
        try:
            datos = v2._pedir("GET", "/v2/tree")
            nombres: dict[str, str] = {}
            _nombres([n for n in v2._lista(datos, "items", "nodes", "tree") if isinstance(n, dict)], nombres)
            self._cache = nombres
        except (BibliotecaNoDisponible, BibliotecaError) as error:
            log.info("AVACOM Biblioteca no entregó el árbol de materias: %s", getattr(error, "motivo", None) or getattr(error, "codigo", None) or error)
            self._cache = {}
        except Exception:   # noqa: BLE001 — nada de lo que pase al otro lado debe romper el libro
            log.exception("Fallo inesperado al leer el árbol de la biblioteca")
            self._cache = {}
        return self._cache
