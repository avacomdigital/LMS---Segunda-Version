"""
Base común de las pruebas de API de MOD-008: el nodo instalado con su grupo 8A (un docente y un alumno, Juan), una tableta compartida y una
tableta ASIGNADA a Juan (`hw-juan`), y la lección de ejemplo «Ciencias naturales» como contenido (sin biblioteca real).

La fuente «ejemplo» sirve contenido y medios reales pero NO califica (la clave sólo vive en la biblioteca). Para probar la calificación
inmediata se sustituye la fuente por `FuenteQueCalifica`: el mismo manifiesto con el calificador de referencia de la biblioteca
(`tools.host_contenido_v2_pruebas.calificar`, el que las pruebas del contrato comparan con `validate_course.py`).
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from unittest import mock

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from classroom_engine.infraestructura.contenedor import ruta_ejemplo
from classroom_engine.infraestructura.fuente_ejemplo import FuenteEjemplo
from tools.host_contenido_v2_pruebas import HostContenidoV2Pruebas, calificar

from .. import models as m
from ..infraestructura.contenedor import RelojNodo

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
LECCION_1 = "l1-three-states"          # 3 láminas + 2 páginas + 1 laboratorio + 1 práctica de 6 preguntas = 7 bloques
LECCION_2 = "l2-changes-of-state"      # 2 láminas + 1 laboratorio + 1 práctica de 3 preguntas = 4 bloques
LECCION_EXAMEN = "l3-assessment"       # sólo un examen: nada que estudiar
BASE = "/api/modo-estudio"

BLOQUES_L1 = ["l1-lecture:l1-lecture-s1", "l1-lecture:l1-lecture-s2", "l1-lecture:l1-lecture-s3",
              "l1-explanation:l1-explanation-p1", "l1-explanation:l1-explanation-p2", "l1-lab-phet", "l1-activity"]
BLOQUES_L1_SIN_PRACTICA = BLOQUES_L1[:-1]

# Las respuestas correctas de la práctica de la lección 1 (q6 es abierta: se corrige a mano).
CORRECTAS = {
    "l1-act-q1": {"selectedOptionIds": ["a"]},
    "l1-act-q2": {"value": False},
    "l1-act-q3": {"blanks": {"b1": "propio", "b2": "forma"}},
    "l1-act-q4": {"pairs": [{"leftId": "solid", "rightId": "fixed"}, {"leftId": "liquid", "rightId": "slide"},
                            {"leftId": "gas", "rightId": "spread"}]},
    "l1-act-q5": {"order": ["o-solid", "o-liquid", "o-gas"]},
}
INCORRECTA_Q2 = {"value": True}


class FuenteQueCalifica(FuenteEjemplo):
    """El manifiesto de ejemplo con el calificador de referencia: califica de verdad (correcta, incorrecta, abierta = revisión manual)."""

    lotes: list[list[str]] = []      # las preguntas de cada llamada `evaluar_lote`: sirve para comprobar «una llamada por envío»
    sueltas: list[str] = []

    def _pregunta(self, pregunta_ref: str) -> dict:
        for leccion in self._leer()["lessons"]:
            for objeto in leccion["objects"]:
                for pregunta in objeto.get("questions", []):
                    if pregunta["id"] == pregunta_ref:
                        return pregunta
        raise KeyError(pregunta_ref)

    def evaluar(self, curso_ref, version, objeto_ref, pregunta_ref, respuesta):
        FuenteQueCalifica.sueltas.append(pregunta_ref)
        return calificar(self._pregunta(pregunta_ref), respuesta)

    def evaluar_lote(self, curso_ref, version, items):
        FuenteQueCalifica.lotes.append([i["questionId"] for i in items])
        return [calificar(self._pregunta(i["questionId"]), i["response"]) for i in items]


class BaseEstudio(BaseAcceso):
    """El nodo con lo necesario para probar el modo de estudio por HTTP."""

    def setUp(self):
        super().setUp()
        self.hw_compartida = self.TABLETA                      # la tableta del aula, registrada por BaseAcceso (compartida)
        self.compartida = self.tableta
        self.hw_juan = "hw-juan"
        self.propia = self.registrar(self.hw_juan, "Tableta de Juan")
        self.asignar(self.propia["id"], self.estudiante_id)     # asignada a Juan
        FuenteQueCalifica.lotes, FuenteQueCalifica.sueltas = [], []

    # ------------------------------------------------------------------------ aparatos y personas
    def registrar(self, hw: str, nombre: str | None = None) -> dict:
        r = self.api.post("/api/dispositivos/", {"identificador_hw": hw, "nombre": nombre or hw}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def asignar(self, dispositivo_id: str, alumno_id: str, esperado: int = 200) -> dict:
        r = self.admin.post(f"/api/dispositivos/{dispositivo_id}/asignar/", {"alumno_id": alumno_id}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def nuevo_alumno(self, alias: str, codigo: str, pin: str = "573920", grupo_id: str | None = None) -> str:
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba", "fecha_nacimiento": "2012-05-06"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": codigo, "es_login": True}],
            "secreto": pin, "secreto_definitivo": True, "grupo_id": grupo_id or self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def alumno_con_tableta(self, alias: str, codigo: str, grupo_id: str | None = None) -> tuple[str, str]:
        """Un alumno nuevo con su tableta asignada: `(alumno_id, huella)`."""
        alumno_id = self.nuevo_alumno(alias, codigo, grupo_id=grupo_id)
        hw = f"hw-{codigo}"
        self.asignar(self.registrar(hw)["id"], alumno_id)
        return alumno_id, hw

    # -------------------------------------------------------------------------------- asignaciones
    def crear_asignacion(self, leccion: str = LECCION_1, esperado: int = 201, **extra) -> dict:
        """El profesor (sin sesión: Q-34) asigna una lección a su grupo 8A."""
        cuerpo = {"alcance": "grupo", "grupo_id": self.grupo["id"], "curso_ref": CURSO, "fuente": "ejemplo", "leccion_ref": leccion,
                  "actor": self.docente_id, "actor_rotulo": "Prof. Gómez", **extra}
        r = self.api.post(f"{BASE}/docente/asignaciones/", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def ver(self, ruta: str, hw: str | None = None, cliente: APIClient | None = None, **params):
        """GET de una ruta del alumno en su tableta (`hw`, por defecto la de Juan)."""
        consulta = {"dispositivo": self.hw_juan if hw is None else hw, **params}
        consulta = {k: v for k, v in consulta.items() if v}
        return (cliente or self.api).get(f"{BASE}{ruta}", consulta)

    def enviar(self, metodo: str, ruta: str, cuerpo: dict | None = None, hw: str | None = None, cliente: APIClient | None = None):
        datos = {"dispositivo": self.hw_juan if hw is None else hw, **(cuerpo or {})}
        datos = {k: v for k, v in datos.items() if v not in ("", None)}
        return getattr(cliente or self.api, metodo)(f"{BASE}{ruta}", datos, format="json")

    def borrar(self, ruta: str, hw: str | None = None, cliente: APIClient | None = None):
        """DELETE de una ruta del alumno: el aparato va en la URL, como dice el contrato (`?dispositivo=`)."""
        return (cliente or self.api).delete(f"{BASE}{ruta}?dispositivo={self.hw_juan if hw is None else hw}")

    def json_ok(self, respuesta, esperado: int = 200) -> dict:
        self.assertEqual(respuesta.status_code, esperado, respuesta.content)
        return respuesta.json()

    def bloques(self, asignacion_id: str, refs: list[str], hw: str | None = None, **extra):
        return self.enviar("patch", f"/lecciones/{asignacion_id}/progreso/", {"bloques_vistos": refs, **extra}, hw=hw)

    # ---------------------------------------------------------------------------------------- eventos
    def eventos(self, *tipos: str) -> list[str]:
        filas = m.EventoSalida.objects.order_by("id")
        if tipos:
            filas = filas.filter(tipo_evento__in=tipos)
        return list(filas.values_list("tipo_evento", flat=True))

    @contextmanager
    def reloj(self, momento: int):
        """El reloj del nodo, fijo: sirve para probar plazos y vigencias."""
        with mock.patch.object(RelojNodo, "ahora_ms", return_value=momento):
            yield

    @contextmanager
    def biblioteca_que_califica(self):
        """La fuente de ejemplo pero calificando de verdad (sustituye a la biblioteca)."""
        with mock.patch("classroom_engine.infraestructura.contenedor.fuente",
                        side_effect=lambda nombre=None, curso_ref="": FuenteQueCalifica(ruta_ejemplo())):
            yield FuenteQueCalifica

    @contextmanager
    def host_de_contenido(self, medios: dict[str, tuple[str, bytes]] | None = None):
        """La API de Contenido v2 de pruebas (`tools/host_contenido_v2_pruebas.py`) en loopback, con el manifiesto de ejemplo: la
        fuente «biblioteca» de verdad (HTTP, flujos, sesiones de medios y `POST /v2/evaluate`). `medios`: `{mediaId: (tipo, bytes)}`."""
        with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
            manifiesto = json.load(f)
        with tempfile.TemporaryDirectory(prefix="avacom-estudio-v2-") as carpeta:
            ruta = os.path.join(carpeta, "link.json")
            host = HostContenidoV2Pruebas(ruta, {CURSO: manifiesto}, medios=medios or {}).iniciar()
            try:
                with override_settings(AVACOM_CONTENIDO_ENLACE_V2=ruta):
                    yield host
            finally:
                host.detener()
