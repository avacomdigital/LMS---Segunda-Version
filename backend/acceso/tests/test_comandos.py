"""
La consola del técnico (RB-21, RB-43, RB-44, PA-07): instalar con el PIN maestro leído del entorno o de la entrada estándar —nunca de un argumento—,
reemplazar el PIN maestro y restablecer la contraseña del administrador. Más el estado del PIN en /health/ (RB-42).
"""
from __future__ import annotations

import io
from unittest import mock

from django.core.management import CommandError, call_command
from django.db.models import F
from django.test import TestCase, override_settings

from acceso import models as m
from acceso.dominio.politicas import PoliticaPinMaestro as P

from .base import ARGON2_RAPIDO, BaseAcceso


def ejecutar(nombre, *args, entrada: str = "", entorno: dict | None = None):
    salida = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(entrada)), mock.patch.dict("os.environ", entorno or {}, clear=False):
        call_command(nombre, *args, stdout=salida)
    return salida.getvalue()


@override_settings(AVACOM_LMS_ARGON2=ARGON2_RAPIDO)
class InstalarPorConsolaTests(TestCase):
    ARGS = ("--codigo", "IE-CONSOLA", "--nombre", "IE Consola", "--admin-dni", "1042888795", "--admin-nombres", "Ana",
            "--admin-password", "Rectoria.2026!")

    def test_sin_pin_maestro_no_se_instala(self):
        with mock.patch.dict("os.environ", {}, clear=False) as entorno:
            entorno.pop("AVACOM_LMS_PIN_MAESTRO", None)
            with self.assertRaises(CommandError) as error:
                ejecutar("acceso_instalar", *self.ARGS)
        self.assertIn("argumento", str(error.exception))
        self.assertFalse(m.Organizacion.objects.exists())

    def test_el_pin_se_lee_de_la_variable_de_entorno_y_no_se_imprime(self):
        salida = ejecutar("acceso_instalar", *self.ARGS, entorno={"AVACOM_LMS_PIN_MAESTRO": "482915"})
        self.assertNotIn("482915", salida)
        self.assertEqual(m.PinMaestro.objects.filter(activa=True).count(), 1)

    def test_el_pin_se_lee_de_la_entrada_estandar(self):
        ejecutar("acceso_instalar", *self.ARGS, "--pin-maestro-stdin", entrada="482915\n")
        self.assertEqual(m.PinMaestro.objects.filter(activa=True).count(), 1)

    def test_el_comando_no_acepta_el_pin_como_argumento(self):
        with self.assertRaises(CommandError):
            ejecutar("acceso_instalar", *self.ARGS, "--pin-maestro", "482915")

    def test_un_pin_trivial_detiene_la_instalacion(self):
        with self.assertRaises(CommandError) as error:
            ejecutar("acceso_instalar", *self.ARGS, entorno={"AVACOM_LMS_PIN_MAESTRO": "123456"})
        self.assertIn("pin_debil", str(error.exception))
        self.assertFalse(m.Organizacion.objects.exists())


