"""Errores del dominio de licenciamiento (MOD-018). La capa HTTP los traduce a códigos; el dominio sólo los lanza."""
from __future__ import annotations


class ErrorLicencia(Exception):
    codigo = "error_licencia"
    http = 400

    def __init__(self, detalle: str = "", **extra):
        super().__init__(detalle or self.__class__.__doc__ or self.codigo)
        self.detalle = detalle or (self.__class__.__doc__ or self.codigo)
        self.extra = extra


class DatosInvalidos(ErrorLicencia):
    """Los datos recibidos no cumplen las reglas del módulo."""
    codigo = "datos_invalidos"
    http = 400


class SinPermiso(ErrorLicencia):
    """Quien actúa no tiene el permiso license.* que exige la función."""
    codigo = "sin_permiso"
    http = 403


class NoEncontrado(ErrorLicencia):
    """No existe lo que se pidió."""
    codigo = "no_encontrado"
    http = 404


class Conflicto(ErrorLicencia):
    """La petición choca con el estado actual de la licencia."""
    codigo = "conflicto"
    http = 409


class LicenciaInvalida(ErrorLicencia):
    """El archivo no es una licencia válida de AVACOM. `motivo` dice por qué, sin revelar nada del contenido."""
    codigo = "licencia_invalida"
    http = 400

    def __init__(self, motivo: str, detalle: str = "", **extra):
        super().__init__(detalle or MENSAJES_DE_MOTIVO.get(motivo, "El archivo no es una licencia válida."), motivo=motivo, **extra)
        self.motivo = motivo


class HuellaNoCoincide(ErrorLicencia):
    """La licencia fue emitida para otro equipo: la huella de este equipo no coincide con la que lleva el archivo."""
    codigo = "huella_no_coincide"
    http = 409


class NoDisponiblePorLicencia(ErrorLicencia):
    """El módulo no está disponible con la licencia actual. El permiso del rol se conserva: vuelve a funcionar al renovar."""
    codigo = "no_disponible_por_licencia"
    http = 402


class CupoAgotado(ErrorLicencia):
    """Se alcanzó el cupo de la licencia: no se pueden dar de alta más equipos o usuarios. Lo que ya existe sigue funcionando."""
    codigo = "cupo_agotado"
    http = 402


class RetoInvalido(ErrorLicencia):
    """El reto que trae el equipo no existe, ya venció o ya se usó. Un reto vale una sola vez: se pide otro."""
    codigo = "reto_invalido"
    http = 400


class IdentidadInvalida(ErrorLicencia):
    """La prueba de clave del equipo no es válida (la clave o la firma del reto no cuadran)."""
    codigo = "identidad_invalida"
    http = 400


class IdentidadRequerida(ErrorLicencia):
    """La licencia exige que un equipo nuevo pruebe su clave (nivel mínimo de garantía) y este no lo hizo. Lo que ya está registrado sigue funcionando. 402, no 403: no es un permiso."""
    codigo = "identidad_requerida"
    http = 402


class ClaveDistinta(ErrorLicencia):
    """Este equipo ya tiene registrada otra clave: una identidad se enrola una vez. Para cambiarla, el técnico reinicia la identidad del equipo."""
    codigo = "clave_distinta"
    http = 409


class ClaveEnUso(ErrorLicencia):
    """Esa clave ya identifica a otro equipo del aula: una clave no puede contar como dos equipos."""
    codigo = "clave_en_uso"
    http = 409


# Los motivos son parte del contrato con el cliente (OPS los convierte en frases): no se renombran.
MENSAJES_DE_MOTIVO = {
    "demasiado_grande": "El archivo es demasiado grande para ser una licencia.",
    "demasiado_corta": "El archivo está incompleto o dañado.",
    "formato": "El archivo no tiene el formato de una licencia de AVACOM.",
    "texto": "El texto no es una licencia: pega o copia el archivo completo.",
    "version_no_soportada": "Esta licencia usa una versión del formato que este equipo no entiende.",
    "kid_desconocido": "La licencia fue firmada con una llave que este equipo no reconoce.",
    "firma_invalida": "La firma de la licencia no es válida: el archivo fue modificado o no es de AVACOM.",
    "etiqueta_critica_desconocida": "La licencia exige algo que esta versión no entiende: actualiza AVACOM OPS.",
    "campo_faltante": "A la licencia le falta información obligatoria.",
    "campo_invalido": "La licencia trae un dato fuera de rango.",
    "solicitud_ajena": "La solicitud no fue generada por este equipo.",
    "serie_no_posterior": "La licencia no es más reciente que la que ya está instalada.",
    "otra_licencia": "Esta es otra licencia distinta de la instalada: para cambiarla hay que liberar este equipo primero.",
    "sin_licencia_instalada": "Este equipo todavía no tiene una licencia instalada: usa «Activar».",
    "tipo_no_admitido": "Esa licencia no se puede usar en este equipo.",
    "aun_no_vigente": "La licencia todavía no empieza según la fecha de este equipo. Revisa que la fecha y la hora del equipo estén bien y vuelve a intentarlo.",
}
