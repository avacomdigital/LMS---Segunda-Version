"""
La purga (P-08): apagada por defecto; con el respaldo ausente (MOD-016 no existe) nunca borra nada y dice por qué; con un respaldo falso que cubre, borra sólo lo elegible, en orden y
sin huecos, nunca lo inmutable, y el contador no retrocede por borrar.
"""
from __future__ import annotations

from django.test import override_settings

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..infraestructura import contenedor
from ..infraestructura.respaldo import RespaldoFijo, SincronizacionFija
from .base import BaseNodo

TECNICO = "reporte.exportado.v1"            # clase técnico: 30 días


class PurgaTests(BaseNodo):
    def test_apagada_por_defecto(self):
        self.publicar_varios(3)
        self.assertEqual(servicios.purgar(), {"habilitada": False, "evaluados": 0, "purgados": 0, "motivos": {}})
        self.assertEqual(m.Evento.objects.count(), 3)

    def test_sin_mod016_nada_es_elegible_y_la_cola_crece(self):
        for i in range(3):
            self.publicar(TECNICO, agregado=("Exportacion", f"x-{i}"), carga={"exportacion_id": f"x-{i}"})
        self.avanzar(dias=40)
        r = servicios.purgar(forzar=True)
        self.assertEqual((r["purgados"], r["evaluados"]), (0, 3))
        self.assertEqual(r["motivos"], {"sin_respaldo_verificado": 3})
        self.assertEqual(m.Evento.objects.count(), 3)
        self.assertEqual(servicios.cola()["purga"], {"habilitada": False, "respaldo_verificado_hasta": 0})

    def test_con_respaldo_borra_solo_lo_elegible_en_orden_y_sin_huecos(self):
        with override_settings(AVACOM_NODO_PURGA=True):
            contenedor.reiniciar()
            for i in range(6):
                self.publicar(TECNICO, agregado=("Exportacion", f"x-{i}"), carga={"exportacion_id": f"x-{i}"})
            self.publicar("auditoria.cadena_verificada.v1", agregado=("Cadena", "c"), carga={"tramo": 1})       # inmutable: la 7
            c = self.consumidor_de_prueba("lector", "reporting")
            c.lote()
            self.assertEqual(servicios.marca("lector", "reporting"), 6)
            self.s.respaldo = RespaldoFijo(hasta=4)                                                   # el respaldo verificado cubre hasta la 4
            self.avanzar(dias=8)                                                                      # pasó la mínima (7) pero no la de la clase (30)
            r = servicios.purgar()
            self.assertEqual((r["purgados"], r["motivos"].get("retencion_vigente")), (0, 8))         # 6 técnicos + 1 auditoría + 1 `nodo.marca_lectura_avanzada` (sincronización, 30 d)
            self.avanzar(dias=30)
            r = servicios.purgar()
            self.assertEqual(r["purgados"], 4)                                                        # 1–4: respaldadas, superadas, vencidas
            self.assertEqual(sorted(m.Evento.objects.values_list("secuencia", flat=True))[:3], [5, 6, 7])
            self.assertEqual(len(self.asientos(cat.A_PURGA_EJECUTADA)), 1)
            # el contador no retrocede (INV-002): el siguiente evento sigue después del último
            self.assertGreater(self.publicar(TECNICO, agregado=("Exportacion", "x-z"), carga={"exportacion_id": "x-z"})["secuencia"], 7)
            # un consumidor que no superó la 5 la retiene, y con ella todo lo que sigue (sin huecos)
            self.s.respaldo = RespaldoFijo(hasta=100)
            servicios.registrar_consumidor("rezagado", "pruebas", ("reporting",), aplicar=lambda e: None)
            self.avanzar(dias=40)
            r = servicios.purgar()
            self.assertEqual((r["purgados"], r["motivos"].get("consumidor_pendiente")), (0, 3))         # 5, 6 y la x-z de arriba: lo de `reporting` que el rezagado no superó
            servicios.desregistrar_consumidor("rezagado")                                               # BR-018: desinstalado, deja de bloquear
            r = servicios.purgar()
            self.assertEqual(r["purgados"], 2)                                                          # 5 y 6; la 7 (auditoría) jamás
            self.assertTrue(m.Evento.objects.filter(secuencia=7).exists())
            self.assertIn("inmutable", r["motivos"])

    def test_con_sincronizacion_habilitada_hace_falta_el_reconocimiento(self):
        with override_settings(AVACOM_NODO_PURGA=True):
            contenedor.reiniciar()
            self.publicar(TECNICO, agregado=("Exportacion", "x"), carga={"exportacion_id": "x"})
            self.s.respaldo = RespaldoFijo(hasta=10)
            self.s.sincronizacion = SincronizacionFija(habilitada=True, reconocida_hasta=0)
            self.avanzar(dias=40)
            r = servicios.purgar()
            self.assertEqual((r["purgados"], r["motivos"]), (0, {"sin_reconocer": 1}))
            self.s.sincronizacion = SincronizacionFija(habilitada=True, reconocida_hasta=1)
            self.assertEqual(servicios.purgar()["purgados"], 1)
