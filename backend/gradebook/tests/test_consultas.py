"""
Las consultas del libro del profesor: el libro del grupo (alumnos × evaluaciones, estado de revisión y de publicación), el historial de un estudiante, intentos y resultados
por asignación, el detalle de una calificación y la configuración institucional.
"""
from __future__ import annotations

from .. import models as m
from .base import BaseGradebook


class LibroTests(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a1, self.i1, _, _ = self.examen_entregado(abiertas=False)
        self.a2, self.i2, _, _ = self.examen_entregado(abiertas=True, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        self.ana_id, self.hw_ana = self.alumno_con_tableta("Ana", "300501")

    def test_el_libro_trae_columnas_filas_estados_y_la_escala_del_nivel(self):
        libro = self.libro()
        self.assertEqual((libro["modo"], libro["escala"]["codigo"], libro["politica_intentos"]), ("calificaciones", "gen-0-100", "ultimo"))
        self.assertEqual((libro["grupo"]["id"], libro["grupo"]["nivel_clave"], libro["grupo"]["periodo"]), (self.grupo["id"], "secundaria", "2026"))
        self.assertEqual({a["id"] for a in libro["asignaciones"]}, {self.a1["id"], self.a2["id"]})
        self.assertEqual({a["tipo_evaluacion"] for a in libro["asignaciones"]}, {"sumativa"})
        por_nombre = {f["rotulo"]: f for f in libro["alumnos"]}
        juan, ana = por_nombre["Juan P."], por_nombre["Ana"]
        self.assertEqual((juan["celdas"][self.a1["id"]]["estado"], juan["celdas"][self.a2["id"]]["estado"]), ("revisado", "provisional"))
        self.assertEqual((ana["celdas"][self.a1["id"]]["estado"], ana["celdas"][self.a1["id"]]["estado_simple"], ana["celdas"][self.a1["id"]]["puntaje_efectivo"]),
                         ("pendiente", "no_iniciado", None))                                        # quien no ha hecho nada no tiene un cero: tiene un pendiente
        celda = juan["celdas"][self.a1["id"]]
        self.assertTrue(celda["presentacion"]["provisional"])                                       # sin publicar: la presentación es provisional
        self.assertEqual(celda["puntaje_original"], celda["puntaje_efectivo"])
        self.assertEqual(libro["totales"], {"alumnos": 2, "asignaciones": 2, "pendientes": 3, "por_revisar": 1, "sin_publicar": 1})
        self.assertEqual({a["id"]: a["por_revisar"] for a in libro["asignaciones"]}, {self.a1["id"]: 0, self.a2["id"]: 1})

    def test_filtros_por_asignacion_buscador_y_periodo(self):
        self.assertEqual([a["id"] for a in self.libro(asignacion_id=self.a1["id"])["asignaciones"]], [self.a1["id"]])
        self.assertEqual([f["rotulo"] for f in self.libro(q="ana")["alumnos"]], ["Ana"])
        self.assertEqual([f["rotulo"] for f in self.libro(q="  JUAN ")["alumnos"]], ["Juan P."])
        self.assertEqual(self.libro(q="nadie")["alumnos"], [])
        self.assertEqual(self.libro(periodo="2099")["asignaciones"], [])
        self.assertEqual(len(self.libro(periodo="2026")["asignaciones"]), 2)
        self.assertEqual(self.libro(curso_ref="otro-curso")["asignaciones"], [])
        self.leer("/libro/", esperado=403, grupo_id="no-existe")                                    # para un profesor, un grupo ajeno y uno inexistente son lo mismo
        self.leer("/libro/", esperado=404, cliente=self.admin, grupo_id="no-existe")

    def test_lo_publicado_se_ve_definitivo_y_con_su_presentacion_estampada(self):
        cal = self.calificacion(self.i1)
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        celda = next(f for f in self.libro()["alumnos"] if f["rotulo"] == "Juan P.")["celdas"][self.a1["id"]]
        self.assertEqual((celda["estado"], celda["publicada"], celda["presentacion"]["provisional"]), ("definitivo", True, False))
        self.assertEqual(self.libro()["totales"]["sin_publicar"], 0)

    def test_si_alguien_cambia_la_puntuacion_en_mod_010_el_libro_no_la_pisa_y_avisa(self):
        cal = self.revisar_todo(self.i2)["calificacion"]
        antes = cal["puntaje_efectivo"]
        ref = self.pendientes(self.i2)[0]
        self.accion(f"/intentos/{self.i2}/respuestas/{ref}/puntuar/", {"puntaje": 0, "motivo": "Corrección directa en la evaluación"})
        self.sincronizar()
        detalle = self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]
        self.assertEqual(detalle["puntaje_efectivo"], antes)                                        # lo registrado no se pisa en silencio
        self.assertTrue(detalle["desfase_con_evaluacion"])                                          # pero el desfase se señala
        self.assertEqual(self.fila_cal(self.i2).version, 1)

    def test_el_historial_del_estudiante(self):
        cal = self.calificacion(self.i1)
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        h = self.leer(f"/estudiantes/{self.estudiante_id}/")
        self.assertEqual((h["alumno_id"], h["rotulo"], len(h["grupos"])), (self.estudiante_id, "Juan P.", 1))
        g = h["grupos"][0]
        self.assertEqual((g["modo"], [c["id"] for c in g["calificaciones"]], g["agregados"][0]["oficial"]), ("calificaciones", [cal["id"]], False))
        self.assertEqual({r["asignacion_id"] for r in g["resultados"]}, {self.a1["id"], self.a2["id"]})
        self.assertEqual(self.leer(f"/estudiantes/{self.estudiante_id}/", grupo_id=self.grupo["id"])["grupos"][0]["grupo"]["id"], self.grupo["id"])
        self.leer(f"/estudiantes/{self.ana_id}/", esperado=200)
        self.assertEqual(self.leer("/estudiantes/inexistente/", esperado=403)["codigo"], "fuera_de_alcance")

    def test_intentos_y_resultados_por_asignacion(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, intentos_permitidos=2)
        _, i1, _, _ = self.examen_entregado(abiertas=False, bien=False, asignacion=a)
        _, i2, _, _ = self.examen_entregado(abiertas=False, asignacion=a)
        r = self.leer(f"/asignaciones/{a['id']}/")
        fila = r["alumnos"][0]
        self.assertEqual((r["asignacion"]["intentos_permitidos"], r["politica_intentos"], r["clasificacion"]["tipo_evaluacion"]), (2, "ultimo", "sumativa"))
        self.assertEqual([(i["numero"], i["estado"], i["calificacion"]["estado"]) for i in fila["intentos"]], [(1, "calificado", "revisada"), (2, "calificado", "revisada")])
        self.assertEqual((fila["resultado"]["intentos_total"], fila["resultado"]["intentos_registrados"], fila["resultado"]["calificacion_aplicable_id"]), (2, 2, self.fila_cal(i2).id))
        self.leer("/asignaciones/no-existe/", esperado=404)

    def test_el_detalle_de_una_calificacion_trae_su_historial_sus_revisiones_y_su_intento(self):
        cal = self.revisar_todo(self.i2)["calificacion"]
        d = self.leer(f"/calificaciones/{cal['id']}/")
        self.assertEqual((d["intento"]["id"], d["intento"]["estado"], len(d["revisiones"]), d["historial"][0]["tipo"]), (self.i2, "calificado", 2, "registro"))
        self.assertEqual({r["tipo"] for r in d["revisiones"]}, {"manual"})
        self.leer("/calificaciones/no-existe/", esperado=404)

    def test_registrar_a_mano_un_intento_que_no_existe_o_en_curso(self):
        self.gb("/intentos/no-existe/registrar/", {}, esperado=404)
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"], hw=self.hw_ana, alumno_id=self.ana_id)["intento"]["id"]
        self.assertEqual(self.gb(f"/intentos/{i}/registrar/", {}, esperado=409)["motivo"], "sin_calificar")


class ConfiguracionTests(BaseGradebook):
    def test_la_configuracion_trae_los_cinco_niveles_la_politica_y_las_escalas(self):
        cfg = self.leer("/configuracion/")
        self.assertEqual([n["nivel_clave"] for n in cfg["niveles"]], ["preescolar", "primaria", "secundaria", "bachillerato", "preuniversitario"])
        self.assertEqual((cfg["politica"]["politica_intentos"], cfg["politica"]["politica_provisional"], cfg["politica"]["ponderaciones_aplicadas"]), ("ultimo", True, False))
        self.assertEqual([e["codigo"] for e in cfg["escalas"]], ["gen-0-100"])
        self.assertEqual(cfg["modos"], ["simple", "calificaciones"])

    def test_la_politica_institucional(self):
        r = self.gb("/politica/", {"pais": "co", "jurisdiccion": "Antioquia", "institucion": "IE San José", "politica_intentos": "mejor", "ponderaciones": {"sumativa": 70, "formativa": 30}},
                    metodo="put", cliente=self.admin)["politica"]
        self.assertEqual((r["pais"], r["politica_intentos"], r["politica_provisional"], r["ponderaciones"], r["ponderaciones_aplicadas"]),
                         ("CO", "mejor", False, {"sumativa": 70, "formativa": 30}, False))        # se guardan para V1 y NO se aplican
        for malo in ({"pais": "Colombia"}, {"politica_intentos": "al_azar"}, {"ponderaciones": [1, 2]}):
            self.gb("/politica/", malo, metodo="put", cliente=self.admin, esperado=400)
        self.gb("/politica/", {"pais": "CO"}, metodo="put", cliente=self.docente, esperado=403)
        self.assertEqual(self.eventos_gb("calificacion.politica_configurada.v1"), ["calificacion.politica_configurada.v1"])
        self.assertEqual(m.Politica.objects.get().version, 1)
