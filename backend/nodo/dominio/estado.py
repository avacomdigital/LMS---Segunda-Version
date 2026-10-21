"""
El estado del nodo (H del Maestro, P-09): `arrancando → operativo ⇄ restringido`, `en_recuperacion` tras un apagado sucio y `detenido` al parar. El Maestro no define cuándo se
restringe: aquí se propone (Q-N1) con los umbrales como DATO y con histéresis (se sale solo cuando la condición se despeja con holgura). El modo restringido NUNCA cierra una
clase: sólo responde 503 en rutas que no son núcleo (R-07), y eso lo aplica la Fase 5.

Puro: recibe una lectura de la salud y devuelve el estado y sus motivos. Quién mide el disco o el WAL es cosa de la infraestructura.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import catalogos as cat


@dataclass(frozen=True)
class Umbrales:
    disco_min_bytes: int = cat.DISCO_MIN_BYTES
    disco_min_pct: float = cat.DISCO_MIN_PCT
    wal_max_bytes: int = cat.WAL_MAX_BYTES
    retroceso_restringe_ms: int = cat.RETROCESO_RESTRINGE_MS
    histeresis: float = cat.HISTERESIS


@dataclass(frozen=True)
class LecturaDeSalud:
    transaccion_inmediata: bool = True
    base_integra: bool = True
    disco_libre_bytes: int | None = None
    disco_total_bytes: int | None = None
    wal_bytes: int = 0
    consumidores_nucleo_suspendidos: tuple[str, ...] = ()
    retroceso_ms: int = 0
    arrancando: bool = False
    recuperando: bool = False
    detenido: bool = False


@dataclass(frozen=True)
class EstadoDelNodo:
    estado: str
    motivos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def restringido(self) -> bool:
        return self.estado == cat.RESTRINGIDO


def _disco_escaso(lectura: LecturaDeSalud, u: Umbrales, saliendo: bool) -> bool:
    if lectura.disco_libre_bytes is None:
        return False
    factor = u.histeresis if saliendo else 1.0
    if lectura.disco_libre_bytes < u.disco_min_bytes * factor:
        return True
    if lectura.disco_total_bytes:
        return 100.0 * lectura.disco_libre_bytes / lectura.disco_total_bytes < u.disco_min_pct * factor
    return False


def motivos_de_restriccion(lectura: LecturaDeSalud, umbrales: Umbrales = Umbrales(), *, estaba_restringido: bool = False) -> tuple[str, ...]:
    """Los motivos vigentes. Con `estaba_restringido`, las condiciones con histéresis sólo se dan por despejadas cuando mejoran un `histeresis` sobre el umbral de entrada."""
    motivos: list[str] = []
    if not lectura.transaccion_inmediata:
        motivos.append(cat.M_TRANSACCION_NO_INMEDIATA)
    if not lectura.base_integra:
        motivos.append(cat.M_BASE_DANADA)
    if _disco_escaso(lectura, umbrales, saliendo=estaba_restringido):
        motivos.append(cat.M_DISCO_ESCASO)
    wal_umbral = umbrales.wal_max_bytes / (umbrales.histeresis if estaba_restringido else 1.0)
    if lectura.wal_bytes > wal_umbral:
        motivos.append(cat.M_WAL_ENORME)
    if lectura.consumidores_nucleo_suspendidos:
        motivos.append(cat.M_CONSUMIDOR_NUCLEO_SUSPENDIDO)
    if lectura.retroceso_ms > umbrales.retroceso_restringe_ms:
        motivos.append(cat.M_RELOJ_RETROCEDIDO)
    return tuple(motivos)


def evaluar(lectura: LecturaDeSalud, umbrales: Umbrales = Umbrales(), *, estado_previo: str = cat.OPERATIVO) -> EstadoDelNodo:
    """El estado que toca ahora. El orden manda: detenido > arrancando > en recuperación > restringido > operativo."""
    if lectura.detenido:
        return EstadoDelNodo(cat.DETENIDO)
    if lectura.arrancando:
        return EstadoDelNodo(cat.ARRANCANDO)
    if lectura.recuperando:
        return EstadoDelNodo(cat.EN_RECUPERACION)
    motivos = motivos_de_restriccion(lectura, umbrales, estaba_restringido=(estado_previo == cat.RESTRINGIDO))
    if motivos:
        return EstadoDelNodo(cat.RESTRINGIDO, motivos)
    return EstadoDelNodo(cat.OPERATIVO)


def es_ruta_nucleo(ruta: str, prefijos: tuple[str, ...] = cat.PREFIJOS_NUCLEO) -> bool:
    """R-01: las rutas que el modo restringido jamás rechaza. Se comparan por prefijo sobre la ruta ya normalizada (sin el pase de medios)."""
    ruta = str(ruta or "")
    return any(ruta.startswith(p) for p in prefijos)


def estado_del_consumidor(marca: int, ultima_secuencia: int, *, reconstruyendose: bool = False, limite_rezago: int = cat.REZAGO_LIMITE) -> tuple[str, int]:
    """`(estado, rezago)` de un consumidor sobre una fuente (P-06): al día, rezagado o suspendido (rezago por encima del límite); reconstruyéndose si lo pidió."""
    rezago = max(0, int(ultima_secuencia) - int(marca))
    if reconstruyendose:
        return cat.C_RECONSTRUYENDOSE, rezago
    if rezago > int(limite_rezago):
        return cat.C_SUSPENDIDO, rezago
    return (cat.C_REZAGADO if rezago > 0 else cat.C_AL_DIA), rezago


def peor(estados: list[str]) -> str:
    orden = {cat.C_AL_DIA: 0, cat.C_REZAGADO: 1, cat.C_RECONSTRUYENDOSE: 2, cat.C_SUSPENDIDO: 3}
    return max(estados, key=lambda e: orden.get(e, 0)) if estados else cat.C_AL_DIA
