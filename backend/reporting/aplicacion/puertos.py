"""
Puertos (interfaces) de MOD-013. Todo lo que Reporting necesita de OTRO módulo entra por aquí y sólo por aquí, y SIEMPRE como lectura: las clases (MOD-007), las evaluaciones
(MOD-010), el libro con las calificaciones ya presentadas (MOD-011), el estudio (MOD-008), los equipos (MOD-009), el padrón (MOD-001/002), el árbol académico de la biblioteca,
el reloj del nodo (MOD-015, BR-062), la auditoría (MOD-019) y la cola de salida. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los casos de uso ni el
dominio. Este archivo no importa Django.

BR-085: ningún puerto de este archivo escribe en datos de otro módulo; los únicos que escriben son los repositorios `m13_*` y la auditoría propia.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34, prototipo) lo declara el cliente."""

    id: str
    rotulo: str = ""
    nivel: int = 2            # 1 alumno · 2 personal · 3 administración (m01_rol.nivel)
    autenticado: bool = False
    dispositivo_id: str = ""
    principal: Any = None     # el Principal de MOD-001 cuando hay sesión JWT (lo evalúa el adaptador, nunca el dominio)
    rol: str = ""             # el código del rol efectivo (TEACHER, REPORTS…), sólo para la bitácora


# ------------------------------------------------------------------------------------------------ fuentes de lectura (módulos dueños)

class Aula(Protocol):
    """MOD-007 por `classroom_engine.servicios`."""

    def detalle_de_sesion(self, sesion_id: str) -> dict | None:
        """`{sesion, participantes[], actividades[], intentos[]}` con sólo cifras (nunca el contenido de una respuesta)."""
    def sesion(self, sesion_id: str) -> dict | None: ...
    def sesiones(self, grupo_ids: list[str] | None = None) -> list[dict]: ...
    def hay_sesion_activa(self) -> bool: ...
    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]: ...
    def ultima_secuencia(self) -> int: ...


class Evaluaciones(Protocol):
    """MOD-010 por `evaluacion.servicios`."""

    def asignaciones_de_grupo(self, grupo_id: str) -> list[dict]: ...
    def asignacion(self, asignacion_id: str) -> dict | None: ...
    def intentos_de_asignacion(self, asignacion_id: str) -> list[dict]: ...
    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]: ...
    def ultima_secuencia(self) -> int: ...


class Libro(Protocol):
    """MOD-011 por `gradebook.servicios`: la calificación YA presentada con la escala del nivel (en modo simple, sin cifras). Reporting no convierte nada."""

    def resultados_del_grupo(self, grupo_id: str) -> dict | None: ...
    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]: ...
    def ultima_secuencia(self) -> int: ...


class Estudio(Protocol):
    """MOD-008 por `modo_estudio.servicios`."""

    def asignacion(self, asignacion_id: str) -> dict | None: ...
    def asignaciones_de_estudio(self, grupo_ids: list[str] | None = None) -> list[dict]: ...
    def tareas_de(self, asignacion_ids: list[str]) -> list[dict]: ...
    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]: ...
    def ultima_secuencia(self) -> int: ...


class Equipos(Protocol):
    """MOD-009 por `device_manager.servicios`: sólo para ponerle nombre a un equipo al mostrarlo."""

    def por_id(self, dispositivo_id: str) -> dict | None: ...


class Identidad(Protocol):
    """MOD-001/002: el padrón. SÓLO LECTURA; sin organización instalada degrada (sin grupos, sin padrón)."""

    def organizacion_id(self) -> str | None: ...
    def grupo(self, grupo_id: str) -> dict | None:
        """`{id, codigo, nombre, periodo, nivel_clave, activo}`."""
    def todos_los_grupos(self) -> list[str]:
        """Los grupos activos de la organización."""
    def grupos_del_docente(self, persona_id: str) -> list[str]: ...
    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool: ...
    def alumnos_del_grupo(self, grupo_id: str) -> list[dict]:
        """`[{id, rotulo}]`, activos."""
    def grupos_del_alumno(self, alumno_id: str) -> list[str]: ...
    def rotulos_personas(self, persona_ids: list[str]) -> dict[str, str]: ...
    def grupos_de_nivel(self, nivel_clave: str) -> list[str]: ...


