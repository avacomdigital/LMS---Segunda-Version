"""
Errores del dominio del Gradebook. La capa HTTP los traduce a `{detail, codigo, …}`; el dominio y la aplicación sólo los lanzan. Cada uno lleva su
código HTTP y los datos que la pantalla necesita (`estado`, `motivo`, `version_actual`…). Siguen la forma de los errores de MOD-010.
"""
from __future__ import annotations


class ErrorGradebook(Exception):
    codigo = "error_gradebook"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


# ------------------------------------------------------------------------------------------- 400

class DatosInvalidos(ErrorGradebook):
    """Los datos recibidos no cumplen las reglas del Gradebook."""
    codigo = "datos_invalidos"
    http = 400


class PuntajeInvalido(DatosInvalidos):
    """Una puntuación interna va de 0 a 100, con a lo sumo dos decimales."""
    codigo = "puntaje_invalido"


class EscalaInvalida(DatosInvalidos):
    """La definición de la escala no es válida: lleva `problemas`, uno por cada regla que incumple."""
    codigo = "escala_invalida"


class FaltaAlumno(ErrorGradebook):
    """Sin sesión no se sabe de quién son las notas: hay que declarar `alumno_id`."""
    codigo = "falta_alumno"
    http = 400


# ------------------------------------------------------------------------------------------- 403

class SinPermiso(ErrorGradebook):
    """Quien actúa no tiene el permiso que exige la función."""
    codigo = "sin_permiso"
    http = 403


class FueraDeAlcance(SinPermiso):
    """El permiso existe, pero no sobre este grupo: un profesor sólo califica a SUS grupos."""
    codigo = "fuera_de_alcance"


class AlumnoDesconocido(SinPermiso):
    """El `alumno_id` que declara el aparato no existe en el padrón o está inactivo."""

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle, motivo="alumno_desconocido", **extra)


# ------------------------------------------------------------------------------------------- 404 / 409

class NoEncontrado(ErrorGradebook):
    """No existe, o no es visible para quien pregunta."""
    codigo = "no_encontrado"
    http = 404


class NodoNoInstalado(ErrorGradebook):
    """El nodo aún no está instalado: no hay organización (MOD-001)."""
    codigo = "no_instalado"
    http = 409


class ConflictoDeVersion(ErrorGradebook):
    """Otra persona cambió esta calificación mientras tú la editabas: vuelve a leerla (lleva `version_actual`)."""
    codigo = "conflicto_de_version"
    http = 409


class SolicitudRepetida(ErrorGradebook):
    """Esa `solicitud_id` ya se usó para OTRA operación: es la clave de un reintento, no un identificador reutilizable. Manda una nueva por cada acción."""
    codigo = "solicitud_repetida"
    http = 409


class TransicionInvalida(ErrorGradebook):
    """El estado de la calificación no admite esa operación. Lleva `estado`."""
    codigo = "transicion_invalida"
    http = 409


class IntentoNoCalificable(ErrorGradebook):
    """El intento aún no está calificado del todo (revisión pendiente, biblioteca sin responder, anulado o sin entregar): no se registra una calificación."""
    codigo = "intento_no_calificable"
    http = 409


class ReactivosPendientes(ErrorGradebook):
    """Quedan reactivos de revisión docente sin puntuar. Lleva `pendientes`."""
    codigo = "reactivos_pendientes"
    http = 409


class NoPublicable(ErrorGradebook):
    """La calificación no cumple las condiciones para publicarse. Lleva `motivos`."""
    codigo = "no_publicable"
    http = 409


class ModoSimple(ErrorGradebook):
    """El nivel está en modo simple: no hay calificaciones que registrar ni publicar."""
    codigo = "modo_simple"
    http = 409


class ModoBloqueado(ErrorGradebook):
    """No se alterna el modo de un nivel mientras haya evaluaciones en curso en ese nivel. Lleva `en_curso`."""
    codigo = "evaluaciones_en_curso"
    http = 409


class EscalaNoVigente(ErrorGradebook):
    """La escala no existe, está desactivada o aún es una plantilla sin adoptar: toda conversión responde a una política institucional explícita."""
    codigo = "escala_no_vigente"
    http = 409


class RubricaNoDisponible(ErrorGradebook):
    """La biblioteca no entregó la rúbrica de esta pregunta (cerrada, o la pregunta no la tiene): sin ella no se puede aplicar una rúbrica."""
    codigo = "rubrica_no_disponible"
    http = 409


class ReactivoNoRevisable(ErrorGradebook):
    """Ese reactivo se califica solo: el profesor puntúa los que la biblioteca marca para corrección manual."""
    codigo = "reactivo_no_revisable"
    http = 409


class RevisionNoPendiente(ErrorGradebook):
    """Ese intento no está en revisión docente."""
    codigo = "revision_no_pendiente"
    http = 409
