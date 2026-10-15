"""
CAP-081 · el reporte de la clase al terminarla, con participación y aciertos (TST-008): una clase cerrada hace cinco minutos, 25 alumnos, 25 filas y el promedio calculado; lo que cada
cifra significa; qué pasa con una clase abierta, con quien no entregó y con quien no entró; y quién puede verlo.
"""
from __future__ import annotations

from .base import BaseReporting


class ReporteDeClaseTests(BaseReporting):
    def test_tst_008_clase_cerrada_hace_cinco_minutos_da_25_filas_y_el_promedio(self):
        """TST-008: abrir reportes, filtrar por clase → 25 filas y promedio calculado."""
        notas = [(5, 5)] * 15 + [(0, 5)] * 10                         # quince con todo bien (100 %) y diez con todo mal (0 %: una cifra real, no una ausencia)
        c = self.clase_cerrada(notas)
        self.avanzar(minutos=5)
        listado = self.rp("/clases/", grupo_id=self.grupo["id"])
        self.assertEqual([x["sesion_id"] for x in listado["clases"]], [c["sesion"]["id"]])
        r = self.reporte_de_clase(c["sesion"]["id"])
        self.assertEqual(len(r["filas"]), 25)
        self.assertEqual(r["totales"]["participantes"], 25)
        # promedio simple de los alumnos: (15·100 + 10·0) / 25 = 60 %
        self.assertEqual(r["totales"]["promedio_aciertos"], 60)
        self.assertEqual(r["totales"]["promedio_participacion"], 100)
        self.assertEqual(r["totales"]["actividades"], 1)
        self.assertEqual({f["actividades_entregadas"] for f in r["filas"]}, {1})
        self.assertEqual(sorted({f["porcentaje_aciertos"] for f in r["filas"]}), [0, 100])
        self.assertTrue(r["nominal"])
        self.assertEqual(r["filas"][0]["alumno"], sorted(f["alumno"] for f in r["filas"])[0])      # con nombre y en orden

    def test_cada_cifra_dice_lo_que_significa(self):
        c = self.clase_cerrada([(5, 5), (2, 5), None])
        r = self.reporte_de_clase(c["sesion"]["id"])
        por = {f["alumno_id"]: f for f in r["filas"]}
        bien, mas_o_menos, sin = (por[a[0]] for a in c["alumnos"])
        self.assertEqual((bien["actividades_recibidas"], bien["actividades_entregadas"], bien["aciertos"], bien["calificadas"], bien["porcentaje_aciertos"]), (1, 1, 5, 5, 100))
        # los aciertos son los PUNTOS que valían las respuestas, no el número de respuestas: dos correctas que valían 1 punto cada una, de nueve que valían las cinco (2 / 9)
        self.assertEqual((mas_o_menos["aciertos"], mas_o_menos["calificadas"], mas_o_menos["porcentaje_aciertos"]), (2, 5, 22.22))
        # quien no entregó NO tiene 0 % de aciertos: no tiene cifra (una actividad sin entregar no es un cero)
        self.assertEqual((sin["actividades_recibidas"], sin["actividades_entregadas"], sin["porcentaje_participacion"], sin["porcentaje_aciertos"]), (1, 0, 0, None))
        self.assertEqual(r["totales"]["promedio_aciertos"], 61.11)                # (100 + 22,22) / 2: el que no entregó no cuenta
        self.assertAlmostEqual(r["totales"]["promedio_participacion"], 66.67, places=2)

    def test_una_clase_sin_actividades_no_tiene_participacion_ni_aciertos(self):
        (a, alias), = [self.alumno_nuevo()]
        s = self.clase()
        self.unir(s, a, alias)
        self.cerrar_clase(s["id"])
        r = self.reporte_de_clase(s["id"])
        self.assertEqual(len(r["filas"]), 1)
        self.assertEqual((r["filas"][0]["porcentaje_participacion"], r["filas"][0]["porcentaje_aciertos"]), (None, None))
        self.assertEqual((r["totales"]["promedio_participacion"], r["totales"]["promedio_aciertos"]), (None, None))

    def test_una_clase_abierta_todavia_no_tiene_reporte(self):
        c = self.clase_cerrada([(5, 5)], cerrar=False)
        r = self.docente.get(f"/api/reportes/clases/{c['sesion']['id']}/")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "clase_en_curso")
        self.assertEqual(self.rp("/clases/")["clases"], [])           # tampoco aparece en el listado

    def test_una_clase_que_no_existe_es_404(self):
        self.reporte_de_clase("no-existe", esperado=404)

    def test_el_reporte_declara_su_corte_y_el_estado_de_integracion(self):
        """BR-083: en pantalla, el instante de corte y el estado de los equipos."""
        c = self.clase_cerrada([(5, 5), (4, 5)])
        r = self.reporte_de_clase(c["sesion"]["id"])
        corte = r["corte"]
        self.assertEqual(corte["en"], self.t)
        self.assertEqual((corte["estado"], corte["antiguedad_ms"], corte["incompleto"]), ("al_dia", 0, False))
        self.assertEqual((corte["integracion"]["estado"], corte["integracion"]["sin_sincronizar"], corte["integracion"]["equipos"]), ("completa", 0, 2))
        self.assertTrue(corte["texto"].startswith("Datos al "))
        self.assertIn("Esto es lo que había en el nodo a esa hora", corte["explicacion"])
        self.assertEqual(r["objetivos"]["disponible"], False)         # el dominio por objetivo aún no existe: no es un cero

    def test_los_rotulos_del_aula_se_piden_al_mostrar_y_no_se_guardan(self):
        c = self.clase_cerrada([(5, 5)])
        r = self.reporte_de_clase(c["sesion"]["id"])
        self.assertEqual(r["clase"]["curso_rotulo"], "Estados de la materia y sus cambios")
        self.assertEqual(r["clase"]["leccion_rotulo"], "Los tres estados de la materia")
        self.assertEqual((r["clase"]["grupo"]["codigo"], r["clase"]["grupo"]["periodo"]), ("8A", "2026"))


