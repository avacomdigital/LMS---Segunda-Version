"""
Las proyecciones de los reportes (H, BR-007, BR-083, FUN-144, FUN-145, FUN-147): se reconstruyen por completo desde la cola y dan los mismos reportes; el consumidor es idempotente y
aísla lo que no puede aplicar; los agregados se actualizan FUERA de clase; un reporte con equipos por sincronizar se marca incompleto una sola vez.
"""
from __future__ import annotations

from unittest import mock

from nodo.pruebas import cola
from .. import models as m
from ..aplicacion.consumidor import ConsumirEventos, Reconstruir
from ..aplicacion.puertos import Actor
from ..aplicacion.proyectar import Proyector
from ..infraestructura.contenedor import servicios
from ..infraestructura.programador import Programador
from .base import BaseReporting

TABLAS = (m.ClaseAlumno, m.Clase, m.AvanceAlumno, m.AvanceGrupo, m.EstadoDispositivo, m.MarcaConsumidor, m.EstadoProyeccion)


class SemillaDeReportes(BaseReporting):
    def sembrar(self) -> dict:
        """Dos clases con alumnos que contestan distinto, una evaluación y un estudio asignados: lo bastante para que todos los reportes tengan algo que decir."""
        a = self.clase_cerrada([(5, 5), (0, 5), None, (5, 5)])
        self.avanzar(minutos=40)
        b = self.clase_cerrada([(5, 5), None, (0, 5)])
        self.evaluacion()
        self.estudio()
        return {"a": a, "b": b}

    def foto(self, s: dict) -> dict:
        """Todo lo que un profesor puede leer, tal como lo ve (para compararlo antes y después)."""
        alumno = s["a"]["alumnos"][0][0]
        return {"clase_a": self.reporte_de_clase(s["a"]["sesion"]["id"]), "clase_b": self.reporte_de_clase(s["b"]["sesion"]["id"]),
                "grupo": self.rp(f"/grupos/{self.grupo['id']}/"), "alumno": self.rp(f"/alumnos/{alumno}/"), "clases": self.rp("/clases/"), "uso": self.rp("/uso/", cliente=self.admin)}


