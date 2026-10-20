"""
Leer los archivos de licenciamiento que se le dan a la herramienta: una RUTA (lo normal; en Windows también la que se arrastra a la consola, con comillas) o el TEXTO del archivo
(`AVQ1.…`, `AVL1.…`, `AVR1.…`). Se lee como máximo lo que cabe en un archivo de licenciamiento: una ruta cualquiera no se traga entera.
"""
from __future__ import annotations

from pathlib import Path

from .dominio_nodo import licencia, tlv

LIMITE_DE_LECTURA = 64 * 1024


class ErrorDeArchivo(ValueError):
    """No se pudo leer lo que se pidió. El mensaje se le muestra tal cual a quien opera."""


def limpiar(valor: str) -> str:
    """Quita lo que se cuela al escribir o arrastrar una ruta: espacios, comillas y la marca BOM que Windows PowerShell antepone a lo que se le envía por una tubería."""
    return (valor or "").replace("﻿", "").strip().strip('"').strip("'").strip()


def cargar(valor: str, magic: bytes, nombre: str) -> tuple[bytes, str]:
    """`(bytes, de dónde salieron)`. `nombre` es cómo se llama el archivo en los mensajes («la solicitud», «la licencia»…)."""
    valor = limpiar(valor)
    if not valor:
        raise ErrorDeArchivo(f"Falta {nombre}: indica la ruta del archivo (o su texto).")
    prefijo = licencia.PREFIJO_TEXTO[magic]
    if valor.startswith(prefijo):
        try:
            return licencia.de_texto(valor, magic), "texto"
        except Exception as error:     # noqa: BLE001
            raise ErrorDeArchivo(f"El texto de {nombre} no está completo o fue alterado: cópialo de nuevo, entero y sin espacios.") from error
    ruta = Path(valor)
    if not ruta.is_file():
        raise ErrorDeArchivo(f"No se encontró {nombre} en «{valor}».")
    if ruta.stat().st_size > LIMITE_DE_LECTURA:
        raise ErrorDeArchivo(f"«{ruta.name}» es demasiado grande para ser {nombre}.")
    return ruta.read_bytes(), str(ruta)


def escribir(ruta: Path, datos: bytes) -> None:
    """Escribe sin sobrescribir: si ya existe un archivo con ese nombre, no lo pisa."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("xb") as archivo:
        archivo.write(datos)


MAGIC_SOLICITUD, MAGIC_LICENCIA, MAGIC_LIBERACION = tlv.MAGIC_SOLICITUD, tlv.MAGIC_LICENCIA, tlv.MAGIC_LIBERACION
