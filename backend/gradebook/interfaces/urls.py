from django.urls import path

from . import views as v

urlpatterns = [
    # ---- el profesor: leer el libro
    path("libro/", v.LibroView.as_view(), name="gradebook-libro"),
    path("resumen/", v.ResumenView.as_view(), name="gradebook-resumen"),
    path("estudiantes/<str:alumno_id>/", v.EstudianteView.as_view(), name="gradebook-estudiante"),
    path("asignaciones/<str:asignacion_id>/", v.AsignacionView.as_view(), name="gradebook-asignacion"),
    path("asignaciones/<str:asignacion_id>/clasificacion/", v.ClasificacionView.as_view(), name="gradebook-clasificacion"),
    path("asignaciones/<str:asignacion_id>/publicar/", v.PublicarAsignacionView.as_view(), name="gradebook-publicar-asignacion"),
    # ---- el profesor: revisar (FUN-120, FUN-121)
    path("revisiones/", v.BandejaView.as_view(), name="gradebook-revisiones"),
    path("revisiones/<str:intento_id>/", v.RevisionView.as_view(), name="gradebook-revision"),
    path("revisiones/<str:intento_id>/respuestas/<str:pregunta_ref>/", v.AplicarRevisionView.as_view(), name="gradebook-aplicar-revision"),
    path("revisiones/<str:intento_id>/confirmar/", v.ConfirmarRevisionView.as_view(), name="gradebook-confirmar-revision"),
    # ---- el profesor: registrar, ajustar, reabrir, valorar, retroalimentar y publicar (FUN-119, FUN-122, FUN-123)
    path("intentos/<str:intento_id>/registrar/", v.RegistrarView.as_view(), name="gradebook-registrar"),
    path("calificaciones/<str:calificacion_id>/", v.CalificacionView.as_view(), name="gradebook-calificacion"),
    path("calificaciones/<str:calificacion_id>/ajustar/", v.AjustarView.as_view(), name="gradebook-ajustar"),
    path("calificaciones/<str:calificacion_id>/reabrir/", v.ReabrirView.as_view(), name="gradebook-reabrir"),
    path("calificaciones/<str:calificacion_id>/valoracion/", v.ValoracionView.as_view(), name="gradebook-valoracion"),
    path("calificaciones/<str:calificacion_id>/retroalimentacion/", v.RetroalimentacionView.as_view(), name="gradebook-retroalimentacion"),
    path("calificaciones/<str:calificacion_id>/publicar/", v.PublicarView.as_view(), name="gradebook-publicar"),
    path("calificaciones/<str:calificacion_id>/retirar-publicacion/", v.RetirarPublicacionView.as_view(), name="gradebook-retirar-publicacion"),
    # ---- la administración: modo, escalas y política (FUN-124, FUN-125)
    path("configuracion/", v.ConfiguracionView.as_view(), name="gradebook-configuracion"),
    path("niveles/<str:nivel_clave>/", v.NivelView.as_view(), name="gradebook-nivel"),
    path("politica/", v.PoliticaView.as_view(), name="gradebook-politica"),
    path("escalas/plantillas/", v.PlantillasView.as_view(), name="gradebook-plantillas"),
    path("escalas/adoptar/", v.AdoptarView.as_view(), name="gradebook-adoptar"),
    path("escalas/vista-previa/", v.VistaPreviaView.as_view(), name="gradebook-vista-previa"),
    path("escalas/", v.EscalasView.as_view(), name="gradebook-escalas"),
    path("escalas/<str:escala_id>/", v.EscalaView.as_view(), name="gradebook-escala"),
    path("escalas/<str:escala_id>/versiones/", v.VersionesDeEscalaView.as_view(), name="gradebook-escala-versiones"),
    # ---- el nodo: eventos y derivados (FUN-127, FUN-129)
    path("sincronizar/", v.SincronizarView.as_view(), name="gradebook-sincronizar"),
    path("derivados/reconstruir/", v.ReconstruirView.as_view(), name="gradebook-reconstruir"),
    # ---- el alumno
    path("mias/", v.MisResultadosView.as_view(), name="gradebook-mias"),
]
