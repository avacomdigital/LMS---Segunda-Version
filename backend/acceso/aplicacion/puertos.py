"""
Puertos (interfaces) que la capa de aplicación necesita. Los adaptadores viven en
`infraestructura/` y pueden cambiarse (Django ORM → SQLAlchemy, Argon2 → otro
hasher) sin tocar dominio ni casos de uso.
"""
from __future__ import annotations

from typing import Iterable, Protocol

from ..dominio.entidades import (
    AutorizacionTemporal,
    Credencial,
    Dispositivo,
    EventoSalida,
    Grupo,
    Identificador,
    IntentoAcceso,
    MiembroGrupo,
    Organizacion,
    Permiso,
    Persona,
    PoliticaCredencial,
    Rol,
    Sesion,
    Usuario,
    UsuarioPermiso,
    UsuarioRol,
)
from ..dominio.valores import Alcance, Menu, PapelGrupo, TipoIdentificador


class RepositorioOrganizaciones(Protocol):
    def unica(self) -> Organizacion | None: ...
    def guardar(self, organizacion: Organizacion) -> None: ...


class RepositorioPoliticas(Protocol):
    def por_organizacion(self, organizacion_id: str) -> list[PoliticaCredencial]: ...
    def por_perfil(self, organizacion_id: str, perfil: Menu) -> PoliticaCredencial | None:
        """La política general del perfil (sin nivel educativo)."""
    def por_nivel(self, organizacion_id: str, perfil: Menu, nivel_clave: str) -> PoliticaCredencial | None:
        """La excepción del perfil para un nivel educativo concreto (BR-024), si existe."""
    def por_id(self, politica_id: str) -> PoliticaCredencial | None: ...
    def guardar(self, politica: PoliticaCredencial) -> None: ...


class RepositorioPermisos(Protocol):
    def listar(self) -> list[Permiso]: ...
    def obtener(self, codigo: str) -> Permiso | None: ...
    def guardar(self, permiso: Permiso) -> None: ...


class RepositorioRoles(Protocol):
    def por_id(self, rol_id: str) -> Rol | None: ...
    def por_codigo(self, organizacion_id: str, codigo: str) -> Rol | None:
        """Rol propio de la organización o, en su defecto, plantilla de sistema."""
    def listar(self, organizacion_id: str) -> list[Rol]: ...
    def guardar(self, rol: Rol) -> None: ...


class RepositorioUsuarios(Protocol):
    def por_id(self, usuario_id: str) -> Usuario | None: ...
    def por_identificador(self, valor_hmac: str) -> tuple[Usuario, Identificador] | None: ...
    def guardar(self, usuario: Usuario) -> None: ...
    def persona(self, usuario_id: str) -> Persona | None: ...
    def guardar_persona(self, persona: Persona) -> None: ...
    def identificadores(self, usuario_id: str) -> list[Identificador]: ...
    def existe_identificador(self, valor_hmac: str, excepto_usuario: str | None = None) -> bool: ...
    def reemplazar_identificadores(self, usuario_id: str, identificadores: list[Identificador]) -> None: ...
    def permisos_adicionales(self, usuario_id: str) -> list[UsuarioPermiso]: ...
    def guardar_permiso_adicional(self, permiso: UsuarioPermiso) -> None: ...
    def asignaciones(self, usuario_id: str) -> list[UsuarioRol]:
        """Roles asignados a la persona con su alcance y vigencia (m01_persona_rol)."""
    def guardar_asignacion(self, asignacion: UsuarioRol) -> None: ...
    def listar(self, organizacion_id: str, alcance: Alcance, actor_id: str, grupos_docente: Iterable[str],
               nivel_maximo: int, grupo_id: str | None = None, rol_codigo: str | None = None,
               estado: str | None = None) -> list[Usuario]: ...


class RepositorioCredenciales(Protocol):
    def activa(self, usuario_id: str) -> Credencial | None: ...
    def historial(self, usuario_id: str, cantidad: int) -> list[Credencial]: ...
    def guardar(self, credencial: Credencial) -> None: ...
    def desactivar(self, usuario_id: str, ahora: int) -> None: ...


