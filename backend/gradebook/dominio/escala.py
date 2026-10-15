"""
El motor de escalas y equivalencias (FUN-124, §4.3 y «Sistema de calificaciones internacionales configurables»). La escala INTERNA es siempre 0–100; lo que
se presenta (un número, una letra, un concepto, un nivel de competencia) sale de una `DefinicionEscala` que la institución adopta, valida y versiona.

Mantiene SEPARADAS cuatro cosas que no son la misma:
  · el resultado interno         0–100, el valor guardado (`puntaje.py`)
  · la calificación presentada   el valor o la etiqueta que ve quien lee la escala (`Presentacion.valor` / `etiqueta`)
  · el nivel de desempeño        el descriptor del tramo donde cae el resultado (`nivel_desempeno`), que el docente puede valorar distinto (valoración docente)
  · la decisión de aprobación    aquí sólo el CRITERIO de la escala (`cumple_criterio`); aprobar o promover es una decisión institucional y humana que este módulo no toma

Una conversión sólo existe dentro de una escala validada: no hay equivalencias nacionales implícitas. Las plantillas (`plantillas_escalas.py`) son puntos de
partida que la institución revisa y adopta. Dominio puro: ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from . import catalogos as cat
from . import puntaje as pj
from .errores import EscalaInvalida, PuntajeInvalido

LIMITE_SUPERIOR = pj.CIEN
LIMITE_DE_VALOR = Decimal("100000")        # el valor presentado más grande que una escala numérica puede declarar (cabe en DECIMAL(7,2))


@dataclass(frozen=True)
class Tramo:
    """Un intervalo `[desde, hasta)` de la escala interna (el último incluye el 100) y lo que significa."""

    orden: int
    clave: str                       # lo que se guarda y se muestra corto: «A», «SB», «superior»
    etiqueta: str                    # el nombre completo: «Sobresaliente»
    desde: Decimal
    hasta: Decimal
    nivel_desempeno: str = ""       # el descriptor de desempeño del tramo (por omisión, la etiqueta)
    aprueba: bool | None = None     # el criterio de aprobación de la escala sobre este tramo (None: la escala no lo define)
    descripcion: str = ""


@dataclass(frozen=True)
class DefinicionEscala:
    tipo: str
    conversion: str
    decimales: int = 2
    redondeo: str = cat.MITAD_ARRIBA
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    puntos: tuple[tuple[Decimal, Decimal], ...] = ()
    aprobacion_minima: Decimal | None = None
    tramos: tuple[Tramo, ...] = ()


@dataclass(frozen=True)
class Presentacion:
    """Lo que resulta de convertir un resultado interno con una escala. Cuatro cosas separadas; ninguna sustituye a otra."""

    interno: Decimal
    valor: Decimal | None            # sólo en escalas numéricas
    etiqueta: str                    # «4,5», «B», «Notable», «A»
    clave: str                       # la etiqueta corta del tramo, o el valor formateado
    nivel_desempeno: str             # el descriptor del tramo ('' si la escala no tiene tramos)
    tramo_orden: int | None
    cumple_criterio: bool | None     # None: la escala no define criterio de aprobación
    desempeno_clave: str = ""        # la clave del tramo («SB», «DAR»): con una escala numérica es lo que acompaña al número


# ------------------------------------------------------------------------------------------------ validación

def validar(d: DefinicionEscala) -> list[str]:
    """Todas las reglas que incumple la definición (vacía = válida). Los intervalos deben cubrir 0–100 completos, sin solapamientos ni huecos."""
    p: list[str] = []
    if d.tipo not in cat.TIPOS_DE_ESCALA:
        p.append(f"`tipo` debe ser uno de {', '.join(cat.TIPOS_DE_ESCALA)}.")
    if d.conversion not in cat.CONVERSIONES:
        p.append(f"`conversion` debe ser uno de {', '.join(cat.CONVERSIONES)}.")
    if not 0 <= int(d.decimales) <= cat.MAX_DECIMALES:
        p.append(f"`decimales` debe estar entre 0 y {cat.MAX_DECIMALES}.")
    if d.redondeo not in cat.REDONDEOS:
        p.append(f"`redondeo` debe ser uno de {', '.join(cat.REDONDEOS)}.")

    if d.tipo == cat.NUMERICA:
        if d.conversion != cat.INTERPOLADA:
            p.append("Una escala numérica se convierte por `interpolada` (los tramos describen el desempeño, no el número).")
        p += _validar_numerica(d)
    elif d.tipo in cat.TIPOS_DE_ESCALA:
        if d.conversion != cat.TRAMOS:
            p.append(f"Una escala {d.tipo} se convierte por `tramos`.")
        if d.valor_min is not None or d.valor_max is not None or d.puntos or d.aprobacion_minima is not None:
            p.append(f"Una escala {d.tipo} no lleva valores numéricos (`valor_min`, `valor_max`, `puntos`, `aprobacion_minima`).")
        if not d.tramos:
            p.append("Una escala sin valores numéricos necesita al menos un tramo.")
    p += _validar_tramos(d.tramos)
    return p


def _validar_numerica(d: DefinicionEscala) -> list[str]:
    p: list[str] = []
    if d.valor_min is None or d.valor_max is None:
        return ["Una escala numérica necesita `valor_min` y `valor_max`."]
    # Lo que se guarda y lo que se lee de vuelta deben ser lo mismo (la huella de una versión lo prueba): dos decimales y un tope que cabe en la columna.
    for nombre, valor in (("valor_min", d.valor_min), ("valor_max", d.valor_max), ("aprobacion_minima", d.aprobacion_minima)):
        if valor is not None and (pj.decimales_de(valor) > 2 or abs(valor) >= LIMITE_DE_VALOR):
            p.append(f"`{nombre}` admite a lo sumo dos decimales y debe ser menor que {LIMITE_DE_VALOR} en valor absoluto.")
    if p:
        return p
    if d.valor_min >= d.valor_max:
        p.append("`valor_min` debe ser menor que `valor_max`.")
    if len(d.puntos) < 2:
        p.append("`puntos` necesita al menos dos puntos (interno → valor): el primero en 0 y el último en 100.")
        return p
    xs = [x for x, _ in d.puntos]
    ys = [y for _, y in d.puntos]
    if xs[0] != pj.CERO or xs[-1] != pj.CIEN:
        p.append("Los puntos deben ir de 0 a 100 en la escala interna.")
    if any(b <= a for a, b in zip(xs, xs[1:])):
        p.append("Los puntos deben estar en orden estrictamente creciente en la escala interna.")
    if any(b < a for a, b in zip(ys, ys[1:])):
        p.append("Un resultado mayor no puede presentar un valor menor: los valores no pueden decrecer.")
    if any(y < d.valor_min or y > d.valor_max for y in ys):
        p.append("Todos los valores de `puntos` deben estar entre `valor_min` y `valor_max`.")
    if d.aprobacion_minima is not None and not d.valor_min <= d.aprobacion_minima <= d.valor_max:
        p.append("`aprobacion_minima` debe estar dentro de la escala.")
    return p


def _validar_tramos(tramos: tuple[Tramo, ...]) -> list[str]:
    p: list[str] = []
    if not tramos:
        return p
    claves: set[str] = set()
    for i, t in enumerate(tramos, start=1):
        if t.orden != i:
            p.append(f"Los tramos deben numerarse 1, 2, 3… en orden: el tramo {i} trae `orden = {t.orden}`.")
        if not t.clave.strip() or not t.etiqueta.strip():
            p.append(f"El tramo {i} necesita `clave` y `etiqueta`.")
        if t.clave in claves:
            p.append(f"La clave «{t.clave}» está repetida.")
        claves.add(t.clave)
        if t.desde >= t.hasta:
            p.append(f"El tramo «{t.clave}» debe tener `desde` menor que `hasta`.")
        if pj.decimales_de(t.desde) > 2 or pj.decimales_de(t.hasta) > 2:
            p.append(f"Los límites del tramo «{t.clave}» admiten a lo sumo dos decimales.")
        if t.desde < pj.CERO or t.hasta > pj.CIEN:
            p.append(f"El tramo «{t.clave}» se sale de 0–100.")
    ordenados = sorted(tramos, key=lambda t: t.orden)
    if ordenados[0].desde != pj.CERO:
        p.append("El primer tramo debe empezar en 0: un resultado bajo quedaría sin equivalencia.")
    for anterior, siguiente in zip(ordenados, ordenados[1:]):
        if siguiente.desde > anterior.hasta:
            p.append(f"Hueco entre «{anterior.clave}» y «{siguiente.clave}»: faltan los valores de {anterior.hasta} a {siguiente.desde}.")
        elif siguiente.desde < anterior.hasta:
            p.append(f"Solapamiento entre «{anterior.clave}» y «{siguiente.clave}»: los valores de {siguiente.desde} a {anterior.hasta} tendrían dos equivalencias.")
    if ordenados[-1].hasta != pj.CIEN:
        p.append("El último tramo debe terminar en 100: el resultado máximo quedaría sin equivalencia.")
    return p


def exigir_valida(d: DefinicionEscala) -> DefinicionEscala:
    problemas = validar(d)
    if problemas:
        raise EscalaInvalida("La definición de la escala no es válida.", problemas=problemas)
    return d


# ------------------------------------------------------------------------------------------------ conversión

def tramo_de(interno: Decimal, tramos: tuple[Tramo, ...]) -> Tramo | None:
    """El tramo `[desde, hasta)` donde cae el resultado; el último incluye el 100. Con una escala válida siempre hay uno."""
    ordenados = sorted(tramos, key=lambda t: t.orden)
    for t in ordenados:
        if t.desde <= interno < t.hasta or (t is ordenados[-1] and interno == t.hasta):
            return t
    return None


def _interpolar(interno: Decimal, puntos: tuple[tuple[Decimal, Decimal], ...]) -> Decimal:
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        if x0 <= interno <= x1:
            return y0 + (y1 - y0) * (interno - x0) / (x1 - x0)
    return puntos[-1][1] if interno > puntos[-1][0] else puntos[0][1]


def formatear(valor: Decimal, decimales: int) -> str:
    return format(valor, f".{decimales}f")


def convertir(interno: Decimal, d: DefinicionEscala) -> Presentacion:
    """Convierte un resultado interno (0–100) con la escala. Lanza `PuntajeInvalido` si el resultado no es interno y `EscalaInvalida` si la escala no
    es válida: nunca se presenta nada con una escala que no se pueda defender."""
    if interno < pj.CERO or interno > pj.CIEN:
        raise PuntajeInvalido("Sólo se convierte un resultado interno entre 0 y 100.", valor=float(interno))
    exigir_valida(d)
    tramo = tramo_de(interno, d.tramos) if d.tramos else None
    descriptor = (tramo.nivel_desempeno or tramo.etiqueta) if tramo else ""
    orden = tramo.orden if tramo else None
    if d.tipo == cat.NUMERICA:
        valor = _interpolar(interno, d.puntos)
        valor = pj.redondear(valor, d.decimales, d.redondeo)
        valor = min(max(valor, d.valor_min), d.valor_max)
        texto = formatear(valor, d.decimales)
        if d.aprobacion_minima is not None:
            cumple: bool | None = valor >= d.aprobacion_minima
        else:
            cumple = tramo.aprueba if tramo else None
        return Presentacion(interno, valor, texto, texto, descriptor, orden, cumple, tramo.clave if tramo else "")
    return Presentacion(interno, None, tramo.etiqueta, tramo.clave, descriptor, orden, tramo.aprueba, tramo.clave)


def vista_previa(d: DefinicionEscala, internos: list[Decimal]) -> list[Presentacion]:
    """La conversión de unos valores de muestra (lo que ve el administrador antes de adoptar o cambiar una escala)."""
    exigir_valida(d)
    return [convertir(x, d) for x in internos]


# ---------------------------------------------------------------------------------- (de)serialización y huella

def _num(valor: Decimal | None) -> str | None:
    return None if valor is None else format(valor.normalize(), "f")


def a_dict(d: DefinicionEscala) -> dict:
    """La definición como un dict de JSON: los decimales viajan como texto para que la huella y la lectura no dependan de un float."""
    return {
        "tipo": d.tipo, "conversion": d.conversion, "decimales": d.decimales, "redondeo": d.redondeo,
        "valor_min": _num(d.valor_min), "valor_max": _num(d.valor_max), "puntos": [[_num(x), _num(y)] for x, y in d.puntos],
        "aprobacion_minima": _num(d.aprobacion_minima),
        "tramos": [{"orden": t.orden, "clave": t.clave, "etiqueta": t.etiqueta, "desde": _num(t.desde), "hasta": _num(t.hasta),
                    "nivel_desempeno": t.nivel_desempeno, "aprueba": t.aprueba, "descripcion": t.descripcion} for t in d.tramos],
    }


def huella(d: DefinicionEscala) -> str:
    """SHA-256 de la definición canónica: prueba de que una versión no cambió desde que se adoptó (un boletín ya expedido se interpreta con ella)."""
    return hashlib.sha256(json.dumps(a_dict(d), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def desde_dict(datos: Any) -> DefinicionEscala:
    """Lee una definición que llega por la API o de una plantilla. Cualquier error de forma se reúne en `EscalaInvalida.problemas`; la validez de
    fondo (cobertura de 0–100, orden, límites) la comprueba `validar`."""
    problemas: list[str] = []
    if not isinstance(datos, dict):
        raise EscalaInvalida("La definición de la escala debe ser un objeto.", problemas=["`definicion` debe ser un objeto."])

    def dec(valor: Any, nombre: str, *, opcional: bool = False) -> Decimal | None:
        if valor is None or valor == "":
            if not opcional:
                problemas.append(f"Falta `{nombre}`.")
            return None
        try:
            return pj.a_decimal(valor, campo=nombre)
        except PuntajeInvalido:
            problemas.append(f"`{nombre}` debe ser un número.")
            return None

    for clave in ("puntos", "tramos"):
        if datos.get(clave) is not None and not isinstance(datos[clave], list):
            raise EscalaInvalida("La definición de la escala no tiene la forma esperada.", problemas=[f"`{clave}` debe ser una lista."])
    puntos: list[tuple[Decimal, Decimal]] = []
    for i, par in enumerate(datos.get("puntos") or [], start=1):
        if not isinstance(par, (list, tuple)) or len(par) != 2:
            problemas.append(f"El punto {i} debe ser [interno, valor].")
            continue
        x, y = dec(par[0], f"puntos[{i}][0]"), dec(par[1], f"puntos[{i}][1]")
        if x is not None and y is not None:
            puntos.append((x, y))
    tramos: list[Tramo] = []
    for i, t in enumerate(datos.get("tramos") or [], start=1):
        if not isinstance(t, dict):
            problemas.append(f"El tramo {i} debe ser un objeto.")
            continue
        orden = t.get("orden", i)
        if isinstance(orden, bool) or not isinstance(orden, int):
            problemas.append(f"`tramos[{i}].orden` debe ser un entero.")
            continue
        desde, hasta = dec(t.get("desde"), f"tramos[{i}].desde"), dec(t.get("hasta"), f"tramos[{i}].hasta")
        aprueba = t.get("aprueba")
        if aprueba is not None and not isinstance(aprueba, bool):
            problemas.append(f"`tramos[{i}].aprueba` debe ser verdadero, falso o nulo.")
            aprueba = None
        if desde is None or hasta is None:
            continue
        tramos.append(Tramo(orden=orden, clave=str(t.get("clave") or "").strip(), etiqueta=str(t.get("etiqueta") or "").strip(), desde=desde, hasta=hasta,
                            nivel_desempeno=str(t.get("nivel_desempeno") or "").strip(), aprueba=aprueba, descripcion=str(t.get("descripcion") or "").strip()))
    decimales = datos.get("decimales", 2)
    if isinstance(decimales, bool) or not isinstance(decimales, int):
        problemas.append("`decimales` debe ser un entero.")
        decimales = 2
    d = DefinicionEscala(
        tipo=str(datos.get("tipo") or ""), conversion=str(datos.get("conversion") or ""), decimales=decimales,
        redondeo=str(datos.get("redondeo") or cat.MITAD_ARRIBA), valor_min=dec(datos.get("valor_min"), "valor_min", opcional=True),
        valor_max=dec(datos.get("valor_max"), "valor_max", opcional=True), puntos=tuple(puntos),
        aprobacion_minima=dec(datos.get("aprobacion_minima"), "aprobacion_minima", opcional=True), tramos=tuple(tramos))
    if problemas:
        raise EscalaInvalida("La definición de la escala no tiene la forma esperada.", problemas=problemas)
    return d


def lineal(minimo: Decimal, maximo: Decimal) -> tuple[tuple[Decimal, Decimal], ...]:
    """Los dos puntos de la conversión lineal de 0–100 a [mínimo, máximo]."""
    return ((pj.CERO, minimo), (pj.CIEN, maximo))


def presentacion_a_dict(p: Presentacion) -> dict:
    """La presentación en cuatro bloques separados (resultado interno, calificación presentada, desempeño, criterio de aprobación)."""
    return {
        "interno": pj.como_numero(p.interno),
        "presentada": {"valor": pj.como_numero(p.valor), "etiqueta": p.etiqueta, "clave": p.clave},
        "desempeno": {"nivel": p.nivel_desempeno, "clave": p.desempeno_clave, "tramo": p.tramo_orden},
        "aprobacion": {"cumple_criterio": p.cumple_criterio},
    }


def presentar(interno: Decimal, d: DefinicionEscala, desempeno_docente: str = "") -> dict:
    """La presentación COMPLETA que se estampa al publicar: el cálculo (`convertir`) más la valoración del profesor si la hubo. La valoración docente
    sustituye al nivel de desempeño que salió de la cuenta (la presentación oficial no es sólo una operación matemática); el resultado interno y,
    en una escala numérica, el valor presentado no cambian. En una escala sin números (letras, conceptos, competencias) la valoración fija además la
    etiqueta que se presenta y su criterio de aprobación."""
    p = convertir(interno, d)
    salida = presentacion_a_dict(p)
    salida["desempeno"]["origen"] = "calculo"
    if desempeno_docente:
        tramo = next((t for t in d.tramos if t.clave == desempeno_docente), None)
        if tramo is not None:
            salida["desempeno"] = {"nivel": tramo.nivel_desempeno or tramo.etiqueta, "clave": tramo.clave, "tramo": tramo.orden, "origen": "docente"}
            if d.tipo != cat.NUMERICA:
                salida["presentada"] = {"valor": None, "etiqueta": tramo.etiqueta, "clave": tramo.clave}
                salida["aprobacion"] = {"cumple_criterio": tramo.aprueba}
    return salida
