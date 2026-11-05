"""
Unión de varios WAV PCM del mismo formato (los que devuelve la voz del servicio local, uno por trozo de texto) en un único WAV.

Se valida cada WAV (cabecera RIFF/WAVE, formato PCM, bloque `data`) antes de unirlo: un cuerpo que no es audio —una página de error, un JSON, un archivo cortado— no debe llegar a la
app como si fuera sonido. Entre trozos se inserta un silencio breve para que la frase no se corte en seco.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass


class WavInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Info:
    canales: int
    frecuencia: int
    bits: int
    desde: int          # dónde empiezan las muestras
    largo: int          # cuántos bytes de muestras


@dataclass(frozen=True)
class Resultado:
    wav: bytes
    duracion_ms: int
    frecuencia: int


def analizar(wav: bytes) -> Info:
    if len(wav) < 44 or wav[0:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise WavInvalido("La respuesta de voz no es un WAV válido.")
    canales = frecuencia = bits = formato = 0
    pos = 12
    while pos + 8 <= len(wav):
        ident = wav[pos:pos + 4]
        tam = struct.unpack_from("<I", wav, pos + 4)[0]
        if ident == b"fmt ":
            if pos + 8 + 16 > len(wav):
                raise WavInvalido("El WAV está cortado en su cabecera.")
            formato, canales, frecuencia = struct.unpack_from("<HHI", wav, pos + 8)
            bits = struct.unpack_from("<H", wav, pos + 8 + 14)[0]
        elif ident == b"data":
            largo = min(tam, len(wav) - (pos + 8))      # un `data` con tamaño de más (flujo, archivo cortado) se recorta a lo que llegó
            if formato not in (1, 0xFFFE) or canales < 1 or frecuencia < 8000 or bits not in (8, 16, 24, 32):
                raise WavInvalido("El WAV no es PCM o su formato no es válido.")
            paso = canales * (bits // 8)
            largo -= largo % paso                       # sin muestras a medias
            if largo <= 0:
                raise WavInvalido("El WAV no trae audio.")
            return Info(canales, frecuencia, bits, pos + 8, largo)
        pos += 8 + tam + (tam & 1)
    raise WavInvalido("El WAV no contiene el bloque «data».")


def unir(wavs: list[bytes], silencio_ms: int = 150) -> Resultado:
    if not wavs:
        raise WavInvalido("No hay audio que unir.")
    infos = [analizar(w) for w in wavs]
    base = infos[0]
    for otra in infos[1:]:
        if (otra.canales, otra.frecuencia, otra.bits) != (base.canales, base.frecuencia, base.bits):
            raise WavInvalido("Los trozos de audio tienen formatos distintos.")
    paso = base.canales * (base.bits // 8)
    silencio = b"\x00" * (base.frecuencia * silencio_ms // 1000 * paso) if base.bits != 8 else b"\x80" * (base.frecuencia * silencio_ms // 1000 * paso)
    partes: list[bytes] = []
    for i, (w, info) in enumerate(zip(wavs, infos)):
        if i and silencio_ms > 0:
            partes.append(silencio)
        partes.append(w[info.desde:info.desde + info.largo])
    datos = b"".join(partes)
    cabecera = (b"RIFF" + struct.pack("<I", 36 + len(datos)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, base.canales, base.frecuencia, base.frecuencia * paso, paso, base.bits)
                + b"data" + struct.pack("<I", len(datos)))
    return Resultado(cabecera + datos, int(len(datos) / (base.frecuencia * paso) * 1000), base.frecuencia)
