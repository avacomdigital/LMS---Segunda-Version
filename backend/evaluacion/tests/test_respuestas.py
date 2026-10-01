"""
Las respuestas de un intento por HTTP (FUN-110, FUN-111; BR-009, BR-071, BR-127, BR-138; INV-005, INV-013): cada una se guarda en cuanto se confirma,
las malas no tumban a las buenas (TST-036), el reenvío no duplica nada (TST-040) y la sesión de tableta más reciente prevalece (TST-027).
"""
from __future__ import annotations

from device_manager import models as m09

from .. import models as m
from .base import BASE, SEG, BaseEvaluacion, respuesta_correcta, respuesta_incorrecta


class GuardarRespuestasTests(BaseEvaluacion):
    def setUp(self):
        super().setUp()
        self.asignacion = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        self.i = self.abrir(self.asignacion["id"])["intento"]["id"]
        self.refs = self.refs_del_examen(self.i)

    def test_cada_respuesta_se_guarda_al_confirmarse_sin_esperar_la_entrega(self):
        acuse = self.responder(self.i, [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))])
        self.assertEqual((acuse["acuse"], acuse["aceptadas"], acuse["duplicadas"], acuse["rechazadas"]), (True, [self.refs[0]], [], []))
        self.assertEqual((acuse["intento"]["estado"], acuse["intento"]["respondidas"], acuse["intento"]["secuencia_maxima"]), ("en_curso", 1, 1))
        fila = self.fila(self.i)
        self.assertEqual((fila.estado, len(fila.respuestas), fila.respuestas[0]["respuesta"]), ("en_curso", 1, respuesta_correcta(self.refs[0])))
        self.assertEqual(self.preguntas(self.i)["respondidas"].keys(), {self.refs[0]})

    def test_br_127_el_evento_de_la_respuesta_no_lleva_su_contenido(self):
        self.responder(self.i, [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))])
        evento = m.EventoSalida.objects.get(tipo_evento="evaluacion.respuesta_registrada.v1")
        self.assertEqual((evento.carga["pregunta_ref"], evento.carga["secuencia"], evento.carga["intento_id"]), (self.refs[0], 1, self.i))
        self.assertNotIn("respuesta", evento.carga)
        self.assertNotIn("respuestas", evento.carga)

    def test_tst_036_una_respuesta_mala_no_tumba_a_las_buenas_y_se_rechaza_con_su_motivo(self):
        paquete = [
            self.r(self.refs[0], 1, respuesta_correcta(self.refs[0])),
            self.r("l3-q-que-no-existe", 2, {"value": True}),
            self.r(self.refs[1], 0, respuesta_correcta(self.refs[1])),                    # la secuencia empieza en 1
            self.r(self.refs[2], 3, {"zzz": 1}),                                          # claves que ningún tipo admite
            {"secuencia": 4, "respuesta": {"value": True}},                               # sin pregunta
            self.r(self.refs[3], 5, {}),                                                  # vacía
        ]
        acuse = self.responder(self.i, paquete)
        self.assertEqual(acuse["aceptadas"], [self.refs[0]])
        motivos = {x["pregunta_ref"]: x["motivo"] for x in acuse["rechazadas"]}
        self.assertEqual(len(acuse["rechazadas"]), 5)
        self.assertEqual(motivos["l3-q-que-no-existe"], "la pregunta no está en tu examen")
        self.assertIn("secuencia", motivos[self.refs[1]])
        self.assertIn("sobra: zzz", motivos[self.refs[2]])
        self.assertEqual(motivos[""], "falta pregunta_ref")
        self.assertIn("no vacío", motivos[self.refs[3]])
        self.assertEqual([r["pregunta_ref"] for r in self.fila(self.i).respuestas], [self.refs[0]])

    def test_tst_040_el_reenvio_exacto_no_duplica_nada_y_lo_acusa_igual(self):
        paquete = [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))]
        self.responder(self.i, paquete)
        otra_vez = self.responder(self.i, paquete)
        self.assertEqual((otra_vez["aceptadas"], otra_vez["duplicadas"]), ([], [self.refs[0]]))
        self.assertEqual(len(self.fila(self.i).respuestas), 1)
        self.assertEqual(len(self.eventos("evaluacion.respuesta_registrada.v1")), 1)
        self.assertEqual(len(self.eventos("evaluacion.respuesta_deduplicada.v1")), 1)

    def test_una_secuencia_mayor_sustituye_y_lo_anterior_queda_en_el_historial(self):
        ref = self.refs[0]
        self.responder(self.i, [self.r(ref, 1, respuesta_incorrecta(ref))])
        acuse = self.responder(self.i, [self.r(ref, 2, respuesta_correcta(ref))])
        self.assertEqual(acuse["aceptadas"], [ref])
        vigente = self.fila(self.i).respuestas[0]
        self.assertEqual((vigente["respuesta"], vigente["secuencia"]), (respuesta_correcta(ref), 2))
        self.assertEqual([(h["respuesta"], h["motivo"]) for h in vigente["historial"]], [(respuesta_incorrecta(ref), "reemplazada")])
        self.assertEqual(self.fila(self.i).secuencia_maxima, 2)

    def test_una_secuencia_menor_que_llega_tarde_no_pisa_a_la_vigente_y_deja_incidente(self):
        ref = self.refs[0]
        self.responder(self.i, [self.r(ref, 3, respuesta_correcta(ref))])
        acuse = self.responder(self.i, [self.r(ref, 2, respuesta_incorrecta(ref))])
        self.assertEqual((acuse["aceptadas"], acuse["superadas"]), ([], [ref]))
        vigente = self.fila(self.i).respuestas[0]
        self.assertEqual((vigente["respuesta"], vigente["secuencia"]), (respuesta_correcta(ref), 3))
        self.assertEqual(vigente["historial"][-1]["motivo"], "superada")
        self.assertIn("respuesta_tardia", self.incidentes(self.i))
        # reenviar el mismo paquete tardío no repite el incidente (INV-005)
        self.responder(self.i, [self.r(ref, 2, respuesta_incorrecta(ref))])
        self.assertEqual(self.incidentes(self.i).count("respuesta_tardia"), 1)

    def test_dos_cambios_de_la_misma_pregunta_en_un_vaciado_de_cola_dejan_el_ultimo_aunque_lleguen_desordenados(self):
        ref = self.refs[0]
        acuse = self.responder(self.i, [self.r(ref, 7, respuesta_correcta(ref)), self.r(ref, 5, respuesta_incorrecta(ref))], origen="cola")
        self.assertEqual(acuse["aceptadas"], [ref, ref])                              # la 5 entra primero y la 7 la sustituye
        vigente = self.fila(self.i).respuestas[0]
        self.assertEqual((vigente["secuencia"], vigente["respuesta"], vigente["origen"]), (7, respuesta_correcta(ref), "cola"))
        self.assertEqual(len(self.fila(self.i).respuestas), 1)

    def test_br_138_la_sesion_mas_reciente_prevalece_aunque_su_secuencia_sea_menor(self):
        ref = self.refs[0]
        self.responder(self.i, [self.r(ref, 9, respuesta_incorrecta(ref))])             # la tableta de Juan lleva 9 cambios
        self.avanzar(seg=5)
        self.registrar("hw-laptop", "Laptop", capacidad="supervisado")
        self.abrir(self.asignacion["id"], hw="hw-laptop")                              # sigue en otra: sesión nueva
        acuse = self.responder(self.i, [self.r(ref, 1, respuesta_correcta(ref))], hw="hw-laptop")
        self.assertEqual((acuse["aceptadas"], acuse["superadas"]), ([ref], []))
        vigente = self.fila(self.i).respuestas[0]
        self.assertEqual((vigente["respuesta"], vigente["historial"][-1]["motivo"]), (respuesta_correcta(ref), "reemplazada"))

    def test_escribir_cuenta_como_senal_y_evita_la_pausa(self):
        self.avanzar(seg=25)
        self.responder(self.i, [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))])
        self.avanzar(seg=25)                                                           # 50 s desde el último latido, 25 desde que escribió
        self.assertEqual(self.estado(self.i)["intento"]["estado"], "en_curso")
        self.assertEqual(self.incidentes(self.i), [])

    def test_sin_escribir_ni_latir_la_misma_espera_si_suspende(self):
        self.avanzar(seg=50)
        self.assertEqual(self.estado(self.i)["intento"]["estado"], "pausado_desconexion")

    def test_la_pregunta_actual_se_guarda_si_es_del_examen_y_se_ignora_si_no(self):
        self.responder(self.i, [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))], pregunta_actual=self.refs[2])
        self.assertEqual(self.fila(self.i).pregunta_actual, self.refs[2])
        self.responder(self.i, [self.r(self.refs[1], 2, respuesta_correcta(self.refs[1]))], pregunta_actual="l3-q-ajena")
        self.assertEqual(self.fila(self.i).pregunta_actual, self.refs[2])

    def test_el_origen_cola_queda_registrado_y_uno_desconocido_se_rechaza(self):
        self.responder(self.i, [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))], origen="cola")
        self.assertEqual(self.fila(self.i).respuestas[0]["origen"], "cola")
        r = self.api.post(f"{BASE}/intentos/{self.i}/respuestas/", {**self.alumno(), "origen": "telepatia", "respuestas": [
            self.r(self.refs[1], 2, respuesta_correcta(self.refs[1]))]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))

    def test_la_peticion_se_valida(self):
        url = f"{BASE}/intentos/{self.i}/respuestas/"
        for cuerpo in ({**self.alumno()}, {**self.alumno(), "respuestas": []}, {**self.alumno(), "respuestas": "hola"}):
            r = self.api.post(url, cuerpo, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"), cuerpo)
        demasiadas = [self.r(self.refs[0], n + 1, respuesta_correcta(self.refs[0])) for n in range(201)]
        r = self.api.post(url, {**self.alumno(), "respuestas": demasiadas}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertEqual(self.fila(self.i).respuestas, [])

    def test_quien_escribe_debe_ser_el_alumno_y_una_tableta_del_intento(self):
        url = f"{BASE}/intentos/{self.i}/respuestas/"
        cuerpo = [self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))]
        r = self.api.post(url, {"alumno_id": self.estudiante_id, "respuestas": cuerpo}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))
        self.registrar("hw-intrusa", "Intrusa", capacidad="supervisado")
        r = self.api.post(url, {**self.alumno("hw-intrusa"), "respuestas": cuerpo}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_ajeno"))
        otro, hw = self.alumno_con_tableta("Otro", "500001", capacidad="supervisado")
        r = self.api.post(url, {**self.alumno(hw, otro), "respuestas": cuerpo}, format="json")
        self.assertEqual(r.status_code, 404)                                           # el intento es de Juan: no se revela
        self.assertEqual(self.fila(self.i).respuestas, [])

    def test_un_intento_anulado_no_admite_respuestas(self):
        self.entregar(self.i, confirmar=True)                                           # no se anula lo que sigue en curso: primero se entrega
        self.accion(f"/intentos/{self.i}/anular/", {"motivo": "Se detectó un problema"})
        r = self.api.post(f"{BASE}/intentos/{self.i}/respuestas/", {**self.alumno(), "respuestas": [
            self.r(self.refs[0], 1, respuesta_correcta(self.refs[0]))]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "intento_cerrado"))


class FormaDeLasRespuestasTests(BaseEvaluacion):
    """Con el examen de banco fijo (las doce preguntas, de los seis tipos) cada tipo admite SU forma y sólo esa."""

    def test_la_respuesta_se_guarda_tal_como_llego_sin_que_el_nodo_la_interprete(self):
        with self.examen_de_banco_fijo():
            a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
            i = self.abrir(a["id"])["intento"]["id"]
            tipos = self.fila(i).armado_meta["tipos"]
            self.assertEqual(sorted(set(tipos.values())), ["fill_blanks", "matching", "multiple_choice", "open", "ordering", "true_false"])
            abierta = next(ref for ref, tipo in tipos.items() if tipo == "open")
            texto = {"text": "  Porque al enfriarse el gas se contrae.  " + chr(10) + "(sin recortar)"}
            self.responder(i, [self.r(abierta, 1, texto)])
            self.assertEqual(self.fila(i).respuestas[0]["respuesta"], texto)

    def test_cada_tipo_rechaza_la_forma_de_otro(self):
        with self.examen_de_banco_fijo():
            a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
            i = self.abrir(a["id"])["intento"]["id"]
            tipos = self.fila(i).armado_meta["tipos"]
            por_tipo = {tipo: next(ref for ref, t in tipos.items() if t == tipo) for tipo in set(tipos.values())}
            equivocada = {"multiple_choice": {"value": True}, "true_false": {"selectedOptionIds": ["a"]}, "fill_blanks": {"text": "x"},
                          "matching": {"order": ["a"]}, "ordering": {"pairs": []}, "open": {"value": True}}
            paquete = [self.r(ref, n + 1, equivocada[tipo]) for n, (tipo, ref) in enumerate(sorted(por_tipo.items()))]
            acuse = self.responder(i, paquete)
            self.assertEqual((acuse["aceptadas"], len(acuse["rechazadas"])), ([], 6))
            correctas = [self.r(ref, 10 + n, respuesta_correcta(ref)) for n, ref in enumerate(sorted(por_tipo.values()))]
            self.assertEqual(len(self.responder(i, correctas)["aceptadas"]), 6)


class ReanudacionTests(BaseEvaluacion):
    """BR-071: lo capturado antes de una pausa llega después y no se pierde; el alumno retoma donde iba."""

    def test_la_cola_de_una_desconexion_larga_entra_completa_y_en_orden_al_volver(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 900})
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.latir_hasta(i, 40)
        capturadas = self.t
        self.avanzar(minutos=3)                                                        # se cayó la red tres minutos
        cola = [self.r(ref, n + 1, respuesta_correcta(ref), capturada_en=capturadas + (n + 1) * 10 * SEG) for n, ref in enumerate(refs)]
        acuse = self.responder(i, cola, origen="cola")
        self.assertEqual(acuse["aceptadas"], refs)
        fila = self.fila(i)
        self.assertEqual((fila.estado, len(fila.respuestas)), ("pausado_desconexion", len(refs)))     # esperan al profesor, pero no se pierden
        self.assertEqual(fila.consumido_ms, 40 * SEG)                                                  # el tiempo sin red no consumió reloj
        self.assertIn("respuesta_tardia", self.incidentes(i))
        reactivado = self.accion(f"/intentos/{i}/reactivar/")
        self.assertEqual(reactivado["estado"], "en_curso")
        self.entregar(i)                                                                # nada que confirmar: respondió todo
        self.assertEqual(self.estado(i)["intento"]["respondidas"], len(refs))

    def test_las_respuestas_de_la_cola_no_pisan_lo_que_se_respondio_despues_desde_el_mismo_aparato(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        ref = self.refs_del_examen(i)[0]
        self.responder(i, [self.r(ref, 4, respuesta_correcta(ref))])
        acuse = self.responder(i, [self.r(ref, 3, respuesta_incorrecta(ref))], origen="cola")      # la cola vieja llega después
        self.assertEqual(acuse["superadas"], [ref])
        self.assertEqual(self.fila(i).respuestas[0]["respuesta"], respuesta_correcta(ref))

    def test_la_sesion_de_la_tableta_anterior_queda_cerrada_por_relevo_y_sus_respuestas_siguen_ahi(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]))])
        self.avanzar(seg=5)
        self.registrar("hw-laptop", "Laptop", capacidad="supervisado")
        self.abrir(a["id"], hw="hw-laptop")
        self.responder(i, [self.r(refs[1], 1, respuesta_correcta(refs[1]))], hw="hw-laptop")
        fila = self.fila(i)
        self.assertEqual({r["pregunta_ref"] for r in fila.respuestas}, {refs[0], refs[1]})
        self.assertEqual(len({r["sesion_ref"] for r in fila.respuestas}), 2)             # cada respuesta recuerda desde qué sesión se escribió
        self.assertEqual(m09.DimSesionAlumno.objects.get(pk=fila.sesiones[0]["sesion_ref"]).motivo_cierre, "relevo")
