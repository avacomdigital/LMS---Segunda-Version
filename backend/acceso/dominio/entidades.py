"""
Entidades del dominio de acceso. Son dataclasses planas: el ORM las mapea en
`infraestructura/repositorios.py`, nunca al revés.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .valores import (
    Alcance,
    ClaseSesion,
    EstadoUsuario,
    Menu,
    PapelGrupo,
    ResultadoIntento,
    TipoAutorizacion,
    TipoDispositivo,
    TipoIdentificador,
    TipoSecreto,
)


@dataclass
class Organizacion:
    id: str
    codigo: str
    nombre: str
    pais: str
    idioma: str
    locale: str
    zona_horaria: str
    creado_en: int


@dataclass
class PoliticaCredencial:
    """El **reglamento de acceso que cada colegio elige**, escrito en una fila.

    Es la respuesta a «¿cómo entra la gente aquí?», y cada institución la contesta
    distinto. Un colegio de primaria quiere que sus niños entren con el código
    estudiantil y cuatro números; una universidad quiere documento y contraseña
    larga. En vez de programar dos versiones del software, se guarda la respuesta
    en esta tabla y el mismo código se comporta como pida cada sitio.

    Hay una política por **perfil**: una para estudiantes, otra para docentes y
    otra para administración. Por eso el estudiante puede entrar con PIN mientras
    el profesor necesita contraseña con mayúscula y símbolo: son dos filas
    distintas de esta misma tabla, no dos programas distintos.

    Manda sobre cinco cosas del día a día:
      · con QUÉ se identifica uno (código, documento, correo o lo que sea)
      · qué CLASE de clave usa (PIN de números o contraseña)
      · qué tan DIFÍCIL debe ser esa clave (largo, mayúsculas, símbolos...)
      · cuántos ERRORES se toleran antes de bloquear, y por cuánto tiempo
      · cuánto DURA la sesión antes de volver a pedir la clave
    """

    id: str
    organizacion_id: str
    perfil: Menu                            # a quién le aplica: student / teacher / admin / reports / technician
    tipo_identificador: TipoIdentificador   # con qué se identifica: DNI, código estudiantil, correo
    tipo_secreto: TipoSecreto               # PIN (sólo números), PASSWORD (contraseña) o AVATAR (código gráfico)
    longitud_minima: int                    # 6 para un PIN de aula, 8 para docentes, 12 para administración
    exige_mayuscula: bool                   # las cuatro «exige_*» sólo tienen sentido con contraseña;
    exige_minuscula: bool                   # en un PIN se ignoran, porque un PIN es sólo dígitos
    exige_digito: bool
    exige_simbolo: bool
    intentos_maximos: int                   # cuántas veces puede equivocarse antes de quedar bloqueado
    ventana_intentos_min: int               # en cuántos minutos se cuentan esos errores (pasado ese rato, borrón y cuenta nueva)
    bloqueo_minutos: int                    # cuánto dura el castigo. El docente puede levantarlo antes
    duracion_sesion_min: int                # 240 = cuatro horas: más que una jornada de clase
    vigencia_credencial_dias: int | None    # cada cuánto caduca la clave. None = no caduca nunca
    permite_acceso_temporal: bool           # si a este perfil se le puede dar el «pase de emergencia» de examen
    creado_en: int
    actualizado_en: int
    nivel_clave: str | None = None          # None = política del perfil; con valor = excepción para ese nivel educativo (BR-024)
    inactividad_min: int = 20               # FUN-009: minutos sin actividad tras los que la sesión se cierra sola

    def validar(self) -> None:
        """Impide que un colegio se configure a sí mismo un reglamento absurdo.

        El administrador puede ajustar estos números desde la pantalla de
        administración, y podría por descuido dejar la puerta abierta de par en par
        (un PIN de 1 dígito) o cerrarla con llave (bloquear al primer error). Estas
        comprobaciones son el suelo por debajo del cual no se puede bajar: si algo
        no cuadra, el cambio se rechaza y el reglamento anterior sigue vigente.
        """
        if self.tipo_secreto is TipoSecreto.AVATAR:
            if self.perfil is not Menu.STUDENT:
                raise ValueError("El avatar sólo se admite para estudiantes (BR-024).")
        elif self.longitud_minima < 4:
            raise ValueError("La longitud mínima no puede ser menor que 4.")
        if self.tipo_secreto is TipoSecreto.PIN and not 4 <= self.longitud_minima <= 8:
            raise ValueError("Un PIN tiene entre 4 y 8 dígitos.")
        if self.tipo_secreto is TipoSecreto.PASSWORD and self.longitud_minima < 8:
            raise ValueError("Una contraseña tiene al menos 8 caracteres.")
        if self.intentos_maximos < 3:
            raise ValueError("Permita al menos 3 intentos antes de bloquear.")
        if self.duracion_sesion_min < 5 or self.duracion_sesion_min > 24 * 60:
            raise ValueError("La sesión dura entre 5 minutos y 24 horas.")
        if self.inactividad_min < 5 or self.inactividad_min > self.duracion_sesion_min:
            raise ValueError("La inactividad se mide en minutos: al menos 5 y nunca más que la duración de la sesión.")
        if self.bloqueo_minutos < 1 or self.ventana_intentos_min < 1:
            raise ValueError("Ventana y bloqueo se expresan en minutos mayores que cero.")

    def admite_identificador(self, tipo: TipoIdentificador) -> bool:
        """¿Sirve este tipo de identificador para entrar en este colegio?

        Un estudiante puede tener registrados su código y su documento, pero si el
        colegio dijo «aquí se entra con el código», el documento no abre la puerta
        aunque sea suyo y sea correcto. `CUALQUIERA` es el comodín para los
        colegios que prefieren aceptar todo lo que la persona tenga registrado.
        """
        return self.tipo_identificador is TipoIdentificador.CUALQUIERA or self.tipo_identificador is tipo


@dataclass
class Permiso:
    codigo: str
    modulo: str
    descripcion: str
    alcance_maximo: Alcance


@dataclass
class RolPermiso:
    permiso_codigo: str
    alcance: Alcance


@dataclass
class Rol:
    id: str
    organizacion_id: str | None
    codigo: str
    nombre: str
    menu_principal: Menu
    nivel: int
    es_sistema: bool
    creado_en: int
    permisos: list[RolPermiso] = field(default_factory=list)


@dataclass
class Usuario:
    id: str
    organizacion_id: str
    rol_id: str
    estado: EstadoUsuario
    alias: str
    idioma: str
    creado_en: int
    actualizado_en: int
    creado_por: str | None = None
    ultimo_acceso_en: int | None = None
    # Admisión nominal (JRN-007, MSG-023): el profesor deja entrar a un alumno «por su nombre» y se
    # vincula después con la persona definitiva. Mientras tanto la cuenta es provisional.
    provisional: bool = False
    vinculado_a: str | None = None

    @property
    def activo(self) -> bool:
        return self.estado is EstadoUsuario.ACTIVO


@dataclass
class Persona:
    usuario_id: str
    nombres: str
    apellidos: str
    pais: str
    fecha_nacimiento: str | None = None
    telefono: str | None = None
    actualizado_en: int = 0


@dataclass
class Identificador:
    """Identificador externo (DEC-048): matrícula, documento o clave emitida por la instalación."""

    id: str
    usuario_id: str
    tipo: TipoIdentificador
    valor: str
    es_login: bool
    creado_en: int
    verificado_en: int | None = None
    emisor: str = ""               # institución o instalación que lo emitió (código de la organización por defecto)
    principal: bool = False        # sólo uno por persona: el que se muestra y el que vincula entre nodos
    retirado_en: int | None = None  # CV-05: nada se borra; un identificador que deja de valer se retira

    @property
    def vigente(self) -> bool:
        return self.retirado_en is None


@dataclass
class Credencial:
    id: str
    usuario_id: str
    tipo: TipoSecreto
    hash: str
    activa: bool
    debe_cambiar: bool
    creado_en: int
    expira_en: int | None = None
    sustituida_en: int | None = None
    creado_por: str | None = None

    def expirada(self, ahora: int) -> bool:
        return self.expira_en is not None and ahora >= self.expira_en


@dataclass
class UsuarioPermiso:
    id: str
    usuario_id: str
    permiso_codigo: str
    alcance: Alcance
    otorgado_por: str
    motivo: str
    vigente_desde: int
    vigente_hasta: int | None = None
    revocado_en: int | None = None

    def vigente(self, ahora: int) -> bool:
        if self.revocado_en is not None:
            return False
        if ahora < self.vigente_desde:
            return False
        return self.vigente_hasta is None or ahora < self.vigente_hasta


@dataclass
class UsuarioRol:
    """Asignación de un rol a una persona con alcance concreto y vigencia (m01_persona_rol del Maestro, BR-021).

    Una persona puede tener varios roles vigentes, pero en cada sesión trabaja con uno solo,
    elegido al entrar. El alcance de la asignación acota al del rol: un «Coordinador» asignado
    con alcance LEVEL=secundaria no llega a primaria aunque su rol diga ORGANIZATION.
    """

    id: str
    usuario_id: str
    rol_id: str
    alcance_tipo: Alcance          # ORGANIZATION (toda la instalación), LEVEL (un nivel) o ASSIGNED_GROUPS (un grupo)
    desde: int
    alcance_id: str | None = None  # nivel_clave o grupo_id; nulo cuando es toda la organización
    hasta: int | None = None
    asignado_por: str | None = None
    revocado_en: int | None = None

    def vigente(self, ahora: int) -> bool:
        if self.revocado_en is not None or ahora < self.desde:
            return False
        return self.hasta is None or ahora < self.hasta


@dataclass
class Grupo:
    id: str
    organizacion_id: str
    codigo: str
    nombre: str
    periodo: str
    activo: bool
    creado_en: int
    politica_credencial_id: str | None = None
    nivel_clave: str | None = None  # preescolar · primaria · secundaria · bachillerato · preuniversitario


@dataclass
class MiembroGrupo:
    id: str
    grupo_id: str
    usuario_id: str
    papel: PapelGrupo
    desde: int
    hasta: int | None = None

    def vigente(self, ahora: int) -> bool:
        return self.hasta is None or ahora < self.hasta


@dataclass
class Dispositivo:
    """Lo que el login necesita saber de un equipo. El dueño es MOD-009 (`device_manager`); aquí es una
    lectura por el puerto `RepositorioDispositivos`, con los nombres que usa este módulo."""

    id: str
    organizacion_id: str
    identificador: str
    nombre: str
    tipo: TipoDispositivo
    activo: bool
    registrado_en: int
    ultimo_visto_en: int
    bloqueado: bool = False


@dataclass
class Sesion:
    id: str
    usuario_id: str
    clase: ClaseSesion
    emitida_en: int
    expira_en: int
    dispositivo_id: str | None = None
    ultimo_uso_en: int | None = None
    revocada_en: int | None = None
    motivo_revocacion: str | None = None
    evaluacion_ref: str | None = None
    rol_id: str | None = None  # el rol EFECTIVO de esta sesión (BR-021): uno solo, elegido al entrar

    def vigente(self, ahora: int) -> bool:
        return self.revocada_en is None and ahora < self.expira_en

    def inactiva(self, ahora: int, inactividad_min: int) -> bool:
        """FUN-009: la sesión superó el tiempo de inactividad configurado."""
        ultimo = self.ultimo_uso_en or self.emitida_en
        return ahora - ultimo > inactividad_min * 60_000


@dataclass
class IntentoAcceso:
    identificador_hmac: str
    resultado: ResultadoIntento
    motivo: str
    momento: int
    usuario_id: str | None = None
    dispositivo_id: str | None = None
    autorizacion_id: str | None = None
    id: int | None = None


@dataclass
class AutorizacionTemporal:
    id: str
    usuario_id: str
    otorgada_por: str
    tipo: TipoAutorizacion
    secreto_hash: str
    creada_en: int
    expira_en: int
    motivo: str
    dispositivo_id: str | None = None
    evaluacion_ref: str | None = None
    usada_en: int | None = None
    revocada_en: int | None = None
    sesion_id: str | None = None

    def canjeable(self, ahora: int) -> bool:
        return self.usada_en is None and self.revocada_en is None and ahora < self.expira_en


@dataclass
class EventoSalida:
    agregado_tipo: str
    agregado_id: str
    tipo_evento: str
    carga: dict[str, Any]
    creado_en: int
    id: int | None = None
    publicado_en: int | None = None
    intentos: int = 0


@dataclass(frozen=True)
class Concesion:
    """Un permiso efectivo del actor: el alcance máximo entre el rol y los adicionales."""

    permiso_codigo: str
    alcance: Alcance
    origen: str  # "rol" | "adicional"
    vigente_hasta: int | None = None


@dataclass(frozen=True)
class Principal:
    """Quién actúa. Lo construye la autenticación y lo consumen las políticas y los casos de uso."""

    usuario_id: str
    organizacion_id: str
    rol_id: str
    rol_codigo: str
    menu: Menu
    nivel: int
    sesion_id: str
    clase_sesion: ClaseSesion
    debe_cambiar_credencial: bool
    dispositivo_id: str | None = None
    evaluacion_ref: str | None = None

    # DRF sólo necesita esto para tratar al portador como autenticado.
    is_authenticated = True
    is_anonymous = False
