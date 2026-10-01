"""
Rutas de MOD-019. Prefijo `/api/auditoria/` (reemplaza a la ruta vieja del expediente) y `/api/logs/` (urls_logs.py).
No existe ningún PUT/PATCH/DELETE sobre asientos, tramos ni logs: las vistas responden 405 explícito.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("asientos/", views.AsientosView.as_view(), name="auditoria-asientos"),
    path("asientos/<str:pk>/", views.AsientoView.as_view(), name="auditoria-asiento"),
    path("catalogo/", views.CatalogoView.as_view(), name="auditoria-catalogo"),
    path("tramos/", views.TramosView.as_view(), name="auditoria-tramos"),
    path("verificar/", views.VerificarView.as_view(), name="auditoria-verificar"),
    path("estado/", views.EstadoView.as_view(), name="auditoria-estado"),
    path("tecnico/accesos/", views.TecnicoAccesosView.as_view(), name="auditoria-tecnico-accesos"),
]
