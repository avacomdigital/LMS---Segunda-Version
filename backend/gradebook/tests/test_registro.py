"""
FUN-119 · Registrar la calificación normalizada de un intento. Con un examen REAL de MOD-010 (por HTTP): el libro consume los eventos de la evaluación y registra la
calificación sólo cuando el intento está calificado del todo; nunca por un intento en curso ni con revisiones pendientes ni en un nivel de modo simple; y es idempotente.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from audit import models as maudit

from .. import models as m
from .base import GB, BaseGradebook


class RegistroTests(BaseGradebook):
    def test_un_intento_calificado_solo_se_registra_con_su_evaluador_y_su_regla(self):
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        self.assertEqual(self.fila(i).estado, "calificado")
        cal = self.calificacion(i)
        porcentaje = self.fila(i).porcentaje
        self.assertEqual(cal["puntaje_original"], cal["puntaje_efectivo"])
        self.assertEqual(Decimal(str(cal["puntaje_original"])), Decimal(str(round(porcentaje, 2))))       # la escala interna tiene dos decimales
        self.assertEqual((cal["origen"], cal["evaluador_id"], cal["regla_puntuacion"]), ("automatica", "sistema", "mod10.porcentaje.v1"))
        self.assertEqual((cal["estado"], cal["version"], cal["publicada"]), ("revisada", 1, False))
        self.assertEqual((cal["intento_id"], cal["asignacion_id"], cal["alumno_id"], cal["grupo_id"]), (i, a["id"], self.estudiante_id, self.grupo["id"]))
        self.assertEqual((cal["nivel_clave"], cal["periodo"], cal["numero_intento"]), ("secundaria", "2026", 1))
        self.assertEqual(self.eventos_gb("calificacion.registrada.v1"), ["calificacion.registrada.v1"])
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.registrada", objeto_id=cal["id"]).exists())

    def test_la_puntuacion_se_normaliza_a_dos_decimales_con_mitad_arriba(self):
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        crudo = self.fila(i).porcentaje
        self.assertNotEqual(crudo, round(crudo, 2))                                    # MOD-010 guarda cuatro decimales (71.4286…)
        cal = self.calificacion(i)
        self.assertEqual(cal["puntaje_efectivo"], float(Decimal(str(crudo)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))
        self.assertEqual(Decimal(str(cal["puntaje_efectivo"])).as_tuple().exponent, -2)

    def test_un_intento_en_curso_no_produce_una_calificacion_ni_un_cero(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.sincronizar()
        self.assertFalse(m.Calificacion.objects.exists())
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual((celda["estado_simple"], celda["estado"], celda["puntaje_efectivo"], celda["calificacion_id"]), ("en_progreso", "pendiente", None, None))
        self.assertEqual(self.fila(i).estado, "en_curso")

    def test_tst_un_intento_con_respuestas_por_revisar_no_es_definitivo(self):
        """No se calcula un intento como definitivo cuando quedan componentes obligatorios pendientes: provisional, nunca una calificación."""
        a, i, refs, tipos = self.examen_entregado(abiertas=True)
        self.assertEqual(self.fila(i).estado, "en_revision_docente")
        self.sincronizar()
        self.assertFalse(m.Calificacion.objects.exists())
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual((celda["estado_simple"], celda["estado"], celda["calificacion_id"], celda["puntaje_efectivo"]), ("completado", "provisional", None, None))
        r = self.gb(f"/intentos/{i}/registrar/", {}, esperado=409)                    # tampoco a mano
        self.assertEqual((r["codigo"], r["motivo"]), ("intento_no_calificable", "revision_pendiente"))

    def test_el_registro_es_idempotente_aunque_el_evento_se_reprocese(self):
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin)                # vuelve a leer TODOS los eventos desde cero
        self.sincronizar()
        self.assertEqual(m.Calificacion.objects.filter(intento_id=i).count(), 1)
        self.assertEqual(self.fila_cal(i).version, 1)
        self.assertEqual(m.VersionCalificacion.objects.filter(calificacion_id=cal["id"]).count(), 1)
        self.assertEqual(self.eventos_gb("calificacion.registrada.v1"), ["calificacion.registrada.v1"])
        r = self.gb(f"/intentos/{i}/registrar/", {})
        self.assertEqual((r["resultado"], r["calificacion"]["id"]), ("sin_cambios", cal["id"]))

    def test_el_evento_no_pisa_una_calificacion_ya_ajustada(self):
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        self.ajustar(cal, 90)
        self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin)
        self.assertEqual(self.fila_cal(i).puntaje_efectivo, Decimal("90.00"))
        self.assertEqual(self.fila_cal(i).puntaje_original, Decimal(str(cal["puntaje_original"])))
        self.assertNotEqual(self.fila_cal(i).puntaje_efectivo, self.fila_cal(i).puntaje_original)

    def test_en_modo_simple_completar_una_actividad_no_crea_un_registro_calificable(self):
        self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "simple"}, format="json")
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        self.assertEqual(self.fila(i).estado, "calificado")                            # MOD-010 conserva su puntuación técnica
        self.sincronizar()
        self.assertFalse(m.Calificacion.objects.exists())
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual((celda["estado_simple"], celda["estado"], celda["calificacion_id"]), ("completado", "sin_registro", None))
        r = self.gb(f"/intentos/{i}/registrar/", {}, esperado=409)
        self.assertEqual(r["codigo"], "modo_simple")

    def test_pasar_a_modo_calificaciones_no_convierte_solo_lo_que_se_califico_antes(self):
        self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "simple"}, format="json")
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        self.sincronizar()
        self.avanzar(seg=5)
        self.gb(f"/asignaciones/{a['id']}/", cliente=self.docente, metodo="get")
        self.accion(f"/asignaciones/{a['id']}/cerrar/", {"motivo": "fin"})                 # sin evaluaciones en curso: se puede cambiar el modo
        self.avanzar(seg=5)
        self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "calificaciones", "escala_id": self.adoptar("gen-0-10")["id"]}, format="json")
        self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin)       # incluso reproduciendo todo: lo anterior al cambio NO se registra
        self.assertFalse(m.Calificacion.objects.exists())
        r = self.gb(f"/intentos/{i}/registrar/", {})                                       # sí a petición explícita del profesor
        self.assertEqual(r["resultado"], "creada")

    def test_varios_intentos_cada_uno_su_calificacion_y_cuenta_el_que_dice_la_politica(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, intentos_permitidos=2)
        _, primero, refs, _ = self.examen_entregado(abiertas=False, bien=False, asignacion=a)
        _, segundo, refs, _ = self.examen_entregado(abiertas=False, bien=True, asignacion=a)
        self.sincronizar()
        c1, c2 = self.fila_cal(primero), self.fila_cal(segundo)
        self.assertEqual((c1.numero_intento, c2.numero_intento, c1.puntaje_efectivo, c2.puntaje_efectivo > 0), (1, 2, Decimal("0.00"), True))
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual((celda["politica_intentos"], celda["calificacion_id"], celda["intentos"]), ("ultimo", c2.id, {"total": 2, "registrados": 2}))
        # Con `mejor` y `primero` cuenta otro: la política es de la institución, no una suposición.
        self.gb("/politica/", {"politica_intentos": "primero"}, metodo="put", cliente=self.admin)
        self.assertEqual(self.libro()["alumnos"][0]["celdas"][a["id"]]["calificacion_id"], c1.id)
        self.gb("/politica/", {"politica_intentos": "mejor"}, metodo="put", cliente=self.admin)
        self.assertEqual(self.libro()["alumnos"][0]["celdas"][a["id"]]["calificacion_id"], c2.id)
        self.gb("/politica/", {"politica_intentos": "promedio"}, metodo="put", cliente=self.admin)
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual((celda["calificacion_id"], celda["puntaje_efectivo"]), (None, round((0 + float(c2.puntaje_efectivo)) / 2, 2)))

    def test_un_intento_anulado_deja_de_contar_sin_borrar_nada(self):
        a, i, refs, tipos = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        self.accion(f"/intentos/{i}/anular/", {"motivo": "Copió durante el examen"})
        self.sincronizar()
        fila = self.fila_cal(i)
        self.assertEqual((fila.estado, fila.puntaje_efectivo), ("anulada", Decimal(str(cal["puntaje_efectivo"]))))
        self.assertEqual(self.eventos_gb("calificacion.anulada.v1"), ["calificacion.anulada.v1"])
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual(celda["estado"], "anulado")
        self.assertEqual(self.leer(f"/calificaciones/{fila.id}/")["historial"][-1]["tipo"], "anulacion")
