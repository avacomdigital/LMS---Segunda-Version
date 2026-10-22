"""
La verificación completa de un `.avupd` (CAP-109, BR-013, P-02), en este orden y sin escribir un byte en disco:

  1. tamaño del archivo dentro de los topes;
  2. el contenedor, estricto (`contenedor.abrir`): estructura, sin bytes sobrantes, sin enlaces, sin duplicados;
  3. `manifiesto.firma` presente y con la forma exacta; el `kid` entre las llaves de publicación que el nodo conoce;
  4. la FIRMA Ed25519 sobre la cabecera y los bytes exactos de `manifiesto.json` (antes de interpretar un solo campo);
  5. el manifiesto: formato, etiquetas críticas, campos, rutas seguras y dentro de los módulos declarados (R-07);
  6. las entradas contra el manifiesto: ni una de más (`archivo_no_declarado`), ni una de menos (`archivo_faltante`), el tamaño declarado en el ZIP igual al del manifiesto;
  7. cada archivo: se descomprime acotado (bomba), el CRC cuadra y el SHA-256 es el del manifiesto.

Un paquete que no pasa cualquiera de los pasos se rechaza con un motivo; el que pasa queda como `Paquete`, del que se puede sacar cada archivo. Puro.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from . import catalogos as cat
from . import contenedor, firma, manifiesto as mf
from .errores import rechazo

MAX_FIRMA_BYTES = 1024            # `manifiesto.firma` mide 71 + largo del kid; uno mayor que esto no es una firma


@dataclass(frozen=True)
class Paquete:
    """Un `.avupd` verificado: el manifiesto, la llave que lo firmó, la huella del archivo completo y las entradas (por ruta) para extraerlo."""

    manifiesto: mf.Manifiesto
    kid: str
    sha256: str
    bytes: int
    datos: bytes
    entradas: Mapping[str, contenedor.Entrada]

    def contenido(self, ruta: str) -> bytes:
        return contenedor.leer(self.datos, self.entradas[ruta], self.entradas[ruta].tam_declarado)

    def archivos(self) -> Iterator[tuple[str, bytes]]:
        """`(ruta, contenido)` de cada archivo declarado, en el orden del manifiesto. Vuelve a comprobar el SHA-256 al leer (lo que se extrae es lo que se verificó)."""
        for archivo in self.manifiesto.archivos:
            contenido = self.contenido(archivo.ruta)
            if hashlib.sha256(contenido).hexdigest() != archivo.sha256:
                raise rechazo("sha_distinto", ruta=archivo.ruta)
            yield archivo.ruta, contenido


def verificar(datos: bytes, claves: Mapping[str, bytes], max_bytes: int = cat.MAX_PAQUETE_BYTES, verificador: firma.Verificador | None = None) -> Paquete:
    """El paquete verificado o un rechazo con motivo (TST-047, TST-048, TST-062). `claves` = `{kid: llave pública de 32 bytes}` de publicación."""
    datos = bytes(datos)
    if len(datos) > min(int(max_bytes), cat.MAX_PAQUETE_BYTES):
        raise rechazo("demasiado_grande")
    entradas = {e.nombre: e for e in contenedor.abrir(datos)}
    if cat.NOMBRE_FIRMA not in entradas:
        raise rechazo("sin_firma")
    if cat.NOMBRE_MANIFIESTO not in entradas:
        raise rechazo("sin_manifiesto")
    if entradas[cat.NOMBRE_FIRMA].tam_declarado > MAX_FIRMA_BYTES:
        raise rechazo("firma_formato")
    sello = firma.leer(contenedor.leer(datos, entradas[cat.NOMBRE_FIRMA], MAX_FIRMA_BYTES))
    clave = claves.get(sello.kid)
    if clave is None:
        raise rechazo("kid_desconocido", kid=sello.kid)
    manifiesto_bytes = contenedor.leer(datos, entradas[cat.NOMBRE_MANIFIESTO], cat.MAX_MANIFIESTO_BYTES)
    if not (verificador or firma.verificar)(clave, sello.firma, firma.mensaje_firmado(sello.kid, manifiesto_bytes, sello.version)):
        raise rechazo("firma_invalida")
    manifiesto = mf.leer(manifiesto_bytes)
    declaradas = {cat.CARPETA_ARCHIVOS + a.ruta: a for a in manifiesto.archivos}
    for nombre in entradas:
        if nombre in (cat.NOMBRE_FIRMA, cat.NOMBRE_MANIFIESTO):
            continue
        if nombre not in declaradas:
            raise rechazo("archivo_no_declarado")
    por_ruta: dict[str, contenedor.Entrada] = {}
    for nombre, archivo in declaradas.items():
        entrada = entradas.get(nombre)
        if entrada is None:
            raise rechazo("archivo_faltante", ruta=archivo.ruta)
        if entrada.tam_declarado != archivo.bytes:
            raise rechazo("tamano_distinto", ruta=archivo.ruta)
        contenido = contenedor.leer(datos, entrada, archivo.bytes)
        if hashlib.sha256(contenido).hexdigest() != archivo.sha256:
            raise rechazo("sha_distinto", ruta=archivo.ruta)
        por_ruta[archivo.ruta] = entrada
    return Paquete(manifiesto=manifiesto, kid=sello.kid, sha256=hashlib.sha256(datos).hexdigest(), bytes=len(datos), datos=datos, entradas=por_ruta)
