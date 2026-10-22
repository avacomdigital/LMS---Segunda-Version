"""
Pruebas de mutación del formato `.avupd` (Fase 1, A1): «un byte cambiado en el manifiesto, en un archivo o en el relleno» NO se acepta.

    ≥ 100 000 mutaciones con semilla fija de un paquete válido: 0 aceptadas.

Tres familias, porque cada una ataca una defensa distinta:
  · bytes del contenedor (70 000): un bit, varios, un byte, un tramo, insertar, borrar, truncar, añadir, intercambiar, poner a cero → la estructura estricta, el CRC, la firma o el SHA;
  · el manifiesto reempaquetado con su firma ORIGINAL (20 000): cualquier cambio dentro del JSON firmado → la firma;
  · un archivo reempaquetado con el manifiesto y la firma originales (10 000): cualquier cambio en el contenido → el tamaño o el SHA-256 del manifiesto.

Una mutación es «aceptada» si `verificar` devuelve un paquete. La semilla es fija para que un fallo se reproduzca con exactitud. Además, miles de llaves ajenas con el `kid` de una
conocida tampoco firman nada que el nodo acepte.
"""
from __future__ import annotations

import random

from django.test import SimpleTestCase

from actualizacion.dominio import firma, manifiesto as mf, paquete
from actualizacion.dominio.errores import PaqueteRechazado

from . import emisor
from .emisor import KID_DEV_1, archivos_de_ejemplo, claves_publicas, emitir, empaquetar, manifiesto_de_ejemplo

SEMILLA = 20261021
TOTAL = 100_000
CUOTAS = {"contenedor": 70_000, "manifiesto": 20_000, "archivo": 10_000}


def _aceptada(datos: bytes, claves) -> bool:
    try:
        paquete.verificar(datos, claves)
        return True
    except PaqueteRechazado:
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
        elif familia == 7:                                                     # añadir al final (relleno)
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


class MutacionesTests(SimpleTestCase):
    def test_cien_mil_mutaciones_y_ninguna_se_acepta(self):
        rng = random.Random(SEMILLA)
        claves = claves_publicas()
        archivos = archivos_de_ejemplo()
        m = manifiesto_de_ejemplo(archivos)
        manifiesto_bytes = mf.escribir(m)
        sello = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), manifiesto_bytes)
        valido = empaquetar(manifiesto_bytes, sello, archivos)
        self.assertEqual(valido, emitir())
        self.assertTrue(_aceptada(valido, claves))
        aceptadas: list[tuple[str, int]] = []
        # 1 · bytes del contenedor
        for i in range(CUOTAS["contenedor"]):
            if _aceptada(_mutar(rng, valido), claves):
                aceptadas.append(("contenedor", i))
        # 2 · el manifiesto cambiado y reempaquetado con la firma original
        for i in range(CUOTAS["manifiesto"]):
            if _aceptada(empaquetar(_mutar(rng, manifiesto_bytes), sello, archivos), claves):
                aceptadas.append(("manifiesto", i))
        # 3 · un archivo cambiado y reempaquetado con el manifiesto y la firma originales
        rutas = list(archivos)
        for i in range(CUOTAS["archivo"]):
            ruta = rng.choice(rutas)
            if _aceptada(empaquetar(manifiesto_bytes, sello, {**archivos, ruta: _mutar(rng, archivos[ruta])}), claves):
                aceptadas.append(("archivo", i))
        self.assertEqual(sum(CUOTAS.values()), TOTAL)
        self.assertEqual(aceptadas, [])

    def test_mil_llaves_ajenas_con_el_kid_de_una_conocida(self):
        claves = claves_publicas()
        archivos = archivos_de_ejemplo()
        manifiesto_bytes = mf.escribir(manifiesto_de_ejemplo(archivos))
        for _ in range(1_000):
            privada, _publica = firma.par_nuevo()
            self.assertFalse(_aceptada(empaquetar(manifiesto_bytes, firma.sellar(KID_DEV_1, privada, manifiesto_bytes), archivos), claves))

    def test_la_firma_de_un_manifiesto_no_vale_para_otro(self):
        """Reutilizar una firma válida con otro manifiesto (un paquete viejo con uno nuevo) no pasa."""
        archivos = archivos_de_ejemplo()
        a = mf.escribir(manifiesto_de_ejemplo(archivos))
        b = mf.escribir(manifiesto_de_ejemplo(archivos, serie=0) if False else manifiesto_de_ejemplo(archivos, nombre="Otro paquete"))
        sello_a = firma.sellar(KID_DEV_1, emisor.clave_privada(KID_DEV_1), a)
        self.assertFalse(_aceptada(empaquetar(b, sello_a, archivos), claves_publicas()))
        self.assertTrue(_aceptada(empaquetar(a, sello_a, archivos), claves_publicas()))
