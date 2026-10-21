"""
FUN-139 (avance del grupo), FUN-140 / CAP-082 (informe del alumno), FUN-142 (uso de equipos), FUN-143 (filtros) y BR-086 (umbral de privacidad): lo que cada reporte dice, a quién le dice
qué, y lo que NO dice (el dominio por objetivo, un promedio general como dato principal, personas en el reporte de equipos).
"""
from __future__ import annotations

from nodo.pruebas import cola
from .. import models as m
from .base import CURSO, BaseReporting


class ReporteDeGrupoTests(BaseReporting):
    def test_pone_primero_a_quien_necesita_atencion_con_su_motivo_en_una_linea(self):
        # los alumnos son Alumno 01, Alumno 02 y Juan (por orden alfabético): a una clase de dos no va Juan
        self.clase_cerrada([(5, 5)] * 3)
        for _ in range(3):
            self.avanzar(minutos=30)
            self.clase_cerrada([(5, 5)] * 2)
        g = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual(len(g["alumnos"]), 3)
        juan = g["alumnos"][0]                                                                              # los que necesitan atención van arriba
        self.assertEqual((juan["alumno"], juan["clases_asistidas"], juan["clases_total"]), ("Juan P.", 1, 4))
        self.assertEqual(juan["motivo"], "Estuvo en 1 de 4 clases")
        self.assertEqual([a["codigo"] for a in juan["atencion"]], ["pocas_clases"])
        self.assertEqual([a["alumno_id"] for a in g["atencion"]], [juan["alumno_id"]])
        self.assertEqual([a["atencion"] for a in g["alumnos"][1:]], [[], []])
        self.assertEqual((g["totales"]["en_atencion"], g["totales"]["alumnos"], g["totales"]["clases"]), (1, 3, 4))
        self.assertEqual([a["alumno"] for a in g["alumnos"][1:]], ["Alumno 01", "Alumno 02"])               # y los demás por nombre

    def test_no_pone_un_promedio_general_como_dato_principal_pero_si_las_cuentas_del_grupo(self):
        self.clase_cerrada([(5, 5), (0, 5)])
        g = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual(g["totales"]["promedio_aciertos"], 50)                   # existe, pero la pantalla no lo pone primero
        self.assertEqual(list(g)[:4], ["tipo", "titulo", "generado_en", "generado_por"])
        self.assertEqual([c["promedio_aciertos"] for c in g["clases"]], [50])

    def test_cuenta_las_evaluaciones_y_el_estudio_del_grupo(self):
        self.clase_cerrada([(5, 5)])
        self.evaluacion(titulo="Primer examen")
        self.evaluacion(titulo="Segundo examen")
        self.estudio(titulo="Leer la lección")
        g = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual((g["totales"]["evaluaciones"], g["totales"]["estudios"]), (2, 1))
        self.assertEqual([e["titulo"] for e in g["evaluaciones"]], ["Primer examen", "Segundo examen"])
        self.assertEqual({e["alumnos"] for e in g["evaluaciones"]}, {1})                                      # el grupo tiene un solo alumno (Juan)
        self.assertEqual(g["modo"], "simple")                                                                 # el nivel no está en modo calificaciones: sin notas
        self.assertEqual(g["objetivos"]["disponible"], False)

    def test_el_dominio_por_objetivo_no_existe_todavia_y_se_dice(self):
        self.clase_cerrada([(5, 5)])
        g = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual(g["objetivos"]["disponible"], False)
        self.assertIn("Aún no disponible", g["objetivos"]["texto"])
        self.assertEqual(self.rp("/filtros/")["objetivos"]["disponible"], False)

    def test_un_grupo_ajeno_o_inexistente(self):
        _, otro = self.otro_docente()
        self.rp(f"/grupos/{self.grupo['id']}/", cliente=otro, esperado=403)
        self.rp("/grupos/no-existe/", esperado=404)
        self.rp(f"/grupos/{self.grupo['id']}/", cliente=self.reportes())
        self.rp(f"/grupos/{self.grupo['id']}/", cliente=self.tecnico(), esperado=403)
        self.assertEqual([a.valor_nuevo["codigo"] for a in self.asientos("reporte.acceso_denegado")], ["fuera_de_alcance", "sin_permiso"])        # cada intento deja el suyo

    def test_generarlo_deja_el_evento_el_reciente_y_el_asiento_de_un_reporte_nominal(self):
        self.clase_cerrada([(5, 5), (3, 5)])
        self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual(self.eventos_rp("reporte.grupo_generado.v1"), ["reporte.grupo_generado.v1"])
        carga = cola("reporting").get(tipo_evento="reporte.grupo_generado.v1").carga
        self.assertEqual((carga["tipo"], carga["grupo_id"], carga["nominal"], carga["por"]), ("grupo", self.grupo["id"], True, self.docente_id))
        self.assertNotIn("Alumno", str(carga))
        asiento, = self.asientos("reporte.generado")
        self.assertEqual((asiento.valor_nuevo["reporte"], asiento.valor_nuevo["alcance"], asiento.valor_nuevo["filas"]), ("grupo", {"grupo_id": self.grupo["id"]}, 2))
        self.assertNotIn("Alumno", str(asiento.valor_nuevo))                        # nunca el nombre de una persona
        r = self.rp("/recientes/")["recientes"]
        self.assertEqual([(x["tipo"], x["titulo"], x["veces"]) for x in r], [("grupo", "Grupo 8A", 1)])


