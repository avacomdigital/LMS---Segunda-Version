"""
El PIN maestro (RN-01…RN-12 de los requisitos de acceso, 2026-10-05): formato y trivialidad, vigencia de 365 días con aviso a los 30,
bloqueo contra la adivinación por equipo y global, cambio por el administrador, la exigencia extra a la administración al entrar y que
nunca quede escrito en claro. Las reglas puras se prueban sin base de datos (`PoliticaPinMaestro`); el resto, por la API.
"""
from __future__ import annotations

import json

from django.db.models import F
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from acceso import models as m
from acceso.dominio import errores
from acceso.dominio.entidades import IntentoAcceso
from acceso.dominio.politicas import PoliticaPinMaestro as P
from acceso.dominio.valores import ResultadoIntento

from .base import ARGON2_RAPIDO, BaseAcceso

MIN, DIA = P.MINUTO, P.DIA
AHORA = 1_800_000_000_000


def fallo(momento, resultado=ResultadoIntento.FALLO):
    return IntentoAcceso("", resultado, "pin_maestro", momento)


def historial(*momentos, resultado=ResultadoIntento.FALLO):
    """Del más reciente al más antiguo, como los entrega el repositorio."""
    return [fallo(t, resultado) for t in sorted(momentos, reverse=True)]


class ReglasDelPinTests(SimpleTestCase):
    def test_formato_seis_digitos_exactos(self):
        self.assertEqual(P.validar_formato(" 482915 "), "482915")
        for malo in ("12345", "1234567", "48291a", "48 915", "", None, "٤٨٢٩١٥"):   # incluye dígitos arábigos: sólo ASCII
            with self.assertRaises(errores.PinInvalido, msg=repr(malo)):
                P.validar_formato(malo)

    def test_pines_triviales_se_rechazan_con_explicacion(self):
        # RN-05 / AC-A02
        for trivial in ("111111", "123456", "654321", "121212", "123123", "987654", "000000"):
            self.assertTrue(P.es_trivial(trivial), trivial)
            with self.assertRaises(errores.PinDebil):
                P.exigir_fuerte(trivial)
        for bueno in ("482915", "135792", "708316"):
            self.assertFalse(P.es_trivial(bueno), bueno)
            self.assertEqual(P.exigir_fuerte(bueno), bueno)

    def test_vigencia_de_365_dias_y_aviso_a_los_30(self):
        # RN-07, RN-08, RN-09 / AC-A04, AC-A05
        creado = AHORA
        vence = P.vence_en(creado)
        self.assertEqual(vence - creado, 365 * DIA)
        self.assertFalse(P.esta_vencido(vence, vence - 1))
        self.assertTrue(P.esta_vencido(vence, vence))                       # el día 366 ya no vale
        self.assertTrue(P.esta_vencido(vence, creado + 366 * DIA))
        self.assertEqual(P.dias_restantes(vence, creado), 365)
        self.assertEqual(P.dias_restantes(vence, vence + 5 * DIA), 0)
        self.assertFalse(P.en_aviso(vence, vence - 31 * DIA))               # 31 días restantes: nada
        self.assertTrue(P.en_aviso(vence, vence - 30 * DIA))                # 30 o menos: aviso
        self.assertTrue(P.en_aviso(vence, vence - DIA))

    def test_cinco_fallos_en_quince_minutos_bloquean_quince_minutos(self):
        # RN-10 / AC-A06
        cuatro = historial(AHORA, AHORA + MIN, AHORA + 2 * MIN, AHORA + 3 * MIN)
        estado = P.evaluar_bloqueo_equipo(cuatro, AHORA + 3 * MIN)
        self.assertFalse(estado.bloqueado)
        self.assertEqual(estado.fallos, 4)
        cinco = historial(AHORA, AHORA + MIN, AHORA + 2 * MIN, AHORA + 3 * MIN, AHORA + 4 * MIN)
        estado = P.evaluar_bloqueo_equipo(cinco, AHORA + 4 * MIN)
        self.assertTrue(estado.bloqueado)
        self.assertEqual(estado.hasta, AHORA + 4 * MIN + 15 * MIN)
        self.assertEqual(estado.segundos_restantes(AHORA + 4 * MIN), 15 * 60)
        self.assertFalse(P.evaluar_bloqueo_equipo(cinco, AHORA + 4 * MIN + 15 * MIN).bloqueado)   # pasado el castigo, se puede volver a intentar

    def test_fallos_espaciados_no_bloquean_y_un_acierto_borra_la_cuenta(self):
        espaciados = historial(*(AHORA + i * 10 * MIN for i in range(6)))   # uno cada 10 min: nunca 5 dentro de 15
        self.assertFalse(P.evaluar_bloqueo_equipo(espaciados, AHORA + 50 * MIN).bloqueado)
        # cuatro fallos, un acierto y otro fallo (del más reciente al más antiguo): sólo cuenta el último
        con_acierto = [fallo(AHORA + 4 * MIN), fallo(AHORA + 3 * MIN + 1, ResultadoIntento.EXITO)] + historial(AHORA, AHORA + MIN, AHORA + 2 * MIN, AHORA + 3 * MIN)
        estado = P.evaluar_bloqueo_equipo(con_acierto, AHORA + 4 * MIN)
        self.assertEqual((estado.bloqueado, estado.fallos), (False, 1))

    def test_tres_bloqueos_seguidos_suben_el_castigo_a_sesenta_minutos(self):
        # RN-10: «tras tres bloqueos seguidos el bloqueo sube a 60 minutos y se avisa al administrador»
        momentos, t = [], AHORA
        for episodio in range(3):
            momentos += [t + i * MIN for i in range(5)]
            t = t + 4 * MIN + 16 * MIN                                      # sale del castigo de 15 min y vuelve a probar
        estado = P.evaluar_bloqueo_equipo(historial(*momentos), momentos[-1])
        self.assertTrue(estado.bloqueado)
        self.assertEqual(estado.episodios, 3)
        self.assertEqual(estado.hasta, momentos[-1] + 60 * MIN)
        dos = P.evaluar_bloqueo_equipo(historial(*momentos[:10]), momentos[9])
        self.assertEqual((dos.episodios, dos.hasta), (2, momentos[9] + 15 * MIN))

    def test_tope_global_de_veinte_fallos_por_hora(self):
        fallos = sorted((AHORA + i * MIN for i in range(20)), reverse=True)
        estado = P.evaluar_bloqueo_global(fallos, AHORA + 20 * MIN)
        self.assertTrue(estado.bloqueado and estado.global_)
        self.assertEqual(estado.hasta, min(fallos) + 60 * MIN)              # se libera cuando el fallo número 20 cumple su hora
        self.assertFalse(P.evaluar_bloqueo_global(fallos[:19], AHORA + 20 * MIN).bloqueado)
        self.assertFalse(P.evaluar_bloqueo_global(fallos, AHORA + 61 * MIN).bloqueado)


