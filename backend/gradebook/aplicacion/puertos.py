"""
Puertos (interfaces) de MOD-011. Todo lo que el Gradebook necesita de OTRO módulo entra por aquí y sólo por aquí: los intentos y las respuestas
(MOD-010), la identidad y los grupos (MOD-001/002), la rúbrica (la biblioteca, por su `grading-guide`), el reloj del nodo (MOD-015, BR-062), la
auditoría (MOD-019) y la cola de salida. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso ni el dominio.
Este archivo no importa Django.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from ..dominio.escala import DefinicionEscala


@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34, prototipo) lo declara el cliente."""

    id: str
    rotulo: str = ""
    nivel: int = 2            # 1 alumno · 2 personal · 3 administración (m01_rol.nivel)
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None     # el Principal de MOD-001 cuando hay sesión JWT (lo evalúa el adaptador, nunca el dominio)


# ------------------------------------------------------------------------------------ MOD-010 · evaluación

class Evaluacion(Protocol):
    """Los resultados de la evaluación. SÓLO por la interfaz pública de MOD-010 (`evaluacion.servicios`): el libro no lee ni escribe `m10_*` por su cuenta.
    Las operaciones de escritura (`puntuar`, `publicar_revision`) las ejecuta MOD-010, dueño de las respuestas, dentro de la transacción del caso de uso."""

    def intento(self, intento_id: str) -> dict | None: ...
    def intentos_del_alumno(self, asignacion_id: str, alumno_id: str) -> list[dict]: ...
    def intentos_de_asignacion(self, asignacion_id: str) -> list[dict]: ...
    def intentos_en_revision(self, asignacion_ids: list[str]) -> list[dict]:
        """Los intentos de esas asignaciones que esperan revisión del profesor (estado `en_revision_docente`)."""
    def asignacion(self, asignacion_id: str) -> dict | None: ...
    def asignaciones_de_grupo(self, grupo_id: str) -> list[dict]: ...
    def asignaciones_del_alumno(self, alumno_id: str) -> list[dict]: ...
    def pares_de_resultados(self) -> list[tuple[str, str]]:
        """Todos los `(asignacion_id, alumno_id)` que tienen al menos un intento: lo que hay que recalcular al reconstruir lo derivado."""
    def pendientes_de(self, intento: dict) -> list[str]:
        """Las `pregunta_ref` que sólo un profesor puede puntuar y nadie ha revisado."""
    def aciertos_de(self, intento: dict) -> tuple[int, int]:
        """`(aciertos, preguntas)` del intento, para el modo simple y la retroalimentación."""
    def resultado_liberado(self, asignacion: dict, intento: dict) -> bool:
        """¿MOD-010 ya liberó este resultado al alumno (RF-004)? Lo usa el modo simple para decidir si muestra los aciertos."""
    def asignaciones_sin_grupo(self) -> list[dict]:
        """Las asignaciones (no borrador) a alumnos sueltos: no pertenecen a ningún grupo."""
    def evaluaciones_en_curso(self, grupo_ids: list[str], alumno_ids: list[str] | tuple[str, ...] = ()) -> int:
        """Cuántas asignaciones abiertas o programadas (y cuántos intentos vivos) hay en esos grupos y, con `alumno_ids`, a alumnos sueltos que los alcanzan."""
    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
        """`(eventos, nueva_marca)`: los eventos de esos `tipos` con secuencia mayor a la marca, en orden; `[{secuencia, tipo, carga, creado_en}]`. LECTURA: no
        marca nada como publicado (ese oficio es de MOD-015). `nueva_marca` es hasta donde se miró (sirve para no releer lo irrelevante)."""
    def revision_del_intento(self, actor: Actor, intento_id: str) -> dict:
        """Lo que MOD-010 muestra para revisar: `{intento, titulo, filas[{pregunta, respuesta, veredicto, revision, …}]}`."""
    def puntuar(self, actor: Actor, intento_id: str, pregunta_ref: str, datos: dict) -> dict:
        """MOD-010 asienta la puntuación del reactivo (`{puntaje, comentario?, motivo?}`)."""
    def publicar_revision(self, actor: Actor, intento_id: str) -> dict:
        """`en_revision_docente → calificado` en MOD-010 cuando no queda nada pendiente."""


class GuiaDeCalificacion(Protocol):
    """La rúbrica y la respuesta modelo de una pregunta abierta: de la biblioteca, sólo para calificar a mano (`grading-guide`). Nunca se guarda."""

    def de(self, fuente: str, curso_ref: str, version: str, pregunta_ref: str) -> dict | None:
        """`{rubrica: [{id, criterio, puntos_max: Decimal}], respuesta_modelo, puntos, formato}` o None si la biblioteca no la entrega."""


