"""
El dominio de Reporting, sin base de datos ni HTTP: las cuentas (con `Decimal`, sin cero donde no hay dato), «necesita atención», la integración de los equipos (BR-083), el umbral de
privacidad (BR-086), el nombre seguro del archivo, el cálculo de una clase a partir de lo que entrega el aula y el avance de un alumno.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.test import SimpleTestCase

from ..dominio import archivo as arch
from ..dominio import avance as av
from ..dominio import catalogos as cat
from ..dominio import clase as clase_dom
from ..dominio import documento as doc
from ..dominio import integracion as integ
from ..dominio import metricas as mt
from ..dominio import privacidad as priv
from ..dominio import texto as tx


class MetricasTests(SimpleTestCase):
    def test_un_porcentaje_sin_total_no_existe_y_un_cero_real_si(self):
        self.assertIsNone(mt.porcentaje(1, 0))
        self.assertIsNone(mt.porcentaje(None, 5))
        self.assertEqual(mt.porcentaje(0, 5), Decimal("0.00"))
        self.assertEqual(mt.porcentaje(1, 3), Decimal("33.33"))
        self.assertEqual(mt.porcentaje(2, 3), Decimal("66.67"))
        self.assertEqual(mt.porcentaje(7, 5), Decimal("100.00"))                   # nunca pasa de 100

    def test_el_promedio_cuenta_a_quien_tiene_cifra_y_redondea_mitad_arriba(self):
        self.assertIsNone(mt.promedio([]))
        self.assertIsNone(mt.promedio([None, None]))
        self.assertEqual(mt.promedio([100, None, 0]), Decimal("50.00"))
        self.assertEqual(mt.promedio([Decimal("0.005")]), Decimal("0.01"))
        self.assertEqual(mt.promedio([Decimal("84.99"), Decimal("85.00")]), Decimal("85.00"))      # 84,995 → 85,00

    def test_los_numeros_viajan_sin_ruido_binario(self):
        self.assertEqual(mt.a_decimal(0.1), Decimal("0.1"))
        self.assertEqual(mt.como_numero(Decimal("25.00")), 25)
        self.assertIsInstance(mt.como_numero(Decimal("25.00")), int)
        self.assertEqual(mt.como_numero(Decimal("22.22")), 22.22)
        self.assertIsNone(mt.como_numero(None))
        for no_es_numero in (True, "x", float("nan"), float("inf"), [1]):
            self.assertIsNone(mt.a_decimal(no_es_numero))


class AtencionTests(SimpleTestCase):
    def motivos(self, **kw):
        return [(m["codigo"], m["texto"]) for m in mt.motivos_de_atencion(mt.MetricasDeAlumno(**kw))]

    def test_con_pocos_datos_no_se_juzga(self):
        self.assertEqual(self.motivos(clases_total=1, clases_asistidas=0, actividades_recibidas=2, actividades_entregadas=0), [])

    def test_asistencia_y_entrega_por_debajo_de_la_mitad(self):
        self.assertEqual(self.motivos(clases_total=4, clases_asistidas=1), [("pocas_clases", "Estuvo en 1 de 4 clases")])
        self.assertEqual(self.motivos(clases_total=4, clases_asistidas=2), [])                      # justo la mitad: no es «por debajo»
        self.assertEqual(self.motivos(actividades_recibidas=3, actividades_entregadas=1), [("pocas_entregas", "Entregó 1 de 3 actividades de clase")])
        self.assertEqual(self.motivos(actividades_recibidas=4, actividades_entregadas=2), [])

    def test_evaluaciones_y_estudio_con_su_singular_y_su_plural(self):
        self.assertEqual(self.motivos(evaluaciones_sin_presentar=1), [("evaluaciones_sin_presentar", "No presentó 1 evaluación")])
        self.assertEqual(self.motivos(evaluaciones_sin_presentar=2), [("evaluaciones_sin_presentar", "No presentó 2 evaluaciones")])
        self.assertEqual(self.motivos(estudios_vencidos=1), [("estudio_vencido", "Tiene 1 tarea de estudio vencida")])
        self.assertEqual(self.motivos(estudios_vencidos=3), [("estudio_vencido", "Tiene 3 tareas de estudio vencidas")])

    def test_del_mas_al_menos_urgente(self):
        codigos = [c for c, _ in self.motivos(clases_total=4, clases_asistidas=1, actividades_recibidas=4, actividades_entregadas=0, evaluaciones_sin_presentar=1, estudios_vencidos=2)]
        self.assertEqual(codigos, ["evaluaciones_sin_presentar", "pocas_entregas", "pocas_clases", "estudio_vencido"])
        self.assertEqual(tuple(codigos), cat.MOTIVOS_DE_ATENCION)


class IntegracionTests(SimpleTestCase):
    def test_una_senal_de_un_motivo_desconocido_no_se_acepta(self):
        with self.assertRaises(ValueError):
            integ.senal("e1", "inventado", 10)

    def test_una_senal_caduca_sin_que_pase_nada_y_se_ordena_sin_repetir(self):
        a, b = integ.senal("b", cat.CONEXION_PERDIDA, 100), integ.senal("a", cat.ENTREGA_PENDIENTE, 100)
        vencida = integ.senal("c", cat.CONEXION_PERDIDA, 50)
        self.assertEqual([s["equipo"] for s in integ.vigentes([a, b, b, vencida], 49)], ["a", "b", "c"])
        self.assertEqual([s["equipo"] for s in integ.vigentes([a, b, b, vencida], 50)], ["a", "b"])           # justo en el instante: ya no vale
        self.assertEqual(integ.vigentes([a, b], 100), [])

    def test_resumen_cuenta_equipos_distintos_y_dice_el_motivo(self):
        senales = [integ.senal("e1", cat.CONEXION_PERDIDA, 100), integ.senal("e1", cat.ENTREGA_PENDIENTE, 100), integ.senal("e2", cat.COLA_DE_ESTUDIO, 100)]
        r = integ.resumir(senales, 24, 0)
        self.assertEqual((r["estado"], r["equipos"], r["sin_sincronizar"], r["texto"]), ("incompleta", 24, 2, "2 tabletas sin sincronizar"))
        self.assertEqual(r["motivo_linea"], "2 tabletas aún no sincronizan")
        self.assertEqual([(m["codigo"], m["equipos"]) for m in r["motivos"]], [("conexion_perdida", 1), ("entrega_pendiente", 1), ("cola_de_estudio", 1)])
        uno = integ.resumir(senales[:1], 3, 0)
        self.assertEqual((uno["texto"], uno["motivo_linea"], uno["motivos"][0]["texto"]), ("1 tableta sin sincronizar", "1 tableta aún no sincroniza", "1 tableta perdió la conexión y aún no envía lo que guardó"))

    def test_sin_senales_es_completo_y_sin_equipos_se_dice(self):
        self.assertEqual((integ.resumir([], 5, 0)["estado"], integ.resumir([], 5, 0)["texto"]), ("completa", "Todo sincronizado"))
        self.assertEqual(integ.resumir([], 0, 0)["texto"], "Sin tabletas en este reporte")
        self.assertEqual(integ.resumir([integ.senal("e", cat.COLA_DE_ESTUDIO, 5)], 1, 10)["estado"], "completa")      # la señal ya caducó

    def test_el_total_nunca_es_menor_que_los_equipos_con_pendientes(self):
        self.assertEqual(integ.resumir([integ.senal("e1", cat.COLA_DE_ESTUDIO, 100), integ.senal("e2", cat.COLA_DE_ESTUDIO, 100)], 0, 0)["equipos"], 2)

    def test_avisar_una_vez_por_cambio(self):
        completa = integ.resumir([], 3, 0)
        una = integ.resumir([integ.senal("e1", cat.CONEXION_PERDIDA, 100)], 3, 0)
        otra_causa = integ.resumir([integ.senal("e1", cat.CONEXION_PERDIDA, 100), integ.senal("e2", cat.COLA_DE_ESTUDIO, 100)], 3, 0)
        self.assertTrue(integ.nueva_incompletitud(None, una))
        self.assertTrue(integ.nueva_incompletitud(completa, una))
        self.assertFalse(integ.nueva_incompletitud(una, una))                           # lo mismo de antes: no se vuelve a avisar
        self.assertTrue(integ.nueva_incompletitud(una, otra_causa))                    # un motivo nuevo sí
        self.assertFalse(integ.nueva_incompletitud(otra_causa, una))
        self.assertFalse(integ.nueva_incompletitud(una, completa))                      # volver a completo no es «marcar incompleto»


class PrivacidadTests(SimpleTestCase):
    def test_solo_con_el_umbral_activo_y_menos_de_cinco(self):
        self.assertTrue(priv.aplica(4, True))
        self.assertFalse(priv.aplica(5, True))
        self.assertFalse(priv.aplica(4, False))
        self.assertTrue(priv.aplica(0, True))

    def test_el_bloque_lo_dice_en_lenguaje_llano(self):
        b = priv.bloque(3, True)
        self.assertEqual((b["umbral_activo"], b["aplicada"], b["minimo"], b["alumnos"]), (True, True, 5, 3))
        self.assertIn("3 alumnos, menos de 5", b["aviso"])
        self.assertEqual(priv.bloque(1, True)["aviso"][:23], "Este reporte abarca 1 a")
        self.assertEqual(priv.bloque(30, True)["aviso"], "")


class ArchivoTests(SimpleTestCase):
    def test_ningun_caracter_que_fat32_o_ntfs_rechacen(self):
        sucio = 'reporte: "8A" <grupo>/alumno\\a|b?c*d'
        limpio = arch.sanear(sucio, "xlsx")
        self.assertEqual(limpio, "reporte-8A-grupo-alumno-a-b-c-d.xlsx")
        self.assertFalse(set(limpio) & set('\\/:*?"<>|'))
        self.assertFalse(any(ord(c) < 32 for c in arch.sanear("a\tb\x00c\nd", "csv")))

    def test_sin_espacios_ni_puntos_al_final_ni_nombres_reservados(self):
        self.assertEqual(arch.sanear("reporte. . ", "xlsx"), "reporte.xlsx")
        for reservado in ("CON", "prn", "Aux", "NUL", "COM1", "lpt9"):
            self.assertTrue(arch.sanear(reservado, "csv").startswith("reporte-"), reservado)
        self.assertEqual(arch.sanear("", "csv"), "reporte.csv")
        self.assertEqual(arch.sanear("   ", "csv", respaldo="uso"), "uso.csv")
        self.assertEqual(arch.sanear("x", ".XLSX"), "x.xlsx")

    def test_a_lo_sumo_cien_unidades_con_la_extension_y_sin_partir_un_emoji(self):
        largo = arch.sanear("a" * 300, "xlsx")
        self.assertEqual((len(largo), largo[-5:]), (100, ".xlsx"))
        emojis = arch.sanear("😀" * 80, "xlsx")
        self.assertLessEqual(len(emojis.encode("utf-16-le")) // 2, 100)
        self.assertTrue(emojis.endswith(".xlsx"))
        self.assertEqual(set(emojis[:-5]), {"😀"})                                          # sólo emojis completos: ningún par sustituto partido por la mitad
        emojis.encode("utf-16-le")                                                           # y se puede codificar sin errores

    def test_es_determinista_y_conserva_tildes_y_enie(self):
        self.assertEqual(arch.sanear("Reporte señor Ávila", "csv"), arch.sanear("Reporte señor Ávila", "csv"))
        self.assertEqual(arch.sanear("Reporte señor Ávila", "csv"), "Reporte señor Ávila.csv")
        self.assertEqual(arch.sanear("Café", "csv"), "Café.csv")                                # NFC

    def test_el_nombre_del_reporte_lleva_tipo_sujeto_y_corte_local(self):
        corte = datetime(2026, 10, 15, 10, 42, tzinfo=timezone(timedelta(hours=-5)))
        self.assertEqual(arch.nombre_del_reporte("grupo", "8A", corte, "xlsx"), "reporte-grupo-8A-2026-10-15-1042.xlsx")
        self.assertEqual(arch.nombre_del_reporte("uso", "", corte, "csv"), "reporte-uso-2026-10-15-1042.csv")
        self.assertEqual(arch.nombre_del_reporte("grupo", "8/A:", corte, "xlsx"), "reporte-grupo-8-A-2026-10-15-1042.xlsx")

    def test_la_huella_es_el_sha256_de_los_bytes(self):
        self.assertEqual(arch.huella(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_la_politica_del_administrador_cierra_solo_los_extraibles(self):
        self.assertTrue(arch.destino_permitido(cat.EXTRAIBLE, True))
        self.assertFalse(arch.destino_permitido(cat.EXTRAIBLE, False))
        self.assertTrue(arch.destino_permitido(cat.CARPETA_LOCAL, False))
        self.assertTrue(arch.destino_permitido(cat.RED, False))
        self.assertFalse(arch.destino_permitido("nube", True))


def detalle_de_clase(**cambios) -> dict:
    """Lo que entrega el aula de una clase cerrada: tres participantes, dos actividades; Ana entrega todo bien, Beto una sola y Cora nada."""
    d = {
        "sesion": {"id": "s1", "grupo_id": "g1", "profesor_id": "p1", "estado": "cerrada", "curso_ref": "c", "leccion_ref": "l", "iniciada_en": 1_000, "finalizada_en": 3_601_000, "creado_en": 900},
        "participantes": [
            {"id": "pa", "persona_id": "ana", "estado": "salio", "presencia_al_cerrar": "conectado", "ingreso": 1_000, "salida": 3_601_000, "dispositivo_id": "t1"},
            {"id": "pb", "persona_id": "beto", "estado": "salio", "presencia_al_cerrar": "conectado", "ingreso": 2_000, "salida": 3_601_000, "dispositivo_id": "t2"},
            {"id": "pc", "persona_id": "cora", "estado": "salio", "presencia_al_cerrar": "conectado", "ingreso": 3_000, "salida": 3_601_000, "dispositivo_id": "t3"},
            {"id": "pd", "persona_id": "dani", "estado": "esperando", "presencia_al_cerrar": "esperando", "ingreso": 4_000, "salida": None, "dispositivo_id": "t4"}],
        "actividades": [{"distribucion_id": "d1", "destinatarios": ["pa", "pb", "pc"]}, {"distribucion_id": "d2", "destinatarios": ["pa", "pb", "pc"]}],
        "intentos": [
            {"distribucion_id": "d1", "participante_id": "pa", "numero": 1, "estado": "entregado", "puntaje": 9.0, "puntaje_maximo": 9.0, "calificadas": 5, "aciertos": 5, "origen_envio": "directo", "recuperado_de_cola": False},
            {"distribucion_id": "d2", "participante_id": "pa", "numero": 1, "estado": "entregado", "puntaje": 3.0, "puntaje_maximo": 6.0, "calificadas": 3, "aciertos": 1, "origen_envio": "cola", "recuperado_de_cola": True},
            {"distribucion_id": "d1", "participante_id": "pb", "numero": 1, "estado": "entregado", "puntaje": 0.0, "puntaje_maximo": 9.0, "calificadas": 5, "aciertos": 0, "origen_envio": "directo", "recuperado_de_cola": False}]}
    d.update(cambios)
    return d


class ClaseDominioTests(SimpleTestCase):
    def test_una_clase_que_no_ha_terminado_no_tiene_reporte(self):
        d = detalle_de_clase()
        d["sesion"] = {**d["sesion"], "estado": "abierta", "finalizada_en": None}
        self.assertIsNone(clase_dom.resumir(d, 0))

    def test_solo_cuenta_quien_entro_de_verdad(self):
        r = clase_dom.resumir(detalle_de_clase(), 4_000_000)
        self.assertEqual([a["alumno_id"] for a in r["alumnos"]], ["ana", "beto", "cora"])                 # dani sólo esperaba: no es un participante
        self.assertEqual(r["clase"]["participantes"], 3)
        self.assertEqual(r["clase"]["equipos"], 3)

    def test_participacion_y_aciertos_por_puntos_y_sin_cifra_cuando_no_hay_datos(self):
        r = clase_dom.resumir(detalle_de_clase(), 4_000_000)
        ana, beto, cora = r["alumnos"]
        self.assertEqual((ana["actividades_recibidas"], ana["actividades_entregadas"], ana["porcentaje_participacion"], ana["porcentaje_aciertos"]), (2, 2, Decimal("100.00"), Decimal("80.00")))
        self.assertEqual((ana["aciertos"], ana["calificadas"], ana["entregas_por_cola"]), (6, 8, 1))        # 12 de 15 puntos = 80 %
        self.assertEqual((beto["actividades_entregadas"], beto["porcentaje_participacion"], beto["porcentaje_aciertos"]), (1, Decimal("50.00"), Decimal("0.00")))
        self.assertEqual((cora["actividades_entregadas"], cora["porcentaje_participacion"], cora["porcentaje_aciertos"]), (0, Decimal("0.00"), None))       # sin entregar NO es un 0 % de aciertos
        self.assertEqual(r["clase"]["promedio_participacion"], Decimal("50.00"))                           # (100 + 50 + 0) / 3
        self.assertEqual(r["clase"]["promedio_aciertos"], Decimal("40.00"))                                # (80 + 0) / 2: cora no cuenta
        self.assertEqual((r["clase"]["duracion_ms"], ana["presente_ms"], r["clase"]["actividades"]), (3_600_000, 3_600_000, 2))

    def test_una_clase_sin_actividades_no_tiene_promedios(self):
        r = clase_dom.resumir(detalle_de_clase(actividades=[], intentos=[]), 4_000_000)
        self.assertEqual((r["clase"]["promedio_participacion"], r["clase"]["promedio_aciertos"]), (None, None))
        self.assertTrue(all(a["porcentaje_participacion"] is None for a in r["alumnos"]))

    def test_se_cuenta_el_ultimo_intento_entregado(self):
        d = detalle_de_clase()
        d["intentos"] = [{"distribucion_id": "d1", "participante_id": "pa", "numero": 1, "estado": "entregado", "puntaje": 1.0, "puntaje_maximo": 9.0, "calificadas": 5, "aciertos": 1},
                         {"distribucion_id": "d1", "participante_id": "pa", "numero": 2, "estado": "entregado", "puntaje": 9.0, "puntaje_maximo": 9.0, "calificadas": 5, "aciertos": 5},
                         {"distribucion_id": "d1", "participante_id": "pa", "numero": 3, "estado": "en_curso", "puntaje": None, "puntaje_maximo": None, "calificadas": 0, "aciertos": 0}]
        ana = clase_dom.resumir(d, 4_000_000)["alumnos"][0]
        self.assertEqual((ana["actividades_entregadas"], ana["porcentaje_aciertos"]), (1, Decimal("100.00")))

    def test_la_integracion_mira_la_presencia_de_antes_del_cierre_y_caduca_con_la_gracia(self):
        d = detalle_de_clase()
        d["participantes"][1] = {**d["participantes"][1], "presencia_al_cerrar": "reconectando"}
        d["intentos"].append({"distribucion_id": "d2", "participante_id": "pb", "numero": 1, "estado": "en_curso", "puntaje": None, "puntaje_maximo": None, "calificadas": 0, "aciertos": 0})
        fin = 3_601_000
        r = clase_dom.resumir(d, fin + 60_000)
        self.assertEqual(r["clase"]["estado_integracion"], "incompleta")
        self.assertEqual(sorted((s["equipo"], s["motivo"]) for s in r["clase"]["senales"]), [("t2", "conexion_perdida"), ("t2", "entrega_pendiente")])
        self.assertEqual({s["hasta_en"] for s in r["clase"]["senales"]}, {fin + 15 * 60_000})
        despues = clase_dom.resumir(d, fin + 15 * 60_000 + 1)
        self.assertEqual((despues["clase"]["estado_integracion"], despues["clase"]["senales"]), ("completa", []))
        self.assertEqual(r["alumnos"][1]["estado"], "reconectando")                                          # la presencia que se reporta es la de antes del barrido de cierre

    def test_misma_clase_misma_huella_y_un_cambio_la_cambia(self):
        a = clase_dom.resumir(detalle_de_clase(), 4_000_000)["clase"]["huella"]
        b = clase_dom.resumir(detalle_de_clase(), 9_000_000)["clase"]["huella"]
        self.assertEqual(a, b)                                                                              # pasa el tiempo y no cambia lo que se guarda
        d = detalle_de_clase()
        d["intentos"][0] = {**d["intentos"][0], "puntaje": 8.0}
        self.assertNotEqual(a, clase_dom.resumir(d, 4_000_000)["clase"]["huella"])


def detalle_de_alumno() -> dict:
    return {"clases": [{"sesion_id": "s1", "curso_ref": "c1", "finalizada_en": 100, "asistio": True, "recibidas": 2, "entregadas": 2, "puntos": 9, "puntos_maximos": 18},
                       {"sesion_id": "s2", "curso_ref": "c2", "finalizada_en": 200, "asistio": False, "recibidas": 0, "entregadas": 0, "puntos": 0, "puntos_maximos": 0},
                       {"sesion_id": "s3", "curso_ref": "c1", "finalizada_en": 300, "asistio": True, "recibidas": 1, "entregadas": 0, "puntos": 0, "puntos_maximos": 0}],
            "evaluaciones": [{"asignacion_id": "e1", "curso_ref": "c1", "presento": True, "sin_presentar": False, "ultima_en": 150},
                             {"asignacion_id": "e2", "curso_ref": "c2", "presento": False, "sin_presentar": True, "ultima_en": None}],
            "estudios": [{"asignacion_id": "t1", "curso_ref": "c1", "avance_pct": 100, "completada": True, "vencida": False, "ultima_en": 400},
                         {"asignacion_id": "t2", "curso_ref": "c2", "avance_pct": 20, "completada": False, "vencida": True, "ultima_en": None}]}


class AvanceDominioTests(SimpleTestCase):
    def test_resumen_de_un_alumno(self):
        s = av.resumir(detalle_de_alumno())
        self.assertEqual((s["clases_total"], s["clases_asistidas"], s["porcentaje_asistencia"]), (3, 2, Decimal("66.67")))
        self.assertEqual((s["actividades_recibidas"], s["actividades_entregadas"], s["porcentaje_participacion"]), (3, 2, Decimal("66.67")))
        self.assertEqual(s["porcentaje_aciertos"], Decimal("50.00"))
        self.assertEqual((s["evaluaciones_total"], s["evaluaciones_presentadas"], s["evaluaciones_sin_presentar"]), (2, 1, 1))
        self.assertEqual((s["estudios_total"], s["estudios_completados"], s["estudios_vencidos"], s["avance_estudio"]), (2, 1, 1, Decimal("60.00")))
        self.assertEqual(s["ultima_actividad_en"], 400)
        self.assertEqual([m["codigo"] for m in s["atencion"]], ["evaluaciones_sin_presentar", "estudio_vencido"])

    def test_filtrar_por_los_cursos_de_un_nodo_recalcula_todo_con_lo_que_queda(self):
        s = av.resumir(detalle_de_alumno(), {"c1"})
        self.assertEqual((s["clases_total"], s["clases_asistidas"], s["evaluaciones_total"], s["evaluaciones_sin_presentar"], s["estudios_total"], s["estudios_vencidos"]), (2, 2, 1, 0, 1, 0))
        self.assertEqual(s["atencion"], [])
        vacio = av.resumir(detalle_de_alumno(), set())
        self.assertEqual((vacio["clases_total"], vacio["porcentaje_asistencia"], vacio["porcentaje_aciertos"], vacio["avance_estudio"]), (0, None, None, None))

    def test_un_alumno_sin_nada_no_tiene_cifras_ni_motivos(self):
        s = av.resumir({})
        self.assertEqual((s["clases_total"], s["porcentaje_participacion"], s["atencion"], s["ultima_actividad_en"]), (0, None, [], None))

    def test_el_motivo_de_una_linea_dice_cuantos_mas_hay(self):
        s = av.resumir(detalle_de_alumno())
        self.assertEqual(av.motivo_de_atencion(s), "No presentó 1 evaluación (y 1 más)")
        self.assertEqual(av.motivo_de_atencion(av.resumir({})), "")
        self.assertTrue(av.necesita_atencion(s))

    def test_quien_necesita_atencion_va_primero_y_los_demas_por_nombre_sin_tildes(self):
        filas = [{"alumno_id": "1", "alumno": "Zoe", "atencion": []}, {"alumno_id": "2", "alumno": "Álvaro", "atencion": []},
                 {"alumno_id": "3", "alumno": "Ñoño", "atencion": [{"codigo": "x"}]}, {"alumno_id": "4", "alumno": "Beto", "atencion": [{"codigo": "x"}, {"codigo": "y"}]}]
        self.assertEqual([f["alumno"] for f in av.ordenar_por_atencion(filas)], ["Beto", "Ñoño", "Álvaro", "Zoe"])


class TextoTests(SimpleTestCase):
    def test_fechas_y_duraciones_en_espanol_claro(self):
        dt = datetime(2026, 10, 15, 10, 42, tzinfo=timezone.utc)
        self.assertEqual(tx.fecha_corta(dt), "15 oct · 10:42")
        self.assertEqual(tx.fecha_larga(dt), "15 oct 2026 · 10:42")
        self.assertEqual([tx.duracion(x) for x in (None, 0, 59_999, 60_000, 2_520_000, 3_900_000, 7_200_000)], ["", "menos de 1 min", "menos de 1 min", "1 min", "42 min", "1 h 05 min", "2 h 00 min"])
        self.assertEqual((tx.minutos(None), tx.minutos(90_000), tx.minutos(-5)), (None, 1.5, 0.0))

    def test_la_linea_de_corte_solo_anuncia_lo_pendiente(self):
        dt = datetime(2026, 10, 15, 10, 42, tzinfo=timezone.utc)
        self.assertEqual(tx.linea_de_corte(dt, integ.resumir([], 3, 0)), "Datos al 15 oct · 10:42")
        dos = integ.resumir([integ.senal("a", cat.COLA_DE_ESTUDIO, 9), integ.senal("b", cat.COLA_DE_ESTUDIO, 9)], 3, 0)
        self.assertEqual(tx.linea_de_corte(dt, dos), "Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar")

    def test_la_clave_de_orden_ignora_tildes_y_mayusculas(self):
        self.assertEqual(sorted(["Zoe", "Álvaro", "ana", "Ñoño", "Beto"], key=tx.clave_de_orden), ["Álvaro", "ana", "Beto", "Ñoño", "Zoe"])


class DocumentoTests(SimpleTestCase):
    def reporte_de_grupo(self, con_alumnos=True) -> dict:
        return {"tipo": "grupo", "titulo": "Reporte del grupo", "nominal": con_alumnos, "grupo": {"id": "g", "codigo": "8A", "nombre": "Octavo A", "periodo": "2026"},
                "corte": {"en": 1, "integracion": {"estado": "incompleta", "texto": "2 tabletas sin sincronizar", "motivos": [{"codigo": "x", "texto": "2 tabletas guardan trabajo de estudio por enviar"}]}},
                "privacidad": {"aplicada": not con_alumnos, "aviso": "Menos de 5 alumnos."}, "objetivos": {"disponible": False}, "modo": "simple",
                "totales": {"alumnos": 2, "clases": 1, "evaluaciones": 0, "estudios": 0, "en_atencion": 1, "promedio_participacion": 75, "promedio_aciertos": None},
                "alumnos": [{"alumno": "Ana", "clases_asistidas": 1, "clases_total": 1, "porcentaje_participacion": 100, "porcentaje_aciertos": 80.5, "evaluaciones_presentadas": 0,
                             "evaluaciones_total": 0, "evaluaciones_sin_presentar": 0, "estudios_completados": 0, "estudios_total": 0, "atencion": [], "motivo": ""}] if con_alumnos else [],
                "clases": [{"finalizada_en": 5, "curso_rotulo": "Estados", "leccion_rotulo": "Tres estados", "participantes": 2, "promedio_participacion": 75, "promedio_aciertos": None, "incompleta": True}],
                "evaluaciones": []}

    def contexto(self) -> dict:
        return {"titulo": "Reporte del grupo", "generado_por": "Prof. Gómez", "generado_el": "15 oct 2026 · 10:50", "corte_texto": "15 oct 2026 · 10:42 (hora del nodo)",
                "version_nodo": "2.8.0", "fecha": lambda ms: f"t{ms}"}

    def test_la_cabecera_lleva_lo_que_exige_br_083_y_el_resumen_lo_que_se_ve(self):
        d = doc.de_reporte("grupo", self.reporte_de_grupo(), self.contexto())
        self.assertEqual([e for e, _ in d.cabecera], ["Reporte", "Grupo", "Periodo", "Generado por", "Generado el", "Datos al corte", "Estado de integración", "Umbral de privacidad aplicado", "Versión del nodo"])
        c = dict(d.cabecera)
        self.assertEqual((c["Grupo"], c["Periodo"], c["Umbral de privacidad aplicado"], c["Versión del nodo"]), ("Octavo A", "2026", "No", "2.8.0"))
        self.assertIn("Esto es lo que había en el nodo a esa hora.", c["Datos al corte"])
        self.assertEqual(c["Estado de integración"], "2 tabletas sin sincronizar (2 tabletas guardan trabajo de estudio por enviar)")
        self.assertEqual((d.sujeto, d.nominal, d.filas), ("8A", True, 2))
        self.assertEqual([t.nombre for t in d.tablas], ["Alumnos", "Clases"])
        self.assertIn("Este archivo incluye nombres de alumnos. Una vez fuera del equipo del colegio, quien lo guarda es responsable de quién lo abre.", d.notas)
        self.assertIn("Dominio por objetivo: aún no disponible.", d.notas)

    def test_con_la_privacidad_aplicada_no_hay_tabla_de_alumnos_y_se_dice(self):
        d = doc.de_reporte("grupo", self.reporte_de_grupo(con_alumnos=False), self.contexto())
        self.assertEqual([t.nombre for t in d.tablas], ["Clases"])
        self.assertEqual(dict(d.cabecera)["Umbral de privacidad aplicado"], "Sí")
        self.assertIn("Menos de 5 alumnos.", d.notas)
        self.assertIn("Este archivo no incluye datos de personas.", d.notas)
        self.assertFalse(d.nominal)
