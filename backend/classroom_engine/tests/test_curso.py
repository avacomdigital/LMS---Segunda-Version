"""
El endpoint de prueba del curso «Ciencias naturales» (manifiesto de ejemplo) y la
misma vista servida por la biblioteca (host de pruebas con el manifiesto).
"""
from __future__ import annotations

import json
import os
import tempfile

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tools.host_contenido_v2_pruebas import PNG_1x1, HostContenidoV2Pruebas

from ..dominio import catalogos, curso as cur

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"


def manifiesto() -> dict:
    with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
        return json.load(f)


class CursoDeEjemploTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_el_endpoint_de_prueba_entrega_ciencias_naturales(self):
        r = self.api.get("/api/aula/pruebas/curso/")
        self.assertEqual(r.status_code, 200)
        v = r.json()
        self.assertEqual(v["fuente"], "ejemplo")
        self.assertEqual(v["curso_ref"], CURSO)
        self.assertEqual(v["titulo"], "Estados de la materia y sus cambios")
        self.assertEqual(v["version"], "1.0.0")
        self.assertEqual(v["idioma"], "es-CO")
        self.assertEqual(v["clasificacion"]["pais"], "CO")
        self.assertEqual(v["clasificacion"]["asignatura"], {"codigo": "science", "nombre": "Ciencias naturales"})
        self.assertEqual(v["clasificacion"]["nivel"]["codigo"], "lower_secondary")
        self.assertEqual(v["clasificacion"]["grado"]["nombre"], "Sexto")
        self.assertEqual(v["resumen"]["lecciones"], 3)
        self.assertEqual(v["resumen"]["objetos"], 8)
        self.assertEqual(v["resumen"]["objetos_por_tipo"], {"lecture": 2, "explanation": 1, "simulation_lab": 2, "activity": 2, "exam": 1})
        self.assertEqual(v["resumen"]["preguntas"], 9)   # las del examen no viajan al aula
        self.assertEqual(v["resumen"]["fuera_de_alcance"], [{"objeto_ref": "l3-exam", "tipo": "exam", "modulo": "MOD-010"}])
        self.assertEqual(v["portada"]["media_ref"], "img-cover-matter")
        self.assertIn("/medios/img-cover-matter/", v["portada_url"])

    def test_los_objetos_llevan_su_componente_maui(self):
        v = self.api.get("/api/aula/pruebas/curso/").json()
        l1 = v["lecciones"][0]
        self.assertEqual(l1["leccion_ref"], "l1-three-states")
        self.assertEqual([o["componente"] for o in l1["objetos"]], ["presentacion", "lectura", "laboratorio_web", "actividad"])
        self.assertEqual([o["tipo"] for o in l1["objetos"]], ["lecture", "explanation", "simulation_lab", "activity"])
        self.assertEqual(l1["temas"][0]["subtemas"][0], {"tema_ref": "st-solid", "titulo": "Sólido"})

    def test_la_presentacion_trae_laminas_bloques_y_tramos(self):
        v = self.api.get("/api/aula/pruebas/curso/").json()
        lecture = v["lecciones"][0]["objetos"][0]
        self.assertEqual(lecture["total_unidades"], 3)
        s1, s2, s3 = lecture["laminas"]
        self.assertEqual((s1["unidad_ref"], s1["indice"], s1["duracion_seg"]), ("l1-lecture-s1", 1, 240))
        self.assertEqual([b["componente"] for b in s1["bloques"]], ["titulo", "texto"])
        texto = s1["bloques"][1]
        self.assertEqual(texto["estilo"], "definition")
        self.assertEqual(texto["tramos"][0], {"texto": "Materia", "negrita": True, "cursiva": False, "matematica": False})
        self.assertFalse(texto["tramos"][1]["negrita"])
        imagen, lista = s2["bloques"]
        self.assertEqual(imagen["componente"], "imagen")
        self.assertEqual(imagen["url"], f"/api/aula/cursos/{CURSO}/medios/img-particles/?fuente=ejemplo")
        self.assertEqual(imagen["texto_alternativo"][:15], "Tres recipiente")
        self.assertEqual((lista["componente"], lista["ordenada"], len(lista["items"])), ("lista", False, 3))
        self.assertEqual((lista["items_tramos"][0][0]["texto"], lista["items_tramos"][0][0]["negrita"]), ("Sólido:", True))
        video = s3["bloques"][0]
        self.assertEqual((video["componente"], video["desde_seg"], video["hasta_seg"], video["autoplay"]), ("video", 0, 60, False))
        self.assertEqual(video["duracion_seg"], 150.0)
        self.assertEqual((video["ancho"], video["alto"]), (1280, 720))  # proporción real para que el cliente ajuste el alto a la pantalla
        self.assertTrue(video["subtitulos_url"].endswith("/medios/vid-changes/subtitulos?fuente=ejemplo"))

    def test_la_lectura_trae_paginas_con_audio_y_pdf_por_rango(self):
        v = self.api.get("/api/aula/pruebas/curso/").json()
        lectura = v["lecciones"][0]["objetos"][1]
        self.assertEqual(lectura["componente"], "lectura")
        self.assertEqual(len(lectura["paginas"]), 2)
        audio = lectura["paginas"][0]["bloques"][0]
        self.assertEqual((audio["componente"], audio["duracion_seg"]), ("audio", 25.5))
        self.assertTrue(audio["transcripcion_url"].endswith("/medios/aud-summary/transcripcion?fuente=ejemplo"))
        pdf = lectura["paginas"][1]["bloques"][1]
        self.assertEqual((pdf["componente"], pdf["desde_pagina"], pdf["hasta_pagina"], pdf["paginas"]), ("pdf", 1, 3, 3))
        self.assertTrue(pdf["url_pagina_inicial"].endswith("#page=1"))

    def test_el_laboratorio_es_una_webview_con_parametros_de_lanzamiento(self):
        v = self.api.get("/api/aula/pruebas/curso/").json()
        phet = v["lecciones"][0]["objetos"][2]
        self.assertEqual(phet["componente"], "laboratorio_web")
        self.assertEqual(phet["simulacion"]["componente"], "webview")
        self.assertEqual(phet["simulacion"]["simulacion"]["proveedor"], "phet")
        self.assertIn("block_network", phet["simulacion"]["simulacion"]["ajustes"])
        self.assertEqual(phet["simulacion"]["simulacion"]["destinos"], ["screen", "tablet"])
        self.assertTrue(phet["url_lanzamiento"].endswith("/medios/sim-phet-states/states-of-matter-basics_es.html?fuente=ejemplo"))
        self.assertEqual(phet["simulacion"]["licencia"]["tipo"], "cc-by-4.0")
        curva = v["lecciones"][1]["objetos"][1]
        self.assertEqual(curva["parametros_lanzamiento"], {"startTemp": -10, "altitudeMeters": 0})
        self.assertIn("index.html?fuente=ejemplo&startTemp=-10&altitudeMeters=0", curva["url_lanzamiento"])
        self.assertEqual(curva["simulacion"]["simulacion"]["ancho_diseno"], 1280)
        self.assertEqual(len(curva["pasos"]), 3)

    def test_la_actividad_trae_las_seis_clases_de_pregunta_sin_ninguna_clave(self):
        r = self.api.get("/api/aula/pruebas/curso/")
        v = r.json()
        actividad = v["lecciones"][0]["objetos"][3]
        self.assertEqual(actividad["componente"], "actividad")
        self.assertEqual(actividad["ajustes"], {"retroalimentacion": "immediate", "intentos_permitidos": 2,
                                                "barajar_preguntas": False, "barajar_opciones": True, "tiempo_limite_seg": None})
        self.assertEqual([p["componente"] for p in actividad["preguntas"]],
                         ["opcion_multiple", "verdadero_falso", "completar", "relacionar", "ordenar", "abierta"])
        self.assertEqual(actividad["puntos_totales"], 13.0)
        mc, tf, fb, ma, ord_, ab = actividad["preguntas"]
        self.assertEqual([o["opcion_ref"] for o in mc["opciones"]], ["a", "b", "c"])
        self.assertEqual((mc["medios"], mc["opciones"][0]["media_ref"], mc["opciones"][0]["url"]), ([], None, None))
        self.assertFalse(mc["permite_varias"])
        self.assertEqual([o["opcion_ref"] for o in tf["opciones"]], ["true", "false"])
        self.assertEqual(fb["espacios"][0], {"espacio_ref": "b1", "modo_entrada": "select", "opciones": ["propio", "variable"]})
        self.assertEqual(len(ma["izquierda"]), 3)
        self.assertEqual(len(ma["derecha"]), 4)
        # Al alumno «ordenar» le llega barajado (la fuente trae los ítems en el orden que el autor los escribió, y ese puede ser el correcto)
        self.assertCountEqual([e["ref"] for e in ord_["elementos"]], ["o-gas", "o-solid", "o-liquid"])
        self.assertNotEqual([e["ref"] for e in ord_["elementos"]], ["o-gas", "o-solid", "o-liquid"])
        self.assertEqual([e["ref"] for e in ord_["elementos"]], [e["ref"] for e in self.api.get("/api/aula/pruebas/curso/").json()["lecciones"][0]["objetos"][3]["preguntas"][4]["elementos"]])   # y siempre igual
        self.assertEqual((ab["formato_respuesta"], ab["longitud_maxima"]), ("text", 600))
        # Ninguna clave de corrección, ni en camelCase ni en español, en ningún nivel del payload.
        self.assertIsNone(cur.contiene_clave(v))
        texto = r.content.decode("utf-8")
        for prohibida in ("isCorrect", "acceptedAnswers", "modelAnswer", "correctOrder", '"pairs"', '"rubric"', '"answer"', '"feedback"'):
            self.assertNotIn(prohibida, texto)

    def test_el_examen_se_muestra_pero_no_se_ejecuta_en_el_aula(self):
        v = self.api.get("/api/aula/pruebas/curso/").json()
        examen = v["lecciones"][2]["objetos"][0]
        self.assertEqual((examen["componente"], examen["fuera_de_alcance"], examen["modulo"]), ("examen", True, "MOD-010"))
        self.assertEqual(examen["preguntas"], [])
        self.assertEqual(examen["total_preguntas_banco"], 12)
        self.assertEqual(examen["ajustes"]["seleccion"]["cantidad_preguntas"], 4)
        self.assertEqual(examen["ajustes"]["aprobacion_pct"], 60)

    def test_las_notas_del_docente_solo_salen_con_rol_docente(self):
        estudiante = self.api.get("/api/aula/pruebas/curso/").json()
        self.assertNotIn("notas_docente", json.dumps(estudiante))
        docente = self.api.get("/api/aula/pruebas/curso/?rol=docente").json()
        self.assertEqual(docente["rol"], "docente")
        self.assertIn("Curso de cuatro sesiones", docente["notas_docente"]["summary"])
        self.assertIn("timing", docente["lecciones"][0]["notas_docente"])
        self.assertIn("tips", docente["lecciones"][0]["objetos"][0]["notas_docente"])
        self.assertIn("tips", docente["lecciones"][0]["objetos"][0]["laminas"][1]["notas_docente"])
        self.assertIsNone(cur.contiene_clave(docente))   # tampoco el docente recibe claves desde el aula

    def test_la_lista_agrupa_por_asignatura_para_el_panel(self):
        r = self.api.get("/api/aula/cursos/?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertEqual(len(datos["asignaturas"]), 1)
        self.assertEqual(datos["asignaturas"][0]["nombre"], "Ciencias naturales")
        self.assertEqual(datos["asignaturas"][0]["codigo"], "science")
        ficha = datos["asignaturas"][0]["cursos"][0]
        self.assertEqual((ficha["curso_ref"], ficha["lecciones"], ficha["objetos"], ficha["medios"]), (CURSO, 3, 8, 8))
        self.assertEqual(self.api.get("/api/aula/pruebas/cursos/").json()["cursos"][0]["titulo"], ficha["titulo"])

    def test_leccion_y_objeto_sueltos_y_referencias_inexistentes(self):
        r = self.api.get(f"/api/aula/cursos/{CURSO}/lecciones/l2-changes-of-state/?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["leccion"]["titulo"], "Cambios de estado")
        self.assertEqual(r.json()["curso"]["clasificacion"]["asignatura"]["nombre"], "Ciencias naturales")
        r = self.api.get(f"/api/aula/cursos/{CURSO}/objetos/l2-activity/?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["objeto"]["componente"], "actividad")
        self.assertEqual(r.json()["leccion"]["leccion_ref"], "l2-changes-of-state")
        self.assertNotIn("objetos", r.json()["leccion"])
        r = self.api.get(f"/api/aula/cursos/{CURSO}/objetos/no-existe/?fuente=ejemplo")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "referencia_no_encontrada"))
        r = self.api.get("/api/aula/cursos/otro-curso/?fuente=ejemplo")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "curso_no_encontrado"))

    def test_la_fuente_se_resuelve_sola_para_la_referencia_del_ejemplo(self):
        # Sin `?fuente=`: la referencia es la del manifiesto de ejemplo → se sirve aunque la biblioteca no esté.
        r = self.api.get(f"/api/aula/cursos/{CURSO}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["fuente"], "ejemplo")
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/img-particles/")
        self.assertEqual(r.status_code, 200)

    def test_fuente_desconocida_y_biblioteca_ausente(self):
        r = self.api.get("/api/aula/cursos/?fuente=nube")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        # Sin link.json no hay contenido: 503 con motivo y sugerencia, nunca un 500 (§8 del mapeo).
        with override_settings(AVACOM_CONTENIDO_ENLACE_V2=os.path.join(tempfile.gettempdir(), "no-existe-link.json")):
            r = self.api.get("/api/aula/cursos/?fuente=biblioteca")
            self.assertEqual(r.status_code, 503)
            self.assertFalse(r.json()["disponible"])
            self.assertIn("sugerencia", r.json())
            self.assertIn("sin contenido", r.json()["detail"])
            estado = self.api.get("/api/aula/fuente/?fuente=biblioteca")
            self.assertEqual((estado.status_code, estado.json()["disponible"], estado.json()["fuente"]), (200, False, "biblioteca"))
        r = self.api.get("/api/aula/fuente/?fuente=ejemplo").json()
        self.assertEqual((r["fuente"], r["disponible"], r["cursos_instalados"][0]["curso_ref"]), ("ejemplo", True, CURSO))

    def test_la_fuente_de_ejemplo_no_califica(self):
        r = self.api.post(f"/api/aula/cursos/{CURSO}/evaluar/?fuente=ejemplo",
                          {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["a"]}}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (501, "capacidad_ausente"))
        # Pero la forma de la respuesta se valida ANTES de llegar a la fuente: posiciones u opciones inventadas son 400.
        r = self.api.post(f"/api/aula/cursos/{CURSO}/evaluar/?fuente=ejemplo",
                          {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["z"]}}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.api.post(f"/api/aula/cursos/{CURSO}/evaluar/?fuente=ejemplo",
                          {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedIndex": 1}}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.api.post(f"/api/aula/cursos/{CURSO}/evaluar/?fuente=ejemplo", {"objeto_ref": "l3-exam", "pregunta_ref": "l3-q1",
                                                                                "respuesta": {"selectedOptionIds": ["a"]}}, format="json")
        self.assertEqual(r.status_code, 400)          # el examen es de MOD-010: el aula no lo califica
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=ejemplo&version=9.9.9")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "curso_no_encontrado"))

    # ------------------------------------------------------------------- medios
    def test_los_medios_de_ejemplo_son_bytes_validos_de_su_tipo(self):
        base = f"/api/aula/cursos/{CURSO}/medios"
        r = self.api.get(f"{base}/img-particles/?fuente=ejemplo")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        self.assertEqual(r.content[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(r["X-Avacom-Marcador"], "ejemplo")
        r = self.api.head(f"{base}/img-particles/?fuente=ejemplo")
        self.assertEqual((r.status_code, r["Content-Type"], r.content), (200, "image/png", b""))
        r = self.api.get(f"{base}/img-particles/?fuente=ejemplo", HTTP_RANGE="bytes=0-9")
        self.assertEqual((r.status_code, len(r.content)), (206, 10))
        self.assertTrue(r["Content-Range"].startswith("bytes 0-9/"))
        r = self.api.get(f"{base}/aud-summary/?fuente=ejemplo")
        self.assertEqual((r.status_code, r["Content-Type"], r.content[:4]), (200, "audio/wav", b"RIFF"))
        r = self.api.get(f"{base}/pdf-lab-guide/?fuente=ejemplo")
        self.assertEqual((r.status_code, r["Content-Type"], r.content[:5]), (200, "application/pdf", b"%PDF-"))
        self.assertIn(b"/Count 3", r.content)
        r = self.api.get(f"{base}/sim-phet-states/states-of-matter-basics_es.html?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/html"))
        self.assertIn("Estados de la materia: básico (PhET)", r.content.decode("utf-8"))
        r = self.api.get(f"{base}/sim-heating-curve/index.html?fuente=ejemplo&startTemp=-10")
        self.assertEqual(r.status_code, 200)
        self.assertIn("scale(", r.content.decode("utf-8"))      # scale_to_fit
        r = self.api.get(f"{base}/vid-changes/subtitulos?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/vtt"))
        self.assertTrue(r.content.startswith(b"WEBVTT"))
        r = self.api.get(f"{base}/aud-summary/transcripcion?fuente=ejemplo")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/plain"))

    def test_el_video_de_ejemplo_no_se_simula_y_se_explica(self):
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/vid-changes/?fuente=ejemplo")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "referencia_no_encontrada"))
        self.assertIn("sugerencia", r.json())
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/no-existe/?fuente=ejemplo")
        self.assertEqual(r.status_code, 404)
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/sim-phet-states/otro.js?fuente=ejemplo")
        self.assertEqual(r.status_code, 404)


