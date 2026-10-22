"""
Puertos (interfaces) de MOD-017 · Update Manager (P-14). Todo lo que el módulo necesita del mundo entra por aquí y sólo por aquí: el reloj del nodo, las llaves de publicación,
el registro de módulos y lo instalado, las fuentes de paquetes (unidades y la carpeta de entrada), la carpeta de actualizaciones (paquetes, staging, orden y resultado), el aula
(¿hay clase?), la licencia, el respaldo, la cola de salida, la auditoría y los permisos. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso ni el
dominio. Este archivo no importa Django.

R-03 · actualizacion es dueña de `m17_*` y NO lee ni escribe ninguna otra tabla: lo ajeno llega como valores por estos puertos.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..dominio.registro import Instalacion


@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34, prototipo) lo declara el cliente; el vigilante y el arranque son `sistema`."""

    id: str
    rotulo: str = ""
    nivel: int = 2
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None
    rol: str = ""


@dataclass(frozen=True)
class Candidato:
    """Un `.avupd` encontrado en una fuente, todavía sin importar. `id` es opaco (P-11): la API nunca recibe una ruta; la resuelve el nodo."""

    id: str
    nombre: str              # el nombre del archivo, sin su carpeta
    origen: str              # unidad | entrada | internet
    bytes: int
    modificado_en: int       # ms (reloj del sistema de archivos: sólo informativo)
    fuente: str = ""         # rótulo de la fuente (la letra de la unidad, «Carpeta de entrada»)


# ------------------------------------------------------------------------------------------------------------------- lo que el nodo sabe
class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La autoridad es el reloj del NODO (R-09, INV-017): el de MOD-015, con su marca alta."""


class Claves(Protocol):
    def publicas(self) -> dict[str, bytes]:
        """`{kid: llave pública de 32 bytes}` de PUBLICACIÓN que este nodo acepta. En producción, sólo las de producción; en desarrollo y pruebas, también la de desarrollo."""


class RegistroModulos(Protocol):
    def instalacion(self) -> Instalacion:
        """Lo instalado: la versión del producto, el contrato de la biblioteca y cada módulo con su versión de módulo, de contrato, su serie y su versión de DATOS viva."""


class Fuentes(Protocol):
    """Dónde pueden aparecer paquetes (P-11): las unidades extraíbles y la carpeta `Actualizaciones\\entrada\\`. Nunca una ruta libre."""

    def candidatos(self) -> list[Candidato]: ...
    def leer(self, candidato_id: str) -> tuple[Candidato, bytes] | None:
        """Los bytes del candidato (acotados por el tope del paquete), o None si ya no está."""


class Almacen(Protocol):
    """La carpeta de actualizaciones (`%ProgramData%\\AVACOM\\OPS Master\\Actualizaciones\\`): paquetes importados, staging, la orden y el resultado. Escrituras atómicas."""

    def guardar_paquete(self, paquete_id: str, datos: bytes) -> str:
        """Copia el `.avupd` verificado a `paquetes\\<id>.avupd`; devuelve la ruta relativa."""
    def leer_paquete(self, paquete_id: str) -> bytes | None: ...
    def extraer(self, paquete_id: str, archivos: Iterable[tuple[str, bytes]]) -> str:
        """Deja los archivos en `staging\\<id>\\`, de cero (se borra lo que hubiera); devuelve la ruta relativa."""
    def borrar_staging(self, paquete_id: str) -> None: ...
    def escribir_orden(self, orden: dict) -> None:
        """`orden.json`, de forma atómica. Si ya hay una orden, falla (`ActualizacionEnCurso`)."""
    def leer_orden(self) -> dict | None: ...
    def leer_resultado(self) -> dict | None: ...
    def archivar_resultado(self, orden_id: str) -> None:
        """Mueve `resultado.json` a `resultados\\<orden_id>.json` (y retira la orden si sigue ahí): el mismo resultado no se registra dos veces."""
    def hay_orden(self) -> bool: ...
    def espacio_libre(self) -> int | None:
        """Bytes libres en la unidad de los datos del nodo, o None si no se pudo medir."""
    def bytes_de_la_base(self) -> int:
        """Lo que mide la base de datos (+wal, +shm): lo que la copia previa va a ocupar."""


class Aula(Protocol):
    def sesiones_activas(self) -> int:
        """Clases abiertas o suspendidas (FUN-183). Lo responde `classroom_engine.servicios`."""
    def proxima_clase_en(self) -> int | None:
        """El instante de la próxima clase programada, si el nodo lo conoce (Q-U9). Hoy: None."""


class Licencia(Protocol):
    def admite(self, modulos: Iterable[str]) -> tuple[bool, str]:
        """¿La licencia admite lo que la actualización habilita? (MOD-018). Provisional: siempre `(True, "")`."""


class Respaldo(Protocol):
    def disponible(self) -> bool:
        """¿Se puede tomar el respaldo previo? (MOD-016; provisional: lo toma el Host con `Datos.Respaldar`, así que sí)."""
    def descripcion(self) -> str: ...


class Eventos(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo: str, carga: dict) -> None:
        """Escribe el evento en la MISMA transacción que el hecho (cola única de MOD-015)."""


class Auditoria(Protocol):
    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None: ...
    def puede(self, actor: Actor, permiso: str) -> bool: ...


# ------------------------------------------------------------------------------------------------------------------- repositorios m17_*
class RepositorioPaquetes(Protocol):
    def insertar(self, datos: dict) -> dict: ...
    def obtener(self, paquete_id: str) -> dict | None: ...
    def todos(self, limite: int = 200) -> list[dict]: ...
    def existe_sha(self, sha256: str) -> str | None:
        """El `paquete_id` ya importado con esa huella, si lo hay (importar dos veces el mismo archivo no crea dos paquetes)."""


class RepositorioHistorial(Protocol):
    def insertar(self, datos: dict) -> dict: ...
    def de_paquete(self, paquete_id: str) -> list[dict]:
        """Las filas de ese paquete en orden de inserción."""
    def de_todos(self) -> dict[str, list[dict]]:
        """{paquete_id: filas en orden} de todos los paquetes (sin los `rechazado`)."""
    def ultimas(self, limite: int = 100, tipos: tuple[str, ...] | None = None) -> list[dict]: ...
    def rechazado_reciente(self, sha256: str, desde: int) -> bool: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso (`uow()`); `uow(lectura=True)` abre una consulta SIN transacción (SQLite con `IMMEDIATE`: un `atomic` toma el bloqueo de toda la base)."""

    paquetes: RepositorioPaquetes
    historial: RepositorioHistorial
    eventos: Eventos
    auditoria: Auditoria

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...


class Vivo(Protocol):
    """La memoria del proceso: si hay una orden aceptada (para el 503 del inicio de clases sin tocar la base) y los candidatos ya anunciados."""

    def en_curso(self) -> bool | None:
        """True/False si se sabe; None si todavía no se calculó desde el historial."""
    def marcar_en_curso(self, valor: bool) -> None: ...
    def anunciado(self, candidato_id: str) -> bool: ...
    def anunciar(self, candidato_id: str) -> None: ...


@dataclass
class Fallo:
    """Lo que un adaptador no pudo hacer, dicho en una frase: nunca un 500 (R-04)."""

    codigo: str
    detalle: str = ""
    extra: dict = field(default_factory=dict)
