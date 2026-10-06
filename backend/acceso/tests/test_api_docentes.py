"""
El profesor crea su propio usuario y restablece su propia contraseña con el PIN maestro (RN-20…RN-25, RB-13…RB-15, RB-28), sin sesión y
sin internet. Cubre AC-A04, A07…A10 de los requisitos.
"""
from __future__ import annotations

from django.db.models import F

from acceso import models as m
from acceso.dominio.politicas import PoliticaPinMaestro as P

from .base import BaseAcceso

NUEVO_DNI = "52.100.200"
NUEVA_CLAVE = "Profe.Nuevo.2026!"


class RegistroDelDocenteTests(BaseAcceso):
    def setUp(self):
        super().setUp()
        self.registrar_equipo_master()

    def datos(self, **cambios):
        base = {"pin_maestro": self.PIN_MAESTRO, "documento": NUEVO_DNI, "nombres": "Marta", "apellidos": "Ríos", "secreto": NUEVA_CLAVE,
                "grupos": [self.grupo["id"]], "dispositivo": self.MASTER}
        base.update(cambios)
        return base

    def registrar(self, **cambios):
        return self.api.post("/api/acceso/docentes/registro/", self.datos(**cambios), format="json")

    def test_el_profesor_se_registra_entra_con_su_documento_y_solo_ve_sus_grupos(self):
        # AC-A08 · RN-20, RN-21, RN-22, RN-23
        r = self.registrar()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["alias"], "Marta Ríos")
        usuario = m.Usuario.objects.get(id=r.json()["id"])
        self.assertEqual((usuario.origen, usuario.estado, usuario.rol.codigo), ("PIN_MAESTRO", "ACTIVO", "TEACHER"))   # activa al instante (PA-02)
        self.assertIsNone(usuario.confirmado_en)
        self.assertIsNone(usuario.creado_por_id)
        self.assertFalse(m.Credencial.objects.get(usuario=usuario, activa=True).debe_cambiar)   # la contraseña es la definitiva, no provisional
        entrada = self.login(NUEVO_DNI, NUEVA_CLAVE)
        self.assertEqual(entrada.status_code, 200, entrada.content)
        self.assertEqual(entrada.json()["usuario"]["rol"], "TEACHER")
        profe = self.con_token(entrada.json()["token"])
        self.assertEqual([g["id"] for g in profe.get("/api/acceso/grupos/").json()], [self.grupo["id"]])
        self.assertEqual(profe.get(f"/api/acceso/grupos/{self.otro_grupo['id']}/").status_code, 403)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.docente.registrado.v1", agregado_id=usuario.id).exists())

    def test_el_registro_sin_grupos_es_valido_y_el_profesor_crea_los_suyos(self):
        # RN-23 y RB-28: sin grupo no ve nada, pero puede crear el suyo y queda como su docente
        r = self.registrar(grupos=[])
        self.assertEqual(r.status_code, 201, r.content)
        profe = self.sesion(NUEVO_DNI, NUEVA_CLAVE)
        self.assertEqual(profe.get("/api/acceso/grupos/").json(), [])
        g = profe.post("/api/acceso/grupos/", {"codigo": "NUEVO", "nombre": "Grupo nuevo", "periodo": "2026"}, format="json")
        self.assertEqual(g.status_code, 201, g.content)
        self.assertEqual([x["papel"] for x in profe.get("/api/acceso/grupos/").json()], ["DOCENTE"])
        self.assertEqual(profe.patch(f"/api/acceso/grupos/{self.grupo['id']}/", {"nombre": "x"}, format="json").status_code, 403)   # los ajenos no

    def test_un_pin_equivocado_no_crea_nada_y_dice_cuantos_intentos_quedan(self):
        antes = m.Usuario.objects.count()
        r = self.registrar(pin_maestro="906531")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["intentos_restantes"]), (401, "pin_maestro_invalido", 4))
        self.assertEqual(r.json()["detail"], "Ese PIN no es. Te quedan 4 intentos.")
        self.assertEqual(m.Usuario.objects.count(), antes)

    def test_la_contrasena_debe_cumplir_la_politica_del_perfil_y_no_deja_cuenta_a_medias(self):
        antes = (m.Usuario.objects.count(), m.Credencial.objects.count(), m.Persona.objects.count())
        r = self.registrar(secreto="corta")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "secreto_debil"))
        self.assertTrue(r.json()["reglas"])
        self.assertEqual((m.Usuario.objects.count(), m.Credencial.objects.count(), m.Persona.objects.count()), antes)
        # el PIN sí se había comprobado: el intento correcto quedó registrado y no pesa como fallo
        self.assertTrue(m.IntentoAcceso.objects.filter(motivo="pin_maestro", resultado="EXITO").exists())

    def test_un_documento_que_ya_existe_se_rechaza_tras_probar_el_pin(self):
        r = self.registrar(documento=self.DOCENTE_DNI)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "identificador_duplicado"))
        # sin el PIN correcto no se revela nada del documento (RN-25)
        r = self.registrar(documento=self.DOCENTE_DNI, pin_maestro="906531")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "pin_maestro_invalido"))

    def test_un_grupo_que_no_existe_se_rechaza(self):
        r = self.registrar(grupos=["no-existe"])
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertFalse(m.IdentificadorUsuario.objects.filter(usuario__origen="PIN_MAESTRO").exists())

    def test_desde_una_tableta_de_alumno_no_se_registra_un_profesor_aunque_el_pin_sea_correcto(self):
        # AC-A07 · RN-11
        r = self.registrar(dispositivo=self.TABLETA)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"))
        self.assertFalse(m.Usuario.objects.filter(origen="PIN_MAESTRO").exists())

    def test_con_el_pin_vencido_no_hay_altas_pero_las_clases_y_los_profesores_siguen(self):
        # AC-A04 · RN-09 · D-A1
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 366 * P.DIA, vence_en=F("vence_en") - 366 * P.DIA)
        r = self.registrar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pin_maestro_vencido"))
        self.assertIn("venció", r.json()["detail"])
        self.assertEqual(self.registrar().status_code, 403)
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento="identidad.pin_maestro.vencido.v1").count(), 1)   # sólo la primera vez
        otra = self.sesion(self.DOCENTE_DNI, self.DOCENTE_PASS)                              # los ya registrados siguen entrando y operando
        self.assertEqual(otra.get("/api/acceso/grupos/").status_code, 200)
        self.assertEqual(self.api.get("/api/acceso/configuracion/").json()["pin_maestro"]["vencido"], True)

    def test_si_la_administracion_apaga_el_registro_de_profesores_se_cierra(self):
        # RN-37
        r = self.admin.put("/api/acceso/politicas/teacher/", {"autoregistro": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.registrar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "registro_cerrado"))
        self.assertFalse(self.api.get("/api/acceso/configuracion/").json()["autoregistro_docentes"])

    def test_sin_pin_maestro_configurado_no_hay_registro(self):
        m.PinMaestro.objects.all().delete()
        r = self.registrar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "pin_maestro_no_configurado"))

    def test_el_pin_no_se_puede_probar_sin_el_documento_ni_sin_la_contrasena(self):
        for faltante in ("documento", "nombres", "secreto", "pin_maestro"):
            cuerpo = self.datos()
            cuerpo.pop(faltante)
            self.assertEqual(self.api.post("/api/acceso/docentes/registro/", cuerpo, format="json").status_code, 400, faltante)


