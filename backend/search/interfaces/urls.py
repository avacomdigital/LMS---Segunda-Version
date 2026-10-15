from django.urls import path

from . import views

urlpatterns = [
    path("", views.BuscarView.as_view(), name="search"),
    path("filters/", views.FiltrosView.as_view(), name="search-filters"),
    path("status/", views.EstadoView.as_view(), name="search-status"),
    path("open/", views.AbrirView.as_view(), name="search-open"),
    path("reindex/", views.ReindexView.as_view(), name="search-reindex"),
    path("sync/", views.SyncView.as_view(), name="search-sync"),
    path("synonyms/", views.SinonimosView.as_view(), name="search-synonyms"),
]
