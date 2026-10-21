"""
El arranque y la parada en lo que toca a la cola (P-10 · Fase 2), las anclas (P-12: restaurar una copia vieja no repite una secuencia), el estado del nodo (P-09, P-16: restringido
sólo con motivo, publicado sólo al cambiar) y el campo aditivo `nodo` de `/health/`.
"""
from __future__ import annotations

import json

from django.test import override_settings
from rest_framework.test import APIClient

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..dominio.anclas import Ancla
from ..dominio.estado import LecturaDeSalud
from ..infraestructura import contenedor
from ..infraestructura.salud import SaludFija
from .base import BaseNodo


class ArranqueTests(BaseNodo):
    def test_arrancar_abre_la_fila_publica_servicios_iniciados_y_parar_la_cierra(self):
        r = servicios.arrancar()
        self.assertEqual((r["restauracion"], r["apagado_sucio_previo"], r["transaccion_inmediata"], r["base_integra"]), (None, False, True, True))
        fila = m.Arranque.objects.get()
        self.assertEqual((fila.iniciado_en, fila.cerrado_en, fila.restauracion), (self.t, None, False))
        self.assertEqual(len(self.eventos(tipo=cat.EV_SERVICIOS_INICIADOS)), 1)
        self.assertEqual(servicios.estado_resumido()["estado"], cat.OPERATIVO)
        self.assertEqual(self.s.anclas.leer().secuencia, 1)
        self.avanzar(minutos=5)
        servicios.parar()
        fila.refresh_from_db()
        self.assertEqual(fila.cerrado_en, self.t)
        self.assertEqual(servicios.estado_resumido()["estado"], cat.DETENIDO)
        self.assertEqual(m.MarcaAlta.objects.get(pk=1).valor, self.t)

    def test_un_arranque_sin_parar_deja_el_siguiente_como_apagado_sucio(self):
        servicios.arrancar()
        contenedor.reiniciar()
        self.avanzar(minutos=1)
        r = servicios.arrancar()
        self.assertTrue(r["apagado_sucio_previo"])
        self.assertTrue(servicios.estado_resumido()["apagado_sucio_previo"])
        self.assertEqual(m.Arranque.objects.count(), 2)

    def test_p12_restaurar_una_copia_vieja_no_repite_ninguna_secuencia(self):
        self.publicar_varios(3)                                                                       # «la copia vieja» llega hasta la 3
        self.s.anclas.escribir(Ancla(secuencia=500, marca_alta=self.t, escrita_en=self.t))            # pero el ancla recuerda que se emitió hasta la 500
        contenedor.reiniciar()
        with self.assertLogs("avacom.nodo", level="ERROR"):
            r = servicios.arrancar()
        self.assertEqual((r["restauracion"]["max_en_base"], r["restauracion"]["ancla"], r["restauracion"]["sin_ancla"]), (3, 500, False))
        self.assertGreaterEqual(r["contador"], 500 + cat.MARGEN_SECUENCIA)
        self.assertGreater(self.publicar()["secuencia"], 500 + cat.MARGEN_SECUENCIA)
        fila = m.Arranque.objects.get()
        self.assertTrue(fila.restauracion)
        self.assertEqual((fila.secuencia_al_iniciar, fila.ancla_secuencia), (3, 500))
        recuperacion = self.eventos(tipo=cat.EV_RECUPERACION_COMPLETADA)
        self.assertEqual(len(recuperacion), 1)
        self.assertEqual(set(recuperacion[0].carga), {"incidente", "inicio", "fin", "ultima_secuencia_valida", "eventos_reprocesados", "marcas_ajustadas", "contador", "instante"})
        self.assertEqual(recuperacion[0].carga["ultima_secuencia_valida"], 3)
        self.assertEqual(len(self.asientos(cat.A_RESTAURACION_DETECTADA)), 1)
        self.assertEqual(servicios.estado_resumido()["estado"], cat.OPERATIVO)                        # una restauración no restringe: sólo se dice
        self.assertEqual(servicios.estado()["arranque"]["restauracion"]["ancla"], 500)

    def test_p12_sin_ancla_y_con_eventos_tambien_es_una_restauracion(self):
        self.publicar_varios(2)
        self.assertIsNone(self.s.anclas.leer())
        contenedor.reiniciar()
        with self.assertLogs("avacom.nodo", level="ERROR"):
            r = servicios.arrancar()
        self.assertTrue(r["restauracion"]["sin_ancla"])
        self.assertGreaterEqual(r["contador"], 2 + cat.MARGEN_SECUENCIA)

    def test_un_ancla_danada_o_alterada_se_trata_como_ausente_y_nunca_impide_arrancar(self):
        self.s.anclas.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.s.anclas.ruta.write_text("{esto no es json", encoding="utf-8")
        with self.assertLogs("avacom.nodo", level="ERROR"):
            self.assertIsNone(self.s.anclas.leer())
        self.s.anclas.escribir(Ancla(10, 5, 1))
        texto = json.loads(self.s.anclas.ruta.read_text(encoding="utf-8"))
        texto["secuencia"] = 9999
        self.s.anclas.ruta.write_text(json.dumps(texto), encoding="utf-8")
        with self.assertLogs("avacom.nodo", level="ERROR"):
            self.assertIsNone(self.s.anclas.leer())
        self.assertIsNotNone(servicios.arrancar())

    def test_lo_normal_no_salta_aunque_el_ancla_vaya_por_detras(self):
        self.publicar_varios(20)
        self.s.anclas.escribir(Ancla(secuencia=15, marca_alta=self.t, escrita_en=self.t))
        contenedor.reiniciar()
        r = servicios.arrancar()
        self.assertIsNone(r["restauracion"])
        self.assertEqual(self.publicar()["secuencia"], 23)                                            # la 21 fue `servicios_iniciados` y la 22 `salud_evaluada` (arrancando → operativo)

    def test_p13_la_marca_alta_sobrevive_al_arranque_por_las_anclas_y_la_base(self):
        self.avanzar(horas=5)
        servicios.ahora_ms()
        servicios.arrancar()
        servicios.parar()
        marca = self.t
        self.t -= 4 * 3_600_000                                                                       # el reloj del sistema retrocedió 4 h entre arranques
        contenedor.reiniciar()
        servicios.arrancar()
        self.assertEqual(servicios.ahora_ms(), marca)
        self.assertGreaterEqual(servicios.estado()["reloj"]["marca_alta"], marca)


