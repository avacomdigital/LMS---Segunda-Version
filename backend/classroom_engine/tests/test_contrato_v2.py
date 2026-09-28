"""
El contrato v2 de contenido tal como lo publica AVACOM Biblioteca junto a `openapi.v2.json`:
`course.schema.json` (estructura del curso 1.0) y `validate_course.py` (reglas semánticas, lo
que un alumno puede recibir y la corrección de referencia). Copias en spec-driven/02-classroom-engine/.

Tres cosas se comprueban aquí:
  1. El manifiesto de ejemplo (`example.json`) cumple el esquema y las reglas del validador.
  2. Las claves de corrección que el aula nunca reenvía cubren las que el validador declara.
  3. El host de pruebas recorta y califica EXACTAMENTE como la referencia (paridad función a función).

El validador necesita `jsonschema>=4.18` (no es dependencia del LMS): sin él, las pruebas que lo
importan se omiten y las demás siguen valiendo.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from tools.host_contenido_v2_pruebas import HostContenidoV2Pruebas, calificar, objeto_visible

from ..dominio import catalogos, curso as cur

CARPETA_CONTRATO = Path(settings.AVACOM_AULA_CURSO_EJEMPLO).parent
RUTA_VALIDADOR = CARPETA_CONTRATO / "validate_course.py"
RUTA_ESQUEMA = CARPETA_CONTRATO / "course.schema.json"
CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"


def manifiesto() -> dict:
    with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
        return json.load(f)


def cargar_validador():
    """Ejecuta validate_course.py desde spec-driven como módulo, sin escribir `__pycache__` en la
    carpeta de la especificación; None si falta jsonschema (el módulo hace sys.exit al importarlo)."""
    if importlib.util.find_spec("jsonschema") is None:
        return None
    modulo = types.ModuleType("validate_course")
    modulo.__file__ = str(RUTA_VALIDADOR)          # SCHEMA_PATH se resuelve junto al archivo
    try:
        exec(compile(RUTA_VALIDADOR.read_text(encoding="utf-8"), str(RUTA_VALIDADOR), "exec"), modulo.__dict__)
    except SystemExit:
        return None
    return modulo


def constantes_del_validador() -> dict:
    """ANSWER_KEY_* de validate_course.py leídas del código fuente, sin importar el módulo."""
    arbol = ast.parse(RUTA_VALIDADOR.read_text(encoding="utf-8"))
    salida = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            nombre = nodo.targets[0].id
            if nombre.startswith("ANSWER_KEY"):
                salida[nombre] = ast.literal_eval(nodo.value)
    return salida


class EsquemaYValidadorTests(SimpleTestCase):
    def test_los_archivos_del_contrato_estan_junto_al_openapi(self):
        for nombre in ("openapi.v2.json", "course.schema.json", "validate_course.py", "example.json"):
            self.assertTrue((CARPETA_CONTRATO / nombre).exists(), nombre)
        esquema = json.loads(RUTA_ESQUEMA.read_text(encoding="utf-8"))
        self.assertEqual(esquema["$id"], "urn:avacom:content:course:1.0")
        self.assertEqual(esquema["properties"]["schemaVersion"], {"const": "1.0"})
        # Los conjuntos cerrados del esquema son los catálogos del aula (lo que llegue de más se muestra, no se descarta).
        defs = esquema["$defs"]
        self.assertEqual(set(defs["LessonObject"]["properties"]["type"]["enum"]), set(catalogos.TIPOS_OBJETO))
        self.assertEqual(set(defs["Question"]["properties"]["type"]["enum"]), set(catalogos.TIPOS_PREGUNTA))
        self.assertEqual(set(defs["Block"]["properties"]["type"]["enum"]), set(catalogos.TIPOS_BLOQUE))
        self.assertEqual(set(defs["Media"]["properties"]["kind"]["enum"]), set(catalogos.CLASES_MEDIO))
        self.assertEqual(tuple(defs["Mode"]["enum"]), catalogos.MODOS)

    def test_las_claves_de_correccion_del_aula_cubren_las_del_validador(self):
        constantes = constantes_del_validador()
        declaradas = set(constantes["ANSWER_KEY_OPTION_FIELDS"]) | set(constantes["ANSWER_KEY_BLANK_FIELDS"])
        for campos in constantes["ANSWER_KEY_FIELDS"].values():
            declaradas |= set(campos)
        self.assertEqual(set(constantes["ANSWER_KEY_FIELDS"]), set(catalogos.TIPOS_PREGUNTA))
        self.assertTrue(declaradas <= catalogos.CLAVES_DE_CORRECCION, declaradas - catalogos.CLAVES_DE_CORRECCION)

    def test_el_ejemplo_cumple_el_esquema_y_las_reglas_del_validador(self):
        validador = cargar_validador()
        if validador is None:
            self.skipTest("validate_course.py necesita jsonschema>=4.18 (pip install jsonschema)")
        informe = validador.Report()
        curso = manifiesto()
        validador.validate_structure(curso, informe)
        self.assertEqual(informe.errors, [])
        validador.validate_semantics(curso, informe)
        self.assertEqual([i for i in informe.items if i["severity"] == "error"], [])
        self.assertEqual([i for i in informe.items if i["severity"] == "warning"], [])

    def test_el_host_recorta_como_visible_object(self):
        validador = cargar_validador()
        if validador is None:
            self.skipTest("validate_course.py necesita jsonschema>=4.18 (pip install jsonschema)")
        for leccion in manifiesto()["lessons"]:
            for objeto in leccion["objects"]:
                for perfil in ("student", "teacher"):
                    for claves in (False, True):
                        with self.subTest(objeto=objeto["id"], perfil=perfil, claves=claves):
                            self.assertEqual(objeto_visible(objeto, perfil=perfil, claves_actividad=claves),
                                             validador.visible_object(objeto, perfil, claves))

    def test_el_host_califica_como_evaluate_response(self):
        validador = cargar_validador()
        if validador is None:
            self.skipTest("validate_course.py necesita jsonschema>=4.18 (pip install jsonschema)")
        preguntas = {q["id"]: q for l in manifiesto()["lessons"] for o in l["objects"] for q in o.get("questions", [])}
        casos = [
            ("l1-act-q1", {"selectedOptionIds": ["a"]}), ("l1-act-q1", {"selectedOptionIds": ["b"]}), ("l1-act-q1", {"selectedOptionIds": ["a", "c"]}),
            ("l1-act-q2", {"value": False}), ("l1-act-q2", {"value": True}),
            ("l1-act-q3", {"blanks": {"b1": "propio", "b2": "masa"}}), ("l1-act-q3", {"blanks": {"b1": "PROPIO ", "b2": "forma"}}), ("l1-act-q3", {"blanks": {}}),
            ("l1-act-q4", {"pairs": [{"leftId": "solid", "rightId": "fixed"}, {"leftId": "gas", "rightId": "none"}]}),
            ("l1-act-q4", {"pairs": [{"leftId": "solid", "rightId": "fixed"}, {"leftId": "liquid", "rightId": "slide"}, {"leftId": "gas", "rightId": "spread"}]}),
            ("l1-act-q5", {"order": ["o-solid", "o-liquid", "o-gas"]}), ("l1-act-q5", {"order": ["o-liquid", "o-solid", "o-gas"]}), ("l1-act-q5", {"order": ["o-gas", "o-liquid", "o-solid"]}),
            ("l1-act-q6", {"text": "El perfume se evapora."}),
            ("l2-act-q3", {"blanks": {"b1": "0,0"}}), ("l2-act-q3", {"blanks": {"b1": "100"}}), ("l2-act-q3", {"blanks": {"b1": "cero"}}),
            ("l3-q6", {"selectedOptionIds": ["a"]}), ("l3-q6", {"selectedOptionIds": ["a", "b", "c"]}),   # opción múltiple con crédito parcial
            ("l3-q9", {"pairs": [{"leftId": "melting", "rightId": "s-l"}]}),
            ("l3-q11", {"order": ["o-ice", "o-water", "o-steam"]}),
        ]
        for pregunta_ref, respuesta in casos:
            pregunta = preguntas[pregunta_ref]
            with self.subTest(pregunta=pregunta_ref, respuesta=respuesta):
                self.assertEqual(calificar(pregunta, respuesta), validador.evaluate_response(pregunta, respuesta))


class RecorteYCorreccionDelHostTests(SimpleTestCase):
    """Lo que la referencia fija y el aula asume, sin depender de jsonschema."""

    def setUp(self):
        self.preguntas = {q["id"]: q for l in manifiesto()["lessons"] for o in l["objects"] for q in o.get("questions", [])}
        self.objetos = {o["id"]: o for l in manifiesto()["lessons"] for o in l["objects"]}

    def test_correct_es_booleano_y_la_retroalimentacion_general_va_primero(self):
        v = calificar(self.preguntas["l1-act-q3"], {"blanks": {"b1": "propio", "b2": "masa"}})
        self.assertEqual((v["score"], v["maxScore"], v["correct"], v["requiresManualGrading"]), (1.0, 2.0, False, False))
        self.assertEqual(v["feedback"], ["Piensa en el agua pasando de un vaso a una botella.", "La masa no cambia al cambiar de recipiente."])
        v = calificar(self.preguntas["l1-act-q1"], {"selectedOptionIds": ["a"]})
        self.assertEqual((v["score"], v["correct"], v["feedback"]), (1.0, True, ["Correcto: el aire es una mezcla de gases."]))

    def test_opcion_multiple_solo_da_credito_parcial_con_allow_multiple(self):
        q = self.preguntas["l3-q6"]
        self.assertTrue(q["allowMultiple"] and q["partialCredit"])
        correctas = [o["id"] for o in q["options"] if o["isCorrect"]]
        incorrecta = next(o["id"] for o in q["options"] if not o["isCorrect"])
        parcial = calificar(q, {"selectedOptionIds": correctas[:1]})
        self.assertEqual((parcial["score"], parcial["correct"]), (round(q["points"] / len(correctas), 4), False))
        castigo = calificar(q, {"selectedOptionIds": correctas + [incorrecta]})
        self.assertEqual(castigo["score"], round(q["points"] * (len(correctas) - 1) / len(correctas), 4))
        sin_parcial = calificar({**q, "partialCredit": False}, {"selectedOptionIds": correctas[:1]})
        self.assertEqual((sin_parcial["score"], sin_parcial["correct"]), (0.0, False))

    def test_completar_normaliza_mayusculas_acentos_y_coma_decimal(self):
        q = self.preguntas["l1-act-q3"]
        self.assertTrue(calificar(q, {"blanks": {"b1": " PROPIO ", "b2": "Fórma"}})["correct"])
        self.assertFalse(calificar({**q, "blanks": [{**q["blanks"][0], "caseSensitive": True}, q["blanks"][1]]},
                                   {"blanks": {"b1": "PROPIO", "b2": "forma"}})["correct"])
        numerica = self.preguntas["l2-act-q3"]
        self.assertTrue(calificar(numerica, {"blanks": {"b1": "0,0"}})["correct"])
        self.assertFalse(calificar(numerica, {"blanks": {"b1": "cero"}})["correct"])
        con_tolerancia = {**numerica, "blanks": [{**numerica["blanks"][0], "numericTolerance": 0.5}]}
        self.assertTrue(calificar(con_tolerancia, {"blanks": {"b1": "0.4"}})["correct"])

    def test_ordenar_con_credito_parcial_cuenta_posiciones(self):
        q = {**self.preguntas["l1-act-q5"], "partialCredit": True}
        v = calificar(q, {"order": ["o-solid", "o-gas", "o-liquid"]})   # sólo la primera posición acierta
        self.assertEqual((v["score"], v["correct"]), (round(2 / 3, 4), False))

    def test_una_abierta_no_lleva_nota_ni_retroalimentacion(self):
        v = calificar(self.preguntas["l1-act-q6"], {"text": "…"})
        self.assertEqual(v, {"questionId": "l1-act-q6", "maxScore": 4.0, "requiresManualGrading": True, "feedback": [], "score": None, "correct": None})

    def test_el_recorte_quita_las_claves_por_tipo_y_las_notas_por_perfil(self):
        # Se miran las preguntas: `settings.feedback` («immediate») de la actividad no es una clave.
        actividad = objeto_visible(self.objetos["l1-activity"], perfil="student")
        self.assertNotIn("teacherNotes", actividad)
        self.assertIsNone(cur.contiene_clave(actividad["questions"]))
        docente = objeto_visible(self.objetos["l1-activity"], perfil="teacher")
        self.assertIn("teacherNotes", docente)
        self.assertIsNone(cur.contiene_clave(docente["questions"]))
        # includeActivityKeys: sólo actividades con feedback immediate conservan sus claves…
        con_claves = objeto_visible(self.objetos["l1-activity"], perfil="student", claves_actividad=True)
        self.assertEqual(cur.contiene_clave(con_claves["questions"]), "isCorrect")
        # …y un examen NUNCA las conserva, se pida lo que se pida.
        examen = objeto_visible(self.objetos["l3-exam"], perfil="teacher", claves_actividad=True)
        self.assertIsNone(cur.contiene_clave(examen["questions"]))


class NormalizadorSegunElEsquemaTests(SimpleTestCase):
    """Lo que el esquema 1.0 permite y el manifiesto de ejemplo no ejercita."""

    def setUp(self):
        self.medios = {
            "img-a": {"media_ref": "img-a", "clase": "image", "componente": "imagen", "url": "/m/img-a/", "texto_alternativo": "Un vaso"},
            "vid-b": {"media_ref": "vid-b", "clase": "video", "componente": "video", "url": "/m/vid-b/"},
        }
        self.url = lambda m, r: f"/m/{m}/{r or ''}"

    def test_la_pregunta_trae_sus_medios_y_las_opciones_e_items_con_imagen(self):
        p = cur._pregunta({
            "id": "q", "type": "multiple_choice", "prompt": "¿Cuál *pesa* más? $2 \\times 3$", "mediaIds": ["img-a", "vid-b", "no-esta"],
            "points": 1.5, "allowMultiple": False, "curriculumRefs": [{"framework": "DBA", "code": "CN.6.1"}],
            "options": [{"id": "a", "mediaId": "img-a", "isCorrect": True}, {"id": "b", "text": "Texto", "isCorrect": False}],
        }, self.medios, self.url)
        self.assertEqual([m["media_ref"] for m in p["medios"]], ["img-a", "vid-b", "no-esta"])
        self.assertTrue(p["medios"][2]["ausente"])
        self.assertEqual((p["opciones"][0]["media_ref"], p["opciones"][0]["url"], p["opciones"][0]["texto_alternativo"]), ("img-a", "/m/img-a/", "Un vaso"))
        self.assertEqual((p["opciones"][1]["media_ref"], p["opciones"][1]["texto"]), (None, "Texto"))
        self.assertEqual(p["enunciado_tramos"][1], {"texto": "pesa", "negrita": False, "cursiva": True, "matematica": False})
        self.assertEqual(p["enunciado_tramos"][3], {"texto": "2 × 3", "negrita": False, "cursiva": False, "matematica": True})
        self.assertEqual((p["puntos"], p["referencias_curriculares"]), (1.5, [{"marco": "DBA", "codigo": "CN.6.1", "descripcion": None, "relacion": None}]))
        self.assertIsNone(cur.contiene_clave(p))
        relacionar = cur._pregunta({"id": "r", "type": "matching", "prompt": "Une", "left": [{"id": "l1", "mediaId": "img-a"}], "right": [{"id": "r1", "text": "**Agua**"}],
                                    "pairs": [], "wrongPairs": []}, self.medios, self.url)
        self.assertEqual(relacionar["izquierda"][0]["url"], "/m/img-a/")
        self.assertEqual(relacionar["derecha"][0]["tramos"][0]["negrita"], True)
        self.assertIsNone(cur.contiene_clave(relacionar))

    def test_los_puntos_son_decimales_y_los_ajustes_traen_los_tiempos(self):
        actividad = cur._objeto({
            "id": "act", "type": "activity", "title": "A", "modes": ["class"], "instructions": "Haz",
            "settings": {"feedback": "on_submit", "timeLimitSec": 300},
            "questions": [{"id": "q1", "type": "true_false", "prompt": "¿?", "points": 1.5, "answer": True},
                          {"id": "q2", "type": "true_false", "prompt": "¿?", "points": 2, "answer": False}],
        }, "estudiante", {}, self.url)
        self.assertEqual((actividad["puntos_totales"], actividad["ajustes"]["tiempo_limite_seg"]), (3.5, 300))
        self.assertIsNone(cur.contiene_clave(actividad))
        examen = cur._objeto({
            "id": "ex", "type": "exam", "title": "E", "modes": ["exam"], "instructions": "…",
            "settings": {"selection": {"strategy": "fixed"}, "timeLimit": {"policy": "fixed", "fixedSec": 1800}, "passingScorePct": 60, "showResults": "never"},
            "questions": [],
        }, "estudiante", {}, self.url)
        self.assertEqual(examen["ajustes"]["tiempo"], {"politica": "fixed", "fijo_seg": 1800, "extra_pct": None})
        pagina = cur._objeto({"id": "ex", "type": "explanation", "title": "L", "modes": ["class"],
                              "pages": [{"id": "p1", "estimatedSec": 90, "blocks": [{"type": "text", "text": "hola"}]}]}, "estudiante", {}, self.url)
        self.assertEqual(pagina["paginas"][0]["duracion_seg"], 90)

    def test_el_esquema_que_trae_contenido_2_1_7_tambien_se_entiende(self):
        """Visto en vivo el 2026-09-28: la app instalada valida con un esquema más nuevo que el entregado
        (mismo $id 1.0): `…Percent` en vez de `…Pct`, `timeLimit` sin `policy`, `track`, `relation`,
        `hasSpeech` y un séptimo tipo `drag_drop`. Nada de eso rompe la vista: se acepta o se muestra."""
        examen = cur._objeto({
            "id": "ex", "type": "exam", "title": "E", "modes": ["exam"], "instructions": "…",
            "settings": {"selection": {"strategy": "random_balanced", "questionCount": 4, "difficultyTolerancePercent": 20,
                                       "timeTolerancePercent": 25, "coverAllTopics": True},
                         "timeLimit": {"extraPercent": 25}, "showResults": "after_submit"},
            "questions": [{"id": "q1", "type": "drag_drop", "prompt": "Arrastra", "difficulty": 1, "estimatedSec": 30, "topicRef": "t",
                           "feedback": {"correct": "Bien", "incorrect": "Mal"}, "items": [{"id": "i1", "text": "a"}, {"id": "i2", "text": "b"}],
                           "targets": [{"id": "t1", "label": "Uno"}, {"id": "t2", "label": "Dos"}],
                           "placements": [{"itemId": "i1", "targetId": "t1"}], "wrongPlacements": [{"itemId": "i2", "targetId": "t1", "feedback": "No"}]}],
        }, "estudiante", {}, self.url)
        self.assertEqual(examen["ajustes"]["seleccion"]["tolerancia_dificultad_pct"], 20)
        self.assertEqual(examen["ajustes"]["tiempo"], {"politica": "sum_of_estimates", "fijo_seg": None, "extra_pct": 25})
        self.assertEqual((examen["ajustes"]["aprobacion_pct"], examen["total_preguntas_banco"]), (None, 1))
        fijo = cur._objeto({"id": "ex", "type": "exam", "title": "E", "modes": ["exam"], "instructions": "…",
                            "settings": {"selection": {"strategy": "fixed"}, "timeLimit": {"fixedSec": 600}, "showResults": "never"}, "questions": []},
                           "estudiante", {}, self.url)
        self.assertEqual(fijo["ajustes"]["tiempo"]["politica"], "fixed")
        actividad = cur._objeto({
            "id": "act", "type": "activity", "title": "A", "modes": ["class"], "instructions": "Haz", "settings": {"feedback": "immediate"},
            "curriculumRefs": [{"framework": "avacom-node", "code": "vocales.a", "relation": "teaches"}],
            "questions": [{"id": "q1", "type": "drag_drop", "prompt": "Arrastra", "difficulty": 1, "estimatedSec": 30, "points": 2,
                           "feedback": {"correct": "Bien", "incorrect": "Mal"}, "items": [{"id": "i1", "text": "a"}], "targets": [{"id": "t1", "label": "Uno"}],
                           "placements": [{"itemId": "i1", "targetId": "t1"}], "wrongPlacements": []}],
        }, "estudiante", {}, self.url)
        arrastrar = actividad["preguntas"][0]
        self.assertEqual((arrastrar["tipo"], arrastrar["componente"], arrastrar["puntos"]), ("drag_drop", "no_soportado", 2))
        self.assertIsNone(cur.contiene_clave(actividad))        # placements y wrongPlacements no se copian: la vista es por campos
        self.assertEqual(actividad["referencias_curriculares"][0]["relacion"], "teaches")
        vista = cur.normalizar({"schemaVersion": "1.0", "id": "c", "version": "1.0.0", "title": "T", "language": "es-CO",
                                "classification": {"country": "CO", "track": "complementary", "level": {"code": "idiomas", "name": "Idiomas", "order": 0},
                                                   "grade": {"code": "ingles", "name": "Inglés", "order": 0}, "subject": {"code": "a1", "name": "A1"},
                                                   "topic": {"code": "saludos", "name": "Saludos"}},
                                "modes": ["class"], "teacherNotes": {"summary": "s"},
                                "media": [{"id": "aud", "kind": "audio", "path": "a.mp3", "mimeType": "audio/mpeg", "hasSpeech": True, "license": {"type": "avacom"}}],
                                "lessons": [{"id": "l1", "title": "L", "modes": ["class"], "teacherNotes": {"summary": "s"},
                                             "objects": [{"id": "o1", "type": "explanation", "title": "E", "modes": ["class"], "teacherNotes": {"summary": "s"},
                                                          "pages": [{"id": "p1", "blocks": [{"type": "audio", "mediaId": "aud"}]}]}]}]},
                               rol="estudiante", fuente="ejemplo", url_medio=self.url)
        self.assertEqual((vista["clasificacion"]["pista"], vista["medios"][0]["tiene_voz"]), ("complementary", True))
        self.assertEqual(cur.clasificacion_de({"classification": {"country": "co"}})["pista"], "school")

    def test_sin_claves_tambien_quita_keywords_y_numeric_tolerance(self):
        sucio = {"blanks": [{"id": "b", "numericTolerance": 0.5, "inputMode": "numeric"}], "keywords": ["evapora"], "texto": "queda"}
        self.assertEqual(cur.sin_claves(sucio), {"blanks": [{"id": "b", "inputMode": "numeric"}], "texto": "queda"})


class ElAulaNuncaPideLasClavesTests(TestCase):
    """`includeActivityKeys` existe en el contrato; el aula no lo usa (artículo 14: la clave se compara donde vive)."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp(prefix="avacom-aula-v2-claves-")
        self.ruta_enlace = os.path.join(self.carpeta, "link.json")
        self.host = HostContenidoV2Pruebas(self.ruta_enlace, {CURSO: manifiesto()}).iniciar()
        self._ajuste = override_settings(AVACOM_CONTENIDO_ENLACE_V2=self.ruta_enlace)
        self._ajuste.enable()
        self.api = APIClient()

    def tearDown(self):
        self._ajuste.disable()
        self.host.detener()

    def _directo(self, camino: str):
        peticion = urllib.request.Request(f"http://127.0.0.1:{self.host.puerto}{camino}", headers={"X-Avacom-Token": self.host.token})
        try:
            with urllib.request.urlopen(peticion, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_el_aula_no_manda_include_activity_keys_y_la_vista_no_trae_claves(self):
        for rol in ("docente", "estudiante"):
            r = self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca&rol={rol}")
            self.assertEqual(r.status_code, 200)
            self.assertIsNone(cur.contiene_clave(r.json()))
        self.assertTrue(all("includeActivityKeys" not in c for c in self.host.consultas))
        r = self.api.get(f"/api/aula/cursos/{CURSO}/objetos/l1-activity/?fuente=biblioteca&rol=docente")
        self.assertIsNone(cur.contiene_clave(r.json()))
        self.assertTrue(all("includeActivityKeys" not in c for c in self.host.consultas))

    def test_el_host_si_entiende_include_activity_keys_como_el_contrato(self):
        estado, cuerpo = self._directo(f"/v2/courses/{CURSO}/objects/l1-activity?includeActivityKeys=true")
        self.assertEqual((estado, cur.contiene_clave(cuerpo["questions"])), (200, "isCorrect"))
        estado, cuerpo = self._directo(f"/v2/courses/{CURSO}/objects/l3-exam?includeActivityKeys=true")
        self.assertEqual((estado, cuerpo["error"]["code"]), (403, "answer_keys_forbidden"))
        estado, cuerpo = self._directo(f"/v2/courses/{CURSO}/lessons/l3-assessment?mode=exam&includeActivityKeys=true")
        self.assertEqual((estado, cuerpo["error"]["code"]), (403, "answer_keys_forbidden"))
        estado, cuerpo = self._directo(f"/v2/courses/{CURSO}/objects/l3-exam?profile=teacher")
        self.assertEqual((estado, cur.contiene_clave(cuerpo["questions"])), (200, None))

    def test_el_estado_de_la_fuente_informa_la_version_del_esquema_y_de_la_app(self):
        r = self.api.get("/api/aula/fuente/?fuente=biblioteca")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["disponible"], r.json()["esquema"], r.json()["version_app"]), (True, "1.0", "2.1.7"))