class RestablecerLaContrasenaTests(BaseAcceso):
    def setUp(self):
        super().setUp()
        self.registrar_equipo_master()

    def restablecer(self, **cambios):
        cuerpo = {"pin_maestro": self.PIN_MAESTRO, "documento": self.DOCENTE_DNI, "secreto_nuevo": "Nueva.Clave.2026!", "dispositivo": self.MASTER}
        cuerpo.update(cambios)
        return self.api.post("/api/acceso/docentes/restablecer/", cuerpo, format="json")

    def test_el_profesor_restablece_su_contrasena_se_cierran_sus_sesiones_y_entra_con_la_nueva(self):
        # AC-A09 · RN-24
        abierta = self.docente
        r = self.restablecer()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["sesiones_revocadas"], 1)
        self.assertEqual(abierta.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 401)
        entrada = self.login(self.DOCENTE_DNI, "Nueva.Clave.2026!")
        self.assertEqual(entrada.status_code, 200, entrada.content)
        self.assertFalse(entrada.json()["usuario"]["debe_cambiar_credencial"])          # la eligió ella: es definitiva
        self.assertEqual(m.Sesion.objects.filter(usuario_id=self.docente_id, motivo_revocacion="credencial_restablecida_pin_maestro").count(), 1)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.docente.contrasena_restablecida.v1", agregado_id=self.docente_id).exists())

    def test_queda_auditado_quien_desde_que_equipo_y_cuando(self):
        from audit.models import Bitacora
        self.restablecer()
        asiento = Bitacora.objects.filter(accion="identidad.docente.contrasena_restablecida").get()
        self.assertEqual(asiento.objeto_id, self.docente_id)
        self.assertEqual(asiento.valor_nuevo["dispositivo_id"], m.IntentoAcceso.objects.filter(motivo="credencial_restablecida_pin_maestro").get().dispositivo_id)
        self.assertGreater(asiento.ocurrido_en, 0)

    def test_restablecer_levanta_el_bloqueo_por_intentos_de_la_cuenta(self):
        for _ in range(5):
            self.login(self.DOCENTE_DNI, "mala")
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 423)
        self.assertEqual(self.restablecer().status_code, 200)
        self.assertEqual(self.login(self.DOCENTE_DNI, "Nueva.Clave.2026!").status_code, 200)

    def test_la_contrasena_nueva_debe_cumplir_la_politica_y_no_repetir_las_ultimas(self):
        r = self.restablecer(secreto_nuevo="corta")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "secreto_debil"))
        r = self.restablecer(secreto_nuevo=self.DOCENTE_PASS)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "secreto_debil"))
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 200)   # nada cambió

    def test_una_cuenta_de_administracion_se_rechaza_igual_que_un_documento_inexistente(self):
        # AC-A10 · RN-12 · RN-25
        admin = self.restablecer(documento=self.ADMIN_DNI)
        fantasma = self.restablecer(documento="99.999.999")
        self.assertEqual((admin.status_code, fantasma.status_code), (404, 404))
        self.assertEqual(admin.json(), fantasma.json())                                 # no revela nada
        self.assertEqual(self.login(self.ADMIN_DNI, self.ADMIN_PASS).status_code, 200)

    def test_un_alumno_tampoco_se_restablece_con_el_pin_maestro(self):
        r = self.restablecer(documento=self.ESTUDIANTE_CODIGO)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 200)

    def test_un_profesor_que_ademas_es_administrador_no_se_restablece_con_el_pin(self):
        self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/roles/", {"rol": "ADMIN"}, format="json")
        r = self.restablecer()
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 200)

    def test_con_el_pin_malo_la_respuesta_es_la_misma_exista_o_no_el_documento(self):
        # RN-25
        existe = self.restablecer(pin_maestro="906531")
        no_existe = self.restablecer(pin_maestro="906531", documento="99.999.999")
        self.assertEqual((existe.status_code, no_existe.status_code), (401, 401))
        # la misma respuesta, salvo el contador de intentos (que baja con cada intento, exista o no el documento)
        self.assertEqual({k: v for k, v in existe.json().items() if k not in ("detail", "intentos_restantes")},
                         {k: v for k, v in no_existe.json().items() if k not in ("detail", "intentos_restantes")})

    def test_desde_una_tableta_de_alumno_no_se_restablece(self):
        r = self.restablecer(dispositivo=self.TABLETA)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"))

    def test_con_el_pin_vencido_no_se_restablece(self):
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 400 * P.DIA, vence_en=F("vence_en") - 400 * P.DIA)
        r = self.restablecer()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pin_maestro_vencido"))


