"""Errores del dominio de respaldo (MOD-016). La capa HTTP los traduce a códigos; el dominio sólo los lanza."""
from __future__ import annotations

from . import catalogos as cat


class ErrorRespaldo(Exception):
    codigo = "error_respaldo"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorRespaldo):
    """Los datos recibidos no cumplen las reglas del módulo."""
    codigo = "datos_invalidos"
    http = 400


class SinPermiso(ErrorRespaldo):
    """Quien actúa no tiene el permiso backup.* que exige la función: respaldar y restaurar son del personal de AVACOM."""
    codigo = "sin_permiso"
    http = 403


class PaseRequerido(ErrorRespaldo):
    """Esta operación exige un pase de soporte firmado por AVACOM."""
    codigo = "pase_requerido"
    http = 403


class PaseInvalido(ErrorRespaldo):
    """El pase de soporte no es válido: no está firmado por AVACOM, venció, no es para esta operación o ya se usó."""
    codigo = "pase_invalido"
    http = 403

    def __init__(self, motivo: str, detalle: str = "", **extra):
        super().__init__(detalle or "El pase de soporte de AVACOM no es válido.", motivo=motivo, **extra)
        self.motivo = motivo


class NoEncontrado(ErrorRespaldo):
    """No existe lo que se pidió."""
    codigo = "no_encontrado"
    http = 404


class Conflicto(ErrorRespaldo):
    """La petición choca con el estado actual del respaldo o del aula."""
    codigo = "conflicto"
    http = 409


class EstadoInvalido(Conflicto):
    """El respaldo no está en un estado que admita esa operación."""
    codigo = "estado_invalido"


class SesionActiva(Conflicto):
    """Hay una clase en curso: no se restaura con una clase abierta (FUN-174)."""
    codigo = "sesion_activa"


class RespaldoEnCurso(Conflicto):
    """Ya hay un respaldo o una restauración en marcha: espera a que termine."""
    codigo = "respaldo_en_curso"


class EspacioInsuficiente(Conflicto):
    """El destino no tiene espacio suficiente para el respaldo."""
    codigo = "espacio_insuficiente"


class RespaldoFallido(Conflicto):
    """El respaldo no terminó. `motivo` dice por qué; lo que había antes sigue intacto."""
    codigo = "respaldo_fallido"

    def __init__(self, motivo: str, detalle: str = "", **extra):
        super().__init__(detalle or "El respaldo no terminó.", motivo=motivo, **extra)
        self.motivo = motivo


class RestauracionAbortada(Conflicto):
    """La restauración se abortó ANTES de tocar los datos vivos (o lo dice si ya los había tocado). `motivo` dice por qué."""
    codigo = "restauracion_abortada"

    def __init__(self, motivo: str, detalle: str = "", **extra):
        super().__init__(detalle or "La restauración se abortó.", motivo=motivo, **extra)
        self.motivo = motivo


class SinRespaldoPrevio(Conflicto):
    """Un respaldo incremental necesita un completo anterior (FUN-171)."""
    codigo = "sin_respaldo_previo"


class CustodiaRequerida(Conflicto):
    """Este respaldo es de otro equipo: hace falta el código de custodia de la institución (BR-102)."""
    codigo = "custodia_requerida"


class CustodiaYaEmitida(Conflicto):
    """La institución ya tiene un código de custodia. Emitir otro es posible, pero se pide explícitamente (`reemplazar`)."""
    codigo = "custodia_ya_emitida"


class SinCustodia(Conflicto):
    """Todavía no se emitió el código de custodia de la institución: sin él no hay respaldo restaurable en otro equipo (BR-102)."""
    codigo = "sin_custodia"


class ModuloSinRestauracionAislada(Conflicto):
    """El módulo no declara restauración aislada (FUN-175): sólo se restaura el equipo completo."""
    codigo = "modulo_sin_restauracion_aislada"


class RespaldoRechazado(ErrorRespaldo):
    """El archivo no es un respaldo válido de AVACOM. `motivo` dice por qué, sin revelar nada del contenido."""
    codigo = "respaldo_invalido"
    http = 422

    def __init__(self, motivo: str, detalle: str = "", **extra):
        super().__init__(detalle or cat.MENSAJES_DE_MOTIVO.get(motivo, "El archivo no es un respaldo válido."), motivo=motivo, **extra)
        self.motivo = motivo


class ClaveNoDisponible(RespaldoRechazado):
    """Ni la clave de este equipo ni el código de custodia abren el respaldo."""
    codigo = "clave_no_disponible"

    def __init__(self, detalle: str = "", **extra):
        super().__init__("clave_no_disponible", detalle, **extra)
