"""
Base común de las pruebas de MOD-010: el nodo instalado con su grupo 8A (un docente y un alumno, Juan), el examen de ejemplo «Estados de la materia»
(`l3-exam`: 12 preguntas en dos temas, `random_balanced` de 4 con tolerancias del 15 %) como contenido, un RELOJ del nodo que la prueba mueve a voluntad
y tabletas con la capacidad de control que cada caso necesita. Sin biblioteca real.

La fuente «ejemplo» sirve el examen pero NO califica (la clave sólo vive en la biblioteca). Para probar la calificación se sustituye por `FuenteQueCalifica`:
el mismo manifiesto con el calificador de referencia de la biblioteca (`tools.host_contenido_v2_pruebas.calificar`).
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
from tools.host_contenido_v2_pruebas import calificar

from .. import models as m
from ..infraestructura.contenedor import RelojNodo

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
EXAMEN = "l3-exam"
BASE = "/api/evaluacion"
T0 = 1_790_000_000_000          # 2026-09-21: el origen del reloj de las pruebas
SEG, MIN = 1_000, 60_000


class FuenteQueCalifica(FuenteEjemplo):
    """El manifiesto de ejemplo con el calificador de referencia: califica de verdad (correcta, incorrecta, abierta = revisión manual)."""

    lotes: list[list[str]] = []
    sueltas: list[str] = []
    versiones: list[str] = []
    caida = False

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
        from classroom_engine.dominio.errores import FuenteNoDisponible
        if FuenteQueCalifica.caida:
            raise FuenteNoDisponible("La biblioteca está cerrada (prueba).")
        FuenteQueCalifica.lotes.append([i["questionId"] for i in items])
        FuenteQueCalifica.versiones.append(version)
        return [calificar(self._pregunta(i["questionId"]), i["response"]) for i in items]


def manifiesto() -> dict:
    with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
        return json.load(f)


def manifiesto_de_banco_fijo() -> dict:
    """El mismo curso de ejemplo con el examen en `fixed` (las doce preguntas, de los seis tipos, a cada alumno) y sin límite de tiempo de la biblioteca."""
    datos = manifiesto()
    for leccion in datos["lessons"]:
        for objeto in leccion["objects"]:
            if objeto["type"] == "exam":
                objeto["settings"]["selection"] = {"strategy": "fixed"}
                objeto["settings"]["timeLimit"] = {"policy": "none"}
    return datos


def pregunta_cruda(pregunta_ref: str) -> dict:
    for leccion in manifiesto()["lessons"]:
        for objeto in leccion["objects"]:
            for pregunta in objeto.get("questions", []):
                if pregunta["id"] == pregunta_ref:
                    return pregunta
    raise KeyError(pregunta_ref)


def respuesta_correcta(pregunta_ref: str) -> dict:
    """La respuesta que la biblioteca daría por buena (la clave se lee del manifiesto: sólo la prueba la conoce)."""
    p = pregunta_cruda(pregunta_ref)
    tipo = p["type"]
    if tipo == "multiple_choice":
        return {"selectedOptionIds": [o["id"] for o in p["options"] if o.get("isCorrect")]}
    if tipo == "true_false":
        return {"value": p["answer"]}
    if tipo == "fill_blanks":
        return {"blanks": {b["id"]: b["acceptedAnswers"][0] for b in p["blanks"]}}
    if tipo == "matching":
        return {"pairs": [{"leftId": x["leftId"], "rightId": x["rightId"]} for x in p["pairs"]]}
    if tipo == "ordering":
        return {"order": list(p["correctOrder"])}
    return {"text": "Porque al enfriarse las partículas se mueven más despacio y el gas ocupa menos espacio."}


def respuesta_incorrecta(pregunta_ref: str) -> dict:
    p = pregunta_cruda(pregunta_ref)
    tipo = p["type"]
    if tipo == "multiple_choice":
        return {"selectedOptionIds": [o["id"] for o in p["options"] if not o.get("isCorrect")][:1]}
    if tipo == "true_false":
        return {"value": not p["answer"]}
    if tipo == "fill_blanks":
        return {"blanks": {b["id"]: "xyz" for b in p["blanks"]}}
    if tipo == "matching":
        derecha = [x["rightId"] for x in p["pairs"]]
        return {"pairs": [{"leftId": x["leftId"], "rightId": derecha[(i + 1) % len(derecha)]} for i, x in enumerate(p["pairs"])]}
    if tipo == "ordering":
        return {"order": list(reversed(p["correctOrder"]))}
    return {"text": "No sé."}


class BaseEvaluacion(BaseAcceso):
    """El nodo con lo necesario para probar la evaluación por HTTP."""

    fuente_de_ejemplo = True        # False: la fuente «biblioteca» de verdad, contra el host de pruebas de la API v2 (`test_contrato_v2`)

    def setUp(self):
        super().setUp()
        self.t = T0
        parche = mock.patch.object(RelojNodo, "ahora_ms", side_effect=lambda: self.t)
        parche.start()
        self.addCleanup(parche.stop)
        FuenteQueCalifica.lotes, FuenteQueCalifica.sueltas, FuenteQueCalifica.versiones, FuenteQueCalifica.caida = [], [], [], False
        if self.fuente_de_ejemplo:
            parche_fuente = mock.patch("classroom_engine.infraestructura.contenedor.fuente",
                                       side_effect=lambda nombre=None, curso_ref="": FuenteQueCalifica(ruta_ejemplo()))
            parche_fuente.start()
            self.addCleanup(parche_fuente.stop)
        # La tableta de Juan: declara que sólo la app corre (supervisado); la del aula (BaseAcceso) no declara nada.
        self.hw_juan = "hw-juan"
        self.tableta_juan = self.registrar(self.hw_juan, "Tableta de Juan", capacidad="supervisado")

    # ------------------------------------------------------------------------------------------ reloj
    def avanzar(self, ms: int = 0, seg: int = 0, minutos: int = 0) -> int:
        self.t += ms + seg * SEG + minutos * MIN
        return self.t

    # ------------------------------------------------------------------------- aparatos y personas
    def registrar(self, hw: str, nombre: str | None = None, capacidad: str | None = None) -> dict:
        cuerpo = {"identificador_hw": hw, "nombre": nombre or hw}
        if capacidad is not None:
            cuerpo["capacidad_control"] = capacidad
        r = self.api.post("/api/dispositivos/", cuerpo, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def nuevo_alumno(self, alias: str, codigo: str, grupo_id: str | None = None) -> str:
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba", "fecha_nacimiento": "2012-05-06"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": codigo, "es_login": True}],
            "secreto": "573920", "secreto_definitivo": True, "grupo_id": grupo_id or self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def alumno_con_tableta(self, alias: str, codigo: str, capacidad: str | None = "controlado", grupo_id: str | None = None) -> tuple[str, str]:
        """Un alumno nuevo con su tableta: `(alumno_id, huella)`."""
        alumno_id = self.nuevo_alumno(alias, codigo, grupo_id=grupo_id)
        hw = f"hw-{codigo}"
        self.registrar(hw, f"Tableta {alias}", capacidad=capacidad)
        return alumno_id, hw

    # ------------------------------------------------------------------------------- asignaciones
    def crear_asignacion(self, nivel: str = "supervisado", esperado: int = 201, **extra) -> dict:
        """El profesor (sin sesión: Q-34) asigna el examen de ejemplo a su grupo 8A y lo inicia."""
        cuerpo = {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": EXAMEN, "alcance": "grupo", "grupo_id": self.grupo["id"],
                  "nivel_examen": nivel, "iniciar": True, "actor": self.docente_id, "actor_rotulo": "Prof. Gómez", **extra}
        r = self.api.post(f"{BASE}/asignaciones/", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def accion(self, ruta: str, cuerpo: dict | None = None, esperado: int = 200, metodo: str = "post", cliente: APIClient | None = None) -> dict:
        r = getattr(cliente or self.api, metodo)(f"{BASE}{ruta}", {"actor": self.docente_id, **(cuerpo or {})}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def ver(self, ruta: str, esperado: int = 200, cliente: APIClient | None = None, **params) -> dict:
        r = (cliente or self.api).get(f"{BASE}{ruta}", {"actor": self.docente_id, **params})
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    # ------------------------------------------------------------------------------------ el alumno
    def alumno(self, hw: str | None = None, alumno_id: str | None = None) -> dict:
        return {"dispositivo": hw or self.hw_juan, "alumno_id": alumno_id or self.estudiante_id}

    def abrir(self, asignacion_id: str, hw: str | None = None, alumno_id: str | None = None, esperado: int | tuple = (200, 201), **extra):
        r = self.api.post(f"{BASE}/asignaciones/{asignacion_id}/intentos/", {**self.alumno(hw, alumno_id), **extra}, format="json")
        esperados = esperado if isinstance(esperado, tuple) else (esperado,)
        self.assertIn(r.status_code, esperados, r.content)
        return r.json()

    def estado(self, intento_id: str, hw: str | None = None, alumno_id: str | None = None, esperado: int = 200) -> dict:
        r = self.api.get(f"{BASE}/intentos/{intento_id}/estado/", self.alumno(hw, alumno_id))
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def latido(self, intento_id: str, hw: str | None = None, alumno_id: str | None = None, esperado: int = 200, **extra) -> dict:
        r = self.api.post(f"{BASE}/intentos/{intento_id}/latido/", {**self.alumno(hw, alumno_id), **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def latir_hasta(self, intento_id: str, segundos: int, cada: int = 20, hw: str | None = None, alumno_id: str | None = None) -> None:
        """La tableta da señal cada `cada` segundos durante `segundos` (el reloj del nodo avanza). Con más de 30 s de silencio el nodo suspende."""
        for _ in range(segundos // cada):
            self.avanzar(seg=cada)
            self.latido(intento_id, hw=hw, alumno_id=alumno_id)

    def preguntas(self, intento_id: str, hw: str | None = None, alumno_id: str | None = None, esperado: int = 200) -> dict:
        r = self.api.get(f"{BASE}/intentos/{intento_id}/preguntas/", self.alumno(hw, alumno_id))
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def responder(self, intento_id: str, respuestas: list[dict], hw: str | None = None, alumno_id: str | None = None, esperado: int = 200, **extra):
        r = self.api.post(f"{BASE}/intentos/{intento_id}/respuestas/", {**self.alumno(hw, alumno_id), "respuestas": respuestas, **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def entregar(self, intento_id: str, hw: str | None = None, alumno_id: str | None = None, esperado: int = 200, **extra):
        r = self.api.post(f"{BASE}/intentos/{intento_id}/entregar/", {**self.alumno(hw, alumno_id), **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    @staticmethod
    def r(ref: str, secuencia: int, respuesta: dict, **extra) -> dict:
        return {"pregunta_ref": ref, "secuencia": secuencia, "respuesta": respuesta, **extra}

    def refs_del_examen(self, intento_id: str, hw: str | None = None, alumno_id: str | None = None) -> list[str]:
        return [p["pregunta_ref"] for p in self.preguntas(intento_id, hw, alumno_id)["preguntas"]]

    def refs_cerradas(self, intento_id: str) -> list[str]:
        """Las preguntas de su examen que la biblioteca califica sola (el examen cambia de un alumno a otro y de una corrida a otra: las de redacción
        piden revisión del profesor y cambiarían el estado final)."""
        tipos = self.fila(intento_id).armado_meta["tipos"]
        return [ref for ref in self.refs_del_examen(intento_id) if tipos[ref] != "open"]

    def responder_todo(self, intento_id: str, bien: bool = True, hw: str | None = None, alumno_id: str | None = None, desde: int = 1) -> list[str]:
        """Responde TODAS las preguntas de su examen (bien o mal) y devuelve las referencias."""
        refs = self.refs_del_examen(intento_id, hw, alumno_id)
        f = respuesta_correcta if bien else respuesta_incorrecta
        self.responder(intento_id, [self.r(ref, desde + n, f(ref)) for n, ref in enumerate(refs)], hw, alumno_id)
        return refs

    def intento_abierto(self, asignacion_id: str | None = None, nivel: str = "supervisado", **extra) -> tuple[dict, dict]:
        """Atajo: la asignación (si no se da una) y el intento abierto de Juan."""
        asignacion = {"id": asignacion_id} if asignacion_id else self.crear_asignacion(nivel, **extra)
        apertura = self.abrir(asignacion["id"])
        return asignacion, apertura

    # ---------------------------------------------------------------------------------------- lectura
    def eventos(self, *tipos: str) -> list[str]:
        filas = m.EventoSalida.objects.order_by("id")
        if tipos:
            filas = filas.filter(tipo_evento__in=tipos)
        return list(filas.values_list("tipo_evento", flat=True))

    def incidentes(self, intento_id: str) -> list[str]:
        return list(m.Incidente.objects.filter(intento_id=intento_id).order_by("ocurrido_en", "id").values_list("tipo", flat=True))

    def fila(self, intento_id: str) -> m.Intento:
        return m.Intento.objects.get(pk=intento_id)

    @contextmanager
    def examen_de_banco_fijo(self):
        """El mismo curso de ejemplo pero con el examen en `fixed` (las doce preguntas, de los seis tipos, a cada alumno) y sin límite de tiempo de la
        biblioteca: sirve para probar la autocalificación de TODOS los tipos en un solo examen."""
        datos = manifiesto_de_banco_fijo()
        with tempfile.TemporaryDirectory(prefix="avacom-evaluacion-") as carpeta:
            ruta = os.path.join(carpeta, "example-fijo.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f)
            with override_settings(AVACOM_AULA_CURSO_EJEMPLO=ruta):
                yield ruta

    @contextmanager
    def biblioteca_caida(self):
        FuenteQueCalifica.caida = True
        try:
            yield
        finally:
            FuenteQueCalifica.caida = False
