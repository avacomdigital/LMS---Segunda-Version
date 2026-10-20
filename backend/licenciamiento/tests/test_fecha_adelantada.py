"""
MOD-018 · Q-L13 (decisión del CTO): ante un salto accidental de la fecha hacia el futuro el nodo YA NO LO GUARDA y NO DEGRADA la licencia a las 72 horas: lanza un error hasta que la fecha
concuerde con la actual. Se prueba con el nodo real (base, anclas, bitácora, permisos, API) y el reloj falso de `base.py`: `avanzar` pasa el tiempo de verdad (pared y monótono) y
`saltar` sólo mueve el de pared (alguien cambió la hora del sistema).

Lo que se comprueba, en orden: no se acepta (ni hora, ni marca alta, ni ancla), no degrada, avisa con un error que dice las dos fechas, se quita solo al corregir la fecha sin dejar nada
detrás, no lo olvida un reinicio, la administración puede confirmar que la de hoy es la correcta, un equipo apagado no es un salto, y ninguna acción de la licencia se fecha con la del salto.
"""
from __future__ import annotations

import json
import random

from licenciamiento import models as m
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio import solicitud as sol
from licenciamiento.dominio.politica import DIA_MS, HORA_MS
from licenciamiento.infraestructura import contenedor

from .base import L, BaseLicencia


