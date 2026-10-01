"""
Pruebas del expediente: inscripción, aperturas del visor, progreso monotónico,
intentos con corrección delegada, consolidado docente, degradación y rechazos.
"""
from __future__ import annotations

import os
import tempfile

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tools.host_biblioteca_pruebas import HostBibliotecaPruebas

from .models import Auditoria, Inscripcion, Intento, ProgresoLeccion

MAT = "co-secundaria-8-matematicas"


class ConHost(TestCase):
    capacidades: list[str] | None = None

    def setUp(self):
        self.carpeta = tempfile.mkdtemp(prefix="avacom-lms-")
        self.ruta_enlace = os.path.join(self.carpeta, "enlace.json")
        self.host = HostBibliotecaPruebas(self.ruta_enlace, capacidades=self.capacidades).iniciar()
        self._ajuste = override_settings(AVACOM_CONTENIDO_ENLACE=self.ruta_enlace)
        self._ajuste.enable()
        self.api = APIClient()

    def tearDown(self):
        self._ajuste.disable()
        self.host.detener()

    def abrir(self, ref, seccion="co-sec-mat-dba-8-05", persona="ethan-martinez", tipo="documento"):
        return self.api.post("/api/aperturas/", {
            "curso_ref": MAT, "persona_id": persona, "persona_rotulo": "Ethan Martínez",
            "leccion_codigo": seccion, "elemento_ref": ref, "version_elemento": "1", "tipo": tipo,
            "elemento_rotulo": "x", "dispositivo": "tableta-01",
        }, format="json")


class AperturasYProgresoTests(ConHost):
    def test_abrir_un_material_inscribe_y_avanza_la_seccion(self):
        r = self.abrir("co-sec-mat-doc-funcion")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["progreso_seccion"], 50.0)   # 1 de 2 items de DBA-8-05
        self.assertTrue(Inscripcion.objects.filter(curso_ref=MAT, persona_id="ethan-martinez").exists())
        self.assertEqual(Inscripcion.objects.get(curso_ref=MAT, persona_id="ethan-martinez").curso_rotulo, "Matemáticas · Grado 8")

        r = self.api.get(f"/api/biblioteca/cursos/{MAT}/?persona=ethan-martinez")
        seccion = next(s for s in r.json()["secciones"] if s["codigo"] == "co-sec-mat-dba-8-05")
        self.assertEqual(seccion["progreso"], 50.0)
        self.assertTrue(next(i for i in seccion["items"] if i["elemento_ref"] == "co-sec-mat-doc-funcion")["abierto"])

        # abrir el segundo completa la sección y sella
        self.abrir("co-sec-mat-int-grafica", tipo="interactivo")
        fila = ProgresoLeccion.objects.get(curso_ref=MAT, persona_id="ethan-martinez", leccion_codigo="co-sec-mat-dba-8-05")
        self.assertEqual(fila.estado, "completada")
        self.assertIsNotNone(fila.completado_en)
        # el promedio del curso se calcula sobre las 3 secciones vigentes
        r = self.api.get(f"/api/students/ethan-martinez/courses/{MAT}/progress/")
        self.assertAlmostEqual(r.json()["progreso"], 33.33, places=1)

    def test_el_progreso_nunca_disminuye(self):
        self.abrir("co-sec-mat-doc-funcion")
        r = self.api.post(f"/api/students/ethan-martinez/courses/{MAT}/progress/",
                          {"leccion_codigo": "co-sec-mat-dba-8-05", "porcentaje": 10}, format="json")
        self.assertEqual(r.json()["porcentaje"], 50.0)
        r = self.api.post(f"/api/students/ethan-martinez/courses/{MAT}/progress/",
                          {"leccion_codigo": "co-sec-mat-dba-8-05", "porcentaje": 100}, format="json")
        self.assertEqual(r.json()["estado"], "completada")

    def test_cerrar_apertura_registra_tiempo(self):
        pk = self.abrir("co-sec-mat-video-pendiente", seccion="co-sec-mat-dba-8-06", tipo="video").json()["id"]
        r = self.api.post(f"/api/aperturas/{pk}/cerrar/", {"progreso_pct": 80}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["progreso_pct"], 80)
        self.assertIsNotNone(r.json()["cerrado_en"])

    def test_los_cursos_del_estudiante_traen_progreso(self):
        self.abrir("co-sec-mat-doc-funcion")
        r = self.api.get("/api/students/ethan-martinez/courses/")
        self.assertTrue(r.json()["disponible"])
        mat = next(c for c in r.json()["cursos"] if c["curso_ref"] == MAT)
        self.assertTrue(mat["inscrito"])
        self.assertGreater(mat["progreso"], 0)
        # el otro curso se ofrece aunque no esté inscrito
        self.assertEqual(len(r.json()["cursos"]), 2)


