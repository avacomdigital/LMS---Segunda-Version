"""
Lo que la evaluación hace SOLA (D-15, INV-010, BR-051): el barrido del nodo persiste lo que el reloj ya provocó aunque nadie pregunte, un intento
defectuoso no frena al resto del aula y el programador es sólo un reloj con tolerancia a fallos.
"""
from __future__ import annotations

from unittest import mock

from .. import models as m
from ..aplicacion import barrido
from ..infraestructura import programador as prog
from ..infraestructura.contenedor import servicios
from .base import MIN, SEG, BaseEvaluacion, respuesta_correcta


def barrer() -> dict:
    return barrido.BarrerNodo(servicios()).ejecutar()


class BarridoTests(BaseEvaluacion):
    def test_un_nodo_sin_nada_que_hacer_no_hace_nada(self):
        self.assertEqual(barrer(), {"asignaciones": 0, "pausados": 0, "entregados": 0, "recalificados": 0, "errores": 0})

    def test_activa_lo_programado_cuando_llega_su_hora_aunque_nadie_pregunte(self):
        a = self.crear_asignacion("supervisado", abre_en=self.t + 10 * MIN, limite_en=self.t + 60 * MIN)
        self.assertEqual(a["estado"], "programada")
        self.avanzar(minutos=11)
        self.assertEqual(barrer()["asignaciones"], 1)
        self.assertEqual(m.Asignacion.objects.get(pk=a["id"]).estado, "activa")           # leído de la base, sin pasar por la API
        self.assertEqual(barrer()["asignaciones"], 0)                                      # idempotente

    def test_pausa_a_quien_dejo_de_dar_senal_una_sola_vez(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 40)
        self.avanzar(minutos=1)
        self.assertEqual(barrer()["pausados"], 1)
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.reloj_desde), ("pausado_desconexion", None))
        self.assertEqual(self.incidentes(i), ["desconexion"])
        self.assertEqual(self.eventos("evaluacion.intento_pausado.v1"), ["evaluacion.intento_pausado.v1"])
        self.assertEqual(barrer()["pausados"], 0)                                          # ya está pausado: no se repite nada
        self.assertEqual(self.incidentes(i), ["desconexion"])

    def test_entrega_a_quien_agoto_el_tiempo_y_lo_califica(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 300})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        self.latir_hasta(i, 280)
        self.avanzar(seg=20)
        self.assertEqual(barrer()["entregados"], 1)
        fila = self.fila(i)
        self.assertEqual((fila.origen_entrega, fila.consumido_ms), ("tiempo", 300 * SEG))
        self.assertIn(fila.estado, ("calificado", "en_revision_docente"))
        self.assertIn("tiempo_agotado", self.incidentes(i))

    def test_vence_el_plazo_endurecido_y_entrega_a_los_abiertos(self):
        a = self.crear_asignacion("supervisado", plazo="endurecido", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 280)
        self.avanzar(seg=20)
        self.assertEqual(barrer()["asignaciones"], 1)
        self.assertEqual((m.Asignacion.objects.get(pk=a["id"]).estado, self.fila(i).origen_entrega), ("cerrada", "plazo"))

    def test_marca_fuera_de_plazo_al_vencer_un_plazo_blando(self):
        a = self.crear_asignacion("supervisado", limite_en=self.t + 5 * MIN, tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 280)
        self.avanzar(seg=20)
        barrer()
        self.assertEqual((m.Asignacion.objects.get(pk=a["id"]).estado, self.fila(i).estado), ("activa_fuera_de_plazo", "en_curso_fuera_de_plazo"))

    def test_reintenta_las_calificaciones_que_la_biblioteca_no_pudo_hacer(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        cerradas = self.refs_cerradas(i)
        self.responder(i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        with self.biblioteca_caida():
            self.entregar(i, confirmar=True)
            self.assertEqual(barrer()["recalificados"], 0)                                 # sigue caída: no falla y no avanza
        self.assertTrue(self.fila(i).calificacion_pendiente)
        self.assertEqual(barrer()["recalificados"], 1)
        fila = self.fila(i)
        self.assertEqual((fila.calificacion_pendiente, fila.porcentaje is not None), (False, True))
        self.assertEqual(barrer()["recalificados"], 0)
        self.assertEqual(len(self.eventos("evaluacion.intento_calificado.v1", "evaluacion.revision.solicitada.v1")), 1)

    def test_un_intento_defectuoso_no_frena_al_resto_del_aula(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        ana, hw_ana = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        luis, hw_luis = self.alumno_con_tableta("Luis", "L-100", "supervisado")
        juan = self.abrir(a["id"])["intento"]["id"]
        i_ana = self.abrir(a["id"], hw=hw_ana, alumno_id=ana)["intento"]["id"]
        i_luis = self.abrir(a["id"], hw=hw_luis, alumno_id=luis)["intento"]["id"]
        self.avanzar(minutos=1)                                                            # los tres quedaron sin señal
        original = barrido.Motor.asegurar_intento

        def fallando(motor, uow, intento, asignacion, ahora):
            if intento["id"] == i_ana:
                raise RuntimeError("un caso raro")
            return original(motor, uow, intento, asignacion, ahora)

        with mock.patch.object(barrido.Motor, "asegurar_intento", fallando), self.assertLogs("avacom.evaluacion.programador", level="ERROR") as registro:
            resumen = barrer()
        self.assertEqual((resumen["pausados"], resumen["errores"]), (2, 1))
        self.assertIn(i_ana, registro.output[0])
        self.assertEqual({self.fila(juan).estado, self.fila(i_luis).estado}, {"pausado_desconexion"})
        self.assertEqual(self.fila(i_ana).estado, "en_curso")                              # el fallo no dejó nada a medias
        self.assertEqual(self.incidentes(i_ana), [])
        # la siguiente ronda, ya sin el fallo, lo pone al día
        self.assertEqual(barrer()["pausados"], 1)
        self.assertEqual(self.fila(i_ana).estado, "pausado_desconexion")


class ArchivadoTests(BaseEvaluacion):
    def test_cerrada_hace_mas_de_24_horas_se_archiva_y_no_antes(self):
        a = self.crear_asignacion("supervisado")
        self.accion(f"/asignaciones/{a['id']}/cerrar/")
        self.avanzar(minutos=23 * 60)
        self.assertEqual(barrido.ArchivarCerradas(servicios()).ejecutar(), 0)
        self.avanzar(minutos=60)
        self.assertEqual(barrido.ArchivarCerradas(servicios()).ejecutar(), 1)
        fila = m.Asignacion.objects.get(pk=a["id"])
        self.assertEqual((fila.estado, fila.archivada_en), ("archivada", self.t))
        self.assertEqual(barrido.ArchivarCerradas(servicios()).ejecutar(), 0)


class ProgramadorTests(BaseEvaluacion):
    def setUp(self):
        super().setUp()
        # dentro de una prueba (una transacción) cerrar la conexión la rompería: el programador real la cierra entre ticks
        for objetivo in ("close_old_connections", "connections"):
            parche = mock.patch.object(prog, objetivo)
            parche.start()
            self.addCleanup(parche.stop)

    def test_un_tick_aplica_el_barrido(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.avanzar(minutos=1)
        prog.Programador().tick()
        self.assertEqual(self.fila(i).estado, "pausado_desconexion")

    def test_un_tick_que_falla_se_registra_y_no_tumba_al_hilo(self):
        with mock.patch.object(barrido.BarrerNodo, "ejecutar", side_effect=RuntimeError("se cayó")), \
                self.assertLogs("avacom.evaluacion.programador", level="ERROR") as registro:
            prog.Programador().tick(archivar=True)                                         # no lanza
        self.assertIn("barrer intentos", registro.output[0])

    def test_un_tick_sin_novedades_no_ensucia_el_registro(self):
        with self.assertNoLogs("avacom.evaluacion.programador", level="INFO"):
            prog.Programador().tick(archivar=True)

    def test_un_tick_con_novedades_las_cuenta_en_el_registro(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        self.abrir(a["id"])
        self.avanzar(minutos=1)
        with self.assertLogs("avacom.evaluacion.programador", level="INFO") as registro:
            prog.Programador().tick()
        self.assertIn("pausados", registro.output[0])

    def test_al_arrancar_los_intentos_abiertos_quedan_restaurando_y_el_arranque_se_puede_apagar(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        hilo = prog.Programador(intervalo_s=0.01)
        hilo.detener()                                                                     # el bucle sale en cuanto termina el arranque
        with self.settings(AVACOM_EVAL_DETECTAR_REINICIO=False):
            hilo.run()
        self.assertEqual(self.fila(i).estado, "en_curso")
        hilo = prog.Programador(intervalo_s=0.01)
        hilo.detener()
        with self.settings(AVACOM_EVAL_DETECTAR_REINICIO=True):
            hilo.run()
        self.assertEqual(self.fila(i).estado, "restaurando")
        self.assertEqual(self.incidentes(i), ["reinicio_nodo"])

    def test_iniciar_respeta_el_interruptor_y_arranca_un_solo_hilo(self):
        with self.settings(AVACOM_EVAL_PROGRAMADOR=False):
            self.assertIsNone(prog.iniciar())
        previo = prog._instancia
        self.addCleanup(setattr, prog, "_instancia", previo)
        prog._instancia = None
        with self.settings(AVACOM_EVAL_PROGRAMADOR=True), mock.patch.object(prog.Programador, "start") as arrancar, \
                mock.patch.object(prog.Programador, "is_alive", return_value=True):
            primero = prog.iniciar()
            segundo = prog.iniciar()
        self.assertIs(primero, segundo)
        arrancar.assert_called_once()
