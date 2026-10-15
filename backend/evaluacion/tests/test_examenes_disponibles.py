"""
El punto de entrada del profesor desde el MENÚ PRINCIPAL de OPS: `GET /api/evaluacion/examenes/disponibles/` lista los exámenes de los cursos instalados
sin estar dentro de una clase (con `mode=class`, el modo del aula, los exámenes de la biblioteca real no aparecen). Cada examen trae cuántas veces se aplicó y
si hay una aplicación abierta; un curso que falla no tumba a los demás; la biblioteca cerrada se dice, no se rompe; y el alumno no entra.
"""
from __future__ import annotations

from unittest import mock

from ..infraestructura import fuentes_examen
from .base import BASE, CURSO, EXAMEN, BaseEvaluacion


class ExamenesDisponiblesTests(BaseEvaluacion):
    def test_lista_el_examen_de_cada_curso_instalado_sin_preguntas_ni_claves(self):
        r = self.ver("/examenes/disponibles/", fuente="ejemplo")
        self.assertEqual((r["disponible"], r["omitidos"]), (True, []))
        curso = next(c for c in r["cursos"] if c["curso_ref"] == CURSO)
        self.assertEqual((curso["titulo"], curso["version"]), ("Estados de la materia y sus cambios", "1.0.0"))
        examen = next(e for e in curso["examenes"] if e["objeto_ref"] == EXAMEN)
        self.assertEqual((examen["titulo"], examen["leccion_ref"], examen["preguntas"], examen["aplicaciones"], examen["abiertas"]),
                         ("Examen de estados de la materia", "l3-assessment", 12, 0, 0))
        texto = str(r).lower()
        for prohibido in ("iscorrect", "prompt", "correctorder", "acceptedanswers"):
            self.assertNotIn(prohibido, texto)

    def test_dice_cuantas_veces_se_aplico_y_si_hay_una_abierta(self):
        a = self.crear_asignacion("abierto")
        examen = self._examen(self.ver("/examenes/disponibles/", fuente="ejemplo"))
        self.assertEqual((examen["aplicaciones"], examen["abiertas"]), (1, 1))
        self.accion(f"/asignaciones/{a['id']}/cerrar/", {"motivo": "Terminó la clase"})
        examen = self._examen(self.ver("/examenes/disponibles/", fuente="ejemplo"))
        self.assertEqual((examen["aplicaciones"], examen["abiertas"]), (1, 0))

    def test_un_curso_que_falla_no_tumba_a_los_demas_y_queda_en_omitidos(self):
        from classroom_engine.dominio.errores import FuenteNoDisponible
        with mock.patch.object(fuentes_examen, "esquema", side_effect=FuenteNoDisponible("El índice se está reconstruyendo")):
            r = self.ver("/examenes/disponibles/", fuente="ejemplo")
        self.assertEqual(r["cursos"], [])
        self.assertEqual(r["omitidos"][0]["curso_ref"], CURSO)
        self.assertIn("reconstruyendo", r["omitidos"][0]["motivo"])

    def test_con_la_biblioteca_cerrada_se_dice_sin_romper(self):
        cerrada = {"disponible": False, "motivo": "AVACOM Contenido no está abierto.", "sugerencia": "Ábrelo e inténtalo de nuevo.", "cursos_instalados": []}
        with mock.patch("classroom_engine.infraestructura.fuente_ejemplo.FuenteEjemplo.estado", return_value=cerrada):
            r = self.ver("/examenes/disponibles/", fuente="ejemplo")
        self.assertEqual((r["disponible"], r["cursos"], r["motivo"]), (False, [], "AVACOM Contenido no está abierto."))

    def test_un_alumno_no_lista_los_examenes_del_profesor(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = alumno.get(f"{BASE}/examenes/disponibles/", {"fuente": "ejemplo"})
        self.assertEqual(r.status_code, 403, r.content)

    def test_desde_el_examen_elegido_se_aplica_igual_que_desde_la_clase(self):
        examen = self._examen(self.ver("/examenes/disponibles/", fuente="ejemplo"))
        a = self.crear_asignacion("supervisado", objeto_ref=examen["objeto_ref"])         # sin `sesion_id`: no nace en una clase
        self.assertEqual((a["sesion_id"], a["estado"], a["objeto_ref"]), ("", "activa", EXAMEN))
        self.assertEqual(self.abrir(a["id"], esperado=201)["intento"]["estado"], "en_curso")

    @staticmethod
    def _examen(r: dict) -> dict:
        curso = next(c for c in r["cursos"] if c["curso_ref"] == CURSO)
        return next(e for e in curso["examenes"] if e["objeto_ref"] == EXAMEN)
