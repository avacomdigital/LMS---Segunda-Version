"""
El sello de dispositivo AVACOM (S1): lo que se acepta y lo que se rechaza. Sin hardware: la clave del equipo es una EC P-256 en memoria y la «prueba de posesión» entra como un booleano.
Cada rechazo se prueba con un sello FIRMADO CORRECTAMENTE cuando lo que se demuestra es la regla de forma y no la firma.
"""
from __future__ import annotations

import random

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from django.test import SimpleTestCase

from licenciamiento.dominio import firma, sello as s, tlv
from licenciamiento.dominio.errores import LicenciaInvalida

AHORA = 1_790_000_000_000
PRIV, PUB = firma.par_nuevo()
PRIV2, PUB2 = firma.par_nuevo()
CLAVES = {"sello-prueba": PUB}
EQUIPO = ec.generate_private_key(ec.SECP256R1())
SPKI = EQUIPO.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
HUELLA = s.huella_de_spki(SPKI)


def ejemplo(**cambios) -> s.Sello:
    base = dict(id="0a0b0c0d-0e0f-1011-1213-141516171819", serie="OPS-0001", modelo="Panel 86", origen="fabrica", clave_huella=HUELLA, cifrado_huella=b"\x11" * 32, ek_huella=b"\x22" * 32,
                emitido=AHORA - 1000, vence=0, lote="L-01", mac="00:11:22:33:44:55", evidencia="inventario", kid="", sha256="")
    base.update(cambios)
    return s.Sello(**base)


def emitir(sello: s.Sello | None = None, kid="sello-prueba", llave=PRIV) -> bytes:
    return s.codificar_sello(kid, sello or ejemplo(), lambda m: firma.firmar(llave, m))


def motivo(accion) -> str:
    try:
        accion()
    except LicenciaInvalida as error:
        return error.motivo
    raise AssertionError("debía rechazarse")


