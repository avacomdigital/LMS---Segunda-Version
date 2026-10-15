"""
Seguridad e integridad del libro. TST-069: el rol técnico no puede modificar calificaciones —ni leer datos académicos— y el intento queda en la bitácora. Un profesor sólo
opera SUS grupos; la administración configura pero no califica; el alumno sólo lee lo suyo; la bitácora no se altera.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from audit import models as maudit

from .. import models as m
from .base import GB, BaseGradebook


class _ConCalificacion(BaseGradebook):
    def setUp(self):
        super().setUp()
        self.a, self.i, self.refs, self.tipos = self.examen_entregado(abiertas=False)
        self.cal = self.calificacion(self.i)
        self.tecnico_cliente = self.tecnico()

    def intentos_de_modificar(self, cliente, esperado: int = 403) -> list[tuple[str, str]]:
        cal = self.cal
        cuerpos = [
            ("post", f"/calificaciones/{cal['id']}/ajustar/", {"puntaje_nuevo": 99, "motivo": "Intento no autorizado", "version_esperada": cal["version"]}),
            ("post", f"/calificaciones/{cal['id']}/reabrir/", {"motivo": "Intento no autorizado", "version_esperada": cal["version"]}),
            ("post", f"/calificaciones/{cal['id']}/valoracion/", {"tramo": "x", "motivo": "Intento no autorizado", "version_esperada": cal["version"]}),
            ("post", f"/calificaciones/{cal['id']}/retroalimentacion/", {"comentario": "x", "version_esperada": cal["version"]}),
            ("post", f"/calificaciones/{cal['id']}/publicar/", {}),
            ("post", f"/calificaciones/{cal['id']}/retirar-publicacion/", {"motivo": "Intento no autorizado", "version_esperada": cal["version"]}),
            ("post", f"/asignaciones/{self.a['id']}/publicar/", {}),
            ("put", f"/asignaciones/{self.a['id']}/clasificacion/", {"tipo_evaluacion": "formativa"}),
            ("post", f"/intentos/{self.i}/registrar/", {}),
            ("post", f"/revisiones/{self.i}/confirmar/", {}),
            ("post", f"/revisiones/{self.i}/respuestas/{self.refs[0]}/", {"puntaje": 1}),
        ]
        hechos = []
        for metodo, ruta, cuerpo in cuerpos:
            r = getattr(cliente, metodo)(f"{GB}{ruta}", cuerpo, format="json")
            self.assertEqual(r.status_code, esperado, (ruta, r.content))
            hechos.append((metodo, ruta))
        return hechos

    def sin_cambios(self):
        fila = self.fila_cal(self.i)
        self.assertEqual((fila.version, fila.estado, fila.puntaje_efectivo), (1, "revisada", fila.puntaje_original))
        self.assertEqual(m.VersionCalificacion.objects.filter(calificacion_id=fila.id).count(), 1)


class RolTecnicoTests(_ConCalificacion):
    def test_tst_069_el_tecnico_no_modifica_y_la_alerta_queda_en_la_bitacora(self):
        hechos = self.intentos_de_modificar(self.tecnico_cliente)
        self.sin_cambios()
        asientos = maudit.Bitacora.objects.filter(accion="calificacion.modificacion_denegada", usuario_id=self.tecnico_id)
        self.assertEqual(asientos.count(), len(hechos))                                    # CADA intento deja su asiento
        ultimo = asientos.order_by("-secuencia").first()
        self.assertEqual((ultimo.resultado, ultimo.valor_nuevo["codigo"], ultimo.valor_nuevo["rol"]), ("denegado", "sin_permiso", "TECHNICIAN"))
        self.assertTrue(ultimo.valor_nuevo["permiso_solicitado"].startswith("grades."))
        self.assertTrue(ultimo.valor_nuevo["ruta"].startswith("/api/gradebook/"))
        # Y además el 403 genérico de la API (019-08), con los roles activos.
        self.assertTrue(maudit.Bitacora.objects.filter(accion="acceso.denegado", usuario_id=self.tecnico_id).exists())

    def test_el_tecnico_tampoco_lee_datos_academicos(self):
        for ruta, params in (("/libro/", {"grupo_id": self.grupo["id"]}), (f"/calificaciones/{self.cal['id']}/", {}), (f"/estudiantes/{self.estudiante_id}/", {}),
                             (f"/asignaciones/{self.a['id']}/", {}), ("/resumen/", {"grupo_id": self.grupo["id"]}), ("/revisiones/", {}), ("/mias/", {})):
            r = self.tecnico_cliente.get(f"{GB}{ruta}", params)
            self.assertEqual(r.status_code, 403, (ruta, r.content))
        self.assertEqual(self.tecnico_cliente.post(f"{GB}/sincronizar/", {}, format="json").status_code, 403)
        self.assertEqual(self.tecnico_cliente.post(f"{GB}/derivados/reconstruir/", {}, format="json").status_code, 403)

    def test_el_tecnico_no_configura_el_modo_ni_las_escalas(self):
        for metodo, ruta, cuerpo in (("post", "/escalas/adoptar/", {"plantilla": "gen-0-5"}), ("put", "/niveles/primaria/", {"modo": "simple"}), ("put", "/politica/", {"pais": "CO"}),
                                     ("post", "/escalas/", {"codigo": "abc", "nombre": "x", "definicion": {}})):
            self.assertEqual(getattr(self.tecnico_cliente, metodo)(f"{GB}{ruta}", cuerpo, format="json").status_code, 403, ruta)
        self.assertEqual(m.Escala.objects.count(), 1)                                      # sólo la del setUp


class AlcanceTests(_ConCalificacion):
    def test_un_profesor_no_opera_grupos_que_no_son_suyos(self):
        _, otro, grupo = self.otro_docente()
        self.intentos_de_modificar(otro)
        self.sin_cambios()
        for ruta, params in (("/libro/", {"grupo_id": self.grupo["id"]}), (f"/calificaciones/{self.cal['id']}/", {}), (f"/asignaciones/{self.a['id']}/", {}),
                             (f"/estudiantes/{self.estudiante_id}/", {}), ("/resumen/", {"grupo_id": self.grupo["id"]}), (f"/revisiones/{self.i}/", {})):
            r = otro.get(f"{GB}{ruta}", params)
            self.assertEqual((r.status_code, r.json().get("codigo")), (403, "fuera_de_alcance"), ruta)
        # Lo suyo sí: su libro existe (vacío) y su bandeja sólo trae sus grupos.
        self.assertEqual(self.leer("/libro/", cliente=otro, grupo_id=grupo["id"])["totales"]["alumnos"], 0)
        self.assertEqual(self.leer("/revisiones/", cliente=otro)["total"], 0)
        self.assertEqual(maudit.Bitacora.objects.filter(accion="calificacion.modificacion_denegada").count() > 0, True)

    def test_el_profesor_titular_si_opera_su_grupo(self):
        self.assertEqual(self.ajustar(self.cal, 90)["calificacion"]["puntaje_efectivo"], 90.0)
        self.assertEqual(self.leer(f"/estudiantes/{self.estudiante_id}/")["grupos"][0]["calificaciones"][0]["puntaje_efectivo"], 90.0)

    def test_la_administracion_configura_pero_no_califica(self):
        self.intentos_de_modificar(self.admin)
        self.sin_cambios()
        self.assertEqual(self.leer("/libro/", cliente=self.admin, grupo_id=self.grupo["id"])["modo"], "calificaciones")        # sí lee toda la organización
        self.assertEqual(self.leer("/configuracion/", cliente=self.admin)["niveles"][2]["modo"], "calificaciones")
        self.assertTrue(self.gb("/politica/", {"politica_intentos": "mejor"}, metodo="put", cliente=self.admin)["politica"]["politica_intentos"] == "mejor")

    def test_reportes_lee_toda_la_organizacion_y_no_modifica(self):
        reportes = self.reportes()
        self.assertEqual(self.leer("/libro/", cliente=reportes, grupo_id=self.grupo["id"])["totales"]["alumnos"], 1)
        self.assertEqual(self.leer(f"/calificaciones/{self.cal['id']}/", cliente=reportes)["calificacion"]["id"], self.cal["id"])
        self.intentos_de_modificar(reportes)
        self.sin_cambios()

    def test_el_alumno_no_entra_a_lo_del_profesor_y_solo_lee_lo_suyo(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.intentos_de_modificar(alumno)
        for ruta, params in (("/libro/", {"grupo_id": self.grupo["id"]}), (f"/calificaciones/{self.cal['id']}/", {}), ("/configuracion/", {}), ("/escalas/", {}),
                             (f"/estudiantes/{self.estudiante_id}/", {})):
            self.assertEqual(alumno.get(f"{GB}{ruta}", params).status_code, 403, ruta)
        mias = alumno.get(f"{GB}/mias/").json()
        self.assertEqual(mias["alumno_id"], self.estudiante_id)
        self.assertEqual([x["asignacion_id"] for x in mias["items"]], [self.a["id"]])

    def test_un_alumno_no_ve_lo_de_otro_aunque_lo_declare(self):
        self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {})
        otro_id, hw = self.alumno_con_tableta("Ana", "300999")
        propio = self.leer("/mias/", cliente=self.api, alumno_id=otro_id)["items"]
        self.assertEqual([x for x in propio if x.get("calificacion")], [])                  # lo de Juan no aparece entre lo de Ana


class SesionObligatoriaTests(_ConCalificacion):
    def test_con_la_sesion_obligatoria_nadie_anonimo_entra(self):
        from django.test import override_settings
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            for metodo, ruta in (("get", "/libro/"), ("post", f"/calificaciones/{self.cal['id']}/ajustar/"), ("get", "/mias/"), ("get", "/configuracion/")):
                r = getattr(self.api, metodo)(f"{GB}{ruta}", {"actor": self.docente_id, "alumno_id": self.estudiante_id})
                self.assertEqual(r.status_code, 401, ruta)
        self.sin_cambios()


class BitacoraTests(_ConCalificacion):
    def test_los_asientos_del_libro_no_se_pueden_alterar_ni_borrar(self):
        self.ajustar(self.cal, 85)
        asiento = maudit.Bitacora.objects.filter(accion="calificacion.modificada").first()
        self.assertIsNotNone(asiento)
        for operacion in (lambda: maudit.Bitacora.objects.filter(pk=asiento.pk).update(motivo="otro motivo"), lambda: maudit.Bitacora.objects.filter(pk=asiento.pk).delete()):
            with self.assertRaises(Exception), transaction.atomic():
                operacion()
        asiento.refresh_from_db()
        self.assertNotEqual(asiento.motivo, "otro motivo")

    def test_la_cadena_de_la_bitacora_sigue_integra_tras_calificar_ajustar_y_publicar(self):
        self.ajustar(self.cal, 85)
        self.gb(f"/calificaciones/{self.cal['id']}/publicar/", {})
        self.tecnico_cliente.post(f"{GB}/calificaciones/{self.cal['id']}/ajustar/", {}, format="json")
        r = self.admin.post("/api/auditoria/verificar/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["estado"], r.json()["salto_en"]), ("verificada", None), r.json())

    def test_el_historial_exige_motivo_en_los_cambios_y_numeros_unicos(self):
        """El historial es de sólo inserción por código (el repositorio no tiene operación que lo cambie: ver la prueba de arquitectura); la base además
        impide un ajuste sin motivo y dos versiones con el mismo número."""
        self.ajustar(self.cal, 85)
        version = m.VersionCalificacion.objects.filter(tipo="ajuste").first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.VersionCalificacion.objects.create(calificacion_id=version.calificacion_id, numero=99, tipo="ajuste", motivo="", actor_id="x")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.VersionCalificacion.objects.create(calificacion_id=version.calificacion_id, numero=version.numero, tipo="registro", actor_id="x")
