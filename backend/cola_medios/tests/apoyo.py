"""Apoyo a las pruebas que tocan la cola de medios (las suyas y las de otros módulos que prueban la capa que está debajo de ella)."""
from __future__ import annotations

import dataclasses

from ..infraestructura import contenedor


def configurar_cola(caso, **cambios):
    """Reinicia la cola de medios del proceso con la configuración de pruebas cambiada (`activa=False`, `hilos=2`, `max_bytes=…`…) y la devuelve; al terminar el
    caso la deja como estaba."""
    servidor = contenedor.reiniciar(dataclasses.replace(contenedor.configuracion(), **cambios))
    caso.addCleanup(contenedor.reiniciar)
    return servidor


def sin_cola(caso):
    """Para las pruebas de lo que hay DEBAJO de la cola (la sesión de medios de Contenido, el paso a través): la cola apagada, todo va a la fuente."""
    return configurar_cola(caso, activa=False)
