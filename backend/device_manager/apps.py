from django.apps import AppConfig


class DeviceManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "device_manager"
    verbose_name = "Gestión de dispositivos"

    def ready(self) -> None:
        # MOD-015 (Fase 3): la historia de la cola antigua (`m09_evento_salida`) la sirve este módulo detrás de la fachada de la cola única; la cola no lee tablas ajenas (R-09).
        from nodo import servicios as nodo

        from . import servicios

        nodo.registrar_lector_legado(self.name, servicios.eventos_legados)
