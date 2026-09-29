"""
Composition root de MOD-007: el único sitio que sabe qué adaptador va con qué puerto
y cómo se construyen las URL de los medios que consume el cliente MAUI.
"""
from __future__ import annotations

import time
from urllib.parse import quote

from django.conf import settings

from ..aplicacion.casos_uso import Servicios
from ..aplicacion.configuracion import ConfigAula
from ..dominio.errores import DatosInvalidos
from .fuente_biblioteca import FuenteBiblioteca
from .fuente_ejemplo import ALIAS, FuenteEjemplo
from .limitador import LimitadorEnMemoria
from .repositorios import AutorizacionAula
from .unidad_trabajo import FabricaUoWAula

FUENTES = ("biblioteca", "ejemplo")


class RelojNodo:
    """BR-062: la marca temporal autoritativa la pone el equipo del aula."""

    def ahora_ms(self) -> int:
        return int(time.time() * 1000)


def ruta_ejemplo() -> str:
    return getattr(settings, "AVACOM_AULA_CURSO_EJEMPLO", "") or ""


def fuente_por_defecto() -> str:
    return getattr(settings, "AVACOM_AULA_FUENTE_CURSOS", "biblioteca") or "biblioteca"


def fuente(nombre: str | None, curso_ref: str = ""):
    """La fuente pedida; sin nombre, la configurada. Si no se pidió ninguna y la referencia es la
    del manifiesto de ejemplo, se resuelve sola: así las URL de medios no dependen del parámetro."""
    if nombre:
        if nombre not in FUENTES:
            raise DatosInvalidos(f"Fuente desconocida «{nombre}». Fuentes: {', '.join(FUENTES)}.", fuente=nombre)
        return FuenteEjemplo(ruta_ejemplo()) if nombre == "ejemplo" else FuenteBiblioteca()
    if curso_ref and (curso_ref in ALIAS or _es_el_ejemplo(curso_ref)):
        return FuenteEjemplo(ruta_ejemplo())
    return fuente(fuente_por_defecto())


def _es_el_ejemplo(curso_ref: str) -> bool:
    try:
        return str(FuenteEjemplo(ruta_ejemplo())._leer().get("id", "")) == curso_ref
    except Exception:
        return False


def url_medio(nombre_fuente: str, curso_ref: str, media_ref: str, ruta: str | None) -> str:
    base = f"/api/aula/cursos/{quote(curso_ref, safe='')}/medios/{quote(media_ref, safe='')}/"
    if ruta:
        base += quote(ruta.strip("/"), safe="/")
    return f"{base}?fuente={nombre_fuente}"


def configuracion() -> ConfigAula:
    """Los tiempos y la capacidad del aula salen de `settings` (variables AVACOM_AULA_*)."""
    return ConfigAula(
        latido_vencido_ms=int(settings.AVACOM_AULA_LATIDO_VENCIDO_MS),
        ausencia_ms=int(settings.AVACOM_AULA_AUSENCIA_MS),
        inactividad_ms=int(settings.AVACOM_AULA_INACTIVIDAD_MS),
        dispositivos_normal=int(settings.AVACOM_AULA_DISPOSITIVOS_NORMAL),
        dispositivos_pico=int(settings.AVACOM_AULA_DISPOSITIVOS_PICO),
        unirse_intentos=int(settings.AVACOM_AULA_UNIRSE_INTENTOS),
        unirse_ventana_ms=int(settings.AVACOM_AULA_UNIRSE_VENTANA_MS),
    )


_limitador: LimitadorEnMemoria | None = None


def limitador() -> LimitadorEnMemoria:
    """Un solo limitador por proceso (el nodo es un proceso). Se recrea si cambia la configuración."""
    global _limitador
    c = configuracion()
    if _limitador is None or (_limitador.maximo, _limitador.ventana_ms) != (c.unirse_intentos, c.unirse_ventana_ms):
        _limitador = LimitadorEnMemoria(c.unirse_intentos, c.unirse_ventana_ms)
    return _limitador


def servicios() -> Servicios:
    return Servicios(
        uow=FabricaUoWAula(),
        fuente=fuente,
        reloj=RelojNodo(),
        autorizacion=AutorizacionAula(),
        url_medio=url_medio,
        config=configuracion(),
        limitador=limitador(),
    )
