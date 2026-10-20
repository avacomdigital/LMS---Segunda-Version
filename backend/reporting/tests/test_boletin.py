"""
El boletín académico individual (2026-10-19): un modelo de información común que responde cuatro preguntas (qué aprendió, qué competencias alcanzó, cómo ha progresado, qué debe
mejorar) con plantillas por país y nivel (Colombia por áreas con desempeños nacionales; México por campos formativos en primaria, disciplinas en secundaria y sin cifras en
preescolar; genérica), armado sobre lo que el libro YA presentó, y su exportación: un xlsx por estudiante o, para un grupo, un zip con un archivo por estudiante. Nunca es un
documento oficial y lo dice.
"""
from __future__ import annotations

import io
import re
import zipfile

from django.test import SimpleTestCase

from gradebook.tests.base import BaseGradebook

from .. import models as m
from ..dominio import boletin as bol
from ..dominio import catalogos as cat
from .base import BaseReporting
from .test_exportacion import como_dict, leer_xlsx

R = "/api/reportes"


class _ConExamenCalificado(BaseGradebook):
    """8A en secundaria con el sistema de Colombia (1,0–5,0), Juan con un examen calificado (sin revisión pendiente) y Ana sin hacer nada. El libro se pone al día a mano: en las
    pruebas no corre el hilo del nodo. Se parte del nodo del libro (no del de los reportes: sus atajos de clase pisan los del examen) y se traen aquí los de leer y exportar reportes."""

    plantilla = "co-1-5"

    def setUp(self):
        super().setUp()
        self.avanzar(seg=10)
        self.a1, self.i1, _, _ = self.examen_entregado(abiertas=False)
        self.sincronizar()
        self.ana_id, _ = self.alumno_con_tableta("Ana", "300501")

    # ---- leer reportes
    def rp(self, ruta: str, cliente=None, esperado: int = 200, **params) -> dict:
        r = (cliente or self.docente).get(f"{R}{ruta}", params)
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

    def asientos(self, accion: str):
        from audit.models import Bitacora
        return list(Bitacora.objects.filter(accion=accion).order_by("secuencia"))

    def eventos_rp(self, *tipos: str) -> list[str]:
        filas = m.EventoSalida.objects.order_by("id")
        if tipos:
            filas = filas.filter(tipo_evento__in=tipos)
        return list(filas.values_list("tipo_evento", flat=True))

    def boletin(self, alumno_id: str | None = None, cliente=None, esperado: int = 200, **params) -> dict:
        return self.rp(f"/boletines/{alumno_id or self.estudiante_id}/", cliente=cliente, esperado=esperado, grupo_id=params.pop("grupo_id", self.grupo["id"]), **params)

    def politica(self, **campos) -> None:
        self.gb("/politica/", campos, metodo="put", cliente=self.admin)

    # ---- exportar
    def exportar(self, reporte: dict, formato: str = "xlsx", destino: str = "carpeta_local", cliente=None, esperado: int = 201, **extra):
        r = (cliente or self.docente).post(f"{R}/exportaciones/", {"reporte": reporte, "formato": formato, "destino_tipo": destino, **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content if not getattr(r, "streaming", False) else b"")
        if esperado != 201:
            return r.json(), b""
        return r, b"".join(r.streaming_content)

    def alcance(self, reporte: dict, formato: str = "xlsx", cliente=None, esperado: int = 200) -> dict:
        r = (cliente or self.docente).post(f"{R}/exportaciones/alcance/", {"reporte": reporte, "formato": formato}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()


class PlantillasTests(SimpleTestCase):
    def test_auto_elige_por_el_pais_y_una_fijada_manda(self):
        self.assertEqual(bol.elegir_plantilla("auto", "CO", "secundaria")["codigo"], "co")
        self.assertEqual(bol.elegir_plantilla("auto", "mx", "primaria")["codigo"], "mx")
        self.assertEqual(bol.elegir_plantilla("auto", "", "primaria")["codigo"], "generica")
        self.assertEqual(bol.elegir_plantilla("auto", "PE", "primaria")["codigo"], "generica")             # sin plantilla propia no se inventa una
        self.assertEqual(bol.elegir_plantilla("mx", "CO", "primaria")["codigo"], "mx")

    def test_colombia_no_impone_periodos_y_trae_los_desempenos_nacionales(self):
        p = bol.elegir_plantilla("co", "CO", "secundaria")
        self.assertEqual((p["periodos"], p["desempenos_nacionales"], p["organizacion"]), ([], ["Superior", "Alto", "Básico", "Bajo"], "Áreas y asignaturas"))
        self.assertIn("1290", p["marco"])

    def test_mexico_primaria_por_campos_formativos_secundaria_por_disciplinas_y_preescolar_sin_cifras(self):
        primaria = bol.elegir_plantilla("mx", "MX", "primaria")
        self.assertEqual((primaria["organizacion"], len(primaria["periodos"]), primaria["sin_cifras"]), ("Campos formativos", 3, False))
        secundaria = bol.elegir_plantilla("mx", "MX", "secundaria")
        self.assertEqual((secundaria["organizacion"], secundaria["rotulo_de_area"]), ("Disciplinas", "Disciplina"))
        preescolar = bol.elegir_plantilla("mx", "MX", "preescolar")
        self.assertTrue(preescolar["sin_cifras"])
        self.assertEqual((bol.campo_formativo_de("math"), bol.campo_formativo_de("social-studies"), bol.campo_formativo_de("arts"), bol.campo_formativo_de("pe"), bol.campo_formativo_de("rara")),
                         ("Saberes y pensamiento científico", "Ética, naturaleza y sociedades", "Lenguajes", "De lo humano y lo comunitario", "Sin clasificar"))

    def test_el_desempeno_nacional_solo_se_dice_cuando_la_escala_ya_lo_nombra_asi(self):
        co = bol.PLANTILLAS["co"]
        self.assertEqual(bol.desempeno_nacional({"desempeno": "Básico"}, co), "Básico")
        self.assertIsNone(bol.desempeno_nacional({"desempeno": "Notable"}, co))                            # otra escala: la equivalencia la declara el SIEE
        self.assertIsNone(bol.desempeno_nacional({"desempeno": "Básico"}, bol.PLANTILLAS["mx"]))

    def _boletin_de_mentira(self, modo="calificaciones"):
        return {"alumno": {"id": "a1", "rotulo": "Ana"}, "grupo": {"id": "g1", "codigo": "3B", "nombre": "Tercero B", "periodo": "2026", "nivel_clave": "primaria"}, "modo": modo,
                "sistema": {"nombre": "México 5–10"},
                "cursos": [{"curso_ref": "avacom.mx.primary.3.math.fracciones", "curso_rotulo": "Fracciones", "materia": "math", "evaluaciones": 2,
                            "conteo": {"con_nota": 2, "aprobadas": 2, "no_aprobadas": 0, "completadas": 2, "pendientes": 0},
                            "bruto": {"puntos": 15, "puntos_maximos": 20, "porcentaje": 75, "evaluaciones": 2}, "promedio_simple": 75,
                            "presentado": {"etiqueta": "7.5", "desempeno": "Bueno", "cumple_criterio": True}},
                           {"curso_ref": "avacom.mx.primary.3.spanish.lectura", "curso_rotulo": "Lectura", "materia": "spanish", "evaluaciones": 1,
                            "conteo": {"con_nota": 0, "aprobadas": 0, "no_aprobadas": 0, "completadas": 0, "pendientes": 1},
                            "bruto": {"puntos": None, "puntos_maximos": None, "porcentaje": None, "evaluaciones": 0}, "promedio_simple": None, "presentado": None}],
                "evaluaciones": {"items": [{"asignacion_id": "e1", "titulo": "Quiz 1", "curso_ref": "avacom.mx.primary.3.math.fracciones", "curso_rotulo": "Fracciones", "materia": "math",
                                            "tipo_evaluacion": "sumativa", "fecha": 1, "estado": "definitivo", "estado_simple": "completado", "publicada": True,
                                            "bruto": {"puntos": 8, "puntos_maximos": 10, "porcentaje": 80}, "presentacion": {"presentada": {"etiqueta": "8.0"}, "desempeno": {"nivel": "Bueno"},
                                                                                                                             "aprobacion": {"cumple_criterio": True}, "provisional": False}}]},
                "insights": {"comentarios": {"fortalezas": [{"texto": "Suma bien", "titulo": "Quiz 1", "fecha": 1}], "dificultades": [], "oportunidades": [{"texto": "Practicar", "titulo": "Quiz 1", "fecha": 1}]},
                             "tendencia": {"direccion": "insuficiente"}, "curso_a_reforzar": None, "mejor_curso": None},
                "observaciones": [{"curso_ref": "", "recomendaciones": [{"codigo": "pedir_ayuda", "texto": "Pedir ayuda"}], "texto": "Ánimo", "actualizada_en": 5}],
                "resumen": {"evaluaciones": 3, "conteo": {"con_nota": 2, "aprobadas": 2, "no_aprobadas": 0, "completadas": 2, "pendientes": 1}, "promedio_simple": 75,
                            "presentado": {"etiqueta": "7.5"}, "bruto": {"puntos": 15, "puntos_maximos": 20, "porcentaje": 75, "evaluaciones": 2}}}

    def test_el_modelo_mexicano_de_primaria_agrupa_las_materias_en_campos_formativos(self):
        modelo = bol.armar_modelo(self._boletin_de_mentira(), [], {"pais": "MX", "institucion": "Esc. Benito Juárez"}, {"plantilla_boletin": "auto"}, nombres_de_materias={"math": "Matemáticas"})
        self.assertEqual(modelo["plantilla"]["codigo"], "mx")
        self.assertEqual([a["rotulo"] for a in modelo["areas"]], ["Lenguajes", "Saberes y pensamiento científico"])
        saberes = next(a for a in modelo["areas"] if a["rotulo"].startswith("Saberes"))
        self.assertEqual((saberes["bruto"]["puntos"], saberes["bruto"]["puntos_maximos"], saberes["cursos"][0]["curso_rotulo"], saberes["presentado"]["etiqueta"]), (15, 20, "Fracciones", "7.5"))
        self.assertEqual(modelo["evaluaciones"][0]["area"], "Saberes y pensamiento científico")
        self.assertEqual((modelo["competencias"]["logros"][0]["texto"], modelo["competencias"]["evaluaciones_aprobadas"]), ("Suma bien", ["Quiz 1"]))
        self.assertEqual(modelo["recomendaciones"]["del_docente"][0]["recomendaciones"], ["Pedir ayuda"])
        self.assertEqual(modelo["recomendaciones"]["oportunidades"][0]["texto"], "Practicar")
        self.assertEqual((modelo["institucion"]["nombre"], modelo["resumen"]["oficial"], modelo["sin_cifras"]), ("Esc. Benito Juárez", False, False))
        self.assertIn("No es un boletín ni una boleta oficial", modelo["leyenda"])

    def test_sin_sistema_o_en_preescolar_no_hay_cifras(self):
        modelo = bol.armar_modelo(self._boletin_de_mentira(modo="simple"), [], {"pais": "MX"}, {"plantilla_boletin": "auto"})
        self.assertTrue(modelo["sin_cifras"])
        self.assertTrue(all(c["presentado"] is None and c["promedio_simple"] is None and c["bruto"]["puntos"] is None for a in modelo["areas"] for c in a["cursos"]))
        self.assertTrue(all(e["bruto"] is None and e["presentada"] is None for e in modelo["evaluaciones"]))
        self.assertEqual((modelo["resumen"]["promedio_simple"], modelo["resumen"]["presentado"], modelo["sistema"]), (None, None, None))

    def test_la_configuracion_del_nodo_cambia_plantilla_periodos_y_leyenda(self):
        modelo = bol.armar_modelo(self._boletin_de_mentira(), [], {"pais": "MX"}, {"plantilla_boletin": "co", "periodos_boletin": ["Primer semestre", "Segundo semestre"], "leyenda_boletin": "Leyenda propia"})
        self.assertEqual((modelo["plantilla"]["codigo"], modelo["plantilla"]["periodos"], modelo["leyenda"]), ("co", ["Primer semestre", "Segundo semestre"], "Leyenda propia"))
        self.assertEqual([a["rotulo"] for a in modelo["areas"]], ["Math", "Spanish"])                     # sin la biblioteca, el código en palabras

    def test_el_documento_tiene_una_hoja_por_pregunta_y_una_de_datos(self):
        modelo = bol.armar_modelo(self._boletin_de_mentira(), [{"grupo_id": "g1", "grupo_codigo": "3B", "periodo": "2026", "curso_ref": "avacom.mx.primary.3.math.fracciones", "calificaciones": 2,
                                                               "promedio_simple": 75, "presentado": {"etiqueta": "7.5"}, "modo": "calificaciones"}], {"pais": "MX"}, {})
        ctx = {"generado_por": "Prof.", "generado_el": "hoy", "corte_texto": "hoy", "version_nodo": "x", "fecha": lambda ms: "d"}
        d = bol.documento_de_boletin(modelo, ctx)
        self.assertEqual([t.nombre for t in d.tablas], ["1 Qué aprendió", "1b Evaluaciones", "2 Competencias", "3 Progreso", "4 Qué debe mejorar", "Datos"])
        self.assertEqual(dict(d.cabecera)["Estudiante"], "Ana")
        self.assertEqual(dict(d.cabecera)["Organización"], "Campos formativos")
        self.assertTrue(d.nominal)
        self.assertEqual(d.tablas[3].filas[0][:3], ["2026", "3B", "Fracciones"])
        self.assertEqual(d.tablas[4].filas[0][1], "Pedir ayuda")
        self.assertTrue(any("No es un boletín" in n for n in d.notas))


class BoletinDeUnEstudianteTests(_ConExamenCalificado):
    def test_responde_las_cuatro_preguntas_con_la_nota_en_bruto_presentada_y_el_desempeno(self):
        self.politica(pais="CO", institucion="IE San José")
        r = self.boletin()
        self.assertEqual((r["tipo"], r["nominal"], r["privacidad"]["aplicada"], r["alumno"]["rotulo"]), ("boletin", True, False, "Juan P."))
        b = r["boletin"]
        self.assertEqual((b["plantilla"]["codigo"], b["institucion"]["nombre"], b["periodo"], b["modo"]), ("co", "IE San José", "2026", "calificaciones"))
        self.assertEqual(b["preguntas"], ["¿Qué aprendió?", "¿Qué competencias alcanzó?", "¿Cómo ha progresado?", "¿Qué debe mejorar?"])
        area, = b["areas"]
        curso, = area["cursos"]
        self.assertEqual((area["rotulo"], curso["evaluaciones"], curso["con_nota"]), ("Science", 1, 1))             # la biblioteca de prueba no nombra las materias: el código en palabras
        self.assertIsNotNone(curso["bruto"]["puntos"])
        self.assertGreater(curso["bruto"]["puntos_maximos"], curso["bruto"]["puntos"])
        self.assertEqual((curso["presentado"]["etiqueta"], curso["desempeno"], curso["desempeno_nacional"], curso["cumple_criterio"]), ("3.8", "Básico", "Básico", True))
        e, = b["evaluaciones"]
        self.assertEqual((e["titulo"], e["presentada"], e["desempeno"], e["publicada"], e["provisional"]), (self.a1["titulo"], "3.8", "Básico", False, True))
        self.assertEqual(b["competencias"]["evaluaciones_aprobadas"], [self.a1["titulo"]])
        self.assertEqual(b["competencias"]["objetivos"]["disponible"], False)
        self.assertEqual([(f["periodo"], f["actual"]) for f in b["progreso"]["filas"]], [("2026", True)])
        self.assertEqual(b["progreso"]["periodos"], ["2026"])
        self.assertEqual((b["resumen"]["con_nota"], b["resumen"]["oficial"], b["resumen"]["bruto"]["evaluaciones"]), (1, False, 1))
        self.assertIn("No es un boletín ni una boleta oficial", b["leyenda"])

    def test_las_recomendaciones_del_profesor_entran_en_la_cuarta_pregunta(self):
        self.gb(f"/estudiantes/{self.estudiante_id}/observacion/", {"grupo_id": self.grupo["id"], "recomendaciones": ["practicar_ejercicios"], "texto": "Buen trabajo"}, metodo="put")
        rec = self.boletin()["boletin"]["recomendaciones"]["del_docente"]
        self.assertEqual((rec[0]["curso_rotulo"], rec[0]["recomendaciones"], rec[0]["texto"]), ("General", ["Practicar más ejercicios del tema con el modo estudio"], "Buen trabajo"))

    def test_sin_grupo_se_toma_el_primero_visible_y_un_grupo_ajeno_da_404(self):
        self.assertEqual(self.boletin(grupo_id="")["grupo"]["id"], self.grupo["id"])
        self.boletin(grupo_id=self.otro_grupo["id"], esperado=404, cliente=self.admin)
        self.boletin(alumno_id="no-existe", grupo_id="", esperado=409)                                        # sin grupo activo: no hay boletín que armar

    def test_quien_puede_y_quien_no_y_el_rastro(self):
        _, ruiz, _ = self.otro_docente()
        self.boletin(cliente=ruiz, esperado=403)
        self.boletin(cliente=self.tecnico(), esperado=403)
        self.boletin(cliente=self.reportes())
        self.boletin(cliente=self.admin)
        self.boletin()
        self.assertEqual([a.valor_nuevo["codigo"] for a in self.asientos("reporte.acceso_denegado")], ["fuera_de_alcance", "sin_permiso"])
        self.assertEqual(self.eventos_rp("reporte.boletin_generado.v1"), ["reporte.boletin_generado.v1"] * 3)
        self.assertEqual([a.valor_nuevo["reporte"] for a in self.asientos("reporte.generado")][:1], ["boletin"])
        self.assertNotIn("Juan", str([a.valor_nuevo for a in self.asientos("reporte.generado")]))
        self.assertEqual([x["titulo"] for x in self.rp("/recientes/")["recientes"]], ["Boletín de Juan P."])

    def test_el_filtro_por_materia_recorta_el_boletin(self):
        self.assertEqual(len(self.boletin(subject="science")["boletin"]["evaluaciones"]), 1)
        self.assertEqual(self.boletin(subject="math")["boletin"]["evaluaciones"], [])


class BoletinesDelGrupoTests(_ConExamenCalificado):
    def test_un_boletin_por_estudiante_en_orden_alfabetico(self):
        r = self.rp("/boletines/", grupo_id=self.grupo["id"])
        self.assertEqual((r["tipo"], r["totales"]["estudiantes"], r["totales"]["boletines"], r["totales"]["con_nota"]), ("boletin", 2, 2, 1))
        self.assertEqual([b["estudiante"]["rotulo"] for b in r["boletines"]], ["Ana", "Juan P."])
        self.assertEqual([x["titulo"] for x in self.rp("/recientes/")["recientes"]], ["Boletines del grupo 8A"])

    def test_sin_grupo_o_ajeno(self):
        self.rp("/boletines/", esperado=404)
        _, ruiz, _ = self.otro_docente()
        self.rp("/boletines/", cliente=ruiz, grupo_id=self.grupo["id"], esperado=403)


class ExportarBoletinTests(_ConExamenCalificado):
    def test_el_boletin_de_un_estudiante_es_un_xlsx_con_las_cuatro_preguntas_y_los_datos(self):
        self.politica(pais="CO")
        d = {"tipo": "boletin", "alumno_id": self.estudiante_id, "grupo_id": self.grupo["id"]}
        a = self.alcance(d)
        self.assertEqual((a["tipo"], a["alumnos"], a["archivos"], a["formato_de_entrega"], a["nominal"]), ("boletin", 1, 1, "xlsx", True))
        self.assertTrue(re.fullmatch(r"reporte-boletin-8A-2026-09-2\d-\d{4}\.xlsx", a["nombre_sugerido"]), a["nombre_sugerido"])
        self.assertIn("el boletín académico de un estudiante del grupo 8A", a["texto_alcance"])
        self.assertEqual(a["plantilla"], "Colombia · boletín por áreas y asignaturas")
        r, cuerpo = self.exportar(d)
        self.assertEqual(r["X-Avacom-Export-Formato"], "xlsx")
        hojas = leer_xlsx(cuerpo)
        self.assertEqual(list(hojas), ["Resumen", "1 Qué aprendió", "1b Evaluaciones", "2 Competencias", "3 Progreso", "4 Qué debe mejorar", "Datos"])
        resumen = como_dict(hojas["Resumen"])
        self.assertEqual((resumen["Estudiante"], resumen["Grupo"], resumen["Organización"]), ("Juan P.", "Octavo A", "Áreas y asignaturas"))
        self.assertEqual(resumen["Con nota"], 1.0)
        fila = hojas["1 Qué aprendió"][1]
        self.assertEqual(fila[0], "Science")
        self.assertIn("de", fila[5])                                                                              # «14 de 18»: los puntos brutos
        self.assertEqual(fila[-1], "Básico")                                                                      # el desempeño nacional
        self.assertTrue(any("No es un boletín" in str(f) for f in hojas["Resumen"]))

    def test_los_boletines_de_un_grupo_van_en_un_zip_con_un_archivo_por_estudiante(self):
        d = {"tipo": "boletin", "grupo_id": self.grupo["id"]}
        a = self.alcance(d)
        self.assertEqual((a["alumnos"], a["archivos"], a["formato_de_entrega"]), (2, 2, "zip"))
        self.assertTrue(re.fullmatch(r"reporte-boletines-8A-2026-09-2\d-\d{4}\.zip", a["nombre_sugerido"]), a["nombre_sugerido"])
        self.assertIn("un archivo por estudiante, en un zip", a["texto_alcance"])
        r, cuerpo = self.exportar(d)
        self.assertEqual((r["Content-Type"], r["X-Avacom-Export-Formato"]), ("application/zip", "zip"))
        self.assertTrue(r["X-Avacom-Export-Nombre"].endswith(".zip"))
        z = zipfile.ZipFile(io.BytesIO(cuerpo))
        self.assertIsNone(z.testzip())
        self.assertEqual(z.namelist(), ["boletin-01-Ana.xlsx", "boletin-02-Juan P.xlsx"])
        for nombre in z.namelist():
            hojas = leer_xlsx(z.read(nombre))
            self.assertEqual(list(hojas)[:2], ["Resumen", "1 Qué aprendió"])
        self.assertEqual(m.Exportacion.objects.get().formato, "zip")
        # el mismo grupo en csv: un csv por estudiante dentro del zip
        _, cuerpo_csv = self.exportar(d, formato="csv")
        self.assertEqual(zipfile.ZipFile(io.BytesIO(cuerpo_csv)).namelist(), ["boletin-01-Ana.csv", "boletin-02-Juan P.csv"])
        self.assertTrue(zipfile.ZipFile(io.BytesIO(cuerpo_csv)).read("boletin-01-Ana.csv").startswith(b"\xef\xbb\xbf"))

    def test_misma_entrada_mismos_bytes_tambien_en_el_zip(self):
        d = {"tipo": "boletin", "grupo_id": self.grupo["id"]}
        _, a = self.exportar(d)
        _, b = self.exportar(d)
        self.assertEqual(a, b)

    def test_quien_no_ve_al_estudiante_no_exporta_su_boletin(self):
        _, ruiz, _ = self.otro_docente()
        self.exportar({"tipo": "boletin", "alumno_id": self.estudiante_id, "grupo_id": self.grupo["id"]}, cliente=ruiz, esperado=403)
        self.exportar({"tipo": "boletin", "grupo_id": self.grupo["id"]}, cliente=self.tecnico(), esperado=403)


class ConfiguracionDelBoletinTests(BaseReporting):
    def test_la_administracion_fija_plantilla_periodos_y_leyenda(self):
        r = self.admin.put("/api/reportes/configuracion/", {"plantilla_boletin": "mx", "periodos_boletin": ["1.er periodo", "2.º periodo", "3.er periodo"], "leyenda_boletin": "  Base de  trabajo "}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c = r.json()["configuracion"]
        self.assertEqual((c["plantilla_boletin"], c["periodos_boletin"], c["leyenda_boletin"], c["plantillas_de_boletin"]), ("mx", ["1.er periodo", "2.º periodo", "3.er periodo"], "Base de trabajo", ["auto", "co", "mx", "generica"]))
        self.assertEqual(self.rp("/configuracion/")["configuracion"]["plantilla_boletin"], "mx")
        asiento, = self.asientos("reporte.configuracion_cambiada")
        self.assertEqual((asiento.valor_anterior["plantilla_boletin"], asiento.valor_nuevo["plantilla_boletin"]), ("auto", "mx"))
        repetido = self.admin.put("/api/reportes/configuracion/", {"plantilla_boletin": "mx"}, format="json").json()
        self.assertFalse(repetido["cambiado"])

    def test_lo_que_no_vale(self):
        for cuerpo in ({"plantilla_boletin": "fr"}, {"periodos_boletin": "uno"}, {"periodos_boletin": [""]}, {"periodos_boletin": ["a"] * 7}, {"periodos_boletin": ["a", "a"]}, {"leyenda_boletin": 5}):
            r = self.admin.put("/api/reportes/configuracion/", cuerpo, format="json")
            self.assertEqual(r.status_code, 400, cuerpo)
        self.assertEqual(self.docente.put("/api/reportes/configuracion/", {"plantilla_boletin": "co"}, format="json").status_code, 403)

    def test_el_catalogo_de_tipos_incluye_el_boletin_con_su_permiso_y_su_evento(self):
        self.assertIn(cat.BOLETIN, cat.TIPOS)
        self.assertEqual((cat.PERMISO_DE_TIPO[cat.BOLETIN], cat.EVENTO_DE_TIPO[cat.BOLETIN]), (cat.P_STUDENT, "reporte.boletin_generado.v1"))
