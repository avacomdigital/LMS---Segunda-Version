"""
El tiempo real del aula sin abrir un socket (007-01 a 007-04, 007-06 a 007-13): la presencia por latido, el cierre por
inactividad, la detección de caída y la reanudación, el cronómetro, la mano levantada, la proyección de un alumno, el
anclaje, la tarea de estudio, el freno de `unirse` y la capacidad. Los sockets se prueban en `test_websockets.py`.

El reloj del nodo se sustituye por uno falso: cada caso de uso lee la hora de `Servicios.reloj` (BR-062).
"""
from __future__ import annotations

import dataclasses

from django.test import SimpleTestCase, override_settings

from ..aplicacion import casos_uso as cu
from ..aplicacion import casos_uso_cierre as cc
from ..aplicacion import casos_uso_tiempo_real as tr
from ..dominio import actividad as act
from ..dominio import sesion as dom
from ..infraestructura.contenedor import servicios
from ..infraestructura.limitador import LimitadorEnMemoria
from .. import models as m
from .test_sesiones import ConSesionDeClase

MIN = 60_000


class RelojFalso:
    def __init__(self, ahora: int):
        self.ahora = ahora

    def ahora_ms(self) -> int:
        return self.ahora


def con_reloj(ahora: int):
    """Los servicios de verdad con la hora del nodo en `ahora`."""
    return dataclasses.replace(servicios(), reloj=RelojFalso(ahora))


def ahora_real() -> int:
    return m.ahora_ms()


# ============================================================ dominio puro

class CronometroTests(SimpleTestCase):
    base = dict(abierta_en=1_000_000, pausada_ms=0, ahora=1_000_000)

    def test_sin_limite_no_hay_cronometro(self):
        self.assertIsNone(act.cronometro(tiempo_limite_seg=None, **self.base))

    def test_en_curso_congelado_con_gracia_y_vencido(self):
        en_curso = act.cronometro(tiempo_limite_seg=600, **{**self.base, "ahora": 1_000_000 + 60_000})
        self.assertEqual((en_curso["estado"], en_curso["restante_ms"]), (act.CRONO_EN_CURSO, 540_000))
        congelado = act.cronometro(tiempo_limite_seg=600, suspendida_en=1_000_000 + 100_000, **{**self.base, "ahora": 1_000_000 + 900_000})
        self.assertEqual((congelado["estado"], congelado["restante_ms"]), (act.CRONO_CONGELADO, 500_000))
        con_gracia = act.cronometro(tiempo_limite_seg=600, **{**self.base, "ahora": 1_000_000 + 600_000 + 5 * MIN})
        self.assertEqual((con_gracia["estado"], con_gracia["restante_ms"]), (act.CRONO_CON_GRACIA, 0))
        vencido = act.cronometro(tiempo_limite_seg=600, **{**self.base, "ahora": 1_000_000 + 600_000 + 16 * MIN})
        self.assertEqual(vencido["estado"], act.CRONO_VENCIDO)

    def test_la_pausa_acumulada_no_cuenta(self):
        r = act.cronometro(tiempo_limite_seg=600, abierta_en=0, pausada_ms=200_000, ahora=500_000)
        self.assertEqual((r["estado"], r["restante_ms"]), (act.CRONO_EN_CURSO, 300_000))

    def test_cerrada_esta_vencida(self):
        r = act.cronometro(tiempo_limite_seg=600, abierta_en=0, pausada_ms=0, ahora=999_999, cerrada_en=100_000)
        self.assertEqual((r["estado"], r["transcurrido_ms"]), (act.CRONO_VENCIDO, 100_000))


