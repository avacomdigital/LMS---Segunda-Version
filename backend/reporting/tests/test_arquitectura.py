"""
Reglas de desacoplamiento y de frontera de MOD-013 (hexagonal, como el resto del repo) y las del Maestro que se pueden comprobar leyendo el código y el esquema:

  · el dominio y la aplicación no conocen el framework, los adaptadores ni los otros módulos; las vistas no tocan el ORM
  · BR-085 · Reporting NUNCA escribe en datos de otro módulo (sólo `m13_*`) ni importa sus modelos: lo ajeno entra por `<módulo>.servicios` y el padrón de MOD-001 es la única lectura directa
  · artículo 14 · ninguna tabla ni columna guarda títulos de curso, lección o pregunta, respuestas ni claves; sólo referencias y cifras
  · BR-007 · cada tabla `m13_*` está clasificada como derivada (se reconstruye) o propia (no se puede perder), exactamente una vez
  · BR-084 · nada del módulo habla con internet, y el escritor de archivos usa sólo la biblioteca estándar (sin dependencias nuevas en el instalador)
  · BR-085 / TST-069 · el reparto de permisos por rol y las acciones de bitácora y eventos en sus catálogos cerrados
"""
from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from acceso.dominio import plantillas
from acceso.models import Rol, RolPermiso
from audit.dominio import catalogos as catalogo_audit

from .. import models as m
from ..dominio import catalogos as cat
from .base import BaseReporting

