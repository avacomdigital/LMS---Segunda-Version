"""
Identidad declarada (D-15 · 2026-09-29, pedido del usuario): en Modo Estudio el alumno ELIGE quién es —sin código ni contraseña, «esto es un LMS offline»— en
CUALQUIER tableta, compartida o asignada. Lo declarado (`alumno_id`) gana al dueño de una tableta asignada; sin declarar, la asignada toma a su dueño; y quien se
declara debe existir y estar activo. Un alumno declarado en la tableta asignada a OTRO estudia y aparece ante el profesor, pero NO se lleva el paquete (BR-054).
"""
from __future__ import annotations

import json

from acceso.models import Usuario

from .. import models as m
from .base import BASE, BLOQUES_L1, CORRECTAS, BaseEstudio


class BaseDeclarada(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()
        self.ana_id = self.nuevo_alumno("Ana R.", "300111")          # del mismo grupo; sin tableta propia

    def ana(self, ruta: str, hw: str | None = None, **params):
        """GET de Ana, declarada, sobre la tableta de Juan (o la que se diga)."""
        return self.ver(ruta, hw=hw, alumno_id=self.ana_id, **params)

    def ana_envia(self, metodo: str, ruta: str, cuerpo: dict | None = None, hw: str | None = None):
        return self.enviar(metodo, ruta, {"alumno_id": self.ana_id, **(cuerpo or {})}, hw=hw)


class EstudiaEnLaTabletaDeOtroTests(BaseDeclarada):
    def test_ana_estudia_de_principio_a_fin_en_la_tableta_de_juan_y_aparece_ante_el_profesor(self):
        # 1 · ve sus pendientes: la lista es de Ana, no del dueño de la tableta, y le dice que aquí no se descarga
        lista = self.json_ok(self.ana("/asignaciones/"))
        self.assertEqual(lista["alumno"], {"id": self.ana_id, "rotulo": "Ana R."})
        self.assertEqual([x["descarga"] for x in lista["asignaciones"]], [{"permitida": False, "motivo": "dispositivo_ajeno"}])
        self.assertEqual(self.json_ok(self.ana(f"/asignaciones/{self.a['id']}/"))["descarga"], {"permitida": False, "motivo": "dispositivo_ajeno"})
        # 2 · abre la lección: las URL de los medios llevan a quién pregunta (el visor no manda cabeceras) y sirven
        leccion = self.json_ok(self.ana(f"/lecciones/{self.a['id']}/"))
        self.assertEqual(leccion["asignacion"]["descarga"], {"permitida": False, "motivo": "dispositivo_ajeno"})
        self.assertIn(f"alumno_id={self.ana_id}", json.dumps(leccion))
        r = self.api.get(f"{BASE}/asignaciones/{self.a['id']}/medios/img-particles/", {"dispositivo": self.hw_juan, "alumno_id": self.ana_id})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(b"".join(r.streaming_content) if r.streaming else r.content), 0)
        # 3 · avanza, practica y completa: todo queda a nombre de Ana
        self.json_ok(self.ana_envia("post", "/sesion/"))
        self.json_ok(self.bloques(self.a["id"], BLOQUES_L1[:6], alumno_id=self.ana_id))
        practica = self.json_ok(self.ana_envia("post", f"/lecciones/{self.a['id']}/practica/"))["practica"]
        self.json_ok(self.ana_envia("post", f"/practicas/{practica['id']}/respuestas/", {
            "respuestas": [{"pregunta_ref": "l1-act-q1", "secuencia": 1, "respuesta": CORRECTAS["l1-act-q1"]}]}))
        self.json_ok(self.ana_envia("post", f"/practicas/{practica['id']}/terminar/"))
        tarea = self.json_ok(self.ana_envia("post", f"/lecciones/{self.a['id']}/completar/"))["tarea"]
        self.assertEqual((tarea["estado"], tarea["avance_pct"]), ("completada", 100.0))
        self.assertEqual([(t.alumno_id, t.estado) for t in m.Tarea.objects.all()], [(self.ana_id, "completada")])       # y Juan no fue tocado
        self.assertEqual([p.alumno_id for p in m.Practica.objects.all()], [self.ana_id])
        # 4 · el profesor la ve completada y ve en qué tableta estudió
        detalle = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/{self.a['id']}/"))
        filas = {f["alumno_id"]: f for f in detalle["alumnos"]}
        self.assertEqual((filas[self.ana_id]["estado"], filas[self.ana_id]["avance_pct"], filas[self.ana_id]["completada_en"] is not None), ("completada", 100.0, True))
        self.assertEqual((filas[self.estudiante_id]["estado"], filas[self.estudiante_id]["avance_pct"]), ("pendiente", 0.0))
        self.assertEqual(filas[self.ana_id]["dispositivo"]["id"], self.propia["id"])
        self.assertEqual((detalle["completaron"], detalle["pendientes"]), (1, 1))

    def test_pero_no_se_lleva_el_paquete_de_la_tableta_de_otro(self):
        r = self.ana_envia("post", "/paquetes/", {"asignacion_id": self.a["id"]})
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["paquete"]["motivo"]), (403, "descarga_denegada", "dispositivo_ajeno"))
        self.assertIn("tableta asignada a ti", r.json()["mensaje"])
        fila = m.Paquete.objects.get()
        self.assertEqual((fila.alumno_id, fila.dispositivo_id, fila.estado, fila.motivo), (self.ana_id, self.propia["id"], "denegado", "dispositivo_ajeno"))
        self.assertEqual(self.eventos("estudio.descarga.denegada.v1"), ["estudio.descarga.denegada.v1"])
        # y el paquete que sí se lleva el dueño no es legible para quien se declara en su tableta
        suyo = self.json_ok(self.enviar("post", "/paquetes/", {"asignacion_id": self.a["id"]}, hw=self.hw_juan), 201)["paquete"]
        r = self.ana(f"/paquetes/{suyo['id']}/manifiesto/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.json_ok(self.ana("/paquetes/"))["paquetes"][0]["estado"], "denegado")        # lo único que Ana tiene ahí es la constancia
        self.assertEqual(len(self.json_ok(self.ana("/paquetes/"))["paquetes"]), 1)

    def test_lo_declarado_gana_al_dueno_y_sin_declarar_manda_el_dueno(self):
        self.assertEqual(self.json_ok(self.ver("/asignaciones/"))["alumno"]["id"], self.estudiante_id)
        self.assertEqual(self.json_ok(self.ana("/asignaciones/"))["alumno"]["id"], self.ana_id)
        self.assertEqual(self.json_ok(self.ver("/asignaciones/", alumno_id=self.estudiante_id))["alumno"]["id"], self.estudiante_id)
        self.assertEqual(self.json_ok(self.enviar("post", "/sesion/"))["alumno"]["id"], self.estudiante_id)

    def test_el_dueno_declarado_o_no_conserva_todo_lo_suyo_incluido_el_paquete(self):
        for declarar in (False, True):
            with self.subTest(declarar=declarar):
                m.Paquete.objects.all().delete()
                r = self.enviar("post", "/paquetes/", {"asignacion_id": self.a["id"], **({"alumno_id": self.estudiante_id} if declarar else {})})
                self.assertEqual(r.status_code, 201, r.content)
                self.assertEqual(self.json_ok(self.ver("/asignaciones/", **({"alumno_id": self.estudiante_id} if declarar else {})))
                                 ["asignaciones"][0]["descarga"], {"permitida": True, "motivo": ""})

    def test_una_tableta_compartida_sirve_igual_pero_sin_paquete(self):
        lista = self.json_ok(self.ana("/asignaciones/", hw=self.hw_compartida))
        self.assertEqual((lista["alumno"]["id"], lista["asignaciones"][0]["descarga"]), (self.ana_id, {"permitida": False, "motivo": "dispositivo_compartido"}))
        self.json_ok(self.ana(f"/lecciones/{self.a['id']}/", hw=self.hw_compartida))
        r = self.ana_envia("post", "/paquetes/", {"asignacion_id": self.a["id"]}, hw=self.hw_compartida)
        self.assertEqual((r.status_code, r.json()["paquete"]["motivo"]), (403, "dispositivo_compartido"))


class QuienSeDeclaraTests(BaseDeclarada):
    def test_quien_no_existe_o_esta_inactivo_no_estudia_en_ninguna_ruta(self):
        Usuario.objects.filter(pk=self.ana_id).update(estado="INACTIVO")
        for quien in ("fantasma", self.ana_id):
            with self.subTest(quien=quien):
                casos = [self.ver("/asignaciones/", alumno_id=quien), self.ver(f"/asignaciones/{self.a['id']}/", alumno_id=quien),
                         self.ver(f"/lecciones/{self.a['id']}/", alumno_id=quien),
                         self.enviar("patch", f"/lecciones/{self.a['id']}/progreso/", {"alumno_id": quien, "bloques_vistos": BLOQUES_L1[:1]}),
                         self.enviar("post", f"/lecciones/{self.a['id']}/completar/", {"alumno_id": quien}),
                         self.enviar("post", f"/lecciones/{self.a['id']}/practica/", {"alumno_id": quien}),
                         self.enviar("post", "/paquetes/", {"alumno_id": quien, "asignacion_id": self.a["id"]}),
                         self.enviar("post", "/sesion/", {"alumno_id": quien}),
                         self.enviar("post", "/sync/", {"alumno_id": quien, "emisor_id": "e", "eventos": []})]
                for r in casos:
                    self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (403, "sin_permiso", "alumno_desconocido"))
        self.assertEqual((m.Tarea.objects.count(), m.Paquete.objects.count(), m.Sincronizacion.objects.count()), (0, 0, 0))

    def test_cerrar_la_sesion_limpiar_y_retirar_el_paquete_no_dependen_de_que_el_alumno_siga_activo(self):
        paquete = self.json_ok(self.enviar("post", "/paquetes/", {"asignacion_id": self.a["id"]}, hw=self.hw_juan), 201)["paquete"]
        self.json_ok(self.enviar("post", "/sesion/"))
        Usuario.objects.filter(pk=self.estudiante_id).update(estado="INACTIVO")
        self.assertEqual(self.enviar("post", "/sesion/cerrar/", {"alumno_id": self.estudiante_id}).status_code, 200)
        self.assertEqual(self.enviar("post", "/sesion/limpieza/", {"alumno_id": self.estudiante_id, "resultado": "completa"}).status_code, 200)
        self.assertEqual(self.borrar(f"/paquetes/{paquete['id']}/").status_code, 200)
        self.assertIsNotNone(m.Paquete.objects.get(pk=paquete["id"]).retirado_en)

    def test_un_alumno_de_otro_grupo_no_ve_lo_asignado_aunque_se_declare_en_la_tableta(self):
        luis = self.nuevo_alumno("Luis", "400222", grupo_id=self.otro_grupo["id"])
        self.assertEqual(self.json_ok(self.ver("/asignaciones/", alumno_id=luis))["asignaciones"], [])
        for r in (self.ver(f"/asignaciones/{self.a['id']}/", alumno_id=luis), self.ver(f"/lecciones/{self.a['id']}/", alumno_id=luis),
                  self.enviar("patch", f"/lecciones/{self.a['id']}/progreso/", {"alumno_id": luis, "bloques_vistos": BLOQUES_L1[:1]}),
                  self.enviar("post", "/paquetes/", {"alumno_id": luis, "asignacion_id": self.a["id"]})):
            self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))
        self.assertEqual(m.Tarea.objects.count(), 0)

    def test_sin_declarar_a_nadie_una_tableta_compartida_sigue_pidiendo_quien_eres(self):
        for r in (self.ver("/asignaciones/", hw=self.hw_compartida), self.enviar("post", "/sesion/", hw=self.hw_compartida),
                  self.enviar("post", f"/lecciones/{self.a['id']}/completar/", hw=self.hw_compartida)):
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_alumno"))

    def test_con_sesion_manda_el_token_aunque_se_declare_a_otro(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = self.json_ok(self.ver("/asignaciones/", hw=self.hw_compartida, alumno_id=self.ana_id, cliente=juan))
        self.assertEqual(r["alumno"]["id"], self.estudiante_id)
