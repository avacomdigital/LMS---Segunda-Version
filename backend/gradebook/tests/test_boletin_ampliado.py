"""
Las correcciones del boletín que pidió el CTO (2026-10-19): la nota se lee con los PUNTOS BRUTOS, el porcentaje y el sistema configurado; el libro y el boletín se segmentan por
MATERIA (un profesor dicta varios cursos de la misma materia) además de por curso; y el profesor deja sus RECOMENDACIONES por periodo (la cuarta pregunta del boletín) con frases
de un catálogo cerrado, cada cambio con su asiento en la bitácora (quién y cuándo).
"""
from __future__ import annotations

from django.apps import apps as registro_de_apps

from audit.models import Bitacora

from .. import models as m
from ..dominio import curso as cur
from .base import GB
from .test_boletin import _ConDosExamenes


def _asientos(accion: str):
    return list(Bitacora.objects.filter(accion=accion).order_by("secuencia"))


class PuntosBrutosTests(_ConDosExamenes):
    def test_la_calificacion_registrada_guarda_los_puntos_que_conto_mod_010(self):
        cal = self.calificacion(self.i1)
        fila = self.fila(self.i1)
        self.assertEqual((cal["puntos"], cal["puntos_maximos"]), (round(fila.puntaje, 2), round(fila.puntaje_maximo, 2)))
        self.assertEqual(cal["bruto"], {"puntos": cal["puntos"], "puntos_maximos": cal["puntos_maximos"], "aciertos": cal["aciertos"], "preguntas": cal["preguntas"],
                                        "porcentaje": cal["puntaje_efectivo"]})
        self.assertEqual(cal["materia"], "science")                                                                   # sale del propio curso_ref

    def test_el_libro_el_boletin_y_el_detalle_dicen_la_nota_en_bruto_junto_a_la_presentada(self):
        cal = self.calificacion(self.i1)
        celda = next(f for f in self.libro()["alumnos"] if f["alumno_id"] == self.estudiante_id)["celdas"][self.a1["id"]]
        self.assertEqual(celda["bruto"]["puntos"], cal["puntos"])
        self.assertEqual(celda["presentacion"]["presentada"]["etiqueta"], "3.8")
        b = self.boletin(self.estudiante_id)
        item = next(i for i in b["evaluaciones"]["items"] if i["asignacion_id"] == self.a1["id"])
        self.assertEqual((item["bruto"]["puntos"], item["bruto"]["puntos_maximos"], item["bruto"]["porcentaje"]), (cal["puntos"], cal["puntos_maximos"], cal["puntaje_efectivo"]))
        # el resumen y cada curso suman lo obtenido sobre lo posible (sólo lo que tiene nota)
        self.assertEqual((b["resumen"]["bruto"]["puntos"], b["resumen"]["bruto"]["puntos_maximos"], b["resumen"]["bruto"]["evaluaciones"]), (cal["puntos"], cal["puntos_maximos"], 1))
        self.assertEqual(b["cursos"][0]["bruto"]["porcentaje"], round(cal["puntos"] * 100 / cal["puntos_maximos"], 2))
        pendiente = next(i for i in b["evaluaciones"]["items"] if i["asignacion_id"] == self.a2["id"])
        self.assertIsNone(pendiente["bruto"])                                                                          # lo pendiente no tiene cifras

    def test_el_alumno_ve_los_puntos_y_el_porcentaje_solo_cuando_la_nota_esta_publicada(self):
        cal = self.calificacion(self.i1)
        antes = next(i for i in self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"] if i["asignacion_id"] == self.a1["id"])
        self.assertIsNone(antes["calificacion"])
        self.assertNotIn("puntos", str(antes))
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        despues = next(i for i in self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"] if i["asignacion_id"] == self.a1["id"])
        self.assertEqual(despues["calificacion"]["bruto"], cal["bruto"])
        self.assertEqual(despues["calificacion"]["presentada"]["etiqueta"], "3.8")

    def test_la_migracion_0003_completa_los_puntos_de_lo_que_ya_estaba_calificado(self):
        """Lo calificado antes de esta versión no tenía puntos: la migración los toma del intento de MOD-010 y deja en nulo lo que no los tiene."""
        cal = self.calificacion(self.i1)
        m.Calificacion.objects.filter(pk=cal["id"]).update(puntos=None, puntos_maximos=None)              # como quedó una base de la 2.8.4
        huerfana = m.Calificacion.objects.get(pk=cal["id"])
        huerfana.pk = "cal-sin-intento"; huerfana.intento_id = "intento-que-ya-no-esta"; huerfana.save()
        migracion = __import__("gradebook.migrations.0003_puntos_brutos_y_observaciones", fromlist=["puntos_de_lo_que_habia"])
        migracion.puntos_de_lo_que_habia(registro_de_apps, None)
        fila = self.fila(self.i1)
        rellena = m.Calificacion.objects.get(pk=cal["id"])
        self.assertEqual((float(rellena.puntos), float(rellena.puntos_maximos)), (round(fila.puntaje, 2), round(fila.puntaje_maximo, 2)))
        sin = m.Calificacion.objects.get(pk="cal-sin-intento")
        self.assertIsNone(sin.puntos); self.assertIsNone(sin.puntos_maximos)

    def test_un_ajuste_no_cambia_los_puntos_brutos_pero_si_el_porcentaje(self):
        cal = self.calificacion(self.i1)
        r = self.ajustar(cal, 90)
        c = r["calificacion"]
        self.assertEqual((c["puntos"], c["puntos_maximos"]), (cal["puntos"], cal["puntos_maximos"]))                    # lo que MOD-010 contó no se toca
        self.assertEqual((c["bruto"]["porcentaje"], c["puntaje_efectivo"]), (90, 90))
        self.assertTrue(c["ajustada"])

    def test_la_base_no_admite_puntos_a_medias_ni_por_encima_del_maximo(self):
        from django.db import IntegrityError, transaction
        self.calificacion(self.i1)
        fila = m.Calificacion.objects.get(intento_id=self.i1)
        for puntos, maximo in ((5, None), (None, 5), (6, 5), (-1, 5)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.Calificacion.objects.filter(pk=fila.id).update(puntos=puntos, puntos_maximos=maximo)


class MateriaTests(_ConDosExamenes):
    def test_la_materia_sale_del_identificador_del_curso(self):
        self.assertEqual(cur.arbol_de("avacom.co.lower-secondary.6.science.states-of-matter"),
                         {"country": "CO", "level": "lower-secondary", "grade": "6", "subject": "science", "topic": "states-of-matter"})
        self.assertEqual((cur.materia_de("ejemplo-1"), cur.arbol_de(""), cur.arbol_de(None)), ("", {}, {}))
        self.assertTrue(cur.cumple("avacom.co.lower-secondary.6.science.states-of-matter", {"subject": "science"}))
        self.assertTrue(cur.cumple("avacom.co.lower-secondary.6.science.states-of-matter", {"subject": "SCIENCE", "grade": "6"}))
        self.assertFalse(cur.cumple("avacom.co.lower-secondary.6.science.states-of-matter", {"subject": "math"}))
        self.assertFalse(cur.cumple("ejemplo-1", {"subject": "science"}))                                            # sin forma conocida no se adivina
        self.assertTrue(cur.cumple("ejemplo-1", {}))
        self.assertEqual((cur.rotulo_de_materia("social-studies"), cur.rotulo_de_materia("")), ("Social studies", "Sin materia"))

    def test_el_libro_ofrece_las_materias_del_grupo_y_se_filtra_por_una(self):
        libro = self.libro()
        materia, = libro["materias"]
        self.assertEqual((materia["codigo"], materia["evaluaciones"], len(materia["cursos"])), ("science", 2, 1))
        self.assertEqual(libro["filtro"], {"materia": None, "curso_ref": None, "asignacion_id": None})
        self.assertEqual([a["materia"] for a in libro["asignaciones"]], ["science", "science"])
        con = self.libro(subject="science")
        self.assertEqual((len(con["asignaciones"]), con["filtro"]["materia"]), (2, {"subject": "science"}))
        sin = self.libro(materia="math")
        self.assertEqual((sin["asignaciones"], sin["totales"]["asignaciones"]), ([], 0))
        self.assertEqual(len(sin["materias"]), 1)                                                                    # las fichas siguen ofreciendo todo el grupo
        self.leer("/libro/", esperado=400, grupo_id=self.grupo["id"], subject="no vale!")

    def test_el_boletin_se_filtra_por_materia_y_dice_las_materias_del_grupo(self):
        b = self.boletin(self.estudiante_id, subject="science")
        self.assertEqual((b["resumen"]["evaluaciones"], b["filtro"]["materia"]), (2, {"subject": "science"}))
        vacio = self.boletin(self.estudiante_id, subject="math")
        self.assertEqual((vacio["resumen"]["evaluaciones"], vacio["cursos"], vacio["evaluaciones"]["total"]), (0, [], 0))
        self.assertEqual([x["codigo"] for x in vacio["materias"]], ["science"])


class ObservacionesTests(_ConDosExamenes):
    def observar(self, cuerpo: dict, esperado: int = 200, cliente=None, alumno_id: str | None = None) -> dict:
        return self.gb(f"/estudiantes/{alumno_id or self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], **cuerpo}, esperado=esperado, cliente=cliente, metodo="put")

    def test_el_profesor_recomienda_con_frases_del_catalogo_y_queda_en_el_boletin(self):
        r = self.observar({"recomendaciones": ["practicar_ejercicios", "pedir_ayuda"], "texto": "Va mejorando."})
        o = r["observacion"]
        self.assertTrue(r["cambiado"])
        self.assertEqual(([x["codigo"] for x in o["recomendaciones"]], o["texto"], o["version"], o["curso_ref"], o["periodo"]),
                         (["practicar_ejercicios", "pedir_ayuda"], "Va mejorando.", 1, "", "2026"))
        self.assertEqual(o["recomendaciones"][0]["texto"], "Practicar más ejercicios del tema con el modo estudio")
        self.assertEqual(o["actualizada_por"], self.docente_id)
        b = self.boletin(self.estudiante_id)
        self.assertEqual([x["id"] for x in b["observaciones"]], [o["id"]])
        self.assertEqual({x["codigo"] for x in b["recomendaciones_disponibles"]} >= {"practicar_ejercicios", "pedir_ayuda"}, True)

    def test_cada_cambio_deja_su_asiento_con_quien_y_cuando_y_repetir_no_deja_nada(self):
        self.observar({"recomendaciones": ["pedir_ayuda"]})
        igual = self.observar({"recomendaciones": ["pedir_ayuda"]})
        self.assertFalse(igual["cambiado"])
        cambio = self.observar({"recomendaciones": ["pedir_ayuda", "entregar_a_tiempo"], "version_esperada": 1})
        self.assertEqual((cambio["cambiado"], cambio["observacion"]["version"]), (True, 2))
        asientos = _asientos("calificacion.observacion_registrada")
        self.assertEqual(len(asientos), 2)
        self.assertEqual((asientos[0].valor_anterior, asientos[0].valor_nuevo["recomendaciones"]), (None, ["pedir_ayuda"]))
        self.assertEqual((asientos[1].valor_anterior["recomendaciones"], asientos[1].valor_nuevo["recomendaciones"], asientos[1].valor_nuevo["version"]),
                         (["pedir_ayuda"], ["pedir_ayuda", "entregar_a_tiempo"], 2))
        self.assertTrue(all(a.usuario_id == self.docente_id and a.ocurrido_en for a in asientos))
        self.assertEqual(self.eventos_gb("calificacion.observacion_registrada.v1"), ["calificacion.observacion_registrada.v1"] * 2)

    def test_una_version_vieja_no_pisa_el_cambio_de_otro(self):
        self.observar({"recomendaciones": ["pedir_ayuda"]})
        self.observar({"recomendaciones": ["entregar_a_tiempo"], "version_esperada": 1})
        r = self.observar({"recomendaciones": ["mantener_el_ritmo"], "version_esperada": 1}, esperado=409)
        self.assertEqual((r["codigo"], r["version_actual"]), ("conflicto_de_version", 2))

    def test_lo_que_no_vale(self):
        self.assertEqual(self.observar({"recomendaciones": ["inventada"]}, esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.observar({"recomendaciones": "pedir_ayuda"}, esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.observar({"recomendaciones": list(cur.PARTES) + ["a", "b"]}, esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.observar({"recomendaciones": [], "curso_ref": "curso-que-no-existe"}, esperado=400)["codigo"], "datos_invalidos")
        self.gb(f"/estudiantes/{self.estudiante_id}/observacion/", {"recomendaciones": []}, esperado=400, metodo="put")                 # sin grupo

    def test_solo_el_profesor_del_grupo_observa_y_un_alumno_no(self):
        _, ruiz, _ = self.otro_docente()
        self.observar({"recomendaciones": ["pedir_ayuda"]}, esperado=403, cliente=ruiz)
        self.observar({"recomendaciones": ["pedir_ayuda"]}, esperado=403, cliente=self.admin)                       # la administración no califica directamente
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.put(f"{GB}/estudiantes/{self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], "recomendaciones": []}, format="json").status_code, 403)

    def test_una_observacion_por_curso_convive_con_la_general(self):
        general = self.observar({"recomendaciones": ["mantener_el_ritmo"]})["observacion"]
        curso = self.observar({"recomendaciones": ["repasar_conceptos"], "curso_ref": self.a1["curso_ref"]})["observacion"]
        self.assertNotEqual(general["id"], curso["id"])
        b = self.boletin(self.estudiante_id)
        self.assertEqual(sorted(o["curso_ref"] for o in b["observaciones"]), sorted(["", self.a1["curso_ref"]]))
