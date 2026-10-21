from django.apps import AppConfig


class NodoConfig(AppConfig):
    """MOD-015 · Node Platform y Cola de Salida: la cola única (`m15_evento`), las marcas y los problemas de los consumidores, el corte de cada módulo, las anclas y el estado del nodo."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "nodo"
    verbose_name = "Plataforma del nodo y cola de salida (MOD-015)"
