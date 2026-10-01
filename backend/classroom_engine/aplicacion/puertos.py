"""
Puertos (interfaces) de MOD-007. Todo lo que el aula necesita de OTRO módulo entra
por aquí y sólo por aquí: la biblioteca (curso), la identidad (MOD-001/002), la
evaluación (MOD-010), el reloj (MOD-015), la auditoría (MOD-019) y la cola de
salida. Los adaptadores viven en `infraestructura/` y se cambian sin tocar los
casos de uso ni el dominio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# ------------------------------------------------------- fuente de cursos (MOD-004 / Biblioteca)

@dataclass
class Bytes:
    """Un medio servido por la fuente: bytes completos o un flujo crudo que el adaptador HTTP reenvía."""

    tipo: str
    datos: bytes | None = None
    flujo: Any = None                    # respuesta HTTP abierta de la biblioteca (pass-through)
    cabeceras: dict[str, str] = field(default_factory=dict)


class FuenteDeCursos(Protocol):
    """Quien entrega el curso. Nunca se cachea: cada llamada vuelve a preguntar."""

    nombre: str

    def cursos(self) -> list[dict]:
        """Manifiestos o fichas (contrato 1) de los cursos ofrecidos, con la política de la escuela ya aplicada."""

    def curso(self, curso_ref: str, *, version: str | None = None, rol: str = "estudiante", semilla: str | None = None) -> dict:
        """El curso crudo (esquema 1.0 recortado por la biblioteca, o el árbol del contrato 1).
        `version` exige esa versión (la API sólo sirve la instalada: otra es CursoNoEncontrado).
        `rol` decide el perfil que se pide (`teacher` trae `teacherNotes`). `semilla` fija el barajado
        de las opciones para que toda la clase vea el mismo orden. CursoNoEncontrado si no existe."""

    def medio(self, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str) -> Bytes:
        """Los bytes de un medio del curso (o de un archivo interno de una simulación)."""

    def evaluar(self, curso_ref: str, version: str, objeto_ref: str, pregunta_ref: str, respuesta: dict) -> dict:
        """Compara la respuesta con la clave DONDE VIVE la clave y devuelve el veredicto crudo
        (`score`, `maxScore`, `correct`, `requiresManualGrading`, `feedback`). Siempre con `version`."""

    def evaluar_lote(self, curso_ref: str, version: str, items: list[dict]) -> list[dict]:
        """Varias respuestas de una vez (hasta 200 por llamada); cada item lleva objectId, questionId y response."""

    def estado(self) -> dict:
        """Nunca lanza: {disponible, motivo, sugerencia, huella, cursos_instalados…}."""


# ------------------------------------------------------------------ identidad (MOD-001 / MOD-002)

class Identidad(Protocol):
    def rotulo_persona(self, persona_id: str) -> str: ...
    def rotulo_grupo(self, grupo_id: str) -> str: ...
    def esta_inscrito(self, grupo_id: str, persona_id: str) -> bool | None:
        """True/False si hay padrón; None si no se puede saber (sin grupo o sin MOD-002)."""
    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool | None: ...


# ----------------------------------------------------------------- dispositivos (MOD-009)

class Dispositivos(Protocol):
    """El inventario de tabletas y la sesión de alumno en cada una. El aula no escribe m09_*: pide."""

    def resolver(self, identificador: str, nombre: str = "", plataforma: str = "", version_app: str = "",
                 momento: int | None = None) -> dict | None:
        """Reconoce (o registra la primera vez) la tableta que se presenta. None si no hay huella o nodo."""
    def por_id(self, dispositivo_id: str) -> dict | None: ...
    def latido(self, dispositivo_id: str, momento: int, telemetria: dict | None = None) -> None:
        """Señal de vida de la tableta; `telemetria` puede traer espacio_libre_mb y bateria_pct."""
    def bloqueados_entre(self, dispositivo_ids: list[str]) -> set[str]:
        """Los que no deben recibir lanzamientos: bloqueados o retirados."""
    def abrir_sesion_alumno(self, alumno_id: str, dispositivo_id: str, momento: int, actor: str = "") -> dict:
        """La Dim Sesión Alumno. Lanza DispositivoBloqueado / DispositivoInactivo (errores del aula)."""
    def cerrar_sesion_alumno(self, sesion_id: str, momento: int, motivo: str) -> None: ...


# --------------------------------------------------------------------- evaluación (MOD-010)

class Evaluacion(Protocol):
    def preparar_asignacion(self, sesion_id: str, curso_ref: str, objeto_ref: str, personas: list[str]) -> str:
        """Pide a MOD-010 la asignación de una actividad lanzada en clase; devuelve su referencia ('' si no existe aún)."""
    def intentos_abiertos(self, curso_ref: str, personas: list[str]) -> int: ...


# ------------------------------------------------------------ plataforma (MOD-015) y auditoría (MOD-019)

class Reloj(Protocol):
    def ahora_ms(self) -> int:
        """La marca autoritativa la pone el nodo (BR-062); ningún dato académico usa el reloj del dispositivo."""


class Auditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. `extra` admite motivo, resultado, dispositivo_id y evento_id."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "",
                  anterior: dict | None = None, nuevo: dict | None = None, **extra) -> None: ...


class Outbox(Protocol):
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None: ...


# ----------------------------------------------------------------------- autorización

@dataclass(frozen=True)
class Actor:
    """Quien actúa. Con sesión (MOD-001) lo construye la autenticación; sin ella (Q-34) lo declara el cliente."""

    id: str
    rotulo: str = ""
    nivel: int = 2            # 1 alumno · 2 personal · 3 administración (m01_rol.nivel)
    autenticado: bool = False
    dispositivo: str = ""
    sesion_usuario_id: str = ""
    principal: Any = None     # el Principal de MOD-001 cuando hay sesión JWT (lo evalúa el adaptador, nunca el dominio)


class Autorizacion(Protocol):
    def exigir(self, actor: Actor, permiso: str, sesion: dict | None = None) -> None:
        """Lanza SinPermiso si el actor no puede ejecutar la función que exige `permiso` (classroom.*).
        Con `sesion` comprueba además que el actor sea su profesor titular o la administración (007-10)."""


# ---------------------------------------------------------- tiempo real (Django Channels)

class TiempoReal(Protocol):
    """Avisa a las pantallas conectadas de que algo cambió en la sesión. NUNCA lleva contenido académico: sólo
    qué cambió; el cliente pide el estado por HTTP. Se emite cuando la transacción del caso de uso se confirma,
    no antes: quien recibe el aviso ya puede leer el hecho."""

    def cambio(self, sesion_id: str, que: str, carga: dict | None = None, *, conteo: bool = False) -> None:
        """`que`: selector · controles · distribucion · aviso · presencia · codigo · sesion · resultados · entregas · ayuda.
        Con `conteo` reenvía además el número de conectados a la pantalla del profesor."""


class Limitador(Protocol):
    """Freno a los intentos repetidos de unirse con un código equivocado (007-10)."""

    def registrar_fallo(self, clave: str, ahora: int) -> None: ...
    def bloqueado(self, clave: str, ahora: int) -> int:
        """Milisegundos que faltan para poder reintentar; 0 si no está bloqueado."""
    def olvidar(self, clave: str) -> None: ...


# ------------------------------------------------------------------------ repositorio

class RepositorioSesiones(Protocol):
    """El cajón de MOD-007. Trabaja con dicts planos para que los casos de uso no dependan del ORM."""

    # sesiones
    def crear_sesion(self, datos: dict) -> dict: ...
    def sesion(self, sesion_id: str) -> dict | None: ...
    def sesion_por_codigo(self, codigo: str) -> dict | None: ...
    def sesiones(self, estado: str | None = None, grupo_id: str | None = None, profesor_id: str | None = None) -> list[dict]: ...
    def sesiones_en_estado(self, *estados: str) -> list[dict]: ...
    def ultima_actividad(self, sesion_id: str) -> int:
        """El instante más reciente de cualquier cosa que ocurrió en la sesión (acción del profesor, latido o entrega)."""
    def sesion_abierta_de(self, profesor_id: str) -> dict | None: ...
    def sesion_activa_del_grupo(self, grupo_id: str) -> dict | None: ...
    def codigo_ocupado(self, codigo: str) -> bool: ...
    def actualizar_sesion(self, sesion_id: str, **campos) -> dict: ...
    def cerradas_antes_de(self, momento: int) -> list[dict]: ...
    # participantes
    def participantes(self, sesion_id: str) -> list[dict]: ...
    def participante(self, participante_id: str) -> dict | None: ...
    def participante_de(self, sesion_id: str, persona_id: str) -> dict | None: ...
    def crear_participante(self, datos: dict) -> dict: ...
    def actualizar_participante(self, participante_id: str, **campos) -> dict: ...
    def registrar_presencia(self, participante_id: str, estado: str, momento: int, dispositivo: str = "", detalle: str = "") -> None: ...
    def conectados_maximo(self, sesion_id: str) -> int: ...
    def conteo_participantes(self, sesion_id: str) -> dict:
        """{total, conectados, reconectando, esperando, salieron} por estado."""
    # selector
    def selector_vigente(self, sesion_id: str) -> dict | None: ...
    def declarar_selector(self, sesion_id: str, datos: dict, momento: int) -> dict: ...
    def total_selectores(self, sesion_id: str) -> int: ...
    # controles
    def controles_abiertos(self, sesion_id: str) -> list[dict]: ...
    def abrir_control(self, sesion_id: str, tipo: str, momento: int, actor: str, motivo: str = "") -> dict: ...
    def cerrar_control(self, sesion_id: str, tipo: str, momento: int, actor: str) -> dict | None: ...
    def cerrar_controles(self, sesion_id: str, momento: int, actor: str) -> int: ...
    # distribuciones
    def distribuciones(self, sesion_id: str, abiertas: bool | None = None) -> list[dict]: ...
    def distribucion(self, distribucion_id: str) -> dict | None: ...
    def crear_distribucion(self, datos: dict, participantes: list[str]) -> dict: ...
    def confirmar_entrega(self, distribucion_id: str, participante_id: str, momento: int, estado: str) -> dict: ...
    def cerrar_distribucion(self, distribucion_id: str, momento: int) -> dict: ...
    def actualizar_distribucion(self, distribucion_id: str, **campos) -> dict: ...
    def sumar_pausa(self, sesion_id: str, pausa_ms: int) -> int:
        """Suma `pausa_ms` a `pausada_ms` de las distribuciones abiertas (el cronómetro estuvo congelado)."""
    # intentos (provisional en MOD-007 hasta que MOD-010 tenga dueño)
    def intentos(self, distribucion_id: str, participante_id: str | None = None) -> list[dict]: ...
    def intentos_de_sesion(self, sesion_id: str, estado: str | None = None) -> list[dict]: ...
    def intento(self, intento_id: str) -> dict | None: ...
    def crear_intento(self, datos: dict) -> dict: ...
    def actualizar_intento(self, intento_id: str, **campos) -> dict: ...
    def entregas_pendientes_de(self, sesion_id: str, participante_id: str) -> list[dict]: ...
    # avisos y resumen
    def crear_aviso(self, datos: dict) -> dict: ...
    def avisos(self, sesion_id: str, participante_id: str | None = None, desde: int | None = None, limite: int = 20) -> list[dict]: ...
    def guardar_resumen(self, sesion_id: str, resumen: dict) -> dict: ...
    def resumen(self, sesion_id: str) -> dict | None: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción por caso de uso: el hecho, su auditoría y su evento se confirman juntos."""

    sesiones: RepositorioSesiones
    tiempo_real: TiempoReal
    outbox: Outbox
    auditoria: Auditoria
    identidad: Identidad
    dispositivos: Dispositivos
    evaluacion: Evaluacion

    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...
