from django.apps import AppConfig


class ClassroomEngineConfig(AppConfig):
    """MOD-007 · Classroom Engine. Sesiones de clase, participantes, foco y distribución.

    No guarda ningún curso: lo lee en vivo (AVACOM Biblioteca o el manifiesto de
    ejemplo) y sólo escribe lo que ocurre en el aula (tablas m07_*)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "classroom_engine"
    verbose_name = "Classroom Engine (MOD-007) · sesión de clase"

    def ready(self) -> None:
        # MOD-015 (Fase 3): la historia de la cola antigua (`m07_evento_salida`) la sirve este módulo detrás de la fachada de la cola única; la cola no lee tablas ajenas (R-09).
        from nodo import servicios as nodo

        from . import servicios

        nodo.registrar_lector_legado(self.name, servicios.eventos_legados)
