r"""
Captura las respuestas REALES de `/api/licencia/identidad/` (Fase 5) como JSON para las pruebas de los clientes de C# (`tests/Avacom.Lms.Core.Tests/Fixtures/identidad/`), igual que
`test_capturar_contrato.py` hace con el resto de la licencia. No hace nada en una corrida normal. Para regenerar:

    set AVACOM_CAPTURAR_CONTRATO_IDENTIDAD=C:\projects\prototypes\prototype-lms-v04\tests\Avacom.Lms.Core.Tests\Fixtures\identidad
    .venv\Scripts\python manage.py test licenciamiento.tests.test_capturar_contrato_identidad

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA.
"""
from __future__ import annotations

import json
import os
import unittest

from . import atestacion_apoyo as ap
from .test_identidad import HW, BaseIdentidad

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO_IDENTIDAD", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO_IDENTIDAD no está definida: no se capturan archivos")
class CapturarContratoIdentidadTests(BaseIdentidad):
    def guardar(self, nombre: str, respuesta, esperado: int) -> dict:
        self.assertEqual(respuesta.status_code, esperado, respuesta.content)
        os.makedirs(CARPETA, exist_ok=True)
        cuerpo = respuesta.json()
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        return cuerpo

    def test_capturar(self):
        from .base import L
        self.registrar()
        self.guardar("reto", self.api.post(f"{L}/identidad/reto/", {}, format="json"), 201)
        nonce = self.reto()
        self.guardar("enrolar_software", self.enrolar(nonce=nonce), 200)
        self.reloj.avanzar(60_000)
        self.guardar("enrolar_confirmada", self.enrolar(), 200)
        self.guardar("error_clave_distinta", self.enrolar(entorno=ap.Entorno()), 409)
        self.guardar("error_reto_invalido", self.enrolar(nonce=bytes(32)), 400)
        self.guardar("error_identidad_invalida", self.enrolar(firma=b"basura"), 400)
        self.guardar("error_equipo_no_registrado", self.enrolar("student-fantasma-00000000"), 404)
        dm = next(d for d in self.admin.get("/api/dispositivos/").json() if d["identificador_hw"] == HW)
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, "dispositivo_con_garantia.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(dm, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        # un equipo con atestación completa
        self.registrar("student-tableta-11112222")
        n2 = self.reto()
        e2 = ap.Entorno()
        self.e = e2
        self.s.atestacion.e = e2
        e2.raices[:] = [ap.at.Raiz("prueba", e2.raices[0].spki, 0, 2**62)]
        self.guardar("enrolar_hardware", self.enrolar("student-tableta-11112222", nonce=n2, entorno=e2, cadena=e2.cadena(ap.extension(reto=n2))), 200)
