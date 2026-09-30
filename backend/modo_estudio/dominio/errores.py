"""
Errores del dominio del modo de estudio. La capa HTTP los traduce a `{detail, codigo, …}`; el dominio y la aplicación sólo los lanzan.
Cada uno lleva su código HTTP y los datos extra que la pantalla necesita (`faltan`, `paquete`, `mensaje`…). Son los códigos de la §4
del contrato (`spec-driven/04-modo-estudio/02-modelo-y-api.md`).
"""
from __future__ import annotations


class ErrorEstudio(Exception):
    codigo = "error_estudio"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorEstudio):
    """Los datos recibidos no cumplen las reglas del modo de estudio."""
    codigo = "datos_invalidos"
    http = 400


class FaltaDispositivo(ErrorEstudio):
    """Falta el aparato: sin sesión de alumno hay que decir desde qué dispositivo se pregunta (`dispositivo`, su huella)."""
    codigo = "falta_dispositivo"
    http = 400


class FaltaAlumno(ErrorEstudio):
    """Sin sesión y sin dueño (aparato compartido) no se sabe quién estudia: hay que declarar `alumno_id` (D-15)."""
    codigo = "falta_alumno"
    http = 400


class SinPermiso(ErrorEstudio):
    """Quien actúa no tiene el permiso study.* que exige la función."""
    codigo = "sin_permiso"
    http = 403


class AlumnoDesconocido(SinPermiso):
    """El `alumno_id` que declara el aparato no existe en el padrón o está inactivo (D-15): la tableta vuelve a preguntar «¿Quién eres?».
    Sale como `sin_permiso` con `motivo = alumno_desconocido`."""

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle, motivo="alumno_desconocido", **extra)


class NoEsElTitular(SinPermiso):
    """La tarea, la práctica o el paquete son de otra persona: sólo su titular los lee o los escribe."""
    codigo = "no_es_el_titular"


class DispositivoBloqueado(ErrorEstudio):
    """La tableta está bloqueada por el profesor o el administrador (MOD-009): no abre sesión ni estudia."""
    codigo = "dispositivo_bloqueado"
    http = 403


class DispositivoInactivo(ErrorEstudio):
    """La tableta fue dada de baja del inventario del aula (MOD-009)."""
    codigo = "dispositivo_inactivo"
    http = 403


class DescargaDenegada(ErrorEstudio):
    """BR-054: el material sólo se descarga en una tableta asignada a la persona (no en una compartida, ni en la asignada a OTRA persona).
    Lleva `paquete` (estado «denegado», con su `motivo`) y `mensaje` (MSG-046)."""
    codigo = "descarga_denegada"
    http = 403


class NoEncontrado(ErrorEstudio):
    """No existe, o no es visible para el alumno."""
    codigo = "no_encontrado"
    http = 404


class NodoNoInstalado(ErrorEstudio):
    """El nodo aún no está instalado: no hay organización (MOD-001) a la que atar grupos, alumnos y aparatos."""
    codigo = "no_instalado"
    http = 409


class AsignacionCerrada(ErrorEstudio):
    """La asignación ya no admite avance ni respuestas: el profesor la cerró o su plazo endurecido venció."""
    codigo = "asignacion_cerrada"
    http = 409


class BloquesPendientes(ErrorEstudio):
    """FUN-087: la lección sólo se completa cuando se atendieron todos los bloques obligatorios. Lleva `faltan`."""
    codigo = "bloques_pendientes"
    http = 409


class PracticaTerminada(ErrorEstudio):
    """La práctica ya terminó: no admite respuestas nuevas. Se abre otra («Intentar nuevamente»)."""
    codigo = "practica_terminada"
    http = 409


class PracticaEnCurso(ErrorEstudio):
    """Hay otra práctica en curso de esa actividad con un número distinto: la cola trae un intento nuevo sin haber cerrado el anterior."""
    codigo = "practica_en_curso"
    http = 409


class HuellaInvalida(ErrorEstudio):
    """La huella que el aparato confirma no es la del manifiesto que se le entregó: el paquete no está íntegro."""
    codigo = "huella_invalida"
    http = 409


class PaqueteVencido(ErrorEstudio):
    """El paquete venció (su vigencia pasó o el curso tiene una versión nueva): hay que pedirlo de nuevo («Actualizar descarga»)."""
    codigo = "paquete_vencido"
    http = 410


class FuenteNoDisponible(ErrorEstudio):
    """La fuente de cursos no responde (biblioteca cerrada). Estado normal del nodo: lo ya guardado sigue funcionando."""
    codigo = "fuente_no_disponible"
    http = 503

    def __init__(self, detalle: str = "", sugerencia: str | None = None, **extra):
        super().__init__(detalle, **extra)
        self.sugerencia = sugerencia


class FuenteError(ErrorEstudio):
    """La fuente de cursos contestó, pero con un error (paquete que no pasa su verificación, respuesta inesperada)."""
    codigo = "fuente_error"
    http = 502


class MedioDemasiadoGrande(ErrorEstudio):
    """Un medio supera el tope de tamaño que el nodo mide al preparar un paquete. No sale por HTTP: el paquete lo deja en `no_incluidos`."""
    codigo = "medio_demasiado_grande"
    http = 413
