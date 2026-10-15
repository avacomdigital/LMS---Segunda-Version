"""
La consulta de búsqueda ya interpretada: el texto normalizado, sus raíces, los filtros validados y la expresión de texto completo (FTS5) que se arma de ellos.

Seguridad: la expresión `MATCH` NUNCA se arma con el texto del usuario tal cual. Cada palabra pasa antes por `normalizar` (sólo letras, dígitos y ñ), se pone entre
comillas y se entrega al motor como PARÁMETRO. Un `OR`, un `NOT`, un `*` o unas comillas escritos por quien busca son palabras más, no operadores.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import catalogos as cat
from . import texto
from .errores import ConsultaInvalida, ConsultaVacia, DatosInvalidos


@dataclass(frozen=True)
class Filtros:
    """Los filtros académicos validados. El árbol (`pais`, `nivel`, `grado`, `materia`, `tema`) es el de la biblioteca; `periodo` y `grupo` son del padrón (MOD-001)."""

    tipos: tuple[str, ...] = ()
    pais: str = ""
    nivel: str = ""
    grado: str = ""
    materia: str = ""
    tema: str = ""
    periodo: str = ""
    grupo_id: str = ""

    @property
    def del_arbol(self) -> dict[str, str]:
        return {k: v for k, v in (("country", self.pais), ("level", self.nivel), ("grade", self.grado), ("subject", self.materia), ("topic", self.tema)) if v}

    @property
    def hay_arbol(self) -> bool:
        return bool(self.del_arbol)

    @property
    def hay_ambito_de_grupo(self) -> bool:
        """Ciclo y grupo son conceptos del padrón: sólo las entidades del LMS (de un grupo) los tienen. Con alguno elegido, el catálogo no entra."""
        return bool(self.periodo or self.grupo_id)

    def como_dict(self) -> dict:
        return {"type": list(self.tipos), "country": self.pais, "level": self.nivel, "grade": self.grado, "subject": self.materia, "topic": self.tema,
                "period": self.periodo, "group": self.grupo_id}


@dataclass(frozen=True)
class Consulta:
    original: str
    normal: str                                  # el texto entero normalizado (con vacías): para la coincidencia exacta del título
    raices: tuple[str, ...]                      # las raíces significativas, sin repetir y en orden
    filtros: Filtros = field(default_factory=Filtros)
    limite: int = cat.LIMITE_POR_DEFECTO
    pagina: int = 1

    @property
    def desplazamiento(self) -> int:
        return (self.pagina - 1) * self.limite


def _entero(valor, nombre: str, defecto: int, minimo: int, maximo: int) -> int:
    if valor in (None, ""):
        return defecto
    try:
        numero = int(str(valor).strip())
    except ValueError:
        raise DatosInvalidos(f"«{nombre}» debe ser un número entero.", parametro=nombre) from None
    if not minimo <= numero <= maximo:
        raise DatosInvalidos(f"«{nombre}» debe estar entre {minimo} y {maximo}.", parametro=nombre)
    return numero


def _valor_de_filtro(valor, nombre: str) -> str:
    limpio = " ".join(str(valor or "").split())
    if len(limpio) > cat.MAX_VALOR_FILTRO:
        raise DatosInvalidos(f"«{nombre}» es demasiado largo (máximo {cat.MAX_VALOR_FILTRO} caracteres).", parametro=nombre)
    return limpio


def interpretar(parametros: dict) -> Consulta:
    """Valida los parámetros de `GET /api/search/` y arma la consulta. Lanza `ConsultaVacia`, `ConsultaInvalida` o `DatosInvalidos`."""
    original = " ".join(str(parametros.get("q") or "").split())
    if len(original) > cat.MAX_CONSULTA:
        raise ConsultaInvalida(f"La búsqueda es demasiado larga (máximo {cat.MAX_CONSULTA} caracteres).", maximo=cat.MAX_CONSULTA)
    normal = texto.normalizar(original)
    if not normal:
        raise ConsultaVacia("Escribe qué quieres buscar.")
    if len(normal.replace(" ", "")) < cat.MIN_CONSULTA:
        raise ConsultaInvalida(f"Escribe al menos {cat.MIN_CONSULTA} letras.", minimo=cat.MIN_CONSULTA)
    todas = texto.significativas(original)
    if len(todas) > cat.MAX_PALABRAS_DE_LA_CONSULTA:
        raise ConsultaInvalida(f"La búsqueda tiene demasiadas palabras (máximo {cat.MAX_PALABRAS_DE_LA_CONSULTA}).", maximo=cat.MAX_PALABRAS_DE_LA_CONSULTA)
    sin_repetir = tuple(dict.fromkeys(todas))

    tipos_crudos = str(parametros.get("type") or parametros.get("types") or "").replace(";", ",")
    tipos = tuple(dict.fromkeys(t.strip().lower() for t in tipos_crudos.split(",") if t.strip()))
    for tipo in tipos:
        if tipo not in cat.TIPOS:
            raise DatosInvalidos(f"«{tipo}» no es un tipo de resultado conocido.", parametro="type", validos=list(cat.TIPOS))
    filtros = Filtros(
        tipos=tipos,
        pais=_valor_de_filtro(parametros.get("country"), "country"),
        nivel=_valor_de_filtro(parametros.get("level"), "level"),
        grado=_valor_de_filtro(parametros.get("grade"), "grade"),
        materia=_valor_de_filtro(parametros.get("subject"), "subject"),
        tema=_valor_de_filtro(parametros.get("topic"), "topic"),
        periodo=_valor_de_filtro(parametros.get("period"), "period"),
        grupo_id=_valor_de_filtro(parametros.get("group"), "group"),
    )
    return Consulta(
        original=original, normal=normal, raices=sin_repetir, filtros=filtros,
        limite=_entero(parametros.get("limit") or parametros.get("page_size"), "limit", cat.LIMITE_POR_DEFECTO, 1, cat.LIMITE_MAXIMO),
        pagina=_entero(parametros.get("page"), "page", 1, 1, cat.PAGINA_MAXIMA),
    )


def _termino(raiz_: str, equivalentes: list[str], prefijo: bool) -> str:
    """Un término de la expresión: la raíz (con `*` si se está escribiendo) y, entre paréntesis y con OR, sus sinónimos. Todo entre comillas."""
    principal = f'"{raiz_}"*' if prefijo and len(raiz_) >= 2 else f'"{raiz_}"'
    if not equivalentes:
        return principal
    otros = []
    for equivalente in equivalentes:
        partes = texto.raices(equivalente)
        if partes:
            otros.append('"' + " ".join(partes) + '"')              # una frase entre comillas: sus palabras seguidas
    return "(" + " OR ".join([principal, *otros]) + ")" if otros else principal


def expresion_match(consulta: Consulta, sinonimos: dict[str, list[str]] | None, *, todas: bool = True) -> str:
    """La expresión FTS5. `todas=True`: cada palabra debe aparecer (AND); `todas=False`: basta una (OR), que es la relajación cuando nada coincide con todas.
    La última palabra vale como prefijo (quien escribe «fracc» busca «fracciones»). `sinonimos`: raíz → equivalentes (texto normalizado)."""
    sinonimos = sinonimos or {}
    terminos = [_termino(r, sinonimos.get(r, []), prefijo=(i == len(consulta.raices) - 1)) for i, r in enumerate(consulta.raices)]
    return (" AND " if todas else " OR ").join(terminos)