class ListaYSuspensionDeDocentesTests(BaseAcceso):
    def setUp(self):
        super().setUp()
        self.registrar_equipo_master(nombre="ops-sala-docentes")
        r = self.api.post("/api/acceso/docentes/registro/", {
            "pin_maestro": self.PIN_MAESTRO, "documento": NUEVO_DNI, "nombres": "Marta", "apellidos": "Ríos", "secreto": NUEVA_CLAVE,
            "grupos": [self.grupo["id"]], "dispositivo": self.MASTER}, format="json")
        self.nuevo_id = r.json()["id"]

    def test_la_administracion_ve_quien_se_registro_con_el_pin_y_desde_que_equipo(self):
        # RN-22 / RB-15
        r = self.admin.get("/api/acceso/docentes/?origen=PIN_MAESTRO")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([d["id"] for d in r.json()], [self.nuevo_id])
        fila = r.json()[0]
        self.assertEqual((fila["alias"], fila["estado"], fila["equipo"], fila["confirmado"]), ("Marta Ríos", "ACTIVO", "ops-sala-docentes", False))
        self.assertEqual([g["id"] for g in fila["grupos"]], [self.grupo["id"]])
        self.assertNotIn(NUEVO_DNI, r.content.decode())                                    # ni documento ni datos personales

    def test_el_profesor_no_ve_la_lista(self):
        self.assertEqual(self.docente.get("/api/acceso/docentes/").status_code, 403)

    def test_la_administracion_puede_suspenderlo_y_deja_de_entrar(self):
        s = self.admin.patch(f"/api/acceso/usuarios/{self.nuevo_id}/", {"estado": "SUSPENDIDO"}, format="json")
        self.assertEqual(s.status_code, 200, s.content)
        self.assertEqual(self.login(NUEVO_DNI, NUEVA_CLAVE).status_code, 401)
        self.assertEqual(self.admin.get("/api/acceso/docentes/").json()[0]["estado"], "SUSPENDIDO")

    def test_la_administracion_confirma_al_profesor(self):
        r = self.admin.post(f"/api/acceso/usuarios/{self.nuevo_id}/confirmar/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(self.admin.get("/api/acceso/docentes/").json()[0]["confirmado"])
