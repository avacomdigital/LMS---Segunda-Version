"""
FUN-124 · El motor de escalas y equivalencias, por la API: las plantillas son sólo un punto de partida; una escala existe cuando la institución la ADOPTA y queda
versionada e inmutable; una definición que no cubre 0–100 completo, sin huecos ni solapamientos, se rechaza con TODOS sus problemas; y la presentación separa el
resultado interno, la calificación presentada, el nivel de desempeño y el criterio de aprobación.
"""
from __future__ import annotations

from .. import models as m
from .base import GB, BaseGradebook


class PlantillasTests(BaseGradebook):
    activar_modo = False

    def test_el_catalogo_trae_los_siete_paises_y_las_genericas_todas_validas(self):
        r = self.leer("/escalas/plantillas/")
        codigos = {p["codigo"] for p in r["plantillas"]}
        self.assertEqual({p["pais"] for p in r["plantillas"]} - {""}, {"ES", "US", "MX", "CO", "CL", "PE", "EC"})
        self.assertTrue({"gen-0-5", "gen-0-10", "gen-0-20", "gen-0-100", "gen-letras", "gen-conceptual"} <= codigos)
        self.assertTrue(all(p["problemas"] == [] for p in r["plantillas"]))
        self.assertTrue(all("orientativa" in p["advertencia"] for p in r["plantillas"]))
        self.assertTrue(all(p["referencia"] for p in r["plantillas"]))
        solo_co = {p["codigo"] for p in self.leer("/escalas/plantillas/", pais="co")["plantillas"]}
        self.assertIn("co-1-5", solo_co)
        self.assertNotIn("es-0-10", solo_co)
        self.assertIn("gen-0-10", solo_co)                                                           # las genéricas siempre

    def test_una_plantilla_sin_adoptar_no_presenta_nada(self):
        self.assertEqual(self.leer("/escalas/")["escalas"], [])
        r = self.gb("/niveles/secundaria/", {"modo": "calificaciones", "escala_id": "gen-0-10"}, metodo="put", cliente=self.admin, esperado=409)
        self.assertEqual(r["codigo"], "escala_no_vigente")                                         # una plantilla no es una escala vigente


class AdopcionTests(BaseGradebook):
    activar_modo = False

    def test_adoptar_crea_la_escala_y_su_version_uno_con_huella(self):
        e = self.adoptar("co-1-5", jurisdiccion="Antioquia", nota="Sistema institucional de evaluación 2026")
        self.assertEqual((e["codigo"], e["pais"], e["jurisdiccion"], e["tipo"], e["plantilla_origen"]), ("co-1-5", "CO", "Antioquia", "numerica", "co-1-5"))
        v = e["versiones"][0]
        self.assertEqual((v["numero"], len(v["huella"]), v["creada_por"]), (1, 64, self.admin_id))
        self.assertEqual(v["definicion"]["tramos"][0]["clave"], "bajo")
        self.assertEqual(self.eventos_gb("calificacion.escala_adoptada.v1"), ["calificacion.escala_adoptada.v1"])
        self.assertEqual(m.EscalaTramo.objects.filter(version_id=v["id"]).count(), 4)
        self.assertEqual(self.adoptar("co-1-5", esperado=400)["codigo"], "datos_invalidos")        # el código ya existe
        self.assertEqual(self.adoptar("no-existe", esperado=400)["codigo"], "datos_invalidos")

    def test_la_institucion_puede_adoptar_la_plantilla_con_sus_ajustes(self):
        base = next(p for p in self.leer("/escalas/plantillas/")["plantillas"] if p["codigo"] == "co-1-5")["definicion"]
        propia = {**base, "aprobacion_minima": "3.5"}
        e = self.adoptar("co-1-5", codigo="co-colegio", nombre="Nuestro 1–5", definicion=propia)
        self.assertEqual(e["versiones"][0]["definicion"]["aprobacion_minima"], "3.5")
        self.assertEqual(e["versiones"][0]["definicion"]["tramos"], base["tramos"])
        r = self.gb("/escalas/vista-previa/", {"escala_version_id": e["versiones"][0]["id"], "valores": [50, 62.5]})
        self.assertEqual([c["aprobacion"]["cumple_criterio"] for c in r["conversiones"]], [False, True])        # 3.0 no alcanza 3.5; 3.5 sí

    def test_solo_la_administracion_adopta_el_profesor_la_lee(self):
        r = self.gb("/escalas/adoptar/", {"plantilla": "gen-0-5"}, cliente=self.docente, esperado=403)
        self.assertEqual((r["codigo"], r["permiso"]), ("sin_permiso", "grades.mode.set"))
        self.assertEqual(self.gb("/escalas/plantillas/", cliente=self.docente, metodo="get")["plantillas"][0]["codigo"], "gen-0-5")
        self.assertEqual(m.Escala.objects.count(), 0)

    def test_una_escala_propia_exige_una_definicion_valida(self):
        definicion = {"tipo": "competencias", "conversion": "tramos", "decimales": 0, "redondeo": "mitad_arriba",
                      "tramos": [{"orden": 1, "clave": "I", "etiqueta": "Inicio", "desde": "0", "hasta": "50", "aprueba": False},
                                 {"orden": 2, "clave": "P", "etiqueta": "En proceso", "desde": "50", "hasta": "80", "aprueba": True},
                                 {"orden": 3, "clave": "L", "etiqueta": "Logrado", "desde": "80", "hasta": "100", "aprueba": True}]}
        e = self.gb("/escalas/", {"codigo": "mi-escala", "nombre": "Mi escala por niveles", "pais": "CO", "definicion": definicion}, cliente=self.admin, esperado=201)
        self.assertEqual((e["tipo"], e["plantilla_origen"]), ("competencias", ""))
        r = self.gb("/escalas/vista-previa/", {"escala_version_id": e["versiones"][0]["id"], "valores": [0, 49.99, 50, 79.99, 80, 100]})
        self.assertEqual([c["presentada"]["clave"] for c in r["conversiones"]], ["I", "I", "P", "P", "L", "L"])


