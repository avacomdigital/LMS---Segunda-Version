"""
Entrar como visitante (RN-40…RN-47, RB-07, RB-19, RB-25): sin profesor, PIN ni código; una cuenta efímera con permisos mínimos que se retira al
cerrar. Cubre AC-A14, A15, A16, A19 y A21 de los requisitos.
"""
from __future__ import annotations

from django.db.models import F

from acceso import models as m

from .base import BaseAcceso

HORA = 3_600_000


class AbrirSesionVisitanteTests(BaseAcceso):
    def setUp(self):
        super().setUp()
        self.otra = self.api.post("/api/dispositivos/", {"identificador": "otra-hw", "nombre": "tableta-03"}, format="json").json()

    def visitar(self, dispositivo=None, **extra):
        return self.api.post("/api/acceso/sesiones/visitante/", {"dispositivo": dispositivo or self.TABLETA, **extra}, format="json")

    def test_entra_en_un_toque_sin_profesor_ni_pin_ni_codigo(self):
        # AC-A14 · RN-41
        r = self.visitar()
        self.assertEqual(r.status_code, 200, r.content)
        datos = r.json()
        self.assertEqual(datos["usuario"]["clase_sesion"], "VISITANTE")
        self.assertEqual((datos["usuario"]["rol"], datos["usuario"]["alias"]), ("STUDENT", "Visitante · tableta-07"))
        self.assertTrue(datos["usuario"]["provisional"])
        self.assertEqual(datos["usuario"]["origen"], "VISITANTE")
        yo = self.con_token(datos["token"]).get("/api/acceso/yo/")
        self.assertEqual(yo.status_code, 200, yo.content)
        self.assertEqual({p["codigo"] for p in yo.json()["permisos"]}, {"content.read", "identity.session.revoke_own"})   # sólo leer y salir

    def test_la_visita_es_una_cuenta_efimera_de_rol_alumno_sin_clave_ni_grupo(self):
        # RN-45
        usuario = m.Usuario.objects.get(id=self.visitar().json()["usuario"]["id"])
        self.assertEqual((usuario.origen, usuario.provisional, usuario.estado, usuario.rol.codigo), ("VISITANTE", True, "ACTIVO", "STUDENT"))
        self.assertFalse(m.Credencial.objects.filter(usuario=usuario).exists())
        self.assertFalse(m.MiembroGrupo.objects.filter(usuario=usuario).exists())
        self.assertFalse(usuario.identificadores.get().es_login)        # tiene identificador (DEC-049) pero no sirve para entrar
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.sesion.visitante_abierta.v1").exists())

    def test_la_visita_no_entra_a_la_lista_de_nombres_ni_se_puede_usar_para_iniciar_sesion(self):
        visita = self.visitar().json()["usuario"]
        lista = self.api.get(f"/api/acceso/aula/grupos/{self.grupo['id']}/estudiantes/?dispositivo={self.TABLETA}").json()
        self.assertEqual([a["alias"] for a in lista], ["Juan P."])
        r = self.api.post("/api/acceso/sesiones/", {"usuario_id": visita["id"], "secreto": "1234", "dispositivo": self.TABLETA}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_no_puede_ver_progreso_ni_estudio_asignado_ni_usuarios(self):
        # AC-A15 · RN-43: la causa exacta, no un «sin permiso» genérico
        token = self.visitar().json()["token"]
        visita = self.con_token(token)
        for ruta in ("/api/acceso/usuarios/", "/api/acceso/grupos/", "/api/modo-estudio/asignaciones/", f"/api/acceso/usuarios/{self.estudiante_id}/"):
            r = visita.get(ruta)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sesion_visitante_limitada"), ruta)
        r = visita.put("/api/acceso/yo/credencial/", {"secreto_actual": "1234", "secreto_nuevo": "4321"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sesion_visitante_limitada"))     # ninguna credencial se cambia
        r = visita.post("/api/acceso/autorizaciones-temporales/", {"usuario_id": self.estudiante_id, "tipo": "CODIGO"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_la_sesion_de_visitante_no_rinde_evaluaciones(self):
        # AC-A15 · RN-43: abrir el intento de una evaluación formal exige `assessment.attempt.start`, que la visita no tiene
        visita = self.con_token(self.visitar().json()["token"])
        r = visita.post("/api/evaluacion/asignaciones/cualquiera/intentos/", {"dispositivo": self.TABLETA}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sesion_visitante_limitada"))

    def test_cerrar_la_sesion_retira_la_cuenta_pero_no_la_borra(self):
        # AC-A19 · RN-45 · CV-05
        datos = self.visitar().json()
        visita = self.con_token(datos["token"])
        self.assertEqual(visita.delete("/api/acceso/sesiones/actual/").status_code, 204)
        usuario = m.Usuario.objects.get(id=datos["usuario"]["id"])
        self.assertEqual(usuario.estado, "RETIRADO")
        self.assertEqual(visita.get("/api/acceso/yo/").status_code, 401)

    def test_pasadas_24_horas_se_retira_sola_y_cierra_su_sesion(self):
        datos = self.visitar().json()
        m.Usuario.objects.filter(id=datos["usuario"]["id"]).update(creado_en=F("creado_en") - 25 * HORA)
        self.visitar("otra-hw")                                         # la próxima visita barre a las vencidas
        self.assertEqual(m.Usuario.objects.get(id=datos["usuario"]["id"]).estado, "RETIRADO")
        self.assertEqual(m.Sesion.objects.get(id=datos["sesion_id"]).motivo_revocacion, "visita_retirada")

    def test_la_sesion_de_una_visita_dura_como_mucho_un_dia(self):
        datos = self.visitar().json()
        sesion = m.Sesion.objects.get(id=datos["sesion_id"])
        self.assertLessEqual(sesion.expira_en - sesion.emitida_en, 24 * HORA)

    def test_con_la_politica_visitante_apagada_no_se_puede_entrar(self):
        # RN-47
        r = self.admin.put("/api/acceso/politicas/student/", {"visitante": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["visitante"], False)
        self.assertFalse(self.api.get("/api/acceso/configuracion/").json()["visitante"])
        r = self.visitar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "visitante_no_permitido"))
        self.admin.put("/api/acceso/politicas/student/", {"visitante": True}, format="json")
        self.assertEqual(self.visitar().status_code, 200)

    def test_solo_el_perfil_de_estudiantes_enciende_el_interruptor_de_visitantes(self):
        r = self.admin.put("/api/acceso/politicas/teacher/", {"visitante": False}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))

    def test_solo_desde_una_tableta_registrada(self):
        for dispositivo in ("", "desconocida"):
            r = self.api.post("/api/acceso/sesiones/visitante/", {"dispositivo": dispositivo}, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"))

    def test_dos_visitas_en_dos_tabletas_conviven_porque_son_cuentas_distintas(self):
        # D-A7: la sesión única por persona no hace que una visita cierre a otra
        una, otra = self.visitar().json(), self.visitar("otra-hw").json()
        self.assertNotEqual(una["usuario"]["id"], otra["usuario"]["id"])
        self.assertEqual(otra["usuario"]["alias"], "Visitante · tableta-03")
        self.assertEqual(self.con_token(una["token"]).get("/api/acceso/yo/").status_code, 200)
        self.assertEqual(self.con_token(otra["token"]).get("/api/acceso/yo/").status_code, 200)

    def test_quien_entra_despues_en_la_tableta_cierra_la_visita_y_la_retira(self):
        # INV-011
        visita = self.visitar().json()
        juan = self.api.post("/api/acceso/sesiones/", {"usuario_id": self.estudiante_id, "secreto": self.ESTUDIANTE_PIN, "dispositivo": self.TABLETA}, format="json")
        self.assertEqual(juan.status_code, 200, juan.content)
        self.assertEqual(m.Sesion.objects.get(id=visita["sesion_id"]).motivo_revocacion, "dispositivo_compartido")
        self.assertEqual(m.Usuario.objects.get(id=visita["usuario"]["id"]).estado, "RETIRADO")
        # y al revés: la visita cierra la sesión de quien estaba
        self.visitar()
        self.assertEqual(self.con_token(juan.json()["token"]).get("/api/acceso/yo/").status_code, 401)

    def test_entrar_como_visitante_nunca_se_bloquea_ni_con_la_tableta_en_pausa(self):
        # RN-33 · RF-26
        for _ in range(5):
            self.api.post("/api/acceso/sesiones/", {"usuario_id": self.estudiante_id, "secreto": "0000", "dispositivo": self.TABLETA}, format="json")
        r = self.api.post("/api/acceso/sesiones/", {"usuario_id": self.estudiante_id, "secreto": self.ESTUDIANTE_PIN, "dispositivo": self.TABLETA}, format="json")
        self.assertEqual(r.json()["codigo"], "dispositivo_en_pausa")
        self.assertEqual(self.visitar().status_code, 200)

    def test_el_profesor_ve_quienes_entraron_como_visitante_y_desde_que_tableta(self):
        # RN-46
        self.visitar()
        self.visitar("otra-hw")
        r = self.docente.get("/api/acceso/visitantes/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(sorted((v["alias"], v["dispositivo"]) for v in r.json()),
                         [("Visitante · tableta-03", "tableta-03"), ("Visitante · tableta-07", "tableta-07")])
        self.assertEqual(self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).get("/api/acceso/visitantes/").status_code, 403)

    def test_el_profesor_vincula_una_visita_a_un_alumno_y_nada_queda_en_el_expediente_de_otro(self):
        # AC-A16 · RN-44: el mismo mecanismo de la admisión nominal (JRN-007)
        visita = self.visitar().json()["usuario"]
        r = self.docente.post(f"/api/acceso/usuarios/{visita['id']}/vincular/", {"usuario_definitivo_id": self.estudiante_id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        fila = m.Usuario.objects.get(id=visita["id"])
        self.assertEqual((fila.estado, fila.vinculado_a_id), ("RETIRADO", self.estudiante_id))
        # no puede vincularla a alguien fuera de su alcance
        otro = self.admin.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": "Pablo", "persona": {"nombres": "Pablo"}, "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "170099"}],
            "secreto": "4821", "secreto_definitivo": True, "grupo_id": self.otro_grupo["id"]}, format="json").json()
        nueva = self.visitar().json()["usuario"]
        r = self.docente.post(f"/api/acceso/usuarios/{nueva['id']}/vincular/", {"usuario_definitivo_id": otro["id"]}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_con_sesion_obligatoria_el_visitante_pasa_con_sus_permisos_limitados_y_sin_pase_no_se_pasa(self):
        # AC-A21 · RB-40
        from django.test import override_settings
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.api.get("/api/aula/sesiones/").status_code, 401)
            self.assertEqual(self.api.get("/api/modo-estudio/asignaciones/").status_code, 401)
            visita = self.con_token(self.visitar().json()["token"])
            r = visita.get("/api/modo-estudio/asignaciones/")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sesion_visitante_limitada"))
            self.assertEqual(visita.get("/api/acceso/yo/").status_code, 200)
