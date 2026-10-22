"""
El contenedor de un `.avupd` (P-02): un ZIP CANÓNICO y SIN COMPRESIÓN, leído de forma ESTRICTA y sin `zipfile`, para que ningún byte que no forme parte del paquete pase sin
verse (A1, A3).

Canónico quiere decir que cada byte del archivo está determinado por su contenido: las entradas van ALMACENADAS (método 0: los bytes del archivo tal cual), y lo que no se
verifica contra el manifiesto (CRC, tamaños, nombres, orden) tiene un valor FIJO (versión 2.0, sin banderas, fecha fija, atributos a cero, sin extras ni comentarios). Así,
cualquier cambio de un solo byte —en el manifiesto, en un archivo, en una cabecera o en el relleno— rompe algo que se comprueba (D-4). Sin compresión no hay descompresión: la
bomba de descompresión no existe por construcción, y un `.py` de 64 MB sigue siendo un archivo de 64 MB. `escribir` produce ese contenedor (lo usan el emisor de pruebas y el emisor
de AVACOM); `abrir` lo exige. Cualquier `zipfile` lo abre para mirarlo.

Lo que `abrir` exige, antes de mirar el contenido de una sola entrada:

  · El registro de fin (EOCD) son los ÚLTIMOS 22 bytes, sin comentario: bytes después de él son «sobrantes»; sin él, el archivo está truncado.
  · El directorio central termina justo donde empieza el EOCD y empieza justo donde termina la última entrada; la primera entrada empieza en el byte 0; las entradas son
    contiguas y van en el mismo orden que el directorio. No hay huecos donde esconder nada.
  · Ni ZIP64, ni cifrado, ni descriptores de datos, ni campos extra, ni comentarios por entrada, ni discos múltiples, ni compresión (método ≠ 0 es `metodo`).
  · La cabecera local de cada entrada coincide con la del directorio (nombre, tamaños, CRC) y ambas traen los valores fijos.
  · Nada de directorios ni enlaces simbólicos; nombres ASCII; sin nombres repetidos.

Y al leer una entrada: el tamaño es el declarado y el CRC cuadra (lo que el manifiesto exige además —bytes y SHA-256— lo comprueba `paquete.verificar`).
"""
from __future__ import annotations

import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass

from . import catalogos as cat
from .errores import rechazo

_FIRMA_LOCAL, _FIRMA_CENTRAL, _FIRMA_FIN = b"PK\x03\x04", b"PK\x01\x02", b"PK\x05\x06"
_LOCAL = struct.Struct("<HHHHHIIIHH")           # tras la firma: versión, flags, método, hora, fecha, crc, comprimido, declarado, largo nombre, largo extra
_CENTRAL = struct.Struct("<HHHHHHIIIHHHHHII")   # tras la firma: hecho por, necesita, flags, método, hora, fecha, crc, comprimido, declarado, nombre, extra, comentario, disco, attr int, attr ext, offset
_FIN = struct.Struct("<HHHHIIH")                # tras la firma: disco, disco del directorio, entradas en este disco, entradas, tamaño del directorio, offset del directorio, comentario
TAM_FIN = 4 + _FIN.size                         # 22
_FLAG_CIFRADO = 0x0001
METODO_ALMACENADO = 0
_S_IFMT, _S_IFDIR, _S_IFLNK = 0o170000, 0o040000, 0o120000
# Los valores FIJOS del contenedor canónico.
VERSION = 20                                    # 2.0; host MS-DOS (byte alto 0)
HORA, FECHA = 0, ((2026 - 1980) << 9) | (1 << 5) | 1      # 2026-01-01 00:00:00 en formato DOS: una fecha válida para cualquier lector, y siempre la misma
ATRIBUTOS_INTERNOS, ATRIBUTOS_EXTERNOS = 0, 0


@dataclass(frozen=True)
class Entrada:
    nombre: str
    crc: int
    tam_declarado: int
    inicio_datos: int


