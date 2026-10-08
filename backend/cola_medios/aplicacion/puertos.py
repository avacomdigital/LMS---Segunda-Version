"""
Lo que la cola necesita de fuera, y sólo por aquí: la fuente de los bytes (AVACOM Contenido, por los casos de uso del aula), el índice persistente, la
memoria rápida (LocMemCache), el aviso a las pantallas y el reloj. Los adaptadores viven en `infraestructura/`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..dominio.clave import ClaveMedio


@dataclass
class RespuestaDeOrigen:
    """La respuesta de la fuente a una petición de bytes: estado HTTP, cabeceras (claves en minúsculas) y un flujo con `read(n)` y `close()`."""

    estado: int
    cabeceras: dict[str, str]
    flujo: Any
    extra: dict[str, str] = field(default_factory=dict)       # cabeceras `X-Avacom-*` que la fuente puso

    def cerrar(self) -> None:
        try:
            self.flujo.close()
        except Exception:   # noqa: BLE001
            pass


class Origen(Protocol):
    def abrir(self, clave: ClaveMedio, rango: str | None, metodo: str) -> RespuestaDeOrigen:
        """Lanza `ErrorDeOrigen` con el error original del aula."""

    def version_del_curso(self, fuente: str, curso_ref: str) -> str:
        """La versión instalada del curso. Lanza `ErrorDeOrigen` si la biblioteca no está o el curso ya no se ofrece."""


class Registro(Protocol):
    """El índice persistente (`cm_recurso`, `cm_solicitud`). Todo son diccionarios planos."""

    def obtener(self, clave: str) -> dict | None: ...
    def por_id(self, recurso_id: str) -> dict | None: ...
    def crear(self, datos: dict) -> dict: ...
    def actualizar(self, recurso_id: str, **campos) -> dict | None: ...
    def eliminar(self, recurso_id: str) -> None: ...
    def solicitar(self, recurso_id: str, *, modulo: str, contexto_ref: str, prioridad: int, persona_id: str, dispositivo_id: str,
                  ahora: int, vence_en: int | None) -> None: ...
    def mejor_prioridad(self, recurso_id: str, ahora: int) -> int | None: ...
    def bajar_proyecciones(self, modulo: str, contexto_ref: str, excepto: list[str], a: int) -> list[str]:
        """Las solicitudes de proyección de ese contexto que ya no son la vigente bajan a `a`. Devuelve los recursos afectados."""
    def activos(self) -> list[dict]: ...
    def del_contexto(self, contexto_ref: str, modulo: str = "") -> list[dict]: ...
    def listar(self, estado: str = "", limite: int = 100) -> list[dict]: ...
    def resumen(self) -> dict: ...
    def candidatos_a_expulsion(self) -> list[dict]: ...
    def aplicar_usos(self, usos: dict[str, tuple[int, int]]) -> None:
        """{recurso_id: (último_uso_en, veces_más)}."""
    def purgar(self, *, fallidos_antes_de: int, solicitudes_vencidas_antes_de: int) -> int: ...
    def ids(self) -> set[str]: ...
    def contextos_de(self, recurso_id: str) -> list[tuple[str, str]]:
        """[(modulo, contexto_ref)] de las solicitudes de ese recurso que tienen contexto."""


class Memoria(Protocol):
    def get(self, clave: str) -> Any: ...
    def set(self, clave: str, valor: Any, segundos: int) -> None: ...
    def delete(self, clave: str) -> None: ...


class Difusion(Protocol):
    def recurso_cambio(self, modulo: str, contexto_ref: str) -> None:
        """Avisa a quien siga ese contexto (la clase) que cambió el estado de sus recursos. Nunca lleva bytes."""


class Reloj(Protocol):
    def ahora_ms(self) -> int: ...
