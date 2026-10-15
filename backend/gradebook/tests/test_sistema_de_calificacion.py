"""
El SISTEMA de calificación a la vista (FUN-124): el profesor ve en el libro qué sistema usa el nivel de su grupo (nombre, país, rango, desde dónde se aprueba y
sus tramos) y el alumno lo ve junto a su nota, tal como se publicó: si la institución cambia de sistema después, la nota ya publicada conserva el suyo.
También: las plantillas de la tabla internacional (España por términos, GPA de Estados Unidos, México de 5 a 10) convierten y aprueban donde deben.
"""
from __future__ import annotations

from decimal import Decimal as D

from ..dominio import escala as esc
from ..dominio import plantillas_escalas as plantillas
from evaluacion import models as m10
from evaluacion.dominio import catalogos as cat10

from .. import models as m
from .base import GB, BaseGradebook


class PlantillasDeLaTablaTests(BaseGradebook):
    activar_modo = False

    def convertir(self, codigo: str, x: str):
        return esc.convertir(D(x), plantillas.plantilla(codigo).definicion)

    def test_espana_primaria_y_eso_se_califica_con_terminos_y_se_aprueba_desde_suficiente(self):
        self.assertEqual([self.convertir("es-terminos", x).clave for x in ("0", "49.99", "50", "60", "70", "90", "100")], ["IN", "IN", "SU", "BI", "NT", "SB", "SB"])
        self.assertEqual([self.convertir("es-terminos", x).cumple_criterio for x in ("49.99", "50")], [False, True])
        self.assertEqual(self.convertir("es-terminos", "75").etiqueta, "Notable")
        # Bachillerato conserva la escala 0–10 con los mismos términos.
        self.assertEqual((self.convertir("es-0-10", "50").etiqueta, self.convertir("es-0-10", "50").cumple_criterio), ("5.0", True))

    def test_estados_unidos_gpa_va_de_cero_a_cuatro_y_no_aprueba_por_redondeo(self):
        self.assertEqual([self.convertir("us-gpa", x).etiqueta for x in ("0", "85", "90", "100")], ["0.00", "3.50", "4.00", "4.00"])
        self.assertEqual([(self.convertir("us-gpa", x).etiqueta, self.convertir("us-gpa", x).cumple_criterio) for x in ("59.99", "60")], [("0.99", False), ("1.00", True)])
        self.assertEqual([self.convertir("us-gpa", x).desempeno_clave for x in ("59", "60", "75", "85", "95")], ["F", "D", "C", "B", "A"])

    def test_mexico_de_5_a_10_empieza_en_cinco_y_aprueba_con_seis_al_sesenta_por_ciento(self):
        self.assertEqual([self.convertir("mx-5-10", x).etiqueta for x in ("0", "59.99", "60", "80", "100")], ["5.0", "5.9", "6.0", "8.0", "10.0"])
        self.assertEqual([self.convertir("mx-5-10", x).cumple_criterio for x in ("59.99", "60")], [False, True])

    def test_las_nuevas_plantillas_estan_en_el_catalogo_validas_y_con_sus_niveles(self):
        por_codigo = {p["codigo"]: p for p in self.leer("/escalas/plantillas/")["plantillas"]}
        for codigo, pais, niveles in (("es-terminos", "ES", ["primaria", "secundaria"]), ("us-gpa", "US", ["secundaria", "bachillerato", "preuniversitario"]),
                                      ("mx-5-10", "MX", ["primaria", "secundaria"])):
            self.assertEqual((por_codigo[codigo]["pais"], por_codigo[codigo]["niveles"], por_codigo[codigo]["problemas"]), (pais, niveles, []))

    def test_describir_dice_el_rango_el_minimo_y_los_tramos_de_cada_sistema(self):
        co = esc.describir(plantillas.plantilla("co-1-5").definicion)
        self.assertEqual((co["valor_min"], co["valor_max"], co["aprobacion_minima"], co["aprueba_desde"]), (1.0, 5.0, 3.0, "Básico"))
        self.assertEqual([(t["clave"], t["aprueba"]) for t in co["tramos"]], [("bajo", False), ("basico", True), ("alto", True), ("superior", True)])
        terminos = esc.describir(plantillas.plantilla("es-terminos").definicion)
        self.assertEqual((terminos["valor_min"], terminos["aprobacion_minima"], terminos["aprueba_desde"]), (None, None, "Suficiente"))
        peru = esc.describir(plantillas.plantilla("pe-literal").definicion)           # las competencias no fijan un umbral de aprobación
        self.assertEqual((peru["aprobacion_minima"], peru["aprueba_desde"]), (None, None))
        generica = esc.describir(plantillas.plantilla("gen-0-10").definicion)
        self.assertEqual((generica["valor_max"], generica["aprobacion_minima"], generica["aprueba_desde"], generica["tramos"]), (10.0, None, None, []))


