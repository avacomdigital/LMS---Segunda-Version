"""
El corte de un módulo y la fachada de lectura (P-05) con un lector legado FALSO (ningún módulo se corta en la Fase 2): el contador salta, una marca previa al corte sigue valiendo sin
perder ni repetir, un consumidor reconstruido reproduce toda la historia, el corte es de una sola vía y va en una transacción, y un módulo cortado sin lector en este proceso no se sirve a
medias.
"""
from __future__ import annotations

from django.db import transaction

from .. import models as m
from .. import servicios
from ..aplicacion.leer import Cortar, FuenteLegadaAusente
from ..dominio import catalogos as cat
from ..dominio.errores import FueraDeTransaccion, ModuloYaCortado
from .base import BaseNodo, BaseNodoTransaccional

MODULO = "device_manager"
TIPO_DM = "dispositivo.registrado.v1"


def _legado(n: int) -> list[dict]:
    return [{"secuencia": i, "tipo": TIPO_DM, "agregado_tipo": "Dispositivo", "agregado_id": f"d-{i}", "carga": {"dispositivo_id": f"d-{i}"}, "creado_en": 1_000 + i} for i in range(1, n + 1)]


def lector_de(filas: list[dict]):
    """Lo que un módulo cortado registra: lee SU tabla antigua con `desde < id ≤ hasta` (y esos tipos), como lo hará `servicios.eventos_legados` en la Fase 3."""
    def leer(desde, limite, tipos, hasta):
        validas = [f for f in filas if desde < f["secuencia"] <= hasta and (tipos is None or f["tipo"] in tipos)]
        lote = validas[:limite]
        return [dict(f) for f in lote], (lote[-1]["secuencia"] if len(lote) >= limite else hasta)
    return leer


