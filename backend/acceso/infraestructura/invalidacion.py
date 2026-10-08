"""
Las escrituras de los repositorios que pueden cambiar la persona de una sesión vacían la caché de pases (`aplicacion/cache_pases.py`).

Se vacía dos veces: ya, y cuando la transacción en curso se confirme. Entre una cosa y la otra otra petición pudo volver a llenar la caché leyendo lo
viejo (la base todavía no ve el cambio), y esa copia viva duraría `CACHE_PASES_SEG`. Este archivo es el único que conoce `transaction`: la aplicación
no importa el framework.
"""
from __future__ import annotations

import functools

from django.db import transaction

from ..aplicacion import cache_pases


def invalida(funcion):
    """Decorador para los métodos de repositorio que escriben algo de lo que decide quién es la persona de una sesión."""
    @functools.wraps(funcion)
    def envuelta(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        finally:
            cache_pases.limpiar(funcion.__qualname__)
            transaction.on_commit(cache_pases.limpiar)
    return envuelta