@override_settings(AVACOM_LMS_ARGON2=ARGON2_RAPIDO)
class InstalacionConPinMaestroTests(TestCase):
    def instalar(self, **extra):
        return APIClient().post("/api/acceso/instalacion/", {
            "organizacion": {"codigo": "IE-NUEVA", "nombre": "IE Nueva"},
            "administrador": {"nombres": "Ana", "dni": "1042888795", "password": "Rectoria.2026!"}, **extra}, format="json")

    def test_sin_pin_maestro_no_se_instala(self):
        # RN-03 / AC-A01
        self.assertEqual(self.instalar().status_code, 400)
        self.assertEqual(self.instalar(pin_maestro="").status_code, 400)
        self.assertFalse(m.Organizacion.objects.exists())

    def test_un_pin_trivial_o_mal_formado_deja_el_equipo_vacio_y_explica_por_que(self):
        # AC-A02
        r = self.instalar(pin_maestro="123456")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_debil"))
        self.assertIn("fácil de adivinar", r.json()["detail"])
        r = self.instalar(pin_maestro="12345")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_invalido"))
        self.assertFalse(m.Organizacion.objects.exists())
        self.assertFalse(m.Usuario.objects.exists())
        self.assertFalse(m.PinMaestro.objects.exists())

    def test_con_pin_valido_nace_la_version_uno_y_la_respuesta_no_lo_devuelve(self):
        r = self.instalar(pin_maestro="482915")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn("482915", r.content.decode())
        version = m.PinMaestro.objects.get()
        self.assertTrue(version.activa)
        self.assertIsNone(version.creado_por_id)                            # nadie lo creó: es el primer arranque
        self.assertEqual(version.vence_en - version.creado_en, 365 * DIA)
        self.assertTrue(version.hash.startswith("$argon2id$"))
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.pin_maestro.configurado.v1").exists())
        config = APIClient().get("/api/acceso/configuracion/").json()
        self.assertEqual(config["pin_maestro"], {"configurado": True, "vencido": False, "por_vencer": False})
        self.assertEqual((config["autoregistro_alumnos"], config["autoregistro_docentes"], config["visitante"]), (True, True, True))
        self.assertEqual(m.Usuario.objects.get().origen, "INSTALACION")


