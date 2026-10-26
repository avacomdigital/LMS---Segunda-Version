"""La estación de aprovisionamiento (S1): qué firma y qué se niega a firmar, y el recorrido por la línea de comandos."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from avacom_licencias import cli, llaves, registro as reg, sellos
from avacom_licencias.dominio_nodo import firma, sello

AHORA = 1_790_000_000_000
FRASE = "una frase de paso larga y sin usar"
SPKI = lambda k: k.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)  # noqa: E731


class Equipo:
    def __init__(self, serie="OPS-0001", ek=b"\x04" + b"\x07" * 64):
        self.clave = ec.generate_private_key(ec.SECP256R1())
        self.serie, self.ek = serie, ek

    def avsol(self) -> bytes:
        def firmar(m):
            r, t = decode_dss_signature(self.clave.sign(m, ec.ECDSA(hashes.SHA256())))
            return r.to_bytes(32, "big") + t.to_bytes(32, "big")
        s = sello.Solicitud("0a0b0c0d-0e0f-1011-1213-141516171819", self.serie, "Panel 86", SPKI(self.clave), b"\x30" * 90, self.ek, "00:11:22:33:44:55", True, AHORA, sello.huella_de_spki(SPKI(self.clave)))
        return sello.codificar_solicitud(s, firmar)


def inventario(**series) -> sellos.Inventario:
    series = series or {"OPS-0001": {"ek_huella": sello.huella_de_spki(b"\x04" + b"\x07" * 64).hex()}}
    return sellos.Inventario.leer(json.dumps({"version": 1, "lote": "L-01", "modelo": "Panel 86", "series": series}))


class EstacionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registro = reg.Registro(Path(self._tmp.name) / "registro.jsonl")
        self.priv, self.pub = firma.par_nuevo()

    def emitir(self, equipo=None, inv=None, **kw):
        return sellos.emitir_sello((equipo or Equipo()).avsol(), self.priv, "sello-prueba", inv or inventario(), self.registro, kw.pop("origen", "entrega"), AHORA, **kw)

    def test_emite_un_sello_que_el_nodo_verifica(self):
        equipo = Equipo()
        datos, s, renglon = self.emitir(equipo)
        v = sello.evaluar(datos, {"sello-prueba": self.pub}, sello.huella_de_spki(SPKI(equipo.clave)), True, frozenset(), AHORA + 1)
        self.assertEqual(v.estado, sello.AUTENTICADO)
        self.assertEqual((s.serie, s.origen, s.evidencia, s.lote), ("OPS-0001", "entrega", "inventario", "L-01"))
        self.assertEqual((renglon["accion"], renglon["serie"]), ("sello", "OPS-0001"))
        self.assertNotIn("clave_huella", json.dumps(renglon).replace("clave_huella_sha256", ""))        # el registro no copia la huella entera

    def test_serie_fuera_del_inventario_es_un_equipo_ajeno(self):
        with self.assertRaisesRegex(sellos.ErrorDeSello, "no está en el inventario"):
            self.emitir(Equipo(serie="PC-DE-UN-TERCERO"))

    def test_ekpub_distinta_a_la_del_inventario_se_niega(self):
        with self.assertRaisesRegex(sellos.ErrorDeSello, "EKPub"):
            self.emitir(Equipo(ek=b"\x04" + b"\x09" * 64))

    def test_sin_ekpub_cuando_el_inventario_la_pide_se_niega(self):
        with self.assertRaisesRegex(sellos.ErrorDeSello, "EKPub"):
            self.emitir(Equipo(ek=None))

    def test_una_serie_se_sella_una_vez(self):
        self.emitir()
        with self.assertRaisesRegex(sellos.ErrorDeSello, "ya tiene sello"):
            self.emitir()
        _, _, r2 = self.emitir(reemitir=True)
        self.assertTrue(r2["reemite"])

    def test_solicitud_alterada_se_rechaza(self):
        datos = bytearray(Equipo().avsol())
        datos[40] ^= 1
        with self.assertRaises(sellos.ErrorDeSello):
            sellos.emitir_sello(bytes(datos), self.priv, "sello-prueba", inventario(), self.registro, "entrega", AHORA)

    def test_registro_alterado_no_se_firma_nada(self):
        self.emitir()
        texto = self.registro.ruta.read_text(encoding="utf-8").replace("OPS-0001", "OPS-0002")
        self.registro.ruta.write_text(texto, encoding="utf-8")
        with self.assertRaisesRegex(sellos.ErrorDeSello, "alterado"):
            self.emitir(Equipo(), reemitir=True)

    def test_vencimiento_pasado_se_niega(self):
        with self.assertRaisesRegex(sellos.ErrorDeSello, "vencimiento"):
            self.emitir(vence_ms=AHORA - 1)

    def test_origen_invalido(self):
        with self.assertRaises(sellos.ErrorDeSello):
            self.emitir(origen="mercado")

    def test_revocados_parten_de_la_lista_anterior(self):
        claves = {"sello-prueba": self.pub}
        d1, n1 = sellos.emitir_revocados(self.priv, "sello-prueba", [b"\x01" * 32], None, claves, self.registro, AHORA)
        d2, n2 = sellos.emitir_revocados(self.priv, "sello-prueba", [b"\x02" * 32], d1, claves, self.registro, AHORA + 1)
        self.assertEqual((n1, n2), (1, 2))
        self.assertEqual(sello.leer_revocados(d2, claves), (2, frozenset({b"\x01" * 32, b"\x02" * 32})))

    def test_revocados_no_parten_de_una_lista_alterada(self):
        claves = {"sello-prueba": self.pub}
        d1, _ = sellos.emitir_revocados(self.priv, "sello-prueba", [b"\x01" * 32], None, claves, self.registro, AHORA)
        malo = bytearray(d1)
        malo[-2] ^= 1
        with self.assertRaises(sellos.ErrorDeSello):
            sellos.emitir_revocados(self.priv, "sello-prueba", [b"\x02" * 32], bytes(malo), claves, self.registro, AHORA)


class RecorridoDeLaLineaDeComandosTests(unittest.TestCase):
    """Genera la llave con la ceremonia real, sella, verifica, revoca: lo que haría quien opera, pero con la frase por la variable de pruebas."""

    def correr(self, *args) -> tuple[int, str]:
        salida, error = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"AVACOM_EMISOR_FRASE": FRASE}), contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = cli.main(list(args))
        return codigo, salida.getvalue() + error.getvalue()

    def test_recorrido_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            avkey, texto_pub, _ = llaves.generar("sello-prueba", FRASE, "2026-10-26T00:00:00Z")
            (t / "sello-prueba.avkey").write_bytes(avkey)
            (t / "sello-prueba.pub").write_text(texto_pub, encoding="utf-8")
            (t / "equipo.avsol").write_bytes(Equipo().avsol())
            (t / "inventario.json").write_text(json.dumps({"version": 1, "lote": "L-01", "series": {"OPS-0001": {}}}), encoding="utf-8")
            registro = str(t / "registro.jsonl")
            codigo, texto = self.correr("sello", "emitir", "--solicitud", str(t / "equipo.avsol"), "--privada", str(t / "sello-prueba.avkey"), "--inventario", str(t / "inventario.json"),
                                        "--origen", "fabrica", "--salida", str(t / "salida"), "--registro", registro)
            self.assertEqual(codigo, 0, texto)
            archivo = t / "salida" / "OPS-0001.avsello"
            self.assertTrue(archivo.is_file())
            codigo, texto = self.correr("sello", "ver", str(archivo), "--publica", str(t / "sello-prueba.pub"))
            self.assertEqual(codigo, 0, texto)
            self.assertIn("La firma es válida", texto)
            huella = next(l.split(": ")[1] for l in texto.splitlines() if "Huella de la clave" in l)
            codigo, texto = self.correr("sello", "revocar", "--privada", str(t / "sello-prueba.avkey"), "--huella", huella, "--salida", str(t / "salida"), "--registro", registro)
            self.assertEqual(codigo, 0, texto)
            codigo, texto = self.correr("sello", "revocados", "ver", str(t / "salida" / "revocados-0001.avrev"), "--publica", str(t / "sello-prueba.pub"))
            self.assertEqual(codigo, 0, texto)
            self.assertIn(huella, texto)

    def test_la_llave_de_licencias_no_firma_sellos(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            avkey, _, _ = llaves.generar("prod-2026-1", FRASE, "2026-10-26T00:00:00Z")
            (t / "prod.avkey").write_bytes(avkey)
            (t / "equipo.avsol").write_bytes(Equipo().avsol())
            (t / "inventario.json").write_text(json.dumps({"series": {"OPS-0001": {}}}), encoding="utf-8")
            codigo, texto = self.correr("sello", "emitir", "--solicitud", str(t / "equipo.avsol"), "--privada", str(t / "prod.avkey"), "--inventario", str(t / "inventario.json"),
                                        "--origen", "entrega", "--salida", str(t / "s"), "--registro", str(t / "r.jsonl"))
            self.assertEqual(codigo, 1)
            self.assertIn("llave de sello", texto)
            self.assertFalse((t / "s").exists())


if __name__ == "__main__":
    unittest.main()
