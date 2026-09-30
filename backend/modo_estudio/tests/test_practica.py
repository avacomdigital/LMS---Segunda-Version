"""
La práctica autocalificable, separada de la evaluación formal (FUN-083, FUN-088, BR-055, D-5, D-6, NFR-012): abrir o reanudar, responder con
retroalimentación inmediata (UNA llamada a la biblioteca por envío), sin tope de intentos, terminar con un resultado amable, y sin biblioteca
guardar SIN calificar para calificar después. Nunca toca `m07_intento` ni `m10_intento`.
"""
from __future__ import annotations

import json
import time

from django.conf import settings

from classroom_engine import models as m7
from classroom_engine.dominio import curso as curso_aula
from expediente.models import Intento as IntentoExpediente
from tools.host_contenido_v2_pruebas import HostContenidoV2Pruebas

from .. import models as m
from .base import BASE, CORRECTAS, CURSO, INCORRECTA_Q2, LECCION_2, BaseEstudio


class BasePractica(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()

    def abrir(self, asignacion_id: str | None = None, esperado: int = 200, **extra) -> dict:
        return self.json_ok(self.enviar("post", f"/lecciones/{asignacion_id or self.a['id']}/practica/", extra), esperado)

    def responder(self, practica_id: str, respuestas: list, **extra):
        return self.enviar("post", f"/practicas/{practica_id}/respuestas/", {"respuestas": respuestas, **extra})

    def terminar(self, practica_id: str):
        return self.enviar("post", f"/practicas/{practica_id}/terminar/")

    @staticmethod
    def r(ref: str, secuencia: int, respuesta: dict, **extra) -> dict:
        return {"pregunta_ref": ref, "secuencia": secuencia, "respuesta": respuesta, **extra}

    def correctas(self, *refs: str, desde: int = 1) -> list[dict]:
        return [self.r(ref, desde, CORRECTAS[ref]) for ref in refs]


class AbrirPracticaTests(BasePractica):
    def test_abrir_devuelve_la_practica_y_la_actividad_sin_claves(self):
        r = self.abrir()
        p = r["practica"]
        self.assertEqual((p["numero"], p["estado"], p["objeto_ref"], p["titulo"], p["total_preguntas"], p["respondidas"], p["aciertos"], p["reanudada"]),
                         (1, "en_curso", "l1-activity", "Practica: los tres estados", 6, {}, 0, False))
        self.assertGreater(p["iniciada_en"], 0)
        self.assertEqual((r["objeto"]["objeto_ref"], r["objeto"]["tipo"], len(r["objeto"]["preguntas"])), ("l1-activity", "activity", 6))
        self.assertIsNone(curso_aula.contiene_clave(r))                     # la actividad llega SIN claves: ni isCorrect, ni answer, ni feedback…
        fila = m.Practica.objects.get(pk=p["id"])
        self.assertEqual((fila.modo, fila.origen, fila.alumno_id, fila.dispositivo_id), ("estudio", "directo", self.estudiante_id, self.propia["id"]))
        tarea = m.Tarea.objects.get(asignacion_id=self.a["id"])
        self.assertEqual((tarea.estado, tarea.practica_intentos, tarea.practica_total), ("en_curso", 1, 6))

    def test_abrir_otra_vez_reanuda_la_que_esta_en_curso_y_emite_el_evento(self):
        p = self.abrir()["practica"]
        self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))
        otra = self.abrir()["practica"]
        self.assertEqual((otra["id"], otra["numero"], otra["reanudada"], sorted(otra["respondidas"])), (p["id"], 1, True, ["l1-act-q1"]))
        self.assertEqual(otra["respondidas"]["l1-act-q1"]["respuesta"], CORRECTAS["l1-act-q1"])
        self.assertEqual(m.Practica.objects.filter(tarea__asignacion_id=self.a["id"]).count(), 1)
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.actividad.reanudada.v1").carga
        self.assertEqual((carga["asignacion_id"], carga["alumno_id"], carga["practica_id"], carga["numero"], carga["respondidas"]),
                         (self.a["id"], self.estudiante_id, p["id"], 1, 1))

    def test_sin_tope_de_intentos_y_nueva_fuerza_otra(self):
        primera = self.abrir()["practica"]
        self.json_ok(self.terminar(primera["id"]))
        numeros = [self.abrir()["practica"]["numero"]]
        self.json_ok(self.terminar(m.Practica.objects.get(numero=2).id))
        numeros.append(self.abrir()["practica"]["numero"])                     # la actividad admite 2 intentos: aquí no hay tope (BR-055)
        forzada = self.abrir(nueva=True)["practica"]                            # con la tercera a medias, «nueva» la cierra y abre la cuarta
        numeros.append(forzada["numero"])
        self.assertEqual(numeros, [2, 3, 4])
        self.assertEqual(m.Practica.objects.get(numero=3).estado, "terminada")
        self.assertEqual(m.Practica.objects.filter(estado="en_curso").count(), 1)
        self.assertEqual(m.Tarea.objects.get().practica_intentos, 4)

    def test_solo_se_practican_las_actividades_de_la_leccion(self):
        r = self.enviar("post", f"/lecciones/{self.a['id']}/practica/", {"objeto_ref": "l1-lab-phet"})
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))
        r = self.enviar("post", f"/lecciones/{self.a['id']}/practica/", {"objeto_ref": "l3-exam"})
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))     # el examen es evaluación formal, nunca se practica aquí

    def test_una_asignacion_cerrada_no_admite_practica(self):
        self.api.post(f"{BASE}/docente/asignaciones/{self.a['id']}/cerrar/", {}, format="json")
        r = self.enviar("post", f"/lecciones/{self.a['id']}/practica/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))

    def test_una_asignacion_sin_practica_no_tiene_a_que_abrir(self):
        sin = self.crear_asignacion(LECCION_2)
        self.assertIsNotNone(sin["practica"])
        # el bloque «práctica» sólo existe cuando la lección tiene una actividad
        m.Asignacion.objects.filter(pk=sin["id"]).update(practica=None, bloques=[b for b in m.Asignacion.objects.get(pk=sin["id"]).bloques if b["tipo"] != "practica"])
        r = self.enviar("post", f"/lecciones/{sin['id']}/practica/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))

    def test_de_otro_grupo_no_se_practica(self):
        ajena = self.crear_asignacion(grupo_id=self.otro_grupo["id"])
        self.assertEqual(self.enviar("post", f"/lecciones/{ajena['id']}/practica/").status_code, 404)


class ResponderYCalificarTests(BasePractica):
    def test_cada_envio_se_califica_con_una_sola_llamada_a_la_biblioteca_y_en_menos_de_dos_segundos(self):
        with self.biblioteca_que_califica() as fuente:
            p = self.abrir()["practica"]
            t0 = time.perf_counter()
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2", "l1-act-q3")))
            transcurrido = time.perf_counter() - t0
            self.assertLess(transcurrido, 2.0)                                     # NFR-012
            self.assertEqual(fuente.lotes, [["l1-act-q1", "l1-act-q2", "l1-act-q3"]])       # UNA llamada por envío…
            self.assertEqual(fuente.sueltas, [])                                    # …nunca una por respuesta
        self.assertEqual((r["acuse"], r["aceptadas"], r["duplicadas"], r["superadas"], r["rechazadas"]), (True, ["l1-act-q1", "l1-act-q2", "l1-act-q3"], [], [], []))
        self.assertEqual([v["pregunta_ref"] for v in r["veredictos"]], ["l1-act-q1", "l1-act-q2", "l1-act-q3"])
        self.assertTrue(all(v["correcta"] is True and v["pendiente"] is False for v in r["veredictos"]))
        self.assertEqual(set(r["veredictos"][0]), {"pregunta_ref", "correcta", "puntaje", "puntaje_maximo", "pendiente", "retroalimentacion"})
        self.assertEqual(r["practica"], {"id": p["id"], "estado": "en_curso", "numero": 1, "objeto_ref": "l1-activity", "respondidas": 3, "aciertos": 3,
                                         "total_preguntas": 6, "sin_calificar": 0, "terminada_en": None})
        self.assertIsNone(r["resultado"])
        self.assertGreater(r["servidor_en"], 0)
        fila = m.Practica.objects.get(pk=p["id"])
        self.assertEqual((fila.aciertos, fila.puntaje, fila.puntaje_maximo), (3, 4.0, 4.0))
        # lo guardado es lo que contestó el alumno y el veredicto: ninguna clave de corrección
        self.assertTrue(all(set(x) <= {"pregunta_ref", "respuesta", "secuencia", "sesion_ref", "recibida_en", "capturada_en", "origen", "veredicto"}
                            for x in fila.respuestas))
        self.assertEqual(sorted(fila.respuestas[0]["veredicto"]), ["correcta", "pendiente", "puntaje", "puntaje_maximo", "retroalimentacion"])

    def test_una_respuesta_incorrecta_trae_su_retroalimentacion_y_no_suma_aciertos(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            r = self.json_ok(self.responder(p["id"], [self.r("l1-act-q2", 1, INCORRECTA_Q2), self.r("l1-act-q1", 1, {"selectedOptionIds": ["b"]})]))
        v = {x["pregunta_ref"]: x for x in r["veredictos"]}
        self.assertEqual((v["l1-act-q2"]["correcta"], v["l1-act-q1"]["correcta"]), (False, False))
        self.assertIn("La leche toma la forma del vaso", " ".join(v["l1-act-q1"]["retroalimentacion"]))
        self.assertEqual(r["practica"]["aciertos"], 0)

    def test_la_pregunta_abierta_queda_pendiente_de_revision_y_no_se_inventa_nota(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            r = self.json_ok(self.responder(p["id"], [self.r("l1-act-q6", 1, {"text": "El perfume se evapora."})]))
        v = r["veredictos"][0]
        self.assertEqual((v["correcta"], v["puntaje"], v["pendiente"]), (None, None, True))
        self.assertEqual((r["practica"]["aciertos"], r["practica"]["sin_calificar"]), (0, 1))

    def test_inv_013_un_reenvio_no_duplica_una_secuencia_mayor_sustituye_y_una_menor_llega_tarde(self):
        with self.biblioteca_que_califica() as fuente:
            p = self.abrir()["practica"]
            paquete = self.correctas("l1-act-q1", "l1-act-q2")
            self.json_ok(self.responder(p["id"], paquete))
            r = self.json_ok(self.responder(p["id"], paquete))                      # el mismo envío otra vez: acuse positivo, nada nuevo
            self.assertEqual((r["aceptadas"], sorted(r["duplicadas"]), r["veredictos"]), ([], ["l1-act-q1", "l1-act-q2"], []))
            self.assertEqual(len(fuente.lotes), 1)                                  # nada nuevo que calificar: no se vuelve a llamar
            self.assertEqual(len(m.Practica.objects.get(pk=p["id"]).respuestas), 2)
            r = self.json_ok(self.responder(p["id"], [self.r("l1-act-q2", 3, INCORRECTA_Q2)]))     # mayor: sustituye y se vuelve a calificar
            self.assertEqual((r["aceptadas"], r["veredictos"][0]["correcta"], r["practica"]["aciertos"]), (["l1-act-q2"], False, 1))
            r = self.json_ok(self.responder(p["id"], [self.r("l1-act-q2", 2, CORRECTAS["l1-act-q2"])]))    # menor: llega tarde y no pisa
            self.assertEqual((r["aceptadas"], r["superadas"]), ([], ["l1-act-q2"]))
        fila = m.Practica.objects.get(pk=p["id"])
        self.assertEqual([(x["pregunta_ref"], x["secuencia"]) for x in fila.respuestas], [("l1-act-q1", 1), ("l1-act-q2", 3)])
        self.assertEqual(fila.aciertos, 1)

    def test_cada_respuesta_aceptada_emite_su_evento_sin_el_contenido_de_la_respuesta(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2")))
            self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))            # duplicada: no emite otra vez
        eventos = list(m.EventoSalida.objects.filter(tipo_evento="evaluacion.respuesta_registrada.v1").order_by("id"))
        self.assertEqual(len(eventos), 2)
        for e in eventos:
            self.assertEqual((e.carga["practica_id"], e.carga["asignacion_id"], e.carga["alumno_id"], e.carga["modo"]), (p["id"], self.a["id"], self.estudiante_id, "estudio"))
            self.assertNotIn("respuesta", e.carga)                               # BR-127
        self.assertEqual([e.carga["pregunta_ref"] for e in eventos], ["l1-act-q1", "l1-act-q2"])

    def test_lo_mal_formado_se_rechaza_pregunta_por_pregunta_y_el_resto_se_guarda(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            r = self.json_ok(self.responder(p["id"], [
                self.r("l1-act-q2", 1, CORRECTAS["l1-act-q2"]),
                self.r("l1-act-q1", 1, {"selectedOptionIds": ["zzz"]}),           # una opción que no está en la pregunta
                self.r("l1-act-q3", 1, {"blanks": {"nada": "x"}}),                # un hueco que no existe
                self.r("no-existe", 1, {"value": True}),                           # una pregunta que no es de la actividad
                self.r("l1-act-q4", 0, CORRECTAS["l1-act-q4"]),                    # secuencia inválida
                {"pregunta_ref": "l1-act-q5", "secuencia": 1, "respuesta": "b"},   # la respuesta debe ser un objeto
                {"secuencia": 1, "respuesta": {"value": True}},                    # sin pregunta_ref
            ]))
        self.assertEqual(r["aceptadas"], ["l1-act-q2"])
        self.assertEqual(sorted(x["pregunta_ref"] for x in r["rechazadas"]), ["", "l1-act-q1", "l1-act-q3", "l1-act-q4", "l1-act-q5", "no-existe"])
        self.assertTrue(all(x["motivo"] for x in r["rechazadas"]))
        self.assertEqual(len(m.Practica.objects.get(pk=p["id"]).respuestas), 1)

    def test_un_envio_vacio_o_demasiado_grande_es_400(self):
        p = self.abrir()["practica"]
        self.assertEqual(self.responder(p["id"], []).status_code, 400)
        r = self.responder(p["id"], [self.r("l1-act-q2", i + 1, {"value": True}) for i in range(201)])
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))

    def test_terminar_dentro_del_envio_devuelve_el_resultado(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2", "l1-act-q3", "l1-act-q4", "l1-act-q5"), terminar=True))
        self.assertEqual((r["practica"]["estado"], r["resultado"]["correctas"], r["resultado"]["total"]), ("terminada", 5, 6))
        self.assertEqual(self.eventos("estudio.practica.terminada.v1"), ["estudio.practica.terminada.v1"])


class TerminarYResultadoTests(BasePractica):
    def test_el_resultado_es_un_conteo_amable_y_nunca_habla_de_nota(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2", "l1-act-q3", "l1-act-q4", "l1-act-q5")))
            r = self.json_ok(self.terminar(p["id"]))
        res = r["resultado"]
        self.assertEqual((res["correctas"], res["total"], res["porcentaje"], res["mensaje"], res["sin_calificar"]), (5, 6, 83.33, "¡Buen avance!", 0))
        self.assertEqual(len(res["revision"]), 5)
        self.assertEqual(set(res["revision"][0]), {"pregunta_ref", "correcta", "retroalimentacion"})
        self.assertEqual((r["practica"]["estado"], r["practica"]["aciertos"], r["practica"]["terminada_en"] is not None), ("terminada", 5, True))
        texto = str(r).lower()
        for palabra in ("nota", "examen", "evaluación", "evaluacion"):
            self.assertNotIn(palabra, texto)

    def test_los_tres_mensajes_segun_los_aciertos(self):
        b = self.crear_asignacion(LECCION_2)
        respuestas_l2 = {"l2-act-q1": {"selectedOptionIds": ["a"]},
                         "l2-act-q2": {"pairs": [{"leftId": "melting", "rightId": "s-l"}, {"leftId": "evaporation", "rightId": "l-g"},
                                                 {"leftId": "condensation", "rightId": "g-l"}, {"leftId": "solidification", "rightId": "l-s"}]},
                         "l2-act-q3": {"blanks": {"b1": "0"}}}
        malas = {"l2-act-q1": {"selectedOptionIds": ["b"]}, "l2-act-q2": {"pairs": [{"leftId": "melting", "rightId": "l-g"}]},
                 "l2-act-q3": {"blanks": {"b1": "100"}}}
        with self.biblioteca_que_califica():
            casos = [("todas", respuestas_l2, "¡Muy bien!", 3), ("una", {**malas, "l2-act-q1": respuestas_l2["l2-act-q1"]}, "Sigue practicando: puedes intentarlo otra vez", 1),
                     ("dos", {**malas, "l2-act-q1": respuestas_l2["l2-act-q1"], "l2-act-q3": respuestas_l2["l2-act-q3"]}, "¡Buen avance!", 2)]
            for nombre, respuestas, mensaje, correctas in casos:
                with self.subTest(nombre=nombre):
                    p = self.abrir(b["id"], nueva=True)["practica"]
                    self.json_ok(self.responder(p["id"], [self.r(ref, 1, resp) for ref, resp in respuestas.items()]))
                    res = self.json_ok(self.terminar(p["id"]))["resultado"]
                    self.assertEqual((res["mensaje"], res["correctas"], res["total"]), (mensaje, correctas, 3))

    def test_terminar_marca_el_bloque_de_la_practica_actualiza_el_resumen_de_la_tarea_y_es_idempotente(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2")))
            self.json_ok(self.terminar(p["id"]))
            self.json_ok(self.terminar(p["id"]))                                    # idempotente: no repite el evento
        tarea = m.Tarea.objects.get(asignacion_id=self.a["id"])
        self.assertIn("l1-activity", tarea.bloques_vistos)                          # práctica terminada al menos una vez (D-4)
        self.assertEqual((tarea.practica_intentos, tarea.practica_mejor, tarea.practica_ultima, tarea.practica_total), (1, 2, 2, 6))
        self.assertEqual(self.eventos("estudio.practica.terminada.v1"), ["estudio.practica.terminada.v1"])
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.practica.terminada.v1").carga
        self.assertEqual((carga["practica_id"], carga["numero"], carga["respondidas"], carga["aciertos"]), (p["id"], 1, 2, 2))
        resumen = self.json_ok(self.ver("/asignaciones/"))["asignaciones"][0]["practica"]
        self.assertEqual((resumen["intentos"], resumen["mejor_correctas"], resumen["ultima_correctas"], resumen["en_curso"]), (1, 2, 2, False))

    def test_la_mejor_y_la_ultima_son_de_las_practicas_terminadas(self):
        with self.biblioteca_que_califica():
            p1 = self.abrir()["practica"]
            self.json_ok(self.responder(p1["id"], self.correctas("l1-act-q1", "l1-act-q2", "l1-act-q3")))
            self.json_ok(self.terminar(p1["id"]))
            p2 = self.abrir()["practica"]
            self.json_ok(self.responder(p2["id"], self.correctas("l1-act-q1")))
            self.json_ok(self.terminar(p2["id"]))
            self.abrir()                                                            # una tercera en curso: aún no cuenta como última
        tarea = m.Tarea.objects.get()
        self.assertEqual((tarea.practica_intentos, tarea.practica_mejor, tarea.practica_ultima), (3, 3, 1))
        self.assertTrue(self.json_ok(self.ver("/asignaciones/"))["asignaciones"][0]["practica"]["en_curso"])

    def test_no_se_responde_sobre_una_practica_terminada_pero_reenviar_lo_mismo_se_acusa(self):
        with self.biblioteca_que_califica():
            p = self.abrir()["practica"]
            self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1"), terminar=True))
            r = self.responder(p["id"], self.correctas("l1-act-q2"))
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "practica_terminada"))
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))      # el reintento de red del mismo envío
            self.assertEqual((r["aceptadas"], r["duplicadas"], r["practica"]["estado"]), ([], ["l1-act-q1"], "terminada"))
        self.assertEqual(len(m.Practica.objects.get(pk=p["id"]).respuestas), 1)


class SeparadaDeLaEvaluacionFormalTests(BasePractica):
    def test_practicar_no_toca_ni_consume_los_intentos_formales(self):
        formales = IntentoExpediente.objects.create(evaluacion_ref="l3-exam", curso_ref=CURSO, persona_id=self.estudiante_id, dispositivo="hw-juan",
                                                    total_preguntas=4)
        antes = (m7.Intento.objects.count(), IntentoExpediente.objects.count(), IntentoExpediente.objects.get(pk=formales.pk).estado)
        with self.biblioteca_que_califica():
            for _ in range(3):
                p = self.abrir(nueva=True)["practica"]
                self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2", "l1-act-q3"), terminar=True))
        despues = (m7.Intento.objects.count(), IntentoExpediente.objects.count(), IntentoExpediente.objects.get(pk=formales.pk).estado)
        self.assertEqual(antes, despues)                                             # BR-055: m07_intento y m10_intento, intactos
        self.assertEqual(m.Practica.objects.count(), 3)
        self.assertEqual(set(m.Practica.objects.values_list("modo", flat=True)), {"estudio"})

    def test_sin_practicar_tampoco_hay_intentos_formales(self):
        self.abrir()
        self.assertEqual((m7.Intento.objects.count(), IntentoExpediente.objects.count()), (0, 0))

    def test_la_tabla_de_practicas_no_admite_un_intento_formal(self):
        from django.db import IntegrityError, transaction
        p = self.abrir()["practica"]
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Practica.objects.filter(pk=p["id"]).update(modo="formal")



class SinBibliotecaTests(BasePractica):
    def test_sin_biblioteca_la_respuesta_se_guarda_sin_calificar_y_se_califica_despues(self):
        p = self.abrir()["practica"]                                                # la fuente de ejemplo no califica (501): es «sin biblioteca»
        r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2")))
        self.assertEqual((r["aceptadas"], r["veredictos"], r["practica"]["sin_calificar"], r["practica"]["aciertos"]), (["l1-act-q1", "l1-act-q2"], [], 2, 0))
        fila = m.Practica.objects.get(pk=p["id"])
        self.assertEqual([x["veredicto"] for x in fila.respuestas], [None, None])
        res = self.json_ok(self.terminar(p["id"]))["resultado"]                     # nada se inventa: sólo se dice que quedó guardado
        self.assertEqual((res["sin_calificar"], res["correctas"], res["mensaje"]), (2, 0, "Tus respuestas quedaron guardadas: verás cuántas acertaste en cuanto se revisen."))
        # cuando vuelve la biblioteca, la siguiente lectura las califica
        with self.biblioteca_que_califica() as fuente:
            r = self.json_ok(self.terminar(p["id"]))
            self.assertEqual(fuente.lotes, [["l1-act-q1", "l1-act-q2"]])
        self.assertEqual((r["resultado"]["correctas"], r["resultado"]["sin_calificar"], r["practica"]["aciertos"]), (2, 0, 2))
        self.assertEqual(sorted(v["pregunta_ref"] for v in r["veredictos"]), ["l1-act-q1", "l1-act-q2"])
        self.assertEqual(m.Tarea.objects.get().practica_mejor, 2)                   # y el resumen de la tarea también se corrige

    def test_al_reanudar_lo_pendiente_se_reintenta_y_lo_nuevo_se_califica_en_la_misma_llamada(self):
        p = self.abrir()["practica"]
        self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))            # sin calificar
        with self.biblioteca_que_califica() as fuente:
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q2")))
            self.assertEqual(fuente.lotes, [["l1-act-q1", "l1-act-q2"]])              # UNA llamada: lo pendiente de antes y lo nuevo
        self.assertEqual((r["practica"]["aciertos"], r["practica"]["sin_calificar"], len(r["veredictos"])), (2, 0, 2))

    def test_reanudar_reintenta_la_calificacion_pendiente(self):
        p = self.abrir()["practica"]
        self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))
        with self.biblioteca_que_califica():
            otra = self.abrir()["practica"]
        self.assertEqual((otra["reanudada"], otra["aciertos"], otra["respondidas"]["l1-act-q1"]["veredicto"]["correcta"]), (True, 1, True))

    def test_con_la_biblioteca_cerrada_se_guarda_igual_pero_no_se_abre_una_practica_nueva(self):
        from unittest import mock
        from ..dominio.errores import FuenteNoDisponible
        from ..infraestructura.contenedor import ContenidoAula
        p = self.abrir()["practica"]
        with mock.patch.object(ContenidoAula, "leccion", side_effect=FuenteNoDisponible("cerrada")):
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))          # guardar nunca falla de cara al alumno
            self.assertEqual((r["aceptadas"], r["veredictos"]), (["l1-act-q1"], []))
            abrir = self.enviar("post", f"/lecciones/{self.a['id']}/practica/")
            self.assertEqual((abrir.status_code, abrir.json()["codigo"]), (503, "fuente_no_disponible"))


