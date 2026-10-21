from django.apps import AppConfig


class GradebookConfig(AppConfig):
    """MOD-011 · Gradebook. La calificación normalizada de cada intento (0–100), sus revisiones y ajustes, las escalas versionadas y el modo por nivel.

    No calcula respuestas (eso es de MOD-010), no guarda rúbricas ni evidencias y no administra el progreso del estudiante (MOD-012): consume los
    resultados de la evaluación y es el dueño de la nota (tablas m11_*)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "gradebook"
    verbose_name = "Gradebook (MOD-011) · calificaciones"

    def ready(self) -> None:
        # Como dueño de la NOTA, el libro añade su condición a «el alumno ya puede ver su resultado» de MOD-010 (compuerta de resultado, ver `infraestructura/compuerta.py`).
        from evaluacion import servicios as mod10
        from nodo import servicios as nodo

        from . import servicios
        from .infraestructura import compuerta

        mod10.registrar_compuerta_de_resultado(compuerta.NOMBRE, compuerta.compuerta_de_resultado)
        # MOD-015 (Fase 3): la historia de la cola antigua (`m11_evento_salida`) la sirve este módulo detrás de la fachada de la cola única; la cola no lee tablas ajenas (R-09).
        nodo.registrar_lector_legado(self.name, servicios.eventos_legados)
