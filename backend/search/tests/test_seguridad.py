"""
BR-088 y TST-073 (alta prioridad, BLOQUEANTES): la búsqueda sólo devuelve lo que la persona puede leer, con lo que vale AHORA, aunque el índice vaya rezagado.

  · un docente nunca encuentra lo de un grupo que no enseña (ni su título, ni un fragmento, ni un conteo, ni por el filtro de grupo)
  · quitarle el grupo, desactivar el grupo o retirar la entidad surte efecto en la PRÓXIMA consulta, sin esperar a ningún evento ni a ninguna sincronización
  · abrir un resultado vuelve a comprobar el permiso y deja asiento si se intenta lo que no se puede leer
  · cada rol ve lo suyo: administración todo, reportes sólo el catálogo, técnico no busca (sólo mantiene el índice), alumno no busca
"""
from __future__ import annotations

import json

from django.test import override_settings

from audit.models import Bitacora
from evaluacion import models as m10

from .. import models as m
from .base import SEARCH, BaseSearch

SECRETO = "Examen confidencial del Noveno B"


class TST073Tests(BaseSearch):
    """El docente A (8A) y el docente B (9B)."""

    def setUp(self):
        super().setUp()
        self.b_id, self.b = self.otro_docente()
        self.de_a = self.evaluacion("Fracciones del Octavo")
        self.de_b = self.evaluacion(SECRETO, grupo_id=self.otro_grupo["id"], actor=self.b_id)
        self.sincronizar()

    def test_cero_resultados_fuera_de_su_alcance(self):
        r = self.buscar("confidencial")
        self.assertEqual((r["total"], r["results"]), (0, []))
        self.assertEqual(self.buscar("noveno")["total"], 0)
        self.assertEqual(self.buscar("fracciones")["total"], 1)

    def test_la_respuesta_no_menciona_nada_de_lo_ajeno(self):
        """Ni título, ni fragmento, ni grupo, ni identificador: el JSON entero no contiene rastro de la evaluación ajena."""
        for q in ("confidencial", "examen confidencial noveno", "noveno", "materia", "fracciones"):
            respuesta = self.buscar(q)
            respuesta.pop("query"), respuesta.pop("normalized")                      # lo que escribió quien busca se le devuelve tal cual: no es un dato ajeno
            cuerpo = json.dumps(respuesta, ensure_ascii=False)
            for rastro in (SECRETO, "Noveno B", self.de_b["id"], self.otro_grupo["id"], "confidencial"):
                self.assertNotIn(rastro, cuerpo, (q, rastro))

    def test_el_filtro_de_grupo_no_deja_mirar_un_grupo_ajeno(self):
        r = self.buscar("confidencial", group=self.otro_grupo["id"])
        self.assertEqual(r["total"], 0)
        self.assertEqual(self.buscar("materia", group=self.otro_grupo["id"])["total"], 0)
        self.assertEqual(self.buscar("materia", period="2026")["total"], 1)         # el ciclo no abre lo ajeno: sólo reparte lo propio

    def test_el_dueno_si_lo_encuentra(self):
        r = self.buscar("confidencial", cliente=self.b)
        self.assertEqual(self.ids(r), [self.de_b["id"]])
        self.assertEqual(self.buscar("fracciones", cliente=self.b)["total"], 0)

    def test_la_administracion_ve_todo_y_reportes_ninguna_evaluacion(self):
        self.assertEqual(sorted(self.ids(self.buscar("materia", cliente=self.admin))), sorted([self.de_a["id"], self.de_b["id"]]))
        self.assertEqual(self.buscar("materia", cliente=self.reportes(), type="assessment")["total"], 0)

    def test_los_tres_tipos_respetan_el_grupo(self):
        self.estudio("l1-three-states", titulo="Tarea secreta del noveno", grupo_id=self.otro_grupo["id"], actor=self.b_id)
        self.clase(profesor=self.b_id, grupo_id=self.otro_grupo["id"])
        self.sincronizar()
        for tipo in ("study", "class", "assessment"):
            self.assertEqual(self.buscar("secreta", type=tipo)["total"], 0, tipo)
        self.assertEqual(self.buscar("estados", type="class")["total"], 0)
        self.assertEqual(self.buscar("estados", type="class", cliente=self.b)["total"], 1)
        self.assertEqual(self.buscar("secreta", type="study", cliente=self.b)["total"], 1)