class DegradacionTests(ConHost):
    def test_expediente_legible_con_la_biblioteca_cerrada(self):
        self.abrir("co-sec-mat-doc-funcion")
        self.host.detener()
        r = self.api.get("/api/students/ethan-martinez/courses/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["disponible"])
        self.assertTrue(r.json()["aviso"])
        curso = r.json()["cursos"][0]
        self.assertEqual(curso["titulo"], "Matemáticas · Grado 8")   # rótulo histórico
        self.assertIsNone(curso["disponible"])                       # no se pudo comprobar ≠ no está
        self.assertGreater(curso["progreso"], 0)
        # la estructura en vivo sí degrada con 503
        self.assertEqual(self.api.get(f"/api/biblioteca/cursos/{MAT}/").status_code, 503)

    def test_curso_retirado_se_explica_con_fecha(self):
        self.abrir("co-sec-mat-doc-funcion")
        self.host.catalogo["cursos"] = [c for c in self.host.catalogo["cursos"] if c["curso_ref"] != MAT]
        r = self.api.get("/api/students/ethan-martinez/courses/")
        mat = next(c for c in r.json()["cursos"] if c["curso_ref"] == MAT)
        self.assertFalse(mat["disponible"])
        self.assertIn("No disponible desde", mat["aviso"])
        self.assertTrue(Auditoria.objects.filter(accion="disponibilidad.desaparecio").exists())
        # y vuelve
        self.host.catalogo = __import__("tools.host_biblioteca_pruebas", fromlist=["x"]).catalogo_por_defecto()
        r = self.api.get("/api/students/ethan-martinez/courses/")
        self.assertTrue(next(c for c in r.json()["cursos"] if c["curso_ref"] == MAT)["disponible"])
        self.assertTrue(Auditoria.objects.filter(accion="disponibilidad.reaparecio").exists())

    def test_una_apertura_sin_biblioteca_se_registra_sin_inventar_progreso(self):
        self.host.detener()
        r = self.abrir("co-sec-mat-doc-funcion")
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.json()["estructura_disponible"])
        self.assertEqual(r.json()["progreso_seccion"], 0.0)


class IntentosTests(ConHost):
    def iniciar(self):
        return self.api.post("/api/intentos/start/", {
            "evaluacion_ref": "co-sec-mat-eval-funcion", "persona_id": "sofia-torres", "persona_rotulo": "Sofía Torres",
            "curso_ref": MAT, "leccion_codigo": "co-sec-mat-var-e1", "dispositivo": "tableta-02",
        }, format="json")

    def test_flujo_completo_con_correccion_delegada(self):
        r = self.iniciar()
        self.assertEqual(r.status_code, 201)
        intento = r.json()
        self.assertEqual(len(intento["preguntas"]), 3)
        self.assertNotIn("clave", r.content.decode().lower())
        self.assertTrue(intento["puede_corregir"])

        # reanudar devuelve el mismo intento
        self.assertEqual(self.iniciar().json()["id"], intento["id"])

        r = self.api.post("/api/intentos/answer/", {"intento_id": intento["id"], "pregunta_ref": "pr-001", "respuesta": "3"}, format="json")
        self.assertTrue(r.json()["acierta"])
        self.assertIn("multiplica", r.json()["retroalimentacion"])
        r = self.api.post("/api/intentos/answer/", {"intento_id": intento["id"], "pregunta_ref": "pr-002", "respuesta": "verdadero"}, format="json")
        self.assertFalse(r.json()["acierta"])
        # idempotente: corregir la respuesta no duplica filas
        r = self.api.post("/api/intentos/answer/", {"intento_id": intento["id"], "pregunta_ref": "pr-002", "respuesta": "falso"}, format="json")
        self.assertTrue(r.json()["acierta"])
        self.assertEqual(Intento.objects.get(pk=intento["id"]).respuestas.count(), 2)
        # la abierta no se corrige: queda pendiente
        r = self.api.post("/api/intentos/answer/", {"intento_id": intento["id"], "pregunta_ref": "pr-003", "respuesta": "texto libre"}, format="json")
        self.assertIsNone(r.json()["acierta"])

        r = self.api.post("/api/intentos/finish/", {"intento_id": intento["id"]}, format="json")
        self.assertEqual(r.json()["estado"], "pendiente_correccion")
        self.assertEqual(r.json()["puntaje"], 100.0)   # ponderado sobre las corregibles (1+1 de 2)
        self.assertEqual(r.json()["aciertos"], 2)
        # finalizar dos veces conserva una sola nota
        r2 = self.api.post("/api/intentos/finish/", {"intento_id": intento["id"]}, format="json")
        self.assertEqual(r2.json()["finalizado_en"], r.json()["finalizado_en"])
        # y la evaluación cuenta como completada en la sección
        fila = ProgresoLeccion.objects.get(curso_ref=MAT, persona_id="sofia-torres", leccion_codigo="co-sec-mat-var-e1")
        self.assertEqual(float(fila.porcentaje), 50.0)   # 1 de 2 items (evaluación + lección)

        detalle = self.api.get(f"/api/resultados/{intento['id']}/").json()
        self.assertEqual(len(detalle["preguntas"]), 3)
        self.assertNotIn("clave", str(detalle).lower())

    def test_una_corregible_sin_responder_cuenta_como_error(self):
        pk = self.iniciar().json()["id"]
        self.api.post("/api/intentos/answer/", {"intento_id": pk, "pregunta_ref": "pr-001", "respuesta": "3"}, format="json")
        r = self.api.post("/api/intentos/finish/", {"intento_id": pk}, format="json")
        # pr-001 bien (1), pr-002 sin responder (error, 1), pr-003 abierta (pendiente)
        self.assertEqual(r.json()["puntaje"], 50.0)
        self.assertEqual(r.json()["pendientes"], 1)
        self.assertEqual(r.json()["estado"], "pendiente_correccion")

    def test_el_consolidado_docente_ve_a_los_estudiantes(self):
        r = self.iniciar()
        self.api.post("/api/intentos/answer/", {"intento_id": r.json()["id"], "pregunta_ref": "pr-001", "respuesta": "3"}, format="json")
        self.api.post("/api/intentos/finish/", {"intento_id": r.json()["id"]}, format="json")
        self.abrir("co-sec-mat-doc-funcion")
        r = self.api.get(f"/api/cursos/{MAT}/consolidado/")
        self.assertEqual(r.json()["resumen"]["estudiantes"], 2)
        sofia = next(e for e in r.json()["estudiantes"] if e["persona_id"] == "sofia-torres")
        self.assertEqual(sofia["notas"][0]["puntaje"], 50.0)   # pr-001 bien, pr-002 sin responder cuenta como error
        self.assertEqual(r.json()["titulo"], "Matemáticas · Grado 8")


