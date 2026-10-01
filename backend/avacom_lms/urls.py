from django.urls import include, path

from expediente.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("api/acceso/", include("acceso.interfaces.urls")),
    path("api/dispositivos/", include("device_manager.interfaces.urls")),
    path("api/biblioteca/", include("biblioteca.urls")),
    path("api/aula/", include("classroom_engine.interfaces.urls")),
    path("api/modo-estudio/", include("modo_estudio.interfaces.urls")),
    # MOD-010: asignaciones, intentos, respuestas con secuencia, incidentes y nivel de control de los exámenes.
    path("api/evaluacion/", include("evaluacion.interfaces.urls")),
    # MOD-019: bitácora (sólo lectura, audit.read/audit.export) y logs de diagnóstico (diagnostics.read; entrega de OPS/Student).
    path("api/auditoria/", include("audit.interfaces.urls")),
    path("api/logs/", include("audit.interfaces.urls_logs")),
    path("api/", include("expediente.urls")),
]
