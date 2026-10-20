"""
La huella del equipo (P-04): factores con valores basura de placas OEM, coincidencia k de n, huella de instalación y la lectura de la tabla SMBIOS con tablas fabricadas a mano
(incluida la de una placa de panel interactivo que sólo trae relleno de fábrica).
"""
from __future__ import annotations

import uuid

from django.test import SimpleTestCase

from licenciamiento.dominio import huella as h
from licenciamiento.dominio import smbios
from licenciamiento.dominio.licencia import HuellaDeLicencia

from .emisor import factores_de_ejemplo, huella_de

BASURA = (
    "", "   ", None, "0", "00000000", "0000000000000000", "FFFFFFFF", "ffffffffffffffff", "To be filled by O.E.M.", "TO BE FILLED BY O.E.M", "to be filled by oem", "Default string",
    "DEFAULT STRING", "None", "NONE", "Not Specified", "System Serial Number", "Chassis Serial Number", "Base Board Serial Number", "Type2 - Board Serial Number", "N/A", "n/a", "Unknown",
    "123456789", "0123456789", "0123456789ABCDEF", "00000000-0000-0000-0000-000000000000", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF", "03000200-0400-0500-0006-000700080009",
    "{00000000-0000-0000-0000-000000000000}", "abc", "xxxxxxxx", "1111111111", "aaaaaaaa", "System Product Name", "  To   be filled by O.E.M.  ",
)
VALIDOS = ("BRD-7781-ZX-2209", "4C4C4544-0042-3510-8058-B6C04F425A32", "BFEBFBFF000A0671", "CH-55-0192-77", "PF3A0K7Q", "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", "R9-0042", "0123456789ABCDEG")


class BasuraTests(SimpleTestCase):
    def test_los_valores_de_relleno_de_las_placas_oem_no_identifican_a_nadie(self):
        for valor in BASURA:
            self.assertTrue(h.es_basura(valor), repr(valor))

    def test_los_valores_reales_si_cuentan(self):
        for valor in VALIDOS:
            self.assertFalse(h.es_basura(valor), valor)

    def test_un_factor_basura_se_descarta_y_no_llega_al_hash(self):
        crudos = {h.F_MACHINE_GUID: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", h.F_SMBIOS_UUID: "03000200-0400-0500-0006-000700080009", h.F_PLACA: "To be filled by O.E.M.",
                  h.F_CHASIS: "Default string", h.F_PROCESADOR: "BFEBFBFF000A0671", 99: "no es un factor de hardware"}
        validos = h.factores_validos(crudos)
        self.assertEqual(sorted(validos), [h.F_MACHINE_GUID])
        self.assertTrue(all(len(valor) == 32 for valor in validos.values()))

    def test_el_processor_id_no_sella_aunque_sea_valido(self):
        """D-3 (Fase 0): es la firma CPUID del MODELO, igual en todos los equipos del mismo modelo: no identifica una unidad."""
        validos = h.factores_validos({h.F_PROCESADOR: "BFEBFBFF000A0671", h.F_PLACA: "BRD-7781-ZX-2209"})
        self.assertEqual(sorted(validos), [h.F_PLACA])

    def test_el_hash_es_distinto_por_factor_y_estable(self):
        a = h.hash_de_factor(h.F_PLACA, "ABC-1234")
        self.assertEqual(a, h.hash_de_factor(h.F_PLACA, "  abc-1234 "))      # se normaliza: mayúsculas y espacios
        self.assertNotEqual(a, h.hash_de_factor(h.F_CHASIS, "ABC-1234"))      # el mismo valor en otro factor no coincide
        self.assertNotEqual(a, h.hash_de_factor(h.F_PLACA, "ABC-1235"))
        self.assertNotIn(b"ABC-1234", a)

    def test_la_clave_de_producto_cambia_el_hash(self):
        self.assertNotEqual(h.hash_de_factor(h.F_PLACA, "ABC-1234"), h.hash_de_factor(h.F_PLACA, "ABC-1234", clave=b"otra-clave"))


