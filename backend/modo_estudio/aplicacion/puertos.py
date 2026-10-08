"""
Puertos (interfaces) de MOD-008. Todo lo que el modo de estudio necesita de OTRO módulo entra por aquí y sólo por aquí: el curso y la
calificación (Contenido, que reutiliza el aula), los aparatos (MOD-009), las personas y los grupos (MOD-001), el expediente
(`actualizar_progreso`), la autorización con la política de MOD-001, el reloj, la auditoría (MOD-019) y la cola de salida. Los
adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso ni el dominio.

Los repositorios trabajan con dicts planos para que los casos de uso no dependan del ORM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from classroom_engine.aplicacion.puertos import Bytes   # un medio del aula es un medio de estudio: bytes completos o un flujo crudo


# ------------------------------------------------------------------------------- quién actúa

@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación y trae el `principal`; sin ella (Q-34, prototipo) lo declara
    el cliente: el alumno con `alumno_id` (lo elige quien tiene la tableta, D-15), el profesor con `actor`. `dispositivo_id` es el aparato
    de la sesión de login, si el token lo trae."""

    id: str
    rotulo: str = ""
    nivel: int = 1            # 1 alumno · 2 personal · 3 administración (m01_rol.nivel)
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None     # el Principal de MOD-001 cuando hay sesión JWT (lo evalúa el adaptador, nunca el dominio)


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso` (study.*). Con sesión, el rol debe tenerlo
        concedido (política de MOD-001); sin sesión (Q-34) se permite, como en el aula y el expediente."""


# ---------------------------------------------------------------- plataforma (MOD-015 y MOD-019)

class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La marca autoritativa la pone el nodo (BR-062, INV-017); ningún dato académico usa el reloj del aparato."""


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None: ...


class Auditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. `extra` admite motivo, resultado, dispositivo_id y evento_id."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "",
                  anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


# ------------------------------------------------------------------ identidad (MOD-001 / MOD-002)

class Identidad(Protocol):
    """Las personas y los grupos del padrón. Sólo lectura: MOD-008 no es dueño de personas ni de grupos."""

    def organizacion_id(self) -> str | None:
        """La organización del nodo; None si el nodo no está instalado."""
    def rotulo_persona(self, persona_id: str) -> str: ...
    def rotulos_personas(self, persona_ids: list[str]) -> dict[str, str]: ...
    def grupo(self, grupo_id: str) -> dict | None:
        """`{id, codigo, nombre, nivel_clave, activo}` o None."""
    def grupos_activos(self) -> list[dict]: ...
    def grupos_del_docente(self, docente_id: str) -> list[dict]:
        """Los grupos activos donde la persona es docente vigente."""
    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool: ...
    def alumnos_del_grupo(self, grupo_id: str) -> list[dict]:
        """`[{id, rotulo}]` de los alumnos ACTIVOS del grupo (miembros vigentes con papel de estudiante)."""
    def grupos_del_alumno(self, alumno_id: str) -> list[str]:
        """Los ids de los grupos ACTIVOS donde la persona es alumno vigente."""
    def alumnos_conocidos(self, alumno_ids: list[str]) -> set[str] | None:
        """Los que existen en el padrón; None si no se puede saber (sin organización)."""
    def alumnos_activos(self, persona_ids: list[str]) -> dict[str, str]:
        """`{id: rótulo}` de los que existen en el padrón Y están activos: quien puede elegirse como alumno en una tableta (D-15)."""


# -------------------------------------------------------------------------- aparatos (MOD-009)

class Dispositivos(Protocol):
    """El inventario de aparatos y la sesión de alumno en cada uno. MOD-008 no escribe m09_*: pide (BR-004)."""

    def por_identificador(self, organizacion_id: str, huella: str) -> dict | None: ...
    def resolver(self, huella: str, nombre: str = "", plataforma: str = "", version_app: str = "", momento: int | None = None) -> dict | None:
        """Reconoce (o registra la primera vez, como compartido) el aparato que se presenta. None si no hay huella o nodo."""
    def por_id(self, dispositivo_id: str) -> dict | None: ...
    def asignados_a(self, alumno_ids: list[str]) -> dict[str, dict]: ...
    def sesion_abierta_de_alumno(self, alumno_id: str) -> dict | None: ...
    def abrir_sesion_alumno(self, alumno_id: str, dispositivo_id: str, momento: int, actor: str = "") -> dict:
        """La Dim Sesión Alumno (relevo si hay otra). Lanza DispositivoBloqueado / DispositivoInactivo (errores de MOD-008)."""
    def cerrar_sesion_alumno(self, sesion_id: str, momento: int, motivo: str) -> None: ...


# ------------------------------------------------------------------------------------ expediente

class Expediente(Protocol):
    def actualizar_progreso(self, curso_ref: str, alumno_id: str, leccion_ref: str, porcentaje: float, leccion_rotulo: str = "",
                            version: str = "", actor: str = "") -> None:
        """Pasa el avance de la lección al expediente (`expediente.servicios.actualizar_progreso`): upsert MONOTÓNICO, 100 sella la sección."""


# -------------------------------------------------------------------------- contenido (MOD-007)

class Contenido(Protocol):
    """El curso, sus medios y la calificación: los casos de uso del aula (`classroom_engine`) sobre la fuente de cursos, con las URL de
    los medios apuntando a las rutas de MOD-008. Nunca se cachea: cada llamada vuelve a preguntar (artículo 14)."""

    def leccion(self, *, fuente: str, curso_ref: str, leccion_ref: str, asignacion_id: str = "", dispositivo: str = "",
                alumno_id: str = "", semilla: str | None = None) -> dict:
        """La lección EN VIVO y sin claves: `{fuente, curso (ficha), leccion (vista de aula), medios {media_ref: {clase, mime, titulo}}}`.
        `fuente` vacío usa la configurada. Lanza FuenteNoDisponible, NoEncontrado (curso o lección) o FuenteError."""
    def version_instalada(self, fuente: str, curso_ref: str) -> str | None:
        """La versión del curso instalada AHORA; None si no se puede saber. Nunca lanza."""
    def tamano_de(self, fuente: str, curso_ref: str, media_ref: str) -> int | None:
        """Lo que pesa un medio sin bajarlo (HEAD); None si no se sabe. Nunca lanza."""
    def medir(self, fuente: str, curso_ref: str, media_ref: str, tope_bytes: int, contexto_ref: str = "") -> dict:
        """Devuelve `{bytes, sha256, mime}` del medio COMPLETO (la cola de medios lo trae una vez a la caché del nodo y lo reutiliza; `contexto_ref` es la
        asignación que lo pidió). Lanza NoEncontrado, MedioDemasiadoGrande o FuenteNoDisponible."""
    def abrir_medio(self, fuente: str, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        """Los bytes de un medio (o de un archivo interno de una simulación), de la caché del nodo o en paso a través (ver `cola_medios`)."""
    def calificar(self, fuente: str, curso_ref: str, version: str, items: list[dict]) -> dict[str, dict | None]:
        """La clave se compara DONDE VIVE (`POST /v2/evaluate`). `items`: `[{objeto_ref, pregunta_ref, respuesta}]`. Devuelve el
        veredicto de cada pregunta (la traducción del aula) o None si no se pudo calificar. Nunca lanza: sin biblioteca la respuesta
        se guarda sin calificar (D-6)."""


# --------------------------------------------------------------------------------- repositorios

class RepositorioAsignaciones(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, asignacion_id: str) -> dict | None: ...
    def actualizar(self, asignacion_id: str, **campos) -> dict: ...
    def listar(self, *, grupo_id: str | None = None, estado: str | None = None) -> list[dict]: ...
    def candidatas_del_alumno(self, alumno_id: str, grupo_ids: list[str]) -> list[dict]:
        """Las asignaciones que le alcanzan: de sus grupos o con él entre los destinatarios (en cualquier estado)."""


class RepositorioTareas(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, tarea_id: str) -> dict | None: ...
    def obtener(self, asignacion_id: str, alumno_id: str) -> dict | None: ...
    def actualizar(self, tarea_id: str, **campos) -> dict: ...
    def de_alumno(self, alumno_id: str, asignacion_ids: list[str] | None = None) -> dict[str, dict]:
        """Las tareas de un alumno por `asignacion_id`."""
    def de_asignacion(self, asignacion_id: str) -> list[dict]: ...


class RepositorioPaquetes(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, paquete_id: str) -> dict | None: ...
    def obtener(self, asignacion_id: str, alumno_id: str, dispositivo_id: str) -> dict | None:
        """La fila única (asignación, alumno, aparato), retirada o no: volver a pedir la reutiliza."""
    def actualizar(self, paquete_id: str, **campos) -> dict: ...
    def de_asignacion(self, asignacion_id: str) -> list[dict]:
        """Los paquetes NO retirados de una asignación, de cualquier alumno y aparato (CAP-051)."""
    def del_aparato(self, alumno_id: str, dispositivo_id: str) -> list[dict]:
        """Los paquetes NO retirados de un alumno en un aparato."""
    def de_alumno(self, alumno_id: str, asignacion_ids: list[str] | None = None) -> list[dict]:
        """Los paquetes NO retirados de un alumno en cualquier aparato."""
    def activos_en(self, dispositivo_id: str, ahora: int) -> int:
        """Cuántos paquetes conserva un aparato: solicitados, descargándose o disponibles, no retirados y vigentes."""


class RepositorioPracticas(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, practica_id: str) -> dict | None: ...
    def actualizar(self, practica_id: str, **campos) -> dict: ...
    def de_tarea(self, tarea_id: str, objeto_ref: str | None = None) -> list[dict]:
        """Las prácticas de una tarea, por actividad y número."""
    def obtener(self, tarea_id: str, objeto_ref: str, numero: int) -> dict | None: ...
    def en_curso(self, tarea_id: str, objeto_ref: str) -> dict | None: ...
    def con_en_curso(self, tarea_ids: list[str]) -> set[tuple[str, str]]:
        """`{(tarea_id, objeto_ref)}` de las prácticas en curso de esas tareas."""


class RepositorioSincronizacion(Protocol):
    def por_emisor_y_secuencia(self, emisor_id: str, secuencia: int) -> dict | None: ...
    def crear(self, datos: dict) -> dict: ...
    def actualizar(self, fila_id: int, **campos) -> dict: ...
    def pendientes_de_decision(self, *, alumno_id: str | None = None, asignacion_id: str | None = None,
                               emisor_id: str | None = None) -> list[dict]: ...
    def por_decision(self, asignacion_id: str, alumno_id: str, secuencia: int, emisor_id: str | None = None) -> list[dict]: ...
    def del_emisor(self, emisor_id: str, alumno_id: str | None = None) -> list[dict]:
        """Lo que el libro tiene de una instalación, en orden de secuencia (sin la carga)."""


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso: el hecho, su auditoría y su evento se confirman juntos."""

    asignaciones: RepositorioAsignaciones
    tareas: RepositorioTareas
    paquetes: RepositorioPaquetes
    practicas: RepositorioPracticas
    sincronizaciones: RepositorioSincronizacion
    outbox: Outbox
    auditoria: Auditoria
    identidad: Identidad
    dispositivos: Dispositivos
    expediente: Expediente

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
