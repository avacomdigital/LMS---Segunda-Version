"""
Value Objects del módulo de acceso. Validan en el constructor y no dependen de nada.

Este archivo, como todo `acceso/dominio`, no importa Django ni DRF: una prueba
de arquitectura lo garantiza (tests/test_arquitectura.py).
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from enum import Enum


class Alcance(str, Enum):
    """Hasta dónde llega un permiso. Es una regla de negocio, no una tabla.

    Corresponde a los cuatro alcances del Documento Maestro (MOD-001):
    propio → SELF · grupo → ASSIGNED_GROUPS · nivel educativo → LEVEL · instalación → ORGANIZATION.
    """

    SELF = "SELF"
    ASSIGNED_GROUPS = "ASSIGNED_GROUPS"
    LEVEL = "LEVEL"
    ORGANIZATION = "ORGANIZATION"

    @property
    def orden(self) -> int:
        return {"SELF": 1, "ASSIGNED_GROUPS": 2, "LEVEL": 3, "ORGANIZATION": 4}[self.value]

    def cubre(self, requerido: "Alcance") -> bool:
        return self.orden >= requerido.orden

    @classmethod
    def parse(cls, texto: str) -> "Alcance":
        try:
            return cls(str(texto or "").strip().upper())
        except ValueError:
            raise ValueError(f"Alcance desconocido: {texto!r}. Use SELF, ASSIGNED_GROUPS, LEVEL u ORGANIZATION.")

    @classmethod
    def minimo(cls, a: "Alcance", b: "Alcance") -> "Alcance":
        return a if a.orden <= b.orden else b


class Menu(str, Enum):
    """El menú que abre el cliente. Uno por rol de sistema del Documento Maestro (los cinco roles)."""

    STUDENT = "student"        # Alumno
    TEACHER = "teacher"        # Profesor
    ADMIN = "admin"            # Administrador
    REPORTS = "reports"        # Reportes: sólo lectura
    TECHNICIAN = "technician"  # Técnico AVACOM: sin datos personales


class NivelEducativo(str, Enum):
    """Los cinco niveles del Documento Maestro. La configuración de acceso puede variar por nivel (BR-024)."""

    PREESCOLAR = "preescolar"
    PRIMARIA = "primaria"
    SECUNDARIA = "secundaria"
    BACHILLERATO = "bachillerato"
    PREUNIVERSITARIO = "preuniversitario"


class TipoIdentificador(str, Enum):
    """Identificadores externos (DEC-048): vinculan a la misma persona entre nodos."""

    DNI = "DNI"                              # documento nacional (CURP, cédula, tarjeta de identidad)
    CODIGO_ESTUDIANTIL = "CODIGO_ESTUDIANTIL"  # matrícula emitida por la institución
    CLAVE_INSTALACION = "CLAVE_INSTALACION"    # la emite el nodo cuando la institución no da matrícula (DEC-049)
    EMAIL = "EMAIL"
    CUALQUIERA = "CUALQUIERA"  # sólo válido en la política


class TipoSecreto(str, Enum):
    """Credenciales del Documento Maestro: contraseña, clave corta (PIN) y avatar (código gráfico)."""

    PIN = "PIN"
    PASSWORD = "PASSWORD"
    AVATAR = "AVATAR"


class MotivoCierre(str, Enum):
    """Por qué se cerró una sesión. Alineado con m01_sesion_usuario.motivo_cierre del Documento Maestro."""

    PERSONA = "persona"                        # cerró sesión ella misma
    OTRO_DISPOSITIVO = "otro_dispositivo"      # abrió en otro aparato: sesión única por persona
    DISPOSITIVO_COMPARTIDO = "dispositivo_compartido"  # otra persona entró en esta tableta (INV-011)
    INACTIVIDAD = "inactividad"                # FUN-009
    RESTAURACION = "restauracion"              # el nodo se restauró desde un respaldo
    PROFESOR = "profesor"
    ADMINISTRADOR = "administrador"
    CREDENCIAL_CAMBIADA = "credencial_cambiada"
    CREDENCIAL_RESTABLECIDA = "credencial_restablecida"
    CREDENCIAL_RESTABLECIDA_PIN_MAESTRO = "credencial_restablecida_pin_maestro"  # RN-24: el profesor la restableció con el PIN maestro
    VISITA_RETIRADA = "visita_retirada"        # RN-45: la cuenta efímera de una visita pasó las 24 h
    ROL_CAMBIADO = "rol_cambiado"
    ESTADO_CUENTA = "estado_cuenta"
    DISPOSITIVO_BAJA = "dispositivo_baja"


class EstadoUsuario(str, Enum):
    ACTIVO = "ACTIVO"
    BLOQUEADO = "BLOQUEADO"
    SUSPENDIDO = "SUSPENDIDO"
    RETIRADO = "RETIRADO"


class PapelGrupo(str, Enum):
    ESTUDIANTE = "ESTUDIANTE"
    DOCENTE = "DOCENTE"


class ClaseSesion(str, Enum):
    NORMAL = "NORMAL"
    TEMPORAL = "TEMPORAL"
    VISITANTE = "VISITANTE"   # RN-40…47: entra sin identidad confirmada, con permisos mínimos (D-A4: clase de sesión, no un sexto rol)


class OrigenCuenta(str, Enum):
    """Cómo nació una cuenta (RB-03). Sirve para auditar y para que la administración sepa quién se registró con el PIN maestro."""

    INSTALACION = "INSTALACION"          # el primer administrador, creado al instalar el nodo
    IMPORTACION = "IMPORTACION"          # cargada por la administración (padrón o archivo)
    PROFESOR = "PROFESOR"                # la creó un profesor para su grupo
    AUTOALTA_ALUMNO = "AUTOALTA_ALUMNO"  # el propio alumno se registró en la tableta (RN-30)
    PIN_MAESTRO = "PIN_MAESTRO"          # el propio profesor se registró con el PIN maestro (RN-20)
    VISITANTE = "VISITANTE"              # cuenta efímera de una visita (RN-45)


class BloqueoAlcance(str, Enum):
    """Sobre qué recae el castigo por fallar la clave (RN-33): la cuenta o la tableta desde la que se prueba."""

    CUENTA = "CUENTA"
    DISPOSITIVO = "DISPOSITIVO"


class TipoAutorizacion(str, Enum):
    DISPOSITIVO = "DISPOSITIVO"
    CODIGO = "CODIGO"


class TipoDispositivo(str, Enum):
    TABLETA = "TABLETA"
    MASTER = "MASTER"
    OTRO = "OTRO"


class ResultadoIntento(str, Enum):
    EXITO = "EXITO"
    FALLO = "FALLO"
    BLOQUEADO = "BLOQUEADO"
    DESBLOQUEO = "DESBLOQUEO"
    TEMPORAL_EXITO = "TEMPORAL_EXITO"
    TEMPORAL_FALLO = "TEMPORAL_FALLO"
    ALTA = "ALTA"   # RB-17: una cuenta propia nacida desde la tableta; no cuenta como fallo ni como acierto, sólo para el tope por hora


def _enum(cls, texto, nombre):
    if isinstance(texto, cls):
        return texto
    try:
        return cls(str(texto or "").strip().upper() if cls is not Menu else str(texto or "").strip().lower())
    except ValueError:
        raise ValueError(f"{nombre} desconocido: {texto!r}.")


@dataclass(frozen=True)
class UserId:
    valor: str

    def __post_init__(self):
        try:
            uuid.UUID(str(self.valor))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("El identificador de usuario debe ser un UUID.")
        object.__setattr__(self, "valor", str(self.valor).lower())

    @classmethod
    def nuevo(cls) -> "UserId":
        return cls(str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class CountryCode:
    """ISO 3166-1 alpha-2: `CO`, `MX`, `US`."""

    valor: str

    def __post_init__(self):
        v = str(self.valor or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", v):
            raise ValueError("El país debe ser un código ISO 3166-1 alpha-2 (dos letras, p. ej. CO).")
        object.__setattr__(self, "valor", v)

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class LanguageCode:
    """ISO 639-1 (o 639-2 de tres letras): `es`, `en`, `fr`."""

    valor: str

    def __post_init__(self):
        v = str(self.valor or "").strip().lower()
        if not re.fullmatch(r"[a-z]{2,3}", v):
            raise ValueError("El idioma debe ser un código ISO 639 (p. ej. es, en).")
        object.__setattr__(self, "valor", v)

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class LocaleCode:
    """BCP 47 / RFC 5646 en su forma idioma[-REGIÓN]: `es-CO`, `en-US`."""

    valor: str

    def __post_init__(self):
        partes = str(self.valor or "").strip().replace("_", "-").split("-")
        if not partes or not re.fullmatch(r"[A-Za-z]{2,3}", partes[0]):
            raise ValueError("El locale debe seguir BCP 47 (p. ej. es-CO).")
        salida = [partes[0].lower()]
        for extra in partes[1:]:
            if re.fullmatch(r"[A-Za-z]{2}", extra):
                salida.append(extra.upper())
            elif re.fullmatch(r"[A-Za-z0-9]{3,8}", extra):
                salida.append(extra)
            else:
                raise ValueError("El locale debe seguir BCP 47 (p. ej. es-CO).")
        object.__setattr__(self, "valor", "-".join(salida))

    @property
    def idioma(self) -> LanguageCode:
        return LanguageCode(self.valor.split("-")[0])

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class PermissionCode:
    """`modulo.recurso.accion`, p. ej. `student.progress.read`."""

    valor: str

    def __post_init__(self):
        v = str(self.valor or "").strip().lower()
        if not re.fullmatch(r"[a-z_]+(\.[a-z_]+){1,3}", v):
            raise ValueError(f"Código de permiso inválido: {self.valor!r}.")
        object.__setattr__(self, "valor", v)

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class DocumentNumber:
    """Un identificador de persona con su tipo y su forma normalizada (la que se indexa con HMAC)."""

    tipo: TipoIdentificador
    valor: str

    def __post_init__(self):
        tipo = _enum(TipoIdentificador, self.tipo, "Tipo de identificador")
        if tipo is TipoIdentificador.CUALQUIERA:
            raise ValueError("CUALQUIERA sólo se usa en la política, no en un identificador.")
        v = str(self.valor or "").strip()
        if not v:
            raise ValueError("El identificador no puede estar vacío.")
        if tipo is TipoIdentificador.EMAIL:
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
                raise ValueError("El correo no tiene un formato válido.")
        elif len(v) > 64:
            raise ValueError("El identificador es demasiado largo.")
        object.__setattr__(self, "tipo", tipo)
        object.__setattr__(self, "valor", v)

    @property
    def normalizado(self) -> str:
        if self.tipo is TipoIdentificador.EMAIL:
            return self.valor.lower().replace(" ", "")
        return re.sub(r"[\s.\-]", "", self.valor).upper()

    @staticmethod
    def normalizar_entrada(texto: str) -> tuple[str, str]:
        """Para el login: devuelve (forma normalizada como documento, forma normalizada como email)."""
        t = str(texto or "").strip()
        return re.sub(r"[\s.\-]", "", t).upper(), t.lower().replace(" ", "")


@dataclass(frozen=True)
class Pin:
    valor: str

    def __post_init__(self):
        v = str(self.valor or "").strip()
        if not v.isdigit():
            raise ValueError("El PIN sólo admite dígitos.")
        object.__setattr__(self, "valor", v)

    def es_trivial(self) -> bool:
        v = self.valor
        if len(set(v)) == 1:
            return True
        asc = all(int(v[i + 1]) - int(v[i]) == 1 for i in range(len(v) - 1))
        desc = all(int(v[i]) - int(v[i + 1]) == 1 for i in range(len(v) - 1))
        if asc or desc:
            return True
        if len(v) % 2 == 0 and v[: len(v) // 2] == v[len(v) // 2:]:
            return True
        return v in {"123123", "112233", "121212", "696969", "159753", "147258"}


@dataclass(frozen=True)
class Avatar:
    """Código gráfico para preescolar (BR-024): el niño toca un dibujo, la app envía su código.

    Baja entropía, como un PIN: se guarda con Argon2id y lo protegen el bloqueo por
    intentos y que sólo esté habilitado en los niveles que el administrador decida.
    """

    valor: str

    def __post_init__(self):
        v = str(self.valor or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{2,31}", v):
            raise ValueError("El avatar es un código de 3 a 32 caracteres: letras, números y guiones.")
        object.__setattr__(self, "valor", v)


@dataclass(frozen=True)
class Password:
    valor: str

    def __post_init__(self):
        v = str(self.valor or "")
        if not v or v != v.strip():
            raise ValueError("La contraseña no puede estar vacía ni empezar o terminar con espacios.")
        if len(v) > 128:
            raise ValueError("La contraseña es demasiado larga.")

    @property
    def tiene_mayuscula(self) -> bool:
        return any(c.isupper() for c in self.valor)

    @property
    def tiene_minuscula(self) -> bool:
        return any(c.islower() for c in self.valor)

    @property
    def tiene_digito(self) -> bool:
        return any(c.isdigit() for c in self.valor)

    @property
    def tiene_simbolo(self) -> bool:
        return any(not c.isalnum() for c in self.valor)


def alias_clave(alias: str) -> str:
    """La forma con que se compara un alias dentro del grupo (RN-34): sin mayúsculas, sin tildes y con los espacios colapsados."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", str(alias or "")) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes).strip().casefold()


def sugerir_alias(primer_nombre: str, apellidos: str, ocupados: set[str]) -> str | None:
    """RN-34: si «Juan P.» ya existe en el grupo, pide una letra más del apellido («Juan Pé.») en vez de rechazar sin salida.
    Sin apellido no se puede inventar la letra: devuelve None y la pantalla pide que la escriba la persona."""
    apellido = (apellidos or "").split()[0] if (apellidos or "").strip() else ""
    for letras in range(2, len(apellido) + 1):
        candidato = f"{primer_nombre} {apellido[:letras]}" + ("." if letras < len(apellido) else "")
        if alias_clave(candidato) not in ocupados:
            return candidato
    return None
