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

from audit.infraestructura import verificador  # noqa: E402
from cola_medios.infraestructura import programador as programador_medios  # noqa: E402
from classroom_engine.infraestructura import programador  # noqa: E402
from classroom_engine.interfaces.websockets import websocket_urlpatterns  # noqa: E402
from evaluacion.infraestructura import programador as programador_evaluacion  # noqa: E402

from avacom_lms.velocidad import con_velocidad  # noqa: E402

application = ProtocolTypeRouter({
    # `/api/diagnostico/velocidad/…`: puntos de medición de la red (AVACOM-Medir-Red.bat); todo lo demás sigue a Django tal cual.
    "http": con_velocidad(django_asgi_app),
    "websocket": URLRouter(websocket_urlpatterns),
})

programador.iniciar()
# MOD-010: pausa a quien dejó de dar señal, entrega por tiempo o plazo y restaura los exámenes abiertos tras un reinicio del nodo.
programador_evaluacion.iniciar()
# MOD-019: verifica la cadena de la bitácora cada hora (fuera de clase no hay diferencia: verifica por bloques) y rota por tamaño.
verificador.iniciar()
# Cola de medios: hilos que traen los recursos de AVACOM Contenido a la caché del nodo y la mantienen (al arrancar retoman lo que quedó a medias).
try:
    programador_medios.iniciar()
except Exception:   # noqa: BLE001 — la cola de medios es una mejora: si no arranca, el nodo sirve los medios en paso a través como siempre
    import logging
    logging.getLogger("avacom.cola_medios").exception("La cola de medios no arrancó")