RAIZ = Path(__file__).resolve().parent.parent
IMPORTACION = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
PROHIBIDOS = ("django", "rest_framework", "channels", "pydantic", "sqlalchemy", "fastapi")
OTROS_MODULOS = ("acceso", "classroom_engine", "modo_estudio", "evaluacion", "device_manager", "expediente", "biblioteca", "audit", "gradebook", "search", "cola_medios")
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
        for carpeta, prohibidas in (("dominio", ("aplicacion", "infraestructura", "interfaces", "models")), ("aplicacion", ("infraestructura", "interfaces", "models"))):
            for a in fuentes(carpeta):
                for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")):
                    destino = mod.lstrip(".").split(".")[0] if mod.startswith(".") else ""
                    if mod.startswith("reporting."):
                        destino = mod.split(".")[1]
                    if destino in prohibidas:
                        violaciones.append(f"{a.relative_to(RAIZ)} importa {mod}")
        self.assertEqual(violaciones, [])

    def test_dominio_y_aplicacion_no_conocen_a_los_otros_modulos(self):
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion") for mod in IMPORTACION.findall(a.read_text(encoding="utf-8"))
                       if mod.split(".")[0] in OTROS_MODULOS]
        self.assertEqual(violaciones, [])

    def test_las_vistas_no_tocan_el_orm_ni_la_biblioteca(self):
        texto = (RAIZ / "interfaces" / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("models", texto)
        self.assertNotIn(".objects.", texto)
        self.assertNotIn("biblioteca", texto.replace("la biblioteca", "").replace("AVACOM Biblioteca", ""))

    def test_br_085_reporting_nunca_lee_ni_escribe_las_tablas_de_otro_modulo(self):
        """Lo ajeno entra por la interfaz del dueño (`<módulo>.servicios`). La única lectura directa de tablas ajenas es el padrón de MOD-001, que no tiene interfaz propia."""
        modelos_ajenos = re.compile(r"\b(evaluacion|modo_estudio|classroom_engine|gradebook|device_manager|cola_medios|expediente|search)\.models\b")
        infra_ajena = re.compile(r"from\s+(evaluacion|modo_estudio|classroom_engine|gradebook|device_manager|search)\.(?:infraestructura|aplicacion|dominio)(?!\.contenedor import RelojNodo)")
        violaciones = [str(a.relative_to(RAIZ)) for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces")
                       if modelos_ajenos.search(a.read_text(encoding="utf-8")) or infra_ajena.search(a.read_text(encoding="utf-8"))]
        self.assertEqual(violaciones, [])
        for a in fuentes("infraestructura"):
            for dueno in re.findall(r"from\s+(\w+)\.models\s+import", a.read_text(encoding="utf-8")):
                self.assertEqual((dueno, a.name), ("acceso", "identidad.py"), f"{a.name} lee modelos de {dueno}")

    def test_br_085_las_fuentes_solo_leen(self):
        for nombre in ("fuentes.py", "identidad.py", "arbol.py", "autorizacion.py"):
            texto = (RAIZ / "infraestructura" / nombre).read_text(encoding="utf-8")
            self.assertEqual(ESCRITURAS.findall(texto), [], f"{nombre} escribe")
        for ruta in fuentes("dominio", "aplicacion", "interfaces"):
            self.assertEqual(ESCRITURAS.findall(ruta.read_text(encoding="utf-8")), [], f"{ruta.name} escribe")
        for fuente in (RAIZ.parent / "classroom_engine" / "servicios.py", RAIZ.parent / "modo_estudio" / "servicios.py"):
            bloque = fuente.read_text(encoding="utf-8").split("(MOD-013 · Reporting)", 1)[1]
            self.assertEqual(ESCRITURAS.findall(bloque), [], f"{fuente.parent.name}/servicios.py escribe en lo que añadió MOD-013")
        self.assertEqual(ESCRITURAS.findall((RAIZ.parent / "gradebook" / "servicios.py").read_text(encoding="utf-8")), [])

    def test_las_escrituras_del_modulo_son_solo_de_sus_tablas(self):
        """Los únicos `.save()`, `.create()`, `.delete()`… están en `repositorios.py` y operan sobre `m.<Modelo>` de `reporting.models`."""
        texto = (RAIZ / "infraestructura" / "repositorios.py").read_text(encoding="utf-8")
        for linea in texto.splitlines():
            if ESCRITURAS.search(linea):
                self.assertRegex(linea, r"m\.\w+\.objects|fila\.save|\bfilas?\.|\.filter\(|\.update_or_create|\.get_or_create|\.bulk_create|modelo\.objects|\.delete\(\)|Reciente|Exportacion", linea)
        self.assertNotRegex(texto, r"from\s+(?!\.\.|\.|django|__future__|hashlib|json)\w+\.models")

    def test_la_capa_de_biblioteca_no_se_toca_y_solo_arbol_py_habla_con_ella(self):
        habladores = [a.name for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces") if "biblioteca" in " ".join(IMPORTACION.findall(a.read_text(encoding="utf-8")))]
        self.assertEqual(habladores, ["arbol.py"])
        texto = (RAIZ / "infraestructura" / "arbol.py").read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r"v2\.(\w+)", texto))), ["_lista", "_pedir", "cursos"])         # sólo LEE el árbol: nada de evaluar, sesiones de medios ni escritura

    def test_br_084_nada_del_modulo_habla_con_internet(self):
        prohibidos = ("requests", "urllib", "http", "socket", "ftplib", "smtplib", "webbrowser", "aiohttp", "httpx", "xmlrpc")
        violaciones = [f"{a.relative_to(RAIZ)} importa {mod}" for a in fuentes("dominio", "aplicacion", "infraestructura", "interfaces", "management")
                       for mod in IMPORTACION.findall(a.read_text(encoding="utf-8")) if mod.split(".")[0] in prohibidos and not mod.startswith("urllib.parse")]
        self.assertEqual(violaciones, [])

    def test_el_escritor_de_archivos_usa_solo_la_biblioteca_estandar(self):
        """XLSX y CSV con `zipfile`, `csv` y `hashlib`: ninguna dependencia nueva que empaquetar en el instalador ni que pueda descargar algo en ejecución."""
        permitidos = {"__future__", "csv", "hashlib", "io", "re", "tempfile", "zipfile", "xml"}
        usados = {mod.split(".")[0] for mod in IMPORTACION.findall((RAIZ / "infraestructura" / "archivos.py").read_text(encoding="utf-8")) if not mod.startswith(".")}
        self.assertEqual(usados - permitidos, set())
        requisitos = (RAIZ.parent / "requirements.txt").read_text(encoding="utf-8").lower()
        for libreria in ("openpyxl", "xlsxwriter", "pandas", "reportlab", "fpdf", "weasyprint", "requests"):
            self.assertNotIn(libreria, requisitos)


