"""Las reglas puras de la cola de medios: claves, `Range`, ritmo y cupos, expulsión y qué medios usa un objeto."""
from __future__ import annotations

from django.test import SimpleTestCase

from ..dominio import catalogos as cat
from ..dominio.clave import ClaveMedio
from ..dominio.politica import Candidato, elegir_expulsiones
from ..dominio.rangos import Insatisfacible, Tramo, interpretar, total_de_content_range
from ..dominio.referencias import medios_de
from ..dominio.ritmo import Cubo, Cupo, Cupos


class ClaveTests(SimpleTestCase):
    def test_la_misma_referencia_da_la_misma_huella_y_cualquier_cambio_la_cambia(self):
        a = ClaveMedio.de("biblioteca", "curso", "vid", None)
        self.assertEqual(a.huella(), ClaveMedio.de("biblioteca", "curso", "vid", "").huella())
        self.assertEqual(len(a.huella()), 64)
        for otra in (ClaveMedio.de("ejemplo", "curso", "vid"), ClaveMedio.de("biblioteca", "otro", "vid"), ClaveMedio.de("biblioteca", "curso", "img"),
                     ClaveMedio.de("biblioteca", "curso", "vid", "subtitulos")):
            self.assertNotEqual(a.huella(), otra.huella())

    def test_las_barras_sobrantes_de_la_ruta_no_crean_otro_recurso(self):
        self.assertEqual(ClaveMedio.de("b", "c", "m", "/js/app.js/").huella(), ClaveMedio.de("b", "c", "m", "js/app.js").huella())

    def test_dos_referencias_que_se_parecen_no_chocan(self):
        self.assertNotEqual(ClaveMedio.de("b", "c", "m1", "x").huella(), ClaveMedio.de("b", "c", "m", "1x").huella())


class RangosTests(SimpleTestCase):
    def test_los_tramos_que_un_reproductor_pide(self):
        self.assertEqual(interpretar("bytes=0-9", 100), Tramo(0, 9))
        self.assertEqual(interpretar("bytes=10-", 100), Tramo(10, 99))
        self.assertEqual(interpretar("bytes=-10", 100), Tramo(90, 99))
        self.assertEqual(interpretar("bytes=90-500", 100), Tramo(90, 99))        # el fin se recorta al final del archivo
        self.assertEqual(interpretar("bytes=-500", 100), Tramo(0, 99))
        self.assertEqual(interpretar("  Bytes=5-6 ", 100), Tramo(5, 6))

    def test_la_longitud_y_el_encabezado_de_un_tramo(self):
        t = interpretar("bytes=10-19", 100)
        self.assertEqual((t.longitud, t.encabezado(100)), (10, "bytes 10-19/100"))

    def test_sin_range_o_ilegible_se_envia_entero(self):
        for cabecera in (None, "", "items=0-9", "bytes=", "bytes=a-b", "bytes=9-3", "bytes=0-4,10-14", "bytes=5"):
            self.assertIsNone(interpretar(cabecera, 100), cabecera)
        self.assertIsNone(interpretar("bytes=0-9", 0))                              # archivo vacío

    def test_un_tramo_fuera_del_archivo_es_insatisfacible(self):
        for cabecera in ("bytes=100-", "bytes=500-600", "bytes=-0"):
            with self.assertRaises(Insatisfacible, msg=cabecera):
                interpretar(cabecera, 100)

    def test_el_content_range_de_una_respuesta_parcial(self):
        self.assertEqual(total_de_content_range("bytes 10-19/100"), (10, 19, 100))
        self.assertEqual(total_de_content_range("bytes 10-19/*"), (10, 19, None))
        self.assertIsNone(total_de_content_range("bytes */100"))
        self.assertIsNone(total_de_content_range(None))


