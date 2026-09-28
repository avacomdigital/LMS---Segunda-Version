"""
MOD-009 por HTTP y por su interfaz interna: registro idempotente (CAP-053), inventario con estado en
vivo (CAP-054), bloqueo y baja, latido, y la sesión de alumno en la tableta con sus dos invariantes
(INV-011: una tableta compartida, cero o una sesión; DEC-023: un alumno, una sola sesión abierta).
"""
from __future__ import annotations

from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from expediente.models import Auditoria

from .. import models as m
from .. import servicios
from ..dominio import dispositivo as dom
from ..dominio.errores import DispositivoBloqueado, DispositivoInactivo


class RegistroYLatidoTests(BaseAcceso):
    def test_registro_idempotente_por_huella_y_datos_de_la_tableta(self):
        r = self.api.post("/api/dispositivos/", {"identificador_hw": "hw-android-01", "nombre": "Tableta 01",
                                                 "plataforma": "android", "version_app": "0.4.2"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["identificador_hw"], d["identificador"], d["nombre"], d["tipo"]), ("hw-android-01", "hw-android-01", "Tableta 01", "TABLETA"))
        self.assertEqual((d["plataforma"], d["version_app"], d["activo"], d["bloqueado"], d["en_linea"]), ("android", "0.4.2", True, False, True))
        self.assertIsNone(d["sesion_abierta"])
        otra = self.api.post("/api/dispositivos/", {"identificador": "hw-android-01", "nombre": "Tableta 01 renombrada"}, format="json")
        self.assertEqual((otra.status_code, otra.json()["id"], otra.json()["nombre"]), (200, d["id"], "Tableta 01 renombrada"))
        self.assertEqual(m.Dispositivo.objects.filter(identificador_hw="hw-android-01").count(), 1)
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=dom.EV_REGISTRADO, agregado_id=d["id"]).count(), 1)
        self.assertTrue(Auditoria.objects.filter(accion="dispositivos.registrado", objeto_id=d["id"]).exists())

    def test_sin_huella_o_con_plataforma_desconocida_es_400(self):
        self.assertEqual(self.api.post("/api/dispositivos/", {"nombre": "x"}, format="json").status_code, 400)
        r = self.api.post("/api/dispositivos/", {"identificador_hw": "hw-x", "plataforma": "ios"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_latido_registra_si_hace_falta_y_dice_si_esta_bloqueada(self):
        r = self.api.post("/api/dispositivos/latido/", {"identificador_hw": "hw-nueva", "plataforma": "windows", "version_app": "1.0"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["plataforma"], r.json()["bloqueado"], r.json()["en_linea"]), ("windows", False, True))
        self.assertIn("servidor_en", r.json())
        d = m.Dispositivo.objects.get(identificador_hw="hw-nueva")
        m.Dispositivo.objects.filter(pk=d.id).update(bloqueado=True, ultimo_latido_en=1)
        r = self.api.post("/api/dispositivos/latido/", {"identificador_hw": "hw-nueva"}, format="json")
        self.assertTrue(r.json()["bloqueado"])
        self.assertGreater(m.Dispositivo.objects.get(pk=d.id).ultimo_latido_en, 1)
        # volver tras un silencio largo publica «reconectado»
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=dom.EV_RECONECTADO, agregado_id=d.id).exists())

    def test_sin_organizacion_no_hay_inventario(self):
        from acceso.models import Organizacion
        Organizacion.objects.all().delete()
        r = APIClient().post("/api/dispositivos/", {"identificador_hw": "hw-sin-nodo", "nombre": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "no_instalado"))


