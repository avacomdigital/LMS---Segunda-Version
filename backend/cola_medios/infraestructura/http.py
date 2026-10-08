"""
La respuesta HTTP de un recurso de la cola. Bajo el servidor ASGI del nodo el cuerpo es un generador ASÍNCRONO: Django consume los generadores síncronos
enteros en memoria antes de enviar el primer byte (un video de 300 MB con `Range: bytes=0-` se cargaba completo por cada tableta); uno asíncrono sale
por trozos, deja pasar a las demás conexiones y permite regular el ritmo. Bajo WSGI (pruebas, `runserver` sin Daphne) se usa uno síncrono equivalente.

Cada transferencia ocupa un cupo mientras dura (`AVACOM_COLA_TRANSFERENCIAS`). Si no hay cupo espera un máximo y, pasado éste, se envía igual: los
límites dan forma al tráfico, pero nunca hacen que un medio falle.
"""
from __future__ import annotations

import asyncio
import time

from django.core.handlers.asgi import ASGIRequest
from django.http import HttpResponse, StreamingHttpResponse

from ..aplicacion.respuesta import RespuestaLocal
from ..aplicacion.servidor import Servidor, tomar_cupo

TROZO_SALIDA = 256 * 1024
PAUSA_CUPO = 0.05


def _es_asgi(request) -> bool:
    return isinstance(getattr(request, "_request", request), ASGIRequest)


def _con_cabeceras(respuesta, local: RespuestaLocal):
    for clave, valor in local.headers.items():
        if clave != "content-type":
            respuesta[clave] = valor
    return respuesta


def respuesta_http(request, local: RespuestaLocal, metodo: str, servidor: Servidor):
    tipo = local.headers.get("content-type") or "application/octet-stream"
    if metodo == "HEAD" or local.sin_cuerpo or local.status == 416 or local.longitud == 0:
        local.close()
        return _con_cabeceras(HttpResponse(status=local.status, content_type=tipo), local)
    if local.en_una_pieza and local.completa_ahora():
        return _en_una_pieza(local, tipo, servidor)
    if _es_asgi(request):
        respuesta = StreamingHttpResponse(_cuerpo_async(local, servidor), status=local.status, content_type=tipo)
    else:
        respuesta = StreamingHttpResponse(_cuerpo_sync(local, servidor), status=local.status, content_type=tipo)
    respuesta._resource_closers.append(local.close)
    return _con_cabeceras(respuesta, local)


def _en_una_pieza(local: RespuestaLocal, tipo: str, servidor: Servidor):
    """Lo que una fuente entrega ya hecho en memoria (el manifiesto de ejemplo) sale como una respuesta normal, con su cuerpo, igual que antes de la cola
    (el cuerpo está en `respuesta.content`): no necesita flujo ni cupo. La biblioteca de verdad siempre sale por flujo."""
    try:
        cuerpo = local.read(-1)
    finally:
        local.close()
    espera = servidor.salida.reservar(len(cuerpo))
    if espera > 0:
        time.sleep(espera)
    servidor.contar("bytes_servidos", len(cuerpo))
    return _con_cabeceras(HttpResponse(cuerpo, status=local.status, content_type=tipo), local)


async def _cuerpo_async(local: RespuestaLocal, servidor: Servidor):
    cupo = None
    try:
        limite = time.monotonic() + servidor.cfg.espera_cupo_seg
        while cupo is None:
            cupo = tomar_cupo(servidor)
            if cupo is None:
                if time.monotonic() >= limite:
                    servidor.contar("cupo_vencido")
                    break
                await asyncio.sleep(PAUSA_CUPO)
        while True:
            trozo = await local.leer_async(TROZO_SALIDA)
            if not trozo:
                break
            espera = servidor.salida.reservar(len(trozo))
            if espera > 0:
                await asyncio.sleep(espera)
            servidor.contar("bytes_servidos", len(trozo))
            yield trozo
    finally:
        if cupo is not None:
            cupo.liberar()
        local.close()


def _cuerpo_sync(local: RespuestaLocal, servidor: Servidor):
    cupo = None
    try:
        limite = time.monotonic() + servidor.cfg.espera_cupo_seg
        while cupo is None:
            cupo = tomar_cupo(servidor)
            if cupo is None:
                if time.monotonic() >= limite:
                    servidor.contar("cupo_vencido")
                    break
                time.sleep(PAUSA_CUPO)
        while True:
            trozo = local.read(TROZO_SALIDA)
            if not trozo:
                break
            espera = servidor.salida.reservar(len(trozo))
            if espera > 0:
                time.sleep(espera)
            servidor.contar("bytes_servidos", len(trozo))
            yield trozo
    finally:
        if cupo is not None:
            cupo.liberar()
        local.close()