class PaqueteInvalidoTests(TestCase):
    """Visto en vivo el 2026-09-28 con AVACOM Contenido 2.1.7: un paquete que no pasa la verificación
    (E-PKG-COURSE) sigue en `/v2/courses`, pero el curso, la lección, el objeto, los medios y `evaluate`
    responden 500 `package_invalid`. El aula no puede dejar sin panel al docente por un paquete roto."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp(prefix="avacom-aula-v2-paquete-")
        self.ruta_enlace = os.path.join(self.carpeta, "link.json")
        sano = manifiesto()
        roto = json.loads(json.dumps(sano))
        roto["id"], roto["title"] = CURSO + ".roto", "Estados de la materia (paquete roto)"
        self.roto = roto["id"]
        self.host = HostContenidoV2Pruebas(self.ruta_enlace, {CURSO: sano, self.roto: roto}, invalidos={self.roto}).iniciar()
        self._ajuste = override_settings(AVACOM_CONTENIDO_ENLACE_V2=self.ruta_enlace)
        self._ajuste.enable()
        self.api = APIClient()

    def tearDown(self):
        self._ajuste.disable()
        self.host.detener()

    def test_la_lista_conserva_la_ficha_marcada_y_los_demas_cursos_siguen(self):
        r = self.api.get("/api/aula/cursos/?fuente=biblioteca")
        self.assertEqual(r.status_code, 200)
        cursos = {c["curso_ref"]: c for c in r.json()["cursos"]}
        self.assertEqual(set(cursos), {CURSO, self.roto})
        self.assertIsNone(cursos[CURSO]["no_disponible"])
        self.assertEqual((cursos[CURSO]["lecciones"], cursos[CURSO]["objetos"]), (3, 7))   # con mode=class el examen no cuenta
        marcado = cursos[self.roto]
        self.assertEqual((marcado["no_disponible"]["codigo"], marcado["no_disponible"]["codigo_biblioteca"]), ("paquete_invalido", "package_invalid"))
        self.assertIn("E-PKG", marcado["no_disponible"]["sugerencia"])
        self.assertEqual((marcado["titulo"], marcado["lecciones"], marcado["objetos"], marcado["portada_url"]),
                         ("Estados de la materia (paquete roto)", 0, 0, None))
        self.assertEqual(marcado["clasificacion"]["asignatura"]["codigo"], "science")   # la ficha trae la clasificación: se agrupa igual
        self.assertEqual(len(r.json()["asignaturas"]), 1)

    def test_abrir_o_evaluar_el_paquete_roto_es_502_paquete_invalido_con_sugerencia(self):
        r = self.api.get(f"/api/aula/cursos/{self.roto}/?fuente=biblioteca")
        self.assertEqual(r.status_code, 502)
        self.assertEqual((r.json()["codigo"], r.json()["codigo_biblioteca"], r.json()["estado_biblioteca"], r.json()["curso_ref"]),
                         ("paquete_invalido", "package_invalid", 500, self.roto))
        self.assertIn("reinstálalo", r.json()["sugerencia"])
        r = self.api.post(f"/api/aula/cursos/{self.roto}/evaluar/?fuente=biblioteca",
                          {"objeto_ref": "l1-activity", "pregunta_ref": "l1-act-q1", "respuesta": {"selectedOptionIds": ["a"]}}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (502, "paquete_invalido"))
        r = self.api.get(f"/api/aula/cursos/{self.roto}/medios/img-particles/?fuente=biblioteca")
        self.assertEqual((r.status_code, r.json()["codigo"]), (502, "paquete_invalido"))
        # El curso sano no se ve afectado.
        self.assertEqual(self.api.get(f"/api/aula/cursos/{CURSO}/?fuente=biblioteca").status_code, 200)
