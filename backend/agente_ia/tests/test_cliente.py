"""El cliente HTTP del servicio de IA, contra un servicio simulado por HTTP de verdad: lo que manda (UTF-8) y cómo traduce cada cosa que puede salir mal."""
from __future__ import annotations

import socket
from unittest import mock

from django.test import SimpleTestCase, override_settings

from ..dominio.errores import ErrorDeIa
from ..infraestructura import cliente as modulo_cliente
from ..infraestructura import configuracion
from ..infraestructura.cliente import ClienteIa
from .falso import DEPENDENCIAS_SANAS, ServicioIaFalso, error_servicio, respuesta_llm, wav_de


def puerto_cerrado() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


class ClienteTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ia = ServicioIaFalso()

    @classmethod
    def tearDownClass(cls):
        cls.ia.cerrar()
        super().tearDownClass()

    def setUp(self):
        self.ia.reiniciar()
        self.cliente = ClienteIa(self.ia.url, 3, 3, 1)

    def codigo(self, funcion, *args) -> ErrorDeIa:
        with self.assertRaises(ErrorDeIa) as contexto:
            funcion(*args)
        return contexto.exception

    # ---------------------------------------------------------------- lo que manda

    def test_la_pregunta_viaja_en_utf8_con_su_conversacion_y_el_contexto(self):
        self.cliente.consultar("¿Qué es AVACOM? Ñandú, canción", "lms-abc-1", 256)
        p = self.ia.de("/llm/query")[0]
        self.assertEqual(p.metodo, "POST")
        self.assertEqual(p.cabeceras["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(p.json, {"query": "¿Qué es AVACOM? Ñandú, canción", "use_avacom_context": True, "max_tokens": 256, "conversation_id": "lms-abc-1"})

    def test_sin_conversacion_no_se_manda_conversation_id(self):
        self.cliente.consultar("hola", None, 128)
        self.assertNotIn("conversation_id", self.ia.de("/llm/query")[0].json)

    def test_la_voz_pide_wav_con_su_velocidad(self):
        self.cliente.sintetizar("Hola mundo.", 0.9)
        self.assertEqual(self.ia.de("/audio/gen-voice")[0].json, {"text": "Hola mundo.", "speed": 0.9, "format": "wav"})

    # ---------------------------------------------------------------- lo que recibe

    def test_respuesta_buena_con_acentos(self):
        self.ia.programar("/llm/query", (200, respuesta_llm("Sí, ¡claro! Mañana también.")))
        self.assertEqual(self.cliente.consultar("x", None, 16)["response"], "Sí, ¡claro! Mañana también.")

    def test_la_voz_devuelve_un_wav_valido(self):
        self.assertEqual(self.cliente.sintetizar("Hola.", 1.0)[:4], b"RIFF")

    def test_las_dependencias(self):
        self.assertEqual(self.cliente.dependencias()["llm_model"]["name"], DEPENDENCIAS_SANAS["llm_model"]["name"])

    # ---------------------------------------------------------------- lo que sale mal

    def test_servicio_apagado_es_ai_unreachable(self):
        c = ClienteIa(f"http://127.0.0.1:{puerto_cerrado()}", 8, 8, 8)
        for llamada in (lambda: c.consultar("x", None, 16), c.dependencias):
            e = self.codigo(llamada)
            self.assertEqual((e.codigo, e.http, e.reintentable), ("ai_unreachable", 503, True))

    def test_el_tiempo_agotado_es_ai_timeout_y_no_deja_colgado_a_nadie(self):
        self.ia.programar("/llm/query", (200, respuesta_llm(), 1.5))
        c = ClienteIa(self.ia.url, 0.4, 0.4, 0.4)
        e = self.codigo(c.consultar, "x", None, 16)
        self.assertEqual((e.codigo, e.http), ("ai_timeout", 504))

    def test_los_errores_del_servicio_conservan_su_codigo(self):
        casos = {("llm_unavailable", 503): ("llm_unavailable", 503), ("llm_model_missing", 503): ("llm_model_missing", 503), ("busy", 429): ("busy", 429),
                 ("llm_timeout", 504): ("llm_timeout", 504), ("llm_error", 502): ("llm_error", 502), ("context_unavailable", 503): ("context_unavailable", 503)}
        for (codigo, estado), (cod_esp, http_esp) in casos.items():
            self.ia.programar("/llm/query", (estado, error_servicio(codigo, "texto del servicio")))
            e = self.codigo(self.cliente.consultar, "x", None, 16)
            self.assertEqual((e.codigo, e.http, e.origen_http), (cod_esp, http_esp, estado), codigo)

    def test_los_errores_de_voz_conservan_su_codigo(self):
        for codigo, estado in (("tts_busy", 429), ("tts_unavailable", 503), ("tts_timeout", 504), ("voice_not_found", 404), ("tts_empty_audio", 503), ("text_too_long", 422)):
            self.ia.programar("/audio/gen-voice", (estado, error_servicio(codigo)))
            e = self.codigo(self.cliente.sintetizar, "x", 1.0)
            if codigo == "text_too_long":
                self.assertEqual(e.codigo, "text_too_long")
            else:
                self.assertEqual(e.codigo, codigo, codigo)

    def test_el_422_de_validacion_de_fastapi_se_entiende(self):
        self.ia.programar("/llm/query", (422, {"detail": [{"type": "missing", "loc": ["body", "query"], "msg": "Field required"}]}))
        e = self.codigo(self.cliente.consultar, "x", None, 16)
        self.assertEqual(e.codigo, "llm_error")           # nuestro defecto, no de quien pregunta
        self.assertIn("validation_error", e.detalle)
        self.assertEqual(e.origen_http, 422)

    def test_un_5xx_con_cuerpo_html_de_un_proxy_no_rompe(self):
        self.ia.programar("/llm/query", (502, b"<html><body>502 Bad Gateway</body></html>"))
        e = self.codigo(self.cliente.consultar, "x", None, 16)
        self.assertEqual((e.codigo, e.http), ("ai_internal", 502))

    def test_un_200_que_no_es_json_es_respuesta_invalida(self):
        self.ia.programar("/llm/query", (200, b"<html>hola</html>"))
        self.assertEqual(self.codigo(self.cliente.consultar, "x", None, 16).codigo, "ai_invalid_response")

    def test_un_200_sin_texto_o_con_texto_vacio_es_respuesta_invalida(self):
        for cuerpo in ({"success": True}, {"response": ""}, {"response": "   "}, {"response": 5}, ["lista"]):
            self.ia.programar("/llm/query", (200, cuerpo))
            self.assertEqual(self.codigo(self.cliente.consultar, "x", None, 16).codigo, "ai_invalid_response", cuerpo)

    def test_un_200_de_voz_que_no_es_audio_es_respuesta_invalida(self):
        for cuerpo in (b"<html>error</html>" + b" " * 60, {"success": False}, b"RIFF" + b"\x00" * 100):
            self.ia.programar("/audio/gen-voice", (200, cuerpo))
            self.assertEqual(self.codigo(self.cliente.sintetizar, "x", 1.0).codigo, "ai_invalid_response", cuerpo)

    def test_una_respuesta_enorme_se_corta(self):
        with mock.patch.object(modulo_cliente, "TOPE_AUDIO", 1000):
            self.ia.programar("/audio/gen-voice", (200, wav_de(1.0)))
            self.assertEqual(self.codigo(self.cliente.sintetizar, "x", 1.0).codigo, "ai_invalid_response")

    def test_la_conexion_cortada_a_media_respuesta_es_ai_unreachable(self):
        """El servicio cierra el socket sin contestar (se reinició): no debe subir una excepción rara."""
        servidor = socket.socket()
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        import threading

        def cerrar():
            for _ in range(2):          # la comprobación previa de conexión y la petición de verdad
                conexion, _direccion = servidor.accept()
                conexion.settimeout(1)
                try:
                    conexion.recv(100)
                except OSError:
                    pass
                conexion.close()
        threading.Thread(target=cerrar, daemon=True).start()
        c = ClienteIa(f"http://127.0.0.1:{servidor.getsockname()[1]}", 2, 2, 1)
        self.assertEqual(self.codigo(c.consultar, "x", None, 16).codigo, "ai_unreachable")
        servidor.close()

    def test_no_usa_el_proxy_del_sistema(self):
        with mock.patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9"}):
            self.assertEqual(self.cliente.consultar("x", None, 16)["response"][:5], "¡Hola")


class ConfiguracionTests(SimpleTestCase):
    def test_por_omision_es_el_puerto_12000_del_servicio(self):
        with override_settings(AVACOM_IA_URL="", AVACOM_IA_ENV_ARCHIVO=""):
            self.assertEqual(configuracion.url_del_servicio(), "http://127.0.0.1:12000")

    def test_la_url_explicita_manda_y_se_quita_la_barra_final(self):
        with override_settings(AVACOM_IA_URL="http://127.0.0.1:13000/", AVACOM_IA_ENV_ARCHIVO=""):
            self.assertEqual(configuracion.url_del_servicio(), "http://127.0.0.1:13000")

    def test_si_el_instalador_de_la_ia_cambio_el_puerto_se_sigue_sin_reiniciar(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as carpeta:
            env = Path(carpeta) / ".env"
            env.write_text("# AVACOM Local AI\nAVACOM_HOST=0.0.0.0\nAVACOM_PORT=12345\n", encoding="utf-8")
            with override_settings(AVACOM_IA_URL="", AVACOM_IA_ENV_ARCHIVO=str(env)):
                self.assertEqual(configuracion.url_del_servicio(), "http://127.0.0.1:12345")
                env.write_text("AVACOM_PORT=12346\n", encoding="utf-8")                  # se lee en cada petición
                self.assertEqual(configuracion.url_del_servicio(), "http://127.0.0.1:12346")
                env.write_text("AVACOM_PORT=no-es-un-numero\n", encoding="utf-8")
                self.assertEqual(configuracion.url_del_servicio(), "http://127.0.0.1:12000")
            with override_settings(AVACOM_IA_URL="", AVACOM_IA_ENV_ARCHIVO=str(Path(carpeta) / "no-existe.env")):
                self.assertEqual(configuracion.url_del_servicio(), "http://127.0.0.1:12000")

    def test_en_pruebas_no_se_lee_el_equipo_real(self):
        from django.conf import settings
        self.assertEqual(settings.AVACOM_IA_ENV_ARCHIVO, "")