class NormalizadorTests(TestCase):
    def test_tramos_y_texto_plano(self):
        def t(texto, **marcas):
            return {"texto": texto, "negrita": False, "cursiva": False, "matematica": False, **marcas}
        self.assertEqual(cur.tramos("**Gas:** sin forma"), [t("Gas:", negrita=True), t(" sin forma")])
        self.assertEqual(cur.tramos("sin marcado"), [t("sin marcado")])
        self.assertEqual(cur.tramos(""), [])
        self.assertEqual(cur.texto_plano("a **b** c"), "a b c")
        # El subconjunto AVACOM Markdown del esquema 1.0: *cursiva* y matemática en línea $...$ (legible, sin LaTeX).
        self.assertEqual(cur.tramos("El *volumen* mide $\\frac{1}{3} \\times 2$ litros"),
                         [t("El "), t("volumen", cursiva=True), t(" mide "), t("1/3 × 2", matematica=True), t(" litros")])
        self.assertEqual(cur.tramos("2*3*4 no es cursiva"), [t("2*3*4 no es cursiva")])
        self.assertEqual(cur.texto_plano("*a* y $x^{2}$"), "a y x^2")
        # Listas y saltos de línea viajan tal cual en `texto`: la etiqueta los respeta.
        self.assertEqual(cur.tramos("- uno\n- **dos**"), [t("- uno\n- "), t("dos", negrita=True)])

    def test_agrupar_por_asignatura_y_catalogos(self):
        grupos = cur.agrupar_por_asignatura([
            {"clasificacion": {"asignatura": {"codigo": "math", "nombre": "Matemáticas"}}, "curso_ref": "a"},
            {"clasificacion": {"asignatura": {"codigo": "science", "nombre": "Ciencias naturales"}}, "curso_ref": "b"},
            {"clasificacion": {"asignatura": {"codigo": "math", "nombre": "Matemáticas"}}, "curso_ref": "c"},
        ])
        self.assertEqual([g["nombre"] for g in grupos], ["Ciencias naturales", "Matemáticas"])
        self.assertEqual(len(grupos[1]["cursos"]), 2)
        self.assertEqual(set(catalogos.TIPOS_OBJETO), {"lecture", "explanation", "simulation_lab", "activity", "exam"})
        self.assertEqual(set(catalogos.TIPOS_BLOQUE), {"heading", "text", "list", "formula", "image", "video", "audio", "pdf"})
        formula = cur._bloque({"type": "formula", "latex": "\\frac{1}{3} \\times 2", "display": True}, {}, lambda m, r: "")
        self.assertEqual((formula["componente"], formula["latex"], formula["texto"], formula["en_bloque"]), ("formula", "\\frac{1}{3} \\times 2", "1/3 × 2", True))
        self.assertEqual(len(catalogos.TIPOS_PREGUNTA), 6)

    def test_sin_claves_limpia_camel_y_espanol(self):
        sucio = {"options": [{"id": "a", "isCorrect": True, "feedback": "x"}], "answer": False, "clave_respuesta": "3",
                 "rubric": [], "ok": {"pairs": [], "texto": "se queda"}}
        self.assertEqual(cur.sin_claves(sucio), {"options": [{"id": "a"}], "ok": {"texto": "se queda"}})
        self.assertEqual(cur.contiene_clave(sucio), "isCorrect")

    def test_localizar_y_primer_objeto(self):
        vista = cur.normalizar(manifiesto(), rol="docente", fuente="ejemplo", url_medio=lambda m, r: f"/m/{m}/{r or ''}")
        hallado = cur.localizar(vista, objeto_ref="l1-lecture", unidad_ref="l1-lecture-s2")
        self.assertEqual(hallado["leccion"]["leccion_ref"], "l1-three-states")
        self.assertEqual(hallado["unidad"]["indice"], 2)
        pregunta = cur.localizar(vista, objeto_ref="l1-activity", unidad_ref="l1-act-q3")["unidad"]
        self.assertEqual(pregunta["componente"], "completar")
        self.assertEqual(cur.primer_objeto(vista, "l2-changes-of-state")["objeto"]["objeto_ref"], "l2-lecture")
        self.assertIsNone(cur.primer_objeto(vista, "l3-assessment"))   # el examen no es foco de aula
        with self.assertRaises(cur.ReferenciaNoEncontrada):
            cur.localizar(vista, objeto_ref="l1-lecture", unidad_ref="no-existe")


    def test_el_arbol_del_contrato_1_se_normaliza_con_la_misma_forma(self):
        """El normalizador sigue aceptando el árbol antiguo (`secciones/items`) por si una biblioteca lo publicara."""
        arbol = {"curso_ref": "co-secundaria-8-matematicas", "titulo": "Matemáticas · Grado 8", "version": "1", "asignatura": "Matemáticas",
                 "nivel": "secundaria", "grado": "8", "idioma": "es", "huella": "abc",
                 "secciones": [{"codigo": "s1", "titulo": "Funciones", "tipo": "tema", "orden": 1, "items": [
                     {"orden": 1, "tipo": "evaluacion", "elemento_ref": "ev-1", "titulo": "Evaluación"},
                     {"orden": 2, "tipo": "leccion", "elemento_ref": "lec-1", "titulo": "Función lineal"},
                     {"orden": 3, "tipo": "interactivo", "elemento_ref": "int-1", "titulo": "Explorador"},
                     {"orden": 4, "tipo": "video", "elemento_ref": "vid-1", "titulo": "Pendiente", "clave_respuesta": "x"}]}]}
        v = cur.normalizar(arbol, rol="estudiante", fuente="biblioteca", url_medio=lambda m, r: "")
        self.assertEqual((v["esquema"], v["clasificacion"]["asignatura"]["nombre"], len(v["lecciones"])), ("contrato-1", "Matemáticas", 1))
        tipos = {o["tipo_contrato1"]: o for o in v["lecciones"][0]["objetos"]}
        self.assertEqual((tipos["evaluacion"]["componente"], tipos["evaluacion"]["fuera_de_alcance"]), ("examen", True))
        self.assertEqual(tipos["leccion"]["detalle_url"], "/api/biblioteca/leccion/lec-1/")
        self.assertEqual(tipos["interactivo"]["url_lanzamiento"], "/api/biblioteca/medio/int-1/index.html")
        self.assertEqual(tipos["video"]["medio"]["url"], "/api/biblioteca/medio/vid-1/")
        self.assertIsNone(cur.contiene_clave(v))