class PinMaestroPorConsolaTests(BaseAcceso):
    def test_el_estado_dice_cuanto_queda_sin_mostrar_el_pin(self):
        salida = ejecutar("acceso_pin_maestro")
        self.assertIn("vigente · quedan 365 días", salida)
        self.assertNotIn(self.PIN_MAESTRO, salida)
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 340 * P.DIA, vence_en=F("vence_en") - 340 * P.DIA)
        self.assertIn("por vencer", ejecutar("acceso_pin_maestro"))
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 40 * P.DIA, vence_en=F("vence_en") - 40 * P.DIA)
        self.assertIn("VENCIDO", ejecutar("acceso_pin_maestro"))

    def test_el_tecnico_reemplaza_el_pin_cuando_el_administrador_lo_perdio(self):
        # RN-04: no se recupera, se reemplaza
        salida = ejecutar("acceso_pin_maestro", "--cambiar", entrada="739104\n")
        self.assertIn("reemplazado", salida)
        self.assertNotIn("739104", salida)
        self.assertEqual(m.PinMaestro.objects.count(), 2)
        r = self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro=self.PIN_MAESTRO)
        self.assertEqual(r.json()["codigo"], "pin_maestro_invalido")
        self.assertEqual(self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro="739104").status_code, 200)
        from audit.models import Bitacora
        asiento = Bitacora.objects.filter(accion="identidad.pin_maestro.cambiado").latest("secuencia")
        self.assertEqual((asiento.actor_tipo, asiento.valor_nuevo["motivo"]), ("sistema", "consola"))

    def test_el_pin_nuevo_sigue_las_mismas_reglas(self):
        for malo, codigo in (("111111", "pin_debil"), ("12", "pin_invalido"), (self.PIN_MAESTRO, "pin_debil")):
            with self.assertRaises(CommandError) as error:
                ejecutar("acceso_pin_maestro", "--cambiar", entrada=malo + "\n")
            self.assertIn(codigo, str(error.exception))
        with self.assertRaises(CommandError):
            ejecutar("acceso_pin_maestro", "--cambiar", entrada="")
        self.assertEqual(m.PinMaestro.objects.count(), 1)

    def test_el_pin_nuevo_tambien_puede_venir_del_entorno(self):
        ejecutar("acceso_pin_maestro", "--cambiar", entorno={"AVACOM_LMS_PIN_MAESTRO_NUEVO": "739104"})
        self.assertEqual(self.login(self.ADMIN_DNI, self.ADMIN_PASS, pin_maestro="739104").status_code, 200)


class RestablecerAdministradorPorConsolaTests(BaseAcceso):
    def test_restablece_la_contrasena_del_administrador_queda_provisional_y_cierra_sus_sesiones(self):
        salida = ejecutar("acceso_restablecer_admin", "--dni", self.ADMIN_DNI)
        self.assertEqual(self.admin.get("/api/acceso/yo/").status_code, 401)
        self.assertEqual(self.login(self.ADMIN_DNI, self.ADMIN_PASS).status_code, 401)
        provisional = [linea.split(": ")[-1] for linea in salida.splitlines() if "provisional" in linea][0].strip()
        entrada = self.login(self.ADMIN_DNI, provisional)
        self.assertEqual(entrada.status_code, 200, entrada.content)
        self.assertTrue(entrada.json()["usuario"]["debe_cambiar_credencial"])
        from audit.models import Bitacora
        asiento = Bitacora.objects.filter(accion="identidad.credencial.restablecida", objeto_id=self.admin_id).latest("secuencia")
        self.assertEqual((asiento.actor_tipo, asiento.valor_nuevo["via"]), ("sistema", "consola"))

    def test_la_contrasena_puede_venir_de_la_entrada_estandar(self):
        ejecutar("acceso_restablecer_admin", "--dni", self.ADMIN_DNI, "--secreto-stdin", entrada="Provisional.2026!Aula\n")
        self.assertEqual(self.login(self.ADMIN_DNI, "Provisional.2026!Aula").status_code, 200)

    def test_solo_cuentas_de_administracion(self):
        # un profesor se restablece con el PIN maestro y un alumno con su profesor: esta salida no es para ellos
        for documento in (self.DOCENTE_DNI, self.ESTUDIANTE_CODIGO, "99.999"):
            with self.assertRaises(CommandError):
                ejecutar("acceso_restablecer_admin", "--dni", documento)
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).status_code, 200)


class HealthTests(BaseAcceso):
    def test_health_dice_el_estado_del_pin_maestro_sin_fechas(self):
        # RB-42
        self.assertEqual(self.api.get("/health/").json()["acceso"]["pin_maestro"], "configurado")
        m.PinMaestro.objects.update(creado_en=F("creado_en") - 400 * P.DIA, vence_en=F("vence_en") - 400 * P.DIA)
        self.assertEqual(self.api.get("/health/").json()["acceso"]["pin_maestro"], "vencido")
        m.PinMaestro.objects.all().delete()
        self.assertEqual(self.api.get("/health/").json()["acceso"]["pin_maestro"], "sin_configurar")
