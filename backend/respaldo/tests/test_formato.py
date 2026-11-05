"""
El formato `.avbak` y su criptografía (BR-102, TST-058, TST-059, INV-021): ida y vuelta, claves, custodia y TODO lo que se puede alterar. Puras: sin base de datos.
"""
from __future__ import annotations

import io
import os
import random

from django.test import SimpleTestCase

from respaldo.dominio import catalogos as cat
from respaldo.dominio import cripto, formato
from respaldo.dominio.errores import ClaveNoDisponible, RespaldoRechazado


def entradas(datos: dict[str, bytes], clase: str = "primario") -> list[formato.Entrada]:
    return [formato.Entrada(n, clase, len(d), (lambda d=d: io.BytesIO(d))) for n, d in datos.items()]


class Armado:
    """Un respaldo escrito en memoria, con las dos llaves."""

    def __init__(self, datos: dict[str, bytes], rid: str = "00000000-0000-4000-8000-000000000001", con_custodia: bool = True):
        self.nodo = cripto.generar_clave()
        self.codigo = cripto.generar_codigo_de_custodia()
        self.sal = cripto.generar_sal()
        kek = cripto.clave_de_custodia(cripto.secreto_de_custodia(self.codigo), self.sal)
        self.dek = cripto.generar_clave()
        claves = formato.envolver_dek(rid, self.dek, self.nodo, (kek, self.sal) if con_custodia else None)
        self.datos = datos
        salida = io.BytesIO()
        self.resultado = formato.escribir(salida, {"respaldo_id": rid, "tipo": "completo", "creado_en": 1_700_000_000_000, "nodo_id": "nodo-a"}, entradas(datos), self.dek, claves)
        self.bytes = salida.getvalue()

    def leer(self, crudo: bytes | None = None, clave_nodo: bytes | None = None, codigo: str | None = None) -> dict[str, bytes]:
        f = io.BytesIO(self.bytes if crudo is None else crudo)
        manifiesto, cabecera = formato.leer_manifiesto(f)
        dek = formato.abrir_dek(manifiesto, clave_nodo if clave_nodo is not None else self.nodo, codigo)
        return {n: b"".join(b) for n, _i, b in formato.recorrer(f, manifiesto, cabecera, dek)}


DATOS = {"base.sqlite3": os.urandom(2 * cat.CHUNK + 123), "evidencias/entrega 1.pdf": os.urandom(5000), "evidencias/vacio.txt": b""}


class IdaYVuelta(SimpleTestCase):
    def test_vuelve_exactamente_lo_que_se_guardo_incluso_con_varios_trozos_y_un_archivo_vacio(self):
        a = Armado(DATOS)
        self.assertGreaterEqual(a.resultado["manifiesto"]["trozos"], 3)
        self.assertEqual(a.leer(), DATOS)

    def test_el_manifiesto_se_lee_sin_ninguna_clave_y_no_trae_nombres_de_archivos_ni_datos_de_personas(self):
        a = Armado(DATOS)
        manifiesto, _ = formato.leer_manifiesto(io.BytesIO(a.bytes))
        self.assertEqual(manifiesto["respaldo_id"], "00000000-0000-4000-8000-000000000001")
        self.assertEqual(manifiesto["entradas"], 3)
        _, cabecera = formato.leer_manifiesto(io.BytesIO(a.bytes))
        for prohibido in ("entrega", "evidencias", ".pdf", "base.sqlite3", "vacio"):
            self.assertNotIn(prohibido.encode(), cabecera, f"«{prohibido}» no debe leerse en claro en el manifiesto")
        for prohibido in ("entrega 1", "evidencias/", "base.sqlite3"):                              # 8 bytes o más: no aparecen por azar en 2 MB de texto cifrado
            self.assertNotIn(prohibido.encode(), a.bytes)

    def test_ningun_contenido_se_lee_en_claro(self):
        a = Armado({"base.sqlite3": b"SQLite format 3\x00" + b"calificacion-de-Maria-Lopez" * 100})
        self.assertNotIn(b"Maria", a.bytes)
        self.assertNotIn(b"SQLite format", a.bytes)

    def test_dos_respaldos_del_mismo_contenido_no_se_parecen(self):
        self.assertNotEqual(Armado(DATOS).bytes, Armado(DATOS).bytes)