class ReporteDeAlumnoTests(BaseReporting):
    def test_el_informe_nominal_dice_clases_actividades_evaluaciones_y_estudio(self):
        c = self.clase_cerrada([(5, 5), None])
        self.avanzar(minutos=30)
        self.clase_cerrada([(5, 5), (0, 5)])
        self.evaluacion(titulo="Primer examen")
        self.estudio(titulo="Leer la lección")
        ana = c["alumnos"][0][0]                                    # la primera por orden alfabético: en las dos clases saca 5 de 5
        r = self.rp(f"/alumnos/{ana}/")
        self.assertTrue(r["nominal"])
        self.assertEqual(r["alumno"]["id"], ana)
        g, = r["grupos"]
        self.assertEqual(g["grupo"]["codigo"], "8A")
        s = g["resumen"]
        self.assertEqual((s["clases_total"], s["clases_asistidas"], s["actividades_recibidas"], s["actividades_entregadas"], s["porcentaje_aciertos"]), (2, 2, 2, 2, 100))
        self.assertEqual([e["titulo"] for e in g["evaluaciones"]], ["Primer examen"])
        self.assertEqual(g["evaluaciones"][0]["presentacion"], None)                                           # modo simple: ni notas ni letras
        self.assertEqual((g["evaluaciones"][0]["simbolo"], g["evaluaciones"][0]["presento"]), ("vacio", False))
        self.assertEqual([e["titulo"] for e in g["estudios"]], ["Leer la lección"])
        self.assertEqual(len(g["clases"]), 2)
        self.assertEqual(g["modo"], "simple")
        self.assertEqual(r["privacidad"]["aplicada"], False)

    def test_el_informe_del_alumno_no_se_recorta_con_el_umbral_de_privacidad(self):
        """BR-086 es de los reportes AGREGADOS: el informe de UN alumno es nominal por definición (lo ve quien tiene reports.student.view)."""
        self.rp_put("/configuracion/", {"umbral_privacidad": True})
        c = self.clase_cerrada([(5, 5)])
        r = self.rp(f"/alumnos/{c['alumnos'][0][0]}/")
        self.assertEqual((r["privacidad"]["aplicada"], r["nominal"]), (False, True))
        self.assertEqual(r["grupos"][0]["resumen"]["actividades_entregadas"], 1)

    def test_un_alumno_sin_grupo_o_ajeno(self):
        c = self.clase_cerrada([(5, 5)])
        ana = c["alumnos"][0][0]
        _, otro = self.otro_docente()
        self.rp(f"/alumnos/{ana}/", cliente=otro, esperado=403)
        self.rp(f"/alumnos/{ana}/", cliente=self.tecnico(), esperado=403)
        self.rp(f"/alumnos/{ana}/", cliente=self.reportes())
        r = self.rp(f"/alumnos/{self.docente_id}/", esperado=409)                  # una persona que no es alumno de ningún grupo
        self.assertEqual(r["codigo"], "alumno_sin_grupo")
        self.rp(f"/alumnos/{ana}/", grupo_id=self.otro_grupo["id"], cliente=self.admin, esperado=404)       # ese alumno no está en ese grupo
        self.assertEqual(self.rp(f"/alumnos/{ana}/", grupo_id=self.grupo["id"])["grupos"][0]["grupo"]["id"], self.grupo["id"])

    def test_generarlo_deja_el_asiento_sin_el_nombre_del_alumno(self):
        c = self.clase_cerrada([(5, 5)])
        ana = c["alumnos"][0][0]
        self.rp(f"/alumnos/{ana}/")
        self.assertEqual(self.eventos_rp("reporte.alumno_generado.v1"), ["reporte.alumno_generado.v1"])
        asiento, = self.asientos("reporte.generado")
        self.assertEqual(asiento.valor_nuevo["alcance"], {"alumno_id": ana})
        self.assertNotIn(c["alumnos"][0][1], str(asiento.valor_nuevo))

    def test_la_lista_de_alumnos_para_elegir_tocando(self):
        for alias in ("Álvaro", "Ana", "Beto", "Ñoño"):
            self.alumno_nuevo(alias)
        r = self.rp("/alumnos/", grupo_id=self.grupo["id"])
        self.assertEqual([a["rotulo"] for a in r["alumnos"]], ["Álvaro", "Ana", "Beto", "Juan P.", "Ñoño"])
        self.assertEqual({i["inicial"]: i["cantidad"] for i in r["iniciales"]}, {"A": 2, "B": 1, "J": 1, "Ñ": 1})
        self.rp("/alumnos/", grupo_id=self.otro_grupo["id"], esperado=403)
        self.rp("/alumnos/", grupo_id="no-existe", esperado=404)


