"""
El catálogo de AVACOM Biblioteca dentro de la búsqueda (cursos, lecciones y recursos): se pregunta EN VIVO, nunca se guarda (artículo 14). Se prueba el adaptador real contra
respuestas de `GET /v2/search` y la mezcla con lo del LMS con un catálogo de mentira (`CatalogoFalso`).

Lo que garantiza: lo que la biblioteca retira deja de salir en ese instante (TST-044); una biblioteca cerrada no tumba la búsqueda; el catálogo exige `content.read`; ciclo y
grupo (que son del padrón) lo excluyen; las preguntas nunca entran; los filtros del árbol llegan a la biblioteca y acotan lo del LMS por el curso de cada entidad.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from biblioteca.cliente import BibliotecaError, BibliotecaNoDisponible

from ..aplicacion.buscar import Buscar
from ..aplicacion.puertos import Actor
from ..dominio.documento import Visibilidad
from ..infraestructura.catalogo import CatalogoBiblioteca
from .base import SEARCH, BaseSearch

CURSO_FRACCIONES = "avacom.co.primary.4.math.fractions"
RESPUESTA = {"items": [
    {"scope": "course", "courseId": CURSO_FRACCIONES, "title": "Fracciones", "snippet": "Curso de **fracciones** y decimales",
     "treePath": ["Colombia", "Primaria", "Cuarto", "Matemáticas", "Fracciones"]},
    {"scope": "lesson", "courseId": CURSO_FRACCIONES, "lessonId": "l1", "title": "Fracciones propias", "snippet": "Las **fracciones** propias", "treePath": []},
    {"scope": "object", "courseId": CURSO_FRACCIONES, "lessonId": "l1", "objectId": "o1", "title": "Actividad de fracciones", "snippet": "**fracciones**"},
    {"scope": "question", "courseId": CURSO_FRACCIONES, "lessonId": "l1", "objectId": "o2", "questionId": "q1", "title": "¿Cuánto es un medio?",
     "snippet": "La **fracción** correcta es…"},
], "total": 7}


class AdaptadorTests(SimpleTestCase):
    def buscar(self, tipos=("course", "lesson", "resource"), **arbol):
        with mock.patch("biblioteca.contenido_v2._pedir", return_value=RESPUESTA) as pedir:
            resultado = CatalogoBiblioteca().buscar("fracciones", arbol, tipos, 100)
        return resultado, pedir

    def test_traduce_los_tres_ambitos_y_deja_fuera_las_preguntas(self):
        r, _ = self.buscar()
        self.assertTrue(r.disponible)
        self.assertEqual([(i.tipo, i.curso_ref, i.leccion_ref, i.objeto_ref) for i in r.impactos],
                         [("course", CURSO_FRACCIONES, "", ""), ("lesson", CURSO_FRACCIONES, "l1", ""), ("resource", CURSO_FRACCIONES, "l1", "o1")])
        self.assertEqual(r.total, 7)                                                      # lo que la biblioteca dice haber encontrado, aunque devuelva menos

    def test_quita_las_negritas_y_conserva_donde_estaban(self):
        r, _ = self.buscar()
        curso = r.impactos[0]
        self.assertEqual(curso.fragmento, "Curso de fracciones y decimales")
        self.assertEqual([curso.fragmento[a:b] for a, b in curso.resaltados], ["fracciones"])
        self.assertEqual(curso.ruta_arbol, ("Colombia", "Primaria", "Cuarto", "Matemáticas", "Fracciones"))

    def test_sólo_devuelve_los_tipos_pedidos(self):
        r, _ = self.buscar(tipos=("lesson",))
        self.assertEqual([i.tipo for i in r.impactos], ["lesson"])

    def test_manda_el_texto_el_perfil_de_profesor_y_los_filtros_del_arbol(self):
        _, pedir = self.buscar(country="CO", level="primary")
        (metodo, camino), argumentos = pedir.call_args.args, pedir.call_args.kwargs
        self.assertEqual((metodo, camino), ("GET", "/v2/search"))
        self.assertEqual(argumentos["consulta"], {"q": "fracciones", "scope": "all", "profile": "teacher", "country": "CO", "level": "primary"})

    def test_la_biblioteca_cerrada_no_es_un_error_es_no_disponible(self):
        with mock.patch("biblioteca.contenido_v2._pedir", side_effect=BibliotecaNoDisponible("AVACOM Biblioteca no está encendida.", "Ábrela.")):
            r = CatalogoBiblioteca().buscar("fracciones", {}, ("course",), 10)
        self.assertEqual((r.disponible, r.motivo, r.sugerencia, r.impactos), (False, "AVACOM Biblioteca no está encendida.", "Ábrela.", ()))

    def test_un_error_de_la_biblioteca_o_uno_inesperado_tampoco_rompe(self):
        for error in (BibliotecaError(500, "falló", codigo="internal"), BibliotecaError(400, "mala", codigo="invalid_parameter"), RuntimeError("raro")):
            with mock.patch("biblioteca.contenido_v2._pedir", side_effect=error):
                r = CatalogoBiblioteca().buscar("fracciones", {}, ("course",), 10)
            self.assertFalse(r.disponible)
            self.assertTrue(r.motivo)

    def test_el_arbol_y_los_cursos_de_un_nodo(self):
        nodos = [{"kind": "country", "code": "CO", "name": "Colombia", "count": 2, "children": []}]
        with mock.patch("biblioteca.contenido_v2._pedir", return_value=nodos):
            self.assertEqual(CatalogoBiblioteca().arbol(), (True, "", nodos))
        with mock.patch("biblioteca.contenido_v2._pedir", side_effect=BibliotecaNoDisponible("cerrada")):
            self.assertEqual(CatalogoBiblioteca().arbol()[:2], (False, "cerrada"))
        with mock.patch("biblioteca.contenido_v2.cursos", return_value=[{"courseId": "a"}, {"courseId": "b"}, {"id": "c"}, {}]) as cursos:
            self.assertEqual(CatalogoBiblioteca().cursos_del_arbol({"level": "primary"}), {"a", "b", "c"})
            cursos.assert_called_once_with(level="primary")
        with mock.patch("biblioteca.contenido_v2.cursos", side_effect=BibliotecaNoDisponible("cerrada")):
            self.assertIsNone(CatalogoBiblioteca().cursos_del_arbol({"level": "primary"}))

    def test_existe_distingue_retirado_de_no_se_pudo_saber(self):
        esquema = {"lessons": [{"id": "l1", "objects": [{"id": "o1"}]}, {"id": "l2", "objects": []}]}
        with mock.patch("biblioteca.contenido_v2.esquema_curso", return_value=esquema):
            c = CatalogoBiblioteca()
            self.assertIs(c.existe("c"), True)
            self.assertIs(c.existe("c", "l1"), True)
            self.assertIs(c.existe("c", "l1", "o1"), True)
            self.assertIs(c.existe("c", "l9"), False)
            self.assertIs(c.existe("c", "l2", "o1"), False)
        with mock.patch("biblioteca.contenido_v2.esquema_curso", side_effect=BibliotecaError(404, "no está", codigo="course_not_found")):
            self.assertIs(CatalogoBiblioteca().existe("c"), False)
        with mock.patch("biblioteca.contenido_v2.esquema_curso", side_effect=BibliotecaError(403, "política", codigo="disabled_by_policy")):
            self.assertIs(CatalogoBiblioteca().existe("c"), False)
        with mock.patch("biblioteca.contenido_v2.esquema_curso", side_effect=BibliotecaNoDisponible("cerrada")):
            self.assertIsNone(CatalogoBiblioteca().existe("c"))
        with mock.patch("biblioteca.contenido_v2.esquema_curso", side_effect=BibliotecaError(500, "falló", codigo="x")):
            self.assertIsNone(CatalogoBiblioteca().existe("c"))


class MezclaTests(BaseSearch):
    def setUp(self):
        super().setUp()
        self.catalogo.curso(CURSO_FRACCIONES, "Fracciones", "Curso de fracciones", country="CO", level="primary", grade="4", subject="math")
        self.catalogo.leccion(CURSO_FRACCIONES, "l1", "Suma de fracciones", "Las fracciones se suman")

    def test_el_catalogo_y_el_lms_se_ordenan_juntos_por_relevancia(self):
        a = self.evaluacion("Repaso de fracciones")
        r = self.buscar("fracciones")
        self.assertEqual([(x["source"], x["entity_type"]) for x in r["results"]], [("catalog", "course"), ("catalog", "lesson"), ("local", "assessment")])
        self.assertEqual(r["results"][0]["match"], "titulo_exacto")
        self.assertEqual(r["results"][2]["entity_id"], a["id"])
        self.assertEqual((r["total"], r["sources"]["catalog"]["status"], r["sources"]["local"]["status"]), (3, "ok", "ok"))
        self.assertEqual(r["results"][0]["context"]["tree_path"], ["CO", "Fracciones"])
        self.assertEqual(r["results"][1]["navigation_target"], {"entity_type": "lesson", "entity_id": "l1", "group_id": "", "course_ref": CURSO_FRACCIONES,
                                                              "lesson_ref": "l1", "object_ref": "", "source": "biblioteca"})

    def test_el_catalogo_cuenta_y_pagina_con_lo_demas(self):
        for n in range(3):
            self.evaluacion(f"Repaso {n} de fracciones")
        p1 = self.buscar("fracciones", limit=2, page=1)
        p2 = self.buscar("fracciones", limit=2, page=2)
        p3 = self.buscar("fracciones", limit=2, page=3)
        self.assertEqual([p["total"] for p in (p1, p2, p3)], [5, 5, 5])
        self.assertEqual([len(p["results"]) for p in (p1, p2, p3)], [2, 2, 1])
        self.assertEqual(len({x["entity_id"] for p in (p1, p2, p3) for x in p["results"]}), 5)

    def test_una_biblioteca_cerrada_no_tumba_la_busqueda(self):
        a = self.evaluacion("Repaso de fracciones")
        self.catalogo.disponible = False
        r = self.buscar("fracciones")
        self.assertEqual(self.ids(r), [a["id"]])
        self.assertEqual(r["sources"]["catalog"]["status"], "unavailable")
        self.assertIn("no está encendida", r["sources"]["catalog"]["reason"])
        self.assertEqual(r["sources"]["catalog"]["hint"], "Abre la aplicación de contenido.")

    def test_lo_que_la_biblioteca_retira_deja_de_salir_en_el_acto(self):
        """TST-044: la unidad se desactiva y la búsqueda siguiente ya no la devuelve; nada que sincronizar ni purgar en el LMS."""
        self.assertEqual(self.buscar("fracciones")["total"], 2)
        self.catalogo.retirar(CURSO_FRACCIONES)
        self.assertEqual(self.buscar("fracciones")["total"], 0)

    def test_el_filtro_de_tipo_decide_si_se_pregunta_a_la_biblioteca(self):
        self.evaluacion("Repaso de fracciones")
        self.buscar("fracciones", type="assessment")
        self.assertEqual(self.catalogo.consultas, [])
        self.assertEqual(self.buscar("fracciones", type="lesson")["total"], 1)
        self.assertEqual(self.catalogo.consultas[-1]["tipos"], ("lesson",))

    def test_ciclo_y_grupo_son_del_padron_y_dejan_fuera_al_catalogo(self):
        self.evaluacion("Repaso de fracciones")
        for filtro in ({"period": "2026"}, {"group": self.grupo["id"]}):
            r = self.buscar("fracciones", **filtro)
            self.assertEqual([x["source"] for x in r["results"]], ["local"], filtro)
        self.assertEqual(self.catalogo.consultas, [])

    def test_el_arbol_llega_a_la_biblioteca_y_acota_lo_del_lms_por_el_curso_de_cada_entidad(self):
        from evaluacion.tests.base import CURSO as CURSO_DE_EJEMPLO
        self.catalogo.clasificacion[CURSO_DE_EJEMPLO] = {"country": "CO", "level": "lower-secondary", "grade": "6", "subject": "science"}
        a = self.evaluacion("Estados de la materia")
        r = self.buscar("estados", level="lower-secondary")
        self.assertEqual(self.ids(r), [a["id"]])
        self.assertEqual(self.catalogo.consultas[-1]["arbol"], {"level": "lower-secondary"})
        self.assertEqual(self.buscar("estados", level="primary")["total"], 0)                      # el curso de esa evaluación cuelga de otro nivel
        self.assertEqual(self.ids(self.buscar("fracciones", level="primary", grade="4")), self.ids(self.buscar("fracciones", level="primary", subject="math")))
        self.assertEqual(self.buscar("fracciones", level="primary", grade="5")["total"], 0)

    def test_con_la_biblioteca_cerrada_un_filtro_de_arbol_no_se_puede_aplicar_y_se_dice(self):
        self.evaluacion("Estados de la materia")
        self.catalogo.disponible = False
        r = self.buscar("estados", level="primary")
        self.assertEqual((r["total"], r["results"]), (0, []))                                        # no se enseña lo que no se pudo filtrar
        self.assertIn("no se puede aplicar el filtro", r["notice"])

    def test_sin_content_read_no_se_pregunta_a_la_biblioteca(self):
        class Autorizacion:
            def exigir(self, actor, permiso): pass
            def tiene(self, actor, permiso): return True
            def visibilidad(self, actor):
                return Visibilidad(persona_id="p", por_tipo={"assessment": "GROUPS"}, grupos=frozenset(), contenido=False)

        servicios = self.servicios()
        servicios.autorizacion = Autorizacion()
        r = Buscar(servicios).ejecutar(Actor(id="p"), {"q": "fracciones"})
        self.assertEqual(self.catalogo.consultas, [])
        self.assertEqual((r["total"], r["sources"]["catalog"]["status"]), (0, "not_requested"))

    def test_las_preguntas_de_la_biblioteca_nunca_llegan_al_cliente(self):
        with mock.patch("biblioteca.contenido_v2._pedir", return_value=RESPUESTA):
            with mock.patch("search.infraestructura.contenedor.CatalogoBiblioteca", CatalogoBiblioteca):
                r = self.buscar("fracciones")
        self.assertEqual(sorted(x["entity_type"] for x in r["results"]), ["course", "lesson", "resource"])
        self.assertNotIn("question", str(r["results"]).lower().replace("questionid", ""))
        self.assertEqual(r["results"][0]["highlights"], [[9, 19]])


class AbrirDelCatalogoTests(BaseSearch):
    def setUp(self):
        super().setUp()
        self.catalogo.curso(CURSO_FRACCIONES, "Fracciones", country="CO")
        self.catalogo.leccion(CURSO_FRACCIONES, "l1", "Suma de fracciones")

    def abrir(self, cuerpo: dict, esperado: int = 200, cliente=None) -> dict:
        r = (cliente or self.docente).post(f"{SEARCH}/open/", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def test_abrir_un_curso_y_una_leccion_vuelve_a_comprobar_con_la_biblioteca(self):
        r = self.abrir({"entity_type": "course", "entity_id": CURSO_FRACCIONES})
        self.assertEqual(r["navigation_target"]["course_ref"], CURSO_FRACCIONES)
        r = self.abrir({"entity_type": "lesson", "entity_id": "l1", "course_ref": CURSO_FRACCIONES})
        self.assertEqual((r["navigation_target"]["lesson_ref"], r["navigation_target"]["source"]), ("l1", "biblioteca"))

    def test_si_la_biblioteca_lo_retiro_entre_la_busqueda_y_el_toque_ya_no_se_abre(self):
        self.catalogo.retirar(CURSO_FRACCIONES)
        self.assertEqual(self.abrir({"entity_type": "course", "entity_id": CURSO_FRACCIONES}, esperado=404)["codigo"], "no_disponible")

    def test_con_la_biblioteca_cerrada_se_dice_y_no_se_finge(self):
        self.catalogo.disponible = False
        r = self.abrir({"entity_type": "course", "entity_id": CURSO_FRACCIONES}, esperado=503)
        self.assertEqual(r["codigo"], "catalogo_no_disponible")

    def test_una_leccion_sin_su_curso_no_se_puede_abrir(self):
        self.assertEqual(self.abrir({"entity_type": "lesson", "entity_id": "l1"}, esperado=400)["codigo"], "datos_invalidos")


class FiltrosDelArbolTests(BaseSearch):
    def test_el_arbol_de_la_biblioteca_se_ofrece_anidado_y_aplanado(self):
        self.catalogo.nodos = [{"kind": "country", "code": "CO", "name": "Colombia", "count": 3, "children": [
            {"kind": "level", "code": "primary", "name": "Primaria", "count": 3, "children": [
                {"kind": "grade", "code": "4", "name": "Cuarto", "count": 2, "children": [
                    {"kind": "subject", "code": "math", "name": "Matemáticas", "count": 2, "children": [
                        {"kind": "topic", "code": "fractions", "name": "Fracciones", "count": 1, "children": []}]}]},
                {"kind": "grade", "code": "5", "name": "Quinto", "count": 1, "children": [
                    {"kind": "subject", "code": "math", "name": "Matemáticas", "count": 1, "children": []}]}]}]}]
        r = self.docente.get(f"{SEARCH}/filters/").json()
        self.assertEqual(r["tree"][0]["children"][0]["code"], "primary")
        self.assertEqual([c["code"] for c in r["countries"]], ["CO"])
        self.assertEqual([(c["code"], c["name"]) for c in r["levels"]], [("primary", "Primaria")])
        self.assertEqual([c["code"] for c in r["grades"]], ["4", "5"])
        self.assertEqual([c["code"] for c in r["subjects"]], ["math"])                                  # sin repetir
        self.assertEqual([c["code"] for c in r["topics"]], ["fractions"])
        self.assertEqual(r["catalog"], {"status": "ok", "reason": ""})

    def test_con_la_biblioteca_cerrada_los_filtros_siguen_con_lo_del_padron(self):
        self.catalogo.disponible = False
        r = self.docente.get(f"{SEARCH}/filters/").json()
        self.assertEqual(r["catalog"]["status"], "unavailable")
        self.assertEqual((r["tree"], r["levels"]), ([], []))
        self.assertEqual([g["name"] for g in r["groups"]], ["Octavo A"])
