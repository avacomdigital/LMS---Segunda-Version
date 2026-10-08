"""
Qué medios usa un objeto de la vista de aula (lámina, lectura, laboratorio, actividad…): todo `media_ref` que aparece en su estructura, sin importar
cuán adentro esté (bloques, opciones, pausas de un video, la página html de una lámina).
"""
from __future__ import annotations

from typing import Any

MAXIMO_REFERENCIAS = 200


def medios_de(estructura: Any) -> list[tuple[str, str]]:
    """[(media_ref, ruta)] sin repetir y en el orden en que aparecen. Un medio html lleva la ruta de su página de entrada."""
    vistos: dict[tuple[str, str], None] = {}

    def recorrer(nodo: Any) -> None:
        if len(vistos) >= MAXIMO_REFERENCIAS:
            return
        if isinstance(nodo, dict):
            ref = nodo.get("media_ref")
            if isinstance(ref, str) and ref and not nodo.get("ausente"):
                entrada = nodo.get("entrada")
                vistos.setdefault((ref, entrada.strip("/") if isinstance(entrada, str) else ""), None)
            for valor in nodo.values():
                if isinstance(valor, (dict, list)):
                    recorrer(valor)
        elif isinstance(nodo, list):
            for elemento in nodo:
                recorrer(elemento)

    recorrer(estructura)
    return list(vistos)
