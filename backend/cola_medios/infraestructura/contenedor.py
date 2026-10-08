"""
Composition root de la cola de medios: el único sitio que sabe qué adaptador va con qué puerto y que construye UN servidor por proceso (el nodo es un
proceso). Los límites salen de `settings` (variables `AVACOM_COLA_*`).
"""
from __future__ import annotations

import atexit
import dataclasses
import logging
import shutil
import tempfile
import threading
import time

from django.conf import settings

from ..aplicacion.config import GIB, MIB, Config
from ..aplicacion.almacen import Almacen
from ..aplicacion.servidor import Servidor
from .difusion import DifusionAula
from .memoria import MemoriaLocal
from .origen import OrigenDeAula
from .registro import RegistroOrm

log = logging.getLogger("avacom.cola_medios")


class RelojNodo:
    def ahora_ms(self) -> int:
        return int(time.time() * 1000)


def configuracion() -> Config:
    g = lambda nombre, defecto: getattr(settings, nombre, defecto)   # noqa: E731
    return Config(
        activa=bool(g("AVACOM_COLA_ACTIVA", True)),
        carpeta=str(g("AVACOM_COLA_DIR", "") or ""),
        max_bytes=int(g("AVACOM_COLA_MAX_MB", 4096)) * MIB,
        libre_min_bytes=int(g("AVACOM_COLA_LIBRE_MIN_MB", 1024)) * MIB,
        hilos=int(g("AVACOM_COLA_DESCARGAS", 3)),
        transferencias=int(g("AVACOM_COLA_TRANSFERENCIAS", 24)),
        ancho_entrada_bps=int(g("AVACOM_COLA_ANCHO_ENTRADA_KBPS", 0)) * 1024,
        ancho_salida_bps=int(g("AVACOM_COLA_ANCHO_SALIDA_KBPS", 0)) * 1024,
        revalidar_seg=int(g("AVACOM_COLA_REVALIDAR_SEG", 60)),
        espera_inicio_seg=float(g("AVACOM_COLA_ESPERA_INICIO_SEG", 6)),
        espera_paquete_seg=float(g("AVACOM_COLA_ESPERA_PAQUETE_SEG", 120)),
        espera_cupo_seg=float(g("AVACOM_COLA_ESPERA_CUPO_SEG", 20)),
        estancado_seg=float(g("AVACOM_COLA_ESTANCADO_SEG", 30)),
        adelanto_max_bytes=int(g("AVACOM_COLA_ADELANTO_MAX_MB", 32)) * MIB,
        reintentos=int(g("AVACOM_COLA_REINTENTOS", 3)),
        servir_sin_biblioteca=bool(g("AVACOM_COLA_SERVIR_SIN_BIBLIOTECA", False)),
    )


_servidor: Servidor | None = None
_candado = threading.Lock()


def servidor() -> Servidor:
    global _servidor
    if _servidor is None:
        with _candado:
            if _servidor is None:
                _servidor = _construir(configuracion())
    return _servidor


_carpeta_temporal: str | None = None


def _carpeta_de_pruebas() -> str:
    """Sin carpeta configurada (pruebas, comandos) la caché vive en una carpeta temporal, una por proceso, que se borra al salir."""
    global _carpeta_temporal
    if _carpeta_temporal is None:
        _carpeta_temporal = tempfile.mkdtemp(prefix="avacom-cola-")
        atexit.register(shutil.rmtree, _carpeta_temporal, True)
    return _carpeta_temporal


def _construir(config: Config) -> Servidor:
    almacen = Almacen(config.carpeta or _carpeta_de_pruebas())
    motivo = ""
    try:
        almacen.preparar()
    except OSError as error:
        # Sin carpeta donde guardar no hay caché, pero el nodo tiene que arrancar y servir los medios como siempre: la cola se apaga sola y lo dice (estado y log).
        motivo = f"No se pudo preparar la carpeta de la caché de medios ({almacen.carpeta}): {error}"
        log.error(motivo, extra={"evento": "medios.cola.apagada_sin_carpeta"})
        config = dataclasses.replace(config, activa=False)
    registro = RegistroOrm()
    return Servidor(config=config, registro=registro, almacen=almacen, origen=OrigenDeAula(), memoria=MemoriaLocal(), difusion=DifusionAula(registro),
                    reloj=RelojNodo(), motivo_apagada=motivo)


def reiniciar(config: Config | None = None) -> Servidor:
    """Descarta el servidor actual y construye otro (con `config` o con la de `settings`). Lo usan las pruebas, entre un caso y el siguiente."""
    global _servidor
    with _candado:
        anterior = _servidor
        if anterior is not None:
            anterior.planificador.cerrar()
            try:
                MemoriaLocal().vaciar()
            except Exception:   # noqa: BLE001
                pass
        _servidor = _construir(config or configuracion())
        if not (config or configuracion()).carpeta:
            _servidor.almacen.vaciar()           # la carpeta temporal se reutiliza entre casos: cada uno empieza con la caché vacía
        return _servidor
