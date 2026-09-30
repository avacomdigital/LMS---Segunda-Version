"""
El trabajo sin red que se integra sin duplicar ni exigir sesión (CAP-048, FUN-086, D-9, D-10, D-11, D-15, BR-059, BR-060, BR-137, BR-138, TST-029, BR-074):
la cola del aparato llega en orden de secuencia, cada evento en su transacción; reenviar no duplica nada; sin sesión se autoriza por el aparato y por el alumno
que declara; la política de plazo blando y endurecido; y la decisión del profesor sobre lo que llegó fuera de la gracia.
"""
from __future__ import annotations

from unittest import mock

from acceso.models import Usuario
from expediente.models import Auditoria, ProgresoLeccion

from .. import models as m
from ..aplicacion import sincronizacion
from .base import BASE, BLOQUES_L1, CORRECTAS, LECCION_1, BaseEstudio

T0 = 1_800_000_000_000
MIN = 60_000
EMISOR = "instalacion-juan-01"


class BaseSync(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()

    def ev(self, secuencia: int, tipo: str, carga: dict, ocurrido_en: int | None = None, **extra) -> dict:
        evento = {"secuencia": secuencia, "tipo": tipo, "carga": {"asignacion_id": self.a["id"], **carga}, **extra}
        if ocurrido_en is not None:
            evento["ocurrido_en"] = ocurrido_en
        return evento

    def vistos(self, secuencia: int, refs: list[str], **carga):
        return self.ev(secuencia, "study.block.viewed", {"bloques_vistos": refs, **carga})

    def respuesta(self, secuencia: int, pregunta: str, respuesta: dict, numero: int = 1, secuencia_respuesta: int = 1, **extra):
        return self.ev(secuencia, "study.answer.submitted", {"objeto_ref": "l1-activity", "intento_numero": numero, "pregunta_ref": pregunta,
                                                            "respuesta": respuesta, "secuencia_respuesta": secuencia_respuesta}, **extra)

    def terminada(self, secuencia: int, numero: int = 1):
        return self.ev(secuencia, "study.practice.finished", {"objeto_ref": "l1-activity", "intento_numero": numero})

    def completada(self, secuencia: int):
        return self.ev(secuencia, "study.lesson.completed", {})

    def sync(self, eventos: list, hw: str | None = None, emisor: str = EMISOR, cliente=None, **extra):
        return self.enviar("post", "/sync/", {"emisor_id": emisor, "eventos": eventos, **extra}, hw=hw, cliente=cliente)

    def ok(self, eventos: list, **kw) -> dict:
        return self.json_ok(self.sync(eventos, **kw))

    def estados(self, r: dict) -> list[tuple]:
        return [(x["secuencia"], x["estado"], x["motivo"]) for x in r["resultados"]]


class IntegrarEventosTests(BaseSync):
    def test_sin_sesion_el_aparato_asignado_integra_el_avance_y_acusa_con_el_estado_de_las_tareas(self):
        with self.reloj(T0):
            r = self.ok([self.vistos(1, BLOQUES_L1[:2], bloque_actual=BLOQUES_L1[1], posicion_seg=12)])
        self.assertEqual((r["acuse"], r["servidor_en"]), (True, T0))
        self.assertEqual(r["resultados"], [{"secuencia": 1, "estado": "integrado", "motivo": "",
                                            "detalle": {"aceptados": BLOQUES_L1[:2], "desconocidos": [], "fuera_de_plazo": False}}])
        self.assertEqual(r["resumen"], {"integrados": 1, "duplicados": 0, "rechazados": 0, "pendientes_decision": 0})
        self.assertEqual([x["id"] for x in r["asignaciones"]], [self.a["id"]])
        tarea = r["asignaciones"][0]["tarea"]
        self.assertEqual((tarea["estado"], tarea["avance_pct"], tarea["bloques_atendidos"], tarea["ultimo_bloque"]["ref"]), ("en_curso", 28.57, 2, BLOQUES_L1[1]))
        self.assertEqual(r["veredictos"], [])
        fila = m.Sincronizacion.objects.get(emisor_id=EMISOR, secuencia=1)
        self.assertEqual((fila.estado, fila.alumno_id, fila.dispositivo_id, fila.tipo, fila.asignacion_id, fila.recibido_en, fila.ocurrido_en),
                         ("integrado", self.estudiante_id, self.propia["id"], "study.block.viewed", self.a["id"], T0, T0))
        self.assertEqual(float(ProgresoLeccion.objects.get(persona_id=self.estudiante_id, leccion_codigo=LECCION_1).porcentaje), 28.57)   # y pasa al expediente

    def test_un_evento_por_envio_resume_lo_integrado(self):
        with self.reloj(T0):
            self.ok([self.vistos(4, BLOQUES_L1[:1]), self.vistos(5, BLOQUES_L1[:2])])
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.trabajo.integrado.v1").carga
        self.assertEqual({k: carga[k] for k in ("alumno_id", "dispositivo_id", "emisor_id", "integrados", "duplicados", "rechazados", "pendientes_decision",
                                                "desde_secuencia", "hasta_secuencia")},
                         {"alumno_id": self.estudiante_id, "dispositivo_id": self.propia["id"], "emisor_id": EMISOR, "integrados": 2, "duplicados": 0,
                          "rechazados": 0, "pendientes_decision": 0, "desde_secuencia": 4, "hasta_secuencia": 5})
        self.ok([])                                                                  # un envío vacío no es un envío
        self.assertEqual(len(self.eventos("estudio.trabajo.integrado.v1")), 1)

    def test_las_respuestas_de_la_cola_abren_la_practica_con_el_numero_que_eligio_el_aparato(self):
        r = self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"], numero=1), self.respuesta(2, "l1-act-q2", CORRECTAS["l1-act-q2"], numero=1)])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "integrado", "")])
        practica = m.Practica.objects.get()
        self.assertEqual((practica.numero, practica.estado, practica.origen, practica.modo, practica.total_preguntas, practica.dispositivo_id),
                         (1, "en_curso", "cola", "estudio", 6, self.propia["id"]))
        self.assertEqual([(x["pregunta_ref"], x["secuencia"], x["origen"], x["sesion_ref"], x["veredicto"]) for x in practica.respuestas],
                         [("l1-act-q1", 1, "cola", EMISOR, None), ("l1-act-q2", 1, "cola", EMISOR, None)])
        self.assertEqual(r["resultados"][0]["detalle"], {"practica_id": practica.id, "numero": 1, "pregunta_ref": "l1-act-q1",
                                                          "aceptada": True, "duplicada": False, "superada": False})
        self.assertEqual(self.eventos("evaluacion.respuesta_registrada.v1"), ["evaluacion.respuesta_registrada.v1"] * 2)
        self.assertEqual(m.Tarea.objects.get().practica_intentos, 1)
        # el aparato numeró el intento 3 sin haber cerrado el 1: no se puede tener dos en curso
        r = self.ok([self.respuesta(3, "l1-act-q1", CORRECTAS["l1-act-q1"], numero=3)])
        self.assertEqual(self.estados(r), [(3, "rechazado", "practica_en_curso")])
        self.assertEqual(r["resultados"][0]["detalle"]["numero_en_curso"], 1)
        self.ok([self.terminada(4, 1), self.respuesta(5, "l1-act-q1", CORRECTAS["l1-act-q1"], numero=3)])
        self.assertEqual(sorted(m.Practica.objects.values_list("numero", "estado")), [(1, "terminada"), (3, "en_curso")])

    def test_terminar_la_practica_marca_el_bloque_y_actualiza_el_resumen(self):
        r = self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"]), self.terminada(2)])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "integrado", "")])
        self.assertEqual(r["resultados"][1]["detalle"]["recien_terminada"], True)
        self.assertEqual(m.Practica.objects.get().estado, "terminada")
        self.assertIn("l1-activity", m.Tarea.objects.get().bloques_vistos)
        self.assertEqual(self.eventos("estudio.practica.terminada.v1"), ["estudio.practica.terminada.v1"])
        r = self.ok([self.terminada(3, numero=9)])                                   # un intento que el nodo nunca vio
        self.assertEqual(self.estados(r), [(3, "rechazado", "no_encontrado")])

    def test_completar_sin_todos_los_bloques_se_rechaza_y_con_ellos_se_integra(self):
        r = self.ok([self.vistos(1, BLOQUES_L1[:3]), self.completada(2)])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "rechazado", "bloques_pendientes")])
        self.assertEqual([x["ref"] for x in r["resultados"][1]["detalle"]["faltan"]], BLOQUES_L1[3:])
        self.assertEqual(m.Tarea.objects.get().estado, "en_curso")
        self.assertEqual(self.eventos("estudio.leccion.completada.v1"), [])
        r = self.ok([self.vistos(3, BLOQUES_L1), self.completada(4)])
        self.assertEqual(self.estados(r), [(3, "integrado", ""), (4, "integrado", "")])
        self.assertEqual(r["asignaciones"][0]["tarea"]["estado"], "completada")
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.leccion.completada.v1").carga
        self.assertEqual((carga["origen"], carga["alumno_id"], carga["fuera_de_plazo"]), ("cola", self.estudiante_id, False))
        self.assertEqual(ProgresoLeccion.objects.get(persona_id=self.estudiante_id).estado, "completada")
        self.assertTrue(Auditoria.objects.filter(accion="estudio.leccion.completada").exists())

    def test_los_eventos_se_procesan_en_orden_de_secuencia_aunque_lleguen_desordenados(self):
        r = self.ok([self.terminada(3), self.respuesta(2, "l1-act-q1", CORRECTAS["l1-act-q1"]), self.vistos(1, BLOQUES_L1[:1])])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "integrado", ""), (3, "integrado", "")])      # la práctica se termina DESPUÉS de crearse
        self.assertEqual(m.Practica.objects.get().estado, "terminada")
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.trabajo.integrado.v1").carga
        self.assertEqual((carga["desde_secuencia"], carga["hasta_secuencia"]), (1, 3))


