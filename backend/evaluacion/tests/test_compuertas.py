"""
Las compuertas de resultado de MOD-010 (`aplicacion/compuertas.py`): el puerto por el que otro módulo puede RETENER un resultado que la política de publicación ya mostraría.
Puras: no necesitan la base ni la biblioteca. Que el libro de calificaciones registre la suya se prueba en `gradebook/tests/test_compuerta_de_resultados.py`.
"""
from __future__ import annotations

from unittest import TestCase, mock

from ..aplicacion import compuertas
from ..aplicacion.motor import Motor
from ..dominio import catalogos as cat

CALIFICADO = {"id": "i-1", "alumno_id": "a-1", "estado": cat.CALIFICADO, "calificacion_pendiente": False, "liberado_en": None}
AL_ENTREGAR = {"id": "x-1", "resultados": cat.AL_ENTREGAR, "liberados_en": None}
TRAS_LIBERAR = {"id": "x-2", "resultados": cat.TRAS_LIBERAR, "liberados_en": None}


class CompuertasTests(TestCase):
    def setUp(self):
        parche = mock.patch.dict(compuertas._COMPUERTAS, {}, clear=True)         # cada prueba parte sin compuertas (y recupera las registradas al terminar)
        parche.start()
        self.addCleanup(parche.stop)

    def test_sin_compuertas_mod010_se_comporta_como_siempre(self):
        self.assertTrue(Motor.resultado_disponible(AL_ENTREGAR, CALIFICADO))
        self.assertFalse(Motor.resultado_disponible(TRAS_LIBERAR, CALIFICADO))
        self.assertIsNone(Motor.resultado_retenido_por(AL_ENTREGAR, CALIFICADO))

    def test_una_compuerta_que_retiene_cierra_lo_que_la_politica_abre_y_dice_cual(self):
        compuertas.registrar("otra", lambda asignacion, intento: False)
        self.assertFalse(Motor.resultado_disponible(AL_ENTREGAR, CALIFICADO))
        self.assertEqual(Motor.resultado_retenido_por(AL_ENTREGAR, CALIFICADO), "otra")

    def test_una_compuerta_que_deja_pasar_no_cambia_nada(self):
        compuertas.registrar("abierta", lambda asignacion, intento: True)
        self.assertTrue(Motor.resultado_disponible(AL_ENTREGAR, CALIFICADO))

    def test_una_compuerta_nunca_abre_lo_que_la_politica_mantiene_cerrado(self):
        compuertas.registrar("abierta", lambda asignacion, intento: True)
        self.assertFalse(Motor.resultado_disponible(TRAS_LIBERAR, CALIFICADO))                      # sin liberar
        self.assertFalse(Motor.resultado_disponible({**AL_ENTREGAR, "resultados": cat.NUNCA}, CALIFICADO))
        self.assertFalse(Motor.resultado_disponible(AL_ENTREGAR, {**CALIFICADO, "estado": cat.EN_REVISION}))

    def test_la_compuerta_sólo_se_consulta_cuando_la_politica_ya_lo_mostraria(self):
        consultas = []
        compuertas.registrar("cuenta", lambda asignacion, intento: consultas.append(intento["id"]) or True)
        Motor.resultado_disponible(TRAS_LIBERAR, CALIFICADO)                                         # cerrado por la política: ni se pregunta
        self.assertEqual(consultas, [])
        Motor.resultado_disponible(AL_ENTREGAR, CALIFICADO)
        self.assertEqual(consultas, ["i-1"])

    def test_una_compuerta_que_falla_cierra_y_no_abre(self):
        def rota(asignacion, intento):
            raise RuntimeError("fallo")

        compuertas.registrar("rota", rota)
        with self.assertLogs("avacom.evaluacion.compuertas", level="ERROR"):
            self.assertFalse(Motor.resultado_disponible(AL_ENTREGAR, CALIFICADO))
        with self.assertLogs("avacom.evaluacion.compuertas", level="ERROR"):
            self.assertEqual(Motor.resultado_retenido_por(AL_ENTREGAR, CALIFICADO), "rota")

    def test_registrar_dos_veces_el_mismo_nombre_reemplaza_no_duplica(self):
        compuertas.registrar("x", lambda asignacion, intento: False)
        compuertas.registrar("x", lambda asignacion, intento: True)
        self.assertEqual(compuertas.registradas(), ("x",))
        self.assertTrue(Motor.resultado_disponible(AL_ENTREGAR, CALIFICADO))
