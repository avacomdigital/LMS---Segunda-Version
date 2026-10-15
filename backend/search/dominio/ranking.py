"""
La relevancia de un resultado. Una política en cinco escalones, de más a menos útil, que es la que se propuso para el MVP y que NO es una regla institucional fija:

  1. el título es exactamente lo buscado                       1.00
  2. el título contiene todas las palabras / alguna de ellas   0.80 · 0.55–0.65
  3. las palabras clave (curso, lección, materia…) lo contienen 0.45–0.50
  4. la descripción lo contiene                                 0.30–0.35
  5. sólo el contexto (grupo, profesor…) o un sinónimo          0.10–0.20

Dentro de cada escalón desempata `bm25` (el motor de texto completo), que sólo suma hasta 0.04: nunca salta un escalón. Los resultados del catálogo (que la
biblioteca ya ordenó por su cuenta y no trae `bm25`) se puntúan con la MISMA escala y se desempatan por la posición que la biblioteca les dio.
"""
from __future__ import annotations

from . import texto

EXACTO = "titulo_exacto"
TITULO = "titulo"
PALABRAS_CLAVE = "palabras_clave"
DESCRIPCION = "descripcion"
CONTEXTO = "contexto"
SINONIMO = "sinonimo"


def _cubre(raices_buscadas: tuple[str, ...], campo: set[str], prefijo_final: bool) -> int:
    """Cuántas de las raíces buscadas están en el campo (la última, también por prefijo si se está escribiendo)."""
    n = 0
    for i, buscada in enumerate(raices_buscadas):
        if buscada in campo or (prefijo_final and i == len(raices_buscadas) - 1 and any(c.startswith(buscada) for c in campo)):
            n += 1
    return n


def puntuar(consulta, *, titulo: str, palabras: str = "", descripcion: str = "", contexto: str = "", bm25: float | None = None,
            posicion: int | None = None, total: int | None = None) -> tuple[float, str]:
    """`(puntaje 0..1, escalón)`. `bm25` es el que devuelve FTS5 (negativo: más negativo, mejor); `posicion`/`total`, para lo que no lo trae."""
    buscadas = consulta.raices
    cantidad = max(1, len(buscadas))
    en_titulo = set(texto.raices(titulo))
    en_palabras = set(texto.raices(palabras))
    en_descripcion = set(texto.raices(descripcion))
    en_contexto = set(texto.raices(contexto))

    titulo_normal = texto.normalizar(titulo)
    cubre_titulo = _cubre(buscadas, en_titulo, True)
    if titulo_normal and titulo_normal == consulta.normal:
        base, escalon = 1.00, EXACTO
    elif cubre_titulo == cantidad:
        base, escalon = 0.80 + (0.05 if titulo_normal.startswith(consulta.normal) else 0.0), TITULO
    elif cubre_titulo:
        base, escalon = 0.55 + 0.10 * cubre_titulo / cantidad, TITULO
    elif (c := _cubre(buscadas, en_palabras, True)):
        base, escalon = 0.45 + 0.05 * c / cantidad, PALABRAS_CLAVE
    elif (c := _cubre(buscadas, en_descripcion, True)):
        base, escalon = 0.30 + 0.05 * c / cantidad, DESCRIPCION
    elif (c := _cubre(buscadas, en_contexto, True)):
        base, escalon = 0.15 + 0.05 * c / cantidad, CONTEXTO
    else:
        base, escalon = 0.10, SINONIMO

    if bm25 is not None:
        fuerza = max(0.0, -float(bm25))
        extra = 0.04 * fuerza / (fuerza + 3.0)
    elif posicion is not None and total:
        extra = 0.04 * (1.0 - min(posicion, total) / max(total, 1))
    else:
        extra = 0.0
    return round(min(1.0, base + extra), 4), escalon
