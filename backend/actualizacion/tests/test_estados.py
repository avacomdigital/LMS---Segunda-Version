"""
La máquina de estados (P-05), la ventana (P-08) y la reversión a 14 días (P-09): la tabla completa estados × filas, y el estado DERIVADO del historial en cada recorrido.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.test import SimpleTestCase

from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import estados, orden, ventana
from actualizacion.dominio.errores import DatosInvalidos, EstadoInvalido, FueraDePlazoReversion

from .emisor import AHORA, manifiesto_de_ejemplo


@dataclass(frozen=True)
class F:
    tipo: str
    en: int = AHORA
    detalle: dict | None = None


def derivar(*filas: F):
    return estados.derivar([F(f.tipo, f.en, f.detalle or {}) for f in filas])


class TablaDeTransicionesTests(SimpleTestCase):
    PERMITIDAS = {
        None: {cat.H_RECIBIDO},
        cat.RECIBIDO: {cat.H_VERIFICADO, cat.H_INCOMPATIBLE},
        cat.VERIFICADO: {cat.H_INCOMPATIBLE, cat.H_PROGRAMADO, cat.H_BLOQUEADA, cat.H_APLICANDO},
        cat.INCOMPATIBLE: {cat.H_VERIFICADO, cat.H_BLOQUEADA},
        cat.PROGRAMADO: {cat.H_PROGRAMADO, cat.H_DESPROGRAMADO, cat.H_VENTANA_VENCIDA, cat.H_BLOQUEADA, cat.H_APLICANDO},
        cat.APLICANDO: {cat.H_APLICADO, cat.H_REVERTIDO, cat.H_REVERSION_FALLIDA, cat.H_APLAZADA},
        cat.APLICADO: {cat.H_APLICANDO, cat.H_ARCHIVADO, cat.H_BLOQUEADA},
        cat.REVERSION_FALLIDA: {cat.H_APLICANDO, cat.H_BLOQUEADA},
        cat.REVERTIDO: set(),
        cat.ARCHIVADO: set(),
    }

    def test_la_tabla_completa_estados_por_filas(self):
        """Cada par (estado, tipo de fila) está permitido exactamente cuando la tabla lo dice; lo demás es `EstadoInvalido`. `rechazado` no entra: no es una fila de un paquete."""
        estados_todos = [None, *cat.ESTADOS]
        self.assertEqual(set(estados_todos), set(self.PERMITIDAS))
        for estado in estados_todos:
            for tipo in cat.HISTORIAL:
                if tipo == cat.H_RECHAZADO:
                    with self.assertRaises(EstadoInvalido):
                        estados.transicion(estado, None, tipo)
                    continue
                if tipo in self.PERMITIDAS[estado]:
                    nuevo = estados.transicion(estado, cat.VERIFICADO, tipo)
                    self.assertIn(nuevo, cat.ESTADOS, (estado, tipo))
                else:
                    with self.assertRaises(EstadoInvalido, msg=(estado, tipo)):
                        estados.transicion(estado, cat.VERIFICADO, tipo)

    def test_los_estados_del_maestro_son_seis_y_las_extensiones_estan_marcadas(self):
        self.assertEqual(cat.ESTADOS_DEL_MAESTRO, ("recibido", "verificado", "incompatible", "aplicado", "revertido", "archivado"))
        self.assertEqual(set(cat.ESTADOS_EXTENSION) & set(cat.ESTADOS_DEL_MAESTRO), set())
        self.assertEqual(cat.TERMINALES, (cat.REVERTIDO, cat.ARCHIVADO))

    def test_una_aplazada_vuelve_al_estado_anterior(self):
        self.assertEqual(estados.transicion(cat.APLICANDO, cat.PROGRAMADO, cat.H_APLAZADA), cat.PROGRAMADO)
        self.assertEqual(estados.transicion(cat.APLICANDO, cat.VERIFICADO, cat.H_APLAZADA), cat.VERIFICADO)
        self.assertEqual(estados.transicion(cat.APLICANDO, cat.APLICADO, cat.H_APLAZADA), cat.VERIFICADO)       # una reversión aplazada deja el paquete sin su «aplicado»… no: ver abajo


class DerivarTests(SimpleTestCase):
    def test_sin_filas_no_hay_estado(self):
        d = derivar()
        self.assertEqual((d.estado, d.aplicado_en, d.ventana, d.en_curso), (None, None, None, False))

    def test_el_camino_feliz_recibido_verificado_programado_aplicando_aplicado(self):
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO))
        self.assertEqual(d.estado, cat.VERIFICADO)
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_PROGRAMADO, detalle={"desde": AHORA + 1, "hasta": AHORA + 2}))
        self.assertEqual((d.estado, d.ventana), (cat.PROGRAMADO, {"desde": AHORA + 1, "hasta": AHORA + 2}))
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_PROGRAMADO, detalle={"desde": 1, "hasta": 2}), F(cat.H_APLICANDO, detalle={"orden_id": "o-1", "accion": "aplicar"}))
        self.assertEqual((d.estado, d.en_curso, d.orden_id, d.accion, d.previo), (cat.APLICANDO, True, "o-1", "aplicar", cat.PROGRAMADO))
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_APLICANDO, detalle={"orden_id": "o-1"}), F(cat.H_APLICADO, en=AHORA + 60_000))
        self.assertEqual((d.estado, d.aplicado_en, d.revertible_hasta, d.orden_id, d.ventana), (cat.APLICADO, AHORA + 60_000, AHORA + 60_000 + 14 * cat.DIA_MS, None, None))

    def test_incompatible_conserva_su_lista_y_puede_volver_a_verificado(self):
        lista = [{"codigo": "serie_menor", "modulo": "reporting", "detalle": "x"}]
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_INCOMPATIBLE, detalle={"incompatibilidades": lista}))
        self.assertEqual((d.estado, list(d.incompatibilidades)), (cat.INCOMPATIBLE, lista))
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_INCOMPATIBLE, detalle={"incompatibilidades": lista}), F(cat.H_VERIFICADO))
        self.assertEqual((d.estado, d.incompatibilidades), (cat.VERIFICADO, ()))

    def test_bloqueada_no_cambia_el_estado(self):
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_BLOQUEADA))
        self.assertEqual(d.estado, cat.VERIFICADO)
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_PROGRAMADO, detalle={"desde": 1, "hasta": 2}), F(cat.H_BLOQUEADA))
        self.assertEqual((d.estado, d.ventana), (cat.PROGRAMADO, {"desde": 1, "hasta": 2}))

    def test_desprogramar_y_ventana_vencida_vuelven_a_verificado_sin_ventana(self):
        base = (F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_PROGRAMADO, detalle={"desde": 1, "hasta": 2}))
        self.assertEqual((derivar(*base, F(cat.H_DESPROGRAMADO)).estado, derivar(*base, F(cat.H_DESPROGRAMADO)).ventana), (cat.VERIFICADO, None))
        self.assertEqual((derivar(*base, F(cat.H_VENTANA_VENCIDA)).estado, derivar(*base, F(cat.H_VENTANA_VENCIDA)).ventana), (cat.VERIFICADO, None))

    def test_aplazada_vuelve_al_estado_previo(self):
        base = (F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_PROGRAMADO, detalle={"desde": 1, "hasta": 2}), F(cat.H_APLICANDO, detalle={"orden_id": "o"}))
        d = derivar(*base, F(cat.H_APLAZADA))
        self.assertEqual((d.estado, d.ventana, d.orden_id), (cat.PROGRAMADO, {"desde": 1, "hasta": 2}, None))
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_APLICANDO, detalle={"orden_id": "o"}), F(cat.H_APLAZADA))
        self.assertEqual((d.estado, d.ventana, d.orden_id), (cat.VERIFICADO, None, None))

    def test_la_reversion_automatica_y_la_fallida(self):
        base = (F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_APLICANDO, detalle={"orden_id": "o"}))
        d = derivar(*base, F(cat.H_REVERTIDO))
        self.assertEqual((d.estado, d.aplicado_en, d.revertible_hasta), (cat.REVERTIDO, None, None))
        d = derivar(*base, F(cat.H_REVERSION_FALLIDA))
        self.assertEqual((d.estado, d.aplicado_en), (cat.REVERSION_FALLIDA, None))
        d = derivar(*base, F(cat.H_REVERSION_FALLIDA), F(cat.H_APLICANDO, detalle={"orden_id": "o2", "accion": "revertir"}), F(cat.H_REVERTIDO))
        self.assertEqual(d.estado, cat.REVERTIDO)

    def test_la_reversion_manual_dentro_de_14_dias_y_fuera(self):
        aplicado = (F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_APLICANDO, detalle={"orden_id": "o"}), F(cat.H_APLICADO, en=AHORA))
        d = derivar(*aplicado)
        self.assertTrue(d.revertible(AHORA + 13 * cat.DIA_MS))
        self.assertTrue(d.revertible(AHORA + 14 * cat.DIA_MS - 1))
        self.assertFalse(d.revertible(AHORA + 14 * cat.DIA_MS))
        self.assertTrue(d.plazo_vencido(AHORA + 14 * cat.DIA_MS))
        estados.exigir_revertible(d, AHORA + cat.DIA_MS)
        with self.assertRaises(FueraDePlazoReversion) as ctx:
            estados.exigir_revertible(d, AHORA + 14 * cat.DIA_MS)
        self.assertEqual(ctx.exception.extra["revertible_hasta"], AHORA + 14 * cat.DIA_MS)
        # la reversión manual: aplicando (revertir) → revertido
        d = derivar(*aplicado, F(cat.H_APLICANDO, detalle={"orden_id": "o2", "accion": "revertir"}), F(cat.H_REVERTIDO))
        self.assertEqual((d.estado, d.aplicado_en), (cat.REVERTIDO, None))
        # archivado a los 14 días: terminal, sin reversión
        d = derivar(*aplicado, F(cat.H_ARCHIVADO, en=AHORA + 14 * cat.DIA_MS))
        self.assertEqual((d.estado, d.aplicado_en, d.revertible(AHORA + 15 * cat.DIA_MS)), (cat.ARCHIVADO, None, False))
        with self.assertRaises(EstadoInvalido):
            estados.exigir_revertible(d, AHORA)

    def test_que_se_puede_aplicar_y_programar(self):
        for tipo_final, aplicable, programable in ((cat.H_VERIFICADO, True, True), (cat.H_INCOMPATIBLE, True, False)):
            d = derivar(F(cat.H_RECIBIDO), F(tipo_final))
            if aplicable:
                estados.exigir_aplicable(d)
            if programable:
                estados.exigir_programable(d)
            else:
                with self.assertRaises(EstadoInvalido):
                    estados.exigir_programable(d)
        d = derivar(F(cat.H_RECIBIDO), F(cat.H_VERIFICADO), F(cat.H_APLICANDO, detalle={"orden_id": "o"}))
        with self.assertRaises(EstadoInvalido):
            estados.exigir_aplicable(d)
        with self.assertRaises(EstadoInvalido):
            estados.exigir_programable(d)

    def test_una_fila_imposible_en_el_historial_se_detecta(self):
        with self.assertRaises(EstadoInvalido):
            derivar(F(cat.H_APLICADO))
        with self.assertRaises(EstadoInvalido):
            derivar(F(cat.H_RECIBIDO), F(cat.H_APLICADO))

    def test_el_resultado_del_host_se_traduce_a_una_fila(self):
        self.assertEqual(estados.resultado_a_fila(cat.R_APLICADO, cat.ACCION_APLICAR), cat.H_APLICADO)
        self.assertEqual(estados.resultado_a_fila(cat.R_REVERTIDO, cat.ACCION_APLICAR), cat.H_REVERTIDO)
        self.assertEqual(estados.resultado_a_fila(cat.R_REVERTIDO, cat.ACCION_REVERTIR), cat.H_REVERTIDO)
        self.assertEqual(estados.resultado_a_fila(cat.R_REVERSION_FALLIDA, cat.ACCION_APLICAR), cat.H_REVERSION_FALLIDA)
        self.assertEqual(estados.resultado_a_fila(cat.R_APLAZADA, cat.ACCION_APLICAR), cat.H_APLAZADA)
        self.assertEqual(estados.resultado_a_fila(cat.R_RECHAZADA, cat.ACCION_APLICAR), cat.H_APLAZADA)
        self.assertEqual(estados.resultado_a_fila(cat.R_RECHAZADA, cat.ACCION_REVERTIR), cat.H_REVERSION_FALLIDA)


class VentanaTests(SimpleTestCase):
    def test_validar(self):
        v = ventana.validar(AHORA + cat.MINUTO_MS, AHORA + 31 * cat.MINUTO_MS, AHORA)
        self.assertEqual((v.desde, v.hasta), (AHORA + cat.MINUTO_MS, AHORA + 31 * cat.MINUTO_MS))
        ventana.validar(AHORA - 4 * cat.MINUTO_MS, AHORA + 30 * cat.MINUTO_MS, AHORA)                   # hasta cinco minutos en el pasado se tolera
        for desde, hasta in ((AHORA - 6 * cat.MINUTO_MS, AHORA + cat.DIA_MS), (AHORA, AHORA + 9 * cat.MINUTO_MS), (AHORA, AHORA + cat.DIA_MS + 1),
                             (AHORA + 91 * cat.DIA_MS, AHORA + 92 * cat.DIA_MS), (AHORA + 10, AHORA), ("1", 2), (True, AHORA + cat.DIA_MS), (1.5, 2.5)):
            with self.assertRaises(DatosInvalidos, msg=(desde, hasta)):
                ventana.validar(desde, hasta, AHORA)

    def test_decidir(self):
        v = ventana.Ventana(AHORA, AHORA + 30 * cat.MINUTO_MS)
        self.assertEqual(ventana.decidir(AHORA - 1, v, 0, None), (False, ventana.FUERA_DE_VENTANA))
        self.assertEqual(ventana.decidir(AHORA + 30 * cat.MINUTO_MS, v, 0, None), (False, ventana.FUERA_DE_VENTANA))
        self.assertEqual(ventana.decidir(AHORA, v, 1, None), (False, ventana.SESION_ACTIVA))
        self.assertEqual(ventana.decidir(AHORA, v, 0, AHORA + 10 * cat.MINUTO_MS), (False, ventana.CLASE_PROXIMA))
        self.assertEqual(ventana.decidir(AHORA, v, 0, AHORA + 15 * cat.MINUTO_MS), (True, ""))
        self.assertEqual(ventana.decidir(AHORA, v, 0, AHORA - 1), (True, ""))               # una clase que ya pasó no cuenta
        self.assertEqual(ventana.decidir(AHORA, v, 0, None), (True, ""))
        self.assertEqual(ventana.decidir(AHORA, None, 0, None), (False, ventana.SIN_VENTANA))
        self.assertTrue(v.abierta(AHORA) and not v.vencida(AHORA) and v.vencida(AHORA + 30 * cat.MINUTO_MS))


class OrdenTests(SimpleTestCase):
    def test_el_limite_de_reversion_es_3_min_con_evaluacion_y_5_en_general(self):
        m = manifiesto_de_ejemplo()
        self.assertEqual(orden.limite_minutos(m), 5)
        from actualizacion.dominio import manifiesto as mf
        con_eval = manifiesto_de_ejemplo(modulos=m.modulos + (mf.Modulo("evaluacion", "1.0.1", 2, 1, 3),))
        self.assertEqual(orden.limite_minutos(con_eval), 3)

    def test_armar_una_orden_de_aplicar_y_una_de_revertir(self):
        m = manifiesto_de_ejemplo()
        o = orden.armar(orden_id="o-1", accion=cat.ACCION_APLICAR, m=m, sha256="ab" * 32, bytes_paquete=1000, kid="upd-dev-1", ahora=AHORA, actor="admin", ventana=None)
        self.assertEqual((o["formato"], o["orden_id"], o["paquete_id"], o["accion"], o["limite_minutos"], o["pasos"]), (1, "o-1", m.paquete_id, "aplicar", 5, list(cat.PASOS)))
        self.assertEqual(o["modulos"][0]["migraciones"], [{"nombre": "0004_parche_de_ejemplo", "reverso": "0003_corte_cola_unica"}])
        self.assertEqual(o["carpetas"], {"staging": f"staging/{m.paquete_id}", "instantanea": f"versiones/{m.paquete_id}/anterior"})
        self.assertEqual(len(o["archivos"]), 2)
        r = orden.armar(orden_id="o-2", accion=cat.ACCION_REVERTIR, m=m, sha256="ab" * 32, bytes_paquete=1000, kid="upd-dev-1", ahora=AHORA, actor="admin", ventana={"desde": 1, "hasta": 2}, nota="falla el boletín")
        self.assertEqual((r["accion"], r["pasos"], r["ventana"], r["nota"]), ("revertir", list(cat.PASOS_REVERSION), {"desde": 1, "hasta": 2}, "falla el boletín"))
        with self.assertRaises(DatosInvalidos):
            orden.armar(orden_id="o", accion="borrar", m=m, sha256="", bytes_paquete=0, kid="", ahora=AHORA, actor="", ventana=None)

    def test_leer_resultado(self):
        bueno = {"formato": 1, "orden_id": "o-1", "paquete_id": "p", "accion": "aplicar", "resultado": "aplicado", "paso": "verificar", "iniciado_en": AHORA, "terminado_en": AHORA + 90_000,
                 "detalle": "ok", "respaldo": "C:\\x\\Respaldos\\2.12.0-x", "migraciones": [{"modulo": "reporting", "nombre": "0004_parche_de_ejemplo", "ok": True}], "error": None}
        r = orden.leer_resultado(bueno)
        self.assertEqual((r.resultado, r.exito, r.duracion_ms, r.paso, r.migraciones[0]["ok"], r.error), ("aplicado", True, 90_000, "verificar", True, None))
        self.assertEqual(r.como_dict()["respaldo"], True)                   # la carpeta del respaldo no sale: sólo si lo hubo
        for malo in ({}, {**bueno, "formato": 2}, {**bueno, "resultado": "casi"}, {**bueno, "accion": "x"}, {**bueno, "orden_id": ""}, {**bueno, "terminado_en": AHORA - 1},
                     {**bueno, "iniciado_en": "ayer"}, {**bueno, "migraciones": "no"}, [1]):
            with self.assertRaises(DatosInvalidos, msg=malo):
                orden.leer_resultado(malo)
        self.assertEqual(orden.leer_resultado({**bueno, "paso": "lo_que_sea", "resultado": "reversion_fallida", "error": "x" * 5000}).paso, "")
        self.assertEqual(len(orden.leer_resultado({**bueno, "error": "x" * 5000}).error), 2000)
