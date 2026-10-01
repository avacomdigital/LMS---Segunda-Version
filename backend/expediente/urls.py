from django.urls import path, re_path

from . import views

urlpatterns = [
    path("inscripciones/", views.InscripcionesView.as_view(), name="inscripciones"),
    path("inscripciones/<int:pk>/", views.InscripcionView.as_view(), name="inscripcion"),
    path("students/<str:persona>/courses/", views.StudentCoursesView.as_view(), name="student-courses"),
    path(
        "students/<str:persona>/courses/<str:curso_ref>/progress/",
        views.StudentCourseProgressView.as_view(),
        name="student-course-progress",
    ),
    path("aperturas/", views.AperturasView.as_view(), name="aperturas"),
    path("aperturas/<int:pk>/cerrar/", views.AperturaCerrarView.as_view(), name="apertura-cerrar"),
    path("intentos/start/", views.IntentoStartView.as_view(), name="intento-start"),
    path("intentos/answer/", views.IntentoAnswerView.as_view(), name="intento-answer"),
    path("intentos/finish/", views.IntentoFinishView.as_view(), name="intento-finish"),
    path("resultados/", views.ResultadosView.as_view(), name="resultados"),
    path("resultados/<int:pk>/", views.ResultadoDetalleView.as_view(), name="resultado-detalle"),
    path("cursos/<str:curso_ref>/consolidado/", views.ConsolidadoView.as_view(), name="consolidado"),
    # /api/auditoria/ vive en MOD-019 (app audit): consulta filtrada por permiso, cursor y asiento por consulta.
    # Rutas de administración retiradas: responden rechazo explicativo, no 404.
    re_path(
        r"^(courses|curriculum-frameworks|course-versions|sections|lessons|lesson-items|"
        r"learning-resources|activities|quiz-questions|quiz-options|course-packages|course-hosts)/.*$",
        views.RechazoAdministracionView.as_view(),
        name="rechazo-administracion",
    ),
]
