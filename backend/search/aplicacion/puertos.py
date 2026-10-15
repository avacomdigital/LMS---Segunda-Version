"""
Los puertos de Search (MOD-021): lo que la aplicación necesita de afuera. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso.

  FuenteLocal       una entidad del LMS que se indexa (evaluación, estudio asignado, clase): sus eventos, su estado ACTUAL y su listado. Es la interfaz del módulo
                    propietario (BR-004): Search nunca lee ni escribe las tablas de otro módulo.
  Catalogo          el catálogo de AVACOM Biblioteca (cursos, lecciones, recursos): se pregunta EN VIVO y nunca se guarda (artículo 14).
  Identidad         el padrón de MOD-001: grupos, periodos y a qué grupos enseña quien consulta.
  Autorizacion      los permisos de MOD-001 con SU política: qué puede leer quien consulta, en este instante.
  Indice            la tabla de texto completo (SQLite FTS5) y su proyección. Reconstruible: vaciarla no pierde ningún dato académico.
  Marcas · Estado · Sinonimos · Outbox · Auditoria · Reloj · Aula   lo propio del módulo y los servicios de plataforma.

No hay una cola nueva: Search lee las colas de salida de los módulos propietarios desde su marca de lectura y guarda sólo su marca (cuando exista MOD-015, la marca se
llevará allí), igual que el Gradebook con la evaluación.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..dominio.documento import Documento, Visibilidad


@dataclass(frozen=True)
class Actor:
    id: str = ""
    rotulo: str = ""
    nivel: int = 2
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None


@dataclass(frozen=True)
class Regla:
    """Lo que UN tipo permite ver a quien consulta: toda la organización o sólo los grupos que enseña (y lo que creó sin grupo)."""

    tipo: str
    alcance: str
    grupos: tuple[str, ...] = ()
    persona_id: str = ""


@dataclass(frozen=True)
class Impacto:
    """Un resultado del catálogo de la biblioteca (curso, lección o recurso), con lo que ella devuelve."""

    tipo: str
    curso_ref: str
    titulo: str
    leccion_ref: str = ""
    objeto_ref: str = ""
    fragmento: str = ""
    resaltados: tuple = ()
    ruta_arbol: tuple[str, ...] = ()
    posicion: int = 0


@dataclass(frozen=True)
class ResultadoDelCatalogo:
    disponible: bool = True
    motivo: str = ""
    sugerencia: str = ""
    impactos: tuple[Impacto, ...] = ()
    total: int = 0


# ----------------------------------------------------------------------------------------------- módulos propietarios

class FuenteLocal(Protocol):
    tipo: str          # el tipo de entidad que indexa (`assessment`, `study`, `class`)
    fuente: str        # el módulo dueño de la cola de la que se lee (`evaluacion`, `estudio`, `aula`)

    def eventos_desde(self, secuencia: int, limite: int) -> tuple[list[dict], int]:
        """`(eventos, hasta_donde_se_miró)`: los eventos de ESTA entidad con secuencia mayor a la dada, `[{secuencia, tipo, entidad_id, creado_en}]`. Lectura pura."""

    def ultima_secuencia(self) -> int: ...

    def documento(self, entidad_id: str) -> Documento | None:
        """El estado ACTUAL de la entidad, o None si ya no existe o no es buscable (borrador, archivada…)."""

    def documentos(self, entidad_ids: list[str]) -> dict[str, Documento]:
        """Lo mismo para varias a la vez: sólo las que existen y son buscables."""

    def todos(self) -> Iterator[Documento]:
        """Todas las entidades buscables (para la construcción inicial y la reconstrucción)."""


class Catalogo(Protocol):
    def buscar(self, consulta: str, arbol: dict[str, str], tipos: tuple[str, ...], limite: int) -> ResultadoDelCatalogo:
        """La búsqueda de la biblioteca (`/v2/search`). Nunca lanza: una biblioteca cerrada es `disponible=False` con su motivo."""

    def arbol(self) -> tuple[bool, str, list[dict]]:
        """`(disponible, motivo, nodos)`: el árbol académico de la biblioteca, `[{kind, code, name, count, children}]`."""

    def cursos_del_arbol(self, arbol: dict[str, str]) -> set[str] | None:
        """Los `curso_ref` de los cursos que cuelgan de ese nodo del árbol; None si la biblioteca no pudo contestar."""

    def existe(self, curso_ref: str, leccion_ref: str = "", objeto_ref: str = "") -> bool | None:
        """¿Sigue instalado y disponible? None si la biblioteca no pudo contestar."""


class Identidad(Protocol):
    def organizacion_id(self) -> str | None: ...

    def grupos(self, grupo_ids: list[str]) -> dict[str, dict]:
        """`{id: {id, codigo, nombre, periodo, nivel_clave, activo}}`."""

    def grupos_activos(self) -> list[dict]:
        """Todos los grupos activos de la organización."""

    def grupos_del_docente(self, persona_id: str) -> list[str]: ...

    def grupos_de_periodo(self, periodo: str) -> list[str]: ...


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None:
        """Lanza SinPermiso si el rol efectivo no tiene el permiso."""

    def visibilidad(self, actor: Actor) -> Visibilidad:
        """Lo que el actor puede leer AHORA: por tipo, el alcance de su permiso de lectura; y los grupos de los que es docente."""

    def tiene(self, actor: Actor, permiso: str) -> bool: ...


class Aula(Protocol):
    def hay_sesion_activa(self) -> bool: ...


# ----------------------------------------------------------------------------------------------- lo propio

class Indice(Protocol):
    def buscar(self, expresion: str, reglas: list[Regla], *, grupo_ids: list[str] | None, curso_refs: list[str] | None, tope: int) -> list[dict]:
        """Los candidatos que coinciden con la expresión y que las reglas permiten, del mejor al peor: `[{tipo, entidad_id, bm25, …}]`."""

    def guardar(self, documento: Documento, ahora: int) -> str:
        """`nuevo` | `actualizado` | `igual` (si la huella no cambió, no escribe)."""

    def quitar(self, tipo: str, entidad_id: str) -> bool: ...

    def quitar_ids(self, tipo: str, entidad_ids: list[str]) -> int: ...

    def vaciar(self) -> int: ...

    def contar(self) -> dict[str, int]: ...

    def ids_de(self, tipo: str) -> set[str]: ...


class Marcas(Protocol):
    def estado(self, fuente: str) -> dict:
        """`{secuencia, fallo_secuencia, fallos, actualizada_en}`; sin fila, todo en cero."""

    def guardar(self, fuente: str, secuencia: int, ahora: int, *, fallo_secuencia: int = 0, fallos: int = 0) -> None: ...

    def todas(self) -> dict[str, dict]: ...


class EstadoDelIndice(Protocol):
    def leer(self) -> dict:
        """`{estado, construido_en, sincronizado_en, error, error_en, reconstruccion_desde}`; sin fila, el índice está por construirse."""

    def escribir(self, **campos) -> None: ...


class Sinonimos(Protocol):
    def mapa(self) -> dict[str, list[str]]:
        """raíz → equivalentes (texto normalizado), en ambos sentidos."""

    def grupos(self) -> list[list[str]]: ...

    def reemplazar(self, grupos: list[list[str]], ahora: int, actor_id: str) -> None: ...


class Outbox(Protocol):
    def publicar(self, tipo_evento: str, agregado_id: str, carga: dict) -> None: ...


class Auditoria(Protocol):
    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...

    def denegada(self, actor: str, permiso: str | None, objeto: dict) -> None: ...


class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """El instante autoritativo lo pone el nodo (BR-062): ningún dato usa el reloj del dispositivo."""


class UnidadDeTrabajo(Protocol):
    indice: Indice
    marcas: Marcas
    estado: EstadoDelIndice
    sinonimos: Sinonimos
    outbox: Outbox
    auditoria: Auditoria

    def aislado(self) -> AbstractContextManager: ...


@dataclass
class Configuracion:
    sincronizar_al_consultar: bool = True
    lote_eventos: int = 200
    paginas_al_consultar: int = 3


@dataclass
class Servicios:
    uow: Callable[..., AbstractContextManager]
    fuentes: dict[str, FuenteLocal]                # por TIPO de entidad
    identidad: Identidad
    autorizacion: Autorizacion
    catalogo: Catalogo
    aula: Aula
    reloj: Reloj
    config: Configuracion = field(default_factory=Configuracion)
