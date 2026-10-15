"""`python manage.py search_reconstruir`: reconstruye el índice de búsqueda completo desde los módulos propietarios (lo que se hace tras restaurar un respaldo, FUN-215)."""
from django.core.management.base import BaseCommand, CommandError

from search.aplicacion.indexar import Reconstruir
from search.aplicacion.puertos import Actor
from search.dominio import catalogos as cat
from search.dominio.errores import ErrorBusqueda
from search.infraestructura.contenedor import servicios


class Command(BaseCommand):
    help = "Reconstruye el índice de búsqueda (MOD-021) desde las evaluaciones, los estudios asignados y las clases. Falla si hay una clase en curso."

    def handle(self, *args, **opciones):
        try:
            resultado = Reconstruir(servicios()).ejecutar(Actor(id=cat.SISTEMA), desde_el_sistema=True)
        except ErrorBusqueda as error:
            raise CommandError(f"{error.codigo}: {error.detalle}") from error
        self.stdout.write(f"Índice reconstruido: {resultado['total']} documentos {resultado['documentos']} en {resultado['duracion_ms']} ms.")
