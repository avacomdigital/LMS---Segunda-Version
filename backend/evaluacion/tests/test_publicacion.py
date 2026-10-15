"""
RF-004 (el profesor decide cuándo se muestran los resultados): calificar y publicar son dos cosas distintas. Las cuatro políticas (manual, inmediata,
al finalizar el grupo, programada) más `nunca`; el valor predeterminado seguro (manual) aunque la biblioteca sugiera otra cosa; la publicación por
alumno; quién publicó y cuándo; el reloj del NODO para lo programado (lo persiste el barrido y lo aplica la lectura perezosa); y que ningún camino del
API deja ver una nota no publicada ni la de otro alumno. Con el examen de banco fijo (doce preguntas, de los seis tipos: las abiertas piden revisión).
"""
from __future__ import annotations

from audit import models as maudit

from .. import models as m
from ..aplicacion import barrido
from ..infraestructura.contenedor import servicios
from .base import BASE, MIN, respuesta_correcta
from .test_calificacion import _ConExamenCompleto


class _ConPublicacion(_ConExamenCompleto):
    def resultado(self, i: str, esperado: int, hw: str | None = None, alumno_id: str | None = None) -> dict:
        r = self.api.get(f"{BASE}/intentos/{i}/resultado/", self.alumno(hw, alumno_id))
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def presentar_otro(self, asignacion_id: str, alumno: str, hw: str, responder_abiertas: bool = False) -> str:
        """Otro alumno del grupo (ya inscrito, con su tableta) presenta y entrega. Devuelve su intento."""
        i = self.abrir(asignacion_id, hw=hw, alumno_id=alumno)["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        refs = [r for r in tipos if responder_abiertas or tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(refs)], hw=hw, alumno_id=alumno)
        self.entregar(i, hw=hw, alumno_id=alumno, confirmar=True)
        return i

    def mia(self, asignacion_id: str, hw: str | None = None, alumno_id: str | None = None) -> dict:
        mias = self.api.get(f"{BASE}/mias/", {**self.alumno(hw, alumno_id), "todas": "1"}).json()
        return next(e for e in mias["pendientes"] + mias["recientes"] if e["id"] == asignacion_id)


class PoliticaPorDefectoTests(_ConPublicacion):
    def test_sin_eleccion_del_profesor_la_politica_es_manual_aunque_la_biblioteca_sugiera_inmediata(self):
        # El examen de banco fijo conserva `showResults = after_teacher_release`; aquí se simula una biblioteca que sugiere `after_submit`.
        from unittest import mock
        from ..infraestructura.contenido import ContenidoEvaluacion
        original = ContenidoEvaluacion.examen

        def sugiere_inmediata(self_, fuente, curso_ref, objeto_ref):
            ficha = original(self_, fuente, curso_ref, objeto_ref)
            return {**ficha, "ajustes": {**ficha["ajustes"], "mostrar_resultados": "al_entregar"}}

        with mock.patch.object(ContenidoEvaluacion, "examen", sugiere_inmediata):
            a = self.crear_asignacion("supervisado")
        self.assertEqual((a["resultados"], a["publicar_en"], a["liberados_en"], a["liberados_por"]), ("tras_liberar", None, None, ""))
        self.assertEqual(a["ajustes"]["mostrar_resultados"], "al_entregar")                   # la sugerencia queda como dato, no decide

    def test_la_politica_institucional_cambia_el_valor_por_defecto(self):
        with self.settings(AVACOM_EVAL_RESULTADOS_POR_DEFECTO="al_finalizar_grupo"):
            a = self.crear_asignacion("supervisado")
        self.assertEqual(a["resultados"], "al_finalizar_grupo")

    def test_los_nombres_del_documento_de_requisitos_se_aceptan_como_sinonimos(self):
        self.assertEqual(self.crear_asignacion("supervisado", resultados="inmediata")["resultados"], "al_entregar")
        self.assertEqual(self.crear_asignacion("supervisado", resultados="manual")["resultados"], "tras_liberar")
        self.assertEqual(self.crear_asignacion("supervisado", resultados="al_finalizar_grupo")["resultados"], "al_finalizar_grupo")
        self.assertEqual(self.crear_asignacion("supervisado", esperado=400, resultados="cuando_quiera")["codigo"], "datos_invalidos")

    def test_programada_exige_fecha_y_en_el_futuro(self):
        self.assertIn("publicar_en", self.crear_asignacion("supervisado", esperado=400, resultados="programada")["detail"])
        self.assertIn("futuro", self.crear_asignacion("supervisado", esperado=400, resultados="programada", publicar_en=self.t - MIN)["detail"])
        a = self.crear_asignacion("supervisado", resultados="programada", publicar_en=self.t + 60 * MIN)
        self.assertEqual((a["resultados"], a["publicar_en"]), ("programada", self.t + 60 * MIN))
        self.assertEqual(self.eventos("evaluacion.resultados_configurados.v1"), ["evaluacion.resultados_configurados.v1"])


class PublicacionManualTests(_ConPublicacion):
    def test_el_alumno_no_ve_la_nota_antes_de_la_autorizacion_y_el_profesor_si(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        self.assertEqual(self.fila(i).estado, "calificado")                                   # calificado ≠ publicado
        self.assertEqual(self.resultado(i, 403)["codigo"], "resultados_no_liberados")
        mia = self.mia(a["id"])
        self.assertEqual((mia["mi_intento"]["estado"], mia["mi_intento"]["resultado_disponible"], mia["resultados"]), ("calificado", False, "tras_liberar"))
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        self.assertEqual((panel["totales"]["listos_para_publicar"], panel["totales"]["publicados"]), (1, 0))
        self.assertIsNotNone(panel["filas"][0]["porcentaje"])                                 # el profesor ve la nota interna
        self.assertFalse(panel["filas"][0]["resultado_publicado"])
        liberada = self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        self.assertEqual((liberada["liberados_en"], liberada["liberados_por"]), (self.t, self.docente_id))
        self.resultado(i, 200)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/panel/")["totales"]["publicados"], 1)
        asiento = maudit.Bitacora.objects.get(accion="evaluacion.resultados.liberados", objeto_id=a["id"])
        self.assertEqual((asiento.usuario_id, asiento.valor_nuevo["origen"]), (self.docente_id, "manual"))

    def test_la_entrega_dice_que_sigue_sin_revelar_la_nota(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="manual")
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        refs = [r for r in tipos if tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(refs)])
        e = self.entregar(i, confirmar=True)
        self.assertEqual((e["que_sigue"]["codigo"], e["resultado_disponible"], e["resultados"]), ("resultado_al_liberar", False, "tras_liberar"))
        self.assertNotIn("porcentaje", e)
        self.assertNotIn("puntaje", e)


class PublicacionInmediataTests(_ConPublicacion):
    def test_inmediata_se_ve_al_entregar_solo_si_esta_completamente_calificado(self):
        a, i, _, _ = self.presentar(resultados="inmediata", responder_abiertas=False)
        self.assertEqual(self.resultado(i, 200)["porcentaje"], self.fila(i).porcentaje)
        b, j, _, _ = self.presentar(resultados="inmediata", responder_abiertas=True)        # con abiertas por revisar: nada parcial
        self.assertEqual(self.fila(j).estado, "en_revision_docente")
        self.assertEqual(self.resultado(j, 403)["codigo"], "resultados_no_liberados")
        for ref in [r for r, t in self.fila(j).armado_meta["tipos"].items() if t == "open"]:
            self.accion(f"/intentos/{j}/respuestas/{ref}/puntuar/", {"puntaje": 1})
        publicado = self.accion(f"/intentos/{j}/publicar/")
        self.assertEqual((publicado["estado"], publicado["resultado_publicado"]), ("calificado", True))
        self.resultado(j, 200)

    def test_la_entrega_inmediata_con_la_biblioteca_caida_promete_el_resultado_pronto_sin_inventar_nota(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="inmediata")
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        refs = [r for r in tipos if tipos[r] != "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(refs)])
        with self.biblioteca_caida():
            e = self.entregar(i, confirmar=True)
        self.assertEqual((e["que_sigue"]["codigo"], e["resultado_disponible"]), ("resultado_pronto", False))
        self.resultado(i, 403)


class PublicacionPorGrupoTests(_ConPublicacion):
    """El grupo 8A tiene a Juan y a Ana (inscrita ANTES de que Juan entregue: `al_finalizar_grupo` mira a los destinatarios actuales)."""

    def setUp(self):
        super().setUp()
        self.ana, self.hw_ana = self.alumno_con_tableta("Ana", "A-100", "supervisado")

    def test_al_finalizar_el_grupo_el_nodo_publica_cuando_el_ultimo_queda_resuelto(self):
        a, i_juan, _, _ = self.presentar(resultados="al_finalizar_grupo", responder_abiertas=False)
        self.assertEqual(self.resultado(i_juan, 403)["codigo"], "resultados_no_liberados")   # Juan terminó; el grupo (Juan + Ana) no
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["liberados_en"], None)
        ana, hw = self.ana, self.hw_ana
        i_ana = self.presentar_otro(a["id"], ana, hw)                                        # Ana entrega: el grupo terminó
        vista = self.ver(f"/asignaciones/{a['id']}/")
        self.assertEqual((vista["liberados_por"], vista["liberados_en"]), ("sistema", self.t))
        self.resultado(i_juan, 200)
        self.resultado(i_ana, 200, hw=hw, alumno_id=ana)
        self.assertEqual(self.eventos("evaluacion.resultados_liberados.v1"), ["evaluacion.resultados_liberados.v1"])
        evento = m.EventoSalida.objects.get(tipo_evento="evaluacion.resultados_liberados.v1")
        self.assertEqual((evento.carga["origen"], evento.carga["por"], evento.carga["politica"]), ("grupo", "sistema", "al_finalizar_grupo"))
        self.assertTrue(maudit.Bitacora.objects.filter(accion="evaluacion.resultados.liberados", objeto_id=a["id"]).exists())

    def test_un_alumno_con_revision_pendiente_detiene_al_grupo_hasta_que_el_profesor_publica_su_calificacion(self):
        a, i_juan, _, _ = self.presentar(resultados="al_finalizar_grupo", responder_abiertas=False)
        ana, hw = self.ana, self.hw_ana
        i_ana = self.presentar_otro(a["id"], ana, hw, responder_abiertas=True)
        self.assertEqual(self.fila(i_ana).estado, "en_revision_docente")
        self.resultado(i_juan, 403)
        for ref in [r for r, t in self.fila(i_ana).armado_meta["tipos"].items() if t == "open"]:
            self.accion(f"/intentos/{i_ana}/respuestas/{ref}/puntuar/", {"puntaje": 1})
        self.accion(f"/intentos/{i_ana}/publicar/")
        self.resultado(i_juan, 200)
        self.resultado(i_ana, 200, hw=hw, alumno_id=ana)

    def test_quien_nunca_empezo_detiene_al_grupo_mientras_la_evaluacion_sigue_abierta_y_no_cuando_cierra(self):
        a, i_juan, _, _ = self.presentar(resultados="al_finalizar_grupo", responder_abiertas=False)      # Ana nunca abre el examen
        self.resultado(i_juan, 403)
        self.accion(f"/asignaciones/{a['id']}/cerrar/", {"motivo": "Terminó la clase"})      # nadie más puede empezar: el grupo quedó resuelto
        self.resultado(i_juan, 200)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["liberados_por"], "sistema")

    def test_un_intento_anulado_cuenta_como_resuelto(self):
        a, i_juan, _, _ = self.presentar(resultados="al_finalizar_grupo", responder_abiertas=False)
        ana, hw = self.ana, self.hw_ana
        i_ana = self.presentar_otro(a["id"], ana, hw, responder_abiertas=True)
        self.resultado(i_juan, 403)
        self.accion(f"/intentos/{i_ana}/anular/", {"motivo": "Falla técnica que impidió presentar con normalidad"})
        self.resultado(i_juan, 200)
        self.resultado(i_ana, 403, hw=hw, alumno_id=ana)                                      # un intento anulado no tiene resultado que ver


