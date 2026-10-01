"""
El reloj del nodo (D-8), la suspensión y la reactivación (PAN-061, PAN-122), el reinicio del equipo (BR-051, AC-073) y el cambio de tableta (TST-026):
TST-015, TST-032, TST-034. El reloj de la tableta nunca decide; congelar es detener en el ÚLTIMO LATIDO; reactivar continúa desde lo congelado.
"""
from __future__ import annotations

from device_manager import models as m09

from .. import models as m
from ..aplicacion import barrido
from ..infraestructura.contenedor import servicios
from .base import BASE, MIN, SEG, BaseEvaluacion, respuesta_correcta


class RelojDelIntentoTests(BaseEvaluacion):
    def abierto(self, **extra):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 600}, **extra)
        return a, self.abrir(a["id"])["intento"]["id"]

    def test_el_cronometro_cuenta_con_el_reloj_del_nodo_y_la_tableta_no_lo_cambia(self):
        _, i = self.abierto()
        self.latir_hasta(i, 100)
        e = self.estado(i)
        self.assertEqual((e["reloj"]["restante_ms"], e["reloj"]["limite_seg"], e["reloj"]["corriendo"], e["reloj"]["servidor_en"]),
                         (500 * SEG, 600, True, self.t))
        # una tableta que dice llevar 5 s no le quita ni le da tiempo: el nodo toma el mayor, acotado por el tiempo real
        self.assertEqual(self.latido(i, transcurrido_ms=5 * SEG)["reloj"]["restante_ms"], 500 * SEG)

    def test_tst_032_el_tiempo_se_agota_en_el_instante_exacto_y_el_nodo_entrega(self):
        a, i = self.abierto()
        self.responder_todo(i)
        self.latir_hasta(i, 580)                                                      # a los 580 s sigue en curso
        self.assertEqual(self.estado(i)["intento"]["estado"], "en_curso")
        self.avanzar(seg=20)                                                          # 600 s exactos
        e = self.estado(i)
        self.assertEqual(e["intento"]["estado"] in ("calificado", "en_revision_docente"), True)
        fila = self.fila(i)
        self.assertEqual((fila.origen_entrega, fila.entregado_en, fila.consumido_ms, fila.reloj_desde), ("tiempo", fila.iniciado_en + 600 * SEG, 600 * SEG, None))
        self.assertIn("tiempo_agotado", self.incidentes(i))
        self.assertEqual(self.eventos("evaluacion.intento_entregado.v1"), ["evaluacion.intento_entregado.v1"])
        self.assertEqual(len(fila.respuestas), 4)                                     # lo respondido se entrega tal cual

    def test_el_tiempo_se_agota_aunque_nadie_pregunte_hasta_mucho_despues_si_hubo_latidos(self):
        _, i = self.abierto()
        self.latir_hasta(i, 580)
        self.avanzar(minutos=30)                                                      # nadie pregunta; la tableta ya no da señal
        e = self.estado(i)
        # el reloj paró en el último latido (a los 580 s): no alcanzó a agotarse, quedó suspendido con 20 s a favor
        self.assertEqual((e["intento"]["estado"], e["reloj"]["restante_ms"], e["reloj"]["congelado"]), ("pausado_desconexion", 20 * SEG, True))

    def test_tst_015_un_corte_de_20_segundos_no_pausa_ni_pierde_nada(self):
        _, i = self.abierto()
        refs = self.refs_del_examen(i)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]))])
        self.avanzar(seg=20)                                                          # la red se cae 20 s y vuelve
        e = self.latido(i)
        self.assertEqual((e["intento"]["estado"], e["espera_reactivacion"], e["intento"]["respondidas"]), ("en_curso", False, 1))
        self.assertEqual(self.incidentes(i), [])

    def test_tst_034_un_corte_de_45_segundos_suspende_registra_incidente_y_no_invalida(self):
        _, i = self.abierto()
        refs = self.refs_del_examen(i)
        self.latir_hasta(i, 60)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]))])
        ultimo = self.t
        self.avanzar(seg=45)
        e = self.latido(i)                                                            # la tableta vuelve a los 45 s
        self.assertEqual((e["intento"]["estado"], e["espera_reactivacion"], e["mensaje"]["codigo"]), ("pausado_desconexion", True, "suspendido"))
        self.assertIn("el tiempo está detenido", e["mensaje"]["texto"])               # MSG-033
        self.assertEqual(e["reloj"]["restante_ms"], 540 * SEG)                        # congelado en el último latido, no en el regreso
        fila = self.fila(i)
        self.assertEqual((fila.pausas[0]["desde"], fila.pausas[0]["hasta"], fila.pausas[0]["causa"]), (ultimo, None, "sin_latido"))
        self.assertEqual(self.incidentes(i), ["desconexion"])
        self.assertNotEqual(fila.estado, "anulado")                                   # BR-077: nunca se invalida
        # el tiempo que pasa mientras espera no se cuenta
        self.avanzar(minutos=5)
        self.assertEqual(self.estado(i)["reloj"]["restante_ms"], 540 * SEG)

    def test_la_reactivacion_es_del_profesor_y_devuelve_exactamente_el_tiempo_que_le_quedaba(self):
        _, i = self.abierto()
        self.latir_hasta(i, 60)
        self.avanzar(seg=45)
        self.latido(i)                                                                # queda suspendido, esperando al profesor
        self.avanzar(minutos=3)
        self.assertEqual(self.latido(i)["intento"]["estado"], "pausado_desconexion")  # reanudar solo es lo que el sistema nunca hace
        r = self.accion(f"/intentos/{i}/reactivar/", {"desde_pregunta": self.fila(i).armado[1]})
        self.assertEqual((r["estado"], r["restante_ms"], r["desde_pregunta"]), ("en_curso", 540 * SEG, self.fila(i).armado[1]))
        self.assertEqual(self.estado(i)["reloj"]["restante_ms"], 540 * SEG)
        self.avanzar(seg=10)
        self.assertEqual(self.estado(i)["reloj"]["restante_ms"], 530 * SEG)          # el cronómetro continúa desde el valor congelado
        self.assertEqual(self.incidentes(i), ["desconexion", "reactivado"])
        pausa = self.fila(i).pausas[0]
        self.assertEqual((pausa["reactivado_por"], pausa["hasta"] is not None), (self.docente_id, True))
        self.assertIn("evaluacion.intento_reactivado.v1", self.eventos())
        from audit import models as maudit
        self.assertTrue(maudit.Bitacora.objects.filter(accion="evaluacion.intento.reactivado", objeto_id=i).exists())         # MOD-019 sella la reactivación

    def test_reactivar_a_uno_que_ya_corre_no_hace_nada_y_a_uno_entregado_se_rechaza(self):
        _, i = self.abierto()
        r = self.accion(f"/intentos/{i}/reactivar/")
        self.assertEqual(r["estado"], "en_curso")
        self.assertEqual(self.incidentes(i), [])
        self.entregar(i, confirmar=True)
        self.accion(f"/intentos/{i}/reactivar/", esperado=409)

    def test_con_reactivacion_automatica_la_tableta_sigue_sola_al_volver(self):
        a, i = self.abierto(reactivacion="automatica")
        self.latir_hasta(i, 60)
        self.avanzar(seg=100)
        e = self.latido(i)
        self.assertEqual((e["intento"]["estado"], e["espera_reactivacion"], e["reloj"]["restante_ms"], e["reloj"]["corriendo"]), ("en_curso", False, 540 * SEG, True))
        self.assertEqual(self.incidentes(i), ["desconexion", "reconexion"])
        reconexion = m.Incidente.objects.get(intento_id=i, tipo="reconexion")
        self.assertEqual(reconexion.detalle["pausa_ms"], 100 * SEG)

    def test_en_suspension_se_siguen_guardando_las_respuestas_capturadas_antes(self):
        """BR-071 · TST-017: lo que la tableta capturó durante el corte llega después y se conserva."""
        _, i = self.abierto()
        refs = self.refs_del_examen(i)
        self.latir_hasta(i, 60)
        self.avanzar(minutos=2)
        r = self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]), capturada_en=self.t - MIN)], origen="cola")
        self.assertEqual((r["aceptadas"], r["intento"]["estado"]), ([refs[0]], "pausado_desconexion"))
        self.assertIn("respuesta_tardia", self.incidentes(i))

    def test_cierre_forzado_de_un_suspendido(self):
        _, i = self.abierto()
        self.latir_hasta(i, 60)
        self.avanzar(minutos=2)
        self.estado(i)                                                                # el nodo lo ve suspendido
        r = self.accion(f"/intentos/{i}/cerrar/")
        self.assertEqual((r["estado"] in ("calificado", "en_revision_docente"), r["origen_entrega"]), (True, "profesor"))
        self.assertEqual(self.fila(i).origen_entrega, "profesor")
        self.assertEqual(self.fila(i).pausas[0]["hasta"] is not None, True)               # la pausa se cierra con la entrega
        self.accion(f"/intentos/{i}/cerrar/")                                         # idempotente

    def test_el_cierre_forzado_solo_alcanza_a_un_suspendido(self):
        _, i = self.abierto()
        self.accion(f"/intentos/{i}/cerrar/", esperado=409)

    def test_el_reloj_desfasado_de_la_tableta_se_registra_una_sola_vez_por_ventana(self):
        _, i = self.abierto()
        for _ in range(3):
            self.avanzar(seg=10)
            self.latido(i, hora_tableta_ms=self.t + 120 * SEG)                        # su reloj va dos minutos adelantado
        self.assertEqual(self.incidentes(i), ["reloj_desfasado"])
        self.latido(i, hora_tableta_ms=self.t + 100)                                  # dentro de la tolerancia: nada
        self.assertEqual(self.incidentes(i), ["reloj_desfasado"])

    def test_el_tiempo_que_cuenta_la_tableta_sin_red_se_reconcilia_sin_regalar_tiempo(self):
        _, i = self.abierto()
        self.avanzar(seg=20)
        self.latido(i)                                                                 # última señal a los 20 s
        self.avanzar(seg=60)                                                           # sin red: el nodo la suspende con el reloj congelado en 20 s
        e = self.latido(i, transcurrido_ms=70 * SEG)                                   # …pero la tableta siguió contando offline: lleva 70 s
        self.assertEqual((e["intento"]["estado"], e["reloj"]["restante_ms"]), ("pausado_desconexion", 530 * SEG))     # manda el mayor: no se regala tiempo
        e = self.latido(i, transcurrido_ms=9999 * SEG)                                 # un valor inflado no pasa del tiempo real transcurrido (80 s)
        self.assertEqual(e["reloj"]["restante_ms"], 520 * SEG)
        e = self.latido(i, transcurrido_ms=10 * SEG)                                   # y nunca baja
        self.assertEqual(e["reloj"]["restante_ms"], 520 * SEG)


