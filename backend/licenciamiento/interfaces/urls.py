from django.urls import path

from . import views

urlpatterns = [
    # Consultar (CAP-112)
    path("estado/", views.EstadoView.as_view()),
    path("consumo/", views.ConsumoView.as_view()),
    path("capacidades/", views.CapacidadesView.as_view()),
    path("copia/", views.CopiaView.as_view()),                 # CAP-111: extensión (no está en P-17)
    # Activar, renovar y liberar sin internet, mediante archivo (FUN-188, FUN-191, JRN-020)
    path("solicitud/", views.SolicitudView.as_view()),
    path("activar/", views.ActivarView.as_view()),
    path("renovar/", views.RenovarView.as_view()),
    path("liberar/", views.LiberarView.as_view()),
    # Extensión: confirmar la fecha tras un salto sospechoso del reloj (P-06)
    path("reloj/confirmar/", views.ConfirmarRelojView.as_view()),
    # Fase 5 · identidad de dispositivo (P-24): públicas, como el latido; el equipo se identifica antes de tener sesión y al abrirla
    path("identidad/reto/", views.IdentidadRetoView.as_view()),
    path("identidad/enrolar/", views.IdentidadEnrolarView.as_view()),
]
