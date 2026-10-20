"""
P-12 · «entorno sin puerta trasera», de punta a punta con un layout de producción de verdad en disco: un nodo instalado NO se vuelve «de pruebas» porque alguien ponga
`AVACOM_LMS_ENTORNO=pruebas` en `backend.env`. La clasificación pura está probada en `test_estado.py`; aquí se comprueba lo que de ella se desprende: el modo, la carpeta de estado y que el
nodo, con ese texto editado, SIGUE evaluando la licencia (y degrada cuando toca).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from licenciamiento.dominio import entorno
from licenciamiento.dominio.politica import DIA_MS, HORA_MS
from licenciamiento.infraestructura import contenedor

from .base import BaseLicencia


class LayoutDeProduccionTests(SimpleTestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="avacom-layout-")) / "Program Files" / "AVACOM" / "OPS Master" / "Backend"
        self.raiz.mkdir(parents=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.raiz.parents[3], True))

    def test_el_marcador_de_canal_en_disco_hace_de_produccion_a_un_nodo_aunque_digan_pruebas(self):
        (self.raiz / entorno.MARCADOR_DE_CANAL).write_text("produccion")
        for declarado in ("pruebas", "desarrollo", "", "instalado"):
            self.assertEqual(entorno.clasificar(self.raiz, {"AVACOM_LMS_ENTORNO": declarado}, ["manage.py", "test"]), entorno.PRODUCCION, declarado)

    def test_sin_el_marcador_pero_bajo_program_files_tambien_es_produccion(self):
        self.assertEqual(entorno.clasificar(self.raiz, {"AVACOM_LMS_ENTORNO": "pruebas"}, ["manage.py", "test"]), entorno.PRODUCCION)

    def test_este_repositorio_de_desarrollo_se_clasifica_como_pruebas_al_correr_manage_py_test(self):
        self.assertEqual(settings.AVACOM_LICENCIA_ENTORNO, entorno.PRUEBAS)
        self.assertEqual(entorno.clasificar(Path(settings.BASE_DIR), {}, ["manage.py", "runserver"]), entorno.DESARROLLO)

    def test_el_modo_y_la_carpeta_de_un_nodo_de_produccion_no_obedecen_a_ninguna_variable(self):
        with override_settings(AVACOM_LICENCIA_ENTORNO=entorno.PRODUCCION, AVACOM_LICENCIA_MODO="auto", AVACOM_LICENCIA_DIR="C:/otra/carpeta/vacia"):
            self.assertEqual(contenedor.modo(), contenedor.FIRMADA)
            with mock.patch.dict(os.environ, {"ProgramData": "D:/ProgramData"}):
                carpeta = contenedor.carpeta_de_estado()
            self.assertEqual(carpeta.parts[-5:], ("ProgramData", "AVACOM", "OPS Master", "Config", "licencia"))       # SIEMPRE ProgramData: mover el estado reiniciaría la evaluación
        with override_settings(AVACOM_LICENCIA_ENTORNO=entorno.PRUEBAS, AVACOM_LICENCIA_MODO="auto"):
            self.assertEqual(contenedor.modo(), contenedor.ILIMITADA)
        with override_settings(AVACOM_LICENCIA_ENTORNO=entorno.DESARROLLO, AVACOM_LICENCIA_MODO="firmada"):
            self.assertEqual(contenedor.modo(), contenedor.FIRMADA)                                                 # una variable sólo puede AÑADIR protección


class NodoDeProduccionConElTextoEditadoTests(BaseLicencia):
    def test_con_AVACOM_LMS_ENTORNO_pruebas_en_backend_env_el_nodo_instalado_sigue_evaluando_la_licencia(self):
        raiz = Path(tempfile.mkdtemp(prefix="avacom-layout-")) / "Program Files" / "AVACOM" / "OPS Master" / "Backend"
        raiz.mkdir(parents=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(raiz.parents[3], True))
        (raiz / entorno.MARCADOR_DE_CANAL).write_text("produccion")
        # «backend.env» del administrador: AVACOM_LMS_ENTORNO=pruebas (y de paso el modo ilimitada, que no existe como variable)
        clasificado = entorno.clasificar(raiz, {"AVACOM_LMS_ENTORNO": "pruebas", "AVACOM_LICENCIA_MODO": "ilimitada"}, ["daphne"])
        self.assertEqual(clasificado, entorno.PRODUCCION)
        from dataclasses import replace

        # En producción la carpeta de estado es SIEMPRE `%ProgramData%\AVACOM\OPS Master\Config\licencia` (D-5): la prueba redirige `%ProgramData%` a una carpeta temporal y pone un registro
        # de mentira, para no escribir NADA en el ProgramData ni en el registro REAL de quien corre las pruebas (una corrida anterior dejó ahí un ancla de reloj que degradaba la siguiente).
        programdata = Path(tempfile.mkdtemp(prefix="avacom-programdata-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(programdata, True))

        class RegistroDeMentira:
            def leer(self):
                return None

            def escribir(self, marca, mac):
                pass

        with mock.patch.dict(os.environ, {"ProgramData": str(programdata)}), mock.patch.object(contenedor, "RegistroDeWindows", RegistroDeMentira), \
                override_settings(AVACOM_LICENCIA_ENTORNO=clasificado, AVACOM_LICENCIA_MODO="ilimitada", AVACOM_LICENCIA_DIR=self.carpeta):
            self.assertEqual(contenedor.modo(), contenedor.FIRMADA)
            self.assertTrue(str(contenedor.carpeta_de_estado()).startswith(str(programdata)))
            s = contenedor.servicios()
            s.reloj, s.huella = self.reloj, self.huella
            s.config = replace(s.config, entorno=clasificado)
            from licenciamiento.aplicacion.evaluar import Evaluar
            self.assertEqual(Evaluar(s).ejecutar("arranque").estado.estado, "sin_licencia")
            self.reloj.avanzar(31 * DIA_MS + HORA_MS)
            e = Evaluar(s).ejecutar("tick")
            self.assertEqual((e.estado.estado, e.estado.motivo), ("degradada", "evaluacion_vencida"))                 # la licencia SIGUE aplicándose
            self.assertEqual(self.admin.get("/api/reportes/estado/").status_code, 402)
            self.assertEqual(self.docente.get("/api/aula/sesiones/").status_code, 200)                              # y la clase, intacta (R-01)

    def test_la_llave_de_desarrollo_no_se_carga_en_produccion(self):
        from licenciamiento.infraestructura.claves import ClavesPublicas
        carpeta = contenedor.CARPETA_DE_CLAVES
        self.assertEqual(sorted(ClavesPublicas(carpeta, entorno.PRUEBAS).publicas()), ["dev-1", "dev-2"])
        self.assertEqual(sorted(ClavesPublicas(carpeta, entorno.DESARROLLO).publicas()), ["dev-1", "dev-2"])
        self.assertEqual(ClavesPublicas(carpeta, entorno.PRODUCCION).publicas(), {})         # hasta la ceremonia de llaves del CTO (Q-L3) un nodo de producción no acepta ninguna licencia
