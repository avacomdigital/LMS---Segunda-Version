"""
Troceo del texto que se va a leer en voz alta.

La voz del servicio local rechaza más de 600 caracteres por llamada (medidos DESPUÉS de quitar Markdown y emojis, `text_too_long`) y una respuesta del modelo puede pasarlos. Aquí se
divide por frases en trozos de a lo sumo `maximo` caracteres (por omisión 450: margen bajo el límite). Un trozo sin letras ni números (`***`, `---`) se descarta, porque el servicio
contesta `tts_empty_audio` y no hay nada que pronunciar.
"""
from __future__ import annotations

MAXIMO_POR_OMISION = 450
_FIN_DE_FRASE = frozenset(".!?…\n;")


def tiene_contenido_pronunciable(texto: str) -> bool:
    return any(c.isalnum() for c in texto)


def trocear(texto: str, maximo: int = MAXIMO_POR_OMISION) -> list[str]:
    """Los trozos, en orden, cada uno de a lo sumo `maximo` caracteres y con algo que decir. Un texto vacío da una lista vacía."""
    maximo = max(20, int(maximo))
    trozos: list[str] = []
    actual = ""

    def cerrar() -> None:
        nonlocal actual
        limpio = actual.strip()
        actual = ""
        if tiene_contenido_pronunciable(limpio):
            trozos.append(limpio)

    for frase in _frases(texto or ""):
        for pieza in _partir_frase_larga(frase, maximo):
            if actual and len(actual) + 1 + len(pieza) > maximo:
                cerrar()
            actual = f"{actual} {pieza}" if actual else pieza
    cerrar()
    return trozos


def _frases(texto: str):
    """Corta en `. ! ? … ;` (sólo si lo que sigue es un espacio o el fin: «3.5» y «p. ej.» no cortan donde no deben) y en CADA salto de línea (un renglón de una lista es una frase)."""
    acumulado: list[str] = []
    n = len(texto)
    for i, c in enumerate(texto):
        acumulado.append(c)
        if c == "\n" or (c in _FIN_DE_FRASE and (i + 1 >= n or texto[i + 1].isspace())):
            frase = "".join(acumulado).strip()
            acumulado = []
            if frase:
                yield frase
    resto = "".join(acumulado).strip()
    if resto:
        yield resto


def _partir_frase_larga(frase: str, maximo: int):
    """Una frase más larga que el máximo se parte en la última coma o, si no hay, en el último espacio; sin espacios, corte duro."""
    while len(frase) > maximo:
        corte = frase.rfind(",", 0, maximo)
        if corte < maximo // 3:
            corte = frase.rfind(" ", 0, maximo)
        if corte <= 0:
            corte = maximo - 1
        parte = frase[:corte + 1].strip()
        frase = frase[corte + 1:].strip()
        if parte:
            yield parte
    if frase:
        yield frase
