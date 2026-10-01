"""Humo del módulo: crear, abrir, responder y entregar un examen de punta a punta."""
from __future__ import annotations

from classroom_engine.dominio import curso as curso_aula

from .base import BASE, BaseEvaluacion


class HumoTests(BaseEvaluacion):
    def test_el_examen_de_punta_a_punta(self):
        asignacion = self.crear_asignacion("supervisado")
        self.assertEqual((asignacion["estado"], asignacion["nivel_examen"], asignacion["estrategia"], asignacion["preguntas_por_alumno"],
                          asignacion["total_banco"]), ("activa", "supervisado", "random_balanced", 4, 12))
        apertura = self.abrir(asignacion["id"])
        self.assertEqual(apertura["intento"]["estado"], "en_curso")
        examen = self.preguntas(apertura["intento"]["id"])
        self.assertEqual(len(examen["preguntas"]), 4)
        self.assertIsNone(curso_aula.contiene_clave(examen))
        refs = self.responder_todo(apertura["intento"]["id"])
        entrega = self.entregar(apertura["intento"]["id"], confirmar=True)
        self.assertIn(entrega["intento"]["estado"], ("calificado", "en_revision_docente"))
        self.assertEqual(len(refs), 4)
