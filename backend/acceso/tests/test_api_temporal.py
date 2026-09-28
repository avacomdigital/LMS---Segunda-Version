"""Acceso temporal a examen: opción A (tableta autorizada) y opción B (código de un solo uso)."""
from __future__ import annotations

from acceso import models as m

from .base import BaseAcceso


class AccesoTemporalTests(BaseAcceso):
    def otorgar(self, **extra):
        cuerpo = {"usuario_id": self.estudiante_id, "tipo": "DISPOSITIVO", "dispositivo_id": self.tableta["id"],
                  "evaluacion_ref": "co-sec-mat-eval-08", "motivo": "Olvidó el PIN antes del parcial"}
        cuerpo.update(extra)
        return self.docente.post("/api/acceso/autorizaciones-temporales/", cuerpo, format="json")

    def canjear(self, **cuerpo):
        return self.api.post("/api/acceso/autorizaciones-temporales/canjear/", cuerpo, format="json")

    def test_opcion_a_la_tableta_autorizada_entra_sin_que_juan_recuerde_nada(self):
        r = self.otorgar()
        self.assertEqual(r.status_code, 201, r.content)
        entrega = r.json()["entrega"]
        self.assertEqual(set(entrega), {"grant_id", "token"})
        self.assertEqual(r.json()["dispositivo"], "tableta-07")
        self.assertNotIn(entrega["token"], m.AutorizacionTemporal.objects.get(id=entrega["grant_id"]).secreto_hash)

        r = self.canjear(grant_id=entrega["grant_id"], token=entrega["token"], dispositivo=self.TABLETA)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["usuario"]["clase_sesion"], "TEMPORAL")
        self.assertEqual(r.json()["usuario"]["evaluacion_ref"], "co-sec-mat-eval-08")
        temporal = self.con_token(r.json()["token"])
        yo = temporal.get("/api/acceso/yo/").json()
        self.assertEqual(yo["sesion"]["clase"], "TEMPORAL")
        self.assertEqual({p["codigo"] for p in yo["permisos"]} & {"identity.password.change_own", "identity.user.read"}, set())
        r = temporal.get("/api/acceso/usuarios/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sesion_temporal_limitada"))
        # un solo uso
        self.assertEqual(self.canjear(grant_id=entrega["grant_id"], token=entrega["token"], dispositivo=self.TABLETA).status_code, 401)

    def test_opcion_a_otra_tableta_no_sirve_y_al_tercer_fallo_se_revoca(self):
        self.api.post("/api/dispositivos/", {"identificador": "otra-hw", "nombre": "tableta-01"}, format="json")
        entrega = self.otorgar().json()["entrega"]
        for _ in range(3):
            self.assertEqual(self.canjear(grant_id=entrega["grant_id"], token=entrega["token"], dispositivo="otra-hw").status_code, 401)
        self.assertIsNotNone(m.AutorizacionTemporal.objects.get(id=entrega["grant_id"]).revocada_en)
        self.assertEqual(self.canjear(grant_id=entrega["grant_id"], token=entrega["token"], dispositivo=self.TABLETA).status_code, 401)

    def test_opcion_b_codigo_de_seis_digitos_hasheado_con_argon2(self):
        r = self.otorgar(tipo="CODIGO", dispositivo_id="")
        self.assertEqual(r.status_code, 201, r.content)
        codigo = r.json()["entrega"]["codigo"]
        self.assertRegex(codigo, r"^\d{6}$")
        fila = m.AutorizacionTemporal.objects.get(id=r.json()["id"])
        self.assertTrue(fila.secreto_hash.startswith("$argon2id$"))
        self.assertEqual(self.canjear(codigo="000000", dispositivo=self.TABLETA).status_code, 401)
        r = self.canjear(codigo=f"{codigo[:3]} {codigo[3:]}", dispositivo=self.TABLETA)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["usuario"]["clase_sesion"], "TEMPORAL")
        self.assertIsNotNone(m.AutorizacionTemporal.objects.get(id=fila.id).usada_en)

    def test_caducidad_y_revocacion_por_el_docente(self):
        r = self.otorgar(tipo="CODIGO", dispositivo_id="", minutos=1)
        codigo, aut_id = r.json()["entrega"]["codigo"], r.json()["id"]
        m.AutorizacionTemporal.objects.filter(id=aut_id).update(expira_en=1)
        self.assertEqual(self.canjear(codigo=codigo).status_code, 401)

        r = self.otorgar()
        entrega = r.json()["entrega"]
        sesion = self.canjear(grant_id=entrega["grant_id"], token=entrega["token"], dispositivo=self.TABLETA).json()
        temporal = self.con_token(sesion["token"])
        listado = self.docente.get(f"/api/acceso/autorizaciones-temporales/?usuario={self.estudiante_id}").json()
        self.assertEqual(len(listado), 2)
        self.assertEqual(len(self.docente.get(f"/api/acceso/autorizaciones-temporales/?usuario={self.estudiante_id}&vigentes=1").json()), 0)
        self.assertNotIn("entrega", listado[0])
        self.assertEqual(self.docente.delete(f"/api/acceso/autorizaciones-temporales/{r.json()['id']}/").status_code, 204)
        self.assertEqual(temporal.get("/api/acceso/yo/").status_code, 401)

    def test_solo_perfiles_con_acceso_temporal_y_solo_dentro_del_alcance(self):
        # el docente tiene el permiso, pero el administrador no es un estudiante de sus grupos → denegado (nunca «no existe»)
        r = self.docente.post("/api/acceso/autorizaciones-temporales/", {
            "usuario_id": self.admin_id, "tipo": "CODIGO", "motivo": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        # el alcance máximo del permiso es ASSIGNED_GROUPS: ni el administrador lo otorga fuera de un grupo propio
        r = self.admin.post("/api/acceso/autorizaciones-temporales/", {
            "usuario_id": self.estudiante_id, "tipo": "CODIGO", "motivo": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
        # si la política del perfil no admite acceso temporal, el docente recibe 400
        self.assertEqual(self.admin.put("/api/acceso/politicas/student/", {"permite_acceso_temporal": False}, format="json").status_code, 200)
        r = self.otorgar(tipo="CODIGO", dispositivo_id="")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        est = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(est.get("/api/dispositivos/").status_code, 403)
        self.assertEqual([d["nombre"] for d in self.docente.get("/api/dispositivos/").json()], ["tableta-07"])
