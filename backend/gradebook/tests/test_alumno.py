"""
Lo que ve el ALUMNO según el modo de su nivel. TST-075: en preescolar (modo simple) sólo hay estados y símbolos, ni un número. TST-080: preescolar y secundaria
conviven en el mismo nodo con configuraciones distintas y sin cruces. El modo simple es el valor por defecto de todo nivel.
"""
from __future__ import annotations

from .. import models as m
from .base import BaseGradebook
from .test_publicacion import numeros


class _ConPreescolar(BaseGradebook):
    """8A es de secundaria (modo calificaciones con la escala 0–100) y P1 es de preescolar, SIN configuración: modo simple por defecto."""

    def setUp(self):
        super().setUp()
        r = self.admin.post("/api/acceso/grupos/", {"codigo": "P1", "nombre": "Párvulos", "periodo": "2026", "nivel_clave": "preescolar"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.grupo_pre = r.json()
        self.admin.post(f"/api/acceso/grupos/{self.grupo_pre['id']}/miembros/", {"usuario_id": self.docente_id, "papel": "DOCENTE"}, format="json")
        self.ana_id, self.hw_ana = self.alumno_con_tableta("Ana", "300001", capacidad="supervisado", grupo_id=self.grupo_pre["id"])

    def examen_de_ana(self, **extra):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, grupo_id=self.grupo_pre["id"], **extra)
        return self.examen_entregado(abiertas=False, asignacion=a, hw=self.hw_ana, alumno_id=self.ana_id)

    def mias_de_ana(self) -> list[dict]:
        return self.leer("/mias/", cliente=self.api, alumno_id=self.ana_id)["items"]


class ModoSimpleTests(_ConPreescolar):
    def test_el_modo_simple_es_el_valor_por_defecto_de_todo_nivel(self):
        cfg = self.leer("/configuracion/")
        por_nivel = {n["nivel_clave"]: n for n in cfg["niveles"]}
        self.assertEqual([n["modo"] for n in cfg["niveles"]], ["calificaciones" if n["nivel_clave"] == "secundaria" else "simple" for n in cfg["niveles"]])
        self.assertTrue(por_nivel["preescolar"]["por_defecto"])
        self.assertTrue(all(n["por_defecto"] for k, n in por_nivel.items() if k != "secundaria"))
        self.assertFalse(por_nivel["secundaria"]["por_defecto"])

    def test_tst_075_preescolar_ve_simbolos_y_no_numeros(self):
        a, i, refs, tipos = self.examen_de_ana()
        self.assertEqual(self.fila(i).estado, "calificado")                      # la puntuación técnica de MOD-010 sigue ahí, sin convertirse en nota
        self.sincronizar()
        self.assertFalse(m.Calificacion.objects.filter(alumno_id=self.ana_id).exists())     # y no hay un registro calificable formal
        item = next(x for x in self.mias_de_ana() if x["asignacion_id"] == a["id"])
        self.assertEqual((item["modo"], item["estado_simple"], item["simbolo"]), ("simple", "completado", "lleno"))
        self.assertEqual(numeros({k: v for k, v in item.items() if k != "asignacion_id"}), [])       # TST-075: ningún número en lo que ve el alumno
        self.assertNotIn("puntaje", str(item))
        self.assertNotIn("porcentaje", str(item))
        self.assertIsNone(item["aciertos"])                                      # y los aciertos esperan a que el profesor libere el resultado
        self.assertIsNone(item["nota"])
        # Cuando el profesor libera ese resultado (RF-004) se ven los símbolos y, desde la decisión del 2026-10-19, también la nota (porcentaje del examen, sin escala).
        self.accion(f"/intentos/{i}/liberar-resultado/", {})
        item = next(x for x in self.mias_de_ana() if x["asignacion_id"] == a["id"])
        simbolos = item["aciertos"]["simbolos"]
        self.assertTrue(simbolos and set(simbolos) <= {"acierto", "fallo"})
        self.assertIsNotNone(item["nota"])
        self.assertEqual((item["nota"]["aciertos"], item["nota"]["preguntas"]), (simbolos.count("acierto"), len(simbolos)))
        # El profesor ve la misma nota en el libro, marcada como publicada.
        fila = next(f for f in self.libro(grupo_id=self.grupo_pre["id"])["alumnos"] if f["alumno_id"] == self.ana_id)
        self.assertEqual(fila["celdas"][a["id"]]["nota_simple"]["porcentaje"], item["nota"]["porcentaje"])
        self.assertTrue(fila["celdas"][a["id"]]["nota_simple"]["publicada"])

    def test_los_tres_estados_de_presentacion(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, grupo_id=self.grupo_pre["id"])
        estado = lambda: next(x for x in self.mias_de_ana() if x["asignacion_id"] == a["id"])       # noqa: E731
        self.assertEqual((estado()["estado_simple"], estado()["simbolo"]), ("no_iniciado", "vacio"))
        apertura = self.abrir(a["id"], hw=self.hw_ana, alumno_id=self.ana_id)
        self.assertEqual((estado()["estado_simple"], estado()["simbolo"]), ("en_progreso", "medio"))
        self.entregar(apertura["intento"]["id"], hw=self.hw_ana, alumno_id=self.ana_id, confirmar=True)
        self.assertEqual((estado()["estado_simple"], estado()["simbolo"]), ("completado", "lleno"))

    def test_tst_080_preescolar_y_secundaria_conviven_sin_cruces(self):
        a_sec, i_sec, _, _ = self.examen_entregado(abiertas=False)
        a_pre, i_pre, _, _ = self.examen_de_ana()
        cal_sec = self.calificacion(i_sec)
        self.gb(f"/calificaciones/{cal_sec['id']}/publicar/", {})
        # Secundaria: modo calificaciones con su escala y su nota publicada.
        libro_sec = self.libro()
        self.assertEqual((libro_sec["modo"], libro_sec["escala"]["codigo"]), ("calificaciones", "gen-0-100"))
        juan = self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]
        self.assertEqual((juan["modo"], juan["estado"]), ("calificaciones", "publicado"))
        # Preescolar: modo simple, sin escala, y ninguna calificación registrada aunque su examen se calificó en MOD-010.
        libro_pre = self.libro(grupo_id=self.grupo_pre["id"])
        self.assertEqual((libro_pre["modo"], libro_pre["escala"]), ("simple", None))
        celda = libro_pre["alumnos"][0]["celdas"][a_pre["id"]]
        self.assertEqual((celda["estado_simple"], celda["estado"], celda["calificacion_id"], celda["presentacion"]), ("completado", "sin_registro", None, None))
        ana = next(x for x in self.mias_de_ana() if x["asignacion_id"] == a_pre["id"])
        self.assertEqual(ana["modo"], "simple")
        self.assertEqual(m.Calificacion.objects.filter(alumno_id=self.ana_id).count(), 0)
        # Con su evaluación abierta, preescolar no cambia de modo; al cerrarla sí, y eso NO toca a secundaria.
        letras = self.adoptar("gen-letras")["id"]
        self.gb("/niveles/preescolar/", {"modo": "calificaciones", "escala_id": letras}, metodo="put", cliente=self.admin, esperado=409)
        self.accion(f"/asignaciones/{a_pre['id']}/cerrar/", {"motivo": "fin"})
        self.gb("/niveles/preescolar/", {"modo": "calificaciones", "escala_id": letras}, metodo="put", cliente=self.admin)
        self.assertEqual(self.libro()["escala"]["codigo"], "gen-0-100")
        self.assertEqual(self.libro(grupo_id=self.grupo_pre["id"])["escala"]["codigo"], "gen-letras")
        self.assertEqual(self.fila_cal(i_sec).estado, "definitiva")                      # lo publicado en secundaria sigue igual


