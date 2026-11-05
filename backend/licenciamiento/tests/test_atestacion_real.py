"""
La atestación REAL (Fase 5, P-24): dos cadenas capturadas de un emulador Android (Android 17, API 37, x86_64) con el APK de Student, la prueba de posesión firmada por el Keystore de Java y lo que el
nodo hace con ellas — con las raíces de Google de verdad, con la raíz del emulador clavada y con la cadena ALTERADA.

Qué NO prueba: una tableta física. La clave de un emulador vive en software (nivel `Software`, arranque `Unverified`, gestor abierto) y su raíz es «Droid Unregistered Device CA», no una de Google: así
que aquí el resultado correcto es siempre `software`. Cómo se capturaron: `spec-driven/15-licenciamiento/08-identidad-de-dispositivo.md` §6.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from django.test import SimpleTestCase

from licenciamiento.dominio import atestacion as at
from licenciamiento.infraestructura.identidad import AtestacionEmpaquetada

CARPETA = Path(__file__).resolve().parent / "fixtures" / "atestacion"
AHORA = int(__import__("datetime").datetime(2026, 10, 22, 18, 0, tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
APP_DEL_EMULADOR = at.PoliticaDeApp(frozenset({"com.avacom.lms.student"}), frozenset({bytes.fromhex("52e975525eb071b8249759602228ce26fa8ab3fe80848a62f76b3ad7cfedb536")}))


def cargar(nombre: str) -> dict:
    d = json.loads((CARPETA / f"{nombre}.json").read_text(encoding="utf-8"))
    return {**d, "nonce": bytes.fromhex(d["nonce_hex"]), "spki": base64.b64decode(d["clave_publica"]), "firma_der": base64.b64decode(d["firma"]),
            "certs": [base64.b64decode(c) for c in d["cadena"]]}


def raiz_del_emulador(certs: list[bytes]) -> at.Raiz:
    c = x509.load_der_x509_certificate(certs[-1])
    return at.Raiz("emulador", c.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo), 0, 2**62)


class CadenasRealesTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b = cargar("emulador_1"), cargar("emulador_2")
        cls.google = AtestacionEmpaquetada()

    def ev(self, c, **kw):
        datos = dict(spki_declarada=c["spki"], nonce=c["nonce"], cadena_der=c["certs"], ahora_ms=AHORA, raices=self.google.raices(), revocadas=self.google.revocadas(), app=APP_DEL_EMULADOR)
        datos.update(kw)
        return at.evaluar(**datos)

    def test_la_firma_del_keystore_de_java_se_verifica_con_python(self):
        for c in (self.a, self.b):
            self.assertTrue(at.verificar_posesion(c["spki"], c["firma_der"], c["nonce"], c["hw"]), c["hw"])

    def test_la_firma_de_una_tableta_no_vale_para_otra_ni_para_otro_reto(self):
        a, b = self.a, self.b
        self.assertFalse(at.verificar_posesion(a["spki"], a["firma_der"], a["nonce"], b["hw"]))
        self.assertFalse(at.verificar_posesion(a["spki"], a["firma_der"], b["nonce"], a["hw"]))
        self.assertFalse(at.verificar_posesion(b["spki"], a["firma_der"], a["nonce"], a["hw"]))

    def test_las_dos_cadenas_son_de_claves_distintas_y_traen_su_reto(self):
        self.assertNotEqual(self.a["spki"], self.b["spki"])
        for c in (self.a, self.b):
            hoja = x509.load_der_x509_certificate(c["certs"][0])
            ext = [e for e in hoja.extensions if e.oid == at.OID_ATESTACION][0].value.value
            d = at.leer_descripcion(ext)
            self.assertEqual(d.reto, c["nonce"])
            self.assertEqual((d.nivel_atestacion, d.nivel_llave), (at.NIVEL_SOFTWARE, at.NIVEL_SOFTWARE))        # la clave de un emulador vive en software
            self.assertEqual((d.arranque, d.bloqueado), (at.ARRANQUE_NO_VERIFICADO, False))                      # y su arranque no está verificado
            self.assertEqual(d.paquetes, ("com.avacom.lms.student",))
            self.assertEqual(len(d.firmas_app), 1)

    def test_con_las_raices_de_google_el_emulador_no_da_hardware(self):
        for c in (self.a, self.b):
            r = self.ev(c)
            self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_RAIZ_DESCONOCIDA), c["hw"])

    def test_con_la_raiz_del_emulador_clavada_el_resto_de_la_cadena_se_lee_y_la_clave_en_software_no_da_hardware(self):
        for c in (self.a, self.b):
            r = self.ev(c, raices=[raiz_del_emulador(c["certs"])])
            self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_NIVEL_SOFTWARE), c["hw"])
            self.assertEqual((r.detalle["nivel"], r.detalle["arranque"], r.detalle["gestor_cerrado"]), ("software", "no_verificado", False))

    def test_el_reto_de_otra_activacion_se_detecta_con_la_cadena_real(self):
        r = self.ev(self.a, raices=[raiz_del_emulador(self.a["certs"])], nonce=self.b["nonce"])
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_RETO_DISTINTO))

    def test_la_cadena_de_una_tableta_con_la_clave_de_otra_no_pasa(self):
        r = self.ev(self.a, raices=[raiz_del_emulador(self.a["certs"])], spki_declarada=self.b["spki"])
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_CLAVE_DISTINTA))

    def test_mezclar_hoja_de_una_con_intermedia_de_otra_no_pasa(self):
        mezclada = [self.a["certs"][0], self.b["certs"][1], self.b["certs"][2]]
        r = self.ev(self.a, cadena_der=mezclada, raices=[raiz_del_emulador(self.b["certs"])])
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_CADENA_INVALIDA))

    def test_un_byte_cambiado_en_cualquier_certificado_rompe_la_cadena(self):
        raices = [raiz_del_emulador(self.a["certs"])]
        for i in range(len(self.a["certs"])):
            alterada = [bytes(c) for c in self.a["certs"]]
            c = bytearray(alterada[i])
            c[len(c) // 2] ^= 0x01
            alterada[i] = bytes(c)
            r = self.ev(self.a, cadena_der=alterada, raices=raices)
            self.assertEqual(r.garantia, at.SOFTWARE)
            self.assertNotIn(r.motivo, (at.M_OK, at.M_NIVEL_SOFTWARE), (i, r))

    def test_fuera_de_la_vigencia_de_los_certificados_no_da_hardware(self):
        r = self.ev(self.a, raices=[raiz_del_emulador(self.a["certs"])], ahora_ms=AHORA + 400 * 86_400_000)
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_FUERA_DE_VIGENCIA))

    def test_la_firma_de_la_app_del_emulador_no_es_la_de_avacom(self):
        """El APK de depuración del emulador se firma con otra llave que la de entrega: con la política REAL (`app.json`) nunca daría `hardware` aunque lo demás cuadrara."""
        real = self.google.app()
        self.assertEqual(real.paquetes, frozenset({"com.avacom.lms.student"}))
        self.assertNotIn(bytes.fromhex("52e975525eb071b8249759602228ce26fa8ab3fe80848a62f76b3ad7cfedb536"), real.firmas)
        self.assertIn(bytes.fromhex("16efdeaffb023e8b5b6704d9412911652bc7e4f405fcc3faf23eb92511a65ce0"), real.firmas)


class DatosEmpaquetadosTests(SimpleTestCase):
    """Lo que viaja en el paquete para verificar sin internet."""

    def test_las_raices_de_google_cargan_y_la_de_2016_ya_no_ancla_nada(self):
        fuente = AtestacionEmpaquetada()
        raices = {r.nombre: r for r in fuente.raices()}
        self.assertGreaterEqual(len(raices), 4)
        self.assertIn("ecdsa-p384-2025", raices)
        self.assertIn("rsa-2022", raices)
        caducada = raices["rsa-2016"]
        self.assertLess(caducada.hasta_ms, AHORA)                              # caducó el 2026-05-24
        for nombre in ("rsa-2022", "ecdsa-p384-2025", "rsa-2019", "rsa-2021"):
            self.assertGreater(raices[nombre].hasta_ms, AHORA, nombre)

    def test_la_lista_de_revocadas_carga_y_trae_los_dos_formatos(self):
        revocadas = AtestacionEmpaquetada().revocadas()
        self.assertGreater(len(revocadas), 1500)
        self.assertTrue(any(len(s) == 32 for s in revocadas))                     # serie en hexadecimal
        self.assertTrue(any(s.isdigit() for s in revocadas))                      # y en decimal

    def test_las_huellas_de_las_raices_son_las_de_la_documentacion_de_google(self):
        # SHA-256 anotadas el 2026-10-22 al comparar developer.android.com con https://android.googleapis.com/attestation/root
        esperadas = {"rsa-2022": "cedb1cb6dc896ae5ec797348bce9286753c2b38ee71ce0fbe34a9a1248800dfc",
                     "ecdsa-p384-2025": "6d9db4ce6c5c0b293166d08986e05774a8776ceb525d9e4329520de12ba4bcc0"}
        datos = json.loads((Path(__file__).resolve().parent.parent / "atestacion" / "raices_google.json").read_text(encoding="utf-8"))
        por_nombre = {r["nombre"]: r["sha256"] for r in datos["raices"]}
        for nombre, huella in esperadas.items():
            self.assertEqual(por_nombre[nombre], huella)

    def test_sin_los_archivos_la_atestacion_no_da_hardware_y_no_lanza(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as vacia:
            fuente = AtestacionEmpaquetada(Path(vacia), firmas_extra="")
            self.assertEqual((fuente.raices(), fuente.revocadas(), fuente.app()), ([], frozenset(), at.PoliticaDeApp()))

    def test_las_firmas_extra_de_otras_maquinas_de_desarrollo_se_suman(self):
        f = AtestacionEmpaquetada(firmas_extra="52:E9:75:52:5E:B0:71:B8:24:97:59:60:22:28:CE:26:FA:8A:B3:FE:80:84:8A:62:F7:6B:3A:D7:CF:ED:B5:36, basura")
        self.assertIn(bytes.fromhex("52e975525eb071b8249759602228ce26fa8ab3fe80848a62f76b3ad7cfedb536"), f.app().firmas)
        self.assertIn(bytes.fromhex("16efdeaffb023e8b5b6704d9412911652bc7e4f405fcc3faf23eb92511a65ce0"), f.app().firmas)