class RecepcionTardiaTests(SimpleTestCase):
    def test_abierta_se_acepta_siempre(self):
        self.assertEqual(act.politica_de_recepcion(cerrada_en=None, capturada_en=None, recibida_en=5), act.ACEPTAR)

    def test_capturado_antes_del_cierre_entra_dentro_de_la_gracia(self):
        # AC-040: cierre 10:00, gracia 15 min, capturado 09:58, llega 10:07
        self.assertEqual(act.politica_de_recepcion(cerrada_en=1_000, capturada_en=1_000 - 2 * MIN, recibida_en=1_000 + 7 * MIN), act.ACEPTAR)

    def test_capturado_antes_del_cierre_pero_fuera_de_la_gracia_lo_decide_el_profesor(self):
        # AC-041: llega a las 10:21
        self.assertEqual(act.politica_de_recepcion(cerrada_en=1_000, capturada_en=1_000 - 2 * MIN, recibida_en=1_000 + 21 * MIN),
                         act.DECIDE_EL_PROFESOR)

    def test_capturado_despues_del_cierre_no_cuenta(self):
        self.assertEqual(act.politica_de_recepcion(cerrada_en=1_000, capturada_en=1_500, recibida_en=1_600), act.RECHAZAR)

    def test_sin_hora_de_captura_manda_la_de_recepcion(self):
        self.assertEqual(act.politica_de_recepcion(cerrada_en=1_000, capturada_en=None, recibida_en=1_100), act.RECHAZAR)


class FusionTests(SimpleTestCase):
    def r(self, ref, secuencia, **extra):
        return {"pregunta_ref": ref, "secuencia": secuencia, "respuesta": {"value": True}, **extra}

    def test_un_reenvio_no_duplica(self):
        vigentes, res = act.fusionar_respuestas([], [self.r("q1", 1)])
        self.assertEqual(res.aceptadas, ["q1"])
        vigentes, res = act.fusionar_respuestas(vigentes, [self.r("q1", 1)])
        self.assertEqual((res.aceptadas, res.duplicadas, len(vigentes)), ([], ["q1"], 1))

    def test_la_secuencia_mayor_sustituye_y_la_menor_llega_tarde(self):
        vigentes, _ = act.fusionar_respuestas([], [self.r("q1", 3, respuesta={"value": False})])
        vigentes, res = act.fusionar_respuestas(vigentes, [self.r("q1", 2, respuesta={"value": True})])
        self.assertEqual((res.superadas, vigentes[0]["respuesta"]), (["q1"], {"value": False}))
        vigentes, res = act.fusionar_respuestas(vigentes, [self.r("q1", 4, respuesta={"value": True})])
        self.assertEqual((res.aceptadas, vigentes[0]["respuesta"], vigentes[0]["secuencia"]), (["q1"], {"value": True}, 4))

    def test_conserva_el_orden_de_llegada(self):
        vigentes, _ = act.fusionar_respuestas([], [self.r("q2", 1), self.r("q1", 1)])
        self.assertEqual([r["pregunta_ref"] for r in vigentes], ["q2", "q1"])


class RezagadosTests(SimpleTestCase):
    def fila(self, avance, estado="respondiendo"):
        return {"avance": avance, "estado": estado}

    def test_sin_con_quien_comparar_no_hay_rezagados(self):
        filas = [self.fila(0.0, "sin_empezar")]
        self.assertEqual(act.marcar_rezagados(filas), 0)

    def test_quien_va_un_tercio_por_detras_de_la_mediana_o_no_empezo(self):
        filas = [self.fila(0.9), self.fila(0.8), self.fila(0.3), self.fila(0.0, "sin_empezar"), self.fila(1.0, "entregado")]
        self.assertEqual(act.marcar_rezagados(filas), 2)
        self.assertEqual([f["rezagado"] for f in filas], [False, False, True, True, False])

    def test_porcentaje_en_escala_interna(self):
        self.assertEqual(act.porcentaje(17, 20), 85.0)
        self.assertEqual(act.porcentaje(25, 20), 100.0)
        self.assertIsNone(act.porcentaje(None, 20))
        self.assertIsNone(act.porcentaje(3, 0))


class LimitadorTests(SimpleTestCase):
    def test_bloquea_tras_el_maximo_y_libera_al_pasar_la_ventana(self):
        lim = LimitadorEnMemoria(maximo=3, ventana_ms=1_000)
        for t in (0, 100, 200):
            self.assertEqual(lim.bloqueado("tab", t), 0)
            lim.registrar_fallo("tab", t)
        self.assertEqual(lim.bloqueado("tab", 300), 700)
        self.assertEqual(lim.bloqueado("otra", 300), 0)
        self.assertEqual(lim.bloqueado("tab", 1_100), 0)   # el primer fallo salió de la ventana
        lim.registrar_fallo("tab", 1_100)
        lim.olvidar("tab")
        self.assertEqual(lim.bloqueado("tab", 1_100), 0)


# =============================================================== casos de uso

