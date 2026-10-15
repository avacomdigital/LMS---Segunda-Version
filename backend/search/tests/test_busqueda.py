"""
La búsqueda (CAP-124 y CAP-125) por HTTP, con el nodo de las pruebas de la evaluación: texto, tildes y ñ, relevancia, varias palabras, prefijo, sinónimos, sintaxis
hostil, paginación, tipos y filtros de grupo y ciclo. Las evaluaciones, los estudios y las clases nacen POR LAS RUTAS REALES de sus módulos.
"""
from __future__ import annotations

import json

from django.db import connection

from evaluacion import models as m10

from .. import models as m
from .base import SEARCH, BaseSearch


class TextoTests(BaseSearch):
    def test_encuentra_sin_importar_tildes_mayusculas_ni_plural(self):
        a = self.evaluacion("Introducción a las fracciones")
        for q in ("fraccion", "FRACCIÓN", "fracciones", "  Fraccion   ", "introduccion fracciones"):
            self.assertEqual(self.ids(self.buscar(q)), [a["id"]], q)

    def test_la_n_con_tilde_es_otra_letra(self):
        con = self.evaluacion("El año escolar")
        sin = self.evaluacion("El ano")
        self.assertEqual(self.ids(self.buscar("año")), [con["id"]])
        self.assertEqual(self.ids(self.buscar("AÑOS")), [con["id"]])
        self.assertEqual(self.ids(self.buscar("ano")), [sin["id"]])

    def test_consulta_vacia_corta_o_larga_es_400_con_codigo(self):
        self.assertEqual(self.buscar("", esperado=400)["codigo"], "consulta_vacia")
        self.assertEqual(self.buscar("   ", esperado=400)["codigo"], "consulta_vacia")
        self.assertEqual(self.docente.get(f"{SEARCH}/").json()["codigo"], "consulta_vacia")
        self.assertEqual(self.buscar("a", esperado=400)["codigo"], "consulta_invalida")
        self.assertEqual(self.buscar("x" * 121, esperado=400)["codigo"], "consulta_invalida")

    def test_sin_coincidencias_no_es_un_error(self):
        self.evaluacion("Estados de la materia")
        r = self.buscar("trigonometría")
        self.assertEqual((r["total"], r["results"], r["has_more"]), (0, [], False))
        self.assertEqual((r["index_status"], r["index_notice"]), ("consultable", ""))

    def test_el_ultimo_termino_vale_como_prefijo(self):
        a = self.evaluacion("Fracciones equivalentes")
        self.assertEqual(self.ids(self.buscar("fracc")), [a["id"]])
        self.assertEqual(self.ids(self.buscar("fracciones equi")), [a["id"]])
        # sólo la ÚLTIMA palabra es prefijo: «equi» no coincide como prefijo, así que no hay «todas» y se relaja a «alguna»
        self.assertEqual(self.buscar("equi fracciones")["match_mode"], "any")

    def test_varias_palabras_exigen_todas_y_si_ninguna_cumple_se_relaja_a_alguna(self):
        suma = self.evaluacion("Suma de fracciones")
        resta = self.evaluacion("Resta de decimales")
        todas = self.buscar("suma fracciones")
        self.assertEqual((self.ids(todas), todas["match_mode"]), ([suma["id"]], "all"))
        alguna = self.buscar("suma decimales")
        self.assertEqual(alguna["match_mode"], "any")
        self.assertEqual(sorted(self.ids(alguna)), sorted([suma["id"], resta["id"]]))

    def test_las_palabras_vacias_no_estorban(self):
        a = self.evaluacion("Fracciones equivalentes")
        self.assertEqual(self.ids(self.buscar("las fracciones de la")), [a["id"]])

    def test_sinonimos_de_partida_examen_evaluacion_prueba(self):
        a = self.evaluacion("Prueba diagnóstica")
        self.assertEqual(self.ids(self.buscar("examen diagnostica")), [a["id"]])
        self.assertEqual(self.ids(self.buscar("evaluacion diagnostica")), [a["id"]])

    def test_la_administracion_configura_sinonimos_y_se_aplican_al_consultar(self):
        a = self.evaluacion("Repaso de mates")
        self.assertEqual(self.ids(self.buscar("matematicas")), [a["id"]])          # ya viene de fábrica: matemáticas ≈ mates
        r = self.admin.put(f"{SEARCH}/synonyms/", {"groups": [["balon", "pelota", "esférico"], ["x"]]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["groups"], [["balon", "pelota", "esferico"]])       # normalizados; un grupo de una palabra no equivale a nada
        self.assertEqual(self.ids(self.buscar("matematicas")), [])                  # se reemplazó todo
        b = self.evaluacion("La pelota")
        self.assertEqual(self.ids(self.buscar("balon")), [b["id"]])
        self.assertEqual(self.admin.get(f"{SEARCH}/synonyms/").json()["groups"], [["balon", "pelota", "esferico"]])
        self.assertEqual(self.docente.put(f"{SEARCH}/synonyms/", {"groups": []}, format="json").status_code, 403)
        self.assertEqual(self.admin.put(f"{SEARCH}/synonyms/", {"groups": "no"}, format="json").status_code, 400)

    def test_sintaxis_del_motor_escrita_por_el_usuario_nunca_rompe_nada(self):
        self.evaluacion("Fracciones equivalentes")
        for q in ('fracciones OR 1', '"fracciones', "fracc*", "NEAR(a b)", "-fracciones", "col:fracciones", "fracciones'; DROP TABLE m21_documento;--",
                  "a AND NOT b", "((((", "%%%", "\\", "titulo:fracciones", "fracciones NOT equivalentes", "\"\"", "*", "^fracciones"):
            r = self.docente.get(f"{SEARCH}/", {"q": q})
            self.assertIn(r.status_code, (200, 400), (q, r.content))
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM m21_documento")
            self.assertGreaterEqual(cursor.fetchone()[0], 1)

    def test_el_motor_no_recibe_texto_del_usuario_dentro_del_sql(self):
        """La consulta del usuario viaja sólo como PARÁMETRO: lo que recibe el motor (el SQL y, aparte, sus parámetros) no lleva ni una letra de lo escrito en el SQL."""
        self.evaluacion("Fracciones equivalentes")
        self.buscar("fracciones")                      # la primera consulta construye el índice; la medida es de la segunda
        capturado: list[tuple[str, tuple]] = []

        def envoltorio(ejecutar, sql, parametros, muchos, contexto):
            capturado.append((sql, tuple(parametros or ())))
            return ejecutar(sql, parametros, muchos, contexto)

        with connection.execute_wrapper(envoltorio):
            self.buscar("zzzmarcadorzzz OR fracciones")
        con_texto = [(sql, p) for sql, p in capturado if "m21_documento_fts MATCH" in sql]
        self.assertTrue(con_texto)
        for sql, parametros in con_texto:
            self.assertNotIn("zzzmarcadorzzz", sql)
            self.assertTrue(any("zzzmarcadorzzz" in str(p) for p in parametros))


class RelevanciaTests(BaseSearch):
    def test_el_titulo_exacto_va_primero_y_luego_titulo_palabras_clave_y_descripcion(self):
        descripcion = self.evaluacion("Guía de repaso", descripcion="Ejercicios con fracciones para casa")
        parcial = self.evaluacion("Repaso de fracciones y decimales")
        exacto = self.evaluacion("Fracciones")
        r = self.buscar("fracciones")
        self.assertEqual(self.ids(r), [exacto["id"], parcial["id"], descripcion["id"]])
        self.assertEqual([x["match"] for x in r["results"]], ["titulo_exacto", "titulo", "descripcion"])
        puntajes = [x["score"] for x in r["results"]]
        self.assertEqual(puntajes, sorted(puntajes, reverse=True))
        self.assertTrue(all(0 < p <= 1 for p in puntajes))

    def test_las_palabras_clave_del_curso_cuentan_despues_del_titulo(self):
        """«materia» está en el curso de ejemplo («Estados de la materia y sus cambios»): para estas evaluaciones es palabra clave; en otra es el título."""
        por_curso = self.evaluacion("Examen final")
        por_titulo = self.evaluacion("Repaso de la materia")
        exacta = self.evaluacion("Materia")
        r = self.buscar("materia")
        self.assertEqual(self.ids(r), [exacta["id"], por_titulo["id"], por_curso["id"]])
        self.assertEqual([x["match"] for x in r["results"]], ["titulo_exacto", "titulo", "palabras_clave"])

    def test_un_resultado_trae_lo_que_el_cliente_necesita_para_abrirlo(self):
        a = self.evaluacion("Fracciones")
        x = self.buscar("fracciones")["results"][0]
        self.assertEqual((x["id"], x["entity_type"], x["entity_id"], x["source"], x["subtype"]), (a["id"], "assessment", a["id"], "local", "examen"))
        self.assertEqual(x["context"]["group_name"], "Octavo A")
        self.assertEqual(x["context"]["period"], "2026")
        self.assertEqual(x["navigation_target"]["entity_id"], a["id"])
        self.assertEqual(x["navigation_target"]["group_id"], self.grupo["id"])
        self.assertEqual(x["navigation_target"]["object_ref"], "l3-exam")
        self.assertIn("Estados de la materia", x["context"]["course_label"])

    def test_el_resultado_resalta_lo_encontrado_en_la_descripcion(self):
        self.evaluacion("Guía", descripcion="Ejercicios de fracciones equivalentes")
        x = self.buscar("fracciones")["results"][0]
        self.assertEqual([x["snippet"][a:b] for a, b in x["highlights"]], ["fracciones"])


class PaginacionTests(BaseSearch):
    def test_paginas_disjuntas_con_el_total_visible(self):
        ids = [self.evaluacion(f"Repaso {n} de fracciones")["id"] for n in range(7)]
        p1 = self.buscar("fracciones", limit=3, page=1)
        p2 = self.buscar("fracciones", limit=3, page=2)
        p3 = self.buscar("fracciones", limit=3, page=3)
        p4 = self.buscar("fracciones", limit=3, page=4)
        self.assertEqual([p["total"] for p in (p1, p2, p3, p4)], [7, 7, 7, 7])
        self.assertEqual([len(p["results"]) for p in (p1, p2, p3, p4)], [3, 3, 1, 0])
        self.assertEqual([p["has_more"] for p in (p1, p2, p3)], [True, True, False])
        vistos = self.ids(p1) + self.ids(p2) + self.ids(p3)
        self.assertEqual(sorted(vistos), sorted(ids))
        self.assertEqual(len(set(vistos)), 7)
        self.assertEqual((p1["page"], p1["page_size"], p1["total_exact"]), (1, 3, True))

    def test_el_orden_es_estable_entre_consultas(self):
        for n in range(5):
            self.evaluacion(f"Repaso {n} de fracciones")
        self.assertEqual(self.ids(self.buscar("fracciones")), self.ids(self.buscar("fracciones")))

    def test_parametros_invalidos(self):
        self.evaluacion("Fracciones")
        for parametros in ({"limit": 0}, {"limit": 51}, {"limit": "x"}, {"page": 0}, {"page": "y"}):
            self.assertEqual(self.buscar("fracciones", esperado=400, **parametros)["codigo"], "datos_invalidos", parametros)


class TiposYFiltrosTests(BaseSearch):
    def sembrar(self):
        self.ev = self.evaluacion("Estados de la materia")
        self.es = self.estudio("l1-three-states", titulo="Estados de la materia en casa")
        self.cl = self.clase()
        self.sincronizar()

    def test_los_tres_tipos_del_lms_se_buscan_juntos(self):
        self.sembrar()
        r = self.buscar("materia")
        self.assertEqual(sorted(x["entity_type"] for x in r["results"]), ["assessment", "class", "study"])

    def test_filtro_por_tipo(self):
        self.sembrar()
        self.assertEqual(self.ids(self.buscar("materia", type="assessment")), [self.ev["id"]])
        self.assertEqual(sorted(x["entity_type"] for x in self.buscar("materia", type="study,class")["results"]), ["class", "study"])
        self.assertEqual(self.buscar("materia", type="course")["total"], 0)
        self.assertEqual(self.buscar("materia", esperado=400, type="alumno")["codigo"], "datos_invalidos")

    def test_una_clase_se_encuentra_por_su_leccion_y_su_grupo(self):
        self.sembrar()
        r = self.buscar("tres estados", type="class")
        self.assertEqual(self.ids(r), [self.cl["id"]])
        self.assertEqual(r["results"][0]["context"]["group_name"], "Octavo A")
        self.assertEqual(self.ids(self.buscar("octavo", type="class")), [self.cl["id"]])

    def test_filtro_por_grupo_y_por_ciclo(self):
        otro_id = self.admin.post("/api/acceso/grupos/", {"codigo": "8B", "nombre": "Octavo B", "periodo": "2027"}, format="json").json()["id"]
        r = self.admin.post(f"/api/acceso/grupos/{otro_id}/miembros/", {"usuario_id": self.docente_id, "papel": "DOCENTE"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        a = self.evaluacion("Fracciones del 8A")
        b = self.evaluacion("Fracciones del 8B", grupo_id=otro_id)
        self.assertEqual(sorted(self.ids(self.buscar("fracciones"))), sorted([a["id"], b["id"]]))
        self.assertEqual(self.ids(self.buscar("fracciones", group=otro_id)), [b["id"]])
        self.assertEqual(self.ids(self.buscar("fracciones", group=self.grupo["id"])), [a["id"]])
        self.assertEqual(self.ids(self.buscar("fracciones", period="2027")), [b["id"]])
        self.assertEqual(self.ids(self.buscar("fracciones", period="2026")), [a["id"]])
        self.assertEqual(self.buscar("fracciones", period="1999")["total"], 0)
        self.assertEqual(self.buscar("fracciones", group=otro_id, period="2026")["total"], 0)       # el grupo no es de ese ciclo
        self.assertEqual(self.ids(self.buscar("fracciones", group=otro_id, period="2027")), [b["id"]])

    def test_los_filtros_se_combinan_con_el_texto(self):
        self.sembrar()
        self.assertEqual(self.ids(self.buscar("estados", type="study", group=self.grupo["id"], period="2026")), [self.es["id"]])
        self.assertEqual(self.buscar("estados", type="study", period="2027")["total"], 0)

    def test_buscar_no_cambia_nada_de_los_modulos_propietarios(self):
        """FUN-211: Search nunca modifica las entidades originales ni escribe en sus colas."""
        self.sembrar()
        antes = (m10.Asignacion.objects.count(), m10.EventoSalida.objects.count(), list(m10.Asignacion.objects.values_list("id", "estado", "titulo")))
        for q in ("materia", "estados", "fracciones", "tres estados"):
            self.buscar(q)
        despues = (m10.Asignacion.objects.count(), m10.EventoSalida.objects.count(), list(m10.Asignacion.objects.values_list("id", "estado", "titulo")))
        self.assertEqual(antes, despues)

    def test_la_respuesta_no_filtra_texto_de_otros(self):
        self.evaluacion("Fracciones")
        cuerpo = json.dumps(self.buscar("fracciones"))
        for prohibido in ("alias", "token", "hash", "secreto"):
            self.assertNotIn(prohibido, cuerpo.lower())

    def test_estudios_y_clases_sin_grupo_los_ve_solo_quien_los_creo(self):
        """Una clase sin padrón (Q-34) pertenece a quien la abrió: no es de ningún grupo y ninguna otra persona la ve."""
        c = self.api.post("/api/aula/sesiones/", {"via": "leccion", "curso_ref": "avacom.co.lower-secondary.6.science.states-of-matter",
                                                 "leccion_ref": "l1-three-states", "fuente": "ejemplo", "profesor_id": self.docente_id,
                                                 "profesor_rotulo": "Prof. Gómez", "superficie": "pantalla"}, format="json").json()
        otro_id, otro = self.otro_docente()
        self.sincronizar()
        self.assertEqual(self.ids(self.buscar("estados", type="class")), [c["id"]])
        self.assertEqual(self.buscar("estados", cliente=otro, type="class")["total"], 0)
        self.assertEqual(self.ids(self.buscar("estados", cliente=self.admin, type="class")), [c["id"]])
        self.assertEqual(m.Documento.objects.filter(tipo="class").count(), 1)
