"""
Lectura PURA de la tabla SMBIOS que Windows entrega con `GetSystemFirmwareTable('RSMB', 0, …)`: recibe los bytes y devuelve cadenas. La llamada al sistema vive en
`infraestructura/huella_windows.py`; aquí no hay nada del sistema operativo, así que se prueba con tablas fabricadas a mano (incluidas las de placas con relleno OEM).

Estructura del buffer `RawSMBIOSData`: 8 bytes de cabecera (`Used20CallingMethod`, versión mayor, menor, revisión DMI y el largo de la tabla, u32 little endian) y la tabla:
una secuencia de estructuras `tipo(u8) · largo(u8) · handle(u16) · área formateada · cadenas terminadas en 0 · un 0 más`. Se leen cuatro tipos:

    1  Información del sistema   UUID (16 bytes, los tres primeros campos en little endian desde SMBIOS 2.6) y número de serie
    2  Placa base                número de serie
    3  Chasis                    número de serie
    4  Procesador                `ProcessorId` (8 bytes)
"""
from __future__ import annotations

import uuid

TIPO_SISTEMA, TIPO_PLACA, TIPO_CHASIS, TIPO_PROCESADOR, TIPO_FIN = 1, 2, 3, 4, 127
_TOPE_ESTRUCTURAS = 4096
_DOS_CEROS = bytes((0, 0))


def _estructuras(tabla: bytes):
    """Recorre las estructuras de la tabla; para en la de fin (127) o cuando los datos no alcanzan. Nunca lanza por una tabla rota: lo que no se pueda leer, no se lee."""
    pos = 0
    for _ in range(_TOPE_ESTRUCTURAS):
        if pos + 4 > len(tabla):
            return
        tipo, largo = tabla[pos], tabla[pos + 1]
        if largo < 4 or pos + largo > len(tabla):
            return
        formateada = tabla[pos:pos + largo]
        inicio = pos + largo
        if tabla[inicio:inicio + 2] == _DOS_CEROS:             # sin cadenas: dos ceros justo después del área formateada
            cadenas, siguiente = b"", inicio + 2
        else:                                                  # «uno 0 dos 0» y un 0 más que cierra el área
            fin = tabla.find(_DOS_CEROS, inicio)
            if fin < 0:
                return
            cadenas, siguiente = tabla[inicio:fin + 1], fin + 2
        yield tipo, formateada, cadenas
        if tipo == TIPO_FIN:
            return
        pos = siguiente


def _cadena(formateada: bytes, cadenas: bytes, desplazamiento: int) -> str:
    """La cadena a la que apunta el índice (base 1) que hay en `desplazamiento` del área formateada; vacía si no hay."""
    if desplazamiento >= len(formateada):
        return ""
    indice = formateada[desplazamiento]
    if indice == 0:
        return ""
    partes = cadenas.split(bytes((0,)))
    if indice > len(partes) - 1:
        return ""
    return partes[indice - 1].decode("utf-8", "replace").strip()


def leer_tabla(buffer: bytes) -> dict[str, str]:
    """
    Del buffer `RawSMBIOSData` a `{"smbios_uuid", "sistema_serie", "placa_serie", "chasis_serie", "procesador_id"}` (cadenas; vacías si la placa no las trae). El UUID sale con el
    formato habitual (mayúsculas con guiones); `procesador_id` son los 8 bytes del `ProcessorId` en hexadecimal.
    """
    resultado = {"smbios_uuid": "", "sistema_serie": "", "placa_serie": "", "chasis_serie": "", "procesador_id": ""}
    if len(buffer) < 8:
        return resultado
    largo_tabla = int.from_bytes(buffer[4:8], "little")
    tabla = bytes(buffer[8:8 + largo_tabla]) if largo_tabla else bytes(buffer[8:])
    for tipo, formateada, cadenas in _estructuras(tabla):
        if tipo == TIPO_SISTEMA and not resultado["smbios_uuid"]:
            resultado["sistema_serie"] = _cadena(formateada, cadenas, 7)
            if len(formateada) >= 24:
                resultado["smbios_uuid"] = str(uuid.UUID(bytes_le=bytes(formateada[8:24]))).upper()
        elif tipo == TIPO_PLACA and not resultado["placa_serie"]:
            resultado["placa_serie"] = _cadena(formateada, cadenas, 7)
        elif tipo == TIPO_CHASIS and not resultado["chasis_serie"]:
            resultado["chasis_serie"] = _cadena(formateada, cadenas, 7)
        elif tipo == TIPO_PROCESADOR and not resultado["procesador_id"] and len(formateada) >= 16:
            resultado["procesador_id"] = bytes(formateada[8:16])[::-1].hex().upper()
    return resultado


def factores(datos: dict[str, str], machine_guid: str = "") -> dict[int, str]:
    """Los cinco factores de hardware con sus valores crudos (aún sin filtrar la basura): lo que `huella.factores_validos` recibe."""
    from . import huella as h
    return {
        h.F_MACHINE_GUID: machine_guid,
        h.F_SMBIOS_UUID: datos.get("smbios_uuid", ""),
        h.F_PLACA: datos.get("placa_serie", ""),
        h.F_CHASIS: datos.get("chasis_serie", "") or datos.get("sistema_serie", ""),
        h.F_PROCESADOR: datos.get("procesador_id", ""),
    }
