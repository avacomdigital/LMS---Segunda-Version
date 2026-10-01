"""
El aula completa (TST-004: 25 alumnos; TST-017: 50 tabletas a la vez): todos abren, responden, dan señal y entregan sin que nadie pierda nada ni se
dupliquen intentos, calificaciones o incidentes, y el panel del profesor se lee con un número de consultas que no crece por alumno al cuadrado.
"""
from __future__ import annotations

import time

from django.db import connection
from django.test.utils import CaptureQueriesContext

from .. import models as m
from .base import SEG, BaseEvaluacion, FuenteQueCalifica, respuesta_correcta


class AulaCompletaTests(BaseEvaluacion):
    def aula(self, cuantos: int) -> list[tuple[str, str, str]]:
        """Juan más `cuantos - 1` alumnos, cada uno con su tableta: [(alumno_id, hw, alias)]."""
        gente = [(self.estudiante_id, self.hw_juan, "Juan")]
        for n in range(1, cuantos):
            alumno_id, hw = self.alumno_con_tableta(f"Alumno{n:02d}", f"C-{n:04d}", "supervisado")
            gente.append((alumno_id, hw, f"Alumno{n:02d}"))
        return gente

    def test_tst_004_veinticinco_alumnos_abren_responden_y_entregan_sin_perder_nada(self):
        gente = self.aula(25)
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        empezo = time.perf_counter()
        intentos = {alumno: self.abrir(a["id"], hw=hw, alumno_id=alumno)["intento"]["id"] for alumno, hw, _ in gente}
        self.assertEqual(len(set(intentos.values())), 25)
        self.assertEqual(m.Intento.objects.count(), 25)
        # cada uno tiene SU examen: cuatro preguntas de los dos temas, y no todos el mismo
        armados = {tuple(self.fila(i).armado) for i in intentos.values()}
        self.assertTrue(all(len(self.fila(i).armado) == 4 for i in intentos.values()))
        self.assertGreater(len(armados), 1)
        for alumno, hw, _ in gente:
            i = intentos[alumno]
            tipos = self.fila(i).armado_meta["tipos"]
            cerradas = [r for r in tipos if tipos[r] != "open"]
            self.responder(i, [self.r(ref, n + 1, respuesta_correcta(ref)) for n, ref in enumerate(cerradas)], hw=hw, alumno_id=alumno)
            self.entregar(i, hw=hw, alumno_id=alumno, confirmar=True)
        self.assertLess(time.perf_counter() - empezo, 120.0)
        # una llamada a la biblioteca por intento, nunca una por reactivo (TST-037), y ningún intento perdió una respuesta
        self.assertEqual(len(FuenteQueCalifica.lotes), 25)
        self.assertEqual(FuenteQueCalifica.sueltas, [])
        for i in intentos.values():
            fila = self.fila(i)
            self.assertIn(fila.estado, ("calificado", "en_revision_docente"))
            self.assertEqual(len(fila.respuestas), len([r for r in fila.armado if fila.armado_meta["tipos"][r] != "open"]))
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        totales = panel["totales"]
        self.assertEqual((totales["destinatarios"], totales["sin_intento"], totales["en_curso"], totales["suspendidos"]), (25, 0, 0, 0))
        self.assertEqual(totales["entregados"] + totales["calificados"] + totales["en_revision"], 25)
        self.assertEqual(len(self.eventos("evaluacion.intento_entregado.v1")), 25)
        self.assertEqual(len(self.eventos("evaluacion.intento_abierto.v1")), 25)

    def test_tst_017_cincuenta_tabletas_dan_senal_y_escriben_a_la_vez_y_nadie_se_suspende(self):
        gente = self.aula(50)
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 1800})
        intentos = {alumno: self.abrir(a["id"], hw=hw, alumno_id=alumno)["intento"]["id"] for alumno, hw, _ in gente}
        refs = {alumno: [r for r in self.fila(i).armado if self.fila(i).armado_meta["tipos"][r] != "open"] for alumno, i in intentos.items()}
        # tres minutos de aula: cada 20 s todas las tabletas dan señal y cada una guarda una respuesta
        for vuelta in range(9):
            self.avanzar(seg=20)
            for alumno, hw, _ in gente:
                i = intentos[alumno]
                self.latido(i, hw=hw, alumno_id=alumno)
                if vuelta < len(refs[alumno]):
                    ref = refs[alumno][vuelta]
                    self.responder(i, [self.r(ref, vuelta + 1, respuesta_correcta(ref))], hw=hw, alumno_id=alumno)
        self.assertEqual(m.Intento.objects.filter(estado="en_curso").count(), 50)
        self.assertEqual(m.Incidente.objects.count(), 0)                                   # nadie se desconectó: ni un incidente
        for alumno, i in intentos.items():
            self.assertEqual(len(self.fila(i).respuestas), min(9, len(refs[alumno])))
        reloj = self.estado(intentos[self.estudiante_id])["reloj"]
        self.assertEqual(reloj["restante_ms"], (1800 - 180) * SEG)
        # el panel se lee con las consultas acotadas por alumno (sin N+1 por tablas grandes) y con las 50 filas
        with CaptureQueriesContext(connection) as consultas:
            panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        self.assertEqual(len(panel["filas"]), 50)
        self.assertEqual(panel["totales"]["en_curso"], 50)
        self.assertLess(len(consultas), 50 * 6, f"el panel de 50 alumnos hizo {len(consultas)} consultas")

    def test_inv_012_aperturas_repetidas_de_toda_el_aula_no_duplican_intentos(self):
        gente = self.aula(10)
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        for _ in range(3):
            for alumno, hw, _ in gente:
                self.abrir(a["id"], hw=hw, alumno_id=alumno)
        self.assertEqual(m.Intento.objects.count(), 10)
        self.assertEqual(len(self.eventos("evaluacion.intento_abierto.v1")), 10)
