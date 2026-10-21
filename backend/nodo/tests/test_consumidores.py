"""
Los consumidores sobre el registro (P-06, P-07, BR-005…008, BR-011, INV-006, FUN-160…164): un consumidor de prueba que reproduce desde 0, descarta repetidos y no avanza la marca si
falla; el reintento con espera creciente, el problema y el reproceso, todo con el reloj falso (nada duerme); un consumidor v1 que recibe una v2 con un campo extra sin fallar; el
registro que rechaza un contrato incompatible; el estado de la cola sin carga útil; el rezago que suspende y avisa.
"""
from __future__ import annotations

import json
from unittest import mock

from django.test import override_settings  # noqa: F401 — usado en los casos de abajo

from .. import models as m
from .. import servicios
from ..aplicacion.puertos import Actor
from ..dominio import catalogo
from ..dominio import catalogos as cat
from ..dominio.errores import ConsumidorDesconocido, ConsumidorSinAplicador, ContratoIncompatible, DatosInvalidos, NoEncontrado, ProblemaYaResuelto, ReprocesoFallido
from ..infraestructura import contenedor
from .base import TIPO, BaseNodo

ENTREGADO = "evaluacion.intento_entregado.v1"
ADMIN = Actor(id="admin-1")


class ConsumidorTests(BaseNodo):
    def test_un_consumidor_nuevo_empieza_en_cero_y_aplica_solo_lo_de_su_fuente_y_sus_tipos(self):
        self.publicar_varios(3)
        self.publicar(ENTREGADO, agregado=("Intento", "i-9"), carga={"intento_id": "i-9"})
        self.publicar("aula.sesion.iniciada.v1", agregado=("Sesion", "s-1"), carga={"sesion_id": "s-1"})
        c = self.consumidor_de_prueba(tipos=(ENTREGADO,))
        self.assertEqual(servicios.marca("prueba", "evaluacion"), 0)                                   # BR-007
        r = c.lote()
        self.assertEqual((r["leidos"], r["procesados"], r["marca_anterior"], r["marca"], r["pendientes"], r["estado"]), (1, 1, 0, 4, False, cat.C_AL_DIA))
        self.assertEqual(c.aplicados, [4])
        self.assertEqual(servicios.marca("prueba", "evaluacion"), 4)                                   # miró hasta la última de SU fuente (la 5 es del aula)
        self.assertEqual(c.lote()["leidos"], 0)
        self.assertEqual(len(self.asientos(cat.A_CONSUMIDOR_REGISTRADO)), 1)

    def test_br008_reproducir_desde_cero_da_el_mismo_estado_y_los_repetidos_se_descartan(self):
        self.publicar_varios(5)
        c = self.consumidor_de_prueba()
        c.hasta_vaciar()
        antes = list(c.aplicados)
        r = servicios.reproducir("prueba", actor=ADMIN)
        self.assertEqual((r["marcas_reiniciadas"], r["estado"]), (1, cat.C_RECONSTRUYENDOSE))
        self.assertEqual(servicios.marca("prueba", "evaluacion"), 0)
        self.assertEqual(servicios.cola()["consumidores"][0]["estado"], cat.C_RECONSTRUYENDOSE)
        c.hasta_vaciar()
        self.assertEqual(c.aplicados, antes)                                                             # idempotente: los repetidos no cambian nada
        self.assertEqual(servicios.cola()["consumidores"][0]["estado"], cat.C_AL_DIA)
        self.assertFalse(m.MarcaLectura.objects.get(consumidor="prueba").reconstruyendose)
        self.assertEqual(len(self.asientos(cat.A_CONSUMIDOR_REPRODUCIDO)), 1)
        with self.assertRaises(ConsumidorDesconocido):
            servicios.reproducir("nadie", actor=ADMIN)
        with self.assertRaises(DatosInvalidos):
            servicios.reproducir("prueba", "aula", actor=ADMIN)

    def test_br005_la_marca_no_pasa_del_evento_que_falla_y_el_reintento_espera(self):
        self.publicar_varios(6)
        c = self.consumidor_de_prueba(falla_en={3})
        with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
            r = c.lote()
        self.assertEqual((r["procesados"], [f["secuencia"] for f in r["fallidos"]], r["marca"]), (5, [3], 2))      # lo de detrás se aplicó (idempotente); la marca se queda en 2
        self.assertEqual(c.aplicados, [1, 2, 4, 5, 6])
        marca, reintento, _ = self.s.uow(lectura=True).marcas.estado("prueba", "evaluacion")
        self.assertEqual((marca, reintento.secuencia, reintento.intentos), (2, 3, 1))
        self.assertGreater(reintento.proximo_en, self.t)
        self.assertTrue(reintento.ultimo_error.startswith("RuntimeError"))
        self.assertTrue(c.lote()["esperando"])                                                           # la espera no pasó: nada que hacer (nada duerme)
        self.assertEqual(c.lote()["procesados"], 0)
        self.avanzar(seg=2)
        with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
            r = c.lote()
        self.assertEqual((r["procesados"], r["marca"]), (3, 2))                                         # releyó 3, 4, 5, 6; la 3 falló otra vez; 4-6 ya estaban (descartados)
        self.assertEqual(self.s.uow(lectura=True).marcas.estado("prueba", "evaluacion")[1].intentos, 2)
        self.assertEqual(len(self.eventos(tipo=cat.EV_ENTREGA_REINTENTADA)), 2)
        # se corrige la causa: el siguiente lote aplica la 3 y la marca alcanza la cola
        c.falla_en.clear()
        self.avanzar(seg=5)
        r = c.lote()
        self.assertEqual((r["procesados"], r["marca"], r["fallidos"]), (4, 6, []))                      # 3 se aplica; 4-6 se releen y el consumidor los descarta (BR-008)
        self.assertEqual(sorted(c.aplicados), [1, 2, 3, 4, 5, 6])
        self.assertEqual(self.s.uow(lectura=True).marcas.estado("prueba", "evaluacion")[1].secuencia, 0)
        self.assertEqual(m.Problema.objects.count(), 0)

    def test_fun163_al_agotar_los_intentos_el_evento_se_aparta_y_la_marca_avanza(self):
        self.publicar_varios(4)
        with override_settings(AVACOM_NODO_MAX_INTENTOS=3):
            contenedor.reiniciar()
            c = self.consumidor_de_prueba(falla_en={2})
            for _ in range(3):
                with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                    r = c.lote()
                self.avanzar(seg=10)
            self.assertEqual(r["marca"], 2)                                                              # la marca pasa HASTA el apartado; lo de detrás se relee
            self.assertEqual(r["apartado"], m.Problema.objects.get().id)
            problema = m.Problema.objects.get()
            self.assertEqual((problema.consumidor, problema.fuente, problema.secuencia, problema.tipo, problema.intentos, problema.estado),
                             ("prueba", "evaluacion", 2, TIPO, 3, cat.PR_APARTADO))
            self.assertTrue(problema.ultimo_error.startswith("RuntimeError"))
            self.assertEqual(len(self.eventos(tipo=cat.EV_EVENTO_APARTADO)), 1)
            self.assertEqual(len(self.asientos(cat.A_EVENTO_APARTADO)), 1)
            self.assertEqual(self.s.uow(lectura=True).marcas.estado("prueba", "evaluacion")[1].secuencia, 0)
            r = c.lote()
            self.assertEqual((r["procesados"], r["marca"], r["fallidos"]), (2, 4, []))                   # 3 y 4 se releen; el consumidor los descarta (ya estaban) y la marca avanza
            self.assertEqual(sorted(c.aplicados), [1, 3, 4])
            cola = servicios.cola()
            self.assertEqual((cola["problemas"], cola["consumidores"][0]["problemas"], cola["consumidores"][0]["estado"]), (1, 1, cat.C_AL_DIA))

    def test_fun164_reprocesar_un_problema_es_idempotente_exige_el_permiso_y_deja_asiento(self):
        self.publicar_varios(3)
        with override_settings(AVACOM_NODO_MAX_INTENTOS=1):
            contenedor.reiniciar()
            c = self.consumidor_de_prueba(falla_en={2})
            with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                c.lote()
            problema = m.Problema.objects.get()
            # sigue fallando: el reproceso falla, el problema sigue apartado con un intento más
            with self.assertRaises(ReprocesoFallido), self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                servicios.reprocesar(problema.id, ADMIN)
            problema.refresh_from_db()
            self.assertEqual((problema.estado, problema.intentos_reproceso), (cat.PR_APARTADO, 1))
            self.assertEqual(len(self.asientos(cat.A_REPROCESO_FALLIDO)), 1)
            # se corrige la causa
            c.falla_en.clear()
            r = servicios.reprocesar(problema.id, ADMIN)
            self.assertEqual((r["estado"], r["resuelto_por"], r["secuencia"]), (cat.PR_REPROCESADO, "admin-1", 2))
            self.assertEqual(sorted(c.aplicados), [1, 2, 3])
            self.assertEqual(len(self.asientos(cat.A_EVENTO_REPROCESADO)), 1)
            self.assertEqual(len(self.eventos(tipo=cat.EV_EVENTO_REPROCESADO)), 1)
            with self.assertRaises(ProblemaYaResuelto):
                servicios.reprocesar(problema.id, ADMIN)
            with self.assertRaises(NoEncontrado):
                servicios.reprocesar(99999, ADMIN)
            # sin quien aplique en este proceso
            self.s.aplicadores.clear()
            m.Problema.objects.filter(pk=problema.id).update(estado=cat.PR_APARTADO)
            with self.assertRaises(ConsumidorSinAplicador):
                servicios.reprocesar(problema.id, ADMIN)

    def test_inv006_un_consumidor_v1_recibe_una_v2_con_un_campo_extra_y_no_falla(self):
        v2 = "evaluacion.intento_abierto.v2"
        with mock.patch.dict(catalogo.TIPOS, {v2: ("evaluacion", cat.CLASE_APRENDIZAJE, cat.S_PERSONAL_MENOR, ("intento_id",), "clase", (2,))}):
            self.publicar(TIPO, carga={"intento_id": "i-1"})
            self.publicar(v2, agregado=("Intento", "i-2"), carga={"intento_id": "i-2", "campo_nuevo": "que el v1 no conoce"})
            c = self.consumidor_de_prueba(tipos=(TIPO,))                                                 # declara la v1
            r = c.lote()
        self.assertEqual((r["procesados"], r["fallidos"]), (2, []))
        self.assertEqual(c.cargas[1]["campo_nuevo"], "que el v1 no conoce")
        # y al revés: declarar una versión que nadie publica es incompatible (INV-007)
        with self.assertRaises(ContratoIncompatible) as ctx:
            servicios.registrar_consumidor("otro", "pruebas", ("evaluacion",), ("evaluacion.intento_abierto.v3",), aplicar=lambda e: None)
        self.assertEqual(ctx.exception.extra["tipos"][0]["motivo"], "version_no_producida")
        with self.assertRaises(ContratoIncompatible):
            servicios.registrar_consumidor("otro", "pruebas", ("evaluacion",), ("no.existe.v1",), aplicar=lambda e: None)
        self.assertEqual(len(self.asientos(cat.A_MODULO_INCOMPATIBLE)), 2)
        self.assertIsNone(m.Consumidor.objects.filter(pk="otro").first())

    def test_registrar_exige_lo_minimo_y_es_idempotente(self):
        with self.assertRaises(DatosInvalidos):
            servicios.registrar_consumidor("", "pruebas", ("evaluacion",))
        with self.assertRaises(DatosInvalidos):
            servicios.registrar_consumidor("x", "pruebas", ())
        a = servicios.registrar_consumidor("x", "pruebas", ("evaluacion", "aula"), version_contrato=1)
        b = servicios.registrar_consumidor("x", "pruebas", ("evaluacion", "aula"), version_contrato=1)
        self.assertEqual((a["registrado_en"], b["registrado_en"]), (self.t, self.t))
        self.assertEqual(m.MarcaLectura.objects.filter(consumidor="x").count(), 2)
        self.assertEqual(len(self.asientos(cat.A_CONSUMIDOR_REGISTRADO)), 1)                             # repetir sin cambios no asienta
        with self.assertRaises(ConsumidorDesconocido):
            servicios.aplicar_lote("nadie", "evaluacion", aplicar=lambda e: None)
        with self.assertRaises(DatosInvalidos):
            servicios.aplicar_lote("x", "gradebook", aplicar=lambda e: None)
        with self.assertRaises(ConsumidorSinAplicador):
            servicios.aplicar_lote("x", "evaluacion")

    def test_br018_desregistrar_deja_de_contar_y_conserva_las_marcas(self):
        self.publicar_varios(2)
        c = self.consumidor_de_prueba()
        c.lote()
        self.assertTrue(servicios.desregistrar_consumidor("prueba"))
        self.assertFalse(servicios.desregistrar_consumidor("prueba"))
        self.assertEqual(servicios.cola()["consumidores"], [])
        self.assertEqual(servicios.marca("prueba", "evaluacion"), 2)
        self.assertEqual(len(self.asientos(cat.A_CONSUMIDOR_DESREGISTRADO)), 1)
        with self.assertRaises(ConsumidorDesconocido):
            c.lote()

    def test_p06_el_rezago_sobre_el_limite_suspende_y_avisa_una_vez(self):
        self.consumidor_de_prueba(limite_rezago=5)
        self.publicar_varios(10)
        cola = servicios.cola()
        self.assertEqual((cola["consumidores"][0]["estado"], cola["consumidores"][0]["pendientes"]), (cat.C_SUSPENDIDO, 10))
        c = self.consumidor_de_prueba(limite_rezago=5, falla_en=set(range(1, 11)))
        with self.assertLogs("avacom.nodo", level="ERROR"):
            c.lote()
        self.assertEqual(m.Consumidor.objects.get(pk="prueba").estado, cat.C_SUSPENDIDO)
        self.assertEqual(len(self.eventos(tipo=cat.EV_CONSUMIDOR_REZAGADO)), 1)
        c.falla_en.clear()
        self.avanzar(seg=5)
        c.hasta_vaciar()
        self.assertEqual(m.Consumidor.objects.get(pk="prueba").estado, cat.C_AL_DIA)

    def test_cap097_el_estado_de_la_cola_no_lleva_ninguna_carga(self):
        self.publicar_varios(3, carga={"intento_id": "secreto-de-prueba-123"})
        c = self.consumidor_de_prueba(falla_en={2})
        with override_settings(AVACOM_NODO_MAX_INTENTOS=1):
            contenedor.reiniciar()
            c = self.consumidor_de_prueba(falla_en={2})
            with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                c.lote()
        cola = json.dumps(servicios.cola())
        problemas = json.dumps(servicios.problemas(ADMIN))
        for texto in (cola, problemas):
            self.assertNotIn("secreto-de-prueba", texto)
            self.assertNotIn('"carga"', texto)
        p = servicios.problemas(ADMIN)
        self.assertEqual((p["total"], p["problemas"][0]["secuencia"], p["problemas"][0]["tipo"]), (1, 2, TIPO))
        self.assertEqual(servicios.problemas(ADMIN, estado=cat.PR_REPROCESADO)["total"], 0)
        with self.assertRaises(DatosInvalidos):
            servicios.problemas(ADMIN, estado="raro")

    def test_p15_los_eventos_tecnicos_se_agregan_por_lote_y_se_pueden_apagar(self):
        self.publicar_varios(5)
        c = self.consumidor_de_prueba()
        c.lote()
        avanzadas = self.eventos(tipo=cat.EV_MARCA_AVANZADA)
        self.assertEqual(len(avanzadas), 1)                                                              # UNO por lote, no uno por evento
        self.assertEqual((avanzadas[0].carga["desde"], avanzadas[0].carga["hasta"], avanzadas[0].carga["aplicados"], avanzadas[0].modulo, avanzadas[0].clase),
                         (0, 5, 5, cat.MODULO, cat.CLASE_SINCRONIZACION))
        with override_settings(AVACOM_NODO_EVENTOS_TECNICOS=False):
            contenedor.reiniciar()
            c = self.consumidor_de_prueba()
            self.publicar_varios(2)
            c.lote()
        self.assertEqual(len(self.eventos(tipo=cat.EV_MARCA_AVANZADA)), 1)
        # un evento nodo.* jamás provoca otro: lo publicado por el nodo no genera más filas nodo.* al leerse
        total = m.Evento.objects.count()
        servicios.cola()
        self.assertEqual(m.Evento.objects.count(), total)

    def test_hasta_vaciar_recorre_lotes_y_se_detiene_en_un_fallo(self):
        self.publicar_varios(7)
        c = self.consumidor_de_prueba()
        r = c.hasta_vaciar(limite=3)
        self.assertEqual((r["leidos"], r["procesados"], r["marca"], r["pendientes"]), (7, 7, 7, False))
        c2 = self.consumidor_de_prueba("otro", falla_en={5})
        with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
            r = c2.hasta_vaciar(limite=3)
        self.assertEqual((r["leidos"], r["marca"]), (6, 4))                                              # dos lotes: el segundo tuvo un fallo y ahí se detuvo
