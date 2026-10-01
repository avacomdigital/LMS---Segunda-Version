"""
§2.4 y §4.2 · `/api/logs/`: lectura de los logs por el técnico y el administrador (`diagnostics.read`, sin datos personales)
y entrega de los renglones WARNING+ de OPS y Student (`/api/logs/clientes/`, por dispositivo o sesión; no toca la bitácora).
019-10 · «accesos del técnico».
"""
from __future__ import annotations

import logging

from django.test import override_settings

from ..aplicacion import logs as app_logs
from ..models import Bitacora
from ..pruebas import LogsDePrueba
from .test_api import BaseApiAuditoria


def renglon(**extra) -> dict:
    base = {"ts": "2026-09-30T10:15:02.314-05:00", "nivel": "ERROR", "canal": "escritura", "app": "student", "modulo": "estudio",
            "evento": "cola.persistir_fallo", "ruta": "bad", "mensaje": "No se pudo escribir la cola de respuestas",
            "detalle": {"errno": 28, "libre_mb": 0}, "corr": "9c1e-student-1", "version_app": "1.4.0"}
    base.update(extra)
    return base


class LogsClientesTests(LogsDePrueba, BaseApiAuditoria):
    def setUp(self):
        super().setUp()
        app_logs.reiniciar_tasa()

    def test_student_entrega_sus_errores_y_quedan_en_backend_clientes_con_el_dispositivo_autenticado(self):
        r = self.api.post("/api/logs/clientes/", {"app": "student", "version_app": "1.4.0", "dispositivo_id": "otro-inventado",
                                                  "renglones": [renglon(), renglon(nivel="WARNING", canal="comunicacion", evento="socket.caida",
                                                                                   mensaje="WebSocket caído 12 s", detalle={"duracion_ms": 12000})]},
                          format="json", HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"])
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(r.json(), {"recibidos": 2, "escritos": 2, "descartados": 0, "dispositivo_id": self.tableta["id"]})
        lineas = self.lineas_log(archivo="backend-clientes.log")
        self.assertEqual(len(lineas), 2)
        error = next(l for l in lineas if l["nivel"] == "ERROR")
        self.assertEqual((error["app"], error["canal"], error["evento"], error["ruta"], error["dispositivo_id"], error["corr"]),
                         ("student", "escritura", "cola.persistir_fallo", "bad", self.tableta["id"], "9c1e-student-1"))
        self.assertEqual(error["detalle"]["detalle"], {"errno": 28, "libre_mb": 0})
        self.assertEqual(error["detalle"]["ts_cliente"], "2026-09-30T10:15:02.314-05:00")
        # También está en errores (WARNING+), y la bitácora no se tocó.
        self.assertTrue(any(l["evento"] == "socket.caida" for l in self.lineas_log(archivo="backend-errores.log")))
        self.assertFalse(Bitacora.objects.filter(modulo="auditoria", accion__startswith="auditoria.registro").exists())

    def test_sin_equipo_registrado_ni_sesion_no_se_acepta_y_un_equipo_bloqueado_tampoco(self):
        r = self.api.post("/api/logs/clientes/", {"app": "student", "renglones": [renglon()]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "permiso_denegado"))
        r = self.api.post("/api/logs/clientes/", {"app": "student", "renglones": [renglon()]}, format="json", HTTP_X_AVACOM_DISPOSITIVO="no-existe")
        self.assertEqual(r.status_code, 403)
        self.admin.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "x"}, format="json")
        r = self.api.post("/api/logs/clientes/", {"app": "student", "renglones": [renglon()]}, format="json", HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"])
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.lineas_log(archivo="backend-clientes.log"), [])

    def test_ops_con_sesion_y_sin_equipo_entrega_a_nombre_del_usuario(self):
        r = self.admin.post("/api/logs/clientes/", {"app": "ops", "renglones": [renglon(app="ops", canal="aplicacion", evento="win2d.bad_number")]}, format="json")
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(r.json()["dispositivo_id"], f"sesion:{self.admin_id}")
        self.assertEqual(self.lineas_log(archivo="backend-clientes.log")[0]["app"], "ops")

    def test_los_secretos_de_un_renglon_se_redactan_y_hay_tope_de_renglones_y_de_tasa(self):
        with override_settings(AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES=3, AVACOM_LMS_LOGS_CLIENTES_MAX_POR_MINUTO=4):
            renglones = [renglon(mensaje=f"r{i}", detalle={"pin": "1234", "errno": i}) for i in range(5)]
            r = self.api.post("/api/logs/clientes/", {"app": "student", "renglones": renglones}, format="json", HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"])
            self.assertEqual(r.json(), {"recibidos": 5, "escritos": 3, "descartados": 2, "dispositivo_id": self.tableta["id"]})
            r = self.api.post("/api/logs/clientes/", {"app": "student", "renglones": renglones[:3]}, format="json", HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"])
            self.assertEqual((r.json()["escritos"], r.json()["descartados"]), (1, 2))
        texto = (self.carpeta_logs() / "backend-clientes.log").read_text(encoding="utf-8")
        self.assertNotIn("1234", texto)
        self.assertIn("[redactado]", texto)
        self.assertEqual(self.api.post("/api/logs/clientes/", {"app": "nave", "renglones": []}, format="json",
                                       HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"]).status_code, 400)


class LogsLecturaTests(LogsDePrueba, BaseApiAuditoria):
    def test_el_tecnico_y_el_administrador_leen_los_logs_el_profesor_no(self):
        logging.getLogger("avacom.aula.x").error("fallo de escritura", extra={"canal": "escritura", "evento": "prueba.escritura", "ruta": "bad", "detalle": {"errno": 28}})
        for cliente in (self.tecnico_cliente, self.admin):
            r = cliente.get("/api/logs/?canal=escritura&nivel=ERROR&ultimos=20")
            self.assertEqual(r.status_code, 200, r.content)
            cuerpo = r.json()
            self.assertTrue(any(l["evento"] == "prueba.escritura" for l in cuerpo["lineas"]), cuerpo["lineas"][:2])
            self.assertTrue(all(l["canal"] == "escritura" and l["nivel"] == "ERROR" for l in cuerpo["lineas"]))
            self.assertIn("bad", cuerpo["resumen"])
            self.assertIn("backend-app", cuerpo["archivos"])
        r = self.docente.get("/api/logs/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "permiso_denegado"))
        self.assertEqual(self.api.get("/api/logs/").status_code, 401)
        self.assertEqual(self.admin.get("/api/logs/?canal=inventado").status_code, 400)

    def test_los_logs_que_se_leen_no_traen_datos_personales_y_se_filtran_por_corr_app_y_archivo(self):
        self.api.post("/api/logs/clientes/", {"app": "student", "renglones": [{"ts": "2026-09-30T10:00:00-05:00", "nivel": "WARNING", "canal": "dispositivo",
                                                                               "app": "student", "mensaje": "batería baja", "detalle": {"bateria_pct": 9, "nombre": "Juan"},
                                                                               "corr": "corr-bat-1"}]}, format="json", HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"])
        r = self.tecnico_cliente.get("/api/logs/?app=student&archivo=backend-clientes&corr=corr-bat")
        lineas = r.json()["lineas"]
        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["detalle"]["detalle"], {"bateria_pct": 9, "nombre": "[redactado]"})
        self.assertEqual(lineas[0]["dispositivo_id"], self.tableta["id"])
        self.assertEqual(self.tecnico_cliente.get(f"/api/logs/?dispositivo={self.tableta['id']}&canal=dispositivo").json()["total"], 1)
        # Los archivos son de toda la corrida: se acota por corr para no contar lo de otros casos.
        self.assertEqual(self.tecnico_cliente.get("/api/logs/?app=ops&archivo=backend-clientes&corr=corr-bat").json()["total"], 0)


class AccesosDelTecnicoTests(BaseApiAuditoria):
    def test_las_acciones_y_denegaciones_del_tecnico_se_listan_y_el_indicador_dice_que_no_accedio_a_datos_personales(self):
        self.tecnico_cliente.get("/api/auditoria/asientos/")             # denegado
        self.tecnico_cliente.get("/api/logs/")                            # permitido
        self.tecnico_cliente.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "mantenimiento"}, format="json")   # permitido
        r = self.admin.get("/api/auditoria/tecnico/accesos/")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual([t["usuario_id"] for t in cuerpo["tecnicos"]], [self.tecnico_id])
        self.assertEqual(cuerpo["tecnicos"][0]["rotulo"], "Técnico AVACOM")
        acciones = {a["accion"] for a in cuerpo["asientos"]}
        self.assertIn("acceso.denegado", acciones)
        self.assertIn("dispositivos.bloqueado", acciones)
        self.assertTrue(all(a["actor"]["usuario_id"] == self.tecnico_id for a in cuerpo["asientos"]))
        self.assertGreaterEqual(cuerpo["denegaciones"], 1)
        self.assertEqual((cuerpo["sin_acceso_a_datos_personales"], cuerpo["salto_detectado"]), (True, False))
        self.assertFalse(cuerpo["cadena_verificada"])
        self.admin.post("/api/auditoria/verificar/", {}, format="json")
        self.assertTrue(self.admin.get("/api/auditoria/tecnico/accesos/").json()["cadena_verificada"])
        # Sólo el administrador consulta los accesos del técnico; el técnico no se consulta a sí mismo.
        self.assertEqual(self.tecnico_cliente.get("/api/auditoria/tecnico/accesos/").status_code, 403)

    def test_si_el_tecnico_llegara_a_un_dato_personal_el_indicador_lo_dice(self):
        from .. import contexto, servicios
        with contexto.con(usuario_id=self.tecnico_id, rol_codigo="TECHNICIAN", origen="api"):
            servicios.anexar(self.tecnico_id, "acceso.dato_personal.consultado", "m01_persona", "p-1", nuevo={"campo": "fecha_nacimiento"})
        self.assertFalse(self.admin.get("/api/auditoria/tecnico/accesos/").json()["sin_acceso_a_datos_personales"])
