"""
La actividad lanzada en clase de punta a punta (007-05, 007-06, 007-08): la tableta guarda respuestas una a una (idempotente
por secuencia), el aula las compara donde vive la clave, el profesor ve el avance vivo y los rezagados, y el cierre no pierde
entregas (BR-052, DEC-019). La biblioteca se sustituye por el manifiesto de ejemplo con un evaluador de mentira.
"""
from __future__ import annotations

from unittest import mock

from expediente.models import Auditoria

from .. import models as m
from ..aplicacion import casos_uso as cu
from ..aplicacion import casos_uso_actividad as ca
from ..aplicacion import casos_uso_tiempo_real as tr
from ..dominio import sesion as dom
from ..dominio.errores import DistribucionCerrada, IntentoEntregado, ParticipanteExpulsado
from ..infraestructura.contenedor import ruta_ejemplo, servicios
from ..infraestructura.fuente_ejemplo import FuenteEjemplo
from .test_sesiones import ConSesionDeClase
from .test_tiempo_real import MIN, con_reloj

Q1 = {"selectedOptionIds": ["a"]}
Q2 = {"value": True}


class FuenteConNotas(FuenteEjemplo):
    """El manifiesto de ejemplo con un evaluador de mentira: todo es correcto salvo la pregunta abierta (revisión manual)."""

    def evaluar(self, curso_ref, version, objeto_ref, pregunta_ref, respuesta):
        manual = pregunta_ref.endswith("q6")
        return {"questionId": pregunta_ref, "score": None if manual else 1.0, "maxScore": 4.0 if manual else 1.0,
                "correct": None if manual else True, "requiresManualGrading": manual, "feedback": []}

    def evaluar_lote(self, curso_ref, version, items):
        return [self.evaluar(curso_ref, version, i["objectId"], i["questionId"], i["response"]) for i in items]


def con_biblioteca_que_califica(prueba):
    def envuelto(self, *args, **kwargs):
        with mock.patch("classroom_engine.infraestructura.contenedor.fuente",
                        side_effect=lambda nombre=None, curso_ref="": FuenteConNotas(ruta_ejemplo())):
            return prueba(self, *args, **kwargs)
    envuelto.__name__ = prueba.__name__
    return envuelto


