"""
FUN-123 · Ajustar una calificación con motivo (TST-039), con las tres garantías del libro: el original nunca se sobrescribe (queda el historial), una escritura
que no trae la versión que leyó se rechaza (concurrencia optimista) y reenviar la misma solicitud no duplica el ajuste (idempotencia).
También: la valoración docente del nivel de desempeño y la retroalimentación pedagógica.
"""
from __future__ import annotations

from decimal import Decimal

from audit import models as maudit

from .. import models as m
from .base import GB, BaseGradebook


class _ConCalificacion(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a, self.i, self.refs, self.tipos = self.examen_entregado(abiertas=False)
        self.cal = self.calificacion(self.i)
        self.original = self.cal["puntaje_original"]


class AjusteTests(_ConCalificacion):
    def test_tst_039_de_70_a_85_con_motivo_conservando_lo_anterior(self):
        motivo = "Se reconoció una respuesta correcta que la rúbrica inicial no contemplaba"
        a70 = self.ajustar(self.cal, 70, motivo="Corrección por error de digitación en la hoja de respuestas")["calificacion"]
        self.assertEqual((a70["puntaje_efectivo"], a70["puntaje_original"], a70["ajustada"], a70["version"]), (70.0, self.original, True, 2))
        self.avanzar(seg=30)
        r = self.ajustar(a70, 85, motivo=motivo)
        cal = r["calificacion"]
        self.assertEqual((cal["puntaje_efectivo"], cal["puntaje_original"], cal["version"], cal["ajustada"]), (85.0, self.original, 3, True))
        # El historial conserva el valor anterior, el nuevo, el motivo, quién y cuándo según el reloj del NODO.
        ultimo = r["historial"][-1]
        self.assertEqual((ultimo["tipo"], ultimo["puntaje_anterior"], ultimo["puntaje_nuevo"], ultimo["motivo"], ultimo["actor_id"]), ("ajuste", 70.0, 85.0, motivo, self.docente_id))
        self.assertEqual(ultimo["en"], self.t)
        self.assertEqual([v["tipo"] for v in r["historial"]], ["registro", "ajuste", "ajuste"])
        self.assertEqual([v["puntaje_nuevo"] for v in r["historial"]], [self.original, 70.0, 85.0])
        fila = self.fila_cal(self.i)
        self.assertEqual((fila.puntaje_original, fila.puntaje_efectivo), (Decimal(str(self.original)), Decimal("85.00")))
        # La auditoría guarda el valor anterior y el nuevo con el motivo.
        asiento = maudit.Bitacora.objects.filter(accion="calificacion.modificada", objeto_id=cal["id"]).order_by("-secuencia").first()
        self.assertEqual(asiento.motivo, motivo)
        self.assertEqual((asiento.valor_anterior["puntaje_efectivo"], asiento.valor_nuevo["puntaje_efectivo"]), (70.0, 85.0))
        self.assertEqual(self.eventos_gb("calificacion.ajustada.v1"), ["calificacion.ajustada.v1"] * 2)
        self.assertEqual(self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]["puntaje_efectivo"], 85.0)

    def test_un_ajuste_sin_motivo_se_rechaza_y_no_cambia_nada(self):
        for motivo in ("", "  ", "ok", None):
            r = self.gb(f"/calificaciones/{self.cal['id']}/ajustar/", {"puntaje_nuevo": 85, "motivo": motivo, "version_esperada": self.cal["version"]}, esperado=400)
            self.assertEqual(r["codigo"], "datos_invalidos")
        r = self.gb(f"/calificaciones/{self.cal['id']}/ajustar/", {"puntaje_nuevo": 85, "version_esperada": self.cal["version"]}, esperado=400)
        self.assertIn("motivo", r["detail"])
        self.assertEqual((self.fila_cal(self.i).puntaje_efectivo, self.fila_cal(self.i).version), (Decimal(str(self.original)), 1))
        self.assertEqual(m.VersionCalificacion.objects.count(), 1)

    def test_la_puntuacion_va_de_0_a_100_con_dos_decimales(self):
        for malo in (-0.01, 100.01, 150, "abc", True, None, 85.125, "85,125"):
            r = self.ajustar(self.cal, malo, esperado=400)
            self.assertEqual(r["codigo"], "puntaje_invalido", malo)
        self.assertEqual(self.fila_cal(self.i).version, 1)
        cal = self.cal
        for bueno, esperado in ((0, 0.0), (100, 100.0), (85.25, 85.25), ("85,5", 85.5), ("70", 70.0)):                  # los extremos son válidos; la coma decimal también
            cal = self.ajustar(cal, bueno)["calificacion"]
            self.assertEqual(cal["puntaje_efectivo"], esperado)
        self.assertEqual(Decimal(str(cal["puntaje_efectivo"])).as_tuple().exponent, -1)

    def test_ajustar_al_mismo_valor_no_es_un_ajuste(self):
        r = self.ajustar(self.cal, self.original, esperado=400)
        self.assertIn("igual al vigente", r["detail"])

    def test_sin_la_version_que_leyo_no_hay_ajuste(self):
        r = self.gb(f"/calificaciones/{self.cal['id']}/ajustar/", {"puntaje_nuevo": 85, "motivo": "Por una razón de peso"}, esperado=400)
        self.assertIn("version_esperada", r["detail"])

    def test_dos_docentes_editando_a_la_vez_no_se_pisan(self):
        otro = self.segundo_docente()                                            # otro profesor del mismo grupo, con su propia sesión
        primero = self.ajustar(self.cal, 90, cliente=self.docente)["calificacion"]
        r = self.gb(f"/calificaciones/{self.cal['id']}/ajustar/", {"puntaje_nuevo": 60, "motivo": "Creía que seguía en la versión uno", "version_esperada": self.cal["version"]},
                    esperado=409, cliente=otro)
        self.assertEqual((r["codigo"], r["version_actual"], r["puntaje_efectivo"], r["version_esperada"]), ("conflicto_de_version", 2, 90.0, 1))
        self.assertEqual(self.fila_cal(self.i).puntaje_efectivo, Decimal("90.00"))                  # lo del primero sigue
        self.assertEqual(m.VersionCalificacion.objects.filter(calificacion_id=primero["id"], tipo="ajuste").count(), 1)
        # Con la versión nueva, el segundo sí puede.
        self.ajustar(primero, 60, cliente=otro)
        self.assertEqual(self.fila_cal(self.i).puntaje_efectivo, Decimal("60.00"))

    def test_el_cambio_compara_la_version_en_la_base_no_en_una_lectura_previa(self):
        """El compare-and-swap es UNA sentencia: dos escritores con la misma versión no pueden ganar los dos."""
        from ..infraestructura.repositorios import CalificacionesDjango
        repo = CalificacionesDjango()
        primero = repo.actualizar_si_version(self.cal["id"], 1, puntaje_efectivo=Decimal("10.00"))
        segundo = repo.actualizar_si_version(self.cal["id"], 1, puntaje_efectivo=Decimal("20.00"))
        self.assertEqual((primero["version"], segundo), (2, None))
        self.assertEqual(self.fila_cal(self.i).puntaje_efectivo, Decimal("10.00"))

    def test_reintentar_la_misma_solicitud_no_duplica_el_ajuste(self):
        r1 = self.ajustar(self.cal, 85, solicitud_id="sol-0001")
        r2 = self.ajustar(self.cal, 85, solicitud_id="sol-0001")            # el cliente perdió la señal y repite con la versión vieja
        self.assertEqual((r1["reintento"], r2["reintento"]), (False, True))
        self.assertEqual((r2["calificacion"]["version"], r2["calificacion"]["puntaje_efectivo"]), (2, 85.0))
        self.assertEqual(m.VersionCalificacion.objects.filter(tipo="ajuste").count(), 1)
        self.assertEqual(self.eventos_gb("calificacion.ajustada.v1"), ["calificacion.ajustada.v1"])
        self.assertEqual(maudit.Bitacora.objects.filter(accion="calificacion.modificada").count(), 1)
        # Una solicitud DISTINTA con la versión vieja sí es un conflicto, no un reintento.
        self.ajustar(self.cal, 60, solicitud_id="sol-0002", esperado=409)

    def test_una_calificacion_reabierta_o_anulada_no_se_ajusta(self):
        self.gb(f"/calificaciones/{self.cal['id']}/reabrir/", {"motivo": "Se revisará de nuevo", "version_esperada": 1})
        r = self.ajustar({**self.cal, "version": 2}, 85, esperado=409)
        self.assertEqual((r["codigo"], r["estado"]), ("transicion_invalida", "reabierta"))

    def test_otra_calificacion_o_inexistente(self):
        self.gb("/calificaciones/no-existe/ajustar/", {"puntaje_nuevo": 85, "motivo": "no existe", "version_esperada": 1}, esperado=404)


