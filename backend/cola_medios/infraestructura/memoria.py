"""La memoria rápida de la cola: `LocMemCache` de Django (una caché aparte, `medios`, para que sus límites no afecten a nada más)."""
from __future__ import annotations

from django.core.cache import caches


class MemoriaLocal:
    def __init__(self, alias: str = "medios"):
        self._alias = alias

    @property
    def _cache(self):
        return caches[self._alias]

    def get(self, clave: str):
        return self._cache.get(clave)

    def set(self, clave: str, valor, segundos: int) -> None:
        self._cache.set(clave, valor, timeout=segundos)

    def delete(self, clave: str) -> None:
        self._cache.delete(clave)

    def vaciar(self) -> None:
        self._cache.clear()
