"""
Errores del dominio de MOD-015. La capa HTTP los traduce a `{detail, codigo, …}`; el dominio y la aplicación sólo los lanzan. Cada uno lleva su código HTTP y los datos que la
pantalla necesita. Siguen la forma de los errores de MOD-010, MOD-011 y MOD-013.

Ojo con la semántica hacia los clientes (R-07): nada de esta lista se usa en una ruta con cola de dispositivo; el modo restringido responde 503 y sólo fuera del núcleo.
"""
from __future__ import annotations


class ErrorNodo(Exception):
    codigo = "error_nodo"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


# ------------------------------------------------------------------------------------------- 400 (sólo en pruebas y desarrollo: en producción el hecho no se pierde, R-06)

class DatosInvalidos(ErrorNodo):
    """Los datos recibidos no tienen la forma esperada."""
    codigo = "datos_invalidos"
    http = 400


class NombreInvalido(DatosInvalidos):
    """El tipo de evento no sigue el patrón del catálogo (BR-122): dominio, objeto, acción en participio y versión, en minúsculas."""
    codigo = "nombre_invalido"


class TipoNoCatalogado(DatosInvalidos):
    """El tipo de evento no está en el catálogo (BR-133: cada tipo declara su clase, su sensibilidad y su clave de deduplicación)."""
    codigo = "tipo_no_catalogado"


class CargaInvalida(DatosInvalidos):
    """La carga del evento trae datos que no pueden viajar en la cola (BR-127) o es demasiado grande."""
    codigo = "carga_invalida"


class SobreIncompleto(DatosInvalidos):
    """Al sobre le falta un campo: ninguno es opcional."""
    codigo = "sobre_incompleto"


# ------------------------------------------------------------------------------------------- 403

class SinPermiso(ErrorNodo):
    """Quien actúa no tiene el permiso que exige la función."""
    codigo = "sin_permiso"
    http = 403


# ------------------------------------------------------------------------------------------- 404 / 409 / 500

class NoEncontrado(ErrorNodo):
    """No existe."""
    codigo = "no_encontrado"
    http = 404


class FueraDeTransaccion(ErrorNodo):
    """`publicar` se llamó fuera de la transacción del hecho (BR-001, INV-022): el evento sólo se escribe junto con lo que lo originó."""
    codigo = "fuera_de_transaccion"
    http = 500


class ModuloYaCortado(ErrorNodo):
    """Ese módulo ya escribe en la cola única: el corte es de una sola vía."""
    codigo = "modulo_ya_cortado"
    http = 409


class ContratoIncompatible(ErrorNodo):
    """El contrato que declara ese consumidor o módulo no es compatible con lo que el nodo produce (INV-007)."""
    codigo = "contrato_incompatible"
    http = 409


class ConsumidorDesconocido(ErrorNodo):
    """Ese consumidor no está registrado en la cola."""
    codigo = "consumidor_desconocido"
    http = 404


class ConsumidorSinAplicador(ErrorNodo):
    """Ese consumidor no corre en este proceso: no hay quién aplique el evento."""
    codigo = "consumidor_sin_aplicador"
    http = 409


class ProblemaYaResuelto(ErrorNodo):
    """Ese evento apartado ya fue reprocesado."""
    codigo = "problema_ya_resuelto"
    http = 409


class ReprocesoFallido(ErrorNodo):
    """El evento volvió a fallar al reprocesarlo: queda apartado con un intento más."""
    codigo = "reproceso_fallido"
    http = 409


class NodoRestringido(ErrorNodo):
    """El nodo está en modo restringido: esta operación espera a que la condición se despeje. La clase sigue."""
    codigo = "nodo_restringido"
    http = 503
