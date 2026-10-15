"""El tratamiento del texto, la interpretación de la consulta, la expresión de texto completo y la relevancia. Puro: sin base de datos."""
from __future__ import annotations

import unicodedata

from django.test import SimpleTestCase

from ..dominio import catalogos as cat
from ..dominio import consulta as dom
from ..dominio import ranking, texto
from ..dominio.errores import ConsultaInvalida, ConsultaVacia, DatosInvalidos


class NormalizarTests(SimpleTestCase):
    def test_minusculas_sin_tildes_ni_signos(self):
        self.assertEqual(texto.normalizar("Matemáticas"), "matematicas")
        self.assertEqual(texto.normalizar("  Introducción   a las  FRACCIONES!! "), "introduccion a las fracciones")
        self.assertEqual(texto.normalizar("¿Qué es el «agua»?"), "que es el agua")

    def test_la_n_con_tilde_se_conserva(self):
        self.assertEqual(texto.normalizar("AÑO Pequeño"), "año pequeño")
        self.assertNotEqual(texto.normalizar("año"), texto.normalizar("ano"))
        self.assertEqual(texto.normalizar("Ñandú"), "ñandu")

    def test_la_n_descompuesta_y_compuesta_son_la_misma(self):
        descompuesta = unicodedata.normalize("NFD", "señal")
        self.assertNotEqual(descompuesta, "señal")
        self.assertEqual(texto.normalizar(descompuesta), "señal")

    def test_vacio_y_nulo(self):
        self.assertEqual(texto.normalizar(None), "")
        self.assertEqual(texto.normalizar(""), "")
        self.assertEqual(texto.normalizar("¿?!!"), "")


class RaizTests(SimpleTestCase):
    def test_singular_y_plural_comparten_raiz(self):
        for a, b in (("fraccion", "fracciones"), ("matematica", "matematicas"), ("examen", "examenes"), ("año", "años"), ("clase", "clases"),
                     ("profesor", "profesores"), ("evaluacion", "evaluaciones"), ("numero", "numeros")):
            self.assertEqual(texto.raiz(a), texto.raiz(b), (a, b))

    def test_lo_corto_y_los_numeros_no_se_tocan(self):
        for palabra in ("sol", "mes", "8a", "2026", "casa"):
            self.assertEqual(texto.raiz(palabra), palabra)

    def test_raices_de_un_texto(self):
        self.assertEqual(texto.raices("Las fracciones propias"), ["las", "fraccion", "propi"])
        self.assertEqual(texto.para_el_indice("Fracciones y Decimales"), "fraccion y decimal")


class SignificativasTests(SimpleTestCase):
    def test_se_quitan_las_palabras_vacias_si_queda_algo(self):
        self.assertEqual(texto.significativas("suma de fracciones"), ["suma", "fraccion"])

    def test_si_solo_hay_vacias_se_conservan(self):
        self.assertEqual(texto.significativas("de la"), ["de", "la"])


