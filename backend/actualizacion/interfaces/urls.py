from django.urls import path

from . import views

urlpatterns = [
    path("estado/", views.EstadoView.as_view(), name="actualizacion-estado"),
    path("paquetes/", views.PaquetesView.as_view(), name="actualizacion-paquetes"),
    path("paquetes/importar/", views.ImportarView.as_view(), name="actualizacion-importar"),
    path("paquetes/<str:paquete_id>/", views.PaqueteView.as_view(), name="actualizacion-paquete"),
    path("paquetes/<str:paquete_id>/programar/", views.ProgramarView.as_view(), name="actualizacion-programar"),
    path("paquetes/<str:paquete_id>/desprogramar/", views.DesprogramarView.as_view(), name="actualizacion-desprogramar"),
    path("paquetes/<str:paquete_id>/aplicar/", views.AplicarView.as_view(), name="actualizacion-aplicar"),
    path("paquetes/<str:paquete_id>/revertir/", views.RevertirView.as_view(), name="actualizacion-revertir"),
    path("historial/", views.HistorialView.as_view(), name="actualizacion-historial"),
]
