"""
019-05 · `/api/auditoria/`: consulta filtrada por permiso y paginada por cursor, asiento por consulta, enmascarado de
asientos sensibles (BR-131), sin verbos de escritura (AC-081), catálogo, tramos, estado y verificación.
"""
from __future__ import annotations

import time

from acceso.tests.base import BaseAcceso

from .. import servicios
from ..models import Bitacora

HORA_MS = 60 * 60 * 1000


class BaseApiAuditoria(BaseAcceso):
    def setUp(self):
        super().setUp()
        self.tecnico_cliente = self.tecnico()

    def tecnico(self):
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "TECHNICIAN", "alias": "Técnico AVACOM", "persona": {"nombres": "Tomás", "apellidos": "Técnico"},
            "identificadores": [{"tipo": "DNI", "valor": "70.111.222", "es_login": True}], "secreto": "Tecnico.2026!Aula", "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.tecnico_id = r.json()["id"]
        return self.sesion("70.111.222", "Tecnico.2026!Aula")

    def otro_admin(self):
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "ADMIN", "alias": "Coordinación", "persona": {"nombres": "Carla", "apellidos": "Coord"},
            "identificadores": [{"tipo": "DNI", "valor": "52.000.111", "es_login": True}], "secreto": "Coordina.2026!Aula", "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return self.sesion("52.000.111", "Coordina.2026!Aula")

    def escalar(self, usuario_id: str, permiso: str, horas: float = 1):
        """Otra identidad concede la escalada (OtorgarEscalada prohíbe la autoconcesión)."""
        otro = self.otro_admin()
        r = otro.post(f"/api/acceso/usuarios/{usuario_id}/escaladas/", {
            "permiso": permiso, "alcance": "ORGANIZATION", "motivo": "Inspección de auditoría",
            "vigente_hasta": int(time.time() * 1000) + int(horas * HORA_MS)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()


class ConsultaTests(BaseApiAuditoria):
    def test_el_administrador_lista_asientos_con_etiquetas_y_cada_consulta_deja_asiento(self):
        antes = Bitacora.objects.filter(accion="auditoria.consulta_realizada").count()
        r = self.admin.get("/api/auditoria/asientos/?limite=5&modulo=acceso")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["orden"], cuerpo["limite"], cuerpo["enmascarado"]), ("desc", 5, True))
        self.assertTrue(cuerpo["asientos"])
        primero = cuerpo["asientos"][0]
        for campo in ("id", "secuencia", "ocurrido_en", "actor", "modulo", "accion", "etiqueta", "resultado", "objeto", "origen", "huella", "correlacion_id"):
            self.assertIn(campo, primero)
        self.assertTrue(all(a["modulo"] == "acceso" for a in cuerpo["asientos"]))
        self.assertNotEqual(primero["huella"], None)
        self.assertEqual(len(primero["huella"]), 17)   # abreviada en la lista
        consulta = Bitacora.objects.filter(accion="auditoria.consulta_realizada").order_by("-secuencia").first()
        self.assertEqual(Bitacora.objects.filter(accion="auditoria.consulta_realizada").count(), antes + 1)
        self.assertEqual((consulta.usuario_id, consulta.valor_nuevo["filtros"], consulta.valor_nuevo["limite"]), (self.admin_id, {"modulo": "acceso"}, 5))

    def test_el_tecnico_el_profesor_y_el_alumno_no_leen_la_bitacora_y_la_denegacion_queda_asentada(self):
        for cliente, rol in ((self.tecnico_cliente, "TECHNICIAN"), (self.docente, "TEACHER"), (self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN), "STUDENT")):
            r = cliente.get("/api/auditoria/asientos/")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "permiso_denegado"), r.content)
            asiento = Bitacora.objects.filter(accion="acceso.denegado").order_by("-secuencia").first()
            self.assertEqual((asiento.roles_activos, asiento.valor_nuevo["permiso_solicitado"], asiento.valor_nuevo["ruta"]),
                             ([rol], "audit.read", "/api/auditoria/asientos/"))
        self.assertEqual(self.api.get("/api/auditoria/asientos/").status_code, 401)

    def test_filtros_por_actor_accion_resultado_fecha_objeto_y_correlacion(self):
        self.admin.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "prueba"}, format="json", HTTP_X_AVACOM_CORRELACION="corr-filtro-1")
        r = self.admin.get(f"/api/auditoria/asientos/?accion=dispositivos.bloqueado&actor={self.admin_id}")
        asientos = r.json()["asientos"]
        self.assertEqual(len(asientos), 1)
        self.assertEqual((asientos[0]["objeto"], asientos[0]["correlacion_id"], asientos[0]["actor"]["rotulo"]),
                         ({"tabla": "m09_dispositivo", "id": self.tableta["id"]}, "corr-filtro-1", "Rectoría"))
        self.assertEqual(self.admin.get("/api/auditoria/asientos/?correlacion=corr-filtro-1").json()["total"], 1)
        self.assertEqual(self.admin.get(f"/api/auditoria/asientos/?objeto_tabla=m09_dispositivo&objeto_id={self.tableta['id']}&resultado=ok").json()["total"], 2)
        self.assertEqual(self.admin.get("/api/auditoria/asientos/?accion=dispositivos.*").json()["total"], 2)
        futuro = int(time.time() * 1000) + HORA_MS
        self.assertEqual(self.admin.get(f"/api/auditoria/asientos/?desde={futuro}").json()["total"], 0)
        self.assertGreater(self.admin.get(f"/api/auditoria/asientos/?hasta={futuro}").json()["total"], 0)
        self.assertEqual(self.admin.get("/api/auditoria/asientos/?resultado=inventado").status_code, 400)
        servicios.anexar(self.admin_id, "auditoria.tramo_exportado", "t", "1", nuevo={}, motivo="Inspección anual")
        self.assertEqual(self.admin.get("/api/auditoria/asientos/?texto=anual").json()["total"], 1)

    def test_la_paginacion_por_cursor_es_estable_aunque_lleguen_asientos_nuevos(self):
        for i in range(6):
            servicios.anexar(self.admin_id, "prueba.cursor", "t", str(i))
        p1 = self.admin.get("/api/auditoria/asientos/?accion=prueba.cursor&limite=4").json()
        self.assertEqual((len(p1["asientos"]), p1["total"]), (4, 6))
        self.assertEqual(p1["siguiente"], p1["asientos"][-1]["secuencia"])
        servicios.anexar(self.admin_id, "prueba.cursor", "t", "nuevo")   # llega uno nuevo entre páginas
        p2 = self.admin.get(f"/api/auditoria/asientos/?accion=prueba.cursor&limite=4&antes={p1['siguiente']}").json()
        self.assertEqual((len(p2["asientos"]), p2["siguiente"]), (2, None))
        vistos = [a["secuencia"] for a in p1["asientos"] + p2["asientos"]]
        self.assertEqual(vistos, sorted(vistos, reverse=True))
        self.assertEqual(len(set(vistos)), 6)
        asc = self.admin.get(f"/api/auditoria/asientos/?accion=prueba.cursor&despues={vistos[-1]}&limite=10").json()
        self.assertEqual(asc["orden"], "asc")
        self.assertEqual([a["secuencia"] for a in asc["asientos"]], sorted(a["secuencia"] for a in asc["asientos"]))
        self.assertEqual(self.admin.get("/api/auditoria/asientos/?antes=3&despues=1").status_code, 400)

    def test_el_detalle_trae_huella_completa_y_los_valores_sensibles_van_enmascarados_sin_escalada(self):
        fila = servicios.anexar(self.admin_id, "calificacion.modificada", "calificacion", "c-1", anterior={"valor_interno": 72},
                                nuevo={"valor_interno": 80}, motivo="Error de suma")
        r = self.admin.get(f"/api/auditoria/asientos/{fila.id}/")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual((d["huella"], d["huella_previa"], d["sensible"], d["enmascarado"]), (fila.huella, fila.huella_previa, True, True))
        self.assertEqual((d["valor_anterior"], d["valor_nuevo"], d["motivo"]), ({"enmascarado": True}, {"enmascarado": True}, "Error de suma"))
        self.assertEqual(self.admin.get(f"/api/auditoria/asientos/{fila.secuencia}/").json()["id"], fila.id)
        self.assertEqual(self.admin.get("/api/auditoria/asientos/no-existe/").status_code, 404)
        self.assertFalse(Bitacora.objects.filter(accion="acceso.dato_personal.consultado").exists())
        # Con escalada vigente de audit.read se ve el valor y queda asentado que se consultó un dato sensible.
        self.escalar(self.admin_id, "audit.read")
        d = self.admin.get(f"/api/auditoria/asientos/{fila.id}/").json()
        self.assertEqual((d["enmascarado"], d["valor_anterior"], d["valor_nuevo"]), (False, {"valor_interno": 72}, {"valor_interno": 80}))
        consultado = Bitacora.objects.get(accion="acceso.dato_personal.consultado")
        self.assertEqual((consultado.usuario_id, consultado.objeto_id, consultado.valor_nuevo["secuencia"]), (self.admin_id, fila.id, fila.secuencia))
        lista = self.admin.get("/api/auditoria/asientos/?accion=calificacion.modificada").json()
        self.assertEqual((lista["enmascarado"], lista["asientos"][0]["valor_nuevo"]), (False, {"valor_interno": 80}))

    def test_ninguna_ruta_de_auditoria_acepta_verbos_de_escritura(self):
        fila = Bitacora.objects.order_by("secuencia").first()
        rutas = ["/api/auditoria/asientos/", f"/api/auditoria/asientos/{fila.id}/", "/api/auditoria/catalogo/", "/api/auditoria/tramos/",
                 "/api/auditoria/verificar/", "/api/auditoria/estado/", "/api/auditoria/tecnico/accesos/", "/api/logs/", "/api/logs/clientes/"]
        for ruta in rutas:
            for verbo in ("put", "patch", "delete"):
                r = getattr(self.admin, verbo)(ruta, {"accion": "x"}, format="json")
                self.assertEqual(r.status_code, 405, (verbo, ruta, r.status_code))
        self.assertEqual(Bitacora.objects.get(pk=fila.pk).accion, fila.accion)
        self.assertFalse(Bitacora.objects.filter(accion="x").exists())


