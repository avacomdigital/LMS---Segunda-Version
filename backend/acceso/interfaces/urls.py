from django.urls import path

from . import views

urlpatterns = [
    # sin sesión
    path("configuracion/", views.ConfiguracionView.as_view(), name="acceso-configuracion"),
    path("instalacion/", views.InstalacionView.as_view(), name="acceso-instalacion"),
    # los dispositivos viven en MOD-009: /api/dispositivos/ (app device_manager)
    path("sesiones/", views.SesionesView.as_view(), name="acceso-sesiones"),
    path("autorizaciones-temporales/canjear/", views.CanjeView.as_view(), name="acceso-canjear"),
    # identidad propia
    path("yo/", views.YoView.as_view(), name="acceso-yo"),
    path("yo/credencial/", views.CredencialPropiaView.as_view(), name="acceso-yo-credencial"),
    path("sesiones/actual/", views.SesionActualView.as_view(), name="acceso-sesion-actual"),
    path("sesiones/<str:pk>/", views.SesionView.as_view(), name="acceso-sesion"),
    # usuarios
    path("usuarios/", views.UsuariosView.as_view(), name="acceso-usuarios"),
    path("usuarios/importar/", views.ImportarUsuariosView.as_view(), name="acceso-usuarios-importar"),
    path("usuarios/<str:pk>/", views.UsuarioView.as_view(), name="acceso-usuario"),
    path("usuarios/<str:pk>/vincular/", views.UsuarioVincularView.as_view(), name="acceso-usuario-vincular"),
    path("usuarios/<str:pk>/roles/", views.UsuarioRolesView.as_view(), name="acceso-usuario-roles"),
    path("usuarios/<str:pk>/roles/<str:asignacion_id>/", views.UsuarioRolView.as_view(), name="acceso-usuario-rol-asignacion"),
    path("usuarios/<str:pk>/rol/", views.UsuarioRolesView.as_view(), name="acceso-usuario-rol"),
    path("usuarios/<str:pk>/escaladas/", views.UsuarioEscaladasView.as_view(), name="acceso-usuario-escaladas"),
    path("usuarios/<str:pk>/escaladas/<str:permiso>/", views.UsuarioEscaladaView.as_view(), name="acceso-usuario-escalada"),
    path("usuarios/<str:pk>/sesiones/", views.UsuarioSesionesView.as_view(), name="acceso-usuario-sesiones"),
    path("usuarios/<str:pk>/credencial/restablecer/", views.RestablecerCredencialView.as_view(), name="acceso-restablecer"),
    path("usuarios/<str:pk>/desbloquear/", views.DesbloquearView.as_view(), name="acceso-desbloquear"),
    # acceso temporal a examen
    path("autorizaciones-temporales/", views.AutorizacionesView.as_view(), name="acceso-autorizaciones"),
    path("autorizaciones-temporales/<str:pk>/", views.AutorizacionView.as_view(), name="acceso-autorizacion"),
    # catálogos y configuración
    path("roles/", views.RolesView.as_view(), name="acceso-roles"),
    path("permisos/", views.PermisosView.as_view(), name="acceso-permisos"),
    path("politicas/", views.PoliticasView.as_view(), name="acceso-politicas"),
    path("politicas/<str:perfil>/", views.PoliticaView.as_view(), name="acceso-politica"),
    path("grupos/", views.GruposView.as_view(), name="acceso-grupos"),
    path("grupos/<str:pk>/", views.GrupoView.as_view(), name="acceso-grupo"),
    path("grupos/<str:pk>/miembros/", views.MiembrosView.as_view(), name="acceso-miembros"),
    path("grupos/<str:pk>/miembros/<str:usuario_id>/", views.MiembroView.as_view(), name="acceso-miembro"),
]
