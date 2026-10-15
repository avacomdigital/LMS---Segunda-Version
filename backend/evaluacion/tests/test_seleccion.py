"""
RF-001 / RF-002 / RF-003 (selección aleatoria por alumno y configuración del profesor): un banco de 100 preguntas y un examen de 20; cada intento recibe
20 válidas sin repetición; dos alumnos reciben selecciones independientes; el profesor fija cuántas preguntas (y el nodo rechaza más de las que hay en el
banco ANTES de iniciar); la selección se congela al crear el intento y se recupera igual tras reinicios y reconexiones; la versión del banco queda
congelada; las opciones se barajan sólo si la asignación lo pide; y la ficha del examen que el profesor ve antes de asignar.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from contextlib import contextmanager
from unittest import mock

from django.test import override_settings

from .. import models as m
from ..aplicacion import barrido
from ..infraestructura import fuentes_examen
from ..infraestructura.contenedor import servicios
from .base import BASE, CURSO, EXAMEN, BaseEvaluacion, manifiesto, respuesta_correcta

TEMAS = ("t-solidos", "t-liquidos", "t-gases", "t-cambios", "t-mezclas")


def manifiesto_de_cien() -> dict:
    """El curso de ejemplo con el examen `l3-exam` reemplazado por un banco de CIEN preguntas de opción múltiple (clones de `l3-q1` con identificadores
    `l3-c001`…`l3-c100`), cinco temas y tres dificultades; el examen pide 20 al azar cubriendo todos los temas, sin cronómetro, y la biblioteca sugiere
    `after_submit` (para comprobar que la sugerencia NO decide la política de publicación)."""
    datos = manifiesto()
    for leccion in datos["lessons"]:
        for objeto in leccion["objects"]:
            if objeto["type"] != "exam":
                continue
            base = next(q for q in objeto["questions"] if q["type"] == "multiple_choice")
            preguntas = []
            for n in range(1, 101):
                q = copy.deepcopy(base)
                q["id"] = f"l3-c{n:03d}"
                q["prompt"] = f"Pregunta {n}: {base['prompt']}"
                q["topicRef"] = TEMAS[n % len(TEMAS)]
                q["difficulty"] = 1 + n % 3
                q["estimatedSec"] = 30 + 10 * (n % 4)
                preguntas.append(q)
            objeto["questions"] = preguntas
            objeto["settings"] = {"selection": {"strategy": "random_balanced", "questionCount": 20, "difficultyTolerancePct": 25, "timeTolerancePct": 25,
                                                "coverAllTopics": True}, "timeLimit": {"policy": "none"}, "passingScorePct": 60, "showResults": "after_submit",
                                  "allowBackNavigation": True, "shuffleOptions": True}
    return datos


class _ConBancoDeCien(BaseEvaluacion):
    def setUp(self):
        super().setUp()
        contexto = self.banco_de_cien()
        contexto.__enter__()
        self.addCleanup(contexto.__exit__, None, None, None)

    @contextmanager
    def banco_de_cien(self):
        with tempfile.TemporaryDirectory(prefix="avacom-banco-cien-") as carpeta:
            ruta = os.path.join(carpeta, "example-cien.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(manifiesto_de_cien(), f)
            with override_settings(AVACOM_AULA_CURSO_EJEMPLO=ruta):
                yield ruta


class BancoDeCienTests(_ConBancoDeCien):
    def test_un_banco_de_cien_y_un_examen_de_veinte_cada_intento_recibe_veinte_validas_sin_repetir(self):
        a = self.crear_asignacion("abierto")
        self.assertEqual((a["estrategia"], a["preguntas_por_alumno"], a["total_banco"]), ("random_balanced", 20, 100))
        i = self.abrir(a["id"])["intento"]["id"]
        armado = self.fila(i).armado
        self.assertEqual(len(armado), 20)
        self.assertEqual(len(set(armado)), 20)                                               # sin repeticiones dentro del intento
        self.assertTrue(all(ref.startswith("l3-c") for ref in armado))                      # sólo preguntas del banco de ESTE curso
        vistas = self.preguntas(i)["preguntas"]
        self.assertEqual([p["pregunta_ref"] for p in vistas], armado)                        # en el orden del alumno
        self.assertEqual(self.fila(i).armado_meta["estrategia"], "random_balanced")

    def test_cubre_todos_los_temas_cuando_el_examen_lo_pide(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        temas = {int(ref[-3:]) % len(TEMAS) for ref in self.fila(i).armado}                  # el tema de un clon es `n % 5`
        self.assertEqual(temas, set(range(len(TEMAS))))

    def test_dos_alumnos_reciben_selecciones_aleatorias_independientes(self):
        a = self.crear_asignacion("abierto")
        i_juan = self.abrir(a["id"])["intento"]["id"]
        ana, hw = self.alumno_con_tableta("Ana", "A-100", "abierto")
        i_ana = self.abrir(a["id"], hw=hw, alumno_id=ana)["intento"]["id"]
        de_juan, de_ana = self.fila(i_juan).armado, self.fila(i_ana).armado
        self.assertEqual((len(de_juan), len(de_ana)), (20, 20))
        self.assertNotEqual(de_juan, de_ana)                                                  # ni el mismo conjunto ni el mismo orden
        self.assertNotEqual(set(de_juan), set(de_ana))

    def test_el_profesor_fija_cuantas_preguntas_recibe_cada_alumno(self):
        a = self.crear_asignacion("abierto", preguntas=15)
        self.assertEqual((a["estrategia"], a["preguntas_por_alumno"], a["total_banco"], a["ajustes"]["cantidad_preguntas"]), ("random_balanced", 15, 100, 15))
        i = self.abrir(a["id"])["intento"]["id"]
        self.assertEqual(len(set(self.fila(i).armado)), 15)

    def test_pedir_mas_preguntas_que_el_banco_se_rechaza_antes_de_iniciar_y_no_se_crea_nada(self):
        r = self.crear_asignacion("abierto", esperado=400, preguntas=101)
        self.assertEqual((r["codigo"], r["codigo_detalle"], r["total_banco"]), ("datos_invalidos", "banco_insuficiente", 100))
        self.assertEqual(m.Asignacion.objects.count(), 0)
        self.assertEqual(self.crear_asignacion("abierto", esperado=400, preguntas=0)["codigo"], "datos_invalidos")

    def test_pedir_todas_las_preguntas_del_banco_las_da_en_orden_aleatorio_por_alumno(self):
        a = self.crear_asignacion("abierto", preguntas=100)
        self.assertEqual((a["estrategia"], a["preguntas_por_alumno"]), ("random_balanced", 100))
        i = self.abrir(a["id"])["intento"]["id"]
        self.assertEqual(len(set(self.fila(i).armado)), 100)

    def test_el_profesor_puede_pedir_el_banco_fijo_en_su_orden(self):
        a = self.crear_asignacion("abierto", estrategia="fixed")
        self.assertEqual((a["estrategia"], a["preguntas_por_alumno"]), ("fixed", 100))
        i = self.abrir(a["id"])["intento"]["id"]
        self.assertEqual(self.fila(i).armado, [f"l3-c{n:03d}" for n in range(1, 101)])

    def test_una_estrategia_desconocida_se_rechaza(self):
        self.assertEqual(self.crear_asignacion("abierto", esperado=400, estrategia="al_azar")["codigo"], "datos_invalidos")


class SeleccionCongeladaTests(_ConBancoDeCien):
    """RF-002 (regla crítica): la selección se hace UNA vez al crear el intento; reconectar, reabrir la pantalla, reiniciar la app o el nodo devuelve
    exactamente el mismo examen y lo ya respondido."""

    def test_reabrir_tras_reiniciar_la_aplicacion_recupera_las_mismas_preguntas_y_respuestas(self):
        a = self.crear_asignacion("abierto", reactivacion="automatica")
        apertura = self.abrir(a["id"], esperado=201)
        i = apertura["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0])), self.r(refs[1], 2, respuesta_correcta(refs[1]))])
        self.avanzar(seg=90)                                                                  # la app se cerró: sin señal, el nodo la pausa
        reabierta = self.abrir(a["id"], esperado=200)                                         # volver a pulsar «Comenzar» no crea otro intento
        self.assertEqual((reabierta["intento"]["id"], reabierta["reanudado"]), (i, True))
        self.latido(i)                                                                        # con reactivación automática sigue solo
        de_nuevo = self.preguntas(i)
        self.assertEqual([p["pregunta_ref"] for p in de_nuevo["preguntas"]], refs)
        self.assertEqual(set(de_nuevo["respondidas"]), {refs[0], refs[1]})
        self.assertEqual(m.Intento.objects.filter(asignacion_id=a["id"]).count(), 1)

    def test_el_nodo_se_reinicia_durante_el_examen_y_el_intento_se_recupera_sin_duplicarse(self):
        a = self.crear_asignacion("abierto", reactivacion="automatica")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]))])
        barrido.RecuperarTrasReinicio(servicios()).ejecutar()                                 # el nodo arranca de nuevo
        self.assertEqual(self.fila(i).estado, "restaurando")
        self.avanzar(seg=5)
        self.latido(i)                                                                        # la tableta vuelve a dar señal
        self.assertEqual(self.fila(i).estado, "en_curso")
        self.assertEqual(self.fila(i).armado, refs)
        self.assertEqual(set(self.preguntas(i)["respondidas"]), {refs[0]})
        self.assertEqual(self.abrir(a["id"], esperado=200)["intento"]["id"], i)
        self.assertEqual(m.Intento.objects.filter(asignacion_id=a["id"]).count(), 1)

    def test_si_cambia_la_version_del_banco_el_intento_abierto_conserva_la_suya_congelada(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]))])
        original_pool, original_preguntas = fuentes_examen.examen_pool, fuentes_examen.examen_preguntas

        def pool_nuevo(origen, curso_ref, objeto_ref):
            return {**original_pool(origen, curso_ref, objeto_ref), "version": "2.0.0"}

        def preguntas_nuevas(origen, curso_ref, objeto_ref, ids, semilla=None):
            return {**original_preguntas(origen, curso_ref, objeto_ref, ids, semilla), "version": "2.0.0"}

        with mock.patch.object(fuentes_examen, "examen_pool", pool_nuevo), mock.patch.object(fuentes_examen, "examen_preguntas", preguntas_nuevas):
            self.assertEqual((self.fila(i).curso_version, self.fila(i).armado), ("1.0.0", refs))          # lo congelado no cambia
            r = self.api.get(f"{BASE}/intentos/{i}/preguntas/", self.alumno())
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "version_no_disponible"))         # el nodo no mezcla versiones
            ana, hw = self.alumno_con_tableta("Ana", "A-100", "abierto")
            r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(hw, ana), format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "version_no_disponible"))         # ni abre intentos con otra versión
        self.assertEqual(self.fila(i).curso_version, "1.0.0")
        self.assertEqual([p["pregunta_ref"] for p in self.preguntas(i)["preguntas"]], refs)             # con la versión de vuelta, el mismo examen


class OpcionesTests(BaseEvaluacion):
    """RF-002.5/6: las opciones se barajan por alumno (reproducible, siempre igual para él) sólo si la asignación lo pide; la asociación con la clave la
    guarda la biblioteca, no el nodo."""

    def _opciones(self, intento_id: str) -> dict[str, list[str]]:
        """Las opciones de las preguntas de opción múltiple, en el orden en que las ve el alumno (verdadero/falso no se baraja)."""
        return {p["pregunta_ref"]: [o["opcion_ref"] for o in p["opciones"]] for p in self.preguntas(intento_id)["preguntas"]
                if p.get("opciones") and p.get("tipo") == "multiple_choice"}

    def test_barajadas_de_forma_reproducible_para_el_alumno(self):
        a = self.crear_asignacion("abierto", estrategia="fixed")
        self.assertTrue(a["mezclar_opciones"])
        i = self.abrir(a["id"])["intento"]["id"]
        primera, segunda = self._opciones(i), self._opciones(i)
        self.assertEqual(primera, segunda)                                                    # el mismo examen cada vez que lo pide
        self.assertTrue(primera)

    def test_sin_mezclar_las_opciones_llegan_en_el_orden_del_banco(self):
        a = self.crear_asignacion("abierto", estrategia="fixed", mezclar_opciones=False)
        self.assertFalse(a["mezclar_opciones"])
        i = self.abrir(a["id"])["intento"]["id"]
        from .base import pregunta_cruda
        for ref, ids in self._opciones(i).items():
            self.assertEqual(ids, [o["id"] for o in pregunta_cruda(ref)["options"]])

    def test_las_preguntas_nunca_llevan_la_clave_aunque_no_se_barajen(self):
        a = self.crear_asignacion("abierto", estrategia="fixed", mezclar_opciones=False)
        i = self.abrir(a["id"])["intento"]["id"]
        texto = json.dumps(self.preguntas(i)).lower()
        for clave in ("iscorrect", "correctorder", "acceptedanswers", "\"answer\"", "rightid"):
            self.assertNotIn(clave, texto)


class FichaDelExamenTests(_ConBancoDeCien):
    def test_la_ficha_dice_cuantas_preguntas_hay_y_que_sugiere_la_biblioteca_sin_traer_preguntas(self):
        ficha = self.ver("/examenes/", fuente="ejemplo", curso_ref=CURSO, objeto_ref=EXAMEN)
        self.assertEqual((ficha["total_banco"], ficha["estrategia"], ficha["preguntas_sugeridas"], ficha["cubrir_todos_los_temas"]), (100, "random_balanced", 20, True))
        self.assertEqual(sorted(ficha["temas"]), sorted(TEMAS))
        self.assertEqual(ficha["tipos"], {"multiple_choice": 100})
        self.assertEqual((ficha["resultados_sugeridos"], ficha["resultados_por_defecto"]), ("al_entregar", "tras_liberar"))
        self.assertEqual(ficha["curso_version"], "1.0.0")
        self.assertNotIn("preguntas", {k for k in ficha if k not in ("preguntas_sugeridas",)})
        self.assertNotIn("iscorrect", json.dumps(ficha).lower())

    def test_la_ficha_exige_curso_y_examen_y_no_revela_lo_que_no_existe(self):
        self.assertEqual(self.ver("/examenes/", esperado=400, fuente="ejemplo")["codigo"], "datos_invalidos")
        self.assertEqual(self.ver("/examenes/", esperado=404, fuente="ejemplo", curso_ref=CURSO, objeto_ref="no-existe")["codigo"], "no_encontrado")
