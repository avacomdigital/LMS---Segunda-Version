"""
El agente de IA de punta a punta por la API del nodo (`/api/agente-ia/`), contra un servicio de IA simulado por HTTP de verdad: lo que recibe quien pregunta, lo que se asienta en la
bitácora, lo que queda en el log y —sobre todo— que NINGÚN fallo de la IA rompe nada: sin servicio, sin modelo, con tiempo agotado, con respuestas absurdas, con la bitácora caída.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from acceso.dominio.entidades import Principal
from audit.models import Bitacora

from ..aplicacion.agente import Agente
from ..dominio import wav
from ..infraestructura import configuracion, contenedor
from ..infraestructura.contenedor import _cliente_de
from ..infraestructura.registro import RegistroDeAuditoriaYLog
from .falso import DEPENDENCIAS_SANAS, ServicioIaFalso, error_servicio, respuesta_llm, wav_de
from .test_cliente import puerto_cerrado

PREGUNTA = "¿Cuánto es mil novecientos cuarenta y tres?"
RUTA = "/api/agente-ia"


class BaseIa(TestCase):
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
        self.api = APIClient()
        self.addCleanup(contenedor.reemplazar, None)
        self.dirigir(self.ia.url)

    def dirigir(self, url: str, **otros):
        ajustes = override_settings(**{"AVACOM_IA_URL": url, "AVACOM_IA_TIEMPO_LLM_S": 3, "AVACOM_IA_TIEMPO_VOZ_S": 3, "AVACOM_IA_TIEMPO_SALUD_S": 2, "AVACOM_IA_VOZ_TURNO_S": 5, **otros})
        ajustes.enable()
        self.addCleanup(ajustes.disable)

    def preguntar(self, texto=PREGUNTA, **mas):
        return self.api.post(f"{RUTA}/preguntar/", {"pregunta": texto, "conversacion": "ops-pantalla-1", **mas}, format="json")

    def hablar(self, texto="Hola. Soy el asistente.", **mas):
        return self.api.post(f"{RUTA}/hablar/", {"texto": texto, **mas}, format="json")

    @staticmethod
    def asientos(accion=None):
        consulta = Bitacora.objects.filter(modulo="agente_ia")
        return list(consulta.filter(accion=accion) if accion else consulta)

    @staticmethod
    def archivo_de_log(nombre: str) -> list[dict]:
        ruta = Path(settings.AVACOM_LMS_DIR_LOGS_EFECTIVO) / nombre
        if not ruta.exists():
            return []
        return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]

    def sin_espera(self) -> list[float]:
        """Un agente cuyas esperas de reintento no duermen de verdad; devuelve la lista donde quedan anotadas."""
        esperas: list[float] = []
        contenedor.reemplazar(Agente(configuracion.actual, _cliente_de, RegistroDeAuditoriaYLog(), threading.Lock(), dormir=esperas.append))
        return esperas


class PreguntarTests(BaseIa):
    def test_una_pregunta_se_responde_y_se_asienta_sin_su_texto(self):
        self.ia.programar("/llm/query", (200, respuesta_llm("Mil novecientos cuarenta y tres, claro.")))
        with self.assertLogs("avacom.agente_ia", level="INFO") as registros:
            r = self.preguntar()
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual((cuerpo["texto"], cuerpo["modelo"], cuerpo["contexto_usado"], cuerpo["conversacion"]), ("Mil novecientos cuarenta y tres, claro.", "qwen3:8b", True, "ops-pantalla-1"))
        self.assertGreaterEqual(cuerpo["ms"], 0)
        # lo que llegó al servicio
        recibida = self.ia.de("/llm/query")[0].json
        self.assertEqual(recibida["query"], PREGUNTA)
        self.assertRegex(recibida["conversation_id"], r"^lms-[0-9a-f]{10}-ops-pantalla-1$")
        # la bitácora: una consulta realizada, sólo con cifras
        (asiento,) = self.asientos("agente_ia.consulta_realizada")
        self.assertEqual(asiento.resultado, "ok")
        todo = json.dumps(asiento.valor_nuevo, ensure_ascii=False)
        self.assertNotIn("novecientos", todo)
        self.assertEqual(asiento.valor_nuevo["longitud_pregunta"], len(PREGUNTA))
        # el log
        evento = [x for x in registros.records if getattr(x, "evento", "") == "agente_ia.consulta"]
        self.assertEqual(len(evento), 1)
        self.assertNotIn("novecientos", evento[0].getMessage() + json.dumps(evento[0].detalle, ensure_ascii=False))

    def test_la_misma_pantalla_conserva_la_conversacion_y_otra_persona_no_la_comparte(self):
        self.preguntar(actor="ana")
        self.preguntar(actor="ana")
        self.preguntar(actor="beto")
        ids = [p.json["conversation_id"] for p in self.ia.de("/llm/query")]
        self.assertEqual(ids[0], ids[1])
        self.assertNotEqual(ids[0], ids[2])
        self.assertTrue(all(len(i) <= 64 for i in ids))

    def test_sin_id_de_pantalla_no_se_manda_conversacion(self):
        self.api.post(f"{RUTA}/preguntar/", {"pregunta": "hola"}, format="json")
        self.assertNotIn("conversation_id", self.ia.de("/llm/query")[0].json)

    # ---------------------------------------------------------------- lo que sale mal: la IA no está

    def test_con_el_servicio_apagado_se_responde_503_con_codigo_y_queda_en_bitacora_y_en_el_log(self):
        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        with self.assertLogs("avacom.agente_ia", level="WARNING") as registros:
            r = self.preguntar()
        self.assertEqual(r.status_code, 503)
        cuerpo = r.json()
        self.assertEqual((cuerpo["codigo"], cuerpo["reintentable"]), ("ai_unreachable", True))
        self.assertTrue(cuerpo["detail"] and cuerpo["sugerencia"])
        self.assertNotIn("127.0.0.1", json.dumps(cuerpo))                           # lo técnico no llega a la pantalla
        (asiento,) = self.asientos("agente_ia.consulta_fallida")
        self.assertEqual(asiento.resultado, "fallido")
        self.assertEqual(asiento.valor_nuevo["codigo"], "ai_unreachable")
        self.assertEqual(asiento.valor_nuevo["estado_http"], 503)
        self.assertNotIn("novecientos", json.dumps(asiento.valor_nuevo, ensure_ascii=False))
        registro = registros.records[0]
        self.assertEqual((registro.evento, registro.ruta, registro.canal), ("agente_ia.consulta_fallida", "sad", "comunicacion"))
        self.assertIn("127.0.0.1", registro.detalle["detalle_tecnico"])             # lo técnico sí queda en el log

    def test_el_fallo_queda_escrito_en_el_archivo_de_errores_en_json(self):
        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        previas = len([x for x in self.archivo_de_log("backend-errores.log") if x.get("evento") == "agente_ia.consulta_fallida"])     # el archivo es el de toda la corrida
        self.preguntar()
        lineas = [x for x in self.archivo_de_log("backend-errores.log") if x.get("evento") == "agente_ia.consulta_fallida"]
        self.assertEqual(len(lineas), previas + 1)
        linea = lineas[-1]
        self.assertEqual((linea["nivel"], linea["modulo"], linea["ruta"], linea["canal"]), ("WARNING", "agente_ia", "sad", "comunicacion"))
        self.assertEqual(linea["detalle"]["codigo"], "ai_unreachable")
        self.assertNotIn("novecientos", json.dumps(linea, ensure_ascii=False))

    def test_cada_codigo_del_servicio_se_traduce_y_se_asienta(self):
        casos = (("llm_unavailable", 503, 503, True), ("llm_model_missing", 503, 503, False), ("context_unavailable", 503, 503, False), ("llm_timeout", 504, 504, True),
                 ("busy", 429, 429, True), ("llm_error", 502, 502, True))
        for codigo, estado_servicio, http_esperado, reintentable in casos:
            self.ia.programar("/llm/query", (estado_servicio, error_servicio(codigo, "texto interno del servicio")))
            antes = len(self.asientos("agente_ia.consulta_fallida"))
            r = self.preguntar()
            self.assertEqual((r.status_code, r.json()["codigo"], r.json()["reintentable"]), (http_esperado, codigo, reintentable), codigo)
            self.assertNotIn("texto interno", json.dumps(r.json()), codigo)
            self.assertEqual(len(self.asientos("agente_ia.consulta_fallida")), antes + 1, codigo)

    def test_el_tiempo_agotado_se_responde_504_y_no_deja_la_pantalla_esperando(self):
        self.ia.programar("/llm/query", (200, respuesta_llm(), 2.5))
        self.dirigir(self.ia.url, AVACOM_IA_TIEMPO_LLM_S=0.4)
        r = self.preguntar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (504, "ai_timeout"))
        self.assertEqual(len(self.asientos("agente_ia.consulta_fallida")), 1)

    def test_una_respuesta_absurda_es_502_y_se_registra_como_error_de_verdad(self):
        self.ia.programar("/llm/query", (200, b"<html>no soy json</html>"))
        with self.assertLogs("avacom.agente_ia", level="ERROR") as registros:
            r = self.preguntar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (502, "ai_invalid_response"))
        self.assertEqual((registros.records[0].levelname, registros.records[0].ruta, registros.records[0].canal), ("ERROR", "bad", "aplicacion"))

    def test_un_defecto_inesperado_no_es_un_500(self):
        with mock.patch("agente_ia.infraestructura.cliente.ClienteIa.consultar", side_effect=RuntimeError("bug nuestro")):
            r = self.preguntar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (502, "ai_internal"))
        self.assertNotIn("bug nuestro", json.dumps(r.json()))
        (asiento,) = self.asientos("agente_ia.consulta_fallida")
        self.assertIn("bug nuestro", asiento.valor_nuevo["detalle_tecnico"])

    def test_un_defecto_en_la_propia_vista_tampoco_es_un_500(self):
        with mock.patch("agente_ia.interfaces.views.agente", side_effect=RuntimeError("se cayó el contenedor")):
            r = self.preguntar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (502, "ai_internal"))
        self.assertTrue(any(x.get("evento") == "agente_ia.defecto" for x in self.archivo_de_log("backend-errores.log")))

    def test_si_la_bitacora_falla_la_respuesta_sale_igual_y_el_log_lo_dice(self):
        with mock.patch("audit.servicios.anexar", side_effect=RuntimeError("bitácora caída")):
            with self.assertLogs("avacom.agente_ia", level="ERROR") as registros:
                r = self.preguntar()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(x.evento == "agente_ia.bitacora_no_disponible" for x in registros.records))

    def test_si_la_bitacora_falla_el_fallo_de_la_ia_tambien_sale_con_su_codigo(self):
        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        with mock.patch("audit.servicios.anexar", side_effect=RuntimeError("bitácora caída")):
            r = self.preguntar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (503, "ai_unreachable"))

    def test_si_el_log_falla_tampoco_se_rompe_nada(self):
        with mock.patch("agente_ia.infraestructura.registro.log") as log:
            log.log.side_effect = OSError("disco lleno")
            self.assertEqual(self.preguntar().status_code, 200)

    def test_con_la_ia_desactivada_se_dice_y_no_se_llama_al_servicio(self):
        self.dirigir(self.ia.url, AVACOM_IA_HABILITADA=False)
        r = self.preguntar()
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["reintentable"]), (503, "ai_disabled", False))
        self.assertEqual(self.ia.recibidas, [])
        self.assertEqual(len(self.asientos("agente_ia.consulta_fallida")), 1)

    # ---------------------------------------------------------------- lo que sale mal: la petición

    def test_pregunta_vacia_o_invalida(self):
        for cuerpo in ({}, {"pregunta": ""}, {"pregunta": "   \n "}, {"pregunta": 5}, {"pregunta": None}, {"pregunta": ["x"]}):
            r = self.api.post(f"{RUTA}/preguntar/", cuerpo, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "question_required"), cuerpo)
        self.assertEqual(self.ia.recibidas, [])
        self.assertEqual(self.asientos(), [])                                       # un error de quien pregunta no es un hecho que auditar

    def test_pregunta_demasiado_larga(self):
        self.assertEqual(self.preguntar("a" * 2000).status_code, 200)
        r = self.preguntar("a" * 2001)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "question_too_long"))
        self.assertEqual(len(self.ia.de("/llm/query")), 1)

    def test_un_cuerpo_que_no_es_json_no_rompe(self):
        r = self.api.post(f"{RUTA}/preguntar/", "esto no es json", content_type="application/json")
        self.assertIn(r.status_code, (400, 415))
        self.assertLess(r.status_code, 500)

    # ---------------------------------------------------------------- quién puede

    @staticmethod
    def principal(menu):
        """Un `Principal` de verdad (con el `Menu` del dominio, que es un `str`+`Enum`): el ensayo de punta a punta encontró que comparar `str(menu)` dejaba pasar a los alumnos."""
        from acceso.dominio.valores import Menu
        return Principal(usuario_id="u-1", organizacion_id="o-1", rol_id="r-1", rol_codigo=menu.name, menu=menu, nivel=1, sesion_id="s-1", clase_sesion="NORMAL", debe_cambiar_credencial=False)

    def test_una_tableta_de_alumno_no_puede(self):
        from acceso.dominio.valores import Menu
        with mock.patch("agente_ia.interfaces.views.principal_de", return_value=self.principal(Menu.STUDENT)):
            for r in (self.preguntar(), self.hablar(), self.api.get(f"{RUTA}/estado/")):
                self.assertEqual(r.status_code, 403)
        self.assertEqual(self.ia.recibidas, [])
        self.assertEqual(self.asientos(), [])

    def test_el_personal_si_puede_cualquiera_sea_su_menu_menos_alumno(self):
        from acceso.dominio.valores import Menu
        for menu in (Menu.TEACHER, Menu.ADMIN, Menu.REPORTS, Menu.TECHNICIAN):
            with mock.patch("agente_ia.interfaces.views.principal_de", return_value=self.principal(menu)):
                self.assertEqual(self.preguntar().status_code, 200, menu)

    def test_con_la_sesion_obligatoria_se_pide_sesion(self):
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.preguntar().status_code, 401)
            self.assertEqual(self.hablar().status_code, 401)
            self.assertEqual(self.api.get(f"{RUTA}/estado/").status_code, 401)


class HablarTests(BaseIa):
    def test_un_texto_corto_devuelve_un_wav_valido_con_sus_cabeceras(self):
        r = self.hablar("¡Hola! Soy el asistente virtual de AVACOM.")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "audio/wav")
        self.assertEqual(r["X-Audio-Chunks"], "1")
        info = wav.analizar(r.content)
        self.assertEqual((info.canales, info.frecuencia, info.bits), (1, 22050, 16))
        self.assertEqual(self.ia.de("/audio/gen-voice")[0].json["text"], "¡Hola! Soy el asistente virtual de AVACOM.")

    def test_un_texto_largo_se_trocea_a_450_y_se_une_en_un_solo_audio(self):
        frase = "Esta es una frase de prueba con bastantes palabras para ocupar espacio."
        texto = " ".join([frase] * 13)[:959]
        r = self.hablar(texto)
        self.assertEqual(r.status_code, 200)
        enviados = [p.json["text"] for p in self.ia.de("/audio/gen-voice")]
        self.assertEqual(len(enviados), 3)
        self.assertTrue(all(len(t) <= 450 for t in enviados))
        self.assertEqual(r["X-Audio-Chunks"], "3")
        # 3 trozos de 0,2 s + 2 silencios de 0,15 s
        self.assertLessEqual(abs(int(r["X-Audio-Duration-Ms"]) - 900), 3)
        self.assertEqual(wav.analizar(r.content).frecuencia, 22050)

    def test_pide_audio_en_la_cabecera_accept_y_no_recibe_406(self):
        r = self.api.post(f"{RUTA}/hablar/", {"texto": "Hola."}, format="json", HTTP_ACCEPT="audio/wav")
        self.assertEqual(r.status_code, 200)

    def test_la_velocidad_se_acota_a_lo_que_acepta_el_servicio(self):
        for pedida, enviada in ((1.2, 1.2), (9, 2.0), (0.1, 0.5), ("rápido", 1.0), (None, 1.0)):
            self.hablar(velocidad=pedida)
            self.assertEqual(self.ia.de("/audio/gen-voice")[-1].json["speed"], enviada, pedida)

    def test_texto_vacio_sin_contenido_o_demasiado_largo(self):
        casos = (({}, 400, "text_required"), ({"texto": "   "}, 400, "text_required"), ({"texto": "*** ---"}, 422, "empty_text"),
                 ({"texto": "a" * 3001}, 400, "text_too_long"), ({"texto": 7}, 400, "text_required"))
        for cuerpo, estado, codigo in casos:
            r = self.api.post(f"{RUTA}/hablar/", cuerpo, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (estado, codigo), cuerpo)
        self.assertEqual(self.ia.recibidas, [])

    def test_voz_ocupada_se_reintenta_sola_y_sale(self):
        esperas = self.sin_espera()
        self.ia.programar("/audio/gen-voice", (429, error_servicio("tts_busy")), (429, error_servicio("tts_busy")), (200, lambda _p: wav_de()))
        r = self.hablar()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(esperas, [0.5, 1.0])
        self.assertEqual(len(self.ia.de("/audio/gen-voice")), 3)

    def test_voz_siempre_ocupada_se_rinde_a_los_cuatro_intentos_y_lo_asienta(self):
        esperas = self.sin_espera()
        self.ia.programar("/audio/gen-voice", (429, error_servicio("tts_busy")))
        r = self.hablar()
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["reintentable"]), (429, "tts_busy", True))
        self.assertEqual((len(esperas), len(self.ia.de("/audio/gen-voice"))), (3, 4))
        self.assertEqual(len(self.asientos("agente_ia.voz_fallida")), 1)

    def test_lo_que_no_mejora_reintentando_no_se_reintenta(self):
        for codigo, estado in (("voice_not_found", 404), ("tts_unavailable", 503), ("text_too_long", 422)):
            self.ia.reiniciar()
            self.ia.programar("/audio/gen-voice", (estado, error_servicio(codigo)))
            self.hablar()
            self.assertEqual(len(self.ia.de("/audio/gen-voice")), 1, codigo)

    def test_un_trozo_sin_nada_pronunciable_no_echa_a_perder_el_resto(self):
        self.ia.programar("/audio/gen-voice", (200, lambda _p: wav_de()), (503, error_servicio("tts_empty_audio")), (200, lambda _p: wav_de()))
        texto = "Primera frase de prueba. " * 16 + "Segunda frase de prueba. " * 16 + "Tercera frase de prueba. " * 16
        r = self.hablar(texto)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["X-Audio-Chunks"], "3")
        self.assertEqual(len(self.ia.de("/audio/gen-voice")), 3)

    def test_si_ningun_trozo_se_puede_pronunciar_es_empty_text(self):
        self.ia.programar("/audio/gen-voice", (503, error_servicio("tts_empty_audio")))
        r = self.hablar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (422, "empty_text"))

    def test_un_audio_que_no_es_wav_no_llega_a_la_pantalla(self):
        self.ia.programar("/audio/gen-voice", (200, b"<html>502</html>" + b" " * 60))
        with self.assertLogs("avacom.agente_ia", level="ERROR"):
            r = self.hablar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (502, "ai_invalid_response"))
        self.assertEqual(len(self.asientos("agente_ia.voz_fallida")), 1)

    def test_servicio_apagado_en_la_voz(self):
        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        r = self.hablar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (503, "ai_unreachable"))
        self.assertEqual(self.asientos("agente_ia.voz_fallida")[0].valor_nuevo["codigo"], "ai_unreachable")

    def test_dos_voces_a_la_vez_se_hacen_cola_y_el_servicio_nunca_recibe_dos_juntas(self):
        self.ia.programar("/audio/gen-voice", (200, lambda _p: wav_de(), 0.25))
        resultados = []
        hilos = [threading.Thread(target=lambda: resultados.append(APIClient().post(f"{RUTA}/hablar/", {"texto": "Hola mundo."}, format="json").status_code)) for _ in range(3)]
        [h.start() for h in hilos]
        [h.join(20) for h in hilos]
        self.assertEqual(sorted(resultados), [200, 200, 200])
        self.assertEqual(self.ia.maximo_simultaneas["/audio/gen-voice"], 1)

    def test_la_voz_de_un_texto_largo_tiene_un_tope_total_y_no_cuelga_a_la_app(self):
        self.ia.programar("/audio/gen-voice", (200, lambda _p: wav_de(), 0.6))
        self.dirigir(self.ia.url, AVACOM_IA_TIEMPO_VOZ_TOTAL_S=1.5)
        texto = "Primera frase de prueba. " * 16 + "Segunda frase de prueba. " * 16 + "Tercera frase de prueba. " * 16 + "Cuarta frase de prueba. " * 16
        r = self.hablar(texto)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["reintentable"]), (504, "ai_timeout", True))
        self.assertLess(len(self.ia.de("/audio/gen-voice")), 4)                       # no pidió todos los trozos
        self.assertEqual(len(self.asientos("agente_ia.voz_fallida")), 1)

    def test_un_fallo_de_voz_no_pierde_el_texto_porque_son_dos_peticiones(self):
        """El texto ya se mostró con `preguntar/`; `hablar/` puede fallar sin deshacerlo."""
        self.assertEqual(self.preguntar().status_code, 200)
        self.ia.programar("/audio/gen-voice", (503, error_servicio("tts_unavailable")))
        self.assertEqual(self.hablar("Hola.").status_code, 503)
        self.assertEqual(self.preguntar().status_code, 200)                         # y la siguiente pregunta sigue funcionando


class EstadoTests(BaseIa):
    def test_servicio_sano(self):
        r = self.api.get(f"{RUTA}/estado/")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual((cuerpo["disponible"], cuerpo["voz_disponible"], cuerpo["servicio_activo"], cuerpo["modelo"], cuerpo["codigo"]), (True, True, True, "qwen3:8b", None))
        self.assertNotIn("avacom-context", json.dumps(cuerpo))                       # ni una ruta del equipo

    def test_cada_pieza_caida_se_dice_con_su_codigo_y_siempre_es_200(self):
        def con(**cambios):
            d = json.loads(json.dumps(DEPENDENCIAS_SANAS))
            for clave, valor in cambios.items():
                d[clave].update(valor)
            return d
        casos = (       # (lo que dice el servicio, el código esperado, ¿hay voz?)
            (con(ollama={"reachable": False}), "llm_unavailable", True),
            (con(llm_model={"installed": False}), "llm_model_missing", True),
            (con(context={"state": "missing"}), "context_unavailable", True),
            (con(tts_model={"loaded": False, "file_present": False}), None, False),
            (con(piper={"available": False}), None, False),
        )
        for dependencias, codigo, voz in casos:
            self.ia.programar("/health/dependencies", (200, dependencias))
            r = self.api.get(f"{RUTA}/estado/")
            cuerpo = r.json()
            self.assertEqual(r.status_code, 200)
            self.assertEqual((cuerpo["codigo"], cuerpo["disponible"], cuerpo["voz_disponible"]), (codigo, codigo is None, voz), dependencias)
            self.assertEqual(bool(cuerpo["motivo"]), codigo is not None)
            self.assertEqual(bool(cuerpo["motivo_voz"]), not voz)

    def test_un_estado_incompleto_del_servicio_cuenta_como_no_disponible(self):
        for raro in ({}, {"status": "ok"}, {"ollama": "raro", "llm_model": None}):
            self.ia.programar("/health/dependencies", (200, raro))
            cuerpo = self.api.get(f"{RUTA}/estado/").json()
            self.assertEqual((cuerpo["disponible"], cuerpo["voz_disponible"]), (False, False), raro)

    def test_servicio_apagado_es_200_con_disponible_falso(self):
        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        r = self.api.get(f"{RUTA}/estado/")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual((cuerpo["disponible"], cuerpo["servicio_activo"], cuerpo["codigo"]), (False, False, "ai_unreachable"))
        self.assertTrue(cuerpo["motivo"] and cuerpo["sugerencia"])

    def test_desactivada(self):
        self.dirigir(self.ia.url, AVACOM_IA_HABILITADA=False)
        cuerpo = self.api.get(f"{RUTA}/estado/").json()
        self.assertEqual((cuerpo["habilitada"], cuerpo["disponible"], cuerpo["codigo"]), (False, False, "ai_disabled"))

    def test_consultar_el_estado_no_llena_la_bitacora(self):
        self.api.get(f"{RUTA}/estado/")
        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        self.api.get(f"{RUTA}/estado/")
        self.assertEqual(self.asientos(), [])


class RutaTests(BaseIa):
    def test_el_agente_no_se_cuela_en_la_licencia(self):
        """No está en la tabla de rutas licenciables: ninguna licencia vencida lo apaga (y tampoco es una ruta intocable: simplemente pasa)."""
        from licenciamiento.dominio import rutas
        self.assertIsNone(rutas.capacidad_de("POST", "/api/agente-ia/preguntar/"))

    def test_los_asientos_del_agente_estan_en_el_catalogo(self):
        from audit.dominio import catalogos
        for clave in ("agente_ia.consulta_realizada", "agente_ia.consulta_fallida", "agente_ia.voz_fallida"):
            self.assertEqual(catalogos.resolver(clave).modulo, "agente_ia")
