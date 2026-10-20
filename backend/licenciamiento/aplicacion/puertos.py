"""
Puertos (interfaces) de MOD-018 · Licensing. Todo lo que el módulo necesita del mundo entra por aquí y sólo por aquí: el reloj del nodo, la huella de este equipo, lo propio del nodo
(secreto de instalación y llave), las anclas del reloj, la carpeta de estado, las llaves públicas, los conteos de equipos y usuarios (que dan sus dueños por su `servicios.py`), la
auditoría, la cola de salida y los permisos. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso ni el dominio. Este archivo no importa Django.

R-08 · licenciamiento es dueño de las tablas `m18_*` y NO lee ni escribe `m01_*` ni `m09_*`: lo ajeno llega como números por `Conteos`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34, prototipo) lo declara el cliente; el programador y el arranque son `sistema`."""

    id: str
    rotulo: str = ""
    nivel: int = 2
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None
    rol: str = ""


# ------------------------------------------------------------------------------------------------------------------- lo que el nodo sabe
class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La autoridad es el reloj del NODO (INV-017, BR-062); nada usa el reloj de un dispositivo."""
    def monotono_ms(self) -> int:
        """Un reloj que no se puede cambiar desde el reloj del sistema: sirve para distinguir un salto del reloj de pared de un paso real del tiempo."""


class FuenteDeHuella(Protocol):
    def crudos(self) -> dict[int, str]:
        """Los factores de hardware de ESTE equipo con sus valores crudos (sin filtrar la basura). Sin sistema operativo compatible: vacío (se usará la huella de instalación)."""


class Nodo(Protocol):
    """Lo que es propio de esta instalación y no sale de ella."""

    def secreto_de_instalacion(self) -> bytes:
        """32 bytes al azar del primer arranque, protegidos con DPAPI de máquina (en Windows): la huella de instalación cuando el hardware no alcanza."""
    def clave_privada(self) -> bytes:
        """La llave Ed25519 del nodo (firma solicitudes y liberaciones). Nunca sale del equipo."""
    def clave_publica(self) -> bytes: ...
    def tomar_novedades(self) -> list[str]:
        """Los archivos propios del nodo que NO se pudieron abrir y se apartaron para crear otros (una sola entrega): la evaluación los asienta como integridad alterada."""
    def devolver_novedades(self, nombres: list[str]) -> None:
        """Lo entregado que no llegó a asentarse vuelve a la cola para el siguiente ciclo."""


@dataclass(frozen=True)
class LecturaDeAnclas:
    marcas: dict[str, int] = field(default_factory=dict)        # {ancla: marca alta en ms} de cada ancla externa que se pudo leer y verificar
    instalada_en: int | None = None                             # cuándo empezó la ventana de evaluación, guardado fuera de la base (restaurar un respaldo no la reinicia)
    alteradas: tuple[str, ...] = ()                             # anclas que no pasaron su verificación: no cuentan y se avisan


class Anclas(Protocol):
    """Marcas del reloj (y el inicio de la evaluación) guardadas FUERA de la base de datos: una copia de seguridad restaurada no las rebobina."""

    def leer(self) -> LecturaDeAnclas: ...
    def escribir(self, marca_ms: int, instalada_en: int | None = None) -> None: ...


class Almacen(Protocol):
    """La carpeta de estado (`%ProgramData%\\AVACOM\\OPS Master\\Config\\licencia\\`): archivos con nombre, escritos de forma atómica."""

    def leer(self, nombre: str) -> bytes | None: ...
    def existe(self, nombre: str) -> bool:
        """¿Está el archivo, aunque no se haya podido leer ahora? (Distingue «no está» de «está y no pude leerlo».)"""
    def escribir(self, nombre: str, datos: bytes) -> None: ...
    def borrar(self, nombre: str) -> None: ...
    def poner_en_cuarentena(self, nombre: str) -> str | None:
        """Aparta el archivo (renombrar, nunca borrar) y devuelve el nombre nuevo; `None` si no se pudo."""


class Claves(Protocol):
    def publicas(self) -> dict[str, bytes]:
        """`{kid: llave pública de 32 bytes}` que este nodo acepta. En producción: las de producción (nunca la de desarrollo); en desarrollo y pruebas, también la de desarrollo."""


class Conteos(Protocol):
    """Lo que cuentan los módulos dueños (por su `servicios.py`). None = no se pudo contar (nodo sin instalar, base ocupada): el cupo no se aplica y se dice."""

    def equipos(self) -> int | None: ...
    def usuarios(self) -> int | None: ...


class Auditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. Nunca lleva el contenido de una licencia ni huellas crudas: ids, serie, resultado y hash."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...
    def ultima_marca(self) -> int | None:
        """La fecha (reloj del nodo) del último asiento de la bitácora encadenada: una de las anclas del reloj (P-06)."""


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict, clave: str | None = None) -> bool:
        """Escribe el evento en la misma transacción que el hecho. Con `clave` es IDEMPOTENTE: si ya existe un evento con esa clave no escribe nada y devuelve False."""
    def existentes(self, claves: list[str]) -> set[str]:
        """Cuáles de estas claves ya tienen su evento (una lectura, sin transacción): así un ciclo sin novedades no abre una transacción de escritura."""


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso`."""
    def puede(self, actor: Actor, permiso: str) -> bool: ...


