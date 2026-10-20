"""
Reglas de desacoplamiento y de pertenencia de los datos del Gradebook: dominio y aplicación no conocen el framework; las vistas no tocan el ORM; el esquema es sólo de
calificaciones (sin intentos, respuestas, rúbricas ni claves); MOD-010 se lee sólo por su interfaz pública; el historial, las revisiones y las escalas son de sólo inserción;
y los eventos, las acciones de auditoría y los permisos están en sus catálogos cerrados.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from acceso.dominio import plantillas
from audit.dominio import catalogos as catalogo_audit

from .. import models as m
from ..dominio import catalogos as cat

PROHIBIDOS = ("django", "rest_framework", "pydantic", "sqlalchemy", "fastapi")
RAIZ = Path(__file__).resolve().parent.parent
TABLAS = {"m11_escala", "m11_escala_version", "m11_escala_tramo", "m11_config_nivel", "m11_politica", "m11_clasificacion", "m11_calificacion", "m11_calificacion_version",
          "m11_revision", "m11_resultado", "m11_agregado_periodo", "m11_marca_consumidor", "m11_evento_salida", "m11_observacion"}


def fuentes(*carpetas: str):
    for carpeta in carpetas:
        for archivo in (RAIZ / carpeta).rglob("*.py"):
            if "migrations" not in archivo.parts and "tests" not in archivo.parts:
                yield archivo


class ArquitecturaTests(SimpleTestCase):
    def test_dominio_y_aplicacion_no_importan_frameworks(self):
        patron = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
        violaciones = [f"{a.relative_to(RAIZ)} importa {modulo}" for a in fuentes("dominio", "aplicacion") for modulo in patron.findall(a.read_text(encoding="utf-8"))
                       if modulo.split(".")[0] in PROHIBIDOS]
        self.assertEqual(violaciones, [])

    def test_dominio_y_aplicacion_no_tocan_el_orm_ni_los_modulos_ajenos(self):
        for a in fuentes("dominio", "aplicacion"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotIn(".objects.", texto, a.name)
            self.assertNotRegex(texto, r"^\s*from\s+\.\.?\s+import\s+models", a.name)
            for ajeno in ("evaluacion", "acceso", "audit", "biblioteca", "classroom_engine"):
                self.assertNotRegex(texto, rf"^\s*(?:from|import)\s+{ajeno}\b", f"{a.name} importa {ajeno}")

    def test_las_vistas_no_tocan_el_orm_ni_la_biblioteca(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        for prohibido in ("from .. import models", "from ..models", ".objects.", "contenido_v2", "evaluacion.models"):
            self.assertNotIn(prohibido, texto)

    def test_mod_010_se_lee_solo_por_su_interfaz_publica(self):
        """Nada del libro importa los modelos de `m10_*`: lo que necesita de la evaluación lo pide a `evaluacion.servicios` (BR-004, escritor único)."""
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"(?:from|import)\s+evaluacion(?:\.\w+)*\.models\b", a.name)
            self.assertNotRegex(texto, r"from\s+evaluacion\s+import\s+models\b", a.name)
        permitidos = {"evaluacion.servicios", "evaluacion.dominio.errores", "evaluacion.aplicacion.puertos", "evaluacion.infraestructura.contenedor"}
        for a in fuentes("infraestructura"):
            for modulo in re.findall(r"(?:from|import)\s+(evaluacion[\w\.]*)", a.read_text(encoding="utf-8")):
                self.assertIn(modulo, permitidos | {"evaluacion"}, f"{a.name} importa {modulo}")

    def test_el_esquema_es_solo_del_libro_sin_intentos_respuestas_ni_claves(self):
        from django.apps import apps

        modelos = list(apps.get_app_config("gradebook").get_models())
        self.assertEqual({x._meta.db_table for x in modelos}, TABLAS)
        for modelo in modelos:
            for campo in modelo._meta.get_fields():
                self.assertNotIn(campo.name, {"respuestas", "respuesta", "armado", "enunciado", "correcta", "solucion", "prompt", "pregunta", "respuesta_correcta"},
                                 f"{modelo.__name__}.{campo.name}")
        for tabla in TABLAS:
            self.assertTrue(tabla.startswith("m11_"))
            self.assertNotIn("intento", tabla.replace("m11_calificacion_version", ""))

    def test_el_historial_las_revisiones_y_las_escalas_son_de_solo_insercion(self):
        from ..infraestructura.repositorios import EscalasDjango, RevisionesDjango, VersionesDjango

        self.assertEqual({n for n in dir(VersionesDjango) if not n.startswith("_")}, {"anexar", "de", "por_solicitud"})
        self.assertEqual({n for n in dir(RevisionesDjango) if not n.startswith("_")}, {"anexar", "de_intento", "por_solicitud"})
        self.assertTrue({"crear_version", "version", "ultima_version", "versiones_de"} <= {n for n in dir(EscalasDjango) if not n.startswith("_")})
        self.assertFalse({n for n in dir(EscalasDjango) if n.startswith(("actualizar", "editar", "borrar", "eliminar", "modificar"))})
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"(?:VersionCalificacion|Revision|EscalaVersion|EscalaTramo)\.objects[^\n]*\.(?:update|delete)\(", a.name)

    def test_los_once_eventos_del_documento_maestro_estan_en_el_catalogo(self):
        nombres = {"calificacion.registrada.v1", "calificacion.manual_aplicada.v1", "calificacion.rubrica_aplicada.v1", "calificacion.intento_reabierto.v1",
                   "calificacion.ajustada.v1", "calificacion.escala_convertida.v1", "calificacion.modo_cambiado.v1", "calificacion.estado_simple_calculado.v1",
                   "calificacion.agregados_recalculados.v1", "calificacion.libro_exportado.v1", "calificacion.derivadas_reconstruidas.v1"}
        self.assertEqual(set(cat.EVENTOS_DEL_MAESTRO), nombres)
        self.assertTrue(set(cat.EVENTOS_PROPUESTOS).isdisjoint(nombres))                      # lo propuesto se distingue de lo del Maestro
        self.assertTrue(all(e.startswith("calificacion.") and e.endswith(".v1") for e in cat.EVENTOS))

    def test_toda_accion_de_auditoria_del_libro_esta_en_el_catalogo_cerrado(self):
        for accion in (*cat.ACCIONES_NUEVAS, cat.A_MODIFICADA, cat.A_REABIERTA):
            definicion = catalogo_audit.ACCIONES.get(accion)
            self.assertIsNotNone(definicion, accion)
            self.assertEqual(definicion.modulo, catalogo_audit.M_EVALUACION)
        for sensible in (cat.A_MODIFICADA, cat.A_REABIERTA, cat.A_PUBLICADA, cat.A_DENEGADA):
            self.assertTrue(catalogo_audit.ACCIONES[sensible].sensible)
        for con_motivo in (cat.A_MODIFICADA, cat.A_REABIERTA, cat.A_VALORACION, cat.A_PUBLICACION_RETIRADA):
            self.assertTrue(catalogo_audit.ACCIONES[con_motivo].exige_motivo)
        # Cada evento al que apunta una acción es un evento que el módulo publica.
        for a in catalogo_audit.ACCIONES.values():
            if a.evento_origen and a.evento_origen.startswith("calificacion."):
                self.assertIn(a.evento_origen, cat.EVENTOS, a.clave)

    def test_los_permisos_del_libro_estan_sembrados_y_repartidos_como_dice_el_maestro(self):
        for permiso in (*cat.PERMISOS, cat.P_READ):
            self.assertIn(permiso, plantillas.PERMISOS_POR_CODIGO)
        self.assertEqual(set(cat.PERMISOS_DEL_MAESTRO), {"grades.modify", "grades.reopen", "grades.rubric.apply", "grades.mode.set", "grades.export"})
        self.assertEqual(cat.PERMISOS_PROPUESTOS, ("grades.publish",))
        roles = plantillas.ROLES_SISTEMA
        for permiso in cat.PERMISOS_DEL_DOCENTE:
            self.assertIn(permiso, roles["TEACHER"][3], permiso)
            self.assertNotIn(permiso, roles["ADMIN"][3], permiso)                              # la administración no califica directamente
        for permiso in cat.PERMISOS_DE_ADMINISTRACION:
            self.assertIn(permiso, roles["ADMIN"][3], permiso)
            self.assertNotIn(permiso, roles["TEACHER"][3], permiso)
        for rol in ("TECHNICIAN", "REPORTS", "STUDENT"):
            self.assertFalse([p for p in roles[rol][3] if p.startswith("grades.")], rol)       # técnico, reportes y alumno: ninguno
        self.assertNotIn("results.read", roles["TECHNICIAN"][3])


class EsquemaTests(TestCase):
    def test_no_hay_migraciones_pendientes(self):
        call_command("makemigrations", "gradebook", "--check", "--dry-run", verbosity=0)

    def test_la_base_impone_la_escala_interna_y_la_integridad(self):
        base = dict(id="c1", intento_id="i1", asignacion_id="a1", alumno_id="al1", puntaje_original=70, puntaje_efectivo=70, puntaje_fuente=70, regla_puntuacion="mod10.porcentaje.v1",
                    origen="automatica", evaluador_id="sistema")
        m.Calificacion.objects.create(**base)
        malos = [dict(id="c2", intento_id="i2", puntaje_efectivo=100.01), dict(id="c3", intento_id="i3", puntaje_original=-1), dict(id="c4", intento_id="i4", estado="inventado"),
                 dict(id="c5", intento_id="i5", evaluador_id=""), dict(id="c6", intento_id="i6", regla_puntuacion=""), dict(id="c7", intento_id="i1"),
                 dict(id="c8", intento_id="i8", estado="definitiva"), dict(id="c9", intento_id="i9", publicada_en=1, publicada_por="p"),
                 dict(id="c10", intento_id="i10", origen="otro")]
        for cambios in malos:
            with self.assertRaises(IntegrityError, msg=str(cambios)), transaction.atomic():
                m.Calificacion.objects.create(**{**base, **cambios})
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ConfigNivel.objects.create(nivel_clave="primaria", modo="calificaciones")            # el modo calificaciones exige una escala
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.ConfigNivel.objects.create(nivel_clave="universidad", modo="simple")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Politica.objects.create(id="otra", politica_intentos="al_azar")

    def test_las_escalas_se_validan_tambien_en_la_base(self):
        e = m.Escala.objects.create(id="e1", codigo="x-escala", nombre="X", tipo="numerica", creada_por="a")
        v = m.EscalaVersion.objects.create(id="v1", escala=e, numero=1, conversion="interpolada", huella="h", creada_por="a")
        for cambios in (dict(desde=0, hasta=0), dict(desde=-1, hasta=10), dict(desde=0, hasta=101)):
            with self.assertRaises(IntegrityError, msg=str(cambios)), transaction.atomic():
                m.EscalaTramo.objects.create(version=v, orden=1, clave="a", etiqueta="a", **cambios)
        m.EscalaTramo.objects.create(version=v, orden=1, clave="a", etiqueta="a", desde=0, hasta=100)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.EscalaTramo.objects.create(version=v, orden=2, clave="a", etiqueta="b", desde=0, hasta=100)        # la clave se repite en la versión
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.EscalaVersion.objects.create(id="v2", escala=e, numero=1, conversion="tramos", huella="h", creada_por="a")   # el número se repite
