"""
Arranque del backend de AVACOM OPS Master con Daphne.

Sirve `avacom_lms.asgi:application`: la API REST y el canal en tiempo real del
aula (WebSocket, Django Channels) en el MISMO puerto, 0.0.0.0:8000. Waitress es
WSGI y no atiende WebSocket ni inicia el programador del nodo (presencia por
latido, cierre por inactividad, archivado, deteccion de caida), que arranca al
importar `avacom_lms.asgi`.

Este archivo pertenece al instalador, no al backend: vive en la carpeta Runtime
de la instalacion y no toca nada de la carpeta Backend.

Parada limpia. El servicio de Windows no tiene consola y Daphne no cierra por
senal en Windows; terminar el proceso a la fuerza dejaria conexiones SQLite
abiertas. Por eso el host le deja abierta la entrada estandar y la cierra (o
escribe "detener") para pedir el cierre: al recibirla se detiene Twisted, se
cierran las conexiones de Django y se vuelca el WAL de SQLite al archivo
principal, de modo que el expediente queda consistente en un solo archivo. Si el
host muere, la entrada se cierra igual y este proceso no queda huerfano.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent
RAIZ_INSTALACION = RUNTIME.parent
BACKEND = RAIZ_INSTALACION / "Backend"


def _vigilar_entrada() -> None:
    """Espera "detener" o el cierre de la entrada estandar y detiene el servidor."""
    try:
        while True:
            linea = sys.stdin.readline()
            if linea == "" or linea.strip().lower() == "detener":
                break
    except Exception:  # noqa: BLE001 — sin entrada valida no se vigila; el host mata el proceso si hace falta
        return
    from twisted.internet import reactor

    print("AVACOM OPS Backend: se pidio detener; cerrando...", flush=True)
    reactor.callFromThread(reactor.stop)


def _cerrar_base_de_datos() -> None:
    """Cierra Django y pasa el WAL al archivo principal (SQLite consistente al parar)."""
    try:
        from django.db import connection, connections

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connections.close_all()
        print("AVACOM OPS Backend: expediente cerrado y WAL volcado.", flush=True)
    except Exception as error:  # noqa: BLE001 — la parada no puede fallar por esto
        print(f"AVACOM OPS Backend: no se pudo volcar el WAL: {error}", flush=True)


def main() -> int:
    if not (BACKEND / "manage.py").exists():
        print(f"No se encontro el backend en {BACKEND}", file=sys.stderr)
        return 2

    # El backend se importa como esta instalado, sin copiarlo ni empaquetarlo.
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "avacom_lms.settings")

    host = os.environ.get("AVACOM_OPS_BACKEND_HOST", "0.0.0.0")
    puerto = int(os.environ.get("AVACOM_OPS_BACKEND_PORT", "8000"))

    # daphne.cli instala el reactor asyncio de Twisted al importarse: debe ir
    # antes que cualquier otra cosa que importe twisted.internet.reactor.
    from daphne.cli import CommandLineInterface

    print(
        f"AVACOM OPS Backend escuchando en {host}:{puerto} "
        f"(daphne, HTTP + WebSocket, expediente en "
        f"{os.environ.get('AVACOM_LMS_DB', 'ruta por defecto del backend')})",
        flush=True,
    )
    threading.Thread(target=_vigilar_entrada, name="vigilar-entrada", daemon=True).start()
    try:
        CommandLineInterface().run([
            "-b", host,
            "-p", str(puerto),
            "-v", "1",
            "--server-name", "AVACOM OPS Backend",
            "avacom_lms.asgi:application",
        ])
    finally:
        _cerrar_base_de_datos()
    return 0


if __name__ == "__main__":
    sys.exit(main())
