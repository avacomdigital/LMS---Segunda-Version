"""
Captura las respuestas REALES de `/api/agente-ia/` como archivos para las pruebas de los clientes de C# (`tests/Avacom.Lms.Core.Tests/Fixtures/agente_ia/`). Así un campo mal escrito en un
DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía. El servicio de IA es el simulado (`falso.py`), pero lo que se captura es lo que dice el NODO.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\\projects\\prototypes\\prototype-lms-v04\\tests\\Avacom.Lms.Core.Tests\\Fixtures\\agente_ia
    .venv\\Scripts\\python manage.py test agente_ia.tests.test_capturar_contrato
"""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from .falso import DEPENDENCIAS_SANAS, error_servicio, respuesta_llm
from .test_api import RUTA, BaseIa
from .test_cliente import puerto_cerrado

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseIa):
    def guardar(self, nombre: str, respuesta, esperado: int) -> None:
        self.assertEqual(respuesta.status_code, esperado, nombre)
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(respuesta.json(), f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def test_capturar(self):
        self.ia.programar("/llm/query", (200, respuesta_llm("Mil novecientos cuarenta y tres. ¡Con gusto!")))
        self.guardar("preguntar", self.preguntar("¿Cuánto es 1943?"), 200)
        self.guardar("error_pregunta_vacia", self.preguntar(" "), 400)
        for codigo, estado_servicio, nombre in (("llm_model_missing", 503, "error_modelo_no_instalado"), ("busy", 429, "error_ocupado"), ("llm_error", 502, "error_modelo")):
            self.ia.programar("/llm/query", (estado_servicio, error_servicio(codigo)))
            self.guardar(nombre, self.preguntar(), {"error_modelo_no_instalado": 503, "error_ocupado": 429, "error_modelo": 502}[nombre])
        self.ia.programar("/llm/query", (200, respuesta_llm(), 2.5))
        self.dirigir(self.ia.url, AVACOM_IA_TIEMPO_LLM_S=0.3)
        self.guardar("error_tiempo_agotado", self.preguntar(), 504)
        self.dirigir(self.ia.url)

        self.dirigir(f"http://127.0.0.1:{puerto_cerrado()}")
        self.guardar("error_servicio_apagado", self.preguntar(), 503)
        self.guardar("estado_servicio_apagado", self.api.get(f"{RUTA}/estado/"), 200)
        self.dirigir(self.ia.url)

        self.guardar("estado", self.api.get(f"{RUTA}/estado/"), 200)
        sin_modelo = json.loads(json.dumps(DEPENDENCIAS_SANAS))
        sin_modelo["llm_model"]["installed"] = False
        self.ia.programar("/health/dependencies", (200, sin_modelo))
        self.guardar("estado_modelo_faltante", self.api.get(f"{RUTA}/estado/"), 200)

        # la voz: el cuerpo es el WAV y las cabeceras dicen cuánto dura
        r = self.hablar("¡Hola! Soy el asistente virtual de AVACOM.")
        self.assertEqual(r.status_code, 200)
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, "hablar.wav"), "wb") as f:
            f.write(r.content)
        with open(os.path.join(CARPETA, "hablar_cabeceras.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"Content-Type": r["Content-Type"], "X-Audio-Duration-Ms": r["X-Audio-Duration-Ms"], "X-Audio-Chunks": r["X-Audio-Chunks"]}, f, indent=2, sort_keys=True)
            f.write("\n")
        self.ia.programar("/audio/gen-voice", (429, error_servicio("tts_busy")))
        self.sin_espera()
        self.guardar("error_voz_ocupada", self.hablar(), 429)
        self.ia.programar("/audio/gen-voice", (200, b"<html>502</html>" + b" " * 60))
        self.guardar("error_voz_invalida", self.hablar(), 502)
        self.guardar("error_texto_sin_contenido", self.hablar("*** ---"), 422)

        from acceso.dominio.valores import Menu
        with mock.patch("agente_ia.interfaces.views.principal_de", return_value=self.principal(Menu.STUDENT)):
            self.guardar("error_sin_permiso", self.preguntar(), 403)
