"""
Reglas de desacoplamiento y de frontera de MOD-015 (hexagonal, como el resto del repo) y las del Maestro que se pueden comprobar leyendo el código y el esquema:

  · el dominio y la aplicación no conocen el framework, los adaptadores ni los otros módulos; las vistas no tocan el ORM
  · R-09 · `nodo` es el único escritor de `m15_*`, no lee tablas de otros módulos (sólo sus `servicios.py`, el contexto de MOD-019 y la política de MOD-001) y ninguna FK sale del módulo
  · P-03 / P-08 · el sobre es inmutable (trigger), la marca alta sólo sube (trigger) y el ÚNICO borrado de la cola es la purga
  · R-10 · los permisos, su reparto por rol, las acciones de bitácora y los eventos están en los catálogos cerrados
  · R-01 · las rutas núcleo existen; `makemigrations --check`; sin dependencias nuevas ni internet
"""
from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.utils import DatabaseError
from django.test import SimpleTestCase, TestCase
from django.urls import resolve

from acceso.dominio import plantillas
from acceso.models import Rol, RolPermiso
from audit.dominio import catalogos as catalogo_audit

from .. import models as m
from ..dominio import catalogo
from ..dominio import catalogos as cat
from ..infraestructura import triggers
from .base import BaseNodo

RAIZ = Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
PROHIBIDOS = ("django", "rest_framework", "channels", "pydantic", "sqlalchemy", "fastapi")
OTROS_MODULOS = ("acceso", "classroom_engine", "modo_estudio", "evaluacion", "device_manager", "expediente", "biblioteca", "audit", "gradebook", "search", "cola_medios",
                 "reporting", "licenciamiento", "cache_medios")
ESCRITURAS = re.compile(r"\.(?:save|update|create|delete|bulk_create|bulk_update|update_or_create|get_or_create)\(")


def fuentes(*carpetas: str):
    for carpeta in carpetas:
        yield from (RAIZ / carpeta).rglob("*.py")


