"""
FUN-126 · estado simple, FUN-127 · agregados tras cada cambio, FUN-129 · reconstrucción tras una restauración, y el consumidor de eventos de MOD-010: idempotente,
ordenado por su secuencia, con marca de lectura, aislando el evento que no se puede aplicar.
"""
from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import override_settings

from audit import models as maudit
from evaluacion import models as m10

from .. import models as m
from ..aplicacion.consumidor import ConsumirEventos
from ..dominio import catalogos as cat
from ..infraestructura.contenedor import servicios
from .base import BaseGradebook


def derivado() -> dict:
    """Una foto de lo derivado, para compararla antes y después de reconstruirlo."""
    campos = ("estado_simple", "estado_calificacion", "calificacion_aplicable_id", "puntaje_aplicable", "politica_intentos", "intentos_total", "intentos_registrados", "cuenta", "publicada")
    agregados = ("calificaciones", "promedio_simple", "pendientes", "provisionales", "publicadas")
    return {"resultados": {(r.asignacion_id, r.alumno_id): tuple(getattr(r, c) for c in campos) for r in m.ResultadoAsignacion.objects.all()},
            "agregados": {(a.alumno_id, a.grupo_id, a.periodo, a.curso_ref): tuple(getattr(a, c) for c in agregados) for a in m.AgregadoPeriodo.objects.all()}}


