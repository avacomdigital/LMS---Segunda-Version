"""
Reglas de desacoplamiento y de frontera de MOD-017 (hexagonal, como el resto del repo) y las del prompt que se pueden comprobar leyendo el código y el esquema:

  · el dominio y la aplicación no conocen el framework, los adaptadores ni los otros módulos; las vistas no tocan el ORM
  · R-09 · el dominio y la aplicación NO leen ningún reloj: reciben el instante (un reloj, una sola autoridad: el nodo); ninguna copia nueva de `RelojNodo`
  · R-03 · actualizacion es dueña de `m17_*` y no lee ni escribe ninguna tabla ajena: lo ajeno entra por el `servicios.py` de cada dueño; ninguna clave foránea sale del módulo
  · R-06 · nada del módulo habla con internet (el canal por internet no se construye en MVP)
  · R-07 · nada del módulo escribe en `backend/`, en el Host, en `installer/` ni en `backend.env`: sólo en la carpeta de actualizaciones
  · R-05 / P-03 · el código del nodo no trae una clave privada de publicación, un generador de paquetes ni la semilla de desarrollo
  · R-08 · permisos y acciones de bitácora están en sus catálogos cerrados; los eventos en el catálogo de la cola única; `makemigrations --check` al día
  · P-01 · `modulos.json` tiene una entrada por app del LMS
"""
from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from actualizacion.dominio import catalogos as cat

RAIZ = Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
PROHIBIDOS = ("django", "rest_framework", "channels", "pydantic", "sqlalchemy", "fastapi")
OTROS_MODULOS = ("acceso", "classroom_engine", "modo_estudio", "evaluacion", "device_manager", "expediente", "biblioteca", "audit", "gradebook", "search", "cola_medios", "reporting",
                 "licenciamiento", "nodo")
RELOJES = re.compile(r"\btime\.(?:time|time_ns|monotonic|monotonic_ns|perf_counter)\s*\(|\bdatetime\.(?:now|utcnow|today)\s*\(|\btimezone\.now\s*\(|\bdate\.today\s*\(")
INTERNET = ("requests", "urllib", "http", "socket", "ftplib", "smtplib", "webbrowser", "aiohttp", "httpx", "xmlrpc", "ssl")
APPS_DE_DJANGO = ("daphne", "django.contrib.contenttypes", "django.contrib.staticfiles", "rest_framework", "channels")


def fuentes(*carpetas: str):
    for carpeta in carpetas:
        base = RAIZ / carpeta
        if base.exists():
            yield from base.rglob("*.py")


