"""
Lo común a los casos de uso de MOD-018: los servicios que entrega el composition root, la configuración, el resumen de una licencia que SÍ se puede mostrar (sin firma ni huellas),
la huella de este equipo y el armado de la instantánea que lee el camino caliente. Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio import cupo, estado as est, huella as hu
from ..dominio.licencia import ILIMITADO, Licencia
from ..dominio.politica import POLITICA_PROVISIONAL, Politica
from .puertos import (Actor, Almacen, Anclas, Auditoria, Autorizacion, Claves, Conteos, EquiposConIdentidad, FuenteDeAtestacion, FuenteDeHuella, Instantanea, Nodo, Outbox, Reloj,
                      Retos, UnidadDeTrabajo, Vivo)


@dataclass(frozen=True)
class ConfigLicencia:
    """Lo que decide la instalación (`AVACOM_LICENCIA_*`) y el entorno que clasificó P-12. Los casos de uso sólo ven este objeto."""

    politica: Politica = POLITICA_PROVISIONAL
    entorno: str = "produccion"                    # produccion | desarrollo | pruebas (dominio/entorno.py)
    modo: str = "firmada"                          # firmada | ilimitada
    version_del_nodo: str = ""
    # BR-063: los valores de `settings` que valen cuando no hay licencia (desarrollo y pruebas).
    concurrencia_normal: int = 50
    concurrencia_pico: int = 100
    # Fase 5 (P-24): la garantía mínima de identidad que exige la licencia para dar de alta un equipo NUEVO (`declarada` = ninguna, lo de siempre; `software`; `hardware`). Nunca afecta a un
    # equipo que ya existe. `AVACOM_LICENCIA_IDENTIDAD_MINIMA`.
    identidad_minima: str = "declarada"


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[..., UnidadDeTrabajo]
    reloj: Reloj
    huella: FuenteDeHuella
    nodo: Nodo
    anclas: Anclas
    almacen: Almacen
    claves: Claves
    conteos: Conteos
    autorizacion: Autorizacion
    vivo: Vivo
    config: ConfigLicencia = field(default_factory=ConfigLicencia)
    retos: Retos | None = None
    atestacion: FuenteDeAtestacion | None = None
    equipos: EquiposConIdentidad | None = None
    bloqueo: threading.RLock = field(default_factory=threading.RLock)      # el programador y una acción del administrador no se mezclan


def nuevo_id() -> str:
    return str(uuid.uuid4())


class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios


# ------------------------------------------------------------------------------------------------------------------- lo que se puede mostrar
def corto(sha256: str) -> str:
    """Los primeros 12 caracteres de una huella de archivo: suficientes para citarla en pantalla y en la bitácora."""
    return (sha256 or "")[:12]


def resumen_de_licencia(lic: Licencia) -> dict:
    """La licencia tal como la ve el administrador: sin la firma, sin los hashes de la huella y sin el hash de la llave del nodo."""
    return {
        "id": lic.id, "serie": lic.serie, "aula": lic.aula, "tipo": lic.tipo, "emitida": lic.emitida, "desde": lic.desde, "vence": lic.vence, "gracia_dias": lic.gracia_dias,
        "limites": limites_a_dict(lic.limites), "capacidades": sorted(lic.capacidades), "liberacion_pendiente": lic.liberacion_pendiente,
        "liberacion_dias": lic.liberacion_dias, "kid": lic.kid, "archivo": corto(lic.sha256),
    }


def limites_a_dict(limites) -> dict:
    def tope(valor: int) -> int | None:
        return None if valor == ILIMITADO else int(valor)
    return {"equipos": tope(limites.equipos), "usuarios": tope(limites.usuarios), "concurrentes_normal": tope(limites.concurrentes_normal), "concurrentes_pico": tope(limites.concurrentes_pico)}


def resumen_de_huella(coincidencia: hu.Coincidencia | None, nivel_actual: str) -> dict:
    """Sólo cifras y nivel: ningún identificador, ni crudo ni hasheado."""
    if coincidencia is None:
        return {"nivel": nivel_actual, "coincide": None, "parcial": False, "k": None, "factores": None, "coinciden": None}
    return {"nivel": coincidencia.nivel, "coincide": coincidencia.ok, "parcial": coincidencia.parcial, "k": coincidencia.k, "factores": coincidencia.en_licencia,
            "coinciden": coincidencia.coinciden}


def ilimitada(config: ConfigLicencia, ahora: int) -> Instantanea:
    """La instantánea de desarrollo y pruebas (R-05): nada se restringe y los límites de concurrencia son los de `settings`."""
    todas = frozenset(cat.CAPACIDADES_LICENCIABLES)
    from ..dominio.licencia import Limites
    limites = Limites(ILIMITADO, ILIMITADO, config.concurrencia_normal, config.concurrencia_pico)
    e = est.Estado(cat.ACTIVA, cat.M_LICENCIA_ILIMITADA, ahora, None, None, frozenset(), todas, limites, "desarrollo", None, None)
    return Instantanea(estado=e, modo="ilimitada", entorno=config.entorno, calculada_en=ahora, limites_de_concurrencia=(config.concurrencia_normal, config.concurrencia_pico))


def concurrencia_de(snapshot: Instantanea | None, config: ConfigLicencia) -> tuple[int, int]:
    """`(normal, pico)` de BR-063: de la licencia vigente; sin ella, los valores de `settings`."""
    if snapshot is None or snapshot.estado is None or snapshot.modo == "ilimitada":
        return config.concurrencia_normal, config.concurrencia_pico
    lim = snapshot.estado.limites
    return cupo.concurrencia(lim.concurrentes_normal, lim.concurrentes_pico, config.concurrencia_normal, config.concurrencia_pico)


__all__ = ["Actor", "ConfigLicencia", "Servicios", "_CasoDeUso", "concurrencia_de", "corto", "ilimitada", "limites_a_dict", "nuevo_id", "resumen_de_huella", "resumen_de_licencia"]
