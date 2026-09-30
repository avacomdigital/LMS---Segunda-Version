"""
Abrir la lección asignada, reanudarla, registrar el avance por bloques (monótono) y completarla solo cuando se atendieron todos los
obligatorios (FUN-082, FUN-087, FUN-088, D-4). La lección se lee EN VIVO, sin claves, con los medios apuntando a las rutas de este módulo; el
avance pasa al expediente; y una asignación cerrada se puede leer pero no admite avance.
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

from django.conf import settings
from django.test import override_settings

from classroom_engine.dominio import curso as curso_aula
from expediente.models import Auditoria, ProgresoLeccion

from .. import models as m
from ..dominio.errores import FuenteNoDisponible
from ..infraestructura.contenedor import ContenidoAula
from .base import BASE, BLOQUES_L1, CURSO, LECCION_1, BaseEstudio


class AbrirLeccionTests(BaseEstudio):
    def test_abrir_la_leccion_trae_la_vista_de_aula_sin_claves_y_crea_la_tarea(self):
        a = self.crear_asignacion()
        r = self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
        self.assertEqual(set(r), {"asignacion", "curso", "leccion", "bloques", "reanudar", "servidor_en"})
        self.assertIsNone(curso_aula.contiene_clave(r))                           # ninguna clave de corrección, para nadie
        self.assertEqual((r["curso"]["curso_ref"], r["curso"]["version"], r["curso"]["portada_url"]), (CURSO, "1.0.0", None))
        self.assertEqual((r["leccion"]["leccion_ref"], [o["tipo"] for o in r["leccion"]["objetos"]]),
                         (LECCION_1, ["lecture", "explanation", "simulation_lab", "activity"]))
        self.assertEqual([b["ref"] for b in r["bloques"]], BLOQUES_L1)
        self.assertFalse(any(b["atendido"] for b in r["bloques"]))
        self.assertEqual(r["reanudar"], {"bloque_ref": None, "indice": None, "posicion_seg": None, "puede": False})
        tarea = r["asignacion"]["tarea"]
        self.assertEqual((tarea["estado"], tarea["avance_pct"], tarea["bloques_total"], tarea["bloques_atendidos"], tarea["puede_reanudar"]), ("en_curso", 0.0, 7, 0, False))
        self.assertIsNotNone(tarea["abierta_en"])
        fila = m.Tarea.objects.get(asignacion_id=a["id"], alumno_id=self.estudiante_id)
        self.assertEqual((fila.estado, float(fila.avance_pct), fila.abierta_en is not None), ("en_curso", 0.0, True))
        self.assertEqual(self.eventos("estudio.leccion.abierta.v1"), ["estudio.leccion.abierta.v1"])
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.leccion.abierta.v1").carga
        self.assertEqual((carga["asignacion_id"], carga["alumno_id"], carga["curso_ref"], carga["leccion_ref"]), (a["id"], self.estudiante_id, CURSO, LECCION_1))

    def test_abrir_otra_vez_no_repite_el_evento_ni_duplica_la_tarea(self):
        a = self.crear_asignacion()
        self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
        self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
        self.assertEqual(len(self.eventos("estudio.leccion.abierta.v1")), 1)
        self.assertEqual(m.Tarea.objects.filter(asignacion_id=a["id"]).count(), 1)

    def test_los_medios_de_la_leccion_apuntan_a_las_rutas_de_este_modulo(self):
        a = self.crear_asignacion()
        r = self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
        texto = json.dumps(r["leccion"])
        self.assertIn(f"/api/modo-estudio/asignaciones/{a['id']}/medios/img-particles/?dispositivo={self.hw_juan}", texto)
        self.assertNotIn("/api/aula/", texto)
        self.assertNotIn("/api/biblioteca/", texto)

    def test_una_asignacion_de_otro_grupo_o_inexistente_no_se_abre(self):
        b = self.crear_asignacion(grupo_id=self.otro_grupo["id"])
        self.assertEqual(self.ver(f"/lecciones/{b['id']}/").status_code, 404)
        self.assertEqual(self.ver("/lecciones/no-existe/").status_code, 404)
        self.assertEqual(m.Tarea.objects.count(), 0)

    def test_sin_biblioteca_la_leccion_es_503_y_no_deja_tarea_ni_evento_pero_la_lista_sigue(self):
        a = self.crear_asignacion()
        with mock.patch.object(ContenidoAula, "leccion", side_effect=FuenteNoDisponible("Biblioteca cerrada.", sugerencia="Abre AVACOM Contenido.")):
            r = self.ver(f"/lecciones/{a['id']}/")
            self.assertEqual((r.status_code, r.json()["codigo"], r.json()["disponible"], r.json()["sugerencia"]),
                             (503, "fuente_no_disponible", False, "Abre AVACOM Contenido."))
            self.assertEqual(len(self.json_ok(self.ver("/asignaciones/"))["asignaciones"]), 1)
        self.assertEqual((m.Tarea.objects.count(), self.eventos("estudio.leccion.abierta.v1")), (0, []))

    def test_una_asignacion_cerrada_se_lee_pero_no_se_empieza(self):
        a = self.crear_asignacion()
        self.api.post(f"{BASE}/docente/asignaciones/{a['id']}/cerrar/", {}, format="json")
        r = self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
        self.assertEqual((r["asignacion"]["estado_asignacion"], r["asignacion"]["tarea"]), ("cerrada", None))
        self.assertEqual((m.Tarea.objects.count(), self.eventos("estudio.leccion.abierta.v1")), (0, []))

    def test_si_el_curso_cambia_de_version_la_estructura_se_rehace_conservando_lo_visto(self):
        a = self.crear_asignacion()
        self.json_ok(self.bloques(a["id"], ["l1-lecture:l1-lecture-s1", "l1-lecture:l1-lecture-s3", "l1-activity"], bloque_actual="l1-lecture:l1-lecture-s3"))
        with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
            curso = json.load(f)
        curso["version"] = "1.1.0"
        laminas = next(o for l in curso["lessons"] if l["id"] == LECCION_1 for o in l["objects"] if o["id"] == "l1-lecture")["slides"]
        laminas[:] = [s for s in laminas if s["id"] != "l1-lecture-s3"] + [
            {"id": "l1-lecture-s4", "title": "Nueva lámina", "blocks": [{"type": "text", "text": "Algo nuevo."}]}]
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "example.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(curso, f)
            with override_settings(AVACOM_AULA_CURSO_EJEMPLO=ruta):
                r = self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
        refs = [b["ref"] for b in r["bloques"]]
        self.assertEqual(refs, ["l1-lecture:l1-lecture-s1", "l1-lecture:l1-lecture-s2", "l1-lecture:l1-lecture-s4", *BLOQUES_L1[3:]])
        self.assertEqual([b["ref"] for b in r["bloques"] if b["atendido"]], ["l1-lecture:l1-lecture-s1", "l1-activity"])   # la lámina 3 ya no existe
        fila = m.Asignacion.objects.get(pk=a["id"])
        self.assertEqual((fila.curso_version, len(fila.bloques)), ("1.1.0", 7))
        tarea = m.Tarea.objects.get(asignacion_id=a["id"])
        self.assertEqual((tarea.bloques_vistos, tarea.ultimo_bloque_ref, float(tarea.avance_pct)), (["l1-lecture:l1-lecture-s1", "l1-activity"], "", 28.57))


class ProgresoTests(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()

    def test_registrar_bloques_es_monotono_y_recalcula_el_avance(self):
        r = self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:1]))
        self.assertEqual((r["aceptados"], r["desconocidos"]), (BLOQUES_L1[:1], []))
        self.assertEqual((r["tarea"]["avance_pct"], r["tarea"]["bloques_atendidos"], r["tarea"]["estado"]), (14.29, 1, "en_curso"))
        r = self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:3]))
        self.assertEqual((r["tarea"]["avance_pct"], r["tarea"]["bloques_atendidos"]), (42.86, 3))
        r = self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:1]))                    # un aparato atrasado no desatiende lo ya atendido
        self.assertEqual((r["tarea"]["avance_pct"], r["tarea"]["bloques_atendidos"]), (42.86, 3))
        self.assertEqual(m.Tarea.objects.get(asignacion_id=self.a["id"]).bloques_vistos, BLOQUES_L1[:3])

    def test_una_referencia_que_no_existe_se_informa_y_no_se_guarda(self):
        r = self.json_ok(self.bloques(self.a["id"], [BLOQUES_L1[0], "l1-lecture:no-existe"]))
        self.assertEqual((r["aceptados"], r["desconocidos"]), ([BLOQUES_L1[0]], ["l1-lecture:no-existe"]))
        self.assertEqual(m.Tarea.objects.get(asignacion_id=self.a["id"]).bloques_vistos, [BLOQUES_L1[0]])

    def test_el_bloque_actual_y_su_posicion_son_el_punto_de_reanudacion(self):
        r = self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:3], bloque_actual=BLOQUES_L1[3], posicion_seg=208))
        self.assertEqual(r["tarea"]["ultimo_bloque"], {"ref": BLOQUES_L1[3], "indice": 4, "titulo": "Resumen", "tipo": "pagina", "posicion_seg": 208})
        self.assertTrue(r["tarea"]["puede_reanudar"])
        leccion = self.json_ok(self.ver(f"/lecciones/{self.a['id']}/"))
        self.assertEqual(leccion["reanudar"], {"bloque_ref": BLOQUES_L1[3], "indice": 4, "posicion_seg": 208, "puede": True})
        self.assertEqual([b["ref"] for b in leccion["bloques"] if b["atendido"]], BLOQUES_L1[:3])
        # mover sólo la posición dentro del mismo bloque, y cambiar de bloque reinicia la posición
        r = self.json_ok(self.enviar("patch", f"/lecciones/{self.a['id']}/progreso/", {"posicion_seg": 250}))
        self.assertEqual(r["tarea"]["ultimo_bloque"]["posicion_seg"], 250)
        r = self.json_ok(self.enviar("patch", f"/lecciones/{self.a['id']}/progreso/", {"bloque_actual": BLOQUES_L1[4]}))
        self.assertEqual((r["tarea"]["ultimo_bloque"]["ref"], r["tarea"]["ultimo_bloque"]["posicion_seg"]), (BLOQUES_L1[4], None))
        r = self.json_ok(self.enviar("patch", f"/lecciones/{self.a['id']}/progreso/", {"bloque_actual": "no-existe"}))
        self.assertEqual(r["desconocidos"], ["no-existe"])

    def test_si_ya_atendio_algo_pero_no_dejo_marca_se_retoma_en_el_primer_bloque_sin_atender(self):
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:2]))
        leccion = self.json_ok(self.ver(f"/lecciones/{self.a['id']}/"))
        self.assertEqual(leccion["reanudar"], {"bloque_ref": BLOQUES_L1[2], "indice": 3, "posicion_seg": None, "puede": True})

    def test_el_avance_pasa_al_expediente_y_es_monotono_alli_tambien(self):
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:3]))
        fila = ProgresoLeccion.objects.get(curso_ref=CURSO, persona_id=self.estudiante_id, leccion_codigo=LECCION_1)
        self.assertEqual((float(fila.porcentaje), fila.estado, fila.leccion_rotulo), (42.86, "en_curso", "Los tres estados de la materia"))
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:5]))
        self.assertEqual(float(ProgresoLeccion.objects.get(pk=fila.pk).porcentaje), 71.43)

    def test_lo_mal_formado_es_400_y_una_asignacion_cerrada_es_409(self):
        for cuerpo in ({"bloques_vistos": "l1"}, {"posicion_seg": -3}, {"posicion_seg": "a mitad"}, {"capturado_en": -1}):
            with self.subTest(cuerpo=cuerpo):
                r = self.enviar("patch", f"/lecciones/{self.a['id']}/progreso/", cuerpo)
                self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.api.post(f"{BASE}/docente/asignaciones/{self.a['id']}/cerrar/", {}, format="json")
        r = self.bloques(self.a["id"], BLOQUES_L1[:1])
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))
        self.assertEqual(m.Tarea.objects.count(), 0)

    def test_lo_avanzado_despues_de_la_fecha_limite_con_plazo_blando_se_acepta_marcado(self):
        con_fecha = self.crear_asignacion(LECCION_1, fecha_limite=1_000_000)
        with self.reloj(500_000):
            r = self.json_ok(self.bloques(con_fecha["id"], BLOQUES_L1[:1]))
        self.assertEqual((r["tarea"]["fuera_de_plazo"], r["tarea"]["vencida"]), (False, False))
        with self.reloj(2_000_000):
            r = self.json_ok(self.bloques(con_fecha["id"], BLOQUES_L1[:2]))
        self.assertEqual((r["tarea"]["fuera_de_plazo"], r["tarea"]["vencida"], r["tarea"]["bloques_atendidos"]), (True, True, 2))
        with self.reloj(500_000):                      # la marca no se quita: sigue siendo trabajo fuera de plazo
            r = self.json_ok(self.bloques(con_fecha["id"], BLOQUES_L1[:3]))
        self.assertTrue(r["tarea"]["fuera_de_plazo"])

    def test_con_plazo_endurecido_lo_capturado_despues_del_cierre_se_rechaza_en_linea(self):
        dura = self.crear_asignacion(LECCION_1, fecha_limite=1_000_000, plazo="endurecido", gracia_min=1)
        with self.reloj(500_000):
            self.json_ok(self.bloques(dura["id"], BLOQUES_L1[:1]))
        with self.reloj(2_000_000):
            r = self.bloques(dura["id"], BLOQUES_L1[:2])
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (409, "asignacion_cerrada", "plazo_vencido"))
        with self.reloj(1_030_000):                    # capturado antes, recibido dentro de la gracia: se acepta
            r = self.json_ok(self.bloques(dura["id"], BLOQUES_L1[:2], capturado_en=990_000))
        self.assertEqual(r["tarea"]["bloques_atendidos"], 2)
        with self.reloj(9_000_000):                    # capturado antes pero recibido después de la gracia: en línea no hay a quién preguntar
            r = self.bloques(dura["id"], BLOQUES_L1[:3], capturado_en=990_000)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["recepcion"]), (409, "asignacion_cerrada", "decide_el_profesor"))


class CompletarTests(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()

    def completar(self):
        return self.enviar("post", f"/lecciones/{self.a['id']}/completar/")

    def test_sin_todos_los_obligatorios_es_409_y_dice_cuales_faltan(self):
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:5]))
        r = self.completar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "bloques_pendientes"))
        self.assertEqual(r.json()["faltan"], [{"ref": "l1-lab-phet", "indice": 6, "titulo": "Laboratorio: partículas en movimiento"},
                                             {"ref": "l1-activity", "indice": 7, "titulo": "Practica: los tres estados"}])
        self.assertEqual(m.Tarea.objects.get(asignacion_id=self.a["id"]).estado, "en_curso")
        self.assertEqual(self.eventos("estudio.leccion.completada.v1"), [])

    def test_sin_ningun_bloque_atendido_faltan_todos(self):
        r = self.completar()
        self.assertEqual((r.status_code, len(r.json()["faltan"])), (409, 7))
        self.assertEqual(m.Tarea.objects.count(), 0)          # no se completó nada: no queda ni la tarea

    def test_con_todos_atendidos_se_completa_se_sella_en_el_expediente_y_es_idempotente(self):
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1))
        with self.reloj(5_000_000):
            r = self.json_ok(self.completar())
        tarea = r["tarea"]
        self.assertEqual((tarea["estado"], tarea["avance_pct"], tarea["completada_en"], tarea["bloques_atendidos"], tarea["fuera_de_plazo"]), ("completada", 100.0, 5_000_000, 7, False))
        self.assertEqual(self.eventos("estudio.leccion.completada.v1"), ["estudio.leccion.completada.v1"])
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.leccion.completada.v1").carga
        self.assertEqual((carga["asignacion_id"], carga["alumno_id"], carga["leccion_ref"], carga["fuera_de_plazo"], carga["origen"]),
                         (self.a["id"], self.estudiante_id, LECCION_1, False, "directo"))
        fila = ProgresoLeccion.objects.get(curso_ref=CURSO, persona_id=self.estudiante_id, leccion_codigo=LECCION_1)
        self.assertEqual((float(fila.porcentaje), fila.estado), (100.0, "completada"))
        self.assertTrue(Auditoria.objects.filter(accion="estudio.leccion.completada", actor_id=self.estudiante_id).exists())
        again = self.json_ok(self.completar())
        self.assertEqual(again["tarea"]["completada_en"], 5_000_000)
        self.assertEqual(len(self.eventos("estudio.leccion.completada.v1")), 1)
        resumen = self.json_ok(self.ver("/asignaciones/"))["resumen"]
        self.assertEqual(resumen, {"pendientes": 0, "descargadas": 0, "completadas": 1})

    def test_ni_una_asignacion_cerrada_impide_repetir_lo_ya_completado_pero_si_completar_lo_pendiente(self):
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1))
        self.json_ok(self.completar())
        self.api.post(f"{BASE}/docente/asignaciones/{self.a['id']}/cerrar/", {}, format="json")
        self.assertEqual(self.completar().status_code, 200)
        otra = self.crear_asignacion(LECCION_1)
        self.api.post(f"{BASE}/docente/asignaciones/{otra['id']}/cerrar/", {}, format="json")
        r = self.enviar("post", f"/lecciones/{otra['id']}/completar/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))

    def test_completar_fuera_de_plazo_con_plazo_blando_lo_marca(self):
        con_fecha = self.crear_asignacion(LECCION_1, fecha_limite=1_000_000)
        self.json_ok(self.bloques(con_fecha["id"], BLOQUES_L1))
        with self.reloj(3_000_000):
            r = self.json_ok(self.enviar("post", f"/lecciones/{con_fecha['id']}/completar/"))
        self.assertEqual((r["tarea"]["estado"], r["tarea"]["fuera_de_plazo"]), ("completada", True))
        carga = m.EventoSalida.objects.filter(tipo_evento="estudio.leccion.completada.v1").latest("id").carga
        self.assertTrue(carga["fuera_de_plazo"])


class MediosDeLaLeccionTests(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()

    def medio(self, ref: str, hw: str | None = None, ruta: str = "", **cabeceras):
        consulta = {"dispositivo": self.hw_juan if hw is None else hw}
        return self.api.get(f"{BASE}/asignaciones/{self.a['id']}/medios/{ref}/{ruta}", consulta, **cabeceras)

    def test_un_medio_de_la_leccion_se_sirve_con_range(self):
        r = self.medio("img-particles")
        self.assertEqual((r.status_code, r["Content-Type"], r["Accept-Ranges"]), (200, "image/png", "bytes"))
        self.assertTrue(r.content.startswith(b"\x89PNG"))
        parcial = self.medio("img-particles", HTTP_RANGE="bytes=0-7")
        self.assertEqual((parcial.status_code, parcial.content, parcial["Content-Range"].startswith("bytes 0-7/")), (206, b"\x89PNG\r\n\x1a\n", True))
        self.assertEqual(self.api.head(f"{BASE}/asignaciones/{self.a['id']}/medios/img-particles/", {"dispositivo": self.hw_juan}).status_code, 200)

    def test_los_archivos_de_una_simulacion_se_sirven_por_su_ruta(self):
        r = self.medio("sim-phet-states", ruta="states-of-matter-basics_es.html")
        self.assertEqual((r.status_code, r["Content-Type"].split(";")[0]), (200, "text/html"))

    def test_un_medio_que_no_es_de_la_leccion_no_se_sirve(self):
        for ref in ("img-ice-water-steam", "img-cover-matter", "sim-heating-curve", "no-existe"):     # de la lección 2, la portada, otra simulación
            with self.subTest(ref=ref):
                self.assertEqual(self.medio(ref).status_code, 404)

    def test_solo_a_quien_le_alcanza_la_asignacion(self):
        luis, hw_luis = self.alumno_con_tableta("Luis", "400222", grupo_id=self.otro_grupo["id"])
        self.assertEqual(self.medio("img-particles", hw=hw_luis).status_code, 404)
        r = self.api.get(f"{BASE}/asignaciones/{self.a['id']}/medios/img-particles/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))
