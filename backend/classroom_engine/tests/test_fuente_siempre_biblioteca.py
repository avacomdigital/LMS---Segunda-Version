"""
Los cursos salen SIEMPRE de la biblioteca. El manifiesto de ejemplo es sólo para pruebas y desarrollo: con `AVACOM_AULA_PERMITIR_EJEMPLO` apagado (lo que
tiene un nodo real y el instalador) pedir la fuente «ejemplo» —un cliente viejo, una preferencia guardada, una variable de entorno— se resuelve con la
biblioteca. `manage.py test` lo enciende solo para que las pruebas del aula sigan usando el ejemplo.
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from ..infraestructura import contenedor
from ..infraestructura.fuente_biblioteca import FuenteBiblioteca
from ..infraestructura.fuente_ejemplo import ALIAS, FuenteEjemplo


class FuenteSiempreBibliotecaTests(SimpleTestCase):
    def test_las_pruebas_corren_con_el_ejemplo_permitido(self):
        self.assertTrue(contenedor.ejemplo_permitido())

    @override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False)
    def test_pedir_el_ejemplo_con_el_ejemplo_apagado_devuelve_la_biblioteca(self):
        self.assertIsInstance(contenedor.fuente("ejemplo"), FuenteBiblioteca)
        self.assertIsInstance(contenedor.fuente("biblioteca"), FuenteBiblioteca)

    @override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False)
    def test_sin_nombre_y_con_la_referencia_del_ejemplo_tampoco_se_cae_al_ejemplo(self):
        referencia = next(iter(ALIAS), "avacom.co.lower-secondary.6.science.states-of-matter")
        self.assertIsInstance(contenedor.fuente(None, referencia), FuenteBiblioteca)

    @override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False, AVACOM_AULA_FUENTE_CURSOS="ejemplo")
    def test_una_variable_de_entorno_que_pide_el_ejemplo_se_ignora(self):
        self.assertEqual(contenedor.fuente_por_defecto(), "biblioteca")
        self.assertIsInstance(contenedor.fuente(None), FuenteBiblioteca)

    @override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=True)
    def test_con_el_ejemplo_permitido_para_pruebas_sigue_funcionando(self):
        self.assertIsInstance(contenedor.fuente("ejemplo"), FuenteEjemplo)

    @override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False)
    def test_un_nombre_desconocido_sigue_siendo_un_error(self):
        from ..dominio.errores import DatosInvalidos

        with self.assertRaises(DatosInvalidos):
            contenedor.fuente("otra")
