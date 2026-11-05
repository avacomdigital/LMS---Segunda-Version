from django.apps import AppConfig


class AgenteIaConfig(AppConfig):
    """AI Agent · el asistente de IA de OPS Master. Conecta la pantalla «AI Agent» con AVACOM Local AI (Qwen por Ollama + la voz Piper), que corre en el MISMO equipo.

    No guarda nada: ni tablas, ni preguntas, ni respuestas (la memoria de la conversación vive en el servicio local). Es el único cliente del servicio de IA: la app MAUI habla sólo con este
    backend. Un fallo de la IA se responde con un código y queda en la bitácora y en el log; nunca rompe el aula. Contrato: `docs/contrato-api-ai-lms.md` del proyecto avacom-local-ai."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agente_ia"
    verbose_name = "Agente de IA · AVACOM Local AI"
