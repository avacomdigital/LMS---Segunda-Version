"""
Composition root: el único sitio que sabe qué adaptador va con qué puerto.
Cambiar Django ORM por SQLAlchemy o Argon2 por otro hasher se hace aquí.
"""
from __future__ import annotations

from django.conf import settings

from ..aplicacion.casos_uso import Servicios
from .seguridad import AzarSeguro, CifradorAesGcm, Claves, EmisorJwt, HasherArgon2, RelojSistema
from .unidad_trabajo import FabricaUoWDjango

_cache: dict[tuple, Servicios] = {}


def _huella() -> tuple:
    argon = getattr(settings, "AVACOM_LMS_ARGON2", {}) or {}
    return (
        getattr(settings, "AVACOM_LMS_CLAVE_DATOS", None),
        getattr(settings, "AVACOM_LMS_CLAVE_INDICE", None),
        getattr(settings, "AVACOM_LMS_CLAVE_TOKENS", None),
        settings.SECRET_KEY,
        tuple(sorted(argon.items())),
    )


def servicios() -> Servicios:
    """Servicios listos para los casos de uso. Se cachean por configuración (las pruebas la cambian)."""
    huella = _huella()
    if huella not in _cache:
        claves = Claves(huella[0], huella[1], huella[2], settings.SECRET_KEY)
        argon = dict(getattr(settings, "AVACOM_LMS_ARGON2", {}) or {})
        cifrador = CifradorAesGcm(claves)
        _cache.clear()
        _cache[huella] = Servicios(
            uow=FabricaUoWDjango(cifrador),
            uow_lectura=FabricaUoWDjango(cifrador, solo_lectura=True),
            cache_pases_seg=float(getattr(settings, "AVACOM_PASE_MEDIOS_CACHE_SEG", 15)),
            hasher=HasherArgon2(**argon),
            cifrador=cifrador,
            tokens=EmisorJwt(claves),
            reloj=RelojSistema(),
            azar=AzarSeguro(),
        )
    return _cache[huella]
