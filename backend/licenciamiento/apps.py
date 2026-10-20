from django.apps import AppConfig


class LicenciamientoConfig(AppConfig):
    """MOD-018 · Licensing. Valida sin internet qué puede hacer esta instalación y hasta cuándo: licencia firmada y sellada al hardware del equipo maestro; estados activa, en gracia,
    degradada y reactivada; cupo de equipos y usuarios (sólo al crear); módulos habilitados. NUNCA detiene una clase en curso (tablas m18_*).

    Lo ajeno entra por el `servicios.py` de cada dueño (R-08); lo propio se lee de memoria."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "licenciamiento"
    verbose_name = "Licensing (MOD-018) · licencia, cupo y módulos habilitados"
