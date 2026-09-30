from django.urls import path, re_path

from . import views

urlpatterns = [
    path("", views.DispositivosView.as_view(), name="dispositivos"),
    path("latido/", views.LatidoView.as_view(), name="dispositivos-latido"),
    path("<str:pk>/", views.DispositivoView.as_view(), name="dispositivo"),
    re_path(r"^(?P<pk>[^/]+)/(?P<accion>bloquear|desbloquear|asignar|liberar)/$", views.DispositivoAccionView.as_view(), name="dispositivo-accion"),
]