class DefinicionesInvalidasTests(BaseGradebook):
    activar_modo = False

    def numerica(self, **cambios) -> dict:
        base = {"tipo": "numerica", "conversion": "interpolada", "decimales": 1, "redondeo": "mitad_arriba", "valor_min": "0", "valor_max": "10",
                "puntos": [["0", "0"], ["100", "10"]], "aprobacion_minima": "6", "tramos": []}
        return {**base, **cambios}

    def tramos(self, filas, tipo="alfabetica", **extra) -> dict:
        return {"tipo": tipo, "conversion": "tramos", "decimales": 0, "redondeo": "mitad_arriba",
                "tramos": [{"orden": i, "clave": c, "etiqueta": c, "desde": d, "hasta": h, "aprueba": None} for i, (c, d, h) in enumerate(filas, start=1)], **extra}

    def rechazada(self, definicion: dict, texto: str) -> list[str]:
        r = self.gb("/escalas/vista-previa/", {"definicion": definicion}, esperado=400)
        self.assertEqual(r["codigo"], "escala_invalida", r)
        self.assertTrue(any(texto in p for p in r["problemas"]), r["problemas"])
        return r["problemas"]

    def test_hueco_entre_tramos(self):
        self.rechazada(self.tramos([("F", "0", "60"), ("D", "65", "70"), ("A", "70", "100")]), "Hueco entre «F» y «D»")

    def test_solapamiento_entre_tramos(self):
        self.rechazada(self.tramos([("F", "0", "65"), ("D", "60", "70"), ("A", "70", "100")]), "Solapamiento entre «F» y «D»")

    def test_los_tramos_deben_cubrir_de_0_a_100(self):
        self.rechazada(self.tramos([("F", "5", "60"), ("A", "60", "100")]), "empezar en 0")
        self.rechazada(self.tramos([("F", "0", "60"), ("A", "60", "99")]), "terminar en 100")

    def test_limites_mal_definidos(self):
        self.rechazada(self.tramos([("F", "0", "0"), ("A", "0", "100")]), "`desde` menor que `hasta`")
        self.rechazada(self.tramos([("F", "0", "60.123"), ("A", "60.123", "100")]), "dos decimales")
        self.rechazada(self.tramos([("A", "0", "50"), ("A", "50", "100")]), "repetida")
        self.rechazada(self.tramos([("F", "0", "50"), ("A", "50", "120")]), "se sale de 0–100")

    def test_una_escala_numerica_no_puede_decrecer_ni_salirse_de_su_rango(self):
        self.rechazada(self.numerica(puntos=[["0", "10"], ["100", "0"]]), "no pueden decrecer")
        self.rechazada(self.numerica(puntos=[["0", "0"], ["100", "12"]]), "entre `valor_min` y `valor_max`")
        self.rechazada(self.numerica(puntos=[["10", "0"], ["100", "10"]]), "de 0 a 100")
        self.rechazada(self.numerica(puntos=[["0", "0"], ["60", "5"], ["50", "7"], ["100", "10"]]), "estrictamente creciente")
        self.rechazada(self.numerica(aprobacion_minima="11"), "dentro de la escala")
        self.rechazada(self.numerica(valor_min="10", valor_max="0"), "menor que")

    def test_tipo_conversion_decimales_y_redondeo(self):
        problemas = self.rechazada(self.numerica(tipo="astrologica", decimales=9, redondeo="al_ojo"), "`tipo` debe ser")
        self.assertTrue(any("`decimales`" in p for p in problemas) and any("`redondeo`" in p for p in problemas), problemas)
        self.rechazada(self.numerica(conversion="tramos"), "se convierte por `interpolada`")
        self.rechazada(self.tramos([("A", "0", "100")], valor_min="0"), "no lleva valores numéricos")

    def test_se_reportan_todos_los_problemas_juntos(self):
        r = self.gb("/escalas/vista-previa/", {"definicion": self.tramos([("F", "5", "60"), ("D", "65", "70"), ("A", "69", "99")])}, esperado=400)
        self.assertGreaterEqual(len(r["problemas"]), 4)

    def test_la_forma_rota_tambien_se_explica(self):
        r = self.gb("/escalas/vista-previa/", {"definicion": {"tipo": "numerica", "puntos": "mal", "tramos": [1]}}, esperado=400)
        self.assertEqual(r["codigo"], "escala_invalida")
        self.gb("/escalas/vista-previa/", {"definicion": "no es un objeto"}, esperado=400)
        self.gb("/escalas/vista-previa/", {}, esperado=400)


