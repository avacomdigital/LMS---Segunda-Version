"""
Lo que se DEDUCE de los intentos y las calificaciones: el estado simple (FUN-126), el estado de un resultado, el intento que cuenta cuando hay varios
(§4.5) y los agregados (FUN-127). Funciones puras sobre dicts planos; nada se guarda aquí.

Dos principios que mandan:
  · Una actividad pendiente NO es un cero. Sin calificación registrada el resultado es `pendiente`, `provisional` o `sin_registro`, nunca 0.
  · Lo provisional no es oficial. Los agregados sólo promedian lo registrado (`revisada` y `definitiva`), sin ponderaciones que la institución no declaró, y
    se rotulan como promedio simple informativo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import catalogos as cat
from . import puntaje as pj

_ESTADO_VISIBLE = {cat.REVISADA: cat.REVISADO, cat.DEFINITIVA: cat.DEFINITIVO, cat.REABIERTA: cat.REABIERTO, cat.ANULADA: cat.ANULADO}


# ---------------------------------------------------------------------------------------------- estado simple

def estado_simple(intentos: list[dict]) -> str:
    """No iniciado · en progreso · completado, a partir de los intentos de MOD-010 de UN alumno en UNA asignación. Completar una actividad no es tener una
    calificación: `completado` basta con que haya un intento entregado. Un intento anulado no cuenta. No administra el progreso del estudiante (MOD-012)."""
    estados = [i["estado"] for i in intentos if i["estado"] != cat.I_ANULADO]
    if any(e in cat.I_ENTREGADOS for e in estados):
        return cat.COMPLETADO
    if any(e in cat.I_VIVOS for e in estados):
        return cat.EN_PROGRESO
    return cat.NO_INICIADO


def estado_de_intento(intento: dict | None) -> str:
    """El estado de un resultado que aún no tiene calificación registrada, deducido del intento de MOD-010."""
    if intento is None:
        return cat.PENDIENTE
    estado = intento["estado"]
    if estado == cat.I_ANULADO:
        return cat.ANULADO
    if estado == cat.I_EN_REVISION:
        # Con una parte automática ya calculada hay una cifra PROVISIONAL (nunca oficial); sin ella, sólo pendiente.
        return cat.PROVISIONAL if intento.get("porcentaje") is not None else cat.PENDIENTE
    if estado == cat.I_CALIFICADO and not intento.get("calificacion_pendiente"):
        return cat.SIN_REGISTRO           # calificado en MOD-010 pero sin calificación aquí (modo simple, o anterior al modo calificaciones)
    return cat.PENDIENTE


def estado_de_resultado(calificacion: dict | None, intento: dict | None) -> str:
    if calificacion is not None:
        return _ESTADO_VISIBLE[calificacion["estado"]]
    return estado_de_intento(intento)


# --------------------------------------------------------------------------------- el intento que cuenta (§4.5)

def seleccionar_aplicable(politica: str, calificaciones: list[dict]) -> tuple[str | None, Decimal | None]:
    """`(calificación_id, puntaje)` del resultado aplicable entre las calificaciones que cuentan (`revisada` y `definitiva`) de un alumno en una asignación.

    La política es CONFIGURABLE: MOD-010 no declara cuál intento cuenta (último, mejor, promedio) y aquí no se asume. `ultimo` es el comportamiento
    provisional documentado. Con `promedio` no hay una calificación aplicable sino un valor calculado (`id = None`). Sin calificaciones: `(None, None)`."""
    vigentes = [c for c in calificaciones if c["estado"] in cat.CUENTAN]
    if not vigentes:
        return None, None
    if politica == cat.PROMEDIO:
        return None, pj.promedio([c["puntaje_efectivo"] for c in vigentes])
    if politica == cat.PRIMERO:
        elegida = min(vigentes, key=lambda c: (c["numero_intento"], c["id"]))
    elif politica == cat.MEJOR:
        elegida = max(vigentes, key=lambda c: (c["puntaje_efectivo"], c["numero_intento"]))
    else:                                              # `ultimo` y cualquier valor desconocido caen en el provisional documentado
        elegida = max(vigentes, key=lambda c: (c["numero_intento"], c["id"]))
    return elegida["id"], elegida["puntaje_efectivo"]


@dataclass(frozen=True)
class ResultadoCalculado:
    estado_simple: str
    estado_calificacion: str
    calificacion_aplicable_id: str | None
    puntaje_aplicable: Decimal | None
    intentos_total: int
    intentos_registrados: int
    publicada: bool


def calcular_resultado(intentos: list[dict], calificaciones: list[dict], politica: str) -> ResultadoCalculado:
    """El resultado de UN alumno en UNA asignación, a partir de lo que dicen MOD-010 (intentos) y MOD-011 (calificaciones)."""
    validos = [i for i in intentos if i["estado"] != cat.I_ANULADO]
    vigentes = [c for c in calificaciones if c["estado"] in cat.CUENTAN]
    aplicable_id, puntaje = seleccionar_aplicable(politica, vigentes)
    por_id = {c["id"]: c for c in calificaciones}
    if vigentes:
        aplicable = por_id.get(aplicable_id) if aplicable_id else None
        if aplicable is not None:
            estado, publicada = _ESTADO_VISIBLE[aplicable["estado"]], aplicable["estado"] == cat.DEFINITIVA
        else:                                          # promedio: definitivo sólo si todo lo que promedia ya lo es
            todas = all(c["estado"] == cat.DEFINITIVA for c in vigentes)
            estado, publicada = (cat.DEFINITIVO if todas else cat.REVISADO), todas
    elif any(c["estado"] == cat.REABIERTA for c in calificaciones):
        estado, publicada = cat.REABIERTO, False
    elif validos:
        estado, publicada = estado_de_intento(max(validos, key=lambda i: i.get("numero", 0))), False
    elif intentos:
        estado, publicada = cat.ANULADO, False
    else:
        estado, publicada = cat.PENDIENTE, False
    return ResultadoCalculado(estado_simple(intentos), estado, aplicable_id, puntaje, len(validos), len(vigentes), publicada)


# --------------------------------------------------------------------------------------------------- agregados

@dataclass(frozen=True)
class AgregadoCalculado:
    calificaciones: int
    promedio_simple: Decimal | None
    pendientes: int
    provisionales: int
    publicadas: int


def calcular_agregado(resultados: list[dict]) -> AgregadoCalculado:
    """El agregado de un alumno en un periodo y un curso: sobre los resultados de las evaluaciones que afectan la calificación oficial. El promedio es
    SIMPLE (media de los resultados aplicables ya registrados) y NO oficial: no hay ponderación hasta que la institución la declare (V1)."""
    valores = [r["puntaje_aplicable"] for r in resultados if r.get("puntaje_aplicable") is not None and r.get("cuenta", True)]
    estados = [r["estado_calificacion"] for r in resultados]
    return AgregadoCalculado(
        calificaciones=len(valores), promedio_simple=pj.promedio(valores), pendientes=estados.count(cat.PENDIENTE),
        provisionales=estados.count(cat.PROVISIONAL), publicadas=sum(1 for r in resultados if r.get("publicada")))


# --------------------------------------------------------------------------------- lo que revisa un humano

def forma_de_revision(tipo_pregunta: str, respuesta: dict | None) -> str:
    """Qué clase de revisión humana pide una pregunta: respuesta abierta, dibujo o proyecto/entrega. Las referencias a evidencias (dibujo, audio) son
    de MOD-014: aquí sólo se reconocen, no se guardan."""
    if tipo_pregunta in ("project", "assignment", "submission", "proyecto"):
        return "proyecto"
    if tipo_pregunta in ("drawing", "dibujo") or (isinstance(respuesta, dict) and respuesta.get("drawingRef")):
        return "dibujo"
    return "abierta"