class ConfiguracionPorNivelTests(_ConPreescolar):
    def test_no_se_alterna_el_modo_con_evaluaciones_en_curso_en_ese_nivel(self):
        self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"}, grupo_id=self.grupo_pre["id"])      # abierta en preescolar
        escala = self.adoptar("gen-letras")
        r = self.gb("/niveles/preescolar/", {"modo": "calificaciones", "escala_id": escala["id"]}, metodo="put", cliente=self.admin, esperado=409)
        self.assertEqual((r["codigo"], r["en_curso"]), ("evaluaciones_en_curso", 1))
        # Validar no cambia nada y dice por qué no.
        v = self.gb("/niveles/preescolar/", {"modo": "calificaciones", "escala_id": escala["id"], "validar": True}, metodo="put", cliente=self.admin)
        self.assertEqual((v["permitido"], v["en_curso"], v["de"], v["a"]), (False, 1, "simple", "calificaciones"))
        self.assertEqual(self.leer("/configuracion/")["niveles"][0]["modo"], "simple")
        # En otro nivel sin evaluaciones sí se puede, y aquella no bloquea a este.
        ok = self.gb("/niveles/primaria/", {"modo": "calificaciones", "escala_id": escala["id"]}, metodo="put", cliente=self.admin)
        self.assertTrue(ok["cambiado"])
        # Y cambiar sólo la escala (mismo modo) no es alternar el modo: no se bloquea.
        self.gb("/niveles/secundaria/", {"modo": "calificaciones", "escala_id": self.adoptar("gen-0-5")["id"]}, metodo="put", cliente=self.admin)

    def test_una_plantilla_aplicada_a_un_nivel_que_no_se_sugiere_se_avisa_sin_impedirlo(self):
        """Respetar las diferencias normativas por nivel: en España Primaria y ESO califican con términos (IN…SB) y Bachillerato con 0–10; en preescolar ninguna
        plantilla se sugiere (se usa el modo simple)."""
        terminos, numerica = self.adoptar("es-terminos"), self.adoptar("es-0-10")
        v = self.gb("/niveles/preescolar/", {"modo": "calificaciones", "escala_id": terminos["id"], "validar": True}, metodo="put", cliente=self.admin)
        self.assertTrue(v["permitido"])
        self.assertTrue(any("no se sugiere para el nivel preescolar" in w for w in v["advertencias"]), v["advertencias"])
        ok = self.gb("/niveles/primaria/", {"modo": "calificaciones", "escala_id": terminos["id"], "validar": True}, metodo="put", cliente=self.admin)
        self.assertFalse(any("no se sugiere" in w for w in ok["advertencias"]))
        # La escala de Bachillerato (0–10) no es la de Primaria: se avisa, y se puede aplicar igual.
        otra = self.gb("/niveles/primaria/", {"modo": "calificaciones", "escala_id": numerica["id"], "validar": True}, metodo="put", cliente=self.admin)
        self.assertTrue(otra["permitido"])
        self.assertTrue(any("no se sugiere para el nivel primaria" in w for w in otra["advertencias"]), otra["advertencias"])

    def test_el_modo_calificaciones_exige_una_escala_vigente(self):
        r = self.gb("/niveles/primaria/", {"modo": "calificaciones"}, metodo="put", cliente=self.admin, esperado=400)
        self.assertIn("escala", r["detail"])
        r = self.gb("/niveles/primaria/", {"modo": "calificaciones", "escala_id": "no-existe"}, metodo="put", cliente=self.admin, esperado=409)
        self.assertEqual(r["codigo"], "escala_no_vigente")
        self.gb("/niveles/primaria/", {"modo": "turbo"}, metodo="put", cliente=self.admin, esperado=400)
        self.gb("/niveles/universidad/", {"modo": "simple"}, metodo="put", cliente=self.admin, esperado=400)

    def test_configurar_dos_veces_lo_mismo_es_idempotente_y_cada_cambio_deja_evento_y_asiento(self):
        escala = self.adoptar("gen-letras")
        uno = self.gb("/niveles/primaria/", {"modo": "calificaciones", "escala_id": escala["id"]}, metodo="put", cliente=self.admin)
        dos = self.gb("/niveles/primaria/", {"modo": "calificaciones", "escala_id": escala["id"]}, metodo="put", cliente=self.admin)
        self.assertEqual((uno["cambiado"], dos["cambiado"]), (True, False))
        self.assertEqual(self.eventos_gb("calificacion.modo_cambiado.v1").count("calificacion.modo_cambiado.v1"), 2)      # secundaria (setUp) y primaria
        self.gb("/niveles/primaria/", {"modo": "simple"}, metodo="put", cliente=self.admin)
        self.assertEqual(self.leer("/configuracion/")["niveles"][1]["modo"], "simple")
        self.assertEqual(self.leer("/configuracion/")["niveles"][1]["escala"], None)

    def test_pasar_a_simple_avisa_de_lo_ya_publicado_y_no_borra_nada(self):
        a, i, _, _ = self.examen_entregado(abiertas=False)
        cal = self.calificacion(i)
        self.gb(f"/calificaciones/{cal['id']}/publicar/", {})
        v = self.gb("/niveles/secundaria/", {"modo": "simple", "validar": True}, metodo="put", cliente=self.admin)
        self.assertTrue(v["permitido"] or v["en_curso"])
        self.accion(f"/asignaciones/{a['id']}/cerrar/", {"motivo": "fin"})
        v = self.gb("/niveles/secundaria/", {"modo": "simple", "validar": True}, metodo="put", cliente=self.admin)
        self.assertTrue(any("publicadas" in w for w in v["advertencias"]), v)
        self.gb("/niveles/secundaria/", {"modo": "simple"}, metodo="put", cliente=self.admin)
        self.assertEqual(self.fila_cal(i).estado, "definitiva")                          # no se borra
        item = self.leer("/mias/", cliente=self.api, alumno_id=self.estudiante_id)["items"][0]
        self.assertEqual((item["modo"], numeros({k: v for k, v in item.items() if k != "asignacion_id"})), ("simple", []))     # y el alumno ya no ve la nota
