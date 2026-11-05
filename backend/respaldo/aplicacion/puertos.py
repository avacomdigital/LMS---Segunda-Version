"""
Puertos (interfaces) de MOD-016 · Backup & Recovery. Todo lo que el módulo necesita del mundo entra por aquí y sólo por aquí: el reloj del nodo, las claves del equipo, lo que hay que
respaldar (la base y las carpetas de la institución), la carpeta de respaldos y las unidades extraíbles, el aplicador de la restauración, el aula (¿hay clase?), lo que hay que rehacer
tras restaurar, la cola de salida, la auditoría y los permisos. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso ni el dominio. Este archivo no
importa Django.

R-03 · respaldo es dueño de `m16_*` y NO lee ni escribe ninguna otra tabla: lo ajeno llega como valores por estos puertos.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Protocol


@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; el vigilante y el arranque son `sistema`."""

    id: str
    rotulo: str = ""
    nivel: int = 2
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None
    rol: str = ""


@dataclass(frozen=True)
class ArchivoDeOrigen:
    """Un archivo de la institución listo para entrar a un respaldo."""

    nombre: str                    # `<carpeta>/<ruta relativa>`
    clase: str                     # primario | reinstalable
    bytes: int
    modificado_en: int             # ms
    abrir: Callable[[], BinaryIO]


@dataclass(frozen=True)
class CarpetaDeOrigen:
    nombre: str
    clase: str
    ruta: Path


@dataclass(frozen=True)
class Unidad:
    id: str                        # opaco: la API nunca recibe una letra de unidad ni una ruta
    rotulo: str
    libre_bytes: int | None


@dataclass(frozen=True)
class CandidatoDeRespaldo:
    """Un `.avbak` encontrado en una unidad o en la carpeta de entrada, todavía sin catalogar. `id` es opaco."""

    id: str
    nombre: str
    bytes: int
    fuente: str
    modificado_en: int = 0