def abrir(datos: bytes) -> tuple[Entrada, ...]:
    """Las entradas del contenedor, en el orden del directorio, o un rechazo con motivo. No lee el contenido de ninguna."""
    datos = bytes(datos)
    n = len(datos)
    if n < TAM_FIN + 30:
        raise rechazo("demasiado_corto")
    fin = datos[-TAM_FIN:]
    if fin[:4] != _FIRMA_FIN:
        pos_fin = datos.rfind(_FIRMA_FIN)
        if pos_fin == -1:
            raise rechazo("truncado" if datos[:4] == _FIRMA_LOCAL else "estructura")
        raise rechazo("truncado" if pos_fin + TAM_FIN > n else "bytes_sobrantes")
    disco, disco_dir, entradas_disco, entradas, tam_dir, pos_dir, largo_comentario = _FIN.unpack(fin[4:])
    if largo_comentario != 0 or disco != 0 or disco_dir != 0 or entradas_disco != entradas:
        raise rechazo("estructura")
    if entradas == 0xFFFF or tam_dir == 0xFFFFFFFF or pos_dir == 0xFFFFFFFF:
        raise rechazo("zip64")
    if entradas == 0:
        raise rechazo("estructura")
    if entradas > cat.MAX_ARCHIVOS + 2:
        raise rechazo("demasiados_archivos")
    fin_dir = pos_dir + tam_dir
    if fin_dir != n - TAM_FIN:
        raise rechazo("bytes_sobrantes" if fin_dir < n - TAM_FIN else "estructura")
    lista: list[Entrada] = []
    pos, esperado = pos_dir, 0
    for _ in range(entradas):
        if pos + 4 + _CENTRAL.size > fin_dir or datos[pos:pos + 4] != _FIRMA_CENTRAL:
            raise rechazo("estructura")
        (hecho_por, necesita, flags, metodo, hora, fecha, crc, comprimido, declarado, largo_nombre, largo_extra, largo_coment, disco_e, iattr, eattr,
         offset) = _CENTRAL.unpack_from(datos, pos + 4)
        inicio_nombre = pos + 4 + _CENTRAL.size
        pos = inicio_nombre + largo_nombre + largo_extra + largo_coment
        if pos > fin_dir or largo_nombre == 0:
            raise rechazo("estructura")
        if comprimido == 0xFFFFFFFF or declarado == 0xFFFFFFFF or offset == 0xFFFFFFFF:
            raise rechazo("zip64")
        if flags & _FLAG_CIFRADO:
            raise rechazo("cifrado")
        if metodo != METODO_ALMACENADO:
            raise rechazo("metodo")
        nombre_b = datos[inicio_nombre:inicio_nombre + largo_nombre]
        tipo = (eattr >> 16) & _S_IFMT
        if tipo == _S_IFLNK:
            raise rechazo("enlace")
        if tipo == _S_IFDIR or nombre_b.endswith(b"/"):
            raise rechazo("directorio")
        if (flags, largo_extra, largo_coment, disco_e, hecho_por, necesita, hora, fecha, iattr, eattr) != (0, 0, 0, 0, VERSION, VERSION, HORA, FECHA, ATRIBUTOS_INTERNOS, ATRIBUTOS_EXTERNOS):
            raise rechazo("estructura")
        if comprimido != declarado or offset != esperado:
            raise rechazo("estructura")
        # la cabecera local tiene que decir lo mismo que el directorio
        if offset + 4 + _LOCAL.size > pos_dir or datos[offset:offset + 4] != _FIRMA_LOCAL:
            raise rechazo("estructura")
        (lver, lflags, lmetodo, lhora, lfecha, lcrc, lcomprimido, ldeclarado, lnombre, lextra) = _LOCAL.unpack_from(datos, offset + 4)
        if lflags & _FLAG_CIFRADO:
            raise rechazo("cifrado")
        if lmetodo != METODO_ALMACENADO:
            raise rechazo("metodo")
        if (lver, lflags, lhora, lfecha, lcrc, lcomprimido, ldeclarado, lnombre, lextra) != (VERSION, 0, HORA, FECHA, crc, declarado, declarado, largo_nombre, 0):
            raise rechazo("estructura")
        inicio_datos = offset + 4 + _LOCAL.size + largo_nombre
        if datos[offset + 4 + _LOCAL.size:inicio_datos] != nombre_b:
            raise rechazo("estructura")
        esperado = inicio_datos + declarado
        if esperado > pos_dir:
            raise rechazo("truncado")
        try:
            nombre = nombre_b.decode("ascii")
        except UnicodeDecodeError:
            raise rechazo("ruta_invalida") from None
        lista.append(Entrada(nombre, crc, declarado, inicio_datos))
    if esperado != pos_dir or pos != fin_dir:
        raise rechazo("estructura")
    nombres = [e.nombre for e in lista]
    if len(set(nombres)) != len(nombres):
        raise rechazo("nombre_duplicado")
    return tuple(lista)


def leer(datos: bytes, entrada: Entrada, maximo: int) -> bytes:
    """El contenido de una entrada (como mucho `maximo` bytes: lo que pase de ahí no es lo que se esperaba). El CRC debe cuadrar."""
    if entrada.tam_declarado > maximo:
        raise rechazo("tamano_distinto")
    salida = bytes(datos[entrada.inicio_datos:entrada.inicio_datos + entrada.tam_declarado])
    if len(salida) != entrada.tam_declarado:
        raise rechazo("truncado")
    if zlib.crc32(salida) & 0xFFFFFFFF != entrada.crc:
        raise rechazo("estructura")
    return salida


# --------------------------------------------------------------------------------------------------------------------------- escritura (el emisor)
def escribir(entradas: Iterable[tuple[str, bytes]], *, atributos: dict[str, int] | None = None, version: int = VERSION) -> bytes:
    """
    El contenedor canónico de `(nombre, contenido)`, en ese orden, sin comprimir. Determinista: el mismo contenido da siempre los mismos bytes.
    `atributos` (nombre → atributos externos) y `version` existen SÓLO para que las pruebas fabriquen contenedores que el lector debe rechazar.
    """
    atributos = atributos or {}
    locales, centrales = [], []
    offset = 0
    for nombre, contenido in entradas:
        nombre_b = nombre.encode("ascii")
        datos = bytes(contenido)
        crc = zlib.crc32(datos) & 0xFFFFFFFF
        local = _FIRMA_LOCAL + _LOCAL.pack(version, 0, METODO_ALMACENADO, HORA, FECHA, crc, len(datos), len(datos), len(nombre_b), 0) + nombre_b + datos
        central = _FIRMA_CENTRAL + _CENTRAL.pack(version, version, 0, METODO_ALMACENADO, HORA, FECHA, crc, len(datos), len(datos), len(nombre_b), 0, 0, 0, ATRIBUTOS_INTERNOS,
                                                 atributos.get(nombre, ATRIBUTOS_EXTERNOS), offset) + nombre_b
        locales.append(local)
        centrales.append(central)
        offset += len(local)
    directorio = b"".join(centrales)
    fin = _FIRMA_FIN + _FIN.pack(0, 0, len(centrales), len(centrales), len(directorio), offset, 0)
    return b"".join(locales) + directorio + fin
