"""
Puertos (interfaces) de MOD-010. Todo lo que la evaluación necesita de OTRO módulo entra por aquí y sólo por aquí: el examen y su calificación
(la biblioteca, por la fuente de cursos del aula), la identidad (MOD-001/002), los dispositivos (MOD-009), la clase de la que nace el examen
(MOD-007), el reloj (MOD-015, BR-062), la auditoría (MOD-019) y la cola de salida. Los adaptadores viven en `infraestructura/` y se cambian sin
tocar los casos de uso ni el dominio. Este archivo no importa Django.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from classroom_engine.aplicacion.puertos import Bytes      # un medio de una pregunta es un medio del aula: bytes completos o un flujo crudo


# -------------------------------------------------------------------- el examen (AVACOM Biblioteca)

class Contenido(Protocol):
    """El examen, visto desde la fuente de cursos del aula. Nunca se cachea ni se guarda: cada llamada vuelve a preguntar (artículo 14)."""

    def examen(self, fuente: str, curso_ref: str, objeto_ref: str) -> dict:
        """Lo necesario para ASIGNAR: `{fuente, curso_ref, curso_version, curso_rotulo, leccion_ref, objeto_rotulo, titulo, ajustes, pool}` donde
        `ajustes` son los de la biblioteca ya normalizados (`estrategia`, `cantidad_preguntas`, tolerancias, `cubrir_todos_los_temas`, `tiempo`,
        `aprobacion_pct`, `mostrar_resultados`, `navegacion_atras`, `barajar_opciones`) y `pool` la lista de metadatos por pregunta. Lanza
        NoEncontrado (el curso o el objeto no existen, o no es un examen) y FuenteNoDisponible."""

    def preguntas(self, fuente: str, curso_ref: str, version: str, objeto_ref: str, refs: list[str], semilla: str, *, intento_id: str,
                  dispositivo: str, alumno_id: str) -> dict:
        """El examen DE UN ALUMNO en la vista de aula, sin claves: `{titulo, instrucciones, version, preguntas}` en el orden de `refs`. Las
        URL de sus medios apuntan a las rutas de este módulo. Lanza FuenteNoDisponible y VersionNoDisponible."""

    def abrir_medio(self, fuente: str, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        """Los bytes de un medio del examen."""

    def medios_de(self, fuente: str, curso_ref: str, version: str, objeto_ref: str, refs: list[str], semilla: str) -> set[str]:
        """Los `media_ref` que usan las preguntas indicadas (para servir sólo los medios de ESTE examen)."""

    def calificar(self, fuente: str, curso_ref: str, version: str, items: list[dict]) -> dict[str, dict | None]:
        """Compara las respuestas con la clave DONDE VIVE, siempre con `version`. `items`: `[{objeto_ref, pregunta_ref, respuesta}]` (hasta 200).
        Devuelve `{pregunta_ref: veredicto | None}`; `None` = la biblioteca no estaba (se guarda sin calificar)."""

    def version_instalada(self, fuente: str, curso_ref: str) -> str | None: ...


# ------------------------------------------------------------------ identidad (MOD-001 / MOD-002)

class Identidad(Protocol):
    def organizacion_id(self) -> str | None: ...
    def rotulo_persona(self, persona_id: str) -> str: ...
    def rotulos_personas(self, persona_ids: list[str]) -> dict[str, str]: ...
    def grupo(self, grupo_id: str) -> dict | None: ...
    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool: ...
    def alumnos_del_grupo(self, grupo_id: str) -> list[dict]: ...
    def grupos_del_alumno(self, alumno_id: str) -> list[str]: ...
    def alumnos_activos(self, persona_ids: list[str]) -> dict[str, str]: ...


# ----------------------------------------------------------------- dispositivos (MOD-009)

class Dispositivos(Protocol):
    """El inventario de tabletas. La evaluación no escribe m09_*: pide. La capacidad de control la DECLARA la tableta (registro y latido) y la
    guarda MOD-009; aquí sólo se lee."""

    def por_identificador(self, organizacion_id: str, huella: str) -> dict | None: ...
    def resolver(self, huella: str, nombre: str = "", plataforma: str = "", version_app: str = "", momento: int | None = None,
                 capacidad_control: str | None = None) -> dict | None:
        """Reconoce (o registra la primera vez) la tableta que se presenta. None si no hay huella o nodo."""
    def por_id(self, dispositivo_id: str) -> dict | None: ...
    def asignados_a(self, alumno_ids: list[str]) -> dict[str, dict]: ...
    def latido(self, dispositivo_id: str, momento: int, capacidad_control: str | None = None, telemetria: dict | None = None) -> dict | None: ...
    def abrir_sesion_alumno(self, alumno_id: str, dispositivo_id: str, momento: int, actor: str = "") -> dict:
        """La Dim Sesión Alumno: abrirla en otra tableta cierra la anterior con motivo `relevo` (DEC-023). Lanza DispositivoBloqueado / DispositivoInactivo."""


# ----------------------------------------------------------------------- la clase (MOD-007)

class Aula(Protocol):
    """La clase de la que nace un examen: sólo lectura."""

    def sesion(self, sesion_id: str) -> dict | None: ...
    def dispositivos_de(self, sesion_id: str) -> dict[str, str]:
        """`{persona_id: dispositivo_id}` de quienes están admitidos en la sesión con una tableta conocida."""


# ------------------------------------------------------------ plataforma (MOD-015) y auditoría (MOD-019)

class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La marca autoritativa la pone el nodo (BR-062, INV-017); ningún dato académico usa el reloj del dispositivo."""


class Auditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. `extra` admite motivo, resultado, dispositivo_id y evento_id."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "",
                  anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None: ...


class TiempoReal(Protocol):
    """Avisa a las pantallas de que algo cambió. NUNCA lleva contenido académico: el cliente vuelve a pedir por HTTP. Sale cuando la transacción
    del caso de uso se confirma."""

    def cambio(self, sesion_id: str, que: str, carga: dict | None = None) -> None:
        """`que`: `evaluacion` (a las tabletas y al profesor) · `evaluacion_panel` (sólo al profesor). Sin `sesion_id` no hace nada."""


# ----------------------------------------------------------------------- autorización

@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34) lo declara el cliente."""

    id: str
    rotulo: str = ""
    nivel: int = 2            # 1 alumno · 2 personal · 3 administración (m01_rol.nivel)
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None     # el Principal de MOD-001 cuando hay sesión JWT (lo evalúa el adaptador, nunca el dominio)


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str, asignacion: dict | None = None) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso` (assessment.*). Con `asignacion`, comprueba además que el
        actor sea su profesor titular o la administración."""


# ------------------------------------------------------------------------ repositorios

class RepositorioAsignaciones(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, asignacion_id: str) -> dict | None: ...
    def listar(self, *, estados: tuple[str, ...] | None = None, grupo_id: str | None = None, sesion_id: str | None = None,
               profesor_id: str | None = None) -> list[dict]: ...
    def actualizar(self, asignacion_id: str, **campos) -> dict: ...


class RepositorioIntentos(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, intento_id: str) -> dict | None: ...
    def actualizar(self, intento_id: str, **campos) -> dict: ...
    def de_asignacion(self, asignacion_id: str, estados: tuple[str, ...] | None = None) -> list[dict]: ...
    def del_alumno(self, asignacion_id: str, alumno_id: str) -> list[dict]:
        """Todos los intentos de esa persona en esa asignación, del primero al último."""
    def de_alumno_en(self, alumno_id: str, asignacion_ids: list[str]) -> list[dict]: ...
    def en_estados(self, *estados: str) -> list[dict]: ...
    def vivos_de_personas(self, personas: list[str]) -> int: ...
    def corriendo_en_dispositivo(self, dispositivo_id: str) -> list[dict]: ...


class RepositorioAdmisiones(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, admision_id: str) -> dict | None: ...
    def de_terna(self, asignacion_id: str, alumno_id: str, dispositivo_id: str) -> dict | None: ...
    def de_asignacion(self, asignacion_id: str, solo_en_espera: bool = True) -> list[dict]: ...
    def del_alumno(self, asignacion_id: str, alumno_id: str) -> list[dict]: ...
    def actualizar(self, admision_id: str, **campos) -> dict: ...


class RepositorioIncidentes(Protocol):
    def crear(self, datos: dict) -> tuple[dict, bool]:
        """(fila, creada). Con `ref_cliente` repetido devuelve la existente y `creada = False` (idempotente)."""
    def de_intento(self, intento_id: str) -> list[dict]: ...
    def de_intentos(self, intento_ids: list[str]) -> dict[str, list[dict]]: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso: el hecho, su auditoría y su evento se confirman juntos."""

    asignaciones: RepositorioAsignaciones
    intentos: RepositorioIntentos
    admisiones: RepositorioAdmisiones
    incidentes: RepositorioIncidentes
    outbox: Outbox
    auditoria: Auditoria
    identidad: Identidad
    dispositivos: Dispositivos
    aula: Aula
    tiempo_real: TiempoReal

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
