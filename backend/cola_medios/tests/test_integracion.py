"""
La cola de medios dentro del nodo: las tres rutas de medios (aula, modo estudio, evaluación) sobre la API de Contenido v2 de pruebas, la preparación de lo que
se proyecta y de lo que se estudia, y las rutas `/api/medios/cola/`. Lo que cada módulo respondía antes lo siguen respondiendo igual: sólo cambia de dónde
salen los bytes.
"""
from __future__ import annotations

import hashlib
from unittest import mock

from django.core.cache import caches
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from classroom_engine.tests.test_sesiones import ConSesionDeClase
from evaluacion.infraestructura import fuentes_examen
from evaluacion.infraestructura.contenido import ContenidoEvaluacion
from modo_estudio.tests.base import BASE as BASE_ESTUDIO
from modo_estudio.tests.base import CURSO, BaseEstudio
from modo_estudio.tests.test_paquetes import BasePaquetes

from .. import models as m
from ..dominio import catalogos as cat
from ..infraestructura import contenedor
from .apoyo import configurar_cola, sin_cola

VIDEO = bytes((i * 13) % 253 for i in range(300_000))
AUDIO = b"ID3" + bytes(range(256)) * 200
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40
PDF = b"%PDF-1.4\n" + b"x" * 50_000
VTT = b"WEBVTT\n\n1\n00:00:00.000 --> 00:00:30.000\nEl hielo es solido."
MEDIOS = {
    "img-particles": ("image/png", PNG),
    "vid-changes": ("video/mp4", VIDEO),
    "vid-changes/@captions": ("text/vtt; charset=utf-8", VTT),
    "aud-summary": ("audio/mpeg", AUDIO),
    "pdf-lab-guide": ("application/pdf", PDF),
    "sim-phet-states/index.html": ("text/html; charset=utf-8", b"<html><script src='js/app.js'></script></html>"),
    "sim-phet-states/js/app.js": ("application/javascript", b"console.log('sim');"),
}
AULA = f"/api/aula/cursos/{CURSO}/medios"


def cuerpo(respuesta) -> bytes:
    return b"".join(respuesta.streaming_content) if respuesta.streaming else respuesta.content


def gets_de_medios(host) -> int:
    return sum(1 for p in host.peticiones if p.startswith("MEDIA GET"))


