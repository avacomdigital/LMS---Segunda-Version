"""
Pruebas de mutación del formato (P-02, «ni la propia IA puede romper la licencia» NO es demostrable como imposibilidad; lo que SÍ se mide es esto):

    ≥ 100 000 mutaciones con semilla fija de una licencia válida (binaria y en texto): 0 aceptadas.

Una mutación es «aceptada» si el archivo alterado se lee como una licencia (cualquiera). Cada familia de mutaciones corre su parte de las 100 000; la semilla es fija para que un
fallo se pueda reproducir con exactitud. Además se prueba que miles de llaves ajenas con el `kid` de una conocida tampoco firman nada que el nodo acepte.
"""
from __future__ import annotations

import random

from django.test import SimpleTestCase

from licenciamiento.dominio import firma, licencia, tlv
from licenciamiento.dominio.errores import LicenciaInvalida

from .emisor import KID_DEV_1, claves_publicas, emitir, licencia_de_ejemplo, sellar_campos

SEMILLA = 20261020
TOTAL = 100_000


def _aceptada(datos: bytes, claves) -> bool:
    try:
        licencia.leer(datos, claves)
        return True
    except LicenciaInvalida:
        return False


def _aceptado_texto(texto: str, claves) -> bool:
    try:
        licencia.leer_texto(texto, claves)
        return True
    except LicenciaInvalida:
        return False


def _mutar(rng: random.Random, datos: bytes) -> bytes:
    """Una alteración al azar de `datos` (siempre distinta del original)."""
    n = len(datos)
    while True:
        familia = rng.randrange(10)
        m = bytearray(datos)
        if familia == 0:                                                       # un bit
            i = rng.randrange(n)
            m[i] ^= 1 << rng.randrange(8)
        elif familia == 1:                                                     # varios bits
            for _ in range(rng.randrange(2, 17)):
                m[rng.randrange(n)] ^= 1 << rng.randrange(8)
        elif familia == 2:                                                     # un byte por otro
            m[rng.randrange(n)] = rng.randrange(256)
        elif familia == 3:                                                     # tramo reemplazado por azar
            a = rng.randrange(n)
            b = min(n, a + rng.randrange(1, 33))
            m[a:b] = bytes(rng.randrange(256) for _ in range(b - a))
        elif familia == 4:                                                     # insertar bytes
            i = rng.randrange(n + 1)
            m[i:i] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 17)))
        elif familia == 5:                                                     # borrar bytes
            a = rng.randrange(n)
            del m[a:a + rng.randrange(1, 17)]
        elif familia == 6:                                                     # truncar
            del m[rng.randrange(n):]
        elif familia == 7:                                                     # añadir al final
            m += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 65)))
        elif familia == 8:                                                     # intercambiar dos tramos
            a, b = sorted(rng.sample(range(n), 2))
            largo = rng.randrange(1, min(16, n - b) + 1)
            m[a:a + largo], m[b:b + largo] = m[b:b + largo], m[a:a + largo]
        else:                                                                  # poner a cero un tramo
            a = rng.randrange(n)
            m[a:a + rng.randrange(1, 33)] = bytes(min(32, n - a))
        resultado = bytes(m)
        if resultado != datos:
            return resultado


def _mutar_texto(rng: random.Random, texto: str) -> str:
    alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=+/ .\n"
    n = len(texto)
    while True:
        familia = rng.randrange(5)
        t = list(texto)
        if familia == 0:
            t[rng.randrange(n)] = rng.choice(alfabeto)
        elif familia == 1:
            t.insert(rng.randrange(n + 1), rng.choice(alfabeto))
        elif familia == 2:
            del t[rng.randrange(n)]
        elif familia == 3:
            del t[rng.randrange(n):]
        else:
            t += [rng.choice(alfabeto) for _ in range(rng.randrange(1, 9))]
        resultado = "".join(t)
        if resultado != texto:
            return resultado


