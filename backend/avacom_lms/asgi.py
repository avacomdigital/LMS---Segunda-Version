"""
ASGI del nodo del aula: HTTP (Django/DRF) y WebSocket (Django Channels) en el mismo proceso.

    daphne avacom_lms.asgi:application        o        python manage.py runserver   (con `daphne` en INSTALLED_APPS)

Las rutas de WebSocket viven en `classroom_engine/interfaces/websockets.py`. El programador del nodo (presencia por
latido, cierre por inactividad, archivado y detección de caída) arranca aquí, con el servidor, y sólo aquí.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "avacom_lms.settings")
django_asgi_app = get_asgi_application()   # antes de importar nada que toque modelos

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from classroom_engine.infraestructura import programador  # noqa: E402
from classroom_engine.interfaces.websockets import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(websocket_urlpatterns),
})

programador.iniciar()
