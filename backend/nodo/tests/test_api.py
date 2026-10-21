"""
`/api/nodo/` por rol (P-17): la administración y el técnico ven el estado y la cola; el técnico reprocesa SÓLO con una escalada temporal; el profesor y el alumno no ven nada y
el intento queda asentado; ninguna respuesta lleva la carga de un evento (R-13); con sesión obligatoria lo anónimo recibe 401.
"""
from __future__ import annotations

import json

from django.test import override_settings
from rest_framework.test import APIClient

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..infraestructura import contenedor
from .base import TIPO, BaseNodoConRoles


class ApiPorRolTests(BaseNodoConRoles):
    def problema(self) -> m.Problema:
        """Un evento apartado de verdad: un consumidor que falla una vez con `max_intentos=1`."""
        with override_settings(AVACOM_NODO_MAX_INTENTOS=1):
            contenedor.reiniciar()
            self.publicar_varios(3, carga={"intento_id": "dato-que-el-tecnico-no-debe-ver"})
            self.c = self.consumidor_de_prueba(falla_en={2})
            with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
                self.c.lote()
        contenedor.reiniciar()
        self.c = self.consumidor_de_prueba()                       # vuelve a registrar el aplicador en el contenedor nuevo (ya sin fallos)
        return m.Problema.objects.get()

    def test_estado_y_cola_para_administracion_y_tecnico(self):
        for cliente in (self.admin, self.tecnico):
            e = self.nd("/estado/", cliente)
            self.assertEqual((e["estado"], e["restringido"]), (cat.OPERATIVO, False))
            c = self.nd("/cola/", cliente)
            self.assertEqual(set(c), {"consumidores", "eventos", "ultima_secuencia", "contador", "problemas", "cortes", "purga", "servidor_en"})

    def test_el_profesor_y_el_alumno_no_ven_nada_y_queda_asiento(self):
        for cliente, rol in ((self.docente, "TEACHER"), (self.alumno(), "STUDENT")):
            for ruta in ("/estado/", "/cola/", "/problemas/"):
                r = self.nd(ruta, cliente, esperado=403)
                self.assertEqual(r["codigo"], "sin_permiso")
        asientos = self.asientos(cat.A_ACCESO_DENEGADO)
        self.assertEqual(len(asientos), 6)
        self.assertEqual(asientos[0].valor_nuevo["permiso_solicitado"], cat.P_HEALTH)
        self.assertEqual(asientos[0].resultado, "denegado")

    def test_problemas_sin_carga_y_reproceso_por_rol(self):
        problema = self.problema()
        p = self.nd("/problemas/", self.tecnico)
        self.assertEqual((p["total"], p["problemas"][0]["id"], p["problemas"][0]["secuencia"], p["problemas"][0]["estado"]), (1, problema.id, 2, cat.PR_APARTADO))
        for texto in (json.dumps(p), json.dumps(self.nd("/cola/", self.tecnico)), json.dumps(self.nd("/estado/", self.tecnico))):
            self.assertNotIn("dato-que-el-tecnico", texto)
            self.assertNotIn('"carga"', texto)
        self.assertEqual(self.nd("/problemas/", self.tecnico, limite="x", esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.nd("/problemas/", self.tecnico, estado="raro", esperado=400)["codigo"], "datos_invalidos")
        # el técnico sin escalada: 403 con asiento; con escalada: 200 con asiento de reproceso
        r = self.nd_post(f"/problemas/{problema.id}/reprocesar/", cliente=self.tecnico, esperado=403)
        self.assertEqual((r["codigo"], r["permiso"]), ("sin_permiso", cat.P_REPLAY))
        self.assertIn("escalada", r["detail"])
        self.assertEqual(len(self.asientos(cat.A_ACCESO_DENEGADO)), 1)
        self.escalar(self.tecnico_id)
        r = self.nd_post(f"/problemas/{problema.id}/reprocesar/", cliente=self.tecnico)
        self.assertEqual((r["estado"], r["resuelto_por"]), (cat.PR_REPROCESADO, self.tecnico_id))
        self.assertEqual(self.asientos(cat.A_EVENTO_REPROCESADO)[0].usuario_id, self.tecnico_id)
        self.assertEqual(self.nd_post(f"/problemas/{problema.id}/reprocesar/", cliente=self.tecnico, esperado=409)["codigo"], "problema_ya_resuelto")
        self.assertEqual(self.nd_post("/problemas/999/reprocesar/", cliente=self.admin, esperado=404)["codigo"], "no_encontrado")
        self.assertEqual(self.nd_post(f"/problemas/{problema.id}/reprocesar/", cliente=self.docente, esperado=403)["codigo"], "sin_permiso")

    def test_la_administracion_reprocesa_y_reproduce(self):
        problema = self.problema()
        r = self.nd_post(f"/problemas/{problema.id}/reprocesar/")
        self.assertEqual(r["estado"], cat.PR_REPROCESADO)
        r = self.nd_post("/consumidores/prueba/reproducir/")
        self.assertEqual((r["marcas_reiniciadas"], r["estado"]), (1, cat.C_RECONSTRUYENDOSE))
        self.assertEqual(servicios.marca("prueba", "evaluacion"), 0)
        self.assertEqual(self.nd_post("/consumidores/nadie/reproducir/", esperado=404)["codigo"], "consumidor_desconocido")
        self.assertEqual(self.nd_post("/consumidores/prueba/reproducir/", {"fuente": "aula"}, esperado=400)["codigo"], "datos_invalidos")
        self.assertEqual(self.nd_post("/consumidores/prueba/reproducir/", cliente=self.tecnico, esperado=403)["codigo"], "sin_permiso")

    def test_un_reproceso_que_vuelve_a_fallar_responde_409(self):
        problema = self.problema()
        self.c.falla_en.add(2)
        with self.assertLogs("avacom.nodo.consumidores", level="ERROR"):
            r = self.nd_post(f"/problemas/{problema.id}/reprocesar/", esperado=409)
        self.assertEqual(r["codigo"], "reproceso_fallido")
        self.assertNotIn("dato-que-el-tecnico", json.dumps(r))

    def test_con_sesion_obligatoria_lo_anonimo_recibe_401_y_sin_ella_el_prototipo_deja_pasar(self):
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            contenedor.reiniciar()
            r = APIClient().get("/api/nodo/estado/")
            self.assertEqual(r.status_code, 401)                                   # el 401 lo arma DRF (el mismo de las demás rutas con sesión obligatoria)
            self.assertEqual(self.tecnico.get("/api/nodo/estado/").status_code, 200)
        self.assertEqual(APIClient().get("/api/nodo/estado/?actor=alguien").status_code, 200)

    def test_el_actor_de_la_sesion_llega_al_sobre_de_lo_que_publica_el_nodo(self):
        problema = self.problema()
        self.nd_post(f"/problemas/{problema.id}/reprocesar/")
        reprocesado = self.eventos(tipo=cat.EV_EVENTO_REPROCESADO)[0]
        self.assertEqual(reprocesado.actor, self.admin_id)
        self.assertEqual(reprocesado.dispositivo_id, cat.DISPOSITIVO_NODO)
        self.assertTrue(reprocesado.correlacion_id)
        self.assertEqual(reprocesado.tipo, cat.EV_EVENTO_REPROCESADO)
        self.assertEqual(m.Evento.objects.filter(tipo=TIPO).count(), 3)
