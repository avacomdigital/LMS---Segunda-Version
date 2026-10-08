"""
Contrato 2 de AVACOM Contenido entregado el 2026-10-07 (`course.schema (3).json`, `openapi.v2 (3).json`): lo nuevo que el aula consume.

  · Medio de clase `html`: la lección maquetada por el curso (carpeta con páginas, estilos y fuentes; `entry` es la primera página). Dentro de
    una página, otro medio se nombra `../{mediaId}`, sus subtítulos `../{mediaId}/@captions` y el póster de un video `../{mediaId}/@poster`.
  · `html {mediaId, entry}` en una cátedra o explicación: la sección n es `entry#s{n}`.
  · `interactions` en un video (pausas para pensar, formativas) y `posterPath` (`extras[mediaId].poster` en la sesión de medios).
  · Las sesiones de medios se reutilizan por (curso, medio) mientras viven: 35 tabletas pidiendo trozos no abren una por trozo.

Nada de esto existe aún en los 7 cursos instalados en la Contenido real (2.1.7): se prueba con la API de Contenido de pruebas.
"""
from __future__ import annotations

import copy
import json
import re

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from biblioteca import contenido_v2
from classroom_engine.dominio import respuestas
from classroom_engine.dominio.errores import DatosInvalidos
from cola_medios.tests.apoyo import sin_cola
from modo_estudio.tests.base import BaseEstudio

from .test_curso import manifiesto

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
VIDEO = bytes(range(256)) * 64
PAGINA = (b"<!doctype html><html><head><link rel='stylesheet' href='estilos.css'></head><body>"
          b"<section id='s1'><h1>Qu\xc3\xa9 es la materia</h1></section>"
          b"<section id='s2'><video src='../vid-changes' poster='../vid-changes/@poster'><track src='../vid-changes/@captions'></video></section>"
          b"</body></html>")
MEDIOS = {
    "html-l1/index.html": ("text/html; charset=utf-8", PAGINA),
    "html-l1/estilos.css": ("text/css", b"section{display:none} section:target{display:block}"),
    "vid-changes": ("video/mp4", VIDEO),
    "vid-changes/@captions": ("text/vtt; charset=utf-8", b"WEBVTT\n\n1\n00:00:00.000 --> 00:00:30.000\nEl hielo es solido."),
    "vid-changes/@poster": ("image/png", PNG),
    "img-particles": ("image/png", PNG),
}


def manifiesto_con_html() -> dict:
    """El curso de ejemplo con lo que trae el contrato 2: la cátedra 1 maquetada en html y el video con póster y pausas."""
    m = copy.deepcopy(manifiesto())
    m["media"].append({"id": "html-l1", "kind": "html", "path": "html/l1", "entry": "index.html", "mimeType": "text/html",
                       "title": "Lección 1 maquetada", "license": {"type": "avacom"}})
    for medio in m["media"]:
        if medio["id"] == "vid-changes":
            medio["posterPath"] = "media/vid-changes.jpg"
            medio["interactions"] = [{
                "id": "p1", "atSec": 12, "prompt": "¿Qué pasa con las partículas al calentar?",
                "options": [{"id": "a", "text": "Se mueven más", "isCorrect": True, "feedback": "Ganan energía y vibran más."},
                            {"id": "b", "text": "Se detienen", "isCorrect": False, "feedback": "Al revés: el calor las agita."}],
                "teacherTip": "Pregunta a la clase antes de mostrar la respuesta.",
            }]
    for leccion in m["lessons"]:
        for objeto in leccion["objects"]:
            if objeto["id"] == "l1-lecture":
                objeto["html"] = {"mediaId": "html-l1", "entry": "index.html"}
    return m


def urls_de_medios(vista: dict) -> list[str]:
    return re.findall(r'"(/api/[^"]*/medios/[^"]*)"', json.dumps(vista))