# ------------------------------------------------------------------------------------------------------------------- lo que el nodo sabe
class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La autoridad es el reloj del NODO (R-09, INV-017): el de MOD-015, con su marca alta."""
    def desfase_min(self) -> int:
        """Minutos que la hora local del equipo se adelanta a UTC (para el calendario de respaldos y para escribir las fechas de las constancias)."""


class Nodo(Protocol):
    def ultima_secuencia(self) -> int:
        """La última secuencia de la cola única (MOD-015): lo que se pierde al restaurar se mide contra ella."""
    def version_producto(self) -> str: ...
    def institucion(self) -> str:
        """El nombre de la organización para las constancias (vacío si el nodo todavía no está instalado)."""


class Aula(Protocol):
    def sesiones_activas(self) -> int:
        """Clases abiertas o suspendidas. Lo responde `classroom_engine.servicios`; ante un fallo se asume que SÍ hay clase."""


class Clavero(Protocol):
    """La identidad y las claves del equipo, FUERA de la base (una restauración no las rebobina). La clave del nodo no sale del equipo: ligada a él con DPAPI en Windows."""

    def nodo_id(self) -> str: ...
    def clave_del_nodo(self) -> bytes: ...
    def custodia(self) -> dict | None:
        """`{emitida_en, sal, clave}` con la clave de custodia derivada, ya desenvuelta; None si la institución todavía no tiene código."""
    def guardar_custodia(self, emitida_en: int, sal: bytes, clave: bytes) -> None: ...


class Soporte(Protocol):
    def llaves_publicas(self) -> dict[str, bytes]:
        """`{kid: llave pública de 32 bytes}` con las que AVACOM firma los pases de soporte. En producción, sólo las de producción."""


class Origen(Protocol):
    """Lo que hay que respaldar: la base de datos del aula y las carpetas de archivos de la institución."""

    def instantanea_de_la_base(self, destino: Path) -> int:
        """Escribe en `destino` una copia CONSISTENTE de la base (API de respaldo de SQLite: no detiene a nadie) y devuelve sus bytes."""
    def bytes_de_la_base(self) -> int: ...
    def carpetas(self, incluir_reinstalable: bool) -> list[CarpetaDeOrigen]: ...
    def archivos(self, incluir_reinstalable: bool, desde_ms: int | None) -> tuple[list[ArchivoDeOrigen], list[str]]:
        """Los archivos que entran (si `desde_ms`, sólo los modificados desde entonces) y los nombres que se OMITIERON por inseguros (sin revelar su contenido)."""


class Almacen(Protocol):
    """La carpeta de respaldos (`%ProgramData%\\AVACOM\\OPS Master\\Respaldos\\`): los `.avbak`, el trabajo en curso y los informes para el personal administrativo."""

    def abrir_para_escribir(self, respaldo_id: str) -> tuple[BinaryIO, Any]:
        """Un archivo temporal `.avbak.parcial` (nunca se confunde con un respaldo terminado) y su manija."""
    def terminar(self, manija: Any, respaldo_id: str, creado_en: int, tipo: str) -> str:
        """Vacía a disco y renombra a su nombre final de forma atómica; devuelve ese nombre (sin carpeta)."""
    def descartar(self, manija: Any) -> None: ...
    def abrir(self, nombre: str) -> BinaryIO | None: ...
    def tamano(self, nombre: str) -> int | None: ...
    def borrar(self, nombre: str) -> bool: ...
    def listar(self) -> list[str]:
        """Los nombres de los `.avbak` terminados que hay en la carpeta (para catalogar los que la base no conoce)."""
    def carpeta_de_trabajo(self, etiqueta: str) -> Path:
        """Una carpeta de trabajo nueva y vacía (instantánea, restauración en staging)."""
    def limpiar_trabajo(self, ruta: Path) -> None: ...
    def espacio_libre(self) -> int | None: ...
    def guardar_informe(self, nombre: str, texto: str, con_bom: bool = False) -> None:
        """Deja un archivo para el personal administrativo en `Informes\\`. Atómico."""
    def leer_informe(self, nombre: str) -> str | None: ...
    def listar_informes(self) -> list[str]: ...
    def ruta_de(self, nombre: str) -> Path | None:
        """Sólo para los adaptadores (copiar a una unidad). La API jamás la devuelve."""


class Unidades(Protocol):
    """Las unidades extraíbles y la carpeta de entrada: nunca una ruta libre. En desarrollo y pruebas, carpetas que hacen de unidad."""

    def listar(self) -> list[Unidad]: ...
    def copiar(self, unidad_id: str, origen: Path, nombre: str, extras: dict[str, str] | None = None) -> str:
        """Copia el respaldo (y, si se pide, textos sueltos como la constancia) a `AVACOM\\Respaldos\\` de la unidad; verifica el tamaño y devuelve el rótulo de la unidad."""
    def candidatos(self) -> list[CandidatoDeRespaldo]: ...
    def traer(self, candidato_id: str, destino: Path) -> CandidatoDeRespaldo | None:
        """Copia el candidato a `destino` (acotado y atómico) y lo describe, o None si ya no está."""


class Aplicador(Protocol):
    """Aplica una restauración SOBRE el equipo vivo. Es la única pieza que escribe fuera de `m16_*` y fuera de la carpeta de respaldos, y lo hace sólo para devolver lo respaldado."""

    def comprobar_base(self, ruta: Path) -> dict:
        """`{integra, migraciones_desconocidas, tablas}` de una base ya descifrada, sin tocar la viva: `PRAGMA integrity_check`, tablas de AVACOM y migraciones que este código no conoce."""
    def aplicar_base(self, ruta: Path) -> dict:
        """Reemplaza el contenido de la base viva por el de `ruta` con la API de respaldo de SQLite (atómico: o queda la nueva o queda la anterior)."""
    def aplicar_archivos(self, nombre_de_carpeta: str, clase: str, desde: Path) -> int:
        """Devuelve los archivos de `desde` a su carpeta de origen (`os.replace` uno a uno). No borra lo que sobre."""


class TrasRestaurar(Protocol):
    """Lo que otros módulos rehacen después de una restauración (BR-003: cada uno en lo suyo, por su interfaz): arranque del nodo (INV-002), esquema, sesiones, licencia, índices."""

    def ejecutar(self, huella_nueva: bool) -> dict:
        """Devuelve `{nodo, esquema, sesiones, licencia, reconstruidos: [..], fallos: [..]}`. Nunca lanza: un paso que falla se anota y los demás siguen."""


class Modulos(Protocol):
    def declara_restauracion_aislada(self, modulo: str) -> bool: ...


class Eventos(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo: str, carga: dict) -> None:
        """Escribe el evento en la MISMA transacción que el hecho (cola única de MOD-015)."""


class Auditoria(Protocol):
    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class AuditoriaDeRestauracion(Protocol):
    """Lo que la restauración necesita de la bitácora además de asentar: leer lo del módulo antes de reemplazar la base y volver a asentar lo que ésta se lleva."""

    def del_modulo(self) -> list[dict]: ...
    def cola(self) -> dict: ...
    def recuperar(self, previos: list[dict]) -> int: ...


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None: ...
    def puede(self, actor: Actor, permiso: str) -> bool: ...


# ------------------------------------------------------------------------------------------------------------------- repositorios m16_*
class RepositorioRespaldos(Protocol):
    def insertar(self, datos: dict) -> dict: ...
    def obtener(self, respaldo_id: str) -> dict | None: ...
    def todos(self, limite: int = 500) -> list[dict]: ...
    def existe_sha(self, sha256: str) -> str | None: ...


class RepositorioHistorial(Protocol):
    def insertar(self, datos: dict) -> dict: ...
    def de_respaldo(self, respaldo_id: str) -> list[dict]: ...
    def de_todos(self) -> dict[str, list[dict]]: ...
    def ultimas(self, limite: int = 100, tipos: tuple[str, ...] | None = None) -> list[dict]: ...


class RepositorioAjuste(Protocol):
    def obtener(self) -> dict:
        """La programación vigente; si todavía no hay fila, la crea con los valores por defecto."""
    def guardar(self, datos: dict, en: int, por: str) -> dict: ...


class RepositorioPases(Protocol):
    def usar(self, pase_id: str, en: int, permiso: str, tecnico: str, kid: str, respaldo_id: str = "") -> bool:
        """Registra el uso; False si ese pase ya se usó (un pase vale una vez)."""
    def todos(self) -> list[dict]: ...
    def reinsertar(self, filas: list[dict]) -> None:
        """Vuelve a anotar pases gastados (la base restaurada no los conoce)."""


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso (`uow()`); `uow(lectura=True)` abre una consulta SIN transacción."""

    respaldos: RepositorioRespaldos
    historial: RepositorioHistorial
    ajuste: RepositorioAjuste
    pases: RepositorioPases
    eventos: Eventos
    auditoria: Auditoria

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...


class Vivo(Protocol):
    """La memoria del proceso: qué respaldo se está haciendo ahora (para derivar «en curso» frente a «incompleto») y cuándo se aplazó algo por una clase."""

    def en_marcha(self) -> dict | None: ...
    def marcar(self, respaldo_id: str, operacion: str, en: int) -> None: ...
    def liberar(self) -> None: ...
    def aplazado_por_clase(self) -> int | None: ...
    def aplazar(self, en: int | None) -> None: ...


@dataclass
class Fallo:
    """Lo que un adaptador no pudo hacer, dicho en una frase: nunca un 500 (R-04)."""

    codigo: str
    detalle: str = ""
    extra: dict = field(default_factory=dict)
