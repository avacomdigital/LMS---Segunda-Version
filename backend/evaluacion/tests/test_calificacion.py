"""
Calificación y revisión docente (CAP-060, CAP-062, FUN-112, FUN-113; BR-068, BR-069, BR-070; DEC-032; INV-005, INV-019; TST-037, TST-038): UNA
llamada por lote a la biblioteca, escala interna de 0 a 100, los reactivos abiertos esperan al profesor y el alumno no ve su nota hasta que se libera.
Con el examen de banco fijo (las doce preguntas, de los seis tipos) para que cada tipo pase por el calificador de referencia.
"""
from __future__ import annotations

import time

from audit import models as maudit

from .base import BASE, FuenteQueCalifica, BaseEvaluacion, respuesta_correcta, respuesta_incorrecta


class _ConExamenCompleto(BaseEvaluacion):
    def setUp(self):
        super().setUp()
        contexto = self.examen_de_banco_fijo()
        contexto.__enter__()
        self.addCleanup(contexto.__exit__, None, None, None)

    def presentar(self, resultados: str = "tras_liberar", responder_abiertas: bool = True, bien: bool = True, **extra):
        """Juan abre el examen completo (12 preguntas), responde y entrega. Devuelve (asignación, intento_id, referencias, tipos)."""
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados=resultados, **extra)
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        f = respuesta_correcta if bien else respuesta_incorrecta
        refs = [r for r in tipos if responder_abiertas or tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, f(ref)) for n, ref in enumerate(refs)])
        self.entregar(i, confirmar=True)
        return a, i, refs, tipos

    def porcentaje_esperado(self, i: str, ganados: dict[str, float]) -> float:
        puntos = self.fila(i).armado_meta["puntos"]
        return round(100.0 * sum(ganados.values()) / sum(puntos.values()), 4)


class AutocalificacionTests(_ConExamenCompleto):
    def test_tst_037_se_califica_con_una_sola_llamada_por_lote_y_en_menos_de_dos_segundos(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(tipos)])
        version = self.fila(i).curso_version
        empezo = time.perf_counter()
        self.entregar(i, confirmar=True)
        self.assertLess(time.perf_counter() - empezo, 2.0)
        self.assertEqual(len(FuenteQueCalifica.lotes), 1)                               # UNA llamada por lote, no una por reactivo
        self.assertEqual(sorted(FuenteQueCalifica.lotes[0]), sorted(tipos))             # las doce, juntas
        self.assertEqual(FuenteQueCalifica.versiones, [version])                        # con la versión del intento, nunca otra
        self.assertEqual(FuenteQueCalifica.sueltas, [])
        self.entregar(i, confirmar=True)                                                # idempotente: ni una segunda llamada
        self.assertEqual(len(FuenteQueCalifica.lotes), 1)

    def test_lo_cerrado_se_califica_solo_y_la_nota_va_de_0_a_100(self):
        a, i, refs, tipos = self.presentar(responder_abiertas=False)
        fila = self.fila(i)
        puntos = fila.armado_meta["puntos"]
        self.assertEqual(fila.estado, "calificado")
        self.assertEqual(fila.calificado_por, "sistema")
        self.assertEqual(fila.porcentaje, self.porcentaje_esperado(i, {r: puntos[r] for r in refs}))
        self.assertGreater(fila.porcentaje, 0)
        self.assertLess(fila.porcentaje, 100)                                           # las abiertas sin responder suman cero sobre su máximo
        self.assertFalse(fila.requiere_revision)
        self.assertTrue(all(r["veredicto"]["correcta"] is True for r in fila.respuestas))
        self.assertEqual(self.eventos("evaluacion.autocalificacion.completada.v1", "evaluacion.intento_calificado.v1"),
                         ["evaluacion.autocalificacion.completada.v1", "evaluacion.intento_calificado.v1"])

    def test_todo_mal_es_cero_y_sigue_siendo_una_calificacion_valida(self):
        a, i, refs, tipos = self.presentar(responder_abiertas=False, bien=False)
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.porcentaje), ("calificado", 0.0))
        self.assertTrue(all(r["veredicto"]["correcta"] is False for r in fila.respuestas))

    def test_el_examen_sin_responder_nada_tambien_se_califica_en_cero(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.entregar(i, confirmar=True)
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.porcentaje, fila.respuestas), ("calificado", 0.0, []))
        self.assertEqual(FuenteQueCalifica.lotes, [])                                   # no hay nada que mandar a calificar

    def test_la_nota_no_se_redondea_a_entero_antes_de_guardar(self):
        a, i, refs, tipos = self.presentar(responder_abiertas=False)
        porcentaje = self.fila(i).porcentaje
        self.assertNotEqual(porcentaje, round(porcentaje))                              # 10 de 12 reactivos: 83.3333…, no 83
        self.assertEqual(porcentaje, round(porcentaje, 4))


