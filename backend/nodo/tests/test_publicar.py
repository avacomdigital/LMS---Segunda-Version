"""
`publicar` (FUN-159, BR-001, INV-022, R-02, R-06, R-08, R-13) y `leer`: hecho y evento en la misma transacción (una excepción después de publicar no deja nada), fuera de transacción
falla, el sobre sale completo con el contexto de la petición, lo fuera de norma falla en pruebas y entra marcado en producción, la secuencia es estrictamente creciente, el ancla se
refresca por lotes, y la medición de `publicar` (≤ 1 ms p95 en esta máquina) y del tamaño de un evento (para estimar el crecimiento sin purga).
"""
from __future__ import annotations

import json
import statistics
import time

from django.db import connection, transaction
from django.test import override_settings

from audit import contexto

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..dominio.errores import CargaInvalida, DatosInvalidos, FueraDeTransaccion, NombreInvalido, TipoNoCatalogado
from ..infraestructura import contenedor
from .base import TIPO, BaseNodo, BaseNodoTransaccional


class PublicarTests(BaseNodo):
    def test_el_sobre_sale_completo_con_su_secuencia(self):
        sobre = self.publicar(carga={"intento_id": "i-1", "asignacion_id": "a-1"})
        self.assertEqual(sobre["secuencia"], 1)
        self.assertEqual((sobre["tipo"], sobre["version"], sobre["modulo"], sobre["clase"], sobre["sensibilidad"]), (TIPO, 1, "evaluacion", cat.CLASE_APRENDIZAJE, cat.S_PERSONAL_MENOR))
        self.assertEqual((sobre["agregado_tipo"], sobre["agregado_id"], sobre["actor"], sobre["dispositivo_id"]), ("Intento", "i-1", cat.SISTEMA, cat.DISPOSITIVO_NODO))
        self.assertEqual(sobre["creado_en"], self.t)
        self.assertTrue(sobre["correlacion_id"] and sobre["evento_id"] and sobre["catalogado"] and not sobre["carga_omitida"])
        fila = m.Evento.objects.get(secuencia=1)
        self.assertEqual(fila.carga, {"intento_id": "i-1", "asignacion_id": "a-1"})
        self.assertEqual(fila.evento_id, sobre["evento_id"])

    def test_el_actor_el_aparato_y_la_correlacion_salen_del_contexto_de_la_peticion(self):
        with contexto.con(usuario_id="u-9", dispositivo_id="hw-9", corr="corr-9", origen=contexto.ORIGEN_API):
            sobre = self.publicar()
        self.assertEqual((sobre["actor"], sobre["dispositivo_id"], sobre["correlacion_id"]), ("u-9", "hw-9", "corr-9"))
        with contexto.con(dispositivo_id="hw-7", corr="corr-7", origen=contexto.ORIGEN_API):
            sobre = self.publicar()
        self.assertEqual((sobre["actor"], sobre["dispositivo_id"]), ("aparato:hw-7", "hw-7"))      # una tableta sin sesión (la cola de respuestas) también es un actor
        sobre = self.publicar(actor="u-1", dispositivo_id="hw-1", correlacion_id="c-1")                # lo que el adaptador pasa manda
        self.assertEqual((sobre["actor"], sobre["dispositivo_id"], sobre["correlacion_id"]), ("u-1", "hw-1", "c-1"))

    def test_r02_una_excepcion_despues_de_publicar_no_deja_ni_hecho_ni_evento(self):
        class Falla(Exception):
            pass

        with self.assertRaises(Falla):
            with transaction.atomic():
                m.Consumidor.objects.create(nombre="hecho", modulo="x", fuentes=[], tipos=[], registrado_en=1, actualizado_en=1)      # «el hecho»
                servicios.publicar("evaluacion", "Intento", "i-1", TIPO, {"intento_id": "i-1"})
                raise Falla()
        self.assertEqual((m.Evento.objects.count(), m.Consumidor.objects.count()), (0, 0))
        # y una transacción revertida no consume número (P-02): el siguiente evento es el 1
        self.assertEqual(self.publicar()["secuencia"], 1)

    def test_la_secuencia_es_estrictamente_creciente(self):
        secuencias = [s["secuencia"] for s in self.publicar_varios(50)]
        self.assertEqual(secuencias, list(range(1, 51)))
        self.assertEqual(servicios.ultima_secuencia(), 50)
        self.assertEqual(servicios.ultima_secuencia("evaluacion"), 50)
        self.assertEqual(servicios.ultima_secuencia("aula"), 0)

    def test_r06_un_tipo_fuera_del_catalogo_falla_en_pruebas(self):
        with self.assertRaises(TipoNoCatalogado):
            self.publicar("evaluacion.lo_que_sea_pasado.v1")
        with self.assertRaises(NombreInvalido):
            self.publicar("Evaluacion.MalNombre")
        with self.assertRaises(DatosInvalidos):
            self.publicar(TIPO, modulo="gradebook")              # el tipo lo publica otro módulo (R-09)
        self.assertEqual(m.Evento.objects.count(), 0)

    def test_r06_en_produccion_lo_fuera_de_norma_entra_marcado_con_error_y_asiento(self):
        with override_settings(AVACOM_NODO_ESTRICTO=False):
            contenedor.reiniciar()
            with self.assertLogs("avacom.nodo", level="ERROR"):
                sobre = self.publicar("evaluacion.lo_que_sea_pasado.v1")
            self.assertFalse(sobre["catalogado"])
            self.assertEqual((sobre["clase"], sobre["sensibilidad"]), (cat.CLASE_APRENDIZAJE, cat.S_PERSONAL_MENOR))      # lo desconocido, como lo más sensible
            with self.assertLogs("avacom.nodo", level="ERROR"):
                sobre2 = self.publicar(carga={"intento_id": "i", "password": "x"})
            self.assertTrue(sobre2["carga_omitida"])
            self.assertEqual(m.Evento.objects.get(secuencia=sobre2["secuencia"]).carga, {"_omitida": "carga_con_datos_personales"})
            sobre3 = self.publicar(TIPO, modulo="gradebook")     # módulo ajeno: en producción no se pierde el hecho; se avisa
            self.assertTrue(sobre3["catalogado"])
        self.assertEqual(len(self.asientos(cat.A_EVENTO_NO_CATALOGADO)), 2)
        self.assertNotIn("password", json.dumps(self.asientos(cat.A_EVENTO_NO_CATALOGADO)[1].valor_nuevo))

    def test_r13_una_carga_con_datos_personales_falla_en_pruebas(self):
        with self.assertRaises(CargaInvalida):
            self.publicar(carga={"intento_id": "i", "alumno": {"nombres": "Juan"}})
        self.assertEqual(m.Evento.objects.count(), 0)

    def test_leer_filtra_por_modulo_y_tipos_y_dice_hasta_donde_miro(self):
        self.publicar_varios(3)
        self.publicar("aula.sesion.iniciada.v1", agregado=("Sesion", "s-1"), carga={"sesion_id": "s-1"})
        self.publicar("evaluacion.intento_entregado.v1", agregado=("Intento", "i-9"), carga={"intento_id": "i-9"})
        eventos, hasta = servicios.leer("evaluacion", 0, 10)
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), ([1, 2, 3, 5], 5))
        eventos, hasta = servicios.leer("evaluacion", 0, 10, ("evaluacion.intento_entregado.v1",))
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), ([5], 5))
        eventos, hasta = servicios.leer("evaluacion", 0, 2)
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), ([1, 2], 2))
        eventos, hasta = servicios.leer("classroom_engine", 0, 10)
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), ([4], 4))
        eventos, hasta = servicios.leer("classroom_engine", 4, 10)
        self.assertEqual((eventos, hasta), ([], 4))
        self.assertEqual(set(eventos_keys(servicios.leer("evaluacion", 0, 1)[0][0])), {"secuencia", "evento_id", "tipo", "version", "modulo", "creado_en", "agregado_tipo",
                                                                                            "agregado_id", "actor", "dispositivo_id", "correlacion_id", "clase", "sensibilidad", "carga",
                                                                                            "catalogado", "carga_omitida"})

    def test_p12_el_ancla_se_refresca_por_lotes_y_recuerda_la_mayor_secuencia(self):
        with override_settings(AVACOM_NODO_ANCLA_CADA_EVENTOS=10, AVACOM_NODO_ANCLA_CADA_MS=10 ** 9):
            contenedor.reiniciar()
            self.publicar_varios(9)
            self.assertIsNone(self.s.anclas.leer())
            self.publicar_varios(1)
            ancla = self.s.anclas.leer()
            self.assertEqual(ancla.secuencia, 10)
            self.publicar_varios(25)
            self.assertEqual(self.s.anclas.leer().secuencia, 30)
            self.assertGreaterEqual(self.s.anclas.leer().marca_alta, self.t)
        # el archivo existe en la carpeta temporal de la prueba, no en ProgramData
        self.assertTrue(self.s.anclas.ruta.exists())
        self.assertTrue(str(self.s.anclas.ruta).startswith(self.carpeta))

    def test_r08_publicar_es_un_insert_de_menos_de_un_milisegundo_p95(self):
        """Medido dentro de UNA transacción (lo que `publicar` añade al hecho). El commit durable se midió aparte (Fase 0): ≈1,3 ms p50 con synchronous=FULL."""
        tiempos = []
        with transaction.atomic():
            for i in range(1000):
                t0 = time.perf_counter()
                servicios.publicar("evaluacion", "Intento", f"i-{i}", TIPO, {"intento_id": f"i-{i}", "asignacion_id": "a-1", "alumno_id": "u-1", "instante": self.t})
                tiempos.append((time.perf_counter() - t0) * 1000)
        tiempos.sort()
        p95, p50 = tiempos[int(0.95 * len(tiempos)) - 1], statistics.median(tiempos)
        print(f"\n[medición] publicar: p50 {p50:.3f} ms · p95 {p95:.3f} ms · consultas por publicar: 1 INSERT")
        self.assertLess(p95, 1.5, f"p95 {p95:.3f} ms")
        with transaction.atomic():
            with self.assertNumQueries(1):
                servicios.publicar("evaluacion", "Intento", "i-x", TIPO, {"intento_id": "i-x"})

    def test_medicion_tamano_de_un_evento_para_estimar_el_crecimiento_sin_purga(self):
        """Q-N3: cuánto crece la cola por evento (fila + índices) con una carga típica de respuesta. Se imprime; el diseño lo convierte en MB por clase y por año."""
        def tamano() -> int:
            with connection.cursor() as c:
                c.execute("PRAGMA page_count")
                paginas = c.fetchone()[0]
                c.execute("PRAGMA page_size")
                return paginas * c.fetchone()[0]
        antes = tamano()
        carga = {"intento_id": "e3d2b2d0a0b44b9f8c1a5e1c2f3a4b5c", "asignacion_id": "9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a", "alumno_id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
                 "pregunta_ref": "l3-exam-q07", "curso_version": "2026.09.1", "sesion_ref": "s-0a1b2c3d", "secuencia": 12}
        with transaction.atomic():
            for i in range(2000):
                servicios.publicar("evaluacion", "Intento", f"i-{i % 30}", "evaluacion.respuesta_registrada.v1", carga)
        por_evento = (tamano() - antes) / 2000
        print(f"\n[medición] bytes por evento (fila + índices, carga de {len(json.dumps(carga))} B): {por_evento:.0f}")
        self.assertLess(por_evento, 4096)