class ReconstruccionTests(SemillaDeReportes):
    def test_br007_reconstruir_por_la_ruta_devuelve_exactamente_los_mismos_reportes(self):
        s = self.sembrar()
        antes = self.foto(s)
        r = self.reconstruir()
        self.assertGreater(r["eventos"], 0)
        self.assertEqual(r["borradas"]["m13_clase"], 2)
        despues = self.foto(s)
        self.assertEqual(antes, despues)                       # con el reloj del nodo quieto, TODO es igual: incluso el instante de corte

    def test_br007_borrar_todo_lo_derivado_y_leer_de_nuevo_rehace_los_mismos_reportes(self):
        """Una pérdida de las proyecciones (un respaldo restaurado a medias): la marca vuelve a cero y la cola se reproduce sola."""
        s = self.sembrar()
        antes = self.foto(s)
        for modelo in TABLAS:
            modelo.objects.all().delete()
        self.assertEqual(m.Clase.objects.count(), 0)
        despues = self.foto(s)
        self.assertEqual(antes, despues)
        self.assertEqual(m.Clase.objects.count(), 2)

    def test_borrar_lo_derivado_no_toca_lo_propio(self):
        s = self.sembrar()
        self.rp_put("/configuracion/", {"umbral_privacidad": True})
        reciente_antes = list(m.Reciente.objects.values_list("tipo", flat=True))
        self.reconstruir()
        self.assertTrue(m.Config.objects.get(pk="nodo").umbral_privacidad)                    # la configuración es una decisión, no una proyección
        self.assertEqual(list(m.Reciente.objects.values_list("tipo", flat=True)), reciente_antes)
        self.assertGreaterEqual(cola("reporting").count(), 1)
        self.assertEqual(s["a"]["sesion"]["id"] in [c["sesion_id"] for c in self.rp("/clases/")["clases"]], True)

    def test_reconstruir_no_repite_los_avisos_ni_los_eventos_de_generacion(self):
        s = self.sembrar()
        self.foto(s)
        antes = cola("reporting").count()
        self.reconstruir()
        nuevos = list(cola("reporting").order_by("id").values_list("tipo_evento", flat=True)[antes:])
        self.assertEqual(nuevos, ["reporte.agregados_reconstruidos.v1"])

    def test_no_se_reconstruye_con_una_clase_abierta(self):
        self.clase_cerrada([(5, 5)], cerrar=False)
        r = self.admin.post("/api/reportes/reconstruir/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sesion_activa"))
        self.assertFalse(m.EstadoProyeccion.objects.filter(reconstruyendose=True).exists())      # el intento rechazado no deja nada «reconstruyéndose»

    def test_si_la_reconstruccion_falla_no_queda_a_medias(self):
        s = self.sembrar()
        antes = self.foto(s)
        with mock.patch.object(ConsumirEventos, "hasta_vaciar", side_effect=RuntimeError("falla de prueba")):
            with self.assertRaises(RuntimeError):
                Reconstruir(servicios()).ejecutar(Actor(id="sistema"), desde_el_sistema=True)
        estado = m.EstadoProyeccion.objects.get(pk="reportes")
        self.assertFalse(estado.reconstruyendose)
        self.assertIn("RuntimeError", estado.ultimo_error)
        self.assertEqual(self.foto(s), antes)                    # todo se revirtió (también lo que ya se había borrado): sigue lo de antes
        self.reconstruir()                                      # y la siguiente vez funciona
        self.assertEqual(m.EstadoProyeccion.objects.get(pk="reportes").ultimo_error, "")

    def test_un_grupo_que_no_se_puede_recalcular_se_dice_y_lo_demas_se_reconstruye(self):
        s = self.sembrar()
        with mock.patch.object(Proyector, "grupo", side_effect=RuntimeError("falla de prueba")):
            r = self.reconstruir()
        self.assertEqual((r["grupos"], sorted(r["grupos_fallidos"])), (0, sorted([self.grupo["id"], self.otro_grupo["id"]])))
        self.assertEqual(m.Clase.objects.count(), 2)                                           # las clases sí
        self.assertTrue(m.AvanceGrupo.objects.get(pk=self.grupo["id"]).desactualizado)         # el grupo queda marcado: se recalcula al pedirlo
        self.assertEqual(self.rp(f"/grupos/{self.grupo['id']}/")["totales"]["clases"], 2)
        self.assertEqual(s["a"]["sesion"]["id"] in [c["sesion_id"] for c in self.rp("/clases/")["clases"]], True)


class PermisosDeMantenimientoTests(SemillaDeReportes):
    def test_solo_administracion_y_tecnico_reconstruyen(self):
        self.sembrar()
        self.reconstruir(cliente=self.tecnico())
        self.reconstruir(cliente=self.admin)
        self.reconstruir(cliente=self.docente, esperado=403)
        self.reconstruir(cliente=self.reportes(), esperado=403)                 # Reportes no tiene reports.rebuild

    def test_el_estado_de_los_agregados_es_del_tecnico_y_la_administracion(self):
        self.sembrar()
        self.actualizar()
        e = self.rp("/estado/", cliente=self.admin)
        self.assertEqual(e["estado"], "al_dia")
        self.assertEqual(e["clases"], 2)
        self.assertTrue(e["puede_reconstruir"])
        self.assertEqual({f["fuente"] for f in e["fuentes"]}, {"aula", "evaluacion", "calificacion", "estudio"})
        self.rp("/estado/", cliente=self.tecnico())
        self.rp("/estado/", cliente=self.docente, esperado=403)