def cambiar(actuales: dict[int, bytes], *factores: int) -> dict[int, bytes]:
    hoy = dict(actuales)
    for factor in factores:
        hoy[factor] = h.hash_de_factor(factor, f"OTRO-VALOR-{factor}")
    return hoy


class MismaHuellaTests(SimpleTestCase):
    """D-10: lo que distingue un traslado (otra huella) de una renovación (la misma)."""

    def test_es_la_misma_si_coinciden_k_y_factores_sin_importar_el_orden(self):
        a = huella_de()
        self.assertTrue(a.es_la_misma(huella_de()))
        self.assertTrue(a.es_la_misma(HuellaDeLicencia(a.k, tuple(reversed(a.factores)))))

    def test_otros_factores_u_otro_k_son_otra_huella(self):
        a = huella_de()
        self.assertFalse(a.es_la_misma(huella_de(factores_de_ejemplo(3))))
        self.assertFalse(a.es_la_misma(HuellaDeLicencia(a.k - 1, a.factores)))


class KDeNTests(SimpleTestCase):
    """Con cuatro factores de unidad: 3 de 4. Con tres: 2 de 3. Con dos: 2 de 2 (un clon y una placa cambiada no se distinguen, así que se exigen los dos)."""

    def setUp(self):
        self.actuales = factores_de_ejemplo(4)
        self.licencia = huella_de(self.actuales)

    def test_la_regla_de_k(self):
        self.assertEqual([h.k_para(n) for n in (2, 3, 4)], [2, 2, 3])
        self.assertEqual(self.licencia.k, 3)

    def test_el_mismo_equipo_coincide_en_todo(self):
        c = h.comparar(self.licencia, self.actuales)
        self.assertEqual((c.k, c.en_licencia, c.coinciden, c.ok, c.parcial, c.nivel), (3, 4, 4, True, False, "hardware"))

    def test_con_cuatro_factores_sobrevive_al_cambio_de_uno_y_lo_dice_pero_no_al_de_dos(self):
        uno = h.comparar(self.licencia, cambiar(self.actuales, h.F_PLACA))
        self.assertTrue(uno.ok and uno.parcial)
        self.assertEqual(uno.coinciden, 3)
        dos = h.comparar(self.licencia, cambiar(self.actuales, h.F_PLACA, h.F_CHASIS))
        self.assertEqual((dos.coinciden, dos.ok), (2, False))

    def test_con_tres_factores_sobrevive_al_cambio_de_un_disco_o_de_un_dato_pero_una_placa_nueva_no(self):
        tres = factores_de_ejemplo(3)                                 # MachineGuid, UUID de SMBIOS y serie de placa
        licencia = huella_de(tres)
        self.assertEqual(licencia.k, 2)
        self.assertTrue(h.comparar(licencia, cambiar(tres, h.F_MACHINE_GUID)).ok)                          # un disco con Windows nuevo: cambia el MachineGuid
        self.assertFalse(h.comparar(licencia, cambiar(tres, h.F_SMBIOS_UUID, h.F_PLACA)).ok)               # una placa nueva: cambian el UUID y la serie

    def test_un_disco_clonado_a_otra_placa_no_pasa(self):
        """El clon conserva el `MachineGuid` (vive en el disco) pero el SMBIOS, la placa y el chasis son los de la máquina nueva."""
        hoy = cambiar(self.actuales, h.F_SMBIOS_UUID, h.F_PLACA, h.F_CHASIS)
        c = h.comparar(self.licencia, hoy)
        self.assertEqual((c.coinciden, c.ok), (1, False))

    def test_con_dos_factores_se_exigen_los_dos(self):
        dos = factores_de_ejemplo(2)                                  # MachineGuid + UUID de SMBIOS: lo que medimos en la máquina de desarrollo
        licencia = huella_de(dos)
        self.assertEqual(licencia.k, 2)
        self.assertTrue(h.comparar(licencia, dos).ok)
        for factor in (h.F_MACHINE_GUID, h.F_SMBIOS_UUID):
            self.assertFalse(h.comparar(licencia, cambiar(dos, factor)).ok, factor)

    def test_k_es_configurable_en_la_licencia(self):
        estricta = huella_de(self.actuales, k=4)
        generosa = huella_de(self.actuales, k=2)
        hoy = cambiar(self.actuales, h.F_PLACA)
        self.assertFalse(h.comparar(estricta, hoy).ok)
        self.assertTrue(h.comparar(generosa, hoy).ok)

    def test_un_equipo_sin_factores_validos_no_coincide_con_una_licencia_de_hardware(self):
        self.assertFalse(h.comparar(self.licencia, {}).ok)


