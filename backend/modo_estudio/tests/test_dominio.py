"""
Las reglas puras de MOD-008, sin base de datos ni HTTP: los bloques de una lección y el avance (D-4, FUN-087), la política de plazo y de recepción (D-9,
D-8), el manifiesto canónico y su huella (D-7), la fusión idempotente de respuestas (INV-013), el resultado de una práctica y la validación de lo que
llega de la cola del aparato.
"""
from __future__ import annotations

import hashlib
import json

from django.test import SimpleTestCase

from ..dominio import asignacion as asignacion_dom
from ..dominio import bloques as bloques_dom
from ..dominio import catalogos as cat
from ..dominio import paquete as paquete_dom
from ..dominio import plazo as plazo_dom
from ..dominio import practica as practica_dom
from ..dominio import sync as sync_dom
from ..dominio.errores import DatosInvalidos

MIN = 60_000


def leccion() -> dict:
    """Una lección con la forma de la vista de aula (lo que `ConsultarCurso` entrega), sin claves."""
    return {"leccion_ref": "l1", "titulo": "L1", "objetos": [
        {"objeto_ref": "lec", "tipo": "lecture", "titulo": "Presentación", "laminas": [
            {"unidad_ref": "s1", "indice": 1, "titulo": "Qué es", "bloques": [{"tipo": "text", "texto": "hola"}]},
            {"unidad_ref": "s2", "indice": 2, "titulo": "", "bloques": [{"tipo": "image", "media_ref": "img-a"}, {"tipo": "video", "media_ref": "vid-b"},
                                                                          {"tipo": "image", "media_ref": "img-a"}]}]},
        {"objeto_ref": "exp", "tipo": "explanation", "titulo": "Lectura", "paginas": [
            {"unidad_ref": "p1", "indice": 1, "titulo": "Resumen", "bloques": [{"tipo": "audio", "media_ref": "aud-c"}]}]},
        {"objeto_ref": "lab", "tipo": "simulation_lab", "titulo": "Laboratorio", "simulacion": {"media_ref": "sim-d", "clase": "simulation"}},
        {"objeto_ref": "act", "tipo": "activity", "titulo": "Practica", "preguntas": [
            {"pregunta_ref": "q1", "tipo": "multiple_choice", "medios": [{"media_ref": "img-e"}],
             "opciones": [{"opcion_ref": "a", "media_ref": "img-f"}, {"opcion_ref": "b", "media_ref": None}]},
            {"pregunta_ref": "q2", "tipo": "matching", "medios": [], "izquierda": [{"ref": "l", "media_ref": "img-a"}], "derecha": [{"ref": "r", "media_ref": None}]}]},
        {"objeto_ref": "exa", "tipo": "exam", "titulo": "Examen", "preguntas": []},
        {"objeto_ref": "raro", "tipo": "hologram", "titulo": "Algo nuevo"},
    ]}