class PermisosDeLaClaseTests(BaseReporting):
    def setUp(self):
        super().setUp()
        self.c = self.clase_cerrada([(5, 5), (3, 5)])
        self.sid = self.c["sesion"]["id"]

    def test_el_profesor_ve_las_clases_de_su_grupo(self):
        self.assertEqual(len(self.reporte_de_clase(self.sid)["filas"]), 2)

    def test_otro_profesor_no_ve_la_clase_de_un_grupo_ajeno(self):
        _, otro = self.otro_docente()
        r = self.reporte_de_clase(self.sid, cliente=otro, esperado=403)
        self.assertEqual(r["codigo"], "fuera_de_alcance")
        self.assertEqual(self.rp("/clases/", cliente=otro)["clases"], [])           # ni en su listado

    def test_reportes_y_administracion_ven_toda_la_organizacion(self):
        self.assertEqual(len(self.reporte_de_clase(self.sid, cliente=self.reportes())["filas"]), 2)
        self.assertEqual(len(self.reporte_de_clase(self.sid, cliente=self.admin)["filas"]), 2)

    def test_tst_069_el_tecnico_no_lee_datos_academicos_y_queda_asiento(self):
        tecnico = self.tecnico()
        r = self.reporte_de_clase(self.sid, cliente=tecnico, esperado=403)
        self.assertEqual(r["codigo"], "sin_permiso")
        self.rp("/clases/", cliente=tecnico, esperado=403)
        asientos = self.asientos("reporte.acceso_denegado")
        self.assertEqual(len(asientos), 2)
        self.assertEqual(asientos[0].valor_nuevo["permiso_solicitado"], "reports.view")
        self.assertEqual(asientos[0].valor_nuevo["rol"], "TECHNICIAN")

    def test_el_alumno_no_ve_reportes(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.reporte_de_clase(self.sid, cliente=alumno, esperado=403)

    def test_el_profesor_ve_tambien_la_clase_que_abrio_aunque_no_tenga_padron(self):
        a, alias = self.alumno_nuevo()
        s = self.clase(grupo_id=None)
        self.unir(s, a, alias)
        self.cerrar_clase(s["id"])
        self.assertEqual(self.reporte_de_clase(s["id"])["clase"]["grupo"], None)
        _, otro = self.otro_docente()
        self.reporte_de_clase(s["id"], cliente=otro, esperado=403)                 # sin grupo sólo la ve quien la abrió o quien ve toda la organización
        self.reporte_de_clase(s["id"], cliente=self.reportes())

    def test_sin_sesion_se_permite_como_en_el_resto_del_prototipo_y_la_persona_se_declara(self):
        r = self.api.get(f"/api/reportes/clases/{self.sid}/", {"actor": self.docente_id})
        self.assertEqual(r.status_code, 200, r.content)
