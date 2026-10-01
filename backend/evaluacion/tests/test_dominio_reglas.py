"""
Reglas puras de MOD-010, sin base de datos: armado por alumno, niveles y plan de bloqueo, plazos y fusión idempotente de respuestas con sesiones.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.test import SimpleTestCase

from ..dominio import armado as armado_dom
from ..dominio import asignacion as asig
from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio import respuestas as resp
from ..dominio.errores import DatosInvalidos, TransicionInvalida

T0 = 1_790_000_000_000
MIN = 60_000


def pool_de_ejemplo() -> list[dict]:
    with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
        manifiesto = json.load(f)
    examen = next(o for l in manifiesto["lessons"] for o in l["objects"] if o["type"] == "exam")
    return armado_dom.normalizar_pool({"questions": [{"questionId": q["id"], "type": q["type"], "topicRef": q["topicRef"], "difficulty": q["difficulty"],
                                                      "estimatedSec": q["estimatedSec"], "points": q["points"]} for q in examen["questions"]]})


class ArmadoTests(SimpleTestCase):
    def armar(self, semilla: str, **extra):
        pool = pool_de_ejemplo()
        args = dict(estrategia=armado_dom.RANDOM_BALANCED, cantidad=4, tolerancia_dificultad_pct=15, tolerancia_tiempo_pct=15, cubrir_temas=True,
                    semilla=semilla)
        args.update(extra)
        return armado_dom.armar(pool, **args), {p["pregunta_ref"]: p for p in pool}

    def test_fixed_entrega_todo_el_banco_en_su_orden(self):
        a, _ = self.armar("x", estrategia=armado_dom.FIXED)
        self.assertEqual(a.refs, [f"l3-q{n}" for n in range(1, 13)])
        self.assertTrue(a.dentro_de_tolerancia)

    def test_es_determinista_la_misma_semilla_da_el_mismo_examen(self):
        for semilla in ("a|b|1", "a|b|2", "otra"):
            primero, _ = self.armar(semilla)
            segundo, _ = self.armar(semilla)
            self.assertEqual(primero.refs, segundo.refs)

    def test_alumnos_distintos_reciben_examenes_distintos(self):
        examenes = {tuple(sorted(self.armar(f"asig|alumno-{n}|1")[0].refs)) for n in range(30)}
        self.assertGreater(len(examenes), 5)

    def test_cada_examen_tiene_la_cantidad_pedida_sin_repetir_y_cubre_los_dos_temas(self):
        for n in range(60):
            a, pool = self.armar(f"asig|alumno-{n}|1")
            self.assertEqual(len(a.refs), 4)
            self.assertEqual(len(set(a.refs)), 4)
            self.assertEqual({pool[r]["tema_ref"] for r in a.refs}, {"t-states", "t-changes"})       # coverAllTopics

    def test_la_dificultad_y_el_tiempo_totales_quedan_dentro_de_la_tolerancia_o_se_avisa(self):
        for n in range(60):
            a, pool = self.armar(f"asig|alumno-{n}|1")
            objetivo_d = 4 * sum(p["dificultad"] for p in pool.values()) / 12
            objetivo_t = 4 * sum(p["estimado_seg"] for p in pool.values()) / 12
            if a.dentro_de_tolerancia:
                self.assertLessEqual(abs(a.dificultad_total - objetivo_d) / objetivo_d * 100, 15.001)
                self.assertLessEqual(abs(a.tiempo_total_seg - objetivo_t) / objetivo_t * 100, 15.001)
            else:
                self.assertIn("W-EXAM-TOLERANCE", a.avisos)
        dentro = sum(1 for n in range(60) if self.armar(f"asig|alumno-{n}|1")[0].dentro_de_tolerancia)
        self.assertGreaterEqual(dentro, 55)         # el banco de ejemplo permite equilibrar casi siempre

    def test_una_tolerancia_imposible_entrega_el_mejor_examen_y_lo_avisa_sin_bloquear(self):
        a, _ = self.armar("x", tolerancia_dificultad_pct=0.001, tolerancia_tiempo_pct=0.001)
        self.assertEqual(len(a.refs), 4)
        self.assertFalse(a.dentro_de_tolerancia)
        self.assertIn("W-EXAM-TOLERANCE", a.avisos)

    def test_cantidad_mayor_que_el_banco_se_recorta(self):
        a, _ = self.armar("x", cantidad=99)
        self.assertEqual(len(a.refs), 12)

    def test_con_menos_cupos_que_temas_se_avisa(self):
        a, _ = self.armar("x", cantidad=1)
        self.assertEqual(len(a.refs), 1)
        self.assertIn("W-EXAM-TOPICS", a.avisos)

    def test_banco_vacio_y_estrategia_desconocida(self):
        with self.assertRaises(DatosInvalidos):
            armado_dom.armar([], estrategia=armado_dom.FIXED, cantidad=1, tolerancia_dificultad_pct=1, tolerancia_tiempo_pct=1, cubrir_temas=False, semilla="x")
        with self.assertRaises(DatosInvalidos):
            armado_dom.armar(pool_de_ejemplo(), estrategia="azar", cantidad=1, tolerancia_dificultad_pct=1, tolerancia_tiempo_pct=1, cubrir_temas=False,
                             semilla="x")

    def test_el_armado_solo_guarda_referencias_tipos_y_puntos(self):
        a, _ = self.armar("x")
        meta = a.meta()
        self.assertEqual(set(meta), {"estrategia", "tipos", "puntos", "puntos_totales", "estimado_seg", "dentro_de_tolerancia", "avisos"})
        self.assertEqual(set(meta["tipos"]), set(a.refs))

    def test_limite_de_tiempo_por_politica(self):
        self.assertEqual(armado_dom.limite_en_segundos("sum_of_estimates", estimado_seg=200, extra_pct=25), 250)
        self.assertEqual(armado_dom.limite_en_segundos("sum_of_estimates", estimado_seg=201, extra_pct=25), 252)         # redondea hacia arriba
        self.assertEqual(armado_dom.limite_en_segundos("fixed", estimado_seg=200, fijo_seg=900), 900)
        self.assertIsNone(armado_dom.limite_en_segundos("none", estimado_seg=200))
        self.assertIsNone(armado_dom.limite_en_segundos(None, estimado_seg=200))

    def test_ajustes_de_biblioteca_acepta_las_dos_formas_del_esquema(self):
        entregado = armado_dom.ajustes_de_biblioteca({
            "selection": {"strategy": "random_balanced", "questionCount": 4, "difficultyTolerancePct": 15, "timeTolerancePct": 10, "coverAllTopics": True},
            "timeLimit": {"policy": "sum_of_estimates", "extraPct": 25}, "passingScorePct": 60, "showResults": "after_teacher_release",
            "allowBackNavigation": False, "shuffleOptions": True})
        self.assertEqual((entregado["tolerancia_dificultad_pct"], entregado["tolerancia_tiempo_pct"], entregado["tiempo"]["politica"],
                          entregado["mostrar_resultados"], entregado["navegacion_atras"]), (15, 10, "sum_of_estimates", cat.TRAS_LIBERAR, False))
        instalado = armado_dom.ajustes_de_biblioteca({
            "selection": {"strategy": "fixed", "difficultyTolerancePercent": 20, "timeTolerancePercent": 5},
            "timeLimit": {"fixedSec": 1200}, "showResults": "never"})
        self.assertEqual((instalado["tolerancia_dificultad_pct"], instalado["tiempo"], instalado["mostrar_resultados"]),
                         (20, {"politica": "fixed", "fijo_seg": 1200, "extra_pct": None}, cat.NUNCA))
        self.assertEqual(armado_dom.ajustes_de_biblioteca({})["tiempo"]["politica"], "none")


class BloqueoTests(SimpleTestCase):
    def test_una_tableta_alcanza_el_nivel_si_su_capacidad_no_es_menor(self):
        casos = {("controlado", "controlado"): True, ("controlado", "supervisado"): True, ("controlado", "abierto"): True,
                 ("supervisado", "controlado"): False, ("supervisado", "supervisado"): True, ("abierto", "supervisado"): False,
                 ("abierto", "abierto"): True, ("", "controlado"): False, ("", "abierto"): True, (None, "supervisado"): False, ("raro", "supervisado"): False}
        for (capacidad, nivel), esperado in casos.items():
            self.assertEqual(bloqueo.alcanza(capacidad, nivel), esperado, f"{capacidad!r} vs {nivel}")

    def test_lo_que_la_tableta_no_declara_cuenta_como_abierto(self):
        self.assertEqual(bloqueo.normalizar_capacidad(None), "abierto")
        self.assertEqual(bloqueo.normalizar_capacidad("CONTROLADO"), "controlado")
        self.assertEqual(bloqueo.validar_capacidad(""), "abierto")
        with self.assertRaises(DatosInvalidos):
            bloqueo.validar_capacidad("blindado")

    def test_degradar_solo_baja_y_admitir_es_siempre_por_debajo(self):
        bloqueo.validar_degradacion("controlado", "supervisado")
        bloqueo.validar_degradacion("supervisado", "abierto")
        for vigente, nuevo in (("controlado", "controlado"), ("supervisado", "controlado"), ("abierto", "supervisado")):
            with self.assertRaises(DatosInvalidos):
                bloqueo.validar_degradacion(vigente, nuevo)
        bloqueo.validar_admision("controlado", "supervisado")
        with self.assertRaises(DatosInvalidos):
            bloqueo.validar_admision("supervisado", "supervisado")

    def test_el_plan_de_controlado_con_capacidad_aplica_las_dos_capas(self):
        plan = bloqueo.plan_de_bloqueo("controlado", "controlado")
        self.assertEqual((plan["capa_sistema"], plan["capa_app"], plan["registrar_salidas"], plan["bloquear_capturas"],
                          plan["cubrir_pantallas_extra"], plan["parcial"], plan["latido_seg"]), (True, True, True, True, True, False, 5))

    def test_el_plan_de_controlado_sin_la_capa_del_sistema_es_parcial_y_no_lo_oculta(self):
        plan = bloqueo.plan_de_bloqueo("controlado", "supervisado")
        self.assertEqual((plan["capa_sistema"], plan["capa_app"], plan["parcial"]), (False, True, True))

    def test_supervisado_no_bloquea_pero_registra_salidas_y_consultas(self):
        plan = bloqueo.plan_de_bloqueo("supervisado", "supervisado", nivel_exigido="controlado")
        self.assertEqual((plan["capa_sistema"], plan["capa_app"], plan["registrar_salidas"], plan["registrar_consultas"], plan["nivel_exigido"]),
                         (False, False, True, True, "controlado"))

    def test_abierto_solo_registra_entrega_y_tiempo(self):
        plan = bloqueo.plan_de_bloqueo("abierto", "abierto")
        self.assertEqual((plan["capa_sistema"], plan["capa_app"], plan["registrar_salidas"], plan["registrar_consultas"], plan["latido_seg"]),
                         (False, False, False, False, 10))

    def test_cada_nivel_tiene_su_texto_obligatorio_para_la_antesala(self):
        for nivel in cat.NIVELES:
            c = bloqueo.condiciones(nivel)
            self.assertTrue(c["texto"].strip() and c["titulo"].strip() and c["registra"])
        self.assertIn("tu profesor lo verá", bloqueo.condiciones("controlado")["texto"])
        self.assertIn("qué consultaste", bloqueo.condiciones("supervisado")["texto"])
        self.assertIn("consulta libre", bloqueo.condiciones("abierto")["texto"])

    def test_informe_de_bloqueo(self):
        resultado, capas = bloqueo.valida_informe_de_bloqueo("PARCIAL", {"app": 1, "sistema": 0, "inventada": True})
        self.assertEqual((resultado, capas), ("parcial", {"sistema": False, "app": True, "capturas": False, "pantallas": False}))
        with self.assertRaises(DatosInvalidos):
            bloqueo.valida_informe_de_bloqueo("quizá", {})
        with self.assertRaises(DatosInvalidos):
            bloqueo.valida_informe_de_bloqueo("aplicado", "no es un objeto")


class AsignacionDominioTests(SimpleTestCase):
    def asignacion(self, **extra) -> dict:
        return {"estado": cat.ACTIVA, "plazo": cat.BLANDO, "abre_en": None, "limite_en": T0 + 10 * MIN, "cerrada_en": None, **extra}

    def test_las_transiciones_del_diagrama(self):
        for origen, destino in [("borrador", "programada"), ("borrador", "activa"), ("programada", "activa"), ("activa", "activa_fuera_de_plazo"),
                                ("activa", "cerrada"), ("activa_fuera_de_plazo", "cerrada"), ("activa_fuera_de_plazo", "activa"), ("cerrada", "activa"),
                                ("cerrada", "archivada")]:
            asig.comprobar_transicion(origen, destino)
        for origen, destino in [("archivada", "activa"), ("borrador", "cerrada"), ("programada", "cerrada"), ("activa", "borrador")]:
            with self.assertRaises(TransicionInvalida):
                asig.comprobar_transicion(origen, destino)

    def test_el_plazo_blando_marca_y_no_cierra(self):
        a = self.asignacion()
        self.assertEqual(asig.estado_por_tiempo(a, T0 + 9 * MIN), cat.ACTIVA)
        self.assertEqual(asig.estado_por_tiempo(a, T0 + 10 * MIN), cat.ACTIVA_FUERA_DE_PLAZO)
        self.assertEqual(asig.estado_por_tiempo(a, T0 + 999 * MIN), cat.ACTIVA_FUERA_DE_PLAZO)         # nunca cierra sola

    def test_el_plazo_endurecido_cierra_al_vencer_y_nunca_pasa_por_fuera_de_plazo(self):
        a = self.asignacion(plazo=cat.ENDURECIDO)
        self.assertEqual(asig.estado_por_tiempo(a, T0 + 9 * MIN), cat.ACTIVA)
        self.assertEqual(asig.estado_por_tiempo(a, T0 + 10 * MIN), cat.CERRADA)
        self.assertEqual(asig.cierre_por_plazo(a), T0 + 10 * MIN)
        self.assertIsNone(asig.cierre_por_plazo(self.asignacion()))
        self.assertEqual(asig.estado_por_tiempo(self.asignacion(estado=cat.ACTIVA_FUERA_DE_PLAZO, plazo=cat.ENDURECIDO), T0 + 11 * MIN), cat.CERRADA)

    def test_programada_se_activa_al_llegar_su_fecha_y_cerrada_se_archiva_a_las_24_horas(self):
        p = self.asignacion(estado=cat.PROGRAMADA, abre_en=T0 + 5 * MIN, limite_en=None)
        self.assertEqual(asig.estado_por_tiempo(p, T0 + 4 * MIN), cat.PROGRAMADA)
        self.assertEqual(asig.estado_por_tiempo(p, T0 + 5 * MIN), cat.ACTIVA)
        c = self.asignacion(estado=cat.CERRADA, cerrada_en=T0)
        self.assertEqual(asig.estado_por_tiempo(c, T0 + 23 * 60 * MIN), cat.CERRADA)
        self.assertEqual(asig.estado_por_tiempo(c, T0 + 24 * 60 * MIN), cat.ARCHIVADA)
        self.assertEqual(asig.estado_por_tiempo(c, T0 + 60 * MIN, archivo_tras_ms=30 * MIN), cat.ARCHIVADA)

    def test_estado_por_tiempo_es_idempotente(self):
        for estado in cat.ESTADOS_ASIGNACION:
            a = self.asignacion(estado=estado, cerrada_en=T0 if estado in cat.CON_CIERRE else None)
            primero = asig.estado_por_tiempo(a, T0 + 30 * MIN)
            self.assertEqual(asig.estado_por_tiempo({**a, "estado": primero}, T0 + 30 * MIN), primero)

    def test_politica_de_recepcion_tras_el_cierre(self):
        cierre = T0
        p = lambda capturada, recibida: asig.politica_de_recepcion(cerrada_en=cierre, capturada_en=capturada, recibida_en=recibida)    # noqa: E731
        self.assertEqual(asig.politica_de_recepcion(cerrada_en=None, capturada_en=None, recibida_en=T0), asig.ACEPTAR)
        self.assertEqual(p(cierre - MIN, cierre + 10 * MIN), asig.ACEPTAR)                      # TST-042: a los 10 minutos, dentro de la gracia
        self.assertEqual(p(cierre - MIN, cierre + 15 * MIN), asig.ACEPTAR)                      # justo en el límite
        self.assertEqual(p(cierre - MIN, cierre + 20 * MIN), asig.DECIDE_EL_PROFESOR)           # a los 20, decide el profesor
        self.assertEqual(p(cierre + MIN, cierre + 2 * MIN), asig.RECHAZAR)                      # capturado después del cierre

    def test_el_corte_de_recepcion_es_el_cierre_de_la_asignacion_solo_cuando_ella_fue_la_causa(self):
        asignacion = {"cerrada_en": T0 + 10 * MIN}
        sin_senal = {"origen_entrega": cat.O_PLAZO, "entregado_en": T0 + MIN}                    # reloj detenido en el último latido
        self.assertEqual(asig.cierre_de_recepcion(sin_senal, asignacion), T0 + 10 * MIN)
        self.assertEqual(asig.cierre_de_recepcion({**sin_senal, "origen_entrega": cat.O_CIERRE}, asignacion), T0 + 10 * MIN)
        for origen in (cat.O_TIEMPO, cat.O_ALUMNO, cat.O_PROFESOR):                              # su propio instante, no el de la asignación
            self.assertEqual(asig.cierre_de_recepcion({**sin_senal, "origen_entrega": origen}, asignacion), T0 + MIN)
        self.assertEqual(asig.cierre_de_recepcion(sin_senal, {"cerrada_en": None}), T0 + MIN)    # reabierta: vale la entrega
        self.assertEqual(asig.cierre_de_recepcion(sin_senal, {"cerrada_en": T0}), T0 + MIN)      # se cerró antes de entregar (no ocurre): no se adelanta

    def test_validaciones(self):
        self.assertEqual(asig.validar_plazo(None, None, None, T0), (cat.BLANDO, None, None))
        with self.assertRaises(DatosInvalidos):
            asig.validar_plazo("endurecido", None, None, T0)                                    # el endurecido exige fecha límite
        with self.assertRaises(DatosInvalidos):
            asig.validar_plazo("blando", T0, T0 + MIN, T0)                                      # la apertura no puede ser posterior al límite
        with self.assertRaises(DatosInvalidos):
            asig.validar_plazo("flexible", None, None, T0)
        self.assertEqual(asig.validar_gracia_ms(), cat.GRACIA_MS_POR_DEFECTO)
        self.assertEqual(asig.validar_gracia_ms(gracia_min=5), 5 * MIN)
        with self.assertRaises(DatosInvalidos):
            asig.validar_gracia_ms(gracia_min=-1)
        self.assertEqual(asig.validar_intentos_permitidos(3), 3)
        self.assertIsNone(asig.validar_intentos_permitidos(None))                               # nulo explícito = sin tope
        with self.assertRaises(DatosInvalidos):
            asig.validar_intentos_permitidos(0)
        self.assertEqual(asig.validar_tiempo({"modo": "fijo", "limite_seg": 900}), (cat.TIEMPO_FIJO, 900))
        self.assertEqual(asig.validar_tiempo(None), (cat.TIEMPO_BIBLIOTECA, None))
        with self.assertRaises(DatosInvalidos):
            asig.validar_tiempo({"modo": "fijo"})
        with self.assertRaises(DatosInvalidos):
            asig.validar_tiempo({"modo": "infinito"})
        self.assertEqual(asig.validar_alcance("grupo", None, "g1"), ("grupo", []))
        self.assertEqual(asig.validar_alcance("seleccion", ["a", "a", "b"], None), ("seleccion", ["a", "b"]))
        for malo in (("grupo", None, ""), ("seleccion", [], "g"), ("todos", None, "g")):
            with self.assertRaises(DatosInvalidos):
                asig.validar_alcance(*malo)
        self.assertEqual(asig.validar_reactivacion(None, cat.CONTROLADO), cat.REACTIVA_PROFESOR)          # por defecto la reactivación es del profesor
        self.assertEqual(asig.validar_recursos([{"media_ref": "img-1", "rotulo": "Mapa"}]), [{"media_ref": "img-1", "rotulo": "Mapa"}])
        with self.assertRaises(DatosInvalidos):
            asig.validar_recursos([{"rotulo": "sin referencia"}])


class FusionDeRespuestasTests(SimpleTestCase):
    def fusionar(self, vigentes, nuevas, sesion="s1", orden=100):
        return resp.fusionar(vigentes, nuevas, sesion_ref=sesion, sesion_orden=orden, ahora=T0)

    @staticmethod
    def n(ref, secuencia, **respuesta):
        return {"pregunta_ref": ref, "secuencia": secuencia, "respuesta": respuesta or {"value": True}}

    def test_una_respuesta_nueva_se_acepta(self):
        lista, r = self.fusionar([], [self.n("q1", 1)])
        self.assertEqual((r.aceptadas, r.duplicadas, r.superadas), (["q1"], [], []))
        self.assertEqual(lista[0]["veredicto"], None)

    def test_el_reenvio_del_mismo_paquete_no_duplica_nada_inv_013(self):
        lista, _ = self.fusionar([], [self.n("q1", 1), self.n("q2", 2)])
        lista2, r = self.fusionar(lista, [self.n("q1", 1), self.n("q2", 2)])
        self.assertEqual((r.aceptadas, sorted(r.duplicadas)), ([], ["q1", "q2"]))
        self.assertEqual(lista2, lista)

    def test_la_secuencia_mayor_de_la_misma_sesion_sustituye_y_la_menor_llega_tarde(self):
        lista, _ = self.fusionar([], [self.n("q1", 3, value=True)])
        sustituida, r = self.fusionar(lista, [self.n("q1", 5, value=False)])
        self.assertEqual((r.aceptadas, sustituida[0]["respuesta"], sustituida[0]["secuencia"]), (["q1"], {"value": False}, 5))
        self.assertEqual(sustituida[0]["historial"][0]["motivo"], "reemplazada")
        tarde, r = self.fusionar(sustituida, [self.n("q1", 4, value=True)])
        self.assertEqual((r.superadas, tarde[0]["respuesta"]), (["q1"], {"value": False}))             # no pisa a la vigente
        self.assertEqual(tarde[0]["historial"][-1]["motivo"], "superada")

    def test_dos_cambios_de_la_misma_pregunta_en_un_vaciado_dejan_el_ultimo_sea_cual_sea_el_orden(self):
        for orden in ([self.n("q1", 2, value=1), self.n("q1", 7, value=2)], [self.n("q1", 7, value=2), self.n("q1", 2, value=1)]):
            lista, _ = self.fusionar([], orden)
            self.assertEqual((lista[0]["secuencia"], lista[0]["respuesta"]), (7, {"value": 2}))

    def test_br_138_gana_la_sesion_mas_reciente_sin_importar_el_orden_de_llegada(self):
        # primero llega lo de la sesión B (más reciente) y DESPUÉS lo de la A (más antigua): A no sustituye a B (TST-027)
        lista, _ = self.fusionar([], [self.n("q1", 1, value="B")], sesion="B", orden=200)
        despues, r = self.fusionar(lista, [self.n("q1", 9, value="A")], sesion="A", orden=100)
        self.assertEqual((r.superadas, despues[0]["respuesta"], despues[0]["sesion_ref"]), (["q1"], {"value": "B"}, "B"))
        # al revés: lo de A ya estaba y llega lo de B: B sustituye aunque su secuencia sea menor
        lista, _ = self.fusionar([], [self.n("q1", 9, value="A")], sesion="A", orden=100)
        despues, r = self.fusionar(lista, [self.n("q1", 1, value="B")], sesion="B", orden=200)
        self.assertEqual((r.aceptadas, despues[0]["respuesta"], despues[0]["sesion_ref"]), (["q1"], {"value": "B"}, "B"))

    def test_preguntas_distintas_de_sesiones_distintas_conviven(self):
        lista, _ = self.fusionar([], [self.n("q1", 1)], sesion="A", orden=100)
        lista, r = self.fusionar(lista, [self.n("q2", 1)], sesion="B", orden=200)
        self.assertEqual((r.aceptadas, [x["pregunta_ref"] for x in lista]), (["q2"], ["q1", "q2"]))

    def test_historial_acotado(self):
        lista = []
        for n in range(1, 30):
            lista, _ = self.fusionar(lista, [self.n("q1", n, value=n)])
        self.assertLessEqual(len(lista[0]["historial"]), resp.MAX_HISTORIAL)

    def test_limpiar_rechaza_con_motivo_y_guarda_lo_demas(self):
        entrada = [{"pregunta_ref": "q1", "secuencia": 1, "respuesta": {"value": True}}, {"pregunta_ref": "zz", "secuencia": 1, "respuesta": {"value": True}},
                   {"pregunta_ref": "q2", "secuencia": 0, "respuesta": {"value": True}}, {"pregunta_ref": "q2", "secuencia": 1, "respuesta": {}},
                   {"pregunta_ref": "q3", "secuencia": 1, "respuesta": {"text": "no es del tipo"}}, {"secuencia": 1, "respuesta": {"value": 1}}, 7]
        limpias, rechazadas = resp.limpiar_respuestas(entrada, ["q1", "q2", "q3"], {"q1": "true_false", "q2": "true_false", "q3": "true_false"}, 200)
        self.assertEqual([r["pregunta_ref"] for r in limpias], ["q1"])
        self.assertEqual(len(rechazadas), 6)
        self.assertTrue(all(r["motivo"] for r in rechazadas))
        with self.assertRaises(DatosInvalidos):
            resp.limpiar_respuestas([{}] * 201, [], {}, 200)
        with self.assertRaises(DatosInvalidos):
            resp.limpiar_respuestas("no es una lista", [], {}, 200)

    def test_forma_por_tipo(self):
        self.assertIsNone(resp.forma_valida("multiple_choice", {"selectedOptionIds": ["a"]}))
        self.assertIsNone(resp.forma_valida("open", {"drawingRef": "dib-1"}))
        self.assertIsNone(resp.forma_valida("tipo_nuevo", {"lo_que_sea": 1}))                  # conjunto abierto: la biblioteca decide
        self.assertIn("sobra", resp.forma_valida("true_false", {"value": True, "extra": 1}))


class TotalesTests(SimpleTestCase):
    @staticmethod
    def con_veredicto(ref, puntaje, maximo=1.0, manual=False, revision=None):
        v = {"puntaje": None if manual else puntaje, "puntaje_maximo": maximo, "pendiente": manual, "requiere_correccion_manual": manual, "correcta": None}
        return {"pregunta_ref": ref, "respuesta": {}, "secuencia": 1, "veredicto": v, "revision": revision}

    def test_escala_interna_y_decimales_sin_redondear(self):
        rs = [self.con_veredicto("a", 1.3333, 2.0), self.con_veredicto("b", 1.5, 1.5)]
        t = resp.totales(rs, ["a", "b"], {"a": 2.0, "b": 1.5})
        self.assertEqual((t["puntaje"], t["puntaje_maximo"]), (2.8333, 3.5))
        self.assertAlmostEqual(t["porcentaje"], 100 * 2.8333 / 3.5, places=3)

    def test_lo_omitido_suma_cero_sobre_su_maximo(self):
        t = resp.totales([self.con_veredicto("a", 1, 1)], ["a", "b", "c"], {"a": 1, "b": 1, "c": 2})
        self.assertEqual((t["puntaje"], t["puntaje_maximo"], t["porcentaje"], t["sin_calificar"]), (1.0, 4.0, 25.0, 0))

    def test_un_reactivo_pendiente_ni_suma_ni_resta_hasta_que_el_profesor_lo_puntua(self):
        rs = [self.con_veredicto("a", 1, 1), self.con_veredicto("b", None, 3, manual=True)]
        t = resp.totales(rs, ["a", "b"], {"a": 1, "b": 3})
        self.assertEqual((t["puntaje"], t["puntaje_maximo"], t["sin_calificar"], t["pendientes_de_revision"]), (1.0, 1.0, 1, 1))
        self.assertEqual(resp.pendientes_de_revision(rs), ["b"])
        self.assertTrue(resp.requiere_revision(rs))
        revisado = [rs[0], self.con_veredicto("b", None, 3, manual=True, revision={"puntaje": 2.0, "revisada_por": "p", "revisada_en": T0})]
        t = resp.totales(revisado, ["a", "b"], {"a": 1, "b": 3})
        self.assertEqual((t["puntaje"], t["puntaje_maximo"], t["sin_calificar"]), (3.0, 4.0, 0))
        self.assertFalse(resp.requiere_revision(revisado))

    def test_sin_veredicto_no_es_revision_docente_sino_calificacion_pendiente(self):
        sin = [{"pregunta_ref": "a", "respuesta": {}, "secuencia": 1, "veredicto": None, "revision": None}]
        self.assertFalse(resp.requiere_revision(sin))
        self.assertEqual(len(resp.sin_veredicto(sin)), 1)
        self.assertEqual(resp.totales(sin, ["a"], {"a": 1})["sin_calificar"], 1)

    def test_porcentaje_acotado(self):
        self.assertEqual(resp.porcentaje(5, 4), 100.0)
        self.assertEqual(resp.porcentaje(-1, 4), 0.0)
        self.assertIsNone(resp.porcentaje(None, 4))
        self.assertIsNone(resp.porcentaje(1, 0))
