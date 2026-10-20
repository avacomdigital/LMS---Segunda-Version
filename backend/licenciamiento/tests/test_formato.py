"""
El formato `.avlic` (P-02): lo que se acepta y, sobre todo, lo que se RECHAZA. Cada rechazo se prueba con un archivo FIRMADO CORRECTAMENTE cuando lo que se quiere demostrar es que lo
rechaza la regla de forma (versión, etiqueta crítica, orden…) y no la firma.
"""
from __future__ import annotations

import uuid

from django.test import SimpleTestCase

from licenciamiento.dominio import firma, licencia, solicitud, tlv
from licenciamiento.dominio.errores import LicenciaInvalida
from licenciamiento.dominio.licencia import CONOCIDOS, ILIMITADO, T_AULA, T_HASH_NODO, T_ID, T_SERIE, T_VENCE, Limites
from licenciamiento.dominio.politica import DIA_MS

from . import emisor
from .emisor import AHORA, KID_DEV_1, KID_DEV_2, claves_publicas, emitir, licencia_de_ejemplo, sellar_campos


def motivo(accion) -> str:
    try:
        accion()
    except LicenciaInvalida as error:
        return error.motivo
    raise AssertionError("el archivo debía rechazarse y se aceptó")


class IdaYVueltaTests(SimpleTestCase):
    def test_una_licencia_firmada_se_lee_igual_que_se_escribio(self):
        lic = licencia_de_ejemplo()
        leida = licencia.leer(emitir(lic), claves_publicas())
        self.assertEqual((leida.id, leida.serie, leida.aula, leida.emitida, leida.desde, leida.vence, leida.gracia_dias), (lic.id, 1, "Aula de pruebas", lic.emitida, lic.desde, lic.vence, 30))
        self.assertEqual(leida.limites, lic.limites)
        self.assertEqual(leida.capacidades, frozenset({"*"}))
        self.assertEqual(leida.huella, lic.huella)
        self.assertEqual((leida.tipo, leida.liberacion_pendiente, leida.liberacion_dias, leida.hash_clave_nodo, leida.kid), ("produccion", False, 0, None, KID_DEV_1))
        self.assertEqual(len(leida.sha256), 64)

    def test_una_licencia_mide_menos_de_seiscientos_bytes(self):
        self.assertLess(len(emitir()), 600)

    def test_la_bandera_de_liberacion_pendiente_y_el_hash_del_nodo_viajan(self):
        lic = licencia_de_ejemplo(liberacion_pendiente=True, liberacion_dias=14, hash_clave_nodo=b"\x07" * 32)
        leida = licencia.leer(emitir(lic), claves_publicas())
        self.assertEqual((leida.liberacion_pendiente, leida.liberacion_dias, leida.hash_clave_nodo), (True, 14, b"\x07" * 32))

    def test_sin_tope_y_cero_son_valores_distintos(self):
        leida = licencia.leer(emitir(licencia_de_ejemplo(limites=Limites(ILIMITADO, 0, 0, ILIMITADO))), claves_publicas())
        self.assertEqual(leida.limites, Limites(ILIMITADO, 0, 0, ILIMITADO))

    def test_las_capacidades_se_leen_como_conjunto_y_habilitan(self):
        leida = licencia.leer(emitir(licencia_de_ejemplo(capacidades=frozenset({"reportes", "busqueda"}))), claves_publicas())
        self.assertTrue(leida.habilita("reportes") and leida.habilita("busqueda"))
        self.assertFalse(leida.habilita("importacion"))
        self.assertTrue(licencia.leer(emitir(licencia_de_ejemplo()), claves_publicas()).habilita("lo_que_sea"))     # «*»

    def test_el_mismo_contenido_da_siempre_los_mismos_bytes_mas_la_firma(self):
        a, b = emitir(), emitir()
        self.assertEqual(a, b)               # Ed25519 es determinista: no hay dos archivos «iguales» con bytes distintos

    def test_la_variante_texto_va_y_vuelve_y_es_estricta(self):
        datos = emitir()
        texto = licencia.a_texto(datos)
        self.assertTrue(texto.startswith("AVL1."))
        self.assertEqual(licencia.de_texto(texto), datos)
        self.assertEqual(licencia.leer_texto(texto, claves_publicas()).serie, 1)
        for malo in (texto + " ", " " + texto, texto + "\n", texto + "=", texto[:-1], texto.replace("AVL1.", "AVL2."), texto.lower(), "AVL1.", "AVL1.@@@@", texto[:-1] + "_" if texto[-1] != "_" else texto[:-1] + "-"):
            if malo == texto:
                continue
            with self.assertRaises(LicenciaInvalida, msg=repr(malo[:12] + "…" + malo[-6:])):
                licencia.leer_texto(malo, claves_publicas())

    def test_el_texto_canonico_no_acepta_variantes_del_ultimo_caracter(self):
        """Los bits sobrantes del último carácter base64 tienen que ser cero: otra letra «equivalente» no es otro archivo válido."""
        datos = emitir()
        texto = licencia.a_texto(datos)
        alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        aceptados = [c for c in alfabeto if c != texto[-1] and _acepta(texto[:-1] + c)]
        self.assertEqual(aceptados, [])


