"""
Lo que encontró la revisión independiente del backend de MOD-011 (2026-10-14), una prueba por defecto corregido. Cada caso reproduce lo que se vio y fija el
comportamiento nuevo; los que no se corrigieron (porque son decisiones de diseño) están explicados en `spec-driven/12-gradebook/01-diseno.md` (§8, D-17 en adelante).

  A1 · M2   publicar, leer y reclasificar lo asignado a alumnos sueltos (sin grupo) no se salta el alcance por grupo
  A3        cambiar sólo la escala de un nivel ya no deja sin registrar lo que MOD-010 calificó y el libro no había leído
  A4        un evento que no se pudo aplicar retiene la marca unos ciclos y, al dejarse atrás, queda en la bitácora
  M3        un intento vivo en una asignación a alumnos sueltos también impide cambiar el modo
  M4        números absurdos y formas inesperadas dan 400, nunca 500
  M5        repetir lo mismo no repite eventos, asientos ni versiones
  M6        reabrir y confirmar sin tocar nada no borra un ajuste
  M7        lo que ve el alumno es lo que cuenta en el libro
  M9        una `solicitud_id` no se reutiliza para otra operación
  B1 · B4 · B6   escalas con lo que la columna guarda, el rótulo de una persona ajena, puntos a mano con dos decimales
"""
from __future__ import annotations

from unittest import mock

from audit import models as maudit

from .. import models as m
from ..aplicacion.registro import Registrador
from ..dominio import catalogos as cat
from .base import GB, BaseGradebook


# ======================================================================================== A1 · M2 · alumnos sueltos

