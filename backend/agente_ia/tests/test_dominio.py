"""Lo puro del agente de IA: el troceo del texto de la voz, la unión de WAV, el id de conversación y la traducción de errores."""
from __future__ import annotations

import re
import struct

from django.test import SimpleTestCase

from ..dominio import conversacion, errores, troceo, wav
from .falso import wav_de


class TroceoTests(SimpleTestCase):
    def test_un_texto_corto_es_un_solo_trozo(self):
        self.assertEqual(troceo.trocear("¡Hola! Soy el asistente de AVACOM."), ["¡Hola! Soy el asistente de AVACOM."])

    def test_vacio_o_solo_simbolos_no_da_trozos(self):
        for texto in ("", "   ", "*** ---", "…!?", None):
            self.assertEqual(troceo.trocear(texto), [], repr(texto))

    def test_un_texto_largo_se_parte_por_frases_y_ningun_trozo_pasa_del_maximo(self):
        frase = "Esta es una frase de prueba con bastantes palabras para ocupar espacio."
        texto = " ".join([frase] * 30)                                    # ≈ 2200 caracteres
        trozos = troceo.trocear(texto, 450)
        self.assertGreater(len(trozos), 4)
        self.assertTrue(all(len(t) <= 450 for t in trozos), [len(t) for t in trozos])
        self.assertEqual(" ".join(trozos), texto)                          # no se pierde ni se inventa nada
        self.assertTrue(all(t.endswith(".") for t in trozos))              # se corta en fin de frase, no a media frase

    def test_el_caso_medido_959_caracteres_dan_3_trozos_de_a_lo_sumo_450(self):
        texto = " ".join(["Una oración de relleno número %d para el ensayo." % i for i in range(20)])[:959]
        self.assertEqual(len(texto), 959)
        trozos = troceo.trocear(texto)
        self.assertEqual(len(trozos), 3)
        self.assertTrue(all(len(t) <= 450 for t in trozos))

    def test_los_decimales_y_las_abreviaturas_no_cortan_la_frase(self):
        self.assertEqual(troceo.trocear("El valor es 3.5 metros, p. ej. cuatro."), ["El valor es 3.5 metros, p. ej. cuatro."])

    def test_una_frase_larguisima_se_parte_en_comas_o_espacios_y_sin_espacios_con_corte_duro(self):
        con_comas = ", ".join(["palabra%d" % i for i in range(120)]) + "."
        trozos = troceo.trocear(con_comas, 100)
        self.assertTrue(all(len(t) <= 100 for t in trozos))
        self.assertEqual("".join(trozos).replace(" ", ""), con_comas.replace(" ", ""))
        duro = troceo.trocear("x" * 1000, 100)
        self.assertTrue(all(len(t) <= 100 for t in duro))
        self.assertEqual("".join(duro), "x" * 1000)

    def test_cada_salto_de_linea_es_un_corte_de_frase(self):
        self.assertEqual(troceo.trocear("Primera línea\nSegunda línea", 20), ["Primera línea", "Segunda línea"])
        self.assertEqual(troceo.trocear("- uno\n- dos\n- tres", 20), ["- uno - dos - tres"])

    def test_las_tildes_y_la_enie_cuentan_como_letras(self):
        self.assertEqual(troceo.trocear("ñ"), ["ñ"])


class WavTests(SimpleTestCase):
    def test_unir_dos_wav_suma_el_audio_y_un_silencio_y_deja_una_cabecera_valida(self):
        a, b = wav_de(0.5), wav_de(0.25)
        r = wav.unir([a, b], silencio_ms=150)
        info = wav.analizar(r.wav)
        self.assertEqual((info.canales, info.frecuencia, info.bits), (1, 22050, 16))
        esperado = int((0.5 + 0.25 + 0.15) * 1000)
        self.assertLessEqual(abs(r.duracion_ms - esperado), 2)
        self.assertEqual(struct.unpack_from("<I", r.wav, 4)[0], len(r.wav) - 8)
        self.assertEqual(struct.unpack_from("<I", r.wav, 40)[0], len(r.wav) - 44)

    def test_un_solo_wav_se_devuelve_igual_de_largo(self):
        r = wav.unir([wav_de(0.3)])
        self.assertEqual(len(r.wav), len(wav_de(0.3)))

    def test_lo_que_no_es_audio_se_rechaza(self):
        for basura in (b"", b"<html>502 Bad Gateway</html>" + b" " * 40, b'{"success": false}' + b" " * 40, b"RIFF" + b"\x00" * 60):
            with self.assertRaises(wav.WavInvalido):
                wav.analizar(basura)

    def test_formatos_distintos_no_se_unen(self):
        with self.assertRaises(wav.WavInvalido):
            wav.unir([wav_de(0.1, frecuencia=22050), wav_de(0.1, frecuencia=16000)])

    def test_un_wav_cortado_a_mitad_se_recorta_a_lo_que_llego(self):
        completo = wav_de(0.5)
        cortado = completo[:-1001]                                          # le falta el final y deja una muestra a medias
        info = wav.analizar(cortado)
        self.assertEqual(info.largo % 2, 0)
        self.assertLess(info.largo, len(completo) - 44)

    def test_sin_audio_no_hay_union(self):
        with self.assertRaises(wav.WavInvalido):
            wav.unir([])


