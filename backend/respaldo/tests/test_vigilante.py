"""
El vigilante de MOD-016: el calendario (FUN-169/170/171), aplazar por una clase (nunca se frena el aula por un respaldo), reanudar lo interrumpido (FUN-177), verificar lo pendiente y la
prueba periódica de recuperación (CAP-103).
"""
from __future__ import annotations

from datetime import datetime, timezone

from respaldo.dominio import catalogos as cat

from .base import BaseRespaldo, R


def ms(anio, mes, dia, hora=0, minuto=0) -> int:
    return int(datetime(anio, mes, dia, hora, minuto, tzinfo=timezone.utc).timestamp() * 1000)


class Calendario(BaseRespaldo):
    def programar(self, **cuerpo):
        r = self.tecnico().post(f"{R}/programacion/", cuerpo, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def lista(self) -> list[dict]:
        return self.admin.get(f"{R}/respaldos/").json()["respaldos"]

    def test_toca_a_la_hora_programada_y_no_antes(self):
        self.programar(hora_min=2 * 60, dias=[0, 1, 2, 3, 4, 5, 6])
        self.reloj.t = ms(2026, 10, 25, 2, 5)
        self.assertEqual(self.tick()["pasos"]["programado"], "completo", "un equipo sin ningún respaldo automático hace el primero en cuanto se programa")
        self.reloj.t = ms(2026, 10, 26, 1, 30)
        self.assertIsNone(self.tick()["pasos"]["programado"], "todavía no son las 02:00 de hoy")
        self.reloj.t = ms(2026, 10, 26, 2, 1)
        self.assertEqual(self.tick()["pasos"]["programado"], "incremental")
        r = self.lista()
        self.assertEqual((len(r), r[0]["disparo"], r[0]["estado"], r[0]["tipo"]), (2, "programado", "completo_verificado", "incremental"))

    def test_un_horario_cubierto_no_se_repite_y_el_dia_siguiente_hace_un_incremental(self):
        self.programar(hora_min=120, dias=[0, 1, 2, 3, 4, 5, 6])
        self.reloj.t = ms(2026, 10, 26, 2, 5)
        self.tick()
        self.reloj.t = ms(2026, 10, 26, 9)
        self.assertIsNone(self.tick()["pasos"]["programado"])
        self.reloj.t = ms(2026, 10, 27, 2, 5)
        self.assertEqual(self.tick()["pasos"]["programado"], "incremental")
        self.assertEqual([r["tipo"] for r in self.lista()], ["incremental", "completo"])

    def test_un_equipo_apagado_a_esa_hora_se_pone_al_dia_una_sola_vez(self):
        self.programar(hora_min=120, dias=[0, 1, 2, 3, 4, 5, 6])
        self.reloj.t = ms(2026, 10, 26, 14)
        self.assertEqual(self.tick()["pasos"]["programado"], "completo")
        self.reloj.t = ms(2026, 10, 26, 14, 1)
        self.assertIsNone(self.tick()["pasos"]["programado"])
        self.assertEqual(len(self.lista()), 1)

    def test_con_una_clase_abierta_se_aplaza_y_se_hace_al_terminar(self):
        self.programar(hora_min=120, dias=[0, 1, 2, 3, 4, 5, 6])
        self.s.aula.sesiones_activas = lambda: 1                                    # hay una clase abierta (la clase REAL se prueba en la restauración)
        self.reloj.t = ms(2026, 10, 26, 3)
        self.assertEqual(self.tick()["pasos"]["programado"], "aplazado_por_clase")
        self.assertEqual(self.lista(), [])
        self.assertIsNotNone(self.admin.get(f"{R}/estado/").json()["aplazado_por_clase"], "la administración ve que se aplazó por una clase")
        self.s.aula.sesiones_activas = lambda: 0
        self.reloj.t = ms(2026, 10, 26, 4)
        self.assertEqual(self.tick()["pasos"]["programado"], "completo")
        self.assertIsNone(self.admin.get(f"{R}/estado/").json()["aplazado_por_clase"])

    def test_apagado_no_hace_nada(self):
        self.programar(activo=False)
        self.reloj.t = ms(2026, 10, 26, 12)
        self.assertIsNone(self.tick()["pasos"]["programado"])

    def test_un_respaldo_automatico_que_fallo_se_reintenta_a_la_hora_no_en_cada_ciclo(self):
        self.programar(hora_min=120, dias=[0, 1, 2, 3, 4, 5, 6])
        self.s.almacen.espacio_libre = lambda: 10
        self.reloj.t = ms(2026, 10, 26, 3)
        self.tick()
        self.assertEqual([r["estado"] for r in self.lista()], ["fallido"])
        self.reloj.t += 5 * cat.MINUTO_MS
        self.assertIsNone(self.tick()["pasos"]["programado"])
        self.assertEqual(len(self.lista()), 1)
        del self.s.almacen.espacio_libre
        self.reloj.t += cat.HORA_MS
        self.assertEqual(self.tick()["pasos"]["programado"], "completo")

    def test_programar_valida_y_deja_rastro(self):
        r = self.tecnico().post(f"{R}/programacion/", {"hora_min": 5000}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.tecnico().post(f"{R}/programacion/", {"destino": "unidad"}, format="json")
        self.assertEqual(r.status_code, 400, "el calendario no saca datos del equipo: exportar es manual y con pase")
        r = self.tecnico().post(f"{R}/programacion/", {"retencion": 7}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("respaldo.programado", self.acciones_asentadas())
        self.assertIn(cat.EV_PROGRAMADO, self.tipos_de_eventos())


class Arranque(BaseRespaldo):
    def test_lo_que_quedo_a_medias_se_marca_interrumpido_y_se_reanuda_con_el_mismo_identificador(self):
        from respaldo.aplicacion.motor import Motor
        with self.s.uow() as uow:
            Motor(self.s)._h(uow, "11111111-1111-4111-8111-111111111111", cat.H_INICIADO, "sistema", {"tipo": "completo", "disparo": "programado", "base_id": ""})
        self.assertEqual(self.ficha("11111111-1111-4111-8111-111111111111")["estado"], "incompleto")
        r = self.tick("arranque")
        self.assertEqual(r["pasos"]["reanudar"], ["11111111-1111-4111-8111-111111111111"])
        f = self.ficha("11111111-1111-4111-8111-111111111111")
        self.assertEqual((f["estado"], f["tipo"], f["disparo"]), ("completo_verificado", "completo", "programado"))
        historial = [h["tipo"] for h in self.admin.get(f"{R}/respaldos/{f['respaldo_id']}/").json()["historial"]]
        self.assertEqual(historial[:3], ["iniciado", "interrumpido", "reanudado"])
        self.assertIn(cat.EV_REANUDADO, self.tipos_de_eventos())

    def test_lo_interrumpido_hace_mas_de_un_dia_no_se_reanuda_pero_se_deja_dicho(self):
        from respaldo.aplicacion.motor import Motor
        with self.s.uow() as uow:
            Motor(self.s)._h(uow, "22222222-2222-4222-8222-222222222222", cat.H_INICIADO, "sistema", {"tipo": "completo", "disparo": "manual"}, en=self.t0 - 3 * cat.DIA_MS)
        self.assertEqual(self.tick("arranque")["pasos"]["reanudar"], [])
        self.assertEqual(self.ficha("22222222-2222-4222-8222-222222222222")["estado"], "incompleto")

    def test_los_respaldos_de_la_carpeta_que_la_base_no_conoce_se_catalogan_al_arrancar(self):
        f = self.respaldar()
        from respaldo.models import Historial, Respaldo
        Historial.objects.all().delete()
        Respaldo.objects.all().delete()
        self.assertEqual(self.tick("arranque")["pasos"]["catalogo"]["catalogados"], [f["respaldo_id"]])


class Verificacion(BaseRespaldo):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.tecnico().post(f"{R}/programacion/", {"activo": False}, format="json").status_code, 200)      # que el calendario no haga otro respaldo en medio
    def test_lo_que_quedo_sin_verificar_se_verifica_solo_y_un_fallo_no_se_reintenta_en_cada_ciclo(self):
        self.s.config = type(self.s.config)(**{**self.s.config.__dict__, "verificar_al_terminar": False})
        f = self.respaldar()
        self.assertEqual(f["estado"], "completo_no_verificado")
        self.assertEqual(self.tick()["pasos"]["verificar"], f["respaldo_id"])
        self.assertEqual(self.ficha(f["respaldo_id"])["estado"], "completo_verificado")

    def test_un_respaldo_dañado_se_reintenta_cada_seis_horas(self):
        self.s.config = type(self.s.config)(**{**self.s.config.__dict__, "verificar_al_terminar": False})
        f = self.respaldar()
        ruta = self.carpeta / f["archivo"]
        ruta.write_bytes(ruta.read_bytes()[:-10])
        self.assertEqual(self.tick()["pasos"]["verificar"], f["respaldo_id"])
        self.assertIsNone(self.tick()["pasos"]["verificar"], "no se repite en el siguiente ciclo")
        self.reloj.avanzar(7 * cat.HORA_MS)
        self.assertEqual(self.tick()["pasos"]["verificar"], f["respaldo_id"])

    def test_la_prueba_periodica_de_recuperacion_vuelve_a_verificar_el_ultimo_restaurable_cada_treinta_dias(self):
        f = self.respaldar()
        self.assertIsNone(self.tick()["pasos"]["verificar"])
        self.reloj.avanzar(31 * cat.DIA_MS)
        self.assertEqual(self.tick()["pasos"]["verificar"], f["respaldo_id"])
        self.assertEqual(self.tipos_de_eventos().count(cat.EV_VERIFICADO), 2)
