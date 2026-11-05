"""
Fase 4 · la biblioteca nativa `avacom_lic` contra su gemelo de referencia (P-20, P-22).

  · Carga: por ruta ABSOLUTA, con ABI y autoprueba; ninguna ruta sale del directorio actual ni del PATH; un nodo de producción no lee `AVACOM_LIC_NATIVA`.
  · Diferencial: ≥ 10 000 casos aleatorios con semilla fija (licencias válidas y alteradas-y-vueltas-a-firmar, firmas, huella, SMBIOS, solicitudes, ancla del reloj, HKDF, XChaCha). La nativa y la
    referencia deben dar el MISMO veredicto, el mismo motivo de rechazo y los mismos bytes.
  · Respaldo: sin la biblioteca (renombrada, ABI distinta, falla una llamada) el nodo sigue por la referencia, con registro y con UN asiento de integridad; la clase nunca se detiene.
  · Tiempo: cargar + autoprueba ≤ 200 ms (P-20: «arranque del backend y validación de licencia ≤ +200 ms»).

Si la biblioteca no está compilada (`native/avacom-lic/Build-Native.ps1`; los binarios no se versionan) las pruebas que la necesitan se OMITEN y lo dicen; las del respaldo corren siempre.
"""
from __future__ import annotations

import os
import random
import shutil
import struct
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from licenciamiento.dominio import firma, huella as hu, licencia as lic_mod, tlv
from licenciamiento.dominio.errores import LicenciaInvalida
from licenciamiento.dominio.licencia import HuellaDeLicencia, Limites
from licenciamiento.infraestructura import nativo
from licenciamiento.infraestructura.nativo import Biblioteca, FactoresActuales, Nativa, NativaNoDisponible, Referencia

from . import emisor
from .base import BaseLicencia

SEMILLA = 20261022
DIA = 86_400_000
_NATIVA = nativo.cargar("pruebas")
HAY_NATIVA = _NATIVA.activa
MOTIVO_OMISION = "avacom_lic no está compilada: ejecuta native/avacom-lic/Build-Native.ps1 (los binarios no se versionan)"
REF = Referencia()


def _intento(f):
    try:
        return "ok", f()
    except LicenciaInvalida as error:
        return "error", error.motivo


# --------------------------------------------------------------------------------------------------------------------------- generadores
def _huella_aleatoria(rng: random.Random) -> HuellaDeLicencia:
    n = rng.randrange(1, 9)
    factores = sorted(rng.sample(range(1, 33), n))
    return HuellaDeLicencia(rng.randrange(1, n + 1), tuple((f, rng.randbytes(32)) for f in factores))


def _licencia_aleatoria(rng: random.Random, ahora: int):
    desde = ahora - rng.randrange(-3, 400) * DIA - rng.randrange(0, DIA)
    normal = rng.randrange(1, 120)
    pendiente = rng.random() < 0.15
    caps = frozenset(rng.sample(["*", "reportes", "busqueda", "importacion", "administracion_avanzada", "x", "a_b_c", "0123"], rng.randrange(1, 5)))
    return emisor.licencia_de_ejemplo(
        id=str(uuid.UUID(int=rng.getrandbits(128), version=4)), serie=rng.randrange(1, 2**32 - 1), aula=rng.choice(["", "Aula de pruebas", "Aula ñandú 3", "Sala B", "日本語の教室", "x" * 120]),
        emitida=desde - DIA, desde=desde, vence=desde + rng.randrange(1, 700) * DIA, gracia_dias=rng.randrange(0, 366),
        limites=Limites(rng.randrange(1, 2**32 - 1), rng.randrange(1, 2**32 - 1), normal, normal + rng.randrange(0, 2**32 - 1 - normal)), capacidades=caps,
        huella=_huella_aleatoria(rng), tipo=rng.choice([lic_mod.TIPO_PRODUCCION, lic_mod.TIPO_EVALUACION, lic_mod.TIPO_DESARROLLO]),
        liberacion_pendiente=pendiente, liberacion_dias=(rng.randrange(0, 366) if pendiente else 0), hash_clave_nodo=(rng.randbytes(32) if rng.random() < 0.3 else None))


