"""
El estado SALE del tiempo y de los hechos (P-05, P-06, P-14, FUN-189/190/192/193/194, TST-060): ventana de evaluación al actualizar, reloj que retrocede o salta, respaldo viejo
restaurado, otro hardware, huella parcial y huella de instalación. El reloj y el hardware son los falsos de `base.py`; el nodo, la base, la bitácora y las anclas son los de verdad.
"""
from __future__ import annotations

import json

from audit.models import Bitacora
from licenciamiento import models as m
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio import huella as hu
from licenciamiento.dominio.politica import DIA_MS, HORA_MS

from . import emisor
from .base import CRUDOS_A, CRUDOS_B, L, BaseLicencia

TODAS = sorted(cat.CAPACIDADES_LICENCIABLES)


class EvaluacionAlActualizarTests(BaseLicencia):
    """P-14: un nodo que se actualiza sin licencia abre su ventana de evaluación DESDE LA ACTUALIZACIÓN: a nadie se le bloquea nada por actualizar."""

    def test_la_primera_evaluacion_abre_la_ventana_deja_asiento_evento_y_ancla(self):
        e = self.evaluar("arranque")
        self.assertEqual((e.estado.estado, e.estado.motivo, e.estado.dias_restantes), ("sin_licencia", "evaluacion", 30))
        self.assertEqual(sorted(e.estado.capacidades), TODAS)
        self.assertEqual(m.Instalacion.objects.get().instalada_en, self.t0)
        ancla = json.loads(self.s.almacen.leer(cat.ARCHIVO_ANCLA))
        self.assertEqual((ancla["instalada_en"], ancla["marca"]), (self.t0, self.t0))
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_EVALUACION).exists())
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_EVALUACION).count(), 1)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_VALIDADA).exists())        # FUN-189: validada al arrancar

    def test_repetir_la_evaluacion_no_repite_asientos_ni_eventos(self):
        self.evaluar("arranque")
        eventos, asientos = m.EventoSalida.objects.count(), Bitacora.objects.filter(modulo="licencia").count()
        for _ in range(4):
            self.evaluar("tick")
        self.assertEqual((m.EventoSalida.objects.count(), Bitacora.objects.filter(modulo="licencia").count()), (eventos, asientos))

    def test_un_ciclo_sin_novedades_no_abre_una_transaccion_de_escritura(self):
        """R-07: ni una sola escritura cuando no hay nada nuevo (sólo lecturas)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.reloj.t = (self.t0 // HORA_MS + 1) * HORA_MS + 10 * 60_000        # a las y diez de la hora siguiente: el ciclo de abajo cae en la misma hora
        self.evaluar("arranque")
        self.reloj.avanzar(2 * 60_000)                                         # dos minutos después: menos que el margen de la marca alta
        with CaptureQueriesContext(connection) as consultas:
            self.evaluar("tick")
        escrituras = [q["sql"] for q in consultas.captured_queries if q["sql"].split()[0].upper() in ("INSERT", "UPDATE", "DELETE", "SAVEPOINT", "RELEASE")]
        self.assertEqual(escrituras, [])

    def test_nadie_se_bloquea_por_actualizar_y_a_los_treinta_dias_se_degrada_sin_cortar_nada(self):
        self.evaluar("arranque")
        self.reloj.avanzar(29 * DIA_MS)
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.dias_restantes), ("sin_licencia", 1))
        self.assertEqual(self.docente.get("/api/acceso/yo/").status_code, 200)
        self.reloj.avanzar(2 * DIA_MS + HORA_MS)                               # pasó la ventana y las 24 h de histéresis
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.motivo), ("degradada", "evaluacion_vencida"))
        self.assertEqual(sorted(e.estado.capacidades), [])
        self.assertEqual(self.docente.get("/api/acceso/yo/").status_code, 200)                       # el núcleo sigue igual
        self.assertEqual(self.estado()["capacidades"]["no_disponibles"], TODAS)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_DEGRADADAS).exists())
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_DEGRADADA).count(), 1)

    def test_restaurar_una_base_vieja_no_reinicia_la_evaluacion(self):
        self.evaluar("arranque")
        self.reloj.avanzar(40 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "degradada")
        for modelo in (m.Instalacion, m.Observacion, m.EventoSalida, m.Consumo):          # «se restaura una base anterior»: no sabe nada de lo ocurrido
            modelo.objects.all().delete()
        m.MarcaAlta.objects.all().delete()
        e = self.evaluar("arranque")
        self.assertEqual((e.estado.estado, e.estado.motivo), ("degradada", "evaluacion_vencida"))
        self.assertEqual(m.Instalacion.objects.get().instalada_en, self.t0)                       # la ventana la recordó el ancla de afuera

    def test_un_ancla_alterada_no_cuenta_y_se_avisa_como_integridad_alterada(self):
        self.evaluar("arranque")
        self.s.almacen.escribir(cat.ARCHIVO_ANCLA, json.dumps({"marca": 1, "instalada_en": 1, "mac": "00" * 32}).encode())
        e = self.evaluar("tick")
        self.assertIn("integridad_alterada", e.estado.banderas)
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 1)
        self.assertEqual(e.estado.estado, "sin_licencia")                                            # sólo es una bandera: ninguna clase se detiene
        self.assertEqual(m.Instalacion.objects.get().instalada_en, self.t0)                          # una ancla alterada no puede acortar ni alargar la ventana


class RelojTests(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.activar_ok(vence=self.t0 + 30 * DIA_MS)                 # vence en 30 días, con 30 más de gracia
        self.evaluar("arranque")

    def test_retroceder_el_reloj_no_alarga_una_licencia_y_deja_rastro_una_sola_vez(self):
        self.reloj.avanzar(40 * DIA_MS)
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.dias_restantes), ("en_gracia", 20))
        self.reloj.saltar(-35 * DIA_MS)                                        # alguien pone la hora de hace 35 días
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.dias_restantes, e.estado.ahora), ("en_gracia", 20, self.t0 + 40 * DIA_MS))      # se mide contra la marca alta
        self.assertIn("reloj_sospechoso", e.estado.banderas)
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RELOJ).count(), 1)
        self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RELOJ).count(), 1)                    # un reloj torcido no llena la bitácora
        self.assertTrue(m.Observacion.objects.filter(tipo=cat.O_RETROCESO).exists())

    def test_retroceder_el_reloj_no_aplaza_la_degradacion(self):
        self.reloj.avanzar(61 * DIA_MS + 2 * HORA_MS)                                  # ya pasó la gracia y la histéresis
        self.assertEqual(self.evaluar("tick").estado.estado, "degradada")
        self.reloj.saltar(-50 * DIA_MS)                                        # y alguien devuelve la hora 50 días
        e = self.evaluar("tick")
        self.assertEqual(e.estado.estado, "degradada")
        self.assertIn("reloj_sospechoso", e.estado.banderas)

    def test_un_respaldo_viejo_restaurado_no_rebobina_el_vencimiento(self):
        self.reloj.avanzar(40 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "en_gracia")
        # «Se restaura una base de hace 40 días»: la tabla de licencias y la marca alta vuelven a como estaban, y hasta el reloj parece ir atrás.
        fila = m.Licencia.objects.get()
        for modelo in (m.Observacion, m.EventoSalida, m.Consumo):
            modelo.objects.all().delete()
        m.Licencia.objects.all().delete()
        m.MarcaAlta.objects.all().delete()
        m.MarcaAlta.objects.create(valor=self.t0, actualizada_en=self.t0)
        self.assertIsNotNone(fila.archivo)
        self.reloj.saltar(-39 * DIA_MS)
        e = self.evaluar("arranque")
        self.assertEqual((e.estado.estado, e.estado.dias_restantes), ("en_gracia", 20))             # NO «activa»: las anclas de afuera no se rebobinaron
        self.assertEqual(e.estado.ahora, self.t0 + 40 * DIA_MS)
        self.assertEqual([f.tipo for f in m.Licencia.objects.all()], ["reactivada"])                  # FUN-194: la reactivó el espejo de la carpeta de estado
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_REACTIVADA).count(), 1)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_REACTIVADA).exists())
        self.assertGreaterEqual(m.MarcaAlta.objects.get().valor, self.t0 + 40 * DIA_MS)

    def test_el_paso_normal_del_tiempo_no_es_un_salto(self):
        self.evaluar("tick")
        self.reloj.avanzar(10 * DIA_MS)
        e = self.evaluar("tick")
        self.assertNotIn("reloj_sospechoso", e.estado.banderas)
        self.assertFalse(m.Observacion.objects.filter(tipo=cat.O_SALTO).exists())

    def test_un_salto_hacia_adelante_no_degrada_a_nadie_avisa_y_espera_confirmacion(self):
        self.reloj.avanzar(59 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "en_gracia")
        self.reloj.saltar(10 * DIA_MS)                                         # alguien adelanta la hora diez días: ahora estaríamos 9 días después de la gracia
        e = self.evaluar("tick")
        self.assertEqual(e.estado.estado, "en_gracia")                         # NO degrada
        self.assertIn("reloj_sospechoso", e.estado.banderas)
        self.assertTrue(m.Observacion.objects.filter(tipo=cat.O_SALTO).exists())
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RELOJ).count(), 1)
        r = self.admin.post(f"{L}/reloj/confirmar/", {}, format="json")        # la administración confirma que hoy es la fecha correcta
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["estado"], "degradada")
        self.assertNotIn("reloj_sospechoso", r.json()["banderas"])
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RELOJ_CONFIRMADO).count(), 1)

    def test_una_sospecha_de_salto_no_aplaza_la_degradacion_para_siempre(self):
        self.reloj.avanzar(59 * DIA_MS)
        self.evaluar("tick")
        self.reloj.saltar(10 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "en_gracia")
        self.reloj.avanzar(73 * HORA_MS)                                       # sin confirmar: a las 72 h ya no es una palanca
        self.assertEqual(self.evaluar("tick").estado.estado, "degradada")


class HuellaTests(BaseLicencia):
    def test_tst_060_restaurar_en_hardware_distinto_deja_la_clase_operable_y_se_resuelve_sin_bloqueo(self):
        """TST-060: se instala en otro equipo y se restaura la base. La licencia es de OTRO hardware: gracia completa, la clase opera, y una licencia nueva para este equipo lo arregla."""
        self.activar_ok()
        self.huella.valores = dict(CRUDOS_B)                                                          # «el nodo nuevo»: el mismo disco clonado, otra placa
        e = self.evaluar("arranque")
        self.assertEqual((e.estado.estado, e.estado.motivo, e.estado.dias_restantes), ("en_gracia", "huella_distinta", 30))
        self.assertEqual(sorted(e.estado.capacidades), TODAS)                                        # todo habilitado: es gracia
        self.assertEqual(self.docente.get("/api/aula/sesiones/").status_code, 200)                    # la clase se puede iniciar y operar
        self.assertEqual(self.admin.get("/api/reportes/estado/").status_code, 200)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_GRACIA).exists())
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_GRACIA).count(), 1)
        self.assertTrue(m.Observacion.objects.filter(tipo=cat.O_HUELLA_INICIO).exists())
        # Pasa la gracia: degrada los módulos licenciables, JAMÁS la clase
        self.reloj.avanzar(31 * DIA_MS + 2 * HORA_MS)
        e = self.evaluar("tick")
        self.assertEqual((e.estado.estado, e.estado.motivo), ("degradada", "huella_distinta"))
        self.assertEqual(self.docente.get("/api/aula/sesiones/").status_code, 200)
        self.assertEqual(self.admin.get("/api/reportes/estado/").status_code, 402)
        # La solución: la solicitud de ESTE equipo → una licencia nueva (serie 2) para su hardware → activar
        solicitud = self.solicitud_del_nodo()
        nueva = self.licencia(serie=2, emitida=self.t0 + 31 * DIA_MS, huella=solicitud.huella)
        from licenciamiento.dominio import licencia as lic_mod
        r = self.admin.post(f"{L}/activar/", {"licencia": lic_mod.a_texto(emisor.emitir(nueva))}, format="json")
        # Es un TRASLADO (D-10): la serie siguiente de la misma licencia emitida para OTRA huella se activa (`license.activate`: lo hace el técnico); sólo con la misma huella es una renovación
        self.assertEqual((r.status_code, r.json()["accion"], r.json()["estado"]), (200, "activada", "activa"), r.content)
        self.assertEqual(self.admin.get("/api/reportes/estado/").status_code, 200)

    def test_cambiar_un_componente_sigue_activa_y_avisa_huella_parcial(self):
        self.activar_ok()
        self.huella.valores = {**CRUDOS_A, hu.F_PLACA: "BRD-NUEVA-0001"}
        e = self.evaluar("tick")
        self.assertEqual(e.estado.estado, "activa")
        self.assertIn("huella_parcial", e.estado.banderas)
        self.assertEqual(self.estado()["huella"], {"nivel": "hardware", "coincide": True, "parcial": True, "k": 3, "factores": 4, "coinciden": 3})

    def test_un_equipo_de_hardware_pobre_usa_la_huella_de_instalacion_y_activa_igual(self):
        self.huella.valores = {1: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", 2: "03000200-0400-0500-0006-000700080009", 3: "Default string", 4: "To be filled by O.E.M."}
        solicitud = self.solicitud_del_nodo()
        self.assertEqual(solicitud.nivel, "instalacion")
        r = self.activar(huella=solicitud.huella)
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "activa"), r.content)
        self.assertEqual(r.json()["huella"]["nivel"], "instalacion")


class ConsumoTests(BaseLicencia):
    def test_el_consumo_cuenta_equipos_sin_el_maestro_y_usuarios_sin_visitantes(self):
        self.registrar_equipo_master()
        r = self.admin.get(f"{L}/consumo/")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual(cuerpo["equipos"]["en_uso"], 1)                         # la tableta de BaseAcceso; el MASTER no cuenta
        self.assertEqual(cuerpo["usuarios"]["en_uso"], 3)                        # administración, docente y estudiante
        self.assertEqual(cuerpo["concurrentes"], {"normal": 50, "pico": 100})

    def test_con_licencia_el_consumo_se_mide_contra_sus_limites(self):
        self.activar_ok(limites=emisor.Limites(equipos=2, usuarios=4, concurrentes_normal=10, concurrentes_pico=20))
        cuerpo = self.admin.get(f"{L}/consumo/").json()
        self.assertEqual((cuerpo["equipos"]["limite"], cuerpo["equipos"]["porcentaje"], cuerpo["usuarios"]["limite"], cuerpo["usuarios"]["porcentaje"]), (2, 50, 4, 75))
        self.assertEqual(cuerpo["concurrentes"], {"normal": 10, "pico": 20})

    def test_el_conteo_se_guarda_una_vez_por_hora_con_su_evento(self):
        self.evaluar("arranque")
        self.assertEqual(m.Consumo.objects.get().usuarios, 3)
        eventos = m.EventoSalida.objects.filter(tipo_evento=cat.EV_CONSUMO).count()
        self.evaluar("tick")
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=cat.EV_CONSUMO).count(), eventos)
        self.reloj.avanzar(HORA_MS)
        self.evaluar("tick")
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=cat.EV_CONSUMO).count(), eventos + 1)

    def test_el_estado_en_la_api_trae_los_avisos_escalonados(self):
        self.activar_ok(vence=self.t0 + 12 * DIA_MS)
        cuerpo = self.estado()
        self.assertEqual([a for a in cuerpo["avisos"] if a["codigo"] == "por_vencer"], [{"codigo": "por_vencer", "dias": 12, "umbral": 14}])
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_AVISO).exists())