class AlcanceDeLoAsignadoASueltosTests(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.ruiz_id, self.ruiz, self.g9 = self.otro_docente()           # profesor de 9B: no enseña a Juan (8A)
        a = self.crear_asignacion("supervisado", alcance="seleccion", destinatarios=[self.estudiante_id], grupo_id="")
        self.a, self.i, _, _ = self.examen_entregado(abiertas=False, asignacion=a)
        self.sincronizar()
        self.cal = m.Calificacion.objects.get(intento_id=self.i)

    def test_un_profesor_ajeno_no_publica_por_asignacion(self):
        r = self.gb(f"/asignaciones/{self.a['id']}/publicar/", {}, esperado=403, cliente=self.ruiz)
        self.assertEqual(r["codigo"], "fuera_de_alcance")
        self.cal.refresh_from_db()
        self.assertEqual((self.cal.estado, self.cal.publicada_por), ("revisada", ""))

    def test_un_profesor_ajeno_no_lee_ni_reclasifica_ni_revisa_esa_asignacion(self):
        self.leer(f"/asignaciones/{self.a['id']}/", esperado=403, cliente=self.ruiz)
        self.gb(f"/asignaciones/{self.a['id']}/clasificacion/", {"tipo_evaluacion": "diagnostica", "afecta_oficial": False}, esperado=403, cliente=self.ruiz, metodo="put")
        self.leer("/revisiones/", esperado=403, cliente=self.ruiz, asignacion_id=self.a["id"])
        self.leer(f"/calificaciones/{self.cal.id}/", esperado=403, cliente=self.ruiz)
        self.assertFalse(m.Clasificacion.objects.exists())

    def test_quien_la_asigno_y_quien_ensena_al_alumno_si_pueden(self):
        self.leer(f"/asignaciones/{self.a['id']}/")
        r = self.gb(f"/asignaciones/{self.a['id']}/publicar/", {})
        self.assertEqual((r["total_publicadas"], r["omitidas"]), (1, []))
        self.cal.refresh_from_db()
        self.assertEqual(self.cal.estado, "definitiva")

    def test_el_historial_de_un_alumno_con_un_grupo_ajeno_no_da_el_rotulo_de_cualquiera(self):
        r = self.leer(f"/estudiantes/{self.docente_id}/", esperado=404, cliente=self.ruiz, grupo_id=self.g9["id"])       # un profesor, no un alumno de 9B
        self.assertNotIn("rotulo", r)


class AsignacionMixtaTests(BaseGradebook):
    """Una evaluación a alumnos de dos grupos: cada profesor opera a los de SU grupo."""

    def setUp(self):
        super().setUp()
        self.ruiz_id, self.ruiz, self.g9 = self.otro_docente()
        self.ana_id, hw = self.alumno_con_tableta("Ana", "300901", capacidad="supervisado", grupo_id=self.g9["id"])
        a = self.crear_asignacion("supervisado", alcance="seleccion", destinatarios=[self.estudiante_id, self.ana_id], grupo_id="")
        _, self.i_juan, _, _ = self.examen_entregado(abiertas=False, asignacion=a)
        _, self.i_ana, _, _ = self.examen_entregado(abiertas=False, asignacion=a, hw=hw, alumno_id=self.ana_id)
        self.a = a
        self.sincronizar()

    def test_cada_profesor_publica_solo_a_sus_alumnos(self):
        r = self.gb(f"/asignaciones/{self.a['id']}/publicar/", {}, cliente=self.ruiz)
        self.assertEqual([p["alumno_id"] for p in r["publicadas"]], [self.ana_id])
        self.assertEqual([(o["alumno_id"], o["codigo"]) for o in r["omitidas"]], [(self.estudiante_id, "fuera_de_alcance")])
        self.assertEqual(m.Calificacion.objects.get(intento_id=self.i_juan).estado, "revisada")
        self.assertEqual(m.Calificacion.objects.get(intento_id=self.i_ana).estado, "definitiva")

    def test_cada_profesor_ve_solo_a_sus_alumnos_de_esa_asignacion(self):
        vista = self.leer(f"/asignaciones/{self.a['id']}/", cliente=self.ruiz)
        self.assertEqual([f["alumno_id"] for f in vista["alumnos"]], [self.ana_id])
        # quien la asignó (profesor de Juan) la ve entera
        self.assertEqual({f["alumno_id"] for f in self.leer(f"/asignaciones/{self.a['id']}/")["alumnos"]}, {self.estudiante_id, self.ana_id})

class AlumnoEnDosGruposTests(BaseGradebook):
    def test_la_calificacion_cae_siempre_en_el_grupo_de_quien_asigno(self):
        _, _, g9 = self.otro_docente()
        r = self.admin.post(f"/api/acceso/grupos/{g9['id']}/miembros/", {"usuario_id": self.estudiante_id, "papel": "ESTUDIANTE"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)                      # Juan está en 8A (de Gómez) y en 9B (de Ruiz)
        a = self.crear_asignacion("supervisado", alcance="seleccion", destinatarios=[self.estudiante_id], grupo_id="")
        _, i, _, _ = self.examen_entregado(abiertas=False, asignacion=a)
        self.sincronizar()
        self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin)
        self.assertEqual(m.Calificacion.objects.get(intento_id=i).grupo_id, self.grupo["id"])     # el de Gómez, que la asignó, y no uno al azar


class BandejaDeLoAsignadoASueltosTests(BaseGradebook):
    def test_la_bandeja_incluye_lo_asignado_a_alumnos_sueltos_y_solo_a_quien_corresponde(self):
        _, ruiz, _ = self.otro_docente()
        a = self.crear_asignacion("supervisado", alcance="seleccion", destinatarios=[self.estudiante_id], grupo_id="")
        _, i, _, _ = self.examen_entregado(abiertas=True, asignacion=a)
        self.sincronizar()
        self.assertEqual([x["intento_id"] for x in self.leer("/revisiones/")["items"]], [i])
        self.assertEqual(self.leer("/revisiones/", cliente=ruiz)["items"], [])


# ================================================================================================ A3 · cambio de escala

class CambioDeEscalaNoPierdeEventosTests(BaseGradebook):
    def test_cambiar_solo_la_escala_no_descarta_lo_que_el_libro_aun_no_leia(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)            # MOD-010 calificó; el libro todavía no lo leyó
        self.avanzar(seg=10)
        definicion = self.escala["versiones"][0]["definicion"]
        otra = {**definicion, "redondeo": "abajo" if definicion["redondeo"] != "abajo" else "arriba"}
        r = self.admin.post(f"{GB}/escalas/{self.escala['id']}/versiones/", {"definicion": otra, "nota": "v2"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        v2 = r.json()["versiones"][-1]["id"]
        r = self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "calificaciones", "escala_version_id": v2}, format="json")
        self.assertEqual((r.status_code, r.json()["cambiado"]), (200, True), r.content)
        self.sincronizar()
        self.assertEqual(m.Calificacion.objects.filter(intento_id=i).count(), 1)

    def test_el_modo_desde_se_mueve_al_cambiar_el_modo_y_no_al_cambiar_la_escala(self):
        """El guardia de D-2 (lo anterior al cambio de modo no se convierte solo) es el MODO, no la fila entera del nivel."""
        nivel = m.ConfigNivel.objects.get(pk=self.nivel)
        desde = nivel.modo_desde
        self.avanzar(seg=5)
        definicion = self.escala["versiones"][0]["definicion"]
        otra = {**definicion, "redondeo": "abajo" if definicion["redondeo"] != "abajo" else "arriba"}
        v2 = self.admin.post(f"{GB}/escalas/{self.escala['id']}/versiones/", {"definicion": otra}, format="json").json()["versiones"][-1]["id"]
        self.assertEqual(self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "calificaciones", "escala_version_id": v2}, format="json").status_code, 200)
        nivel.refresh_from_db()
        self.assertEqual(nivel.modo_desde, desde)
        self.assertGreater(nivel.actualizada_en, desde)
        self.avanzar(seg=5)
        self.assertEqual(self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "simple"}, format="json").status_code, 200)
        nivel.refresh_from_db()
        self.assertGreater(nivel.modo_desde, desde)