class ConsumidorTests(SemillaDeReportes):
    sincronizar_al_consultar = False

    def test_las_marcas_avanzan_con_lo_aplicado_y_no_se_relee_nada(self):
        self.sembrar()
        r1 = ConsumirEventos(servicios()).hasta_vaciar()
        self.assertGreater(r1["procesados"], 0)
        marcas = {x.fuente: x.ultima_secuencia for x in m.MarcaConsumidor.objects.all()}
        self.assertGreater(marcas["aula"], 0)
        r2 = ConsumirEventos(servicios()).hasta_vaciar()
        self.assertEqual((r2["leidos"], r2["procesados"]), (0, 0))
        self.assertEqual({x.fuente: x.ultima_secuencia for x in m.MarcaConsumidor.objects.all()}, marcas)

    def test_aplicar_dos_veces_el_mismo_evento_no_duplica_ni_cambia_nada(self):
        s = self.sembrar()
        ConsumirEventos(servicios()).hasta_vaciar()
        antes = (list(m.Clase.objects.order_by("sesion_id").values()), list(m.ClaseAlumno.objects.order_by("id").values_list("alumno_id", "porcentaje_aciertos")), cola("reporting").count())
        m.MarcaConsumidor.objects.all().delete()                  # el consumidor vuelve a leer TODA la cola
        r = ConsumirEventos(servicios()).hasta_vaciar()
        self.assertGreater(r["procesados"], 0)
        despues = (list(m.Clase.objects.order_by("sesion_id").values()), list(m.ClaseAlumno.objects.order_by("id").values_list("alumno_id", "porcentaje_aciertos")), cola("reporting").count())
        self.assertEqual(antes, despues)
        self.assertEqual(m.ClaseAlumno.objects.count(), 7)

    def test_un_evento_que_falla_retiene_la_marca_y_tras_cinco_ciclos_se_deja_atras_con_asiento(self):
        self.clase_cerrada([(5, 5)])
        with mock.patch.object(Proyector, "clase", side_effect=RuntimeError("falla de prueba")):
            for ciclo in range(1, 5):
                r = ConsumirEventos(servicios()).ejecutar()
                self.assertGreaterEqual(len(r["fallidos"]), 1, ciclo)                # cerrar una clase deja varios eventos del aula: todos fallan igual
            marca = m.MarcaConsumidor.objects.get(pk="aula")
            self.assertGreater(marca.secuencia_fallida, 0)                       # la marca NO pasó de largo
            self.assertEqual(marca.fallos_seguidos, 4)
            self.assertEqual(self.asientos("reporte.evento_omitido"), [])
            ConsumirEventos(servicios()).ejecutar()                              # el quinto
        marca = m.MarcaConsumidor.objects.get(pk="aula")
        self.assertEqual((marca.secuencia_fallida, marca.fallos_seguidos), (0, 0))
        asientos = self.asientos("reporte.evento_omitido")
        self.assertEqual(len(asientos), 1)
        self.assertEqual(asientos[0].valor_nuevo["fuente"], "aula")

    def test_un_evento_que_falla_no_detiene_a_los_demas(self):
        self.clase_cerrada([(5, 5)])
        a2 = self.clase_cerrada([(5, 5)])
        originales = Proyector.clase
        primera = {"hecho": False}

        def a_medias(proyector, uow, sesion_id, ahora):
            if not primera["hecho"]:
                primera["hecho"] = True
                raise RuntimeError("falla de prueba")
            return originales(proyector, uow, sesion_id, ahora)

        with mock.patch.object(Proyector, "clase", a_medias):
            r = ConsumirEventos(servicios()).ejecutar()
        self.assertEqual(len(r["fallidos"]), 1)
        self.assertGreaterEqual(r["procesados"], 1)                              # el otro sí se aplicó
        self.assertEqual(m.Clase.objects.filter(pk=a2["sesion"]["id"]).count(), 1)