class Claves(SimpleTestCase):
    def test_abre_con_la_clave_del_nodo_o_con_el_codigo_de_custodia_y_con_el_codigo_escrito_a_mano(self):
        a = Armado(DATOS)
        self.assertEqual(a.leer(), DATOS)
        self.assertEqual(a.leer(clave_nodo=b"", codigo=a.codigo), DATOS)       # otro equipo: sin clave del nodo, con el código
        escrito = a.codigo.lower().replace("-", " ")
        self.assertEqual(a.leer(clave_nodo=b"", codigo=escrito), DATOS)

    def test_otro_equipo_sin_el_codigo_no_puede_abrirlo_BR_102(self):
        a = Armado(DATOS)
        with self.assertRaises(ClaveNoDisponible):
            a.leer(clave_nodo=cripto.generar_clave())
        with self.assertRaises(ClaveNoDisponible):
            a.leer(clave_nodo=cripto.generar_clave(), codigo=cripto.generar_codigo_de_custodia())      # un código válido pero de otra institución

    def test_un_respaldo_hecho_antes_de_emitir_la_custodia_solo_abre_en_su_equipo(self):
        a = Armado(DATOS, con_custodia=False)
        self.assertEqual(a.leer(), DATOS)
        with self.assertRaises(ClaveNoDisponible):
            a.leer(clave_nodo=b"", codigo=a.codigo)

    def test_el_codigo_de_custodia_detecta_un_error_de_copia(self):
        codigo = cripto.generar_codigo_de_custodia()
        self.assertEqual(len(codigo.replace("-", "")), 34)
        self.assertIsNotNone(cripto.secreto_de_custodia(codigo))
        mal = ("A" if codigo[0] != "A" else "B") + codigo[1:]
        self.assertIsNone(cripto.secreto_de_custodia(mal))
        self.assertIsNone(cripto.secreto_de_custodia(codigo[:-1]))
        self.assertIsNone(cripto.secreto_de_custodia(""))
        self.assertIsNone(cripto.secreto_de_custodia(None))


