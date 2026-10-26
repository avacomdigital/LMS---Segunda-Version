"""
Lo común a los casos de uso de MOD-016: los servicios que entrega el composition root, la configuración y la ficha de un respaldo con su estado DERIVADO. Ningún archivo de esta carpeta
importa Django.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio import estados
from .puertos import (Aplicador, Aula, Autorizacion, Almacen, Clavero, Modulos, Nodo, Origen, Reloj, Soporte, TrasRestaurar, UnidadDeTrabajo, Unidades, Vivo)


@dataclass(frozen=True)
class ConfigRespaldo:
    """Lo que decide la instalación y el entorno. Los casos de uso sólo ven este objeto."""

    entorno: str = "produccion"                         # produccion | desarrollo | pruebas (el mismo criterio de MOD-018, P-12)
    aviso_sin_respaldo_dias: int = cat.AVISO_SIN_RESPALDO_DIAS
    prueba_de_recuperacion_cada_dias: int = cat.PRUEBA_DE_RECUPERACION_CADA_DIAS
    verificar_al_terminar: bool = True
    margen_espacio: int = cat.MARGEN_ESPACIO


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[..., UnidadDeTrabajo]
    reloj: Reloj
    nodo: Nodo
    aula: Aula
    clavero: Clavero
    soporte: Soporte
    origen: Origen
    almacen: Almacen
    unidades: Unidades
    aplicador: Aplicador
    tras: TrasRestaurar
    modulos: Modulos
    autorizacion: Autorizacion
    vivo: Vivo
    config: ConfigRespaldo = field(default_factory=ConfigRespaldo)
    bloqueo: threading.RLock = field(default_factory=threading.RLock)      # el vigilante y una acción del técnico no se mezclan
    en_operacion: threading.Lock = field(default_factory=threading.Lock)  # un solo respaldo o restauración a la vez


def nuevo_id() -> str:
    return str(uuid.uuid4())


class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios

    def ahora(self) -> int:
        return int(self.s.reloj.ahora_ms())


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


def derivado_de(filas: list[dict], vivo: bool = False) -> estados.Derivado:
    return estados.derivar([_Fila(f) for f in filas], vivo)


def fila_a_dict(fila: dict) -> dict:
    return {"id": fila.get("id"), "respaldo_id": fila.get("respaldo_id") or None, "tipo": fila["tipo"], "en": fila["en"], "actor": fila.get("actor") or "", "detalle": fila.get("detalle") or {}}


def respaldo_a_dict(fila: dict | None, filas: list[dict], vivo: bool, respaldo_id: str = "") -> dict:
    """La ficha de un respaldo con su estado DERIVADO. Si la base no tiene la fila (nunca llegó a existir un archivo), se arma con lo que dijo el `iniciado`."""
    d = derivado_de(filas, vivo)
    inicio = next((f for f in filas if f["tipo"] in (cat.H_INICIADO, cat.H_REANUDADO)), None)
    detalle = (inicio or {}).get("detalle") or {}
    base = fila or {"respaldo_id": respaldo_id, "tipo": detalle.get("tipo") or cat.T_COMPLETO, "base_id": detalle.get("base_id") or "", "disparo": detalle.get("disparo") or cat.D_MANUAL,
                    "archivo": "", "sha256": "", "bytes": 0, "creado_en": int((inicio or {}).get("en") or 0), "secuencia_global": 0, "version_producto": "", "nodo_id": "", "entradas": 0,
                    "archivos": 0, "incluye_reinstalable": False, "con_custodia": False, "creado_por": (inicio or {}).get("actor") or ""}
    return {**{k: base[k] for k in ("respaldo_id", "tipo", "base_id", "disparo", "archivo", "sha256", "bytes", "creado_en", "secuencia_global", "version_producto", "entradas", "archivos",
                                    "incluye_reinstalable", "con_custodia", "creado_por")},
            "estado": d.estado, "restaurable": d.restaurable, "existe": d.existe, "ejecutado_en": d.ejecutado_en, "verificado_en": d.verificado_en, "exportado": d.exportado,
            "exportado_en": d.exportado_en, "error": d.error, "ultima_en": d.ultima_en}


def corto(identificador: str) -> str:
    return str(identificador or "")[:8].upper()
