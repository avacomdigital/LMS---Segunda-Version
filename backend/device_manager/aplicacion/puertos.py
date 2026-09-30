"""
Puertos (interfaces) de MOD-009. Lo que el módulo necesita de OTROS módulos entra por aquí:
la organización del nodo y las sesiones de login (MOD-001), el reloj (MOD-015), la auditoría
(MOD-019) y la cola de salida. Los adaptadores viven en `infraestructura/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación y trae el `principal`; sin ella
    (Q-04, prototipo) lo declara el cliente, como en el aula."""

    id: str
    rotulo: str = ""
    nivel: int = 2
    autenticado: bool = False
    principal: Any = None


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso` (device.*)."""


class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La marca autoritativa la pone el nodo (BR-062, INV-017)."""


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None: ...


class Auditoria(Protocol):
    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "",
                  anterior: dict | None = None, nuevo: dict | None = None) -> None: ...


class Organizaciones(Protocol):
    def unica_id(self) -> str | None:
        """La organización del nodo (MOD-001 la instala); None si el nodo no está instalado."""


class SesionesDeUsuario(Protocol):
    """Las sesiones de login (MOD-001) que viven en un dispositivo: al darlo de baja se cierran."""

    def cerrar_en_dispositivo(self, dispositivo_id: str, momento: int, actor: str) -> int: ...


class Alumnos(Protocol):
    """Las personas de MOD-001 a las que se asigna un equipo (FUN-092). Sólo lectura: este módulo no es dueño de personas."""

    def existe(self, alumno_id: str) -> bool | None:
        """True/False si el padrón lo sabe; None si no se puede saber (sin organización instalada)."""
    def rotulos(self, alumno_ids: list[str]) -> dict[str, str]:
        """El alias de cada persona (`m01_usuario.alias`); las que no existen no aparecen."""


class PaquetesDeEstudio(Protocol):
    """Lo que MOD-008 tiene en un equipo (FUN-093): liberar un equipo con un paquete activo lo dejaría a la vista del siguiente
    alumno. El adaptador resuelve `modo_estudio` de forma perezosa: este módulo no lo importa al cargarse."""

    def activos_en(self, dispositivo_id: str) -> int:
        """Paquetes `solicitado`, `descargandose` o `disponible` (y vigentes) que el equipo conserva."""


class RepositorioDispositivos(Protocol):
    """El inventario. Trabaja con dicts planos para que los casos de uso no dependan del ORM."""

    def crear(self, datos: dict) -> dict: ...
    def por_id(self, dispositivo_id: str) -> dict | None: ...
    def por_identificador(self, organizacion_id: str, identificador_hw: str) -> dict | None: ...
    def listar(self, organizacion_id: str, solo_activos: bool = True) -> list[dict]: ...
    def actualizar(self, dispositivo_id: str, **campos) -> dict: ...
    def bloqueados_entre(self, dispositivo_ids: list[str]) -> set[str]: ...
    def asignados_a(self, alumno_ids: list[str]) -> dict[str, dict]:
        """Por cada alumno, el equipo activo que tiene asignado (perfil `asignado`); los que no tienen no aparecen."""


class RepositorioSesionesAlumno(Protocol):
    """La sesión de alumno en el dispositivo (Dim Sesión Alumno)."""

    def sesion(self, sesion_id: str) -> dict | None: ...
    def abierta_de_alumno(self, alumno_id: str) -> dict | None: ...
    def abierta_en_dispositivo(self, dispositivo_id: str) -> dict | None: ...
    def abiertas_por_dispositivo(self, dispositivo_ids: list[str]) -> dict[str, dict]: ...
    def crear(self, datos: dict) -> dict: ...
    def cerrar(self, sesion_id: str, momento: int, motivo: str) -> dict | None: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso: el hecho, su auditoría y su evento se confirman juntos."""

    dispositivos: RepositorioDispositivos
    sesiones_alumno: RepositorioSesionesAlumno
    outbox: Outbox
    auditoria: Auditoria
    organizaciones: Organizaciones
    sesiones_usuario: SesionesDeUsuario
    alumnos: Alumnos
    paquetes_estudio: PaquetesDeEstudio

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
