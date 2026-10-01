"""
Plazos de la evaluación (D-14, BR-073, BR-074, DEC-019): el plazo blando marca y no cierra; el endurecido cierra y entrega (TST-033); lo que llega
después se acepta dentro de la gracia (TST-042), espera la decisión del profesor pasada ésta (TST-078) y se rechaza si se capturó tras el cierre.
Ningún envío se descarta en silencio.
"""
from __future__ import annotations

from .. import models as m
from .base import BASE, MIN, SEG, BaseEvaluacion, respuesta_correcta, respuesta_incorrecta


class PlazoBlandoTests(BaseEvaluacion):
    def test_el_intento_en_curso_cruza_el_limite_se_marca_y_sigue_presentando(self):
        a = self.crear_asignacion("supervisado", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.latir_hasta(i, 280)
        self.assertEqual(self.estado(i)["intento"]["estado"], "en_curso")
        self.avanzar(seg=20)                                                           # llega el límite: BR-073, sólo se marca
        e = self.latido(i)
        self.assertEqual((e["intento"]["estado"], e["intento"]["fuera_de_plazo"]), ("en_curso_fuera_de_plazo", True))
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "activa_fuera_de_plazo")
        self.assertTrue(e["reloj"]["corriendo"])
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])    # sigue aceptando respuestas
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        self.assertEqual([f["fuera_de_plazo"] for f in panel["filas"]], [True])

    def test_entregar_fuera_de_plazo_lo_marca_y_publica_el_evento_pero_se_acepta(self):
        a = self.crear_asignacion("supervisado", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.latir_hasta(i, 300)
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        self.entregar(i, confirmar=True)
        fila = self.fila(i)
        self.assertEqual((fila.fuera_de_plazo, fila.origen_entrega, fila.estado in ("calificado", "en_revision_docente")), (True, "alumno", True))
        self.assertEqual(self.eventos("evaluacion.intento_fuera_de_plazo.v1"), ["evaluacion.intento_fuera_de_plazo.v1"])

    def test_el_que_entrega_a_tiempo_no_se_marca(self):
        a = self.crear_asignacion("supervisado", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 60)
        self.entregar(i, confirmar=True)
        self.assertEqual((self.fila(i).fuera_de_plazo, self.eventos("evaluacion.intento_fuera_de_plazo.v1")), (False, []))

    def test_prorrogar_devuelve_la_asignacion_a_activa_y_los_nuevos_intentos_no_nacen_marcados(self):
        a = self.crear_asignacion("supervisado", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        self.avanzar(minutos=6)
        self.accion(f"/asignaciones/{a['id']}/prorrogar/", {"limite_en": self.t + 20 * MIN})
        i = self.abrir(a["id"], esperado=201)["intento"]["id"]
        self.assertEqual((self.estado(i)["intento"]["estado"], self.fila(i).fuera_de_plazo), ("en_curso", False))

    def test_abrir_un_intento_con_el_plazo_blando_vencido_nace_fuera_de_plazo(self):
        a = self.crear_asignacion("supervisado", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        self.avanzar(minutos=6)
        i = self.abrir(a["id"], esperado=201)["intento"]["id"]
        self.assertEqual((self.estado(i)["intento"]["estado"], self.fila(i).fuera_de_plazo), ("en_curso_fuera_de_plazo", True))


class PlazoEndurecidoTests(BaseEvaluacion):
    def presentando(self, minutos: int = 10, respuestas: int = 1, **extra):
        a = self.crear_asignacion("supervisado", plazo="endurecido", limite_en=self.t + minutos * MIN, tiempo={"modo": "sin_limite"}, **extra)
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(cerradas[:respuestas])])
        return a, i, cerradas

    def test_tst_033_al_vencer_el_plazo_cierra_la_asignacion_y_entrega_lo_respondido(self):
        a, i, cerradas = self.presentando()
        self.latir_hasta(i, 580)
        self.assertEqual(self.estado(i)["intento"]["estado"], "en_curso")
        self.avanzar(seg=20)                                                           # la hora exacta del límite
        cerrada = self.ver(f"/asignaciones/{a['id']}/")
        self.assertEqual((cerrada["estado"], cerrada["cerrada_en"]), ("cerrada", a["limite_en"]))
        fila = self.fila(i)
        self.assertEqual((fila.origen_entrega, fila.entregado_en, len(fila.respuestas)), ("plazo", a["limite_en"], 1))
        self.assertIn(fila.estado, ("calificado", "en_revision_docente"))
        self.assertIn("entrega_automatica", self.incidentes(i))
        self.assertEqual(self.eventos("evaluacion.asignacion_cerrada.v1"), ["evaluacion.asignacion_cerrada.v1"])
        self.assertFalse(self.fila(i).fuera_de_plazo)                                  # entregó en el límite, no después
        self.assertEqual(self.estado(i)["intento"]["estado"], fila.estado)

    def test_el_cierre_por_plazo_se_aplica_al_leer_sin_esperar_al_programador(self):
        a, i, _ = self.presentando()
        self.latir_hasta(i, 580)
        self.avanzar(minutos=1)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/panel/")["asignacion"]["estado"], "cerrada")
        self.assertEqual(self.fila(i).origen_entrega, "plazo")

    def test_un_intento_sin_senal_se_entrega_con_el_reloj_detenido_en_su_ultimo_latido(self):
        a, i, _ = self.presentando()
        self.latir_hasta(i, 100)
        ultimo = self.t
        self.avanzar(minutos=15)                                                       # nadie da señal y el plazo vence
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "cerrada")
        fila = self.fila(i)
        self.assertEqual((fila.origen_entrega, fila.entregado_en, fila.consumido_ms), ("plazo", ultimo, 100 * SEG))
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["cerrada_en"], a["limite_en"])   # la asignación cerró en la fecha, no en el último latido

    def test_un_intento_suspendido_tambien_se_entrega_al_cerrar_y_nada_se_anula(self):
        a, i, _ = self.presentando()
        self.latir_hasta(i, 60)
        self.avanzar(minutos=1)
        self.assertEqual(self.estado(i)["intento"]["estado"], "pausado_desconexion")
        self.avanzar(minutos=15)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "cerrada")
        fila = self.fila(i)
        self.assertEqual((fila.origen_entrega, fila.estado in ("calificado", "en_revision_docente"), fila.anulado_por), ("plazo", True, ""))

    def test_el_cierre_no_inventa_intentos_para_quien_no_llego(self):
        a, i, _ = self.presentando()
        segundo, _ = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        self.latir_hasta(i, 580)
        self.avanzar(seg=20)
        total = self.ver(f"/asignaciones/{a['id']}/")["totales"]
        self.assertEqual((total["destinatarios"], total["sin_intento"], total["entregados"] + total["calificados"] + total["en_revision"]), (2, 1, 1))
        self.assertEqual(m.Intento.objects.filter(alumno_id=segundo).count(), 0)

    def test_no_se_abre_un_intento_nuevo_con_la_asignacion_cerrada_por_plazo(self):
        a, i, _ = self.presentando(minutos=5)
        self.avanzar(minutos=6)
        self.abrir(a["id"], hw=self.hw_juan, esperado=409)


