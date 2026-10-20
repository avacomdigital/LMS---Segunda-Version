"""Las llaves de emisión: privada cifrada con frase de paso, pública en texto (LIC-E-05, LIC-E-14)."""
from __future__ import annotations

import base64
import json
import unittest

from avacom_licencias import llaves
from avacom_licencias.dominio_nodo import firma

from .apoyo import FRASE

CREADA = "2026-10-20T15:00:00Z"


class LlavesTests(unittest.TestCase):
    def test_se_crea_y_se_abre_con_la_frase(self):
        avkey, publica_texto, publica = llaves.generar("prod-2026-1", FRASE, CREADA)
        abierta = llaves.abrir(avkey, FRASE)
        self.assertEqual(abierta.kid, "prod-2026-1")
        self.assertEqual(abierta.publica, publica)
        self.assertEqual(firma.publica_de(abierta.privada), publica)
        kid, leida = llaves.leer_publica(publica_texto)
        self.assertEqual((kid, leida), ("prod-2026-1", publica))

    def test_la_privada_no_esta_en_claro_en_el_archivo(self):
        avkey, _, _ = llaves.generar("prod-2026-1", FRASE, CREADA)
        privada = llaves.abrir(avkey, FRASE).privada
        for forma in (privada, privada.hex().encode(), base64.b64encode(privada), base64.urlsafe_b64encode(privada)):
            self.assertNotIn(forma, avkey)
        self.assertNotIn(FRASE.encode(), avkey)

    def test_una_frase_equivocada_no_abre(self):
        avkey, _, _ = llaves.generar("prod-2026-1", FRASE, CREADA)
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.abrir(avkey, FRASE + "x")
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.abrir(avkey, "")

    def test_el_nombre_y_la_publica_van_atados_al_cifrado(self):
        avkey, _, _ = llaves.generar("prod-2026-1", FRASE, CREADA)
        documento = json.loads(avkey)
        cambiado = dict(documento, kid="prod-2026-2")
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.abrir(json.dumps(cambiado).encode(), FRASE)
        otra = llaves.generar("prod-2026-1", FRASE, CREADA)[2]
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.abrir(json.dumps(dict(documento, publica=otra.hex())).encode(), FRASE)

    def test_un_archivo_que_no_es_una_llave_se_rechaza(self):
        for basura in (b"", b"no es json", b"{}", json.dumps({"formato": "otro", "version": 1}).encode()):
            with self.assertRaises(llaves.ErrorDeLlave):
                llaves.abrir(basura, FRASE)

    def test_nombres_y_frases_invalidos(self):
        for kid in ("", "Prod 2026", "PROD", "con/barra", "x" * 65, None):
            with self.assertRaises(llaves.ErrorDeLlave):
                llaves.generar(kid, FRASE, CREADA)
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.generar("prod-2026-1", "corta", CREADA)

    def test_dos_llaves_nunca_son_iguales(self):
        a, b = llaves.generar("k1", FRASE, CREADA), llaves.generar("k1", FRASE, CREADA)
        self.assertNotEqual(a[2], b[2])
        self.assertNotEqual(json.loads(a[0])["kdf"]["sal"], json.loads(b[0])["kdf"]["sal"])

    def test_el_nombre_cabe_en_lo_que_acepta_el_nodo(self):
        """El cargador de llaves del nodo acepta hasta 32 caracteres: el emisor no crea una llave que el nodo no reconocería."""
        llaves.generar("a" * 32, FRASE, CREADA)
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.generar("a" * 33, FRASE, CREADA)

    def test_la_entrada_para_el_nodo_es_el_formato_de_produccion_json(self):
        _, _, publica = llaves.generar("prod-2026-1", FRASE, CREADA)
        texto = llaves.entrada_para_el_nodo("prod-2026-1", publica)
        self.assertEqual(json.loads(texto), {"version": 1, "claves": [{"kid": "prod-2026-1", "publica": publica.hex(), "estado": "vigente"}]})
        self.assertEqual(llaves.leer_claves_del_nodo(texto), {"prod-2026-1": publica})
        self.assertNotIn("privada", texto)

    def test_leer_claves_del_nodo_hace_lo_mismo_que_el_nodo(self):
        buena = {"kid": "a", "publica": "11" * 32, "estado": "siguiente"}
        casos = {"retirada": [dict(buena, estado="retirada")], "kid inválido": [dict(buena, kid="Mal Nombre")], "pública corta": [dict(buena, publica="11" * 31)],
                 "pública no hex": [dict(buena, publica="zz" * 32)], "sin kid": [{"publica": "11" * 32}], "basura": ["x", 5, None]}
        for nombre, claves in casos.items():
            self.assertEqual(llaves.leer_claves_del_nodo(json.dumps({"claves": claves})), {}, nombre)
        self.assertEqual(llaves.leer_claves_del_nodo(json.dumps({"claves": [buena]})), {"a": bytes.fromhex("11" * 32)})
        self.assertEqual(llaves.leer_claves_del_nodo(json.dumps([1, 2])), {})
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.leer_claves_del_nodo("{ no es json")

    def test_la_publica_se_comprueba(self):
        _, texto, _ = llaves.generar("prod-2026-1", FRASE, CREADA)
        malo = texto.replace("sha256=", "sha256=00")
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.leer_publica(malo)
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.leer_publica("otra-cosa\nkid=x")
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.leer_publica("avacom-llave-publica\nkid=prod-2026-1\npublica=zz")


if __name__ == "__main__":
    unittest.main()
