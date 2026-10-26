"""
Las reglas de arquitectura de MOD-016: dominio y aplicación sin Django ni módulos vecinos (R-03), sólo `m16_*` recibe escrituras (INV-023), tablas de sólo inserción, y que el catálogo de
permisos, de bitácora y de la cola única digan lo mismo que el módulo.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from django.db import connection, IntegrityError
from django.test import SimpleTestCase

from acceso.dominio import plantillas
from audit.dominio import catalogos as audit_cat
from nodo.dominio import catalogo_datos
from respaldo.dominio import catalogos as cat

from .base import BaseRespaldo, R

RAIZ = Path(__file__).resolve().parent.parent
VECINOS = {"acceso", "audit", "nodo", "classroom_engine", "licenciamiento", "search", "reporting", "gradebook", "actualizacion", "expediente", "evaluacion", "modo_estudio", "device_manager",
           "biblioteca", "cola_medios"}


def importados(carpeta: str) -> set[str]:
    salida: set[str] = set()
    for archivo in (RAIZ / carpeta).glob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                salida |= {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                salida.add(nodo.module.split(".")[0])
    return salida


class Fronteras(SimpleTestCase):
    def test_el_dominio_y_la_aplicacion_no_importan_django_ni_a_ningun_vecino(self):
        for carpeta in ("dominio", "aplicacion"):
            usados = importados(carpeta)
            self.assertFalse(usados & ({"django", "rest_framework"} | VECINOS), f"{carpeta}: {usados & ({'django', 'rest_framework'} | VECINOS)}")

    def test_la_infraestructura_toca_a_los_vecinos_solo_por_sus_servicios(self):
        for archivo in (RAIZ / "infraestructura").glob("*.py"):
            for linea in archivo.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*from (acceso|audit|nodo|classroom_engine|licenciamiento)\b([\w.]*) import (\w+)", linea)
                if m and archivo.name not in ("autorizacion.py", "repositorios.py", "adaptadores.py"):
                    self.fail(f"{archivo.name}: {linea.strip()}")
                if m and archivo.name != "autorizacion.py":
                    self.assertTrue(m.group(3) in ("servicios", "pruebas") or m.group(2) in (".servicios",), f"{archivo.name}: {linea.strip()}")

    def test_ninguna_prueba_ni_el_emisor_de_pruebas_viajan_con_la_llave_de_produccion(self):
        import json
        self.assertEqual(json.loads((RAIZ / "claves" / "produccion.json").read_text(encoding="utf-8"))["claves"], [], "se llena en la ceremonia de llaves, no antes")
        self.assertIn("sop-dev-1", (RAIZ / "claves" / "desarrollo.json").read_text(encoding="utf-8"))


class Catalogos(SimpleTestCase):
    def test_los_eventos_estan_en_el_catalogo_de_la_cola_unica(self):
        for tipo in cat.EVENTOS:
            self.assertIn(tipo, catalogo_datos.TIPOS, tipo)
            self.assertEqual(catalogo_datos.TIPOS[tipo][0], "respaldo")
        self.assertEqual({t for t in catalogo_datos.TIPOS if t.startswith("respaldo.")}, set(cat.EVENTOS))

    def test_las_acciones_estan_en_el_catalogo_de_la_bitacora(self):
        for accion in cat.ACCIONES_DE_AUDITORIA:
            self.assertIn(accion, audit_cat.ACCIONES, accion)
            self.assertEqual(audit_cat.ACCIONES[accion].modulo, "respaldo")

    def test_los_diez_eventos_del_maestro_estan_todos(self):
        for tipo in ("programado", "completo_ejecutado", "incremental_ejecutado", "punto_recuperacion_creado", "verificado", "restauracion_completada", "modulo_restaurado", "exportado",
                     "reanudado", "indice_reconstruido"):
            self.assertIn(f"respaldo.{tipo}.v1", cat.EVENTOS)

    def test_los_permisos_estan_sembrados_y_solo_el_tecnico_de_avacom_opera(self):
        for p in cat.PERMISOS:
            self.assertIn(p, plantillas.PERMISOS_POR_CODIGO)
        admin = plantillas.ROLES_SISTEMA["ADMIN"][3]
        tecnico = plantillas.ROLES_SISTEMA["TECHNICIAN"][3]
        self.assertEqual({p for p in admin if p.startswith("backup.")}, {cat.P_LEER}, "la administración de la institución SÓLO lee")
        self.assertEqual({p for p in tecnico if p.startswith("backup.")}, set(cat.PERMISOS))
        for rol in ("STUDENT", "TEACHER", "REPORTS"):
            self.assertFalse({p for p in plantillas.ROLES_SISTEMA[rol][3] if p.startswith("backup.")}, rol)
        self.assertEqual(set(cat.PERMISOS_DE_AVACOM), set(plantillas.PERMISOS_DE_RESPALDO_SOLO_DE_AVACOM))


class Siembra(BaseRespaldo):
    def test_la_migracion_siembra_lo_mismo_que_las_plantillas(self):
        from acceso.models import RolPermiso
        por_rol: dict[str, set[str]] = {}
        for rol, permiso in RolPermiso.objects.filter(permiso__codigo__startswith="backup.", rol__organizacion__isnull=True).values_list("rol__codigo", "permiso__codigo"):
            por_rol.setdefault(rol, set()).add(permiso)
        self.assertEqual(por_rol.get("ADMIN"), {cat.P_LEER})
        self.assertEqual(por_rol.get("TECHNICIAN"), set(cat.PERMISOS))
        self.assertEqual(set(por_rol), {"ADMIN", "TECHNICIAN"})


class Escrituras(BaseRespaldo):
    """INV-023: durante un respaldo, una verificación y una restauración sólo `m16_*`, la cola única y la bitácora reciben escrituras."""

    def test_solo_m16_la_cola_unica_y_la_bitacora_reciben_escrituras(self):
        escritas: set[str] = set()

        def espia(execute, sql, params, many, context):
            m = re.match(r"\s*(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM)\s+\"?(\w+)\"?", sql, re.I)
            if m:
                escritas.add(m.group(1))
            return execute(sql, params, many, context)

        self.tecnico()
        with connection.execute_wrapper(espia):
            f = self.respaldar()
            self.tecnico().post(f"{R}/respaldos/{f['respaldo_id']}/verificar/", {}, format="json")
            r = self.tecnico().post(f"{R}/restaurar/", {"respaldo_id": f["respaldo_id"], "motivo": "otro", "pase": self.pase(cat.P_RESTAURAR)}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        # `m01_sesion`: la autenticación de MOD-001 anota el último uso de la sesión en CADA petición (no es una escritura de respaldo).
        ajenas = {t for t in escritas if not (t.startswith(("m16_", "m15_", "m19_")) or t in ("sqlite_sequence", "django_session", "m01_sesion"))}
        self.assertEqual(ajenas, set(), f"respaldo escribió en tablas que no son suyas: {ajenas}")
        self.assertIn("m16_respaldo", escritas)


class SoloInsercion(BaseRespaldo):
    def test_el_historial_los_respaldos_y_los_pases_no_se_reescriben(self):
        f = self.respaldar()
        self.restaurar_con_pase = self.tecnico().post(f"{R}/restaurar/", {"respaldo_id": f["respaldo_id"], "motivo": "otro", "pase": self.pase(cat.P_RESTAURAR)}, format="json")
        from django.db import DatabaseError
        for tabla in ("m16_respaldo", "m16_historial", "m16_pase_usado"):
            with self.assertRaises((DatabaseError, IntegrityError)), connection.cursor() as c:
                c.execute(f"UPDATE {tabla} SET bytes = 1" if tabla == "m16_respaldo" else f"UPDATE {tabla} SET en = 1" if tabla == "m16_historial" else f"UPDATE {tabla} SET usado_en = 1")
