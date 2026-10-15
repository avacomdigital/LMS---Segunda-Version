"""
La escala interna universal de 0 a 100 (FUN-119, §4.1) y el redondeo. Todo cálculo de una calificación usa `Decimal`, nunca `float`: el `float` sólo
aparece en el borde (leer el porcentaje que calculó MOD-010, escribir el JSON de respuesta).

Reglas, documentadas y deterministas:
  · Toda puntuación interna está en el rango cerrado [0, 100] con a lo sumo DOS decimales.
  · Lo que escribe una persona (un ajuste) se valida ESTRICTO: más de dos decimales, fuera de rango, texto, booleano, NaN o infinito se rechazan.
  · Lo que calcula MOD-010 (un porcentaje con hasta cuatro decimales) se normaliza a dos con `mitad_arriba` (ROUND_HALF_UP): 84,995 → 85,00.
  · La escala de presentación nunca modifica el valor interno guardado.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from . import catalogos as cat
from .errores import PuntajeInvalido

CERO = Decimal("0")
CIEN = Decimal("100")
CENTESIMA = Decimal("0.01")

_MODOS_DE_REDONDEO = {
    cat.MITAD_ARRIBA: ROUND_HALF_UP,
    cat.MITAD_PAR: ROUND_HALF_EVEN,
    cat.ABAJO: ROUND_FLOOR,
    cat.ARRIBA: ROUND_CEILING,
}


def a_decimal(valor: Any, *, campo: str = "puntaje") -> Decimal:
    """Convierte lo que llega (número JSON, texto, Decimal) a `Decimal` SIN pasar por la representación binaria de un float: `85.3` es 85,3 exacto.
    Rechaza booleanos, nulos, vacíos, NaN e infinitos."""
    if isinstance(valor, bool) or valor is None or (isinstance(valor, str) and not valor.strip()):
        raise PuntajeInvalido(f"Falta `{campo}`: debe ser un número.", campo=campo)
    try:
        if isinstance(valor, Decimal):
            d = valor
        elif isinstance(valor, float):
            d = Decimal(repr(valor))                      # el texto más corto que identifica al float: 85.3 → 85,3
        elif isinstance(valor, str):
            d = Decimal(valor.strip().replace(",", "."))
        elif isinstance(valor, int):
            d = Decimal(valor)
        else:                                             # listas, tuplas, diccionarios: Decimal los aceptaría como «dígitos»; aquí no son un número
            raise TypeError
    except (InvalidOperation, ValueError, TypeError):
        raise PuntajeInvalido(f"`{campo}` debe ser un número.", campo=campo, valor=str(valor)[:40]) from None
    if not d.is_finite():
        raise PuntajeInvalido(f"`{campo}` debe ser un número finito.", campo=campo)
    return d


def _mostrar(valor: Decimal) -> float | str:
    """El valor rechazado, para el cuerpo del error: un exponente enorme (`1e999999`) no cabe en un float ni en un JSON válido, así que viaja como texto."""
    return float(valor) if abs(valor) < Decimal("1e15") else str(valor)[:40]


def decimales_de(valor: Decimal) -> int:
    """Cuántos decimales significativos tiene (85,50 tiene uno; 85,125 tiene tres)."""
    exponente = valor.normalize().as_tuple().exponent
    return max(0, -int(exponente))


def validar_interno(valor: Any, *, campo: str = "puntaje") -> Decimal:
    """Una puntuación interna escrita por una persona: [0, 100], a lo sumo dos decimales. Devuelve el valor con exactamente dos decimales."""
    d = a_decimal(valor, campo=campo)
    if d < CERO or d > CIEN:
        raise PuntajeInvalido(f"`{campo}` debe estar entre 0 y 100.", campo=campo, valor=_mostrar(d))
    if decimales_de(d) > 2:
        raise PuntajeInvalido(f"`{campo}` admite a lo sumo dos decimales.", campo=campo, valor=_mostrar(d))
    return d.quantize(CENTESIMA)


def validar_puntos(valor: Any, *, campo: str = "puntaje") -> Decimal:
    """Los puntos que un profesor asigna a UN reactivo (no un porcentaje): no negativos y con a lo sumo dos decimales. El máximo lo pone el reactivo y lo hace
    cumplir MOD-010; aquí sólo se acota lo absurdo, para que nunca se guarde una cifra que el libro no pueda reproducir."""
    d = a_decimal(valor, campo=campo)
    if d < CERO:
        raise PuntajeInvalido(f"`{campo}` no puede ser negativo.", campo=campo, valor=_mostrar(d))
    if d > Decimal("100000"):
        raise PuntajeInvalido(f"`{campo}` es demasiado grande.", campo=campo, valor=_mostrar(d))
    if decimales_de(d) > 2:
        raise PuntajeInvalido(f"`{campo}` admite a lo sumo dos decimales.", campo=campo, valor=_mostrar(d))
    return d.quantize(CENTESIMA)


def interno_desde_porcentaje(porcentaje: Any) -> Decimal:
    """El porcentaje que calculó MOD-010 (escala 0–100, hasta cuatro decimales) → escala interna con dos decimales, `mitad_arriba`. Fuera de rango
    se rechaza: MOD-010 ya lo acota, y una cifra imposible nunca se registra en silencio."""
    d = a_decimal(porcentaje, campo="porcentaje")
    if d < CERO or d > CIEN:
        raise PuntajeInvalido("El porcentaje del intento está fuera de 0–100.", campo="porcentaje", valor=_mostrar(d))
    return d.quantize(CENTESIMA, rounding=ROUND_HALF_UP)


def redondear(valor: Decimal, decimales: int, regla: str = cat.MITAD_ARRIBA) -> Decimal:
    """Redondea `valor` a `decimales` con la `regla` de la escala. Determinista: el mismo valor y la misma regla dan siempre el mismo resultado."""
    if regla not in _MODOS_DE_REDONDEO:
        raise ValueError(f"Regla de redondeo desconocida: {regla}")
    if not 0 <= decimales <= cat.MAX_DECIMALES:
        raise ValueError(f"Decimales fuera de 0–{cat.MAX_DECIMALES}: {decimales}")
    return valor.quantize(Decimal(1).scaleb(-decimales), rounding=_MODOS_DE_REDONDEO[regla])


def promedio(valores: list[Decimal]) -> Decimal | None:
    """Media aritmética simple con dos decimales (`mitad_arriba`). Sin valores no hay promedio: nunca un cero."""
    if not valores:
        return None
    return (sum(valores, CERO) / Decimal(len(valores))).quantize(CENTESIMA, rounding=ROUND_HALF_UP)


def como_numero(valor: Decimal | None) -> float | None:
    """Sólo para el JSON de salida: el cálculo ya terminó. Los valores de dos decimales viajan exactos."""
    return None if valor is None else float(valor)
