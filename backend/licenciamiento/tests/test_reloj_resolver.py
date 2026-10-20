"""
MOD-018 · Q-L13 (decisión del CTO): una FECHA ADELANTADA no se acepta. Lo que el nodo concluye del reloj en cada ciclo es UNA función pura, `reloj.resolver`; aquí se prueba sin base de datos,
caso por caso: qué hora vale, qué marca vale y cuándo se abre o se cierra un episodio. La prueba contra el nodo real (base, anclas, API, reinicios) está en `test_fecha_adelantada.py`.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from licenciamiento.dominio import reloj
from licenciamiento.dominio.politica import DIA_MS, HORA_MS, POLITICA_PROVISIONAL

P = POLITICA_PROVISIONAL
T = 1_800_000_000_000                 # «ahora» de la prueba (milisegundos)
MONO = 5_000_000


def resolver(reloj_ms, mono, previo=None, marca=T, audit=None, abierto=False):
    return reloj.resolver(reloj_ms, mono, previo, marca, audit, abierto, P.tolerancia_retroceso_ms, P.salto_adelante_ms, P.tolerancia_fecha_ms)


def lectura_normal(t):
    """La lectura previa de un proceso al que le va bien: reloj de pared, monótono y confiable coinciden."""
    return (t, MONO, t)


class SinEpisodioTests(SimpleTestCase):
    def test_el_paso_normal_del_tiempo_es_lo_de_siempre(self):
        r = resolver(T + 60_000, MONO + 60_000, lectura_normal(T))
        self.assertEqual((r.adelantado, r.adelanto_ms, r.abre_episodio, r.cierra_episodio), (False, 0, False, False))
        self.assertEqual((r.lectura.ahora, r.lectura.retroceso, r.marca), (T + 60_000, False, T))

    def test_un_adelanto_por_debajo_del_umbral_se_acepta_como_siempre(self):
        """Cinco días de golpe: bajo los 7 del umbral. Es un ajuste de hora, no un episodio: la hora vale y la marca sube."""
        r = resolver(T + 5 * DIA_MS, MONO, lectura_normal(T))
        self.assertEqual((r.adelantado, r.lectura.ahora, r.abre_episodio), (False, T + 5 * DIA_MS, False))

    def test_un_nodo_que_arranca_adelantado_sin_episodio_lo_acepta_porque_los_dias_de_calendario_cuentan(self):
        """Q-L16: apagado un trimestre (receso, vacaciones). Sin lectura previa no hay con qué distinguirlo de un salto y no debe cobrarse como tal."""
        r = resolver(T + 90 * DIA_MS, MONO, None)
        self.assertEqual((r.adelantado, r.lectura.ahora, r.marca, r.abre_episodio), (False, T + 90 * DIA_MS, T, False))

    def test_una_pila_de_bios_que_vuelve_de_2010_y_sincroniza_la_hora_no_es_un_episodio(self):
        """El nodo arrancó con la fecha de fábrica (retroceso) y, ya en marcha, el sistema sincroniza la hora: el salto es enorme pero el reloj queda junto al confiable."""
        # el ciclo anterior (reloj en 2010): el confiable se quedó en la marca
        previo = (T - 16 * 365 * DIA_MS, MONO, T)
        r = resolver(T + HORA_MS, MONO + 60_000, previo)
        self.assertEqual((r.adelantado, r.abre_episodio, r.lectura.retroceso, r.lectura.ahora), (False, False, False, T + HORA_MS))

    def test_el_retroceso_sigue_siendo_lo_que_era(self):
        r = resolver(T - 3 * DIA_MS, MONO + 60_000, lectura_normal(T))
        self.assertTrue(r.lectura.retroceso)
        self.assertEqual(r.lectura.ahora, T + 60_000)                    # no baja de la marca y avanza con el monótono (H-13)
        self.assertFalse(r.adelantado)


class FechaAdelantadaTests(SimpleTestCase):
    def test_un_salto_hacia_adelante_en_marcha_no_se_acepta(self):
        r = resolver(T + 60_000 + 10 * DIA_MS, MONO + 60_000, lectura_normal(T))
        self.assertTrue(r.adelantado)
        self.assertEqual(r.adelanto_ms, 10 * DIA_MS)
        self.assertEqual(r.lectura.ahora, T + 60_000)                    # la confiable sigue el reloj monótono: ni un segundo de más
        self.assertEqual(r.marca, T)                                     # la marca no sube con el salto
        self.assertTrue(r.abre_episodio)
        self.assertFalse(r.cierra_episodio)

    def test_mientras_el_reloj_siga_adelantado_el_episodio_sigue_aunque_la_base_no_lo_haya_asentado(self):
        """El ciclo anterior ya retenía (reloj de pared 10 días por delante de la confiable): se sigue reteniendo, y se vuelve a pedir que se asiente."""
        previo = (T + 10 * DIA_MS, MONO, T)
        r = resolver(T + 10 * DIA_MS + 300_000, MONO + 300_000, previo, abierto=False)
        self.assertEqual((r.adelantado, r.lectura.ahora, r.abre_episodio), (True, T + 300_000, True))

    def test_con_el_episodio_asentado_no_se_vuelve_a_abrir(self):
        previo = (T + 10 * DIA_MS, MONO, T)
        r = resolver(T + 10 * DIA_MS + 300_000, MONO + 300_000, previo, abierto=True)
        self.assertEqual((r.adelantado, r.abre_episodio, r.cierra_episodio), (True, False, False))

    def test_un_reinicio_con_el_episodio_abierto_sigue_sin_aceptar_la_fecha(self):
        """La base lo recuerda: sin lectura previa, la referencia es la marca (lo último que el aula guardó de verdad)."""
        r = resolver(T + 30 * DIA_MS, MONO, None, marca=T, abierto=True)
        self.assertEqual((r.adelantado, r.lectura.ahora, r.adelanto_ms, r.abre_episodio), (True, T, 30 * DIA_MS, False))

    def test_cuando_la_fecha_concuerda_el_episodio_se_cierra_y_la_hora_vale_otra_vez(self):
        previo = (T + 10 * DIA_MS, MONO, T)
        r = resolver(T + 300_000, MONO + 300_000, previo, abierto=True)             # la corrigieron: el reloj volvió junto a la confiable
        self.assertEqual((r.adelantado, r.adelanto_ms, r.cierra_episodio, r.abre_episodio), (False, 0, True, False))
        self.assertEqual(r.lectura.ahora, T + 300_000)

    def test_con_el_episodio_abierto_y_la_fecha_corregida_tras_un_reinicio_tambien_se_cierra(self):
        r = resolver(T + 2 * HORA_MS, MONO, None, marca=T, abierto=True)
        self.assertEqual((r.adelantado, r.cierra_episodio, r.lectura.ahora), (False, True, T + 2 * HORA_MS))

    def test_la_tolerancia_es_de_un_dia_exacto(self):
        previo = lectura_normal(T)
        en_el_limite = resolver(T + DIA_MS + 7 * DIA_MS, MONO, previo, abierto=True)     # 8 días por delante: episodio
        self.assertTrue(en_el_limite.adelantado)
        # ya en episodio, el reloj vuelve a quedar a UN día de la confiable: concuerda (justo en la tolerancia); a un día y un milisegundo, no
        previo = (T + 10 * DIA_MS, MONO, T)
        self.assertFalse(resolver(T + DIA_MS, MONO, previo, abierto=True).adelantado)
        self.assertTrue(resolver(T + DIA_MS + 1, MONO, previo, abierto=True).adelantado)

    def test_si_se_corrige_pero_todavia_a_mas_de_un_dia_sigue_el_aviso(self):
        previo = (T + 10 * DIA_MS, MONO, T)
        r = resolver(T + 3 * DIA_MS, MONO + 60_000, previo, abierto=True)
        self.assertEqual((r.adelantado, r.adelanto_ms), (True, 3 * DIA_MS - 60_000))
        self.assertEqual(r.lectura.ahora, T + 60_000)

    def test_confirmada_por_la_administracion_la_fecha_vale(self):
        """Una `reloj_confirmado` posterior deja el episodio como NO abierto (lo decide quien arma `episodio_abierto`) y sin lectura previa (`olvidar_reloj`): la hora del equipo vale."""
        r = resolver(T + 10 * DIA_MS, MONO + 1, None, marca=T, abierto=False)
        self.assertEqual((r.adelantado, r.lectura.ahora, r.cierra_episodio), (False, T + 10 * DIA_MS, False))

    def test_el_retroceso_con_el_episodio_abierto_lo_cierra_y_marca_el_retroceso(self):
        r = resolver(T - 20 * DIA_MS, MONO + 60_000, (T + 10 * DIA_MS, MONO, T), abierto=True)
        self.assertEqual((r.adelantado, r.cierra_episodio, r.lectura.retroceso), (False, True, True))
        self.assertEqual(r.lectura.ahora, T + 60_000)


class ElAsientoDeLaBitacoraTests(SimpleTestCase):
    """La bitácora la sellan los demás módulos con el reloj de pared: tras un salto lleva la fecha adelantada y no puede ser ancla (si lo fuera, el salto entraría por ahí en la marca)."""

    def test_un_asiento_sellado_con_la_fecha_adelantada_no_cuenta(self):
        r = resolver(T + 60_000 + 10 * DIA_MS, MONO + 60_000, lectura_normal(T), audit=T + 10 * DIA_MS)
        self.assertEqual((r.marca, r.lectura.ahora, r.adelantado), (T, T + 60_000, True))

    def test_pasado_el_salto_y_corregida_la_fecha_ese_asiento_sigue_sin_contar(self):
        """Hasta que llega un asiento nuevo con la fecha buena, el último de la bitácora es el del salto: no puede subir la marca."""
        r = resolver(T + 300_000, MONO + 300_000, (T + 10 * DIA_MS, MONO, T), audit=T + 10 * DIA_MS, abierto=True)
        self.assertEqual((r.marca, r.lectura.ahora, r.cierra_episodio), (T, T + 300_000, True))

    def test_un_asiento_normal_sigue_siendo_ancla(self):
        r = resolver(T + 60_000, MONO + 60_000, lectura_normal(T), marca=T - 5 * DIA_MS, audit=T + 30_000)
        self.assertEqual(r.marca, T + 30_000)                              # protege lo que protegía: una marca de la base que se quedó atrás de la bitácora

    def test_un_asiento_adelantado_pero_bajo_el_umbral_cuenta_como_antes(self):
        r = resolver(T + 60_000, MONO + 60_000, lectura_normal(T), audit=T + 3 * DIA_MS)
        self.assertEqual(r.marca, T + 3 * DIA_MS)