class EsquemaTests(TestCase):
    def modelos(self):
        return list(apps.get_app_config("reporting").get_models())

    def test_son_las_tablas_m13_y_cada_una_esta_clasificada_una_sola_vez(self):
        tablas = sorted(x._meta.db_table for x in self.modelos())
        self.assertTrue(all(t.startswith("m13_") for t in tablas), tablas)
        self.assertEqual(len(tablas), 11)
        self.assertEqual(sorted(m.TABLAS_DERIVADAS + m.TABLAS_PROPIAS), tablas)
        self.assertEqual(set(m.TABLAS_DERIVADAS) & set(m.TABLAS_PROPIAS), set())

    def test_articulo_14_ninguna_columna_guarda_contenido_de_curso_ni_personas(self):
        prohibidas = re.compile(r"titulo|rotulo|enunciado|pregunta|opcion|respuesta|correcta|contenido|nombre_de_persona|alias|nombres|apellidos|ruta|path")
        permitidos = {"nombre_archivo"}                 # el nombre PROPUESTO del archivo (código del grupo y fecha): sin ruta y sin personas
        for modelo in self.modelos():
            for campo in modelo._meta.get_fields():
                if campo.name in permitidos:
                    continue
                self.assertNotRegex(campo.name, prohibidas, f"{modelo._meta.db_table}.{campo.name}")
        columnas_de_clave = [c.name for x in self.modelos() for c in x._meta.get_fields() if "clave" in c.name]
        self.assertEqual(sorted(set(columnas_de_clave)), ["clave", "nivel_clave"])                 # `nivel_clave` es el nivel educativo del grupo; `clave` la huella de un reciente

    def test_ninguna_clave_foranea_sale_del_modulo(self):
        for modelo in self.modelos():
            for campo in modelo._meta.get_fields():
                if campo.is_relation and not campo.auto_created:
                    self.assertEqual(campo.related_model._meta.app_label, "reporting", f"{modelo._meta.db_table}.{campo.name}")

    def test_la_migracion_esta_al_dia(self):
        call_command("makemigrations", "reporting", "--check", "--dry-run", verbosity=0)


