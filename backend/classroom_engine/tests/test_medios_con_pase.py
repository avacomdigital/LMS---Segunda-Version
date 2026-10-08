"""
Bugfix 01 (QA-27) · los medios del aula con la sesión obligatoria.

Con `AVACOM_LMS_EXIGIR_SESION=1` la ruta de medios pedía `Authorization: Bearer`, pero quien pide un medio es el VISOR (la `<video>` de la WebView, `Image` de MAUI),
que no manda cabeceras: todo medio daba 401 y el reproductor decía «formato no compatible». Ahora la lección entrega cada medio con un pase en el camino
(`/api/m/<pase>/aula/cursos/…/medios/…`) que sólo abre medios y sólo mientras viva la sesión que lo emitió.

Los medios salen de la API de Contenido v2 de pruebas (`fuente=biblioteca`): es la fuente real de un nodo instalado y la única que sirve video.
"""
from __future__ import annotations

import json
import re

import jwt
from django.test import override_settings
from rest_framework.test import APIClient

from acceso.aplicacion.casos_uso import PaseDeMedios
from acceso.infraestructura.contenedor import servicios as servicios_acceso
from acceso.tests.base import BaseAcceso
from modo_estudio.tests.base import BaseEstudio

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
LECCION = "l1-three-states"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
VIDEO = bytes(range(256)) * 400                                     # 102 400 bytes
AUDIO = b"ID3" + bytes(range(256)) * 200
PDF = b"%PDF-1.4\n" + b"0" * 500
MEDIOS = {
    "img-particles": ("image/png", PNG),
    "vid-changes": ("video/mp4", VIDEO),
    "vid-changes/@captions": ("text/vtt; charset=utf-8", b"WEBVTT\n\n1\n00:00:00.000 --> 00:00:30.000\nEl hielo es solido."),
    "aud-summary": ("audio/mpeg", AUDIO),
    "pdf-lab-guide": ("application/pdf", PDF),
    "sim-phet-states/states-of-matter-basics_es.html": ("text/html; charset=utf-8", b"<html><script src='js/app.js'></script></html>"),
    "sim-phet-states/js/app.js": ("application/javascript", b"console.log('sim');"),
}


def urls_de_medios(vista: dict) -> list[str]:
    """Toda cadena `/api/…/medios/…` de una vista (bloques, portada, subtítulos, lanzamientos)."""
    return re.findall(r'"(/api/[^"]*/medios/[^"]*)"', json.dumps(vista))


def pase_de(url: str) -> str:
    return url.split("/")[3]


def sesion_id_de(cliente) -> str:
    """La sesión es el `jti` del JWT del cliente."""
    return jwt.decode(cliente.token, options={"verify_signature": False})["jti"]


def url_de(urls: list[str], ref: str, resto: str = "?") -> str:
    return next(u for u in urls if f"/medios/{ref}/{resto}" in u)


