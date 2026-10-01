"""
Errores del dominio de la evaluación. La capa HTTP los traduce a `{detail, codigo, …}`; el dominio y la aplicación sólo los lanzan. Cada
uno lleva su código HTTP y los datos extra que la pantalla necesita (`estado`, `destino`, `motivo`, `admision`…). Son los códigos del §7
del contrato (`spec-driven/06-evaluation-delivery/backend.md`).
"""
from __future__ import annotations


class ErrorEvaluacion(Exception):
    codigo = "error_evaluacion"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


# ------------------------------------------------------------------------------------------- 400

class DatosInvalidos(ErrorEvaluacion):
    """Los datos recibidos no cumplen las reglas de la evaluación."""
    codigo = "datos_invalidos"
    http = 400


class FaltaDispositivo(ErrorEvaluacion):
    """Falta el aparato: sin sesión de alumno hay que decir desde qué dispositivo se pregunta (`dispositivo`, su huella)."""
    codigo = "falta_dispositivo"
    http = 400


class FaltaAlumno(ErrorEvaluacion):
    """Sin sesión y sin dueño (aparato compartido) no se sabe quién rinde: hay que declarar `alumno_id`."""
    codigo = "falta_alumno"
    http = 400


# ------------------------------------------------------------------------------------------- 403

class SinPermiso(ErrorEvaluacion):
    """Quien actúa no tiene el permiso assessment.* que exige la función."""
    codigo = "sin_permiso"
    http = 403


class AlumnoDesconocido(SinPermiso):
    """El `alumno_id` que declara el aparato no existe en el padrón o está inactivo: la tableta vuelve a preguntar quién es."""

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle, motivo="alumno_desconocido", **extra)


class NoEsElTitular(SinPermiso):
    """La asignación es de otro profesor: sólo su titular o la administración la opera."""
    codigo = "no_es_el_titular"


class DispositivoBloqueado(ErrorEvaluacion):
    """La tableta está bloqueada por el profesor o el administrador (MOD-009): no rinde."""
    codigo = "dispositivo_bloqueado"
    http = 403


class DispositivoInactivo(ErrorEvaluacion):
    """La tableta fue dada de baja del inventario del aula (MOD-009)."""
    codigo = "dispositivo_inactivo"
    http = 403


class DispositivoAjeno(ErrorEvaluacion):
    """Esta tableta no es una de las que ha usado este intento: para continuar desde otra se abre el intento de nuevo desde ella."""
    codigo = "dispositivo_ajeno"
    http = 403


class AdmisionRechazada(ErrorEvaluacion):
    """El profesor no admitió esta tableta por debajo del nivel que exige el examen (BR-076)."""
    codigo = "admision_rechazada"
    http = 403


class ResultadosNoLiberados(ErrorEvaluacion):
    """El profesor aún no publica los resultados (DEC-032): el alumno no ve su nota antes."""
    codigo = "resultados_no_liberados"
    http = 403


# ------------------------------------------------------------------------------------------- 404 / 409

class NoEncontrado(ErrorEvaluacion):
    """No existe, o no es visible para quien pregunta (no se revela)."""
    codigo = "no_encontrado"
    http = 404


class NodoNoInstalado(ErrorEvaluacion):
    """El nodo aún no está instalado: no hay organización (MOD-001) a la que atar grupos, alumnos y aparatos."""
    codigo = "no_instalado"
    http = 409


class AdministracionNoPermitida(ErrorEvaluacion):
    """Crear una evaluación o añadir un reactivo es de AVACOM Biblioteca (artículo 14): FUN-103 y FUN-104 no ocurren en el LMS."""
    codigo = "administracion_no_permitida"
    http = 409


class AsignacionNoAbierta(ErrorEvaluacion):
    """La asignación todavía no abre (programada o borrador) o ya no recibe intentos."""
    codigo = "asignacion_no_abierta"
    http = 409


class AsignacionCerrada(ErrorEvaluacion):
    """La asignación cerró y esto se capturó después del cierre: no existe para la evaluación."""
    codigo = "asignacion_cerrada"
    http = 409


class IntentosAgotados(ErrorEvaluacion):
    """BR-072: la asignación admite un número de intentos y ya se usaron."""
    codigo = "intentos_agotados"
    http = 409


class IntentosAbiertos(ErrorEvaluacion):
    """Hay intentos vivos y la operación no se puede hacer mientras los haya (por ejemplo, fijar el nivel o liberar resultados)."""
    codigo = "intentos_abiertos"
    http = 409


class TransicionInvalida(ErrorEvaluacion):
    """La máquina de estados no autoriza esa transición. Lleva `estado` (el actual) y `destino`."""
    codigo = "transicion_invalida"
    http = 409


class IntentoCerrado(ErrorEvaluacion):
    """El intento ya se entregó o se cerró: no admite respuestas nuevas."""
    codigo = "intento_cerrado"
    http = 409


class VersionNoDisponible(ErrorEvaluacion):
    """INV-024: el examen se asignó con una versión del curso que la biblioteca ya no tiene instalada. Hay que volver a asignarlo."""
    codigo = "version_no_disponible"
    http = 409


class ConfirmacionRequerida(ErrorEvaluacion):
    """FUN-114: quedan reactivos sin responder; la entrega exige `confirmar = true`. Lleva `faltan`."""
    codigo = "confirmacion_requerida"
    http = 409


class ReactivosPendientes(ErrorEvaluacion):
    """No se puede publicar el intento mientras queden reactivos de revisión docente sin puntuar. Lleva `pendientes`."""
    codigo = "reactivos_pendientes"
    http = 409


# ------------------------------------------------------------------------------------------- 502 / 503

class FuenteNoDisponible(ErrorEvaluacion):
    """La fuente de cursos no responde (biblioteca cerrada). Estado normal del nodo: guardar respuestas nunca falla por esto."""
    codigo = "fuente_no_disponible"
    http = 503

    def __init__(self, detalle: str = "", sugerencia: str | None = None, **extra):
        super().__init__(detalle, **extra)
        self.sugerencia = sugerencia


class FuenteError(ErrorEvaluacion):
    """La fuente de cursos contestó, pero con un error (paquete que no pasa su verificación, respuesta inesperada)."""
    codigo = "fuente_error"
    http = 502
