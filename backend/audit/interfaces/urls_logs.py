"""Rutas de los logs de diagnóstico: `/api/logs/` (lectura, `diagnostics.read`) y `/api/logs/clientes/` (entrega de OPS/Student)."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.LogsView.as_view(), name="logs"),
    path("clientes/", views.LogsClientesView.as_view(), name="logs-clientes"),
]
