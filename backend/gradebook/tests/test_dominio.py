"""
El dominio del Gradebook, sin base de datos ni HTTP: la escala interna de 0 a 100 con `Decimal` (precisión y redondeo deterministas), el motor de escalas con sus
plantillas por país, la rúbrica y lo que se deduce de los intentos (estado simple, intento que cuenta, agregados). Una actividad pendiente nunca es un cero.
"""
from __future__ import annotations

from decimal import Decimal as D

from django.test import SimpleTestCase

from ..dominio import catalogos as cat
from ..dominio import escala as esc
from ..dominio import plantillas_escalas as plantillas
from ..dominio import puntaje as pj
from ..dominio import resultado as res
from ..dominio import rubrica as rub
from ..dominio.errores import DatosInvalidos, EscalaInvalida, PuntajeInvalido


class PuntajeTests(SimpleTestCase):
    def test_una_puntuacion_interna_va_de_0_a_100_con_dos_decimales(self):
        for bueno, esperado in ((0, "0.00"), (100, "100.00"), (85, "85.00"), ("85.5", "85.50"), (85.25, "85.25"), (D("70"), "70.00"), ("85,5", "85.50")):
            self.assertEqual(str(pj.validar_interno(bueno)), esperado)
        for malo in (-0.01, 100.01, 85.123, "85.125", True, False, None, "", "  ", "abc", float("nan"), float("inf"), [], {}):
            with self.assertRaises(PuntajeInvalido, msg=repr(malo)):
                pj.validar_interno(malo)

    def test_los_float_no_ensucian_los_decimales(self):
        self.assertEqual(pj.a_decimal(85.3), D("85.3"))                  # no 85.2999999999999971578…
        self.assertEqual(pj.validar_interno(70.3), D("70.30"))
        self.assertEqual(pj.a_decimal(0.1 + 0.2), D("0.30000000000000004"))             # lo que el float realmente guarda: por eso nada se calcula con float

    def test_el_porcentaje_de_mod_010_se_normaliza_con_mitad_arriba(self):
        for crudo, esperado in ((84.995, "85.00"), (71.4286, "71.43"), (83.3333, "83.33"), (0.004, "0.00"), (0.005, "0.01"), (100.0, "100.00"), (0, "0.00")):
            self.assertEqual(str(pj.interno_desde_porcentaje(crudo)), esperado, crudo)
        for fuera in (100.0001, -0.0001):
            with self.assertRaises(PuntajeInvalido):
                pj.interno_desde_porcentaje(fuera)

    def test_las_reglas_de_redondeo_son_deterministas(self):
        esperados = {cat.MITAD_ARRIBA: ["3", "3", "4"], cat.MITAD_PAR: ["2", "3", "4"], cat.ABAJO: ["2", "2", "3"], cat.ARRIBA: ["3", "3", "4"]}
        for regla, lista in esperados.items():
            self.assertEqual([str(pj.redondear(D(x), 0, regla)) for x in ("2.5", "2.51", "3.5")], lista, regla)
        self.assertEqual(str(pj.redondear(D("4.55"), 1, cat.MITAD_ARRIBA)), "4.6")
        self.assertEqual(str(pj.redondear(D("4.55"), 1, cat.MITAD_PAR)), "4.6")
        self.assertEqual(str(pj.redondear(D("4.45"), 1, cat.MITAD_PAR)), "4.4")
        self.assertEqual(str(pj.redondear(D("4.59"), 1, cat.ABAJO)), "4.5")
        self.assertEqual(str(pj.redondear(D("4.51"), 1, cat.ARRIBA)), "4.6")
        self.assertEqual(pj.redondear(D("7.123456"), 3, cat.MITAD_ARRIBA), pj.redondear(D("7.123456"), 3, cat.MITAD_ARRIBA))
        with self.assertRaises(ValueError):
            pj.redondear(D("1"), 2, "al_ojo")

    def test_el_promedio_de_nada_no_es_cero(self):
        self.assertIsNone(pj.promedio([]))
        self.assertEqual(pj.promedio([D("70"), D("85.5")]), D("77.75"))
        self.assertEqual(pj.promedio([D("1"), D("2"), D("2")]), D("1.67"))