class ContratoHtmlTests(BaseEstudio):
    def setUp(self):
        super().setUp()
        contenido_v2.olvidar_sesiones_medios()
        self.host = self.enterContext(self.host_de_contenido_con(manifiesto_con_html(), MEDIOS))
        self.visor = APIClient()

    def host_de_contenido_con(self, m: dict, medios: dict):
        """Como `host_de_contenido`, pero con un manifiesto propio."""
        import os
        import tempfile
        from contextlib import contextmanager

        from tools.host_contenido_v2_pruebas import HostContenidoV2Pruebas

        @contextmanager
        def ctx():
            with tempfile.TemporaryDirectory(prefix="avacom-html-v2-") as carpeta:
                ruta = os.path.join(carpeta, "link.json")
                host = HostContenidoV2Pruebas(ruta, {CURSO: m}, medios=medios).iniciar()
                try:
                    with override_settings(AVACOM_CONTENIDO_ENLACE_V2=ruta):
                        yield host
                finally:
                    host.detener()
        return ctx()

    def leccion(self, cliente=None) -> dict:
        r = (cliente or self.visor).get(f"/api/aula/cursos/{CURSO}/lecciones/l1-three-states/?fuente=biblioteca")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def objeto(self, ref: str, cliente=None) -> dict:
        return next(o for o in self.leccion(cliente)["leccion"]["objetos"] if o["objeto_ref"] == ref)

    # ------------------------------------------------------------------- lo normalizado
    def test_el_medio_html_llega_con_su_pagina_de_entrada_y_su_carpeta(self):
        curso = self.visor.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").json()
        html = next(m for m in curso["medios"] if m["media_ref"] == "html-l1")
        self.assertEqual((html["clase"], html["componente"], html["entrada"]), ("html", "html", "index.html"))
        self.assertTrue(html["url"].endswith("/medios/html-l1/index.html?fuente=biblioteca"), html["url"])
        self.assertTrue(html["base_url"].endswith("/medios/html-l1/?fuente=biblioteca"), html["base_url"])

    def test_la_catedra_maquetada_trae_su_url_y_cada_lamina_su_seccion(self):
        catedra = self.objeto("l1-lecture")
        self.assertEqual((catedra["html"]["media_ref"], catedra["html"]["entrada"], catedra["html"]["ausente"]), ("html-l1", "index.html", False))
        self.assertTrue(catedra["html"]["url"].endswith("/medios/html-l1/index.html?fuente=biblioteca"))
        for lamina in catedra["laminas"]:
            self.assertEqual(lamina["url_html"], f"{catedra['html']['url']}#s{lamina['indice']}")
            self.assertTrue(lamina["bloques"], "los bloques siguen siendo el respaldo")
        # Una explicación sin maquetar: nada cambia.
        lectura = self.objeto("l1-explanation")
        self.assertIsNone(lectura["html"])
        self.assertTrue(all(p["url_html"] is None for p in lectura["paginas"]))

    def test_el_video_trae_poster_y_pausas_y_el_consejo_solo_al_docente(self):
        def bloque_video(cliente=None):
            catedra = self.objeto("l1-lecture", cliente)
            return next(b for l in catedra["laminas"] for b in l["bloques"] if b["componente"] == "video")
        video = bloque_video()
        self.assertTrue(video["poster_url"].endswith("/medios/vid-changes/poster?fuente=biblioteca"), video["poster_url"])
        pausa = video["pausas"][0]
        self.assertEqual((pausa["pausa_ref"], pausa["en_seg"]), ("p1", 12))
        self.assertEqual([(o["opcion_ref"], o["es_respuesta"]) for o in pausa["opciones"]], [("a", True), ("b", False)])
        self.assertEqual(pausa["opciones"][1]["explicacion"], "Al revés: el calor las agita.")
        self.assertNotIn("consejo_docente", pausa)                                             # sin sesión = estudiante
        self.assertEqual(bloque_video(self.docente)["pausas"][0]["consejo_docente"], "Pregunta a la clase antes de mostrar la respuesta.")
        # Nada del contrato crudo se cuela: ni `isCorrect` ni `feedback`.
        self.assertNotIn("isCorrect", json.dumps(video))
        self.assertNotIn('"feedback"', json.dumps(video))

    # ------------------------------------------------------------------- lo servido
    def test_la_pagina_html_y_lo_que_nombra_con_rutas_relativas_se_sirven(self):
        catedra = self.objeto("l1-lecture")
        pagina = catedra["html"]["url"]
        r = self.visor.get(pagina)
        self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, "text/html"))
        self.assertIn(b"../vid-changes/@captions", b"".join(r.streaming_content))
        carpeta = pagina.split("?")[0].rsplit("/", 1)[0]          # lo que el navegador toma como base de la página
        for relativo, tipo in (("estilos.css", "text/css"), ("../vid-changes", "video/mp4"), ("../vid-changes/@captions", "text/vtt"),
                               ("../vid-changes/@poster", "image/png")):
            # `..` resuelto como lo hace el navegador: sube de `html-l1/` a `medios/`, sin barra final y sin `?fuente=`.
            ruta = carpeta + "/" + relativo
            while "/../" in ruta:
                ruta = re.sub(r"/[^/]+/\.\./", "/", ruta, count=1)
            with override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False):      # como en un nodo real: sin `?fuente`, biblioteca
                r = self.visor.get(ruta)
            self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, tipo), ruta)
        with override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False):
            r = self.visor.get(carpeta.rsplit("/", 1)[0] + "/vid-changes", HTTP_RANGE="bytes=0-9")   # un `<video>` pide trozos
        self.assertEqual((r.status_code, r["Content-Range"]), (206, f"bytes 0-9/{len(VIDEO)}"))

    def test_con_sesion_obligatoria_las_rutas_relativas_heredan_el_pase_del_camino(self):
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True, AVACOM_AULA_PERMITIR_EJEMPLO=False):
            catedra = self.objeto("l1-lecture", self.docente)
            pagina = catedra["html"]["url"]
            self.assertRegex(pagina, r"^/api/m/[\w.-]+/aula/cursos/")
            carpeta = pagina.split("?")[0].rsplit("/", 1)[0]
            medios = carpeta.rsplit("/", 1)[0]
            for ruta, tipo in ((f"{medios}/vid-changes", "video/mp4"), (f"{medios}/vid-changes/@captions", "text/vtt"),
                               (f"{medios}/vid-changes/@poster", "image/png"), (f"{carpeta}/estilos.css", "text/css")):
                r = self.visor.get(ruta)
                self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, tipo), ruta)
            self.assertEqual(self.visor.get(f"{medios}/vid-changes".replace("/api/m/", "/api/m/x", 1)).status_code, 401)

    # ------------------------------------------------------- sesiones de medios reutilizadas
    def test_los_trozos_de_un_mismo_medio_comparten_la_sesion_de_medios(self):
        catedra = self.objeto("l1-lecture")
        url = next(b["url"] for l in catedra["laminas"] for b in l["bloques"] if b["componente"] == "video")
        antes = self.host.peticiones.count("POST /v2/media-sessions")
        for rango in ("bytes=0-9", "bytes=10-19", "bytes=20-"):
            self.assertEqual(self.visor.get(url, HTTP_RANGE=rango).status_code, 206)
        self.assertEqual(self.host.peticiones.count("POST /v2/media-sessions") - antes, 1)
        self.assertEqual(self.host.cuerpos[-1]["ttlSec"], 15 * 60)
        # Los subtítulos y el póster van por la misma sesión del medio.
        self.assertEqual(self.visor.get(url.replace("/vid-changes/?", "/vid-changes/subtitulos?")).status_code, 200)
        self.assertEqual(self.host.peticiones.count("POST /v2/media-sessions") - antes, 1)
        # Otro medio, otra sesión.
        self.assertEqual(self.visor.get(url.replace("vid-changes", "img-particles")).status_code, 200)
        self.assertEqual(self.host.peticiones.count("POST /v2/media-sessions") - antes, 2)

    def test_si_contenido_olvida_la_sesion_se_abre_otra_una_sola_vez(self):
        sin_cola(self)                                              # prueba la capa de abajo: con la cola, el segundo GET sale de la caché del nodo
        catedra = self.objeto("l1-lecture")
        url = next(b["url"] for l in catedra["laminas"] for b in l["bloques"] if b["componente"] == "video")
        self.assertEqual(self.visor.get(url).status_code, 200)
        self.host.sesiones.clear()                                  # Contenido se reinició o revocó la sesión
        antes = self.host.peticiones.count("POST /v2/media-sessions")
        self.assertEqual(self.visor.get(url).status_code, 200)
        self.assertEqual(self.host.peticiones.count("POST /v2/media-sessions") - antes, 1)
        # Un medio que de verdad no existe sigue siendo 404, sin bucles.
        r = self.visor.get(url.replace("vid-changes", "no-existe"))
        self.assertEqual(r.status_code, 404)

    def test_con_la_reutilizacion_apagada_cada_trozo_abre_su_sesion_de_un_minuto(self):
        sin_cola(self)                                              # prueba la capa de abajo: con la cola, el segundo trozo sale de la caché del nodo
        catedra = self.objeto("l1-lecture")
        url = next(b["url"] for l in catedra["laminas"] for b in l["bloques"] if b["componente"] == "video")
        with override_settings(AVACOM_CONTENIDO_SESION_MEDIOS_SEG=0):
            antes = self.host.peticiones.count("POST /v2/media-sessions")
            for rango in ("bytes=0-9", "bytes=10-19"):
                self.assertEqual(self.visor.get(url, HTTP_RANGE=rango).status_code, 206)
            self.assertEqual(self.host.peticiones.count("POST /v2/media-sessions") - antes, 2)
            self.assertEqual(self.host.cuerpos[-1]["ttlSec"], 60)