class PresenciaPorLatidoTests(ConSesionDeClase):
    def setUp(self):
        super().setUp()
        self.s = self.iniciar()
        self.pid = self.unirse(self.s)["participante"]["id"]
        self.t0 = m.Participante.objects.get(pk=self.pid).ultimo_latido_en

    def estado(self):
        return m.Participante.objects.get(pk=self.pid).estado

    def test_sin_latido_pasa_a_reconectando_y_con_latido_vuelve_a_conectado(self):
        self.assertEqual(tr.BarrerPresencia(con_reloj(self.t0 + 10_000)).ejecutar()["reconectando"], 0)   # aún no vence
        r = tr.BarrerPresencia(con_reloj(self.t0 + 16_000)).ejecutar()
        self.assertEqual((r["reconectando"], self.estado()), (1, "reconectando"))
        detalle = self.api.get(f"/api/aula/sesiones/{self.s['id']}/").json()
        self.assertEqual((detalle["conteo"]["conectados"], detalle["conteo"]["reconectando"]), (0, 1))
        self.assertEqual(m.Presencia.objects.filter(participante_id=self.pid).order_by("-id").first().detalle, "latido vencido")
        self.assertIn(dom.EV_PRESENCIA_REGISTRADA, self.eventos(self.s["id"]))
        # un latido suelto lo recupera (007-04): la presencia la decide el latido, no sólo lo que la tableta declare
        tr.LatidoParticipante(servicios()).ejecutar(self.s["id"], self.pid)
        self.assertEqual(self.estado(), "conectado")

    def test_la_ausencia_prolongada_lo_da_por_salido(self):
        tr.BarrerPresencia(con_reloj(self.t0 + 16_000)).ejecutar()
        r = tr.BarrerPresencia(con_reloj(self.t0 + 5 * MIN + 1_000)).ejecutar()
        p = m.Participante.objects.get(pk=self.pid)
        self.assertEqual((r["salieron"], p.estado), (1, "salio"))
        self.assertIsNotNone(p.salida)

    def test_un_latido_suelto_no_revierte_una_salida(self):
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/participantes/{self.pid}/presencia/", {"estado": "salio"}, format="json")
        tr.LatidoParticipante(servicios()).ejecutar(self.s["id"], self.pid)
        self.assertEqual(self.estado(), "salio")
        tr.LatidoParticipante(servicios()).ejecutar(self.s["id"], self.pid, estado="conectado")   # declararse conectado sí
        self.assertEqual(self.estado(), "conectado")

    def test_las_clases_suspendidas_no_se_barren(self):
        self.api.post(f"/api/aula/sesiones/{self.s['id']}/suspender/", {"causa": "caida_nodo"}, format="json")
        r = tr.BarrerPresencia(con_reloj(self.t0 + 10 * MIN)).ejecutar()
        self.assertEqual((r["sesiones"], self.estado()), (0, "reconectando"))

    def test_el_sondeo_tambien_cuenta_como_latido(self):
        m.Participante.objects.filter(pk=self.pid).update(estado="reconectando", ultimo_latido_en=1)
        self.api.get(f"/api/aula/sesiones/{self.s['id']}/estado/?participante={self.pid}")
        p = m.Participante.objects.get(pk=self.pid)
        self.assertEqual(p.estado, "conectado")
        self.assertGreater(p.ultimo_latido_en, 1)

    def test_perder_la_conexion_del_socket_pasa_a_reconectando_una_sola_vez(self):
        self.assertTrue(tr.PerderConexion(servicios()).ejecutar(self.s["id"], self.pid))
        self.assertFalse(tr.PerderConexion(servicios()).ejecutar(self.s["id"], self.pid))
        self.assertEqual(self.estado(), "reconectando")

    def test_la_telemetria_llega_al_inventario(self):
        from acceso.models import Organizacion
        from device_manager import models as m9
        Organizacion.objects.create(id="org-1", codigo="IE", nombre="IE", pais="CO", idioma="es", locale="es-CO",
                                    zona_horaria="America/Bogota", creado_en=1)
        s = self.iniciar(profesor="prof-2")
        pid = self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-telemetria")["participante"]["id"]
        tr.LatidoParticipante(servicios()).ejecutar(s["id"], pid, telemetria={"espacio_libre_mb": 1234, "bateria_pct": 87})
        d = m9.Dispositivo.objects.get(identificador_hw="tab-telemetria")
        self.assertEqual((d.espacio_libre_mb, d.bateria_pct), (1234, 87))


