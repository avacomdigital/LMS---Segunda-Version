"""
El paquete de estudio (D-7, D-8, CAP-047): el manifiesto canónico, su huella y su vigencia. Dominio puro: no importa Django.

El paquete es la lección (la vista de aula SIN claves) más los medios que referencia, con su `huella` (SHA-256 del manifiesto), su
tamaño y su vigencia. Las simulaciones no se empaquetan: son carpetas sin listado en la API (Q-71). Ninguna tabla guarda el manifiesto:
se reconstruye en vivo cada vez que se pide, y la huella guardada es la que el aparato debe confirmar.

La huella es el SHA-256 hexadecimal del JSON canónico del manifiesto SIN el campo `huella`: claves ordenadas, sin espacios, UTF-8 y
sin escapar los caracteres no ASCII. Para que un aparato con otra biblioteca JSON llegue al mismo valor, los números que valen un entero
(`13.0`) viajan como enteros (`13`): es el único punto en que dos serializadores suelen discrepar.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable

from . import catalogos as cat


def normalizar_numeros(valor):
    """Recorre el manifiesto y deja los `float` enteros como `int`; un número no finito (que JSON no admite) queda nulo."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            return None
        return int(valor) if valor.is_integer() else valor
    if isinstance(valor, dict):
        return {str(k): normalizar_numeros(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [normalizar_numeros(v) for v in valor]
    return valor


def serializar_canonico(manifiesto: dict) -> bytes:
    """Claves ordenadas, sin espacios, UTF-8 (`ensure_ascii=False`). Es lo que se hashea."""
    return json.dumps(manifiesto, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def huella_de(manifiesto: dict) -> str:
    """SHA-256 hexadecimal del manifiesto sin el campo `huella`."""
    sin_huella = {k: v for k, v in manifiesto.items() if k != "huella"}
    return hashlib.sha256(serializar_canonico(sin_huella)).hexdigest()


def construir_manifiesto(*, paquete_id: str, asignacion: dict, curso: dict, leccion_ref: str, vigente_hasta: int | None,
                         generado_en: int, leccion: dict, archivos: list[dict], no_incluidos: list[dict]) -> dict:
    """El manifiesto con su huella: `{paquete_id, asignacion, curso, leccion_ref, vigente_hasta, generado_en, leccion, archivos[],
    no_incluidos[], huella}`. `asignacion` es sólo lo estable (estructura y rótulos), nunca el avance ni las fechas: si el profesor
    mueve una fecha, la huella del paquete no cambia."""
    manifiesto = normalizar_numeros({
        "paquete_id": paquete_id, "asignacion": asignacion, "curso": curso, "leccion_ref": leccion_ref,
        "vigente_hasta": vigente_hasta, "generado_en": generado_en, "leccion": leccion,
        "archivos": archivos, "no_incluidos": no_incluidos,
    })
    return {**manifiesto, "huella": huella_de(manifiesto)}


def archivo(*, media_ref: str, clase: str | None, mime: str | None, tamano: int, sha256: str) -> dict:
    """Un medio medido: `{media_ref, clase, mime, bytes, sha256}` (metadatos, nunca contenido)."""
    return {"media_ref": media_ref, "clase": clase, "mime": mime, "bytes": int(tamano), "sha256": sha256}


def no_incluido(media_ref: str, motivo: str) -> dict:
    return {"media_ref": media_ref, "motivo": motivo}


def bytes_total(archivos: Iterable[dict]) -> int:
    return sum(int(a.get("bytes") or 0) for a in archivos)


def es_simulacion(medio: dict | None) -> bool:
    """Una simulación es una carpeta de archivos que la API no lista: no se empaqueta (`simulacion_requiere_nodo`)."""
    return bool(medio) and medio.get("clase") == "simulation"


def evaluar_vencimiento(*, vigente_hasta: int | None, ahora: int, curso_version: str, version_instalada: str | None) -> str | None:
    """¿Venció un paquete? Devuelve el motivo (`vigencia` o `version_nueva`) o None si sigue vigente. La versión sólo cuenta cuando se
    sabe con certeza cuál está instalada (la biblioteca cerrada no vence nada: lo ya descargado sigue sirviendo)."""
    if vigente_hasta is not None and ahora > int(vigente_hasta):
        return cat.VIGENCIA
    if curso_version and version_instalada and version_instalada != curso_version:
        return cat.VERSION_NUEVA
    return None


def resumen_de_estado(paquetes: Iterable[dict]) -> str | None:
    """El estado que resume varios paquetes de una persona (quién completó, CAP-051): el más avanzado de todos."""
    orden = (cat.DISPONIBLE, cat.DESCARGANDOSE, cat.SOLICITADO, cat.VENCIDO, cat.DENEGADO)
    estados = {p["estado"] for p in paquetes}
    return next((e for e in orden if e in estados), None)
