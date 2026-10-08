"""
Los hilos de la cola: lo que baja los recursos y lo que mantiene la caché, sin que nadie pulse nada. Los arranca `avacom_lms/asgi.py` junto con el servidor
(igual que el programador del aula) y no corren en las pruebas ni en los comandos de gestión.

    N hilos de descarga     (`AVACOM_COLA_DESCARGAS`) toman la tarea más urgente y la traen; uno de ellos está reservado para lo urgente (proyección,
                            examen, clase) para que unos paquetes de estudio de cientos de megas no retrasen lo que el profesor acaba de proyectar.
    un hilo de mantenimiento  cada 30 s anota usos, quita archivos sueltos, respeta el tope de la caché; al arrancar rehace la cola con lo que quedó a medias.

Un fallo en un tick o en una descarga se registra y el siguiente lo vuelve a intentar: el nodo no se cae por esto.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connections

from audit import contexto

from .contenedor import servidor

log = logging.getLogger("avacom.cola_medios")

MANTENIMIENTO_CADA_SEG = 30.0


class _Hilo(threading.Thread):
    def __init__(self, nombre: str):
        super().__init__(name=nombre, daemon=True)
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()


class HiloDeDescargas(_Hilo):
    def __init__(self, indice: int, urgente_solo: bool):
        super().__init__(f"cola-medios-descarga-{indice}")
        self.urgente_solo = urgente_solo

    def run(self) -> None:
        srv = servidor()
        while not self._detener.is_set():
            try:
                tarea = srv.planificador.siguiente(urgente_solo=self.urgente_solo, segundos=1.0)
            except Exception:   # noqa: BLE001
                log.exception("El planificador de medios falló")
                continue
            if tarea is None:
                continue
            token = contexto.establecer(corr=contexto.nuevo_corr(), origen=contexto.ORIGEN_SISTEMA)
            try:
                srv.descargador.ejecutar(tarea)
            except Exception:   # noqa: BLE001 — `ejecutar` no debería lanzar; si lo hace, la tarea no puede quedar colgada
                log.exception("La descarga de un medio terminó con un error inesperado", extra={"evento": "medios.cola.hilo_error"})
                tarea.terminar("fallido", codigo="interno")
                srv.planificador.terminar(tarea)
            finally:
                contexto.restaurar(token)
                close_old_connections()
        connections.close_all()


class HiloDeMantenimiento(_Hilo):
    def __init__(self):
        super().__init__("cola-medios-mantenimiento")

    def run(self) -> None:
        srv = servidor()
        token = contexto.establecer(corr=contexto.nuevo_corr(), origen=contexto.ORIGEN_SISTEMA)
        try:
            n = srv.rehidratar()
            if n:
                log.info("La cola de medios retomó %s recursos que habían quedado a medias", n, extra={"evento": "medios.cola.rehidratada"})
        except Exception:   # noqa: BLE001
            log.exception("No se pudo rehacer la cola de medios al arrancar")
        finally:
            contexto.restaurar(token)
            close_old_connections()
        while not self._detener.wait(MANTENIMIENTO_CADA_SEG):
            token = contexto.establecer(corr=contexto.nuevo_corr(), origen=contexto.ORIGEN_SISTEMA)
            try:
                resultado = srv.mantenimiento()
                if any(resultado.values()):
                    log.info("Mantenimiento de la cola de medios: %s", resultado, extra={"evento": "medios.cola.mantenimiento", "detalle": resultado})
            except Exception:   # noqa: BLE001
                log.exception("El mantenimiento de la cola de medios falló")
            finally:
                contexto.restaurar(token)
                close_old_connections()
        connections.close_all()


_hilos: list[_Hilo] = []
_candado = threading.Lock()


def iniciar() -> list[_Hilo]:
    """Arranca los hilos una sola vez por proceso. `AVACOM_COLA_ACTIVA=0` o `AVACOM_COLA_DESCARGAS=0` los desactiva."""
    try:
        srv = servidor()
    except Exception:   # noqa: BLE001 — la cola nunca tumba el arranque del nodo: sin ella los medios van en paso a través, como siempre
        log.exception("No se pudo construir la cola de medios; el nodo arranca sin ella", extra={"evento": "medios.cola.no_arranco"})
        return []
    if not srv.cfg.activa or srv.cfg.hilos <= 0:
        return []
    with _candado:
        if any(h.is_alive() for h in _hilos):
            return _hilos
        _hilos.clear()
        _hilos.append(HiloDeMantenimiento())
        for i in range(srv.cfg.hilos):
            _hilos.append(HiloDeDescargas(i, urgente_solo=(i == 0 and srv.cfg.hilos > 1)))
        for h in _hilos:
            h.start()
        return _hilos


def detener() -> None:
    srv = servidor()
    srv.planificador.cerrar()
    for h in list(_hilos):
        h.detener()
