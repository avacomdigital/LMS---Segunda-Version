"""
El CORTE de un módulo (P-05): el instante en que deja de escribir en su cola antigua (`m*_evento_salida`, que queda intacta como historia de sólo lectura, BR-016) y pasa a
escribir sólo en `m15_evento` (R-03). Es una fila (`m15_corte`: módulo, `ultima_legada`, fecha) escrita en la MISMA transacción que sube el contador global a
`max(contador actual, ultima_legada)`, para que toda marca anterior siga valiendo: las marcas viejas son `id` de la tabla antigua y las nuevas, secuencias globales MAYORES.

La fachada de lectura presenta UN flujo continuo por fuente: primero lo que quedó en la tabla antigua (`id ≤ ultima_legada`), después las filas de `m15_evento` de ese módulo.
Resultado: un consumidor con una marca previa al corte no pierde ni repite nada, y uno reconstruido (marca 0) reproduce toda la historia (BR-007).

Puro: no importa Django. Las lecturas reales las hacen los adaptadores; aquí sólo se decide qué leer y cómo se fusiona.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Corte:
    modulo: str
    ultima_legada: int            # el último `id` de la tabla antigua en el momento del corte (0 si estaba vacía)
    cortado_en: int


@dataclass(frozen=True)
class PlanDeLectura:
    legado: tuple[int, int, int] | None     # (desde, limite, hasta) a pedir a la tabla antigua, o None si no hay nada que pedir ahí
    nuevo: tuple[int, int] | None           # (desde, limite) a pedir a `m15_evento`, o None si el tramo legado aún no se agotó


def contador_tras_corte(contador_actual: int, ultima_legada: int) -> int:
    """A dónde salta el contador de `m15_evento` al cortar: nunca por debajo del último id legado (ni del contador que ya tiene)."""
    return max(int(contador_actual or 0), int(ultima_legada or 0))


def piso_del_contador(cortes) -> int:
    """Por debajo de qué valor NUNCA puede quedar el contador de `m15_evento` mientras haya módulos cortados: el mayor `ultima_legada` (D-28). Una reconstrucción de la tabla (SQLite
    la hace al alterar una columna) devuelve el AUTOINCREMENT a `max(secuencia)`; si eso queda por debajo de un corte, el siguiente evento de ese módulo saldría bajo su corte y la
    fachada no lo serviría. Lo reponen toda migración que reconstruya la tabla y el arranque del nodo."""
    return max((int(c.ultima_legada) for c in cortes), default=0)


def planear(desde: int, limite: int, corte: Corte | None) -> PlanDeLectura:
    """
    Qué pedir a cada tabla para servir `limite` eventos con secuencia > `desde`:
      · sin corte: todo sale de `m15_evento` (el módulo todavía no publica aquí, o nunca tuvo cola antigua);
      · con corte y `desde` por debajo de `ultima_legada`: primero la tabla antigua (hasta `ultima_legada`), y lo que falte de `m15_evento` desde `ultima_legada`;
      · con corte y `desde` ya en la zona nueva: sólo `m15_evento`.
    """
    desde, limite = int(desde), max(1, int(limite))
    if corte is None or desde >= corte.ultima_legada:
        return PlanDeLectura(None, (desde, limite))
    return PlanDeLectura((desde, limite, corte.ultima_legada), (corte.ultima_legada, limite))


def fusionar(plan: PlanDeLectura, legados: list[dict], hasta_legado: int, leer_nuevo: Callable[[int, int], tuple[list[dict], int]]) -> tuple[list[dict], int]:
    """
    Arma `(eventos, hasta)` con lo que devolvió la tabla antigua y, si el tramo legado se agotó dentro del límite, lo que haga falta de `m15_evento`. `hasta` es la secuencia
    hasta la que se MIRÓ (la que el consumidor puede tomar como marca si aplicó todo): la última del lote si el lote llenó el límite, o la última que existía.
    """
    if plan.legado is None:
        return leer_nuevo(*plan.nuevo)
    _desde, limite, tope = plan.legado
    eventos = list(legados)
    if len(eventos) >= limite:
        return eventos[:limite], int(eventos[limite - 1]["secuencia"])
    # El tramo legado quedó agotado (el adaptador miró hasta `tope`): lo que falte viene de la cola nueva, desde el tope del corte.
    if hasta_legado < tope:
        hasta_legado = tope
    nuevos, hasta_nuevo = leer_nuevo(tope, limite - len(eventos))
    eventos += nuevos
    return eventos, max(int(hasta_legado), int(hasta_nuevo))


def marca_vigente(marca: int, corte: Corte | None) -> bool:
    """¿Una marca anterior al corte sigue valiendo tras él? Siempre: los `id` legados son ≤ `ultima_legada` y las secuencias nuevas son mayores (el contador saltó)."""
    return corte is None or int(marca) >= 0