class CatalogoTramosEstadoTests(BaseApiAuditoria):
    def test_el_catalogo_alimenta_los_filtros(self):
        r = self.admin.get("/api/auditoria/catalogo/")
        self.assertEqual(r.status_code, 200)
        c = r.json()
        self.assertIn({"clave": "aula", "etiqueta": "Aula (clase en vivo)"}, c["modulos"])
        claves = {a["clave"] for a in c["acciones"]}
        self.assertIn("calificacion.modificada", claves)
        self.assertIn("aula.control.*", claves)
        self.assertNotIn("prueba.*", claves)
        self.assertTrue(all(a["etiqueta"] for a in c["acciones"]))
        self.assertEqual(self.tecnico_cliente.get("/api/auditoria/catalogo/").status_code, 403)

    def test_tramos_estado_y_verificar(self):
        self.assertEqual(self.admin.get("/api/auditoria/tramos/").json()["tramos"][0]["estado"], "activa")
        e = self.admin.get("/api/auditoria/estado/").json()
        self.assertEqual((e["salto_detectado"], e["triggers_ok"]), (False, True))
        self.assertGreater(e["cabeza"]["secuencia"], 1)
        r = self.admin.post("/api/auditoria/verificar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "verificada"), r.content)
        self.assertEqual(self.admin.get("/api/auditoria/tramos/").json()["tramos"][0]["estado"], "verificada")
        self.assertIsNotNone(self.admin.get("/api/auditoria/estado/").json()["ultimo_verificado_en"])
        self.assertEqual(self.tecnico_cliente.post("/api/auditoria/verificar/", {}, format="json").status_code, 403)