class RevocacionConIndiceRezagadoTests(BaseSearch):
    """El índice NO se pone al día antes de consultar: lo que se prueba es que los permisos no se toman del índice."""

    sincronizar_al_consultar = False

    def setUp(self):
        super().setUp()
        self.evaluacion_a = self.evaluacion("Fracciones del Octavo")
        self.reconstruir()                                              # el índice conoce la evaluación

    def test_sin_sincronizar_se_encuentra_lo_ya_indexado_y_se_avisa_del_rezago(self):
        r = self.buscar("fracciones")
        self.assertEqual(self.ids(r), [self.evaluacion_a["id"]])
        self.evaluacion("Fracciones nuevas")                            # nace un evento que nadie aplicó: el índice va atrás
        r = self.buscar("fracciones")
        self.assertEqual(r["index_status"], "rezagado")
        self.assertIn("podrían no incluir", r["index_notice"])
        self.assertEqual(r["total"], 1)                                 # aún no conoce la nueva, pero se puede consultar
        self.sincronizar()
        r = self.buscar("fracciones")
        self.assertEqual((r["index_status"], r["total"]), ("consultable", 2))

    def test_quitar_al_docente_del_grupo_oculta_lo_suyo_en_la_siguiente_consulta(self):
        self.assertEqual(self.buscar("fracciones")["total"], 1)
        r = self.admin.delete(f"/api/acceso/grupos/{self.grupo['id']}/miembros/{self.docente_id}/")
        self.assertIn(r.status_code, (200, 204), r.content)
        r = self.buscar("fracciones")
        self.assertEqual((r["total"], r["results"]), (0, []))
        self.assertTrue(m.Documento.objects.filter(entidad_id=self.evaluacion_a["id"]).exists())    # el índice sigue igual: no hizo falta tocarlo
        self.assertEqual(self.buscar("fracciones", cliente=self.admin)["total"], 1)                   # a quien sí puede leerlo, no se le oculta

    def test_desactivar_el_grupo_oculta_sus_evaluaciones(self):
        r = self.admin.patch(f"/api/acceso/grupos/{self.grupo['id']}/", {"activo": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.buscar("fracciones")["total"], 0)
        self.assertEqual(self.buscar("fracciones", cliente=self.admin)["total"], 0)                   # ni siquiera la administración: el grupo ya no existe para el aula
        self.assertTrue(m10.Asignacion.objects.filter(pk=self.evaluacion_a["id"]).exists())           # el dueño no perdió nada

    def test_un_docente_que_entra_a_un_grupo_lo_ve_al_instante(self):
        b_id, b = self.otro_docente()
        self.assertEqual(self.buscar("fracciones", cliente=b)["total"], 0)
        self.admin.post(f"/api/acceso/grupos/{self.grupo['id']}/miembros/", {"usuario_id": b_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(self.buscar("fracciones", cliente=b)["total"], 1)

    def test_una_evaluacion_retirada_desaparece_aunque_el_indice_no_lo_sepa_y_se_purga(self):
        m10.Asignacion.objects.filter(pk=self.evaluacion_a["id"]).update(estado="archivada", cerrada_en=self.t, archivada_en=self.t)
        r = self.buscar("fracciones")
        self.assertEqual((r["total"], r["results"]), (0, []))
        self.assertFalse(m.Documento.objects.filter(entidad_id=self.evaluacion_a["id"]).exists())    # la búsqueda limpió lo que descubrió obsoleto
        self.assertIn("busqueda.entradas_purgadas.v1", self.eventos_search())

    def test_una_evaluacion_borrada_del_dueno_desaparece_y_se_purga(self):
        m10.Asignacion.objects.filter(pk=self.evaluacion_a["id"]).delete()
        self.assertEqual(self.buscar("fracciones")["total"], 0)
        self.assertEqual(m.Documento.objects.count(), 0)

    def test_el_titulo_que_se_muestra_es_el_vigente_no_el_indexado(self):
        m10.Asignacion.objects.filter(pk=self.evaluacion_a["id"]).update(titulo="Fracciones corregidas")
        self.assertEqual(self.titulos(self.buscar("fracciones")), ["Fracciones corregidas"])


class AbrirTests(BaseSearch):
    def setUp(self):
        super().setUp()
        self.b_id, self.b = self.otro_docente()
        self.mia = self.evaluacion("Fracciones del Octavo")
        self.ajena = self.evaluacion("Examen ajeno", grupo_id=self.otro_grupo["id"], actor=self.b_id)
        self.sincronizar()

    def abrir(self, cuerpo: dict, cliente=None, esperado: int = 200) -> dict:
        r = (cliente or self.docente).post(f"{SEARCH}/open/", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def test_abrir_lo_propio_devuelve_el_destino_de_navegacion(self):
        r = self.abrir({"entity_type": "assessment", "entity_id": self.mia["id"]})
        self.assertTrue(r["allowed"] and r["verified"])
        self.assertEqual(r["navigation_target"]["entity_id"], self.mia["id"])
        self.assertEqual(r["navigation_target"]["object_ref"], "l3-exam")

    def test_abrir_lo_ajeno_es_404_igual_que_lo_inexistente_y_deja_asiento(self):
        ajeno = self.abrir({"entity_type": "assessment", "entity_id": self.ajena["id"]}, esperado=404)
        inexistente = self.abrir({"entity_type": "assessment", "entity_id": "no-existe"}, esperado=404)
        self.assertEqual(ajeno, inexistente)                                          # no se revela qué hay
        self.assertEqual(ajeno["codigo"], "no_disponible")
        asientos = Bitacora.objects.filter(accion="busqueda.apertura_denegada")
        self.assertEqual(asientos.count(), 1)
        self.assertEqual((asientos.first().resultado, asientos.first().objeto_id), ("denegado", self.ajena["id"]))

    def test_abrir_vuelve_a_comprobar_aunque_el_resultado_ya_se_haya_mostrado(self):
        self.assertEqual(self.buscar("fracciones")["total"], 1)                     # se vio en la lista…
        self.admin.delete(f"/api/acceso/grupos/{self.grupo['id']}/miembros/{self.docente_id}/")
        self.abrir({"entity_type": "assessment", "entity_id": self.mia["id"]}, esperado=404)          # …pero al tocarlo ya no es suyo

    def test_abrir_un_grupo_desactivado_o_una_entidad_archivada(self):
        m10.Asignacion.objects.filter(pk=self.mia["id"]).update(estado="archivada", cerrada_en=self.t, archivada_en=self.t)
        self.abrir({"entity_type": "assessment", "entity_id": self.mia["id"]}, esperado=404)

    def test_datos_invalidos(self):
        self.assertEqual(self.abrir({"entity_type": "alumno", "entity_id": "x"}, esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.abrir({"entity_type": "assessment"}, esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.abrir({"entity_type": "lesson", "entity_id": "l1"}, esperado=400)["codigo"], "datos_invalidos")        # falta el curso

    def test_la_administracion_abre_lo_de_cualquier_grupo(self):
        self.abrir({"entity_type": "assessment", "entity_id": self.ajena["id"]}, cliente=self.admin)


class RolesTests(BaseSearch):
    def setUp(self):
        super().setUp()
        self.mia = self.evaluacion("Fracciones del Octavo")
        self.catalogo.curso("avacom.co.primary.4.math.fractions", "Fracciones", "Curso de fracciones", country="CO", level="primary")
        self.sincronizar()

    def test_el_alumno_no_busca(self):
        alumno = self.alumno_con_sesion()
        for ruta in ("/", "/filters/", "/status/"):
            r = alumno.get(f"{SEARCH}{ruta}", {"q": "fracciones"})
            self.assertEqual(r.status_code, 403, (ruta, r.content))
            self.assertEqual(r.json()["codigo"], "sin_permiso")
        self.assertEqual(alumno.post(f"{SEARCH}/open/", {"entity_type": "course", "entity_id": "x", "course_ref": "x"}, format="json").status_code, 403)

    def test_el_tecnico_no_busca_pero_mantiene_el_indice(self):
        tecnico = self.tecnico()
        self.assertEqual(tecnico.get(f"{SEARCH}/", {"q": "fracciones"}).status_code, 403)
        self.assertEqual(tecnico.get(f"{SEARCH}/filters/").status_code, 403)
        r = tecnico.get(f"{SEARCH}/status/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("detail", r.json())
        self.assertEqual(tecnico.post(f"{SEARCH}/reindex/", {}, format="json").status_code, 200)

    def test_reportes_busca_solo_en_el_catalogo(self):
        reportes = self.reportes()
        r = self.buscar("fracciones", cliente=reportes)
        self.assertEqual([x["entity_type"] for x in r["results"]], ["course"])
        self.assertEqual(self.buscar("fracciones", cliente=reportes, type="assessment")["total"], 0)
        self.assertEqual([t["value"] for t in reportes.get(f"{SEARCH}/filters/").json()["types"]], ["course", "lesson", "resource"])

    def test_el_profesor_no_puede_reconstruir_ni_sincronizar_ni_tocar_sinonimos(self):
        for metodo, ruta in (("post", "/reindex/"), ("post", "/sync/")):
            self.assertEqual(getattr(self.docente, metodo)(f"{SEARCH}{ruta}", {}, format="json").status_code, 403, ruta)
        self.assertEqual(self.docente.get(f"{SEARCH}/synonyms/").status_code, 403)

    def test_el_detalle_del_estado_solo_lo_ve_quien_mantiene_el_indice(self):
        self.assertNotIn("detail", self.estado(self.docente))
        detalle = self.estado(self.admin)["detail"]
        self.assertEqual(detalle["documents"]["assessment"], 1)
        self.assertEqual(set(detalle["sources"]), {"evaluacion", "estudio", "aula"})

    def test_sin_sesion_y_sin_actor_declarado_no_se_ve_nada_de_ningun_grupo(self):
        """Q-34 (prototipo): sin sesión se puede buscar, pero a quien no dice quién es no se le enseña lo de ningún grupo; el catálogo sí."""
        anonimo = self.api.get(f"{SEARCH}/", {"q": "fracciones"})
        self.assertEqual(anonimo.status_code, 200, anonimo.content)
        self.assertEqual([x["entity_type"] for x in anonimo.json()["results"]], ["course"])
        declarado = self.api.get(f"{SEARCH}/", {"q": "fracciones", "actor": self.docente_id}).json()
        self.assertEqual(sorted(x["entity_type"] for x in declarado["results"]), ["assessment", "course"])

    @override_settings(AVACOM_LMS_EXIGIR_SESION=True)
    def test_con_la_sesion_obligatoria_nadie_busca_sin_sesion(self):
        r = self.api.get(f"{SEARCH}/", {"q": "fracciones"})
        self.assertIn(r.status_code, (401, 403))


class OpcionesDeFiltrosTests(BaseSearch):
    def test_solo_los_grupos_y_tipos_de_quien_consulta(self):
        b_id, b = self.otro_docente()
        mio = self.docente.get(f"{SEARCH}/filters/").json()
        self.assertEqual([g["name"] for g in mio["groups"]], ["Octavo A"])
        self.assertEqual(mio["periods"], ["2026"])
        self.assertEqual(mio["current_period"], "2026")
        self.assertEqual([t["value"] for t in mio["types"]], ["course", "lesson", "resource", "assessment", "study", "class"])
        otro = b.get(f"{SEARCH}/filters/").json()
        self.assertEqual([g["name"] for g in otro["groups"]], ["Noveno B"])
        admin = self.admin.get(f"{SEARCH}/filters/").json()
        self.assertEqual([g["name"] for g in admin["groups"]], ["Noveno B", "Octavo A"])
        self.assertNotIn(self.otro_grupo["id"], json.dumps(mio))
