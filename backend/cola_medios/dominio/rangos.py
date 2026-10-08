"""
`Range` de HTTP (RFC 9110 §14) para servir un archivo local: un solo tramo `bytes=a-b`, `bytes=a-` o `bytes=-n`.

Lo que no se entiende (otra unidad, varios tramos, un número roto) se trata como si no hubiera `Range`: se responde el archivo entero con 200, que es lo
que la norma permite y lo que hace un servidor que no soporta tramos múltiples. Un tramo que empieza más allá del final es `Insatisfacible` (416).
"""
from __future__ import annotations

from dataclasses import dataclass


class Insatisfacible(Exception):
    """El tramo pedido empieza después del último byte."""


@dataclass(frozen=True)
class Tramo:
    inicio: int          # primer byte (incluido)
    fin: int             # último byte (incluido)

    @property
    def longitud(self) -> int:
        return self.fin - self.inicio + 1

    def encabezado(self, total: int) -> str:
        return f"bytes {self.inicio}-{self.fin}/{total}"


def interpretar(cabecera: str | None, total: int) -> Tramo | None:
    """El tramo que pide la cabecera sobre un archivo de `total` bytes, o None si hay que enviarlo entero. Lanza `Insatisfacible`."""
    if not cabecera or total <= 0:
        return None
    texto = cabecera.strip()
    if not texto.lower().startswith("bytes="):
        return None
    pedido = texto[6:].strip()
    if "," in pedido or "-" not in pedido:
        return None
    a, _, b = pedido.partition("-")
    a, b = a.strip(), b.strip()
    try:
        if a == "":                                   # sufijo: los últimos n bytes
            if not b:
                return None
            n = int(b)
            if n <= 0:
                raise Insatisfacible()
            return Tramo(max(0, total - n), total - 1)
        inicio = int(a)
        if inicio < 0:
            return None
        if inicio >= total:
            raise Insatisfacible()
        if b == "":
            return Tramo(inicio, total - 1)
        fin = int(b)
        if fin < inicio:
            return None                               # tramo mal formado: se ignora
        return Tramo(inicio, min(fin, total - 1))
    except ValueError:
        return None


def total_de_content_range(valor: str | None) -> tuple[int, int, int | None] | None:
    """`bytes 10-19/100` → (10, 19, 100); `bytes */100` → None; total desconocido (`/*`) → total None."""
    if not valor:
        return None
    texto = valor.strip()
    if not texto.lower().startswith("bytes "):
        return None
    cuerpo = texto[6:].strip()
    rango, _, total = cuerpo.partition("/")
    a, _, b = rango.partition("-")
    try:
        return int(a), int(b), (None if total.strip() == "*" else int(total))
    except ValueError:
        return None