class IdempotenciaTests(BaseSync):
    """BR-060 · TST-029: el mismo `emisor_id + secuencia` dos veces es UNA sola respuesta."""

    def test_el_reenvio_devuelve_duplicado_con_el_mismo_resultado_y_no_duplica_nada(self):
        paquete = [self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"]), self.vistos(2, BLOQUES_L1[:2])]
        primero = self.ok(paquete)
        otra = self.ok(paquete)
        self.assertEqual(self.estados(otra), [(1, "duplicado", ""), (2, "duplicado", "")])
        self.assertEqual(otra["resumen"], {"integrados": 0, "duplicados": 2, "rechazados": 0, "pendientes_decision": 0})
        self.assertEqual(otra["resultados"][0]["detalle"]["estado_original"], "integrado")
        self.assertEqual(otra["resultados"][0]["detalle"]["practica_id"], primero["resultados"][0]["detalle"]["practica_id"])
        self.assertEqual(m.Sincronizacion.objects.count(), 2)
        self.assertEqual(m.Practica.objects.count(), 1)
        self.assertEqual(len(m.Practica.objects.get().respuestas), 1)               # una sola respuesta
        self.assertEqual(len(self.eventos("evaluacion.respuesta_registrada.v1")), 1)
        self.assertEqual([x["id"] for x in otra["asignaciones"]], [self.a["id"]])   # y el aparato recibe igual el estado vigente de la tarea

    def test_un_rechazo_tambien_queda_en_el_libro_y_el_reenvio_dice_lo_mismo(self):
        malo = self.ev(1, "study.lesson.completed", {})
        self.assertEqual(self.estados(self.ok([malo])), [(1, "rechazado", "bloques_pendientes")])
        self.ok([self.vistos(2, BLOQUES_L1)])
        r = self.ok([malo])                                                          # ahora sí estaría completo, pero el nodo ya respondió lo suyo
        self.assertEqual(self.estados(r), [(1, "duplicado", "bloques_pendientes")])
        self.assertEqual(r["resultados"][0]["detalle"]["estado_original"], "rechazado")
        self.assertEqual(m.Tarea.objects.get().estado, "en_curso")

    def test_dos_instalaciones_pueden_usar_la_misma_secuencia(self):
        self.ok([self.vistos(1, BLOQUES_L1[:1])], emisor="instalacion-A")
        r = self.ok([self.vistos(1, BLOQUES_L1[:2])], emisor="instalacion-B")
        self.assertEqual(self.estados(r), [(1, "integrado", "")])
        self.assertEqual(m.Sincronizacion.objects.count(), 2)

    def test_la_secuencia_de_otra_persona_no_se_revela_ni_se_toma(self):
        self.ok([self.vistos(1, BLOQUES_L1[:1])])
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")
        r = self.ok([self.vistos(1, BLOQUES_L1[:1])], hw=hw_ana)                     # el mismo emisor y secuencia, pero de Ana
        self.assertEqual(self.estados(r), [(1, "rechazado", "emisor_ajeno")])
        self.assertNotIn("practica_id", str(r))
        self.assertEqual(m.Sincronizacion.objects.count(), 1)

    def test_la_segunda_respuesta_de_una_pregunta_sigue_a_inv_013_por_su_secuencia_de_respuesta(self):
        self.ok([self.respuesta(1, "l1-act-q2", {"value": True}, secuencia_respuesta=3)])
        r = self.ok([self.respuesta(2, "l1-act-q2", {"value": False}, secuencia_respuesta=2)])       # otra llegada, secuencia de respuesta menor
        self.assertEqual((r["resultados"][0]["estado"], r["resultados"][0]["detalle"]["superada"], r["resultados"][0]["detalle"]["aceptada"]), ("integrado", True, False))
        r = self.ok([self.respuesta(3, "l1-act-q2", {"value": False}, secuencia_respuesta=5)])
        self.assertTrue(r["resultados"][0]["detalle"]["aceptada"])
        respuestas = m.Practica.objects.get().respuestas
        self.assertEqual([(x["respuesta"], x["secuencia"]) for x in respuestas], [({"value": False}, 5)])
        self.assertEqual(len(self.eventos("evaluacion.respuesta_registrada.v1")), 2)

    def test_una_reinstalacion_con_otro_emisor_no_duplica_la_respuesta(self):
        self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"])], emisor="instalacion-vieja")
        r = self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"])], emisor="instalacion-nueva")     # misma respuesta, otra cola
        self.assertEqual(r["resultados"][0]["detalle"]["duplicada"], True)
        self.assertEqual(len(m.Practica.objects.get().respuestas), 1)


class CalificarLoIntegradoTests(BaseSync):
    def test_lo_integrado_se_califica_despues_con_una_llamada_por_actividad_y_los_veredictos_vuelven_en_la_respuesta(self):
        with self.biblioteca_que_califica() as fuente:
            r = self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"]), self.respuesta(2, "l1-act-q2", {"value": True}),
                         self.respuesta(3, "l1-act-q3", CORRECTAS["l1-act-q3"])])
            self.assertEqual(fuente.lotes, [["l1-act-q1", "l1-act-q2", "l1-act-q3"]])       # UNA llamada por envío
            self.assertEqual(fuente.sueltas, [])
        practica = m.Practica.objects.get()
        self.assertEqual([(v["asignacion_id"], v["objeto_ref"], v["numero"], v["pregunta_ref"], v["veredicto"]["correcta"]) for v in r["veredictos"]],
                         [(self.a["id"], "l1-activity", 1, "l1-act-q1", True), (self.a["id"], "l1-activity", 1, "l1-act-q2", False),
                          (self.a["id"], "l1-activity", 1, "l1-act-q3", True)])
        self.assertEqual(set(r["veredictos"][0]["veredicto"]), {"pregunta_ref", "correcta", "puntaje", "puntaje_maximo", "pendiente", "retroalimentacion"})
        self.assertEqual(practica.aciertos, 2)
        self.assertEqual([x["veredicto"]["correcta"] for x in practica.respuestas], [True, False, True])

    def test_sin_biblioteca_se_integra_sin_calificar_y_la_siguiente_sincronizacion_lo_califica(self):
        r = self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"])])
        self.assertEqual((r["resultados"][0]["estado"], r["veredictos"]), ("integrado", []))
        self.assertIsNone(m.Practica.objects.get().respuestas[0]["veredicto"])
        with self.biblioteca_que_califica() as fuente:
            r = self.ok([self.respuesta(2, "l1-act-q2", CORRECTAS["l1-act-q2"])])
            self.assertEqual(fuente.lotes, [["l1-act-q1", "l1-act-q2"]])              # lo pendiente de antes y lo nuevo, en la misma llamada
        self.assertEqual(sorted(v["pregunta_ref"] for v in r["veredictos"]), ["l1-act-q1", "l1-act-q2"])
        self.assertEqual(m.Practica.objects.get().aciertos, 2)

    def test_terminar_en_el_mismo_envio_deja_el_resumen_de_la_tarea_con_lo_calificado(self):
        with self.biblioteca_que_califica():
            self.ok([self.respuesta(1, "l1-act-q1", CORRECTAS["l1-act-q1"]), self.respuesta(2, "l1-act-q2", CORRECTAS["l1-act-q2"]), self.terminada(3)])
        tarea = m.Tarea.objects.get()
        self.assertEqual((tarea.practica_intentos, tarea.practica_mejor, tarea.practica_ultima), (1, 2, 2))

    def test_una_respuesta_con_la_forma_equivocada_se_rechaza_cuando_se_puede_comprobar(self):
        r = self.ok([self.respuesta(1, "l1-act-q1", {"selectedOptionIds": ["zzz"]}), self.respuesta(2, "no-existe", {"value": True})])
        self.assertEqual(self.estados(r), [(1, "rechazado", "datos_invalidos"), (2, "rechazado", "no_encontrado")])
        self.assertEqual(m.Practica.objects.count(), 0)


