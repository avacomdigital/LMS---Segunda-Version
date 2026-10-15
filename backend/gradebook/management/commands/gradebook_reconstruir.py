"""
FUN-129 · Reconstruir lo derivado del Gradebook tras restaurar un respaldo o cuando alguien dude de una cifra.

    python manage.py gradebook_reconstruir                 vuelve a calcular el resultado por asignación y el agregado por periodo
    python manage.py gradebook_reconstruir --reproducir    además reinicia la marca de lectura y vuelve a aplicar TODOS los eventos de MOD-010 (idempotente:
                                                           sólo se registra lo que faltaba; nada se duplica ni se pisa)

No toca ninguna calificación, ajuste ni versión: sólo lo que se deduce de ellos. Corre como `sistema` (el nodo), sin sesión.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from gradebook.aplicacion.consumidor import ReproducirYReconstruir
from gradebook.aplicacion.puertos import Actor
from gradebook.dominio import catalogos as cat
from gradebook.infraestructura.contenedor import servicios


class Command(BaseCommand):
    help = "Reconstruye los resultados por asignación y los agregados por periodo del Gradebook (FUN-129)."

    def add_arguments(self, parser):
        parser.add_argument("--reproducir", action="store_true", help="Vuelve a leer todos los eventos de MOD-010 desde el principio antes de reconstruir.")

    def handle(self, *args, **opciones):
        resultado = ReproducirYReconstruir(servicios()).ejecutar(Actor(id=cat.SISTEMA, rotulo="sistema", nivel=3), reproducir=bool(opciones["reproducir"]), desde_el_sistema=True)
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
