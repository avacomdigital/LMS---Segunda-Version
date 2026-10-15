"""
El tratamiento del texto de Search: normalizar, sacar la raíz de cada palabra y cortar un fragmento con lo encontrado. Puro: ni Django ni base de datos.

  normalizar   minúsculas, sin tildes y sin signos, y SIN perder la ñ («año» y «ano» son palabras distintas en español; «fracción» y «fraccion» son la misma).
  raiz         una raíz ligera del español: quita el plural y la vocal final, de modo que «fracción» y «fracciones», «matemática» y «matemáticas» o «examen» y
               «exámenes» se encuentren entre sí. Es la MISMA función al indexar y al consultar, así que nunca hay desajuste.
  fragmento    el trozo de un texto donde está lo buscado, con los desplazamientos de lo resaltado.
"""
from __future__ import annotations

import re
import unicodedata

_NO_ALFANUMERICO = re.compile(r"[^0-9a-zñ]+")
_PALABRA = re.compile(r"\w+", re.UNICODE)
_ESPACIOS = re.compile(r"\s+")

# Las palabras que no distinguen nada. Se quitan de la CONSULTA (si queda alguna otra), no del índice.
PALABRAS_VACIAS = frozenset({
    "a", "al", "con", "de", "del", "el", "en", "es", "la", "las", "lo", "los", "o", "para", "por", "que", "se", "su", "sus", "un", "una", "unas", "uno", "unos", "y",
})


def normalizar(texto) -> str:
    """Minúsculas, sin tildes ni signos, palabras separadas por un espacio. La tilde de la ñ se conserva (U+0303 detrás de una `n`)."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", str(texto).casefold())
    salida: list[str] = []
    previo = ""
    for caracter in descompuesto:
        if unicodedata.category(caracter) == "Mn":
            if caracter == "̃" and previo == "n":
                salida.append(caracter)          # la ñ se queda: es otra letra
            continue                              # cualquier otra marca (tildes, diéresis) se pierde
        salida.append(caracter)
        previo = caracter
    compuesto = unicodedata.normalize("NFC", "".join(salida))
    return _ESPACIOS.sub(" ", _NO_ALFANUMERICO.sub(" ", compuesto)).strip()


def raiz(palabra: str) -> str:
    """La raíz ligera de una palabra YA normalizada. Sin plural ni vocal final cuando queda lo bastante para no confundirla con otra."""
    if len(palabra) < 4 or palabra.isdigit():
        return palabra
    if palabra.endswith("s"):
        palabra = palabra[:-1]
    if len(palabra) >= 5 and palabra[-1] in "aeo":
        palabra = palabra[:-1]
    return palabra


def palabras(texto) -> list[str]:
    """Las palabras normalizadas de un texto, en orden y con repeticiones."""
    normal = normalizar(texto)
    return normal.split(" ") if normal else []


def raices(texto) -> list[str]:
    return [raiz(p) for p in palabras(texto)]


def para_el_indice(texto) -> str:
    """Lo que se guarda en la tabla de texto completo: las raíces, separadas por un espacio. El texto ORIGINAL queda aparte, tal cual, para mostrarlo."""
    return " ".join(raices(texto))


def significativas(texto) -> list[str]:
    """Las raíces de la consulta sin las palabras vacías (salvo que sólo haya vacías: entonces, todas)."""
    todas = palabras(texto)
    utiles = [p for p in todas if p not in PALABRAS_VACIAS]
    return [raiz(p) for p in (utiles or todas)]


def _espacios_colapsados(texto: str) -> str:
    return _ESPACIOS.sub(" ", str(texto or "")).strip()


def fragmento(texto, buscadas: list[str], *, ancho: int = 160, prefijo_final: bool = False) -> tuple[str, list[tuple[int, int]]]:
    """`(fragmento, resaltados)`: el trozo del `texto` que rodea la primera palabra cuya raíz está entre `buscadas`, con los `(inicio, fin)` de cada palabra
    encontrada DENTRO del fragmento. Sin coincidencia, el comienzo del texto. `prefijo_final`: la última de `buscadas` vale como prefijo (se está escribiendo)."""
    limpio = _espacios_colapsados(texto)
    if not limpio:
        return "", []
    conjunto = set(buscadas)
    ultima = buscadas[-1] if buscadas and prefijo_final else None

    def coincide(palabra: str) -> bool:
        r = raiz(normalizar(palabra))
        return bool(r) and (r in conjunto or (ultima is not None and r.startswith(ultima)))

    encontradas = [(m.start(), m.end()) for m in _PALABRA.finditer(limpio) if coincide(m.group())]
    if not encontradas:
        corte = _corte_en_palabra(limpio, ancho)
        return (limpio[:corte] + ("…" if corte < len(limpio) else "")), []
    primera = encontradas[0][0]
    inicio = max(0, primera - ancho // 3)
    if inicio > 0:                                      # no empezar a mitad de una palabra
        while inicio < primera and not limpio[inicio - 1].isspace():
            inicio += 1
    fin = min(len(limpio), inicio + ancho)
    if fin < len(limpio):
        fin = _corte_en_palabra(limpio, fin, minimo=max(fin - 20, primera + 1))
    trozo = limpio[inicio:fin]
    cabeza = "…" if inicio > 0 else ""
    cola = "…" if fin < len(limpio) else ""
    desplazamiento = len(cabeza) - inicio
    marcas = [(a + desplazamiento, b + desplazamiento) for a, b in encontradas if a >= inicio and b <= fin]
    return cabeza + trozo + cola, marcas


def _corte_en_palabra(texto: str, limite: int, minimo: int = 1) -> int:
    """El punto de corte más cercano a `limite` que no parte una palabra."""
    if limite >= len(texto):
        return len(texto)
    corte = limite
    while corte > minimo and not texto[corte].isspace():
        corte -= 1
    return corte if corte > minimo else limite


def quitar_marcas(texto: str) -> tuple[str, list[tuple[int, int]]]:
    """Convierte un fragmento con **negritas** de Markdown (así resalta la biblioteca lo encontrado) en `(texto plano, resaltados)`."""
    plano: list[str] = []
    marcas: list[tuple[int, int]] = []
    abierto: int | None = None
    i, largo = 0, len(texto or "")
    while i < largo:
        if texto.startswith("**", i):
            if abierto is None:
                abierto = len(plano)
            else:
                if len(plano) > abierto:
                    marcas.append((abierto, len(plano)))
                abierto = None
            i += 2
            continue
        plano.append(texto[i])
        i += 1
    return "".join(plano), marcas
