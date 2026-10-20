"""
MOD-018 · R-01 en profundidad: una licencia con un límite en 0 no «limita», DETIENE (sin concurrencia el aula no admite ni al primer alumno; sin equipos o sin usuarios no se registra
ninguna tableta ni persona nueva). El emisor oficial no emite ceros, pero el nodo no depende de que todos los emisores sean cuidadosos: rechaza el archivo, esté bien firmado o no.
Lo encontró la verificación independiente (`spec-driven/15-licenciamiento/06-verificacion-independiente.md`, H-15).
"""
from __future__ import annotations

from licenciamiento.dominio.licencia import ILIMITADO, Limites

from .base import BaseLicencia


class LimitesEnCeroTests(BaseLicencia):
    def test_un_limite_en_cero_se_rechaza_aunque_este_bien_firmado(self):
        casos = {
            "equipos": Limites(0, 1200, 50, 100),
            "usuarios": Limites(55, 0, 50, 100),
            "concurrentes normales": Limites(55, 1200, 0, 100),
            "concurrentes en pico": Limites(55, 1200, 0, 0),
        }
        for nombre, limites in casos.items():
            with self.subTest(nombre):
                r = self.activar(limites=limites)
                self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (400, "licencia_invalida", "campo_invalido"), r.content)
        self.assertEqual(self.estado()["licencia"], None)       # nada se instaló

    def test_los_limites_minimos_y_sin_tope_siguen_valiendo(self):
        for limites in (Limites(1, 1, 1, 1), Limites(ILIMITADO, ILIMITADO, ILIMITADO, ILIMITADO), Limites(55, 1200, 1, ILIMITADO)):
            with self.subTest(limites=limites):
                r = self.activar(limites=limites)
                self.assertEqual(r.status_code, 200, r.content)

    def test_la_clase_sigue_admitiendo_alumnos_con_el_limite_minimo(self):
        self.activar_ok(limites=Limites(55, 1200, 1, 1))
        sesion = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-1"}, format="json").json()
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": sesion["codigo_union"], "persona_id": "ana", "persona_rotulo": "ana", "dispositivo": "tab-1"}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