class InstalacionTests(SimpleTestCase):
    def test_con_dos_o_mas_factores_de_unidad_la_solicitud_es_de_hardware_con_todos_ellos(self):
        for n, k_esperado in ((2, 2), (3, 2), (4, 3)):
            validos = factores_de_ejemplo(n)
            nivel, k, factores = h.huella_de_solicitud(validos, b"\x01" * 32)
            self.assertEqual((nivel, k, sorted(factores)), ("hardware", k_esperado, sorted(validos)), n)

    def test_con_menos_de_dos_factores_se_usa_la_huella_de_instalacion_y_nunca_se_niega(self):
        for n in (0, 1):
            validos = dict(list(factores_de_ejemplo(4).items())[:n])
            nivel, k, factores = h.huella_de_solicitud(validos, b"\x09" * 32)
            self.assertEqual((nivel, k, sorted(factores)), ("instalacion", 1, [h.F_INSTALACION]), n)

    def test_un_equipo_con_un_solo_factor_es_un_equipo_de_instalacion_aunque_traiga_el_processor_id(self):
        """Lo que midió la Fase 0 en un panel real: MachineGuid y UUID válidos; series de placa y chasis, «Default string»; ProcessorId válido pero de modelo."""
        crudos = {h.F_MACHINE_GUID: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", h.F_SMBIOS_UUID: "03000200-0400-0500-0006-000700080009", h.F_PLACA: "Default string",
                  h.F_CHASIS: "Default string", h.F_PROCESADOR: "BFEBFBFF000A0671"}
        self.assertEqual(h.huella_de_solicitud(h.factores_validos(crudos), b"\x01" * 32)[0], "instalacion")

    def test_una_licencia_de_instalacion_coincide_con_el_secreto_de_este_nodo_y_con_ningun_otro(self):
        secreto = b"\x42" * 32
        _, k, factores = h.huella_de_solicitud({}, secreto)
        licencia = HuellaDeLicencia(k, tuple(sorted(factores.items())))
        propio = h.hash_de_factor(h.F_INSTALACION, secreto.hex())
        ajeno = h.hash_de_factor(h.F_INSTALACION, (b"\x43" * 32).hex())
        self.assertTrue(h.comparar(licencia, {}, inst_hash=propio).ok)
        self.assertEqual(h.comparar(licencia, {}, inst_hash=propio).nivel, "instalacion")
        self.assertFalse(h.comparar(licencia, {}, inst_hash=ajeno).ok)
        self.assertFalse(h.comparar(licencia, {}, inst_hash=None).ok)

    def test_sin_secreto_de_instalacion_no_hay_huella_posible(self):
        with self.assertRaises(ValueError):
            h.huella_de_solicitud({}, None)

    def test_el_nivel_de_los_factores_actuales(self):
        self.assertEqual(h.nivel_de(factores_de_ejemplo(4)), "hardware")
        self.assertEqual(h.nivel_de(factores_de_ejemplo(2)), "hardware")
        self.assertEqual(h.nivel_de(factores_de_ejemplo(1)), "instalacion")
        self.assertEqual(h.nivel_de({}), "instalacion")