class EstadoYCambioDelPinTests(BaseAcceso):
    def version_activa(self):
        return m.PinMaestro.objects.get(activa=True)

    def test_el_administrador_consulta_el_estado_sin_ver_el_pin_ni_su_huella(self):
        # RB-12
        r = self.admin.get("/api/acceso/pin-maestro/")
        self.assertEqual(r.status_code, 200, r.content)
        e = r.json()
        self.assertEqual((e["configurado"], e["vencido"], e["aviso"], e["dias_restantes"], e["bloqueado_hasta"]), (True, False, False, 365, None))
        texto = r.content.decode()
        self.assertNotIn(self.PIN_MAESTRO, texto)
        self.assertNotIn("argon2", texto)
        self.assertNotIn("hash", texto)

    def test_nadie_mas_consulta_ni_cambia_el_pin(self):
        # RB-08: sólo ADMIN tiene `identity.master_pin.manage`; el profesor y el alumno no
        for sesion in (self.docente, self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)):
            self.assertEqual(sesion.get("/api/acceso/pin-maestro/").status_code, 403)
            self.assertEqual(sesion.put("/api/acceso/pin-maestro/", {"pin_nuevo": "739104"}, format="json").status_code, 403)
        self.assertEqual(self.api.get("/api/acceso/pin-maestro/").status_code, 401)

    def test_el_administrador_lo_cambia_cuando_quiera_sin_saber_el_actual_y_el_reloj_reinicia(self):
        # RN-06, RN-07
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 200 * DIA, vence_en=F("vence_en") - 200 * DIA)
        self.assertEqual(self.admin.get("/api/acceso/pin-maestro/").json()["dias_restantes"], 165)
        r = self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "739104"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.admin.get("/api/acceso/pin-maestro/").json()["dias_restantes"], 365)
        self.assertEqual(m.PinMaestro.objects.count(), 2)                   # la anterior se conserva (CV-05)
        self.assertEqual(m.PinMaestro.objects.filter(activa=True).count(), 1)
        vieja = m.PinMaestro.objects.get(activa=False)
        self.assertIsNotNone(vieja.sustituida_en)
        self.assertEqual(self.version_activa().creado_por_id, self.admin_id)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.pin_maestro.cambiado.v1").exists())

    def test_el_pin_nuevo_debe_ser_de_seis_digitos_no_trivial_y_no_uno_de_los_tres_ultimos(self):
        # RN-02, RN-05
        r = self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "12345"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_invalido"))
        r = self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "abcdef"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_invalido"))
        r = self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "111111"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_debil"))
        r = self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": self.PIN_MAESTRO}, format="json")   # el vigente cuenta como usado
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_debil"))
        self.assertEqual(self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "739104"}, format="json").status_code, 200)
        self.assertEqual(self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "846205"}, format="json").status_code, 200)
        r = self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": self.PIN_MAESTRO}, format="json")   # hace dos cambios: aún entre los tres últimos
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_debil"))
        self.assertEqual(self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "590218"}, format="json").status_code, 200)
        self.assertEqual(self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": self.PIN_MAESTRO}, format="json").status_code, 200)   # ya salió

    def test_el_aviso_aparece_a_los_30_dias_y_no_antes(self):
        # AC-A05 / RN-08
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 334 * DIA, vence_en=F("vence_en") - 334 * DIA)   # quedan 31 días
        self.assertFalse(self.admin.get("/api/acceso/pin-maestro/").json()["aviso"])
        self.assertFalse(self.api.get("/api/acceso/configuracion/").json()["pin_maestro"]["por_vencer"])
        m.PinMaestro.objects.update(creado_en=F("creado_en") - DIA, vence_en=F("vence_en") - DIA)               # quedan 30
        self.assertTrue(self.admin.get("/api/acceso/pin-maestro/").json()["aviso"])
        self.assertTrue(self.api.get("/api/acceso/configuracion/").json()["pin_maestro"]["por_vencer"])

    def test_nada_queda_escrito_en_claro_ni_vigente_ni_intentado(self):
        # AC-A22: ni la base, ni la cola de eventos, ni la bitácora
        self.admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "739104"}, format="json")
        self.registrar_equipo_master()
        for _ in range(2):
            self.api.post("/api/acceso/docentes/restablecer/", {"pin_maestro": "906531", "documento": self.DOCENTE_DNI,
                                                                "secreto_nuevo": "Otra.Clave.2026!", "dispositivo": self.MASTER}, format="json")
        from audit.models import Bitacora, EventoSalida as EventoAuditoria
        rastros = [json.dumps(list(m.EventoSalida.objects.values_list("carga", flat=True))),
                   json.dumps(list(Bitacora.objects.values_list("valor_nuevo", "valor_anterior", "motivo", "objeto_id"))),
                   json.dumps(list(EventoAuditoria.objects.values_list("carga", flat=True))),
                   json.dumps(list(m.IntentoAcceso.objects.values_list("identificador_hmac", "motivo")))]
        for pin in (self.PIN_MAESTRO, "739104", "906531"):
            for rastro in rastros:
                self.assertNotIn(pin, rastro)
        for version in m.PinMaestro.objects.all():
            self.assertTrue(version.hash.startswith("$argon2id$"))


