"""
Puertos (interfaces) de MOD-015. Todo lo que el nodo necesita de fuera entra por aquí: la base (sus propias tablas `m15_*` y nada más, R-09), el reloj del sistema, el contexto de la
petición (actor, aparato y correlación, de MOD-019), las anclas fuera de la base, la auditoría, la autorización (MOD-001), el respaldo (MOD-016, que no existe: su puerto devuelve
«no cubre nada»), la sincronización remota (V1) y la salud del equipo. Los adaptadores viven en `infraestructura/`. Este archivo no importa Django.

La única lectura de tablas AJENAS que hace la cola es por `LectorLegado`: la función `eventos_legados` que cada módulo cortado registra (su propio `servicios.py` lee su tabla antigua).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ..dominio.anclas import Ancla
from ..dominio.corte import Corte
from ..dominio.estado import LecturaDeSalud
from ..dominio.reintentos import EstadoDeReintento
from ..dominio.sobre import Sobre


@dataclass(frozen=True)
class Actor:
    """Quien actúa sobre la cola. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34, prototipo) lo declara el cliente; el propio nodo es `sistema`."""

    id: str
    rotulo: str = ""
    nivel: int = 2
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None
    rol: str = ""


# ------------------------------------------------------------------------------------------------ lo que entra de fuera

class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """El reloj del SISTEMA del nodo (lo que las pruebas mueven). La marca alta se le pone encima en `servicios.ahora_ms`."""


class Contexto(Protocol):
    def actual(self) -> tuple[str | None, str | None, str | None]:
        """`(actor, dispositivo_id, correlacion_id)` de la operación en curso (MOD-019, `audit/contexto.py`); None donde no haya."""


class Anclas(Protocol):
    def leer(self) -> Ancla | None: ...
    def escribir(self, ancla: Ancla) -> None: ...


class Auditoria(Protocol):
    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None: ...
    def puede(self, actor: Actor, permiso: str) -> bool: ...


class Respaldo(Protocol):
    """MOD-016 · Backup. Hasta que exista, `cubre` es siempre False: nada se purga (P-08)."""

    def cubre(self, secuencia: int) -> bool: ...
    def verificado_hasta(self) -> int: ...


class Sincronizacion(Protocol):
    """CAP-095 (V1): el drenaje a servicios remotos. Hasta que exista, no está habilitada."""

    def habilitada(self) -> bool: ...
    def reconocida_hasta(self) -> int: ...


class Salud(Protocol):
    def leer(self) -> LecturaDeSalud: ...


class LectorLegado(Protocol):
    def __call__(self, desde: int, limite: int, tipos: tuple[str, ...] | None, hasta: int) -> tuple[list[dict], int]:
        """Los eventos de la tabla ANTIGUA del módulo con `desde < id ≤ hasta` (y de esos `tipos`, o todos), en orden, y hasta dónde se miró."""


Aplicador = Callable[[dict], None]


# ------------------------------------------------------------------------------------------------ repositorios m15_*

class RepositorioEventos(Protocol):
    def insertar(self, sobre: Sobre) -> int:
        """UN INSERT dentro de la transacción del hecho. Devuelve la secuencia."""
    def leer(self, modulo: str, desde: int, limite: int, tipos: tuple[str, ...] | None) -> tuple[list[dict], int]: ...
    def por_secuencia(self, secuencia: int) -> dict | None: ...
    def ultima_secuencia(self, modulo: str | None = None) -> int: ...
    def contador(self) -> int:
        """El contador del AUTOINCREMENT (`sqlite_sequence`): ≥ la última secuencia emitida, también tras borrar."""
    def asegurar_contador(self, minimo: int) -> int:
        """Sube el contador a `minimo` si está por debajo (nunca lo baja). Devuelve el contador que queda."""
    def contar(self, modulo: str | None = None) -> int: ...
    def primeros(self, limite: int) -> list[dict]:
        """Los más antiguos (para la purga): `{secuencia, creado_en, clase, tipo}`."""
    def borrar(self, secuencias: list[int]) -> int:
        """El ÚNICO borrado de la cola (P-08): sólo lo llama la purga."""


class RepositorioCortes(Protocol):
    def get(self, modulo: str) -> Corte | None: ...
    def crear(self, corte: Corte, version_contrato: int) -> None: ...
    def todos(self) -> list[Corte]: ...


class RepositorioModulos(Protocol):
    def registrar(self, nombre: str, version_modulo: str, version_datos: str, version_contrato: int, produce: list[str], consume: list[str], compatible: bool, detalle: dict, ahora: int) -> dict: ...
    def get(self, nombre: str) -> dict | None: ...
    def todos(self) -> list[dict]: ...


class RepositorioConsumidores(Protocol):
    def registrar(self, nombre: str, modulo: str, fuentes: list[str], tipos: list[str], version_contrato: int, limite_rezago: int | None, ahora: int) -> dict: ...
    def get(self, nombre: str) -> dict | None: ...
    def todos(self, activos: bool = True) -> list[dict]: ...
    def desregistrar(self, nombre: str, ahora: int) -> bool: ...
    def actualizar_estado(self, nombre: str, estado: str, ahora: int) -> bool:
        """Devuelve True si el estado cambió."""


class RepositorioMarcas(Protocol):
    def estado(self, consumidor: str, fuente: str) -> tuple[int, EstadoDeReintento, bool]:
        """`(marca, reintento, reconstruyendose)`; sin fila, `(0, SIN_REINTENTO, False)` (BR-007)."""
    def guardar(self, consumidor: str, fuente: str, marca: int, reintento: EstadoDeReintento, ahora: int, reconstruyendose: bool | None = None) -> None: ...
    def de_consumidor(self, consumidor: str) -> list[dict]: ...
    def todas(self) -> list[dict]: ...
    def reiniciar(self, consumidor: str, fuente: str | None, ahora: int) -> int:
        """Pone en cero las marcas (de una fuente o de todas) y las marca `reconstruyendose`. Devuelve cuántas."""


class RepositorioProblemas(Protocol):
    def apartar(self, consumidor: str, fuente: str, evento: dict, intentos: int, error: str, ahora: int) -> dict: ...
    def get(self, problema_id: int) -> dict | None: ...
    def listar(self, consumidor: str | None = None, estado: str | None = None, limite: int = 100) -> list[dict]: ...
    def contar(self, consumidor: str | None = None, estado: str | None = None) -> int: ...
    def resolver(self, problema_id: int, estado: str, ahora: int, por: str, error: str = "") -> dict | None: ...
    def fallo_de_reproceso(self, problema_id: int, error: str, ahora: int) -> dict | None: ...


class RepositorioArranques(Protocol):
    def abrir(self, ahora: int, version: str, pid: int, secuencia_al_iniciar: int, ancla_secuencia: int, restauracion: bool, contador: int, detalle: dict) -> dict: ...
    def cerrar(self, arranque_id: int, ahora: int) -> None: ...
    def ultimo(self) -> dict | None: ...
    def anteriores_sin_cerrar(self, arranque_id: int) -> list[dict]: ...


class RepositorioMarcaAlta(Protocol):
    def valor(self) -> int: ...
    def subir(self, valor: int, ahora: int) -> None:
        """Nunca baja (trigger)."""


class UnidadDeTrabajo(Protocol):
    eventos: RepositorioEventos
    cortes: RepositorioCortes
    modulos: RepositorioModulos
    consumidores: RepositorioConsumidores
    marcas: RepositorioMarcas
    problemas: RepositorioProblemas
    arranques: RepositorioArranques
    marca_alta: RepositorioMarcaAlta
    auditoria: Auditoria

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
    def en_transaccion(self) -> bool:
        """¿Hay una transacción abierta en la conexión? (`publicar` exige que sí: BR-001)."""
    def aislado(self):
        """Un savepoint: si lo de dentro falla, se deshace sólo eso."""
