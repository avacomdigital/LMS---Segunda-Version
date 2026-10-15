"""
Los errores de Search. El mismo contrato de degradación que el resto del backend:
  DatosInvalidos → 400 · SinPermiso / FueraDeAlcance → 403 · NoEncontrado → 404 · SesionActiva / ReconstruccionEnCurso / NodoNoInstalado → 409.
Un error del catálogo (la biblioteca cerrada) NO es un error de la búsqueda: lo que se pudo buscar se devuelve y el catálogo aparece como «no disponible».
"""
from __future__ import annotations


class ErrorBusqueda(Exception):
    codigo = "error_busqueda"
    http = 400

    def __init__(self, detalle: str, **extra):
        super().__init__(detalle)
        self.detalle = detalle
        self.extra = extra


class DatosInvalidos(ErrorBusqueda):
    codigo = "datos_invalidos"
    http = 400


class ConsultaVacia(DatosInvalidos):
    codigo = "consulta_vacia"


class ConsultaInvalida(DatosInvalidos):
    codigo = "consulta_invalida"


class SinPermiso(ErrorBusqueda):
    codigo = "sin_permiso"
    http = 403


class FueraDeAlcance(ErrorBusqueda):
    codigo = "fuera_de_alcance"
    http = 403


class NoEncontrado(ErrorBusqueda):
    """El recurso que se quiere abrir ya no existe, se retiró o la persona dejó de poder leerlo: no se distingue (no se revela qué hay)."""

    codigo = "no_disponible"
    http = 404


class SesionActiva(ErrorBusqueda):
    """Reconstruir el índice completo exige que no haya una clase en curso (Documento Maestro, precondición de FUN-215)."""

    codigo = "sesion_activa"
    http = 409


class ReconstruccionEnCurso(ErrorBusqueda):
    codigo = "reconstruccion_en_curso"
    http = 409


class NodoNoInstalado(ErrorBusqueda):
    codigo = "no_instalado"
    http = 409


class CatalogoNoDisponible(ErrorBusqueda):
    """AVACOM Biblioteca no contestó: no se puede comprobar el recurso del catálogo que se quiere abrir (y sin ella tampoco se podría abrir)."""

    codigo = "catalogo_no_disponible"
    http = 503