class Arbol(Protocol):
    """El árbol académico de AVACOM Biblioteca (país · nivel · grado · materia · tema), SÓLO LEÍDO en el momento. Una biblioteca cerrada no es un error: se dice."""

    def arbol(self) -> tuple[bool, str, list[dict]]: ...
    def cursos_del_arbol(self, arbol: dict[str, str]) -> set[str] | None: ...


@dataclass
class ArchivoGenerado:
    """El archivo que el nodo acaba de generar, listo para entregarse: su contenido (posicionado al inicio; quien lo recibe lo cierra), su tamaño y su huella SHA-256."""

    contenido: Any
    bytes_total: int
    huella: str

    def cerrar(self) -> None:
        try:
            self.contenido.close()
        except Exception:   # noqa: BLE001
            pass


class Escritor(Protocol):
    def escribir(self, documento: Any, formato: str) -> ArchivoGenerado:
        """El documento exportable (`dominio.documento.Documento`) → xlsx o csv. Sin ninguna llamada a internet (BR-084) y sin tener el archivo entero en memoria dos veces."""


# ------------------------------------------------------------ plataforma (MOD-015) y auditoría (MOD-019)

class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La marca autoritativa la pone el nodo (BR-062, INV-017); nada usa el reloj del dispositivo."""
    def a_local(self, ms: int) -> datetime:
        """Ese instante en la zona horaria del nodo (para el nombre y la cabecera del archivo)."""


class Auditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. `extra` admite motivo, resultado, dispositivo_id y evento_id."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None: ...


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str, *, grupo_id: str = "", organizacion: bool = False) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso`; con `grupo_id`, FueraDeAlcance si el permiso no llega a ese grupo (un profesor sólo
        ve SUS grupos; reportes y administración, toda la organización); con `organizacion`, si no llega a TODA la organización."""
    def exigir_alguno(self, actor: Actor, permisos: tuple[str, ...], *, grupo_id: str = "", organizacion: bool = False) -> None: ...
    def grupos_visibles(self, actor: Actor, permiso: str) -> list[str] | None:
        """Los grupos sobre los que el actor tiene `permiso`; None = toda la organización."""
    def puede(self, actor: Actor, permiso: str) -> bool:
        """¿Tiene ese permiso el rol efectivo (con cualquier alcance)? Sin sesión (prototipo) siempre sí."""


# ------------------------------------------------------------------------------------------------ repositorios m13_*

class RepositorioClases(Protocol):
    def guardar(self, clase: dict, alumnos: list[dict]) -> bool:
        """Crea o reemplaza la clase y sus filas por alumno. False si nada cambió (misma huella): recalcular lo mismo no escribe."""
    def get(self, sesion_id: str) -> dict | None: ...
    def alumnos(self, sesion_id: str) -> list[dict]: ...
    def alumnos_de_clases(self, sesion_ids: list[str]) -> dict[str, dict[str, dict]]:
        """`{sesion_id: {alumno_id: fila}}` de varias clases en UNA consulta (el avance de un grupo recorre todas sus clases)."""
    def listar(self, *, grupo_ids: list[str] | None = None, profesor_id: str = "", desde: int | None = None, hasta: int | None = None, limite: int = 50) -> list[dict]: ...
    def de_grupo(self, grupo_id: str) -> list[dict]: ...
    def filas_de_alumno(self, alumno_id: str, sesion_ids: list[str]) -> list[dict]: ...
    def contar(self) -> int: ...
    def con_senales(self) -> list[dict]:
        """Las clases cuyas señales de integración aún están guardadas (para limpiarlas al caducar)."""
    def eliminar(self, sesion_id: str) -> None: ...


class RepositorioAvances(Protocol):
    def grupo(self, grupo_id: str) -> dict | None: ...
    def guardar_grupo(self, datos: dict) -> None: ...
    def marcar_sucio(self, grupo_id: str, ahora: int) -> None:
        """Marca el avance del grupo como desactualizado (lo crea vacío si no existía): se recalcula fuera de clase o cuando alguien lo pide."""
    def marcar_todos_sucios(self, grupo_ids: list[str], ahora: int) -> None: ...
    def sucios(self) -> list[str]: ...
    def alumnos(self, grupo_id: str) -> list[dict]: ...
    def alumno(self, grupo_id: str, alumno_id: str) -> dict | None: ...
    def de_alumno(self, alumno_id: str) -> list[dict]: ...
    def guardar_alumnos(self, grupo_id: str, filas: list[dict]) -> None:
        """Reemplaza las filas de ese grupo (los alumnos que ya no están, se van)."""
    def eliminar_grupo(self, grupo_id: str) -> None:
        """Quita el avance de un grupo que ya no existe o dejó de estar activo (y los de sus alumnos)."""


