"""
La publicación controlada de calificaciones (extensión técnica propuesta sobre la regla de visibilidad del Documento Maestro): el profesor decide cuándo el alumno
las ve; antes de publicar sólo ve el estado de su entrega; publicar comprueba las precondiciones de MOD-010 y de la asignación; lo que se publica queda estampado con
la versión de la escala vigente, y un cambio posterior queda auditado.
"""
from __future__ import annotations

from audit import models as maudit

from .. import models as m
from .base import GB, BaseGradebook


def numeros(valor) -> list:
    """Todos los números (no booleanos) que aparecen en una estructura JSON."""
    if isinstance(valor, bool):
        return []
    if isinstance(valor, (int, float)):
        return [valor]
    if isinstance(valor, dict):
        return [n for v in valor.values() for n in numeros(v)]
    if isinstance(valor, list):
        return [n for v in valor for n in numeros(v)]
    return []


class _ConCalificacion(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a, self.i, self.refs, self.tipos = self.examen_entregado(abiertas=False)
        self.cal = self.calificacion(self.i)
        self.cliente_alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)

    def mias(self, cliente=None, esperado: int = 200, **params) -> dict:
        return self.leer("/mias/", esperado=esperado, cliente=cliente or self.cliente_alumno, **params)

    def item(self, cliente=None) -> dict:
        return next(x for x in self.mias(cliente)["items"] if x["asignacion_id"] == self.a["id"])

    def publicar(self, cal: dict | None = None, **extra) -> dict:
        cal = cal or self.cal
        return self.gb(f"/calificaciones/{cal['id']}/publicar/", {"version_esperada": cal["version"], **extra})


class VisibilidadTests(_ConCalificacion):
    def test_el_alumno_no_ve_la_nota_antes_de_que_se_publique_solo_el_estado_de_su_entrega(self):
        item = self.item()
        self.assertEqual((item["modo"], item["estado"], item["estado_simple"], item["calificacion"]), ("calificaciones", "resultado_no_publicado", "completado", None))
        self.assertEqual(numeros({k: v for k, v in item.items() if k not in ("asignacion_id",)}), [])          # ni una sola cifra
        self.assertNotIn(str(self.cal["puntaje_efectivo"]), str(item))
        # Lo mismo declarando al alumno sin sesión (Q-34).
        sin_sesion = self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)
        self.assertIsNone(sin_sesion["items"][0]["calificacion"])
        self.assertEqual(self.leer("/mias/", cliente=self.api, alumno_id="fantasma", esperado=403)["codigo"], "sin_permiso")
        self.assertEqual(self.leer("/mias/", cliente=self.api, esperado=400)["codigo"], "falta_alumno")

    def test_publicar_la_deja_definitiva_estampada_y_visible_sin_el_resultado_interno(self):
        self.avanzar(seg=10)
        r = self.publicar()
        cal = r["calificacion"]
        self.assertEqual((cal["estado"], cal["publicada"], cal["publicada_por"], cal["publicada_en"], cal["version"]), ("definitiva", True, self.docente_id, self.t, 2))
        self.assertEqual(cal["presentacion"]["escala"]["codigo"], "gen-0-100")
        self.assertFalse(cal["presentacion"]["provisional"])
        item = self.item()
        self.assertEqual((item["estado"], item["calificacion"]["presentada"]["valor"]), ("publicado", round(self.cal["puntaje_efectivo"])))
        self.assertEqual(item["calificacion"]["aprobacion"], {"cumple_criterio": None})                          # gen-0-100 no define criterio de aprobación
        self.assertNotIn("interno", item["calificacion"])
        self.assertNotIn("puntaje_efectivo", str(item))
        self.assertEqual(self.eventos_gb("calificacion.publicada.v1", "calificacion.escala_convertida.v1"),
                         ["calificacion.escala_convertida.v1", "calificacion.publicada.v1"])
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.publicada", objeto_id=cal["id"]).exists())
        self.assertEqual(self.libro()["alumnos"][0]["celdas"][self.a["id"]]["estado"], "definitivo")

    def test_otro_alumno_no_ve_la_nota_de_juan(self):
        self.publicar()
        ana_id, _hw = self.alumno_con_tableta("Ana", "300777")
        ana = self.leer("/mias/", cliente=self.api, alumno_id=ana_id)
        self.assertEqual([x for x in ana["items"] if x["asignacion_id"] == self.a["id"] and x["calificacion"]], [])

    def test_publicar_es_idempotente(self):
        primera = self.publicar(solicitud_id="pub-1")
        segunda = self.publicar(solicitud_id="pub-1")
        tercera = self.publicar()
        self.assertEqual((primera["reintento"], segunda["reintento"], tercera["reintento"]), (False, True, True))
        self.assertEqual(tercera["calificacion"]["version"], 2)
        self.assertEqual(self.eventos_gb("calificacion.publicada.v1"), ["calificacion.publicada.v1"])
        self.assertEqual(m.VersionCalificacion.objects.filter(tipo="publicacion").count(), 1)

    def test_no_se_publica_con_una_version_vieja(self):
        self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {"version_esperada": 7}, esperado=409)
        self.assertEqual(self.fila_cal(self.i).estado, "revisada")


