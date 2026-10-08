"""Instalación, login, bloqueo, identidad, sesión única, inactividad, cierre y revocación de sesiones."""
from __future__ import annotations

from acceso import models as m

from .base import BaseAcceso


class InstalacionYConfiguracionTests(BaseAcceso):
    def test_la_instalacion_es_unica(self):
        r = self.api.post("/api/acceso/instalacion/", {
            "organizacion": {"codigo": "OTRA", "nombre": "Otra"},
            "administrador": {"nombres": "X", "dni": "1", "password": "Otra.Clave.2026!"}, "pin_maestro": "739104"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "ya_instalado")

    def test_configuracion_publica_sin_pii(self):
        r = self.api.get("/api/acceso/configuracion/")
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertTrue(datos["instalado"])
        self.assertEqual(datos["organizacion"]["locale"], "es-CO")
        student = datos["perfiles"]["student"]
        # RN-31 y D-A3: el PIN es para todos los alumnos y es de 4 dígitos por defecto.
        self.assertEqual((student["tipo_identificador"], student["tipo_secreto"], student["longitud_minima"]),
                         ("CODIGO_ESTUDIANTIL", "PIN", 4))
        self.assertEqual((student["autoregistro"], student["bloqueo_alcance"]), (True, "DISPOSITIVO"))   # RN-37 y RN-33
        self.assertEqual(datos["perfiles"]["admin"]["bloqueo_alcance"], "CUENTA")
        self.assertEqual(student["niveles"], {})
        self.assertEqual(datos["perfiles"]["teacher"]["tipo_secreto"], "PASSWORD")
        self.assertEqual(set(datos["perfiles"]), {"student", "teacher", "admin", "reports", "technician"})
        self.assertEqual((datos["duracion_sesion_min"], datos["inactividad_min"]), (480, 480))
        self.assertIn("preescolar", datos["niveles_educativos"])
        self.assertTrue(datos["claves_derivadas"])  # el prototipo deriva de SECRET_KEY y lo dice

    def test_health_informa_del_modulo(self):
        r = self.api.get("/health/")
        self.assertEqual(r.json()["acceso"]["instalado"], True)

    def test_la_pii_no_esta_en_claro_en_la_base(self):
        persona = m.Persona.objects.get(usuario_id=self.estudiante_id)
        self.assertNotIn("Juan", persona.nombres_cifrado)
        ident = m.IdentificadorUsuario.objects.get(usuario_id=self.estudiante_id, tipo="CODIGO_ESTUDIANTIL")
        self.assertNotIn(self.ESTUDIANTE_CODIGO, ident.valor_cifrado)
        self.assertEqual(len(ident.valor_hmac), 64)
        self.assertEqual(ident.emisor, "IE-SANJOSE")
        self.assertTrue(ident.principal)
        credencial = m.Credencial.objects.get(usuario_id=self.estudiante_id, activa=True)
        self.assertTrue(credencial.hash.startswith("$argon2id$"))

    def test_toda_persona_tiene_asignacion_de_rol(self):
        self.assertEqual(m.UsuarioRol.objects.filter(usuario_id=self.estudiante_id, revocado_en__isnull=True).count(), 1)
        self.assertEqual(m.UsuarioRol.objects.get(usuario_id=self.admin_id).alcance_tipo, "ORGANIZATION")


class LoginTests(BaseAcceso):
    def test_estudiante_entra_con_codigo_y_pin_y_ve_su_menu(self):
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertEqual(datos["tipo"], "Bearer")
        self.assertEqual(datos["usuario"]["menu"], "student")
        self.assertFalse(datos["usuario"]["debe_cambiar_credencial"])
        self.assertIsNone(datos["sesion_anterior"])
        self.assertEqual(datos["roles_disponibles"], ["STUDENT"])
        self.assertEqual(datos["inactividad_min"], 480)
        self.assertAlmostEqual(datos["expira_en"] - m.Sesion.objects.get(id=datos["sesion_id"]).emitida_en, 480 * 60_000, delta=5)
        yo = self.con_token(datos["token"]).get("/api/acceso/yo/").json()
        self.assertEqual(yo["usuario"]["rol"], "STUDENT")
        self.assertEqual(yo["rol_efectivo"], {"codigo": "STUDENT", "menu": "student", "alcance_asignacion": "ORGANIZATION"})
        self.assertEqual(yo["usuario"]["persona"]["nombres"], "Juan")
        self.assertEqual(yo["sesion"]["dispositivo"], "tableta-07")
        self.assertIn({"codigo": "student.exam.attempt", "alcance": "SELF", "origen": "rol", "vigente_hasta": None}, yo["permisos"])
        self.assertEqual(yo["grupos"][0]["codigo"], "8A")

    def test_docente_entra_con_dni_con_puntos_y_admin_ve_permisos_de_organizacion(self):
        self.assertEqual(self.login("80123456", self.DOCENTE_PASS).status_code, 200)
        yo = self.admin.get("/api/acceso/yo/").json()
        self.assertEqual(yo["usuario"]["menu"], "admin")
        self.assertIn({"codigo": "identity.policy.manage", "alcance": "ORGANIZATION", "origen": "rol", "vigente_hasta": None}, yo["permisos"])

    def test_credenciales_invalidas_no_revelan_nada(self):
        mal = self.login(self.ESTUDIANTE_CODIGO, "000001")
        inexistente = self.login("999999", "000001")
        self.assertEqual((mal.status_code, inexistente.status_code), (401, 401))
        self.assertEqual(mal.json()["codigo"], inexistente.json()["codigo"])
        self.assertEqual(mal.json()["intentos_restantes"], 4)
        self.assertEqual(mal["WWW-Authenticate"], "Bearer")

    def test_el_identificador_no_permitido_por_la_politica_no_entra(self):
        # El estudiante tiene DNI registrado pero la política del perfil exige código y su DNI no es de login.
        self.assertEqual(self.login("1020334556", self.ESTUDIANTE_PIN).status_code, 401)

    def test_cinco_fallos_bloquean_y_el_docente_desbloquea(self):
        for _ in range(4):
            self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, "000001").status_code, 401)
        r = self.login(self.ESTUDIANTE_CODIGO, "000001")
        self.assertEqual(r.status_code, 423)
        self.assertEqual(r.json()["codigo"], "usuario_bloqueado")
        self.assertGreater(r.json()["reintentar_en_seg"], 800)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.cuenta.bloqueada.v1", agregado_id=self.estudiante_id).exists())
        # con la clave correcta también está bloqueado
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 423)
        ficha = self.docente.get(f"/api/acceso/usuarios/{self.estudiante_id}/").json()
        self.assertIsNotNone(ficha["bloqueado_hasta"])
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/desbloquear/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 200)
        self.assertTrue(m.IntentoAcceso.objects.filter(usuario_id=self.estudiante_id, resultado="DESBLOQUEO").exists())

    def test_sin_token_o_con_token_roto(self):
        r = self.api.get("/api/acceso/yo/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "sesion_requerida"))
        r = self.con_token("eyJ.basura.xx").get("/api/acceso/yo/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "sesion_invalida"))


class SesionUnicaTests(BaseAcceso):
    def test_abrir_en_otro_dispositivo_cierra_la_anterior_y_lo_avisa(self):
        # TST-027 · PAN-103 · MSG-020
        self.api.post("/api/dispositivos/", {"identificador": "otra-hw", "nombre": "tableta-03"}, format="json")
        primera = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA).json()
        segunda = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, "otra-hw").json()
        self.assertEqual(segunda["sesion_anterior"]["sesion_id"], primera["sesion_id"])
        self.assertEqual(segunda["sesion_anterior"]["dispositivo"], "tableta-07")
        r = self.con_token(primera["token"]).get("/api/acceso/yo/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "sesion_cerrada_otro_dispositivo"))
        self.assertEqual(m.Sesion.objects.get(id=primera["sesion_id"]).motivo_revocacion, "otro_dispositivo")
        self.assertEqual(self.con_token(segunda["token"]).get("/api/acceso/yo/").status_code, 200)
        self.assertEqual(m.Sesion.objects.filter(usuario_id=self.estudiante_id, revocada_en__isnull=True).count(), 1)

    def test_una_tableta_compartida_tiene_una_sola_sesion(self):
        # INV-011 · JRN-022: el siguiente alumno que entra en la misma tableta cierra la del anterior.
        otro = self.docente.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": "María R.", "persona": {"nombres": "María", "apellidos": "Ruiz"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "130010"}], "secreto": "480215",
            "secreto_definitivo": True, "grupo_id": self.grupo["id"]}, format="json").json()
        juan = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA).json()
        maria = self.login("130010", "480215", self.TABLETA).json()
        self.assertIsNone(maria["sesion_anterior"])
        self.assertEqual(m.Sesion.objects.get(id=juan["sesion_id"]).motivo_revocacion, "dispositivo_compartido")
        self.assertEqual(self.con_token(juan["token"]).get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(m.Sesion.objects.filter(dispositivo_id=self.tableta["id"], revocada_en__isnull=True).count(), 1)
        self.assertEqual(m.Sesion.objects.get(id=maria["sesion_id"]).usuario_id, otro["id"])

    def test_sesion_se_cierra_por_inactividad(self):
        # FUN-009
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).json()
        m.Sesion.objects.filter(id=r["sesion_id"]).update(ultimo_uso_en=1, emitida_en=1, expira_en=10**14)
        yo = self.con_token(r["token"]).get("/api/acceso/yo/")
        self.assertEqual((yo.status_code, yo.json()["codigo"]), (401, "sesion_inactiva"))
        self.assertEqual(m.Sesion.objects.get(id=r["sesion_id"]).motivo_revocacion, "inactividad")
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.sesion.cerrada.v1", agregado_id=r["sesion_id"]).exists())

    def test_la_sesion_sobrevive_al_reinicio_del_nodo(self):
        # FUN-011: la sesión está en la base, no en memoria. Otro proceso con el mismo pase la restaura.
        r = self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).json()
        from acceso.infraestructura import contenedor
        contenedor._cache.clear()  # simula un proceso nuevo tras el reinicio
        self.assertEqual(self.con_token(r["token"]).get("/api/acceso/yo/").status_code, 200)