class SistemaVisibleTests(BaseGradebook):
    plantilla = "co-1-5"

    def publicar_la_de_juan(self) -> dict:
        _, intento, _, _ = self.examen_entregado(abiertas=False)
        cal = self.calificacion(intento)
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        return cal

    def lo_de_juan(self) -> dict:
        return self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]

    def test_el_profesor_ve_en_el_libro_y_en_la_configuracion_el_sistema_del_nivel(self):
        e = self.libro()["escala"]
        self.assertEqual((e["codigo"], e["pais"], e["tipo"], e["valor_min"], e["valor_max"], e["aprobacion_minima"], e["aprueba_desde"]),
                         ("co-1-5", "CO", "numerica", 1.0, 5.0, 3.0, "Básico"))
        self.assertEqual([t["etiqueta"] for t in e["tramos"]], ["Bajo", "Básico", "Alto", "Superior"])
        nivel = next(n for n in self.leer("/configuracion/")["niveles"] if n["nivel_clave"] == "secundaria")
        self.assertEqual((nivel["escala"]["pais"], nivel["escala"]["aprueba_desde"]), ("CO", "Básico"))

    def test_el_detalle_de_la_calificacion_dice_con_que_sistema_se_presento(self):
        cal = self.publicar_la_de_juan()
        d = self.leer(f"/calificaciones/{cal['id']}/")
        self.assertEqual((d["sistema"]["codigo"], d["sistema"]["pais"], d["sistema"]["aprobacion_minima"], d["sistema"]["aprueba_desde"]), ("co-1-5", "CO", 3.0, "Básico"))
        # Cambiar de sistema después no cambia el de una nota publicada.
        nueva = self.adoptar("es-0-10")
        self.admin.put(f"{GB}/niveles/secundaria/", {"modo": "calificaciones", "escala_id": nueva["id"]}, format="json")
        self.assertEqual(self.leer(f"/calificaciones/{cal['id']}/")["sistema"]["pais"], "CO")

    def test_en_modo_simple_no_hay_sistema_que_mostrar(self):
        r = self.admin.post("/api/acceso/grupos/", {"codigo": "P1", "nombre": "Párvulos", "periodo": "2026", "nivel_clave": "preescolar"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        grupo_id = r.json()["id"]
        self.admin.post(f"/api/acceso/grupos/{grupo_id}/miembros/", {"usuario_id": self.docente_id, "papel": "DOCENTE"}, format="json")
        libro = self.libro(grupo_id=grupo_id)
        self.assertEqual((libro["modo"], libro["escala"]), ("simple", None))

    def test_el_alumno_ve_con_su_nota_el_sistema_con_que_se_publico(self):
        self.publicar_la_de_juan()
        item = self.lo_de_juan()
        self.assertEqual(item["estado"], "publicado")
        e = item["calificacion"]["escala"]
        self.assertEqual((e["nombre"], e["pais"], e["valor_min"], e["valor_max"], e["aprobacion_minima"], e["aprueba_desde"]),
                         (self.escala["nombre"], "CO", 1.0, 5.0, 3.0, "Básico"))
        self.assertEqual([t["clave"] for t in e["tramos"]], ["bajo", "basico", "alto", "superior"])

    def test_antes_de_publicar_el_alumno_no_ve_nada_de_la_nota_ni_del_sistema(self):
        _, intento, _, _ = self.examen_entregado(abiertas=False)
        self.calificacion(intento)
        item = self.lo_de_juan()
        self.assertIsNone(item["calificacion"])
        self.assertNotIn("Básico", str(item))

    def test_si_la_institucion_cambia_de_sistema_la_nota_ya_publicada_conserva_el_suyo(self):
        self.publicar_la_de_juan()
        nueva = self.adoptar("es-0-10")
        r = self.admin.put(f"{GB}/niveles/secundaria/", {"modo": "calificaciones", "escala_id": nueva["id"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.libro()["escala"]["pais"], "ES")                            # el nivel ya usa el sistema español…
        e = self.lo_de_juan()["calificacion"]["escala"]
        self.assertEqual((e["pais"], e["aprobacion_minima"], e["aprueba_desde"]), ("CO", 3.0, "Básico"))     # …y la nota publicada sigue siendo la colombiana


class NivelDelGrupoTests(BaseGradebook):
    """Un grupo sin nivel está siempre en modo simple (el sistema de calificación se elige por nivel): quien lo administra puede asignarle uno desde OPS."""

    def sin_nivel(self) -> dict:
        r = self.admin.post("/api/acceso/grupos/", {"codigo": "OB", "nombre": "Octavo B", "periodo": "2026"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        grupo = r.json()
        self.assertFalse(grupo["nivel_clave"])
        self.admin.post(f"/api/acceso/grupos/{grupo['id']}/miembros/", {"usuario_id": self.docente_id, "papel": "DOCENTE"}, format="json")
        return grupo

    def test_un_grupo_sin_nivel_esta_en_modo_simple_aunque_el_nivel_secundaria_tenga_sistema(self):
        grupo = self.sin_nivel()
        libro = self.libro(grupo_id=grupo["id"])
        self.assertEqual((libro["modo"], libro["escala"], libro["grupo"]["nivel_clave"]), ("simple", None, ""))

    def test_el_profesor_asigna_el_nivel_de_su_grupo_y_el_libro_pasa_al_sistema_de_ese_nivel(self):
        grupo = self.sin_nivel()
        r = self.docente.patch(f"/api/acceso/grupos/{grupo['id']}/", {"nivel_clave": "secundaria"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        libro = self.libro(grupo_id=grupo["id"])
        self.assertEqual((libro["modo"], libro["escala"]["codigo"], libro["grupo"]["nivel_clave"]), ("calificaciones", "gen-0-100", "secundaria"))

    def test_el_profesor_no_cambia_el_nivel_de_un_grupo_que_no_es_suyo(self):
        r = self.docente.patch(f"/api/acceso/grupos/{self.otro_grupo['id']}/", {"nivel_clave": "primaria"}, format="json")
        self.assertEqual(r.status_code, 403, r.content)


class EvaluacionCalificadaAntesDelSistemaTests(BaseGradebook):
    """Julian completó su examen cuando el nivel estaba en modo simple; después la administración eligió el sistema. Pasar de modo NO registra nada solo (D-2), así que su celda
    decía «sin registro» y no había nota que ver: el profesor registra lo ya calificado y la nota sale con el sistema elegido (sin publicar: publicar es otra decisión)."""

    activar_modo = False
    plantilla = "co-1-5"

    def examen_ya_calificado_y_sistema_elegido(self, **extra):
        a, i, _, _ = self.examen_entregado(abiertas=False, **extra)
        self.sincronizar()
        self.assertEqual(m.Calificacion.objects.count(), 0)                              # en modo simple no hay calificación registrada
        m10.Asignacion.objects.filter(pk=a["id"]).update(estado=cat10.CERRADA, cerrada_en=1)          # terminó: ya no impide cambiar el modo del nivel
        self.avanzar(seg=5)
        self.activar_calificaciones(self.nivel, self.plantilla)
        self.sincronizar()
        return a, i

    def celda(self, a: dict) -> dict:
        return self.libro()["alumnos"][0]["celdas"][a["id"]]

    def test_antes_de_registrar_la_celda_dice_sin_registro_y_no_hay_nota(self):
        a, _ = self.examen_ya_calificado_y_sistema_elegido()
        celda = self.celda(a)
        self.assertEqual((celda["estado"], celda["calificacion_id"], celda["presentacion"]), ("sin_registro", None, None))

    def test_registrar_la_evaluacion_hace_aparecer_la_nota_con_el_sistema_elegido(self):
        a, i = self.examen_ya_calificado_y_sistema_elegido()
        r = self.gb(f"/asignaciones/{a['id']}/registrar/", {})
        self.assertEqual((r["registradas"], r["ya_registradas"], r["no_registrables"], r["en_modo_simple"]), (1, 0, [], 0))
        celda = self.celda(a)
        self.assertEqual((celda["estado"], celda["publicada"]), ("revisado", False))
        self.assertTrue(celda["presentacion"]["provisional"])                             # sin publicar: provisional
        self.assertEqual(celda["presentacion"]["escala"]["codigo"], "co-1-5")            # con el sistema elegido
        self.assertIsNotNone(celda["presentacion"]["presentada"]["valor"])
        self.assertEqual(m.Calificacion.objects.get(intento_id=i).estado, "revisada")

    def test_registrar_dos_veces_no_duplica_y_el_alumno_no_ve_nada_hasta_publicar(self):
        a, i = self.examen_ya_calificado_y_sistema_elegido()
        self.gb(f"/asignaciones/{a['id']}/registrar/", {})
        otra = self.gb(f"/asignaciones/{a['id']}/registrar/", {})
        self.assertEqual((otra["registradas"], otra["ya_registradas"]), (0, 1))
        self.assertEqual(m.Calificacion.objects.filter(intento_id=i).count(), 1)
        item = self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]
        self.assertIsNone(item["calificacion"])
        self.assertNotIn("valor", str(item))
        cal = self.calificacion(i)
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        item = self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]
        self.assertEqual(item["calificacion"]["escala"]["codigo"], "co-1-5")

    def test_lo_que_aun_no_se_puede_registrar_se_cuenta_con_su_motivo(self):
        a, i, _, _ = self.examen_entregado(abiertas=True)                                 # con abiertas: queda en revisión docente
        m10.Asignacion.objects.filter(pk=a["id"]).update(estado=cat10.CERRADA, cerrada_en=1)
        self.activar_calificaciones(self.nivel, self.plantilla)
        r = self.gb(f"/asignaciones/{a['id']}/registrar/", {})
        self.assertEqual((r["registradas"], len(r["no_registrables"])), (0, 1))
        self.assertEqual((r["no_registrables"][0]["intento_id"], r["no_registrables"][0]["motivo"]), (i, "revision_pendiente"))

    def test_en_un_nivel_en_modo_simple_no_se_registra_nada_y_se_dice(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        r = self.gb(f"/asignaciones/{a['id']}/registrar/", {})
        self.assertEqual((r["registradas"], r["en_modo_simple"]), (0, 1))
        self.assertEqual(m.Calificacion.objects.count(), 0)

    def test_quien_no_enseña_en_ese_grupo_no_registra(self):
        a, _ = self.examen_ya_calificado_y_sistema_elegido()
        _, ruiz, _ = self.otro_docente()
        self.gb(f"/asignaciones/{a['id']}/registrar/", {}, cliente=ruiz, esperado=403)
        self.assertEqual(m.Calificacion.objects.count(), 0)