# ============================================================================================== A4 · eventos que fallan

class EventosQueFallanTests(BaseGradebook):
    @staticmethod
    def marca() -> m.MarcaConsumidor:
        return m.MarcaConsumidor.objects.get(consumidor=cat.CONSUMIDOR)

    def test_un_fallo_retiene_la_marca_y_el_ciclo_siguiente_lo_recupera(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        with mock.patch.object(Registrador, "registrar", side_effect=RuntimeError("fallo pasajero")):
            r = self.sincronizar()
        self.assertEqual(len(r["fallidos"]), 1)
        self.assertEqual(m.Calificacion.objects.count(), 0)
        marca = self.marca()
        self.assertEqual(marca.fallos_seguidos, 1)
        self.assertLess(marca.ultima_secuencia, marca.secuencia_fallida)           # la marca NO pasó de largo
        r = self.sincronizar()
        self.assertEqual(r["fallidos"], [])
        self.assertEqual(m.Calificacion.objects.filter(intento_id=i).count(), 1)    # se recuperó solo
        marca.refresh_from_db()
        self.assertEqual((marca.fallos_seguidos, marca.secuencia_fallida), (0, 0))
        self.assertFalse(maudit.Bitacora.objects.filter(accion="calificacion.evento_omitido").exists())

    def test_un_evento_que_nunca_se_puede_aplicar_se_deja_atras_con_su_asiento(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        with mock.patch.object(Registrador, "registrar", side_effect=RuntimeError("siempre falla")):
            for _ in range(cat.MAX_FALLOS_DE_EVENTO):
                self.sincronizar()
        asientos = maudit.Bitacora.objects.filter(accion="calificacion.evento_omitido")
        self.assertEqual(asientos.count(), 1)                                      # nunca se pierde en silencio
        self.assertEqual(self.marca().fallos_seguidos, 0)
        self.assertEqual(self.sincronizar()["leidos"], 0)                          # y la cola no quedó atascada
        # el libro sigue sin esa calificación, pero el profesor la puede registrar a mano
        self.assertEqual(self.gb(f"/intentos/{i}/registrar/", {})["resultado"], "creada")

    def test_un_lote_con_un_fallo_se_detiene_ahi(self):
        """Cada ciclo es UN reintento del evento que falló, no cinco seguidos que lo agoten en una sola consulta."""
        a, i, _, _ = self.examen_entregado(abiertas=False)
        with mock.patch.object(Registrador, "registrar", side_effect=RuntimeError("fallo")):
            self.leer("/libro/", grupo_id=self.grupo["id"])                        # la consulta pone el libro al día (un ciclo)
        self.assertEqual(self.marca().fallos_seguidos, 1)


# ================================================================================================ M3 · en curso a sueltos

class EnCursoASueltosBloqueaElModoTests(BaseGradebook):
    def test_un_intento_vivo_en_una_asignacion_a_alumnos_sueltos_bloquea_el_cambio_de_modo(self):
        a = self.crear_asignacion("supervisado", alcance="seleccion", destinatarios=[self.estudiante_id], grupo_id="", tiempo={"modo": "sin_limite"})
        self.abrir(a["id"])
        r = self.admin.put(f"{GB}/niveles/{self.nivel}/", {"modo": "simple"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "evaluaciones_en_curso"), r.content)
        self.assertEqual(m.ConfigNivel.objects.get(pk=self.nivel).modo, "calificaciones")


# ========================================================================================== M4 · entradas absurdas

class EntradasAbsurdasTests(BaseGradebook):
    def test_un_ajuste_con_numeros_enormes_o_formas_raras_da_400(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        for valor in ("1e999999", "-1e999999", "5e400", [0, [9, 9], 0], {"a": 1}):
            r = self.ajustar(cal, valor, esperado=400)
            self.assertEqual(r["codigo"], "puntaje_invalido", valor)
        self.assertEqual(self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]["puntaje_efectivo"], cal["puntaje_efectivo"])

    def test_puntuar_a_mano_con_decimales_de_mas_o_una_cifra_enorme_da_400(self):
        a, i, _, _ = self.examen_entregado(abiertas=True)
        self.sincronizar()
        ref = self.pendientes(i)[0]
        for valor in ("1e999999", "-1e999999", 2.125, "-1", 1e12, [1]):
            self.gb(f"/revisiones/{i}/respuestas/{ref}/", {"puntaje": valor}, esperado=400)
        self.assertFalse(m.Revision.objects.exists())

    def test_una_escala_con_formas_o_valores_que_no_caben_da_400(self):
        base = self.escala["versiones"][0]["definicion"]
        casos = {
            "puntos-no-es-lista": {**base, "puntos": 5},
            "tramos-no-es-lista": {**base, "tramos": 7},
            "valor-enorme": {**base, "valor_min": "0", "valor_max": "1000000", "puntos": [["0", "0"], ["100", "1000000"]], "aprobacion_minima": None},
            "aprobacion-con-tres-decimales": {**base, "valor_min": "0", "valor_max": "10", "puntos": [["0", "0"], ["100", "10"]], "aprobacion_minima": "6.005"},
        }
        for nombre, definicion in casos.items():
            r = self.admin.post(f"{GB}/escalas/", {"codigo": f"escala-mala-{nombre}", "nombre": nombre, "definicion": definicion}, format="json")
            self.assertEqual(r.status_code, 400, (nombre, r.content))
        self.assertEqual(m.Escala.objects.filter(codigo__startswith="escala-mala").count(), 0)

    def test_publicar_una_asignacion_con_ids_mal_formados_da_400(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        self.sincronizar()
        for cuerpo in ({"calificacion_ids": 5}, {"calificacion_ids": [{"a": 1}]}, {"calificacion_ids": "abc"}):
            self.gb(f"/asignaciones/{a['id']}/publicar/", cuerpo, esperado=400)


# =============================================================================================== M5 · idempotencia

class RepetirLoMismoTests(BaseGradebook):
    def test_repetir_la_politica_no_repite_evento_ni_asiento(self):
        r = self.gb("/politica/", {"politica_intentos": "mejor"}, metodo="put", cliente=self.admin)
        self.assertTrue(r["cambiado"])
        eventos, asientos = len(self.eventos_gb("calificacion.politica_configurada.v1")), maudit.Bitacora.objects.filter(accion="calificacion.politica_configurada").count()
        version = r["politica"]["version"]
        r = self.gb("/politica/", {"politica_intentos": "mejor"}, metodo="put", cliente=self.admin)
        self.assertFalse(r["cambiado"])
        self.assertEqual(r["politica"]["version"], version)
        self.assertEqual(len(self.eventos_gb("calificacion.politica_configurada.v1")), eventos)
        self.assertEqual(maudit.Bitacora.objects.filter(accion="calificacion.politica_configurada").count(), asientos)

    def test_repetir_la_clasificacion_no_repite_evento_ni_asiento(self):
        a = self.crear_asignacion("supervisado")
        cuerpo = {"tipo_evaluacion": "formativa", "afecta_oficial": False}
        self.assertTrue(self.gb(f"/asignaciones/{a['id']}/clasificacion/", cuerpo, metodo="put")["cambiado"])
        eventos = len(self.eventos_gb("calificacion.clasificacion_definida.v1"))
        r = self.gb(f"/asignaciones/{a['id']}/clasificacion/", cuerpo, metodo="put")
        self.assertFalse(r["cambiado"])
        self.assertEqual(len(self.eventos_gb("calificacion.clasificacion_definida.v1")), eventos)

    def test_la_misma_definicion_no_es_otra_version_de_la_escala(self):
        definicion = self.escala["versiones"][0]["definicion"]
        r = self.admin.post(f"{GB}/escalas/{self.escala['id']}/versiones/", {"definicion": definicion}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["reintento"])
        self.assertEqual(len(r.json()["versiones"]), 1)
        self.assertEqual(m.EscalaVersion.objects.filter(escala_id=self.escala["id"]).count(), 1)
        otra = {**definicion, "redondeo": "abajo" if definicion["redondeo"] != "abajo" else "arriba"}
        r = self.admin.post(f"{GB}/escalas/{self.escala['id']}/versiones/", {"definicion": otra}, format="json")
        self.assertEqual(len(r.json()["versiones"]), 2)                      # una definición distinta sí lo es

    def test_confirmar_dos_veces_la_revision_dice_que_ya_estaba_confirmada(self):
        """No acepta `solicitud_id` (no hace falta): el reintento recibe 409 `revision_no_pendiente` con el `calificacion_id`, que el cliente trata como «ya hecho»."""
        a, i, _, _ = self.examen_entregado(abiertas=True)
        self.sincronizar()
        primera = self.revisar_todo(i)
        r = self.gb(f"/revisiones/{i}/confirmar/", {"solicitud_id": "abc"}, esperado=409)
        self.assertEqual((r["codigo"], r["calificacion_id"]), ("revision_no_pendiente", primera["calificacion"]["id"]))


# ================================================================================================= M6 · reabrir y confirmar

class ReabrirYConfirmarConservaElAjusteTests(BaseGradebook):
    def test_reabrir_y_confirmar_sin_cambiar_nada_no_borra_el_ajuste(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        ajustada = self.ajustar(cal, 90)["calificacion"]
        self.assertTrue(ajustada["ajustada"])
        self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "revisar de nuevo", "version_esperada": ajustada["version"]})
        c = self.gb(f"/revisiones/{i}/confirmar/", {})
        self.assertEqual((c["calificacion"]["puntaje_efectivo"], c["calificacion"]["ajustada"], c["ajuste_descartado"], c["ajuste_anterior"]), (90, True, False, None))
        recalculo = m.VersionCalificacion.objects.filter(tipo="recalculo").order_by("numero").last()
        self.assertEqual((recalculo.datos["ajuste_conservado"], recalculo.datos["ajuste_descartado"]), (True, False))

    def test_si_recalificar_cambia_la_puntuacion_el_ajuste_se_descarta_y_se_dice(self):
        a, i, _, _ = self.examen_entregado(abiertas=True)
        self.sincronizar()
        puntos, ref = self.puntos_de(i), self.pendientes(i)[0]
        cal = self.revisar_todo(i, fraccion=0.5)["calificacion"]
        ajustada = self.ajustar(cal, 99)["calificacion"]
        self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "revisar de nuevo", "version_esperada": ajustada["version"]})
        self.gb(f"/revisiones/{i}/respuestas/{ref}/", {"puntaje": puntos[ref], "motivo": "Recalificación a petición del estudiante"})
        c = self.gb(f"/revisiones/{i}/confirmar/", {})
        self.assertEqual((c["ajuste_descartado"], c["ajuste_anterior"]), (True, 99))
        self.assertNotEqual(c["calificacion"]["puntaje_efectivo"], 99)
        self.assertFalse(c["calificacion"]["ajustada"])                       # el efectivo vuelve a ser lo que dice la evaluación
        recalculo = m.VersionCalificacion.objects.filter(tipo="recalculo").order_by("numero").last()
        self.assertTrue(recalculo.datos["ajuste_descartado"])
        self.assertEqual(float(recalculo.puntaje_anterior), 99.0)             # el valor que tenía queda en el historial


