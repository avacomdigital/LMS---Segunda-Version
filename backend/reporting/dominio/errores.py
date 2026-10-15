"""
Errores del dominio de Reporting. La capa HTTP los traduce a `{detail, codigo, …}`; el dominio y la aplicación sólo los lanzan. Cada uno lleva su código HTTP y los datos
que la pantalla necesita. Siguen la forma de los errores de MOD-010 y MOD-011, y su mensaje se escribe para quien está frente a la pantalla (sin jerga).
"""
from __future__ import annotations


class ErrorReporting(Exception):
    codigo = "error_reporting"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


# ------------------------------------------------------------------------------------------- 400

class DatosInvalidos(ErrorReporting):
    """Los datos recibidos no tienen la forma esperada."""
    codigo = "datos_invalidos"
    http = 400


class MotivoRequerido(DatosInvalidos):
    """El administrador pidió que cada exportación diga para qué se hace: hay que elegir una razón de la lista."""
    codigo = "razon_requerida"


# ------------------------------------------------------------------------------------------- 403

class SinPermiso(ErrorReporting):
    """Quien actúa no tiene el permiso que exige la función."""
    codigo = "sin_permiso"
    http = 403


class FueraDeAlcance(SinPermiso):
    """El permiso existe, pero no sobre este grupo: un profesor sólo ve los reportes de SUS grupos."""
    codigo = "fuera_de_alcance"


class DestinoNoPermitido(SinPermiso):
    """El administrador del colegio no permite guardar reportes en ese tipo de destino."""
    codigo = "destino_no_permitido"


# ------------------------------------------------------------------------------------------- 404 / 409 / 501

class NoEncontrado(ErrorReporting):
    """No existe, o no es visible para quien pregunta."""
    codigo = "no_encontrado"
    http = 404


class NodoNoInstalado(ErrorReporting):
    """El nodo aún no está instalado: no hay organización a la que atar grupos y alumnos."""
    codigo = "no_instalado"
    http = 409


class ClaseEnCurso(ErrorReporting):
    """La clase aún no termina: su reporte se arma al cerrarla."""
    codigo = "clase_en_curso"
    http = 409


class AlumnoSinGrupo(ErrorReporting):
    """Ese alumno no pertenece a ningún grupo activo: no hay avance que reportar."""
    codigo = "alumno_sin_grupo"
    http = 409


class SinSesionesFinalizadas(ErrorReporting):
    """No hay clases finalizadas en ese periodo."""
    codigo = "sin_sesiones_finalizadas"
    http = 409


class SesionActiva(ErrorReporting):
    """Hay una clase en curso: reconstruir los reportes espera a que termine."""
    codigo = "sesion_activa"
    http = 409


class ReconstruccionEnCurso(ErrorReporting):
    """Ya se están reconstruyendo los reportes."""
    codigo = "reconstruccion_en_curso"
    http = 409


class ExportacionCaducada(ErrorReporting):
    """Esa exportación caducó sin confirmarse: hay que generarla de nuevo."""
    codigo = "exportacion_caducada"
    http = 409


class ExportacionYaConfirmada(ErrorReporting):
    """Esa exportación ya quedó entregada."""
    codigo = "exportacion_ya_confirmada"
    http = 409


class HuellaDistinta(ErrorReporting):
    """El archivo que quedó guardado no coincide con el que el nodo entregó."""
    codigo = "huella_distinta"
    http = 409


class ConflictoDeVersion(ErrorReporting):
    """Otra persona cambió esta configuración mientras tú la editabas: vuelve a leerla."""
    codigo = "conflicto_de_version"
    http = 409


class CapacidadReservada(ErrorReporting):
    """Esta capacidad está prevista para una versión posterior y todavía no existe."""
    codigo = "capacidad_reservada"
    http = 501
