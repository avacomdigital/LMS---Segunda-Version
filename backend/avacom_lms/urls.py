from django.urls import include, path

from expediente.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("api/acceso/", include("acceso.interfaces.urls")),
    path("api/dispositivos/", include("device_manager.interfaces.urls")),
    path("api/biblioteca/", include("biblioteca.urls")),
    path("api/aula/", include("classroom_engine.interfaces.urls")),
    path("api/modo-estudio/", include("modo_estudio.interfaces.urls")),
    # MOD-010: asignaciones, intentos, respuestas con secuencia, incidentes y nivel de control de los exámenes.
    path("api/evaluacion/", include("evaluacion.interfaces.urls")),
    # MOD-011: libro de calificaciones (escala interna 0–100, revisión docente, ajustes, publicación, escalas y modo por nivel).
    path("api/gradebook/", include("gradebook.interfaces.urls")),
    # MOD-021: búsqueda (índice local FTS5 de evaluaciones, estudios y clases + catálogo de la biblioteca en vivo), filtrada por lo que cada persona puede leer.
    path("api/search/", include("search.interfaces.urls")),
    # MOD-013: reportes de clase, alumno, grupo y uso de equipos (sólo lectura sobre lo de otros módulos) y su exportación a archivo en dos tiempos.
    path("api/reportes/", include("reporting.interfaces.urls")),
    # MOD-018: estado, consumo y módulos de la licencia; solicitud, activación, renovación y liberación sin internet, mediante archivo.
    path("api/licencia/", include("licenciamiento.interfaces.urls")),
    # Cola de medios: estado de los recursos que el nodo trae de AVACOM Contenido y reparte a las tabletas.
    path("api/medios/", include("cola_medios.interfaces.urls")),
    # MOD-015: el estado del nodo, la cola única por consumidor (sin carga útil), los eventos apartados y su reproceso. Rutas NÚCLEO: el modo restringido nunca las rechaza.
    path("api/nodo/", include("nodo.interfaces.urls")),
    # MOD-017: paquetes de actualización (.avupd) encontrados e importados, su verificación, la ventana, la orden de aplicar o revertir al Host y el historial del nodo.
    path("api/actualizacion/", include("actualizacion.interfaces.urls")),
    # MOD-016: respaldos cifrados (.avbak), su calendario, verificación, exportación y restauración. Sólo el personal de AVACOM opera; la administración lee estado y constancias.
    path("api/respaldo/", include("respaldo.interfaces.urls")),
    # MOD-019: bitácora (sólo lectura, audit.read/audit.export) y logs de diagnóstico (diagnostics.read; entrega de OPS/Student).
    path("api/auditoria/", include("audit.interfaces.urls")),
    path("api/logs/", include("audit.interfaces.urls_logs")),
    path("api/", include("expediente.urls")),
]
