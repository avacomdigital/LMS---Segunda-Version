"""
Los dos puntos de MOD-010 que la revisión independiente dejó abiertos (D-24), ya cerrados:

  A  El alumno no veía una nota sin publicar por la ruta de resultado de MOD-010: la política de liberación de MOD-010 y la publicación del libro eran dos controles independientes.
     Ahora, en un nivel en modo CALIFICACIONES, el resultado de un intento sólo sale si su calificación está publicada (compuerta de resultado: MOD-010 define el puerto, el libro
     registra la suya). En modo SIMPLE la política de MOD-010 sigue mandando (decisión S0).
  B  La administración conservaba `assessment.review` y podía puntuar y publicar una revisión por las rutas provisionales de MOD-010: puntuar es calificar y la administración no
     califica directamente. El profesor conserva el permiso; `acceso/0016` lo quita a ADMIN en las instalaciones que ya existen.
"""
from __future__ import annotations

import importlib
import pathlib
import re
from unittest import mock

from evaluacion.tests.base import respuesta_correcta

from .. import models as m
from .base import GB, BaseGradebook

EV = "/api/evaluacion"


class _ConResultado(BaseGradebook):
    def entrega(self, **extra) -> tuple[dict, str, dict]:
        """Juan presenta el examen (sólo lo cerrado: se califica solo) y lo entrega. Devuelve (asignación, intento, la respuesta de la entrega)."""
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, **extra)
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        refs = [r for r in tipos if tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(refs)])
        return a, i, self.entregar(i, confirmar=True)

    def resultado(self, intento_id: str):
        return self.api.get(f"{EV}/intentos/{intento_id}/resultado/", self.alumno())

    def calificacion_de(self, intento_id: str) -> m.Calificacion:
        self.sincronizar()
        return m.Calificacion.objects.get(intento_id=intento_id)


# ======================================================================================================= A

class EnModoCalificacionesElResultadoEsperaALaPublicacionTests(_ConResultado):
    def test_con_al_entregar_el_porcentaje_no_sale_hasta_que_el_libro_publica(self):
        a, i, entrega = self.entrega(resultados="al_entregar")
        # la política de MOD-010 lo mostraría al instante, pero la calificación aún no está publicada
        self.assertFalse(entrega["resultado_disponible"])
        self.assertEqual(entrega["que_sigue"]["codigo"], "resultado_en_libro")
        r = self.resultado(i)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["retenido_por"]), (403, "resultados_no_liberados", "libro_de_calificaciones"))
        self.assertNotIn("porcentaje", r.json())
        cal = self.calificacion_de(i)                                           # registrada («revisada»), todavía sin publicar
        self.assertEqual(cal.estado, "revisada")
        self.assertEqual(self.resultado(i).status_code, 403)
        self.assertFalse(self.estado(i)["resultado_disponible"])
        # el profesor publica en el libro: ahora sí
        self.gb(f"/calificaciones/{cal.id}/publicar/", {})
        r = self.resultado(i)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertGreater(r.json()["porcentaje"], 0)
        self.assertTrue(self.estado(i)["resultado_disponible"])

    def test_retirar_la_publicacion_vuelve_a_cerrar_el_resultado(self):
        a, i, _ = self.entrega(resultados="al_entregar")
        cal = self.calificacion_de(i)
        publicada = self.gb(f"/calificaciones/{cal.id}/publicar/", {})["calificacion"]
        self.assertEqual(self.resultado(i).status_code, 200)
        self.gb(f"/calificaciones/{cal.id}/retirar-publicacion/", {"motivo": "Se publicó antes de revisar el acta", "version_esperada": publicada["version"]})
        r = self.resultado(i)
        self.assertEqual((r.status_code, r.json()["retenido_por"]), (403, "libro_de_calificaciones"))

    def test_las_dos_condiciones_hacen_falta_a_la_vez(self):
        """Publicar en el libro no abre lo que la política de MOD-010 mantiene cerrado (`tras_liberar` sin liberar), ni liberar en MOD-010 abre lo que el libro no publicó."""
        a, i, _ = self.entrega()                                                # política por defecto: `tras_liberar`, manual
        cal = self.calificacion_de(i)
        self.gb(f"/calificaciones/{cal.id}/publicar/", {})
        r = self.resultado(i)                                                   # el libro publicó, MOD-010 no liberó
        self.assertEqual((r.status_code, r.json()["retenido_por"]), (403, None))
        self.assertFalse(self.estado(i)["resultado_disponible"])
        self.accion(f"/intentos/{i}/liberar-resultado/")                        # ahora MOD-010 también
        self.assertEqual(self.resultado(i).status_code, 200)

    def test_liberar_en_mod010_sin_publicar_en_el_libro_no_basta(self):
        a, i, _ = self.entrega()
        self.calificacion_de(i)                                                 # revisada, sin publicar
        self.accion(f"/intentos/{i}/liberar-resultado/")
        r = self.resultado(i)
        self.assertEqual((r.status_code, r.json()["retenido_por"]), (403, "libro_de_calificaciones"))

    def test_mis_evaluaciones_dice_quien_retiene_el_resultado(self):
        """La tableta lo lee para decir «tu profesor publicará tu calificación» y no «en cuanto termine de calificarse»."""
        a, i, _ = self.entrega(resultados="al_entregar")
        self.calificacion_de(i)

        def mi_intento():
            mias = self.api.get(f"{EV}/mias/", {**self.alumno(), "todas": "1"}).json()
            return next(e for e in mias["pendientes"] + mias["recientes"] if e["id"] == a["id"])["mi_intento"]

        retenido = mi_intento()
        self.assertEqual((retenido["resultado_disponible"], retenido["retenido_por"]), (False, "libro_de_calificaciones"))
        self.gb(f"/calificaciones/{m.Calificacion.objects.get(intento_id=i).id}/publicar/", {})
        publicado = mi_intento()
        self.assertEqual((publicado["resultado_disponible"], publicado["retenido_por"]), (True, None))

    def test_si_el_libro_aun_no_registro_la_calificacion_el_resultado_queda_retenido(self):
        a, i, _ = self.entrega(resultados="al_entregar")
        self.assertFalse(m.Calificacion.objects.exists())                       # el consumidor de eventos todavía no corrió
        self.assertEqual(self.resultado(i).status_code, 403)

    def test_un_fallo_de_la_compuerta_cierra_no_abre(self):
        a, i, _ = self.entrega(resultados="al_entregar")
        cal = self.calificacion_de(i)
        self.gb(f"/calificaciones/{cal.id}/publicar/", {})
        self.assertEqual(self.resultado(i).status_code, 200)

        def rota(asignacion, intento):
            raise RuntimeError("la base no responde")

        with mock.patch.dict("evaluacion.aplicacion.compuertas._COMPUERTAS", {"libro_de_calificaciones": rota}):
            self.assertEqual(self.resultado(i).status_code, 403)
        self.assertEqual(self.resultado(i).status_code, 200)


