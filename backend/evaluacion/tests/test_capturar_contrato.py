"""
Captura las respuestas REALES de `/api/evaluacion/` como archivos JSON para las pruebas de los clientes de C# (`tests/Avacom.Lms.Core.Tests/Fixtures/evaluacion/`).
Así un campo mal escrito en un DTO de C# se descubre contra el backend de verdad y no contra lo que alguien creyó que devolvía.

No hace nada en una corrida normal. Para regenerar los archivos:

    set AVACOM_CAPTURAR_CONTRATO=C:\\projects\\prototypes\\prototype-lms-v04\\tests\\Avacom.Lms.Core.Tests\\Fixtures\\evaluacion
    .venv\\Scripts\\python manage.py test evaluacion.tests.test_capturar_contrato

Los identificadores y las horas cambian en cada corrida: las pruebas de C# comprueban la FORMA, no esos valores.
"""
from __future__ import annotations

import json
import os
import unittest

from .base import BASE, MIN, BaseEvaluacion, respuesta_correcta

CARPETA = os.environ.get("AVACOM_CAPTURAR_CONTRATO", "")


@unittest.skipUnless(CARPETA, "AVACOM_CAPTURAR_CONTRATO no está definida: no se capturan archivos")
class CapturarContratoTests(BaseEvaluacion):
    def guardar(self, nombre: str, cuerpo) -> None:
        os.makedirs(CARPETA, exist_ok=True)
        with open(os.path.join(CARPETA, f"{nombre}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(cuerpo, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def get(self, ruta: str, esperado: int = 200, **params) -> dict:
        r = self.api.get(f"{BASE}{ruta}", params)
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def post(self, ruta: str, cuerpo: dict, esperado: int | tuple = (200, 201)) -> dict:
        r = self.api.post(f"{BASE}{ruta}", cuerpo, format="json")
        self.assertIn(r.status_code, esperado if isinstance(esperado, tuple) else (esperado,), r.content)
        return r.json()

    def test_capturar(self):
        with self.examen_de_banco_fijo():
            # ---- el profesor aplica el examen con la tableta de Juan por DEBAJO del nivel: queda en espera de admisión (202)
            controlado = self.crear_asignacion("controlado", tiempo={"modo": "fijo", "limite_seg": 600})
            self.guardar("asignacion", controlado)
            # la elegibilidad sólo juzga las tabletas que ya se conocen: la de Juan queda asignada a su nombre
            r = self.api.post(f"/api/dispositivos/{self.tableta_juan['id']}/asignar/", {"alumno_id": self.estudiante_id, "actor": self.docente_id}, format="json")
            self.assertIn(r.status_code, (200, 201), r.content)
            self.guardar("elegibilidad", self.ver(f"/asignaciones/{controlado['id']}/elegibilidad/"))
            self.guardar("apertura_espera", self.post(f"/asignaciones/{controlado['id']}/intentos/", self.alumno(), esperado=202))
            self.guardar("admisiones", self.ver(f"/asignaciones/{controlado['id']}/admisiones/"))
            adm = self.ver(f"/asignaciones/{controlado['id']}/admisiones/")["admisiones"][0]
            self.guardar("admision_decidida", self.accion(f"/asignaciones/{controlado['id']}/admisiones/{adm['id']}/decidir/", {
                "decision": "admitir", "nivel_admitido": "supervisado", "motivo": "La tableta aún no está aprovisionada"}))
            self.accion(f"/asignaciones/{controlado['id']}/cerrar/")

            # ---- el examen supervisado completo
            a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 900}, resultados="tras_liberar")
            self.guardar("estudiantes", self.get("/estudiantes/"))
            self.guardar("mias", self.get("/mias/", **self.alumno()))
            self.guardar("antesala", self.get(f"/asignaciones/{a['id']}/antesala/", **self.alumno()))
            apertura = self.post(f"/asignaciones/{a['id']}/intentos/", {**self.alumno(), "nombre": "Tableta de Juan", "plataforma": "android",
                                                                        "capacidad_control": "supervisado"}, esperado=201)
            self.guardar("apertura", apertura)
            i = apertura["intento"]["id"]
            preguntas = self.get(f"/intentos/{i}/preguntas/", **self.alumno())
            self.guardar("preguntas", preguntas)
            refs = [p["pregunta_ref"] for p in preguntas["preguntas"]]
            self.guardar("estado", self.get(f"/intentos/{i}/estado/", **self.alumno()))
            self.avanzar(seg=5)
            self.guardar("latido", self.post(f"/intentos/{i}/latido/", {**self.alumno(), "pregunta_actual": refs[0], "transcurrido_ms": 5000,
                                                                       "capacidad_control": "supervisado", "bateria_pct": 80}))
            self.guardar("acuse_respuestas", self.post(f"/intentos/{i}/respuestas/", {**self.alumno(), "respuestas": [
                {"pregunta_ref": refs[0], "secuencia": 1, "respuesta": respuesta_correcta(refs[0])},
                {"pregunta_ref": "l3-q-que-no-existe", "secuencia": 2, "respuesta": {"value": True}}]}))
            self.guardar("acuse_incidentes", self.post(f"/intentos/{i}/incidentes/", {**self.alumno(), "incidentes": [
                {"tipo": "salida_de_app", "ref_cliente": "c-1", "detalle": {"segundos": 4}}]}))
            self.guardar("acuse_bloqueo", self.post(f"/intentos/{i}/bloqueo/", {**self.alumno(), "resultado": "aplicado", "capas": {"app": True}}))
            self.guardar("panel", self.ver(f"/asignaciones/{a['id']}/panel/"))
            self.guardar("expediente", self.ver(f"/intentos/{i}/"))
            self.guardar("error_confirmacion", self.post(f"/intentos/{i}/entregar/", self.alumno(), esperado=409))
            # un corte largo: el intento queda suspendido y el latido lo dice
            self.avanzar(minutos=2)
            self.guardar("estado_suspendido", self.get(f"/intentos/{i}/estado/", **self.alumno()))
            self.guardar("reactivacion", self.accion(f"/intentos/{i}/reactivar/"))
            for ref in refs[1:]:
                self.post(f"/intentos/{i}/respuestas/", {**self.alumno(), "respuestas": [
                    {"pregunta_ref": ref, "secuencia": 1, "respuesta": respuesta_correcta(ref)}]})
            self.guardar("entrega", self.post(f"/intentos/{i}/entregar/", {**self.alumno(), "confirmar": True}))
            self.guardar("revision", self.ver(f"/intentos/{i}/revision/"))
            tipos = self.fila(i).armado_meta["tipos"]
            for ref in [r for r in refs if tipos[r] == "open"]:
                self.guardar("puntaje", self.accion(f"/intentos/{i}/respuestas/{ref}/puntuar/", {"puntaje": 1.0, "comentario": "Completa"}))
            self.guardar("publicado", self.accion(f"/intentos/{i}/publicar/"))
            self.guardar("resultados", self.ver(f"/asignaciones/{a['id']}/resultados/"))
            self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
            self.guardar("resultado", self.get(f"/intentos/{i}/resultado/", **self.alumno()))
            self.guardar("lista_asignaciones", self.ver("/asignaciones/"))