class ConActividad(ConSesionDeClase):
    def setUp(self):
        super().setUp()
        self.s = self.iniciar()
        self.ana = self.unirse(self.s, persona="ana", rotulo="Ana", dispositivo="t-ana")["participante"]["id"]
        self.beto = self.unirse(self.s, persona="beto", rotulo="Beto", dispositivo="t-beto")["participante"]["id"]

    def lanzar(self, **extra) -> dict:
        r = self.api.post(f"/api/aula/sesiones/{self.s['id']}/distribuciones/",
                          {"clase": "actividad", "objeto_ref": "l1-activity", "intentos_permitidos": 2, **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def responder(self, d, pid, respuestas, esperado=200, **extra):
        r = self.api.post(f"/api/aula/sesiones/{self.s['id']}/distribuciones/{d['id']}/respuestas/",
                          {"participante_id": pid, "respuestas": respuestas, **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def resultados(self, d) -> dict:
        r = self.api.get(f"/api/aula/sesiones/{self.s['id']}/distribuciones/{d['id']}/resultados/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    @staticmethod
    def q(ref, secuencia, respuesta, **extra):
        return {"pregunta_ref": ref, "secuencia": secuencia, "respuesta": respuesta, **extra}


class GuardarRespuestasTests(ConActividad):
    def test_al_lanzar_se_fija_lo_que_hace_falta_para_el_avance(self):
        d = self.lanzar()
        self.assertEqual((d["total_preguntas"], d["puntos_totales"]), (6, 13.0))

    @con_biblioteca_que_califica
    def test_cada_respuesta_se_guarda_y_se_califica_donde_vive_la_clave(self):
        d = self.lanzar()
        r = self.responder(d, self.ana, [self.q("l1-act-q1", 1, Q1)])
        self.assertEqual((r["acuse"], r["aceptadas"], r["intento"]["estado"], r["intento"]["respondidas"]), (True, ["l1-act-q1"], "en_curso", 1))
        self.assertNotIn("veredicto", str(r))          # el alumno no recibe la nota de una actividad en clase (DEC-032)
        f = m.Intento.objects.get(participante_id=self.ana)
        self.assertEqual((f.puntaje, f.puntaje_maximo, f.respuestas[0]["veredicto"]["correcta"]), (1.0, 1.0, True))
        self.assertEqual(f.respuestas[0]["secuencia"], 1)
        self.assertIn(dom.EV_RESPUESTA_REGISTRADA, self.eventos(self.s["id"]))
        carga = m.EventoSalida.objects.get(tipo_evento=dom.EV_RESPUESTA_REGISTRADA).carga
        self.assertNotIn("respuesta", carga)            # BR-127: la carga del evento no lleva el contenido

    def test_sin_biblioteca_la_respuesta_se_guarda_igual_sin_calificar(self):
        d = self.lanzar()
        r = self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)])
        self.assertEqual(r["aceptadas"], ["l1-act-q2"])                  # guardar nunca falla de cara al alumno (UXR-004)
        f = m.Intento.objects.get(participante_id=self.ana)
        self.assertEqual((f.respuestas[0]["veredicto"], f.puntaje), (None, None))
        fila = next(x for x in self.resultados(d)["filas"] if x["participante_id"] == self.ana)
        self.assertEqual((fila["respondidas"], fila["sin_calificar"], fila["porcentaje"]), (1, 1, None))

    @con_biblioteca_que_califica
    def test_un_reenvio_no_duplica_nada(self):
        d = self.lanzar()
        paquete = [self.q("l1-act-q1", 1, Q1), self.q("l1-act-q2", 1, Q2)]
        self.responder(d, self.ana, paquete)
        r = self.responder(d, self.ana, paquete)
        self.assertEqual((r["aceptadas"], sorted(r["duplicadas"])), ([], ["l1-act-q1", "l1-act-q2"]))   # acuse positivo igual
        self.assertEqual(m.Intento.objects.filter(participante_id=self.ana).count(), 1)
        self.assertEqual(len(m.Intento.objects.get(participante_id=self.ana).respuestas), 2)
        self.assertEqual(self.eventos(self.s["id"]).count(dom.EV_RESPUESTA_DEDUPLICADA), 2)

    def test_la_secuencia_mayor_sustituye_y_la_menor_llega_tarde(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 3, {"value": False})])
        r = self.responder(d, self.ana, [self.q("l1-act-q2", 2, {"value": True})])
        self.assertEqual((r["aceptadas"], r["superadas"]), ([], ["l1-act-q2"]))
        self.responder(d, self.ana, [self.q("l1-act-q2", 5, {"value": True})])
        f = m.Intento.objects.get(participante_id=self.ana)
        self.assertEqual((f.respuestas[0]["respuesta"], f.respuestas[0]["secuencia"]), ({"value": True}, 5))

    def test_lo_mal_formado_se_rechaza_pregunta_por_pregunta(self):
        d = self.lanzar()
        r = self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2), {"pregunta_ref": "l1-act-q1", "secuencia": 1, "respuesta": "a"},
                                         {"pregunta_ref": "l1-act-q3", "secuencia": 0, "respuesta": {"blanks": {"b1": "x"}}}])
        self.assertEqual(r["aceptadas"], ["l1-act-q2"])
        self.assertEqual(sorted(x["pregunta_ref"] for x in r["rechazadas"]), ["l1-act-q1", "l1-act-q3"])
        self.responder(d, self.ana, [], esperado=400)                                    # ni respuestas ni entrega
        self.responder(d, self.ana, [self.q(f"p{i}", 1, Q2) for i in range(201)], esperado=400)

    def test_solo_los_destinatarios_admitidos_responden(self):
        d = self.lanzar(alcance="seleccion", participantes=[self.ana])
        self.responder(d, self.beto, [self.q("l1-act-q2", 1, Q2)], esperado=403)         # no se le lanzó a Beto
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/participantes/{self.ana}/expulsar/", {"motivo": "x"}, format="json")
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)], esperado=403)         # BR-048
        self.responder({"id": "no-existe"}, self.ana, [self.q("l1-act-q2", 1, Q2)], esperado=404)