class GraciaTests(BaseEvaluacion):
    """TST-042 y TST-078: la ventana de gracia de 15 minutos (DEC-019) y la decisión del profesor (BR-074)."""

    def cerrada_por_plazo(self, gracia_min: int | None = None):
        extra = {"gracia_min": gracia_min} if gracia_min is not None else {}
        a = self.crear_asignacion("supervisado", plazo="endurecido", limite_en=self.t + 10 * MIN, tiempo={"modo": "sin_limite"}, **extra)
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        self.latir_hasta(i, 580)
        self.avanzar(seg=20)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "cerrada")
        return a, i, cerradas

    def test_tst_042_lo_capturado_antes_del_cierre_y_recibido_dentro_de_la_gracia_se_acepta_y_recalifica(self):
        a, i, cerradas = self.cerrada_por_plazo()
        antes = self.fila(i).porcentaje
        self.avanzar(minutos=5)
        acuse = self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)], origen="cola")
        self.assertEqual((acuse["politica"], acuse["aceptadas"], acuse["rechazadas"]), ("aceptar", [cerradas[1]], []))
        fila = self.fila(i)
        self.assertEqual(len(fila.respuestas), 2)
        self.assertGreater(fila.porcentaje, antes)                                    # recalificado con la respuesta tardía
        self.assertIn("respuesta_tardia", self.incidentes(i))
        self.assertEqual(fila.envio_tardio, "")
        from .base import FuenteQueCalifica
        self.assertEqual(len(FuenteQueCalifica.lotes), 2)                              # una llamada al entregar y otra sólo con lo nuevo
        self.assertEqual(FuenteQueCalifica.lotes[1], [cerradas[1]])

    def test_el_reenvio_de_la_misma_cola_dentro_de_la_gracia_no_cambia_nada_inv_005(self):
        a, i, cerradas = self.cerrada_por_plazo()
        self.avanzar(minutos=2)
        cola = [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)]
        self.responder(i, cola, origen="cola")
        despues = (self.fila(i).porcentaje, len(self.fila(i).respuestas), self.incidentes(i))
        repetido = self.responder(i, cola, origen="cola")
        self.assertEqual((repetido["aceptadas"], repetido["duplicadas"]), ([], [cerradas[1]]))
        self.assertEqual((self.fila(i).porcentaje, len(self.fila(i).respuestas), self.incidentes(i)), despues)

    def test_tst_078_pasada_la_gracia_queda_pendiente_del_profesor_y_no_se_descarta(self):
        a, i, cerradas = self.cerrada_por_plazo()
        self.avanzar(minutos=20)                                                       # la gracia era de 15
        acuse = self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)], origen="cola")
        self.assertEqual((acuse["politica"], acuse["aceptadas"]), ("decide_el_profesor", []))
        fila = self.fila(i)
        self.assertEqual((fila.envio_tardio, len(fila.respuestas), len(fila.respuestas_pendientes)), ("pendiente_decision", 1, 1))
        self.assertEqual(self.eventos("evaluacion.envio_tardio_pendiente.v1"), ["evaluacion.envio_tardio_pendiente.v1"])
        # el profesor lo ve en el panel, arriba de lo que no necesita nada suyo, y en los totales
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        self.assertEqual((panel["totales"]["pendientes_decision"], panel["filas"][0]["envio_tardio"]), (1, "pendiente_decision"))

    def test_el_reenvio_de_lo_pendiente_no_lo_duplica_ni_repite_el_aviso(self):
        a, i, cerradas = self.cerrada_por_plazo()
        self.avanzar(minutos=20)
        cola = [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)]
        self.responder(i, cola, origen="cola")
        self.responder(i, cola, origen="cola")
        self.assertEqual(len(self.fila(i).respuestas_pendientes), 1)
        self.assertEqual(len(self.eventos("evaluacion.envio_tardio_pendiente.v1")), 1)

    def test_el_profesor_acepta_lo_pendiente_se_suma_se_recalifica_y_queda_su_firma(self):
        a, i, cerradas = self.cerrada_por_plazo()
        antes = self.fila(i).porcentaje
        self.avanzar(minutos=20)
        self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)], origen="cola")
        r = self.accion(f"/intentos/{i}/decidir-envio/", {"decision": "aceptar", "motivo": "Se le cayó la red al salir"})
        self.assertEqual((r["envio_tardio"], r["decidido_por"]), ("aceptado", self.docente_id))
        fila = self.fila(i)
        self.assertEqual((len(fila.respuestas), fila.envio_tardio, fila.decision_envio["decision"], fila.decision_envio["por"]),
                         (2, "aceptado", "aceptar", self.docente_id))
        self.assertGreater(fila.porcentaje, antes)
        self.assertIn("evaluacion.envio_tardio_decidido.v1", self.eventos())
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/panel/")["totales"]["pendientes_decision"], 0)

    def test_el_profesor_descarta_lo_pendiente_y_el_intento_no_cambia_pero_queda_constancia(self):
        a, i, cerradas = self.cerrada_por_plazo()
        antes = (self.fila(i).porcentaje, len(self.fila(i).respuestas))
        self.avanzar(minutos=20)
        self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)], origen="cola")
        r = self.accion(f"/intentos/{i}/decidir-envio/", {"decision": "descartar"})
        self.assertEqual(r["envio_tardio"], "descartado")
        fila = self.fila(i)
        self.assertEqual((fila.porcentaje, len(fila.respuestas)), antes)
        self.assertEqual(len(fila.respuestas_pendientes), 1)                           # lo descartado no se borra: es evidencia
        self.assertEqual(fila.decision_envio["decision"], "descartar")

    def test_se_decide_una_sola_vez_y_solo_sobre_un_envio_pendiente(self):
        a, i, cerradas = self.cerrada_por_plazo()
        self.accion(f"/intentos/{i}/decidir-envio/", {"decision": "aceptar"}, esperado=409)       # nada pendiente
        self.avanzar(minutos=20)
        self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)], origen="cola")
        self.accion(f"/intentos/{i}/decidir-envio/", {"decision": "quizas"}, esperado=400)
        self.accion(f"/intentos/{i}/decidir-envio/", {"decision": "aceptar"})
        self.accion(f"/intentos/{i}/decidir-envio/", {"decision": "descartar"}, esperado=409)     # ya está decidido

    def test_solo_el_profesor_decide_el_alumno_no(self):
        a, i, cerradas = self.cerrada_por_plazo()
        self.avanzar(minutos=20)
        self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 20 * SEG)], origen="cola")
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = alumno.post(f"{BASE}/intentos/{i}/decidir-envio/", {"decision": "aceptar"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.fila(i).envio_tardio, "pendiente_decision")

    def test_lo_capturado_despues_del_cierre_se_rechaza_y_no_deja_ni_pendiente(self):
        a, i, cerradas = self.cerrada_por_plazo()
        self.avanzar(minutos=2)
        r = self.api.post(f"{BASE}/intentos/{i}/respuestas/", {**self.alumno(), "origen": "cola", "respuestas": [
            self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] + 30 * SEG)]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))
        fila = self.fila(i)
        self.assertEqual((len(fila.respuestas), len(fila.respuestas_pendientes), fila.envio_tardio), (1, 0, ""))

    def test_la_gracia_es_configurable_y_con_cero_no_hay_ventana(self):
        a, i, cerradas = self.cerrada_por_plazo(gracia_min=0)
        self.avanzar(seg=30)
        acuse = self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=a["limite_en"] - 10 * SEG)], origen="cola")
        self.assertEqual(acuse["politica"], "decide_el_profesor")

    def test_si_entrego_el_alumno_ya_no_hay_mas_respuestas_ni_siquiera_dentro_de_la_gracia(self):
        a = self.crear_asignacion("supervisado", plazo="endurecido", limite_en=self.t + 10 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        self.entregar(i, confirmar=True)
        r = self.api.post(f"{BASE}/intentos/{i}/respuestas/", {**self.alumno(), "respuestas": [
            self.r(cerradas[1], 1, respuesta_incorrecta(cerradas[1]), capturada_en=self.t - SEG)]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "intento_cerrado"))
        self.assertEqual(len(self.fila(i).respuestas), 1)

    def test_el_tablet_sin_senal_que_responde_sin_red_hasta_el_limite_entra_por_la_gracia(self):
        """El intento se entregó con el reloj detenido en el último latido, pero la asignación cerró en la fecha límite: lo que el alumno respondió
        sin red ENTRE los dos instantes se capturó antes del cierre y se acepta (BR-074)."""
        a = self.crear_asignacion("supervisado", plazo="endurecido", limite_en=self.t + 10 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.latir_hasta(i, 100)
        sin_red = self.t
        self.avanzar(minutos=11)                                                       # sin señal hasta pasado el límite
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "cerrada")
        self.assertEqual(self.fila(i).entregado_en, sin_red)
        acuse = self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]), capturada_en=sin_red + 5 * MIN)], origen="cola")
        self.assertEqual((acuse["politica"], acuse["aceptadas"]), ("aceptar", [cerradas[0]]))
        self.assertEqual(len(self.fila(i).respuestas), 1)


