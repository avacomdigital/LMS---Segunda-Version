r"""
Captura las respuestas REALES de `/api/licencia/` como archivos JSON (y una licencia, una solicitud y una liberación de verdad) para las pruebas de los clientes de C#
(`tests/Avacom.Lms.Core.Tests/Fixtures/licencia/`). Así un campo mal escrito en un DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\projects\prototypes\prototype-lms-v04\tests\Avacom.Lms.Core.Tests\Fixtures\licencia
    .venv\Scripts\python manage.py test licenciamiento.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores. La licencia de ejemplo está firmada con la llave de DESARROLLO (`dev-1`): sólo
la acepta un nodo de desarrollo o de pruebas.
"""
from __future__ import annotations

import json
import os
import unittest

from django.test import override_settings

from licenciamiento.dominio import licencia as lic_mod
from licenciamiento.dominio.licencia import Limites
from licenciamiento.dominio.politica import DIA_MS, HORA_MS

from . import emisor
from .base import CRUDOS_A, CRUDOS_B, L, BaseLicencia

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseLicencia):
    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def guardar_bytes(self, nombre: str, contenido: bytes) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, nombre), "wb") as f:
            f.write(contenido)

    def capturar(self, nombre: str, respuesta, esperado: int | None = None) -> dict:
        if esperado is not None:
            self.assertEqual(respuesta.status_code, esperado, respuesta.content)
        cuerpo = respuesta.json()
        self.guardar(nombre, cuerpo)
        return cuerpo

    # ---------------------------------------------------------------------------------------------------------------------------- el ciclo feliz
    def test_capturar_el_ciclo_de_vida(self):
        self.evaluar("arranque")
        self.capturar("estado_sin_licencia", self.admin.get(f"{L}/estado/"), 200)
        self.capturar("consumo", self.admin.get(f"{L}/consumo/"), 200)
        self.capturar("capacidades", self.docente.get(f"{L}/capacidades/"), 200)
        solicitud = self.capturar("solicitud", self.admin.post(f"{L}/solicitud/", {}, format="json"), 201)
        self.guardar_bytes("ejemplo.avreq", self.bytes_de(solicitud["archivo_b64"]))
        datos = self.avlic()
        self.guardar_bytes("ejemplo.avlic", datos)
        self.guardar_bytes("ejemplo-texto.avlic", lic_mod.a_texto(datos).encode("ascii"))
        self.guardar_bytes("ejemplo-alterada.avlic", datos[:60] + bytes([datos[60] ^ 1]) + datos[61:])
        self.capturar("activar", self.admin.post(f"{L}/activar/", {"licencia": lic_mod.a_texto(datos)}, format="json"), 200)
        self.capturar("estado_activa", self.admin.get(f"{L}/estado/"), 200)
        self.capturar("copia", self.admin.get(f"{L}/copia/"), 200)
        self.capturar("renovar", self.activar(via="renovar", serie=2, emitida=self.t0 - DIA_MS, vence=self.t0 + 700 * DIA_MS), 200)
        self.capturar("reactivar", self.activar(via="activar", serie=2, emitida=self.t0 - DIA_MS, vence=self.t0 + 700 * DIA_MS), 200)
        liberada = self.capturar("liberar", self.admin.post(f"{L}/liberar/", {}, format="json"), 201)
        self.guardar_bytes("ejemplo.avrel", self.bytes_de(liberada["archivo_b64"]))
        self.capturar("estado_tras_liberar", self.admin.get(f"{L}/estado/"), 200)

    # ---------------------------------------------------------------------------------------------------------------------------- los estados que ve el administrador
    def test_capturar_los_estados(self):
        self.activar_ok(vence=self.t0 + 12 * DIA_MS, limites=Limites(equipos=2, usuarios=4, concurrentes_normal=50, concurrentes_pico=100))
        self.capturar("estado_por_vencer_y_cupo", self.admin.get(f"{L}/estado/"), 200)          # 12 días: aviso por_vencer; 1 de 2 equipos y 3 de 4 usuarios: sin aviso de cupo aún
        self.capturar("consumo_con_limites", self.admin.get(f"{L}/consumo/"), 200)
        self.reloj.avanzar(20 * DIA_MS)
        self.evaluar("tick")
        self.capturar("estado_gracia", self.admin.get(f"{L}/estado/"), 200)
        self.reloj.avanzar(40 * DIA_MS)
        self.evaluar("tick")
        self.capturar("estado_degradada", self.admin.get(f"{L}/estado/"), 200)
        self.capturar("capacidades_degradada", self.docente.get(f"{L}/capacidades/"), 200)
        self.capturar("error_modulo_no_disponible", self.admin.get("/api/reportes/clases/"), 402)

    def test_capturar_huella_distinta_parcial_y_reloj(self):
        self.activar_ok()
        self.huella.valores = {**CRUDOS_A, 3: "BRD-NUEVA-0001"}
        self.evaluar("tick")
        self.capturar("estado_huella_parcial", self.admin.get(f"{L}/estado/"), 200)
        self.huella.valores = dict(CRUDOS_B)
        self.evaluar("tick")
        self.capturar("estado_huella_distinta", self.admin.get(f"{L}/estado/"), 200)
        self.huella.valores = dict(CRUDOS_A)
        self.reloj.avanzar(HORA_MS)
        self.evaluar("tick")
        self.reloj.avanzar(10 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(-8 * DIA_MS)
        self.capturar("estado_reloj_retroceso", self.admin.get(f"{L}/estado/"), 200)
        self.reloj.saltar(40 * DIA_MS)
        self.evaluar("tick")
        self.capturar("estado_reloj_salto", self.admin.get(f"{L}/estado/"), 200)
        self.capturar("reloj_confirmar", self.admin.post(f"{L}/reloj/confirmar/", {}, format="json"), 200)

    def test_capturar_liberacion_pendiente_e_instalacion(self):
        self.activar_ok(liberacion_pendiente=True, liberacion_dias=14)
        self.capturar("estado_liberacion_pendiente", self.admin.get(f"{L}/estado/"), 200)
        self.huella.valores = {1: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", 2: "03000200-0400-0500-0006-000700080009", 3: "Default string", 4: "To be filled by O.E.M."}
        self.capturar("solicitud_instalacion", self.admin.post(f"{L}/solicitud/", {}, format="json"), 201)

    def test_capturar_el_cupo(self):
        self.activar_ok(limites=Limites(equipos=2, usuarios=4, concurrentes_normal=1, concurrentes_pico=2))
        self.capturar("estado_cupo_casi_lleno", self.admin.get(f"{L}/estado/"), 200)        # 1 de 2 equipos (50 %) y 3 de 4 usuarios (75 %): todavía sin aviso
        self.api.post("/api/dispositivos/", {"identificador": "tab-02", "nombre": "tab-02"}, format="json")
        self.capturar("error_cupo_equipos", self.api.post("/api/dispositivos/", {"identificador": "tab-03", "nombre": "tab-03"}, format="json"), 402)
        self.admin.post("/api/acceso/usuarios/", {"rol": "STUDENT", "alias": "Nuevo 1", "persona": {"nombres": "Nuevo", "apellidos": "Uno"},
                                                  "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "800001", "es_login": True}], "secreto": "4321", "secreto_definitivo": True,
                                                  "grupo_id": self.grupo["id"]}, format="json")
        self.capturar("error_cupo_usuarios", self.admin.post("/api/acceso/usuarios/", {"rol": "STUDENT", "alias": "Nuevo 2", "persona": {"nombres": "Nuevo", "apellidos": "Dos"},
                                                                                        "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "800002", "es_login": True}],
                                                                                        "secreto": "4321", "secreto_definitivo": True, "grupo_id": self.grupo["id"]}, format="json"), 402)
        self.evaluar("tick")
        self.capturar("estado_cupo_lleno", self.admin.get(f"{L}/estado/"), 200)

    # ---------------------------------------------------------------------------------------------------------------------------- los errores
    def test_capturar_los_errores(self):
        self.capturar("error_sin_licencia_para_renovar", self.activar(via="renovar", serie=2), 400)
        self.capturar("error_sin_licencia_para_liberar", self.admin.post(f"{L}/liberar/", {}, format="json"), 409)
        self.capturar("error_sin_licencia_para_copiar", self.admin.get(f"{L}/copia/"), 404)
        self.capturar("error_huella_no_coincide", self.activar(huella=emisor.huella_de(self.factores(CRUDOS_B))), 409)
        datos = bytearray(self.avlic())
        datos[40] ^= 1
        self.capturar("error_firma_invalida", self.admin.post(f"{L}/activar/", {"licencia": lic_mod.a_texto(bytes(datos))}, format="json"), 400)
        self.capturar("error_texto_invalido", self.admin.post(f"{L}/activar/", {"licencia": "AVL1.@@@"}, format="json"), 400)
        self.capturar("error_sin_cuerpo", self.admin.post(f"{L}/activar/", {}, format="json"), 400)
        self.activar_ok()
        self.capturar("error_otra_licencia", self.activar(id="12345678-1234-4234-8234-123456789abc"), 400)
        self.capturar("error_serie_no_posterior", self.activar(via="renovar", serie=1), 400)
        self.capturar("error_aun_no_vigente", self.activar(via="renovar", serie=3, emitida=self.t0 + DIA_MS, desde=self.t0 + 20 * DIA_MS, vence=self.t0 + 400 * DIA_MS), 400)
        self.capturar("error_sin_permiso", self.docente.get(f"{L}/estado/"), 403)
        self.capturar("error_sin_permiso_renovar", self.activar(cliente=self.tecnico(), via="renovar", serie=3, emitida=self.t0 + DIA_MS), 403)
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            from rest_framework.test import APIClient
            self.capturar("error_sesion_requerida", APIClient().get(f"{L}/estado/"), 401)