class BaseDeFecha(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.activar_ok(vence=self.t0 + 30 * DIA_MS)           # 30 días de vigencia y 30 de gracia EXACTOS: degrada en el día 60, ni uno más (Q-L16)
        self.evaluar("arranque")

    def marca_db(self) -> int:
        return m.MarcaAlta.objects.get().valor

    def marca_ancla(self) -> int:
        return json.loads(self.s.almacen.leer(cat.ARCHIVO_ANCLA))["marca"]

    def reiniciar_nodo(self):
        """Un proceso nuevo: la memoria viva queda vacía (sin reloj previo ni episodio en memoria); la base y la carpeta de estado son las mismas."""
        contenedor.reiniciar()
        self.s = contenedor.servicios()
        self.s.reloj, self.s.huella = self.reloj, self.huella
        return self.evaluar("arranque")

    def episodios(self):
        return list(m.Observacion.objects.filter(tipo=cat.O_SALTO).order_by("id"))


class NoSeAceptaTests(BaseDeFecha):
    def test_una_fecha_adelantada_no_se_acepta_no_degrada_y_se_avisa_con_un_error(self):
        self.reloj.avanzar(59 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "en_gracia")
        self.reloj.saltar(10 * DIA_MS)                                           # alguien adelanta la fecha diez días: el equipo diría que ya pasó la gracia (día 69)
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.dias_restantes), ("en_gracia", 1))        # NO degrada: la licencia sigue contando el tiempo REAL
        self.assertEqual(e.estado.ahora, self.t0 + 59 * DIA_MS)                               # la hora confiable no se movió ni un milisegundo hacia el salto
        self.assertIn("reloj_adelantado", e.estado.banderas)
        self.assertNotIn("reloj_sospechoso", e.estado.banderas)                               # eso es el reloj ATRASADO: otra cosa
        self.assertEqual(e.estado.reloj_adelanto_ms, 10 * DIA_MS)
        self.assertEqual(sorted(e.estado.capacidades), sorted(cat.CAPACIDADES_LICENCIABLES))  # todos los módulos siguen encendidos

    def test_el_error_llega_por_la_api_primero_y_con_las_dos_fechas(self):
        self.reloj.avanzar(10 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(400 * DIA_MS)
        self.evaluar("tick")
        estado = self.estado()
        self.assertIn("reloj_adelantado", estado["banderas"])
        aviso = estado["avisos"][0]
        self.assertEqual(aviso, {"codigo": "reloj_adelantado", "adelanto_dias": 400, "fecha_equipo": self.t0 + 410 * DIA_MS, "fecha_esperada": self.t0 + 10 * DIA_MS})
        self.assertEqual((estado["estado"], estado["ahora"]), ("activa", self.t0 + 10 * DIA_MS))

    def test_no_se_guarda_ni_en_la_base_ni_en_las_anclas_de_afuera(self):
        self.reloj.avanzar(5 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(365 * DIA_MS)
        self.evaluar("tick")
        self.evaluar("accion")
        for _ in range(3):
            self.reloj.avanzar(HORA_MS)
            self.evaluar("tick")
        limite = self.t0 + 5 * DIA_MS + 3 * HORA_MS
        self.assertLessEqual(self.marca_db(), limite)
        self.assertLessEqual(self.marca_ancla(), limite)

    def test_la_marca_sigue_el_tiempo_real_mientras_dura_el_error(self):
        """La marca alta no se congela: sube con el reloj monótono, así que corregir la fecha después no deja un hueco ni un adelanto."""
        self.reloj.saltar(30 * DIA_MS)
        self.evaluar("tick")
        self.reloj.avanzar(3 * DIA_MS)
        self.evaluar("accion")
        self.assertGreaterEqual(self.marca_db(), self.t0 + 3 * DIA_MS - HORA_MS)
        self.assertLessEqual(self.marca_db(), self.t0 + 3 * DIA_MS + 5_000)

    def test_el_salto_deja_su_asiento_una_vez_y_el_episodio_queda_abierto_en_la_base(self):
        self.reloj.saltar(10 * DIA_MS)
        self.evaluar("tick")
        for _ in range(3):
            self.reloj.avanzar(HORA_MS)
            self.evaluar("tick")
        from audit.models import Bitacora
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RELOJ).count(), 1)             # un reloj torcido no llena la bitácora
        filas = self.episodios()
        self.assertEqual(len(filas), 1)
        self.assertTrue(filas[0].detalle["inicio"])
        self.assertAlmostEqual(filas[0].detalle["adelanto_ms"], 10 * DIA_MS, delta=5_000)        # la bitácora de la prueba se sella con el reloj real: unos milisegundos de diferencia con el falso

    def test_la_real_degradacion_por_el_paso_del_tiempo_sigue_siendo_exacta_con_el_error_puesto(self):
        """El error no aplaza nada y no adelanta nada: la gracia termina el día 60 del tiempo real, con la fecha mal o bien."""
        self.reloj.avanzar(59 * DIA_MS + 23 * HORA_MS)
        self.reloj.saltar(20 * DIA_MS)
        e = self.evaluar("tick")
        self.assertEqual(e.estado.estado, "en_gracia")
        self.reloj.avanzar(HORA_MS)                                              # justo se cumplen los 30 días de gracia: degrada en ese instante, no 24 h después
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.motivo), ("degradada", "vencida"))
        self.assertIn("reloj_adelantado", e.estado.banderas)