def _acepta(texto: str) -> bool:
    try:
        licencia.leer_texto(texto, claves_publicas())
        return True
    except LicenciaInvalida:
        return False


class RechazosDeFormaTests(SimpleTestCase):
    """Todos estos archivos están FIRMADOS por una llave conocida: lo que los rechaza es la regla de forma."""

    def setUp(self):
        self.claves = claves_publicas()
        self.base = licencia.campos_de(licencia_de_ejemplo())

    def leer(self, datos: bytes):
        return licencia.leer(datos, self.claves)

    def test_version_menor_o_mayor_se_rechaza_aunque_este_bien_firmada(self):
        for version in (0, 2, 255, 65535):
            datos = sellar_campos(self.base, version=version, conocidos=CONOCIDOS)
            self.assertEqual(motivo(lambda: self.leer(datos)), "version_no_soportada", version)

    def test_un_kid_desconocido_se_rechaza(self):
        datos = emitir(kid=KID_DEV_2)
        self.assertEqual(motivo(lambda: licencia.leer(datos, claves_publicas(KID_DEV_1))), "kid_desconocido")
        self.assertEqual(self.leer(datos).kid, KID_DEV_2)          # con la llave de rotación a mano, sí

    def test_dos_llaves_conviven_y_cada_licencia_se_verifica_con_la_suya(self):
        for kid in (KID_DEV_1, KID_DEV_2):
            self.assertEqual(self.leer(emitir(kid=kid)).kid, kid)

    def test_una_firma_de_otra_llave_con_un_kid_conocido_se_rechaza(self):
        ajena = firma.par_nuevo()[0]
        datos = sellar_campos(self.base, conocidos=CONOCIDOS, clave=ajena)
        self.assertEqual(motivo(lambda: self.leer(datos)), "firma_invalida")

    def test_una_etiqueta_critica_desconocida_se_rechaza_y_una_no_critica_se_ignora(self):
        campos = {**self.base, 99: b"futuro"}
        critica = sellar_campos(campos, conocidos={**CONOCIDOS, 99: (16, True)})
        self.assertEqual(motivo(lambda: self.leer(critica)), "etiqueta_critica_desconocida")
        # La misma etiqueta, no crítica, la ignora quien no la conoce
        informativa = sellar_campos(campos, conocidos={**CONOCIDOS, 99: (16, False)})
        self.assertEqual(self.leer(informativa).serie, 1)

    def test_una_etiqueta_conocida_con_el_bit_critico_cambiado_se_rechaza(self):
        for numero in (T_SERIE, T_AULA):
            critica_antes = CONOCIDOS[numero][1]
            datos = sellar_campos(self.base | {T_AULA: b"x"}, conocidos={**CONOCIDOS, numero: (CONOCIDOS[numero][0], not critica_antes)})
            self.assertEqual(motivo(lambda: self.leer(datos)), "formato", numero)

    def test_etiquetas_desordenadas_o_repetidas_se_rechazan(self):
        cuerpo = tlv.escribir(tlv.MAGIC_LICENCIA, KID_DEV_1, self.base, CONOCIDOS)
        cabecera = tlv.leer_cabecera(cuerpo + bytes(64), tlv.MAGIC_LICENCIA)
        campos = cuerpo[cabecera.fin:]
        uno = campos[:4 + int.from_bytes(campos[2:4], "big")]
        resto = campos[len(uno):]
        for torcido in (resto + uno, uno + uno + resto):
            datos = tlv.sellar(cuerpo[:cabecera.fin] + torcido, lambda d: firma.firmar(emisor.clave_privada(KID_DEV_1), d))
            self.assertEqual(motivo(lambda: self.leer(datos)), "formato")

    def test_bytes_sobrantes_dentro_de_lo_firmado_se_rechazan(self):
        cuerpo = tlv.escribir(tlv.MAGIC_LICENCIA, KID_DEV_1, self.base, CONOCIDOS)
        for sobrante in (b"\x00", b"\x01\x02\x03", bytes(4)):
            datos = tlv.sellar(cuerpo + sobrante, lambda d: firma.firmar(emisor.clave_privada(KID_DEV_1), d))
            self.assertEqual(motivo(lambda: self.leer(datos)), "formato", sobrante)

    def test_bytes_sobrantes_despues_de_la_firma_se_rechazan(self):
        datos = emitir()
        for extra in (b"\x00", b"basura", bytes(64)):
            self.assertIn(motivo(lambda: self.leer(datos + extra)), ("firma_invalida", "formato", "kid_desconocido"), extra)

    def test_toda_licencia_truncada_se_rechaza(self):
        datos = emitir()
        for largo in range(len(datos)):
            with self.assertRaises(LicenciaInvalida, msg=f"truncada a {largo} bytes"):
                self.leer(datos[:largo])

    def test_un_archivo_demasiado_grande_ni_se_mira(self):
        self.assertEqual(motivo(lambda: self.leer(b"AVLC" + bytes(tlv.MAX_ARCHIVO))), "demasiado_grande")

    def test_el_magic_equivocado_se_rechaza(self):
        datos = bytearray(emitir())
        datos[:4] = b"AVRQ"
        self.assertEqual(motivo(lambda: self.leer(bytes(datos))), "formato")

    def test_campos_obligatorios_y_rangos(self):
        for etiqueta in licencia.OBLIGATORIOS:
            sin = {k: v for k, v in self.base.items() if k != etiqueta}
            self.assertEqual(motivo(lambda: self.leer(sellar_campos(sin, conocidos=CONOCIDOS))), "campo_faltante", etiqueta)
        casos = {
            "serie cero": {T_SERIE: (0).to_bytes(4, "big")},
            "vence antes de desde": {T_VENCE: (AHORA - 40 * DIA_MS).to_bytes(8, "big")},
            "gracia de más de un año": {licencia.T_GRACIA: (366).to_bytes(2, "big")},
            "id con largo equivocado": {T_ID: b"\x01" * 15},
            "tipo desconocido": {licencia.T_TIPO: b"\x09"},
            "concurrentes normal > pico": {licencia.T_LIMITES: b"".join(n.to_bytes(4, "big") for n in (1, 1, 200, 100))},
            "bandera desconocida": {licencia.T_BANDERAS: (2).to_bytes(4, "big") + (0).to_bytes(2, "big")},
            "días de liberación sin bandera": {licencia.T_BANDERAS: (0).to_bytes(4, "big") + (5).to_bytes(2, "big")},
            "aula con salto de línea": {T_AULA: b"Aula\nB"},
            "aula con espacio al borde": {T_AULA: b" Aula"},
            "hash del nodo corto": {T_HASH_NODO: b"\x01" * 31},
        }
        for nombre, cambio in casos.items():
            with self.assertRaises(LicenciaInvalida, msg=nombre):
                self.leer(sellar_campos({**self.base, **cambio}, conocidos=CONOCIDOS))

    def test_capacidades_fuera_de_orden_o_repetidas_o_mal_formadas_se_rechazan(self):
        def lista(*codigos: str) -> bytes:
            return b"".join(bytes([len(c)]) + c.encode() for c in codigos)
        for nombre, valor in {"desordenadas": lista("reportes", "busqueda"), "repetidas": lista("busqueda", "busqueda"), "mayúsculas": lista("Busqueda"),
                              "largo cero": b"\x00", "cortada": b"\x09abc", "con espacio": lista("a b")}.items():
            with self.assertRaises(LicenciaInvalida, msg=nombre):
                self.leer(sellar_campos({**self.base, licencia.T_CAPACIDADES: valor}, conocidos=CONOCIDOS))

    def test_una_huella_mal_formada_se_rechaza(self):
        buena = self.base[licencia.T_HUELLA]
        for nombre, valor in {"k mayor que n": bytes([9]) + buena[1:], "k cero": bytes([0]) + buena[1:], "n no cuadra": buena[:1] + bytes([3]) + buena[2:],
                              "cortada": buena[:-1], "factor repetido": buena[:2] + buena[2:35] + buena[2:35] + buena[68:]}.items():
            with self.assertRaises(LicenciaInvalida, msg=nombre):
                self.leer(sellar_campos({**self.base, licencia.T_HUELLA: valor}, conocidos=CONOCIDOS))


