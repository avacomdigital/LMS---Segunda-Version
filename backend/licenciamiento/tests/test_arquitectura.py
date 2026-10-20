"""
Reglas de desacoplamiento y de frontera de MOD-018 (hexagonal, como el resto del repo) y las del prompt que se pueden comprobar leyendo el código y el esquema:

  · el dominio y la aplicación no conocen el framework, los adaptadores ni los otros módulos; las vistas no tocan el ORM
  · R-06 · el dominio y la aplicación NO leen ningún reloj: reciben el instante (un reloj, una sola autoridad: el nodo)
  · R-08 · licenciamiento es dueño de `m18_*` y no lee ni escribe `m01_*` ni `m09_*`: lo ajeno entra por el `servicios.py` de cada dueño; ninguna clave foránea sale del módulo
  · R-13 · nada del módulo habla con internet
  · P-03 · el código del nodo no trae una clave privada de emisión, un generador de licencias ni la llave de desarrollo
  · R-09 · permisos y acciones de bitácora están en sus catálogos cerrados; `makemigrations --check` al día
"""
from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from licenciamiento.dominio import catalogos as cat

RAIZ =Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
PROHIBIDOS = ("django", "rest_framework", "channels", "pydantic", "sqlalchemy", "fastapi")
OTROS_MODULOS = ("acceso", "classroom_engine", "modo_estudio", "evaluacion", "device_manager", "expediente", "biblioteca", "audit", "gradebook", "search", "cola_medios", "reporting")
RELOJES = re.compile(r"\btime\.(?:time|time_ns|monotonic|monotonic_ns|perf_counter)\s*\(|\bdatetime\.(?:now|utcnow|today)\s*\(|\btimezone\.now\s*\(|\bdate\.today\s*\(")
INTERNET = ("requests", "urllib", "http", "socket", "ftplib", "smtplib", "webbrowser", "aiohttp", "httpx", "xmlrpc", "ssl")


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
        for carpeta, prohibidas in (("dominio", ("aplicacion", "infraestructura", "interfaces", "models")), ("aplicacion", ("infraestructura", "interfaces", "models"))):
            for a in fuentes(carpeta):
                for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")):
                    destino = mod.lstrip(".").split(".")[0] if mod.startswith(".") else ""
                    if mod.startswith("licenciamiento."):
                        destino = mod.split(".")[1]
                    if destino in prohibidas:
                        violaciones.append(f"{a.relative_to(RAIZ)} importa {mod}")
        self.assertEqual(violaciones, [])

    def test_el_dominio_y_la_aplicacion_no_conocen_a_los_otros_modulos(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                       if mod.split(".")[0] in OTROS_MODULOS]
        self.assertEqual(violaciones, [])

    def test_r_06_el_dominio_y_la_aplicacion_no_leen_ningun_reloj(self):
        """El instante entra por un puerto (`Reloj`); una prueba lo mueve a voluntad y nunca se crea una sexta copia de `RelojNodo`."""
        violaciones = [f"{a.relative_to(RAIZ)}: {RELOJES.search(a.read_text(encoding='utf-8')).group(0)}" for a in fuentes("dominio", "aplicacion")
                       if RELOJES.search(a.read_text(encoding="utf-8"))]
        self.assertEqual(violaciones, [])

    def test_r_13_nada_del_modulo_habla_con_internet(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces", "management")
                       for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")) if mod.split(".")[0] in INTERNET and not mod.startswith("urllib.parse")]
        self.assertEqual(violaciones, [])

    def test_ningun_archivo_del_modulo_trae_una_clave_privada_ni_un_generador_de_licencias(self):
        """P-03: el nodo sólo VERIFICA licencias. La clave de emisión vive fuera (HSM o equipo sin red) y el emisor interno está en `tools/licencias/`, que el instalador no copia."""
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces", "management"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotIn("BEGIN PRIVATE KEY", texto, a.name)
            self.assertNotIn("BEGIN EC PRIVATE KEY", texto, a.name)
            self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", texto, a.name)
            self.assertNotRegex(texto, r"avacom-licencia-desarrollo", a.name)          # la semilla de la llave de desarrollo sólo existe en las pruebas
            self.assertNotRegex(texto, r"def\s+(emitir|firmar_licencia|generar_licencia)\b", a.name)

    def test_el_dominio_no_usa_azar_inseguro(self):
        for a in fuentes("dominio"):
            self.assertNotRegex(a.read_text(encoding="utf-8"), r"^\s*import random|from random import", a.name)


class FronteraTests(SimpleTestCase):
    def test_r_08_licenciamiento_no_lee_ni_escribe_las_tablas_de_otro_modulo(self):
        """Lo ajeno (cuántos equipos, cuántos usuarios) entra como NÚMEROS por el `servicios.py` del dueño, y sólo desde `infraestructura/conteos.py`."""
        modelos_ajenos = re.compile(r"\b(acceso|device_manager|classroom_engine|evaluacion|modo_estudio|gradebook|reporting|search|expediente|audit|cola_medios)\.models\b")
        violaciones = [str(a.relative_to(RAIZ)) for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces") if modelos_ajenos.search(a.read_text(encoding="utf-8"))]
        self.assertEqual(violaciones, [])
        for a in fuentes("dominio", "aplicacion", "interfaces"):
            texto = a.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"from\s+(acceso|device_manager)\s+import\s+servicios", f"{a.name} habla con otro módulo: eso se hace en infraestructura/")
        conteos = (RAIZ / "infraestructura" / "conteos.py").read_text(encoding="utf-8")
        self.assertIn("from device_manager import servicios", conteos)
        self.assertIn("from acceso import servicios", conteos)

    def test_el_resto_del_proyecto_consulta_la_licencia_solo_por_su_servicios(self):
        permitidos = {"licenciamiento", "licenciamiento.servicios", "licenciamiento.dominio.errores"}      # la fachada y su error (`CupoAgotado`, para traducirlo al propio de cada módulo)
        raiz = RAIZ.parent
        for modulo in ("acceso", "device_manager", "classroom_engine", "expediente", "audit"):
            for a in (raiz / modulo).rglob("*.py"):
                if "tests" in a.parts or "migrations" in a.parts:
                    continue
                texto = a.read_text(encoding="utf-8")
                for mod in re.findall(r"^\s*(?:from|import)\s+(licenciamiento[\w\.]*)", texto, re.MULTILINE):
                    self.assertIn(mod, permitidos, f"{a.relative_to(raiz)} importa {mod}")
                for nombre in re.findall(r"^\s*from\s+licenciamiento\s+import\s+(\w+)", texto, re.MULTILINE):
                    self.assertEqual(nombre, "servicios", f"{a.relative_to(raiz)} importa licenciamiento.{nombre}")

    def test_los_repositorios_no_actualizan_ni_borran_el_historial_ni_las_observaciones(self):
        """De sólo inserción: este archivo no tiene un solo update ni delete sobre `Licencia` ni `Observacion`."""
        texto = (RAIZ / "infraestructura" / "repositorios.py").read_text(encoding="utf-8")
        for linea in texto.splitlines():
            if re.search(r"m\.(Licencia|Observacion)\.objects", linea):
                self.assertNotRegex(linea, r"\.(update|delete|bulk_update|update_or_create)\(", linea)

    def test_el_instalador_no_copia_las_pruebas_ni_la_llave_de_desarrollo_al_paquete(self):
        """P-03: el emisor de pruebas y la llave de desarrollo existen sólo en el repositorio. Lo comprueba el script de compilación (y, sobre el paquete real, `Build-Installer.ps1` al terminar)."""
        script = (RAIZ.parent.parent / "installer" / "build" / "Build-Installer.ps1").read_text(encoding="utf-8")
        self.assertIn("licenciamiento\\tests", script)
        self.assertIn("desarrollo.json", script)
        self.assertIn(".avacom-canal", script)


class EsquemaTests(TestCase):
    def modelos(self):
        return list(apps.get_app_config("licenciamiento").get_models())

    def test_son_las_tablas_m18_y_cada_una_esta_clasificada_una_sola_vez(self):
        from .. import models as m
        tablas = sorted(x._meta.db_table for x in self.modelos())
        self.assertTrue(all(t.startswith("m18_") for t in tablas), tablas)
        self.assertEqual(len(tablas), 6)
        self.assertEqual(sorted(m.TABLAS_DERIVADAS + m.TABLAS_PROPIAS), tablas)
        self.assertEqual(set(m.TABLAS_DERIVADAS) & set(m.TABLAS_PROPIAS), set())

    def test_ninguna_clave_foranea_sale_del_modulo_y_ninguna_columna_guarda_personas_ni_claves_de_datos(self):
        prohibidas = re.compile(r"nombre|alias|apellido|alumno|usuario_id|persona|clave_datos|secreto|password|pin|token|clave_privada|privada")
        for modelo in self.modelos():
            for campo in modelo._meta.get_fields():
                if campo.is_relation and not campo.auto_created:
                    self.assertEqual(campo.related_model._meta.app_label, "licenciamiento", f"{modelo._meta.db_table}.{campo.name}")
                self.assertNotRegex(campo.name, prohibidas, f"{modelo._meta.db_table}.{campo.name}")
        self.assertEqual([m for m in self.modelos() if any(c.is_relation for c in m._meta.get_fields() if not c.auto_created)], [])     # ni una sola relación

    def test_la_migracion_esta_al_dia(self):
        call_command("makemigrations", "licenciamiento", "--check", "--dry-run", verbosity=0)


class CatalogosTests(TestCase):
    def test_las_acciones_de_bitacora_estan_en_el_catalogo_cerrado_con_su_modulo_y_su_evento(self):
        from audit.dominio import catalogos as catalogo_audit
        for accion in cat.ACCIONES_DE_AUDITORIA:
            definicion = catalogo_audit.resolver(accion)
            self.assertIsNotNone(definicion, accion)
            self.assertEqual(definicion.modulo, catalogo_audit.M_LICENCIA, accion)
        self.assertEqual(catalogo_audit.modulo_de("licencia.lo_que_sea"), catalogo_audit.M_LICENCIA)
        self.assertEqual(catalogo_audit.resolver(cat.A_GRACIA).evento_origen, cat.EV_GRACIA)
        self.assertEqual(catalogo_audit.resolver(cat.A_DEGRADADA).evento_origen, cat.EV_DEGRADADAS)
        # Lo que ya existía no se tocó: la acción reservada de la instalación sigue en su sitio
        self.assertIsNotNone(catalogo_audit.resolver("instalacion.licencia_activada"))

    def test_los_eventos_son_los_siete_del_maestro_versionados_mas_las_extensiones_marcadas(self):
        self.assertEqual(sorted(cat.EVENTOS_DEL_MAESTRO), sorted([
            "licencia.activada.v1", "licencia.validada.v1", "licencia.consumo_calculado.v1", "licencia.renovada.v1", "licencia.periodo_gracia_iniciado.v1",
            "licencia.funciones_degradadas.v1", "licencia.reactivada.v1"]))
        self.assertTrue(all(e.startswith("licencia.") and e.endswith(".v1") for e in cat.EVENTOS))
        self.assertEqual(set(cat.EVENTOS_EXTENDIDOS) & set(cat.EVENTOS_DEL_MAESTRO), set())

    def test_las_capacidades_licenciables_no_incluyen_el_nucleo(self):
        self.assertEqual(sorted(cat.CAPACIDADES_LICENCIABLES), ["administracion_avanzada", "busqueda", "importacion", "reportes"])
