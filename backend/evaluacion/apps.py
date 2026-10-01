from django.apps import AppConfig


class EvaluacionConfig(AppConfig):
    """MOD-010 · Evaluation & Delivery Engine. Asignaciones, intentos, respuestas con secuencia, incidentes y nivel de control.

    No guarda ningún examen: lo lee en vivo (AVACOM Biblioteca o el manifiesto de ejemplo) y sólo escribe lo que el alumno hizo
    con él (tablas m10_*)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "evaluacion"
    verbose_name = "Evaluation & Delivery Engine (MOD-010) · exámenes"
