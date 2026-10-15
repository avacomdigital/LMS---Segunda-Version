"""
Reglas de desacoplamiento y de frontera de MOD-021 (hexagonal, como el resto del repo): el dominio y la aplicación no conocen el framework ni los adaptadores, las vistas no
tocan el ORM, todas las tablas son `m21_*` y NINGUNA guarda contenido de un curso ni claves (artículo 14); el módulo no toca la capa de biblioteca ni lee las tablas de otro
módulo (BR-004); y sus permisos, acciones de bitácora y eventos están declarados donde corresponde.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.test import SimpleTestCase, TestCase

from acceso.dominio import plantillas
from acceso.models import Rol, RolPermiso
from audit.dominio import catalogos as catalogo_audit

from ..dominio import catalogos as cat

RAIZ = Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
PROHIBIDOS = ("django", "rest_framework", "channels", "pydantic", "sqlalchemy", "fastapi")
OTROS_MODULOS = ("acceso", "classroom_engine", "modo_estudio", "evaluacion", "device_manager", "expediente", "biblioteca", "audit", "gradebook", "cola_medios")


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
                    if m.startswith("search."):
                        destino = m.split(".")[1]
                    if destino in prohibidas:
                        violaciones.append(f"{a.relative_to(RAIZ)} importa {m}")
        self.assertEqual(violaciones, [])

    def test_dominio_y_aplicacion_no_conocen_a_los_otros_modulos(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {m}" for a in fuentes("dominio", "aplicacion")
                       for m in IMPORTACION.findall(a.read_text(encoding="utf-8")) if m.split(".")[0] in OTROS_MODULOS]
        self.assertEqual(violaciones, [])

    def test_las_vistas_no_tocan_el_orm_ni_la_biblioteca(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("models", texto)
        self.assertNotIn(".objects.", texto)
        self.assertNotIn("biblioteca", texto.replace("la biblioteca", "").replace("AVACOM Biblioteca", ""))

    def test_search_nunca_lee_las_tablas_de_otro_modulo(self):
        """BR-004: lo ajeno se pide a la interfaz del dueño (`<módulo>.servicios`). La única lectura directa es el padrón de MOD-001, que no tiene interfaz propia."""
        prohibidos = re.compile(r"\b(evaluacion|modo_estudio|classroom_engine|gradebook|device_manager|cola_medios|expediente)\.models\b|from\s+(evaluacion|modo_estudio|classroom_engine)\.infraestructura(?!\.contenedor import RelojNodo)")
        violaciones = [str(a.relative_to(RAIZ)) for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces") if prohibidos.search(a.read_text(encoding="utf-8"))]
        self.assertEqual(violaciones, [])
        modelos_ajenos = re.compile(r"from\s+(\w+)\.models\s+import")
        for a in fuentes("infraestructura"):
            for dueno in modelos_ajenos.findall(a.read_text(encoding="utf-8")):
                self.assertEqual((dueno, a.name), ("acceso", "identidad.py"), f"{a.name} lee modelos de {dueno}")

    def test_la_capa_de_biblioteca_no_se_toca_y_solo_catalogo_py_habla_con_ella(self):
        """Decisión del proyecto: lo que Search necesita de la biblioteca se lee con su cliente tal cual, en UN adaptador de este módulo."""
        habladores = []
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            if "biblioteca" in " ".join(IMPORTACION.findall(a.read_text(encoding="utf-8"))):
                habladores.append(a.name)
        self.assertEqual(habladores, ["catalogo.py"])
        texto = (RAIZ / "infraestructura" / "catalogo.py").read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r"v2\.(\w+)", texto))), ["_lista", "_pedir", "cursos", "esquema_curso"])      # sólo LEE: nada de evaluar, sesiones de medios ni escritura

    def test_el_sql_nunca_se_arma_con_texto_del_usuario(self):
        texto = (RAIZ / "infraestructura" / "repositorios.py").read_text(encoding="utf-8")
        self.assertNotRegex(texto, r"\.execute\(\s*f?[\"'][^\"']*\{(?!_marcas|_COLUMNAS|_PESOS|' OR '|' AND ')", )
        self.assertNotIn("% (", texto)
        self.assertNotIn(".format(", texto)
        self.assertNotIn("RawSQL", texto)


class EsquemaTests(SimpleTestCase):
    def test_todas_las_tablas_son_m21_y_ninguna_guarda_contenido_de_un_curso(self):
        """Artículo 14: ni tablas ni columnas de curso, lección, recurso, pregunta, opción, medio ni claves. El único rastro de un curso es su REFERENCIA (`curso_ref`)."""
        modelos = list(apps.get_app_config("search").get_models())
        self.assertEqual({m._meta.db_table for m in modelos}, {"m21_documento", "m21_marca_lectura", "m21_estado_indice", "m21_sinonimo", "m21_evento_salida"})
        for modelo in modelos:
            self.assertTrue(modelo._meta.db_table.startswith("m21_"))
            self.assertNotRegex(modelo._meta.db_table, r"curso|leccion|objeto|pregunta|opcion|medio|bloque|lamina|materia")
        prohibidos = re.compile(r"(?<![a-z])(pregunta|opcion|enunciado|clave|correcta|solucion|leccion|objeto|bloque|lamina|html)(?![a-z])", re.I)
        campos = [f.name for m in modelos for f in m._meta.get_fields()]
        self.assertEqual([c for c in campos if prohibidos.search(c)], [])
        self.assertEqual([c for c in campos if "curso" in c], ["curso_ref"])

    def test_las_acciones_de_la_bitacora_estan_en_el_catalogo_de_mod_019(self):
        for accion in (cat.A_INDICE_RECONSTRUIDO, cat.A_APERTURA_DENEGADA, cat.A_SINONIMOS_CONFIGURADOS, cat.A_EVENTO_OMITIDO):
            definicion = catalogo_audit.resolver(accion)
            self.assertIsNotNone(definicion, accion)
            self.assertEqual(definicion.modulo, catalogo_audit.M_BUSQUEDA)
        self.assertEqual(catalogo_audit.resolver(cat.A_INDICE_RECONSTRUIDO).evento_origen, cat.EV_INDICE_RECONSTRUIDO)

    def test_los_permisos_de_lectura_son_los_del_catalogo_de_mod_001(self):
        for permiso in (*cat.PERMISOS, *cat.PERMISO_DE_LECTURA.values()):
            self.assertIn(permiso, plantillas.PERMISOS_POR_CODIGO, permiso)
        self.assertEqual(set(cat.PERMISO_DE_LECTURA), set(cat.TIPOS))


class IndiceFtsTests(TestCase):
    def test_el_indice_de_texto_completo_es_una_tabla_virtual_fts5(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT sql FROM sqlite_master WHERE name = 'm21_documento_fts'")
            definicion = cursor.fetchone()[0]
        self.assertIn("fts5", definicion.lower())
        self.assertIn("remove_diacritics 0", definicion)                    # la normalización es la del dominio (conserva la ñ), no la del motor


class PermisosSembradosTests(TestCase):
    """Las plantillas y la migración `acceso/0015` dan a cada rol lo que le toca; el alumno no recibe nada de Search."""

    def alcance(self, rol: str, permiso: str):
        fila = RolPermiso.objects.filter(rol__codigo=rol, rol__organizacion__isnull=True, permiso_id=permiso).first()
        return fila.alcance if fila else None

    def test_matriz_de_roles(self):
        self.assertEqual(self.alcance("TEACHER", "search.query"), "ASSIGNED_GROUPS")
        self.assertEqual(self.alcance("ADMIN", "search.query"), "ORGANIZATION")
        self.assertEqual(self.alcance("REPORTS", "search.query"), "ORGANIZATION")
        self.assertEqual(self.alcance("ADMIN", "search.reindex"), "ORGANIZATION")
        self.assertEqual(self.alcance("TECHNICIAN", "search.reindex"), "ORGANIZATION")
        for rol, permiso in (("STUDENT", "search.query"), ("STUDENT", "search.reindex"), ("TEACHER", "search.reindex"), ("REPORTS", "search.reindex"), ("TECHNICIAN", "search.query")):
            self.assertIsNone(self.alcance(rol, permiso), (rol, permiso))

    def test_las_plantillas_coinciden_con_lo_sembrado(self):
        for codigo, (_nombre, _menu, _nivel, concedidos) in plantillas.ROLES_SISTEMA.items():
            esperado = {p: a.value for p, a in concedidos.items() if p.startswith("search.")}
            real = {f.permiso_id: f.alcance for f in RolPermiso.objects.filter(rol__codigo=codigo, rol__organizacion__isnull=True, permiso__codigo__startswith="search.")}
            self.assertEqual(real, esperado, codigo)
        self.assertTrue(Rol.objects.filter(codigo="TEACHER").exists())
