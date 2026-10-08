from django.apps import AppConfig


class ColaMediosConfig(AppConfig):
    """Cola de medios del nodo. Reparte los bytes de video, audio, imagen, PDF y html que vienen de AVACOM Contenido a las tabletas de la LAN:
    los trae UNA vez, los guarda en una caché de disco con su SHA-256, regula cuántos y a qué ritmo, y los sirve con `Range`.

    Atiende a MOD-007 (aula), MOD-008 (modo estudio) y MOD-010 (evaluación); ninguno de los tres cambia lo que responde, sólo de dónde salen los bytes.
    No guarda cursos ni claves: ver `models.py`."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "cola_medios"
    verbose_name = "Cola de medios"