class SeQuitaSoloTests(BaseDeFecha):
    def test_al_corregir_la_fecha_el_error_se_quita_solo_y_no_queda_nada_detras(self):
        self.reloj.avanzar(40 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(365 * DIA_MS)
        self.assertIn("reloj_adelantado", self.evaluar("tick").estado.banderas)
        self.reloj.saltar(-365 * DIA_MS)                                         # la fecha vuelve a ser la de hoy
        e = self.evaluar("tick")
        self.assertNotIn("reloj_adelantado", e.estado.banderas)
        self.assertEqual((e.estado.estado, e.estado.dias_restantes, e.estado.ahora), ("en_gracia", 20, self.t0 + 40 * DIA_MS))
        self.assertEqual(e.estado.reloj_adelanto_ms, 0)
        self.assertLessEqual(self.marca_db(), self.t0 + 40 * DIA_MS)             # la marca NUNCA llegó al futuro: corregir la fecha no choca con ella
        self.assertNotIn("reloj_sospechoso", e.estado.banderas)                  # y no se toma por un reloj atrasado
        self.assertEqual([f.detalle for f in self.episodios()][-1], {"fin": True})
        self.assertNotIn("reloj_adelantado", self.estado()["banderas"])
        self.assertEqual([a["codigo"] for a in self.estado()["avisos"]], ["gracia"])      # sólo el aviso de la gracia: el error desapareció

    def test_despues_de_corregirla_el_tiempo_sigue_corriendo_normal(self):
        self.reloj.saltar(100 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(-100 * DIA_MS)
        self.evaluar("tick")
        self.reloj.avanzar(61 * DIA_MS)                                          # el día 61 de uso real, ya sin error
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.ahora), ("degradada", self.t0 + 61 * DIA_MS))
        self.assertNotIn("reloj_adelantado", e.estado.banderas)

    def test_corregirla_a_medias_mantiene_el_error(self):
        self.reloj.saltar(30 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(-27 * DIA_MS)                                          # quedó 3 días adelantada: todavía no concuerda
        e = self.evaluar("tick")
        self.assertIn("reloj_adelantado", e.estado.banderas)
        self.assertAlmostEqual(e.estado.reloj_adelanto_ms, 3 * DIA_MS, delta=5_000)
        self.reloj.saltar(-3 * DIA_MS + 2 * HORA_MS)                             # ahora a dos horas de la real: concuerda
        self.assertNotIn("reloj_adelantado", self.evaluar("tick").estado.banderas)

    def test_adelantar_y_devolver_la_fecha_no_es_una_palanca_ni_para_aplazar_ni_para_adelantar(self):
        """H-14 (antes: «aplaza 72 h»): ahora ni aplaza ni adelanta nada. La licencia degrada el día 60 de tiempo real, adelantes o devuelvas lo que adelantes o devuelvas."""
        self.reloj.avanzar(58 * DIA_MS)
        self.evaluar("tick")
        for salto in (30, 400, 9):
            self.reloj.saltar(salto * DIA_MS)
            self.evaluar("tick")
            self.reloj.saltar(-salto * DIA_MS)
            self.evaluar("tick")
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.dias_restantes), ("en_gracia", 2))
        self.reloj.avanzar(2 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "degradada")

    def test_un_nodo_degradado_no_recupera_los_modulos_adelantando_y_devolviendo_la_fecha(self):
        self.reloj.avanzar(61 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "degradada")
        self.reloj.saltar(400 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(-400 * DIA_MS)
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, sorted(e.estado.capacidades)), ("degradada", []))