class RepositorioEstadoDeEquipos(Protocol):
    def fijar(self, alumno_id: str, dispositivo_id: str, cola_pendiente: int, ahora: int) -> None: ...
    def pendientes_de(self, alumno_ids: list[str]) -> list[dict]: ...


class RepositorioMarcas(Protocol):
    def get(self, fuente: str) -> int: ...
    def estado(self, fuente: str) -> dict:
        """`{secuencia, fallo_secuencia, fallos}`."""
    def guardar(self, fuente: str, secuencia: int, ahora: int, *, fallo_secuencia: int = 0, fallos: int = 0) -> None: ...


class RepositorioEstado(Protocol):
    def get(self) -> dict: ...
    def empezar_reconstruccion(self, ahora: int, por: str) -> None: ...
    def terminar_reconstruccion(self, ahora: int, por: str, error: str = "") -> None: ...
    def anotar_actualizacion(self, ahora: int) -> None: ...


class RepositorioConfig(Protocol):
    def get(self) -> dict:
        """La configuración vigente, o los valores de fábrica si nadie la cambió."""
    def guardar(self, datos: dict, por: str, ahora: int, version_esperada: int | None) -> dict | None:
        """None si `version_esperada` ya no es la vigente."""


class RepositorioExportaciones(Protocol):
    def crear(self, datos: dict) -> dict: ...
    def por_id(self, exportacion_id: str) -> dict | None: ...
    def anotar_intento_fallido(self, exportacion_id: str, intento: dict) -> dict | None:
        """Añade un intento fallido sin cerrarla (sólo si sigue `autorizada`)."""
    def entregar(self, exportacion_id: str, *, destino_tipo: str, huella_verificada: str, ahora: int, intento: dict) -> dict | None:
        """`autorizada → entregada` en UNA sentencia: None si ya no estaba `autorizada` (otro la confirmó o caducó)."""
    def caducar(self, exportacion_id: str, ahora: int) -> dict | None:
        """`autorizada → caducada` si ya venció; None si no aplica."""
    def vencidas(self, ahora: int) -> list[dict]: ...
    def de_actor(self, actor_id: str, limite: int = 20) -> list[dict]: ...


class RepositorioRecientes(Protocol):
    def registrar(self, actor_id: str, tipo: str, parametros: dict, ahora: int) -> None: ...
    def marcar_exportado(self, actor_id: str, tipo: str, parametros: dict, ahora: int) -> None: ...
    def de(self, actor_id: str, limite: int) -> list[dict]: ...


class RepositorioProyecciones(Protocol):
    def borrar_derivadas(self) -> dict[str, int]:
        """Borra TODAS las tablas derivadas (BR-007) y devuelve cuántas filas tenía cada una. Nunca toca la configuración, las exportaciones ni los recientes."""


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso (`uow()`); `uow(lectura=True)` abre una consulta SIN transacción (el nodo corre SQLite con `IMMEDIATE`: un `atomic` toma el bloqueo
    de toda la base)."""

    clases: RepositorioClases
    avances: RepositorioAvances
    equipos_estado: RepositorioEstadoDeEquipos
    marcas: RepositorioMarcas
    estado: RepositorioEstado
    config: RepositorioConfig
    exportaciones: RepositorioExportaciones
    recientes: RepositorioRecientes
    proyecciones: RepositorioProyecciones
    outbox: Outbox
    auditoria: Auditoria
    identidad: Identidad
    aula: Aula
    evaluacion: Evaluaciones
    libro: Libro
    estudio: Estudio
    equipos: Equipos
    arbol: Arbol

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
    def aislado(self) -> Any:
        """Un contexto (savepoint) que deshace sólo lo suyo si falla: aísla un evento que no se puede aplicar para que no detenga a los demás."""