class InventarioYBloqueoTests(BaseAcceso):
    def test_listar_con_y_sin_sesion_y_lo_que_puede_cada_perfil(self):
        listado = self.api.get("/api/dispositivos/").json()            # sin sesión (Q-04): OPS en el prototipo
        self.assertEqual([d["nombre"] for d in listado], ["tableta-07"])
        self.assertEqual([d["nombre"] for d in self.docente.get("/api/dispositivos/").json()], ["tableta-07"])
        self.assertEqual([d["nombre"] for d in self.admin.get("/api/dispositivos/").json()], ["tableta-07"])
        estudiante = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual((estudiante.get("/api/dispositivos/").status_code, estudiante.get("/api/dispositivos/").json()["codigo"]), (403, "sin_permiso"))
        self.assertEqual(estudiante.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {}, format="json").status_code, 403)
        self.assertEqual(self.docente.patch(f"/api/dispositivos/{self.tableta['id']}/", {"nombre": "x"}, format="json").status_code, 403)
        self.assertEqual(self.api.get(f"/api/dispositivos/{self.tableta['id']}/").json()["id"], self.tableta["id"])
        self.assertEqual(self.api.get("/api/dispositivos/no-existe/").status_code, 404)

    def test_bloquear_y_desbloquear_es_reversible_y_queda_en_bitacora(self):
        ruta = f"/api/dispositivos/{self.tableta['id']}"
        r = self.docente.post(f"{ruta}/bloquear/", {"motivo": "uso indebido"}, format="json")
        self.assertEqual((r.status_code, r.json()["bloqueado"]), (200, True), r.content)
        self.assertTrue(self.docente.post(f"{ruta}/bloquear/", {}, format="json").json()["bloqueado"])   # idempotente
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=dom.EV_BLOQUEADO, agregado_id=self.tableta["id"]).count(), 1)
        asiento = Auditoria.objects.get(accion="dispositivos.bloqueado", objeto_id=self.tableta["id"])
        self.assertEqual((asiento.actor_id, asiento.valor_nuevo["motivo"]), (self.docente_id, "uso indebido"))
        # con la tableta bloqueada nadie abre sesión de login desde ella (regla del equipo, no de la persona)
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_bloqueado"))
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 200)   # sin tableta sigue entrando
        r = self.api.post(f"{ruta}/desbloquear/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["bloqueado"]), (200, False))
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA).status_code, 200)
        self.assertEqual(self.api.post(f"{ruta}/apagar/", {}, format="json").status_code, 404)

    def test_dar_de_baja_cierra_las_sesiones_de_login_y_de_alumno_en_la_tableta(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        abierta = servicios.abrir_sesion_alumno(self.estudiante_id, self.tableta["id"])
        r = self.admin.patch(f"/api/dispositivos/{self.tableta['id']}/", {"activo": False}, format="json")
        self.assertEqual((r.status_code, r.json()["activo"]), (200, False), r.content)
        self.assertEqual(alumno.get("/api/acceso/yo/").status_code, 401)
        from acceso.models import Sesion
        self.assertEqual(Sesion.objects.filter(dispositivo_id=self.tableta["id"], revocada_en__isnull=True).count(), 0)
        cerrada = m.DimSesionAlumno.objects.get(pk=abierta["id"])
        self.assertEqual((cerrada.motivo_cierre, cerrada.finalizada_en is not None), ("sistema", True))
        self.assertEqual([d["id"] for d in self.api.get("/api/dispositivos/").json()], [])
        self.assertEqual([d["id"] for d in self.api.get("/api/dispositivos/?todos=1").json()], [self.tableta["id"]])
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA).status_code, 200)   # retirada = como sin tableta
        with self.assertRaises(DispositivoInactivo):
            servicios.abrir_sesion_alumno(self.estudiante_id, self.tableta["id"])


class SesionDeAlumnoTests(BaseAcceso):
    def _tableta(self, huella: str) -> str:
        return self.api.post("/api/dispositivos/", {"identificador_hw": huella, "nombre": huella}, format="json").json()["id"]

    def test_inv_011_una_tableta_compartida_tiene_una_sola_sesion_de_alumno(self):
        ana = servicios.abrir_sesion_alumno("ana", self.tableta["id"])
        self.assertEqual(servicios.abrir_sesion_alumno("ana", self.tableta["id"])["id"], ana["id"])   # idempotente
        luis = servicios.abrir_sesion_alumno("luis", self.tableta["id"])
        cerrada = m.DimSesionAlumno.objects.get(pk=ana["id"])
        self.assertEqual((cerrada.motivo_cierre, cerrada.finalizada_en is not None), ("relevo", True))
        self.assertEqual(m.DimSesionAlumno.objects.filter(dispositivo_id=self.tableta["id"], finalizada_en__isnull=True).count(), 1)
        self.assertEqual(self.api.get(f"/api/dispositivos/{self.tableta['id']}/").json()["sesion_abierta"]["alumno_id"], "luis")
        self.assertEqual([e.tipo_evento for e in m.EventoSalida.objects.filter(agregado_tipo="DimSesionAlumno").order_by("id")],
                         [dom.EV_SESION_ABIERTA, dom.EV_SESION_CERRADA, dom.EV_SESION_ABIERTA])
        self.assertEqual(luis["dispositivo_id"], self.tableta["id"])

    def test_dec_023_un_alumno_tiene_una_sola_sesion_abierta_aunque_cambie_de_tableta(self):
        otra = self._tableta("hw-otra")
        primera = servicios.abrir_sesion_alumno("ana", self.tableta["id"])
        segunda = servicios.abrir_sesion_alumno("ana", otra)
        self.assertEqual(m.DimSesionAlumno.objects.get(pk=primera["id"]).motivo_cierre, "relevo")
        self.assertEqual(servicios.sesion_abierta_de_alumno("ana")["id"], segunda["id"])
        self.assertEqual(m.DimSesionAlumno.objects.filter(alumno_id="ana", finalizada_en__isnull=True).count(), 1)
        servicios.cerrar_sesion_alumno(segunda["id"], motivo="usuario")
        self.assertIsNone(servicios.sesion_abierta_de_alumno("ana"))
        self.assertEqual(m.DimSesionAlumno.objects.get(pk=segunda["id"]).motivo_cierre, "usuario")

    def test_una_tableta_bloqueada_no_abre_sesion_de_alumno(self):
        self.api.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {}, format="json")
        with self.assertRaises(DispositivoBloqueado):
            servicios.abrir_sesion_alumno("ana", self.tableta["id"])
        self.assertEqual(servicios.bloqueados_entre([self.tableta["id"], "no-existe"]), {self.tableta["id"]})
        self.assertIsNone(servicios.resolver(""))
        self.assertEqual(servicios.resolver(self.TABLETA)["id"], self.tableta["id"])