class CorteTests(BaseNodo):
    def cortar(self, n_legado: int = 30) -> list[dict]:
        legado = _legado(n_legado)
        servicios.registrar_lector_legado(MODULO, lector_de(legado))
        r = servicios.cortar(MODULO, n_legado)
        self.assertEqual((r["modulo"], r["ultima_legada"], r["contador"]), (MODULO, n_legado, n_legado + 1))      # +1: el evento `nodo.modulo_cortado.v1` de la misma transacción
        return legado

    def test_el_corte_sube_el_contador_y_queda_asentado(self):
        self.cortar(30)
        sobre = self.publicar(TIPO_DM, modulo=MODULO, agregado=("Dispositivo", "d-31"), carga={"dispositivo_id": "d-31"})
        self.assertGreater(sobre["secuencia"], 30)                                                   # ninguna secuencia nueva coincide con un id legado
        self.assertEqual(servicios.corte_de(MODULO)["ultima_legada"], 30)
        self.assertEqual(len(self.asientos(cat.A_MODULO_CORTADO)), 1)
        self.assertEqual(len(self.eventos(tipo=cat.EV_MODULO_CORTADO)), 1)
        with self.assertRaises(ModuloYaCortado):
            servicios.cortar(MODULO, 30)

    def test_la_fachada_sirve_un_flujo_continuo_legado_y_nuevo(self):
        self.cortar(30)
        nuevos = [self.publicar(TIPO_DM, modulo=MODULO, agregado=("Dispositivo", f"d-{i}"), carga={"dispositivo_id": f"d-{i}"})["secuencia"] for i in range(31, 36)]
        eventos, hasta = servicios.leer(MODULO, 0, 10)
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), (list(range(1, 11)), 10))
        self.assertTrue(all(e["legado"] for e in eventos))
        eventos, hasta = servicios.leer(MODULO, 27, 10)
        self.assertEqual([e["secuencia"] for e in eventos], [28, 29, 30] + nuevos)
        self.assertEqual(hasta, nuevos[-1])
        eventos, hasta = servicios.leer(MODULO, 30, 10)
        self.assertEqual([e["secuencia"] for e in eventos], nuevos)
        eventos, hasta = servicios.leer(MODULO, nuevos[-1], 10)
        self.assertEqual((eventos, hasta), ([], nuevos[-1]))
        # la forma de un legado es la del sobre (con lo que no tenía, vacío)
        legado = servicios.leer(MODULO, 0, 1)[0][0]
        self.assertEqual((legado["modulo"], legado["evento_id"], legado["version"], legado["actor"]), (MODULO, f"{MODULO}:1", 1, ""))
        # y los tipos filtran en los dos lados
        self.publicar("dispositivo.bloqueado.v1", modulo=MODULO, agregado=("Dispositivo", "d-x"), carga={"dispositivo_id": "d-x"})
        eventos, _ = servicios.leer(MODULO, 25, 50, ("dispositivo.bloqueado.v1",))
        self.assertEqual([e["tipo"] for e in eventos], ["dispositivo.bloqueado.v1"])

    def test_una_marca_previa_al_corte_sigue_valiendo_y_marca_cero_reproduce_toda_la_historia(self):
        self.cortar(30)
        nuevos = [self.publicar(TIPO_DM, modulo=MODULO, agregado=("Dispositivo", f"d-{i}"), carga={"dispositivo_id": f"d-{i}"})["secuencia"] for i in range(31, 41)]
        # un consumidor que iba por la 20 (un id de la tabla antigua) antes del corte
        c = self.consumidor_de_prueba("viejo", MODULO)
        with transaction.atomic():
            self.s.uow().marcas.guardar("viejo", MODULO, 20, self.s.uow().marcas.estado("viejo", MODULO)[1], self.t)
        c.hasta_vaciar(limite=7)
        self.assertEqual(c.aplicados, list(range(21, 31)) + nuevos)                                  # ni perdió ni repitió
        # uno reconstruido (marca 0) ve toda la historia (BR-007)
        c2 = self.consumidor_de_prueba("nuevo", MODULO)
        c2.hasta_vaciar(limite=4)
        self.assertEqual(c2.aplicados, list(range(1, 31)) + nuevos)
        self.assertEqual(servicios.marca("nuevo", MODULO), nuevos[-1])
        cola = servicios.cola()
        self.assertEqual(cola["cortes"][0]["modulo"], MODULO)
        self.assertEqual([x["estado"] for x in cola["consumidores"]], [cat.C_AL_DIA, cat.C_AL_DIA])

    def test_un_modulo_cortado_sin_lector_en_este_proceso_no_se_sirve_a_medias(self):
        self.cortar(10)
        self.s.legados.clear()
        with self.assertRaises(FuenteLegadaAusente):
            servicios.leer(MODULO, 0, 10)
        eventos, _ = servicios.leer(MODULO, 10, 10)                                                  # la zona nueva sí se sirve
        self.assertEqual(eventos, [])

    def test_un_problema_sobre_un_evento_legado_se_reprocesa_por_la_fachada(self):
        from django.test import override_settings

        from ..aplicacion.puertos import Actor
        from ..infraestructura import contenedor

        with override_settings(AVACOM_NODO_MAX_INTENTOS=1):
            contenedor.reiniciar()
            self.cortar(5)
            c = self.consumidor_de_prueba("c", MODULO, falla_en={3})
            with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                c.hasta_vaciar()
            problema = m.Problema.objects.get()
            self.assertEqual((problema.secuencia, problema.evento_id), (3, f"{MODULO}:3"))
            c.falla_en.clear()
            r = servicios.reprocesar(problema.id, Actor(id="admin"))
            self.assertEqual(r["estado"], cat.PR_REPROCESADO)
            self.assertEqual(c.aplicados, [1, 2, 4, 5, 3])

    def test_un_modulo_sin_corte_se_lee_solo_de_la_cola_nueva(self):
        self.assertEqual(servicios.leer("classroom_engine", 0, 10), ([], 0))
        self.publicar("aula.sesion.iniciada.v1", agregado=("Sesion", "s-1"), carga={"sesion_id": "s-1"})
        eventos, hasta = servicios.leer("classroom_engine", 0, 10)
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), ([1], 1))
        self.assertNotIn("legado", eventos[0])


class CorteEnTransaccionTests(BaseNodoTransaccional):
    def test_el_corte_va_en_una_transaccion(self):
        with self.assertRaises(FueraDeTransaccion):
            with self.s.uow(lectura=True) as uow:
                Cortar(self.s).ejecutar(uow, MODULO, 10)
        self.assertIsNone(servicios.corte_de(MODULO))
