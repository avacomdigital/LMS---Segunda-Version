"""
Lo que un `curso_ref` de AVACOM Biblioteca dice de sí mismo, sin preguntarle a nadie. El identificador de un curso del tramo escolar SE DERIVA de su lugar en el árbol
del país (`course.schema.json`, `classification`): `avacom.<país>.<nivel>.<grado>.<materia>.<tema>`. Así, un profesor de matemáticas que dicta varios cursos (polinomios,
ecuaciones 2×2…) puede ver juntos todos los de SU materia aunque la biblioteca esté cerrada: la materia sale del propio identificador.

Es una lectura de conveniencia, no una fuente de verdad: el nombre con que se muestra una materia lo pone el árbol de la biblioteca cuando responde; si no, el código
en palabras. Un identificador que no tenga esa forma (un curso del tramo complementario, un ejemplo, otro proveedor) no tiene materia conocida y no se inventa una.
Este archivo no importa Django.
"""
from __future__ import annotations

PREFIJO = "avacom"
PARTES = ("country", "level", "grade", "subject", "topic")
SIN_MATERIA = ""


def arbol_de(curso_ref: str | None) -> dict[str, str]:
    """`{country, level, grade, subject, topic}` de un `curso_ref` del tramo escolar, o `{}` si el identificador no tiene esa forma."""
    partes = str(curso_ref or "").strip().split(".")
    if len(partes) != 6 or partes[0] != PREFIJO or any(not p for p in partes):
        return {}
    salida = dict(zip(PARTES, partes[1:]))
    salida["country"] = salida["country"].upper()
    return salida


def materia_de(curso_ref: str | None) -> str:
    """El código de la materia de un curso («math», «science», «social-studies»), o vacío si no se puede saber."""
    return arbol_de(curso_ref).get("subject", SIN_MATERIA)


def rotulo_de_materia(codigo: str) -> str:
    """El código de una materia en palabras cuando la biblioteca no entrega su nombre: «social-studies» → «Social studies». Nunca inventa una traducción."""
    texto = str(codigo or "").replace("-", " ").replace("_", " ").strip()
    return texto[:1].upper() + texto[1:] if texto else "Sin materia"


def cumple(curso_ref: str | None, filtro: dict[str, str]) -> bool:
    """¿Cuelga el curso del nodo pedido? Cada clave del filtro (país, nivel, grado, materia, tema) tiene que coincidir con la del identificador; sin filtro, todo cumple.
    Un curso cuyo identificador no dice nada no cumple ningún filtro: no se le adivina una materia."""
    if not filtro:
        return True
    arbol = arbol_de(curso_ref)
    if not arbol:
        return False
    return all(arbol.get(clave, "").casefold() == str(valor).casefold() for clave, valor in filtro.items() if valor)
