from django.urls import path

from . import views

urlpatterns = [
    path("estado/", views.EstadoView.as_view(), name="respaldo-estado"),
    path("respaldos/", views.RespaldosView.as_view(), name="respaldo-respaldos"),
    path("respaldos/ahora/", views.AhoraView.as_view(), name="respaldo-ahora"),
    path("respaldos/<str:respaldo_id>/", views.RespaldoView.as_view(), name="respaldo-respaldo"),
    path("respaldos/<str:respaldo_id>/constancia/", views.ConstanciaView.as_view(), name="respaldo-constancia"),
    path("respaldos/<str:respaldo_id>/verificar/", views.VerificarView.as_view(), name="respaldo-verificar"),
    path("respaldos/<str:respaldo_id>/exportar/", views.ExportarView.as_view(), name="respaldo-exportar"),
    path("resumen/", views.ResumenView.as_view(), name="respaldo-resumen"),
    path("informes/", views.InformesView.as_view(), name="respaldo-informes"),
    path("informes/<str:nombre>/", views.InformeView.as_view(), name="respaldo-informe"),
    path("destinos/", views.DestinosView.as_view(), name="respaldo-destinos"),
    path("programacion/", views.ProgramacionView.as_view(), name="respaldo-programacion"),
    path("custodia/emitir/", views.CustodiaView.as_view(), name="respaldo-custodia"),
    path("restaurar/", views.RestaurarView.as_view(), name="respaldo-restaurar"),
    path("restaurar/modulo/", views.RestaurarModuloView.as_view(), name="respaldo-restaurar-modulo"),
]