class PlantillasTests(SimpleTestCase):
    def test_toda_plantilla_es_una_escala_valida_que_cubre_0_a_100(self):
        self.assertGreaterEqual(len(plantillas.PLANTILLAS), 15)
        for p in plantillas.PLANTILLAS:
            self.assertEqual(esc.validar(p.definicion), [], p.codigo)
            for x in ("0", "0.01", "25", "49.99", "50", "59.99", "60", "69.99", "70", "89.99", "90", "99.99", "100"):
                presentacion = esc.convertir(D(x), p.definicion)                     # nunca queda un resultado sin equivalencia
                self.assertTrue(presentacion.etiqueta, (p.codigo, x))
        self.assertEqual({p.pais for p in plantillas.PLANTILLAS} - {""}, {"ES", "US", "MX", "CO", "CL", "PE", "EC"})

    def test_el_ejemplo_lineal_del_documento(self):
        """100→5,0 · 80→4,0 · 60→3,0 · 40→2,0 (0–5) y 10,0 · 8,0 · 6,0 · 4,0 (0–10): conversiones lineales ilustrativas, no criterios oficiales de aprobación."""
        e5, e10 = plantillas.plantilla("gen-0-5").definicion, plantillas.plantilla("gen-0-10").definicion
        for interno, v5, v10 in ((100, "5.0", "10.0"), (80, "4.0", "8.0"), (60, "3.0", "6.0"), (40, "2.0", "4.0")):
            self.assertEqual((esc.convertir(D(interno), e5).etiqueta, esc.convertir(D(interno), e10).etiqueta), (v5, v10))
            self.assertIsNone(esc.convertir(D(interno), e5).cumple_criterio)         # una escala genérica NO inventa un criterio de aprobación

    def test_chile_tiene_su_exigencia_del_60_por_ciento(self):
        cl = plantillas.plantilla("cl-1-7").definicion
        self.assertEqual([esc.convertir(D(x), cl).etiqueta for x in (0, 30, 60, 80, 100)], ["1.0", "2.5", "4.0", "5.5", "7.0"])
        self.assertEqual([esc.convertir(D(x), cl).cumple_criterio for x in (58, 60)], [False, True])
        self.assertEqual(esc.convertir(D(59), cl).etiqueta, "4.0")                       # 3,95 se redondea al décimo, como en los establecimientos chilenos

    def test_colombia_ecuador_y_espana_no_aprueban_por_redondeo(self):
        co, ec, es = (plantillas.plantilla(c).definicion for c in ("co-1-5", "ec-0-10", "es-0-10"))
        self.assertEqual((esc.convertir(D("49.9"), co).etiqueta, esc.convertir(D("49.9"), co).cumple_criterio, esc.convertir(D("49.9"), co).nivel_desempeno), ("2.9", False, "Bajo"))
        self.assertEqual((esc.convertir(D("50"), co).etiqueta, esc.convertir(D("50"), co).cumple_criterio), ("3.0", True))
        self.assertEqual((esc.convertir(D("69.99"), ec).etiqueta, esc.convertir(D("69.99"), ec).cumple_criterio, esc.convertir(D("69.99"), ec).desempeno_clave), ("6.99", False, "PAAR"))
        self.assertEqual((esc.convertir(D("70"), ec).etiqueta, esc.convertir(D("70"), ec).cumple_criterio, esc.convertir(D("70"), ec).desempeno_clave), ("7.00", True, "AAR"))
        self.assertEqual((esc.convertir(D("49.9"), es).cumple_criterio, esc.convertir(D("49.9"), es).desempeno_clave), (False, "IN"))
        self.assertEqual((esc.convertir(D("90"), es).etiqueta, esc.convertir(D("90"), es).desempeno_clave), ("9.0", "SB"))

    def test_estados_unidos_usa_letras_y_peru_literal_no_define_aprobacion(self):
        us = plantillas.plantilla("us-letras").definicion
        self.assertEqual([esc.convertir(D(x), us).etiqueta for x in ("59.99", "60", "69.99", "70", "89.99", "90", "100")], ["F", "D", "D", "C", "B", "A", "A"])
        self.assertEqual(esc.convertir(D("95"), us).nivel_desempeno, "Sobresaliente")
        pe = plantillas.plantilla("pe-literal").definicion
        self.assertEqual([esc.convertir(D(x), pe).etiqueta for x in (0, 54.99, 55, 70, 90, 100)], ["C", "C", "B", "A", "AD", "AD"])
        self.assertIsNone(esc.convertir(D(95), pe).cumple_criterio)                  # la evaluación por competencias es una valoración, no un umbral aritmético

    def test_la_valoracion_docente_cambia_el_desempeno_no_el_resultado_interno(self):
        co = plantillas.plantilla("co-1-5").definicion
        calculada = esc.presentar(D("50"), co)
        valorada = esc.presentar(D("50"), co, "alto")
        self.assertEqual((calculada["desempeno"]["origen"], valorada["desempeno"]["origen"], valorada["desempeno"]["clave"]), ("calculo", "docente", "alto"))
        self.assertEqual((valorada["interno"], valorada["presentada"]), (calculada["interno"], calculada["presentada"]))
        pe = plantillas.plantilla("pe-literal").definicion                           # sin números: la valoración fija también la etiqueta
        self.assertEqual(esc.presentar(D("50"), pe, "A")["presentada"]["etiqueta"], "A")
        self.assertEqual(esc.presentar(D("50"), pe)["presentada"]["etiqueta"], "C")

    def test_la_huella_cambia_con_la_definicion_y_no_con_el_orden_de_las_claves(self):
        d = plantillas.plantilla("gen-0-10").definicion
        self.assertEqual(esc.huella(d), esc.huella(esc.desde_dict(esc.a_dict(d))))
        self.assertNotEqual(esc.huella(d), esc.huella(plantillas.plantilla("gen-0-5").definicion))

    def test_convertir_rechaza_lo_que_no_es_interno_y_las_escalas_que_no_se_pueden_defender(self):
        d = plantillas.plantilla("gen-0-10").definicion
        for malo in (D("-1"), D("100.01")):
            with self.assertRaises(PuntajeInvalido):
                esc.convertir(malo, d)
        roto = esc.DefinicionEscala(tipo=cat.ALFABETICA, conversion=cat.TRAMOS, tramos=(esc.Tramo(1, "A", "A", D(0), D(50)),))
        with self.assertRaises(EscalaInvalida):
            esc.convertir(D(10), roto)