def _actuales_aleatorios(rng: random.Random, lic: lic_mod.Licencia) -> FactoresActuales | None:
    if rng.random() < 0.2:
        return None
    factores: dict[int, bytes] = {}
    instalacion = None
    for f, h in lic.huella.factores:
        r = rng.random()
        if f == hu.F_INSTALACION:
            instalacion = h if r < 0.6 else rng.randbytes(32)
        elif r < 0.55:
            factores[f] = h
        elif r < 0.8:
            factores[f] = rng.randbytes(32)
    for f in rng.sample(range(1, 40), rng.randrange(0, 4)):
        factores.setdefault(f, rng.randbytes(32))
    factores.pop(hu.F_INSTALACION, None)
    return FactoresActuales(factores, instalacion)


def _alterar_cuerpo(rng: random.Random, cuerpo: bytearray) -> bytearray:
    m = bytearray(cuerpo)
    for _ in range(rng.randrange(1, 5)):
        n = len(m)
        familia = rng.randrange(9)
        if familia == 0 and n:
            m[rng.randrange(n)] ^= 1 << rng.randrange(8)
        elif familia == 1 and n:
            m[rng.randrange(n)] = rng.randrange(256)
        elif familia == 2 and n:
            a = rng.randrange(n)
            b = min(n, a + rng.randrange(1, 9))
            m[a:b] = bytes(rng.randrange(256) for _ in range(b - a))
        elif familia == 3 and n:
            del m[rng.randrange(n):]
        elif familia == 4:
            m += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 25)))
        elif familia == 5 and n > 4:
            m[rng.randrange(n - 1)] ^= 0x80                                    # bit crítico / alto de un largo
        elif familia == 6 and n > 4:
            m[rng.randrange(n - 1)] = 0xFF
        elif familia == 7 and n > 4:
            m[rng.randrange(n - 1)] = 0x00
        elif familia == 8 and n > 8:
            a, b = rng.randrange(n - 4), rng.randrange(n - 4)
            m[a:a + 4] = m[b:b + 4]
    return m


def _resignar(cabecera: bytes, cuerpo: bytes, kid: str) -> bytes:
    sin_firma = cabecera + bytes(cuerpo)
    return sin_firma + firma.firmar(emisor.clave_privada(kid), sin_firma)


def _tabla_smbios_aleatoria(rng: random.Random) -> bytes:
    """Una tabla RawSMBIOSData plausible (o rota a propósito) con estructuras de tipos 0 a 4 y 127."""
    cuerpo = bytearray()
    for _ in range(rng.randrange(0, 9)):
        tipo = rng.choice([0, 1, 1, 2, 2, 3, 3, 4, 4, 11, 17])
        largo = rng.choice([4, 8, 8, 15, 20, 24, 25, 27, 32])
        formateada = bytearray(rng.randrange(256) for _ in range(largo))
        formateada[0], formateada[1] = tipo, largo
        if largo > 7:
            formateada[7] = rng.randrange(0, 4)
        cadenas = [rng.choice([b"", b"SN-%d" % rng.randrange(1000), b" ", b"\xc2\xa0", b"To be filled by O.E.M.", b"\xff\xfe", "ñandú".encode(), b" x "]) for _ in range(rng.randrange(0, 4))]
        textos = b"".join(c + b"\x00" for c in cadenas if c != b"") or b""
        cuerpo += bytes(formateada) + (textos + b"\x00" if textos else b"\x00\x00")
    cuerpo += bytes([127, 4, 0, 0, 0, 0])
    if rng.random() < 0.15:
        cuerpo = cuerpo[:rng.randrange(0, len(cuerpo) + 1)]
    cabecera = bytes([0, 3, 4, 0]) + struct.pack("<I", len(cuerpo) if rng.random() < 0.8 else rng.randrange(0, 200))
    return cabecera + bytes(cuerpo)