class RespuestaArrastrarTests(SimpleTestCase):
    """`drag_drop` → `{"placements": [{itemId, targetId}]}`, como lo exige `POST /v2/evaluate` (contrato 2)."""

    PREGUNTA = {"pregunta_ref": "q", "tipo": "drag_drop", "elementos": [{"ref": "i1"}, {"ref": "i2"}, {"ref": "i3"}],
                "zonas": [{"zona_ref": "t1"}, {"zona_ref": "t2"}]}

    def test_una_pieza_por_zona_como_mucho_y_las_distractoras_pueden_quedarse_fuera(self):
        salida = respuestas.validar_respuesta(self.PREGUNTA, {"placements": [{"itemId": "i1", "targetId": "t1"}, {"itemId": "i2", "targetId": "t1"}]})
        self.assertEqual(salida, {"placements": [{"itemId": "i1", "targetId": "t1"}, {"itemId": "i2", "targetId": "t1"}]})

    def test_lo_que_no_vale(self):
        for mala in ({"placements": []}, {"placements": [{"itemId": "i9", "targetId": "t1"}]}, {"placements": [{"itemId": "i1", "targetId": "t9"}]},
                     {"placements": [{"itemId": "i1", "targetId": "t1"}, {"itemId": "i1", "targetId": "t2"}]}, {"order": ["i1"]}):
            with self.subTest(mala=mala), self.assertRaises(DatosInvalidos):
                respuestas.validar_respuesta(self.PREGUNTA, mala)
