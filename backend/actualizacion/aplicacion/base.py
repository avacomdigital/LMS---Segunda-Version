"""
Lo común a los casos de uso de MOD-017: los servicios que entrega el composition root, la configuración y lo que un paquete y su historial muestran. Ningún archivo de esta
carpeta importa Django.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio import estados
from .puertos import (Almacen, Auditoria, Aula, Autorizacion, Claves, Eventos, Fuentes, Licencia, RegistroModulos, Reloj, Respaldo, UnidadDeTrabajo, Vivo)


@dataclass(frozen=True)
class ConfigActualizacion:
    """Lo que decide la instalación (`AVACOM_ACTUALIZACION_*`) y el entorno. Los casos de uso sólo ven este objeto."""

    entorno: str = "produccion"                       # produccion | desarrollo | pruebas (el mismo criterio de MOD-018, P-12)
    max_paquete_bytes: int = cat.MAX_PAQUETE_BYTES
    dias_reversion: int = cat.DIAS_REVERSION
    margen_clase_ms: int = cat.MARGEN_ANTES_DE_CLASE_MIN * cat.MINUTO_MS
    canal: str = ""                                   # P-18: el canal por internet (apagado de fábrica: cadena vacía)
    version_del_nodo: str = "desarrollo"


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[..., UnidadDeTrabajo]
    reloj: Reloj
    claves: Claves
    registro: RegistroModulos
    fuentes: Fuentes
    almacen: Almacen
    aula: Aula
    licencia: Licencia
    respaldo: Respaldo
    autorizacion: Autorizacion
    vivo: Vivo
    config: ConfigActualizacion = field(default_factory=ConfigActualizacion)
    bloqueo: threading.RLock = field(default_factory=threading.RLock)      # el vigilante y una acción del administrador no se mezclan


def nuevo_id() -> str:
    return str(uuid.uuid4())


class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios

    def ahora(self) -> int:
        return int(self.s.reloj.ahora_ms())


# ------------------------------------------------------------------------------------------------------------------- lo que se puede mostrar
def corto(sha256: str) -> str:
    return (sha256 or "")[:12]


def fila_a_dict(fila: dict) -> dict:
    return {"id": fila.get("id"), "paquete_id": fila.get("paquete_id") or None, "tipo": fila["tipo"], "en": fila["en"], "actor": fila.get("actor") or "", "serie": fila.get("serie", 0),
            "version_producto": fila.get("version_producto") or "", "detalle": fila.get("detalle") or {}}


def paquete_a_dict(paquete: dict, filas: list[dict], ahora: int, dias_reversion: int = cat.DIAS_REVERSION) -> dict:
    """La ficha de un paquete con su estado DERIVADO (P-05): qué cambia, peso, serie, compatibilidad, ventana, reversión."""
    d = estados.derivar([_Fila(f) for f in filas], dias_reversion)
    manifiesto = paquete.get("manifiesto") or {}
    return {
        "paquete_id": paquete["paquete_id"], "nombre": paquete["nombre"], "version_producto": paquete["version_producto"], "serie": paquete["serie"], "modulos": list(paquete.get("modulos") or []),
        "kid": paquete["kid"], "sha256": paquete["sha256"], "bytes": paquete["bytes"], "archivo": paquete.get("archivo") or "", "origen": paquete["origen"], "recibido_en": paquete["recibido_en"],
        "importado_por": paquete.get("importado_por") or "", "manifiesto": manifiesto,
        "estado": d.estado, "en_curso": d.en_curso, "accion": d.accion, "orden_id": d.orden_id, "ventana": d.ventana, "aplicado_en": d.aplicado_en, "revertible_hasta": d.revertible_hasta,
        "revertible": d.revertible(ahora), "incompatibilidades": list(d.incompatibilidades), "ultima_en": d.ultima_en, "historial": [fila_a_dict(f) for f in filas],
    }


@dataclass(frozen=True)
class _Fila:
    """Una fila del historial como la ve el dominio."""

    datos: dict

    @property
    def tipo(self) -> str:
        return self.datos["tipo"]

    @property
    def en(self) -> int:
        return int(self.datos["en"])

    @property
    def detalle(self) -> dict:
        return self.datos.get("detalle") or {}


def derivado_de(filas: list[dict], dias_reversion: int = cat.DIAS_REVERSION) -> estados.Derivado:
    return estados.derivar([_Fila(f) for f in filas], dias_reversion)