class _Conteo:
    total = 0


# =================================================================================================================================== carga
class PruebasDeCarga(SimpleTestCase):
    def test_las_rutas_son_absolutas_y_un_nodo_de_produccion_no_lee_el_entorno(self):
        with mock.patch.dict(os.environ, {"AVACOM_LIC_NATIVA": r"C:\otra\avacom_lic.dll"}):
            produccion, esperada = nativo.candidatas("produccion", Path(tempfile.gettempdir()) / "x")
            pruebas, _ = nativo.candidatas("pruebas", Path(tempfile.gettempdir()) / "x")
        self.assertTrue(all(r.is_absolute() for r in produccion + pruebas))
        self.assertEqual(len(produccion), 1)                                         # sólo <backend>\native\: ni variable de entorno ni la carpeta del repositorio
        self.assertNotIn(Path(r"C:\otra\avacom_lic.dll"), produccion)
        self.assertIn(Path(r"C:\otra\avacom_lic.dll"), pruebas)                      # fuera de producción sí (así se prueba una compilación nueva)
        self.assertFalse(esperada)                                                   # la carpeta native no existe: instalación sin nativa, la referencia sin asiento

    def test_una_ruta_relativa_o_inexistente_no_se_carga(self):
        for ruta in (Path("avacom_lic.dll"), Path(tempfile.gettempdir()) / "no-existe" / "avacom_lic.dll"):
            with self.assertRaises(Exception):
                nativo._cargar_ruta(ruta)

    @unittest.skipUnless(HAY_NATIVA, MOTIVO_OMISION)
    def test_abi_y_autoprueba(self):
        n = _NATIVA.nativa
        self.assertEqual(n.abi(), nativo.ABI_ESPERADA)
        self.assertEqual(n.selftest(), 0)
        self.assertTrue(n.ruta.is_absolute())

    @unittest.skipUnless(HAY_NATIVA, MOTIVO_OMISION)
    def test_cargar_y_autoprobar_cuesta_menos_de_200_ms(self):
        mejor = min(self._medir() for _ in range(3))
        self.assertLess(mejor, 0.2, f"cargar + avl_selftest tardó {mejor * 1000:.1f} ms")

    @staticmethod
    def _medir() -> float:
        ruta = _NATIVA.nativa.ruta
        t = time.perf_counter()
        nativo._cargar_ruta(ruta)
        return time.perf_counter() - t

    @unittest.skipUnless(HAY_NATIVA, MOTIVO_OMISION)
    def test_una_dll_con_otra_abi_o_que_falla_la_autoprueba_no_se_carga(self):
        with mock.patch.object(Nativa, "abi", return_value=99):
            with self.assertRaises(OSError):
                nativo._cargar_ruta(_NATIVA.nativa.ruta)
        with mock.patch.object(Nativa, "selftest", return_value=-23):
            with self.assertRaises(OSError):
                nativo._cargar_ruta(_NATIVA.nativa.ruta)

    @unittest.skipUnless(HAY_NATIVA, MOTIVO_OMISION)
    def test_el_validar_una_licencia_con_la_nativa_no_cuesta_mas_de_200_ms_que_la_referencia(self):
        rng = random.Random(SEMILLA)
        lic = emisor.emitir(_licencia_aleatoria(rng, emisor.AHORA), emisor.KID_DEV_1)
        claves = emisor.claves_publicas()
        kw = dict(ahora=emisor.AHORA, tolerancia_inicio=DIA, produccion=False, comprobar_inicio=False)
        t = time.perf_counter()
        for _ in range(200):
            REF.licencia_verificar(lic, claves, **kw)
        ref = (time.perf_counter() - t) / 200
        t = time.perf_counter()
        for _ in range(200):
            _NATIVA.nativa.licencia_verificar(lic, claves, **kw)
        nat = (time.perf_counter() - t) / 200
        self.assertLess(nat - ref, 0.2)
        print(f"\n  [medido] validar una licencia: referencia {ref * 1e6:.0f} µs · nativa {nat * 1e6:.0f} µs", end="")