class ConversacionTests(SimpleTestCase):
    PATRON = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

    def test_cumple_el_patron_del_servicio_aunque_la_pantalla_mande_cualquier_cosa(self):
        for pantalla in ("ops-abc123", "con espacios y ñ", "x" * 500, "a/b\\c?d=e&f"):
            c = conversacion.conversacion_de("u-42", pantalla)
            self.assertRegex(c, self.PATRON)

    def test_sin_id_de_pantalla_no_hay_conversacion(self):
        for vacio in (None, "", "   ", "ñññ"):
            self.assertIsNone(conversacion.conversacion_de("u-42", vacio))

    def test_dos_personas_con_el_mismo_id_de_pantalla_no_comparten_conversacion(self):
        self.assertNotEqual(conversacion.conversacion_de("u-1", "ops-abc"), conversacion.conversacion_de("u-2", "ops-abc"))
        self.assertEqual(conversacion.conversacion_de("u-1", "ops-abc"), conversacion.conversacion_de("u-1", "ops-abc"))

    def test_no_lleva_datos_personales(self):
        self.assertNotIn("1042888795", conversacion.conversacion_de("1042888795", "ops-abc"))


class ErroresTests(SimpleTestCase):
    def test_todo_codigo_del_contrato_tiene_regla_y_un_mensaje_para_la_persona(self):
        contrato = ("llm_unavailable", "llm_model_missing", "context_unavailable", "llm_timeout", "busy", "llm_error", "tts_busy", "tts_unavailable", "tts_empty_audio", "tts_timeout",
                    "voice_not_found", "internal_error")
        for codigo in contrato:
            e = errores.ErrorDeIa(codigo)
            self.assertTrue(e.mensaje and e.mensaje[0].isupper(), codigo)
            self.assertNotIn("Ollama", e.mensaje + (e.sugerencia or ""), codigo)       # sin jerga para quien usa la pantalla

    def test_lo_transitorio_es_reintentable_y_lo_de_configuracion_no(self):
        for codigo in ("ai_unreachable", "llm_unavailable", "llm_timeout", "busy", "tts_busy", "tts_timeout", "tts_unavailable", "ai_timeout"):
            self.assertTrue(errores.ErrorDeIa(codigo).reintentable, codigo)
        for codigo in ("llm_model_missing", "context_unavailable", "voice_not_found", "ai_disabled", "question_required", "empty_text"):
            self.assertFalse(errores.ErrorDeIa(codigo).reintentable, codigo)

    def test_los_estados_http(self):
        esperado = {"ai_unreachable": 503, "ai_timeout": 504, "busy": 429, "tts_busy": 429, "ai_invalid_response": 502, "question_required": 400, "empty_text": 422,
                    "llm_model_missing": 503, "ai_disabled": 503}
        for codigo, http in esperado.items():
            self.assertEqual(errores.ErrorDeIa(codigo).http, http, codigo)

    def test_un_codigo_desconocido_del_servicio_no_se_pierde_ni_rompe(self):
        e = errores.desde_servicio(503, "algo_nuevo", "mensaje")
        self.assertEqual((e.codigo, e.http), ("ai_internal", 502))
        self.assertIn("algo_nuevo", e.detalle)
        self.assertEqual(errores.desde_servicio(400, "otro", "m").codigo, "llm_error")

    def test_el_cuerpo_usa_el_formato_de_degradacion_del_nodo(self):
        cuerpo = errores.ErrorDeIa("ai_unreachable", "detalle técnico").cuerpo()
        self.assertEqual(set(cuerpo), {"detail", "codigo", "reintentable", "sugerencia"})
        self.assertNotIn("detalle técnico", str(cuerpo))                  # el detalle técnico no se le muestra a nadie
