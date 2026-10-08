from django.urls import path, re_path

from . import views

urlpatterns = [
    # --- el curso, en vivo (sin escribir nada) ---
    path("fuente/", views.FuenteView.as_view(), name="aula-fuente"),
    path("cursos/", views.CursosView.as_view(), name="aula-cursos"),
    path("cursos/<str:curso_ref>/", views.CursoView.as_view(), name="aula-curso"),
    path("cursos/<str:curso_ref>/evaluar/", views.EvaluarView.as_view(), name="aula-evaluar"),
    path("cursos/<str:curso_ref>/lecciones/<str:leccion_ref>/", views.LeccionView.as_view(), name="aula-leccion"),
    path("cursos/<str:curso_ref>/objetos/<str:objeto_ref>/", views.ObjetoView.as_view(), name="aula-objeto"),
    path("cursos/<str:curso_ref>/medios/<str:media_ref>/", views.MedioView.as_view(), name="aula-medio"),
    # Sin barra final: es como una página html del curso nombra a otro medio (`../vid-changes`, `../vid-changes/@captions`). Con la barra,
    # la redirección de CommonMiddleware perdería el pase de medios del camino (`/api/m/<pase>/…`).
    re_path(r"^cursos/(?P<curso_ref>[^/]+)/medios/(?P<media_ref>[^/]+)$", views.MedioView.as_view(), name="aula-medio-sin-barra"),
    re_path(r"^cursos/(?P<curso_ref>[^/]+)/medios/(?P<media_ref>[^/]+)/(?P<ruta>.+)$", views.MedioView.as_view(), name="aula-medio-interno"),
    # --- el endpoint de prueba: el manifiesto de ejemplo («Ciencias naturales») ---
    path("pruebas/cursos/", views.PruebasCursosView.as_view(), name="aula-pruebas-cursos"),
    path("pruebas/curso/", views.PruebasCursoView.as_view(), name="aula-pruebas-curso"),
    # --- el canal en tiempo real: diagnóstico (los sockets viven en `websockets.py`, ruta ws/aula/sesiones/<id>/) ---
    path("tiempo-real/", views.TiempoRealView.as_view(), name="aula-tiempo-real"),
    # --- la sesión de clase (lo único que MOD-007 escribe) ---
    path("sesiones/", views.SesionesView.as_view(), name="aula-sesiones"),
    path("sesiones/unirse/", views.UnirseView.as_view(), name="aula-unirse"),
    path("sesiones/<str:sesion_id>/", views.SesionView.as_view(), name="aula-sesion"),
    path("sesiones/<str:sesion_id>/estado/", views.EstadoTabletaView.as_view(), name="aula-sesion-estado"),
    path("sesiones/<str:sesion_id>/selector/", views.SelectorView.as_view(), name="aula-sesion-selector"),
    path("sesiones/<str:sesion_id>/controles/", views.ControlesView.as_view(), name="aula-sesion-controles"),
    path("sesiones/<str:sesion_id>/distribuciones/", views.DistribucionesView.as_view(), name="aula-sesion-distribuciones"),
    path("sesiones/<str:sesion_id>/distribuciones/<str:distribucion_id>/envios/<str:intento_id>/<str:decision>/",
         views.EnvioDecisionView.as_view(), name="aula-sesion-envio-decision"),
    path("sesiones/<str:sesion_id>/distribuciones/<str:distribucion_id>/<str:accion>/", views.DistribucionAccionView.as_view(),
         name="aula-sesion-distribucion-accion"),
    path("sesiones/<str:sesion_id>/anclaje/", views.AnclajeView.as_view(), name="aula-sesion-anclaje"),
    path("sesiones/<str:sesion_id>/avisos/", views.AvisosView.as_view(), name="aula-sesion-avisos"),
    path("sesiones/<str:sesion_id>/codigo/rotar/", views.CodigoRotarView.as_view(), name="aula-sesion-codigo-rotar"),
    path("sesiones/<str:sesion_id>/participantes/<str:participante_id>/presencia/", views.PresenciaView.as_view(),
         name="aula-sesion-presencia"),
    path("sesiones/<str:sesion_id>/participantes/<str:participante_id>/<str:accion>/", views.ParticipanteAccionView.as_view(),
         name="aula-sesion-participante-accion"),
    re_path(r"^sesiones/(?P<sesion_id>[^/]+)/(?P<accion>suspender|reanudar|cerrar)/$", views.SesionTransicionView.as_view(),
            name="aula-sesion-transicion"),
]