# =================================================================================================================================== diferencial
@unittest.skipUnless(HAY_NATIVA, MOTIVO_OMISION)
class PruebasDiferenciales(SimpleTestCase):
    """La nativa contra la referencia. Un solo recuento: al final se exige haber corrido ≥ 10 000 casos."""

    nat = _NATIVA.nativa if HAY_NATIVA else None
    claves = emisor.claves_publicas()

    def _comparar_licencia(self, datos: bytes, **kw):
        r = _intento(lambda: REF.licencia_verificar(datos, self.claves, **kw))
        n = _intento(lambda: self.nat.licencia_verificar(datos, self.claves, **kw))
        self.assertEqual(r, n, f"referencia y nativa difieren con {datos.hex()} y {kw}")
        _Conteo.total += 1
        return r

    def test_licencias_validas_con_politica_y_huella(self):
        rng = random.Random(SEMILLA)
        aceptadas = rechazadas = 0
        for i in range(2500):
            ahora = emisor.AHORA + rng.randrange(-5, 5) * DIA
            lic = _licencia_aleatoria(rng, ahora)
            kid = rng.choice([emisor.KID_DEV_1, emisor.KID_DEV_2])
            datos = emisor.emitir(lic, kid)
            kw = dict(ahora=ahora, tolerancia_inicio=rng.choice([0, DIA, 7 * DIA]), produccion=rng.random() < 0.5, comprobar_inicio=rng.random() < 0.5, actuales=_actuales_aleatorios(rng, lic))
            r = self._comparar_licencia(datos, **kw)
            aceptadas += r[0] == "ok"
            rechazadas += r[0] == "error"
        self.assertGreater(aceptadas, 1000)
        self.assertGreater(rechazadas, 100)                                           # tipo desarrollo en producción y «aún no vigente» también se ejercitan

    def test_cuerpos_alterados_y_vueltos_a_firmar(self):
        """La firma es válida: lo que decide es el lector de campos y las reglas de forma. Mismo veredicto, mismo motivo."""
        rng = random.Random(SEMILLA + 1)
        base = [emisor.emitir(_licencia_aleatoria(rng, emisor.AHORA), emisor.KID_DEV_1) for _ in range(40)]
        motivos: dict[str, int] = {}
        aceptadas = 0
        for i in range(6000):
            original = rng.choice(base)
            cabecera = original[:7 + original[6]]
            cuerpo = _alterar_cuerpo(rng, bytearray(original[len(cabecera):-64]))
            datos = _resignar(cabecera, cuerpo, emisor.KID_DEV_1)
            r = self._comparar_licencia(datos, ahora=emisor.AHORA, tolerancia_inicio=DIA, produccion=False, comprobar_inicio=False)
            if r[0] == "ok":
                aceptadas += 1
            else:
                motivos[r[1]] = motivos.get(r[1], 0) + 1
        self.assertGreater(aceptadas, 100)
        for motivo in ("formato", "campo_invalido", "etiqueta_critica_desconocida", "campo_faltante"):
            self.assertGreater(motivos.get(motivo, 0), 20, f"la mutación casi no produjo «{motivo}»: {motivos}")

    def test_cabeceras_y_firmas_alteradas(self):
        rng = random.Random(SEMILLA + 2)
        base = [emisor.emitir(_licencia_aleatoria(rng, emisor.AHORA), rng.choice([emisor.KID_DEV_1, emisor.KID_DEV_2])) for _ in range(30)]
        for _ in range(2500):
            m = bytearray(rng.choice(base))
            for _ in range(rng.randrange(1, 4)):
                if len(m) < 80:
                    break
                opcion = rng.randrange(6)
                if opcion == 0:
                    m[rng.randrange(min(len(m), 8 + m[6]))] ^= 1 << rng.randrange(8)       # cabecera
                elif opcion == 1:
                    m[-1 - rng.randrange(64)] ^= 1 << rng.randrange(8)                     # firma
                elif opcion == 2:
                    del m[rng.randrange(len(m)):]
                elif opcion == 3:
                    m += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 40)))
                elif opcion == 4:
                    m[6] = rng.choice([0, 1, 5, 64, 65, 200, 255])                           # largo del kid
                else:
                    m[rng.randrange(len(m))] = rng.randrange(256)
            self._comparar_licencia(bytes(m), ahora=emisor.AHORA, tolerancia_inicio=DIA, produccion=False, comprobar_inicio=False)
        for largo in (0, 1, 10, 71, 72, 73, 16 * 1024, 16 * 1024 + 1, 20000):                # los topes de tamaño, justo en el borde
            self._comparar_licencia(bytes(rng.randrange(256) for _ in range(largo)), ahora=0, tolerancia_inicio=0, produccion=False, comprobar_inicio=False)

    def test_firma_separada(self):
        rng = random.Random(SEMILLA + 3)
        for i in range(3000):
            privada = rng.randbytes(32)
            publica = firma.publica_de(privada)
            mensaje = rng.randbytes(rng.choice([0, 1, 2, 31, 32, 33, 64, 100, 1000]))
            sig = firma.firmar(privada, mensaje)
            casos = [(publica, sig, mensaje)]
            m2 = bytearray(sig)
            m2[rng.randrange(64)] ^= 1 << rng.randrange(8)
            casos.append((publica, bytes(m2), mensaje))
            if mensaje:
                m3 = bytearray(mensaje)
                m3[rng.randrange(len(m3))] ^= 1 << rng.randrange(8)
                casos.append((publica, sig, bytes(m3)))
            p4 = bytearray(publica)
            p4[rng.randrange(32)] ^= 1 << rng.randrange(8)
            casos.append((bytes(p4), sig, mensaje))
            casos.append((rng.randbytes(32), rng.randbytes(64), mensaje))                   # llave y firma al azar
            s5 = bytearray(sig)
            s5[32:] = ((int.from_bytes(sig[32:], "little") + 2**252 + 27742317777372353535851937790883648493) % 2**256).to_bytes(32, "little")   # S + L
            casos.append((publica, bytes(s5), mensaje))
            for c in casos:
                self.assertEqual(REF.verificar(*c), self.nat.verificar(*c), f"difieren: {c[0].hex()} {c[1].hex()} {c[2].hex()}")
                _Conteo.total += 1
        # llaves públicas y R de orden pequeño (con y sin bit de signo, canónicas y no): ninguna firma «universal» se acepta
        ys = sorted(firma._Y_DE_ORDEN_PEQUENO)
        debiles = [(y | (signo << 255)).to_bytes(32, "little") for y in ys for signo in (0, 1)]
        for pub in debiles + [bytes(32)]:
            for r_ in debiles[:6]:
                for s_ in (bytes(32), bytes([1]) + bytes(31), rng.randbytes(31) + bytes([0x01])):
                    sig = r_ + s_
                    for mensaje in (b"mensaje", b""):
                        self.assertFalse(REF.verificar(pub, sig, mensaje), f"la referencia aceptó la llave débil {pub.hex()}")
                        self.assertFalse(self.nat.verificar(pub, sig, mensaje), f"la nativa aceptó la llave débil {pub.hex()} con R={r_.hex()}")
                        _Conteo.total += 1
        # y llaves no válidas como punto: ambas dicen lo mismo
        for pub in (bytes([0xFF] * 32), bytes([0xEE]) + bytes([0xFF] * 30) + bytes([0x7F])):
            for sig in (bytes(64), bytes([1]) + bytes(63), rng.randbytes(64)):
                self.assertEqual(REF.verificar(pub, sig, b"mensaje"), self.nat.verificar(pub, sig, b"mensaje"), f"difieren con la llave {pub.hex()}")
                _Conteo.total += 1

    def test_comparar_huella(self):
        rng = random.Random(SEMILLA + 4)
        for _ in range(1500):
            h = _huella_aleatoria(rng)
            lic = emisor.licencia_de_ejemplo(huella=h)
            actuales = _actuales_aleatorios(rng, lic) or FactoresActuales({}, None)
            self.assertEqual(REF.huella_comparar(h.k, list(h.factores), actuales), self.nat.huella_comparar(h.k, list(h.factores), actuales))
            _Conteo.total += 1
        h = HuellaDeLicencia(1, ((hu.F_INSTALACION, bytes([7]) * 32),))
        for inst in (bytes([7]) * 32, bytes([8]) * 32, None):
            a = FactoresActuales({}, inst)
            self.assertEqual(REF.huella_comparar(1, list(h.factores), a), self.nat.huella_comparar(1, list(h.factores), a))
            _Conteo.total += 1

    def test_smbios(self):
        rng = random.Random(SEMILLA + 5)
        for _ in range(1200):
            tabla = _tabla_smbios_aleatoria(rng) if rng.random() < 0.85 else rng.randbytes(rng.randrange(0, 300))
            self.assertEqual(REF.smbios(tabla), self.nat.smbios(tabla), f"difieren con {tabla.hex()}")
            _Conteo.total += 1

    def test_hardware_de_este_equipo(self):
        if os.name != "nt":
            self.skipTest("avl_fp_collect sólo existe en Windows")
        try:
            esperado = REF.recolectar_hardware()
        except Exception as error:   # noqa: BLE001
            self.skipTest(f"la referencia no pudo leer el hardware aquí: {error}")
        self.assertEqual(self.nat.recolectar_hardware(), esperado)
        _Conteo.total += 1

    def test_solicitudes_byte_a_byte(self):
        rng = random.Random(SEMILLA + 6)
        for _ in range(500):
            n = rng.randrange(1, 17)
            factores = tuple((f, rng.randbytes(32)) for f in sorted(rng.sample(range(1, 33), n)))
            args = dict(nonce=rng.randbytes(16), version_nodo=rng.choice(["", "2.15.0", "desarrollo", "ñ" * 40, "x" * 100]), creada=rng.randrange(1, 2**62),
                        nivel=rng.choice([hu.NIVEL_HARDWARE, hu.NIVEL_INSTALACION]), huella=HuellaDeLicencia(rng.randrange(1, n + 1), factores),
                        licencia_vigente=rng.choice([None, str(uuid.UUID(int=rng.getrandbits(128), version=4))]), aula=rng.choice(["", "Aula 1", "ñ" * 300, "y" * 600]))
            privada = rng.randbytes(32)
            esperado = REF.construir_solicitud(privada, **args)
            self.assertEqual(esperado, self.nat.construir_solicitud(privada, **args))
            _Conteo.total += 1
        s = REF.construir_solicitud(bytes(range(32)), **args)                                 # y la que produjo la nativa la lee el dominio
        self.assertEqual(sol_leer(self.nat.construir_solicitud(bytes(range(32)), **args)).sha256, sol_leer(s).sha256)

    def test_ancla_del_reloj(self):
        rng = random.Random(SEMILLA + 7)
        for _ in range(500):
            secreto = rng.randbytes(rng.choice([1, 16, 32, 100]))
            marca = rng.randrange(0, 2**62)
            instalada = rng.choice([None, rng.randrange(0, 2**62)])
            _, mac, _ = REF.avance_de_reloj(secreto, marca, None, instalada, marca)
            previo = rng.choice([None, mac, rng.randbytes(32)])
            candidata = rng.choice([marca - rng.randrange(0, 1000) if marca > 1000 else 0, marca + rng.randrange(0, 10**9), rng.randrange(0, 2**62)])
            r = REF.avance_de_reloj(secreto, marca, previo, instalada, candidata)
            self.assertEqual(r, self.nat.avance_de_reloj(secreto, marca, previo, instalada, candidata))
            _Conteo.total += 1

    def test_hkdf_y_xchacha(self):
        rng = random.Random(SEMILLA + 8)
        for _ in range(500):
            secreto, sal, info = rng.randbytes(rng.randrange(1, 80)), rng.randbytes(rng.choice([0, 0, 8, 64, 200])), rng.randbytes(rng.choice([0, 5, 90]))
            largo = rng.choice([1, 16, 32, 33, 64, 65, 100, 255 * 64])
            self.assertEqual(REF.derivar(secreto, sal, info, largo), self.nat.derivar(secreto, sal, info, largo))
            _Conteo.total += 1
        for _ in range(600):
            llave, nonce = rng.randbytes(32), rng.randbytes(24)
            contexto, claro = rng.randbytes(rng.choice([0, 1, 12, 100])), rng.randbytes(rng.choice([0, 1, 15, 16, 17, 63, 64, 65, 1000]))
            envuelto = REF.envolver(llave, nonce, contexto, claro)
            self.assertEqual(envuelto, self.nat.envolver(llave, nonce, contexto, claro))
            self.assertEqual(self.nat.desenvolver(llave, contexto, envuelto), claro)
            self.assertEqual(REF.desenvolver(llave, contexto, envuelto), claro)
            malo = bytearray(envuelto)
            malo[rng.randrange(len(malo))] ^= 1 << rng.randrange(8)
            for ctx, blob in ((contexto, bytes(malo)), (contexto + b"x", envuelto)):
                with self.assertRaises(nativo.ClaveAjena):
                    self.nat.desenvolver(llave, ctx, blob)
                with self.assertRaises(nativo.ClaveAjena):
                    REF.desenvolver(llave, ctx, blob)
            _Conteo.total += 3

    def test_zz_al_menos_10_000_casos_diferenciales(self):
        self.assertGreaterEqual(_Conteo.total, 10_000, f"sólo se compararon {_Conteo.total} casos")
        print(f"\n  [medido] casos diferenciales comparados: {_Conteo.total}", end="")


