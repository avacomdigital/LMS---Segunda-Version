"""
Toda sesión dura como mínimo UNA HORA, para cualquier tipo de usuario (pedido para la prueba de 35 tabletas, 2026-10-08).

Se comprueba de dos maneras: el reglamento de fábrica de cada perfil (duración e inactividad) y la sesión que de verdad se abre al entrar cada tipo de persona
(administración, docente, alumno y visitante), con su caducidad y su inactividad.
"""
from __future__ import annotations

from .. import models as m
from ..dominio import plantillas
from .base import BaseAcceso

HORA_MS = 60 * 60 * 1000


class SesionMinimaDeUnaHoraTests(BaseAcceso):
    def test_el_reglamento_de_fabrica_de_todos_los_perfiles_da_al_menos_una_hora(self):
        for perfil, politica in plantillas.POLITICAS_POR_DEFECTO.items():
            with self.subTest(perfil=perfil.value):
                self.assertGreaterEqual(politica["duracion_sesion_min"], 60)
                self.assertGreaterEqual(politica["inactividad_min"], 60)

    def test_las_politicas_guardadas_de_la_organizacion_dan_al_menos_una_hora(self):
        for p in m.PoliticaCredencial.objects.all():
            with self.subTest(perfil=p.perfil, nivel=p.nivel_clave):
                self.assertGreaterEqual(p.duracion_sesion_min, 60)
                self.assertGreaterEqual(p.inactividad_min, 60)

    def comprobar(self, respuesta):
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        datos = respuesta.json()
        fila = m.Sesion.objects.get(id=datos["sesion_id"])
        self.assertGreaterEqual(fila.expira_en - fila.emitida_en, HORA_MS, "la sesión caduca antes de una hora")
        self.assertGreaterEqual(datos["inactividad_min"], 60, "la inactividad cierra la sesión antes de una hora")

    def test_la_sesion_real_de_cada_tipo_de_persona_dura_al_menos_una_hora(self):
        self.comprobar(self.login(self.ADMIN_DNI, self.ADMIN_PASS))       # `login` pone solo el PIN maestro de la administración
        self.comprobar(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS))
        self.comprobar(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN))

    def test_la_visita_dura_al_menos_una_hora(self):
        r = self.api.post("/api/acceso/sesiones/visitante/", {"dispositivo": self.TABLETA}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        fila = m.Sesion.objects.get(id=r.json()["sesion_id"])
        self.assertGreaterEqual(fila.expira_en - fila.emitida_en, HORA_MS)
        self.assertGreaterEqual(plantillas.HORAS_VIDA_VISITANTE, 1)