class DominioTests(SimpleTestCase):
    def test_el_dominio_y_la_aplicacion_no_importan_frameworks(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                       if mod.split(".")[0] in PROHIBIDOS]
        self.assertEqual(violaciones, [])

    def test_las_dependencias_apuntan_hacia_adentro(self):
        violaciones = []
        for carpeta, prohibidas in (("dominio", ("aplicacion", "infraestructura", "interfaces", "models", "servicios")), ("aplicacion", ("infraestructura", "interfaces", "models", "servicios"))):
            for a in fuentes(carpeta):
                for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")):
                    destino = mod.lstrip(".").split(".")[0] if mod.startswith(".") else ""
                    if mod.startswith("actualizacion."):
                        destino = mod.split(".")[1]
                    if destino in prohibidas:
                        violaciones.append(f"{a.relative_to(RAIZ)} importa {mod}")
        self.assertEqual(violaciones, [])

    def test_el_dominio_y_la_aplicacion_no_conocen_a_los_otros_modulos(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                       if mod.split(".")[0] in OTROS_MODULOS]
        self.assertEqual(violaciones, [])

    def test_r_09_el_dominio_y_la_aplicacion_no_leen_ningun_reloj(self):
        violaciones = [f"{a.relative_to(RAIZ)}: {RELOJES.search(a.read_text(encoding='utf-8')).group(0)}" for a in fuentes("dominio", "aplicacion")
                       if RELOJES.search(a.read_text(encoding="utf-8"))]
        self.assertEqual(violaciones, [])
        texto = "\n".join(a.read_text(encoding="utf-8") for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"))
        self.assertNotRegex(texto, r"class\s+RelojNodo\b")                       # ninguna copia nueva del reloj del nodo (R-09)
        self.assertIn("from nodo import servicios as nodo", (RAIZ / "infraestructura" / "provisionales.py").read_text(encoding="utf-8"))

    def test_r_06_nada_del_modulo_habla_con_internet(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces")
                       for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")) if mod.split(".")[0] in INTERNET and not mod.startswith("urllib.parse")]
        self.assertEqual(violaciones, [])

    def test_r_07_nada_del_modulo_escribe_en_backend_ni_en_el_host(self):
        """Lo único que el módulo escribe en disco es la carpeta de actualizaciones (`infraestructura/almacen.py`): el Host es quien copia a `backend/` (P-06)."""
        escritura = re.compile(r"\bopen\([^)]*[\"'](?:w|a|x)b?[\"']|\.write_bytes\(|\.write_text\(|shutil\.copy|os\.replace\(|os\.rename\(")
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            if a.name == "almacen.py":
                continue
            self.assertIsNone(escritura.search(texto), f"{a.relative_to(RAIZ)} escribe en disco fuera del almacén")
        almacen = (RAIZ / "infraestructura" / "almacen.py").read_text(encoding="utf-8")
        for intocable in ("Program Files", "backend.env", "installer", "Runtime", "Host"):
            self.assertNotRegex(almacen, rf"Path\([^)]*{intocable}", intocable)

    def test_r_05_ningun_archivo_del_modulo_trae_una_clave_privada_ni_un_emisor(self):
        """P-03: el nodo sólo VERIFICA paquetes. La clave de publicación vive fuera y el emisor interno está en `tools/actualizacion/` (Fase 4), que el instalador no copia."""
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotIn("BEGIN PRIVATE KEY", texto, a.name)
            self.assertNotRegex(texto, r"avacom-actualizacion-desarrollo", a.name)         # la semilla de la llave de desarrollo sólo existe en las pruebas
            self.assertNotRegex(texto, r"def\s+(emitir|empaquetar|generar_paquete)\b", a.name)
        self.assertNotIn("avacom-actualizacion-desarrollo", (RAIZ / "claves" / "desarrollo.json").read_text(encoding="utf-8"))
        claves = __import__("json").loads((RAIZ / "claves" / "produccion.json").read_text(encoding="utf-8"))["claves"]
        self.assertEqual([(c["kid"], c["estado"]) for c in claves], [("upd-2026-1", "vigente")])      # ceremonia del 2026-10-22 (Q-U8): sólo la pública de producción
        self.assertEqual(len(bytes.fromhex(claves[0]["publica"])), 32)

    def test_el_dominio_no_usa_azar_inseguro(self):
        for a in fuentes("dominio", "aplicacion"):
            self.assertNotRegex(a.read_text(encoding="utf-8"), r"^\s*import random|from random import", a.name)

    def test_el_instalador_excluye_las_pruebas_y_la_llave_de_desarrollo(self):
        """`Build-Installer.ps1` excluye `actualizacion\\tests` (la copia, la huella y la comprobación de sospechosos) y la llave `desarrollo.json` (el patrón cubre cualquier carpeta),
        como hace con los de licenciamiento (P-03)."""
        script = (RAIZ.parent.parent / "installer" / "build" / "Build-Installer.ps1").read_text(encoding="utf-8")
        self.assertIn("desarrollo.json", script)
        self.assertIn("backend\\actualizacion\\tests", script)                    # robocopy /XD
        self.assertIn("(Join-Path $carpeta 'actualizacion\\tests')", script)      # la huella
        self.assertIn("(Join-Path $destinoBackend 'actualizacion\\tests')", script)   # los sospechosos
        self.assertIn("avacom-actualizacion-desarrollo", script)                 # la semilla del emisor


class FronteraTests(SimpleTestCase):
    def test_r_03_actualizacion_no_lee_ni_escribe_las_tablas_de_otro_modulo(self):
        modelos_ajenos = re.compile(r"\b(acceso|device_manager|classroom_engine|evaluacion|modo_estudio|gradebook|reporting|search|expediente|audit|cola_medios|licenciamiento|nodo)\.models\b")
        violaciones = [str(a.relative_to(RAIZ)) for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces") if modelos_ajenos.search(a.read_text(encoding="utf-8"))]
        self.assertEqual(violaciones, [])
        for a in fuentes("dominio", "aplicacion", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"from\s+(nodo|audit|classroom_engine|acceso|licenciamiento)\s+import\s+servicios", f"{a.name} habla con otro módulo: eso se hace en infraestructura/")
        provisionales = (RAIZ / "infraestructura" / "provisionales.py").read_text(encoding="utf-8")
        self.assertIn("from classroom_engine import servicios as aula", provisionales)
        repositorios = (RAIZ / "infraestructura" / "repositorios.py").read_text(encoding="utf-8")
        self.assertIn("from nodo import servicios as nodo", repositorios)
        self.assertIn("from audit import servicios as auditoria", repositorios)

    def test_el_resto_del_proyecto_consulta_la_actualizacion_solo_por_su_servicios(self):
        permitidos = {"actualizacion", "actualizacion.servicios", "actualizacion.infraestructura", "actualizacion.infraestructura.vigilante"}   # la fachada y el arranque del vigilante (asgi)
        raiz = RAIZ.parent
        for modulo in ("acceso", "device_manager", "classroom_engine", "expediente", "audit", "nodo", "licenciamiento", "avacom_lms"):
            for a in (raiz / modulo).rglob("*.py"):
                if "tests" in a.parts or "migrations" in a.parts:
                    continue
                texto = a.read_text(encoding="utf-8")
                for mod in re.findall(r"^\s*(?:from|import)\s+(actualizacion[\w\.]*)", texto, re.MULTILINE):
                    self.assertIn(mod, permitidos, f"{a.relative_to(raiz)} importa {mod}")

    def test_los_repositorios_no_actualizan_ni_borran_el_historial_ni_los_paquetes(self):
        texto = (RAIZ / "infraestructura" / "repositorios.py").read_text(encoding="utf-8")
        for linea in texto.splitlines():
            if re.search(r"m\.(Paquete|Historial)\.objects", linea):
                self.assertNotRegex(linea, r"\.(update|delete|bulk_update|update_or_create)\(", linea)

    def test_las_vistas_no_tocan_el_orm(self):
        for a in fuentes("interfaces"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"\.objects\.|from \.\. import models|from \.\.models", a.name)

    def test_la_biblioteca_solo_se_lee(self):
        """R-12: de `backend/biblioteca/` sólo se lee la constante del contrato, y sólo desde el adaptador del registro."""
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            if a.name == "registro_modulos.py":
                self.assertIn("from biblioteca.contenido_v2 import CONTRATO", texto)
                continue
            self.assertNotRegex(texto, r"^\s*(?:from|import)\s+biblioteca", a.name)


class EsquemaTests(TestCase):
    def modelos(self):
        return list(apps.get_app_config("actualizacion").get_models())

    def test_son_las_tablas_m17_y_cada_una_esta_clasificada_una_sola_vez(self):
        from .. import models as m
        tablas = sorted(x._meta.db_table for x in self.modelos())
        self.assertTrue(all(t.startswith("m17_") for t in tablas), tablas)
        self.assertEqual(tablas, ["m17_historial", "m17_paquete"])
        self.assertEqual(sorted(m.TABLAS_DERIVADAS + m.TABLAS_PROPIAS), tablas)

    def test_ninguna_clave_foranea_sale_del_modulo_y_ninguna_columna_guarda_personas_ni_rutas(self):
        prohibidas = re.compile(r"nombres|alias|apellido|alumno|usuario_id|persona|clave_datos|secreto|password|pin|token|clave_privada|privada|ruta")
        for modelo in self.modelos():
            for campo in modelo._meta.get_fields():
                if campo.is_relation and not campo.auto_created:
                    self.assertEqual(campo.related_model._meta.app_label, "actualizacion", f"{modelo._meta.db_table}.{campo.name}")
                self.assertNotRegex(campo.name, prohibidas, f"{modelo._meta.db_table}.{campo.name}")
        self.assertEqual([m for m in self.modelos() if any(c.is_relation for c in m._meta.get_fields() if not c.auto_created)], [])     # ni una sola relación

    def test_las_migraciones_estan_al_dia(self):
        call_command("makemigrations", "actualizacion", "acceso", "--check", "--dry-run", verbosity=0)

    def test_los_triggers_de_solo_insercion_existen_y_actuan(self):
        from django.db import connection
        from django.db.utils import IntegrityError, OperationalError

        from .. import models as m
        with connection.cursor() as c:
            c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'm17_%' ORDER BY name")
            self.assertEqual([r[0] for r in c.fetchall()], ["m17_historial_solo_insercion", "m17_paquete_solo_insercion"])
        fila = m.Historial.objects.create(paquete_id="", tipo=cat.H_RECHAZADO, en=1, actor="x", detalle={})
        with self.assertRaises((IntegrityError, OperationalError)):
            m.Historial.objects.filter(pk=fila.pk).update(actor="otro")


class CatalogosTests(TestCase):
    def test_las_acciones_de_bitacora_estan_en_el_catalogo_cerrado_con_su_modulo_y_su_evento(self):
        from audit.dominio import catalogos as catalogo_audit
        self.assertIn("actualizacion", catalogo_audit.MODULOS)
        for accion in cat.ACCIONES_DE_AUDITORIA:
            definicion = catalogo_audit.resolver(accion)
            self.assertIsNotNone(definicion, accion)
            self.assertEqual(definicion.modulo, catalogo_audit.M_ACTUALIZACION, accion)
        self.assertEqual(catalogo_audit.modulo_de("actualizacion.lo_que_sea"), catalogo_audit.M_ACTUALIZACION)
        for accion, evento in ((cat.A_IMPORTADO, cat.EV_IMPORTADO), (cat.A_VERIFICADO, cat.EV_VERIFICADO), (cat.A_APLICADO, cat.EV_APLICADA), (cat.A_REVERTIDO, cat.EV_REVERTIDA),
                               (cat.A_BLOQUEADA, cat.EV_BLOQUEADA), (cat.A_PROGRAMADO, cat.EV_PROGRAMADA)):
            self.assertEqual(catalogo_audit.resolver(accion).evento_origen, evento, accion)
        self.assertTrue(set(cat.EXTENSIONES_DE_AUDITORIA) < set(cat.ACCIONES_DE_AUDITORIA))

    def test_los_eventos_son_los_nueve_del_maestro_mas_las_extensiones_y_estan_en_la_cola_unica(self):
        from nodo.dominio import catalogo as catalogo_nodo
        from nodo.dominio import catalogos as cat_nodo
        self.assertEqual(sorted(cat.EVENTOS_DEL_MAESTRO), sorted([
            "actualizacion.disponible_detectada.v1", "actualizacion.paquete_importado.v1", "actualizacion.paquete_verificado.v1", "actualizacion.ventana_programada.v1",
            "actualizacion.bloqueada.v1", "actualizacion.modulo_aplicada.v1", "actualizacion.migracion_ejecutada.v1", "actualizacion.revertida.v1", "actualizacion.resultado_registrado.v1"]))
        self.assertEqual(set(cat.EVENTOS_EXTENSION) & set(cat.EVENTOS_DEL_MAESTRO), set())
        for tipo in cat.EVENTOS:
            definicion = catalogo_nodo.resolver(tipo)
            self.assertIsNotNone(definicion, f"{tipo} no está en el catálogo de la cola única: regenera nodo/dominio/catalogo_datos.py")
            self.assertEqual(definicion.modulo, cat.MODULO, tipo)
            self.assertEqual(definicion.clase, cat_nodo.CLASE_TECNICO, tipo)             # Parte XI: «Técnico: salud del equipo, servicios, respaldos, actualizaciones»
            self.assertTrue(catalogo_nodo.validar_nombre(tipo).participio, tipo)         # BR-122

    def test_los_permisos_estan_en_las_plantillas_con_sus_roles(self):
        from acceso.dominio import plantillas
        for permiso in cat.PERMISOS:
            self.assertIn(permiso, plantillas.PERMISOS_POR_CODIGO)
            self.assertEqual(plantillas.PERMISOS_POR_CODIGO[permiso][1], "actualizacion")
        admin, tecnico = plantillas.ROLES_SISTEMA["ADMIN"][3], plantillas.ROLES_SISTEMA["TECHNICIAN"][3]
        self.assertTrue(all(p in admin for p in cat.PERMISOS))
        self.assertEqual(sorted(p for p in cat.PERMISOS if p in tecnico), sorted(cat.PERMISOS_DEL_TECNICO))
        self.assertNotIn(cat.P_APLICAR, tecnico)                                        # sólo por escalada (ESC-01)
        for rol in ("TEACHER", "STUDENT", "REPORTS"):
            self.assertEqual([p for p in cat.PERMISOS if p in plantillas.ROLES_SISTEMA[rol][3]], [], rol)

    def test_modulos_json_tiene_una_entrada_por_app_del_lms(self):
        """P-01: una app sin entrada no es actualizable por separado; una entrada sin app es un error."""
        from actualizacion.infraestructura.registro_modulos import RegistroDelNodo
        registradas = set(RegistroDelNodo().registrados())
        instaladas = {a for a in settings.INSTALLED_APPS if a not in APPS_DE_DJANGO}
        self.assertEqual(registradas, instaladas)
        self.assertFalse(RegistroDelNodo().registrados()["biblioteca"].actualizable)      # R-12
        inst = RegistroDelNodo().instalacion()
        self.assertEqual(inst.contrato_biblioteca, 2)
        self.assertGreaterEqual(inst.modulos["acceso"].version_datos, 20)                 # la versión de datos es viva: la última migración aplicada
        self.assertGreaterEqual(inst.modulos["actualizacion"].version_datos, 2)

    def test_los_motivos_de_rechazo_tienen_mensaje(self):
        for motivo in cat.MOTIVOS_DE_FIRMA:
            self.assertIn(motivo, cat.MENSAJES_DE_MOTIVO)
        self.assertEqual(len(cat.ESTADOS), 9)
        self.assertEqual(len(cat.HISTORIAL), 14)
