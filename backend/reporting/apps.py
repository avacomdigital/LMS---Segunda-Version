from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """MOD-013 · Reporting. Vistas por clase, alumno, grupo y equipos sobre lo que otros módulos ya calcularon, recortadas siempre por el alcance de quien consulta; la
    exportación a archivo para entregar sin internet; proyecciones propias reconstruibles desde la cola (tablas m13_*).

    No escribe ningún dato académico: lee de los módulos dueños por su interfaz pública (`<módulo>.servicios`)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reporting"
    verbose_name = "Reporting (MOD-013) · reportes y exportación"

    def ready(self) -> None:
        # MOD-015 (Fase 3): la historia de la cola antigua (`m13_evento_salida`) la sirve este módulo detrás de la fachada de la cola única; la cola no lee tablas ajenas (R-09).
        from nodo import servicios as nodo

        from . import servicios

        nodo.registrar_lector_legado(self.name, servicios.eventos_legados)
