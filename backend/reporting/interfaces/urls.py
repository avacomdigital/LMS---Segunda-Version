from django.urls import path

from . import views

urlpatterns = [
    # Leer (sólo lectura sobre lo que ya calcularon los otros módulos)
    path("clases/", views.ClasesView.as_view()),
    path("clases/<str:sesion_id>/", views.ClaseView.as_view()),
    path("grupos/<str:grupo_id>/", views.GrupoView.as_view()),
    path("alumnos/", views.AlumnosView.as_view()),
    path("alumnos/<str:alumno_id>/", views.AlumnoView.as_view()),
    path("uso/", views.UsoView.as_view()),
    path("boletines/", views.BoletinesView.as_view()),
    path("boletines/<str:alumno_id>/", views.BoletinView.as_view()),
    path("filtros/", views.FiltrosView.as_view()),
    path("recientes/", views.RecientesView.as_view()),
    # Reservadas para V1 (responden 501 capacidad_reservada)
    path("comparar/", views.ComparacionView.as_view()),
    path("cobertura/", views.CoberturaView.as_view()),
    # Configuración del nodo, estado de los agregados y su mantenimiento
    path("configuracion/", views.ConfiguracionView.as_view()),
    path("estado/", views.EstadoView.as_view()),
    path("actualizar/", views.ActualizarView.as_view()),
    path("reconstruir/", views.ReconstruirView.as_view()),
    # Exportar a archivo, en dos tiempos
    path("exportaciones/", views.ExportacionesView.as_view()),
    path("exportaciones/alcance/", views.AlcanceView.as_view()),
    path("exportaciones/<str:exportacion_id>/", views.ExportacionView.as_view()),
    path("exportaciones/<str:exportacion_id>/confirmar/", views.ConfirmarView.as_view()),
]
