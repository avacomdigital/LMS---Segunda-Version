"""Traspaso de sesión entre apps (OPS ↔ Student): un código de un solo uso y 60 s que abre la MISMA sesión en la otra app sin pedir la clave."""
from __future__ import annotations

from acceso import models as m

from .base import BaseAcceso


class TraspasoTests(BaseAcceso):
    def pedir(self, cliente):
        r = cliente.post("/api/acceso/sesiones/traspaso/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def canjear(self, codigo: str, dispositivo: str | None = None):
        return self.api.post("/api/acceso/sesiones/traspaso/canjear/", {"codigo": codigo, "dispositivo": dispositivo or ""}, format="json")

    def test_el_profesor_pasa_su_sesion_a_la_otra_app_sin_clave(self):
        pedido = self.pedir(self.docente)
        self.assertEqual((pedido["expira_en_seg"], pedido["menu"]), (60, "teacher"))
        r = self.canjear(pedido["codigo"], self.TABLETA)
        self.assertEqual(r.status_code, 200, r.content)
        datos = r.json()
        self.assertEqual((datos["usuario"]["id"], datos["usuario"]["rol"]), (self.docente_id, "TEACHER"))
        self.assertEqual(self.con_token(datos["token"]).get("/api/acceso/yo/").status_code, 200)
        self.assertEqual(datos["sesion_anterior"]["dispositivo"], None)   # la sesión de origen no tenía equipo

    def test_la_sesion_de_origen_se_cierra_y_el_codigo_sirve_una_sola_vez(self):
        pedido = self.pedir(self.docente)
        self.assertEqual(self.canjear(pedido["codigo"], self.TABLETA).status_code, 200)
        self.assertEqual(self.docente.get("/api/acceso/yo/").status_code, 401)           # la de origen quedó cerrada (otro dispositivo)
        otra = self.canjear(pedido["codigo"], self.TABLETA)
        self.assertEqual((otra.status_code, otra.json()["codigo"]), (401, "credenciales_invalidas"))

    def test_el_alumno_tambien_pasa_de_app(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        pedido = self.pedir(alumno)
        self.assertEqual(pedido["menu"], "student")
        r = self.canjear(pedido["codigo"], self.TABLETA)
        self.assertEqual((r.status_code, r.json()["usuario"]["menu"]), (200, "student"))

    def test_el_codigo_no_sirve_como_pase_de_sesion(self):
        pedido = self.pedir(self.docente)
        self.assertEqual(self.con_token(pedido["codigo"]).get("/api/acceso/yo/").status_code, 401)

    def test_un_pase_de_sesion_no_sirve_como_codigo_de_traspaso(self):
        r = self.canjear(self.docente.token)
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "credenciales_invalidas"))

    def test_basura_y_codigo_vencido_se_rechazan_igual(self):
        self.assertEqual(self.canjear("no-es-un-codigo").status_code, 401)
        pedido = self.pedir(self.docente)
        m.Sesion.objects.filter(usuario_id=self.docente_id, revocada_en__isnull=True).update(revocada_en=1, motivo_revocacion="persona")
        self.assertEqual(self.canjear(pedido["codigo"]).status_code, 401)                 # la sesión de origen ya no vale

    def test_sin_sesion_no_se_pide_traspaso(self):
        r = self.api.post("/api/acceso/sesiones/traspaso/", {}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_una_visita_no_se_traspasa(self):
        r = self.api.post("/api/acceso/sesiones/visitante/", {"dispositivo": self.TABLETA}, format="json")
        if r.status_code != 200:
            self.skipTest("el nodo de la prueba no ofrece visitante")
        visita = self.con_token(r.json()["token"])
        self.assertEqual(visita.post("/api/acceso/sesiones/traspaso/", {}, format="json").status_code, 409)

    def test_queda_asentado_en_la_bitacora(self):
        self.canjear(self.pedir(self.docente)["codigo"], self.TABLETA)
        from audit.models import Bitacora
        acciones = set(Bitacora.objects.values_list("accion", flat=True))
        self.assertIn("identidad.traspaso.emitido", acciones)
        self.assertIn("identidad.traspaso.canjeado", acciones)