def p1363(clave, mensaje: bytes) -> bytes:
    r, t = decode_dss_signature(clave.sign(mensaje, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, "big") + t.to_bytes(32, "big")


def firmar_ecdsa(mensaje: bytes) -> bytes:
    return p1363(EQUIPO, mensaje)


def sellar_campos(campos) -> bytes:
    return tlv.sellar(tlv.escribir(s.MAGIC_SELLO, "sello-prueba", campos, s.CONOCIDOS_SELLO), lambda m: firma.firmar(PRIV, m))


class FormatoTests(SimpleTestCase):
    def test_ida_y_vuelta(self):
        leido = s.leer_sello(emitir(), CLAVES)
        original = ejemplo()
        self.assertEqual((leido.id, leido.serie, leido.modelo, leido.origen, leido.clave_huella, leido.cifrado_huella, leido.ek_huella, leido.emitido, leido.vence, leido.lote, leido.mac, leido.evidencia, leido.kid),
                         (original.id, original.serie, original.modelo, "fabrica", HUELLA, b"\x11" * 32, b"\x22" * 32, original.emitido, 0, "L-01", "00:11:22:33:44:55", "inventario", "sello-prueba"))

    def test_un_sello_mide_poco(self):
        self.assertLess(len(emitir()), 400)

    def test_firma_alterada_o_de_otra_llave(self):
        datos = bytearray(emitir())
        datos[-1] ^= 1
        self.assertEqual(motivo(lambda: s.leer_sello(bytes(datos), CLAVES)), "firma_invalida")
        self.assertEqual(motivo(lambda: s.leer_sello(emitir(llave=PRIV2), CLAVES)), "firma_invalida")

    def test_kid_desconocido(self):
        self.assertEqual(motivo(lambda: s.leer_sello(emitir(kid="otra-llave"), CLAVES)), "kid_desconocido")

    def test_una_licencia_no_es_un_sello(self):
        self.assertEqual(motivo(lambda: s.leer_sello(b"AVLC" + emitir()[4:], CLAVES)), "formato")

    def test_con_la_llave_de_licencias_no_se_acepta_como_sello(self):
        # SP-07: las llaves son distintas; un sello firmado con un kid que no está entre las de sello se rechaza
        self.assertEqual(motivo(lambda: s.leer_sello(emitir(kid="prod-2026-1"), CLAVES)), "kid_desconocido")

    def test_vencimiento_antes_de_la_emision_se_rechaza(self):
        self.assertEqual(motivo(lambda: s.leer_sello(emitir(ejemplo(vence=AHORA - 5000)), CLAVES)), "campo_invalido")

    def test_texto_no_ascii_se_rechaza(self):
        campos = {s.T_ID: b"\x01" * 16, s.T_ORIGEN: b"\x01", s.T_CLAVE_HUELLA: HUELLA, s.T_EMITIDO: AHORA.to_bytes(8, "big"), s.T_VENCE: bytes(8), s.T_EVIDENCIA: b"\x01", s.T_SERIE: "ñ".encode()}
        self.assertEqual(motivo(lambda: s.leer_sello(sellar_campos(campos), CLAVES)), "campo_invalido")

    def test_falta_un_campo_obligatorio(self):
        campos = {s.T_ID: b"\x01" * 16, s.T_ORIGEN: b"\x01", s.T_EMITIDO: AHORA.to_bytes(8, "big"), s.T_VENCE: bytes(8), s.T_EVIDENCIA: b"\x01"}
        self.assertEqual(motivo(lambda: s.leer_sello(sellar_campos(campos), CLAVES)), "campo_faltante")

    def test_mutaciones_de_un_sello_valido_nunca_se_aceptan(self):
        """Semilla fija: cada alteración de un bit (o truncado) del sello firmado se rechaza."""
        base, azar, aceptadas = emitir(), random.Random(20261026), 0
        for _ in range(20_000):
            datos = bytearray(base)
            if azar.random() < 0.15:
                datos = datos[:azar.randrange(len(datos))]
            else:
                datos[azar.randrange(len(datos))] ^= 1 << azar.randrange(8)
            try:
                s.leer_sello(bytes(datos), CLAVES)
                aceptadas += 1
            except LicenciaInvalida:
                pass
        self.assertEqual(aceptadas, 0)


class VeredictoTests(SimpleTestCase):
    def evaluar(self, datos=None, huella=HUELLA, posesion=True, revocados=frozenset(), ahora=AHORA):
        return s.evaluar(emitir() if datos is None else datos, CLAVES, huella, posesion, revocados, ahora)

    def test_autenticado(self):
        self.assertEqual(self.evaluar().estado, s.AUTENTICADO)

    def test_sin_sello(self):
        self.assertEqual(s.evaluar(None, CLAVES, HUELLA, True, frozenset(), AHORA).estado, s.SIN_SELLO)
        self.assertEqual(s.evaluar(b"", CLAVES, HUELLA, True, frozenset(), AHORA).estado, s.SIN_SELLO)

    def test_sello_alterado(self):
        datos = bytearray(emitir())
        datos[20] ^= 1
        self.assertEqual(self.evaluar(bytes(datos)).estado, s.SELLO_INVALIDO)

    def test_sello_vencido(self):
        v = self.evaluar(emitir(ejemplo(vence=AHORA + 10)), ahora=AHORA + 11)
        self.assertEqual((v.estado, v.motivo), (s.SELLO_INVALIDO, "vencido"))
        self.assertEqual(self.evaluar(emitir(ejemplo(vence=AHORA + 10)), ahora=AHORA + 10).estado, s.AUTENTICADO)

    def test_sello_copiado_a_otro_equipo(self):
        otra = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.assertEqual(self.evaluar(huella=s.huella_de_spki(otra)).estado, s.CLAVE_DISTINTA)

    def test_equipo_sin_clave_no_es_fraude_es_no_verificable(self):
        self.assertEqual(self.evaluar(huella=None, posesion=None).estado, s.NO_VERIFICABLE)

    def test_la_clave_esta_pero_no_firma(self):
        self.assertEqual(self.evaluar(posesion=False).estado, s.CLAVE_DISTINTA)
        self.assertEqual(self.evaluar(posesion=None).estado, s.NO_VERIFICABLE)

    def test_revocado(self):
        self.assertEqual(self.evaluar(revocados=frozenset({HUELLA})).estado, s.REVOCADO)

    def test_cambiar_mac_serie_modelo_no_cambia_el_veredicto(self):
        """SP-03: lo informativo no decide."""
        for cambios in (dict(mac=""), dict(mac="AA:BB:CC:DD:EE:FF"), dict(serie="OTRA", modelo="Otro"), dict(ek_huella=None, cifrado_huella=None)):
            self.assertEqual(self.evaluar(emitir(ejemplo(**cambios))).estado, s.AUTENTICADO, cambios)

    def test_posesion_ata_el_reto_a_la_huella(self):
        self.assertNotEqual(s.mensaje_de_posesion(b"\x01" * 32, HUELLA), s.mensaje_de_posesion(b"\x01" * 32, b"\x00" * 32))
        with self.assertRaises(ValueError):
            s.mensaje_de_posesion(b"\x01" * 31, HUELLA)


class RevocadosTests(SimpleTestCase):
    def test_ida_y_vuelta_y_firma(self):
        datos = s.codificar_revocados("sello-prueba", 7, AHORA, [b"\x02" * 32, b"\x01" * 32, b"\x01" * 32], lambda m: firma.firmar(PRIV, m))
        self.assertEqual(s.leer_revocados(datos, CLAVES), (7, frozenset({b"\x01" * 32, b"\x02" * 32})))
        malo = bytearray(datos)
        malo[-1] ^= 1
        self.assertEqual(motivo(lambda: s.leer_revocados(bytes(malo), CLAVES)), "firma_invalida")

    def test_lista_vacia_es_valida_y_mas_de_128_no_cabe(self):
        self.assertEqual(s.leer_revocados(s.codificar_revocados("sello-prueba", 1, AHORA, [], lambda m: firma.firmar(PRIV, m)), CLAVES)[1], frozenset())
        with self.assertRaises(ValueError):
            s.codificar_revocados("sello-prueba", 1, AHORA, [i.to_bytes(32, "big") for i in range(129)], lambda m: firma.firmar(PRIV, m))


class SolicitudTests(SimpleTestCase):
    def solicitud(self, spki=SPKI) -> s.Solicitud:
        return s.Solicitud("0a0b0c0d-0e0f-1011-1213-141516171819", "OPS-0001", "Panel 86", spki, b"\x30" * 100, b"\x31" * 100, "00:11:22:33:44:55", True, AHORA, HUELLA)

    def test_ida_y_vuelta_prueba_posesion(self):
        leida = s.leer_solicitud(s.codificar_solicitud(self.solicitud(), firmar_ecdsa))
        self.assertEqual((leida.clave_huella, leida.serie, leida.en_tpm, leida.mac), (HUELLA, "OPS-0001", True, "00:11:22:33:44:55"))

    def test_firmada_con_otra_clave_se_rechaza(self):
        otra = ec.generate_private_key(ec.SECP256R1())
        self.assertEqual(motivo(lambda: s.leer_solicitud(s.codificar_solicitud(self.solicitud(), lambda m: p1363(otra, m)))), "firma_invalida")

    def test_alterada_se_rechaza(self):
        datos = bytearray(s.codificar_solicitud(self.solicitud(), firmar_ecdsa))
        datos[30] ^= 1
        with self.assertRaises(LicenciaInvalida):
            s.leer_solicitud(bytes(datos))

    def test_clave_que_no_es_p256_se_rechaza(self):
        with self.assertRaises(LicenciaInvalida):
            s.leer_solicitud(s.codificar_solicitud(self.solicitud(b"\x30\x03\x02\x01\x00"), firmar_ecdsa))
