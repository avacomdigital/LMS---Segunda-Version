from django.apps import AppConfig


class AuditConfig(AppConfig):
    """MOD-019 · Audit. Bitácora encadenada de sólo inserción (m19_bitacora, m19_bitacora_tramo) y el sistema de
    logs de diagnóstico en archivos de texto (logging_setup.py, middleware.py).

    Dos registros que comparten infraestructura y nunca se mezclan: la bitácora responde «quién hizo qué, sobre
    qué y con qué resultado» y es evidencia; los logs responden «qué falló en el equipo» y se purgan por rotación."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "Audit (MOD-019) · bitácora y logs"
