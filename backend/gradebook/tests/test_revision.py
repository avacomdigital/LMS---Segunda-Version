"""
FUN-120, FUN-121 · La revisión docente de lo que sólo un profesor puede calificar (TST-038): la puntuación manual de una respuesta abierta, la rúbrica sobre una
entrega y el dibujo, cada uno con puntuación y comentario pedagógico; la confirmación sólo cuando no queda nada pendiente; y el flujo de reabrir y recalificar.
La respuesta y la puntuación son de MOD-010; la rúbrica es de la biblioteca; el libro guarda la traza y la calificación resultante.
"""
from __future__ import annotations

from decimal import Decimal
from unittest import mock

from audit import models as maudit

from evaluacion.tests.base import respuesta_correcta

from .. import models as m
from ..dominio import resultado as res
from .base import GB, BaseGradebook


class _ConRevisionPendiente(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a, self.i, self.refs, self.tipos = self.examen_entregado(abiertas=True)
        self.abiertas = self.pendientes(self.i)
        self.puntos = self.puntos_de(self.i)
        self.sincronizar()

    def rev(self, ref: str, cuerpo: dict, esperado: int = 200, **extra) -> dict:
        return self.gb(f"/revisiones/{self.i}/respuestas/{ref}/", cuerpo, esperado=esperado, **extra)


class BandejaYDetalleTests(_ConRevisionPendiente):
    def test_la_bandeja_lista_lo_que_espera_al_profesor(self):
        b = self.leer("/revisiones/", grupo_id=self.grupo["id"])
        self.assertEqual((b["total"], b["pendientes"], b["reabiertas"]), (1, 1, 0))
        item = b["items"][0]
        self.assertEqual((item["intento_id"], item["asignacion_id"], item["alumno_id"], item["motivo"]), (self.i, self.a["id"], self.estudiante_id, "pendiente"))
        self.assertEqual((sorted(item["pendientes"]), item["n_pendientes"]), (sorted(self.abiertas), 2))
        self.assertEqual((item["grupo_id"], item["estado_intento"]), (self.grupo["id"], "en_revision_docente"))
        self.assertIsNotNone(item["porcentaje_provisional"])                                 # lo automático ya sumado, rotulado provisional
        self.assertEqual(self.leer("/revisiones/", asignacion_id=self.a["id"])["total"], 1)  # sin grupo, por asignación

    def test_el_detalle_trae_respuesta_rubrica_y_evidencias_de_cada_reactivo(self):
        d = self.leer(f"/revisiones/{self.i}/")
        self.assertEqual((d["intento"]["estado"], d["puede_confirmar"], sorted(d["intento"]["pendientes"])), ("en_revision_docente", False, sorted(self.abiertas)))
        por_ref = {f["pregunta_ref"]: f for f in d["filas"]}
        for ref in self.abiertas:
            fila = por_ref[ref]
            self.assertTrue(fila["requiere_revision"] and fila["pendiente"] and not fila["revisada"])
            self.assertEqual(fila["forma"], "abierta")
            self.assertEqual(fila["respuesta"], respuesta_correcta(ref))
            self.assertGreaterEqual(len(fila["rubrica"]["criterios"]), 2)                      # la rúbrica de la biblioteca, con sus puntos
            self.assertEqual(sum(c["puntos_max"] for c in fila["rubrica"]["criterios"]), fila["puntaje_maximo"])
            self.assertTrue(fila["rubrica"]["respuesta_modelo"])
        cerrada = next(r for r in self.refs if self.tipos[r] != "open")
        self.assertFalse(por_ref[cerrada]["requiere_revision"])
        self.assertIsNone(por_ref[cerrada]["rubrica"])

    def test_un_dibujo_se_reconoce_y_su_evidencia_es_una_referencia_a_mod_014(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        apertura = self.abrir(a["id"], alumno_id=self.estudiante_id)
        i = apertura["intento"]["id"]
        tipos = self.fila(i).armado_meta["tipos"]
        abiertas = [r for r in self.fila(i).armado if tipos[r] == "open"]
        self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(self.fila(i).armado) if tipos[ref] != "open"]
                       + [self.r(abiertas[0], 50, {"drawingRef": "mod14://dibujo/abc-123"}), self.r(abiertas[1], 51, {"text": "Porque sí."})])
        self.entregar(i, confirmar=True)
        d = self.leer(f"/revisiones/{i}/")
        por_ref = {f["pregunta_ref"]: f for f in d["filas"]}
        self.assertEqual((por_ref[abiertas[0]]["forma"], por_ref[abiertas[0]]["evidencias"]), ("dibujo", [{"tipo": "dibujo", "ref": "mod14://dibujo/abc-123"}]))
        self.assertEqual((por_ref[abiertas[1]]["forma"], por_ref[abiertas[1]]["evidencias"]), ("abierta", []))
        self.assertEqual(res.forma_de_revision("project", None), "proyecto")             # el contrato de la biblioteca aún no publica `project`; se reconoce por si llega

    def test_sin_sesion_el_prototipo_no_recorta_la_bandeja_a_quien_no_es_docente_de_un_grupo(self):
        """Q-34: el actor es una declaración. Un docente declarado ve los suyos; uno que no dice quién es (o no es docente de nada) ve todo, como en el resto del prototipo."""
        for actor in (self.docente_id, "alguien-que-no-es-docente", ""):
            r = self.api.get(f"{GB}/revisiones/", {"actor": actor} if actor else {})
            self.assertEqual((r.status_code, r.json()["total"]), (200, 1), actor)

    def test_el_alumno_y_el_tecnico_no_abren_la_bandeja(self):
        for cliente in (self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN), self.tecnico()):
            self.assertEqual(cliente.get(f"{GB}/revisiones/", {"grupo_id": self.grupo["id"]}).status_code, 403)
            self.assertEqual(cliente.get(f"{GB}/revisiones/{self.i}/").status_code, 403)