class LaAdministracionEntraConElPinTests(BaseAcceso):
    def test_la_administracion_pide_ademas_el_pin_maestro_y_lo_dice_despues_de_la_contrasena(self):
        # La contraseña es correcta: sólo entonces se dice que falta el PIN.
        r = self.api.post("/api/acceso/sesiones/", {"identificador": self.ADMIN_DNI, "secreto": self.ADMIN_PASS}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "pin_maestro_requerido"))
        # Con la contraseña mal no se revela que es una cuenta de administración.
        r = self.api.post("/api/acceso/sesiones/", {"identificador": self.ADMIN_DNI, "secreto": "mala"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "credenciales_invalidas"))
        r = self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro="906531")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["intentos_restantes"]), (401, "pin_maestro_invalido", 4))
        self.assertEqual(self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro=self.PIN_MAESTRO).status_code, 200)

    def test_el_profesor_y_el_alumno_no_piden_pin_maestro(self):
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 200)
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 200)

    def test_un_pin_maestro_vencido_no_se_exige_para_que_el_administrador_pueda_reemplazarlo(self):
        # RN-09: sin esto, un PIN vencido dejaría a la administración fuera de la única pantalla que lo cambia
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 400 * DIA, vence_en=F("vence_en") - 400 * DIA)
        r = self.api.post("/api/acceso/sesiones/", {"identificador": self.ADMIN_DNI, "secreto": self.ADMIN_PASS}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        admin = self.con_token(r.json()["token"])
        self.assertTrue(admin.get("/api/acceso/pin-maestro/").json()["vencido"])
        self.assertEqual(admin.put("/api/acceso/pin-maestro/", {"pin_nuevo": "739104"}, format="json").status_code, 200)
        r = self.api.post("/api/acceso/sesiones/", {"identificador": self.ADMIN_DNI, "secreto": self.ADMIN_PASS}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "pin_maestro_requerido"))   # con el PIN nuevo vuelve a exigirse

    def test_el_pin_de_la_administracion_tambien_se_bloquea_por_equipo(self):
        for _ in range(5):
            self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro="906531")
        r = self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro=self.PIN_MAESTRO)
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "pin_maestro_bloqueado"))
        self.assertGreater(r.json()["reintentar_en_seg"], 800)
        # la cuenta no se bloquea por esto: el profesor sigue entrando
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 200)

    def test_la_administracion_no_entra_con_el_pin_desde_una_tableta_de_alumno(self):
        r = self.login(self.ADMIN_DNI, self.ADMIN_PASS, dispositivo=self.TABLETA, pin_maestro=self.PIN_MAESTRO)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"))


