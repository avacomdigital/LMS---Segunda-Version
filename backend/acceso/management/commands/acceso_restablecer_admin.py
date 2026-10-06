"""
`manage.py acceso_restablecer_admin --dni <documento>`: restablece la contraseña de una cuenta de administración desde la consola (RB-44, PA-07).

El PIN maestro NO restablece la contraseña del administrador (RN-12) y nadie puede hacerlo desde una pantalla: si se perdió, sólo queda este camino,
que exige estar en el equipo (autoridad física del técnico) y queda auditado con `actor = sistema`. La contraseña queda como PROVISIONAL (debe
cambiarla al entrar) y se cierran las sesiones de esa cuenta.

    manage.py acceso_restablecer_admin --dni 1042888795                 # genera la contraseña provisional y la muestra UNA vez
    manage.py acceso_restablecer_admin --dni 1042888795 --secreto-stdin # la lee de la entrada estándar (una línea)

La contraseña nunca va como argumento (se vería en el listado de procesos).
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand, CommandError

from acceso.aplicacion.consola import RestablecerAdministradorDeConsola
from acceso.dominio import errores
from acceso.infraestructura.contenedor import servicios


class Command(BaseCommand):
    help = "Restablece la contraseña de una cuenta de administración (emergencia: sólo desde la consola del equipo)."

    def add_arguments(self, parser):
        parser.add_argument("--dni", required=True, help="El documento (o correo) de la cuenta de administración.")
        parser.add_argument("--secreto-stdin", action="store_true", help="Lee la contraseña provisional de la entrada estándar en vez de generarla.")

    def handle(self, *args, **opciones):
        secreto = sys.stdin.readline().strip() if opciones["secreto_stdin"] else None
        try:
            salida = RestablecerAdministradorDeConsola(servicios()).ejecutar(opciones["dni"], secreto)
        except errores.ErrorAcceso as error:
            raise CommandError(f"{error.codigo}: {error.detalle} {error.extra.get('reglas') or ''}".strip())
        self.stdout.write(self.style.SUCCESS(f"Contraseña de {salida['alias']} restablecida; se cerraron {salida['sesiones_revocadas']} sesiones."))
        self.stdout.write(self.style.WARNING(f"Contraseña provisional (no se volverá a mostrar; debe cambiarla al entrar): {salida['secreto_provisional']}"))