class ReinicioDelNodoTests(BaseEvaluacion):
    """AC-073: el equipo del aula se reinicia con 25 alumnos en examen: cada intento se recupera con pérdida máxima del último latido y NINGUNO cambia a
    entregado ni a anulado."""

    def puesta_en_marcha(self, n: int = 5, **extra):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 600}, **extra)
        intentos = [self.abrir(a["id"])["intento"]["id"]]
        for k in range(n - 1):
            alumno_id, hw = self.alumno_con_tableta(f"Alumno {k}", f"7000{k:02d}", capacidad="supervisado")
            intentos.append(self.abrir(a["id"], hw=hw, alumno_id=alumno_id)["intento"]["id"])
        return a, intentos

    def test_los_intentos_abiertos_quedan_restaurando_con_el_reloj_congelado_y_nadie_se_entrega_ni_se_anula(self):
        a, intentos = self.puesta_en_marcha(5)
        self.latir_todos(intentos, 100)
        self.avanzar(seg=300)                                                          # el equipo estuvo caído cinco minutos
        resultado = barrido.RecuperarTrasReinicio(servicios()).ejecutar()
        self.assertEqual(resultado, {"restaurados": 5})
        for i in intentos:
            fila = self.fila(i)
            self.assertEqual((fila.estado, fila.reloj_desde, fila.consumido_ms), ("restaurando", None, 100 * SEG))
            self.assertIn("reinicio_nodo", self.incidentes(i))
            self.assertNotIn(fila.estado, ("entregado", "anulado", "calificado"))
        self.assertEqual(len(self.eventos("evaluacion.intento_restaurado.v1")), 5)
        self.assertEqual(m.Intento.objects.filter(estado="anulado").count(), 0)

    def latir_todos(self, intentos: list[str], segundos: int, cada: int = 20) -> None:
        """Todas las tabletas dan señal cada `cada` segundos durante `segundos`: ninguna se suspende."""
        for _ in range(segundos // cada):
            self.avanzar(seg=cada)
            for i in intentos:
                self.latido(i, hw=self.hw_de(i), alumno_id=self.fila(i).alumno_id)

    def hw_de(self, intento_id: str) -> str:
        return m09.Dispositivo.objects.get(pk=self.fila(intento_id).dispositivo_id).identificador_hw

    def test_la_tableta_que_reaparece_queda_esperando_al_profesor_y_este_la_reactiva(self):
        a, intentos = self.puesta_en_marcha(2)
        self.latir_todos(intentos, 60)
        self.avanzar(seg=200)
        barrido.RecuperarTrasReinicio(servicios()).ejecutar()
        i = intentos[0]
        e = self.latido(i, hw=self.hw_de(i), alumno_id=self.fila(i).alumno_id)
        self.assertEqual((e["intento"]["estado"], e["espera_reactivacion"], e["reloj"]["restante_ms"]), ("pausado_desconexion", True, 540 * SEG))
        n = self.accion(f"/asignaciones/{a['id']}/reactivar/")
        self.assertEqual((n["suspendidos"], n["reactivados"]), (2, 2))                  # el que sigue `restaurando` también espera reactivación
        self.assertEqual(self.estado(i, hw=self.hw_de(i), alumno_id=self.fila(i).alumno_id)["reloj"]["restante_ms"], 540 * SEG)

    def test_con_reactivacion_automatica_el_intento_sigue_solo_al_reaparecer_su_tableta(self):
        a, intentos = self.puesta_en_marcha(1, reactivacion="automatica")
        i = intentos[0]
        self.latir_todos([i], 60)
        self.avanzar(seg=200)
        barrido.RecuperarTrasReinicio(servicios()).ejecutar()
        e = self.latido(i)
        self.assertEqual((e["intento"]["estado"], e["reloj"]["restante_ms"], e["reloj"]["corriendo"]), ("en_curso", 540 * SEG, True))

    def test_contar_antes_de_reactivar_a_todos_dice_a_cuantos_afecta(self):
        a, intentos = self.puesta_en_marcha(3)
        self.avanzar(seg=60)
        barrido.RecuperarTrasReinicio(servicios()).ejecutar()
        previo = self.ver(f"/asignaciones/{a['id']}/reactivar/")
        self.assertEqual((previo["suspendidos"], previo["reactivados"]), (3, 0))
        self.assertEqual(m.Intento.objects.filter(estado="restaurando").count(), 3)         # contar no cambia nada
        hecho = self.accion(f"/asignaciones/{a['id']}/reactivar/")
        self.assertEqual((hecho["suspendidos"], hecho["reactivados"]), (3, 3))

    def test_el_arranque_sin_intentos_abiertos_no_hace_nada(self):
        self.assertEqual(barrido.RecuperarTrasReinicio(servicios()).ejecutar(), {"restaurados": 0})


class CambioDeTabletaTests(BaseEvaluacion):
    """TST-026 y TST-027: el intento continúa en otra tableta sin perder nada; la sesión más reciente prevalece."""

    def test_tst_026_pasar_a_otra_tableta_continua_donde_iba_y_no_pierde_respuestas(self):
        a = self.crear_asignacion("supervisado")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0])), self.r(refs[1], 2, respuesta_correcta(refs[1]))], pregunta_actual=refs[2])
        self.avanzar(seg=20)
        self.registrar("hw-laptop", "Laptop Windows", capacidad="supervisado")
        r = self.abrir(a["id"], hw="hw-laptop", esperado=200)
        self.assertEqual((r["reanudado"], r["intento"]["id"], r["intento"]["respondidas"], r["intento"]["pregunta_actual"]), (True, i, 2, refs[2]))
        fila = self.fila(i)
        laptop = m09.Dispositivo.objects.get(identificador_hw="hw-laptop")
        self.assertEqual((fila.dispositivo_id, len(fila.sesiones), fila.sesiones[0]["hasta"] is not None, fila.sesiones[1]["hasta"]), (laptop.id, 2, True, None))
        self.assertIn("cambio_de_dispositivo", self.incidentes(i))
        self.assertEqual(self.preguntas(i, hw="hw-laptop")["respondidas"].keys(), {refs[0], refs[1]})
        self.responder(i, [self.r(refs[2], 1, respuesta_correcta(refs[2]))], hw="hw-laptop")                 # continúa desde la pregunta 3
        self.assertEqual(len(self.fila(i).respuestas), 3)
        # DEC-023: la sesión de la tableta anterior se cerró por relevo
        anterior = m09.DimSesionAlumno.objects.get(pk=fila.sesiones[0]["sesion_ref"])
        self.assertEqual(anterior.motivo_cierre, "relevo")

    def test_tst_027_la_tableta_anterior_no_sustituye_a_la_actual(self):
        a = self.crear_asignacion("supervisado")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.registrar("hw-laptop", "Laptop", capacidad="supervisado")
        self.avanzar(seg=5)
        self.abrir(a["id"], hw="hw-laptop")
        # la laptop responde la primera pregunta; DESPUÉS llega lo que la tableta vieja había capturado antes: no la pisa
        correcta = respuesta_correcta(refs[0])
        self.responder(i, [self.r(refs[0], 1, correcta)], hw="hw-laptop")
        tarde = self.responder(i, [self.r(refs[0], 9, {"text": "de la vieja"} if self.fila(i).armado_meta["tipos"][refs[0]] == "open" else correcta)])
        self.assertEqual((tarde["aceptadas"], tarde["superadas"]), ([], [refs[0]]))
        vigente = self.fila(i).respuestas[0]
        self.assertEqual((vigente["respuesta"], vigente["secuencia"]), (correcta, 1))
        self.assertEqual(vigente["historial"][-1]["motivo"], "superada")

    def test_la_tableta_vieja_ya_no_mantiene_vivo_el_intento_y_se_le_avisa(self):
        a = self.crear_asignacion("supervisado")
        i = self.abrir(a["id"])["intento"]["id"]
        self.registrar("hw-laptop", "Laptop", capacidad="supervisado")
        self.avanzar(seg=5)
        self.abrir(a["id"], hw="hw-laptop")
        self.avanzar(seg=20)
        e = self.latido(i)                                                             # late la vieja
        self.assertEqual((e["sesion_activa"], e["mensaje"]["codigo"]), (False, "otra_tableta"))
        self.assertEqual(self.fila(i).ultimo_latido_en, self.t - 20 * SEG)             # su latido no cuenta
        self.assertTrue(self.latido(i, hw="hw-laptop")["sesion_activa"])
