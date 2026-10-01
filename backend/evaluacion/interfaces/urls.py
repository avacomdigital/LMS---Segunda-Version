from django.urls import path

from . import views as v

urlpatterns = [
    # ---- el profesor: asignaciones
    path("asignaciones/", v.AsignacionesView.as_view(), name="evaluacion-asignaciones"),
    path("asignaciones/<str:asignacion_id>/", v.AsignacionView.as_view(), name="evaluacion-asignacion"),
    path("asignaciones/<str:asignacion_id>/iniciar/", v.IniciarView.as_view(), name="evaluacion-iniciar"),
    path("asignaciones/<str:asignacion_id>/cerrar/", v.CerrarAsignacionView.as_view(), name="evaluacion-cerrar"),
    path("asignaciones/<str:asignacion_id>/prorrogar/", v.ProrrogarView.as_view(), name="evaluacion-prorrogar"),
    path("asignaciones/<str:asignacion_id>/reabrir/", v.ReabrirView.as_view(), name="evaluacion-reabrir"),
    path("asignaciones/<str:asignacion_id>/plazo/", v.PlazoView.as_view(), name="evaluacion-plazo"),
    path("asignaciones/<str:asignacion_id>/endurecer/", v.EndurecerView.as_view(), name="evaluacion-endurecer"),
    path("asignaciones/<str:asignacion_id>/nivel/", v.NivelView.as_view(), name="evaluacion-nivel"),
    path("asignaciones/<str:asignacion_id>/degradar/", v.DegradarView.as_view(), name="evaluacion-degradar"),
    path("asignaciones/<str:asignacion_id>/liberar-resultados/", v.LiberarResultadosView.as_view(), name="evaluacion-liberar"),
    # ---- el profesor: vigilar y decidir
    path("asignaciones/<str:asignacion_id>/panel/", v.PanelView.as_view(), name="evaluacion-panel"),
    path("asignaciones/<str:asignacion_id>/elegibilidad/", v.ElegibilidadView.as_view(), name="evaluacion-elegibilidad"),
    path("asignaciones/<str:asignacion_id>/resultados/", v.ResultadosView.as_view(), name="evaluacion-resultados"),
    path("asignaciones/<str:asignacion_id>/admisiones/", v.AdmisionesView.as_view(), name="evaluacion-admisiones"),
    path("asignaciones/<str:asignacion_id>/admisiones/<str:admision_id>/decidir/", v.AdmisionDecidirView.as_view(), name="evaluacion-admision-decidir"),
    path("asignaciones/<str:asignacion_id>/reactivar/", v.ReactivarTodosView.as_view(), name="evaluacion-reactivar-todos"),
    # ---- el profesor: sobre un intento
    path("intentos/<str:intento_id>/", v.IntentoView.as_view(), name="evaluacion-intento"),
    path("intentos/<str:intento_id>/revision/", v.RevisionView.as_view(), name="evaluacion-revision"),
    path("intentos/<str:intento_id>/reactivar/", v.ReactivarView.as_view(), name="evaluacion-reactivar"),
    path("intentos/<str:intento_id>/cerrar/", v.CerrarIntentoView.as_view(), name="evaluacion-cerrar-intento"),
    path("intentos/<str:intento_id>/anular/", v.AnularView.as_view(), name="evaluacion-anular"),
    path("intentos/<str:intento_id>/publicar/", v.PublicarView.as_view(), name="evaluacion-publicar"),
    path("intentos/<str:intento_id>/recalificar/", v.RecalificarView.as_view(), name="evaluacion-recalificar"),
    path("intentos/<str:intento_id>/decidir-envio/", v.DecidirEnvioView.as_view(), name="evaluacion-decidir-envio"),
    path("intentos/<str:intento_id>/respuestas/<str:pregunta_ref>/puntuar/", v.PuntuarView.as_view(), name="evaluacion-puntuar"),
    # ---- el alumno: descubrir y abrir
    path("estudiantes/", v.EstudiantesView.as_view(), name="evaluacion-estudiantes"),
    path("mias/", v.MisEvaluacionesView.as_view(), name="evaluacion-mias"),
    path("asignaciones/<str:asignacion_id>/antesala/", v.AntesalaView.as_view(), name="evaluacion-antesala"),
    path("asignaciones/<str:asignacion_id>/intentos/", v.AbrirIntentoView.as_view(), name="evaluacion-abrir"),
    # ---- el alumno: presentar
    path("intentos/<str:intento_id>/estado/", v.EstadoView.as_view(), name="evaluacion-estado"),
    path("intentos/<str:intento_id>/latido/", v.LatidoView.as_view(), name="evaluacion-latido"),
    path("intentos/<str:intento_id>/preguntas/", v.PreguntasView.as_view(), name="evaluacion-preguntas"),
    path("intentos/<str:intento_id>/medios/<str:media_ref>/", v.MedioView.as_view(), name="evaluacion-medio"),
    path("intentos/<str:intento_id>/medios/<str:media_ref>/<path:ruta>", v.MedioView.as_view(), name="evaluacion-medio-ruta"),
    path("intentos/<str:intento_id>/respuestas/", v.RespuestasView.as_view(), name="evaluacion-respuestas"),
    path("intentos/<str:intento_id>/incidentes/", v.IncidentesView.as_view(), name="evaluacion-incidentes"),
    path("intentos/<str:intento_id>/bloqueo/", v.BloqueoView.as_view(), name="evaluacion-bloqueo"),
    path("intentos/<str:intento_id>/entregar/", v.EntregarView.as_view(), name="evaluacion-entregar"),
    path("intentos/<str:intento_id>/resultado/", v.ResultadoView.as_view(), name="evaluacion-resultado"),
    # ---- FUN-103 y FUN-104: son de la biblioteca (artículo 14)
    path("evaluaciones/", v.EvaluacionesRechazadaView.as_view(), name="evaluacion-crear-rechazada"),
    path("reactivos/", v.ReactivosRechazadaView.as_view(), name="evaluacion-reactivo-rechazado"),
]