class PuntuacionTests(_ConRevisionPendiente):
    def test_tst_038_manual_y_por_rubrica_con_puntuacion_y_comentario(self):
        manual, por_rubrica = self.abiertas
        # FUN-120: una respuesta abierta, a mano, con su comentario pedagógico.
        r = self.rev(manual, {"puntaje": self.puntos[manual] - 1, "comentario": "Explica el cambio de estado, falta el ejemplo."})
        self.assertEqual((r["tipo"], r["puntaje"], r["pendientes"], r["listo_para_confirmar"]), ("manual", self.puntos[manual] - 1, [por_rubrica], False))
        # FUN-121: otra, aplicando la rúbrica de la biblioteca criterio por criterio.
        guia = next(f for f in self.leer(f"/revisiones/{self.i}/")["filas"] if f["pregunta_ref"] == por_rubrica)["rubrica"]["criterios"]
        criterios = [{"criterio_id": c["id"], "puntos": c["puntos_max"]} for c in guia]
        criterios[0]["puntos"] = 0
        r = self.rev(por_rubrica, {"criterios": criterios, "comentario": "Le falta mencionar el primer criterio."})
        total = sum(c["puntos"] for c in criterios)
        self.assertEqual((r["tipo"], r["puntaje"], r["pendientes"], r["listo_para_confirmar"]), ("rubrica", total, [], True))
        self.assertEqual([c["puntos"] for c in r["criterios"]], [c["puntos"] for c in criterios])
        # MOD-010 es el dueño: ahí quedó la puntuación y el comentario…
        respuestas = {x["pregunta_ref"]: x for x in self.fila(self.i).respuestas}
        self.assertEqual((respuestas[manual]["revision"]["puntaje"], respuestas[manual]["revision"]["comentario"]),
                         (self.puntos[manual] - 1, "Explica el cambio de estado, falta el ejemplo."))
        self.assertEqual(respuestas[por_rubrica]["revision"]["puntaje"], total)
        # …y el libro guarda la traza: el desglose por criterio, quién y cuándo.
        trazas = {t.pregunta_ref: t for t in m.Revision.objects.filter(intento_id=self.i)}
        self.assertEqual((trazas[manual].tipo, trazas[por_rubrica].tipo, trazas[manual].revisor_id), ("manual", "rubrica", self.docente_id))
        self.assertEqual([c["puntos"] for c in trazas[por_rubrica].criterios], [c["puntos"] for c in criterios])
        self.assertEqual(self.eventos_gb("calificacion.manual_aplicada.v1", "calificacion.rubrica_aplicada.v1"),
                         ["calificacion.manual_aplicada.v1", "calificacion.rubrica_aplicada.v1"])
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.manual_aplicada").exists())
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.rubrica_aplicada").exists())
        # La calificación todavía NO existe: falta confirmar la revisión.
        self.assertFalse(m.Calificacion.objects.exists())

    def test_confirmar_cierra_la_revision_y_registra_la_calificacion_del_profesor(self):
        r = self.revisar_todo(self.i)
        self.assertEqual((r["estado"], r["resultado"], r["registrada"]), ("calificado", "creada", True))
        cal = r["calificacion"]
        self.assertEqual((cal["origen"], cal["evaluador_id"], cal["regla_puntuacion"], cal["estado"]), ("docente", self.docente_id, "mod10.revision_docente.v1", "revisada"))
        self.assertEqual(cal["puntaje_efectivo"], float(Decimal(str(self.fila(self.i).porcentaje)).quantize(Decimal("0.01"))))
        self.assertEqual(self.fila(self.i).estado, "calificado")
        self.assertEqual(self.libro()["alumnos"][0]["celdas"][self.a["id"]]["estado"], "revisado")
        self.assertEqual(self.eventos_gb("calificacion.registrada.v1"), ["calificacion.registrada.v1"])
        self.assertEqual(self.leer("/revisiones/", grupo_id=self.grupo["id"])["total"], 0)

    def test_no_se_confirma_con_reactivos_sin_puntuar(self):
        self.rev(self.abiertas[0], {"puntaje": 1})
        r = self.gb(f"/revisiones/{self.i}/confirmar/", {}, esperado=409)
        self.assertEqual((r["codigo"], r["pendientes"]), ("reactivos_pendientes", [self.abiertas[1]]))
        self.assertFalse(m.Calificacion.objects.exists())
        self.assertEqual(self.fila(self.i).estado, "en_revision_docente")             # y MOD-010 no quedó a medias

    def test_la_rubrica_se_valida_contra_la_de_la_biblioteca(self):
        ref = self.abiertas[0]
        guia = next(f for f in self.leer(f"/revisiones/{self.i}/")["filas"] if f["pregunta_ref"] == ref)["rubrica"]["criterios"]
        completos = [{"criterio_id": c["id"], "puntos": 0} for c in guia]
        for cuerpo, texto in (
            ({"criterios": [{"criterio_id": "inventado", "puntos": 1}]}, "no existe en la rúbrica"),
            ({"criterios": completos[:-1]}, "Falta puntuar criterios"),
            ({"criterios": [{**completos[0], "puntos": guia[0]["puntos_max"] + 1}, *completos[1:]]}, "vale de 0 a"),
            ({"criterios": [{**completos[0], "puntos": 0.001}, *completos[1:]]}, "dos decimales"),
            ({"criterios": [{**completos[0], "puntos": -1}, *completos[1:]]}, "vale de 0 a"),
            ({"criterios": completos + [completos[0]]}, "repetido"),
            ({"criterios": completos, "puntaje": 1}, "no los dos"),
            ({"comentario": "sin nada"}, "Falta la puntuación"),
        ):
            r = self.rev(ref, cuerpo, esperado=400)
            self.assertEqual(r["codigo"], "datos_invalidos")
            self.assertIn(texto, r["detail"], cuerpo)
        self.assertFalse(m.Revision.objects.exists())                                 # nada se guardó

    def test_un_puntaje_fuera_de_rango_o_ilegible_se_rechaza(self):
        ref = self.abiertas[0]
        for malo in (self.puntos[ref] + 1, -1, "mucho", True):
            self.rev(ref, {"puntaje": malo}, esperado=400)
        self.assertEqual(self.rev(ref, {"puntaje": 0})["puntaje"], 0)                  # cero es una puntuación válida: sólo lo pendiente no es cero

    def test_sin_rubrica_en_la_biblioteca_la_manual_sigue_y_la_rubrica_pide_otra_cosa(self):
        ref = self.abiertas[0]
        with mock.patch("gradebook.infraestructura.guia.GuiaBiblioteca._crudo", side_effect=RuntimeError("biblioteca cerrada")):
            r = self.rev(ref, {"criterios": [{"criterio_id": "r1", "puntos": 1}]}, esperado=409)
            self.assertEqual(r["codigo"], "rubrica_no_disponible")
            self.assertTrue(all(f["rubrica"] is None for f in self.leer(f"/revisiones/{self.i}/")["filas"]))
            self.assertEqual(self.rev(ref, {"puntaje": 1})["tipo"], "manual")

    def test_reenviar_la_misma_solicitud_no_duplica_la_revision(self):
        ref = self.abiertas[0]
        primera = self.rev(ref, {"puntaje": 1, "comentario": "ok", "solicitud_id": "rev-0001"})
        repetida = self.rev(ref, {"puntaje": 1, "comentario": "ok", "solicitud_id": "rev-0001"})
        self.assertEqual((primera["reintento"], repetida["reintento"], repetida["numero"]), (False, True, 1))
        self.assertEqual(m.Revision.objects.count(), 1)
        self.assertEqual(self.eventos_gb("calificacion.manual_aplicada.v1"), ["calificacion.manual_aplicada.v1"])

    def test_cambiar_un_puntaje_ya_asentado_exige_motivo(self):
        ref = self.abiertas[0]
        self.rev(ref, {"puntaje": 1})
        r = self.rev(ref, {"puntaje": 2}, esperado=400)
        self.assertEqual(r["codigo"], "datos_invalidos")
        self.assertEqual(self.rev(ref, {"puntaje": 2, "motivo": "Revisé de nuevo el argumento"})["numero"], 2)
        self.assertEqual(self.fila(self.i).respuestas[self.fila(self.i).armado.index(ref)]["revision"]["puntaje"], 2)

    def test_una_pregunta_cerrada_no_se_puntua_a_mano(self):
        cerrada = next(r for r in self.refs if self.tipos[r] != "open")
        r = self.rev(cerrada, {"puntaje": 1}, esperado=400)
        self.assertIn("se califica solo", r["detail"])

    def test_el_alumno_no_puede_puntuar(self):
        cliente = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.rev(self.abiertas[0], {"puntaje": 1}, esperado=403, cliente=cliente)
        self.assertEqual(r["codigo"], "sin_permiso")
        self.assertFalse(m.Revision.objects.exists())