class SesionesTests(BaseAcceso):
    def test_logout_revoca_la_sesion_actual(self):
        estudiante = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(estudiante.delete("/api/acceso/sesiones/actual/").status_code, 204)
        r = estudiante.get("/api/acceso/yo/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "sesion_revocada"))
        self.assertEqual(m.Sesion.objects.filter(usuario_id=self.estudiante_id).latest("emitida_en").motivo_revocacion, "persona")

    def test_docente_lista_y_revoca_sesiones_de_sus_estudiantes(self):
        estudiante = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        sesiones = self.docente.get(f"/api/acceso/sesiones/?usuario={self.estudiante_id}").json()
        self.assertEqual(len(sesiones), 1)
        self.assertEqual((sesiones[0]["dispositivo"], sesiones[0]["rol"]), ("tableta-07", "STUDENT"))
        self.assertEqual(self.docente.delete(f"/api/acceso/sesiones/{sesiones[0]['id']}/").status_code, 204)
        self.assertEqual(estudiante.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(m.Sesion.objects.get(id=sesiones[0]["id"]).motivo_revocacion, "profesor")
        # el docente tiene el permiso, pero el administrador no está en su alcance → 403 (nunca 404)
        r = self.docente.get(f"/api/acceso/sesiones/?usuario={self.admin_id}")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

    def test_revocar_todas_las_sesiones_de_un_usuario(self):
        # FUN-010
        self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        r = self.admin.delete(f"/api/acceso/usuarios/{self.estudiante_id}/sesiones/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["sesiones_revocadas"], 1)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.sesiones.revocadas.v1").exists())

    def test_estudiante_no_revoca_sesiones_ajenas(self):
        estudiante = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        docente_sesion = self.admin.get(f"/api/acceso/sesiones/?usuario={self.docente_id}").json()[0]["id"]
        self.assertEqual(estudiante.delete(f"/api/acceso/sesiones/{docente_sesion}/").status_code, 403)
        self.assertIsNone(m.Sesion.objects.get(id=docente_sesion).revocada_en)

    def test_sesion_expirada(self):
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).json()
        m.Sesion.objects.filter(id=r["sesion_id"]).update(emitida_en=0, expira_en=1)
        yo = self.con_token(r["token"]).get("/api/acceso/yo/")
        self.assertEqual((yo.status_code, yo.json()["codigo"]), (401, "sesion_expirada"))
