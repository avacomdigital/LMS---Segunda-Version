import contextlib
import io
import json
import unittest

import kiosk_fleet as k


class Politica(unittest.TestCase):
    def test_una_sola_app_con_rol_kiosco(self):
        p = k.construir_politica()
        self.assertEqual(len(p["applications"]), 1)
        app = p["applications"][0]
        self.assertEqual(app["packageName"], "com.avacom.lms.student")
        self.assertEqual(app["roles"], [{"roleType": "KIOSK"}])
        self.assertEqual(app["installType"], "REQUIRED_FOR_SETUP")

    def test_cierra_las_salidas_del_sistema(self):
        c = k.construir_politica()["kioskCustomization"]
        self.assertEqual(c["systemNavigation"], "NAVIGATION_DISABLED")
        self.assertEqual(c["statusBar"], "NOTIFICATIONS_AND_SYSTEM_INFO_DISABLED")
        self.assertEqual(c["deviceSettings"], "SETTINGS_ACCESS_BLOCKED")
        self.assertEqual(c["powerButtonActions"], "POWER_BUTTON_BLOCKED")

    def test_no_deja_abrir_otras_vias(self):
        p = k.construir_politica()
        for campo in ("factoryResetDisabled", "safeBootDisabled", "addUserDisabled", "screenCaptureDisabled"):
            self.assertTrue(p[campo], campo)
        self.assertFalse(p["installUnknownSourcesAllowed"])
        self.assertFalse(p["debuggingFeaturesAllowed"])

    def test_informa_las_apps_instaladas(self):
        self.assertTrue(k.construir_politica()["statusReportingSettings"]["applicationReportsEnabled"])

    def test_ventana_de_actualizacion(self):
        p = k.construir_politica(ventana_actualizacion=(60, 180))
        self.assertEqual(p["systemUpdate"], {"type": "WINDOWED", "startMinutes": 60, "endMinutes": 180})
        self.assertNotIn("systemUpdate", k.construir_politica(ventana_actualizacion=None))

    def test_ventana_invalida(self):
        for mala in ((100, 100), (-1, 50), (0, 1440)):
            with self.assertRaises(ValueError):
                k.construir_politica(ventana_actualizacion=mala)

    def test_es_serializable_y_no_comparte_estado(self):
        a = k.construir_politica()
        json.dumps(a)
        a["applications"].clear()
        self.assertEqual(len(k.construir_politica()["applications"]), 1)