class AutorizarPorElAparatoTests(BaseSync):
    """D-11 (revisada por D-15) · BR-137: sin sesión se autoriza por el aparato (registrado, activo, no bloqueado) y por el alumno que declara (existe y
    está activo). Ya no hace falta que el aparato sea suyo; cada evento comprueba que la asignación le alcance."""

    def test_un_aparato_compartido_sincroniza_para_el_alumno_que_declara(self):
        with self.reloj(T0):
            r = self.ok([self.vistos(1, BLOQUES_L1[:2])], hw=self.hw_compartida, alumno_id=self.estudiante_id)
        self.assertEqual(self.estados(r), [(1, "integrado", "")])
        fila = m.Sincronizacion.objects.get()
        self.assertEqual((fila.alumno_id, fila.dispositivo_id, fila.estado), (self.estudiante_id, self.compartida["id"], "integrado"))
        self.assertEqual(m.Tarea.objects.get().alumno_id, self.estudiante_id)

    def test_en_un_aparato_compartido_hay_que_decir_quien_es(self):
        r = self.sync([self.vistos(1, BLOQUES_L1[:1])], hw=self.hw_compartida)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_alumno"))
        self.assertEqual(self.ver("/sync/status/", hw=self.hw_compartida, emisor_id=EMISOR).status_code, 400)
        self.assertEqual(m.Sincronizacion.objects.count(), 0)

    def test_un_aparato_que_el_nodo_no_conoce_no_autoriza(self):
        r = self.sync([self.vistos(1, BLOQUES_L1[:1])], hw="hw-desconocida", alumno_id=self.estudiante_id)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (403, "sin_permiso", "dispositivo_desconocido"))
        self.assertEqual(m.Sincronizacion.objects.count(), 0)

    def test_el_alumno_declarado_debe_existir_y_estar_activo(self):
        r = self.sync([self.vistos(1, BLOQUES_L1[:1])], hw=self.hw_compartida, alumno_id="fantasma")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (403, "sin_permiso", "alumno_desconocido"))
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        Usuario.objects.filter(pk=ana_id).update(estado="INACTIVO")
        r = self.sync([self.vistos(1, BLOQUES_L1[:1])], alumno_id=ana_id)
        self.assertEqual((r.status_code, r.json()["motivo"]), (403, "alumno_desconocido"))
        self.assertEqual(self.ver("/sync/status/", emisor_id=EMISOR, alumno_id="fantasma").status_code, 403)
        self.assertEqual(m.Sincronizacion.objects.count(), 0)

    def test_un_aparato_asignado_a_otro_admite_al_alumno_que_declara_y_cada_evento_comprueba_su_asignacion(self):
        """D-15: la tableta de Juan sincroniza el trabajo de Ana (nombrada en la asignación); lo de otro grupo se rechaza evento por evento."""
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        ajena = self.crear_asignacion(grupo_id=self.otro_grupo["id"])
        r = self.ok([self.vistos(1, BLOQUES_L1[:1]), self.ev(2, "study.block.viewed", {"asignacion_id": ajena["id"], "bloques_vistos": ["x"]})], alumno_id=ana_id)
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "rechazado", "no_encontrado")])
        self.assertEqual({f.secuencia: (f.alumno_id, f.dispositivo_id) for f in m.Sincronizacion.objects.all()},
                         {1: (ana_id, self.propia["id"]), 2: (ana_id, self.propia["id"])})
        self.assertEqual([t.alumno_id for t in m.Tarea.objects.all()], [ana_id])          # el trabajo quedó a nombre de Ana, no del dueño de la tableta
        estado = self.json_ok(self.ver("/sync/status/", emisor_id=EMISOR, alumno_id=ana_id))
        self.assertEqual((estado["ultima_secuencia"], estado["conteos"]), (2, {"synced": 1, "rejected": 1, "conflict": 0}))
        del_dueno = self.json_ok(self.ver("/sync/status/", emisor_id=EMISOR))              # y el libro del dueño no cambia
        self.assertEqual((del_dueno["ultima_secuencia"], del_dueno["conteos"]), (0, {"synced": 0, "rejected": 0, "conflict": 0}))

    def test_sin_declarar_a_nadie_un_aparato_asignado_sincroniza_para_su_dueno(self):
        r = self.ok([self.vistos(1, BLOQUES_L1[:1])])
        self.assertEqual(self.estados(r), [(1, "integrado", "")])
        self.assertEqual(m.Sincronizacion.objects.get().alumno_id, self.estudiante_id)

    def test_la_misma_secuencia_de_otra_persona_con_el_mismo_emisor_no_se_revela(self):
        """`(emisor_id, secuencia)` es la clave del libro: si dos alumnos comparten instalación, la secuencia debe ser única en ella."""
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        self.ok([self.vistos(1, BLOQUES_L1[:1])], alumno_id=self.estudiante_id)
        r = self.ok([self.vistos(1, BLOQUES_L1[:2])], alumno_id=ana_id)
        self.assertEqual(self.estados(r), [(1, "rechazado", "emisor_ajeno")])
        self.assertEqual(m.Sincronizacion.objects.count(), 1)
        self.assertEqual(self.estados(self.ok([self.vistos(2, BLOQUES_L1[:2])], alumno_id=ana_id)), [(2, "integrado", "")])       # con otra secuencia sí

    def test_sin_aparato_ni_sesion_falta_el_dispositivo(self):
        r = self.api.post(f"{BASE}/sync/", {"emisor_id": EMISOR, "eventos": []}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))

    def test_un_aparato_bloqueado_o_retirado_no_sincroniza(self):
        from device_manager import models as m9
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=True)
        self.assertEqual(self.sync([self.vistos(1, BLOQUES_L1[:1])]).json()["codigo"], "dispositivo_bloqueado")
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=False, activo=False)
        self.assertEqual(self.sync([self.vistos(1, BLOQUES_L1[:1])]).json()["codigo"], "dispositivo_inactivo")

    def test_con_sesion_manda_la_persona_del_token_aunque_el_aparato_sea_compartido(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.json_ok(self.sync([self.vistos(1, BLOQUES_L1[:1])], hw=self.hw_compartida, cliente=juan))
        self.assertEqual(self.estados(r), [(1, "integrado", "")])
        self.assertEqual(m.Sincronizacion.objects.get().alumno_id, self.estudiante_id)

    def test_el_profesor_y_la_administracion_no_sincronizan_trabajo_de_alumnos(self):
        for cliente in (self.docente, self.admin):
            r = self.sync([self.vistos(1, BLOQUES_L1[:1])], cliente=cliente)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))


