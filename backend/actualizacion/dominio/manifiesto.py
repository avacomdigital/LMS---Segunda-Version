"""
El manifiesto de un paquete `.avupd` (P-02, BR-012): qué módulos trae, con qué versión de módulo, de datos y de contrato, qué serie, qué migraciones con su reverso (BR-015),
cada archivo con su tamaño y su SHA-256, y los requisitos (versión mínima instalada, contrato de la biblioteca, cliente mínimo, espacio). Se lee SÓLO después de verificar
la firma: aquí se interpreta, no se confía.

Formato (`formato = 1`), JSON en UTF-8:

    {"formato": 1, "paquete_id": "<uuid>", "nombre": "…", "producto": "AVACOM LMS", "version_producto": "2.12.0", "version_minima": "2.11.0" | null,
     "emitido_en": <ms>, "criticas": [], "nota": "…",
     "modulos": [{"nombre": "reporting", "version": "1.4.0", "version_datos": 4, "version_contrato": 1, "serie": 7, "cambia_contrato": false,
                  "requiere": {"nodo": 1}, "migraciones": [{"nombre": "0004_x", "reverso": "0003_y"}]}],
     "archivos": [{"ruta": "reporting/dominio/boletin.py", "bytes": 1234, "sha256": "<64 hex>"}],
     "requisitos": {"contrato_biblioteca": 2, "cliente_minimo": "2.10.0", "espacio_bytes": 0, "contrato_red": null}}

Puro: no importa Django.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field

from . import catalogos as cat
from . import rutas
from . import version as ver
from .errores import rechazo

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Archivo:
    ruta: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Migracion:
    nombre: str
    reverso: str          # la migración a la que se vuelve (`zero` si es la primera): BR-015, toda migración declara su reverso


@dataclass(frozen=True)
class Modulo:
    nombre: str
    version: str
    version_datos: int
    version_contrato: int
    serie: int
    cambia_contrato: bool = False
    requiere: dict[str, int] = field(default_factory=dict)         # {módulo: versión de contrato mínima que necesita de él}
    migraciones: tuple[Migracion, ...] = ()


@dataclass(frozen=True)
class Requisitos:
    contrato_biblioteca: int | None = None
    cliente_minimo: str | None = None
    espacio_bytes: int = 0
    contrato_red: int | None = None


@dataclass(frozen=True)
class Manifiesto:
    formato: int
    paquete_id: str
    nombre: str
    producto: str
    version_producto: str
    version_minima: str | None
    emitido_en: int
    modulos: tuple[Modulo, ...]
    archivos: tuple[Archivo, ...]
    requisitos: Requisitos = Requisitos()
    criticas: tuple[str, ...] = ()
    nota: str = ""

    @property
    def nombres_de_modulos(self) -> tuple[str, ...]:
        return tuple(m.nombre for m in self.modulos)

    @property
    def serie(self) -> int:
        return max(m.serie for m in self.modulos)

    @property
    def bytes_total(self) -> int:
        return sum(a.bytes for a in self.archivos)

    @property
    def toca_evaluacion(self) -> bool:
        return "evaluacion" in self.nombres_de_modulos

    def modulo(self, nombre: str) -> Modulo | None:
        return next((m for m in self.modulos if m.nombre == nombre), None)


# --------------------------------------------------------------------------------------------------------------------------- lectura (después de la firma)
def _entero(valor, minimo: int = 0, maximo: int = 2**53) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo or valor > maximo:
        raise rechazo("campo_invalido")
    return valor


def _texto(valor, maximo: int, obligatorio: bool = True) -> str:
    if valor is None and not obligatorio:
        return ""
    if not isinstance(valor, str) or (obligatorio and not valor.strip()) or len(valor) > maximo or "\0" in valor:
        raise rechazo("campo_invalido")
    return valor


def _campo(datos: dict, clave: str):
    if clave not in datos:
        raise rechazo("campo_faltante", campo=clave)
    return datos[clave]


def _lista(valor, maximo: int) -> list:
    if not isinstance(valor, list) or len(valor) > maximo:
        raise rechazo("campo_invalido")
    return valor


def _modulo(datos) -> Modulo:
    if not isinstance(datos, dict):
        raise rechazo("campo_invalido")
    nombre = _campo(datos, "nombre")
    if not ver.es_nombre_de_modulo(nombre):
        raise rechazo("campo_invalido")
    version = _campo(datos, "version")
    if not ver.es_version(version):
        raise rechazo("campo_invalido")
    requiere_crudo = datos.get("requiere") or {}
    if not isinstance(requiere_crudo, dict) or len(requiere_crudo) > cat.MAX_MODULOS_POR_PAQUETE:
        raise rechazo("campo_invalido")
    requiere = {}
    for otro, contrato in requiere_crudo.items():
        if not ver.es_nombre_de_modulo(otro):
            raise rechazo("campo_invalido")
        requiere[otro] = _entero(contrato, 1, 10_000)
    migraciones = []
    for m in _lista(datos.get("migraciones") or [], cat.MAX_MIGRACIONES_POR_MODULO):
        if not isinstance(m, dict):
            raise rechazo("campo_invalido")
        nombre_m, reverso = _campo(m, "nombre"), _campo(m, "reverso")
        if not ver.es_nombre_de_migracion(nombre_m) or not (reverso == "zero" or ver.es_nombre_de_migracion(reverso)):
            raise rechazo("campo_invalido")
        migraciones.append(Migracion(nombre_m, reverso))
    cambia = datos.get("cambia_contrato", False)
    if not isinstance(cambia, bool):
        raise rechazo("campo_invalido")
    return Modulo(nombre=nombre, version=version, version_datos=_entero(_campo(datos, "version_datos"), 0, 9999), version_contrato=_entero(_campo(datos, "version_contrato"), 1, 10_000),
                  serie=_entero(_campo(datos, "serie"), 1), cambia_contrato=cambia, requiere=requiere, migraciones=tuple(migraciones))


def _archivo(datos, modulos: tuple[str, ...]) -> Archivo:
    if not isinstance(datos, dict):
        raise rechazo("campo_invalido")
    ruta = rutas.validar(_campo(datos, "ruta"))
    rutas.exigir_dentro_de(ruta, modulos)
    sha = _campo(datos, "sha256")
    if not isinstance(sha, str) or not _SHA256.match(sha):
        raise rechazo("campo_invalido")
    return Archivo(ruta, _entero(_campo(datos, "bytes"), 0, cat.MAX_ARCHIVO_BYTES), sha)


def _requisitos(datos) -> Requisitos:
    if datos is None:
        return Requisitos()
    if not isinstance(datos, dict):
        raise rechazo("campo_invalido")
    biblioteca = datos.get("contrato_biblioteca")
    cliente = datos.get("cliente_minimo")
    red = datos.get("contrato_red")
    if cliente is not None and not ver.es_version(cliente):
        raise rechazo("campo_invalido")
    return Requisitos(contrato_biblioteca=None if biblioteca is None else _entero(biblioteca, 1, 1000), cliente_minimo=cliente,
                      espacio_bytes=_entero(datos.get("espacio_bytes", 0), 0, 1 << 40), contrato_red=None if red is None else _entero(red, 1, 1000))


def leer(datos: bytes) -> Manifiesto:
    """El manifiesto a partir de sus bytes (ya verificados por la firma). Primero la versión del formato y las etiquetas críticas; después, cada campo."""
    try:
        crudo = json.loads(bytes(datos).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise rechazo("manifiesto_ilegible") from None
    if not isinstance(crudo, dict):
        raise rechazo("manifiesto_ilegible")
    if crudo.get("formato") != cat.FORMATO_MANIFIESTO:
        raise rechazo("version_formato_desconocida")
    criticas = _lista(crudo.get("criticas") or [], 32)
    for etiqueta in criticas:
        if not isinstance(etiqueta, str) or etiqueta not in cat.ETIQUETAS_CRITICAS_CONOCIDAS:
            raise rechazo("etiqueta_critica_desconocida")
    producto = _texto(_campo(crudo, "producto"), cat.MAX_NOMBRE)
    if producto != cat.PRODUCTO:
        raise rechazo("producto_distinto")
    paquete_id = _texto(_campo(crudo, "paquete_id"), 36)
    try:
        if str(uuid.UUID(paquete_id)) != paquete_id:
            raise ValueError
    except ValueError:
        raise rechazo("campo_invalido") from None
    version_producto = _campo(crudo, "version_producto")
    version_minima = crudo.get("version_minima")
    if not ver.es_version(version_producto) or (version_minima is not None and not ver.es_version(version_minima)):
        raise rechazo("campo_invalido")
    modulos = tuple(_modulo(m) for m in _lista(_campo(crudo, "modulos"), cat.MAX_MODULOS_POR_PAQUETE))
    if not modulos or len({m.nombre for m in modulos}) != len(modulos):
        raise rechazo("campo_invalido")
    nombres = tuple(m.nombre for m in modulos)
    for nombre in nombres:
        if nombre in cat.APPS_INTOCABLES:
            raise rechazo("ruta_intocable")
    archivos = tuple(_archivo(a, nombres) for a in _lista(_campo(crudo, "archivos"), cat.MAX_ARCHIVOS))
    if not archivos:
        raise rechazo("campo_invalido")
    if len({a.ruta for a in archivos}) != len(archivos):
        raise rechazo("ruta_duplicada")
    if sum(a.bytes for a in archivos) > cat.MAX_PAQUETE_BYTES:
        raise rechazo("demasiado_grande")
    return Manifiesto(formato=cat.FORMATO_MANIFIESTO, paquete_id=paquete_id, nombre=_texto(_campo(crudo, "nombre"), cat.MAX_NOMBRE), producto=producto,
                      version_producto=version_producto, version_minima=version_minima, emitido_en=_entero(_campo(crudo, "emitido_en"), 1), modulos=modulos,
                      archivos=archivos, requisitos=_requisitos(crudo.get("requisitos")), criticas=tuple(criticas), nota=_texto(crudo.get("nota"), cat.MAX_NOTA, obligatorio=False))


# --------------------------------------------------------------------------------------------------------------------------- escritura (el emisor)
def a_dict(m: Manifiesto) -> dict:
    return {
        "formato": m.formato, "paquete_id": m.paquete_id, "nombre": m.nombre, "producto": m.producto, "version_producto": m.version_producto, "version_minima": m.version_minima,
        "emitido_en": m.emitido_en, "criticas": list(m.criticas), "nota": m.nota,
        "modulos": [{"nombre": x.nombre, "version": x.version, "version_datos": x.version_datos, "version_contrato": x.version_contrato, "serie": x.serie,
                     "cambia_contrato": x.cambia_contrato, "requiere": dict(x.requiere), "migraciones": [{"nombre": g.nombre, "reverso": g.reverso} for g in x.migraciones]}
                    for x in m.modulos],
        "archivos": [{"ruta": a.ruta, "bytes": a.bytes, "sha256": a.sha256} for a in m.archivos],
        "requisitos": {"contrato_biblioteca": m.requisitos.contrato_biblioteca, "cliente_minimo": m.requisitos.cliente_minimo, "espacio_bytes": m.requisitos.espacio_bytes,
                       "contrato_red": m.requisitos.contrato_red},
    }


def escribir(m: Manifiesto) -> bytes:
    """Los bytes canónicos del manifiesto (claves ordenadas, sin espacios): lo que se firma."""
    return json.dumps(a_dict(m), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def resumen(m: Manifiesto) -> dict:
    """Lo que se guarda y se muestra de un manifiesto: sin la lista de archivos (sus rutas no viajan en eventos ni asientos; R-13 del nodo)."""
    return {
        "paquete_id": m.paquete_id, "nombre": m.nombre, "version_producto": m.version_producto, "version_minima": m.version_minima, "emitido_en": m.emitido_en, "serie": m.serie,
        "archivos": len(m.archivos), "bytes": m.bytes_total, "nota": m.nota,
        "modulos": [{"nombre": x.nombre, "version": x.version, "version_datos": x.version_datos, "version_contrato": x.version_contrato, "serie": x.serie,
                     "cambia_contrato": x.cambia_contrato, "requiere": dict(x.requiere), "migraciones": [g.nombre for g in x.migraciones]} for x in m.modulos],
        "requisitos": {"contrato_biblioteca": m.requisitos.contrato_biblioteca, "cliente_minimo": m.requisitos.cliente_minimo, "espacio_bytes": m.requisitos.espacio_bytes,
                       "contrato_red": m.requisitos.contrato_red},
    }