class EstadoTests(BaseNodo):
    def test_operativo_sin_motivos_y_salud_publicada_solo_al_cambiar(self):
        e = servicios.estado()
        self.assertEqual((e["estado"], e["motivos"], e["restringido"]), (cat.OPERATIVO, [], False))
        self.assertEqual(len(self.eventos(tipo=cat.EV_SALUD_EVALUADA)), 1)                            # arrancando → operativo
        servicios.estado()
        servicios.estado()
        self.assertEqual(len(self.eventos(tipo=cat.EV_SALUD_EVALUADA)), 1)                            # BR-130: sin cambio no se publica
        self.assertEqual(set(e), {"estado", "motivos", "restringido", "version", "arranque", "base", "disco", "reloj", "cola", "purga", "servidor_en"})

    def test_q_n1_sin_transaccion_inmediata_el_nodo_queda_restringido_con_evento_y_asiento(self):
        self.s.salud = SaludFija(LecturaDeSalud(transaccion_inmediata=False))
        with self.assertLogs("avacom.nodo", level="ERROR"):
            e = servicios.estado()
        self.assertEqual((e["estado"], e["motivos"]), (cat.RESTRINGIDO, [cat.M_TRANSACCION_NO_INMEDIATA]))
        self.assertEqual(len(self.eventos(tipo=cat.EV_MODO_RESTRINGIDO)), 1)
        self.assertEqual(len(self.asientos(cat.A_MODO_RESTRINGIDO)), 1)
        self.assertTrue(servicios.estado_resumido()["restringido"])
        self.s.salud = SaludFija(LecturaDeSalud())
        e = servicios.estado()
        self.assertEqual(e["estado"], cat.OPERATIVO)
        self.assertEqual(len(self.eventos(tipo=cat.EV_MODO_RESTRINGIDO)), 2)                         # entró y salió
        self.assertEqual(len(self.asientos(cat.A_MODO_RESTRINGIDO)), 2)

    def test_arrancar_detecta_el_modo_de_transaccion_real(self):
        self.s.salud = SaludFija(LecturaDeSalud(transaccion_inmediata=False, base_integra=False))
        with self.assertLogs("avacom.nodo", level="ERROR"):
            r = servicios.arrancar()
        self.assertEqual((r["transaccion_inmediata"], r["base_integra"]), (False, False))
        self.assertEqual(set(servicios.estado_resumido()["motivos"]), {cat.M_TRANSACCION_NO_INMEDIATA, cat.M_BASE_DANADA})

    def test_la_lectura_real_de_la_salud_de_la_base_de_pruebas(self):
        lectura = self.s.salud.leer()
        self.assertTrue(lectura.transaccion_inmediata)
        self.assertTrue(self.s.salud.comprobar_integridad())
        self.assertEqual(servicios.estado()["estado"], cat.OPERATIVO)

    def test_health_suma_el_campo_nodo_sin_tocar_la_base(self):
        r = APIClient().get("/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertEqual(set(r.json()["nodo"]), {"estado", "motivos", "restringido", "apagado_sucio_previo", "version"})
        self.assertEqual(m.Evento.objects.count(), 0)

    def test_consumidores_nucleo_suspendidos_restringen(self):
        with override_settings(AVACOM_NODO_CONSUMIDORES_NUCLEO=("prueba",)):
            contenedor.reiniciar()
            self.consumidor_de_prueba(limite_rezago=2)
            self.publicar_varios(5)
            with self.assertLogs("avacom.nodo", level="ERROR"):
                e = servicios.estado()
            self.assertEqual((e["estado"], e["motivos"]), (cat.RESTRINGIDO, [cat.M_CONSUMIDOR_NUCLEO_SUSPENDIDO]))