class IntentosTests(ConActividad):
    def test_entregar_sella_el_intento_y_reenviar_lo_entregado_no_abre_otro(self):
        d = self.lanzar()
        paquete = [self.q("l1-act-q2", 1, Q2)]
        r = self.responder(d, self.ana, paquete, entregar=True, intento_numero=1)
        self.assertEqual((r["intento"]["estado"], r["intento"]["numero"]), ("entregado", 1))
        r = self.responder(d, self.ana, paquete, entregar=True, intento_numero=1)        # el reintento de red del mismo envío
        self.assertEqual((r["intento"]["estado"], r["duplicadas"]), ("entregado", ["l1-act-q2"]))
        self.assertEqual(m.Intento.objects.filter(participante_id=self.ana).count(), 1)
        self.assertEqual(self.eventos(self.s["id"]).count(dom.EV_INTENTO_ENTREGADO), 1)  # se entrega una sola vez (INV-005)
        self.responder(d, self.ana, [self.q("l1-act-q3", 1, {"blanks": {"b1": "x"}})], esperado=409, intento_numero=1)   # ya entregado
        # el segundo intento (la actividad admite 2) empieza con su propia secuencia desde 1
        r = self.responder(d, self.ana, paquete, intento_numero=2)
        self.assertEqual((r["intento"]["numero"], r["intento"]["estado"], r["aceptadas"]), (2, "en_curso", ["l1-act-q2"]))
        self.responder(d, self.ana, paquete, entregar=True, intento_numero=2)
        self.responder(d, self.ana, paquete, esperado=400, intento_numero=4)             # el siguiente sería el 3
        self.responder(d, self.ana, paquete, esperado=409)                                # sin número: intentos agotados
        self.assertEqual(m.Intento.objects.filter(participante_id=self.ana).count(), 2)

    def test_una_entrega_sin_respuestas_nuevas_es_valida(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)])
        r = self.responder(d, self.ana, [], entregar=True)
        self.assertEqual(r["intento"]["estado"], "entregado")


class ResultadosEnVivoTests(ConActividad):
    def setUp(self):
        super().setUp()
        self.luis = self.unirse(self.s, persona="luis", rotulo="Luis", dispositivo="t-luis")["participante"]["id"]

    @con_biblioteca_que_califica
    def test_avance_por_alumno_rezagados_y_promedio_con_datos_suficientes(self):
        d = self.lanzar()
        todas = [self.q(f"l1-act-q{i}", 1, Q1 if i == 1 else Q2) for i in range(1, 6)]
        self.responder(d, self.ana, todas, entregar=True)                         # 5 de 6 calificadas, entregó
        self.responder(d, self.beto, todas[:3])                                   # respondiendo
        r = self.resultados(d)
        filas = {f["participante_id"]: f for f in r["filas"]}
        self.assertEqual((filas[self.ana]["estado"], filas[self.ana]["respondidas"], filas[self.ana]["porcentaje"]), ("entregado", 5, 100.0))
        self.assertEqual((filas[self.beto]["estado"], filas[self.beto]["respondidas"]), ("respondiendo", 3))
        self.assertEqual(filas[self.luis]["estado"], "sin_empezar")
        self.assertTrue(filas[self.luis]["rezagado"])                             # nadie más lo está: sólo el que no empezó
        self.assertEqual((r["totales"]["entregaron"], r["totales"]["respondiendo"], r["totales"]["sin_empezar"], r["totales"]["rezagados"]), (1, 1, 1, 1))
        self.assertIsNone(r["totales"]["promedio_porcentaje"])                    # CMP-043: con menos de tres entregas no hay promedio
        self.assertFalse(r["totales"]["datos_suficientes"])
        self.assertEqual(r["filas"][0]["participante_id"], self.luis)             # el que necesita atención va primero
        for pid in (self.beto, self.luis):
            self.responder(d, pid, todas, entregar=True)
        r = self.resultados(d)
        self.assertEqual((r["totales"]["entregaron"], r["totales"]["promedio_porcentaje"], r["totales"]["datos_suficientes"]), (3, 100.0, True))

    def test_el_panel_del_profesor_trae_el_avance_de_cada_actividad(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)], entregar=True)
        self.responder(d, self.beto, [self.q("l1-act-q2", 1, Q2)])
        avance = next(x for x in self.api.get(f"/api/aula/sesiones/{self.s['id']}/").json()["distribuciones"] if x["id"] == d["id"])["avance"]
        self.assertEqual(avance, {"destinatarios": 3, "entregaron": 1, "respondiendo": 1, "por_decidir": 0, "sin_empezar": 1})

    def test_el_alumno_no_ve_resultados_de_otros_pero_su_estado_trae_su_intento_y_su_cronometro(self):
        d = self.lanzar(tiempo_limite_seg=600)
        self.responder(d, self.ana, [self.q("l1-act-q2", 4, Q2)])
        estado = self.api.get(f"/api/aula/sesiones/{self.s['id']}/estado/?participante={self.ana}").json()
        p = estado["pendientes"][0]
        self.assertEqual((p["intentos_usados"], p["intento"]["numero"], p["intento"]["respondidas"], p["intento"]["secuencia_maxima"]), (1, 1, 1, 4))
        self.assertEqual(p["intento"]["respondidas_refs"], ["l1-act-q2"])   # sólo la referencia: nada del contenido ni de la nota
        self.assertEqual((p["cronometro"]["estado"], p["cronometro"]["limite_ms"]), ("en_curso", 600_000))
        self.assertEqual((p["intentos_permitidos"], p["tiempo_limite_seg"]), (2, 600))
        self.assertNotIn("puntaje", str(estado["pendientes"]))