class Arbol(Protocol):
    """El árbol académico de la biblioteca, sólo para ponerle nombre a una materia (el código sale del `curso_ref`). Leído en vivo; con la biblioteca cerrada, vacío."""

    def nombres_de_materias(self) -> dict[str, str]: ...


# ----------------------------------------------------------------------------------- MOD-001/002 · identidad

class Identidad(Protocol):
    def organizacion_id(self) -> str | None: ...
    def grupo(self, grupo_id: str) -> dict | None:
        """`{id, codigo, nombre, periodo, nivel_clave, activo}`."""
    def grupos_de_nivel(self, nivel_clave: str) -> list[str]: ...
    def todos_los_grupos(self) -> list[str]:
        """Los grupos activos de la organización (lo que ve quien no tiene el alcance recortado a los suyos)."""
    def grupos_del_docente(self, persona_id: str) -> list[str]: ...
    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool: ...
    def alumnos_del_grupo(self, grupo_id: str) -> list[dict]:
        """`[{id, rotulo}]`, activos."""
    def grupos_del_alumno(self, alumno_id: str) -> list[str]: ...
    def alumnos_activos(self, persona_ids: list[str]) -> dict[str, str]: ...
    def rotulos_personas(self, persona_ids: list[str]) -> dict[str, str]: ...


# ------------------------------------------------------------ plataforma (MOD-015) y auditoría (MOD-019)

class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La marca autoritativa la pone el nodo (BR-062, INV-017); ningún dato académico usa el reloj del dispositivo."""


class Auditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. `extra` admite motivo, resultado, dispositivo_id y evento_id."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None: ...


# ----------------------------------------------------------------------------------------- autorización

class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str, *, grupo_id: str = "", organizacion: bool = False) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso`; con `grupo_id`, FueraDeAlcance si el permiso no llega a ese grupo
        (un profesor sólo opera SUS grupos; la administración y reportes, toda la organización); con `organizacion`, si no llega a TODA la organización."""

    def exigir_alguno(self, actor: Actor, permisos: tuple[str, ...], *, grupo_id: str = "", organizacion: bool = False) -> None: ...

    def exigir_alumno(self, actor: Actor) -> None:
        """Quien consulta SUS resultados: con sesión, un alumno con `results.read` sobre lo suyo; sin sesión (Q-34), un alumno que existe y está activo."""

    def grupos_visibles(self, actor: Actor, permiso: str) -> list[str] | None:
        """Los grupos sobre los que el actor tiene `permiso`; None = toda la organización."""


# ----------------------------------------------------------------------------------------- repositorios

class RepositorioCalificaciones(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, calificacion_id: str) -> dict | None: ...
    def por_intento(self, intento_id: str) -> dict | None: ...
    def de_asignacion(self, asignacion_id: str, alumno_id: str | None = None) -> list[dict]: ...
    def de_grupo(self, grupo_id: str) -> list[dict]: ...
    def de_alumno(self, alumno_id: str, grupo_id: str | None = None) -> list[dict]: ...
    def todas(self) -> list[dict]: ...
    def actualizar_si_version(self, calificacion_id: str, version_esperada: int, **campos) -> dict | None:
        """Compara y cambia en UNA sentencia: sólo escribe si `version` sigue siendo la esperada, y la incrementa. None = alguien se adelantó."""


class RepositorioVersiones(Protocol):
    """SÓLO INSERCIÓN: ni `actualizar` ni `borrar`."""

    def anexar(self, calificacion_id: str, tipo: str, *, actor_id: str, en: int, puntaje_anterior: Decimal | None = None, puntaje_nuevo: Decimal | None = None,
               estado_anterior: str = "", estado_nuevo: str = "", motivo: str = "", solicitud_id: str = "", datos: dict | None = None) -> dict: ...
    def de(self, calificacion_id: str) -> list[dict]: ...
    def por_solicitud(self, calificacion_id: str, solicitud_id: str) -> dict | None: ...


class RepositorioRevisiones(Protocol):
    """SÓLO INSERCIÓN."""

    def anexar(self, datos: dict) -> dict: ...
    def por_solicitud(self, intento_id: str, solicitud_id: str) -> dict | None: ...
    def de_intento(self, intento_id: str) -> list[dict]: ...


