"""
MOD-010 contra la API de Contenido v2 de verdad (HTTP, token, enlace `link.json`), con el host de pruebas de la biblioteca: lo que el nodo pide de un examen
(`/exams/{oid}/pool`, `/exams/{oid}/questions?ids&seed`), cómo califica (UNA llamada `/v2/evaluate/batch`, con la versión del intento) y qué pasa cuando la
biblioteca no está o el curso cambió de versión (INV-024). El nodo no guarda curso, preguntas ni claves (artículo 14).
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile

from django.test import override_settings

from tools.host_contenido_v2_pruebas import HostContenidoV2Pruebas

from .. import models as m
from ..aplicacion import barrido
from ..infraestructura.contenedor import servicios
from .base import CURSO, EXAMEN, BaseEvaluacion, manifiesto_de_banco_fijo, respuesta_correcta


def claves_de(valor) -> set[str]:
    """Todas las claves de un JSON, a cualquier profundidad."""
    if isinstance(valor, dict):
        return set(valor) | {k for v in valor.values() for k in claves_de(v)}
    if isinstance(valor, list):
        return {k for v in valor for k in claves_de(v)}
    return set()


class _ConBiblioteca(BaseEvaluacion):
    fuente_de_ejemplo = False           # la fuente «biblioteca» de verdad, por HTTP

    def setUp(self):
        super().setUp()
        self.carpeta = tempfile.mkdtemp(prefix="avacom-eval-v2-")
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        self.ruta_enlace = os.path.join(self.carpeta, "link.json")
        self.v1 = manifiesto_de_banco_fijo()
        self.host = HostContenidoV2Pruebas(self.ruta_enlace, {CURSO: self.v1}, archivados={(CURSO, self.v1["version"]): copy.deepcopy(self.v1)}).iniciar()
        self.addCleanup(self.host.detener)
        ajuste = override_settings(AVACOM_CONTENIDO_ENLACE_V2=self.ruta_enlace)
        ajuste.enable()
        self.addCleanup(ajuste.disable)

    def asignar(self, **extra) -> dict:
        return self.crear_asignacion("supervisado", fuente="biblioteca", tiempo={"modo": "sin_limite"}, **extra)

    def peticiones(self, fragmento: str) -> list[str]:
        return [p for p in self.host.peticiones if fragmento in p]


class ExamenPorHttpTests(_ConBiblioteca):
    def test_el_ciclo_completo_pide_el_pool_las_preguntas_y_califica_en_un_solo_lote(self):
        a = self.asignar()
        self.assertEqual(len(self.peticiones(f"/exams/{EXAMEN}/pool")), 1)               # al asignar: ajustes y metadatos, sin enunciados
        i = self.abrir(a["id"])["intento"]["id"]
        fila = self.fila(i)
        preguntas = self.preguntas(i)
        self.assertEqual(len(preguntas["preguntas"]), 12)
        i_questions = [c for c in self.host.consultas if "ids" in c]
        self.assertEqual(len(i_questions), 1)
        self.assertEqual((i_questions[0]["seed"], i_questions[0]["ids"].split(",")), (fila.semilla, list(fila.armado)))
        refs = list(fila.armado)
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(refs)])
        self.entregar(i)
        lote = self.peticiones("POST /v2/evaluate/batch")
        sueltas = [p for p in self.host.peticiones if p == "POST /v2/evaluate"]
        self.assertEqual((len(lote), sueltas), (1, []))                                    # UNA llamada por lote, nunca una por reactivo
        items = self.host.cuerpos[-1]["items"]
        self.assertEqual(sorted(x["questionId"] for x in items), sorted(refs))
        self.assertEqual({(x["courseId"], x["version"], x["objectId"]) for x in items}, {(CURSO, fila.curso_version, EXAMEN)})
        self.assertEqual(self.fila(i).estado, "en_revision_docente")                       # las dos abiertas esperan al profesor

    def test_el_nodo_nunca_recibe_ni_entrega_una_clave(self):
        a = self.asignar()
        i = self.abrir(a["id"])["intento"]["id"]
        claves = claves_de(self.preguntas(i))
        for prohibida in ("isCorrect", "answer", "acceptedAnswers", "correctOrder", "pairs", "explanation"):
            self.assertNotIn(prohibida, claves)
        self.assertEqual(self.fila(i).armado_meta["tipos"].keys(), set(self.fila(i).armado))      # el nodo guarda referencias y tipos, no el examen

    def test_la_version_del_curso_se_congela_en_la_asignacion_y_en_el_intento(self):
        a = self.asignar()
        i = self.abrir(a["id"])["intento"]["id"]
        self.assertEqual((a["curso_version"], self.fila(i).curso_version), (self.v1["version"], self.v1["version"]))

    def test_el_examen_de_cada_alumno_se_pide_con_su_propia_semilla(self):
        a = self.asignar()
        ana, hw_ana = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        i_juan = self.abrir(a["id"])["intento"]["id"]
        i_ana = self.abrir(a["id"], hw=hw_ana, alumno_id=ana)["intento"]["id"]
        self.preguntas(i_juan)
        self.preguntas(i_ana, hw=hw_ana, alumno_id=ana)
        semillas = [c["seed"] for c in self.host.consultas if "ids" in c]
        self.assertEqual(semillas, [self.fila(i_juan).semilla, self.fila(i_ana).semilla])
        self.assertNotEqual(*semillas)


class CursoQueCambiaTests(_ConBiblioteca):
    """INV-024: un intento se califica con las claves de la versión con la que se hizo, aunque el curso se actualice a mitad del examen."""

    def actualizar_curso(self) -> dict:
        """La versión nueva invierte la clave de todas las verdaderas/falsas: lo correcto en la 1.0.0 es incorrecto en la nueva."""
        v2 = copy.deepcopy(self.v1)
        v2["version"] = "9.9.9"
        for leccion in v2["lessons"]:
            for objeto in leccion["objects"]:
                for pregunta in objeto.get("questions", []):
                    if pregunta["type"] == "true_false":
                        pregunta["answer"] = not pregunta["answer"]
        self.host.manifiestos[CURSO] = v2
        return v2

    def test_el_intento_en_marcha_se_califica_con_la_version_con_la_que_se_hizo(self):
        a = self.asignar()
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        cerradas = [r for r in tipos if tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(cerradas)])
        self.actualizar_curso()                                                             # el curso cambia con el examen a medias
        self.entregar(i, confirmar=True)
        items = self.host.cuerpos[-1]["items"]
        self.assertEqual({x["version"] for x in items}, {self.v1["version"]})
        fila = self.fila(i)
        self.assertEqual(fila.estado, "calificado")
        self.assertTrue(all(r["veredicto"]["correcta"] for r in fila.respuestas))           # con la 9.9.9 las verdaderas/falsas saldrían mal
        self.assertEqual(fila.curso_version, self.v1["version"])

    def test_abrir_con_la_version_ya_cambiada_se_rechaza_y_no_se_arma_nada(self):
        a = self.asignar()
        self.actualizar_curso()
        r = self.api.post(f"/api/evaluacion/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "version_no_disponible"))
        self.assertEqual(m.Intento.objects.filter(asignacion_id=a["id"]).count(), 0)


class BibliotecaQueNoEstaTests(_ConBiblioteca):
    def test_con_el_indice_reconstruyendose_no_se_asigna_y_la_respuesta_lo_explica(self):
        self.host.reconstruyendo = True
        cuerpo = {"fuente": "biblioteca", "curso_ref": CURSO, "objeto_ref": EXAMEN, "alcance": "grupo", "grupo_id": self.grupo["id"],
                  "nivel_examen": "supervisado", "iniciar": True, "actor": self.docente_id}
        r = self.api.post("/api/evaluacion/asignaciones/", cuerpo, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (503, "fuente_no_disponible"))
        self.host.reconstruyendo = False
        self.assertEqual(self.api.post("/api/evaluacion/asignaciones/", cuerpo, format="json").status_code, 201)

    def test_el_examen_se_entrega_aunque_la_biblioteca_se_apague_y_se_califica_cuando_vuelve(self):
        a = self.asignar(resultados="al_entregar")
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        cerradas = [r for r in tipos if tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(cerradas)])
        self.host.detener()                                                                  # la biblioteca se cierra
        self.entregar(i, confirmar=True)
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.calificacion_pendiente, len(fila.respuestas)), ("entregado", True, len(cerradas)))
        self.assertEqual(barrido.BarrerNodo(servicios()).ejecutar()["recalificados"], 0)    # sigue apagada: el barrido no falla
        self.host.iniciar()                                                                  # vuelve (otro puerto, mismo token)
        self.assertEqual(barrido.BarrerNodo(servicios()).ejecutar()["recalificados"], 1)
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.calificacion_pendiente), ("calificado", False))
        self.assertGreater(fila.porcentaje, 0)

    def test_un_token_rechazado_una_vez_se_reintenta_y_el_examen_sigue(self):
        a = self.asignar()
        self.host.rechazar_proximas = 1                                                      # el token rotó entre dos llamadas
        i = self.abrir(a["id"], esperado=(200, 201))["intento"]["id"]
        self.assertEqual(len(self.preguntas(i)["preguntas"]), 12)