class FragmentoTests(SimpleTestCase):
    def test_resalta_las_palabras_encontradas_por_su_raiz(self):
        trozo, marcas = texto.fragmento("Aprende las Fracciones equivalentes paso a paso", ["fraccion"])
        self.assertEqual(trozo, "Aprende las Fracciones equivalentes paso a paso")
        self.assertEqual([trozo[a:b] for a, b in marcas], ["Fracciones"])

    def test_corta_alrededor_de_lo_encontrado_con_puntos_suspensivos(self):
        largo = "Introducción general. " * 12 + "Aquí se explican las fracciones con ejemplos. " + "Cierre del tema. " * 12
        trozo, marcas = texto.fragmento(largo, ["fraccion"], ancho=100)
        self.assertTrue(trozo.startswith("…") and trozo.endswith("…"))
        self.assertLessEqual(len(trozo), 110)
        self.assertEqual([trozo[a:b] for a, b in marcas], ["fracciones"])

    def test_sin_coincidencia_devuelve_el_comienzo(self):
        trozo, marcas = texto.fragmento("Un texto que no menciona lo buscado " * 10, ["zzz"], ancho=40)
        self.assertEqual(marcas, [])
        self.assertTrue(trozo.startswith("Un texto que no"))
        self.assertTrue(trozo.endswith("…"))

    def test_el_ultimo_termino_vale_como_prefijo(self):
        trozo, marcas = texto.fragmento("Las fracciones propias", ["fracc"], prefijo_final=True)
        self.assertEqual([trozo[a:b] for a, b in marcas], ["fracciones"])

    def test_vacio(self):
        self.assertEqual(texto.fragmento("", ["a"]), ("", []))

    def test_quitar_marcas_de_la_biblioteca(self):
        plano, marcas = texto.quitar_marcas("Las **fracciones** y los **decimales**")
        self.assertEqual(plano, "Las fracciones y los decimales")
        self.assertEqual([plano[a:b] for a, b in marcas], ["fracciones", "decimales"])
        self.assertEqual(texto.quitar_marcas("sin marcas"), ("sin marcas", []))
        self.assertEqual(texto.quitar_marcas("marca **abierta")[0], "marca abierta")


class InterpretarTests(SimpleTestCase):
    def test_una_consulta_normal(self):
        c = dom.interpretar({"q": "  Fracciones   equivalentes "})
        self.assertEqual((c.original, c.normal, c.raices), ("Fracciones equivalentes", "fracciones equivalentes", ("fraccion", "equivalent")))
        self.assertEqual((c.limite, c.pagina, c.desplazamiento), (cat.LIMITE_POR_DEFECTO, 1, 0))

    def test_vacia(self):
        for parametros in ({}, {"q": ""}, {"q": "   "}, {"q": "¿?!"}):
            with self.assertRaises(ConsultaVacia):
                dom.interpretar(parametros)

    def test_demasiado_corta_o_larga(self):
        with self.assertRaises(ConsultaInvalida):
            dom.interpretar({"q": "a"})
        with self.assertRaises(ConsultaInvalida):
            dom.interpretar({"q": "x" * (cat.MAX_CONSULTA + 1)})
        with self.assertRaises(ConsultaInvalida):
            dom.interpretar({"q": " ".join(f"palabra{i}" for i in range(cat.MAX_PALABRAS_DE_LA_CONSULTA + 1))})

    def test_tipos_y_filtros(self):
        c = dom.interpretar({"q": "suma", "type": "course, assessment;class", "country": "CO", "level": "primary", "grade": "4", "subject": "math", "period": "2026",
                             "group": "g-1", "limit": "10", "page": "2"})
        self.assertEqual(c.filtros.tipos, ("course", "assessment", "class"))
        self.assertEqual(c.filtros.del_arbol, {"country": "CO", "level": "primary", "grade": "4", "subject": "math"})
        self.assertTrue(c.filtros.hay_arbol and c.filtros.hay_ambito_de_grupo)
        self.assertEqual((c.limite, c.pagina, c.desplazamiento), (10, 2, 10))

    def test_valores_invalidos(self):
        for parametros in ({"q": "suma", "type": "alumno"}, {"q": "suma", "limit": "0"}, {"q": "suma", "limit": str(cat.LIMITE_MAXIMO + 1)}, {"q": "suma", "limit": "x"},
                           {"q": "suma", "page": "0"}, {"q": "suma", "page": str(cat.PAGINA_MAXIMA + 1)}, {"q": "suma", "country": "x" * 200}):
            with self.assertRaises(DatosInvalidos, msg=parametros):
                dom.interpretar(parametros)


