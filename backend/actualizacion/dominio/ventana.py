"""
La ventana de aplicación (P-08, CAP-108, FUN-182, C-2): una ventana ÚNICA en MVP (las recurrentes son V1, Q-U1). Puro: recibe el instante, no lo lee.

  · `validar`: «desde» como mucho cinco minutos en el pasado y noventa días en el futuro; «hasta» entre diez minutos y un día después de «desde».
  · `decidir`: dentro de la ventana, con cero sesiones activas y a más de 15 minutos de la próxima clase programada (si el nodo la conoce; hoy no, Q-U9), se abre.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import catalogos as cat
from .errores import DatosInvalidos

FUERA_DE_VENTANA, SESION_ACTIVA, CLASE_PROXIMA, SIN_VENTANA = "fuera_de_ventana", "sesion_activa", "clase_proxima", "sin_ventana"


@dataclass(frozen=True)
class Ventana:
    desde: int
    hasta: int

    def abierta(self, ahora: int) -> bool:
        return self.desde <= int(ahora) < self.hasta

    def vencida(self, ahora: int) -> bool:
        return int(ahora) >= self.hasta

    def como_dict(self) -> dict:
        return {"desde": self.desde, "hasta": self.hasta}


def validar(desde, hasta, ahora: int) -> Ventana:
    if isinstance(desde, bool) or isinstance(hasta, bool) or not isinstance(desde, int) or not isinstance(hasta, int):
        raise DatosInvalidos("La ventana se indica con «desde» y «hasta» en milisegundos del reloj del nodo.")
    if desde < int(ahora) - cat.VENTANA_TOLERANCIA_PASADO_MS:
        raise DatosInvalidos("La ventana empieza en el pasado.")
    if desde > int(ahora) + cat.VENTANA_MAX_ADELANTO_MS:
        raise DatosInvalidos("La ventana está demasiado lejos: como mucho a 90 días.")
    if hasta - desde < cat.VENTANA_MIN_MS:
        raise DatosInvalidos("La ventana dura menos de diez minutos: no alcanza para aplicar y verificar.")
    if hasta - desde > cat.VENTANA_MAX_MS:
        raise DatosInvalidos("La ventana dura más de un día.")
    return Ventana(int(desde), int(hasta))


def decidir(ahora: int, ventana: Ventana | None, sesiones_activas: int, proxima_clase_en: int | None, margen_ms: int = cat.MARGEN_ANTES_DE_CLASE_MIN * cat.MINUTO_MS) -> tuple[bool, str]:
    """`(se puede empezar ahora, motivo)`. Nunca con una clase abierta (R-01); nunca a menos del margen de una clase programada."""
    if ventana is None:
        return False, SIN_VENTANA
    if not ventana.abierta(ahora):
        return False, FUERA_DE_VENTANA
    if int(sesiones_activas) > 0:
        return False, SESION_ACTIVA
    if proxima_clase_en is not None and 0 <= int(proxima_clase_en) - int(ahora) < margen_ms:
        return False, CLASE_PROXIMA
    return True, ""
