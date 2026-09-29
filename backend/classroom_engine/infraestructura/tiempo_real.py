"""
Adaptador del puerto `TiempoReal` sobre Django Channels (007-01).

Cada caso de uso que cambia algo de la sesión avisa aquí; el aviso sale cuando la transacción se CONFIRMA
(`transaction.on_commit`): quien lo recibe ya puede leer el hecho por HTTP. El aviso NUNCA lleva contenido
académico (ni respuestas, ni nombres, ni claves): sólo qué cambió y, para la pantalla del profesor, cuántos
participantes hay conectados. Los clientes reaccionan pidiendo el estado por HTTP, que sigue siendo la única
fuente de verdad y el respaldo cuando el WebSocket se cae.

Cada sesión tiene tres clases de grupo de canales:
    aula.<sesion>.docente        → pantallas del profesor (reciben `cambio` y `conteo`)
    aula.<sesion>.alumnos        → todas las tabletas (reciben `cambio`)
    aula.<sesion>.p.<participante> → una sola tableta (lo que sólo le concierne a ella)

Quién recibe qué (para que 50 tabletas respondiendo no provoquen 2.500 consultas por segundo):
    selector, controles, distribucion, aviso al grupo, sesion   → profesor y todas las tabletas
    presencia, ayuda, proyeccion, aviso individual              → profesor y la tableta afectada
    resultados, entregas, codigo                                → sólo el profesor

Los sockets viven en el bucle de eventos del servidor ASGI; los casos de uso corren en hilos (vistas DRF,
programador del nodo). Por eso el envío se programa en ESE bucle (`run_coroutine_threadsafe`): la capa en
memoria no es segura entre bucles y un aviso publicado desde otro hilo llegaría tarde o no llegaría.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .. import models as m
from ..dominio import sesion as dom

log = logging.getLogger("avacom.aula.tiempo_real")

TIPO_MENSAJE = "aula.mensaje"   # nombre del manejador del consumidor (`aula_mensaje`)


def grupo_docente(sesion_id: str) -> str:
    return f"aula.{sesion_id}.docente"


def grupo_alumnos(sesion_id: str) -> str:
    return f"aula.{sesion_id}.alumnos"


def grupo_participante(sesion_id: str, participante_id: str) -> str:
    return f"aula.{sesion_id}.p.{participante_id}"


# A quién le llega cada clase de cambio. Lo no listado va a todos.
SOLO_DOCENTE = frozenset({"resultados", "entregas", "codigo"})
DOCENTE_Y_PARTICIPANTE = frozenset({"presencia", "ayuda", "proyeccion"})


# ------------------------------------------------------------- el bucle del servidor
_bucle: asyncio.AbstractEventLoop | None = None
_candado = threading.Lock()


def registrar_bucle(bucle: asyncio.AbstractEventLoop) -> None:
    """Lo llama el consumidor al conectarse: es el bucle donde viven los sockets."""
    global _bucle
    with _candado:
        _bucle = bucle


def _enviar_a_grupos(envios: list[tuple[str, dict]]) -> None:
    capa = get_channel_layer()
    if capa is None:
        return

    async def enviar():
        for grupo, mensaje in envios:
            await capa.group_send(grupo, {"type": TIPO_MENSAJE, "mensaje": mensaje})

    with _candado:
        bucle = _bucle
    if bucle is not None and bucle.is_running():
        try:
            asyncio.run_coroutine_threadsafe(enviar(), bucle).result(timeout=5)
            return
        except Exception:   # el aula no cae porque un aviso no salió: el respaldo por HTTP sigue ahí
            log.exception("No se pudo difundir por el bucle del servidor")
            return
    # Sin servidor ASGI en marcha (pruebas síncronas, comandos): nadie escucha; se envía igual por si acaso.
    try:
        async_to_sync(enviar)()
    except Exception:
        log.exception("No se pudo difundir")


def conteo_de(sesion_id: str) -> dict:
    por_estado: dict[str, int] = {}
    for estado in m.Participante.objects.filter(sesion_id=sesion_id).values_list("estado", flat=True):
        por_estado[estado] = por_estado.get(estado, 0) + 1
    return {"total": sum(por_estado.values()), "conectados": por_estado.get(dom.CONECTADO, 0),
            "reconectando": por_estado.get(dom.RECONECTANDO, 0), "esperando": por_estado.get(dom.ESPERANDO, 0),
            "salieron": por_estado.get(dom.SALIO, 0)}


def mensaje_conteo(sesion_id: str, ahora: int | None = None) -> dict:
    return {"tipo": "conteo", "sesion_id": sesion_id, **conteo_de(sesion_id), "emitido_en": ahora or int(time.time() * 1000)}


class TiempoRealCanales:
    """Implementa `aplicacion.puertos.TiempoReal`."""

    def cambio(self, sesion_id: str, que: str, carga: dict | None = None, *, conteo: bool = False) -> None:
        transaction.on_commit(lambda: self._emitir(sesion_id, que, dict(carga or {}), conteo))

    @staticmethod
    def _emitir(sesion_id: str, que: str, carga: dict, conteo: bool) -> None:
        ahora = int(time.time() * 1000)
        cambio = {"tipo": "cambio", "que": que, "sesion_id": sesion_id, "carga": carga, "emitido_en": ahora}
        participante_id = str(carga.get("participante_id") or "")
        envios = [(grupo_docente(sesion_id), cambio)]
        if que in SOLO_DOCENTE:
            pass
        elif que in DOCENTE_Y_PARTICIPANTE or (que == "aviso" and participante_id):
            if participante_id:
                envios.append((grupo_participante(sesion_id, participante_id), cambio))
        else:
            envios.append((grupo_alumnos(sesion_id), cambio))
        if conteo:
            try:
                envios.append((grupo_docente(sesion_id), mensaje_conteo(sesion_id, ahora)))
            except Exception:
                log.exception("No se pudo contar a los participantes")
        _enviar_a_grupos(envios)
