"""
Autorización real de la clase (007-10) con el módulo de acceso instalado y sesiones JWT de verdad: los once permisos
`classroom.*` existen y los conceden el rol de profesor (sobre sus grupos) y el de administración; la clase la opera su
profesor titular o la administración, nunca otro profesor ni un alumno; y una tableta sólo habla por su propia persona.
"""
from __future__ import annotations

from acceso.models import Permiso, Rol, RolPermiso
from acceso.tests.base import BaseAcceso

from .. import models as m
from ..dominio import sesion as dom

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"


class ConClaseConSesiones(BaseAcceso):
    def setUp(self):
        super().setUp()
        # un segundo profesor, con su propia sesión
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "TEACHER", "alias": "Prof. Ruiz", "persona": {"nombres": "Marta", "apellidos": "Ruiz"},
            "identificadores": [{"tipo": "DNI", "valor": "52.987.654", "es_login": True}],
            "secreto": "Otro.Docente.2026!", "secreto_definitivo": True}, format="json")
        assert r.status_code == 201, r.content
        self.otro_docente_id = r.json()["id"]
        self.otro_docente = self.sesion("52.987.654", "Otro.Docente.2026!")
        self.alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)

    def iniciar(self, cliente=None, **extra):
        cuerpo = {"via": "leccion", "curso_ref": CURSO, "leccion_ref": "l1-three-states", "fuente": "ejemplo",
                  "grupo_id": self.grupo["id"], **extra}
        return (cliente or self.docente).post("/api/aula/sesiones/", cuerpo, format="json")

    def ruta(self, sesion, resto=""):
        return f"/api/aula/sesiones/{sesion['id']}/{resto}"


class PermisosSembradosTests(ConClaseConSesiones):
    def test_los_once_permisos_existen_y_los_concede_el_profesor_y_la_administracion(self):
        codigos = set(Permiso.objects.filter(codigo__startswith="classroom.").values_list("codigo", flat=True))
        self.assertEqual(codigos, set(dom.PERMISOS))
        for rol in ("TEACHER", "ADMIN"):
            concedidos = set(RolPermiso.objects.filter(rol=Rol.objects.get(codigo=rol, organizacion__isnull=True),
                                                       permiso__codigo__startswith="classroom.").values_list("permiso_id", flat=True))
            self.assertEqual(concedidos, set(dom.PERMISOS), rol)
        self.assertFalse(RolPermiso.objects.filter(rol=Rol.objects.get(codigo="STUDENT", organizacion__isnull=True),
                                                   permiso__codigo__startswith="classroom.").exists())