class ReabrirYRecalificarTests(_ConRevisionPendiente):
    def test_reabrir_recalificar_y_confirmar_conserva_el_original_y_deja_historial(self):
        cal = self.revisar_todo(self.i, fraccion=0.5)["calificacion"]
        original = cal["puntaje_original"]
        # Ya registrada: no se puntúa por la puerta de atrás.
        r = self.rev(self.abiertas[0], {"puntaje": 1, "motivo": "otra vez"}, esperado=409)
        self.assertEqual(r["codigo"], "transicion_invalida")
        # FUN-122: se reabre con motivo y queda en la bandeja como reabierta.
        reabierta = self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "El estudiante pidió revisar su argumento", "version_esperada": cal["version"]})
        self.assertEqual((reabierta["calificacion"]["estado"], reabierta["calificacion"]["version"]), ("reabierta", 2))
        bandeja = self.leer("/revisiones/", grupo_id=self.grupo["id"])
        self.assertEqual((bandeja["reabiertas"], bandeja["items"][0]["motivo"], bandeja["items"][0]["calificacion_id"]), (1, "reabierta", cal["id"]))
        self.assertTrue(self.leer(f"/revisiones/{self.i}/")["intento"]["reabierta"])
        self.assertEqual(self.libro()["alumnos"][0]["celdas"][self.a["id"]]["estado"], "reabierto")
        # Se recalifica (cambiar lo ya puntuado exige motivo) y se confirma.
        ref = self.abiertas[0]
        self.rev(ref, {"puntaje": self.puntos[ref], "comentario": "Tiene razón: sí lo explicó", "motivo": "Recalificación a petición del estudiante"})
        r = self.gb(f"/revisiones/{self.i}/confirmar/", {})
        self.assertEqual((r["resultado"], r["calificacion"]["estado"], r["calificacion"]["version"]), ("recalculada", "revisada", 3))
        nuevo = r["calificacion"]
        self.assertGreater(nuevo["puntaje_efectivo"], original)
        self.assertEqual(nuevo["puntaje_original"], original)                          # el original NO se sobrescribe
        self.assertFalse(nuevo["desfase_con_evaluacion"])
        tipos = [v["tipo"] for v in self.leer(f"/calificaciones/{cal['id']}/")["historial"]]
        self.assertEqual(tipos, ["registro", "reapertura", "recalculo"])
        self.assertEqual(self.eventos_gb("calificacion.intento_reabierto.v1"), ["calificacion.intento_reabierto.v1"])
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.reabierta", objeto_id=cal["id"]).exists())

    def test_reabrir_exige_motivo_version_y_permiso(self):
        cal = self.revisar_todo(self.i)["calificacion"]
        self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"version_esperada": cal["version"]}, esperado=400)
        self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "porque sí"}, esperado=400)
        self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "porque sí", "version_esperada": 99}, esperado=409)
        self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "porque sí", "version_esperada": cal["version"]}, esperado=403, cliente=self.admin)   # la administración no califica
        self.assertEqual(self.fila_cal(self.i).estado, "revisada")
