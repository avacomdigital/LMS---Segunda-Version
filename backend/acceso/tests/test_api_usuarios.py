"""Usuarios: creación por alcance, importación, admisión nominal, credenciales, roles con alcance, escaladas, grupos y políticas."""
from __future__ import annotations

import time

from acceso import models as m

from .base import BaseAcceso


def estudiante(codigo: str, grupo_id: str | None = None, **extra) -> dict:
    datos = {"rol": "STUDENT", "alias": f"Alumno {codigo}", "persona": {"nombres": "Nombre", "apellidos": "Apellido"},
             "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": codigo, "es_login": True}]}
    if grupo_id:
        datos["grupo_id"] = grupo_id
    datos.update(extra)
    return datos


class CrearUsuarioTests(BaseAcceso):
    def test_docente_crea_estudiante_en_su_grupo_y_recibe_pin_generado_una_vez(self):
        # Con `POST /usuarios/` el nodo sigue generando el PIN (de 4 dígitos, RN-31); el padrón y la importación, en cambio, lo dejan pendiente (RB-26).
        r = self.docente.post("/api/acceso/usuarios/", estudiante("130001", self.grupo["id"]), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        datos = r.json()
        self.assertRegex(datos["secreto_inicial"], r"^\d{4}$")
        self.assertTrue(datos["debe_cambiar_credencial"])
        self.assertEqual(datos["grupos"][0]["codigo"], "8A")
        self.assertEqual((datos["origen"], datos["confirmado"]), ("PROFESOR", True))
        self.assertEqual(datos["roles"][0]["rol"], "STUDENT")
        ficha = self.docente.get(f"/api/acceso/usuarios/{datos['id']}/").json()
        self.assertNotIn("secreto_inicial", ficha)
        self.assertEqual(ficha["identificadores"][0]["valor"], "130001")
        self.assertTrue(ficha["identificadores"][0]["principal"])
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.usuario.creado.v1", agregado_id=datos["id"]).exists())

    def test_sin_identificador_el_nodo_emite_una_clave_de_instalacion(self):
        # DEC-049: nunca existe una persona sin identificador externo.
        r = self.docente.post("/api/acceso/usuarios/", {**estudiante("x", self.grupo["id"]), "identificadores": []}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        ident = r.json()["identificadores"][0]
        self.assertEqual(ident["tipo"], "CLAVE_INSTALACION")
        self.assertTrue(ident["valor"].startswith("IE-SANJOSE-"))
        self.assertEqual(ident["emisor"], "IE-SANJOSE")

    def test_docente_no_crea_en_grupo_ajeno_ni_docentes_ni_sin_grupo(self):
        r = self.docente.post("/api/acceso/usuarios/", estudiante("130002", self.otro_grupo["id"]), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        r = self.docente.post("/api/acceso/usuarios/", estudiante("130003"), format="json")
        self.assertEqual(r.status_code, 400)
        r = self.docente.post("/api/acceso/usuarios/", {**estudiante("130004", self.grupo["id"]), "rol": "TEACHER",
                                                        "identificadores": [{"tipo": "DNI", "valor": "555"}]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

    def test_pin_debil_y_identificador_duplicado(self):
        r = self.docente.post("/api/acceso/usuarios/", estudiante("130005", self.grupo["id"], secreto="12"), format="json")   # RN-31: 4 a 6 dígitos
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "secreto_debil"))
        self.assertTrue(r.json()["reglas"])
        r = self.docente.post("/api/acceso/usuarios/", estudiante(self.ESTUDIANTE_CODIGO, self.grupo["id"]), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "identificador_duplicado"))
        self.assertEqual(m.Usuario.objects.filter(alias__startswith="Alumno").count(), 0)

    def test_estudiante_no_crea_usuarios_y_solo_se_lista_a_si_mismo(self):
        est = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(est.post("/api/acceso/usuarios/", estudiante("130006"), format="json").status_code, 403)
        lista = est.get("/api/acceso/usuarios/").json()
        self.assertEqual([u["id"] for u in lista], [self.estudiante_id])
        self.assertEqual(est.get(f"/api/acceso/usuarios/{self.docente_id}/").status_code, 403)

    def test_listados_por_alcance(self):
        self.admin.post("/api/acceso/usuarios/", estudiante("140001", self.otro_grupo["id"]), format="json")
        del_docente = {u["alias"] for u in self.docente.get("/api/acceso/usuarios/").json()}
        self.assertEqual(del_docente, {"Prof. Gómez", "Juan P."})
        del_admin = {u["alias"] for u in self.admin.get("/api/acceso/usuarios/").json()}
        self.assertEqual(del_admin, {"Rectoría", "Prof. Gómez", "Juan P.", "Alumno 140001"})
        self.assertEqual(self.docente.get(f"/api/acceso/usuarios/?grupo={self.otro_grupo['id']}").status_code, 403)
        self.assertEqual(len(self.admin.get("/api/acceso/usuarios/?rol=STUDENT").json()), 2)


class ImportacionTests(BaseAcceso):
    CSV = ("rol,alias,nombres,apellidos,tipo_identificador,identificador,grupo,secreto\n"
           "STUDENT,,Carlos,Torres,CODIGO_ESTUDIANTIL,150001,8A,\n"
           "STUDENT,Sofi L.,Sofía,López,CODIGO_ESTUDIANTIL,150002,9B,\n"
           f"STUDENT,,Juan,Pérez,CODIGO_ESTUDIANTIL,{BaseAcceso.ESTUDIANTE_CODIGO},8A,\n"
           "STUDENT,,Pedro,Ruiz,CODIGO_ESTUDIANTIL,150003,NO-EXISTE,\n"
           "TEACHER,Prof. Díaz,Ana,Díaz,DNI,90111222,,Docente.2026!\n")

    def test_admin_importa_el_padron_fusiona_existentes_y_devuelve_rechazadas(self):
        # FUN-003 / JRN-003 / MSG-065
        r = self.admin.post("/api/acceso/usuarios/importar/", {"contenido": self.CSV}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        datos = r.json()
        self.assertEqual(datos["resumen"], {"total": 5, "creados": 3, "existentes": 1, "rechazadas": 1})
        self.assertEqual(datos["existentes"][0]["identificador"], self.ESTUDIANTE_CODIGO)
        self.assertEqual(datos["rechazadas"][0]["fila"], 4)
        creados = {c["identificador"]: c for c in datos["creados"]}
        # RB-26 / RN-35: un alumno importado sin PIN queda «pendiente»: no se genera ni se entrega ningún número.
        self.assertIsNone(creados["150001"]["secreto_inicial"])
        self.assertFalse(m.Credencial.objects.filter(usuario_id=creados["150001"]["id"]).exists())
        self.assertEqual(creados["150001"]["alias"], "Carlos T.")
        self.assertEqual(creados["150002"]["grupo"], "9B")
        self.assertIsNone(creados["90111222"]["secreto_inicial"])
        self.assertEqual(self.login("90111222", "Docente.2026!").status_code, 200)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.usuarios.importados.v1").exists())

    def test_columnas_invalidas_o_sin_permiso(self):
        r = self.admin.post("/api/acceso/usuarios/importar/", {"contenido": "nombre,clave\nJuan,1\n"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertIn("columnas_esperadas", r.json())
        r = self.docente.post("/api/acceso/usuarios/importar/", {"contenido": self.CSV}, format="json")
        self.assertEqual(r.status_code, 403)


class AdmisionNominalTests(BaseAcceso):
    def test_profesor_admite_por_nombre_y_vincula_despues(self):
        # JRN-007 · MSG-023: el alumno no tiene su credencial a la mano.
        r = self.docente.post("/api/acceso/usuarios/", {"rol": "STUDENT", "alias": "Lucía", "provisional": True,
                                                        "grupo_id": self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        provisional = r.json()
        self.assertTrue(provisional["provisional"])
        self.assertEqual(provisional["identificadores"][0]["tipo"], "CLAVE_INSTALACION")
        # El profesor le da el pase de examen a la tableta y Lucía trabaja.
        aut = self.docente.post("/api/acceso/autorizaciones-temporales/", {
            "usuario_id": provisional["id"], "tipo": "DISPOSITIVO", "dispositivo_id": self.tableta["id"], "motivo": "sin credencial"}, format="json")
        self.assertEqual(aut.status_code, 201, aut.content)
        # Llega el padrón con la Lucía definitiva.
        definitiva = self.admin.post("/api/acceso/usuarios/", estudiante("160001", self.grupo["id"], alias="Lucía M."), format="json").json()
        r = self.docente.post(f"/api/acceso/usuarios/{provisional['id']}/vincular/", {"usuario_definitivo_id": definitiva["id"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        fila = m.Usuario.objects.get(id=provisional["id"])
        self.assertEqual((fila.estado, fila.vinculado_a_id), ("RETIRADO", definitiva["id"]))
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.usuario.vinculado.v1", agregado_id=provisional["id"]).exists())
        # y no se puede vincular dos veces ni a una cuenta que no es provisional
        self.assertEqual(self.docente.post(f"/api/acceso/usuarios/{definitiva['id']}/vincular/", {"usuario_definitivo_id": provisional["id"]}, format="json").status_code, 409)


class CredencialTests(BaseAcceso):
    def test_restablecer_a_un_profesor_devuelve_secreto_una_vez_y_obliga_a_cambiarlo(self):
        abierta = self.docente
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/credencial/restablecer/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        provisional = r.json()["secreto_provisional"]
        self.assertGreaterEqual(len(provisional), 8)
        self.assertFalse(r.json()["pin_pendiente"])
        self.assertEqual(r.json()["sesiones_revocadas"], 1)
        self.assertEqual(abierta.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 401)

        entrada = self.login(self.DOCENTE_DNI, provisional)
        self.assertTrue(entrada.json()["usuario"]["debe_cambiar_credencial"])
        prof = self.con_token(entrada.json()["token"])
        r = prof.get("/api/acceso/usuarios/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "debe_cambiar_credencial"))
        r = prof.put("/api/acceso/yo/credencial/", {"secreto_actual": provisional, "secreto_nuevo": "NuevaClave.2026!"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(prof.get("/api/acceso/yo/").status_code, 200)
        self.assertEqual(self.login(self.DOCENTE_DNI, "NuevaClave.2026!").status_code, 200)

    def test_restablecer_a_un_alumno_lo_deja_en_pin_pendiente_sin_entregar_ningun_numero(self):
        # RB-23 / RN-35 / AC-A17: el profesor nunca ve un número; el alumno elige uno nuevo al tocar su nombre.
        abierta = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["secreto_provisional"])
        self.assertTrue(r.json()["pin_pendiente"])
        self.assertEqual(r.json()["sesiones_revocadas"], 1)
        self.assertEqual(abierta.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 401)
        self.assertFalse(m.Credencial.objects.filter(usuario_id=self.estudiante_id, activa=True).exists())
        self.assertEqual(self.docente.get(f"/api/acceso/usuarios/{self.estudiante_id}/").json()["tiene_credencial"], False)

    def test_no_se_reutiliza_una_credencial_anterior(self):
        est = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = est.put("/api/acceso/yo/credencial/", {"secreto_actual": self.ESTUDIANTE_PIN, "secreto_nuevo": self.ESTUDIANTE_PIN}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "secreto_debil"))
        r = est.put("/api/acceso/yo/credencial/", {"secreto_actual": "mal", "secreto_nuevo": "480215"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_el_docente_no_restablece_al_administrador(self):
        r = self.docente.post(f"/api/acceso/usuarios/{self.admin_id}/credencial/restablecer/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

    def test_politica_de_grupo_sobrescribe_la_del_perfil(self):
        politicas = {p["perfil"]: p for p in self.admin.get("/api/acceso/politicas/").json() if not p["nivel_clave"]}
        r = self.admin.patch(f"/api/acceso/grupos/{self.grupo['id']}/", {"politica_credencial_id": politicas["teacher"]["id"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        ficha = self.docente.get(f"/api/acceso/usuarios/{self.estudiante_id}/").json()
        self.assertEqual(ficha["tipo_secreto"], "PASSWORD")
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {"secreto": "480215"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "secreto_debil"))
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 401)

    def test_politica_por_nivel_educativo_preescolar_con_avatar(self):
        # BR-024: el administrador habilita el método simplificado para un nivel.
        r = self.admin.put("/api/acceso/politicas/student/?nivel=preescolar", {"tipo_secreto": "AVATAR", "longitud_minima": 4}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["nivel_clave"], r.json()["tipo_secreto"]), ("preescolar", "AVATAR"))
        self.assertEqual(self.api.get("/api/acceso/configuracion/").json()["perfiles"]["student"]["niveles"]["preescolar"]["tipo_secreto"], "AVATAR")
        pre = self.admin.post("/api/acceso/grupos/", {"codigo": "TR-A", "nombre": "Transición A", "periodo": "2026", "nivel_clave": "preescolar"},
                              format="json").json()
        r = self.admin.post("/api/acceso/usuarios/", estudiante("170001", pre["id"], secreto="gato-azul", secreto_definitivo=True), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["tipo_secreto"], "AVATAR")
        self.assertEqual(self.login("170001", "gato-azul").status_code, 200)
        # el estudiante de octavo sigue con PIN
        self.assertEqual(self.docente.get(f"/api/acceso/usuarios/{self.estudiante_id}/").json()["tipo_secreto"], "PIN")

    def test_configurar_politica_valida_coherencia(self):
        r = self.admin.put("/api/acceso/politicas/student/", {"tipo_secreto": "PIN", "longitud_minima": 12}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "politica_invalida"))
        r = self.admin.put("/api/acceso/politicas/student/", {"inactividad_min": 500}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "politica_invalida"))
        r = self.admin.put("/api/acceso/politicas/student/", {"tipo_identificador": "CUALQUIERA", "duracion_sesion_min": 120, "inactividad_min": 15}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).json()["inactividad_min"], 15)
        self.assertEqual(self.docente.put("/api/acceso/politicas/student/", {"longitud_minima": 4}, format="json").status_code, 403)


class RolesTests(BaseAcceso):
    def test_admin_asigna_rol_adicional_y_la_persona_elige_al_entrar(self):
        # FUN-002 · BR-021: varios roles, uno efectivo por sesión.
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/roles/", {"rol": "REPORTS"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual({a["rol"] for a in r.json()["roles"]}, {"TEACHER", "REPORTS"})
        # sin elegir, entra con el principal
        como_docente = self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).json()
        self.assertEqual((como_docente["usuario"]["menu"], sorted(como_docente["roles_disponibles"])), ("teacher", ["REPORTS", "TEACHER"]))
        # eligiendo, entra como Reportes y sólo ve lo de Reportes
        como_reportes = self.login(self.DOCENTE_DNI, self.DOCENTE_PASS, rol="REPORTS").json()
        self.assertEqual(como_reportes["usuario"]["menu"], "reports")
        yo = self.con_token(como_reportes["token"]).get("/api/acceso/yo/").json()
        self.assertEqual(yo["rol_efectivo"]["codigo"], "REPORTS")
        codigos = {p["codigo"] for p in yo["permisos"]}
        self.assertIn("reports.student.view", codigos)
        self.assertNotIn("identity.password.reset", codigos)
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS, rol="ADMIN").status_code, 401)

    def test_asignacion_acotada_a_un_nivel(self):
        # Una coordinadora de secundaria: rol de administración acotado al nivel.
        for g in (self.grupo, self.otro_grupo):
            self.admin.patch(f"/api/acceso/grupos/{g['id']}/", {"nivel_clave": "secundaria"}, format="json")
        once = self.admin.post("/api/acceso/grupos/", {"codigo": "11A", "nombre": "Once A", "periodo": "2026", "nivel_clave": "bachillerato"}, format="json").json()
        bachiller = self.admin.post("/api/acceso/usuarios/", estudiante("180001", once["id"]), format="json").json()
        de_noveno = self.admin.post("/api/acceso/usuarios/", estudiante("180002", self.otro_grupo["id"]), format="json").json()
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/roles/",
                            {"rol": "ADMIN", "alcance_tipo": "LEVEL", "alcance_id": "secundaria"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        coord = self.sesion(self.DOCENTE_DNI, self.DOCENTE_PASS)
        coord = self.con_token(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS, rol="ADMIN", pin_maestro=self.PIN_MAESTRO).json()["token"])
        yo = coord.get("/api/acceso/yo/").json()
        self.assertEqual(yo["rol_efectivo"]["alcance_asignacion"], "LEVEL")
        self.assertEqual(coord.get(f"/api/acceso/usuarios/{de_noveno['id']}/").status_code, 200)   # 9B es de secundaria
        self.assertEqual(coord.get(f"/api/acceso/usuarios/{bachiller['id']}/").status_code, 403)   # 11A no
        self.assertEqual(coord.put("/api/acceso/politicas/student/", {"inactividad_min": 10}, format="json").status_code, 403)  # organización

    def test_asignar_rol_principal_revoca_sesiones_y_el_docente_no_puede(self):
        est = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.admin.put(f"/api/acceso/usuarios/{self.estudiante_id}/rol/", {"rol": "TEACHER"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["menu"], "teacher")
        self.assertEqual(est.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(self.docente.put(f"/api/acceso/usuarios/{self.estudiante_id}/rol/", {"rol": "ADMIN"}, format="json").status_code, 403)

    def test_revocar_asignacion_nunca_deja_a_la_persona_sin_rol(self):
        roles = self.admin.get(f"/api/acceso/usuarios/{self.docente_id}/roles/").json()
        self.assertEqual(self.admin.delete(f"/api/acceso/usuarios/{self.docente_id}/roles/{roles[0]['id']}/").status_code, 409)
        self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/roles/", {"rol": "REPORTS"}, format="json")
        reportes = next(a for a in self.admin.get(f"/api/acceso/usuarios/{self.docente_id}/roles/").json() if a["rol"] == "REPORTS")
        self.assertEqual(self.admin.delete(f"/api/acceso/usuarios/{self.docente_id}/roles/{reportes['id']}/").status_code, 204)
        self.assertEqual([a["rol"] for a in self.admin.get(f"/api/acceso/usuarios/{self.docente_id}/roles/").json()], ["TEACHER"])

    def test_rol_del_colegio_clonado_de_plantilla(self):
        r = self.admin.post("/api/acceso/roles/", {
            "codigo": "COORDINADOR", "nombre": "Coordinador", "plantilla": "TEACHER",
            "permisos": [{"codigo": "audit.read", "alcance": "ORGANIZATION"}, {"codigo": "content.project", "alcance": None}],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        permisos = {p["codigo"]: p["alcance"] for p in r.json()["permisos"]}
        self.assertEqual(permisos["audit.read"], "ORGANIZATION")
        self.assertNotIn("content.project", permisos)
        self.assertEqual(permisos["identity.password.reset"], "ASSIGNED_GROUPS")
        codigos = {rol["codigo"] for rol in self.docente.get("/api/acceso/roles/").json()}
        self.assertEqual(codigos, {"STUDENT", "TEACHER", "ADMIN", "REPORTS", "TECHNICIAN", "COORDINADOR"})
        self.assertEqual(self.docente.post("/api/acceso/roles/", {"codigo": "X", "nombre": "X"}, format="json").status_code, 403)
        sensibles = {p["codigo"] for p in self.admin.get("/api/acceso/permisos/").json() if p["sensible"]}
        self.assertIn("identity.password.reset", sensibles)


class EscaladaTests(BaseAcceso):
    def hasta(self, horas: float) -> int:
        return int(time.time() * 1000) + int(horas * 3_600_000)

    def test_escalada_con_caducidad_obligatoria_y_revocacion(self):
        # BR-101
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/escaladas/",
                            {"permiso": "audit.read", "alcance": "ORGANIZATION", "motivo": "Coordinadora académica 2026"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/escaladas/",
                            {"permiso": "audit.read", "alcance": "ORGANIZATION", "motivo": "x", "vigente_hasta": self.hasta(48)}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/escaladas/",
                            {"permiso": "audit.read", "alcance": "ORGANIZATION", "motivo": "Coordinadora académica 2026",
                             "vigente_hasta": self.hasta(4)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        permisos = {p["codigo"]: p for p in self.docente.get("/api/acceso/yo/").json()["permisos"]}
        self.assertEqual((permisos["audit.read"]["origen"], permisos["audit.read"]["alcance"]), ("adicional", "ORGANIZATION"))
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.escalada.concedida.v1").exists())
        self.assertEqual(self.admin.delete(f"/api/acceso/usuarios/{self.docente_id}/escaladas/audit.read/").status_code, 204)
        self.assertNotIn("audit.read", {p["codigo"] for p in self.docente.get("/api/acceso/yo/").json()["permisos"]})

    def test_no_hay_autoconcesion_ni_techo_superado_ni_docente_concediendo(self):
        r = self.admin.post(f"/api/acceso/usuarios/{self.admin_id}/escaladas/",
                            {"permiso": "audit.read", "alcance": "ORGANIZATION", "motivo": "x", "vigente_hasta": self.hasta(1)}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/escaladas/",
                              {"permiso": "audit.read", "alcance": "SELF", "motivo": "x", "vigente_hasta": self.hasta(1)}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/escaladas/",
                            {"permiso": "identity.password.change_own", "alcance": "ORGANIZATION", "motivo": "x", "vigente_hasta": self.hasta(1)}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))


class GruposTests(BaseAcceso):
    def test_docente_ve_sus_grupos_y_gestiona_solo_estudiantes(self):
        grupos = self.docente.get("/api/acceso/grupos/").json()
        self.assertEqual([g["codigo"] for g in grupos], ["8A"])
        self.assertEqual(grupos[0]["papel"], "DOCENTE")
        detalle = self.docente.get(f"/api/acceso/grupos/{self.grupo['id']}/").json()
        self.assertEqual({(x["alias"], x["papel"]) for x in detalle["miembros"]}, {("Prof. Gómez", "DOCENTE"), ("Juan P.", "ESTUDIANTE")})
        r = self.docente.post(f"/api/acceso/grupos/{self.grupo['id']}/miembros/", {"usuario_id": self.admin_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.docente.get(f"/api/acceso/grupos/{self.otro_grupo['id']}/").status_code, 403)
        self.assertEqual(self.docente.delete(f"/api/acceso/grupos/{self.grupo['id']}/miembros/{self.estudiante_id}/").status_code, 204)
        self.assertEqual(self.docente.get(f"/api/acceso/usuarios/{self.estudiante_id}/").status_code, 403)

    def test_estudiante_ve_su_grupo_pero_no_lo_administra(self):
        est = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual([g["codigo"] for g in est.get("/api/acceso/grupos/").json()], ["8A"])
        self.assertEqual(est.post("/api/acceso/grupos/", {"codigo": "X", "nombre": "X", "periodo": "2026"}, format="json").status_code, 403)

    def test_suspender_revoca_y_la_baja_no_se_revierte(self):
        est = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.docente.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {"estado": "SUSPENDIDO"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(est.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 401)
        # BR-025: la baja conserva identidad e historial y no se reactiva; el código sigue reservado.
        self.assertEqual(self.docente.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {"estado": "RETIRADO"}, format="json").status_code, 200)
        r = self.docente.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {"estado": "ACTIVO"}, format="json")
        self.assertEqual(r.status_code, 409)
        r = self.docente.post("/api/acceso/usuarios/", estudiante(self.ESTUDIANTE_CODIGO, self.grupo["id"]), format="json")
        self.assertEqual(r.json()["codigo"], "identificador_duplicado")

    def test_cambiar_identificadores_retira_en_vez_de_borrar(self):
        r = self.docente.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "122500", "es_login": True}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        filas = m.IdentificadorUsuario.objects.filter(usuario_id=self.estudiante_id)
        self.assertEqual((filas.count(), filas.filter(retirado_en__isnull=True).count()), (3, 1))
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 401)
        self.assertEqual(self.login("122500", self.ESTUDIANTE_PIN).status_code, 200)
