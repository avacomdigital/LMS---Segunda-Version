"""
Reglas de desacoplamiento y de la regla de oro (artículo 14): dominio y aplicación no conocen el framework; las vistas no tocan el ORM; el esquema es sólo
de evaluación, sin curso ni claves; el incidente es de sólo inserción; todo evento y toda acción auditada están en sus catálogos cerrados.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from audit.dominio import catalogos as catalogo_audit

from ..dominio import catalogos as cat

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

    def test_dominio_y_aplicacion_no_tocan_el_orm_de_otros_modulos(self):
        """Lo ajeno entra por un puerto: ni `models` ni `objects` ni la biblioteca directamente."""
        for carpeta in ("dominio", "aplicacion"):
            for archivo in (RAIZ / carpeta).rglob("*.py"):
                texto = archivo.read_text(encoding="utf-8")
                self.assertNotIn(".objects.", texto, archivo.name)
                self.assertNotRegex(texto, r"^\s*from\s+\.\.?\s+import\s+models", archivo.name)
                self.assertNotIn("biblioteca.contenido_v2", texto, archivo.name)

    def test_las_vistas_no_tocan_el_orm_ni_la_biblioteca_directamente(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("from .. import models", texto)
        self.assertNotIn("from ..models", texto)
        self.assertNotIn(".objects.", texto)
        self.assertNotIn("contenido_v2", texto)

    def test_el_esquema_es_solo_de_evaluacion_sin_curso_ni_claves(self):
        """Regla de oro (artículo 14): ninguna tabla de curso, asignatura, lección, objeto, pregunta ni opción, y ninguna columna que pueda guardar una clave."""
        from django.apps import apps

        modelos = apps.get_app_config("evaluacion").get_models()
        tablas = {m._meta.db_table for m in modelos}
        self.assertEqual(tablas, {"m10_asignacion", "m10_admision", "m10_intento_formal", "m10_incidente", "m10_evento_salida"})
        for tabla in tablas:
            self.assertTrue(tabla.startswith("m10_"), tabla)
            for prohibida in ("curso", "asignatura", "leccion", "objeto", "lamina", "bloque", "medio", "pregunta", "opcion", "materia"):
                self.assertNotIn(prohibida, tabla, f"{tabla} parece una tabla de contenido")
        for modelo in apps.get_app_config("evaluacion").get_models():
            for campo in modelo._meta.get_fields():
                self.assertNotIn(campo.name, {"correcta", "solucion", "enunciado", "prompt", "texto_pregunta", "respuesta_correcta"},
                                 f"{modelo.__name__}.{campo.name}")
                self.assertFalse(campo.name.startswith("clave"), f"{modelo.__name__}.{campo.name}")

    def test_el_incidente_es_de_solo_insercion(self):
        """Ni el repositorio ni ningún caso de uso actualiza o borra un incidente (BR-077): alimenta el expediente y no modifica nada."""
        from ..infraestructura.repositorios import IncidentesDjango

        publicos = {n for n in dir(IncidentesDjango) if not n.startswith("_")}
        self.assertEqual(publicos, {"crear", "de_intento", "de_intentos"})
        for archivo in RAIZ.rglob("*.py"):
            if "tests" in archivo.parts or "migrations" in archivo.parts:
                continue
            texto = archivo.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"Incidente\.objects\.[^\n]*\.(update|delete)\(", archivo.name)

    def test_el_dominio_nunca_asigna_anulado_fuera_de_anular(self):
        """INV-018 por código: en todo el módulo, `cat.ANULADO` aparece como destino de estado únicamente en `anular` y en sus tablas de lectura."""
        patron = re.compile(r'"estado":\s*cat\.ANULADO|estado=cat\.ANULADO')
        sospechosos = []
        for archivo in RAIZ.rglob("*.py"):
            if "tests" in archivo.parts or "migrations" in archivo.parts:
                continue
            for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), start=1):
                if not patron.search(linea):
                    continue
                relativo = archivo.relative_to(RAIZ).as_posix()
                es_la_restriccion_de_la_base = relativo == "models.py" and "Q(estado=cat.ANULADO)" in linea
                es_el_asiento_de_anular = relativo == "aplicacion/intentos.py" and "nuevo=" in linea       # el asiento DESPUÉS de `int_dom.anular`
                es_anular = relativo == "dominio/intento.py"
                if not (es_la_restriccion_de_la_base or es_el_asiento_de_anular or es_anular):
                    sospechosos.append(f"{relativo}:{n}")
        self.assertEqual(sospechosos, [])

    def test_los_eventos_son_los_del_maestro_mas_los_propios(self):
        self.assertEqual(len(cat.EVENTOS_DEL_MAESTRO), 14)
        self.assertEqual(len(set(cat.EVENTOS)), len(cat.EVENTOS))
        for fuera in cat.NO_SE_PUBLICAN_AQUI:               # FUN-103 y FUN-104 son de la biblioteca
            self.assertNotIn(fuera, cat.EVENTOS)
        self.assertTrue(all(e.startswith("evaluacion.") and e.endswith(".v1") for e in cat.EVENTOS))

    def test_los_permisos_son_los_once_del_maestro_mas_cinco_del_proyecto(self):
        self.assertEqual(len(cat.PERMISOS_DEL_MAESTRO), 11)
        self.assertEqual(len(set(cat.PERMISOS_DEL_ALUMNO + cat.PERMISOS_DEL_DOCENTE)), 14)         # create e item.create no tienen función en el LMS
        from acceso.dominio import plantillas

        catalogo = {c for c, *_ in plantillas.PERMISOS if c.startswith("assessment.")}
        self.assertEqual(catalogo, set(cat.PERMISOS_DEL_MAESTRO) | {cat.P_READ, cat.P_REACTIVATE, cat.P_VOID, cat.P_REVIEW, cat.P_RESULTS_VIEW})
        self.assertEqual(len(catalogo), 16)

    def test_toda_accion_auditada_esta_en_el_catalogo_cerrado_de_audit(self):
        """Una clave fuera del catálogo falla en pruebas y en producción se asienta como `auditoria.accion_desconocida`: se busca antes de que ocurra."""
        literales = set()
        for archivo in RAIZ.rglob("*.py"):
            if "tests" in archivo.parts or "migrations" in archivo.parts:
                continue
            literales.update(re.findall(r'"((?:evaluacion|calificacion|administracion|aula)\.[a-z_.]+)"', archivo.read_text(encoding="utf-8")))
        literales = {x for x in literales if not x.endswith(".v1")}
        literales.update({cat.A_INTENTO_ABIERTO, cat.A_INTENTO_ENTREGADO, cat.A_INTENTO_ANULADO, cat.A_PUNTAJE_MODIFICADO, cat.A_NIVEL_EXCEPCION})
        desconocidas = sorted(a for a in literales if catalogo_audit.resolver(a) is None)
        self.assertEqual(desconocidas, [])

    def test_el_catalogo_de_incidentes_es_cerrado_y_la_tableta_solo_informa_los_suyos(self):
        self.assertEqual(set(cat.INCIDENTES_DE_LA_TABLETA), {t.clave for t in cat.INCIDENTES.values() if t.origen == cat.O_TABLETA})
        for solo_del_nodo in ("desconexion", "reconexion", "reinicio_nodo", "reactivado", "degradacion", "admitido_bajo_nivel", "tiempo_agotado"):
            self.assertNotIn(solo_del_nodo, cat.INCIDENTES_DE_LA_TABLETA)
        self.assertTrue(all(t.severidad in cat.SEVERIDADES for t in cat.INCIDENTES.values()))