class MediosConSesionObligatoriaTests(BaseEstudio):
    """El nodo instalado (sesión obligatoria) con la API de Contenido de pruebas como biblioteca."""

    def setUp(self):
        super().setUp()      # el nodo se instala y se abren las sesiones en modo prototipo; después se cierra
        self.host = self.enterContext(self.host_de_contenido(MEDIOS))
        self.enterContext(override_settings(AVACOM_LMS_EXIGIR_SESION=True))
        self.visor = APIClient()                           # sin credenciales: lo que hace una <video> o una Image

    def leccion(self, cliente=None) -> dict:
        r = (cliente or self.docente).get(f"/api/aula/cursos/{CURSO}/lecciones/{LECCION}/?fuente=biblioteca")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def urls(self, cliente=None) -> list[str]:
        return urls_de_medios(self.leccion(cliente))

    def test_el_sintoma_original_el_visor_sin_cabeceras_no_entra_por_la_ruta_con_bearer(self):
        # La ruta con Bearer sigue siendo la de siempre (herramientas, pruebas): sin cabecera, 401; con ella, el medio.
        ruta = f"/api/aula/cursos/{CURSO}/medios/vid-changes/?fuente=biblioteca"
        self.assertEqual(self.visor.get(ruta).status_code, 401)
        self.assertEqual(self.docente.get(ruta).status_code, 200)

    def test_la_leccion_entrega_cada_medio_con_su_pase_en_el_camino(self):
        urls = self.urls()
        self.assertGreater(len(urls), 5)
        for url in urls:
            self.assertRegex(url, r"^/api/m/[\w-]+\.[\w-]+\.[\w-]+/aula/cursos/[^/]+/medios/", url)

    def test_el_visor_sin_cabeceras_abre_video_audio_imagen_subtitulos_y_pdf(self):
        urls = self.urls()
        for ref, tipo in {"vid-changes": "video/mp4", "aud-summary": "audio/mpeg", "img-particles": "image/png", "pdf-lab-guide": "application/pdf"}.items():
            r = self.visor.get(url_de(urls, ref))
            self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, tipo), ref)
        r = self.visor.get(url_de(urls, "vid-changes", "subtitulos"))
        self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, "text/vtt"))

    def test_range_y_head_funcionan_con_el_pase_como_los_pide_un_reproductor(self):
        url = url_de(self.urls(), "vid-changes")
        r = self.visor.get(url, HTTP_RANGE="bytes=0-1023")
        self.assertEqual((r.status_code, len(b"".join(r.streaming_content)), r["Content-Range"]), (206, 1024, f"bytes 0-1023/{len(VIDEO)}"))
        cola = self.visor.get(url, HTTP_RANGE=f"bytes={len(VIDEO) - 10}-")
        self.assertEqual((cola.status_code, b"".join(cola.streaming_content)), (206, VIDEO[-10:]))
        cabecera = self.visor.head(url)
        self.assertEqual((cabecera.status_code, cabecera["Content-Type"]), (200, "video/mp4"))

    def test_un_archivo_relativo_de_una_simulacion_hereda_el_pase_del_camino(self):
        lanzamiento = next(u for u in self.urls() if "/medios/sim-phet-states/" in u and u.split("?")[0].endswith(".html"))
        pase = pase_de(lanzamiento)
        self.assertEqual(self.visor.get(lanzamiento).status_code, 200)
        # Lo que el navegador resuelve para `js/app.js` desde la página de la simulación: misma carpeta, mismo prefijo de camino.
        relativo = lanzamiento.split("?")[0].rsplit("/", 1)[0] + "/js/app.js"      # sin `?fuente=`: el navegador no lo hereda
        self.assertTrue(relativo.startswith(f"/api/m/{pase}/aula/cursos/"))
        with override_settings(AVACOM_AULA_PERMITIR_EJEMPLO=False):               # como en un nodo real: los cursos salen de la biblioteca
            r = self.visor.get(relativo)
        self.assertEqual((r.status_code, b"".join(r.streaming_content)), (200, b"console.log('sim');"))

    def test_las_cabeceras_cors_dejan_cargar_los_subtitulos_desde_la_pagina_del_reproductor(self):
        url = url_de(self.urls(), "vid-changes", "subtitulos")
        r = self.visor.get(url, HTTP_ORIGIN="null")
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
        previa = self.visor.options(url, HTTP_ORIGIN="null", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="range")
        self.assertEqual((previa.status_code, previa["Access-Control-Allow-Origin"]), (204, "*"))
        self.assertIn("Range", previa["Access-Control-Allow-Headers"])

    def test_un_pase_alterado_se_rechaza(self):
        url = url_de(self.urls(), "vid-changes")
        pase = pase_de(url)
        for malo in (pase[:-3] + ("AAA" if not pase.endswith("AAA") else "BBB"), "no-es-un-pase", pase.split(".")[0]):
            r = self.visor.get(url.replace(pase, malo))
            self.assertEqual((r.status_code, r.json()["codigo"]), (401, "pase_de_medios_invalido"), malo)

    def test_un_pase_vencido_dice_que_vencio(self):
        url = url_de(self.urls(), "vid-changes")
        vencido = PaseDeMedios(servicios_acceso()).emitir(self.docente_id, sesion_id_de(self.docente), ahora_ms=1_000_000_000)
        r = self.visor.get(url.replace(pase_de(url), vencido))
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "pase_de_medios_vencido"))

    def test_el_pase_muere_con_la_sesion_que_lo_emitio(self):
        url = url_de(self.urls(), "vid-changes")
        self.assertEqual(self.visor.get(url).status_code, 200)
        self.assertEqual(self.docente.delete("/api/acceso/sesiones/actual/").status_code, 204)
        r = self.visor.get(url)
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "sesion_revocada"))

    def test_el_pase_no_vale_como_sesion_de_api_ni_fuera_de_los_medios(self):
        pase = pase_de(url_de(self.urls(), "vid-changes"))
        # 1. Como Authorization: no es una sesión (su jti no es el de ninguna).
        r = self.visor.get("/api/aula/cursos/?fuente=biblioteca", HTTP_AUTHORIZATION=f"Bearer {pase}")
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "sesion_invalida"))
        # 2. En el camino, sólo rutas de medios: ni la API del aula, ni el expediente, ni la identidad.
        for ruta in ("aula/cursos/", f"aula/cursos/{CURSO}/", "aula/sesiones/", "acceso/sesiones/actual/", "expediente/", "health/", ""):
            r = self.visor.get(f"/api/m/{pase}/{ruta}")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pase_de_medios_fuera_de_alcance"), ruta)
        # 3. Sólo leer.
        for metodo in ("post", "put", "patch", "delete"):
            r = getattr(self.visor, metodo)(f"/api/m/{pase}/aula/cursos/{CURSO}/medios/vid-changes/", {}, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (405, "pase_de_medios_metodo"), metodo)

    def test_el_registro_de_la_peticion_no_lleva_el_pase(self):
        url = url_de(self.urls(), "vid-changes")
        pase = pase_de(url)
        with self.assertLogs("avacom.app", level="INFO") as registro:
            self.visor.get(url)
        texto = "\n".join(f"{r.getMessage()} {getattr(r, 'detalle', '')}" for r in registro.records)
        self.assertNotIn(pase, texto)
        self.assertIn(f"/api/aula/cursos/{CURSO}/medios/vid-changes/", texto)

    def test_cada_persona_recibe_sus_medios_con_su_propio_pase(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        del_alumno, del_docente = self.urls(alumno), self.urls()
        self.assertTrue(all("/api/m/" in u for u in del_alumno))
        self.assertNotEqual(pase_de(del_alumno[0]), pase_de(del_docente[0]))
        self.assertEqual(self.visor.get(url_de(del_alumno, "vid-changes")).status_code, 200)

    # ------------------------------------------------------------ modo de estudio
    def test_el_modo_de_estudio_entrega_y_sirve_sus_medios_con_pase_y_conserva_la_regla_de_la_asignacion(self):
        with override_settings(AVACOM_LMS_EXIGIR_SESION=False):      # asignar y dar de alta aparatos se hace como en el resto de las pruebas
            a = self.crear_asignacion(fuente="biblioteca")
            luis, hw_luis = self.alumno_con_tableta("Luis", "400222", grupo_id=self.otro_grupo["id"])
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.hw_juan)
        r = juan.get(f"/api/modo-estudio/lecciones/{a['id']}/", {"dispositivo": self.hw_juan})
        self.assertEqual(r.status_code, 200, r.content)
        urls = urls_de_medios(r.json()["leccion"])
        self.assertTrue(urls and all(re.match(rf"^/api/m/[\w.-]+/modo-estudio/asignaciones/{a['id']}/medios/", u) for u in urls), urls[:2])
        propia = url_de(urls, "img-particles")
        r = self.visor.get(propia)
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        # Un alumno al que la asignación no le alcanza sigue sin ver el medio, aunque tenga pase: el pase es suyo, la regla es la de siempre.
        sesion_luis = self.sesion("400222", "573920", hw_luis)
        ajeno = PaseDeMedios(servicios_acceso()).emitir(luis, sesion_id_de(sesion_luis))
        r = self.visor.get(propia.replace(pase_de(propia), ajeno))
        self.assertEqual(r.status_code, 404)


class SinSesionObligatoriaTests(BaseAcceso):
    """Modo prototipo (Q-34 abierta): sin sesión no hay de quién emitir un pase y las direcciones quedan como siempre."""

    def test_sin_sesion_la_direccion_no_lleva_pase(self):
        r = APIClient().get(f"/api/aula/cursos/{CURSO}/lecciones/{LECCION}/?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        urls = urls_de_medios(r.json())
        self.assertGreater(len(urls), 5)
        self.assertTrue(all(u.startswith("/api/aula/cursos/") for u in urls), urls[:3])
        self.assertEqual(APIClient().get(url_de(urls, "img-particles")).status_code, 200)