class UnReinicioNoLoOlvidaTests(BaseDeFecha):
    def test_tras_un_reinicio_con_la_fecha_todavia_adelantada_sigue_sin_aceptarla(self):
        self.reloj.avanzar(10 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(60 * DIA_MS)
        self.evaluar("tick")
        e = self.reiniciar_nodo()                                                # el servicio se reinicia (una actualización de Windows) con la fecha todavía mal
        self.assertIn("reloj_adelantado", e.estado.banderas)
        self.assertEqual((e.estado.estado, e.estado.ahora), ("activa", self.t0 + 10 * DIA_MS))   # la referencia es la marca: lo último que el aula guardó de verdad
        self.assertLessEqual(self.marca_db(), self.t0 + 10 * DIA_MS)

    def test_tras_un_reinicio_con_la_fecha_ya_corregida_el_error_se_cierra(self):
        self.reloj.saltar(60 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(-60 * DIA_MS)                                          # la corrigen y se reinicia antes del siguiente ciclo
        e = self.reiniciar_nodo()
        self.assertNotIn("reloj_adelantado", e.estado.banderas)
        self.assertEqual([f.detalle for f in self.episodios()][-1], {"fin": True})

    def test_el_episodio_sobrevive_a_varios_reinicios_hasta_que_la_fecha_concuerda(self):
        self.reloj.saltar(45 * DIA_MS)
        self.evaluar("tick")
        for _ in range(3):
            self.reloj.avanzar(6 * HORA_MS)
            self.assertIn("reloj_adelantado", self.reiniciar_nodo().estado.banderas)
        self.reloj.saltar(-45 * DIA_MS)
        self.assertNotIn("reloj_adelantado", self.reiniciar_nodo().estado.banderas)
        self.assertEqual(len(self.episodios()), 2)                                # uno que abre y uno que cierra, sin repeticiones


class ConfirmarLaFechaTests(BaseDeFecha):
    def test_la_administracion_puede_confirmar_que_la_fecha_del_equipo_es_la_correcta(self):
        """La única forma de aceptar un salto: el aula se había quedado atrás (o estuvo apagada con el salto pendiente) y la fecha del equipo ES la de hoy."""
        self.reloj.avanzar(59 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(10 * DIA_MS)
        self.assertIn("reloj_adelantado", self.evaluar("tick").estado.banderas)
        r = self.admin.post(f"{L}/reloj/confirmar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual(cuerpo["estado"], "degradada")                          # ya con la fecha del equipo: pasó la gracia
        self.assertNotIn("reloj_adelantado", cuerpo["banderas"])
        self.assertEqual(cuerpo["ahora"], self.t0 + 69 * DIA_MS)
        self.assertEqual(self.marca_db(), self.t0 + 69 * DIA_MS)                 # sólo ahora —y por decisión de una persona— se guarda
        from audit.models import Bitacora
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RELOJ_CONFIRMADO).count(), 1)
        e = self.evaluar("tick")                                                 # y los ciclos siguientes ya no la retienen
        self.assertEqual((e.estado.estado, e.estado.ahora), ("degradada", self.t0 + 69 * DIA_MS))
        self.assertNotIn("reloj_adelantado", e.estado.banderas)

    def test_confirmar_sin_fecha_adelantada_no_cambia_nada_importante(self):
        self.evaluar("tick")
        r = self.admin.post(f"{L}/reloj/confirmar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["estado"], r.json()["banderas"]), ("activa", []))

    def test_el_profesor_no_puede_confirmar_la_fecha(self):
        self.reloj.saltar(20 * DIA_MS)
        self.evaluar("tick")
        self.assertEqual(self.docente.post(f"{L}/reloj/confirmar/", {}, format="json").status_code, 403)
        self.assertIn("reloj_adelantado", self.evaluar("tick").estado.banderas)


class LosDiasDeCalendarioCuentanTests(BaseDeFecha):
    def test_un_nodo_apagado_semanas_no_es_un_salto_y_la_gracia_sigue_corriendo_apagado(self):
        """Q-L16 · gracia de 30 días CALENDARIO: un receso escolar con el equipo apagado consume la gracia. Entre un arranque y otro no hay referencia; no se cobra como salto."""
        self.reloj.avanzar(31 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "en_gracia")
        self.reloj.saltar(45 * DIA_MS)                                           # «se apagó» 45 días…
        e = self.reiniciar_nodo()                                                # …y arranca con la fecha de hoy
        self.assertNotIn("reloj_adelantado", e.estado.banderas)
        self.assertEqual((e.estado.estado, e.estado.ahora), ("degradada", self.t0 + 76 * DIA_MS))
        self.assertEqual(self.episodios(), [])

    def test_un_adelanto_menor_que_el_umbral_se_acepta_como_un_ajuste_de_hora(self):
        self.evaluar("tick")
        self.reloj.saltar(5 * DIA_MS)
        e = self.evaluar("tick")
        self.assertNotIn("reloj_adelantado", e.estado.banderas)
        self.assertEqual(e.estado.ahora, self.t0 + 5 * DIA_MS)

    def test_el_bios_que_vuelve_de_2010_y_sincroniza_la_hora_no_es_un_episodio(self):
        self.reloj.avanzar(2 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(-16 * 365 * DIA_MS)                                    # arranca con la fecha de fábrica
        self.reiniciar_nodo()
        self.reloj.avanzar(10 * 60_000)
        self.evaluar("tick")
        self.reloj.saltar(16 * 365 * DIA_MS)                                     # el sistema sincroniza la hora con la red
        e = self.evaluar("tick")
        self.assertNotIn("reloj_adelantado", e.estado.banderas)
        self.assertEqual(self.episodios(), [])
        self.assertAlmostEqual(e.estado.ahora, self.reloj.t, delta=HORA_MS)


class LasAccionesNoSeFechanConElSaltoTests(BaseDeFecha):
    def test_la_solicitud_lleva_la_hora_confiable_no_la_del_salto(self):
        self.reloj.avanzar(3 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(50 * DIA_MS)
        s = self.solicitud_del_nodo()                                            # el nodo miró el reloj ANTES de fechar (sin esperar al ciclo siguiente, sin asentar nada)
        self.assertEqual(s.creada, self.t0 + 3 * DIA_MS)
        self.assertIn("reloj_adelantado", self.evaluar("tick").estado.banderas)  # y el ciclo siguiente sí asienta y avisa

    def test_una_licencia_que_empieza_en_el_futuro_real_se_rechaza_aunque_la_fecha_del_equipo_la_deje_pasar(self):
        """`desde` se compara con la hora confiable, la misma con la que `estado.calcular` decide si ya rige (D-8): con la fecha del equipo 10 días adelantada, esta licencia habría entrado y el nodo
        se habría quedado sin licencia hasta que llegara su `desde`."""
        self.reloj.saltar(10 * DIA_MS)
        self.evaluar("tick")
        r = self.activar(serie=2, desde=self.t0 + 5 * DIA_MS, emitida=self.t0 - HORA_MS, via="renovar")
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "aun_no_vigente"), r.content)

    def test_la_liberacion_lleva_la_hora_confiable(self):
        self.reloj.avanzar(2 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(30 * DIA_MS)
        self.evaluar("tick")
        r = self.admin.post(f"{L}/liberar/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        liberacion = sol.leer_liberacion(self.bytes_de(r.json()["archivo_b64"]))
        self.assertEqual(liberacion.liberada, self.t0 + 2 * DIA_MS)


class CualquierSecuenciaTests(BaseDeFecha):
    def test_con_saltos_adelante_y_correcciones_al_azar_el_confiable_nunca_baja_ni_se_adelanta_al_tiempo_real(self):
        """Secuencias al azar (semilla fija) de tiempo real, saltos grandes hacia adelante, correcciones y reinicios. Lo que debe valer siempre: el confiable nunca baja, nunca va por
        delante del tiempo real transcurrido, y mientras la fecha esté adelantada hay error y mientras concuerde no lo hay."""
        azar = random.Random(20261021)
        real, desfase, abierto = 0, 0, False                                    # desfase: cuánto lleva adelantado el reloj de pared respecto del tiempo real
        ultimo = None
        for paso in range(120):
            accion = azar.choice(("avanzar", "avanzar", "avanzar", "saltar", "corregir", "reiniciar"))
            if accion == "avanzar":
                horas = azar.randint(1, 20)
                self.reloj.avanzar(horas * HORA_MS)
                real += horas * HORA_MS
            elif accion == "saltar":
                dias = azar.randint(8, 400)
                self.reloj.saltar(dias * DIA_MS)
                desfase += dias * DIA_MS
            elif accion == "corregir" and desfase:
                self.reloj.saltar(-desfase)
                desfase = 0
            elif accion == "reiniciar":
                e = self.reiniciar_nodo()
                if desfase == 0 or not abierto:
                    pass
            e = self.evaluar("tick")
            abierto = desfase > DIA_MS
            if ultimo is not None:
                self.assertGreaterEqual(e.estado.ahora, ultimo, f"paso {paso}: el confiable bajó")
            ultimo = e.estado.ahora
            self.assertLessEqual(e.estado.ahora, self.t0 + real + HORA_MS, f"paso {paso}: el confiable se adelantó al tiempo real ({accion})")
            self.assertEqual("reloj_adelantado" in e.estado.banderas, abierto, f"paso {paso}: el error {'faltó' if abierto else 'sobró'} con el reloj adelantado {desfase // DIA_MS} días ({accion})")
            if not abierto:
                self.assertAlmostEqual(e.estado.ahora, self.reloj.t, delta=2 * HORA_MS, msg=f"paso {paso}: con la fecha en orden la hora vale")
