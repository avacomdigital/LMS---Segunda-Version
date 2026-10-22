r"""
Captura las respuestas REALES de `/api/actualizacion/` como archivos JSON (y un `.avupd` de verdad, firmado con la llave de desarrollo) para las pruebas de los clientes de C#
(`tests/Avacom.Lms.Core.Tests/Fixtures/actualizacion/`, Fase 3) y para `02-api.md`. Así un campo mal escrito en un DTO se descubre contra el backend de verdad.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\projects\prototypes\prototype-lms-v04\tests\Avacom.Lms.Core.Tests\Fixtures\actualizacion
    .venv\Scripts\python manage.py test actualizacion.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores.
"""
from __future__ import annotations

import json
import os
import unittest

from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import manifiesto as mf

from . import emisor
from .base import A, BaseActualizacion

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseActualizacion):
    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def capturar(self, nombre: str, respuesta, esperado: int | None = None) -> dict:
        if esperado is not None:
            self.assertEqual(respuesta.status_code, esperado, respuesta.content)
        cuerpo = respuesta.json()
        self.guardar(nombre, {"status": respuesta.status_code, "cuerpo": cuerpo})
        return cuerpo

    def test_capturar_el_ciclo_de_vida(self):
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, "ejemplo.avupd"), "wb") as f:
            f.write(self.avupd())
        self.guardar("manifiesto_ejemplo", mf.a_dict(emisor.manifiesto_de_ejemplo(version_producto=self.version_nueva, version_minima=self.version_instalada)))
        self.capturar("estado_al_dia", self.admin.get(f"{A}/estado/"), 200)
        self.dejar_en_usb(self.avupd())
        paquetes = self.capturar("paquetes_con_candidato", self.admin.get(f"{A}/paquetes/"), 200)
        importado = self.capturar("importar_201", self.admin.post(f"{A}/paquetes/importar/", {"candidato": paquetes["candidatos"][0]["id"]}, format="json"), 201)
        pid = importado["paquete_id"]
        self.capturar("paquetes_importado", self.admin.get(f"{A}/paquetes/"), 200)
        self.capturar("paquete_verificado", self.admin.get(f"{A}/paquetes/{pid}/"), 200)
        self.capturar("programar_200", self.admin.post(f"{A}/paquetes/{pid}/programar/", {"desde": self.reloj.t + 30 * cat.MINUTO_MS, "hasta": self.reloj.t + 90 * cat.MINUTO_MS}, format="json"), 200)
        self.capturar("estado_programado", self.admin.get(f"{A}/estado/"), 200)
        self.capturar("desprogramar_200", self.admin.post(f"{A}/paquetes/{pid}/desprogramar/", {}, format="json"), 200)
        aplicado = self.capturar("aplicar_202", self.admin.post(f"{A}/paquetes/{pid}/aplicar/", {}, format="json"), 202)
        self.guardar("orden_json", self.orden())
        self.capturar("estado_aplicando", self.admin.get(f"{A}/estado/"), 200)
        self.capturar("health_aplicando", self.api.get("/health/"), 200)
        self.capturar("inicio_de_clase_503", self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json"), 503)
        self.capturar("aplicar_409_en_curso", self.admin.post(f"{A}/paquetes/{pid}/aplicar/", {}, format="json"), 409)
        self.resultado_del_host(aplicado["orden"]["orden_id"], pid)
        with open(os.path.join(CARPETA, "resultado_json.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(json.loads((self.carpeta / cat.ARCHIVO_RESULTADO).read_text(encoding="utf-8")), f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        self.tick()
        self.capturar("paquete_aplicado", self.admin.get(f"{A}/paquetes/{pid}/"), 200)
        self.capturar("estado_aplicado", self.admin.get(f"{A}/estado/"), 200)
        revertido = self.capturar("revertir_202", self.admin.post(f"{A}/paquetes/{pid}/revertir/", {"nota": "el boletín sale en blanco"}, format="json"), 202)
        self.resultado_del_host(revertido["orden"]["orden_id"], pid, resultado=cat.R_REVERTIDO, accion=cat.ACCION_REVERTIR)
        self.tick()
        self.capturar("paquete_revertido", self.admin.get(f"{A}/paquetes/{pid}/"), 200)
        self.capturar("historial", self.admin.get(f"{A}/historial/"), 200)

    def test_capturar_los_errores(self):
        self.capturar("importar_404_candidato", self.admin.post(f"{A}/paquetes/importar/", {"candidato": "no-existe"}, format="json"), 404)
        self.capturar("importar_400_sin_candidato", self.admin.post(f"{A}/paquetes/importar/", {}, format="json"), 400)
        manifiesto = mf.escribir(emisor.manifiesto_de_ejemplo(version_producto=self.version_nueva, version_minima=self.version_instalada))
        self.capturar("importar_422_sin_firma", self.importar(emisor.empaquetar(manifiesto, None, emisor.archivos_de_ejemplo()), nombre="sin-firma.avupd"), 422)
        datos = bytearray(self.avupd())
        datos[len(datos) // 2] ^= 0xFF
        self.capturar("importar_422_alterado", self.importar(bytes(datos), nombre="alterado.avupd"), 422)
        self.capturar("importar_422_kid_desconocido", self.importar(self.avupd(kid="prod-2030-1"), nombre="kid.avupd"), 422)
        incompatible = self.capturar("importar_201_incompatible", self.importar(self.avupd(paquete_id="17171717-0009-4000-8000-000000000009", requisitos=mf.Requisitos(contrato_biblioteca=3)),
                                                                                nombre="incompatible.avupd"), 201)
        self.capturar("aplicar_409_contrato_incompatible", self.admin.post(f"{A}/paquetes/{incompatible['paquete_id']}/aplicar/", {}, format="json"), 409)
        ficha = self.importar_ok()
        libre = self.s.almacen.espacio_libre
        self.s.almacen.espacio_libre = lambda: 10
        self.capturar("aplicar_409_espacio_insuficiente", self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/aplicar/", {}, format="json"), 409)
        self.s.almacen.espacio_libre = libre
        self.abrir_clase()
        self.capturar("aplicar_409_sesion_activa", self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/aplicar/", {}, format="json"), 409)
        self.capturar("revertir_409_estado_invalido", self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "x"}, format="json"), 409)
        self.capturar("programar_400", self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/programar/", {"desde": 1, "hasta": 2}, format="json"), 400)
        tecnico = self.tecnico()
        self.capturar("aplicar_403_tecnico", tecnico.post(f"{A}/paquetes/{ficha['paquete_id']}/aplicar/", {}, format="json"), 403)
        self.capturar("estado_403_docente", self.docente.get(f"{A}/estado/"), 403)
        self.capturar("paquete_404", self.admin.get(f"{A}/paquetes/no-existe/"), 404)
