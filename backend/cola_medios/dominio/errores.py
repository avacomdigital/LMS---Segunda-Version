"""
Errores de la cola de medios. Hay dos familias que no se deben confundir:

  ErrorDeOrigen   lo que contestó AVACOM Contenido (o la fuente de cursos): un 404, la biblioteca cerrada, la política apagada. Lleva el error ORIGINAL
                  del aula (`original`) para que la vista lo responda exactamente como antes de que existiera la cola. Pasa tal cual hacia arriba.
  ErrorDeCola     un problema del propio nodo (disco lleno, archivo incompleto, un bug). La cola nunca le cuesta un medio a nadie: ante uno de estos el
                  llamador sirve el medio en paso a través, como siempre.
"""
from __future__ import annotations


class ErrorDeOrigen(Exception):
    def __init__(self, original: Exception, *, transitorio: bool, codigo: str = ""):
        super().__init__(str(original))
        self.original = original
        self.transitorio = transitorio       # la fuente no estaba (se reintenta); False = el medio ya no existe (no se reintenta)
        self.codigo = codigo


class ErrorDeCola(Exception):
    def __init__(self, mensaje: str, codigo: str = ""):
        super().__init__(mensaje)
        self.codigo = codigo


class SinEspacio(ErrorDeCola):
    pass


class Incompleto(ErrorDeCola):
    pass


class Cancelado(ErrorDeCola):
    pass


class DemasiadoGrande(ErrorDeCola):
    def __init__(self, bytes_: int):
        super().__init__(f"El medio pesa {bytes_} bytes y supera el tope pedido.", "demasiado_grande")
        self.bytes = bytes_
