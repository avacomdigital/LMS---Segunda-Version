"""
`manage.py acceso_pin_maestro`: el estado del PIN maestro y, con --cambiar, su reemplazo (RB-43). Es la salida del técnico cuando el administrador
perdió el PIN o se filtró y no puede entrar a cambiarlo (RN-04: el PIN no se recupera, se reemplaza).

    manage.py acceso_pin_maestro                          # estado: configurado, vence en…, días restantes (nunca el PIN)
    manage.py acceso_pin_maestro --cambiar                # lee el PIN nuevo de la entrada estándar (una línea)

El PIN nuevo NUNCA va como argumento —se vería en el listado de procesos del equipo—: sale de la entrada estándar o de la variable de entorno
AVACOM_LMS_PIN_MAESTRO_NUEVO. Queda auditado con `actor = sistema` y `motivo = consola`.
"""
from __future__ import annotations

import os
import sys

from django.core.management.base import BaseCommand, CommandError

from acceso.aplicacion.consola import CambiarPinMaestroDeConsola, EstadoPinMaestroDeConsola
from acceso.dominio import errores
from acceso.infraestructura.contenedor import servicios


class Command(BaseCommand):
    help = "Muestra el estado del PIN maestro o, con --cambiar, lo reemplaza (el nuevo se lee de la entrada estándar)."

    def add_arguments(self, parser):
        parser.add_argument("--cambiar", action="store_true", help="Reemplaza el PIN maestro; el nuevo se lee de la entrada estándar.")

    def handle(self, *args, **opciones):
        try:
            if opciones["cambiar"]:
                nuevo = (os.environ.get("AVACOM_LMS_PIN_MAESTRO_NUEVO") or sys.stdin.readline()).strip()
                if not nuevo:
                    raise CommandError("Falta el PIN nuevo: escríbelo por la entrada estándar o en AVACOM_LMS_PIN_MAESTRO_NUEVO. "
                                       "No se acepta como argumento para que no quede a la vista en el listado de procesos.")
                salida = CambiarPinMaestroDeConsola(servicios()).ejecutar(nuevo)
                self.stdout.write(self.style.SUCCESS(f"PIN maestro reemplazado. Vence en {salida['dias_restantes']} días. No se vuelve a mostrar."))
                return
            estado = EstadoPinMaestroDeConsola(servicios()).ejecutar()
        except errores.ErrorAcceso as error:
            raise CommandError(f"{error.codigo}: {error.detalle}")
        if not estado["configurado"]:
            self.stdout.write(self.style.WARNING("PIN maestro: sin configurar."))
            return
        texto = "VENCIDO" if estado["vencido"] else f"vigente · quedan {estado['dias_restantes']} días"
        self.stdout.write(f"PIN maestro: {texto}" + (" · por vencer: avisa a la administración" if estado["aviso"] and not estado["vencido"] else ""))
        if estado["bloqueado_hasta"]:
            self.stdout.write(self.style.WARNING("Hay equipos bloqueados por intentos fallidos."))