class ArquitecturaTests(SimpleTestCase):
    def test_dominio_y_aplicacion_no_importan_frameworks(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                       if mod.split(".")[0] in PROHIBIDOS]
        self.assertEqual(violaciones, [])

    def test_las_dependencias_apuntan_hacia_adentro(self):
        violaciones = []
        for carpeta, prohibidas in (("dominio", ("aplicacion", "infraestructura", "interfaces", "models", "servicios")), ("aplicacion", ("infraestructura", "interfaces", "models", "servicios"))):
            for a in fuentes(carpeta):
                for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")):
                    destino = mod.lstrip(".").split(".")[0] if mod.startswith(".") else (mod.split(".")[1] if mod.startswith("nodo.") else "")
                    if destino in prohibidas:
                        violaciones.append(f"{a.relative_to(RAIZ)} importa {mod}")
        self.assertEqual(violaciones, [])

    def test_dominio_y_aplicacion_no_conocen_a_los_otros_modulos(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                       if mod.split(".")[0] in OTROS_MODULOS]
        self.assertEqual(violaciones, [])

    def test_r09_nodo_no_lee_tablas_de_otros_modulos(self):
        """Lo ajeno que la infraestructura toca: el contexto y la bitácora de MOD-019, la política de MOD-001 y el reloj de la evaluación (UN reloj). Nunca `<otro>.models`."""
        modelos_ajenos = re.compile(r"\b(" + "|".join(OTROS_MODULOS) + r")\.models\b")
        permitidos = {"audit", "audit.contexto", "audit.servicios", "audit.dominio.asiento", "audit.dominio", "acceso.aplicacion", "acceso.aplicacion.casos_uso",
                      "acceso.infraestructura.contenedor", "acceso.dominio.errores", "acceso.dominio", "acceso.interfaces.permisos", "evaluacion.infraestructura.contenedor"}
        for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces", "migrations"):
            texto = a.read_text(encoding="utf-8")
            self.assertIsNone(modelos_ajenos.search(texto), a.name)
            for mod in IMPORTACION.findall(texto):
                raiz = mod.split(".")[0]
                if raiz in OTROS_MODULOS:
                    self.assertIn(mod, permitidos, f"{a.relative_to(RAIZ)} importa {mod}")
        texto = (RAIZ / "servicios.py").read_text(encoding="utf-8")
        self.assertEqual([mod for mod in IMPORTACION.findall(texto) if mod.split(".")[0] in OTROS_MODULOS], [])

    def test_las_vistas_no_tocan_el_orm(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn(".objects.", texto)
        self.assertNotIn("from .. import models", texto)

    def test_las_escrituras_del_modulo_son_solo_de_sus_tablas_y_el_unico_borrado_es_la_purga(self):
        """Los únicos `.create()`, `.update()`, `.delete()`… están en `repositorios.py` y operan sobre `m.<Modelo>` de `nodo.models`; `.delete(` aparece UNA vez: en `EventosDjango.borrar`."""
        for ruta in fuentes("dominio", "aplicacion", "interfaces"):
            self.assertEqual(ESCRITURAS.findall(ruta.read_text(encoding="utf-8")), [], f"{ruta.name} escribe")
        for ruta in fuentes("infraestructura"):
            if ruta.name != "repositorios.py":
                self.assertEqual(ESCRITURAS.findall(ruta.read_text(encoding="utf-8")), [], f"{ruta.name} escribe")
        texto = (RAIZ / "infraestructura" / "repositorios.py").read_text(encoding="utf-8")
        self.assertEqual(texto.count(".delete("), 1)
        self.assertIn("def borrar(self, secuencias", texto)
        for linea in texto.splitlines():
            if ESCRITURAS.search(linea):
                self.assertRegex(linea, r"m\.\w+\.objects|fila\.save|filas\.update", linea)
        self.assertNotRegex(texto, r"from\s+(?!\.\.|\.|django|__future__)\w+\.models")

    def test_nadie_fuera_de_nodo_toca_m15(self):
        backend = RAIZ.parent
        for app in backend.iterdir():
            if not app.is_dir() or app.name in ("nodo", ".venv", "__pycache__", "logs"):
                continue
            for ruta in app.rglob("*.py"):
                if "migrations" in ruta.parts and app.name != "nodo":
                    pass
                texto = ruta.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn("nodo.models", texto, str(ruta))
                self.assertNotIn("from nodo import models", texto, str(ruta))
                if "m15_" in texto and ruta.name != "settings.py":
                    self.assertNotRegex(texto, r"(DELETE|UPDATE|INSERT)\s+(FROM|INTO)?\s*m15_", str(ruta))

    def test_br084_nada_del_modulo_habla_con_internet(self):
        prohibidos = ("requests", "urllib", "http", "socket", "ftplib", "smtplib", "webbrowser", "aiohttp", "httpx", "xmlrpc")
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces")
                       for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")) if mod.split(".")[0] in prohibidos]
        self.assertEqual(violaciones, [])

    def test_sin_dependencias_nuevas(self):
        permitidos = {"__future__", "contextlib", "dataclasses", "hashlib", "json", "logging", "os", "random", "re", "shutil", "tempfile", "threading", "time", "typing", "uuid",
                      "collections", "pathlib", "django", "rest_framework", "nodo", "acceso", "audit", "evaluacion"}
        usados = {mod.split(".")[0] for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                  if not mod.startswith(".")}
        self.assertEqual(usados - permitidos, set())

    def test_la_lista_de_rutas_nucleo_se_corresponde_con_las_rutas_reales(self):
        for ruta in ("/health/", "/api/acceso/sesiones/", "/api/aula/sesiones/", "/api/evaluacion/mias/", "/api/modo-estudio/sync/", "/api/dispositivos/latido/", "/api/logs/clientes/",
                     "/api/nodo/estado/", "/api/nodo/cola/", "/api/nodo/problemas/"):
            resolve(ruta)
            self.assertTrue(any(ruta.startswith(p) for p in cat.PREFIJOS_NUCLEO), ruta)


class EsquemaTests(TestCase):
    def modelos(self):
        return list(apps.get_app_config("nodo").get_models())

    def test_son_las_ocho_tablas_m15(self):
        tablas = sorted(x._meta.db_table for x in self.modelos())
        self.assertEqual(tablas, sorted(m.TABLAS))
        self.assertTrue(all(t.startswith("m15_") for t in tablas))

    def test_ninguna_clave_foranea_sale_del_modulo_ni_hay_fk(self):
        for modelo in self.modelos():
            for campo in modelo._meta.get_fields():
                self.assertFalse(campo.is_relation and not campo.auto_created, f"{modelo._meta.db_table}.{campo.name}")

    def test_articulo_14_ninguna_columna_guarda_contenido_de_curso_ni_personas(self):
        prohibidas = re.compile(r"titulo|rotulo|enunciado|pregunta|opcion|respuesta|correcta|contenido|nombres|apellidos|alias|ruta|path|correo|email")
        for modelo in self.modelos():
            for campo in modelo._meta.get_fields():
                self.assertNotRegex(campo.name, prohibidas, f"{modelo._meta.db_table}.{campo.name}")

    def test_la_secuencia_es_autoincrement_y_el_sobre_tiene_sus_doce_campos(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='m15_evento'")
            sql = cursor.fetchone()[0]
        self.assertIn("AUTOINCREMENT", sql.upper())
        columnas = {c.name for c in m.Evento._meta.get_fields()}
        for campo in cat.CAMPOS_DEL_SOBRE:
            self.assertIn(campo, columnas, campo)
        self.assertIn("carga", columnas)

    def test_la_migracion_esta_al_dia(self):
        call_command("makemigrations", "nodo", "--check", "--dry-run", verbosity=0)
        call_command("makemigrations", "acceso", "--check", "--dry-run", verbosity=0)


class TriggersTests(BaseNodo):
    def test_los_triggers_existen_en_la_base_de_pruebas(self):
        self.assertEqual(triggers.existentes(connection) & set(triggers.NOMBRES), set(triggers.NOMBRES))

    def test_p03_el_sobre_es_inmutable(self):
        self.publicar()
        with self.assertRaises((IntegrityError, DatabaseError)):
            with transaction.atomic():
                m.Evento.objects.filter(secuencia=1).update(actor="otro")
        with self.assertRaises((IntegrityError, DatabaseError)):
            with transaction.atomic():
                m.Evento.objects.filter(secuencia=1).update(carga={"x": 1})
        self.assertEqual(m.Evento.objects.get(secuencia=1).actor, cat.SISTEMA)

    def test_p13_la_marca_alta_solo_sube(self):
        m.MarcaAlta.objects.create(id=1, valor=100, actualizada_en=1)
        with self.assertRaises((IntegrityError, DatabaseError)):
            with transaction.atomic():
                m.MarcaAlta.objects.filter(pk=1).update(valor=99)
        m.MarcaAlta.objects.filter(pk=1).update(valor=101)
        self.assertEqual(m.MarcaAlta.objects.get(pk=1).valor, 101)


class PermisosYCatalogosTests(TestCase):
    def test_los_tres_permisos_estan_sembrados_con_el_alcance_maximo_de_la_organizacion(self):
        codigos = [c for c, *_ in plantillas.PERMISOS if c.startswith("node.")]
        self.assertEqual(sorted(codigos), sorted(cat.PERMISOS))
        for codigo in cat.PERMISOS:
            self.assertEqual(plantillas.PERMISOS_POR_CODIGO[codigo][3], plantillas.Alcance.ORGANIZATION)
            self.assertEqual(plantillas.PERMISOS_POR_CODIGO[codigo][1], "nodo")

    def concedidos(self, rol: str) -> dict[str, str]:
        r = Rol.objects.filter(codigo=rol, organizacion__isnull=True).first()
        self.assertIsNotNone(r, rol)
        return {rp.permiso_id: rp.alcance for rp in RolPermiso.objects.filter(rol=r, permiso_id__in=list(cat.PERMISOS))}

    def test_el_reparto_por_rol_es_el_del_maestro_mas_las_extensiones(self):
        # Administración: los tres. Técnico: ver la cola y la salud; reprocesar SÓLO por escalada (P-17). Nadie más.
        self.assertEqual(set(self.concedidos("ADMIN")), set(cat.PERMISOS))
        self.assertEqual(self.concedidos("TECHNICIAN"), {cat.P_READ: "ORGANIZATION", cat.P_HEALTH: "ORGANIZATION"})
        for rol in ("TEACHER", "REPORTS", "STUDENT"):
            self.assertEqual(self.concedidos(rol), {}, rol)

    def test_las_acciones_de_bitacora_estan_en_el_catalogo_cerrado(self):
        self.assertIn("nodo", catalogo_audit.MODULOS)
        for accion in cat.ACCIONES_DE_AUDITORIA:
            definicion = catalogo_audit.resolver(accion)
            self.assertIsNotNone(definicion, accion)
            self.assertEqual(definicion.modulo, catalogo_audit.M_NODO, accion)
        self.assertEqual(catalogo_audit.modulo_de("nodo.lo_que_sea"), catalogo_audit.M_NODO)
        self.assertEqual(catalogo_audit.resolver(cat.A_EVENTO_APARTADO).evento_origen, cat.EV_EVENTO_APARTADO)

    def test_los_eventos_del_maestro_y_las_extensiones_marcadas(self):
        self.assertEqual(sorted(cat.EVENTOS_DEL_MAESTRO), sorted([
            "nodo.servicios_iniciados.v1", "nodo.evento_publicado.v1", "nodo.marca_lectura_avanzada.v1", "nodo.entrega_reintentada.v1", "nodo.evento_apartado.v1",
            "nodo.evento_reprocesado.v1", "nodo.recuperacion_completada.v1", "nodo.salud_evaluada.v1", "nodo.ingreso_limitado.v1"]))
        for tipo in cat.EVENTOS:
            self.assertIn(tipo, catalogo.TIPOS)

    def test_el_catalogo_de_tipos_cubre_lo_que_cada_modulo_publica_hoy(self):
        """Cada tipo que un adaptador de outbox puede escribir hoy (su catálogo cerrado) está en el catálogo de la cola única: cuando se corte, ninguno quedará `no_catalogado`."""
        from audit.infraestructura import eventos as ev_audit
        from device_manager.dominio import dispositivo as ev_dm
        from evaluacion.dominio import catalogos as ev_ev
        from gradebook.dominio import catalogos as ev_gb
        from reporting.dominio import catalogos as ev_rp
        for lista in (ev_audit.EVENTOS, ev_dm.EVENTOS, ev_gb.EVENTOS, ev_rp.EVENTOS):
            for tipo in lista:
                self.assertIn(tipo, catalogo.TIPOS, tipo)
        for nombre in dir(ev_ev):
            if nombre.startswith("EV_") and isinstance(getattr(ev_ev, nombre), str):
                self.assertIn(getattr(ev_ev, nombre), catalogo.TIPOS, nombre)
