"""Errores del dominio. La capa HTTP los traduce a códigos; el dominio sólo los lanza."""
from __future__ import annotations


class ErrorAcceso(Exception):
    codigo = "error_acceso"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorAcceso):
    """Los datos recibidos no cumplen las reglas del dominio."""
    codigo = "datos_invalidos"
    http = 400


class SecretoDebil(ErrorAcceso):
    """El PIN o la contraseña no cumple la política de credenciales."""
    codigo = "secreto_debil"
    http = 400


class IdentificadorDuplicado(ErrorAcceso):
    """Ese identificador ya pertenece a otra persona."""
    codigo = "identificador_duplicado"
    http = 400


class PoliticaInvalida(ErrorAcceso):
    """La política de credenciales no es coherente."""
    codigo = "politica_invalida"
    http = 400


class CredencialesInvalidas(ErrorAcceso):
    """Identificador o clave incorrectos."""
    codigo = "credenciales_invalidas"
    http = 401


class SesionRequerida(ErrorAcceso):
    """Hace falta iniciar sesión."""
    codigo = "sesion_requerida"
    http = 401


class SesionInvalida(ErrorAcceso):
    """La sesión no es válida."""
    codigo = "sesion_invalida"
    http = 401


class SesionExpirada(SesionInvalida):
    """La sesión caducó."""
    codigo = "sesion_expirada"


class SesionRevocada(SesionInvalida):
    """La sesión fue cerrada."""
    codigo = "sesion_revocada"


class SesionInactiva(SesionInvalida):
    """La sesión se cerró por inactividad (FUN-009)."""
    codigo = "sesion_inactiva"


class SesionCerradaEnOtroDispositivo(SesionInvalida):
    """La sesión se cerró porque la persona entró desde otro dispositivo (sesión única, INV-011)."""
    codigo = "sesion_cerrada_otro_dispositivo"


class SinPermiso(ErrorAcceso):
    """No tiene permiso para esta operación."""
    codigo = "sin_permiso"
    http = 403


class DebeCambiarCredencial(SinPermiso):
    """Debe cambiar su clave provisional antes de continuar."""
    codigo = "debe_cambiar_credencial"


class SesionTemporalLimitada(SinPermiso):
    """Una sesión de acceso temporal sólo sirve para rendir la evaluación."""
    codigo = "sesion_temporal_limitada"


class DispositivoBloqueado(SinPermiso):
    """La tableta está bloqueada por el profesor o el administrador (MOD-009): no abre sesión."""
    codigo = "dispositivo_bloqueado"


class NoEncontrado(ErrorAcceso):
    """No existe o está fuera de su alcance."""
    codigo = "no_encontrado"
    http = 404


class Conflicto(ErrorAcceso):
    """La operación choca con el estado actual."""
    codigo = "conflicto"
    http = 409


class YaInstalado(Conflicto):
    """El nodo ya tiene una organización instalada."""
    codigo = "ya_instalado"


class UsuarioBloqueado(ErrorAcceso):
    """El usuario está bloqueado."""
    codigo = "usuario_bloqueado"
    http = 423
