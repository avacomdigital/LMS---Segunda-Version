"""
Composition root de MOD-007: el único sitio que sabe qué adaptador va con qué puerto
y cómo se construyen las URL de los medios que consume el cliente MAUI.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import quote

from django.conf import settings
from django.db import transaction

from acceso.interfaces.medios import con_pase

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


def ejemplo_permitido() -> bool:
    """El manifiesto de ejemplo sólo existe para pruebas y desarrollo (`AVACOM_AULA_PERMITIR_EJEMPLO=1`). En un nodo real está apagado."""
    return bool(getattr(settings, "AVACOM_AULA_PERMITIR_EJEMPLO", False))


def fuente_por_defecto() -> str:
    nombre = getattr(settings, "AVACOM_AULA_FUENTE_CURSOS", "biblioteca") or "biblioteca"
    return nombre if nombre != "ejemplo" or ejemplo_permitido() else "biblioteca"


def fuente(nombre: str | None, curso_ref: str = ""):
    """La fuente pedida; sin nombre, la configurada. Los cursos salen SIEMPRE de la biblioteca: pedir «ejemplo» con el ejemplo apagado (lo normal)
    se resuelve con la biblioteca. Con el ejemplo permitido (pruebas), si no se pidió ninguna y la referencia es la del manifiesto de ejemplo, se
    resuelve sola: así las URL de medios no dependen del parámetro."""
    if nombre:
        if nombre not in FUENTES:
            raise DatosInvalidos(f"Fuente desconocida «{nombre}». Fuentes: {', '.join(FUENTES)}.", fuente=nombre)
        return FuenteEjemplo(ruta_ejemplo()) if nombre == "ejemplo" and ejemplo_permitido() else FuenteBiblioteca()
    if ejemplo_permitido() and curso_ref and (curso_ref in ALIAS or _es_el_ejemplo(curso_ref)):
        return FuenteEjemplo(ruta_ejemplo())
    return fuente(fuente_por_defecto())


def _es_el_ejemplo(curso_ref: str) -> bool:
    try:
        return str(FuenteEjemplo(ruta_ejemplo())._leer().get("id", "")) == curso_ref
    except Exception:
        return False


def url_medio(nombre_fuente: str, curso_ref: str, media_ref: str, ruta: str | None) -> str:
    """La dirección de un medio para el visor. Con sesión (la petición que arma la lección la trae) lleva el pase en el camino
    (`/api/m/<pase>/aula/…`, ver `acceso/interfaces/medios.py`): quien la abre es una WebView o una `Image`, que no mandan `Authorization`."""
    base = f"/api/aula/cursos/{quote(curso_ref, safe='')}/medios/{quote(media_ref, safe='')}/"
    if ruta:
        base += quote(ruta.strip("/"), safe="/")
    return con_pase(f"{base}?fuente={nombre_fuente}")


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


def preparar_medios_del_aula(sesion_id: str, fuente: str | None, curso_ref: str, estructura, reemplazar_proyeccion: bool, actor_id: str) -> None:
    """Lo que el profesor proyecta o lanza se pone en la cola de medios del nodo (`cola_medios`) con la prioridad más alta, al confirmarse la transacción
    del caso de uso: así las tabletas lo encuentran ya en la caché del nodo en vez de pedirlo todas a la vez a AVACOM Contenido."""
    from cola_medios import servicio as cola    # importación tardía: `cola_medios` importa este módulo

    def preparar() -> None:
        try:
            cola.preparar_objeto(estructura, fuente=fuente, curso_ref=curso_ref, modulo=cola.MODULO_AULA, contexto_ref=sesion_id, prioridad=cola.PROYECCION,
                                 persona_id=actor_id, reemplazar=reemplazar_proyeccion)
        except Exception:   # noqa: BLE001 — un fallo al confirmar no puede convertir en error una clase que ya quedó escrita
            logging.getLogger("avacom.aula").exception("No se pudieron preparar los medios de la clase", extra={"evento": "medios.cola.preparar_fallo"})

    transaction.on_commit(preparar)


def servicios() -> Servicios:
    return Servicios(
        uow=FabricaUoWAula(),
        uow_lectura=FabricaUoWAula(solo_lectura=True),
        fuente=fuente,
        reloj=RelojNodo(),
        autorizacion=AutorizacionAula(),
        url_medio=url_medio,
        config=configuracion(),
        limitador=limitador(),
        preparar_medios=preparar_medios_del_aula,
    )
