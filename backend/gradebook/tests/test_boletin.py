"""
El boletín de un estudiante (vista del profesor) y el resumen del libro que alimenta las listas: lo que lleva un estudiante en un grupo, por curso, con sus insights y una
página de evaluaciones. Con cientos de evaluaciones al año la tabla alumnos × evaluaciones no se puede leer: se lista a los estudiantes y cada uno abre su página.
"""
from __future__ import annotations

from .base import GB, BaseGradebook
from .test_alumno import _ConPreescolar


class _ConDosExamenes(BaseGradebook):
    """Juan (8A, secundaria, sistema de Colombia 1,0–5,0) con un examen calificado y otro en revisión docente; Ana, en el mismo grupo, sin haber hecho nada."""

    plantilla = "co-1-5"

    def setUp(self):
        super().setUp()
        self.avanzar(seg=10)
        self.a1, self.i1, _, _ = self.examen_entregado(abiertas=False)
        self.avanzar(seg=60)
        self.a2, self.i2, _, _ = self.examen_entregado(abiertas=True, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        self.ana_id, _ = self.alumno_con_tableta("Ana", "300501")

    def boletin(self, alumno_id: str, **params) -> dict:
        return self.leer(f"/estudiantes/{alumno_id}/boletin/", grupo_id=params.pop("grupo_id", self.grupo["id"]), **params)


class BoletinTests(_ConDosExamenes):
    def test_trae_lo_que_lleva_el_estudiante_en_total_y_por_curso_con_el_sistema_del_nivel(self):
        b = self.boletin(self.estudiante_id)
        self.assertEqual((b["alumno"]["rotulo"], b["grupo"]["nivel_clave"], b["modo"], b["sistema"]["codigo"]), ("Juan P.", "secundaria", "calificaciones", "co-1-5"))
        r, c = b["resumen"], b["resumen"]["conteo"]
        self.assertEqual((r["evaluaciones"], c["con_nota"], c["sin_publicar"], c["publicadas"], c["por_revisar"], c["pendientes"], c["sin_registro"]), (2, 1, 1, 0, 1, 0, 0))
        self.assertEqual((r["oficial"], r["ponderado"]), (False, False))                         # el promedio es simple e informativo
        self.assertIsNotNone(r["promedio_simple"])
        self.assertEqual(r["presentado"]["etiqueta"], "3.8")                                       # 71,43 de 100 en la escala colombiana
        self.assertTrue(r["presentado"]["cumple_criterio"])
        curso = b["cursos"][0]
        self.assertEqual((len(b["cursos"]), curso["evaluaciones"], curso["conteo"]["con_nota"], curso["presentado"]["desempeno"]), (1, 2, 1, "Básico"))

    def test_lo_pendiente_no_es_un_cero_ni_tiene_promedio(self):
        b = self.boletin(self.ana_id)
        r = b["resumen"]
        self.assertEqual((r["evaluaciones"], r["conteo"]["con_nota"], r["conteo"]["pendientes"], r["promedio_simple"], r["presentado"]), (2, 0, 2, None, None))
        self.assertTrue(all(i["puntaje_efectivo"] is None and i["presentacion"] is None and i["estado"] == "pendiente" for i in b["evaluaciones"]["items"]))
        self.assertEqual(b["insights"]["tendencia"]["direccion"], "insuficiente")

    def test_las_evaluaciones_vienen_por_paginas_de_la_mas_reciente_a_la_mas_antigua(self):
        todas = self.boletin(self.estudiante_id)["evaluaciones"]
        self.assertEqual((todas["total"], [i["asignacion_id"] for i in todas["items"]]), (2, [self.a2["id"], self.a1["id"]]))
        primera = self.boletin(self.estudiante_id, limite=1)["evaluaciones"]
        segunda = self.boletin(self.estudiante_id, limite=1, desde=1)["evaluaciones"]
        self.assertEqual(([i["asignacion_id"] for i in primera["items"]], [i["asignacion_id"] for i in segunda["items"]]), ([self.a2["id"]], [self.a1["id"]]))
        self.assertEqual((primera["total"], segunda["total"], segunda["desde"], segunda["limite"]), (2, 2, 1, 1))
        self.assertEqual(self.boletin(self.estudiante_id, desde=5)["evaluaciones"]["items"], [])                  # más allá del final: vacío, no un error

    def test_se_puede_pedir_solo_un_curso(self):
        b = self.boletin(self.estudiante_id)
        curso_ref = b["cursos"][0]["curso_ref"]
        self.assertEqual(self.boletin(self.estudiante_id, curso_ref=curso_ref)["evaluaciones"]["total"], 2)
        sin = self.boletin(self.estudiante_id, curso_ref="curso-que-no-existe")["evaluaciones"]
        self.assertEqual((sin["total"], sin["items"]), (0, []))

    def test_cada_evaluacion_dice_su_estado_y_la_nota_presentada_provisional(self):
        items = {i["asignacion_id"]: i for i in self.boletin(self.estudiante_id)["evaluaciones"]["items"]}
        calificada, en_revision = items[self.a1["id"]], items[self.a2["id"]]
        self.assertEqual((calificada["estado"], calificada["estado_simple"], calificada["publicada"]), ("revisado", "completado", False))
        self.assertTrue(calificada["presentacion"]["provisional"])
        self.assertEqual(calificada["presentacion"]["presentada"]["etiqueta"], "3.8")
        self.assertIsNotNone(calificada["calificacion_id"])
        self.assertEqual((en_revision["estado"], en_revision["calificacion_id"], en_revision["presentacion"]), ("provisional", None, None))     # lo parcial no es una nota

    def test_publicar_la_pasa_a_definitiva_y_cambia_el_conteo(self):
        cal = self.calificacion(self.i1)
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        c = self.boletin(self.estudiante_id)["resumen"]["conteo"]
        self.assertEqual((c["publicadas"], c["sin_publicar"]), (1, 0))

    def test_pide_grupo_y_valida_la_paginacion(self):
        self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", esperado=400)
        for malo in ({"limite": 0}, {"limite": 101}, {"limite": "x"}, {"desde": -1}):
            self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", esperado=400, grupo_id=self.grupo["id"], **malo)

    def test_un_estudiante_que_no_es_del_grupo_o_un_grupo_que_no_existe_dan_404(self):
        self.leer(f"/estudiantes/{self.otro_alumno_id()}/boletin/", esperado=404, grupo_id=self.grupo["id"])
        self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", esperado=404, cliente=self.admin, grupo_id="no-existe")

    def otro_alumno_id(self) -> str:
        _, cliente, otro = self.otro_docente()
        return self.alumno_con_tableta("Mario", "300777", grupo_id=otro["id"])[0]


class BoletinPermisosTests(_ConDosExamenes):
    def test_un_profesor_ajeno_no_lo_ve_y_un_alumno_tampoco(self):
        _, ruiz, _ = self.otro_docente()
        self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", esperado=403, cliente=ruiz, grupo_id=self.grupo["id"])
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.get(f"{GB}/estudiantes/{self.estudiante_id}/boletin/", {"grupo_id": self.grupo["id"]}).status_code, 403)

    def test_el_profesor_del_grupo_y_la_administracion_si(self):
        self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", cliente=self.docente, grupo_id=self.grupo["id"])
        self.leer(f"/estudiantes/{self.estudiante_id}/boletin/", cliente=self.admin, grupo_id=self.grupo["id"])