class RitmoTests(SimpleTestCase):
    def test_sin_tope_no_hay_espera(self):
        self.assertEqual(Cubo(0).reservar(10**9), 0.0)

    def test_con_tope_se_gasta_la_rafaga_y_despues_se_espera(self):
        ahora = [0.0]
        cubo = Cubo(1000, reloj=lambda: ahora[0])
        self.assertEqual(cubo.reservar(1000), 0.0)                  # el segundo de ráfaga
        self.assertAlmostEqual(cubo.reservar(500), 0.5)             # hay que esperar medio segundo
        ahora[0] += 1.0                                             # pasa un segundo: se recuperan 1000 fichas (el cubo no pasa de 1000)
        self.assertEqual(cubo.reservar(400), 0.0)

    def test_los_cupos_no_pasan_del_maximo_y_se_liberan(self):
        cupos = Cupos(2)
        self.assertTrue(cupos.intentar())
        self.assertTrue(cupos.intentar())
        self.assertFalse(cupos.intentar())
        cupos.liberar()
        self.assertTrue(cupos.intentar())
        self.assertEqual((cupos.en_uso, cupos.picos), (2, 2))

    def test_liberar_dos_veces_el_mismo_cupo_cuenta_una(self):
        cupos = Cupos(3)
        cupos.intentar()
        cupos.intentar()
        cupo = Cupo(cupos)
        cupo.liberar()
        cupo.liberar()
        self.assertEqual(cupos.en_uso, 1)


class PoliticaTests(SimpleTestCase):
    def test_sale_primero_lo_menos_usado_y_se_para_al_liberar_lo_pedido(self):
        c = [Candidato("a", 100, 1_000), Candidato("b", 100, 5_000), Candidato("c", 100, 3_000)]
        self.assertEqual(elegir_expulsiones(c, 150, ahora_ms=100_000, proteger_ms=0), ["a", "c"])

    def test_no_se_toca_lo_que_se_esta_leyendo_ni_lo_usado_hace_poco(self):
        c = [Candidato("leyendo", 100, 1_000, en_uso=True), Candidato("reciente", 100, 99_000), Candidato("viejo", 100, 2_000)]
        self.assertEqual(elegir_expulsiones(c, 1_000, ahora_ms=100_000, proteger_ms=10_000), ["viejo"])

    def test_si_no_hay_de_donde_devuelve_lo_que_pueda(self):
        self.assertEqual(elegir_expulsiones([], 10, 0, 0), [])


class ReferenciasTests(SimpleTestCase):
    def test_encuentra_los_medios_en_cualquier_profundidad_sin_repetir(self):
        objeto = {"objeto_ref": "o1", "laminas": [
            {"bloques": [{"media_ref": "img-a", "url": "/x"}, {"media_ref": "vid-b", "pausas": [{"media_ref": "img-a"}]}]},
            {"bloques": [{"media_ref": None}, {"media_ref": ""}, {"media_ref": "aud-c"}]},
        ], "preguntas": [{"opciones": [{"media_ref": "img-d"}]}], "html": {"media_ref": "lec-html", "entrada": "index.html"}}
        self.assertEqual(medios_de(objeto), [("img-a", ""), ("vid-b", ""), ("aud-c", ""), ("img-d", ""), ("lec-html", "index.html")])

    def test_un_medio_ausente_no_se_pide(self):
        self.assertEqual(medios_de({"bloques": [{"media_ref": "fantasma", "ausente": True}, {"media_ref": "real"}]}), [("real", "")])

    def test_un_medio_suelto(self):
        self.assertEqual(medios_de({"media_ref": "vid-1"}), [("vid-1", "")])

    def test_no_se_desborda_con_estructuras_enormes(self):
        enorme = [{"media_ref": f"m{i}"} for i in range(1000)]
        self.assertEqual(len(medios_de(enorme)), 200)


class CatalogosTests(SimpleTestCase):
    def test_las_prioridades_van_de_lo_proyectado_a_lo_anticipado(self):
        orden = [cat.PROYECCION, cat.EVALUACION, cat.CLASE, cat.ESTUDIO, cat.PAQUETE, cat.PRECARGA]
        self.assertEqual(orden, sorted(orden))
        self.assertEqual(set(cat.PRIORIDADES), set(orden))

    def test_los_cinco_estados_del_diseno(self):
        self.assertEqual(set(cat.ESTADOS), {"pendiente", "descargando", "disponible", "fallido", "cancelado"})