class ConLaApiDeContenidoV2Tests(TestCase):
    """La misma vista de aula cuando el curso lo entrega AVACOM Biblioteca por la API de Contenido v2
    (host de pruebas con el manifiesto completo, que recorta, baraja y califica como la API real)."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp(prefix="avacom-aula-v2-")
        self.ruta_enlace = os.path.join(self.carpeta, "link.json")
        self.manifiesto = manifiesto()
        viejo = json.loads(json.dumps(self.manifiesto))
        viejo["version"], viejo["title"] = "0.9.0", "Estados de la materia (borrador)"
        self.host = HostContenidoV2Pruebas(
            self.ruta_enlace, {CURSO: self.manifiesto}, archivados={(CURSO, "0.9.0"): viejo},
            medios={"img-particles": ("image/png", PNG_1x1), "vid-changes": ("video/mp4", bytes(range(256)) * 400),
                    "vid-changes/@captions": ("text/vtt; charset=utf-8", b"WEBVTT\n\n1\n00:00:00.000 --> 00:00:30.000\nEl hielo es solido."),
                    "aud-summary/@transcript": ("text/plain; charset=utf-8", b"Los tres estados de la materia."),
                    "sim-heating-curve/index.html": ("text/html; charset=utf-8", b"<html><body>curva</body></html>")},
        ).iniciar()
        self._ajuste = override_settings(AVACOM_CONTENIDO_ENLACE_V2=self.ruta_enlace)
        self._ajuste.enable()
        self.api = APIClient()

    def tearDown(self):
        self._ajuste.disable()
        self.host.detener()

    def _evaluar(self, cuerpo: dict):
        return self.api.post(f"/api/aula/cursos/{CURSO}/evaluar/?fuente=biblioteca", cuerpo, format="json")

    # ------------------------------------------------------------------ el curso
    def test_el_curso_recortado_por_la_api_produce_la_misma_vista_que_el_ejemplo(self):
        biblioteca = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca&rol=docente").json()
        ejemplo = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=ejemplo&rol=docente").json()
        self.assertEqual(biblioteca["fuente"], "biblioteca")
        self.assertEqual((biblioteca["titulo"], biblioteca["version"]), (ejemplo["titulo"], "1.0.0"))
        # Con `mode=class` la API no entrega el examen (declara modes: [exam]); todo lo demás es idéntico.
        self.assertEqual(biblioteca["resumen"]["fuera_de_alcance"], [])
        self.assertEqual(biblioteca["resumen"]["objetos_por_tipo"], {k: v for k, v in ejemplo["resumen"]["objetos_por_tipo"].items() if k != "exam"})
        self.assertEqual((biblioteca["resumen"]["preguntas"], biblioteca["resumen"]["medios"]), (ejemplo["resumen"]["preguntas"], 8))
        self.assertEqual(len(biblioteca["lecciones"]), 3)
        self.assertEqual(biblioteca["lecciones"][0]["objetos"][0]["laminas"][1]["bloques"][0]["url"],
                         f"/api/aula/cursos/{CURSO}/medios/img-particles/?fuente=biblioteca")
        self.assertIsNone(cur.contiene_clave(biblioteca))
        # El aula pide el curso en modo clase y con el perfil del rol: teacher trae las notas del docente.
        self.assertEqual(self.host.peticiones[0], f"GET /v2/courses/{CURSO}")
        self.assertEqual(self.host.consultas[0], {"mode": "class", "profile": "teacher"})
        self.assertIn("notas_docente", biblioteca)
        estudiante = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").json()
        self.assertEqual(self.host.consultas[-1]["profile"], "student")
        self.assertNotIn("notas_docente", json.dumps(estudiante))

    def test_las_opciones_llegan_barajadas_y_se_identifican_por_id_no_por_posicion(self):
        v = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").json()
        mc = v["lecciones"][0]["objetos"][3]["preguntas"][0]
        self.assertEqual([o["opcion_ref"] for o in mc["opciones"]], ["b", "c", "a"])     # el host rota una posición
        ejemplo = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=ejemplo").json()["lecciones"][0]["objetos"][3]["preguntas"][0]
        self.assertEqual({o["opcion_ref"] for o in mc["opciones"]}, {o["opcion_ref"] for o in ejemplo["opciones"]})

    def test_la_lista_baja_cada_curso_completo_y_lo_agrupa_por_asignatura(self):
        datos = self.api.get("/api/aula/cursos/?fuente=biblioteca").json()
        self.assertEqual([a["nombre"] for a in datos["asignaturas"]], ["Ciencias naturales"])
        ficha = datos["asignaturas"][0]["cursos"][0]
        self.assertEqual((ficha["curso_ref"], ficha["version"], ficha["lecciones"]), (CURSO, "1.0.0", 3))
        self.assertEqual(self.host.peticiones, ["GET /v2/courses", f"GET /v2/courses/{CURSO}"])

    def test_el_curso_se_arma_con_el_esquema_y_cada_leccion_completa(self):
        v = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").json()
        # Esquema + las dos lecciones con objetos en modo clase; la de evaluación queda vacía y no se pide.
        self.assertEqual(self.host.peticiones, [f"GET /v2/courses/{CURSO}", f"GET /v2/courses/{CURSO}/lessons/l1-three-states",
                                                f"GET /v2/courses/{CURSO}/lessons/l2-changes-of-state"])
        self.assertEqual([len(l["objetos"]) for l in v["lecciones"]], [4, 3, 0])
        self.assertEqual(v["lecciones"][0]["objetos"][0]["total_unidades"], 3)          # láminas reales, no el resumen
        # Los medios del esquema no traen rutas, sólo si hay subtítulos o transcripción: las URL salen igual.
        video = v["lecciones"][0]["objetos"][0]["laminas"][2]["bloques"][0]
        self.assertTrue(video["subtitulos_url"].endswith("/medios/vid-changes/subtitulos?fuente=biblioteca"))
        # `semilla` viaja como `seed` para que toda la clase vea las opciones en el mismo orden.
        con_semilla = self.api.get(f"/api/aula/cursos/{CURSO}/objetos/l1-activity/?fuente=biblioteca&semilla=aula-1").json()
        self.assertEqual(self.host.consultas[-1].get("seed"), "aula-1")
        otra_vez = self.api.get(f"/api/aula/cursos/{CURSO}/objetos/l1-activity/?fuente=biblioteca&semilla=aula-1").json()
        self.assertEqual([o["opcion_ref"] for o in con_semilla["objeto"]["preguntas"][0]["opciones"]],
                         [o["opcion_ref"] for o in otra_vez["objeto"]["preguntas"][0]["opciones"]])

    def test_la_api_solo_sirve_la_version_instalada(self):
        # La API no entrega el esquema de una versión archivada: `version` sólo se admite en evaluate y grading-guide.
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca&version=0.9.0")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["codigo_biblioteca"]), (404, "curso_no_encontrado", "version_not_available"))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca&version=1.0.0")
        self.assertEqual((r.status_code, r.json()["version"]), (200, "1.0.0"))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca&version=3.0.0")
        self.assertEqual(r.status_code, 404)
        # Sin `version` la clase en vivo ve la versión instalada.
        self.assertEqual(self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").json()["version"], "1.0.0")

    def test_un_401_reintenta_una_sola_vez_tras_releer_link_json(self):
        self.host.rechazar_proximas = 1
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.host.peticiones.count(f"GET /v2/courses/{CURSO}"), 2)
        self.host.rechazar_proximas = 2
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["codigo_biblioteca"]), (502, "fuente_error", "unauthorized"))
        # La biblioteca se reinició con otro token: como link.json se relee en cada petición, la siguiente llamada entra.
        self.host.rotar_token()
        self.assertEqual(self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").status_code, 200)

    def test_los_codigos_de_error_del_contrato_se_traducen(self):
        r = self.api.get("/api/aula/cursos/otro-curso/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "curso_no_encontrado"))
        self.host.desactivados.add(CURSO)
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "desactivado_por_politica"))
        self.assertEqual(self.api.get("/api/aula/cursos/?fuente=biblioteca").json()["cursos"], [])   # lo desactivado no se muestra
        self.host.desactivados.clear()
        self.host.reconstruyendo = True
        r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["disponible"], r.json()["codigo_biblioteca"]), (503, False, "index_rebuilding"))
        self.assertIn("unos segundos", r.json()["sugerencia"])
        self.host.reconstruyendo = False

    def test_el_estado_de_la_fuente_trae_los_cursos_instalados_y_la_huella(self):
        r = self.api.get("/api/aula/fuente/?fuente=biblioteca").json()
        self.assertEqual((r["fuente"], r["disponible"], r["puerto"]), ("biblioteca", True, self.host.puerto))
        self.assertEqual(r["cursos_instalados"], [{"curso_ref": CURSO, "version": "1.0.0", "titulo": "Estados de la materia y sus cambios"}])
        self.assertTrue(r["huella"].startswith("v2-"))

    def test_los_medios_pasan_a_traves_de_la_api(self):
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/img-particles/?fuente=biblioteca")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        self.assertEqual(b"".join(r.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")
        # Una sesión de medios de un minuto sólo para ese medio, y los bytes del servidor de medios (sin token).
        self.assertEqual(self.host.peticiones[-2:][0], "POST /v2/media-sessions")
        self.assertEqual(self.host.cuerpos[-1], {"courseId": CURSO, "mediaIds": ["img-particles"], "ttlSec": 60})
        self.assertTrue(self.host.peticiones[-1].startswith("MEDIA GET /s/") and self.host.peticiones[-1].endswith("/img-particles"))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/vid-changes/?fuente=biblioteca", HTTP_RANGE="bytes=0-9")
        self.assertEqual((r.status_code, r["Content-Range"]), (206, "bytes 0-9/102400"))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/vid-changes/subtitulos?fuente=biblioteca")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/vtt"))
        self.assertTrue(self.host.peticiones[-1].endswith("/vid-changes/@captions"))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/aud-summary/transcripcion?fuente=biblioteca")
        self.assertEqual((r.status_code, b"".join(r.streaming_content)), (200, b"Los tres estados de la materia."))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/img-particles/subtitulos?fuente=biblioteca")
        self.assertEqual(r.status_code, 404)        # una imagen no tiene subtítulos
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/sim-heating-curve/index.html?fuente=biblioteca")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.host.peticiones[-1].endswith("/sim-heating-curve/index.html"))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/medios/no-existe/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "referencia_no_encontrada"))

    # ------------------------------------------------------------------ evaluar
    def test_evaluar_opcion_multiple_por_id_y_siempre_con_version(self):
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["a"]}})
        self.assertEqual(r.status_code, 200)
        v = r.json()
        self.assertEqual((v["curso_ref"], v["version"], v["objeto_ref"], v["pregunta_ref"]), (CURSO, "1.0.0", "l1-activity", "l1-act-q1"))
        self.assertEqual((v["puntaje"], v["puntaje_maximo"], v["correcta"], v["requiere_correccion_manual"], v["pendiente"]), (1.0, 1.0, True, False, False))
        self.assertEqual(v["retroalimentacion"], ["Correcto: el aire es una mezcla de gases."])
        self.assertEqual(self.host.cuerpos[-1], {"courseId": CURSO, "version": "1.0.0", "objectId": "l1-activity", "questionId": "l1-act-q1",
                                                 "response": {"selectedOptionIds": ["a"]}})
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["b"]}})
        v = r.json()
        self.assertEqual((v["puntaje"], v["correcta"]), (0.0, False))
        self.assertIn("La leche toma la forma del vaso: es un líquido.", v["retroalimentacion"])
        for prohibida in ("isCorrect", "answer", "feedback"):
            self.assertNotIn(f'"{prohibida}"', r.content.decode("utf-8"))

    def test_evaluar_los_demas_tipos_y_el_credito_parcial_decimal(self):
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q2", "respuesta": {"value": False}})
        self.assertEqual((r.json()["puntaje"], r.json()["correcta"]), (1.0, True))
        # fill_blanks con crédito parcial: 1 de 2 huecos → 1.0 de 2 y `correcta` FALSA (validate_course: correct = ratio == 1.0).
        # La retroalimentación general va primero y después la del valor equivocado.
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q3", "respuesta": {"blanks": {"b1": "propio", "b2": "masa"}}})
        self.assertEqual((r.json()["puntaje"], r.json()["puntaje_maximo"], r.json()["correcta"], r.json()["pendiente"]), (1.0, 2.0, False, False))
        self.assertEqual(r.json()["retroalimentacion"], ["Piensa en el agua pasando de un vaso a una botella.", "La masa no cambia al cambiar de recipiente."])
        # matching parcial: 2 de 3 parejas → 2.0 de 3 (decimal, no entero); la pareja gas→none es un `wrongPair` con su propia retroalimentación
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q4",
                           "respuesta": {"pairs": [{"leftId": "solid", "rightId": "fixed"}, {"leftId": "liquid", "rightId": "slide"},
                                                   {"leftId": "gas", "rightId": "none"}]}})
        self.assertEqual((r.json()["puntaje"], r.json()["puntaje_maximo"], r.json()["correcta"]), (2.0, 3.0, False))
        self.assertEqual(r.json()["retroalimentacion"], ["Recuerda los tres recipientes de la cátedra.", "Los gases sí tienen partículas, solo que muy separadas."])
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q5", "respuesta": {"order": ["o-solid", "o-liquid", "o-gas"]}})
        self.assertEqual((r.json()["puntaje"], r.json()["correcta"]), (2.0, True))
        # numérico: coma decimal admitida y `numericTolerance` (0 en el ejemplo); el valor equivocado listado trae su retroalimentación
        r = self._evaluar({"objeto_ref": "l2-activity", "pregunta_ref": "l2-act-q3", "respuesta": {"blanks": {"b1": "0,0"}}})
        self.assertEqual((r.json()["puntaje"], r.json()["correcta"]), (1.0, True))
        r = self._evaluar({"objeto_ref": "l2-activity", "pregunta_ref": "l2-act-q3", "respuesta": {"blanks": {"b1": "100"}}})
        self.assertEqual((r.json()["puntaje"], r.json()["correcta"], r.json()["retroalimentacion"]),
                         (0.0, False, ["Piensa en el hielo, no en el agua hirviendo.", "100 °C es la ebullición a nivel del mar."]))
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q5", "respuesta": {"order": ["o-solid", "o-gas"]}})
        self.assertEqual(r.status_code, 400)      # el orden debe contener todos los elementos, una vez cada uno

    def test_una_pregunta_abierta_queda_pendiente_sin_inventar_nota(self):
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q6", "respuesta": {"text": "El perfume se evapora."}})
        v = r.json()
        self.assertEqual((v["puntaje"], v["correcta"], v["requiere_correccion_manual"], v["pendiente"]), (None, None, True, True))
        self.assertEqual(v["puntaje_maximo"], 4.0)
        r = self._evaluar({"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q6", "respuesta": {"text": "a", "audioRef": "b"}})
        self.assertEqual(r.status_code, 400)

    def test_evaluar_en_lote_con_la_version_indicada(self):
        r = self._evaluar({"version": "0.9.0", "items": [
            {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["a"]}},
            {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q6", "respuesta": {"text": "…"}},
        ]})
        self.assertEqual(r.status_code, 200)
        v = r.json()
        self.assertEqual((v["version"], v["pendientes"], len(v["veredictos"])), ("0.9.0", 1, 2))
        self.assertEqual([x["pregunta_ref"] for x in v["veredictos"]], ["l1-act-q1", "l1-act-q6"])
        self.assertEqual(self.host.peticiones[-1], "POST /v2/evaluate/batch")
        self.assertTrue(all(i["version"] == "0.9.0" for i in self.host.cuerpos[-1]["items"]))
        # Con una versión archivada el aula no conoce la estructura: la forma la valida la biblioteca (422 → 400).
        r = self._evaluar({"version": "0.9.0", "objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedIndex": 1}})
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["codigo_biblioteca"]), (400, "datos_invalidos", "invalid_response"))
        r = self._evaluar({"items": [{"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["a"]}}] * 201})
        self.assertEqual(r.status_code, 400)
