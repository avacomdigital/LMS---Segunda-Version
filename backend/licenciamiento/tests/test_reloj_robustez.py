"""
MOD-018 · el reloj del equipo no puede servir para alargar una licencia (H-13). Lo encontró la verificación independiente
(`spec-driven/15-licenciamiento/06-verificacion-independiente.md`).

El instante confiable es `max(reloj de pared, marca alta)`. Si el reloj de pared queda por debajo de la marca (alguien atrasa la fecha, o una pila de BIOS agotada devuelve el reloj a
2010), ese máximo es un valor FIJO —la marca—: el tiempo de la licencia se congelaba hasta que la hora de pared alcanzaba la marca. Con el reloj de pared por debajo de la marca, el
instante confiable avanza ahora con el reloj monótono del proceso (`reloj.piso_monotono`).

El otro lado —adelantar la fecha (H-14, que aplazaba la degradación 72 h, y H-09)— lo resolvió el CTO (Q-L13): una fecha adelantada NO se acepta ni se guarda y avisa con un error hasta que
la fecha concuerde. Esas pruebas están en `test_fecha_adelantada.py` y `test_reloj_resolver.py`.

Se prueba con el nodo real y el reloj falso de `base.py`: `avanzar` pasa el tiempo de verdad (pared y monótono) y `saltar` sólo mueve el de pared (alguien cambió la hora).
"""
from __future__ import annotations

import random

from licenciamiento.dominio.politica import DIA_MS, HORA_MS
from licenciamiento.infraestructura import contenedor

from .base import BaseLicencia


class BaseDeReloj(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.activar_ok(vence=self.t0 + 30 * DIA_MS)           # 30 días de vigencia y 30 de gracia: degrada a partir del día 61
        self.evaluar("arranque")

    def pasar(self, horas: int, paso: int = 12):
        """Pasa `horas` de verdad, con un ciclo del programador cada `paso` horas (el reloj de pared y el monótono avanzan juntos: nada parece un salto)."""
        e = None
        for _ in range(max(1, horas // paso)):
            self.reloj.avanzar(paso * HORA_MS)
            e = self.evaluar("tick")
        return e

    def reiniciar_nodo(self):
        """Un proceso nuevo: la memoria viva queda vacía (sin reloj previo); la base y la carpeta de estado son las mismas."""
        contenedor.reiniciar()
        self.s = contenedor.servicios()
        self.s.reloj, self.s.huella = self.reloj, self.huella
        return self.evaluar("arranque")


class AtrasarLaFechaTests(BaseDeReloj):
    """H-13: atrasar la fecha no alarga la licencia ni la congela."""

    def test_atrasar_la_fecha_no_alarga_la_licencia(self):
        self.pasar(10 * 24)
        self.reloj.saltar(-100 * DIA_MS)                        # alguien devuelve la fecha 100 días
        self.evaluar("tick")
        e = self.pasar(45 * 24)                                 # día 55 de uso real: todavía en gracia
        self.assertEqual(e.estado.estado, "en_gracia")
        e = self.pasar(7 * 24)                                  # día 62: pasó la gracia (día 60). Con la fecha congelada seguiría «en_gracia» ~100 días más
        self.assertEqual((e.estado.estado, e.estado.motivo), ("degradada", "vencida"))
        self.assertEqual(sorted(e.estado.capacidades), [])

    def test_con_la_fecha_atrasada_el_instante_confiable_sigue_el_tiempo_real(self):
        """Una pila de BIOS agotada: la fecha vuelve a 2010. El instante confiable no se queda clavado en la marca."""
        self.pasar(10 * 24)
        self.reloj.saltar(-5 * 365 * DIA_MS)
        e = self.evaluar("tick")
        antes = e.estado.ahora
        e = self.pasar(20 * 24)
        self.assertEqual(e.estado.ahora - antes, 20 * DIA_MS)
        self.assertIn("reloj_sospechoso", e.estado.banderas)

    def test_tras_un_reinicio_la_licencia_sigue_corriendo_con_la_fecha_atrasada(self):
        """Cada reinicio sólo pierde el tiempo que el equipo estuvo apagado (aquí, nada): no devuelve el reloj al principio."""
        self.pasar(10 * 24)
        self.reloj.saltar(-100 * DIA_MS)
        self.evaluar("tick")
        dias = 0
        for dia in range(1, 80):
            self.pasar(12)                                      # medio día con el nodo encendido…
            self.reiniciar_nodo()                               # …se reinicia el servicio…
            e = self.pasar(12)                                  # …y otro medio día: cada vuelta es un día real
            if e.estado.estado == "degradada":
                dias = dia
                break
        self.assertTrue(dias and dias <= 55, f"degradó a los {dias} días reales (debía ser ~52)")


class ConElRelojEnOrdenTests(BaseDeReloj):
    """El piso monótono sólo actúa con el reloj de pared por debajo de la marca: con el reloj en orden no interviene."""

    def test_una_deriva_del_monotono_no_adelanta_el_confiable_ni_levanta_banderas(self):
        """El monótono corre 1 minuto por día más que el de pared: tras 120 días son 2 horas de diferencia. El confiable sigue al reloj, no al monótono."""
        e = None
        for _ in range(120):
            self.reloj.avanzar(24 * HORA_MS)
            self.reloj.mono += 60_000
            e = self.evaluar("tick")
            self.assertNotIn("reloj_sospechoso", e.estado.banderas)
        self.assertEqual(e.estado.ahora, self.reloj.t)

    def test_un_atraso_menor_que_la_tolerancia_no_activa_el_piso(self):
        e = self.pasar(24)
        antes = e.estado.ahora
        self.reloj.saltar(-2 * 60_000)                          # NTP corrige 2 minutos hacia atrás
        e = self.evaluar("tick")
        self.assertNotIn("reloj_sospechoso", e.estado.banderas)
        self.assertEqual(e.estado.ahora, antes)                 # se mide contra la marca: el reloj no baja

    def test_el_confiable_nunca_baja_ni_va_por_detras_del_tiempo_real(self):
        """Secuencias al azar (semilla fija) de avances, saltos hacia atrás y saltos hacia adelante de hasta 6 días (por debajo del umbral de sospecha)."""
        azar = random.Random(20261020)
        ultimo, real = None, 0
        for _ in range(200):
            accion = azar.choice(("avanzar", "avanzar", "avanzar", "atras", "adelante"))
            if accion == "avanzar":
                horas = azar.randint(1, 30)
                self.reloj.avanzar(horas * HORA_MS)
                real += horas * HORA_MS
            elif accion == "atras":
                self.reloj.saltar(-azar.randint(1, 200) * HORA_MS)
            else:
                self.reloj.saltar(azar.randint(1, 6 * 24) * HORA_MS)
            ahora = self.evaluar("tick").estado.ahora
            if ultimo is not None:
                self.assertGreaterEqual(ahora, ultimo, "el instante confiable bajó")
            ultimo = ahora
            self.assertGreaterEqual(ahora - self.t0, real - HORA_MS, "el confiable va por detrás del tiempo real transcurrido")
