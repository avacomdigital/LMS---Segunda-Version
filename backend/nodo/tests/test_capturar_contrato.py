r"""
Captura las respuestas REALES de `/api/nodo/` como archivos JSON para las pruebas de los clientes de C# (`tests/Avacom.Lms.Core.Tests/Fixtures/nodo/`). Así un campo mal escrito en un
DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\projects\prototypes\prototype-lms-v04\tests\Avacom.Lms.Core.Tests\Fixtures\nodo
    .venv\Scripts\python manage.py test nodo.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores.
"""
from __future__ import annotations

import json
import os
import unittest

from django.test import override_settings
from rest_framework.test import APIClient

from .. import models as m
from ..dominio import catalogos as cat
from ..dominio.estado import LecturaDeSalud
from ..infraestructura import contenedor
from ..infraestructura.salud import SaludFija
from .base import BaseNodoConRoles

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseNodoConRoles):
    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def test_capturar(self):
        # --- un nodo con dos consumidores, uno rezagado, y un evento apartado ---
        with override_settings(AVACOM_NODO_MAX_INTENTOS=1):
            contenedor.reiniciar()
            self.publicar_varios(8)
            al_dia = self.consumidor_de_prueba("libro", "evaluacion", tipos=("evaluacion.intento_abierto.v1",))
            al_dia.lote()
            rezagado = self.consumidor_de_prueba("reportes", "evaluacion", falla_en={3}, limite_rezago=20)
            with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                rezagado.lote(limite=4)
        contenedor.reiniciar()
        self.consumidor_de_prueba("libro", "evaluacion", tipos=("evaluacion.intento_abierto.v1",))
        self.consumidor_de_prueba("reportes", "evaluacion", limite_rezago=20)
        problema = m.Problema.objects.get()

        self.guardar("estado", self.nd("/estado/", self.tecnico))
        self.guardar("cola", self.nd("/cola/", self.tecnico))
        self.guardar("problemas", self.nd("/problemas/", self.tecnico))
        self.guardar("problemas_vacio", self.nd("/problemas/", self.tecnico, estado=cat.PR_REPROCESADO))
        self.guardar("error_sin_permiso", self.nd_post(f"/problemas/{problema.id}/reprocesar/", cliente=self.tecnico, esperado=403))
        self.guardar("error_sin_permiso_lectura", self.nd("/cola/", self.docente, esperado=403))
        self.guardar("reprocesar", self.nd_post(f"/problemas/{problema.id}/reprocesar/"))
        self.guardar("problemas_reprocesados", self.nd("/problemas/", self.tecnico, estado=cat.PR_REPROCESADO))
        self.guardar("error_problema_ya_resuelto", self.nd_post(f"/problemas/{problema.id}/reprocesar/", esperado=409))
        self.guardar("error_no_encontrado", self.nd_post("/problemas/99999/reprocesar/", esperado=404))
        self.guardar("reproducir", self.nd_post("/consumidores/reportes/reproducir/"))
        self.guardar("error_consumidor_desconocido", self.nd_post("/consumidores/nadie/reproducir/", esperado=404))
        self.guardar("cola_reconstruyendose", self.nd("/cola/", self.tecnico))
        # --- restringido: sin transaction_mode=IMMEDIATE ---
        self.s.salud = SaludFija(LecturaDeSalud(transaccion_inmediata=False, disco_libre_bytes=1_500_000_000, disco_total_bytes=256_000_000_000, wal_bytes=12_000_000))
        with self.assertLogs("avacom.nodo", level="ERROR"):
            self.guardar("estado_restringido", self.nd("/estado/", self.admin))
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            r = APIClient().get("/api/nodo/estado/")
            self.guardar("error_sesion_requerida", r.json())
        self.guardar("health", APIClient().get("/health/").json())