class BloquesTests(SimpleTestCase):
    def test_la_estructura_sigue_el_orden_en_que_se_ve_y_el_examen_no_es_bloque(self):
        bloques = bloques_dom.bloques_de_leccion(leccion())
        self.assertEqual([(b["ref"], b["indice"], b["tipo"], b["objeto_ref"]) for b in bloques],
                         [("lec:s1", 1, "lamina", "lec"), ("lec:s2", 2, "lamina", "lec"), ("exp:p1", 3, "pagina", "exp"), ("lab", 4, "laboratorio", "lab"),
                          ("act", 5, "practica", "act")])
        self.assertTrue(all(b["obligatorio"] for b in bloques))                       # D-4 · Q-66: todo es obligatorio
        self.assertEqual([b["titulo"] for b in bloques], ["Qué es", "Presentación · 2", "Resumen", "Laboratorio", "Practica"])   # sin título: el del objeto y su número

    def test_cada_bloque_lleva_las_referencias_de_los_medios_que_usa(self):
        por_ref = {b["ref"]: b["medios"] for b in bloques_dom.bloques_de_leccion(leccion())}
        self.assertEqual(por_ref, {"lec:s1": [], "lec:s2": ["img-a", "vid-b"], "exp:p1": ["aud-c"], "lab": ["sim-d"], "act": ["img-e", "img-f", "img-a"]})
        self.assertEqual(bloques_dom.medios_de_leccion(leccion()), ["img-a", "vid-b", "aud-c", "sim-d", "img-e", "img-f"])
        self.assertEqual(bloques_dom.medios_de_bloques(bloques_dom.bloques_de_leccion(leccion())), {"img-a", "vid-b", "aud-c", "sim-d", "img-e", "img-f"})

    def test_la_practica_es_la_primera_actividad_y_la_evaluacion_el_primer_examen_solo_informativo(self):
        self.assertEqual(bloques_dom.practica_de_leccion(leccion()), {"objeto_ref": "act", "titulo": "Practica", "total_preguntas": 2})
        self.assertEqual(bloques_dom.evaluacion_de_leccion(leccion()), {"objeto_ref": "exa", "titulo": "Examen"})
        self.assertEqual((bloques_dom.practica_de_leccion({"objetos": []}), bloques_dom.evaluacion_de_leccion({"objetos": []})), (None, None))

    def test_el_avance_es_obligatorios_atendidos_sobre_obligatorios_y_no_es_una_nota(self):
        bloques = bloques_dom.bloques_de_leccion(leccion())
        self.assertEqual(bloques_dom.avance_pct(bloques, []), 0.0)
        self.assertEqual(bloques_dom.avance_pct(bloques, ["lec:s1"]), 20.0)
        self.assertEqual(bloques_dom.avance_pct(bloques, ["lec:s1", "lab", "no-existe"]), 40.0)     # lo que no existe no cuenta
        self.assertEqual(bloques_dom.avance_pct(bloques, [b["ref"] for b in bloques]), 100.0)
        self.assertEqual(bloques_dom.avance_pct([], ["x"]), 0.0)
        siete = [{"ref": str(i), "indice": i, "titulo": "", "obligatorio": True} for i in range(7)]
        self.assertEqual(bloques_dom.avance_pct(siete, ["0", "1", "2", "3"]), 57.14)                # el 57 % de «Actividad 4 de 7»

    def test_completar_exige_todos_los_obligatorios_y_dice_cuales_faltan(self):
        bloques = bloques_dom.bloques_de_leccion(leccion())
        vistos = ["lec:s1", "exp:p1", "act"]
        self.assertFalse(bloques_dom.esta_completa(bloques, vistos))
        self.assertEqual(bloques_dom.faltan(bloques, vistos), [{"ref": "lec:s2", "indice": 2, "titulo": "Presentación · 2"},
                                                               {"ref": "lab", "indice": 4, "titulo": "Laboratorio"}])
        self.assertTrue(bloques_dom.esta_completa(bloques, [b["ref"] for b in bloques]))
        opcionales = [{**b, "obligatorio": b["ref"] != "lab"} for b in bloques]
        self.assertTrue(bloques_dom.esta_completa(opcionales, ["lec:s1", "lec:s2", "exp:p1", "act"]))     # un bloque opcional no impide completar

    def test_el_progreso_es_monotono_y_las_referencias_desconocidas_se_separan(self):
        bloques = bloques_dom.bloques_de_leccion(leccion())
        self.assertEqual(bloques_dom.sumar_vistos(["a", "b"], ["b", "c"]), ["a", "b", "c"])
        self.assertEqual(bloques_dom.sumar_vistos(["a", "b"], []), ["a", "b"])                     # nunca se desatiende un bloque
        self.assertEqual(bloques_dom.clasificar_refs(bloques, ["lab", "lab", "nada", "act"]), (["lab", "act"], ["nada"]))
        self.assertEqual(bloques_dom.conservar_vistos(["lec:s1", "viejo", "act"], bloques), ["lec:s1", "act"])

    def test_el_punto_de_reanudacion_es_el_ultimo_bloque_o_el_primero_sin_atender(self):
        bloques = bloques_dom.bloques_de_leccion(leccion())
        self.assertEqual(bloques_dom.punto_de_reanudacion(bloques, ["lec:s1"], "exp:p1", 208),
                         {"ref": "exp:p1", "indice": 3, "titulo": "Resumen", "tipo": "pagina", "posicion_seg": 208})
        self.assertEqual(bloques_dom.punto_de_reanudacion(bloques, ["lec:s1"], "", None)["ref"], "lec:s2")
        self.assertIsNone(bloques_dom.punto_de_reanudacion(bloques, [], "", None))
        self.assertIsNone(bloques_dom.punto_de_reanudacion(bloques, [b["ref"] for b in bloques], "", None))

    def test_la_posicion_es_un_entero_de_segundos_o_ausente(self):
        self.assertEqual((bloques_dom.validar_posicion(None), bloques_dom.validar_posicion(""), bloques_dom.validar_posicion(208), bloques_dom.validar_posicion(3.0)),
                         (None, None, 208, 3))
        for malo in (-1, 2.5, "x", True):
            with self.assertRaises(DatosInvalidos):
                bloques_dom.validar_posicion(malo)


