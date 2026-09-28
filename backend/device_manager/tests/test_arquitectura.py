"""Regla de desacoplamiento: dominio y aplicación no conocen el framework; las vistas no tocan el ORM;
las tablas son m09_* y ninguna guarda contenido del curso."""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

PROHIBIDOS = ("django", "rest_framework", "pydantic", "sqlalchemy", "fastapi")
RAIZ = Path(__file__).resolve().parent.parent


class ArquitecturaTests(SimpleTestCase):
    def test_dominio_y_aplicacion_no_importan_frameworks(self):
        patron = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
        violaciones = []
        for carpeta in ("dominio", "aplicacion"):
            for archivo in (RAIZ / carpeta).rglob("*.py"):
                for modulo in patron.findall(archivo.read_text(encoding="utf-8")):
                    if modulo.split(".")[0] in PROHIBIDOS:
                        violaciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
        self.assertEqual(violaciones, [])

    def test_las_vistas_no_tocan_el_orm(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("from .. import models", texto)
        self.assertNotIn("from ..models", texto)
        self.assertNotIn(".objects.", texto)

    def test_el_esquema_es_m09_y_no_guarda_contenido(self):
        from django.apps import apps

        modelos = apps.get_app_config("device_manager").get_models()
        tablas = {m._meta.db_table for m in modelos}
        self.assertEqual(tablas, {"m09_dispositivo", "m09_dim_sesion_alumno", "m09_evento_salida"})
        for tabla in tablas:
            for prohibida in ("curso", "leccion", "objeto", "pregunta", "opcion"):
                self.assertNotIn(prohibida, tabla)

    def test_acceso_ya_no_es_dueno_de_dispositivo(self):
        from django.apps import apps

        nombres = {m.__name__ for m in apps.get_app_config("acceso").get_models()}
        self.assertNotIn("Dispositivo", nombres)
        sesion = apps.get_model("acceso", "Sesion")
        self.assertEqual(sesion._meta.get_field("dispositivo").remote_field.model._meta.db_table, "m09_dispositivo")