class PrecondicionesTests(_ConCalificacion):
    def test_no_se_publica_si_la_evaluacion_no_muestra_resultados_a_los_alumnos(self):
        self.accion(f"/asignaciones/{self.a['id']}/publicacion/", {"resultados": "nunca"}, metodo="patch")
        r = self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {}, esperado=409)
        self.assertEqual(r["codigo"], "no_publicable")
        self.assertIn("«nunca»", r["motivos"][0])
        self.assertEqual(self.fila_cal(self.i).estado, "revisada")

    def test_no_se_publica_si_el_intento_se_anulo_en_la_evaluacion(self):
        self.accion(f"/intentos/{self.i}/anular/", {"motivo": "Se detectó una irregularidad"})
        self.sincronizar()                                                                    # el libro la marca anulada
        r = self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {}, esperado=409)
        self.assertEqual(r["codigo"], "no_publicable")
        self.assertEqual(self.fila_cal(self.i).estado, "anulada")

    def test_en_modo_simple_no_hay_nada_que_publicar(self):
        self.gb("/niveles/secundaria/", {"modo": "simple"}, metodo="put", cliente=self.admin, esperado=409)       # con la evaluación abierta no se alterna el modo
        self.accion(f"/asignaciones/{self.a['id']}/cerrar/", {"motivo": "fin"})
        self.gb("/niveles/secundaria/", {"modo": "simple"}, metodo="put", cliente=self.admin)
        r = self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {}, esperado=409)
        self.assertEqual(r["codigo"], "modo_simple")

    def test_una_calificacion_reabierta_o_anulada_no_se_publica(self):
        self.gb(f"/calificaciones/{self.cal['id']}/reabrir/", {"motivo": "Se revisará de nuevo", "version_esperada": 1})
        r = self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {}, esperado=409)
        self.assertEqual(r["codigo"], "no_publicable")
        self.assertIn("«reabierta»", r["motivos"][0])