class ForaDeLoNormalTests(BaseSync):
    def test_mas_de_200_eventos_es_400_y_exactamente_200_se_procesan(self):
        r = self.sync([self.vistos(i, BLOQUES_L1[:1]) for i in range(1, 202)])
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertEqual(m.Sincronizacion.objects.count(), 0)
        r = self.ok([self.vistos(i, BLOQUES_L1[:1]) for i in range(1, 201)])
        self.assertEqual(r["resumen"]["integrados"], 200)

    def test_sin_emisor_o_con_eventos_que_no_son_una_lista_es_400(self):
        self.assertEqual(self.sync([], emisor="").status_code, 400)
        r = self.enviar("post", "/sync/", {"emisor_id": EMISOR, "eventos": {"secuencia": 1}})
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))

    def test_un_evento_malo_no_tumba_a_los_demas(self):
        r = self.ok([
            self.vistos(1, BLOQUES_L1[:1]),
            {"tipo": "study.block.viewed", "carga": {"asignacion_id": self.a["id"], "bloques_vistos": ["x"]}},          # sin secuencia
            {"secuencia": 2, "tipo": "study.otra.cosa", "carga": {"asignacion_id": self.a["id"]}},                       # tipo desconocido
            {"secuencia": 3, "tipo": "study.block.viewed", "carga": "no es un objeto"},
            self.ev(4, "study.block.viewed", {"bloques_vistos": []}),                                                    # sin nada que avanzar
            {"secuencia": 5, "tipo": "study.block.viewed", "carga": {"asignacion_id": "no-existe", "bloques_vistos": ["x"]}},
            self.vistos(6, BLOQUES_L1[:2]),
        ])
        estados = {x["secuencia"]: (x["estado"], x["motivo"]) for x in r["resultados"]}
        self.assertEqual(estados[None], ("rechazado", "evento_invalido"))
        self.assertEqual([estados[i] for i in (1, 2, 3, 4, 5, 6)],
                         [("integrado", ""), ("rechazado", "datos_invalidos"), ("rechazado", "datos_invalidos"), ("rechazado", "datos_invalidos"),
                          ("rechazado", "no_encontrado"), ("integrado", "")])
        self.assertEqual(r["resumen"], {"integrados": 2, "duplicados": 0, "rechazados": 5, "pendientes_decision": 0})
        self.assertEqual(m.Sincronizacion.objects.count(), 6)                          # el sin secuencia no se puede registrar
        again = self.ok([{"secuencia": 2, "tipo": "study.otra.cosa", "carga": {"asignacion_id": self.a["id"]}}])
        self.assertEqual(self.estados(again), [(2, "duplicado", "datos_invalidos")])
        self.assertEqual(float(m.Tarea.objects.get().avance_pct), 28.57)

    def test_la_asignacion_de_otro_grupo_se_rechaza_como_inexistente(self):
        ajena = self.crear_asignacion(grupo_id=self.otro_grupo["id"])
        r = self.ok([self.ev(1, "study.block.viewed", {"asignacion_id": ajena["id"], "bloques_vistos": ["x"]})])
        self.assertEqual(self.estados(r), [(1, "rechazado", "no_encontrado")])
        self.assertEqual(m.Tarea.objects.count(), 0)

    def test_un_fallo_inesperado_en_un_evento_no_tumba_a_los_demas_y_ese_no_se_acusa(self):
        original = sincronizacion.aplicar_evento

        def con_fallo(uow, **kw):
            if kw["carga"].get("bloque_actual") == "boom":
                raise RuntimeError("fallo inesperado")
            return original(uow, **kw)

        with mock.patch.object(sincronizacion, "aplicar_evento", side_effect=con_fallo), \
                self.assertLogs("modo_estudio.aplicacion.sincronizacion", level="ERROR"):
            r = self.ok([self.vistos(1, BLOQUES_L1[:1]), self.vistos(2, BLOQUES_L1[:1], bloque_actual="boom"), self.vistos(3, BLOQUES_L1[:2])])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (3, "integrado", "")])       # el 2 no se acusa: la cola lo reenviará
        self.assertFalse(m.Sincronizacion.objects.filter(secuencia=2).exists())
        r = self.ok([self.vistos(2, BLOQUES_L1[:1], bloque_actual=BLOQUES_L1[0])])             # el reenvío sí se procesa
        self.assertEqual(self.estados(r), [(2, "integrado", "")])

    def test_lo_capturado_no_puede_ser_posterior_a_la_llegada_el_reloj_del_nodo_manda(self):
        with self.reloj(T0):
            self.ok([{**self.vistos(1, BLOQUES_L1[:1]), "ocurrido_en": T0 + 10 * 86_400_000, "ocurrido_en_tableta": T0 + 99}])
        fila = m.Sincronizacion.objects.get()
        self.assertEqual((fila.ocurrido_en, fila.ocurrido_en_tableta, fila.recibido_en), (T0, T0 + 99, T0))


