"""Errores del dominio de dispositivos. La capa HTTP los traduce a códigos; el dominio sólo los lanza."""
from __future__ import annotations


class ErrorDispositivos(Exception):
    codigo = "error_dispositivos"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorDispositivos):
    """Los datos recibidos no cumplen las reglas del módulo."""
    codigo = "datos_invalidos"
    http = 400


class SinPermiso(ErrorDispositivos):
    """Quien actúa no tiene el permiso device.* que exige la función."""
    codigo = "sin_permiso"
    http = 403


class NoEncontrado(ErrorDispositivos):
    """No existe ese dispositivo."""
    codigo = "no_encontrado"
    http = 404


class NodoNoInstalado(ErrorDispositivos):
    """El nodo aún no está instalado: no hay organización a la que registrar dispositivos."""
    codigo = "no_instalado"
    http = 409


class DispositivoBloqueado(ErrorDispositivos):
    """La tableta está bloqueada por el profesor o el administrador: no abre sesión ni recibe lanzamientos."""
    codigo = "dispositivo_bloqueado"
    http = 403


class DispositivoInactivo(ErrorDispositivos):
    """La tableta fue dada de baja del inventario del aula."""
    codigo = "dispositivo_inactivo"
    http = 403


class DispositivoYaAsignado(ErrorDispositivos):
    """El equipo ya es de otra persona (FUN-092): primero se libera y después se asigna a quien corresponda."""
    codigo = "dispositivo_ya_asignado"
    http = 409


class PaqueteSinIntegrar(ErrorDispositivos):
    """El equipo aún tiene un paquete de estudio activo (FUN-093): mientras la persona conserve material o trabajo sin integrar en
    él, liberarlo lo dejaría a la vista del siguiente alumno. Debe retirarse el paquete antes de liberar el equipo."""
    codigo = "paquete_sin_integrar"
    http = 409
