"""
La puerta de la cola de medios para los módulos del nodo. Es lo único que `classroom_engine`, `modo_estudio` y `evaluacion` importan de aquí.

    abrir_medio(...)     los bytes de un medio. Recibe `directo`, la forma de siempre de abrirlo en la fuente: se usa cuando la cola está apagada, no puede
                         ayudar a tiempo o falla por su cuenta. La cola NUNCA hace fallar un medio: lo peor que puede pasar es que se sirva como antes.
    preparar_*           deja en cola, sin esperar y sin lanzar, los medios que se van a necesitar.
    medir_medio(...)     tamaño y SHA-256 para un paquete de estudio.

Los errores de la fuente (la biblioteca cerrada, el curso retirado, el medio inexistente) pasan tal cual: la cola los desenvuelve y la vista los responde igual
que antes de que existiera.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from classroom_engine.aplicacion.puertos import Bytes
from classroom_engine.dominio import errores as e7
from classroom_engine.infraestructura.contenedor import servicios as servicios_aula

from .dominio import catalogos as cat
from .dominio.clave import ClaveMedio
from .dominio.errores import DemasiadoGrande, ErrorDeOrigen
from .dominio.referencias import medios_de
from .infraestructura import contenedor

log = logging.getLogger("avacom.cola_medios")

PROYECCION, EVALUACION, CLASE, ESTUDIO, PAQUETE, PRECARGA = cat.PROYECCION, cat.EVALUACION, cat.CLASE, cat.ESTUDIO, cat.PAQUETE, cat.PRECARGA
MODULO_AULA, MODULO_ESTUDIO, MODULO_EVALUACION = cat.MODULO_AULA, cat.MODULO_ESTUDIO, cat.MODULO_EVALUACION
__all__ = ["abrir_medio", "medir_medio", "preparar_objeto", "preparar_medios", "DemasiadoGrande", "responder"]


def _clave(fuente: str | None, curso_ref: str, media_ref: str, ruta: str | None) -> ClaveMedio | None:
    """La clave con el nombre REAL de la fuente (`biblioteca`/`ejemplo`). None si la fuente pedida no existe: que el camino de siempre dé el error."""
    try:
        nombre = servicios_aula().fuente(fuente or None, curso_ref).nombre
    except e7.ErrorAula:
        return None
    return ClaveMedio.de(nombre, curso_ref, media_ref, ruta)


def _servidor():
    """El servidor de la cola, o None si ni siquiera se pudo construir: lo que llama sirve el medio como siempre."""
    try:
        return contenedor.servidor()
    except Exception:   # noqa: BLE001
        log.exception("La cola de medios no está disponible", extra={"evento": "medios.cola.no_disponible"})
        return None


def abrir_medio(*, fuente: str | None, curso_ref: str, media_ref: str, ruta: str | None, rango: str | None, metodo: str, modulo: str, prioridad: int,
                contexto_ref: str = "", directo: Callable[[], Bytes]) -> Bytes:
    srv = _servidor()
    if srv is None or not srv.cfg.activa:
        return directo()
    clave = _clave(fuente, curso_ref, media_ref, ruta)
    if clave is None:
        return directo()
    try:
        local = srv.abrir(clave, rango, metodo, prioridad=prioridad, modulo=modulo, contexto_ref=contexto_ref)
    except ErrorDeOrigen as error:
        raise error.original from error
    except Exception:   # noqa: BLE001 — un problema de la cola no le cuesta el medio a nadie
        log.exception("La cola de medios falló al abrir %s; se sirve en paso a través", media_ref, extra={"evento": "medios.cola.abrir_fallo"})
        return directo()
    if local is None:
        return directo()
    return Bytes(local.headers.get("content-type") or "application/octet-stream", flujo=local)


def medir_medio(*, fuente: str | None, curso_ref: str, media_ref: str, tope_bytes: int, modulo: str, prioridad: int, contexto_ref: str = "") -> dict | None:
    """{bytes, sha256, mime} o None si la cola no puede medirlo (quien llama lo mide como siempre). Lanza `DemasiadoGrande` y el error original de la fuente."""
    srv = _servidor()
    if srv is None or not srv.cfg.activa:
        return None
    clave = _clave(fuente, curso_ref, media_ref, None)
    if clave is None:
        return None
    try:
        return srv.medir(clave, prioridad=prioridad, modulo=modulo, contexto_ref=contexto_ref, tope_bytes=tope_bytes)
    except ErrorDeOrigen as error:
        raise error.original from error
    except DemasiadoGrande:
        raise
    except Exception:   # noqa: BLE001
        log.exception("La cola de medios falló al medir %s", media_ref, extra={"evento": "medios.cola.medir_fallo"})
        return None


def preparar_medios(medios: list[tuple[str, str]], *, fuente: str | None, curso_ref: str, modulo: str, contexto_ref: str, prioridad: int,
                    persona_id: str = "", dispositivo_id: str = "", reemplazar: bool = False) -> dict:
    """Pone en cola [(media_ref, ruta)] de un curso. Nunca lanza. `reemplazar`: es LA proyección vigente de ese contexto, y las anteriores bajan a prioridad de clase."""
    try:
        srv = _servidor()
        if srv is None or not srv.cfg.activa or not medios:
            return {"encolados": 0, "omitidos": len(medios or [])}
        clave = _clave(fuente, curso_ref, medios[0][0], None)
        if clave is None:
            return {"encolados": 0, "omitidos": len(medios)}
        return srv.preparar(medios, fuente=clave.fuente, curso_ref=curso_ref, modulo=modulo, contexto_ref=contexto_ref, prioridad=prioridad,
                            persona_id=persona_id, dispositivo_id=dispositivo_id, reemplazar=reemplazar)
    except Exception:   # noqa: BLE001
        log.exception("No se pudieron preparar los medios de %s", curso_ref, extra={"evento": "medios.cola.preparar_fallo"})
        return {"encolados": 0, "omitidos": len(medios or [])}


def preparar_objeto(estructura, *, fuente: str | None, curso_ref: str, modulo: str, contexto_ref: str, prioridad: int, persona_id: str = "",
                    dispositivo_id: str = "", reemplazar: bool = False) -> dict:
    """Pone en cola los medios que usa un objeto de la vista de aula (lámina, lectura, laboratorio, actividad)."""
    try:
        medios = medios_de(estructura)
    except Exception:   # noqa: BLE001
        log.exception("No se pudo leer qué medios usa un objeto", extra={"evento": "medios.cola.preparar_fallo"})
        return {"encolados": 0, "omitidos": 0}
    return preparar_medios(medios, fuente=fuente, curso_ref=curso_ref, modulo=modulo, contexto_ref=contexto_ref, prioridad=prioridad,
                           persona_id=persona_id, dispositivo_id=dispositivo_id, reemplazar=reemplazar)


def responder(request, medio: Bytes, metodo: str):
    """La respuesta HTTP de un `Bytes` que vino de la cola (o None si no es de ella: el llamador usa su camino de siempre)."""
    from .aplicacion.respuesta import RespuestaLocal
    from .infraestructura.http import respuesta_http
    if isinstance(medio.flujo, RespuestaLocal):
        return respuesta_http(request, medio.flujo, metodo, contenedor.servidor())
    return None