class AulaConLaColaTests(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.host = self.enterContext(self.host_de_contenido(MEDIOS))
        self.visor = APIClient()

    def get(self, ref, resto="", **cabeceras):
        return self.visor.get(f"{AULA}/{ref}/{resto}?fuente=biblioteca", **cabeceras)

    def test_los_bytes_son_los_mismos_y_la_fuente_los_sirve_una_sola_vez(self):
        for _ in range(3):
            r = self.get("vid-changes")
            self.assertEqual((r.status_code, r["Content-Type"], r["Content-Length"], r["Accept-Ranges"], r["Cache-Control"]),
                             (200, "video/mp4", str(len(VIDEO)), "bytes", "no-store"))
            self.assertEqual(cuerpo(r), VIDEO)
        self.assertEqual(gets_de_medios(self.host), 1)

    def test_range_como_lo_pide_un_reproductor(self):
        r = self.get("vid-changes", HTTP_RANGE="bytes=0-1023")
        self.assertEqual((r.status_code, r["Content-Range"], r["Content-Length"]), (206, f"bytes 0-1023/{len(VIDEO)}", "1024"))
        self.assertEqual(cuerpo(r), VIDEO[:1024])
        cola = self.get("vid-changes", HTTP_RANGE=f"bytes={len(VIDEO) - 10}-")
        self.assertEqual((cola.status_code, cuerpo(cola)), (206, VIDEO[-10:]))
        sufijo = self.get("vid-changes", HTTP_RANGE="bytes=-5")
        self.assertEqual(cuerpo(sufijo), VIDEO[-5:])
        fuera = self.get("vid-changes", HTTP_RANGE=f"bytes={len(VIDEO) + 5}-")
        self.assertEqual((fuera.status_code, fuera["Content-Range"]), (416, f"bytes */{len(VIDEO)}"))
        self.assertEqual(gets_de_medios(self.host), 1)

    def test_head_primero_va_a_la_fuente_y_despues_sale_de_la_cache(self):
        h = self.visor.head(f"{AULA}/vid-changes/?fuente=biblioteca")
        self.assertEqual((h.status_code, h["Content-Type"]), (200, "video/mp4"))
        self.assertEqual(self.get("vid-changes").status_code, 200)
        antes = gets_de_medios(self.host)
        h = self.visor.head(f"{AULA}/vid-changes/?fuente=biblioteca")
        self.assertEqual((h.status_code, h["Content-Length"], h.content), (200, str(len(VIDEO)), b""))
        self.assertEqual(gets_de_medios(self.host), antes)

    def test_subtitulos_archivos_de_una_simulacion_y_todos_los_tipos(self):
        for ref, resto, tipo, esperado in (("img-particles", "", "image/png", PNG), ("aud-summary", "", "audio/mpeg", AUDIO),
                                           ("pdf-lab-guide", "", "application/pdf", PDF), ("vid-changes", "subtitulos", "text/vtt", VTT),
                                           ("sim-phet-states", "index.html", "text/html", None), ("sim-phet-states", "js/app.js", "application/javascript",
                                                                                                    b"console.log('sim');")):
            r = self.get(ref, resto)
            self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, tipo), f"{ref}/{resto}")
            if esperado is not None:
                self.assertEqual(cuerpo(r), esperado, f"{ref}/{resto}")

    def test_un_medio_que_no_existe_da_el_mismo_404_de_siempre(self):
        r = self.get("no-existe")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "referencia_no_encontrada"))
        r = self.get("no-existe")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "referencia_no_encontrada"))      # también con el fallo recordado

    def test_un_curso_que_no_existe_da_el_mismo_404_de_siempre(self):
        r = self.visor.get(f"/api/aula/cursos/no-existe/medios/vid-changes/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "curso_no_encontrado"))

    def test_con_la_biblioteca_cerrada_dice_lo_de_siempre(self):
        self.host.detener()
        r = self.get("vid-changes")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["disponible"]), (503, "fuente_no_disponible", False))

    def test_apagada_la_cola_responde_lo_mismo_que_encendida(self):
        encendida = [(self.get(ref).status_code, cuerpo(self.get(ref))) for ref in ("img-particles", "vid-changes", "aud-summary")]
        sin_cola(self)
        apagada = [(self.get(ref).status_code, cuerpo(self.get(ref))) for ref in ("img-particles", "vid-changes", "aud-summary")]
        self.assertEqual(encendida, apagada)

    def test_si_la_cola_se_rompe_el_medio_se_sirve_como_antes(self):
        with mock.patch("cola_medios.aplicacion.servidor.Servidor.abrir", side_effect=RuntimeError("bug de la cola")):
            r = self.get("vid-changes")
        self.assertEqual((r.status_code, cuerpo(r)), (200, VIDEO))

    def test_una_version_nueva_del_curso_se_ve_en_el_siguiente_get(self):
        self.assertEqual(cuerpo(self.get("img-particles")), PNG)
        self.host.manifiestos[CURSO]["version"] = "9.9.9"
        self.host.medios["img-particles"] = ("image/png", b"\x89PNG\r\n\x1a\nNUEVA")
        caches["medios"].clear()                                   # pasó la vigencia de la versión
        self.assertEqual(cuerpo(self.get("img-particles")), b"\x89PNG\r\n\x1a\nNUEVA")

    def test_el_pase_de_medios_sigue_siendo_la_unica_llave(self):
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.visor.get(f"{AULA}/vid-changes/?fuente=biblioteca").status_code, 401)       # sin sesión ni pase no se sirve ni de la caché
            self.assertEqual(self.docente.get(f"{AULA}/vid-changes/?fuente=biblioteca").status_code, 200)
            r = self.visor.get(f"{AULA}/vid-changes/?fuente=biblioteca".replace("/api/", "/api/m/pase-falso/", 1))
            self.assertEqual(r.status_code, 401)


