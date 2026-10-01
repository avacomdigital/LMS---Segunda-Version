"""
El agregado más crítico (ENT-012), sin base de datos: los nueve estados del Maestro, el reloj del nodo con su congelamiento y la regla que no admite
excepción —ninguna flecha hacia `anulado` parte del sistema (INV-018)—.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from ..dominio import catalogos as cat
from ..dominio import intento as it
from ..dominio.errores import DatosInvalidos, TransicionInvalida

T0 = 1_790_000_000_000
SEG = 1000


def intento(estado: str = cat.EN_CURSO, **extra) -> dict:
    base = {"estado": estado, "tiempo_limite_seg": 600, "consumido_ms": 0, "reloj_desde": T0 if estado in cat.CORRIENDO else None,
            "ultimo_latido_en": T0, "iniciado_en": T0, "pausas": [], "armado": ["a", "b"], "respuestas": []}
    return {**base, **extra}


def aplicar(i: dict, cambios: dict) -> dict:
    return {**i, **cambios}


class MaquinaDeEstadosTests(SimpleTestCase):
    def test_los_nueve_estados_son_los_del_maestro(self):
        self.assertEqual(len(cat.ESTADOS_INTENTO), 9)
        self.assertEqual(set(cat.ESTADOS_INTENTO), {"no_iniciado", "en_curso", "pausado_desconexion", "restaurando", "en_curso_fuera_de_plazo",
                                                    "entregado", "en_revision_docente", "calificado", "anulado"})

    def test_las_transiciones_del_diagrama_existen(self):
        permitidas = [("no_iniciado", "en_curso"), ("en_curso", "pausado_desconexion"), ("pausado_desconexion", "en_curso"),
                      ("en_curso", "restaurando"), ("pausado_desconexion", "restaurando"), ("restaurando", "en_curso"),
                      ("restaurando", "pausado_desconexion"), ("en_curso", "en_curso_fuera_de_plazo"), ("en_curso", "entregado"),
                      ("pausado_desconexion", "entregado"), ("en_curso_fuera_de_plazo", "entregado"), ("entregado", "en_revision_docente"),
                      ("entregado", "calificado"), ("en_revision_docente", "calificado"), ("entregado", "anulado"),
                      ("en_revision_docente", "anulado"), ("calificado", "anulado")]
        for origen, destino in permitidas:
            it.comprobar_transicion(origen, destino)

    def test_lo_que_el_diagrama_prohibe_se_rechaza(self):
        for origen, destino in [("no_iniciado", "entregado"), ("en_curso", "anulado"), ("pausado_desconexion", "anulado"), ("entregado", "en_curso"),
                                ("calificado", "en_curso"), ("anulado", "calificado"), ("en_revision_docente", "entregado"), ("no_iniciado", "anulado")]:
            with self.assertRaises(TransicionInvalida, msg=f"{origen} → {destino}"):
                it.comprobar_transicion(origen, destino)

    def test_inv_018_ninguna_transicion_hacia_anulado_es_del_sistema(self):
        """Sólo se llega a `anulado` desde un intento ya entregado, y únicamente por `anular` (una persona con motivo). Ninguna otra función del dominio
        devuelve `estado = anulado`, en ningún estado de partida."""
        self.assertEqual({o for o, ds in it.TRANSICIONES.items() if cat.ANULADO in ds}, set(cat.ENTREGADOS))
        for estado in cat.ESTADOS_INTENTO:
            i = intento(estado, entregado_en=T0)
            for nombre, llamada in {
                "pausar": lambda: it.pausar(i, T0 + 60 * SEG), "restaurar": lambda: it.restaurar(i, T0 + 60 * SEG),
                "reactivar": lambda: it.reactivar(i, T0 + 60 * SEG, "sistema"), "entregar": lambda: it.entregar(i, T0 + 60 * SEG, cat.O_TIEMPO),
                "vencio_el_plazo": lambda: it.vencio_el_plazo_blando(i), "abrir": lambda: it.abrir(i, T0),
                "reconciliar": lambda: it.reconciliar_reloj(i, T0 + 60 * SEG, 30 * SEG), "pasar_a_pausado": lambda: it.pasar_a_pausado(i),
            }.items():
                try:
                    cambios = llamada()
                except (TransicionInvalida, DatosInvalidos):
                    continue
                self.assertNotEqual(cambios.get("estado"), cat.ANULADO, f"{nombre} desde {estado}")

    def test_anular_exige_una_persona_con_motivo_y_un_intento_entregado(self):
        entregado = intento(cat.ENTREGADO, entregado_en=T0)
        cambios = it.anular(entregado, "prof-1", "Copió de su compañero", T0 + 1)
        self.assertEqual((cambios["estado"], cambios["anulado_por"], cambios["anulado_en"]), (cat.ANULADO, "prof-1", T0 + 1))
        for quien in ("", "  ", cat.SISTEMA):
            with self.assertRaises(DatosInvalidos):
                it.anular(entregado, quien, "motivo válido", T0)
        for motivo in ("", " ", "ab"):
            with self.assertRaises(DatosInvalidos):
                it.anular(entregado, "prof-1", motivo, T0)
        with self.assertRaises(TransicionInvalida):          # un intento en curso no se anula: primero se entrega
            it.anular(intento(cat.EN_CURSO), "prof-1", "motivo válido", T0)


class RelojTests(SimpleTestCase):
    def test_el_reloj_corre_en_en_curso_y_se_agota_en_el_instante_exacto(self):
        i = intento(tiempo_limite_seg=600)
        self.assertEqual(it.reloj(i, T0 + 100 * SEG)["restante_ms"], 500 * SEG)
        self.assertEqual(it.instante_de_agotamiento(i), T0 + 600 * SEG)
        self.assertFalse(it.agotado(i, T0 + 599 * SEG))
        self.assertTrue(it.agotado(i, T0 + 600 * SEG))

    def test_sin_limite_no_hay_cronometro(self):
        i = intento(tiempo_limite_seg=None)
        self.assertIsNone(it.reloj(i, T0 + 9999 * SEG)["restante_ms"])
        self.assertIsNone(it.instante_de_agotamiento(i))
        self.assertFalse(it.agotado(i, T0 + 9999 * SEG))

    def test_pausar_congela_el_reloj_en_el_ultimo_latido(self):
        i = intento(ultimo_latido_en=T0 + 100 * SEG)
        pausado = aplicar(i, it.pausar(i, T0 + 190 * SEG))
        self.assertEqual((pausado["estado"], pausado["reloj_desde"], pausado["consumido_ms"]), (cat.PAUSADO, None, 100 * SEG))
        self.assertEqual(pausado["pausas"][0]["desde"], T0 + 100 * SEG)
        self.assertEqual(pausado["pausas"][0]["estado_previo"], cat.EN_CURSO)
        # congelado: el tiempo que pasa no se cuenta
        self.assertEqual(it.reloj(pausado, T0 + 5000 * SEG)["restante_ms"], 500 * SEG)
        self.assertTrue(it.reloj(pausado, T0)["congelado"])

    def test_reactivar_continua_desde_el_valor_congelado(self):
        i = intento(ultimo_latido_en=T0 + 100 * SEG)
        pausado = aplicar(i, it.pausar(i, T0 + 190 * SEG))
        reactivado = aplicar(pausado, it.reactivar(pausado, T0 + 400 * SEG, "prof-1"))
        self.assertEqual((reactivado["estado"], reactivado["reloj_desde"]), (cat.EN_CURSO, T0 + 400 * SEG))
        self.assertEqual(reactivado["pausas"][0]["hasta"], T0 + 400 * SEG)
        self.assertEqual(reactivado["pausas"][0]["reactivado_por"], "prof-1")
        self.assertEqual(it.reloj(reactivado, T0 + 400 * SEG)["restante_ms"], 500 * SEG)             # le devuelve exactamente lo que le quedaba
        self.assertEqual(it.reloj(reactivado, T0 + 450 * SEG)["restante_ms"], 450 * SEG)

    def test_fuera_de_plazo_se_pausa_y_vuelve_fuera_de_plazo(self):
        """Extensión D-9: un alumno puede desconectarse después de vencido el plazo blando."""
        i = intento(cat.EN_CURSO_FUERA_DE_PLAZO, fuera_de_plazo=True)
        pausado = aplicar(i, it.pausar(i, T0 + 60 * SEG))
        self.assertEqual(pausado["pausas"][0]["estado_previo"], cat.EN_CURSO_FUERA_DE_PLAZO)
        self.assertEqual(it.reactivar(pausado, T0 + 90 * SEG, "prof-1")["estado"], cat.EN_CURSO_FUERA_DE_PLAZO)

    def test_vencer_el_plazo_con_el_alumno_suspendido_recuerda_que_volvera_fuera_de_plazo(self):
        i = intento()
        pausado = aplicar(i, it.pausar(i, T0 + 60 * SEG))
        cambios = it.vencio_el_plazo_blando(pausado)
        self.assertTrue(cambios["fuera_de_plazo"])
        marcado = aplicar(pausado, cambios)
        self.assertEqual(it.reactivar(marcado, T0 + 90 * SEG, "prof-1")["estado"], cat.EN_CURSO_FUERA_DE_PLAZO)

    def test_vencer_el_plazo_pasa_en_curso_a_fuera_de_plazo_y_no_toca_a_un_entregado(self):
        self.assertEqual(it.vencio_el_plazo_blando(intento())["estado"], cat.EN_CURSO_FUERA_DE_PLAZO)
        self.assertEqual(it.vencio_el_plazo_blando(intento(cat.ENTREGADO, entregado_en=T0)), {})
        self.assertEqual(it.vencio_el_plazo_blando(intento(cat.NO_INICIADO)), {})

    def test_el_reinicio_del_nodo_deja_restaurando_con_el_reloj_congelado_sin_entregar_ni_anular(self):
        i = intento(ultimo_latido_en=T0 + 200 * SEG)
        r = aplicar(i, it.restaurar(i, T0 + 900 * SEG))
        self.assertEqual((r["estado"], r["reloj_desde"], r["consumido_ms"]), (cat.RESTAURANDO, None, 200 * SEG))
        self.assertEqual(r["pausas"][0]["causa"], cat.C_REINICIO_NODO)
        # desde una pausa sólo cambia el estado: la pausa sigue abierta
        pausado = aplicar(i, it.pausar(i, T0 + 300 * SEG))
        self.assertEqual(it.restaurar(pausado, T0 + 900 * SEG), {"estado": cat.RESTAURANDO})
        with self.assertRaises(TransicionInvalida):
            it.restaurar(intento(cat.ENTREGADO, entregado_en=T0), T0 + 900 * SEG)

    def test_reactivar_solo_aplica_a_un_intento_suspendido(self):
        with self.assertRaises(TransicionInvalida):
            it.reactivar(intento(), T0 + 5 * SEG, "prof-1")

    def test_entregar_detiene_el_reloj_en_el_instante_indicado(self):
        i = intento(tiempo_limite_seg=600)
        e = it.entregar(i, T0 + 900 * SEG, cat.O_TIEMPO, hasta=T0 + 600 * SEG)
        self.assertEqual((e["estado"], e["entregado_en"], e["consumido_ms"], e["reloj_desde"], e["origen_entrega"]),
                         (cat.ENTREGADO, T0 + 600 * SEG, 600 * SEG, None, cat.O_TIEMPO))
        with self.assertRaises(DatosInvalidos):
            it.entregar(i, T0, "otro")

    def test_entregar_a_un_suspendido_es_cierre_forzado_y_cierra_la_pausa(self):
        i = intento()
        pausado = aplicar(i, it.pausar(i, T0 + 100 * SEG))
        e = it.entregar(pausado, T0 + 500 * SEG, cat.O_PROFESOR)
        self.assertEqual(e["consumido_ms"], pausado["consumido_ms"])
        self.assertEqual(e["pausas"][0]["hasta"], T0 + 500 * SEG)

    def test_tras_calificar(self):
        self.assertEqual(it.tras_calificar(True), cat.EN_REVISION)
        self.assertEqual(it.tras_calificar(False), cat.CALIFICADO)

    def test_silencio_y_umbral_de_pausa(self):
        i = intento(ultimo_latido_en=T0 + 10 * SEG)
        self.assertEqual(it.silencio_ms(i, T0 + 30 * SEG), 20 * SEG)
        self.assertFalse(it.debe_pausarse(i, T0 + 40 * SEG, 30 * SEG))
        self.assertTrue(it.debe_pausarse(i, T0 + 41 * SEG, 30 * SEG))
        self.assertFalse(it.debe_pausarse(intento(cat.ENTREGADO, entregado_en=T0), T0 + 999 * SEG, 30 * SEG))

    def test_el_reloj_de_la_tableta_no_regala_tiempo_y_un_valor_inflado_no_pasa_del_reloj_de_pared(self):
        # el nodo contó 160 s (60 acumulados + 100 en marcha) de los 200 s que lleva abierto el intento
        i = intento(consumido_ms=60 * SEG, reloj_desde=T0 + 100 * SEG)
        # la tableta cuenta más tiempo que el nodo: el nodo toma el mayor
        self.assertEqual(it.reconciliar_reloj(i, T0 + 200 * SEG, 190 * SEG), {"consumido_ms": 190 * SEG, "reloj_desde": T0 + 200 * SEG})
        # lo que la tableta cuenta de más y excede el tiempo real desde que se abrió no vale
        self.assertEqual(it.reconciliar_reloj(i, T0 + 200 * SEG, 9999 * SEG), {"consumido_ms": 200 * SEG, "reloj_desde": T0 + 200 * SEG})
        i = intento(consumido_ms=0)
        # un valor inflado queda acotado por el tiempo real desde que se abrió
        inflado = it.reconciliar_reloj(intento(consumido_ms=0, reloj_desde=None, estado=cat.PAUSADO), T0 + 100 * SEG, 9999 * SEG)
        self.assertEqual(inflado, {"consumido_ms": 100 * SEG})
        # sólo sube: un valor menor que el del nodo no cambia nada
        self.assertEqual(it.reconciliar_reloj(i, T0 + 100 * SEG, 10 * SEG), {})
        for basura in (None, "", -5, 0, True, "x"):
            self.assertEqual(it.reconciliar_reloj(i, T0 + 100 * SEG, basura), {})
