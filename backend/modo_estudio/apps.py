from django.apps import AppConfig


class ModoEstudioConfig(AppConfig):
    """MOD-008 · Modo Estudio. El producto cuando no hay profesor delante: sirve al alumno el contenido asignado, le deja practicar
    con retroalimentación inmediata, guarda lo que hace y lo entrega cuando el aparato vuelve a estar en la red del aula.

    No guarda ningún curso ni ninguna clave de respuesta: lee la lección en vivo (AVACOM Biblioteca o el manifiesto de ejemplo, por
    los casos de uso del aula) y sólo escribe referencias, rótulos de evidencia y lo que el alumno hace (tablas m08_*)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "modo_estudio"
    verbose_name = "Modo Estudio (MOD-008)"

    def ready(self) -> None:
        # MOD-015 (Fase 3): la historia de la cola antigua (`m08_evento_salida`) la sirve este módulo detrás de la fachada de la cola única; la cola no lee tablas ajenas (R-09).
        from nodo import servicios as nodo

        from . import servicios

        nodo.registrar_lector_legado(self.name, servicios.eventos_legados)