class PublicacionProgramadaTests(_ConPublicacion):
    def test_el_nodo_habilita_los_resultados_al_alcanzar_el_momento_con_su_reloj_y_lo_persiste_el_barrido(self):
        cuando = self.t + 30 * MIN
        a, i, _, _ = self.presentar(resultados="programada", publicar_en=cuando, responder_abiertas=False)
        self.assertEqual(self.resultado(i, 403)["publicar_en"], cuando)
        self.avanzar(minutos=29)
        self.assertEqual(barrido.BarrerNodo(servicios()).ejecutar()["publicadas"], 0)
        self.resultado(i, 403)
        self.avanzar(minutos=1)
        self.assertEqual(barrido.BarrerNodo(servicios()).ejecutar()["publicadas"], 1)        # el reloj del nodo decide (BR-062)
        vista = self.ver(f"/asignaciones/{a['id']}/")
        self.assertEqual((vista["liberados_en"], vista["liberados_por"]), (cuando, "sistema"))
        self.resultado(i, 200)
        evento = m.EventoSalida.objects.get(tipo_evento="evaluacion.resultados_liberados.v1")
        self.assertEqual((evento.carga["origen"], evento.carga["por"]), ("programada", "sistema"))
        self.assertEqual(barrido.BarrerNodo(servicios()).ejecutar()["publicadas"], 0)        # idempotente

    def test_sin_barrido_la_lectura_del_alumno_aplica_lo_que_el_reloj_ya_provoco(self):
        cuando = self.t + 10 * MIN
        a, i, _, _ = self.presentar(resultados="programada", publicar_en=cuando, responder_abiertas=False)
        self.resultado(i, 403)
        self.avanzar(minutos=10)
        self.resultado(i, 200)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["liberados_por"], "sistema")

    def test_la_entrega_programada_le_dice_al_alumno_cuando_sin_revelar_la_nota(self):
        cuando = self.t + 10 * MIN
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="programada", publicar_en=cuando)
        i = self.abrir(a["id"])["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(r for r in tipos if tipos[r] != "open")])
        e = self.entregar(i, confirmar=True)
        self.assertEqual((e["que_sigue"]["codigo"], e["publicar_en"], e["resultado_disponible"]), ("resultado_programado", cuando, False))
        self.assertEqual(self.mia(a["id"])["publicar_en"], cuando)


class PublicacionPorAlumnoTests(_ConPublicacion):
    def test_el_profesor_publica_el_resultado_de_un_alumno_sin_esperar_al_grupo(self):
        ana, hw = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        a, i_juan, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        i_ana = self.presentar_otro(a["id"], ana, hw)
        r = self.accion(f"/intentos/{i_juan}/liberar-resultado/")
        self.assertEqual((r["liberado_en"], r["liberado_por"], r["resultado_publicado"]), (self.t, self.docente_id, True))
        self.resultado(i_juan, 200)
        self.resultado(i_ana, 403, hw=hw, alumno_id=ana)                                      # sólo el de Juan
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["liberados_en"], None)          # la asignación sigue sin liberar
        filas = {f["alumno_id"]: f for f in self.ver(f"/asignaciones/{a['id']}/resultados/")["filas"]}
        self.assertEqual((filas[self.estudiante_id]["resultado_publicado"], filas[self.estudiante_id]["liberado_por"], filas[ana]["resultado_publicado"]),
                         (True, self.docente_id, False))
        self.assertEqual(self.eventos("evaluacion.resultado_intento_liberado.v1"), ["evaluacion.resultado_intento_liberado.v1"])
        asiento = maudit.Bitacora.objects.get(accion="evaluacion.resultado.liberado", objeto_id=i_juan)
        self.assertEqual(asiento.valor_nuevo["alumno_id"], self.estudiante_id)
        otra = self.accion(f"/intentos/{i_juan}/liberar-resultado/")                          # idempotente: la primera manda
        self.assertEqual(otra["liberado_en"], self.t)
        self.assertEqual(len(self.eventos("evaluacion.resultado_intento_liberado.v1")), 1)

    def test_no_se_publica_lo_que_no_esta_completamente_calificado(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=True)
        r = self.accion(f"/intentos/{i}/liberar-resultado/", esperado=409)
        self.assertEqual(r["codigo"], "reactivos_pendientes")
        b = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, resultados="manual")
        j = self.abrir(b["id"])["intento"]["id"]
        self.assertEqual(self.accion(f"/intentos/{j}/liberar-resultado/", esperado=409)["codigo"], "transicion_invalida")

    def test_con_la_politica_nunca_no_se_publica_ni_por_alumno(self):
        a, i, _, _ = self.presentar(resultados="nunca", responder_abiertas=False)
        self.assertEqual(self.accion(f"/intentos/{i}/liberar-resultado/", esperado=409)["codigo"], "transicion_invalida")
        self.resultado(i, 403)

    def test_el_alumno_no_publica_ni_cambia_la_politica(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        for metodo, ruta in (("post", f"/intentos/{i}/liberar-resultado/"), ("patch", f"/asignaciones/{a['id']}/publicacion/"),
                             ("post", f"/asignaciones/{a['id']}/liberar-resultados/")):
            r = getattr(alumno, metodo)(f"{BASE}{ruta}", {"resultados": "inmediata"}, format="json")
            self.assertEqual(r.status_code, 403, (ruta, r.content))
        self.resultado(i, 403)


class ConfigurarPublicacionTests(_ConPublicacion):
    def test_cambiar_la_politica_queda_con_evento_y_asiento_y_se_aplica_al_instante(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        cuando = self.t + 15 * MIN
        r = self.accion(f"/asignaciones/{a['id']}/publicacion/", {"resultados": "programada", "publicar_en": cuando}, metodo="patch")
        self.assertEqual((r["resultados"], r["publicar_en"]), ("programada", cuando))
        asiento = maudit.Bitacora.objects.get(accion="evaluacion.resultados.configurados", objeto_id=a["id"])
        self.assertEqual((asiento.valor_anterior["resultados"], asiento.valor_nuevo["resultados"]), ("tras_liberar", "programada"))
        self.assertEqual(len(self.eventos("evaluacion.resultados_configurados.v1")), 1)
        self.resultado(i, 403)
        self.avanzar(minutos=15)
        self.resultado(i, 200)

    def test_cambiar_a_inmediata_o_a_grupo_terminado_publica_en_el_mismo_acto(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        self.accion(f"/asignaciones/{a['id']}/publicacion/", {"resultados": "inmediata"}, metodo="patch")
        self.resultado(i, 200)
        b, j, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        self.accion(f"/asignaciones/{b['id']}/cerrar/")                                       # sólo Juan presentó y ya cerró: el grupo quedó resuelto
        self.accion(f"/asignaciones/{b['id']}/publicacion/", {"resultados": "al_finalizar_grupo"}, metodo="patch")
        self.assertEqual(self.ver(f"/asignaciones/{b['id']}/")["liberados_por"], "sistema")
        self.resultado(j, 200)

    def test_lo_ya_publicado_no_se_vuelve_a_esconder(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        r = self.accion(f"/asignaciones/{a['id']}/publicacion/", {"resultados": "nunca"}, metodo="patch", esperado=409)
        self.assertEqual((r["codigo"], r["liberados_por"]), ("transicion_invalida", self.docente_id))
        self.resultado(i, 200)

    def test_la_fecha_programada_se_valida_tambien_al_cambiarla(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        self.accion(f"/asignaciones/{a['id']}/publicacion/", {"resultados": "programada"}, metodo="patch", esperado=400)
        self.accion(f"/asignaciones/{a['id']}/publicacion/", {"resultados": "programada", "publicar_en": self.t - 1}, metodo="patch", esperado=400)


class NadaSeFiltraTests(_ConPublicacion):
    """Ninguna ruta del alumno deja ver una nota no publicada ni la de otro alumno; el panel y los resultados son sólo del profesor."""

    def test_un_alumno_no_consulta_resultados_ajenos_ni_por_su_intento_ni_por_el_panel(self):
        ana, hw = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        a, i_juan, _, _ = self.presentar(resultados="inmediata", responder_abiertas=False)
        self.presentar_otro(a["id"], ana, hw)
        self.resultado(i_juan, 200)
        self.assertEqual(self.api.get(f"{BASE}/intentos/{i_juan}/resultado/", self.alumno(hw, ana)).status_code, 404)   # no se revela que existe
        self.assertEqual(self.api.get(f"{BASE}/intentos/{i_juan}/estado/", self.alumno(hw, ana)).status_code, 404)
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.get(f"{BASE}/asignaciones/{a['id']}/resultados/").status_code, 403)
        self.assertEqual(alumno.get(f"{BASE}/asignaciones/{a['id']}/panel/").status_code, 403)

    def test_las_rutas_del_alumno_no_llevan_la_nota_mientras_no_este_publicada(self):
        a, i, _, _ = self.presentar(resultados="manual", responder_abiertas=False)
        for cuerpo in (self.estado(i), self.mia(a["id"]), self.api.get(f"{BASE}/asignaciones/{a['id']}/antesala/", self.alumno()).json()):
            texto = str(cuerpo).lower()
            self.assertNotIn("porcentaje", texto)
            self.assertNotIn("puntaje", texto)
            self.assertNotIn("veredicto", texto)
