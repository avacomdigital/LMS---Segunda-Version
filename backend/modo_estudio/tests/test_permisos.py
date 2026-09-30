"""
Los ocho permisos `study.*` (§3 del contrato): los siembran las plantillas de MOD-001 y la migración `acceso/0007` (idempotente), y se evalúan con su
política. Los seis del alumno son sólo del rol STUDENT y sobre lo suyo (SELF): la administración NO los tiene («no accede al modo de estudio del alumno»).
`study.assignment.create` y `.review` (del proyecto) son del profesor sobre sus grupos y de la administración. Sin sesión (Q-34) todo se permite.
"""
from __future__ import annotations

import importlib

from django.apps import apps
from django.test import SimpleTestCase, TestCase, override_settings

from acceso.dominio import plantillas
from acceso.dominio.valores import Alcance
from acceso.models import Permiso, Rol, RolPermiso

from ..dominio import catalogos as cat
from .base import BASE, BaseEstudio

ESTUDIO_ALUMNO = set(cat.PERMISOS_DEL_ALUMNO)
ESTUDIO_DOCENTE = set(cat.PERMISOS_DEL_DOCENTE)


class PlantillasTests(SimpleTestCase):
    def test_los_ocho_permisos_estan_en_las_plantillas_con_su_alcance_maximo(self):
        estudio = {c: (modulo, maximo) for c, modulo, _, maximo, _ in plantillas.PERMISOS if c.startswith("study.")}
        self.assertEqual(set(estudio), ESTUDIO_ALUMNO | ESTUDIO_DOCENTE)
        self.assertEqual({modulo for modulo, _ in estudio.values()}, {"estudio"})
        for codigo in ESTUDIO_ALUMNO:
            self.assertIs(estudio[codigo][1], Alcance.SELF, codigo)
        for codigo in ESTUDIO_DOCENTE:
            self.assertIs(estudio[codigo][1], Alcance.ORGANIZATION, codigo)

    def test_el_catalogo_del_modulo_coincide_con_las_plantillas(self):
        self.assertEqual(set(cat.PERMISOS), {c for c, *_ in plantillas.PERMISOS if c.startswith("study.")})
        self.assertEqual(set(plantillas.PERMISOS_DE_ESTUDIO_DEL_ALUMNO), ESTUDIO_ALUMNO)

    def test_cada_rol_recibe_lo_suyo(self):
        roles = {codigo: {c for c in permisos if c.startswith("study.")} for codigo, (_, _, _, permisos) in plantillas.ROLES_SISTEMA.items()}
        self.assertEqual(roles["STUDENT"], ESTUDIO_ALUMNO)
        self.assertEqual(roles["TEACHER"], ESTUDIO_DOCENTE)
        self.assertEqual(roles["ADMIN"], ESTUDIO_DOCENTE)                            # el administrador NO tiene los seis del alumno
        self.assertEqual((roles["REPORTS"], roles["TECHNICIAN"]), (set(), set()))
        student = plantillas.ROLES_SISTEMA["STUDENT"][3]
        self.assertTrue(all(student[c] is Alcance.SELF for c in ESTUDIO_ALUMNO))
        self.assertIs(plantillas.ROLES_SISTEMA["TEACHER"][3]["study.assignment.create"], Alcance.ASSIGNED_GROUPS)
        self.assertIs(plantillas.ROLES_SISTEMA["ADMIN"][3]["study.assignment.review"], Alcance.ORGANIZATION)

    def test_una_sesion_temporal_de_examen_no_estudia(self):
        self.assertFalse(ESTUDIO_ALUMNO & set(plantillas.PERMISOS_SESION_TEMPORAL))

    def test_las_constantes_de_perfil_coinciden_con_las_de_mod_009(self):
        from device_manager.dominio import dispositivo as dom9
        self.assertEqual((cat.COMPARTIDO, cat.ASIGNADO), (dom9.COMPARTIDO, dom9.ASIGNADO))