class FiltrosTests(BaseReporting):
    def test_ofrece_grupos_periodos_y_el_arbol_sin_pedir_que_se_escriba_nada(self):
        f = self.rp("/filtros/")
        self.assertEqual([g["codigo"] for g in f["grupos"]], ["8A"])                      # el profesor sólo ve SU grupo
        self.assertEqual(f["periodos"], ["2026"])
        self.assertTrue(f["nodos"]["disponible"])
        self.assertEqual(f["puede"], {"clase": True, "grupo": True, "alumno": True, "uso": False, "exportar": True, "reconstruir": False, "configurar": False})
        admin = self.rp("/filtros/", cliente=self.admin)
        self.assertEqual(sorted(g["codigo"] for g in admin["grupos"]), ["8A", "9B"])
        self.assertTrue(admin["puede"]["configurar"] and admin["puede"]["reconstruir"] and admin["puede"]["uso"])
        tecnico = self.rp("/filtros/", cliente=self.tecnico())                             # el técnico ve lo que puede (uso y reconstruir), no lo académico
        self.assertEqual((tecnico["puede"]["clase"], tecnico["puede"]["uso"], tecnico["puede"]["reconstruir"]), (False, True, True))

    def test_br_085_el_tecnico_recibe_los_grupos_para_filtrar_el_uso_pero_ninguna_cifra_academica(self):
        """Los grupos que ofrece /filtros/ traen «cuántos alumnos» y «cuántos necesitan atención»: para quien sólo ve el uso de equipos eso es un dato académico por grupo."""
        self.clase_cerrada([(5, 5), (0, 5)])
        self.rp(f"/grupos/{self.grupo['id']}/")                                                # el grupo se calcula la primera vez que alguien lo pide
        docente = self.rp("/filtros/")["grupos"][0]
        self.assertIsInstance(docente["alumnos"], int)                                         # quien puede leer lo académico, lo recibe
        self.assertIsInstance(docente["en_atencion"], int)
        grupos = self.rp("/filtros/", cliente=self.tecnico())["grupos"]
        self.assertTrue(grupos)                                                                # sí recibe los grupos (para elegir uno en el uso de equipos)…
        for g in grupos:
            self.assertIsNone(g["alumnos"], g)                                                 # …sin cifras de estudiantes
            self.assertIsNone(g["en_atencion"], g)
            self.assertEqual(set(g) - {"id", "codigo", "nombre", "periodo", "nivel_clave"}, {"alumnos", "en_atencion", "desactualizado"}, g)

    def test_filtrar_por_nodo_academico_acota_clases_evaluaciones_y_estudio(self):
        self.clase_cerrada([(5, 5)])
        self.evaluacion()
        self.estudio()
        self.arbol.cursos[(("country", "CO"),)] = {CURSO}
        self.arbol.cursos[(("country", "MX"),)] = {"otro-curso"}
        g_co = self.rp(f"/grupos/{self.grupo['id']}/", country="CO")
        self.assertEqual((len(g_co["clases"]), g_co["totales"]["evaluaciones"], g_co["totales"]["estudios"]), (1, 1, 1))
        self.assertEqual(g_co["avisos"], [])
        g_mx = self.rp(f"/grupos/{self.grupo['id']}/", country="MX")
        self.assertEqual((len(g_mx["clases"]), g_mx["totales"]["evaluaciones"], g_mx["totales"]["estudios"]), (0, 0, 0))
        self.assertEqual(self.rp("/clases/", country="MX")["clases"], [])
        self.assertEqual(len(self.rp("/clases/", country="CO")["clases"]), 1)

    def test_un_filtro_de_materia_tiene_que_ser_un_codigo_y_no_se_guarda_otra_cosa(self):
        """Los códigos del árbol van a los recientes, a la exportación y al asiento encadenado (que no se poda): ni texto libre ni de cualquier tamaño."""
        self.clase_cerrada([(5, 5)])
        for malo in ("A" * 65, "con espacios", "a/b", "<script>", "x" * 5000, "país;DROP"):
            r = self.rp(f"/grupos/{self.grupo['id']}/", country=malo, esperado=400)
            self.assertEqual((r["codigo"], r["filtro"]), ("datos_invalidos", "country"), malo[:20])
        self.rp("/clases/", level="no válido!", esperado=400)
        self.assertEqual(self.rp("/recientes/")["recientes"], [])                              # lo rechazado no dejó rastro
        self.assertEqual(m.Exportacion.objects.count(), 0)
        cuerpo = {"reporte": {"tipo": "grupo", "grupo_id": self.grupo["id"], "subject": "q" * 100}, "formato": "csv", "destino_tipo": "carpeta_local"}
        r = self.docente.post("/api/reportes/exportaciones/", cuerpo, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertEqual(m.Exportacion.objects.count(), 0)
        # los códigos de verdad pasan (letras, números, guion, guion bajo y punto)
        self.arbol.cursos[tuple(sorted({"country": "CO", "level": "lower_secondary", "grade": "6", "subject": "science", "topic": "states-of-matter"}.items()))] = {CURSO}
        g = self.rp(f"/grupos/{self.grupo['id']}/", country="CO", level="lower_secondary", grade="6", subject="science", topic="states-of-matter")
        self.assertEqual(len(g["clases"]), 1)

    def test_los_recientes_del_mismo_reporte_se_distinguen_por_su_filtro_y_su_periodo(self):
        """Tres «Grupo 8A» seguidos no se pueden diferenciar: el título dice si lleva filtro de materia y, en el uso de equipos, desde cuándo se miró."""
        self.clase_cerrada([(5, 5)])
        self.arbol.cursos[(("country", "CO"),)] = {CURSO}
        self.rp(f"/grupos/{self.grupo['id']}/")
        self.rp(f"/grupos/{self.grupo['id']}/", country="CO")
        self.assertEqual(sorted(x["titulo"] for x in self.rp("/recientes/")["recientes"]), ["Grupo 8A", "Grupo 8A · con filtro de materia"])
        self.rp("/uso/", cliente=self.admin)
        self.rp("/uso/", cliente=self.admin, desde=self.t - 3_600_000)
        uso = sorted(x["titulo"] for x in self.rp("/recientes/", cliente=self.admin)["recientes"])
        self.assertEqual(len(uso), 2)
        self.assertEqual(uso[0], "Uso de equipos")
        self.assertTrue(uso[1].startswith("Uso de equipos · desde "), uso)

    def test_con_la_biblioteca_cerrada_el_filtro_no_se_aplica_y_se_dice(self):
        self.clase_cerrada([(5, 5)])
        self.arbol.disponible = False
        g = self.rp(f"/grupos/{self.grupo['id']}/", country="MX")
        self.assertEqual(len(g["clases"]), 1)                                                            # no se enseña como «filtrado» lo que no se pudo filtrar
        self.assertEqual(g["avisos"][0]["filtro"], "nodo")
        self.assertIn("AVACOM Biblioteca no respondió", g["avisos"][0]["texto"])
        self.assertFalse(self.rp("/filtros/")["nodos"]["disponible"])
        self.assertEqual(self.rp("/clases/", country="MX")["avisos"][0]["aplicado"], False)


class UmbralDePrivacidadTests(BaseReporting):
    """BR-086: un reporte agregado de menos de cinco alumnos, con el umbral activo, sólo muestra el agregado y lo dice."""

    def test_apagado_de_fabrica_muestra_todo(self):
        c = self.clase_cerrada([(5, 5), (0, 5)])
        r = self.reporte_de_clase(c["sesion"]["id"])
        self.assertEqual((r["privacidad"]["umbral_activo"], r["privacidad"]["aplicada"], len(r["filas"])), (False, False, 2))

    def test_activo_y_con_menos_de_cinco_alumnos_solo_el_agregado(self):
        self.rp_put("/configuracion/", {"umbral_privacidad": True})
        c = self.clase_cerrada([(5, 5), (0, 5), (5, 5), (5, 5)])
        r = self.reporte_de_clase(c["sesion"]["id"])
        self.assertEqual((r["privacidad"]["umbral_activo"], r["privacidad"]["aplicada"], r["privacidad"]["alumnos"]), (True, True, 4))
        self.assertEqual(r["filas"], [])                                                                  # ni una fila identificable
        self.assertFalse(r["nominal"])
        self.assertEqual(r["totales"]["participantes"], 4)                                                # el agregado sí
        self.assertEqual(r["totales"]["promedio_aciertos"], 75)
        self.assertIn("menos de 5", r["privacidad"]["aviso"])
        g = self.rp(f"/grupos/{self.grupo['id']}/")
        self.assertEqual((g["privacidad"]["aplicada"], g["alumnos"], g["atencion"], g["totales"]["en_atencion"]), (True, [], [], 0))
        self.assertEqual(g["totales"]["alumnos"], 4)                                                      # Juan y tres más: el grupo también tiene menos de cinco

    def test_con_cinco_o_mas_alumnos_no_se_aplica_aunque_este_activo(self):
        self.rp_put("/configuracion/", {"umbral_privacidad": True})
        c = self.clase_cerrada([(5, 5)] * 5)
        r = self.reporte_de_clase(c["sesion"]["id"])
        self.assertEqual((r["privacidad"]["aplicada"], len(r["filas"]), r["nominal"]), (False, 5, True))

    def test_el_umbral_lo_cambia_la_administracion_con_asiento_y_sin_repetir_lo_mismo(self):
        r = self.rp_put("/configuracion/", {"umbral_privacidad": True})
        self.assertEqual((r["cambiado"], r["configuracion"]["umbral_privacidad"], r["configuracion"]["version"]), (True, True, 1))
        asiento, = self.asientos("reporte.configuracion_cambiada")
        self.assertEqual((asiento.valor_anterior["umbral_privacidad"], asiento.valor_nuevo["umbral_privacidad"]), (False, True))
        r = self.rp_put("/configuracion/", {"umbral_privacidad": True})
        self.assertEqual((r["cambiado"], r["configuracion"]["version"]), (False, 1))                       # repetir lo mismo no deja asiento ni sube la versión
        self.assertEqual(len(self.asientos("reporte.configuracion_cambiada")), 1)
        self.rp_put("/configuracion/", {"umbral_privacidad": False}, cliente=self.docente, esperado=403)
        self.rp_put("/configuracion/", {"umbral_privacidad": False}, cliente=self.reportes(), esperado=403)
        self.rp_put("/configuracion/", {"umbral_privacidad": "si"}, esperado=400)
        self.rp_put("/configuracion/", {}, esperado=400)
        r = self.rp_put("/configuracion/", {"exigir_razon": True, "version_esperada": 99}, esperado=409)
        self.assertEqual(r["codigo"], "conflicto_de_version")
        self.assertEqual(self.rp("/configuracion/")["configuracion"]["umbral_privacidad"], True)           # cualquiera que pueda ver reportes lee la política

    def test_el_alumno_no_lee_la_configuracion(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.rp("/configuracion/", cliente=alumno, esperado=403)


class UsoDeEquiposTests(BaseReporting):
    def test_dice_que_equipos_se_usaron_y_cuanto_sin_ninguna_persona(self):
        a = self.clase_cerrada([(5, 5), (3, 5), None])
        self.avanzar(minutos=40)
        self.clase_cerrada([(5, 5), (3, 5)])
        u = self.rp("/uso/", cliente=self.admin)
        self.assertEqual((u["totales"]["clases"], u["totales"]["equipos"]), (2, 3))
        self.assertEqual(sorted(e["clases"] for e in u["equipos"]), [1, 2, 2])
        self.assertTrue(all(e["tiempo_total_ms"] >= 0 and e["alumnos"] >= 1 for e in u["equipos"]))
        self.assertFalse(u["nominal"])
        self.assertEqual(len(u["clases"]), 2)
        texto = str(u)
        for _, alias, _ in a["alumnos"]:
            self.assertNotIn(alias, texto)                                                         # el reporte de equipos no lleva personas
        self.assertEqual(u["privacidad"]["aplicada"], False)
        self.assertEqual(self.eventos_rp("reporte.uso_generado.v1"), ["reporte.uso_generado.v1"])
        self.assertEqual(self.asientos("reporte.generado"), [])                                    # no es nominal: no deja asiento de generación

    def test_el_tecnico_lo_ve_porque_no_lleva_personas_y_el_profesor_no_lo_tiene(self):
        self.clase_cerrada([(5, 5)])
        self.rp("/uso/", cliente=self.tecnico())
        self.rp("/uso/", cliente=self.reportes())
        self.rp("/uso/", cliente=self.docente, esperado=403)

    def test_sin_clases_finalizadas_en_el_periodo_no_hay_reporte(self):
        self.clase_cerrada([(5, 5)])
        r = self.rp("/uso/", cliente=self.admin, desde="2020-01-01", hasta="2020-01-31", esperado=409)
        self.assertEqual(r["codigo"], "sin_sesiones_finalizadas")
        self.assertIn("Elige otro periodo", r["detail"])
        self.rp("/uso/", cliente=self.admin, desde="2020-01-31", hasta="2020-01-01", esperado=400)
        self.rp("/uso/", cliente=self.admin, desde="ayer", esperado=400)

    def test_el_periodo_se_puede_dar_en_fechas_o_en_milisegundos(self):
        self.clase_cerrada([(5, 5)])
        self.rp("/uso/", cliente=self.admin, desde=self.t - 3_600_000, hasta=self.t + 3_600_000)
        u = self.rp("/uso/", cliente=self.admin, desde="2026-09-21", hasta="2026-09-21")
        self.assertEqual(u["totales"]["clases"], 1)

    def test_una_clase_abierta_no_cuenta_como_finalizada(self):
        self.clase_cerrada([(5, 5)], cerrar=False)
        self.rp("/uso/", cliente=self.admin, esperado=409)

    def test_cada_equipo_lleva_su_nombre_y_no_su_huella(self):
        self.clase_cerrada([(5, 5)])
        u = self.rp("/uso/", cliente=self.admin)
        self.assertTrue(all(e["nombre"] for e in u["equipos"]))
        self.assertNotIn("identificador_hw", str(u))


class ReservadasTests(BaseReporting):
    def test_comparar_grupos_y_cobertura_estan_reservadas_para_v1(self):
        for ruta in ("/comparar/", "/cobertura/"):
            r = self.rp(ruta, esperado=501)
            self.assertEqual((r["codigo"], r["permiso"]), ("capacidad_reservada", "reports.curriculum.view"))
        self.rp("/cobertura/", cliente=self.tecnico(), esperado=501)

    def test_el_evento_de_cobertura_se_declara_y_no_se_emite(self):
        from ..dominio import catalogos as cat
        self.assertIn(cat.EV_COBERTURA_GENERADO, cat.EVENTOS)
        from ..infraestructura.repositorios import OutboxDjango
        with self.assertRaises(ValueError):
            OutboxDjango().publicar("Reporte", "x", cat.EV_COBERTURA_GENERADO, {})