class PlazoTests(SimpleTestCase):
    F = 1_000_000

    def recepcion(self, plazo: str, capturado: int | None, recibido: int, cerrada_en: int | None = None, fecha: int | None = F):
        return plazo_dom.politica_de_recepcion(fecha_limite=fecha, plazo=plazo, gracia_ms=15 * MIN, cerrada_en=cerrada_en, capturado_en=capturado, recibido_en=recibido)

    def test_con_plazo_blando_siempre_se_acepta(self):
        for capturado, recibido in ((self.F - 5, self.F), (self.F + 5, self.F + 10), (self.F - 1, self.F + 999 * MIN)):
            self.assertEqual(self.recepcion(cat.BLANDO, capturado, recibido), (plazo_dom.ACEPTAR, ""))

    def test_con_plazo_endurecido_se_acepta_a_tiempo_y_dentro_de_la_gracia(self):
        self.assertEqual(self.recepcion(cat.ENDURECIDO, self.F - 10, self.F - 5), (plazo_dom.ACEPTAR, ""))
        self.assertEqual(self.recepcion(cat.ENDURECIDO, self.F - 10, self.F + 15 * MIN), (plazo_dom.ACEPTAR, ""))      # justo en el límite de la gracia

    def test_capturado_antes_pero_recibido_despues_de_la_gracia_decide_el_profesor(self):
        self.assertEqual(self.recepcion(cat.ENDURECIDO, self.F - 10, self.F + 15 * MIN + 1), (plazo_dom.DECIDE_EL_PROFESOR, cat.MOTIVO_FUERA_DE_GRACIA))

    def test_capturado_despues_del_cierre_se_rechaza_y_se_dice_por_que(self):
        self.assertEqual(self.recepcion(cat.ENDURECIDO, self.F + 1, self.F + 2), (plazo_dom.RECHAZAR, cat.MOTIVO_PLAZO_VENCIDO))
        self.assertEqual(self.recepcion(cat.ENDURECIDO, None, self.F + 2), (plazo_dom.RECHAZAR, cat.MOTIVO_PLAZO_VENCIDO))       # sin hora capturada: la de llegada

    def test_un_cierre_a_mano_cierra_incluso_con_plazo_blando_y_manda_el_primero_que_ocurra(self):
        self.assertEqual(self.recepcion(cat.BLANDO, 560, 600, cerrada_en=550), (plazo_dom.RECHAZAR, cat.MOTIVO_ASIGNACION_CERRADA))
        self.assertEqual(self.recepcion(cat.BLANDO, 560, 600, cerrada_en=550, fecha=None)[0], plazo_dom.RECHAZAR)
        self.assertEqual(self.recepcion(cat.BLANDO, 500, 550 + 2 * MIN, cerrada_en=550), (plazo_dom.ACEPTAR, ""))
        self.assertEqual(plazo_dom.cierre_efectivo(fecha_limite=self.F, plazo=cat.ENDURECIDO, cerrada_en=self.F - 10), (self.F - 10, cat.MOTIVO_ASIGNACION_CERRADA))
        self.assertEqual(plazo_dom.cierre_efectivo(fecha_limite=self.F, plazo=cat.ENDURECIDO, cerrada_en=self.F + 10), (self.F, cat.MOTIVO_PLAZO_VENCIDO))
        self.assertEqual(plazo_dom.cierre_efectivo(fecha_limite=self.F, plazo=cat.BLANDO, cerrada_en=None), (None, ""))

    def test_fuera_de_plazo_y_vencida_son_derivadas(self):
        self.assertTrue(plazo_dom.fuera_de_plazo(100, 101))
        self.assertFalse(plazo_dom.fuera_de_plazo(100, 100))
        self.assertFalse(plazo_dom.fuera_de_plazo(None, 10**15))
        self.assertTrue(plazo_dom.vencida(100, cat.EN_CURSO, 101))
        self.assertFalse(plazo_dom.vencida(100, cat.COMPLETADA, 10**15))                       # lo completado no vence
        self.assertFalse(plazo_dom.vencida(None, cat.PENDIENTE, 10**15))

    def test_la_vigencia_de_un_paquete(self):
        dia = plazo_dom.DIA_MS
        self.assertEqual(plazo_dom.vigente_hasta(fecha_limite=None, gracia_ms=15 * MIN, ahora=1_000, vigencia_dias=14), 1_000 + 14 * dia)
        self.assertEqual(plazo_dom.vigente_hasta(fecha_limite=10 * dia, gracia_ms=15 * MIN, ahora=1_000, vigencia_dias=14), 10 * dia + 15 * MIN)
        self.assertEqual(plazo_dom.vigente_hasta(fecha_limite=500, gracia_ms=0, ahora=1_000, vigencia_dias=3), 1_000 + 3 * dia)      # ya pasó: no nace vencido
        self.assertTrue(plazo_dom.paquete_vencido_por_vigencia(99, 100))
        self.assertFalse(plazo_dom.paquete_vencido_por_vigencia(100, 100))
        self.assertFalse(plazo_dom.paquete_vencido_por_vigencia(None, 10**15))
        self.assertEqual((plazo_dom.gracia_en_ms(None), plazo_dom.gracia_en_ms(5), plazo_dom.gracia_en_ms(0)), (15 * MIN, 5 * MIN, 0))