class RevisionDocenteTests(_ConExamenCompleto):
    def setUp(self):
        super().setUp()
        self.a, self.i, self.refs, self.tipos = self.presentar()
        self.abiertas = [r for r in self.refs if self.tipos[r] == "open"]
        self.puntos = self.fila(self.i).armado_meta["puntos"]

    def test_tst_038_las_abiertas_dejan_el_intento_en_revision_y_la_nota_no_es_definitiva(self):
        fila = self.fila(self.i)
        self.assertEqual((fila.estado, fila.requiere_revision, fila.sin_calificar, fila.calificado_por), ("en_revision_docente", True, 2, ""))
        self.assertEqual(self.eventos("evaluacion.revision.solicitada.v1"), ["evaluacion.revision.solicitada.v1"])
        self.assertEqual(self.eventos("evaluacion.intento_calificado.v1"), [])
        panel = self.ver(f"/asignaciones/{self.a['id']}/panel/")["filas"][0]
        self.assertEqual((panel["estado"], panel["requiere_revision"]), ("en_revision_docente", True))
        resultados = self.ver(f"/asignaciones/{self.a['id']}/resultados/")["filas"][0]
        self.assertEqual((resultados["estado"], resultados["definitivo"], resultados["aprobado"]), ("en_revision_docente", False, None))

    def test_el_profesor_ve_lo_mismo_que_vio_el_alumno_con_su_respuesta_y_el_veredicto(self):
        revision = self.ver(f"/intentos/{self.i}/revision/")
        self.assertEqual((revision["intento"]["estado"], sorted(revision["intento"]["pendientes"])), ("en_revision_docente", sorted(self.abiertas)))
        self.assertEqual([f["pregunta"]["pregunta_ref"] for f in revision["filas"]], list(self.fila(self.i).armado))
        por_ref = {f["pregunta"]["pregunta_ref"]: f for f in revision["filas"]}
        for ref in self.abiertas:
            self.assertEqual(por_ref[ref]["respuesta"], respuesta_correcta(ref))
            self.assertTrue(por_ref[ref]["veredicto"]["requiere_correccion_manual"])
        cerrada = next(r for r in self.refs if self.tipos[r] != "open")
        self.assertTrue(por_ref[cerrada]["veredicto"]["correcta"])
        self.assertTrue(all(f["respondida"] for f in revision["filas"]))

    def test_no_se_publica_con_reactivos_sin_puntuar(self):
        r = self.accion(f"/intentos/{self.i}/publicar/", esperado=409)
        self.assertEqual((r["codigo"], sorted(r["pendientes"])), ("reactivos_pendientes", sorted(self.abiertas)))
        self.accion(f"/intentos/{self.i}/respuestas/{self.abiertas[0]}/puntuar/", {"puntaje": self.puntos[self.abiertas[0]]})
        r = self.accion(f"/intentos/{self.i}/publicar/", esperado=409)
        self.assertEqual(r["pendientes"], [self.abiertas[1]])

    def test_puntuar_y_publicar_cierra_el_ciclo_con_el_evaluador_a_la_vista(self):
        primera, segunda = self.abiertas
        p1 = self.accion(f"/intentos/{self.i}/respuestas/{primera}/puntuar/", {"puntaje": self.puntos[primera], "comentario": "Completa"})
        self.assertEqual((p1["puntaje"], p1["pendientes"]), (self.puntos[primera], [segunda]))
        self.accion(f"/intentos/{self.i}/respuestas/{segunda}/puntuar/", {"puntaje": self.puntos[segunda] / 2})
        publicado = self.accion(f"/intentos/{self.i}/publicar/")
        self.assertEqual((publicado["estado"], publicado["calificado_por"]), ("calificado", self.docente_id))     # INV-019: una persona
        esperado = self.porcentaje_esperado(self.i, {**{r: self.puntos[r] for r in self.refs if r != segunda}, segunda: self.puntos[segunda] / 2})
        fila = self.fila(self.i)
        self.assertEqual((fila.estado, fila.porcentaje, fila.requiere_revision, fila.calificado_por), ("calificado", esperado, False, self.docente_id))
        self.assertEqual(fila.respuestas[self.refs.index(primera)]["revision"]["comentario"], "Completa")
        self.assertEqual(self.eventos("evaluacion.revision_publicada.v1", "evaluacion.intento_calificado.v1"),
                         ["evaluacion.revision_publicada.v1", "evaluacion.intento_calificado.v1"])
        self.assertTrue(maudit.Bitacora.objects.filter(accion="evaluacion.revision.publicada", objeto_id=self.i).exists())
        self.accion(f"/intentos/{self.i}/publicar/", esperado=409)                       # ya está calificado

    def test_el_puntaje_se_valida_y_solo_se_puntua_lo_que_la_biblioteca_dejo_para_el_profesor(self):
        ref = self.abiertas[0]
        maximo = self.puntos[ref]
        for cuerpo in ({}, {"puntaje": None}, {"puntaje": -1}, {"puntaje": maximo + 1}):
            r = self.accion(f"/intentos/{self.i}/respuestas/{ref}/puntuar/", cuerpo, esperado=400)
            self.assertEqual(r["codigo"], "datos_invalidos", cuerpo)
        cerrada = next(r for r in self.refs if self.tipos[r] != "open")
        r = self.accion(f"/intentos/{self.i}/respuestas/{cerrada}/puntuar/", {"puntaje": 0}, esperado=400)
        self.assertIn("se califica solo", r["detail"])
        self.accion(f"/intentos/{self.i}/respuestas/l3-q-que-no-existe/puntuar/", {"puntaje": 0}, esperado=404)
        self.assertEqual(self.fila(self.i).estado, "en_revision_docente")

    def test_br_070_cambiar_un_puntaje_asentado_exige_motivo_y_deja_el_valor_anterior_y_el_nuevo(self):
        primera, segunda = self.abiertas
        self.accion(f"/intentos/{self.i}/respuestas/{primera}/puntuar/", {"puntaje": self.puntos[primera]})
        self.accion(f"/intentos/{self.i}/respuestas/{segunda}/puntuar/", {"puntaje": self.puntos[segunda]})
        self.accion(f"/intentos/{self.i}/publicar/")
        antes = self.fila(self.i).porcentaje
        r = self.accion(f"/intentos/{self.i}/respuestas/{primera}/puntuar/", {"puntaje": 0}, esperado=400)
        self.assertIn("motivo", r["detail"])
        self.accion(f"/intentos/{self.i}/respuestas/{primera}/puntuar/", {"puntaje": 0, "motivo": "Copió el enunciado"})
        fila = self.fila(self.i)
        self.assertLess(fila.porcentaje, antes)
        self.assertEqual(fila.estado, "calificado")                                      # sigue calificado: la corrección no lo reabre
        asiento = maudit.Bitacora.objects.get(accion="calificacion.modificada", objeto_id=self.i)
        self.assertEqual((asiento.valor_anterior["puntaje"], asiento.valor_nuevo["puntaje"], asiento.motivo),
                         (self.puntos[primera], 0.0, "Copió el enunciado"))

    def test_no_se_puntua_un_intento_que_todavia_se_esta_presentando(self):
        b = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        j = self.abrir(b["id"])["intento"]["id"]
        ref = self.refs_del_examen(j)[0]
        self.accion(f"/intentos/{j}/respuestas/{ref}/puntuar/", {"puntaje": 1}, esperado=409)
        self.accion(f"/intentos/{j}/publicar/", esperado=409)

    def test_solo_el_profesor_revisa_el_alumno_no(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        for metodo, ruta, cuerpo in (("get", f"/intentos/{self.i}/revision/", None),
                                     ("post", f"/intentos/{self.i}/respuestas/{self.abiertas[0]}/puntuar/", {"puntaje": 1}),
                                     ("post", f"/intentos/{self.i}/publicar/", {}), ("post", f"/intentos/{self.i}/recalificar/", {})):
            r = getattr(alumno, metodo)(f"{BASE}{ruta}", **({"data": cuerpo, "format": "json"} if cuerpo is not None else {}))
            self.assertEqual(r.status_code, 403, (ruta, r.content))
        self.assertEqual(self.fila(self.i).estado, "en_revision_docente")


class BibliotecaCaidaTests(_ConExamenCompleto):
    """Sin biblioteca al entregar el intento queda `entregado` con la calificación pendiente y se resuelve después: el resultado es el mismo (INV-005)."""

    def entregar_sin_biblioteca(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="al_entregar")
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        refs = [r for r in tipos if tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(refs)])
        with self.biblioteca_caida():
            self.entregar(i, confirmar=True)
        return a, i, refs

    def test_el_intento_queda_entregado_con_la_calificacion_pendiente_y_nada_se_pierde(self):
        a, i, refs = self.entregar_sin_biblioteca()
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.calificacion_pendiente, fila.porcentaje, len(fila.respuestas)), ("entregado", True, None, len(refs)))
        self.assertTrue(all(r["veredicto"] is None for r in fila.respuestas))
        self.assertEqual(self.eventos("evaluacion.autocalificacion.completada.v1", "evaluacion.intento_calificado.v1"), [])
        self.assertEqual(self.eventos("evaluacion.intento_entregado.v1"), ["evaluacion.intento_entregado.v1"])

    def test_el_alumno_no_ve_una_nota_provisional_mientras_la_calificacion_esta_pendiente(self):
        a, i, _ = self.entregar_sin_biblioteca()
        r = self.api.get(f"{BASE}/intentos/{i}/resultado/", self.alumno())
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "resultados_no_liberados"))

    def test_recalificar_con_la_biblioteca_de_vuelta_completa_la_nota_una_sola_vez(self):
        a, i, refs = self.entregar_sin_biblioteca()
        with self.biblioteca_caida():
            con_caida = self.accion(f"/intentos/{i}/recalificar/")                     # sigue caída: no falla, sigue pendiente
        self.assertEqual((con_caida["estado"], con_caida["calificacion_pendiente"]), ("entregado", True))
        listo = self.accion(f"/intentos/{i}/recalificar/")
        self.assertEqual((listo["estado"], listo["calificacion_pendiente"], listo["porcentaje"] > 0), ("calificado", False, True))
        self.assertEqual(len(FuenteQueCalifica.lotes), 1)
        otra = self.accion(f"/intentos/{i}/recalificar/")                              # INV-005: nada que volver a calificar
        self.assertEqual((otra["porcentaje"], len(FuenteQueCalifica.lotes)), (listo["porcentaje"], 1))
        self.assertEqual(len(self.eventos("evaluacion.intento_calificado.v1")), 1)
        resultado = self.api.get(f"{BASE}/intentos/{i}/resultado/", self.alumno())
        self.assertEqual(resultado.status_code, 200, resultado.content)

    def test_recalificar_solo_un_intento_entregado(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.accion(f"/intentos/{i}/recalificar/", esperado=409)


class ResultadoDelAlumnoTests(_ConExamenCompleto):
    """DEC-032: el alumno NUNCA ve su nota antes de que el profesor la publique, aunque ya esté calificada."""

    def resultado(self, i: str, esperado: int):
        r = self.api.get(f"{BASE}/intentos/{i}/resultado/", self.alumno())
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def test_tras_liberar_la_nota_no_aparece_hasta_que_el_profesor_libera(self):
        a, i, refs, _ = self.presentar(resultados="tras_liberar", responder_abiertas=False)
        self.assertEqual(self.fila(i).estado, "calificado")
        self.assertEqual(self.resultado(i, 403)["codigo"], "resultados_no_liberados")
        mias = self.api.get(f"{BASE}/mias/", {**self.alumno(), "todas": "1"}).json()
        self.assertFalse(mias["pendientes"][0]["mi_intento"]["resultado_disponible"] if mias["pendientes"] else False)
        self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        cuerpo = self.resultado(i, 200)
        self.assertEqual((cuerpo["porcentaje"], cuerpo["aprobacion_pct"], cuerpo["aprobado"]), (self.fila(i).porcentaje, 60, self.fila(i).porcentaje >= 60))
        self.assertEqual(len(cuerpo["detalle"]), 12)
        respondida = next(d for d in cuerpo["detalle"] if d["respondida"])
        self.assertTrue(respondida["correcta"])
        self.assertTrue(respondida["retroalimentacion"])                                # la retroalimentación llega con la nota, no antes
        omitida = next(d for d in cuerpo["detalle"] if not d["respondida"])
        self.assertEqual(omitida["puntaje"], 0.0)

    def test_al_entregar_la_nota_se_ve_de_inmediato(self):
        a, i, _, _ = self.presentar(resultados="al_entregar", responder_abiertas=False)
        self.assertEqual(self.resultado(i, 200)["porcentaje"], self.fila(i).porcentaje)

    def test_nunca_ni_siquiera_liberando(self):
        a, i, _, _ = self.presentar(resultados="nunca", responder_abiertas=False)
        self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        self.assertEqual(self.resultado(i, 403)["codigo"], "resultados_no_liberados")

    def test_con_reactivos_por_revisar_no_hay_resultado_parcial_ni_liberando(self):
        a, i, _, _ = self.presentar(resultados="al_entregar")                           # responde las abiertas: quedan en revisión
        self.assertEqual(self.fila(i).estado, "en_revision_docente")
        self.assertEqual(self.resultado(i, 403)["codigo"], "resultados_no_liberados")
        self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        self.assertEqual(self.resultado(i, 403)["codigo"], "resultados_no_liberados")

    def test_no_se_liberan_resultados_con_alumnos_presentando(self):
        a, i, _, _ = self.presentar(resultados="tras_liberar", responder_abiertas=False)
        otro, hw = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        self.abrir(a["id"], hw=hw, alumno_id=otro)                                       # Ana sigue presentando
        r = self.accion(f"/asignaciones/{a['id']}/liberar-resultados/", esperado=409)
        self.assertEqual(r["codigo"], "intentos_abiertos")
        self.resultado(i, 403)

    def test_el_resultado_es_del_alumno_dueno_del_intento_y_de_su_tableta(self):
        a, i, _, _ = self.presentar(resultados="al_entregar", responder_abiertas=False)
        otro, hw = self.alumno_con_tableta("Otro", "500001", capacidad="supervisado")
        self.assertEqual(self.api.get(f"{BASE}/intentos/{i}/resultado/", self.alumno(hw, otro)).status_code, 404)


class ResultadosDeLaAsignacionTests(_ConExamenCompleto):
    def entregar_tres(self) -> tuple[dict, list[str]]:
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="al_entregar")
        intentos = []
        gente = [(None, None, True), *[(*self.alumno_con_tableta(n, c, "supervisado"), b) for n, c, b in (("Ana", "A-100", False), ("Luis", "L-100", True))]]
        for alumno, hw, bien in gente:
            i = self.abrir(a["id"], hw=hw, alumno_id=alumno)["intento"]["id"]
            tipos = self.fila(i).armado_meta["tipos"]
            f = respuesta_correcta if bien else respuesta_incorrecta
            self.responder(i, [self.r(r, n + 1, f(r)) for n, r in enumerate(x for x in tipos if tipos[x] != "open")], hw=hw, alumno_id=alumno)
            self.entregar(i, hw=hw, alumno_id=alumno, confirmar=True)
            intentos.append(i)
        return a, intentos

    def test_con_menos_de_tres_entregas_no_hay_promedio_cmp_043(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.entregar(i, confirmar=True)
        r = self.ver(f"/asignaciones/{a['id']}/resultados/")
        self.assertEqual((r["datos_suficientes"], r["promedio_porcentaje"], r["filas"][0]["definitivo"]), (False, None, True))

    def test_con_tres_calificados_hay_promedio_y_cada_alumno_aprobado_o_no(self):
        a, intentos = self.entregar_tres()
        r = self.ver(f"/asignaciones/{a['id']}/resultados/")
        porcentajes = [self.fila(i).porcentaje for i in intentos]
        self.assertEqual((r["datos_suficientes"], r["promedio_porcentaje"]), (True, round(sum(porcentajes) / 3, 2)))
        por_alumno = {f["rotulo"]: f for f in r["filas"]}
        self.assertEqual(sorted(f["aprobado"] for f in r["filas"]), [False, True, True])
        self.assertTrue(all(f["definitivo"] for f in por_alumno.values()))
        self.assertEqual(r["aprobacion_pct"], 60)

    def test_el_profesor_ve_los_resultados_aunque_no_los_haya_liberado_y_el_alumno_no_ve_los_del_grupo(self):
        a, intentos = self.entregar_tres()
        self.assertIsNone(self.ver(f"/asignaciones/{a['id']}/resultados/")["liberados_en"])
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.get(f"{BASE}/asignaciones/{a['id']}/resultados/").status_code, 403)
