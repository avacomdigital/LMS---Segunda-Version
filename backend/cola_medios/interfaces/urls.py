from django.urls import path

from . import views

urlpatterns = [
    path("cola/", views.EstadoView.as_view(), name="medios-cola"),
    path("cola/recursos/", views.RecursosView.as_view(), name="medios-cola-recursos"),
    path("cola/recursos/<str:recurso_id>/", views.RecursoView.as_view(), name="medios-cola-recurso"),
    path("cola/recursos/<str:recurso_id>/cancelar/", views.CancelarView.as_view(), name="medios-cola-cancelar"),
    path("cola/recursos/<str:recurso_id>/reintentar/", views.ReintentarView.as_view(), name="medios-cola-reintentar"),
    path("cola/limpiar/", views.LimpiarView.as_view(), name="medios-cola-limpiar"),
]
