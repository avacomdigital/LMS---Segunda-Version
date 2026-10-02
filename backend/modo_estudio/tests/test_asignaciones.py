"""
Asignar trabajo de estudio y ver quién lo completó (CAP-050, CAP-051, FUN-081): a un grupo (también los alumnos que entren después) o a alumnos
sueltos, con fecha límite y plazo blando o endurecido; qué ve cada alumno (sólo lo suyo, activo o completado por él); el detalle del profesor y
su cierre. La lección se lee EN VIVO al asignar y sólo se guardan referencias, rótulos y la estructura de bloques (artículo 14).
"""
from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.test import override_settings

from expediente.models import Auditoria

from .. import models as m
from ..infraestructura.contenedor import ContenidoAula
from ..dominio.errores import FuenteNoDisponible
from .base import BASE, BLOQUES_L1, CURSO, LECCION_1, LECCION_2, LECCION_EXAMEN, BaseEstudio


class GruposDelDocenteTests(BaseEstudio):
    def test_sin_sesion_ve_todos_los_grupos_y_con_sesion_los_suyos(self):
        r = self.json_ok(self.api.get(f"{BASE}/docente/grupos/"))
        self.assertTrue(r["instalado"])
        self.assertEqual({g["codigo"] for g in r["grupos"]}, {"8A", "9B"})
        ocho_a = next(g for g in r["grupos"] if g["codigo"] == "8A")
        self.assertEqual((ocho_a["id"], ocho_a["nombre"], ocho_a["nivel_clave"]), (self.grupo["id"], "Octavo A", None))
        self.assertEqual(ocho_a["alumnos"], [{"id": self.estudiante_id, "rotulo": "Juan P."}])
        propios = self.json_ok(self.docente.get(f"{BASE}/docente/grupos/"))
        self.assertEqual([g["codigo"] for g in propios["grupos"]], ["8A"])
        self.assertEqual({g["codigo"] for g in self.json_ok(self.admin.get(f"{BASE}/docente/grupos/"))["grupos"]}, {"8A", "9B"})

    def test_sin_organizacion_no_hay_grupos(self):
        from acceso.models import Organizacion
        Organizacion.objects.all().delete()
        self.assertEqual(self.json_ok(self.api.get(f"{BASE}/docente/grupos/")), {"instalado": False, "grupos": []})

    def test_un_alumno_no_asigna_trabajo(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = juan.get(f"{BASE}/docente/grupos/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))


class CrearAsignacionTests(BaseEstudio):
    def test_asignar_una_leccion_al_grupo_guarda_referencias_rotulos_y_estructura(self):
        a = self.crear_asignacion()
        self.assertEqual((a["alcance"], a["grupo_id"], a["grupo_rotulo"], a["estado"]), ("grupo", self.grupo["id"], "Octavo A", "activa"))
        self.assertEqual((a["titulo"], a["asignatura"], a["unidad"]), ("Los tres estados de la materia", "Ciencias naturales", "Estados de la materia"))
        self.assertEqual(a["curso"], {"fuente": "ejemplo", "curso_ref": CURSO, "version": "1.0.0", "titulo": "Estados de la materia y sus cambios"})
        self.assertEqual((a["leccion_ref"], a["bloques_total"], a["plazo"], a["gracia_ms"], a["paquete_permitido"]), (LECCION_1, 7, "blando", 900_000, True))
        self.assertEqual(a["practica"], {"objeto_ref": "l1-activity", "titulo": "Practica: los tres estados", "total_preguntas": 6})
        self.assertIsNone(a["evaluacion"])
        self.assertEqual((a["destinatarios_total"], a["completaron"], a["en_curso"], a["pendientes"]), (1, 0, 0, 1))
        self.assertGreater(a["bytes_estimados"], 0)
        fila = m.Asignacion.objects.get(pk=a["id"])
        self.assertEqual([b["ref"] for b in fila.bloques], BLOQUES_L1)
        self.assertEqual([b["indice"] for b in fila.bloques], list(range(1, 8)))
        self.assertEqual({b["tipo"] for b in fila.bloques}, {"lamina", "pagina", "laboratorio", "practica"})
        self.assertEqual((fila.profesor_id, fila.profesor_rotulo, fila.fuente_curso), (self.docente_id, "Prof. Gómez", "ejemplo"))
        self.assertEqual(self.eventos("estudio.asignacion.creada.v1"), ["estudio.asignacion.creada.v1"])
        self.assertTrue(Auditoria.objects.filter(accion="estudio.asignacion.creada", objeto_id=a["id"]).exists())

    def test_la_leccion_2_trae_su_propia_estructura_y_el_examen_no_es_un_bloque(self):
        a = self.crear_asignacion(LECCION_2)
        self.assertEqual(a["bloques_total"], 4)
        self.assertEqual(a["practica"]["total_preguntas"], 3)
        sin_nada = self.crear_asignacion(LECCION_EXAMEN, esperado=400)      # un examen es evaluación formal: aquí no hay nada que estudiar
        self.assertEqual(sin_nada["codigo"], "datos_invalidos")

    def test_fecha_limite_plazo_gracia_consigna_y_paquete_se_guardan(self):
        a = self.crear_asignacion(fecha_limite=1_900_000_000_000, plazo="endurecido", gracia_min=5, consigna="Lee y practica.",
                                  titulo="Repaso de la materia", paquete_permitido=False)
        self.assertEqual((a["fecha_limite"], a["plazo"], a["gracia_ms"], a["consigna"], a["titulo"], a["paquete_permitido"]),
                         (1_900_000_000_000, "endurecido", 300_000, "Lee y practica.", "Repaso de la materia", False))

    def test_asignar_a_alumnos_sueltos(self):
        otro = self.nuevo_alumno("Ana R.", "300111")
        a = self.crear_asignacion(alcance="seleccion", alumnos=[otro], grupo_id="")
        self.assertEqual((a["alcance"], a["grupo_id"], a["destinatarios_total"]), ("seleccion", None, 1))
        self.assertEqual(m.Asignacion.objects.get(pk=a["id"]).destinatarios, [otro])
        con_grupo = self.crear_asignacion(alcance="seleccion", alumnos=[self.estudiante_id])
        self.assertEqual((con_grupo["alcance"], con_grupo["grupo_id"], con_grupo["destinatarios_total"]), ("seleccion", self.grupo["id"], 1))

    def test_lo_mal_formado_se_rechaza_sin_escribir_nada(self):
        casos = [
            ({"alcance": "seleccion", "alumnos": [], "grupo_id": ""}, 400, "datos_invalidos"),
            ({"alcance": "seleccion", "alumnos": ["nadie"], "grupo_id": ""}, 400, "datos_invalidos"),
            ({"alcance": "grupo", "grupo_id": ""}, 400, "datos_invalidos"),
            ({"alcance": "curso"}, 400, "datos_invalidos"),
            ({"plazo": "eterno"}, 400, "datos_invalidos"),
            ({"gracia_min": -1}, 400, "datos_invalidos"),
            ({"fecha_limite": -5}, 400, "datos_invalidos"),
            ({"grupo_id": "no-existe"}, 404, "no_encontrado"),
            ({"leccion_ref": "no-existe"}, 404, "no_encontrado"),
            ({"curso_ref": "no.existe"}, 404, "no_encontrado"),
            ({"alcance": "seleccion", "alumnos": [self.estudiante_id], "grupo_id": self.otro_grupo["id"]}, 400, "datos_invalidos"),
        ]
        for extra, http, codigo in casos:
            with self.subTest(extra=extra):
                r = self.api.post(f"{BASE}/docente/asignaciones/", {"alcance": "grupo", "grupo_id": self.grupo["id"], "curso_ref": CURSO,
                                                                    "fuente": "ejemplo", "leccion_ref": LECCION_1, **extra}, format="json")
                self.assertEqual((r.status_code, r.json()["codigo"]), (http, codigo), r.content)
        self.assertEqual(m.Asignacion.objects.count(), 0)

    def test_sin_biblioteca_no_se_asigna_a_ciegas(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with override_settings(AVACOM_CONTENIDO_ENLACE_V2=os.path.join(carpeta, "no-hay-link.json")):
                r = self.api.post(f"{BASE}/docente/asignaciones/", {"alcance": "grupo", "grupo_id": self.grupo["id"], "curso_ref": CURSO,
                                                                    "fuente": "biblioteca", "leccion_ref": LECCION_1}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["disponible"]), (503, "fuente_no_disponible", False))
        self.assertIn("sugerencia", r.json())
        self.assertEqual(m.Asignacion.objects.count(), 0)

    def test_con_sesion_se_exige_el_permiso_y_ser_titular_del_grupo(self):
        cuerpo = {"alcance": "grupo", "grupo_id": self.grupo["id"], "curso_ref": CURSO, "fuente": "ejemplo", "leccion_ref": LECCION_1}
        a = self.json_ok(self.docente.post(f"{BASE}/docente/asignaciones/", cuerpo, format="json"), 201)
        self.assertEqual(a["profesor"], "Prof. Gómez")
        self.assertEqual(m.Asignacion.objects.get(pk=a["id"]).profesor_id, self.docente_id)         # con sesión manda el token, no el cuerpo
        ajeno = self.docente.post(f"{BASE}/docente/asignaciones/", {**cuerpo, "grupo_id": self.otro_grupo["id"]}, format="json")
        self.assertEqual((ajeno.status_code, ajeno.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.admin.post(f"{BASE}/docente/asignaciones/", {**cuerpo, "grupo_id": self.otro_grupo["id"]}, format="json").status_code, 201)
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = juan.post(f"{BASE}/docente/asignaciones/", cuerpo, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

    def test_con_sesion_un_docente_no_asigna_a_alumnos_de_otro_grupo(self):
        ajeno = self.nuevo_alumno("Luis", "400222", grupo_id=self.otro_grupo["id"])
        r = self.docente.post(f"{BASE}/docente/asignaciones/", {
            "alcance": "seleccion", "alumnos": [ajeno], "curso_ref": CURSO, "fuente": "ejemplo", "leccion_ref": LECCION_1}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        propio = self.docente.post(f"{BASE}/docente/asignaciones/", {
            "alcance": "seleccion", "alumnos": [self.estudiante_id], "curso_ref": CURSO, "fuente": "ejemplo", "leccion_ref": LECCION_1}, format="json")
        self.assertEqual(propio.status_code, 201, propio.content)


class ListarYDetalleDelProfesorTests(BaseEstudio):
    def test_la_lista_trae_los_totales_y_se_filtra_por_grupo_y_estado(self):
        a = self.crear_asignacion()
        b = self.crear_asignacion(LECCION_2, grupo_id=self.otro_grupo["id"], actor="prof-ajeno")
        todas = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/"))["asignaciones"]
        self.assertEqual({x["id"] for x in todas}, {a["id"], b["id"]})
        fila = next(x for x in todas if x["id"] == a["id"])
        for campo in ("id", "titulo", "asignatura", "unidad", "grupo_id", "grupo_rotulo", "curso", "leccion_ref", "fecha_limite", "plazo", "estado", "alcance",
                      "paquete_permitido", "destinatarios_total", "completaron", "en_curso", "pendientes", "fuera_de_plazo", "pendientes_decision", "creada_en"):
            self.assertIn(campo, fila)
        self.assertNotIn("alumnos", fila)
        por_grupo = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/", {"grupo_id": self.grupo["id"]}))["asignaciones"]
        self.assertEqual([x["id"] for x in por_grupo], [a["id"]])
        self.api.post(f"{BASE}/docente/asignaciones/{a['id']}/cerrar/", {}, format="json")
        self.assertEqual([x["id"] for x in self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/", {"estado": "cerrada"}))["asignaciones"]], [a["id"]])
        self.assertEqual(self.api.get(f"{BASE}/docente/asignaciones/", {"estado": "rara"}).status_code, 400)
        # con sesión el docente sólo ve las de sus grupos
        propias = self.json_ok(self.docente.get(f"{BASE}/docente/asignaciones/"))["asignaciones"]
        self.assertEqual([x["id"] for x in propias], [a["id"]])

    def test_quien_completo_lista_a_los_destinatarios_con_o_sin_tarea(self):
        a = self.crear_asignacion()
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")           # entra al grupo DESPUÉS de asignar: también es destinataria
        self.json_ok(self.bloques(a["id"], BLOQUES_L1[:2]))                     # Juan avanza 2 de 7
        d = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/{a['id']}/"))
        self.assertEqual((d["destinatarios_total"], d["en_curso"], d["completaron"], d["pendientes"]), (2, 1, 0, 1))
        filas = {f["alumno_id"]: f for f in d["alumnos"]}
        juan, ana = filas[self.estudiante_id], filas[ana_id]
        self.assertEqual((juan["rotulo"], juan["estado"], juan["avance_pct"], juan["bloques_atendidos"], juan["bloques_total"]), ("Juan P.", "en_curso", 0.0, 2, 7))
        self.assertEqual((ana["estado"], ana["avance_pct"], ana["bloques_atendidos"], ana["completada_en"], ana["ultimo_avance_en"]), ("pendiente", 0.0, 0, None, None))
        self.assertEqual((juan["dispositivo"]["nombre"], juan["dispositivo"]["perfil"]), ("Tableta de Juan", "asignado"))
        self.assertEqual((ana["practica"], ana["paquete"], ana["pendientes_decision"], ana["vencida"], ana["fuera_de_plazo"]),
                         ({"intentos": 0, "mejor_correctas": None, "total": 6}, None, 0, False, False))
        self.assertEqual([f["rotulo"] for f in d["alumnos"]], ["Ana R.", "Juan P."])     # orden alfabético

    def test_una_seleccion_solo_alcanza_a_los_nombrados(self):
        ana_id, _ = self.alumno_con_tableta("Ana R.", "300111")
        a = self.crear_asignacion(alcance="seleccion", alumnos=[ana_id], grupo_id="")
        d = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/{a['id']}/"))
        self.assertEqual([f["alumno_id"] for f in d["alumnos"]], [ana_id])

    def test_un_docente_no_ve_la_asignacion_de_otro_grupo(self):
        b = self.crear_asignacion(grupo_id=self.otro_grupo["id"], actor="prof-ajeno")
        r = self.docente.get(f"{BASE}/docente/asignaciones/{b['id']}/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.admin.get(f"{BASE}/docente/asignaciones/{b['id']}/").status_code, 200)
        self.assertEqual(self.api.get(f"{BASE}/docente/asignaciones/no-existe/").status_code, 404)


class CambiarYCerrarTests(BaseEstudio):
    def test_endurecer_el_plazo_o_mover_la_fecha_y_quitarla(self):
        a = self.crear_asignacion(fecha_limite=1_900_000_000_000)
        r = self.json_ok(self.api.patch(f"{BASE}/docente/asignaciones/{a['id']}/", {
            "plazo": "endurecido", "gracia_min": 10, "fecha_limite": 1_950_000_000_000, "titulo": "Nuevo título", "consigna": "Entrega a tiempo.",
            "paquete_permitido": False}, format="json"))
        self.assertEqual((r["plazo"], r["gracia_ms"], r["fecha_limite"], r["titulo"], r["consigna"], r["paquete_permitido"]),
                         ("endurecido", 600_000, 1_950_000_000_000, "Nuevo título", "Entrega a tiempo.", False))
        r = self.json_ok(self.api.patch(f"{BASE}/docente/asignaciones/{a['id']}/", {"fecha_limite": None}, format="json"))
        self.assertIsNone(r["fecha_limite"])
        self.assertEqual(r["plazo"], "endurecido")                 # lo que no se toca, no cambia
        auditada = Auditoria.objects.filter(accion="estudio.asignacion.actualizada", objeto_id=a["id"]).count()
        self.assertEqual(auditada, 2)
        self.assertEqual(self.api.patch(f"{BASE}/docente/asignaciones/{a['id']}/", {}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(f"{BASE}/docente/asignaciones/{a['id']}/", {"plazo": "nunca"}, format="json").status_code, 400)

    def test_cerrar_la_asignacion_es_idempotente_deja_evento_y_bitacora_y_ya_no_se_cambia(self):
        a = self.crear_asignacion()
        r = self.json_ok(self.api.post(f"{BASE}/docente/asignaciones/{a['id']}/cerrar/", {"actor": self.docente_id}, format="json"))
        self.assertEqual((r["estado"], r["cerrada_en"] is not None), ("cerrada", True))
        self.assertEqual(m.Asignacion.objects.get(pk=a["id"]).estado, "cerrada")
        self.json_ok(self.api.post(f"{BASE}/docente/asignaciones/{a['id']}/cerrar/", {}, format="json"))
        self.assertEqual(self.eventos("estudio.asignacion.cerrada.v1"), ["estudio.asignacion.cerrada.v1"])
        self.assertEqual(Auditoria.objects.filter(accion="estudio.asignacion.cerrada", objeto_id=a["id"]).count(), 1)
        r = self.api.patch(f"{BASE}/docente/asignaciones/{a['id']}/", {"titulo": "otro"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))

    def test_solo_su_titular_o_la_administracion_la_cierra(self):
        b = self.crear_asignacion(grupo_id=self.otro_grupo["id"], actor="prof-ajeno")
        r = self.docente.post(f"{BASE}/docente/asignaciones/{b['id']}/cerrar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.admin.post(f"{BASE}/docente/asignaciones/{b['id']}/cerrar/", {}, format="json").status_code, 200)


class LoQueVeElAlumnoTests(BaseEstudio):
    def test_el_alumno_ve_lo_de_su_grupo_con_la_forma_del_contrato_y_sin_leer_la_biblioteca(self):
        a = self.crear_asignacion(fecha_limite=1_900_000_000_000, consigna="Lee con calma.")
        with mock.patch.object(ContenidoAula, "leccion", side_effect=FuenteNoDisponible("cerrada")):     # la lista funciona con la biblioteca cerrada
            r = self.json_ok(self.ver("/asignaciones/"))
        self.assertEqual(r["alumno"], {"id": self.estudiante_id, "rotulo": "Juan P."})
        self.assertEqual(r["resumen"], {"pendientes": 1, "descargadas": 0, "completadas": 0})
        x = r["asignaciones"][0]
        self.assertEqual((x["id"], x["titulo"], x["consigna"], x["asignatura"], x["unidad"], x["leccion_ref"]),
                         (a["id"], "Los tres estados de la materia", "Lee con calma.", "Ciencias naturales", "Estados de la materia", LECCION_1))
        self.assertEqual((x["fecha_limite"], x["plazo"], x["gracia_ms"], x["estado_asignacion"], x["profesor"]), (1_900_000_000_000, "blando", 900_000, "activa", "Prof. Gómez"))
        self.assertIsNone(x["tarea"])                                      # aún no la ha tocado: equivale a pendiente, 0 %
        self.assertEqual(x["practica"], {"disponible": True, "objeto_ref": "l1-activity", "titulo": "Practica: los tres estados", "total_preguntas": 6,
                                         "intentos": 0, "mejor_correctas": None, "ultima_correctas": None, "en_curso": False})
        self.assertIsNone(x["evaluacion"])
        self.assertIsNone(x["paquete"])
        self.assertEqual(x["descarga"], {"permitida": True, "motivo": ""})
        self.assertEqual([b["ref"] for b in x["bloques"]], BLOQUES_L1)
        self.assertFalse(any(b["atendido"] for b in x["bloques"]))
        self.assertEqual(x["bloques"][6], {"ref": "l1-activity", "indice": 7, "tipo": "practica", "titulo": "Practica: los tres estados",
                                           "obligatorio": True, "atendido": False, "objeto_ref": "l1-activity"})

    def test_un_alumno_no_ve_las_asignaciones_de_otro_grupo(self):
        a = self.crear_asignacion()
        b = self.crear_asignacion(LECCION_2, grupo_id=self.otro_grupo["id"])
        luis, hw_luis = self.alumno_con_tableta("Luis", "400222", grupo_id=self.otro_grupo["id"])
        propias_de_juan = self.json_ok(self.ver("/asignaciones/"))["asignaciones"]
        propias_de_luis = self.json_ok(self.ver("/asignaciones/", hw=hw_luis))["asignaciones"]
        self.assertEqual([x["id"] for x in propias_de_juan], [a["id"]])
        self.assertEqual([x["id"] for x in propias_de_luis], [b["id"]])
        r = self.ver(f"/asignaciones/{a['id']}/", hw=hw_luis)                # su id no le sirve de nada: 404, no se revela
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/").status_code, 200)

    def test_una_seleccion_solo_la_ven_los_nombrados_y_los_que_entran_despues_ven_la_del_grupo(self):
        a = self.crear_asignacion()
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")           # entra al grupo después de asignar
        self.assertEqual([x["id"] for x in self.json_ok(self.ver("/asignaciones/", hw=hw_ana))["asignaciones"]], [a["id"]])
        b = self.crear_asignacion(LECCION_2, alcance="seleccion", alumnos=[ana_id], grupo_id="")
        self.assertEqual({x["id"] for x in self.json_ok(self.ver("/asignaciones/", hw=hw_ana))["asignaciones"]}, {a["id"], b["id"]})
        self.assertEqual([x["id"] for x in self.json_ok(self.ver("/asignaciones/"))["asignaciones"]], [a["id"]])     # Juan no está en la selección

    def test_solo_se_listan_las_activas_o_las_completadas_por_el_alumno(self):
        a = self.crear_asignacion()
        b = self.crear_asignacion(LECCION_2)
        self.api.post(f"{BASE}/docente/asignaciones/{a['id']}/cerrar/", {}, format="json")
        self.assertEqual([x["id"] for x in self.json_ok(self.ver("/asignaciones/"))["asignaciones"]], [b["id"]])   # cerrada y sin completar: ya no
        m.Tarea.objects.create(id="t-1", asignacion_id=a["id"], alumno_id=self.estudiante_id, estado="completada", completada_en=5, avance_pct=100)
        r = self.json_ok(self.ver("/asignaciones/"))
        self.assertEqual({x["id"] for x in r["asignaciones"]}, {a["id"], b["id"]})
        self.assertEqual(r["resumen"], {"pendientes": 1, "descargadas": 0, "completadas": 1})
        self.assertEqual(r["asignaciones"][-1]["id"], a["id"])                # las completadas al final
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/").json()["estado_asignacion"], "cerrada")   # y una cerrada se puede leer

    def test_sin_aparato_ni_sesion_falta_el_dispositivo_y_en_uno_compartido_la_persona(self):
        self.crear_asignacion()
        r = self.api.get(f"{BASE}/asignaciones/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))
        r = self.ver("/asignaciones/", hw=self.hw_compartida)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_alumno"))
        declarado = self.json_ok(self.ver("/asignaciones/", hw=self.hw_compartida, alumno_id=self.estudiante_id))
        self.assertEqual(len(declarado["asignaciones"]), 1)
        self.assertEqual(declarado["asignaciones"][0]["descarga"], {"permitida": False, "motivo": "dispositivo_compartido"})

    def test_con_sesion_de_alumno_manda_la_persona_del_token(self):
        self.crear_asignacion()
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.json_ok(self.ver("/asignaciones/", hw=self.hw_compartida, cliente=juan))
        self.assertEqual((r["alumno"]["id"], len(r["asignaciones"])), (self.estudiante_id, 1))
        r = self.docente.get(f"{BASE}/asignaciones/", {"dispositivo": self.hw_juan})           # el profesor no tiene study.assignment.read
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
