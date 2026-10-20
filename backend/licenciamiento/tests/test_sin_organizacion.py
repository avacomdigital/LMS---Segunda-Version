"""
Un nodo al que todavía no se le instaló la organización (primer arranque, antes de que OPS haga la instalación). Fase 2 del prompt: «anota cómo se calcula el estado para un nodo sin organización
instalada (409 `no_instalado`)». Lo que estas pruebas fijan:

  · la licencia NO necesita organización: el estado se calcula igual —sin licencia, con su ventana de evaluación desde el primer arranque— y sus rutas responden;
  · lo que depende de la organización (contar equipos y usuarios) responde `null` y no aplica cupo: contar nunca lanza ni cierra nada (R-04);
  · los 409 `no_instalado` siguen siendo de cada módulo dueño de su dato (acceso, dispositivos…): la licencia nunca los produce ni los esconde.
"""
from __future__ import annotations

import shutil
import tempfile

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from acceso.models import Organizacion
from licenciamiento import servicios
from licenciamiento.dominio import catalogos as cat
from licenciamiento.infraestructura import contenedor

from .base import L


class NodoSinOrganizacionTests(TestCase):
    def setUp(self):
        carpeta = tempfile.mkdtemp(prefix="avacom-licencia-sin-org-")
        self.addCleanup(shutil.rmtree, carpeta, True)
        sobre = override_settings(AVACOM_LICENCIA_MODO="firmada", AVACOM_LICENCIA_DIR=carpeta)
        sobre.enable()
        self.addCleanup(sobre.disable)
        contenedor.reiniciar()
        self.addCleanup(contenedor.reiniciar)
        self.assertFalse(Organizacion.objects.exists())               # el nodo está recién instalado: sin organización
        self.cliente = APIClient()

    def test_el_estado_se_calcula_igual_y_la_evaluacion_empieza_en_el_primer_arranque(self):
        r = self.cliente.get(f"{L}/estado/")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["estado"], cuerpo["motivo"], cuerpo["tipo"], cuerpo["licencia"]), (cat.SIN_LICENCIA, cat.M_EVALUACION, None, None))
        self.assertEqual(cuerpo["capacidades"]["no_disponibles"], [])                                      # durante la evaluación todo está habilitado
        self.assertEqual(cuerpo["vigencia"]["dias_restantes"], 30)
        self.assertEqual(cuerpo["limites"], {"equipos": 60, "usuarios": 1200, "concurrentes_normal": 50, "concurrentes_pico": 100})       # el tamaño máximo de un aula (Q-L1)
        self.assertEqual(cuerpo["consumo"], None)
        self.assertEqual([a["codigo"] for a in cuerpo["avisos"]], ["evaluacion"])                          # el aviso existe desde el primer día

    def test_el_consumo_no_se_puede_contar_y_lo_dice_con_null(self):
        r = self.cliente.get(f"{L}/consumo/")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["equipos"]["en_uso"], cuerpo["usuarios"]["en_uso"]), (None, None))
        self.assertEqual((cuerpo["equipos"]["limite"], cuerpo["equipos"]["porcentaje"]), (60, None))
        self.assertEqual(cuerpo["concurrentes"], {"normal": 50, "pico": 100})
        servicios.exigir_equipo_nuevo(5)                                                                   # el cupo de la evaluación rige con la cifra que trae quien da de alta (el dueño del dato)
        servicios.exigir_usuario_nuevo(5)

    def test_las_capacidades_y_el_resumen_responden_y_nada_se_apaga(self):
        self.assertEqual(self.cliente.get(f"{L}/capacidades/").json()["no_disponibles"], [])
        self.assertTrue(servicios.capacidad_habilitada("reportes"))
        self.assertEqual(servicios.estado_resumido()["estado"], cat.SIN_LICENCIA)

    def test_el_409_no_instalado_es_de_cada_modulo_dueno_y_no_de_la_licencia(self):
        r = self.cliente.get("/api/dispositivos/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "no_instalado"))                       # lo dice device_manager, dueño de su dato
        self.assertEqual(self.cliente.get(f"{L}/estado/").status_code, 200)                                # la licencia sigue respondiendo
