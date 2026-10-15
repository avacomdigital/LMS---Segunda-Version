"""
Compuertas de resultado: el punto por el que OTRO módulo puede RETENER lo que MOD-010 ya dejaría ver al alumno.

MOD-010 decide cuándo un resultado se puede mostrar según su política de publicación (RF-004: `al_entregar`, `tras_liberar`, `al_finalizar_grupo`, `programada`, `nunca`). Un módulo
que es dueño de la NOTA (MOD-011 · Gradebook) necesita añadir una condición suya —«que la calificación esté publicada»— sin que MOD-010 lo conozca ni lo importe: MOD-010 define este
puerto y el otro módulo registra su compuerta al arrancar. Una compuerta sólo puede CERRAR: nunca abre lo que la política de MOD-010 mantiene cerrado.

  · Sin compuertas registradas, MOD-010 se comporta exactamente como siempre.
  · Una compuerta recibe `(asignacion, intento)` y responde `True` si NO retiene el resultado. Se consulta sólo cuando la política ya lo permitiría (no cuesta nada mientras está cerrado).
  · Si una compuerta falla, el resultado QUEDA retenido y el fallo se registra: ante la duda, el alumno no ve una nota que quizá no esté publicada.
Dominio puro: ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger("avacom.evaluacion.compuertas")

Compuerta = Callable[[dict, dict], bool]

_COMPUERTAS: dict[str, Compuerta] = {}


def registrar(nombre: str, compuerta: Compuerta) -> None:
    """Registra (o reemplaza) la compuerta de `nombre`. Idempotente: el arranque de la aplicación puede ocurrir más de una vez en el mismo proceso."""
    _COMPUERTAS[nombre] = compuerta


def retiene(asignacion: dict, intento: dict) -> str | None:
    """El nombre de la primera compuerta que retiene este resultado, o `None` si ninguna lo retiene."""
    for nombre, compuerta in tuple(_COMPUERTAS.items()):
        try:
            if not compuerta(asignacion, intento):
                return nombre
        except Exception:      # noqa: BLE001 — una compuerta rota cierra, no abre
            log.exception("La compuerta de resultado «%s» falló; el resultado del intento %s queda retenido", nombre, intento.get("id"))
            return nombre
    return None


def registradas() -> tuple[str, ...]:
    return tuple(_COMPUERTAS)