class Alteraciones(SimpleTestCase):
    """TST-059 y la regla de oro: lo alterado se RECHAZA, nunca se restaura ni se acepta a medias."""

    def _debe_fallar(self, a: Armado, crudo: bytes) -> str:
        try:
            a.leer(crudo)
        except RespaldoRechazado as error:
            return error.motivo
        self.fail("Un respaldo alterado se aceptó")

    def test_truncado(self):
        a = Armado(DATOS)
        for corte in (1, 10, 100, cat.CHUNK, len(a.bytes) // 2, len(a.bytes) - 1):
            self.assertIn(self._debe_fallar(a, a.bytes[:-corte]), ("truncado", "integridad_alterada", "formato_invalido"), corte)

    def test_con_bytes_de_mas(self):
        a = Armado(DATOS)
        self.assertEqual(self._debe_fallar(a, a.bytes + b"\x00"), "integridad_alterada")

    def test_un_byte_cambiado_en_cualquier_parte_se_detecta(self):
        a = Armado({"base.sqlite3": os.urandom(3 * cat.CHUNK // 2), "evidencias/a.txt": b"hola"})
        azar = random.Random(20261026)
        aceptados = 0
        for _ in range(300):
            i = azar.randrange(len(a.bytes))
            crudo = bytearray(a.bytes)
            crudo[i] ^= 1 << azar.randrange(8)
            try:
                a.leer(bytes(crudo))
                aceptados += 1
            except (RespaldoRechazado, ClaveNoDisponible):
                pass
        self.assertEqual(aceptados, 0, "algún cambio de un bit pasó sin detectarse")

    def test_trozos_reordenados_o_repetidos(self):
        a = Armado({"base.sqlite3": os.urandom(3 * cat.CHUNK)})
        manifiesto, cabecera = formato.leer_manifiesto(io.BytesIO(a.bytes))
        cuerpo = a.bytes[len(cabecera):]
        trozos, p = [], 0
        while p < len(cuerpo):
            n = int.from_bytes(cuerpo[p:p + 4], "big")
            trozos.append(cuerpo[p:p + 4 + n])
            p += 4 + n
        self.assertGreaterEqual(len(trozos), 4)
        self.assertEqual(self._debe_fallar(a, cabecera + b"".join([trozos[1], trozos[0], *trozos[2:]])), "integridad_alterada")
        self.assertEqual(self._debe_fallar(a, cabecera + b"".join([trozos[0], trozos[0], *trozos[2:]])), "integridad_alterada")

    def test_el_manifiesto_alterado_invalida_todos_los_trozos(self):
        a = Armado(DATOS)
        crudo = a.bytes.replace(b'"tipo":"completo"', b'"tipo":"incremental"', 1)
        self.assertNotEqual(crudo, a.bytes)
        with self.assertRaises((RespaldoRechazado, ClaveNoDisponible)):
            a.leer(crudo)

    def test_no_es_un_respaldo(self):
        for basura in (b"", b"AVBK", b"PK\x03\x04" + b"\x00" * 40, os.urandom(300), b"AVBK" + b"\x00\x02" + b"\x00\x00\x00\x05" + b"hola!"):
            with self.assertRaises(RespaldoRechazado):
                formato.leer_manifiesto(io.BytesIO(basura))

    def test_version_del_formato_desconocida(self):
        a = Armado(DATOS)
        crudo = a.bytes[:4] + (99).to_bytes(2, "big") + a.bytes[6:]
        with self.assertRaises(RespaldoRechazado) as r:
            formato.leer_manifiesto(io.BytesIO(crudo))
        self.assertEqual(r.exception.motivo, "version_no_soportada")

    def test_un_archivo_que_cambia_de_tamano_mientras_se_respalda_falla(self):
        d = b"x" * 1000

        def crece():
            return io.BytesIO(d + b"y")

        e = [formato.Entrada("a.bin", "primario", len(d), crece)]
        with self.assertRaises(formato.ArchivoCambio):
            formato.escribir(io.BytesIO(), {"respaldo_id": "r", "tipo": "completo", "creado_en": 1}, e, cripto.generar_clave(), {})


class RutasSeguras(SimpleTestCase):
    def test_lo_que_no_se_extrae(self):
        for mala in ("../x", "a/../b", "/abs", "C:/x", "a\\b", "a//b", "", "con", "a/nul.txt", "a/.", "a/b ", "a/b.", "x" * 500, "a/b:c"):
            self.assertFalse(formato.ruta_segura(mala), mala)

    def test_lo_que_si(self):
        for buena in ("base.sqlite3", "evidencias/entrega 1.pdf", "evidencias/2026/Mª Ángeles (copia).docx", "a/b/c.txt"):
            self.assertTrue(formato.ruta_segura(buena), buena)

    def test_un_respaldo_con_una_ruta_que_escapa_se_rechaza_al_leer(self):
        dek = cripto.generar_clave()
        nodo = cripto.generar_clave()
        claves = formato.envolver_dek("00000000-0000-4000-8000-0000000000aa", dek, nodo, None)
        salida = io.BytesIO()
        formato.escribir(salida, {"respaldo_id": "00000000-0000-4000-8000-0000000000aa", "tipo": "completo", "creado_en": 1}, entradas({"../escapa.txt": b"x"}), dek, claves)
        f = io.BytesIO(salida.getvalue())
        manifiesto, cabecera = formato.leer_manifiesto(f)
        with self.assertRaises(RespaldoRechazado):
            for _n, _i, b in formato.recorrer(f, manifiesto, cabecera, formato.abrir_dek(manifiesto, nodo, None)):
                list(b)

    def test_dos_entradas_con_el_mismo_nombre_se_rechazan(self):
        dek = cripto.generar_clave()
        nodo = cripto.generar_clave()
        salida = io.BytesIO()
        formato.escribir(salida, {"respaldo_id": "00000000-0000-4000-8000-0000000000aa", "tipo": "completo", "creado_en": 1},
                         [*entradas({"a.txt": b"1"}), *entradas({"A.TXT": b"2"})], dek, formato.envolver_dek("00000000-0000-4000-8000-0000000000aa", dek, nodo, None))
        f = io.BytesIO(salida.getvalue())
        manifiesto, cabecera = formato.leer_manifiesto(f)
        with self.assertRaises(RespaldoRechazado):
            for _n, _i, b in formato.recorrer(f, manifiesto, cabecera, formato.abrir_dek(manifiesto, nodo, None)):
                list(b)
