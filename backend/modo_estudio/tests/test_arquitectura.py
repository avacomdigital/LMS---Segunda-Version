"""
Reglas de desacoplamiento de MOD-008 (hexagonal como el resto del repo): el dominio y la aplicación no conocen el framework ni los adaptadores, las
vistas no tocan el ORM, todas las tablas son m08_* y ninguna guarda contenido del curso ni claves de respuesta (regla de oro, artículo 14), y el
módulo nunca toca los intentos de evaluación formal (`m07_intento`, `m10_intento`; BR-055).
"""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

PROHIBIDOS = ("django", "rest_framework", "pydantic", "sqlalchemy", "fastapi")
RAIZ = Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
MODELOS_AJENOS = re.compile(r"from\s+(?:classroom_engine|expediente)\s+import\s+[^\n]*\bmodels\b")
INTENTOS_FORMALES = re.compile(r"\b(?:IntentoRespuesta|IntentoPregunta)\b")


def fuentes(*carpetas: str):
    for carpeta in carpetas:
        yield from ((RAIZ / carpeta).rglob("*.py"))


class ArquitecturaTests(SimpleTestCase):
    def test_dominio_y_aplicacion_no_importan_frameworks(self):
        violaciones = []
        for archivo in fuentes("dominio", "aplicacion"):
            for modulo in IMPORTACION.findall(archivo.read_text(encoding="utf-8")):
                if modulo.split(".")[0] in PROHIBIDOS:
                    violaciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
        self.assertEqual(violaciones, [])

    def test_las_dependencias_apuntan_hacia_adentro(self):
        """El dominio no conoce la aplicación ni los adaptadores; la aplicación no conoce los adaptadores."""
        violaciones = []
        for carpeta, prohibidas in (("dominio", ("aplicacion", "infraestructura", "interfaces", "models")),
                                    ("aplicacion", ("infraestructura", "interfaces", "models"))):
            for archivo in fuentes(carpeta):
                for modulo in IMPORTACION.findall(archivo.read_text(encoding="utf-8")):
                    destino = modulo.lstrip(".").split(".")[0] if modulo.startswith(".") else ""
                    if modulo.startswith("modo_estudio."):
                        destino = modulo.split(".")[1]
                    if destino in prohibidas:
                        violaciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
        self.assertEqual(violaciones, [])

    def test_de_los_otros_modulos_el_dominio_y_la_aplicacion_solo_usan_reglas_puras_y_puertos(self):
        """De `classroom_engine` sólo se reutilizan sus reglas puras (`dominio`) y el tipo de un medio (`aplicacion.puertos`): nunca su ORM ni sus adaptadores."""
        permitidos = ("classroom_engine.dominio", "classroom_engine.aplicacion.puertos")
        violaciones = []
        for archivo in fuentes("dominio", "aplicacion"):
            for modulo in IMPORTACION.findall(archivo.read_text(encoding="utf-8")):
                ajeno = modulo.split(".")[0] in ("classroom_engine", "device_manager", "acceso", "expediente", "biblioteca")
                if ajeno and not modulo.startswith(permitidos):
                    violaciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
        self.assertEqual(violaciones, [])

    def test_las_vistas_no_tocan_el_orm_ni_la_biblioteca_directamente(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("from .. import models", texto)
        self.assertNotIn("from ..models", texto)
        self.assertNotIn(".objects.", texto)
        self.assertNotIn("infraestructura.repositorios", texto)
        self.assertNotIn("cliente_biblioteca", texto)
        self.assertNotIn("from biblioteca", texto)

    def test_el_esquema_es_m08_y_no_guarda_contenido_ni_claves(self):
        from django.apps import apps

        modelos = list(apps.get_app_config("modo_estudio").get_models())
        tablas = {m._meta.db_table for m in modelos}
        self.assertEqual(tablas, {"m08_asignacion", "m08_tarea", "m08_paquete", "m08_practica", "m08_sincronizacion", "m08_evento_salida"})
        for tabla in tablas:
            self.assertTrue(tabla.startswith("m08_"), tabla)
            for prohibida in ("curso", "asignatura", "leccion", "objeto", "lamina", "bloque", "medio", "pregunta", "opcion", "materia", "clave"):
                self.assertNotIn(prohibida, tabla, f"{tabla} parece una tabla de contenido")
        for modelo in modelos:
            for campo in modelo._meta.get_fields():
                for prohibida in ("clave", "correcta", "solucion", "is_correct", "answer_key"):
                    self.assertNotIn(prohibida, campo.name, f"{modelo.__name__}.{campo.name}")

    def test_la_practica_solo_admite_el_modo_de_estudio_y_las_tablas_tienen_sus_restricciones(self):
        from django.apps import apps

        restricciones = {c.name for c in apps.get_model("modo_estudio", "Practica")._meta.constraints}
        self.assertTrue({"ck_m08_practica_modo_estudio", "ux_m08_practica_numero", "ux_m08_practica_en_curso"} <= restricciones)
        self.assertIn("ux_m08_sync_emisor_secuencia", {c.name for c in apps.get_model("modo_estudio", "Sincronizacion")._meta.constraints})   # BR-060
        self.assertIn("ux_m08_paquete", {c.name for c in apps.get_model("modo_estudio", "Paquete")._meta.constraints})
        self.assertIn("ux_m08_tarea", {c.name for c in apps.get_model("modo_estudio", "Tarea")._meta.constraints})

    def test_el_modulo_nunca_toca_los_intentos_de_evaluacion_formal(self):
        """BR-055: la práctica no consume ni modifica `m07_intento` ni `m10_intento`. El código de producción no importa los modelos del aula ni del
        expediente (de donde vienen esos intentos): del expediente sólo usa `expediente.servicios` (progreso y auditoría)."""
        violaciones = []
        for archivo in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            texto = archivo.read_text(encoding="utf-8")
            for modulo in IMPORTACION.findall(texto):
                if modulo.startswith(("classroom_engine.models", "expediente.models")):
                    violaciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
            if MODELOS_AJENOS.search(texto):
                violaciones.append(f"{archivo.relative_to(RAIZ)} importa los modelos de otro módulo")
            if INTENTOS_FORMALES.search(texto):
                violaciones.append(f"{archivo.relative_to(RAIZ)} usa un intento formal")
        self.assertEqual(violaciones, [])

    def test_lo_que_se_le_dice_al_alumno_nunca_habla_de_notas(self):
        """DEC-032 · BR-055: los mensajes de la práctica nunca se llaman nota, examen ni evaluación."""
        texto = (RAIZ / "dominio" / "practica.py").read_text(encoding="utf-8")
        mensajes = re.findall(r'^MENSAJE_\w+ = "([^"]+)"', texto, re.MULTILINE)
        self.assertGreaterEqual(len(mensajes), 5)
        for mensaje in mensajes:
            for palabra in ("nota", "examen", "evaluación", "evaluacion"):
                self.assertNotIn(palabra, mensaje.lower())