class ActualizacionPeriodicaTests(SemillaDeReportes):
    """FUN-144: los agregados se actualizan fuera del horario de clase."""

    sincronizar_al_consultar = False

    def test_con_una_clase_abierta_espera_y_sin_ella_actualiza(self):
        self.clase_cerrada([(5, 5)], cerrar=False)
        self.assertEqual(Programador.tick(), {"omitido": "clase_en_curso"})
        self.assertEqual(m.Clase.objects.count(), 0)
        self.assertEqual(m.MarcaConsumidor.objects.count(), 0)                   # ni siquiera leyó la cola: no compite con las tabletas

    def test_fuera_de_clase_pone_al_dia_y_avisa_una_sola_vez(self):
        s = self.sembrar()
        self.assertEqual(self.rp("/estado/", cliente=self.admin)["estado"], "rezagada")      # hay eventos sin aplicar: se dice como antigüedad del dato
        r = Programador.tick()
        self.assertGreater(r["eventos"], 0)
        self.assertEqual(r["grupos"], 1)
        self.assertFalse(m.AvanceGrupo.objects.get(pk=self.grupo["id"]).desactualizado)
        self.assertEqual(self.eventos_rp("reporte.agregados_actualizados.v1"), ["reporte.agregados_actualizados.v1"])
        self.assertEqual(self.rp("/estado/", cliente=self.admin)["estado"], "al_dia")
        Programador.tick()
        self.assertEqual(len(self.eventos_rp("reporte.agregados_actualizados.v1")), 1)       # sin novedades no hay evento
        self.assertEqual(self.reporte_de_clase(s["a"]["sesion"]["id"])["corte"]["estado"], "al_dia")

    def test_un_cambio_en_el_grupo_lo_marca_desactualizado_y_se_recalcula_al_pedirlo(self):
        self.sembrar()
        Programador.tick()
        self.assertFalse(m.AvanceGrupo.objects.get(pk=self.grupo["id"]).desactualizado)
        self.estudio(titulo="Otra tarea")
        ConsumirEventos(servicios()).hasta_vaciar()
        self.assertTrue(m.AvanceGrupo.objects.get(pk=self.grupo["id"]).desactualizado)
        g = self.rp(f"/grupos/{self.grupo['id']}/")                              # al pedirlo se recalcula en el momento: nunca enseña un avance viejo
        self.assertEqual(g["totales"]["estudios"], 2)
        self.assertFalse(m.AvanceGrupo.objects.get(pk=self.grupo["id"]).desactualizado)

    def test_la_actualizacion_a_peticion_la_pide_quien_puede_reconstruir(self):
        self.sembrar()
        r = self.actualizar()
        self.assertEqual(r["grupos"], 1)
        self.actualizar(cliente=self.docente, esperado=403)

    def test_el_estado_muestra_antiguedad_si_la_cola_va_por_detras(self):
        self.clase_cerrada([(5, 5)])
        from ..dominio import catalogos as cat
        self.avanzar(minutos=10)                                                    # esos eventos se publicaron hace diez minutos y nadie los ha leído (la cola única es inmutable: se mueve el reloj)
        mas_viejo = min(e.creado_en for e in cola("classroom_engine").filter(tipo_evento__in=cat.EVENTOS_CONSUMIDOS["aula"]))
        e = self.rp("/estado/", cliente=self.admin)
        self.assertEqual(e["estado"], "rezagada")
        self.assertEqual(e["corte_en"], mas_viejo - 1)                              # lo que el reporte sabe es lo anterior al evento más viejo sin aplicar
        self.assertEqual(e["antiguedad_ms"], self.t - mas_viejo + 1)
        self.assertGreaterEqual(e["antiguedad_ms"], 600_001)