class EnModoSimpleLaPoliticaDeMod010SigueMandandoTests(_ConResultado):
    activar_modo = False                                                         # todo nivel sin configurar está en modo simple

    def test_con_al_entregar_el_alumno_ve_su_resultado_como_siempre(self):
        a, i, entrega = self.entrega(resultados="al_entregar")
        self.assertTrue(entrega["resultado_disponible"])
        self.assertEqual(entrega["que_sigue"]["codigo"], "resultado_disponible")
        self.assertEqual(self.resultado(i).status_code, 200)

    def test_con_la_politica_nunca_el_alumno_no_ve_cifras_ni_en_modo_simple(self):
        """Lo que el profesor usa para no mostrar cifras a los más pequeños: la política `nunca` de la evaluación."""
        a, i, entrega = self.entrega(resultados="nunca")
        self.assertEqual(entrega["que_sigue"]["codigo"], "sin_resultado")
        self.assertEqual(self.resultado(i).status_code, 403)

    def test_los_aciertos_en_simbolos_siguen_dependiendo_de_la_liberacion_de_mod010(self):
        a, i, _ = self.entrega(resultados="al_entregar")
        mias = self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]
        self.assertEqual(mias["modo"], "simple")
        self.assertTrue(mias["aciertos"]["simbolos"])