class InsightsTests(_ConDosExamenes):
    def test_con_pocas_notas_no_se_dice_hacia_donde_va(self):
        t = self.boletin(self.estudiante_id)["insights"]["tendencia"]
        self.assertEqual((t["direccion"], t["calificaciones"], t["minimo"]), ("insuficiente", 1, 4))

    def test_la_tendencia_baja_cuando_lo_reciente_va_peor_que_lo_anterior(self):
        for bien in (True, False, False):
            self.avanzar(seg=60)
            self.examen_entregado(bien=bien, abiertas=False, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        t = self.boletin(self.estudiante_id)["insights"]["tendencia"]
        self.assertEqual((t["direccion"], t["calificaciones"], t["comparadas"]), ("baja", 4, 2))
        self.assertGreater(t["de"], t["a"])
        self.assertLessEqual(t["diferencia"], -5)

    def test_la_constancia_cuenta_lo_completado_contra_lo_asignado(self):
        self.assertEqual(self.boletin(self.estudiante_id)["insights"]["constancia"], {"completadas": 2, "evaluaciones": 2})
        self.assertEqual(self.boletin(self.ana_id)["insights"]["constancia"], {"completadas": 0, "evaluaciones": 2})

    def test_lo_que_el_profesor_escribio_sale_con_su_evaluacion(self):
        cal = self.calificacion(self.i1)
        self.gb(f"/calificaciones/{cal['id']}/retroalimentacion/", {"fortalezas": "Razona bien los cambios de estado.", "dificultades": "Se confunde al ordenar procesos.",
                                                                    "version_esperada": cal["version"]})
        c = self.boletin(self.estudiante_id)["insights"]["comentarios"]
        self.assertEqual((c["fortalezas"][0]["texto"], c["fortalezas"][0]["titulo"]), ("Razona bien los cambios de estado.", self.a1["titulo"]))
        self.assertEqual((c["dificultades"][0]["texto"], c["oportunidades"]), ("Se confunde al ordenar procesos.", []))

    def test_los_insights_se_dicen_informativos(self):
        self.assertTrue(self.boletin(self.estudiante_id)["insights"]["informativo"])


class ResumenDelLibroTests(_ConDosExamenes):
    def test_el_libro_en_resumen_no_manda_las_celdas_pero_si_lo_que_lleva_cada_estudiante(self):
        completo = self.libro()
        resumen = self.libro(vista="resumen")
        self.assertTrue(all(f["celdas"] for f in completo["alumnos"]))
        self.assertTrue(all(f["celdas"] == {} for f in resumen["alumnos"]))
        juan = next(f for f in resumen["alumnos"] if f["rotulo"] == "Juan P.")["resumen"]
        c = juan["conteo"]
        self.assertEqual((juan["evaluaciones"], c["completadas"], c["con_nota"], c["sin_publicar"], c["por_revisar"], c["pendientes"]), (2, 2, 1, 1, 1, 0))
        self.assertEqual((c["aprobadas"], c["no_aprobadas"]), (1, 0))
        self.assertEqual((juan["promedio_simple"], juan["presentado"]["etiqueta"], juan["presentado"]["desempeno"]), (71.43, "3.8", "Básico"))       # visto con el sistema del nivel
        ana = next(f for f in resumen["alumnos"] if f["rotulo"] == "Ana")["resumen"]
        self.assertEqual((ana["conteo"]["pendientes"], ana["conteo"]["con_nota"], ana["promedio_simple"], ana["presentado"]), (2, 0, None, None))

    def test_el_resumen_de_cada_evaluacion_cuenta_lo_que_hay_que_hacer(self):
        por_id = {a["id"]: a["conteo"] for a in self.libro(vista="resumen")["asignaciones"]}
        self.assertEqual((por_id[self.a1["id"]]["con_nota"], por_id[self.a1["id"]]["sin_publicar"], por_id[self.a1["id"]]["pendientes"]), (1, 1, 1))     # Juan, y Ana pendiente
        self.assertEqual((por_id[self.a2["id"]]["por_revisar"], por_id[self.a2["id"]]["con_nota"]), (1, 0))

    def test_el_libro_completo_sigue_igual_para_quien_lo_use(self):
        self.assertEqual(self.libro()["alumnos"][0]["celdas"].keys(), self.libro(vista="completo")["alumnos"][0]["celdas"].keys())


class BoletinEnModoSimpleTests(_ConPreescolar):
    def test_sin_sistema_no_hay_cifras_ni_comentarios_solo_lo_completado(self):
        a, i, _, _ = self.examen_de_ana()
        self.sincronizar()
        b = self.leer(f"/estudiantes/{self.ana_id}/boletin/", grupo_id=self.grupo_pre["id"])
        self.assertEqual((b["modo"], b["sistema"]), ("simple", None))
        self.assertEqual((b["resumen"]["promedio_simple"], b["resumen"]["presentado"], b["resumen"]["conteo"]["completadas"]), (None, None, 1))
        c = b["resumen"]["conteo"]
        self.assertEqual((c["sin_registro"], c["con_nota"], c["sin_publicar"], c["por_revisar"]), (0, 0, 0, 0))                    # en modo simple no hay notas que registrar ni publicar
        self.assertEqual(b["cursos"][0]["conteo"]["sin_registro"], 0)
        item = b["evaluaciones"]["items"][0]
        self.assertEqual((item["asignacion_id"], item["estado_simple"], item["puntaje_efectivo"], item["presentacion"]), (a["id"], "completado", None, None))
        self.assertEqual((b["insights"]["tendencia"]["direccion"], b["insights"]["comentarios"]), ("insuficiente", {"fortalezas": [], "dificultades": [], "oportunidades": []}))

    def test_el_libro_en_resumen_de_un_nivel_simple_no_pide_registrar_nada(self):
        self.examen_de_ana()
        self.sincronizar()
        libro = self.leer("/libro/", grupo_id=self.grupo_pre["id"], vista="resumen")
        ana = next(f for f in libro["alumnos"] if f["alumno_id"] == self.ana_id)["resumen"]
        self.assertEqual((ana["conteo"]["completadas"], ana["conteo"]["sin_registro"], ana["conteo"]["con_nota"], ana["presentado"]), (1, 0, 0, None))
        self.assertTrue(all(a["conteo"]["sin_registro"] == 0 for a in libro["asignaciones"]))
