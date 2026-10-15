"""
`manage.py reporting_reconstruir` · FUN-147 / BR-007: borra las proyecciones de los reportes (sólo las derivadas), reinicia las marcas de lectura a cero y reproduce toda la cola de los
módulos. Es lo que se hace tras restaurar un respaldo. Nunca toca la configuración, las exportaciones ni los recientes. No corre con una clase abierta.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from reporting.aplicacion.consumidor import Reconstruir
from reporting.aplicacion.puertos import Actor
from reporting.dominio import catalogos as cat
from reporting.dominio.errores import ErrorReporting
from reporting.infraestructura.contenedor import servicios


class Command(BaseCommand):
    help = "Reconstruye las proyecciones de los reportes desde la cola de los módulos (BR-007)."

    def handle(self, *args, **opciones):
        try:
            resultado = Reconstruir(servicios()).ejecutar(Actor(id=cat.SISTEMA), desde_el_sistema=True)
        except ErrorReporting as error:
            raise CommandError(error.detalle) from error
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
