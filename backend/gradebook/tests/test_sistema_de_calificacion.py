"""
El SISTEMA de calificación a la vista (FUN-124): el profesor ve en el libro qué sistema usa el nivel de su grupo (nombre, país, rango, desde dónde se aprueba y
sus tramos) y el alumno lo ve junto a su nota, tal como se publicó: si la institución cambia de sistema después, la nota ya publicada conserva el suyo.
También: las plantillas de la tabla internacional (España por términos, GPA de Estados Unidos, México de 5 a 10) convierten y aprueban donde deben.
"""
from __future__ import annotations

from decimal import Decimal as D

from ..dominio import escala as esc
from ..dominio import plantillas_escalas as plantillas
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