class TitularidadTests(ConClaseConSesiones):
    def test_el_profesor_inicia_y_opera_su_clase_con_su_identidad_del_token(self):
        r = self.iniciar()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["profesor_id"], self.docente_id)          # el JWT manda, no el cuerpo
        r = self.iniciar(cliente=self.docente, profesor_id="impostor")
        self.assertEqual(r.status_code, 409)                                # ya tiene una abierta: es él
        self.assertEqual(r.json()["codigo"], "sesion_activa_existente")

    def test_otro_profesor_no_opera_la_clase_ajena(self):
        s = self.iniciar().json()
        for metodo, resto, cuerpo in (
            ("post", "selector/", {"objeto_ref": "l1-lecture"}),
            ("post", "controles/", {"tipo": "bloqueo", "activo": True}),
            ("post", "distribuciones/", {"clase": "recurso", "media_ref": "pdf-lab-guide"}),
            ("post", "avisos/", {"texto": "hola"}),
            ("post", "codigo/rotar/", {}),
            ("post", "suspender/", {"causa": "manual"}),
            ("post", "cerrar/", {}),
        ):
            r = getattr(self.otro_docente, metodo)(self.ruta(s, resto), cuerpo, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"), resto)
        self.assertEqual(m.SesionDeClase.objects.get(pk=s["id"]).estado, "abierta")

    def test_la_administracion_puede_operar_cualquier_clase(self):
        s = self.iniciar().json()
        r = self.admin.post(self.ruta(s, "avisos/"), {"texto": "Aviso de dirección"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.admin.post(self.ruta(s, "cerrar/"), {"origen": "administrador"}, format="json")
        self.assertEqual((r.status_code, r.json()["origen_cierre"]), (200, "administrador"))

    def test_suspender_y_reanudar_ahora_piden_permiso_y_titularidad(self):
        s = self.iniciar().json()
        self.assertEqual(self.alumno.post(self.ruta(s, "suspender/"), {}, format="json").status_code, 403)
        self.assertEqual(self.docente.post(self.ruta(s, "suspender/"), {"causa": "manual"}, format="json").status_code, 200)
        r = self.otro_docente.post(self.ruta(s, "reanudar/"), {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.alumno.post(self.ruta(s, "reanudar/"), {}, format="json").status_code, 403)
        self.assertEqual(self.docente.post(self.ruta(s, "reanudar/"), {}, format="json").status_code, 200)

    def test_un_rol_al_que_le_falta_el_permiso_no_opera(self):
        s = self.iniciar().json()
        RolPermiso.objects.filter(rol=Rol.objects.get(codigo="TEACHER", organizacion__isnull=True), permiso_id="classroom.present").delete()
        r = self.docente.post(self.ruta(s, "selector/"), {"objeto_ref": "l1-lecture"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        self.assertIn("classroom.present", r.json()["detail"])
        self.assertEqual(self.docente.post(self.ruta(s, "avisos/"), {"texto": "sí puede"}, format="json").status_code, 201)

    def test_el_alumno_no_opera_la_clase_en_ninguna_funcion(self):
        s = self.iniciar().json()
        for resto, cuerpo in (("selector/", {"objeto_ref": "l1-lecture"}), ("controles/", {"tipo": "bloqueo", "activo": True}),
                              ("distribuciones/", {"clase": "recurso", "media_ref": "x"}), ("avisos/", {"texto": "x"}),
                              ("codigo/rotar/", {}), ("cerrar/", {}), ("anclaje/", {"nodos": [{"ref": "x"}]})):
            r = self.alumno.post(self.ruta(s, resto), cuerpo, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"), resto)


class TabletaConSesionTests(ConClaseConSesiones):
    def unirse(self, s, cliente=None, **extra):
        return (cliente or self.alumno).post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "dispositivo": self.TABLETA, **extra},
                                            format="json")

    def test_con_sesion_la_persona_la_fija_el_token(self):
        s = self.iniciar().json()
        r = self.unirse(s, persona_id="otro-alumno")                       # el cuerpo miente: cuenta el JWT
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["participante"]["persona_id"], self.estudiante_id)
        self.assertEqual(r.json()["participante"]["estado"], "conectado")  # está en el padrón del grupo

    def test_una_tableta_solo_habla_por_su_participante(self):
        s = self.iniciar().json()
        pid = self.unirse(s).json()["participante"]["id"]
        # otro alumno con su propia sesión intenta hablar por el participante de Juan
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": "Luisa", "persona": {"nombres": "Luisa", "apellidos": "Mora", "fecha_nacimiento": "2012-01-02"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "122500", "es_login": True}],
            "secreto": "482913", "secreto_definitivo": True, "grupo_id": self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        intruso = self.sesion("122500", "482913")
        base = self.ruta(s)
        self.assertEqual(intruso.post(f"{base}participantes/{pid}/presencia/", {"estado": "salio"}, format="json").status_code, 403)
        r403 = intruso.get(f"{base}estado/?participante={pid}")
        self.assertEqual((r403.status_code, r403.json()["codigo"]), (403, "persona_ajena"))   # la tableta lo distingue y conserva la cola de la otra persona
        self.assertEqual(intruso.post(f"{base}participantes/{pid}/ayuda/", {"activa": True}, format="json").status_code, 403)
        # él sí
        self.assertEqual(self.alumno.get(f"{base}estado/?participante={pid}").status_code, 200)
        self.assertEqual(self.alumno.post(f"{base}participantes/{pid}/ayuda/", {"activa": True}, format="json").status_code, 200)
        self.assertEqual(m.Participante.objects.get(pk=pid).sesion_usuario_id != "", True)   # la sesión de usuario quedó ligada