class InactividadTests(ConSesionDeClase):
    def test_a_los_120_minutos_sin_actividad_se_cierra_sola(self):
        s = self.iniciar()
        t0 = m.SesionDeClase.objects.get(pk=s["id"]).iniciada_en
        self.assertEqual(tr.CerrarInactivas(con_reloj(t0 + 119 * MIN)).ejecutar(), [])
        self.assertEqual(tr.CerrarInactivas(con_reloj(t0 + 121 * MIN)).ejecutar(), [s["id"]])
        f = m.SesionDeClase.objects.get(pk=s["id"])
        self.assertEqual((f.estado, f.origen_cierre), ("cerrada", "inactividad"))
        self.assertEqual(m.Resumen.objects.get(pk=s["id"]).origen_cierre, "inactividad")

    def test_un_alumno_conectado_mantiene_viva_la_clase(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        t0 = m.SesionDeClase.objects.get(pk=s["id"]).iniciada_en
        m.Participante.objects.filter(pk=pid).update(ultimo_latido_en=t0 + 110 * MIN)
        self.assertEqual(tr.CerrarInactivas(con_reloj(t0 + 121 * MIN)).ejecutar(), [])   # el latido fue hace 11 minutos
        self.assertEqual(tr.CerrarInactivas(con_reloj(t0 + 231 * MIN + 1)).ejecutar(), [s["id"]])

    def test_las_suspendidas_no_caducan(self):
        s = self.iniciar()
        self.api.post(f"/api/aula/sesiones/{s['id']}/suspender/", {"causa": "corte_electrico"}, format="json")
        t0 = m.SesionDeClase.objects.get(pk=s["id"]).iniciada_en
        self.assertEqual(tr.CerrarInactivas(con_reloj(t0 + 1000 * MIN)).ejecutar(), [])   # DEC-018


class CaidaYReanudacionTests(ConSesionDeClase):
    def test_al_arrancar_las_clases_abiertas_quedan_suspendidas_y_se_reanudan_con_un_toque(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s2"}, format="json")
        suspendidas = tr.DetectarCaida(servicios()).ejecutar()
        self.assertEqual(suspendidas, [s["id"]])
        d = self.api.get(f"/api/aula/sesiones/{s['id']}/").json()
        self.assertEqual((d["estado"], d["causa_suspension"], d["codigo_union"]), ("suspendida", "reinicio", s["codigo_union"]))
        rec = d["recuperacion"]
        self.assertEqual((rec["causa"], rec["bloque"], rec["dentro_de_ventana"]), ("reinicio", 2, True))
        self.assertIn("Tres estados", rec["bloque_rotulo"])
        self.assertGreaterEqual(rec["minuto"], 0)
        self.assertEqual(d["participantes"][0]["estado"], "reconectando")
        # la tableta ve que la clase está en pausa, sin que nadie le pida nada
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertEqual((estado["sesion"]["estado"], estado["recuperacion"]["causa"]), ("suspendida", "reinicio"))
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/reanudar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["recuperacion"]), (200, "abierta", None))
        self.assertEqual(r.json()["codigo_union"], s["codigo_union"])
        self.assertIn(dom.EV_SESION_SUSPENDIDA, self.eventos(s["id"]))

    def test_la_ventana_de_tres_minutos_se_mide_pero_no_impide_reanudar(self):
        s = self.iniciar()
        t0 = m.SesionDeClase.objects.get(pk=s["id"]).iniciada_en
        cu.SuspenderSesion(con_reloj(t0 + 1_000)).ejecutar(tr.SISTEMA, s["id"], "corte_electrico")
        sesion = m.SesionDeClase.objects.get(pk=s["id"])
        self.assertEqual(sesion.suspendida_en, t0 + 1_000)
        d = cu.VerSesion(con_reloj(t0 + 1_000 + 10 * MIN)).ejecutar(s["id"])
        self.assertFalse(d["recuperacion"]["dentro_de_ventana"])
        r = cu.ReanudarSesion(con_reloj(t0 + 1_000 + 10 * MIN)).ejecutar(tr.SISTEMA, s["id"])
        self.assertEqual(r["estado"], "abierta")

    def test_el_corte_se_fecha_en_la_ultima_senal_no_en_el_arranque(self):
        s = self.iniciar()
        ultima = m.SesionDeClase.objects.get(pk=s["id"]).iniciada_en
        tr.DetectarCaida(con_reloj(ultima + 30 * MIN)).ejecutar()
        self.assertEqual(m.SesionDeClase.objects.get(pk=s["id"]).suspendida_en, ultima)

    def test_reanudar_no_marca_como_salido_a_quien_estuvo_callado_durante_el_corte(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        t0 = m.Participante.objects.get(pk=pid).ultimo_latido_en
        cu.SuspenderSesion(con_reloj(t0 + 1_000)).ejecutar(tr.SISTEMA, s["id"], "reinicio")
        t_reanuda = t0 + 20 * MIN
        cu.ReanudarSesion(con_reloj(t_reanuda)).ejecutar(tr.SISTEMA, s["id"])
        tr.BarrerPresencia(con_reloj(t_reanuda + 1_000)).ejecutar()
        self.assertEqual(m.Participante.objects.get(pk=pid).estado, "reconectando")   # sigue esperando su primer latido
        tr.LatidoParticipante(servicios()).ejecutar(s["id"], pid)
        self.assertEqual(m.Participante.objects.get(pk=pid).estado, "conectado")

    def test_el_cronometro_de_una_actividad_se_congela_mientras_la_clase_esta_suspendida(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/",
                          {"clase": "actividad", "objeto_ref": "l1-activity", "tiempo_limite_seg": 600, "intentos_permitidos": 2}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        abierta = m.Distribucion.objects.get(pk=d["id"]).abierta_en
        cu.SuspenderSesion(con_reloj(abierta + 100_000)).ejecutar(tr.SISTEMA, s["id"], "reinicio")
        congelado = cu.EstadoParaTableta(con_reloj(abierta + 900_000)).ejecutar(s["id"], pid)["pendientes"][0]["cronometro"]
        self.assertEqual((congelado["estado"], congelado["restante_ms"]), (act.CRONO_CONGELADO, 500_000))
        cu.ReanudarSesion(con_reloj(abierta + 900_000)).ejecutar(tr.SISTEMA, s["id"])
        self.assertEqual(m.Distribucion.objects.get(pk=d["id"]).pausada_ms, 800_000)
        seguido = cu.EstadoParaTableta(con_reloj(abierta + 900_000)).ejecutar(s["id"], pid)["pendientes"][0]["cronometro"]
        self.assertEqual((seguido["estado"], seguido["restante_ms"]), (act.CRONO_EN_CURSO, 500_000))


class ManoLevantadaTests(ConSesionDeClase):
    def test_levantar_bajar_y_atender(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        base = f"/api/aula/sesiones/{s['id']}/participantes/{pid}"
        r = self.api.post(f"{base}/ayuda/", {"activa": True}, format="json")
        self.assertEqual((r.status_code, r.json()["cambio"]), (200, True))
        self.assertFalse(self.api.post(f"{base}/ayuda/", {"activa": True}, format="json").json()["cambio"])   # idempotente
        d = self.api.get(f"/api/aula/sesiones/{s['id']}/").json()
        self.assertEqual((d["manos_levantadas"], bool(d["participantes"][0]["ayuda_en"])), (1, True))
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertTrue(estado["ayuda_pedida"])
        r = self.api.post(f"{base}/atender/", {"profesor_id": "prof-1"}, format="json")
        self.assertEqual((r.status_code, r.json()["cambio"]), (200, True))
        self.assertEqual(self.api.get(f"/api/aula/sesiones/{s['id']}/").json()["manos_levantadas"], 0)
        self.assertIn(dom.EV_AYUDA_SOLICITADA, self.eventos(s["id"]))

    def test_solo_pide_ayuda_quien_esta_admitido(self):
        s = self.iniciar(grupo_id="")
        pid = self.unirse(s)["participante"]["id"]
        m.Participante.objects.filter(pk=pid).update(estado="salio", salida=1)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{pid}/ayuda/", {"activa": True}, format="json")
        self.assertEqual(r.status_code, 400)


class ProyeccionDeAlumnoTests(ConSesionDeClase):
    def test_estado_salvaguardas_y_auditoria(self):
        from expediente.models import Auditoria
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        otro = self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-2")["participante"]["id"]
        ruta = lambda p: f"/api/aula/sesiones/{s['id']}/participantes/{p}/proyeccion/"
        r = self.api.post(ruta(pid), {"activa": True, "profesor_id": "prof-1"}, format="json")
        self.assertEqual((r.status_code, r.json()["proyectando"]), (200, True))
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertTrue(estado["proyectando"])                                   # CMP-063: el alumno lo sabe siempre
        self.assertFalse(self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={otro}").json()["proyectando"])
        self.api.post(ruta(otro), {"activa": True, "profesor_id": "prof-1"}, format="json")   # uno solo a la vez
        self.assertFalse(m.Participante.objects.get(pk=pid).proyectado_desde)
        self.assertTrue(m.Participante.objects.get(pk=otro).proyectado_desde)
        self.api.post(ruta(otro), {"activa": False, "profesor_id": "prof-1"}, format="json")
        terminada = Auditoria.objects.filter(accion="aula.proyeccion.terminada", objeto_id=otro).first()
        self.assertEqual(terminada.actor_id, "prof-1")
        self.assertGreaterEqual(terminada.valor_nuevo["duracion_ms"], 0)         # el asiento lleva autor y duración
        self.assertTrue(Auditoria.objects.filter(accion="aula.proyeccion.iniciada", objeto_id=pid).exists())

    def test_la_proyeccion_termina_al_cerrar_la_clase(self):
        from expediente.models import Auditoria
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{pid}/proyeccion/", {"activa": True}, format="json")
        self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        self.assertIsNone(m.Participante.objects.get(pk=pid).proyectado_desde)
        self.assertTrue(Auditoria.objects.filter(accion="aula.proyeccion.terminada", objeto_id=pid).exists())

    def test_solo_alcanza_a_admitidos(self):
        s = self.iniciar(grupo_id="")
        pid = self.unirse(s)["participante"]["id"]
        m.Participante.objects.filter(pk=pid).update(estado="salio", salida=1)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{pid}/proyeccion/", {"activa": True}, format="json")
        self.assertEqual(r.status_code, 400)


class CierreCompletoTests(ConSesionDeClase):
    def test_anclar_despues_de_cerrar_y_sugerencias_del_curso(self):
        from expediente.models import Auditoria
        s = self.iniciar()
        self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        ruta = f"/api/aula/sesiones/{s['id']}/anclaje/"
        r = self.api.get(ruta)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["anclajes"], [])
        self.assertTrue(r.json()["sugerencias"], "el curso de ejemplo trae tema y referencias curriculares")
        elegido = r.json()["sugerencias"][0]
        r = self.api.post(ruta, {"nodos": [{"ref": elegido["ref"], "rotulo": elegido["rotulo"]}, {"ref": elegido["ref"]}], "profesor_id": "prof-1"},
                          format="json")
        self.assertEqual((r.status_code, r.json()["cambio"], len(r.json()["anclajes"])), (200, True, 1))   # BR-040: después del cierre
        self.assertNotIn(elegido["ref"], [x["ref"] for x in self.api.get(ruta).json()["sugerencias"]])      # ya no se sugiere lo anclado
        self.assertFalse(self.api.post(ruta, {"nodos": [{"ref": elegido["ref"], "rotulo": elegido["rotulo"]}]}, format="json").json()["cambio"])
        asiento = Auditoria.objects.filter(accion="aula.sesion.anclada", objeto_id=s["id"]).first()
        self.assertEqual(asiento.valor_anterior, {"anclajes": []})
        self.assertEqual(self.api.post(ruta, {"nodos": [{"rotulo": "sin ref"}]}, format="json").status_code, 400)

    def test_no_se_exige_anclar_para_cerrar(self):
        s = self.iniciar(via="libre", curso_ref="", leccion_ref="")
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["anclajes"]), (200, "cerrada", []))
        self.assertEqual(self.api.get(f"/api/aula/sesiones/{s['id']}/anclaje/").json()["sugerencias"], [])

    def test_dejar_una_tarea_de_estudio_con_fecha_limite(self):
        s = self.iniciar()
        self.unirse(s)
        d = self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/", {"clase": "recurso", "media_ref": "pdf-lab-guide", "rotulo": "Guía"},
                          format="json").json()
        self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        hasta = m.ahora_ms() + 3 * 24 * 60 * MIN
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/{d['id']}/estudio/", {"disponible": True, "hasta": hasta}, format="json")
        self.assertEqual((r.status_code, r.json()["disponible_estudio"], r.json()["estudio_hasta"]), (200, True, hasta))
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/{d['id']}/estudio/", {"disponible": True, "hasta": 5}, format="json")
        self.assertEqual(r.status_code, 400)
        # la tableta lo sabe al terminar la clase (007-09): «aviso de fin de clase con lo pendiente»
        pid = m.Participante.objects.get(sesion_id=s["id"]).id
        cierre = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()["cierre"]
        self.assertEqual((cierre["origen_cierre"], [e["rotulo"] for e in cierre["estudio"]], cierre["estudio"][0]["hasta"]), ("profesor", ["Guía"], hasta))

    def test_el_resumen_trae_la_participacion_por_alumno(self):
        s = self.iniciar()
        self.unirse(s)
        self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-2")
        self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/", {"clase": "actividad", "objeto_ref": "l1-activity"}, format="json")
        cerrada = self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {"forzar": True}, format="json").json()
        detalle = cerrada["resumen"]["detalle"]
        self.assertEqual(sorted(p["rotulo"] for p in detalle["participantes"]), ["Ana", "Luis"])
        self.assertEqual(len(detalle["pendientes"]), 2)                     # nadie respondió
        self.assertEqual(detalle["actividades"][0]["destinatarios"], 2)
        self.assertTrue(all(p["presente_ms"] >= 0 for p in detalle["participantes"]))


