from django.urls import include, path

from expediente.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("api/acceso/", include("acceso.interfaces.urls")),
    path("api/dispositivos/", include("device_manager.interfaces.urls")),
    path("api/biblioteca/", include("biblioteca.urls")),
    path("api/aula/", include("classroom_engine.interfaces.urls")),
    path("api/modo-estudio/", include("modo_estudio.interfaces.urls")),
    path("api/", include("expediente.urls")),
]