class PermisosYCatalogosTests(TestCase):
    def test_los_ocho_permisos_estan_sembrados_con_el_alcance_maximo_de_la_organizacion(self):
        codigos = [c for c, *_ in plantillas.PERMISOS if c.startswith("reports.")]
        self.assertEqual(sorted(codigos), sorted(cat.PERMISOS))
        for codigo in cat.PERMISOS:
            self.assertEqual(plantillas.PERMISOS_POR_CODIGO[codigo][3], plantillas.Alcance.ORGANIZATION)

    def concedidos(self, rol: str) -> dict[str, str]:
        r = Rol.objects.filter(codigo=rol, organizacion__isnull=True).first()
        self.assertIsNotNone(r, rol)
        return {rp.permiso_id: rp.alcance for rp in RolPermiso.objects.filter(rol=r, permiso_id__in=list(cat.PERMISOS))}

    def test_el_reparto_por_rol_es_el_del_producto(self):
        # Profesor: grupo, alumno, clase y exportar SOBRE SUS GRUPOS; sin uso, sin reconstruir, sin configurar
        self.assertEqual(self.concedidos("TEACHER"), {"reports.view": "ASSIGNED_GROUPS", "reports.group.view": "ASSIGNED_GROUPS", "reports.student.view": "ASSIGNED_GROUPS",
                                                      "reports.export": "ASSIGNED_GROUPS"})
        # Reportes: lectura de toda la organización y exportar; SIN reconstruir (BR-085) ni configurar
        self.assertEqual(self.concedidos("REPORTS"), {"reports.view": "ORGANIZATION", "reports.group.view": "ORGANIZATION", "reports.student.view": "ORGANIZATION",
                                                      "reports.usage.view": "ORGANIZATION", "reports.curriculum.view": "ORGANIZATION", "reports.export": "ORGANIZATION"})
        # Administración: todo
        self.assertEqual(set(self.concedidos("ADMIN")), set(cat.PERMISOS))
        # Técnico: sólo el uso de equipos (sin personas) y reconstruir; NINGUNO de lectura académica (BR-097, TST-069)
        self.assertEqual(self.concedidos("TECHNICIAN"), {"reports.usage.view": "ORGANIZATION", "reports.rebuild": "ORGANIZATION"})
        self.assertFalse(set(self.concedidos("TECHNICIAN")) & set(cat.PERMISOS_DE_LECTURA_ACADEMICA))
        # El alumno: ninguno
        self.assertEqual(self.concedidos("STUDENT"), {})

    def test_las_acciones_de_bitacora_estan_en_el_catalogo_cerrado(self):
        for accion in cat.ACCIONES_DE_AUDITORIA:
            definicion = catalogo_audit.resolver(accion)
            self.assertIsNotNone(definicion, accion)
            self.assertEqual(definicion.modulo, catalogo_audit.M_REPORTES, accion)
        self.assertEqual(catalogo_audit.modulo_de("reporte.lo_que_sea"), catalogo_audit.M_REPORTES)
        for sensible in (cat.A_GENERADO, cat.A_EXPORT_AUTORIZADA, cat.A_EXPORTADO, cat.A_EXPORT_FALLIDA, cat.A_EXPORT_CADUCADA, cat.A_ACCESO_DENEGADO):
            self.assertTrue(catalogo_audit.resolver(sensible).sensible, sensible)           # su detalle se enmascara sin escalada (BR-131)
        self.assertEqual(catalogo_audit.resolver(cat.A_EXPORTADO).evento_origen, cat.EV_EXPORTADO)

    def test_los_eventos_son_los_ocho_del_maestro_versionados_mas_el_del_boletin(self):
        self.assertEqual(sorted(cat.EVENTOS), sorted([
            "reporte.agregados_actualizados.v1", "reporte.agregados_reconstruidos.v1", "reporte.alumno_generado.v1", "reporte.cobertura_generado.v1", "reporte.exportado.v1",
            "reporte.grupo_generado.v1", "reporte.marcado_incompleto.v1", "reporte.uso_generado.v1", "reporte.boletin_generado.v1"]))      # el boletín académico (2026-10-19)
        self.assertEqual(cat.EVENTOS_RESERVADOS, (cat.EV_COBERTURA_GENERADO,))

    def test_los_eventos_que_consume_pertenecen_a_su_fuente_y_estan_versionados(self):
        prefijos = {cat.AULA: "aula.", cat.EVALUACION: "evaluacion.", cat.CALIFICACION: "calificacion.", cat.ESTUDIO: "estudio."}
        for fuente, tipos in cat.EVENTOS_CONSUMIDOS.items():
            self.assertTrue(tipos)
            for tipo in tipos:
                self.assertTrue(tipo.startswith(prefijos[fuente]) and tipo.endswith(".v1"), tipo)
        self.assertEqual(set(cat.EVENTOS_CONSUMIDOS), set(cat.FUENTES))

    def test_los_motivos_de_fallo_son_el_contrato_con_el_cliente(self):
        self.assertEqual(cat.MOTIVOS_DE_FALLO, ("medio_retirado", "sin_espacio", "protegido_contra_escritura", "sin_permiso", "ruta_de_red_inalcanzable", "nombre_invalido",
                                                "bloqueado_por_antivirus", "archivo_en_uso", "verificacion_fallida", "cancelado", "otro"))
        self.assertEqual(cat.DESTINOS, ("extraible", "carpeta_local", "red"))
        self.assertEqual(cat.FORMATOS, ("xlsx", "csv"))


class ProyeccionesSinContenidoTests(BaseReporting):
    """Con datos reales: lo que queda guardado de una clase, un grupo y un alumno son ids, estados y cifras (artículo 14), nunca un título ni un nombre."""

    def test_el_detalle_y_las_filas_no_traen_titulos_ni_nombres(self):
        c = self.clase_cerrada([(5, 5), (3, 5)])
        self.evaluacion(titulo="Examen de los estados")
        self.estudio(titulo="Leer la lección de los estados")
        self.rp(f"/grupos/{self.grupo['id']}/")
        guardado = str(list(m.AvanceAlumno.objects.values())) + str(list(m.AvanceGrupo.objects.values())) + str(list(m.Clase.objects.values())) + str(list(m.ClaseAlumno.objects.values()))
        self.assertIn("asignacion_id", guardado)                                  # sí guarda las referencias
        for prohibido in ("Examen de los estados", "Leer la lección", "Estados de la materia", "Los tres estados", "Juan P.", c["alumnos"][0][1], "Prof. Gómez", "Octavo A"):
            self.assertNotIn(prohibido, guardado, prohibido)