class EstudioConLaColaTests(BasePaquetes):
    MEDIOS_E = {
        "img-particles": ("image/png", PNG), "aud-summary": ("audio/mpeg", AUDIO), "pdf-lab-guide": ("application/pdf", PDF),
        "vid-changes": ("video/mp4", VIDEO),
    }

    def pedir_paquete(self, hw: str, asignacion_id: str) -> dict:
        return self.json_ok(self.solicitar(hw, asignacion_id=asignacion_id), 201)["paquete"]

    def test_dos_alumnos_piden_el_paquete_y_la_fuente_entrega_cada_medio_una_vez(self):
        with self.host_de_contenido(self.MEDIOS_E) as host:
            a = self.crear_asignacion(fuente="biblioteca")
            uno = self.pedir_paquete(self.hw_juan, a["id"])
            traidos = gets_de_medios(host)
            self.assertGreaterEqual(traidos, 4)
            _, hw_ana = self.alumno_con_tableta("Ana", "A-100")
            dos = self.pedir_paquete(hw_ana, a["id"])
            self.assertEqual(gets_de_medios(host), traidos)                       # el segundo alumno no le cuesta nada a Contenido
            self.assertEqual({x["media_ref"]: (x["bytes"], x["sha256"]) for x in uno["archivos"]},
                             {x["media_ref"]: (x["bytes"], x["sha256"]) for x in dos["archivos"]})
            self.assertRegex(dos["huella"], r"^[0-9a-f]{64}$")
            contextos = set(m.Solicitud.objects.filter(modulo="estudio").values_list("contexto_ref", flat=True))
            self.assertEqual(contextos, {a["id"]})

    def test_la_descarga_del_archivo_sale_de_la_cache_con_range_y_con_su_etag(self):
        with self.host_de_contenido(self.MEDIOS_E) as host:
            a = self.crear_asignacion(fuente="biblioteca")
            p = self.pedir_paquete(self.hw_juan, a["id"])
            traidos = gets_de_medios(host)
            sha = {x["media_ref"]: x["sha256"] for x in p["archivos"]}["vid-changes"]
            r = self.archivo(p["id"], "vid-changes", HTTP_RANGE="bytes=1000-1999")
            self.assertEqual((r.status_code, r["ETag"], r["Content-Range"]), (206, f'"{sha}"', f"bytes 1000-1999/{len(VIDEO)}"))
            self.assertEqual(cuerpo(r), VIDEO[1000:2000])
            completo = self.archivo(p["id"], "vid-changes")
            self.assertEqual(hashlib.sha256(cuerpo(completo)).hexdigest(), sha)
            self.assertEqual(gets_de_medios(host), traidos)

    def test_el_tope_de_tamano_sigue_funcionando_con_la_cola(self):
        with self.host_de_contenido(self.MEDIOS_E), override_settings(AVACOM_ESTUDIO_MEDIO_MAX_MB=0):
            a = self.crear_asignacion(fuente="biblioteca")
            p = self.pedir_paquete(self.hw_juan, a["id"])
        self.assertEqual(p["archivos"], [])
        self.assertIn("medio_demasiado_grande", {x["motivo"] for x in p["no_incluidos"]})

    def test_los_medios_de_la_leccion_en_linea_pasan_por_la_cola(self):
        with self.host_de_contenido(self.MEDIOS_E) as host:
            a = self.crear_asignacion(fuente="biblioteca")
            antes = sum(1 for p in host.peticiones if p.startswith("MEDIA GET") and p.endswith("/vid-changes"))
            for _ in range(2):
                r = self.ver(f"/asignaciones/{a['id']}/medios/vid-changes/")
                self.assertEqual((r.status_code, cuerpo(r)), (200, VIDEO))
            despues = sum(1 for p in host.peticiones if p.startswith("MEDIA GET") and p.endswith("/vid-changes"))
            self.assertEqual(despues - antes, 1)


class EvaluacionPreparaLosMediosDeSuIntentoTests(BaseEstudio):
    def test_las_preguntas_de_un_intento_ponen_sus_medios_en_cola_con_prioridad_de_examen(self):
        contenido = ContenidoEvaluacion()
        crudas = [{"id": "q1", "mediaIds": ["img-particles"]}, {"id": "q2", "options": [{"mediaId": "vid-changes"}, {"mediaId": None}]}, {"id": "q3"}]
        with self.host_de_contenido(MEDIOS), \
                mock.patch.object(ContenidoEvaluacion, "_crudo", return_value=(object(), {"questions": crudas, "version": "1.0.0", "title": "Examen"})), \
                mock.patch.object(fuentes_examen, "esquema", return_value={"media": []}), \
                mock.patch.object(fuentes_examen, "preguntas_de_examen", return_value=[{"pregunta_ref": "q1"}]), \
                self.captureOnCommitCallbacks(execute=True):
            vista = contenido.preguntas("biblioteca", CURSO, "1.0.0", "l3-exam", ["q1"], "semilla", intento_id="intento-7", dispositivo="hw-juan",
                                        alumno_id=self.estudiante_id)
        self.assertEqual(vista["preguntas"], [{"pregunta_ref": "q1"}])         # preparar los medios no toca lo que ve el alumno
        filas = list(m.Solicitud.objects.filter(contexto_ref="intento-7").select_related("recurso"))
        self.assertEqual(sorted(s.recurso.media_ref for s in filas), ["img-particles", "vid-changes"])
        self.assertTrue(all((s.modulo, s.prioridad, s.persona_id) == ("evaluacion", cat.EVALUACION, self.estudiante_id) for s in filas))

    def test_el_medio_de_un_examen_se_sirve_por_la_cola_con_la_prioridad_de_examen(self):
        with self.host_de_contenido(MEDIOS) as host:
            primero = ContenidoEvaluacion().abrir_medio("biblioteca", CURSO, "img-particles", None, None, "GET")
            segundo = ContenidoEvaluacion().abrir_medio("biblioteca", CURSO, "img-particles", None, "bytes=0-7", "GET")
            self.assertEqual(primero.flujo.read(-1), PNG)
            self.assertEqual(segundo.flujo.read(-1), PNG[:8])
            self.assertEqual(gets_de_medios(host), 1)
            primero.flujo.close()
            segundo.flujo.close()