class SolicitudYLiberacionTests(SimpleTestCase):
    def setUp(self):
        self.privada, self.publica = firma.par_nuevo()
        self.huella = emisor.huella_de()

    def solicitud(self, **cambios):
        datos = dict(nonce=b"\x11" * 16, version_nodo="2.9.0", creada=AHORA, nivel="hardware", huella=self.huella, licencia_vigente=None, aula="8A")
        datos.update(cambios)
        return solicitud.construir_solicitud(self.privada, **datos)

    def test_la_solicitud_va_firmada_por_el_nodo_y_el_emisor_la_lee(self):
        leida = solicitud.leer_solicitud(self.solicitud(licencia_vigente=str(uuid.UUID(int=5))))
        self.assertEqual((leida.nonce, leida.version_nodo, leida.creada, leida.nivel, leida.clave_nodo, leida.aula), (b"\x11" * 16, "2.9.0", AHORA, "hardware", self.publica, "8A"))
        self.assertEqual(leida.huella, self.huella)
        self.assertEqual(leida.licencia_vigente, str(uuid.UUID(int=5)))

    def test_la_solicitud_no_lleva_identificadores_crudos_ni_datos_de_personas(self):
        datos = self.solicitud()
        for crudo in (b"BRD-7781", b"4C4C4544", b"9f1c2a3e", b"CH-55", b"BFEBFBFF"):
            self.assertNotIn(crudo, datos)

    def test_alterar_una_solicitud_la_invalida(self):
        datos = bytearray(self.solicitud())
        for i in range(0, len(datos), 7):
            torcida = bytearray(datos)
            torcida[i] ^= 0x01
            with self.assertRaises(LicenciaInvalida, msg=f"byte {i}"):
                solicitud.leer_solicitud(bytes(torcida))

    def test_una_solicitud_no_se_acepta_como_licencia_ni_al_reves(self):
        with self.assertRaises(LicenciaInvalida):
            licencia.leer(self.solicitud(), claves_publicas())
        with self.assertRaises(LicenciaInvalida):
            solicitud.leer_solicitud(emitir())

    def test_la_liberacion_va_y_vuelve(self):
        datos = solicitud.construir_liberacion(self.privada, licencia_id=str(uuid.UUID(int=9)), serie=3, liberada=AHORA, nonce=b"\x22" * 16)
        leida = solicitud.leer_liberacion(datos)
        self.assertEqual((leida.licencia_id, leida.serie, leida.liberada, leida.nonce, leida.clave_nodo), (str(uuid.UUID(int=9)), 3, AHORA, b"\x22" * 16, self.publica))
        torcida = bytearray(datos)
        torcida[20] ^= 0x01
        with self.assertRaises(LicenciaInvalida):
            solicitud.leer_liberacion(bytes(torcida))

    def test_la_variante_texto_de_la_solicitud_usa_su_propio_prefijo(self):
        datos = self.solicitud()
        texto = licencia.a_texto(datos, tlv.MAGIC_SOLICITUD)
        self.assertTrue(texto.startswith("AVQ1."))
        self.assertEqual(licencia.de_texto(texto, tlv.MAGIC_SOLICITUD), datos)
        with self.assertRaises(LicenciaInvalida):
            licencia.de_texto(texto, tlv.MAGIC_LICENCIA)