class IntegracionTests(BaseReporting):
    """BR-083 y FUN-145: el reporte declara cuántas tabletas aún no sincronizan y se marca incompleto UNA vez."""

    def test_un_participante_que_quedo_reconectando_deja_la_clase_incompleta_hasta_que_pasa_la_gracia(self):
        a, b = self.alumno_nuevo(), self.alumno_nuevo()
        s = self.clase()
        pa, pb = self.unir(s, a[0], a[1]), self.unir(s, b[0], b[1])
        self.presencia(s["id"], pa, "reconectando")
        d = self.lanzar(s["id"])
        self.responder(s["id"], d, pb)
        self.entregar(s["id"], d, pb)
        self.cerrar_actividad(s["id"], d)
        self.cerrar_clase(s["id"])
        r = self.reporte_de_clase(s["id"])
        integ = r["corte"]["integracion"]
        self.assertEqual((r["corte"]["incompleto"], integ["estado"], integ["sin_sincronizar"], integ["equipos"]), (True, "incompleta", 1, 2))
        self.assertEqual([x["codigo"] for x in integ["motivos"]], ["conexion_perdida"])
        self.assertTrue(r["corte"]["texto"].endswith("· 1 tableta sin sincronizar"))
        self.assertEqual(integ["motivo_linea"], "1 tableta aún no sincroniza")
        self.assertEqual(self.eventos_rp("reporte.marcado_incompleto.v1"), ["reporte.marcado_incompleto.v1"])
        for _ in range(3):
            self.reporte_de_clase(s["id"])
        self.assertEqual(len(self.eventos_rp("reporte.marcado_incompleto.v1")), 1)           # una vez por cambio, no por lectura
        carga = cola("reporting").get(tipo_evento="reporte.marcado_incompleto.v1").carga
        self.assertEqual((carga["ambito"], carga["sin_sincronizar"], carga["motivos"]), ("clase", 1, ["conexion_perdida"]))
        self.assertNotIn("alumno_id", str(carga))
        # pasada la gracia del nodo (15 min) ya no espera nada de esa tableta: el reporte es completo sin que ocurra ningún evento
        self.avanzar(minutos=16)
        r = self.reporte_de_clase(s["id"])
        self.assertEqual((r["corte"]["incompleto"], r["corte"]["integracion"]["estado"]), (False, "completa"))
        self.assertEqual(m.Clase.objects.get(pk=s["id"]).estado_integracion, "incompleta")      # lo guardado aún lo dice…
        self.actualizar()
        self.assertEqual(m.Clase.objects.get(pk=s["id"]).estado_integracion, "completa")        # …hasta que la actualización periódica lo limpia

    def test_la_entrega_que_llega_por_la_cola_se_cuenta_como_entrega_y_se_distingue(self):
        a, alias = self.alumno_nuevo()
        s = self.clase()
        pa = self.unir(s, a, alias)
        d = self.lanzar(s["id"])
        self.responder(s["id"], d, pa)
        self.cerrar_actividad(s["id"], d)
        self.cerrar_clase(s["id"])
        r = self.reporte_de_clase(s["id"])
        self.assertEqual(r["filas"][0]["actividades_entregadas"], 1)                    # el cierre entregó lo que llevaba
        self.assertEqual(r["filas"][0]["entregas_por_cola"], 0)

    def test_la_cola_de_estudio_de_una_tableta_marca_incompleto_el_avance_del_grupo(self):
        s = self.clase_cerrada([(5, 5)])
        self.estudio()
        r0 = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual((r0["corte"]["incompleto"], r0["corte"]["integracion"]["sin_sincronizar"]), (False, 0))
        sesion = self.api.post("/api/modo-estudio/sesion/", {"dispositivo": self.hw_juan, "alumno_id": self.estudiante_id}, format="json")
        self.assertEqual(sesion.status_code, 200, sesion.content)
        c = self.api.post("/api/modo-estudio/sesion/cerrar/", {"dispositivo": self.hw_juan, "alumno_id": self.estudiante_id, "cola_pendiente": 2, "limpieza": "pendiente"}, format="json")
        self.assertEqual(c.status_code, 200, c.content)
        r = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual((r["corte"]["incompleto"], r["corte"]["integracion"]["sin_sincronizar"]), (True, 1))
        self.assertEqual([x["codigo"] for x in r["corte"]["integracion"]["motivos"]], ["cola_de_estudio"])
        avisos = cola("reporting").filter(tipo_evento="reporte.marcado_incompleto.v1")
        self.assertEqual(avisos.count(), 1)
        self.assertEqual(avisos.get().carga["ambito"], "grupo")
        # el informe de ese alumno también lo declara
        ra = self.rp(f"/alumnos/{self.estudiante_id}/")
        self.assertTrue(ra["corte"]["incompleto"])
        # cuando el nodo integra su trabajo (`estudio.trabajo.integrado.v1`), el reporte vuelve a ser completo
        cola("modo_estudio").create(agregado_tipo="Sincronizacion", agregado_id="e1", tipo_evento="estudio.trabajo.integrado.v1",
                                    carga={"alumno_id": self.estudiante_id, "dispositivo_id": sesion.json()["dispositivo"]["id"], "integrados": 2}, creado_en=self.t)
        r = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual((r["corte"]["incompleto"], r["corte"]["integracion"]["estado"]), (False, "completa"))
        self.assertEqual(s["sesion"]["id"] is not None, True)
