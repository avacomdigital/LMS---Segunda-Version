"""
Las cuentas de los reportes, con `Decimal` y `mitad_arriba` como el libro de calificaciones: lo que se muestra dos veces (en pantalla y en el archivo) sale de aquí y es igual.

Reglas que mandan:
  · Sin datos no hay cifra: un promedio sin valores es `None`, nunca un cero. Una actividad que nadie entregó no es un «0 % de aciertos».
  · El promedio de un grupo es la media simple de los ALUMNOS que tienen cifra (no ponderada por actividades): lo que cada persona logró pesa igual.
  · Los porcentajes son de 0 a 100 con dos decimales.
Este archivo no importa Django.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import catalogos as cat

CERO = Decimal("0")
CIEN = Decimal("100")
CENTESIMA = Decimal("0.01")


def a_decimal(valor) -> Decimal | None:
    """Un número cualquiera (int, float, Decimal, texto) → `Decimal`, o None si no lo es. Los `float` se pasan por su texto para no arrastrar el ruido binario."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        d = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENTESIMA, rounding=ROUND_HALF_UP)


def porcentaje(parte, total) -> Decimal | None:
    """`parte` de `total` en 0–100, con dos decimales. Sin total (None o 0) no hay porcentaje."""
    p, t = a_decimal(parte), a_decimal(total)
    if p is None or t is None or t <= 0:
        return None
    return redondear(max(CERO, min(CIEN, CIEN * p / t)))


def promedio(valores: Iterable) -> Decimal | None:
    """Media simple con dos decimales de los valores que existen (los `None` no cuentan). Sin valores: None."""
    lista = [d for d in (a_decimal(v) for v in valores) if d is not None]
    if not lista:
        return None
    return redondear(sum(lista, CERO) / Decimal(len(lista)))


def como_numero(valor) -> int | float | None:
    """Sólo para el JSON de salida: el cálculo ya terminó. Un valor entero viaja como entero (`25`, no `25.0`); los demás, con sus dos decimales exactos."""
    d = a_decimal(valor)
    if d is None:
        return None
    return int(d) if d == d.to_integral_value() else float(d)


# ------------------------------------------------------------------------------------------------ «necesita atención»

@dataclass(frozen=True)
class MetricasDeAlumno:
    clases_total: int = 0
    clases_asistidas: int = 0
    actividades_recibidas: int = 0
    actividades_entregadas: int = 0
    evaluaciones_sin_presentar: int = 0
    estudios_vencidos: int = 0


def motivos_de_atencion(m: MetricasDeAlumno) -> list[dict]:
    """Por qué un alumno necesita atención, del más al menos urgente. Los criterios son una PROPUESTA de partida (constantes de `catalogos`), no una norma
    institucional; la pantalla los muestra como «motivo» de una línea, nunca como un juicio. Un alumno sin motivos no aparece en la lista de atención."""
    motivos: list[dict] = []
    if m.evaluaciones_sin_presentar >= 1:
        n = m.evaluaciones_sin_presentar
        motivos.append({"codigo": cat.MOT_EVALUACIONES, "cantidad": n, "texto": f"No presentó {n} {'evaluación' if n == 1 else 'evaluaciones'}"})
    if m.actividades_recibidas >= cat.MIN_ACTIVIDADES_PARA_JUZGAR:
        pct = porcentaje(m.actividades_entregadas, m.actividades_recibidas)
        if pct is not None and pct < cat.UMBRAL_DE_ENTREGA_PCT:
            motivos.append({"codigo": cat.MOT_POCAS_ENTREGAS, "cantidad": m.actividades_recibidas - m.actividades_entregadas,
                            "texto": f"Entregó {m.actividades_entregadas} de {m.actividades_recibidas} actividades de clase"})
    if m.clases_total >= cat.MIN_CLASES_PARA_JUZGAR:
        pct = porcentaje(m.clases_asistidas, m.clases_total)
        if pct is not None and pct < cat.UMBRAL_DE_ASISTENCIA_PCT:
            motivos.append({"codigo": cat.MOT_POCAS_CLASES, "cantidad": m.clases_total - m.clases_asistidas,
                            "texto": f"Estuvo en {m.clases_asistidas} de {m.clases_total} clases"})
    if m.estudios_vencidos >= 1:
        n = m.estudios_vencidos
        motivos.append({"codigo": cat.MOT_ESTUDIO, "cantidad": n, "texto": f"Tiene {n} {'tarea de estudio vencida' if n == 1 else 'tareas de estudio vencidas'}"})
    return motivos


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{n} {singular if n == 1 else plural_}"