class PlazoBlandoTests(BaseSync):
    def test_lo_capturado_despues_de_la_fecha_limite_se_integra_marcado_fuera_de_plazo(self):
        con_fecha = self.crear_asignacion(fecha_limite=T0)
        a = con_fecha["id"]
        with self.reloj(T0 + 5 * 86_400_000):
            r = self.ok([{"secuencia": 1, "tipo": "study.block.viewed", "ocurrido_en": T0 - 1_000,
                          "carga": {"asignacion_id": a, "bloques_vistos": BLOQUES_L1[:1]}},
                         {"secuencia": 2, "tipo": "study.block.viewed", "ocurrido_en": T0 + 1_000,
                          "carga": {"asignacion_id": a, "bloques_vistos": BLOQUES_L1[:2]}}])
        self.assertEqual([x["detalle"]["fuera_de_plazo"] for x in r["resultados"]], [False, True])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "integrado", "")])          # blando: SIEMPRE se integra
        self.assertEqual((r["asignaciones"][0]["tarea"]["fuera_de_plazo"], r["asignaciones"][0]["tarea"]["vencida"]), (True, True))


class PlazoEndurecidoTests(BaseSync):
    """D-9: `endurecido` cierra al vencer. Capturado antes y recibido dentro de la gracia: se acepta; capturado antes y recibido después: decide el profesor
    (BR-074, nunca se descarta en silencio); capturado después del cierre: se rechaza."""

    def setUp(self):
        super().setUp()
        self.dura = self.crear_asignacion(fecha_limite=T0, plazo="endurecido", gracia_min=15)
        self.d = self.dura["id"]

    def evento(self, secuencia: int, capturado: int, refs=None, **carga):
        return {"secuencia": secuencia, "tipo": "study.block.viewed", "ocurrido_en": capturado,
                "carga": {"asignacion_id": self.d, "bloques_vistos": refs or BLOQUES_L1[:1], **carga}}

    def test_antes_del_cierre_dentro_de_la_gracia_pendiente_de_decision_y_rechazado(self):
        with self.reloj(T0 - 10 * MIN):
            r = self.ok([self.evento(1, T0 - 11 * MIN, BLOQUES_L1[:1])])
        self.assertEqual(self.estados(r), [(1, "integrado", "")])
        with self.reloj(T0 + 5 * MIN):                                               # capturado antes, recibido a los 5 min: dentro de los 15 de gracia
            r = self.ok([self.evento(2, T0 - MIN, BLOQUES_L1[:2])])
        self.assertEqual(self.estados(r), [(2, "integrado", "")])
        with self.reloj(T0 + 20 * MIN):                                              # capturado antes, recibido a los 20 min: decide el profesor
            r = self.ok([self.evento(3, T0 - MIN, BLOQUES_L1[:3])])
        self.assertEqual(self.estados(r), [(3, "pendiente_decision", "fuera_de_gracia")])
        self.assertEqual(r["resumen"]["pendientes_decision"], 1)
        with self.reloj(T0 + 20 * MIN):                                              # capturado después del cierre: se rechaza
            r = self.ok([self.evento(4, T0 + MIN, BLOQUES_L1[:4])])
        self.assertEqual(self.estados(r), [(4, "rechazado", "plazo_vencido")])
        self.assertEqual(m.Tarea.objects.get().bloques_vistos, BLOQUES_L1[:2])       # lo pendiente y lo rechazado no se aplicó
        libro = {f.secuencia: f for f in m.Sincronizacion.objects.all()}
        self.assertEqual({s: f.estado for s, f in libro.items()}, {1: "integrado", 2: "integrado", 3: "pendiente_decision", 4: "rechazado"})
        self.assertEqual(libro[3].carga["bloques_vistos"], BLOQUES_L1[:3])            # con lo pendiente se conserva la carga completa

    def test_una_respuesta_pendiente_conserva_su_contenido_hasta_que_decide_el_profesor(self):
        evento = {"secuencia": 1, "tipo": "study.answer.submitted", "ocurrido_en": T0 - MIN,
                  "carga": {"asignacion_id": self.d, "objeto_ref": "l1-activity", "intento_numero": 1, "pregunta_ref": "l1-act-q1",
                            "respuesta": CORRECTAS["l1-act-q1"], "secuencia_respuesta": 1}}
        with self.reloj(T0 + 30 * MIN):
            self.assertEqual(self.estados(self.ok([evento])), [(1, "pendiente_decision", "fuera_de_gracia")])
        fila = m.Sincronizacion.objects.get()
        self.assertEqual(fila.carga["respuesta"], CORRECTAS["l1-act-q1"])
        self.assertEqual(m.Practica.objects.count(), 0)                              # todavía no existe: nada se aplica sin decisión

    def test_el_estado_de_la_sincronizacion_muestra_lo_que_espera_al_profesor(self):
        with self.reloj(T0 + 20 * MIN):
            self.ok([self.evento(1, T0 - MIN), self.evento(2, T0 + MIN)])
        estado = self.json_ok(self.ver("/sync/status/", emisor_id=EMISOR))
        self.assertEqual(estado["emisor_id"], EMISOR)
        self.assertEqual((estado["ultima_secuencia"], estado["conteos"]), (2, {"synced": 0, "rejected": 1, "conflict": 1}))
        self.assertEqual(estado["pendientes_decision"], [{"secuencia": 1, "tipo": "study.block.viewed", "asignacion_id": self.d, "motivo": "fuera_de_gracia"}])
        vacio = self.json_ok(self.ver("/sync/status/", emisor_id="otra"))
        self.assertEqual((vacio["ultima_secuencia"], vacio["conteos"], vacio["pendientes_decision"]), (0, {"synced": 0, "rejected": 0, "conflict": 0}, []))
        self.assertEqual(self.ver("/sync/status/").status_code, 400)

    def test_el_profesor_ve_lo_pendiente_y_puede_aceptarlo(self):
        with self.reloj(T0 + 20 * MIN):
            self.ok([self.evento(1, T0 - MIN, BLOQUES_L1[:3])])
        d = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/{self.d}/"))
        self.assertEqual(d["pendientes_decision"], 1)
        fila = d["alumnos"][0]
        self.assertEqual(fila["pendientes_decision"], 1)
        self.assertEqual(fila["decisiones"], [{"emisor_id": EMISOR, "secuencia": 1, "tipo": "study.block.viewed", "motivo": "fuera_de_gracia",
                                               "ocurrido_en": T0 - MIN, "recibido_en": T0 + 20 * MIN}])
        lista = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/"))["asignaciones"]
        self.assertEqual(next(x for x in lista if x["id"] == self.d)["pendientes_decision"], 1)
        with self.reloj(T0 + 3 * 60 * MIN):
            decision = fila["decisiones"][0]         # el par (emisor_id, secuencia) sale del detalle: con él se resuelve
            r = self.json_ok(self.api.post(f"{BASE}/docente/asignaciones/{self.d}/decisiones/", {
                "alumno_id": fila["alumno_id"], "secuencia": decision["secuencia"], "emisor_id": decision["emisor_id"], "decision": "aceptar",
                "actor": self.docente_id}, format="json"))
        self.assertEqual((r["estado"], r["motivo"], r["decidido_por"], r["decision"]), ("integrado", "aceptado_por_docente", self.docente_id, "aceptar"))
        tarea = m.Tarea.objects.get()
        self.assertEqual((tarea.bloques_vistos, tarea.estado), (BLOQUES_L1[:3], "en_curso"))
        fila = m.Sincronizacion.objects.get()
        self.assertEqual((fila.estado, fila.motivo), ("integrado", "aceptado_por_docente"))
        self.assertEqual(fila.resultado["decidido_por"], self.docente_id)
        self.assertTrue(Auditoria.objects.filter(accion="estudio.envio.aceptar", actor_id=self.docente_id).exists())
        despues = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/{self.d}/"))
        self.assertEqual((despues["pendientes_decision"], despues["alumnos"][0]["pendientes_decision"], despues["alumnos"][0]["decisiones"]), (0, 0, []))
        self.assertEqual(len(self.eventos("estudio.trabajo.integrado.v1")), 2)      # el envío y la decisión
        # ya se decidió: no se decide dos veces
        again = self.api.post(f"{BASE}/docente/asignaciones/{self.d}/decisiones/", {"alumno_id": self.estudiante_id, "secuencia": 1, "decision": "descartar"}, format="json")
        self.assertEqual((again.status_code, again.json()["codigo"]), (400, "datos_invalidos"))

    def test_aceptar_una_respuesta_la_aplica_y_la_califica(self):
        evento = {"secuencia": 1, "tipo": "study.answer.submitted", "ocurrido_en": T0 - MIN,
                  "carga": {"asignacion_id": self.d, "objeto_ref": "l1-activity", "intento_numero": 1, "pregunta_ref": "l1-act-q1",
                            "respuesta": CORRECTAS["l1-act-q1"], "secuencia_respuesta": 1}}
        with self.reloj(T0 + 30 * MIN):
            self.ok([evento])
        with self.biblioteca_que_califica(), self.reloj(T0 + 40 * MIN):
            self.json_ok(self.api.post(f"{BASE}/docente/asignaciones/{self.d}/decisiones/", {
                "alumno_id": self.estudiante_id, "secuencia": 1, "decision": "aceptar"}, format="json"))
        practica = m.Practica.objects.get()
        self.assertEqual((practica.aciertos, practica.origen, practica.respuestas[0]["veredicto"]["correcta"]), (1, "cola", True))
        self.assertNotIn("respuesta", m.Sincronizacion.objects.get().carga)            # después de decidir queda un resumen, sin el contenido (BR-127)

    def test_descartar_lo_deja_rechazado_sin_aplicar_nada_y_con_constancia(self):
        with self.reloj(T0 + 20 * MIN):
            self.ok([self.evento(1, T0 - MIN, BLOQUES_L1[:3])])
        r = self.json_ok(self.api.post(f"{BASE}/docente/asignaciones/{self.d}/decisiones/", {
            "alumno_id": self.estudiante_id, "secuencia": 1, "decision": "descartar"}, format="json"))
        self.assertEqual((r["estado"], r["motivo"]), ("rechazado", "descartado_por_docente"))
        self.assertEqual(m.Tarea.objects.count(), 0)
        self.assertEqual(m.Sincronizacion.objects.get().estado, "rechazado")
        self.assertTrue(Auditoria.objects.filter(accion="estudio.envio.descartar").exists())
        self.assertEqual(self.ver("/sync/status/", emisor_id=EMISOR).json()["pendientes_decision"], [])

    def test_aceptar_algo_que_ya_no_se_puede_aplicar_lo_deja_rechazado_con_su_causa(self):
        completada = {"secuencia": 1, "tipo": "study.lesson.completed", "ocurrido_en": T0 - MIN, "carga": {"asignacion_id": self.d}}
        with self.reloj(T0 + 20 * MIN):
            self.assertEqual(self.estados(self.ok([completada])), [(1, "pendiente_decision", "fuera_de_gracia")])
        r = self.json_ok(self.api.post(f"{BASE}/docente/asignaciones/{self.d}/decisiones/", {
            "alumno_id": self.estudiante_id, "secuencia": 1, "decision": "aceptar"}, format="json"))
        self.assertEqual((r["estado"], r["motivo"]), ("rechazado", "bloques_pendientes"))      # faltaban bloques: no se completa por decreto
        self.assertEqual(m.Sincronizacion.objects.get().estado, "rechazado")

    def test_decisiones_mal_pedidas_o_de_quien_no_es_titular(self):
        with self.reloj(T0 + 20 * MIN):
            self.ok([self.evento(1, T0 - MIN)])
        url = f"{BASE}/docente/asignaciones/{self.d}/decisiones/"
        casos = [({"alumno_id": self.estudiante_id, "secuencia": 1}, 400), ({"alumno_id": self.estudiante_id, "secuencia": 1, "decision": "quizas"}, 400),
                 ({"secuencia": 1, "decision": "aceptar"}, 400), ({"alumno_id": self.estudiante_id, "decision": "aceptar"}, 400),
                 ({"alumno_id": self.estudiante_id, "secuencia": 99, "decision": "aceptar"}, 404)]
        for cuerpo, esperado in casos:
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(self.api.post(url, cuerpo, format="json").status_code, esperado)
        ajena = self.crear_asignacion(grupo_id=self.otro_grupo["id"], actor="prof-ajeno", fecha_limite=T0, plazo="endurecido")
        r = self.docente.post(f"{BASE}/docente/asignaciones/{ajena['id']}/decisiones/", {"alumno_id": "x", "secuencia": 1, "decision": "aceptar"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(juan.post(url, {"alumno_id": self.estudiante_id, "secuencia": 1, "decision": "aceptar"}, format="json").status_code, 403)

    def test_una_asignacion_cerrada_a_mano_rechaza_lo_capturado_despues_y_acepta_lo_capturado_antes(self):
        b = self.crear_asignacion(fecha_limite=T0 * 2)             # plazo blando: la fecha no cierra; cierra el profesor
        with self.reloj(T0):
            self.api.post(f"{BASE}/docente/asignaciones/{b['id']}/cerrar/", {}, format="json")
        cierre = m.Asignacion.objects.get(pk=b["id"]).cerrada_en

        def evento(sec: int, capturado: int) -> dict:
            return {"secuencia": sec, "tipo": "study.block.viewed", "ocurrido_en": capturado,
                    "carga": {"asignacion_id": b["id"], "bloques_vistos": BLOQUES_L1[:1]}}

        with self.reloj(cierre + 2 * MIN):
            r = self.ok([evento(1, cierre - 5_000), evento(2, cierre + 1_000)])
        self.assertEqual(self.estados(r), [(1, "integrado", ""), (2, "rechazado", "asignacion_cerrada")])
        with self.reloj(cierre + 30 * MIN):
            r = self.ok([evento(3, cierre - 5_000)])
        self.assertEqual(self.estados(r), [(3, "pendiente_decision", "fuera_de_gracia")])
