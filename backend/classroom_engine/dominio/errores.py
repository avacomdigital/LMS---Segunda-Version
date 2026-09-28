"""Errores del dominio del aula. La capa HTTP los traduce a códigos; el dominio sólo los lanza."""
from __future__ import annotations


class ErrorAula(Exception):
    codigo = "error_aula"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorAula):
    """Los datos recibidos no cumplen las reglas del aula."""
    codigo = "datos_invalidos"
    http = 400


class SinPermiso(ErrorAula):
    """Quien actúa no tiene el permiso classroom.* que exige la función."""
    codigo = "sin_permiso"
    http = 403


class NoEncontrado(ErrorAula):
    """No existe."""
    codigo = "no_encontrado"
    http = 404


class CursoNoEncontrado(NoEncontrado):
    """La fuente de cursos no conoce esa referencia."""
    codigo = "curso_no_encontrado"


class ReferenciaNoEncontrada(NoEncontrado):
    """La lección, el objeto, la unidad o el medio no están en el curso vigente."""
    codigo = "referencia_no_encontrada"


class DesactivadoPorPolitica(NoEncontrado):
    """La política del colegio desactivó ese curso o contenido en la biblioteca (`disabled_by_policy`).
    Para el aula es «no disponible»: no se muestra ni se guarda (§7 del mapeo)."""
    codigo = "desactivado_por_politica"


class TransicionInvalida(ErrorAula):
    """La sesión de clase no admite esa transición desde su estado actual (INV-025)."""
    codigo = "transicion_invalida"
    http = 409


class SesionCerrada(TransicionInvalida):
    """La sesión está cerrada: no admite participantes nuevos ni cambios de foco (BR-052)."""
    codigo = "sesion_cerrada"


class SesionActivaExistente(ErrorAula):
    """El profesor ya tiene una sesión de clase abierta en este nodo (BR-045)."""
    codigo = "sesion_activa_existente"
    http = 409


class GrupoConSesionActiva(ErrorAula):
    """El grupo ya tiene una sesión abierta o suspendida con otro profesor (DEC-035)."""
    codigo = "grupo_con_sesion_activa"
    http = 409


class ActividadesAbiertas(ErrorAula):
    """Hay actividades abiertas pendientes de cierre (precondición de FUN-079)."""
    codigo = "actividades_abiertas"
    http = 409


class ParticipanteExpulsado(ErrorAula):
    """El participante fue expulsado; sólo el profesor puede readmitirlo (BR-048)."""
    codigo = "participante_expulsado"
    http = 403


class SinParticipantesAdmitidos(ErrorAula):
    """Lanzar una actividad exige al menos un dispositivo admitido (FUN-070)."""
    codigo = "sin_participantes_admitidos"
    http = 409


class CodigoInvalido(NoEncontrado):
    """No hay ninguna sesión abierta con ese código de unión."""
    codigo = "codigo_invalido"


# ------------------------------------------------------------- dispositivos (MOD-009)

class DispositivoBloqueado(ErrorAula):
    """La tableta está bloqueada por el profesor o el administrador: no entra a la clase ni recibe lanzamientos."""
    codigo = "dispositivo_bloqueado"
    http = 403


class DispositivoInactivo(ErrorAula):
    """La tableta fue retirada del inventario del aula."""
    codigo = "dispositivo_inactivo"
    http = 403


# ----------------------------------------------------- fuente de cursos (puerto)

class FuenteNoDisponible(ErrorAula):
    """La fuente de cursos no está (biblioteca cerrada, manifiesto ausente). Estado normal del aula."""
    codigo = "fuente_no_disponible"
    http = 503

    def __init__(self, detalle: str = "", sugerencia: str | None = None, **extra):
        super().__init__(detalle, **extra)
        self.sugerencia = sugerencia


class CapacidadAusente(ErrorAula):
    """La biblioteca instalada no publica la capacidad necesaria."""
    codigo = "capacidad_ausente"
    http = 501


class FuenteError(ErrorAula):
    """La fuente contestó, pero con error."""
    codigo = "fuente_error"
    http = 502