class EstadoSimpleTests(BaseGradebook):
    def test_fun_126_el_estado_simple_se_calcula_y_se_avisa_en_cada_cambio(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        self.sincronizar()
        self.assertEqual(self.eventos_gb("calificacion.estado_simple_calculado.v1"), [])         # nadie ha empezado: no hay novedad que avisar
        apertura = self.abrir(a["id"])
        self.sincronizar()
        evento = m.EventoSalida.objects.filter(tipo_evento="calificacion.estado_simple_calculado.v1").get()
        self.assertEqual((evento.carga["estado"], evento.carga["anterior"], evento.carga["alumno_id"]), ("en_progreso", None, self.estudiante_id))
        self.entregar(apertura["intento"]["id"], confirmar=True)
        self.sincronizar()
        estados = [(e.carga["anterior"], e.carga["estado"]) for e in m.EventoSalida.objects.filter(tipo_evento="calificacion.estado_simple_calculado.v1").order_by("id")]
        self.assertEqual(estados, [(None, "en_progreso"), ("en_progreso", "completado")])
        fila = m.ResultadoAsignacion.objects.get(asignacion_id=a["id"], alumno_id=self.estudiante_id)
        self.assertEqual(fila.estado_simple, "completado")
        self.sincronizar()                                                                       # sin novedades no se repite
        self.assertEqual(len(self.eventos_gb("calificacion.estado_simple_calculado.v1")), 2)

    def test_completar_no_es_tener_una_calificacion_publicada(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        self.sincronizar()
        fila = m.ResultadoAsignacion.objects.get(asignacion_id=a["id"], alumno_id=self.estudiante_id)
        self.assertEqual((fila.estado_simple, fila.estado_calificacion, fila.publicada), ("completado", "revisado", False))


class AgregadosTests(BaseGradebook):
    def dos_evaluaciones(self, bien2: bool = True):
        a1, i1, _, _ = self.examen_entregado(abiertas=False)
        a2, i2, _, _ = self.examen_entregado(abiertas=False, bien=bien2, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        self.sincronizar()
        return (a1, i1), (a2, i2)

    def agregado(self) -> m.AgregadoPeriodo:
        return m.AgregadoPeriodo.objects.get(alumno_id=self.estudiante_id, grupo_id=self.grupo["id"])

    def test_fun_127_los_agregados_se_recalculan_tras_cada_cambio(self):
        (a1, i1), (a2, i2) = self.dos_evaluaciones()
        c1, c2 = self.fila_cal(i1), self.fila_cal(i2)
        esperado = ((c1.puntaje_efectivo + c2.puntaje_efectivo) / 2).quantize(Decimal("0.01"))
        ag = self.agregado()
        self.assertEqual((ag.calificaciones, ag.promedio_simple, ag.pendientes, ag.publicadas, ag.periodo), (2, esperado, 0, 0, "2026"))
        antes = len(self.eventos_gb("calificacion.agregados_recalculados.v1"))
        cal = self.leer(f"/calificaciones/{c1.id}/")["calificacion"]
        self.ajustar(cal, 100)
        ag = self.agregado()
        self.assertEqual(ag.promedio_simple, ((Decimal("100") + c2.puntaje_efectivo) / 2).quantize(Decimal("0.01")))      # el ajuste recalcula
        self.gb(f"/calificaciones/{c1.id}/publicar/", {})
        self.assertEqual(self.agregado().publicadas, 1)
        self.assertGreater(len(self.eventos_gb("calificacion.agregados_recalculados.v1")), antes)
        evento = m.EventoSalida.objects.filter(tipo_evento="calificacion.agregados_recalculados.v1").order_by("-id").first()
        self.assertEqual((evento.carga["oficial"], evento.carga["alumno_id"]), (False, self.estudiante_id))

    def test_lo_provisional_o_pendiente_no_entra_al_promedio_pero_se_cuenta(self):
        a1, i1, _, _ = self.examen_entregado(abiertas=False)
        a2, i2, _, _ = self.examen_entregado(abiertas=True, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))        # en revisión
        self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})                                                                         # sin empezar
        self.sincronizar()
        c1 = self.fila_cal(i1)
        ag = self.agregado()
        self.assertEqual((ag.calificaciones, ag.promedio_simple, ag.provisionales), (1, c1.puntaje_efectivo, 1))
        self.assertEqual(m.Calificacion.objects.count(), 1)                          # lo provisional NO se guardó como calificación

    def test_sin_nada_registrado_no_hay_promedio_y_nunca_es_cero(self):
        self.examen_entregado(abiertas=True)
        self.sincronizar()
        ag = self.agregado()
        self.assertEqual((ag.calificaciones, ag.promedio_simple), (0, None))

    def test_una_evaluacion_formativa_no_afecta_la_calificacion_oficial(self):
        (a1, i1), (a2, i2) = self.dos_evaluaciones(bien2=False)
        c1 = self.fila_cal(i1)
        self.assertEqual(self.gb(f"/asignaciones/{a2['id']}/clasificacion/", {"tipo_evaluacion": "formativa"}, metodo="put")["afecta_oficial"], False)
        self.assertEqual(self.agregado().promedio_simple, c1.puntaje_efectivo)       # el cero de la formativa no promedia
        self.assertEqual(self.leer(f"/asignaciones/{a2['id']}/clasificacion/")["tipo_evaluacion"], "formativa")
        self.assertEqual(self.leer(f"/asignaciones/{a1['id']}/clasificacion/")["tipo_evaluacion"], "sumativa")        # el examen, por defecto, sumativo y oficial
        self.gb(f"/asignaciones/{a2['id']}/clasificacion/", {"tipo_evaluacion": "inventada"}, metodo="put", esperado=400)
        self.assertEqual(self.eventos_gb("calificacion.clasificacion_definida.v1"), ["calificacion.clasificacion_definida.v1"])

    def test_el_resumen_del_periodo_es_informativo_y_con_menos_de_tres_no_hay_promedio_de_grupo(self):
        self.dos_evaluaciones()
        r = self.leer("/resumen/", grupo_id=self.grupo["id"])
        self.assertEqual((r["oficial"], r["ponderado"]), (False, False))
        self.assertIn("No es una calificación oficial", r["aviso"])
        curso = r["cursos"][0]
        self.assertEqual((len(curso["alumnos"]), curso["promedio_del_grupo"], curso["datos_suficientes"]), (1, None, False))
        for nombre, codigo in (("Ana", "300801"), ("Luis", "300802")):
            alumno_id, hw = self.alumno_con_tableta(nombre, codigo)
            for _ in range(2):
                self.examen_entregado(abiertas=False, hw=hw, alumno_id=alumno_id, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        self.sincronizar()
        curso = self.leer("/resumen/", grupo_id=self.grupo["id"], curso_ref=curso["curso_ref"])["cursos"][0]
        self.assertEqual((len(curso["alumnos"]), curso["datos_suficientes"]), (3, True))
        self.assertIsNotNone(curso["promedio_del_grupo"])
        self.assertEqual(self.leer("/resumen/", grupo_id=self.grupo["id"], periodo="2099")["cursos"], [])


class ReconstruccionTests(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a, self.i, _, _ = self.examen_entregado(abiertas=False)
        self.a2, self.i2, _, _ = self.examen_entregado(abiertas=True, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        self.sincronizar()
        self.cal = self.leer(f"/calificaciones/{self.fila_cal(self.i).id}/")["calificacion"]
        self.ajustar(self.cal, 77.5)
        self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {})

    def test_fun_129_se_reconstruye_lo_derivado_y_queda_igual(self):
        antes = derivado()
        self.assertTrue(antes["resultados"] and antes["agregados"])
        calificaciones = list(m.Calificacion.objects.values_list("id", "puntaje_original", "puntaje_efectivo", "estado", "version"))
        versiones = m.VersionCalificacion.objects.count()
        m.ResultadoAsignacion.objects.all().delete()                                 # un respaldo restaurado sin lo derivado…
        m.AgregadoPeriodo.objects.all().delete()
        r = self.gb("/derivados/reconstruir/", {}, cliente=self.admin)
        self.assertEqual((r["resultados"], r["agregados"]), (len(antes["resultados"]), len(antes["agregados"])))
        self.assertEqual(derivado(), antes)                                          # …vuelve a ser exactamente lo mismo
        self.assertEqual(list(m.Calificacion.objects.values_list("id", "puntaje_original", "puntaje_efectivo", "estado", "version")), calificaciones)      # ni una nota tocada
        self.assertEqual(m.VersionCalificacion.objects.count(), versiones)
        self.assertEqual(self.eventos_gb("calificacion.derivadas_reconstruidas.v1"), ["calificacion.derivadas_reconstruidas.v1"])
        self.assertTrue(maudit.Bitacora.objects.filter(accion="calificacion.derivadas_reconstruidas").exists())

    def test_reconstruir_dos_veces_es_idempotente_y_solo_lo_hace_la_administracion(self):
        self.gb("/derivados/reconstruir/", {}, cliente=self.admin)
        uno = derivado()
        self.gb("/derivados/reconstruir/", {}, cliente=self.admin)
        self.assertEqual(derivado(), uno)
        self.gb("/derivados/reconstruir/", {}, cliente=self.docente, esperado=403)
        self.assertEqual(self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.docente, esperado=403)["codigo"], "sin_permiso")

    def test_reproducir_todos_los_eventos_tras_perder_la_marca_no_duplica_nada(self):
        antes, eventos = derivado(), self.eventos_gb()
        calificaciones, versiones = m.Calificacion.objects.count(), m.VersionCalificacion.objects.count()
        m.MarcaConsumidor.objects.all().delete()                                      # se perdió hasta dónde se había leído
        r = self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin)
        self.assertGreater(r["reproduccion"]["leidos"], 0)
        self.assertEqual(r["reproduccion"]["fallidos"], [])
        self.assertEqual((m.Calificacion.objects.count(), m.VersionCalificacion.objects.count()), (calificaciones, versiones))
        self.assertEqual(derivado(), antes)
        nuevos = [e for e in self.eventos_gb() if e not in eventos or self.eventos_gb().count(e) != eventos.count(e)]
        self.assertEqual(set(nuevos), {"calificacion.derivadas_reconstruidas.v1"})   # reproducir NO vuelve a emitir registros ni ajustes

    def test_sin_el_resultado_de_la_asignacion_el_libro_aun_la_muestra_pendiente_no_en_cero(self):
        m.ResultadoAsignacion.objects.all().delete()
        celda = self.libro()["alumnos"][0]["celdas"][self.a2["id"]]
        self.assertEqual((celda["estado"], celda["puntaje_efectivo"]), ("pendiente", None))