class SembradoTests(TestCase):
    """Lo que dejan las migraciones (0002/0004 con las plantillas, 0006 y `0007_permisos_estudio`)."""

    def concedidos(self, rol: str) -> dict[str, str]:
        r = Rol.objects.get(codigo=rol, organizacion__isnull=True)
        return {rp.permiso_id: rp.alcance for rp in RolPermiso.objects.filter(rol=r, permiso__codigo__startswith="study.")}

    def test_la_base_recien_migrada_ya_tiene_los_permisos_y_los_roles_con_lo_suyo(self):
        self.assertEqual(set(Permiso.objects.filter(codigo__startswith="study.").values_list("codigo", flat=True)), ESTUDIO_ALUMNO | ESTUDIO_DOCENTE)
        self.assertEqual({p.codigo: p.alcance_maximo for p in Permiso.objects.filter(codigo__startswith="study.")},
                         {**{c: "SELF" for c in ESTUDIO_ALUMNO}, **{c: "ORGANIZATION" for c in ESTUDIO_DOCENTE}})
        self.assertEqual(self.concedidos("STUDENT"), {c: "SELF" for c in ESTUDIO_ALUMNO})
        self.assertEqual(self.concedidos("TEACHER"), {c: "ASSIGNED_GROUPS" for c in ESTUDIO_DOCENTE})
        self.assertEqual(self.concedidos("ADMIN"), {c: "ORGANIZATION" for c in ESTUDIO_DOCENTE})
        self.assertEqual((self.concedidos("REPORTS"), self.concedidos("TECHNICIAN")), ({}, {}))

    def test_la_migracion_0007_es_idempotente_y_repara_una_instalacion_anterior(self):
        migracion = importlib.import_module("acceso.migrations.0007_permisos_estudio")
        antes = (Permiso.objects.filter(codigo__startswith="study.").count(), RolPermiso.objects.filter(permiso__codigo__startswith="study.").count())
        migracion.sembrar(apps, None)
        migracion.sembrar(apps, None)
        self.assertEqual((Permiso.objects.filter(codigo__startswith="study.").count(), RolPermiso.objects.filter(permiso__codigo__startswith="study.").count()), antes)
        # una instalación que ya existía (sin los permisos) los recibe al migrar
        RolPermiso.objects.filter(permiso__codigo__startswith="study.").delete()
        Permiso.objects.filter(codigo__startswith="study.").delete()
        migracion.sembrar(apps, None)
        self.assertEqual(self.concedidos("STUDENT"), {c: "SELF" for c in ESTUDIO_ALUMNO})
        self.assertEqual(self.concedidos("ADMIN"), {c: "ORGANIZATION" for c in ESTUDIO_DOCENTE})
        self.assertEqual(self.concedidos("TEACHER"), {c: "ASSIGNED_GROUPS" for c in ESTUDIO_DOCENTE})
        self.assertNotIn("study.open", self.concedidos("ADMIN"))