class Token(unittest.TestCase):
    def test_duraciones(self):
        self.assertEqual(k.duracion_segundos("7d"), "604800s")
        self.assertEqual(k.duracion_segundos("90m"), "5400s")
        self.assertEqual(k.duracion_segundos("1m"), "60s")

    def test_duraciones_invalidas(self):
        for mala in ("", "7", "d", "30s", "-1h", "1.5h", "7 dias"):
            with self.assertRaises(ValueError, msg=mala):
                k.duracion_segundos(mala)

    def test_qr_agrega_wifi_sin_perder_lo_de_google(self):
        google = json.dumps({"android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": "x/y", "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {"t": "1"}})
        qr = k.armar_qr(google, ssid="Aula", clave_wifi="secreta")
        self.assertEqual(qr["android.app.extra.PROVISIONING_WIFI_SSID"], "Aula")
        self.assertEqual(qr["android.app.extra.PROVISIONING_WIFI_PASSWORD"], "secreta")
        self.assertEqual(qr["android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"], "x/y")

    def test_qr_sin_wifi_queda_igual(self):
        google = json.dumps({"a": 1})
        self.assertEqual(k.armar_qr(google), {"a": 1})

    def test_zero_touch(self):
        e = k.extras_zero_touch("TOKEN123")
        self.assertEqual(e[k.EXTRA_ADMIN][k.CLAVE_TOKEN_ZERO_TOUCH], "TOKEN123")


def dispositivo(**cambios):
    d = {"name": "enterprises/E/devices/1", "state": "ACTIVE", "policyCompliant": True,
         "softwareInfo": {"androidVersion": "14"}, "hardwareInfo": {"serialNumber": "S1", "model": "Tab"},
         "applicationReports": [{"packageName": k.PAQUETE_STUDENT, "state": "INSTALLED", "versionName": "2.16.0"}]}
    d.update(cambios)
    return d


class Flota(unittest.TestCase):
    def test_lista(self):
        r = k.resumir_flota([dispositivo()])
        self.assertEqual((r["total"], r["listas"], r["no_listas"]), (1, 1, 0))
        self.assertEqual(r["dispositivos"][0]["version_app"], "2.16.0")

    def test_cada_motivo(self):
        casos = {
            "estado": dispositivo(state="DISABLED"),
            "política": dispositivo(policyCompliant=False),
            "Android 13": dispositivo(softwareInfo={"androidVersion": "13"}),
            "no está instalada": dispositivo(applicationReports=[]),
            "app": dispositivo(applicationReports=[{"packageName": k.PAQUETE_STUDENT, "state": "INSTALL_FAILED"}]),
        }
        for esperado, d in casos.items():
            r = k.resumir_flota([d])
            self.assertEqual(r["listas"], 0, esperado)
            self.assertTrue(any(esperado in m for m in r["dispositivos"][0]["motivos"]), (esperado, r["dispositivos"][0]["motivos"]))

    def test_sin_informe_de_version_no_cuenta_como_lista(self):
        self.assertEqual(k.resumir_flota([dispositivo(softwareInfo={})])["listas"], 0)

    def test_android_15_pasa(self):
        self.assertEqual(k.resumir_flota([dispositivo(softwareInfo={"androidVersion": "15"})])["listas"], 1)

    def test_flota_vacia(self):
        self.assertEqual(k.resumir_flota([])["total"], 0)


class DryRun(unittest.TestCase):
    def correr(self, *argv):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = k.main(["--dry-run", *argv])
        return codigo, salida.getvalue()

    def test_todos_los_subcomandos_sin_llamar_a_google(self):
        for argv in (["signup-url", "--project", "p", "--callback", "https://x"],
                     ["create-enterprise", "--project", "p", "--signup-url-name", "s", "--enterprise-token", "t", "--name", "n"],
                     ["apply-policy", "--enterprise", "LC1"],
                     ["enrollment-token", "--enterprise", "LC1", "--wifi-ssid", "Aula"],
                     ["devices", "--enterprise", "LC1"]):
            codigo, texto = self.correr(*argv)
            self.assertEqual(codigo, 0, argv)
            self.assertIn("[DRY-RUN]", texto)

    def test_el_dry_run_no_muestra_la_clave_wifi(self):
        import os
        os.environ[k.VARIABLE_CLAVE_WIFI] = "claveultrasecreta"
        try:
            _, texto = self.correr("enrollment-token", "--enterprise", "LC1", "--wifi-ssid", "Aula")
        finally:
            del os.environ[k.VARIABLE_CLAVE_WIFI]
        self.assertNotIn("claveultrasecreta", texto)

    def test_duracion_mala_da_codigo_2(self):
        codigo, _ = self.correr("enrollment-token", "--enterprise", "LC1", "--duration", "5s")
        self.assertEqual(codigo, 2)

    def test_la_politica_impresa_lleva_el_rol_kiosco(self):
        _, texto = self.correr("apply-policy", "--enterprise", "enterprises/LC1")
        self.assertIn("PATCH https://androidmanagement.googleapis.com/v1/enterprises/LC1/policies/aula-examen", texto)
        self.assertIn('"roleType": "KIOSK"', texto)


ONC = {"Type": "UnencryptedConfiguration", "NetworkConfigurations": [
    {"GUID": "aula", "Name": "Aula", "Type": "WiFi",
     "WiFi": {"SSID": "Aula", "Security": "WPA-PSK", "Passphrase": "claveultrasecreta", "AutoConnect": True}}]}


class WifiPorPolitica(unittest.TestCase):
    def test_la_politica_lleva_la_red(self):
        self.assertEqual(k.construir_politica(wifi=ONC)["openNetworkConfiguration"], ONC)

    def test_sin_wifi_no_hay_clave(self):
        self.assertNotIn("openNetworkConfiguration", k.construir_politica())

    def test_rechaza_lo_mal_formado(self):
        import copy
        malos = []
        for cambio in (lambda o: o.pop("NetworkConfigurations"),
                       lambda o: o["NetworkConfigurations"].clear(),
                       lambda o: o["NetworkConfigurations"][0].update(Type="Ethernet"),
                       lambda o: o["NetworkConfigurations"][0].pop("GUID"),
                       lambda o: o["NetworkConfigurations"][0]["WiFi"].pop("SSID"),
                       lambda o: o["NetworkConfigurations"][0]["WiFi"].update(Security="WPA3"),
                       lambda o: o["NetworkConfigurations"][0]["WiFi"].pop("Passphrase")):
            o = copy.deepcopy(ONC)
            cambio(o)
            malos.append(o)
        for o in malos:
            with self.assertRaises(ValueError):
                k.validar_wifi(o)
        with self.assertRaises(ValueError):
            k.validar_wifi([])

    def test_red_abierta_no_pide_clave(self):
        abierta = {"NetworkConfigurations": [{"GUID": "a", "Name": "A", "Type": "WiFi", "WiFi": {"SSID": "A", "Security": "None"}}]}
        self.assertEqual(k.validar_wifi(abierta), abierta)

    def test_ocultar_secretos_no_toca_el_original(self):
        oculto = k.ocultar_secretos(k.construir_politica(wifi=ONC))
        self.assertNotIn("claveultrasecreta", json.dumps(oculto))
        self.assertEqual(ONC["NetworkConfigurations"][0]["WiFi"]["Passphrase"], "claveultrasecreta")

    def test_dry_run_con_wifi_json_no_imprime_la_clave(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "wifi.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(ONC, f)
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                codigo = k.main(["--dry-run", "apply-policy", "--enterprise", "LC1", "--wifi-json", ruta])
        self.assertEqual(codigo, 0)
        self.assertIn("openNetworkConfiguration", salida.getvalue())
        self.assertNotIn("claveultrasecreta", salida.getvalue())

    def test_wifi_json_inexistente_o_invalido_da_codigo_2(self):
        import os, tempfile
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(k.main(["--dry-run", "apply-policy", "--enterprise", "LC1", "--wifi-json", "no-existe.json"]), 2)
            with tempfile.TemporaryDirectory() as d:
                ruta = os.path.join(d, "x.json")
                open(ruta, "w").write("{}")
                self.assertEqual(k.main(["--dry-run", "apply-policy", "--enterprise", "LC1", "--wifi-json", ruta]), 2)


if __name__ == "__main__":
    unittest.main()