class RepositorioEscalas(Protocol):
    def crear_escala(self, datos: dict) -> dict: ...
    def por_id(self, escala_id: str) -> dict | None: ...
    def por_codigo(self, codigo: str) -> dict | None: ...
    def listar(self) -> list[dict]: ...
    def crear_version(self, escala_id: str, definicion: DefinicionEscala, *, huella: str, nota: str, creada_por: str, vigente_desde: int) -> dict: ...
    def version(self, version_id: str) -> dict | None:
        """`{id, escala_id, codigo, nombre, numero, definicion: DefinicionEscala, huella, nota, vigente_desde, activa}`."""
    def ultima_version(self, escala_id: str) -> dict | None: ...
    def versiones_de(self, escala_id: str) -> list[dict]: ...


class RepositorioNiveles(Protocol):
    def get(self, nivel_clave: str) -> dict | None: ...
    def todos(self) -> list[dict]: ...
    def guardar(self, nivel_clave: str, modo: str, escala_version_id: str | None, por: str, ahora: int, version_esperada: int | None) -> dict | None:
        """Crea o cambia; None si `version_esperada` ya no es la vigente."""


class RepositorioPolitica(Protocol):
    def get(self) -> dict:
        """La política vigente, o los valores por defecto si nadie la configuró."""
    def guardar(self, datos: dict, por: str, ahora: int) -> dict: ...


class RepositorioClasificaciones(Protocol):
    def get(self, asignacion_id: str) -> dict | None: ...
    def de(self, asignacion_ids: list[str]) -> dict[str, dict]: ...
    def guardar(self, asignacion_id: str, tipo_evaluacion: str, afecta_oficial: bool, objetivos: list, por: str, ahora: int) -> dict: ...


class RepositorioResultados(Protocol):
    """Lo DERIVADO: se puede borrar y reconstruir."""

    def get(self, asignacion_id: str, alumno_id: str) -> dict | None: ...
    def guardar(self, datos: dict) -> dict: ...
    def de_grupo(self, grupo_id: str) -> list[dict]: ...
    def de_asignacion(self, asignacion_id: str) -> list[dict]: ...
    def de_alumno(self, alumno_id: str, grupo_id: str | None = None, periodo: str | None = None, curso_ref: str | None = None) -> list[dict]: ...
    def borrar_todo(self) -> int: ...


class RepositorioObservaciones(Protocol):
    """Las observaciones del docente: una por alumno, grupo, periodo y curso (vacío = general)."""

    def get(self, alumno_id: str, grupo_id: str, periodo: str, curso_ref: str = "") -> dict | None: ...
    def de_alumno(self, alumno_id: str, grupo_id: str) -> list[dict]: ...
    def de_grupo(self, grupo_id: str) -> list[dict]: ...
    def crear(self, datos: dict) -> dict: ...
    def actualizar_si_version(self, observacion_id: str, version_esperada: int, **campos) -> dict | None:
        """Compara y cambia en UNA sentencia; None = alguien se adelantó."""


class RepositorioAgregados(Protocol):
    def get(self, alumno_id: str, grupo_id: str, periodo: str, curso_ref: str) -> dict | None: ...
    def guardar(self, datos: dict) -> dict: ...
    def de_grupo(self, grupo_id: str, periodo: str | None = None) -> list[dict]: ...
    def de_alumno(self, alumno_id: str) -> list[dict]: ...
    def borrar_todo(self) -> int: ...


class RepositorioMarcas(Protocol):
    def get(self, consumidor: str) -> int: ...
    def estado(self, consumidor: str) -> dict:
        """`{secuencia, fallo_secuencia, fallos}`: la marca y el evento que no se pudo aplicar y la retiene (0 = ninguno), con cuántos ciclos seguidos falló."""
    def guardar(self, consumidor: str, fuente: str, secuencia: int, ahora: int, *, fallo_secuencia: int = 0, fallos: int = 0) -> None: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso: el hecho, su historial, su auditoría y su evento se confirman juntos; ante cualquier error se revierte TODO (también lo
    que MOD-010 hizo dentro de esa transacción por encargo del libro)."""

    calificaciones: RepositorioCalificaciones
    versiones: RepositorioVersiones
    revisiones: RepositorioRevisiones
    escalas: RepositorioEscalas
    niveles: RepositorioNiveles
    politica: RepositorioPolitica
    clasificaciones: RepositorioClasificaciones
    resultados: RepositorioResultados
    agregados: RepositorioAgregados
    observaciones: RepositorioObservaciones
    marcas: RepositorioMarcas
    outbox: Outbox
    auditoria: Auditoria
    identidad: Identidad
    evaluacion: Evaluacion
    guia: GuiaDeCalificacion
    arbol: Arbol

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
    def aislado(self) -> Any:
        """Un contexto (savepoint) que deshace sólo lo suyo si falla: aísla un evento que no se puede aplicar para que no detenga a los demás."""
