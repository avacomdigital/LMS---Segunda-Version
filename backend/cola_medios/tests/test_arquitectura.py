"""
Reglas de desacoplamiento de la cola de medios (hexagonal, como el resto del repo): el dominio y la aplicación no conocen el framework ni los adaptadores, las
vistas no tocan el ORM, todas las tablas son `cm_*` y ninguna guarda contenido del curso ni claves de respuesta (regla de oro, artículo 14).
"""
from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.test import SimpleTestCase

PROHIBIDOS = ("django", "rest_framework", "channels", "pydantic", "sqlalchemy", "fastapi")
RAIZ = Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)


def fuentes(*carpetas: str):
    for carpeta in carpetas:
        yield from (RAIZ / carpeta).rglob("*.py")


class ArquitecturaTests(SimpleTestCase):
    def test_dominio_y_aplicacion_no_importan_frameworks(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {m}" for a in fuentes("dominio", "aplicacion")
                       for m in IMPORTACION.findall(a.read_text(encoding="utf-8")) if m.split(".")[0] in PROHIBIDOS]
        self.assertEqual(violaciones, [])

    def test_las_dependencias_apuntan_hacia_adentro(self):
        violaciones = []
        for carpeta, prohibidas in (("dominio", ("aplicacion", "infraestructura", "interfaces", "models")), ("aplicacion", ("infraestructura", "interfaces", "models"))):
            for a in fuentes(carpeta):
                for m in IMPORTACION.findall(a.read_text(encoding="utf-8")):
                    destino = m.lstrip(".").split(".")[0] if m.startswith(".") else ""
                    if m.startswith("cola_medios."):
                        destino = m.split(".")[1]
                    if destino in prohibidas:
                        violaciones.append(f"{a.relative_to(RAIZ)} importa {m}")
        self.assertEqual(violaciones, [])

    def test_dominio_y_aplicacion_no_conocen_a_los_otros_modulos(self):
        ajenos = ("classroom_engine", "modo_estudio", "evaluacion", "device_manager", "acceso", "expediente", "biblioteca", "audit")
        violaciones = [f"{a.relative_to(RAIZ)} importa {m}" for a in fuentes("dominio", "aplicacion")
                       for m in IMPORTACION.findall(a.read_text(encoding="utf-8")) if m.split(".")[0] in ajenos]
        self.assertEqual(violaciones, [])

    def test_las_vistas_no_tocan_el_orm(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("models", texto)
        self.assertNotIn(".objects.", texto)

    def test_la_cola_nunca_edita_la_capa_de_biblioteca(self):
        """El adaptador de origen sólo LEE por los casos de uso del aula; nada de `contenido_v2._pedir` ni de las funciones de la biblioteca."""
        texto = (RAIZ / "infraestructura" / "origen.py").read_text(encoding="utf-8")
        self.assertNotIn("contenido_v2", texto)
        self.assertNotIn("from biblioteca import", texto)

    def test_todas_las_tablas_son_cm_y_ninguna_guarda_contenido(self):
        modelos = list(apps.get_app_config("cola_medios").get_models())
        self.assertEqual({m._meta.db_table for m in modelos}, {"cm_recurso", "cm_solicitud"})
        prohibidos = re.compile(r"(?<![a-z])(pregunta|opcion|respuesta|clave_resp|enunciado|titulo|contenido|texto|html)(?![a-z])", re.I)
        campos = [f.name for m in modelos for f in m._meta.get_fields()]
        self.assertEqual([c for c in campos if prohibidos.search(c)], [])

    def test_la_caché_en_disco_nunca_se_sirve_como_archivo_estatico(self):
        from django.conf import settings
        self.assertNotIn(str(RAIZ.parent / "cache_medios"), [str(p) for p in getattr(settings, "STATICFILES_DIRS", [])])
        urls = (RAIZ / "interfaces" / "urls.py").read_text(encoding="utf-8")
        self.assertNotIn("static", urls)
