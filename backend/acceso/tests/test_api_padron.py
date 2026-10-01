"""Padrón del aula desde OPS: `/api/acceso/padron/…` (registrar estudiantes y asociarlos a un grupo)."""
from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .base import ARGON2_RAPIDO, BaseAcceso


@override_settings(AVACOM_LMS_ARGON2=ARGON2_RAPIDO)
class PadronPrototipoTests(TestCase):
    """Sin sesión (Q-34 abierta): es el modo en que se prueba el modo repaso en el equipo de desarrollo."""

    def setUp(self):
        self.api = APIClient()

    def preparar(self):
        r = self.api.post("/api/acceso/padron/preparar/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def grupo(self, nombre="Sexto A", **extra):
        r = self.api.post("/api/acceso/padron/grupos/", {"nombre": nombre, **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def test_nodo_vacio_no_es_error_y_dice_que_no_esta_instalado(self):
        r = self.api.get("/api/acceso/padron/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"instalado": False, "organizacion": None, "grupos": [], "sin_grupo": []})

    def test_sin_organizacion_no_se_puede_registrar_nada(self):
        r = self.api.post("/api/acceso/padron/grupos/", {"nombre": "Sexto A"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "no_instalado")

    def test_preparar_el_aula_de_prueba_una_sola_vez(self):
        org = self.preparar()["organizacion"]
        self.assertEqual(org["codigo"], "AULA-PRUEBA")
        self.assertNotIn("password_inicial", org)
        self.assertTrue(self.api.get("/api/acceso/padron/").json()["instalado"])
        r = self.api.post("/api/acceso/padron/preparar/", {}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_el_grupo_toma_codigo_del_nombre_y_periodo_del_anio(self):
        self.preparar()
        g = self.grupo("Sexto A", nivel_clave="secundaria")
        self.assertEqual(g["codigo"], "SEXTO-A")
        self.assertRegex(g["periodo"], r"^\d{4}$")
        self.assertEqual(g["nivel_clave"], "secundaria")

    def test_dos_grupos_con_el_mismo_codigo_y_periodo_chocan(self):
        self.preparar()
        self.grupo("Sexto A")
        r = self.api.post("/api/acceso/padron/grupos/", {"nombre": "sexto a"}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_registrar_estudiante_con_su_grupo_sin_documento_ni_pin(self):
        self.preparar()
        g = self.grupo()
        r = self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Juan", "apellidos": "Pérez", "grupo_id": g["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        e = r.json()
        self.assertEqual(e["alias"], "Juan Pérez")
        self.assertTrue(e["identificador"].startswith("AULA-PRUEBA-"))   # la clave la emite el nodo (DEC-049)
        self.assertTrue(e["secreto_inicial"])                            # el PIN generado se entrega una sola vez
        estado = self.api.get("/api/acceso/padron/").json()
        grupo = estado["grupos"][0]
        self.assertEqual([x["alias"] for x in grupo["estudiantes"]], ["Juan Pérez"])
        self.assertEqual(estado["sin_grupo"], [])

    def test_registrar_con_documento_y_pin_propios(self):
        self.preparar()
        g = self.grupo()
        r = self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Ana", "documento": "122499", "pin": "691302", "grupo_id": g["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["identificador"], "122499")
        self.assertNotIn("secreto_inicial", r.json())
        # y con ese documento y ese PIN la persona entra (el padrón y el acceso son la misma identidad)
        l = self.api.post("/api/acceso/sesiones/", {"identificador": "122499", "secreto": "691302"}, format="json")
        self.assertEqual(l.status_code, 200, l.content)

    def test_documento_repetido_no_duplica_la_persona(self):
        self.preparar()
        g = self.grupo()
        cuerpo = {"nombres": "Ana", "documento": "122499", "grupo_id": g["id"]}
        self.assertEqual(self.api.post("/api/acceso/padron/estudiantes/", cuerpo, format="json").status_code, 201)
        r = self.api.post("/api/acceso/padron/estudiantes/", {**cuerpo, "nombres": "Otra"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "identificador_duplicado")

    def test_faltan_nombres_o_grupo(self):
        self.preparar()
        g = self.grupo()
        self.assertEqual(self.api.post("/api/acceso/padron/estudiantes/", {"nombres": " ", "grupo_id": g["id"]}, format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Ana"}, format="json").status_code, 400)
        r = self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Ana", "grupo_id": "no-existe"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_matricular_en_otro_grupo_y_retirar(self):
        self.preparar()
        a, b = self.grupo("Sexto A"), self.grupo("Sexto B")
        e = self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Juan", "grupo_id": a["id"]}, format="json").json()
        r = self.api.post(f"/api/acceso/padron/grupos/{b['id']}/estudiantes/", {"usuario_id": e["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.api.post(f"/api/acceso/padron/grupos/{b['id']}/estudiantes/", {"usuario_id": e["id"]}, format="json")
        self.assertEqual(r.status_code, 200)   # ya estaba
        grupos = {g["codigo"]: g for g in self.api.get("/api/acceso/padron/").json()["grupos"]}
        self.assertEqual(len(grupos["SEXTO-A"]["estudiantes"]), 1)
        self.assertEqual(len(grupos["SEXTO-B"]["estudiantes"]), 1)
        self.assertEqual(self.api.delete(f"/api/acceso/padron/grupos/{a['id']}/estudiantes/{e['id']}/").status_code, 204)
        estado = self.api.get("/api/acceso/padron/").json()
        grupos = {g["codigo"]: g for g in estado["grupos"]}
        self.assertEqual(grupos["SEXTO-A"]["estudiantes"], [])
        self.assertEqual(len(grupos["SEXTO-B"]["estudiantes"]), 1)

    def test_quien_salio_del_grupo_puede_volver(self):
        """Regresión: reingresar chocaba con UNIQUE(grupo, usuario, papel) y daba 500; ahora reabre la pertenencia."""
        self.preparar()
        a = self.grupo()
        e = self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Juan", "grupo_id": a["id"]}, format="json").json()
        self.api.delete(f"/api/acceso/padron/grupos/{a['id']}/estudiantes/{e['id']}/")
        r = self.api.post(f"/api/acceso/padron/grupos/{a['id']}/estudiantes/", {"usuario_id": e["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.json()["ya_estaba"])
        estado = self.api.get("/api/acceso/padron/").json()
        self.assertEqual([x["id"] for x in estado["grupos"][0]["estudiantes"]], [e["id"]])
        self.assertEqual(estado["sin_grupo"], [])
        # y sigue habiendo UNA sola fila de pertenencia
        from acceso.models import MiembroGrupo
        self.assertEqual(MiembroGrupo.objects.filter(grupo_id=a["id"], usuario_id=e["id"]).count(), 1)

    def test_el_estudiante_que_sale_del_unico_grupo_queda_sin_grupo(self):
        self.preparar()
        a = self.grupo()
        e = self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Juan", "grupo_id": a["id"]}, format="json").json()
        self.api.delete(f"/api/acceso/padron/grupos/{a['id']}/estudiantes/{e['id']}/")
        self.assertEqual([x["id"] for x in self.api.get("/api/acceso/padron/").json()["sin_grupo"]], [e["id"]])

    def test_el_modo_de_estudio_ve_a_los_registrados(self):
        self.preparar()
        g = self.grupo()
        self.api.post("/api/acceso/padron/estudiantes/", {"nombres": "Juan", "apellidos": "Pérez", "grupo_id": g["id"]}, format="json")
        r = self.api.get("/api/modo-estudio/docente/grupos/")
        self.assertEqual(r.status_code, 200, r.content)
        grupos = r.json()["grupos"]
        self.assertEqual(grupos[0]["id"], g["id"])
        self.assertEqual([a["rotulo"] for a in grupos[0]["alumnos"]], ["Juan Pérez"])

    @override_settings(AVACOM_LMS_EXIGIR_SESION=True)
    def test_si_el_nodo_exige_sesion_nada_de_esto_es_anonimo(self):
        for metodo, ruta in (("get", "/api/acceso/padron/"), ("post", "/api/acceso/padron/preparar/"),
                             ("post", "/api/acceso/padron/grupos/"), ("post", "/api/acceso/padron/estudiantes/")):
            r = getattr(self.api, metodo)(ruta, {} if metodo == "post" else None, format="json") if metodo == "post" else self.api.get(ruta)
            self.assertEqual(r.status_code, 401, (ruta, r.content))


class PadronConSesionTests(BaseAcceso):
    """Con sesión rige lo de siempre: el docente sólo registra en SUS grupos y sólo la administración crea grupos."""

    def test_el_docente_registra_en_su_grupo(self):
        r = self.docente.post("/api/acceso/padron/estudiantes/", {"nombres": "Luisa", "grupo_id": self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_el_docente_no_registra_en_un_grupo_ajeno(self):
        r = self.docente.post("/api/acceso/padron/estudiantes/", {"nombres": "Luisa", "grupo_id": self.otro_grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 403, r.content)

    def test_el_docente_no_crea_grupos_la_administracion_si(self):
        self.assertEqual(self.docente.post("/api/acceso/padron/grupos/", {"nombre": "Décimo"}, format="json").status_code, 403)
        self.assertEqual(self.admin.post("/api/acceso/padron/grupos/", {"nombre": "Décimo"}, format="json").status_code, 201)

    def test_el_padron_del_docente_muestra_solo_sus_grupos(self):
        estado = self.docente.get("/api/acceso/padron/").json()
        self.assertTrue(estado["instalado"])
        self.assertEqual([g["codigo"] for g in estado["grupos"]], ["8A"])
        self.assertEqual([e["alias"] for e in estado["grupos"][0]["estudiantes"]], ["Juan P."])
        self.assertEqual(self.admin.get("/api/acceso/padron/").json()["grupos"].__len__(), 2)

    def test_matricular_y_retirar_con_sesion_de_docente(self):
        nuevo = self.docente.post("/api/acceso/padron/estudiantes/", {"nombres": "Luisa", "grupo_id": self.grupo["id"]}, format="json").json()
        self.assertEqual(self.docente.delete(f"/api/acceso/padron/grupos/{self.grupo['id']}/estudiantes/{nuevo['id']}/").status_code, 204)
        # un docente no puede meter a nadie en un grupo que no es suyo
        r = self.docente.post(f"/api/acceso/padron/grupos/{self.otro_grupo['id']}/estudiantes/", {"usuario_id": nuevo["id"]}, format="json")
        self.assertEqual(r.status_code, 403, r.content)

    def test_preparar_con_el_nodo_ya_instalado_es_409(self):
        self.assertEqual(self.admin.post("/api/acceso/padron/preparar/", {}, format="json").status_code, 409)
