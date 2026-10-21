from django.urls import path

from . import views

urlpatterns = [
    # El estado del nodo (FUN-167, PAN-242): servicios, base, disco, reloj y la cola en cifras.
    path("estado/", views.EstadoView.as_view()),
    # La cola por consumidor (CAP-097): pendientes, aplicados, rezagados y estado. Nunca la carga de un evento.
    path("cola/", views.ColaView.as_view()),
    # Los eventos apartados (FUN-163) y su reproceso (FUN-164, `node.queue.replay`, con asiento).
    path("problemas/", views.ProblemasView.as_view()),
    path("problemas/<int:problema_id>/reprocesar/", views.ReprocesarView.as_view()),
    # Reproducir un consumidor desde cero (BR-007, `node.queue.replay`).
    path("consumidores/<str:nombre>/reproducir/", views.ReproducirView.as_view()),
]
