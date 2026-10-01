"""
Firma de manifiestos (019-06, §3.3): HMAC-SHA256 con una clave derivada de `AVACOM_LMS_SECRET` (el mismo mecanismo de
claves del instalador: `AVACOM_LMS_CLAVE_*`). La clave no sale del nodo: la firma prueba «lo emitió este nodo y no fue
modificado». La verificación por terceros con firma asimétrica queda como pregunta al CTO (§6.2).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

from django.conf import settings

VERSION_FORMATO = "auditoria-tramo/1"
_PROPOSITO = b"avacom-lms-auditoria-firma-v1"


def clave() -> bytes:
    propia = getattr(settings, "AVACOM_LMS_CLAVE_AUDITORIA", None)
    if propia:
        try:
            return base64.b64decode(propia)
        except Exception:   # noqa: BLE001 — una clave mal formada no deja el nodo sin firma: se deriva
            pass
    secreto = str(getattr(settings, "SECRET_KEY", "")).encode("utf-8")
    return hashlib.sha256(_PROPOSITO + b"|" + secreto).digest()


def canonico(manifiesto: dict) -> bytes:
    return json.dumps(manifiesto, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def firmar(manifiesto: dict) -> str:
    return "hmac-sha256:" + hmac.new(clave(), canonico(manifiesto), hashlib.sha256).hexdigest()


def verificar(manifiesto: dict, firma: str) -> bool:
    try:
        return hmac.compare_digest(firmar(manifiesto), str(firma or ""))
    except Exception:   # noqa: BLE001
        return False
