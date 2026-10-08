"""
Puntos de medición de la red del aula, a nivel ASGI: ni Django, ni base de datos, ni sesión. Los usa `AVACOM-Medir-Red.bat` (y quien quiera medir) para saber cuánto
aguanta de verdad el camino laptop/tableta ↔ router ↔ nodo, sin que cuente ningún otro trabajo del nodo.

    GET  /api/diagnostico/velocidad/ping/                       → {"ok": true, "t": <ms del nodo>}                    (latencia de una petición mínima)
    GET  /api/diagnostico/velocidad/estado/                     → mediciones en curso y estadísticas de la caché de pases de medios
    GET  /api/diagnostico/velocidad/descarga/?mb=N               → N MB (1…256) de bytes sin comprimir                   (nodo → cliente)
    POST /api/diagnostico/velocidad/carga/                       → {"bytes": n, "ms": m, "mbps": x}  tras leer todo el cuerpo (cliente → nodo)

Reglas: los bytes no llevan nada del aula (ceros), no hay datos personales; como mucho `MAX_FLUJOS` mediciones a la vez (la siguiente recibe 429 con
`Retry-After`) para que una medición no se coma el aula; `AVACOM_DIAGNOSTICO_VELOCIDAD=0` las apaga. Un cliente que corta a la mitad libera su cupo.

Se monta ENVOLVIENDO la aplicación HTTP en `asgi.py`: lo que no es de aquí pasa intacto a Django.
"""
from __future__ import annotations

import json
import os
import time
from urllib.parse import parse_qs

PREFIJO = "/api/diagnostico/velocidad/"
MAX_MB = 256
MAX_FLUJOS = int(os.environ.get("AVACOM_DIAGNOSTICO_VELOCIDAD_FLUJOS", "12"))
TROZO = 64 * 1024
_CEROS = bytes(TROZO)

_en_uso = 0


def activo() -> bool:
    return os.environ.get("AVACOM_DIAGNOSTICO_VELOCIDAD", "1") != "0"


async def _responder_json(send, estado: int, cuerpo: dict, extra: list | None = None) -> None:
    datos = json.dumps(cuerpo).encode("utf-8")
    await send({"type": "http.response.start", "status": estado, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(datos)).encode()), (b"cache-control", b"no-store"), *(extra or [])]})
    await send({"type": "http.response.body", "body": datos})


def estado_del_nodo() -> dict:
    """Lo que el nodo cuenta de sí mientras se le mide: mediciones en curso y cómo le va a la caché de pases de medios (aciertos, fallos y quién la vació)."""
    try:
        from acceso.aplicacion import cache_pases
        pases = cache_pases.estadisticas()
    except Exception:   # noqa: BLE001 — el diagnóstico nunca tumba al nodo
        pases = None
    return {"mediciones_en_curso": _en_uso, "maximo": MAX_FLUJOS, "cache_pases": pases}


class Medicion:
    """Cupo de mediciones simultáneas. Se toma al entrar y se suelta siempre (aunque el cliente cuelgue)."""

    def __enter__(self):
        global _en_uso
        if _en_uso >= MAX_FLUJOS:
            raise OcupadoError()
        _en_uso += 1
        return self

    def __exit__(self, *_):
        global _en_uso
        _en_uso = max(0, _en_uso - 1)


class OcupadoError(Exception):
    pass


def con_velocidad(http_app):
    """Devuelve una aplicación ASGI que atiende `PREFIJO…` y deja pasar todo lo demás a `http_app`."""

    async def aplicacion(scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(PREFIJO):
            return await http_app(scope, receive, send)
        if not activo():
            return await _responder_json(send, 404, {"detail": "La medición de velocidad está apagada en este nodo."})
        ruta = scope["path"][len(PREFIJO):].strip("/")
        metodo = scope["method"].upper()
        try:
            if ruta == "ping" and metodo in ("GET", "HEAD"):
                return await _responder_json(send, 200, {"ok": True, "t": int(time.time() * 1000)})
            if ruta == "estado" and metodo == "GET":
                return await _responder_json(send, 200, estado_del_nodo())
            if ruta == "descarga" and metodo == "GET":
                return await _descarga(scope, send)
            if ruta == "carga" and metodo == "POST":
                return await _carga(receive, send)
        except OcupadoError:
            return await _responder_json(send, 429, {"detail": "Hay otras mediciones en curso; vuelve a intentarlo en unos segundos."},
                                         [(b"retry-after", b"5")])
        return await _responder_json(send, 404, {"detail": "Esa medición no existe."})

    return aplicacion


async def _descarga(scope, send) -> None:
    consulta = parse_qs(scope.get("query_string", b"").decode("latin1"))
    try:
        mb = min(MAX_MB, max(1, int((consulta.get("mb") or ["10"])[0])))
    except ValueError:
        mb = 10
    total = mb * 1024 * 1024
    with Medicion():
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"application/octet-stream"), (b"content-length", str(total).encode()), (b"cache-control", b"no-store"),
            (b"content-encoding", b"identity")]})
        restante = total
        while restante > 0:
            n = min(TROZO, restante)
            restante -= n
            await send({"type": "http.response.body", "body": _CEROS if n == TROZO else _CEROS[:n], "more_body": restante > 0})


async def _carga(receive, send) -> None:
    with Medicion():
        inicio = time.monotonic()
        total = 0
        while True:
            mensaje = await receive()
            if mensaje["type"] == "http.disconnect":
                return
            total += len(mensaje.get("body", b""))
            if not mensaje.get("more_body", False):
                break
        ms = max(1, int((time.monotonic() - inicio) * 1000))
        await _responder_json(send, 200, {"bytes": total, "ms": ms, "mbps": round(total * 8 / 1_000_000 / (ms / 1000), 2)})
