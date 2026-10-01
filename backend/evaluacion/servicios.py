"""
La interfaz de MOD-010 para los OTROS módulos del mismo proceso (BR-004: quien necesita un dato ajeno invoca la interfaz del propietario). La usa el aula
al cerrar una clase: cuenta los intentos que sus alumnos siguen presentando (JRN-011). Devuelve cifras planas; no abre ninguna transacción.
"""
from __future__ import annotations

from .infraestructura.unidad_trabajo import Cajones


def intentos_vivos_de(persona_ids: list[str]) -> int:
    """Cuántos intentos de MOD-010 siguen en curso, pausados o restaurándose entre esas personas."""
    return Cajones().intentos.vivos_de_personas(list(persona_ids))