class PermisosPorSesionTests(BaseEstudio):
    def codigos(self, cliente) -> dict[str, str]:
        return {p["codigo"]: p["alcance"] for p in cliente.get("/api/acceso/yo/").json()["permisos"] if p["codigo"].startswith("study.")}

    def test_lo_que_ve_cada_perfil_en_su_identidad(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(self.codigos(juan), {c: "SELF" for c in ESTUDIO_ALUMNO})
        self.assertEqual(self.codigos(self.docente), {c: "ASSIGNED_GROUPS" for c in ESTUDIO_DOCENTE})
        self.assertEqual(self.codigos(self.admin), {c: "ORGANIZATION" for c in ESTUDIO_DOCENTE})       # sin los seis del alumno

    def test_con_sesion_de_alumno_las_rutas_del_alumno_funcionan_y_las_del_profesor_no(self):
        self.crear_asignacion()
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.hw_juan)
        self.assertEqual(juan.get(f"{BASE}/asignaciones/").status_code, 200)
        self.assertEqual(self.enviar("post", "/sesion/", cliente=juan).status_code, 200)
        for ruta in ("/docente/grupos/", "/docente/asignaciones/"):
            r = juan.get(f"{BASE}{ruta}")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"), ruta)
        r = juan.post(f"{BASE}/docente/asignaciones/", {"alcance": "grupo", "grupo_id": self.grupo["id"], "curso_ref": "x", "leccion_ref": "y"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

    def llamar(self, cliente, metodo: str, ruta: str, cuerpo: dict | None):
        if metodo in ("get", "delete"):
            return getattr(cliente, metodo)(f"{BASE}{ruta}?dispositivo={self.hw_juan}")
        return getattr(cliente, metodo)(f"{BASE}{ruta}", {"dispositivo": self.hw_juan, **(cuerpo or {})}, format="json")

    def test_con_sesion_de_profesor_o_administracion_las_rutas_del_alumno_son_403(self):
        a = self.crear_asignacion()
        rutas = [("get", "/asignaciones/", None), ("get", f"/asignaciones/{a['id']}/", None), ("get", f"/lecciones/{a['id']}/", None),
                 ("patch", f"/lecciones/{a['id']}/progreso/", {"bloques_vistos": []}), ("post", f"/lecciones/{a['id']}/completar/", {}),
                 ("post", f"/lecciones/{a['id']}/practica/", {}), ("post", "/practicas/x/respuestas/", {"respuestas": []}),
                 ("post", "/practicas/x/terminar/", {}), ("get", "/paquetes/", None), ("post", "/paquetes/", {"asignacion_id": a["id"]}),
                 ("get", "/paquetes/x/", None), ("get", "/paquetes/x/manifiesto/", None), ("post", "/paquetes/x/confirmar/", {"huella": "h"}),
                 ("delete", "/paquetes/x/", None), ("get", f"/asignaciones/{a['id']}/medios/img-particles/", None),
                 ("post", "/sesion/", {}), ("post", "/sesion/cerrar/", {}), ("post", "/sync/", {"emisor_id": "e", "eventos": []}),
                 ("get", "/sync/status/?emisor_id=e", None)]
        for nombre, cliente in (("docente", self.docente), ("admin", self.admin)):
            for metodo, ruta, cuerpo in rutas:
                with self.subTest(perfil=nombre, ruta=ruta, metodo=metodo):
                    r = self.llamar(cliente, metodo, ruta, cuerpo)
                    self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

    def test_sin_sesion_todo_se_permite_como_en_el_aula_y_el_expediente(self):
        a = self.crear_asignacion()
        self.assertEqual(self.ver("/asignaciones/").status_code, 200)
        self.assertEqual(self.api.get(f"{BASE}/docente/grupos/").status_code, 200)
        self.assertEqual(self.ver(f"/lecciones/{a['id']}/").status_code, 200)

    def test_exigir_sesion_cierra_las_rutas_sin_ella_salvo_la_sincronizacion_la_limpieza_y_los_nombres(self):
        """BR-137 · D-11 · D-15: sincronizar no exige sesión (se autoriza por el aparato y el alumno que declara); la limpieza del aparato se avisa DESPUÉS de
        cerrar la sesión; y «¿Quién eres?» se pregunta ANTES de saber quién es la persona."""
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.ver("/asignaciones/").status_code, 401)
            self.assertEqual(self.ver("/estado/").status_code, 401)
            self.assertEqual(self.enviar("post", "/sesion/").status_code, 401)
            self.assertEqual(self.api.get(f"{BASE}/docente/grupos/").status_code, 401)
            juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
            self.assertEqual(self.ver("/estado/", cliente=juan).status_code, 200)
            self.assertEqual(self.enviar("post", "/sync/", {"emisor_id": "e1", "eventos": []}).status_code, 200)          # sin sesión, por el aparato y su dueño
            self.assertEqual(self.ver("/sync/status/", emisor_id="e1").status_code, 200)
            self.assertEqual(self.enviar("post", "/sesion/limpieza/", {"resultado": "completa"}).status_code, 200)
            self.assertEqual(self.ver("/estudiantes/").status_code, 200)                                                 # los nombres, sin sesión ni permiso
            r = self.enviar("post", "/sync/", {"emisor_id": "e1", "eventos": []}, hw=self.hw_compartida)                   # una compartida: hay que decir quién es
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_alumno"))
            r = self.enviar("post", "/sync/", {"emisor_id": "e1", "eventos": [], "alumno_id": self.estudiante_id}, hw=self.hw_compartida)
            self.assertEqual(r.status_code, 200)
