"""
§2 del prompt de MOD-019 · sistema de logs en archivos: carpeta por entorno, JSON Lines con los campos mínimos,
saneamiento de datos personales, correlación por petición y ruta happy/sad/bad, y el helper de pruebas.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from acceso.tests.base import BaseAcceso

from .. import contexto, logging_setup as ls
from ..pruebas import LogsDePrueba


class CarpetaPorEntornoTests(SimpleTestCase):
    BASE = Path("C:/repo/backend")

    def test_la_variable_de_entorno_manda_sobre_todo(self):
        env = {"AVACOM_LMS_DIR_LOGS": "D:/mis-logs", "AVACOM_LMS_DEBUG": "0"}
        self.assertEqual(ls.carpeta_logs(self.BASE, env, ["manage.py", "test"]), Path("D:/mis-logs"))

    def test_instalado_va_a_program_data_y_desarrollo_a_backend_logs(self):
        instalado = ls.carpeta_logs(self.BASE, {"AVACOM_LMS_DEBUG": "0", "ProgramData": "C:/ProgramData"}, ["manage.py", "runserver"])
        self.assertEqual(instalado, Path("C:/ProgramData/AVACOM/OPS Master/Logs"))
        desarrollo = ls.carpeta_logs(self.BASE, {"AVACOM_LMS_DEBUG": "1"}, ["manage.py", "runserver"])
        self.assertEqual(desarrollo, self.BASE / "logs")

    def test_las_pruebas_usan_una_carpeta_temporal_por_corrida_y_jamas_program_data(self):
        env = {"TEMP": "C:/Temp", "ProgramData": "C:/ProgramData"}
        a = ls.carpeta_logs(self.BASE, env, ["manage.py", "test"])
        b = ls.carpeta_logs(self.BASE, {**env, "AVACOM_LMS_ENTORNO": "pruebas", "AVACOM_LMS_DEBUG": "0"}, ["manage.py", "runserver"])
        for carpeta in (a, b):
            self.assertTrue(str(carpeta).startswith("C:/Temp/avacom-lms-pruebas") or str(carpeta).startswith("C:\\Temp\\avacom-lms-pruebas"), carpeta)
            self.assertNotIn("ProgramData", str(carpeta))

    def test_si_la_carpeta_no_se_puede_escribir_cae_a_temp_con_aviso(self):
        with tempfile.TemporaryDirectory() as tmp:
            bloqueada = Path(tmp) / "archivo-no-carpeta"
            bloqueada.write_text("x", encoding="utf-8")   # un archivo donde debería ir una carpeta: mkdir falla
            efectiva, aviso = ls.preparar_carpeta(bloqueada / "Logs", {"TEMP": tmp})
            self.assertEqual(efectiva, Path(tmp) / "avacom-lms" / "logs")
            self.assertIn("No se pudo escribir", aviso or "")


class SaneamientoTests(SimpleTestCase):
    def test_las_claves_prohibidas_se_redactan_en_cualquier_nivel(self):
        entrada = {"usuario_id": "u-1", "password": "Secreta.1", "anidado": {"pin": "1234", "errno": 28, "respuesta": "b"},
                   "lista": [{"token": "abc"}, 3], "nombre": "Juan", "identificador_hw": "hw-7", "Authorization": "Bearer x"}
        salida = ls.sanear(entrada)
        self.assertEqual(salida["usuario_id"], "u-1")
        self.assertEqual(salida["identificador_hw"], "hw-7")
        for clave in ("password", "nombre", "Authorization"):
            self.assertEqual(salida[clave], ls.REDACTADO)
        self.assertEqual(salida["anidado"], {"pin": ls.REDACTADO, "errno": 28, "respuesta": ls.REDACTADO})
        self.assertEqual(salida["lista"], [{"token": ls.REDACTADO}, 3])

    def test_el_formateador_escribe_una_linea_json_con_los_campos_minimos_y_sin_secretos(self):
        record = logging.LogRecord("avacom.aula.x", logging.ERROR, __file__, 1, "No se pudo escribir la cola", None, None)
        record.canal, record.evento, record.ruta = "escritura", "cola.persistir_fallo", "bad"
        record.detalle = {"errno": 28, "libre_mb": 0, "secreto": "no"}
        with contexto.con(corr="9c1e-corr", dispositivo_id="d-3f", caso="x.y.z"):
            ls.FiltroContexto("student").filter(record)
        linea = json.loads(ls.FormateadorJson().format(record))
        for campo in ("ts", "nivel", "canal", "app", "modulo", "evento", "ruta", "caso", "dispositivo_id", "corr",
                      "secuencia_bitacora", "mensaje", "detalle", "traza"):
            self.assertIn(campo, linea)
        self.assertEqual((linea["nivel"], linea["canal"], linea["app"], linea["modulo"]), ("ERROR", "escritura", "student", "aula"))
        self.assertEqual((linea["corr"], linea["dispositivo_id"], linea["caso"]), ("9c1e-corr", "d-3f", "x.y.z"))
        self.assertEqual(linea["detalle"], {"errno": 28, "libre_mb": 0, "secreto": ls.REDACTADO})

    def test_la_ruta_se_deduce_del_estado_http(self):
        self.assertEqual([ls.ruta_por_estado(s) for s in (200, 201, 302, 400, 403, 404, 409, 500)],
                         ["happy", "happy", "happy", "sad", "sad", "sad", "sad", "bad"])
        self.assertEqual(ls.ruta_por_estado(200, excepcion=True), "bad")


class CorrelacionTests(LogsDePrueba, BaseAcceso):
    def test_cada_peticion_devuelve_su_corr_y_deja_una_linea_happy(self):
        r = self.admin.get("/api/acceso/yo/")
        self.assertEqual(r.status_code, 200)
        corr = r["X-Avacom-Correlacion"]
        self.assertTrue(len(corr) >= 8)
        lineas = [l for l in self.assertLogged(evento="http.peticion", ruta="happy") if l["corr"] == corr]
        self.assertEqual(len(lineas), 1, lineas)
        self.assertEqual((lineas[0]["detalle"]["path"], lineas[0]["detalle"]["estado"], lineas[0]["usuario_id"]),
                         ("/api/acceso/yo/", 200, self.admin_id))

    def test_el_cliente_puede_traer_su_propio_corr_y_se_respeta(self):
        r = self.admin.get("/api/acceso/yo/", HTTP_X_AVACOM_CORRELACION="ops-0001-abcd")
        self.assertEqual(r["X-Avacom-Correlacion"], "ops-0001-abcd")
        r = self.admin.get("/api/acceso/yo/", HTTP_X_AVACOM_CORRELACION="<script>")
        self.assertNotEqual(r["X-Avacom-Correlacion"], "<script>")

    def test_un_404_es_sad_y_no_deja_error_escondido(self):
        r = self.admin.get("/api/acceso/usuarios/no-existe/")
        self.assertEqual(r.status_code, 404)
        self.assertLogged(evento="http.peticion", ruta="sad")
        self.assertNoLogged(nivel="ERROR")

    def test_la_cabecera_de_dispositivo_solo_se_acepta_si_el_equipo_esta_activo_y_sin_bloqueo(self):
        from ..middleware import dispositivo_validado
        self.assertEqual(dispositivo_validado(self.tableta["id"]), self.tableta["id"])
        self.assertIsNone(dispositivo_validado("no-existe"))
        self.assertIsNone(dispositivo_validado(""))
        self.assertIsNone(dispositivo_validado("../x"))
        self.assertLogged(evento="dispositivo.cabecera_rechazada", nivel="WARNING", canal="dispositivo")
        self.admin.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "prueba"}, format="json")
        self.assertIsNone(dispositivo_validado(self.tableta["id"]))

    def test_los_logs_no_contienen_secretos_sembrados(self):
        # Se siembra un secreto por todas las rutas que escriben: login, creación de usuario y un log directo.
        self.login(self.ADMIN_DNI, self.ADMIN_PASS)
        logging.getLogger("avacom.prueba").warning("sembrado", extra={"detalle": {"password": self.ADMIN_PASS, "pin": self.ESTUDIANTE_PIN}})
        texto = "".join((self.carpeta_logs() / n).read_text(encoding="utf-8") for n in self.ARCHIVOS_LOG if (self.carpeta_logs() / n).exists())
        self.assertNotIn(self.ADMIN_PASS, texto)
        self.assertNotIn(self.ESTUDIANTE_PIN, texto)
        self.assertNotIn(self.ADMIN_DNI, texto)


class HelperDePruebasTests(LogsDePrueba, TestCase):
    def test_las_lineas_de_este_caso_llevan_su_id_y_no_se_mezclan_con_otros(self):
        logging.getLogger("avacom.prueba").info("hola", extra={"evento": "prueba.hola", "canal": "aplicacion"})
        lineas = self.assertLogged(evento="prueba.hola")
        self.assertEqual(lineas[0]["caso"], self.id())
        self.assertNoLogged(evento="prueba.inexistente")