class PreparacionDeLaClaseTests(ConSesionDeClase):
    """Lo que el profesor proyecta o lanza queda en la cola del nodo, con la prioridad más alta, ligado a su clase."""

    def drenar(self) -> None:
        servidor = contenedor.servidor()
        while True:
            tarea = servidor.planificador.siguiente(urgente_solo=False, segundos=0.01)
            if tarea is None:
                return
            servidor.descargador.ejecutar(tarea)

    def contexto(self, sesion_id: str) -> list[m.Recurso]:
        return list(m.Recurso.objects.filter(solicitudes__contexto_ref=sesion_id).distinct().order_by("media_ref"))

    def test_iniciar_la_clase_prepara_los_medios_del_primer_objeto(self):
        with self.captureOnCommitCallbacks(execute=True):
            s = self.iniciar()
        refs = [r.media_ref for r in self.contexto(s["id"])]
        self.assertIn("img-particles", refs)
        self.assertTrue(all(r.estado == "pendiente" for r in self.contexto(s["id"])))
        self.assertTrue(all(sol.prioridad == cat.PROYECCION and sol.modulo == "aula" for sol in m.Solicitud.objects.filter(contexto_ref=s["id"])))

    def test_declarar_el_selector_baja_lo_que_se_proyectaba_antes(self):
        with self.captureOnCommitCallbacks(execute=True):
            s = self.iniciar()
        antes = {r.media_ref for r in self.contexto(s["id"])}
        with self.captureOnCommitCallbacks(execute=True):
            r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"media_ref": "aud-summary", "rotulo": "Resumen", "profesor_id": "prof-1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        por_medio = {sol.recurso.media_ref: sol.prioridad for sol in m.Solicitud.objects.filter(contexto_ref=s["id"]).select_related("recurso")}
        self.assertEqual(por_medio["aud-summary"], cat.PROYECCION)
        for ref in antes - {"aud-summary"}:
            self.assertEqual(por_medio[ref], cat.CLASE, ref)

    def test_lanzar_un_recurso_lo_prepara_sin_bajar_la_proyeccion(self):
        with self.captureOnCommitCallbacks(execute=True):
            s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{pid}/admitir/", {}, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            r = self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/", {"clase": "recurso", "media_ref": "pdf-lab-guide", "alcance": "grupo",
                                                                               "profesor_id": "prof-1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        por_medio = {sol.recurso.media_ref: sol.prioridad for sol in m.Solicitud.objects.filter(contexto_ref=s["id"]).select_related("recurso")}
        self.assertEqual(por_medio["pdf-lab-guide"], cat.PROYECCION)
        self.assertEqual(por_medio["img-particles"], cat.PROYECCION)

    def test_si_la_cola_falla_la_clase_sigue(self):
        with mock.patch("cola_medios.servicio.preparar_objeto", side_effect=RuntimeError("bug de la cola")), self.captureOnCommitCallbacks(execute=True):
            s = self.iniciar()
        self.assertEqual(s["estado"], "abierta")

    def test_sin_la_cola_encendida_no_se_prepara_nada_y_la_clase_funciona(self):
        sin_cola(self)
        with self.captureOnCommitCallbacks(execute=True):
            s = self.iniciar()
        self.assertEqual(s["estado"], "abierta")
        self.assertEqual(m.Recurso.objects.count(), 0)

    def test_el_avance_de_la_clase_se_consulta_por_su_sesion(self):
        with self.captureOnCommitCallbacks(execute=True):
            s = self.iniciar()
        r = self.api.get(f"/api/medios/cola/recursos/?contexto={s['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["total"], 1)
        self.assertEqual({x["estado"] for x in r.json()["recursos"]}, {"pendiente"})
        self.drenar()
        r = self.api.get(f"/api/medios/cola/recursos/?contexto={s['id']}&estado=disponible")
        recursos = r.json()["recursos"]
        self.assertTrue(recursos)
        self.assertTrue(all(x["porcentaje"] == 100 and len(x["sha256"]) == 64 and x["prioridad"] == "proyeccion" for x in recursos))
        self.assertEqual(self.api.get(f"/api/medios/cola/recursos/?contexto={s['id']}&estado=raro").status_code, 400)


class RutasDeLaColaTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def crear(self, estado="disponible", **extra) -> m.Recurso:
        import uuid
        ahora = 1_800_000_000_000
        return m.Recurso.objects.create(id=str(uuid.uuid4()), clave=uuid.uuid4().hex + uuid.uuid4().hex, fuente="biblioteca", curso_ref="c", media_ref="m",
                                        estado=estado, creado_en=ahora, actualizado_en=ahora, bytes_total=10, bytes_hechos=10, **extra)

    def test_el_estado_dice_como_va_la_cola_y_cuales_son_sus_limites(self):
        self.crear()
        self.crear("fallido", error_codigo="origen_no_disponible")
        r = self.api.get("/api/medios/cola/")
        self.assertEqual(r.status_code, 200)
        e = r.json()
        self.assertEqual((e["activa"], e["recursos"]["disponible"], e["recursos"]["fallido"]), (True, 1, 1))
        for clave in ("cola", "cache", "transferencias", "limites", "contadores"):
            self.assertIn(clave, e)
        self.assertEqual(e["limites"]["transferencias_simultaneas"], 24)
        self.assertEqual(e["cache"]["bytes_maximo"], 4096 * 1024 * 1024)

    def test_un_recurso_se_consulta_por_su_id(self):
        r = self.crear()
        self.assertEqual(self.api.get(f"/api/medios/cola/recursos/{r.id}/").json()["id"], r.id)
        self.assertEqual(self.api.get("/api/medios/cola/recursos/no-existe/").status_code, 404)

    def test_cancelar_y_reintentar_son_del_personal(self):
        fallido = self.crear("fallido", error_codigo="origen_no_disponible", curso_version="1.0")
        listo = self.crear()
        self.assertEqual(self.api.post(f"/api/medios/cola/recursos/{listo.id}/cancelar/").status_code, 409)       # ya está listo
        self.assertEqual(self.api.post(f"/api/medios/cola/recursos/{listo.id}/reintentar/").status_code, 409)
        self.assertEqual(self.api.post("/api/medios/cola/recursos/no-existe/cancelar/").status_code, 409)

    def test_limpiar_vacia_la_cache(self):
        self.crear()
        r = self.api.post("/api/medios/cola/limpiar/")
        self.assertEqual((r.status_code, r.json()["expulsados"]), (200, 1))
        self.assertEqual(m.Recurso.objects.count(), 0)

    def test_una_tableta_de_alumno_no_cambia_la_cola(self):
        from acceso.interfaces import permisos
        from types import SimpleNamespace
        r = self.crear()
        alumno = SimpleNamespace(menu="student")
        with mock.patch.object(permisos, "principal_de", return_value=alumno), \
                mock.patch("cola_medios.interfaces.views.principal_de", return_value=alumno):
            self.assertEqual(self.api.post("/api/medios/cola/limpiar/").status_code, 403)
            self.assertEqual(self.api.post(f"/api/medios/cola/recursos/{r.id}/cancelar/").status_code, 403)
            self.assertEqual(self.api.post(f"/api/medios/cola/recursos/{r.id}/reintentar/").status_code, 403)
            self.assertEqual(self.api.get("/api/medios/cola/").status_code, 200)             # ver sí puede
        self.assertEqual(m.Recurso.objects.count(), 1)

    def test_con_la_sesion_obligatoria_las_rutas_piden_sesion(self):
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.api.get("/api/medios/cola/").status_code, 401)
            self.assertEqual(self.api.post("/api/medios/cola/limpiar/").status_code, 401)