class PublicarAsignacionTests(BaseGradebook):
    def test_publicar_toda_la_asignacion_omite_lo_que_no_cumple_sin_tumbar_lo_demas(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        _, juan, _, _ = self.examen_entregado(abiertas=False, asignacion=a)
        ana_id, hw_ana = self.alumno_con_tableta("Ana", "300778")
        _, ana, _, _ = self.examen_entregado(abiertas=False, asignacion=a, hw=hw_ana, alumno_id=ana_id)
        pedro_id, hw_pedro = self.alumno_con_tableta("Pedro", "300779")
        _, pedro, _, _ = self.examen_entregado(abiertas=True, asignacion=a, hw=hw_pedro, alumno_id=pedro_id)      # sigue en revisión
        self.sincronizar()
        self.assertEqual(m.Calificacion.objects.count(), 2)                                   # Pedro no tiene calificación: no es definitiva
        r = self.gb(f"/asignaciones/{a['id']}/publicar/", {})
        self.assertEqual((r["total_publicadas"], r["omitidas"], r["ya_publicadas"]), (2, [], 0))
        self.assertEqual({c.estado for c in m.Calificacion.objects.all()}, {"definitiva"})
        # Una segunda vez no repite nada.
        r = self.gb(f"/asignaciones/{a['id']}/publicar/", {})
        self.assertEqual((r["total_publicadas"], r["ya_publicadas"]), (0, 2))
        # A Pedro todavía no le llega: sigue en revisión (sólo el estado de su entrega).
        item = next(x for x in self.leer("/mias/", cliente=self.api, alumno_id=pedro_id)["items"] if x["asignacion_id"] == a["id"])
        self.assertEqual((item["estado"], item["calificacion"]), ("en_revision", None))

    def test_se_pueden_indicar_cuales_publicar(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        _, juan, _, _ = self.examen_entregado(abiertas=False, asignacion=a)
        ana_id, hw_ana = self.alumno_con_tableta("Ana", "300778")
        _, ana, _, _ = self.examen_entregado(abiertas=False, asignacion=a, hw=hw_ana, alumno_id=ana_id)
        self.sincronizar()
        r = self.gb(f"/asignaciones/{a['id']}/publicar/", {"calificacion_ids": [self.fila_cal(juan).id]})
        self.assertEqual([x["alumno_id"] for x in r["publicadas"]], [self.estudiante_id])
        self.assertEqual(self.fila_cal(ana).estado, "revisada")


class CambiosPosterioresTests(_ConCalificacion):
    def test_retirar_la_publicacion_exige_motivo_y_el_alumno_deja_de_verla(self):
        pub = self.publicar()["calificacion"]
        self.gb(f"/calificaciones/{pub['id']}/retirar-publicacion/", {"version_esperada": pub["version"]}, esperado=400)
        r = self.gb(f"/calificaciones/{pub['id']}/retirar-publicacion/", {"motivo": "Se publicó antes de revisar el acta", "version_esperada": pub["version"]})
        self.assertEqual((r["calificacion"]["estado"], r["calificacion"]["publicada"], r["historial"][-1]["tipo"]), ("revisada", False, "retiro_publicacion"))
        self.assertEqual((self.item()["estado"], self.item()["calificacion"]), ("resultado_no_publicado", None))
        self.assertEqual(self.eventos_gb("calificacion.publicacion_retirada.v1"), ["calificacion.publicacion_retirada.v1"])
        self.publicar(r["calificacion"])                                                      # y se puede volver a publicar
        self.assertEqual(self.item()["estado"], "publicado")

    def test_reabrir_una_publicada_retira_su_publicacion(self):
        pub = self.publicar()["calificacion"]
        self.gb(f"/calificaciones/{pub['id']}/reabrir/", {"motivo": "El estudiante presentó una objeción", "version_esperada": pub["version"]})
        self.assertEqual((self.item()["estado"], self.item()["calificacion"]), ("en_revision", None))
        self.assertEqual(self.leer(f"/calificaciones/{pub['id']}/")["historial"][-1]["tipo"], "reapertura")

    def test_un_ajuste_posterior_a_la_publicacion_queda_marcado_y_se_vuelve_a_presentar(self):
        pub = self.publicar()["calificacion"]
        r = self.ajustar(pub, 91.5, motivo="Error de transcripción detectado por la coordinación")
        cal = r["calificacion"]
        self.assertEqual((cal["estado"], cal["puntaje_efectivo"], cal["publicada"]), ("definitiva", 91.5, True))
        self.assertEqual(cal["presentacion"]["presentada"]["valor"], 92)                    # gen-0-100 redondea a 0 decimales: mitad arriba
        self.assertEqual(cal["presentacion"]["escala"]["version_id"], pub["presentacion"]["escala"]["version_id"])      # con la MISMA versión de escala
        self.assertTrue(r["historial"][-1]["tipo"] == "ajuste")
        asiento = maudit.Bitacora.objects.filter(accion="calificacion.modificada", objeto_id=cal["id"]).first()
        self.assertTrue(asiento.valor_nuevo["posterior_a_publicacion"])
        self.assertEqual(self.item()["calificacion"]["presentada"]["valor"], 92)
        self.assertEqual(self.eventos_gb("calificacion.ajustada.v1"), ["calificacion.ajustada.v1"])
        self.assertEqual(len(self.eventos_gb("calificacion.escala_convertida.v1")), 2)       # al publicar y al volver a presentar

    def test_una_escala_nueva_no_altera_lo_ya_publicado(self):
        """Los boletines ya expedidos se siguen leyendo con la versión de escala con la que se publicaron."""
        escala = self.adoptar("gen-0-10", codigo="escala-sec")
        self.admin.put(f"{GB}/niveles/secundaria/", {"modo": "calificaciones", "escala_id": escala["id"]}, format="json")
        pub = self.publicar(self.leer(f"/calificaciones/{self.cal['id']}/")["calificacion"])["calificacion"]
        antes = self.item()["calificacion"]["presentada"]
        self.assertEqual(antes["valor"], round(self.cal["puntaje_efectivo"] / 10, 1))
        v1 = pub["presentacion"]["escala"]["version_id"]
        # La institución publica otra versión de la MISMA escala (0–5) y se la asigna al nivel.
        nueva = self.gb(f"/escalas/{escala['id']}/versiones/", {"definicion": self._definicion_0_a_5(), "nota": "Acuerdo del consejo académico 2026-10"},
                        cliente=self.admin, esperado=201)
        v2 = nueva["versiones"][-1]
        self.assertEqual(v2["numero"], 2)
        self.admin.put(f"{GB}/niveles/secundaria/", {"modo": "calificaciones", "escala_version_id": v2["id"]}, format="json")
        despues = self.item()["calificacion"]
        self.assertEqual(despues["presentada"], antes)                                         # lo publicado no cambia
        self.assertEqual(self.fila_cal(self.i).escala_version_id, v1)
        # Una calificación nueva, sin publicar, ya se presenta con la versión vigente.
        a2, i2, _, _ = self.examen_entregado(abiertas=False, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        c2 = self.calificacion(i2)
        self.assertEqual(c2["presentacion"]["escala"]["version_id"], v2["id"])
        self.assertTrue(c2["presentacion"]["provisional"])
        self.assertEqual(c2["presentacion"]["presentada"]["valor"], round(c2["puntaje_efectivo"] / 20, 1))

    @staticmethod
    def _definicion_0_a_5() -> dict:
        return {"tipo": "numerica", "conversion": "interpolada", "decimales": 1, "redondeo": "mitad_arriba", "valor_min": "0", "valor_max": "5",
                "puntos": [["0", "0"], ["100", "5"]], "aprobacion_minima": None, "tramos": []}
