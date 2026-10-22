"""Errores del dominio de actualización (MOD-017). La capa HTTP los traduce a códigos; el dominio sólo los lanza."""
from __future__ import annotations

from . import catalogos as cat


class ErrorActualizacion(Exception):
    codigo = "error_actualizacion"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorActualizacion):
    """Los datos recibidos no cumplen las reglas del módulo."""
    codigo = "datos_invalidos"
    http = 400


class SinPermiso(ErrorActualizacion):
    """Quien actúa no tiene el permiso update.* que exige la función."""
    codigo = "sin_permiso"
    http = 403


class NoEncontrado(ErrorActualizacion):
    """No existe lo que se pidió."""
    codigo = "no_encontrado"
    http = 404


class Conflicto(ErrorActualizacion):
    """La petición choca con el estado actual del paquete o del aula."""
    codigo = "conflicto"
    http = 409


class EstadoInvalido(Conflicto):
    """El paquete no está en un estado que admita esa operación."""
    codigo = "estado_invalido"


class ContratoIncompatible(Conflicto):
    """El paquete no es compatible con los módulos instalados: la instalación no inicia (BR-013, INV-007)."""
    codigo = "contrato_incompatible"


class EspacioInsuficiente(Conflicto):
    """No hay espacio libre para la copia de la base, la instantánea y el paquete."""
    codigo = "espacio_insuficiente"


class SesionActiva(Conflicto):
    """Hay una clase en curso: la actualización se difiere (FUN-183, R-01)."""
    codigo = "sesion_activa"


class YaAplicado(Conflicto):
    """Este paquete (o uno con la misma serie) ya está aplicado."""
    codigo = "ya_aplicado"


class PaqueteRepetido(Conflicto):
    """Ya se importó un paquete con ese identificador (y otro contenido)."""
    codigo = "paquete_repetido"


class SerieMenor(Conflicto):
    """El paquete es más viejo que lo instalado: no se degrada (P-16, A2)."""
    codigo = "serie_menor"


class FueraDePlazoReversion(Conflicto):
    """Pasaron los 14 días: la instantánea ya no está y no se puede revertir."""
    codigo = "fuera_de_plazo_reversion"


class ActualizacionEnCurso(Conflicto):
    """Ya hay una orden aceptada: no se acepta otra hasta que termine."""
    codigo = "actualizacion_en_curso"


class PaqueteRechazado(ErrorActualizacion):
    """El archivo no es un paquete válido de AVACOM. `motivo` dice por qué, sin revelar nada del contenido."""
    codigo = "paquete_invalido"
    http = 422

    def __init__(self, motivo: str, detalle: str = "", **extra):
        super().__init__(detalle or cat.MENSAJES_DE_MOTIVO.get(motivo, "El archivo no es un paquete de actualización válido."), motivo=motivo, **extra)
        self.motivo = motivo


class FirmaInvalida(PaqueteRechazado):
    """El paquete no está firmado, o su firma no es válida o es de una llave que este equipo no reconoce."""
    codigo = "firma_invalida"


def rechazo(motivo: str, **extra) -> PaqueteRechazado:
    """El error que toca según el motivo: los de firma son `FirmaInvalida`; el resto, `PaqueteRechazado`."""
    clase = FirmaInvalida if motivo in cat.MOTIVOS_DE_FIRMA else PaqueteRechazado
    return clase(motivo, **extra)