# ------------------------------------------------------------------------------------------------------------------------ SMBIOS
def estructura(tipo: int, formateada: bytes, *cadenas: str) -> bytes:
    area = b"".join(c.encode() + bytes((0,)) for c in cadenas) + bytes((0,)) if cadenas else bytes((0, 0))
    return bytes([tipo, 4 + len(formateada), 0, 0]) + formateada + area


def buffer(*estructuras: bytes) -> bytes:
    tabla = b"".join(estructuras) + estructura(127, b"")
    return bytes([0, 3, 4, 0]) + len(tabla).to_bytes(4, "little") + tabla


GUID = "4C4C4544-0042-3510-8058-B6C04F425A32"


def tabla_real(serie_sistema="PF3A0K7Q", serie_placa="BRD-7781-ZX-2209", serie_chasis="CH-55-0192-77", guid=GUID) -> bytes:
    return buffer(
        estructura(1, bytes([1, 2, 3, 4]) + uuid.UUID(guid).bytes_le + bytes([6]), "ACME", "Panel 86", "1.0", serie_sistema),
        estructura(2, bytes([1, 2, 3, 4, 0, 9, 0, 0, 0, 10, 0]), "ACME", "Board", "A1", serie_placa),
        estructura(3, bytes([1, 3, 3, 4 if serie_chasis else 0, 0, 0, 0, 0, 0, 0]), "ACME", "Series", "B", *([serie_chasis] if serie_chasis else [])),
        estructura(4, bytes([1, 3, 0xC6, 2]) + bytes.fromhex("71060A00FFFBEBBF") + bytes([3]), "SOCKET", "Intel", "CPU"),
    )


class SmbiosTests(SimpleTestCase):
    def test_lee_uuid_series_y_procesador_de_una_tabla_real(self):
        datos = smbios.leer_tabla(tabla_real())
        self.assertEqual(datos, {"smbios_uuid": GUID, "sistema_serie": "PF3A0K7Q", "placa_serie": "BRD-7781-ZX-2209", "chasis_serie": "CH-55-0192-77", "procesador_id": "BFEBFBFF000A0671"})

    def test_una_placa_de_panel_con_puro_relleno_de_fabrica_deja_un_solo_factor_valido(self):
        datos = smbios.leer_tabla(tabla_real("System Serial Number", "To be filled by O.E.M.", "Default string", "03000200-0400-0500-0006-000700080009"))
        crudos = smbios.factores(datos, machine_guid="9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01")
        validos = h.factores_validos(crudos)
        self.assertEqual(sorted(validos), [h.F_MACHINE_GUID])             # el ProcessorId (válido) no sella; las series y el UUID de relleno se descartan
        self.assertEqual(h.nivel_de(validos), "instalacion")            # se usa la huella de instalación y nadie se queda sin poder activar

    def test_el_chasis_cae_al_numero_de_serie_del_sistema_si_no_trae_el_suyo(self):
        datos = smbios.leer_tabla(tabla_real(serie_chasis=""))
        self.assertEqual(smbios.factores(datos)[h.F_CHASIS], "PF3A0K7Q")

    def test_una_tabla_rota_o_vacia_no_lanza(self):
        for roto in (b"", b"\x00" * 7, b"\x00\x03\x04\x00\xff\xff\xff\xff" + b"\x01\x02", tabla_real()[:30], tabla_real()[:-7], bytes([0, 3, 4, 0]) + (500).to_bytes(4, "little") + b"\x01\x04\x00\x00"):
            datos = smbios.leer_tabla(roto)
            self.assertEqual(set(datos), {"smbios_uuid", "sistema_serie", "placa_serie", "chasis_serie", "procesador_id"})

    def test_los_ceros_son_basura_aunque_vengan_como_uuid_valido(self):
        datos = smbios.leer_tabla(tabla_real(guid="00000000-0000-0000-0000-000000000000"))
        self.assertTrue(h.es_basura(datos["smbios_uuid"]))
