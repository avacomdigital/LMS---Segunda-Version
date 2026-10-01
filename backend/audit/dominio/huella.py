"""
La huella de la cadena (019-02, FUN-196, INV-002). Función pura: la base de las pruebas de cadena.

    huella = SHA-256( huella_previa ‖ contenido canónico del asiento )
    génesis: huella_previa = 64 ceros

Contenido canónico (§3.2): JSON con claves ordenadas, sin espacios, UTF-8, con exactamente los campos de
CAMPOS_CANONICOS; enteros sin notación científica; `null` explícito. Debe ser idéntico al recalcular, por eso el
orden y el formato no dependen de Django ni de la versión del serializador: sólo de `json` de la biblioteca estándar.
"""
from __future__ import annotations

import hashlib
import json

GENESIS = "0" * 64
LARGO = 64

CAMPOS_CANONICOS = (
    "secuencia", "ocurrido_en", "usuario_id", "actor_tipo", "roles_activos", "modulo", "accion", "resultado",
    "objeto_tabla", "objeto_id", "valor_anterior", "valor_nuevo", "motivo", "origen", "dispositivo_id",
    "correlacion_id", "evento_id",
)


def contenido_canonico(asiento: dict) -> str:
    cuerpo = {campo: _normalizar(asiento.get(campo)) for campo in CAMPOS_CANONICOS}
    return json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _normalizar(valor):
    if isinstance(valor, bool) or valor is None or isinstance(valor, (int, str)):
        return valor
    if isinstance(valor, float):
        return int(valor) if valor.is_integer() else valor
    if isinstance(valor, dict):
        return {str(k): _normalizar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    return str(valor)


def calcular(huella_previa: str, asiento: dict) -> str:
    """Hex SHA-256 de `huella_previa ‖ contenido canónico`."""
    previa = (huella_previa or GENESIS).lower()
    if len(previa) != LARGO:
        raise ValueError("La huella previa debe tener 64 caracteres hexadecimales.")
    return hashlib.sha256((previa + contenido_canonico(asiento)).encode("utf-8")).hexdigest()


def es_huella(valor: str | None) -> bool:
    if not valor or len(valor) != LARGO:
        return False
    try:
        int(valor, 16)
    except ValueError:
        return False
    return True
