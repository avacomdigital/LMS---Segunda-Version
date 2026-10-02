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
principal, de modo que el expediente queda consistente en un solo archivo.

Si el host MUERE (se cierra a la fuerza, lo mata el sistema al apagar, falla), la
entrada se cierra igual y este proceso se detiene solo. Dos cosas lo hacen fiable:

  * Nada de lo que escribe en pantalla puede impedirlo. Con el host muerto, la
    tuberia de salida esta rota y un `print` lanza OSError; si eso ocurriera ANTES
    de pedir la parada, el proceso se quedaria vivo, huerfano y con el puerto
    ocupado (es justo lo que pasaba). Por eso todo se escribe con `_decir`.
  * Una salida garantizada: si despues de cerrar el expediente el interprete no
    termina (un hilo de fondo que no es demonio), se sale a la fuerza. El
    expediente ya esta cerrado y volcado: no hay nada que perder.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent
RAIZ_INSTALACION = RUNTIME.parent
BACKEND = RAIZ_INSTALACION / "Backend"

# Segundos que se le dan al interprete para terminar solo despues de cerrar el expediente.
SALIDA_GARANTIZADA_SEG = 10


def _decir(texto: str, error: bool = False) -> None:
    """Escribe en la salida del servicio sin que un pipe roto (el host murio) pueda tumbar lo que se esta haciendo."""
    try:
        print(texto, file=sys.stderr if error else sys.stdout, flush=True)
    except Exception:  # noqa: BLE001 — sin donde escribir, se sigue: lo importante es poder parar
        pass


def _vigilar_entrada() -> None:
    """Espera "detener" o el cierre de la entrada estandar y detiene el servidor."""
    try:
        while True:
            linea = sys.stdin.readline()
            if linea == "" or linea.strip().lower() == "detener":
                break
    except Exception:  # noqa: BLE001 — la entrada se rompio: es lo mismo que cerrarse, se detiene
        pass
    from twisted.internet import reactor

    _decir("AVACOM OPS Backend: se pidio detener; cerrando...")
    reactor.callFromThread(reactor.stop)


def _cerrar_base_de_datos() -> None:
    """Cierra Django y pasa el WAL al archivo principal (SQLite consistente al parar)."""
    try:
        from django.db import connection, connections

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connections.close_all()
        _decir("AVACOM OPS Backend: expediente cerrado y WAL volcado.")
    except Exception as error:  # noqa: BLE001 — la parada no puede fallar por esto
        _decir(f"AVACOM OPS Backend: no se pudo volcar el WAL: {error}")


def _garantizar_la_salida() -> None:
    """Pasado el plazo, termina el proceso aunque quede un hilo de fondo vivo (el expediente ya esta cerrado)."""

    def salir() -> None:
        _decir("AVACOM OPS Backend: el proceso no terminaba solo; se sale a la fuerza.", error=True)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)

    guardia = threading.Timer(SALIDA_GARANTIZADA_SEG, salir)
    guardia.daemon = True
    guardia.start()


def main() -> int:
    if not (BACKEND / "manage.py").exists():
        _decir(f"No se encontro el backend en {BACKEND}", error=True)
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

    _decir(
        f"AVACOM OPS Backend escuchando en {host}:{puerto} "
        f"(daphne, HTTP + WebSocket, expediente en "
        f"{os.environ.get('AVACOM_LMS_DB', 'ruta por defecto del backend')})"
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
        _garantizar_la_salida()
    return 0


if __name__ == "__main__":
    sys.exit(main())
