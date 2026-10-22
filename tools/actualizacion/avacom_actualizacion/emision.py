"""
Armar y firmar un paquete `.avupd` (P-02, P-03) a partir de una DESCRIPCIÓN humana (`paquete.json`) y la carpeta `backend/` de donde salen los archivos.

La descripción dice qué es el paquete (nombre, versión del producto, módulos con su versión, serie, contrato y migraciones con su reverso) y qué archivos lleva cada módulo; el emisor
lee esos archivos, calcula tamaño y SHA-256, escribe el manifiesto canónico, lo firma con la llave privada y empaqueta todo en el contenedor canónico sin comprimir. Antes de entregar
el resultado lo VERIFICA como lo haría un nodo (con la llave pública de la misma llave): si el nodo lo rechazaría, el emisor se niega a entregarlo.

Sólo usa el dominio del nodo: lo que se emite y lo que el nodo lee no pueden diferir.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from .dominio_nodo import catalogos as cat
from .dominio_nodo import contenedor, errores, firma
from .dominio_nodo import manifiesto as mf
from .dominio_nodo import paquete as dom_paquete


class ErrorDeEmision(ValueError):
    """La descripción o los archivos no permiten emitir el paquete. El mensaje se le muestra tal cual a quien opera."""


def _archivos_de(origen: Path, patron: str) -> list[str]:
    """Una ruta relativa a `backend/` (con `/`) o, si termina en `/`, todos los archivos de esa carpeta (sin `__pycache__` ni `.pyc`)."""
    if not patron.endswith("/"):
        return [patron]
    base = origen / patron.rstrip("/")
    if not base.is_dir():
        raise ErrorDeEmision(f"La carpeta «{patron}» no existe en {origen}.")
    salida = []
    for archivo in sorted(base.rglob("*")):
        relativo = archivo.relative_to(origen).as_posix()
        if archivo.is_file() and "__pycache__" not in relativo.split("/") and archivo.suffix != ".pyc":
            salida.append(relativo)
    return salida


def construir_manifiesto(descripcion: dict, origen: Path, *, ahora_ms: int | None = None) -> tuple[mf.Manifiesto, dict[str, bytes]]:
    """`(manifiesto, {ruta: contenido})`. Lanza `ErrorDeEmision` con un mensaje claro si algo no cuadra."""
    origen = Path(origen)
    try:
        modulos_json = descripcion["modulos"]
        rutas: list[str] = []
        modulos = []
        for m in modulos_json:
            for patron in m.get("archivos", []):
                for ruta in _archivos_de(origen, str(patron)):
                    if ruta not in rutas:
                        rutas.append(ruta)
            modulos.append(mf.Modulo(
                nombre=m["nombre"], version=m["version"], version_datos=int(m["version_datos"]), version_contrato=int(m["version_contrato"]), serie=int(m["serie"]),
                cambia_contrato=bool(m.get("cambia_contrato", False)), requiere={str(k): int(v) for k, v in dict(m.get("requiere", {})).items()},
                migraciones=tuple(mf.Migracion(str(g["nombre"]), str(g["reverso"])) for g in m.get("migraciones", []))))
        for patron in descripcion.get("archivos_extra", []):
            for ruta in _archivos_de(origen, str(patron)):
                if ruta not in rutas:
                    rutas.append(ruta)
        contenidos: dict[str, bytes] = {}
        for ruta in rutas:
            archivo = origen / Path(*ruta.split("/"))
            if not archivo.is_file():
                raise ErrorDeEmision(f"No existe el archivo «{ruta}» en {origen}.")
            contenidos[ruta] = archivo.read_bytes()
        r = descripcion.get("requisitos", {}) or {}
        manifiesto = mf.Manifiesto(
            formato=cat.FORMATO_MANIFIESTO, paquete_id=str(descripcion.get("paquete_id") or uuid.uuid4()), nombre=str(descripcion["nombre"]), producto=cat.PRODUCTO,
            version_producto=str(descripcion["version_producto"]), version_minima=descripcion.get("version_minima"),
            emitido_en=int(ahora_ms if ahora_ms is not None else descripcion.get("emitido_en") or time.time() * 1000),
            modulos=tuple(modulos),
            archivos=tuple(mf.Archivo(ruta, len(c), hashlib.sha256(c).hexdigest()) for ruta, c in contenidos.items()),
            requisitos=mf.Requisitos(contrato_biblioteca=r.get("contrato_biblioteca"), cliente_minimo=r.get("cliente_minimo"), espacio_bytes=int(r.get("espacio_bytes") or 0),
                                     contrato_red=r.get("contrato_red")),
            criticas=tuple(descripcion.get("criticas", [])), nota=str(descripcion.get("nota", "")))
    except KeyError as error:
        raise ErrorDeEmision(f"A la descripción le falta el campo «{error.args[0]}».") from None
    except (TypeError, ValueError, AttributeError) as error:
        raise ErrorDeEmision(f"La descripción tiene un valor inválido: {error}.") from None
    return manifiesto, contenidos


def emitir(descripcion: dict, origen: Path, kid: str, clave_privada: bytes, *, ahora_ms: int | None = None) -> tuple[bytes, mf.Manifiesto]:
    """El `.avupd` firmado y su manifiesto. Se vuelve a verificar con la pública de la misma llave antes de devolverlo."""
    manifiesto, contenidos = construir_manifiesto(descripcion, origen, ahora_ms=ahora_ms)
    # El nodo es quien manda: el manifiesto pasa por su lector (rutas seguras, dentro de los módulos, etiquetas críticas...) ANTES de firmarlo.
    manifiesto_bytes = mf.escribir(manifiesto)
    try:
        mf.leer(manifiesto_bytes)
    except errores.PaqueteRechazado as error:
        raise ErrorDeEmision(f"El nodo rechazaría este paquete ({error.motivo}): {error.detalle}") from None
    entradas = [(cat.NOMBRE_MANIFIESTO, manifiesto_bytes), (cat.NOMBRE_FIRMA, firma.sellar(kid, clave_privada, manifiesto_bytes))]
    entradas += [(cat.CARPETA_ARCHIVOS + a.ruta, contenidos[a.ruta]) for a in manifiesto.archivos]
    datos = contenedor.escribir(entradas)
    verificar(datos, {kid: firma.publica_de(clave_privada)})
    return datos, manifiesto


def verificar(datos: bytes, claves: dict[str, bytes]) -> dom_paquete.Paquete:
    """La verificación COMPLETA del nodo. Un rechazo se vuelve `ErrorDeEmision` con el motivo."""
    try:
        return dom_paquete.verificar(datos, claves)
    except errores.PaqueteRechazado as error:
        raise ErrorDeEmision(f"El paquete no pasa la verificación del nodo: {error.motivo} ({error.detalle})") from None