class PaqueteTests(SimpleTestCase):
    def manifiesto(self, **cambios) -> dict:
        datos = dict(paquete_id="p1", asignacion={"id": "a1", "bloques": []}, curso={"curso_ref": "c", "version": "1.0.0"}, leccion_ref="l1", vigente_hasta=2_000,
                     generado_en=1_000, leccion={"leccion_ref": "l1", "objetos": []}, archivos=[paquete_dom.archivo(media_ref="m", clase="image", mime="image/png", tamano=3, sha256="ab")],
                     no_incluidos=[paquete_dom.no_incluido("sim", cat.NO_INCLUIDO_SIMULACION)])
        return paquete_dom.construir_manifiesto(**{**datos, **cambios})

    def test_la_huella_es_el_sha256_del_json_canonico_sin_el_campo_huella(self):
        man = self.manifiesto()
        sin = {k: v for k, v in man.items() if k != "huella"}
        canonico = json.dumps(sin, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(man["huella"], hashlib.sha256(canonico).hexdigest())
        self.assertEqual(paquete_dom.huella_de(man), man["huella"])                            # con o sin el campo, la misma huella
        self.assertEqual(paquete_dom.serializar_canonico(sin), canonico)

    def test_el_json_canonico_ordena_las_claves_no_lleva_espacios_y_no_escapa_lo_que_no_es_ascii(self):
        texto = paquete_dom.serializar_canonico({"b": 1, "a": {"z": "ñandú", "y": [1, 2]}}).decode("utf-8")
        self.assertEqual(texto, '{"a":{"y":[1,2],"z":"ñandú"},"b":1}')

    def test_la_huella_no_depende_del_orden_de_las_claves_pero_si_de_cualquier_valor(self):
        uno = paquete_dom.huella_de({"a": 1, "b": [1, {"x": 1, "y": 2}]})
        self.assertEqual(uno, paquete_dom.huella_de({"b": [1, {"y": 2, "x": 1}], "a": 1}))
        self.assertNotEqual(uno, paquete_dom.huella_de({"a": 1, "b": [1, {"x": 1, "y": 3}]}))
        self.assertNotEqual(self.manifiesto()["huella"], self.manifiesto(vigente_hasta=2_001)["huella"])
        self.assertEqual(self.manifiesto()["huella"], self.manifiesto()["huella"])             # determinista

    def test_los_numeros_enteros_viajan_como_enteros_para_que_otro_serializador_llegue_a_la_misma_huella(self):
        self.assertEqual(paquete_dom.normalizar_numeros({"a": 13.0, "b": [1.5, 2.0, True, None], "c": {"d": float("inf")}, "e": "1.0"}),
                         {"a": 13, "b": [1.5, 2, True, None], "c": {"d": None}, "e": "1.0"})
        self.assertIsInstance(paquete_dom.normalizar_numeros(13.0), int)
        man = self.manifiesto(leccion={"puntos_totales": 13.0})
        self.assertEqual(man["leccion"]["puntos_totales"], 13)

    def test_el_vencimiento_es_por_vigencia_o_por_version_nueva_y_solo_si_se_sabe(self):
        self.assertEqual(paquete_dom.evaluar_vencimiento(vigente_hasta=100, ahora=101, curso_version="1.0.0", version_instalada="1.0.0"), cat.VIGENCIA)
        self.assertEqual(paquete_dom.evaluar_vencimiento(vigente_hasta=100, ahora=50, curso_version="1.0.0", version_instalada="1.1.0"), cat.VERSION_NUEVA)
        self.assertIsNone(paquete_dom.evaluar_vencimiento(vigente_hasta=100, ahora=100, curso_version="1.0.0", version_instalada="1.0.0"))
        self.assertIsNone(paquete_dom.evaluar_vencimiento(vigente_hasta=100, ahora=50, curso_version="1.0.0", version_instalada=None))   # sin biblioteca no vence por versión
        self.assertIsNone(paquete_dom.evaluar_vencimiento(vigente_hasta=None, ahora=10**15, curso_version="", version_instalada="2"))

    def test_las_simulaciones_no_se_empaquetan_y_los_totales_se_suman(self):
        self.assertTrue(paquete_dom.es_simulacion({"clase": "simulation"}))
        self.assertFalse(paquete_dom.es_simulacion({"clase": "image"}))
        self.assertFalse(paquete_dom.es_simulacion(None))
        self.assertEqual(paquete_dom.bytes_total([{"bytes": 3}, {"bytes": 4}]), 7)
        self.assertEqual(paquete_dom.resumen_de_estado([{"estado": "vencido"}, {"estado": "disponible"}, {"estado": "denegado"}]), "disponible")
        self.assertEqual(paquete_dom.resumen_de_estado([{"estado": "denegado"}]), "denegado")
        self.assertIsNone(paquete_dom.resumen_de_estado([]))


class PracticaTests(SimpleTestCase):
    @staticmethod
    def r(ref: str, secuencia: int, respuesta=None, veredicto=None, **extra) -> dict:
        return {"pregunta_ref": ref, "secuencia": secuencia, "respuesta": respuesta or {"value": True}, "veredicto": veredicto, **extra}

    @staticmethod
    def v(correcta, pendiente=False) -> dict:
        return {"puntaje": 1.0 if correcta else 0.0, "puntaje_maximo": 1.0, "correcta": correcta, "pendiente": pendiente, "retroalimentacion": []}

    def test_la_fusion_no_duplica_la_secuencia_mayor_sustituye_y_la_menor_llega_tarde(self):
        vigentes = [self.r("q1", 1), self.r("q2", 3)]
        fusionadas, res = practica_dom.fusionar(vigentes, [self.r("q1", 1), self.r("q2", 2), self.r("q3", 1), self.r("q2", 4, {"value": False})])
        self.assertEqual((res.aceptadas, res.duplicadas, res.superadas), (["q3", "q2"], ["q1"], ["q2"]))    # la 2 de q2 llega tarde (ya hay una 3); la 4 sí sustituye
        self.assertEqual([(x["pregunta_ref"], x["secuencia"]) for x in fusionadas], [("q1", 1), ("q2", 4), ("q3", 1)])
        _, res = practica_dom.fusionar([self.r("q2", 5)], [self.r("q2", 4)])
        self.assertEqual((res.aceptadas, res.superadas), ([], ["q2"]))
        self.assertTrue(all("sesion_usuario_id" not in x for x in fusionadas))               # el rastro del aula no se guarda

    def test_normalizar_rechaza_pregunta_por_pregunta(self):
        limpias, rechazadas = practica_dom.normalizar_respuestas([
            {"pregunta_ref": "q1", "respuesta": {"value": True}, "secuencia": 2, "capturada_en": 55}, {"pregunta_ref": "q2", "respuesta": {}, "secuencia": 1},
            {"pregunta_ref": "q3", "respuesta": {"value": True}, "secuencia": 0}, {"respuesta": {"value": True}, "secuencia": 1}, "no soy un objeto",
            {"pregunta_ref": "q4", "respuesta": {"value": True}, "secuencia": True}])
        self.assertEqual(limpias, [{"pregunta_ref": "q1", "respuesta": {"value": True}, "secuencia": 2, "capturada_en": 55}])
        self.assertEqual([x["pregunta_ref"] for x in rechazadas], ["q2", "q3", "", "", "q4"])
        with self.assertRaises(DatosInvalidos):
            practica_dom.normalizar_respuestas("x")
        with self.assertRaises(DatosInvalidos):
            practica_dom.normalizar_respuestas([{"pregunta_ref": str(i), "respuesta": {"a": 1}, "secuencia": 1} for i in range(201)])

    def test_los_aciertos_cuentan_solo_las_correctas_y_lo_pendiente_no_es_una_nota(self):
        respuestas = [self.r("q1", 1, veredicto=self.v(True)), self.r("q2", 1, veredicto=self.v(False)), self.r("q3", 1, veredicto=self.v(None, pendiente=True)),
                      self.r("q4", 1)]
        self.assertEqual(practica_dom.aciertos(respuestas), 1)
        self.assertEqual(practica_dom.sin_calificar(respuestas), 2)
        self.assertEqual([x["pregunta_ref"] for x in practica_dom.por_calificar(respuestas)], ["q4"])
        self.assertEqual(practica_dom.totales(respuestas), (1.0, 2.0))
        self.assertEqual(practica_dom.resumen(respuestas, 8), {"respondidas": 4, "aciertos": 1, "total_preguntas": 8, "sin_calificar": 2})
        self.assertEqual(practica_dom.totales([self.r("q", 1)]), (None, None))

    def test_el_resultado_y_su_mensaje(self):
        def resultado(correctas: int, total: int, sin: int = 0):
            respuestas = [self.r(f"q{i}", 1, veredicto=self.v(i < correctas)) for i in range(total - sin)] + [self.r(f"s{i}", 1) for i in range(sin)]
            return practica_dom.resultado_de(respuestas, total)
        r = resultado(7, 8)
        self.assertEqual((r["correctas"], r["total"], r["porcentaje"], r["mensaje"], r["sin_calificar"]), (7, 8, 87.5, "¡Muy bien!", 0))
        self.assertEqual(resultado(5, 8)["mensaje"], "¡Buen avance!")                                # 62,5 %
        self.assertEqual(resultado(4, 8)["mensaje"], "Sigue practicando: puedes intentarlo otra vez")    # 50 %
        self.assertEqual(resultado(6, 10)["mensaje"], "¡Buen avance!")                                # justo 60 %
        self.assertEqual(resultado(0, 8, sin=8)["mensaje"], practica_dom.MENSAJE_GUARDADO)              # nada calificado: no se inventa
        self.assertEqual(practica_dom.resultado_de([], 8)["mensaje"], practica_dom.MENSAJE_SIN_RESPUESTAS)
        self.assertIsNone(practica_dom.resultado_de([], 0)["porcentaje"])
        self.assertEqual(set(resultado(1, 2)["revision"][0]), {"pregunta_ref", "correcta", "retroalimentacion"})

    def test_un_veredicto_viejo_no_pisa_a_una_respuesta_mas_nueva(self):
        respuestas = [self.r("q1", 3)]
        actualizadas, aplicados = practica_dom.aplicar_veredictos(respuestas, {"q1": (2, {"puntaje": 1.0, "puntaje_maximo": 1.0, "correcta": True, "pendiente": False,
                                                                                           "retroalimentacion": [], "requiere_correccion_manual": False})})
        self.assertEqual((aplicados, actualizadas[0]["veredicto"]), ([], None))
        actualizadas, aplicados = practica_dom.aplicar_veredictos(respuestas, {"q1": (3, {"puntaje": 1.0, "puntaje_maximo": 1.0, "correcta": True, "pendiente": False,
                                                                                          "retroalimentacion": ["bien"], "requiere_correccion_manual": False})})
        self.assertEqual(aplicados, ["q1"])
        self.assertEqual(actualizadas[0]["veredicto"], {"puntaje": 1.0, "puntaje_maximo": 1.0, "correcta": True, "pendiente": False, "retroalimentacion": ["bien"]})
        self.assertEqual(practica_dom.veredicto_publico(actualizadas[0])["pregunta_ref"], "q1")

    def test_el_resumen_de_la_tarea_toma_la_mejor_y_la_ultima_de_las_terminadas(self):
        def p(numero, estado, aciertos, total=8):
            return {"numero": numero, "estado": estado, "aciertos": aciertos, "total_preguntas": total}
        self.assertEqual(practica_dom.resumen_de_practicas([p(1, "terminada", 7), p(2, "terminada", 6), p(3, "en_curso", 8)]),
                         {"practica_intentos": 3, "practica_mejor": 7, "practica_ultima": 6, "practica_total": 8})
        self.assertEqual(practica_dom.resumen_de_practicas([], 6), {"practica_intentos": 0, "practica_mejor": None, "practica_ultima": None, "practica_total": 6})
        self.assertEqual(practica_dom.siguiente_numero([p(1, "terminada", 1), p(4, "terminada", 1)]), 5)
        self.assertEqual(practica_dom.siguiente_numero([]), 1)


class SyncTests(SimpleTestCase):
    def test_el_evento_exige_una_secuencia_valida_lo_demas_se_valida_al_integrar(self):
        ev = sync_dom.normalizar_evento({"secuencia": 5, "tipo": "study.block.viewed", "ocurrido_en": 100, "ocurrido_en_tableta": 90, "carga": {"a": 1}})
        self.assertEqual(ev, {"secuencia": 5, "tipo": "study.block.viewed", "ocurrido_en": 100, "ocurrido_en_tableta": 90, "carga": {"a": 1}})
        self.assertIsNone(sync_dom.normalizar_evento({"secuencia": 1, "tipo": "x", "carga": None})["ocurrido_en"])
        for malo in ({"tipo": "x"}, {"secuencia": 0}, {"secuencia": "a"}, {"secuencia": True}, "no soy un objeto", None):
            with self.assertRaises(DatosInvalidos):
                sync_dom.normalizar_evento(malo)

    def test_la_carga_de_cada_tipo(self):
        vista = sync_dom.validar_carga(cat.T_BLOQUE_VISTO, {"asignacion_id": "a", "bloques_vistos": ["x", "y"], "bloque_actual": "y", "posicion_seg": 12})
        self.assertEqual(vista, {"asignacion_id": "a", "bloques_vistos": ["x", "y"], "bloque_actual": "y", "posicion_seg": 12})
        respuesta = sync_dom.validar_carga(cat.T_RESPUESTA_ENVIADA, {"asignacion_id": "a", "objeto_ref": "o", "intento_numero": 2, "pregunta_ref": "q",
                                                                      "respuesta": {"value": True}, "secuencia_respuesta": 4})
        self.assertEqual((respuesta["intento_numero"], respuesta["secuencia_respuesta"], respuesta["respuesta"]), (2, 4, {"value": True}))
        self.assertEqual(sync_dom.validar_carga(cat.T_PRACTICA_TERMINADA, {"asignacion_id": "a", "objeto_ref": "o", "intento_numero": 1})["intento_numero"], 1)
        self.assertEqual(sync_dom.validar_carga(cat.T_LECCION_COMPLETADA, {"asignacion_id": "a"}), {"asignacion_id": "a"})
        malos = [(cat.T_BLOQUE_VISTO, {"bloques_vistos": ["x"]}), (cat.T_BLOQUE_VISTO, {"asignacion_id": "a"}), (cat.T_BLOQUE_VISTO, {"asignacion_id": "a", "bloques_vistos": "x"}),
                 (cat.T_RESPUESTA_ENVIADA, {"asignacion_id": "a", "objeto_ref": "o", "intento_numero": 0, "pregunta_ref": "q", "respuesta": {"a": 1}, "secuencia_respuesta": 1}),
                 (cat.T_RESPUESTA_ENVIADA, {"asignacion_id": "a", "objeto_ref": "o", "intento_numero": 1, "pregunta_ref": "q", "respuesta": {}, "secuencia_respuesta": 1}),
                 (cat.T_PRACTICA_TERMINADA, {"asignacion_id": "a", "objeto_ref": "o"}), ("study.otra", {"asignacion_id": "a"}), (cat.T_LECCION_COMPLETADA, "x")]
        for tipo, carga in malos:
            with self.subTest(tipo=tipo, carga=carga), self.assertRaises(DatosInvalidos):
                sync_dom.validar_carga(tipo, carga)

    def test_de_lo_integrado_no_se_conserva_el_contenido_de_las_respuestas(self):
        self.assertEqual(sync_dom.resumen_de_carga({"asignacion_id": "a", "pregunta_ref": "q", "respuesta": {"text": "mi respuesta"}}),
                         {"asignacion_id": "a", "pregunta_ref": "q"})
        self.assertEqual(sync_dom.resumen_de_carga("no es un dict"), {})

    def test_el_orden_el_resumen_y_los_conteos_del_aparato(self):
        self.assertEqual([e["secuencia"] for e in sync_dom.ordenar([{"secuencia": 3}, {"secuencia": 1}, {"secuencia": 2}])], [1, 2, 3])
        resultados = [{"estado": "integrado"}, {"estado": "integrado"}, {"estado": "duplicado"}, {"estado": "rechazado"}, {"estado": "pendiente_decision"}]
        self.assertEqual(sync_dom.contar(resultados), {"integrados": 2, "duplicados": 1, "rechazados": 1, "pendientes_decision": 1})
        self.assertEqual(sync_dom.conteos_del_aparato([{"estado": "integrado"}, {"estado": "rechazado"}, {"estado": "rechazado"}, {"estado": "pendiente_decision"}]),
                         {"synced": 1, "rejected": 2, "conflict": 1})
        self.assertEqual(sync_dom.normalizar_emisor(" e1 "), "e1")
        for malo in ("", None, "x" * 65):
            with self.assertRaises(DatosInvalidos):
                sync_dom.normalizar_emisor(malo)
        self.assertEqual(len(sync_dom.validar_envio([{}] * 200)), 200)
        with self.assertRaises(DatosInvalidos):
            sync_dom.validar_envio([{}] * 201)
        self.assertEqual(sync_dom.validar_envio(None), [])


class AsignacionDominioTests(SimpleTestCase):
    def nueva(self, **extra) -> dict:
        return {"alcance": "grupo", "grupo_id": "g1", "curso_ref": "c", "leccion_ref": "l", **extra}

    def test_una_asignacion_nueva_se_normaliza_con_sus_valores_por_defecto(self):
        n = asignacion_dom.validar_nueva(self.nueva())
        self.assertEqual((n["alcance"], n["plazo"], n["gracia_ms"], n["paquete_permitido"], n["fecha_limite"], n["alumnos"]), ("grupo", "blando", 900_000, True, None, []))
        n = asignacion_dom.validar_nueva(self.nueva(alcance="seleccion", alumnos=["a", "b", "a"], gracia_min=0, plazo="endurecido", fecha_limite=123, paquete_permitido=False))
        self.assertEqual((n["alumnos"], n["gracia_ms"], n["plazo"], n["fecha_limite"], n["paquete_permitido"]), (["a", "b"], 0, "endurecido", 123, False))
        self.assertEqual(asignacion_dom.validar_nueva({"alumnos": ["a"], "curso_ref": "c", "leccion_ref": "l"})["alcance"], "seleccion")    # sin alcance: por los alumnos

    def test_lo_mal_formado_se_rechaza(self):
        malos = [{"alcance": "curso"}, {"grupo_id": ""}, {"alcance": "seleccion", "alumnos": []}, {"alcance": "seleccion", "alumnos": ["x" * 65]}, {"plazo": "eterno"},
                 {"gracia_min": -1}, {"gracia_min": 99999}, {"fecha_limite": 0}, {"fecha_limite": "ayer"}, {"curso_ref": ""}, {"leccion_ref": ""}, {"fuente": "otra"},
                 {"paquete_permitido": "si"}, {"titulo": "x" * 251}]
        for extra in malos:
            with self.subTest(extra=extra), self.assertRaises(DatosInvalidos):
                asignacion_dom.validar_nueva(self.nueva(**extra))

    def test_los_cambios_traen_solo_lo_presente_y_quitar_la_fecha_es_posible(self):
        self.assertEqual(asignacion_dom.validar_cambios({"plazo": "endurecido", "gracia_min": 5}), {"plazo": "endurecido", "gracia_ms": 300_000})
        self.assertEqual(asignacion_dom.validar_cambios({"fecha_limite": None}), {"fecha_limite": None})
        self.assertEqual(asignacion_dom.validar_cambios({"quitar_fecha": True}), {"fecha_limite": None})
        self.assertEqual(asignacion_dom.validar_cambios({"titulo": " Nuevo ", "consigna": "", "paquete_permitido": False}),
                         {"titulo": "Nuevo", "consigna": "", "paquete_permitido": False})
        for malo in ({}, {"titulo": ""}, {"plazo": "nunca"}, {"paquete_permitido": "no"}, {"fecha_limite": -1}):
            with self.subTest(malo=malo), self.assertRaises(DatosInvalidos):
                asignacion_dom.validar_cambios(malo)

    def test_la_decision_del_profesor(self):
        self.assertEqual(asignacion_dom.validar_decision({"alumno_id": "a", "secuencia": 3, "decision": "aceptar"}),
                         {"alumno_id": "a", "secuencia": 3, "emisor_id": None, "decision": "aceptar"})
        for malo in ({"alumno_id": "a", "secuencia": 3}, {"alumno_id": "a", "decision": "aceptar"}, {"secuencia": 3, "decision": "aceptar"},
                     {"alumno_id": "a", "secuencia": 0, "decision": "aceptar"}, {"alumno_id": "a", "secuencia": 3, "decision": "quizas"}):
            with self.subTest(malo=malo), self.assertRaises(DatosInvalidos):
                asignacion_dom.validar_decision(malo)