class ExpresionTests(SimpleTestCase):
    def consulta(self, q: str):
        return dom.interpretar({"q": q})

    def test_todas_las_palabras_y_prefijo_en_la_ultima(self):
        self.assertEqual(dom.expresion_match(self.consulta("suma fracciones"), {}), '"suma" AND "fraccion"*')

    def test_alguna_de_las_palabras(self):
        self.assertEqual(dom.expresion_match(self.consulta("suma fracciones"), {}, todas=False), '"suma" OR "fraccion"*')

    def test_sinonimos(self):
        e = dom.expresion_match(self.consulta("examen"), {"examen": ["evaluacion", "prueba"]})
        self.assertEqual(e, '("examen"* OR "evaluacion" OR "prueb")')
        self.assertIn('"cienci natural"', dom.expresion_match(self.consulta("naturales"), {"natural": ["ciencias naturales"]}))

    def test_los_operadores_del_motor_son_palabras_mas(self):
        """Lo que escribe quien busca nunca llega al motor como sintaxis: sólo letras y dígitos, entre comillas."""
        for q in ('fracciones OR 1', '"fracciones', "fracc*", "NEAR(a b)", "-fracciones", "col:fracciones", "fracciones'; DROP TABLE m21_documento;--", "a AND NOT b", "(((("):
            try:
                e = dom.expresion_match(self.consulta(q), {})
            except (ConsultaVacia, ConsultaInvalida):
                continue
            sin_operadores = e.replace(" AND ", " ").replace(" OR ", " ")
            for parte in sin_operadores.split(" "):
                self.assertRegex(parte, r'^"[0-9a-zñ]+"\*?$', f"{q!r} → {e!r}")


class RankingTests(SimpleTestCase):
    def c(self, q: str):
        return dom.interpretar({"q": q})

    def puntaje(self, q: str, **campos) -> tuple[float, str]:
        return ranking.puntuar(self.c(q), **campos)

    def test_la_escalera_de_la_politica(self):
        exacto = self.puntaje("fracciones", titulo="Fracciones")
        titulo = self.puntaje("fracciones", titulo="Introducción a las fracciones")
        parcial = self.puntaje("suma fracciones", titulo="Fracciones equivalentes")
        palabras = self.puntaje("fracciones", titulo="Repaso", palabras="Matemáticas Fracciones")
        descripcion = self.puntaje("fracciones", titulo="Repaso", descripcion="Ejercicios de fracciones")
        contexto = self.puntaje("fracciones", titulo="Repaso", contexto="Octavo A fracciones")
        self.assertEqual(exacto[1], ranking.EXACTO)
        self.assertEqual(titulo[1], ranking.TITULO)
        self.assertEqual(parcial[1], ranking.TITULO)
        self.assertEqual((palabras[1], descripcion[1], contexto[1]), (ranking.PALABRAS_CLAVE, ranking.DESCRIPCION, ranking.CONTEXTO))
        self.assertGreater(exacto[0], titulo[0])
        self.assertGreater(titulo[0], parcial[0])
        self.assertGreater(parcial[0], palabras[0])
        self.assertGreater(palabras[0], descripcion[0])
        self.assertGreater(descripcion[0], contexto[0])

    def test_bm25_desempata_sin_saltar_de_escalon(self):
        flojo, _ = self.puntaje("fracciones", titulo="Introducción a las fracciones", bm25=-0.1)
        fuerte, _ = self.puntaje("fracciones", titulo="Introducción a las fracciones", bm25=-12.0)
        descripcion, _ = self.puntaje("fracciones", titulo="Repaso", descripcion="fracciones", bm25=-50.0)
        self.assertGreater(fuerte, flojo)
        self.assertGreater(flojo, descripcion)
        self.assertLessEqual(fuerte, 1.0)

    def test_la_posicion_de_la_biblioteca_desempata_lo_que_no_trae_bm25(self):
        primero, _ = self.puntaje("fracciones", titulo="Curso de fracciones", posicion=0, total=10)
        ultimo, _ = self.puntaje("fracciones", titulo="Curso de fracciones", posicion=9, total=10)
        self.assertGreater(primero, ultimo)

    def test_el_puntaje_nunca_pasa_de_uno(self):
        self.assertLessEqual(self.puntaje("fracciones", titulo="Fracciones", bm25=-99.0)[0], 1.0)