class RepositorioGrupos(Protocol):
    def por_id(self, grupo_id: str) -> Grupo | None: ...
    def listar(self, organizacion_id: str, solo_ids: Iterable[str] | None = None) -> list[Grupo]: ...
    def guardar(self, grupo: Grupo) -> None: ...
    def miembros(self, grupo_id: str, vigentes: bool = True) -> list[MiembroGrupo]: ...
    def membresias(self, usuario_id: str, vigentes: bool = True) -> list[MiembroGrupo]: ...
    def guardar_miembro(self, miembro: MiembroGrupo) -> None: ...
    def ids_grupos(self, usuario_id: str, papel: PapelGrupo | None, ahora: int) -> frozenset[str]: ...
    def ids_grupos_por_nivel(self, organizacion_id: str, nivel_clave: str) -> frozenset[str]:
        """Los grupos activos de un nivel educativo: lo que abre una asignación de rol con alcance LEVEL."""
    def nivel_de_usuario(self, usuario_id: str, ahora: int) -> str | None:
        """El nivel educativo del primer grupo vigente donde la persona es ESTUDIANTE (para BR-024)."""
    def politica_de_grupo(self, usuario_id: str, ahora: int) -> PoliticaCredencial | None:
        """La política del primer grupo vigente del usuario (como ESTUDIANTE) que tenga una propia."""


class RepositorioDispositivos(Protocol):
    def por_id(self, dispositivo_id: str) -> Dispositivo | None: ...
    def por_identificador(self, organizacion_id: str, identificador: str) -> Dispositivo | None: ...
    def listar(self, organizacion_id: str, solo_activos: bool = True) -> list[Dispositivo]: ...
    def guardar(self, dispositivo: Dispositivo) -> None: ...


class RepositorioSesiones(Protocol):
    def por_id(self, sesion_id: str) -> Sesion | None: ...
    def guardar(self, sesion: Sesion) -> None: ...
    def listar(self, organizacion_id: str, usuario_id: str | None, solo_activas: bool, ahora: int,
               usuarios_permitidos: Iterable[str] | None = None) -> list[Sesion]: ...
    def abiertas_de_usuario(self, usuario_id: str, ahora: int) -> list[Sesion]:
        """Sesiones vigentes de la persona: para imponer la sesión única al abrir otra."""
    def abiertas_en_dispositivo(self, dispositivo_id: str, ahora: int) -> list[Sesion]:
        """Sesiones vigentes en la tableta: para imponer INV-011 (cero o una por dispositivo compartido)."""
    def revocar_de_usuario(self, usuario_id: str, motivo: str, ahora: int, excepto: str | None = None) -> int: ...


class RepositorioIntentos(Protocol):
    def registrar(self, intento: IntentoAcceso) -> None: ...
    def recientes(self, usuario_id: str, desde: int) -> list[IntentoAcceso]:
        """Del más reciente al más antiguo."""
    def fallos_de_autorizacion(self, autorizacion_id: str) -> int: ...


class RepositorioAutorizaciones(Protocol):
    def por_id(self, autorizacion_id: str) -> AutorizacionTemporal | None: ...
    def guardar(self, autorizacion: AutorizacionTemporal) -> None: ...
    def canjeables_por_codigo(self, organizacion_id: str, ahora: int) -> list[AutorizacionTemporal]: ...
    def listar(self, organizacion_id: str, usuario_id: str | None, solo_vigentes: bool, ahora: int,
               usuarios_permitidos: Iterable[str] | None = None) -> list[AutorizacionTemporal]: ...


class Outbox(Protocol):
    def publicar(self, evento: EventoSalida) -> None: ...


class RegistroAuditoria(Protocol):
    """MOD-019: el asiento queda en la misma transacción que el hecho. `extra` admite motivo, resultado, dispositivo_id y evento_id."""

    def registrar(self, actor_id: str, accion: str, tabla: str = "", objeto_id: str = "", nuevo=None, anterior=None, **extra) -> None: ...