def sol_leer(datos: bytes):
    from licenciamiento.dominio import solicitud
    return solicitud.leer_solicitud(datos)


# =================================================================================================================================== respaldo
class PruebasDelRespaldo(SimpleTestCase):
    def test_sin_la_biblioteca_la_referencia_responde_igual(self):
        rng = random.Random(SEMILLA + 9)
        b = Biblioteca(None, "no_encontrada", True)
        self.assertFalse(b.activa)
        lic = emisor.emitir(_licencia_aleatoria(rng, emisor.AHORA), emisor.KID_DEV_1)
        kw = dict(ahora=emisor.AHORA, tolerancia_inicio=DIA, produccion=False, comprobar_inicio=False)
        self.assertEqual(b.licencia_verificar(lic, emisor.claves_publicas(), **kw), REF.licencia_verificar(lic, emisor.claves_publicas(), **kw))
        self.assertTrue(b.verificar(firma.publica_de(bytes(32)), firma.firmar(bytes(32), b"x"), b"x"))

    def test_una_llamada_de_la_nativa_que_falla_cae_a_la_referencia(self):
        class Rota:
            def verificar(self, *a):
                raise OSError("simulado")

            def smbios(self, *a):
                raise NativaNoDisponible("simulado")

        b = Biblioteca(Rota(), None, True)                                      # type: ignore[arg-type]
        privada = bytes(range(32))
        self.assertTrue(b.verificar(firma.publica_de(privada), firma.firmar(privada, b"m"), b"m"))
        self.assertEqual(b.smbios(bytes([0, 3, 4, 0, 0, 0, 0, 0])), REF.smbios(bytes([0, 3, 4, 0, 0, 0, 0, 0])))

    def test_el_verificador_del_dominio_usa_la_nativa_y_si_lanza_la_referencia(self):
        privada = bytes(range(32))
        publica, sig = firma.publica_de(privada), firma.firmar(privada, b"hola")
        llamadas = []
        firma.instalar_verificador_alterno(lambda p, s, m: llamadas.append(1) or True)
        try:
            self.assertTrue(firma.verificar(publica, sig, b"hola"))
            self.assertEqual(llamadas, [1])
            firma.instalar_verificador_alterno(lambda p, s, m: (_ for _ in ()).throw(RuntimeError("la nativa murió")))
            self.assertTrue(firma.verificar(publica, sig, b"hola"))                          # la referencia
            self.assertFalse(firma.verificar(publica, sig, b"otra cosa"))
        finally:
            firma.instalar_verificador_alterno(None)

    def test_instalacion_con_native_pero_sin_la_dll_se_usa_la_referencia_y_se_espera_asiento(self):
        raiz = Path(tempfile.mkdtemp(prefix="avacom-sin-dll-"))
        self.addCleanup(shutil.rmtree, raiz, True)
        (raiz / nativo.CARPETA_EN_INSTALACION).mkdir()                                     # el instalador creó la carpeta pero la DLL no está (renombrada, borrada por un antivirus)
        b = nativo.cargar("produccion", raiz)
        self.assertFalse(b.activa)
        self.assertTrue(b.esperada)
        self.assertEqual(b.motivo, "no_encontrada")
        novedades = []

        class Nodo:
            def anotar_novedad(self, nombre):
                novedades.append(nombre)

        nativo.informar_al_nodo(b, Nodo())
        self.assertEqual(novedades, [nativo.NOMBRE_DEL_SECRETO])
        # sin carpeta native (desarrollo, instalaciones anteriores): referencia en silencio
        vacio = Path(tempfile.mkdtemp(prefix="avacom-sin-native-"))
        self.addCleanup(shutil.rmtree, vacio, True)
        b2 = nativo.cargar("produccion", vacio)
        nativo.informar_al_nodo(b2, Nodo())
        self.assertFalse(b2.esperada)
        self.assertEqual(novedades, [nativo.NOMBRE_DEL_SECRETO])

    def test_una_dll_dañada_no_carga_y_se_sigue(self):
        raiz = Path(tempfile.mkdtemp(prefix="avacom-dll-mala-"))
        self.addCleanup(shutil.rmtree, raiz, True)
        carpeta = raiz / nativo.CARPETA_EN_INSTALACION
        carpeta.mkdir()
        (carpeta / nativo._ARCHIVO).write_bytes(b"esto no es una biblioteca" * 20)
        b = nativo.cargar("produccion", raiz)
        self.assertFalse(b.activa)
        self.assertTrue(b.esperada)
        self.assertIn(b.motivo, ("OSError", "FileNotFoundError", "BadImageFormatError"))


class PruebasConUnNodoReal(BaseLicencia):
    """La señal del respaldo recorre el camino de siempre de la integridad: una observación, un asiento, la bandera; y nada de la clase cambia."""

    def test_la_nativa_que_faltaba_se_asienta_como_integridad_alterada_y_el_nodo_sigue(self):
        self.s.nodo.anotar_novedad(nativo.NOMBRE_DEL_SECRETO)
        e = self.evaluar("tick")
        self.assertIn("integridad_alterada", e.estado.banderas)
        asiento = self.s.vivo.leer()
        self.assertIsNotNone(asiento)
        activada = self.activar_ok()                                                     # activar una licencia funciona igual
        self.assertEqual(activada["estado"], "activa")
        self.assertEqual(self.estado()["estado"], "activa")
        self.assertEqual(self.s.nodo.tomar_novedades(), [])                              # ya se entregó una sola vez

    def test_sin_novedad_no_hay_bandera(self):
        e = self.evaluar("tick")
        self.assertNotIn("integridad_alterada", e.estado.banderas)


__all__ = []
