"""Identidad de dispositivo · dominio puro (Fase 5, P-24): la atestación de Android y la prueba de posesión, con cadenas sintéticas y defectos fabricados uno a uno."""
from __future__ import annotations

import os
import random

from django.test import SimpleTestCase

from licenciamiento.dominio import atestacion as at

from . import atestacion_apoyo as ap

NONCE = bytes(range(32))


class AtestacionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.e = ap.Entorno()

    def ev(self, ext, nonce=NONCE, **kw):
        return self.e.evaluar(self.e.cadena(ext), nonce, **kw)

    def test_una_atestacion_completa_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE))
        self.assertEqual((r.garantia, r.motivo), (at.HARDWARE, at.M_OK), r)
        self.assertEqual(r.detalle["nivel"], "tee")
        self.assertEqual(r.detalle["arranque"], "verificado")

    def test_strongbox_tambien_es_hardware(self):
        r = self.ev(ap.extension(reto=NONCE, nivel_atestacion=at.NIVEL_STRONGBOX))
        self.assertEqual(r.garantia, at.HARDWARE)
        self.assertEqual(r.detalle["nivel"], "strongbox")

    def test_un_reto_distinto_no_da_hardware(self):
        r = self.ev(ap.extension(reto=bytes(reversed(NONCE))))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_RETO_DISTINTO))

    def test_un_reto_demasiado_corto_no_da_hardware(self):
        corto = NONCE[:8]
        r = self.e.evaluar(self.e.cadena(ap.extension(reto=corto)), corto)
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_CADENA_INVALIDA))

    def test_una_app_firmada_con_otra_llave_no_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE, firmas=(ap.FIRMA_AJENA,)))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_APP_AJENA))

    def test_otra_app_con_la_misma_firma_no_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE, paquetes=("com.otra.app",)))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_PAQUETE_AJENO))

    def test_el_arranque_desbloqueado_no_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE, bloqueado=False))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_GESTOR_ABIERTO))

    def test_el_arranque_no_verificado_no_da_hardware(self):
        for estado in (at.ARRANQUE_AUTOFIRMADO, at.ARRANQUE_NO_VERIFICADO, at.ARRANQUE_FALLIDO):
            r = self.ev(ap.extension(reto=NONCE, arranque=estado))
            self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_ARRANQUE), estado)

    def test_sin_raiz_de_confianza_no_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE, arranque=None))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_ARRANQUE))

    def test_una_clave_en_software_no_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE, nivel_atestacion=at.NIVEL_SOFTWARE))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_NIVEL_SOFTWARE))
        r = self.ev(ap.extension(reto=NONCE, nivel_atestacion=at.NIVEL_TEE, nivel_llave=at.NIVEL_SOFTWARE))
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_NIVEL_SOFTWARE))

    def test_una_raiz_que_no_es_de_google_no_da_hardware(self):
        r = self.ev(ap.extension(reto=NONCE), raices=[])
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_RAIZ_DESCONOCIDA))

    def test_una_raiz_vencida_no_ancla_nada(self):
        raiz = self.e.raices[0]
        vencida = [at.Raiz(raiz.nombre, raiz.spki, raiz.desde_ms, ap.AHORA - 1)]
        r = self.ev(ap.extension(reto=NONCE), raices=vencida)
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_FUERA_DE_VIGENCIA))

    def test_un_certificado_revocado_no_da_hardware(self):
        for serie in ("3", "2", "1", format(3, "x")):
            r = self.ev(ap.extension(reto=NONCE), revocadas=frozenset({serie}))
            self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_REVOCADO), serie)

    def test_la_clave_declarada_tiene_que_ser_la_de_la_hoja(self):
        otra = ap.spki(ap.ec.generate_private_key(ap.ec.SECP256R1()).public_key())
        r = self.ev(ap.extension(reto=NONCE), spki_declarada=otra)
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_CLAVE_DISTINTA))

    def test_una_cadena_con_la_hoja_de_otra_clave_no_se_deja_pasar(self):
        intruso = ap.ec.generate_private_key(ap.ec.SECP256R1())
        cadena = self.e.cadena(ap.extension(reto=NONCE), hoja_con_clave=intruso)
        r = self.e.evaluar(cadena, NONCE)
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_CLAVE_DISTINTA))

    def test_una_cadena_cortada_o_desordenada_no_da_hardware(self):
        cadena = self.e.cadena(ap.extension(reto=NONCE))
        for mala in (cadena[:2], [cadena[1], cadena[0], cadena[2]], [cadena[0], cadena[2]], []):
            r = self.e.evaluar(mala, NONCE)
            self.assertEqual(r.garantia, at.SOFTWARE)

    def test_basura_en_la_cadena_no_lanza(self):
        for mala in ([b"x"], [b""], [os.urandom(300)], [b"\x30\x03\x02\x01\x01"]):
            self.assertEqual(self.e.evaluar(mala, NONCE).garantia, at.SOFTWARE)

    def test_sin_extension_no_da_hardware(self):
        cadena = self.e.cadena(None)
        r = self.e.evaluar(cadena, NONCE)
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_SIN_EXTENSION))

    def test_sin_politica_de_app_no_se_puede_dar_hardware(self):
        r = self.ev(ap.extension(reto=NONCE), app=at.PoliticaDeApp())
        self.assertEqual((r.garantia, r.motivo), (at.SOFTWARE, at.M_PAQUETE_AJENO))

    def test_mutar_la_extension_nunca_lanza_ni_regala_hardware(self):
        base = ap.extension(reto=NONCE)
        azar = random.Random(20261022)
        aceptadas = 0
        for _ in range(600):
            mutada = bytearray(base)
            for _k in range(azar.randint(1, 4)):
                mutada[azar.randrange(len(mutada))] = azar.randrange(256)
            if bytes(mutada) == base:
                continue
            r = self.ev(bytes(mutada))
            self.assertIn(r.garantia, (at.HARDWARE, at.SOFTWARE))
            aceptadas += r.garantia == at.HARDWARE
        # cambiar un byte que no cuenta (relleno de un hash, la versión) puede seguir dando hardware; lo que no puede pasar es una excepción
        self.assertLess(aceptadas, 600)

    def test_la_extension_truncada_se_rechaza(self):
        base = ap.extension(reto=NONCE)
        for corte in range(0, len(base), 7):
            with self.assertRaises(at.AtestacionInvalida):
                at.leer_descripcion(base[:corte])

    def test_el_orden_de_los_niveles(self):
        self.assertTrue(at.al_menos(at.HARDWARE, at.SOFTWARE))
        self.assertTrue(at.al_menos(at.SOFTWARE, at.DECLARADA))
        self.assertFalse(at.al_menos(at.DECLARADA, at.SOFTWARE))
        self.assertFalse(at.al_menos("rara", at.DECLARADA))


class PosesionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.e = ap.Entorno()

    def test_la_firma_del_reto_se_verifica(self):
        firma = self.e.firmar_reto(NONCE, "student-tableta-0a1b2c3d")
        self.assertTrue(at.verificar_posesion(self.e.spki_clave, firma, NONCE, "student-tableta-0a1b2c3d"))

    def test_la_firma_de_un_equipo_no_sirve_para_otro(self):
        firma = self.e.firmar_reto(NONCE, "student-tableta-0a1b2c3d")
        self.assertFalse(at.verificar_posesion(self.e.spki_clave, firma, NONCE, "student-tableta-ffffffff"))

    def test_la_firma_de_otro_reto_no_sirve(self):
        firma = self.e.firmar_reto(NONCE, "x")
        self.assertFalse(at.verificar_posesion(self.e.spki_clave, firma, NONCE[::-1], "x"))

    def test_la_firma_de_otra_clave_no_sirve_ni_la_basura(self):
        otra = ap.ec.generate_private_key(ap.ec.SECP256R1())
        firma = otra.sign(at.mensaje_del_reto(NONCE, "x"), ap.ec.ECDSA(ap.hashes.SHA256()))
        self.assertFalse(at.verificar_posesion(self.e.spki_clave, firma, NONCE, "x"))
        self.assertFalse(at.verificar_posesion(self.e.spki_clave, b"", NONCE, "x"))
        self.assertFalse(at.verificar_posesion(b"no es una clave", firma, NONCE, "x"))

    def test_la_firma_p1363_de_windows_tambien_se_acepta(self):
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        der = self.e.firmar_reto(NONCE, "ops-pc-1")
        r, s = decode_dss_signature(der)
        p1363 = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        self.assertTrue(at.verificar_posesion(self.e.spki_clave, p1363, NONCE, "ops-pc-1"))
        self.assertFalse(at.verificar_posesion(self.e.spki_clave, p1363[:-1] + bytes([p1363[-1] ^ 1]), NONCE, "ops-pc-1"))

    def test_solo_se_acepta_ec_p256(self):
        p384 = ap.ec.generate_private_key(ap.ec.SECP384R1())
        firma = p384.sign(at.mensaje_del_reto(NONCE, "x"), ap.ec.ECDSA(ap.hashes.SHA256()))
        self.assertFalse(at.verificar_posesion(ap.spki(p384.public_key()), firma, NONCE, "x"))