class CierreManualTests(BaseEvaluacion):
    def test_cerrar_a_mano_entrega_a_todos_con_origen_cierre_y_la_gracia_corre_desde_ahi(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        otro, hw = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        j = self.abrir(a["id"], hw=hw, alumno_id=otro)["intento"]["id"]
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        for _ in range(2):
            self.avanzar(seg=20)
            self.latido(i)
            self.latido(j, hw=hw, alumno_id=otro)
        cierre = self.t
        r = self.accion(f"/asignaciones/{a['id']}/cerrar/", {"motivo": "Sonó el timbre"})
        self.assertEqual((r["estado"], r["entregados"], r["cerrada_en"]), ("cerrada", 2, cierre))
        self.assertEqual((self.fila(i).origen_entrega, self.fila(j).origen_entrega), ("cierre", "cierre"))
        self.assertEqual({self.fila(i).entregado_en, self.fila(j).entregado_en}, {cierre})
        # lo capturado antes del cierre llega a los 3 minutos: dentro de la gracia
        self.avanzar(minutos=3)
        acuse = self.responder(i, [self.r(cerradas[1], 1, respuesta_correcta(cerradas[1]), capturada_en=cierre - 5 * SEG)], origen="cola")
        self.assertEqual(acuse["politica"], "aceptar")

    def test_el_cierre_forzado_de_un_solo_intento_suspendido_tiene_origen_profesor(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 40)
        self.avanzar(minutos=1)
        self.assertEqual(self.estado(i)["intento"]["estado"], "pausado_desconexion")
        self.accion(f"/intentos/{i}/cerrar/")
        self.assertEqual(self.fila(i).origen_entrega, "profesor")

    def test_reabrir_deja_los_intentos_ya_entregados_como_estaban(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.accion(f"/asignaciones/{a['id']}/cerrar/")
        entregado = self.fila(i).entregado_en
        self.accion(f"/asignaciones/{a['id']}/reabrir/", {"limite_en": self.t + 60 * MIN})
        self.assertEqual((self.fila(i).entregado_en, self.fila(i).origen_entrega), (entregado, "cierre"))
        self.abrir(a["id"], esperado=409)                                              # su único intento ya se entregó (cupo de uno)
