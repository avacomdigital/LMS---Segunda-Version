"""
Lectura de los archivos de log del nodo (para `GET /api/logs/` y la pestaña «Errores» de OPS) y escritura de los
renglones que suben OPS y Student (`POST /api/logs/clientes/` → backend-clientes.log). Nunca datos personales (§2.6):
lo que se lee se vuelve a sanear por clave antes de salir, por si un archivo viejo trae algo que hoy no se admite.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from django.conf import settings

from ..logging_setup import LOGGER_CLIENTES, sanear

ARCHIVOS_BASE = ("backend-app", "backend-errores", "backend-auditoria", "backend-clientes", "instalacion")
NIVELES = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def carpeta() -> Path:
    return Path(getattr(settings, "AVACOM_LMS_DIR_LOGS_EFECTIVO", Path(settings.BASE_DIR) / "logs"))


def archivos_disponibles() -> list[str]:
    base = carpeta()
    if not base.exists():
        return []
    return sorted({p.name.split(".log")[0] for p in base.glob("*.log*") if p.is_file()})


def leer(filtros: dict, ultimos: int = 200) -> dict:
    """Las últimas `ultimos` líneas (por `ts`) que cumplen los filtros, más un resumen por ruta y nivel."""
    base = carpeta()
    nombres = [filtros["archivo"]] if filtros.get("archivo") else list(ARCHIVOS_BASE)
    nivel_min = NIVELES.get(str(filtros.get("nivel") or "").upper(), 0)
    lineas: list[dict] = []
    vistas: set[tuple] = set()   # un WARNING+ está en su canal Y en errores: se cuenta una vez
    for nombre in nombres:
        for ruta in sorted(base.glob(f"{nombre}.log*"), reverse=True):   # .log.N primero (más viejas), .log al final
            if not ruta.is_file():
                continue
            try:
                with ruta.open(encoding="utf-8", errors="replace") as f:
                    for cruda in f:
                        cruda = cruda.strip()
                        if not cruda:
                            continue
                        try:
                            linea = json.loads(cruda)
                        except ValueError:
                            continue
                        if not isinstance(linea, dict):
                            continue
                        clave = (linea.get("ts"), linea.get("logger"), linea.get("evento"), linea.get("mensaje"), linea.get("corr"))
                        if clave in vistas:
                            continue
                        if _pasa(linea, filtros, nivel_min):
                            vistas.add(clave)
                            linea["archivo"] = nombre
                            lineas.append(linea)
            except OSError:
                continue
    lineas.sort(key=lambda l: str(l.get("ts") or ""))
    recortadas = lineas[-ultimos:] if ultimos > 0 else lineas
    for l in recortadas:
        if l.get("detalle") is not None:
            l["detalle"] = sanear(l["detalle"])
    rutas = Counter(l.get("ruta") for l in lineas if l.get("ruta"))
    niveles = Counter(l.get("nivel") for l in lineas)
    return {"lineas": recortadas, "total": len(lineas), "resumen": {"happy": rutas.get("happy", 0), "sad": rutas.get("sad", 0), "bad": rutas.get("bad", 0),
                                                                    "niveles": dict(niveles)}, "archivos": archivos_disponibles()}


def _pasa(l: dict, filtros: dict, nivel_min: int) -> bool:
    if nivel_min and NIVELES.get(str(l.get("nivel") or "").upper(), 0) < nivel_min:
        return False
    for clave in ("canal", "app", "ruta"):
        if filtros.get(clave) and l.get(clave) != filtros[clave]:
            return False
    if filtros.get("dispositivo") and l.get("dispositivo_id") != filtros["dispositivo"]:
        return False
    if filtros.get("corr") and not str(l.get("corr") or "").startswith(filtros["corr"]):
        return False
    if filtros.get("evento") and filtros["evento"] not in str(l.get("evento") or ""):
        return False
    if filtros.get("desde") and str(l.get("ts") or "") < str(filtros["desde"]):
        return False
    return True


def escribir_de_cliente(renglon: dict, dispositivo_id: str | None, app: str, version_app: str) -> None:
    """Un renglón de OPS/Student va a backend-clientes.log con el `dispositivo_id` autenticado, nunca el declarado."""
    log = logging.getLogger(LOGGER_CLIENTES)
    nivel = NIVELES.get(str(renglon.get("nivel") or "WARNING").upper(), logging.WARNING)
    detalle = {"ts_cliente": renglon.get("ts"), "version_app": renglon.get("version_app") or version_app or None}
    if renglon.get("detalle") is not None:
        detalle["detalle"] = renglon["detalle"]
    if renglon.get("traza"):
        detalle["traza"] = str(renglon["traza"])[:8000]
    log.log(nivel, "%s", str(renglon.get("mensaje") or "")[:2000],
            extra={"canal": renglon.get("canal") or "aplicacion", "app": app, "modulo": renglon.get("modulo") or app,
                   "evento": renglon.get("evento") or None, "ruta": renglon.get("ruta") or None, "corr": renglon.get("corr") or None,
                   "dispositivo_id": dispositivo_id, "detalle": detalle})
