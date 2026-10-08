from django.urls import path, re_path

from . import views

urlpatterns = [
    # --- estado y sesión de estudio (FUN-080, FUN-089, FUN-090) ---
    path("estado/", views.EstadoView.as_view(), name="estudio-estado"),
    path("estudiantes/", views.EstudiantesView.as_view(), name="estudio-estudiantes"),
    path("sesion/", views.SesionView.as_view(), name="estudio-sesion"),
    path("sesion/cerrar/", views.SesionCerrarView.as_view(), name="estudio-sesion-cerrar"),
    path("sesion/limpieza/", views.SesionLimpiezaView.as_view(), name="estudio-sesion-limpieza"),
    # --- pendientes y lección del alumno (FUN-081, FUN-082, FUN-087) ---
    path("asignaciones/", views.AsignacionesView.as_view(), name="estudio-asignaciones"),
    path("asignaciones/<str:asignacion_id>/", views.AsignacionView.as_view(), name="estudio-asignacion"),
    path("asignaciones/<str:asignacion_id>/medios/<str:media_ref>/", views.MedioDeAsignacionView.as_view(), name="estudio-medio"),
    # Sin barra final: así nombra una página html del curso a otro medio (`../vid-changes`); la redirección perdería el pase del camino.
    re_path(r"^asignaciones/(?P<asignacion_id>[^/]+)/medios/(?P<media_ref>[^/]+)$", views.MedioDeAsignacionView.as_view(),
            name="estudio-medio-sin-barra"),
    re_path(r"^asignaciones/(?P<asignacion_id>[^/]+)/medios/(?P<media_ref>[^/]+)/(?P<ruta>.+)$", views.MedioDeAsignacionView.as_view(),
            name="estudio-medio-interno"),
    path("lecciones/<str:asignacion_id>/", views.LeccionView.as_view(), name="estudio-leccion"),
    path("lecciones/<str:asignacion_id>/progreso/", views.ProgresoView.as_view(), name="estudio-progreso"),
    path("lecciones/<str:asignacion_id>/completar/", views.CompletarView.as_view(), name="estudio-completar"),
    # --- práctica autocalificable, separada de la evaluación formal (FUN-083, FUN-088) ---
    path("lecciones/<str:asignacion_id>/practica/", views.PracticaView.as_view(), name="estudio-practica"),
    path("practicas/<str:practica_id>/respuestas/", views.PracticaRespuestasView.as_view(), name="estudio-practica-respuestas"),
    path("practicas/<str:practica_id>/terminar/", views.PracticaTerminarView.as_view(), name="estudio-practica-terminar"),
    # --- paquete de estudio (CAP-047, FUN-084, FUN-085) ---
    path("paquetes/", views.PaquetesView.as_view(), name="estudio-paquetes"),
    path("paquetes/<str:paquete_id>/", views.PaqueteView.as_view(), name="estudio-paquete"),
    path("paquetes/<str:paquete_id>/manifiesto/", views.ManifiestoView.as_view(), name="estudio-manifiesto"),
    path("paquetes/<str:paquete_id>/archivos/<str:media_ref>/", views.ArchivoDePaqueteView.as_view(), name="estudio-archivo"),
    path("paquetes/<str:paquete_id>/confirmar/", views.ConfirmarView.as_view(), name="estudio-confirmar"),
    # --- trabajo sin red (CAP-048, FUN-086) ---
    path("sync/", views.SyncView.as_view(), name="estudio-sync"),
    path("sync/status/", views.SyncStatusView.as_view(), name="estudio-sync-status"),
    # --- profesor · OPS (CAP-050, CAP-051) ---
    path("docente/grupos/", views.DocenteGruposView.as_view(), name="estudio-docente-grupos"),
    path("docente/asignaciones/", views.DocenteAsignacionesView.as_view(), name="estudio-docente-asignaciones"),
    path("docente/asignaciones/<str:asignacion_id>/", views.DocenteAsignacionView.as_view(), name="estudio-docente-asignacion"),
    path("docente/asignaciones/<str:asignacion_id>/cerrar/", views.DocenteCerrarView.as_view(), name="estudio-docente-cerrar"),
    path("docente/asignaciones/<str:asignacion_id>/decisiones/", views.DocenteDecisionesView.as_view(), name="estudio-docente-decisiones"),
]
