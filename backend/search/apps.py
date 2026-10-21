from django.apps import AppConfig


class SearchConfig(AppConfig):
    """MOD-021 · Search. Descubrimiento de lo que el nodo tiene: cursos, lecciones y recursos (que busca AVACOM Biblioteca, su dueña) y las evaluaciones, asignaciones de
    estudio y clases (que son del LMS y se indexan aquí, en un índice local reconstruible).

    No es la fuente de verdad de nada: no guarda cursos (artículo 14), no decide quién puede leer (lo decide MOD-001 con los datos vigentes en cada consulta) y no
    modifica jamás las entidades de los módulos propietarios. Sus tablas son `m21_*` y se pueden vaciar y reconstruir sin perder ningún dato académico."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "search"
    verbose_name = "Search (MOD-021) · búsqueda"

    def ready(self) -> None:
        # MOD-015 (Fase 3): la historia de la cola antigua (`m21_evento_salida`) la sirve este módulo detrás de la fachada de la cola única; la cola no lee tablas ajenas (R-09).
        from nodo import servicios as nodo

        from . import servicios

        nodo.registrar_lector_legado(self.name, servicios.eventos_legados)
