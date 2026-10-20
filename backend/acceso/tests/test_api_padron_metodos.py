"""
Padrón · un método que no corresponde a la ruta es un 405, no un 500.

`PadronMatriculaView` atiende dos rutas: `padron/grupos/<pk>/estudiantes/` (POST: matricular) y `padron/grupos/<pk>/estudiantes/<usuario_id>/` (DELETE: retirar). Antes, un DELETE a la primera o un POST
a la segunda no coincidía con la firma del método y salía un `TypeError` sin atrapar: un 500 con la página de error de Django. Lo encontró un barrido de las 316 rutas del backend (MOD-018, verificación
independiente): no tiene nada que ver con la licencia, pasaba igual en todos los estados.
"""
from __future__ import annotations

from .base import BaseAcceso

COLECCION = "/api/acceso/padron/grupos/{pk}/estudiantes/"
ELEMENTO = "/api/acceso/padron/grupos/{pk}/estudiantes/{usuario_id}/"


class MetodosDelPadronTests(BaseAcceso):
    def _grupo_y_estudiante(self):
        g = self.admin.post("/api/acceso/padron/grupos/", {"nombre": "Quinto B", "nivel_clave": "primaria"}, format="json")
        self.assertEqual(g.status_code, 201, g.content)
        e = self.admin.post("/api/acceso/padron/estudiantes/", {"nombres": "Sofía", "apellidos": "Gómez", "documento": "", "grupo_id": g.json()["id"]}, format="json")
        self.assertEqual(e.status_code, 201, e.content)
        return g.json()["id"], e.json()["id"]

    def test_retirar_sobre_la_coleccion_no_es_un_500(self):
        grupo, _ = self._grupo_y_estudiante()
        r = self.admin.delete(COLECCION.format(pk=grupo))
        self.assertEqual(r.status_code, 405, r.content)

    def test_matricular_sobre_un_elemento_no_es_un_500(self):
        grupo, estudiante = self._grupo_y_estudiante()
        r = self.admin.post(ELEMENTO.format(pk=grupo, usuario_id=estudiante), {"usuario_id": estudiante}, format="json")
        self.assertEqual(r.status_code, 405, r.content)

    def test_con_ids_que_no_existen_tampoco(self):
        for metodo, ruta in (("delete", COLECCION.format(pk="X")), ("post", ELEMENTO.format(pk="X", usuario_id="X"))):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.admin, metodo)(ruta, {}, format="json").status_code, 405)

    def test_lo_que_si_corresponde_sigue_funcionando(self):
        grupo, estudiante = self._grupo_y_estudiante()
        otro = self.admin.post("/api/acceso/padron/grupos/", {"nombre": "Sexto A", "nivel_clave": "primaria"}, format="json").json()["id"]
        r = self.admin.post(COLECCION.format(pk=otro), {"usuario_id": estudiante}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        self.assertEqual(self.admin.delete(ELEMENTO.format(pk=otro, usuario_id=estudiante)).status_code, 204)