class FrenoYCapacidadTests(ConSesionDeClase):
    @override_settings(AVACOM_AULA_UNIRSE_INTENTOS=3)
    def test_un_codigo_equivocado_repetido_frena_a_la_tableta(self):
        s = self.iniciar()
        malos = {"codigo_union": "000000", "persona_id": "x", "dispositivo": "tab-freno"}
        for _ in range(3):
            self.assertEqual(self.api.post("/api/aula/sesiones/unirse/", malos, format="json").status_code, 404)
        r = self.api.post("/api/aula/sesiones/unirse/", {**malos, "codigo_union": s["codigo_union"]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (429, "demasiados_intentos"))
        self.assertGreater(r.json()["reintentar_en_ms"], 0)
        # otra tableta no paga por ella
        self.assertEqual(self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "y",
                                                                     "dispositivo": "tab-otra"}, format="json").status_code, 201)

    @override_settings(AVACOM_AULA_UNIRSE_INTENTOS=3)
    def test_acertar_borra_los_fallos_previos(self):
        s = self.iniciar()
        for _ in range(2):
            self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": "000000", "persona_id": "x", "dispositivo": "tab-borra"}, format="json")
        self.assertEqual(self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "x",
                                                                     "dispositivo": "tab-borra"}, format="json").status_code, 201)
        for _ in range(2):
            self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": "000000", "persona_id": "x", "dispositivo": "tab-borra"}, format="json")
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "x", "dispositivo": "tab-borra"}, format="json")
        self.assertEqual(r.status_code, 200)      # dos fallos nuevos no bastan para frenar

    @override_settings(AVACOM_AULA_DISPOSITIVOS_PICO=2, AVACOM_AULA_DISPOSITIVOS_NORMAL=1)
    def test_al_llegar_al_pico_se_rechaza_lo_nuevo_sin_tocar_a_los_conectados(self):
        s = self.iniciar()
        a = self.unirse(s, persona="a", dispositivo="t1")["participante"]["id"]
        self.assertEqual(self.api.get(f"/api/aula/sesiones/{s['id']}/").json()["capacidad"]["nivel"], "normal")
        self.unirse(s, persona="b", dispositivo="t2")
        capacidad = self.api.get(f"/api/aula/sesiones/{s['id']}/").json()["capacidad"]
        self.assertEqual((capacidad["nivel"], capacidad["activos"], capacidad["pico"]), ("lleno", 2, 2))
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "c", "dispositivo": "t3"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "aula_llena"))
        self.assertEqual(m.Participante.objects.filter(sesion_id=s["id"]).count(), 2)
        # quien ya estaba puede volver: readmitir no es una conexión nueva
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "a", "participante_id": a,
                                                         "dispositivo": "t1"}, format="json")
        self.assertEqual(r.status_code, 200)