class BloqueoDelPinPorEquipoTests(BaseAcceso):
    """RN-10 y RN-11 con una operación real: restablecer la contraseña de un profesor."""

    def setUp(self):
        super().setUp()
        self.registrar_equipo_master()
        self.registrar_equipo_master("ops-master-2", "ops-master-2")

    def restablecer(self, pin, equipo=None):
        self.n = getattr(self, "n", 0) + 1       # una contraseña distinta cada vez: no se reutilizan las últimas
        return self.api.post("/api/acceso/docentes/restablecer/", {
            "pin_maestro": pin, "documento": self.DOCENTE_DNI, "secreto_nuevo": f"Nueva.Clave.{2026 + self.n}!",
            "dispositivo": equipo or self.MASTER}, format="json")

    def test_cinco_fallos_bloquean_el_equipo_aunque_despues_llegue_el_pin_correcto(self):
        # AC-A06
        for quedan in (4, 3, 2, 1):
            r = self.restablecer("906531")
            self.assertEqual((r.status_code, r.json()["codigo"], r.json()["intentos_restantes"]), (401, "pin_maestro_invalido", quedan))
        r = self.restablecer("906531")
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "pin_maestro_bloqueado"))
        r = self.restablecer(self.PIN_MAESTRO)
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "pin_maestro_bloqueado"))
        self.assertLessEqual(r.json()["reintentar_en_seg"], 15 * 60)
        self.assertGreater(r.json()["reintentar_en_seg"], 14 * 60)
        # queda auditado: cada fallo y el bloqueo, con equipo y hora, nunca el PIN intentado
        self.assertEqual(m.IntentoAcceso.objects.filter(motivo="pin_maestro", resultado="FALLO").count(), 5)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.pin_maestro.bloqueado.v1").exists())
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento="identidad.pin_maestro.fallido.v1").count(), 5)
        # otro equipo no está bloqueado: el castigo es por equipo
        self.assertEqual(self.restablecer(self.PIN_MAESTRO, "ops-master-2").status_code, 200)
        # pasados 15 minutos el primero vuelve a poder intentar
        m.IntentoAcceso.objects.update(momento=F("momento") - 16 * MIN)
        self.assertEqual(self.restablecer(self.PIN_MAESTRO).status_code, 200)

    def test_un_acierto_borra_la_cuenta_de_fallos(self):
        for _ in range(4):
            self.restablecer("906531")
        self.assertEqual(self.restablecer(self.PIN_MAESTRO).status_code, 200)
        r = self.restablecer("906531")
        self.assertEqual(r.json()["intentos_restantes"], 4)

    def test_tres_bloqueos_seguidos_avisan_a_la_administracion_y_suben_a_una_hora(self):
        for episodio in range(3):
            for _ in range(5):
                self.restablecer("906531")
            m.IntentoAcceso.objects.update(momento=F("momento") - 16 * MIN)   # sale del castigo y sigue probando
        # en el tercer episodio el castigo fue de 60 min; los registros se corrieron 16 min hacia atrás: quedan 44
        r = self.restablecer(self.PIN_MAESTRO)
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "pin_maestro_bloqueado"))
        self.assertGreater(r.json()["reintentar_en_seg"], 40 * 60)
        avisos = [e.carga for e in m.EventoSalida.objects.filter(tipo_evento="identidad.pin_maestro.bloqueado.v1").order_by("id")]
        self.assertEqual([a["avisar_administrador"] for a in avisos], [False, False, True])

    def test_el_tope_global_de_veinte_fallos_por_hora_bloquea_a_todos_los_equipos(self):
        for i in range(4):
            self.registrar_equipo_master(f"ops-extra-{i}", f"extra-{i}")
        for i in range(4):
            for _ in range(5):
                self.restablecer("906531", f"ops-extra-{i}")
        r = self.restablecer(self.PIN_MAESTRO, "ops-master-2")      # un equipo que nunca falló
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "pin_maestro_bloqueado"))

    def test_desde_una_tableta_de_alumno_no_se_acepta_ni_con_el_pin_correcto(self):
        # RN-11 / AC-A07
        r = self.restablecer(self.PIN_MAESTRO, self.TABLETA)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"))
        self.assertEqual(r.json()["detail"], "Esto se hace desde el equipo del profesor.")
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 200)   # la contraseña no cambió

    def test_el_pin_mal_formado_no_gasta_un_intento(self):
        antes = m.IntentoAcceso.objects.filter(motivo="pin_maestro").count()
        r = self.restablecer("12345")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "pin_invalido"))
        self.assertEqual(m.IntentoAcceso.objects.filter(motivo="pin_maestro").count(), antes)

    def test_sin_version_activa_se_dice_que_no_esta_configurado(self):
        m.PinMaestro.objects.all().delete()
        r = self.restablecer(self.PIN_MAESTRO)
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "pin_maestro_no_configurado"))
