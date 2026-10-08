"""
La persona de cada pase de medios, guardada unos segundos.

Un video, una imagen o un audio del aula se piden con un pase en la dirección (`/api/m/<pase>/…`) y el nodo comprueba la sesión en CADA petición: sesión,
usuario, rol, política de credenciales y credencial, ocho consultas y una conexión nueva a SQLite. La prueba de 35 tabletas (2026-10-08) midió que esa
comprobación era la MITAD del trabajo del nodo mientras servía medios (la entrega de los bytes, el 1 %): con la red llena de imágenes, el nodo tardaba más
en decidir si dejaba pasar que en entregar.

Lo que se guarda es sólo el resultado de esa comprobación (un `Principal`, que es inmutable), por `CACHE_PASES_SEG` segundos. La caché NO se fía del tiempo
para lo importante: cualquier escritura que pueda cambiar la respuesta —cerrar o revocar una sesión, cambiar la clave, desactivar o mover a una persona,
cambiar una política, un rol o un grupo— la vacía al instante y otra vez al confirmarse la transacción (`infraestructura/invalidacion.py`). El tiempo sólo cubre lo que
cambia sin pasar por ahí: la hora (una sesión que caduca sola, la inactividad), que se vuelve a comprobar a lo sumo cada `CACHE_PASES_SEG`.

Sólo la usa el pase de medios (GET/HEAD de medios): las peticiones con `Authorization` siguen comprobándose enteras cada vez.
"""
from __future__ import annotations

import threading
import time

CACHE_PASES_SEG = 15.0
_MAX_ENTRADAS = 4096

_candado = threading.Lock()
_entradas: dict[tuple, tuple[float, object]] = {}
_epoca = 0
_aciertos = 0
_fallos = 0
_vaciados: dict[str, int] = {}     # quién vació la caché y cuántas veces: lo que explica una caché que no acierta


def epoca() -> int:
    """El número de vaciados hasta ahora: quien comprueba lo lee ANTES de consultar la base y sólo guarda si no cambió (un vaciado en medio vale más)."""
    return _epoca


def tomar(clave: tuple, vigencia_seg: float):
    global _aciertos, _fallos
    if vigencia_seg <= 0:
        return None
    with _candado:
        hallada = _entradas.get(clave)
        if hallada is None or time.monotonic() - hallada[0] > vigencia_seg:
            _entradas.pop(clave, None)
            _fallos += 1
            return None
        _aciertos += 1
        return hallada[1]


def guardar(clave: tuple, valor, epoca_al_empezar: int, vigencia_seg: float) -> None:
    if vigencia_seg <= 0:
        return
    with _candado:
        if epoca_al_empezar != _epoca:
            return
        if len(_entradas) >= _MAX_ENTRADAS:
            ahora = time.monotonic()
            for k in [k for k, (t, _) in _entradas.items() if ahora - t > vigencia_seg]:
                _entradas.pop(k, None)
            if len(_entradas) >= _MAX_ENTRADAS:
                _entradas.clear()
        _entradas[clave] = (time.monotonic(), valor)


def limpiar(origen: str = "") -> None:
    global _epoca
    with _candado:
        _epoca += 1
        _entradas.clear()
        if origen:
            _vaciados[origen] = _vaciados.get(origen, 0) + 1


def estadisticas() -> dict:
    with _candado:
        return {"entradas": len(_entradas), "aciertos": _aciertos, "fallos": _fallos, "vaciados": dict(sorted(_vaciados.items(), key=lambda kv: -kv[1])[:8])}