class RubricaTests(SimpleTestCase):
    RUBRICA = [{"id": "r1", "criterion": "Menciona el gas", "points": 1}, {"id": "r2", "criterion": "Explica el movimiento", "points": 2}]

    def test_aplicar_una_rubrica_suma_los_criterios(self):
        rubrica = rub.normalizar_rubrica(self.RUBRICA)
        total, maximo, detalle = rub.aplicar(rubrica, [{"criterio_id": "r1", "puntos": 1}, {"criterio_id": "r2", "puntos": 1.5}], D(3))
        self.assertEqual((total, maximo), (D("2.5"), D(3)))
        self.assertEqual([d["puntos"] for d in detalle], [1.0, 1.5])

    def test_lo_incoherente_con_la_rubrica_se_rechaza(self):
        rubrica = rub.normalizar_rubrica(self.RUBRICA)
        for aplicados in ([], None, "x", [1], [{"criterio_id": "r9", "puntos": 1}], [{"criterio_id": "r1", "puntos": 1}], [{"criterio_id": "r1", "puntos": 2}, {"criterio_id": "r2", "puntos": 0}],
                          [{"criterio_id": "r1", "puntos": -1}, {"criterio_id": "r2", "puntos": 0}], [{"criterio_id": "r1", "puntos": 1}] * 2,
                          [{"criterio_id": "r1", "puntos": 0.001}, {"criterio_id": "r2", "puntos": 0}]):
            with self.assertRaises(DatosInvalidos, msg=repr(aplicados)):
                rub.aplicar(rubrica, aplicados, D(3))
        with self.assertRaises(DatosInvalidos):
            rub.aplicar([], [{"criterio_id": "r1", "puntos": 1}])
        with self.assertRaises(DatosInvalidos):                                       # el total no supera lo que vale la pregunta
            rub.aplicar(rubrica, [{"criterio_id": "r1", "puntos": 1}, {"criterio_id": "r2", "puntos": 2}], D(2))

    def test_la_forma_de_revision(self):
        self.assertEqual(res.forma_de_revision("open", {"text": "x"}), "abierta")
        self.assertEqual(res.forma_de_revision("open", {"drawingRef": "mod14://d/1"}), "dibujo")
        self.assertEqual(res.forma_de_revision("drawing", None), "dibujo")
        self.assertEqual(res.forma_de_revision("project", None), "proyecto")
        self.assertEqual(res.forma_de_revision("assignment", {"text": "x"}), "proyecto")


