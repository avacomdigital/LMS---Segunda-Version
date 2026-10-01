"""
Autenticación JWT para DRF. Sin cabecera devuelve None (anónimo), así que las rutas
del expediente no cambian de comportamiento mientras Q-34 siga abierta.
"""
from __future__ import annotations

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from ..aplicacion.casos_uso import ResolverPrincipal
from ..dominio import errores
from ..infraestructura.contenedor import servicios


class AutenticacionJwt(BaseAuthentication):
    palabra = b"bearer"

    def authenticate(self, request):
        cabecera = get_authorization_header(request).split()
        if not cabecera or cabecera[0].lower() != self.palabra:
            return None
        if len(cabecera) != 2:
            raise exceptions.AuthenticationFailed({"detail": "Cabecera Authorization mal formada.", "codigo": "sesion_invalida"})
        try:
            principal = ResolverPrincipal(servicios()).ejecutar(cabecera[1].decode("ascii"))
        except UnicodeDecodeError:
            raise exceptions.AuthenticationFailed({"detail": "Token ilegible.", "codigo": "sesion_invalida"})
        except errores.ErrorAcceso as error:
            raise exceptions.AuthenticationFailed({"detail": error.detalle, "codigo": error.codigo})
        # MOD-019: quien firma la sesión pasa al contexto de la operación ANTES de que corra la vista, para que todo
        # asiento y toda línea de log que deje el caso de uso lleven actor, rol y aparato sin que nadie los pase a mano.
        from audit import contexto   # módulo puro, sin modelos
        contexto.establecer(usuario_id=principal.usuario_id, rol_codigo=principal.rol_codigo, sesion_id=principal.sesion_id,
                            dispositivo_id=contexto.actual().dispositivo_id or principal.dispositivo_id)
        return principal, cabecera[1]

    def authenticate_header(self, request):
        return "Bearer"
