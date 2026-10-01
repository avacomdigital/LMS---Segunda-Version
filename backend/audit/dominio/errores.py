"""Errores del dominio de auditoría. La capa HTTP los traduce a códigos estables; el dominio sólo los lanza."""
from __future__ import annotations


class ErrorAuditoria(Exception):
    codigo = "error_auditoria"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorAuditoria):
    """Los datos recibidos no tienen la forma esperada."""
    codigo = "datos_invalidos"
    http = 400


class BitacoraInmutable(ErrorAuditoria):
    """La bitácora sólo se agrega: nadie puede editarla ni borrarla (BR-100, INV-027, AC-081)."""
    codigo = "bitacora_inmutable"
    http = 403


class AccionDesconocida(ErrorAuditoria):
    """La acción no está en el catálogo cerrado de acciones auditables (§3.5)."""
    codigo = "accion_desconocida"
    http = 422


class MotivoRequerido(ErrorAuditoria):
    """Esta acción exige un motivo (calificaciones, escaladas, exportaciones)."""
    codigo = "motivo_requerido"
    http = 400


class SinPermiso(ErrorAuditoria):
    """Quien actúa no tiene el permiso que exige la función."""
    codigo = "permiso_denegado"
    http = 403


class AutorizacionRequerida(ErrorAuditoria):
    """Exportar exige una autorización de salida vigente por operación (ESC-03, BR-105)."""
    codigo = "autorizacion_requerida"
    http = 403


class CadenaConSalto(ErrorAuditoria):
    """El tramo tiene un salto detectado: hay que aclararlo antes de exportarlo (FUN-200 pide un rango verificado)."""
    codigo = "cadena_con_salto"
    http = 409


class TramoNoVerificado(ErrorAuditoria):
    """El tramo aún no fue verificado: verifícalo antes de exportarlo."""
    codigo = "tramo_no_verificado"
    http = 409


class NoEncontrado(ErrorAuditoria):
    """No existe ese asiento, tramo o exportación."""
    codigo = "no_encontrado"
    http = 404


class BitacoraNoDisponible(ErrorAuditoria):
    """No se pudo escribir la bitácora: el hecho no ocurre (§1.2)."""
    codigo = "bitacora_no_disponible"
    http = 503