# ====================================================================================== M7 · lo que ve el alumno

class MisResultadosSigueAlLibroTests(BaseGradebook):
    def dos_intentos(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, intentos_permitidos=2)
        _, p1, _, _ = self.examen_entregado(abiertas=False, bien=False, asignacion=a)
        _, p2, _, _ = self.examen_entregado(abiertas=False, bien=True, asignacion=a)
        self.sincronizar()
        return a, m.Calificacion.objects.get(intento_id=p1), m.Calificacion.objects.get(intento_id=p2)

    def mias(self) -> dict:
        return self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]

    def test_con_ultimo_no_se_ensena_un_intento_viejo_mientras_el_que_cuenta_no_este_publicado(self):
        a, c1, c2 = self.dos_intentos()
        self.gb(f"/calificaciones/{c1.id}/publicar/", {})                  # sólo el intento 1 (el que NO cuenta)
        item = self.mias()
        self.assertEqual((item["estado"], item["calificacion"]), ("resultado_no_publicado", None))
        self.gb(f"/calificaciones/{c2.id}/publicar/", {})
        item = self.mias()
        self.assertEqual((item["estado"], item["calificacion"]["numero_intento"]), ("publicado", 2))

    def test_con_promedio_ve_la_media_y_solo_cuando_estan_todos_publicados(self):
        a, c1, c2 = self.dos_intentos()
        self.gb("/politica/", {"politica_intentos": "promedio"}, metodo="put", cliente=self.admin)
        self.gb(f"/calificaciones/{c1.id}/publicar/", {})
        self.assertEqual(self.mias()["estado"], "resultado_no_publicado")         # la media aún incluye un intento sin publicar
        self.gb(f"/calificaciones/{c2.id}/publicar/", {})
        item = self.mias()
        celda = self.libro()["alumnos"][0]["celdas"][a["id"]]
        self.assertEqual((item["estado"], item["calificacion"]["numero_intento"]), ("publicado", None))
        self.assertAlmostEqual(item["calificacion"]["presentada"]["valor"], celda["puntaje_efectivo"], delta=0.5)      # lo mismo que cuenta en el libro


