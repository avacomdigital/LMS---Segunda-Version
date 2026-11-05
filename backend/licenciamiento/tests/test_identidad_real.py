"""
El recorrido HTTP de la identidad con la prueba REAL del Keystore de un emulador (las cadenas de `fixtures/atestacion/`): el nodo acepta la firma de Java, decide `software` por la raíz que no es de
Google, la guarda en `device_manager`, y repetirla (el mismo reto) o aplicarla a otro equipo no funciona.
"""
from __future__ import annotations

from licenciamiento.dominio import atestacion as at
from licenciamiento.infraestructura.identidad import AtestacionEmpaquetada

from .base import L
from .test_atestacion_real import cargar
from .test_identidad import BaseIdentidad, b64


class RetosFijos:
    """Los retos que usó el emulador (el nodo no los emitió, pero ante el nodo son retos vigentes de un solo uso)."""

    def __init__(self, *nonces: bytes):
        self.vigentes = set(nonces)

    def entregar(self, ahora_ms: int):
        raise AssertionError("no se piden retos nuevos en estas pruebas")

    def consumir(self, nonce: bytes, ahora_ms: int) -> bool:
        if bytes(nonce) in self.vigentes:
            self.vigentes.discard(bytes(nonce))
            return True
        return False


class PruebaRealTests(BaseIdentidad):
    def setUp(self):
        super().setUp()
        self.a, self.b = cargar("emulador_1"), cargar("emulador_2")
        self.s.retos = RetosFijos(self.a["nonce"], self.b["nonce"])
        self.s.atestacion = AtestacionEmpaquetada(firmas_extra="")      # las raíces de Google DEL PAQUETE: ninguna coincide con la del emulador

    def enrolar_real(self, c, hw=None):
        cuerpo = {"nonce": b64(c["nonce"]), "clave_publica": c["clave_publica"], "firma": c["firma"], "cadena": c["cadena"], "proveedor": c["proveedor"]}
        return self.api.post(f"{L}/identidad/enrolar/", {"identificador_hw": hw or c["hw"], "identidad": cuerpo}, format="json")

    def test_el_nodo_acepta_la_firma_de_java_y_deja_al_emulador_en_software(self):
        self.registrar(self.a["hw"])
        r = self.enrolar_real(self.a)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("software", "raiz_desconocida"))
        d = self.equipo(self.a["hw"])
        self.assertEqual((d.garantia, d.clave_huella), ("software", at.huella_de_clave(self.a["spki"])))
        self.assertEqual(d.garantia_detalle["proveedor_declarado"], "software")
        self.assertEqual(d.garantia_detalle["certificados"], 3)

    def test_repetir_la_misma_prueba_es_un_reto_invalido(self):
        self.registrar(self.a["hw"])
        self.assertEqual(self.enrolar_real(self.a).status_code, 200)
        r = self.enrolar_real(self.a)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "reto_invalido"))

    def test_la_prueba_de_una_tableta_no_se_presenta_por_otra(self):
        self.registrar(self.a["hw"])
        self.registrar(self.b["hw"])
        r = self.enrolar_real(self.a, hw=self.b["hw"])                       # la firma ata el reto a la huella de la tableta A
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "identidad_invalida"))
        self.assertEqual(self.equipo(self.b["hw"]).garantia, "declarada")

    def test_las_dos_tabletas_reales_quedan_con_claves_distintas(self):
        self.registrar(self.a["hw"])
        self.registrar(self.b["hw"])
        self.assertEqual(self.enrolar_real(self.a).status_code, 200)
        self.assertEqual(self.enrolar_real(self.b).status_code, 200)
        self.assertNotEqual(self.equipo(self.a["hw"]).clave_huella, self.equipo(self.b["hw"]).clave_huella)