class SinComprobarTests(ConHost):
    capacidades = ["curso", "evaluacion"]

    def test_sin_capacidad_de_correccion_no_hay_nota(self):
        r = self.api.post("/api/intentos/start/", {"evaluacion_ref": "co-sec-mat-eval-funcion", "persona_id": "lucas", "curso_ref": MAT}, format="json")
        self.assertFalse(r.json()["puede_corregir"])
        pk = r.json()["id"]
        r = self.api.post("/api/intentos/answer/", {"intento_id": pk, "pregunta_ref": "pr-001", "respuesta": "3"}, format="json")
        self.assertIsNone(r.json()["acierta"])
        self.assertIn("comprobar", r.json()["motivo"])
        r = self.api.post("/api/intentos/finish/", {"intento_id": pk}, format="json")
        self.assertEqual(r.json()["estado"], "pendiente_correccion")
        self.assertIsNone(r.json()["puntaje"])


class SinEvaluacionTests(ConHost):
    capacidades = ["curso"]

    def test_sin_capacidad_evaluacion_no_se_entregan_preguntas(self):
        r = self.api.post("/api/intentos/start/", {"evaluacion_ref": "co-sec-mat-eval-funcion", "persona_id": "lucas"}, format="json")
        self.assertEqual(r.status_code, 501)
        self.assertEqual(Intento.objects.count(), 0)


class FronteraTests(TestCase):
    def test_la_administracion_de_cursos_se_rechaza_con_explicacion(self):
        api = APIClient()
        for ruta in ("/api/courses/", "/api/lessons/1/", "/api/course-packages/"):
            r = api.post(ruta, {"name": "x"}, format="json")
            self.assertEqual(r.status_code, 409, ruta)
            self.assertEqual(r.json()["error"], "administracion_no_permitida")
            self.assertEqual(r.json()["dueno"], "AVACOM Biblioteca")
        self.assertTrue(Auditoria.objects.filter(accion="administracion.rechazada").exists())

    def test_el_esquema_no_tiene_tablas_de_curso_ni_columnas_de_clave(self):
        from django.apps import apps

        tablas = {m._meta.db_table for m in apps.get_app_config("expediente").get_models()}
        for prohibida in ("m05_curso", "m05_seccion", "m05_leccion", "m05_leccion_item", "m10_quiz_pregunta", "m10_quiz_opcion"):
            self.assertNotIn(prohibida, tablas)
        for modelo in apps.get_app_config("expediente").get_models():
            for campo in modelo._meta.get_fields():
                self.assertNotIn("clave", campo.name, f"{modelo.__name__}.{campo.name}")
                self.assertNotIn("correcta", campo.name, f"{modelo.__name__}.{campo.name}")

    def test_la_auditoria_es_de_solo_escritura(self):
        # MOD-019: m19_auditoria es una vista de lectura sobre m19_bitacora; se escribe por audit.servicios.anexar.
        from audit import servicios as auditoria
        auditoria.anexar("a", "prueba.expediente")
        fila = Auditoria.objects.get(accion="prueba.expediente")
        self.assertEqual(fila.actor_id, "a")
        fila.accion = "y"
        with self.assertRaises(ValueError):
            fila.save()
        with self.assertRaises(ValueError):
            fila.delete()