class PropiedadYPermisosTests(BasePractica):
    def test_la_practica_es_de_su_titular(self):
        p = self.abrir()["practica"]
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")
        r = self.enviar("post", f"/practicas/{p['id']}/respuestas/", {"respuestas": self.correctas("l1-act-q1")}, hw=hw_ana)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.enviar("post", f"/practicas/{p['id']}/terminar/", hw=hw_ana).status_code, 403)
        self.assertEqual(self.enviar("post", "/practicas/no-existe/terminar/").status_code, 404)

    def test_con_sesion_el_profesor_y_la_administracion_no_practican(self):
        for cliente in (self.docente, self.admin):
            r = self.enviar("post", f"/lecciones/{self.a['id']}/practica/", cliente=cliente)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(self.enviar("post", f"/lecciones/{self.a['id']}/practica/", cliente=juan).status_code, 200)


class ConLaBibliotecaRealTests(BasePractica):
    """La fuente «biblioteca» de verdad: la API de Contenido v2 de pruebas en loopback (HTTP, `POST /v2/evaluate/batch`)."""

    def test_se_califica_con_la_api_v2_en_una_llamada_por_envio(self):
        with self.host_de_contenido() as host:
            a = self.crear_asignacion(fuente="biblioteca")
            self.assertEqual(a["curso"]["fuente"], "biblioteca")
            p = self.abrir(a["id"])["practica"]
            antes = len([x for x in host.peticiones if "evaluate" in x])
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2", "l1-act-q3")))
            llamadas = [x for x in host.peticiones if "evaluate" in x][antes:]
            lote = [c for c in host.cuerpos if "items" in c][-1]
        self.assertEqual(len(llamadas), 1)                                          # UNA llamada al lote, no tres
        self.assertIn("batch", llamadas[0])
        self.assertEqual((r["practica"]["aciertos"], r["practica"]["sin_calificar"], [v["correcta"] for v in r["veredictos"]]), (3, 0, [True, True, True]))
        self.assertEqual([i["version"] for i in lote["items"]], ["1.0.0", "1.0.0", "1.0.0"])     # siempre con la versión (el contrato de evaluate)

    def test_si_la_biblioteca_se_cae_a_mitad_la_respuesta_se_guarda_sin_calificar(self):
        with self.host_de_contenido() as host:
            a = self.crear_asignacion(fuente="biblioteca")
            p = self.abrir(a["id"])["practica"]
            host.detener()                                                          # la biblioteca se cierra
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))
        self.assertEqual((r["aceptadas"], r["veredictos"], r["practica"]["sin_calificar"]), (["l1-act-q1"], [], 1))

    def test_cuando_la_biblioteca_vuelve_lo_guardado_sin_calificar_se_califica(self):
        with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
            manifiesto = json.load(f)
        with self.host_de_contenido() as host:
            a = self.crear_asignacion(fuente="biblioteca")
            p = self.abrir(a["id"])["practica"]
            ruta_del_enlace = host.ruta_enlace
            host.detener()                                                          # la biblioteca se cierra: la respuesta queda guardada, sin nota
            r = self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1", "l1-act-q2")))
            self.assertEqual((r["veredictos"], r["practica"]["sin_calificar"], r["practica"]["aciertos"]), ([], 2, 0))
            nueva = HostContenidoV2Pruebas(ruta_del_enlace, {CURSO: manifiesto}).iniciar()      # vuelve la biblioteca
            try:
                r = self.json_ok(self.terminar(p["id"]))                             # la siguiente lectura las califica
            finally:
                nueva.detener()
        self.assertEqual((r["resultado"]["correctas"], r["resultado"]["sin_calificar"], sorted(v["pregunta_ref"] for v in r["veredictos"])),
                         (2, 0, ["l1-act-q1", "l1-act-q2"]))
        self.assertEqual(m.Practica.objects.get(pk=p["id"]).aciertos, 2)