# ------------------------------------------------------------------------------------------------------------------- repositorios m18_*
class RepositorioInstalacion(Protocol):
    def obtener(self) -> dict | None: ...
    def crear(self, ahora: int, version: str) -> dict: ...


class RepositorioHistorial(Protocol):
    """El historial de SÓLO INSERCIÓN de licencias (no hay «estado actual» que pueda divergir): la vigente es la última fila efectiva."""

    def vigente(self) -> dict | None:
        """La última fila efectiva (activada, renovada o reactivada); None si no hay ninguna o la última fue una liberación."""
    def ultima(self) -> dict | None: ...
    def insertar(self, datos: dict) -> dict: ...
    def todas(self, limite: int = 50) -> list[dict]: ...
    def liberadas(self) -> set[tuple[str, int]]:
        """`{(licencia_id, serie)}` de las licencias cuya fila MÁS RECIENTE es una liberación (volver a activar una liberada la saca de aquí)."""


class RepositorioObservaciones(Protocol):
    """Hechos observados que explican el estado (huella distinta, reloj raro, integridad…). De sólo inserción."""

    def registrar(self, tipo: str, ahora: int, licencia_id: str = "", serie: int = 0, detalle: dict | None = None) -> dict: ...
    def ultima(self, tipo: str, licencia_id: str | None = None, serie: int | None = None) -> dict | None: ...


class RepositorioMarca(Protocol):
    def valor(self) -> int: ...
    def subir(self, valor: int, ahora: int) -> None:
        """Sólo sube: un trigger de la base lo garantiza."""


class RepositorioConsumo(Protocol):
    def guardar(self, ahora: int, equipos: int, usuarios: int) -> None: ...
    def leer(self) -> dict | None: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso (`uow()`); `uow(lectura=True)` abre una consulta SIN transacción (el nodo corre SQLite con `IMMEDIATE`: un `atomic` toma el bloqueo de toda la base)."""

    instalacion: RepositorioInstalacion
    historial: RepositorioHistorial
    observaciones: RepositorioObservaciones
    marca: RepositorioMarca
    consumo: RepositorioConsumo
    outbox: Outbox
    auditoria: Auditoria

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...


# ------------------------------------------------------------------------------------------------------------------- lo que ve el resto del módulo
@dataclass(frozen=True)
class Instantanea:
    """El estado de la licencia en un instante, YA calculado: es lo único que lee el camino caliente de cada petición (cero consultas SQL)."""

    estado: Any                               # dominio.estado.Estado
    avisos: tuple[dict, ...] = field(default_factory=tuple)
    consumo: Any = None                       # dominio.cupo.Consumo | None
    licencia: dict | None = None              # el resumen que se puede mostrar (sin la firma ni la huella)
    huella: dict | None = None                # nivel y coincidencia, sin identificadores
    modo: str = "firmada"
    entorno: str = "produccion"
    calculada_en: int = 0
    limites_de_concurrencia: tuple[int, int] | None = None


class Vivo(Protocol):
    """La memoria del proceso: la última instantánea buena, el último reloj observado y los bloqueos ya asentados esta hora. Una instantánea mala nunca la reemplaza."""

    def leer(self) -> Instantanea | None: ...
    def publicar(self, instantanea: Instantanea) -> None: ...
    def reloj_previo(self) -> tuple[int, int, int] | None:
        """`(reloj de pared, monótono, instante confiable)` de la lectura anterior de este proceso, o None si es el primer ciclo."""
    def recordar_reloj(self, reloj_ms: int, monotono_ms: int, confiable_ms: int | None = None) -> None: ...
    def registrar_bloqueo(self, actor: str, clave: str, ahora_ms: int) -> None:
        """Cuenta un bloqueo de licencia: un módulo apagado (`clave` = la capacidad) o un cupo agotado (`clave` = `cupo:equipos`). Sólo memoria: la bitácora lo asienta el
        programador, UNA vez por actor, clave y hora (R-07: ninguna petición escribe en la base por esto)."""
    def tomar_bloqueos(self) -> list[dict]:
        """Los bloqueos pendientes de asentar `[{hora, actor, clave, cantidad}]`. Una vez entregados, el mismo (hora, actor, clave) no vuelve a entregarse."""
    def arranque_id(self) -> str:
        """Identifica ESTE arranque del proceso (para `licencia.validada` una sola vez por arranque)."""