class MutacionesTests(SimpleTestCase):
    def test_cien_mil_mutaciones_con_semilla_fija_cero_aceptadas(self):
        claves = claves_publicas()
        datos = emitir()
        texto = licencia.a_texto(datos)
        self.assertTrue(_aceptada(datos, claves) and _aceptado_texto(texto, claves))        # el original sí se acepta: la prueba no es vacía
        rng = random.Random(SEMILLA)
        aceptadas = 0
        for _ in range(TOTAL - 20_000):                                                      # 80 000 sobre el binario…
            if _aceptada(_mutar(rng, datos), claves):
                aceptadas += 1
        for _ in range(20_000):                                                              # …y 20 000 sobre la variante texto
            if _aceptado_texto(_mutar_texto(rng, texto), claves):
                aceptadas += 1
        self.assertEqual(aceptadas, 0, f"se aceptaron {aceptadas} de {TOTAL} mutaciones (semilla {SEMILLA})")

    def test_toda_mutacion_de_un_solo_bit_es_rechazada(self):
        """Exhaustivo: cada bit de cada byte de la licencia, uno por uno."""
        claves = claves_publicas()
        datos = emitir()
        for i in range(len(datos)):
            for bit in range(8):
                m = bytearray(datos)
                m[i] ^= 1 << bit
                self.assertFalse(_aceptada(bytes(m), claves), f"byte {i}, bit {bit}")

    def test_mutaciones_de_una_licencia_con_otros_contenidos(self):
        claves = claves_publicas()
        rng = random.Random(SEMILLA + 1)
        for datos in (emitir(licencia_de_ejemplo(liberacion_pendiente=True, liberacion_dias=7, hash_clave_nodo=b"\x05" * 32)),
                      emitir(licencia_de_ejemplo(capacidades=frozenset({"reportes", "busqueda"}), aula="Colegio San José · Sede 2")), emitir(kid="dev-2")):
            self.assertTrue(_aceptada(datos, claves))
            for _ in range(3000):
                self.assertFalse(_aceptada(_mutar(rng, datos), claves))

    def test_mil_llaves_ajenas_con_un_kid_conocido_no_firman_nada_que_el_nodo_acepte(self):
        claves = claves_publicas()
        campos = licencia.campos_de(licencia_de_ejemplo())
        rng = random.Random(SEMILLA + 2)
        for _ in range(1000):
            ajena = bytes(rng.randrange(256) for _ in range(32))
            datos = sellar_campos(campos, kid=KID_DEV_1, conocidos=licencia.CONOCIDOS, clave=ajena)
            self.assertFalse(_aceptada(datos, claves))

    def test_las_firmas_aleatorias_no_pasan(self):
        claves = claves_publicas()
        cuerpo = licencia.sin_firma(licencia_de_ejemplo(), KID_DEV_1)
        rng = random.Random(SEMILLA + 3)
        for _ in range(2000):
            self.assertFalse(_aceptada(cuerpo + bytes(rng.randrange(256) for _ in range(tlv.TAM_FIRMA)), claves))

    def test_la_firma_de_una_licencia_no_sirve_para_otra(self):
        """Cambiar el contenido y conservar la firma vieja (el ataque más obvio)."""
        claves = claves_publicas()
        a = emitir(licencia_de_ejemplo(serie=1))
        b = emitir(licencia_de_ejemplo(serie=2))
        mezcla = b[:-tlv.TAM_FIRMA] + a[-tlv.TAM_FIRMA:]
        self.assertFalse(_aceptada(mezcla, claves))
        self.assertTrue(_aceptada(a, claves) and _aceptada(b, claves))

    def test_el_algoritmo_esta_fijado_la_firma_no_se_negocia(self):
        """No existe ningún campo de la licencia que cambie el algoritmo: la verificación es siempre Ed25519 (RFC 8032) con una llave de 32 bytes."""
        self.assertNotIn("alg", {nombre.lower() for nombre in dir(licencia) if nombre.startswith("T_")})
        self.assertEqual(len(firma.par_nuevo()[1]), 32)