class VersionesTests(BaseGradebook):
    activar_modo = False

    def test_una_version_nueva_no_modifica_la_anterior_y_conserva_el_tipo(self):
        e = self.adoptar("gen-0-10", codigo="decima")
        v1 = e["versiones"][0]
        nueva = self.gb(f"/escalas/{e['id']}/versiones/", {"definicion": {**v1["definicion"], "decimales": 2}, "nota": "Con dos decimales"}, cliente=self.admin, esperado=201)
        self.assertEqual([v["numero"] for v in nueva["versiones"]], [1, 2])
        self.assertEqual(nueva["versiones"][0], v1)                                                   # la 1 no cambió ni en la huella
        self.assertNotEqual(nueva["versiones"][1]["huella"], v1["huella"])
        self.assertEqual(nueva["versiones"][1]["definicion"]["decimales"], 2)
        letras = next(p for p in self.leer("/escalas/plantillas/")["plantillas"] if p["codigo"] == "gen-letras")["definicion"]
        r = self.gb(f"/escalas/{e['id']}/versiones/", {"definicion": letras}, cliente=self.admin, esperado=400)       # una escala numérica no pasa a letras
        self.assertIn("tipo", r["detail"])
        self.gb("/escalas/no-existe/versiones/", {"definicion": v1["definicion"]}, cliente=self.admin, esperado=404)
        self.gb(f"/escalas/{e['id']}/versiones/", {"definicion": v1["definicion"]}, cliente=self.docente, esperado=403)

    def test_no_hay_ruta_para_editar_una_version(self):
        e = self.adoptar("gen-0-10", codigo="decima")
        v = e["versiones"][0]
        for metodo in ("put", "patch", "delete"):
            r = getattr(self.admin, metodo)(f"{GB}/escalas/{e['id']}/versiones/{v['id']}/", {}, format="json")
            self.assertEqual(r.status_code, 404)
            r = getattr(self.admin, metodo)(f"{GB}/escalas/{e['id']}/", {}, format="json")
            self.assertEqual(r.status_code, 405)


class ConversionTests(BaseGradebook):
    activar_modo = False

    def test_la_conversion_separa_interno_presentada_desempeno_y_criterio(self):
        e = self.adoptar("co-1-5")
        r = self.gb("/escalas/vista-previa/", {"escala_version_id": e["versiones"][0]["id"], "valores": [49.99, 50, 90]})
        bajo, basico, superior = r["conversiones"]
        self.assertEqual((bajo["interno"], bajo["presentada"], bajo["aprobacion"]), (49.99, {"valor": 2.9, "etiqueta": "2.9", "clave": "2.9"}, {"cumple_criterio": False}))
        self.assertEqual(bajo["desempeno"]["nivel"], "Bajo")
        self.assertEqual((basico["presentada"]["valor"], basico["desempeno"]["nivel"], basico["aprobacion"]["cumple_criterio"]), (3.0, "Básico", True))
        self.assertEqual((superior["interno"], superior["presentada"]["valor"], superior["desempeno"]["clave"]), (90.0, 4.6, "superior"))
        self.assertEqual(set(bajo), {"interno", "presentada", "desempeno", "aprobacion"})               # cuatro cosas separadas, ninguna sustituye a otra

    def test_la_conversion_no_modifica_el_valor_interno_guardado(self):
        self.activar_calificaciones("secundaria", "gen-0-5")
        a, i, _, _ = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        interno = cal["puntaje_efectivo"]
        self.assertEqual(cal["presentacion"]["presentada"]["valor"], round(interno / 20, 1))
        self.assertEqual(self.fila_cal(i).puntaje_efectivo, self.fila_cal(i).puntaje_original)
        self.assertEqual(float(self.fila_cal(i).puntaje_efectivo), interno)

    def test_valores_de_muestra_fuera_de_rango_se_rechazan(self):
        e = self.adoptar("gen-0-10")
        for malo in ([101], [-1], [85.123], ["x"]):
            self.gb("/escalas/vista-previa/", {"escala_version_id": e["versiones"][0]["id"], "valores": malo}, esperado=400)
        self.gb("/escalas/vista-previa/", {"escala_version_id": e["versiones"][0]["id"], "valores": list(range(201))}, esperado=400)