# ===================================================================================== M9 · solicitud_id y su contenido

class SolicitudIdNoSeReutilizaTests(BaseGradebook):
    def test_una_solicitud_id_de_un_ajuste_no_sirve_para_reabrir_ni_para_ajustar_otro_valor(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        ajustada = self.ajustar(cal, 90, solicitud_id="x1")["calificacion"]
        r = self.gb(f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "otra cosa distinta", "version_esperada": ajustada["version"], "solicitud_id": "x1"}, esperado=409)
        self.assertEqual(r["codigo"], "solicitud_repetida")
        r = self.ajustar(ajustada, 10, solicitud_id="x1", esperado=409)
        self.assertEqual(r["codigo"], "solicitud_repetida")
        self.assertEqual(self.leer(f"/calificaciones/{cal['id']}/")["calificacion"]["estado"], "revisada")
        # el reenvío de verdad (la misma operación con la misma clave) sigue siendo un reintento sin efecto
        self.assertTrue(self.ajustar(cal, 90, solicitud_id="x1")["reintento"])

    def test_una_solicitud_id_de_una_pregunta_no_sirve_para_otra(self):
        a, i, _, _ = self.examen_entregado(abiertas=True)
        self.sincronizar()
        primera, segunda = self.pendientes(i)[:2]
        puntos = self.puntos_de(i)
        self.gb(f"/revisiones/{i}/respuestas/{primera}/", {"puntaje": puntos[primera], "solicitud_id": "s1"})
        r = self.gb(f"/revisiones/{i}/respuestas/{segunda}/", {"puntaje": puntos[segunda], "solicitud_id": "s1"}, esperado=409)
        self.assertEqual(r["codigo"], "solicitud_repetida")
        self.assertEqual(m.Revision.objects.count(), 1)
