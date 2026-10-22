"""
El registro de módulos (P-01, BR-012): qué apps del backend son módulos actualizables por separado, con su versión de módulo, su versión de contrato, su serie, lo que
producen y lo que consumen (con el rango de versiones de contrato que aceptan). Vive en `backend/avacom_lms/modulos.json`, provisional hasta que MOD-015 lo absorba.
La versión de DATOS no se escribe ahí: se lee viva de las migraciones aplicadas (D-3).

Formato:

    {"formato": 1, "modulos": {"reporting": {"modulo": "MOD-013", "version": "1.3.0", "version_contrato": 1, "serie": 3, "actualizable": true,
                                             "produce": ["reporte"], "consume": {"nodo": [1, 1], "gradebook": [1, 2]}}}}

Puro: no importa Django.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import version as ver
from .errores import DatosInvalidos

FORMATO_REGISTRO = 1


@dataclass(frozen=True)
class ModuloRegistrado:
    nombre: str
    modulo: str                                   # «MOD-013»
    version: str
    version_contrato: int
    serie: int
    actualizable: bool = True
    produce: tuple[str, ...] = ()                 # prefijos de evento que publica
    consume: dict[str, tuple[int, int]] = field(default_factory=dict)      # {módulo: (contrato mínimo, contrato máximo) que acepta}


@dataclass(frozen=True)
class ModuloInstalado(ModuloRegistrado):
    version_datos: int = 0                        # el número de la última migración aplicada (vivo)


@dataclass(frozen=True)
class Instalacion:
    """Lo que hay instalado, tal como lo ve la compatibilidad (P-04)."""

    version_producto: str
    contrato_biblioteca: int
    modulos: dict[str, ModuloInstalado]
    licencia_admite: bool = True
    motivo_licencia: str = ""


def leer(datos) -> dict[str, ModuloRegistrado]:
    if not isinstance(datos, dict) or datos.get("formato") != FORMATO_REGISTRO or not isinstance(datos.get("modulos"), dict):
        raise DatosInvalidos("El registro de módulos no tiene la forma esperada.")
    salida: dict[str, ModuloRegistrado] = {}
    for nombre, m in datos["modulos"].items():
        if not ver.es_nombre_de_modulo(nombre) or not isinstance(m, dict) or not ver.es_version(m.get("version")):
            raise DatosInvalidos(f"La entrada «{nombre}» del registro de módulos no es válida.")
        consume = {}
        for otro, rango in (m.get("consume") or {}).items():
            if not ver.es_nombre_de_modulo(otro) or not isinstance(rango, list) or len(rango) != 2 or not all(isinstance(x, int) and x >= 1 for x in rango) or rango[0] > rango[1]:
                raise DatosInvalidos(f"El rango de contrato que «{nombre}» consume de «{otro}» no es válido.")
            consume[otro] = (int(rango[0]), int(rango[1]))
        contrato, serie = m.get("version_contrato", 1), m.get("serie", 0)
        if not isinstance(contrato, int) or contrato < 1 or not isinstance(serie, int) or serie < 0:
            raise DatosInvalidos(f"La entrada «{nombre}» del registro de módulos trae un contrato o una serie inválidos.")
        salida[nombre] = ModuloRegistrado(nombre=nombre, modulo=str(m.get("modulo") or ""), version=str(m["version"]), version_contrato=contrato, serie=serie,
                                          actualizable=bool(m.get("actualizable", True)), produce=tuple(str(p) for p in (m.get("produce") or [])), consume=consume)
    return salida


def instalado(registrado: ModuloRegistrado, version_datos: int) -> ModuloInstalado:
    return ModuloInstalado(nombre=registrado.nombre, modulo=registrado.modulo, version=registrado.version, version_contrato=registrado.version_contrato, serie=registrado.serie,
                           actualizable=registrado.actualizable, produce=registrado.produce, consume=registrado.consume, version_datos=int(version_datos))


def como_dict(m: ModuloInstalado) -> dict:
    return {"nombre": m.nombre, "modulo": m.modulo, "version": m.version, "version_datos": m.version_datos, "version_contrato": m.version_contrato, "serie": m.serie,
            "actualizable": m.actualizable, "produce": list(m.produce), "consume": {k: list(v) for k, v in m.consume.items()}}