def eventos_keys(evento: dict):
    return evento.keys()


class FueraDeTransaccionTests(BaseNodoTransaccional):
    """Un `TestCase` corre dentro de una transacción (siempre hay un bloque atómico): esto se prueba sin ella."""

    def test_r02_fuera_de_la_transaccion_del_hecho_falla_y_no_escribe_nada(self):
        with self.assertRaises(FueraDeTransaccion):
            servicios.publicar("evaluacion", "Intento", "i-1", TIPO, {"intento_id": "i-1"})
        self.assertEqual(m.Evento.objects.count(), 0)
        with transaction.atomic():
            self.assertEqual(servicios.publicar("evaluacion", "Intento", "i-1", TIPO, {"intento_id": "i-1"})["secuencia"], 1)
        self.assertEqual(m.Evento.objects.count(), 1)


class RelojTests(BaseNodo):
    def test_p13_ahora_ms_es_el_maximo_con_la_marca_alta_y_no_retrocede(self):
        self.assertEqual(servicios.ahora_ms(), self.t)
        self.avanzar(horas=1)
        self.assertEqual(servicios.ahora_ms(), self.t)
        marca = self.t
        self.t -= 3_600_000 * 2                  # el reloj del sistema retrocede dos horas
        self.assertEqual(servicios.ahora_ms(), marca)
        self.assertEqual(self.publicar()["creado_en"], marca)      # lo que se publica lleva el reloj del nodo, no el retrocedido
        self.avanzar(horas=3)
        self.assertEqual(servicios.ahora_ms(), self.t)

    def test_nuevo_id(self):
        self.assertEqual(len(servicios.nuevo_id()), 36)