class UnidadDeTrabajo(Protocol):
    """Una transacción. Todo lo que se escribe dentro se confirma o se deshace junto.

    En lenguaje llano: es **la carpeta de trabajo de una gestión**.

    Cuando el docente matricula a un estudiante nuevo no ocurre «una cosa»: se crea
    la cuenta, se guardan sus datos personales cifrados, su código, su PIN, su
    inscripción al grupo, el apunte de auditoría y el aviso para sincronizar. Son
    siete escrituras distintas. Si la quinta falla (por ejemplo, el código ya era de
    otra persona), lo que NO puede pasar es quedarnos con media matrícula: un
    estudiante sin PIN, o un PIN sin estudiante.

    La Unidad de Trabajo es la promesa de que eso no ocurre: se abre al empezar la
    gestión, se hacen todas las escrituras dentro, y al cerrarse **o se guarda todo,
    o no se guarda nada**. Como la carpeta de una matrícula en secretaría: se
    entrega completa y firmada, o se devuelve entera y es como si nunca hubiera
    pasado.

    Los atributos de abajo son los cajones de esa carpeta: uno por cada cosa que el
    módulo sabe guardar (usuarios, credenciales, grupos, sesiones...). Cada cajón
    sabe leer y escribir lo suyo; el caso de uso los usa sin saber si detrás hay
    SQLite, PostgreSQL o un archivo. Por eso esto es una *interfaz* (un contrato de
    lo que se puede pedir) y no el código que lo hace de verdad: ese vive en
    `infraestructura/unidad_trabajo.py` y puede cambiarse sin tocar nada de aquí.
    """

    organizaciones: RepositorioOrganizaciones
    politicas: RepositorioPoliticas
    permisos: RepositorioPermisos
    roles: RepositorioRoles
    usuarios: RepositorioUsuarios
    credenciales: RepositorioCredenciales
    grupos: RepositorioGrupos
    dispositivos: RepositorioDispositivos
    sesiones: RepositorioSesiones
    intentos: RepositorioIntentos
    autorizaciones: RepositorioAutorizaciones
    outbox: Outbox
    auditoria: RegistroAuditoria

    # Estas dos son las que abren y cierran la carpeta. Python las llama solo al
    # entrar y al salir de un bloque `with`; el caso de uso nunca las invoca a mano:
    #
    #     with self.s.uow() as uow:      # <- se abre la carpeta
    #         uow.usuarios.guardar(...)  #    escrituras dentro
    #         uow.credenciales.guardar(...)
    #     # <- al salir bien, se confirma todo; si hubo un error, se deshace todo
    def __enter__(self) -> "UnidadDeTrabajo": ...
    def __exit__(self, tipo, valor, traza) -> None: ...


class FabricaUoW(Protocol):
    def __call__(self) -> UnidadDeTrabajo: ...


class Hasher(Protocol):
    """Argon2id en producción. La interfaz no lo sabe."""

    def hash(self, secreto: str) -> str: ...
    def verificar(self, hash_guardado: str, secreto: str) -> bool: ...
    def necesita_rehash(self, hash_guardado: str) -> bool: ...


class Cifrador(Protocol):
    """AES-256-GCM para recuperar; HMAC-SHA-256 para buscar."""

    def cifrar(self, texto: str, contexto: str) -> str: ...
    def descifrar(self, cifrado: str, contexto: str) -> str: ...
    def indice(self, texto_normalizado: str) -> str: ...
    def claves_derivadas(self) -> bool: ...


class EmisorTokens(Protocol):
    def emitir(self, claims: dict) -> str: ...
    def leer(self, token: str) -> dict:
        """Lanza SesionInvalida / SesionExpirada."""


class Reloj(Protocol):
    def ahora_ms(self) -> int: ...


class Azar(Protocol):
    def token_url(self, octetos: int = 32) -> str: ...
    def pin(self, digitos: int) -> str: ...
    def password(self, longitud: int) -> str: ...
    def hash_rapido(self, texto: str) -> str:
        """SHA-256 en hex, para secretos de alta entropía."""