def _c(id_, numero, puntaje, estado=cat.REVISADA):
    return {"id": id_, "numero_intento": numero, "puntaje_efectivo": D(str(puntaje)), "estado": estado}


class ResultadoTests(SimpleTestCase):
    def test_estado_simple(self):
        i = lambda estado: {"estado": estado}      # noqa: E731
        self.assertEqual(res.estado_simple([]), cat.NO_INICIADO)
        self.assertEqual(res.estado_simple([i("no_iniciado")]), cat.NO_INICIADO)
        for vivo in ("en_curso", "pausado_desconexion", "restaurando", "en_curso_fuera_de_plazo"):
            self.assertEqual(res.estado_simple([i(vivo)]), cat.EN_PROGRESO)
        for entregado in ("entregado", "en_revision_docente", "calificado"):
            self.assertEqual(res.estado_simple([i(entregado)]), cat.COMPLETADO)
        self.assertEqual(res.estado_simple([i("calificado"), i("en_curso")]), cat.COMPLETADO)       # un segundo intento en curso no deshace lo completado
        self.assertEqual(res.estado_simple([i("anulado")]), cat.NO_INICIADO)

    def test_una_actividad_pendiente_nunca_es_un_cero(self):
        self.assertEqual(res.estado_de_intento(None), cat.PENDIENTE)
        self.assertEqual(res.estado_de_intento({"estado": "en_revision_docente", "porcentaje": None}), cat.PENDIENTE)
        self.assertEqual(res.estado_de_intento({"estado": "en_revision_docente", "porcentaje": 40.0}), cat.PROVISIONAL)
        self.assertEqual(res.estado_de_intento({"estado": "entregado", "porcentaje": None, "calificacion_pendiente": True}), cat.PENDIENTE)
        self.assertEqual(res.estado_de_intento({"estado": "calificado", "porcentaje": 0.0, "calificacion_pendiente": False}), cat.SIN_REGISTRO)
        r = res.calcular_resultado([{"estado": "en_curso", "numero": 1}], [], cat.ULTIMO)
        self.assertEqual((r.estado_calificacion, r.puntaje_aplicable, r.calificacion_aplicable_id), (cat.PENDIENTE, None, None))

    def test_la_politica_de_intentos_es_configurable(self):
        cs = [_c("a", 1, 80), _c("b", 2, 60), _c("c", 3, 70)]
        self.assertEqual(res.seleccionar_aplicable(cat.ULTIMO, cs), ("c", D("70")))
        self.assertEqual(res.seleccionar_aplicable(cat.PRIMERO, cs), ("a", D("80")))
        self.assertEqual(res.seleccionar_aplicable(cat.MEJOR, cs), ("a", D("80")))
        self.assertEqual(res.seleccionar_aplicable(cat.PROMEDIO, cs), (None, D("70.00")))
        self.assertEqual(res.seleccionar_aplicable("inventada", cs), ("c", D("70")))                  # lo desconocido cae en el provisional documentado
        self.assertEqual(res.seleccionar_aplicable(cat.ULTIMO, []), (None, None))
        # Lo reabierto o anulado no cuenta.
        self.assertEqual(res.seleccionar_aplicable(cat.ULTIMO, [_c("a", 1, 80), _c("b", 2, 10, cat.ANULADA), _c("c", 3, 20, cat.REABIERTA)]), ("a", D("80")))
        self.assertEqual(cat.POLITICA_PROVISIONAL, cat.ULTIMO)

    def test_el_estado_del_resultado_sigue_a_la_calificacion_que_cuenta(self):
        intentos = [{"estado": "calificado", "numero": 1, "porcentaje": 80.0}, {"estado": "calificado", "numero": 2, "porcentaje": 60.0}]
        r = res.calcular_resultado(intentos, [_c("a", 1, 80, cat.DEFINITIVA), _c("b", 2, 60)], cat.ULTIMO)
        self.assertEqual((r.estado_calificacion, r.publicada, r.calificacion_aplicable_id), (cat.REVISADO, False, "b"))
        r = res.calcular_resultado(intentos, [_c("a", 1, 80, cat.DEFINITIVA), _c("b", 2, 60)], cat.PRIMERO)
        self.assertEqual((r.estado_calificacion, r.publicada), (cat.DEFINITIVO, True))
        r = res.calcular_resultado(intentos, [_c("a", 1, 80, cat.DEFINITIVA), _c("b", 2, 60)], cat.PROMEDIO)
        self.assertEqual((r.estado_calificacion, r.puntaje_aplicable), (cat.REVISADO, D("70.00")))      # promedia sólo lo registrado; no es definitivo si algo no lo es
        r = res.calcular_resultado(intentos[:1], [_c("a", 1, 80, cat.REABIERTA)], cat.ULTIMO)
        self.assertEqual((r.estado_calificacion, r.puntaje_aplicable), (cat.REABIERTO, None))
        r = res.calcular_resultado([{"estado": "anulado", "numero": 1}], [], cat.ULTIMO)
        self.assertEqual(r.estado_calificacion, cat.ANULADO)

    def test_el_agregado_promedia_solo_lo_registrado_y_no_es_oficial(self):
        filas = [{"puntaje_aplicable": D("80"), "estado_calificacion": cat.DEFINITIVO, "publicada": True, "cuenta": True},
                 {"puntaje_aplicable": D("60"), "estado_calificacion": cat.REVISADO, "publicada": False, "cuenta": True},
                 {"puntaje_aplicable": D("10"), "estado_calificacion": cat.REVISADO, "publicada": False, "cuenta": False},            # formativa: no cuenta para lo oficial
                 {"puntaje_aplicable": None, "estado_calificacion": cat.PENDIENTE, "publicada": False, "cuenta": True},
                 {"puntaje_aplicable": None, "estado_calificacion": cat.PROVISIONAL, "publicada": False, "cuenta": True}]
        a = res.calcular_agregado(filas)
        self.assertEqual((a.calificaciones, a.promedio_simple, a.pendientes, a.provisionales, a.publicadas), (2, D("70.00"), 1, 1, 1))
        vacio = res.calcular_agregado([{"puntaje_aplicable": None, "estado_calificacion": cat.PENDIENTE, "publicada": False}])
        self.assertEqual((vacio.calificaciones, vacio.promedio_simple), (0, None))                  # sin nada registrado no hay promedio: nunca un cero