class ValoracionYRetroalimentacionTests(_ConCalificacion):
    def test_el_docente_valora_el_nivel_de_desempeno_sin_cambiar_el_resultado(self):
        self.admin.put(f"{GB}/niveles/secundaria/", {"modo": "calificaciones", "escala_id": self.adoptar("co-1-5")["id"]}, format="json")
        cal = self.leer(f"/calificaciones/{self.cal['id']}/")["calificacion"]
        self.assertEqual(cal["presentacion"]["desempeno"]["origen"], "calculo")
        r = self.gb(f"/calificaciones/{cal['id']}/valoracion/", {"tramo": "alto", "motivo": "Su proceso fue superior al de la prueba", "version_esperada": cal["version"]})
        nueva = r["calificacion"]
        self.assertEqual((nueva["desempeno_docente"], nueva["puntaje_efectivo"], nueva["version"]), ("alto", cal["puntaje_efectivo"], 2))
        self.assertEqual(nueva["presentacion"]["desempeno"], {"nivel": "Alto", "clave": "alto", "tramo": 3, "origen": "docente"})
        self.assertEqual(r["historial"][-1]["tipo"], "valoracion")
        self.assertEqual(self.eventos_gb("calificacion.valoracion_docente.v1"), ["calificacion.valoracion_docente.v1"])
        self.gb(f"/calificaciones/{cal['id']}/valoracion/", {"tramo": "inventado", "motivo": "No existe", "version_esperada": 2}, esperado=400)
        self.gb(f"/calificaciones/{cal['id']}/valoracion/", {"tramo": "bajo", "version_esperada": 2}, esperado=400)       # sin motivo
        quitada = self.gb(f"/calificaciones/{cal['id']}/valoracion/", {"tramo": "", "motivo": "Vuelve al cálculo", "version_esperada": 2})["calificacion"]
        self.assertEqual((quitada["desempeno_docente"], quitada["presentacion"]["desempeno"]["origen"]), ("", "calculo"))

    def test_la_retroalimentacion_pedagogica_no_toca_ninguna_cifra(self):
        r = self.gb(f"/calificaciones/{self.cal['id']}/retroalimentacion/", {
            "fortalezas": "Razona bien los cambios de estado.", "dificultades": "Se confunde al ordenar procesos.", "oportunidades": "Practicar con diagramas.",
            "adaptacion": "Tiempo adicional del 25 %", "version_esperada": 1})
        cal = r["calificacion"]
        self.assertEqual((cal["puntaje_efectivo"], cal["puntaje_original"], cal["version"]), (self.original, self.original, 2))
        self.assertEqual((cal["retroalimentacion"]["fortalezas"], cal["adaptacion"]), ("Razona bien los cambios de estado.", "Tiempo adicional del 25 %"))
        self.assertEqual(r["historial"][-1]["tipo"], "retroalimentacion")
        # No se pisa lo que no se manda.
        cal = self.gb(f"/calificaciones/{cal['id']}/retroalimentacion/", {"comentario": "Buen avance.", "version_esperada": 2})["calificacion"]
        self.assertEqual((cal["retroalimentacion"]["fortalezas"], cal["retroalimentacion"]["comentario"]), ("Razona bien los cambios de estado.", "Buen avance."))
        self.gb(f"/calificaciones/{cal['id']}/retroalimentacion/", {"version_esperada": 3}, esperado=400)
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.retroalimentada").exists())
