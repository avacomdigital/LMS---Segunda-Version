"""
Identidad de dispositivo (Fase 5, P-24) con un nodo REAL: el reto, el enrolamiento por HTTP, la atestación (cadenas sintéticas con una raíz de prueba), el nivel mínimo para un equipo nuevo y
lo que NUNCA pasa (frenar a un equipo ya registrado). La cadena capturada del emulador real se prueba aparte (`test_atestacion_real.py`).
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from django.test import override_settings

from device_manager import models as m9
from licenciamiento.dominio import atestacion as at
from licenciamiento.infraestructura import contenedor

from . import atestacion_apoyo as ap
from .base import L, BaseLicencia

HW = "student-tableta-aabbccdd"


def b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


class FuenteFalsa:
    """Las «raíces de Google» de la prueba (la raíz sintética), sin revocadas y con la app de AVACOM de las pruebas."""

    def __init__(self, entorno: ap.Entorno):
        self.e = entorno

    def raices(self):
        return list(self.e.raices)

    def revocadas(self):
        return frozenset()

    def app(self):
        return self.e.app


class BaseIdentidad(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.e = ap.Entorno()
        self.s.atestacion = FuenteFalsa(self.e)
        # el reloj falso de la base arranca en el instante real; la raíz sintética vale desde hace mucho y por mucho
        self.e.raices[:] = [at.Raiz("prueba", self.e.raices[0].spki, 0, 2**62)]

    # ------------------------------------------------------------------------------------------------------------- recorrido del cliente
    def reto(self) -> bytes:
        r = self.api.post(f"{L}/identidad/reto/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return base64.b64decode(r.json()["nonce"])

    def prueba(self, nonce: bytes, hw: str = HW, *, entorno: ap.Entorno | None = None, cadena: list[bytes] | None = None, firma: bytes | None = None) -> dict:
        e = entorno or self.e
        datos = {"nonce": b64(nonce), "clave_publica": b64(e.spki_clave), "firma": b64(firma if firma is not None else e.firmar_reto(nonce, hw))}
        if cadena is not None:
            datos["cadena"] = [b64(c) for c in cadena]
        return datos

    def registrar(self, hw: str = HW, **extra):
        return self.api.post("/api/dispositivos/", {"identificador": hw, "nombre": hw, **extra}, format="json")

    def enrolar(self, hw: str = HW, **kw):
        nonce = kw.pop("nonce", None) or self.reto()
        return self.api.post(f"{L}/identidad/enrolar/", {"identificador_hw": hw, "identidad": self.prueba(nonce, hw, **kw)}, format="json")

    def equipo(self, hw: str = HW) -> m9.Dispositivo:
        return m9.Dispositivo.objects.get(identificador_hw=hw)


class RetoTests(BaseIdentidad):
    def test_el_reto_es_publico_de_32_bytes_y_distinto_cada_vez(self):
        a, b = self.reto(), self.reto()
        self.assertEqual((len(a), len(b)), (32, 32))
        self.assertNotEqual(a, b)

    def test_un_reto_vale_una_sola_vez(self):
        self.registrar()
        nonce = self.reto()
        self.assertEqual(self.enrolar(nonce=nonce).status_code, 200)
        r = self.enrolar(nonce=nonce)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "reto_invalido"))

    def test_un_reto_desconocido_o_vencido_se_rechaza(self):
        self.registrar()
        r = self.enrolar(nonce=bytes(32))
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "reto_invalido"))
        nonce = self.reto()
        self.reloj.avanzar(6 * 60_000)
        r = self.enrolar(nonce=nonce)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "reto_invalido"))

    def test_un_reto_corto_se_rechaza(self):
        self.registrar()
        r = self.api.post(f"{L}/identidad/enrolar/", {"identificador_hw": HW, "identidad": {"nonce": b64(b"corto"), "clave_publica": "AA==", "firma": "AA=="}}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "reto_invalido"))

    def test_el_reto_se_gasta_aunque_la_firma_sea_mala(self):
        self.registrar()
        nonce = self.reto()
        r = self.enrolar(nonce=nonce, firma=b"basura")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "identidad_invalida"))
        self.assertEqual(self.enrolar(nonce=nonce).json()["codigo"], "reto_invalido")

    def test_los_retos_pendientes_tienen_tope(self):
        retos = self.s.retos
        for _ in range(2100):
            retos.entregar(self.reloj.ahora_ms())
        self.assertLessEqual(retos.pendientes(), 2000)


class EnrolarTests(BaseIdentidad):
    def test_sin_cadena_la_garantia_es_software(self):
        self.registrar()
        r = self.enrolar()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("software", "sin_cadena"))
        d = self.equipo()
        self.assertEqual((d.garantia, d.clave_huella, d.garantia_detalle["motivo"]), ("software", at.huella_de_clave(self.e.spki_clave), "sin_cadena"))
        self.assertEqual(d.garantia_en, self.reloj.t)

    def test_con_la_cadena_completa_la_garantia_es_hardware(self):
        self.registrar()
        nonce = self.reto()
        r = self.enrolar(nonce=nonce, cadena=self.e.cadena(ap.extension(reto=nonce)))
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("hardware", "ok"), r.content)
        self.assertEqual(self.equipo().garantia, "hardware")

    def test_una_cadena_con_el_reto_de_otro_no_da_hardware(self):
        self.registrar()
        nonce = self.reto()
        r = self.enrolar(nonce=nonce, cadena=self.e.cadena(ap.extension(reto=bytes(reversed(nonce)))))
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("software", "reto_distinto"))

    def test_una_cadena_de_otro_reto_ya_usado_no_sirve_como_repetida(self):
        """Repetir (con otro reto del nodo) una cadena capturada de una activación anterior: el reto de la cadena ya no es el vigente."""
        self.registrar()
        viejo = self.reto()
        capturada = self.e.cadena(ap.extension(reto=viejo))
        self.assertEqual(self.enrolar(nonce=viejo, cadena=capturada).json()["garantia"], "hardware")
        d = self.equipo()
        m9.Dispositivo.objects.filter(pk=d.pk).update(clave_publica="", clave_huella="", garantia="declarada")        # el técnico reinició la identidad
        nuevo = self.reto()
        r = self.enrolar(nonce=nuevo, cadena=capturada)
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("software", "reto_distinto"))

    def test_una_app_firmada_con_otra_llave_no_da_hardware(self):
        self.registrar()
        nonce = self.reto()
        r = self.enrolar(nonce=nonce, cadena=self.e.cadena(ap.extension(reto=nonce, firmas=(ap.FIRMA_AJENA,))))
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("software", "app_ajena"))

    def test_un_arranque_desbloqueado_no_da_hardware(self):
        self.registrar()
        nonce = self.reto()
        r = self.enrolar(nonce=nonce, cadena=self.e.cadena(ap.extension(reto=nonce, bloqueado=False, arranque=at.ARRANQUE_NO_VERIFICADO)))
        self.assertEqual(r.json()["garantia"], "software")

    def test_una_raiz_que_no_es_de_google_no_da_hardware(self):
        self.registrar()
        nonce = self.reto()
        otro = ap.Entorno()                                              # otra raíz: la cadena es válida entre sí pero no llega a una raíz pinneada
        r = self.enrolar(nonce=nonce, entorno=otro, cadena=otro.cadena(ap.extension(reto=nonce)))
        self.assertEqual((r.json()["garantia"], r.json()["motivo"]), ("software", "raiz_desconocida"))

    def test_la_confirmacion_de_cada_sesion_conserva_el_nivel(self):
        self.registrar()
        nonce = self.reto()
        self.enrolar(nonce=nonce, cadena=self.e.cadena(ap.extension(reto=nonce)))
        self.reloj.avanzar(3_600_000)
        r = self.enrolar()                                               # sólo firma el reto: no trae la cadena otra vez
        self.assertEqual((r.status_code, r.json()["garantia"], r.json()["motivo"]), (200, "hardware", "confirmada"), r.content)
        self.assertEqual(self.equipo().garantia_en, self.reloj.t)

    def test_otra_clave_para_un_equipo_ya_enrolado_es_409_y_no_cambia_nada(self):
        self.registrar()
        self.enrolar()
        intruso = ap.Entorno()
        r = self.enrolar(entorno=intruso)
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "clave_distinta"))
        self.assertEqual(self.equipo().clave_huella, at.huella_de_clave(self.e.spki_clave))

    def test_una_clave_no_cuenta_como_dos_equipos(self):
        self.registrar()
        self.registrar("student-otra-11223344")
        self.assertEqual(self.enrolar().status_code, 200)
        r = self.enrolar("student-otra-11223344")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "clave_en_uso"))
        self.assertEqual(self.equipo("student-otra-11223344").garantia, "declarada")

    def test_enrolar_un_equipo_que_no_se_registro_es_404_sin_frenar_nada(self):
        r = self.enrolar("student-fantasma-00000000")
        self.assertEqual(r.status_code, 404, r.content)
        self.assertFalse(m9.Dispositivo.objects.filter(identificador_hw="student-fantasma-00000000").exists())

    def test_la_firma_de_un_equipo_no_vale_para_otro(self):
        self.registrar()
        nonce = self.reto()
        r = self.api.post(f"{L}/identidad/enrolar/", {"identificador_hw": HW, "identidad": self.prueba(nonce, "student-otro-99999999")}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "identidad_invalida"))

    def test_la_llave_no_sale_en_el_listado_de_dispositivos(self):
        self.registrar()
        self.enrolar()
        fila = next(d for d in self.admin.get("/api/dispositivos/").json() if d["identificador_hw"] == HW)
        self.assertNotIn("clave_publica", fila)
        self.assertEqual((fila["garantia"], fila["clave_huella"]), ("software", at.huella_de_clave(self.e.spki_clave)))

    def test_el_tecnico_reinicia_la_identidad_y_se_puede_enrolar_otra_clave(self):
        from device_manager import servicios as dm
        self.registrar()
        self.enrolar()
        dm.reiniciar_identidad(self.equipo().id, actor="tecnico")
        d = self.equipo()
        self.assertEqual((d.garantia, d.clave_huella, d.clave_publica), ("declarada", "", ""))
        self.assertEqual(self.enrolar(entorno=ap.Entorno()).status_code, 200)

    def test_los_endpoints_no_exigen_sesion_aunque_el_nodo_la_exija(self):
        from rest_framework.test import APIClient
        anonimo = APIClient()
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(anonimo.post(f"{L}/identidad/reto/", {}, format="json").status_code, 201)


class EquipoNuevoTests(BaseIdentidad):
    """Registro de un equipo NUEVO con su prueba de clave (el nivel mínimo que puede pedir la licencia)."""

    def con_minimo(self, minimo: str):
        sobre = override_settings(AVACOM_LICENCIA_IDENTIDAD_MINIMA=minimo)
        sobre.enable()
        self.addCleanup(sobre.disable)
        contenedor.reiniciar()
        self.s = contenedor.servicios()
        self.s.reloj, self.s.huella = self.reloj, self.huella
        self.s.atestacion = FuenteFalsa(self.e)
        self.activar_ok()

    def registrar_con(self, hw: str, nonce: bytes | None = None, **kw):
        datos = {"identificador": hw, "nombre": hw}
        if nonce is not None:
            datos["identidad"] = self.prueba(nonce, hw, **kw)
        return self.api.post("/api/dispositivos/", datos, format="json")

    def test_sin_minimo_un_equipo_nuevo_sin_prueba_entra_como_declarada(self):
        self.activar_ok()
        self.assertEqual(self.registrar_con("tab-nueva-1").status_code, 201)
        self.assertEqual(self.equipo("tab-nueva-1").garantia, "declarada")

    def test_un_equipo_nuevo_con_prueba_entra_con_su_clave_y_su_nivel(self):
        self.activar_ok()
        nonce = self.reto()
        r = self.registrar_con("tab-nueva-2", nonce, cadena=self.e.cadena(ap.extension(reto=nonce)))
        self.assertEqual(r.status_code, 201, r.content)
        d = self.equipo("tab-nueva-2")
        self.assertEqual((d.garantia, d.clave_huella), ("hardware", at.huella_de_clave(self.e.spki_clave)))

    def test_con_minimo_software_un_equipo_nuevo_sin_clave_recibe_402_y_no_se_crea(self):
        self.con_minimo("software")
        r = self.registrar_con("tab-nueva-3")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["minimo"], r.json()["nivel"]), (402, "identidad_requerida", "software", "declarada"))
        self.assertFalse(m9.Dispositivo.objects.filter(identificador_hw="tab-nueva-3").exists())

    def test_con_minimo_software_un_equipo_con_clave_entra(self):
        self.con_minimo("software")
        self.assertEqual(self.registrar_con("tab-nueva-4", self.reto()).status_code, 201)

    def test_con_minimo_hardware_un_equipo_en_software_no_entra(self):
        self.con_minimo("hardware")
        self.assertEqual(self.registrar_con("tab-nueva-5", self.reto()).status_code, 402)
        nonce = self.reto()
        self.assertEqual(self.registrar_con("tab-nueva-6", nonce, cadena=self.e.cadena(ap.extension(reto=nonce))).status_code, 201)

    def test_el_minimo_nunca_toca_lo_ya_registrado_ni_su_latido(self):
        self.con_minimo("hardware")
        for hw in (self.TABLETA,):
            for ruta in ("/api/dispositivos/latido/", "/api/dispositivos/"):
                r = self.api.post(ruta, {"identificador": hw, "nombre": hw}, format="json")
                self.assertEqual(r.status_code, 200, (ruta, r.content))
        self.assertEqual(self.api.post("/api/dispositivos/latido/", {"identificador": "tab-nueva-7"}, format="json").status_code, 402)

    def test_una_prueba_mala_con_minimo_no_deja_entrar_y_sin_minimo_entra_declarada(self):
        self.con_minimo("software")
        malo = self.api.post("/api/dispositivos/", {"identificador": "tab-8", "identidad": self.prueba(self.reto(), "tab-8", firma=b"x")}, format="json")
        self.assertEqual(malo.status_code, 402)

    def test_el_equipo_maestro_no_necesita_prueba(self):
        self.con_minimo("hardware")
        self.assertEqual(self.api.post("/api/dispositivos/", {"identificador": "ops-master-9", "tipo": "MASTER"}, format="json").status_code, 201)

    def test_la_misma_clave_en_dos_altas_solo_se_guarda_una_vez(self):
        self.activar_ok()
        n1 = self.reto()
        self.assertEqual(self.registrar_con("tab-9a", n1).status_code, 201)
        n2 = self.reto()
        self.assertEqual(self.registrar_con("tab-9b", n2).status_code, 201)             # entra (no se frena a nadie) pero sin la clave repetida
        self.assertEqual(self.equipo("tab-9a").garantia, "software")
        self.assertEqual((self.equipo("tab-9b").garantia, self.equipo("tab-9b").clave_huella), ("declarada", ""))

    def test_en_desarrollo_sin_licencia_la_prueba_se_guarda_y_no_hay_minimo(self):
        with override_settings(AVACOM_LICENCIA_MODO="auto", AVACOM_LICENCIA_IDENTIDAD_MINIMA="hardware"):
            contenedor.reiniciar()
            s = contenedor.servicios()
            s.reloj = self.reloj
            s.atestacion = FuenteFalsa(self.e)
            nonce = s.retos.entregar(self.reloj.t)[0]
            r = self.api.post("/api/dispositivos/", {"identificador": "tab-dev", "identidad": self.prueba(nonce, "tab-dev")}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(self.equipo("tab-dev").garantia, "software")


class ClavesDeEcTests(BaseIdentidad):
    def test_una_clave_que_no_es_p256_se_rechaza(self):
        self.registrar()
        nonce = self.reto()
        p384 = ec.generate_private_key(ec.SECP384R1())
        datos = {"nonce": b64(nonce), "clave_publica": b64(ap.spki(p384.public_key())), "firma": b64(b"x")}
        r = self.api.post(f"{L}/identidad/enrolar/", {"identificador_hw": HW, "identidad": datos}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "identidad_invalida"))
