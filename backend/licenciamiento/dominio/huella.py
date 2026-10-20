"""
La huella del equipo maestro (P-04): varios factores de hardware, TOLERANTE (k de n) y sin identificadores crudos (cada factor viaja como un hash con clave de producto).

  1 MachineGuid · 2 UUID de SMBIOS · 3 serie de la placa · 4 serie del chasis · 5 ProcessorId (RESERVADO, no sella) · 6 secreto de instalación (si el hardware no alcanza)

  · Se DESCARTAN los valores basura que las placas OEM de los paneles interactivos traen de fábrica («To be filled by O.E.M.», «Default string», ceros, `FFFF…`, números de
    ejemplo…): un factor basura no identifica a nadie, y dos paneles distintos lo compartirían. En la máquina de desarrollo medida en la Fase 0, las series de placa, de chasis,
    de BIOS y de sistema eran «Default string».
  · El `ProcessorId` NO sella (D-3): es la firma CPUID del MODELO del procesador, igual en todos los equipos del mismo modelo; contarlo haría parecer «hardware» a una huella que no
    distingue una unidad de otra. Sigue en el formato (etiqueta 5) por si una licencia futura lo quisiera.
  · Coincidencia k de n entre los factores de UNIDAD (1 a 4), con k = 2 de 2, 2 de 3 o 3 de 4 (`k_para`): con tres o más sobrevive al cambio de un disco o de una tarjeta, y un
    disco clonado en otra placa no pasa (conserva el MachineGuid pero no los factores de placa). Con sólo dos —disco y placa— no se puede distinguir un clon de una placa cambiada: se
    exigen los dos, y la deriva se resuelve reactivando o liberando.
  · El nivel es `hardware` si hay al menos dos factores válidos y alguno ligado a la placa (2, 3 o 4). Si no, se usa la huella de INSTALACIÓN: un secreto aleatorio del primer
    arranque (protegido con DPAPI de máquina). Su nivel (`instalacion`) se ve en pantalla: es más débil —un disco clonado trae el secreto— y nunca impide activar por tener
    hardware pobre.
  · La deriva de la huella es un modo de fallo ESPERADO (se cambia una placa; se restaura en otro equipo): se resuelve reactivando o liberando, jamás con un bloqueo.

Este archivo es puro: la lectura de Windows (registro, SMBIOS) vive en `infraestructura/huella_windows.py` y sólo le entrega cadenas.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass

F_MACHINE_GUID, F_SMBIOS_UUID, F_PLACA, F_CHASIS, F_PROCESADOR, F_INSTALACION = 1, 2, 3, 4, 5, 6
FACTORES_DE_UNIDAD = (F_MACHINE_GUID, F_SMBIOS_UUID, F_PLACA, F_CHASIS)      # los que sellan una licencia (D-3)
FACTORES_DE_PLACA = (F_SMBIOS_UUID, F_PLACA, F_CHASIS)                         # ligados al hardware: un disco clonado en otra placa no los trae
FACTORES_DE_HARDWARE = FACTORES_DE_UNIDAD
NOMBRES = {F_MACHINE_GUID: "machine_guid", F_SMBIOS_UUID: "smbios_uuid", F_PLACA: "placa", F_CHASIS: "chasis", F_PROCESADOR: "procesador", F_INSTALACION: "instalacion"}

NIVEL_HARDWARE, NIVEL_INSTALACION = "hardware", "instalacion"
MINIMO_DE_FACTORES = 2

# No es un secreto (viaja en el código del nodo): evita que los identificadores sean «buscables» por quien lea una solicitud, y ata el hash a este producto.
CLAVE_DE_PRODUCTO = b"AVACOM LMS \xc2\xb7 huella de equipo \xc2\xb7 v1"

# Textos de relleno que dejan los fabricantes de placas (comparados en minúsculas, con los espacios colapsados y sin puntos finales).
_BASURA = frozenset({
    "to be filled by o.e.m", "to be filled by oem", "default string", "default", "none", "not specified", "not applicable", "n/a", "na", "null", "unknown",
    "system serial number", "chassis serial number", "base board serial number", "baseboard serial number", "system product name", "system manufacturer", "system version",
    "type2 - board serial number", "type1 - serial number", "serial number", "serial", "oem", "o.e.m", "123456789", "1234567890", "0123456789", "0123456789abcdef",
    "01234567890123456789", "123456789012345", "unspecified", "empty", "not available", "chassis manufacture",
    "00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff", "03000200-0400-0500-0006-000700080009", "00020003-0004-0005-0006-000700080009",
    "12345678-1234-1234-1234-123456789abc",
})
_SEPARADORES = re.compile(r"[\s\-_:{}()]")


def normalizar(valor: object) -> str:
    """El valor tal como se compara y se hashea: texto, sin llaves, sin espacios sobrantes y en mayúsculas."""
    if valor is None:
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip().strip("{}").strip().upper()


def es_basura(valor: object) -> bool:
    """¿Este valor NO identifica a un equipo? Vacío, un solo carácter repetido (ceros, `FFFF…`), demasiado corto o un relleno conocido de fabricante."""
    texto = normalizar(valor)
    if not texto:
        return True
    if texto.lower().rstrip(". ") in _BASURA:
        return True
    sin_separadores = _SEPARADORES.sub("", texto)
    return len(sin_separadores) < 4 or len(set(sin_separadores)) == 1


def hash_de_factor(factor: int, valor: object, clave: bytes = CLAVE_DE_PRODUCTO) -> bytes:
    """HMAC-SHA256 con la clave de producto del factor y su valor normalizado. Dos factores distintos nunca comparten hash aunque tengan el mismo valor."""
    return hmac.new(clave, f"{factor}:{normalizar(valor)}".encode("utf-8"), hashlib.sha256).digest()


def factores_validos(crudos: Mapping[int, object], clave: bytes = CLAVE_DE_PRODUCTO) -> dict[int, bytes]:
    """`{factor: hash}` sólo con los factores de UNIDAD cuyo valor sirve: los basura se descartan y el `ProcessorId` no sella (D-3)."""
    return {factor: hash_de_factor(factor, valor, clave) for factor, valor in crudos.items() if factor in FACTORES_DE_UNIDAD and not es_basura(valor)}


def k_para(n_factores: int) -> int:
    """Cuántos de `n` factores de unidad deben coincidir: 2 de 2, 2 de 3 y 3 de 4. Con dos no se puede distinguir un clon de una placa cambiada, así que se exigen los dos."""
    return 3 if n_factores >= 4 else 2


def nivel_de(validos: Mapping[int, bytes]) -> str:
    """`hardware` si hay al menos dos factores de unidad válidos y alguno ligado a la placa; si no, `instalacion`."""
    unidad = [f for f in validos if f in FACTORES_DE_UNIDAD]
    return NIVEL_HARDWARE if len(unidad) >= MINIMO_DE_FACTORES and any(f in FACTORES_DE_PLACA for f in unidad) else NIVEL_INSTALACION


def huella_de_solicitud(validos: Mapping[int, bytes], secreto_de_instalacion: bytes | None, clave: bytes = CLAVE_DE_PRODUCTO) -> tuple[str, int, dict[int, bytes]]:
    """
    Lo que una solicitud (`.avreq`) declara de este equipo: `(nivel, k, {factor: hash})`. Con nivel `hardware` van TODOS los factores de unidad válidos y k = `k_para(n)`. Si no, nivel
    `instalacion`: un solo factor (el secreto de instalación) y k = 1. Nunca se niega la solicitud por tener hardware pobre.
    """
    unidad = {f: h for f, h in validos.items() if f in FACTORES_DE_UNIDAD}
    if nivel_de(unidad) == NIVEL_HARDWARE:
        return NIVEL_HARDWARE, k_para(len(unidad)), unidad
    if not secreto_de_instalacion:
        raise ValueError("sin secreto de instalación no hay huella posible")
    return NIVEL_INSTALACION, 1, {F_INSTALACION: hash_de_factor(F_INSTALACION, secreto_de_instalacion.hex(), clave)}


@dataclass(frozen=True)
class Coincidencia:
    """El resultado de cotejar los factores de una licencia con los de este equipo."""

    k: int
    en_licencia: int            # cuántos factores trae la licencia
    coinciden: int              # cuántos de ellos coinciden con los de este equipo
    ok: bool                    # coinciden k o más
    parcial: bool               # ok, pero no todos: algo cambió (un disco, una tarjeta…)
    nivel: str                  # hardware | instalacion (según los factores de la licencia)


def comparar(licencia_huella, actuales: Mapping[int, bytes], inst_hash: bytes | None = None) -> Coincidencia:
    """
    Cuántos factores de la licencia coinciden con los de este equipo. Comparación en tiempo constante. `actuales` son los factores de hardware válidos de hoy; `inst_hash` es el
    hash del secreto de instalación de este nodo (factor 6), que sólo cuenta si la licencia lo trae.
    """
    coinciden = 0
    for factor, esperado in licencia_huella.factores:
        hoy = inst_hash if factor == F_INSTALACION else actuales.get(factor)
        if hoy is not None and hmac.compare_digest(hoy, esperado):
            coinciden += 1
    nivel = NIVEL_INSTALACION if any(f == F_INSTALACION for f, _ in licencia_huella.factores) else NIVEL_HARDWARE
    ok = coinciden >= licencia_huella.k
    return Coincidencia(licencia_huella.k, len(licencia_huella.factores), coinciden, ok, ok and coinciden < len(licencia_huella.factores), nivel)
