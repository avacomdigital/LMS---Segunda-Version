from django.urls import path

from . import views

urlpatterns = [
    path("preguntar/", views.PreguntarView.as_view(), name="agente-ia-preguntar"),
    path("hablar/", views.HablarView.as_view(), name="agente-ia-hablar"),
    path("estado/", views.EstadoView.as_view(), name="agente-ia-estado"),
]
