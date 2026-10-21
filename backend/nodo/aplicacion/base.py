"""
Lo común a los casos de uso de MOD-015: la configuración que decide la instalación (`AVACOM_NODO_*`), los servicios que entrega el composition root y el ESTADO VIVO del proceso
(la marca alta del reloj, la última secuencia emitida, el ancla que ya se escribió, el estado del nodo que se vio por última vez). Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from ..dominio import catalogos as cat
from ..dominio.anclas import Ancla, ancla_siguiente, hay_que_refrescar, marca_siguiente
from ..dominio.estado import Umbrales
from .puertos import Anclas, Aplicador, Autorizacion, Contexto, LectorLegado, Reloj, Respaldo, Salud, Sincronizacion, UnidadDeTrabajo

log = logging.getLogger("avacom.nodo")


@dataclass(frozen=True)
class ConfigNodo:
    """Parámetros que decide la instalación (`AVACOM_NODO_*`). Los lee el composition root de `settings`; los casos de uso sólo ven este objeto."""

    estricto: bool = True                                   # pruebas y desarrollo: un tipo o una carga fuera de norma FALLAN; producción: se aceptan marcados (R-06)
    lote: int = cat.LOTE_DE_EVENTOS
    max_intentos: int = cat.MAX_INTENTOS
    espera_base_ms: int = cat.ESPERA_BASE_MS
    espera_tope_ms: int = cat.ESPERA_TOPE_MS
    jitter: float = cat.JITTER
    rezago_limite: int = cat.REZAGO_LIMITE
    ciclo_meses: int = cat.CICLO_MESES_POR_DEFECTO
    retencion_minima_dias: int = cat.RETENCION_MINIMA_DIAS
    purga_habilitada: bool = False                          # AVACOM_NODO_PURGA=0 por defecto (P-08)
    eventos_tecnicos: bool = True                           # publicar los nodo.* agregados por lote (Q-N6)
    margen_secuencia: int = cat.MARGEN_SECUENCIA
    ancla_cada_ms: int = cat.ANCLA_CADA_MS
    ancla_cada_eventos: int = cat.ANCLA_CADA_EVENTOS
    carga_max_bytes: int = cat.CARGA_MAX_BYTES
    umbrales: Umbrales = Umbrales()
    consumidores_nucleo: tuple[str, ...] = ()               # los que, suspendidos por rezago crítico, restringen el nodo (Q-N1)
    version_del_nodo: str = "desarrollo"


class EstadoVivo:
    """Lo que vive en memoria mientras el proceso corre. Un candado: lo tocan las vistas, los programadores y los consumidores a la vez."""

    def __init__(self):
        self._candado = threading.Lock()
        self.marca_alta = 0                  # el instante más alto que este proceso vio (P-13)
        self.ultima_emitida = 0              # la mayor secuencia emitida por este proceso
        self.ancla = Ancla()                 # la última ancla ESCRITA
        self.estado = cat.ARRANCANDO         # el último estado del nodo evaluado
        self.motivos: tuple[str, ...] = ()
        self.arranque_id: int | None = None
        self.arrancado = True                # False SÓLO mientras `Arrancar` corre: un proceso que no arranca por `asgi.py` (una prueba, un comando) no se queda «arrancando»
        self.apagado_sucio = False           # el arranque anterior no se cerró limpio
        self.transaccion_inmediata = True
        self.base_integra = True
        self.restauracion: dict | None = None

    def ahora(self, reloj_ms: int) -> int:
        """`max(reloj, marca alta)` y la marca sube (monótona)."""
        with self._candado:
            self.marca_alta = marca_siguiente(self.marca_alta, reloj_ms)
            return self.marca_alta

    def emitida(self, secuencia: int) -> None:
        with self._candado:
            if int(secuencia) > self.ultima_emitida:
                self.ultima_emitida = int(secuencia)

    def toca_anclar(self, ahora: int, cada_ms: int, cada_eventos: int) -> Ancla | None:
        """Si toca refrescar el ancla, devuelve la que hay que escribir (y la da por escrita); si no, None. La primera vez sólo abre la ventana de tiempo."""
        with self._candado:
            if self.ancla.escrita_en == 0:
                self.ancla = Ancla(self.ancla.secuencia, self.ancla.marca_alta, int(ahora))
            if not hay_que_refrescar(self.ancla, self.ultima_emitida, ahora, cada_ms=cada_ms, cada_eventos=cada_eventos):
                return None
            self.ancla = ancla_siguiente(self.ancla, self.ultima_emitida, self.marca_alta, ahora)
            return self.ancla

    def ancla_actual(self, ahora: int) -> Ancla:
        with self._candado:
            self.ancla = ancla_siguiente(self.ancla, self.ultima_emitida, self.marca_alta, ahora)
            return self.ancla

    def cambiar_estado(self, estado: str, motivos: tuple[str, ...]) -> bool:
        """Devuelve True si el estado cambió (BR-130: sólo entonces se publica algo)."""
        with self._candado:
            cambio = estado != self.estado or tuple(motivos) != self.motivos
            self.estado, self.motivos = estado, tuple(motivos)
            return cambio


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[..., UnidadDeTrabajo]
    reloj: Reloj
    contexto: Contexto
    anclas: Anclas
    autorizacion: Autorizacion
    respaldo: Respaldo
    sincronizacion: Sincronizacion
    salud: Salud
    config: ConfigNodo = ConfigNodo()
    vivo: EstadoVivo = field(default_factory=EstadoVivo)
    legados: dict[str, LectorLegado] = field(default_factory=dict)       # módulo cortado → lector de su tabla antigua (P-05)
    aplicadores: dict[str, Aplicador] = field(default_factory=dict)      # consumidor → su `aplicar` (para reprocesar, FUN-164)
    rng: random.Random = field(default_factory=random.Random)

    def ahora_ms(self) -> int:
        """El reloj del nodo (P-13): `max(reloj del sistema, marca alta)`."""
        return self.vivo.ahora(self.reloj.ahora_ms())

    def anclar_si_toca(self, ahora: int) -> None:
        """Refresca el ancla por lotes (P-12). Un fallo al escribirla no detiene a nadie: se registra y se vuelve a intentar en el siguiente lote."""
        ancla = self.vivo.toca_anclar(ahora, self.config.ancla_cada_ms, self.config.ancla_cada_eventos)
        if ancla is None:
            return
        try:
            self.anclas.escribir(ancla)
        except Exception:   # noqa: BLE001 — R-01: el ancla es una protección, no una condición para publicar
            log.exception("No se pudo escribir el ancla de la secuencia", extra={"evento": "nodo.ancla_fallo", "ruta": "bad"})


class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios
