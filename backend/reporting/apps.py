from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """MOD-013 · Reporting. Vistas por clase, alumno, grupo y equipos sobre lo que otros módulos ya calcularon, recortadas siempre por el alcance de quien consulta; la
    exportación a archivo para entregar sin internet; proyecciones propias reconstruibles desde la cola (tablas m13_*).

    No escribe ningún dato académico: lee de los módulos dueños por su interfaz pública (`<módulo>.servicios`)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reporting"
    verbose_name = "Reporting (MOD-013) · reportes y exportación"