class CierreSinPerderEntregasTests(ConActividad):
    def test_cerrar_la_clase_entrega_lo_capturado_de_quien_sigue_respondiendo(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)])
        r = self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        f = m.Intento.objects.get(participante_id=self.ana)
        self.assertEqual((f.estado, f.origen_envio), ("entregado", "cierre"))
        self.assertEqual(r.json()["resumen"]["pendientes"], 1)
        self.assertIsNotNone(f.enviado_en)

    def test_cerrar_la_actividad_tambien_entrega_lo_que_llevan(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)])
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/distribuciones/{d['id']}/cerrar/", {}, format="json")
        self.assertEqual(m.Intento.objects.get(participante_id=self.ana).estado, "entregado")

    def test_lo_capturado_antes_del_cierre_entra_por_la_gracia_y_se_suma_al_intento_del_cierre(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)])
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        cierre = m.Distribucion.objects.get(pk=d["id"]).cerrada_en
        # AC-040: capturada 2 minutos antes del cierre, llega 7 minutos después
        r = ca.EnviarRespuestas(con_reloj(cierre + 7 * MIN)).ejecutar(
            self.s["id"], d["id"], self.ana, {"respuestas": [self.q("l1-act-q3", 1, {"blanks": {"b1": "x"}}, capturada_en=cierre - 2 * MIN)],
                                              "origen": "cola"})
        self.assertEqual((r["politica"], r["aceptadas"], r["intento"]["estado"], r["intento"]["recuperado_de_cola"]),
                         ("aceptar", ["l1-act-q3"], "entregado", True))
        self.assertEqual(m.Intento.objects.filter(participante_id=self.ana).count(), 1)     # se sumó al del cierre, no abrió otro
        self.assertEqual(len(m.Intento.objects.get(participante_id=self.ana).respuestas), 2)

    def test_un_alumno_que_respondio_todo_sin_red_entrega_despues_del_cierre_dentro_de_la_gracia(self):
        d = self.lanzar()
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        cierre = m.Distribucion.objects.get(pk=d["id"]).cerrada_en
        r = ca.EnviarRespuestas(con_reloj(cierre + 3 * MIN)).ejecutar(
            self.s["id"], d["id"], self.beto, {"respuestas": [self.q("l1-act-q2", 1, Q2, capturada_en=cierre - 5_000)], "origen": "cola"})
        self.assertEqual((r["intento"]["estado"], r["intento"]["recuperado_de_cola"]), ("entregado", True))   # nadie más podrá entregarlo
        # BR-137: llega aunque el participante ya figure como «salió» (la cola se entrega sin sesión abierta)
        self.assertEqual(m.Participante.objects.get(pk=self.beto).estado, "salio")

    def test_fuera_de_la_gracia_no_se_descarta_en_silencio_lo_decide_el_profesor(self):
        d = self.lanzar()
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        cierre = m.Distribucion.objects.get(pk=d["id"]).cerrada_en
        # AC-041: llega a los 21 minutos
        r = ca.EnviarRespuestas(con_reloj(cierre + 21 * MIN)).ejecutar(
            self.s["id"], d["id"], self.beto, {"respuestas": [self.q("l1-act-q2", 1, Q2, capturada_en=cierre - 2 * MIN)], "origen": "cola"})
        self.assertEqual((r["politica"], r["intento"]["estado"]), ("decide_el_profesor", "pendiente_decision"))
        actividad = self.api.get(f"/api/aula/sesiones/{self.s['id']}/").json()["distribuciones"][0]
        self.assertEqual(actividad["avance"]["por_decidir"], 1)
        intento_id = r["intento"]["id"]
        rr = self.api.post(f"/api/aula/sesiones/{self.s['id']}/distribuciones/{d['id']}/envios/{intento_id}/aceptar/", {"profesor_id": "prof-1"}, format="json")
        self.assertEqual((rr.status_code, rr.json()["estado"], rr.json()["decidido_por"]), (200, "entregado", "prof-1"))
        self.assertTrue(m.Intento.objects.get(pk=intento_id).recuperado_de_cola)
        self.assertTrue(Auditoria.objects.filter(accion="aula.envio.aceptar", objeto_id=intento_id).exists())
        rr = self.api.post(f"/api/aula/sesiones/{self.s['id']}/distribuciones/{d['id']}/envios/{intento_id}/descartar/", {}, format="json")
        self.assertEqual(rr.status_code, 400)                                        # ya se decidió

    def test_el_profesor_puede_descartar_lo_que_llego_fuera_de_plazo(self):
        d = self.lanzar()
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        cierre = m.Distribucion.objects.get(pk=d["id"]).cerrada_en
        r = ca.EnviarRespuestas(con_reloj(cierre + 30 * MIN)).ejecutar(
            self.s["id"], d["id"], self.beto, {"respuestas": [self.q("l1-act-q2", 1, Q2, capturada_en=cierre - 1_000)], "origen": "cola"})
        rr = self.api.post(f"/api/aula/sesiones/{self.s['id']}/distribuciones/{d['id']}/envios/{r['intento']['id']}/descartar/", {}, format="json")
        self.assertEqual((rr.status_code, rr.json()["estado"]), (200, "descartado"))

    def test_lo_capturado_despues_del_cierre_no_existe_para_la_actividad(self):
        d = self.lanzar()
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        cierre = m.Distribucion.objects.get(pk=d["id"]).cerrada_en
        with self.assertRaises(DistribucionCerrada):
            ca.EnviarRespuestas(con_reloj(cierre + 2 * MIN)).ejecutar(
                self.s["id"], d["id"], self.beto, {"respuestas": [self.q("l1-act-q2", 1, Q2, capturada_en=cierre + 1_000)]})
        self.assertEqual(m.Intento.objects.filter(participante_id=self.beto).count(), 0)

    def test_un_intento_entregado_por_el_alumno_no_admite_respuestas_tardias(self):
        d = self.lanzar()
        self.responder(d, self.ana, [self.q("l1-act-q2", 1, Q2)], entregar=True, intento_numero=1)
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/cerrar/", {"forzar": True}, format="json")
        cierre = m.Distribucion.objects.get(pk=d["id"]).cerrada_en
        with self.assertRaises(IntentoEntregado):
            ca.EnviarRespuestas(con_reloj(cierre + MIN)).ejecutar(
                self.s["id"], d["id"], self.ana, {"respuestas": [self.q("l1-act-q3", 1, {"blanks": {"b1": "x"}}, capturada_en=cierre - 1_000)],
                                                  "intento_numero": 1})