class ConsumidorTests(BaseGradebook):
    def marca(self) -> int:
        fila = m.MarcaConsumidor.objects.filter(pk=cat.CONSUMIDOR).first()
        return fila.ultima_secuencia if fila else 0

    def test_la_marca_avanza_hasta_el_final_de_la_cola_de_mod_010(self):
        self.examen_entregado(abiertas=False)
        ultimo = m10.EventoSalida.objects.order_by("-id").first().id
        r = ConsumirEventos(servicios()).ejecutar()
        self.assertEqual((r["marca"], r["fallidos"], r["pendientes"]), (ultimo, [], False))
        self.assertEqual(self.marca(), ultimo)
        r = ConsumirEventos(servicios()).ejecutar()
        self.assertEqual((r["leidos"], r["procesados"], r["marca"]), (0, 0, ultimo))        # sin novedades no hace nada
        fila = m.MarcaConsumidor.objects.get(pk=cat.CONSUMIDOR)
        self.assertEqual((fila.fuente, fila.actualizada_en), ("m10_evento_salida", self.t))          # hora del nodo

    def test_con_lotes_chicos_procesa_en_orden_y_llega_al_mismo_resultado(self):
        self.examen_entregado(abiertas=False)
        self.examen_entregado(abiertas=False, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        with override_settings(AVACOM_GRADEBOOK_LOTE_EVENTOS=1):
            marcas = []
            while True:
                r = ConsumirEventos(servicios()).ejecutar()
                marcas.append(r["marca"])
                if not r["pendientes"]:
                    break
        self.assertEqual(marcas, sorted(marcas))                                      # la marca sólo avanza
        self.assertGreater(len(marcas), 2)
        self.assertEqual(m.Calificacion.objects.count(), 2)

    def test_la_marca_y_lo_aplicado_se_confirman_juntos(self):
        self.examen_entregado(abiertas=False)
        with mock.patch("gradebook.infraestructura.repositorios.MarcasDjango.guardar", side_effect=RuntimeError("se cayó el disco")):
            with self.assertRaises(RuntimeError):
                ConsumirEventos(servicios()).ejecutar()
        self.assertEqual((m.Calificacion.objects.count(), self.marca()), (0, 0))        # nada a medias: ni la nota ni la marca
        ConsumirEventos(servicios()).ejecutar()
        self.assertEqual(m.Calificacion.objects.count(), 1)

    def test_dos_consumidores_con_la_misma_marca_no_duplican(self):
        self.examen_entregado(abiertas=False)
        ConsumirEventos(servicios()).ejecutar()
        m.MarcaConsumidor.objects.filter(pk=cat.CONSUMIDOR).update(ultima_secuencia=0)         # el otro leyó antes de que éste guardara su marca
        ConsumirEventos(servicios()).ejecutar()
        self.assertEqual((m.Calificacion.objects.count(), m.VersionCalificacion.objects.count()), (1, 1))
        self.assertEqual(self.eventos_gb("calificacion.registrada.v1"), ["calificacion.registrada.v1"])

    def test_un_evento_que_no_se_puede_aplicar_se_aisla_y_los_demas_siguen(self):
        a1, i1, _, _ = self.examen_entregado(abiertas=False)
        a2, i2, _, _ = self.examen_entregado(abiertas=False, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
        original = __import__("gradebook.aplicacion.registro", fromlist=["Registrador"]).Registrador.registrar

        def falla_con_el_primero(self_, uow, intento_id, *a, **k):
            if intento_id == i1:
                raise RuntimeError("evento envenenado")
            return original(self_, uow, intento_id, *a, **k)

        with mock.patch("gradebook.aplicacion.registro.Registrador.registrar", falla_con_el_primero):
            r = ConsumirEventos(servicios()).ejecutar()
        self.assertEqual([f["error"] for f in r["fallidos"]], ["RuntimeError"])
        self.assertEqual(list(m.Calificacion.objects.values_list("intento_id", flat=True)), [i2])         # el otro sí se registró
        self.assertEqual(self.marca(), r["marca"])                                                         # y la cola no quedó atascada
        self.sincronizar()                                                                                 # el primero se vuelve a intentar con un reproducido
        self.gb("/derivados/reconstruir/", {"reproducir": True}, cliente=self.admin)
        self.assertEqual(m.Calificacion.objects.count(), 2)

    def test_eventos_sin_datos_o_de_intentos_inexistentes_se_saltan_sin_romper(self):
        m10.EventoSalida.objects.create(agregado_tipo="Intento", agregado_id="x", tipo_evento="evaluacion.intento_calificado.v1", carga={})
        m10.EventoSalida.objects.create(agregado_tipo="Intento", agregado_id="y", tipo_evento="evaluacion.intento_calificado.v1",
                                        carga={"intento_id": "no-existe", "asignacion_id": "tampoco", "alumno_id": "nadie"})
        r = ConsumirEventos(servicios()).ejecutar()
        self.assertEqual((r["fallidos"], r["procesados"]), ([], 2))
        self.assertEqual(m.Calificacion.objects.count(), 0)

    def test_el_hilo_del_nodo_usa_el_mismo_caso_de_uso(self):
        from ..infraestructura.programador import Programador
        self.examen_entregado(abiertas=False)
        Programador.tick()
        self.assertEqual(m.Calificacion.objects.count(), 1)

    def test_las_consultas_ponen_el_libro_al_dia_antes_de_responder(self):
        self.examen_entregado(abiertas=False)
        self.assertEqual(m.Calificacion.objects.count(), 0)
        self.libro()
        self.assertEqual(m.Calificacion.objects.count(), 1)
        with override_settings(AVACOM_GRADEBOOK_SINCRONIZAR=False):
            self.examen_entregado(abiertas=False, asignacion=self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}))
            self.libro()
            self.assertEqual(m.Calificacion.objects.count(), 1)                              # con la puesta al día apagada, sólo lo hace el hilo