class UnNivelConOtroModoNoAfectaAlRestoTests(_ConResultado):
    def test_la_compuerta_mira_el_nivel_del_alumno_no_el_de_otro_grupo(self):
        """Preescolar sin configurar (simple) y secundaria en calificaciones conviven: sólo el segundo espera a la publicación."""
        pre = self.admin.post("/api/acceso/grupos/", {"codigo": "P1", "nombre": "Párvulos", "periodo": "2026", "nivel_clave": "preescolar"}, format="json")
        self.assertEqual(pre.status_code, 201, pre.content)
        ana_id, hw = self.alumno_con_tableta("Ana", "300905", capacidad="supervisado", grupo_id=pre.json()["id"])
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="al_entregar", grupo_id=pre.json()["id"])
        i = self.abrir(a["id"], hw=hw, alumno_id=ana_id)["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate([r for r in tipos if tipos[r] != "open"])], hw=hw, alumno_id=ana_id)
        self.entregar(i, hw=hw, alumno_id=ana_id, confirmar=True)
        self.assertEqual(self.api.get(f"{EV}/intentos/{i}/resultado/", self.alumno(hw, ana_id)).status_code, 200)       # preescolar: simple, manda MOD-010
        _, j, _ = self.entrega(resultados="al_entregar")                         # Juan, de secundaria (calificaciones)
        self.assertEqual(self.resultado(j).status_code, 403)


class ArquitecturaDeLaCompuertaTests(BaseGradebook):
    def test_mod010_no_importa_el_libro_y_la_compuerta_esta_registrada(self):
        from evaluacion.aplicacion import compuertas

        self.assertIn("libro_de_calificaciones", compuertas.registradas())
        raiz = pathlib.Path(importlib.import_module("evaluacion").__file__).parent
        for archivo in raiz.rglob("*.py"):
            if "tests" in archivo.parts or "migrations" in archivo.parts:
                continue
            self.assertIsNone(re.search(r"^\s*(?:from|import)\s+gradebook\b", archivo.read_text(encoding="utf-8"), re.M), f"{archivo} importa el libro")


# ======================================================================================================= B

class LaAdministracionNoPuntuaTests(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a, self.i, self.refs, self.tipos = self.examen_entregado(abiertas=True)
        self.abiertas = self.pendientes(self.i)
        self.sincronizar()

    def test_el_administrador_no_puntua_ni_publica_ni_ve_la_revision_por_las_rutas_de_mod010(self):
        ref = self.abiertas[0]
        for metodo, ruta, cuerpo in (("post", f"{EV}/intentos/{self.i}/respuestas/{ref}/puntuar/", {"puntaje": 1}),
                                     ("post", f"{EV}/intentos/{self.i}/publicar/", {}),
                                     ("get", f"{EV}/intentos/{self.i}/revision/", None)):
            r = getattr(self.admin, metodo)(ruta, cuerpo, format="json") if cuerpo is not None else self.admin.get(ruta)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"), ruta)
        self.assertEqual(self.fila(self.i).estado, "en_revision_docente")        # nada cambió

    def test_el_profesor_sigue_puntuando_y_confirmando(self):
        puntos = self.puntos_de(self.i)
        for ref in self.abiertas:
            self.gb(f"/revisiones/{self.i}/respuestas/{ref}/", {"puntaje": puntos[ref]})
        self.assertEqual(self.gb(f"/revisiones/{self.i}/confirmar/", {})["calificacion"]["estado"], "revisada")

    def test_el_administrador_no_tiene_assessment_review_pero_si_el_resto_de_la_evaluacion(self):
        from acceso.dominio import plantillas

        concedidos = plantillas.ROLES_SISTEMA["ADMIN"][3]
        self.assertNotIn("assessment.review", concedidos)
        self.assertIn("assessment.review", plantillas.ROLES_SISTEMA["TEACHER"][3])
        for conserva in ("assessment.read", "assessment.results.view", "assessment.assign", "assessment.attempt.void", "grades.mode.set"):
            self.assertIn(conserva, concedidos, conserva)


class MigracionQuitaElPermisoAlAdminTests(BaseGradebook):
    def test_borra_la_fila_una_vez_y_repetirla_no_hace_nada(self):
        from django.apps import apps

        from acceso.models import Rol, RolPermiso

        migracion = importlib.import_module("acceso.migrations.0016_admin_sin_assessment_review")
        rol = Rol.objects.get(codigo="ADMIN", organizacion__isnull=True)
        RolPermiso.objects.update_or_create(rol=rol, permiso_id="assessment.review", defaults={"alcance": "ORGANIZATION"})     # como en una instalación anterior
        self.assertTrue(RolPermiso.objects.filter(rol=rol, permiso_id="assessment.review").exists())
        migracion.quitar(apps, None)
        self.assertFalse(RolPermiso.objects.filter(rol=rol, permiso_id="assessment.review").exists())
        migracion.quitar(apps, None)                                              # idempotente
        # el profesor la conserva
        docente = Rol.objects.get(codigo="TEACHER", organizacion__isnull=True)
        self.assertTrue(RolPermiso.objects.filter(rol=docente, permiso_id="assessment.review").exists())
        # y la inversa la devuelve con alcance de organización
        migracion.devolver(apps, None)
        self.assertEqual(RolPermiso.objects.get(rol=rol, permiso_id="assessment.review").alcance, "ORGANIZATION")
